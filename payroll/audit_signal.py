from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import (
    EmployeeProfile,
    Payroll,
    PayVar,
    PayT,
    PerformanceReview,
    IOU,
    LeaveRequest,
)
from .models.utils import AuditTrail

# from django.contrib.contenttypes.models import ContentType


def log_audit(user, action, instance):
    AuditTrail.objects.create(
        user=user,
        action=action,
        content_object=instance,
    )


@receiver(post_save, sender=EmployeeProfile)
def log_employee_save(sender, instance, created, **kwargs):
    action = "Created" if created else "Updated"
    log_audit(instance.user, f"{action} EmployeeProfile", instance)


@receiver(post_delete, sender=EmployeeProfile)
def log_employee_delete(sender, instance, **kwargs):
    log_audit(instance.user, "Deleted EmployeeProfile", instance)


@receiver(post_save, sender=Payroll)
def log_payroll_save(sender, instance, created, **kwargs):
    log_audit(None, "Created Payroll" if created else "Updated Payroll", instance)


@receiver(post_delete, sender=Payroll)
def log_payroll_delete(sender, instance, **kwargs):
    log_audit(None, "Deleted Payroll", instance)


@receiver(post_save, sender=PayVar)
def log_payvar_save(sender, instance, created, **kwargs):
    log_audit(None, "Created PayVar" if created else "Updated PayVar", instance)


@receiver(post_delete, sender=PayVar)
def log_payvar_delete(sender, instance, **kwargs):
    log_audit(None, "Deleted PayVar", instance)


@receiver(post_save, sender=PayT)
def log_payt_save(sender, instance, created, **kwargs):
    log_audit(None, "Created PayT" if created else "Updated PayT", instance)


@receiver(post_delete, sender=PayT)
def log_payt_delete(sender, instance, **kwargs):
    log_audit(None, "Deleted PayT", instance)


@receiver(post_save, sender=PerformanceReview)
def log_review_save(sender, instance, created, **kwargs):
    log_audit(
        instance.employee.user,
        "Created PerformanceReview" if created else "Updated PerformanceReview",
        instance,
    )


@receiver(post_delete, sender=PerformanceReview)
def log_review_delete(sender, instance, **kwargs):
    log_audit(instance.employee.user, "Deleted PerformanceReview", instance)


@receiver(post_save, sender=IOU)
def log_iou_save(sender, instance, created, **kwargs):
    log_audit(
        instance.employee_id.user, "Created IOU" if created else "Updated IOU", instance
    )


@receiver(post_delete, sender=IOU)
def log_iou_delete(sender, instance, **kwargs):
    log_audit(instance.employee_id.user, "Deleted IOU", instance)


@receiver(post_save, sender=LeaveRequest)
def log_leave_save(sender, instance, created, **kwargs):
    log_audit(
        instance.employee.user,
        "Created LeaveRequest" if created else "Updated LeaveRequest",
        instance,
    )


@receiver(post_delete, sender=LeaveRequest)
def log_leave_delete(sender, instance, **kwargs):
    log_audit(instance.employee.user, "Deleted LeaveRequest", instance)
