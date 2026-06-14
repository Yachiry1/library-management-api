import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_checks(client: AsyncClient) -> None:
    live = await client.get("/health/live")
    assert live.status_code == 200

    ready = await client.get("/health/ready")
    assert ready.status_code == 200
