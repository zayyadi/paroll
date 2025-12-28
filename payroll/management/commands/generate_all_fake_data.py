from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.utils import timezone
from payroll.models import EmployeeProfile, Department
from accounting.models import Account, FiscalYear, AccountingPeriod

User = get_user_model()


class Command(BaseCommand):
    help = "Generates all fake data for the payroll system (users, employees, payroll, accounting)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--users",
            type=int,
            default=50,
            help="Number of fake users to create (default: 50)",
        )
        parser.add_argument(
            "--employees",
            type=int,
            default=50,
            help="Number of fake employees to create (default: 50)",
        )
        parser.add_argument(
            "--months",
            type=int,
            default=12,
            help="Number of months of payroll data to generate (default: 12)",
        )
        parser.add_argument(
            "--accounts",
            type=int,
            default=30,
            help="Number of fake accounting accounts to create (default: 30)",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip data generation if data already exists",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing data before generating new data",
        )
        parser.add_argument(
            "--include-all",
            action="store_true",
            help="Include all optional data (allowances, deductions, IOU, leave, etc.)",
        )

    def handle(self, *args, **options):
        users_count = options["users"]
        employees_count = options["employees"]
        months_count = options["months"]
        accounts_count = options["accounts"]
        skip_existing = options["skip_existing"]
        clear_existing = options["clear_existing"]
        include_all = options["include_all"]

        self.stdout.write("Starting comprehensive fake data generation...")
        self.stdout.write("=" * 60)

        # Check if we should skip due to existing data
        if skip_existing and self._has_existing_data():
            self.stdout.write(
                self.style.WARNING(
                    "Existing data found and --skip-existing specified. Skipping generation."
                )
            )
            return

        # Clear existing data if requested
        if clear_existing:
            self._clear_existing_data()

        # Step 1: Create users
        self.stdout.write("\n1. Creating fake users...")
        call_command(
            "create_fake_users",
            count=users_count,
            include_admin=True,
        )

        # Step 2: Create departments and employees
        self.stdout.write("\n2. Creating departments and employees...")

        # Check if we have enough users first
        available_users = User.objects.filter(employee_user__isnull=True).count()
        if available_users < employees_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Not enough users available. Found {available_users}, need {employees_count}. "
                    "Creating more users first..."
                )
            )
            # Create additional users if needed
            additional_users_needed = employees_count - available_users
            call_command(
                "create_fake_users",
                count=additional_users_needed,
            )

        call_command(
            "create_fake_employees",
            count=employees_count,
            create_departments=True,
        )

        # Step 3: Create accounting data
        self.stdout.write("\n3. Creating accounting data...")
        call_command(
            "create_fake_accounts",
            count=accounts_count,
            include_fiscal_year=True,
        )

        # Step 4: Create payroll data
        self.stdout.write("\n4. Creating payroll data...")
        call_command(
            "create_fake_payroll",
            count=months_count,
            include_allowances=include_all,
            include_deductions=include_all,
            include_iou=include_all,
            include_leave=include_all,
        )

        # Step 5: Create comprehensive accounting sample data if requested
        if include_all:
            self.stdout.write("\n5. Creating comprehensive accounting sample data...")
            call_command(
                "generate_sample_data",
                accounts=accounts_count,
                journals=50,
                fiscal_year=timezone.now().year,
            )

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Fake data generation complete!"))
        self.stdout.write("\nGenerated data summary:")

        user_count = User.objects.count()
        employee_count = EmployeeProfile.objects.count()
        department_count = Department.objects.count()
        account_count = Account.objects.count()

        self.stdout.write(f"  Users: {user_count}")
        self.stdout.write(f"  Employees: {employee_count}")
        self.stdout.write(f"  Departments: {department_count}")
        self.stdout.write(f"  Accounts: {account_count}")

        if include_all:
            from payroll.models import (
                Payroll,
                PayT,
                Allowance,
                Deduction,
                IOU,
                LeaveRequest,
            )

            payroll_count = Payroll.objects.count()
            pay_period_count = PayT.objects.count()
            allowance_count = Allowance.objects.count()
            deduction_count = Deduction.objects.count()
            iou_count = IOU.objects.count()
            leave_count = LeaveRequest.objects.count()

            self.stdout.write(f"  Payroll records: {payroll_count}")
            self.stdout.write(f"  Pay periods: {pay_period_count}")
            self.stdout.write(f"  Allowances: {allowance_count}")
            self.stdout.write(f"  Deductions: {deduction_count}")
            self.stdout.write(f"  IOUs: {iou_count}")
            self.stdout.write(f"  Leave requests: {leave_count}")

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("You can now login with:")
        self.stdout.write("  Admin: admin@payroll.com / admin123")
        self.stdout.write("  HR: hr@payroll.com / admin123")
        self.stdout.write("  Manager: manager@payroll.com / admin123")
        self.stdout.write("  Accountant: accountant@payroll.com / admin123")
        self.stdout.write("  Regular users: password123")

    def _has_existing_data(self):
        """Check if there's existing data"""
        return (
            User.objects.filter(email__contains="@example.com").exists()
            or EmployeeProfile.objects.exists()
            or Department.objects.exists()
            or Account.objects.exists()
        )

    def _clear_existing_data(self):
        """Clear existing fake data"""
        from django.db import transaction

        self.stdout.write("Clearing existing fake data...")

        with transaction.atomic():
            # Clear in order of dependencies
            from payroll.models import (
                PayVar,
                Payday,
                PayT,
                Allowance,
                Deduction,
                IOU,
                IOUDeduction,
                LeaveRequest,
                LeavePolicy,
                Payroll,
                EmployeeProfile,
            )
            from accounting.models import (
                JournalEntry,
                Journal,
                TransactionNumber,
                AccountingAuditTrail,
                Account,
                AccountingPeriod,
                FiscalYear,
            )

            # Payroll data
            Payday.objects.all().delete()
            PayVar.objects.all().delete()
            PayT.objects.all().delete()
            Allowance.objects.all().delete()
            Deduction.objects.all().delete()
            IOUDeduction.objects.all().delete()
            IOU.objects.all().delete()
            LeaveRequest.objects.all().delete()
            LeavePolicy.objects.all().delete()
            Payroll.objects.all().delete()

            # Employee data
            EmployeeProfile.objects.all().delete()
            Department.objects.all().delete()

            # Accounting data
            JournalEntry.objects.all().delete()
            Journal.objects.all().delete()
            TransactionNumber.objects.all().delete()
            AccountingAuditTrail.objects.all().delete()
            Account.objects.all().delete()
            AccountingPeriod.objects.all().delete()
            FiscalYear.objects.all().delete()

            # Users (except superusers)
            User.objects.filter(is_superuser=False).delete()

        self.stdout.write(self.style.SUCCESS("Existing data cleared"))
