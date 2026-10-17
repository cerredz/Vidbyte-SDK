"""FILE: tests/features/agent_swarm/agent_swarm_fixtures.py

PURPOSE: Shared offline harness for the AgentSwarm feature pack: one scripted model runner that reaches every member agent the swarm builds inside arun, an on_event recorder that turns swarm state changes into Signals, blocking and raising search tools, settings builders under tmp_path, transcript readers, and the event oracle every run is checked against.
ROLE IN CODEBASE: Imported by every test module in tests/features/agent_swarm/. It replaces only the model runner, at BaseAgent._runner_for_model (spec section 13), so the agent loop, the middleware pipeline, the prompt catalog, the file tools, bash, the filesystem, asyncio, and the settings validation all run for real.
ARCHITECTURE NOTE: ScriptedSwarm routes each model call by agent name to that agent's list of steps (one continuous list across all its turns, because each member runs one loop for the whole swarm) or to a behaviour function, and records what the agent was sent. Becoming idle, waking, and failing happen inside the swarm, not on a model call, so tests wait for them through EventLog.signal(kind, agent), which the on_event callback sets (spec section 13, R-6). assert_event_invariants is the oracle: it replays result.events as a state machine and checks every invariant of spec section 6.1 that the event record can show.
FUNCTION INVENTORY: member / build_settings / build_swarm / workplace_path build the subject; tool_call / reply / finish / send / fail / observe / after build steps; Gate and Signal order concurrent agents without sleeps; ScriptedSwarm.install patches the runner and ScriptedSwarm.calls_by / first_call / last_call / position / assert_complete read what happened; EventLog records on_event deliveries and sets Signals; SearchTool and BlockingSearchTool are developer search tools; run_swarm and guard_asyncio_run turn a hang into a failure; yield_to_loop is a zero-delay scheduler yield; tool_results / tool_result / is_error / user_messages / message_tool_calls / seen_text / prompt_text / template_regex / renderings read rendered output; of_kind / only / seq_of read events; assert_event_invariants is the oracle; assert_no_stray_tasks and snapshot check what is left behind.
COMMON MODIFICATION PATTERNS: Add a step kind as a frozen dataclass plus one branch in ScriptedSwarm._respond. When the spec adds an event kind, add its allowed fields to _ALLOWED_FIELDS and its place in the lifecycle to assert_event_invariants.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte.agents.agent_swarm, vidbyte.lib.dataclasses.agent_swarm, vidbyte.lib.enums.agent_swarm, vidbyte.lib.constants.agent_swarm, vidbyte.tools.toolsets.agent_swarm, or the new Prompt members at module level: before the feature exists that would make every module in the pack a collection error. 2. Do not mock the loop, the middleware pipeline, the catalog, the file tools, or bash (spec section 13). 3. Do not wait on wall-clock time; Gate, Signal and the blocking tool use asyncio events, their timeout only turns a hang into a failure, and yield_to_loop sleeps for zero seconds. 4. Do not encode feature wording here; tests take prompt text from the catalog.
KNOWN EDGE CASES: The swarm contains exceptions raised by on_event, so an assertion inside an EventLog hook would only reach result.event_error_types; the oracle therefore checks event_error_types against the expected tuple. A runner that raises inside a member becomes AGENT_FAILED, so unscripted calls and guard failures are also kept in ScriptedSwarm.unscripted and ScriptedSwarm.problems, which assert_complete checks.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm/spec.md sections 6, 8.5, 9.1, 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import inspect
import itertools
import json
import re
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from vidbyte import BaseAgent
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmSettings
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmMember

MODEL = "gpt-4.1"
# The section 4 goal; every test that does not care about the goal's text uses it.
GOAL = "Build a Celsius-to-Fahrenheit command-line tool with tests."
# Each member's own system prompt, as in the section 4 snippet plus two more roles.
PROMPTS: Mapping[str, str] = {
    "builder": "You write the code.",
    "tester": "You write and run the tests.",
    "reviewer": "You review every change.",
    "docs": "You write the documentation.",
}
# A failure-only guard: a Gate, Signal or blocking tool that is never released fails the test after this long instead of hanging it.
GUARD_SECONDS = 20.0
# A failure-only guard around a whole arun: longer than GUARD_SECONDS so a stuck Signal reports first.
RUN_GUARD_SECONDS = 60.0
DEFAULT_USAGE: Mapping[str, int] = {"input_tokens": 3, "output_tokens": 2}
# The loop's own provisional answer to a refused isDone (vidbyte/agents/runtime.py, spec EC-5).
FINISH_NOT_ACCEPTED = "finish attempt not accepted yet; continue with the next message"
# A key-shaped string the provider-key matcher accepts as OpenAI's; never a real key.
FAKE_OPENAI_KEY = "sk-proj-SwarmFakeKey0000AAAA1111"

# Event kind values (spec section 8.5), as strings so this module never imports the feature at load time.
STARTED = "agent_started"
TOOL_CALLED = "tool_called"
SENT = "message_sent"
DELIVERED = "message_delivered"
IDLE = "agent_idle"
WOKE = "agent_woke"
FAILED = "agent_failed"
ENDED = "swarm_ended"

_CALL_IDS = itertools.count(1)
_FIELD = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


# ---------------------------------------------------------------- builders


def member(name: str, *, system_prompt: str | None = None, provider: str = "openai", model_name: str = MODEL) -> AgentSwarmMember:
    """One AgentSwarmMember; its own prompt defaults to PROMPTS[name] or a generic line."""
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember

    prompt = system_prompt if system_prompt is not None else PROMPTS.get(name, f"You are {name}; you help the swarm.")
    return AgentSwarmMember(name=name, system_prompt=prompt, provider=provider, model_name=model_name)


def workplace_path(tmp_path: Path) -> Path:
    """Where build_settings puts the shared folder unless a test names another."""
    return tmp_path / "workplace"


def build_settings(tmp_path: Path, names: Sequence[str] = ("builder", "tester"), **fields: Any) -> AgentSwarmSettings:
    """Valid settings for members `names` over workplace_path(tmp_path); `fields` override single values (including agents)."""
    from vidbyte.agents.agent_swarm import AgentSwarmSettings

    values: dict[str, Any] = {"agents": tuple(member(name) for name in names), "workplace": workplace_path(tmp_path), **fields}
    return AgentSwarmSettings(**values)


def build_swarm(tmp_path: Path, names: Sequence[str] = ("builder", "tester"), **fields: Any) -> AgentSwarm:
    """An AgentSwarm over build_settings(...)."""
    from vidbyte.agents.agent_swarm import AgentSwarm

    return AgentSwarm(build_settings(tmp_path, names, **fields))


# ---------------------------------------------------------------- scripted steps


@dataclass(frozen=True)
class ToolStep:
    name: str
    args: Mapping[str, Any]
    usage: Mapping[str, int]


@dataclass(frozen=True)
class ReplyStep:
    text: str
    usage: Mapping[str, int]


@dataclass(frozen=True)
class RaiseStep:
    error: BaseException


Step = ToolStep | ReplyStep | RaiseStep | Callable[["ModelCall"], Any]


def tool_call(name: str, args: Mapping[str, Any], usage: Mapping[str, int] | None = None) -> ToolStep:
    """The model asks for one tool call."""
    return ToolStep(name, dict(args), dict(usage or DEFAULT_USAGE))


def reply(text: str, usage: Mapping[str, int] | None = None) -> ReplyStep:
    """The model answers with text and no tool call: a plain turn end."""
    return ReplyStep(text, dict(usage or DEFAULT_USAGE))


def finish(text: str) -> ToolStep:
    """The model calls the loop's own isDone: the other way a turn ends."""
    return tool_call("isDone", {"final_answer": text})


