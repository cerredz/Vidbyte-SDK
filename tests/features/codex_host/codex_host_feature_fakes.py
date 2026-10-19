"""FILE: tests/features/codex_host/codex_host_feature_fakes.py

PURPOSE: The first-class-features half of the in-memory codex app-server in codex_host_fakes.py. It holds the switches that shape the slice-2 answers and the handlers for collaborationMode/list, mcpServerStatus/list, thread/settings/update, turn/settings/update, thread/memoryMode/set, memory/status, memory/reset, thread/archive, thread/unarchive, thread/revert, thread/inject_items, the two thread/backgroundTerminals methods and thread/search, plus the child-thread filters of thread/list and the edit and resume forms of thread/goal/set, all answered the way codex app-server 0.163.0 does by its schema.
ROLE IN CODEBASE: codex_host_fakes.FakeAppServer inherits FeatureHandlers next to HelperHandlers, so a test sets these switches and calls these drive helpers on self.server like any other. The answers are built from the 0.163.0 schema's member names, so the real openai-codex models, and the host's own translators for the unmodeled methods, read them unchanged (docs/spec/codex-host-first-class/spec.md section 13).
ARCHITECTURE NOTE: FeatureHandlers is a mixin with no state of its own. FakeAppServer.__init__ calls _init_feature_switches() after the helper switches and splices _feature_handlers() into its method table after the helper handlers, so the thread/list and thread/goal/set entries here replace the helper ones and fall back to them for every older request shape; holds, scripted failures and before_response treat the new methods exactly as the older ones. feature_answers replaces one method's answer with a scripted value, which is how the malformed-answer tests (AC-41) reach the host's translators. This module reaches codex_host_fakes only on use, through _fakes(), because codex_host_fakes imports it to build FakeAppServer.
FUNCTION INVENTORY: FeatureHandlers: _init_feature_switches sets collaboration_modes, feature_answers, mcp_servers, mcp_next_cursor, turn_settings_status, memory_status, background_terminals, archived, injected, memory_modes, goal_resume_starts_turn and search_snippet; _feature_handlers maps the fourteen new methods and the two replaced ones; _scripted answers a method from feature_answers or its handler; one handler per method; _child_threads with _descends answers the thread/list child filters; _feature_goal_set answers the edit and resume forms of thread/goal/set; plan_item, reasoning_item, started_note, delta_note, plan_update_note and diff_note build items and notifications for the stream tests. PLAN_PRESET, DEFAULT_PRESET, mcp_server and background_terminal build the wire shapes.
COMMON MODIFICATION PATTERNS: Teach the fake another slice-2 method by adding its handler here and its name to _feature_handlers, building the answer from the schema's member names. Add a switch to _init_feature_switches, neutral by default, when a test needs Codex to answer differently.
WHAT NOT TO DO IN THIS FILE: 1. Do not import codex_host_fakes at module level; use _fakes(). 2. Do not change an answer an older request shape gets: the thread/list and thread/goal/set replacements fall back to the helper handlers. 3. Do not start a real process, run codex or touch the network (NFR-12), and do not encode the host's own rules; answer as Codex would and let the tests assert the spec.
KNOWN EDGE CASES: thread/settings/update, thread/memoryMode/set, thread/revert and thread/inject_items refuse a notLoaded thread with -32600, as compact does, because the spec assumes they need a loaded thread (A-4). thread/search and the child filters of thread/list apply Codex's default source filter, CLI and VS Code only, when sourceKinds is absent or empty (spec section 13, D-35), so a host that drops the key finds nothing. thread/unarchive refuses a thread that is not archived (EC-43). A status-only active set on a stored goal that is not active starts a goal turn while goal_resume_starts_turn is on (A-1, A-19). An objective sent without a status to a thread that has a goal edits it in place and starts no turn.
RELATED DOCS: tests/features/codex_host/FEATURE.md; tests/features/codex_host/codex_host_fakes.py; tests/features/codex_host/codex_host_helper_fakes.py; docs/spec/codex-host-first-class/spec.md sections 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host
"""

from __future__ import annotations

import copy
import functools
import threading
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import TYPE_CHECKING, Any

from tests.features.codex_host.codex_host_helper_fakes import source_kind

if TYPE_CHECKING:
    from tests.features.codex_host.codex_host_fakes import FakeThread, Note, Reply

