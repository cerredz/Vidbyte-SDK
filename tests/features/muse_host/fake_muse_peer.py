"""FILE: tests/features/muse_host/fake_muse_peer.py

PURPOSE: A standard-library stand-in for the `muse` executable and for `wsl.exe`, scripted by a JSON scenario file, that MuseHost launches through MuseHostSettings.muse_command or through a fake wsl.exe on PATH.
ROLE IN CODEBASE: Run as a real child process by the muse_host tests and never imported. It plays `muse --version`, the `muse serve` MSP 1.0.1 peer, and the WSL forms `wsl.exe -l -q`, `wsl.exe -d <distro> -e <muse_path> serve|--version` and `wsl.exe -d <distro> -e sh -s <mark>`, and logs what it received so the tests can assert on it.
ARCHITECTURE NOTE: argv[1] is the scenario path. Everything after it is what MuseHost appended (spec §13); the fake wsl.exe built by conftest.py inserts `--as-wsl` first. The main thread is the only stdin reader; a turn plays in a worker thread so the peer can send approvals and still see turn/interrupt, approval/decide and userInput/cancel. Each process logs to its own JSONL file, so two peers never interleave lines.
FUNCTION INVENTORY: main dispatches on the appended argv; FakeLog appends one JSON record per line; FrameWriter serialises stdout frames; MspPeer answers the MSP requests the host may send and enforces the schema members spec §8.5 lists; TurnWorker plays one turn after its turn/start ack; run_version, run_wsl_list and run_reap play the one-shot forms; held waits for the release file, a stop event or the hold limit.
COMMON MODIFICATION PATTERNS: Add a scenario key with its default in conftest.py's default_scenario, read it here with .get, and log anything a test must assert on.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte or anything outside the standard library; the child gets the caller's environment, not the test's sys.path. 2. Do not contact the network, the real muse or the real wsl.exe; this file replaces them. 3. Do not log the value of META_API_KEY; log only whether it is set.
KNOWN EDGE CASES: A held turn or a stubborn peer exits by itself after HOLD_LIMIT_SECONDS, so a broken run cannot leak it for long. Requests before the `initialized` notification get -32600 notInitialized, and an `initialize` without clientInfo name and version gets -32602, as the MSP 1.0.1 schema requires (review R-16).
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host
"""

from __future__ import annotations

import json
import os
import re
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
UUID7_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
CLIENT_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")
SOURCE_RANGE = {"first": {"id": "r-1", "sequence": 1}, "last": {"id": "r-2", "sequence": 2}, "stream": {"id": "s-1", "kind": "session"}}
DISTRO_NOT_FOUND_TEXT = "There is no distribution with the supplied name.\nError code: Wsl/Service/WSL_E_DISTRO_NOT_FOUND\n"
DEFAULT_CHOICES = [
    {"choiceId": "choice-approve-once", "decision": "approved", "label": "Approve once", "scope": "once"},
    {"choiceId": "choice-approve-session", "decision": "approvedForSession", "label": "Approve for session", "scope": "session"},
    {"choiceId": "choice-deny-once", "decision": "denied", "label": "Deny", "scope": "once"},
    {"choiceId": "choice-deny-persistent", "decision": "denied", "label": "Always deny", "scope": "localPersistent"},
]
ERROR_KINDS = {
    -32700: "parseError", -32600: "invalidRequest", -32601: "methodNotFound", -32602: "invalidParams", -32603: "internal",
    -32001: "overloaded", -32002: "inputTooLarge", -32010: "capabilityRequired", -32011: "notFound", -32013: "interrupted",
    -32014: "cancelled", -32020: "sessionNotFound", -32021: "sessionInUse", -32022: "sessionAmbiguous", -32023: "forkBoundaryInvalid",
    -32024: "sessionNotLoaded", -32030: "commandRejected", -32031: "backpressured", -32051: "approvalAlreadyResolved",
    -32052: "approvalChoiceInvalid", -32053: "approvalRequirementStale",
}
RETRYABLE_CODES = frozenset({-32001, -32031})


