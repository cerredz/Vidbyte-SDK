"""FILE: tests/features/codex_host/codex_host_helper_fakes.py

PURPOSE: The thread-helper, goal and skill half of the in-memory codex app-server in codex_host_fakes.py. It holds the switches that shape those answers and the handlers for paged thread/list, the three thread/goal methods (set, clear, get), thread/compact/start, thread/delete, thread/turns/list and skills/list, plus the turn/start input recording that the skill read-back reads, all answered the way codex app-server 0.162 does.
ROLE IN CODEBASE: codex_host_fakes.FakeAppServer inherits HelperHandlers, so a test sets these switches and reaches these handlers on self.server like any other. codex_host_fakes re-exports goal_record and skill_entry, so tests keep calling self.fakes.goal_record and self.fakes.skill_entry; no test imports this module.
ARCHITECTURE NOTE: HelperHandlers is a mixin with no state of its own. FakeAppServer.__init__ calls _init_helper_switches() at the point where the switches sat before the split, and splices _helper_handlers() into its method table where those entries sat, so holds, scripted failures and the per-request answer thread treat these methods exactly as they treat the older ones. The handlers read and change the server's threads under its condition. thread/goal/set and thread/goal/clear predate the thread helpers and sit here so the goal methods live together; their switches (goal_starts_turn, goal_updates, budget_echo) are still set by FakeAppServer.__init__. This module reaches codex_host_fakes (FakeRpcError, FakeTurn, Reply, BASE_TIME, DEFAULT_CWD, _UNSET) only on use, through _fakes(), because codex_host_fakes imports this module to build FakeAppServer and a module-level import would be circular.
FUNCTION INVENTORY: HelperHandlers: _init_helper_switches sets paged_thread_list, thread_page_size, endless_thread_list, skills, record_turn_input, drop_skill_input, input_hidden_reads, recorded_skill_name, input_on_earlier_turn, goal_get_answer and turn_cursors, each off or empty by default; _helper_handlers maps the seven methods besides thread/list, in the table order they had before the split; _thread_list with _listed_threads and _offset answers thread/list; _record_turn_input stores turn/start's input as Codex records it; _goal_clear, _goal_set, _goal_get, _thread_compact, _thread_delete, _turns_list with _listed_turn, and _skills_list answer the rest. goal_record and skill_entry build a stored goal and a skills/list entry; source_kind maps a thread's source to the ThreadSourceKind a sourceKinds filter matches.
COMMON MODIFICATION PATTERNS: Teach the fake a new thread-helper, goal or skill method by adding its handler here and its name to _helper_handlers, building the answer from the generated model's aliases. Add a switch to _init_helper_switches, off by default, when a test needs Codex to answer differently.
WHAT NOT TO DO IN THIS FILE: 1. Do not import codex_host_fakes at module level; use _fakes(). 2. Do not give a switch a default that changes an answer the older modules rely on. 3. Do not start a real process, run codex or touch the network (NG-13), and do not encode the host's own rules; answer as Codex would and let the tests assert the spec.
KNOWN EDGE CASES: Without a paging switch, thread/list keeps the single page with cursor-after-page that the older list tests pin. A cursor this fake did not issue, and that no test named in turn_cursors, is refused with -32600. thread/goal/get never loads a thread, so a notLoaded thread stays notLoaded, and thread/compact/start refuses one (spec A-4, A-5). input_hidden_reads counts only the thread/turns/list reads that ask for full items. thread/goal/set answers -32600 for a thread with no goal when no objective is sent.
RELATED DOCS: tests/features/codex_host/FEATURE.md; tests/features/codex_host/codex_host_fakes.py; docs/spec/codex-host-thread-helpers/spec.md section 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tests.features.codex_host.codex_host_fakes import FakeThread, FakeTurn, Note, Reply


def _fakes() -> ModuleType:
    # codex_host_fakes builds FakeAppServer from HelperHandlers while it loads, so it is reached here on use, never at import.
    from tests.features.codex_host import codex_host_fakes

    return codex_host_fakes


def goal_record(thread_id: str, objective: str, status: str = "active", *, token_budget: int | None = None, tokens_used: int = 0, time_used_seconds: int = 0) -> dict[str, Any]:
    """A stored ThreadGoal, keyed by its wire aliases; tokenBudget is left out when there is none."""
    goal: dict[str, Any] = {
        "createdAt": _fakes().BASE_TIME,
        "objective": objective,
        "status": status,
        "threadId": thread_id,
        "timeUsedSeconds": time_used_seconds,
        "tokensUsed": tokens_used,
        "updatedAt": _fakes().BASE_TIME + 30,
    }
    if token_budget is not None:
        goal["tokenBudget"] = token_budget
    return goal


def skill_entry(name: str, path: str, *, enabled: bool = True, scope: str = "user", description: str = "") -> dict[str, Any]:
    """One SkillMetadata entry of a skills/list answer."""
    return {"name": name, "description": description or f"The {name} skill.", "enabled": enabled, "path": path, "scope": scope}


def source_kind(thread: FakeThread) -> str:
    """The ThreadSourceKind a sourceKinds filter matches the thread's source against."""
    if isinstance(thread.source, str):
        return thread.source
    agent = thread.source.get("subAgent") if isinstance(thread.source, dict) else None
    if agent is None:
        return "unknown"
    if isinstance(agent, dict):
        return "subAgentThreadSpawn" if "thread_spawn" in agent else "subAgentOther"
    return {"review": "subAgentReview", "compact": "subAgentCompact"}.get(agent, "subAgentOther")


