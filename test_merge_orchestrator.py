"""Test script for MergeOrchestrator."""

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
from backend.orchestrator.merge_orchestrator import MergeOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_successful_merge():
    """Test successful merge with passing quality gates."""
    print("=" * 70)
    print("Test 1: Successful Merge with Quality Gates")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        print(f"\n1. Created test project: {project_path}")

        # Initialize git repo
        repo = gitpython_module.Repo.init(project_path)

        # Create initial commit on main/master
        readme = project_path / "README.md"
        readme.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        base_branch = repo.active_branch.name
        print(f"   ✓ Initialized git repository (branch: {base_branch})")

        # Initialize managers
        worktree_manager = WorktreeManager(project_path)
        orchestrator = MergeOrchestrator(
            project_path=project_path,
            target_branch=base_branch,
            run_quality_gates=True,
        )
        print("   ✓ Initialized managers")

        # Create agent worktree
        print("\n2. Creating agent worktree...")
        agent_branch = "agent-test-001"
        worktree_path = worktree_manager.create_worktree(agent_branch, base_branch)
        print(f"   ✓ Created worktree: {worktree_path}")

        # Agent makes changes (clean Python file)
        print("\n3. Agent creating files...")
        code_file = worktree_path / "hello.py"
        code_file.write_text("""def greet(name: str) -> str:
    '''Greet someone by name.'''
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("World"))
""")
        print("   ✓ Created hello.py (clean code)")

        # Commit agent's work
        commit_sha = worktree_manager.commit_in_worktree(
            worktree_path,
            "Add hello.py with greet function",
            author_name="Agent-test",
            author_email="agent-test@orchestrator.local",
        )
        print(f"   ✓ Committed changes: {commit_sha[:8]}")

        # Merge agent's work
        print("\n4. Merging agent work...")
        result = await orchestrator.merge_agent_work(
            agent_branch=agent_branch,
            worktree_path=worktree_path,
            agent_id="test-001",
            task_id="task_001",
        )

        # Display results
        print("\n5. Merge Results:")
        print(orchestrator.get_merge_summary(result))

        # Verify
        if result.success:
            print("\n✅ TEST 1 PASSED: Successful merge with quality gates")
            # Cleanup worktree
            worktree_manager.remove_worktree(worktree_path)
            return True
        else:
            print("\n❌ TEST 1 FAILED: Expected successful merge")
            return False


async def test_quality_gate_failure():
    """Test merge rejection due to quality gate failures."""
    print("\n\n" + "=" * 70)
    print("Test 2: Merge Rejected - Quality Gates Failed")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        print(f"\n1. Created test project: {project_path}")

        # Initialize git repo
        repo = gitpython_module.Repo.init(project_path)
        readme = project_path / "README.md"
        readme.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        base_branch = repo.active_branch.name
        print(f"   ✓ Initialized git repository (branch: {base_branch})")

        # Initialize managers
        worktree_manager = WorktreeManager(project_path)
        orchestrator = MergeOrchestrator(
            project_path=project_path,
            target_branch=base_branch,
            run_quality_gates=True,
            stop_on_first_failure=True,
        )

        # Create agent worktree
        print("\n2. Creating agent worktree...")
        agent_branch = "agent-test-002"
        worktree_path = worktree_manager.create_worktree(agent_branch, base_branch)
        print(f"   ✓ Created worktree: {worktree_path}")

        # Agent makes changes (BAD code with syntax error)
        print("\n3. Agent creating files with errors...")
        bad_code = worktree_path / "broken.py"
        bad_code.write_text("""def broken_function()
    return "missing colon causes syntax error"

# Security issue
api_key = "sk_test_fakekeyfakekeyfakekeyfake"
eval("1 + 1")  # Security risk
""")
        print("   ✓ Created broken.py (intentional errors)")

        # Commit agent's work
        commit_sha = worktree_manager.commit_in_worktree(
            worktree_path,
            "Add broken.py (for testing quality gates)",
            author_name="Agent-test",
            author_email="agent-test@orchestrator.local",
        )
        print(f"   ✓ Committed changes: {commit_sha[:8]}")

        # Attempt merge (should fail quality gates)
        print("\n4. Attempting merge (expecting failure)...")
        result = await orchestrator.merge_agent_work(
            agent_branch=agent_branch,
            worktree_path=worktree_path,
            agent_id="test-002",
            task_id="task_002",
        )

        # Display results
        print("\n5. Merge Results:")
        print(orchestrator.get_merge_summary(result))

        # Verify
        if not result.success and not result.quality_gates_passed:
            print("\n✅ TEST 2 PASSED: Merge correctly rejected due to quality failures")
            # Cleanup worktree
            worktree_manager.remove_worktree(worktree_path)
            return True
        else:
            print("\n❌ TEST 2 FAILED: Expected merge rejection")
            return False


