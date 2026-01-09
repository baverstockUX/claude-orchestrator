"""Merge strategy for combining agent work."""

import logging
from pathlib import Path
from typing import Optional

import git
from git import Repo
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ConflictInfo(BaseModel):
    """Information about a merge conflict."""
    file_path: str
    conflict_type: str  # "content", "delete/modify", "rename"
    ours: Optional[str] = None
    theirs: Optional[str] = None


class MergeResult(BaseModel):
    """Result of a merge operation."""
    success: bool
    commit_sha: Optional[str] = None
    conflicts: list[ConflictInfo] = []
    error_message: Optional[str] = None


class MergeStrategy:
    """Handles merging agent work back to main branch."""

    def __init__(self, repo_path: Path):
        """
        Initialize merge strategy.

        Args:
            repo_path: Path to git repository
        """
        self.repo = Repo(repo_path)

    def merge_agent_work(
        self,
        agent_branch: str,
        target_branch: str = "main",
        commit_message: Optional[str] = None
    ) -> MergeResult:
        """
        Merge agent's worktree branch back to target branch.

        Strategy:
        1. Checkout target branch
        2. Attempt auto-merge
        3. If conflicts, detect and report them
        4. If successful, return commit SHA

        Args:
            agent_branch: Branch name from agent (e.g., "agent-1")
            target_branch: Target branch to merge into (default: "main")
            commit_message: Optional custom commit message

        Returns:
            MergeResult with success status, commit SHA, or conflicts
        """
        # Ensure we're on target branch
        try:
            self.repo.git.checkout(target_branch)
        except git.GitCommandError as e:
            return MergeResult(
                success=False,
                error_message=f"Failed to checkout {target_branch}: {e}"
            )

        # Attempt merge
        try:
            merge_msg = commit_message or f"Merge agent work from {agent_branch}"
            self.repo.git.merge(agent_branch, "-m", merge_msg)

            # Get merge commit SHA
            commit_sha = self.repo.head.commit.hexsha

            logger.info(f"Successfully merged {agent_branch} into {target_branch}")
            return MergeResult(success=True, commit_sha=commit_sha)

        except git.GitCommandError as e:
            # Merge conflict detected
            logger.warning(f"Merge conflict detected for {agent_branch}: {e}")
            conflicts = self._detect_conflicts()

            return MergeResult(
                success=False,
                conflicts=conflicts,
                error_message=f"Merge conflicts in {len(conflicts)} files"
            )

    def _detect_conflicts(self) -> list[ConflictInfo]:
        """
        Parse git status to identify conflicted files.

        Returns:
            List of ConflictInfo objects
        """
        status = self.repo.git.status("--porcelain")
        conflicts = []

        for line in status.split("\n"):
            if not line:
                continue

            # Parse status codes
            status_code = line[:2]
            file_path = line[3:].strip()

            # UU = both modified (merge conflict)
            # DD = both deleted
            # AU = added by us
            # UA = added by them
            # DU = deleted by us
            # UD = deleted by them
            # AA = both added

            if status_code == "UU":
                conflicts.append(ConflictInfo(
                    file_path=file_path,
                    conflict_type="content"
                ))
            elif status_code in ["DD", "DU", "UD"]:
                conflicts.append(ConflictInfo(
                    file_path=file_path,
                    conflict_type="delete/modify"
                ))
            elif status_code == "AA":
                conflicts.append(ConflictInfo(
                    file_path=file_path,
                    conflict_type="both_added"
                ))

        return conflicts

    def abort_merge(self) -> None:
        """
        Abort an in-progress merge.

        Use this to rollback when merge fails quality gates.
        """
        try:
            self.repo.git.merge("--abort")
            logger.info("Merge aborted successfully")
        except git.GitCommandError as e:
            logger.error(f"Failed to abort merge: {e}")
            raise

    def has_conflicts(self) -> bool:
        """
        Check if repository currently has merge conflicts.

        Returns:
            True if conflicts exist
        """
        status = self.repo.git.status("--porcelain")
        for line in status.split("\n"):
            if line.startswith(("UU", "DD", "AU", "UA", "DU", "UD", "AA")):
                return True
        return False

    def get_merge_base(self, branch1: str, branch2: str) -> str:
        """
        Find common ancestor commit between two branches.

        Args:
            branch1: First branch name
            branch2: Second branch name

        Returns:
            Commit SHA of merge base
        """
        merge_base = self.repo.merge_base(branch1, branch2)
        if not merge_base:
            raise ValueError(f"No merge base found between {branch1} and {branch2}")
        return merge_base[0].hexsha

    def get_diff_files(self, branch1: str, branch2: str) -> list[str]:
        """
        Get list of files that differ between two branches.

        Args:
            branch1: First branch name
            branch2: Second branch name

        Returns:
            List of file paths
        """
        diff = self.repo.git.diff("--name-only", branch1, branch2)
        return [f for f in diff.split("\n") if f]

    def has_uncommitted_changes(self) -> bool:
        """
        Check if repository has uncommitted changes.

        Returns:
            True if there are uncommitted changes
        """
        return self.repo.is_dirty(untracked_files=True)
