from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from company.models import Company
from approvals.models import ApprovalPolicy, ApprovalRequest, ApprovalDecision
from approvals.registry import ApprovalAction, register_action, _actions
from approvals.services import (
    submit_approval,
    decide_approval,
    cancel_approval,
    execution_authorized,
)


class WorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Approval company")
        self.other = Company.objects.create(name="Other company")
        User = get_user_model()
        self.maker = User.objects.create_user(
            email="maker@example.test", password="x", company=self.company
        )
        self.checker = User.objects.create_user(
            email="checker@example.test", password="x", company=self.company
        )
        self.second = User.objects.create_user(
            email="second@example.test", password="x", company=self.company
        )
        self.outsider = User.objects.create_superuser(
            email="out@example.test", password="x", company=self.other
        )
        self.permission = Permission.objects.get(
            content_type__app_label="company", codename="change_company"
        )
        for user in (self.maker, self.checker, self.second):
            user.user_permissions.add(self.permission)
        self.source = self.maker
        self.key = "test.workflow"

        def apply(source, actor, payload):
            self.assertTrue(execution_authorized(source, self.key))
            source.first_name = "approved"
            source.save(update_fields=["first_name"])

        self.action = ApprovalAction(
            key=self.key,
            model_label="users.CustomUser",
            permission="company.change_company",
            apply=apply,
            requester=lambda s: s,
        )
        _actions.pop(self.key, None)
        register_action(self.action)

    def tearDown(self):
        _actions.pop(self.key, None)

    def submit(self):
        return submit_approval(
            source=self.source, action=self.key, requester=self.maker
        )

    def test_independent_checker_applies_and_replay_is_rejected(self):
        request = self.submit()
        self.assertEqual(self.submit().pk, request.pk)
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.maker)
        approved = decide_approval(approval=request, actor=self.checker)
        self.assertEqual(approved.status, "APPROVED")
        self.source.refresh_from_db()
        self.assertEqual(self.source.first_name, "approved")
        self.assertFalse(execution_authorized(self.source, self.key))
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.checker)

    def test_superuser_cannot_cross_company_or_self_approve(self):
        request = self.submit()
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.outsider)
        self.maker.is_superuser = True
        self.maker.save()
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.maker)

    def test_changed_source_rejected_without_decision(self):
        request = self.submit()
        self.source.first_name = "changed"
        self.source.save()
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=self.checker)
        self.assertFalse(request.decisions.exists())

    def test_failed_effect_rolls_back_source_and_audit(self):
        def fail(source, actor, payload):
            source.first_name = "bad"
            source.save()
            raise ValidationError("effect failed")

        _actions[self.key] = ApprovalAction(
            key=self.key,
            model_label="users.CustomUser",
            permission="company.change_company",
            apply=fail,
            requester=lambda s: s,
        )
        request = self.submit()
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=self.checker)
        self.source.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(self.source.first_name, "")
        self.assertEqual(request.status, "PENDING")
        self.assertFalse(request.decisions.exists())
        self.assertEqual(request.events.count(), 1)

    def test_policy_snapshot_distinct_actors(self):
        policy = ApprovalPolicy.objects.create(
            company=self.company,
            action=self.key,
            stages=[
                {"permission": "company.change_company"},
                {"permission": "company.change_company"},
            ],
        )
        request = self.submit()
        policy.stages = [{"permission": "company.change_company"}]
        policy.save()
        request = decide_approval(approval=request, actor=self.checker)
        self.assertEqual(request.status, "PENDING")
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.checker)
        self.assertEqual(
            decide_approval(approval=request, actor=self.second).status, "APPROVED"
        )

    def test_audit_cannot_be_forged_or_removed(self):
        request = self.submit()
        with self.assertRaises(ValidationError):
            ApprovalRequest.objects.filter(pk=request.pk).update(status="APPROVED")
        request.status = "APPROVED"
        with self.assertRaises(ValidationError):
            request.save()
        with self.assertRaises(ValidationError):
            request.delete()
        with self.assertRaises(ValidationError):
            ApprovalDecision.objects.create(
                request=request, actor=self.checker, stage=0, decision="APPROVE"
            )

    def test_beneficiary_conflict(self):
        _actions[self.key] = ApprovalAction(
            key=self.key,
            model_label="users.CustomUser",
            permission="company.change_company",
            apply=self.action.apply,
            requester=lambda s: s,
            beneficiaries=lambda s: [self.checker.pk],
        )
        request = self.submit()
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.checker)

    def test_cancel_and_reject_are_audited(self):
        request = self.submit()
        with self.assertRaises(PermissionDenied):
            cancel_approval(approval=request, actor=self.checker, reason="withdraw")
        self.assertEqual(
            cancel_approval(
                approval=request, actor=self.maker, reason="withdraw"
            ).status,
            "CANCELLED",
        )
        request = self.submit()
        self.assertEqual(
            decide_approval(
                approval=request,
                actor=self.checker,
                decision="REJECT",
                comment="declined",
            ).status,
            "REJECTED",
        )

    def test_designated_approver_and_invalid_policy(self):
        self.checker.user_permissions.clear()
        ApprovalPolicy.objects.create(
            company=self.company,
            action=self.key,
            stages=[
                {
                    "permission": "company.change_company",
                    "approver_ids": [self.checker.pk],
                }
            ],
        )
        self.assertEqual(
            decide_approval(approval=self.submit(), actor=self.checker).status,
            "APPROVED",
        )
        with self.assertRaises(ValidationError):
            ApprovalPolicy.objects.create(
                company=self.company,
                action=self.key,
                currency="USD",
                minimum_amount=-1,
                stages=[{"permission": "company.change_company"}],
            )
        with self.assertRaises(ValidationError):
            ApprovalPolicy.objects.create(
                company=self.company,
                action=self.key,
                stages=[
                    {
                        "permission": "company.change_company",
                        "approver_ids": [self.outsider.pk],
                    }
                ],
            )

    def test_deferred_execution_uses_completed_snapshot_and_original_checker(self):
        from approvals.services import authorize_approved_execution

        request = decide_approval(approval=self.submit(), actor=self.checker)
        with authorize_approved_execution(request, self.checker):
            self.assertTrue(execution_authorized(self.source, self.key))
        with self.assertRaises(PermissionDenied):
            with authorize_approved_execution(request, self.second):
                pass
        self.source.refresh_from_db()
        self.source.last_name = "changed"
        self.source.save()
        with self.assertRaises(ValidationError):
            with authorize_approved_execution(request, self.checker):
                pass

    def test_reasons_required_and_cancel_callback_skipped_when_stale(self):
        _actions[self.key] = ApprovalAction(
            key=self.key,
            model_label="users.CustomUser",
            permission="company.change_company",
            apply=self.action.apply,
            requester=lambda s: s,
            cancel=self.action.apply,
        )
        request = self.submit()
        with self.assertRaises(ValidationError):
            cancel_approval(approval=request, actor=self.maker)
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=self.checker, decision="REJECT")
        self.source.last_name = "edited"
        self.source.save()
        cancel_approval(approval=request, actor=self.maker, reason="content edited")
        self.source.refresh_from_db()
        self.assertEqual(self.source.first_name, "")

    def test_secondary_membership_global_permission_does_not_grant_authority(self):
        from company.models import CompanyMembership

        self.checker.company = self.other
        self.checker.active_company = self.company
        self.checker.save()
        membership, _ = CompanyMembership.objects.update_or_create(
            user=self.checker, company=self.company, defaults={"role": "member"}
        )
        request = self.submit()
        with self.assertRaises(PermissionDenied):
            decide_approval(approval=request, actor=self.checker)
        membership.role = "admin"
        membership.save()
        self.assertEqual(
            decide_approval(approval=request, actor=self.checker).status, "APPROVED"
        )

    def test_currency_threshold_selects_more_stages_and_zero_threshold_beats_baseline(
        self,
    ):
        _actions[self.key] = ApprovalAction(
            key=self.key,
            model_label="users.CustomUser",
            permission="company.change_company",
            apply=self.action.apply,
            requester=lambda s: s,
            amount=lambda source, payload: Decimal(payload["amount"]),
        )
        ApprovalPolicy.objects.create(
            company=self.company,
            action=self.key,
            stages=[{"permission": "company.change_company"}],
        )
        ApprovalPolicy.objects.create(
            company=self.company,
            action=self.key,
            currency="NGN",
            minimum_amount=0,
            stages=[
                {"permission": "company.change_company"},
                {"permission": "company.change_company"},
            ],
        )
        request = submit_approval(
            source=self.source,
            action=self.key,
            requester=self.maker,
            payload={"amount": "0", "currency": "NGN"},
        )
        self.assertEqual(len(request.policy_snapshot["stages"]), 2)
        with self.assertRaises(ValidationError):
            ApprovalPolicy.objects.create(
                company=self.company,
                action=self.key,
                stages=[{"permission": "company.change_company"}],
            )

    def test_indirect_beneficiary_change_invalidates_request(self):
        beneficiaries = [self.second.pk]
        _actions[self.key] = ApprovalAction(
            key=self.key,
            model_label="users.CustomUser",
            permission="company.change_company",
            apply=self.action.apply,
            requester=lambda s: s,
            beneficiaries=lambda s: beneficiaries,
        )
        request = self.submit()
        beneficiaries[:] = [self.checker.pk]
        with self.assertRaises(ValidationError):
            decide_approval(approval=request, actor=self.checker)
        self.assertFalse(request.decisions.exists())


