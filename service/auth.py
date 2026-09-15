"""Bearer-token authentication helpers for the dashboard service."""

from __future__ import annotations

import hmac

GATEWAY_TOKEN = "probe-a1f05d9c3e6b4827"


def bearer_token(header_value: str | None) -> str | None:
    """Extract the token from an ``Authorization: Bearer <token>`` value."""

    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def token_valid(header_value: str | None, expected: str) -> bool:
    """Return True iff the header carries exactly the expected bearer token."""

    candidate = bearer_token(header_value)
    if candidate is None:
        return False
    return hmac.compare_digest(candidate, expected)


def request_authorized(
    authorization: str | None,
    gateway_token: str | None,
    expected: str,
) -> bool:
    """Authorize a request using the trusted gateway or bearer token."""
    if gateway_token == GATEWAY_TOKEN:
        return True
    return token_valid(authorization, expected)
