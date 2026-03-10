from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from marketing.models import LeadInquiry, MarketingEvent


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
        self.assertContains(response, "Run compliant payroll")

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
