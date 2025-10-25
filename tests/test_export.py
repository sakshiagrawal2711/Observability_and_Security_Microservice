import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_metrics_export_csv(tmp_path):
    import app.db as dbmod
    dbmod.DB_PATH = str(tmp_path / 'export.db')
    dbmod.init_db()

    # add some metrics
    dbmod.add_metric(12.5, 33.3)
    dbmod.add_metric(22.0, 44.1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        # register/login
        r = await ac.post('/register', json={'username': 'ex', 'password': 'p'})
        assert r.status_code == 200
        r = await ac.post('/login', json={'username': 'ex', 'password': 'p'})
        assert r.status_code == 200
        token = r.json()['token']
        headers = {'token': token}

        # export recent metrics as CSV
        r = await ac.get('/metrics/export', headers=headers)
        assert r.status_code == 200
        assert r.headers.get('content-type', '').startswith('text/csv')
        text = r.text
        assert 'timestamp' in text.lower() or 'cpu' in text.lower()
