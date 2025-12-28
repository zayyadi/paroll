"""
WebSocket Consumer for Real-time Notifications

This consumer handles WebSocket connections for real-time notification delivery.
It allows clients to receive notifications instantly without polling.

Architecture Reference: plans/NOTIFICATION_SYSTEM_ARCHITECTURE.md (Section 12)
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notification delivery.

    Features:
    - User authentication via Django session
    - Automatic group joining for user-specific notifications
    - Real-time notification broadcasting
    - Bidirectional communication (client can send actions)
    - Unread count updates
    """

    async def connect(self):
        """
        Handle WebSocket connection.

        Authenticates the user and joins their notification group.
        """
        # Get user from scope (set by AuthMiddlewareStack)
        self.user = self.scope.get("user")

        # Reject connection if user is not authenticated
        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt rejected")
            await self.close(code=4001)  # Custom code for unauthorized
            return

        # Get employee profile
        try:
            self.employee = await database_sync_to_async(
                lambda: self.user.employee_user
            )()
        except Exception as e:
            logger.error(f"Failed to get employee profile for user {self.user.id}: {e}")
            await self.close(code=4002)  # Custom code for no employee profile
            return

        # Create notification group for this user
        self.group_name = f"notifications_{self.employee.id}"

        # Join the notification group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Accept the WebSocket connection
        await self.accept()

        logger.info(
            f"WebSocket connected for user {self.user.id} (employee: {self.employee.id})"
        )

        # Send initial unread count
        await self.send_unread_count()

        # Send connection confirmation
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection",
                    "status": "connected",
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.

        Leaves the notification group and cleans up resources.
        """
        # Leave the notification group
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(
                f"WebSocket disconnected for user {self.user.id} "
                f"(employee: {self.employee.id}, code: {close_code})"
            )
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages from client.

        Supported actions:
        - mark_read: Mark a specific notification as read
        - mark_all_read: Mark all notifications as read
        - get_unread_count: Get current unread count
        - ping: Keep-alive ping
        """
        try:
            data = json.loads(text_data)
            action = data.get("action")

            logger.debug(
                f"Received WebSocket action: {action} from user {self.user.id}"
            )

            if action == "mark_read":
                notification_id = data.get("notification_id")
                await self.mark_as_read(notification_id)

            elif action == "mark_all_read":
                await self.mark_all_as_read()

            elif action == "get_unread_count":
                await self.send_unread_count()

            elif action == "ping":
                # Respond to keep-alive ping
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "pong",
                            "timestamp": timezone.now().isoformat(),
                        }
                    )
                )

            else:
                logger.warning(f"Unknown WebSocket action: {action}")
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "error",
                            "message": f"Unknown action: {action}",
                        }
                    )
                )

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                    }
                )
            )

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Internal server error",
                    }
                )
            )

    async def notification_message(self, event):
        """
        Handle new notification message from channel layer.

        This method is called when a notification is broadcast to the user's group.
        """
        notification = event.get("notification")

        # Send notification to client
        await self.send(
            text_data=json.dumps(
                {
                    "type": "notification",
                    "notification": notification,
                }
            )
        )

        # Update unread count
        await self.send_unread_count()

    async def notification_update(self, event):
        """
        Handle notification update message from channel layer.

        This is called when a notification is marked as read/unread.
        """
        notification_id = event.get("notification_id")
        update_type = event.get("update_type")

        # Send update to client
        await self.send(
            text_data=json.dumps(
                {
                    "type": "notification_update",
                    "notification_id": notification_id,
                    "update_type": update_type,
                }
            )
        )

        # Update unread count
        await self.send_unread_count()

    async def send_unread_count(self):
        """
        Send unread notification count to client.

        Queries the database for the current unread count and sends it to the client.
        """
        try:
            from payroll.models.notification import Notification

            count = await database_sync_to_async(
                lambda: Notification.objects.filter(
                    recipient=self.employee, is_read=False, is_deleted=False
                ).count()
            )()

            await self.send(
                text_data=json.dumps(
                    {
                        "type": "unread_count",
                        "count": count,
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")

    async def mark_as_read(self, notification_id):
        """
        Mark a specific notification as read.

        Args:
            notification_id: UUID of the notification to mark as read
        """
        try:
            from payroll.models.notification import Notification

            notification = await database_sync_to_async(Notification.objects.get)(
                id=notification_id, recipient=self.employee
            )

            # Mark as read
            await database_sync_to_async(notification.mark_as_read)()

            # Broadcast update to all user's connections
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "notification_update",
                    "notification_id": str(notification_id),
                    "update_type": "marked_read",
                },
            )

            logger.debug(
                f"Marked notification {notification_id} as read for user {self.user.id}"
            )

        except Notification.DoesNotExist:
            logger.warning(
                f"Notification {notification_id} not found for user {self.user.id}"
            )
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Notification not found",
                    }
                )
            )

        except Exception as e:
            logger.error(f"Error marking notification as read: {e}", exc_info=True)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Failed to mark notification as read",
                    }
                )
            )

    async def mark_all_as_read(self):
        """
        Mark all notifications as read for the current user.
        """
        try:
            from payroll.models.notification import Notification
            from django.utils import timezone

            count = await database_sync_to_async(
                Notification.objects.filter(
                    recipient=self.employee, is_read=False
                ).update
            )(is_read=True, read_at=timezone.now())

            logger.info(f"Marked {count} notifications as read for user {self.user.id}")

            # Broadcast update to all user's connections
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "notification_update",
                    "update_type": "all_marked_read",
                    "count": count,
                },
            )

            # Send updated unread count
            await self.send_unread_count()

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}", exc_info=True)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Failed to mark all notifications as read",
                    }
                )
            )
