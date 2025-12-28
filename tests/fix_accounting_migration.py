#!/usr/bin/env python
"""
Script to diagnose and fix accounting module migration issues
"""
import os
import sys
import django
from django.core.management import execute_from_command_line


def main():
    """Main function to diagnose and fix migration issues"""
    print("=" * 60)
    print("Accounting Migration Diagnostic Tool")
    print("=" * 60)

    # Set up Django environment
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    try:
        django.setup()
        print("✓ Django setup successful")
    except Exception as e:
        print(f"✗ Django setup failed: {e}")
        return

    # Check database connection
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return

    # Check if accounting tables exist
    from django.db.migrations.recorder import MigrationRecorder

    recorder = MigrationRecorder(connection)

    try:
        applied_migrations = recorder.applied_migrations()
        accounting_migrations = [m for m in applied_migrations if m[0] == "accounting"]

        if accounting_migrations:
            print(
                f"✓ Found {len(accounting_migrations)} applied accounting migrations:"
            )
            for app, name in accounting_migrations:
                print(f"  - {app}.{name}")
        else:
            print("✗ No accounting migrations found in the database")
    except Exception as e:
        print(f"✗ Error checking applied migrations: {e}")

    # Try to show migration status
    print("\n" + "-" * 60)
    print("Checking migration status...")
    try:
        from django.core.management import call_command

        call_command("showmigrations", "accounting")
    except Exception as e:
        print(f"✗ Error showing migrations: {e}")

    # Try to apply migration
    print("\n" + "-" * 60)
    print("Attempting to apply accounting migration...")
    try:
        call_command("migrate", "accounting", verbosity=2)
        print("✓ Migration applied successfully")
    except Exception as e:
        print(f"✗ Migration failed: {e}")

        # Try to fake apply if there are dependency issues
        print("\nAttempting to fake apply migration...")
        try:
            call_command("migrate", "accounting", "--fake", verbosity=2)
            print("✓ Migration faked successfully")
        except Exception as e2:
            print(f"✗ Fake migration also failed: {e2}")

    print("\n" + "=" * 60)
    print("Diagnostic complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
