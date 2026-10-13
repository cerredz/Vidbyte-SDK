"""FILE: tests/features/opencode_host/conftest.py

PURPOSE: Shared offline fixtures for the opencode_host feature pack: the lazy feature imports, an in-memory opencode 1.18.31 server reached through httpx.MockTransport (FakeOpencodeServer), the owned-server fake launcher, host builders, shrunk timings, and the error-shape checks every row test uses.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/opencode_host/. HTTP is faked only at the spec §13 seam, `vidbyte.lib.http.transport.httpx.AsyncClient`, so the real HttpTransport, OpencodeClient, OpencodeWire and OpencodeTurnWatcher all run; nothing in the host is mocked.
ARCHITECTURE NOTE: Every vidbyte import happens inside a fixture, so a missing OpencodeHost, record or constant fails each test at setup instead of aborting collection. FakeOpencodeServer models the routes spec §8.5 lists with the response shapes of the opencode 1.18.31 OpenAPI; a turn advances one step per `GET /session/status` poll, so watcher tests depend on poll counts, never on wall-clock time.
FUNCTION INVENTORY: opencode_api and opencode_tools_api return namespaces of the spec §8.5/§9.1 names; FakeOpencodeServer answers HTTP, records every request and scripts turns; fake_opencode installs it; make_opencode_host builds an attached host on it; ServeFake writes scenarios for fake_opencode_serve.py and reads its logs; fast_timings shrinks the stop and poll constants; check_native_error and check_tool_error assert the INV-7/INV-8 shapes; wait_until polls with a deadline; process_running reports POSIX liveness; LoopbackSilentServer is a real socket that never answers (AC-3).
COMMON MODIFICATION PATTERNS: Add a route by adding a ROUTES entry and an on_<route> method; add a turn behaviour as a plan mode in FakeOpencodeServer.advance. Add a fixture here only when two or more modules in this pack need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub OpencodeHost, HttpTransport or ManagedProcess; a missing feature must stay red. 2. Do not put a key, password or token literal in a fixture; secret-shaped values are generated per test with uuid4. 3. Do not answer a route the spec does not list; unknown routes answer 404 and are recorded as "unknown" so tests can catch them.
KNOWN EDGE CASES: `POST …/abort` answers `200 true` even for a missing session and `GET …/diff` answers `200 []` for one, as verified in the S1 probes; the host must check the session first. A held turn never finishes until the test calls release_turn. Context keys are checked against the spec §13 list.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.4, §8.5, §9.1, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host
"""

from __future__ import annotations

import asyncio
import base64
import copy
import importlib
import itertools
import json
import os
import re
import socket
import sys
import threading
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

FAKE_SERVE = Path(__file__).with_name("fake_opencode_serve.py")
REAL_ASYNC_CLIENT = httpx.AsyncClient
ATTACHED_URL = "http://127.0.0.1:4096"
ATTACHED_LOGIN = "opencode"
OWNED_PORT = 41234
KNOWN_SESSION = "ses_known0001"
OTHER_SESSION = "ses_other0002"
MISSING_SESSION = "ses_missing0003"
# The fake shares one id counter: KNOWN_SESSION's timestamp takes 1, its history then takes msg 2, prt 3, msg 4 and prt 5.
KNOWN_USER_MESSAGE = "msg_00000002"
KNOWN_REPLY_MESSAGE = "msg_00000004"
MISSING_MESSAGE = "msg_99999999"
KNOWN_PART = "prt_00000003"
PROMPT = "List the top-level folders."
MODEL = "acme/coder-1"
BASE_MS = 1_760_000_000_000
FAST_GRACE_SECONDS = 0.3
FAST_KILL_WAIT_SECONDS = 0.5
FAST_POLL_SECONDS = 0.02
SLACK_SECONDS = 2.0
POLL_SECONDS = 0.02
DEFAULT_TOKENS = {"input": 120, "output": 45, "reasoning": 5, "cache": {"read": 10, "write": 2}}
CONTEXT_KEYS = frozenset({
    "reason", "field", "vendor_code", "vendor_error", "vendor_kind", "retryable", "status_code", "version",
    "available_models", "available_providers", "live_turns", "truncated", "session_id", "exit_code", "status",
    "features", "distros", "retry_attempt", "method", "error_type",
})
ROUTES: tuple[tuple[str, str, str], ...] = (
    ("GET", r"/global/health", "health"),
    ("GET", r"/provider", "provider"),
    ("GET", r"/provider/auth", "provider_auth"),
    ("GET", r"/config/providers", "config_providers"),
    ("POST", r"/session", "session_create"),
    ("GET", r"/session", "session_list"),
    ("GET", r"/session/status", "session_status"),
    ("GET", r"/session/(?P<sid>[^/]+)", "session_get"),
    ("GET", r"/session/(?P<sid>[^/]+)/children", "session_children"),
    ("POST", r"/session/(?P<sid>[^/]+)/prompt_async", "prompt_async"),
    ("POST", r"/session/(?P<sid>[^/]+)/fork", "fork"),
    ("POST", r"/session/(?P<sid>[^/]+)/revert", "revert"),
    ("POST", r"/session/(?P<sid>[^/]+)/unrevert", "unrevert"),
    ("POST", r"/session/(?P<sid>[^/]+)/abort", "abort"),
    ("GET", r"/session/(?P<sid>[^/]+)/message", "messages"),
    ("GET", r"/session/(?P<sid>[^/]+)/message/(?P<mid>[^/]+)", "message_get"),
    ("GET", r"/session/(?P<sid>[^/]+)/diff", "diff"),
    ("GET", r"/permission", "permission_list"),
    ("POST", r"/permission/(?P<rid>[^/]+)/reply", "permission_reply"),
    ("GET", r"/question", "question_list"),
    ("POST", r"/question/(?P<rid>[^/]+)/reject", "question_reject"),
    ("POST", r"/mcp", "mcp_add"),
)
TURN_ROUTES = frozenset({"session_create", "prompt_async"})


