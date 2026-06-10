from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from company.models import Company
from payroll.models import Appraisal, AppraisalAssignment, Metric, Rating, Review


User = get_user_model()


class PerformanceReviewFeatureTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Performance Co")
        self.appraiser_user = User.objects.create_user(
            email="appraiser@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.appraisee_user = User.objects.create_user(
            email="appraisee@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.appraiser = self.appraiser_user.employee_user
        self.appraisee = self.appraisee_user.employee_user
        self.appraiser.company = self.company
        self.appraisee.company = self.company
        self.appraiser.save(update_fields=["company"])
        self.appraisee.save(update_fields=["company"])
        self.appraisal = Appraisal.objects.create(
            company=self.company,
            name="Midyear",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
        )

    def _grant(self, user, codename):
        permission = Permission.objects.get(
            content_type__app_label="payroll",
            codename=codename,
        )
        user.user_permissions.add(permission)

    def test_appraisal_assignment_and_review(self):
        assignment = AppraisalAssignment.objects.create(
            appraisal=self.appraisal,
            appraisee=self.appraisee,
            appraiser=self.appraiser,
        )
        review = Review.objects.create(
            appraisal=self.appraisal,
            employee=self.appraisee,
            reviewer=self.appraiser,
            self_assessment="Delivered key outcomes.",
        )

        self.assertEqual(assignment.appraisee, self.appraisee)
        self.assertEqual(review.reviewer, self.appraiser)

    def test_appraisal_and_review_views_render_for_authorized_users(self):
        self._grant(self.appraiser_user, "view_appraisal")
        self._grant(self.appraiser_user, "add_review")
        self._grant(self.appraiser_user, "view_review")
        AppraisalAssignment.objects.create(
            appraisal=self.appraisal,
            appraisee=self.appraisee,
            appraiser=self.appraiser,
        )
        metric = Metric.objects.create(name="Delivery")
        review = Review.objects.create(
            appraisal=self.appraisal,
            employee=self.appraisee,
            reviewer=self.appraiser,
            self_assessment="Delivered key outcomes.",
        )
        Rating.objects.create(review=review, metric=metric, rating=4)
        self.client.force_login(self.appraiser_user)

        appraisal_list = self.client.get(reverse("payroll:appraisal_list"))
        appraisal_detail = self.client.get(
            reverse("payroll:appraisal_detail", args=[self.appraisal.pk])
        )
        review_create = self.client.get(
            reverse(
                "payroll:review_create",
                args=[self.appraisal.pk, self.appraisee.pk],
            )
        )
        review_detail = self.client.get(
            reverse("payroll:review_detail", args=[review.pk])
        )

        self.assertEqual(appraisal_list.status_code, 200)
        self.assertEqual(appraisal_detail.status_code, 200)
        self.assertEqual(review_create.status_code, 200)
        self.assertEqual(review_detail.status_code, 200)
