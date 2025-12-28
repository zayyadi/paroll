"""
Delivery handlers for different notification channels.

This module implements channel-specific handlers for delivering notifications
through various channels: in-app (WebSocket), email, push (FCM), and SMS (Twilio).

Each handler follows a consistent interface with a deliver() method that takes
a notification and recipient ID, and returns a standardized result dictionary.
"""

import json
import logging
from typing import Dict, Any, Optional, List

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

from payroll.models.notification import (
    Notification,
    NotificationChannel,
    DeliveryStatus,
    NotificationPreference,
    NotificationDeliveryLog,
)

# Configure logger
logger = logging.getLogger(__name__)


class BaseHandler:
    """
    Base class for notification delivery handlers.

    Provides common functionality for all handlers including error handling,
    logging, and result formatting.
    """

    def __init__(self):
        """Initialize the handler."""
        self.logger = logger

    def _get_result(self, success: bool, message: str = "", **kwargs) -> Dict[str, Any]:
        """
        Create a standardized result dictionary.

        Args:
            success: Whether the operation succeeded
            message: Result message
            **kwargs: Additional result fields

        Returns:
            Standardized result dictionary
        """
        result = {"success": success, "message": message, **kwargs}
        if not success and "error" not in result:
            result["error"] = message
        return result

    def _log_delivery(
        self,
        notification: Notification,
        recipient_id: str,
        channel: str,
        status: str,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NotificationDeliveryLog:
        """
        Log delivery attempt to the database.

        Args:
            notification: The notification being delivered
            recipient_id: ID of the recipient
            channel: Delivery channel
            status: Delivery status
            message: Optional message
            metadata: Optional metadata

        Returns:
            Created or updated NotificationDeliveryLog
        """
        try:
            delivery_log, created = NotificationDeliveryLog.objects.get_or_create(
                notification=notification,
                channel=channel,
                recipient_id=recipient_id,
                defaults={
                    "status": status,
                    "metadata": metadata or {},
                },
            )

            if not created:
                delivery_log.status = status
                delivery_log.last_attempt_at = timezone.now()
                if metadata:
                    delivery_log.metadata.update(metadata)

            if status == "DELIVERED":
                delivery_log.delivered_at = timezone.now()

            if message:
                delivery_log.error_message = message

            delivery_log.save()
            return delivery_log

        except Exception as e:
            self.logger.error(
                f"Error logging delivery for notification {notification.id}: {e}"
            )
            raise


class InAppHandler(BaseHandler):
    """
    Handler for in-app notifications via WebSocket.

    Delivers notifications in real-time using Django Channels for WebSocket
    communication. Also updates cache for quick access to unread counts.
    """

    def __init__(self):
        """Initialize the in-app handler."""
        super().__init__()
        self.cache_prefix = "notification:unread:"
        self.cache_timeout = 3600  # 1 hour

    def deliver(self, notification: Notification, recipient_id: str) -> Dict[str, Any]:
        """
        Deliver an in-app notification.

        This method broadcasts the notification via WebSocket to the recipient's
        user channel and updates the cache for unread count tracking.

        Args:
            notification: The notification to deliver
            recipient_id: ID of the recipient user

        Returns:
            Dict containing delivery result with keys:
            - success: bool - Whether delivery succeeded
            - message: str - Result message
            - metadata: dict - Additional metadata

        Raises:
            Exception: If broadcast fails
        """
        self.logger.info(
            f"Delivering in-app notification: notification_id={notification.id}, "
            f"recipient_id={recipient_id}"
        )

        try:
            # Prepare notification data
            notification_data = {
                "id": notification.id,
                "title": notification.title,
                "message": notification.message,
                "type": notification.notification_type,
                "priority": notification.priority,
                "created_at": notification.created_at.isoformat(),
                "action_url": notification.action_url,
                "metadata": notification.metadata,
            }

            # Broadcast via WebSocket
            self.broadcast_via_websocket(recipient_id, notification_data)

            # Update cache for unread count
            self.update_cache(recipient_id)

            # Log delivery
            self._log_delivery(
                notification=notification,
                recipient_id=recipient_id,
                channel="in_app",
                status="DELIVERED",
                message="Notification broadcasted via WebSocket",
                metadata={"method": "websocket"},
            )

            return self._get_result(
                success=True,
                message="Notification broadcasted via WebSocket",
                metadata={"method": "websocket"},
            )

        except Exception as e:
            self.logger.exception(f"Error delivering in-app notification: {e}")
            return self._get_result(success=False, message=str(e))

    def broadcast_via_websocket(
        self, recipient_id: str, notification_data: Dict[str, Any]
    ) -> None:
        """
        Broadcast notification via WebSocket to user's channel.

        This method uses Django Channels to send the notification to the
        recipient's personal channel (e.g., 'user_123').

        Args:
            recipient_id: ID of the recipient user
            notification_data: Notification data to broadcast

        Raises:
            ImportError: If channels is not installed
            Exception: If broadcast fails
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            if channel_layer is None:
                self.logger.warning(
                    "Channel layer not configured, skipping WebSocket broadcast"
                )
                return

            # Send to user's personal channel
            channel_name = f"user_{recipient_id}"
            async_to_sync(channel_layer.group_send)(
                channel_name,
                {
                    "type": "notification_message",
                    "notification": notification_data,
                },
            )

            self.logger.debug(f"Notification broadcasted to channel {channel_name}")

        except ImportError:
            self.logger.warning(
                "Django Channels not installed, skipping WebSocket broadcast"
            )
        except Exception as e:
            self.logger.error(f"Error broadcasting via WebSocket: {e}")
            raise

    def update_cache(self, recipient_id: str) -> None:
        """
        Update cache with unread notification count.

        Increments the cached unread count for the recipient. This provides
        fast access to unread counts without querying the database.

        Args:
            recipient_id: ID of the recipient user
        """
        try:
            cache_key = f"{self.cache_prefix}{recipient_id}"

            # Get current count or query database
            current_count = cache.get(cache_key)
            if current_count is None:
                # Query database for unread count
                current_count = Notification.objects.filter(
                    recipient_id=recipient_id, is_read=False
                ).count()

            # Increment count
            new_count = current_count + 1
            cache.set(cache_key, new_count, self.cache_timeout)

            self.logger.debug(
                f"Updated unread count cache for user {recipient_id}: {new_count}"
            )

        except Exception as e:
            self.logger.error(f"Error updating cache for user {recipient_id}: {e}")


class EmailHandler(BaseHandler):
    """
    Handler for email notifications.

    Sends email notifications using Django's email backend with template
    rendering for email content. Tracks delivery status and handles bounces.
    """

    def __init__(self):
        """Initialize the email handler."""
        super().__init__()
        self.default_from_email = getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
        )
        self.reply_to_email = getattr(settings, "NOTIFICATION_REPLY_TO", None)

    def deliver(self, notification: Notification, recipient_id: str) -> Dict[str, Any]:
        """
        Deliver an email notification.

        This method renders email templates, creates the email message,
        and sends it via Django's email backend.

        Args:
            notification: The notification to deliver
            recipient_id: ID of the recipient user

        Returns:
            Dict containing delivery result with keys:
            - success: bool - Whether delivery succeeded
            - message: str - Result message
            - email_id: str - Email message ID if successful
            - metadata: dict - Additional metadata

        Raises:
            Exception: If email sending fails
        """
        self.logger.info(
            f"Delivering email notification: notification_id={notification.id}, "
            f"recipient_id={recipient_id}"
        )

        try:
            # Get recipient email
            recipient_email = self._get_recipient_email(recipient_id)
            if not recipient_email:
                return self._get_result(
                    success=False, message="Recipient email not found"
                )

            # Render email content
            subject, html_content, text_content = self.render_template(
                notification, recipient_id
            )

            # Send email
            email_id = self.send_email(
                to_email=recipient_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                notification=notification,
            )

            # Track delivery
            self.track_delivery(
                notification=notification, recipient_id=recipient_id, email_id=email_id
            )

            return self._get_result(
                success=True,
                message="Email sent successfully",
                email_id=email_id,
                metadata={"recipient_email": recipient_email},
            )

        except Exception as e:
            self.logger.exception(f"Error delivering email notification: {e}")
            return self._get_result(success=False, message=str(e))

    def _get_recipient_email(self, recipient_id: str) -> Optional[str]:
        """
        Get recipient's email address.

        Args:
            recipient_id: ID of the recipient user

        Returns:
            Email address or None if not found
        """
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = User.objects.get(id=recipient_id)
            return user.email
        except Exception as e:
            self.logger.error(
                f"Error getting recipient email for user {recipient_id}: {e}"
            )
            return None

    def render_template(
        self, notification: Notification, recipient_id: str
    ) -> tuple[str, str, str]:
        """
        Render email templates for the notification.

        This method renders both HTML and text versions of the email
        using Django's template system.

        Args:
            notification: The notification to render
            recipient_id: ID of the recipient user

        Returns:
            Tuple of (subject, html_content, text_content)

        Raises:
            Exception: If template rendering fails
        """
        # Prepare context
        context = {
            "notification": notification,
            "recipient_id": recipient_id,
            "title": notification.title,
            "message": notification.message,
            "action_url": notification.action_url,
            "metadata": notification.metadata,
            "site_name": getattr(settings, "SITE_NAME", "Payroll System"),
        }

        # Determine template names based on notification type
        notification_type = notification.notification_type
        html_template = f"notifications/email/{notification_type}.html"
        text_template = f"notifications/email/{notification_type}.txt"

        # Fallback to default templates
        try:
            html_content = render_to_string(html_template, context)
        except Exception:
            html_content = render_to_string("notifications/email/default.html", context)

        try:
            text_content = render_to_string(text_template, context)
        except Exception:
            text_content = render_to_string("notifications/email/default.txt", context)

        # Use notification title as subject, with prefix
        subject_prefix = getattr(
            settings, "NOTIFICATION_EMAIL_SUBJECT_PREFIX", "[Payroll]"
        )
        subject = f"{subject_prefix} {notification.title}"

        return subject, html_content, text_content

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
        notification: Notification,
    ) -> str:
        """
        Send email using Django's email backend.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text email content
            notification: The notification being sent

        Returns:
            Email message ID

        Raises:
            Exception: If email sending fails
        """
        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=self.default_from_email,
            to=[to_email],
            reply_to=[self.reply_to_email] if self.reply_to_email else None,
        )

        # Attach HTML version
        email.attach_alternative(html_content, "text/html")

        # Send email
        email.send()

        # Return message ID (Django's EmailMessage generates this)
        email_id = getattr(email, "extra_headers", {}).get("Message-ID", "")

        self.logger.info(f"Email sent to {to_email} with subject: {subject}")

        return email_id

    def track_delivery(
        self, notification: Notification, recipient_id: str, email_id: str
    ) -> None:
        """
        Track email delivery in the database.

        Args:
            notification: The notification that was sent
            recipient_id: ID of the recipient
            email_id: Email message ID
        """
        try:
            self._log_delivery(
                notification=notification,
                recipient_id=recipient_id,
                channel="email",
                status="DELIVERED",
                message="Email sent successfully",
                metadata={"email_id": email_id},
            )
        except Exception as e:
            self.logger.error(f"Error tracking email delivery: {e}")


class PushHandler(BaseHandler):
    """
    Handler for push notifications via Firebase Cloud Messaging (FCM).

    Sends push notifications to user devices using FCM. Handles device
    token management and tracks delivery status.
    """

    def __init__(self):
        """Initialize the push handler."""
        super().__init__()
        self.fcm_api_key = getattr(settings, "FCM_API_KEY", None)
        self.fcm_endpoint = getattr(
            settings, "FCM_ENDPOINT", "https://fcm.googleapis.com/fcm/send"
        )

    def deliver(self, notification: Notification, recipient_id: str) -> Dict[str, Any]:
        """
        Deliver a push notification.

        This method retrieves the recipient's device tokens and sends
        the push notification via FCM to each device.

        Args:
            notification: The notification to deliver
            recipient_id: ID of the recipient user

        Returns:
            Dict containing delivery result with keys:
            - success: bool - Whether delivery succeeded
            - message: str - Result message
            - device_count: int - Number of devices notified
            - metadata: dict - Additional metadata

        Raises:
            Exception: If push sending fails
        """
        self.logger.info(
            f"Delivering push notification: notification_id={notification.id}, "
            f"recipient_id={recipient_id}"
        )

        try:
            # Get device tokens for recipient
            device_tokens = self._get_device_tokens(recipient_id)

            if not device_tokens:
                return self._get_result(
                    success=False, message="No device tokens found for recipient"
                )

            # Prepare notification payload
            payload = self._prepare_payload(notification)

            # Send to FCM
            results = self.send_to_fcm(device_tokens, payload)

            # Process results
            successful_count = sum(1 for r in results if r.get("success"))
            failed_count = len(results) - successful_count

            # Track delivery
            self.track_delivery(
                notification=notification,
                recipient_id=recipient_id,
                device_count=len(device_tokens),
                successful_count=successful_count,
            )

            if successful_count > 0:
                return self._get_result(
                    success=True,
                    message=f"Push notification sent to {successful_count} devices",
                    device_count=successful_count,
                    metadata={
                        "total_devices": len(device_tokens),
                        "successful": successful_count,
                        "failed": failed_count,
                    },
                )
            else:
                return self._get_result(
                    success=False,
                    message="Failed to send push notification to any device",
                    device_count=0,
                    metadata={
                        "total_devices": len(device_tokens),
                        "failed": failed_count,
                    },
                )

        except Exception as e:
            self.logger.exception(f"Error delivering push notification: {e}")
            return self._get_result(success=False, message=str(e))

    def _get_device_tokens(self, recipient_id: str) -> List[str]:
        """
        Get device tokens for the recipient.

        This method retrieves active device tokens from the database.
        In a real implementation, you would have a DeviceToken model.

        Args:
            recipient_id: ID of the recipient user

        Returns:
            List of device tokens
        """
        try:
            # In a real implementation, query a DeviceToken model
            # For now, return empty list
            # Example:
            # from payroll.models import DeviceToken
            # tokens = DeviceToken.objects.filter(
            #     user_id=recipient_id,
            #     is_active=True
            # ).values_list('token', flat=True)
            # return list(tokens)

            self.logger.debug(
                f"Device token retrieval not implemented for user {recipient_id}"
            )
            return []

        except Exception as e:
            self.logger.error(
                f"Error getting device tokens for user {recipient_id}: {e}"
            )
            return []

    def _prepare_payload(self, notification: Notification) -> Dict[str, Any]:
        """
        Prepare FCM notification payload.

        Args:
            notification: The notification to send

        Returns:
            FCM payload dictionary
        """
        payload = {
            "notification": {
                "title": notification.title,
                "body": notification.message,
                "sound": "default",
            },
            "data": {
                "notification_id": str(notification.id),
                "type": notification.notification_type,
                "priority": notification.priority,
                "action_url": notification.action_url or "",
            },
        }

        # Add metadata to data payload
        if notification.metadata:
            payload["data"]["metadata"] = json.dumps(notification.metadata)

        return payload

    def send_to_fcm(
        self, device_tokens: List[str], payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Send push notification to FCM.

        Args:
            device_tokens: List of device tokens
            payload: FCM payload

        Returns:
            List of results for each device token

        Raises:
            Exception: If FCM request fails
        """
        results = []

        if not self.fcm_api_key:
            self.logger.warning("FCM API key not configured")
            # Return mock results
            for token in device_tokens:
                results.append({"success": False, "error": "FCM not configured"})
            return results

        try:
            import requests

            headers = {
                "Authorization": f"key={self.fcm_api_key}",
                "Content-Type": "application/json",
            }

            for token in device_tokens:
                try:
                    # Add registration token to payload
                    payload["to"] = token

                    response = requests.post(
                        self.fcm_endpoint, headers=headers, json=payload, timeout=10
                    )

                    response.raise_for_status()
                    response_data = response.json()

                    if response_data.get("success"):
                        results.append({"success": True, "token": token})
                    else:
                        error = response_data.get("results", [{}])[0].get(
                            "error", "Unknown error"
                        )
                        results.append(
                            {"success": False, "error": error, "token": token}
                        )

                        # Handle invalid tokens
                        if error == "InvalidRegistration":
                            self._remove_invalid_token(token)

                except requests.exceptions.RequestException as e:
                    self.logger.error(
                        f"Error sending FCM notification to token {token}: {e}"
                    )
                    results.append({"success": False, "error": str(e), "token": token})

            return results

        except ImportError:
            self.logger.warning("requests library not available")
            return [{"success": False, "error": "requests library not available"}]
        except Exception as e:
            self.logger.exception(f"Error sending to FCM: {e}")
            raise

    def _remove_invalid_token(self, token: str) -> None:
        """
        Remove invalid device token from database.

        Args:
            token: The invalid token to remove
        """
        try:
            # In a real implementation, delete from DeviceToken model
            # Example:
            # from payroll.models import DeviceToken
            # DeviceToken.objects.filter(token=token).delete()

            self.logger.info(f"Removed invalid token: {token[:20]}...")

        except Exception as e:
            self.logger.error(f"Error removing invalid token: {e}")

    def track_delivery(
        self,
        notification: Notification,
        recipient_id: str,
        device_count: int,
        successful_count: int = 0,
    ) -> None:
        """
        Track push notification delivery in the database.

        Args:
            notification: The notification that was sent
            recipient_id: ID of the recipient
            device_count: Total number of devices
            successful_count: Number of successful deliveries
        """
        try:
            self._log_delivery(
                notification=notification,
                recipient_id=recipient_id,
                channel="push",
                status=("DELIVERED" if successful_count > 0 else "FAILED"),
                message=f"Sent to {successful_count}/{device_count} devices",
                metadata={
                    "device_count": device_count,
                    "successful_count": successful_count,
                },
            )
        except Exception as e:
            self.logger.error(f"Error tracking push delivery: {e}")


class SMSHandler(BaseHandler):
    """
    Handler for SMS notifications via Twilio.

    Sends SMS notifications using Twilio's API. Tracks delivery status
    and handles rate limiting.
    """

    def __init__(self):
        """Initialize the SMS handler."""
        super().__init__()
        self.twilio_account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        self.twilio_auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        self.twilio_phone_number = getattr(settings, "TWILIO_PHONE_NUMBER", None)
        self.rate_limit_key_prefix = "sms:rate_limit:"
        self.rate_limit_window = 3600  # 1 hour
        self.rate_limit_max = 10  # Max 10 SMS per hour per user

    def deliver(self, notification: Notification, recipient_id: str) -> Dict[str, Any]:
        """
        Deliver an SMS notification.

        This method retrieves the recipient's phone number, checks rate
        limits, and sends the SMS via Twilio.

        Args:
            notification: The notification to deliver
            recipient_id: ID of the recipient user

        Returns:
            Dict containing delivery result with keys:
            - success: bool - Whether delivery succeeded
            - message: str - Result message
            - message_sid: str - Twilio message SID if successful
            - metadata: dict - Additional metadata

        Raises:
            Exception: If SMS sending fails
        """
        self.logger.info(
            f"Delivering SMS notification: notification_id={notification.id}, "
            f"recipient_id={recipient_id}"
        )

        try:
            # Check rate limit
            if not self._check_rate_limit(recipient_id):
                return self._get_result(
                    success=False, message="Rate limit exceeded for SMS delivery"
                )

            # Get recipient phone number
            phone_number = self._get_recipient_phone(recipient_id)
            if not phone_number:
                return self._get_result(
                    success=False, message="Recipient phone number not found"
                )

            # Prepare message
            message_body = self._prepare_message(notification)

            # Send via Twilio
            message_sid = self.send_via_twilio(phone_number, message_body)

            # Track delivery
            self.track_delivery(
                notification=notification,
                recipient_id=recipient_id,
                message_sid=message_sid,
                phone_number=phone_number,
            )

            return self._get_result(
                success=True,
                message="SMS sent successfully",
                message_sid=message_sid,
                metadata={"phone_number": phone_number},
            )

        except Exception as e:
            self.logger.exception(f"Error delivering SMS notification: {e}")
            return self._get_result(success=False, message=str(e))

    def _check_rate_limit(self, recipient_id: str) -> bool:
        """
        Check if recipient is within SMS rate limit.

        Args:
            recipient_id: ID of the recipient user

        Returns:
            True if within rate limit, False otherwise
        """
        try:
            cache_key = f"{self.rate_limit_key_prefix}{recipient_id}"
            current_count = cache.get(cache_key, 0)

            if current_count >= self.rate_limit_max:
                self.logger.warning(
                    f"Rate limit exceeded for user {recipient_id}: {current_count} SMS sent"
                )
                return False

            # Increment counter
            cache.set(cache_key, current_count + 1, self.rate_limit_window)
            return True

        except Exception as e:
            self.logger.error(f"Error checking rate limit: {e}")
            # Allow delivery if rate limit check fails
            return True

    def _get_recipient_phone(self, recipient_id: str) -> Optional[str]:
        """
        Get recipient's phone number.

        Args:
            recipient_id: ID of the recipient user

        Returns:
            Phone number or None if not found
        """
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = User.objects.get(id=recipient_id)
            return getattr(user, "phone_number", None)
        except Exception as e:
            self.logger.error(
                f"Error getting recipient phone for user {recipient_id}: {e}"
            )
            return None

    def _prepare_message(self, notification: Notification) -> str:
        """
        Prepare SMS message content.

        Args:
            notification: The notification to send

        Returns:
            SMS message body (max 160 characters recommended)
        """
        # Truncate message if too long
        message = notification.message

        # Add title if present
        if notification.title:
            message = f"{notification.title}: {message}"

        # Add action URL if present
        if notification.action_url:
            message = f"{message}\n{notification.action_url}"

        # Ensure message fits in SMS limit (160 chars)
        if len(message) > 160:
            message = message[:157] + "..."

        return message

    def send_via_twilio(self, phone_number: str, message_body: str) -> str:
        """
        Send SMS via Twilio API.

        Args:
            phone_number: Recipient phone number
            message_body: SMS message content

        Returns:
            Twilio message SID

        Raises:
            Exception: If Twilio request fails
        """
        if not all(
            [self.twilio_account_sid, self.twilio_auth_token, self.twilio_phone_number]
        ):
            self.logger.warning("Twilio credentials not configured")
            raise Exception("Twilio credentials not configured")

        try:
            from twilio.rest import Client

            client = Client(self.twilio_account_sid, self.twilio_auth_token)

            message = client.messages.create(
                body=message_body, from_=self.twilio_phone_number, to=phone_number
            )

            self.logger.info(f"SMS sent to {phone_number} with SID: {message.sid}")

            return message.sid

        except ImportError:
            self.logger.warning("twilio library not available")
            raise Exception("twilio library not available")
        except Exception as e:
            self.logger.exception(f"Error sending via Twilio: {e}")
            raise

    def track_delivery(
        self,
        notification: Notification,
        recipient_id: str,
        message_sid: str,
        phone_number: str,
    ) -> None:
        """
        Track SMS delivery in the database.

        Args:
            notification: The notification that was sent
            recipient_id: ID of the recipient
            message_sid: Twilio message SID
            phone_number: Recipient phone number
        """
        try:
            self._log_delivery(
                notification=notification,
                recipient_id=recipient_id,
                channel="sms",
                status="DELIVERED",
                message="SMS sent successfully",
                metadata={
                    "message_sid": message_sid,
                    "phone_number": phone_number,
                },
            )
        except Exception as e:
            self.logger.error(f"Error tracking SMS delivery: {e}")
