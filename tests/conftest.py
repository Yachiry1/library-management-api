from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires PostgreSQL")


@pytest.fixture(scope="session")
def require_postgres() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def migrated_database(require_postgres: str) -> str:
    alembic_config = Config("alembic.ini")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    return require_postgres


@pytest.fixture
async def client(migrated_database: str) -> AsyncGenerator[AsyncClient]:
    from app.core.config import get_settings
    from app.db.session import get_db_session
    from app.main import app

    get_settings.cache_clear()
    engine = create_async_engine(migrated_database, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                TRUNCATE TABLE
                    import_jobs,
                    refresh_tokens,
                    books,
                    authors,
                    users
                RESTART IDENTITY CASCADE
                """
            )
        )

    async def override_get_db_session() -> AsyncGenerator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/auth/register",
        json={"email": "reader@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
