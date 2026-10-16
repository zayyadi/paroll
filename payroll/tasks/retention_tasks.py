from __future__ import annotations

from celery import shared_task

from payroll.services.retention import apply_hr_retention


@shared_task(name="payroll.apply_hr_retention")
def apply_hr_retention_task(requested_by_id: int | None = None) -> dict[str, int | None]:
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.get(pk=requested_by_id) if requested_by_id is not None else None
    return apply_hr_retention(actor=actor).as_dict()
