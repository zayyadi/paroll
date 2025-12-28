"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

This configuration supports both HTTP and WebSocket connections using Django Channels
for real-time notification delivery.

Architecture Reference: plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md (Section 12)

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Initialize Django ASGI application
django_asgi_app = get_asgi_application()

# Import WebSocket URL patterns after Django is initialized
from core.routing import websocket_urlpatterns

# Configure ASGI application to handle both HTTP and WebSocket protocols
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
