# Auth Feature

## Purpose

Authentication for the Heofberu backend: self-registration, login, logout,
and access-token refresh. Issues JWT access tokens (returned in the response
body) and refresh tokens (set as an `httponly` cookie), and revokes both on
logout via the Redis token blacklist in `app/core/security/token.py`.

## Endpoints (`router.py`, prefix `/auth`, tag `Auth`)

| Method | Path        | Auth     | Description |
|--------|-------------|----------|-------------|
| POST   | `/auth/register` | Open | Self-register; account is always `PLAYER`; logs the caller in immediately. 400 on duplicate email/username, weak password, or invalid email. |
| POST   | `/auth/login`    | Open | Email + password login; returns a fresh token pair and sets the refresh cookie. 401 on bad credentials. |
| POST   | `/auth/logout`   | Valid access token | Blacklists the current access token and the refresh cookie (if present), clears the cookie client-side. |
| POST   | `/auth/refresh`  | Refresh cookie | Exchanges a valid, non-revoked refresh cookie for a new access token. 401 if missing/invalid/revoked. |

## Structure

- `router.py` — thin endpoints (`/auth/register|login|logout|refresh|forgot-password|reset-password`); all logic delegates to `AuthService`.
- `service.py` — `AuthService`: credential verification (dummy bcrypt hash equalizes timing for unknown emails), registration (always `PLAYER`), refresh with rotation (old `jti` claimed atomically, new cookie issued), logout (blacklists both tokens), password reset (single-use token, revokes the user's sessions). Also owns the refresh-cookie helpers and `REFRESH_COOKIE_NAME`. Token `sub` is the user id (legacy email subjects are still accepted).
- `sessions.py` — Redis session state: per-user revocation timestamp (`auth_revoked_after:*`), `is_session_revoked` (one `MGET` for blacklist + revocation), single-use `claim_token`/`release_token`. Stored on the dedicated `settings.get_auth_redis()` (noeviction, see `app/core/README.md`); fail-closed 503 when it is down. The reset email is queued with `add_safe_task`, so SMTP never blocks or fails the response.
- `dependencies.py` — the one place feature routers import auth from: `AuthServiceDep`, `TokenDep`, `CurrentUserDep`, `OptionalUserDep`, `GmUserDep`, `FounderDep`, `can_see_hidden`.
- `schemas.py` — request/response models and the login-only password constraint (`LoginPassword`); user-field rules come from `users/validators.py`.
- `exceptions.py` — `AccountAlreadyExistsException`, `InvalidResetTokenException`.

## Dependency direction

`auth` -> `users` (repository, service, schemas, validators) and `core/security` (JWT/password primitives, no business rules).
The users domain layers never import `auth`; only `users/router.py` imports the guards from `auth/dependencies.py`, like every other feature router.

## Auth Model

- `register`, `login`, `refresh`, `forgot-password`, `reset-password` are open endpoints.
- `logout` requires a valid, non-blacklisted access token (`CurrentUserDep`), with the raw bearer credentials also passed as `TokenDep` for the service to verify and blacklist.
