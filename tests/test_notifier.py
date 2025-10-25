import os
import asyncio
import pytest

from app import notifier


@pytest.mark.asyncio
async def test_webhook_success(monkeypatch):
    # configure webhook
    os.environ['ALERT_WEBHOOK_URL'] = 'http://example/webhook'

    calls = {'count': 0}

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            calls['count'] += 1
            return FakeResponse(200)

    monkeypatch.setattr('httpx.AsyncClient', FakeAsyncClient)

    res = await notifier.notify_alert('cpu', 90.0, '2025-10-25T00:00:00Z')
    assert res is True
    assert calls['count'] == 1


@pytest.mark.asyncio
async def test_webhook_retries(monkeypatch):
    # set small retry count
    os.environ['ALERT_WEBHOOK_URL'] = 'http://example/webhook'
    os.environ['ALERT_WEBHOOK_RETRIES'] = '2'
    os.environ['ALERT_WEBHOOK_BACKOFF'] = '0.01'

    attempts = []

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            attempts.append(1)
            # always non-2xx to trigger retries
            return FakeResponse(500)

    monkeypatch.setattr('httpx.AsyncClient', FakeAsyncClient)

    res = await notifier.notify_alert('memory', 88.8, '2025-10-25T00:00:00Z')
    assert res is True
    # retries=2 -> attempts should be 3 (initial + 2 retries)
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_smtp_send(monkeypatch):
    # configure SMTP envs
    os.environ.pop('ALERT_WEBHOOK_URL', None)
    os.environ['ALERT_SMTP_HOST'] = 'smtp.example'
    os.environ['ALERT_SMTP_PORT'] = '587'
    os.environ['ALERT_SMTP_USER'] = 'user'
    os.environ['ALERT_SMTP_PASS'] = 'pass'
    os.environ['ALERT_FROM'] = 'from@example.com'
    os.environ['ALERT_TO'] = 'to@example.com'

    sent = {'called': False}

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            pass

        def starttls(self):
            pass

        def login(self, user, pwd):
            pass

        def send_message(self, email):
            sent['called'] = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('smtplib.SMTP', FakeSMTP)

    res = await notifier.notify_alert('cpu', 95.5, '2025-10-25T00:00:00Z')
    assert res is True
    assert sent['called'] is True
