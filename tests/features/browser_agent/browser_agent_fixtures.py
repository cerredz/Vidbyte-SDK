"""FILE: tests/features/browser_agent/browser_agent_fixtures.py

PURPOSE: Shared offline harness for the BrowserAgent feature pack: one scripted model runner that answers the orchestrator, every episode worker, every recheck, and the done-when agent by name; a fake stdio MCP transport that plays the ACTION, SEARCH, and FETCH browser servers; builders for settings and agents; an event sink that records when each event arrived; and readers for the goal card, tool results, prompt templates, and history sizes.
ROLE IN CODEBASE: Imported by every test module in tests/features/browser_agent/. It replaces only the two seams spec section 13 allows: the model runner at BaseAgent._runner_for_model and the MCP stdio transport at vidbyte.tools.mcp.attach.McpStdioTransport. BaseAgent, the linear loop, BrowserAgentRuntime, the MCP mixin, attach, client and bridge, the compaction middleware and engine, ToolSettings, the prompt catalog, and the usage tracker all run for real.
ARCHITECTURE NOTE: ScriptedModel routes each model call by agent name (the orchestrator is NAME, workers are "<NAME>-episode-<n>", rechecks "<NAME>-recheck", the done-when agent "<NAME>-done-when") to that agent's list of steps and records what it was sent: prompt, system string, message history, offered tool names, schemas, and descriptions, plus the agent's configured model. A step is one or more tool calls, a final reply, an error to raise, a step that answers forever, or a callable that observes the call and then returns a step. A call with no step left is recorded as unscripted and fails, so an agent the feature must not run can never pass silently. FakeBrowserServers is a transport factory: every instance it builds is kept, with the command, env, and timeout it was built with and every tools/call it received.
FUNCTION INVENTORY: worker / action_server / search_server / fetch_server / build_settings / build_agent build the subject; tool_call / tool_calls / reply / card / verdict / criteria / fail / forever / observe build steps; ScriptedModel.install / calls_by / first_call / position / assert_complete run and read the script; FakeBrowserServers.install / instances_for / calls_to / serve / add read and shape the fake servers; text_result / image_result / error_result build MCP results; EventLog records events with the orchestrator call count at emit time; installed combines both seams; card_section / tool_results / tool_messages / assistant_turns / is_error / seen_text / prompt_text / template_regex / int_token / error_text / find_error / stored_tokens / content_tokens / unpaired read what happened.
COMMON MODIFICATION PATTERNS: Add a new step kind as a frozen dataclass plus one branch in ScriptedModel._respond. Add a fake server tool with FakeBrowserServers.add or replace a role's catalog with serve. Keep every helper free of feature imports at module level; import feature symbols inside the helper that needs them.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte.agents.browser, vidbyte.lib.constants.browser, vidbyte.lib.enums.browser, vidbyte.lib.dataclasses.browser, or the new Prompt members at module level: before the feature exists that would make every module in the pack a collection error and abort the whole session. 2. Do not mock BaseAgent, the loop, the MCP client or bridge, the compaction middleware, ToolSettings, or the usage tracker (spec section 13, real seams). 3. Do not wait on wall-clock time; ordering checks yield to the event loop with asyncio.sleep(0) only. 4. Do not encode feature logic (caps, wording) here; tests take bounds from the BROWSER_* constants and wording from the prompt catalog. 5. Never put a real key here; the keys below are fakes that exist only to be searched for.
KNOWN EDGE CASES: The fake replies report PRICED_MODEL, which equals MODEL, the section 4 snippet's model since spec r4 ("gpt-5.4-mini"): the agent's usage fails closed on an unpriced call (INV-21), so a reply that reported a model with no pricebook row (for example "gpt-4.1", the r1-r3 snippet model) would turn every run into UsageAccountingError. A runner that raises inside a worker may be turned into a stuck card by the episode tool, so unscripted calls are also kept in ScriptedModel.unscripted, which assert_complete checks. template_regex is only as strict as the literal text of the template it is given.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 4, 8.5, 9.1 and 13; tests/features/infinite_memory_agent/infinite_memory_fixtures.py (the prior art this copies).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q
"""

