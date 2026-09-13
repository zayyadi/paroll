from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from payroll.models import EmployeeProfile, Department
from company.models import Company
from faker import Faker
from payroll.management.commands.nigeria_fakes import (
    NIGERIAN_DEMO_COMPANY,
    nigerian_address,
    nigerian_bank,
    nigerian_first_name,
    nigerian_hmo_provider,
    nigerian_last_name,
    nigerian_name,
    nigerian_nin,
    nigerian_pension_fund_manager,
    nigerian_pension_rsa,
    nigerian_phone_number,
    nigerian_tin,
)
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
import random

User = get_user_model()
fake = Faker()


class Command(BaseCommand):
    help = "Creates fake employees for testing the payroll system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=50,
            help="Number of fake employees to create (default: 50)",
        )
        parser.add_argument(
            "--create-departments",
            action="store_true",
            help="Create departments if they don't exist",
        )

    def handle(self, *args, **options):
        count = options["count"]
        create_departments = options["create_departments"]

        self.stdout.write(f"Creating {count} fake employees...")

        # Create departments if requested
        company, company_created = Company.objects.get_or_create(
            name=NIGERIAN_DEMO_COMPANY,
        )
        if company_created:
            self.stdout.write(
                self.style.SUCCESS(f"Created company: {NIGERIAN_DEMO_COMPANY}")
            )

        departments = self._create_departments(company)

        if not departments:
            self.stdout.write(
                self.style.WARNING(
                    "No departments found. Use --create-departments to create some."
                )
            )
            return

        created_count = 0
        existing_count = 0

        # Get users without employee profiles
        available_users = User.objects.filter(is_superuser=False, is_staff=False)

        if available_users.count() < count:
            self.stdout.write(
                self.style.WARNING(
                    f"Not enough users available. Found {available_users.count()}, need {count}. "
                    "Run create_fake_users first."
                )
            )
            count = available_users.count()

        users = available_users[:count]

        # Track used bank account numbers to ensure uniqueness
        used_bank_accounts = set(
            EmployeeProfile.objects.exclude(bank_account_number__isnull=True)
            .exclude(bank_account_number="")
            .values_list("bank_account_number", flat=True)
        )

        for user in users:
            self._assign_company(user, company)

            # Generate employee data
            first_name = user.first_name or nigerian_first_name()
            last_name = user.last_name or nigerian_last_name()

            employee_data = {
                "user": user,
                "company": company,
                "first_name": first_name,
                "last_name": last_name,
                "email": user.email,
                "department": random.choice(departments),
                "date_of_birth": fake.date_between(start_date="-60y", end_date="-22y"),
                "date_of_employment": fake.date_between(
                    start_date="-5y", end_date="today"
                ),
                "contract_type": random.choice(["P", "T"]),  # Permanent or Temporary
                "phone": nigerian_phone_number(),
                "gender": random.choice(["male", "female", "others"]),
                "address": nigerian_address(),
                "emergency_contact_name": nigerian_name(),
                "emergency_contact_relationship": random.choice(
                    ["Brother", "Sister", "Friend", "Parent", "Spouse", "Cousin"]
                ),
                "emergency_contact_phone": nigerian_phone_number(),
                "next_of_kin_name": nigerian_name(),
                "next_of_kin_relationship": random.choice(
                    ["Brother", "Sister", "Friend", "Parent", "Spouse", "Cousin"]
                ),
                "next_of_kin_phone": nigerian_phone_number(),
                "job_title": random.choice(
                    [
                        ("C", "Casual"),
                        ("JS", "Junior Staff"),
                        ("OP", "Operator"),
                        ("SU", "Supervisor"),
                        ("M", "Manager"),
                        ("COO", "C.O.O"),
                    ]
                )[0],
                "bank": nigerian_bank()[0],
                "bank_account_name": f"{first_name} {last_name}",
                "nin": nigerian_nin(),
                "tin_no": nigerian_tin(),
                "pension_rsa": nigerian_pension_rsa(),
                "hmo_provider": nigerian_hmo_provider(),
                "pension_fund_manager": nigerian_pension_fund_manager(),
                "rent_paid": Decimal(random.randint(0, 2500000)),
                "probation_start_date": None,
                "probation_end_date": None,
                "probation_status": "confirmed",
                "confirmed_at": timezone.now(),
                "confirmed_by": user,
                "status": "active",
            }

            employment_date = employee_data["date_of_employment"]
            probation_months = random.choice([3, 6])
            employee_data["probation_start_date"] = employment_date
            employee_data["probation_end_date"] = employment_date + timedelta(
                days=30 * probation_months
            )

            # Generate unique bank account number
            max_attempts = 100
            for attempt in range(max_attempts):
                bank_account_number = str(random.randint(1000000000, 9999999999))
                if bank_account_number not in used_bank_accounts:
                    used_bank_accounts.add(bank_account_number)
                    employee_data["bank_account_number"] = bank_account_number
                    break
            else:
                # Fallback if we can't find a unique number
                employee_data[
                    "bank_account_number"
                ] = f"1000000000{len(used_bank_accounts)}"[-10:]

            employee, created = EmployeeProfile.objects.get_or_create(
                user=user,
                defaults=employee_data,
            )

            if not created:
                for field, value in employee_data.items():
                    if field != "user":
                        setattr(employee, field, value)
                employee.save()

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created employee: {first_name} {last_name} - {employee.emp_id}"
                    )
                )
            else:
                existing_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Employee already exists: {first_name} {last_name}"
                    )
                )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Summary:"))
        self.stdout.write(f"  Total employees processed: {count}")
        self.stdout.write(f"  New employees created: {created_count}")
        self.stdout.write(f"  Employees already existing: {existing_count}")
        self.stdout.write("=" * 50)

    def _create_departments(self, company):
        """Create common departments if they don't exist"""
        department_names = [
            ("Engineering", "Software development and IT infrastructure"),
            ("Human Resources", "Personnel management and administration"),
            ("Finance", "Financial planning and accounting"),
            ("Marketing", "Sales and marketing activities"),
            ("Operations", "Day-to-day business operations"),
            ("Customer Service", "Customer support and relations"),
            ("Administration", "General administrative tasks"),
            ("Research & Development", "Product research and development"),
        ]

        departments = []
        for name, description in department_names:
            dept, created = Department.objects.get_or_create(
                company=company,
                name=name,
                defaults={"description": description, "company": company},
            )
            departments.append(dept)

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created department: {name}"))

        return departments

    def _assign_company(self, user, company):
        if user.company_id == company.id and user.active_company_id == company.id:
            return

        user.company = company
        user.active_company = company
        user.save(update_fields=["company", "active_company"])
