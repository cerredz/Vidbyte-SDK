"""FILE: tests/features/codex_host/codex_host_fakes.py

PURPOSE: An in-memory codex app-server for the CodexHost feature pack. It answers the JSON-RPC lines the real openai-codex CodexClient writes the way codex app-server 0.162 does, so the client's reader thread, message router, retry helper and goal routing all run unmocked.
ROLE IN CODEBASE: Imported lazily, inside HostTestCase.asyncSetUp only, by the openai-codex-gated modules of tests/features/codex_host/. client_class(server) is what replaces vidbyte.harnesses.native.codex.connection.CodexClient, the seam spec section 13 names.
ARCHITECTURE NOTE: FakeCodexClient subclasses the real openai_codex.client.CodexClient. It overrides start() to attach an in-memory process instead of a subprocess, and wraps close(), the goal-operation methods, _read_message() and _write_message() only to record what happened (a write attempted after close is logged as write_after_close). Every line the client writes reaches FakeAppServer.receive(), which logs the request with the writing thread and answers it on its own daemon thread; the answer, with any notifications written before or after it, goes to stdout in one atomic block. Answers are built from the field names of openai_codex.generated.v2_all, so the real response models validate them.
FUNCTION INVENTORY: FakeAppServer holds the scripted state (account, rate limits, sandbox, model pages, threads, reviewers, skills), the request log, holds, failures and drive helpers (complete_turn, emit_usage, emit, goal_update, server_request, die, send_raw, wait_for, wait_until); Request, Reply, Hold, FakeRpcError, FakeThread, FakeTurn; token_usage builds a usage payload; goal_record and skill_entry build a stored goal and a skills/list entry; client_class binds the fake client to one server; RecordingGoalState logs finish() and wake_notification_reader(). The thread-helper switches (paged_thread_list, thread_page_size, endless_thread_list, record_turn_input, drop_skill_input, input_hidden_reads, goal_get_answer, turn_cursors) and the per-thread fields (created_at, updated_at, source, parent_thread_id, status, explicit_name) are off or neutral by default, so every answer the older modules rely on is unchanged.
COMMON MODIFICATION PATTERNS: Teach the fake a new method by adding a handler to FakeAppServer._handlers, building the answer from the generated model's aliases; add a drive helper when a test needs a new notification sequence.
WHAT NOT TO DO IN THIS FILE: 1. Do not import this module at module level from a test file: it imports openai-codex, which CI does not install. 2. Do not start a real process, run codex or touch the network (NG-13). 3. Do not encode the host's own rules (mapping, preflight order, caps); answer as Codex would and let the tests assert the spec.
KNOWN EDGE CASES: stdout is one FIFO, so a notification written before a response line is routed before that response; the real router drops events for a turn that has no subscriber while its thread has no pending turn/start, which the review read-back tests rely on. The thread reviewer the fake reports is what the request sent, else default_reviewer, unless force_reviewer is set (A-15, A-16).
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md section 13; docs/spec/codex-host-thread-helpers/spec.md section 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host
"""

from __future__ import annotations

import copy
import itertools
import json
import os
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from openai_codex._goal import _GoalOperationState
from openai_codex.client import CodexClient

from tests.features.codex_host.codex_host_support import SECRET_EMAIL, WAIT_SECONDS

FAKE_VERSION = "0.162.1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_PROVIDER = "openai"
DEFAULT_CWD = os.path.abspath(os.path.join(os.sep, "fake-workspace"))
BASE_TIME = 1_760_000_000
# A held answer waits at most this long, so a test that forgets to release cannot leak a thread forever.
HOLD_LIMIT_SECONDS = 60.0
_UNSET = object()

Note = tuple[str, dict[str, Any]]


@dataclass
class Request:
    """One JSON-RPC request the client wrote, with the thread that wrote it."""

    method: str
    params: dict[str, Any]
    request_id: Any
    thread_name: str
    thread_daemon: bool


@dataclass
class Reply:
    """A handler's answer: a JSON result plus notifications around the response line."""

    result: Any = None
    before: list[Note] = field(default_factory=list)
    after: list[Note] = field(default_factory=list)


class FakeRpcError(Exception):
    """A JSON-RPC error answer; openai-codex maps it to its typed error by code."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def wire(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            body["data"] = self.data
        return body


def overloaded_error() -> FakeRpcError:
    """The overload answer openai-codex retries (ServerBusyError)."""
    return FakeRpcError(-32001, "Server overloaded; retry later.", {"codexErrorInfo": "server_overloaded"})


class Hold:
    """Pauses one matching request's answer until the test releases it."""

    def __init__(self, method: str, predicate: Callable[[dict[str, Any]], bool] | None) -> None:
        self.method = method
        self.predicate = predicate
        self.taken = False
        self.request: Request | None = None
        self.arrived = threading.Event()
        self.released = threading.Event()
        self.responded = threading.Event()

    def matches(self, request: Request) -> bool:
        return not self.taken and request.method == self.method and (self.predicate is None or self.predicate(request.params))

    def release(self) -> None:
        self.released.set()

    def wait_arrived(self, timeout: float = WAIT_SECONDS) -> Request:
        if not self.arrived.wait(timeout):
            raise AssertionError(f"{self.method} never reached the fake app-server")
        assert self.request is not None
        return self.request

    def wait_responded(self, timeout: float = WAIT_SECONDS) -> None:
        if not self.responded.wait(timeout):
            raise AssertionError(f"the held {self.method} answer was never written")


