from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from accounting.models import Account, Journal
from accounting.utils import create_journal_with_entries
from payroll.models import PayrollRun


CORRECTION_PREFIX = "Payroll statutory correction:"
ZERO = Decimal("0.00")


class Command(BaseCommand):
    help = (
        "Backfill correction journals for payroll runs where NHF/NHIS were posted "
        "as annual instead of monthly amounts. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist correction journals. If omitted, runs as dry-run.",
        )
        parser.add_argument(
            "--from-date",
            type=str,
            help="Filter payroll journals on/after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--to-date",
            type=str,
            help="Filter payroll journals on/before this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--journal-id",
            action="append",
            type=int,
            help="Specific payroll journal id(s) to evaluate. Can be passed multiple times.",
        )
        parser.add_argument(
            "--company-id",
            type=int,
            help="Restrict to PayrollRun.company_id.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Max journals to process after filters.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        from_date = self._parse_date(options.get("from_date"), "--from-date")
        to_date = self._parse_date(options.get("to_date"), "--to-date")

        if from_date and to_date and from_date > to_date:
            raise CommandError("--from-date cannot be later than --to-date")

        accounts = self._get_required_accounts()
        payroll_ct = ContentType.objects.get_for_model(PayrollRun)
        journal_ct = ContentType.objects.get_for_model(Journal)

        queryset = Journal.objects.filter(
            status=Journal.JournalStatus.POSTED,
            content_type=payroll_ct,
            object_id__isnull=False,
        ).order_by("date", "pk")

        if options.get("journal_id"):
            queryset = queryset.filter(pk__in=options["journal_id"])
        if from_date:
            queryset = queryset.filter(date__gte=from_date)
        if to_date:
            queryset = queryset.filter(date__lte=to_date)
        if options.get("company_id"):
            queryset = queryset.filter(object_id__in=PayrollRun.objects.filter(
                company_id=options["company_id"]
            ).values_list("pk", flat=True))

        if options.get("limit"):
            queryset = queryset[: options["limit"]]

        totals = {
            "scanned": 0,
            "candidates": 0,
            "created": 0,
            "already_corrected": 0,
            "skipped": 0,
            "errors": 0,
        }

        mode = "APPLY" if apply_changes else "DRY RUN"
        self.stdout.write(f"{mode}: payroll statutory backfill")

        for journal in queryset:
            totals["scanned"] += 1

            existing = Journal.objects.filter(
                content_type=journal_ct,
                object_id=journal.pk,
                description__startswith=CORRECTION_PREFIX,
            )
            if existing.exists():
                totals["already_corrected"] += 1
                self.stdout.write(
                    f"- skip journal={journal.pk} ({journal.transaction_number}): already corrected"
                )
                continue

            payroll_run = PayrollRun.objects.filter(pk=journal.object_id).first()
            if payroll_run is None:
                totals["skipped"] += 1
                self.stdout.write(
                    f"- skip journal={journal.pk} ({journal.transaction_number}): missing PayrollRun #{journal.object_id}"
                )
                continue

            correction = self._build_correction(journal, payroll_run)
            if correction is None:
                totals["skipped"] += 1
                self.stdout.write(
                    f"- skip journal={journal.pk} ({journal.transaction_number}): no overposting detected"
                )
                continue

            totals["candidates"] += 1
            self.stdout.write(
                "- candidate "
                f"journal={journal.pk} ({journal.transaction_number}) "
                f"nhf_over={correction['over_nhf']} health_over={correction['over_health_total']}"
            )

            if not apply_changes:
                continue

            try:
                create_journal_with_entries(
                    date=journal.date,
                    description=f"{CORRECTION_PREFIX} {journal.transaction_number}",
                    entries=self._build_entries(correction, accounts),
                    fiscal_year=journal.period.fiscal_year,
                    period=journal.period,
                    source_object=journal,
                    auto_post=True,
                    validate_balances=False,
                )
                totals["created"] += 1
            except Exception as exc:
                totals["errors"] += 1
                self.stderr.write(
                    f"! error journal={journal.pk} ({journal.transaction_number}): {exc}"
                )

        self.stdout.write(
            "summary "
            f"scanned={totals['scanned']} candidates={totals['candidates']} "
            f"created={totals['created']} already_corrected={totals['already_corrected']} "
            f"skipped={totals['skipped']} errors={totals['errors']}"
        )

    def _parse_date(self, value: str | None, arg_name: str) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"Invalid {arg_name} value '{value}'. Use YYYY-MM-DD.") from exc

    def _get_required_accounts(self):
        account_numbers = ["6010", "6030", "2130", "2150"]
        accounts = {
            account.account_number: account
            for account in Account.objects.filter(account_number__in=account_numbers)
        }

        missing = [number for number in account_numbers if number not in accounts]
        if missing:
            raise CommandError(
                f"Missing required account(s): {', '.join(missing)}. "
                "Ensure payroll chart-of-accounts is initialized first."
            )
        return accounts

    def _build_correction(self, journal: Journal, payroll_run: PayrollRun):
        actual = self._actual_posted_totals(journal)
        expected = self._expected_monthly_totals(payroll_run)

        over_nhf = self._q(max(actual["nhf_credit"] - expected["nhf_monthly"], ZERO))
        over_health_total = self._q(
            max(actual["health_payable_credit"] - expected["health_payable_monthly"], ZERO)
        )

        if over_nhf <= ZERO and over_health_total <= ZERO:
            return None

        data_health_employee_over = self._q(
            max(expected["health_employee_annual"] - expected["health_employee_monthly"], ZERO)
        )
        data_health_employer_over = self._q(
            max(expected["health_employer_annual"] - expected["health_employer_monthly"], ZERO)
        )
        data_health_total_over = self._q(data_health_employee_over + data_health_employer_over)

        if over_health_total <= ZERO:
            over_health_employee = ZERO
            over_health_employer = ZERO
        elif data_health_total_over > ZERO:
            # Preserve employee/employer split proportionally and keep totals rounded to cents.
            ratio_employee = data_health_employee_over / data_health_total_over
            over_health_employee = self._q(over_health_total * ratio_employee)
            over_health_employer = self._q(over_health_total - over_health_employee)
        else:
            over_health_employee = over_health_total
            over_health_employer = ZERO

        return {
            "journal": journal,
            "over_nhf": over_nhf,
            "over_health_total": over_health_total,
            "over_health_employee": over_health_employee,
            "over_health_employer": over_health_employer,
        }

    def _actual_posted_totals(self, journal: Journal):
        rows = (
            journal.entries.values("account__account_number", "entry_type")
            .annotate(total=Sum("amount"))
            .order_by()
        )
        totals = {
            (row["account__account_number"], row["entry_type"]): Decimal(row["total"] or 0)
            for row in rows
        }
        return {
            "nhf_credit": totals.get(("2150", "CREDIT"), ZERO),
            "health_payable_credit": totals.get(("2130", "CREDIT"), ZERO),
        }

    def _expected_monthly_totals(self, payroll_run: PayrollRun):
        nhf_monthly = ZERO
        health_employee_monthly = ZERO
        health_employer_monthly = ZERO
        health_employee_annual = ZERO
        health_employer_annual = ZERO

        run_entries = payroll_run.payroll_run_entries.select_related(
            "payroll_entry__pays__employee_pay"
        )

        for run_entry in run_entries:
            payroll = getattr(run_entry.payroll_entry.pays, "employee_pay", None)
            if payroll is None:
                continue

            annual_nhf = Decimal(payroll.nhf or 0)
            annual_health_employee = Decimal(payroll.employee_health or 0)
            annual_health_employer = Decimal(payroll.emplyr_health or 0)

            nhf_monthly += annual_nhf / Decimal("12")
            health_employee_monthly += annual_health_employee / Decimal("12")
            health_employer_monthly += annual_health_employer / Decimal("12")
            health_employee_annual += annual_health_employee
            health_employer_annual += annual_health_employer

        return {
            "nhf_monthly": self._q(nhf_monthly),
            "health_employee_monthly": self._q(health_employee_monthly),
            "health_employer_monthly": self._q(health_employer_monthly),
            "health_payable_monthly": self._q(health_employee_monthly + health_employer_monthly),
            "health_employee_annual": self._q(health_employee_annual),
            "health_employer_annual": self._q(health_employer_annual),
        }

    def _build_entries(self, correction, accounts):
        entries = []

        if correction["over_nhf"] > ZERO:
            entries.append(
                {
                    "account": accounts["2150"],
                    "entry_type": "DEBIT",
                    "amount": correction["over_nhf"],
                    "memo": "Backfill correction: reduce excess NHF payable",
                }
            )

        if correction["over_health_total"] > ZERO:
            entries.append(
                {
                    "account": accounts["2130"],
                    "entry_type": "DEBIT",
                    "amount": correction["over_health_total"],
                    "memo": "Backfill correction: reduce excess health payable",
                }
            )

        salary_credit = self._q(correction["over_nhf"] + correction["over_health_employee"])
        if salary_credit > ZERO:
            entries.append(
                {
                    "account": accounts["6010"],
                    "entry_type": "CREDIT",
                    "amount": salary_credit,
                    "memo": "Backfill correction: reverse excess salary statutory expense",
                }
            )

        if correction["over_health_employer"] > ZERO:
            entries.append(
                {
                    "account": accounts["6030"],
                    "entry_type": "CREDIT",
                    "amount": correction["over_health_employer"],
                    "memo": "Backfill correction: reverse excess employer health expense",
                }
            )

        return entries

    def _q(self, value: Decimal):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