# Codex's own presets, as collaborationMode/list answers them (CollaborationModeMask): a null model means the thread's model.
PLAN_PRESET: dict[str, Any] = {"name": "Plan", "mode": "plan", "model": None, "reasoning_effort": "medium"}
DEFAULT_PRESET: dict[str, Any] = {"name": "Default", "mode": "default", "model": None, "reasoning_effort": None}
# ThreadSearchParams: an absent or empty sourceKinds means the interactive sources only.
INTERACTIVE_SOURCE_KINDS = ("cli", "vscode")


def _fakes() -> ModuleType:
    # codex_host_fakes builds FakeAppServer from FeatureHandlers while it loads, so it is reached here on use, never at import.
    from tests.features.codex_host import codex_host_fakes

    return codex_host_fakes


def mcp_server(name: str, *, tools: tuple[str, ...] = ("search", "fetch"), resources: int = 1, templates: int = 0, auth: str = "oAuth", runtime: str | None = None, **extra: Any) -> dict[str, Any]:
    """One McpServerStatus entry of an mcpServerStatus/list answer; runtimeStatus is left out when runtime is None."""
    server: dict[str, Any] = {
        "name": name,
        "authStatus": auth,
        "tools": {tool: {"name": tool, "inputSchema": {"type": "object"}} for tool in tools},
        "resources": [{"name": f"resource-{index}", "uri": f"file:///resource-{index}"} for index in range(resources)],
        "resourceTemplates": [{"name": f"template-{index}", "uriTemplate": f"file:///template-{index}/{{id}}"} for index in range(templates)],
    }
    if runtime is not None:
        server["runtimeStatus"] = runtime
    server.update(extra)
    return server


def background_terminal(process_id: str, item_id: str, command: str = "npm run dev", **extra: Any) -> dict[str, Any]:
    """One ThreadBackgroundTerminal entry of a thread/backgroundTerminals/list answer."""
    return {"processId": process_id, "itemId": item_id, "command": command, "cwd": _fakes().DEFAULT_CWD, **extra}


