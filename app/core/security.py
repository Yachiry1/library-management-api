from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import Settings

password_hash = PasswordHash.recommended()


class TokenError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def hash_token_identifier(identifier: str) -> str:
    return sha256(identifier.encode("utf-8")).hexdigest()


def create_access_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: UUID, settings: Settings, *, jti: str | None = None
) -> tuple[str, str]:
    now = datetime.now(UTC)
    token_jti = jti or str(uuid4())
    payload = {
        "sub": str(user_id),
        "jti": token_jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.refresh_token_expire_days)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_jti


def decode_token(token: str, settings: Settings) -> dict[str, object]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise TokenError("token_expired", "Token has expired.") from exc
    except InvalidTokenError as exc:
        raise TokenError("invalid_token", "Token is invalid.") from exc
    if not isinstance(payload, dict):
        raise TokenError("invalid_token", "Token payload is invalid.")
    return payload


def require_token_type(payload: dict[str, object], expected_type: str) -> None:
    if payload.get("type") != expected_type:
        raise TokenError("invalid_token_type", f"Expected a {expected_type} token.")


def token_subject(payload: dict[str, object]) -> UUID:
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise TokenError("invalid_token", "Token subject is missing.")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise TokenError("invalid_token", "Token subject is invalid.") from exc


def refresh_jti(payload: dict[str, object]) -> str:
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise TokenError("invalid_token", "Refresh token identifier is missing.")
    return jti
