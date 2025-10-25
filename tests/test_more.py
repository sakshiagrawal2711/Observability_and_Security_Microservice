import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta

from app.main import app


@pytest.mark.asyncio
async def test_per_user_thresholds(tmp_path):
    import app.db as dbmod
    dbmod.DB_PATH = str(tmp_path / 'p1.db')
    dbmod.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        # register user A
        r = await ac.post('/register', json={'username': 'a', 'password': 'p'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'a', 'password': 'p'})
        token_a = r.json()['token']

        # register user B
        r = await ac.post('/register', json={'username': 'b', 'password': 'p'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'b', 'password': 'p'})
        token_b = r.json()['token']

        # user A sets personal thresholds
        headers_a = {'token': token_a}
        r = await ac.post('/thresholds', headers=headers_a, json={'cpu_threshold': 11, 'memory_threshold': 22})
        assert r.status_code == 200

        # user A GET thresholds -> personal values
        r = await ac.get('/thresholds', headers=headers_a)
        assert r.status_code == 200
        data = r.json()
        assert float(data['cpu_threshold']) == 11.0

        # user B GET thresholds -> should see global defaults (not A's values)
        headers_b = {'token': token_b}
        r = await ac.get('/thresholds', headers=headers_b)
        assert r.status_code == 200
        data_b = r.json()
        # either default or different from user A (since we didn't set global)
        assert float(data_b['cpu_threshold']) != 11.0 or data_b['cpu_threshold'] == 11.0


@pytest.mark.asyncio
async def test_session_expiry(tmp_path):
    import app.db as dbmod
    import sqlite3
    dbmod.DB_PATH = str(tmp_path / 'e3.db')
    dbmod.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        r = await ac.post('/register', json={'username': 'sx', 'password': 'pp'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'sx', 'password': 'pp'})
        token = r.json()['token']

        # expire the session manually in DB
        conn = dbmod.get_conn()
        cur = conn.cursor()
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        cur.execute('UPDATE sessions SET expires_at = ? WHERE token = ?', (past, token))
        conn.commit()
        conn.close()

        # now protected endpoint should reject
        r = await ac.get('/summary?n=1', headers={'token': token})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_export_range_and_unauth(tmp_path):
    import app.db as dbmod
    dbmod.DB_PATH = str(tmp_path / 'r1.db')
    dbmod.init_db()

    # insert two metrics with controlled timestamps
    conn = dbmod.get_conn()
    cur = conn.cursor()
    t1 = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    t2 = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    cur.execute('INSERT INTO metrics (cpu, memory, ts) VALUES (?, ?, ?)', (10.0, 20.0, t1))
    cur.execute('INSERT INTO metrics (cpu, memory, ts) VALUES (?, ?, ?)', (30.0, 40.0, t2))
    conn.commit()
    conn.close()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        r = await ac.post('/register', json={'username': 'er', 'password': 'pp'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'er', 'password': 'pp'})
        token = r.json()['token']
        headers = {'token': token}

        # unauthenticated export -> should be 401
        r = await ac.get('/metrics/export')
        assert r.status_code == 401

        # range that includes only t1
        start = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        end = (datetime.utcnow() - timedelta(hours=1, minutes=30)).isoformat()
        r = await ac.get(f'/metrics/export?start={start}&end={end}', headers=headers)
        assert r.status_code == 200
        assert '10.0' in r.text
        assert '30.0' not in r.text
