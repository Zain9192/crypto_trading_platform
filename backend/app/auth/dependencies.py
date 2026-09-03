from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from app.auth.repository import PostgresUserRepository, UserRepositoryProtocol
from app.auth.service import AuthService, AuthenticationError
from app.core.config import Settings, get_settings
from app.core.security import TokenError
from app.db.postgres import get_postgres_connection

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository(
    connection: Annotated[Connection, Depends(get_postgres_connection)],
) -> UserRepositoryProtocol:
    return PostgresUserRepository(connection)


def get_auth_service(
    repository: Annotated[UserRepositoryProtocol, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(repository, settings)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return service.current_user(credentials.credentials)
    except (TokenError, AuthenticationError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
