import uuid
from uuid import UUID

from app.emails.sender import send_email_async
from app.exceptions.registration_exceptions import (
    RegistrationAlreadyExistsException,
    RegistrationNotFoundException,
)
from app.registration.repository import RegistrationRepository
from app.registration.schemas import (
    ApproveResponse,
    RegistrationRequest,
    RegistrationResponse,
    RegistrationsResponse,
    RejectResponse,
)
from app.users.schemas import UserCreate
from app.users.services import UserService


class RegistrationService:
    def __init__(self, repo: RegistrationRepository, user_service: UserService):
        self.repo = repo
        self.user_service = user_service

    async def submit_application(self, data: RegistrationRequest) -> RegistrationResponse:
        self.user_service.check_username_exists(data.username)
        self.user_service.check_email_exists(data.email)

        if await self.repo.redis.exists(f"registration:email:{data.email}") > 0:
            raise RegistrationAlreadyExistsException("email")
        if await self.repo.redis.exists(f"registration:username:{data.username}") > 0:
            raise RegistrationAlreadyExistsException("username")

        reg_id = str(uuid.uuid4())
        data_dict = data.model_dump()
        await self.repo.save_application(reg_id, data_dict)

        saved = await self.repo.get_application(reg_id)
        if not saved:
            raise RegistrationNotFoundException()

        saved_clean = saved.copy()
        if "password" in saved_clean:
            del saved_clean["password"]

        return RegistrationResponse(**saved_clean, registration_id=UUID(reg_id))

    async def approve_application(self, registration_id: str) -> ApproveResponse:
        data = await self.repo.get_application(registration_id)
        if not data:
            raise RegistrationNotFoundException()

        self.user_service.create_user(UserCreate(**data))
        await self.repo.delete_application(registration_id)
        await send_email_async(
            subject="Вашу заявку схвалено",
            email_to=data["email"],
            body="""
                <html>
                    <body>
                        <h1>Вітаємо!</h1>
                        <p>Вашу заявку <b>схвалено</b>.</p>
                    </body>
                </html>
            """,
        )

        return ApproveResponse(detail="Approved")

    async def reject_application(self, registration_id: str) -> RejectResponse:
        data = await self.repo.get_application(registration_id)
        if not data:
            raise RegistrationNotFoundException()

        await self.repo.delete_application(registration_id)
        await send_email_async(
            subject="Вашу заявку було відхилено",
            email_to=data["email"],
            body="""
                <html>
                    <body>
                        <h1>Вітаємо!</h1>
                        <p>Вашу заявку <b>відхилено</b>.</p>
                    </body>
                </html>
            """,
        )

        return RejectResponse(detail="Registration rejected successfully.")

    async def list_applications(self, skip: int, limit: int) -> RegistrationsResponse:
        items = await self.repo.list_applications(skip, limit)
        return RegistrationsResponse(total=len(items), items=[RegistrationResponse(**item) for item in items])

    async def get_application_by_id(self, registration_id: str) -> RegistrationResponse:
        app = await self.repo.get_application(registration_id)
        if not app:
            raise RegistrationNotFoundException()

        return RegistrationResponse(**app, registration_id=UUID(registration_id))
