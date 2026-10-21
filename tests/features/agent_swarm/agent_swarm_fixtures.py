"""FILE: tests/features/agent_swarm/agent_swarm_fixtures.py

PURPOSE: Shared offline harness for the AgentSwarm feature pack: one scripted model runner that reaches every member agent the swarm builds inside arun (and the compaction side call), an on_event recorder that turns swarm state changes into Signals, a recording fake for the Tavily HTTP call, a one-shot model retry seam, settings builders under tmp_path, transcript readers, and the event oracle every run is checked against.
ROLE IN CODEBASE: Imported by every test module in tests/features/agent_swarm/. It replaces only the model runner, at BaseAgent._runner_for_model, and the Tavily client's HTTP search (docs/spec/agent-swarm-v2/spec.md section 13), so the agent loop, the middleware pipeline, the compaction engine, the prompt catalog, the file tools, bash, the filesystem, asyncio, and the settings validation all run for real.
ARCHITECTURE NOTE: ScriptedSwarm routes each model call by agent name to that agent's list of steps (one continuous list across all its turns and compaction side calls, because each member runs one loop for the whole swarm) or to a behaviour function, and records what the agent was sent. Each response is stamped with the member's own provider and model, so UsageTracker parses Anthropic usage with Anthropic's parser (spec section 13). Becoming idle, waking, and stopping happen inside the swarm, not on a model call, so tests wait for them through EventLog.signal(kind, agent), which the on_event callback sets. assert_event_invariants is the oracle: it replays result.events as the spec's state machine for all twenty-four kinds and checks every invariant of spec section 6.1 that the event record can show.
FUNCTION INVENTORY: member / build_settings / build_swarm / workplace_path build the subject; tool_call / calls / reply / finish / send / compact / search / fail / observe / after build steps; Gate and Signal order concurrent agents without sleeps; ScriptedSwarm.install patches the runner and ScriptedSwarm.calls_by / first_call / last_call / position / assert_complete read what happened; EventLog records on_event deliveries and sets Signals; FakeTavily stands in for the Tavily HTTP call; install_model_retry appends a one-shot retry middleware; run_swarm and guard_asyncio_run turn a hang into a failure; yield_to_loop is a zero-delay scheduler yield; tool_results / tool_result / is_error / user_messages / message_tool_calls / seen_text / prompt_text / template_regex / renderings read rendered output; of_kind / only / seq_of / pairs / describe read events; assert_event_invariants is the oracle; assert_no_stray_tasks and snapshot check what is left behind.
COMMON MODIFICATION PATTERNS: Add a step kind as a frozen dataclass plus one branch in ScriptedSwarm._respond. When the spec adds an event kind, add its constant, its allowed fields to _ALLOWED_FIELDS, and its place in the lifecycle to _Replay.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte.agents.agent_swarm, vidbyte.lib.dataclasses.agent_swarm, vidbyte.lib.enums.agent_swarm, vidbyte.lib.constants.agent_swarm, vidbyte.tools.toolsets.agent_swarm, vidbyte.middleware.builtins.agent_swarm_observer, or the new Prompt members at module level: before the feature exists that would make every module in the pack a collection error. 2. Do not mock the loop, the middleware pipeline, the compaction engine, the catalog, AgentSwarmEvents, the file tools, or bash (spec section 13). 3. Do not wait on wall-clock time; Gate, Signal and FakeTavily use asyncio events, their timeout only turns a hang into a failure, and yield_to_loop sleeps for zero seconds. 4. Do not encode feature wording here; tests take prompt text from the catalog.
KNOWN EDGE CASES: The swarm contains exceptions raised by on_event, so an assertion inside an EventLog hook would only reach result.event_error_types; the oracle therefore checks event_error_types against the expected tuple. A runner that raises inside a member becomes agent_failed, so unscripted calls and guard failures are also kept in ScriptedSwarm.unscripted and ScriptedSwarm.problems, which assert_complete checks. Two member tasks cancelled by the time limit record their agent_cancelled events in the task group's order, which is a set's order, so tests compare that window as a set.
RELATED DOCS: tests/features/agent_swarm/FEATURE.md; docs/spec/agent-swarm-v2/spec.md sections 6, 8.5, 9.1 and 13.
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
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.middleware.base import AgentMiddleware

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm import AgentSwarm, AgentSwarmSettings
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent, AgentSwarmMember

MODEL = "gpt-4.1"
ANTHROPIC_MODEL = "claude-sonnet-5"
# The section 4 goal; every test that does not care about the goal's text uses it.
GOAL = "Build a Celsius-to-Fahrenheit command-line tool with tests."
# A failure-only guard: a Gate, Signal or blocking fake that is never released fails the test after this long instead of hanging it.
GUARD_SECONDS = 20.0
# A failure-only guard around a whole arun: longer than GUARD_SECONDS so a stuck Signal reports first.
RUN_GUARD_SECONDS = 60.0
DEFAULT_USAGE: Mapping[str, int] = {"input_tokens": 3, "output_tokens": 2}
# The loop's own provisional answer to a refused isDone (vidbyte/agents/runtime.py).
FINISH_NOT_ACCEPTED = "finish attempt not accepted yet; continue with the next message"
# Key-shaped strings the provider-key matcher accepts as OpenAI's and Anthropic's, and a Tavily-shaped key; never real keys.
FAKE_OPENAI_KEY = "sk-proj-SwarmFakeKey0000AAAA1111"
FAKE_ANTHROPIC_KEY = "sk-ant-SwarmFakeKey0000AAAA1111"
FAKE_TAVILY_KEY = "tvly-SwarmFakeKey0000AAAA1111"
TAVILY_TOOL = "tavily_search"
# INV-1: the nine section leaves in their fixed order; the web-search section only when web_search is set.
SECTION_LEAVES = ("system_environment", "system_tools", "system_web_search", "system_messaging", "system_turns", "system_goal", "system_instructions", "system_objective", "system_thoroughness")

# Event kind values (spec section 8.5), as strings so this module never imports the feature at load time.
STARTED = "agent_started"
TOOL_CALLED = "tool_called"
SENT = "message_sent"
DELIVERED = "message_delivered"
IDLE = "agent_idle"
WOKE = "agent_woke"
FAILED = "agent_failed"
ENDED = "swarm_ended"
PREPARED = "workplace_prepared"
CREATED = "agent_created"
REFUSED = "message_refused"
WAKE_REFUSED = "wake_refused"
UNDELIVERED = "message_undelivered"
STOPPING = "swarm_stopping"
RELEASED = "agent_released"
CANCELLED = "agent_cancelled"
EXITED = "agent_exited"
MODEL_CALLED = "model_called"
MODEL_ERROR = "model_error"
TRIMMED = "history_trimmed"
TRUNCATED = "tool_result_truncated"
FILE_CHANGED = "file_changed"
COMMAND_FAILED = "command_failed"
COMPACTION = "compaction"
ALL_KINDS = (
    STARTED, TOOL_CALLED, SENT, DELIVERED, IDLE, WOKE, FAILED, ENDED, PREPARED, CREATED, REFUSED, WAKE_REFUSED,
    UNDELIVERED, STOPPING, RELEASED, CANCELLED, EXITED, MODEL_CALLED, MODEL_ERROR, TRIMMED, TRUNCATED, FILE_CHANGED,
    COMMAND_FAILED, COMPACTION,
)
TERMINAL_KINDS = frozenset({RELEASED, CANCELLED, FAILED, EXITED})

_CALL_IDS = itertools.count(1)
_FIELD = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


# ---------------------------------------------------------------- builders


def member(name: str, *, provider: str = "openai", model_name: str = MODEL) -> AgentSwarmMember:
    """One AgentSwarmMember: a name, a provider and a model, and no prompt of its own (spec FR-1)."""
    from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmMember

    return AgentSwarmMember(name=name, provider=provider, model_name=model_name)


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


def web_search_fields() -> dict[str, Any]:
    """The settings fields that select Tavily with a fake key."""
    return {"web_search": "tavily", "web_search_api_key": FAKE_TAVILY_KEY}


# ---------------------------------------------------------------- scripted steps


@dataclass(frozen=True)
class ToolStep:
    name: str
    args: Mapping[str, Any]
    usage: Mapping[str, int]


@dataclass(frozen=True)
class MultiToolStep:
    steps: tuple[ToolStep, ...]
    usage: Mapping[str, int]


@dataclass(frozen=True)
class ReplyStep:
    text: str
    usage: Mapping[str, int]


@dataclass(frozen=True)
class RaiseStep:
    error: BaseException


Step = ToolStep | MultiToolStep | ReplyStep | RaiseStep | Callable[["ModelCall"], Any]


def tool_call(name: str, args: Mapping[str, Any], usage: Mapping[str, int] | None = None) -> ToolStep:
    """The model asks for one tool call."""
    return ToolStep(name, dict(args), dict(DEFAULT_USAGE if usage is None else usage))


def calls(*steps: ToolStep, usage: Mapping[str, int] | None = None) -> MultiToolStep:
    """The model asks for several tool calls in one response; the loop runs them in order (spec EC-4, EC-22)."""
    return MultiToolStep(tuple(steps), dict(DEFAULT_USAGE if usage is None else usage))


def reply(text: str, usage: Mapping[str, int] | None = None) -> ReplyStep:
    """The model answers with text and no tool call: a plain turn end, or a compaction summary."""
    return ReplyStep(text, dict(DEFAULT_USAGE if usage is None else usage))


def finish(text: str) -> ToolStep:
    """The model calls the loop's own isDone: the other way a turn ends."""
    return tool_call("isDone", {"final_answer": text})


