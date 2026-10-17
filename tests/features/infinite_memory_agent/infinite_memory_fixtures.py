"""FILE: tests/features/infinite_memory_agent/infinite_memory_fixtures.py

PURPOSE: Shared offline harness for the InfiniteMemory agent feature pack: one scripted model runner that reaches every agent in the delegation tree, builders for settings and agents under tmp_path, and readers for the workspace, the journal, and prompt templates.
ROLE IN CODEBASE: Imported by every test module in tests/features/infinite_memory_agent/. It replaces only the model runner, at BaseAgent._runner_for_model (spec section 13), so InfiniteWorkspace, InfiniteRunJournal, ParallelPipeline, the prompt catalog, the filesystem, and bash all run for real.
ARCHITECTURE NOTE: ScriptedTree routes each model call by agent name (the root is "analyst"; a root-level pair "a" is "analyst/root/a/gen" and "analyst/root/a/ver") to that agent's list of steps and records what the agent was sent: prompt, system string, message history, and offered tools. A step is a tool call, a final reply, an error to raise, or a callable that observes the call (or waits on a Gate or Signal) and then returns one of those. A call with no step left is recorded as unscripted and fails, so an agent the feature must not run can never pass silently.
FUNCTION INVENTORY: generator / verifier / pair_key name agents and keys; build_settings / build_agent / workspace_root / project_dir build the subject under tmp_path; tool_call / reply / fail / observe / after build steps; task / launch / simple_pair build launch_subagent arguments and one-call pairs; ScriptedTree.install patches the runner, ScriptedTree.calls_by / first_call / agents_called / position / assert_complete read what happened; Gate and Signal order concurrent agents without sleeps; read_jsonl / write_jsonl / entry_record / journal_paths / journal_records / events / finished_cards / write_journal / run_started_record / pair_started_record / pair_finished_record / run_finished_record / card_record read and write the section 9.1 shapes; prompt_text / template_regex / renderings / int_token / map_section / tool_results / tool_result / is_error / seen_text read rendered output; snapshot captures workspace bytes.
COMMON MODIFICATION PATTERNS: Add a new step kind as a frozen dataclass plus one branch in ScriptedTree._respond. Keep every helper free of feature imports at module level; import feature symbols inside the helper that needs them.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte.agents.infinite, vidbyte.lib.constants.infinite, vidbyte.lib.enums.infinite, or the new Prompt members at module level: before the feature exists that would make every module in the pack a collection error and abort the whole test session. 2. Do not mock the workspace, the journal, the pipeline, the catalog, or bash (spec section 13). 3. Do not wait on wall-clock time; Gate and Signal use asyncio events, and their timeout only turns a hang into a failure. 4. Do not encode feature logic (caps, wording) here; tests take literal values from the spec or templates from the prompt catalog.
KNOWN EDGE CASES: A runner that raises inside a child agent may be turned into a tool error by the parent, so unscripted calls and guard timeouts are also kept in ScriptedTree.unscripted and ScriptedTree.problems, which assert_complete checks. template_regex is only as strict as the literal text of the template it is given; a template made only of placeholders matches almost anything.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 8.5, 9.1, 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import itertools
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from vidbyte import BaseAgent
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse

if TYPE_CHECKING:
    from vidbyte.agents.infinite import InfiniteMemoryAgent, InfiniteMemoryAgentSettings

# The root agent's name, as in the spec's section 4 snippet; every child name starts with it.
ROOT = "analyst"
SYSTEM_PROMPT = "You research markets and report sourced findings."
TASK = "Compare the list prices of our five competitors."
MODEL = "gpt-4.1"
# How the workspace map appears in every system string (spec section 13), spelled out so a renamed id is caught.
MAP_HEADER = "### [infinite_memory_map] Workspace map"
# A failure-only guard: a Gate or Signal that is never released fails the test after this long instead of hanging it.
GUARD_SECONDS = 20.0
# Fixed, well-formed run ids and stamps for hand-written journals and bookkeeping lines (spec section 9.1).
RUN_A = "20261015T024900Z-1a2b3c4d"
RUN_B = "20261016T081500Z-5e6f7a8b"
AT = "2026-10-15T02:51:07Z"
DEFAULT_USAGE: Mapping[str, int] = {"input_tokens": 3, "output_tokens": 2}

_CALL_IDS = itertools.count(1)
_FIELD = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


# ---------------------------------------------------------------- names and builders


def generator(name: str, parent: str = f"{ROOT}/root") -> str:
    """The BaseAgent name of pair `name`'s generator under `parent` (the root by default)."""
    return f"{parent}/{name}/gen"


