"""Test script for Worker Agents."""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

# Import gitpython first
import git as gitpython_module

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.git.worktree_manager import WorktreeManager
from backend.llm.bedrock_client import BedrockClient
from backend.locking.redis_lock import RedisLock
from backend.orchestrator.specialized_agents import BackendAgent
from backend.orchestrator.worker_agent import AgentConfig
from backend.queue.redis_queue import Task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_backend_agent():
    """Test BackendAgent with a simple task."""
    print("=" * 70)
    print("Testing BackendAgent")
    print("=" * 70)

    # Create temporary test directory
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        print(f"\n1. Created test project: {project_path}")

        # Initialize git repo
        repo = gitpython_module.Repo.init(project_path)

        # Create initial commit
        readme = project_path / "README.md"
        readme.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        base_branch = repo.active_branch.name
        print(f"   ✓ Initialized git repository (branch: {base_branch})")

        # Initialize components
        print("\n2. Initializing components...")

        bedrock = BedrockClient(
            profile="advanced-bedrock",
            region="eu-west-1"
        )
        print("   ✓ Bedrock client initialized")

        worktree_manager = WorktreeManager(project_path)
        print("   ✓ Worktree manager initialized")

        # Mock Redis queue and lock manager (no Redis required for this test)
        class MockRedisQueue:
            async def mark_completed(self, task_id: str):
                logger.info(f"Task {task_id} marked as completed")

            async def mark_failed(self, task_id: str, error_message: str):
                logger.error(f"Task {task_id} marked as failed: {error_message}")

        class MockRedisLockManager:
            async def acquire(self, resource: str, timeout: int = 300):
                logger.info(f"Acquired lock on {resource}")
                from backend.locking.redis_lock import Lock
                import time
                return Lock(resource=resource, lock_id="mock-lock", acquired_at=time.time())

            async def release(self, lock):
                logger.info(f"Released lock on {lock.resource}")

        mock_queue = MockRedisQueue()
        mock_locks = MockRedisLockManager()

        # Create BackendAgent
        print("\n3. Creating BackendAgent...")
        config = AgentConfig(
            agent_id="test-backend-001",
            agent_type="backend",
            project_path=project_path,
            max_retries=3,
            task_timeout=300
        )

        agent = BackendAgent(
            config=config,
            bedrock_client=bedrock,
            task_queue=mock_queue,
            lock_manager=mock_locks,
            worktree_manager=worktree_manager
        )
        print("   ✓ BackendAgent created")

        # Spawn agent (create worktree)
        print("\n4. Spawning agent worktree...")
        await agent.spawn()
        print(f"   ✓ Worktree created at: {agent.worktree_path}")

        # Create a simple task
        print("\n5. Creating test task...")
        task = Task(
            id="test_task_001",
            title="Create FastAPI Hello World endpoint",
            description="Create a simple FastAPI endpoint that returns Hello World",
            agent_type="backend",
            files_to_create=["backend/api/hello.py"],
            files_to_modify=[],
            dependencies=[],
            estimated_hours=1.0,
            project_id="test_project"
        )
        print(f"   Task ID: {task.id}")
        print(f"   Title: {task.title}")

        # Execute task
        print("\n6. Executing task with Claude Sonnet 4.5...")
        print("   (This will make a real API call to AWS Bedrock)")

        result = await agent._execute_task(task)

        if result.success:
            print(f"\n   ✅ Task executed successfully!")
            print(f"   Commit SHA: {result.commit_sha}")
            print(f"   Files modified: {', '.join(result.files_modified)}")
            print(f"   Execution time: {result.execution_time:.2f}s")

            # Verify files were created
            print("\n7. Verifying created files...")
            for file_path in result.files_modified:
                full_path = agent.worktree_path / file_path
                if full_path.exists():
                    print(f"   ✓ {file_path} exists")
                    with open(full_path, 'r') as f:
                        content = f.read()
                        print(f"     Size: {len(content)} bytes")
                        print(f"     Preview: {content[:200]}...")
                else:
                    print(f"   ✗ {file_path} does not exist")

            # Check git commit
            print("\n8. Verifying git commit...")
            worktree_repo = gitpython_module.Repo(agent.worktree_path)
            latest_commit = worktree_repo.head.commit
            print(f"   ✓ Commit: {latest_commit.hexsha[:8]}")
            print(f"   ✓ Message: {latest_commit.message.splitlines()[0]}")
            print(f"   ✓ Author: {latest_commit.author.name} <{latest_commit.author.email}>")

        else:
            print(f"\n   ❌ Task execution failed:")
            print(f"   Error: {result.error_message}")
            return False

        # Cleanup
        print("\n9. Cleaning up...")
        await agent.cleanup()
        print("   ✓ Agent cleaned up")

        print("\n" + "=" * 70)
        print("✅ BACKEND AGENT TEST PASSED")
        print("=" * 70)
        return True


async def main():
    """Run tests."""
    try:
        success = await test_backend_agent()
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