from __future__ import annotations

import copy
import inspect
import itertools
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from vidbyte import BaseAgent
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools.mcp import FirecrawlMCP, PlaywrightMCP

if TYPE_CHECKING:
    from vidbyte.agents.browser import BrowserAgent, BrowserAgentSettings, BrowserServerSettings

# The section 4 snippet's values; every derived agent name starts with NAME.
NAME = "vc-scout"
SYSTEM_PROMPT = "You find seed-stage accelerator programs and record where to apply."
TASK = "Find twenty seed-stage accelerator programs that accept applications this quarter."
MODEL = "gpt-5.4-mini"
# What every fake reply reports as its model: priced, so the agent's fail-closed usage settles (see KNOWN EDGE CASES).
PRICED_MODEL = "gpt-5.4-mini"
DONE_WHEN = ("Twenty programs are listed, each with its application URL and deadline.",)
# Fake keys that exist only so tests can search for them; neither is a real credential.
FIRECRAWL_KEY = "fc-test-only-7f3a9c2e51d84b06"
MODEL_KEY = "sk-test-BROWSER-SECRET-0123456789"
# The commands the fake servers are keyed by: the two presets' own commands, and one custom FETCH command.
ACTION_COMMAND: tuple[str, ...] = tuple(PlaywrightMCP.command)
SEARCH_COMMAND: tuple[str, ...] = tuple(FirecrawlMCP.command)
FETCH_COMMAND: tuple[str, ...] = ("fake-fetch-mcp", "--stdio")
# How the goal card item starts in every orchestrator system string (context manager primitive header, spec INV-14).
CARD_HEADER = "### [browser_goal_card]"
# The recheck and done-when agents' fixed names (spec section 13).
RECHECK = f"{NAME}-recheck"
DONE_WHEN_AGENT = f"{NAME}-done-when"
DEFAULT_USAGE: Mapping[str, int] = {"input_tokens": 3, "output_tokens": 2}
# The default fake browser tools, by role; tests that need other names replace them with FakeBrowserServers.serve.
ACTION_TOOLS = ("browser_navigate", "browser_click", "browser_type", "browser_snapshot", "browser_take_screenshot")
SEARCH_TOOLS = ("firecrawl_search",)
FETCH_TOOLS = ("fetch_markdown",)
# A base64 payload long enough to be unmistakable if it ever reached a model call.
SCREENSHOT_DATA = "iVBORw0KGgoAAAANSUhEUgAA" + "QUJDREVGR0hJSktMTU5PUFFSU1RVVldY" * 64

_CALL_IDS = itertools.count(1)
_FIELD = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


# ---------------------------------------------------------------- names and builders


def worker(index: int) -> str:
    """The BaseAgent name of the run's `index`-th episode worker (1-based)."""
    return f"{NAME}-episode-{index}"


def action_server(**fields: Any) -> BrowserServerSettings:
    """The section 4 ACTION server: the registered Playwright preset."""
    from vidbyte.agents.browser import BrowserServerSettings

    return BrowserServerSettings(PlaywrightMCP, **fields)


def search_server(**fields: Any) -> BrowserServerSettings:
    """The section 4 SEARCH server: the Firecrawl preset with its required key in env."""
    from vidbyte.agents.browser import BrowserServerSettings

    values: dict[str, Any] = {"env": {"FIRECRAWL_API_KEY": FIRECRAWL_KEY}, **fields}
    return BrowserServerSettings(FirecrawlMCP, **values)


def fetch_server(**fields: Any) -> BrowserServerSettings:
    """A custom FETCH server given by command."""
    from vidbyte.agents.browser import BrowserServerSettings

    return BrowserServerSettings(command=FETCH_COMMAND, **fields)


