"""Type checking for Python (mypy) and TypeScript (tsc)."""

import logging
import re
import subprocess
import time
from pathlib import Path

from backend.quality.validators import (
    QualityGateValidator,
    ValidationIssue,
    ValidationResult,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


class TypeChecker(QualityGateValidator):
    """Type checking using mypy and tsc."""

    @property
    def name(self) -> str:
        return "Type Checking"

    def _is_skippable(self) -> bool:
        """Skip if no Python or TypeScript files exist."""
        has_python = any(self.worktree_path.rglob("*.py"))
        has_typescript = any(self.worktree_path.rglob("*.ts")) or any(
            self.worktree_path.rglob("*.tsx")
        )
        return not (has_python or has_typescript)

    async def validate(self) -> ValidationResult:
        """Run type checking."""
        start_time = time.time()
        issues = []

        # Check Python types with mypy
        python_issues = await self._check_python_types()
        issues.extend(python_issues)

        # Check TypeScript types with tsc
        typescript_issues = await self._check_typescript_types()
        issues.extend(typescript_issues)

        duration = time.time() - start_time
        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED

        return ValidationResult(
            gate_name=self.name,
            status=status,
            duration_seconds=duration,
            issues=issues,
            output=f"Found {len(issues)} type issues",
        )

    async def _check_python_types(self) -> list[ValidationIssue]:
        """Check Python types using mypy."""
        issues = []

        # Check if Python files exist
        python_files = list(self.worktree_path.rglob("*.py"))
        if not python_files:
            return issues

        # Check if mypy is available
        try:
            result = subprocess.run(
                ["mypy", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning("mypy not found, skipping Python type checking")
                return issues
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("mypy not available, skipping Python type checking")
            return issues

        # Run mypy
        try:
            # Run mypy on all Python files
            result = subprocess.run(
                [
                    "mypy",
                    "--no-error-summary",
                    "--show-column-numbers",
                    "--ignore-missing-imports",  # Don't fail on missing stubs
                    str(self.worktree_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Parse mypy output
            # Format: file.py:line:col: error: message
            for line in result.stdout.splitlines():
                if ": error:" in line or ": warning:" in line:
                    match = re.match(r"(.+?):(\d+):(\d+): (error|warning): (.+)", line)
                    if match:
                        file_path = match.group(1)
                        line_num = int(match.group(2))
                        col_num = int(match.group(3))
                        severity = match.group(4)
                        message = match.group(5)

                        # Make path relative to worktree
                        try:
                            relative_path = str(Path(file_path).relative_to(self.worktree_path))
                        except ValueError:
                            relative_path = file_path

                        issues.append(
                            ValidationIssue(
                                file=relative_path,
                                line=line_num,
                                column=col_num,
                                severity=severity,
                                message=message,
                                rule="mypy",
                            )
                        )

        except subprocess.TimeoutExpired:
            logger.error("mypy timed out")
        except Exception as e:
            logger.error(f"Error running mypy: {e}")

        return issues

    async def _check_typescript_types(self) -> list[ValidationIssue]:
        """Check TypeScript types using tsc --noEmit."""
        issues = []

        # Check if TypeScript files exist
        ts_files = list(self.worktree_path.rglob("*.ts")) + list(
            self.worktree_path.rglob("*.tsx")
        )
        if not ts_files:
            return issues

        # Check if tsc is available
        try:
            result = subprocess.run(
                ["tsc", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning("TypeScript compiler (tsc) not found, skipping TS type checking")
                return issues
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("TypeScript compiler (tsc) not available, skipping TS type checking")
            return issues

        # Run tsc --noEmit
        try:
            result = subprocess.run(
                [
                    "tsc",
                    "--noEmit",
                    "--skipLibCheck",
                    "--pretty",
                    "false",  # Disable colors for parsing
                ],
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                # Parse tsc output
                # Format: file.ts(line,col): error TS1234: message
                for line in result.stdout.splitlines():
                    if "error TS" in line or "warning TS" in line:
                        match = re.match(
                            r"(.+?)\((\d+),(\d+)\): (error|warning) TS\d+: (.+)", line
                        )
                        if match:
                            file_path = match.group(1)
                            line_num = int(match.group(2))
                            col_num = int(match.group(3))
                            severity = match.group(4)
                            message = match.group(5)

                            issues.append(
                                ValidationIssue(
                                    file=file_path,
                                    line=line_num,
                                    column=col_num,
                                    severity=severity,
                                    message=message,
                                    rule="tsc",
                                )
                            )

        except subprocess.TimeoutExpired:
            logger.error("tsc timed out")
        except Exception as e:
            logger.error(f"Error running tsc: {e}")

        return issues
