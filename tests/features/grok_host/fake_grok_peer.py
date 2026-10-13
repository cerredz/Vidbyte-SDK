"""FILE: tests/features/grok_host/fake_grok_peer.py

PURPOSE: A standard-library stand-in for the `grok` executable, scripted by a JSON scenario file, that GrokHost launches through GrokHostSettings.grok_command.
ROLE IN CODEBASE: Run as a real child process by the grok_host tests and never imported. It plays `grok --version`, `grok models`, the one-shot `--single` run and the `grok agent --no-leader ... stdio` ACP peer, and logs what it received so the tests can assert on it.
ARCHITECTURE NOTE: argv[1] is the scenario path and everything after it is what GrokHost appended (spec §13). The main thread is the only stdin reader; a turn plays in a worker thread so the peer can send permission requests and still see session/cancel. Each process logs to its own JSONL file under the scenario's log_dir, so two peers never interleave lines.
FUNCTION INVENTORY: main dispatches on the appended argv; claim_launch_number gives each process its launch number; FakeLog appends one JSON record per line to a file named after it; FrameWriter serialises stdout frames; AcpPeer answers initialize, session/new, session/resume, session/list, session/prompt and session/cancel; TurnWorker plays one session/prompt; run_cli plays --version, models and one-shot runs; held waits for the release file, a stop event or the hold limit.
COMMON MODIFICATION PATTERNS: Add a scenario key with its default in conftest.py's default_scenario, read it here with .get, and log anything a test must assert on.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte or anything outside the standard library; the child gets the caller's environment, not the test's sys.path. 2. Do not contact the network or the real grok; this file replaces it.
KNOWN EDGE CASES: A held turn or a stubborn peer exits by itself after HOLD_LIMIT_SECONDS, so a broken run cannot leak it for long. Lines that are not JSON are logged as raw text and ignored. A closed stdout ends the process at once.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

POLL_SECONDS = 0.02
HOLD_LIMIT_SECONDS = 60.0
ANSWER_WAIT_SECONDS = 15.0
GRANDCHILD_SECONDS = 60
DEFAULT_OPTIONS = [
    {"optionId": "opt-allow-once", "name": "Allow once", "kind": "allow_once"},
    {"optionId": "opt-allow-always", "name": "Always allow", "kind": "allow_always"},
    {"optionId": "opt-reject-once", "name": "Reject", "kind": "reject_once"},
    {"optionId": "opt-reject-always", "name": "Always reject", "kind": "reject_always"},
]


def claim_launch_number(log_dir: Path) -> int:
    # Claim the lowest free number with an exclusive create, which is atomic on Windows and POSIX, so no clock is involved.
    number = 1
    while True:
        try:
            os.close(os.open(log_dir / f"launch-{number:06d}.claim", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return number
        except FileExistsError:
            number += 1


class FakeLog:
    """Appends one JSON record per line to this process's own log file."""

    def __init__(self, log_dir: str, role: str) -> None:
        # The file name starts with this process's launch number, so the tests read the logs in launch order, never PID order.
        self.path = Path(log_dir) / f"{claim_launch_number(Path(log_dir)):06d}-{role}-{os.getpid()}.jsonl"
        self.lock = threading.Lock()
        self.sequence = 0

    def write(self, kind: str, **fields: Any) -> None:
        with self.lock:
            self.sequence += 1
            record = {"kind": kind, "pid": os.getpid(), "seq": self.sequence, **fields}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


class FrameWriter:
    """Writes newline-delimited JSON frames to stdout, one writer at a time."""

    def __init__(self, log: FakeLog) -> None:
        self.log = log
        self.lock = threading.Lock()

    def send(self, frame: dict[str, Any]) -> None:
        self.raw(json.dumps(frame))
        self.log.write("sent", frame=frame)

    def raw(self, text: str) -> None:
        data = (text + "\n").encode("utf-8")
        with self.lock:
            try:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except (OSError, ValueError):
                os._exit(0)


def held(scenario: dict[str, Any], stop: threading.Event | None = None) -> str:
    # Waits until the test creates the release file, the stop event is set, or the hold limit passes.
    release = scenario.get("release_file")
    deadline = time.monotonic() + HOLD_LIMIT_SECONDS
    while time.monotonic() < deadline:
        if release and os.path.exists(release):
            return "released"
        if stop is not None and stop.is_set():
            return "stopped"
        time.sleep(POLL_SECONDS)
    return "limit"


