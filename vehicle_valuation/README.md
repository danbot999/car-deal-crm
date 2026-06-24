# NZ Vehicle Market Index

This service builds a local index of public NZ vehicle asking prices and values
Facebook Marketplace targets against deduplicated NZ comparables. Exact
same-year/make/model listings always take priority; an evidence-labelled
generation, model or class fallback keeps difficult cars numeric instead of
ending in `INSUFFICIENT_DATA`.
It stores asking-price history; it does not represent asking prices as completed
sale prices.

## Runtime

- FastAPI: `http://127.0.0.1:8010`
- SQLite index: `crm/work/vehicle-valuation.db` in WAL mode
- Worker reconciliation: every 10 minutes
- Portal refresh: every 6 hours
- Dealer-directory discovery: daily
- Target revaluation: after material changes or after 24 hours
- Live search budget: up to 15 minutes per shared year/make/model identity
- Concurrent grouped searches: 3 (duplicate identities reuse one crawl)

Install and start the supervised Windows task from `crm/`:

```powershell
npm.cmd run valuation:install
```

Manual commands from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m vehicle_valuation.run_api
.\.venv\Scripts\python.exe -m vehicle_valuation.worker
.\.venv\Scripts\python.exe -m vehicle_valuation.worker --backfill --limit 20 --once
```

## API

- `POST /v1/jobs`
- `POST /v1/jobs/batch`
- `GET /v1/jobs/{jobId}`
- `POST /v1/jobs/{jobId}/retry`
- `GET /v1/valuations/{listingId}`
- `GET /v1/valuations/{listingId}/comparables`
- `GET /v1/sources/coverage`

The CRM exposes `/market-evidence` and `/market-evidence/[listingId]` for the
full accepted/excluded link audit, calculation method and source diagnostics.

Protected endpoints use `Authorization: Bearer <CRM_INGEST_TOKEN>`. The n8n and
Admin helper routes are intentionally loopback-only because Uvicorn binds to
`127.0.0.1` by default.

The crawler does not bypass authentication, CAPTCHA, rate limits, or access
controls. A blocked source is recorded in coverage diagnostics and valuation
continues with successful sources.
