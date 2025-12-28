"""
Comprehensive signal handlers for accounting audit trail integration.
This module captures all accounting operations and logs them to the audit trail.
"""

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from .utils import get_request_user, get_request_metadata

User = get_user_model()


def get_audit_user_and_metadata():
    """
    Helper function to get current user and request metadata.
    This works with the middleware to capture request context.
    """
    user = get_request_user()
    ip_address, user_agent = get_request_metadata()
    return user, ip_address, user_agent


def log_model_change(sender, instance, action, changes=None, reason=None):
    """
    Generic function to log model changes to audit trail.

    Args:
        sender: Model class
        instance: Model instance
        action: Action type (CREATE, UPDATE, DELETE)
        changes: Dictionary of changes made
        reason: Reason for the change
    """
    user, ip_address, user_agent = get_audit_user_and_metadata()

    def log_audit_trail():
        try:
            AccountingAuditTrail.log_action(
                user=user,
                action=action,
                instance=instance,
                changes=changes or {},
                reason=reason or f"{action} operation on {sender.__name__}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            # Silently fail to avoid breaking the main application
            # In production, this should be logged to error monitoring
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_audit_trail)
        else:
            # Not in an atomic block, create directly
            log_audit_trail()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_audit_trail()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_audit_trail()


def get_field_changes(old_instance, new_instance):
    """
    Compare two model instances and return field changes.

    Args:
        old_instance: Original model instance
        new_instance: Updated model instance

    Returns:
        Dictionary of field changes
    """
    changes = {}
    for field in new_instance._meta.fields:
        field_name = field.name
        if field_name not in ["id", "created_at", "updated_at"]:
            old_value = getattr(old_instance, field_name)
            new_value = getattr(new_instance, field_name)
            if old_value != new_value:
                changes[field_name] = {
                    "old": str(old_value) if old_value is not None else None,
                    "new": str(new_value) if new_value is not None else None,
                }
    return changes


# Account signal handlers
@receiver(pre_save, sender=Account)
def account_pre_save(sender, instance, **kwargs):
    """Track account changes before save."""
    if instance.pk:
        try:
            old_instance = Account.objects.get(pk=instance.pk)
            instance._audit_changes = get_field_changes(old_instance, instance)
        except Account.DoesNotExist:
            instance._audit_changes = {}
    else:
        instance._audit_changes = {}


@receiver(post_save, sender=Account)
def account_post_save(sender, instance, created, **kwargs):
    """Log account creation and updates."""

    def log_account_change():
        if created:
            log_model_change(
                sender=sender,
                instance=instance,
                action=AccountingAuditTrail.ActionType.CREATE,
                reason=f"Created account: {instance.name} ({instance.account_number})",
            )
        else:
            changes = getattr(instance, "_audit_changes", {})
            if changes:
                log_model_change(
                    sender=sender,
                    instance=instance,
                    action=AccountingAuditTrail.ActionType.UPDATE,
                    changes=changes,
                    reason=f"Updated account: {instance.name} ({instance.account_number})",
                )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_account_change)
        else:
            # Not in an atomic block, create directly
            log_account_change()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_account_change()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_account_change()


@receiver(post_delete, sender=Account)
def account_post_delete(sender, instance, **kwargs):
    """Log account deletion."""

    def log_account_delete():
        log_model_change(
            sender=sender,
            instance=instance,
            action=AccountingAuditTrail.ActionType.DELETE,
            reason=f"Deleted account: {instance.name} ({instance.account_number})",
        )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_account_delete)
        else:
            # Not in an atomic block, create directly
            log_account_delete()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_account_delete()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_account_delete()


# Fiscal Year signal handlers
@receiver(pre_save, sender=FiscalYear)
def fiscal_year_pre_save(sender, instance, **kwargs):
    """Track fiscal year changes before save."""
    if instance.pk:
        try:
            old_instance = FiscalYear.objects.get(pk=instance.pk)
            instance._audit_changes = get_field_changes(old_instance, instance)
        except FiscalYear.DoesNotExist:
            instance._audit_changes = {}
    else:
        instance._audit_changes = {}


