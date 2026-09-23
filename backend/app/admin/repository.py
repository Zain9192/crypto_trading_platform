import psycopg
from psycopg.rows import dict_row


class AdminRepository:
    def __init__(self, dsn):
        self.dsn = dsn

    def users(self, before=None, limit=25):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            rows = c.execute('''SELECT user_id,username,email,role,is_active,is_email_verified,
                    totp_enabled,created_at
                FROM users WHERE (%s::bigint IS NULL OR user_id<%s)
                ORDER BY user_id DESC LIMIT %s''', (before,before,limit+1)).fetchall()
            return {'items':rows[:limit],
                    'next_cursor':rows[limit-1]['user_id'] if len(rows)>limit else None}

    def overview(self):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            row = c.execute('''SELECT now() AS observed_at,
                (SELECT count(*) FROM users) AS users_total,
                (SELECT count(*) FROM users WHERE is_active) AS users_active,
                (SELECT count(*) FROM trading_bots WHERE state='running') AS bots_running,
                (SELECT count(*) FROM trading_bots WHERE state='error') AS bots_error,
                (SELECT max(seen_at) FROM trading_worker_heartbeat) AS trading_worker_seen_at,
                (SELECT count(*) FROM sandbox_orders WHERE status IN
                    ('submitting','unknown','open','partially_filled')) AS sandbox_orders_unresolved,
                (SELECT count(*) FROM notification_email_outbox WHERE sent_at IS NULL AND attempts<5) AS email_pending,
                (SELECT count(*) FROM notification_email_outbox WHERE sent_at IS NULL AND attempts>=5) AS email_failed
                ''').fetchone()
            seen = row['trading_worker_seen_at']
            row['trading_worker_status'] = ('unknown' if seen is None else
                'healthy' if 0 <= (row['observed_at']-seen).total_seconds() <= 90 else 'stale')
            row['postgres_status'] = 'reachable'
            return row

    def models(self, before=None, limit=25):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            rows = c.execute('''SELECT m.model_id,m.algorithm,m.model_version,m.symbol,m.timeframe,
                    m.is_active,m.trained_at,m.metadata->'metrics' AS metrics,
                    m.metadata->'backtest' AS backtest,
                    (SELECT max(p.created_at) FROM predictions p WHERE p.model_id=m.model_id) AS last_prediction_at
                FROM ml_models m WHERE (%s::bigint IS NULL OR m.model_id<%s)
                ORDER BY m.model_id DESC LIMIT %s''',(before,before,limit+1)).fetchall()
            return {'items':rows[:limit],
                    'next_cursor':rows[limit-1]['model_id'] if len(rows)>limit else None}

    def operations(self):
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            bots = c.execute('''SELECT bot_id,symbol,state,failures,last_result,last_tick_at
                FROM trading_bots WHERE state='error' OR failures>0
                ORDER BY updated_at DESC,bot_id LIMIT 50''').fetchall()
            exchanges = c.execute('''SELECT e.exchange,e.sandbox,count(*) AS connections,
                (SELECT max(n.created_at) FROM notifications n WHERE n.kind='exchange_failure'
                 AND n.created_at>=now()-interval '24 hours' AND
                 ((n.payload->>'connection_id') IN
                    (SELECT connection_id::text FROM exchange_connections WHERE exchange=e.exchange AND sandbox=e.sandbox)
                  OR (n.payload->>'bot_id') IN
                    (SELECT b.bot_id::text FROM trading_bots b JOIN exchange_connections ec USING(connection_id)
                     WHERE ec.exchange=e.exchange AND ec.sandbox=e.sandbox))) AS last_failure_at
                FROM exchange_connections e GROUP BY e.exchange,e.sandbox ORDER BY e.exchange,e.sandbox''').fetchall()
            for exchange in exchanges:
                exchange['status'] = 'recent_failure' if exchange['last_failure_at'] else 'unknown'
            return {'bots':bots,'exchanges':exchanges,'limit':50,
                    'observed_at':c.execute('SELECT now() AS observed_at').fetchone()['observed_at']}

    def update_user(self, actor_id, target_id, role, active):
        from psycopg.types.json import Jsonb
        from app.portfolio.risk import PortfolioError
        with psycopg.connect(self.dsn, row_factory=dict_row) as c:
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended('admin-user-management',0))")
            actor = c.execute('SELECT role,is_active FROM users WHERE user_id=%s FOR UPDATE',(actor_id,)).fetchone()
            if not actor or not actor['is_active'] or actor['role'] != 'admin':
                raise PortfolioError('Administrator access required',403)
            target = c.execute('SELECT role,is_active FROM users WHERE user_id=%s FOR UPDATE',(target_id,)).fetchone()
            if target is None:
                raise PortfolioError('User not found',404)
            if actor_id == target_id and (role != 'admin' or not active):
                raise PortfolioError('You cannot demote or deactivate your own account',409)
            if not active:
                if c.execute("""SELECT 1 FROM trading_bots b WHERE user_id=%s AND
                    (state IN ('running','stopping') OR close_requested OR EXISTS
                    (SELECT 1 FROM sandbox_orders o WHERE o.bot_id=b.bot_id AND
                    status IN ('submitting','unknown','open','partially_filled'))) LIMIT 1""",(target_id,)).fetchone():
                    raise PortfolioError('Stop this user’s bots and reconcile pending orders before deactivation',409)
            c.execute('UPDATE users SET role=%s,is_active=%s,updated_at=now() WHERE user_id=%s',(role,active,target_id))
            if not active or role != target['role']:
                c.execute('UPDATE refresh_tokens SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL',(target_id,))
            if target != {'role':role,'is_active':active}:
                c.execute('INSERT INTO admin_audit(actor_id,target_id,action,details) VALUES (%s,%s,%s,%s)',
                    (actor_id,target_id,'update_user',Jsonb({'before':target,'after':{'role':role,'is_active':active}})))
            return {'user_id':target_id,'role':role,'is_active':active}

    def audit(self, before=None, limit=25):
        with psycopg.connect(self.dsn,row_factory=dict_row) as c:
            rows=c.execute('''SELECT * FROM admin_audit WHERE (%s::bigint IS NULL OR audit_id<%s)
                ORDER BY audit_id DESC LIMIT %s''',(before,before,limit+1)).fetchall()
            return {'items':rows[:limit],'next_cursor':rows[limit-1]['audit_id'] if len(rows)>limit else None}
