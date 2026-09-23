import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from app.admin.repository import AdminRepository
from app.auth.repository import PostgresUserRepository
from app.market.schemas import MarketAsset
from app.notifications.alerts import PriceAlertInput, PriceAlerts
from app.notifications.repository import NotificationRepository
from app.notifications.reports import export_report
from app.notifications.email_worker import deliver_one
from app.core.config import Settings
from app.portfolio.risk import PortfolioError
from app.trading.repository import TradingRepository
from app.trading.sandbox import SandboxEngine

DSN=os.getenv('PREDICTION_TEST_DSN')
pytestmark=pytest.mark.skipif(not DSN,reason='Disposable PostgreSQL required')


@pytest.fixture
def db():
    schema='qa_'+uuid4().hex
    with psycopg.connect(DSN,autocommit=True) as c:
        c.execute(psycopg.sql.SQL('CREATE SCHEMA {}').format(psycopg.sql.Identifier(schema)))
    dsn=make_conninfo(DSN,options=f'-c search_path={schema}')
    with psycopg.connect(dsn) as c:
        for path in sorted((Path(__file__).resolve().parents[3]/'database/postgres').glob('*.sql')):
            c.execute(path.read_text())
        for role in ('admin','trader','trader'):
            c.execute('INSERT INTO users(username,email,password_hash,role,is_email_verified) VALUES (%s,%s,%s,%s,true)',(uuid4().hex,uuid4().hex+'@example.test','unused',role))
    yield dsn
    with psycopg.connect(DSN,autocommit=True) as c:
        c.execute(psycopg.sql.SQL('DROP SCHEMA {} CASCADE').format(psycopg.sql.Identifier(schema)))


def test_refresh_is_consumed_once_under_concurrency(db):
    identity=str(uuid4())
    with psycopg.connect(db,row_factory=dict_row) as c:
        PostgresUserRepository(c).save_refresh_token(identity,2,datetime.now(timezone.utc)+timedelta(minutes=5))
    def consume(_):
        with psycopg.connect(db,row_factory=dict_row) as c:
            return PostgresUserRepository(c).consume_refresh_token(identity,2)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume,range(8)))==1


def test_admin_guards_audit_and_sql_injection(db):
    repo=AdminRepository(db)
    with pytest.raises(PortfolioError):
        repo.update_user(1,1,'trader',False)
    with pytest.raises(PortfolioError):
        repo.update_user(2,3,'admin',True)
    repo.update_user(1,2,'admin',True)
    assert len(repo.audit()['items'])==1
    repo.update_user(1,2,'trader',False)
    assert len(repo.audit()['items'])==2
    repo.overview(); repo.models(); repo.operations()
    with psycopg.connect(db,row_factory=dict_row) as c:
        assert PostgresUserRepository(c).get_user_by_email("' OR 1=1 --") is None
        assert c.execute('SELECT count(*) AS n FROM users').fetchone()['n']==3


def test_price_alert_concurrency_ownership_and_email_opt_in(db):
    alerts=PriceAlerts(db)
    NotificationRepository(db).preferences(2,True)
    row=alerts.create(2,PriceAlertInput(asset_key='bitcoin',direction='above',threshold='10'))
    assert not alerts.delete(3,row['alert_id'])
    asset=MarketAsset(id='bitcoin',symbol='BTC',name='Bitcoin',current_price=11,last_updated=datetime.now(timezone.utc)+timedelta(seconds=1))
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _:alerts.evaluate([asset]),range(5)))
    inbox=NotificationRepository(db)
    assert len(inbox.listing(2)['items'])==1 and inbox.listing(3)['items']==[]
    identity=inbox.listing(2)['items'][0]['notification_id']
    assert inbox.mark_read(3,identity) is None
    inbox.mark_read(2,identity); inbox.mark_read(2,identity)
    assert inbox.listing(2)['unread_count']==0
    assert inbox.preferences(2)['pending']==1
    inbox.preferences(2,False)
    assert inbox.preferences(2)['pending']==0


