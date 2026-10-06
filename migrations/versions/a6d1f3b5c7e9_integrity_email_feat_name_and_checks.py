"""integrity: unique lower(users.email), unique feat name, CHECK bounds that mirror the API schemas

Moves rules that only the application enforced into the database. Everything here depends on the data, so the
revision FIRST runs a pre-check over all of it and, if any rule is violated, aborts BEFORE changing anything with one
message listing every problem and the query that shows the offending rows. The revision never deletes or merges rows
and never rewrites data except the lossless email normalization below. Run the "data checks" before deploying to real
data; the whole revision is one transaction, so a failure leaves the schema untouched.

1. ``users.email``: the application stores and looks emails up normalized (``strip().lower()``, lookup by
   ``lower(email)``). Accounts created earlier may differ only by case/whitespace.
   * Pre-check: ``lower(btrim(email))`` must be unique. Case-duplicates are NOT merged (that would pick a winner among
     two real accounts and orphan one's characters): the migration aborts naming every group (ids, usernames). Resolve
     by hand: rename/delete one account, or move its characters to the other, then re-run.
   * Backfill: ``email = lower(btrim(email))`` (identity-preserving, since the application already compares that way;
     the seeded admin from revision 0003 is lowercased too, ``ADMIN_LOGIN`` is compared normalized).
   * ``uq_users_email_lower`` (unique functional index) replaces the plain unique ``ix_users_email``.
2. ``uq_features_feat_name``: partial unique index on ``features.name WHERE source_type = 'FEAT'``. Pre-check: no two
   feats share an exact name (the application's uniqueness check is exact too). Rename duplicates, then re-run.
3. CHECK constraints equal to the bounds the request schemas already enforce (see ``_CHECKS``). Pre-check: no row
   violates any of them; the abort message gives the count and a ``SELECT`` for each violated rule.

Data checks to run on the real database before deploying::

    SELECT lower(btrim(email)) AS email, array_agg(id ORDER BY id) AS ids, array_agg(username ORDER BY id) AS usernames
    FROM users GROUP BY 1 HAVING count(*) > 1;

    SELECT name, array_agg(id ORDER BY id) AS ids FROM features
    WHERE source_type = 'FEAT' GROUP BY name HAVING count(*) > 1;

    -- one per rule in _CHECKS, e.g.:
    SELECT id, current_hp, max_hp FROM characters WHERE current_hp > max_hp;

Downgrade drops the constraints/indexes and restores the plain unique ``ix_users_email``. The lowercasing of existing
emails is NOT undone (the original casing is not stored anywhere).

Revision ID: a6d1f3b5c7e9
Revises: f8c3e5a7b9d1
Create Date: 2026-10-01 10:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a6d1f3b5c7e9"
down_revision: Union[str, None] = "f8c3e5a7b9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (constraint name, table, expression). The same names/expressions are declared on the models.
_CHECKS = (
    ("ck_characters_current_hp_le_max_hp", "characters", "current_hp <= max_hp"),
    ("ck_characters_combat_stats", "characters", "armor_class >= 0 AND shield >= 0 AND speed >= 0"),
    ("ck_characters_money", "characters", "money_gold >= 0 AND money_silver >= 0 AND money_copper >= 0"),
    ("ck_attacks_damage_dice_count", "attacks", "damage_dice_count IS NULL OR damage_dice_count BETWEEN 1 AND 100"),
    (
        "ck_character_asi_choice_feat_has_feat",
        "character_asi_choices",
        "choice_type <> 'FEAT' OR feat_id IS NOT NULL",
    ),
    ("ck_character_asi_choice_level", "character_asi_choices", "class_level IS NULL OR class_level BETWEEN 1 AND 20"),
    ("ck_character_asi_increase_amount", "character_asi_choice_increases", "amount BETWEEN -30 AND 30"),
    ("ck_feature_choice_group_pick_count_max", "feature_choice_groups", "pick_count <= 50"),
    ("ck_feature_ability_score_effect_amount", "feature_ability_score_effects", "amount BETWEEN -30 AND 30"),
    ("ck_races_speed", "races", "speed BETWEEN 0 AND 200"),
    ("ck_race_ability_bonus_range", "race_ability_bonuses", "bonus BETWEEN -10 AND 10"),
    ("ck_subrace_ability_bonus_range", "subrace_ability_bonuses", "bonus BETWEEN -10 AND 10"),
)

_DUPLICATE_EMAILS_SQL = """
    SELECT lower(btrim(email)) AS email, array_agg(id ORDER BY id) AS ids, array_agg(username ORDER BY id) AS usernames
    FROM users GROUP BY 1 HAVING count(*) > 1 ORDER BY 1
"""
_DUPLICATE_FEATS_SQL = """
    SELECT name, array_agg(id ORDER BY id) AS ids
    FROM features WHERE source_type = 'FEAT' GROUP BY name HAVING count(*) > 1 ORDER BY name
"""


def _preflight() -> None:
    """Abort with one message listing every rule the existing data violates; change nothing."""

    bind = op.get_bind()
    problems: list[str] = []

    for row in bind.execute(sa.text(_DUPLICATE_EMAILS_SQL)):
        problems.append(
            f"users: {len(row.ids)} accounts share the email {row.email!r} once case/whitespace is ignored "
            f"(user ids {row.ids}, usernames {row.usernames}). Rename or remove all but one, or move their "
            "characters to the account you keep; this migration never merges accounts."
        )
    for row in bind.execute(sa.text(_DUPLICATE_FEATS_SQL)):
        problems.append(f"features: feat name {row.name!r} is used by feature ids {row.ids}; rename all but one.")

    for name, table, expression in _CHECKS:
        violating = f"FROM {table} WHERE ({expression}) IS FALSE"
        count = bind.execute(sa.text(f"SELECT count(*) {violating}")).scalar_one()
        if count:
            problems.append(
                f"{table}: {count} row(s) violate {name} ({expression}); list them with: SELECT * {violating}"
            )

    if problems:
        raise RuntimeError(
            "Cannot add the integrity constraints, existing data violates them (nothing was changed):\n  - "
            + "\n  - ".join(problems)
            + "\nFix the rows above and run `alembic upgrade head` again."
        )


def upgrade() -> None:
    """Upgrade schema."""

    _preflight()

    # Lossless: the application already compares ``strip().lower()``; the pre-check guarantees no collision.
    op.execute("UPDATE users SET email = lower(btrim(email)) WHERE email IS DISTINCT FROM lower(btrim(email))")
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.drop_index("ix_users_email", table_name="users")

    op.create_index(
        "uq_features_feat_name",
        "features",
        ["name"],
        unique=True,
        postgresql_where=sa.text("source_type = 'FEAT'"),
    )

    for name, table, expression in _CHECKS:
        op.create_check_constraint(name, table, expression)


def downgrade() -> None:
    """Downgrade schema (email casing is not restored)."""

    for name, table, _expression in reversed(_CHECKS):
        op.drop_constraint(name, table, type_="check")

    op.drop_index("uq_features_feat_name", table_name="features")

    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.drop_index("uq_users_email_lower", table_name="users")
