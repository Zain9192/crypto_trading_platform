import logging
import signal
import smtplib
import ssl
import threading
from email.message import EmailMessage

import httpx
import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings

log = logging.getLogger(__name__)


def configured(settings):
    if not settings.notification_email_from:
        return False
    if settings.notification_email_provider == 'smtp':
        return bool(settings.notification_smtp_host)
    return settings.notification_email_provider == 'sendgrid' and bool(settings.notification_sendgrid_key.get_secret_value())


def content(row):
    p = row['payload']
    title = row['kind'].replace('_', ' ').title()
    fields = ('mode', 'symbol', 'direction', 'threshold', 'quantity', 'price', 'quote_currency', 'fee', 'fee_currency', 'message')
    body = '\n'.join(f"{key.replace('_', ' ').title()}: {p[key]}" for key in fields if key in p)
    return f'Crypto Trading Platform: {title}', body + '\n\nReview details in your account notification inbox.'


class EmailSender:
    def __init__(self, settings):
        self.settings = settings

    def send(self, row):
        s = self.settings
        if not s.notification_email_from:
            raise ValueError('Email sender is not configured')
        subject, body = content(row)
        if s.notification_email_provider == 'sendgrid':
            if not s.notification_sendgrid_key.get_secret_value():
                raise ValueError('SendGrid is not configured')
            with httpx.Client(timeout=20) as client:
                response = client.post('https://api.sendgrid.com/v3/mail/send',
                    headers={'Authorization': f'Bearer {s.notification_sendgrid_key.get_secret_value()}'},
                    json={'personalizations': [{'to': [{'email': row['email']}]}],
                          'from': {'email': s.notification_email_from}, 'subject': subject,
                          'content': [{'type': 'text/plain', 'value': body}]})
                response.raise_for_status()
        elif s.notification_email_provider == 'smtp':
            if not s.notification_smtp_host:
                raise ValueError('SMTP is not configured')
            message = EmailMessage()
            message['From'], message['To'], message['Subject'] = s.notification_email_from, row['email'], subject
            message['Message-ID'] = f"<notification-{row['notification_id']}@crypto-platform.invalid>"
            message.set_content(body)
            with smtplib.SMTP(s.notification_smtp_host, s.notification_smtp_port, timeout=20) as client:
                client.starttls(context=ssl.create_default_context())
                if s.notification_smtp_username:
                    client.login(s.notification_smtp_username, s.notification_smtp_password.get_secret_value())
                client.send_message(message)
        else:
            raise ValueError('Email delivery is disabled')


def deliver_one(settings, sender):
    if not configured(settings):
        return False
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as c:
        # Row lock spans delivery; other workers skip it. Delivery is at-least-once
        # if the provider accepts a message but acknowledgement is lost.
        row = c.execute('''SELECT o.notification_id,n.kind,n.payload,u.email,
                u.is_active,u.is_email_verified,p.email_enabled,o.attempts
            FROM notification_email_outbox o JOIN notifications n USING(notification_id)
            JOIN users u ON u.user_id=n.user_id
            LEFT JOIN notification_preferences p ON p.user_id=n.user_id
            WHERE o.sent_at IS NULL AND o.attempts<5 AND o.next_attempt_at<=now()
            ORDER BY o.next_attempt_at LIMIT 1 FOR UPDATE OF o SKIP LOCKED''').fetchone()
        if row is None:
            return False
        if not (row['is_active'] and row['is_email_verified'] and row['email_enabled']):
            c.execute('DELETE FROM notification_email_outbox WHERE notification_id=%s', (row['notification_id'],))
            return True
        try:
            sender.send(row)
        except Exception:
            c.execute('''UPDATE notification_email_outbox SET attempts=attempts+1,
                last_error='Delivery failed; check provider configuration or availability',
                next_attempt_at=now()+(%s * interval '1 second') WHERE notification_id=%s''',
                (min(60 * 2 ** row['attempts'], 3600), row['notification_id']))
            log.warning('Notification email delivery failed (notification %s)', row['notification_id'])
        else:
            c.execute('UPDATE notification_email_outbox SET sent_at=now(),last_error=NULL,attempts=attempts+1 WHERE notification_id=%s', (row['notification_id'],))
        return True


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    settings = get_settings()
    sender = EmailSender(settings)
    while not stop.is_set():
        try:
            worked = deliver_one(settings, sender)
        except psycopg.Error:
            log.warning('Notification email storage unavailable')
            worked = False
        stop.wait(0.2 if worked else 10)


if __name__ == '__main__':
    main()
