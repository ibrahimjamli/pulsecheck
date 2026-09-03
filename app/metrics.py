"""Prometheus instrumentation.

Exposed at /metrics in the OpenMetrics text format so a Prometheus server
(or the kube-prometheus stack) can scrape the pod directly.
"""

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "pulsecheck_http_requests_total",
    "HTTP requests served, by method, route template and status class.",
    ["method", "route", "status"],
)

HTTP_LATENCY = Histogram(
    "pulsecheck_http_request_duration_seconds",
    "Wall-clock time spent serving an HTTP request.",
    ["method", "route"],
)

PROBES = Counter(
    "pulsecheck_probes_total",
    "Outbound uptime probes performed, by result.",
    ["result"],
)

PROBE_LATENCY = Histogram(
    "pulsecheck_probe_duration_seconds",
    "Wall-clock time spent probing a monitored endpoint.",
)


async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    response = await call_next(request)

    # Label on the route template ("/api/v1/monitors/{monitor_id}") rather than
    # the raw path, otherwise every id becomes its own time series.
    route = request.scope.get("route")
    template = getattr(route, "path", request.url.path)

    HTTP_LATENCY.labels(request.method, template).observe(time.perf_counter() - started)
    HTTP_REQUESTS.labels(request.method, template, f"{response.status_code // 100}xx").inc()
    return response


def render_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
