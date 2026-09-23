from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic

import ccxt
import psycopg

from app.core.config import get_settings
from app.db.mongo import get_mongo_client
from app.db.redis_store import get_redis_client


def check(name):
    start=monotonic()
    try:
        if name == 'postgres':
            with psycopg.connect(get_settings().postgres_dsn,connect_timeout=3) as c:
                c.execute('SELECT 1')
        elif name == 'mongo':
            get_mongo_client().admin.command('ping')
        elif name == 'redis':
            get_redis_client().ping()
        else:
            client=getattr(ccxt,name)({'timeout':4000,'maxRetriesOnFailure':0,'enableRateLimit':True})
            try:
                if not client.has.get('fetchTime'):
                    return {'name':name,'status':'unsupported','observed_at':datetime.now(timezone.utc)}
                client.fetch_time()
            finally:
                if getattr(client,'session',None):
                    client.session.close()
        state='reachable'
    except Exception:
        state='unavailable'
    return {'name':name,'status':state,'latency_ms':round((monotonic()-start)*1000),
            'observed_at':datetime.now(timezone.utc)}


def health():
    with ThreadPoolExecutor(max_workers=6) as pool:
        return {'items':list(pool.map(check,('postgres','mongo','redis','binance','coinbase','kraken'))),
                'scope':'Storage ping and public production exchange time endpoints; private accounts and order execution are not probed.'}