class FakeLog:
    """Appends one JSON record per line to this process's own log file."""

    def __init__(self, log_dir: str, role: str) -> None:
        self.path = Path(log_dir) / f"{role}-{os.getpid()}-{uuid.uuid4().hex[:8]}.jsonl"
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
        data = (json.dumps(frame) + "\n").encode("utf-8")
        with self.lock:
            try:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except (OSError, ValueError):
                os._exit(0)
        self.log.write("sent", frame=frame)


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


def error_object(error: dict[str, Any]) -> dict[str, Any]:
    # MSP errors carry data.kind and data.retryable; scenarios give the code and message, and the rest is filled in.
    data = dict(error.get("data") or {})
    data.setdefault("kind", ERROR_KINDS.get(error["code"], "internal"))
    data.setdefault("retryable", error["code"] in RETRYABLE_CODES)
    return {"code": error["code"], "message": error.get("message", data["kind"]), "data": data}


def close_stdin(log: FakeLog) -> None:
    # Closes this process's end of the stdin pipe so the host's next write fails.
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
    """Plays one turn after the turn/start ack: approvals, user input, items, then turn/completed."""

    def __init__(self, peer: MspPeer, session_id: str, turn_id: str) -> None:
        super().__init__(daemon=True)
        self.peer = peer
        self.session_id = session_id
        self.turn_id = turn_id
        self.config = peer.scenario.get("turn", {})

    def run(self) -> None:
        for index, approval in enumerate(self.config.get("approvals", [])):
            self.play_approval(index, approval)
        for index, request in enumerate(self.config.get("user_inputs", [])):
            self.play_user_input(index, request)
        for note in self.config.get("notifications", []):
            self.peer.writer.send(self.substitute(note))
        if self.config.get("foreign_events"):
            self.send_item("item-foreign", "agentMessage", "IGNORED FOREIGN TEXT", turn_id="turn-foreign")
            self.send_completed("failed", {"kind": "stepLimit", "message": "foreign turn", "retryable": False}, turn_id="turn-foreign")
        for index, item in enumerate(self.config.get("items", [])):
            self.send_item(f"item-{index}", item.get("kind", "agentMessage"), item.get("text"), truncated=item.get("truncated"))
        if self.config.get("view_gap"):
            self.peer.writer.send({"jsonrpc": "2.0", "method": "view/gap", "params": {"sessionId": self.session_id, "after": "v-2", "next": "v-9"}})
        mode = self.config.get("mode", "complete")
        if mode == "exit_before_complete":
            self.peer.log.write("exiting_mid_turn")
            os._exit(self.config.get("exit_code", 4))
        if mode == "hold" and not self.wait_for_release():
            return
        for index, item in enumerate(self.config.get("items_after_release", [])):
            self.send_item(f"item-late-{index}", "agentMessage", item)
        self.send_completed(self.config.get("terminal", "completed"), self.config.get("error"), usage=self.config.get("usage"))

    def substitute(self, frame: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(frame).replace("$session", self.session_id).replace("$turn", self.turn_id)
        return json.loads(text)

    def wait_for_release(self) -> bool:
        # Returns True when the turn should complete normally, False when it already completed or must stay silent.
        outcome = held(self.peer.scenario, stop=self.peer.interrupt_event)
        if outcome == "released":
            return True
        if outcome == "limit":
            return False
        on_interrupt = self.config.get("on_interrupt", "cancelled")
        self.peer.log.write("interrupt_seen", on_interrupt=on_interrupt)
        if on_interrupt == "ignore":
            return held(self.peer.scenario) == "released"
        self.send_completed("cancelled", None)
        return False

    def play_approval(self, index: int, approval: dict[str, Any]) -> None:
        approval_id = approval.get("approval_id", f"approval-{index}")
        choices = approval.get("choices", DEFAULT_CHOICES)
        params = {
            "approvalId": approval_id, "availableChoices": choices, "currentRequirementId": {"approvalId": approval_id, "sourceIndex": 0},
            "itemId": f"item-tool-{index}", "judgeEscalated": False, "protectedWrite": False, "rawArgs": "{}", "sessionId": self.session_id,
            "sourceRange": SOURCE_RANGE, "subject": {"kind": "shell", "command": "make clean"}, "taskId": f"task-{index}",
            "toolCallId": f"call-{index}", "toolName": approval.get("tool_name", "shell"), "turnId": self.turn_id, "viewCursor": f"v-a{index}",
        }
        self.peer.writer.send({"jsonrpc": "2.0", "method": "approval/requested", "params": params})
        if approval.get("expect_decide", True):
            self.peer.await_request("approval/decide", lambda frame: frame["params"].get("requirementId", {}).get("sourceIndex") == 0)
        for update in approval.get("updates", []):
            source_index = update.get("source_index", 1)
            change = {"kind": update.get("change_kind", "requirementAdvanced")}
            updated = {
                "approvalId": approval_id, "availableChoices": update.get("choices", choices), "change": change,
                "currentRequirementId": {"approvalId": approval_id, "sourceIndex": source_index}, "sessionId": self.session_id,
                "sourceRange": SOURCE_RANGE, "subject": {"kind": "shell", "command": "make clean"}, "viewCursor": f"v-u{source_index}",
            }
            self.peer.writer.send({"jsonrpc": "2.0", "method": "approval/updated", "params": updated})
            if update.get("expect_decide", True):
                self.peer.await_request("approval/decide", lambda frame, wanted=source_index: frame["params"].get("requirementId", {}).get("sourceIndex") == wanted)

    def play_user_input(self, index: int, request: dict[str, Any]) -> None:
        user_input_id = request.get("user_input_id", f"input-{index}")
        params = {
            "itemId": f"item-ask-{index}", "questions": [{"id": "q1", "question": "Which branch?"}], "sessionId": self.session_id,
            "toolCallId": f"ask-{index}", "toolName": request.get("tool_name", "ask_user"), "turnId": self.turn_id,
            "userInputId": user_input_id, "viewCursor": f"v-q{index}",
        }
        self.peer.writer.send({"jsonrpc": "2.0", "method": "userInput/requested", "params": params})
        self.peer.await_request("userInput/cancel", lambda frame: frame["params"].get("userInputId") == user_input_id)

    def send_item(self, item_id: str, kind: str, text: str | None, *, turn_id: str | None = None, truncated: bool | None = None) -> None:
        item: dict[str, Any] = {"itemId": item_id, "kind": kind, "revision": 1, "status": "completed", "turnId": turn_id or self.turn_id}
        if text is not None:
            item["text"] = text
        if truncated is not None:
            item["truncated"] = truncated
        params = {"item": item, "sessionId": self.session_id, "sourceRange": SOURCE_RANGE, "viewCursor": f"v-{item_id}"}
        self.peer.writer.send({"jsonrpc": "2.0", "method": "item/completed", "params": params})

    def send_completed(self, terminal: str, error: dict[str, Any] | None, *, usage: dict[str, Any] | None = None, turn_id: str | None = None) -> None:
        params: dict[str, Any] = {"sessionId": self.session_id, "turnId": turn_id or self.turn_id, "terminal": terminal, "sourceRange": SOURCE_RANGE, "viewCursor": "v-end"}
        if terminal == "failed" and not self.config.get("drop_error"):
            params["error"] = error or {"kind": "modelError", "message": "model failed", "retryable": False}
        if usage is not None:
            params["usage"] = usage
        self.peer.writer.send({"jsonrpc": "2.0", "method": "turn/completed", "params": params})


class MspPeer:
    """The `muse serve` side of MSP 1.0.1, scripted by the scenario."""

    def __init__(self, scenario: dict[str, Any], log: FakeLog) -> None:
        self.scenario = scenario
        self.msp = scenario.get("msp", {})
        self.log = log
        self.writer = FrameWriter(log)
        self.initialized = False
        self.turn_id: str | None = None
        self.requests: list[dict[str, Any]] = []
        self.condition = threading.Condition()
        self.interrupt_event = threading.Event()
        self.counters: dict[str, int] = {}

    def run(self) -> None:
        while True:
            try:
                raw = sys.stdin.buffer.readline()
            except (OSError, ValueError):
                raw = b""
            if not raw:
                self.log.write("eof")
                if self.scenario.get("ignore_eof"):
                    held(self.scenario)
                os._exit(0)
            self.handle_line(raw)

    def handle_line(self, raw: bytes) -> None:
        try:
            frame = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.log.write("raw", text=raw.decode("utf-8", errors="replace"))
            return
        self.log.write("frame", frame=frame)
        if not isinstance(frame, dict) or not isinstance(frame.get("method"), str):
            return
        method = frame["method"]
        if "id" not in frame:
            if method == "initialized":
                self.initialized = True
            return
        if method != "initialize" and not self.initialized:
            self.reply_error(frame, {"code": -32600, "message": "notInitialized", "data": {"kind": "notInitialized"}})
            return
        problem = self.missing_members(method, frame.get("params") or {})
        if problem:
            self.log.write("schema_violation", method=method, problem=problem)
            self.reply_error(frame, {"code": -32602, "message": problem})
            return
        self.dispatch(method, frame)

    def missing_members(self, method: str, params: dict[str, Any]) -> str:
        # Spec §8.5: every member the MSP 1.0.1 schema marks required, plus a UUIDv7 commandId on every command.
        if method == "initialize":
            info = params.get("clientInfo")
            if not isinstance(info, dict) or not isinstance(info.get("name"), str) or not isinstance(info.get("version"), str) or not info.get("version"):
                return "clientInfo requires name and version"
            return "" if CLIENT_NAME_PATTERN.match(info["name"]) else "clientInfo.name must match [a-z0-9_]+"
        required = {
            "session/start": ("commandId",),
            "session/resume": ("commandId", "sessionId"),
            "session/fork": ("commandId", "sessionId"),
            "session/read": ("sessionId",),
            "view/page": ("sessionId", "limit"),
            "turn/start": ("commandId", "sessionId", "input"),
            "turn/steer": ("commandId", "sessionId", "expectedTurnId", "input"),
            "turn/interrupt": ("commandId", "sessionId"),
            "approval/decide": ("commandId", "sessionId", "approvalId", "requirementId", "choiceId"),
            "userInput/cancel": ("commandId", "sessionId", "userInputId"),
        }.get(method, ())
        missing = [name for name in required if name not in params]
        if missing:
            return f"missing required members {missing}"
        if "commandId" in required and not UUID7_PATTERN.match(str(params["commandId"])):
            return "commandId must be a UUIDv7"
        if method == "session/fork" and "lastTurnId" in params:
            return "lastTurnId is not a session/fork member; use cutPoint.lastTurnId"
        if method == "session/fork" and "cutPoint" in params and not isinstance((params["cutPoint"] or {}).get("lastTurnId"), str):
            return "cutPoint requires lastTurnId"
        if method == "approval/decide" and not isinstance(params["requirementId"], dict):
            return "requirementId must be an ApprovalRequirementRef"
        return ""

    def dispatch(self, method: str, frame: dict[str, Any]) -> None:
        params = frame.get("params") or {}
        if method in ("approval/decide", "userInput/cancel", "turn/interrupt"):
            with self.condition:
                self.requests.append(frame)
                self.condition.notify_all()
        handlers = {
            "initialize": lambda: self.step(method, frame, self.initialize_result()),
            "model/list": lambda: self.step(method, frame, self.model_list_result()),
            "session/start": lambda: self.step(method, frame, {"session": self.session_object(self.scenario.get("new_session_id"), params.get("workspaceRoot")), "viewCursor": "v-1"}),
            "session/resume": lambda: self.session_scoped(method, frame, self.loaded_result(params)),
            "session/fork": lambda: self.session_fork(frame, params),
            "session/list": lambda: self.session_list(frame, params),
            "session/read": lambda: self.session_scoped(method, frame, self.loaded_result(params)),
            "view/page": lambda: self.session_scoped(method, frame, self.view_page_result(params)),
            "turn/start": lambda: self.turn_start(frame, params),
            "turn/steer": lambda: self.turn_steer(frame, params),
            "turn/interrupt": lambda: self.turn_interrupt(frame, params),
            "approval/decide": lambda: self.step(method, frame, {"approvalId": params["approvalId"], "commandId": params["commandId"], "status": "accepted", "terminal": self.msp.get(method, {}).get("terminal", True)}),
            "userInput/cancel": lambda: self.step(method, frame, {"commandId": params["commandId"], "status": "accepted", "userInputId": params["userInputId"]}),
        }
        handler = handlers.get(method)
        if handler is None:
            self.reply_error(frame, {"code": -32601, "message": "Method not found"})
            return
        handler()

    def step(self, method: str, frame: dict[str, Any], default_result: dict[str, Any] | None) -> None:
        config = self.msp.get(method, {})
        mode = config.get("mode", "answer")
        if mode == "silent":
            return
        if mode == "exit":
            sys.stderr.write(config.get("stderr", ""))
            sys.stderr.flush()
            os._exit(config.get("exit_code", 3))
        if mode == "close_stdin_then_answer":
            close_stdin(self.log)
        count = self.counters.get(method, 0)
        self.counters[method] = count + 1
        errors_first = config.get("errors_first", [])
        if count < len(errors_first):
            self.reply_error(frame, errors_first[count])
        elif "error" in config:
            self.reply_error(frame, config["error"])
        elif default_result is None:
            return
        else:
            self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "result": config.get("result", default_result)})
        if mode == "close_stdin_then_answer":
            held(self.scenario)
            os._exit(0)

    def reply_error(self, frame: dict[str, Any], error: dict[str, Any]) -> None:
        self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "error": error_object(error)})

    def initialize_result(self) -> dict[str, Any]:
        config = self.msp.get("initialize", {})
        result: dict[str, Any] = {
            "experimentalApi": False, "grantedCapabilities": [], "museHome": "/var/lib/muse-fake", "platformFamily": "unix",
            "platformOs": "linux", "schema": {"version": config.get("schema_version", 1), "fingerprint": "sha256:" + "0" * 64},
            "serverInfo": {"name": "muse", "version": config.get("server_version", "1.0.1")}, "sessionDurability": "durable", "userAgent": "muse/1.0.1",
        }
        if config.get("drop_server_version"):
            result["serverInfo"].pop("version")
        return result

    def model_list_result(self) -> dict[str, Any]:
        config = self.msp.get("model/list", {})
        models = config.get("models", [])
        entries = [
            {"contextLimit": None, "cost": None, "description": None, "displayLabel": model.get("label", model["modelId"]), "isActive": False,
             "isDefault": index == 0, "modelId": model["modelId"], "outputLimit": None, "profileId": None, "providerId": "meta", "releaseDate": None}
            for index, model in enumerate(models)
        ]
        return {"models": entries, "profileId": None, "providerId": "meta", "source": config.get("source", "providerCatalog")}

    def session_object(self, session_id: str | None, workspace_root: str | None) -> dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        session = {
            "sessionId": session_id, "workspaceRoot": workspace_root or "/mnt/c/w/repo", "status": "idle", "activeTurnId": None,
            "modelId": "muse-large", "providerId": "meta", "forkedFrom": None, "turnCount": 3, "createdAt": "2026-10-01T09:00:00Z",
            "updatedAt": "2026-10-02T09:30:00Z", "path": f"/var/lib/muse-fake/sessions/{session_id}.jsonl",
        }
        session.update(self.scenario.get("session_overrides", {}).get(session_id, {}))
        return session

    def loaded_result(self, params: dict[str, Any]) -> dict[str, Any] | None:
        session_id = params.get("sessionId")
        if session_id not in self.scenario.get("sessions", []):
            return None
        session = self.session_object(session_id, self.scenario.get("workspace_root"))
        return {"session": session, "history": {"items": None, "mode": "none", "snapshot": None}, "pendingRequests": [], "viewCursor": "v-1"}

    def session_scoped(self, method: str, frame: dict[str, Any], result: dict[str, Any] | None) -> None:
        # A session-scoped call on an unknown session gets -32020 sessionNotFound (verified on Muse 1.0.1).
        config = self.msp.get(method, {})
        if result is None and "error" not in config and config.get("mode", "answer") == "answer" and not config.get("errors_first"):
            self.reply_error(frame, {"code": -32020, "message": "session not found"})
            return
        self.step(method, frame, result or {})

    def session_fork(self, frame: dict[str, Any], params: dict[str, Any]) -> None:
        cut = params.get("cutPoint")
        if cut is not None and cut["lastTurnId"] not in self.scenario.get("fork_turns", []):
            self.reply_error(frame, {"code": -32023, "message": "fork boundary invalid"})
            return
        if params.get("sessionId") not in self.scenario.get("sessions", []):
            self.session_scoped("session/fork", frame, None)
            return
        forked = self.session_object(self.scenario.get("fork_session_id"), self.scenario.get("workspace_root"))
        forked["forkedFrom"] = {"commandId": params["commandId"], "cutCursor": "v-7", "cutExplicit": cut is not None, "sessionId": params["sessionId"]}
        result = {"session": forked, "history": {"items": None, "mode": "none", "snapshot": None}, "pendingRequests": [], "viewCursor": "v-1"}
        self.session_scoped("session/fork", frame, result)

    def session_list(self, frame: dict[str, Any], params: dict[str, Any]) -> None:
        config = self.msp.get("session/list", {})
        cursor = params.get("cursor")
        if cursor is not None and "cursor_error" in config:
            self.reply_error(frame, config["cursor_error"])
            return
        pages = config.get("pages", [[]])
        index = int(cursor.split("-", 1)[1]) if cursor else 0
        ids = pages[index] if index < len(pages) else []
        result: dict[str, Any] = {"sessions": [self.session_object(session_id, params.get("workspaceRoot")) for session_id in ids], "nextCursor": None}
        if index + 1 < len(pages):
            result["nextCursor"] = f"page-{index + 1}"
        self.step("session/list", frame, result)

    def view_page_result(self, params: dict[str, Any]) -> dict[str, Any] | None:
        if params.get("sessionId") not in self.scenario.get("sessions", []):
            return None
        config = self.msp.get("view/page", {})
        cursor = params.get("cursor")
        index = int(cursor.split("-", 1)[1]) if cursor else 0
        pages = config.get("pages", [[]])
        if config.get("endless"):
            events = [{"method": "item/completed", "params": {"item": {"itemId": f"filler-{index}", "kind": "reasoning", "revision": 1, "status": "completed"}}}]
            has_next = True
        else:
            events = pages[index] if index < len(pages) else []
            has_next = index + 1 < len(pages)
        framed = []
        for position, event in enumerate(events):
            event_params = {"sessionId": params["sessionId"], "sourceRange": SOURCE_RANGE, "viewCursor": f"v-{index}-{position}", **event.get("params", {})}
            framed.append({"method": event["method"], "params": event_params})
        return {"events": framed, "nextCursor": f"page-{index + 1}" if has_next else None, "resolvedAnchor": {"boundaryCursor": "v-0"}}

    def turn_start(self, frame: dict[str, Any], params: dict[str, Any]) -> None:
        config = self.scenario.get("turn", {})
        start = self.msp.get("turn/start", {})
        if "error" in start or start.get("mode", "answer") != "answer":
            self.step("turn/start", frame, None)
            return
        self.turn_id = config.get("turn_id", "turn-0001")
        ack = {"commandId": params["commandId"], "turnId": self.turn_id, "status": "accepted", "disposition": config.get("disposition", "started"), "startedNewTurn": True}
        if "result" in start:
            ack = start["result"]
        self.writer.send({"jsonrpc": "2.0", "id": frame["id"], "result": ack})
        if config.get("mode") == "exit_on_start":
            os._exit(config.get("exit_code", 4))
        TurnWorker(self, params["sessionId"], self.turn_id).start()

    def turn_steer(self, frame: dict[str, Any], params: dict[str, Any]) -> None:
        if params["expectedTurnId"] != self.turn_id and "error" not in self.msp.get("turn/steer", {}):
            self.reply_error(frame, {"code": -32030, "message": "expectedTurnId does not name the running turn"})
            return
        self.step("turn/steer", frame, {"commandId": params["commandId"], "status": "accepted", "turnId": self.turn_id})

    def turn_interrupt(self, frame: dict[str, Any], params: dict[str, Any]) -> None:
        self.interrupt_event.set()
        self.step("turn/interrupt", frame, {"commandId": params["commandId"], "status": "accepted", "turnId": params.get("turnId", self.turn_id)})

    def await_request(self, method: str, matches: Any) -> dict[str, Any] | None:
        deadline = time.monotonic() + ANSWER_WAIT_SECONDS
        with self.condition:
            while True:
                for frame in self.requests:
                    if frame["method"] == method and matches(frame):
                        self.requests.remove(frame)
                        self.log.write("request_seen", method=method, frame=frame)
                        return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.log.write("request_missing", method=method)
                    return None
                self.condition.wait(remaining)