def flag_value(args: list[str], name: str) -> str | None:
    # Reads `--name=value` or `--name value` from the appended argv.
    for index, arg in enumerate(args):
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
        if arg == name and index + 1 < len(args):
            return args[index + 1]
    return None


def close_stdin(log: FakeLog) -> None:
    # Closes this process's end of the stdin pipe so the host's next write fails (EC-27, EC-51).
    try:
        sys.stdin.close()
    except (OSError, ValueError):
        pass
    try:
        os.close(0)
    except OSError:
        pass
    log.write("stdin_closed")


class TurnWorker(threading.Thread):
    """Plays one session/prompt: permission requests, extra requests, chunks, then the answer."""

    def __init__(self, peer: AcpPeer, frame: dict[str, Any], config: dict[str, Any]) -> None:
        super().__init__(daemon=True)
        self.peer = peer
        self.frame = frame
        self.config = config

    def run(self) -> None:
        session_id = self.frame.get("params", {}).get("sessionId")
        self.ask_permissions(session_id)
        self.ask_other_requests()
        for note in self.config.get("notifications", []):
            self.peer.writer.send(json.loads(json.dumps(note).replace("$session", session_id or "")))
        for chunk in self.config.get("chunks", []):
            self.peer.send_chunk(session_id, chunk)
        if self.config.get("mode") == "exit_after_chunks":
            self.peer.log.write("exiting_mid_turn")
            os._exit(self.config.get("exit_code", 4))
        if self.config.get("mode") == "hold" and not self.wait_for_release():
            return
        for chunk in self.config.get("chunks_after_release", []):
            self.peer.send_chunk(session_id, chunk)
        self.answer()

    def ask_permissions(self, session_id: str | None) -> None:
        for index, permission in enumerate(self.config.get("permissions", [])):
            request_id = f"perm-{index}"
            tool_call: dict[str, Any] = {"toolCallId": f"call-{index}", "title": permission.get("title", "Edit README.md")}
            if permission.get("kind") is not None:
                tool_call["kind"] = permission["kind"]
            params = {"sessionId": session_id, "toolCall": tool_call, "options": permission.get("options", DEFAULT_OPTIONS)}
            self.peer.writer.send({"jsonrpc": "2.0", "id": request_id, "method": "session/request_permission", "params": params})
            answer = self.peer.await_response(request_id)
            self.peer.log.write("permission_answer", request_id=request_id, answer=answer)

    def ask_other_requests(self) -> None:
        for index, request in enumerate(self.config.get("server_requests", [])):
            request_id = f"srv-{index}"
            self.peer.writer.send({"jsonrpc": "2.0", "id": request_id, "method": request["method"], "params": request.get("params", {})})
            answer = self.peer.await_response(request_id)
            self.peer.log.write("server_request_answer", request_id=request_id, method=request["method"], answer=answer)

    def wait_for_release(self) -> bool:
        # Returns True when the turn should answer normally, False when it already answered or must stay silent.
        outcome = held(self.peer.scenario, stop=self.peer.cancel_event)
        if outcome == "released":
            return True
        if outcome == "limit":
            return False
        on_cancel = self.config.get("on_cancel", "cancelled")
        self.peer.log.write("cancel_seen", on_cancel=on_cancel)
        if on_cancel == "ignore":
            return held(self.peer.scenario) == "released"
        if on_cancel == "error_32800":
            self.peer.writer.send({"jsonrpc": "2.0", "id": self.frame["id"], "error": {"code": -32800, "message": "Request cancelled"}})
            return False
        self.peer.writer.send({"jsonrpc": "2.0", "id": self.frame["id"], "result": {"stopReason": "cancelled"}})
        return False

    def answer(self) -> None:
        if "error" in self.config:
            self.peer.writer.send({"jsonrpc": "2.0", "id": self.frame["id"], "error": self.config["error"]})
            return
        if "result" in self.config:
            self.peer.writer.send({"jsonrpc": "2.0", "id": self.frame["id"], "result": self.config["result"]})
            return
        result: dict[str, Any] = {"stopReason": self.config.get("stop_reason", "end_turn")}
        if "usage" in self.config:
            result["usage"] = self.config["usage"]
        self.peer.writer.send({"jsonrpc": "2.0", "id": self.frame["id"], "result": result})