def send(to: str, text: str) -> ToolStep:
    """The model calls the swarm's message tool."""
    return tool_call("message", {"to": to, "text": text})


def fail(error: BaseException) -> RaiseStep:
    """The runner raises `error` instead of answering."""
    return RaiseStep(error)


def observe(action: Callable[[ModelCall], object], then: Step) -> Callable[[ModelCall], Step]:
    """Runs `action(call)` when the call arrives (to read or change state at that moment), then answers `then`."""

    def step(call: ModelCall) -> Step:
        action(call)
        return then

    return step


def after(waitable: Gate | Signal, then: Step) -> Callable[[ModelCall], Any]:
    """Holds the call until `waitable` is released, then answers `then`."""

    async def step(call: ModelCall) -> Step:
        await waitable.wait(call.agent)
        return then

    return step


def provider_error(text: str = "openai returned 503: upstream overloaded") -> BaseException:
    """The provider error a model call raises in the failure tests (spec AC-7, R-1)."""
    from vidbyte.lib.errors import ProviderRequestError

    return ProviderRequestError(text, provider="openai", status_code=503)


async def yield_to_loop(times: int = 1) -> None:
    """Gives other ready tasks a turn: asyncio.sleep(0) is a zero-delay scheduler yield, never a timed wait."""
    for _ in range(times):
        await asyncio.sleep(0)


