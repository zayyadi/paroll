import json
from unittest.mock import AsyncMock
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from company.models import Company, CompanyMembership
from payroll.consumers import CompanyChatConsumer


User = get_user_model()


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class CompanyChatIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Realtime Chat Co")
        self.user = User.objects.create_user(
            email="realtime@test.com",
            password="password123",
            first_name="Rita",
            last_name="Realtime",
            company=self.company,
            active_company=self.company,
        )
        CompanyMembership.objects.get_or_create(
            user=self.user,
            company=self.company,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        self.employee = self.user.employee_user
        self.employee.company = self.company
        self.employee.first_name = "Rita"
        self.employee.last_name = "Realtime"
        self.employee.save()

    def test_company_chat_page_is_available(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payroll:company_chat"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Company Chat")

    def test_company_chat_page_has_rooms_panel(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payroll:company_chat"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chat Rooms")
        self.assertContains(response, "Search teammates")
        self.assertContains(response, "Start direct message")
        self.assertContains(response, "ws/chat/company/")

    def test_company_chat_consumer_connects_authenticated_employee(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")

        room = room_model.objects.create(
            company=self.company,
            slug="general",
            name="General",
        )

        consumer = CompanyChatConsumer()
        consumer.scope = {"user": self.user}
        consumer.channel_name = "test-company-chat"
        consumer.channel_layer = AsyncMock()
        consumer.channel_layer.group_add = AsyncMock()
        consumer.channel_layer.group_discard = AsyncMock()
        consumer.channel_layer.group_send = AsyncMock()
        consumer.accept = AsyncMock()
        consumer.send = AsyncMock()
        consumer.close = AsyncMock()
        consumer._resolve_context = AsyncMock(
            return_value=(self.employee, room, f"chat.company.{self.company.id}")
        )

        with patch("payroll.consumers.chat_consumer.aclose_old_connections", AsyncMock()):
            async_to_sync(consumer.connect)()

        consumer.accept.assert_awaited_once()
        connection_event = json.loads(consumer.send.await_args_list[0].kwargs["text_data"])
        self.assertEqual(connection_event["type"], "connection")
        self.assertEqual(connection_event["room"]["slug"], "general")

    def test_company_chat_consumer_forwards_group_message_to_client(self):
        consumer = CompanyChatConsumer()
        consumer.send = AsyncMock()

        async_to_sync(consumer.chat_message)(
            {
                "message": {
                    "id": 1,
                    "body": "Good morning, everyone.",
                }
            }
        )

        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        self.assertEqual(payload["type"], "chat.message")
        self.assertEqual(payload["message"]["body"], "Good morning, everyone.")
