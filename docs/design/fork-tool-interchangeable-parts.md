# Design Doc: Fork Tool with Interchangeable Parts

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

This feature turns forking from a dev-only, config-copy operation into a first-class capability with two faces: (a) a richer `BaseAgent.fork()` that can branch a live run — carrying conversation history, handoffs, and MCP attachments — while swapping any single "part" of the agent (system prompt, tools, model, loop budget, trace option, output schema, etc.), and (b) a new model-facing builtin tool, `fork_conversation`, that lets an agent fork *its own* current conversation mid-run with a chosen subset of those parts changed, run the fork to completion, and receive its answer as a tool result. Today no such self-forking capability exists anywhere in the SDK — forking is only reachable from Python code, copies configuration but almost no run state, and is exercised by exactly three call sites (`AgentTool`, the eval runner, and docs examples). The design is governed by one invariant: a fork is always privilege-non-escalating — the model can narrow or rearrange what the developer granted, never expand it.

---

## 2. Original User Prompts

**Prompt 1 (via `/talk`):**

> vidbyte-sdk/ repo request for the session object: - I want to extend the forking function inside of our session object and I also want to propagate this change to the forking tool. Basically I want to be able to fork an agent's current run state and current life cycle but fork it with different interchangeable parts. So for example:
>   - We can fork the current conversation with a different system prompt.
>   - We can fork the current conversation with another prompt from the user.
>   - We could fork a conversation and change the agent's tool set.
>   Basically I want it to be able to very easily change each part of an agent when we fork it. I want you to also propagate these changes into their own tool calls. - Can you kind of just scope out and think about how we can implement this change?. inside of the current repo can you show me 1) how a dev would use forking today and 2) help me scope out the implementation of these changes

**Prompt 2:**

> yes 1 fork tool with the params is the right choice, also I want to make sure that we have the following capability: I want the agent to be able to fork its own conversation, not just the dev through the code, do we have this. Also, can you really think about ALL of the interchangable parts that we can have in the forking tool, list these all out, and explain exactly how we are going to implement this change? ( in plain english too)

**Prompt 3 (via `/create-design`):**

> great, apart from the bugs can you create a design doc for creating the fork tool for the agent, extending the fork functionality to create a fork with interchangable parts, and exposing this tool to the agent, take into account file paths and make this design doc very comprehensive

---

## 3. Structured Conversation Notes

### Key Decisions

- **One parameterized fork tool, not several narrow tools.** The user explicitly confirmed ("yes 1 fork tool with the params is the right choice"). Rationale: the parts compose (you usually want prompt *and* toolset swapped together), and N narrow tools bloat the tool list the model reasons over. Tool name: `fork_conversation`.
- **Agent self-forking is the new capability being built.** Confirmed during conversation: nothing model-facing calls `fork()` today. The dev adds `ForkConversationTool` to an agent's tool list; from then on the model can fork itself mid-run.
- **Privilege-non-escalating invariant.** The fork tool can only narrow/rearrange developer-granted capability: tool subset by name from the parent's catalog (plus optional dev-supplied extra toolsets), model choice only from a dev-configured allow-list, `max_iterations` capped at the parent's own value, permission policy always inherited verbatim and never a parameter.
- **Three-tier split of interchangeable parts** (full inventory in §6): Tier 1 = model-facing tool parameters (JSON-expressible, safe), Tier 2 = dev-facing `fork()` keyword overrides (Python objects), Tier 3 = deliberately locked (permission policy, credentials, fork depth, aggregation plan).
- **Blocking (synchronous) forks only in V1.** The tool runs the child to completion inside the tool call and returns its answer inline. Detached/parallel forks with a join primitive are a named non-goal.
- **Fresh identity per fork.** Each fork gets a new `run_id` by default with lineage recorded (`metadata["forked_from"]` pointing at the parent), replacing today's behavior where parent and child share a `run_id` and are indistinguishable in traces.
- **Fork-depth cap (default 2)** via an inherited metadata counter — the fork-bomb brake, since a child whose tool set includes `fork_conversation` can recurse.
- **History as a three-way mode, not a boolean**, on the tool: `"full" | "none" | "last_n"` (+ `last_n` int), because "take a recent window" is a real use case and costs nothing extra. Dev-side `fork()` additionally gets an explicit `history=[...]` transcript override.
- **`None`-means-inherit convention preserved** on all new `fork()` parameters, matching the existing signature style at `vidbyte/agents/base.py:362`.

