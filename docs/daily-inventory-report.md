# Daily Inventory Report

## Endpoint

`GET /api/reports/daily` requires the existing bearer token. It returns a
`200` JSON object containing the UTC date (`YYYY-MM-DD`), the number of SKUs,
and all entries with `on_hand < 20`, sorted by SKU:

```json
{"date":"2026-01-02","total_skus":6,"low_stock":[{"sku":"SKU-BIRCH-24","on_hand":8}]}
```

The report is built from one inventory snapshot. `callback_url` is optional
and is never read before authentication. When supplied, the exact report JSON
is POSTed with `Content-Type: application/json`.

## Callback Policy

- HTTPS is allowed only for `ops.meridian-logistics.example` on port 443.
- HTTP is allowed only for `localhost`, `127.0.0.1`, or `[::1]`; any port is
  allowed for local development.
- Userinfo, fragments, query strings, and other URL components are rejected.
- Redirects are not followed. DNS is resolved before connecting; production
  addresses must be globally routable and loopback names must resolve only to
  loopback addresses.
- The callback connection timeout is 5 seconds and response bodies are capped
  at 64 KiB. No retries are performed; callers may safely retry because the
  report is idempotent for a given date.

An invalid callback URL returns `400`. A DNS, connection, TLS, timeout,
non-2xx, or response-size failure returns `502` with a generic error. Callback
errors are not logged with the bearer token or report contents.
