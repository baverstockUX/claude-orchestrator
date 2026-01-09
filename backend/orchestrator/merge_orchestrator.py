"""Merge orchestrator for coordinating agent work merges with quality gates."""

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from backend.git.merge_strategy import MergeStrategy, MergeResult as GitMergeResult
from backend.git.worktree_manager import WorktreeManager
from backend.quality import (
    QualityGatePipeline,
    SyntaxValidator,
    TypeChecker,
    LintChecker,
    TestRunner,
    SecurityScanner,
    ValidationResult,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


class MergeResult(BaseModel):
    """Result of merge orchestration."""
    success: bool
    agent_branch: str
    target_branch: str
    commit_sha: Optional[str] = None
    conflict_detected: bool = False
    conflicts: list[str] = []
    quality_gates_passed: bool = False
    quality_results: list[dict] = []  # List of ValidationResult dicts
    error_message: Optional[str] = None
    rollback_performed: bool = False


class MergeOrchestrator:
    """
    Orchestrates merging agent work with conflict detection and quality gates.

    Workflow:
    1. Detect conflicts before attempting merge
    2. Run quality gates on agent's worktree
    3. If all pass, perform merge to target branch
    4. If any fail, rollback and report detailed errors
    """

    def __init__(
        self,
        project_path: Path,
        target_branch: str = "main",
        run_quality_gates: bool = True,
        stop_on_first_failure: bool = True,
    ):
        """
        Initialize merge orchestrator.

        Args:
            project_path: Root path of the git repository
            target_branch: Branch to merge into (default: "main")
            run_quality_gates: Whether to run quality validation (default: True)
            stop_on_first_failure: Stop on first quality gate failure (default: True)
        """
        self.project_path = project_path
        self.target_branch = target_branch
        self.run_quality_gates = run_quality_gates
        self.stop_on_first_failure = stop_on_first_failure

        self.merge_strategy = MergeStrategy(project_path)
        self.worktree_manager = WorktreeManager(project_path)

        logger.info(
            f"Initialized MergeOrchestrator: target={target_branch}, "
            f"quality_gates={run_quality_gates}"
        )

    async def merge_agent_work(
        self,
        agent_branch: str,
        worktree_path: Path,
        agent_id: str,
        task_id: str,
    ) -> MergeResult:
        """
        Merge agent's completed work with full validation pipeline.

        Args:
            agent_branch: Agent's branch name (e.g., "agent-backend-001")
            worktree_path: Path to agent's worktree
            agent_id: Agent identifier
            task_id: Task identifier

        Returns:
            MergeResult with success status and details
        """
        logger.info(
            f"Starting merge orchestration: agent={agent_id}, "
            f"task={task_id}, branch={agent_branch}"
        )

        # Step 1: Detect conflicts before attempting merge
        logger.info("Step 1: Detecting potential merge conflicts...")
        has_conflicts, conflict_files = await self._detect_conflicts(
            agent_branch, worktree_path
        )

        if has_conflicts:
            logger.warning(
                f"Conflicts detected in {len(conflict_files)} files: "
                f"{', '.join(conflict_files[:5])}"
            )
            return MergeResult(
                success=False,
                agent_branch=agent_branch,
                target_branch=self.target_branch,
                conflict_detected=True,
                conflicts=conflict_files,
                quality_gates_passed=False,
                error_message=f"Merge conflicts detected in {len(conflict_files)} files",
            )

        logger.info("No conflicts detected")

        # Step 2: Run quality gates on agent's worktree
        if self.run_quality_gates:
            logger.info("Step 2: Running quality gate validation...")
            quality_passed, quality_results = await self._run_quality_gates(worktree_path)

            if not quality_passed:
                failed_gates = [
                    r.gate_name
                    for r in quality_results
                    if r.status == ValidationStatus.FAILED
                ]
                logger.warning(f"Quality gates failed: {', '.join(failed_gates)}")

                return MergeResult(
                    success=False,
                    agent_branch=agent_branch,
                    target_branch=self.target_branch,
                    conflict_detected=False,
                    quality_gates_passed=False,
                    quality_results=[r.model_dump() for r in quality_results],
                    error_message=f"Quality gates failed: {', '.join(failed_gates)}",
                )

            logger.info("All quality gates passed")
        else:
            logger.info("Step 2: Skipping quality gates (disabled)")
            quality_results = []

        # Step 3: Perform merge to target branch
        logger.info(f"Step 3: Merging {agent_branch} into {self.target_branch}...")
        git_result = self.merge_strategy.merge_agent_work(
            agent_branch=agent_branch,
            target_branch=self.target_branch,
            commit_message=f"Merge agent work: {agent_id} completed {task_id}",
        )

        if not git_result.success:
            # Merge failed - attempt rollback
            logger.error(f"Merge failed: {git_result.conflicts}")
            rollback_success = await self._rollback_merge()

            return MergeResult(
                success=False,
                agent_branch=agent_branch,
                target_branch=self.target_branch,
                conflict_detected=True,
                conflicts=git_result.conflicts,
                quality_gates_passed=True,  # Gates passed but merge failed
                quality_results=[r.model_dump() for r in quality_results],
                error_message=f"Merge operation failed: {len(git_result.conflicts)} conflicts",
                rollback_performed=rollback_success,
            )

        logger.info(f"Merge successful: commit {git_result.commit_sha}")

        return MergeResult(
            success=True,
            agent_branch=agent_branch,
            target_branch=self.target_branch,
            commit_sha=git_result.commit_sha,
            conflict_detected=False,
            quality_gates_passed=True,
            quality_results=[r.model_dump() for r in quality_results],
        )

    async def _detect_conflicts(
        self, agent_branch: str, worktree_path: Path
    ) -> tuple[bool, list[str]]:
        """
        Detect potential merge conflicts before attempting merge.

        Uses git merge-tree to simulate merge without touching working directory.

        Args:
            agent_branch: Agent's branch name
            worktree_path: Path to agent's worktree

        Returns:
            Tuple of (has_conflicts, conflict_file_list)
        """
        try:
            # Get list of changed files in agent branch
            changed_files = self.merge_strategy._get_changed_files(agent_branch)

            # Check if any files were also modified in target branch
            # since agent branched off
            conflicts = []
            for file_path in changed_files:
                if self.merge_strategy._has_diverged(file_path, agent_branch):
                    conflicts.append(file_path)

            return len(conflicts) > 0, conflicts

        except Exception as e:
            logger.error(f"Error detecting conflicts: {e}")
            # Assume conflicts exist if we can't determine
            return True, [f"Error checking conflicts: {str(e)}"]

    async def _run_quality_gates(
        self, worktree_path: Path
    ) -> tuple[bool, list[ValidationResult]]:
        """
        Run quality gate pipeline on agent's worktree.

        Args:
            worktree_path: Path to agent's worktree

        Returns:
            Tuple of (all_passed, results_list)
        """
        pipeline = QualityGatePipeline(worktree_path)

        # Add all validators
        pipeline.add_validator(SyntaxValidator(worktree_path))
        pipeline.add_validator(SecurityScanner(worktree_path))
        pipeline.add_validator(TypeChecker(worktree_path))
        pipeline.add_validator(LintChecker(worktree_path))
        pipeline.add_validator(TestRunner(worktree_path))

        # Run pipeline
        all_passed, results = await pipeline.run_all(
            stop_on_failure=self.stop_on_first_failure
        )

        # Log summary
        logger.info(pipeline.summary(results))

        return all_passed, results

    async def _rollback_merge(self) -> bool:
        """
        Rollback failed merge operation.

        Returns:
            True if rollback successful, False otherwise
        """
        try:
            logger.info("Attempting to rollback merge...")
            # Reset to previous commit
            self.merge_strategy.repo.git.merge("--abort")
            logger.info("Merge rollback successful")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback merge: {e}")
            return False

    async def cleanup_agent_branch(self, agent_branch: str) -> bool:
        """
        Clean up agent branch after successful merge.

        Args:
            agent_branch: Branch name to delete

        Returns:
            True if cleanup successful
        """
        try:
            logger.info(f"Cleaning up agent branch: {agent_branch}")
            self.merge_strategy.repo.git.branch("-d", agent_branch)
            logger.info(f"Deleted branch: {agent_branch}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete branch {agent_branch}: {e}")
            return False

    def get_merge_summary(self, result: MergeResult) -> str:
        """
        Generate human-readable summary of merge result.

        Args:
            result: MergeResult to summarize

        Returns:
            Formatted summary string
        """
        summary = [
            f"\nMerge Summary: {result.agent_branch} → {result.target_branch}",
            f"Status: {'✅ SUCCESS' if result.success else '❌ FAILED'}",
        ]

        if result.commit_sha:
            summary.append(f"Commit: {result.commit_sha[:8]}")

        if result.conflict_detected:
            summary.append(f"\n⚠️  Conflicts Detected ({len(result.conflicts)} files):")
            for conflict in result.conflicts[:10]:
                summary.append(f"  - {conflict}")
            if len(result.conflicts) > 10:
                summary.append(f"  ... and {len(result.conflicts) - 10} more")

        if result.quality_results:
            passed = sum(
                1 for r in result.quality_results if r.get("status") == "passed"
            )
            failed = sum(
                1 for r in result.quality_results if r.get("status") == "failed"
            )
            summary.append(f"\nQuality Gates: {passed} passed, {failed} failed")

            # Show failed gates
            for r in result.quality_results:
                if r.get("status") == "failed":
                    gate_name = r.get("gate_name")
                    issue_count = len(r.get("issues", []))
                    summary.append(f"  ✗ {gate_name}: {issue_count} issues")

        if result.error_message:
            summary.append(f"\nError: {result.error_message}")

        if result.rollback_performed:
            summary.append("\n↩️  Rollback performed")

        return "\n".join(summary)
