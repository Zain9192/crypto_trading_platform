import base64
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import psycopg
import pytest
from pydantic import SecretStr
from app.exchange.adapters import ExchangeFailure
from app.exchange.contracts import Credentials, ExchangeName
from app.exchange.repository import ExchangeRepository
from app.exchange.rotate_key import rotate
from app.exchange.schemas import ConnectionCreate
from app.exchange.security import CredentialCipher
from app.exchange.service import ExchangeService

DSN = os.getenv('PREDICTION_TEST_DSN')
pytestmark = pytest.mark.skipif(not DSN, reason='Disposable PostgreSQL service is not configured')


@pytest.fixture
def setup():
    with psycopg.connect(DSN) as c:
        root = Path(__file__).resolve().parents[3] / 'database' / 'postgres'
        for name in ('001_initial.sql','002_auth.sql','005_exchange.sql','005_exchange.sql'):
            c.execute((root / name).read_text())
        identity = uuid4().hex
        user = c.execute("INSERT INTO users(username,email,password_hash) VALUES (%s,%s,'unused') RETURNING user_id", (identity, identity+'@example.test')).fetchone()[0]
    key = os.urandom(32)
    settings = SimpleNamespace(exchange_encryption_key=SecretStr(base64.urlsafe_b64encode(key).decode()))
    service = ExchangeService(ExchangeRepository(DSN), settings, Mock(return_value=Mock()))
    body = ConnectionCreate(exchange=ExchangeName.BINANCE, label='Research', credentials=Credentials(api_key=uuid4().hex,api_secret=uuid4().hex))
    yield service, user, body, key
    with psycopg.connect(DSN) as c:
        c.execute('DELETE FROM users WHERE user_id=%s',(user,))


def test_encrypted_lifecycle_and_ownership(setup):
    s,u,body,key = setup
    saved = s.create(u,body)
    row = s.repository.get(u,saved.connection_id)
    assert body.credentials.api_key.get_secret_value() not in row['credentials_ciphertext']
    assert 'credentials_ciphertext' not in saved.model_dump()
    assert 'api_key' not in s.list(u)[0].model_dump_json()
    assert CredentialCipher(key).decrypt(row['credentials_ciphertext'],**s.context(row)) == body.credentials
    for action in (lambda:s.read(u+999999,saved.connection_id,'get_balance'), lambda:s.replace_credentials(u+999999,saved.connection_id,body.credentials), lambda:s.repository.delete(u+999999,saved.connection_id)):
        with pytest.raises(ExchangeFailure) as error:
            action()
        assert error.value.status_code == 404
    assert s.list(u+999999) == []
    replacement = Credentials(api_key=uuid4().hex,api_secret=uuid4().hex)
    s.replace_credentials(u,saved.connection_id,replacement)
    s.read(u,saved.connection_id,'get_balance')
    assert s.adapter_factory.call_args.args[1] == replacement
    assert s.adapter_factory.call_args.args[2].read_only
    with pytest.raises(ExchangeFailure) as conflict:
        s.create(u,body)
    assert conflict.value.status_code == 409
    s.repository.delete(u,saved.connection_id)
    assert s.list(u) == []


def test_verification_failure_preserves_previous_key_and_missing_config_stores_nothing(setup):
    s,u,body,_ = setup
    saved = s.create(u,body)
    before = s.repository.get(u,saved.connection_id)['credentials_ciphertext']
    s.adapter_factory.return_value.connect.side_effect = ExchangeFailure('Rejected',422)
    with pytest.raises(ExchangeFailure):
        s.replace_credentials(u,saved.connection_id,Credentials(api_key=uuid4().hex,api_secret=uuid4().hex))
    assert s.repository.get(u,saved.connection_id)['credentials_ciphertext'] == before
    s.repository.delete(u,saved.connection_id)
    with pytest.raises(ExchangeFailure):
        s.create(u,body)
    assert s.list(u) == []
    s.settings.exchange_encryption_key = SecretStr('')
    with pytest.raises(ExchangeFailure) as error:
        s.create(u,body)
    assert error.value.status_code == 503


def test_key_rotation_and_failure_rollback(setup):
    s,u,body,old = setup
    saved = s.create(u,body)
    new = os.urandom(32)
    assert rotate(DSN,old,new) == 1
    row = s.repository.get(u,saved.connection_id)
    assert CredentialCipher(new).decrypt(row['credentials_ciphertext'],**s.context(row)) == body.credentials
    with pytest.raises(ValueError):
        CredentialCipher(old).decrypt(row['credentials_ciphertext'],**s.context(row))
    with pytest.raises(ValueError):
        rotate(DSN,os.urandom(32),os.urandom(32))
    assert s.repository.get(u,saved.connection_id)['credentials_ciphertext'] == row['credentials_ciphertext']
