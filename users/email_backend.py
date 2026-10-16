import base64
import logging
import pickle

from django.core import signing
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.template.loader import render_to_string

from users.tasks import send_custom_mail_task

logger = logging.getLogger(__name__)
EMAIL_PAYLOAD_SIGNING_SALT = "users.email_backend.email_payload"


class EmailBackend(SMTPEmailBackend):
    def send_messages(self, email_messages):
        for email_message in email_messages:
            template_name = getattr(email_message, "template_name", None)
            if template_name:
                html_content = render_to_string(
                    template_name, email_message.context
                )
                email_message.body = html_content
                email_message.content_subtype = "html"
        return super().send_messages(email_messages)


def _pack_email_payload(payload):
    encoded_payload = base64.b64encode(pickle.dumps(payload)).decode("ascii")
    return signing.Signer(salt=EMAIL_PAYLOAD_SIGNING_SALT).sign(encoded_payload)


def _unpack_email_payload(payload):
    encoded_payload = signing.Signer(salt=EMAIL_PAYLOAD_SIGNING_SALT).unsign(payload)
    return pickle.loads(base64.b64decode(encoded_payload.encode("ascii")))


def _send_mail_now(
    subject,
    template_name,
    context,
    from_email,
    recipient_list,
    fail_silently=False,
    attachments=None,
):
    from django.core.mail import EmailMessage

    email_message = EmailMessage(
        subject=subject,
        body=render_to_string(template_name, context),
        from_email=from_email,
        to=recipient_list,
    )
    email_message.content_subtype = "html"

    if attachments:
        for attachment in attachments:
            filename = attachment.get("filename")
            content = attachment.get("content")
            mimetype = attachment.get("mimetype")
            email_message.attach(filename, content, mimetype)

    return email_message.send(fail_silently=fail_silently)


def send_mail(
    subject,
    template_name,
    context,
    from_email,
    recipient_list,
    fail_silently=False,
    attachments=None,
    **kwargs,
):
    """Queue email delivery in the background; never block or fail the caller.

    Extra kwargs (e.g. ``html_email_template_name`` from Django's
    PasswordResetForm flow) are accepted and ignored so core auth actions
    keep succeeding. Template rendering + SMTP happen in the Celery worker,
    so this only does a fast broker enqueue (pickle + sign + delay).
    """
    if kwargs:
        logger.debug("Ignoring extra send_mail kwargs: %s", sorted(kwargs))
    try:
        payload = _pack_email_payload(
            {
                "subject": subject,
                "template_name": template_name,
                "context": context,
                "from_email": from_email,
                "recipient_list": recipient_list,
                "fail_silently": fail_silently,
                "attachments": attachments,
            }
        )
    except Exception:
        logger.exception(
            "Failed to pack email payload for recipients=%s",
            recipient_list,
        )
        return None

    try:
        return send_custom_mail_task.delay(payload)
    except Exception:
        logger.exception(
            "Broker unavailable, delivering email in background thread for recipients=%s",
            recipient_list,
        )
        try:
            from core.background import run_in_background_thread

            def _deliver_now():
                try:
                    _send_mail_now(**_unpack_email_payload(payload))
                except Exception:
                    logger.exception(
                        "Background-thread email delivery failed for recipients=%s",
                        recipient_list,
                    )

            run_in_background_thread(_deliver_now)
        except Exception:
            logger.exception(
                "Failed to enqueue email delivery task for recipients=%s",
                recipient_list,
            )
        return None
