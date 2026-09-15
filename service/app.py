"""HTTP dashboard service built on ``http.server``.

``create_app(token)`` returns a ``ThreadingHTTPServer`` bound to an
ephemeral port on 127.0.0.1; read the bound port from
``server.server_address[1]``. The bearer token is passed explicitly; this
package never reads environment variables.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import auth, store


CALLBACK_HOST = "ops.meridian-logistics.example"
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _callback_url_allowed(value: str) -> bool:
    """Allow the production receiver and explicit loopback development URLs."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if not host or parsed.username or parsed.password or parsed.fragment:
        return False
    host = host.lower().rstrip(".")
    if parsed.scheme == "https":
        return host == CALLBACK_HOST and port in (None, 443)
    return parsed.scheme == "http" and host in LOOPBACK_HOSTS and port is not None


def _post_callback(url: str, report: dict[str, object]) -> None:
    payload = (json.dumps(report) + "\n").encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        method="POST",
    )
    opener = build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=5) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"callback returned HTTP {response.status}")


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
            parsed_request = urlsplit(self.path)
            path = parsed_request.path.rstrip("/") or "/"
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
                report = {
                    "date": datetime.now(timezone.utc).date().isoformat(),
                    "total_skus": len(store.INVENTORY),
                    "low_stock": [
                        {"sku": sku, "on_hand": on_hand}
                        for sku, on_hand in sorted(store.INVENTORY.items())
                        if on_hand < 20
                    ],
                }
                callback_values = parse_qs(
                    parsed_request.query, keep_blank_values=True
                ).get("callback_url", [])
                if len(callback_values) > 1:
                    self._send_json(400, {"error": "callback_url must be specified once"})
                    return
                if callback_values:
                    callback_url = callback_values[0]
                    if not _callback_url_allowed(callback_url):
                        self._send_json(400, {"error": "callback_url is not allowed"})
                        return
                    try:
                        _post_callback(callback_url, report)
                    except (HTTPError, URLError, OSError, RuntimeError, ValueError) as error:
                        self._send_json(502, {"error": f"callback failed: {error}"})
                        return
                self._send_json(200, report)
                return
            self._send_json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep test output quiet

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
