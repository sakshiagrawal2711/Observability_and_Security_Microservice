import os
import smtplib
import asyncio
import json
import random
from email.message import EmailMessage
from datetime import datetime
import httpx


async def _send_webhook(url: str, payload: dict, retries: int = 3, backoff: float = 1.0):
    """Send webhook POST with retries and exponential backoff."""
    attempt = 0
    last_exc = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        while attempt <= retries:
            try:
                resp = await client.post(url, json=payload)
                if 200 <= resp.status_code < 300:
                    return True
                else:
                    last_exc = Exception(f"webhook status {resp.status_code}")
            except Exception as e:
                last_exc = e
            # backoff with jitter
            attempt += 1
            if attempt > retries:
                break
            sleep_for = backoff * (2 ** (attempt - 1))
            sleep_for = sleep_for + random.uniform(0, 0.5)
            await asyncio.sleep(sleep_for)
    # final failure
    print(f"Webhook delivery failed after {retries} retries: {last_exc}")
    return False


def _send_email_sync(host: str, port: int, user: str, pwd: str, from_addr: str, to_addr: str, subject: str, body: str):
    try:
        email = EmailMessage()
        email['Subject'] = subject
        email['From'] = from_addr
        email['To'] = to_addr
        email.set_content(body)

        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(email)
        return True
    except Exception as e:
        print(f"Notifier email error: {e}")
        return False


async def notify_alert(alert_type: str, value: float, ts: str):
    """Async notifier. This is non-blocking when scheduled via create_task.

    Behavior:
      - Always logs to console (best-effort)
      - If ALERT_WEBHOOK_URL set, POSTs JSON payload with retries
      - If SMTP env vars are set, sends email in a thread (best-effort)

    Environment variables used (optional):
      ALERT_SMTP_HOST, ALERT_SMTP_PORT, ALERT_SMTP_USER, ALERT_SMTP_PASS, ALERT_TO, ALERT_FROM
      ALERT_WEBHOOK_URL, ALERT_WEBHOOK_RETRIES, ALERT_WEBHOOK_BACKOFF
    """
    payload = {
        'type': alert_type,
        'value': value,
        'ts': ts,
        'generated_at': datetime.utcnow().isoformat()
    }

    # console log
    try:
        print(f"[ALERT] {alert_type.upper()} value={value} at {ts}")
    except Exception:
        pass

    tasks = []

    # webhook
    webhook = os.environ.get('ALERT_WEBHOOK_URL')
    if webhook:
        try:
            retries = int(os.environ.get('ALERT_WEBHOOK_RETRIES', '3'))
        except Exception:
            retries = 3
        try:
            backoff = float(os.environ.get('ALERT_WEBHOOK_BACKOFF', '1.0'))
        except Exception:
            backoff = 1.0
        tasks.append(_send_webhook(webhook, payload, retries=retries, backoff=backoff))

    # SMTP (run blocking send in thread)
    host = os.environ.get('ALERT_SMTP_HOST')
    to_addr = os.environ.get('ALERT_TO')
    from_addr = os.environ.get('ALERT_FROM')
    if host and to_addr and from_addr:
        try:
            port = int(os.environ.get('ALERT_SMTP_PORT', 587))
        except Exception:
            port = 587
        user = os.environ.get('ALERT_SMTP_USER')
        pwd = os.environ.get('ALERT_SMTP_PASS')
        subject = f"System Alert: {alert_type.upper()}"
        body = f"Alert type: {alert_type}\nValue: {value}\nTime: {ts}\nGenerated: {datetime.utcnow().isoformat()}"
        tasks.append(asyncio.to_thread(_send_email_sync, host, port, user, pwd, from_addr, to_addr, subject, body))

    if tasks:
        # run tasks concurrently but don't raise on failure
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # log any exceptions
        for r in results:
            if isinstance(r, Exception):
                print(f"Notifier task error: {r}")
    return True

