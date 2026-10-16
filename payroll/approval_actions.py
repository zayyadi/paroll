"""HR action adapters: effects run only inside a final approved transaction."""
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from approvals.registry import ApprovalAction, register_action

def beneficiary(source):
    employee = getattr(source, "employee", None) or getattr(source, "employee_id", None)
    return [employee.user_id] if employee and employee.user_id else []

def candidate_beneficiaries(source):
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from company.models import CompanyMembership
    from payroll.models import EmployeeProfile
    candidate = getattr(source, "candidate", source)
    email = (candidate.email or "").strip()
    if not email:
        return []
    members = CompanyMembership.objects.filter(company=candidate.company).values_list("user_id", flat=True)
    users = get_user_model().objects.filter(email__iexact=email).filter(Q(company=candidate.company) | Q(pk__in=members)).values_list("pk", flat=True)
    profile_users = EmployeeProfile.objects.filter(company=candidate.company, email__iexact=email, user__isnull=False).values_list("user_id", flat=True)
    return sorted(set(users) | set(profile_users))

def employee_maker(source):
    if getattr(source, "requested_by_id", None):
        return source.requested_by
    employee = getattr(source, "employee", None) or getattr(source, "employee_id", None)
    return employee.user if employee else None

def pending(source, payload):
    if source.status != "PENDING":
        raise ValidationError("Only pending requests can be approved.")

def leave_snapshot(source):
    from payroll.models import EmployeeProfile, Payroll, CompanyPayrollSetting
    company = source.employee.company
    type(company)._base_manager.select_for_update().get(pk=company.pk)
    employee = EmployeeProfile._base_manager.select_for_update().get(pk=source.employee_id)
    salary = Payroll._base_manager.select_for_update().filter(pk=employee.employee_pay_id).first()
    employee.employee_pay = salary
    source.employee = employee
    setting, _ = CompanyPayrollSetting.objects.get_or_create(company=company)
    setting = CompanyPayrollSetting.objects.select_for_update().get(pk=setting.pk)
    data = {field.attname:getattr(source, field.attname) for field in source._meta.concrete_fields}
    data.update(employee_name=str(employee), employee_company_id=employee.company_id,
        monthly_basic_salary=salary.basic_salary if salary else None,
        leave_allowance_percentage=setting.leave_allowance_percentage)
    return data


def leave_amount(source, payload):
    from payroll.services.leave_allowance import calculate_leave_allowance_amount
    return calculate_leave_allowance_amount(source)


def apply_leave(source, actor, payload):
    source.status = "APPROVED"
    source.approved_by = actor
    source.save(user=actor)

def validate_timesheet(source, payload):
    """Only a submitted timesheet can be approved (P2-14)."""
    if source.status != "submitted":
        raise ValidationError("Only a submitted timesheet can be approved.")
    if source.employee.company_id != source.company_id:
        raise ValidationError("Timesheet employee must belong to the timesheet company.")

def apply_timesheet(source, actor, payload):
    """Certify the week's hours so they become payable.

    This is the moment raw clock data becomes approved hours: the timesheet
    flips to ``approved`` and ``is_payable`` turns true, which the payroll
    pre-flight check reads.
    """
    source.approve(actor)

def timesheet_snapshot(source):
    """The reviewable content of a timesheet.

    Deliberately excludes ``approval_request`` (the back-link written after
    submission) and auto-updated bookkeeping (``updated_at``, approval
    stamps): a snapshot hash mismatch would otherwise flag the timesheet as
    "changed after submission" for merely recording its own request.
    """
    return {
        "company_id": source.company_id,
        "employee_id": source.employee_id,
        "week_start": source.week_start.isoformat() if source.week_start else None,
        "total_hours": str(source.total_hours),
        "status": source.status,
        "submitted_by_id": source.submitted_by_id,
        "notes": source.notes,
    }


def reject_timesheet(source, actor, payload):
    if source.status == "submitted":
        source.status = "rejected"
        source.save(update_fields=["status"])


def validate_exit_settlement(source, payload):
    """Only a draft statement with a checklist behind it can be posted (P2-15)."""
    from payroll.models.workforce import ExitSettlement

    if source.status != ExitSettlement.Status.DRAFT:
        raise ValidationError("Only a draft exit settlement can be posted.")
    if source.checklist_id is None:
        raise ValidationError("An exit settlement needs its offboarding checklist.")
    if source.employee.company_id != source.company_id:
        raise ValidationError(
            "Settlement employee must belong to the settlement company."
        )


def apply_exit_settlement(source, actor, payload):
    """Post the settlement: write the journal and flip the statement to POSTED."""
    from payroll.services.exit_settlement_service import post_settlement

    post_settlement(settlement=source, actor=actor)


