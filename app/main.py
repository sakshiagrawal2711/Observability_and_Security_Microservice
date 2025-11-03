import hashlib
import secrets
import asyncio
import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import Response
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from . import db
from . import models
from . import notifier
import psutil
from passlib.hash import pbkdf2_sha256

app = FastAPI(title="System Calculator - Observability & Security Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def hash_password(password: str, salt: str) -> str:
    # use PBKDF2-SHA256 for password hashing (no 72-byte limit)
    return pbkdf2_sha256.hash(salt + password)


@app.on_event('startup')
async def startup_event():
    db.init_db()
    # Collector can be disabled or tuned via environment variables for hosted platforms (e.g., Render)
    collector_enabled = os.environ.get('COLLECTOR_ENABLED', '1')
    if collector_enabled and collector_enabled != '0' and collector_enabled.lower() != 'false':
        app.state.collector_task = asyncio.create_task(metric_collector())
    else:
        app.state.collector_task = None


@app.on_event('shutdown')
async def shutdown_event():
    task = app.state.collector_task
    task.cancel()


async def metric_collector():
    # Collect cpu and memory periodically
    try:
        # sample interval (seconds) can be controlled by SAMPLE_INTERVAL env var
        sample_interval = float(os.environ.get('SAMPLE_INTERVAL', '5.0'))
        while True:
            # use a short non-blocking CPU probe then sleep to control frequency
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
            # read thresholds
            th = db.get_thresholds()
            cpu_th = th.get('cpu_threshold', 80.0)
            mem_th = th.get('memory_threshold', 75.0)
            db.add_metric(cpu, mem)
            # generate alerts based on thresholds
            if cpu > cpu_th:
                db.add_alert('cpu', cpu)
                # schedule notifier asynchronously so collector isn't blocked
                try:
                    asyncio.create_task(notifier.notify_alert('cpu', cpu, datetime.utcnow().isoformat()))
                except Exception:
                    # if scheduling fails, continue without raising
                    pass
            if mem > mem_th:
                db.add_alert('memory', mem)
                try:
                    asyncio.create_task(notifier.notify_alert('memory', mem, datetime.utcnow().isoformat()))
                except Exception:
                    pass
            # sleep for configured interval to reduce collector frequency when hosted
            await asyncio.sleep(max(0.1, sample_interval))
    except asyncio.CancelledError:
        return


@app.get('/')
def root():
    """Root: redirect to dashboard if static UI is present, otherwise return a small JSON."""
    static_dir = pathlib.Path(__file__).parent.parent / 'dashboard'
    if static_dir.exists():
        # redirect browsers to the dashboard index
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url='/dashboard/')
    return {'service': 'ok'}


@app.get('/health')
def health():
    """Simple health endpoint for Render or load balancers."""
    collector_running = bool(getattr(app.state, 'collector_task', None))
    return {'status': 'ok', 'collector_running': collector_running}


@app.post('/register')
def register(req: models.RegisterRequest):
    existing = db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail='username exists')
    salt = secrets.token_hex(8)
    ph = hash_password(req.password, salt)
    uid = db.create_user(req.username, salt, ph)
    return {"user_id": uid}


@app.post('/login')
def login(req: models.LoginRequest):
    user = db.get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail='invalid')
    # verify stored hash
    if not pbkdf2_sha256.verify(user['salt'] + req.password, user['password_hash']):
        raise HTTPException(status_code=401, detail='invalid')
    token = secrets.token_urlsafe(24)
    db.create_session(token, user['id'])
    return models.SessionResponse(token=token)


@app.get('/validate-session')
def validate_session(token: Optional[str] = None):
    if not token:
        raise HTTPException(status_code=400, detail='token required')
    ok = db.validate_session(token)
    return {"valid": ok}


@app.post('/logs/analyze')
def analyze_logs(payload: models.LogAnalyzeRequest):
    lines = payload.logs.splitlines()
    counts = {"INFO": 0, "WARN": 0, "ERROR": 0}
    errors = {}
    for l in lines:
        for lvl in counts.keys():
            if lvl in l:
                counts[lvl] += 1
                if lvl == 'ERROR':
                    errors[l] = errors.get(l, 0) + 1
    top_errors = sorted(errors.items(), key=lambda x: x[1], reverse=True)[:5]
    top_err_list = [e[0] for e in top_errors]
    return models.LogAnalyzeResponse(counts=counts, top_errors=top_err_list)