async def test_merge_with_quality_disabled():
    """Test merge with quality gates disabled (should succeed even with bad code)."""
    print("\n\n" + "=" * 70)
    print("Test 3: Merge with Quality Gates Disabled")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        print(f"\n1. Created test project: {project_path}")

        # Initialize git repo
        repo = gitpython_module.Repo.init(project_path)
        readme = project_path / "README.md"
        readme.write_text("# Test Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        base_branch = repo.active_branch.name
        print(f"   ✓ Initialized git repository (branch: {base_branch})")

        # Initialize managers
        worktree_manager = WorktreeManager(project_path)
        orchestrator = MergeOrchestrator(
            project_path=project_path,
            target_branch=base_branch,
            run_quality_gates=False,  # Disabled
        )

        # Create agent worktree
        print("\n2. Creating agent worktree...")
        agent_branch = "agent-test-003"
        worktree_path = worktree_manager.create_worktree(agent_branch, base_branch)

        # Agent makes changes (any file)
        code_file = worktree_path / "test.py"
        code_file.write_text("print('test')\n")

        # Commit
        commit_sha = worktree_manager.commit_in_worktree(
            worktree_path,
            "Add test.py",
            author_name="Agent-test",
            author_email="agent-test@orchestrator.local",
        )
        print(f"   ✓ Committed changes: {commit_sha[:8]}")

        # Merge (should succeed since quality gates disabled)
        print("\n3. Merging with quality gates disabled...")
        result = await orchestrator.merge_agent_work(
            agent_branch=agent_branch,
            worktree_path=worktree_path,
            agent_id="test-003",
            task_id="task_003",
        )

        # Display results
        print("\n4. Merge Results:")
        print(orchestrator.get_merge_summary(result))

        # Verify
        if result.success:
            print("\n✅ TEST 3 PASSED: Merge succeeded with quality gates disabled")
            worktree_manager.remove_worktree(worktree_path)
            return True
        else:
            print("\n❌ TEST 3 FAILED: Expected successful merge")
            return False


async def main():
    """Run all tests."""
    print("=" * 70)
    print("Testing MergeOrchestrator")
    print("=" * 70)

    try:
        # Test 1: Successful merge
        test1_passed = await test_successful_merge()

        # Test 2: Quality gate failure
        test2_passed = await test_quality_gate_failure()

        # Test 3: Quality gates disabled
        test3_passed = await test_merge_with_quality_disabled()

        # Summary
        print("\n\n" + "=" * 70)
        print("Test Summary")
        print("=" * 70)
        print(f"Test 1 (Successful Merge): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
        print(f"Test 2 (Quality Failure): {'✅ PASSED' if test2_passed else '❌ FAILED'}")
        print(f"Test 3 (Gates Disabled): {'✅ PASSED' if test3_passed else '❌ FAILED'}")

        if all([test1_passed, test2_passed, test3_passed]):
            print("\n" + "=" * 70)
            print("✅ ALL MERGE ORCHESTRATOR TESTS PASSED")
            print("=" * 70)
        else:
            print("\n❌ SOME TESTS FAILED")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
