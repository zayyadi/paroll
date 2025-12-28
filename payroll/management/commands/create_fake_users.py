from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from faker import Faker
import random

User = get_user_model()
fake = Faker()


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

        self.stdout.write(f"Creating {count} fake users...")

        created_count = 0
        existing_count = 0

        # Create regular users
        for i in range(count):
            first_name = fake.first_name()
            last_name = fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@example.com"

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
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created user: {email}"))
            else:
                existing_count += 1
                self.stdout.write(self.style.WARNING(f"User already exists: {email}"))

        # Create admin users if requested
        if include_admin:
            admin_emails = [
                "admin@payroll.com",
                "hr@payroll.com",
                "manager@payroll.com",
                "accountant@payroll.com",
            ]

            for email in admin_emails:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "first_name": email.split("@")[0].title(),
                        "last_name": "User",
                        "is_staff": True,
                        "is_active": True,
                        "is_manager": True,
                    },
                )

                if created:
                    user.set_password("admin123")
                    user.save()
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"Created admin user: {email}")
                    )
                else:
                    existing_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"Admin user already exists: {email}")
                    )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Summary:"))
        self.stdout.write(
            f"  Total users processed: {count + (len(admin_emails) if include_admin else 0)}"
        )
        self.stdout.write(f"  New users created: {created_count}")
        self.stdout.write(f"  Users already existing: {existing_count}")
        self.stdout.write("=" * 50)
