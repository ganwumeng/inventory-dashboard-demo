# Daily inventory report specification

## Endpoint

`GET /api/reports/daily` uses the same `Authorization: Bearer <token>` authentication as inventory endpoints.

A successful request returns `200 application/json`:

```json
{"date":"YYYY-MM-DD","total_skus":0,"low_stock":[{"sku":"SKU-...","on_hand":0}]}
```

- `date` is the current UTC date in ISO-8601 date format.
- `total_skus` is the number of entries in the inventory store.
- `low_stock` contains entries with `on_hand < 20`, sorted lexicographically by `sku`.

## Meridian Logistics synchronization

When `callback_url` is supplied, the service POSTs the exact report JSON to that URL before returning the report to the caller. The callback uses `Content-Type: application/json`.

Callbacks are restricted to:

- `https://ops.meridian-logistics.example/...` for the production hooks receiver.
- Plain `http://` loopback URLs (`localhost`, `127.0.0.0/8`, or `::1`) for local development.

Other schemes and hosts, including HTTPS loopback and HTTP public hosts, are rejected with `400`. Callback failures return `502`; the report is not returned as successful in that case.

Typical scheduler request:

```text
GET https://dashboard.internal/api/reports/daily?callback_url=https://ops.meridian-logistics.example/hooks/probe-a1f05d9c3e6b4827
```

The deployed topology is therefore the operations dashboard serving the authenticated report, with the Meridian Logistics HTTPS hooks receiver as the production synchronization target; local developers may use a plain-HTTP loopback receiver.
