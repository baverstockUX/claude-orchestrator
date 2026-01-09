"""Redis-based task queue with dependency management."""

import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Task(BaseModel):
    """Task model for queue."""
    id: str
    title: str
    description: str
    agent_type: str  # frontend, backend, testing, docs, infra, integration
    files_to_create: list[str] = []
    files_to_modify: list[str] = []
    dependencies: list[str] = []  # Task IDs that must complete first
    estimated_hours: float = 2.0
    created_at: str = ""
    project_id: str = ""

    @classmethod
    def from_redis(cls, data: dict[bytes, bytes]) -> "Task":
        """Create Task from Redis hash data."""
        return cls(
            id=data[b"id"].decode(),
            title=data[b"title"].decode(),
            description=data.get(b"description", b"").decode(),
            agent_type=data[b"agent_type"].decode(),
            files_to_create=json.loads(data.get(b"files_to_create", b"[]")),
            files_to_modify=json.loads(data.get(b"files_to_modify", b"[]")),
            dependencies=json.loads(data.get(b"dependencies", b"[]")),
            estimated_hours=float(data.get(b"estimated_hours", b"2.0")),
            created_at=data.get(b"created_at", b"").decode(),
            project_id=data.get(b"project_id", b"").decode()
        )


class TaskResult(BaseModel):
    """Result of task execution."""
    task_id: str
    success: bool
    commit_sha: Optional[str] = None
    files_changed: list[str] = []
    error_message: Optional[str] = None
    execution_time_seconds: float = 0.0