# ---------------------------------------------------------------- concurrency without sleeps


class Gate:
    """Releases every waiter once `parties` distinct waiters have arrived; fails after GUARD_SECONDS otherwise."""

    def __init__(self, parties: int) -> None:
        self.parties = parties
        self.arrived: list[str] = []
        self._open = asyncio.Event()

    async def wait(self, who: str) -> None:
        self.arrived.append(who)
        if len(self.arrived) >= self.parties:
            self._open.set()
        try:
            await asyncio.wait_for(self._open.wait(), GUARD_SECONDS)
        except TimeoutError as exc:
            raise AssertionError(f"gate never opened: only {self.arrived} of {self.parties} agents were active at once") from exc


class Signal:
    """A one-shot event; wait() fails after GUARD_SECONDS instead of hanging."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._event = asyncio.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self, who: str) -> None:
        try:
            await asyncio.wait_for(self._event.wait(), GUARD_SECONDS)
        except TimeoutError as exc:
            raise AssertionError(f"{who} waited for {self.label!r}, which never happened") from exc


# ---------------------------------------------------------------- the scripted swarm


@dataclass
class ModelCall:
    """What one agent sent on one model call."""

    agent: str
    prompt: str
    system: str
    messages: list[dict[str, Any]]
    tools: tuple[str, ...]
    tool_schemas: dict[str, Any] = field(default_factory=dict)
    tool_descriptions: dict[str, str] = field(default_factory=dict)


class _ScriptedRunner:
    def __init__(self, swarm: ScriptedSwarm, agent: str) -> None:
        self.swarm = swarm
        self.agent = agent

    async def arun(self, prompt: str, **options: Any) -> object:
        return await self.swarm.answer(self.agent, prompt, options)


Behaviour = Callable[["ModelCall"], Any]


class ScriptedSwarm:
    """One scripted runner per agent name, installed for every BaseAgent at once; an agent is answered by its script or its behaviour."""

    def __init__(self, scripts: Mapping[str, Sequence[Step]] | None = None, *, behaviours: Mapping[str, Behaviour] | None = None) -> None:
        self.scripts: dict[str, list[Step]] = {name: list(steps) for name, steps in (scripts or {}).items()}
        self.behaviours: dict[str, Behaviour] = dict(behaviours or {})
        self.cursor: dict[str, int] = {}
        self.calls: list[ModelCall] = []
        self.unscripted: list[ModelCall] = []
        self.problems: list[str] = []
        # Ordered "<agent> call <n>" / "<agent> answered <n>" marks, for before/after checks between agents.
        self.events: list[str] = []

    @contextmanager
    def install(self) -> Iterator[ScriptedSwarm]:
        swarm = self

        def runner_for(agent: BaseAgent) -> tuple[object, str]:
            return _ScriptedRunner(swarm, agent.name), RUNNER_TYPE_TEXT

        with patch.object(BaseAgent, "_runner_for_model", new=runner_for):
            yield self

    async def answer(self, agent: str, prompt: str, options: Mapping[str, Any]) -> object:
        call = self._record(agent, prompt, options)
        index = self.cursor.get(agent, 0)
        step: Any
        if agent in self.behaviours:
            step = self.behaviours[agent]
        else:
            steps = self.scripts.get(agent, [])
            if index >= len(steps):
                self.unscripted.append(call)
                raise AssertionError(f"unscripted model call #{index + 1} for agent {agent!r}")
            step = steps[index]
        self.cursor[agent] = index + 1
        self.events.append(f"{agent} call {index + 1}")
        try:
            # A callable step may return another callable step (after(...) around observe(...)), so resolve until data.
            while callable(step):
                step = step(call)
                if inspect.isawaitable(step):
                    step = await step
        except AssertionError as exc:
            self.problems.append(str(exc))
            raise
        response = self._respond(step)
        self.events.append(f"{agent} answered {index + 1}")
        return response

    def _record(self, agent: str, prompt: str, options: Mapping[str, Any]) -> ModelCall:
        schemas: dict[str, Any] = {}
        descriptions: dict[str, str] = {}
        names: list[str] = []
        for spec in options.get("tools") or ():
            function = spec.get("function", spec) if isinstance(spec, Mapping) else {}
            if isinstance(function, Mapping) and "name" in function:
                name = str(function["name"])
                names.append(name)
                schemas[name] = copy.deepcopy(function.get("parameters"))
                descriptions[name] = str(function.get("description") or "")
        call = ModelCall(
            agent=agent,
            prompt=str(prompt),
            system=str(options.get("system") or ""),
            messages=copy.deepcopy(list(options.get("messages") or [])),
            tools=tuple(names),
            tool_schemas=schemas,
            tool_descriptions=descriptions,
        )
        self.calls.append(call)
        return call

    @staticmethod
    def _respond(step: Any) -> object:
        if isinstance(step, RaiseStep):
            raise step.error
        if isinstance(step, ReplyStep):
            return TextModelResponse(provider=ModelProvider.OPENAI, model=MODEL, text=step.text, raw={}, usage=dict(step.usage))
        if isinstance(step, ToolStep):
            output = [{"type": "function_call", "name": step.name, "arguments": json.dumps(step.args), "call_id": f"call-{next(_CALL_IDS)}"}]
            return SimpleNamespace(text="", raw={"output": output}, provider=ModelProvider.OPENAI, model=MODEL, usage=dict(step.usage))
        raise AssertionError(f"not a scripted step: {step!r}")

    def calls_by(self, agent: str) -> list[ModelCall]:
        return [call for call in self.calls if call.agent == agent]

    def first_call(self, agent: str) -> ModelCall:
        calls = self.calls_by(agent)
        assert calls, f"agent {agent!r} was never called; called: {sorted({c.agent for c in self.calls})}"
        return calls[0]

    def last_call(self, agent: str) -> ModelCall:
        calls = self.calls_by(agent)
        assert calls, f"agent {agent!r} was never called"
        return calls[-1]

    def position(self, mark: str) -> int:
        assert mark in self.events, f"{mark!r} never happened; marks: {self.events}"
        return self.events.index(mark)

    def assert_complete(self) -> None:
        """No unscripted call, no guard failure, and every scripted step was used."""
        assert not self.unscripted, f"unexpected model calls: {[(c.agent, len(c.messages)) for c in self.unscripted]}"
        assert not self.problems, f"scripted steps failed: {self.problems}"
        left = {name: len(steps) - self.cursor.get(name, 0) for name, steps in self.scripts.items() if self.cursor.get(name, 0) < len(steps)}
        assert not left, f"scripted steps never used (agent -> steps left): {left}"


# ---------------------------------------------------------------- the on_event recorder


class CallbackBoom(Exception):
    """The exception an EventLog raises on purpose (spec AC-10)."""


Hook = Callable[["AgentSwarmEvent"], Any]


class EventLog:
    """An on_event callback (sync or async) that records every event it is handed, sets Signals on matching events, and tracks overlap."""

    def __init__(self, *, mode: str = "sync", raise_on: str | None = None, yields: int = 0) -> None:
        assert mode in ("sync", "async")
        self.mode = mode
        self.raise_on = raise_on
        self.yields = yields
        self.received: list[AgentSwarmEvent] = []
        self.active = 0
        self.max_active = 0
        self._watches: list[tuple[str, str, int, Signal]] = []
        self._hooks: list[Hook] = []

    @property
    def callback(self) -> Callable[[AgentSwarmEvent], Any]:
        """The callable to pass as on_event: a plain function or a coroutine function."""
        return self._on_async if self.mode == "async" else self._on_sync

    def signal(self, kind: str, agent: str, nth: int = 1) -> Signal:
        """A Signal set when the `nth` event of `kind` for `agent` is delivered to the callback."""
        signal = Signal(f"{kind} #{nth} for {agent or 'the swarm'}")
        self._watches.append((kind, agent, nth, signal))
        return signal

    def hook(self, action: Hook) -> None:
        """Runs `action(event)` on every delivered event (awaited in async mode when it returns an awaitable)."""
        self._hooks.append(action)

    def _note(self, event: AgentSwarmEvent) -> None:
        self.received.append(event)
        for kind, agent, nth, signal in self._watches:
            if event.kind.value == kind and event.agent == agent:
                seen = sum(1 for item in self.received if item.kind.value == kind and item.agent == agent)
                if seen == nth:
                    signal.set()

    def _on_sync(self, event: AgentSwarmEvent) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self._note(event)
            for action in self._hooks:
                action(event)
            if self.raise_on is not None and event.kind.value == self.raise_on:
                raise CallbackBoom(f"on_event refused {event.kind.value} #{event.sequence}")
        finally:
            self.active -= 1

    async def _on_async(self, event: AgentSwarmEvent) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self._note(event)
            for action in self._hooks:
                outcome = action(event)
                if inspect.isawaitable(outcome):
                    await outcome
            await yield_to_loop(self.yields)
            if self.raise_on is not None and event.kind.value == self.raise_on:
                raise CallbackBoom(f"on_event refused {event.kind.value} #{event.sequence}")
        finally:
            self.active -= 1


# ---------------------------------------------------------------- developer search tools


class SearchTool(BaseTool):
    """A developer search tool; `error` makes execute raise it (spec EC-16 (b))."""

    def __init__(self, name: str = "web_search", *, error: BaseException | None = None) -> None:
        # BaseTool.name is a read-only property over spec().name, so the name is kept privately and served by spec().
        self._tool_name = name
        self.error = error
        self.queries: list[str] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._tool_name,
            description="Search the public web and return short result snippets for a query.",
            permission=ToolPermission.READ,
            input_schema={"type": "object", "properties": {"query": {"type": "string", "description": "What to search for."}}, "required": ["query"]},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        self.queries.append(str(call.arguments.get("query", "")))
        if self.error is not None:
            raise self.error
        return ToolResult.success(self.name, f"results for {call.arguments.get('query')}")


class BlockingSearchTool(SearchTool):
    """A search tool whose execute sets `entered` and then holds until `release` is set, so an agent stays mid-turn."""

    def __init__(self, name: str = "web_search") -> None:
        super().__init__(name)
        self.entered = Signal(f"{name} entered")
        self.release = Signal(f"{name} released")
        self.problems: list[str] = []

    async def execute(self, call: ToolCall) -> ToolResult:
        self.queries.append(str(call.arguments.get("query", "")))
        self.entered.set()
        try:
            await self.release.wait(self.name)
        except AssertionError as exc:
            self.problems.append(str(exc))
            return ToolResult.error(self.name, str(exc))
        return ToolResult.success(self.name, f"results for {call.arguments.get('query')}")


# ---------------------------------------------------------------- hang guards


async def _bounded(awaitable: Awaitable[Any], what: str) -> Any:
    # Run the awaitable as its own task so its own exceptions (TimeoutError included) pass through unchanged, and only a real hang becomes an AssertionError.
    task = asyncio.ensure_future(awaitable)
    done, _ = await asyncio.wait({task}, timeout=RUN_GUARD_SECONDS)
    if not done:
        task.cancel()
        with contextlib.suppress(BaseException):
            await task
        raise AssertionError(f"{what} did not return within {RUN_GUARD_SECONDS} seconds: the swarm hung")
    return task.result()


async def run_swarm(runner: Any, goal: Any = GOAL) -> Any:
    """Awaits runner.arun(goal) (an AgentSwarm or an AgentSwarmRuntime) under RUN_GUARD_SECONDS."""
    return await _bounded(runner.arun(goal), "arun")


def guard_asyncio_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes asyncio.run bound its coroutine by RUN_GUARD_SECONDS, so the section 4 snippet cannot hang the session."""
    real_run = asyncio.run

    def guarded_run(main: Any, **kwargs: Any) -> Any:
        return real_run(_bounded(main, "asyncio.run(swarm.arun(...))"), **kwargs)

    monkeypatch.setattr(asyncio, "run", guarded_run)


