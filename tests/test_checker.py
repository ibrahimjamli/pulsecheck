"""Probe classification. Outbound HTTP is mocked, so the suite makes no
network calls and stays deterministic in CI."""

import httpx
import pytest
import respx

from app.checker import probe


@respx.mock
async def test_matching_status_is_up() -> None:
    respx.get("https://ok.test").mock(return_value=httpx.Response(200))
    result = await probe("https://ok.test", expected_status=200)
    assert result.up is True
    assert result.status_code == 200
    assert result.latency_ms is not None
    assert result.error is None


@respx.mock
async def test_unexpected_status_is_down_with_a_reason() -> None:
    respx.get("https://oops.test").mock(return_value=httpx.Response(500))
    result = await probe("https://oops.test", expected_status=200)
    assert result.up is False
    assert result.status_code == 500
    assert result.error == "expected 200, got 500"


@respx.mock
async def test_a_monitor_may_expect_a_non_200_status() -> None:
    respx.get("https://gone.test").mock(return_value=httpx.Response(404))
    result = await probe("https://gone.test", expected_status=404)
    assert result.up is True


@respx.mock
async def test_timeout_is_reported_without_raising() -> None:
    respx.get("https://slow.test").mock(side_effect=httpx.ConnectTimeout("too slow"))
    result = await probe("https://slow.test", expected_status=200)
    assert result.up is False
    assert result.status_code is None
    assert "timeout" in result.error


@respx.mock
async def test_connection_error_is_reported_without_raising() -> None:
    respx.get("https://dead.test").mock(side_effect=httpx.ConnectError("refused"))
    result = await probe("https://dead.test", expected_status=200)
    assert result.up is False
    assert "ConnectError" in result.error


@respx.mock
@pytest.mark.parametrize("code", [200, 201, 301, 404, 503])
async def test_probe_records_whatever_status_it_saw(code: int) -> None:
    respx.get("https://any.test").mock(return_value=httpx.Response(code))
    result = await probe("https://any.test", expected_status=code)
    assert result.status_code == code
    assert result.up is True
