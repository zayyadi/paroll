"""WebSocket URL routing for realtime notifications and company chat."""

from django.urls import re_path
from payroll.consumers import CompanyChatConsumer, NotificationConsumer

websocket_urlpatterns = [
    # WebSocket endpoint for real-time notifications
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
    re_path(r"ws/chat/company/$", CompanyChatConsumer.as_asgi()),
    re_path(r"ws/chat/rooms/(?P<room_id>\\d+)/$", CompanyChatConsumer.as_asgi()),
]
