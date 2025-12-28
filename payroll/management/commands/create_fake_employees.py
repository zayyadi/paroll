from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from payroll.models import EmployeeProfile, Department
from faker import Faker
from datetime import datetime, timedelta
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
        departments = []
        if create_departments:
            departments = self._create_departments()
        else:
            departments = list(Department.objects.all())

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
        available_users = User.objects.filter(employee_user__isnull=True)

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
            # Generate employee data
            first_name = user.first_name or fake.first_name()
            last_name = user.last_name or fake.last_name()

            employee_data = {
                "user": user,
                "first_name": first_name,
                "last_name": last_name,
                "email": user.email,
                "department": random.choice(departments),
                "date_of_birth": fake.date_between(start_date="-60y", end_date="-22y"),
                "date_of_employment": fake.date_between(
                    start_date="-5y", end_date="today"
                ),
                "contract_type": random.choice(["P", "T"]),  # Permanent or Temporary
                "phone": f"+234{random.randint(800, 899)}{random.randint(100, 999)}{random.randint(1000, 9999)}",
                "gender": random.choice(["male", "female", "others"]),
                "address": fake.address(),
                "emergency_contact_name": fake.name(),
                "emergency_contact_relationship": random.choice(
                    ["Brother", "Sister", "Friend", "Parent", "Spouse", "Cousin"]
                ),
                "emergency_contact_phone": f"+234{random.randint(800, 899)}{random.randint(100, 999)}{random.randint(1000, 9999)}",
                "next_of_kin_name": fake.name(),
                "next_of_kin_relationship": random.choice(
                    ["Brother", "Sister", "Friend", "Parent", "Spouse", "Cousin"]
                ),
                "next_of_kin_phone": f"+234{random.randint(800, 899)}{random.randint(100, 999)}{random.randint(1000, 9999)}",
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
                "bank": random.choice(
                    [
                        ("Zenith", "Zenith BANK"),
                        ("Access", "Access Bank"),
                        ("GTB", "GT Bank"),
                        ("Jaiz", "JAIZ Bank"),
                        ("FCMB", "FCMB"),
                        ("FBN", "First Bank"),
                        ("Union", "Union Bank"),
                        ("UBA", "UBA"),
                    ]
                )[0],
                "bank_account_name": f"{first_name} {last_name}",
                "pension_rsa": f"RSA-{random.randint(10000000000, 99999999999)}",
                "status": random.choice(["active", "pending"]),
            }

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
                employee_data["bank_account_number"] = (
                    f"1000000000{len(used_bank_accounts)}"[-10:]
                )

            employee, created = EmployeeProfile.objects.get_or_create(
                user=user,
                defaults=employee_data,
            )

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

    def _create_departments(self):
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
                name=name,
                defaults={"description": description},
            )
            departments.append(dept)

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created department: {name}"))

        return departments