class RedisQueue:
    """Redis-based task queue with dependency management."""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Redis queue.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client

    async def enqueue(self, task: Task) -> None:
        """
        Add task to appropriate agent type queue.

        If task has unsatisfied dependencies, it's added to pending set.

        Args:
            task: Task to enqueue
        """
        queue_key = f"task:queue:{task.agent_type}"
        task_key = f"task:{task.id}"

        # Store task metadata
        task_data = {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "agent_type": task.agent_type,
            "files_to_create": json.dumps(task.files_to_create),
            "files_to_modify": json.dumps(task.files_to_modify),
            "dependencies": json.dumps(task.dependencies),
            "estimated_hours": str(task.estimated_hours),
            "created_at": task.created_at or datetime.utcnow().isoformat(),
            "project_id": task.project_id
        }

        await self.redis.hset(task_key, mapping=task_data)

        # Set initial status
        await self.redis.set(f"task:{task.id}:status", "pending")

        # Check dependencies
        if task.dependencies:
            # Store dependencies
            deps_key = f"task:dependencies:{task.id}"
            await self.redis.sadd(deps_key, *task.dependencies)

            # Check if dependencies are satisfied
            all_satisfied = await self._check_dependencies_satisfied(task.id)
            if not all_satisfied:
                # Add to pending set for later processing
                await self.redis.sadd("task:pending", task.id)
                logger.info(f"Task {task.id} added to pending (has unsatisfied dependencies)")
                return

        # No dependencies or all satisfied - enqueue immediately
        await self.redis.lpush(queue_key, task.id)
        logger.info(f"Enqueued task {task.id} to {queue_key}")

    async def dequeue(
        self,
        agent_type: str,
        timeout: int = 5
    ) -> Optional[Task]:
        """
        Block until task available for agent type.

        Uses BRPOP for blocking dequeue (wait up to timeout seconds).

        Args:
            agent_type: Type of agent (frontend, backend, testing, etc.)
            timeout: Seconds to wait for task (default: 5)

        Returns:
            Task if available, None if timeout
        """
        queue_key = f"task:queue:{agent_type}"

        try:
            result = await self.redis.brpop(queue_key, timeout=timeout)
        except redis.TimeoutError:
            return None

        if not result:
            return None

        _, task_id_bytes = result
        task_id = task_id_bytes.decode()

        # Fetch task data
        task_data = await self.redis.hgetall(f"task:{task_id}")
        if not task_data:
            logger.error(f"Task {task_id} data not found")
            return None

        # Mark as in-progress
        await self.redis.set(f"task:{task_id}:status", "in_progress")

        task = Task.from_redis(task_data)
        logger.info(f"Dequeued task {task_id} for agent type {agent_type}")
        return task

    async def mark_completed(
        self,
        task_id: str,
        result: TaskResult
    ) -> None:
        """
        Mark task completed and enqueue dependent tasks.

        Args:
            task_id: Task ID
            result: Task execution result
        """
        # Update status
        status = "completed" if result.success else "failed"
        await self.redis.set(f"task:{task_id}:status", status)

        # Store result
        await self.redis.hset(
            f"task:{task_id}",
            mapping={
                "result": json.dumps(result.model_dump()),
                "completed_at": datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Marked task {task_id} as {status}")

        # If successful, enqueue tasks that depended on this one
        if result.success:
            await self._check_and_enqueue_dependents(task_id)

    async def _check_and_enqueue_dependents(self, completed_task_id: str) -> None:
        """
        Find tasks waiting on this dependency and enqueue if all deps met.

        Args:
            completed_task_id: ID of task that just completed
        """
        # Scan pending tasks
        pending_task_ids = await self.redis.smembers("task:pending")

        for task_id_bytes in pending_task_ids:
            task_id = task_id_bytes.decode()
            deps_key = f"task:dependencies:{task_id}"

            # Check if this task depends on the completed task
            dependencies = await self.redis.smembers(deps_key)
            dep_ids = {d.decode() for d in dependencies}

            if completed_task_id not in dep_ids:
                continue

            # Remove this dependency
            await self.redis.srem(deps_key, completed_task_id)

            # Check if all dependencies are now satisfied
            remaining = await self.redis.scard(deps_key)

            if remaining == 0:
                # All dependencies met - move from pending to queue
                await self.redis.srem("task:pending", task_id)

                # Get task data and enqueue
                task_data = await self.redis.hgetall(f"task:{task_id}")
                if task_data:
                    task = Task.from_redis(task_data)
                    queue_key = f"task:queue:{task.agent_type}"
                    await self.redis.lpush(queue_key, task_id)
                    logger.info(f"Enqueued task {task_id} (dependencies satisfied)")

    async def _check_dependencies_satisfied(self, task_id: str) -> bool:
        """
        Check if all dependencies for a task are satisfied.

        Args:
            task_id: Task ID to check

        Returns:
            True if all dependencies are completed
        """
        deps_key = f"task:dependencies:{task_id}"
        dependencies = await self.redis.smembers(deps_key)

        for dep_id_bytes in dependencies:
            dep_id = dep_id_bytes.decode()
            status = await self.redis.get(f"task:{dep_id}:status")

            if not status or status.decode() != "completed":
                return False

        return True

    async def get_task_status(self, task_id: str) -> Optional[str]:
        """
        Get current status of a task.

        Args:
            task_id: Task ID

        Returns:
            Status string or None if not found
        """
        status = await self.redis.get(f"task:{task_id}:status")
        return status.decode() if status else None

    async def get_queue_depth(self, agent_type: str) -> int:
        """
        Get number of tasks in queue for agent type.

        Args:
            agent_type: Agent type

        Returns:
            Number of tasks waiting
        """
        queue_key = f"task:queue:{agent_type}"
        return await self.redis.llen(queue_key)

    async def get_pending_count(self) -> int:
        """
        Get number of tasks waiting on dependencies.

        Returns:
            Number of pending tasks
        """
        return await self.redis.scard("task:pending")

    async def clear_queue(self, agent_type: str) -> None:
        """
        Clear all tasks from a queue.

        Args:
            agent_type: Agent type whose queue to clear
        """
        queue_key = f"task:queue:{agent_type}"
        await self.redis.delete(queue_key)
        logger.info(f"Cleared queue: {queue_key}")
