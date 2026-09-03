from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from fastapi.testclient import TestClient

from app.auth.dependencies import get_user_repository
from app.auth.repository import DuplicateUserError
from app.main import app


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[int, dict[str, Any]] = {}
        self.verification_tokens: dict[str, dict[str, Any]] = {}
        self.refresh_tokens: dict[str, dict[str, Any]] = {}
        self.next_user_id = 1

    def _copy(self, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return deepcopy(value) if value else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized = email.lower()
        for user in self.users.values():
            if user["email"].lower() == normalized:
                return self._copy(user)
        return None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self._copy(self.users.get(user_id))

    def create_user(self, username: str, email: str, password_hash: str) -> dict[str, Any]:
        for user in self.users.values():
            if user["email"].lower() == email.lower() or user["username"].lower() == username.lower():
                raise DuplicateUserError("Email or username is already registered")
        now = datetime.now(timezone.utc)
        user = {
            "user_id": self.next_user_id,
            "username": username,
            "email": email.lower(),
            "password_hash": password_hash,
            "role": "trader",
            "is_active": True,
            "is_email_verified": False,
            "failed_login_attempts": 0,
            "locked_until": None,
            "totp_enabled": False,
            "totp_secret": None,
            "created_at": now,
        }
        self.users[self.next_user_id] = user
        self.next_user_id += 1
        return self._copy(user)

    def create_email_verification_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.verification_tokens[token_hash] = {
            "user_id": user_id,
            "expires_at": expires_at,
            "used_at": None,
        }

    def consume_email_verification_token(self, token_hash: str) -> int | None:
        token = self.verification_tokens.get(token_hash)
        now = datetime.now(timezone.utc)
        if not token or token["used_at"] is not None or token["expires_at"] <= now:
            return None
        token["used_at"] = now
        user_id = int(token["user_id"])
        self.users[user_id]["is_email_verified"] = True
        return user_id

    def record_failed_login(self, user_id: int, max_attempts: int, lockout_minutes: int) -> dict[str, Any]:
        user = self.users[user_id]
        user["failed_login_attempts"] += 1
        if user["failed_login_attempts"] >= max_attempts:
            user["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
        return {
            "failed_login_attempts": user["failed_login_attempts"],
            "locked_until": user["locked_until"],
        }

    def reset_failed_login(self, user_id: int) -> None:
        self.users[user_id]["failed_login_attempts"] = 0
        self.users[user_id]["locked_until"] = None

    def save_refresh_token(self, jti: str, user_id: int, expires_at: datetime) -> None:
        self.refresh_tokens[jti] = {
            "jti": jti,
            "user_id": user_id,
            "expires_at": expires_at,
            "revoked_at": None,
        }

    def get_refresh_token(self, jti: str) -> dict[str, Any] | None:
        return self._copy(self.refresh_tokens.get(jti))

    def revoke_refresh_token(self, jti: str) -> None:
        if jti in self.refresh_tokens and self.refresh_tokens[jti]["revoked_at"] is None:
            self.refresh_tokens[jti]["revoked_at"] = datetime.now(timezone.utc)

    def save_totp_secret(self, user_id: int, encrypted_secret: str) -> None:
        self.users[user_id]["totp_secret"] = encrypted_secret
        self.users[user_id]["totp_enabled"] = False

    def enable_totp(self, user_id: int) -> None:
        self.users[user_id]["totp_enabled"] = True

    def disable_totp(self, user_id: int) -> None:
        self.users[user_id]["totp_enabled"] = False
        self.users[user_id]["totp_secret"] = None


repo = FakeUserRepository()
app.dependency_overrides[get_user_repository] = lambda: repo
client = TestClient(app)


def reset_repo() -> None:
    repo.users.clear()
    repo.verification_tokens.clear()
    repo.refresh_tokens.clear()
    repo.next_user_id = 1


def register_user(email: str = "trader@example.com", username: str = "trader1") -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "StrongPass123!"},
    )
    assert response.status_code == 201
    return response.json()


def verify_registered_user(registration: dict[str, Any]) -> None:
    token = registration["verification_token"]
    assert token
    response = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200
    assert response.json()["is_email_verified"] is True


def login_user(totp_code: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": "trader@example.com",
        "password": "StrongPass123!",
    }
    if totp_code is not None:
        payload["totp_code"] = totp_code
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    return response.json()


def test_register_verify_login_and_current_user_flow() -> None:
    reset_repo()
    registration = register_user()
    assert registration["user"]["role"] == "trader"
    assert registration["user"]["is_email_verified"] is False

    unverified_login = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@example.com", "password": "StrongPass123!"},
    )
    assert unverified_login.status_code == 403

    verify_registered_user(registration)
    tokens = login_user()
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "trader@example.com"


def test_duplicate_email_returns_conflict() -> None:
    reset_repo()
    register_user()
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "other", "email": "TRADER@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 409


def test_refresh_rotation_and_logout_revocation() -> None:
    reset_repo()
    registration = register_user()
    verify_registered_user(registration)
    tokens = login_user()

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    old_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert old_refresh.status_code == 401

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert logout.status_code == 200

    after_logout = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert after_logout.status_code == 401


def test_failed_login_lockout_after_five_attempts() -> None:
    reset_repo()
    registration = register_user()
    verify_registered_user(registration)

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "trader@example.com", "password": "WrongPass123!"},
        )
        assert response.status_code == 401

    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@example.com", "password": "StrongPass123!"},
    )
    assert locked.status_code == 423


def test_totp_setup_enable_and_login_requirement() -> None:
    reset_repo()
    registration = register_user()
    verify_registered_user(registration)
    tokens = login_user()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup = client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()

    enable = client.post("/api/v1/auth/2fa/enable", headers=headers, json={"code": code})
    assert enable.status_code == 200

    missing_code = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@example.com", "password": "StrongPass123!"},
    )
    assert missing_code.status_code == 401
    assert "two-factor" in missing_code.json()["detail"].lower()

    valid_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "trader@example.com",
            "password": "StrongPass123!",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert valid_login.status_code == 200


def test_invalid_or_reused_verification_token_is_rejected() -> None:
    reset_repo()
    registration = register_user()
    token = registration["verification_token"]
    verify_registered_user(registration)

    reused = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert reused.status_code == 400

    unknown = client.post(
        "/api/v1/auth/verify-email",
        json={"token": "x" * 40},
    )
    assert unknown.status_code == 400
