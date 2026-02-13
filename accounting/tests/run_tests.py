#!/usr/bin/env python
"""
Test runner for accounting system tests.
This script provides a convenient way to run different types of tests with appropriate options.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")


def run_command(cmd, description):
    """Run a command and print the description."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd)
    return result.returncode == 0


def run_all_tests(args):
    """Run all accounting tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")
    if args.failfast:
        cmd.append("--failfast")
    if args.debug:
        cmd.append("--debug-mode")

    return run_command(cmd, "All Accounting Tests")


def run_model_tests(args):
    """Run model tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_models"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "Model Tests")


def run_utility_tests(args):
    """Run utility function tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_utils"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "Utility Function Tests")


def run_view_tests(args):
    """Run view tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_views"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "View Tests")


def run_permission_tests(args):
    """Run permission tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_permissions"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "Permission Tests")


def run_signal_tests(args):
    """Run signal handler tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_signal_handlers"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "Signal Handler Tests")


def run_integration_tests(args):
    """Run integration tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_integration"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "Integration Tests")


def run_performance_tests(args):
    """Run performance tests."""
    cmd = ["python", "manage.py", "test", "accounting.tests.test_performance"]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, "Performance Tests")


def run_end_to_end_tests(args):
    """Run end-to-end tests."""
    cmd = ["python", "accounting/tests/end_to_end_test.py"]

    return run_command(cmd, "End-to-End Tests")


def run_coverage_tests(args):
    """Run tests with coverage report."""
    try:
        import coverage
    except ImportError:
        print("Coverage package not installed. Install with: pip install coverage")
        return False

    # Start coverage
    cov = coverage.Coverage(source=["accounting"])
    cov.start()

    # Run all tests
    success = run_all_tests(args)

    # Stop coverage and generate report
    cov.stop()
    cov.save()

    print(f"\n{'='*60}")
    print("Coverage Report")
    print("=" * 60)
    cov.report()

    # Generate HTML report if requested
    if args.html:
        cov.html_report(directory="htmlcov")
        print("HTML coverage report generated in 'htmlcov' directory")

    return success


def run_specific_test(args):
    """Run a specific test class or method."""
    if not args.test:
        print("Error: Please specify a test with --test")
        return False

    cmd = ["python", "manage.py", "test", args.test]
    if args.verbosity:
        cmd.extend(["--verbosity", str(args.verbosity)])
    if args.keepdb:
        cmd.append("--keepdb")

    return run_command(cmd, f"Specific Test: {args.test}")


def main():
    """Main function to parse arguments and run tests."""
    parser = argparse.ArgumentParser(description="Test runner for accounting system")

    # Global options
    parser.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1, 2, 3],
        default=1,
        help="Verbosity level (0=quiet, 1=normal, 2=verbose, 3=very verbose)",
    )
    parser.add_argument(
        "--keepdb", action="store_true", help="Keep the test database after tests"
    )
    parser.add_argument(
        "--failfast", action="store_true", help="Stop running tests on first failure"
    )
    parser.add_argument("--debug", action="store_true", help="Run tests in debug mode")

    # Test type options
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument(
        "--all", action="store_true", help="Run all tests (default)"
    )
    test_group.add_argument("--models", action="store_true", help="Run model tests")
    test_group.add_argument(
        "--utils", action="store_true", help="Run utility function tests"
    )
    test_group.add_argument("--views", action="store_true", help="Run view tests")
    test_group.add_argument(
        "--permissions", action="store_true", help="Run permission tests"
    )
    test_group.add_argument(
        "--signals", action="store_true", help="Run signal handler tests"
    )
    test_group.add_argument(
        "--integration", action="store_true", help="Run integration tests"
    )
    test_group.add_argument(
        "--performance", action="store_true", help="Run performance tests"
    )
    test_group.add_argument("--e2e", action="store_true", help="Run end-to-end tests")
    test_group.add_argument(
        "--coverage", action="store_true", help="Run tests with coverage report"
    )
    test_group.add_argument(
        "--test", type=str, help="Run a specific test class or method"
    )

    # Coverage options
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML coverage report (use with --coverage)",
    )

    args = parser.parse_args()

    # Default to running all tests if no specific test type is specified
    if not any(
        [
            args.models,
            args.utils,
            args.views,
            args.permissions,
            args.signals,
            args.integration,
            args.performance,
            args.e2e,
            args.coverage,
            args.test,
        ]
    ):
        args.all = True

    # Track overall success
    success = True

    # Run the appropriate tests
    if args.all:
        success = run_all_tests(args)
    elif args.models:
        success = run_model_tests(args)
    elif args.utils:
        success = run_utility_tests(args)
    elif args.views:
        success = run_view_tests(args)
    elif args.permissions:
        success = run_permission_tests(args)
    elif args.signals:
        success = run_signal_tests(args)
    elif args.integration:
        success = run_integration_tests(args)
    elif args.performance:
        success = run_performance_tests(args)
    elif args.e2e:
        success = run_end_to_end_tests(args)
    elif args.coverage:
        success = run_coverage_tests(args)
    elif args.test:
        success = run_specific_test(args)

    # Print summary
    print(f"\n{'='*60}")
    if success:
        print("✅ All tests completed successfully!")
    else:
        print("❌ Some tests failed. Check the output above for details.")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
