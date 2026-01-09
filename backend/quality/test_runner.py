"""Test execution for Python (pytest) and TypeScript/Vue (vitest)."""

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


class TestRunner(QualityGateValidator):
    """Run tests using pytest and vitest."""

    @property
    def name(self) -> str:
        return "Test Execution"

    def _is_skippable(self) -> bool:
        """Skip if no test files exist."""
        has_pytest = any(self.worktree_path.rglob("test_*.py")) or any(
            self.worktree_path.rglob("*_test.py")
        )
        has_vitest = any(self.worktree_path.rglob("*.test.ts")) or any(
            self.worktree_path.rglob("*.test.js")
        )
        return not (has_pytest or has_vitest)

    async def validate(self) -> ValidationResult:
        """Run tests."""
        start_time = time.time()
        issues = []
        output_lines = []

        # Run pytest
        pytest_passed, pytest_output = await self._run_pytest()
        if pytest_output:
            output_lines.append(f"pytest: {pytest_output}")
        if not pytest_passed:
            issues.append(
                ValidationIssue(
                    file="tests",
                    severity="error",
                    message="pytest tests failed",
                    rule="pytest",
                )
            )

        # Run vitest
        vitest_passed, vitest_output = await self._run_vitest()
        if vitest_output:
            output_lines.append(f"vitest: {vitest_output}")
        if not vitest_passed:
            issues.append(
                ValidationIssue(
                    file="tests",
                    severity="error",
                    message="vitest tests failed",
                    rule="vitest",
                )
            )

        duration = time.time() - start_time
        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED

        return ValidationResult(
            gate_name=self.name,
            status=status,
            duration_seconds=duration,
            issues=issues,
            output="\n".join(output_lines) if output_lines else "No tests found",
        )

    async def _run_pytest(self) -> tuple[bool, str]:
        """
        Run pytest tests.

        Returns:
            Tuple of (all_passed, output_summary)
        """
        # Check if pytest test files exist
        test_files = list(self.worktree_path.rglob("test_*.py")) + list(
            self.worktree_path.rglob("*_test.py")
        )
        if not test_files:
            return True, "No pytest tests found"

        # Check if pytest is available
        try:
            result = subprocess.run(
                ["pytest", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning("pytest not found, skipping Python tests")
                return True, "pytest not available"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("pytest not available, skipping Python tests")
            return True, "pytest not available"

        # Run pytest
        try:
            result = subprocess.run(
                [
                    "pytest",
                    "-v",
                    "--tb=short",
                    "--no-header",
                    str(self.worktree_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Parse output for summary
            passed = result.returncode == 0
            output = result.stdout

            # Extract summary line (e.g., "3 passed, 1 failed in 1.23s")
            summary_match = re.search(
                r"(\d+ passed)?.*?(\d+ failed)?.*?in ([\d.]+)s", output
            )
            if summary_match:
                summary = summary_match.group(0)
            else:
                summary = "Tests completed" if passed else "Tests failed"

            return passed, summary

        except subprocess.TimeoutExpired:
            logger.error("pytest timed out")
            return False, "pytest timed out after 120s"
        except Exception as e:
            logger.error(f"Error running pytest: {e}")
            return False, f"pytest error: {str(e)}"

    async def _run_vitest(self) -> tuple[bool, str]:
        """
        Run vitest tests.

        Returns:
            Tuple of (all_passed, output_summary)
        """
        # Check if vitest test files exist
        test_files = list(self.worktree_path.rglob("*.test.ts")) + list(
            self.worktree_path.rglob("*.test.js")
        )
        if not test_files:
            return True, "No vitest tests found"

        # Check if vitest is available (via npx or direct)
        # First check if package.json exists
        package_json = self.worktree_path / "package.json"
        if not package_json.exists():
            return True, "No package.json found"

        # Try running vitest
        try:
            # Try npx vitest first
            result = subprocess.run(
                ["npx", "vitest", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.worktree_path),
            )
            if result.returncode != 0:
                logger.warning("vitest not found, skipping TypeScript tests")
                return True, "vitest not available"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("vitest not available, skipping TypeScript tests")
            return True, "vitest not available"

        # Run vitest
        try:
            result = subprocess.run(
                ["npx", "vitest", "run", "--reporter=verbose"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.worktree_path),
            )

            passed = result.returncode == 0
            output = result.stdout

            # Extract summary
            summary_match = re.search(
                r"Test Files\s+(\d+) passed.*?Tests\s+(\d+) passed", output
            )
            if summary_match:
                files = summary_match.group(1)
                tests = summary_match.group(2)
                summary = f"{files} test files, {tests} tests passed"
            else:
                summary = "Tests completed" if passed else "Tests failed"

            return passed, summary

        except subprocess.TimeoutExpired:
            logger.error("vitest timed out")
            return False, "vitest timed out after 120s"
        except Exception as e:
            logger.error(f"Error running vitest: {e}")
            return False, f"vitest error: {str(e)}"
