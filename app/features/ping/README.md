# Ping Feature

## Purpose

Liveness (`/ping`, no external services) and readiness (`/ready`, DB + Redis) checks for load balancers,
orchestrators and uptime probes.

## Endpoints (`router.py`, tag `Health Check`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/ping` | Open | Returns `{"ping": "pong", "timestamp": ..., "status": "healthy"}` with the current epoch time. Liveness only. |
| GET | `/api/v1/ready` | Open | `SELECT 1` on the DB plus `PING` on the cache and auth Redis. `200 {"status": "ready", "checks": {...}}`, or `503 {"status": "unavailable", ...}` with `ok`/`fail` per dependency (causes are logged, never returned). |

The probe is versioned with the rest of the API (`/api/v1/ping`); both probes are excluded from request
logging and rate limiting (`HEALTH_SKIP_PATHS`). The Docker `HEALTHCHECK` stays on `/ping` (liveness): a Redis blip must not
restart the container; point orchestrator readiness probes at `/ready`.

## Structure

A single flat `router.py` — no service, repository, schemas, or exceptions.
No authentication of any kind.
