from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from company.models import Company, CompanyMembership


User = get_user_model()


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class CompanyChatAPITests(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Chat Co A")
        self.company_b = Company.objects.create(name="Chat Co B")

        self.user_a = User.objects.create_user(
            email="chat-a@test.com",
            password="password123",
            first_name="Ada",
            last_name="Admin",
            company=self.company_a,
            active_company=self.company_a,
        )
        self.user_b = User.objects.create_user(
            email="chat-b@test.com",
            password="password123",
            first_name="Ben",
            last_name="Builder",
            company=self.company_b,
            active_company=self.company_b,
        )
        self.limited_user = User.objects.create_user(
            email="chat-limited@test.com",
            password="password123",
            first_name="Lena",
            last_name="Limited",
            company=self.company_a,
            active_company=self.company_a,
        )

        CompanyMembership.objects.get_or_create(
            user=self.user_a,
            company=self.company_a,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        CompanyMembership.objects.get_or_create(
            user=self.user_b,
            company=self.company_b,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        CompanyMembership.objects.get_or_create(
            user=self.limited_user,
            company=self.company_a,
            defaults={"role": CompanyMembership.ROLE_MEMBER, "is_default": False},
        )

        self.employee_a = self.user_a.employee_user
        self.employee_a.company = self.company_a
        self.employee_a.first_name = "Ada"
        self.employee_a.last_name = "Admin"
        self.employee_a.save()

        self.employee_b = self.user_b.employee_user
        self.employee_b.company = self.company_b
        self.employee_b.first_name = "Ben"
        self.employee_b.last_name = "Builder"
        self.employee_b.save()

        self.employee_a2 = self.limited_user.employee_user
        self.employee_a2.company = self.company_a
        self.employee_a2.first_name = "Lena"
        self.employee_a2.last_name = "Limited"
        self.employee_a2.save()

    def test_company_chat_message_list_is_tenant_scoped(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")
        message_model = apps.get_model("payroll", "CompanyChatMessage")

        room_a = room_model.objects.create(
            company=self.company_a,
            slug="general",
            name="General",
        )
        room_b = room_model.objects.create(
            company=self.company_b,
            slug="general",
            name="General",
        )
        message_model.objects.create(
            room=room_a,
            sender=self.employee_a,
            body="Hello from company A",
        )
        message_model.objects.create(
            room=room_b,
            sender=self.employee_b,
            body="Hello from company B",
        )

        self.client.force_authenticate(self.user_a)
        response = self.client.get(reverse("api:v1:company-chat-message-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["body"], "Hello from company A")

    def test_company_chat_message_create_uses_active_company_room(self):
        message_model = apps.get_model("payroll", "CompanyChatMessage")

        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            reverse("api:v1:company-chat-message-list"),
            {"body": "Team sync starts in five minutes."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["body"], "Team sync starts in five minutes.")
        self.assertEqual(message_model.objects.count(), 1)
        message = message_model.objects.select_related("room", "sender").get()
        self.assertEqual(message.room.company_id, self.company_a.id)
        self.assertEqual(message.sender_id, self.employee_a.id)

    def test_company_chat_mark_read_creates_read_state(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")
        message_model = apps.get_model("payroll", "CompanyChatMessage")
        read_state_model = apps.get_model("payroll", "CompanyChatReadState")

        room = room_model.objects.create(
            company=self.company_a,
            slug="general",
            name="General",
        )
        message = message_model.objects.create(
            room=room,
            sender=self.employee_a,
            body="Please review the handbook update.",
        )

        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            reverse("api:v1:company-chat-message-mark-read"),
            {"message_id": message.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        state = read_state_model.objects.get(room=room, employee=self.employee_a)
        self.assertEqual(state.last_read_message_id, message.id)

    def test_direct_room_is_created_once_for_pair(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")
        member_model = apps.get_model("payroll", "CompanyChatRoomMember")

        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            reverse("api:v1:company-chat-room-direct"),
            {"employee_id": self.employee_a2.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        room_id = response.data["id"]

        response_repeat = self.client.post(
            reverse("api:v1:company-chat-room-direct"),
            {"employee_id": self.employee_a2.id},
            format="json",
        )
        self.assertEqual(response_repeat.status_code, status.HTTP_200_OK)
        self.assertEqual(response_repeat.data["id"], room_id)

        room = room_model.objects.get(id=room_id)
        self.assertEqual(room.room_type, "direct")
        self.assertEqual(member_model.objects.filter(room=room).count(), 2)

    def test_room_list_returns_memberships(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")
        member_model = apps.get_model("payroll", "CompanyChatRoomMember")

        direct_room = room_model.objects.create(
            company=self.company_a,
            slug="dm-a",
            name="Direct",
            room_type="direct",
        )
        member_model.objects.create(room=direct_room, employee=self.employee_a)
        member_model.objects.create(room=direct_room, employee=self.employee_a2)

        self.client.force_authenticate(self.user_a)
        response = self.client.get(reverse("api:v1:company-chat-room-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        room_ids = {room["id"] for room in response.data["results"]}
        self.assertIn(direct_room.id, room_ids)

    def test_message_create_requires_membership_for_non_company_rooms(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")

        room = room_model.objects.create(
            company=self.company_a,
            slug="team-alpha",
            name="Team Alpha",
            room_type="team",
        )

        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            reverse("api:v1:company-chat-message-list"),
            {"body": "Hello", "room_id": room.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_room_candidates_returns_company_employees(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get(reverse("api:v1:company-chat-room-candidates"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.employee_a.id, ids)
        self.assertIn(self.employee_a2.id, ids)

    def test_room_add_member_requires_admin_role(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")
        member_model = apps.get_model("payroll", "CompanyChatRoomMember")

        room = room_model.objects.create(
            company=self.company_a,
            slug="team-alpha",
            name="Team Alpha",
            room_type="team",
        )
        member_model.objects.create(room=room, employee=self.employee_a, role="admin")

        self.client.force_authenticate(self.limited_user)
        response = self.client.post(
            reverse("api:v1:company-chat-room-add-member", args=[room.id]),
            {"employee_id": self.employee_a2.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unread_counts_returns_room_counts(self):
        room_model = apps.get_model("payroll", "CompanyChatRoom")
        message_model = apps.get_model("payroll", "CompanyChatMessage")

        room = room_model.objects.create(
            company=self.company_a,
            slug="team-alpha",
            name="Team Alpha",
            room_type="team",
        )
        message_model.objects.create(
            room=room,
            sender=self.employee_a,
            body="Hello",
        )

        self.client.force_authenticate(self.user_a)
        response = self.client.get(reverse("api:v1:company-chat-room-unread"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_unread", response.data)
        self.assertTrue(len(response.data["rooms"]) >= 1)
