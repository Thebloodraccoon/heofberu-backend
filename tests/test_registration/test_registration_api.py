import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_submit_registration(client: AsyncClient, registration_data):
    response = await client.post("/registration/", json=registration_data)
    assert response.status_code == 200
    data = response.json()
    assert "registration_id" in data
    assert data["email"] == registration_data["email"]


@pytest.mark.asyncio
async def test_approve_registration(client: AsyncClient, admin_token, reg_id):
    response = await client.post(
        f"/registration/submit?registration_id={reg_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Approved"


@pytest.mark.asyncio
async def test_reject_registration(client: AsyncClient, admin_token, reg_id):
    response = await client.delete(
        f"/registration/{reg_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Registration rejected successfully."


@pytest.mark.asyncio
async def test_list_applications(client: AsyncClient, admin_token):
    response = await client.get(
        "/registration/",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_application_by_id(client: AsyncClient, admin_token, reg_id):
    response = await client.get(
        f"/registration/{reg_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["registration_id"] == reg_id

    