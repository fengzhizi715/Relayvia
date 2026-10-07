"""A completed command must retain its lease while publishing its result."""

import asyncio
import json

import httpx
import pytest

from app.runners import runner as runner_module


@pytest.mark.parametrize("first_failure", [500, 502, "transport"])
def test_submit_retries_same_result_after_transient_failure(first_failure):
    async def scenario():
        requests = []

        async def handler(request):
            requests.append(json.loads(request.content))
            if len(requests) == 1:
                if first_failure == "transport":
                    raise httpx.ConnectError("temporary failure", request=request)
                return httpx.Response(first_failure)
            return httpx.Response(200, json={})

        client = runner_module.RunnerClient.__new__(runner_module.RunnerClient)
        client.id, client.token = "runner", "test-token"
        client.client = httpx.AsyncClient(base_url="http://backend", transport=httpx.MockTransport(handler))
        result = {"ok": True, "output": {"stdout": "command already completed"}, "artifacts": [{"uri": "artifact://existing"}]}
        try:
            assert await client.submit("task", "lease", result)
            assert len(requests) == 2
            assert requests[0] == requests[1]
            assert requests[0]["result"] == result
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [401, 409])
def test_submit_does_not_retry_stale_or_unauthorized_results(status):
    async def scenario():
        calls = 0

        async def handler(_request):
            nonlocal calls
            calls += 1
            return httpx.Response(status)

        client = runner_module.RunnerClient.__new__(runner_module.RunnerClient)
        client.id, client.token = "runner", "test-token"
        client.client = httpx.AsyncClient(base_url="http://backend", transport=httpx.MockTransport(handler))
        try:
            if status == 409:
                assert not await client.submit("task", "lease", {"ok": True})
            else:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.submit("task", "lease", {"ok": True})
            assert calls == 1
        finally:
            await client.close()

    asyncio.run(scenario())


def test_task_heartbeat_continues_until_result_submission_finishes(monkeypatch):
    async def scenario():
        submission_started = False
        heartbeat_during_submission = asyncio.Event()
        executions = 0

        class Client:
            async def task_heartbeat(self, _task_id, _lease):
                if submission_started:
                    heartbeat_during_submission.set()
                return False

            async def submit(self, _task_id, _lease, _result):
                nonlocal submission_started
                submission_started = True
                await asyncio.wait_for(heartbeat_during_submission.wait(), timeout=1)
                return True

        async def execute(_task, *, cancel_event):
            nonlocal executions
            executions += 1
            return {"ok": True, "output": {}, "artifacts": []}

        monkeypatch.setattr(runner_module, "execute_task", execute)
        await runner_module._run_claimed_task(Client(), {"task_id": "task", "lease_token": "lease"}, 0.2)
        assert heartbeat_during_submission.is_set()
        assert executions == 1

    asyncio.run(scenario())
