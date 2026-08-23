"""Regression coverage for bounded Relayvia Runner concurrency."""

import asyncio

from app.core.config import Settings
from app.runners import runner as runner_module


class FakeRunnerClient:
    def __init__(self) -> None:
        self.id = "runner-test"
        self.name = "runner-test"
        self.tasks = [
            {"task_id": "one", "lease_token": "one", "config": {}},
            {"task_id": "two", "lease_token": "two", "config": {}},
        ]
        self.submitted: list[str] = []
        self.closed = False

    async def register(self) -> None:
        return None

    async def heartbeat(self) -> None:
        return None

    async def claim(self):
        return self.tasks.pop(0) if self.tasks else None

    async def task_heartbeat(self, _task_id: str, _lease_token: str) -> bool:
        return False

    async def submit(self, task_id: str, _lease_token: str, _result: dict) -> bool:
        self.submitted.append(task_id)
        return True

    async def close(self) -> None:
        self.closed = True


def test_one_runner_processes_independent_tasks_concurrently(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    max_active = 0

    async def fake_execute(_task: dict, *, cancel_event: asyncio.Event | None = None) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            entered.set()
        try:
            await release.wait()
            return {"ok": True, "output": {}}
        finally:
            active -= 1

    monkeypatch.setattr(runner_module, "get_settings", lambda: Settings(worker_poll_interval=0.01, runner_concurrency=2, _env_file=None))
    monkeypatch.setattr(runner_module, "execute_task", fake_execute)

    async def scenario() -> None:
        client = FakeRunnerClient()
        stop = asyncio.Event()
        task = asyncio.create_task(runner_module.run_runner(client=client, stop_event=stop))
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert max_active == 2
        release.set()
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)
        assert client.submitted == ["one", "two"]
        assert client.closed is True

    asyncio.run(scenario())
