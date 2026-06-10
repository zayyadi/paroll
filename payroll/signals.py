from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
import logging

from .models import PayrollRun, PayrollRunEntry, IOU, Allowance, Deduction, IOUDeduction
from .services.payroll_accounting_service import (
    handle_payroll_period_closure as _handle_payroll_period_closure,
    handle_iou_approval_accounting,
    handle_iou_direct_payment_accounting,
    create_iou_deduction_for_payroll_entry as _create_iou_deduction_for_payroll_entry,
)

logger = logging.getLogger(__name__)


def _deduction_debug_print(message):
    logger.debug("[DEDUCTION_DEBUG] %s", message)


@receiver(pre_save, sender=PayrollRun)
def handle_payroll_period_closure_signal(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = PayrollRun.objects.get(pk=instance.pk)
    except PayrollRun.DoesNotExist:
        return
    if not old_instance.closed and instance.closed:
        _handle_payroll_period_closure(instance)


@receiver(pre_save, sender=IOU)
def handle_iou_approval_signal(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = IOU.objects.get(pk=instance.pk)
    except IOU.DoesNotExist:
        return
    if old_instance.status != "APPROVED" and instance.status == "APPROVED":
        try:
            handle_iou_approval_accounting(instance)
        except Exception as exc:
            logger.warning(
                "IOU approved without accounting journal for IOU %s: %s",
                instance.pk,
                exc,
            )


@receiver(pre_save, sender=IOU)
def handle_iou_direct_payment_signal(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = IOU.objects.get(pk=instance.pk)
    except IOU.DoesNotExist:
        return
    status_changed_to_paid = old_instance.status != "PAID" and instance.status == "PAID"
    if status_changed_to_paid and instance.payment_method == "DIRECT_PAYMENT":
        try:
            handle_iou_direct_payment_accounting(instance)
        except Exception as exc:
            logger.exception(
                "Error creating IOU direct-payment journal for IOU %s: %s",
                instance.pk,
                exc,
            )


@receiver(post_save, sender=IOUDeduction)
def handle_iou_repayment_signal(sender, instance, created, **kwargs):
    action = "created" if created else "updated"
    _deduction_debug_print(
        f"IOU deduction {action}: id={instance.id}, employee_id={instance.employee_id}, "
        f"iou_id={instance.iou_id}, amount={instance.amount}, payday={instance.payday_id}."
    )


@receiver(post_save, sender=PayrollRunEntry)
def create_iou_deduction_for_payroll_entry_signal(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created:
        _create_iou_deduction_for_payroll_entry(instance)


@receiver(post_save, sender=Allowance)
def handle_allowance_creation_signal(sender, instance, created, **kwargs):
    return


@receiver(post_save, sender=Deduction)
def handle_deduction_creation_signal(sender, instance, created, **kwargs):
    action = "created" if created else "updated"
    _deduction_debug_print(
        f"Deduction {action}: id={instance.id}, employee_id={instance.employee_id}, "
        f"type={instance.deduction_type}, amount={instance.amount}, reason={instance.reason or ''}."
    )