def build_settings(**fields: Any) -> BrowserAgentSettings:
    """Valid settings with one server per role and the snippet's done_when; `fields` override single values."""
    from vidbyte.agents.browser import BrowserAgentSettings

    values: dict[str, Any] = {
        "name": NAME,
        "system_prompt": SYSTEM_PROMPT,
        "provider": "openai",
        "model_name": MODEL,
        "action_servers": (action_server(),),
        "search_servers": (search_server(),),
        "fetch_servers": (fetch_server(),),
        "done_when": DONE_WHEN,
        **fields,
    }
    return BrowserAgentSettings(**values)


def build_agent(**fields: Any) -> BrowserAgent:
    """A BrowserAgent over build_settings(...)."""
    from vidbyte.agents.browser import BrowserAgent

    return BrowserAgent(build_settings(**fields))


# ---------------------------------------------------------------- scripted steps


@dataclass(frozen=True)
class ToolStep:
    calls: tuple[tuple[str, Mapping[str, Any]], ...]
    usage: Mapping[str, int]


@dataclass(frozen=True)
class ReplyStep:
    text: str
    usage: Mapping[str, int]
    model: str = PRICED_MODEL


@dataclass(frozen=True)
class RaiseStep:
    error: BaseException


@dataclass(frozen=True)
class ForeverStep:
    """Answers every remaining call of its agent with `step`; the cursor never moves past it."""

    step: Any


Step = ToolStep | ReplyStep | RaiseStep | ForeverStep | Callable[["ModelCall"], Any]


def tool_call(name: str, args: Mapping[str, Any], usage: Mapping[str, int] | None = None) -> ToolStep:
    """The model asks for one tool call."""
    return ToolStep(((name, dict(args)),), dict(usage or DEFAULT_USAGE))


def tool_calls(*calls: tuple[str, Mapping[str, Any]], usage: Mapping[str, int] | None = None) -> ToolStep:
    """The model asks for several tool calls in one turn, run in the given order."""
    return ToolStep(tuple((name, dict(args)) for name, args in calls), dict(usage or DEFAULT_USAGE))


def reply(text: str, usage: Mapping[str, int] | None = None, model: str = PRICED_MODEL) -> ReplyStep:
    """The model answers with final text and no tool call."""
    return ReplyStep(text, dict(usage or DEFAULT_USAGE), model)


def card(outcome: str, summary: str, *, facts: Sequence[str] = (), urls: Sequence[str] = (), evidence: Sequence[str] = (), usage: Mapping[str, int] | None = None) -> ReplyStep:
    """A worker's final reply in the BrowserEpisodePayload shape (spec section 8.5)."""
    payload = {"outcome": outcome, "summary": summary, "facts": list(facts), "urls": list(urls), "evidence": list(evidence)}
    return reply(json.dumps(payload), usage)


def verdict(value: str, gap: str = "", usage: Mapping[str, int] | None = None) -> ReplyStep:
    """A recheck's reply in the BrowserVerdictPayload shape."""
    return reply(json.dumps({"verdict": value, "gap": gap}), usage)


def criteria(*items: str, usage: Mapping[str, int] | None = None) -> ReplyStep:
    """The done-when agent's reply in the BrowserDoneWhenPayload shape."""
    return reply(json.dumps({"criteria": list(items)}), usage)


def fail(error: BaseException) -> RaiseStep:
    """The runner raises `error` instead of answering."""
    return RaiseStep(error)


def forever(step: Any) -> ForeverStep:
    """Every further call of this agent gets `step` (a worker that never stops asking, a recheck that never changes)."""
    return ForeverStep(step)


def observe(action: Callable[[ModelCall], object], then: Any) -> Callable[[ModelCall], Any]:
    """Runs `action(call)` when the call arrives, then answers `then`."""

    def step(call: ModelCall) -> Any:
        action(call)
        return then

    return step


