"""
Migration chain tests, run against throw-away databases (never the per-process test database).

Parallel-safe like the rest of the suite: every database is named ``heof_test_mig_<run>_<worker>_...`` (so a
leaked one is pruned by ``tests/isolation.py``) and each test works on its own clone of one migrated base database.

* the chain has exactly one head and every ``down_revision`` resolves;
* ``upgrade head`` -> ``downgrade`` -> ``upgrade head`` round trip;
* the migrated schema equals the models: Alembic autogenerate reports no diff, and (what autogenerate cannot see)
  every index, CHECK constraint and generated column the models declare has the identical definition in the database;
* the data migrations behave as designed on representative legacy rows (nested GM block in the search index, email
  case-duplicates, duplicate feat names, ASI JSONB with duplicate abilities).
"""

import os
from pathlib import Path
import subprocess
import sys
import time

from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.schema import AddConstraint, CreateColumn, CreateIndex, DropConstraint, DropIndex

from app.models.articles.article_model import NESTED_GM_BLOCK_SQL_PATTERN
from app.settings import settings
from tests import isolation

ROOT = Path(__file__).resolve().parents[3]

#: The revisions added by this hardening pass and the last one before them.
BEFORE_HARDENING = "d6a2c8e4f0b1"
SEARCH_REVISION = "e7b2d4f6a8c0"
INDEX_REVISION = "f8c3e5a7b9d1"
INTEGRITY_REVISION = "a6d1f3b5c7e9"
ASI_REVISION = "b8e2f4a6c9d1"
BEFORE_ASI = "f9c6d8e2b4a7"

pytestmark = pytest.mark.integration


def _tag() -> str:
    assert isolation.IDENTITY is not None
    return f"heof_test_mig_{isolation.IDENTITY.tag}"


def _admin():
    assert isolation.IDENTITY is not None
    conn = psycopg2.connect(isolation.IDENTITY.base_url)
    conn.autocommit = True
    return conn


def _url(db_name: str) -> str:
    assert isolation.IDENTITY is not None
    return isolation._with_db(isolation.IDENTITY.base_url, db_name)


def _create_db(name: str, template: str | None = None) -> None:
    conn = _admin()
    try:
        cur = conn.cursor()
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{name}"' + (f' TEMPLATE "{template}"' if template else ""))
        cur.execute(f"COMMENT ON DATABASE \"{name}\" IS '{isolation._RUN_COMMENT}{time.time()}'")
    finally:
        conn.close()


def _drop_db(name: str) -> None:
    conn = _admin()
    try:
        conn.cursor().execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        conn.close()