class HelperHandlers:
    """The thread-helper, goal and skill methods of FakeAppServer, answered over the server's own threads and condition."""

    # FakeAppServer, which inherits this mixin, owns this state and these store helpers.
    threads: dict[str, FakeThread]
    _cond: threading.Condition
    _ids: Iterator[int]
    _item_ids: Iterator[int]
    goal_starts_turn: bool
    goal_updates: bool
    budget_echo: Any
    thread_or_error: Callable[[str], FakeThread]
    next_turn_id: Callable[[], str]

    def _init_helper_switches(self) -> None:
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
        # recorded_skill_name: when set, each recorded skill entry carries this name instead of the one sent.
        # input_on_earlier_turn: the input is recorded on a completed turn placed before the started one, so the
        # first turn a page shows holds the skill but is not the turn turn/start returned.
        self.recorded_skill_name: str | None = None
        self.input_on_earlier_turn = False
        # goal_get_answer: when set, thread/goal/get answers goal_get_answer(thread) instead of the stored goal.
        self.goal_get_answer: Callable[[FakeThread], dict[str, Any] | None] | None = None
        # Extra thread/turns/list cursors a test names, mapped to the turn offset they resume at.
        self.turn_cursors: dict[str, int] = {}

    def _helper_handlers(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "thread/goal/clear": self._goal_clear,
            "thread/goal/set": self._goal_set,
            "thread/goal/get": self._goal_get,
            "thread/compact/start": self._thread_compact,
            "thread/delete": self._thread_delete,
            "thread/turns/list": self._turns_list,
            "skills/list": self._skills_list,
        }

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
            threads = [thread for thread in threads if source_kind(thread) in params["sourceKinds"]]
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
        raise _fakes().FakeRpcError(-32600, f"invalid cursor: {cursor}")

    def _record_turn_input(self, thread: FakeThread, turn: FakeTurn, params: dict[str, Any]) -> None:
        if not self.record_turn_input:
            return
        # Codex records the turn's input as its first item, a userMessage whose content is the input sent.
        content = [entry for entry in copy.deepcopy(params.get("input", [])) if not (self.drop_skill_input and entry.get("type") == "skill")]
        if self.recorded_skill_name is not None:
            content = [{**entry, "name": self.recorded_skill_name} if entry.get("type") == "skill" else entry for entry in content]
        message = {"type": "userMessage", "id": f"item-{next(self._item_ids)}", "content": content}
        if self.input_on_earlier_turn:
            earlier = _fakes().FakeTurn(turn_id=self.next_turn_id(), status="completed", items=[message])
            thread.turns.insert(len(thread.turns) - 1, earlier)
        else:
            turn.items.append(message)
            turn.hidden_reads = self.input_hidden_reads

    def _goal_clear(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = self.thread_or_error(params["threadId"])
        cleared = thread.goal is not None
        thread.goal = None
        return {"cleared": cleared}

    def _goal_set(self, params: dict[str, Any]) -> Reply:
        fakes = _fakes()
        thread = self.thread_or_error(params["threadId"])
        if params.get("objective") is not None:
            thread.goal = {"createdAt": fakes.BASE_TIME, "objective": params["objective"], "status": "active", "threadId": thread.thread_id, "timeUsedSeconds": 0, "tokensUsed": 0, "updatedAt": fakes.BASE_TIME}
        if thread.goal is None:
            raise fakes.FakeRpcError(-32600, f"thread has no goal: {thread.thread_id}")
        if params.get("status") is not None:
            thread.goal["status"] = params["status"]
        answer = dict(thread.goal)
        if "tokenBudget" in params:
            thread.goal["tokenBudget"] = params["tokenBudget"]
            answer["tokenBudget"] = params["tokenBudget"] if self.budget_echo is fakes._UNSET else self.budget_echo
        notes: list[Note] = [("thread/goal/updated", {"threadId": thread.thread_id, "goal": dict(thread.goal)})] if self.goal_updates else []
        if params.get("objective") is not None and thread.goal["status"] == "active" and self.goal_starts_turn:
            turn = fakes.FakeTurn(turn_id=self.next_turn_id())
            thread.turns.append(turn)
            notes.append(("turn/started", {"threadId": thread.thread_id, "turn": turn.wire(with_items=False)}))
        return fakes.Reply(result={"goal": answer}, after=notes)

    def _goal_get(self, params: dict[str, Any]) -> dict[str, Any]:
        # Reads the stored goal without loading the thread, so a notLoaded thread stays notLoaded (spec A-5, A-16).
        thread = self.thread_or_error(params["threadId"])
        goal = self.goal_get_answer(thread) if self.goal_get_answer is not None else thread.goal
        return {"goal": copy.deepcopy(goal)}

    def _thread_compact(self, params: dict[str, Any]) -> dict[str, Any]:
        # Compaction acts only on a thread loaded in this app-server (spec A-4).
        thread = self.thread_or_error(params["threadId"])
        if thread.status == "notLoaded":
            raise _fakes().FakeRpcError(-32600, f"thread not loaded: {thread.thread_id}")
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
        cwds = params["cwds"] if "cwds" in params else [_fakes().DEFAULT_CWD]
        return {"data": [{"cwd": cwd, "errors": [], "skills": copy.deepcopy(self.skills.get(cwd, []))} for cwd in cwds]}
