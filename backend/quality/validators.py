"""Base quality gate validator and validation pipeline."""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Validation result status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class ValidationIssue(BaseModel):
    """Individual validation issue."""
    file: str
    line: Optional[int] = None
    column: Optional[int] = None
    severity: str  # error, warning, info
    message: str
    rule: Optional[str] = None


class ValidationResult(BaseModel):
    """Result from a quality gate validation."""
    gate_name: str
    status: ValidationStatus
    duration_seconds: float
    issues: list[ValidationIssue] = []
    output: Optional[str] = None
    error_message: Optional[str] = None


class QualityGateValidator(ABC):
    """Base class for quality gate validators."""

    def __init__(self, worktree_path: Path):
        """
        Initialize validator.

        Args:
            worktree_path: Path to agent's worktree to validate
        """
        self.worktree_path = worktree_path

    @abstractmethod
    async def validate(self) -> ValidationResult:
        """
        Run validation and return result.

        Returns:
            ValidationResult with status and issues
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this quality gate."""
        pass

    def _is_skippable(self) -> bool:
        """
        Check if this validator can be skipped.

        Subclasses can override to skip validation when not applicable.
        For example, skip TypeScript checks if no .ts files exist.
        """
        return False


class QualityGatePipeline:
    """Pipeline for running multiple quality gates in sequence."""

    def __init__(self, worktree_path: Path):
        """
        Initialize pipeline.

        Args:
            worktree_path: Path to agent's worktree to validate
        """
        self.worktree_path = worktree_path
        self.validators: list[QualityGateValidator] = []

    def add_validator(self, validator: QualityGateValidator) -> None:
        """
        Add validator to pipeline.

        Args:
            validator: Validator instance to add
        """
        self.validators.append(validator)

    async def run_all(
        self,
        stop_on_failure: bool = True
    ) -> tuple[bool, list[ValidationResult]]:
        """
        Run all validators in pipeline.

        Args:
            stop_on_failure: Stop pipeline if any validator fails

        Returns:
            Tuple of (all_passed, results_list)
        """
        results = []
        all_passed = True

        for validator in self.validators:
            logger.info(f"Running quality gate: {validator.name}")

            # Skip if validator determines it's not applicable
            if validator._is_skippable():
                result = ValidationResult(
                    gate_name=validator.name,
                    status=ValidationStatus.SKIPPED,
                    duration_seconds=0.0,
                    output="Skipped (not applicable)"
                )
                results.append(result)
                continue

            try:
                result = await validator.validate()
                results.append(result)

                if result.status == ValidationStatus.FAILED:
                    all_passed = False
                    logger.warning(
                        f"Quality gate '{validator.name}' failed with "
                        f"{len(result.issues)} issues"
                    )
                    if stop_on_failure:
                        logger.info("Stopping pipeline due to failure")
                        break
                elif result.status == ValidationStatus.ERROR:
                    all_passed = False
                    logger.error(f"Quality gate '{validator.name}' encountered error")
                    if stop_on_failure:
                        break
                else:
                    logger.info(f"Quality gate '{validator.name}' passed")

            except Exception as e:
                logger.error(f"Quality gate '{validator.name}' raised exception: {e}")
                result = ValidationResult(
                    gate_name=validator.name,
                    status=ValidationStatus.ERROR,
                    duration_seconds=0.0,
                    error_message=str(e)
                )
                results.append(result)
                all_passed = False
                if stop_on_failure:
                    break

        return all_passed, results

    def summary(self, results: list[ValidationResult]) -> str:
        """
        Generate summary of validation results.

        Args:
            results: List of validation results

        Returns:
            Human-readable summary string
        """
        total = len(results)
        passed = sum(1 for r in results if r.status == ValidationStatus.PASSED)
        failed = sum(1 for r in results if r.status == ValidationStatus.FAILED)
        skipped = sum(1 for r in results if r.status == ValidationStatus.SKIPPED)
        errors = sum(1 for r in results if r.status == ValidationStatus.ERROR)
        total_issues = sum(len(r.issues) for r in results)

        summary = f"\nQuality Gate Summary:\n"
        summary += f"  Total gates: {total}\n"
        summary += f"  ✓ Passed: {passed}\n"
        if failed > 0:
            summary += f"  ✗ Failed: {failed}\n"
        if errors > 0:
            summary += f"  ! Errors: {errors}\n"
        if skipped > 0:
            summary += f"  ⊘ Skipped: {skipped}\n"
        if total_issues > 0:
            summary += f"  Issues found: {total_issues}\n"

        return summary
