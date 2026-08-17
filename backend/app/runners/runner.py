"""Relayvia Local Runner.

Independent process: `python -m app.runners.runner`.

Pulls tasks from the backend (register -> heartbeat -> claim -> execute ->
submit-result). Executes shell/git/local commands in a Runner-controlled
environment and reports a uniform ExecutionResult back. Never parses the
Workflow Graph, never schedules, never mutates Workflow state.
"""

import asyncio
import base64
import json
import os
import platform as _platform
import re
import signal
import socket
from pathlib import Path

import httpx

from app.core.config import get_settings


def _runner_name() -> str:
    return f"runner-{socket.gethostname()}"


def _identity_file() -> Path:
    path = get_settings().runner_id_file
    return Path(path) if path else Path.home() / ".relayvia" / "runner.json"


def _load_runner_identity() -> tuple[str | None, str | None]:
    path = _identity_file()
    try:
        content = json.loads(path.read_text())
        runner_id = content.get("runner_id")
        runner_token = content.get("runner_token")
        if isinstance(runner_id, str) and isinstance(runner_token, str):
            return runner_id, runner_token
    except (OSError, ValueError):
        pass
    # An old identity file containing only an ID cannot authenticate after the
    # Runner-token upgrade. Enroll a fresh identity instead of sending an
    # unauthenticated takeover request.
    return None, None


def _save_runner_identity(runner_id: str, runner_token: str) -> None:
    path = _identity_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"runner_id": runner_id, "runner_token": runner_token}))
    path.chmod(0o600)


class RunnerClient:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.AsyncClient(base_url=base_url, timeout=60)
        self.id, self.token = _load_runner_identity()
        self.name = _runner_name()
        self.hostname = socket.gethostname()
        self.platform = f"{_platform.system()}-{_platform.machine()}"

    async def register(self) -> None:
        response = await self.client.post(
            "/api/runners/register",
            json={
                "name": self.name,
                "hostname": self.hostname,
                "platform": self.platform,
                "capabilities": self._capabilities(),
                "metadata": {},
                "runner_id": self.id,
                "runner_token": self.token,
            },
        )
        response.raise_for_status()
        enrolled = response.json()
        self.id = enrolled["id"]
        self.token = enrolled.get("enrollment_token") or self.token
        if not self.token:
            raise RuntimeError("Runner registration did not return an enrollment token")
        _save_runner_identity(self.id, self.token)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("Runner is not enrolled")
        return {"X-Relayvia-Runner-Token": self.token}

    async def heartbeat(self) -> None:
        await self.client.post(
            f"/api/runners/{self.id}/heartbeat",
            json={"hostname": self.hostname, "platform": self.platform, "capabilities": self._capabilities(), "metadata": {}},
            headers=self._headers(),
        )

    @staticmethod
    def _capabilities() -> list[str]:
        from app.connectors.agents.coding import detect_coding_agent_capabilities

        return ["shell", *detect_coding_agent_capabilities()]

    async def claim(self):
        response = await self.client.post(f"/api/runners/{self.id}/claim", headers=self._headers())
        if response.status_code == 409:
            return None
        response.raise_for_status()
        return response.json()

    async def submit(self, task_id: str, lease_token: str, result: dict) -> bool:
        response = await self.client.post(
            f"/api/runners/{self.id}/submit-result",
            json={"task_id": task_id, "lease_token": lease_token, "result": result},
            headers=self._headers(),
        )
        if response.status_code == 409:
            return False  # lease expired / already processed -> drop
        response.raise_for_status()
        return True

    async def close(self) -> None:
        await self.client.aclose()


class WorkspaceError(Exception):
    pass


def _runner_root() -> Path | None:
    root = get_settings().runner_root
    return Path(root).resolve() if root else None


