"""Runner commands used by the coding showcase; credentials stay out of graphs."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

from app.core.config import Settings


def apply_patch(reference: str) -> str:
    if not re.fullmatch(r"artifact://[0-9a-fA-F-]{36}", reference):
        raise ValueError("Expected a Relayvia artifact UUID reference")
    settings = Settings()
    token = settings.control_plane_token
    if not token:
        raise RuntimeError("Control Plane token is required")
    url = settings.backend_url.rstrip("/")
    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.get(
            f"{url}/api/artifacts/{reference.removeprefix('artifact://')}/content",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
    patch = response.content
    if not patch:
        raise RuntimeError("Coding task produced an empty patch")
    for command in (["git", "apply", "--check", "-"], ["git", "apply", "-"]):
        result = subprocess.run(command, input=patch, capture_output=True)
        if result.returncode:
            raise RuntimeError("Patch could not be applied to the clean checkout")
    return hashlib.sha256(patch).hexdigest()


def validate() -> dict:
    # The fixed acceptance suite is committed before either Agent runs.
    changed = subprocess.run(
        ["git", "diff", "HEAD", "--", "test_acceptance.py"], capture_output=True, check=True,
    )
    if changed.stdout:
        raise RuntimeError("Agent changed the fixed acceptance tests")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-v"],
        capture_output=True, text=True, timeout=60,
    )
    summary = result.stdout + result.stderr
    match = re.search(r"Ran (\d+) tests?", summary)
    count = int(match.group(1)) if match else 0
    if result.returncode or count < 8:
        raise RuntimeError(f"Acceptance tests failed (exit={result.returncode}, tests={count}):\n{summary}")
    return {"tests_passed": True, "test_count": count, "log": summary}


def review(executable: str, model: str) -> dict:
    prompt = (
        "Review slugify.py and test_acceptance.py in this directory. Do not edit files. "
        "Check the implementation against all acceptance cases, particularly Unicode normalization, "
        "separators, empty input, TypeError and idempotence. Run python3 -m unittest discover -v. "
        'End your response with a JSON object: {"approved":true or false,"issues":[...],"summary":"..."}. '
        "Approve only if there are no correctness issues. Keep the response concise."
    )
    env = dict(os.environ)
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps({
        "permission": {"*": "allow", "edit": "deny", "external_directory": "deny"},
        "share": "disabled",
    })
    result = subprocess.run(
        [executable, "run", "--format", "json", "--model", model, prompt],
        capture_output=True, text=True, timeout=600, env=env,
    )
    texts = []
    errors = []
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "error":
            errors.append(event.get("error"))
        if event.get("type") == "text":
            texts.append(event.get("part", {}).get("text", ""))
    if result.returncode or errors:
        # Provider errors may include request metadata; do not echo them into Trace.
        raise RuntimeError(f"OpenCode review failed (exit={result.returncode}, error_events={len(errors)})")
    response = "\n".join(texts)
    decoder = json.JSONDecoder()
    verdict = None
    for index, char in enumerate(response):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(response[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("approved"), bool):
            verdict = value
    if verdict is None:
        raise RuntimeError("OpenCode returned no structured review verdict")
    if not verdict["approved"] or verdict.get("issues"):
        raise RuntimeError("OpenCode found review issues: " + json.dumps(verdict, ensure_ascii=False))
    return {"review_passed": True, "model": model, "verdict": verdict, "response": response}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["validate", "review"])
    parser.add_argument("--patch", required=True)
    parser.add_argument("--opencode")
    parser.add_argument("--model")
    args = parser.parse_args()
    digest = apply_patch(args.patch)
    outcome = validate()
    if args.action == "review":
        if not args.opencode or not args.model:
            parser.error("review requires --opencode and --model")
        outcome.update(review(args.opencode, args.model))
    print(json.dumps({"patch": args.patch, "patch_sha256": digest, **outcome}, ensure_ascii=False))


if __name__ == "__main__":
    main()
