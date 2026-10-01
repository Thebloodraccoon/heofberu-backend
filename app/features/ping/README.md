# Ping Feature

## Purpose

Liveness/health check for load balancers and uptime probes. Touches no
external services (no DB, no Redis).

## Endpoints (`router.py`, prefix `/ping`, tag `Health Check`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ping` | Open | Returns `{"ping": "pong", "timestamp": ..., "status": "healthy"}` with the current epoch time. |

## Structure

A single flat `router.py` — no service, repository, schemas, or exceptions.
No authentication of any kind.
