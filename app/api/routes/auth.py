from fastapi import APIRouter, status

from app.api.dependencies import AppSettings, DbSession
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
    responses={409: {"description": "Email already registered"}},
)
async def register(
    payload: RegisterRequest, session: DbSession, settings: AppSettings
) -> AuthResponse:
    return await AuthService(session, settings).register(payload.email, payload.password)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in and issue token pair",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(payload: LoginRequest, session: DbSession, settings: AppSettings) -> AuthResponse:
    return await AuthService(session, settings).login(payload.email, payload.password)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token",
    responses={401: {"description": "Invalid, expired, revoked, or incorrectly typed token"}},
)
async def refresh(payload: RefreshRequest, session: DbSession, settings: AppSettings) -> TokenPair:
    return await AuthService(session, settings).refresh(payload.refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke a refresh token",
    responses={401: {"description": "Invalid, expired, revoked, or incorrectly typed token"}},
)
async def logout(
    payload: LogoutRequest, session: DbSession, settings: AppSettings
) -> MessageResponse:
    await AuthService(session, settings).logout(payload.refresh_token)
    return MessageResponse(message="logged out")