class AcpPeer:
    """The `grok agent --no-leader ... stdio` side of ACP, scripted by the scenario."""

    def __init__(self, scenario: dict[str, Any], log: FakeLog, args: list[str]) -> None:
        self.scenario = scenario
        self.acp = scenario.get("acp", {})
        self.log = log
        self.args = args
        self.writer = FrameWriter(log)
        self.model_flag = flag_value(args, "--model")
        self.responses: dict[str, dict[str, Any]] = {}
        self.condition = threading.Condition()
        self.cancel_event = threading.Event()

    def run(self) -> None:
        while True:
            try:
                raw = sys.stdin.buffer.readline()
            except (OSError, ValueError):
                raw = b""
            if not raw:
                self.log.write("eof")
                self.after_eof()
                return
            self.handle_line(raw)

    def after_eof(self) -> None:
        if self.scenario.get("ignore_eof"):
            held(self.scenario)
        os._exit(0)

    def handle_line(self, raw: bytes) -> None:
        try:
            frame = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.log.write("raw", text=raw.decode("utf-8", errors="replace"))
            return
        self.log.write("frame", frame=frame)
        if not isinstance(frame, dict):
            return
        method = frame.get("method")
        if method is None and "id" in frame:
            with self.condition:
                self.responses[str(frame["id"])] = frame
                self.condition.notify_all()
            return
        handlers = {
            "initialize": lambda: self.step("initialize", frame, self.initialize_result()),
            "session/new": lambda: self.step("session_new", frame, {"sessionId": str(uuid.uuid4())}),
            "session/resume": lambda: self.step("session_resume", frame, {}),
            "session/list": lambda: self.session_list(frame),
            "session/prompt": lambda: self.session_prompt(frame),
            "session/cancel": self.cancel_event.set,
        }
        handler = handlers.get(method)
        if handler is not None:
            handler()
        elif "id" in frame:
            self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "error": {"code": -32601, "message": "Method not found"}})

    def step(self, name: str, frame: dict[str, Any], default_result: dict[str, Any]) -> None:
        config = self.acp.get(name, {})
        mode = config.get("mode", "answer")
        # Garbage goes out first, so a silent step can still send frames the host must drop (EC-6).
        for text in config.get("garbage_before", []):
            self.writer.raw(text)
        if mode == "silent":
            return
        if mode == "exit":
            os._exit(config.get("exit_code", 3))
        if mode == "close_stdin_then_answer":
            close_stdin(self.log)
        if "error" in config:
            self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "error": config["error"]})
        else:
            self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "result": config.get("result", default_result)})
        if mode == "close_stdin_then_answer":
            held(self.scenario)
            os._exit(0)

    def initialize_result(self) -> dict[str, Any]:
        config = self.acp.get("initialize", {})
        models = config.get("models", [])
        model_ids = [model.get("modelId") for model in models]
        default_model = config.get("current_model", model_ids[0] if model_ids else "grok-default")
        # Grok echoes a known --model and silently falls back to its default for an unknown id (EC-25).
        current = self.model_flag if self.model_flag in model_ids else default_model
        meta: dict[str, Any] = {"agentVersion": config.get("agent_version", "1.0.52")}
        if not config.get("drop_model_state"):
            meta["modelState"] = {"currentModelId": current, "availableModels": models}
        capabilities = {"loadSession": True, "sessionCapabilities": config.get("session_capabilities", {"list": {}, "resume": {}})}
        return {
            "protocolVersion": config.get("protocol_version", 1),
            "agentCapabilities": capabilities,
            "authMethods": [{"id": "grok-login", "name": "Grok login", "description": "Sign in with grok login."}],
            "_meta": meta,
        }

    def session_list(self, frame: dict[str, Any]) -> None:
        config = self.acp.get("session_list", {})
        params = frame.get("params") or {}
        cursor = params.get("cursor")
        if cursor is not None and "cursor_error" in config:
            self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "error": config["cursor_error"]})
            return
        if config.get("mode") in ("silent", "exit") or "error" in config or "result" in config:
            self.step("session_list", frame, {})
            return
        index = int(cursor.split("-", 1)[1]) if cursor else 0
        result = self.list_page(config, index, params.get("cwd"))
        self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "result": result})

    def list_page(self, config: dict[str, Any], index: int, cwd: str | None) -> dict[str, Any]:
        pages = config.get("pages", [[]])
        if config.get("endless"):
            entries = [{"sessionId": str(uuid.uuid4()), "title": f"Endless page {index}"}]
            has_next = True
        else:
            entries = [dict(entry) for entry in (pages[index] if index < len(pages) else [])]
            has_next = index + 1 < len(pages)
        for entry in entries:
            if entry.get("cwd") == "$drop":
                entry.pop("cwd")
            else:
                entry.setdefault("cwd", cwd)
        result: dict[str, Any] = {"sessions": entries}
        if has_next:
            result["nextCursor"] = f"page-{index + 1}"
        return result

    def session_prompt(self, frame: dict[str, Any]) -> None:
        config = self.acp.get("session_prompt", {})
        mode = config.get("mode", "complete")
        if mode == "exit":
            os._exit(config.get("exit_code", 4))
        if mode == "close_stdin_hold":
            close_stdin(self.log)
            held(self.scenario)
            os._exit(0)
        TurnWorker(self, frame, config).start()

    def send_chunk(self, session_id: str | None, text: str) -> None:
        update = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}
        self.writer.send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": update}})

    def await_response(self, request_id: str) -> dict[str, Any] | None:
        deadline = time.monotonic() + ANSWER_WAIT_SECONDS
        with self.condition:
            while request_id not in self.responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.condition.wait(remaining)
            return self.responses[request_id]


