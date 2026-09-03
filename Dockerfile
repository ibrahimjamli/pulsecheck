# syntax=docker/dockerfile:1.9

# ---------------------------------------------------------------------------
# Stage 1: build a self-contained virtualenv.
# Compilers and headers live only here, so none of them reach the runtime
# image. Wheels are cached across builds via BuildKit's cache mount.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only the dependency manifest first: application edits then leave this
# layer cached, which is the difference between a 4-second and a 90-second build.
COPY pyproject.toml README.md ./
COPY app ./app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install ".[postgres]"

# Strip the packaging toolchain out of the virtualenv before it is copied into
# the runtime image. Nothing needs pip or setuptools to *run* the application,
# and both keep appearing in vulnerability scans in their own right: pip
# vendors msgpack, and setuptools has its own history of path-traversal
# advisories. Removing them takes the whole class of finding out of the shipped
# image rather than suppressing it.
RUN pip uninstall --yes setuptools wheel && \
    rm -rf /opt/venv/lib/python*/site-packages/pip \
           /opt/venv/lib/python*/site-packages/pip-*.dist-info \
           /opt/venv/bin/pip*

# ---------------------------------------------------------------------------
# Stage 2: runtime. Slim base, no build tooling, unprivileged user.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# OCI labels let `docker inspect` and registry UIs trace an image back to the
# exact commit that produced it.
ARG VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="pulsecheck" \
      org.opencontainers.image.description="Uptime-monitoring API" \
      org.opencontainers.image.source="https://github.com/ibrahimjamli/pulsecheck" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# curl is needed by the HEALTHCHECK below; the rest of the apt cache is dropped
# in the same layer so it never lands in the image.
RUN apt-get update && \
    apt-get install --no-install-recommends -y curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --no-create-home app

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app app ./app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
