"""Frontend agent for Vue 3 + Mosaic Design System tasks."""

import logging
import re
from pathlib import Path

from backend.llm.prompt_templates import get_frontend_agent_prompt
from backend.orchestrator.worker_agent import WorkerAgent, FileOperationError
from backend.queue.redis_queue import Task

logger = logging.getLogger(__name__)


class FrontendAgent(WorkerAgent):
    """Agent specialized in Vue 3 + Mosaic Design System development."""

    async def _invoke_llm_for_task(self, task: Task) -> str:
        """
        Invoke LLM with frontend-specific prompt.

        Args:
            task: Task to execute

        Returns:
            LLM response with Vue component code
        """
        # Get existing file contents for files to modify
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
        prompt = get_frontend_agent_prompt(
            task=task,
            existing_files=file_contents
        )

        # Invoke Claude
        response = self.bedrock.invoke_model(
            prompt=prompt,
            system_prompt=(
                "You are an expert Vue 3 developer specializing in the Mosaic Design System. "
                "You write clean, type-safe TypeScript code with proper composition API patterns. "
                "Always follow MDS component guidelines and best practices."
            ),
            max_tokens=8000
        )

        return response.content

    async def _apply_changes(self, llm_response: str, task: Task) -> list[str]:
        """
        Parse LLM response and apply changes to Vue files.

        Expected format:
        ```vue
        <!-- filepath: src/components/MyComponent.vue -->
        <template>
          ...
        </template>
        <script setup lang="ts">
        ...
        </script>
        <style scoped>
        ...
        </style>
        ```

        Args:
            llm_response: LLM response with Vue component code
            task: Task being executed

        Returns:
            List of modified file paths
        """
        modified_files = []

        # Extract code blocks with file paths
        # Pattern: <!-- filepath: path/to/file.vue --> or // filepath: path/to/file.ts
        file_pattern = r'(?:<!--\s*filepath:\s*([^\s]+)\s*-->|//\s*filepath:\s*([^\s]+))'
        code_block_pattern = r'```(?:vue|typescript|ts)?\n(.*?)```'

        # Find all file markers
        file_markers = list(re.finditer(file_pattern, llm_response, re.IGNORECASE))

        if not file_markers:
            # Fallback: assume single file for files_to_create
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
                    "Expected format: <!-- filepath: path/to/file.vue -->"
                )
        else:
            # Process each file
            for i, marker in enumerate(file_markers):
                file_path = marker.group(1) or marker.group(2)

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
                else:
                    logger.warning(f"No code block found for {file_path}")

        if not modified_files:
            raise FileOperationError("No files were modified by LLM response")

        return modified_files

    async def _write_file(self, relative_path: str, content: str) -> None:
        """
        Write content to file in worktree, creating parent directories if needed.

        Args:
            relative_path: Path relative to project root
            content: File content to write
        """
        full_path = self.worktree_path / relative_path

        try:
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(full_path, 'w') as f:
                f.write(content)

            logger.debug(f"Wrote file: {full_path}")

        except Exception as e:
            raise FileOperationError(f"Failed to write {relative_path}: {e}") from e