def _alembic(db_name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "STAGE": "test",
        "TEST_DATABASE_URL": _url(db_name),
        # Revision 0003 seeds the default GM from these; harmless values for a throw-away database.
        "ADMIN_LOGIN": os.environ.get("ADMIN_LOGIN", "admin@example.com"),
        "ADMIN_NAME": os.environ.get("ADMIN_NAME", "admin"),
        "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD", "migration-test-password"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300
    )
    if check and result.returncode != 0:
        raise AssertionError(f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result


def _version(db_name: str) -> str:
    conn = psycopg2.connect(_url(db_name))
    try:
        cur = conn.cursor()
        cur.execute("SELECT version_num FROM alembic_version")
        return cur.fetchone()[0]
    finally:
        conn.close()


def _sql(db_name: str, statement: str, params: tuple = ()) -> list[tuple]:
    conn = psycopg2.connect(_url(db_name))
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(statement, params or None)
        return cur.fetchall() if cur.description else []
    finally:
        conn.close()


@pytest.fixture(scope="module")
def base_db():
    """A database migrated to head once per module; tests clone it."""

    name = f"{_tag()}_base"
    _create_db(name)
    try:
        _alembic(name, "upgrade", "head")
        yield name
    finally:
        _drop_db(name)


@pytest.fixture
def scratch_db(base_db, request):
    """A private clone of the migrated database, dropped after the test."""

    name = f"{_tag()}_{request.node.name[:30].lower().replace('[', '_').replace(']', '')}"
    _create_db(name, template=base_db)
    try:
        yield name
    finally:
        _drop_db(name)


class TestMigrationChain:
    def test_exactly_one_head_and_every_parent_resolves(self):
        script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

        assert len(script.get_heads()) == 1
        revisions = {revision.revision for revision in script.walk_revisions()}
        for revision in script.walk_revisions():
            parents = revision.down_revision
            for parent in (parents,) if isinstance(parents, str) else (parents or ()):
                assert parent in revisions, f"{revision.revision} points at the unknown revision {parent}"

    def test_hardening_revisions_chain_onto_the_previous_head(self):
        script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

        assert script.get_revision(SEARCH_REVISION).down_revision == BEFORE_HARDENING
        assert script.get_revision(INDEX_REVISION).down_revision == SEARCH_REVISION
        assert script.get_revision(INTEGRITY_REVISION).down_revision == INDEX_REVISION

    def test_model_and_migration_use_the_same_nested_gm_pattern(self):
        migration = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_revision(SEARCH_REVISION)
        source = Path(migration.path).read_text(encoding="utf-8")

        assert NESTED_GM_BLOCK_SQL_PATTERN in source


class TestRoundTrip:
    def test_upgrade_downgrade_upgrade(self, scratch_db):
        head = _version(scratch_db)

        _alembic(scratch_db, "downgrade", BEFORE_ASI)
        assert _version(scratch_db) == BEFORE_ASI
        _alembic(scratch_db, "upgrade", "head")

        assert _version(scratch_db) == head

    def test_hardening_revisions_step_down_and_up_one_by_one(self, scratch_db):
        head = _version(scratch_db)
        _alembic(scratch_db, "downgrade", INTEGRITY_REVISION)
        for current, parent in (
            (INTEGRITY_REVISION, INDEX_REVISION),
            (INDEX_REVISION, SEARCH_REVISION),
            (SEARCH_REVISION, BEFORE_HARDENING),
        ):
            assert _version(scratch_db) == current
            _alembic(scratch_db, "downgrade", "-1")
            assert _version(scratch_db) == parent

        _alembic(scratch_db, "upgrade", "head")
        assert _version(scratch_db) == head


class TestNoDrift:
    def test_autogenerate_reports_no_diff(self, scratch_db):
        result = _alembic(scratch_db, "check", check=False)

        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        assert "No new upgrade operations detected" in result.stdout + result.stderr

    def test_declared_indexes_checks_and_generated_columns_match_the_database(self, scratch_db):
        """What autogenerate does not compare: re-create each declared object from the model, expect identical DDL."""

        engine = sa.create_engine(_url(scratch_db))
        metadata = settings.Base.metadata
        mismatches: list[str] = []
        try:
            with engine.connect() as conn:
                transaction = conn.begin()
                dialect = conn.dialect

                def index_def(name: str) -> str | None:
                    return conn.execute(
                        sa.text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
                        {"n": name},
                    ).scalar()

                def check_def(table: str, name: str) -> str | None:
                    return conn.execute(
                        sa.text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid = to_regclass(:t) AND conname = :n AND contype = 'c'"
                        ),
                        {"t": table, "n": name},
                    ).scalar()

                declared_indexes: set[str] = set()
                declared_checks: set[tuple[str, str]] = set()
                for table in metadata.sorted_tables:
                    for index in table.indexes:
                        declared_indexes.add(index.name)
                        before = index_def(index.name)
                        if before is None:
                            mismatches.append(f"index {index.name} is declared on {table.name} but missing in the DB")
                            continue
                        conn.execute(DropIndex(index))
                        conn.execute(CreateIndex(index))
                        if index_def(index.name) != before:
                            mismatches.append(
                                f"index {index.name}: DB has {before!r}, model gives {index_def(index.name)!r}"
                            )

                    for constraint in table.constraints:
                        if not isinstance(constraint, sa.CheckConstraint) or constraint.name is None:
                            continue
                        declared_checks.add((table.name, constraint.name))
                        before = check_def(table.name, constraint.name)
                        if before is None:
                            mismatches.append(
                                f"check {constraint.name} is declared on {table.name} but missing in the DB"
                            )
                            continue
                        conn.execute(DropConstraint(constraint))
                        conn.execute(AddConstraint(constraint))
                        if check_def(table.name, constraint.name) != before:
                            mismatches.append(
                                f"check {constraint.name}: DB has {before!r}, model gives "
                                f"{check_def(table.name, constraint.name)!r}"
                            )

                    for column in table.columns:
                        if column.computed is None:
                            continue
                        expression_sql = (
                            "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d "
                            "JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum "
                            "WHERE d.adrelid = to_regclass(:t) AND a.attname = :c"
                        )
                        before = conn.execute(sa.text(expression_sql), {"t": table.name, "c": column.name}).scalar()
                        conn.execute(sa.text(f'ALTER TABLE "{table.name}" DROP COLUMN "{column.name}"'))
                        conn.execute(
                            sa.text(
                                f'ALTER TABLE "{table.name}" ADD COLUMN '
                                + str(CreateColumn(column).compile(dialect=dialect))
                            )
                        )
                        after = conn.execute(sa.text(expression_sql), {"t": table.name, "c": column.name}).scalar()
                        if after != before:
                            mismatches.append(
                                f"generated column {table.name}.{column.name}: DB has {before!r}, model gives {after!r}"
                            )

                transaction.rollback()

                db_indexes = {
                    row[0]
                    for row in conn.execute(
                        sa.text(
                            "SELECT i.indexname FROM pg_indexes i WHERE i.schemaname = 'public' "
                            "AND i.indexname NOT IN (SELECT c.relname FROM pg_constraint k "
                            "JOIN pg_class c ON c.oid = k.conindid WHERE k.conindid <> 0) "
                            "AND i.tablename <> 'alembic_version'"
                        )
                    )
                }
                mismatches.extend(
                    f"index {name} exists in the DB but not in the models"
                    for name in sorted(db_indexes - declared_indexes)
                )

                db_checks = {
                    (row[0], row[1])
                    for row in conn.execute(
                        sa.text(
                            "SELECT c.conrelid::regclass::text, c.conname FROM pg_constraint c "
                            "WHERE c.contype = 'c' AND c.connamespace = 'public'::regnamespace"
                        )
                    )
                }
                mismatches.extend(
                    f"check {name} on {table} exists in the DB but not in the models"
                    for table, name in sorted(db_checks - declared_checks)
                )
        finally:
            engine.dispose()

        assert not mismatches, "\n".join(mismatches)


