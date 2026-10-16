"""Canonical monthly net-pay calculator (L2/E2 foundation).

Unifies three competing definitions:
- payroll/utils.py:get_net_pay (annual gross/12 - health/12 - nhf/12 - payee_monthly - water)
- payroll/models/payroll.py:PayrollEntry.get_netpay (stored net + allowances - deductions)
- payroll/utils.py:monthly_cost_breakdown (employer-cost view)

Canonical rule (documented here, locked by tests):
  monthly_gross = annual_gross / 12
  monthly_health = annual_employee_health / 12
  monthly_nhf = annual_nhf / 12
  net = monthly_gross - monthly_health - monthly_nhf - payee_monthly - water_monthly
        + allowances_monthly - deductions_monthly

All annual→monthly divisions are explicit per-field. Renderers must NOT divide
ad hoc (/12 in templates/views). Migrated (locked by payroll/tests_payroll_calc.py
parity tests):
- payroll/utils.py:get_net_pay delegates to monthly_net_pay
- payroll/models/payroll.py:PayrollEntry.get_netpay delegates to entry_net_pay
- payroll/utils.py:monthly_cost_breakdown derives every monthly row from
  monthly_net_pay (employee pension expressed as deductions_monthly)
"""

from decimal import Decimal
from typing import Union

Numeric = Union[int, float, str, Decimal, None]


def _d(value: Numeric) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal(0)


def monthly_net_pay(
    gross_annual: Numeric = 0,
    employee_health_annual: Numeric = 0,
    nhf_annual: Numeric = 0,
    payee_monthly: Numeric = 0,
    water_monthly: Numeric = 0,
    allowances_monthly: Numeric = 0,
    deductions_monthly: Numeric = 0,
) -> dict:
    gross_annual = _d(gross_annual)
    employee_health_annual = _d(employee_health_annual)
    nhf_annual = _d(nhf_annual)
    payee_monthly = _d(payee_monthly)
    water_monthly = _d(water_monthly)
    allowances_monthly = _d(allowances_monthly)
    deductions_monthly = _d(deductions_monthly)

    monthly_gross = gross_annual / Decimal(12)
    monthly_health = employee_health_annual / Decimal(12)
    monthly_nhf = nhf_annual / Decimal(12)

    net = (
        monthly_gross
        - monthly_health
        - monthly_nhf
        - payee_monthly
        - water_monthly
        + allowances_monthly
        - deductions_monthly
    )
    return {
        "monthly_gross": monthly_gross,
        "monthly_health": monthly_health,
        "monthly_nhf": monthly_nhf,
        "payee_monthly": payee_monthly,
        "water_monthly": water_monthly,
        "allowances_monthly": allowances_monthly,
        "deductions_monthly": deductions_monthly,
        "net": net,
    }


def annual_to_monthly(value: Numeric) -> Decimal:
    """Canonical annual→monthly division for stored annual figures.

    Single home of the "/12" that pay configs store annual (or per-year
    levy) amounts for. Anything that needs a monthly figure from a stored
    annual amount must route through here rather than dividing inline.
    """
    return _d(value) / Decimal(12)


def entry_net_pay(
    stored_net: Numeric,
    allowances_monthly: Numeric = 0,
    deductions_monthly: Numeric = 0,
) -> Decimal:
    """Payslip net for a payroll entry: stored base net + adjustments.

    ``PayrollEntry.netpay`` is stored as the employee's base monthly net
    (``EmployeeProfile.net_pay``, computed by ``monthly_net_pay``) plus the
    period's allowances minus the period's standard/IOU deductions. This is
    the ``+ allowances_monthly - deductions_monthly`` tail of the canonical
    rule applied to a stored base.
    """
    return (
        _d(stored_net) + _d(allowances_monthly) - _d(deductions_monthly)
    )


# Standard Nigerian monthly working-day basis for daily-rate calculations
# (Mon-Fri, 52 weeks x 5 / 12).
WORKING_DAYS_PER_MONTH = Decimal(22)


def absence_deduction(
    basic_monthly: Numeric,
    absent_days: Numeric,
    working_days_per_month: Numeric = WORKING_DAYS_PER_MONTH,
) -> Decimal:
    """Unpaid-absence deduction: one daily basic rate per absent day.

    Daily rate is ``monthly basic / working_days_per_month`` (default 22).
    Companies must opt in via ``CompanyPayrollSetting.deduct_unpaid_absence``;
    this function is the arithmetic only (P1-7, Odoo-style attendance feed).
    """
    days = _d(absent_days)
    divisor = _d(working_days_per_month)
    if days <= 0 or divisor <= 0:
        return Decimal("0.00")
    daily_rate = _d(basic_monthly) / divisor
    return (daily_rate * days).quantize(Decimal("0.01"))
