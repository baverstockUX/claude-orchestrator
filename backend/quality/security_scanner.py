"""Security scanning for secrets and vulnerabilities."""

import logging
import re
import time
from pathlib import Path

from backend.quality.validators import (
    QualityGateValidator,
    ValidationIssue,
    ValidationResult,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


class SecurityScanner(QualityGateValidator):
    """Security scanning for secrets and common vulnerabilities."""

    # Common secret patterns
    SECRET_PATTERNS = [
        (r"(aws_access_key_id|AWS_ACCESS_KEY_ID)\s*[:=]\s*['\"]?([A-Z0-9]{20})['\"]?", "AWS Access Key"),
        (r"(aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?", "AWS Secret Key"),
        (r"(api[_-]?key|apikey|API[_-]?KEY)\s*[:=]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]", "API Key"),
        (r"(password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{8,})['\"]", "Hardcoded Password"),
        (r"(bearer|token)\s+([a-zA-Z0-9_\-\.]{20,})", "Bearer Token"),
        (r"(sk_live_[a-zA-Z0-9]{24,}|pk_live_[a-zA-Z0-9]{24,})", "Stripe API Key"),
        (r"(ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36})", "GitHub Personal Access Token"),
        (r"(xox[baprs]-[a-zA-Z0-9\-]+)", "Slack Token"),
        (r"(AIza[a-zA-Z0-9_\-]{35})", "Google API Key"),
        (r"(private[_-]?key|privatekey).*BEGIN.*PRIVATE.*KEY", "Private Key"),
    ]

    # Files to exclude from scanning
    EXCLUDED_PATTERNS = [
        r"\.git/",
        r"node_modules/",
        r"__pycache__/",
        r"\.pyc$",
        r"\.log$",
        r"\.md$",  # Often contain example keys in documentation
    ]

    @property
    def name(self) -> str:
        return "Security Scanning"

    async def validate(self) -> ValidationResult:
        """Run security scanning."""
        start_time = time.time()
        issues = []

        # Scan for secrets
        secret_issues = await self._scan_for_secrets()
        issues.extend(secret_issues)

        # Scan for common vulnerabilities
        vuln_issues = await self._scan_for_vulnerabilities()
        issues.extend(vuln_issues)

        duration = time.time() - start_time
        status = ValidationStatus.FAILED if issues else ValidationStatus.PASSED

        return ValidationResult(
            gate_name=self.name,
            status=status,
            duration_seconds=duration,
            issues=issues,
            output=f"Scanned for secrets and vulnerabilities, found {len(issues)} issues",
        )

    def _should_scan_file(self, file_path: Path) -> bool:
        """Check if file should be scanned."""
        file_str = str(file_path)

        # Check exclusions
        for pattern in self.EXCLUDED_PATTERNS:
            if re.search(pattern, file_str):
                return False

        # Only scan text files
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                # Try to read first few bytes
                f.read(512)
            return True
        except (UnicodeDecodeError, IOError):
            return False

    async def _scan_for_secrets(self) -> list[ValidationIssue]:
        """Scan for hardcoded secrets and credentials."""
        issues = []

        # Scan all files
        for file_path in self.worktree_path.rglob("*"):
            if not file_path.is_file():
                continue

            if not self._should_scan_file(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Check each secret pattern
                for pattern, secret_type in self.SECRET_PATTERNS:
                    matches = re.finditer(pattern, content, re.IGNORECASE)

                    for match in matches:
                        # Find line number
                        line_num = content[: match.start()].count("\n") + 1

                        relative_path = str(file_path.relative_to(self.worktree_path))

                        # Check if this looks like a real secret (not example/placeholder)
                        matched_text = match.group(0)
                        if self._is_likely_real_secret(matched_text):
                            issues.append(
                                ValidationIssue(
                                    file=relative_path,
                                    line=line_num,
                                    severity="error",
                                    message=f"Potential {secret_type} detected",
                                    rule="secret-detection",
                                )
                            )
                            logger.warning(
                                f"Potential secret in {relative_path}:{line_num}: {secret_type}"
                            )

            except Exception as e:
                logger.debug(f"Error scanning {file_path}: {e}")

        return issues

    def _is_likely_real_secret(self, text: str) -> bool:
        """
        Check if matched text looks like a real secret vs placeholder.

        Returns False for obvious placeholders like:
        - 'your_api_key_here'
        - 'YOUR_PASSWORD'
        - 'example123'
        """
        text_lower = text.lower()

        # Placeholder indicators
        placeholders = [
            "example",
            "your_",
            "my_",
            "test_",
            "dummy",
            "fake",
            "placeholder",
            "insert",
            "replace",
            "xxx",
            "yyy",
            "zzz",
            "123456",
            "password",  # Ironically, "password" is often a placeholder
        ]

        for placeholder in placeholders:
            if placeholder in text_lower:
                return False

        # All caps (often placeholders in config examples)
        if text.isupper():
            return False

        return True

    async def _scan_for_vulnerabilities(self) -> list[ValidationIssue]:
        """Scan for common security vulnerabilities."""
        issues = []

        # Scan Python files for common issues
        for py_file in self.worktree_path.rglob("*.py"):
            if not self._should_scan_file(py_file):
                continue

            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()

                relative_path = str(py_file.relative_to(self.worktree_path))

                # Check for eval() usage (code injection risk)
                if re.search(r"\beval\s*\(", content):
                    line_num = self._find_line_number(content, r"\beval\s*\(")
                    issues.append(
                        ValidationIssue(
                            file=relative_path,
                            line=line_num,
                            severity="warning",
                            message="Use of eval() detected (code injection risk)",
                            rule="no-eval",
                        )
                    )

                # Check for exec() usage
                if re.search(r"\bexec\s*\(", content):
                    line_num = self._find_line_number(content, r"\bexec\s*\(")
                    issues.append(
                        ValidationIssue(
                            file=relative_path,
                            line=line_num,
                            severity="warning",
                            message="Use of exec() detected (code injection risk)",
                            rule="no-exec",
                        )
                    )

                # Check for pickle usage (deserialization risk)
                if re.search(r"import\s+pickle|from\s+pickle\s+import", content):
                    line_num = self._find_line_number(content, r"pickle")
                    issues.append(
                        ValidationIssue(
                            file=relative_path,
                            line=line_num,
                            severity="info",
                            message="pickle usage detected (potential deserialization risk)",
                            rule="pickle-usage",
                        )
                    )

            except Exception as e:
                logger.debug(f"Error scanning {py_file}: {e}")

        # Scan JS/TS files
        for js_file in list(self.worktree_path.rglob("*.js")) + list(
            self.worktree_path.rglob("*.ts")
        ):
            if not self._should_scan_file(js_file):
                continue

            try:
                with open(js_file, "r", encoding="utf-8") as f:
                    content = f.read()

                relative_path = str(js_file.relative_to(self.worktree_path))

                # Check for eval() usage
                if re.search(r"\beval\s*\(", content):
                    line_num = self._find_line_number(content, r"\beval\s*\(")
                    issues.append(
                        ValidationIssue(
                            file=relative_path,
                            line=line_num,
                            severity="warning",
                            message="Use of eval() detected (code injection risk)",
                            rule="no-eval",
                        )
                    )

                # Check for dangerouslySetInnerHTML (XSS risk)
                if re.search(r"dangerouslySetInnerHTML", content):
                    line_num = self._find_line_number(content, r"dangerouslySetInnerHTML")
                    issues.append(
                        ValidationIssue(
                            file=relative_path,
                            line=line_num,
                            severity="warning",
                            message="dangerouslySetInnerHTML detected (XSS risk)",
                            rule="no-dangerous-html",
                        )
                    )

            except Exception as e:
                logger.debug(f"Error scanning {js_file}: {e}")

        return issues

    def _find_line_number(self, content: str, pattern: str) -> int:
        """Find line number of first occurrence of pattern."""
        match = re.search(pattern, content)
        if match:
            return content[: match.start()].count("\n") + 1
        return 0
