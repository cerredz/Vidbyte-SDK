# Design Doc: Working Principles System-Prompt Preset

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-15
**Last Updated:** 2026-10-15

---

## 1. Overview

This feature adds an opt-in **system-prompt preset**, `SystemPromptPreset.WORKING_PRINCIPLES`, that any developer can attach to an SDK agent in one line. The preset appends a fixed, domain-neutral, 8-sentence paragraph to the agent's system prompt. The paragraph tells the agent to aim at the outcome beyond the literal request, to work the way the best professional in the field would, to set demanding targets, to verify with an independent check, to borrow the methods of other fields that solve the same problem, to finish the given task before taking the larger move it opens, and to carry these principles into the prompt of every subagent it launches. The text distills Felix Rieseberg's essay [How to be more ambitious: a tutorial for humans with models](https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/). The SDK also hands the preset to every agent that runs inside the enabling agent's run (specialists, Jev clones, swarm helpers, bulk workers, fresh continuations, forks, agents a tool starts), through one run-scoped context variable read in one place, so a developer can trust that the agents it spawns work the same way.

```python
from vidbyte import Agent, SystemPromptPreset

agent = Agent(name="analyst", system_prompt="You analyze markets.", system_prompt_presets=[SystemPromptPreset.WORKING_PRINCIPLES])
```

---

## 2. Goals & Non-Goals

### Goals
- Ship the exact preset text as a repository-backed prompt asset (`vidbyte/prompts/prompts/working_principles/`), resolvable through `Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT` and the generated direct import `vidbyte.prompts.working_principles_system_prompt`.
- Add one opt-in constructor field, `system_prompt_presets`, to `BaseAgent` (and so to `Agent`, `CodingAgent`, and every `BaseAgent(**kwargs)` path) and to `JevAgentSettings`.
- Compose each enabled preset's text into the system prompt the model receives: after the agent's own prompt, before the agentic-loop note, in a fixed order, at most once.
- Propagate the preset to every agent started inside the enabling agent's run through one `ContextVar` scope (`SystemPromptPresetScope`), the same mechanism `vidbyte/lib/usage_ledger.py` uses to meter spawned agents. A child that sets its own value explicitly keeps it.
- Keep SDK machinery agents (Jev run-state, handoff, reviewer, run-brief writer, clarification, continual trace, auto handoff) on their tuned prompts: they opt out explicitly.
- Persist the setting through `fork()`, `export_state()`/`restore()`, and session checkpoints, so a resumed or forked agent keeps it.
- Leave every existing agent byte-identical when the field is not set: same system prompt, same reply metadata, same checkpoint shape except one optional key.
- Document the preset, its source, and its one-line usage.