### Rejected Alternatives

- **Multiple narrow fork tools** (`fork_with_system_prompt`, `fork_with_tools`, ...) — rejected by the user in favor of one parameterized tool. Only advantage would have been per-part permission gating; not needed now.
- **Free-form model selection by the model** — rejected; model strings must come from a dev-configured allow-list.
- **Model-controlled permission policy** — rejected permanently (Tier 3). A dev who wants a differently-permissioned agent constructs a new agent, not a fork.
- **Detached / fire-and-forget forks with a later join** — deferred, not rejected on merit; it requires child lifecycle handles and a join tool, a materially bigger feature.
- **Extracting a formal `Session`/`RunState` object from `BaseAgent`** — discussed (the user's mental model says "session object", but no `Session` class exists in the SDK; run state lives directly on `BaseAgent` fields). A full extraction refactor was deliberately not scoped; fork operates on `BaseAgent`'s existing fields.
- **Reusing `AgentTool` as the fork tool** — rejected; `AgentTool` wraps a *different* pre-built agent for delegation and flattens context into a string prompt. The fork tool is about the agent's *own* config/state with parts swapped, and follows the `bind_agent` builtin pattern instead.

### Constraints & Assumptions

- **The known fork bugs are explicitly OUT of scope of this doc** (user: "apart from the bugs") — they are tracked for separate fix work. But one of them is a *hard prerequisite* and the implementer must check its status before building (see Open Questions):
  1. **Stateful-tool aliasing:** `fork()` passes `self._agent_tool_items` (the same tool instances) to the child, whose constructor calls `_bind_agent_tool_context` (`vidbyte/agents/base.py:346`), re-pointing shared stateful tools (`CreateHandoffTool.bind_agent`, `AttachMcpServerTool.bind_agent`, `AgentTool.bind_context_getter`) at the child — silently breaking the parent. Self-forking multiplies this. If the fix has not landed when implementation starts, the minimal cloning safeguard (fresh instances of stateful builtins for the child) must be included in this feature's PR.
  2. `vidbyte/trace/README.md:45` documents `agent.fork(trace_option=...)` which is a `TypeError` today — this feature makes that example true (add the param), so the README fix rides along naturally.
  3. Forks currently lose MCP attachments (`_mcp_handles`/`_pending_mcp_configs` reset to `[]`) — this feature adds MCP carry, subsuming that gap.
  4. `AggregateAgent.fork` (`vidbyte/agents/aggregation.py:207`) silently swallows `**_overrides` — this feature changes it to raise `ConfigurationError` for unsupported overrides.
- Python ≥3.11, dependencies only `pydantic>=2,<3` and `httpx>=0.27` (`pyproject.toml`). No new dependencies.
- `AgentMessage` history entries are treated as immutable; `list(self.history)` shallow copy is the copy semantics (assert in a test).
- Non-linear runtimes (MCTS, actor variants) reject middleware/continual-trace/non-default algorithms at construction (`vidbyte/agents/base.py:107-129`); fork-with-overrides can construct invalid combos and the constructor catches them — the fork tool must surface these as `ToolResult.error`, never an uncaught exception.
- There is no `Session` class in the repo (the only `session.py` is in the stale `worktree-resolve-sdk-pr-195-comments/` copy, which must be ignored entirely).
- Zero existing direct test coverage of `fork()` — no `.fork(` calls anywhere under `tests/`.

### Clarifications & Answers

- Q: "Do we have agent-self-forking today?" → A: **No.** Only dev-side callers exist: `AgentTool.execute` (`vidbyte/tools/agent_tool.py:50`, calls `fork()` with zero overrides and string-flattens context), `evals/runner.py:124` (`fork(name=f"{target.name}_eval")` for isolation), and doc examples. `ForkConversationTool` creates the capability.
- Q: "One tool or several?" → A: One tool with parameters (user confirmed).
- Q: "What does the user mean by 'session object'?" → Resolved: `BaseAgent` itself; its config fields plus run-state fields (`history`, `_active_prompt`, `handoffs`, `_tool_call_contexts`, `last_*`, MCP handles).
- The user's phrase "propagate these changes into their own tool calls" was interpreted (and confirmed by the one-tool decision) as: expose forking as a model-facing tool call, not as N separate per-part tools.

### Terminology / Glossary

- **Fork** — construct a new `BaseAgent` from a parent's config with keyword overrides; after this feature, optionally carrying run state.
- **Interchangeable part** — any single config or run-state component swappable at fork time while everything else is inherited.
- **Run state / lifecycle** — the mutable per-run fields on `BaseAgent`: `history`, `_active_prompt`, `handoffs`/`last_handoff`, `_tool_call_contexts`, `last_prompt`/`last_reply`/`last_trace`, `_behavior_view`, MCP handles/pending configs.
- **Self-fork** — the agent invoking `fork_conversation` on itself mid-run via the builtin tool.
- **Privilege-non-escalating** — the child's capabilities are always a subset of (parent capabilities ∪ dev-configured allow-lists).
- **Fork depth** — count of fork ancestors, carried in metadata, capped.
- **Stateful builtin** — a tool holding a reference to its owning agent via `bind_agent()`/`bind_context_getter()` (e.g. `CreateHandoffTool`, `AttachMcpServerTool`, `AgentTool`).
- **Context Protocol Header** — the structured module docstring (Description/Purpose/Architecture/Relations, optionally Key Functions/Similar Files) at the top of every `vidbyte/` module. Mandatory for new files.

### Implementation Hints for the Downstream Model

- **Pattern to imitate for the tool:** `vidbyte/tools/builtins/handoff/create.py` (`CreateHandoffTool`) is the canonical agent-bound builtin: starts unbound (`self._agent = None`), `bind_agent(agent)` attaches the live agent, `spec()` builds a rich static description string (module-level `_STATIC_DESCRIPTION`), uses `input_schema=` (JSON Schema dict) on `ToolSpec` rather than `parameters=` tuples, validates args in a `_build_*` helper raising `ValueError`, converts to `ToolResult.error` in `execute()`. Copy this structure closely, including the `__init__.py` re-export style of `vidbyte/tools/builtins/handoff/__init__.py`.
- **Binding wire-up:** `BaseAgent._bind_agent_tool_context` (`vidbyte/agents/base.py:346`) is where builtins get bound — add an `isinstance(tool, ForkConversationTool): tool.bind_agent(self)` branch (import locally inside the method, as the existing branches do, to avoid import cycles).
- **Critical runner gotcha for the model-swap part:** `fork()` currently passes `runner=self.runner` (the live runner object) and separately copies `model_name`/`provider`/`temperature` into the child's `runner_config`. If a fork overrides the model but keeps the parent's executable runner, `_runner_for_modality` (`vidbyte/agents/base.py:895`) will keep using the old runner and the override silently does nothing. When any of model/provider/temperature/runner_options are overridden, the fork must pass `runner=None` and `runners={}` so the child lazily builds a fresh runner from the new config via `ModalityDetector.create_runner`. Also note `_create_runner` (`base.py:602`) returns a non-executable `ConfiguredAgentRunner` placeholder — the lazy path in `_runner_for_modality` is the real construction site.
- **`fork()` today** is at `vidbyte/agents/base.py:362-408`: constructor-replay with `None`-means-inherit overrides for name, runner(s), tools, system_prompt, modality, metadata, middleware, context_items, context_manager, algorithm, plus `include_history: bool = False` (history is the only run state that can cross). Extend, don't rewrite.
- **Tools catalog:** `vidbyte/tools/catalog.py` — `Tools` is immutable-ish with `add`/`extend`/`without` returning new catalogs, `_by_name` lookup, `ToolRegistrationError` on duplicates. Add `subset(names: Iterable[str]) -> Tools` here; raise `ToolRegistryError` (or return an error the tool converts) for unknown names.
- **MCP carry design:** do NOT share live `McpServerHandle`s between parent and child (subprocess ownership: closing one would kill the other's connection). Instead, the child should receive the parent's `_pending_mcp_configs` plus the `McpServerConfig`s of already-attached servers (available on handles via `vidbyte/tools/mcp/types.py` — verify the handle exposes its config; if not, retain configs at attach time) re-registered as *pending*, so the child lazily spawns its own subprocesses on first run via `_ensure_mcp_connected` (`vidbyte/agents/mixins.py:175`). MCP-bridged tools in the parent's catalog must NOT be copied into the child's tool items (they'd be dangling bridges to the parent's subprocess) — filter them out; the child re-bridges its own on connect. `mcp_tool_names()` on the parent tells you which names are MCP-sourced.
- **Fork-depth mechanics:** read `self.metadata.get("fork_depth", 0)` in the tool; refuse with `ToolResult.error` when `>= max_fork_depth`; the fork call passes `metadata={"fork_depth": depth + 1, "forked_from": parent_run_id_or_name, "fork_purpose": purpose}` (fork() already merges metadata dicts).
- **`ToolSpec` contract** is at `vidbyte/lib/dataclasses/tools.py` (re-exported via `vidbyte/tools/types.py`). Note `validate_call` in `vidbyte/tools/base.py` only checks `parameters=` tuples, not `input_schema` — so like `CreateHandoffTool`, do required-arg validation inside `execute()`.
- **Permission level:** use `ToolPermission.SAFE` for consistency with `AgentTool` and `CreateHandoffTool` (the child executes under the parent's inherited permission policy anyway, so the fork call itself grants nothing). Flagged as an open question if the team prefers `EXECUTE`.
- **Exports:** new package `vidbyte/tools/builtins/fork/` with `fork.py` + `__init__.py`; re-export `ForkConversationTool` from `vidbyte/tools/builtins/__init__.py` (alphabetical position in the imports and `__all__`). Check whether `vidbyte/__init__.py` or `vidbyte/tools/__init__.py` re-export builtins and mirror.
- **Tests to imitate:** `tests/test_create_handoff_tool.py` (builtin tool testing pattern, fake agents), `tests/test_agent_base.py` (agent construction/behavior). Repo uses pytest; there are also runnable demo scripts under `scripts/` (e.g. `scripts/test-agent-behavior.py`) — add one if convenient, they appear to be the repo's manual-verification convention.
- **Docs conventions:** every module needs the Context Protocol Header docstring; design docs live in `docs/design/` after implementation (this doc gets promoted from `docs/pre-design/` by `/implement-design-doc`); consider a short skill page under `skills/vidbyte-sdk/` (e.g. `forking.md`) matching existing ones like `agent-behavior.md` — optional.
- **Things NOT to touch:** `worktree-resolve-sdk-pr-195-comments/` (stale git worktree copy of the whole repo — never edit or read as reference); the non-linear runtime validation block (`base.py:100-143`) other than relying on it; `PermissionPolicy` plumbing; `AgentTool._serialize_context` string-flattening (it becomes partially redundant for same-config forks but removing it is out of scope).
- **`AggregateAgent.fork` strictness:** honor `name` (already does) and raise `ConfigurationError` (from `vidbyte/lib/errors`) listing the unsupported override keys instead of `**_overrides: Any` swallowing. Keep the rebuild behavior for the no-override case; `as_tool()`/`AgentTool` depend on it.

### Open Questions

1. **Prerequisite status:** has the stateful-tool aliasing fix (separate bug PR) landed by implementation time? If not, include the minimal clone-stateful-builtins-on-fork safeguard in this PR (fresh `CreateHandoffTool`/`AttachMcpServerTool` instances for the child; `AgentTool` instances re-bound per-child are acceptable only if the parent's binding is restored/unaffected — cloning is safer).
2. **Extra-toolsets registry:** the tool constructor accepts an optional `extra_toolsets: Mapping[str, Tools]` allow-list (named toolsets the model may request beyond the parent's subset). Ship in V1 or defer? Recommendation: ship the constructor parameter (cheap), document sparingly.
3. **Permission enum for the tool spec:** `SAFE` (consistent with `AgentTool`) vs `EXECUTE` (semantically honest — it runs a full agent). Recommendation: `SAFE`; revisit if permission policies start gating on it.
4. **Does `McpServerHandle` retain its originating `McpServerConfig`?** Determines whether attached-server carry needs config retention added at attach time. Verify in `vidbyte/tools/mcp/types.py` / `attach.py`.
5. **Should `fork()` default `include_history` stay `False`?** This design keeps the dev-facing default unchanged (backward compat) while the tool defaults `history_mode="full"` (a "fork of the conversation" naturally carries it). Confirm no objection.
6. **Output schema as a Tier 1 (model-facing) param later?** V1 keeps `output_schema` dev-only; promoting it means letting the model author JSON Schemas. Deferred decision.

---

## 4. Goals & Non-Goals

### Goals

- Extend `BaseAgent.fork()` so every interchangeable part (inventory in §6/§8) can be overridden at fork time, including run-state carry (history modes, handoffs, tool-call contexts), model/runner swap, trace option, output schema, loop settings, runtime type, handoff spec, and MCP attachment carry.
- Give every fork a fresh `run_id` with parent lineage recorded in metadata.
- Add `Tools.subset(names)` to the catalog.
- Create the `ForkConversationTool` builtin (`fork_conversation`) exposing the Tier 1 parameter set, following the `CreateHandoffTool` bind-agent pattern, wired into `_bind_agent_tool_context` and exported from `vidbyte/tools/builtins/__init__.py`.
- Enforce the privilege-non-escalating invariant: name-subset tools, allow-listed models, parent-capped `max_iterations`, inherited permission policy, fork-depth cap (default 2).
- Run forks synchronously inside the tool call; return the child's reply (+ child run_id, lineage metadata) as the `ToolResult`.
- Make `AggregateAgent.fork` raise on unsupported overrides instead of silently ignoring them.
- Fix `vidbyte/trace/README.md:45` to be truthful (rides along with the `trace_option` param).
- Comprehensive tests: per-part override isolation, parent-untouched-after-fork, history modes, lineage, depth cap, disallowed-model rejection as `ToolResult.error`, MCP carry, fork inside an in-flight tool loop.

### Non-Goals

- Fixing the pre-existing fork bugs as standalone work (separate PR; see Open Question 1 for the contingency).
- Detached/parallel/fire-and-forget forks and any join primitive.
- Model-facing control of permission policy, credentials, or free-form model strings.
- A `Session`/`RunState` extraction refactor of `BaseAgent`.
- Removing or redesigning `AgentTool`'s string-flattened context delegation.
- Per-part permission gating (the rejected many-tools design).
- Cross-process or persisted forks (everything is in-memory, same event loop).

---

## 5. Background & Context

- **Why now:** the SDK is growing multi-agent orchestration (AgentTool delegation, handoffs, aggregation) and the missing primitive is an agent's ability to branch *itself* — try an alternate persona, isolate a noisy subtask, get a second opinion with a different toolset — without a dev pre-wiring every variant.
- **Current state:** `BaseAgent.fork()` (`vidbyte/agents/base.py:362`) is constructor-replay covering config only; `include_history` is the sole run-state carry and defaults off. Call sites: `AgentTool.execute` (`vidbyte/tools/agent_tool.py:50`, zero overrides), `evals/runner.py:124` (rename only), README examples (one of which — `trace_option` — doesn't actually work). `AggregateAgent.fork` ignores all overrides. Nothing model-facing forks. Run state beyond history (handoffs, tool-call contexts, MCP attachments, last-run artifacts) never crosses a fork. Parent and child share `run_id`.
- **Problem solved:** "fork the current conversation with different interchangeable parts" — for devs via richer `fork()` kwargs, and for the agent itself via one parameterized builtin tool.
- **Dependencies:** the stateful-tool aliasing bug fix (separate work, see Open Question 1); no new libraries.

---

## 6. Requirements

The interchangeable-parts inventory is normative. **Tier 1** = model-facing tool parameters; **Tier 2** = dev-facing `fork()` overrides; **Tier 3** = locked.

1. `fork_conversation` (Tier 1) MUST accept: `prompt` (string, **required** — the fork's seed user message), `system_prompt` (string, optional), `tool_names` (array of strings, optional — child tool set as a by-name subset of the parent's catalog plus any dev-configured extra toolsets), `history_mode` (`"full" | "none" | "last_n"`, default `"full"`), `last_n` (int, required iff `history_mode="last_n"`), `model` (string, optional — must be in the dev-configured allow-list), `temperature` (number, optional, bounded 0–2), `max_iterations` (int, optional — capped at the parent's effective value), `name` (string, optional child label), `purpose` (string, optional — stored to child metadata for trace observability).
2. `BaseAgent.fork()` (Tier 2) MUST gain, preserving `None`-means-inherit: `prompt` is NOT added to `fork()` (it belongs to the runner call, i.e. `fork(...).arun(prompt)`); new params: `history: Sequence[AgentMessage] | None` (explicit transcript override; wins over `include_history`), `add_tools: Sequence[object]`, `drop_tools: Sequence[str]` (deltas composed via `Tools.add`/`without` semantics; mutually composable with full `tools=` replace, applied after it), `trace_option: TraceOption | None`, `include_run_state: bool = False` (copies `handoffs` list + `_tool_call_contexts`; `last_prompt/last_reply/last_trace/_behavior_view` always reset), `output_schema`, `agent_loop_settings`, `handoff`, `runtime`, `run_id: str | None` (default: generate a fresh id), `model_name`/`provider`/`temperature`/`runner_options` overrides (triggering the runner rebuild per the hint in §3), and `mcp: bool = True` (carry MCP attachment configs as pending; `False` opts out).
3. Every fork MUST get a distinct `run_id` unless explicitly overridden, and MUST record `metadata["forked_from"]` (parent identity) and `metadata["fork_depth"]` (parent depth + 1).
4. `Tools.subset(names)` MUST return a new catalog containing exactly the named tools, in catalog order, erroring on unknown names.
5. `ForkConversationTool` MUST: follow the bind-agent builtin pattern; be wired in `_bind_agent_tool_context`; translate its JSON args into a single `fork()` call; run `await child.generate_reply(prompt)`; return the child's reply content with metadata `{child_run_id, forked_from, fork_depth, name}`; convert ALL failures (validation, disallowed model, unknown tool names, constructor `ConfigurationError`, child execution errors) into `ToolResult.error` — never raise.
6. The tool constructor MUST accept dev-side configuration: `allowed_models: Sequence[str] = ()` (empty = model swap disabled), `extra_toolsets: Mapping[str, Tools] | None = None`, `max_fork_depth: int = 2`.
7. Privilege non-escalation MUST hold: child tool set ⊆ parent catalog ∪ extra_toolsets; child `max_iterations` ≤ parent's; permission policy, API key, provider credentials inherited verbatim and not parameterizable on the tool; depth cap enforced before any child construction.
8. Fork MUST NOT mutate the parent: parent's history, tools, bindings, MCP handles, and run-state fields are byte-identical before/after any fork (test-enforced).
9. MCP carry: child receives parent's pending + attached server *configs* as pending configs; child never shares live handles or MCP-bridged tool instances with the parent; parent's MCP-sourced tools are excluded from the child's copied tool items.
10. `AggregateAgent.fork` MUST raise `ConfigurationError` naming the unsupported override keys (all except `name`).
11. Non-linear runtime conflicts (middleware/trace/algorithm vs MCTS/actor) surface as `ToolResult.error` through the tool and as the existing `ConfigurationError` through `fork()`.
12. `vidbyte/trace/README.md` fork example MUST execute successfully after this change.
13. New/changed modules carry Context Protocol Header docstrings; `ForkConversationTool` exported from `vidbyte/tools/builtins/__init__.py`.

---

## 7. Non-Functional Requirements

- **Performance:** fork construction is in-memory object copying — no I/O added; the dominant cost is the child's own model calls. No measurable overhead (>1ms-scale) added to agents that don't use forking.
- **Scalability/concurrency:** child runs in the same event loop via `await`; no new threads/processes. Depth cap bounds recursive blow-up; document that a fork inside a parallel-tool-call batch shares the loop cooperatively.
- **Security:** privilege-non-escalation invariant (Requirement 7) is the security model; model/tool selection strictly allow-listed; no credential parameters anywhere model-facing.
- **Observability:** fresh `run_id` + `forked_from` + `fork_depth` + `purpose` in metadata make fork trees reconstructable from traces; the child inherits the parent's tracer so spans land in the same sink; tool result metadata carries child identity.
- **Reliability:** the tool never raises — every failure is a structured `ToolResult.error` so the parent loop continues; child failure must not corrupt parent state (test-enforced).
- **Backward compatibility:** all new `fork()` params default to inherit/off; existing call sites (`AgentTool`, evals runner) behave identically except forks now get distinct `run_id`s (flag this in the PR description in case anything keyed on shared run_ids — audit found nothing).

---

## 8. High-Level Design

The change has three layers sharing one mental model: an agent is *config* (prompt, model, tools, middleware, settings) plus *run state* (transcript, handoffs, tool-call contexts, MCP connections), and a fork is `(parent config ⊕ overrides) + transform(parent run state)`.

**Layer A — the fork engine** (`vidbyte/agents/base.py`, plus `vidbyte/tools/catalog.py` for `Tools.subset`). `fork()` grows the Tier 2 override set. Internally it resolves in stages: (1) tool set = replace-or-inherit, then `add_tools`, then `drop_tools`, always excluding parent MCP-bridged tools; (2) runner = inherit unless any model-ish override present, in which case pass `runner=None, runners={}` so the child lazily rebuilds from the new `runner_config` via `_runner_for_modality`; (3) run state = history per `history`/`include_history`, handoffs/tool-call-contexts per `include_run_state`, MCP configs re-queued as pending per `mcp=True`; (4) identity = fresh `run_id`, lineage + depth stamped into merged metadata. `AggregateAgent.fork` becomes strict. Plain English: the copy function stops forgetting the agent's memory and connections, lets you swap any single part, and every copy gets its own name tag pointing back at its parent.

**Layer B — the model-facing tool** (new `vidbyte/tools/builtins/fork/fork.py` + `__init__.py`, export in `vidbyte/tools/builtins/__init__.py`, binding branch in `BaseAgent._bind_agent_tool_context`). `ForkConversationTool` is a bind-agent builtin like `CreateHandoffTool`: dev constructs it (optionally with `allowed_models`, `extra_toolsets`, `max_fork_depth`) and adds it to the agent's tools; the agent binds itself on registration. Its JSON schema exposes exactly the Tier 1 params; its description teaches the model when forking beats continuing (isolate a subtask, alternate persona, second opinion without polluting the main context, cheaper model for exploration). `execute()` = validate → enforce allow-lists/caps/depth → translate names through `Tools.subset` → one `fork()` call → `await child.generate_reply(prompt)` → child's answer as `ToolResult.success` with lineage metadata. Plain English: the dev hands the agent a button labeled "spin up a modified copy of yourself, give it this task, and report back," having decided in advance exactly which modifications the button permits.

**Layer C — propagation and proof** (tests in `tests/test_agent_base.py` + new `tests/test_fork_tool.py`, README fix in `vidbyte/trace/README.md`, optional demo script under `scripts/`). Tests pin the invariants: each part overridable in isolation, parent untouched, history modes, lineage ids, depth cap, disallowed model → `ToolResult.error`, MCP carry without handle sharing, fork mid-tool-loop safety.

```
parent BaseAgent ── run loop ── model emits tool call: fork_conversation{prompt, parts...}
      │                                   │
      │                     ForkConversationTool.execute
      │                    (validate → allow-lists → depth)
      │                                   │
      ├── config ⊕ overrides ──► BaseAgent.fork(...)  ──► child BaseAgent
      └── run state ─ transform ─┘   (fresh run_id,          │
          (history mode, handoffs,    forked_from,      await child.generate_reply(prompt)
           MCP configs re-queued)     depth+1)                │
                                                              ▼
      parent loop continues ◄── ToolResult(child reply + lineage metadata)
```

Key decisions carried into this design: one parameterized tool (user-confirmed); synchronous V1; privilege-non-escalation as the security model; fresh-identity-with-lineage as the observability model; config/run-state separation as the implementation model.

---