def _article_matches(db_name: str, slug: str, word: str, column: str = "search_vector") -> bool:
    return _sql(db_name, f"SELECT {column} @@ to_tsquery('simple', %s) FROM articles WHERE slug = %s", (word, slug))[0][
        0
    ]


class TestSearchVectorNestedGm:
    def test_nested_gm_block_stops_leaking_into_the_public_index(self, scratch_db):
        _alembic(scratch_db, "downgrade", BEFORE_HARDENING)
        _sql(
            scratch_db,
            "INSERT INTO articles (slug, title, excerpt, body_markdown, article_type, status, visibility) VALUES "
            "('nested', 'Nested', 'Intro :::gm exsecret :::note inner ::: exleak :::', "
            "'Open. :::gm hiddenword :::spoiler innerword ::: leakword ::: tail', 'lore', 'PUBLISHED', 'PUBLIC'), "
            "('flat', 'Flat', NULL, 'Open. :::gm flatsecret ::: after', 'lore', 'PUBLISHED', 'PUBLIC')",
        )
        assert _article_matches(scratch_db, "nested", "leakword")  # the legacy leak the revision fixes

        _alembic(scratch_db, "upgrade", "head")

        assert not _article_matches(scratch_db, "nested", "leakword")
        assert not _article_matches(scratch_db, "nested", "innerword")
        assert not _article_matches(scratch_db, "nested", "hiddenword")
        assert not _article_matches(scratch_db, "flat", "flatsecret")
        assert _article_matches(scratch_db, "nested", "leakword", "search_vector_gm")  # GMs still find everything
        assert _article_matches(scratch_db, "flat", "after")