def send(to: object, text: object, usage: Mapping[str, int] | None = None) -> ToolStep:
    """The model calls the swarm's message tool."""
    return tool_call("message", {"to": to, "text": text}, usage)


def compact(focus: str | None = None, usage: Mapping[str, int] | None = None) -> ToolStep:
    """The model calls the swarm's compact tool, with or without a focus."""
    return tool_call("compact", {} if focus is None else {"focus": focus}, usage)


def search(query: str) -> ToolStep:
    """The model calls the Tavily search tool."""
    return tool_call(TAVILY_TOOL, {"query": query})


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
    """The provider error a model call raises in the failure tests."""
    from vidbyte.lib.errors import ProviderRequestError

    return ProviderRequestError(text, provider="openai", status_code=503)


def error_line(error: BaseException) -> str:
    """The "<ExceptionType>: <message>" text model_error and agent_failed carry (spec INV-23)."""
    return f"{type(error).__name__}: {error}"


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
    """What one agent sent on one model call (a compaction side call included)."""

    agent: str
    prompt: str
    system: str
    messages: list[dict[str, Any]]
    tools: tuple[str, ...]
    tool_schemas: dict[str, Any] = field(default_factory=dict)
    tool_descriptions: dict[str, str] = field(default_factory=dict)


class _ScriptedRunner:
    def __init__(self, swarm: ScriptedSwarm, agent: str, provider: ModelProvider, model: str) -> None:
        self.swarm = swarm
        self.agent = agent
        self.provider = provider
        self.model = model

    async def arun(self, prompt: str, **options: Any) -> object:
        return await self.swarm.answer(self.agent, prompt, options, self.provider, self.model)


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
            # Stamp the member's own provider and model on every response (spec section 13: the one fixture change S2 owns).
            config = agent.runner_config
            provider = ModelProvider(str(getattr(config.provider, "value", config.provider)))
            return _ScriptedRunner(swarm, agent.name, provider, str(config.model_name)), RUNNER_TYPE_TEXT

        with patch.object(BaseAgent, "_runner_for_model", new=runner_for):
            yield self

    async def answer(self, agent: str, prompt: str, options: Mapping[str, Any], provider: ModelProvider, model: str) -> object:
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
        response = self._respond(step, provider, model)
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
                schemas[name] = copy.deepcopy(function.get("parameters", function.get("input_schema")))
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
    def _respond(step: Any, provider: ModelProvider, model: str) -> object:
        if isinstance(step, RaiseStep):
            raise step.error
        if isinstance(step, ReplyStep):
            return TextModelResponse(provider=provider, model=model, text=step.text, raw={}, usage=dict(step.usage))
        if isinstance(step, ToolStep | MultiToolStep):
            steps = step.steps if isinstance(step, MultiToolStep) else (step,)
            if provider is ModelProvider.ANTHROPIC:
                content = [{"type": "tool_use", "id": f"toolu_{next(_CALL_IDS)}", "name": item.name, "input": dict(item.args)} for item in steps]
                raw: dict[str, Any] = {"content": content, "stop_reason": "tool_use"}
            else:
                raw = {"output": [{"type": "function_call", "name": item.name, "arguments": json.dumps(item.args), "call_id": f"call-{next(_CALL_IDS)}"} for item in steps]}
            return SimpleNamespace(text="", raw=raw, provider=provider, model=model, usage=dict(step.usage))
        raise AssertionError(f"not a scripted step: {step!r}")

    def calls_by(self, agent: str) -> list[ModelCall]:
        return [call for call in self.calls if call.agent == agent]

    def first_call(self, agent: str) -> ModelCall:
        found = self.calls_by(agent)
        assert found, f"agent {agent!r} was never called; called: {sorted({c.agent for c in self.calls})}"
        return found[0]

    def last_call(self, agent: str) -> ModelCall:
        found = self.calls_by(agent)
        assert found, f"agent {agent!r} was never called"
        return found[-1]

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
    """The exception an EventLog raises on purpose."""


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


