# Users Feature

## Purpose

User accounts and role management (profile, CRUD, role edits). Authentication
and the shared current-user/role-guard dependencies live in `app/features/auth`. Roles come from `app.constants.UserRole`:
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

- `router.py` — thin endpoints; all logic delegates to `UserService`. Guards come from `app/features/auth/dependencies.py`.
- `service.py` — `UserService` (extends `BaseService`): password hashing on create, founder gate on role assignment, only the founder edits non-player accounts, default-admin protection, self-deletion guard. `get_auth_user(user_id)` is the cached per-request lookup (TTL 5 min) behind `CurrentUserDep`; `user_cache_key`/`invalidate_user_cache` give point invalidation after every write (role change, profile edit, delete, login); deleting a user also purges cached articles (`author_id`). Covered by `tests/integration/features/users/test_cache.py`, including a Redis outage during the purge. `resolve_subject_id` maps a token `sub` (id, or legacy email) to a user id.
- `repository.py` — `UserRepository`: search, case-insensitive email lookup/uniqueness, `get_by_subject`, `update_last_login`.
- `validators.py` — the single definition of user-field rules (`Email`, `Username`, `NewPassword`, `Bio`, `ContactField`, `normalize_email`).
- `dependencies.py` — `UserServiceDep`.
- `schemas.py` — `UserCreate`, `UserUpdate` (`extra="forbid"`), `UserProfileUpdate` (no `role`), `UserResponse`.
- `exceptions.py` — `UserNotFoundException` (404), `InvalidPasswordException` (400), `DefaultUserProtectedException` (403), `SelfDeletionException` (403).

## Auth Model

Everything except `/users/me` (GET/PUT) is GM-only; role assignment is
founder-only everywhere; deletion is founder-only. The `/users/me` pair is
self-service for any authenticated caller.
