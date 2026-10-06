# Admin Feature

## Purpose

Founder-level maintenance operations that do not belong to any domain
feature. Currently only a full cache flush.

## Endpoints (`router.py`, prefix `/admin`, tag `Admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| DELETE | `/admin/cache` | Founder | Flushes every cached entry under the app's cache prefix (via `app.core.cache.flush_all`). Best-effort; JWT blacklist keys and other Redis data are preserved. Returns 204. |

## Structure

A single flat `router.py` — no service or repository layer; the endpoint
calls the core cache helper directly. Authorization uses `FounderDep`
from `app/features/users/security.py`.

## Auth Model

**Founder only.** Any other role (including GM) gets 403.
