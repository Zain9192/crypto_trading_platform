"""Authenticated encryption for future exchange credential persistence.

This helper does not persist credentials or expose an HTTP endpoint. The future
repository must supply owner/connection identity from trusted database records.
Use a dedicated, externally supplied 32-byte key, separate from JWT/auth keys.
"""
import base64
import json
import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.exchange.contracts import Credentials, ExchangeName


class CredentialCipher:
    VERSION = "v1"

    def __init__(self, key: bytes):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("Exchange encryption requires a 32-byte key")
        self._cipher = AESGCM(key)

    @staticmethod
    def _context(owner_id: int, exchange: ExchangeName, connection_id: UUID) -> bytes:
        if type(owner_id) is not int or owner_id <= 0:
            raise ValueError("Invalid credential owner")
        return json.dumps(
            ["exchange-credentials", "v1", owner_id, ExchangeName(exchange).value, str(UUID(str(connection_id)))],
            separators=(",", ":"),
        ).encode()

    def encrypt(self, credentials: Credentials, *, owner_id: int, exchange: ExchangeName, connection_id: UUID) -> str:
        aad = self._context(owner_id, exchange, connection_id)
        # Explicit extraction is limited to this encryption boundary. Model dumps stay redacted.
        payload = {"api_key": credentials.api_key.get_secret_value(),
                   "api_secret": credentials.api_secret.get_secret_value(),
                   "passphrase": credentials.passphrase.get_secret_value() if credentials.passphrase else None}
        plaintext = json.dumps(payload, separators=(",", ":")).encode()
        nonce = os.urandom(12)
        encrypted = self._cipher.encrypt(nonce, plaintext, aad)
        return self.VERSION + "." + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")

    def decrypt(self, token: str, *, owner_id: int, exchange: ExchangeName, connection_id: UUID) -> Credentials:
        try:
            aad = self._context(owner_id, exchange, connection_id)
            version, encoded = token.split(".", 1)
            if version != self.VERSION or len(encoded) > 300000:
                raise ValueError("Invalid ciphertext")
            packed = base64.b64decode(encoded, altchars=b"-_", validate=True)
            if len(packed) < 28:
                raise ValueError("Invalid ciphertext")
            plaintext = self._cipher.decrypt(packed[:12], packed[12:], aad)
            return Credentials.model_validate(json.loads(plaintext))
        except (ValueError, TypeError, InvalidTag, UnicodeError):
            # Never attach ciphertext, credentials, provider errors or key material.
            raise ValueError("Exchange credentials could not be decrypted") from None
