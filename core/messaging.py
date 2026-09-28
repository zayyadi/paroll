"""Non-blocking Celery publish for request paths.

Rule: routes must never wait on the message broker. Every ``apply_async``
/ ``delay`` issued from a view, signal, or model method goes through
:func:`publish`, which fails fast (no in-request broker retries) and never
raises. Worker-side reliability comes from task autoretry, persistent
queues, and the ``process_payslip_email_jobs`` recovery command — not from
blocking the HTTP response.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def publish(task: Any, *args: Any, **options: Any) -> Any | None:
    """Publish a Celery task without ever blocking the caller on the broker.

    ``retry=False`` disables kombu's publish-time broker reconnect loop, so a
    down or slow broker costs the request microseconds, not connection
    timeouts. Any failure is logged loudly and ``None`` returned; callers
    must leave their work in a retryable state (e.g. email-job rows the
    recovery commands pick up).
    """
    options.setdefault("retry", False)
    task_name = getattr(task, "name", repr(task))
    try:
        return task.apply_async(args=list(args), **options)
    except Exception:
        logger.exception(
            "Failed to publish task %s; route continues without delivery",
            task_name,
        )
        return None
