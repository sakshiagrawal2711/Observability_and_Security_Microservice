# Architecture Notes — Observability & Security Microservice

These notes describe the design and runtime architecture of the Observability & Security Microservice implemented in this repository. They are written for submission and provide enough detail for a reviewer to understand component responsibilities, data flow, data model, deployment, and validation steps.

---

## 1. High-level overview

The service is a compact observability microservice that:
- Periodically samples system metrics (CPU and memory) using a background collector.
- Persists metrics to a local SQLite database.
- Compares metrics to configured thresholds and generates alerts when thresholds are exceeded.
- Delivers alerts via configurable notifiers (console, webhook POSTs with retries, optional SMTP email).
- Exposes a small REST API for registration/login, metrics, alerts, thresholds, and reporting.
- Provides a simple static dashboard UI to visualize metrics, alerts, and manipulate thresholds.

Primary design goals:
- Simplicity: small, readable codebase suitable for an intern assignment.
- Testability: unit and integration tests (pytest + pytest-asyncio + httpx ASGI transport).
- Extensibility: pluggable notifier model and clear DB helper layer to allow swapping SQLite for another DB later.

Technology stack:
- Python 3.x, FastAPI web framework, uvicorn ASGI server
- SQLite for persistence (file `system_calculator.db`)
- psutil for sampling system metrics
- httpx (async) for webhook delivery
- Chart.js + vanilla JS for static dashboard

---

## 2. Logical components

1) Metric Collector (Background Task)
- Runs in the FastAPI application startup event.
- Samples CPU and memory (via psutil) on a short interval (configurable inside the collector).
- Persists each sample to the `metrics` table.
- Immediately checks configured thresholds (global and per-user) and creates an `alerts` row when exceeded.
- Schedules alert delivery by calling the async notifier non-blockingly (background task / asyncio.create_task).

2) API Layer (`app/main.py`)
- Exposes endpoints for user registration/login, session validation, metrics query, metrics history (with ISO timestamp validation), alerts, thresholds CRUD, log analysis and reporting endpoints.
- Protects user-facing endpoints with a token stored in the DB (sessions table). Tokens are returned on successful login and must be supplied in the `token` header.
- Admin endpoints are protected via a server-side `ADMIN_TOKEN` env var expected in the `x-admin-token` header.

3) Notifier (`app/notifier.py`)
- Async-first design: uses `httpx.AsyncClient` for webhook POSTs with configurable retries and exponential backoff.
- SMTP email sending is invoked in a non-blocking way (background thread / asyncio.to_thread) so that the collector isn't blocked by slow IO.
- If message deliveries are not configured, notifier falls back to writing to the server console for visibility.

4) Persistence / DB Layer (`app/db.py`)
- SQLite with a minimal schema: `users`, `sessions`, `metrics`, `alerts`, `config` (global thresholds) and `user_thresholds` (per-user overrides).
- DB helper functions encapsulate SQL and provide validation (for example: ISO timestamp parsing for history queries).

5) Frontend (`dashboard/`)
- Single-page static UI with login/register forms, charts rendered by Chart.js, threshold editing UI and alerts list.
- Admin UI at `/dashboard/admin.html` uses `ADMIN_TOKEN` for protected operations to edit global thresholds.

6) Tests (`tests/`)
- Pytest + pytest-asyncio used for unit and integration tests.
- Notifier tests mock the webhook (via httpx mocking) and SMTP send to verify retry logic and background dispatch.

7) Packaging / Dev Ops
- Dockerfile and `docker-compose.yml` are included for containerized runs.
- A suggested GitHub Actions workflow is provided in the README; it can be added to `.github/workflows/ci.yml` to run the tests automatically.

---

## 3. Data model (summary)

- users
  - id (PK), username, password_hash, created_at

- sessions
  - id (PK), user_id (FK), token, created_at, expires_at

- metrics
  - id (PK), metric_type (cpu|memory), value (float), ts (ISO-8601 UTC string), inserted_at

- alerts
  - id (PK), user_id (nullable), metric_type, value, threshold, ts (when sample taken), generated_at (when alert row inserted), delivered (bool)

- config (global)
  - key, value (used to store global CPU/MEM thresholds and other settings)

