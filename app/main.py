"""HTTP surface.

Three groups of endpoints:
  * /healthz and /readyz  - container probes, no auth, no database on liveness
  * /metrics              - Prometheus scrape target
  * /api/v1/...           - the actual monitoring API
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.checker import probe
from app.config import get_settings
from app.db import dispose_engine, get_session, init_models
from app.metrics import metrics_middleware, render_metrics
from app.models import Check, Monitor
from app.schemas import CheckOut, HealthOut, MonitorCreate, MonitorOut

logger = logging.getLogger("pulsecheck")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("starting pulsecheck %s in %s", __version__, settings.environment)
    await init_models()
    yield
    await dispose_engine()
    logger.info("pulsecheck stopped")


app = FastAPI(
    title="pulsecheck",
    version=__version__,
    summary="Uptime-monitoring API",
    lifespan=lifespan,
)
app.middleware("http")(metrics_middleware)


# --- operational endpoints ------------------------------------------------


@app.get("/healthz", response_model=HealthOut, tags=["ops"])
async def healthz() -> HealthOut:
    """Liveness. Deliberately touches nothing external: if this fails the
    process is wedged and Kubernetes should restart it."""
    settings = get_settings()
    return HealthOut(status="ok", version=__version__, environment=settings.environment)


@app.get("/readyz", tags=["ops"])
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness. Fails while the database is unreachable so traffic is held
    back instead of erroring, without restarting the pod."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator as 503
        logger.warning("readiness probe failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    return {"status": "ready"}


@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics():  # noqa: ANN201 - returns a raw text/plain Response
    return render_metrics()


# --- monitors -------------------------------------------------------------


@app.post(
    "/api/v1/monitors",
    response_model=MonitorOut,
    status_code=status.HTTP_201_CREATED,
    tags=["monitors"],
)
async def create_monitor(
    payload: MonitorCreate, session: AsyncSession = Depends(get_session)
) -> Monitor:
    monitor = Monitor(**payload.model_dump())
    session.add(monitor)
    await session.commit()
    await session.refresh(monitor)
    return monitor


@app.get("/api/v1/monitors", response_model=list[MonitorOut], tags=["monitors"])
async def list_monitors(session: AsyncSession = Depends(get_session)) -> list[Monitor]:
    result = await session.execute(select(Monitor).order_by(Monitor.id))
    return list(result.scalars().all())


@app.get("/api/v1/monitors/{monitor_id}", response_model=MonitorOut, tags=["monitors"])
async def get_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)) -> Monitor:
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    return monitor


@app.delete(
    "/api/v1/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["monitors"],
)
async def delete_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)) -> None:
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    # Checks are removed by the relationship cascade (all, delete-orphan).
    await session.delete(monitor)
    await session.commit()


# --- checks ---------------------------------------------------------------


@app.post(
    "/api/v1/monitors/{monitor_id}/check",
    response_model=CheckOut,
    status_code=status.HTTP_201_CREATED,
    tags=["checks"],
)
async def run_check(monitor_id: int, session: AsyncSession = Depends(get_session)) -> Check:
    """Probe the monitor now and persist the outcome."""
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="monitor not found")

    result = await probe(monitor.url, monitor.expected_status)
    check = Check(
        monitor_id=monitor.id,
        status_code=result.status_code,
        latency_ms=result.latency_ms,
        up=result.up,
        error=result.error,
    )
    session.add(check)
    await session.commit()
    await session.refresh(check)
    return check


@app.get(
    "/api/v1/monitors/{monitor_id}/checks",
    response_model=list[CheckOut],
    tags=["checks"],
)
async def list_checks(
    monitor_id: int, limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[Check]:
    if await session.get(Monitor, monitor_id) is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    result = await session.execute(
        select(Check)
        .where(Check.monitor_id == monitor_id)
        .order_by(desc(Check.checked_at), desc(Check.id))
        .limit(min(max(limit, 1), 500))
    )
    return list(result.scalars().all())