@dataclass
class FakeTurn:
    """One turn as the fake app-server stores it."""

    turn_id: str
    status: str = "inProgress"
    items: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, Any] | None = None
    # How many more thread/turns/list answers leave this turn's userMessage out (FakeAppServer.input_hidden_reads).
    hidden_reads: int = 0

    def wire(self, *, with_items: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": self.turn_id,
            "items": copy.deepcopy(self.items) if with_items else [],
            "status": self.status,
            "startedAt": BASE_TIME,
            "itemsView": "full" if with_items else "notLoaded",
        }
        if self.status != "inProgress":
            body["completedAt"] = BASE_TIME + 5
            body["durationMs"] = 5000
        if self.error is not None:
            body["error"] = copy.deepcopy(self.error)
        return body


@dataclass
class FakeThread:
    """One thread as the fake app-server stores it, with the approvals Codex reports for it."""

    thread_id: str
    reviewer: str
    policy: Any
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    cwd: str = DEFAULT_CWD
    ephemeral: bool = False
    name: str | None = None
    forked_from: str | None = None
    turns: list[FakeTurn] = field(default_factory=list)
    goal: dict[str, Any] | None = None
    # The fields below default to what every thread reported before the thread-helpers pack; a test sets them per thread.
    created_at: int = BASE_TIME
    updated_at: int = BASE_TIME + 60
    # A SessionSource wire value: "cli", "vscode", "exec", "appServer", "unknown", or {"subAgent": "review"} and the like.
    source: Any = "appServer"
    parent_thread_id: str | None = None
    # A forced status type ("notLoaded", "systemError", "idle" or "active"); None reports idle or active from the turns.
    status: str | None = None
    # When True, name goes on the wire even when it is None or "" (JSON null or an empty string).
    explicit_name: bool = False

    def find_turn(self, turn_id: str) -> FakeTurn | None:
        return next((turn for turn in self.turns if turn.turn_id == turn_id), None)

    def wire(self, *, include_turns: bool) -> dict[str, Any]:
        running = any(turn.status == "inProgress" for turn in self.turns)
        body: dict[str, Any] = {
            "cliVersion": FAKE_VERSION,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "cwd": self.cwd,
            "ephemeral": self.ephemeral,
            "id": self.thread_id,
            "model": self.model,
            "modelProvider": self.provider,
            "preview": f"preview of {self.thread_id}",
            "sessionId": f"session-{self.thread_id}",
            "source": copy.deepcopy(self.source),
            "status": self._status_wire(running),
            "turns": [turn.wire(with_items=True) for turn in self.turns] if include_turns else [],
        }
        if self.name or self.explicit_name:
            body["name"] = self.name
        if not self.ephemeral:
            body["path"] = os.path.join(DEFAULT_CWD, "sessions", f"{self.thread_id}.jsonl")
        if self.forked_from:
            body["forkedFromId"] = self.forked_from
        if self.parent_thread_id:
            body["parentThreadId"] = self.parent_thread_id
        return body

    def _status_wire(self, running: bool) -> dict[str, Any]:
        kind = self.status or ("active" if running else "idle")
        return {"type": "active", "activeFlags": []} if kind == "active" else {"type": kind}

    def source_kind(self) -> str:
        """The ThreadSourceKind a sourceKinds filter matches this thread's source against."""
        if isinstance(self.source, str):
            return self.source
        agent = self.source.get("subAgent") if isinstance(self.source, dict) else None
        if agent is None:
            return "unknown"
        if isinstance(agent, dict):
            return "subAgentThreadSpawn" if "thread_spawn" in agent else "subAgentOther"
        return {"review": "subAgentReview", "compact": "subAgentCompact"}.get(agent, "subAgentOther")


def token_usage(total: tuple[int, int], last: tuple[int, int]) -> dict[str, Any]:
    """A thread/tokenUsage/updated payload from cumulative and last (input, output) pairs."""

    def breakdown(pair: tuple[int, int]) -> dict[str, int]:
        return {"inputTokens": pair[0], "cachedInputTokens": 0, "outputTokens": pair[1], "reasoningOutputTokens": 0, "totalTokens": pair[0] + pair[1]}

    return {"total": breakdown(total), "last": breakdown(last)}


def agent_message(item_id: str, text: str, phase: str | None = "final_answer") -> dict[str, Any]:
    item: dict[str, Any] = {"type": "agentMessage", "id": item_id, "text": text}
    if phase is not None:
        item["phase"] = phase
    return item


def goal_record(thread_id: str, objective: str, status: str = "active", *, token_budget: int | None = None, tokens_used: int = 0, time_used_seconds: int = 0) -> dict[str, Any]:
    """A stored ThreadGoal, keyed by its wire aliases; tokenBudget is left out when there is none."""
    goal: dict[str, Any] = {
        "createdAt": BASE_TIME,
        "objective": objective,
        "status": status,
        "threadId": thread_id,
        "timeUsedSeconds": time_used_seconds,
        "tokensUsed": tokens_used,
        "updatedAt": BASE_TIME + 30,
    }
    if token_budget is not None:
        goal["tokenBudget"] = token_budget
    return goal


def skill_entry(name: str, path: str, *, enabled: bool = True, scope: str = "user", description: str = "") -> dict[str, Any]:
    """One SkillMetadata entry of a skills/list answer."""
    return {"name": name, "description": description or f"The {name} skill.", "enabled": enabled, "path": path, "scope": scope}