# ---------------------------------------------------------------- the scripted model


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
    # The calling agent's configured model (runner_config.model_name).
    model: str = ""


class _ScriptedRunner:
    def __init__(self, model: ScriptedModel, agent: str, recorded_model: str = "") -> None:
        self.model = model
        self.agent = agent
        # Not named model_name: BaseAgent reads that attribute
        # off a runner.
        self.recorded_model = recorded_model

    async def arun(self, prompt: str, **options: Any) -> object:
        return await self.model.answer(self.agent, prompt, options, self.recorded_model)


class ScriptedModel:
    """One scripted runner per agent name, installed for every BaseAgent at once."""

    def __init__(self, scripts: Mapping[str, Sequence[Step]]) -> None:
        self.scripts: dict[str, list[Any]] = {name: list(steps) for name, steps in scripts.items()}
        self.cursor: dict[str, int] = {}
        self.calls: list[ModelCall] = []
        self.unscripted: list[ModelCall] = []
        self.forever_hits: dict[str, int] = {}
        # Ordered "<agent> call <n>" / "<agent> answered <n>" marks, for before/after checks between agents.
        self.events: list[str] = []

    @contextmanager
    def install(self) -> Iterator[ScriptedModel]:
        model = self

        def runner_for(agent: BaseAgent) -> tuple[object, str]:
            return _ScriptedRunner(model, agent.name, str(agent.runner_config.model_name or "")), RUNNER_TYPE_TEXT

        with patch.object(BaseAgent, "_runner_for_model", new=runner_for):
            yield self

    async def answer(self, agent: str, prompt: str, options: Mapping[str, Any], recorded_model: str = "") -> object:
        call = self._record(agent, prompt, options, recorded_model)
        steps = self.scripts.get(agent, [])
        index = self.cursor.get(agent, 0)
        number = len(self.calls_by(agent))
        if index >= len(steps):
            self.unscripted.append(call)
            raise AssertionError(f"unscripted model call #{number} for agent {agent!r}")
        step: Any = steps[index]
        if isinstance(step, ForeverStep):
            self.forever_hits[agent] = self.forever_hits.get(agent, 0) + 1
            step = step.step
        else:
            self.cursor[agent] = index + 1
        self.events.append(f"{agent} call {number}")
        # A callable step may return another callable step, so resolve until data.
        while callable(step):
            step = step(call)
            if inspect.isawaitable(step):
                step = await step
        response = self._respond(step)
        self.events.append(f"{agent} answered {number}")
        return response

    def _record(self, agent: str, prompt: str, options: Mapping[str, Any], recorded_model: str = "") -> ModelCall:
        schemas: dict[str, Any] = {}
        descriptions: dict[str, str] = {}
        for spec in options.get("tools") or ():
            function = spec.get("function", spec) if isinstance(spec, Mapping) else {}
            if isinstance(function, Mapping) and "name" in function:
                schemas[str(function["name"])] = copy.deepcopy(function.get("parameters"))
                descriptions[str(function["name"])] = str(function.get("description") or "")
        call = ModelCall(
            agent=agent,
            prompt=str(prompt),
            system=str(options.get("system") or ""),
            messages=copy.deepcopy(list(options.get("messages") or [])),
            tools=tuple(schemas),
            tool_schemas=schemas,
            tool_descriptions=descriptions,
            model=recorded_model,
        )
        self.calls.append(call)
        return call

    @staticmethod
    def _respond(step: Any) -> object:
        if isinstance(step, RaiseStep):
            raise step.error
        if isinstance(step, ReplyStep):
            return TextModelResponse(provider=ModelProvider.OPENAI, model=step.model, text=step.text, raw={}, usage=dict(step.usage))
        if isinstance(step, ToolStep):
            output = [{"type": "function_call", "name": name, "arguments": json.dumps(dict(args)), "call_id": f"call-{next(_CALL_IDS)}"} for name, args in step.calls]
            return SimpleNamespace(text="", raw={"output": output}, provider=ModelProvider.OPENAI, model=PRICED_MODEL, usage=dict(step.usage))
        raise AssertionError(f"not a scripted step: {step!r}")

    def calls_by(self, agent: str) -> list[ModelCall]:
        return [call for call in self.calls if call.agent == agent]

    def first_call(self, agent: str) -> ModelCall:
        calls = self.calls_by(agent)
        assert calls, f"agent {agent!r} was never called; called: {sorted(self.agents_called())}"
        return calls[0]

    def agents_called(self) -> set[str]:
        return {call.agent for call in self.calls}

    def position(self, mark: str) -> int:
        assert mark in self.events, f"{mark!r} never happened; events: {self.events}"
        return self.events.index(mark)

    def assert_complete(self) -> None:
        """No unscripted call, and every scripted step was used (a forever step counts once it was reached)."""
        assert not self.unscripted, f"unexpected model calls: {[(c.agent, c.prompt[:80]) for c in self.unscripted]}"
        left: dict[str, int] = {}
        for name, steps in self.scripts.items():
            remaining = steps[self.cursor.get(name, 0) :]
            if remaining and isinstance(remaining[0], ForeverStep) and self.forever_hits.get(name, 0) > 0:
                remaining = remaining[1:]
            if remaining:
                left[name] = len(remaining)
        assert not left, f"scripted steps never used (agent -> steps left): {left}"


