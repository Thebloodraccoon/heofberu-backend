# Users Feature

## Purpose

User accounts and role management, plus the app-wide authentication
dependencies. Roles come from `app.constants.UserRole`:
`PLAYER` < `GM` < `FOUND_FATHER` (founder). A seeded default admin
(`settings.ADMIN_LOGIN`) is protected from update/delete.

## Endpoints (`router.py`, prefix `/users`, tag `Users`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/users` | GM | Paginated list (`page`/`size`/`role`/`search`). |
| GET    | `/users/me` | Any authenticated | Current user's own profile. |
| PUT    | `/users/me` | Any authenticated | Update own profile (`UserProfileUpdate`); never touches `role`. |
| GET    | `/users/{user_id}` | GM | Fetch any user by ID. |
| POST   | `/users` | GM (non-PLAYER role: founder) | Create a user with password hashing. |
| PUT    | `/users/{user_id}` | GM (role change: founder) | Update any user; blocked for the default admin. |
| DELETE | `/users/{user_id}` | Founder | Delete a user; cannot delete yourself or the default admin. |

## Structure

- `router.py` — thin endpoints; all logic delegates to `UserService`.
- `service.py` — `UserService` (extends `BaseService`): password hashing on
  create, founder gate on every role assignment, default-admin protection,
  self-deletion guard, lookup by email.
- `repository.py` — `UserRepository` (extends `BaseRepository`): search on
  username/email, uniqueness on username/email, `get_by_email`,
  `get_by_username`, `update_last_login`.
- `dependencies.py` — `UserServiceDep` (built on `DatabaseDep`).
- `schemas.py` — `ProfileFields` (shared validators), `UserCreate`,
  `UserUpdate`, `UserProfileUpdate` (`extra="forbid"`, no `role`),
  `UserResponse`.
- `security.py` — the app-wide auth dependencies (kept here because resolving
  the current user needs the users service, keeping `app/core` feature-free):
  - `TokenDep` — raw bearer credentials (`HTTPBearer`, optional).
  - `CurrentUserDep` — verifies signature/expiry, rejects blacklisted tokens,
    resolves the user via `UserService.get_user_by_email`.
  - `GmUserDep` — `CurrentUserDep` requiring `GM` or `FOUND_FATHER`.
  - `FounderDep` — `CurrentUserDep` requiring `FOUND_FATHER`.
- `exceptions.py` — `UserNotFoundException` (404), `InvalidPasswordException`
  (400), `DefaultUserProtectedException` (403), `SelfDeletionException` (403).

## Auth Model

Everything except `/users/me` (GET/PUT) is GM-only; role assignment is
founder-only everywhere; deletion is founder-only. The `/users/me` pair is
self-service for any authenticated caller.
