"""feature/feat engine (unified effect schema, character-side grants,
feat catalog migration, ability-increases retirement) + subrace tags

Revision ID: c8f4e2a6b9d3
Revises: b3f6a2c8d4e1
Create Date: 2026-09-08 18:00:00.000000

Single consolidated migration (squashed from four WIP revisions that were
never applied anywhere but local dev/test) covering:

1. Reference-side effect engine: ``features`` gains the feat columns
   (``min_level``, ``prerequisite_*``, ``is_repeatable`` — ``source_type=FEAT``
   is now a real, writable source), plus ``feature_choice_groups`` /
   ``feature_choice_options`` ("pick N of M") and six typed effect tables
   (ability score, skill proficiency, saving throw, armor proficiency,
   weapon proficiency, spell grant). Each effect row has exactly one parent:
   ``feature_id`` (fixed) or ``choice_option_id`` (inside a chosen option).

2. Character-side grants: ``feature_grant_source`` enum (AUTO/GM/ASI) +
   ``character_features.grant_source``; ``character_skill_proficiencies``
   gains ``source_character_feature_id``; new tables
   ``character_feature_choices``, ``character_saving_throw_proficiencies``,
   ``character_armor_proficiencies``, ``character_weapon_proficiencies``,
   ``character_granted_spells``.

3. Feat catalog migration: every ``feats`` row gets a mirror ``features``
   row with ``source_type='FEAT'``; every feat with 1+
   ``feat_ability_score_increases`` rows gets exactly ONE
   ``feature_choice_groups`` row (``pick_count=1``) with one option per
   alternative — uniform even for a single option, since taking a feat with
   any ASI option has always required an explicit, confirmed pick. Every
   ``character_feats`` row becomes a ``character_features`` row
   (``grant_source`` mapped from the old ``source_type``: GM/ASI kept,
   ORIGIN folded into AUTO), with a matching ``character_feature_choices``
   row when it had an ``ability_score_increase_id``.
   ``character_asi_choices.feat_id`` / ``.ability_score_increase_id`` are
   repointed (data + FK constraints) from ``feats`` /
   ``feat_ability_score_increases`` to ``features`` /
   ``feature_ability_score_effects``.

4. Ability-increases retirement: ``feature_ability_increases`` (the
   pre-engine "fixed ability bonus on a feature" table — a duplicate of
   what ``feature_ability_score_effects`` already models as a
   ``feature_id``-owned fixed row) is copied into
   ``feature_ability_score_effects`` and dropped.

5. Subrace tags: ``subrace_tags`` (cultural/regional tags) and the
   ``subraces`` m2m link ``subrace_tag_links``, matching
   ``app/models/subrace_tag_model.py`` / ``app/models/subrace_association_models.py``.

The legacy ``feats`` / ``feat_ability_score_increases`` / ``character_feats``
tables stay physically in place (frozen, no longer written by application
code) until a future cleanup migration drops them.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8f4e2a6b9d3"
down_revision: Union[str, None] = "b3f6a2c8d4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ability_score_enum = postgresql.ENUM(
    "STR",
    "DEX",
    "CON",
    "INT",
    "WIS",
    "CHA",
    name="ability_score",
    create_type=False,
)
armor_proficiency_enum = postgresql.ENUM(
    "LIGHT",
    "MEDIUM",
    "HEAVY",
    "SHIELD",
    name="armor_proficiency",
    create_type=False,
)
weapon_proficiency_enum = postgresql.ENUM(
    "SIMPLE",
    "MARTIAL",
    name="weapon_proficiency",
    create_type=False,
)
spell_level_enum = postgresql.ENUM(
    "CANTRIP",
    "LEVEL_1",
    "LEVEL_2",
    "LEVEL_3",
    "LEVEL_4",
    "LEVEL_5",
    "LEVEL_6",
    "LEVEL_7",
    "LEVEL_8",
    "LEVEL_9",
    name="spell_level",
    create_type=False,
)
spell_school_enum = postgresql.ENUM(
    "ABJURATION",
    "CONJURATION",
    "DIVINATION",
    "ENCHANTMENT",
    "EVOCATION",
    "ILLUSION",
    "NECROMANCY",
    "TRANSMUTATION",
    name="spell_school",
    create_type=False,
)

# The "exactly one of the two parents" invariant shared by every effect table.
_PARENT_INVARIANT = (
    "(feature_id IS NOT NULL AND choice_option_id IS NULL) "
    "OR (feature_id IS NULL AND choice_option_id IS NOT NULL)"
)


def upgrade() -> None:
    """Upgrade schema."""

    # ==================================================================
    # 1. Reference-side effect engine
    # ==================================================================

    op.add_column("features", sa.Column("min_level", sa.Integer(), nullable=True))
    op.add_column("features", sa.Column("prerequisite_ability", ability_score_enum, nullable=True))
    op.add_column("features", sa.Column("prerequisite_minimum_score", sa.Integer(), nullable=True))
    op.add_column(
        "features", sa.Column("prerequisite_description", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "features", sa.Column("is_repeatable", sa.Boolean(), nullable=False, server_default=sa.false())
    )

    op.create_table(
        "feature_choice_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("pick_count", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("pick_count >= 1", name="check_feature_choice_group_pick_count_positive"),
    )
    op.create_index(
        op.f("ix_feature_choice_groups_feature_id"), "feature_choice_groups", ["feature_id"], unique=False
    )

    op.create_table(
        "feature_choice_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["feature_choice_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feature_choice_options_group_id"), "feature_choice_options", ["group_id"], unique=False
    )

    op.create_table(
        "feature_ability_score_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("choice_option_id", sa.Integer(), nullable=True),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("new_cap", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_PARENT_INVARIANT, name="ck_feature_ability_score_effect_parent"),
    )
    op.create_index(
        op.f("ix_feature_ability_score_effects_feature_id"),
        "feature_ability_score_effects",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_ability_score_effects_choice_option_id"),
        "feature_ability_score_effects",
        ["choice_option_id"],
        unique=False,
    )

    op.create_table(
        "feature_skill_proficiency_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("choice_option_id", sa.Integer(), nullable=True),
        sa.Column("skill_id", sa.Integer(), nullable=True),
        sa.Column("grants_expertise", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_PARENT_INVARIANT, name="ck_feature_skill_proficiency_effect_parent"),
        sa.CheckConstraint(
            "feature_id IS NULL OR skill_id IS NOT NULL",
            name="ck_feature_skill_proficiency_fixed_requires_skill",
        ),
    )
    op.create_index(
        op.f("ix_feature_skill_proficiency_effects_feature_id"),
        "feature_skill_proficiency_effects",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_skill_proficiency_effects_choice_option_id"),
        "feature_skill_proficiency_effects",
        ["choice_option_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_skill_proficiency_effects_skill_id"),
        "feature_skill_proficiency_effects",
        ["skill_id"],
        unique=False,
    )

    op.create_table(
        "feature_saving_throw_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("choice_option_id", sa.Integer(), nullable=True),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_PARENT_INVARIANT, name="ck_feature_saving_throw_effect_parent"),
    )
    op.create_index(
        op.f("ix_feature_saving_throw_effects_feature_id"),
        "feature_saving_throw_effects",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_saving_throw_effects_choice_option_id"),
        "feature_saving_throw_effects",
        ["choice_option_id"],
        unique=False,
    )

    op.create_table(
        "feature_armor_proficiency_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("choice_option_id", sa.Integer(), nullable=True),
        sa.Column("armor_type", armor_proficiency_enum, nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_PARENT_INVARIANT, name="ck_feature_armor_proficiency_effect_parent"),
    )
    op.create_index(
        op.f("ix_feature_armor_proficiency_effects_feature_id"),
        "feature_armor_proficiency_effects",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_armor_proficiency_effects_choice_option_id"),
        "feature_armor_proficiency_effects",
        ["choice_option_id"],
        unique=False,
    )

    op.create_table(
        "feature_weapon_proficiency_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("choice_option_id", sa.Integer(), nullable=True),
        sa.Column("weapon_category", weapon_proficiency_enum, nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_PARENT_INVARIANT, name="ck_feature_weapon_proficiency_effect_parent"),
        sa.CheckConstraint(
            "(weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)",
            name="ck_feature_weapon_proficiency_one_target",
        ),
    )
    op.create_index(
        op.f("ix_feature_weapon_proficiency_effects_feature_id"),
        "feature_weapon_proficiency_effects",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_weapon_proficiency_effects_choice_option_id"),
        "feature_weapon_proficiency_effects",
        ["choice_option_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_weapon_proficiency_effects_item_id"),
        "feature_weapon_proficiency_effects",
        ["item_id"],
        unique=False,
    )

    op.create_table(
        "feature_spell_grant_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("choice_option_id", sa.Integer(), nullable=True),
        sa.Column("spell_id", sa.Integer(), nullable=True),
        sa.Column("spell_school", spell_school_enum, nullable=True),
        sa.Column("spell_level_max", spell_level_enum, nullable=True),
        sa.Column("always_prepared", sa.Boolean(), nullable=False),
        sa.Column("counts_against_known_limit", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spell_id"], ["spells.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_PARENT_INVARIANT, name="ck_feature_spell_grant_effect_parent"),
        sa.CheckConstraint(
            "(spell_id IS NOT NULL AND spell_school IS NULL AND spell_level_max IS NULL) OR (spell_id IS NULL)",
            name="ck_feature_spell_grant_effect_specific_or_filter",
        ),
    )
    op.create_index(
        op.f("ix_feature_spell_grant_effects_feature_id"),
        "feature_spell_grant_effects",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_spell_grant_effects_choice_option_id"),
        "feature_spell_grant_effects",
        ["choice_option_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_spell_grant_effects_spell_id"), "feature_spell_grant_effects", ["spell_id"], unique=False
    )

    # ==================================================================
    # 2. Character-side grants
    # ==================================================================

    grant_source_enum = postgresql.ENUM("AUTO", "GM", "ASI", name="feature_grant_source", create_type=True)
    grant_source_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "character_features",
        sa.Column(
            "grant_source",
            postgresql.ENUM("AUTO", "GM", "ASI", name="feature_grant_source", create_type=False),
            nullable=False,
            server_default="AUTO",
        ),
    )

    op.add_column(
        "character_skill_proficiencies", sa.Column("source_character_feature_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_character_skill_proficiencies_source_grant",
        "character_skill_proficiencies",
        "character_features",
        ["source_character_feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_character_skill_proficiencies_source_character_feature_id"),
        "character_skill_proficiencies",
        ["source_character_feature_id"],
        unique=False,
    )

    op.create_table(
        "character_feature_choices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_feature_id", sa.Integer(), nullable=False),
        sa.Column("choice_group_id", sa.Integer(), nullable=False),
        sa.Column("choice_option_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["choice_group_id"], ["feature_choice_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["choice_option_id"], ["feature_choice_options.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_feature_id", "choice_group_id", "choice_option_id", name="uq_character_feature_choice_option"
        ),
    )
    for col in ("character_feature_id", "choice_group_id", "choice_option_id"):
        op.create_index(
            op.f(f"ix_character_feature_choices_{col}"), "character_feature_choices", [col], unique=False
        )

    op.create_table(
        "character_saving_throw_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "ability", name="uq_character_saving_throw_ability"),
    )
    for col in ("character_id", "source_character_feature_id"):
        op.create_index(
            op.f(f"ix_character_saving_throw_proficiencies_{col}"),
            "character_saving_throw_proficiencies",
            [col],
            unique=False,
        )

    op.create_table(
        "character_armor_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("armor_type", armor_proficiency_enum, nullable=False),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "armor_type", name="uq_character_armor_proficiency_type"),
    )
    for col in ("character_id", "source_character_feature_id"):
        op.create_index(
            op.f(f"ix_character_armor_proficiencies_{col}"), "character_armor_proficiencies", [col], unique=False
        )

    op.create_table(
        "character_weapon_proficiencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("weapon_category", weapon_proficiency_enum, nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "item_id", name="uq_character_weapon_proficiency_item"),
        sa.CheckConstraint(
            "(weapon_category IS NOT NULL AND item_id IS NULL) OR (weapon_category IS NULL AND item_id IS NOT NULL)",
            name="ck_character_weapon_proficiency_one_target",
        ),
    )
    for col in ("character_id", "item_id", "source_character_feature_id"):
        op.create_index(
            op.f(f"ix_character_weapon_proficiencies_{col}"), "character_weapon_proficiencies", [col], unique=False
        )

    op.create_table(
        "character_granted_spells",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("spell_id", sa.Integer(), nullable=False),
        sa.Column("always_prepared", sa.Boolean(), nullable=False),
        sa.Column("counts_against_known_limit", sa.Boolean(), nullable=False),
        sa.Column("source_character_feature_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spell_id"], ["spells.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_character_feature_id"], ["character_features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("character_id", "spell_id", "source_character_feature_id"):
        op.create_index(
            op.f(f"ix_character_granted_spells_{col}"), "character_granted_spells", [col], unique=False
        )

    # ==================================================================
    # 3. Feat catalog migration + character grant backfill
    # ==================================================================

    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            INSERT INTO features (name, description, source_type, min_level, prerequisite_ability,
                                  prerequisite_minimum_score, prerequisite_description, is_repeatable)
            SELECT f.name, f.description, 'FEAT', f.min_level, f.prerequisite_ability,
                   f.prerequisite_minimum_score, f.prerequisite_description, false
            FROM feats f
            WHERE NOT EXISTS (
                SELECT 1 FROM features e WHERE e.source_type = 'FEAT' AND e.name = f.name
            )
            """
        )
    )

    feats_with_asi = bind.execute(
        sa.text(
            """
            SELECT f.id, f.name
            FROM feats f
            WHERE EXISTS (SELECT 1 FROM feat_ability_score_increases i WHERE i.feat_id = f.id)
            ORDER BY f.id
            """
        )
    ).fetchall()

    for feat_id, feat_name in feats_with_asi:
        feature_id = bind.execute(
            sa.text("SELECT id FROM features WHERE source_type = 'FEAT' AND name = :name"), {"name": feat_name}
        ).scalar()
        if feature_id is None:
            continue

        already_has_group = bind.execute(
            sa.text("SELECT 1 FROM feature_choice_groups WHERE feature_id = :fid"), {"fid": feature_id}
        ).scalar()
        if already_has_group:
            continue

        group_id = bind.execute(
            sa.text(
                """
                INSERT INTO feature_choice_groups (feature_id, pick_count, sort_order, label)
                VALUES (:fid, 1, 0, 'Ability Score Increase')
                RETURNING id
                """
            ),
            {"fid": feature_id},
        ).scalar()

        increases = bind.execute(
            sa.text(
                "SELECT id, ability, amount FROM feat_ability_score_increases WHERE feat_id = :feat_id ORDER BY id"
            ),
            {"feat_id": feat_id},
        ).fetchall()

        for index, (_inc_id, ability, amount) in enumerate(increases):
            option_id = bind.execute(
                sa.text(
                    """
                    INSERT INTO feature_choice_options (group_id, sort_order, label)
                    VALUES (:gid, :idx, :label)
                    RETURNING id
                    """
                ),
                {"gid": group_id, "idx": index, "label": ability},
            ).scalar()

            bind.execute(
                sa.text(
                    """
                    INSERT INTO feature_ability_score_effects (choice_option_id, ability, amount, new_cap)
                    VALUES (:oid, :ability, :amount, NULL)
                    """
                ),
                {"oid": option_id, "ability": ability, "amount": amount},
            )

    bind.execute(
        sa.text(
            """
            INSERT INTO character_features (character_id, feature_id, grant_source, notes)
            SELECT cf.character_id, e.id, (CASE cf.source_type::text
                                             WHEN 'GM' THEN 'GM'
                                             WHEN 'ASI' THEN 'ASI'
                                             WHEN 'ORIGIN' THEN 'AUTO'
                                             ELSE 'AUTO'
                                         END)::feature_grant_source,
                   ''
            FROM character_feats cf
            JOIN feats f ON f.id = cf.feat_id
            JOIN features e ON e.name = f.name AND e.source_type = 'FEAT'
            WHERE NOT EXISTS (
                SELECT 1 FROM character_features x
                WHERE x.character_id = cf.character_id AND x.feature_id = e.id
            )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO character_feature_choices (character_feature_id, choice_group_id, choice_option_id)
            SELECT x.id, g.id, o.id
            FROM character_feats cf
            JOIN feats f ON f.id = cf.feat_id
            JOIN feat_ability_score_increases old_inc ON old_inc.id = cf.ability_score_increase_id
            JOIN features e ON e.name = f.name AND e.source_type = 'FEAT'
            JOIN character_features x ON x.character_id = cf.character_id AND x.feature_id = e.id
            JOIN feature_choice_groups g ON g.feature_id = e.id
            JOIN feature_choice_options o ON o.group_id = g.id
            JOIN feature_ability_score_effects eff
                ON eff.choice_option_id = o.id AND eff.ability = old_inc.ability
            WHERE cf.ability_score_increase_id IS NOT NULL
            ON CONFLICT (character_feature_id, choice_group_id, choice_option_id) DO NOTHING
            """
        )
    )

    # ==================================================================
    # 4. Repoint character_asi_choices at the engine tables
    # ==================================================================

    old_feat_fk = bind.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'character_asi_choices'::regclass
              AND confrelid = 'feats'::regclass AND contype = 'f'
            """
        )
    ).scalar()
    old_asi_fk = bind.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'character_asi_choices'::regclass
              AND confrelid = 'feat_ability_score_increases'::regclass AND contype = 'f'
            """
        )
    ).scalar()
    if old_feat_fk:
        op.drop_constraint(old_feat_fk, "character_asi_choices", type_="foreignkey")
    if old_asi_fk:
        op.drop_constraint(old_asi_fk, "character_asi_choices", type_="foreignkey")

    bind.execute(
        sa.text(
            """
            UPDATE character_asi_choices ac
            SET ability_score_increase_id = eff.id
            FROM feat_ability_score_increases old_inc
            JOIN feats f ON f.id = old_inc.feat_id
            JOIN features e ON e.name = f.name AND e.source_type = 'FEAT'
            JOIN feature_choice_groups g ON g.feature_id = e.id
            JOIN feature_choice_options o ON o.group_id = g.id
            JOIN feature_ability_score_effects eff ON eff.choice_option_id = o.id AND eff.ability = old_inc.ability
            WHERE old_inc.id = ac.ability_score_increase_id
              AND ac.feat_id = f.id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE character_asi_choices ac
            SET feat_id = e.id
            FROM feats f
            JOIN features e ON e.name = f.name AND e.source_type = 'FEAT'
            WHERE ac.feat_id = f.id
            """
        )
    )

    op.create_foreign_key(
        "character_asi_choices_feat_id_fkey",
        "character_asi_choices",
        "features",
        ["feat_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "character_asi_choices_ability_score_increase_id_fkey",
        "character_asi_choices",
        "feature_ability_score_effects",
        ["ability_score_increase_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ==================================================================
    # 5. Retire feature_ability_increases
    # ==================================================================

    bind.execute(
        sa.text(
            """
            INSERT INTO feature_ability_score_effects (feature_id, ability, amount, new_cap)
            SELECT fi.feature_id, fi.ability, fi.amount, fi.new_cap
            FROM feature_ability_increases fi
            WHERE NOT EXISTS (
                SELECT 1 FROM feature_ability_score_effects e
                WHERE e.feature_id = fi.feature_id
                  AND e.ability = fi.ability
                  AND e.amount = fi.amount
                  AND e.new_cap IS NOT DISTINCT FROM fi.new_cap
            )
            """
        )
    )

    op.drop_index(op.f("ix_feature_ability_increases_feature_id"), table_name="feature_ability_increases")
    op.drop_table("feature_ability_increases")

    # ==================================================================
    # 6. Subrace tags
    # ==================================================================

    op.create_table(
        "subrace_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_subrace_tags_name"), "subrace_tags", ["name"], unique=True)

    op.create_table(
        "subrace_tag_links",
        sa.Column("subrace_id", sa.Integer(), nullable=False),
        sa.Column("subrace_tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["subrace_id"], ["subraces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subrace_tag_id"], ["subrace_tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("subrace_id", "subrace_tag_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()

    # --- 6. Subrace tags ---
    op.drop_table("subrace_tag_links")
    op.drop_index(op.f("ix_subrace_tags_name"), table_name="subrace_tags")
    op.drop_table("subrace_tags")

    # --- 5. Restore feature_ability_increases (best-effort) ---
    op.create_table(
        "feature_ability_increases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("ability", ability_score_enum, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("new_cap", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feature_ability_increases_feature_id"), "feature_ability_increases", ["feature_id"], unique=False
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO feature_ability_increases (feature_id, ability, amount, new_cap)
            SELECT feature_id, ability, amount, new_cap
            FROM feature_ability_score_effects
            WHERE feature_id IS NOT NULL
            """
        )
    )

    # --- 4. Repoint character_asi_choices back to the legacy tables ---
    old_feat_fk = bind.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'character_asi_choices'::regclass
              AND confrelid = 'features'::regclass AND contype = 'f'
            """
        )
    ).scalar()
    old_asi_fk = bind.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'character_asi_choices'::regclass
              AND confrelid = 'feature_ability_score_effects'::regclass AND contype = 'f'
            """
        )
    ).scalar()
    if old_feat_fk:
        op.drop_constraint(old_feat_fk, "character_asi_choices", type_="foreignkey")
    if old_asi_fk:
        op.drop_constraint(old_asi_fk, "character_asi_choices", type_="foreignkey")

    bind.execute(
        sa.text(
            """
            UPDATE character_asi_choices ac
            SET ability_score_increase_id = old_inc.id
            FROM feature_ability_score_effects eff
            JOIN feature_choice_options o ON o.id = eff.choice_option_id
            JOIN feature_choice_groups g ON g.id = o.group_id
            JOIN features e ON e.id = g.feature_id AND e.source_type = 'FEAT'
            JOIN feats f ON f.name = e.name
            JOIN feat_ability_score_increases old_inc ON old_inc.feat_id = f.id AND old_inc.ability = eff.ability
            WHERE eff.id = ac.ability_score_increase_id
              AND ac.feat_id = e.id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE character_asi_choices ac
            SET feat_id = f.id
            FROM features e
            JOIN feats f ON f.name = e.name
            WHERE ac.feat_id = e.id AND e.source_type = 'FEAT'
            """
        )
    )
    op.create_foreign_key(
        "character_asi_choices_feat_id_fkey",
        "character_asi_choices",
        "feats",
        ["feat_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "character_asi_choices_ability_score_increase_id_fkey",
        "character_asi_choices",
        "feat_ability_score_increases",
        ["ability_score_increase_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- 3. Remove the feat-catalog backfill on the character side ---
    op.execute(
        """
        DELETE FROM character_feature_choices
        WHERE character_feature_id IN (
            SELECT x.id FROM character_features x
            JOIN features e ON e.id = x.feature_id AND e.source_type = 'FEAT'
        )
        """
    )
    op.execute(
        """
        DELETE FROM character_features
        WHERE id IN (
            SELECT x.id
            FROM character_features x
            JOIN features e ON e.id = x.feature_id AND e.source_type = 'FEAT'
            JOIN feats f ON f.name = e.name
            WHERE EXISTS (SELECT 1 FROM character_feats cf WHERE cf.character_id = x.character_id AND cf.feat_id = f.id)
        )
        """
    )
    op.execute(
        "DELETE FROM feature_choice_groups WHERE feature_id IN (SELECT id FROM features WHERE source_type = 'FEAT')"
    )

    # --- 2. Character-side grant tables ---
    op.drop_table("character_granted_spells")
    op.drop_table("character_weapon_proficiencies")
    op.drop_table("character_armor_proficiencies")
    op.drop_table("character_saving_throw_proficiencies")
    op.drop_table("character_feature_choices")

    op.drop_index(
        op.f("ix_character_skill_proficiencies_source_character_feature_id"),
        table_name="character_skill_proficiencies",
    )
    op.drop_constraint(
        "fk_character_skill_proficiencies_source_grant", "character_skill_proficiencies", type_="foreignkey"
    )
    op.drop_column("character_skill_proficiencies", "source_character_feature_id")

    op.drop_column("character_features", "grant_source")

    feature_grant_source_enum = postgresql.ENUM("AUTO", "GM", "ASI", name="feature_grant_source", create_type=False)
    feature_grant_source_enum.drop(op.get_bind(), checkfirst=True)

    # --- 1. Reference-side effect engine ---
    op.drop_table("feature_spell_grant_effects")
    op.drop_table("feature_weapon_proficiency_effects")
    op.drop_table("feature_armor_proficiency_effects")
    op.drop_table("feature_saving_throw_effects")
    op.drop_table("feature_skill_proficiency_effects")
    op.drop_table("feature_ability_score_effects")
    op.drop_table("feature_choice_options")
    op.drop_table("feature_choice_groups")

    op.drop_column("features", "is_repeatable")
    op.drop_column("features", "prerequisite_description")
    op.drop_column("features", "prerequisite_minimum_score")
    op.drop_column("features", "prerequisite_ability")
    op.drop_column("features", "min_level")
