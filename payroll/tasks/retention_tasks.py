from __future__ import annotations

from celery import shared_task

from payroll.services.retention import apply_hr_retention


@shared_task(name="payroll.apply_hr_retention")
def apply_hr_retention_task() -> dict[str, int | None]:
    return apply_hr_retention().as_dict()
