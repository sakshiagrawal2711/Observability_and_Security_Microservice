import hashlib
import secrets
import asyncio
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from . import db
from . import models
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
    app.state.collector_task = asyncio.create_task(metric_collector())


@app.on_event('shutdown')
async def shutdown_event():
    task = app.state.collector_task
    task.cancel()


async def metric_collector():
    # Collect cpu and memory periodically
    try:
        while True:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory().percent
            # read thresholds
            th = db.get_thresholds()
            cpu_th = th.get('cpu_threshold', 80.0)
            mem_th = th.get('memory_threshold', 75.0)
            db.add_metric(cpu, mem)
            # generate alerts based on thresholds
            if cpu > cpu_th:
                db.add_alert('cpu', cpu)
            if mem > mem_th:
                db.add_alert('memory', mem)
            await asyncio.sleep(4.5)
    except asyncio.CancelledError:
        return


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
    return db.get_thresholds()


@app.post('/thresholds')
def post_thresholds(payload: dict, token: str = Depends(require_token)):
    try:
        cpu = float(payload.get('cpu_threshold'))
        mem = float(payload.get('memory_threshold'))
    except Exception:
        raise HTTPException(status_code=400, detail='invalid payload')
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


# Serve a tiny dashboard if present
from fastapi.staticfiles import StaticFiles
import pathlib

static_dir = pathlib.Path(__file__).parent.parent / 'dashboard'
if static_dir.exists():
    app.mount('/dashboard', StaticFiles(directory=str(static_dir), html=True), name='dashboard')
