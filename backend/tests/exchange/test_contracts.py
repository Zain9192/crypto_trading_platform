from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.exchange.contracts import ConnectionPolicy, Credentials, ExchangeError, OrderRequest


def order(**values):
    return OrderRequest(**{"client_order_id": uuid4(), "symbol": "BTC/USDT", "side": "buy",
                           "order_type": "limit", "amount": "0.123456789123456789",
                           "price": "100.123456789", **values})


def test_decimal_precision_and_redacted_credentials():
    assert order().amount == Decimal("0.123456789123456789")
    credentials = Credentials(api_key=uuid4().hex, api_secret=uuid4().hex)
    for secret in (credentials.api_key.get_secret_value(), credentials.api_secret.get_secret_value()):
        assert secret not in repr(credentials)
        assert secret not in credentials.model_dump_json()


@pytest.mark.parametrize("values", [
    {"amount": "NaN"}, {"amount": "Infinity"}, {"amount": "0"}, {"price": "-1"},
    {"price": None}, {"symbol": "BTC/USDT:USDT"}, {"symbol": "btc/usdt"},
    {"order_type": "market"}, {"side": "short"}, {"leverage": 10},
])
def test_invalid_or_derivative_orders_rejected(values):
    with pytest.raises(ValidationError):
        order(**values)


def test_market_order_omits_limit_price():
    assert order(order_type="market", price=None).price is None


@pytest.mark.parametrize("policy,supported", [
    (ConnectionPolicy(), True),
    (ConnectionPolicy(sandbox=False, read_only=False), True),
    (ConnectionPolicy(sandbox=True, read_only=False), False),
])
def test_mutations_fail_closed(policy, supported):
    with pytest.raises(ExchangeError):
        policy.require_mutation(sandbox_supported=supported)


def test_supported_sandbox_can_explicitly_enable_mutations():
    ConnectionPolicy(sandbox=True, read_only=False).require_mutation(sandbox_supported=True)


@pytest.mark.parametrize("field", ["api_key", "api_secret", "passphrase"])
def test_blank_credentials_rejected(field):
    with pytest.raises(ValidationError):
        Credentials(**{"api_key": uuid4().hex, "api_secret": uuid4().hex, field: "   "})
