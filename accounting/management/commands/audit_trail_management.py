from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

# from django.db import transaction
# from django.utils import timezone
from django.utils.dateparse import parse_date

# from datetime import datetime, timedelta
# import json

from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.middleware import set_audit_user, set_audit_metadata

# from accounting.utils import log_accounting_activity

User = get_user_model()


class Command(BaseCommand):
    help = "Manage audit trail: backfill, verify integrity, and cleanup"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["backfill", "verify", "cleanup", "stats"],
            help="Action to perform",
        )

        parser.add_argument(
            "--model",
            choices=["all", "account", "fiscalyear", "period", "journal", "entry"],
            default="all",
            help="Model to process (default: all)",
        )

        parser.add_argument(
            "--start-date", type=str, help="Start date for backfill (YYYY-MM-DD format)"
        )

        parser.add_argument(
            "--end-date", type=str, help="End date for backfill (YYYY-MM-DD format)"
        )

        parser.add_argument(
            "--user-id",
            type=int,
            help="User ID to assign for backfilled entries (default: system user)",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform a dry run without making changes",
        )

        parser.add_argument("--verbose", action="store_true", help="Verbose output")

    def handle(self, *args, **options):
        action = options["action"]
        model_type = options["model"]
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        # Set up audit context for management commands
        self.setup_audit_context(options.get("user_id"))

        if action == "backfill":
            self.backfill_audit_trail(model_type, options, dry_run, verbose)
        elif action == "verify":
            self.verify_audit_trail_integrity(model_type, verbose)
        elif action == "cleanup":
            self.cleanup_orphaned_audit_entries(dry_run, verbose)
        elif action == "stats":
            self.show_audit_statistics(verbose)
        else:
            raise CommandError(f"Unknown action: {action}")

    def setup_audit_context(self, user_id=None):
        """Set up audit context for management commands."""
        try:
            if user_id:
                user = User.objects.get(pk=user_id)
            else:
                # Try to get or create a system user
                user, created = User.objects.get_or_create(
                    username="system",
                    defaults={
                        "email": "system@example.com",
                        "first_name": "System",
                        "last_name": "User",
                        "is_staff": True,
                        "is_superuser": True,
                    },
                )

            set_audit_user(user)
            set_audit_metadata(
                ip_address="127.0.0.1", user_agent="Django Management Command"
            )

            self.user = user
            self.stdout.write(f"Using audit context: {user}")

        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found")
        except Exception as e:
            raise CommandError(f"Failed to set up audit context: {e}")

    def backfill_audit_trail(self, model_type, options, dry_run, verbose):
        """Backfill audit trail entries for existing data."""
        start_date = options.get("start_date")
        end_date = options.get("end_date")

        self.stdout.write(f"Starting audit trail backfill for {model_type}")

        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")

        if model_type in ["all", "account"]:
            self.backfill_accounts(start_date, end_date, dry_run, verbose)

        if model_type in ["all", "fiscalyear"]:
            self.backfill_fiscal_years(start_date, end_date, dry_run, verbose)

        if model_type in ["all", "period"]:
            self.backfill_periods(start_date, end_date, dry_run, verbose)

        if model_type in ["all", "journal"]:
            self.backfill_journals(start_date, end_date, dry_run, verbose)

        if model_type in ["all", "entry"]:
            self.backfill_journal_entries(start_date, end_date, dry_run, verbose)

    def backfill_accounts(self, start_date, end_date, dry_run, verbose):
        """Backfill audit trail for Account objects."""
        queryset = Account.objects.all()

        if start_date:
            start = parse_date(start_date)
            queryset = queryset.filter(created_at__gte=start)

        if end_date:
            end = parse_date(end_date)
            queryset = queryset.filter(created_at__lte=end)

        count = 0
        for account in queryset:
            # Check if audit entry already exists
            existing = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(Account),
                object_id=account.pk,
                action=AccountingAuditTrail.ActionType.CREATE,
            ).exists()

            if not existing:
                if verbose:
                    self.stdout.write(
                        f"Would create audit entry for account: {account}"
                    )

                if not dry_run:
                    AccountingAuditTrail.objects.create(
                        user=self.user,
                        action=AccountingAuditTrail.ActionType.CREATE,
                        content_type=ContentType.objects.get_for_model(Account),
                        object_id=account.pk,
                        changes={
                            "name": account.name,
                            "account_number": account.account_number,
                            "type": account.type,
                            "description": account.description or "",
                        },
                        reason="Backfilled audit entry",
                        ip_address="127.0.0.1",
                        user_agent="Django Management Command",
                    )

                count += 1

        self.stdout.write(
            f"{'Would create' if dry_run else 'Created'} {count} account audit entries"
        )

    def backfill_fiscal_years(self, start_date, end_date, dry_run, verbose):
        """Backfill audit trail for FiscalYear objects."""
        queryset = FiscalYear.objects.all()

        if start_date:
            start = parse_date(start_date)
            queryset = queryset.filter(created_at__gte=start)

        if end_date:
            end = parse_date(end_date)
            queryset = queryset.filter(created_at__lte=end)

        count = 0
        for fiscal_year in queryset:
            # Check if audit entry already exists
            existing = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(FiscalYear),
                object_id=fiscal_year.pk,
                action=AccountingAuditTrail.ActionType.CREATE,
            ).exists()

            if not existing:
                if verbose:
                    self.stdout.write(
                        f"Would create audit entry for fiscal year: {fiscal_year}"
                    )

                if not dry_run:
                    AccountingAuditTrail.objects.create(
                        user=self.user,
                        action=AccountingAuditTrail.ActionType.CREATE,
                        content_type=ContentType.objects.get_for_model(FiscalYear),
                        object_id=fiscal_year.pk,
                        changes={
                            "year": fiscal_year.year,
                            "name": fiscal_year.name,
                            "start_date": str(fiscal_year.start_date),
                            "end_date": str(fiscal_year.end_date),
                        },
                        reason="Backfilled audit entry",
                        ip_address="127.0.0.1",
                        user_agent="Django Management Command",
                    )

                count += 1

            # Also check for closure entries
            if fiscal_year.is_closed and not dry_run:
                closure_existing = AccountingAuditTrail.objects.filter(
                    content_type=ContentType.objects.get_for_model(FiscalYear),
                    object_id=fiscal_year.pk,
                    action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
                ).exists()

                if not closure_existing:
                    if verbose:
                        self.stdout.write(
                            f"Would create closure audit entry for fiscal year: {fiscal_year}"
                        )

                    if not dry_run:
                        AccountingAuditTrail.objects.create(
                            user=self.user,
                            action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
                            content_type=ContentType.objects.get_for_model(FiscalYear),
                            object_id=fiscal_year.pk,
                            changes={"is_closed": True},
                            reason=f"Backfilled closure entry for {fiscal_year.name}",
                            ip_address="127.0.0.1",
                            user_agent="Django Management Command",
                        )

        self.stdout.write(
            f"{'Would create' if dry_run else 'Created'} {count} fiscal year audit entries"
        )

    def backfill_periods(self, start_date, end_date, dry_run, verbose):
        """Backfill audit trail for AccountingPeriod objects."""
        queryset = AccountingPeriod.objects.all()

        if start_date:
            start = parse_date(start_date)
            queryset = queryset.filter(created_at__gte=start)

        if end_date:
            end = parse_date(end_date)
            queryset = queryset.filter(created_at__lte=end)

        count = 0
        for period in queryset:
            # Check if audit entry already exists
            existing = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(AccountingPeriod),
                object_id=period.pk,
                action=AccountingAuditTrail.ActionType.CREATE,
            ).exists()

            if not existing:
                if verbose:
                    self.stdout.write(f"Would create audit entry for period: {period}")

                if not dry_run:
                    AccountingAuditTrail.objects.create(
                        user=self.user,
                        action=AccountingAuditTrail.ActionType.CREATE,
                        content_type=ContentType.objects.get_for_model(
                            AccountingPeriod
                        ),
                        object_id=period.pk,
                        changes={
                            "period_number": period.period_number,
                            "name": period.name,
                            "start_date": str(period.start_date),
                            "end_date": str(period.end_date),
                            "fiscal_year": period.fiscal_year.name,
                        },
                        reason="Backfilled audit entry",
                        ip_address="127.0.0.1",
                        user_agent="Django Management Command",
                    )

                count += 1

            # Also check for closure entries
            if period.is_closed and not dry_run:
                closure_existing = AccountingAuditTrail.objects.filter(
                    content_type=ContentType.objects.get_for_model(AccountingPeriod),
                    object_id=period.pk,
                    action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
                ).exists()

                if not closure_existing:
                    if verbose:
                        self.stdout.write(
                            f"Would create closure audit entry for period: {period}"
                        )

                    if not dry_run:
                        AccountingAuditTrail.objects.create(
                            user=self.user,
                            action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
                            content_type=ContentType.objects.get_for_model(
                                AccountingPeriod
                            ),
                            object_id=period.pk,
                            changes={"is_closed": True},
                            reason=f"Backfilled closure entry for {period.name}",
                            ip_address="127.0.0.1",
                            user_agent="Django Management Command",
                        )

        self.stdout.write(
            f"{'Would create' if dry_run else 'Created'} {count} period audit entries"
        )

    def backfill_journals(self, start_date, end_date, dry_run, verbose):
        """Backfill audit trail for Journal objects."""
        queryset = Journal.objects.all()

        if start_date:
            start = parse_date(start_date)
            queryset = queryset.filter(created_at__gte=start)

        if end_date:
            end = parse_date(end_date)
            queryset = queryset.filter(created_at__lte=end)

        count = 0
        for journal in queryset:
            # Check if audit entry already exists
            existing = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(Journal),
                object_id=journal.pk,
                action=AccountingAuditTrail.ActionType.CREATE,
            ).exists()

            if not existing:
                if verbose:
                    self.stdout.write(
                        f"Would create audit entry for journal: {journal.transaction_number}"
                    )

                if not dry_run:
                    AccountingAuditTrail.objects.create(
                        user=journal.created_by or self.user,
                        action=AccountingAuditTrail.ActionType.CREATE,
                        content_type=ContentType.objects.get_for_model(Journal),
                        object_id=journal.pk,
                        changes={
                            "transaction_number": journal.transaction_number,
                            "description": journal.description,
                            "date": str(journal.date),
                            "status": journal.status,
                        },
                        reason="Backfilled audit entry",
                        ip_address="127.0.0.1",
                        user_agent="Django Management Command",
                    )

                count += 1

        self.stdout.write(
            f"{'Would create' if dry_run else 'Created'} {count} journal audit entries"
        )

    def backfill_journal_entries(self, start_date, end_date, dry_run, verbose):
        """Backfill audit trail for JournalEntry objects."""
        queryset = JournalEntry.objects.all()

        if start_date:
            start = parse_date(start_date)
            queryset = queryset.filter(created_at__gte=start)

        if end_date:
            end = parse_date(end_date)
            queryset = queryset.filter(created_at__lte=end)

        count = 0
        for entry in queryset:
            # Check if audit entry already exists
            existing = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(JournalEntry),
                object_id=entry.pk,
                action=AccountingAuditTrail.ActionType.CREATE,
            ).exists()

            if not existing:
                if verbose:
                    self.stdout.write(
                        f"Would create audit entry for journal entry: {entry}"
                    )

                if not dry_run:
                    AccountingAuditTrail.objects.create(
                        user=entry.created_by or self.user,
                        action=AccountingAuditTrail.ActionType.CREATE,
                        content_type=ContentType.objects.get_for_model(JournalEntry),
                        object_id=entry.pk,
                        changes={
                            "journal": entry.journal.transaction_number,
                            "account": entry.account.name,
                            "entry_type": entry.entry_type,
                            "amount": str(entry.amount),
                            "memo": entry.memo or "",
                        },
                        reason="Backfilled audit entry",
                        ip_address="127.0.0.1",
                        user_agent="Django Management Command",
                    )

                count += 1

        self.stdout.write(
            f"{'Would create' if dry_run else 'Created'} {count} journal entry audit entries"
        )

    def verify_audit_trail_integrity(self, model_type, verbose):
        """Verify audit trail integrity for specified models."""
        self.stdout.write(f"Verifying audit trail integrity for {model_type}")

        issues = []

        if model_type in ["all", "account"]:
            issues.extend(self.verify_account_integrity())

        if model_type in ["all", "fiscalyear"]:
            issues.extend(self.verify_fiscal_year_integrity())

        if model_type in ["all", "period"]:
            issues.extend(self.verify_period_integrity())

        if model_type in ["all", "journal"]:
            issues.extend(self.verify_journal_integrity())

        if model_type in ["all", "entry"]:
            issues.extend(self.verify_journal_entry_integrity())

        if issues:
            self.stdout.write(
                self.style.ERROR(f"Found {len(issues)} integrity issues:")
            )
            for issue in issues:
                self.stdout.write(f"  - {issue}")
        else:
            self.stdout.write(self.style.SUCCESS("No integrity issues found"))

    def verify_account_integrity(self):
        """Verify Account audit trail integrity."""
        issues = []
        accounts = Account.objects.all()

        for account in accounts:
            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(Account),
                object_id=account.pk,
            )

            if not audit_entries.exists():
                issues.append(f"Account {account.name} has no audit entries")

        return issues

    def verify_fiscal_year_integrity(self):
        """Verify FiscalYear audit trail integrity."""
        issues = []
        fiscal_years = FiscalYear.objects.all()

        for fiscal_year in fiscal_years:
            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(FiscalYear),
                object_id=fiscal_year.pk,
            )

            if not audit_entries.exists():
                issues.append(f"Fiscal year {fiscal_year.name} has no audit entries")

            # Check for closure consistency
            if fiscal_year.is_closed:
                closure_entries = audit_entries.filter(
                    action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR
                )
                if not closure_entries.exists():
                    issues.append(
                        f"Fiscal year {fiscal_year.name} is closed but has no closure audit entry"
                    )

        return issues

    def verify_period_integrity(self):
        """Verify AccountingPeriod audit trail integrity."""
        issues = []
        periods = AccountingPeriod.objects.all()

        for period in periods:
            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(AccountingPeriod),
                object_id=period.pk,
            )

            if not audit_entries.exists():
                issues.append(f"Period {period.name} has no audit entries")

            # Check for closure consistency
            if period.is_closed:
                closure_entries = audit_entries.filter(
                    action=AccountingAuditTrail.ActionType.CLOSE_PERIOD
                )
                if not closure_entries.exists():
                    issues.append(
                        f"Period {period.name} is closed but has no closure audit entry"
                    )

        return issues

    def verify_journal_integrity(self):
        """Verify Journal audit trail integrity."""
        issues = []
        journals = Journal.objects.all()

        for journal in journals:
            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(Journal),
                object_id=journal.pk,
            )

            if not audit_entries.exists():
                issues.append(
                    f"Journal {journal.transaction_number} has no audit entries"
                )

            # Check for status consistency
            if journal.status == Journal.JournalStatus.APPROVED:
                approval_entries = audit_entries.filter(
                    action=AccountingAuditTrail.ActionType.APPROVE
                )
                if not approval_entries.exists():
                    issues.append(
                        f"Journal {journal.transaction_number} is approved but has no approval audit entry"
                    )

            if journal.status == Journal.JournalStatus.POSTED:
                posting_entries = audit_entries.filter(
                    action=AccountingAuditTrail.ActionType.POST
                )
                if not posting_entries.exists():
                    issues.append(
                        f"Journal {journal.transaction_number} is posted but has no posting audit entry"
                    )

            if journal.status == Journal.JournalStatus.REVERSED:
                reversal_entries = audit_entries.filter(
                    action=AccountingAuditTrail.ActionType.REVERSE
                )
                if not reversal_entries.exists():
                    issues.append(
                        f"Journal {journal.transaction_number} is reversed but has no reversal audit entry"
                    )

        return issues

    def verify_journal_entry_integrity(self):
        """Verify JournalEntry audit trail integrity."""
        issues = []
        entries = JournalEntry.objects.all()

        for entry in entries:
            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=ContentType.objects.get_for_model(JournalEntry),
                object_id=entry.pk,
            )

            if not audit_entries.exists():
                issues.append(f"Journal entry {entry.id} has no audit entries")

        return issues

    def cleanup_orphaned_audit_entries(self, dry_run, verbose):
        """Clean up orphaned audit trail entries."""
        self.stdout.write("Cleaning up orphaned audit trail entries")

        # Find audit entries that reference non-existent objects
        orphaned_count = 0

        for content_type in ContentType.objects.all():
            model_class = content_type.model_class()
            if not model_class:
                continue

            # Get audit entries for this content type
            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=content_type
            )

            for audit_entry in audit_entries:
                try:
                    # Try to get the referenced object
                    model_class.objects.get(pk=audit_entry.object_id)
                except model_class.DoesNotExist:
                    if verbose:
                        self.stdout.write(f"Found orphaned audit entry: {audit_entry}")

                    if not dry_run:
                        audit_entry.delete()

                    orphaned_count += 1

        self.stdout.write(
            f"{'Would delete' if dry_run else 'Deleted'} {orphaned_count} orphaned audit entries"
        )

    def show_audit_statistics(self, verbose):
        """Show audit trail statistics."""
        self.stdout.write("Audit Trail Statistics")
        self.stdout.write("=" * 50)

        # Total audit entries
        total_entries = AccountingAuditTrail.objects.count()
        self.stdout.write(f"Total audit entries: {total_entries}")

        # Entries by action type
        self.stdout.write("\nEntries by action type:")
        for action_type, label in AccountingAuditTrail.ActionType.choices:
            count = AccountingAuditTrail.objects.filter(action=action_type).count()
            self.stdout.write(f"  {label}: {count}")

        # Entries by content type
        self.stdout.write("\nEntries by content type:")
        for content_type in ContentType.objects.all():
            count = AccountingAuditTrail.objects.filter(
                content_type=content_type
            ).count()
            if count > 0:
                self.stdout.write(f"  {content_type.name}: {count}")

        # Recent activity
        self.stdout.write("\nRecent activity (last 10 entries):")
        recent_entries = AccountingAuditTrail.objects.order_by("-timestamp")[:10]
        for entry in recent_entries:
            self.stdout.write(
                f"  {entry.timestamp} - {entry.user} - {entry.action} - {entry.content_object}"
            )

        # Entries without user
        entries_without_user = AccountingAuditTrail.objects.filter(
            user__isnull=True
        ).count()
        if entries_without_user > 0:
            self.stdout.write(f"\nEntries without user: {entries_without_user}")

        # Entries with missing objects
        missing_objects = 0
        for content_type in ContentType.objects.all():
            model_class = content_type.model_class()
            if not model_class:
                continue

            audit_entries = AccountingAuditTrail.objects.filter(
                content_type=content_type
            )
            for audit_entry in audit_entries:
                try:
                    model_class.objects.get(pk=audit_entry.object_id)
                except model_class.DoesNotExist:
                    missing_objects += 1

        if missing_objects > 0:
            self.stdout.write(f"Entries with missing objects: {missing_objects}")
