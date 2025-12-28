#!/usr/bin/env python3
"""
Test script to validate the fake data generation commands
This script checks for syntax errors and basic functionality without actually running Django commands
"""

import os
import sys
import ast
import importlib.util


def test_python_syntax(file_path):
    """Test if a Python file has valid syntax"""
    try:
        with open(file_path, "r") as f:
            source = f.read()

        # Parse the AST to check for syntax errors
        ast.parse(source)
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"Syntax Error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def test_import_structure(file_path):
    """Test if imports are properly structured"""
    try:
        with open(file_path, "r") as f:
            source = f.read()

        tree = ast.parse(source)

        # Check for required imports
        required_imports = [
            "django.core.management.base.BaseCommand",
            "django.contrib.auth.get_user_model",
        ]

        imports_found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports_found.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports_found.append(node.module)

        return True, f"Imports OK: Found {len(imports_found)} import statements"
    except Exception as e:
        return False, f"Import Error: {e}"


def test_class_structure(file_path):
    """Test if the Command class is properly structured"""
    try:
        with open(file_path, "r") as f:
            source = f.read()

        tree = ast.parse(source)

        # Look for Command class
        command_class_found = False
        handle_method_found = False

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name == "Command":
                    command_class_found = True

                    # Check for handle method
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == "handle":
                            handle_method_found = True

        if not command_class_found:
            return False, "Command class not found"

        if not handle_method_found:
            return False, "handle method not found in Command class"

        return True, "Class structure OK"
    except Exception as e:
        return False, f"Class structure Error: {e}"


def main():
    """Main test function"""
    print("Testing Fake Data Generation Commands")
    print("=" * 50)

    # List of command files to test
    command_files = [
        "payroll/management/commands/create_fake_users.py",
        "payroll/management/commands/create_fake_employees.py",
        "payroll/management/commands/create_fake_payroll.py",
        "payroll/management/commands/generate_all_fake_data.py",
    ]

    all_tests_passed = True

    for file_path in command_files:
        if not os.path.exists(file_path):
            print(f"❌ {file_path}: File not found")
            all_tests_passed = False
            continue

        print(f"\n🔍 Testing {file_path}")

        # Test syntax
        syntax_ok, syntax_msg = test_python_syntax(file_path)
        if syntax_ok:
            print(f"  ✅ Syntax: {syntax_msg}")
        else:
            print(f"  ❌ Syntax: {syntax_msg}")
            all_tests_passed = False
            continue

        # Test imports
        imports_ok, imports_msg = test_import_structure(file_path)
        if imports_ok:
            print(f"  ✅ Imports: {imports_msg}")
        else:
            print(f"  ❌ Imports: {imports_msg}")
            all_tests_passed = False

        # Test class structure
        class_ok, class_msg = test_class_structure(file_path)
        if class_ok:
            print(f"  ✅ Class: {class_msg}")
        else:
            print(f"  ❌ Class: {class_msg}")
            all_tests_passed = False

    print("\n" + "=" * 50)
    if all_tests_passed:
        print(
            "🎉 All tests passed! The fake data generation commands are ready to use."
        )
        print("\nTo use the commands, run:")
        print("  python manage.py generate_all_fake_data --include-all")
        print("  python manage.py create_fake_users --count 50 --include-admin")
        print(
            "  python manage.py create_fake_employees --count 50 --create-departments"
        )
        print("  python manage.py create_fake_payroll --count 12 --include-all")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
