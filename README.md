# Observability & Security Microservice (FastAPI)

This project implements the intern assignment from the provided PDF: a small microservice that collects system metrics, generates alerts on thresholds, provides secure session-based access, and exposes a reporting API.

Quick start (PowerShell)

# Observability & Security Microservice (FastAPI)

A compact FastAPI application that implements the intern assignment: it collects system metrics, raises alerts when thresholds are exceeded, provides secure register/login/session management, a log analyzer endpoint, and a small static dashboard for visualization.

Quick start (PowerShell)

```powershell
# create and activate a venv (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install deps
python -m pip install -r requirements.txt

# run the app (development)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# run tests
.\.venv\Scripts\python.exe -m pytest -q
```

What this repo contains
- app/: FastAPI application and DB helper (SQLite).
- dashboard/: a single-file static dashboard served at `/dashboard` (charts, alerts, thresholds, register/login).
- tests/: pytest-based tests (async integration tests using httpx ASGI transport).
- requirements.txt: Python dependencies.

Useful endpoints
- POST /register — create an account (body: {username,password}).
- POST /login — authenticate and receive a token (body: {username,password}).
# Observability & Security Microservice (FastAPI)

A compact FastAPI application implementing the intern assignment: it collects system metrics, raises alerts when thresholds are exceeded, provides register/login/session management, a log-analyzer endpoint, and a small static dashboard for visualization.

Quick start (PowerShell)
```powershell
# create and activate a venv (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install deps
python -m pip install -r requirements.txt

# run the app (development)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# run tests
.\.venv\Scripts\python.exe -m pytest -q
```

Repository layout
- `app/` — FastAPI application, DB helpers and notifier.
- `dashboard/` — static single-file dashboard served at `/dashboard`.
- `tests/` — pytest test suite (async tests using httpx ASGI transport).
- `scripts/seed_demo.py` — demo seeder to populate the DB with sample data.
- `requirements.txt` — Python dependencies.

Useful endpoints
- POST `/register` — create an account (body: {username, password}).
- POST `/login` — authenticate and receive a token (body: {username, password}).
- POST `/logout` — invalidate token.
- GET `/summary?n=10` — reporting summary (requires token in `token` header).
- POST `/logs/analyze` — simple log analysis (counts, top errors).
- GET `/metrics`, GET `/metrics/history` — recent metrics or metrics in a time range (token required).
- GET `/alerts` — recent alerts (token required).
- GET/POST `/thresholds` — view and set CPU/memory thresholds (token required).
- `/dashboard` — static UI to interact with the service.

Database
- By default the app uses an on-disk SQLite DB `system_calculator.db` in the repository root. Add it to `.gitignore` if you don't want to commit it.

Notifier / alert delivery configuration
The notifier supports multiple delivery options. All are optional — if not configured the notifier simply logs alerts to the server console.

- SMTP email (best-effort):
	- `ALERT_SMTP_HOST` — SMTP host (e.g. `smtp.example.com`)
	- `ALERT_SMTP_PORT` — SMTP port (default `587`)
	- `ALERT_SMTP_USER` — SMTP username (optional)
	- `ALERT_SMTP_PASS` — SMTP password (optional)
	- `ALERT_FROM` — From email address
	- `ALERT_TO` — To email address

- Webhook POST (async with retries):
	- `ALERT_WEBHOOK_URL` — URL to POST alert payloads (JSON)
	- `ALERT_WEBHOOK_RETRIES` — number of retries on failure (default `3`)
	- `ALERT_WEBHOOK_BACKOFF` — base backoff seconds for exponential backoff (default `1.0`)

Payload shape (JSON) sent to webhook endpoint:
```json
{
	"type": "cpu",
	"value": 92.5,
	"ts": "2025-10-25T00:00:00Z",
	"generated_at": "2025-10-25T00:00:01Z"
}
```

Admin UI (global thresholds)
- A lightweight admin UI is available at `/dashboard/admin.html` (served with the other static assets).
- Authentication for admin endpoints is performed with a simple server-side token. Set this env var on the server:
	- `ADMIN_TOKEN` — a shared secret used to call the admin endpoints.
- The admin page asks you to paste the `ADMIN_TOKEN` and then lets you GET/POST global thresholds. This updates the `config` table used by the collector.

Example: set ADMIN_TOKEN and run the server (PowerShell):
```powershell
$env:ADMIN_TOKEN = 'change-me'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/dashboard/admin.html`, paste the token, click Load, edit thresholds and Save.

Testing / CI
- Unit and integration tests are implemented with `pytest` (async tests use pytest-asyncio + httpx ASGI transport). Run locally with:
```powershell
python -m pytest -q
```

- GitHub Actions (suggested workflow)
Create `.github/workflows/ci.yml` with a small job that checks out code, sets up Python, installs requirements, and runs tests. Example:

```yaml
name: CI

on: [push, pull_request]

jobs:
	test:
		runs-on: ubuntu-latest
		steps:
			- uses: actions/checkout@v4
			- name: Set up Python
				uses: actions/setup-python@v4
				with:
					python-version: '3.12'
			- name: Install dependencies
				run: python -m pip install -r requirements.txt
			- name: Run tests
				run: python -m pytest -q
```

Add the workflow file to the repo and push — GitHub will run tests on each push/PR.

Seeding demo data
-----------------
To quickly populate the DB with a demo user, metrics and alerts, run the seeder script:

```powershell
python scripts\seed_demo.py --db system_calculator.db
```

The script will print a demo `token` you can paste into the dashboard header to view the seeded data.

Notes and recommendations
- The app currently uses naive UTC timestamps (datetime.utcnow()). For production it is recommended to use timezone-aware datetimes (datetime.now(timezone.utc)). I can convert the codebase to timezone-aware datetimes if you want.
- The notifier is best-effort: failures are logged but do not stop metric collection. For production you may want retries metrics, monitoring, authentication for webhooks (HMAC), and more robust error reporting.