def require_token(token: Optional[str] = Header(None)):
    if not token or not db.validate_session(token):
        raise HTTPException(status_code=401, detail='invalid token')
    return token


@app.get('/summary', response_model=models.SummaryResponse)
def summary(n: int = 5, token: str = Depends(require_token)):
    s = db.get_summary(last_n_alerts=n)
    return models.SummaryResponse(**s)


@app.get('/thresholds')
def get_thresholds(token: str = Depends(require_token)):
    # attempt to return per-user thresholds if set; fall back to global config
    user_id = db.get_user_id_by_token(token)
    if user_id:
        ut = db.get_user_thresholds(user_id)
        if ut:
            return ut
    return db.get_thresholds()


@app.post('/thresholds')
def post_thresholds(payload: dict, token: str = Depends(require_token)):
    try:
        cpu = float(payload.get('cpu_threshold'))
        mem = float(payload.get('memory_threshold'))
    except Exception:
        raise HTTPException(status_code=400, detail='invalid payload')
    # store per-user thresholds when possible, otherwise update global config
    user_id = db.get_user_id_by_token(token)
    if user_id:
        db.set_user_thresholds(user_id, cpu, mem)
    else:
        db.set_thresholds(cpu, mem)
    return {'cpu_threshold': cpu, 'memory_threshold': mem}


@app.get('/metrics')
def metrics(limit: int = 100, token: str = Depends(require_token)):
    return db.get_metrics(limit=limit)


@app.get('/alerts')
def alerts(limit: int = 100, token: str = Depends(require_token)):
    return db.get_alerts(limit=limit)


@app.post('/logout')
def logout(token: str = Depends(require_token)):
    # token already validated by dependency; delete session
    db.delete_session(token)
    return {'ok': True}


@app.get('/metrics/history')
def metrics_history(start: str, end: str, token: str = Depends(require_token)):
    # start and end expected as ISO timestamps
    try:
        data = db.get_metrics_by_range(start, end)
    except Exception as e:
        raise HTTPException(status_code=400, detail='invalid time range')
    return data


@app.get('/metrics/export')
def metrics_export(start: Optional[str] = None, end: Optional[str] = None, token: str = Depends(require_token)):
    """Return metrics as CSV. If start and end ISO strings are provided, export that range; otherwise export recent metrics (limit 1000)."""
    try:
        if start and end:
            rows = db.get_metrics_by_range(start, end)
        else:
            rows = db.get_metrics(limit=1000)
    except Exception:
        raise HTTPException(status_code=400, detail='invalid time range')

    # build CSV
    lines = ['timestamp,cpu,memory']
    for r in rows:
        # ensure values are serialized without extra formatting
        lines.append(f"{r.get('ts')},{r.get('cpu')},{r.get('memory')}")

    csv_text = "\n".join(lines)
    fname = f"metrics_{datetime.utcnow().isoformat().replace(':','-')}.csv"
    return Response(content=csv_text, media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="{fname}"'
    })


# Serve a tiny dashboard if present
from fastapi.staticfiles import StaticFiles
import pathlib

static_dir = pathlib.Path(__file__).parent.parent / 'dashboard'
if static_dir.exists():
    app.mount('/dashboard', StaticFiles(directory=str(static_dir), html=True), name='dashboard')


# --- simple admin protection using an ADMIN_TOKEN env var ---
from fastapi import Header


def require_admin(x_admin_token: str = Header(None)):
    admin_token = os.environ.get('ADMIN_TOKEN')
    if not admin_token:
        raise HTTPException(status_code=403, detail='admin not configured')
    if not x_admin_token or x_admin_token != admin_token:
        raise HTTPException(status_code=401, detail='invalid admin token')
    return True


@app.get('/admin/thresholds')
def admin_get_thresholds(_ok: bool = Depends(require_admin)):
    return db.get_thresholds()


@app.post('/admin/thresholds')
def admin_post_thresholds(payload: dict, _ok: bool = Depends(require_admin)):
    try:
        cpu = float(payload.get('cpu_threshold'))
        mem = float(payload.get('memory_threshold'))
    except Exception:
        raise HTTPException(status_code=400, detail='invalid payload')
    db.set_thresholds(cpu, mem)
    return {'cpu_threshold': cpu, 'memory_threshold': mem}
