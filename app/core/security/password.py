"""
Password hashing and verification helpers (bcrypt via passlib).

bcrypt costs ~100-300 ms of CPU, so the async wrappers run the sync
passlib calls in a worker thread (``anyio.to_thread``) — calling them
directly from ``async def`` endpoints would stall the event loop for
every other request during login/register bursts.
"""

import anyio.to_thread
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash (blocking — prefer :func:`verify_password_async`)."""

    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a hash from a plain password (blocking — prefer :func:`get_password_hash_async`)."""

    return pwd_context.hash(password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash off the event loop."""

    return await anyio.to_thread.run_sync(pwd_context.verify, plain_password, hashed_password)


async def get_password_hash_async(password: str) -> str:
    """Generate a hash from a plain password off the event loop."""

    return await anyio.to_thread.run_sync(pwd_context.hash, password)
