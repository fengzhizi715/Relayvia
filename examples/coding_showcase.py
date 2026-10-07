"""Run real CLI coding showcases against the MySQL configured in .env.

Uses only additive API writes. Keeps workflow versions, runs and artifacts for
inspection. Runtime processes and repositories are isolated under ignored data/.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe

import httpx

PROJECT = Path(__file__).resolve().parents[1]
PYTHON = PROJECT / ".venv/bin/python"
TASK = PROJECT / "examples/coding_showcase_task.py"
sys.path.insert(0, str(PROJECT / "backend"))

from app.core.config import Settings

ACCEPTANCE = '''import unittest
from slugify import slugify

class AcceptanceTests(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(slugify("Hello WORLD"), "hello-world")
    def test_unicode(self):
        self.assertEqual(slugify("Café déjà vu"), "cafe-deja-vu")
    def test_separators(self):
        self.assertEqual(slugify("  A__B...C / D---  "), "a-b-c-d")
    def test_empty(self):
        self.assertEqual(slugify(""), "")
        self.assertEqual(slugify(" --- !!! "), "")
    def test_non_ascii(self):
        self.assertEqual(slugify("中文 🚀"), "")
    def test_numbers(self):
        self.assertEqual(slugify("Version 2.0"), "version-2-0")
    def test_type_error(self):
        for value in [None, 123, [], b"hello"]:
            with self.assertRaises(TypeError):
                slugify(value)
    def test_idempotent(self):
        for text in ["Café hello", "Hello___WORLD", "", "A/B/2"]:
            self.assertEqual(slugify(slugify(text)), slugify(text))
'''


def say(message: str) -> None:
    print(message, flush=True)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def prepare_repository(repo: Path) -> None:
    if (repo / ".git").exists():
        return
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "showcase@relayvia.local")
    git(repo, "config", "user.name", "Relayvia Showcase")
    (repo / "slugify.py").write_text('def slugify(text: str) -> str:\n    raise NotImplementedError("Implement slugify")\n')
    (repo / "test_acceptance.py").write_text(ACCEPTANCE)
    (repo / ".gitignore").write_text("__pycache__/\n")
    (repo / "AGENTS.md").write_text(
        "This is an isolated Relayvia coding test repository. Work only in this repository.\n"
        "Use Python standard library only. Do not modify test_acceptance.py or AGENTS.md.\n"
        "Implement the requested function, add extra tests if useful, and run unittest.\n"
        "Do not commit, push, create PRs, inspect credentials, or modify files outside this repository.\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "Fixed coding showcase acceptance suite")


class Runtime:
    def __init__(self, session: Path, port: int):
        self.session = session
        self.url = f"http://127.0.0.1:{port}"
        self.port = port
        self.processes = {}
        self.logs = []
        secrets_file = session / "runtime-secrets.json"
        if not secrets_file.exists():
            write_json(secrets_file, {"runner_enrollment_token": token_urlsafe(32)})
            secrets_file.chmod(0o600)
        enrollment = json.loads(secrets_file.read_text())["runner_enrollment_token"]
        self.env = {
            **os.environ,
            "PYTHONPATH": str(PROJECT / "backend"),
            "PYTHONUNBUFFERED": "1",
            "RELAYVIA_BACKEND_URL": self.url,
            "RELAYVIA_RUNNER_ENROLLMENT_TOKEN": enrollment,
            "RELAYVIA_RUNNER_ROOT": str(session / "runner"),
            "RELAYVIA_RUNNER_ID_FILE": str(session / "runner-identity.json"),
            "RELAYVIA_RUNNER_ALLOW_UNSANDBOXED_EXECUTION": "true",
            "RELAYVIA_ARTIFACT_STORAGE_DIR": str(session / "artifacts"),
            "RELAYVIA_WORKER_LEASE_RENEW_INTERVAL": "5",
            "RELAYVIA_WORKER_RECOVERY_INTERVAL": "5",
            "RELAYVIA_WORKER_POLL_INTERVAL": "1",
        }
        # Agent providers can still use the user's outbound proxy, while local
        # Runner -> API traffic must reach this test's actual control plane.
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy", "")
        self.env["NO_PROXY"] = ",".join(filter(None, [no_proxy, "127.0.0.1", "localhost", "::1"]))
        self.env["no_proxy"] = self.env["NO_PROXY"]
        token = Settings().control_plane_token
        if not token:
            raise RuntimeError("Set RELAYVIA_CONTROL_PLANE_TOKEN in .env first")
        self.client = httpx.Client(base_url=self.url, headers={"Authorization": f"Bearer {token}"}, timeout=60, trust_env=False)

    def request(self, method: str, path: str, **kwargs):
        result = self.client.request(method, "/api" + path, **kwargs)
        if result.is_error:
            raise RuntimeError(f"{method} {path}: HTTP {result.status_code}: {result.text[:1500]}")
        return result.json() if result.content else None

    def start(self) -> str:
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                client.get(self.url + "/api/health")
        except httpx.HTTPError:
            pass
        else:
            raise RuntimeError(f"Port {self.port} already has a server; use --port with an unused port")
        self.spawn("api", ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)])
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                self.request("GET", "/health")
                break
            except (httpx.HTTPError, RuntimeError):
                if self.processes["api"].poll() is not None:
                    raise RuntimeError("API exited; inspect api.log")
                time.sleep(1)
        else:
            raise RuntimeError("API startup timed out")
        self.spawn("worker", ["-m", "app.workers.workflow_worker"])
        self.spawn("runner", ["-m", "app.runners.runner"])
        identity = self.session / "runner-identity.json"
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if identity.exists():
                runner_id = json.loads(identity.read_text())["runner_id"]
                runner = self.request("GET", "/runners/" + runner_id)
                if runner["status"] == "online" and "codex" in runner["capabilities"]:
                    say(f"Runtime ready; Runner {runner_id}")
                    return runner_id
            if self.processes["runner"].poll() is not None:
                raise RuntimeError("Runner exited; inspect runner.log")
            time.sleep(1)
        raise RuntimeError("Runner startup timed out")

    def spawn(self, name: str, args: list[str]) -> None:
        log = (self.session / f"{name}.log").open("a")
        self.logs.append(log)
        self.processes[name] = subprocess.Popen([str(PYTHON), *args], cwd=PROJECT, env=self.env, stdout=log, stderr=subprocess.STDOUT)

    def stop(self) -> None:
        # Stop execution planes before the API so final heartbeats can finish.
        for name in ("runner", "worker", "api"):
            process = self.processes.get(name)
            if process is None or process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self.processes.clear()
        for log in self.logs:
            log.close()
        self.logs.clear()

    def wait(self, run_id: str, target: str, timeout: int = 1200) -> dict:
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            run = self.request("GET", "/workflow-runs/" + run_id)
            state = [(node["node_id"], node["status"]) for node in run["node_runs"]]
            if state != previous:
                say(f"Run {run_id}: {state}")
                previous = state
            status = run["status"].upper()
            if status == target:
                return run
            if status in {"FAILED", "CANCELLED"}:
                write_json(self.session / f"failed-{run_id}.json", run)
                errors = [(n["node_id"], n["error"]) for n in run["node_runs"] if n["error"]]
                raise RuntimeError(f"Workflow {run['status']}: {errors}")
            time.sleep(2)
        raise RuntimeError(f"Run {run_id} did not reach {target} within {timeout}s")


def node(id: str, type: str, subtype: str, config: dict, **kwargs) -> dict:
    return {"id": id, "type": type, "subtype": subtype, "name": id.replace("_", " ").title(),
            "position": {"x": 0, "y": 0}, "config": config, "input_mapping": {}, "metadata": {}, **kwargs}


def graph(round: int, agent_id: str, runner_id: str, repo: Path, executable: str, model: str) -> dict:
    workspace = {"repository": str(repo), "strategy": "worktree"}
    nodes = [
        node("input", "data", "input", {"schema": {"type": "object", "properties": {"requirement": {"type": "string"}}, "required": ["requirement"]}}),
        node("coder", "agent", "agent", {"agent_id": agent_id, "task_template": "{{workflow.input.requirement}}", "workspace": workspace, "timeout_seconds": 600}, input_mapping={"task": "{{workflow.input.requirement}}"}),
    ]
    if round == 2:
        command = f"{shlex.quote(str(PYTHON))} {shlex.quote(str(TASK))}"
        patch = "'{{nodes.coder.output.patch}}'"
        nodes.extend([
            node("independent_tests", "tool", "test_command", {"command": f"{command} validate --patch {patch}", "runner_id": runner_id, "workspace": workspace, "timeout_seconds": 120}, input_mapping={"patch": "{{nodes.coder.output.patch}}"}),
            node("opencode_review", "tool", "shell", {"command": f"{command} review --patch {patch} --opencode {shlex.quote(executable)} --model {shlex.quote(model)}", "runner_id": runner_id, "workspace": workspace, "timeout_seconds": 660}, input_mapping={"patch": "{{nodes.coder.output.patch}}"}),
        ])
    nodes.extend([
        node("approval", "human", "approval", {"title": "Approve the verified coding showcase patch", "allow_reject": True}, input_mapping={"patch": "{{nodes.coder.output.patch}}"}),
        node("output", "data", "output", {"output_mapping": {"patch": "{{nodes.coder.output.patch}}", "coder_exit_code": "{{nodes.coder.output.exit_code}}"}}),
    ])
    for index, value in enumerate(nodes):
        value["position"] = {"x": index * 260, "y": 100}
    edges = [{"id": f"e{i}", "source": a["id"], "target": b["id"]} for i, (a, b) in enumerate(zip(nodes, nodes[1:]))]
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges, "variables": {}, "metadata": {"showcase_round": round}}


def run_round(runtime: Runtime, round: int, agent_id: str, runner_id: str, repo: Path, executable: str, model: str) -> dict:
    definition = graph(round, agent_id, runner_id, repo, executable, model)
    graph_path = runtime.session / f"round{round}-graph.json"
    if not graph_path.exists():
        write_json(graph_path, definition)
    requirement = (
        "Implement slugify(text: str) -> str in slugify.py. Use Unicode NFKD normalization, "
        "drop non-ASCII characters, lowercase, replace runs of non-alphanumeric characters with '-', "
        "strip leading/trailing '-', and return '' for empty/no-ASCII inputs. "
        "Raise TypeError for non-string input. Use only Python standard library. "
        "Do not modify the fixed test_acceptance.py or AGENTS.md. Add your own extra tests in a new test_*.py file. "
        "Run python3 -m unittest discover -v and report results. Do not commit or push."
    )
    ids_path = runtime.session / f"round{round}-ids.json"
    if ids_path.exists():
        ids = json.loads(ids_path.read_text())
        wf_id, run_id = ids["workflow_id"], ids["run_id"]
        say(f"Resuming persisted round {round}: {run_id}")
    else:
        workflow = runtime.request("POST", "/workflows", json={"name": f"Coding Showcase R{round} {runtime.session.name}", "graph": definition})
        wf_id = workflow["id"]
        validation = runtime.request("POST", f"/workflows/{wf_id}/validate")
        if not validation["valid"]:
            raise RuntimeError("Graph validation failed: " + json.dumps(validation))
        version = runtime.request("POST", f"/workflows/{wf_id}/versions", json={"change_note": "Real CLI + Tencent MySQL coding showcase"})
        run = runtime.request("POST", f"/workflows/{wf_id}/runs", json={"workflow_version_id": version["id"], "input": {"requirement": requirement}})
        run_id = run["id"]
        write_json(ids_path, {"workflow_id": wf_id, "version_id": version["id"], "run_id": run_id})
        runtime.request("POST", f"/workflow-runs/{run_id}/start")
    waiting = runtime.wait(run_id, "WAITING")
    runner_nodes = [n for n in waiting["node_runs"] if n["node_type"] == "tool" or n["node_id"] == "coder"]
    for traced in runner_nodes:
        if not traced["input"] or not traced["started_at"] or traced["attempt"] < 1:
            raise RuntimeError(f"Runner Trace fields missing for {traced['node_id']}")
    coder = next(n for n in waiting["node_runs"] if n["node_id"] == "coder")
    patch = coder["output"].get("patch")
    if not isinstance(patch, str):
        raise RuntimeError("Codex exited successfully but did not produce a Patch Artifact")
    verify_path = runtime.session / "runner" / f"verification-round{round}"
    if verify_path.exists():
        git(repo, "worktree", "remove", "--force", str(verify_path))
    git(repo, "worktree", "add", "--detach", str(verify_path), "HEAD")
    verification = subprocess.run([str(PYTHON), str(TASK), "validate", "--patch", patch], cwd=verify_path, env=runtime.env, capture_output=True, text=True, timeout=120)
    if verification.returncode:
        raise RuntimeError("Independent patch verification failed: " + verification.stderr[-4000:])
    verified = json.loads(verification.stdout)
    write_json(runtime.session / f"round{round}-verification.json", verified)
    patch_bytes = runtime.client.get(f"/api/artifacts/{patch.removeprefix('artifact://')}/content").content
    (runtime.session / f"round{round}.diff").write_bytes(patch_bytes)
    say(f"Round {round}: independent verification passed ({verified['test_count']} tests)")

    # A full process restart tests database-backed waiting and preserved outputs.
    runtime.stop()
    runtime.start()
    restored = runtime.request("GET", f"/workflow-runs/{run_id}")
    restored_coder = next(n for n in restored["node_runs"] if n["node_id"] == "coder")
    if restored["status"].upper() != "WAITING" or restored_coder["output"] != coder["output"] or restored_coder["attempt"] != coder["attempt"]:
        raise RuntimeError("WAITING state or completed Codex output changed after restart")
    for traced in runner_nodes:
        restored_node = next(n for n in restored["node_runs"] if n["node_id"] == traced["node_id"])
        if any(restored_node[key] != traced[key] for key in ("input", "started_at", "attempt")):
            raise RuntimeError(f"Runner Trace changed after restart for {traced['node_id']}")
    approval = next(n for n in restored["node_runs"] if n["node_id"] == "approval")
    if approval["status"].upper() != "WAITING":
        raise RuntimeError("Approval did not survive restart")
    say(f"Round {round}: WAITING and patch restored after API/Worker/Runner restart")
    runtime.request("POST", f"/node-runs/{approval['id']}/approve")
    completed = runtime.wait(run_id, "COMPLETED", timeout=120)
    write_json(runtime.session / f"round{round}-run.json", completed)
    events = runtime.request("GET", f"/workflow-runs/{run_id}/events", params={"limit": 500})
    write_json(runtime.session / f"round{round}-events.json", events)
    result = {"round": round, "status": completed["status"], "workflow_id": wf_id, "run_id": run_id,
              "patch": patch, "verification": verified, "restart_recovery": True, "approval_via_test_api": True,
              "nodes": [{"id": n["node_id"], "status": n["status"], "attempt": n["attempt"]} for n in completed["node_runs"]],
              "event_types": sorted({e["event_type"] for e in events})}
    if round == 2:
        reviewer = next(n for n in completed["node_runs"] if n["node_id"] == "opencode_review")
        result["review"] = json.loads(reviewer["output"]["stdout"])
    git(repo, "worktree", "remove", "--force", str(verify_path))
    say(f"Round {round} COMPLETED: {run_id}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", choices=["1", "2", "all"], default="all")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--session", type=Path, help="Resume an interrupted showcase without re-invoking completed Agents")
    parser.add_argument("--opencode", default=str(PROJECT / "data/coding-showcase/tools/node_modules/.bin/opencode"))
    parser.add_argument("--opencode-model", default="opencode-go/minimax-m2.7")
    args = parser.parse_args()
    executable = shutil.which("codex")
    if not executable:
        parser.error("Codex CLI must already be installed and logged in")
    if args.round != "1" and not Path(args.opencode).is_file():
        parser.error("Install OpenCode CLI or pass --opencode /absolute/path/to/opencode")
    session = args.session.resolve() if args.session else PROJECT / "data/coding-showcase" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not session.is_relative_to(PROJECT / "data/coding-showcase"):
        parser.error("Session must be within this project's data/coding-showcase directory")
    session.mkdir(parents=True, exist_ok=bool(args.session))
    repo = session / "runner/repository"
    prepare_repository(repo)
    runtime = Runtime(session, args.port)
    report = {"session": str(session), "database": "MySQL configured in .env (Tencent Cloud)", "rounds": []}
    if args.session and (session / "report.json").exists():
        report = json.loads((session / "report.json").read_text())
        report.pop("error", None)
    try:
        runner_id = runtime.start()
        agent_path = session / "agent.json"
        if agent_path.exists():
            agent = runtime.request("GET", "/agents/" + json.loads(agent_path.read_text())["id"])
        elif (session / "round1-graph.json").exists():
            prior_graph = json.loads((session / "round1-graph.json").read_text())
            agent_id = next(n["config"]["agent_id"] for n in prior_graph["nodes"] if n["id"] == "coder")
            agent = runtime.request("GET", "/agents/" + agent_id)
            write_json(agent_path, {"id": agent["id"]})
        else:
            agent = runtime.request("POST", "/agents", json={"name": f"Showcase Codex {session.name}", "connector_type": "codex", "runner_id": runner_id, "executable": executable, "timeout_seconds": 600})
            write_json(agent_path, {"id": agent["id"]})
        tested = runtime.request("POST", f"/agents/{agent['id']}/test")
        if tested["status"] != "healthy":
            raise RuntimeError("Codex Runner connection test failed")
        for round in ([1, 2] if args.round == "all" else [int(args.round)]):
            if any(item["round"] == round and item["status"].upper() == "COMPLETED" for item in report["rounds"]):
                say(f"Round {round} already completed; retaining saved evidence")
                continue
            report["rounds"].append(run_round(runtime, round, agent["id"], runner_id, repo, args.opencode, args.opencode_model))
            write_json(session / "report.json", report)
    except Exception as exc:
        report["error"] = str(exc)
        write_json(session / "report.json", report)
        say(f"Showcase stopped: {exc}")
        raise SystemExit(1)
    finally:
        runtime.stop()
        runtime.client.close()
        say(f"Evidence saved in {session}")


if __name__ == "__main__":
    main()