@receiver(post_save, sender=FiscalYear)
def fiscal_year_post_save(sender, instance, created, **kwargs):
    """Log fiscal year creation and updates."""

    def log_fiscal_year_change():
        if created:
            log_model_change(
                sender=sender,
                instance=instance,
                action=AccountingAuditTrail.ActionType.CREATE,
                reason=f"Created fiscal year: {instance.name} ({instance.year})",
            )
        else:
            changes = getattr(instance, "_audit_changes", {})
            if changes:
                # Check if fiscal year is being closed
                if "is_closed" in changes and changes["is_closed"]["new"] is True:
                    log_model_change(
                        sender=sender,
                        instance=instance,
                        action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
                        changes=changes,
                        reason=f"Closed fiscal year: {instance.name} ({instance.year})",
                    )
                else:
                    log_model_change(
                        sender=sender,
                        instance=instance,
                        action=AccountingAuditTrail.ActionType.UPDATE,
                        changes=changes,
                        reason=f"Updated fiscal year: {instance.name} ({instance.year})",
                    )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_fiscal_year_change)
        else:
            # Not in an atomic block, create directly
            log_fiscal_year_change()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_fiscal_year_change()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_fiscal_year_change()


@receiver(post_delete, sender=FiscalYear)
def fiscal_year_post_delete(sender, instance, **kwargs):
    """Log fiscal year deletion."""

    def log_fiscal_year_delete():
        log_model_change(
            sender=sender,
            instance=instance,
            action=AccountingAuditTrail.ActionType.DELETE,
            reason=f"Deleted fiscal year: {instance.name} ({instance.year})",
        )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_fiscal_year_delete)
        else:
            # Not in an atomic block, create directly
            log_fiscal_year_delete()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_fiscal_year_delete()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_fiscal_year_delete()


# Accounting Period signal handlers
@receiver(pre_save, sender=AccountingPeriod)
def accounting_period_pre_save(sender, instance, **kwargs):
    """Track accounting period changes before save."""
    if instance.pk:
        try:
            old_instance = AccountingPeriod.objects.get(pk=instance.pk)
            instance._audit_changes = get_field_changes(old_instance, instance)
        except AccountingPeriod.DoesNotExist:
            instance._audit_changes = {}
    else:
        instance._audit_changes = {}


@receiver(post_save, sender=AccountingPeriod)
def accounting_period_post_save(sender, instance, created, **kwargs):
    """Log accounting period creation and updates."""

    def log_period_change():
        if created:
            log_model_change(
                sender=sender,
                instance=instance,
                action=AccountingAuditTrail.ActionType.CREATE,
                reason=f"Created accounting period: {instance.name} ({instance.fiscal_year.name})",
            )
        else:
            changes = getattr(instance, "_audit_changes", {})
            if changes:
                # Check if period is being closed
                if "is_closed" in changes and changes["is_closed"]["new"] is True:
                    log_model_change(
                        sender=sender,
                        instance=instance,
                        action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
                        changes=changes,
                        reason=f"Closed accounting period: {instance.name} ({instance.fiscal_year.name})",
                    )
                else:
                    log_model_change(
                        sender=sender,
                        instance=instance,
                        action=AccountingAuditTrail.ActionType.UPDATE,
                        changes=changes,
                        reason=f"Updated accounting period: {instance.name} ({instance.fiscal_year.name})",
                    )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_period_change)
        else:
            # Not in an atomic block, create directly
            log_period_change()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_period_change()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_period_change()


@receiver(post_delete, sender=AccountingPeriod)
def accounting_period_post_delete(sender, instance, **kwargs):
    """Log accounting period deletion."""

    def log_period_delete():
        log_model_change(
            sender=sender,
            instance=instance,
            action=AccountingAuditTrail.ActionType.DELETE,
            reason=f"Deleted accounting period: {instance.name} ({instance.fiscal_year.name})",
        )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_period_delete)
        else:
            # Not in an atomic block, create directly
            log_period_delete()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_period_delete()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_period_delete()