- user_thresholds
  - id (PK), user_id, metric_type, threshold_value

Notes:
- Timestamps in the current implementation are stored as naive UTC strings (ISO-8601). For production, convert to timezone-aware datetimes (UTC) and store as ISO with Z or as integer epoch.

---

## 4. Data flow and sequence (textual diagram)

1) Collector tick
  - Collector reads current CPU and memory via psutil.
  - Collector writes a `metrics` row.
  - Collector queries thresholds (global and per-user).
  - If metric > threshold => create `alerts` row and schedule notifier.

2) Notifier delivery
  - FastAPI schedules an async notification (async task) so collector returns quickly.
  - Notifier attempts webhook POST (async) with exponential backoff on failure.
  - Notifier optionally calls SMTP send in background thread.
  - Notifier logs outcomes and marks `alerts.delivered` as appropriate (in future: telemetry counters).

3) Client interaction
  - Dashboard or API client uses token in `token` header to query `/metrics`, `/alerts` and `/summary`.
  - Admin UI uses `x-admin-token` to fetch/update global thresholds.

---

## 5. Deployment & runtime

Local development (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Docker (example):
```powershell
docker build -t obs-microservice .
docker run --rm -p 8000:8000 obs-microservice
```

Environment variables of note:
- `ADMIN_TOKEN` — Protects admin endpoints. Required by admin UI.
- `ALERT_WEBHOOK_URL`, `ALERT_WEBHOOK_RETRIES`, `ALERT_WEBHOOK_BACKOFF` — Webhook delivery config.
- `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASS`, `ALERT_FROM`, `ALERT_TO` — SMTP config (optional).

For production deploys consider:
- Using a managed DB (Postgres) instead of SQLite.
- Running behind HTTPS with proper certificates and authentication.
- Placing the collector in a separate process or worker if sampling becomes heavy.

---

## 6. Security considerations

- Authentication
  - Session tokens are opaque tokens stored in the DB. They should be long, unguessable, and have expirations set.

- Secrets
  - Store `ADMIN_TOKEN` and SMTP credentials in environment variables or a secrets manager — do not commit them.

- Webhooks
  - For production, protect webhook endpoints with HMAC signatures and verify signatures server-side. The current system only POSTs alerts; webhook receivers should verify authenticity.

- Data exposure
  - The dashboard and API require tokens — ensure the UI is served only over HTTPS and tokens stored in browser storage are protected by same-site cookie or secure storage patterns for production.

---

## 7. Scalability and improvements

Short-term improvements (low effort):
- Convert timestamps to timezone-aware (UTC) datetimes.
- Add more metrics (disk, network) and tune collection frequency.
- Add metrics and telemetry for the notifier itself (success/failure counts, latency histogram).

Medium-term improvements:
- Move persistence to PostgreSQL.
- Replace in-process collector with a separate worker (e.g., Celery or a small asyncio worker service) to allow horizontal scaling.
- Add an internal message queue (Redis / Kafka) for alert delivery and retry handling.

Long-term production hardening:
- AuthZ: per-user roles and permissions for admin operations.
- Observability: add Prometheus metrics for the app, Grafana dashboards, and structured logs.

---

## 8. How to validate and test (quick checklist)

1) Run unit & integration tests
```powershell
python -m pytest -q
```

2) Start the server and seed demo data
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
python scripts\seed_demo.py --db system_calculator.db
```
Open `http://localhost:8000/dashboard`, paste the demo token printed by the seeder, and inspect charts and alerts.

3) Verify notifier behavior
- Set `ALERT_WEBHOOK_URL` to a simple request inspector (e.g. webhook.site or a local httpbin) and trigger a high metric (you can edit thresholds via admin UI) to confirm webhook POSTs and retries.

---

## 9. Next steps (recommended for submission)

- Include this `ARCHITECTURE.md` in the project root (done).
- Optionally add the GitHub Actions workflow to `.github/workflows/ci.yml` to run tests automatically.
- Optionally convert to timezone-aware datetimes and add Prometheus metrics for the collector and notifier.

---

Thank you — if you'd like I can also:
- Generate a short slide deck summary (3–5 slides) for submission.
- Add `.github/workflows/ci.yml` and commit it.
- Convert timestamps to timezone-aware datetimes across the codebase.
