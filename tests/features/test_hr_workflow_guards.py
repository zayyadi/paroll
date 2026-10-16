from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError
from payroll.models import EmployeeTransfer
from payroll.services.transfer_service import execute_transfer

class HRApprovalGuardTests(TestCase):
    def setUp(self):
        from tests.features.test_transfers_promotions import EmployeeTransferTest
        EmployeeTransferTest.setUp(self)
    def test_pending_transfer_cannot_execute(self):
        transfer = EmployeeTransfer.objects.create(company=self.company, employee=self.employee,
            to_department=self.dept_b, effective_date="2020-01-01", requested_by=self.user)
        with self.assertRaises((PermissionDenied, ValueError)):
            execute_transfer(transfer=transfer, performed_by=self.user)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department_id, self.dept_a.pk)

    def test_direct_transfer_approval_cannot_be_saved(self):
        transfer = EmployeeTransfer.objects.create(company=self.company, employee=self.employee,
            to_department=self.dept_b, effective_date="2020-01-01", requested_by=self.user)
        transfer.status = "APPROVED"
        with self.assertRaises(PermissionDenied):
            transfer.save()

class HRWorkflowIntegrationTests(HRApprovalGuardTests):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        self.user.company = self.company
        self.user.save()
        self.checker = get_user_model().objects.create_user(email="checker-hr@test.com", password="x", company=self.company)
        self.second = get_user_model().objects.create_user(email="second-hr@test.com", password="x", company=self.company)
        permission = Permission.objects.get(content_type__app_label="payroll", codename="change_employeetransfer")
        self.checker.user_permissions.add(permission)
        self.second.user_permissions.add(permission)

    def make_transfer(self, date="2020-01-01"):
        return EmployeeTransfer.objects.create(company=self.company, employee=self.employee,
            to_department=self.dept_b, effective_date=date, requested_by=self.user)

    def test_checker_execution_and_no_replay(self):
        from payroll.services.transfer_service import approve_transfer
        transfer = self.make_transfer()
        result = approve_transfer(transfer=transfer, approved_by=self.checker)
        self.assertEqual(result.status, "APPROVED")
        transfer.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertEqual(transfer.status, "COMPLETED")
        self.assertEqual(self.employee.department_id, self.dept_b.pk)
        with self.assertRaises((PermissionDenied, ValidationError, ValueError)):
            execute_transfer(transfer=transfer, performed_by=self.checker)

    def test_requester_and_beneficiary_cannot_decide(self):
        from payroll.services.transfer_service import approve_transfer
        with self.assertRaises(PermissionDenied):
            approve_transfer(transfer=self.make_transfer(), approved_by=self.user)

    def test_stages_do_not_execute_until_final_checker(self):
        from approvals.models import ApprovalPolicy
        from payroll.services.transfer_service import approve_transfer
        ApprovalPolicy.objects.create(company=self.company, action="transfer.approve", stages=[
            {"permission":"payroll.change_employeetransfer"}, {"permission":"payroll.change_employeetransfer"}])
        transfer = self.make_transfer()
        result = approve_transfer(transfer=transfer, approved_by=self.checker)
        self.assertEqual(result.status, "PENDING")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department_id, self.dept_a.pk)
        result = approve_transfer(transfer=transfer, approved_by=self.second)
        self.assertEqual(result.status, "APPROVED")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department_id, self.dept_b.pk)

    def test_future_execution_checks_due_date_and_snapshot(self):
        from payroll.services.transfer_service import approve_transfer
        transfer = self.make_transfer("2099-01-01")
        approve_transfer(transfer=transfer, approved_by=self.checker)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "APPROVED")
        with self.assertRaises(ValueError):
            execute_transfer(transfer=transfer, performed_by=self.checker)
        transfer.to_position = "Tampered"
        with self.assertRaises(PermissionDenied): transfer.save()

    def test_rejection_sets_domain_status(self):
        from payroll.services.transfer_service import reject_transfer
        transfer = self.make_transfer()
        reject_transfer(transfer=transfer, approved_by=self.checker, comment="Position not funded")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "REJECTED")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department_id, self.dept_a.pk)

    def test_bulk_cannot_forge_decision(self):
        transfer = self.make_transfer()
        with self.assertRaises(PermissionDenied):
            EmployeeTransfer.objects.filter(pk=transfer.pk).update(status="COMPLETED")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "PENDING")

    def grant(self, codename):
        from django.contrib.auth.models import Permission
        self.checker.user_permissions.add(Permission.objects.get(content_type__app_label="payroll", codename=codename))
        if hasattr(self.checker, "_perm_cache"): del self.checker._perm_cache

    def test_leave_approval_uses_engine_and_single_human_timestamp(self):
        from payroll.models import LeaveRequest
        from payroll.services.hr_workflow import decide_leave
        self.grant("change_leaverequest")
        leave = LeaveRequest.objects.create(employee=self.employee, leave_type="CASUAL",
            start_date="2020-01-06", end_date="2020-01-06", reason="Personal")
        result = decide_leave(leave=leave, actor=self.checker)
        self.assertEqual(result.status, "APPROVED")
        leave.refresh_from_db()
        self.assertEqual(leave.status, "APPROVED")
        self.assertEqual(leave.approved_by_id, self.checker.pk)
        self.assertIsNone(leave.manager_approved_at)
        self.assertIsNone(leave.hr_approved_at)

    def test_leave_self_approval_denied_even_superuser(self):
        from payroll.models import LeaveRequest
        from payroll.services.hr_workflow import decide_leave
        self.user.is_superuser = True
        self.user.save()
        leave = LeaveRequest.objects.create(employee=self.employee, leave_type="CASUAL",
            start_date="2020-01-06", end_date="2020-01-06", reason="Personal")
        with self.assertRaises(PermissionDenied): decide_leave(leave=leave, actor=self.user)

    def test_iou_terms_and_settlement_guard(self):
        from payroll.models import IOU
        from payroll.services.hr_workflow import decide_iou
        self.grant("change_iou")
        iou = IOU.objects.create(employee_id=self.employee, amount="1000.00", tenor=2)
        result = decide_iou(iou=iou, actor=self.checker, payload={"tenor": 3})
        self.assertEqual(result.status, "APPROVED")
        iou.refresh_from_db()
        self.assertEqual(iou.tenor, 3)
        with self.assertRaises(ValidationError): decide_iou(iou=iou, actor=self.checker, decision="SETTLE")
        iou.amount = "2000.00"
        with self.assertRaises(PermissionDenied): iou.save()

    def test_overtime_bulk_and_approval_guard(self):
        from payroll.models.workforce import OvertimeEntry
        from payroll.services.overtime_service import approve_overtime
        self.grant("change_overtimeentry")
        entry = OvertimeEntry.objects.create(company=self.company, employee=self.employee,
            date="2020-01-01", hours="2", rate_multiplier="1.5")
        approve_overtime(entry=entry, approved_by=self.checker)
        entry.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            OvertimeEntry.objects.filter(pk=entry.pk).update(hours="8")

    def test_final_offboarding_without_actor_is_denied(self):
        from payroll.models.workforce import OffboardingChecklist
        from payroll.services.offboarding_service import complete_offboarding
        checklist = OffboardingChecklist.objects.create(company=self.company, employee=self.employee,
            initiated_by=self.user, last_working_day="2020-01-01", reason="RESIGNATION")
        with self.assertRaises((PermissionDenied, ValidationError)):
            complete_offboarding(checklist=checklist)
        checklist.refresh_from_db()
        self.assertEqual(checklist.status, "IN_PROGRESS")

    def test_direct_repayment_is_reviewed_with_amount_and_receipt(self):
        from payroll.models import IOU
        from payroll.services.hr_workflow import decide_iou
        self.grant("change_iou")
        iou = IOU.objects.create(employee_id=self.employee, amount="1000.00", tenor=2, payment_method="DIRECT_PAYMENT")
        decide_iou(iou=iou, actor=self.checker)
        iou.refresh_from_db()
        with self.assertRaises(ValidationError):
            decide_iou(iou=iou, actor=self.checker, decision="SETTLE", payload={"amount_received":"1000.00"})
        result = decide_iou(iou=iou, actor=self.checker, decision="SETTLE",
                            payload={"amount_received":"1000.00", "receipt_reference":"BANK-RECEIPT-42"})
        self.assertEqual(result.status, "PENDING")
        iou.refresh_from_db()
        self.assertEqual(iou.status, "APPROVED")
        from django.contrib.auth.models import Permission
        self.second.user_permissions.add(Permission.objects.get(content_type__app_label="payroll", codename="change_iou"))
        with self.assertRaises(PermissionDenied):
            decide_iou(iou=iou, actor=self.checker, decision="SETTLE")
        result = decide_iou(iou=iou, actor=self.second, decision="SETTLE")
        self.assertEqual(result.status, "APPROVED")
        iou.refresh_from_db()
        self.assertEqual(iou.status, "PAID")

    def test_partial_save_cannot_persist_unsaved_decision(self):
        from payroll.models import IOU
        iou = IOU.objects.create(employee_id=self.employee, amount="1000.00", tenor=2)
        iou.status = "APPROVED"
        iou.reason = "Description only"
        iou.save(update_fields=["reason"])
        iou.refresh_from_db()
        self.assertEqual(iou.status, "PENDING")

    def test_reviewed_source_cannot_be_deleted(self):
        from payroll.services.transfer_service import approve_transfer
        transfer = self.make_transfer()
        approve_transfer(transfer=transfer, approved_by=self.checker)
        transfer.refresh_from_db()
        with self.assertRaises(PermissionDenied): transfer.delete()
        with self.assertRaises(PermissionDenied): EmployeeTransfer.objects.filter(pk=transfer.pk).delete()

    def test_leave_partial_save_does_not_apply_unpersisted_approval(self):
        from payroll.models import LeaveRequest, LeaveBalance
        leave = LeaveRequest.objects.create(employee=self.employee, leave_type="CASUAL",
            start_date="2020-01-06", end_date="2020-01-06", reason="Personal")
        balance = LeaveBalance.objects.create(employee=self.employee, year=2020, casual_leave=3)
        leave.status = "APPROVED"
        leave.reason = "Description only"
        leave.save(update_fields=["reason"])
        leave.refresh_from_db()
        balance.refresh_from_db()
        self.assertEqual(leave.status, "PENDING")
        self.assertEqual(balance.casual_leave, 3)