# Journal signal handlers
@receiver(pre_save, sender=Journal)
def journal_pre_save(sender, instance, **kwargs):
    """Track journal changes before save."""
    if instance.pk:
        try:
            old_instance = Journal.objects.get(pk=instance.pk)
            instance._audit_changes = get_field_changes(old_instance, instance)
        except Journal.DoesNotExist:
            instance._audit_changes = {}
    else:
        instance._audit_changes = {}


@receiver(post_save, sender=Journal)
def journal_post_save(sender, instance, created, **kwargs):
    """Log journal creation and updates."""

    # Use transaction.on_commit to avoid transaction issues
    def log_journal_change():
        if created:
            log_model_change(
                sender=sender,
                instance=instance,
                action=AccountingAuditTrail.ActionType.CREATE,
                reason=f"Created journal: {instance.transaction_number} - {instance.description}",
            )
        else:
            changes = getattr(instance, "_audit_changes", {})
            if changes:
                # Check for specific status changes
                if "status" in changes:
                    old_status = changes["status"]["old"]
                    new_status = changes["status"]["new"]

                    if old_status != new_status:
                        if new_status == Journal.JournalStatus.APPROVED:
                            log_model_change(
                                sender=sender,
                                instance=instance,
                                action=AccountingAuditTrail.ActionType.APPROVE,
                                changes=changes,
                                reason=f"Approved journal: {instance.transaction_number}",
                            )
                        elif new_status == Journal.JournalStatus.POSTED:
                            log_model_change(
                                sender=sender,
                                instance=instance,
                                action=AccountingAuditTrail.ActionType.POST,
                                changes=changes,
                                reason=f"Posted journal: {instance.transaction_number}",
                            )
                        elif new_status == Journal.JournalStatus.REVERSED:
                            log_model_change(
                                sender=sender,
                                instance=instance,
                                action=AccountingAuditTrail.ActionType.REVERSE,
                                changes=changes,
                                reason=f"Reversed journal: {instance.transaction_number}",
                            )
                        else:
                            log_model_change(
                                sender=sender,
                                instance=instance,
                                action=AccountingAuditTrail.ActionType.UPDATE,
                                changes=changes,
                                reason=f"Updated journal status: {instance.transaction_number} - {old_status} to {new_status}",
                            )
                else:
                    log_model_change(
                        sender=sender,
                        instance=instance,
                        action=AccountingAuditTrail.ActionType.UPDATE,
                        changes=changes,
                        reason=f"Updated journal: {instance.transaction_number} - {instance.description}",
                    )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_journal_change)
        else:
            # Not in an atomic block, create directly
            log_journal_change()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_journal_change()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_journal_change()


@receiver(post_delete, sender=Journal)
def journal_post_delete(sender, instance, **kwargs):
    """Log journal deletion."""

    # Use transaction.on_commit to avoid transaction issues
    def log_journal_delete():
        log_model_change(
            sender=sender,
            instance=instance,
            action=AccountingAuditTrail.ActionType.DELETE,
            reason=f"Deleted journal: {instance.transaction_number} - {instance.description}",
        )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_journal_delete)
        else:
            # Not in an atomic block, create directly
            log_journal_delete()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_journal_delete()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_journal_delete()


# Journal Entry signal handlers
@receiver(pre_save, sender=JournalEntry)
def journal_entry_pre_save(sender, instance, **kwargs):
    """Track journal entry changes before save."""
    if instance.pk:
        try:
            old_instance = JournalEntry.objects.get(pk=instance.pk)
            instance._audit_changes = get_field_changes(old_instance, instance)
        except JournalEntry.DoesNotExist:
            instance._audit_changes = {}
    else:
        instance._audit_changes = {}


@receiver(post_save, sender=JournalEntry)
def journal_entry_post_save(sender, instance, created, **kwargs):
    """Log journal entry creation and updates."""

    # Use transaction.on_commit to avoid transaction issues
    def log_entry_change():
        if created:
            log_model_change(
                sender=sender,
                instance=instance,
                action=AccountingAuditTrail.ActionType.CREATE,
                reason=f"Created journal entry: {instance.get_entry_type_display()} {instance.amount} to {instance.account.name}",
            )
        else:
            changes = getattr(instance, "_audit_changes", {})
            if changes:
                log_model_change(
                    sender=sender,
                    instance=instance,
                    action=AccountingAuditTrail.ActionType.UPDATE,
                    changes=changes,
                    reason=f"Updated journal entry: {instance.get_entry_type_display()} {instance.amount} to {instance.account.name}",
                )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_entry_change)
        else:
            # Not in an atomic block, create directly
            log_entry_change()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_entry_change()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_entry_change()


