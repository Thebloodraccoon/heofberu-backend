"""Test helpers: the ``[{effect_type, items}]`` effect-group shape and "set the whole state" setup built on the point endpoints."""


def effect_items(groups: list, effect_type: str) -> list:
    """Items of the ``effect_type`` group in ``groups`` (``[]`` when the bundle has no such group)."""

    return next((group["items"] for group in groups if group["effect_type"] == effect_type), [])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def set_effects(client, token, feature_id, payload, *, base="/features"):
    """
    Make ``payload["static_groups"]`` the fixed effects of each type it names (setup shorthand).

    Built from the point endpoints: POST the new groups, then DELETE the rows the feature had of those
    types. Returns the first failing response (nothing is deleted then), otherwise
    ``GET {base}/{feature_id}/effects`` (200, ``{feature_id, choice_groups, static_groups}``).
    """

    url = f"{base}/{feature_id}/effects"
    groups = payload.get("static_groups", [])

    before = await client.get(url)
    if before.status_code != 200:
        return before

    stale = [
        (group["effect_type"], item["id"])
        for group in before.json()["static_groups"]
        if group["effect_type"] in {new["effect_type"] for new in groups}
        for item in group["items"]
    ]

    added = await client.post(url, json={"static_groups": groups}, headers=_auth(token))
    if added.status_code != 201:
        return added

    for effect_type, effect_id in stale:
        removed = await client.delete(f"{url}/{effect_type}/{effect_id}", headers=_auth(token))
        assert removed.status_code == 200, removed.text

    return await client.get(url)


async def set_choice_groups(client, token, feature_id, payload, *, base="/features"):
    """
    Make ``payload["choice_groups"]`` the feature's whole choice-group tree (setup shorthand).

    Built from the point endpoints: POST each new group, then DELETE the groups the feature had. A failing POST
    rolls the created groups back and its response is returned. Otherwise returns
    ``GET {base}/{feature_id}/choice-groups`` (200, list of groups).
    """

    url = f"{base}/{feature_id}/choice-groups"

    before = await client.get(url)
    if before.status_code != 200:
        return before

    created = []
    for group in payload.get("choice_groups", []):
        added = await client.post(url, json=group, headers=_auth(token))
        if added.status_code != 201:
            for group_id in created:
                await client.delete(f"{url}/{group_id}", headers=_auth(token))
            return added
        created.append(max(g["id"] for g in added.json()))

    for old in before.json():
        removed = await client.delete(f"{url}/{old['id']}", headers=_auth(token))
        assert removed.status_code == 200, removed.text

    return await client.get(url)