class FeatureHandlers:
    """The slice-2 methods of FakeAppServer, answered over the server's own threads and condition."""

    # FakeAppServer, which inherits this mixin, owns this state and these store helpers.
    threads: dict[str, FakeThread]
    _cond: threading.Condition
    _ids: Iterator[int]
    _item_ids: Iterator[int]
    thread_or_error: Callable[[str], FakeThread]
    next_turn_id: Callable[[], str]
    _thread_list: Callable[[dict[str, Any]], Any]
    _goal_set: Callable[[dict[str, Any]], Reply]

    def _init_feature_switches(self) -> None:
        # Codex's preset list, in its order; a test removes the plan preset to see run_codex_plan refuse.
        self.collaboration_modes: list[dict[str, Any]] = [copy.deepcopy(PLAN_PRESET), copy.deepcopy(DEFAULT_PRESET)]
        # feature_answers: method -> the raw result to answer instead of the handler's (the AC-41 malformed answers).
        self.feature_answers: dict[str, Any] = {}
        self.mcp_servers: list[dict[str, Any]] = []
        self.mcp_next_cursor: str | None = None
        # The status turn/settings/update answers for a running turn; a turn that is not running gets targetUnavailable.
        self.turn_settings_status = "applied"
        self.memory_status: dict[str, Any] = {"v2ConsolidatedThreads": 3, "v2Ready": True}
        self.background_terminals: dict[str, list[dict[str, Any]]] = {}
        self.archived: set[str] = set()
        self.injected: dict[str, list[Any]] = {}
        self.memory_modes: dict[str, str] = {}
        # goal_resume_starts_turn: a status-only active set on a goal that is not active starts a goal turn (A-1, A-19).
        self.goal_resume_starts_turn = True
        self.search_snippet = "the matching line"

    def _feature_handlers(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "collaborationMode/list": self._collaboration_modes,
            "mcpServerStatus/list": self._mcp_servers,
            "thread/settings/update": self._thread_settings,
            "turn/settings/update": self._turn_settings,
            "thread/memoryMode/set": self._memory_mode,
            "memory/status": self._memory_status,
            "memory/reset": self._memory_reset,
            "thread/archive": self._thread_archive,
            "thread/unarchive": self._thread_unarchive,
            "thread/revert": self._thread_revert,
            "thread/inject_items": self._inject_items,
            "thread/backgroundTerminals/list": self._terminals_list,
            "thread/backgroundTerminals/clean": self._terminals_clean,
            "thread/search": self._thread_search,
            # These two replace the helper handlers and fall back to them for every older request shape.
            "thread/list": self._child_threads,
            "thread/goal/set": self._feature_goal_set,
        }
        return {method: functools.partial(self._scripted, method, handler) for method, handler in handlers.items()}

    def _scripted(self, method: str, handler: Callable[[dict[str, Any]], Any], params: dict[str, Any]) -> Any:
        # A scripted answer replaces the handler's, so a test can send a malformed answer through the real client.
        if method in self.feature_answers:
            return copy.deepcopy(self.feature_answers[method])
        return handler(params)

    def _loaded_or_error(self, thread_id: str) -> FakeThread:
        # These calls act only on a thread loaded in this app-server (spec A-4), as compact does.
        thread = self.thread_or_error(thread_id)
        if thread.status == "notLoaded":
            raise _fakes().FakeRpcError(-32600, f"thread not loaded: {thread.thread_id}")
        return thread

    def _collaboration_modes(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"data": copy.deepcopy(self.collaboration_modes)}

    def _mcp_servers(self, params: dict[str, Any]) -> dict[str, Any]:
        # A thread filter names a thread Codex must know (EC-26); without one Codex lists its own servers (A-5).
        if params.get("threadId"):
            self.thread_or_error(params["threadId"])
        servers = [server for server in self.mcp_servers if not params.get("serverName") or server["name"] == params["serverName"]]
        return {"data": copy.deepcopy(servers), "nextCursor": self.mcp_next_cursor}

    def _thread_settings(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self._loaded_or_error(params["threadId"])
        if params.get("model"):
            thread.model = params["model"]
        return {}

    def _turn_settings(self, params: dict[str, Any]) -> dict[str, Any]:
        # Codex applies the change only to a turn that is still running; any other turn is no target.
        thread = self.thread_or_error(params["threadId"])
        turn = thread.find_turn(params["turnId"])
        if turn is None or turn.status != "inProgress":
            return {"status": "targetUnavailable"}
        return {"status": self.turn_settings_status}

    def _memory_mode(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self._loaded_or_error(params["threadId"])
        self.memory_modes[thread.thread_id] = params["mode"]
        return {}

    def _memory_status(self, params: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(self.memory_status)

    def _memory_reset(self, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _thread_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        self.archived.add(thread.thread_id)
        return {}

    def _thread_unarchive(self, params: dict[str, Any]) -> dict[str, Any]:
        # Codex cannot unarchive a thread that is not archived, or one it does not know (EC-43).
        thread_id = params["threadId"]
        if thread_id not in self.archived:
            raise _fakes().FakeRpcError(-32600, f"thread is not archived: {thread_id}")
        self.archived.discard(thread_id)
        return {"thread": self.thread_or_error(thread_id).wire(include_turns=False)}

    def _thread_revert(self, params: dict[str, Any]) -> dict[str, Any]:
        # The history keeps every turn before beforeTurnId; files are not touched (NG-16).
        thread = self._loaded_or_error(params["threadId"])
        ids = [turn.turn_id for turn in thread.turns]
        if params.get("beforeTurnId") not in ids:
            raise _fakes().FakeRpcError(-32600, f"unknown beforeTurnId: {params.get('beforeTurnId')}")
        thread.turns = thread.turns[: ids.index(params["beforeTurnId"])]
        return {"thread": thread.wire(include_turns=False)}

    def _inject_items(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self._loaded_or_error(params["threadId"])
        with self._cond:
            self.injected.setdefault(thread.thread_id, []).extend(copy.deepcopy(params["items"]))
            self._cond.notify_all()
        return {}

    def _terminals_list(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        return {"data": copy.deepcopy(self.background_terminals.get(thread.thread_id, [])), "nextCursor": None}

    def _terminals_clean(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        self.background_terminals.pop(thread.thread_id, None)
        return {}

    def _thread_search(self, params: dict[str, Any]) -> dict[str, Any]:
        # Codex matches the term in a thread's name or in its stored message text, within the source kinds asked for.
        kinds = params.get("sourceKinds") or list(INTERACTIVE_SOURCE_KINDS)
        term = params["searchTerm"]
        archived = bool(params.get("archived"))
        hits = []
        for thread in list(self.threads.values()):
            texts = [thread.name or ""] + [str(item.get("text", "")) for turn in thread.turns for item in turn.items]
            if source_kind(thread) in kinds and (thread.thread_id in self.archived) == archived and any(term in text for text in texts):
                hits.append({"snippet": self.search_snippet, "thread": thread.wire(include_turns=False)})
        return {"data": hits, "nextCursor": None, "backwardsCursor": None}

    def _child_threads(self, params: dict[str, Any]) -> Any:
        # Only the child filters are new; every other listing is the helper handler's, unchanged.
        if "parentThreadId" not in params and "ancestorThreadId" not in params:
            return self._thread_list(params)
        kinds = params.get("sourceKinds") or list(INTERACTIVE_SOURCE_KINDS)
        children = [thread for thread in list(self.threads.values()) if self._descends(thread, params) and source_kind(thread) in kinds]
        return {"data": [thread.wire(include_turns=False) for thread in children], "nextCursor": None}

    def _descends(self, thread: FakeThread, params: dict[str, Any]) -> bool:
        # parentThreadId lists direct children; ancestorThreadId lists every depth below the ancestor.
        if "parentThreadId" in params:
            return thread.parent_thread_id == params["parentThreadId"]
        parent = thread.parent_thread_id
        seen: set[str] = set()
        while parent is not None and parent not in seen:
            if parent == params["ancestorThreadId"]:
                return True
            seen.add(parent)
            stored = self.threads.get(parent)
            parent = stored.parent_thread_id if stored is not None else None
        return False

    def _feature_goal_set(self, params: dict[str, Any]) -> Reply:
        fakes = _fakes()
        thread = self.thread_or_error(params["threadId"])
        prior = thread.goal.get("status") if thread.goal is not None else None
        # An objective sent without a status to a stored goal edits it in place: status and usage stay, no turn starts.
        if thread.goal is not None and params.get("objective") is not None and params.get("status") is None:
            thread.goal["objective"] = params["objective"]
            return self._goal_set({key: value for key, value in params.items() if key != "objective"})
        reply = self._goal_set(params)
        # A status-only active set on a goal that was not active resumes it, and Codex starts a goal turn (A-1, A-19).
        resumes = params.get("status") == "active" and params.get("objective") is None and prior not in (None, "active")
        if resumes and self.goal_resume_starts_turn:
            turn = fakes.FakeTurn(turn_id=self.next_turn_id())
            thread.turns.append(turn)
            reply.after.append(("turn/started", {"threadId": thread.thread_id, "turn": turn.wire(with_items=False)}))
        return reply

    # ----- items and notifications for the stream tests -----

    def plan_item(self, text: str) -> dict[str, Any]:
        return {"type": "plan", "id": f"item-{next(self._item_ids)}", "text": text}

    def reasoning_item(self, summary: str, content: str) -> dict[str, Any]:
        return {"type": "reasoning", "id": f"item-{next(self._item_ids)}", "summary": [summary], "content": [content]}

    def started_note(self, thread_id: str, turn_id: str, item: dict[str, Any]) -> Note:
        return ("item/started", {"item": copy.deepcopy(item), "startedAtMs": (_fakes().BASE_TIME + 1) * 1000, "threadId": thread_id, "turnId": turn_id})

    def delta_note(self, method: str, thread_id: str, turn_id: str, item_id: str, delta: str, **extra: Any) -> Note:
        """One item delta notification, such as item/agentMessage/delta; extra adds summaryIndex or contentIndex."""
        return (method, {"delta": delta, "itemId": item_id, "threadId": thread_id, "turnId": turn_id, **extra})

    def plan_update_note(self, thread_id: str, turn_id: str, steps: list[dict[str, Any]], explanation: str | None = None) -> Note:
        params: dict[str, Any] = {"plan": copy.deepcopy(steps), "threadId": thread_id, "turnId": turn_id}
        if explanation is not None:
            params["explanation"] = explanation
        return ("turn/plan/updated", params)

    def diff_note(self, thread_id: str, turn_id: str, diff: str) -> Note:
        return ("turn/diff/updated", {"diff": diff, "threadId": thread_id, "turnId": turn_id})