def assert_no_stray_tasks() -> None:
    """No task but the current one is still pending: no member run was left waiting (spec INV-11, INV-12)."""
    current = asyncio.current_task()
    stray = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
    assert not stray, f"tasks still pending after arun returned: {stray}"


# ---------------------------------------------------------------- reading what agents saw


def tool_results(call: ModelCall) -> list[tuple[str, str]]:
    """Every (tool name, content) result in the call's history, oldest first."""
    return [(str(m.get("name", "")), str(m.get("content", ""))) for m in call.messages if m.get("role") == "tool"]


def tool_result(call: ModelCall, name: str) -> str:
    """The newest result of tool `name` in the call's history."""
    found = [content for tool, content in tool_results(call) if tool == name]
    assert found, f"no {name!r} result in {call.agent}'s history: {tool_results(call)}"
    return found[-1]


def is_error(content: str) -> bool:
    """True when a tool message carries ToolResult.error (the runtime's error envelope)."""
    return content.lstrip().startswith("[tool_error")


def user_messages(call: ModelCall) -> list[str]:
    """The content of every user message in the call's history, oldest first (the goal is the prompt, not a message)."""
    return [str(m.get("content", "")) for m in call.messages if m.get("role") == "user"]


def message_tool_calls(call: ModelCall) -> list[tuple[dict[str, Any], str]]:
    """Each `message` call in the history as (arguments, tool result content), in order."""
    results = {str(m.get("tool_call_id")): str(m.get("content", "")) for m in call.messages if m.get("role") == "tool"}
    found: list[tuple[dict[str, Any], str]] = []
    for item in call.messages:
        for requested in item.get("tool_calls") or ():
            function = requested.get("function", {})
            if function.get("name") == "message":
                found.append((json.loads(function.get("arguments") or "{}"), results.get(str(requested.get("id")), "")))
    return found


