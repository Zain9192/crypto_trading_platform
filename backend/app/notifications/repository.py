import psycopg
from psycopg.rows import dict_row


class NotificationRepository:
    def __init__(self, dsn):
        self.dsn = dsn

    def listing(self, user_id, before=None, limit=25, unread_only=False):
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            rows = connection.execute('''SELECT * FROM notifications WHERE user_id=%s
                AND (%s::bigint IS NULL OR notification_id<%s)
                AND (NOT %s OR read_at IS NULL)
                ORDER BY notification_id DESC LIMIT %s''',
                (user_id, before, before, unread_only, limit + 1)).fetchall()
            unread = connection.execute('''SELECT count(*) AS count FROM notifications
                WHERE user_id=%s AND read_at IS NULL''', (user_id,)).fetchone()['count']
            return {'items': rows[:limit], 'unread_count': unread,
                    'next_cursor': rows[limit - 1]['notification_id'] if len(rows) > limit else None}

    def mark_read(self, user_id, notification_id):
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            return connection.execute('''UPDATE notifications SET read_at=COALESCE(read_at,now())
                WHERE user_id=%s AND notification_id=%s RETURNING *''',
                (user_id, notification_id)).fetchone()

    def preferences(self, user_id, enabled=None):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            if enabled is not None:
                c.execute('''INSERT INTO notification_preferences(user_id,email_enabled) VALUES (%s,%s)
                    ON CONFLICT(user_id) DO UPDATE SET email_enabled=EXCLUDED.email_enabled''', (user_id,enabled))
                if not enabled:
                    c.execute('''DELETE FROM notification_email_outbox o USING notifications n
                        WHERE o.notification_id=n.notification_id AND n.user_id=%s AND o.sent_at IS NULL''', (user_id,))
            row = c.execute('SELECT email_enabled FROM notification_preferences WHERE user_id=%s', (user_id,)).fetchone()
            counts = c.execute('''SELECT count(*) FILTER (WHERE o.sent_at IS NULL AND o.attempts<5) AS pending,
                count(*) FILTER (WHERE o.sent_at IS NULL AND o.attempts>=5) AS failed
                FROM notification_email_outbox o JOIN notifications n USING(notification_id) WHERE n.user_id=%s''', (user_id,)).fetchone()
            return {'email_enabled': row['email_enabled'] if row else False, **counts}
