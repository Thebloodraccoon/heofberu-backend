import uuid

from fastapi import HTTPException

from app.core.dependencies import UserServiceDep
from app.registration.repository import RegistrationRepository
from app.users.schemas import UserCreate


class RegistrationService:
    def __init__(self, repo: RegistrationRepository, user_service: UserServiceDep):
        self.repo = repo
        self.user_service = user_service

    async def submit_application(self, data: dict):
        if await self.repo.redis.exists(f"registration:email:{data['email']}"):
            raise HTTPException(status_code=409, detail="Email already used in pending registration")
        if await self.repo.redis.exists(f"registration:username:{data['username']}"):
            raise HTTPException(status_code=409, detail="Username already used in pending registration")

        reg_id = str(uuid.uuid4())
        await self.repo.save_application(reg_id, data)
        return reg_id

    async def approve_application(self, registration_id: str):
        data = await self.repo.get_application(registration_id)
        if not data:
            raise HTTPException(status_code=404, detail="Registration not found")

        self.user_service.create_user(UserCreate(**data))
        await self.repo.delete_application(registration_id)
