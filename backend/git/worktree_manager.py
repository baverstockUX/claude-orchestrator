"""Git worktree manager for agent isolation."""

import logging
from pathlib import Path
from typing import Optional

from git import Repo
import git as gitpython

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Manages git worktrees for agent isolation."""

    def __init__(self, project_root: Path):
        """
        Initialize worktree manager.

        Args:
            project_root: Root directory of the git repository
        """
        self.project_root = Path(project_root)
        self.repo = Repo(project_root)
        self.worktrees_dir = self.project_root / ".worktrees"
        self.worktrees_dir.mkdir(exist_ok=True)

        # Add .worktrees to .gitignore if not already there
        gitignore_path = self.project_root / ".gitignore"
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            if ".worktrees/" not in content:
                with gitignore_path.open("a") as f:
                    f.write("\n# Agent worktrees\n.worktrees/\n")

    def create_worktree(
        self,
        branch_name: str,
        base_branch: str = "main"
    ) -> Path:
        """
        Create git worktree for agent isolation.

        Args:
            branch_name: Name of branch to create (e.g., "agent-1")
            base_branch: Base branch to branch from (default: "main")

        Returns:
            Path to worktree directory

        Raises:
            gitpython.GitCommandError: If worktree creation fails
        """
        worktree_path = self.worktrees_dir / branch_name

        # Remove existing worktree if it exists
        if worktree_path.exists():
            logger.warning(f"Worktree {worktree_path} already exists, removing it")
            self.remove_worktree(worktree_path)

        # Create new worktree
        try:
            self.repo.git.worktree(
                "add",
                "-b", branch_name,
                str(worktree_path),
                base_branch
            )
            logger.info(f"Created worktree: {worktree_path}")
            return worktree_path

        except gitpython.GitCommandError as e:
            logger.error(f"Failed to create worktree {branch_name}: {e}")
            raise

    def commit_in_worktree(
        self,
        worktree_path: Path,
        message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None
    ) -> str:
        """
        Commit changes in agent's worktree.

        Args:
            worktree_path: Path to worktree
            message: Commit message
            author_name: Optional author name (default: from git config)
            author_email: Optional author email (default: from git config)

        Returns:
            Commit SHA

        Raises:
            gitpython.GitCommandError: If commit fails
        """
        worktree_repo = Repo(worktree_path)

        # Stage all changes
        worktree_repo.git.add(".")

        # Check if there are changes to commit
        if not worktree_repo.is_dirty(untracked_files=True):
            logger.warning(f"No changes to commit in {worktree_path}")
            return worktree_repo.head.commit.hexsha

        # Commit with optional author override
        if author_name and author_email:
            worktree_repo.index.commit(
                message,
                author=gitpython.Actor(author_name, author_email)
            )
        else:
            worktree_repo.index.commit(message)

        commit_sha = worktree_repo.head.commit.hexsha
        logger.info(f"Committed changes in {worktree_path}: {commit_sha[:8]}")
        return commit_sha

    def remove_worktree(self, worktree_path: Path, force: bool = True) -> None:
        """
        Cleanup worktree after agent completes.

        Args:
            worktree_path: Path to worktree to remove
            force: Force removal even if worktree is dirty

        Raises:
            gitpython.GitCommandError: If removal fails
        """
        if not worktree_path.exists():
            logger.warning(f"Worktree {worktree_path} does not exist")
            return

        try:
            args = ["remove", str(worktree_path)]
            if force:
                args.append("--force")

            self.repo.git.worktree(*args)
            logger.info(f"Removed worktree: {worktree_path}")

        except gitpython.GitCommandError as e:
            logger.error(f"Failed to remove worktree {worktree_path}: {e}")
            raise

    def list_worktrees(self) -> list[dict[str, str]]:
        """
        List all worktrees.

        Returns:
            List of worktree info dicts with 'path' and 'branch' keys
        """
        output = self.repo.git.worktree("list", "--porcelain")
        worktrees = []
        current_worktree = {}

        for line in output.split("\n"):
            if line.startswith("worktree "):
                current_worktree["path"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                current_worktree["branch"] = line.split(" ", 1)[1]
                worktrees.append(current_worktree)
                current_worktree = {}

        return worktrees

    def get_branch_name(self, worktree_path: Path) -> str:
        """
        Get branch name for a worktree.

        Args:
            worktree_path: Path to worktree

        Returns:
            Branch name
        """
        worktree_repo = Repo(worktree_path)
        return worktree_repo.active_branch.name

    def delete_branch(self, branch_name: str, force: bool = True) -> None:
        """
        Delete a branch.

        Args:
            branch_name: Name of branch to delete
            force: Force deletion even if not fully merged

        Raises:
            gitpython.GitCommandError: If deletion fails
        """
        try:
            if force:
                self.repo.delete_head(branch_name, force=True)
            else:
                self.repo.delete_head(branch_name)

            logger.info(f"Deleted branch: {branch_name}")

        except gitpython.GitCommandError as e:
            logger.error(f"Failed to delete branch {branch_name}: {e}")
            raise
