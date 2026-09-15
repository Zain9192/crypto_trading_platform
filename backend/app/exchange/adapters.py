"""CCXT spot adapters; production mutation is always disabled."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps

import ccxt
from pydantic import ValidationError

from app.exchange.contracts import Balance, ConnectionPolicy, ExchangeError, ExchangeName, Order, PriceQuote, Trade
from app.portfolio.risk import PortfolioError


class ExchangeFailure(ExchangeError):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def safe_operation(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except PortfolioError as exc:
            raise ExchangeFailure(str(exc), exc.status_code) from None
        except ccxt.PermissionDenied:
            raise ExchangeFailure('Exchange key lacks required read permission', 403) from None
        except ccxt.AuthenticationError:
            raise ExchangeFailure('Exchange credentials were rejected', 422) from None
        except ccxt.OrderNotFound:
            raise ExchangeFailure('Exchange order not found', 404) from None
        except ccxt.RateLimitExceeded:
            raise ExchangeFailure('Exchange rate limit reached; retry later', 429) from None
        except ccxt.NetworkError:
            raise ExchangeFailure('Exchange unavailable or request timed out', 503) from None
        except (ccxt.BadSymbol, ccxt.InvalidOrder, ccxt.NotSupported):
            raise ExchangeFailure('Exchange does not support this symbol or operation', 422) from None
        except ccxt.BaseError:
            raise ExchangeFailure('Exchange request failed') from None
        except (ValidationError, ValueError, TypeError, KeyError, AttributeError, InvalidOperation):
            raise ExchangeFailure('Exchange returned incomplete or invalid data') from None
    return wrapped


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('Missing number')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Invalid number')
    return result


def timestamp(value):
    if value is None:
        raise ValueError('Missing time')
    return datetime.fromtimestamp(float(value) / 1000, timezone.utc)


class CCXTSpotAdapter:
    sandbox_supported = False

    def __init__(self, credentials, policy: ConnectionPolicy, *, client_factory=None, risk_check=None):
        self.policy, self.risk_check = policy, risk_check
        if policy.sandbox and not self.sandbox_supported:
            raise ExchangeFailure('Spot sandbox is unsupported by this adapter; choose production read-only', 422)
        if not policy.sandbox and not policy.read_only:
            raise ExchangeFailure('Live exchange mutations are disabled', 422)
        options = {'defaultType': 'spot'}
        if self.exchange == ExchangeName.BINANCE:
            options.update({'fetchMarkets': {'types': ['spot']}, 'fetchCurrencies': False})
        config = {'apiKey': credentials.api_key.get_secret_value(), 'secret': credentials.api_secret.get_secret_value(),
                  'enableRateLimit': True, 'timeout': 15000, 'verbose': False, 'maxRetriesOnFailure': 0, 'options': options}
        if credentials.passphrase:
            config['password'] = credentials.passphrase.get_secret_value()
        self._client = (client_factory or getattr(ccxt, self.exchange.value))(config)
        if policy.sandbox:
            self._client.set_sandbox_mode(True)  # Must precede every network-capable call.

    def close(self):
        session = getattr(self._client, 'session', None)
        if session is not None:
            session.close()

    @safe_operation
    def connect(self):
        self._client.check_required_credentials()
        self._client.load_markets()
        self.get_balance()

    def _market(self, symbol):
        if '/' not in symbol or ':' in symbol:
            raise ExchangeFailure('Only unified spot symbols are supported', 422)
        self._client.load_markets()
        market = self._client.market(symbol)
        if market.get('spot') is not True or market.get('active') is False:
            raise ExchangeFailure('Only active spot markets are supported', 422)
        return market

    @safe_operation
    def get_balance(self):
        raw = self._client.fetch_balance({'type': 'spot'})
        if not isinstance(raw, dict) or sum(isinstance(raw.get(k), dict) for k in ('free', 'used', 'total')) < 2:
            raise ValueError('Incomplete balances')
        currencies = set().union(*(raw.get(k, {}) for k in ('free', 'used', 'total')))
        result = []
        for currency in sorted(currencies):
            free, used, total = (raw.get(k, {}).get(currency) for k in ('free', 'used', 'total'))
            if free is None and used is not None and total is not None:
                free = number(total) - number(used)
            if used is None and free is not None and total is not None:
                used = number(total) - number(free)
            if total is None and free is not None and used is not None:
                total = number(free) + number(used)
            row = Balance(currency=currency, free=number(free), used=number(used), total=number(total))
            if row.total:
                result.append(row)
        return result

    @safe_operation
    def get_price(self, symbol):
        self._market(symbol)
        row = self._client.fetch_ticker(symbol)
        return PriceQuote(symbol=symbol, price=number(row.get('last')),
                          observed_at=timestamp(row['timestamp']) if row.get('timestamp') is not None else datetime.now(timezone.utc))

    @staticmethod
    def _order(row, symbol):
        if not row.get('id'):
            raise ValueError('Missing order identity')
        status = row.get('status')
        return Order(order_id=str(row['id']), symbol=row.get('symbol') or symbol, side=row['side'],
                     status=status if status in ('open', 'closed', 'canceled', 'expired', 'rejected') else 'unknown',
                     amount=number(row['amount']), filled=number(row['filled']),
                     price=number(row['price']) if row.get('price') else None)

    @safe_operation
    def get_order(self, order_id, symbol):
        self._market(symbol)
        return self._order(self._client.fetch_order(order_id, symbol), symbol)

    @safe_operation
    def get_trades(self, symbol, since=None, limit=100):
        if not 1 <= limit <= 100 or (since is not None and since.tzinfo is None):
            raise ExchangeFailure('Use a timezone-aware start time and limit between 1 and 100', 422)
        self._market(symbol)
        rows = self._client.fetch_my_trades(symbol, int(since.timestamp() * 1000) if since else None, limit)
        result = {}
        for row in rows:
            if not row.get('id'):
                raise ValueError('Missing trade identity')
            result[str(row['id'])] = Trade(trade_id=str(row['id']), order_id=str(row['order']) if row.get('order') else None,
                symbol=row.get('symbol') or symbol, side=row['side'], amount=number(row['amount']),
                price=number(row['price']), executed_at=timestamp(row['timestamp']))
        return sorted(result.values(), key=lambda r: (r.executed_at, r.trade_id))

    @safe_operation
    def place_order(self, request):
        self.policy.require_mutation(sandbox_supported=self.sandbox_supported)
        if self.risk_check is None:
            raise ExchangeFailure('A portfolio risk validator is required before order submission', 422)
        market = self._market(request.symbol)
        amount = self._client.amount_to_precision(request.symbol, str(request.amount))
        price = self._client.price_to_precision(request.symbol, str(request.price)) if request.price is not None else None
        if number(amount) != request.amount or (price is not None and number(price) != request.price):
            raise ExchangeFailure('Order exceeds exchange precision; adjust amount or price', 422)
        for key, value in (('amount', request.amount), ('price', request.price),
                           ('cost', request.amount * request.price if request.price else None)):
            bounds = market.get('limits', {}).get(key) or {}
            if value is not None and ((bounds.get('min') is not None and value < number(bounds['min'])) or
                                      (bounds.get('max') is not None and value > number(bounds['max']))):
                raise ExchangeFailure('Order is outside exchange limits', 422)
        self.risk_check(request)
        # Never retry an ambiguous submission; Phase 7 must reconcile the client ID.
        return self._order(self._client.create_order(request.symbol, request.order_type, request.side,
            amount, price, {'clientOrderId': str(request.client_order_id)}), request.symbol)

    @safe_operation
    def cancel_order(self, order_id, symbol):
        self.policy.require_mutation(sandbox_supported=self.sandbox_supported)
        self._market(symbol)
        self._client.cancel_order(order_id, symbol)
        return self.get_order(order_id, symbol)


class BinanceAdapter(CCXTSpotAdapter):
    exchange = ExchangeName.BINANCE
    sandbox_supported = True


class CoinbaseAdapter(CCXTSpotAdapter):
    exchange = ExchangeName.COINBASE


class KrakenAdapter(CCXTSpotAdapter):
    exchange = ExchangeName.KRAKEN


def make_adapter(exchange, credentials, policy):
    classes = {ExchangeName.BINANCE: BinanceAdapter, ExchangeName.COINBASE: CoinbaseAdapter, ExchangeName.KRAKEN: KrakenAdapter}
    return classes[ExchangeName(exchange)](credentials, policy)
