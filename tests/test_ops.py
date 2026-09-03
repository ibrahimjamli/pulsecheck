"""Operational endpoints: the ones Kubernetes and Prometheus depend on."""

import httpx


async def test_healthz_reports_version_and_environment(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["version"]


async def test_readyz_passes_when_database_reachable(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_metrics_exposes_prometheus_text_format(client: httpx.AsyncClient) -> None:
    await client.get("/healthz")  # generate at least one sample
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "pulsecheck_http_requests_total" in response.text


async def test_request_metrics_use_route_template_not_raw_path(
    client: httpx.AsyncClient, monitor_id: int
) -> None:
    await client.get(f"/api/v1/monitors/{monitor_id}")
    body = (await client.get("/metrics")).text
    # The id must not leak into a label, or cardinality grows without bound.
    assert 'route="/api/v1/monitors/{monitor_id}"' in body
    assert f'route="/api/v1/monitors/{monitor_id}"' not in body
