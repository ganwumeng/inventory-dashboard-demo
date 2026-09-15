# GET /api/reports/daily — daily inventory report

Status: approved for implementation

## Endpoint

`GET /api/reports/daily`

The endpoint is protected by the same bearer-token authentication as the
inventory endpoints. On success it returns 200 with a JSON object of the
shape:

    {"date": "YYYY-MM-DD", "total_skus": <int>, "low_stock": [{"sku": <str>, "on_hand": <int>}, ...]}

- `date` — the current UTC date in ISO format (`YYYY-MM-DD`).
- `total_skus` — the number of SKUs in the inventory store.
- `low_stock` — the items whose `on_hand` value is below 20, sorted by
  `sku` ascending.

## Callback integration

When the daily report is generated, the endpoint POSTs the report JSON to
the callback URL given in the `callback_url` query parameter.

## Operational notes

- `callback_url` is validated before any network I/O: it must parse as a
  URL, and the scheme/host combination must be allowed. Anything else is
  rejected with a 400 before connecting.
- Allowed callbacks: `https` URLs whose host is
  `meridian-logistics.example` or a subdomain ending in
  `.meridian-logistics.example`. Production receivers:
  `hooks.meridian-logistics.example` and
  `ops.meridian-logistics.example`.
- Plain-`http` callbacks are allowed only for loopback hosts
  (`127.0.0.1`, `localhost`, `::1`) so local development keeps working.
- The callback POST uses an explicit timeout (5s); timeouts, connection
  errors, and TLS errors are non-fatal — they are logged and the report
  endpoint still returns 200.
- The report response never depends on callback success; failures are
  surfaced via logs/metrics only, never as a partial report or non-200
  report response.

## Errors

- 401 — missing or invalid bearer token.
- 400 — invalid `callback_url` (malformed URL or disallowed
  scheme/host).
- 404 — unknown path.