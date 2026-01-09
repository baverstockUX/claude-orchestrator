"""Test script for WorktreeManager."""

import sys
from pathlib import Path

# Import gitpython first before our own git module
import git as gitpython_module

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.git.worktree_manager import WorktreeManager

def test_worktree_manager():
    """Test worktree operations."""
    print("=" * 60)
    print("Testing WorktreeManager")
    print("=" * 60)

    # Initialize manager
    project_root = Path(__file__).parent
    manager = WorktreeManager(project_root)
    print(f"✓ Initialized WorktreeManager at: {project_root}")

    # Create worktree
    print("\n1. Creating worktree for agent-test...")
    worktree_path = manager.create_worktree("agent-test", "master")
    print(f"   ✓ Created worktree: {worktree_path}")

    # Verify worktree exists
    assert worktree_path.exists(), "Worktree directory should exist"
    print(f"   ✓ Worktree directory exists")

    # Create a test file
    print("\n2. Creating test file in worktree...")
    test_file = worktree_path / "test_agent_work.txt"
    test_file.write_text("This is work done by agent-test\n")
    print(f"   ✓ Created: {test_file}")

    # Commit changes
    print("\n3. Committing changes...")
    commit_sha = manager.commit_in_worktree(
        worktree_path,
        "Test commit from agent-test",
        author_name="Test Agent",
        author_email="agent@test.com"
    )
    print(f"   ✓ Committed: {commit_sha[:8]}")

    # List worktrees
    print("\n4. Listing all worktrees...")
    worktrees = manager.list_worktrees()
    print(f"   ✓ Found {len(worktrees)} worktree(s):")
    for wt in worktrees:
        print(f"     - {wt['path']} (branch: {wt.get('branch', 'N/A')})")

    # Get branch name
    branch = manager.get_branch_name(worktree_path)
    print(f"\n5. Branch name: {branch}")
    assert branch == "agent-test", f"Expected 'agent-test', got '{branch}'"
    print(f"   ✓ Correct branch name")

    # Cleanup
    print("\n6. Cleaning up worktree...")
    manager.remove_worktree(worktree_path)
    print(f"   ✓ Removed worktree")

    # Verify cleanup
    assert not worktree_path.exists(), "Worktree directory should be removed"
    print(f"   ✓ Worktree directory removed")

    # Delete branch
    print("\n7. Deleting branch...")
    manager.delete_branch("agent-test", force=True)
    print(f"   ✓ Deleted branch: agent-test")

    print("\n" + "=" * 60)
    print("✅ ALL WORKTREE TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_worktree_manager()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
