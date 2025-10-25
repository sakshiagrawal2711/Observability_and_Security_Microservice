import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_invalid_threshold_payload(tmp_path):
    import app.db as dbmod
    dbmod.DB_PATH = str(tmp_path / 'e1.db')
    dbmod.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        r = await ac.post('/register', json={'username': 'x1', 'password': 'p1'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'x1', 'password': 'p1'})
        token = r.json()['token']
        headers = {'token': token}

        # invalid payload
        r = await ac.post('/thresholds', headers=headers, json={'cpu_threshold': 'not-a-number', 'memory_threshold': 'n'})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_metrics_history_bad_range(tmp_path):
    import app.db as dbmod
    dbmod.DB_PATH = str(tmp_path / 'e2.db')
    dbmod.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        r = await ac.post('/register', json={'username': 'x2', 'password': 'p2'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'x2', 'password': 'p2'})
        token = r.json()['token']
        headers = {'token': token}

        # bad ISO range should produce 400
        r = await ac.get('/metrics/history?start=bad&end=also-bad', headers=headers)
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_unauthorized_access():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        r = await ac.get('/summary?n=1')
        assert r.status_code == 401