def validate_iou(source, payload):
    pending(source, payload)
    source.full_clean()

def apply_iou(source, actor, payload):
    allowed = {"tenor", "repayment_deduction_percentage", "interest_rate", "payment_method"}
    if set(payload) - allowed:
        raise ValidationError("Unsupported IOU approval terms.")
    for name, value in payload.items():
        setattr(source, name, value)
    source.status = "APPROVED"
    source.approved_at = timezone.localdate()
    source.due_date = None
    source.full_clean()
    source.save()

def validate_settlement(source, payload):
    if source.status != "APPROVED":
        raise ValidationError("Only an approved IOU may be settled.")
    method = payload.get("payment_method", source.payment_method)
    if method == "DIRECT_PAYMENT":
        if source.deductions.exists():
            raise ValidationError("Mixed payroll and direct repayment requires reconciliation before settlement.")
        try:
            amount_received = Decimal(str(payload.get("amount_received", "")))
        except InvalidOperation:
            raise ValidationError("The received repayment amount is required.")
        if not amount_received.is_finite() or amount_received != source.total_amount:
            raise ValidationError("The reviewed receipt must cover the full principal and interest.")
        if not str(payload.get("receipt_reference", "")).strip():
            raise ValidationError("A repayment receipt reference is required.")
    elif method == "SALARY_DEDUCTION":
        from django.db.models import Q, Sum
        repaid = (source.deductions.filter(Q(payday__closed=True) | Q(payday__status__in=["locked", "paid"]))
                  .aggregate(total=Sum("amount"))["total"] or 0)
        if repaid < source.total_amount:
            raise ValidationError("Only finalized payroll repayments can settle this IOU.")
    else:
        raise ValidationError("Unsupported repayment method.")

def apply_settlement(source, actor, payload):
    source.status = "PAID"
    source.payment_method = payload.get("payment_method", source.payment_method)
    source.save(update_fields=["status", "payment_method"])

def validate_overtime(source, payload):
    pending(source, payload)
    if source.employee.company_id != source.company_id:
        raise ValidationError("Overtime employee must belong to the request company.")
    if source.hours <= 0 or source.rate_multiplier <= 0:
        raise ValidationError("Overtime hours and rate must be positive.")
    if source.attendance and (source.attendance.company_id != source.company_id or source.attendance.employee_id != source.employee_id):
        raise ValidationError("Overtime attendance must belong to the same employee and company.")

def apply_overtime(source, actor, payload):
    source.status = "APPROVED"
    source.approved_by = actor
    source.approved_at = timezone.now()
    source.save(update_fields=["status", "approved_by", "approved_at"])

def move_snapshot(source):
    data = {field.attname: getattr(source, field.attname) for field in source._meta.concrete_fields}
    employee = source.employee
    data["employee_state"] = {"department": employee.department_id, "title": employee.job_title,
                              "salary": employee.employee_pay_id, "company": employee.company_id}
    salary = getattr(source, "new_salary_config", None)
    if salary:
        salary.refresh_from_db()
        data["salary_terms"] = {field.attname: getattr(salary, field.attname) for field in salary._meta.concrete_fields}
    return data

def hiring_snapshot(source):
    data = {field.attname: getattr(source, field.attname) for field in source._meta.concrete_fields}
    data["scorecards"] = list(source.scorecards.order_by("pk").values("pk", "stage_id", "competency_scores", "average_score", "recommendation", "notes"))
    from payroll.models import HiringStage
    data["stages"] = list(HiringStage.objects.filter(company=source.company).order_by("pk").values("pk", "stage_type", "requires_approval", "requires_scorecard", "is_active"))
    return data

def validate_move(source, payload):
    pending(source, payload)
    if source.employee.company_id != source.company_id:
        raise ValidationError("Employee must belong to the request company.")
    department = getattr(source, "to_department", None)
    salary = getattr(source, "new_salary_config", None)
    for target in (department, salary):
        if target and target.company_id != source.company_id:
            raise ValidationError("The destination must belong to the request company.")

def apply_move(source, actor, payload):
    source.status = "APPROVED"
    source.approved_by = actor
    source.approved_at = timezone.now()
    source.save(update_fields=["status", "approved_by", "approved_at"])
    if source.effective_date <= timezone.localdate():
        from payroll.services.transfer_service import execute_transfer, execute_promotion
        executor = execute_transfer if source._meta.model_name == "employeetransfer" else execute_promotion
        executor(**{"transfer" if source._meta.model_name == "employeetransfer" else "promotion": source,
                    "performed_by": actor})

def validate_offboarding(source, payload):
    if source.status != "IN_PROGRESS" or source.tasks.filter(is_completed=False).exists():
        raise ValidationError("Complete all tasks before approving offboarding.")
    if source.last_working_day > timezone.localdate():
        raise ValidationError("Offboarding cannot be completed before the last working day.")

