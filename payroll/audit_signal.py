from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from accounting.models import AccountingAuditTrail
from accounting.utils import log_accounting_activity
from .models import (
    EmployeeProfile,
    Payroll,
    PayrollEntry,
    PayrollRun,
    IOU,
    LeaveRequest,
    Allowance,
    Deduction,
    IOUDeduction,
)
from .models.utils import AuditTrail


def log_audit(user, action, instance, changes=None, reason=None):
    """
    Log audit trail using both the old AuditTrail and new AccountingAuditTrail models.
    This maintains backward compatibility while adding enhanced accounting audit capabilities.
    """
    # Keep using the old AuditTrail for backward compatibility
    try:
        AuditTrail.objects.create(
            user=user,
            action=action,
            content_object=instance,
        )
    except Exception:
        # Silently fail if the old model doesn't exist or has issues
        pass

    # Also log to the new AccountingAuditTrail for enhanced tracking
    try:
        log_accounting_activity(
            user=user,
            action=(
                AccountingAuditTrail.ActionType.CREATE
                if "Created" in action
                else (
                    AccountingAuditTrail.ActionType.UPDATE
                    if "Updated" in action
                    else AccountingAuditTrail.ActionType.DELETE
                )
            ),
            instance=instance,
            changes=changes or {},
            reason=reason or action,
        )
    except Exception:
        # Silently fail if accounting models aren't ready
        pass


@receiver(post_save, sender=EmployeeProfile)
def log_employee_save(sender, instance, created, **kwargs):
    action = "Created EmployeeProfile" if created else "Updated EmployeeProfile"
    user = getattr(instance, "user", None)
    changes = {}

    if not created:
        # Track changes for updates
        try:
            old_instance = EmployeeProfile.objects.get(pk=instance.pk)
            # Compare fields and log changes
            for field in instance._meta.fields:
                field_name = field.name
                if field_name not in ["id", "created_at", "updated_at"]:
                    old_value = getattr(old_instance, field_name)
                    new_value = getattr(instance, field_name)
                    if old_value != new_value:
                        changes[field_name] = {
                            "old": str(old_value),
                            "new": str(new_value),
                        }
        except EmployeeProfile.DoesNotExist:
            pass

    log_audit(user, action, instance, changes=changes)


@receiver(post_delete, sender=EmployeeProfile)
def log_employee_delete(sender, instance, **kwargs):
    user = getattr(instance, "user", None)
    log_audit(user, "Deleted EmployeeProfile", instance)


@receiver(post_save, sender=Payroll)
def log_payroll_save(sender, instance, created, **kwargs):
    action = "Created Payroll" if created else "Updated Payroll"
    changes = {}

    if not created:
        # Track changes for updates
        try:
            old_instance = Payroll.objects.get(pk=instance.pk)
            # Compare financial fields
            financial_fields = [
                "basic_salary",
                "basic",
                "housing",
                "transport",
                "bht",
                "pension_employee",
                "pension_employer",
                "pension",
                "is_housing",
                "is_nhif",
                "nhf",
                "employee_health",
                "nhif",
                "emplyr_health",
                "gross_income",
                "taxable_income",
                "payee",
                "water_rate",
                "nsitf",
            ]
            for field_name in financial_fields:
                old_value = getattr(old_instance, field_name)
                new_value = getattr(instance, field_name)
                if old_value != new_value:
                    changes[field_name] = {"old": str(old_value), "new": str(new_value)}
        except Payroll.DoesNotExist:
            pass

    log_audit(None, action, instance, changes=changes)


@receiver(post_delete, sender=Payroll)
def log_payroll_delete(sender, instance, **kwargs):
    log_audit(None, "Deleted Payroll", instance)


@receiver(post_save, sender=PayrollEntry)
def log_payvar_save(sender, instance, created, **kwargs):
    action = "Created PayrollEntry" if created else "Updated PayrollEntry"
    changes = {}

    if not created:
        # Track changes for updates
        try:
            old_instance = PayrollEntry.objects.get(pk=instance.pk)
            # Compare financial fields
            financial_fields = [
                "netpay",
            ]
            for field_name in financial_fields:
                old_value = getattr(old_instance, field_name)
                new_value = getattr(instance, field_name)
                if old_value != new_value:
                    changes[field_name] = {"old": str(old_value), "new": str(new_value)}
        except PayrollEntry.DoesNotExist:
            pass

    log_audit(None, action, instance, changes=changes)


@receiver(post_delete, sender=PayrollEntry)
def log_payvar_delete(sender, instance, **kwargs):
    log_audit(None, "Deleted PayrollEntry", instance)


