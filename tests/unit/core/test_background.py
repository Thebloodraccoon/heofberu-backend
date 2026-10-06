"""Unit tests for the fail-safe background task helper."""

import logging

from fastapi import BackgroundTasks
import pytest

from app.core.background import add_safe_task


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddSafeTask:
    async def test_task_is_deferred_and_receives_arguments(self):
        calls = []

        async def work(a, b, *, c):
            calls.append((a, b, c))

        tasks = BackgroundTasks()
        add_safe_task(tasks, work, 1, 2, c=3)

        assert calls == []
        await tasks()
        assert calls == [(1, 2, 3)]

    async def test_failure_is_logged_and_not_raised(self, caplog):
        async def boom():
            raise RuntimeError("smtp down")

        tasks = BackgroundTasks()
        add_safe_task(tasks, boom)

        with caplog.at_level(logging.ERROR, logger="app.core.background"):
            await tasks()

        assert "boom" in caplog.text
        assert "smtp down" in caplog.text

    async def test_failing_task_does_not_block_the_next_one(self):
        ran = []

        async def boom():
            raise RuntimeError("x")

        async def ok():
            ran.append(True)

        tasks = BackgroundTasks()
        add_safe_task(tasks, boom)
        add_safe_task(tasks, ok)
        await tasks()

        assert ran == [True]
