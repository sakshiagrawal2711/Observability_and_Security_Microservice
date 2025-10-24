import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_thresholds_and_metrics(tmp_path):
    import app.db as dbmod
    dbmod.DB_PATH = str(tmp_path / 't2.db')
    dbmod.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        # register/login
        r = await ac.post('/register', json={'username': 'u2', 'password': 'p2'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'u2', 'password': 'p2'})
        token = r.json()['token']
        headers = {'token': token}

        # get thresholds
        r = await ac.get('/thresholds', headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert 'cpu_threshold' in data

        # set thresholds
        r = await ac.post('/thresholds', headers=headers, json={'cpu_threshold': 50, 'memory_threshold': 50})
        assert r.status_code == 200

        # add a metric that will trigger alerts directly through DB
        dbmod.add_metric(60.0, 60.0)
        dbmod.add_alert('cpu', 60.0)
        dbmod.add_alert('memory', 60.0)

        r = await ac.get('/alerts?limit=5', headers=headers)
        assert r.status_code == 200
        arr = r.json()
        assert len(arr) >= 2

        r = await ac.get('/metrics?limit=5', headers=headers)
        assert r.status_code == 200
        m = r.json()
        assert len(m) >= 1
