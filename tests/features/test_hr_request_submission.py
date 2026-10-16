from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate
from approvals.models import ApprovalRequest
from approvals.services import decide_approval
from api.v1.viewsets import IOUViewSet, LeaveRequestViewSet
from company.models import Company
from payroll.models import IOU, LeaveRequest, EmployeeProfile

class HRRequestSubmissionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="HR requests")
        User = get_user_model()
        self.employee_user = User.objects.create_user(email="requester@example.test", password="x", company=self.company, active_company=self.company)
        self.other_user = User.objects.create_user(email="other-employee@example.test", password="x", company=self.company, active_company=self.company)
        self.hr = User.objects.create_user(email="hr-requester@example.test", password="x", company=self.company, active_company=self.company)
        self.checker = User.objects.create_user(email="hr-checker@example.test", password="x", company=self.company, active_company=self.company)
        permissions = Permission.objects.filter(content_type__app_label="payroll", codename__in=["change_iou", "change_leaverequest"])
        self.hr.user_permissions.add(*permissions)
        self.checker.user_permissions.add(*permissions)
        self.employee = self.employee_user.employee_user
        self.other_employee = self.other_user.employee_user

    def api(self, viewset, actor, method="post", payload=None, pk=None, action="create"):
        factory = APIRequestFactory()
        request = getattr(factory, method)("/api/hr/", payload or {}, format="json")
        force_authenticate(request, actor)
        return viewset.as_view({method:action})(request, **({"pk":pk} if pk else {}))

    def approval(self, source):
        return ApprovalRequest.objects.get(content_type=ContentType.objects.get_for_model(source), object_id=source.pk, status="PENDING")

    def test_api_selfservice_iou_records_actual_maker_and_inbox(self):
        response = self.api(IOUViewSet, self.employee_user, payload={"employee_id":self.employee.pk, "amount":"100", "tenor":1, "requested_by":self.hr.pk})
        self.assertEqual(response.status_code,201)
        iou = IOU.objects.get(pk=response.data["id"])
        self.assertEqual(iou.requested_by_id,self.employee_user.pk)
        self.assertEqual(self.approval(iou).requester_id,self.employee_user.pk)

    def test_api_leave_selfservice_records_actual_maker_and_inbox(self):
        response = self.api(LeaveRequestViewSet, self.employee_user, payload={"employee":self.employee.pk, "leave_type":"CASUAL", "start_date":"2020-01-06", "end_date":"2020-01-06", "reason":"Personal"})
        self.assertEqual(response.status_code,201)
        leave = LeaveRequest.objects.get(pk=response.data["id"])
        self.assertEqual(leave.requested_by_id,self.employee_user.pk)
        self.assertEqual(self.approval(leave).requester_id,self.employee_user.pk)

    def test_ordinary_creator_cannot_submit_for_other_employee(self):
        response = self.api(IOUViewSet, self.employee_user, payload={"employee_id":self.other_employee.pk, "amount":"100", "tenor":1})
        self.assertEqual(response.status_code,403)
        self.assertFalse(IOU.objects.exists())

    def test_hr_on_behalf_keeps_actual_maker_and_denies_selfapproval(self):
        response = self.api(IOUViewSet, self.hr, payload={"employee_id":self.employee.pk, "amount":"100", "tenor":1})
        self.assertEqual(response.status_code,201)
        iou = IOU.objects.get(pk=response.data["id"])
        request = self.approval(iou)
        self.assertEqual(iou.requested_by_id,self.hr.pk)
        self.assertEqual(request.requester_id,self.hr.pk)
        self.assertIn(self.employee_user.pk,request.beneficiary_ids)
        with self.assertRaises(PermissionDenied): decide_approval(approval=request,actor=self.hr)
        self.assertEqual(decide_approval(approval=request,actor=self.checker).status,"APPROVED")

    def test_ordinary_list_and_detail_hide_others_requests(self):
        own = IOU.objects.create(employee_id=self.employee,amount="100",tenor=1)
        other = IOU.objects.create(employee_id=self.other_employee,amount="200",tenor=1)
        response = self.api(IOUViewSet,self.employee_user,method="get",action="list")
        self.assertEqual(response.status_code,200)
        rows = response.data["results"] if isinstance(response.data,dict) else response.data
        self.assertEqual([row["id"] for row in rows],[own.pk])
        response = self.api(IOUViewSet,self.employee_user,method="get",pk=other.pk,action="retrieve")
        self.assertEqual(response.status_code,404)

    def test_hr_wide_view_requires_specific_authority(self):
        other = IOU.objects.create(employee_id=self.other_employee,amount="200",tenor=1)
        response = self.api(IOUViewSet,self.hr,method="get",pk=other.pk,action="retrieve")
        self.assertEqual(response.status_code,200)
        self.employee_user.is_staff=True
        self.employee_user.save(update_fields=["is_staff"])
        response = self.api(IOUViewSet,self.employee_user,method="get",pk=other.pk,action="retrieve")
        self.assertEqual(response.status_code,404)

    def test_maker_identity_is_immutable_on_pending_and_approved(self):
        response = self.api(IOUViewSet,self.employee_user,payload={"employee_id":self.employee.pk,"amount":"100","tenor":1})
        iou = IOU.objects.get(pk=response.data["id"])
        iou.requested_by=self.hr
        with self.assertRaises(PermissionDenied): iou.save(update_fields=["requested_by"])
        iou.refresh_from_db()
        decide_approval(approval=self.approval(iou),actor=self.checker)
        iou.refresh_from_db()
        iou.requested_by=self.hr
        with self.assertRaises(PermissionDenied): iou.save(update_fields=["requested_by"])

    def test_api_revision_cancels_old_snapshot_and_submits_new(self):
        response = self.api(IOUViewSet,self.employee_user,payload={"employee_id":self.employee.pk,"amount":"100","tenor":1})
        iou=IOU.objects.get(pk=response.data["id"])
        old=self.approval(iou)
        response=self.api(IOUViewSet,self.employee_user,method="patch",payload={"amount":"150"},pk=iou.pk,action="partial_update")
        self.assertEqual(response.status_code,200)
        old.refresh_from_db()
        self.assertEqual(old.status,"CANCELLED")
        self.assertNotEqual(self.approval(iou).pk,old.pk)

    def test_web_leave_creation_is_enrolled_immediately(self):
        self.client.force_login(self.employee_user)
        response=self.client.post(reverse("payroll:apply_leave"),{"leave_type":"CASUAL","start_date":"2020-01-06","end_date":"2020-01-06","reason":"Personal"})
        self.assertEqual(response.status_code,302)
        leave=LeaveRequest.objects.get(employee=self.employee)
        self.assertEqual(self.approval(leave).requester_id,self.employee_user.pk)

    def test_web_iou_creation_is_enrolled_immediately(self):
        self.employee.net_pay="1000.00"
        self.employee.save(update_fields=["net_pay"])
        self.client.force_login(self.employee_user)
        response=self.client.post(reverse("payroll:request_iou"),{"amount":"100","tenor":"1","reason":"Personal"})
        self.assertEqual(response.status_code,302)
        iou=IOU.objects.get(employee_id=self.employee)
        self.assertEqual(iou.requested_by_id,self.employee_user.pk)
        self.assertEqual(self.approval(iou).requester_id,self.employee_user.pk)

    def test_overtime_generation_is_enrolled_with_actual_creator(self):
        from payroll.models.workforce import OvertimePolicy, AttendanceRecord
        from payroll.services.overtime_service import calculate_overtime_for_attendance
        OvertimePolicy.objects.create(company=self.company,daily_threshold_hours="8",weekday_rate_multiplier="1.5",weekend_rate_multiplier="2",max_daily_overtime_hours="4",requires_approval=True)
        attendance=AttendanceRecord.objects.create(company=self.company,employee=self.employee,work_date="2020-01-06",hours_worked="10")
        entry=calculate_overtime_for_attendance(attendance=attendance,requested_by=self.hr)
        self.assertEqual(entry.requested_by_id,self.hr.pk)
        self.assertEqual(self.approval(entry).requester_id,self.hr.pk)
        self.assertIn(self.employee_user.pk,self.approval(entry).beneficiary_ids)

    def test_admin_maker_is_readonly_and_imports_disabled(self):
        from django.contrib import admin
        from django.test import RequestFactory
        from payroll.admin.general_admin import IOUAdmin
        model_admin=IOUAdmin(IOU,admin.site)
        request=RequestFactory().get("/admin/payroll/iou/")
        request.user=self.hr
        self.assertIn("requested_by",model_admin.get_readonly_fields(request))
        self.assertFalse(model_admin.has_import_permission(request))
        source=IOU(employee_id=self.employee,amount="100",tenor=1)
        model_admin.save_model(request,source,None,False)
        self.assertEqual(source.requested_by_id,self.hr.pk)
        self.assertEqual(self.approval(source).requester_id,self.hr.pk)

    def test_cross_company_creator_assignment_is_rejected(self):
        other_company=Company.objects.create(name="Other company")
        outsider=get_user_model().objects.create_user(email="outsider-request@example.test",password="x",company=other_company,active_company=other_company)
        response=self.api(IOUViewSet,self.hr,payload={"employee_id":outsider.employee_user.pk,"amount":"100","tenor":1})
        self.assertEqual(response.status_code,400)
        self.assertFalse(IOU.objects.exists())

    def test_overtime_foreign_employee_cannot_be_submitted(self):
        from payroll.models.workforce import OvertimeEntry
        from payroll.services.hr_workflow import submit_hr_request
        from django.core.exceptions import ValidationError
        other_company=Company.objects.create(name="Other overtime company")
        outsider=get_user_model().objects.create_user(email="outside-overtime@example.test",password="x",company=other_company,active_company=other_company)
        entry=OvertimeEntry.objects.create(company=self.company,employee=outsider.employee_user,requested_by=self.hr,date="2020-01-01",hours="2",rate_multiplier="1.5")
        with self.assertRaises(ValidationError): submit_hr_request(entry,self.hr)
        self.assertFalse(ApprovalRequest.objects.filter(content_type=ContentType.objects.get_for_model(entry),object_id=entry.pk).exists())

    def test_primary_manager_cannot_read_secondary_member_company_requests(self):
        from company.models import CompanyMembership
        other_company=Company.objects.create(name="Secondary member company")
        CompanyMembership.objects.create(user=self.hr,company=other_company,role="member")
        self.hr.is_manager=True
        self.hr.active_company=other_company
        self.hr.save(update_fields=["is_manager","active_company"])
        self.client.force_login(self.hr)
        response=self.client.get(reverse("payroll:manage_leave_requests"))
        self.assertEqual(response.status_code,403)

    def test_primary_manager_cannot_edit_secondary_member_company_iou(self):
        from company.models import CompanyMembership
        other_company=Company.objects.create(name="Secondary edit company")
        employee_user=get_user_model().objects.create_user(email="secondary-beneficiary@example.test",password="x",company=other_company,active_company=other_company)
        iou=IOU.objects.create(employee_id=employee_user.employee_user,requested_by=employee_user,amount="100",tenor=1)
        CompanyMembership.objects.create(user=self.hr,company=other_company,role="member")
        self.hr.is_manager=True
        self.hr.active_company=other_company
        self.hr.save(update_fields=["is_manager","active_company"])
        self.client.force_login(self.hr)
        response=self.client.get(reverse("payroll:approve_iou",args=[iou.pk]))
        self.assertEqual(response.status_code,403)
        response=self.client.post(reverse("payroll:iou_update",args=[iou.pk]),{"amount":"200","tenor":"1","reason":"Changed","payment_method":"SALARY_DEDUCTION"})
        self.assertEqual(response.status_code,404)
        iou.refresh_from_db()
        self.assertEqual(str(iou.amount),"100.00")

    def test_negative_interest_cannot_create_unaccounted_loan_discount(self):
        response=self.api(IOUViewSet,self.employee_user,payload={"employee_id":self.employee.pk,"amount":"100","tenor":1,"interest_rate":"-1"})
        self.assertEqual(response.status_code,400)
        self.assertFalse(IOU.objects.exists())

    def test_deactivated_borrower_receipt_uses_current_finance_maker_and_checker(self):
        from accounting.models import Journal
        response=self.api(IOUViewSet,self.employee_user,payload={"employee_id":self.employee.pk,"amount":"100","tenor":1})
        iou=IOU.objects.get(pk=response.data["id"])
        decide_approval(approval=self.approval(iou),actor=self.checker)
        self.employee_user.is_active=False
        self.employee_user.save(update_fields=["is_active"])
        receipt={"payment_method":"DIRECT_PAYMENT","amount_received":"100","receipt_reference":"BANK-RECEIPT-RETIRED-1"}
        journals=Journal.objects.count()
        response=self.api(IOUViewSet,self.hr,payload=receipt,pk=iou.pk,action="mark_paid")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["status"],"PENDING")
        request=self.approval(iou)
        self.assertEqual(request.requester_id,self.hr.pk)
        self.assertIn(self.employee_user.pk,request.beneficiary_ids)
        iou.refresh_from_db()
        self.assertEqual(iou.requested_by_id,self.employee_user.pk)
        self.assertEqual(iou.status,"APPROVED")
        self.assertEqual(Journal.objects.count(),journals)
        response=self.api(IOUViewSet,self.hr,payload=receipt,pk=iou.pk,action="mark_paid")
        self.assertEqual(response.status_code,403)
        response=self.api(IOUViewSet,self.checker,payload=receipt,pk=iou.pk,action="mark_paid")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["status"],"APPROVED")
        iou.refresh_from_db()
        self.assertEqual(iou.status,"PAID")
        self.assertEqual(iou.requested_by_id,self.employee_user.pk)
        self.assertEqual(Journal.objects.count(),journals+1)
        self.assertTrue(Journal.objects.filter(approval_request_id=request.pk).exists())

    def test_receipt_employee_beneficiary_cannot_self_approve(self):
        from payroll.services.hr_workflow import decide_iou
        response=self.api(IOUViewSet,self.employee_user,payload={"employee_id":self.employee.pk,"amount":"100","tenor":1,"payment_method":"DIRECT_PAYMENT"})
        iou=IOU.objects.get(pk=response.data["id"])
        decide_approval(approval=self.approval(iou),actor=self.checker)
        iou.refresh_from_db()
        request=decide_iou(iou=iou,actor=self.hr,decision="SETTLE",payload={"amount_received":"100","receipt_reference":"BENEFICIARY-RECEIPT"})
        self.employee_user.user_permissions.add(Permission.objects.get(content_type__app_label="payroll",codename="change_iou"))
        with self.assertRaises(PermissionDenied): decide_approval(approval=request,actor=self.employee_user)
        iou.refresh_from_db()
        self.assertEqual(iou.status,"APPROVED")

    def test_receipt_submission_requires_company_finance_authority(self):
        from payroll.services.hr_workflow import decide_iou
        response=self.api(IOUViewSet,self.employee_user,payload={"employee_id":self.employee.pk,"amount":"100","tenor":1,"payment_method":"DIRECT_PAYMENT"})
        iou=IOU.objects.get(pk=response.data["id"])
        decide_approval(approval=self.approval(iou),actor=self.checker)
        iou.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            decide_iou(iou=iou,actor=self.other_user,decision="SETTLE",payload={"amount_received":"100","receipt_reference":"UNAUTHORIZED-RECEIPT"})
        self.assertFalse(ApprovalRequest.objects.filter(action="iou.settle").exists())
