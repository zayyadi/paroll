from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounting.models import Account
from accounting.utils import create_journal_with_entries


class Command(BaseCommand):
    help = "Migrate payroll cash account usage from 1010 to 1100."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Apply changes. Without this flag, command runs in dry-run mode.",
        )
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Journal date in YYYY-MM-DD format (default: today).",
        )

    def handle(self, *args, **options):
        execute = options["execute"]
        provided_date = options.get("date")

        migration_date = timezone.now().date()
        if provided_date:
            try:
                migration_date = date.fromisoformat(provided_date)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR("Invalid --date format. Use YYYY-MM-DD.")
                )
                return

        old_account = Account.objects.filter(account_number="1010").first()
        new_account = Account.objects.filter(account_number="1100").first()

        self.stdout.write("Cash account migration 1010 -> 1100")
        self.stdout.write(f"Mode: {'EXECUTE' if execute else 'DRY RUN'}")

        if not old_account and not new_account:
            self.stdout.write(
                self.style.WARNING(
                    "No cash accounts found for 1010 or 1100. Nothing to migrate."
                )
            )
            return

        # Case 1: only 1010 exists -> renumber in place to 1100
        if old_account and not new_account:
            self.stdout.write(
                f"Detected only 1010 account: {old_account.name} (id={old_account.pk})."
            )
            if execute:
                old_account.account_number = "1100"
                if old_account.name != "Cash and Cash Equivalents":
                    # Keep account naming consistent with payroll posting mapping.
                    old_account.name = "Cash and Cash Equivalents"
                    old_account.save(update_fields=["account_number", "name"])
                else:
                    old_account.save(update_fields=["account_number"])
                self.stdout.write(
                    self.style.SUCCESS(
                        "Renumbered account 1010 to 1100 successfully."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "Would renumber account_number 1010 to 1100."
                    )
                )
            return

        # Case 2: only 1100 exists -> already migrated
        if not old_account and new_account:
            self.stdout.write(
                self.style.SUCCESS(
                    "Account 1100 already exists and 1010 is absent. Migration complete."
                )
            )
            return

        # Case 3: both exist -> transfer current balance from 1010 to 1100
        assert old_account is not None and new_account is not None
        old_balance = Decimal(old_account.get_balance() or 0)

        self.stdout.write(
            f"Both accounts exist. 1010 balance: {old_balance}. "
            f"Old={old_account.name} (id={old_account.pk}), "
            f"New={new_account.name} (id={new_account.pk})"
        )

        if old_balance == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "1010 current balance is zero. No transfer journal needed."
                )
            )
            return

        transfer_amount = abs(old_balance)
        if old_balance > 0:
            # Asset balance normal positive: reduce old, increase new.
            entries = [
                {
                    "account": new_account,
                    "entry_type": "DEBIT",
                    "amount": transfer_amount,
                    "memo": "Cash account migration in",
                },
                {
                    "account": old_account,
                    "entry_type": "CREDIT",
                    "amount": transfer_amount,
                    "memo": "Cash account migration out",
                },
            ]
        else:
            # Negative asset balance: reverse direction.
            entries = [
                {
                    "account": new_account,
                    "entry_type": "CREDIT",
                    "amount": transfer_amount,
                    "memo": "Cash account migration out (negative balance transfer)",
                },
                {
                    "account": old_account,
                    "entry_type": "DEBIT",
                    "amount": transfer_amount,
                    "memo": "Cash account migration in (negative balance transfer)",
                },
            ]

        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    f"Would post transfer journal on {migration_date} for amount {transfer_amount}."
                )
            )
            return

        journal = create_journal_with_entries(
            date=migration_date,
            description="Cash account migration: transfer balance from 1010 to 1100",
            entries=entries,
            auto_post=True,
            validate_balances=False,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Transfer journal posted successfully: {journal.transaction_number}"
            )
        )
