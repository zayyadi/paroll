"""WebSocket URL routing for realtime notifications."""

from django.urls import re_path
from payroll.consumers import NotificationConsumer

websocket_urlpatterns = [
    # WebSocket endpoint for real-time notifications
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
]
