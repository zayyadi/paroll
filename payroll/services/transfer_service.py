from __future__ import annotations
from typing import Any
from decimal import Decimal
from django.utils import timezone
from django.db import transaction


def execute_transfer(*, transfer: Any, performed_by: Any) -> Any:
    with transaction.atomic():
        employee = transfer.employee
        if transfer.to_department:
            employee.department = transfer.to_department
        if transfer.to_position:
            employee.job_title = transfer.to_position
        employee.save(update_fields=["department", "job_title"])
        transfer.status = "COMPLETED"
        transfer.approved_by = performed_by
        transfer.approved_at = timezone.now()
        transfer.save(update_fields=["status", "approved_by", "approved_at"])
    return transfer


def approve_transfer(*, transfer: Any, approved_by: Any) -> Any:
    transfer.status = "APPROVED"
    transfer.approved_by = approved_by
    transfer.approved_at = timezone.now()
    transfer.save(update_fields=["status", "approved_by", "approved_at"])
    return transfer


def reject_transfer(*, transfer: Any, approved_by: Any) -> Any:
    transfer.status = "REJECTED"
    transfer.approved_by = approved_by
    transfer.approved_at = timezone.now()
    transfer.save(update_fields=["status", "approved_by", "approved_at"])
    return transfer


def execute_promotion(*, promotion: Any, performed_by: Any) -> Any:
    with transaction.atomic():
        employee = promotion.employee
        employee.job_title = promotion.new_title
        if promotion.new_salary_config:
            employee.employee_pay = promotion.new_salary_config
        employee.save(update_fields=["job_title", "employee_pay"])
        promotion.status = "COMPLETED"
        promotion.approved_by = performed_by
        promotion.approved_at = timezone.now()
        promotion.save(update_fields=["status", "approved_by", "approved_at"])
    return promotion


def approve_promotion(*, promotion: Any, approved_by: Any) -> Any:
    promotion.status = "APPROVED"
    promotion.approved_by = approved_by
    promotion.approved_at = timezone.now()
    promotion.save(update_fields=["status", "approved_by", "approved_at"])
    return promotion


def reject_promotion(*, promotion: Any, approved_by: Any) -> Any:
    promotion.status = "REJECTED"
    promotion.approved_by = approved_by
    promotion.approved_at = timezone.now()
    promotion.save(update_fields=["status", "approved_by", "approved_at"])
    return promotion
