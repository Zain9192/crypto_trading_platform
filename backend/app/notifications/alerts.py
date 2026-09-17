from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


class PriceAlertInput(BaseModel):
    asset_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')
    direction: Literal['above', 'below']
    threshold: Decimal = Field(gt=0, max_digits=28, decimal_places=8, allow_inf_nan=False)


class PriceAlerts:
    def __init__(self, dsn):
        self.dsn = dsn

    def listing(self, user_id):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            return c.execute('SELECT * FROM price_alerts WHERE user_id=%s ORDER BY alert_id DESC LIMIT 200', (user_id,)).fetchall()

    def create(self, user_id, body):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            c.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE', (user_id,))
            count = c.execute('SELECT count(*) AS n FROM price_alerts WHERE user_id=%s', (user_id,)).fetchone()['n']
            if count >= 200:
                raise ValueError('Remove an existing alert before adding more (limit 200)')
            return c.execute('''INSERT INTO price_alerts(user_id,asset_key,direction,threshold)
                VALUES (%s,%s,%s,%s) RETURNING *''',
                (user_id, body.asset_key, body.direction, body.threshold)).fetchone()

    def delete(self, user_id, alert_id):
        with psycopg.connect(self.dsn) as c:
            return c.execute('DELETE FROM price_alerts WHERE user_id=%s AND alert_id=%s', (user_id, alert_id)).rowcount > 0

    def evaluate(self, assets):
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            for asset in assets:
                observed = asset.last_updated
                if observed is None or observed.tzinfo is None or not -30 <= (now - observed).total_seconds() <= 120:
                    continue
                price = Decimal(str(asset.current_price)) if asset.current_price is not None else Decimal(0)
                if not price.is_finite() or price <= 0:
                    continue
                # Claim and notify in one transaction; concurrent workers cannot fire twice.
                rows = c.execute('''UPDATE price_alerts SET triggered_at=now()
                    WHERE asset_key=%s AND triggered_at IS NULL AND created_at<=%s
                    AND ((direction='above' AND threshold<=%s) OR (direction='below' AND threshold>=%s))
                    RETURNING *''', (asset.id, observed, price, price)).fetchall()
                for row in rows:
                    c.execute('''INSERT INTO notifications(user_id,event_key,kind,payload)
                        VALUES (%s,%s,'price_alert',%s) ON CONFLICT(user_id,event_key) DO NOTHING''',
                        (row['user_id'], f"price-alert:{row['alert_id']}", Jsonb({
                            'asset_key': asset.id, 'symbol': asset.symbol, 'price': str(price),
                            'threshold': str(row['threshold']), 'direction': row['direction'],
                            'quote_currency': 'USD', 'observed_at': observed.isoformat()})))
