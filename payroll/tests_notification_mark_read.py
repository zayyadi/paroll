from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from payroll.handlers.delivery_handlers import EmailHandler
from payroll.models import Notification


User = get_user_model()


class NotificationMarkReadTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Notify Co")
        self.user = User.objects.create_user(
            email="notify@test.com",
            password="password123",
            first_name="Notify",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])

        self.notification = Notification.objects.create(
            recipient=self.employee,
            notification_type="INFO",
            title="Test notification",
            message="Test message",
            is_read=False,
        )
        self.read_notification = Notification.objects.create(
            recipient=self.employee,
            notification_type="INFO",
            title="Read notification",
            message="Already read",
            is_read=True,
            read_at=timezone.now(),
        )

    def test_mark_notification_read_updates_state(self):
        self.client.login(email=self.user.email, password="password123")
        url = reverse("payroll:mark_notification_read", args=[self.notification.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["unread_count"], 0)

        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
        self.assertIsNotNone(self.notification.read_at)

    def test_notification_dropdown_renders_data_action_controls(self):
        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(reverse("payroll:notification_dropdown"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notification-action="open"')
        self.assertContains(response, f'data-notification-id="{self.notification.id}"')
        self.assertContains(response, "Notifications")
        self.assertNotContains(response, "absolute right-0")
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "<script")

    def test_notification_list_renders_data_action_controls(self):
        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(reverse("payroll:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notification-action="mark-read"')
        self.assertContains(response, 'data-notification-action="mark-unread"')
        self.assertContains(response, 'data-notification-action="delete"')
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "onchange=")
        self.assertNotContains(response, "onkeyup=")

    def test_base_notification_button_uses_vanilla_toggle_controls(self):
        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(reverse("payroll:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="#main-content"')
        self.assertContains(response, 'id="main-content"')
        self.assertContains(response, 'aria-label="View notifications"')
        self.assertContains(response, 'id="notificationButton"')
        self.assertContains(response, 'id="notificationDropdownPanel"')
        self.assertContains(response, 'aria-controls="notificationDropdownPanel"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, "prefers-reduced-motion")
        self.assertContains(response, "setupNotificationToggle")
        self.assertNotContains(response, "loadNotifications(); notificationsOpen")

    def test_notification_detail_renders_data_action_controls(self):
        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(
            reverse("payroll:notification_detail", args=[self.notification.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notification-action="mark-unread"')
        self.assertContains(response, 'data-notification-action="delete"')
        self.assertContains(response, 'data-notification-redirect=')
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "/payroll/notifications/")

    def test_notification_list_read_filter_shows_only_read_notifications(self):
        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(reverse("payroll:notifications"), {"read": "read"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Read notification")
        self.assertNotContains(response, "Test notification")

    def test_aggregated_notifications_render_grouped_items(self):
        grouped = Notification.objects.create(
            recipient=self.employee,
            notification_type="INFO",
            title="Grouped notification",
            message="Grouped message",
            is_aggregated=True,
            aggregation_key="test:grouped",
            aggregation_count=1,
        )
        grouped.aggregated_with.add(self.notification)

        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(reverse("payroll:aggregated_notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grouped notification")
        self.assertContains(response, "Test notification")
        self.assertContains(response, 'data-aggregate-toggle="')
        self.assertContains(response, 'data-notification-action="mark-read"')
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "/payroll/notifications/")

    def test_notification_digests_use_standard_post_form(self):
        Notification.objects.create(
            recipient=self.employee,
            notification_type="INFO",
            title="Daily digest",
            message="Digest message",
            is_aggregated=True,
            aggregation_key="digest:daily:test",
            aggregation_count=2,
        )

        self.client.login(email=self.user.email, password="password123")
        response = self.client.get(reverse("payroll:notification_digests"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily digest")
        self.assertContains(response, reverse("payroll:trigger_manual_digest"))
        self.assertNotContains(response, "onclick=")
        self.assertNotContains(response, "/payroll/notifications/")

    def test_delete_notification_soft_deletes(self):
        self.client.login(email=self.user.email, password="password123")
        url = reverse("payroll:delete_notification", args=[self.notification.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_deleted)

    def test_delete_all_read_soft_deletes_only_read_notifications(self):
        self.client.login(email=self.user.email, password="password123")
        url = reverse("payroll:delete_all_read")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["updated_count"], 1)

        self.read_notification.refresh_from_db()
        self.notification.refresh_from_db()
        self.assertTrue(self.read_notification.is_deleted)
        self.assertFalse(self.notification.is_deleted)

    def test_mark_all_read_clears_cached_badge_count(self):
        cache.set(f"notifications:{self.employee.id}:unread_count", 2, 300)

        self.client.login(email=self.user.email, password="password123")
        response = self.client.post(reverse("payroll:mark_all_read"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertEqual(cache.get(f"notifications:{self.employee.id}:unread_count"), 0)

        count_response = self.client.get(reverse("payroll:notification_count"))
        self.assertEqual(count_response.status_code, 200)
        self.assertEqual(count_response.json()["unread_count"], 0)

    def test_email_handler_renders_default_template_for_generic_notification(self):
        notification = Notification.objects.create(
            recipient=self.employee,
            notification_type="INFO",
            title="System update",
            message="Your account settings were updated.",
            action_url="/payroll/notifications/",
            priority="LOW",
        )

        subject, html_content, text_content = EmailHandler().render_template(
            notification, str(self.user.id)
        )

        self.assertIn("System update", subject)
        self.assertIn("System update", html_content)
        self.assertIn("Your account settings were updated.", html_content)
        self.assertIn("Your account settings were updated.", text_content)
        self.assertIn("/payroll/notifications/", text_content)

    def test_email_handler_renders_iou_approved_template(self):
        notification = Notification.objects.create(
            recipient=self.employee,
            notification_type="IOU_APPROVED",
            title="IOU approved",
            message="Your IOU request has been approved.",
            action_url="/payroll/iou/my-requests/",
            metadata={"amount": "50000.00", "tenor": "3"},
            priority="HIGH",
        )

        subject, html_content, text_content = EmailHandler().render_template(
            notification, str(self.user.id)
        )

        self.assertIn("IOU approved", subject)
        self.assertIn("IOU request approved", html_content)
        self.assertIn("Your IOU request has been approved.", html_content)
        self.assertIn("50000.00", html_content)
        self.assertIn("3", text_content)
