"""FILE: tests/features/opencode_host/fake_opencode_serve.py

PURPOSE: A scripted stand-in for `opencode serve`, run as a real child process through OpencodeHostSettings.opencode_command, so the owned-server tests see a real launch, a real listening line, a real exit and a real reap.
ROLE IN CODEBASE: Test fake for tests/features/opencode_host/test_opencode_host_owned_server.py and test_opencode_host_security.py. It never serves HTTP itself: the tests answer HTTP through httpx.MockTransport, the spec §13 seam, so the port it prints only has to reach the host's URL.
ARCHITECTURE NOTE: argv is `<python> -u fake_opencode_serve.py <scenario.json> <arguments the host appended>`. The scenario picks a mode and a log folder. One JSONL record per event goes to `<log_dir>/serve-<pid>.jsonl`. Secrets never reach the log: the password and backend keys are recorded as presence, length and a SHA-256 digest only.
FUNCTION INVENTORY: main reads the scenario, logs the start record and runs the mode; secret_digest hashes a value for the log; start_grandchild starts a sleeping child for tree-stop checks; hold waits for the die file or the hold limit.
COMMON MODIFICATION PATTERNS: Add a mode by adding a branch in run_mode and a scenario key read with a default; keep every wait bounded by HOLD_LIMIT_SECONDS.
WHAT NOT TO DO IN THIS FILE: 1. Do not print or log a secret value; tests compare digests. 2. Do not import vidbyte; the fake must behave the same whatever the SDK does.
KNOWN EDGE CASES: SIGTERM is ignored on POSIX when the scenario says so, which forces the host's tree stop to use SIGKILL. A held fake exits by itself after sixty seconds, so a broken host cannot leave it running for long.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md FR-18, AC-9, EC-54 to EC-56, EC-153
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_owned_server.py
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

POLL_SECONDS = 0.02
HOLD_LIMIT_SECONDS = 60.0
WATCHED_VARIABLES = ("OPENCODE_SERVER_PASSWORD", "ZHIPU_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY")


def secret_digest(value: str | None) -> dict[str, Any]:
    # Presence, length and digest only: the value itself never reaches the log.
    if value is None:
        return {"present": False}
    return {"present": True, "length": len(value), "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}


def write_record(log_dir: Path, record: dict[str, Any]) -> None:
    path = log_dir / f"serve-{os.getpid()}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"pid": os.getpid(), **record}) + "\n")


def start_grandchild(log_dir: Path) -> None:
    # A sleeping child that inherits nothing it could block on; the host's tree stop must reach it.
    child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({HOLD_LIMIT_SECONDS})"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write_record(log_dir, {"kind": "grandchild", "grandchild_pid": child.pid})


def hold(die_file: Path | None) -> str:
    deadline = time.monotonic() + HOLD_LIMIT_SECONDS
    while time.monotonic() < deadline:
        if die_file is not None and die_file.exists():
            return "die"
        time.sleep(POLL_SECONDS)
    return "limit"


def run_mode(scenario: dict[str, Any], log_dir: Path) -> int:
    mode = scenario.get("mode", "listen")
    port = int(scenario.get("port", 41234))
    die_file = Path(scenario["die_file"]) if scenario.get("die_file") else None
    if mode == "exit_early":
        print("opencode: failed to start", file=sys.stderr, flush=True)
        return int(scenario.get("exit_code", 3))
    if mode == "silent":
        hold(die_file)
        return 0
    for line in scenario.get("noise_lines", []):
        print(line, flush=True)
    print(f"opencode server listening on http://127.0.0.1:{port}", flush=True)
    write_record(log_dir, {"kind": "listening", "port": port})
    outcome = hold(die_file)
    write_record(log_dir, {"kind": "exiting", "reason": outcome})
    return int(scenario.get("exit_code", 3))


def main() -> int:
    scenario_path = Path(sys.argv[1])
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    log_dir = Path(scenario["log_dir"])
    if scenario.get("ignore_term") and sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    # Record what the host passed: argv, the login name, and digests of every secret it injected.
    environment = {name: secret_digest(os.environ.get(name)) for name in WATCHED_VARIABLES}
    environment["OPENCODE_SERVER_USERNAME"] = {"present": "OPENCODE_SERVER_USERNAME" in os.environ, "value": os.environ.get("OPENCODE_SERVER_USERNAME")}
    write_record(log_dir, {"kind": "start", "argv": sys.argv[2:], "env": environment, "cwd": os.getcwd()})
    if scenario.get("grandchild"):
        start_grandchild(log_dir)
    return run_mode(scenario, log_dir)


if __name__ == "__main__":
    sys.exit(main())
