from fastapi import status
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_submit_registration(async_client: AsyncClient, registration_data):
    response = await async_client.post("/registrations/", json=registration_data)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "registration_id" in data
    assert data["email"] == registration_data["email"]
    print("RESPONSE", response.status_code, response.json())

@pytest.mark.asyncio
async def test_approve_registration(async_client: AsyncClient, test_admin_token, reg_id):
    response = await async_client.post(
        f"/registrations/submit?registration_id={reg_id}",
        headers={"Authorization": f"Bearer {test_admin_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["detail"] == "Approved"

@pytest.mark.asyncio
async def test_reject_registration(async_client: AsyncClient, test_admin_token, reg_id):
    response = await async_client.delete(
        f"/registrations/{reg_id}",
        headers={"Authorization": f"Bearer {test_admin_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["detail"] == "Registration rejected successfully."

@pytest.mark.asyncio
async def test_list_applications(async_client: AsyncClient, test_admin_token):
    response = await async_client.get("/registrations/", headers={"Authorization": f"Bearer {test_admin_token.credentials}"})
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_get_application_by_id(async_client: AsyncClient, test_admin_token, reg_id):
    response = await async_client.get(f"/registrations/{reg_id}", headers={"Authorization": f"Bearer {test_admin_token.credentials}"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["registration_id"] == reg_id
