from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from company.models import Company
from marketing.models import Competitor, LeadInquiry, MarketingEvent


class CompetitorTrackingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Intel Co")
        self.superuser = get_user_model().objects.create_user(
            email="intel-admin@example.com",
            password="testpass123",
            first_name="Intel",
            last_name="Admin",
            company=self.company,
            active_company=self.company,
            is_staff=True,
            is_superuser=True,
        )
        self.regular_user = get_user_model().objects.create_user(
            email="employee@example.com",
            password="testpass123",
            first_name="Plain",
            last_name="Employee",
            company=self.company,
            active_company=self.company,
        )

    def test_seed_migration_populates_researched_vendors(self):
        names = set(Competitor.objects.values_list("name", flat=True))
        for expected in ["HRPayHub", "SeamlessHR", "Workpay", "HumanManager", "Bento Africa"]:
            self.assertIn(expected, names)

    def test_seeded_vendors_carry_pricing_and_source(self):
        hrpayhub = Competitor.objects.get(name="HRPayHub")
        self.assertIn("499", hrpayhub.pricing_summary)
        self.assertIsNotNone(hrpayhub.last_verified)
        self.assertTrue(hrpayhub.source_url)
        self.assertEqual(hrpayhub.feature_status("published_pricing"), "yes")

    def test_feature_status_defaults_to_unknown(self):
        competitor = Competitor.objects.create(name="No Data Co")
        self.assertEqual(competitor.feature_status("statutory_paye"), "unknown")

    def test_is_stale_flags_unverified_and_old_records(self):
        competitor = Competitor.objects.create(name="Stale Co")
        self.assertTrue(competitor.is_stale(date(2026, 8, 14)))

        competitor.last_verified = date(2026, 8, 1)
        self.assertFalse(competitor.is_stale(date(2026, 8, 14)))

        competitor.last_verified = date(2026, 1, 1)
        self.assertTrue(competitor.is_stale(date(2026, 8, 14)))

    def test_tracking_page_requires_login(self):
        response = self.client.get(reverse("marketing:competitor_tracking"))
        self.assertEqual(response.status_code, 302)

    def test_tracking_page_forbidden_for_regular_user(self):
        self.client.login(email=self.regular_user.email, password="testpass123")
        response = self.client.get(reverse("marketing:competitor_tracking"))
        self.assertEqual(response.status_code, 403)

    def test_tracking_page_renders_for_superuser(self):
        self.client.login(email=self.superuser.email, password="testpass123")
        response = self.client.get(reverse("marketing:competitor_tracking"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Capability Gap Matrix")
        self.assertContains(response, "HRPayHub")
        self.assertContains(response, "Bento Africa")
        self.assertContains(response, "Published ₦ pricing")

    def test_matrix_has_one_row_per_catalog_feature(self):
        from marketing.models import FEATURE_CATALOG

        self.client.login(email=self.superuser.email, password="testpass123")
        response = self.client.get(reverse("marketing:competitor_tracking"))
        for key, label, _ in FEATURE_CATALOG:
            with self.subTest(feature=key):
                self.assertContains(response, label)


class PricingPageTests(TestCase):
    """The pricing page publishes naira tiers with a monthly/annual toggle."""

    def test_pricing_page_renders_published_tiers(self):
        response = self.client.get(reverse("marketing:pricing"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for name in ["Free", "Starter", "Growth", "Enterprise"]:
            self.assertIn(name, content)
        self.assertIn("₦499", content)
        self.assertIn("₦999", content)
        # The JS toggle carries both billings per tier.
        self.assertIn('data-monthly="499"', content)
        self.assertIn('data-annual="449"', content)
        self.assertIn('data-annual="899"', content)
        self.assertIn("Save 10%", content)

    def test_pricing_page_free_tier_is_zero(self):
        response = self.client.get(reverse("marketing:pricing"))
        content = response.content.decode()
        self.assertIn('data-monthly="0"', content)
        self.assertIn('data-annual="0"', content)

    def test_pricing_page_uses_seeded_plans(self):
        from marketing.models import PricingPlan

        slugs = set(PricingPlan.objects.values_list("slug", flat=True))
        self.assertEqual(slugs, {"free", "starter", "growth", "enterprise"})
        growth = PricingPlan.objects.get(slug="growth")
        self.assertTrue(growth.highlight)
        enterprise = PricingPlan.objects.get(slug="enterprise")
        self.assertTrue(enterprise.is_custom)


class MarketingPublicPagesTests(TestCase):
    def test_landing_page_is_public(self):
        response = self.client.get(reverse("marketing:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "marketing/landing.html")

    def test_landing_page_includes_basic_seo_meta_tags(self):
        response = self.client.get(reverse("marketing:landing"))
        self.assertContains(response, 'name="description"')
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, "from calculation to remittance")

    def test_landing_page_uses_stitch_editorial_design_language(self):
        response = self.client.get(reverse("marketing:landing"))
        self.assertContains(response, "Editorial Command")
        self.assertContains(response, "Manrope")
        self.assertContains(response, "Professional Editorial Management")

    def test_core_marketing_pages_render(self):
        pages = [
            ("marketing:pricing", "marketing/pricing.html"),
            ("marketing:about", "marketing/about.html"),
            ("marketing:support", "marketing/support.html"),
            ("marketing:security", "marketing/security.html"),
            ("marketing:contact", "marketing/contact.html"),
            ("marketing:privacy", "marketing/privacy.html"),
            ("marketing:terms", "marketing/terms.html"),
            ("marketing:cookies", "marketing/cookies.html"),
        ]

        for route_name, template_name in pages:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template_name)


class ContactLeadCaptureTests(TestCase):
    def test_contact_form_submission_creates_lead_inquiry(self):
        payload = {
            "full_name": "Ada Lovelace",
            "work_email": "ada@example.com",
            "company_name": "Analytical Engines Ltd",
            "company_size": "11-50",
            "message": "We need a payroll migration plan.",
        }

        response = self.client.post(reverse("marketing:contact"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LeadInquiry.objects.count(), 1)

        inquiry = LeadInquiry.objects.first()
        self.assertEqual(inquiry.full_name, payload["full_name"])
        self.assertEqual(inquiry.work_email, payload["work_email"])
        self.assertEqual(inquiry.company_name, payload["company_name"])
        self.assertEqual(inquiry.status, LeadInquiry.STATUS_NEW)


class MarketingAnalyticsTests(TestCase):
    def test_landing_page_view_creates_marketing_event(self):
        self.client.get(reverse("marketing:landing"))
        event = MarketingEvent.objects.latest("created_at")
        self.assertEqual(event.event_name, "marketing.page_view")
        self.assertEqual(event.path, reverse("marketing:landing"))

    def test_contact_submission_creates_conversion_event(self):
        payload = {
            "full_name": "Grace Hopper",
            "work_email": "grace@example.com",
            "company_name": "Compiler Corp",
            "company_size": "51-200",
            "message": "Need onboarding support.",
        }
        self.client.post(reverse("marketing:contact"), payload)
        event = MarketingEvent.objects.latest("created_at")
        self.assertEqual(event.event_name, "marketing.contact_submitted")


class LeadInquiryWorkflowTests(TestCase):
    def test_lead_can_be_assigned_and_status_updated(self):
        user = get_user_model().objects.create_user(
            email="agent@example.com",
            password="StrongPass123!",
            first_name="Agent",
            last_name="One",
        )
        inquiry = LeadInquiry.objects.create(
            full_name="Linus Torvalds",
            work_email="linus@example.com",
            company_name="Kernel Works",
            company_size="11-50",
            message="Pricing information request",
        )
        inquiry.assignee = user
        inquiry.status = LeadInquiry.STATUS_CONTACTED
        inquiry.save(update_fields=["assignee", "status"])

        inquiry.refresh_from_db()
        self.assertEqual(inquiry.assignee, user)
        self.assertEqual(inquiry.status, LeadInquiry.STATUS_CONTACTED)