# ---------------------------------------------------------------- the fake browser servers


Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def text_result(text: str) -> dict[str, Any]:
    """An MCP tools/call result holding one text block."""
    return {"content": [{"type": "text", "text": text}]}


def image_result(text: str, data: str = SCREENSHOT_DATA) -> dict[str, Any]:
    """A screenshot-like MCP result: a text block naming the saved file, then a base64 image block."""
    return {"content": [{"type": "text", "text": text}, {"type": "image", "mimeType": "image/png", "data": data}]}


def error_result(text: str) -> dict[str, Any]:
    """An MCP tools/call result the server marks as an error."""
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _default_profiles() -> dict[tuple[str, ...], dict[str, Handler]]:
    shots = itertools.count(1)
    action: dict[str, Handler] = {
        "browser_navigate": lambda args: text_result(f"Navigated to {args.get('url', 'about:blank')}"),
        "browser_click": lambda args: text_result(f"Clicked {args.get('element', 'element')}"),
        "browser_type": lambda args: text_result(f"Typed into {args.get('element', 'field')}"),
        "browser_snapshot": lambda args: text_result("- heading: Seed programs\n- link: Apply now"),
        "browser_take_screenshot": lambda args: image_result(f"Saved screenshot to C:/shots/page-{next(shots)}.png"),
    }
    search: dict[str, Handler] = {"firecrawl_search": lambda args: text_result(f"1. Seedcamp https://seedcamp.com (query: {args.get('query', '')})")}
    fetch: dict[str, Handler] = {"fetch_markdown": lambda args: text_result(f"# Page {args.get('url', '')}\nApplications close 30 November.")}
    return {ACTION_COMMAND: action, SEARCH_COMMAND: search, FETCH_COMMAND: fetch}


class FakeMcpTransport:
    """One fake stdio MCP server process: answers initialize, tools/list, and tools/call from its profile."""

    def __init__(self, world: FakeBrowserServers, command: tuple[str, ...], env: Mapping[str, str] | None, request_timeout: float) -> None:
        self.world = world
        self.command = command
        self.env = dict(env or {})
        self.request_timeout = request_timeout
        self.started = False
        self.closed = False
        self.methods: list[str] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def start(self) -> None:
        self.started = True

    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.methods.append(method)
        if self.closed:
            raise RuntimeError("fake MCP transport is closed")
        profile = self.world.profiles.get(self.command, {})
        if method == "initialize":
            return {"ok": True}
        if method == "tools/list":
            tools = [{"name": name, "description": f"Fake browser tool {name}.", "inputSchema": {"type": "object", "properties": {}}} for name in profile]
            return {"tools": tools}
        if method == "tools/call":
            name = str((params or {}).get("name", ""))
            arguments = dict((params or {}).get("arguments") or {})
            self.calls.append((name, arguments))
            self.world.log.append((self.command, name, arguments))
            handler = profile.get(name)
            if handler is None:
                return error_result(f"unknown tool {name}")
            return dict(handler(arguments))
        raise ValueError(f"unknown MCP method {method}")

    async def close(self) -> None:
        self.closed = True


