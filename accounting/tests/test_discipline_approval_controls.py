from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from approvals.models import ApprovalRequest
from approvals.services import decide_approval
from company.models import Company
from accounting.models import DisciplinaryCase, DisciplinarySanction, DisciplinaryAppeal

class DisciplineApprovalControlsTests(TestCase):
    def setUp(self):
        self.company=Company.objects.create(name="Discipline controls")
        User=get_user_model()
        self.maker=User.objects.create_user(email="discipline-maker@example.test",password="x",company=self.company,active_company=self.company)
        self.checker=User.objects.create_user(email="discipline-checker@example.test",password="x",company=self.company,active_company=self.company)
        self.respondent=User.objects.create_user(email="discipline-respondent@example.test",password="x",company=self.company,active_company=self.company)
        self.reporter=User.objects.create_user(email="discipline-reporter@example.test",password="x",company=self.company,active_company=self.company)
        permissions=Permission.objects.filter(content_type__app_label="accounting",codename__in=["change_disciplinarycase","change_disciplinarysanction","change_disciplinaryappeal"])
        self.maker.user_permissions.add(*permissions)
        self.checker.user_permissions.add(*permissions)
        group,_=Group.objects.get_or_create(name="Accountant")
        self.maker.groups.add(group)
        self.checker.groups.add(group)
        self.case=DisciplinaryCase.objects.create(company=self.company,respondent=self.respondent,reporter=self.reporter,allegation_summary="Attendance allegation",allegation_details="Evidence to investigate")
        self.client.force_login(self.maker)

    def approve_case(self):
        request=self.case.decide(finding="SUBSTANTIATED",decided_by=self.maker,rationale="Verified evidence",approval_actor=self.maker)
        decide_approval(approval=request,actor=self.checker)
        self.case.refresh_from_db()
        return request

    def test_decision_form_does_not_change_source_before_approval(self):
        response=self.client.post(reverse("payroll:discipline_decision_update",args=[self.case.pk]),{"finding":"SUBSTANTIATED","findings_summary":"Evidence assessed","decision_rationale":"Verified evidence"})
        self.assertEqual(response.status_code,302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.findings_summary,"")
        self.assertIsNone(self.case.finding)
        self.assertEqual(self.case.status,"INTAKE")
        request=ApprovalRequest.objects.get(action="discipline.decide",status="PENDING")
        decide_approval(approval=request,actor=self.checker)
        self.case.refresh_from_db()
        self.assertEqual(self.case.findings_summary,"Evidence assessed")
        self.assertEqual(self.case.decided_by_id,self.checker.pk)

    def test_decision_records_final_checker(self):
        self.approve_case()
        self.assertEqual(self.case.decided_by_id,self.checker.pk)

    def test_sanction_creation_is_submitted_before_becoming_active(self):
        self.approve_case()
        response=self.client.post(reverse("payroll:discipline_sanction_create",args=[self.case.pk]),{"sanction_type":"WRITTEN_WARNING","rationale":"Proportionate response","effective_date":"2020-01-01","is_rehabilitative":"on"})
        self.assertEqual(response.status_code,302)
        sanction=DisciplinarySanction.objects.get(case=self.case)
        self.assertEqual(sanction.status,"PENDING")
        request=ApprovalRequest.objects.get(action="discipline.sanction",content_type=ContentType.objects.get_for_model(sanction),object_id=sanction.pk)
        self.assertEqual(request.requester_id,self.maker.pk)

    def test_respondent_can_file_appeal_without_changing_case_decision(self):
        self.approve_case()
        self.client.force_login(self.respondent)
        response=self.client.post(reverse("payroll:discipline_appeal_create",args=[self.case.pk]),{"grounds":"NEW_EVIDENCE","details":"New attendance records"})
        self.assertEqual(response.status_code,302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status,"DECIDED")
        self.assertEqual(self.case.decided_by_id,self.checker.pk)
        self.assertEqual(DisciplinaryAppeal.objects.get(case=self.case).appellant_id,self.respondent.pk)

    def test_appeal_review_is_staged_and_conflicts_block_original_decider(self):
        from django.core.exceptions import PermissionDenied
        self.approve_case()
        appeal=DisciplinaryAppeal.objects.create(case=self.case,appellant=self.respondent,grounds="NEW_EVIDENCE",details="New records")
        response=self.client.post(reverse("payroll:discipline_appeal_review",args=[appeal.pk]),{"status":"OVERTURNED","outcome_notes":"New evidence disproved allegation"})
        self.assertEqual(response.status_code,302)
        appeal.refresh_from_db()
        self.assertEqual(appeal.status,"SUBMITTED")
        self.assertIsNone(appeal.reviewed_by_id)
        request=ApprovalRequest.objects.get(action="discipline.appeal.review",status="PENDING")
        self.assertIn(self.respondent.pk,request.beneficiary_ids)
        self.assertIn(self.checker.pk,request.beneficiary_ids)
        with self.assertRaises(PermissionDenied): decide_approval(approval=request,actor=self.checker)
        reviewer=get_user_model().objects.create_user(email="independent-appeal-reviewer@example.test",password="x",company=self.company,active_company=self.company)
        reviewer.user_permissions.add(Permission.objects.get(content_type__app_label="accounting",codename="change_disciplinaryappeal"))
        decide_approval(approval=request,actor=reviewer)
        appeal.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(appeal.status,"OVERTURNED")
        self.assertEqual(appeal.reviewed_by_id,reviewer.pk)
        self.assertEqual(self.case.finding,"UNSUBSTANTIATED")

    def test_sanction_cannot_activate_without_approved_finding(self):
        from django.core.exceptions import ValidationError
        from approvals.services import submit_approval
        sanction=DisciplinarySanction.objects.create(case=self.case,created_by=self.maker,sanction_type="WRITTEN_WARNING",rationale="Allegation only",effective_date="2020-01-01")
        with self.assertRaises(ValidationError): submit_approval(source=sanction,action="discipline.sanction",requester=self.maker)
        sanction.refresh_from_db()
        self.assertEqual(sanction.status,"PENDING")

    def test_senior_review_level_uses_appropriate_checker_authority(self):
        from django.core.exceptions import PermissionDenied
        self.case.violation_level="LEVEL_3"
        self.case.save(update_fields=["violation_level"])
        request=self.case.decide(finding="SUBSTANTIATED",decided_by=self.maker,rationale="Verified serious finding")
        self.assertEqual(request.action,"discipline.decide.panel")
        with self.assertRaises(PermissionDenied): decide_approval(approval=request,actor=self.checker)
        self.checker.user_permissions.add(Permission.objects.get(content_type__app_label="accounting",codename="review_panel_disciplinarycase"))
        for name in ("_perm_cache","_user_perm_cache","_group_perm_cache"):
            if hasattr(self.checker,name): delattr(self.checker,name)
        decide_approval(approval=request,actor=self.checker)
        self.case.refresh_from_db()
        self.assertEqual(self.case.decided_by_id,self.checker.pk)

    def test_combined_flags_do_not_lower_required_review_level(self):
        self.case.emergency_case=True
        self.case.violation_level="LEVEL_5"
        self.assertEqual(self.case.compute_required_review_level(),"EXECUTIVE")
        self.case.emergency_case=False
        self.case.violation_level="LEVEL_1"
        self.case.repeat_offense_suspected=True
        self.case.conflict_of_interest_flag=True
        self.assertEqual(self.case.compute_required_review_level(),"PANEL")

    def test_future_termination_requires_approved_deferred_execution(self):
        from datetime import date
        from unittest.mock import patch
        from approvals.services import submit_approval
        from accounting.discipline_services import execute_approved_sanction
        self.case.violation_level="LEVEL_3"
        self.case.save(update_fields=["violation_level"])
        self.checker.user_permissions.add(Permission.objects.get(content_type__app_label="accounting",codename="review_panel_disciplinarycase"))
        self.approve_case()
        sanction=DisciplinarySanction.objects.create(case=self.case,created_by=self.maker,sanction_type="TERMINATION",rationale="Approved outcome",effective_date=date(2099,1,1))
        request=submit_approval(source=sanction,action="discipline.sanction",requester=self.maker)
        decide_approval(approval=request,actor=self.checker)
        self.respondent.refresh_from_db()
        self.assertTrue(self.respondent.is_active)
        with patch("accounting.discipline_services.timezone.localdate",return_value=date(2099,1,2)):
            sanction.refresh_from_db()
            sanction.save()
            self.respondent.refresh_from_db()
            self.assertTrue(self.respondent.is_active)
            execute_approved_sanction(sanction=sanction,actor=self.checker)
        self.respondent.refresh_from_db()
        sanction.refresh_from_db()
        self.assertFalse(self.respondent.is_active)
        self.assertEqual(sanction.employment_effect_snapshot["approval_id"],request.pk)

    def test_overturn_restores_only_captured_employment_state(self):
        from approvals.services import submit_approval
        from accounting.discipline_approval_actions import submit_appeal_review
        self.case.violation_level="LEVEL_3"
        self.case.save(update_fields=["violation_level"])
        self.checker.user_permissions.add(Permission.objects.get(content_type__app_label="accounting",codename="review_panel_disciplinarycase"))
        self.approve_case()
        sanction=DisciplinarySanction.objects.create(case=self.case,created_by=self.maker,sanction_type="TERMINATION",rationale="Approved outcome",effective_date="2020-01-01")
        request=submit_approval(source=sanction,action="discipline.sanction",requester=self.maker)
        decide_approval(approval=request,actor=self.checker)
        self.respondent.refresh_from_db()
        self.assertFalse(self.respondent.is_active)
        appeal=DisciplinaryAppeal.objects.create(case=self.case,appellant=self.respondent,grounds="NEW_EVIDENCE",details="Exonerating records")
        request=submit_appeal_review(appeal=appeal,actor=self.maker,status="OVERTURNED",outcome_notes="Exonerating evidence verified")
        reviewer=get_user_model().objects.create_user(email="panel-appeal-reviewer@example.test",password="x",company=self.company,active_company=self.company)
        reviewer.user_permissions.add(Permission.objects.get(content_type__app_label="accounting",codename="review_panel_disciplinarycase"))
        decide_approval(approval=request,actor=reviewer)
        sanction.refresh_from_db()
        self.respondent.refresh_from_db()
        self.assertEqual(sanction.status,"REVOKED")
        self.assertTrue(self.respondent.is_active)
        self.assertNotEqual(self.respondent.employee_user.status,"terminated")

    def test_unrelated_employee_cannot_file_appeal_for_another_case(self):
        self.approve_case()
        unrelated=get_user_model().objects.create_user(email="unrelated-case-participant@example.test",password="x",company=self.company,active_company=self.company)
        self.client.force_login(unrelated)
        response=self.client.post(reverse("payroll:discipline_appeal_create",args=[self.case.pk]),{"grounds":"NEW_EVIDENCE","details":"Not my case"})
        self.assertEqual(response.status_code,403)
        self.assertFalse(DisciplinaryAppeal.objects.exists())
