import pytest


@pytest.mark.asyncio
async def test_save_and_get_application(redis_repo, registration_data):
    reg_id = "test-reg-id"
    await redis_repo.save_application(reg_id, registration_data.model_dump())
    app = await redis_repo.get_application(reg_id)
    assert app["email"] == registration_data.email


@pytest.mark.asyncio
async def test_delete_application(redis_repo, registration_data):
    reg_id = "test-reg-id"
    await redis_repo.save_application(reg_id, registration_data.model_dump())
    await redis_repo.delete_application(reg_id)
    app = await redis_repo.get_application(reg_id)
    assert app is None