# ---------------------------------------------------------------- the web-search boundary and the retry seam


class FakeTavily:
    """Stands in for the Tavily HTTP call (TavilyClient.search): records each query and the key its client holds, then answers, blocks until released, or raises."""

    def __init__(self, *, block: bool = False, error: BaseException | None = None) -> None:
        self.block = block
        self.error = error
        self.queries: list[str] = []
        self.keys: list[str] = []
        self.entered = Signal(f"{TAVILY_TOOL} entered")
        self.release = Signal(f"{TAVILY_TOOL} released")
        self.problems: list[str] = []

    @contextmanager
    def install(self) -> Iterator[FakeTavily]:
        from vidbyte.tools.builtins.operations.clients.tavily import TavilyClient

        fake = self

        async def fake_search(client: Any, query: str, *, max_results: int = 5, search_depth: str = "basic") -> object:
            return await fake.answer(client, query)

        with patch.object(TavilyClient, "search", new=fake_search):
            yield self

    async def answer(self, client: Any, query: str) -> object:
        from vidbyte.lib.dataclasses.operations import SearchHit, SearchPayload

        self.queries.append(query)
        self.keys.append(str(getattr(client, "_api_key", "")))
        self.entered.set()
        if self.block:
            try:
                await self.release.wait(TAVILY_TOOL)
            except AssertionError as exc:
                self.problems.append(str(exc))
        if self.error is not None:
            raise self.error
        hit = SearchHit(title="Celsius to Fahrenheit", url="https://example.com/c2f", snippet=f"notes on {query}")
        return SearchPayload(provider=str(client.provider), query=query, hits=(hit,), attempts=1, billable_units=1)


