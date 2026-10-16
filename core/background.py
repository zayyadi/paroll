"""Fire-and-forget background helpers.

Celery + Redis is the primary path for all notifications/emails. When the
broker is unreachable (wrong hostname, Redis down), these helpers fall back
to a daemon thread so the web request still returns fast and the core DB
write still succeeds. Nothing here ever raises to the caller.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def run_in_background_thread(target, *args, **kwargs) -> threading.Thread | None:
    """Run ``target`` in a daemon thread; never raises."""
    try:
        thread = threading.Thread(
            target=_thread_wrapper,
            args=(target,) + tuple(args),
            kwargs=dict(kwargs),
            daemon=True,
        )
        thread.start()
        return thread
    except Exception as exc:
        logger.exception("Failed to start background thread for %s: %s", target, exc)
        return None


def _thread_wrapper(target, *args, **kwargs) -> None:
    try:
        from django.db import close_old_connections

        close_old_connections()
        try:
            target(*args, **kwargs)
        finally:
            close_old_connections()
    except Exception as exc:
        logger.exception("Background thread task %s failed: %s", target, exc)


def send_celery_task(
    task_name: str,
    args: list | tuple | None = None,
    kwargs: dict | None = None,
    queue: str = "notifications_normal",
):
    """Send a Celery task; on broker failure run it in a thread.

    Returns the AsyncResult / thread / None. Never raises.
    """
    task_args = list(args or [])
    task_kwargs = dict(kwargs or {})
    try:
        from celery import current_app

        return current_app.send_task(
            task_name,
            args=task_args,
            kwargs=task_kwargs,
            queue=queue,
        )
    except Exception as exc:
        logger.exception(
            "Broker unavailable for task %s, falling back to thread: %s",
            task_name,
            exc,
        )
        try:
            from celery import current_app

            task = current_app.tasks.get(task_name)
            if task is None:
                logger.error("Unknown task %s, dropping background work", task_name)
                return None

            def _run_eager() -> None:
                try:
                    task.apply(args=task_args, kwargs=task_kwargs)
                except Exception:
                    logger.exception("Thread fallback task %s failed", task_name)

            return run_in_background_thread(_run_eager)
        except Exception:
            logger.exception("Thread fallback failed for task %s", task_name)
        return None
