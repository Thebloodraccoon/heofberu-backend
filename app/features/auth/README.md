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

- `router.py` — thin endpoints; all logic delegates to `AuthService`.
- `service.py` — `AuthService`: credential verification (with a dummy bcrypt
  hash to equalize timing for unknown emails), registration (always `PLAYER`,
  generic duplicate error so account existence never leaks), refresh
  (checks the blacklist but does not rotate the refresh token), logout
  (blacklists both tokens). Also owns `REFRESH_COOKIE_NAME`.
- `dependencies.py` — `AuthServiceDep` (built on `DatabaseDep`).
- `schemas.py` — `LoginRequest`/`RegisterRequest` and their responses;
  validation mirrors the users schemas without importing them (so no `role`
  field can slip into self-registration).
- `exceptions.py` — `AccountAlreadyExistsException` (400, deliberately generic).

## Auth Model

- `register`, `login`, `refresh` are open endpoints.
- `logout` requires a valid, non-blacklisted access token (`CurrentUserDep`),
  with the raw bearer credentials additionally passed as `TokenDep` for the
  service to verify and blacklist.

Auth dependencies themselves (`TokenDep`/`CurrentUserDep`) live in
`app/features/users/security.py`, not here.