def verifier(name: str, parent: str = f"{ROOT}/root") -> str:
    """The BaseAgent name of pair `name`'s verifier under `parent` (the root by default)."""
    return f"{parent}/{name}/ver"


def pair_key(name: str) -> str:
    """The journal key of a root-level pair."""
    return f"root/{name}"


def project_dir(tmp_path: Path) -> Path:
    """The developer's project folder (root_dir) under tmp_path, created on first use."""
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return project


def workspace_root(tmp_path: Path) -> Path:
    """Where build_settings puts the memory workspace."""
    return project_dir(tmp_path) / "memory"


def build_settings(tmp_path: Path, *, workspace: Mapping[str, Any] | None = None, **fields: Any) -> InfiniteMemoryAgentSettings:
    """Valid settings rooted in tmp_path; `workspace` and `fields` override single values."""
    from vidbyte.agents.infinite import InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings

    workspace_fields: dict[str, Any] = {"root": workspace_root(tmp_path), **dict(workspace or {})}
    agent_fields: dict[str, Any] = {
        "name": ROOT,
        "system_prompt": SYSTEM_PROMPT,
        "provider": "openai",
        "model_name": MODEL,
        "root_dir": project_dir(tmp_path),
        "workspace": InfiniteWorkspaceSettings(**workspace_fields),
        **fields,
    }
    return InfiniteMemoryAgentSettings(**agent_fields)


def build_agent(tmp_path: Path, *, workspace: Mapping[str, Any] | None = None, **fields: Any) -> InfiniteMemoryAgent:
    """An InfiniteMemoryAgent over build_settings(...)."""
    from vidbyte.agents.infinite import InfiniteMemoryAgent

    return InfiniteMemoryAgent(build_settings(tmp_path, workspace=workspace, **fields))


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
    """The model answers with final text and no tool call."""
    return ReplyStep(text, dict(usage or DEFAULT_USAGE))


def fail(error: BaseException) -> RaiseStep:
    """The runner raises `error` instead of answering."""
    return RaiseStep(error)


def observe(action: Callable[[ModelCall], object], then: Step) -> Callable[[ModelCall], Step]:
    """Runs `action(call)` when the call arrives (to read or change the disk at that moment), then answers `then`."""

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


