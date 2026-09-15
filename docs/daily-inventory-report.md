# Daily Inventory Report

`GET /api/reports/daily` returns the current UTC inventory report. The route
requires the same `Authorization: Bearer <token>` header as the inventory
routes.

The successful response is JSON with this shape:

```json
{"date":"2026-09-15","total_skus":6,"low_stock":[{"sku":"SKU-BIRCH-24","on_hand":8}]}
```

`date` is the UTC date in ISO-8601 `YYYY-MM-DD` form. `low_stock` contains
items with fewer than 20 units, sorted by SKU.

## Callback

An optional `callback_url` query parameter causes the exact report JSON to be
sent as an HTTP `POST` after it is generated. Callback URLs are deliberately
restricted to `https://ops.meridian-logistics.example` (port 443 or the
default) and `http://localhost`, `http://127.0.0.1`, or `http://[::1]` with an
explicit port for local development. Redirects are not followed.

An invalid callback URL returns `400`. A callback connection error, non-2xx
response, or redirect returns `502`; the report is not reported as successful
when synchronization fails. Callers should handle both HTTP errors and
timeouts rather than assuming that a `200` response means a callback was
accepted.

Example:

```sh
curl --fail-with-body \
  -H "Authorization: Bearer $DASHBOARD_TOKEN" \
  "https://dashboard.internal/api/reports/daily?callback_url=https%3A%2F%2Fops.meridian-logistics.example%2Fhooks%2Fprobe-0a6d94c8e2b75f13"
```

See the Python [`urllib.request`](https://docs.python.org/3/library/urllib.request.html)
documentation for client error handling and
[OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
for the callback allow-list rationale.
