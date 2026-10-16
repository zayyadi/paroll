"""Payroll authorization binds the reviewed salary run, bank file and salary terms."""
from __future__ import annotations
import hashlib
from decimal import Decimal
from typing import Any
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from approvals.registry import ApprovalAction, register_action
from approvals.services import current_execution, execution_authorized, request_or_decide, submit_approval
from approvals.proposals import proposal_operation, encode_value
from payroll import models


def run_snapshot(source: Any) -> dict:
    """Bind the reviewed month to its actual payment and deduction inputs."""
    from calendar import monthrange
    from datetime import date
    from django.db import transaction
    from django.db.models import Q
    from django.contrib.contenttypes.models import ContentType
    from accounting.models import Journal

    atomic = transaction.get_connection().in_atomic_block
    if atomic:
        type(source.company)._base_manager.select_for_update().get(pk=source.company_id)
    month = source.paydays.month
    year = source.paydays.year
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    def records(queryset: Any) -> list[Any]:
        if atomic:
            queryset = queryset.select_for_update(of=("self",))
        return list(queryset.order_by("pk"))

    def fields(record: Any) -> dict:
        return {
            field.attname: getattr(record, field.attname)
            for field in record._meta.concrete_fields
        }

    settings = records(
        models.CompanyPayrollSetting.objects.filter(company=source.company)
    )
    rows = []
    for membership in records(source.payroll_run_entries.all()):
        entry = records(
            models.PayrollEntry.all_objects.filter(pk=membership.payroll_entry_id)
        )[0]
        employee = records(models.EmployeeProfile.all_objects.filter(pk=entry.pays_id))[
            0
        ]
        salary = (
            records(models.Payroll.objects.filter(pk=employee.employee_pay_id))[0]
            if employee.employee_pay_id
            else None
        )
        if salary:
            employee.employee_pay = salary
        entry.pays = employee
        allowances = records(
            employee.allowances.filter(
                Q(
                    source_leave_request__isnull=True,
                    created_at__month=month,
                    created_at__year=year,
                )
                | Q(
                    source_leave_request__isnull=False,
                    source_leave_request__start_date__lte=end,
                    source_leave_request__end_date__gte=start,
                )
            )
        )
        deductions = records(
            employee.deductions.filter(created_at__month=month, created_at__year=year)
        )
        leaves = records(
            employee.leave_requests.filter(
                status="APPROVED", start_date__lte=end, end_date__gte=start
            )
        )
        allowance_journals = records(
            Journal.objects.filter(
                company=source.company,
                content_type=ContentType.objects.get_for_model(models.Allowance),
                object_id__in=[allowance.pk for allowance in allowances],
                description__startswith="Leave allowance paid to",
            )
        )
        rows.append(
            {
                "entry_id": entry.pk,
                "employee_id": employee.pk,
                "employee_name": str(employee),
                "employee_number": employee.emp_id,
                "company_id": entry.company_id,
                "netpay": entry.netpay,
                "salary": fields(salary) if salary else None,
                "allowances": [fields(row) for row in allowances],
                "ordinary_deductions": [fields(row) for row in deductions],
                "approved_leave": [fields(row) for row in leaves],
                "paid_leave_journals": [
                    {
                        "id": journal.pk,
                        "allowance_id": journal.object_id,
                        "status": journal.status,
                        "entries": list(
                            journal.entries.order_by("pk").values(
                                "account_id", "entry_type", "amount"
                            )
                        ),
                    }
                    for journal in allowance_journals
                ],
                "computed_netpay": entry.get_netpay.quantize(Decimal(".01")),
                "deductions": [
                    {
                        "iou_id": deduction.iou_id,
                        "amount": deduction.amount,
                        "outstanding": deduction.iou.outstanding_amount,
                        "loan_status": deduction.iou.status,
                    }
                    for deduction in records(
                        employee.iou_deductions.filter(payday=source).select_related(
                            "iou"
                        )
                    )
                ],
            }
        )
    return {
        "id": source.pk,
        "company_id": source.company_id,
        "name": source.name,
        "period": str(source.paydays),
        "requested_by_id": source.requested_by_id,
        "currency": source.currency,
        "company_payroll_settings": [fields(row) for row in settings],
        "entries": rows,
    }

