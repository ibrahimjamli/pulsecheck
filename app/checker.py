"""Outbound probing.

Isolated from the web layer so it can be unit-tested without a server and
reused later by a scheduled worker.
"""

import time
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.metrics import PROBE_LATENCY, PROBES


@dataclass(frozen=True)
class ProbeResult:
    up: bool
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None


async def probe(
    url: str, expected_status: int, client: httpx.AsyncClient | None = None
) -> ProbeResult:
    """Issue one GET and classify the outcome.

    A target is "up" only when it answers within the timeout *and* returns the
    status the monitor was created with. Anything else is recorded with a
    reason rather than raised, because a failing target is normal operation
    for this service, not an application error.
    """
    settings = get_settings()
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=settings.probe_timeout_seconds,
            follow_redirects=True,
            headers={"user-agent": settings.probe_user_agent},
        )

    started = time.perf_counter()
    try:
        response = await client.get(url)
        elapsed = time.perf_counter() - started
        PROBE_LATENCY.observe(elapsed)
        up = response.status_code == expected_status
        PROBES.labels("up" if up else "down").inc()
        return ProbeResult(
            up=up,
            status_code=response.status_code,
            latency_ms=round(elapsed * 1000, 2),
            error=None if up else f"expected {expected_status}, got {response.status_code}",
        )
    except httpx.TimeoutException:
        PROBE_LATENCY.observe(time.perf_counter() - started)
        PROBES.labels("timeout").inc()
        return ProbeResult(up=False, error=f"timeout after {settings.probe_timeout_seconds}s")
    except httpx.HTTPError as exc:
        PROBE_LATENCY.observe(time.perf_counter() - started)
        PROBES.labels("error").inc()
        return ProbeResult(up=False, error=f"{type(exc).__name__}: {exc}"[:500])
    finally:
        if owns_client:
            await client.aclose()