### Non-Goals
- Changing the preset wording. It is used verbatim (see section 6.1).
- Turning the preset on by default for any agent.
- A per-call (`arun`) preset switch. Presets are part of an agent's identity, like its system prompt.
- Root-level support on `CodexHarnessAgent`, `AggregateAgent`, and `MultiAgent`. These facades do not take `BaseAgent` keyword arguments; section 6.11 says what reaches them and how to compose the text yourself.
- Reaching the Codex app-server's own native subagents or the actor runtime's role actors. The SDK does not build their prompts; only sentence 8 of the preset (the parent model's handoff rule) can reach them.
- Adding the preset to the declarative YAML agent descriptor. That is a follow-up (section 13).
- Live model evaluation of whether the preset improves outcomes. Tests here are offline and prove wiring, not quality.

---

## 3. Background & Context

- **Why now:** The user installed the same 8-sentence paragraph in every one of their Claude Code accounts (user-level `CLAUDE.md` plus a `SubagentStart` hook, so every subagent gets it). They want the same behavior as a product feature for SDK developers: one obvious line to turn it on, the exact text visible, and inheritance by every spawned agent.
- **Problem:** Today an SDK developer who wants this behavior must paste the paragraph into every agent's `system_prompt`, including agents the SDK builds for them (Jev clones, swarm helpers, bulk workers, fresh continuations), which they cannot reach. Pasted copies drift and duplicate.
- **Current state:**
  - Prompt text lives in families under `vidbyte/prompts/prompts/`, loaded by `Prompts` (`vidbyte/prompts/catalog.py`), keyed by `Prompt` (`vidbyte/lib/enums/prompts.py`). `vidbyte/prompts/__init__.py` generates a direct import per key.
  - `vidbyte/prompts/agentic_loop.py` is the only existing always-on system-prompt fragment. `AgentRuntime.build_context` (`vidbyte/agents/runtime.py`) appends it after the system prompt the runtime was built with.
  - `BaseAgent._runtime()` (`vidbyte/agents/base.py`) builds a fresh runtime for each run from `self.system_prompt`. Every runtime type (LINEAR, JEV, MCTS_SEARCH, ACTOR_*) takes `system_prompt` there.
  - `AgentRuntime._build_system_string` sends `"System prompt:\n<system prompt>"` as zone 1, followed by the live loop-settings block that changes every iteration. Zone 1 is the only stable prefix of the system string.
  - `BaseAgent.generate_reply` already opens a run-scoped `ContextVar` (`usage_ledger_scope`) so every agent the run starts records into the run's ledger. asyncio tasks copy the context in effect when they are created, so the scope reaches `asyncio.gather`, `ParallelPipeline`, and `asyncio.to_thread` work.
  - Draft PR #1005 (still open) planned the same shape for permissions: a per-agent middleware was rejected because it misses specialists, bulk workers, clones, and forks, and a `ContextVar` ceiling (`vidbyte/lib/permission_ceiling.py`) checked in one central place was used instead.
- **Constraints:** `AGENTS.md` placement rules (enum in `vidbyte/lib/enums/prompts.py`, record in `vidbyte/lib/dataclasses/<domain>.py`, canonical helper in `vidbyte/lib/`, no upward imports from `vidbyte/lib/`); one-level call chains; narrated main functions; validated frozen dataclasses for core inputs; 72-column multi-line comments; `python scripts/run_ci.py` green.

---

## 4. Requirements

### Functional Requirements
1. `Prompts().get(Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT).strip()` returns the 8-sentence paragraph byte-for-byte, and `from vidbyte.prompts import working_principles_system_prompt` returns the same text.
2. `BaseAgent(..., system_prompt_presets=[SystemPromptPreset.WORKING_PRINCIPLES])` puts the exact paragraph into the system prompt of every model call the agent makes.
3. The composed system prompt is `<agent system prompt>\n\n<preset text>\n\n<agentic-loop note>`. With no preset it is exactly what it is today.
4. `system_prompt_presets` accepts `None` (the default: inherit from the run it runs in), or an iterable of `SystemPromptPreset` members or their string values. An empty iterable means "no presets, and do not inherit". A bare string, a non-iterable, an unknown value, or a duplicate raises `ConfigurationError` at construction.
5. An agent's **effective presets** for a run are its own value when set, otherwise the presets of the run it is started in, otherwise none.
6. While an agent's run is active, its effective presets are the active scope for every agent started in that run, including agents started in asyncio tasks created during the run. The scope is restored when the run returns or raises.
7. Presets compose in `SystemPromptPreset` declaration order whatever order the caller gave, and a preset whose text is already in the system prompt (compared with whitespace collapsed) is not appended again.
8. These children inherit the preset with no per-path code: `AgentTool` specialists (`as_tool()`), Jev specialists, `JevCloneAgent`, `JevSwarmAgent`, `JevBulkWorker` agents, the Jev fresh-continuation agent, agents a `ForkConversationTool` call creates, and any `BaseAgent` a tool or task starts during the run.
9. `BaseAgent.fork()` (and every caller of it: the fork tool, `AgentTool`, eval runner, LLM-judge and rubric graders, MCP server handler, team transfers) copies the parent's own `system_prompt_presets` value to the child.
10. `export_state()` records the agent's own value in `RunState.system_prompt_presets` (`None` or a tuple of string values); `restore()` and session forks rebuild it; a checkpoint written before this feature restores as `None`.
11. `JevAgentSettings.system_prompt_presets` (same accepted values, validated in `__post_init__`) reaches the JevAgent's `BaseAgent` state.
12. `JevRunState`, `JevHandoff`, `JevReviewer`, `JevRunBriefWriter`, `JevClarificationAgent`, `ContinualTraceAgent`, and `HandoffAgent` are built with `system_prompt_presets=()` and never receive a preset, even inside a run that has one.
13. `ContextMinimalFanoutParadigm` builds its agents with `system_prompt_presets=()` unless the role's `agent_options` sets the key, so a caller opts in per role.
14. A reply from a run whose effective presets are non-empty carries `metadata["system_prompt_presets"]` as a list of string values. A run with none carries no such key.
15. An explicit per-call system override keeps today's meaning: the `system=` provider option and a base context's `system_prompt` replace the composed prompt, presets included.

### Non-Functional Requirements
- **Performance:** One `ContextVar.get()` per agent run plus one catalog read per runtime build (the catalog is loaded once per process). No extra model calls.
- **Token cost:** The paragraph is 241 words, 1,451 characters, 274 tokens (`cl100k_base`) and 273 tokens (`o200k_base`), plus a 2-character separator. It is paid as input tokens on every model call of every agent that has it (each loop iteration re-sends the system prompt), so a 10-iteration run of a parent plus three 10-iteration children adds about 4 × 10 × 274 ≈ 11k input tokens before caching. Anthropic's tokenizer was not measured here (no paid or keyed API calls); expect the same order of magnitude.
- **Cache behavior:** The text sits inside zone 1 (`System prompt:`), which is identical across every iteration of a run, so it stays inside the stable prefix that provider prompt caches reuse. It is appended after the developer's own prompt, so turning it on changes only the tail of zone 1; the leading developer prompt bytes are unchanged.
- **Concurrency:** The scope is a `ContextVar`, so concurrent runs, and the tasks they start, are isolated; a task created outside the run does not inherit it.
- **Observability:** `reply.metadata["system_prompt_presets"]` on any reply (including a child's) shows which presets applied. Provider-visible traces already record the full system string.
- **Reliability:** No new failure modes at run time; all validation happens at construction or restore.
- **Security:** The preset is static, repository-owned text. No user input is spliced into it.

---

## 5. High-Level Design

Four small pieces, layered bottom-up:

1. **Asset and keys (prompts layer + lib enums).** A new family `working_principles` with one Markdown leaf, `system_prompt.md`, holding the verbatim paragraph. `Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT` keys it. A new enum `SystemPromptPreset` names attachable presets; each member's value is the family key, and its text is that family's `system_prompt` leaf, so adding a future preset is one enum member plus one family.
2. **Validation record (lib dataclasses).** `SystemPromptPresetSelection` in `vidbyte/lib/dataclasses/prompts.py` turns the loose caller value into a validated tuple. `BaseAgent` and `JevAgentSettings` both use it, so the rule exists once.
3. **Run scope (lib canonical helper).** `SystemPromptPresetScope` in `vidbyte/lib/system_prompt_presets.py` owns one `ContextVar`: `active()`, `resolve(own)` (own value if set, else active), `enter(presets)` / `exit(token)` (set and restore, for a method that already has a `finally`), and `scope(presets)` (a context manager over the same pair). It is the prompt counterpart of `usage_ledger.py` and #1005's `permission_ceiling.py`, and it holds enum values only, so `vidbyte/lib/` never imports the prompts layer.
4. **Composer (prompts layer) and one composition point (agents layer).** `SystemPromptPresetComposer` in `vidbyte/prompts/system_prompt_presets.py` (beside `agentic_loop.py`) renders preset text and composes it into a prompt idempotently. `BaseAgent._runtime()` passes the composed prompt as the runtime's `system_prompt`, so every runtime type gets it with one change, and `BaseAgent.generate_reply` opens the scope around the whole run.

```
BaseAgent.generate_reply(message)                         # parent, own = (WORKING_PRINCIPLES,)
  effective = SystemPromptPresetScope.resolve(own)         # own if set, else active
  token = SystemPromptPresetScope.enter(effective)          # ContextVar, copied into tasks
  try / with usage_ledger_scope(...):                      # unchanged body, no new nesting
          _generate_reply
            _runtime(): system_prompt = Composer.compose(self.system_prompt, effective)
              AgentRuntime.build_context -> + agentic-loop note -> zone 1 "System prompt:"
            loop -> tool call -> AgentTool / fork tool / custom @tool
                       child.generate_reply                 # own = None
                         resolve(None) -> active = (WORKING_PRINCIPLES,)  -> composed again
            JevRuntime -> clone / swarm / bulk / fresh / specialist (same path)
            JevRunState / JevHandoff / ...  own = ()  -> resolve(()) = ()  -> no preset
```

Key decisions. (1) **A run-scoped `ContextVar`, not per-path plumbing or middleware.** A middleware or a per-path copy misses every path nobody remembered (the #1005 lesson); one scope opened by `generate_reply` reaches every agent started during the run, including ones added in the future. (2) **`None` inherits, an explicit value is final.** This is the smallest rule that lets SDK machinery and the fan-out paradigm opt out per instance, lets a developer opt a specific child out with `()`, and leaves every existing agent (default `None`, no active scope) unchanged. (3) **Compose in `_runtime()`, not in `AgentRuntime.build_context`.** `_runtime()` is the one constructor every runtime type passes through, so MCTS and actor coordinators get the preset too, and the runtime layer needs no new parameter. (4) **Suffix, not prefix.** The developer's own prompt keeps the lead position that sets the agent's identity, matching the agentic-loop note's composition, and the whole system prompt still sits in zone 1, the cache-stable prefix.

---

## 6. Detailed Design

### 6.1 Prompt asset: `working_principles`

**File(s):** `vidbyte/prompts/prompts/working_principles/working_principles.json`, `vidbyte/prompts/prompts/working_principles/system_prompt.md`
**Type:** New files

#### What it does
Holds the verbatim preset text and its family manifest.

#### Interface / API
```json
{"name": "Working Principles", "description": "...", "key": "working_principles",
 "prompts": {"system_prompt": {"path": "system_prompt.md", "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/working_principles/system_prompt.md"}}}
```

#### Logic / Algorithm
1. `system_prompt.md` contains exactly the 8 sentences as one paragraph and a trailing newline. No heading, version field, or examples: the catalog requires none, and the agentic-loop note (`agentic_loop.context_prompt`) is a precedent for a single-paragraph fragment.
2. `skills/creating-system-prompts.md` asks a *substantial agent system prompt* for Identity/Goal/Checklist/Input/Output sections. This asset is a composable fragment appended to another agent's prompt, not an agent's whole prompt, so that guide does not apply and the wording is unchanged. **No repository rule forced a wording change.**
3. The text is deliberately example-free (examples would pull every task toward their domains); sentence 7 is a scope guard so the preset does not fight host prompts that forbid unrequested scope; sentence 8 is the parent-to-child handoff rule, which the SDK backs up by propagating the preset itself (section 6.6).

#### Edge Cases & Error Handling
- The catalog reads the file in text mode, so CRLF checkouts load as `\n`. The composer strips surrounding whitespace before composing.

### 6.2 Enums: `Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT` and `SystemPromptPreset`

**File(s):** `vidbyte/lib/enums/prompts.py`, `vidbyte/lib/enums/__init__.py`
**Type:** Modified

#### Interface / API
```python
class Prompt(str, Enum):
    ...
    WORKING_PRINCIPLES_SYSTEM_PROMPT = "working_principles.system_prompt"

class SystemPromptPreset(str, Enum):
    """Opt-in system-prompt fragments an agent can attach; each value names the prompt family that holds its text."""

    WORKING_PRINCIPLES = "working_principles"
```

#### Logic / Algorithm
1. Each preset's text is the `system_prompt` leaf of the family named by its value: `Prompt(f"{preset.value}.system_prompt")`.
2. Declaration order is the composition order.
3. Update the header's asset and family counts (98 → 99 prompts, 33 → 34 families) and export `SystemPromptPreset` from `vidbyte/lib/enums/__init__.py`.

#### Edge Cases & Error Handling
- A future member without a matching family fails the catalog lookup in the composer and in a test that walks every member.

### 6.3 Validation record: `SystemPromptPresetSelection`

**File(s):** `vidbyte/lib/dataclasses/prompts.py`
**Type:** New file

#### What it does
Validates an agent's own preset value once, for every place that takes one.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class SystemPromptPresetSelection:
    """An agent's own system-prompt presets: known members, no duplicates."""

    presets: tuple[SystemPromptPreset, ...]

    def __post_init__(self) -> None: ...
    @classmethod
    def parse(cls, value: object, owner: str) -> tuple[SystemPromptPreset, ...] | None: ...
```

#### Logic / Algorithm
1. `parse(None)` returns `None` (inherit).
2. A `str`/`bytes` value raises `ConfigurationError` naming `owner` (a bare string is iterable and would be read one character at a time).
3. A non-iterable raises `ConfigurationError`.
4. Each item that is not already a `SystemPromptPreset` is coerced with `SystemPromptPreset(item)`; an unknown value raises `ConfigurationError` listing the allowed values.
5. The record is built; `__post_init__` checks every item is a `SystemPromptPreset` and that there are no duplicates, then `parse` returns `record.presets`.

#### Edge Cases & Error Handling
- `[]`/`()` returns `()` (explicit "none").
- A generator is consumed once into a tuple.

### 6.4 Run scope: `SystemPromptPresetScope`

**File(s):** `vidbyte/lib/system_prompt_presets.py`
**Type:** New file (canonical helper)

#### Interface / API
```python
class SystemPromptPresetScope:
    """The system-prompt presets the current agent run hands to every agent it starts."""

    @staticmethod
    def active() -> tuple[SystemPromptPreset, ...]: ...
    @staticmethod
    def resolve(own: tuple[SystemPromptPreset, ...] | None) -> tuple[SystemPromptPreset, ...]: ...
    @staticmethod
    def enter(presets: tuple[SystemPromptPreset, ...]) -> Token[tuple[SystemPromptPreset, ...]]: ...
    @staticmethod
    def exit(token: Token[tuple[SystemPromptPreset, ...]]) -> None: ...
    @staticmethod
    @contextmanager
    def scope(presets: tuple[SystemPromptPreset, ...]) -> Iterator[tuple[SystemPromptPreset, ...]]: ...
```

#### Logic / Algorithm
1. A module-level `ContextVar[tuple[SystemPromptPreset, ...]]` defaults to `()`.
2. `resolve(own)` returns `own` when it is not `None`, else `active()`.
3. `enter(presets)` sets the variable and returns the token; `exit(token)` resets it. `scope(presets)` does the same around a `with` block, resetting in `finally`.

#### Edge Cases & Error Handling
- Nested scopes restore in LIFO order, including on exceptions and cancellation.
- Tasks created inside the scope keep it after the scope exits in the parent (asyncio copies the context at task creation); the SDK always awaits the tasks it creates inside a run.

### 6.5 Composer: `SystemPromptPresetComposer`

**File(s):** `vidbyte/prompts/system_prompt_presets.py`, `vidbyte/prompts/__init__.py`
**Type:** New file, Modified (export)

#### Interface / API
```python
class SystemPromptPresetComposer:
    """Renders system-prompt preset text and composes it into an agent's system prompt."""

    @staticmethod
    def text(preset: SystemPromptPreset) -> str: ...
    @classmethod
    def compose(cls, system_prompt: str | None, presets: Iterable[SystemPromptPreset] | None) -> str: ...
```

#### Logic / Algorithm
1. `text(preset)` returns `Prompts().get(Prompt(f"{preset.value}.system_prompt")).strip()`.
2. `compose`: start from `system_prompt.strip()` (or `""`); for each member of `SystemPromptPreset` in declaration order that is in `presets`, skip it when its whitespace-collapsed text is already in the whitespace-collapsed prompt, else append it after a blank line. With no presets the input is returned unchanged (not stripped), so the default path is byte-identical.

#### Edge Cases & Error Handling
- Empty or `None` prompt with a preset returns just the preset text.
- A developer who pasted the paragraph with different line wrapping is not given a second copy.

### 6.6 `BaseAgent` wiring

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### Interface / API
```python
def __init__(self, *, ..., outputs: Sequence[OutputConnector] = (), system_prompt_presets: Iterable[SystemPromptPreset | str] | None = None) -> None
self.system_prompt_presets: tuple[SystemPromptPreset, ...] | None
```

#### Logic / Algorithm
1. `__init__` stores `SystemPromptPresetSelection.parse(system_prompt_presets, "BaseAgent.system_prompt_presets")`.
2. `generate_reply` resolves the run's effective presets right after the queue claim, calls `SystemPromptPresetScope.enter(effective)`, and calls `exit(token)` first in its existing `finally`, beside the queue-token reset. The body keeps its indentation, so the change adds no control-flow nesting (lint S024) to a method already at the limit.
3. `_runtime()` passes `system_prompt=SystemPromptPresetComposer.compose(self.system_prompt, SystemPromptPresetScope.resolve(self.system_prompt_presets))`. Inside a run, `resolve` returns the scope the run opened.
4. `_generate_reply` spreads `self._applied_preset_metadata()` into its metadata literal; the helper returns `{"system_prompt_presets": [p.value for p in effective]}` when non-empty and `{}` otherwise, which keeps `_generate_reply` under its complexity and statement limits (lint S008).
5. `export_state()` writes `system_prompt_presets=None if own is None else tuple(p.value for p in own)`; `restore()` passes `state.system_prompt_presets` back to the constructor.

#### Edge Cases & Error Handling
- `self.system_prompt` stays the developer's raw prompt (`card()`, `export_state()`, trace start metadata, forks), so presets are never baked into the stored prompt and never double up on restore.
- Subclasses that override `generate_reply` without calling `BaseAgent.generate_reply` (`MultiAgent`, `AggregateAgent`) do not open a scope; see 6.11.

### 6.7 `AgentForker`

**File(s):** `vidbyte/agents/fork.py`
**Type:** Modified

Pass `system_prompt_presets=agent.system_prompt_presets` to the child `BaseAgent`. A fork whose `system_prompt` is replaced (by the developer or the fork tool's model-supplied prompt) still keeps the parent's presets, because presets are a separate field.

### 6.8 Session persistence

**File(s):** `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/sessions/serialization.py`
**Type:** Modified

Add `system_prompt_presets: tuple[str, ...] | None = None` to `RunState`, following `permission_policy`'s optional-field precedent; write it as `None` or a list and read it back as `None` or a tuple. No schema-version bump: older payloads lack the key and read as `None` (inherit), which is exactly their old behavior.

### 6.9 JevAgent

**File(s):** `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/agent.py`
**Type:** Modified

`JevAgentSettings.system_prompt_presets: tuple[SystemPromptPreset, ...] | None = None`, normalized in `__post_init__` through `SystemPromptPresetSelection.parse`. `JevAgent.__init__` passes it to `BaseAgent`. Jev's clone, swarm, bulk-work, and fresh-continuation agents are built from `JevAgentSettings` with the default `None`, so they inherit from the JevAgent run that starts them; no change in those files.

### 6.10 SDK machinery opt-outs

**File(s):** `vidbyte/agents/jev/done/run_state.py`, `vidbyte/agents/jev/done/handoff.py`, `vidbyte/agents/jev/done/reviewer.py`, `vidbyte/agents/jev/brief/writer.py`, `vidbyte/agents/jev/gate/clarification.py`, `vidbyte/agents/continual_trace.py`, `vidbyte/agents/handoff.py`
**Type:** Modified

Each passes `system_prompt_presets=()` to `BaseAgent`, with one `@intent` comment. `ContinualTraceAgent` and `HandoffAgent` also pop a caller-supplied `system_prompt_presets` from `**kwargs`, as they already pop `system_prompt`. Reason: these agents produce structured evidence, notes, questions, or traces for code to parse, with prompts tuned for that job; "aim beyond the literal request" and "take the larger move" would invite extra content where none is wanted, and the run-brief writer runs every iteration, so it would also pay the token cost on every iteration.

### 6.11 Minimal-context fan-out paradigm and other facades

**File(s):** `vidbyte/paradigms/context_minimal_fanout/paradigm.py`
**Type:** Modified

The paradigm builds each role's agent with `system_prompt_presets=()` unless `role_settings.agent_options` already holds the key. Reason: its adversarial stage exists to make the implementation prompts non-overlapping, and each worker gets only the context of its own slice. Sentences 1 and 7 ("aim at the larger goal", "take the larger move") push a worker past its slice, where it can collide with a sibling working in parallel, and a worker with minimal context cannot judge "clearly serves the user's real goal". A caller who wants it anyway opts in per role: `AgentRoleSettings(..., agent_options={"system_prompt_presets": [SystemPromptPreset.WORKING_PRINCIPLES]})`.

Not covered at the root, documented instead:
- `MultiAgent` and `AggregateAgent` take no `BaseAgent` keyword arguments and override `generate_reply`. Their member agents are ordinary `BaseAgent`s: set the field on them, or run the team inside a preset-enabled agent's run and they inherit it.
- `CodexHarnessAgent` is not a `BaseAgent`. Compose the text yourself: `system_prompt=SystemPromptPresetComposer.compose("...", [SystemPromptPreset.WORKING_PRINCIPLES])`. A native Codex fork copies `system_prompt`, so the text carries into forks. Codex's own subagents are built by Codex; only sentence 8 reaches them.
- Actor-runtime role actors and context-window side calls (error-correction auditor, problem-space explorer, reflexion reflector, independent critic, prosecutor/defender/judge, the agentic grader's grader) use their own fixed prompts through runners or `AgentRuntime`, not `BaseAgent`; they stay as they are. The multi-provider grader's trial loops and Reflexion's retries reuse the composed prompt, so they keep the preset unless the developer overrides `agent_system_prompt`.

### 6.12 Propagation table

| Path | Covered? | How |
|---|---|---|
| The agent itself, any runtime (LINEAR, MCTS_SEARCH, ACTOR_* coordinator) | Yes | `_runtime()` composes into `system_prompt` |
| `JevAgent` main agent | Yes | `JevAgentSettings.system_prompt_presets` |
| `AgentTool` specialist (`as_tool()`) | Yes | runs inside the parent run; scope inherited (its own value wins if set) |
| Jev specialist chosen by the gate | Yes | scope |
| Jev CLONE (`JevCloneAgent`) | Yes | scope |
| Jev SWARM helpers (`JevSwarmAgent`) | Yes | scope (asyncio.gather copies it) |
| Jev BULK_WORK workers (`JevBulkWorker`) | Yes | scope (ParallelPipeline uses asyncio.gather) |
| Jev fresh continuation | Yes | scope |
| `ForkConversationTool` child | Yes | `AgentForker` copies the field, plus scope |
| `BaseAgent.fork()` outside a run (incl. eval runner, LLM judge/rubric graders, MCP handler, team transfers) | Yes | `AgentForker` copies the field |
| Session fork / resume / `BaseAgent.restore` | Yes | `RunState.system_prompt_presets` |
| Any `BaseAgent` a custom `@tool` or task starts during the run | Yes | scope (`asyncio.to_thread` copies context too) |
| Jev run state, handoff, reviewer, run-brief writer, clarification | No, deliberately | explicit `()` |
| `ContinualTraceAgent`, `HandoffAgent` (auto handoff) | No, deliberately | explicit `()` |
| Minimal-context fan-out paradigm agents | Opt-in per role | `()` default; `agent_options` overrides |
| `MultiAgent` / `AggregateAgent` root | Partial | members inherit when the team runs inside a preset scope; set on members directly |
| `CodexHarnessAgent` root and fork | Manual | compose into `system_prompt`; fork copies it |
| Codex-native subagents, actor-runtime role actors | No | prompts built outside the SDK agent path; sentence 8 only |
| Context-window side calls (auditors, critics, judges) | No, deliberately | fixed machinery prompts; trial/retry loops keep the composed prompt |
| Agents built in a raw thread or foreign event loop without copying context | No | same limit as the usage ledger; set the field on that agent |

---

## 7. Data Model Changes

### 7.1 `RunState` (`vidbyte/lib/dataclasses/sessions.py`)

**Change type:** Modified

```python
system_prompt_presets: tuple[str, ...] | None = None  # None: the agent inherits; () : explicitly none
```

**Migration strategy:**
- Forward migration: none. Old payloads lack the key and deserialize to `None`, which reproduces their behavior.
- Rollback plan: an older SDK ignores the extra key when reading a newer checkpoint dict (`_run_state_from_dict` reads known keys only).

### 7.2 `JevAgentSettings` (`vidbyte/agents/jev/settings.py`)

**Change type:** Modified. New optional field `system_prompt_presets: tuple[SystemPromptPreset, ...] | None = None`.

### 7.3 `SystemPromptPresetSelection` (`vidbyte/lib/dataclasses/prompts.py`)

**Change type:** New. See 6.3.

---

## 8. API Changes

N/A for HTTP: the SDK exposes no endpoints. Python API changes:

| Change | Symbol |
|---|---|
| New enum | `vidbyte.SystemPromptPreset`, `vidbyte.lib.enums.SystemPromptPreset` |
| New prompt key | `Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT`; direct import `vidbyte.prompts.working_principles_system_prompt` |
| New keyword | `BaseAgent(..., system_prompt_presets=None)` (also `Agent`, `CodingAgent`, `BaseAgent.restore` via state) |
| New attribute | `BaseAgent.system_prompt_presets` |
| New settings field | `JevAgentSettings.system_prompt_presets` |
| New helper | `vidbyte.prompts.SystemPromptPresetComposer` |
| New lib helper | `vidbyte.lib.system_prompt_presets.SystemPromptPresetScope` |
| New record | `vidbyte.lib.dataclasses.prompts.SystemPromptPresetSelection` |
| New reply metadata key | `system_prompt_presets` (only when non-empty) |
| New `RunState` field | `system_prompt_presets` |

Error cases (all `ConfigurationError` at construction or restore): bare string, non-iterable, unknown preset value, duplicate preset.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/working_principles/working_principles.json` | Family manifest |
| CREATE | `vidbyte/prompts/prompts/working_principles/system_prompt.md` | Verbatim preset text |
| MODIFY | `vidbyte/lib/enums/prompts.py` | `Prompt` key, `SystemPromptPreset` enum, header counts |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export `SystemPromptPreset` |
| CREATE | `vidbyte/lib/dataclasses/prompts.py` | `SystemPromptPresetSelection` |
| CREATE | `vidbyte/lib/system_prompt_presets.py` | `SystemPromptPresetScope` |
| CREATE | `vidbyte/prompts/system_prompt_presets.py` | `SystemPromptPresetComposer` |
| MODIFY | `vidbyte/prompts/__init__.py` | Export the composer |
| MODIFY | `vidbyte/agents/base.py` | Field, scope, composition, metadata, export/restore |
| MODIFY | `vidbyte/agents/fork.py` | Copy the field |
| MODIFY | `vidbyte/lib/dataclasses/sessions.py` | `RunState.system_prompt_presets` |
| MODIFY | `vidbyte/sessions/serialization.py` | Persist the field |
| MODIFY | `vidbyte/agents/jev/settings.py` | `JevAgentSettings.system_prompt_presets` |
| MODIFY | `vidbyte/agents/jev/agent.py` | Pass the field to `BaseAgent` |
| MODIFY | `vidbyte/agents/jev/done/run_state.py`, `done/handoff.py`, `done/reviewer.py`, `brief/writer.py`, `gate/clarification.py` | Machinery opt-out |
| MODIFY | `vidbyte/agents/continual_trace.py`, `vidbyte/agents/handoff.py` | Machinery opt-out |
| MODIFY | `vidbyte/paradigms/context_minimal_fanout/paradigm.py` | Default opt-out, per-role opt-in |
| MODIFY | `vidbyte/__init__.py` | Top-level `SystemPromptPreset` export |
| MODIFY | `vidbyte/prompts/README.md` | Catalog row and description |
| MODIFY | `vidbyte/agents/README.md` | "System Prompt Presets" section |
| MODIFY | `vidbyte/lib/README.md`, `skills/usage/create_agent.md` | Key-module line; constructor listing |
| MODIFY | `vidbyte/agents/jev/README.md`, `vidbyte/paradigms/context_minimal_fanout/README.md` | Inheritance and opt-in notes |
| MODIFY | `README.md`, `llms.txt` | Short usage section |
| MODIFY | `contracts/sdk-public-api.json` | Regenerated for the new root export (`python scripts/generate-sdk-public-api.py`) |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | Add the keyword to `PARITY_KEYWORDS`, as that file asks for every keyword `RunState` exports |
| CREATE | `tests/features/system_prompt_presets/` (`FEATURE.md`, `README.md`, `fakes.py`, `test_system_prompt_presets_units.py`, `test_system_prompt_presets_propagation.py`) | Feature test pack |
| CREATE | `scripts/test-working-principles-preset.py` | Verification entry point |
| CREATE | `docs/design/working-principles-preset.md` | This document |

---

## 10. Testing Plan

All tests are offline. Generative runners are faked (a recording runner bound through the agent's runner cache, or `BaseAgent._runner_for_model` patched for agents the SDK builds internally). No test constructs a real provider runner or calls a model. The one test that drives the real Jev loop answers Jev's decisions with the in-process scripted helper the existing compute tests use, so no decision request leaves the process. A safety net in `fakes.py` also refuses the SDK's HTTP send and any non-loopback socket during every test.

### Unit Tests
- `PromptAsset` → `it resolves the key and the direct import to the verbatim paragraph` — [Silent Failure] (an "improved" asset would still load)
- `PromptAsset` → `it has exactly 8 sentences and no example markers` — [Silent Failure]
- `SystemPromptPreset` → `every member resolves to a family system_prompt leaf` — [Hidden Assumption]
- `SystemPromptPresetSelection.parse` → `None stays None, empty is (), strings coerce` — [Edge Case]
- `SystemPromptPresetSelection.parse` → `rejects a bare string, a non-iterable, an unknown value, and a duplicate` — [Hidden Assumption]
- `SystemPromptPresetScope` → `resolve returns own when set (even empty) and active otherwise` — [Edge Case]
- `SystemPromptPresetScope` → `scope restores after an exception and after nesting` — [Hidden Failure]
- `SystemPromptPresetScope` → `a task created inside the scope inherits it; concurrent scopes stay isolated` — [Hidden Failure]
- `SystemPromptPresetComposer.compose` → `no presets returns the input unchanged` — [Silent Failure]
- `SystemPromptPresetComposer.compose` → `appends after the prompt with one blank line, in enum order` — [Edge Case]
- `SystemPromptPresetComposer.compose` → `skips a preset already present, even re-wrapped` — [Silent Failure]
- `SystemPromptPresetComposer.compose` → `None or empty prompt yields just the preset text` — [Edge Case]

### Integration Tests
- `BaseAgent` → `enabled: the runner's system string contains the paragraph once, between the prompt and the agentic-loop note` — [Silent Failure]
- `BaseAgent` → `disabled: the system string is identical to a build without the field and has no metadata key` — [Silent Failure]
- `BaseAgent` → `string values work and reply metadata lists the applied presets` — [Edge Case]
- `BaseAgent` → `the scope is gone after a run, so a later plain agent gets nothing` — [Hidden Failure]
- `BaseAgent` → `a run that raises still restores the scope` — [Hidden Failure]
- `BaseAgent` → `an explicit per-call system= option still replaces the whole prompt, preset included` — [Hidden Assumption] (requirement 15)
- `Propagation` → `an as_tool() specialist run by the parent gets the preset` — [Hidden Assumption]
- `Propagation` → `a fork_conversation child with its own system prompt gets the preset once` — [Hidden Failure]
- `Runtimes` → `MCTS and both actor runtimes receive the composed prompt` — [Hidden Assumption]
- `Propagation` → `a BaseAgent started inside a custom @tool gets it` — [Hidden Assumption]
- `Propagation` → `a child with system_prompt_presets=() does not, nor do its own children` — [Edge Case]
- `Propagation` → `a child whose own prompt already holds the paragraph is not given a second copy` — [Silent Failure]
- `Propagation` → `fork() copies the field (also for a replaced system prompt)` — [Hidden Failure]
- `Persistence` → `export_state/restore round-trips None, (), and (WORKING_PRINCIPLES,)` — [Hidden Failure]
- `Persistence` → `the session serializer round-trips the field and an old dict without it reads None` — [Hidden Assumption]
- `Persistence` → `Session.resume and Session.fork keep the presets` — [Hidden Failure]
- `Jev` → `JevAgentSettings validates and passes the field; JevAgent's own calls carry the paragraph` — [Hidden Assumption]
- `Jev` → `JevCloneAgent, JevSwarmAgent, JevBulkWorker's agent, and the fresh-continuation agent inherit inside a preset run` — [Hidden Assumption]
- `Jev` → `a CLONE launch through a real JevAgent loop reaches the clones' runners with the paragraph` — [Hidden Failure] (end to end through `JevRuntime`)
- `Jev` → `a specialist the gate chooses inherits the preset` — [Hidden Assumption] (end to end through the preflight gate)
- `Uncovered` → `MultiAgent/AggregateAgent take no keyword and replace generate_reply; CodexHarnessAgent is not a BaseAgent; a child run after its parent's run and a raw thread inherit nothing` — [Hidden Assumption] (pins the documented limits)
- `Machinery` → `JevRunState, JevHandoff, JevReviewer, JevRunBriefWriter, JevClarificationAgent, ContinualTraceAgent, and HandoffAgent never get it inside a preset run` — [Silent Failure]
- `Paradigm` → `fan-out agents get nothing under an active scope by default, and get it when agent_options opts in` — [Edge Case]

What could go wrong between components without an error: a child built before the run but run after it ends (gets nothing; documented), a subclass overriding `generate_reply` (no scope; documented and covered by the MultiAgent/AggregateAgent note), the catalog asset drifting from the expected text (caught by the verbatim test, which holds its own copy of the paragraph as the independent reference).

Gate files the repo requires to stay in sync (prompt counts, public API contract, enum exports) are regenerated and checked by `python scripts/run_ci.py`; the PR records the final summary lines.

### Manual / QA Test Cases
1. Given a fresh venv, when `python -c "from vidbyte.prompts import working_principles_system_prompt as t; print(t)"` runs, then the 8 sentences print — [Edge Case: installed wheel resource loading].
2. Given an agent with the preset and a fake runner, when it delegates to an `as_tool()` specialist, then both runners' `system` arguments contain the paragraph exactly once and the specialist's reply metadata lists `working_principles` — [Hidden Assumption].
3. Given a session checkpoint written by the previous SDK version, when it is restored, then the agent has `system_prompt_presets is None` and behaves as before — [Hidden Assumption].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `contextvars` | stdlib | Run scope | None new; the usage ledger already relies on it |
| Felix Rieseberg's essay | https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/ | Source of the ideas (credited in docs) | None at run time |

No new third-party packages, network calls, or credentials.

---

## 12. Rollout & Deployment

- **Feature flag:** The field itself; default `None`, no active scope at top level, so nothing changes until a developer opts in.
- **Breaking change:** No. One new optional keyword, one new optional `RunState` field, one new enum and prompt key.
- **Deployment order:** Single package release.
- **Rollback:** Revert the PR. Checkpoints written with the field still load on the older SDK (unknown key ignored).

---

## 13. Open Questions

- [ ] Should `JevAgent`'s machinery opt-outs stay absolute, or should `JevReviewer` (an adversarial verifier) receive the preset's "verify independently" stance? This design keeps all machinery on its tuned prompts.
- [ ] Should the minimal-context fan-out paradigm inherit by default instead of opting in per role? This design says no because of sibling overlap (6.11).
- [ ] Should `MultiAgent`, `AggregateAgent`, and `CodexHarnessAgent` take the field at the root (open a scope in their own `generate_reply`, compose in the Codex translator)? Left as a follow-up to keep this PR to one mechanism.
- [ ] Should the declarative YAML agent descriptor accept `system_prompt_presets`? Follow-up.
- [ ] Should an evaluation (offline eval suite with a judge) measure whether the preset improves outcomes on real tasks before it is promoted in docs as a recommended default?

---

## 14. Alternatives Considered

### Alternative 1: A middleware that rewrites `system` before each model call
- What: `WorkingPrinciplesMiddleware` added to an agent's middleware list.
- Why rejected: Middleware is per agent, so it misses every agent the run starts (the #1005 lesson); non-linear runtimes reject middleware; and a transform that rewrites the whole system string would place the text after the per-iteration loop-settings block, outside the cache-stable prefix.

### Alternative 2: Per-path plumbing (copy the field at each spawn site)
- What: Read the parent's setting in every place that builds a child (`AgentTool`, clone, swarm, bulk, fresh, fork tool, ...).
- Why rejected: Eight-plus edit sites today, and every future spawn path silently misses it. Kept only where a child is built *outside* any run (`AgentForker`, `restore`), where no scope exists.

### Alternative 3: A context primitive (`ContextManager.place_after_system_prompt`)
- What: Ship the text as a `TextContextItem` at the top of the context zone.
- Why rejected: It renders in the primitives zone after the loop-settings block, so it is outside the stable prefix, it is not "in the system prompt", and context managers are copied or replaced per child in ways that would need the same per-path plumbing.

### Alternative 4: Prefix the preset before the developer's prompt
- What: `<preset>\n\n<agent prompt>`.
- Why rejected: The developer's prompt sets the agent's identity and should lead; both placements are equally cache-stable inside zone 1; the agentic-loop note's composition is already a suffix.

### Alternative 5: A boolean `working_principles=True`
- What: One flag for this preset.
- Why rejected: `AGENTS.md` asks for enum-typed closed sets, a second preset would need a second flag, and the preset tuple matches the existing `JevRuntimeSettings.preflight` shape.

### Alternative 6: Inherit by union (child presets = parent's ∪ own)
- What: Never let a child opt out.
- Why rejected: SDK machinery and the fan-out paradigm need a per-instance opt-out, and a developer needs one for a strict-format child (for example, a JSON formatter).
