"""Helper for post-response work: failures are logged and never reach the client."""

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)


async def _run_safely(func: Callable[..., Awaitable[Any]], args: tuple, kwargs: dict) -> None:
    try:
        await func(*args, **kwargs)
    except Exception:  # noqa: BLE001 - background work must never surface an error
        logger.exception("Background task %s failed", getattr(func, "__qualname__", func))


def add_safe_task(tasks: BackgroundTasks, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> None:
    """
    Schedule the coroutine function ``func`` to run after the response is sent.

    Any exception it raises is logged instead of propagating, so a failing
    side effect (email, storage cleanup) can never turn into a client error.
    """

    tasks.add_task(_run_safely, func, args, kwargs)
