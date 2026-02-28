from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
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
