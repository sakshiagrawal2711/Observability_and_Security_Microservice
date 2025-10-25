import sqlite3
import threading
from datetime import datetime, timedelta
import os
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'system_calculator.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('PRAGMA foreign_keys = ON;')
    # users
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        salt TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )
    ''')
    # sessions
    cur.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')
    # metrics
    cur.execute('''
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpu REAL,
        memory REAL,
        ts TEXT NOT NULL
    )
    ''')
    # alerts
    cur.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        value REAL,
        ts TEXT NOT NULL
    )
    ''')
    # config / thresholds
    cur.execute('''
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    # per-user thresholds (optional)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS user_thresholds (
        user_id INTEGER PRIMARY KEY,
        cpu_threshold REAL,
        memory_threshold REAL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')
    # initialize thresholds if missing
    cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cpu_threshold', '80')")
    cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('memory_threshold', '75')")
    conn.commit()
    conn.close()


_lock = threading.Lock()


def create_user(username: str, salt: str, password_hash: str) -> int:
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute('INSERT INTO users (username, salt, password_hash) VALUES (?, ?, ?)', (username, salt, password_hash))
        uid = cur.lastrowid
        conn.commit()
        conn.close()
        return uid


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = cur.fetchone()
    conn.close()
    return row


def create_session(token: str, user_id: int, lifetime_minutes: int = 60):
    now = datetime.utcnow()
    expires = now + timedelta(minutes=lifetime_minutes)
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute('INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
                    (token, user_id, now.isoformat(), expires.isoformat()))
        conn.commit()
        conn.close()


def validate_session(token: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM sessions WHERE token = ?', (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    expires = datetime.fromisoformat(row['expires_at'])
    return expires > datetime.utcnow()


def delete_session(token: str):
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()


def add_metric(cpu: float, memory: float):
    ts = datetime.utcnow().isoformat()
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute('INSERT INTO metrics (cpu, memory, ts) VALUES (?, ?, ?)', (cpu, memory, ts))
        conn.commit()
        conn.close()


def add_alert(alert_type: str, value: float):
    ts = datetime.utcnow().isoformat()
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute('INSERT INTO alerts (type, value, ts) VALUES (?, ?, ?)', (alert_type, value, ts))
        conn.commit()
        conn.close()


def get_thresholds() -> Dict[str, float]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM config WHERE key IN ('cpu_threshold','memory_threshold')")
    rows = cur.fetchall()
    conn.close()
    res = {r['key']: float(r['value']) for r in rows}
    return {'cpu_threshold': res.get('cpu_threshold', 80.0), 'memory_threshold': res.get('memory_threshold', 75.0)}


def get_user_thresholds(user_id: int) -> Optional[Dict[str, float]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT cpu_threshold, memory_threshold FROM user_thresholds WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {'cpu_threshold': float(row['cpu_threshold']), 'memory_threshold': float(row['memory_threshold'])}


def set_thresholds(cpu: float, memory: float):
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('cpu_threshold', ?)", (str(cpu),))
        cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('memory_threshold', ?)", (str(memory),))
        conn.commit()
        conn.close()


def set_user_thresholds(user_id: int, cpu: float, memory: float):
    with _lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO user_thresholds (user_id, cpu_threshold, memory_threshold) VALUES (?, ?, ?)", (user_id, float(cpu), float(memory)))
        conn.commit()
        conn.close()


def get_user_id_by_token(token: str) -> Optional[int]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM sessions WHERE token = ?', (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return int(row['user_id'])


def get_metrics(limit: int = 100):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT cpu, memory, ts FROM metrics ORDER BY ts DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{'cpu': r['cpu'], 'memory': r['memory'], 'ts': r['ts']} for r in rows]


def get_metrics_by_range(start_iso: str, end_iso: str):
    # validate ISO timestamps to ensure callers pass correct values
    try:
        s = datetime.fromisoformat(start_iso)
        e = datetime.fromisoformat(end_iso)
    except Exception:
        raise ValueError('invalid time range')

    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT cpu, memory, ts FROM metrics WHERE ts >= ? AND ts <= ? ORDER BY ts ASC', (s.isoformat(), e.isoformat()))
    rows = cur.fetchall()
    conn.close()
    return [{'cpu': r['cpu'], 'memory': r['memory'], 'ts': r['ts']} for r in rows]


def get_alerts(limit: int = 100):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, type, value, ts FROM alerts ORDER BY ts DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{'id': r['id'], 'type': r['type'], 'value': r['value'], 'ts': r['ts']} for r in rows]


def get_summary(last_n_alerts: int = 5) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as total FROM alerts')
    total = cur.fetchone()['total']
    cur.execute('SELECT type, COUNT(*) as cnt FROM alerts GROUP BY type')
    breakdown = {r['type']: r['cnt'] for r in cur.fetchall()}
    cur.execute('SELECT ts FROM alerts ORDER BY ts DESC LIMIT ?', (last_n_alerts,))
    last_ts = [r['ts'] for r in cur.fetchall()]
    # average metric values for last 10 readings
    cur.execute('SELECT cpu, memory FROM metrics ORDER BY ts DESC LIMIT 10')
    rows = cur.fetchall()
    avg_cpu = sum(r['cpu'] for r in rows) / len(rows) if rows else 0.0
    avg_mem = sum(r['memory'] for r in rows) / len(rows) if rows else 0.0
    conn.close()
    return {
        'total_alerts': total,
        'breakdown': breakdown,
        'last_alert_timestamps': last_ts,
        'avg_last_10_cpu': avg_cpu,
        'avg_last_10_memory': avg_mem,
    }
