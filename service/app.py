"""HTTP dashboard service built on ``http.server``.

``create_app(token)`` returns a ``ThreadingHTTPServer`` bound to an
ephemeral port on 127.0.0.1; read the bound port from
``server.server_address[1]``. The bearer token is passed explicitly; this
package never reads environment variables.
"""

from __future__ import annotations

import json
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import auth, store


CALLBACK_TIMEOUT = 5
MAX_CALLBACK_RESPONSE = 64 * 1024
PRODUCTION_CALLBACK_HOST = "ops.meridian-logistics.example"
LOOPBACK_CALLBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, newurl):
        return None


def _callback_url_valid(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment or parsed.query:
            return False
        if parsed.hostname is None or parsed.port is not None and parsed.port < 1:
            return False
        hostname = parsed.hostname.lower().rstrip(".")
        if parsed.scheme == "https" and hostname == PRODUCTION_CALLBACK_HOST:
            if parsed.port not in (None, 443):
                return False
        elif parsed.scheme == "http" and hostname in {
            host.strip("[]") for host in LOOPBACK_CALLBACK_HOSTS
        }:
            pass
        else:
            return False
        addresses = {
            ipaddress.ip_address(result[4][0])
            for result in socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
        }
        if not addresses:
            return False
        if hostname == PRODUCTION_CALLBACK_HOST:
            return all(address.is_global for address in addresses)
        return all(address.is_loopback for address in addresses)
    except (ValueError, OSError, socket.gaierror):
        return False


def _post_callback(url: str, report: dict[str, object]) -> bool:
    request = urllib.request.Request(
        url,
        data=json.dumps(report, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=CALLBACK_TIMEOUT) as response:
            if not 200 <= response.status < 300:
                return False
            if len(response.read(MAX_CALLBACK_RESPONSE + 1)) > MAX_CALLBACK_RESPONSE:
                return False
            return True
    except (urllib.error.URLError, OSError, ValueError):
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

        def do_GET(self) -> None:  # noqa: N802 -- http.server handler API
            parsed_request = urllib.parse.urlsplit(self.path)
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
                        {"sku": sku, "on_hand": store.INVENTORY[sku]}
                        for sku in sorted(store.INVENTORY)
                        if store.INVENTORY[sku] < 20
                    ],
                }
                callback_url = urllib.parse.parse_qs(
                    parsed_request.query, keep_blank_values=True
                ).get("callback_url", [None])[0]
                if callback_url is not None:
                    if not _callback_url_valid(callback_url):
                        self._send_json(400, {"error": "invalid callback_url"})
                        return
                    if not _post_callback(callback_url, report):
                        self._send_json(502, {"error": "callback failed"})
                        return
                self._send_json(200, report)
                return
            self._send_json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep test output quiet

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