class HRLegacyDecisionViewTests(HRWorkflowIntegrationTests):
    def login_checker(self, *permissions):
        self.checker.is_manager = True
        self.checker.save(update_fields=["is_manager"])
        for permission in (*permissions, "view_employeeprofile"):
            self.grant(permission)
        self.client.force_login(self.checker)

    def test_transfer_reject_without_reason_reports_error(self):
        from django.urls import reverse
        transfer = self.make_transfer()
        self.login_checker("change_employeeprofile")
        response = self.client.post(reverse("payroll:transfer_approve", args=[transfer.pk]), {"action":"reject"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A rejection reason is required.")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "PENDING")

    def test_leave_reject_without_reason_reports_error(self):
        from django.urls import reverse
        from payroll.models import LeaveRequest
        leave = LeaveRequest.objects.create(employee=self.employee, leave_type="CASUAL", start_date="2020-01-06", end_date="2020-01-06", reason="Personal")
        self.login_checker("change_leaverequest")
        response = self.client.post(reverse("payroll:reject_leave", args=[leave.pk]), {}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A rejection reason is required.")
        leave.refresh_from_db()
        self.assertEqual(leave.status, "PENDING")

    def test_overtime_reject_without_reason_reports_error(self):
        from django.urls import reverse
        from payroll.models.workforce import OvertimeEntry
        entry = OvertimeEntry.objects.create(company=self.company, employee=self.employee, date="2020-01-01", hours="2", rate_multiplier="1.5")
        self.login_checker("change_employeeprofile", "change_overtimeentry")
        response = self.client.post(reverse("payroll:overtime_approve", args=[entry.pk]), {"action":"reject"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A rejection reason is required.")
        entry.refresh_from_db()
        self.assertEqual(entry.status, "PENDING")

    def test_iou_reject_reason_is_form_validation(self):
        from django.urls import reverse
        from payroll.models import IOU
        iou = IOU.objects.create(employee_id=self.employee, amount="1000", tenor=2)
        self.login_checker("change_iou")
        response = self.client.post(reverse("payroll:approve_iou", args=[iou.pk]), {"status":"REJECTED", "tenor":"2", "repayment_deduction_percentage":"30"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A rejection reason is required.")
        iou.refresh_from_db()
        self.assertEqual(iou.status, "PENDING")

    def test_transfer_stale_snapshot_reports_error(self):
        from django.urls import reverse
        from approvals.services import submit_approval
        transfer = self.make_transfer()
        submit_approval(source=transfer, action="transfer.approve", requester=self.user)
        transfer.reason = "Changed after submission"
        transfer.save(update_fields=["reason"])
        self.login_checker("change_employeeprofile")
        response = self.client.post(reverse("payroll:transfer_approve", args=[transfer.pk]), {"action":"approve"}, follow=True)
        self.assertEqual(response.status_code, 200)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "PENDING")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department_id, self.dept_a.pk)

    def test_transfer_pending_stage_message_is_accurate(self):
        from django.urls import reverse
        from approvals.models import ApprovalPolicy
        transfer = self.make_transfer()
        ApprovalPolicy.objects.create(company=self.company, action="transfer.approve", stages=[{"permission":"payroll.change_employeetransfer"},{"permission":"payroll.change_employeetransfer"}])
        self.login_checker("change_employeeprofile")
        response = self.client.post(reverse("payroll:transfer_approve", args=[transfer.pk]), {"action":"approve"}, follow=True)
        self.assertContains(response, "Approval recorded; awaiting the next stage.")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "PENDING")

    def test_transfer_requester_still_receives_forbidden(self):
        from django.urls import reverse
        from django.contrib.auth.models import Permission
        transfer = self.make_transfer()
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="payroll", codename="change_employeeprofile"))
        self.client.force_login(self.user)
        response = self.client.post(reverse("payroll:transfer_approve", args=[transfer.pk]), {"action":"approve"})
        self.assertEqual(response.status_code,403)

    def test_promotion_reject_without_reason_reports_error(self):
        from django.urls import reverse
        from payroll.models import Promotion
        promotion = Promotion.objects.create(company=self.company, employee=self.employee, old_title="Engineer", new_title="Senior Engineer", effective_date="2020-01-01", requested_by=self.user)
        self.login_checker("change_employeeprofile", "change_promotion")
        response = self.client.post(reverse("payroll:promotion_approve", args=[promotion.pk]), {"action":"reject"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A rejection reason is required.")
        promotion.refresh_from_db()
        self.assertEqual(promotion.status, "PENDING")

    def test_iou_stale_snapshot_renders_form_error(self):
        from django.urls import reverse
        from payroll.models import IOU
        from approvals.services import submit_approval
        iou = IOU.objects.create(employee_id=self.employee, amount="1000", tenor=2)
        submit_approval(source=iou, action="iou.approve", requester=self.user, payload={"tenor":"2", "repayment_deduction_percentage":"30"})
        iou.reason = "Changed request"
        iou.save(update_fields=["reason"])
        self.login_checker("change_iou")
        response = self.client.post(reverse("payroll:approve_iou", args=[iou.pk]), {"status":"APPROVED", "tenor":"2", "repayment_deduction_percentage":"30"})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context["form"].non_field_errors())
        iou.refresh_from_db()
        self.assertEqual(iou.status, "PENDING")

    def test_leave_pending_stage_message_is_accurate(self):
        from django.urls import reverse
        from payroll.models import LeaveRequest
        from approvals.models import ApprovalPolicy
        leave = LeaveRequest.objects.create(employee=self.employee, leave_type="CASUAL", start_date="2020-01-06", end_date="2020-01-06", reason="Personal")
        ApprovalPolicy.objects.create(company=self.company, action="leave.approve", stages=[{"permission":"payroll.change_leaverequest"},{"permission":"payroll.change_leaverequest"}])
        self.login_checker("change_leaverequest")
        response = self.client.post(reverse("payroll:approve_leave", args=[leave.pk]), {}, follow=True)
        self.assertContains(response, "Approval recorded; awaiting the next stage.")
        leave.refresh_from_db()
        self.assertEqual(leave.status, "PENDING")