@receiver(post_delete, sender=JournalEntry)
def journal_entry_post_delete(sender, instance, **kwargs):
    """Log journal entry deletion."""

    # Use transaction.on_commit to avoid transaction issues
    def log_entry_delete():
        log_model_change(
            sender=sender,
            instance=instance,
            action=AccountingAuditTrail.ActionType.DELETE,
            reason=f"Deleted journal entry: {instance.get_entry_type_display()} {instance.amount} to {instance.account.name}",
        )

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_entry_delete)
        else:
            # Not in an atomic block, create directly
            log_entry_delete()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_entry_delete()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_entry_delete()


# Custom signal handlers for specific accounting operations
def log_journal_approval(journal, user, reason=None):
    """
    Log journal approval operation.

    Args:
        journal: Journal instance being approved
        user: User approving the journal
        reason: Reason for approval
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_approval():
        try:
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.APPROVE,
                instance=journal,
                reason=reason or f"Journal {journal.transaction_number} approved",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_approval)
        else:
            # Not in an atomic block, create directly
            log_approval()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_approval()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_approval()


def log_journal_posting(journal, user, reason=None):
    """
    Log journal posting operation.

    Args:
        journal: Journal instance being posted
        user: User posting the journal
        reason: Reason for posting
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_posting():
        try:
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.POST,
                instance=journal,
                reason=reason or f"Journal {journal.transaction_number} posted",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_posting)
        else:
            # Not in an atomic block, create directly
            log_posting()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_posting()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_posting()


def log_journal_reversal(journal, reversal_journal, user, reason):
    """
    Log journal reversal operation.

    Args:
        journal: Original journal being reversed
        reversal_journal: New reversal journal
        user: User performing the reversal
        reason: Reason for reversal
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_reversal():
        try:
            # Log the reversal action on the original journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.REVERSE,
                instance=journal,
                changes={
                    "reversal_reason": reason,
                    "reversal_journal_id": reversal_journal.pk,
                    "reversal_transaction_number": reversal_journal.transaction_number,
                },
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Log the creation of the reversal journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.CREATE,
                instance=reversal_journal,
                reason=f"Reversal journal created for {journal.transaction_number}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_reversal)
        else:
            # Not in an atomic block, create directly
            log_reversal()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_reversal()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_reversal()


def log_period_closure(period, user, reason=None):
    """
    Log accounting period closure operation.

    Args:
        period: AccountingPeriod being closed
        user: User closing the period
        reason: Reason for closure
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_closure():
        try:
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
                instance=period,
                reason=reason or f"Accounting period {period.name} closed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_closure)
        else:
            # Not in an atomic block, create directly
            log_closure()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_closure()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_closure()


def log_fiscal_year_closure(fiscal_year, user, reason=None):
    """
    Log fiscal year closure operation.

    Args:
        fiscal_year: FiscalYear being closed
        user: User closing the fiscal year
        reason: Reason for closure
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_closure():
        try:
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
                instance=fiscal_year,
                reason=reason or f"Fiscal year {fiscal_year.name} closed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_closure)
        else:
            # Not in an atomic block, create directly
            log_closure()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_closure()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_closure()


def log_partial_journal_reversal(
    journal, reversal_journal, user, reason, entry_ids=None, amounts=None
):
    """
    Log partial journal reversal operation.

    Args:
        journal: Original journal being partially reversed
        reversal_journal: New partial reversal journal
        user: User performing reversal
        reason: Reason for reversal
        entry_ids: List of entry IDs that were reversed
        amounts: Dictionary of entry_id -> amount reversed
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_partial_reversal():
        try:
            # Log the partial reversal action on original journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.REVERSE,
                instance=journal,
                changes={
                    "reversal_type": "partial",
                    "reversal_reason": reason,
                    "reversal_journal_id": reversal_journal.pk,
                    "reversal_transaction_number": reversal_journal.transaction_number,
                    "reversed_entries": entry_ids or [],
                    "reversal_amounts": amounts or {},
                },
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Log the creation of partial reversal journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.CREATE,
                instance=reversal_journal,
                reason=f"Partial reversal journal created for {journal.transaction_number}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_partial_reversal)
        else:
            # Not in an atomic block, create directly
            log_partial_reversal()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_partial_reversal()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_partial_reversal()


