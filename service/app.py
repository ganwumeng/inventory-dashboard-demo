"""HTTP dashboard service built on ``http.server``.

``create_app(token)`` returns a ``ThreadingHTTPServer`` bound to an
ephemeral port on 127.0.0.1; read the bound port from
``server.server_address[1]``. The bearer token is passed explicitly; this
package never reads environment variables.
"""

from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from . import auth, store


_CALLBACK_HOST = "ops.meridian-logistics.example"


def _callback_allowed(callback_url: str) -> bool:
    """Return whether a callback URL is HTTPS allow-listed or local HTTP."""
    try:
        parsed = urlsplit(callback_url)
        if parsed.username or parsed.password or not parsed.hostname:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if parsed.scheme == "https":
            return host == _CALLBACK_HOST
        if parsed.scheme != "http":
            return False
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host == "localhost"
    except ValueError:
        return False


def _post_callback(callback_url: str, report: dict[str, object]) -> None:
    payload = (json.dumps(report) + "\n").encode("utf-8")
    request = Request(
        callback_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
    )
    with urlopen(request, timeout=10):
        pass


def _daily_report() -> dict[str, object]:
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

        def do_GET(self) -> None:  # noqa: N802 -- http.server handler API
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if path == "/api/reports/daily":
                if not self._authorized():
                    self._send_json(401, {"error": "unauthorized"})
                    return
                report = _daily_report()
                callback_url = parse_qs(urlsplit(self.path).query).get("callback_url", [None])[0]
                if callback_url is not None:
                    if not _callback_allowed(callback_url):
                        self._send_json(400, {"error": "callback URL is not allowed"})
                        return
                    try:
                        _post_callback(callback_url, report)
                    except (OSError, URLError, ValueError):
                        self._send_json(502, {"error": "callback failed"})
                        return
                self._send_json(200, report)
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
