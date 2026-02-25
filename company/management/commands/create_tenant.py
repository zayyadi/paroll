from __future__ import annotations

import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from company.models import Company, CompanyMembership


User = get_user_model()


class Command(BaseCommand):
    help = "Create a SaaS tenant (company workspace) and assign an owner user."

    def add_arguments(self, parser):
        parser.add_argument("company_name", type=str, help="Company/workspace name")
        parser.add_argument("owner_email", type=str, help="Owner user email")
        parser.add_argument(
            "--owner-password",
            dest="owner_password",
            type=str,
            default=None,
            help="Owner password. If omitted for a new user, a secure password is generated.",
        )
        parser.add_argument(
            "--owner-first-name",
            dest="owner_first_name",
            type=str,
            default="Workspace",
            help="Owner first name for newly created users.",
        )
        parser.add_argument(
            "--owner-last-name",
            dest="owner_last_name",
            type=str,
            default="Owner",
            help="Owner last name for newly created users.",
        )
        parser.add_argument(
            "--existing-user",
            action="store_true",
            help="Attach an existing user as owner; fail if owner_email is not found.",
        )

    def _generate_password(self, length: int = 20) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @transaction.atomic
    def handle(self, *args, **options):
        company_name = options["company_name"].strip()
        owner_email = options["owner_email"].strip().lower()
        owner_password = options["owner_password"]
        owner_first_name = options["owner_first_name"].strip()
        owner_last_name = options["owner_last_name"].strip()
        existing_user_only = options["existing_user"]

        if not company_name:
            raise CommandError("company_name cannot be empty.")
        if not owner_email:
            raise CommandError("owner_email cannot be empty.")

        company, company_created = Company.objects.get_or_create(name=company_name)

        user = User.objects.filter(email__iexact=owner_email).first()
        generated_password = None
        if user is None:
            if existing_user_only:
                raise CommandError(f"User {owner_email} does not exist.")
            generated_password = owner_password or self._generate_password()
            user = User.objects.create_user(
                email=owner_email,
                password=generated_password,
                first_name=owner_first_name,
                last_name=owner_last_name,
                company=company,
                active_company=company,
            )
            self.stdout.write(self.style.SUCCESS(f"Created owner user: {owner_email}"))
        else:
            update_fields = []
            if user.company_id is None:
                user.company = company
                update_fields.append("company")
            if user.active_company_id is None:
                user.active_company = company
                update_fields.append("active_company")
            if update_fields:
                user.save(update_fields=update_fields)

        membership, membership_created = CompanyMembership.objects.get_or_create(
            user=user,
            company=company,
            defaults={
                "role": CompanyMembership.ROLE_OWNER,
                "is_default": True,
            },
        )
        if not membership_created and membership.role != CompanyMembership.ROLE_OWNER:
            membership.role = CompanyMembership.ROLE_OWNER
            membership.save(update_fields=["role"])

        if membership.is_default:
            CompanyMembership.objects.filter(user=user, is_default=True).exclude(
                pk=membership.pk
            ).update(is_default=False)
        elif not CompanyMembership.objects.filter(user=user, is_default=True).exists():
            membership.is_default = True
            membership.save(update_fields=["is_default"])

        if user.active_company_id != company.id:
            user.active_company = company
            user.save(update_fields=["active_company"])

        workspace_state = "created" if company_created else "existing"
        self.stdout.write(
            self.style.SUCCESS(
                f"Workspace {workspace_state}: {company.name} (slug={company.slug})"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Owner linked: {owner_email} -> {company.name} (role={membership.role})"
            )
        )
        if generated_password:
            self.stdout.write(
                self.style.WARNING(
                    "Generated owner password (store securely): "
                    f"{generated_password}"
                )
            )
