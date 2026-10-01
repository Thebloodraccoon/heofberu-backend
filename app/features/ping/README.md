# Ping Feature

## Purpose

Liveness/health check for load balancers and uptime probes. Touches no
external services (no DB, no Redis).

## Endpoints (`router.py`, prefix `/ping`, tag `Health Check`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/ping` | Open | Returns `{"ping": "pong", "timestamp": ..., "status": "healthy"}` with the current epoch time. |

The probe is versioned with the rest of the API (`/api/v1/ping`); it is excluded from request
logging and rate limiting (`HEALTH_SKIP_PATHS`) and used by the Docker `HEALTHCHECK`.

## Structure

A single flat `router.py` — no service, repository, schemas, or exceptions.
No authentication of any kind.
