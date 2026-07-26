"""Update models arch

Revision ID: 69038c284ea4
Revises: bb20790b5a8c
Create Date: 2026-07-26 16:20:28.333101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '69038c284ea4'
down_revision: Union[str, None] = 'bb20790b5a8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### manually adjusted: explicitly create enum types first ###

    def _create_enum_safely(enum_name, values):
        values_sql = ", ".join(f"'{v}'" for v in values)
        op.execute(
            f"""
            DO $$
            BEGIN
                CREATE TYPE {enum_name} AS ENUM ({values_sql});
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
            """
        )

    _create_enum_safely('ability_score', ['STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'])
    _create_enum_safely('attack_type', ['MELEE_ATTACK', 'RANGED_ATTACK'])
    _create_enum_safely('damage_type', [
        'SLASHING', 'PIERCING', 'BLUDGEONING', 'ACID', 'COLD', 'FIRE', 'FORCE',
        'LIGHTNING', 'NECROTIC', 'POISON', 'PSYCHIC', 'RADIANT', 'THUNDER',
    ])
    _create_enum_safely('spell_school', [
        'ABJURATION', 'CONJURATION', 'DIVINATION', 'ENCHANTMENT', 'EVOCATION',
        'ILLUSION', 'NECROMANCY', 'TRANSMUTATION',
    ])
    _create_enum_safely('spell_level', [
        'CANTRIP', 'LEVEL_1', 'LEVEL_2', 'LEVEL_3', 'LEVEL_4', 'LEVEL_5',
        'LEVEL_6', 'LEVEL_7', 'LEVEL_8', 'LEVEL_9',
    ])
    _create_enum_safely('spell_range_type', ['SELF', 'TOUCH', 'RANGED', 'SIGHT', 'UNLIMITED'])
    _create_enum_safely('race_size', ['TINY', 'SMALL', 'MEDIUM', 'LARGE', 'HUGE', 'GARGANTUAN'])
    _create_enum_safely('user_role', ['GM', 'PLAYER'])

    op.create_table('skills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_skills_key'), 'skills', ['key'], unique=True)
    op.create_table('classes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('hit_dice', sa.String(length=10), nullable=False),
    sa.Column('skill_choice_count', sa.Integer(), nullable=False),
    sa.Column('spellcasting_ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_homebrew', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_classes_created_by_id'), 'classes', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_classes_name'), 'classes', ['name'], unique=True)
    op.create_table('races',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('size', postgresql.ENUM('TINY', 'SMALL', 'MEDIUM', 'LARGE', 'HUGE', 'GARGANTUAN', name='race_size', create_type=False), nullable=False),
    sa.Column('speed', sa.Integer(), nullable=False),
    sa.Column('traits', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_homebrew', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_races_created_by_id'), 'races', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_races_name'), 'races', ['name'], unique=True)
    op.create_table('spells',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('school', postgresql.ENUM('ABJURATION', 'CONJURATION', 'DIVINATION', 'ENCHANTMENT', 'EVOCATION', 'ILLUSION', 'NECROMANCY', 'TRANSMUTATION', name='spell_school', create_type=False), nullable=False),
    sa.Column('level', postgresql.ENUM('CANTRIP', 'LEVEL_1', 'LEVEL_2', 'LEVEL_3', 'LEVEL_4', 'LEVEL_5', 'LEVEL_6', 'LEVEL_7', 'LEVEL_8', 'LEVEL_9', name='spell_level', create_type=False), nullable=False),
    sa.Column('cast_time', sa.String(length=50), nullable=False),
    sa.Column('range_type', postgresql.ENUM('SELF', 'TOUCH', 'RANGED', 'SIGHT', 'UNLIMITED', name='spell_range_type', create_type=False), nullable=False),
    sa.Column('range_value', sa.Integer(), nullable=True),
    sa.Column('components', sa.String(length=100), nullable=False),
    sa.Column('material', sa.Text(), nullable=True),
    sa.Column('is_ritual', sa.Boolean(), nullable=False),
    sa.Column('duration', sa.String(length=50), nullable=False),
    sa.Column('is_concentration', sa.Boolean(), nullable=False),
    sa.Column('attack_type', postgresql.ENUM('MELEE_ATTACK', 'RANGED_ATTACK', name='attack_type', create_type=False), nullable=True),
    sa.Column('save_stat', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=True),
    sa.Column('damage_type', postgresql.ENUM('SLASHING', 'PIERCING', 'BLUDGEONING', 'ACID', 'COLD', 'FIRE', 'FORCE', 'LIGHTNING', 'NECROTIC', 'POISON', 'PSYCHIC', 'RADIANT', 'THUNDER', name='damage_type', create_type=False), nullable=True),
    sa.Column('damage_dice', sa.String(length=30), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('higher_levels', sa.Text(), nullable=True),
    sa.Column('is_homebrew', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_spells_created_by_id'), 'spells', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_spells_level'), 'spells', ['level'], unique=False)
    op.create_index(op.f('ix_spells_name'), 'spells', ['name'], unique=True)
    op.create_table('characters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('image_path', sa.String(length=500), nullable=True),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('subclass', sa.String(length=100), nullable=False),
    sa.Column('race_id', sa.Integer(), nullable=True),
    sa.Column('current_hp', sa.Integer(), nullable=False),
    sa.Column('max_hp', sa.Integer(), nullable=False),
    sa.Column('temp_hp', sa.Integer(), nullable=False),
    sa.Column('hit_dice', sa.String(length=20), nullable=False),
    sa.Column('speed', sa.Integer(), nullable=False),
    sa.Column('armor_class', sa.Integer(), nullable=False),
    sa.Column('shield', sa.Integer(), nullable=False),
    sa.Column('initiative_bonus', sa.Integer(), nullable=False),
    sa.Column('passive_perception_bonus', sa.Integer(), nullable=False),
    sa.Column('has_jack_of_all_trades', sa.Boolean(), nullable=False),
    sa.Column('strength', sa.Integer(), nullable=False),
    sa.Column('dexterity', sa.Integer(), nullable=False),
    sa.Column('constitution', sa.Integer(), nullable=False),
    sa.Column('intelligence', sa.Integer(), nullable=False),
    sa.Column('wisdom', sa.Integer(), nullable=False),
    sa.Column('charisma', sa.Integer(), nullable=False),
    sa.Column('proficiencies', sa.Text(), nullable=False),
    sa.Column('traits', sa.Text(), nullable=False),
    sa.Column('feats', sa.Text(), nullable=False),
    sa.Column('inventory', sa.Text(), nullable=False),
    sa.Column('backstory', sa.Text(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('money_gold', sa.Integer(), nullable=False),
    sa.Column('money_silver', sa.Integer(), nullable=False),
    sa.Column('money_copper', sa.Integer(), nullable=False),
    sa.Column('spell_ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=True),
    sa.Column('spell_dc_misc_bonus', sa.Integer(), nullable=False),
    sa.Column('spell_attack_misc_bonus', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('current_hp >= 0', name='check_current_hp_nonnegative'),
    sa.CheckConstraint('level >= 1 AND level <= 20', name='check_character_level_range'),
    sa.CheckConstraint('max_hp >= 0', name='check_max_hp_nonnegative'),
    sa.CheckConstraint('temp_hp >= 0', name='check_temp_hp_nonnegative'),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['race_id'], ['races.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_characters_class_id'), 'characters', ['class_id'], unique=False)
    op.create_index(op.f('ix_characters_name'), 'characters', ['name'], unique=False)
    op.create_index(op.f('ix_characters_owner_id'), 'characters', ['owner_id'], unique=False)
    op.create_index(op.f('ix_characters_race_id'), 'characters', ['race_id'], unique=False)
    op.create_table('class_available_skills',
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('class_id', 'skill_id')
    )
    op.create_table('class_primary_abilities',
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('class_id', 'ability')
    )
    op.create_table('class_saving_throws',
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('class_id', 'ability')
    )
    op.create_table('race_ability_bonuses',
    sa.Column('race_id', sa.Integer(), nullable=False),
    sa.Column('ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=False),
    sa.Column('bonus', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['race_id'], ['races.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('race_id', 'ability')
    )
    op.create_table('race_skills',
    sa.Column('race_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['race_id'], ['races.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('race_id', 'skill_id')
    )
    op.create_table('attacks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('character_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('attack_type', postgresql.ENUM('MELEE_ATTACK', 'RANGED_ATTACK', name='attack_type', create_type=False), nullable=False),
    sa.Column('ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=False),
    sa.Column('is_proficient', sa.Boolean(), nullable=False),
    sa.Column('bonus_attack', sa.Integer(), nullable=False),
    sa.Column('bonus_damage', sa.Integer(), nullable=False),
    sa.Column('damage_dice', sa.String(length=30), nullable=False),
    sa.Column('damage_type', postgresql.ENUM('SLASHING', 'PIERCING', 'BLUDGEONING', 'ACID', 'COLD', 'FIRE', 'FORCE', 'LIGHTNING', 'NECROTIC', 'POISON', 'PSYCHIC', 'RADIANT', 'THUNDER', name='damage_type', create_type=False), nullable=True),
    sa.Column('range', sa.String(length=50), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attacks_character_id'), 'attacks', ['character_id'], unique=False)
    op.create_table('character_saving_throw_proficiencies',
    sa.Column('character_id', sa.Integer(), nullable=False),
    sa.Column('ability', postgresql.ENUM('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA', name='ability_score', create_type=False), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('character_id', 'ability')
    )
    op.create_table('character_skill_proficiencies',
    sa.Column('character_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('is_expertise', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('character_id', 'skill_id')
    )
    op.create_table('character_spell_slots',
    sa.Column('character_id', sa.Integer(), nullable=False),
    sa.Column('spell_level', postgresql.ENUM('CANTRIP', 'LEVEL_1', 'LEVEL_2', 'LEVEL_3', 'LEVEL_4', 'LEVEL_5', 'LEVEL_6', 'LEVEL_7', 'LEVEL_8', 'LEVEL_9', name='spell_level', create_type=False), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('used', sa.Integer(), nullable=False),
    sa.CheckConstraint('used <= total', name='check_spell_slot_used_not_exceeding_total'),
    sa.CheckConstraint('used >= 0', name='check_spell_slot_used_nonnegative'),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('character_id', 'spell_level')
    )
    op.create_table('character_spells',
                    sa.Column('character_id', sa.Integer(), nullable=False),
                    sa.Column('spell_id', sa.Integer(), nullable=False),
                    sa.Column('is_prepared', sa.Boolean(), nullable=False),
                    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
                    sa.ForeignKeyConstraint(['spell_id'], ['spells.id'], ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('character_id', 'spell_id')
                    )
    op.drop_constraint('check_user_role', 'users', type_='check')
    op.execute("UPDATE users SET role = UPPER(role)")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::text::user_role")
    op.alter_column('users', 'role', server_default='PLAYER')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### manually adjusted ###
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR USING role::text")
    op.execute("UPDATE users SET role = LOWER(role)")
    op.alter_column('users', 'role', server_default='player')
    op.drop_table('character_spells')
    op.drop_table('character_spell_slots')
    op.drop_table('character_skill_proficiencies')
    op.drop_table('character_saving_throw_proficiencies')
    op.drop_index(op.f('ix_attacks_character_id'), table_name='attacks')
    op.drop_table('attacks')
    op.drop_table('race_skills')
    op.drop_table('race_ability_bonuses')
    op.drop_table('class_saving_throws')
    op.drop_table('class_primary_abilities')
    op.drop_table('class_available_skills')
    op.drop_index(op.f('ix_characters_race_id'), table_name='characters')
    op.drop_index(op.f('ix_characters_owner_id'), table_name='characters')
    op.drop_index(op.f('ix_characters_name'), table_name='characters')
    op.drop_index(op.f('ix_characters_class_id'), table_name='characters')
    op.drop_table('characters')
    op.drop_index(op.f('ix_spells_name'), table_name='spells')
    op.drop_index(op.f('ix_spells_level'), table_name='spells')
    op.drop_index(op.f('ix_spells_created_by_id'), table_name='spells')
    op.drop_table('spells')
    op.drop_index(op.f('ix_races_name'), table_name='races')
    op.drop_index(op.f('ix_races_created_by_id'), table_name='races')
    op.drop_table('races')
    op.drop_index(op.f('ix_classes_name'), table_name='classes')
    op.drop_index(op.f('ix_classes_created_by_id'), table_name='classes')
    op.drop_table('classes')
    op.drop_index(op.f('ix_skills_key'), table_name='skills')
    op.drop_table('skills')
    # ### end Alembic commands ###

    # --- drop enum types explicitly (mirrors explicit creation in upgrade()) ---
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS race_size")
    op.execute("DROP TYPE IF EXISTS spell_range_type")
    op.execute("DROP TYPE IF EXISTS spell_level")
    op.execute("DROP TYPE IF EXISTS spell_school")
    op.execute("DROP TYPE IF EXISTS damage_type")
    op.execute("DROP TYPE IF EXISTS attack_type")
    op.execute("DROP TYPE IF EXISTS ability_score")