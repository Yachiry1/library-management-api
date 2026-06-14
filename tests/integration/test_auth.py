from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings

pytestmark = pytest.mark.integration


async def test_registration_login_me_and_refresh(client: AsyncClient) -> None:
    register = await client.post(
        "/auth/register",
        json={"email": "Reader@Example.com", "password": "correct horse battery staple"},
    )
    assert register.status_code == 201, register.text

    login = await client.post(
        "/auth/login",
        json={"email": "reader@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()

    me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "reader@example.com"

    refresh = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 200, refresh.text
    assert refresh.json()["refresh_token"] != tokens["refresh_token"]

    reused = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401


async def test_refresh_rejects_expired_invalid_and_access_tokens(client: AsyncClient) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000000",
            "jti": "expired",
            "type": "refresh",
            "iat": int((now - timedelta(days=2)).timestamp()),
            "exp": int((now - timedelta(days=1)).timestamp()),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired_response = await client.post("/auth/refresh", json={"refresh_token": expired})
    assert expired_response.status_code == 401

    registered = await client.post(
        "/auth/register",
        json={"email": "access@example.com", "password": "correct horse battery staple"},
    )
    access_token = registered.json()["access_token"]
    wrong_type = await client.post("/auth/refresh", json={"refresh_token": access_token})
    assert wrong_type.status_code == 401

    invalid = await client.post("/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert invalid.status_code == 401


async def test_logout_token_cases(client: AsyncClient) -> None:
    registered = await client.post(
        "/auth/register",
        json={"email": "logout@example.com", "password": "correct horse battery staple"},
    )
    tokens = registered.json()

    access_logout = await client.post(
        "/auth/logout",
        json={"refresh_token": tokens["access_token"]},
    )
    assert access_logout.status_code == 401

    logout = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 200

    revoked = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert revoked.status_code == 401

    malformed = await client.post("/auth/logout", json={"refresh_token": "nope"})
    assert malformed.status_code == 401


async def test_concurrent_refresh_only_one_succeeds(client: AsyncClient) -> None:
    registered = await client.post(
        "/auth/register",
        json={"email": "race@example.com", "password": "correct horse battery staple"},
    )
    refresh_token = registered.json()["refresh_token"]

    responses = await asyncio.gather(
        client.post("/auth/refresh", json={"refresh_token": refresh_token}),
        client.post("/auth/refresh", json={"refresh_token": refresh_token}),
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 401]