class FakeBrowserServers:
    """Builds FakeMcpTransport instances in place of McpStdioTransport and keeps every one it built."""

    def __init__(self) -> None:
        self.profiles: dict[tuple[str, ...], dict[str, Handler]] = _default_profiles()
        self.instances: list[FakeMcpTransport] = []
        # Every tools/call any instance received, in order: (command, tool, arguments).
        self.log: list[tuple[tuple[str, ...], str, dict[str, Any]]] = []

    @contextmanager
    def install(self) -> Iterator[FakeBrowserServers]:
        with patch("vidbyte.tools.mcp.attach.McpStdioTransport", self._build):
            yield self

    def _build(self, command: Sequence[str], *, env: Mapping[str, str] | None = None, request_timeout: float = 30.0, **_: object) -> FakeMcpTransport:
        transport = FakeMcpTransport(self, tuple(command), env, request_timeout)
        self.instances.append(transport)
        return transport

    def serve(self, command: Sequence[str], tools: Mapping[str, Handler]) -> None:
        """Replace the whole catalog of the server started with `command`."""
        self.profiles[tuple(command)] = dict(tools)

    def add(self, command: Sequence[str], name: str, handler: Handler) -> None:
        """Add one tool to the server started with `command`."""
        self.profiles.setdefault(tuple(command), {})[name] = handler

    def instances_for(self, command: Sequence[str]) -> list[FakeMcpTransport]:
        return [transport for transport in self.instances if transport.command == tuple(command)]

    def calls_to(self, command: Sequence[str]) -> list[tuple[str, dict[str, Any]]]:
        return [(name, args) for cmd, name, args in self.log if cmd == tuple(command)]


@contextmanager
def installed(model: ScriptedModel, servers: FakeBrowserServers) -> Iterator[None]:
    """Both seams at once."""
    with ExitStack() as stack:
        stack.enter_context(model.install())
        stack.enter_context(servers.install())
        yield


# ---------------------------------------------------------------- events


class EventLog:
    """A sync on_event sink that records every event, and how many orchestrator calls had been made when it arrived."""

    def __init__(self, model: ScriptedModel | None = None, *, raise_on: str | None = None, error: type[BaseException] = ValueError) -> None:
        self.model = model
        self.raise_on = raise_on
        self.error = error
        self.events: list[Any] = []
        self.orchestrator_calls: list[int] = []

    def __call__(self, event: Any) -> None:
        self.events.append(event)
        self.orchestrator_calls.append(len(self.model.calls_by(NAME)) if self.model is not None else -1)
        if self.raise_on is not None and getattr(event.kind, "value", event.kind) == self.raise_on:
            raise self.error(f"sink refused {self.raise_on}")

    def kinds(self) -> list[str]:
        return [str(getattr(event.kind, "value", event.kind)) for event in self.events]

    def of(self, kind: str) -> list[Any]:
        return [event for event in self.events if getattr(event.kind, "value", event.kind) == kind]

    def calls_at(self, kind: str) -> list[int]:
        """The orchestrator call count at the moment each `kind` event arrived."""
        return [count for event, count in zip(self.events, self.orchestrator_calls, strict=True) if getattr(event.kind, "value", event.kind) == kind]


