"""Base worker agent for task execution."""

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from backend.git.worktree_manager import WorktreeManager
from backend.locking.redis_lock import RedisLock, Lock
from backend.llm.bedrock_client import BedrockClient, BedrockInvocationError
from backend.queue.redis_queue import RedisQueue, Task

logger = logging.getLogger(__name__)


class AgentConfig(BaseModel):
    """Configuration for worker agent."""
    agent_id: str
    agent_type: str  # frontend, backend, testing, docs, infra, integration
    project_path: Path
    max_retries: int = 3
    task_timeout: int = 300  # 5 minutes
    heartbeat_interval: int = 30  # seconds


class TaskResult(BaseModel):
    """Result of task execution."""
    success: bool
    commit_sha: Optional[str] = None
    error_message: Optional[str] = None
    files_modified: list[str] = []
    execution_time: float = 0.0


class WorkerAgent(ABC):
    """Base class for worker agents that execute tasks in git worktrees."""

    def __init__(
        self,
        config: AgentConfig,
        bedrock_client: BedrockClient,
        task_queue: RedisQueue,
        lock_manager: RedisLock,
        worktree_manager: WorktreeManager
    ):
        """
        Initialize worker agent.

        Args:
            config: Agent configuration
            bedrock_client: Bedrock client for LLM invocation
            task_queue: Redis task queue
            lock_manager: Redis lock manager for file safety
            worktree_manager: Git worktree manager
        """
        self.config = config
        self.bedrock = bedrock_client
        self.queue = task_queue
        self.locks = lock_manager
        self.worktrees = worktree_manager

        self.worktree_path: Optional[Path] = None
        self.current_task: Optional[Task] = None
        self.is_running = False
        self.acquired_locks: list[Lock] = []

        logger.info(
            f"Initialized {self.config.agent_type} agent: {self.config.agent_id}"
        )

    async def spawn(self, base_branch: Optional[str] = None) -> None:
        """
        Spawn agent with dedicated git worktree.

        Creates a new git worktree branch for this agent's isolated work.

        Args:
            base_branch: Base branch to branch from (default: repo's active branch or "main")
        """
        try:
            branch_name = f"agent-{self.config.agent_id}"

            # Get current branch if not specified
            if not base_branch:
                try:
                    base_branch = self.worktrees.repo.active_branch.name
                except Exception:
                    base_branch = "main"

            self.worktree_path = self.worktrees.create_worktree(
                branch_name=branch_name,
                base_branch=base_branch
            )
            logger.info(
                f"Agent {self.config.agent_id} spawned with worktree: {self.worktree_path}"
            )
        except Exception as e:
            logger.error(f"Failed to spawn agent {self.config.agent_id}: {e}")
            raise AgentSpawnError(f"Failed to create worktree: {e}") from e

    async def run_loop(self) -> None:
        """
        Main agent loop: poll queue, execute tasks, report results.

        Runs until stopped or fatal error occurs.
        """
        self.is_running = True
        logger.info(f"Agent {self.config.agent_id} starting run loop")

        try:
            while self.is_running:
                try:
                    # Poll queue for tasks matching agent type
                    task = await self.queue.dequeue(
                        agent_type=self.config.agent_type,
                        timeout=10  # Non-blocking with timeout
                    )

                    if not task:
                        # No task available, continue polling
                        await asyncio.sleep(1)
                        continue

                    self.current_task = task
                    logger.info(
                        f"Agent {self.config.agent_id} received task: {task.id}"
                    )

                    # Execute task
                    result = await self._execute_task(task)

                    # Report result
                    if result.success:
                        await self.queue.mark_completed(task.id)
                        logger.info(
                            f"Task {task.id} completed successfully: {result.commit_sha}"
                        )
                    else:
                        await self.queue.mark_failed(
                            task.id,
                            error_message=result.error_message or "Unknown error"
                        )
                        logger.error(f"Task {task.id} failed: {result.error_message}")

                    self.current_task = None

                except asyncio.CancelledError:
                    logger.info(f"Agent {self.config.agent_id} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in agent run loop: {e}", exc_info=True)
                    if self.current_task:
                        await self.queue.mark_failed(
                            self.current_task.id,
                            error_message=str(e)
                        )
                    await asyncio.sleep(5)  # Back off on errors

        finally:
            self.is_running = False
            logger.info(f"Agent {self.config.agent_id} stopped")

    async def _execute_task(self, task: Task) -> TaskResult:
        """
        Execute task with LLM invocation in worktree.

        Args:
            task: Task to execute

        Returns:
            TaskResult with success status and details
        """
        import time
        start_time = time.time()

        try:
            # 1. Acquire locks on files to modify
            logger.info(f"Acquiring locks for task {task.id}")
            await self._acquire_file_locks(task)

            # 2. Invoke LLM to generate code changes
            logger.info(f"Invoking LLM for task {task.id}")
            llm_response = await self._invoke_llm_for_task(task)

            # 3. Apply changes to worktree
            logger.info(f"Applying changes for task {task.id}")
            modified_files = await self._apply_changes(llm_response, task)

            # 4. Commit changes
            logger.info(f"Committing changes for task {task.id}")
            commit_sha = self.worktrees.commit_in_worktree(
                worktree_path=self.worktree_path,
                message=f"{task.title}\n\n{task.description}",
                author_name=f"Agent-{self.config.agent_type}",
                author_email=f"agent-{self.config.agent_id}@orchestrator.local"
            )

            execution_time = time.time() - start_time

            return TaskResult(
                success=True,
                commit_sha=commit_sha,
                files_modified=modified_files,
                execution_time=execution_time
            )

        except Exception as e:
            logger.error(f"Task execution failed: {e}", exc_info=True)
            execution_time = time.time() - start_time
            return TaskResult(
                success=False,
                error_message=str(e),
                execution_time=execution_time
            )

        finally:
            # Always release locks
            await self._release_file_locks()

    async def _acquire_file_locks(self, task: Task) -> None:
        """
        Acquire distributed locks on all files this task will modify.

        Args:
            task: Task with files_to_create and files_to_modify
        """
        all_files = task.files_to_create + task.files_to_modify

        for file_path in all_files:
            try:
                lock = await self.locks.acquire(
                    resource=f"file:{file_path}",
                    timeout=self.config.task_timeout
                )
                self.acquired_locks.append(lock)
                logger.debug(f"Acquired lock on {file_path}")
            except Exception as e:
                # Release already acquired locks
                await self._release_file_locks()
                raise LockAcquisitionError(
                    f"Failed to acquire lock on {file_path}: {e}"
                ) from e

    async def _release_file_locks(self) -> None:
        """Release all acquired locks."""
        for lock in self.acquired_locks:
            try:
                await self.locks.release(lock)
                logger.debug(f"Released lock on {lock.resource}")
            except Exception as e:
                logger.error(f"Failed to release lock {lock.resource}: {e}")

        self.acquired_locks.clear()

    @abstractmethod
    async def _invoke_llm_for_task(self, task: Task) -> str:
        """
        Invoke LLM with task-specific prompt to generate code changes.

        Subclasses must implement this with specialized prompts.

        Args:
            task: Task to execute

        Returns:
            LLM response with code changes

        Raises:
            BedrockInvocationError: If LLM invocation fails
        """
        pass

    @abstractmethod
    async def _apply_changes(self, llm_response: str, task: Task) -> list[str]:
        """
        Apply LLM-generated changes to files in worktree.

        Subclasses must implement this with file parsing logic.

        Args:
            llm_response: LLM response with code changes
            task: Task being executed

        Returns:
            List of modified file paths

        Raises:
            FileOperationError: If file operations fail
        """
        pass

    async def cleanup(self) -> None:
        """
        Cleanup agent resources and remove worktree.

        Should be called when agent is no longer needed.
        """
        logger.info(f"Cleaning up agent {self.config.agent_id}")

        # Release any remaining locks
        await self._release_file_locks()

        # Remove worktree
        if self.worktree_path:
            try:
                self.worktrees.remove_worktree(self.worktree_path)
                logger.info(f"Removed worktree: {self.worktree_path}")
            except Exception as e:
                logger.error(f"Failed to remove worktree: {e}")

        self.worktree_path = None

    def stop(self) -> None:
        """Signal agent to stop processing tasks."""
        logger.info(f"Stopping agent {self.config.agent_id}")
        self.is_running = False


class AgentSpawnError(Exception):
    """Raised when agent fails to spawn."""
    pass


class LockAcquisitionError(Exception):
    """Raised when agent fails to acquire required locks."""
    pass


class FileOperationError(Exception):
    """Raised when file operations fail."""
    pass