class TestIntegrityRevision:
    def _legacy_users(self, db_name: str) -> None:
        _sql(
            db_name,
            "INSERT INTO users (username, email, hashed_password, role, created_at) VALUES "
            "('alice', 'Alice@Example.com', 'x', 'PLAYER', now()), "
            "('alice2', ' alice@example.com', 'x', 'PLAYER', now()), "
            "('bob', 'Bob@Example.com', 'x', 'PLAYER', now())",
        )

    def test_case_duplicate_emails_abort_the_migration_without_changes(self, scratch_db):
        _alembic(scratch_db, "downgrade", INDEX_REVISION)
        self._legacy_users(scratch_db)

        result = _alembic(scratch_db, "upgrade", "head", check=False)

        assert result.returncode != 0
        assert "alice@example.com" in result.stderr and "never merges accounts" in result.stderr
        assert _version(scratch_db) == INDEX_REVISION
        assert _sql(scratch_db, "SELECT count(*) FROM users WHERE email = 'Bob@Example.com'")[0][0] == 1  # untouched

    def test_after_resolving_duplicates_emails_are_normalized_and_unique(self, scratch_db):
        _alembic(scratch_db, "downgrade", INDEX_REVISION)
        self._legacy_users(scratch_db)
        _sql(scratch_db, "UPDATE users SET email = 'alice.two@example.com' WHERE username = 'alice2'")

        _alembic(scratch_db, "upgrade", "head")

        emails = {
            row[0]
            for row in _sql(scratch_db, "SELECT email FROM users WHERE username LIKE 'alice%' OR username = 'bob'")
        }
        assert emails == {"alice@example.com", "alice.two@example.com", "bob@example.com"}
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _sql(
                scratch_db,
                "INSERT INTO users (username, email, hashed_password, role, created_at) "
                "VALUES ('mallory', 'BOB@example.com', 'x', 'PLAYER', now())",
            )

    def test_duplicate_feat_names_and_bad_rows_are_reported_together(self, scratch_db):
        _alembic(scratch_db, "downgrade", INDEX_REVISION)
        _sql(
            scratch_db,
            "INSERT INTO features (name, source_type, description) VALUES "
            "('Alert', 'FEAT', ''), ('Alert', 'FEAT', ''), ('Alert', 'OTHER', '')",
        )
        _sql(scratch_db, "INSERT INTO races (name, size, speed, description) VALUES ('Fastling', 'MEDIUM', 999, '')")

        result = _alembic(scratch_db, "upgrade", "head", check=False)

        assert result.returncode != 0
        assert "feat name 'Alert'" in result.stderr
        assert "ck_races_speed" in result.stderr
        assert _version(scratch_db) == INDEX_REVISION

        _sql(
            scratch_db,
            "UPDATE features SET name = 'Alert 2' WHERE id = (SELECT max(id) FROM features WHERE source_type = 'FEAT')",
        )
        _sql(scratch_db, "UPDATE races SET speed = 30")
        _alembic(scratch_db, "upgrade", "head")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _sql(scratch_db, "INSERT INTO features (name, source_type, description) VALUES ('Alert', 'FEAT', '')")
        _sql(
            scratch_db, "INSERT INTO features (name, source_type, description) VALUES ('Alert', 'OTHER', '')"
        )  # allowed


