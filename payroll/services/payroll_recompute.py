"""Recompute stored ``Payroll`` figures and employees' stored net pay.

Used after a change to the statutory calculation or the stored-unit
convention, so existing salary configs match what ``Payroll.save`` would
derive today. Historical ``PayrollEntry.netpay`` values are not touched.
"""

from decimal import Decimal

from django.db import transaction

_TRACKED_FIELDS = (
    "gross_income",
    "pension_employee",
    "pension_employer",
    "nhf",
    "employee_health",
    "emplyr_health",
    "nsitf",
    "itf",
    "taxable_income",
    "payee",
)


class _DryRunRollback(Exception):
    pass


def _recompute() -> dict:
    from payroll import utils
    from payroll.models import EmployeeProfile, Payroll

    configs_changed = 0
    for config in Payroll.all_objects.all().iterator():
        before = tuple(getattr(config, field) for field in _TRACKED_FIELDS)
        config.save()
        after = tuple(getattr(config, field) for field in _TRACKED_FIELDS)
        configs_changed += before != after

    profiles_changed = 0
    profiles = EmployeeProfile._base_manager.filter(employee_pay__isnull=False).select_related("employee_pay")
    for profile in profiles.iterator():
        net_pay = Decimal(utils.get_net_pay(profile)).quantize(Decimal("0.01"))
        if profile.net_pay != net_pay:
            profiles_changed += 1
            EmployeeProfile._base_manager.filter(pk=profile.pk).update(net_pay=net_pay)

    return {"configs": configs_changed, "profiles": profiles_changed}


def recompute_payroll_figures(*, apply: bool) -> dict:
    """Recompute everything; without ``apply`` the work is rolled back and
    only the counts of what would change are returned."""
    result: dict = {}
    try:
        with transaction.atomic():
            result = _recompute()
            if not apply:
                raise _DryRunRollback
    except _DryRunRollback:
        pass
    result["applied"] = apply
    return result