# ---------------------------------------------------------------- reading what agents saw


def card_section(system: str) -> str:
    """The goal card item's text inside a system string; fails unless it appears exactly once."""
    count = system.count(CARD_HEADER)
    assert count == 1, f"the goal card appears {count} times in the system string"
    rest = system[system.find(CARD_HEADER) :]
    following = re.search(r"\n### \[", rest[len(CARD_HEADER) :])
    return rest[: len(CARD_HEADER) + following.start()] if following else rest


def tool_messages(call: ModelCall) -> list[dict[str, Any]]:
    return [message for message in call.messages if message.get("role") == "tool"]


def tool_results(call: ModelCall) -> list[tuple[str, str]]:
    """Every (tool name, content) result in the call's history, oldest first."""
    return [(str(m.get("name", "")), str(m.get("content", ""))) for m in tool_messages(call)]


def assistant_turns(messages: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """The tool names each assistant call turn asked for, oldest first."""
    turns: list[list[str]] = []
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            turns.append([str(item["function"]["name"]) for item in message["tool_calls"]])
    return turns


def unpaired(messages: Sequence[Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    """(call ids with no result, result ids with no call) in a stored or outgoing history."""
    called = {str(item["id"]) for m in messages if m.get("role") == "assistant" for item in (m.get("tool_calls") or ())}
    answered = {str(m.get("tool_call_id")) for m in messages if m.get("role") == "tool"}
    return called - answered, answered - called


def is_error(content: str) -> bool:
    """True when a tool message carries ToolResult.error (the runtime's error envelope)."""
    return content.lstrip().startswith("[tool_error")


def seen_text(call: ModelCall) -> str:
    """Everything one model call carried: prompt, system string, history, and tool descriptions."""
    return "\n".join((call.prompt, call.system, json.dumps(call.messages, ensure_ascii=False), json.dumps(call.tool_descriptions, ensure_ascii=False)))


def prompt_text(leaf: str) -> str:
    """The catalog text of browser_agent.<leaf>, through Prompt.BROWSER_AGENT_<LEAF>."""
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    return Prompts().get(Prompt[f"BROWSER_AGENT_{leaf.upper()}"])


def distinctive_line(leaf: str, *others: str) -> str:
    """The longest placeholder-free line of browser_agent.<leaf> that no leaf in `others` contains, to find that leaf inside a composed system string."""
    rejected = [prompt_text(other) for other in others]
    lines = [line.strip() for line in prompt_text(leaf).splitlines() if line.strip() and "{" not in line]
    lines = [line for line in lines if not any(line in text for text in rejected)]
    assert lines, f"browser_agent.{leaf} has no line of its own"
    return max(lines, key=len)


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


def int_token(value: int) -> re.Pattern[str]:
    """`value` as a standalone number (not part of a longer number, word, or key)."""
    return re.compile(rf"(?<![\w-]){value}(?![\w-])")


def error_text(error: BaseException) -> str:
    """The message plus any structured details, where an error may name its field."""
    return f"{error} {json.dumps(getattr(error, 'details', None), default=str)}"


def find_error(error: BaseException, kind: type[BaseException]) -> BaseException | None:
    """`error` or the first exception of type `kind` in its cause/context chain (the run may wrap what the runtime raised)."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, kind):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def stored_tokens(messages: Sequence[Mapping[str, Any]]) -> int:
    """The orchestrator rebuild measure (INV-30): TokenEstimate.count of each message's JSON text, summed."""
    from vidbyte.lib.util import TokenEstimate

    return sum(TokenEstimate.count(json.dumps(dict(message))) for message in messages)


def content_tokens(messages: Sequence[Mapping[str, Any]]) -> int:
    """The AC-31 measure: TokenEstimate.count of each message's string content, summed."""
    from vidbyte.lib.util import TokenEstimate

    return sum(TokenEstimate.count(message["content"]) for message in messages if isinstance(message.get("content"), str))
