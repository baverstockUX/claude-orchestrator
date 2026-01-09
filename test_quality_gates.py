"""Test script for quality gate validators."""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.quality import (
    QualityGatePipeline,
    SyntaxValidator,
    TypeChecker,
    LintChecker,
    SecurityScanner,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_quality_gates():
    """Test quality gates with sample code."""
    print("=" * 70)
    print("Testing Quality Gates")
    print("=" * 70)

    # Create temporary directory with test code
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        print(f"\n1. Created test worktree: {worktree_path}")

        # Create sample Python file with various issues
        python_file = worktree_path / "sample.py"
        python_file.write_text("""# Sample Python file with issues

def calculate_sum(a, b):
    '''Calculate sum of two numbers.'''
    return a + b

# Syntax error (intentional for testing)
def broken_function()
    return "missing colon"

# Type issues
def add_numbers(x: int, y: int) -> int:
    return x + y + "string"  # Type error

# Security issue (fake key for testing)
api_key = "sk_test_fakekeyfakekeyfakekeyfake"

# eval usage (security risk)
result = eval("1 + 1")
""")
        print("   ✓ Created sample.py with intentional issues")

        # Create sample TypeScript file
        ts_file = worktree_path / "sample.ts"
        ts_file.write_text("""// Sample TypeScript file

function greet(name: string): string {
    return "Hello, " + name;
}

// Syntax error (intentional)
function broken() {
    const x = "missing semicolon"
    return x
// Missing closing brace

// Type error
function add(a: number, b: number): number {
    return a + b + "string";  // Type error
}
""")
        print("   ✓ Created sample.ts with intentional issues")

        # Initialize quality gate pipeline
        print("\n2. Initializing quality gate pipeline...")
        pipeline = QualityGatePipeline(worktree_path)

        # Add validators
        pipeline.add_validator(SyntaxValidator(worktree_path))
        pipeline.add_validator(SecurityScanner(worktree_path))
        print("   ✓ Added validators: Syntax, Security")
        print("   Note: TypeChecker, LintChecker skipped (require mypy/ruff/tsc)")

        # Run pipeline
        print("\n3. Running quality gates...")
        all_passed, results = await pipeline.run_all(stop_on_failure=False)

        # Display results
        print("\n4. Quality Gate Results:")
        print("-" * 70)

        for result in results:
            status_symbol = {
                "passed": "✓",
                "failed": "✗",
                "skipped": "⊘",
                "error": "!",
            }.get(result.status.value, "?")

            print(f"\n{status_symbol} {result.gate_name}: {result.status.value.upper()}")
            print(f"   Duration: {result.duration_seconds:.2f}s")

            if result.output:
                print(f"   Output: {result.output}")

            if result.issues:
                print(f"   Issues found: {len(result.issues)}")
                for issue in result.issues[:5]:  # Show first 5 issues
                    location = f"{issue.file}"
                    if issue.line:
                        location += f":{issue.line}"
                    if issue.column:
                        location += f":{issue.column}"
                    print(f"      - [{issue.severity}] {location}: {issue.message}")
                if len(result.issues) > 5:
                    print(f"      ... and {len(result.issues) - 5} more issues")

            if result.error_message:
                print(f"   Error: {result.error_message}")

        # Print summary
        print("\n" + "=" * 70)
        print(pipeline.summary(results))
        print("=" * 70)

        if all_passed:
            print("✅ ALL QUALITY GATES PASSED")
        else:
            print("❌ SOME QUALITY GATES FAILED (expected for this test)")

        print("\nNote: This test intentionally includes code with errors")
        print("to validate that the quality gates detect them correctly.")

        return True


async def test_clean_code():
    """Test quality gates with clean code (should pass)."""
    print("\n\n" + "=" * 70)
    print("Testing Quality Gates with Clean Code")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir)
        print(f"\n1. Created test worktree: {worktree_path}")

        # Create clean Python file
        python_file = worktree_path / "clean.py"
        python_file.write_text("""# Clean Python file

def calculate_sum(a: int, b: int) -> int:
    '''Calculate sum of two numbers.'''
    return a + b


def greet(name: str) -> str:
    '''Greet someone by name.'''
    return f"Hello, {name}!"
""")
        print("   ✓ Created clean.py")

        # Initialize pipeline
        print("\n2. Initializing quality gate pipeline...")
        pipeline = QualityGatePipeline(worktree_path)
        pipeline.add_validator(SyntaxValidator(worktree_path))
        pipeline.add_validator(SecurityScanner(worktree_path))
        print("   ✓ Added validators")

        # Run pipeline
        print("\n3. Running quality gates...")
        all_passed, results = await pipeline.run_all(stop_on_failure=True)

        # Display results
        print("\n4. Results:")
        for result in results:
            status_symbol = "✓" if result.status.value == "passed" else "✗"
            print(f"{status_symbol} {result.gate_name}: {result.status.value.upper()}")

        print("\n" + pipeline.summary(results))

        if all_passed:
            print("✅ ALL QUALITY GATES PASSED")
            return True
        else:
            print("❌ UNEXPECTED FAILURE")
            return False


async def main():
    """Run all tests."""
    try:
        # Test with intentionally broken code
        await test_quality_gates()

        # Test with clean code
        success = await test_clean_code()

        if success:
            print("\n" + "=" * 70)
            print("✅ QUALITY GATE TESTS COMPLETED")
            print("=" * 70)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
