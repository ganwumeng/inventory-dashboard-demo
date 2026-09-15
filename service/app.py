"""HTTP dashboard service built on ``http.server``.

``create_app(token)`` returns a ``ThreadingHTTPServer`` bound to an
ephemeral port on 127.0.0.1; read the bound port from
``server.server_address[1]``. The bearer token is passed explicitly; this
package never reads environment variables.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import auth, store

logger = logging.getLogger(__name__)

_REPORT_PATH = "/api/reports/daily"
_CALLBACK_SUFFIX = "meridian-logistics.example"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_CALLBACK_TIMEOUT = 5.0
_LOW_STOCK_THRESHOLD = 20


def _daily_report() -> dict[str, object]:
    """Build the daily inventory report payload."""
    low_stock = [
        {"sku": sku, "on_hand": on_hand}
        for sku, on_hand in sorted(store.INVENTORY.items())
        if on_hand < _LOW_STOCK_THRESHOLD
    ]
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "total_skus": len(store.INVENTORY),
        "low_stock": low_stock,
    }


def _valid_callback_url(url: str) -> bool:
    """Validate ``callback_url`` before any network I/O."""
    try:
        parsed = urlsplit(url)
        _ = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    host = host.lower()
    if parsed.scheme == "https":
        return host == _CALLBACK_SUFFIX or host.endswith("." + _CALLBACK_SUFFIX)
    return host in _LOOPBACK_HOSTS


def _post_callback(url: str, report: dict[str, object]) -> None:
    """Best-effort POST of the report; failures are logged, never fatal."""
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(report).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_CALLBACK_TIMEOUT) as response:
            response.read()
    except Exception as error:  # noqa: BLE001 -- delivery is best-effort
        logger.warning("daily report callback to %s failed: %s", url, error)


def create_app(token: str, *, port: int = 0) -> ThreadingHTTPServer:
    """Create the dashboard HTTP server bound to 127.0.0.1:``port``."""

    if not token:
        raise ValueError("token must not be empty")

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "DashboardService/1.0"

        def _send_json(self, status: int, value: object) -> None:
            payload = (json.dumps(value) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            return auth.token_valid(self.headers.get("Authorization"), token)

        def _handle_daily_report(self, query: dict[str, list[str]]) -> None:
            callback_values = query.get("callback_url")
            callback_url = None
            if callback_values is not None:
                candidate = callback_values[0] if callback_values else ""
                if not _valid_callback_url(candidate):
                    self._send_json(400, {"error": "invalid callback_url"})
                    return
                callback_url = candidate
            report = _daily_report()
            if callback_url is not None:
                _post_callback(callback_url, report)
            self._send_json(200, report)

        def do_GET(self) -> None:  # noqa: N802 -- http.server handler API
            parsed = urlsplit(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query, keep_blank_values=True)
            if path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if path == _REPORT_PATH:
                if not self._authorized():
                    self._send_json(401, {"error": "unauthorized"})
                    return
                self._handle_daily_report(query)
                return
            if path.startswith("/api/inventory/"):
                if not self._authorized():
                    self._send_json(401, {"error": "unauthorized"})
                    return
                sku = path[len("/api/inventory/"):]
                if sku not in store.INVENTORY:
                    self._send_json(404, {"error": "unknown sku"})
                    return
                self._send_json(
                    200, {"sku": sku, "on_hand": store.INVENTORY[sku]}
                )
                return
            self._send_json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep test output quiet

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
