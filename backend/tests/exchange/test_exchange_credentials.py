import base64
import os
from uuid import uuid4

import pytest

from app.exchange.contracts import Credentials, ExchangeName
from app.exchange.security import CredentialCipher


@pytest.fixture
def encrypted():
    key = os.urandom(32)
    cipher = CredentialCipher(key)
    credentials = Credentials(api_key=uuid4().hex, api_secret=uuid4().hex, passphrase=uuid4().hex)
    context = {"owner_id": 7, "exchange": ExchangeName.BINANCE, "connection_id": uuid4()}
    token = cipher.encrypt(credentials, **context)
    return key, cipher, credentials, context, token


def test_roundtrip_uses_random_nonce_and_does_not_expose_secrets(encrypted):
    key, cipher, credentials, context, token = encrypted
    assert cipher.encrypt(credentials, **context) != token
    recovered = CredentialCipher(key).decrypt(token, **context)
    assert recovered == credentials
    packed = base64.urlsafe_b64decode(token.split(".", 1)[1])
    assert credentials.api_key.get_secret_value().encode() not in packed
    assert credentials.api_secret.get_secret_value().encode() not in packed


@pytest.mark.parametrize("change", ["owner", "exchange", "connection", "key", "ciphertext"])
def test_tampering_and_cross_account_substitution_rejected(encrypted, change):
    _, cipher, _, context, token = encrypted
    if change == "owner":
        context = {**context, "owner_id": 8}
    elif change == "exchange":
        context = {**context, "exchange": ExchangeName.KRAKEN}
    elif change == "connection":
        context = {**context, "connection_id": uuid4()}
    elif change == "key":
        cipher = CredentialCipher(os.urandom(32))
    else:
        raw = bytearray(base64.urlsafe_b64decode(token.split(".", 1)[1]))
        raw[-1] ^= 1
        token = "v1." + base64.urlsafe_b64encode(raw).decode()
    with pytest.raises(ValueError, match="^Exchange credentials could not be decrypted$"):
        cipher.decrypt(token, **context)


@pytest.mark.parametrize("token", ["", "v2.bad", "v1.%%%%", "v1.YQ=="])
def test_malformed_tokens_have_safe_errors(encrypted, token):
    _, cipher, _, context, _ = encrypted
    with pytest.raises(ValueError, match="^Exchange credentials could not be decrypted$"):
        cipher.decrypt(token, **context)


@pytest.mark.parametrize("length", [0, 16, 24, 31, 33])
def test_only_aes256_keys_accepted(length):
    with pytest.raises(ValueError, match="32-byte"):
        CredentialCipher(os.urandom(length))
