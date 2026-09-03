# pulsecheck

[![CI](https://github.com/ibrahimjamli/pulsecheck/actions/workflows/ci.yml/badge.svg)](https://github.com/ibrahimjamli/pulsecheck/actions/workflows/ci.yml)
[![Release](https://github.com/ibrahimjamli/pulsecheck/actions/workflows/release.yml/badge.svg)](https://github.com/ibrahimjamli/pulsecheck/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A small uptime-monitoring API, used as a vehicle for a complete delivery
pipeline: containerised, tested, scanned, signed, and deployed to a real
Kubernetes cluster on every push.

The service itself is deliberately modest, around 200 lines. Everything
interesting is in how it ships.

---

## What the pipeline does

Every pull request runs the following before it can merge:

| Stage | Tooling | Gate |
|---|---|---|
| Lint | Ruff | Any violation fails the build |
| Format | Ruff format | Diff from canonical format fails the build |
| Types | mypy | Any type error fails the build |
| Tests | pytest, Python 3.11 and 3.12 | Any failure fails the build |
| Coverage | coverage.py | Below 85% fails the build |
| Image build | Docker Buildx, layer cache on GHA | Build failure fails the build |
| Vulnerabilities | Trivy | Any fixable HIGH or CRITICAL fails the build |
| SBOM | Syft, SPDX JSON | Published as an artefact |
| Container smoke test | curl against the running image | Must answer `/healthz` and run as UID 10001 |
| Kubernetes deploy | kind, Kustomize | Rollout must succeed within 180s |
| Zero-downtime check | rolling restart under load | A single dropped request fails the build |

Tagging `v*.*.*` additionally builds for amd64 and arm64, pushes to the GitHub
Container Registry, signs the image with Cosign keylessly, attaches a build
provenance attestation, and cuts a GitHub Release.

## Why some of the choices were made

**Two-stage Dockerfile.** Compilers and headers exist only in the build stage.
The runtime image carries a virtualenv and the application, nothing else.
Dependencies are installed before the application is copied, so editing a
source file does not invalidate the dependency layer.

**Runs as UID 10001 with a read-only root filesystem.** The container drops
all capabilities and forbids privilege escalation. Anything that needs to
write gets an explicit `emptyDir`. CI asserts the running UID rather than
trusting the Dockerfile, because a stray `USER root` in a later edit would
otherwise pass silently.

**Liveness and readiness are different endpoints.** `/healthz` touches nothing
external. If it fails the process is wedged and restarting is correct.
`/readyz` pings the database, so a transient database problem removes the pod
from the Service without triggering a restart loop that would make things
worse.

**`maxUnavailable: 0` plus a readiness gate.** The pipeline proves this rather
than claiming it: it restarts the deployment while polling the endpoint twice a
second and fails if a single request is dropped.

That check earned its place on the first run, which dropped three requests. A
pod is removed from the Service endpoints and sent `SIGTERM` at the same
moment, but kube-proxy needs a moment to rewrite the node's iptables rules, so
traffic keeps arriving at a container that is already shutting down. The fix is
a `preStop` sleep that holds the container open through that window. Without
the test the deployment would have looked correct and quietly dropped requests
on every release.

**Metrics are labelled by route template.** `/api/v1/monitors/{monitor_id}`,
not `/api/v1/monitors/17`. Labelling by raw path would create one time series
per monitor id and eventually take down the Prometheus server. There is a test
asserting this specifically.

**Failing targets are recorded, not raised.** A monitored endpoint returning
502 is normal operation for a monitoring service. The API returns 201 with
`"up": false`; it does not return an error.

## The API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness probe |
| `GET` | `/readyz` | Readiness probe, checks the database |
| `GET` | `/metrics` | Prometheus scrape endpoint |
| `GET` | `/docs` | Generated OpenAPI documentation |
| `POST` | `/api/v1/monitors` | Register an endpoint to watch |
| `GET` | `/api/v1/monitors` | List monitors |
| `GET` | `/api/v1/monitors/{id}` | Fetch one monitor |
| `DELETE` | `/api/v1/monitors/{id}` | Remove a monitor and its history |
| `POST` | `/api/v1/monitors/{id}/check` | Probe now, store the result |
| `GET` | `/api/v1/monitors/{id}/checks` | Check history, newest first |

## Running it

The only prerequisite is Docker.

```bash
docker compose up --build -d
curl localhost:8000/healthz
```

That starts the API on port 8000, Postgres behind it, and Prometheus on
port 9090 already scraping the service.

Register something and probe it:

```bash
curl -X POST localhost:8000/api/v1/monitors \
  -H 'content-type: application/json' \
  -d '{"name":"github","url":"https://github.com"}'

curl -X POST localhost:8000/api/v1/monitors/1/check
```

### Without Docker

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/uvicorn app.main:app --reload
```

### On Kubernetes

```bash
make kind-up
make kind-deploy
curl localhost:30080/healthz
```

`make help` lists every target.

## Layout

```
app/            application, ~200 lines
  config.py     environment-driven settings
  db.py         async engine and session lifecycle
  models.py     SQLAlchemy models
  checker.py    outbound probing, isolated for testing
  metrics.py    Prometheus instrumentation
  main.py       HTTP routes
tests/          28 tests, 99% coverage, no network access
deploy/k8s/     Kustomize manifests
.github/        CI and release pipelines
```

## Testing approach

The suite makes no network calls and needs no container. Outbound HTTP is
intercepted with `respx`, and the app is driven through an in-process ASGI
transport, so the whole suite finishes in under ten seconds. Each test gets a
throwaway SQLite file, so no test can see another's rows.

## License

MIT. See [LICENSE](LICENSE).