class TestAsiChoicesRevision:
    LEGACY = (
        "INSERT INTO classes (name, hit_dice, skill_choice_count, description) VALUES ('Fighter', 'D10', 2, '');"
        "INSERT INTO users (username, email, hashed_password, role, created_at) VALUES ('p', 'p@example.com', 'x', 'PLAYER', now());"
        "INSERT INTO characters (owner_id, name, level, class_id, current_hp, max_hp, temp_hp, speed, armor_class, shield,"
        " strength, dexterity, constitution, intelligence, wisdom, charisma, backstory, notes,"
        " money_gold, money_silver, money_copper, created_at) "
        "SELECT u.id, 'Hero', 5, (SELECT id FROM classes LIMIT 1), 10, 20, 0, 30, 10, 0, 10, 10, 10, 10, 10, 10, '', '', 0, 0, 0, now()"
        " FROM users u WHERE u.username = 'p';"
        "INSERT INTO character_asi_choices (character_id, class_level, choice_type, increases) VALUES "
        "((SELECT id FROM characters WHERE name = 'Hero'), 4, 'ASI',"
        ' \'[{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 1}, {"ability": "dex", "amount": "2"}]\'),'
        "((SELECT id FROM characters WHERE name = 'Hero'), 8, 'ASI', NULL),"
        "((SELECT id FROM characters WHERE name = 'Hero'), 12, 'ASI', 'null'::jsonb),"
        "((SELECT id FROM characters WHERE name = 'Hero'), 16, 'ASI', '{\"ability\": \"STR\", \"amount\": 1}'::jsonb)"
    )

    def test_duplicates_are_summed_and_odd_payloads_mean_no_increases(self, scratch_db):
        _alembic(scratch_db, "downgrade", BEFORE_ASI)
        _sql(scratch_db, self.LEGACY)

        _alembic(scratch_db, "upgrade", "head")

        rows = _sql(
            scratch_db, "SELECT ability::text, amount FROM character_asi_choice_increases ORDER BY ability::text"
        )
        assert rows == [("DEX", 2), ("STR", 2)]
        assert _sql(scratch_db, "SELECT bool_and(applied_to_base) FROM character_asi_choices")[0][0] is True

    def test_malformed_elements_abort_instead_of_being_dropped(self, scratch_db):
        _alembic(scratch_db, "downgrade", BEFORE_ASI)
        _sql(scratch_db, self.LEGACY)
        _sql(
            scratch_db,
            'UPDATE character_asi_choices SET increases = \'[{"ability": "XXX", "amount": 1}]\' WHERE class_level = 8',
        )

        result = _alembic(scratch_db, "upgrade", "head", check=False)

        assert result.returncode != 0
        assert "XXX" in result.stderr
        assert _version(scratch_db) == BEFORE_ASI

    def test_downgrade_folds_uncounted_points_into_the_base_scores(self, scratch_db):
        _alembic(scratch_db, "downgrade", BEFORE_ASI)
        _sql(scratch_db, self.LEGACY)
        _alembic(scratch_db, "upgrade", "head")
        _sql(
            scratch_db,
            "WITH c AS (INSERT INTO character_asi_choices (character_id, class_level, choice_type, applied_to_base) "
            "SELECT id, NULL, 'ASI', FALSE FROM characters RETURNING id) "
            "INSERT INTO character_asi_choice_increases (character_asi_choice_id, ability, amount) "
            "SELECT id, 'STR'::ability_score, 3 FROM c UNION ALL SELECT id, 'WIS'::ability_score, -1 FROM c",
        )

        _alembic(scratch_db, "downgrade", BEFORE_ASI)

        assert _sql(scratch_db, "SELECT strength, wisdom, dexterity FROM characters")[0] == (13, 9, 10)
        payload = _sql(scratch_db, "SELECT increases FROM character_asi_choices WHERE class_level IS NULL")[0][0]
        assert {(entry["ability"], entry["amount"]) for entry in payload} == {("STR", 3), ("WIS", -1)}
