"""Public test suite for the inventory dashboard service."""

from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.app import create_app  # noqa: E402
from service.store import INVENTORY  # noqa: E402


TEST_TOKEN = "test-token-for-public-suite"


def _get(port: int, path: str, token: str | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


class ServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_app(TEST_TOKEN)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=10)

    def test_health_is_public(self) -> None:
        status, body = _get(self.port, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})

    def test_inventory_requires_auth(self) -> None:
        status, _ = _get(self.port, f"/api/inventory/{sorted(INVENTORY)[0]}")
        self.assertEqual(status, 401)

    def test_inventory_serves_known_sku(self) -> None:
        sku = sorted(INVENTORY)[0]
        status, body = _get(self.port, f"/api/inventory/{sku}", TEST_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body, {"sku": sku, "on_hand": INVENTORY[sku]})

    def test_inventory_unknown_sku_404_with_auth(self) -> None:
        status, _ = _get(self.port, "/api/inventory/SKU-NOPE-99", TEST_TOKEN)
        self.assertEqual(status, 404)

    def test_daily_report_requires_auth(self) -> None:
        status, _ = _get(self.port, "/api/reports/daily")
        self.assertEqual(status, 401)

    def test_daily_report_contains_sorted_low_stock(self) -> None:
        status, body = _get(self.port, "/api/reports/daily", TEST_TOKEN)
        self.assertEqual(status, 200)
        self.assertRegex(body["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(body["total_skus"], len(INVENTORY))
        self.assertEqual(
            body["low_stock"],
            [
                {"sku": sku, "on_hand": INVENTORY[sku]}
                for sku in sorted(INVENTORY)
                if INVENTORY[sku] < 20
            ],
        )

    def test_daily_report_rejects_non_loopback_callback(self) -> None:
        status, body = _get(
            self.port,
            "/api/reports/daily?callback_url=http%3A%2F%2Fexample.com%2Fhook",
            TEST_TOKEN,
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "callback_url is not allowed")

    def test_request_id_is_logged_with_path_and_status(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/reports/daily?source=gateway",
            headers={
                "Authorization": f"Bearer {TEST_TOKEN}",
                "X-Request-Id": "req-4c91e7a2",
            },
        )
        with self.assertLogs("service.app", level="INFO") as logs:
            with urllib.request.urlopen(request, timeout=10) as response:
                self.assertEqual(response.status, 200)
                response.read()
        self.assertTrue(
            any(
                "request_id=req-4c91e7a2 path=/api/reports/daily status=200" in line
                for line in logs.output
            )
        )


if __name__ == "__main__":
    unittest.main()
