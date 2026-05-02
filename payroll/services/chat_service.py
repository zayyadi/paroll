from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from payroll.models import (
    CompanyChatMessage,
    CompanyChatReadState,
    CompanyChatRoom,
    CompanyChatRoomMember,
)


CHAT_MESSAGE_LIMIT = 2000


def company_chat_group_name(company_id: int) -> str:
    return f"chat.company.{company_id}"


def room_chat_group_name(room_id: int) -> str:
    return f"chat.room.{room_id}"


def get_company_chat_room(company):
    room, _ = CompanyChatRoom.get_or_create_default(company)
    return room


def is_room_member(room, employee) -> bool:
    if room.room_type == CompanyChatRoom.TYPE_COMPANY:
        return employee.company_id == room.company_id
    return CompanyChatRoomMember.objects.filter(
        room=room,
        employee=employee,
        is_active=True,
    ).exists()


def add_room_member(room, employee, role=CompanyChatRoomMember.ROLE_MEMBER):
    return CompanyChatRoomMember.objects.get_or_create(
        room=room,
        employee=employee,
        defaults={"role": role},
    )[0]


def get_or_create_direct_room(company, employee_a, employee_b):
    if employee_a.company_id != company.id or employee_b.company_id != company.id:
        raise ValueError("Direct rooms must be within the same company.")
    if employee_a.id == employee_b.id:
        raise ValueError("Direct rooms require two distinct employees.")

    ordered = sorted([employee_a.id, employee_b.id])
    slug = f"dm-{ordered[0]}-{ordered[1]}"
    room, created = CompanyChatRoom.objects.get_or_create(
        company=company,
        slug=slug,
        defaults={
            "name": "Direct Message",
            "room_type": CompanyChatRoom.TYPE_DIRECT,
            "created_by": employee_a,
        },
    )
    if room.room_type != CompanyChatRoom.TYPE_DIRECT:
        raise ValueError("Room slug already exists for non-direct room.")

    add_room_member(room, employee_a)
    add_room_member(room, employee_b)
    return room, created


def create_company_chat_message(employee, body: str) -> CompanyChatMessage:
    if employee is None or employee.company_id is None:
        raise ValueError("A company-linked employee profile is required to chat.")

    message_body = (body or "").strip()
    if not message_body:
        raise ValueError("Message body cannot be empty.")
    if len(message_body) > CHAT_MESSAGE_LIMIT:
        raise ValueError(f"Message body cannot exceed {CHAT_MESSAGE_LIMIT} characters.")

    room = get_company_chat_room(employee.company)
    return CompanyChatMessage.objects.create(
        room=room,
        sender=employee,
        body=message_body,
    )


def create_room_message(room, employee, body: str) -> CompanyChatMessage:
    if room.company_id != employee.company_id:
        raise ValueError("Employee must belong to the same company as the room.")
    if not is_room_member(room, employee):
        raise ValueError("Employee is not a member of this room.")

    message_body = (body or "").strip()
    if not message_body:
        raise ValueError("Message body cannot be empty.")
    if len(message_body) > CHAT_MESSAGE_LIMIT:
        raise ValueError(f"Message body cannot exceed {CHAT_MESSAGE_LIMIT} characters.")

    return CompanyChatMessage.objects.create(
        room=room,
        sender=employee,
        body=message_body,
    )


def mark_company_chat_read(room, employee, message=None) -> CompanyChatReadState:
    if employee.company_id != room.company_id:
        raise ValueError("Employee and room must belong to the same company.")

    if message is not None and message.room_id != room.id:
        raise ValueError("Read marker must point to a message in the same room.")

    state, _ = CompanyChatReadState.objects.get_or_create(
        room=room,
        employee=employee,
    )
    state.last_read_message = message
    state.last_read_at = timezone.now()
    state.save(update_fields=["last_read_message", "last_read_at", "updated_at"])
    return state


def serialize_company_chat_message(message: CompanyChatMessage) -> dict:
    sender = message.sender
    sender_user = getattr(sender, "user", None)
    full_name = " ".join(part for part in [sender.first_name, sender.last_name] if part).strip()
    return {
        "id": message.id,
        "room": message.room_id,
        "room_slug": message.room.slug,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
        "sender": {
            "id": sender.id,
            "email": getattr(sender_user, "email", ""),
            "full_name": full_name or getattr(sender_user, "email", "Unknown sender"),
        },
    }


def broadcast_company_chat_message(message: CompanyChatMessage) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    payload = serialize_company_chat_message(message)
    if message.room.room_type == CompanyChatRoom.TYPE_COMPANY:
        group_name = company_chat_group_name(message.room.company_id)
    else:
        group_name = room_chat_group_name(message.room_id)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "chat.message",
            "message": payload,
        },
    )
