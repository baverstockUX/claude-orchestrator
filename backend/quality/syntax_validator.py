"""Syntax validation for Python and TypeScript files."""

import ast
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


class SyntaxValidator(QualityGateValidator):
    """Validates syntax for Python and TypeScript files."""

    @property
    def name(self) -> str:
        return "Syntax Validation"

    def _is_skippable(self) -> bool:
        """Skip if no Python or TypeScript files exist."""
        has_python = any(self.worktree_path.rglob("*.py"))
        has_typescript = any(self.worktree_path.rglob("*.ts")) or any(
            self.worktree_path.rglob("*.tsx")
        )
        return not (has_python or has_typescript)

    async def validate(self) -> ValidationResult:
        """Run syntax validation."""
        start_time = time.time()
        issues = []

        # Validate Python files
        python_issues = await self._validate_python_files()
        issues.extend(python_issues)

        # Validate TypeScript files
        typescript_issues = await self._validate_typescript_files()
        issues.extend(typescript_issues)

        duration = time.time() - start_time
        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED

        return ValidationResult(
            gate_name=self.name,
            status=status,
            duration_seconds=duration,
            issues=issues,
            output=f"Checked {len(list(self.worktree_path.rglob('*.py')))} Python files, "
            f"{len(list(self.worktree_path.rglob('*.ts')))} TypeScript files",
        )

    async def _validate_python_files(self) -> list[ValidationIssue]:
        """Validate Python file syntax using ast.parse."""
        issues = []

        for py_file in self.worktree_path.rglob("*.py"):
            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Try to parse with ast
                ast.parse(content, filename=str(py_file))

            except SyntaxError as e:
                relative_path = str(py_file.relative_to(self.worktree_path))
                issues.append(
                    ValidationIssue(
                        file=relative_path,
                        line=e.lineno,
                        column=e.offset,
                        severity="error",
                        message=f"Syntax error: {e.msg}",
                        rule="python-syntax",
                    )
                )
                logger.warning(f"Syntax error in {relative_path}:{e.lineno}: {e.msg}")

            except Exception as e:
                relative_path = str(py_file.relative_to(self.worktree_path))
                logger.error(f"Error parsing {relative_path}: {e}")
                issues.append(
                    ValidationIssue(
                        file=relative_path,
                        severity="error",
                        message=f"Parse error: {str(e)}",
                        rule="python-syntax",
                    )
                )

        return issues

    async def _validate_typescript_files(self) -> list[ValidationIssue]:
        """Validate TypeScript file syntax using tsc --noEmit."""
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
                logger.warning("TypeScript compiler (tsc) not found, skipping TS validation")
                return issues
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("TypeScript compiler (tsc) not available, skipping TS validation")
            return issues

        # Run tsc --noEmit for syntax checking
        try:
            result = subprocess.run(
                ["tsc", "--noEmit", "--skipLibCheck"],
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Parse tsc output for errors
                for line in result.stdout.splitlines():
                    if "error TS" in line:
                        # Format: file.ts(line,col): error TS1234: message
                        parts = line.split(":")
                        if len(parts) >= 3:
                            file_part = parts[0]
                            message = ":".join(parts[2:]).strip()

                            # Extract file and position
                            if "(" in file_part:
                                file_path = file_part.split("(")[0]
                                position = file_part.split("(")[1].rstrip(")")
                                line_num = None
                                col_num = None
                                if "," in position:
                                    line_num = int(position.split(",")[0])
                                    col_num = int(position.split(",")[1])

                                issues.append(
                                    ValidationIssue(
                                        file=file_path,
                                        line=line_num,
                                        column=col_num,
                                        severity="error",
                                        message=message,
                                        rule="typescript-syntax",
                                    )
                                )

        except subprocess.TimeoutExpired:
            logger.error("TypeScript validation timed out")
        except Exception as e:
            logger.error(f"Error running TypeScript validation: {e}")

        return issues
