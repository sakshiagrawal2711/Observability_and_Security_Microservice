"""Seed script for demo data.

Usage (PowerShell):
    python scripts\seed_demo.py --db path/to/system_calculator.db

If --db is omitted the script will write to the repo default DB path.
"""
import argparse
import secrets
from datetime import datetime, timedelta
import time

import app.db as db


def seed(conn_path=None):
    if conn_path:
        db.DB_PATH = conn_path
    db.init_db()

    # create demo user
    username = 'demo'
    password = 'demo123'
    existing = db.get_user_by_username(username)
    if existing:
        user_id = existing['id']
    else:
        salt = secrets.token_hex(8)
        ph = secrets.token_hex(24)  # fake hash placeholder; login not required for demo
        user_id = db.create_user(username, salt, ph)

    # create a session token for the demo user
    token = secrets.token_urlsafe(24)
    db.create_session(token, user_id, lifetime_minutes=60*24)

    # set a per-user threshold for demo
    try:
        db.set_user_thresholds(user_id, 60.0, 70.0)
    except Exception:
        # fallback to global
        db.set_thresholds(60.0, 70.0)

    # insert metrics across the last hour
    now = datetime.utcnow()
    for i in range(30):
        ts = (now - timedelta(minutes=(30 - i))).isoformat()
        cpu = 30 + i * 1.5
        mem = 40 + i * 0.8
        with db._lock:
            conn = db.get_conn()
            cur = conn.cursor()
            cur.execute('INSERT INTO metrics (cpu, memory, ts) VALUES (?, ?, ?)', (cpu, mem, ts))
            conn.commit()
            conn.close()

    # add a few alerts
    db.add_alert('memory', 78.2)
    db.add_alert('cpu', 92.1)

    print('Seeded demo user:')
    print(f'  username: {username}')
    print(f'  token: {token}')
    print('\nUse this token in the dashboard (token header) to view demo data.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--db', help='path to sqlite DB file', default=None)
    args = p.parse_args()
    seed(args.db)
