from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, app_error_from_integrity_error
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token_identifier,
    refresh_jti,
    require_token_type,
    token_subject,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import AuthResponse, TokenPair


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def register(self, email: str, password: str) -> AuthResponse:
        normalized_email = email.casefold()
        user = User(email=normalized_email, hashed_password=hash_password(password), is_active=True)
        try:
            async with self.session.begin():
                self.session.add(user)
                await self.session.flush()
                token_pair = await self._issue_tokens(user.id)
        except IntegrityError as exc:
            raise app_error_from_integrity_error(exc) from exc
        return AuthResponse(user=user, **token_pair.model_dump())

    async def login(self, email: str, password: str) -> AuthResponse:
        normalized_email = email.casefold()
        async with self.session.begin():
            user = await self._get_user_by_email(normalized_email)
            if user is None or not verify_password(password, user.hashed_password):
                raise AuthenticationError("invalid_credentials", "Email or password is incorrect.")
            if not user.is_active:
                raise AuthenticationError("inactive_user", "User is inactive.")
            token_pair = await self._issue_tokens(user.id)
        return AuthResponse(user=user, **token_pair.model_dump())

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = self._decode_refresh_payload(refresh_token)
        user_id = token_subject(payload)
        old_jti = refresh_jti(payload)
        old_hash = hash_token_identifier(old_jti)

        async with self.session.begin():
            token_record = await self._get_refresh_token_for_update(old_hash)
            now = datetime.now(UTC)
            if (
                token_record is None
                or token_record.user_id != user_id
                or token_record.revoked_at is not None
                or token_record.expires_at <= now
            ):
                raise AuthenticationError(
                    "invalid_refresh_token", "Refresh token is invalid or revoked."
                )

            replacement_token, replacement_jti = create_refresh_token(user_id, self.settings)
            replacement = RefreshToken(
                user_id=user_id,
                token_hash=hash_token_identifier(replacement_jti),
                expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
            )
            self.session.add(replacement)
            await self.session.flush()

            token_record.revoked_at = now
            token_record.replaced_by_token_id = replacement.id

            access_token = create_access_token(user_id, self.settings)

        return TokenPair(
            access_token=access_token,
            refresh_token=replacement_token,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    async def logout(self, refresh_token: str) -> None:
        payload = self._decode_refresh_payload(refresh_token)
        user_id = token_subject(payload)
        jti = refresh_jti(payload)
        token_hash = hash_token_identifier(jti)

        async with self.session.begin():
            token_record = await self._get_refresh_token_for_update(token_hash)
            now = datetime.now(UTC)
            if (
                token_record is None
                or token_record.user_id != user_id
                or token_record.revoked_at is not None
                or token_record.expires_at <= now
            ):
                raise AuthenticationError(
                    "invalid_refresh_token", "Refresh token is invalid or revoked."
                )
            token_record.revoked_at = now

    async def authenticate_access_token(self, token: str) -> User:
        try:
            payload = decode_token(token, self.settings)
            require_token_type(payload, "access")
            user_id = token_subject(payload)
        except TokenError as exc:
            raise AuthenticationError(exc.code, exc.message) from exc
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("invalid_token", "Token subject is invalid.")
        return user

    async def _issue_tokens(self, user_id: UUID) -> TokenPair:
        now = datetime.now(UTC)
        access_token = create_access_token(user_id, self.settings)
        refresh_token, jti = create_refresh_token(user_id, self.settings)
        self.session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_token_identifier(jti),
                expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
            )
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    async def _get_user_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return result.scalar_one_or_none()

    def _decode_refresh_payload(self, token: str) -> dict[str, object]:
        try:
            payload = decode_token(token, self.settings)
            require_token_type(payload, "refresh")
        except TokenError as exc:
            raise AuthenticationError(exc.code, exc.message) from exc
        return payload
