"""
Statutory compliance calendar.

Computes due dates for the obligations Nigerian payroll runs generate and
flags overdue remittances with penalty exposure.

Rule basis (verified against current statutory guidance, see the compliance
research report in the thread history):

- PAYE monthly remittance is due on the 10th of the month following the
  salary payment (Nigeria Tax Act 2025 / NTAA; state IRS practice).
- The annual PAYE emoluments return is due 31 January of the following year.
- Pension contributions are remitted within 7 working days of salary payment
  (PenCom); late remittance attracts 2% per month of the outstanding amount.
  The 7-working-day clock runs from the run's actual ``payment_date`` when
  tracked, else from the period start (the previous anchor).
- NHF and NHIA have no fixed federal remittance date in the primary acts;
  the 10th-of-following-month default here is FMBN/HMO practice and is
  flagged as such in the UI.
- NSITF (Employees' Compensation Act 2010): 1% of monthly payroll,
  remitted monthly on or before the last day of the month (NSITF Act s.13(2)
  practice as cited by NSITF compliance guidance).
- ITF training levy: 1% of annual payroll, remitted annually within one
  month of the close of the financial year; compliance practice cites
  1 April (31 March for the prior year). Shown per year, gated on the
  company's ``itf_applicable`` flag.
- Both employer levies are gated on the company flags
  (``CompanyPayrollSetting.nsitf_applicable`` / ``itf_applicable``); their
  penalty rates are not fabricated here.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from django.db.models import Sum
from django.utils import timezone

from payroll.models import (
    CompanyPayrollSetting,
    Payroll,
    PayrollRun,
    PayrollRunEntry,
    PublicHoliday,
    RemittanceRecord,
)

# ---------------------------------------------------------------------------
# Obligation definitions
# ---------------------------------------------------------------------------

OBLIGATION_CHOICES = [
    ("paye", "PAYE"),
    ("pension", "Pension"),
    ("nhf", "NHF"),
    ("nhia", "NHIA"),
    ("paye_annual", "PAYE Annual Return"),
    ("itf", "ITF"),
    ("nsitf", "NSITF"),
]

OBLIGATION_LABELS: dict = dict(OBLIGATION_CHOICES)

# Obligations that carry a money amount (the annual return is a filing).
MONETARY_OBLIGATIONS = {"paye", "pension", "nhf", "nhia", "itf", "nsitf"}

# Statutory schemes for the per-scheme overdue breakdown, in canonical order.
# The annual PAYE return belongs to the PAYE scheme.
SCHEME_GROUPS = [
    ("paye", "PAYE", {"paye", "paye_annual"}),
    ("pension", "Pension", {"pension"}),
    ("nhf", "NHF", {"nhf"}),
    ("nhia", "NHIA", {"nhia"}),
    ("nsitf", "NSITF", {"nsitf"}),
    ("itf", "ITF", {"itf"}),
]

PENSION_PENALTY_PERCENT_PER_MONTH = Decimal("2")


def _as_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    # monthyear.Month and similar month-only values normalize to the 1st.
    return date(value.year, value.month, 1)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Due-date math (pure, unit-testable)
# ---------------------------------------------------------------------------


def paye_due_date(period: date) -> date:
    """10th of the month following the pay period."""
    period = _as_date(period)
    if period.month == 12:
        return date(period.year + 1, 1, 10)
    return date(period.year, period.month + 1, 10)


def nhf_due_date(period: date) -> date:
    """FMBN practice default: 10th of the month following the pay period."""
    return paye_due_date(period)


def nhia_due_date(period: date) -> date:
    """Monthly practice default: 10th of the month following the pay period."""
    return paye_due_date(period)


def annual_paye_return_due(year: int) -> date:
    """31 January of the year following the tax year."""
    return date(year + 1, 1, 31)


def nsitf_due_date(period: date) -> date:
    """NSITF: due on or before the last day of the month (s.13(2) practice)."""
    period = _as_date(period)
    return date(period.year, period.month, calendar.monthrange(period.year, period.month)[1])


def itf_due_date(year: int) -> date:
    """ITF: annual levy due 1 April of the year following the financial year."""
    return date(year + 1, 4, 1)


def add_working_days(
    start: date, days: int, holidays: Optional[list] = None
) -> date:
    """
    Advance ``days`` working days from ``start`` (exclusive), skipping
    weekends and any dates in ``holidays``.
    """
    holiday_set = {_as_date(d) for d in (holidays or []) if d is not None}
    current = _as_date(start)
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holiday_set:
            remaining -= 1
    return current


def pension_due_date(payday: date, holidays: Optional[list] = None) -> date:
    """Pension remittance is due within 7 working days of salary payment."""
    return add_working_days(payday, 7, holidays)


# ---------------------------------------------------------------------------
# Penalty exposure
# ---------------------------------------------------------------------------


def months_overdue(due_date: date, as_of: date) -> int:
    """Whole months between the due date and ``as_of`` (min 1 when overdue)."""
    due = _as_date(due_date)
    as_of = _as_date(as_of)
    if as_of <= due:
        return 0
    days = (as_of - due).days
    return max(1, -(-days // 30))  # ceil(days / 30)


def pension_penalty(amount: Decimal, due_date: date, as_of: date) -> Decimal:
    """PenCom penalty: 2% per month of the outstanding contribution."""
    months = months_overdue(due_date, as_of)
    if months <= 0:
        return Decimal("0.00")
    return (
        Decimal(amount) * PENSION_PENALTY_PERCENT_PER_MONTH * months / Decimal("100")
    ).quantize(Decimal("0.01"))


def penalty_exposure(
    obligation: str,
    amount: Optional[Decimal],
    due_date: date,
    as_of: date,
) -> Optional[dict]:
    """
    Penalty exposure for an overdue obligation.

    Returns a dict with ``rate``/``amount``/``note`` or None when not
    overdue. Rates are only computed where a verified federal rule exists
    (pension). PAYE penalties are set by each state IRS; NHF/NHIA penalties
    are set by the governing act/plan and are intentionally not fabricated.
    """
    as_of = _as_date(as_of)
    if as_of <= _as_date(due_date):
        return None

    if obligation == "pension":
        return {
            "rate": "2% per month",
            "amount": pension_penalty(amount, due_date, as_of),
            "note": "PenCom penalty on outstanding contributions",
        }
    if obligation == "paye":
        return {
            "rate": None,
            "amount": None,
            "note": "Interest and penalties set by the state IRS",
        }
    if obligation == "nhf":
        return {
            "rate": None,
            "amount": None,
            "note": "Penalty per NHF Act / FMBN practice",
        }
    if obligation == "nhia":
        return {
            "rate": None,
            "amount": None,
            "note": "Penalty per NHIA Act / plan terms",
        }
    if obligation == "nsitf":
        return {
            "rate": None,
            "amount": None,
            "note": "Penalty per ECA 2010 / NSITF practice",
        }
    if obligation == "itf":
        return {
            "rate": None,
            "amount": None,
            "note": "Penalty per ITF Act practice",
        }
    if obligation == "paye_annual":
        return {
            "rate": None,
            "amount": None,
            "note": "Late-filing penalties per the state IRS",
        }
    return None


# ---------------------------------------------------------------------------
# Period amounts
# ---------------------------------------------------------------------------


def _decimal(value: object) -> Decimal:
    return Decimal(value or 0)


def period_remittance_amounts(company: Any, run: Any) -> dict:
    """
    Monthly remittance amounts for a pay run.

    Stored-field conventions: ``payee``, ``nhf`` and ``nhif`` are monthly;
    ``pension`` is annual (basic x 12 x rate) and is divided by 12.
    """
    cents = Decimal("0.01")
    aggregate = PayrollRunEntry.objects.filter(
        payroll_run=run,
        payroll_entry__company=company,
    ).aggregate(
        payee=Sum("payroll_entry__pays__employee_pay__payee"),
        pension=Sum("payroll_entry__pays__employee_pay__pension"),
        nhf=Sum("payroll_entry__pays__employee_pay__nhf"),
        nhia=Sum("payroll_entry__pays__employee_pay__nhif"),
        nsitf=Sum("payroll_entry__pays__employee_pay__nsitf"),
    )
    return {
        "paye": _decimal(aggregate["payee"]).quantize(cents),
        "pension": (_decimal(aggregate["pension"]) / Decimal("12")).quantize(cents),
        "nhf": _decimal(aggregate["nhf"]).quantize(cents),
        "nhia": _decimal(aggregate["nhia"]).quantize(cents),
        "nsitf": _decimal(aggregate["nsitf"]).quantize(cents),
    }


def annual_itf_amount(company: Any) -> Decimal:
    """Total annual ITF levy from the company's payroll configs.

    ``Payroll.itf`` is 1% of the employee's annual gross, so the sum across
    the company's current configs is the annual remittance due.
    """
    total = Payroll.objects.filter(company=company).aggregate(itf=Sum("itf"))["itf"]
    return _decimal(total).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Per-company calendar
# ---------------------------------------------------------------------------


def compliance_obligations(company: Any, as_of: Optional[date] = None) -> list:
    """
    Build the compliance calendar for a company: one row per obligation and
    pay period, with status (done / overdue / due_soon / upcoming) and
    penalty exposure for overdue rows.

    Rows are derived from the company's payroll runs, so no sync step is
    needed; the user's remittance state lives in ``RemittanceRecord``.
    """
    as_of = as_of or timezone.localdate()
    setting = CompanyPayrollSetting.objects.filter(company=company).first()
    # Employer levy flags default like the model fields when no settings row
    # exists (NSITF applies by default under the ECA 2010; ITF is opt-in).
    nsitf_applicable = bool(setting.nsitf_applicable if setting else True)
    itf_applicable = bool(setting.itf_applicable if setting else False)
    holidays = list(
        PublicHoliday.objects.filter(company=company).values_list("date", flat=True)
    )

    # Deduplicate pay periods in Python (DISTINCT ON is Postgres-only).
    # PayrollRun.paydays is a monthyear.Month; normalize to a date for the
    # calendar rows and the RemittanceRecord lookup map.
    runs = []
    seen = set()
    for run in PayrollRun.objects.filter(company=company).order_by("paydays"):
        period = _as_date(run.paydays)
        if period is None or period in seen:
            continue
        seen.add(period)
        runs.append(run)

    records = {
        (record.obligation, _as_date(record.period)): record
        for record in RemittanceRecord.objects.filter(company=company)
    }

    obligations = []
    years = set()
    for run in runs:
        period = _as_date(run.paydays)
        years.add(period.year)
        amounts = period_remittance_amounts(company, run)

        # Pension's 7-working-day clock runs from the run's actual salary
        # payment date; when that wasn't recorded it falls back to the period
        # start. The anchor is surfaced on the calendar so the deadline math
        # can be audited.
        pension_anchor = run.payment_date or period
        pension_anchor_fallback = run.payment_date is None

        specs = [
            (
                "paye",
                amounts["paye"],
                paye_due_date(period),
                True,
                "Mark remitted",
                None,
                False,
            ),
            (
                "pension",
                amounts["pension"],
                pension_due_date(pension_anchor, holidays),
                True,
                "Mark remitted",
                pension_anchor,
                pension_anchor_fallback,
            ),
            (
                "nhf",
                amounts["nhf"],
                nhf_due_date(period),
                amounts["nhf"] > 0,
                "Mark remitted",
                None,
                False,
            ),
            (
                "nhia",
                amounts["nhia"],
                nhia_due_date(period),
                bool(setting and setting.nhia_applicable) or amounts["nhia"] > 0,
                "Mark remitted",
                None,
                False,
            ),
            (
                "nsitf",
                amounts["nsitf"],
                nsitf_due_date(period),
                nsitf_applicable and amounts["nsitf"] > 0,
                "Mark remitted",
                None,
                False,
            ),
        ]
        for key, amount, due_date, include, action_label, anchor, anchor_fallback in specs:
            if not include:
                continue
            obligations.append(
                _build_obligation(
                    key,
                    period,
                    amount,
                    due_date,
                    records,
                    as_of,
                    action_label,
                    paid_on=run.payment_date,
                    anchor=anchor,
                    anchor_fallback=anchor_fallback,
                )
            )

    # Annual PAYE emoluments return for each year that has a run.
    for year in sorted(years):
        obligations.append(
            _build_obligation(
                "paye_annual",
                date(year, 1, 1),
                None,
                annual_paye_return_due(year),
                records,
                as_of,
                "Mark filed",
            )
        )

    # Annual ITF training levy for each year that has a run, gated on the
    # company's itf_applicable flag and on there being a real amount.
    if itf_applicable:
        itf_amount = annual_itf_amount(company)
        if itf_amount > 0:
            for year in sorted(years):
                obligations.append(
                    _build_obligation(
                        "itf",
                        date(year, 1, 1),
                        itf_amount,
                        itf_due_date(year),
                        records,
                        as_of,
                        "Mark remitted",
                    )
                )

    obligations.sort(key=lambda o: (o["due_date"], o["key"]))
    return obligations


def compliance_summary(company: Any, as_of: Optional[date] = None) -> dict:
    """
    At-a-glance exposure stats for a company: overdue count and amount, the
    number due within 7 days, and the next open deadline.

    Shared by the compliance calendar page and the payroll dashboard so the
    two surfaces can never drift apart.
    """
    obligations = compliance_obligations(company, as_of)
    overdue = [o for o in obligations if o["status"] == "overdue"]
    open_obligations = [o for o in obligations if o["status"] != "done"]
    return {
        "obligations": obligations,
        "overdue_count": len(overdue),
        "overdue_amount": sum(
            (o["amount"] or 0 for o in overdue if o["amount"] is not None),
            Decimal("0.00"),
        ),
        "due_soon_count": len(
            [o for o in obligations if o["status"] == "due_soon"]
        ),
        "next_due": min((o["due_date"] for o in open_obligations), default=None),
        "total_count": len(obligations),
        "done_count": len(obligations) - len(open_obligations),
        "scheme_breakdown": _scheme_breakdown(overdue),
    }


def _scheme_breakdown(overdue: list) -> list:
    """
    Group overdue obligations by statutory scheme, with the overdue count,
    the outstanding amount, and the computed penalty exposure per scheme.

    Only schemes with overdue obligations are included, sorted by penalty
    exposure (then count) descending so the most exposed scheme leads.
    """
    rows = []
    for key, label, obligation_keys in SCHEME_GROUPS:
        scheme_obligations = [o for o in overdue if o["key"] in obligation_keys]
        if not scheme_obligations:
            continue
        rows.append(
            {
                "key": key,
                "label": label,
                "count": len(scheme_obligations),
                "amount": sum(
                    (o["amount"] or 0 for o in scheme_obligations),
                    Decimal("0.00"),
                ),
                "penalty": sum(
                    (
                        o["penalty"]["amount"] or 0
                        for o in scheme_obligations
                        if o.get("penalty") and o["penalty"].get("amount")
                    ),
                    Decimal("0.00"),
                ),
                "penalty_rate": next(
                    (
                        o["penalty"]["rate"]
                        for o in scheme_obligations
                        if o.get("penalty") and o["penalty"].get("rate")
                    ),
                    None,
                ),
            }
        )
    rows.sort(key=lambda r: (r["penalty"], r["count"]), reverse=True)
    return rows


def _build_obligation(
    key: str,
    period: date,
    amount: Optional[Decimal],
    due_date: date,
    records: dict,
    as_of: date,
    action_label: str,
    paid_on: Optional[date] = None,
    anchor: Optional[date] = None,
    anchor_fallback: bool = False,
) -> dict:
    record = records.get((key, period))
    if record and record.remitted_on:
        status = "done"
    elif due_date < as_of:
        status = "overdue"
    elif due_date <= as_of + timedelta(days=7):
        status = "due_soon"
    else:
        status = "upcoming"

    return {
        "key": key,
        "label": OBLIGATION_LABELS[key],
        "period": period,
        "amount": amount,
        "due_date": due_date,
        "status": status,
        "record": record,
        "action_label": action_label,
        "paid_on": paid_on,
        "anchor": anchor,
        "anchor_fallback": anchor_fallback,
        "penalty": (
            penalty_exposure(key, amount, due_date, as_of)
            if status == "overdue"
            else None
        ),
    }