def run_version(scenario: dict[str, Any], log: FakeLog) -> None:
    config = scenario.get("version", {})
    if config.get("hold"):
        held(scenario)
    sys.stdout.write(config.get("stdout", ""))
    sys.stdout.flush()
    sys.stderr.write(config.get("stderr", ""))
    sys.stderr.flush()
    log.write("exit", code=config.get("exit", 0))
    sys.exit(config.get("exit", 0))


def run_wsl_list(scenario: dict[str, Any], log: FakeLog) -> None:
    # `wsl.exe -l -q` prints the distro names as UTF-16-LE, one per CRLF line.
    config = scenario.get("wsl", {})
    names = config.get("distros", [])
    sys.stdout.buffer.write(("\r\n".join(names) + "\r\n").encode("utf-16-le"))
    sys.stdout.buffer.flush()
    log.write("exit", code=config.get("list_exit", 0))
    sys.exit(config.get("list_exit", 0))


def run_reap(log: FakeLog, args: list[str]) -> None:
    # `wsl.exe -d <distro> -e sh -s <mark>`: the script arrives on stdin; log it and the environment it ran with.
    script = sys.stdin.buffer.read()
    log.write("reap", argv=args, script=script.decode("utf-8", errors="replace"), has_carriage_return=b"\r" in script,
              peer_mark=os.environ.get("VIDBYTE_PEER_MARK"), wslenv=os.environ.get("WSLENV"))
    sys.exit(0)


