"""Regression guard for the effect tree fan-out: how many SQL statements each feature operation issues."""

from contextlib import contextmanager

import pytest
import pytest_asyncio
from sqlalchemy import event

from tests.helpers import set_choice_groups, set_effects


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def count_statements(db_session):
    statements: list[str] = []
    engine = db_session.bind.sync_engine

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest_asyncio.fixture
async def feature_with_tree(client, gm_token, create_feature, create_skill):
    feature_id = (await create_feature(name="Tree", source_type="OTHER")).id
    skill_id = (await create_skill(name="Stealth")).id
    await set_effects(
        client,
        gm_token,
        feature_id,
        {
            "static_groups": [
                {"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]},
                {"effect_type": "skill", "items": [{"skill_id": skill_id}]},
            ]
        },
    )
    await set_choice_groups(
        client,
        gm_token,
        feature_id,
        {
            "choice_groups": [
                {
                    "choice_type": "SKILL",
                    "options": [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill_id}]}]}],
                }
            ]
        },
    )
    return feature_id


@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryBudget:
    async def test_get_effects_loads_the_tree_once(self, client, db_session, feature_with_tree):
        with count_statements(db_session) as statements:
            response = await client.get(f"/features/{feature_with_tree}/effects")

        assert response.status_code == 200
        assert len(statements) <= 17

    async def test_get_choice_groups_does_not_load_fixed_effects(self, client, db_session, feature_with_tree):
        with count_statements(db_session) as statements:
            response = await client.get(f"/features/{feature_with_tree}/choice-groups")

        assert response.status_code == 200
        assert len(statements) <= 11

    async def test_patch_loads_the_tree_once(self, client, gm_token, db_session, feature_with_tree):
        with count_statements(db_session) as statements:
            response = await client.patch(
                f"/features/{feature_with_tree}", json={"description": "new"}, headers=auth(gm_token)
            )

        assert response.status_code == 200
        assert len(statements) <= 25

    async def test_create_issues_no_tree_queries(self, client, gm_token, db_session):
        with count_statements(db_session) as statements:
            response = await client.post(
                "/features", json={"name": "Brand New", "source_type": "OTHER"}, headers=auth(gm_token)
            )

        assert response.status_code == 201
        assert len(statements) <= 6
