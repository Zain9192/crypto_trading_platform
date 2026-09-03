from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.repository import DuplicateUserError
from app.auth.schemas import (
    EmailVerificationRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterResponse,
    TokenPairResponse,
    TwoFactorCodeRequest,
    TwoFactorDisableRequest,
    TwoFactorSetupResponse,
    UserCreate,
    UserResponse,
)
from app.auth.service import (
    AccountLockedError,
    AuthService,
    AuthenticationError,
    EmailNotVerifiedError,
    TwoFactorInvalidError,
    TwoFactorRequiredError,
)
from app.core.config import get_settings
from app.core.security import TokenError

router = APIRouter(prefix="/auth", tags=["authentication"])


def _public_user(user: dict[str, Any]) -> UserResponse:
    return UserResponse(
        user_id=int(user["user_id"]),
        username=str(user["username"]),
        email=str(user["email"]),
        role=str(user["role"]),
        is_email_verified=bool(user["is_email_verified"]),
        totp_enabled=bool(user["totp_enabled"]),
        created_at=user["created_at"],
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, service: Annotated[AuthService, Depends(get_auth_service)]) -> RegisterResponse:
    try:
        user, raw_verification_token = service.register(
            username=payload.username,
            email=str(payload.email),
            password=payload.password,
        )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    settings = get_settings()
    development_token = raw_verification_token if settings.app_env in {"development", "test"} else None
    return RegisterResponse(
        user=_public_user(user),
        verification_required=True,
        verification_token=development_token,
    )


@router.post("/verify-email", response_model=UserResponse)
def verify_email(
    payload: EmailVerificationRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    try:
        return _public_user(service.verify_email(payload.token))
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/login", response_model=TokenPairResponse)
def login(payload: LoginRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> TokenPairResponse:
    try:
        return TokenPairResponse(**service.login(str(payload.email), payload.password, payload.totp_code))
    except AccountLockedError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    except EmailNotVerifiedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TwoFactorRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except TwoFactorInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(
    payload: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPairResponse:
    try:
        return TokenPairResponse(**service.refresh(payload.refresh_token))
    except (TokenError, AuthenticationError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> MessageResponse:
    try:
        service.logout(payload.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> UserResponse:
    return _public_user(current_user)


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
def setup_two_factor(
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> TwoFactorSetupResponse:
    secret, uri = service.setup_totp(int(current_user["user_id"]))
    return TwoFactorSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/2fa/enable", response_model=MessageResponse)
def enable_two_factor(
    payload: TwoFactorCodeRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> MessageResponse:
    try:
        service.enable_totp(int(current_user["user_id"]), payload.code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Two-factor authentication enabled")


@router.post("/2fa/disable", response_model=MessageResponse)
def disable_two_factor(
    payload: TwoFactorDisableRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> MessageResponse:
    try:
        service.disable_totp(int(current_user["user_id"]), payload.password, payload.code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Two-factor authentication disabled")
