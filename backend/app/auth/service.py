from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp

from app.auth.repository import DuplicateUserError, UserRepositoryProtocol
from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_auth_secret,
    encrypt_auth_secret,
    hash_one_time_token,
    hash_password,
    verify_password,
)


class AuthenticationError(ValueError):
    pass


class AccountLockedError(AuthenticationError):
    pass


class EmailNotVerifiedError(AuthenticationError):
    pass


class TwoFactorRequiredError(AuthenticationError):
    pass


class TwoFactorInvalidError(AuthenticationError):
    pass


class AuthService:
    def __init__(self, repository: UserRepositoryProtocol, settings: Settings):
        self.repository = repository
        self.settings = settings

    def register(self, username: str, email: str, password: str) -> tuple[dict[str, Any], str]:
        existing = self.repository.get_user_by_email(email)
        if existing:
            raise DuplicateUserError("Email or username is already registered")

        password_hash = hash_password(password)
        user = self.repository.create_user(username=username, email=email, password_hash=password_hash)
        raw_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.email_verification_token_minutes
        )
        self.repository.create_email_verification_token(
            user_id=int(user["user_id"]),
            token_hash=hash_one_time_token(raw_token),
            expires_at=expires_at,
        )
        return user, raw_token

    def verify_email(self, raw_token: str) -> dict[str, Any]:
        user_id = self.repository.consume_email_verification_token(hash_one_time_token(raw_token))
        if not user_id:
            raise AuthenticationError("Verification token is invalid, expired, or already used")
        user = self.repository.get_user_by_id(user_id)
        if not user:
            raise AuthenticationError("User account no longer exists")
        return user

    def login(self, email: str, password: str, totp_code: str | None = None) -> dict[str, Any]:
        user = self.repository.get_user_by_email(email)
        if not user:
            raise AuthenticationError("Invalid email or password")

        self._assert_account_available(user)

        if not verify_password(password, str(user["password_hash"])):
            self.repository.record_failed_login(
                int(user["user_id"]),
                self.settings.login_max_failed_attempts,
                self.settings.login_lockout_minutes,
            )
            raise AuthenticationError("Invalid email or password")

        if not bool(user["is_email_verified"]):
            raise EmailNotVerifiedError("Email verification is required before login")

        if bool(user["totp_enabled"]):
            if not totp_code:
                raise TwoFactorRequiredError("Two-factor authentication code is required")
            if not self._verify_totp(user, totp_code):
                self.repository.record_failed_login(
                    int(user["user_id"]),
                    self.settings.login_max_failed_attempts,
                    self.settings.login_lockout_minutes,
                )
                raise TwoFactorInvalidError("Invalid two-factor authentication code")

        self.repository.reset_failed_login(int(user["user_id"]))
        return self._issue_token_pair(user)

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        payload = decode_token(refresh_token, "refresh", self.settings)
        jti = str(payload.get("jti", ""))
        if not jti:
            raise TokenError("Refresh token identifier is missing")

        token_record = self.repository.get_refresh_token(jti)
        if not token_record:
            raise TokenError("Refresh token is not recognized")
        if token_record.get("revoked_at") is not None:
            raise TokenError("Refresh token has been revoked")
        if token_record["expires_at"] <= datetime.now(timezone.utc):
            raise TokenError("Refresh token has expired")

        user = self.repository.get_user_by_id(int(payload["sub"]))
        if not user or not bool(user["is_active"]):
            raise AuthenticationError("User account is unavailable")

        self.repository.revoke_refresh_token(jti)
        return self._issue_token_pair(user)

    def logout(self, refresh_token: str) -> None:
        payload = decode_token(refresh_token, "refresh", self.settings)
        jti = str(payload.get("jti", ""))
        if jti:
            self.repository.revoke_refresh_token(jti)

    def current_user(self, access_token: str) -> dict[str, Any]:
        payload = decode_token(access_token, "access", self.settings)
        user = self.repository.get_user_by_id(int(payload["sub"]))
        if not user or not bool(user["is_active"]):
            raise AuthenticationError("User account is unavailable")
        return user

    def setup_totp(self, user_id: int) -> tuple[str, str]:
        user = self.repository.get_user_by_id(user_id)
        if not user:
            raise AuthenticationError("User account is unavailable")
        secret = pyotp.random_base32()
        encrypted_secret = encrypt_auth_secret(secret, self.settings)
        self.repository.save_totp_secret(user_id, encrypted_secret)
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=str(user["email"]),
            issuer_name=self.settings.totp_issuer,
        )
        return secret, uri

    def enable_totp(self, user_id: int, code: str) -> None:
        user = self.repository.get_user_by_id(user_id)
        if not user or not user.get("totp_secret"):
            raise AuthenticationError("Two-factor authentication setup has not been started")
        if not self._verify_totp(user, code):
            raise TwoFactorInvalidError("Invalid two-factor authentication code")
        self.repository.enable_totp(user_id)

    def disable_totp(self, user_id: int, password: str, code: str) -> None:
        user = self.repository.get_user_by_id(user_id)
        if not user or not bool(user["totp_enabled"]):
            raise AuthenticationError("Two-factor authentication is not enabled")
        if not verify_password(password, str(user["password_hash"])):
            raise AuthenticationError("Invalid password")
        if not self._verify_totp(user, code):
            raise TwoFactorInvalidError("Invalid two-factor authentication code")
        self.repository.disable_totp(user_id)

    def _issue_token_pair(self, user: dict[str, Any]) -> dict[str, Any]:
        access_token, access_expires_at = create_access_token(
            user_id=int(user["user_id"]),
            role=str(user["role"]),
            settings=self.settings,
        )
        refresh_token, jti, refresh_expires_at = create_refresh_token(
            user_id=int(user["user_id"]),
            settings=self.settings,
        )
        self.repository.save_refresh_token(jti, int(user["user_id"]), refresh_expires_at)
        expires_in = max(
            0,
            int((access_expires_at - datetime.now(timezone.utc)).total_seconds()),
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": expires_in,
        }

    def _assert_account_available(self, user: dict[str, Any]) -> None:
        if not bool(user["is_active"]):
            raise AuthenticationError("User account is unavailable")
        locked_until = user.get("locked_until")
        if locked_until and locked_until > datetime.now(timezone.utc):
            raise AccountLockedError("Account is temporarily locked after repeated failed logins")

    def _verify_totp(self, user: dict[str, Any], code: str) -> bool:
        encrypted_secret = user.get("totp_secret")
        if not encrypted_secret:
            return False
        secret = decrypt_auth_secret(str(encrypted_secret), self.settings)
        return bool(pyotp.TOTP(secret).verify(code, valid_window=1))