def model_entry(provider_id: str, model_id: str, name: str, context: int, output: int) -> dict[str, Any]:
    # One opencode 1.18.31 Model object; the host reads name, status and limit.
    flags = {"text": True, "audio": False, "image": False, "video": False, "pdf": False}
    return {
        "id": model_id, "providerID": provider_id, "name": name, "release_date": "2026-01-01", "status": "active",
        "api": {"id": model_id, "url": "https://models.invalid/v1", "npm": "@ai-sdk/openai-compatible"},
        "capabilities": {"temperature": True, "reasoning": True, "attachment": False, "toolcall": True, "input": flags, "output": flags, "interleaved": False},
        "cost": {"input": 1, "output": 2, "cache": {"read": 0, "write": 0}},
        "limit": {"context": context, "output": output}, "options": {}, "headers": {},
    }


def decode_basic(header: str | None) -> tuple[str, str] | None:
    if not header or not header.lower().startswith("basic "):
        return None
    login, _, value = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8").partition(":")
    return login, value


@dataclass
class FakeTurn:
    """One prompt_async the fake is playing out, advanced once per status poll."""

    session_id: str
    user_id: str | None
    plan: dict[str, Any]
    polls: int = 0
    released: bool = False
    done: bool = False
    added: int = 0
    writing_id: str | None = None


@dataclass
class Seen:
    """One request the fake received, with the decoded basic-auth pair kept in memory only."""

    method: str
    route: str
    path: str
    params: dict[str, str]
    query: dict[str, str]
    body: Any
    auth: tuple[str, str] | None
    host: str
    port: int | None