class RetryModelErrorOnce(AgentMiddleware):
    """Retries each agent's first failed model attempt at once: the loop's own retry seam, which the member agent does not install (spec AC-10)."""

    def __init__(self, retried: list[str]) -> None:
        self.retried = retried

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if ctx.agent_name in self.retried:
            return MiddlewareDecision.continue_()
        self.retried.append(ctx.agent_name)
        return MiddlewareDecision.retry("agent swarm test retry")


def install_model_retry(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Appends RetryModelErrorOnce after every agent's own middleware (so the swarm observer sees each error first); returns the agents it retried."""
    retried: list[str] = []
    original = BaseAgent._runtime_middleware

    def runtime_middleware(agent: BaseAgent) -> tuple[AgentMiddleware, ...]:
        return (*original(agent), RetryModelErrorOnce(retried))

    monkeypatch.setattr(BaseAgent, "_runtime_middleware", runtime_middleware)
    return retried


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
    """No task but the current one is still pending: no member run was left waiting."""
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


def shared_system_prompt(name: str, names: Sequence[str], workplace: Path, *, search_tool: str | None = None) -> str:
    """The system prompt INV-1 says member `name` receives before the loop prompt: the section leaves joined by one blank line, rendered with its name, its peers, the workplace and the search tool name."""
    sections = [leaf for leaf in SECTION_LEAVES if search_tool is not None or leaf != "system_web_search"]
    values = {"name": name, "peers": ", ".join(other for other in names if other != name), "workplace": str(workplace), "search_tool": search_tool or ""}
    return "\n\n".join(prompt_text(leaf).strip().format(**values) for leaf in sections)


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


def renderings(template: str, haystack: str, /, **known: object) -> int:
    """How many non-empty, non-overlapping renderings of `template` appear in `haystack`; positional-only so a template field named `text` can go in `known`."""
    return sum(1 for match in template_regex(template, **known).finditer(haystack) if match.group(0))


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


def pairs(events: Sequence[Any]) -> list[tuple[str, str]]:
    """Each event as (kind value, agent), in order: the shape exact event-list assertions compare."""
    return [(event.kind.value, event.agent) for event in events]


def start_pairs(names: Sequence[str]) -> list[tuple[str, str]]:
    """The fixed start of every run (spec INV-17, AC-2): workplace_prepared, agent_created per member, agent_started per member."""
    return [(PREPARED, ""), *((CREATED, name) for name in names), *((STARTED, name) for name in names)]


def describe(events: Sequence[Any]) -> list[str]:
    """A compact, readable listing of events for assertion messages."""
    return [f"{e.sequence} {e.kind.value} {e.agent}{'->' + e.peer if e.peer else ''}{' #' + str(e.message_id) if e.message_id else ''}" for e in events]


# ---------------------------------------------------------------- the oracle

_DEFAULTS: Mapping[str, Any] = {
    "peer": "", "message_id": 0, "text": "", "tool_name": "", "tool_status": None, "stop_reason": None,
    "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "model_calls": 0, "messages_dropped": 0, "omitted_chars": 0,
    "path": "", "compaction_trigger": None, "agent_state": None, "folder_state": None,
}
# The fields each kind may set (spec section 8.5, _KIND_FIELDS); every other field must keep its default.
_ALLOWED_FIELDS: Mapping[str, frozenset[str]] = {
    STARTED: frozenset(),
    TOOL_CALLED: frozenset({"tool_name", "tool_status"}),
    SENT: frozenset({"peer", "message_id", "text"}),
    DELIVERED: frozenset({"peer", "message_id"}),
    IDLE: frozenset({"text"}),
    WOKE: frozenset(),
    FAILED: frozenset({"text"}),
    ENDED: frozenset({"stop_reason"}),
    PREPARED: frozenset({"path", "folder_state"}),
    CREATED: frozenset(),
    REFUSED: frozenset({"peer", "text"}),
    WAKE_REFUSED: frozenset({"peer", "message_id"}),
    UNDELIVERED: frozenset({"peer", "message_id"}),
    STOPPING: frozenset({"stop_reason"}),
    RELEASED: frozenset(),
    CANCELLED: frozenset({"agent_state"}),
    EXITED: frozenset({"text"}),
    MODEL_CALLED: frozenset({"input_tokens", "output_tokens", "cached_tokens", "model_calls"}),
    MODEL_ERROR: frozenset({"text"}),
    TRIMMED: frozenset({"messages_dropped"}),
    TRUNCATED: frozenset({"tool_name", "omitted_chars"}),
    FILE_CHANGED: frozenset({"path", "peer"}),
    COMMAND_FAILED: frozenset({"text"}),
    COMPACTION: frozenset({"compaction_trigger", "text", "input_tokens", "messages_dropped"}),
}
_SWARM_KINDS = frozenset({PREPARED, STOPPING, ENDED})
_DERIVED = frozenset({TRUNCATED, FILE_CHANGED, COMMAND_FAILED})
# Kinds an agent records only while it is working: inside a turn, between a model call and its turn end.
_WORKING_ONLY = frozenset({TOOL_CALLED, SENT, REFUSED, DELIVERED, MODEL_CALLED, MODEL_ERROR, TRIMMED, TRUNCATED, FILE_CHANGED, COMMAND_FAILED, COMPACTION})
_COMMAND_FAILED_TEXT = re.compile(r"(exit code -?\d+|timeout)")


class _Replay:
    """The per-agent and per-message state machine of spec sections 6.1 and 9.1, fed one event at a time."""

    def __init__(self, events: Sequence[Any], names: Sequence[str], max_turns: int) -> None:
        self.events = events
        self.names = list(names)
        self.max_turns = max_turns
        self.trace = describe(events)
        self.state: dict[str, str | None] = {name: None for name in names}
        self.terminal: dict[str, str] = {}
        self.pending: dict[str, list[int]] = {name: [] for name in names}
        self.sent: dict[int, Any] = {}
        self.resolved: set[int] = set()
        self.wake_refused: set[int] = set()
        self.last_idle_text: dict[str, str] = {}
        self.last_base: dict[str, Any] = {}
        self.model_calls: dict[str, int] = {}
        self.writers: dict[str, str] = {}
        self.turns = 0
        self.stopping_at: int | None = None
        self.undelivered_at_stop: list[int] = []

    def next_ids(self, index: int, count: int) -> list[tuple[str, str, int]]:
        return [(e.kind.value, e.agent, e.message_id) for e in self.events[index + 1 : index + 1 + count]]

    def step(self, index: int, event: Any, stop: str) -> None:
        kind, agent = event.kind.value, event.agent
        follower = self.events[index + 1]
        stopped = self.stopping_at is not None
        if kind == PREPARED:
            return
        if kind == STOPPING:
            self.stop_block(index, stop)
            return
        if agent in self.terminal:
            # INV-14: after its terminal event only a late message to it, marked undelivered, may name it.
            assert kind == UNDELIVERED, f"{kind} for {agent} after its {self.terminal[agent]}: {self.trace}"
        if kind in _WORKING_ONLY:
            assert self.state[agent] == "working", f"{kind} for {agent} while {self.state[agent]}: {self.trace}"
        # A compaction is checked against the side call's model_called before it, so it never becomes a base itself.
        if kind not in _DERIVED | {COMPACTION} and kind != UNDELIVERED:
            self.last_base[agent] = event
        if kind == CREATED:
            assert self.state[agent] is None, f"{agent} created twice: {self.trace}"
            self.state[agent] = "created"
        elif kind == STARTED:
            assert self.state[agent] == "created", f"{agent} started while {self.state[agent]}: {self.trace}"
            self.state[agent] = "working"
            self.turns += 1
        elif kind == IDLE:
            self.idle(index, event, stopped, follower)
        elif kind == WOKE:
            # INV-9, INV-13: a wake never passes the turn budget and never follows the stop.
            assert not stopped and self.state[agent] == "idle", f"{agent} woke while {self.state[agent]} (stopped={stopped}): {self.trace}"
            assert self.turns < self.max_turns, f"wake #{self.turns + 1} passes max_turns={self.max_turns}: {self.trace}"
            self.state[agent] = "working"
            self.turns += 1
        elif kind == WAKE_REFUSED:
            mid = event.message_id
            assert not stopped and self.state[agent] == "idle" and self.turns >= self.max_turns, f"wake_refused #{event.sequence} out of place: {self.trace}"
            assert mid in self.pending[agent] and mid not in self.wake_refused and self.sent[mid].agent == event.peer, f"wake_refused #{event.sequence} names no waiting message: {self.trace}"
            self.wake_refused.add(mid)
        elif kind == SENT:
            self.sent_message(index, event, stopped, follower)
        elif kind == DELIVERED:
            source = self.sent.get(event.message_id)
            assert not stopped and source is not None and (source.agent, source.peer) == (event.peer, agent), f"delivery #{event.sequence} misrouted or after the stop: {self.trace}"
            assert event.message_id not in self.resolved and self.pending[agent][:1] == [event.message_id], f"delivery #{event.sequence} repeated or out of acceptance order: {self.trace}"
            self.pending[agent].pop(0)
            self.resolved.add(event.message_id)
        elif kind == UNDELIVERED:
            source = self.sent.get(event.message_id)
            assert source is not None and (source.agent, source.peer) == (event.peer, agent), f"undelivered #{event.sequence} misrouted: {self.trace}"
            assert event.message_id not in self.resolved and event.message_id in self.pending[agent], f"message {event.message_id} resolved twice: {self.trace}"
            self.pending[agent].remove(event.message_id)
            self.resolved.add(event.message_id)
        elif kind in TERMINAL_KINDS:
            self.end(index, event, stopped)
        else:
            self.observation(event)

    def idle(self, index: int, event: Any, stopped: bool, follower: Any) -> None:
        agent = event.agent
        assert self.state[agent] == "working", f"{agent} went idle while {self.state[agent]}: {self.trace}"
        self.state[agent] = "idle"
        self.last_idle_text[agent] = event.text
        if stopped or not self.pending[agent]:
            return
        # INV-9, INV-10: a turn end with mail wakes at once with budget left, else refuses one wake per waiting message.
        if self.turns < self.max_turns:
            assert (follower.kind.value, follower.agent) == (WOKE, agent), f"{agent} went idle holding mail {self.pending[agent]} with turns left: {self.trace}"
        else:
            waiting = [mid for mid in self.pending[agent] if mid not in self.wake_refused]
            assert self.next_ids(index, len(waiting)) == [(WAKE_REFUSED, agent, mid) for mid in waiting], f"{agent}'s turn end did not refuse each waiting wake: {self.trace}"

    def sent_message(self, index: int, event: Any, stopped: bool, follower: Any) -> None:
        # INV-6, D-4: any member is a valid recipient, the sender included; the id is the event's own sequence.
        recipient = event.peer
        assert event.message_id == event.sequence and recipient in self.names and event.text.strip(), f"bad message_sent {event!r}"
        self.sent[event.sequence] = event
        self.pending[recipient].append(event.sequence)
        if stopped or self.terminal.get(recipient) in (FAILED, EXITED):
            assert (follower.kind.value, follower.agent, follower.message_id) == (UNDELIVERED, recipient, event.sequence), f"message {event.sequence} to a stopped {recipient} was not marked undelivered at once: {self.trace}"
        elif self.state[recipient] == "idle":
            expected = WOKE if self.turns < self.max_turns else WAKE_REFUSED
            assert (follower.kind.value, follower.agent) == (expected, recipient), f"message {event.sequence} to idle {recipient} was not followed by {expected}: {self.trace}"

    def end(self, index: int, event: Any, stopped: bool) -> None:
        kind, agent = event.kind.value, event.agent
        assert agent not in self.terminal, f"{agent} has two terminal events: {self.trace}"
        assert self.state[agent] in ("working", "idle"), f"{kind} for {agent} while {self.state[agent]}: {self.trace}"
        if kind == RELEASED:
            assert stopped, f"{agent} released before swarm_stopping: {self.trace}"
        if kind == EXITED:
            assert not stopped and self.state[agent] == "working" and event.text.strip(), f"bad agent_exited {event!r}: {self.trace}"
        if kind == FAILED:
            assert event.text.strip(), f"agent_failed for {agent} names no cause"
        self.terminal[agent] = kind
        if kind in (FAILED, EXITED):
            # INV-14: a failed or exited agent's inbox is marked undelivered in the same block.
            expected = [(UNDELIVERED, agent, mid) for mid in self.pending[agent]]
            assert self.next_ids(index, len(expected)) == expected, f"{agent}'s inbox was not marked undelivered with its {kind}: {self.trace}"

    def stop_block(self, index: int, stop: str) -> None:
        assert self.stopping_at is None, f"two swarm_stopping events: {self.trace}"
        self.stopping_at = index
        everyone_out = all(self.terminal.get(name) in (FAILED, EXITED) for name in self.names)
        if stop in ("quiet", "max_turns", "failed"):
            # INV-12: these reasons are decided only when nobody is working; FAILED exactly when everyone failed or exited.
            assert all(self.state[name] != "working" or name in self.terminal for name in self.names), f"{stop} decided while an agent works: {self.trace}"
            assert (stop == "failed") == everyone_out, f"stop reason {stop} but terminals are {self.terminal}: {self.trace}"
        if stop == "max_tokens":
            assert self.events[index - 1].kind.value == MODEL_CALLED, f"max_tokens not decided in the model_called block: {self.trace}"
        if stop == "timeout":
            assert set(self.terminal) == set(self.names), f"timeout decided before every agent ended: {self.trace}"
        # INV-12: the same block marks every still-queued message undelivered, in member order.
        expected = [(UNDELIVERED, name, mid) for name in self.names for mid in self.pending[name]]
        assert self.next_ids(index, len(expected)) == expected, f"swarm_stopping did not mark the queued messages undelivered: {self.trace}"
        self.undelivered_at_stop = [mid for _, _, mid in expected]

    def observation(self, event: Any) -> None:
        kind, agent = event.kind.value, event.agent
        base = self.last_base.get(agent)
        if kind == TOOL_CALLED:
            assert event.tool_name.strip() and event.tool_status is not None, f"tool_called without name or status: {event!r}"
        elif kind == REFUSED:
            assert event.text.strip(), f"message_refused without a reason: {event!r}"
        elif kind == MODEL_CALLED:
            assert event.model_calls >= max(1, self.model_calls.get(agent, 0)), f"model_calls went down for {agent}: {self.trace}"
            self.model_calls[agent] = event.model_calls
        elif kind == MODEL_ERROR:
            assert ": " in event.text, f"model_error text is not '<Type>: <message>': {event!r}"
        elif kind == COMPACTION:
            assert base is not None and base.kind.value == MODEL_CALLED and event.compaction_trigger is not None, f"compaction #{event.sequence} without its side call: {self.trace}"
        elif kind in _DERIVED:
            # INV-25..27: a derived event follows its agent's own tool_called for the matching tool.
            assert base is not None and base.kind.value == TOOL_CALLED, f"{kind} #{event.sequence} without its tool_called: {self.trace}"
            self.derived(event, base)

    def derived(self, event: Any, base: Any) -> None:
        kind, agent = event.kind.value, event.agent
        if kind == TRUNCATED:
            assert event.tool_name == base.tool_name and event.omitted_chars > 0, f"bad tool_result_truncated {event!r}"
        elif kind == COMMAND_FAILED:
            assert base.tool_name == "bash" and _COMMAND_FAILED_TEXT.fullmatch(event.text), f"bad command_failed {event!r}"
        else:
            assert base.tool_name in ("write_text", "patch_file") and base.tool_status.value == "success", f"file_changed after {base!r}"
            assert Path(event.path).is_absolute(), f"file_changed path is not absolute: {event!r}"
            previous = self.writers.get(event.path, "")
            assert event.peer == (previous if previous != agent else ""), f"file_changed #{event.sequence} names peer {event.peer!r}, previous writer {previous!r}"
            self.writers[event.path] = agent


def assert_event_invariants(result: Any, names: Sequence[str], *, max_turns: int, log: EventLog | None = None, error_types: Sequence[str] = ()) -> None:
    """Replays result.events as the spec's state machine and checks every invariant the record can show (spec 6.1, 8.5, 9.1)."""
    events = list(result.events)
    stop = result.stop_reason.value
    trace = describe(events)

    # INV-16: numbered 1..N; one swarm_stopping before the one last swarm_ended, both carrying the result's stop reason.
    assert [event.sequence for event in events] == list(range(1, len(events) + 1)), f"sequences are not 1..N: {trace}"
    ended, stopping = of_kind(events, ENDED), of_kind(events, STOPPING)
    assert len(ended) == 1 and events[-1].kind.value == ENDED, f"swarm_ended is not the one last event: {trace}"
    assert len(stopping) == 1 and stopping[0].sequence < ended[0].sequence, f"not exactly one swarm_stopping before swarm_ended: {trace}"
    assert ended[0].stop_reason is result.stop_reason and stopping[0].stop_reason is result.stop_reason, f"stop reasons differ from {result.stop_reason!r}: {trace}"
    # INV-17, INV-28: workplace_prepared, then agent_created per member, then agent_started per member.
    assert pairs(events[: 1 + 2 * len(names)]) == start_pairs(names), f"the run does not start with the workplace and the members in order: {trace}"
    assert Path(events[0].path).is_absolute() and events[0].folder_state is not None, f"bad workplace_prepared {events[0]!r}"

    previous_ms = 0
    for event in events:
        # Section 9.1, INV-21: whole milliseconds, never decreasing; unlisted fields keep their defaults; agent blank only for swarm kinds.
        assert type(event.elapsed_ms) is int and event.elapsed_ms >= previous_ms, f"elapsed_ms not a non-decreasing int at {event!r}"
        previous_ms = event.elapsed_ms
        allowed = _ALLOWED_FIELDS[event.kind.value]
        for name, default in _DEFAULTS.items():
            if name not in allowed:
                assert getattr(event, name) == default, f"{event.kind.value} #{event.sequence} sets {name}={getattr(event, name)!r}"
        if event.kind.value in _SWARM_KINDS:
            assert event.agent == "", f"{event.kind.value} names agent {event.agent!r}"
        else:
            assert event.agent in names, f"event for a non-member: {event!r}"

    replay = _Replay(events, names, max_turns)
    for index, event in enumerate(events[:-1]):
        replay.step(index, event, stop)

    # INV-7, INV-14: every message has its one outcome and every agent its one ending.
    assert set(replay.sent) == replay.resolved, f"messages without an outcome {sorted(set(replay.sent) - replay.resolved)}: {trace}"
    assert set(replay.terminal) == set(names), f"agents without a terminal event {sorted(set(names) - set(replay.terminal))}: {trace}"
    if stop == "quiet":
        assert not replay.undelivered_at_stop, f"QUIET with undelivered messages {replay.undelivered_at_stop}: {trace}"
    if stop == "max_turns":
        # INV-10, EC-5: the budget is spent and every message left at the stop had its one refused wake.
        assert replay.turns == max_turns and replay.undelivered_at_stop, f"MAX_TURNS after {replay.turns} of {max_turns} turns: {trace}"
        assert set(replay.undelivered_at_stop) <= replay.wake_refused, f"MAX_TURNS left messages whose wake was never refused: {trace}"
    if stop == "timeout":
        assert not of_kind(events, RELEASED), f"TIMEOUT released an agent: {trace}"

    # INV-14: replies are the released agents' replies in member order; on QUIET and MAX_TURNS each is the agent's last turn.
    released = [name for name in names if replay.terminal[name] == RELEASED]
    assert [item.sender for item in result.replies] == released, f"replies {result.replies!r} are not the released agents {released}"
    if stop in ("quiet", "max_turns"):
        assert [item.content for item in result.replies] == [replay.last_idle_text[name] for name in released], f"replies {result.replies!r} are not each released agent's last turn"
    assert tuple(result.event_error_types) == tuple(error_types), f"unexpected callback errors {result.event_error_types!r}"

    if log is not None:
        # INV-20: never two callbacks at once; every event exactly once in order, or a cut prefix plus swarm_ended on TIMEOUT.
        assert log.max_active <= 1, f"on_event ran {log.max_active} times at once"
        if stop != "timeout":
            assert log.received == events, f"on_event saw {describe(log.received)}, the result holds {trace}"
        else:
            numbers = [event.sequence for event in log.received]
            assert numbers == sorted(set(numbers)) and log.received and log.received[-1] == events[-1], f"on_event on TIMEOUT saw {describe(log.received)}"
            assert all(seen == events[seen.sequence - 1] for seen in log.received), "on_event saw an event that differs from result.events"
