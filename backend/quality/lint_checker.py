"""Linting for Python (ruff) and TypeScript/JavaScript (eslint)."""

import json
import logging
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


class LintChecker(QualityGateValidator):
    """Linting using ruff and eslint."""

    @property
    def name(self) -> str:
        return "Linting"

    def _is_skippable(self) -> bool:
        """Skip if no Python or JS/TS files exist."""
        has_python = any(self.worktree_path.rglob("*.py"))
        has_js_ts = (
            any(self.worktree_path.rglob("*.ts"))
            or any(self.worktree_path.rglob("*.tsx"))
            or any(self.worktree_path.rglob("*.js"))
            or any(self.worktree_path.rglob("*.jsx"))
        )
        return not (has_python or has_js_ts)

    async def validate(self) -> ValidationResult:
        """Run linting."""
        start_time = time.time()
        issues = []

        # Lint Python files with ruff
        python_issues = await self._lint_python()
        issues.extend(python_issues)

        # Lint JS/TS files with eslint
        js_issues = await self._lint_javascript()
        issues.extend(js_issues)

        duration = time.time() - start_time
        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED

        return ValidationResult(
            gate_name=self.name,
            status=status,
            duration_seconds=duration,
            issues=issues,
            output=f"Found {len(issues)} lint issues",
        )

    async def _lint_python(self) -> list[ValidationIssue]:
        """Lint Python files using ruff."""
        issues = []

        # Check if Python files exist
        python_files = list(self.worktree_path.rglob("*.py"))
        if not python_files:
            return issues

        # Check if ruff is available
        try:
            result = subprocess.run(
                ["ruff", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning("ruff not found, skipping Python linting")
                return issues
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("ruff not available, skipping Python linting")
            return issues

        # Run ruff with JSON output
        try:
            result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--output-format=json",
                    str(self.worktree_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse JSON output
            if result.stdout:
                try:
                    ruff_output = json.loads(result.stdout)
                    for issue in ruff_output:
                        # Make path relative to worktree
                        file_path = issue.get("filename", "")
                        try:
                            relative_path = str(Path(file_path).relative_to(self.worktree_path))
                        except ValueError:
                            relative_path = file_path

                        location = issue.get("location", {})
                        issues.append(
                            ValidationIssue(
                                file=relative_path,
                                line=location.get("row"),
                                column=location.get("column"),
                                severity="error" if issue.get("type") == "error" else "warning",
                                message=issue.get("message", ""),
                                rule=issue.get("code", "ruff"),
                            )
                        )
                except json.JSONDecodeError:
                    logger.error("Failed to parse ruff JSON output")

        except subprocess.TimeoutExpired:
            logger.error("ruff timed out")
        except Exception as e:
            logger.error(f"Error running ruff: {e}")

        return issues

    async def _lint_javascript(self) -> list[ValidationIssue]:
        """Lint JavaScript/TypeScript files using eslint."""
        issues = []

        # Check if JS/TS files exist
        js_files = (
            list(self.worktree_path.rglob("*.ts"))
            + list(self.worktree_path.rglob("*.tsx"))
            + list(self.worktree_path.rglob("*.js"))
            + list(self.worktree_path.rglob("*.jsx"))
        )
        if not js_files:
            return issues

        # Check if eslint is available
        try:
            result = subprocess.run(
                ["eslint", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning("eslint not found, skipping JS/TS linting")
                return issues
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("eslint not available, skipping JS/TS linting")
            return issues

        # Run eslint with JSON output
        try:
            result = subprocess.run(
                [
                    "eslint",
                    "--format=json",
                    "--ext",
                    ".js,.jsx,.ts,.tsx",
                    str(self.worktree_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse JSON output
            if result.stdout:
                try:
                    eslint_output = json.loads(result.stdout)
                    for file_result in eslint_output:
                        file_path = file_result.get("filePath", "")
                        try:
                            relative_path = str(Path(file_path).relative_to(self.worktree_path))
                        except ValueError:
                            relative_path = file_path

                        for message in file_result.get("messages", []):
                            # Map eslint severity (1=warning, 2=error)
                            severity = "error" if message.get("severity") == 2 else "warning"

                            issues.append(
                                ValidationIssue(
                                    file=relative_path,
                                    line=message.get("line"),
                                    column=message.get("column"),
                                    severity=severity,
                                    message=message.get("message", ""),
                                    rule=message.get("ruleId", "eslint"),
                                )
                            )
                except json.JSONDecodeError:
                    logger.error("Failed to parse eslint JSON output")

        except subprocess.TimeoutExpired:
            logger.error("eslint timed out")
        except Exception as e:
            logger.error(f"Error running eslint: {e}")

        return issues
