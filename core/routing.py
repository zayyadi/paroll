"""
WebSocket URL Routing Configuration

This module defines the WebSocket URL patterns for real-time notifications
using Django Channels.

Architecture Reference: plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md (Section 12)
"""

from django.urls import re_path
from payroll.consumers import NotificationConsumer

websocket_urlpatterns = [
    # WebSocket endpoint for real-time notifications
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
]