def log_journal_reversal_with_correction(
    journal, reversal_journal, correction_journal, user, reason
):
    """
    Log journal reversal with correction operation.

    Args:
        journal: Original journal being reversed
        reversal_journal: New reversal journal
        correction_journal: New correction journal
        user: User performing reversal with correction
        reason: Reason for reversal with correction
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_reversal_with_correction():
        try:
            # Log the reversal with correction action on original journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.REVERSE,
                instance=journal,
                changes={
                    "reversal_type": "reversal_with_correction",
                    "reversal_reason": reason,
                    "reversal_journal_id": reversal_journal.pk,
                    "reversal_transaction_number": reversal_journal.transaction_number,
                    "correction_journal_id": correction_journal.pk,
                    "correction_transaction_number": correction_journal.transaction_number,
                },
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Log the creation of reversal journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.CREATE,
                instance=reversal_journal,
                reason=f"Reversal journal created for {journal.transaction_number}",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Log the creation of correction journal
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.CREATE,
                instance=correction_journal,
                reason=f"Correction journal created for {journal.transaction_number}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_reversal_with_correction)
        else:
            # Not in an atomic block, create directly
            log_reversal_with_correction()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_reversal_with_correction()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_reversal_with_correction()


def log_batch_journal_reversal(
    journals, reversal_journals, user, reason, failed_journals=None
):
    """
    Log batch journal reversal operation.

    Args:
        journals: List of original journals being reversed
        reversal_journals: List of new reversal journals
        user: User performing batch reversal
        reason: Reason for batch reversal
        failed_journals: List of journals that failed to reverse
    """
    _, ip_address, user_agent = get_audit_user_and_metadata()

    def log_batch_reversal():
        try:
            # Log the batch reversal operation
            AccountingAuditTrail.log_action(
                user=user,
                action=AccountingAuditTrail.ActionType.REVERSE,
                instance=None,  # No specific instance for batch operation
                changes={
                    "operation_type": "batch_reversal",
                    "reversal_reason": reason,
                    "reversed_journals": [
                        {
                            "original_journal_id": journal.pk,
                            "original_transaction_number": journal.transaction_number,
                            "reversal_journal_id": reversal_journal.pk,
                            "reversal_transaction_number": reversal_journal.transaction_number,
                        }
                        for journal, reversal_journal in zip(
                            journals, reversal_journals
                        )
                    ],
                    "failed_journals": [
                        {
                            "journal_id": failed["journal"].pk,
                            "transaction_number": failed["journal"].transaction_number,
                            "error": failed["error"],
                        }
                        for failed in (failed_journals or [])
                    ],
                },
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Log the creation of each reversal journal
            for reversal_journal in reversal_journals:
                AccountingAuditTrail.log_action(
                    user=user,
                    action=AccountingAuditTrail.ActionType.CREATE,
                    instance=reversal_journal,
                    reason=f"Batch reversal journal created",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
        except Exception:
            pass

    # Check if we're in an atomic block and if transaction is in a good state
    try:
        # Try to use on_commit if we're in a working transaction
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(log_batch_reversal)
        else:
            # Not in an atomic block, create directly
            log_batch_reversal()
    except Exception:
        # If transaction is broken or on_commit fails, try to create directly
        # This handles case where we're in a broken transaction state
        try:
            # Use a separate transaction to avoid broken one
            with transaction.atomic(using=None, savepoint=False):
                log_batch_reversal()
        except Exception:
            # As a last resort, try without any transaction wrapper
            # This ensures audit logging doesn't break the main application
            log_batch_reversal()
