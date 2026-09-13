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
ad hoc (/12 in templates/views). Follow-up: migrate get_net_pay,
PayrollEntry.get_netpay, and monthly_cost_breakdown to delegate here.
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