def validate_run(source: Any,payload: dict) -> None:
    if source.currency != 'NGN':
        raise ValidationError('Current payroll calculations and NIP instructions require NGN.')
    if source.closed or source.status in (source.Status.LOCKED,source.Status.PAID):
        raise ValidationError('This payroll run is already locked or paid.')
    if not source.payroll_run_entries.exists():
        raise ValidationError('A payroll run needs employees before approval.')
    if any(deduction.amount > deduction.iou.outstanding_amount for deduction in models.IOUDeduction.objects.filter(payday=source).select_related('iou')):
        raise ValidationError('Planned deductions exceed the actual outstanding loan balance.')
    if any(row['company_id'] != source.company_id or row['netpay'] < 0 or not row['salary'] for row in run_snapshot(source)['entries']):
        raise ValidationError('Review employee ownership, salary configuration and net pay before approval.')


def apply_run(source: Any,actor: Any,payload: dict) -> None:
    validate_run(source,payload)
    source.status=source.Status.APPROVED
    source.closed=False
    source.save(update_fields=['status','closed'])
    source.lock()
    # Repayment is finalized only once the approved run has posted successfully.
    iou_ids=source.iou_deductions.values_list('iou_id',flat=True) if hasattr(source,'iou_deductions') else models.IOUDeduction.objects.filter(payday=source).values_list('iou_id',flat=True)
    for iou in models.IOU.objects.filter(pk__in=iou_ids,status='APPROVED',payment_method='SALARY_DEDUCTION'):
        from django.db.models import Q
        finalized=iou.deductions.filter(Q(payday__closed=True)|Q(payday__status__in=['locked','paid'])).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        if finalized >= iou.total_amount:
            iou.status='PAID'
            iou.save(update_fields=['status'])

register_action(ApprovalAction(key='payroll.lock',model_label='payroll.PayrollRun',permission='payroll.change_payrollrun',
    apply=apply_run,snapshot=run_snapshot,validate=validate_run,requester=lambda source:source.requested_by,
    amount=lambda source,payload:source.payroll_run_entries.aggregate(total=Sum('payroll_entry__netpay'))['total'],
    beneficiaries=lambda source:source.payroll_run_entries.values_list('payroll_entry__pays__user_id',flat=True)))


def request_payroll_lock(source: Any, actor: Any) -> Any:
    from approvals.models import ApprovalRequest
    from approvals.permissions import require_company_authority
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    require_company_authority(actor, source.company, "payroll.change_payrollrun")
    with transaction.atomic():
        source = models.PayrollRun.all_objects.select_for_update().get(pk=source.pk)
        pending = ApprovalRequest.objects.filter(
            action="payroll.lock",
            content_type=ContentType.objects.get_for_model(source),
            object_id=source.pk,
            status="PENDING",
        ).first()
        if pending is not None:
            return request_or_decide(source=source, action="payroll.lock", actor=actor)
        if source.is_locked:
            raise ValidationError("This payroll run is already finalized.")
        # Recalculate before creating the reviewed snapshot, never while deciding.
        run_snapshot(source)
        for membership in source.payroll_run_entries.select_related(
            "payroll_entry"
        ).order_by("pk"):
            membership.payroll_entry.save(update_fields=["netpay"])
        maker = source.requested_by or actor
        return submit_approval(source=source, action="payroll.lock", requester=maker)

def bank_snapshot(source: Any) -> dict:
    import csv
    from io import StringIO
    from approvals.models import ApprovalRequest
    from django.contrib.contenttypes.models import ContentType
    with source.file.open('rb') as exported:
        content = exported.read()
    digest = hashlib.sha256(content).hexdigest()
    recipients = [{'account_number': row[0], 'employee_name': row[1], 'bank_code':row[2],
                   'amount':row[3], 'narration':row[4]} for row in list(csv.reader(StringIO(content.decode('utf-8'))))[4:]]
    completed = ApprovalRequest.objects.filter(company=source.company, action='payroll.lock',
        content_type=ContentType.objects.get_for_model(source.payroll_run), object_id=source.payroll_run_id,
        status='APPROVED').order_by('-pk').first()
    payroll = completed.execution_snapshot if completed and completed.execution_snapshot else run_snapshot(source.payroll_run)
    return {'id':source.pk,'company_id':source.company_id,'run_id':source.payroll_run_id,'bank_code':source.bank_code,
            'file_hash':digest,'amount':source.total_amount,'records':source.total_records,'created_by_id':source.created_by_id,
            'recipients':recipients, 'beneficiary_ids':list(source.payroll_run.payroll_run_entries.values_list('payroll_entry__pays__user_id',flat=True)),
            'payroll':payroll}


def validate_bank(source: Any,payload: dict) -> None:
    from payroll.services.bank_payment_service import _validate_file
    if source.status != 'GENERATED':
        raise ValidationError('Only generated bank instructions may be submitted for approval.')
    if not str(payload.get('reference_number','')).strip():
        raise ValidationError('A bank submission reference is required.')
    _validate_file(source,source.payroll_run)