def sandbox_rows(db):
    connection,bot,order=uuid4(),uuid4(),uuid4()
    config={'mode':'sandbox','connection_id':str(connection),'symbol':'BTC/USDT','enabled':True,'interval':'1d',
            'order_amount':'1','confidence_threshold':'0.7','max_open_trades':1,'stop_loss_pct':'5','take_profit_pct':'10'}
    with psycopg.connect(db) as c:
        c.execute("INSERT INTO exchange_connections(connection_id,user_id,exchange,label,sandbox,credentials_ciphertext) VALUES (%s,2,'binance','QA',true,'unused')",(connection,))
        c.execute("INSERT INTO trading_bots(bot_id,user_id,connection_id,symbol,config,state) VALUES (%s,2,%s,'BTC/USDT',%s,'running')",(bot,connection,Jsonb(config)))
        c.execute("INSERT INTO trading_decisions(bot_id,event_key,signal,reason) VALUES (%s,'buy1','buy','prediction')",(bot,))
        c.execute("INSERT INTO sandbox_orders(order_id,bot_id,connection_id,event_key,symbol,side,amount,limit_price) VALUES (%s,%s,%s,'buy1','BTC/USDT','buy',1,100)",(order,bot,connection))
    repo=TradingRepository(db)
    with psycopg.connect(db,row_factory=dict_row) as c:
        stored=c.execute('SELECT * FROM sandbox_orders WHERE order_id=%s',(order,)).fetchone()
    return repo,repo.get(2,bot),stored


def test_partial_fill_replay_is_idempotent_and_reports_are_owned(db):
    repo,row,order=sandbox_rows(db)
    engine=SandboxEngine(repo,Settings(),Mock())
    remote={'side':'buy','amount':D(1),'filled':D('.4'),'cost':D(40),'status':'CANCELED','exchange_order_id':'77'}
    fill={'trade_id':'7','quantity':D('.4'),'price':D(100),'cost':D(40),'fee':D('.01'),'fee_currency':'USDT','executed_at':datetime.now(timezone.utc)}
    engine.apply(row,order,remote,[fill]); engine.apply(row,order,remote,[fill])
    with psycopg.connect(db,row_factory=dict_row) as c:
        p=c.execute('SELECT * FROM sandbox_positions').fetchone()
        assert p['quantity']==D('.4') and p['cost_basis']==D('40.01')
        assert c.execute('SELECT count(*) AS n FROM sandbox_fills').fetchone()['n']==1
        assert c.execute('SELECT count(*) AS n FROM notifications').fetchone()['n']==1
    today=datetime.now(timezone.utc).date()
    assert export_report(db,2,today,today,'csv')['fill_count']==1
    assert export_report(db,3,today,today,'pdf')['fill_count']==0
    with pytest.raises(PortfolioError):
        engine.apply(row,order,{**remote,'filled':D('.3')},[fill])


def test_unresolved_order_is_reconciled_without_resubmission(db):
    repo,row,order=sandbox_rows(db)
    adapter=Mock()
    adapter.lookup.side_effect=TimeoutError('provider-sensitive')
    engine=SandboxEngine(repo,Settings(),Mock())
    engine.reconcile(row,order,adapter)
    with psycopg.connect(db,row_factory=dict_row) as c:
        saved=c.execute('SELECT * FROM sandbox_orders').fetchone()
        assert saved['status']=='unknown'
        assert 'provider-sensitive' not in saved['last_error']
    adapter.submit.assert_not_called()
    with pytest.raises(PortfolioError,match='reconcile'):
        AdminRepository(db).update_user(1,2,'trader',False)


def test_email_retry_is_bounded_and_credentials_never_recorded(db):
    NotificationRepository(db).preferences(2,True)
    with psycopg.connect(db) as c:
        c.execute("INSERT INTO notifications(user_id,event_key,kind,payload) VALUES (2,'email-test','bot_failure','{}')")
    settings=Settings(notification_email_provider='smtp',notification_email_from='qa@example.test',notification_smtp_host='invalid')
    from types import SimpleNamespace
    settings=SimpleNamespace(**settings.model_dump(),postgres_dsn=db)
    sender=Mock(); sender.send.side_effect=RuntimeError('secret-password')
    for _ in range(5):
        assert deliver_one(settings,sender)
        with psycopg.connect(db) as c:
            c.execute("UPDATE notification_email_outbox SET next_attempt_at=now()")
    assert not deliver_one(settings,sender)
    with psycopg.connect(db) as c:
        error=c.execute('SELECT last_error FROM notification_email_outbox').fetchone()[0]
        assert 'secret-password' not in error
