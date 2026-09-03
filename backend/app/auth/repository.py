from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from psycopg import Connection
from psycopg.errors import UniqueViolation


class DuplicateUserError(ValueError):
    pass


class UserRepositoryProtocol(Protocol):
    def get_user_by_email(self, email: str) -> dict[str, Any] | None: ...
    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None: ...
    def create_user(self, username: str, email: str, password_hash: str) -> dict[str, Any]: ...
    def create_email_verification_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None: ...
    def consume_email_verification_token(self, token_hash: str) -> int | None: ...
    def record_failed_login(self, user_id: int, max_attempts: int, lockout_minutes: int) -> dict[str, Any]: ...
    def reset_failed_login(self, user_id: int) -> None: ...
    def save_refresh_token(self, jti: str, user_id: int, expires_at: datetime) -> None: ...
    def get_refresh_token(self, jti: str) -> dict[str, Any] | None: ...
    def revoke_refresh_token(self, jti: str) -> None: ...
    def save_totp_secret(self, user_id: int, encrypted_secret: str) -> None: ...
    def enable_totp(self, user_id: int) -> None: ...
    def disable_totp(self, user_id: int) -> None: ...


class PostgresUserRepository:
    def __init__(self, connection: Connection):
        self.connection = connection

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, username, email, password_hash, role, is_active,
                       is_email_verified, failed_login_attempts, locked_until,
                       totp_enabled, totp_secret, created_at
                FROM users
                WHERE lower(email) = lower(%s)
                """,
                (email,),
            )
            return cursor.fetchone()

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, username, email, password_hash, role, is_active,
                       is_email_verified, failed_login_attempts, locked_until,
                       totp_enabled, totp_secret, created_at
                FROM users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return cursor.fetchone()

    def create_user(self, username: str, email: str, password_hash: str) -> dict[str, Any]:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (%s, lower(%s), %s, 'trader')
                    RETURNING user_id, username, email, password_hash, role, is_active,
                              is_email_verified, failed_login_attempts, locked_until,
                              totp_enabled, totp_secret, created_at
                    """,
                    (username, email, password_hash),
                )
                user = cursor.fetchone()
            self.connection.commit()
            return user
        except UniqueViolation as exc:
            self.connection.rollback()
            raise DuplicateUserError("Email or username is already registered") from exc

    def create_email_verification_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (user_id, token_hash, expires_at),
            )
        self.connection.commit()

    def consume_email_verification_token(self, token_hash: str) -> int | None:
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE email_verification_tokens
                    SET used_at = NOW()
                    WHERE token_hash = %s
                      AND used_at IS NULL
                      AND expires_at > NOW()
                    RETURNING user_id
                    """,
                    (token_hash,),
                )
                token_row = cursor.fetchone()
                if not token_row:
                    return None
                user_id = int(token_row["user_id"])
                cursor.execute(
                    """
                    UPDATE users
                    SET is_email_verified = TRUE, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                return user_id

    def record_failed_login(self, user_id: int, max_attempts: int, lockout_minutes: int) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET failed_login_attempts = failed_login_attempts + 1,
                    locked_until = CASE
                        WHEN failed_login_attempts + 1 >= %s
                        THEN NOW() + (%s * INTERVAL '1 minute')
                        ELSE locked_until
                    END,
                    updated_at = NOW()
                WHERE user_id = %s
                RETURNING failed_login_attempts, locked_until
                """,
                (max_attempts, lockout_minutes, user_id),
            )
            row = cursor.fetchone()
        self.connection.commit()
        return row

    def reset_failed_login(self, user_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET failed_login_attempts = 0, locked_until = NULL, updated_at = NOW()
                WHERE user_id = %s
                """,
                (user_id,),
            )
        self.connection.commit()

    def save_refresh_token(self, jti: str, user_id: int, expires_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO refresh_tokens (jti, user_id, expires_at)
                VALUES (%s, %s, %s)
                """,
                (jti, user_id, expires_at),
            )
        self.connection.commit()

    def get_refresh_token(self, jti: str) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT jti, user_id, expires_at, revoked_at
                FROM refresh_tokens
                WHERE jti = %s
                """,
                (jti,),
            )
            return cursor.fetchone()

    def revoke_refresh_token(self, jti: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE refresh_tokens
                SET revoked_at = COALESCE(revoked_at, NOW())
                WHERE jti = %s
                """,
                (jti,),
            )
        self.connection.commit()

    def save_totp_secret(self, user_id: int, encrypted_secret: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET totp_secret = %s, totp_enabled = FALSE, updated_at = NOW()
                WHERE user_id = %s
                """,
                (encrypted_secret, user_id),
            )
        self.connection.commit()

    def enable_totp(self, user_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET totp_enabled = TRUE, updated_at = NOW() WHERE user_id = %s",
                (user_id,),
            )
        self.connection.commit()

    def disable_totp(self, user_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET totp_enabled = FALSE, totp_secret = NULL, updated_at = NOW()
                WHERE user_id = %s
                """,
                (user_id,),
            )
        self.connection.commit()
