from decimal import Decimal

import ccxt

from app.exchange.adapters import BinanceAdapter, ExchangeFailure, number, safe_operation, timestamp
from app.exchange.contracts import OrderRequest


class SubmissionRejected(ExchangeFailure):
    pass


class SandboxAdapter(BinanceAdapter):
    @safe_operation
    def prepare(self, identity, symbol, side, amount, price, slippage_bps):
        self.policy.require_mutation(sandbox_supported=True)
        market = self._market(symbol)
        factor = 1 + Decimal(slippage_bps) / 10000 * (1 if side == 'buy' else -1)
        limit = number(self._client.price_to_precision(symbol, str(price * factor)))
        quantity = number(self._client.amount_to_precision(symbol, str(amount)))
        if quantity <= 0 or limit <= 0:
            raise ExchangeFailure('Order is below exchange precision', 422)
        for key, value in (('amount', quantity), ('price', limit), ('cost', quantity * limit)):
            bounds = market.get('limits', {}).get(key) or {}
            if (bounds.get('min') is not None and value < number(bounds['min']) or
                    bounds.get('max') is not None and value > number(bounds['max'])):
                raise ExchangeFailure('Order is outside exchange limits', 422)
        return OrderRequest(client_order_id=identity, symbol=symbol, side=side,
                            order_type='limit', amount=quantity, price=limit)

    @safe_operation
    def submit(self, request):
        self.policy.require_mutation(sandbox_supported=True)
        if self.risk_check is None:
            raise ExchangeFailure('Risk approval is required', 422)
        self.risk_check(request)
        # IOC bounds the price and cancels any remainder. Persist intent first.
        try:
            self._client.create_order(request.symbol, 'limit', request.side, str(request.amount), str(request.price),
                                      {'newClientOrderId': str(request.client_order_id), 'timeInForce': 'IOC'})
        except (ccxt.AuthenticationError, ccxt.PermissionDenied, ccxt.InsufficientFunds, ccxt.InvalidOrder) as exc:
            if 'duplicate' in str(exc).lower():
                raise ExchangeFailure('Duplicate client identity requires reconciliation', 503) from None
            raise SubmissionRejected('Sandbox order was rejected by the exchange', 422) from None

    @safe_operation
    def lookup(self, identity, symbol):
        market = self._market(symbol)
        row = self._client.private_get_order({'symbol': market['id'], 'origClientOrderId': str(identity)})
        if row['clientOrderId'] != str(identity) or row['symbol'] != market['id']:
            raise ValueError('Order identity mismatch')
        return {'exchange_order_id': str(row['orderId']), 'symbol': symbol,
                'side': row['side'].lower(), 'amount': number(row['origQty']),
                'filled': number(row['executedQty']), 'cost': number(row['cummulativeQuoteQty']),
                'status': row['status']}

    @safe_operation
    def cancel(self, identity, symbol):
        self.policy.require_mutation(sandbox_supported=True)
        market = self._market(symbol)
        self._client.private_delete_order({'symbol': market['id'], 'origClientOrderId': str(identity)})

    @safe_operation
    def fills(self, order, symbol):
        market = self._market(symbol)
        result, cursor = {}, None
        for _ in range(20):
            params = {'symbol': market['id'], 'limit': 1000}
            params.update({'fromId': cursor} if cursor is not None else {'orderId': int(order['exchange_order_id'])})
            rows = self._client.private_get_mytrades(params)
            for row in rows:
                if str(row['orderId']) == order['exchange_order_id']:
                    if row['symbol'] != market['id'] or bool(row['isBuyer']) != (order['side'] == 'buy'):
                        raise ValueError('Fill identity mismatch')
                    result[str(row['id'])] = {'trade_id': str(row['id']), 'quantity': number(row['qty']),
                        'price': number(row['price']), 'cost': number(row['quoteQty']),
                        'fee': number(row['commission']), 'fee_currency': row['commissionAsset'],
                        'executed_at': timestamp(row['time'])}
            quantity = sum((r['quantity'] for r in result.values()), Decimal(0))
            if quantity >= order['filled'] or len(rows) < 1000:
                break
            next_cursor = max(int(r['id']) for r in rows) + 1
            if cursor is not None and next_cursor <= cursor:
                break
            cursor = next_cursor
        if (sum((r['quantity'] for r in result.values()), Decimal(0)) != order['filled'] or
                sum((r['cost'] for r in result.values()), Decimal(0)) != order['cost']):
            raise ExchangeFailure('Fill history is incomplete; reconciliation will retry', 503)
        return sorted(result.values(), key=lambda r: (r['executed_at'], int(r['trade_id'])))
