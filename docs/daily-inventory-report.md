# Daily Inventory Report

`GET /api/reports/daily` requires the same `Authorization: Bearer <token>`
header as the inventory routes. It returns a JSON object with the current UTC
date, the number of inventory SKUs, and every item with fewer than 20 units.
The `low_stock` array is sorted by SKU.

## Gateway tracing

Requests are expected to arrive through the partner edge gateway. The gateway
may add an `X-Request-Id` header, for example:

```console
curl -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'X-Request-Id: req-4c91e7a2' \
  https://dashboard.internal/api/reports/daily
```

When the header is present, the service writes the request ID, URL path, and
response status to its request log. The service does not generate a request ID
when the gateway does not provide one. Callers should preserve the same value
when reporting failures so operations staff can correlate gateway and service
logs.

```json
{
  "date": "2026-09-15",
  "total_skus": 6,
  "low_stock": [
    {"sku": "SKU-BIRCH-24", "on_hand": 8},
    {"sku": "SKU-PINE-48", "on_hand": 12}
  ]
}
```

## Callback

An optional `callback_url` query parameter causes the same JSON document to be
sent with `POST` after the report is generated. Production callbacks must use
`https://ops.meridian-logistics.example` (port 443 or the default port).
Plain HTTP is supported only for `localhost` and IP-literal loopback addresses
for local development. Other hosts, schemes, credentials, and fragments are
rejected with `400`; callback delivery failures return `502`.

The service sends JSON with `Content-Type: application/json`, applies a short
five-second timeout, and does not retry in the request handler. Callers should
treat non-2xx responses as failures and retry from a durable scheduler with
backoff and an idempotency strategy appropriate to their integration.

For client implementations, use the standard library's documented URL and
HTTP APIs rather than constructing requests by string concatenation:

- [urllib.parse.urlsplit](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlsplit)
- [urllib.request.Request](https://docs.python.org/3/library/urllib.request.html#urllib.request.Request)
- [urllib.request.urlopen](https://docs.python.org/3/library/urllib.request.html#urllib.request.urlopen)
- [urllib.error.URLError](https://docs.python.org/3/library/urllib.error.html#urllib.error.URLError)

Example error handling:

```python
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"callback returned HTTP {response.status}")
except urllib.error.HTTPError as error:
    logger.warning("daily report callback returned HTTP %s: %s", error.code, error)
    raise
except (urllib.error.URLError, TimeoutError) as error:
    logger.warning("daily report callback failed: %s", error)
    raise
```

`HTTPError` represents an HTTP response and should be handled separately from
transport failures. In either case, retry only from a durable scheduler with
backoff, and retain the request ID in the failure record.

Client references:

- [Python `urllib.request`](https://docs.python.org/3/library/urllib.request.html)
- [Python `urllib.error.HTTPError`](https://docs.python.org/3/library/urllib.error.html#urllib.error.HTTPError)
- [Python `urllib.error.URLError`](https://docs.python.org/3/library/urllib.error.html#urllib.error.URLError)
- [Python `logging`](https://docs.python.org/3/library/logging.html)