def seen_text(call: ModelCall) -> str:
    """Everything one model call carried: prompt, system string, and history."""
    return "\n".join((call.prompt, call.system, json.dumps(call.messages, ensure_ascii=False)))


def prompt_text(leaf: str) -> str:
    """The catalog text of agent_swarm.<leaf>, through Prompt.AGENT_SWARM_<LEAF>."""
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    return Prompts().get(Prompt[f"AGENT_SWARM_{leaf.upper()}"])


def template_regex(template: str, **known: object) -> re.Pattern[str]:
    """A regex for `template` rendered by str.format: literal text is exact, known fields are exact, other fields match anything."""
    text = template.strip()
    parts: list[str] = []
    position = 0
    for match in _FIELD.finditer(text):
        parts.append(re.escape(text[position : match.start()]))
        token = match.group(0)
        if token == "{{":
            parts.append(re.escape("{"))
        elif token == "}}":
            parts.append(re.escape("}"))
        else:
            name = re.split(r"[!:.\[]", match.group(1), maxsplit=1)[0]
            parts.append(re.escape(str(known[name])) if name in known else r"[\s\S]*?")
        position = match.end()
    parts.append(re.escape(text[position:]))
    return re.compile("".join(parts))


def renderings(template: str, text: str, **known: object) -> int:
    """How many non-empty, non-overlapping renderings of `template` appear in `text`."""
    return sum(1 for match in template_regex(template, **known).finditer(text) if match.group(0))


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file's bytes under `root`, keyed by POSIX relative path."""
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def error_text(error: BaseException) -> str:
    """The message plus any structured details, where an error may name its field."""
    return f"{error} {json.dumps(getattr(error, 'details', None), default=str)}"


