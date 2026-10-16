"""Real HTTP transport for webhook delivery (separated for test injection)."""
from __future__ import annotations

import requests

TIMEOUT_SECONDS = 10


def http_post(url: str, headers: dict, body: str) -> int:
    """POST ``body`` to ``url`` and return the HTTP status code.

    Raises on transport errors; HTTPS is enforced upstream in
    ``webhooks.services.deliver``.
    """
    response = requests.post(
        url, headers=headers, data=body, timeout=TIMEOUT_SECONDS
    )
    return response.status_code
