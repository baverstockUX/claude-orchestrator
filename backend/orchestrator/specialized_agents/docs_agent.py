"""Documentation agent for README and API docs."""

import logging
import re

from backend.llm.prompt_templates import get_docs_agent_prompt
from backend.orchestrator.worker_agent import WorkerAgent, FileOperationError
from backend.queue.redis_queue import Task

logger = logging.getLogger(__name__)


class DocsAgent(WorkerAgent):
    """Agent specialized in writing documentation."""

    async def _invoke_llm_for_task(self, task: Task) -> str:
        """
        Invoke LLM with docs-specific prompt.

        Args:
            task: Task to execute

        Returns:
            LLM response with documentation
        """
        # Read relevant code files to document
        file_contents = {}
        for file_path in task.files_to_modify:
            full_path = self.worktree_path / file_path
            if full_path.exists():
                try:
                    with open(full_path, 'r') as f:
                        file_contents[file_path] = f.read()
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")

        # Generate prompt
        prompt = get_docs_agent_prompt(
            task=task,
            existing_files=file_contents
        )

        # Invoke Claude
        response = self.bedrock.invoke_model(
            prompt=prompt,
            system_prompt=(
                "You are an expert technical writer specializing in clear, concise documentation. "
                "You write comprehensive README files, API documentation, and setup guides that "
                "are easy to follow and well-structured."
            ),
            max_tokens=8000
        )

        return response.content

    async def _apply_changes(self, llm_response: str, task: Task) -> list[str]:
        """
        Parse LLM response and apply changes to documentation files.

        Expected format:
        <!-- filepath: README.md -->
        # Project Title
        ...

        Args:
            llm_response: LLM response with documentation
            task: Task being executed

        Returns:
            List of modified file paths
        """
        modified_files = []

        # Extract markdown sections with file paths
        file_pattern = r'(?:<!--\s*filepath:\s*([^\s]+)\s*-->|#\s*filepath:\s*([^\s]+))'

        # Find all file markers
        file_markers = list(re.finditer(file_pattern, llm_response, re.IGNORECASE))

        if not file_markers:
            # Fallback: assume single file for files_to_create
            if len(task.files_to_create) == 1:
                logger.info(f"No file markers found, assuming single file: {task.files_to_create[0]}")
                # Remove code block markers if present
                content = llm_response.strip()
                if content.startswith("```"):
                    content = re.sub(r'```(?:markdown|md)?\n', '', content, count=1)
                    content = re.sub(r'\n```$', '', content)
                await self._write_file(task.files_to_create[0], content.strip())
                modified_files.append(task.files_to_create[0])
            else:
                raise FileOperationError(
                    "No file path markers found in LLM response. "
                    "Expected format: <!-- filepath: path/to/file.md -->"
                )
        else:
            # Process each file
            for i, marker in enumerate(file_markers):
                file_path = marker.group(1) or marker.group(2)

                # Extract content between this marker and next (or end)
                start_pos = marker.end()
                end_pos = file_markers[i + 1].start() if i + 1 < len(file_markers) else len(llm_response)
                content = llm_response[start_pos:end_pos].strip()

                # Remove code block markers if present
                if "```" in content:
                    content = re.sub(r'```(?:markdown|md)?\n', '', content, count=1)
                    content = re.sub(r'\n```$', '', content)

                await self._write_file(file_path, content.strip())
                modified_files.append(file_path)
                logger.info(f"Applied changes to {file_path}")

        if not modified_files:
            raise FileOperationError("No files were modified by LLM response")

        return modified_files

    async def _write_file(self, relative_path: str, content: str) -> None:
        """Write content to file in worktree."""
        full_path = self.worktree_path / relative_path

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
            logger.debug(f"Wrote file: {full_path}")
        except Exception as e:
            raise FileOperationError(f"Failed to write {relative_path}: {e}") from e