async def _git_ok(repository: Path) -> bool:
    process = await asyncio.create_subprocess_exec("git", "-C", str(repository), "rev-parse", "--is-inside-work-tree", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await process.wait()
    return process.returncode == 0


async def _run_git(args: list[str]) -> int:
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await process.communicate()
    return process.returncode or 0


async def prepare_workspace(workspace: dict, root: Path) -> tuple[str, str, bool]:
    """Prepare the workspace on this Runner and return (path, branch,
    is_worktree). Raises WorkspaceError on failure."""
    repository = Path(str(workspace.get("repository"))).resolve()
    if not repository.is_relative_to(root):
        raise WorkspaceError("repository escapes the Runner root")
    if not await _git_ok(repository):
        raise WorkspaceError("repository is not a valid Git repository")

    branch = workspace.get("branch")
    strategy = workspace.get("strategy") or "worktree"
    if strategy == "local":
        return str(repository), branch, False

    path = root / "worktrees" / (str(branch).replace("/", "_") if branch else "ws")
    if path.exists() and await _git_ok(path):
        return str(path), branch, True
    add = await _run_git(["git", "-C", str(repository), "worktree", "add", "-b", branch, str(path), workspace.get("base_branch") or "HEAD"])
    if add != 0:
        attach = await _run_git(["git", "-C", str(repository), "worktree", "add", str(path), branch])
        if attach != 0:
            raise WorkspaceError("failed to create Git worktree")
    return str(path), branch, True


async def _git_diff(repository: Path) -> bytes:
    # Mark untracked files as intent-to-add so they appear in the diff patch.
    await _run_git(["git", "-C", str(repository), "add", "-N", "."])
    process = await asyncio.create_subprocess_exec("git", "-C", str(repository), "diff", "HEAD", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await process.communicate()
    return stdout if process.returncode == 0 else b""


async def execute_task(task: dict) -> dict:
    """Execute a claimed Runner task (shell) and build an ExecutionResult.

    When the task declares a workspace, the command runs inside the prepared
    workspace (local repository or isolated Git worktree), and a diff patch is
    emitted as an Artifact.
    """
    config = task.get("config") or {}
    workspace = task.get("workspace")
    command = config.get("command")
    timeout_seconds = int(config.get("timeout_seconds") or 60)

    if not isinstance(command, str) or not command.strip():
        return {"ok": False, "error": {"code": "RUNNER_EMPTY_COMMAND", "message": "Tool command is empty", "retryable": False, "details": {}}}

    root = _runner_root()
    if root is None:
        return {"ok": False, "error": {"code": "RUNNER_ROOT_REQUIRED", "message": "RELAYVIA_RUNNER_ROOT must be configured", "retryable": False, "details": {}}}
    cwd = config.get("working_directory")
    workspace_meta: dict = {}
    is_worktree = False
    if workspace and workspace.get("repository"):
        try:
            prepared_path, prepared_branch, is_worktree = await prepare_workspace(workspace, root)
        except WorkspaceError as exc:
            return {"ok": False, "error": {"code": "WORKSPACE_PREPARATION_FAILED", "message": str(exc), "retryable": False, "details": {}}}
        cwd = prepared_path
        workspace_meta = {"workspace_path": prepared_path, "workspace_branch": prepared_branch}

    if not cwd:
        cwd = str(root)
    if root and cwd:
        try:
            cwd_path = Path(cwd).resolve()
            root_path = Path(root).resolve()
        except (OSError, ValueError):
            return {"ok": False, "error": {"code": "INVALID_WORKING_DIRECTORY", "message": "Working directory is invalid", "retryable": False, "details": {}}}
        if not cwd_path.is_relative_to(root_path):
            return {"ok": False, "error": {"code": "INVALID_WORKING_DIRECTORY", "message": "Working directory escapes the Runner root", "retryable": False, "details": {"cwd": cwd}}}

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return {"ok": False, "error": {"code": "RUNNER_SPAWN_FAILED", "message": str(exc), "retryable": False, "details": {}}}

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        _terminate_process_group(process)
        await process.communicate()
        return {"ok": False, "error": {"code": "RUNNER_TIMEOUT", "message": f"Command timed out after {timeout_seconds}s", "retryable": False, "details": {}}}

    stdout = _safe_output(stdout_bytes)
    stderr = _safe_output(stderr_bytes)
    metadata = {"exit_code": process.returncode, "stderr": stderr, **workspace_meta}

    artifacts: list[dict] = []
    if process.returncode == 0 and is_worktree:
        patch = await _git_diff(Path(cwd))
        if patch:
            artifacts.append({
                "name": "patch.diff",
                "type": "patch",
                "content_type": "text/plain",
                "content": base64.b64encode(patch).decode(),
                "output_key": "patch",
            })

    if process.returncode != 0:
        return {
            "ok": False,
            "error": {
                "code": "RUNNER_EXIT_NONZERO",
                "message": f"Command exited with status {process.returncode}",
                "retryable": True,
                "details": {"exit_code": process.returncode, "stderr": stderr[-2000:]},
            },
            "metadata": metadata,
            "artifacts": artifacts,
        }
    return {"ok": True, "output": {"stdout": stdout, "exit_code": process.returncode}, "metadata": metadata, "artifacts": artifacts}


_MAX_COMMAND_OUTPUT_BYTES = 32_000
_SENSITIVE_OUTPUT = re.compile(r"(?i)\b(authorization|api[_-]?key|token|password|secret)\b\s*([:=])\s*([^\s,;]+)")


def _safe_output(value: bytes) -> str:
    """Bound and redact process output before it enters durable Run Trace."""
    clipped = value[:_MAX_COMMAND_OUTPUT_BYTES]
    text = clipped.decode("utf-8", errors="replace")
    text = _SENSITIVE_OUTPUT.sub(lambda match: f"{match.group(1)}{match.group(2)}***REDACTED***", text)
    if len(value) > _MAX_COMMAND_OUTPUT_BYTES:
        text += "\n***TRUNCATED***"
    return text


def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    """Terminate the shell and all descendants created for one Runner task."""
    if process.pid is None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


async def run_runner() -> None:
    settings = get_settings()
    client = RunnerClient(settings.backend_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            break

    try:
        await client.register()
        print(f"[runner] registered as {client.id} ({client.name})")
        while not stop.is_set():
            try:
                await client.heartbeat()
            except httpx.HTTPError:
                pass
            task = await client.claim()
            if task is not None:
                result = await execute_task(task)
                accepted = await client.submit(task["task_id"], task["lease_token"], result)
                if not accepted:
                    print(f"[runner] task {task['task_id']} stale; result dropped")
            await asyncio.sleep(settings.worker_poll_interval)
    finally:
        await client.close()


def main() -> None:
    asyncio.run(run_runner())


if __name__ == "__main__":
    main()