def oneshot_stdout(config: dict[str, Any], args: list[str]) -> str:
    # Builds the `--output-format json` line a one-shot or fork run prints.
    if "stdout" in config:
        return config["stdout"]
    resumed = flag_value(args, "--resume")
    session_id = config.get("session_id")
    if session_id == "$resume":
        session_id = resumed
    elif session_id is None:
        session_id = flag_value(args, "--session-id") if "--fork-session" in args else None
    text = "x" * config["text_repeat"] if "text_repeat" in config else config.get("text", "one-shot answer")
    body = {"text": text, "stopReason": config.get("stop_reason", "end_turn"), "sessionId": session_id or str(uuid.uuid4()), "requestId": "req-0001"}
    return json.dumps(body) + "\n"


def run_cli(scenario: dict[str, Any], log: FakeLog, role: str, args: list[str]) -> None:
    config = scenario.get({"version": "version", "models": "models_cli"}.get(role, "oneshot"), {})
    if config.get("hold"):
        held(scenario)
    stdout = oneshot_stdout(config, args) if role == "oneshot" else config.get("stdout", "")
    sys.stdout.write(stdout)
    sys.stdout.flush()
    sys.stderr.write(config.get("stderr", ""))
    sys.stderr.flush()
    log.write("exit", code=config.get("exit", 0))
    sys.exit(config.get("exit", 0))


def classify(args: list[str]) -> str:
    if "--version" in args:
        return "version"
    if args[:1] == ["models"]:
        return "models"
    if args[:1] == ["agent"]:
        return "peer"
    if any(arg.startswith("--single=") or arg in ("--single", "-p") for arg in args):
        return "oneshot"
    return "unknown"


def start_grandchild(log: FakeLog) -> None:
    # A grandchild in the peer's own process group that inherits its pipes (EC-10).
    child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({GRANDCHILD_SECONDS})"])
    log.write("grandchild", grandchild_pid=child.pid)


def main() -> None:
    scenario = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    args = sys.argv[2:]
    role = classify(args)
    log = FakeLog(scenario["log_dir"], role)
    environment = {key: os.environ.get(key) for key in scenario.get("env_keys", [])}
    log.write("start", role=role, argv=args, env=environment)
    if scenario.get("ignore_term") and hasattr(signal, "SIGTERM") and sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if role in scenario.get("grandchild_roles", []):
        start_grandchild(log)
    if role == "peer":
        if "--no-leader" not in args or args[-1:] != ["stdio"]:
            log.write("leader_violation", argv=args)
            sys.exit(64)
        AcpPeer(scenario, log, args).run()
        return
    if role == "unknown":
        sys.exit(2)
    run_cli(scenario, log, role, args)


if __name__ == "__main__":
    main()
