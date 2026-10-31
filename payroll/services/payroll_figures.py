"""Monthly statutory figures frozen on each payroll entry.

``PayrollEntry.statutory_snapshot`` is captured from the employee's salary
config whenever the entry's net pay is calculated, and stops changing once the
run is locked (locked entries cannot be saved). Payslips, remittances, reports
and the ledger posting read figures through :func:`entry_figures`, so a later
salary change never rewrites a past month.

Entries created before snapshots existed have an empty snapshot; for those
:func:`entry_figures` falls back to the employee's current config, which is
the previous behaviour.
"""

from decimal import Decimal
from typing import Any

from payroll.services.payroll_calc import annual_to_monthly

CENTS = Decimal("0.01")

FIGURE_KEYS = (
    "gross",
    "basic",
    "housing",
    "transport",
    "other_emoluments",
    "taxable_income",
    "employee_paye",
    "employee_pension",
    "employee_nhf",
    "employee_nhia",
    "employee_water",
    "net_pay",
    "employer_pension",
    "employer_nhia",
    "employer_nsitf",
    "employer_itf",
    "employer_cost",
)


def config_figures(config: Any) -> dict:
    """Monthly figures for a salary config, quantised to kobo."""
    from payroll import utils

    if config is None:
        return {key: Decimal("0.00") for key in FIGURE_KEYS}

    figures = dict(utils.monthly_cost_breakdown(config))
    for field in ("basic", "housing", "transport", "taxable_income"):
        figures[field] = annual_to_monthly(getattr(config, field)).quantize(CENTS)
    figures["other_emoluments"] = (
        figures["gross"] - figures["basic"] - figures["housing"] - figures["transport"]
    )
    return {key: figures[key] for key in FIGURE_KEYS}


def snapshot_for(config: Any) -> dict:
    """JSON-safe snapshot of :func:`config_figures`."""
    snapshot = {key: str(value) for key, value in config_figures(config).items()}
    snapshot["config_id"] = getattr(config, "pk", None)
    return snapshot


def _with_totals(figures: dict) -> dict:
    """Add the employee + employer remittance totals reports show."""
    figures["pension_total"] = figures["employee_pension"] + figures["employer_pension"]
    figures["nhia_total"] = figures["employee_nhia"] + figures["employer_nhia"]
    return figures


def entry_figures(payroll_entry: Any) -> dict:
    """Monthly figures for a payroll entry: its snapshot, else the live config.

    Includes the derived ``pension_total`` and ``nhia_total``.
    """
    snapshot = getattr(payroll_entry, "statutory_snapshot", None) or {}
    if all(key in snapshot for key in FIGURE_KEYS):
        return _with_totals({key: Decimal(snapshot[key]) for key in FIGURE_KEYS})
    return _with_totals(config_figures(payroll_entry.pays.employee_pay))


def sum_figures(payroll_entries: Any) -> dict:
    """Totals of :func:`entry_figures` across payroll entries."""
    totals: dict = {}
    for entry in payroll_entries:
        for key, value in entry_figures(entry).items():
            totals[key] = totals.get(key, Decimal("0.00")) + value
    return totals or _with_totals({key: Decimal("0.00") for key in FIGURE_KEYS})
