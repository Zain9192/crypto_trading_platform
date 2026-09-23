"""Disposable QA server: real authentication/ledger; deterministic public market data."""
import os
from datetime import datetime,timezone
from app.main import app
from app.market.dependencies import get_market_service
from app.market.schemas import MarketAsset

if os.environ.get('APP_ENV')!='test':
    raise RuntimeError('QA server requires APP_ENV=test')

class Market:
    def get_top_assets(self,*args,**kwargs):
        return [MarketAsset(id='bitcoin',symbol='BTC',name='Bitcoin',current_price=100,last_updated=datetime.now(timezone.utc))],False
    def get_asset(self,symbol):
        return self.get_top_assets()[0][0] if symbol.upper()=='BTC' else None
    def get_ohlcv(self,*args,**kwargs):
        return [],False
    def get_history(self,*args,**kwargs):
        return []
    def get_indicators(self,*args,**kwargs):
        return []

app.dependency_overrides[get_market_service]=lambda:Market()
