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
- POST /logout — invalidate token.
- GET /summary?n=10 — reporting summary (requires token in `token` header).
- POST /logs/analyze — simple log analysis (counts, top errors).
- GET /metrics, GET /metrics/history — recent metrics or metrics in a time range (token required).
- GET /alerts — recent alerts (token required).
- GET/POST /thresholds — view and set CPU/memory thresholds (token required).
- /dashboard — static UI to interact with the service.

Notes and tips
- The app stores data in `system_calculator.db` by default. Add that filename to your `.gitignore` to avoid committing it (already included).
- `passlib` is used for password hashing (pbkdf2_sha256) to avoid native bcrypt dependency issues.
- For production use consider HTTPS, stronger session management, per-user thresholds, and a proper DB server.

Ready to push
- I've added a `.gitignore` that excludes venvs, caches, DB files, logs and editor settings.
- If you'd like, I can create a GitHub repository, initialize git, commit, and push — tell me the remote URL or grant access.

If you want any changes to the README or the project layout before pushing, tell me which items to adjust.
