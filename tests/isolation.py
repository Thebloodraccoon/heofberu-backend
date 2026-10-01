"""
Per-process test isolation (Postgres database + Redis key namespace).

Must stay importable WITHOUT importing ``app``: ``tests/conftest.py`` calls
``configure_environment()`` before the app (and therefore ``app.settings.test``,
which reads ``TEST_DATABASE_URL`` / ``CACHE_PREFIX`` at import time) is loaded.

Identity of a process = (run id, xdist worker id):

* run id    -- env ``TEST_RUN_ID`` or a random id generated once by the
               top-level pytest process and inherited by its xdist workers;
* worker id -- ``PYTEST_XDIST_WORKER`` (``gw0``...) or ``main`` without xdist.

Postgres: every process gets its own database ``heof_test_<run>_<worker>``,
cloned (``CREATE DATABASE ... TEMPLATE``) from a template database that holds
the migrated schema. The template is named after a hash of the migration
files, built once (Alembic in a subprocess) under a cross-process advisory
lock and reused by later runs. The worker database is dropped at session end.

Redis: one shared DB, per-process key namespace -- ``CACHE_PREFIX`` is
``cache_<run>_<worker>`` and the test HTTP client uses a unique client IP
(``rate_limit:<ip>:...`` keys). Teardown deletes only those keys.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATABASE_URL = "postgresql://heof_user:test_secret@localhost:5433/heof_test_db"
DEFAULT_REDIS_URL = "redis://localhost:6381/0"

_LOCK_KEY = 0x48454F46  # advisory lock shared by every test process on this server
_RUN_COMMENT = "heof-pytest-run:"
_TPL_COMMENT = "heof-pytest-template:"
_STALE_RUN_DB_SECONDS = 6 * 3600  # leaked worker DBs (killed runs) are pruned after this
_STALE_TEMPLATE_SECONDS = 24 * 3600


def _clean(value: str, limit: int) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())[:limit] or "x"


class Identity:
    run_id: str
    worker: str
    tag: str
    db_name: str
    base_url: str
    db_url: str
    cache_prefix: str
    client_ip: str


def _compute() -> Identity:
    ident = Identity()
    run_id = os.environ.get("TEST_RUN_ID") or uuid.uuid4().hex[:8]
    # Exported so xdist workers (child processes) share the controller's id.
    os.environ["TEST_RUN_ID"] = run_id
    ident.run_id = _clean(run_id, 16)
    ident.worker = _clean(os.environ.get("PYTEST_XDIST_WORKER") or "main", 8)
    ident.tag = f"{ident.run_id}_{ident.worker}"
    ident.db_name = f"heof_test_{ident.tag}"

    # Original (admin) URL survives the TEST_DATABASE_URL rewrite below, so workers
    # inheriting the controller's env do not derive from an already-rewritten URL.
    base = os.environ.setdefault("TEST_BASE_DATABASE_URL", os.environ.get("TEST_DATABASE_URL") or DEFAULT_DATABASE_URL)
    ident.base_url = base
    ident.db_url = _with_db(base, ident.db_name)
    ident.cache_prefix = f"cache_{ident.tag}"
    ident.client_ip = f"t-{ident.tag}"
    return ident


def _with_db(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{db_name}"))


IDENTITY: Identity | None = None


def configure_environment() -> Identity:
    """Set STAGE / TEST_* / CACHE_PREFIX env for this process. Call before importing ``app``."""
    global IDENTITY
    os.environ["STAGE"] = "test"
    os.environ.setdefault("TEST_REDIS_URL", DEFAULT_REDIS_URL)
    ident = _compute()
    os.environ["TEST_DATABASE_URL"] = ident.db_url
    os.environ["CACHE_PREFIX"] = ident.cache_prefix
    IDENTITY = ident
    return ident


# --------------------------------------------------------------------------- Postgres


def _admin_connection():
    import psycopg2

    assert IDENTITY is not None
    conn = psycopg2.connect(IDENTITY.base_url)
    conn.autocommit = True
    return conn


def _migrations_hash() -> str:
    digest = hashlib.sha1()
    paths = sorted((ROOT / "migrations" / "versions").glob("*.py")) + [ROOT / "migrations" / "env.py"]
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _db_comment(cur, name: str) -> str | None:
    cur.execute(
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
        (name,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
    return cur.fetchone() is not None


def _drop(cur, name: str) -> None:
    cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _prune(cur, current_template: str) -> None:
    now = time.time()
    cur.execute(
        "SELECT datname, shobj_description(oid, 'pg_database') FROM pg_database WHERE datname LIKE 'heof_test_%'"
    )
    for name, comment in cur.fetchall():
        if not comment:
            continue
        try:
            if (
                comment.startswith(_RUN_COMMENT)
                and now - float(comment[len(_RUN_COMMENT) :]) > _STALE_RUN_DB_SECONDS
                or (
                    comment.startswith(_TPL_COMMENT)
                    and name != current_template
                    and now - float(comment[len(_TPL_COMMENT) :].split(":")[-1]) > _STALE_TEMPLATE_SECONDS
                )
            ):
                _drop(cur, name)
        except ValueError:
            continue


def _build_template(cur, template: str) -> None:
    cur.execute(f'CREATE DATABASE "{template}"')
    assert IDENTITY is not None
    env = {
        "ADMIN_LOGIN": "admin@example.com",
        "ADMIN_NAME": "admin",
        "ADMIN_PASSWORD": "migration-test-password",
        **os.environ,
        "STAGE": "test",
        "TEST_DATABASE_URL": _with_db(IDENTITY.base_url, template),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _drop(cur, template)
        raise RuntimeError(f"alembic upgrade failed for template {template}:\n{result.stdout}\n{result.stderr}")
    cur.execute(f"COMMENT ON DATABASE \"{template}\" IS '{_TPL_COMMENT}ready:{time.time()}'")


def create_worker_database() -> None:
    """Create this process's DB from the (lazily built) migrated template."""
    assert IDENTITY is not None
    template = f"heof_test_tpl_{_migrations_hash()}"
    conn = _admin_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            comment = _db_comment(cur, template)
            if comment is None or not comment.startswith(_TPL_COMMENT + "ready"):
                _drop(cur, template)  # half-built leftovers
                _build_template(cur, template)
            else:
                cur.execute(f"COMMENT ON DATABASE \"{template}\" IS '{_TPL_COMMENT}ready:{time.time()}'")
            _prune(cur, template)
            _drop(cur, IDENTITY.db_name)  # same run id reused after a crash
            cur.execute(f'CREATE DATABASE "{IDENTITY.db_name}" TEMPLATE "{template}"')
            cur.execute(f"COMMENT ON DATABASE \"{IDENTITY.db_name}\" IS '{_RUN_COMMENT}{time.time()}'")
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    finally:
        conn.close()


def drop_worker_database() -> None:
    assert IDENTITY is not None
    try:
        conn = _admin_connection()
    except Exception:
        return
    try:
        _drop(conn.cursor(), IDENTITY.db_name)
    finally:
        conn.close()


# --------------------------------------------------------------------------- Redis


async def clear_redis_keys(client) -> None:
    """Delete only this process's keys (cache namespace, rate-limit buckets of its client IP, session revocation marks)."""
    assert IDENTITY is not None
    patterns = (
        f"{IDENTITY.cache_prefix}:*",
        f"rate_limit:{IDENTITY.client_ip}:*",
        f"auth_revoked_after:{IDENTITY.cache_prefix}:*",
    )
    for pattern in patterns:
        keys = [key async for key in client.scan_iter(match=pattern, count=500)]
        if keys:
            await client.delete(*keys)
