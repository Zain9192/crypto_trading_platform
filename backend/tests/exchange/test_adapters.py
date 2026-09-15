from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4
import ccxt
import pytest
from app.exchange.adapters import BinanceAdapter, CoinbaseAdapter, KrakenAdapter, ExchangeFailure
from app.exchange.contracts import ConnectionPolicy, Credentials, ExchangeError, OrderRequest
from app.portfolio.risk import validate_order
from app.portfolio.schemas import PaperOrderCreate, RiskSettings


def credentials():
    return Credentials(api_key=uuid4().hex, api_secret=uuid4().hex)


def client():
    c = Mock()
    c.market.return_value = {'spot': True, 'active': True, 'limits': {'amount': {'min': '0.001'}}}
    c.fetch_balance.return_value = {'free': {'BTC': '1.2'}, 'used': {'BTC': '0.3'}, 'total': {'BTC': '1.5'}}
    c.fetch_ticker.return_value = {'last': '100.123456789', 'timestamp': 1700000000000}
    c.fetch_order.return_value = {'id': 'o1', 'symbol': 'BTC/USDT', 'side': 'buy', 'status': 'closed', 'amount': '1', 'filled': '1', 'price': '100'}
    c.create_order.return_value = c.fetch_order.return_value
    c.amount_to_precision.side_effect = lambda symbol, value: value
    c.price_to_precision.side_effect = lambda symbol, value: value
    c.fetch_my_trades.return_value = [{'id': 't1', 'order': 'o1', 'symbol': 'BTC/USDT', 'side': 'buy', 'amount': '1', 'price': '100', 'timestamp': 1700000000000}]
    return c


@pytest.mark.parametrize('klass', [BinanceAdapter, CoinbaseAdapter, KrakenAdapter])
def test_read_operations(klass):
    c = client()
    adapter = klass(credentials(), ConnectionPolicy(sandbox=False), client_factory=lambda config: c)
    adapter.connect()
    assert adapter.get_balance()[0].free == Decimal('1.2')
    assert adapter.get_price('BTC/USDT').price == Decimal('100.123456789')
    assert adapter.get_order('o1', 'BTC/USDT').filled == 1
    since = datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert adapter.get_trades('BTC/USDT', since, 25)[0].trade_id == 't1'
    c.fetch_my_trades.assert_called_with('BTC/USDT', int(since.timestamp()*1000), 25)
    c.set_sandbox_mode.assert_not_called()
    adapter.close()
    c.session.close.assert_called_once()


def test_binance_sandbox_first():
    c = client()
    BinanceAdapter(credentials(), ConnectionPolicy(), client_factory=lambda config: c).connect()
    assert c.mock_calls[0][0] == 'set_sandbox_mode'
    assert c.mock_calls[0].args == (True,)


@pytest.mark.parametrize('klass', [CoinbaseAdapter, KrakenAdapter])
def test_unsupported_sandbox_cannot_fall_back(klass):
    factory = Mock()
    with pytest.raises(ExchangeFailure, match='sandbox'):
        klass(credentials(), ConnectionPolicy(), client_factory=factory)
    factory.assert_not_called()


def order():
    return OrderRequest(client_order_id=uuid4(), symbol='BTC/USDT', side='buy', order_type='limit', amount='1', price='100')


@pytest.mark.parametrize('klass', [BinanceAdapter, CoinbaseAdapter, KrakenAdapter])
def test_production_mutation_disabled(klass):
    c = client()
    adapter = klass(credentials(), ConnectionPolicy(sandbox=False), client_factory=lambda config: c)
    with pytest.raises(ExchangeError, match='read-only'):
        adapter.place_order(order())
    with pytest.raises(ExchangeError, match='read-only'):
        adapter.cancel_order('o1', 'BTC/USDT')
    c.create_order.assert_not_called()
    c.cancel_order.assert_not_called()


def test_risk_required_and_client_id_preserved():
    c = client()
    adapter = BinanceAdapter(credentials(), ConnectionPolicy(read_only=False), client_factory=lambda config: c)
    with pytest.raises(ExchangeFailure, match='risk validator'):
        adapter.place_order(order())
    c.create_order.assert_not_called()
    adapter.risk_check = Mock()
    request = order()
    assert adapter.place_order(request).order_id == 'o1'
    adapter.risk_check.assert_called_once_with(request)
    assert c.create_order.call_args.args[-1] == {'clientOrderId': str(request.client_order_id)}
    assert c.create_order.call_args.args[3:5] == ('1', '100')
    adapter.cancel_order('o1', 'BTC/USDT')
    c.cancel_order.assert_called_once_with('o1', 'BTC/USDT')


def test_phase5_risk_prevents_submission():
    c = client()
    def risk(req):
        validate_order({'cash_balance': Decimal('10')}, [], [], PaperOrderCreate(client_order_id=req.client_order_id,
            symbol='BTC', side=req.side, quantity=req.amount, simulation_price=req.price), RiskSettings())
    adapter = BinanceAdapter(credentials(), ConnectionPolicy(read_only=False), client_factory=lambda config: c, risk_check=risk)
    with pytest.raises(ExchangeFailure, match='Insufficient available cash'):
        adapter.place_order(order())
    c.create_order.assert_not_called()


def test_precision_and_ambiguous_timeout_do_not_retry():
    c = client()
    adapter = BinanceAdapter(credentials(), ConnectionPolicy(read_only=False), client_factory=lambda config: c, risk_check=Mock())
    c.amount_to_precision.side_effect = lambda *args: '0.9'
    with pytest.raises(ExchangeFailure, match='precision'):
        adapter.place_order(order())
    c.create_order.assert_not_called()
    c.amount_to_precision.side_effect = lambda symbol, value: value
    c.create_order.side_effect = ccxt.RequestTimeout('sensitive upstream payload')
    with pytest.raises(ExchangeFailure, match='timed out'):
        adapter.place_order(order())
    assert c.create_order.call_count == 1


@pytest.mark.parametrize('error,status', [(ccxt.AuthenticationError,422), (ccxt.PermissionDenied,403), (ccxt.RateLimitExceeded,429), (ccxt.NetworkError,503), (ccxt.OrderNotFound,404), (ccxt.ExchangeError,502)])
def test_safe_provider_errors(error, status):
    c = client()
    c.fetch_balance.side_effect = error('secret upstream details')
    adapter = KrakenAdapter(credentials(), ConnectionPolicy(sandbox=False), client_factory=lambda config: c)
    with pytest.raises(ExchangeFailure) as caught:
        adapter.get_balance()
    assert caught.value.status_code == status
    assert 'secret' not in str(caught.value)


def test_missing_values_and_derivatives_rejected():
    c = client()
    adapter = BinanceAdapter(credentials(), ConnectionPolicy(), client_factory=lambda config: c)
    c.fetch_balance.return_value = {'free': {'BTC': None}, 'total': {'BTC': '1'}}
    with pytest.raises(ExchangeFailure, match='invalid data'):
        adapter.get_balance()
    c.market.return_value = {'spot': False, 'active': True}
    with pytest.raises(ExchangeFailure, match='spot'):
        adapter.get_price('BTC/USDT')


def test_pinned_real_ccxt_constructors_without_network():
    for klass in (BinanceAdapter, CoinbaseAdapter, KrakenAdapter):
        adapter = klass(credentials(), ConnectionPolicy(sandbox=False))
        assert adapter._client.id == adapter.exchange.value
        assert adapter._client.enableRateLimit
        adapter.close()
    adapter = BinanceAdapter(credentials(), ConnectionPolicy())
    assert 'testnet' in str(adapter._client.urls['api'])
    adapter.close()