@receiver(pre_save, sender=PayrollRun)
def log_payt_closure(sender, instance, **kwargs):
    """
    Log payroll period closure with enhanced audit details.
    """
    if not instance.pk:
        return

    try:
        old_instance = PayrollRun.objects.get(pk=instance.pk)
        # Check if payroll is being closed
        if not old_instance.closed and instance.closed:
            # Log the closure with detailed information
            changes = {
                "status_change": {"old": "open", "new": "closed"},
                "closure_date": timezone.now().isoformat(),
                "payroll_period": str(instance.paydays),
                "employee_count": instance.payroll_payday.count(),
            }

            log_audit(
                None,  # System action
                "Closed Payroll Period",
                instance,
                changes=changes,
                reason=f"Payroll period {instance.save_month_str} closed",
            )
    except PayrollRun.DoesNotExist:
        pass


@receiver(post_save, sender=PayrollRun)
def log_payt_save(sender, instance, created, **kwargs):
    if created:
        log_audit(None, "Created PayrollRun", instance)


@receiver(post_delete, sender=PayrollRun)
def log_payt_delete(sender, instance, **kwargs):
    log_audit(None, "Deleted PayrollRun", instance)


@receiver(pre_save, sender=IOU)
def log_iou_approval(sender, instance, **kwargs):
    """
    Log IOU approval with enhanced audit details.
    """
    if not instance.pk:
        return

    try:
        old_instance = IOU.objects.get(pk=instance.pk)
        # Check if IOU is being approved
        if old_instance.status != "APPROVED" and instance.status == "APPROVED":
            changes = {
                "status_change": {"old": old_instance.status, "new": "APPROVED"},
                "approval_date": (
                    instance.approved_at.isoformat() if instance.approved_at else None
                ),
                "iou_amount": str(instance.amount),
                "iou_tenor": instance.tenor,
                "interest_rate": str(instance.interest_rate),
            }

            user = getattr(instance.employee_id, "user", None)
            log_audit(
                user,
                "Approved IOU",
                instance,
                changes=changes,
                reason=f"IOU of {instance.amount} approved for {instance.tenor} months",
            )
    except IOU.DoesNotExist:
        pass


@receiver(post_save, sender=IOU)
def log_iou_save(sender, instance, created, **kwargs):
    if created:
        user = getattr(instance.employee_id, "user", None)
        log_audit(user, "Created IOU", instance)


@receiver(post_delete, sender=IOU)
def log_iou_delete(sender, instance, **kwargs):
    user = getattr(instance.employee_id, "user", None)
    log_audit(user, "Deleted IOU", instance)


@receiver(post_save, sender=Allowance)
def log_allowance_save(sender, instance, created, **kwargs):
    action = "Created Allowance" if created else "Updated Allowance"
    user = getattr(instance.employee, "user", None)
    changes = {
        "allowance_type": instance.allowance_type,
        "amount": str(instance.amount),
    }

    log_audit(user, action, instance, changes=changes)


@receiver(post_delete, sender=Allowance)
def log_allowance_delete(sender, instance, **kwargs):
    user = getattr(instance.employee, "user", None)
    log_audit(user, "Deleted Allowance", instance)


@receiver(post_save, sender=Deduction)
def log_deduction_save(sender, instance, created, **kwargs):
    action = "Created Deduction" if created else "Updated Deduction"
    user = getattr(instance.employee, "user", None)
    changes = {
        "deduction_type": instance.deduction_type,
        "amount": str(instance.amount),
        "reason": instance.reason or "",
    }

    log_audit(user, action, instance, changes=changes)


@receiver(post_delete, sender=Deduction)
def log_deduction_delete(sender, instance, **kwargs):
    user = getattr(instance.employee, "user", None)
    log_audit(user, "Deleted Deduction", instance)


@receiver(post_save, sender=IOUDeduction)
def log_iou_deduction_save(sender, instance, created, **kwargs):
    if created:
        user = getattr(instance.employee, "user", None)
        changes = {
            "iou_amount": str(instance.iou.amount),
            "deduction_amount": str(instance.amount),
            "payday": str(instance.payday.paydays),
        }

        log_audit(
            user,
            "Created IOU Deduction",
            instance,
            changes=changes,
            reason="IOU repayment installment processed",
        )


@receiver(post_save, sender=LeaveRequest)
def log_leave_save(sender, instance, created, **kwargs):
    action = "Created LeaveRequest" if created else "Updated LeaveRequest"
    user = getattr(instance.employee, "user", None)
    changes = {
        "leave_type": instance.leave_type,
        "start_date": str(instance.start_date),
        "end_date": str(instance.end_date),
        "status": instance.status,
    }

    log_audit(user, action, instance, changes=changes)


@receiver(post_delete, sender=LeaveRequest)
def log_leave_delete(sender, instance, **kwargs):
    user = getattr(instance.employee, "user", None)
    log_audit(user, "Deleted LeaveRequest", instance)
