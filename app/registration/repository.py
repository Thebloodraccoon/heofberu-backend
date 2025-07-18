from collections.abc import Awaitable
import json
from typing import Any, cast

from redis.asyncio import Redis


class RegistrationRepository:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def save_application(self, registration_id: str, data: dict[str, Any]) -> None:
        key = f"registration:{registration_id}"
        await cast(Awaitable[int], self.redis.set(key, json.dumps(data), ex=30 * 24 * 60 * 60))
        await cast(Awaitable[int], self.redis.sadd("registrations:pending", registration_id))
        await cast(Awaitable[int], self.redis.set(f"registration:email:{data['email']}", registration_id))
        await cast(Awaitable[int], self.redis.set(f"registration:username:{data['username']}", registration_id))

    async def get_application(self, registration_id: str) -> dict[str, Any] | None:
        key = f"registration:{registration_id}"
        value = await cast(Awaitable[bytes | None], self.redis.get(key))
        return json.loads(value) if value else None

    async def list_applications(self, skip: int, limit: int) -> list[dict[str, Any]]:
        ids_raw = await cast(Awaitable[set[bytes]], self.redis.smembers("registrations:pending"))
        ids = [x.decode("utf-8") for x in ids_raw][skip : skip + limit]

        result: list[dict[str, Any]] = []
        for reg_id in ids:
            app = await self.get_application(reg_id)
            if app:
                app["registration_id"] = reg_id
                result.append(app)
        return result

    async def delete_application(self, registration_id: str) -> None:
        app = await self.get_application(registration_id)
        if app:
            await cast(Awaitable[int], self.redis.delete(f"registration:email:{app['email']}"))
            await cast(Awaitable[int], self.redis.delete(f"registration:username:{app['username']}"))
        await cast(Awaitable[int], self.redis.delete(f"registration:{registration_id}"))
        await cast(Awaitable[int], self.redis.srem("registrations:pending", registration_id))
