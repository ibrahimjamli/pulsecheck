"""CRUD behaviour of the monitors resource."""

import httpx


async def test_create_returns_201_and_echoes_the_monitor(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/monitors", json={"name": "docs", "url": "https://example.com/docs"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "docs"
    assert body["expected_status"] == 200  # default applied
    assert body["id"] > 0


async def test_create_rejects_a_non_http_url(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/monitors", json={"name": "bad", "url": "ftp://x"})
    assert response.status_code == 422


async def test_create_rejects_an_out_of_range_expected_status(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/monitors",
        json={"name": "bad", "url": "https://example.com", "expected_status": 999},
    )
    assert response.status_code == 422


async def test_list_is_empty_before_anything_is_created(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/monitors")
    assert response.status_code == 200
    assert response.json() == []


async def test_get_returns_the_created_monitor(client: httpx.AsyncClient, monitor_id: int) -> None:
    response = await client.get(f"/api/v1/monitors/{monitor_id}")
    assert response.status_code == 200
    assert response.json()["id"] == monitor_id


async def test_get_unknown_monitor_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/monitors/424242")).status_code == 404


async def test_delete_removes_the_monitor(client: httpx.AsyncClient, monitor_id: int) -> None:
    assert (await client.delete(f"/api/v1/monitors/{monitor_id}")).status_code == 204
    assert (await client.get(f"/api/v1/monitors/{monitor_id}")).status_code == 404


async def test_delete_unknown_monitor_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.delete("/api/v1/monitors/424242")).status_code == 404
