"""Article tree: non-GM descendants/ancestors, delete re-rooting, NULL-path safety and the depth cap."""

import pytest
from sqlalchemy import select, text

from app.models.articles.article_model import Article


async def _path(db_session, article_id) -> str | None:
    value = await db_session.scalar(select(Article.path).where(Article.id == article_id))
    db_session.expire_all()
    return None if value is None else str(value)


@pytest.mark.integration
@pytest.mark.asyncio
class TestVisibleTree:
    async def test_descendants_for_non_gm_skip_hidden_intermediate_and_everything_below_it(
        self, client, create_article
    ):
        root = await create_article(title="Root", status="published")
        hidden = await create_article(title="Hidden Mid", parent_id=root["id"])
        await create_article(title="Below Hidden", parent_id=hidden["id"], status="published")
        visible = await create_article(title="Visible Child", parent_id=root["id"], status="published")
        await create_article(title="Visible Grandchild", parent_id=visible["id"], status="published")

        response = await client.get(f"/articles/{root['id']}/descendants")

        assert response.status_code == 200
        assert [d["title"] for d in response.json()] == ["Visible Child", "Visible Grandchild"]

    async def test_descendants_for_gm_include_hidden_nodes(self, client, create_article, gm_token):
        root = await create_article(title="Root", status="published")
        hidden = await create_article(title="Hidden Mid", parent_id=root["id"])
        await create_article(title="Below Hidden", parent_id=hidden["id"], status="published")

        response = await client.get(
            f"/articles/{root['id']}/descendants", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert {d["title"] for d in response.json()} == {"Hidden Mid", "Below Hidden"}

    async def test_descendants_of_hidden_article_is_404_for_non_gm(self, client, create_article):
        root = await create_article(title="Root")

        assert (await client.get(f"/articles/{root['id']}/descendants")).status_code == 404

    async def test_children_for_non_gm_exclude_gm_only(self, client, create_article):
        root = await create_article(title="Root", status="published")
        await create_article(title="Public", parent_id=root["id"], status="published")
        await create_article(title="Secret", parent_id=root["id"], status="published", visibility="gm_only")

        response = await client.get(f"/articles/{root['id']}/children")

        assert [c["title"] for c in response.json()] == ["Public"]

    async def test_ancestors_for_non_gm_skip_a_hidden_ancestor(self, client, create_article):
        root = await create_article(title="Root", status="published")
        hidden = await create_article(title="Hidden Mid", parent_id=root["id"])
        leaf = await create_article(title="Leaf", parent_id=hidden["id"], status="published")

        response = await client.get(f"/articles/{leaf['id']}/ancestors")

        assert [a["title"] for a in response.json()] == ["Root"]

    async def test_public_child_of_hidden_parent_hides_the_parent_id(self, client, create_article):
        hidden = await create_article(title="Hidden Parent")
        child = await create_article(title="Child", parent_id=hidden["id"], status="published")

        anonymous = (await client.get(f"/articles/{child['id']}")).json()

        assert anonymous["parent_id"] is None

    async def test_public_child_of_public_parent_keeps_the_parent_id(self, client, create_article):
        parent = await create_article(title="Parent", status="published")
        child = await create_article(title="Child", parent_id=parent["id"], status="published")

        assert (await client.get(f"/articles/{child['id']}")).json()["parent_id"] == parent["id"]

    async def test_images_are_empty_for_non_gm_but_listed_for_gm(self, client, create_article, gm_token, db_session):
        article = await create_article(title="Gallery", status="published")
        await db_session.execute(
            text(
                "INSERT INTO article_images (article_id, image_url, storage_key) VALUES (:id, 'https://x/y.png', 'k')"
            ),
            {"id": article["id"]},
        )
        await db_session.commit()

        anonymous = (await client.get(f"/articles/{article['id']}")).json()
        gm_view = (
            await client.get(f"/articles/{article['id']}", headers={"Authorization": f"Bearer {gm_token}"})
        ).json()

        assert anonymous["images"] == []
        assert len(gm_view["images"]) == 1

    async def test_children_list_is_capped(self, client, create_article, monkeypatch):
        monkeypatch.setattr("app.features.articles.tree.repository.TREE_LIST_LIMIT", 2)
        root = await create_article(title="Root", status="published")
        for i in range(3):
            await create_article(title=f"Child {i}", parent_id=root["id"], status="published")

        children = await client.get(f"/articles/{root['id']}/children")
        descendants = await client.get(f"/articles/{root['id']}/descendants")

        assert [len(children.json()), len(descendants.json())] == [2, 2]


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteReroots:
    async def test_delete_makes_children_roots_and_keeps_their_subtrees_intact(
        self, client, create_article, founder_token, gm_token, db_session
    ):
        gm = {"Authorization": f"Bearer {gm_token}"}
        top = await create_article(title="Top")
        mid = await create_article(title="Mid", parent_id=top["id"])
        child_a = await create_article(title="Child A", parent_id=mid["id"])
        child_b = await create_article(title="Child B", parent_id=mid["id"])
        grandchild = await create_article(title="Grandchild", parent_id=child_a["id"])

        deleted = await client.delete(f"/articles/{mid['id']}", headers={"Authorization": f"Bearer {founder_token}"})

        assert deleted.status_code == 204
        assert await _path(db_session, child_a["id"]) == str(child_a["id"])
        assert await _path(db_session, child_b["id"]) == str(child_b["id"])
        assert await _path(db_session, grandchild["id"]) == f"{child_a['id']}.{grandchild['id']}"
        ancestors = await client.get(f"/articles/{grandchild['id']}/ancestors", headers=gm)
        assert [a["id"] for a in ancestors.json()] == [child_a["id"]]
        top_descendants = await client.get(f"/articles/{top['id']}/descendants", headers=gm)
        assert top_descendants.json() == []
        assert (await client.get(f"/articles/{child_a['id']}", headers=gm)).json()["parent_id"] is None

    async def test_delete_leaf_does_not_touch_siblings(self, client, create_article, founder_token, db_session):
        root = await create_article(title="Root")
        leaf = await create_article(title="Leaf", parent_id=root["id"])
        sibling = await create_article(title="Sibling", parent_id=root["id"])

        await client.delete(f"/articles/{leaf['id']}", headers={"Authorization": f"Bearer {founder_token}"})

        assert await _path(db_session, sibling["id"]) == f"{root['id']}.{sibling['id']}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestNullPathSafety:
    async def test_cycle_check_does_not_trust_a_missing_path(self, client, create_article, gm_token, db_session):
        parent = await create_article(title="Parent")
        child = await create_article(title="Child", parent_id=parent["id"])
        await db_session.execute(text("UPDATE articles SET path = NULL"))
        await db_session.commit()

        response = await client.patch(
            f"/articles/{parent['id']}",
            json={"parent_id": child["id"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400
        assert "cycle" in response.text

    async def test_child_of_a_pathless_parent_gets_the_full_chain_not_a_root_path(
        self, client, create_article, db_session
    ):
        grand = await create_article(title="Grand")
        parent = await create_article(title="Parent", parent_id=grand["id"])
        await db_session.execute(text("UPDATE articles SET path = NULL"))
        await db_session.commit()

        child = await create_article(title="Child", parent_id=parent["id"])

        assert await _path(db_session, child["id"]) == f"{grand['id']}.{parent['id']}.{child['id']}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestDepthCap:
    async def test_create_below_the_maximum_depth_is_rejected(self, client, create_article, gm_token, monkeypatch):
        monkeypatch.setattr("app.features.articles.tree.repository.MAX_TREE_DEPTH", 3)
        a = await create_article(title="A")
        b = await create_article(title="B", parent_id=a["id"])
        c = await create_article(title="C", parent_id=b["id"])

        response = await client.post(
            "/articles",
            json={"title": "D", "article_type": "location", "parent_id": c["id"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400
        assert "3 levels" in response.text

    async def test_moving_a_deep_subtree_under_a_parent_is_rejected(
        self, client, create_article, gm_token, monkeypatch
    ):
        monkeypatch.setattr("app.features.articles.tree.repository.MAX_TREE_DEPTH", 3)
        x = await create_article(title="X")
        y = await create_article(title="Y", parent_id=x["id"])
        top = await create_article(title="Top")
        deep = await create_article(title="Deep")
        await create_article(title="Deeper", parent_id=deep["id"])

        too_deep = await client.patch(
            f"/articles/{deep['id']}", json={"parent_id": y["id"]}, headers={"Authorization": f"Bearer {gm_token}"}
        )
        fits = await client.patch(
            f"/articles/{deep['id']}", json={"parent_id": top["id"]}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert too_deep.status_code == 400
        assert fits.status_code == 200