def wsl_role(scenario: dict[str, Any], args: list[str]) -> tuple[str, list[str]]:
    # Splits `-l -q` and `-d <distro> -e <program> <rest...>` the way wsl.exe reads them.
    if args[:2] in (["-l", "-q"], ["--list", "--quiet"]):
        return "wsl_list", []
    if len(args) < 4 or args[0] != "-d" or args[2] != "-e":
        return "wsl_unknown", []
    config = scenario.get("wsl", {})
    distro, program, rest = args[1], args[3], args[4:]
    if distro not in config.get("distros", []) or config.get("launch_distro_missing"):
        return "wsl_missing_distro", rest
    if program == "sh" and rest[:1] == ["-s"]:
        return "reap", rest
    if program != config.get("muse_path", "/usr/local/bin/muse"):
        return "wsl_missing_muse", rest
    return classify(rest), rest


def classify(args: list[str]) -> str:
    if "--version" in args:
        return "version"
    if args[:1] == ["serve"]:
        return "peer"
    return "unknown"


def start_grandchild(log: FakeLog) -> None:
    # A grandchild in the peer's own process group that inherits its pipes (EC-10).
    child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({GRANDCHILD_SECONDS})"])
    log.write("grandchild", grandchild_pid=child.pid)


def main() -> None:
    scenario = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    args = sys.argv[2:]
    via_wsl = args[:1] == ["--as-wsl"]
    launcher_name = ""
    if via_wsl:
        launcher_name, args = args[1], args[2:]
        role, rest = wsl_role(scenario, args)
    else:
        role, rest = classify(args), args
    log = FakeLog(scenario["log_dir"], role)
    environment = {key: os.environ.get(key) for key in scenario.get("env_keys", [])}
    log.write("start", role=role, argv=args, env=environment, via_wsl=via_wsl, launcher_name=launcher_name, meta_key_set="META_API_KEY" in os.environ)
    if scenario.get("ignore_term") and hasattr(signal, "SIGTERM") and sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if role in scenario.get("grandchild_roles", []):
        start_grandchild(log)
    if role == "wsl_list":
        run_wsl_list(scenario, log)
    if role == "wsl_missing_distro":
        sys.stderr.write(DISTRO_NOT_FOUND_TEXT)
        sys.stderr.flush()
        sys.exit(1)
    if role == "wsl_missing_muse":
        sys.stderr.write(scenario.get("wsl", {}).get("missing_muse_stderr", "execvpe failed: No such file or directory\n"))
        sys.stderr.flush()
        sys.exit(scenario.get("wsl", {}).get("missing_muse_exit", 1))
    if role == "reap":
        run_reap(log, rest)
    if role == "version":
        run_version(scenario, log)
    if role == "peer":
        MspPeer(scenario, log).run()
        return
    sys.exit(2)


if __name__ == "__main__":
    main()