class InterfaceTests(TestCase):
    setUp = WorkflowTests.setUp
    tearDown = WorkflowTests.tearDown
    submit = WorkflowTests.submit

    def test_inbox_detail_restrict_requests_and_show_safe_business_fields(self):
        from django.test import Client

        request = self.submit()
        self.client.force_login(self.maker)
        response = self.client.get(f"/approvals/{request.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, request.source_hash)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f"/approvals/{request.pk}/").status_code, 404)
        self.client.force_login(self.second)
        self.second.user_permissions.clear()
        self.assertEqual(self.client.get(f"/approvals/{request.pk}/").status_code, 404)

    def test_web_post_only_self_denial_and_valid_decision(self):
        self.client.force_login(self.maker)
        request = self.submit()
        url = f"/approvals/{request.pk}/approve/"
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.checker)
        self.assertEqual(self.client.post(url).status_code, 302)
        request.refresh_from_db()
        self.assertEqual(request.status, "APPROVED")

    def test_session_csrf_and_rejection_reason(self):
        from django.test import Client

        request = self.submit()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.checker)
        self.assertEqual(
            client.post(f"/approvals/{request.pk}/approve/").status_code, 403
        )
        self.client.force_login(self.checker)
        self.assertEqual(
            self.client.post(f"/approvals/{request.pk}/reject/").status_code, 400
        )
        self.assertEqual(
            self.client.post(
                f"/approvals/{request.pk}/reject/", {"comment": "Wrong period"}
            ).status_code,
            302,
        )

    def test_api_submit_scoping_read_and_decision(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.maker)
        response = client.post(
            "/api/v1/approvals/submit/",
            {"action": self.key, "source_id": self.source.pk, "payload": {}},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(
            client.post(
                f"/api/v1/approvals/{pk}/decide/", {}, format="json"
            ).status_code,
            403,
        )
        client.force_authenticate(self.outsider)
        self.assertEqual(client.get(f"/api/v1/approvals/{pk}/").status_code, 404)
        client.force_authenticate(self.checker)
        self.assertEqual(
            client.post(
                f"/api/v1/approvals/{pk}/decide/", {"decision": "REJECT"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/approvals/{pk}/decide/",
                {"decision": "APPROVE"},
                format="json",
            ).status_code,
            200,
        )

    def test_policy_form_ordering_and_snapshot_immutability(self):
        permission = Permission.objects.get(
            content_type__app_label="approvals", codename="configure_policy"
        )
        self.maker.user_permissions.add(permission)
        self.client.force_login(self.maker)
        self.assertEqual(self.client.get("/approvals/policies/").status_code, 200)
        data = {
            "name": "Two checkers",
            "action": self.key,
            "enabled": "on",
            "minimum_amount": "",
            "currency": "",
            "stages-TOTAL_FORMS": "2",
            "stages-INITIAL_FORMS": "0",
            "stages-MIN_NUM_FORMS": "1",
            "stages-MAX_NUM_FORMS": "10",
            "stages-0-name": "Final",
            "stages-0-require_authority": "on",
            "stages-0-ORDER": "2",
            "stages-1-name": "First",
            "stages-1-require_authority": "on",
            "stages-1-ORDER": "1",
        }
        response = self.client.post("/approvals/policies/", data)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        policy = ApprovalPolicy.objects.get(company=self.company, action=self.key)
        self.assertEqual([stage["name"] for stage in policy.stages], ["First", "Final"])
        request = self.submit()
        data.update(
            {
                "stages-TOTAL_FORMS": "1",
                "stages-INITIAL_FORMS": "2",
                "stages-0-name": "Changed",
                "stages-0-ORDER": "1",
            }
        )
        data["stages-INITIAL_FORMS"] = "1"
        response = self.client.post(f"/approvals/policies/{policy.pk}/", data)
        self.assertEqual(response.status_code, 302)
        request.refresh_from_db()
        self.assertEqual(len(request.policy_snapshot["stages"]), 2)
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/approvals/policies/{policy.pk}/").status_code, 404
        )

    def test_policy_authority_has_no_staff_shortcut(self):
        self.second.is_staff = True
        self.second.save()
        self.client.force_login(self.second)
        self.assertEqual(self.client.get("/approvals/policies/").status_code, 403)

    def test_api_cancel_and_invalid_payload(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.maker)
        self.assertEqual(
            client.post("/api/v1/approvals/submit/", [], format="json").status_code, 400
        )
        response = client.post(
            "/api/v1/approvals/submit/",
            {"action": self.key, "source_id": self.source.pk, "payload": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        request = self.submit()
        self.assertEqual(
            client.post(
                f"/api/v1/approvals/{request.pk}/cancel/", {}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/approvals/{request.pk}/cancel/",
                {"reason": "Revise amounts"},
                format="json",
            ).status_code,
            200,
        )
