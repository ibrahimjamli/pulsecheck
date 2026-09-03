"""The check-running endpoint, with the outbound probe mocked."""

import httpx
import respx


@respx.mock
async def test_running_a_check_persists_the_result(
    client: httpx.AsyncClient, monitor_id: int
) -> None:
    respx.get("https://example.com").mock(return_value=httpx.Response(200))

    response = await client.post(f"/api/v1/monitors/{monitor_id}/check")
    assert response.status_code == 201
    body = response.json()
    assert body["up"] is True
    assert body["status_code"] == 200
    assert body["monitor_id"] == monitor_id

    history = await client.get(f"/api/v1/monitors/{monitor_id}/checks")
    assert history.status_code == 200
    assert len(history.json()) == 1


@respx.mock
async def test_a_failing_target_is_recorded_not_raised(
    client: httpx.AsyncClient, monitor_id: int
) -> None:
    respx.get("https://example.com").mock(return_value=httpx.Response(502))

    response = await client.post(f"/api/v1/monitors/{monitor_id}/check")
    assert response.status_code == 201  # the API call succeeded
    assert response.json()["up"] is False  # the target did not


@respx.mock
async def test_check_history_is_newest_first_and_respects_limit(
    client: httpx.AsyncClient, monitor_id: int
) -> None:
    respx.get("https://example.com").mock(return_value=httpx.Response(200))
    for _ in range(3):
        await client.post(f"/api/v1/monitors/{monitor_id}/check")

    history = (await client.get(f"/api/v1/monitors/{monitor_id}/checks?limit=2")).json()
    assert len(history) == 2
    assert history[0]["id"] > history[1]["id"]


async def test_checking_an_unknown_monitor_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/monitors/424242/check")).status_code == 404


async def test_history_for_an_unknown_monitor_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/monitors/424242/checks")).status_code == 404


@respx.mock
async def test_deleting_a_monitor_also_removes_its_checks(
    client: httpx.AsyncClient, monitor_id: int
) -> None:
    respx.get("https://example.com").mock(return_value=httpx.Response(200))
    await client.post(f"/api/v1/monitors/{monitor_id}/check")
    assert (await client.delete(f"/api/v1/monitors/{monitor_id}")).status_code == 204
    assert (await client.get(f"/api/v1/monitors/{monitor_id}/checks")).status_code == 404
