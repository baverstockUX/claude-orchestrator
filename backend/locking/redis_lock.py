"""Distributed file locking using Redis."""

import asyncio
import logging
import time
import uuid
from typing import Optional

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Lock(BaseModel):
    """Represents an acquired lock."""
    resource: str
    lock_id: str
    acquired_at: float


class LockTimeoutError(Exception):
    """Raised when lock acquisition times out."""
    pass


class RedisLock:
    """Distributed locking mechanism using Redis."""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Redis lock manager.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client

    async def acquire(
        self,
        resource: str,
        timeout: int = 300,
        retry_delay: float = 0.1,
        max_retry_delay: float = 5.0
    ) -> Lock:
        """
        Acquire distributed lock using Redis SET NX EX.

        Retries with exponential backoff if lock held by another agent.

        Args:
            resource: Resource to lock (e.g., "file:src/App.vue")
            timeout: Lock expiry time in seconds (default: 300 = 5 min)
            retry_delay: Initial retry delay in seconds
            max_retry_delay: Maximum retry delay in seconds

        Returns:
            Lock object if successful

        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout
        """
        lock_key = f"lock:{resource}"
        lock_id = str(uuid.uuid4())

        deadline = time.time() + timeout
        current_retry_delay = retry_delay

        while time.time() < deadline:
            # Try to acquire lock with expiry
            acquired = await self.redis.set(
                lock_key,
                lock_id,
                ex=timeout,  # Auto-expire to prevent deadlock
                nx=True  # Only set if not exists
            )

            if acquired:
                logger.debug(f"Acquired lock: {resource} (lock_id: {lock_id})")
                return Lock(
                    resource=resource,
                    lock_id=lock_id,
                    acquired_at=time.time()
                )

            # Lock held by another agent
            # Check who holds the lock
            current_holder = await self.redis.get(lock_key)
            if current_holder:
                logger.debug(
                    f"Lock {resource} held by {current_holder.decode()}, "
                    f"retrying in {current_retry_delay}s"
                )

            # Wait and retry with exponential backoff
            await asyncio.sleep(current_retry_delay)
            current_retry_delay = min(current_retry_delay * 2, max_retry_delay)

        raise LockTimeoutError(
            f"Failed to acquire lock on {resource} within {timeout}s"
        )

    async def release(self, lock: Lock) -> bool:
        """
        Release lock using Lua script to ensure atomicity.

        Only the lock holder can release the lock (verified by lock_id).

        Args:
            lock: Lock object to release

        Returns:
            True if lock was released, False if not held
        """
        # Lua script for atomic release
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        lock_key = f"lock:{lock.resource}"

        # Execute Lua script
        result = await self.redis.eval(
            lua_script,
            1,
            lock_key,
            lock.lock_id
        )

        if result:
            logger.debug(f"Released lock: {lock.resource}")
            return True
        else:
            logger.warning(
                f"Failed to release lock {lock.resource}: "
                f"lock_id mismatch or already expired"
            )
            return False

    async def is_locked(self, resource: str) -> bool:
        """
        Check if resource is currently locked.

        Args:
            resource: Resource to check

        Returns:
            True if locked
        """
        lock_key = f"lock:{resource}"
        exists = await self.redis.exists(lock_key)
        return bool(exists)

    async def get_lock_holder(self, resource: str) -> Optional[str]:
        """
        Get ID of current lock holder.

        Args:
            resource: Resource to check

        Returns:
            Lock ID if locked, None otherwise
        """
        lock_key = f"lock:{resource}"
        lock_id = await self.redis.get(lock_key)
        return lock_id.decode() if lock_id else None

    async def extend_lock(
        self,
        lock: Lock,
        additional_time: int
    ) -> bool:
        """
        Extend lock expiry time.

        Useful for long-running operations.

        Args:
            lock: Lock to extend
            additional_time: Additional seconds to add

        Returns:
            True if extended successfully
        """
        # Lua script for atomic extend
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        lock_key = f"lock:{lock.resource}"

        result = await self.redis.eval(
            lua_script,
            1,
            lock_key,
            lock.lock_id,
            additional_time
        )

        if result:
            logger.debug(f"Extended lock {lock.resource} by {additional_time}s")
            return True
        else:
            logger.warning(f"Failed to extend lock {lock.resource}: lock_id mismatch")
            return False

    async def acquire_multiple(
        self,
        resources: list[str],
        timeout: int = 300
    ) -> list[Lock]:
        """
        Acquire locks on multiple resources atomically.

        If any lock cannot be acquired, all acquired locks are released.

        Args:
            resources: List of resources to lock
            timeout: Lock acquisition timeout

        Returns:
            List of Lock objects

        Raises:
            LockTimeoutError: If any lock cannot be acquired
        """
        locks_acquired: list[Lock] = []

        try:
            for resource in resources:
                lock = await self.acquire(resource, timeout=timeout)
                locks_acquired.append(lock)

            return locks_acquired

        except LockTimeoutError:
            # Failed to acquire all locks - release what we got
            logger.warning(
                f"Failed to acquire all locks, releasing {len(locks_acquired)} locks"
            )
            for lock in locks_acquired:
                await self.release(lock)
            raise

    async def release_multiple(self, locks: list[Lock]) -> int:
        """
        Release multiple locks.

        Args:
            locks: List of locks to release

        Returns:
            Number of locks successfully released
        """
        released_count = 0

        for lock in locks:
            if await self.release(lock):
                released_count += 1

        return released_count


class LockContext:
    """Async context manager for lock acquisition."""

    def __init__(
        self,
        lock_manager: RedisLock,
        resource: str,
        timeout: int = 300
    ):
        """
        Initialize lock context.

        Args:
            lock_manager: RedisLock instance
            resource: Resource to lock
            timeout: Lock timeout in seconds
        """
        self.lock_manager = lock_manager
        self.resource = resource
        self.timeout = timeout
        self.lock: Optional[Lock] = None

    async def __aenter__(self) -> Lock:
        """Acquire lock on entry."""
        self.lock = await self.lock_manager.acquire(
            self.resource,
            timeout=self.timeout
        )
        return self.lock

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock on exit."""
        if self.lock:
            await self.lock_manager.release(self.lock)
