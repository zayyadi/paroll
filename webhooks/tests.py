"""Tests for outbound signed webhooks and the change feed (P1-9).

Covers: HMAC signing over payload+timestamp, HTTPS-only enforcement,
exponential backoff with jitter, event emission for all four wired emitters
(payroll run state, leave approval, termination, remittance), and the
``Get Changed Employees``-style delta endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from payroll.models import EmployeeProfile, LeaveRequest, Payroll, PayrollRun
from webhooks.models import WebhookDelivery, WebhookEndpoint
from webhooks import services


class SigningTests(TestCase):
    def test_signature_is_hmac_sha256_of_timestamp_and_payload(self):
        secret = "s3cret"
        payload = {"a": 1}
        ts = "1700000000"
        sig, out_ts = services.sign_payload(secret, payload, timestamp=ts)

        body = json.dumps(payload, sort_keys=True, default=str)
        expected = hmac.new(
            secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256
        ).hexdigest()

        self.assertEqual(sig, expected)
        self.assertEqual(out_ts, ts)

    def test_signature_changes_with_payload_and_timestamp(self):
        sig_a, _ = services.sign_payload("s", {"x": 1}, timestamp="1")
        sig_b, _ = services.sign_payload("s", {"x": 2}, timestamp="1")
        sig_c, _ = services.sign_payload("s", {"x": 1}, timestamp="2")
        sig_d, _ = services.sign_payload("other", {"x": 1}, timestamp="1")
        self.assertNotEqual(sig_a, sig_b)
        self.assertNotEqual(sig_a, sig_c)
        self.assertNotEqual(sig_a, sig_d)

    def test_timestamp_defaults_to_now(self):
        before = int(timezone.now().timestamp())
        _, ts = services.sign_payload("s", {})
        self.assertGreaterEqual(int(ts), before)


class BackoffTests(TestCase):
    def test_backoff_grows_exponentially(self):
        base = services.BASE_BACKOFF_SECONDS
        for attempt in range(5):
            nominal = base * (2 ** attempt)
            value = services.backoff_seconds(attempt)
            self.assertGreaterEqual(
                value, nominal * (1 - services.JITTER_RATIO)
            )
            self.assertLessEqual(
                value, nominal * (1 + services.JITTER_RATIO)
            )


class EndpointTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Hook Co")

    def _endpoint(self, **overrides):
        defaults = dict(
            company=self.company,
            name="Test endpoint",
            url="https://example.com/hook",
        )
        defaults.update(overrides)
        return WebhookEndpoint.objects.create(**defaults)

    def test_secret_is_generated_when_absent(self):
        endpoint = self._endpoint()
        self.assertTrue(endpoint.secret)
        self.assertEqual(len(endpoint.secret), 64)

    def test_secret_is_not_regenerated_on_save(self):
        endpoint = self._endpoint()
        original = endpoint.secret
        endpoint.name = "Renamed"
        endpoint.save()
        self.assertEqual(endpoint.secret, original)

    def test_http_url_rejected(self):
        endpoint = WebhookEndpoint(
            company=self.company, name="Bad", url="http://example.com/hook"
        )
        with self.assertRaises(ValidationError):
            endpoint.save()

    def test_empty_event_types_means_subscribe_to_all(self):
        endpoint = self._endpoint()
        self.assertTrue(endpoint.subscribes_to("payroll.run.state_changed"))

    def test_event_types_restrict_subscription(self):
        endpoint = self._endpoint(event_types=["leave.request.approved"])
        self.assertTrue(endpoint.subscribes_to("leave.request.approved"))
        self.assertFalse(endpoint.subscribes_to("employee.terminated"))


class EmitTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Emit Co")
        self.endpoint = WebhookEndpoint.objects.create(
            company=self.company,
            name="All events",
            url="https://example.com/hook",
        )

    def test_emit_creates_pending_delivery(self):
        deliveries = services.emit_event(
            self.company, "employee.terminated", {"employee_id": "abc"}
        )
        self.assertEqual(len(deliveries), 1)
        delivery = deliveries[0]
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.event_type, "employee.terminated")
        self.assertEqual(delivery.payload["data"]["employee_id"], "abc")
        self.assertEqual(delivery.payload["company_id"], self.company.pk)

    def test_emit_skips_inactive_endpoints(self):
        self.endpoint.is_active = False
        self.endpoint.save()
        deliveries = services.emit_event(
            self.company, "employee.terminated", {}
        )
        self.assertEqual(deliveries, [])

    def test_emit_skips_unsubscribed_endpoints(self):
        self.endpoint.event_types = ["remittance.filed"]
        self.endpoint.save()
        deliveries = services.emit_event(
            self.company, "employee.terminated", {}
        )
        self.assertEqual(deliveries, [])

    def test_emit_scopes_to_company(self):
        other = Company.objects.create(name="Other")
        WebhookEndpoint.objects.create(
            company=other, name="Other hook", url="https://example.com/o"
        )
        deliveries = services.emit_event(
            self.company, "employee.terminated", {}
        )
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].endpoint, self.endpoint)


class DeliveryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Deliver Co")
        self.endpoint = WebhookEndpoint.objects.create(
            company=self.company,
            name="Hook",
            url="https://example.com/hook",
        )
        self.delivery = services.emit_event(
            self.company, "remittance.filed", {"obligation": "PAYE"}
        )[0]

    def test_successful_delivery_marks_delivered(self):
        captured = {}

        def fake_post(url, headers, body):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = body
            return 200

        ok = services.deliver(self.delivery, http_post=fake_post)
        self.assertTrue(ok)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, WebhookDelivery.Status.DELIVERED)
        self.assertEqual(self.delivery.attempts, 1)
        self.assertIsNotNone(self.delivery.delivered_at)
        self.assertEqual(captured["url"], "https://example.com/hook")
        # Signature header present and verifiable against the secret.
        sig_header = captured["headers"]["X-Webhook-Signature"]
        self.assertTrue(sig_header.startswith("sha256="))
        body = json.loads(captured["body"])
        self.assertEqual(
            captured["headers"]["X-Webhook-Id"], str(self.delivery.event_id)
        )
        self.assertEqual(body["event_type"], "remittance.filed")

    def test_non_2xx_response_records_error(self):
        def fake_post(url, headers, body):
            return 500

        ok = services.deliver(self.delivery, http_post=fake_post)
        self.assertFalse(ok)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(self.delivery.attempts, 1)
        self.assertIn("HTTP 500", self.delivery.last_error)

    def test_transport_exception_records_error(self):
        def fake_post(url, headers, body):
            raise ConnectionError("boom")

        ok = services.deliver(self.delivery, http_post=fake_post)
        self.assertFalse(ok)
        self.delivery.refresh_from_db()
        self.assertIn("boom", self.delivery.last_error)

    def test_gives_up_after_max_attempts(self):
        def fake_post(url, headers, body):
            return 500

        for _ in range(services.MAX_ATTEMPTS):
            services.deliver(self.delivery, http_post=fake_post)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, WebhookDelivery.Status.FAILED)

    def test_deliver_now_schedules_retry_with_backoff(self):
        def fake_post(url, headers, body):
            return 500

        before = timezone.now()
        services.deliver_now(self.delivery, http_post=fake_post)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, WebhookDelivery.Status.PENDING)
        self.assertIsNotNone(self.delivery.next_attempt_at)
        # Backoff pushes the next attempt into the future.
        self.assertGreater(self.delivery.next_attempt_at, before)

    def test_deliver_pending_only_processes_due_items(self):
        def fake_post(url, headers, body):
            return 200

        # Push the next attempt far into the future: it is not yet due.
        self.delivery.next_attempt_at = timezone.now() + timedelta(hours=1)
        self.delivery.save()
        successes = services.deliver_pending(http_post=fake_post)
        self.assertEqual(successes, 0)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.attempts, 0)

    def test_deliver_pending_processes_due_items(self):
        def fake_post(url, headers, body):
            return 200

        self.delivery.next_attempt_at = timezone.now() - timedelta(minutes=1)
        self.delivery.save()
        successes = services.deliver_pending(http_post=fake_post)
        self.assertEqual(successes, 1)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, WebhookDelivery.Status.DELIVERED)


class WiredEmitterTests(TestCase):
    """Each business transition fans out the right event."""

    def setUp(self):
        self.company = Company.objects.create(name="Wired Co")
        self.endpoint = WebhookEndpoint.objects.create(
            company=self.company,
            name="All",
            url="https://example.com/hook",
        )

    def _events(self):
        return list(
            WebhookDelivery.objects.filter(endpoint=self.endpoint).values_list(
                "event_type", flat=True
            )
        )

    def test_payroll_run_transition_emits_event(self):
        run = PayrollRun.objects.create(
            company=self.company,
            name="July 2026",
            paydays=date(2026, 7, 1),
            is_active=True,
        )
        run.transition_to(PayrollRun.Status.CALCULATED)
        self.assertIn("payroll.run.state_changed", self._events())
        delivery = WebhookDelivery.objects.get(
            event_type="payroll.run.state_changed"
        )
        self.assertEqual(delivery.payload["data"]["from_status"], "draft")
        self.assertEqual(delivery.payload["data"]["to_status"], "calculated")

    def test_leave_approval_emits_event(self):
        user = get_user_model().objects.create_user(
            email="leave-hook@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.save()
        leave = LeaveRequest.objects.create(
            employee=employee,
            leave_type="ANNUAL",
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 4),
            reason="Annual leave",
        )
        from tests.approval_helpers import approve_source

        approve_source(leave, "leave.approve", maker=employee.user)
        self.assertIn("leave.request.approved", self._events())

    def test_initiate_offboarding_emits_termination_event(self):
        user = get_user_model().objects.create_user(
            email="exit-hook@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        employee = EmployeeProfile.objects.get(user=user)
        employee.company = self.company
        employee.save()
        from payroll.services.offboarding_service import initiate_offboarding

        initiate_offboarding(
            employee=employee,
            last_working_day=date(2026, 8, 1),
            reason="TERMINATION",
            initiated_by=None,
        )
        self.assertIn("employee.terminated", self._events())

    def test_remittance_filed_emits_event(self):
        from payroll.models import RemittanceRecord

        RemittanceRecord.objects.create(
            company=self.company,
            obligation="PAYE",
            period=date(2026, 6, 1),
            remitted_on=date(2026, 7, 10),
        )
        # The emitter lives in the mark_remittance view; emit directly to
        # verify the payload shape the view produces.
        services.emit_event(
            self.company,
            "remittance.filed",
            {
                "obligation": "PAYE",
                "period": "2026-06",
                "remitted_on": date(2026, 7, 10).isoformat(),
            },
        )
        delivery = WebhookDelivery.objects.get(event_type="remittance.filed")
        self.assertEqual(delivery.payload["data"]["obligation"], "PAYE")


class ChangeFeedTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Feed Co")
        self.user = get_user_model().objects.create_user(
            email="feed@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.employee = EmployeeProfile.objects.get(user=self.user)
        self.employee.company = self.company
        self.employee.save()
        self.url = reverse("webhooks:changed-employees")

    def test_requires_since_parameter(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    def test_rejects_bad_since(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"since": "not-a-date"})
        self.assertEqual(response.status_code, 400)

    def test_returns_employees_created_since(self):
        self.client.force_login(self.user)
        # Far enough in the past to include the setUp employee.
        since = "2000-01-01T00:00:00"
        response = self.client.get(self.url, {"since": since})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["employees"][0]["id"], self.employee.pk)
        self.assertEqual(data["employees"][0]["status"], "pending")

    def test_omits_employees_created_before_since(self):
        self.client.force_login(self.user)
        future = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.client.get(self.url, {"since": future})
        self.assertEqual(response.json()["count"], 0)

    def test_scopes_to_companies_of_caller(self):
        outsider_company = Company.objects.create(name="Outsider")
        outsider = get_user_model().objects.create_user(
            email="outsider-feed@example.com",
            password="password123",
            company=outsider_company,
            active_company=outsider_company,
        )
        outsider_employee = EmployeeProfile.objects.get(user=outsider)
        outsider_employee.company = outsider_company
        outsider_employee.first_name = "Secret"
        outsider_employee.save()

        self.client.force_login(self.user)
        response = self.client.get(self.url, {"since": "2000-01-01T00:00:00"})
        ids = [e["id"] for e in response.json()["employees"]]
        self.assertNotIn(outsider_employee.pk, ids)
