"""item kinds + detail tables, weapon properties, tool proficiencies, speed and AC effects

Items:

* ``weapon_properties`` (GM-managed dictionary) + ``item_weapon_properties`` replace the free-text
  ``items.weapon_properties`` column: the standard 5e properties are seeded with their rules text, every
  other token found in the old column becomes its own property, and every weapon is linked to its tokens.
* ``items`` keeps the core every item has; ``item_type`` splits into ``kind`` (``WEAPON``/``ARMOR``/``TOOL``/
  ``GEAR`` — a ``SHIELD`` is ``ARMOR``) and ``subtype`` (what a ``GEAR`` item is: potion, ring…; NULL for the
  other kinds), plus ``magic_bonus``. The kind-specific stats move into one detail record per kind, every
  weapon/armor/tool gets its row, so ids — and every FK to an item — stay as they are:

  * ``item_weapon_details`` — the old damage columns + category, range and two-handed damage (the PHB weapons
    by name) and attack type (ranged when the weapon has Ammunition);
  * ``item_armor_details`` — the old AC/DEX cap/Strength/stealth columns + category (``SHIELD`` for an old
    shield, else from the old DEX columns: no DEX → heavy, a DEX cap → medium, else light);
    ``armor_class_dex_bonus`` is dropped (the category decides);
  * ``item_tool_details`` — tool category (by name).
* ``character_items.is_equipped`` / ``is_attuned``.
* ``source_item_choice_options``: ``item_id`` nullable — an option may instead be a filter
  (``kind``/``weapon_category``/``armor_category``/``tool_category``, "any simple weapon"). Every existing
  option has an item, so no option or group changes.

Effect engine:

* ``feature_tool_proficiency_effects`` (+ ``ChoiceType.TOOL``, ``character_feature_choices.picked_item_id``
  for an open "any tool" pick, with its partial unique index). Tool proficiencies are computed from grants,
  never stored in ``character_proficiencies`` — ``proficiency_type`` gets no ``TOOL`` value.
* ``feature_speed_effects`` / ``feature_armor_class_effects``: parent is a feature or an item (exactly one);
  ``choice_option_id`` stays as a column but must be NULL.

The downgrade restores the old ``items`` columns (properties re-joined into their old tokens, ``SHIELD`` items
back to their type) and drops the rest; the dictionary rows themselves are lost. Starting-equipment filter
options can't exist in the old schema: they are deleted, a group left with fewer options than it picks gets
its ``pick_count`` lowered (an emptied group is deleted).

Revision ID: a7d3e9f1c2b4
Revises: f3a9c2e7b4d1
Create Date: 2026-10-24 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7d3e9f1c2b4"
down_revision: Union[str, None] = "f3a9c2e7b4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ABILITY_SCORE = postgresql.ENUM(name="ability_score", create_type=False)
_ARMOR = postgresql.ENUM(name="armor_proficiency", create_type=False)
_WEAPON = postgresql.ENUM(name="weapon_proficiency", create_type=False)
_ATTACK_TYPE = postgresql.ENUM(name="attack_type", create_type=False)
_DICE = postgresql.ENUM(name="hit_dice", create_type=False)
_DAMAGE = postgresql.ENUM(name="damage_type", create_type=False)

# (old token, name, description, requires_range, requires_versatile_damage) — the PHB properties.
_STANDARD_PROPERTIES = (
    (
        "AMMUNITION",
        "Боеприпас",
        "Вы можете использовать оружие со свойством «боеприпас» для совершения дальнобойной атаки, только если "
        "у вас есть боеприпасы для стрельбы. Каждая атака тратит один боеприпас; в конце сражения вы "
        "восстанавливаете половину использованных, потратив минуту на поиски. Рукопашная атака таким оружием — "
        "атака импровизированным оружием.",
        True,
        False,
    ),
    ("TWO_HANDED", "Двуручное", "Это оружие нужно держать двумя руками, когда вы атакуете им.", False, False),
    (
        "REACH",
        "Досягаемость",
        "Это оружие добавляет 5 футов к расстоянию, на котором вы можете совершать им атаки, а также "
        "провоцированные атаки.",
        False,
        False,
    ),
    (
        "LIGHT",
        "Лёгкое",
        "Лёгкое оружие маленькое и удобное, и идеально подходит для сражения двумя оружиями.",
        False,
        False,
    ),
    (
        "THROWN",
        "Метательное",
        "Вы можете совершать этим оружием дальнобойные атаки, метая его, с тем же модификатором "
        "характеристики, что и при рукопашной атаке им.",
        True,
        False,
    ),
    (
        "SPECIAL",
        "Особое",
        "Оружие используется по специальным правилам, указанным в его описании.",
        False,
        False,
    ),
    (
        "LOADING",
        "Перезарядка",
        "Из-за долгой перезарядки вы можете выстрелить из этого оружия только один боеприпас одним действием, "
        "бонусным действием или реакцией, вне зависимости от количества положенных атак.",
        False,
        False,
    ),
    (
        "HEAVY",
        "Тяжёлое",
        "Существа Маленького и Крошечного размера совершают броски атаки тяжёлым оружием с помехой.",
        False,
        False,
    ),
    (
        "VERSATILE",
        "Универсальное",
        "Это оружие можно использовать как одной, так и двумя руками; урон двумя руками указан отдельно.",
        False,
        True,
    ),
    (
        "FINESSE",
        "Фехтовальное",
        "Для бросков атаки и урона вы сами выбираете модификатор Силы или Ловкости (один и тот же для обоих).",
        False,
        False,
    ),
)

# PHB weapons by name: (category, range_normal, range_long, versatile dice count, versatile die).
_PHB_WEAPONS = {
    "Боевой посох": ("SIMPLE", None, None, 1, "D8"),
    "Булава": ("SIMPLE", None, None, None, None),
    "Дубинка": ("SIMPLE", None, None, None, None),
    "Кинжал": ("SIMPLE", 20, 60, None, None),
    "Копьё": ("SIMPLE", 20, 60, 1, "D8"),
    "Лёгкий молот": ("SIMPLE", 20, 60, None, None),
    "Метательное копьё": ("SIMPLE", 30, 120, None, None),
    "Палица": ("SIMPLE", None, None, None, None),
    "Палица (дубина)": ("SIMPLE", None, None, None, None),
    "Ручной топор": ("SIMPLE", 20, 60, None, None),
    "Серп": ("SIMPLE", None, None, None, None),
    "Арбалет, лёгкий": ("SIMPLE", 80, 320, None, None),
    "Дротик": ("SIMPLE", 20, 60, None, None),
    "Короткий лук": ("SIMPLE", 80, 320, None, None),
    "Праща": ("SIMPLE", 30, 120, None, None),
    "Алебарда": ("MARTIAL", None, None, None, None),
    "Боевая кирка": ("MARTIAL", None, None, None, None),
    "Боевой молот": ("MARTIAL", None, None, 1, "D10"),
    "Боевой топор": ("MARTIAL", None, None, 1, "D10"),
    "Глефа": ("MARTIAL", None, None, None, None),
    "Двуручный меч": ("MARTIAL", None, None, None, None),
    "Длинное копьё": ("MARTIAL", None, None, None, None),
    "Длинный меч": ("MARTIAL", None, None, 1, "D10"),
    "Кнут": ("MARTIAL", None, None, None, None),
    "Короткий меч": ("MARTIAL", None, None, None, None),
    "Молот": ("MARTIAL", None, None, None, None),
    "Моргенштерн": ("MARTIAL", None, None, None, None),
    "Пика": ("MARTIAL", None, None, None, None),
    "Рапира": ("MARTIAL", None, None, None, None),
    "Секира": ("MARTIAL", None, None, None, None),
    "Скимитар": ("MARTIAL", None, None, None, None),
    "Трезубец": ("MARTIAL", 20, 60, 1, "D8"),
    "Цеп": ("MARTIAL", None, None, None, None),
    "Арбалет, ручной": ("MARTIAL", 30, 120, None, None),
    "Арбалет, тяжёлый": ("MARTIAL", 100, 400, None, None),
    "Длинный лук": ("MARTIAL", 150, 600, None, None),
    "Духовая трубка": ("MARTIAL", 25, 100, None, None),
    "Сеть": ("MARTIAL", 5, 15, None, None),
}

_MUSICAL_INSTRUMENTS = (
    "Барабан", "Боевой гонг", "Виола", "Волынка", "Глор", "Длинный рог", "Зулкун", "Лира", "Лютня",
    "Песенный рог", "Птичья свирель", "Рожок", "Ручной барабан", "Свирель", "Тантан", "Теларр", "Тоскен",
    "Флейта", "Цимбалы", "Шалмей", "Яртинг",
)  # fmt: skip
_GAMING_SETS = ("Драконьи шахматы", "Игральные карты", "Набор игровых костей", "Ставка трех драконов")
_KITS = (
    "Воровские инструменты", "Инструменты навигатора", "Инструменты отравителя", "Набор для грима",
    "Набор для фальсификации", "Набор травника", "Набор взломщика", "Хирургический набор",
    "Комплект целителя (Набор лекаря)",
)  # fmt: skip

_EFFECT_PARENT = (
    "(feature_id IS NOT NULL AND choice_option_id IS NULL) OR (feature_id IS NULL AND choice_option_id IS NOT NULL)"
)
_ITEM_EFFECT_PARENT = "num_nonnulls(feature_id, item_id) = 1 AND choice_option_id IS NULL"

# The old item columns the detail tables take over unchanged.
_WEAPON_COLUMNS = ("damage_dice_count", "damage_dice_type", "damage_type")
_ARMOR_COLUMNS = ("armor_class_base", "armor_class_max_dex_bonus", "strength_requirement", "stealth_disadvantage")
_DETAIL_TABLES = ("item_weapon_details", "item_armor_details", "item_tool_details")


def _names(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _token_names() -> str:
    """``(token, name)`` VALUES rows of the standard properties."""

    return ", ".join(f"('{token}', '{name}')" for token, name, *_ in _STANDARD_PROPERTIES)


def _parents(item_parent: bool) -> list[sa.Column]:
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("features.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "choice_option_id",
            sa.Integer(),
            sa.ForeignKey("feature_choice_options.id", ondelete="CASCADE"),
            nullable=True,
        ),
    ]
    if item_parent:
        columns.append(sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=True))
    return columns


def _index_parents(table: str, item_parent: bool) -> None:
    for column in ("feature_id", "choice_option_id", *(("item_id",) if item_parent else ())):
        op.create_index(f"ix_{table}_{column}", table, [column])


def _item_fk() -> sa.Column:
    return sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)


def _upgrade_properties() -> None:
    op.create_table(
        "weapon_properties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("requires_range", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_versatile_damage", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_weapon_properties_name", "weapon_properties", ["name"], unique=True)
    op.create_table(
        "item_weapon_properties",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "property_id",
            sa.Integer(),
            sa.ForeignKey("weapon_properties.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("ix_item_weapon_properties_property_id", "item_weapon_properties", ["property_id"])

    properties = sa.table(
        "weapon_properties",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("requires_range", sa.Boolean),
        sa.column("requires_versatile_damage", sa.Boolean),
    )
    op.bulk_insert(
        properties,
        [
            {"name": name, "description": text, "requires_range": rng, "requires_versatile_damage": versatile}
            for _, name, text, rng, versatile in _STANDARD_PROPERTIES
        ],
    )
    # Old token -> property name; any other token becomes a property of its own (capitalized).
    op.execute(
        f"""
        CREATE TEMP TABLE _item_tokens ON COMMIT DROP AS
        SELECT DISTINCT i.id AS item_id, COALESCE(m.name, initcap(lower(btrim(t.token)))) AS name
        FROM items i
        CROSS JOIN LATERAL unnest(string_to_array(i.weapon_properties, ',')) AS t(token)
        LEFT JOIN (VALUES {_token_names()}) AS m(token, name) ON m.token = upper(btrim(t.token))
        WHERE i.weapon_properties IS NOT NULL AND btrim(t.token) <> ''
        """
    )
    op.execute(
        "INSERT INTO weapon_properties (name) SELECT DISTINCT name FROM _item_tokens ON CONFLICT (name) DO NOTHING"
    )
    op.execute(
        """
        INSERT INTO item_weapon_properties (item_id, property_id)
        SELECT DISTINCT t.item_id, p.id FROM _item_tokens t JOIN weapon_properties p ON p.name = t.name
        """
    )


def _upgrade_details() -> None:
    op.create_table(
        "item_weapon_details",
        _item_fk(),
        sa.Column("weapon_category", _WEAPON, nullable=True),
        sa.Column("attack_type", _ATTACK_TYPE, nullable=True),
        sa.Column("damage_dice_count", sa.Integer(), nullable=True),
        sa.Column("damage_dice_type", _DICE, nullable=True),
        sa.Column("damage_type", _DAMAGE, nullable=True),
        sa.Column("range_normal", sa.Integer(), nullable=True),
        sa.Column("range_long", sa.Integer(), nullable=True),
        sa.Column("versatile_dice_count", sa.Integer(), nullable=True),
        sa.Column("versatile_dice_type", _DICE, nullable=True),
        sa.CheckConstraint(
            "range_normal IS NULL OR (range_normal > 0 AND (range_long IS NULL OR range_long >= range_normal))",
            name="ck_item_weapon_details_range",
        ),
        sa.CheckConstraint(
            "(versatile_dice_count IS NULL) = (versatile_dice_type IS NULL)", name="ck_item_weapon_details_versatile"
        ),
    )
    op.create_index("ix_item_weapon_details_weapon_category", "item_weapon_details", ["weapon_category"])
    op.create_table(
        "item_armor_details",
        _item_fk(),
        sa.Column("armor_category", _ARMOR, nullable=True),
        sa.Column("armor_class_base", sa.Integer(), nullable=True),
        sa.Column("armor_class_max_dex_bonus", sa.Integer(), nullable=True),
        sa.Column("strength_requirement", sa.Integer(), nullable=True),
        sa.Column("stealth_disadvantage", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_item_armor_details_armor_category", "item_armor_details", ["armor_category"])
    op.create_table("item_tool_details", _item_fk(), sa.Column("tool_category", sa.String(30), nullable=True))
    op.create_index("ix_item_tool_details_tool_category", "item_tool_details", ["tool_category"])

    weapon_columns = ", ".join(_WEAPON_COLUMNS)
    op.execute(
        f"INSERT INTO item_weapon_details (item_id, {weapon_columns}) "
        f"SELECT id, {weapon_columns} FROM items WHERE item_type = 'WEAPON'"
    )
    for name, (category, range_normal, range_long, v_count, v_die) in _PHB_WEAPONS.items():
        op.execute(
            sa.text(
                "UPDATE item_weapon_details d SET weapon_category = CAST(:category AS weapon_proficiency), "
                "range_normal = :rn, range_long = :rl, versatile_dice_count = :vc, "
                "versatile_dice_type = CAST(:vd AS hit_dice) "
                "FROM items i WHERE i.id = d.item_id AND i.name = :name"
            ).bindparams(category=category, rn=range_normal, rl=range_long, vc=v_count, vd=v_die, name=name)
        )
    op.execute(
        """
        UPDATE item_weapon_details d SET attack_type = CASE
            WHEN EXISTS (
                SELECT 1 FROM item_weapon_properties l JOIN weapon_properties p ON p.id = l.property_id
                WHERE l.item_id = d.item_id AND p.name = 'Боеприпас'
            ) THEN 'RANGED_ATTACK'::attack_type
            ELSE 'MELEE_ATTACK'::attack_type END
        """
    )

    armor_columns = ", ".join(_ARMOR_COLUMNS)
    op.execute(
        f"""
        INSERT INTO item_armor_details (item_id, armor_category, {armor_columns})
        SELECT id, CASE
                WHEN item_type = 'SHIELD' THEN 'SHIELD'::armor_proficiency
                WHEN armor_class_base IS NULL THEN NULL
                WHEN NOT armor_class_dex_bonus THEN 'HEAVY'::armor_proficiency
                WHEN armor_class_max_dex_bonus IS NOT NULL THEN 'MEDIUM'::armor_proficiency
                ELSE 'LIGHT'::armor_proficiency END,
            {armor_columns}
        FROM items WHERE item_type IN ('ARMOR', 'SHIELD')
        """
    )

    op.execute(
        f"""
        INSERT INTO item_tool_details (item_id, tool_category)
        SELECT id, CASE
                WHEN name IN ({_names(_MUSICAL_INSTRUMENTS)}) THEN 'MUSICAL_INSTRUMENT'
                WHEN name IN ({_names(_GAMING_SETS)}) THEN 'GAMING_SET'
                WHEN name IN ({_names(_KITS)}) THEN 'KIT'
                WHEN name LIKE 'Инструменты %' THEN 'ARTISAN' END
        FROM items WHERE item_type = 'TOOL'
        """
    )


def _upgrade_items() -> None:
    _upgrade_properties()
    _upgrade_details()

    op.add_column("items", sa.Column("kind", sa.String(20), nullable=True))
    op.add_column("items", sa.Column("subtype", sa.String(30), nullable=True))
    op.add_column("items", sa.Column("magic_bonus", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE items SET
            kind = CASE WHEN item_type IN ('WEAPON', 'ARMOR', 'TOOL') THEN item_type
                        WHEN item_type = 'SHIELD' THEN 'ARMOR' ELSE 'GEAR' END,
            subtype = CASE WHEN item_type IN ('WEAPON', 'ARMOR', 'SHIELD', 'TOOL') THEN NULL ELSE item_type END
        """
    )
    op.alter_column("items", "kind", nullable=False)
    op.create_index("ix_items_kind", "items", ["kind"])
    op.create_index("ix_items_subtype", "items", ["subtype"])
    op.create_check_constraint("ck_items_subtype_gear_only", "items", "kind = 'GEAR' OR subtype IS NULL")
    op.create_check_constraint("ck_items_magic_bonus", "items", "magic_bonus IS NULL OR magic_bonus BETWEEN -10 AND 10")
    for column in ("item_type", "weapon_properties", "armor_class_dex_bonus", *_WEAPON_COLUMNS, *_ARMOR_COLUMNS):
        op.drop_column("items", column)

    op.add_column("character_items", sa.Column("is_equipped", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("character_items", sa.Column("is_attuned", sa.Boolean(), nullable=False, server_default=sa.false()))

    # Every existing option has an item_id, so the new CHECK holds without touching any option or group.
    op.alter_column("source_item_choice_options", "item_id", nullable=True)
    op.add_column("source_item_choice_options", sa.Column("kind", sa.String(20), nullable=True))
    op.add_column("source_item_choice_options", sa.Column("weapon_category", _WEAPON, nullable=True))
    op.add_column("source_item_choice_options", sa.Column("armor_category", _ARMOR, nullable=True))
    op.add_column("source_item_choice_options", sa.Column("tool_category", sa.String(30), nullable=True))
    op.create_check_constraint(
        "ck_choice_option_item_or_filter",
        "source_item_choice_options",
        "(item_id IS NOT NULL) <> (num_nonnulls(kind, weapon_category, armor_category, tool_category) > 0)",
    )


def _upgrade_effects() -> None:
    op.execute("ALTER TYPE choice_type ADD VALUE IF NOT EXISTS 'TOOL'")

    op.create_table(
        "feature_tool_proficiency_effects",
        *_parents(item_parent=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("tool_category", sa.String(30), nullable=True),
        sa.CheckConstraint(_EFFECT_PARENT, name="ck_feature_tool_proficiency_effect_parent"),
        sa.CheckConstraint(
            "feature_id IS NULL OR item_id IS NOT NULL", name="ck_feature_tool_proficiency_fixed_requires_item"
        ),
        sa.CheckConstraint(
            "item_id IS NULL OR tool_category IS NULL", name="ck_feature_tool_proficiency_filter_open_only"
        ),
    )
    _index_parents("feature_tool_proficiency_effects", item_parent=False)
    op.create_index("ix_feature_tool_proficiency_effects_item_id", "feature_tool_proficiency_effects", ["item_id"])

    op.create_table(
        "feature_speed_effects",
        *_parents(item_parent=True),
        sa.Column("speed_type", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(30), nullable=False),
        sa.Column("min_level", sa.Integer(), nullable=True),
        sa.CheckConstraint(_ITEM_EFFECT_PARENT, name="ck_feature_speed_effect_parent"),
        sa.CheckConstraint("value BETWEEN -200 AND 200", name="ck_feature_speed_effect_value"),
        sa.CheckConstraint("min_level IS NULL OR min_level BETWEEN 1 AND 20", name="ck_feature_speed_effect_min_level"),
    )
    _index_parents("feature_speed_effects", item_parent=True)

    op.create_table(
        "feature_armor_class_effects",
        *_parents(item_parent=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("abilities", postgresql.ARRAY(_ABILITY_SCORE), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("allows_shield", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("condition", sa.String(30), nullable=False),
        sa.Column("min_level", sa.Integer(), nullable=True),
        sa.CheckConstraint(_ITEM_EFFECT_PARENT, name="ck_feature_armor_class_effect_parent"),
        sa.CheckConstraint("value BETWEEN -30 AND 30", name="ck_feature_armor_class_effect_value"),
        sa.CheckConstraint(
            "min_level IS NULL OR min_level BETWEEN 1 AND 20", name="ck_feature_armor_class_effect_min_level"
        ),
    )
    _index_parents("feature_armor_class_effects", item_parent=True)

    op.add_column(
        "character_feature_choices",
        sa.Column("picked_item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_character_feature_choices_picked_item_id", "character_feature_choices", ["picked_item_id"])
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text(
            "picked_skill_id IS NULL AND picked_spell_id IS NULL AND picked_ability IS NULL AND picked_item_id IS NULL"
        ),
    )
    op.create_index(
        "uq_character_feature_choice_option_item",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id", "picked_item_id"],
        unique=True,
        postgresql_where=sa.text("picked_item_id IS NOT NULL"),
    )


def upgrade() -> None:
    _upgrade_items()
    _upgrade_effects()


def _downgrade_effects() -> None:
    # TOOL choice groups can't exist in the old schema (the enum value itself stays — Postgres can't drop it);
    # their picks go first (character_feature_choices -> group/option is RESTRICT).
    op.execute(
        "DELETE FROM character_feature_choices WHERE picked_item_id IS NOT NULL "
        "OR choice_group_id IN (SELECT id FROM feature_choice_groups WHERE choice_type = 'TOOL')"
    )
    op.drop_index("uq_character_feature_choice_option_item", table_name="character_feature_choices")
    op.drop_index("uq_character_feature_choice_option", table_name="character_feature_choices")
    op.create_index(
        "uq_character_feature_choice_option",
        "character_feature_choices",
        ["character_feature_id", "choice_group_id", "choice_option_id"],
        unique=True,
        postgresql_where=sa.text("picked_skill_id IS NULL AND picked_spell_id IS NULL AND picked_ability IS NULL"),
    )
    op.drop_index("ix_character_feature_choices_picked_item_id", table_name="character_feature_choices")
    op.drop_column("character_feature_choices", "picked_item_id")
    op.drop_table("feature_armor_class_effects")
    op.drop_table("feature_speed_effects")
    op.execute("DELETE FROM feature_choice_groups WHERE choice_type = 'TOOL'")
    op.drop_table("feature_tool_proficiency_effects")


def _downgrade_choice_options() -> None:
    # Filter options can't exist in the old schema. A group they leave with fewer options than it picks picks
    # what is left; an emptied group goes.
    op.execute(
        """
        CREATE TEMP TABLE _filter_groups ON COMMIT DROP AS
        SELECT DISTINCT group_id FROM source_item_choice_options WHERE item_id IS NULL
        """
    )
    op.execute("DELETE FROM source_item_choice_options WHERE item_id IS NULL")
    op.execute(
        """
        UPDATE source_item_choice_groups g SET pick_count = sub.remaining
        FROM (
            SELECT f.group_id, count(o.id) AS remaining
            FROM _filter_groups f LEFT JOIN source_item_choice_options o ON o.group_id = f.group_id
            GROUP BY f.group_id
        ) sub
        WHERE g.id = sub.group_id AND sub.remaining > 0 AND g.pick_count > sub.remaining
        """
    )
    op.execute(
        """
        DELETE FROM source_item_choice_groups g USING _filter_groups f
        WHERE g.id = f.group_id AND NOT EXISTS (SELECT 1 FROM source_item_choice_options o WHERE o.group_id = g.id)
        """
    )
    op.drop_constraint("ck_choice_option_item_or_filter", "source_item_choice_options", type_="check")
    for column in ("tool_category", "armor_category", "weapon_category", "kind"):
        op.drop_column("source_item_choice_options", column)
    op.alter_column("source_item_choice_options", "item_id", nullable=False)


def _downgrade_items() -> None:
    op.add_column("items", sa.Column("item_type", sa.String(30), nullable=True))
    op.add_column("items", sa.Column("weapon_properties", sa.String(300), nullable=True))
    op.add_column("items", sa.Column("damage_dice_count", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("damage_dice_type", _DICE, nullable=True))
    op.add_column("items", sa.Column("damage_type", _DAMAGE, nullable=True))
    op.add_column("items", sa.Column("armor_class_base", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("armor_class_dex_bonus", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("items", sa.Column("armor_class_max_dex_bonus", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("strength_requirement", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("stealth_disadvantage", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.execute(
        """
        UPDATE items i SET item_type = CASE
            WHEN i.kind = 'GEAR' THEN COALESCE(i.subtype, 'OTHER')
            WHEN EXISTS (SELECT 1 FROM item_armor_details d WHERE d.item_id = i.id AND d.armor_category = 'SHIELD')
                THEN 'SHIELD'
            ELSE i.kind END
        """
    )
    op.alter_column("items", "item_type", nullable=False)
    sets = ", ".join(f"{column} = d.{column}" for column in _WEAPON_COLUMNS)
    op.execute(f"UPDATE items i SET {sets} FROM item_weapon_details d WHERE d.item_id = i.id")
    sets = ", ".join(f"{column} = d.{column}" for column in _ARMOR_COLUMNS)
    op.execute(
        f"UPDATE items i SET {sets}, armor_class_dex_bonus = "
        f"(d.armor_category IS NULL OR d.armor_category NOT IN ('HEAVY', 'SHIELD')) "
        f"FROM item_armor_details d WHERE d.item_id = i.id"
    )
    # Back to the old tokens (FINESSE, LIGHT…); a homebrew property becomes its upper-cased name.
    op.execute(
        f"""
        UPDATE items i SET weapon_properties = left(sub.props, 300)
        FROM (
            SELECT l.item_id, string_agg(COALESCE(m.token, upper(p.name)), ',' ORDER BY p.name) AS props
            FROM item_weapon_properties l
            JOIN weapon_properties p ON p.id = l.property_id
            LEFT JOIN (VALUES {_token_names()}) AS m(token, name) ON m.name = p.name
            GROUP BY l.item_id
        ) sub
        WHERE sub.item_id = i.id
        """
    )
    # The original columns had no server default.
    op.alter_column("items", "armor_class_dex_bonus", server_default=None)
    op.alter_column("items", "stealth_disadvantage", server_default=None)

    op.drop_constraint("ck_items_magic_bonus", "items", type_="check")
    op.drop_constraint("ck_items_subtype_gear_only", "items", type_="check")
    op.drop_index("ix_items_subtype", table_name="items")
    op.drop_index("ix_items_kind", table_name="items")
    for column in ("magic_bonus", "subtype", "kind"):
        op.drop_column("items", column)

    for table in reversed(_DETAIL_TABLES):
        op.drop_table(table)
    op.drop_table("item_weapon_properties")
    op.drop_table("weapon_properties")


def downgrade() -> None:
    _downgrade_effects()
    _downgrade_choice_options()
    op.drop_column("character_items", "is_attuned")
    op.drop_column("character_items", "is_equipped")
    _downgrade_items()
