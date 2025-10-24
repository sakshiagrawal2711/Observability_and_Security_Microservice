import pytest
from httpx import AsyncClient, ASGITransport
import asyncio
import os

from app.main import app


@pytest.mark.asyncio
async def test_register_login_and_summary(tmp_path, monkeypatch):
    # ensure a fresh DB file location
    dbfile = tmp_path / 'test.db'
    # monkeypatch DB path used by app.db
    import app.db as dbmod
    dbmod.DB_PATH = str(dbfile)
    dbmod.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        # register
        r = await ac.post('/register', json={'username': 'u1', 'password': 'p1'})
        assert r.status_code == 200
        # login
        r = await ac.post('/login', json={'username': 'u1', 'password': 'p1'})
        assert r.status_code == 200
        token = r.json().get('token')
        assert token

        # call summary (no alerts yet)
        headers = {'token': token}
        r = await ac.get('/summary?n=3', headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert 'total_alerts' in data
