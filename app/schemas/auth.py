from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import StrictRequest
from app.schemas.user import UserRead


class RegisterRequest(StrictRequest):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(StrictRequest):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class RefreshRequest(StrictRequest):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(StrictRequest):
    refresh_token: str = Field(min_length=1)


class AuthResponse(TokenPair):
    user: UserRead
