from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from company.models import Company
from payroll.management.commands.nigeria_fakes import (
    NIGERIAN_DEMO_COMPANY,
    nigerian_first_name,
    nigerian_last_name,
)
import random

User = get_user_model()
class Command(BaseCommand):
    help = "Creates fake users for testing the payroll system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=50,
            help="Number of fake users to create (default: 50)",
        )
        parser.add_argument(
            "--include-admin",
            action="store_true",
            help="Include admin users in the generated data",
        )

    def handle(self, *args, **options):
        count = options["count"]
        include_admin = options["include_admin"]

        company, company_created = Company.objects.get_or_create(
            name=NIGERIAN_DEMO_COMPANY,
        )
        if company_created:
            self.stdout.write(
                self.style.SUCCESS(f"Created company: {NIGERIAN_DEMO_COMPANY}")
            )

        self.stdout.write(f"Creating {count} fake users...")

        created_count = 0
        existing_count = 0

        # Create regular users
        for i in range(count):
            first_name = nigerian_first_name()
            last_name = nigerian_last_name()
            email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@example.ng"

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_staff": False,
                    "is_active": True,
                    "is_manager": (
                        random.choice([True, False]) if i % 10 == 0 else False
                    ),
                },
            )

            if created:
                # Set a simple password for testing
                user.set_password("password123")
                user.save()
                self._assign_company(user, company)
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created user: {email}"))
            else:
                self._assign_company(user, company)
                existing_count += 1
                self.stdout.write(self.style.WARNING(f"User already exists: {email}"))

        # Create admin users if requested
        if include_admin:
            admin_users = [
                ("admin@payroll.com", "Adebayo", "Ogundimu"),
                ("hr@payroll.com", "Chiamaka", "Eze"),
                ("manager@payroll.com", "Musa", "Bello"),
                ("accountant@payroll.com", "Ngozi", "Okonkwo"),
            ]

            for email, first_name, last_name in admin_users:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "first_name": first_name,
                        "last_name": last_name,
                        "is_staff": True,
                        "is_active": True,
                        "is_manager": True,
                    },
                )

                if created:
                    user.set_password("admin123")
                    user.save()
                    self._assign_company(user, company)
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"Created admin user: {email}")
                    )
                else:
                    self._assign_company(user, company)
                    existing_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"Admin user already exists: {email}")
                    )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Summary:"))
        self.stdout.write(
            f"  Total users processed: {count + (len(admin_users) if include_admin else 0)}"
        )
        self.stdout.write(f"  New users created: {created_count}")
        self.stdout.write(f"  Users already existing: {existing_count}")
        self.stdout.write("=" * 50)

        for existing_user in User.objects.all():
            self._assign_company(existing_user, company)

    def _assign_company(self, user, company):
        if user.company_id == company.id and user.active_company_id == company.id:
            return

        user.company = company
        user.active_company = company
        user.save(update_fields=["company", "active_company"])
