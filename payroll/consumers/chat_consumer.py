import json
import logging

from channels.db import aclose_old_connections, database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from company.utils import get_user_company
from payroll.services.chat_service import (
    company_chat_group_name,
    create_company_chat_message,
    create_room_message,
    get_company_chat_room,
    is_room_member,
    mark_company_chat_read,
    serialize_company_chat_message,
)


logger = logging.getLogger(__name__)


class CompanyChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        await aclose_old_connections()

        try:
            self.employee, self.room, self.group_name = await self._resolve_context()
        except ValueError as exc:
            logger.warning("Rejected company chat connection for user %s: %s", self.user.id, exc)
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection",
                    "status": "connected",
                    "room": {
                        "id": self.room.id,
                        "name": self.room.name,
                        "slug": self.room.slug,
                    },
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        await aclose_old_connections()
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON format.")
            return

        action = data.get("action")
        if action == "send_message":
            await self._handle_send_message(data.get("body", ""))
            return
        if action == "mark_read":
            await self._handle_mark_read(data.get("message_id"))
            return
        if action == "ping":
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "pong",
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )
            return

        await self._send_error(f"Unknown action: {action}")

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat.message",
                    "message": event["message"],
                }
            )
        )

    async def _handle_send_message(self, body):
        try:
            message = await self._create_message(body)
        except ValueError as exc:
            await self._send_error(str(exc))
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "message": serialize_company_chat_message(message),
            },
        )

    async def _handle_mark_read(self, message_id):
        state = await self._mark_read(message_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat.read",
                    "last_read_message_id": state.last_read_message_id,
                    "last_read_at": state.last_read_at.isoformat(),
                }
            )
        )

    async def _send_error(self, message):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "message": message,
                }
            )
        )

    @database_sync_to_async
    def _resolve_context(self):
        company = get_user_company(self.user)
        if company is None:
            raise ValueError("No active company is configured for this account.")

        try:
            employee = self.user.employee_user
        except ObjectDoesNotExist as exc:
            raise ValueError("No employee profile is linked to this account.") from exc

        if employee.company_id != company.id:
            raise ValueError("Employee profile is not attached to the active company.")

        room_id = None
        url_route = self.scope.get("url_route", {})
        if url_route:
            room_id = url_route.get("kwargs", {}).get("room_id")
        if room_id:
            room = company.chat_rooms.filter(id=room_id).first()
            if room is None:
                raise ValueError("Chat room does not exist.")
            if room.room_type != room.TYPE_COMPANY and not is_room_member(room, employee):
                raise ValueError("You are not a member of this chat room.")
            group_name = f"chat.room.{room.id}"
        else:
            room = get_company_chat_room(company)
            group_name = company_chat_group_name(company.id)
        return employee, room, group_name

    @database_sync_to_async
    def _create_message(self, body):
        if self.room.room_type == self.room.TYPE_COMPANY:
            return create_company_chat_message(self.employee, body)
        return create_room_message(self.room, self.employee, body)

    @database_sync_to_async
    def _mark_read(self, message_id):
        message = None
        if message_id:
            message = self.room.messages.get(pk=message_id)
        return mark_company_chat_read(self.room, self.employee, message)
