import csv
import io
from decimal import Decimal

from django.utils import timezone
from django.db.models import Sum


def export_journals_to_csv(company, start_date, end_date):
    """Export posted journals as CSV for import into QuickBooks/Xero/Zoho."""
    from accounting.models import Journal, JournalEntry

    journals = Journal.objects.filter(
        company=company,
        status=Journal.JournalStatus.POSTED,
        date__gte=start_date,
        date__lte=end_date,
    ).prefetch_related("entries__account")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Transaction", "Description", "Account", "AccountNumber", "Type", "Debit", "Credit", "Source"])

    for journal in journals:
        for entry in journal.entries.all():
            writer.writerow([
                journal.date.isoformat(),
                journal.transaction_number,
                journal.description,
                entry.account.name,
                entry.account.account_number or "",
                entry.account.type,
                entry.amount if entry.entry_type == "DEBIT" else "",
                entry.amount if entry.entry_type == "CREDIT" else "",
                "Paroll",
            ])

    return output.getvalue()


def export_trial_balance_csv(company, as_of_date=None):
    """Export trial balance as CSV."""
    from accounting.utils import get_trial_balance
    as_of_date = as_of_date or timezone.now().date()
    tb = get_trial_balance(company=company, as_of_date=as_of_date)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Account", "AccountNumber", "Type", "Debit", "Credit", "Balance"])

    for data in tb.values():
        account = data["account"]
        debt_bal = account.balance if account.type in ("ASSET", "EXPENSE") and account.balance > 0 else Decimal("0")
        credit_bal = account.balance if account.type not in ("ASSET", "EXPENSE") and account.balance > 0 else Decimal("0")
        writer.writerow([
            account.name,
            account.account_number or "",
            account.type,
            float(debt_bal),
            float(credit_bal),
            float(account.balance),
        ])

    return output.getvalue()


def export_chart_of_accounts_csv(company):
    """Export chart of accounts as CSV."""
    from accounting.models import Account

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["AccountNumber", "Name", "Type", "Currency", "Status"])

    for account in Account.objects.filter(company=company).order_by("account_number"):
        writer.writerow([
            account.account_number or "",
            account.name,
            account.type,
            account.currency,
            account.status,
        ])

    return output.getvalue()