# ---------------------------------------------------------------- reading events


def of_kind(events: Sequence[Any], kind: str, agent: str | None = None) -> list[Any]:
    """The events of `kind` (a value string), optionally for one agent, in order."""
    return [event for event in events if event.kind.value == kind and (agent is None or event.agent == agent)]


def only(events: Sequence[Any], kind: str, agent: str | None = None) -> Any:
    """The single event of `kind` for `agent`; fails when there is not exactly one."""
    found = of_kind(events, kind, agent)
    assert len(found) == 1, f"expected one {kind} for {agent!r}, found {[(e.sequence, e.agent, e.peer) for e in found]}"
    return found[0]


def seq_of(events: Sequence[Any], kind: str, agent: str | None = None, nth: int = 1) -> int:
    """The sequence number of the `nth` event of `kind` for `agent`."""
    found = of_kind(events, kind, agent)
    assert len(found) >= nth, f"no {kind} #{nth} for {agent!r}; events: {describe(events)}"
    return int(found[nth - 1].sequence)


def describe(events: Sequence[Any]) -> list[str]:
    """A compact, readable listing of events for assertion messages."""
    return [f"{e.sequence} {e.kind.value} {e.agent}{'->' + e.peer if e.peer else ''}" for e in events]


# ---------------------------------------------------------------- the oracle

