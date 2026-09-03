"""Test fixtures.

Each test gets its own throwaway SQLite file so cases cannot see one
another's rows. The app is exercised through an in-process ASGI transport,
so the suite needs no listening socket and no container.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app import config, db


@pytest.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("PULSECHECK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PULSECHECK_ENVIRONMENT", "test")
    config.get_settings.cache_clear()
    await db.dispose_engine()

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    # Entering the lifespan runs init_models() against the fresh database.
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as http_client,
        app.router.lifespan_context(app),
    ):
        yield http_client

    await db.dispose_engine()
    config.get_settings.cache_clear()


@pytest.fixture
async def monitor_id(client: httpx.AsyncClient) -> int:
    response = await client.post(
        "/api/v1/monitors",
        json={"name": "example", "url": "https://example.com", "expected_status": 200},
    )
    assert response.status_code == 201
    return int(response.json()["id"])
