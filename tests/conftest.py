"""
Shared pytest fixtures: test-stage env, HTTP client, DB factories, and auth helpers.

The module forces ``STAGE=test`` (and default ``TEST_*`` URLs matching the
``docker-compose.dev.yml`` test services) before anything else imports ``app``,
so ``app.settings`` always resolves to ``app.settings.test``.

Database/schema fixtures (``prepare_database``, ``db_session``, ``redis_client``)
live in ``tests/integration/conftest.py`` — they need the ``heof-test-db`` /
``heof-test-redis`` containers, so unit tests never pull them in.
"""

import os

os.environ["STAGE"] = "test"
os.environ.setdefault("TEST_DATABASE_URL", "postgresql://heof_user:test_secret@localhost:5433/heof_test_db")
os.environ.setdefault("TEST_REDIS_URL", "redis://localhost:6381/0")

from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402

from app.constants import UserRole  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Background,
    Character,
    Class,
    Feat,
    Feature,
    Item,
    Race,
    Skill,
    Spell,
    Subclass,
    User,
)
from app.settings import settings  # noqa: E402

assert settings.STAGE == "test", "Tests must run against the test stage (STAGE=test)."


@pytest.fixture
def client(db_session):
    """TestClient bound to the test DB via a get_db dependency override."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[settings.get_db] = _override_get_db
    try:
        with TestClient(app, base_url="https://testserver/api") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def create_user(db_session):
    """Factory fixture for creating users directly in the database."""

    def _create_user(
        username="player1",
        email="player1@example.com",
        password="password123",
        role=UserRole.PLAYER,
    ):
        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture
def player(create_user):
    """A default PLAYER user."""
    return create_user()


@pytest.fixture
def gm(create_user):
    """A default GM user."""
    return create_user(username="gm1", email="gm1@example.com", role=UserRole.GM)


@pytest.fixture
def founder(create_user):
    """A default found-father (founder) user."""
    return create_user(username="founder1", email="founder1@example.com", role=UserRole.FOUND_FATHER)


@pytest.fixture
def create_skill(db_session):
    def _create_skill(key="PERCEPTION", name="Perception", ability="WIS", description=""):
        skill = Skill(key=key, name=name, ability=ability, description=description)
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)
        return skill

    return _create_skill


@pytest.fixture
def create_race(db_session):
    def _create_race(name="Elf", size="MEDIUM", speed=30, description="", is_homebrew=False):
        race = Race(
            name=name,
            size=size,
            speed=speed,
            description=description,
            is_homebrew=is_homebrew,
        )
        db_session.add(race)
        db_session.commit()
        db_session.refresh(race)
        return race

    return _create_race


@pytest.fixture
def create_class(db_session):
    def _create_class(
        name="Fighter",
        hit_dice="D10",
        skill_choice_count=2,
        spellcasting_ability=None,
        description="",
        is_homebrew=False,
    ):
        class_model = Class(
            name=name,
            hit_dice=hit_dice,
            skill_choice_count=skill_choice_count,
            spellcasting_ability=spellcasting_ability,
            description=description,
            is_homebrew=is_homebrew,
        )
        db_session.add(class_model)
        db_session.commit()
        db_session.refresh(class_model)
        return class_model

    return _create_class


@pytest.fixture
def create_subclass(db_session):
    def _create_subclass(
        class_id,
        name="Champion",
        unlock_level=3,
        archetype_group_name=None,
        description="",
        is_homebrew=False,
    ):
        subclass = Subclass(
            class_id=class_id,
            name=name,
            unlock_level=unlock_level,
            archetype_group_name=archetype_group_name,
            description=description,
            is_homebrew=is_homebrew,
        )
        db_session.add(subclass)
        db_session.commit()
        db_session.refresh(subclass)
        return subclass

    return _create_subclass


@pytest.fixture
def create_background(db_session):
    def _create_background(name="Acolyte", is_homebrew=False):
        background = Background(name=name, is_homebrew=is_homebrew)
        db_session.add(background)
        db_session.commit()
        db_session.refresh(background)
        return background

    return _create_background


@pytest.fixture
def create_feat(db_session):
    def _create_feat(
        name="Alert",
        description="",
        prerequisite_ability=None,
        prerequisite_minimum_score=None,
        prerequisite_description="",
        is_homebrew=False,
    ):
        feat = Feat(
            name=name,
            description=description,
            prerequisite_ability=prerequisite_ability,
            prerequisite_minimum_score=prerequisite_minimum_score,
            prerequisite_description=prerequisite_description,
            is_homebrew=is_homebrew,
        )
        db_session.add(feat)
        db_session.commit()
        db_session.refresh(feat)
        return feat

    return _create_feat


@pytest.fixture
def create_feature(db_session):
    def _create_feature(
        name="Extra Attack",
        source_type="CLASS",
        class_id=None,
        subclass_id=None,
        race_id=None,
        background_id=None,
        feat_id=None,
        level=None,
        is_homebrew=False,
    ):
        feature = Feature(
            name=name,
            source_type=source_type,
            class_id=class_id,
            subclass_id=subclass_id,
            race_id=race_id,
            background_id=background_id,
            feat_id=feat_id,
            level=level,
            is_homebrew=is_homebrew,
        )
        db_session.add(feature)
        db_session.commit()
        db_session.refresh(feature)
        return feature

    return _create_feature


@pytest.fixture
def create_item(db_session):
    def _create_item(
        name="Longsword",
        item_type="WEAPON",
        rarity="NONE",
        requires_attunement=False,
        description="",
        is_homebrew=False,
    ):
        item = Item(
            name=name,
            item_type=item_type,
            rarity=rarity,
            requires_attunement=requires_attunement,
            description=description,
            is_homebrew=is_homebrew,
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)
        return item

    return _create_item


@pytest.fixture
def create_spell(db_session):
    def _create_spell(
        name="Cure Wounds",
        school="EVOCATION",
        level="LEVEL_1",
        cast_time="ACTION",
        range_type="TOUCH",
        duration="INSTANTANEOUS",
        components=None,
        description="",
        is_homebrew=False,
    ):
        spell = Spell(
            name=name,
            school=school,
            level=level,
            cast_time=cast_time,
            range_type=range_type,
            components=components if components is not None else [],
            duration=duration,
            description=description,
            is_homebrew=is_homebrew,
        )
        db_session.add(spell)
        db_session.commit()
        db_session.refresh(spell)
        return spell

    return _create_spell


@pytest.fixture
def create_character(db_session):
    def _create_character(
        owner_id,
        class_id,
        name="Test Character",
        level=1,
        race_id=None,
        background_id=None,
        subclass_id=None,
        **kwargs,
    ):
        character = Character(
            owner_id=owner_id,
            class_id=class_id,
            name=name,
            level=level,
            race_id=race_id,
            background_id=background_id,
            subclass_id=subclass_id,
            **kwargs,
        )
        db_session.add(character)
        db_session.commit()
        db_session.refresh(character)
        return character

    return _create_character


DEFAULT_PASSWORD = "password123"


@pytest.fixture
def login_as(client):
    """Log in a user via the API and return the access token."""

    def _login_as(user, password=DEFAULT_PASSWORD):
        response = client.post("/auth/login", json={"email": user.email, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return _login_as


@pytest.fixture
def player_token(player, login_as):
    return login_as(player)


@pytest.fixture
def gm_token(gm, login_as):
    return login_as(gm)


@pytest.fixture
def founder_token(founder, login_as):
    return login_as(founder)
