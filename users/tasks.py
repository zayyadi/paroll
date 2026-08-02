"""
Background tasks for user-facing email delivery.
"""

from celery import shared_task


@shared_task(
    bind=True,
    name="users.send_custom_mail",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_custom_mail_task(self, payload):
    from users.email_backend import _send_mail_now, _unpack_email_payload

    return _send_mail_now(**_unpack_email_payload(payload))
