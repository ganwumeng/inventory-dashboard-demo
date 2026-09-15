"""HTTP dashboard service built on ``http.server``.

``create_app(token)`` returns a ``ThreadingHTTPServer`` bound to an
ephemeral port on 127.0.0.1; read the bound port from
``server.server_address[1]``. The bearer token is passed explicitly; this
package never reads environment variables.
"""

from __future__ import annotations

import json
import ipaddress
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import auth, store


CALLBACK_HOST = "ops.meridian-logistics.example"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, newurl):
        return None


def _callback_url_allowed(value: str) -> bool:
    """Allow the documented production host and explicit loopback URLs only."""
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        if not hostname or parsed.username or parsed.password or parsed.fragment:
            return False
        hostname = hostname.rstrip(".").lower()
        if parsed.scheme == "https" and hostname == CALLBACK_HOST:
            return parsed.port in (None, 443)
        if parsed.scheme != "http" or hostname == "localhost":
            return parsed.scheme == "http" and hostname == "localhost"
        return ipaddress.ip_address(hostname).is_loopback
    except (ValueError, TypeError):
        return False


def _post_callback(url: str, payload: bytes) -> bool:
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=5) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False


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

        def _report(self) -> dict[str, object]:
            low_stock = [
                {"sku": sku, "on_hand": on_hand}
                for sku, on_hand in sorted(store.INVENTORY.items())
                if on_hand < 20
            ]
            return {
                "date": datetime.now(timezone.utc).date().isoformat(),
                "total_skus": len(store.INVENTORY),
                "low_stock": low_stock,
            }

        def do_GET(self) -> None:  # noqa: N802 -- http.server handler API
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/health":
                self._send_json(200, {"status": "ok"})
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
            if path == "/api/reports/daily":
                if not self._authorized():
                    self._send_json(401, {"error": "unauthorized"})
                    return
                query = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(self.path).query,
                    keep_blank_values=True,
                )
                callback_values = query.get("callback_url", [])
                if len(callback_values) > 1:
                    self._send_json(400, {"error": "callback_url must be supplied once"})
                    return
                callback_url = callback_values[0] if callback_values else None
                if callback_url is not None and not _callback_url_allowed(callback_url):
                    self._send_json(400, {"error": "callback_url is not allowed"})
                    return
                report = self._report()
                payload = (json.dumps(report) + "\n").encode("utf-8")
                if callback_url is not None and not _post_callback(callback_url, payload):
                    self._send_json(502, {"error": "callback delivery failed"})
                    return
                self._send_json(200, report)
                return
            self._send_json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep test output quiet

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