def _model(model_id: str, model: str, *, hidden: bool = False, default: bool = False) -> dict[str, Any]:
    return {
        "id": model_id,
        "model": model,
        "displayName": model.upper(),
        "description": f"Fake model {model}.",
        "hidden": hidden,
        "isDefault": default,
        "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [
            {"reasoningEffort": "low", "description": "Low effort."},
            {"reasoningEffort": "medium", "description": "Medium effort."},
            {"reasoningEffort": "max", "description": "Maximum effort."},
        ],
    }


class _FakeStdin:
    def __init__(self, server: FakeAppServer, process: _FakeProcess) -> None:
        self._server = server
        self._process = process
        self.closed = False

    def write(self, text: str) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        self._server.receive(text, threading.current_thread(), self._process)
        return len(text)

    def flush(self) -> None:
        if self.closed:
            raise ValueError("I/O operation on closed file.")

    def close(self) -> None:
        self.closed = True


class _FakeStdout:
    def __init__(self) -> None:
        self._lines: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._eof = False

    def push(self, lines: list[str]) -> None:
        with self._lock:
            if self._eof:
                return
            for line in lines:
                self._lines.put(line + "\n")

    def close(self) -> None:
        with self._lock:
            if self._eof:
                return
            self._eof = True
            self._lines.put("")

    def readline(self) -> str:
        line = self._lines.get()
        if line == "":
            self._lines.put("")
        return line


class _FakeStderr:
    def __init__(self) -> None:
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._cond = threading.Condition()
        self._written = 0
        self._drained = 0

    def write_line(self, text: str) -> None:
        with self._cond:
            self._written += 1
        self._lines.put(text + "\n")

    def close(self) -> None:
        self._lines.put(None)

    def __iter__(self) -> Any:
        while True:
            item = self._lines.get()
            if item is None:
                return
            yield item
            # The drain thread asks for the next line only after it stored this one.
            with self._cond:
                self._drained += 1
                self._cond.notify_all()

    def wait_drained(self, timeout: float = WAIT_SECONDS) -> None:
        with self._cond:
            if not self._cond.wait_for(lambda: self._drained >= self._written, timeout):
                raise AssertionError("the client never drained the fake stderr")


class _FakeProcess:
    def __init__(self, server: FakeAppServer) -> None:
        self.stdin = _FakeStdin(server, self)
        self.stdout = _FakeStdout()
        self.stderr = _FakeStderr()
        self.returncode: int | None = None
        self.pid = 4242

    def terminate(self) -> None:
        self.stdout.close()
        self.stderr.close()

    def kill(self) -> None:
        self.terminate()

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def poll(self) -> int | None:
        return self.returncode


class RecordingGoalState(_GoalOperationState):
    """A real openai-codex goal state that also logs finish() and wake_notification_reader()."""

    def finish(self) -> None:
        self.fake_server.record("finish", self.thread_id)
        _GoalOperationState.finish(self)

    def wake_notification_reader(self) -> None:
        self.fake_server.record("wake_notification_reader", self.thread_id)
        _GoalOperationState.wake_notification_reader(self)


class FakeCodexClient(CodexClient):
    """The real openai-codex client over the in-memory app-server of one test."""

    fake_server: FakeAppServer

    def __init__(self, config: Any = None, approval_handler: Any = None) -> None:
        super().__init__(config, approval_handler=approval_handler)
        self.fake_server.client_created(self, config, approval_handler)

    def start(self) -> None:
        if self._proc is not None:
            return
        self._proc = self.fake_server.process_started()  # type: ignore[assignment]
        self._start_stderr_drain_thread()
        self._start_reader_thread()

    def close(self) -> None:
        self.fake_server.client_closing()
        super().close()

    def reserve_goal_operation(self, thread_id: str) -> _GoalOperationState:
        return self._router._register_goal(self.fake_server.goal_state(thread_id))

    def register_goal_operation(self, thread_id: str) -> _GoalOperationState:
        state = self.fake_server.goal_state(thread_id)
        state.activate_turn_routing()
        return self._router._register_goal(state)

    def cancel_goal_operation(self, state: _GoalOperationState) -> None:
        self.fake_server.record("cancel_goal_operation", state.thread_id)
        super().cancel_goal_operation(state)

    def unregister_goal_operation(self, state: _GoalOperationState) -> None:
        self.fake_server.record("unregister_goal_operation", state.thread_id)
        super().unregister_goal_operation(state)

    def next_goal_notification(self, state: _GoalOperationState) -> Any:
        self.fake_server.record("next_goal_notification", state.thread_id, threading.current_thread())
        try:
            return super().next_goal_notification(state)
        except BaseException:
            self.fake_server.record("next_goal_notification_raised", state.thread_id, threading.current_thread())
            raise

    def _read_message(self) -> Any:
        try:
            return super()._read_message()
        except BaseException as exc:
            self.fake_server.reader_failed(exc)
            raise

    def _write_message(self, payload: Any) -> None:
        # A closed client refuses the write before it reaches the fake stdin, so the attempt is logged here.
        if self._proc is None:
            self.fake_server.record("write_after_close", payload.get("method") if isinstance(payload, dict) else payload)
        super()._write_message(payload)


def client_class(server: FakeAppServer) -> type[FakeCodexClient]:
    """Build the client class that replaces CodexClient at the seam, bound to one server."""
    return type("BoundFakeCodexClient", (FakeCodexClient,), {"fake_server": server})


