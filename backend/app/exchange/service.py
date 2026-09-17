import base64
import logging
from contextlib import contextmanager
from uuid import uuid4
from app.exchange.adapters import ExchangeFailure, make_adapter
from app.exchange.contracts import ConnectionPolicy, ExchangeName
from app.exchange.schemas import ConnectionView
from app.exchange.security import CredentialCipher


def configured_cipher(settings):
    try:
        return CredentialCipher(base64.b64decode(settings.exchange_encryption_key.get_secret_value(), altchars=b'-_', validate=True))
    except (ValueError, TypeError):
        raise ExchangeFailure('Exchange encryption key is not configured correctly', 503) from None


def capabilities():
    return [
        {'exchange': 'binance', 'sandbox': True, 'note': 'Spot testnet and production read-only connections.'},
        {'exchange': 'coinbase', 'sandbox': False, 'note': 'Production read-only. The static Coinbase sandbox is not an execution simulator.'},
        {'exchange': 'kraken', 'sandbox': False, 'note': 'Production read-only. Spot UAT needs separate Kraken access and is not configured here.'},
    ]


class ExchangeService:
    def __init__(self, repository, settings, adapter_factory=make_adapter):
        self.repository, self.settings, self.adapter_factory = repository, settings, adapter_factory

    @staticmethod
    def context(row):
        return {'owner_id': row['user_id'], 'exchange': ExchangeName(row['exchange']), 'connection_id': row['connection_id']}

    @contextmanager
    def transport(self, exchange, credentials, sandbox):
        adapter = self.adapter_factory(exchange, credentials, ConnectionPolicy(sandbox=sandbox))
        try:
            yield adapter
        finally:
            adapter.close()

    def list(self, user_id):
        return [ConnectionView.model_validate(row) for row in self.repository.list(user_id)]

    def create(self, user_id, body):
        if body.sandbox and body.exchange != ExchangeName.BINANCE:
            raise ExchangeFailure('Spot sandbox is unsupported for this exchange; choose production read-only', 422)
        cipher, identity = configured_cipher(self.settings), uuid4()
        encrypted = cipher.encrypt(body.credentials, owner_id=user_id, exchange=body.exchange, connection_id=identity)
        with self.transport(body.exchange, body.credentials, body.sandbox) as adapter:
            adapter.connect()
        return ConnectionView.model_validate(self.repository.create(user_id, identity, body, encrypted))

    def replace_credentials(self, user_id, connection_id, credentials):
        row = self.repository.get(user_id, connection_id)
        cipher = configured_cipher(self.settings)
        with self.transport(ExchangeName(row['exchange']), credentials, row['sandbox']) as adapter:
            adapter.connect()
        encrypted = cipher.encrypt(credentials, **self.context(row))
        return ConnectionView.model_validate(self.repository.replace_credentials(user_id, connection_id, encrypted))

    def read(self, user_id, connection_id, operation, *args):
        if operation not in ('connect', 'get_balance', 'get_price', 'get_order', 'get_trades'):
            raise ExchangeFailure('Exchange operation is not available', 422)
        row = self.repository.get(user_id, connection_id)
        try:
            credentials = configured_cipher(self.settings).decrypt(row['credentials_ciphertext'], **self.context(row))
        except ValueError:
            raise ExchangeFailure('Stored exchange credentials cannot be decrypted; contact the operator', 503) from None
        try:
            with self.transport(ExchangeName(row['exchange']), credentials, row['sandbox']) as adapter:
                result = getattr(adapter, operation)(*args)
        except ExchangeFailure:
            try:
                self.repository.notify_failure(user_id, connection_id)
            except Exception:
                logging.getLogger(__name__).warning('Could not persist exchange failure notification')
            raise
        return {'message': 'Connection verified. Read-only access is active.'} if operation == 'connect' else result