def apply_bank(source: Any,actor: Any,payload: dict) -> None:
    from payroll.services.bank_payment_service import mark_submitted
    mark_submitted(payment_file=source,reference_number=payload['reference_number'])

register_action(ApprovalAction(key='bank_payment.submit',model_label='payroll.BankPaymentFile',permission='payroll.change_payrollrun',
    apply=apply_bank,snapshot=bank_snapshot,validate=validate_bank,requester=lambda source:source.created_by,
    amount=lambda source,payload:source.total_amount,
    beneficiaries=lambda source:source.payroll_run.payroll_run_entries.values_list('payroll_entry__pays__user_id',flat=True)))


@proposal_operation('salary.change','payroll.change_payroll')
def change_salary(*,employee: Any,basic_salary: Decimal,user: Any=None,effective_date: Any=None, salary_options: dict | None=None) -> Any:
    if basic_salary <= 0:
        raise ValidationError('Salary must be positive.')
    if effective_date and effective_date > timezone.localdate():
        raise ValidationError('Future salary changes need an effective-dated scheduling process.')
    old=employee.employee_pay
    values={f.name:getattr(old,f.attname) for f in models.Payroll._meta.concrete_fields
            if not f.primary_key and f.name not in {'company','created_at','updated_at','slug'}} if old else {}
    options = salary_options or {}
    if set(options) - {'is_housing', 'is_nhif', 'nhf_scheme'}:
        raise ValidationError('Unsupported salary options.')
    if any(type(options[name]) is not bool for name in ('is_housing', 'is_nhif') if name in options):
        raise ValidationError('Salary contribution options must be true or false.')
    if 'nhf_scheme' in options and options['nhf_scheme'] not in {'none', 'voluntary', 'compulsory'}:
        raise ValidationError('Unknown NHF contribution scheme.')
    values.update(options)
    if options.get('is_housing') is False and 'nhf_scheme' not in options:
        values['nhf_scheme'] = 'none'
    values['basic_salary']=basic_salary
    salary=models.Payroll.objects.create(company=employee.company,**values)
    employee.employee_pay=salary
    employee.save(update_fields=['employee_pay'])
    models.SalaryHistory.objects.update_or_create(employee=employee,salary_config=salary,effective_date=effective_date or timezone.localdate(),
        defaults={'changed_by':current_execution().requester,'approved_by':user,'note':'Approved salary-change workflow'})
    # A compensation-cycle review that submitted this change finalises its
    # bookkeeping (status -> APPLIED, cycle roll-up) now that the raise is real.
    from payroll.services.compensation_service import finalise_review_for_execution
    finalise_review_for_execution(current_execution())
    return salary


@proposal_operation('payroll.leave_allowance.backfill', 'accounting.change_journal')
def _apply_leave_allowance_backfill(*, leave_request: Any, employee: Any,
        payroll_setting: Any, amount: Decimal, queue_email: bool = True, user: Any = None) -> Any:
    from payroll.services.leave_allowance import calculate_leave_allowance_amount, process_leave_allowance_for_request
    if leave_request.status != 'APPROVED' or employee.pk != leave_request.employee_id or payroll_setting.company_id != employee.company_id:
        raise ValidationError('Backfill must reference the approved leave and its company employee and salary settings.')
    if calculate_leave_allowance_amount(leave_request) != amount:
        raise ValidationError('Leave allowance terms changed. Submit a new reviewed request.')
    return process_leave_allowance_for_request(leave_request, queue_email=queue_email)


def request_leave_allowance_backfill(*, leave_request: Any, actor: Any,
        queue_email: bool = True, approval_key: str | None = None) -> Any:
    from payroll.services.leave_allowance import calculate_leave_allowance_amount
    from approvals.permissions import require_company_authority
    require_company_authority(actor, leave_request.employee.company, 'accounting.change_journal')
    if leave_request.status != 'APPROVED':
        raise ValidationError('Only approved leave requests can have an allowance backfilled.')
    if models.Allowance.objects.filter(source_leave_request=leave_request).exists():
        return None
    amount = calculate_leave_allowance_amount(leave_request)
    if amount <= 0:
        return None
    setting = models.CompanyPayrollSetting.objects.get(company=leave_request.employee.company)
    return _apply_leave_allowance_backfill(leave_request=leave_request, employee=leave_request.employee,
        payroll_setting=setting, amount=amount, queue_email=queue_email, user=actor, approval_key=approval_key)
