from django.core.exceptions import ValidationError
from django.urls import reverse
from django.test import TestCase
from tests.features import test_performance_reviews
from payroll.models import AppraisalAssignment, Review, Metric, Rating


class AppraisalPermissionTests(TestCase):
    _grant = test_performance_reviews.PerformanceReviewFeatureTests._grant
    def setUp(self):
        test_performance_reviews.PerformanceReviewFeatureTests.setUp(self)
        AppraisalAssignment.objects.create(appraisal=self.appraisal, appraisee=self.appraisee, appraiser=self.appraiser)
        self.review = Review.objects.create(appraisal=self.appraisal, employee=self.appraisee, reviewer=self.appraiser)

    def test_employee_cannot_edit_reviewer_assessment(self):
        self.client.force_login(self.appraisee_user)
        response = self.client.get(reverse('payroll:review_update', args=[self.review.pk]))
        self.assertEqual(response.status_code, 403)

    def test_employee_cannot_delete_reviewer_assessment(self):
        self.client.force_login(self.appraisee_user)
        response = self.client.post(reverse('payroll:review_delete', args=[self.review.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Review.objects.filter(pk=self.review.pk).exists())

    def test_employee_cannot_read_unreleased_result(self):
        self.client.force_login(self.appraisee_user)
        response = self.client.get(reverse('payroll:review_detail', args=[self.review.pk]))
        self.assertEqual(response.status_code, 403)

    def _submit(self):
        from approvals.services import submit_approval
        metric = Metric.objects.create(name="Quality")
        self.rating = Rating.objects.create(review=self.review, metric=metric, rating=4)
        self.review.status = "SUBMITTED"
        self.review.save(update_fields=["status"])
        return submit_approval(source=self.review, action="appraisal.publish", requester=self.appraiser_user)

    def test_independent_checker_publishes_and_employee_reads_only(self):
        from django.contrib.auth import get_user_model
        from approvals.services import decide_approval
        checker = get_user_model().objects.create_user(email="checker@example.com", password="test", company=self.company, active_company=self.company)
        self._grant(checker, "publish_review")
        request = self._submit()
        decide_approval(approval=request, actor=checker)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, "PUBLISHED")
        self.assertEqual(self.review.published_by_id, checker.pk)
        self.client.force_login(self.appraisee_user)
        self.assertEqual(self.client.get(reverse('payroll:review_detail', args=[self.review.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('payroll:review_update', args=[self.review.pk])).status_code, 403)

    def test_maker_and_beneficiary_cannot_publish_even_with_permission(self):
        from django.core.exceptions import PermissionDenied
        from approvals.services import decide_approval
        request = self._submit()
        for user in [self.appraiser_user, self.appraisee_user]:
            self._grant(user, "publish_review")
            with self.assertRaises(PermissionDenied):
                decide_approval(approval=request, actor=user)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, "SUBMITTED")

    def test_submitted_rating_edits_and_forged_publication_blocked(self):
        self._submit()
        self.rating.rating = 1
        with self.assertRaises(ValidationError):
            self.rating.save()
        with self.assertRaises(ValidationError):
            Rating.objects.filter(pk=self.rating.pk).update(rating=1)
        with self.assertRaises(ValidationError):
            Review.objects.filter(pk=self.review.pk).update(status="PUBLISHED")
        self.review.status = "PUBLISHED"
        with self.assertRaises(ValidationError):
            self.review.save()

    def test_same_company_other_reviewer_cannot_edit(self):
        from django.contrib.auth import get_user_model
        other = get_user_model().objects.create_user(email="other@example.com", password="test", company=self.company, active_company=self.company)
        self._grant(other, "change_review")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('payroll:review_update', args=[self.review.pk])).status_code, 403)

    def test_no_company_fails_closed(self):
        from django.contrib.auth import get_user_model
        other = get_user_model().objects.create_user(email="unscoped@example.com", password="test")
        get_user_model().objects.filter(pk=other.pk).update(company=None, active_company=None)
        other.refresh_from_db()
        self._grant(other, "view_review")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('payroll:review_detail', args=[self.review.pk])).status_code, 403)

    def test_rejection_returns_draft_for_revision(self):
        from django.contrib.auth import get_user_model
        from approvals.services import decide_approval
        checker = get_user_model().objects.create_user(email="rejector@example.com", password="test", company=self.company, active_company=self.company)
        self._grant(checker, "publish_review")
        request = self._submit()
        decide_approval(approval=request, actor=checker, decision="REJECT", comment="Please include supporting examples")
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, "DRAFT")
        self.client.force_login(self.appraiser_user)
        self.assertEqual(self.client.get(reverse('payroll:review_update', args=[self.review.pk])).status_code, 200)

    def test_cancellation_returns_draft_for_revision(self):
        from approvals.services import cancel_approval
        request = self._submit()
        cancel_approval(approval=request, actor=self.appraiser_user, reason="Correct a factual error")
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, "DRAFT")

    def test_appraisal_cascade_cannot_delete_submitted_review(self):
        self._submit()
        from django.db import transaction
        with self.assertRaises(ValidationError), transaction.atomic():
            self.appraisal.delete()
        self.assertTrue(Review.objects.filter(pk=self.review.pk).exists())

    def test_reviewer_http_submission_creates_bound_publication_request(self):
        from approvals.models import ApprovalRequest
        metric = Metric.objects.create(name="Delivery")
        rating = Rating.objects.create(review=self.review, metric=metric, rating=4)
        self.client.force_login(self.appraiser_user)
        response = self.client.post(reverse("payroll:review_update", args=[self.review.pk]), {
            "self_assessment": "Delivered planned objectives", "action": "submit",
            "ratings-TOTAL_FORMS": "1", "ratings-INITIAL_FORMS": "1",
            "ratings-MIN_NUM_FORMS": "0", "ratings-MAX_NUM_FORMS": "1000",
            "ratings-0-id": str(rating.pk), "ratings-0-review": str(self.review.pk),
            "ratings-0-metric": str(metric.pk), "ratings-0-rating": "5", "ratings-0-comments": "Evidence confirmed",
        })
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, "SUBMITTED")
        request = ApprovalRequest.objects.get(action="appraisal.publish", object_id=self.review.pk)
        self.assertEqual(request.requester_id, self.appraiser_user.pk)
        self.assertEqual(request.source_snapshot["ratings"][0]["rating"], 5)
        self.assertEqual(self.client.get(reverse("payroll:review_update", args=[self.review.pk])).status_code, 403)

    def test_company_admin_employee_cannot_read_unpublished_review_admin_snapshot(self):
        from company.models import CompanyMembership
        from django.contrib.auth.models import Permission
        CompanyMembership.objects.update_or_create(user=self.appraisee_user, company=self.company, defaults={"role": "admin"})
        self.appraisee_user.is_staff = True
        self.appraisee_user.save(update_fields=["is_staff"])
        self.appraisee_user.user_permissions.add(Permission.objects.get(content_type__app_label="approvals", codename="view_approvalrequest"))
        self.review.self_assessment = "PRIVATE_UNPUBLISHED_REVIEW_EVIDENCE"
        self.review.save(update_fields=["self_assessment"])
        request = self._submit()
        self.client.force_login(self.appraisee_user)
        response = self.client.get(reverse("admin:approvals_approvalrequest_change", args=[request.pk]))
        self.assertFalse(b"PRIVATE_UNPUBLISHED_REVIEW_EVIDENCE" in response.content, "Unpublished assessment leaked through raw admin snapshot")
        self.assertNotEqual(response.status_code, 200)

    def test_independent_checker_sees_assessment_and_frozen_metric_in_approval(self):
        from tests.approval_helpers import approval_user
        checker = approval_user(self.company, ["payroll.publish_review"])
        self.review.self_assessment = "REVIEWED_EVIDENCE_FOR_CHECKER"
        self.review.save(update_fields=["self_assessment"])
        request = self._submit()
        self.client.force_login(checker)
        response = self.client.get(reverse("approvals:detail", args=[request.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "REVIEWED_EVIDENCE_FOR_CHECKER")
        self.assertContains(response, "Quality")

    def test_admin_beneficiary_sees_status_without_private_assessment_preview(self):
        from company.models import CompanyMembership
        CompanyMembership.objects.update_or_create(user=self.appraisee_user, company=self.company, defaults={"role": "admin"})
        self.review.self_assessment = "HIDDEN_REVIEW_EVIDENCE_FROM_BENEFICIARY"
        self.review.save(update_fields=["self_assessment"])
        request = self._submit()
        self.client.force_login(self.appraisee_user)
        response = self.client.get(reverse("approvals:detail", args=[request.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "HIDDEN_REVIEW_EVIDENCE_FROM_BENEFICIARY")

    def test_checker_api_shows_evidence_but_admin_beneficiary_api_does_not(self):
        from tests.approval_helpers import approval_user
        from company.models import CompanyMembership
        checker = approval_user(self.company, ["payroll.publish_review"])
        self.review.self_assessment = "PRIVATE_CHECKER_API_EVIDENCE"
        self.review.save(update_fields=["self_assessment"])
        request = self._submit()
        self.client.force_login(checker)
        response = self.client.get(reverse("approval_api:detail", args=[request.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PRIVATE_CHECKER_API_EVIDENCE")
        self.assertContains(response, "Quality")
        CompanyMembership.objects.update_or_create(user=self.appraisee_user, company=self.company, defaults={"role": "admin"})
        self.client.force_login(self.appraisee_user)
        response = self.client.get(reverse("approval_api:detail", args=[request.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "PRIVATE_CHECKER_API_EVIDENCE")
        self.assertEqual(response.json()["fields"], [])

    def test_admin_beneficiary_cannot_read_private_unpublished_decision_notes(self):
        from tests.approval_helpers import approval_user
        from approvals.services import decide_approval
        from company.models import CompanyMembership
        checker = approval_user(self.company, ["payroll.publish_review"])
        request = self._submit()
        decide_approval(approval=request, actor=checker, decision="REJECT", comment="PRIVATE_UNPUBLISHED_APPRAISAL_DECISION_NOTE")
        CompanyMembership.objects.update_or_create(user=self.appraisee_user, company=self.company, defaults={"role": "admin"})
        self.client.force_login(self.appraisee_user)
        for name in ("approvals:detail", "approval_api:detail"):
            response = self.client.get(reverse(name, args=[request.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(b"PRIVATE_UNPUBLISHED_APPRAISAL_DECISION_NOTE" in response.content, "Unpublished decision note leaked through approval history")