@dataclass
class FakeOpencodeServer:
    """An in-memory opencode server: scripted routes, failure injection, held routes and turn plans."""

    workspace: Path
    provider_key: str = field(default_factory=lambda: "pk-" + uuid.uuid4().hex)
    requests: list[Seen] = field(default_factory=list)
    failures: dict[str, list[Any]] = field(default_factory=dict)
    overrides: dict[str, tuple[int, Any]] = field(default_factory=dict)
    holds: dict[str, tuple[asyncio.Event, asyncio.Event]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    status: dict[str, dict[str, Any]] = field(default_factory=dict)
    diffs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    permissions: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    turns: dict[str, FakeTurn] = field(default_factory=dict)
    mcp_answer: dict[str, Any] | None = None
    dead: bool = False

    def __post_init__(self) -> None:
        self.ids = itertools.count(1)
        self.health = {"healthy": True, "version": "1.18.31"}
        self.connected = ["acme"]
        self.defaults = {"acme": "coder-1"}
        self.providers = [
            {"id": "acme", "name": "Acme AI", "source": "env", "env": ["ACME_API_KEY"], "key": self.provider_key,
             "options": {"apiKey": self.provider_key, "baseURL": "https://models.invalid/v1"},
             "models": {"coder-1": model_entry("acme", "coder-1", "Coder One", 200000, 32000), "coder-mini": model_entry("acme", "coder-mini", "Coder Mini", 64000, 8000)}},
            {"id": "zai-coding-plan", "name": "Z.AI Coding Plan", "source": "env", "env": ["ZHIPU_API_KEY"], "options": {},
             "models": {"glm-5.3": model_entry("zai-coding-plan", "glm-5.3", "GLM 5.3", 200000, 32000)}},
        ]
        self.auth_methods = {"acme": [{"type": "api", "label": "API key"}], "zai-coding-plan": [{"type": "oauth", "label": "Z.AI login"}, {"type": "api", "label": "Manual key"}]}
        self.next_plan: dict[str, Any] = {"mode": "complete", "finish_after": 2, "replies": [{"text": "alpha-beta"}]}
        self.add_session(KNOWN_SESSION, "Refactor the parser", history=True, cost=0.5, tokens={"input": 900, "output": 300, "reasoning": 40, "cache": {"read": 70, "write": 8}})
        self.add_session(OTHER_SESSION, "Write release notes")

    # ---- scripting API used by tests -------------------------------------------------
    def add_session(self, session_id: str, title: str, *, parent_id: str | None = None, history: bool = False, cost: float | None = None, tokens: Mapping[str, Any] | None = None) -> dict[str, Any]:
        stamp = BASE_MS + next(self.ids) * 1000
        session: dict[str, Any] = {"id": session_id, "slug": f"slug-{session_id}", "projectID": "prj_fixture", "directory": str(self.workspace), "title": title, "version": "1.18.31", "time": {"created": stamp, "updated": stamp}}
        if parent_id is not None:
            session["parentID"] = parent_id
        if cost is not None:
            session["cost"] = cost
        if tokens is not None:
            session["tokens"] = dict(tokens)
        self.sessions[session_id] = session
        self.messages[session_id] = []
        if history:
            user_id = self.add_user_message(session_id, "Find the parser entry point.")
            self.add_reply(session_id, user_id, {"text": "old answer"})
        return session

    def plan(self, mode: str, **fields: Any) -> None:
        self.next_plan = {"mode": mode, "finish_after": 2, "replies": [{"text": "alpha-beta"}], **fields}

    def fail(self, route: str, kind: str, *, times: int | None = None) -> None:
        self.failures[route] = [kind, times]

    def override(self, route: str, status: int, payload: Any) -> None:
        self.overrides[route] = (status, payload)

    def hold(self, route: str) -> tuple[asyncio.Event, asyncio.Event]:
        gate = (asyncio.Event(), asyncio.Event())
        self.holds[route] = gate
        return gate

    def release_turn(self, session_id: str | None = None) -> None:
        for turn in self.turns.values():
            if session_id is None or turn.session_id == session_id:
                turn.released = True

    def delete_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        self.messages.pop(session_id, None)
        self.status.pop(session_id, None)

    def seen(self, route: str | None = None) -> list[Seen]:
        return [item for item in self.requests if route is None or item.route == route]

    def routes(self) -> list[str]:
        return [item.route for item in self.requests]

    # ---- message and turn model --------------------------------------------------------
    def next_id(self, prefix: str) -> str:
        return f"{prefix}_{next(self.ids):08d}"

    def add_user_message(self, session_id: str, text: str) -> str:
        message_id = self.next_id("msg")
        stamp = BASE_MS + int(message_id.split("_")[1]) * 1000
        info = {"id": message_id, "sessionID": session_id, "role": "user", "time": {"created": stamp}, "agent": "build", "model": {"providerID": "acme", "modelID": "coder-1"}}
        self.messages[session_id].append({"info": info, "parts": [{"id": self.next_id("prt"), "sessionID": session_id, "messageID": message_id, "type": "text", "text": text}]})
        self.sessions[session_id]["time"]["updated"] = stamp
        return message_id

    def add_reply(self, session_id: str, parent_id: str | None, spec: Mapping[str, Any]) -> str:
        message_id = self.next_id("msg")
        stamp = BASE_MS + int(message_id.split("_")[1]) * 1000
        info: dict[str, Any] = {
            "id": message_id, "sessionID": session_id, "role": "assistant", "time": {"created": stamp},
            "parentID": parent_id or "", "modelID": "coder-1", "providerID": "acme", "mode": "build", "agent": "build",
            "path": {"cwd": str(self.workspace), "root": str(self.workspace)}, "cost": spec.get("cost", 0.0125), "tokens": copy.deepcopy(spec.get("tokens", DEFAULT_TOKENS)),
        }
        if spec.get("completed", True):
            info["time"]["completed"] = stamp + 500
        if spec.get("finish", "stop") is not None:
            info["finish"] = spec.get("finish", "stop")
        if spec.get("error") is not None:
            info["error"] = copy.deepcopy(spec["error"])
        parts = [{"id": self.next_id("prt"), "sessionID": session_id, "messageID": message_id, "type": "text", "text": spec["text"]}] if spec.get("text") else []
        self.messages[session_id].append({"info": info, "parts": parts})
        self.sessions[session_id]["time"]["updated"] = stamp
        return message_id

    def start_turn(self, session_id: str, body: Mapping[str, Any]) -> None:
        plan = copy.deepcopy(self.next_plan)
        text = "".join(part.get("text", "") for part in body.get("parts", []) if isinstance(part, Mapping))
        user_id = None if plan["mode"] == "prompt_not_seen" else self.add_user_message(session_id, text)
        turn = FakeTurn(session_id, user_id, plan)
        self.turns[session_id] = turn
        if plan["mode"] == "retry":
            retry = plan["retry"]
            self.status[session_id] = {"type": "retry", "attempt": retry["attempt"], "message": retry["message"], "next": BASE_MS, **({"action": {"reason": retry["reason"], "provider": "acme", "title": "Retrying", "message": retry["message"], "label": "Retry"}} if retry.get("reason") else {})}
        elif plan["mode"] not in ("no_reply", "prompt_not_seen"):
            self.status[session_id] = {"type": "busy"}
        for kind, target in (("permissions", self.permissions), ("questions", self.questions)):
            for entry in plan.get(kind, []):
                target.append({key: (session_id if value == "$session" else value) for key, value in entry.items()})

    def advance(self, turn: FakeTurn) -> None:
        # One status poll is one step of the turn; the watcher's progress depends on polls, not time.
        turn.polls += 1
        if turn.done:
            return
        mode = turn.plan["mode"]
        if mode == "complete" and turn.polls >= turn.plan.get("finish_after", 2):
            self.finish(turn)
        elif mode in ("hold", "retry") and turn.released:
            self.finish(turn)
        elif mode == "steps":
            self.add_steps(turn)
        elif mode == "writing":
            self.write_slowly(turn)

    def add_steps(self, turn: FakeTurn) -> None:
        steps = turn.plan["steps"]
        for spec in steps[turn.added:turn.added + turn.plan.get("per_poll", 1)]:
            self.add_reply(turn.session_id, turn.user_id, spec)
            turn.added += 1
        if turn.added >= len(steps):
            self.status.pop(turn.session_id, None)
            turn.done = True

    def write_slowly(self, turn: FakeTurn) -> None:
        # A reply that exists, without time.completed, while the session already reads idle.
        if turn.writing_id is None:
            turn.writing_id = self.add_reply(turn.session_id, turn.user_id, {"text": "half-written", "completed": False, "finish": None})
            self.status.pop(turn.session_id, None)
        if turn.released:
            for message in self.messages[turn.session_id]:
                if message["info"]["id"] == turn.writing_id:
                    message["info"]["time"]["completed"] = message["info"]["time"]["created"] + 500
                    message["info"]["finish"] = "stop"
                    message["parts"][0]["text"] = "fully written"
            turn.done = True

    def finish(self, turn: FakeTurn) -> None:
        for spec in turn.plan.get("replies", []):
            self.add_reply(turn.session_id, turn.user_id, spec)
        self.status.pop(turn.session_id, None)
        turn.done = True

    def abort_turn(self, session_id: str) -> None:
        turn = self.turns.get(session_id)
        if turn is None or turn.done or session_id not in self.sessions:
            return
        self.add_reply(session_id, turn.user_id, {"text": "", "finish": None, "error": {"name": "MessageAbortedError", "data": {"message": "The operation was aborted."}}})
        self.status.pop(session_id, None)
        turn.done = True

    # ---- HTTP entry point ---------------------------------------------------------------
    async def handle(self, request: httpx.Request) -> httpx.Response:
        route, params = self.match(request.method, request.url.path)
        body = json.loads(request.content) if request.content else None
        self.requests.append(Seen(request.method, route, request.url.path, params, dict(request.url.params), body, decode_basic(request.headers.get("authorization")), request.url.host, request.url.port))
        if route in self.holds:
            entered, release = self.holds[route]
            entered.set()
            await release.wait()
        if self.dead:
            raise httpx.ConnectError("connection refused", request=request)
        failure = self.take_failure(route)
        if failure is not None:
            return self.failure_response(failure, request, params)
        if route in self.overrides:
            status, payload = self.overrides[route]
            return httpx.Response(status, content=payload) if isinstance(payload, bytes) else httpx.Response(status, json=payload)
        if route == "unknown":
            return httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "no such route"}})
        return getattr(self, f"on_{route}")(params, dict(request.url.params), body)

    def match(self, method: str, path: str) -> tuple[str, dict[str, str]]:
        for route_method, pattern, name in ROUTES:
            found = re.fullmatch(pattern, path)
            if route_method == method and found:
                return name, found.groupdict()
        return "unknown", {}

    def take_failure(self, route: str) -> str | None:
        entry = self.failures.get(route)
        if entry is None:
            return None
        kind, times = entry
        if times is not None:
            entry[1] = times - 1
            if entry[1] <= 0:
                del self.failures[route]
        return kind

    def failure_response(self, kind: str, request: httpx.Request, params: Mapping[str, str]) -> httpx.Response:
        if kind == "connect":
            raise httpx.ConnectError("connection refused", request=request)
        if kind == "timeout":
            raise httpx.ReadTimeout("read timed out", request=request)
        bodies: dict[str, tuple[int, Any]] = {
            "401": (401, b""),
            "503": (503, {"name": "ServiceUnavailable", "data": {"message": "server is starting"}}),
            "500": (500, {"name": "UnknownError", "data": {"message": "backend exploded"}}),
            "400": (400, {"name": "BadRequest", "data": {"message": "Agent not found: ghost"}}),
            "404": (404, {"name": "NotFoundError", "data": {"message": "Session not found"}}),
            "409": (409, {"_tag": "SessionBusyError", "sessionID": params.get("sid", ""), "message": "Session is busy"}),
            "not_json": (200, b"<html>opencode</html>"),
            "oversize": (200, b"[" + b" " * (8 * 1024 * 1024) + b"]"),
        }
        status, payload = bodies[kind]
        return httpx.Response(status, content=payload) if isinstance(payload, bytes) else httpx.Response(status, json=payload)

    def not_found(self) -> httpx.Response:
        return httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "Session not found"}})

    # ---- route handlers (opencode 1.18.31 shapes) -------------------------------------
    def on_health(self, params: Any, query: Any, body: Any) -> httpx.Response:
        return httpx.Response(200, json=self.health)

    def on_provider(self, params: Any, query: Any, body: Any) -> httpx.Response:
        return httpx.Response(200, json={"all": self.providers, "default": self.defaults, "connected": self.connected})

    def on_provider_auth(self, params: Any, query: Any, body: Any) -> httpx.Response:
        return httpx.Response(200, json=self.auth_methods)

    def on_config_providers(self, params: Any, query: Any, body: Any) -> httpx.Response:
        connected = [provider for provider in self.providers if provider["id"] in self.connected]
        return httpx.Response(200, json={"providers": connected, "default": self.defaults})

    def on_session_create(self, params: Any, query: Any, body: Any) -> httpx.Response:
        session_id = self.next_id("ses")
        session = self.add_session(session_id, (body or {}).get("title") or "New session")
        return httpx.Response(200, json=session)

    def on_session_list(self, params: Any, query: Mapping[str, str], body: Any) -> httpx.Response:
        # Oldest first on purpose: the host must sort by time.updated itself.
        listed = sorted(self.sessions.values(), key=lambda item: item["time"]["created"])
        limit = int(query.get("limit", len(listed)))
        return httpx.Response(200, json=listed[:limit])

    def on_session_status(self, params: Any, query: Any, body: Any) -> httpx.Response:
        for turn in list(self.turns.values()):
            self.advance(turn)
        return httpx.Response(200, json={key: value for key, value in self.status.items() if key in self.sessions})

    def on_session_get(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        session = self.sessions.get(params["sid"])
        return httpx.Response(200, json=session) if session is not None else self.not_found()

    def on_session_children(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        if params["sid"] not in self.sessions:
            return self.not_found()
        return httpx.Response(200, json=[item for item in self.sessions.values() if item.get("parentID") == params["sid"]])

    def on_prompt_async(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        if params["sid"] not in self.sessions:
            return self.not_found()
        self.start_turn(params["sid"], body or {})
        return httpx.Response(204)

    def on_fork(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        source = self.sessions.get(params["sid"])
        if source is None:
            return self.not_found()
        forked = self.add_session(self.next_id("ses"), f"{source['title']} (fork #1)")
        return httpx.Response(200, json=forked)

    def on_revert(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        session = self.sessions.get(params["sid"])
        if session is None:
            return self.not_found()
        session["revert"] = {"messageID": body["messageID"], **({"partID": body["partID"]} if body.get("partID") else {}), "snapshot": "snap-1"}
        return httpx.Response(200, json=session)

    def on_unrevert(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        session = self.sessions.get(params["sid"])
        if session is None:
            return self.not_found()
        session.pop("revert", None)
        return httpx.Response(200, json=session)

    def on_abort(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        # Verified: `200 true` even when the session does not exist.
        self.abort_turn(params["sid"])
        return httpx.Response(200, json=True)

    def on_messages(self, params: Mapping[str, str], query: Mapping[str, str], body: Any) -> httpx.Response:
        if params["sid"] not in self.sessions:
            return self.not_found()
        listed = self.messages[params["sid"]]
        if "before" in query:
            listed = [item for item in listed if item["info"]["id"] < query["before"]]
        limit = int(query.get("limit", len(listed) or 1))
        return httpx.Response(200, json=listed[-limit:])

    def on_message_get(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        for item in self.messages.get(params["sid"], []):
            if item["info"]["id"] == params["mid"]:
                return httpx.Response(200, json=item)
        return httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "Message not found"}})

    def on_diff(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        # Verified: `200 []` for a missing session.
        return httpx.Response(200, json=self.diffs.get(params["sid"], []))

    def on_permission_list(self, params: Any, query: Any, body: Any) -> httpx.Response:
        return httpx.Response(200, json=self.permissions)

    def on_permission_reply(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        self.permissions = [item for item in self.permissions if item["id"] != params["rid"]]
        return httpx.Response(200, json=True)

    def on_question_list(self, params: Any, query: Any, body: Any) -> httpx.Response:
        return httpx.Response(200, json=self.questions)

    def on_question_reject(self, params: Mapping[str, str], query: Any, body: Any) -> httpx.Response:
        self.questions = [item for item in self.questions if item["id"] != params["rid"]]
        return httpx.Response(200, json=True)

    def on_mcp_add(self, params: Any, query: Any, body: Any) -> httpx.Response:
        if self.mcp_answer is not None:
            return httpx.Response(200, json=self.mcp_answer)
        return httpx.Response(200, json={body["name"]: {"status": "connected"}})


class ServeFake:
    """Writes scenarios for fake_opencode_serve.py and reads what its processes logged."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_dir = root / "serve-log"
        self.log_dir.mkdir()
        self.die_file = root / "serve-die.flag"
        self.scenarios = 0

    def command(self, **scenario: Any) -> tuple[str, ...]:
        self.scenarios += 1
        path = self.root / f"serve-scenario-{self.scenarios}.json"
        data = {"log_dir": str(self.log_dir), "mode": "listen", "port": OWNED_PORT, "die_file": str(self.die_file), **scenario}
        path.write_text(json.dumps(data), encoding="utf-8")
        return (sys.executable, "-u", str(FAKE_SERVE), str(path))

    def missing_command(self) -> tuple[str, ...]:
        return (str(self.root / "no-such-folder" / "opencode"),)

    def not_executable_command(self) -> tuple[str, ...]:
        path = self.root / "opencode-not-a-program.txt"
        path.write_text("this file is not a program\n", encoding="utf-8")
        return (str(path),)

    def kill_server(self) -> None:
        self.die_file.write_text("die", encoding="utf-8")

    def records(self, kind: str | None = None) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(self.log_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    if kind is None or record["kind"] == kind:
                        found.append(record)
        return found

    def pids(self) -> list[int]:
        return [record["pid"] for record in self.records("start")] + [record["grandchild_pid"] for record in self.records("grandchild")]


class LoopbackSilentServer:
    """A real 127.0.0.1 socket that may answer `/global/health` and then never answers anything else (AC-3)."""

    def __init__(self, *, answer_health: bool) -> None:
        self.answer_health = answer_health
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(0.05)
        self.port = self.listener.getsockname()[1]
        self.stop = threading.Event()
        self.connections: list[socket.socket] = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def serve(self) -> None:
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            self.connections.append(connection)
            threading.Thread(target=self.answer, args=(connection,), daemon=True).start()

    def answer(self, connection: socket.socket) -> None:
        connection.settimeout(0.05)
        data = b""
        while b"\r\n\r\n" not in data and not self.stop.is_set():
            try:
                chunk = connection.recv(4096)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            if not chunk:
                return
            data += chunk
        target = data.split(b" ", 2)[1] if data.count(b" ") >= 2 else b""
        if self.answer_health and target.startswith(b"/global/health"):
            body = json.dumps({"healthy": True, "version": "1.18.31"}).encode("utf-8")
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
            connection.close()
            return
        # Accept the request and never answer it.
        self.stop.wait()

    def close(self) -> None:
        self.stop.set()
        self.listener.close()
        for connection in self.connections:
            try:
                connection.close()
            except OSError:
                pass
        self.thread.join(timeout=1.0)


def member_name(code: str) -> str:
    # Spec §6.3.1: member names are the upper-cased value with "." replaced by "_".
    return code.upper().replace(".", "_")


@pytest.fixture
def opencode_api() -> SimpleNamespace:
    # Spec §8.5 and §9.1 names, imported lazily so a missing module fails setup, not collection.
    host_module = importlib.import_module("vidbyte.harnesses.native.opencode")
    records = importlib.import_module("vidbyte.lib.dataclasses.opencode")
    native_records = importlib.import_module("vidbyte.lib.dataclasses.native_hosts")
    native_enums = importlib.import_module("vidbyte.lib.enums.native_hosts")
    backend_enums = importlib.import_module("vidbyte.lib.enums.harness_backends")
    errors = importlib.import_module("vidbyte.lib.errors")
    failure = importlib.import_module("vidbyte.lib.enums.failure")
    names = (
        "OpencodeHostSettings", "OpencodePermissionRule", "OpencodePromptRequest", "OpencodeSpawnRequest", "OpencodeMcpServerConfig",
        "OpencodeReadiness", "OpencodeModel", "OpencodeProvider", "OpencodeAuthMethod", "OpencodeProviderAuth", "OpencodeSession",
        "OpencodeMessage", "OpencodeMessagePage", "OpencodeFileDiff", "OpencodeMcpStatus",
    )
    namespace = {name: getattr(records, name) for name in names}
    namespace.update({name: getattr(native_records, name) for name in ("NativeTurnHandle", "NativeTurnResult", "NativeInterruptResult", "NativeSessionUsage", "NativeTokenUsage", "NativeApprovalDecision")})
    namespace.update({name: getattr(native_enums, name) for name in ("NativeHarness", "NativeTurnStatus", "InterruptSource", "ApprovalOutcome", "OpencodePermissionAction", "OpencodeMcpKind")})
    return SimpleNamespace(
        OpencodeHost=host_module.OpencodeHost,
        HarnessBackendName=backend_enums.HarnessBackendName,
        NativeHostError=errors.NativeHostError,
        ConfigurationError=errors.ConfigurationError,
        FailureCode=failure.FailureCode,
        constants=importlib.import_module("vidbyte.lib.constants.native_hosts"),
        **namespace,
    )


@pytest.fixture
def opencode_tools_api() -> SimpleNamespace:
    toolsets = importlib.import_module("vidbyte.tools.toolsets")
    tool_types = importlib.import_module("vidbyte.tools.types")
    return SimpleNamespace(
        OpencodeTools=toolsets.OpencodeTools,
        ToolCall=tool_types.ToolCall,
        ToolStatus=tool_types.ToolStatus,
        ToolPermission=tool_types.ToolPermission,
        ToolExecutor=importlib.import_module("vidbyte.tools.executor").ToolExecutor,
        PermissionPolicy=importlib.import_module("vidbyte.tools.security").PermissionPolicy,
        opencode_tools_module=importlib.import_module("vidbyte.tools.builtins.opencode"),
    )


@pytest.fixture
def fast_timings(opencode_api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Spec §9.3/§13: these three are read through the constants module at call time.
    monkeypatch.setattr(opencode_api.constants, "NATIVE_STOP_GRACE_SECONDS", FAST_GRACE_SECONDS)
    monkeypatch.setattr(opencode_api.constants, "NATIVE_KILL_WAIT_SECONDS", FAST_KILL_WAIT_SECONDS)
    monkeypatch.setattr(opencode_api.constants, "OPENCODE_POLL_INTERVAL_SECONDS", FAST_POLL_SECONDS)
    return SimpleNamespace(grace=FAST_GRACE_SECONDS, kill_wait=FAST_KILL_WAIT_SECONDS, poll=FAST_POLL_SECONDS, slack=SLACK_SECONDS)


@pytest.fixture
def fake_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeOpencodeServer:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = FakeOpencodeServer(workspace)

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        # The real AsyncClient, wired to the in-memory server (prior art: tests/test_http_transport_content_type.py).
        return REAL_ASYNC_CLIENT(*args, transport=httpx.MockTransport(server.handle), **kwargs)

    monkeypatch.setattr("vidbyte.lib.http.transport.httpx.AsyncClient", client_factory)
    return server


@pytest.fixture
def attached_secret() -> str:
    # Generated per test so no credential-shaped literal is committed.
    return "pw-" + uuid.uuid4().hex


def default_mcp_servers(api: SimpleNamespace) -> dict[str, Any]:
    return {"files": api.OpencodeMcpServerConfig(name="files", kind=api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"))}


@pytest.fixture
def make_opencode_host(opencode_api: SimpleNamespace, fake_opencode: FakeOpencodeServer, fast_timings: SimpleNamespace, attached_secret: str) -> Callable[..., Any]:
    def build(*, max_live_turns: int = 4, request_timeout_seconds: float = 10.0, mcp_servers: Mapping[str, Any] | None = None) -> Any:
        settings = opencode_api.OpencodeHostSettings(
            workspace=fake_opencode.workspace,
            server_url=ATTACHED_URL,
            server_username=ATTACHED_LOGIN,
            server_password=attached_secret,
            request_timeout_seconds=request_timeout_seconds,
            max_live_turns=max_live_turns,
            mcp_servers=dict(mcp_servers) if mcp_servers is not None else default_mcp_servers(opencode_api),
        )
        return opencode_api.OpencodeHost(settings)

    return build


@pytest.fixture
def serve_fake(tmp_path: Path) -> ServeFake:
    return ServeFake(tmp_path)


@pytest.fixture
def silent_loopback() -> Any:
    # A factory, because conftest helpers cannot be imported by name from a pack without __init__.py.
    servers: list[LoopbackSilentServer] = []

    def build(*, answer_health: bool) -> LoopbackSilentServer:
        server = LoopbackSilentServer(answer_health=answer_health)
        servers.append(server)
        return server

    yield build
    for server in servers:
        server.close()


@pytest.fixture
def check_native_error(opencode_api: SimpleNamespace) -> Callable[..., None]:
    def check(error: BaseException, *, code: str, token: str, operation: str | None = None) -> None:
        assert isinstance(error, opencode_api.NativeHostError), f"expected NativeHostError, got {type(error).__name__}: {error}"
        assert error.failure_code is opencode_api.FailureCode[member_name(code)], f"expected {code}, got {error.failure_code.value}: {error}"
        assert error.next_step.strip(), "INV-8: next_step is never empty"
        assert token in error.next_step, f"next_step {error.next_step!r} lacks the required token {token!r}"
        if operation is not None:
            assert error.operation == operation
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in error.context.items()), "spec §13: every context value is a str"
        assert set(error.context) <= CONTEXT_KEYS, f"unexpected context keys {set(error.context) - CONTEXT_KEYS}"

    return check


@pytest.fixture
def check_tool_error(opencode_tools_api: SimpleNamespace) -> Callable[..., None]:
    def check(result: Any, *, code: str, token: str, tool_name: str, harness: str = "opencode") -> None:
        assert result.status is opencode_tools_api.ToolStatus.ERROR, f"expected an error result, got {result.output!r}"
        metadata = result.metadata
        assert metadata["error"] == code, f"expected {code}, got {metadata.get('error')}: {result.output}"
        assert token in metadata["next_step"], f"next_step {metadata['next_step']!r} lacks {token!r}"
        assert metadata["hint"] == metadata["next_step"], "INV-7: hint repeats next_step"
        assert metadata["operation"] == tool_name
        assert metadata["harness"] == harness
        assert result.output.startswith(f"{code}: "), result.output
        assert result.output.endswith(f" Next step: {metadata['next_step']}"), result.output

    return check


@pytest.fixture
def wait_until() -> Callable[[Callable[[], bool], float], Awaitable[bool]]:
    async def poll(predicate: Callable[[], bool], timeout: float) -> bool:
        # Bounded polling, the prior art in test_bash_tool_process_bounds.py; never a fixed sleep.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return True
            await asyncio.sleep(POLL_SECONDS)
        return predicate()

    return poll


@pytest.fixture
def process_running() -> Callable[[int], bool]:
    def running(pid: int) -> bool:
        # POSIX only. A zombie has already exited, so only a live process counts as running.
        stat_path = Path("/proc") / str(pid) / "stat"
        if Path("/proc/self").exists():
            try:
                stat = stat_path.read_text(encoding="utf-8")
            except OSError:
                return False
            return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    return running


@pytest.fixture
def tool_by_name() -> Callable[[Any, str], Any]:
    def named(toolset: Any, name: str) -> Any:
        tools = {tool.name: tool for tool in toolset.all()}
        assert name in tools, f"toolset lacks {name}: {sorted(tools)}"
        return tools[name]

    return named