class FakeAppServer:
    """A scripted codex app-server: state, answers, a request log and drive helpers."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._ids = itertools.count(1)
        self._thread_ids = itertools.count(1)
        self._turn_ids = itertools.count(1)
        self._item_ids = itertools.count(1)
        self._holds: list[Hold] = []
        self._failures: list[list[Any]] = []
        self._before_response: list[list[Any]] = []
        self._server_requests: dict[str, Future[Any]] = {}
        self.process: _FakeProcess | None = None
        self.client: FakeCodexClient | None = None
        self.config: Any = None
        self.approval_handler: Any = None
        self.clients_created = 0
        self.started = 0
        self.closed = 0
        self.start_error: BaseException | None = None
        self.before_close: Callable[[], None] | None = None
        self.log: list[tuple[Any, ...]] = []
        self.requests: list[Request] = []
        self.client_notifications: list[str] = []
        self.reader_errors: list[BaseException] = []
        self.handler_errors: list[str] = []
        # Scripted state; a test changes these before the call they affect.
        self.version: str | None = FAKE_VERSION
        self.user_agent: str | None = None
        self.account: dict[str, Any] | None = {"type": "chatgpt", "email": SECRET_EMAIL, "planType": "plus"}
        self.requires_openai_auth = True
        self.rate_limits: dict[str, Any] = {
            "planType": "plus",
            "limitId": "codex",
            "primary": {"usedPercent": 42, "resetsAt": BASE_TIME + 3600, "windowDurationMins": 300},
            "secondary": {"usedPercent": 7, "resetsAt": BASE_TIME + 86400, "windowDurationMins": 10080},
        }
        self.ordinary_usage_allowed: bool | None = True
        self.sandbox_status = "ready"
        self.model_pages: list[list[dict[str, Any]]] = [
            [_model("gpt-5.5", "gpt-5.5", default=True), _model("codex-auto-review", "codex-auto-review", hidden=True)],
            [_model("gpt-5.5-codex-latest", "gpt-5.5-codex")],
        ]
        self.default_reviewer = "user"
        self.default_policy: Any = "on-request"
        self.force_reviewer: str | None = None
        self.force_policy: Any = None
        self.interrupt_completes = True
        self.autocomplete: dict[str, Any] | None = None
        self.goal_starts_turn = True
        self.goal_updates = True
        self.budget_echo: Any = _UNSET
        self.repeat_last_cursor = False
        self.threads: dict[str, FakeThread] = {}
        # Thread-helper switches; each is off by default, so the answers above stay exactly as they were.
        # paged_thread_list: thread/list sorts, filters (sourceKinds, cwd, searchTerm), honors limit and pages
        # with distinct cursors ending in null; thread_page_size caps each page further.
        self.paged_thread_list = False
        self.thread_page_size: int | None = None
        # endless_thread_list: every thread/list answer is an empty page with a fresh cursor.
        self.endless_thread_list = False
        # Skills per working folder for skills/list; a request without cwds is answered for DEFAULT_CWD.
        self.skills: dict[str, list[dict[str, Any]]] = {}
        # record_turn_input: turn/start stores its input as the turn's userMessage item, the way Codex records it;
        # drop_skill_input leaves the skill entries out of it; input_hidden_reads hides it from that many
        # thread/turns/list answers first.
        self.record_turn_input = False
        self.drop_skill_input = False
        self.input_hidden_reads = 0
        # goal_get_answer: when set, thread/goal/get answers goal_get_answer(thread) instead of the stored goal.
        self.goal_get_answer: Callable[[FakeThread], dict[str, Any] | None] | None = None
        # Extra thread/turns/list cursors a test names, mapped to the turn offset they resume at.
        self.turn_cursors: dict[str, int] = {}
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "initialize": self._initialize,
            "account/read": self._account_read,
            "account/rateLimits/read": self._rate_limits,
            "windowsSandbox/readiness": self._sandbox_readiness,
            "model/list": self._model_list,
            "thread/start": self._thread_start,
            "thread/resume": self._thread_resume,
            "thread/fork": self._thread_fork,
            "thread/read": self._thread_read,
            "thread/list": self._thread_list,
            "thread/name/set": self._thread_name_set,
            "turn/start": self._turn_start,
            "turn/steer": self._turn_steer,
            "turn/interrupt": self._turn_interrupt,
            "review/start": self._review_start,
            "thread/goal/clear": self._goal_clear,
            "thread/goal/set": self._goal_set,
            "thread/goal/get": self._goal_get,
            "thread/compact/start": self._thread_compact,
            "thread/delete": self._thread_delete,
            "thread/turns/list": self._turns_list,
            "skills/list": self._skills_list,
        }

    # ----- lifecycle hooks called by FakeCodexClient -----

    def client_created(self, client: FakeCodexClient, config: Any, approval_handler: Any) -> None:
        with self._cond:
            self.client = client
            self.config = config
            self.approval_handler = approval_handler
            self.clients_created += 1
            self._cond.notify_all()

    def process_started(self) -> _FakeProcess:
        with self._cond:
            self.started += 1
            self.log.append(("start", threading.current_thread().name))
            self._cond.notify_all()
        if self.start_error is not None:
            raise self.start_error
        self.process = _FakeProcess(self)
        return self.process

    def client_closing(self) -> None:
        current = threading.current_thread()
        with self._cond:
            self.closed += 1
            self.log.append(("close", current.name, current.daemon))
            self._cond.notify_all()
        if self.before_close is not None:
            self.before_close()

    def goal_state(self, thread_id: str) -> RecordingGoalState:
        state = RecordingGoalState(thread_id=thread_id)
        state.fake_server = self  # type: ignore[attr-defined]
        return state

    def reader_failed(self, exc: BaseException) -> None:
        with self._cond:
            self.reader_errors.append(exc)
            self._cond.notify_all()

    def record(self, kind: str, *details: Any) -> None:
        with self._cond:
            self.log.append((kind, *details))
            self._cond.notify_all()

    # ----- the wire -----

    def receive(self, text: str, writer: threading.Thread, process: _FakeProcess) -> None:
        message = json.loads(text)
        method = message.get("method")
        if method is not None and "id" in message:
            request = Request(method, dict(message.get("params") or {}), message["id"], writer.name, writer.daemon)
            with self._cond:
                self.requests.append(request)
                self.log.append(("request", method, request))
                self._cond.notify_all()
            # The answer goes back to the process that asked, even after a newer host started its own.
            threading.Thread(target=self._answer, args=(request, process), name=f"fake-answer-{method}", daemon=True).start()
            return
        if method is not None:
            with self._cond:
                self.client_notifications.append(method)
            return
        with self._cond:
            future = self._server_requests.pop(str(message.get("id")), None)
            self.log.append(("answer", message.get("id"), threading.current_thread().name))
            self._cond.notify_all()
        if future is not None:
            future.set_result(message.get("result") if "error" not in message else {"error": message["error"]})

    def _answer(self, request: Request, process: _FakeProcess) -> None:
        hold = self._take_hold(request)
        if hold is not None:
            hold.request = request
            hold.arrived.set()
            hold.released.wait(HOLD_LIMIT_SECONDS)
        lines = self._lines_for(request)
        process.stdout.push(lines)
        if hold is not None:
            hold.responded.set()

    def _lines_for(self, request: Request) -> list[str]:
        try:
            failure = self._take_failure(request)
            if failure is not None:
                raise failure
            handler = self._handlers.get(request.method)
            if handler is None:
                raise FakeRpcError(-32601, f"method not found: {request.method}")
            reply = handler(request.params)
            if not isinstance(reply, Reply):
                reply = Reply(result=reply)
            reply.before.extend(self._take_before_response(request, reply))
            response = {"id": request.request_id, "result": reply.result if reply.result is not None else {}}
        except FakeRpcError as exc:
            reply = Reply()
            response = {"id": request.request_id, "error": exc.wire()}
        except Exception as exc:  # a fake bug becomes a recorded failure and an answer, never a hang
            self.handler_errors.append(f"{request.method}: {type(exc).__name__}: {exc}")
            reply = Reply()
            response = {"id": request.request_id, "error": {"code": -32603, "message": "fake handler failed"}}
        return [self._note_line(note) for note in reply.before] + [json.dumps(response)] + [self._note_line(note) for note in reply.after]

    @staticmethod
    def _note_line(note: Note) -> str:
        return json.dumps({"method": note[0], "params": note[1]})

    def _take_hold(self, request: Request) -> Hold | None:
        with self._cond:
            for hold in self._holds:
                if hold.matches(request):
                    hold.taken = True
                    return hold
        return None

    def _take_failure(self, request: Request) -> FakeRpcError | None:
        with self._cond:
            for rule in self._failures:
                method, predicate, error, remaining = rule
                if method == request.method and remaining != 0 and (predicate is None or predicate(request.params)):
                    if remaining is not None:
                        rule[3] = remaining - 1
                    return error
        return None

    def _take_before_response(self, request: Request, reply: Reply) -> list[Note]:
        with self._cond:
            for rule in self._before_response:
                method, predicate, action, used = rule
                if not used and method == request.method and (predicate is None or predicate(request.params)):
                    rule[3] = True
                    break
            else:
                return []
        return list(action(request.params, reply.result))

    # ----- test controls -----

    def hold(self, method: str, predicate: Callable[[dict[str, Any]], bool] | None = None) -> Hold:
        """Hold the next matching request's answer until the returned Hold is released."""
        hold = Hold(method, predicate)
        with self._cond:
            self._holds.append(hold)
        return hold

    def release_all(self) -> None:
        with self._cond:
            holds = list(self._holds)
        for hold in holds:
            hold.release()

    def fail(self, method: str, error: FakeRpcError, *, times: int | None = None, predicate: Callable[[dict[str, Any]], bool] | None = None) -> None:
        """Answer matching requests with a JSON-RPC error, always or a number of times."""
        with self._cond:
            self._failures.append([method, predicate, error, times])

    def before_response(self, method: str, action: Callable[[dict[str, Any], Any], list[Note]], predicate: Callable[[dict[str, Any]], bool] | None = None) -> None:
        """Once, run action after the answer is built and write its notifications before the response."""
        with self._cond:
            self._before_response.append([method, predicate, action, False])

    def wait_until(self, condition: Callable[[], bool], what: str, timeout: float = WAIT_SECONDS) -> None:
        with self._cond:
            if not self._cond.wait_for(condition, timeout):
                raise AssertionError(f"timed out waiting for {what}; requests so far: {self.methods()}")

    def wait_for(self, method: str, predicate: Callable[[dict[str, Any]], bool] | None = None, count: int = 1, timeout: float = WAIT_SECONDS) -> Request:
        """Wait until the count-th matching request arrived and return it."""
        self.wait_until(lambda: len(self.matching(method, predicate)) >= count, f"{count} x {method}", timeout)
        return self.matching(method, predicate)[count - 1]

    def matching(self, method: str, predicate: Callable[[dict[str, Any]], bool] | None = None) -> list[Request]:
        return [request for request in list(self.requests) if request.method == method and (predicate is None or predicate(request.params))]

    def methods(self) -> list[str]:
        return [request.method for request in list(self.requests)]

    def kinds(self, *kinds: str) -> list[tuple[Any, ...]]:
        """The log entries of the given kinds, in order."""
        return [entry for entry in list(self.log) if entry[0] in kinds]

    # ----- driving the server -----

    def emit(self, notes: list[Note]) -> None:
        if self.process is not None:
            self.process.stdout.push([self._note_line(note) for note in notes])

    def emit_usage(self, thread_id: str, turn_id: str, total: tuple[int, int], last: tuple[int, int]) -> None:
        self.emit([("thread/tokenUsage/updated", {"threadId": thread_id, "turnId": turn_id, "tokenUsage": token_usage(total, last)})])

    def item_note(self, thread_id: str, turn_id: str, item: dict[str, Any]) -> Note:
        return ("item/completed", {"completedAtMs": (BASE_TIME + 3) * 1000, "item": item, "threadId": thread_id, "turnId": turn_id})

    def final_item(self, text: str, phase: str | None = "final_answer") -> dict[str, Any]:
        return agent_message(f"item-{next(self._item_ids)}", text, phase)

    def completion_notes(self, thread_id: str, turn_id: str, *, final: str | None = "Done.", status: str = "completed", usage: dict[str, Any] | None = None, error: dict[str, Any] | None = None, phase: str | None = "final_answer") -> list[Note]:
        """Store the turn's outcome and return the notifications Codex sends for it."""
        thread = self.threads[thread_id]
        turn = thread.find_turn(turn_id)
        assert turn is not None, f"unknown turn {turn_id}"
        notes: list[Note] = []
        if final is not None:
            item = self.final_item(final, phase)
            turn.items.append(item)
            notes.append(self.item_note(thread_id, turn_id, item))
        if usage is not None:
            notes.append(("thread/tokenUsage/updated", {"threadId": thread_id, "turnId": turn_id, "tokenUsage": usage}))
        turn.status = status
        turn.error = error
        notes.append(("turn/completed", {"threadId": thread_id, "turn": turn.wire(with_items=False)}))
        return notes

    def complete_turn(self, thread_id: str, turn_id: str, **outcome: Any) -> None:
        """Codex finishes the turn: final item, optional usage, then turn/completed."""
        self.emit(self.completion_notes(thread_id, turn_id, **outcome))

    def goal_update(self, thread_id: str, status: str) -> Note:
        thread = self.threads[thread_id]
        assert thread.goal is not None, "the thread has no goal"
        thread.goal["status"] = status
        return ("thread/goal/updated", {"threadId": thread_id, "goal": dict(thread.goal)})

    def server_request(self, method: str, params: dict[str, Any] | None) -> Future[Any]:
        """Send a server request to the client; the future resolves with the client's answer. None sends JSON null params."""
        request_id = f"srv-{next(self._ids)}"
        future: Future[Any] = Future()
        with self._cond:
            self._server_requests[request_id] = future
        assert self.process is not None
        self.process.stdout.push([json.dumps({"id": request_id, "method": method, "params": params})])
        return future

    def die(self, stderr_text: str) -> None:
        """The app-server writes to stderr and exits: the client sees end-of-file on stdout."""
        assert self.process is not None
        self.process.stderr.write_line(stderr_text)
        self.process.stderr.wait_drained()
        self.process.stdout.close()

    def send_raw(self, text: str) -> None:
        """Write one stdout line that is not JSON, which kills the SDK reader."""
        assert self.process is not None
        self.process.stdout.push([text])

    # ----- store helpers -----

    def new_thread(self, *, reviewer: str | None = None, policy: Any = None, **fields: Any) -> FakeThread:
        thread = FakeThread(
            thread_id=f"thr-{next(self._thread_ids)}",
            reviewer=self.force_reviewer or reviewer or self.default_reviewer,
            policy=self.force_policy if self.force_policy is not None else (policy if policy is not None else self.default_policy),
            **fields,
        )
        with self._cond:
            self.threads[thread.thread_id] = thread
            self._cond.notify_all()
        return thread

    def seed_thread(self, *, completed_turns: int = 1, reviewer: str = "auto_review", policy: Any = "on-request", running_turn: bool = False) -> FakeThread:
        """A thread that exists before the test, with completed turns that each have a final answer."""
        thread = self.new_thread(reviewer=reviewer, policy=policy)
        for _ in range(completed_turns):
            turn = FakeTurn(turn_id=self.next_turn_id(), status="completed")
            turn.items.append(self.final_item(f"Answer of {turn.turn_id}."))
            thread.turns.append(turn)
        if running_turn:
            thread.turns.append(FakeTurn(turn_id=self.next_turn_id()))
        return thread

    def next_turn_id(self) -> str:
        return f"turn-{next(self._turn_ids)}"

    def thread_or_error(self, thread_id: str) -> FakeThread:
        thread = self.threads.get(thread_id)
        if thread is None:
            raise FakeRpcError(-32600, f"thread not found: {thread_id}")
        return thread

    def thread_response(self, thread: FakeThread, *, include_turns: bool) -> dict[str, Any]:
        return {
            "approvalPolicy": copy.deepcopy(thread.policy),
            "approvalsReviewer": thread.reviewer,
            "cwd": thread.cwd,
            "model": thread.model,
            "modelProvider": thread.provider,
            "sandbox": {"type": "readOnly"},
            "thread": thread.wire(include_turns=include_turns),
        }

    def _apply_approvals(self, thread: FakeThread, params: dict[str, Any]) -> None:
        if "approvalsReviewer" in params:
            thread.reviewer = params["approvalsReviewer"]
        if "approvalPolicy" in params:
            thread.policy = params["approvalPolicy"]
        if self.force_reviewer:
            thread.reviewer = self.force_reviewer
        if self.force_policy is not None:
            thread.policy = self.force_policy

    # ----- handlers -----

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        server_info: dict[str, Any] = {"name": "codex-app-server"}
        if self.version is not None:
            server_info["version"] = self.version
        result: dict[str, Any] = {"serverInfo": server_info, "platformFamily": "windows", "platformOs": "windows"}
        if self.user_agent is not None:
            result["userAgent"] = self.user_agent
        return result

    def _account_read(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"account": copy.deepcopy(self.account), "requiresOpenaiAuth": self.requires_openai_auth}

    def _rate_limits(self, params: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"rateLimits": copy.deepcopy(self.rate_limits)}
        if self.ordinary_usage_allowed is not None:
            result["ordinaryUsageAllowed"] = self.ordinary_usage_allowed
        return result

    def _sandbox_readiness(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": self.sandbox_status}

    def _model_list(self, params: dict[str, Any]) -> dict[str, Any]:
        cursor = params.get("cursor")
        index = 0 if not cursor else int(str(cursor).rsplit("-", 1)[1]) - 1
        page = [model for model in self.model_pages[index] if params.get("includeHidden") or not model["hidden"]]
        result: dict[str, Any] = {"data": copy.deepcopy(page)}
        if index + 1 < len(self.model_pages):
            result["nextCursor"] = f"page-{index + 2}"
        elif self.repeat_last_cursor and cursor:
            result["nextCursor"] = cursor
        return result

    def _thread_start(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.new_thread(
            reviewer=params.get("approvalsReviewer"),
            policy=params.get("approvalPolicy"),
            model=params.get("model") or DEFAULT_MODEL,
            provider=params.get("modelProvider") or DEFAULT_PROVIDER,
            cwd=params.get("cwd") or DEFAULT_CWD,
            ephemeral=bool(params.get("ephemeral", False)),
        )
        return self.thread_response(thread, include_turns=False)

    def _thread_resume(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        self._apply_approvals(thread, params)
        # Resuming loads a stored thread into this app-server, so it no longer reports notLoaded.
        if thread.status == "notLoaded":
            thread.status = None
        return self.thread_response(thread, include_turns=not params.get("excludeTurns", False))

    def _thread_fork(self, params: dict[str, Any]) -> dict[str, Any]:
        source = self.thread_or_error(params["threadId"])
        last = params.get("lastTurnId")
        turns = list(source.turns)
        if last is not None:
            ids = [turn.turn_id for turn in turns]
            if last not in ids:
                raise FakeRpcError(-32602, f"unknown lastTurnId: {last}")
            turns = turns[: ids.index(last) + 1]
        fork = self.new_thread(reviewer=params.get("approvalsReviewer") or source.reviewer, policy=params.get("approvalPolicy") or source.policy, model=source.model, provider=source.provider, forked_from=source.thread_id)
        fork.turns = [copy.deepcopy(turn) for turn in turns]
        return self.thread_response(fork, include_turns=not params.get("excludeTurns", False))

    def _thread_read(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        return {"thread": thread.wire(include_turns=bool(params.get("includeTurns")))}

    def _thread_list(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.endless_thread_list:
            return {"data": [], "nextCursor": f"endless-{next(self._ids)}"}
        if not self.paged_thread_list:
            return {"data": [thread.wire(include_turns=False) for thread in list(self.threads.values())], "nextCursor": "cursor-after-page"}
        matches = self._listed_threads(params)
        start = self._offset(params.get("cursor"), "threads-after-", {})
        size = params.get("limit") or len(matches)
        if self.thread_page_size is not None:
            size = min(size, self.thread_page_size)
        page = matches[start : start + size]
        end = start + len(page)
        return {"data": [thread.wire(include_turns=False) for thread in page], "nextCursor": f"threads-after-{end}" if end < len(matches) else None}

    def _listed_threads(self, params: dict[str, Any]) -> list[FakeThread]:
        # Codex filters by source kind, exact cwd and title substring, then sorts by the requested key.
        threads = list(self.threads.values())
        if "sourceKinds" in params:
            threads = [thread for thread in threads if thread.source_kind() in params["sourceKinds"]]
        if params.get("cwd"):
            threads = [thread for thread in threads if thread.cwd == params["cwd"]]
        if params.get("searchTerm"):
            threads = [thread for thread in threads if params["searchTerm"] in (thread.name or "")]
        key = "updated_at" if params.get("sortKey") == "updated_at" else "created_at"
        return sorted(threads, key=lambda thread: getattr(thread, key), reverse=params.get("sortDirection") != "asc")

    def _offset(self, cursor: Any, prefix: str, aliases: dict[str, int]) -> int:
        # A cursor is one this fake issued (prefix + offset) or one a test named; anything else is refused.
        if not cursor:
            return 0
        if cursor in aliases:
            return aliases[cursor]
        if isinstance(cursor, str) and cursor.startswith(prefix) and cursor[len(prefix) :].isdigit():
            return int(cursor[len(prefix) :])
        raise FakeRpcError(-32600, f"invalid cursor: {cursor}")

    def _thread_name_set(self, params: dict[str, Any]) -> dict[str, Any]:
        self.thread_or_error(params["threadId"]).name = params["name"]
        return {}

    def _turn_start(self, params: dict[str, Any]) -> Reply:
        thread = self.thread_or_error(params["threadId"])
        turn = FakeTurn(turn_id=self.next_turn_id())
        thread.turns.append(turn)
        if self.record_turn_input:
            # Codex records the turn's input as its first item, a userMessage whose content is the input sent.
            content = [entry for entry in copy.deepcopy(params.get("input", [])) if not (self.drop_skill_input and entry.get("type") == "skill")]
            turn.items.append({"type": "userMessage", "id": f"item-{next(self._item_ids)}", "content": content})
            turn.hidden_reads = self.input_hidden_reads
        started = ("turn/started", {"threadId": thread.thread_id, "turn": turn.wire(with_items=False)})
        after: list[Note] = [started]
        if self.autocomplete is not None:
            after.extend(self.completion_notes(thread.thread_id, turn.turn_id, **self.autocomplete))
        return Reply(result={"turn": turn.wire(with_items=False)}, after=after)

    def _turn_steer(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        turn = thread.find_turn(params["expectedTurnId"])
        if turn is None or turn.status != "inProgress":
            raise FakeRpcError(-32600, f"expected active turn id {params['expectedTurnId']}")
        return {"turnId": turn.turn_id}

    def _turn_interrupt(self, params: dict[str, Any]) -> Reply:
        thread = self.thread_or_error(params["threadId"])
        turn = thread.find_turn(params["turnId"])
        after: list[Note] = []
        if self.interrupt_completes and turn is not None and turn.status == "inProgress":
            after = self.completion_notes(thread.thread_id, turn.turn_id, final=None, status="interrupted")
        return Reply(result={}, after=after)

    def _review_start(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        review_thread = thread
        if params.get("delivery") == "detached":
            review_thread = self.new_thread(reviewer=thread.reviewer, policy=thread.policy, model=thread.model)
        turn = FakeTurn(turn_id=self.next_turn_id())
        review_thread.turns.append(turn)
        return {"reviewThreadId": review_thread.thread_id, "turn": turn.wire(with_items=False)}

    def _goal_clear(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        cleared = thread.goal is not None
        thread.goal = None
        return {"cleared": cleared}

    def _goal_set(self, params: dict[str, Any]) -> Reply:
        thread = self.thread_or_error(params["threadId"])
        if params.get("objective") is not None:
            thread.goal = {"createdAt": BASE_TIME, "objective": params["objective"], "status": "active", "threadId": thread.thread_id, "timeUsedSeconds": 0, "tokensUsed": 0, "updatedAt": BASE_TIME}
        if thread.goal is None:
            raise FakeRpcError(-32600, f"thread has no goal: {thread.thread_id}")
        if params.get("status") is not None:
            thread.goal["status"] = params["status"]
        answer = dict(thread.goal)
        if "tokenBudget" in params:
            thread.goal["tokenBudget"] = params["tokenBudget"]
            answer["tokenBudget"] = params["tokenBudget"] if self.budget_echo is _UNSET else self.budget_echo
        notes: list[Note] = [("thread/goal/updated", {"threadId": thread.thread_id, "goal": dict(thread.goal)})] if self.goal_updates else []
        if params.get("objective") is not None and thread.goal["status"] == "active" and self.goal_starts_turn:
            turn = FakeTurn(turn_id=self.next_turn_id())
            thread.turns.append(turn)
            notes.append(("turn/started", {"threadId": thread.thread_id, "turn": turn.wire(with_items=False)}))
        return Reply(result={"goal": answer}, after=notes)

    def _goal_get(self, params: dict[str, Any]) -> dict[str, Any]:
        # Reads the stored goal without loading the thread, so a notLoaded thread stays notLoaded (spec A-5, A-16).
        thread = self.thread_or_error(params["threadId"])
        goal = self.goal_get_answer(thread) if self.goal_get_answer is not None else thread.goal
        return {"goal": copy.deepcopy(goal)}

    def _thread_compact(self, params: dict[str, Any]) -> dict[str, Any]:
        # Compaction acts only on a thread loaded in this app-server (spec A-4).
        thread = self.thread_or_error(params["threadId"])
        if thread.status == "notLoaded":
            raise FakeRpcError(-32600, f"thread not loaded: {thread.thread_id}")
        return {}

    def _thread_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        with self._cond:
            del self.threads[thread.thread_id]
            self._cond.notify_all()
        return {}

    def _turns_list(self, params: dict[str, Any]) -> dict[str, Any]:
        # Persisted history, oldest first unless desc is asked; an ephemeral thread has none (spec A-21).
        thread = self.thread_or_error(params["threadId"])
        turns = [] if thread.ephemeral else list(thread.turns)
        if params.get("sortDirection") == "desc":
            turns.reverse()
        start = self._offset(params.get("cursor"), "turns-after-", self.turn_cursors)
        limit = params.get("limit")
        page = turns[start:] if limit is None else turns[start : start + limit]
        end = start + len(page)
        full = params.get("itemsView") == "full"
        return {"data": [self._listed_turn(turn, full) for turn in page], "nextCursor": f"turns-after-{end}" if end < len(turns) else None}

    def _listed_turn(self, turn: FakeTurn, full: bool) -> dict[str, Any]:
        body = turn.wire(with_items=full)
        if full and turn.hidden_reads > 0:
            turn.hidden_reads -= 1
            body["items"] = [item for item in body["items"] if item["type"] != "userMessage"]
        return body

    def _skills_list(self, params: dict[str, Any]) -> dict[str, Any]:
        # Without cwds Codex answers for its own working folder.
        cwds = params["cwds"] if "cwds" in params else [DEFAULT_CWD]
        return {"data": [{"cwd": cwd, "errors": [], "skills": copy.deepcopy(self.skills.get(cwd, []))} for cwd in cwds]}