def offboarding_snapshot(source):
    return {"employee": source.employee_id, "last_working_day": str(source.last_working_day),
            "reason": source.reason, "status": source.status, "settlement": str(source.final_settlement_amount),
            "tasks": list(source.tasks.order_by("pk").values("pk", "is_completed", "notes"))}

def apply_offboarding(source, actor, payload):
    from payroll.services.offboarding_service import complete_offboarding
    complete_offboarding(checklist=source, actor=actor)

def validate_advance(source, payload):
    from payroll.models import HiringStage
    stage = HiringStage.objects.get(pk=payload.get("next_stage_id"), company=source.company, is_active=True)
    if stage.requires_scorecard and not source.scorecards.filter(stage=stage).exists():
        raise ValidationError("A structured scorecard is required.")

def apply_advance(source, actor, payload):
    from payroll.models import HiringStage
    from payroll.services.hiring import advance_candidate
    advance_candidate(source, HiringStage.objects.get(pk=payload["next_stage_id"]), advanced_by=actor)

def validate_offer(source, payload):
    if source.status != "draft" or source.salary_amount <= 0:
        raise ValidationError("Only a valid draft offer can be released.")
    if source.candidate.company_id != source.company_id:
        raise ValidationError("Candidate must belong to the offer company.")

def apply_offer(source, actor, payload):
    source.status = "sent"
    source.save(update_fields=["status", "updated_at"])
    source.candidate.status = "offer"
    source.candidate.save(update_fields=["status", "updated_at"])

def reject_hr(source, actor, payload):
    if hasattr(source, "status") and source.status == "PENDING":
        source.status = "REJECTED"
        if hasattr(source, "approved_by"):
            source.approved_by = actor
        if hasattr(source, "approved_at"):
            source.approved_at = timezone.localdate() if source._meta.model_name == "iou" else timezone.now()
        source.save()

for key, model, apply, validate, requester, beneficiaries in [
    ("leave.approve", "LeaveRequest", apply_leave, pending, employee_maker, beneficiary),
    ("iou.approve", "IOU", apply_iou, validate_iou, employee_maker, beneficiary),
    ("iou.settle", "IOU", apply_settlement, validate_settlement, None, beneficiary),
    ("overtime.approve", "OvertimeEntry", apply_overtime, validate_overtime, employee_maker, beneficiary),
    ("transfer.approve", "EmployeeTransfer", apply_move, validate_move, lambda s: s.requested_by, beneficiary),
    ("promotion.approve", "Promotion", apply_move, validate_move, lambda s: s.requested_by, beneficiary),
    ("offboarding.complete", "OffboardingChecklist", apply_offboarding, validate_offboarding, lambda s: s.initiated_by, beneficiary),
    ("hiring.advance", "HiringCandidate", apply_advance, validate_advance, lambda s: None, candidate_beneficiaries),
    ("hiring.offer.release", "JobOffer", apply_offer, validate_offer, lambda s: s.created_by, candidate_beneficiaries),
    ("timesheet.approve", "Timesheet", apply_timesheet, validate_timesheet, employee_maker, beneficiary),
    ("exit.settlement", "ExitSettlement", apply_exit_settlement, validate_exit_settlement, lambda s: s.checklist.initiated_by, beneficiary),
]:
    register_action(ApprovalAction(key=key, model_label="payroll." + model,
        permission="payroll.change_" + model.lower(), apply=apply, validate=validate,
        requester=requester, beneficiaries=beneficiaries,
        reject=reject_timesheet if model == "Timesheet" else reject_hr,
        **({"snapshot": leave_snapshot, "amount": leave_amount} if model == "LeaveRequest" else {}),
        **({"snapshot": offboarding_snapshot} if model == "OffboardingChecklist" else {}),
        **({"snapshot": move_snapshot} if model in {"EmployeeTransfer", "Promotion"} else {}),
        **({"snapshot": hiring_snapshot} if model == "HiringCandidate" else {}),
        **({"snapshot": timesheet_snapshot} if model == "Timesheet" else {}),
        **({"amount": lambda s, p: s.total_amount} if key == "iou.settle" else
           {"amount": lambda s, p: s.amount} if model == "IOU" else
           {"amount": lambda s, p: s.salary_amount} if model == "JobOffer" else {})))

# Appraisal agent supplies its own adapters.
try:
    from payroll import appraisal_approval_actions  # noqa: F401,E402
except ImportError as exc:
    if "appraisal_approval_actions" not in str(exc):
        raise

from payroll import financial_approval_actions  # Register payroll/bank/salary operations.