_DEFAULTS: Mapping[str, Any] = {"peer": "", "message_id": 0, "text": "", "tool_name": "", "tool_status": None, "stop_reason": None}
# The fields each kind may set (spec section 9.1); every other field must keep its default.
_ALLOWED_FIELDS: Mapping[str, frozenset[str]] = {
    STARTED: frozenset(),
    TOOL_CALLED: frozenset({"tool_name", "tool_status"}),
    SENT: frozenset({"peer", "message_id", "text"}),
    DELIVERED: frozenset({"peer", "message_id"}),
    IDLE: frozenset({"text"}),
    WOKE: frozenset(),
    FAILED: frozenset({"text"}),
    ENDED: frozenset({"stop_reason"}),
}


def assert_event_invariants(result: Any, names: Sequence[str], *, max_turns: int, log: EventLog | None = None, error_types: Sequence[str] = ()) -> None:
    """Replays result.events as the spec's state machine and checks every invariant the record can show (spec 6.1, 9.1, NFR-1)."""
    events = list(result.events)
    stop = result.stop_reason.value
    trace = describe(events)

    # INV-13: numbered 1..N, one SWARM_ENDED, last, carrying the result's stop reason.
    assert [event.sequence for event in events] == list(range(1, len(events) + 1)), f"sequences are not 1..N: {trace}"
    ended = of_kind(events, ENDED)
    assert len(ended) == 1 and events[-1].kind.value == ENDED, f"SWARM_ENDED is not the one last event: {trace}"
    assert ended[0].agent == "" and ended[0].stop_reason is result.stop_reason, f"SWARM_ENDED {ended[0]!r} does not match {result.stop_reason!r}"
    # Section 4 and the run pseudocode: one AGENT_STARTED per member, in member order, before anything else.
    assert [(event.kind.value, event.agent) for event in events[: len(names)]] == [(STARTED, name) for name in names], f"runs do not start in member order: {trace}"

    previous_ms = 0
    for event in events:
        # Section 9.1: whole milliseconds, never decreasing; unlisted fields keep their defaults.
        assert type(event.elapsed_ms) is int and event.elapsed_ms >= previous_ms, f"elapsed_ms not a non-decreasing int at {event!r}"
        previous_ms = event.elapsed_ms
        allowed = _ALLOWED_FIELDS[event.kind.value]
        for name, default in _DEFAULTS.items():
            if name not in allowed:
                assert getattr(event, name) == default, f"{event.kind.value} #{event.sequence} sets {name}={getattr(event, name)!r}"
        if event.kind.value != ENDED:
            assert event.agent in names, f"event for a non-member: {event!r}"

    state: dict[str, str | None] = {name: None for name in names}
    pending: dict[str, list[int]] = {name: [] for name in names}
    sent: dict[int, Any] = {}
    delivered: set[int] = set()
    last_idle_text: dict[str, str] = {}
    turns = 0
    for index, event in enumerate(events[:-1]):
        kind, agent = event.kind.value, event.agent
        # INV-14: STARTED (IDLE WOKE)* [IDLE | FAILED]; work, sends and deliveries happen only while working; nothing after FAILED.
        if kind == STARTED:
            assert state[agent] is None, f"{agent} started twice: {trace}"
            state[agent] = "working"
            turns += 1
        elif kind == IDLE:
            assert state[agent] == "working", f"{agent} went idle while {state[agent]}: {trace}"
            state[agent] = "idle"
            last_idle_text[agent] = event.text
            # INV-7, AC-20: ending a turn with mail waiting and budget left continues at once.
            if pending[agent] and turns < max_turns:
                follower = events[index + 1]
                assert (follower.kind.value, follower.agent) == (WOKE, agent), f"{agent} went idle holding mail {pending[agent]} with turns left: {trace}"
        elif kind == WOKE:
            assert state[agent] == "idle", f"{agent} woke while {state[agent]}: {trace}"
            # INV-9: a wake never passes the turn budget.
            assert turns < max_turns, f"wake #{turns + 1} passes max_turns={max_turns}: {trace}"
            state[agent] = "working"
            turns += 1
        elif kind == FAILED:
            assert state[agent] == "working", f"{agent} failed while {state[agent]}: {trace}"
            assert event.text.strip(), f"AGENT_FAILED for {agent} names no cause"
            state[agent] = "failed"
        else:
            assert state[agent] == "working", f"{kind} for {agent} while {state[agent]}: {trace}"
        if kind == TOOL_CALLED:
            assert event.tool_name.strip() and event.tool_status is not None, f"TOOL_CALLED without name or status: {event!r}"
        if kind == SENT:
            # Section 9.1, INV-8: a send names another member that has not failed, carries its text, and its id is its own sequence.
            assert event.message_id == event.sequence, f"MESSAGE_SENT id {event.message_id} != sequence {event.sequence}"
            assert event.peer in names and event.peer != agent and event.text.strip(), f"bad MESSAGE_SENT {event!r}"
            assert state[event.peer] != "failed", f"a message to failed {event.peer} was accepted: {trace}"
            sent[event.sequence] = event
            pending[event.peer].append(event.sequence)
            # D-5, INV-7: a message to an idle agent with budget left wakes it in the same step.
            if state[event.peer] == "idle" and turns < max_turns:
                follower = events[index + 1]
                assert (follower.kind.value, follower.agent) == (WOKE, event.peer), f"message {event.sequence} to idle {event.peer} did not wake it: {trace}"
        if kind == DELIVERED:
            # INV-5, INV-14: delivered once, to its named recipient, after its send, in acceptance order.
            source = sent.get(event.message_id)
            assert source is not None, f"MESSAGE_DELIVERED #{event.sequence} names no earlier MESSAGE_SENT: {trace}"
            assert (source.agent, source.peer) == (event.peer, agent), f"delivery #{event.sequence} misrouted: {trace}"
            assert event.message_id not in delivered, f"message {event.message_id} delivered twice: {trace}"
            assert pending[agent] and pending[agent][0] == event.message_id, f"delivery to {agent} out of acceptance order: {trace}"
            delivered.add(event.message_id)
            pending[agent].pop(0)

    running = [name for name in names if state[name] != "failed"]
    undelivered = {name: pending[name] for name in running if pending[name]}
    if stop != "timeout":
        # INV-10, INV-11: the swarm ended because nobody was working; the reason follows from who failed and what is left.
        assert all(state[name] in ("idle", "failed") for name in names), f"a {stop} swarm ended with an agent still working: {state}"
        assert (stop == "failed") == (not running), f"stop reason {stop} but failed agents are {[n for n in names if state[n] == 'failed']}"
        if stop == "quiet":
            assert not undelivered, f"QUIET with undelivered messages {undelivered}: {trace}"
        if stop == "max_turns":
            assert undelivered, f"MAX_TURNS with no undelivered message: {trace}"
            assert turns == max_turns, f"MAX_TURNS after {turns} of {max_turns} turns: {trace}"
    if stop in ("quiet", "max_turns"):
        # FR-15: each released agent's last reply, in member order.
        assert [(item.sender, item.content) for item in result.replies] == [(name, last_idle_text[name]) for name in running], f"replies {result.replies!r} are not each running agent's last turn"
    else:
        assert tuple(result.replies) == (), f"{stop} must return no replies, got {result.replies!r}"
    assert tuple(result.event_error_types) == tuple(error_types), f"unexpected callback errors {result.event_error_types!r}"

    if log is not None:
        # INV-15: never two callbacks at once; every event exactly once in order, or a cut prefix plus SWARM_ENDED on TIMEOUT.
        assert log.max_active <= 1, f"on_event ran {log.max_active} times at once"
        if stop != "timeout":
            assert log.received == events, f"on_event saw {describe(log.received)}, the result holds {trace}"
        else:
            numbers = [event.sequence for event in log.received]
            assert numbers == sorted(set(numbers)) and log.received and log.received[-1] == events[-1], f"on_event on TIMEOUT saw {describe(log.received)}"
            assert all(seen == events[seen.sequence - 1] for seen in log.received), "on_event saw an event that differs from result.events"
