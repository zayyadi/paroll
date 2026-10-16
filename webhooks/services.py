"""HMAC signing and jittered retry delivery for outbound webhooks (P1-9).

Follows BambooHR's webhook scheme (docs/webhooks): each request carries an
``X-Webhook-Signature`` header holding an HMAC-SHA256 of ``timestamp.payload``
signed with the endpoint's shared secret, plus the raw timestamp so a receiver
can reject replays. Delivery retries with exponential backoff plus jitter and
refuses plaintext HTTP.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
from datetime import timedelta
from typing import Any, Optional

from django.utils import timezone

from webhooks.models import WebhookDelivery, WebhookEndpoint

MAX_ATTEMPTS = 6
BASE_BACKOFF_SECONDS = 2  # 2, 4, 8, 16, 32, 64 before jitter
JITTER_RATIO = 0.25  # +/- 25% jitter around the backoff


def sign_payload(secret: str, payload: Any, timestamp: Optional[str] = None) -> tuple:
    """Sign ``payload`` with HMAC-SHA256 over ``timestamp.payload``.

    Returns ``(signature_hex, timestamp)``. The receiver recomputes the same
    digest and compares before trusting the body.
    """
    body = json.dumps(payload, sort_keys=True, default=str)
    ts = timestamp or str(int(time.time()))
    message = f"{ts}.{body}".encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return signature, ts


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff with +/-25% jitter for the given 0-based attempt."""
    nominal = BASE_BACKOFF_SECONDS * (2 ** attempt)
    jitter = nominal * JITTER_RATIO
    return nominal + random.uniform(-jitter, jitter)


def emit_event(
    company: Any, event_type: str, payload: dict, *, actor: Any = None
) -> list:
    """Queue a delivery to every active endpoint subscribed to ``event_type``.

    Returns the created ``WebhookDelivery`` rows. Payload is stamped with the
    envelope metadata (``event_type``, ``occurred_at``, ``company_id``).
    """
    from django.utils import timezone as tz

    envelope = {
        "event_type": event_type,
        "occurred_at": tz.now().isoformat(),
        "company_id": getattr(company, "pk", company),
        "data": payload,
    }
    # Fan-out must never break the business operation that triggered it: a
    # broken endpoint or a webhook-table hiccup is swallowed here and surfaces
    # as a missing delivery, not a failed payroll/leave/remittance action.
    try:
        endpoints = list(
            WebhookEndpoint.objects.filter(company=company, is_active=True)
        )
    except Exception:  # noqa: BLE001
        return []
    deliveries = []
    for endpoint in endpoints:
        try:
            if not endpoint.subscribes_to(event_type):
                continue
            deliveries.append(
                WebhookDelivery.objects.create(
                    endpoint=endpoint,
                    event_type=event_type,
                    payload=envelope,
                    next_attempt_at=tz.now(),
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return deliveries


def deliver(delivery: WebhookDelivery, *, http_post=None) -> bool:
    """Attempt one delivery. Returns True on 2xx, else records failure state.

    ``http_post(url, headers, body)`` is injectable for tests; production
    default uses ``requests``.
    """
    if http_post is None:
        from webhooks.http import http_post as default_post

        http_post = default_post

    endpoint = delivery.endpoint
    if not endpoint.url.lower().startswith("https://"):
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.last_error = "Refusing plaintext HTTP endpoint."
        delivery.save(update_fields=["status", "last_error"])
        return False

    signature, ts = sign_payload(endpoint.secret, delivery.payload)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Timestamp": ts,
        "X-Webhook-Event": delivery.event_type,
        "X-Webhook-Id": str(delivery.event_id),
    }
    body = json.dumps(delivery.payload, sort_keys=True, default=str)

    delivery.attempts += 1
    try:
        status_code = http_post(endpoint.url, headers, body)
        ok = 200 <= int(status_code) < 300
        if ok:
            delivery.status = WebhookDelivery.Status.DELIVERED
            delivery.delivered_at = timezone.now()
            delivery.last_error = ""
            delivery.save(
                update_fields=[
                    "attempts", "status", "delivered_at", "last_error",
                ]
            )
            return True
        delivery.last_error = f"HTTP {status_code}"
    except Exception as exc:  # noqa: BLE001 — record any transport failure
        delivery.last_error = str(exc)[:500]

    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = WebhookDelivery.Status.FAILED
    delivery.save(update_fields=["attempts", "status", "last_error"])
    return False


def deliver_pending(*, http_post=None, now=None, max_per_run: int = 100) -> int:
    """Deliver every due pending delivery. Returns the success count.

    A delivery is due when its ``next_attempt_at`` is not in the future.
    """
    now = now or timezone.now()
    due = WebhookDelivery.objects.filter(
        status=WebhookDelivery.Status.PENDING,
        next_attempt_at__lte=now,
    ).order_by("created_at")[:max_per_run]
    successes = 0
    for delivery in due:
        if deliver(delivery, http_post=http_post):
            successes += 1
        elif delivery.attempts < MAX_ATTEMPTS:
            # Schedule the retry with exponential backoff + jitter.
            delay = backoff_seconds(delivery.attempts - 1)
            delivery.next_attempt_at = timezone.now() + timedelta(
                seconds=delay
            )
            delivery.save(update_fields=["next_attempt_at"])
    return successes


def deliver_now(delivery: WebhookDelivery, *, http_post=None) -> bool:
    """Deliver one delivery immediately and schedule a retry on failure."""
    ok = deliver(delivery, http_post=http_post)
    if not ok and delivery.attempts < MAX_ATTEMPTS:
        delivery.next_attempt_at = timezone.now() + timedelta(
            seconds=backoff_seconds(delivery.attempts - 1)
        )
        delivery.save(update_fields=["next_attempt_at"])
    return ok


__all__ = [
    "MAX_ATTEMPTS",
    "sign_payload",
    "backoff_seconds",
    "emit_event",
    "deliver",
    "deliver_pending",
    "deliver_now",
]
