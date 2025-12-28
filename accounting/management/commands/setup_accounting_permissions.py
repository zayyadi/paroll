from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounting.permissions import (
    setup_accounting_groups_and_permissions,
    assign_user_to_auditor_role,
    assign_user_to_accountant_role,
    assign_user_to_payroll_processor_role,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Set up accounting roles and permissions for auditor, accountant, and payroll processor roles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--setup-all",
            action="store_true",
            help="Set up all accounting groups and permissions",
        )

        parser.add_argument(
            "--assign-auditor",
            type=str,
            help="Assign a user (by email) to the auditor role",
        )

        parser.add_argument(
            "--assign-accountant",
            type=str,
            help="Assign a user (by email) to the accountant role",
        )

        parser.add_argument(
            "--assign-payroll-processor",
            type=str,
            help="Assign a user (by email) to the payroll processor role",
        )

    def handle(self, *args, **options):
        # Set up all groups and permissions
        if options["setup_all"]:
            self.stdout.write("Setting up accounting groups and permissions...")
            setup_accounting_groups_and_permissions()
            self.stdout.write(
                self.style.SUCCESS(
                    "Accounting groups and permissions set up successfully."
                )
            )

        # Assign user to auditor role
        if options["assign_auditor"]:
            email = options["assign_auditor"]
            try:
                user = User.objects.get(email=email)
                assign_user_to_auditor_role(user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"User {email} assigned to Auditor role successfully."
                    )
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with email {email} does not exist.")
                )

        # Assign user to accountant role
        if options["assign_accountant"]:
            email = options["assign_accountant"]
            try:
                user = User.objects.get(email=email)
                assign_user_to_accountant_role(user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"User {email} assigned to Accountant role successfully."
                    )
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with email {email} does not exist.")
                )

        # Assign user to payroll processor role
        if options["assign_payroll_processor"]:
            email = options["assign_payroll_processor"]
            try:
                user = User.objects.get(email=email)
                assign_user_to_payroll_processor_role(user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"User {email} assigned to Payroll Processor role successfully."
                    )
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with email {email} does not exist.")
                )

        # If no arguments provided, show help
        if not any(options.values()):
            self.print_help("setup_accounting_permissions", *args)
