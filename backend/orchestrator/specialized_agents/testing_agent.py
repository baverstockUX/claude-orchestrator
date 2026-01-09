"""Testing agent for pytest and vitest test generation."""

import logging
import re

from backend.llm.prompt_templates import get_testing_agent_prompt
from backend.orchestrator.worker_agent import WorkerAgent, FileOperationError
from backend.queue.redis_queue import Task

logger = logging.getLogger(__name__)


class TestingAgent(WorkerAgent):
    """Agent specialized in writing pytest and vitest tests."""

    async def _invoke_llm_for_task(self, task: Task) -> str:
        """
        Invoke LLM with testing-specific prompt.

        Args:
            task: Task to execute

        Returns:
            LLM response with test code
        """
        # Read implementation files to test
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
        prompt = get_testing_agent_prompt(
            task=task,
            existing_files=file_contents
        )

        # Invoke Claude
        response = self.bedrock.invoke_model(
            prompt=prompt,
            system_prompt=(
                "You are an expert in test-driven development, specializing in pytest for Python "
                "and vitest for TypeScript/Vue. You write comprehensive, maintainable tests with "
                "good coverage, proper mocking, and clear assertions."
            ),
            max_tokens=8000
        )

        return response.content

    async def _apply_changes(self, llm_response: str, task: Task) -> list[str]:
        """
        Parse LLM response and apply changes to test files.

        Expected format:
        ```python
        # filepath: tests/test_api.py
        import pytest
        ...
        ```

        Args:
            llm_response: LLM response with test code
            task: Task being executed

        Returns:
            List of modified file paths
        """
        modified_files = []

        # Extract code blocks with file paths
        file_pattern = r'#\s*filepath:\s*([^\s]+)'
        code_block_pattern = r'```(?:python|typescript|ts)?\n(.*?)```'

        # Find all file markers
        file_markers = list(re.finditer(file_pattern, llm_response, re.IGNORECASE))

        if not file_markers:
            # Fallback: assume single test file
            if len(task.files_to_create) == 1:
                logger.info(f"No file markers found, assuming single file: {task.files_to_create[0]}")
                code_blocks = re.findall(code_block_pattern, llm_response, re.DOTALL)
                if code_blocks:
                    file_path = task.files_to_create[0]
                    content = code_blocks[0].strip()
                    await self._write_file(file_path, content)
                    modified_files.append(file_path)
            else:
                raise FileOperationError(
                    "No file path markers found in LLM response. "
                    "Expected format: # filepath: tests/test_something.py"
                )
        else:
            # Process each file
            for i, marker in enumerate(file_markers):
                file_path = marker.group(1)

                # Extract content between this marker and next (or end)
                start_pos = marker.end()
                end_pos = file_markers[i + 1].start() if i + 1 < len(file_markers) else len(llm_response)
                section = llm_response[start_pos:end_pos]

                # Extract code from code blocks
                code_blocks = re.findall(code_block_pattern, section, re.DOTALL)

                if code_blocks:
                    content = code_blocks[0].strip()
                    await self._write_file(file_path, content)
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