def task(
    name: str,
    *,
    goal: str | None = None,
    criteria: Sequence[str] = ("Every price has a source URL",),
    gen: str | None = None,
    ver: str | None = None,
    context: Sequence[str] | None = None,
    tools: Sequence[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """One launch_subagent task card in the section 9.2 shape; `extra` adds fields as given."""
    card: dict[str, Any] = {
        "name": name,
        "goal": goal if goal is not None else f"Find the list prices for {name}.",
        "done_criteria": list(criteria),
        "generator_prompt": gen if gen is not None else f"Research {name} and report the prices you found.",
        "verifier_prompt": ver if ver is not None else f"Check every {name} price against its source.",
    }
    if context is not None:
        card["context"] = list(context)
    if tools is not None:
        card["tools"] = list(tools)
    card.update(extra)
    return card


def launch(*cards: Mapping[str, Any]) -> ToolStep:
    """A launch_subagent call carrying `cards` in order."""
    return tool_call("launch_subagent", {"tasks": [dict(card) for card in cards]})


PASSED_REVIEW = "Checked every criterion against its source.\nVERDICT: passed"


def simple_pair(name: str, summary: str, review: str = PASSED_REVIEW, parent: str = f"{ROOT}/root") -> dict[str, list[Step]]:
    """Scripts for a pair whose generator answers `summary` and whose verifier answers `review`, one call each."""
    return {generator(name, parent): [reply(summary)], verifier(name, parent): [reply(review)]}


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


# ---------------------------------------------------------------- the scripted tree


@dataclass
class ModelCall:
    """What one agent sent on one model call."""

    agent: str
    prompt: str
    system: str
    messages: list[dict[str, Any]]
    tools: tuple[str, ...]
    tool_schemas: dict[str, Any] = field(default_factory=dict)


class _ScriptedRunner:
    def __init__(self, tree: ScriptedTree, agent: str) -> None:
        self.tree = tree
        self.agent = agent

    async def arun(self, prompt: str, **options: Any) -> object:
        return await self.tree.answer(self.agent, prompt, options)


class ScriptedTree:
    """One scripted runner per agent name, installed for every BaseAgent at once."""

    def __init__(self, scripts: Mapping[str, Sequence[Step]]) -> None:
        self.scripts: dict[str, list[Step]] = {name: list(steps) for name, steps in scripts.items()}
        self.cursor: dict[str, int] = {}
        self.calls: list[ModelCall] = []
        self.unscripted: list[ModelCall] = []
        self.problems: list[str] = []
        # Ordered "<agent> call <n>" / "<agent> answered <n>" marks, for before/after checks between agents.
        self.events: list[str] = []

    @contextmanager
    def install(self) -> Iterator[ScriptedTree]:
        tree = self

        def runner_for(agent: BaseAgent) -> tuple[object, str]:
            return _ScriptedRunner(tree, agent.name), RUNNER_TYPE_TEXT

        with patch.object(BaseAgent, "_runner_for_model", new=runner_for):
            yield self

    async def answer(self, agent: str, prompt: str, options: Mapping[str, Any]) -> object:
        call = self._record(agent, prompt, options)
        steps = self.scripts.get(agent, [])
        index = self.cursor.get(agent, 0)
        if index >= len(steps):
            self.unscripted.append(call)
            raise AssertionError(f"unscripted model call #{index + 1} for agent {agent!r}")
        self.cursor[agent] = index + 1
        self.events.append(f"{agent} call {index + 1}")
        step: Any = steps[index]
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
        for spec in options.get("tools") or ():
            function = spec.get("function", spec) if isinstance(spec, Mapping) else {}
            if isinstance(function, Mapping) and "name" in function:
                schemas[str(function["name"])] = copy.deepcopy(function.get("parameters"))
        call = ModelCall(
            agent=agent,
            prompt=str(prompt),
            system=str(options.get("system") or ""),
            messages=copy.deepcopy(list(options.get("messages") or [])),
            tools=tuple(schemas),
            tool_schemas=schemas,
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
        assert calls, f"agent {agent!r} was never called; called: {sorted(self.agents_called())}"
        return calls[0]

    def agents_called(self) -> set[str]:
        return {call.agent for call in self.calls}

    def position(self, mark: str) -> int:
        assert mark in self.events, f"{mark!r} never happened; events: {self.events}"
        return self.events.index(mark)

    def assert_complete(self) -> None:
        """No unscripted call, no guard failure, and every scripted step was used."""
        assert not self.unscripted, f"unexpected model calls: {[(c.agent, c.prompt[:80]) for c in self.unscripted]}"
        assert not self.problems, f"scripted steps failed: {self.problems}"
        left = {name: len(steps) - self.cursor.get(name, 0) for name, steps in self.scripts.items() if self.cursor.get(name, 0) < len(steps)}
        assert not left, f"scripted steps never used (agent -> steps left): {left}"


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


def seen_text(call: ModelCall) -> str:
    """Everything one model call carried: prompt, system string, and history."""
    return "\n".join((call.prompt, call.system, json.dumps(call.messages, ensure_ascii=False)))


def map_section(system: str) -> str:
    """The workspace map item's text inside a system string."""
    start = system.find(MAP_HEADER)
    assert start >= 0, f"no {MAP_HEADER!r} in the system string"
    rest = system[start + len(MAP_HEADER) :]
    following = re.search(r"\n### \[", rest)
    return rest[: following.start()] if following else rest


def prompt_text(leaf: str) -> str:
    """The catalog text of infinite_memory.<leaf>, through Prompt.INFINITE_MEMORY_<LEAF>."""
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    return Prompts().get(Prompt[f"INFINITE_MEMORY_{leaf.upper()}"])


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


def renderings(template: str, text: str) -> int:
    """How many non-empty, non-overlapping renderings of `template` appear in `text`."""
    return sum(1 for match in template_regex(template).finditer(text) if match.group(0))


def int_token(value: int) -> re.Pattern[str]:
    """`value` as a standalone number (not part of a longer number, word, or key)."""
    return re.compile(rf"(?<![\w-]){value}(?![\w-])")


# ---------------------------------------------------------------- disk shapes (spec section 9.1)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Every non-blank line of a JSON-lines file, parsed."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    """Writes one JSON object per line, each ending with a newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(dict(record)) + "\n" for record in records), encoding="utf-8", newline="\n")


def entry_record(
    entry_id: int,
    text: str,
    *,
    kind: str = "fact",
    tags: Sequence[str] = (),
    refs: Sequence[str] = (),
    supersedes: int | None = None,
    by: str = "root",
    verified_by: str | None = None,
    run: str = RUN_A,
    at: str = AT,
) -> dict[str, Any]:
    """One entries.jsonl line in the section 9.1 shape."""
    return {"id": entry_id, "kind": kind, "text": text, "tags": list(tags), "refs": list(refs), "supersedes": supersedes, "by": by, "verified_by": verified_by, "run": run, "at": at}


def snapshot(root: Path, *, include_runs: bool = False) -> dict[str, bytes]:
    """Every file's bytes under `root`, keyed by POSIX relative path; `.runs/` is left out unless asked."""
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and (include_runs or not relative.startswith(".runs/")):
            files[relative] = path.read_bytes()
    return files


def journal_paths(root: Path) -> list[Path]:
    """Every journal file under `<root>/.runs/`, sorted by name."""
    runs = root / ".runs"
    return sorted(runs.glob("*.jsonl")) if runs.is_dir() else []


def journal_records(root: Path) -> list[dict[str, Any]]:
    """The records of the one journal under `root`; fails when there is not exactly one."""
    paths = journal_paths(root)
    assert len(paths) == 1, f"expected one journal, found {[p.name for p in paths]}"
    return read_jsonl(paths[0])


def events(records: Sequence[Mapping[str, Any]]) -> list[str]:
    """The `event` value of each journal record, in order."""
    return [str(record.get("event")) for record in records]


def finished_cards(root: Path) -> dict[str, dict[str, Any]]:
    """The card of every pair_finished record in the one journal, by pair key."""
    return {str(record["key"]): dict(record["card"]) for record in journal_records(root) if record.get("event") == "pair_finished"}


def run_started_record(run_id: str, task_text: str, at: str = AT) -> dict[str, Any]:
    return {"event": "run_started", "at": at, "run": run_id, "task": task_text}


def pair_started_record(key: str, at: str = AT) -> dict[str, Any]:
    return {"event": "pair_started", "at": at, "key": key}


def card_record(
    name: str,
    *,
    key: str | None = None,
    status: str = "done",
    verdict: str = "passed",
    summary: str = "",
    review: str = "",
    entries: Sequence[int] = (),
    dropped: Sequence[str] = (),
    files: Sequence[str] = (),
) -> dict[str, Any]:
    """An InfiniteResultCard as a pair_finished record carries it (enum values as strings, sequences as lists)."""
    return {
        "name": name,
        "key": key if key is not None else pair_key(name),
        "status": status,
        "verdict": verdict,
        "summary": summary,
        "review": review,
        "entries": list(entries),
        "dropped": list(dropped),
        "files": list(files),
    }


def pair_finished_record(card: Mapping[str, Any], at: str = AT) -> dict[str, Any]:
    return {"event": "pair_finished", "at": at, "key": card["key"], "card": dict(card)}


def run_finished_record(stop_reason: str = "final_response", at: str = AT) -> dict[str, Any]:
    return {"event": "run_finished", "at": at, "stop_reason": stop_reason}


def write_journal(root: Path, run_id: str, records: Sequence[Mapping[str, Any]], *, torn_tail: str | None = None) -> Path:
    """Writes `.runs/<run_id>.jsonl`; `torn_tail` is appended without a newline, like a write cut by power loss."""
    path = root / ".runs" / f"{run_id}.jsonl"
    write_jsonl(path, records)
    if torn_tail is not None:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(torn_tail)
    return path
