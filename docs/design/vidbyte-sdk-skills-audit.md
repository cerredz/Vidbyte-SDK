# Design Doc: Vidbyte SDK Skills Audit & Update

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-04
**Last Updated:** 2026-06-04

---

## 1. Overview

A large batch of PRs has landed on `main` of the Vidbyte SDK (local `main` was 32 commits behind origin before this work; it is now fast-forwarded and up to date). These PRs changed package structure, moved context compaction from the **tool layer** to the **middleware layer**, replaced the public **strategy** layer with **agent runtimes + context-window algorithms**, added new subsystems (handoffs, context primitives, memory tools, evals, tracing, new providers), and extended the prompt catalog. The `skills/` documentation has drifted out of sync with the code: several skill files describe APIs, file paths, prompt families, and providers that no longer match the repository. This change audits every skill file against current source and brings each one back into accuracy, and adds new skill files for high-value subsystems that currently have zero skill coverage.

---

## 2. Goals & Non-Goals

### Goals

- Bring **every** existing skill file under `skills/` into agreement with current `vidbyte/` source: file paths, import paths, API signatures, prompt families/enums, provider lists, package layout, and conceptual model.
- Correct the documented middleware API everywhere (the real API is the 9-hook `MiddlewareContext` / `MiddlewareDecision.continue_()` model, not the `ALLOW/BLOCK/SKIP` 4-hook model still shown in three files).
- Reflect the compaction migration from tool → middleware consistently across all skills.
- Reflect the strategy → agent-runtime/context-algorithm architecture shift in the SDK reference skills.
- Add new skill files for subsystems with no coverage where the existing skill structure supports them (evals, memory tools, context primitives/manager).
- Update `skills/sdk/update-skill-files.md` so the change→file matrix matches the current skill set and conventions, keeping it usable for the next contributor.

### Non-Goals

- No changes to `vidbyte/` runtime code, tests, or behavior. This is documentation-only.
- No rewrite of design docs under `docs/design/` (other than adding this one).
- No new SDK features, providers, tools, or APIs.
- No change to the README beyond fixing any concrete inaccuracies discovered (README accuracy is in scope only if a factual error is found; a full README rewrite is out of scope).
- Not changing `skills/creating-system-prompts.md` (it is generic prompt-writing guidance with no code references — verified accurate) or `skills/mcp-server/*` (verified accurate against `vidbyte/mcp_server/`).

---

## 3. Background & Context

The repo is a Python-native agent framework (`vidbyte/`), `>=3.11`, `unittest`-based, with a `skills/` directory that doubles as both contributor documentation and agent-facing skill files. Skills are grouped:

- `skills/sdk/` — SDK structure + rules + the "how to update skills" meta-guide.
- `skills/vidbyte-sdk/` — deep per-subsystem references (middleware, pipelines, handoff, context-window algorithms, prompts, context templates, algorithm→tool).
- `skills/vidbyte-sdk-doc/` — the single exhaustive reference.
- `skills/usage/` — task-oriented how-tos (create agent/tool/pipeline, import prompt, available tools/features).
- `skills/agent-runtimes/`, `skills/mcp-server/`, `skills/docs/`, plus `skills/creating-system-prompts.md`.

The merged PRs introduced these **ground-truth** changes (verified against current source during the audit):

1. **Compaction moved to middleware.** Implementation lives in `vidbyte/middleware/compaction/` (`base.py`, `context_compaction.py`, `engine.py`, `strategies.py`) and is re-exported through `vidbyte/middleware/builtins/context_compaction.py`. Public middleware: `ToolResultCompactionMiddleware`, `MessageHistoryCompactionMiddleware`, `SummaryCompactionMiddleware`. The legacy `ContextCompactionTool` still exists under `vidbyte/tools/builtins/context/` but is explicitly legacy/manual.
2. **Middleware API is the 9-hook model.** `AgentMiddleware` (in `vidbyte/middleware/base.py`) exposes `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, `after_run` — each `async def hook(self, ctx: MiddlewareContext) -> MiddlewareDecision`, returning `MiddlewareDecision.continue_()/sleep()/deny_tool()/retry()/abort()`. There is **no** `ALLOW/BLOCK/SKIP` and **no** `MiddlewareBlockedError`. `skills/vidbyte-sdk/middleware.md` already documents this correctly; three other files still show the old model.
3. **Strategy layer replaced.** `vidbyte/strategies/` no longer exists. `VidbyteSDK` no longer exposes `sdk.strategies`; the namespace clients are `agents`, `harnesses`, `tools`, `providers`. Public Strategy classes (`ChainOfThoughtStrategy`, `ReActStrategy`, `MultiAgentConsensusStrategy`, …) are no longer exported from `vidbyte`. Execution paradigms are now **agent runtimes** (`vidbyte/agents/runtimes/`: linear, search/MCTS, actor) selected via `runtime=AgentRuntimeType.<X>`, plus **context-window algorithms** (`ContextWindow.preset.<name>` e.g. reflexion, trajectory checkpoints, multi-provider grader). `StrategyResult` survives as an internal result dataclass (`vidbyte/lib/dataclasses/strategies.py`) used by runtimes/pipelines.
4. **Context primitives became a package.** `vidbyte/context/primitives.py` → `vidbyte/context/primitives/` (`base.py`, `checkpoints.py`, `documents.py`, `records.py`, `tasks.py`).
5. **Handoff subsystem added.** `vidbyte/context/handoff/`, `vidbyte/context/handoffs.py` (compat re-export), `vidbyte/agents/handoff.py`, prompt assets under `vidbyte/prompts/prompts/handoff/`. Documented by `skills/vidbyte-sdk/handoff.md` (verified accurate).
6. **New tool categories.** `vidbyte/tools/builtins/` now also has `context_primitives/` (`ContextUpsertTool`, `ContextListTool`, `ContextRemoveTool`), `memory/` (Cognee/Letta/Mem0/Supermemory/Zep tool families), `mcp/`, and standalone `reflexion.py` (`ReflexionTool`) and `trajectory_checkpoint.py` (`TrajectoryCheckpointTool`).
7. **New providers.** `ModelProvider` now has 10 members: `OPENAI, ANTHROPIC, GEMINI, XAI, DEEPSEEK, GLM, MINIMAX, OPENROUTER, ELEVENLABS, PLAYAI`. Provider adapters added: `OpenRouterProvider`, `ElevenLabsProvider`, `PlayAIProvider`. Provider exports also include `audio`/`embedding` capability selectors.
8. **Prompt catalog changed.** The actual `Prompt` enum (`vidbyte/lib/enums/prompts.py`) has 34 members across 13 families: `agentic_loop, handoff, context_engineering, expert_prompting, goals, mimic_behavior, reflexion, prompt_engineering, evals, multi_provider_agentic_grader, templates, actor_runtime, trajectory_checkpoints`. The prompt families documented in `skills/usage/import_prompt.md` and `skills/vidbyte-sdk-doc/SKILL.md` (`chain_of_thought, tree_of_thoughts, vmao, agentic_rag, …`) **no longer exist** — those docs are stale and their direct-import examples would raise `ImportError`.
9. **MapReducePipeline added.** `vidbyte/pipelines/map_reduce.py`. Already documented in `available_features.md` and `create_pipeline.md`, but **missing** from `skills/vidbyte-sdk/pipelines.md` (which still says pipelines do "not … reduce").
10. **New subsystems with zero skill coverage:** `vidbyte/evals/` (graders, runner, suite, registry) and `vidbyte/trace/` (Trace, debug, continual).

---

## 4. Requirements

### Functional Requirements

1. Every `from vidbyte ...` / `from vidbyte.* import ...` example in every skill file must resolve against current source.
2. Every relative-link file path (`[text](path)`) in every skill file must point to an existing file.
3. Every middleware example/section must use the real 9-hook `MiddlewareContext`/`MiddlewareDecision` API.
4. Every reference to context compaction must present it as middleware (`vidbyte/middleware/...`), with `ContextCompactionTool` noted as legacy only.
5. The SDK reference skills (`skills/sdk/SKILL.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/vidbyte-sdk-doc/SKILL.md`) must not present `vidbyte/strategies/`, `sdk.strategies`, or removed Strategy classes as current API; they must describe agent runtimes + context-window algorithms instead.
6. `ModelProvider` lists must include all 10 providers.
7. `skills/usage/import_prompt.md` must list the actual 13 families / 34 prompts with correct enum names and direct-import names.
8. `skills/vidbyte-sdk/pipelines.md` must document `MapReducePipeline` and stop calling reduce a "future" topology.
9. Package-layout trees must show `vidbyte/context/primitives/` as a package, `vidbyte/pipelines/map_reduce.py`, `vidbyte/middleware/compaction/`, `vidbyte/context/handoff/`, and the current built-in tool categories.
10. `skills/sdk/update-skill-files.md` must reference only skills that exist and the current conventions; add change-types for new subsystems where helpful.
11. New skill files (evals, memory tools, context primitives/manager) must be added under the existing structure and registered in the relevant reference tables.

### Non-Functional Requirements

- **Accuracy over completeness:** when source and a doc disagree, source wins. No invented APIs.
- **Internal consistency:** counts (prompt families, providers, tool categories, middleware) must agree across all files that state them.
- **No behavioral risk:** documentation-only; zero runtime/test impact.
- **Reviewability:** logically grouped commits (one theme per commit) so the PR is auditable.
- **Verifiability:** a script checks links resolve and documented imports import.

---

## 5. High-Level Design

The work is a documentation reconciliation pass plus targeted additions. Approach:

1. **Establish ground truth** (done during audit): enumerate real module paths, public exports (`vidbyte/__init__.py`), middleware hooks/decisions, provider enum, prompt enum, tool builtins, pipeline modules, context layout.
2. **Edit existing skills** to match ground truth, file by file, preserving each file's voice/structure and only changing what is factually wrong or stale.
3. **Add new skills** for evals, memory tools, and context primitives/manager — modeled on the structure of existing `skills/vidbyte-sdk/*.md` references, and cross-linked from `skills/sdk/SKILL.md` and `skills/vidbyte-sdk/SKILL.md`.
4. **Refresh the meta-guide** (`update-skill-files.md`) so future code changes map to the now-correct skill set.
5. **Verify** with a script that resolves every relative link and imports every documented public symbol, then run `python -m compileall vidbyte` to confirm no doc edit accidentally touched code.

Data flow is purely editorial: source code (authority) → skill markdown. No system components change.

```
[vidbyte/ source]  --audit-->  [ground-truth tables]  --edit-->  [skills/*.md]
                                                         \--add--> [new skills/*.md]
                                          [verify script] --reads--> both
```

Key decisions:

- **`vidbyte-sdk-doc/SKILL.md` is reworked, not deleted.** It is the exhaustive reference; the Strategies / Multi-Agent / Prompt-families / Package-map / Provider sections are rewritten to the current model. This is the single largest edit.
- **Keep `StrategyResult` language where still true.** Runtimes return `StrategyResult`; we keep that internal contract documented but remove public `Strategy`-class and `sdk.strategies` claims.
- **`ContextCompactionTool` stays documented as legacy**, not deleted from docs, because it still exists in source.

---

## 6. Detailed Design

Each subsection is one skill file (or new file). "What's wrong / what to do" is the concrete edit list.

### 6.1 `skills/sdk/SKILL.md`
**Type:** Modified

- **Middleware section (lines ~38–100):** replace the 4-hook table (`before_tool_call/after_tool_call/before_model_call/after_model_call`) and `MiddlewareDecision ALLOW/BLOCK/SKIP` + `MiddlewareBlockedError` with the real 9-hook `MiddlewareContext`/`MiddlewareDecision.continue_()/abort()/deny_tool()/retry()/sleep()` model. Replace the `RateLimitingMiddleware` example (uses old `before_tool_call(self, call)` returning `BLOCK`) with one matching `middleware.md`. Point readers to `skills/vidbyte-sdk/middleware.md` as the authority.
- **Framework Boundaries table:** the `Strategy` row lists removed classes. Re-frame as **Runtime** (agent execution paradigm: linear/search/actor) and **Context-Window Algorithm** (reflexion, trajectory checkpoints, grader) rather than `ChainOfThoughtStrategy` etc.
- **Core Use Cases:** "context compaction" listed under built-in tools → move to middleware; "Access 15 prompt families" → 13 families; "Reasoning strategies: chain-of-thought…" → reframe around context-window algorithms + prompt families + runtimes.
- **Built-in tool categories rule (line ~200):** currently `code_search, editing, context, calculator, code_execution, document_retrieval, filesystem`. Add `context_primitives`, `memory`, `mcp`, and the standalone `reflexion`/`trajectory_checkpoint` tools.
- **Package Structure tree:** add `vidbyte/middleware/compaction/`, `vidbyte/context/handoff/`, `vidbyte/context/primitives/` (package), `vidbyte/pipelines/map_reduce.py`, `vidbyte/evals/`, `vidbyte/agents/runtimes/`, `vidbyte/agents/algorithms/`; remove `vidbyte/strategies/`.
- **Rules referencing `vidbyte/strategies/`:** update to `vidbyte/agents/runtimes/` and context algorithms.
- **Provider line:** add openrouter/elevenlabs/playai.
- **Usage / Developer Reference tables:** add rows for new skills (evals, memory tools, context primitives) once created; add `agent-runtimes`, `handoff`, `context-window` skill references.

### 6.2 `skills/sdk/update-skill-files.md`
**Type:** Modified

- Replace the "Add a New Strategy Type" / "Add a New Multi-Agent Strategy" change-types with **"Add a New Context-Window Algorithm"** (point to `adding-context-window-algorithms.md`) and **"Add a New Agent Runtime"** (point to `agent-runtimes/SKILL.md`).
- Add change-types: **"Add a New Middleware Built-in"** already exists — fix its target sections (now `available_features.md` middleware + `middleware.md` catalog + `sdk/SKILL.md`). Add **"Add a Compaction Strategy/Middleware"** pointing at `middleware.md` §5.1. Add **"Add a Memory Tool Provider"** and **"Add a Context Primitive Tool"** pointing at the new skills. Add **"Add an Eval Grader"** pointing at the new evals skill.
- Update the **"Add a New Prompt Family"** row: prompt-family count is now 13; the strategy-prompt file paths it lists (`vidbyte/prompts/strategies/...`) must be verified against the actual prompt export modules and corrected.
- Update **Verification Checklist**: provider enum is 10 entries; the "Usage Skill Files table" / "SDK Developer Reference table" must list the new skills.

### 6.3 `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

- **Current Layout tree:** `context/primitives.py` → `context/primitives/` package; add `context/handoff/`, `context/handoffs.py`, `context/compaction.py`, `context/runtime.py`, `context/templates/`; add `pipelines/map_reduce.py`; add `middleware/compaction/`; remove `strategies/` block (replace with note that runtimes live in `agents/runtimes/`).
- **Rules:** the line "current approved categories are `code_search`, `editing`, and `context`" → full current list (add `context_primitives`, `memory`, `mcp`, `calculator`, `code_execution`, `document_retrieval`, `filesystem`, plus `reflexion`/`trajectory_checkpoint` standalone tools). Update `vidbyte/strategies/` rules → `vidbyte/agents/runtimes/`. Keep handoff rule (accurate). Add reference rules for the new skills.

### 6.4 `skills/vidbyte-sdk/middleware.md`
**Type:** Modified (light)

- Core API is correct. Fixes: the catalog says "13 built-in middlewares" but the package now also ships the 3 compaction middlewares — clarify the count or add a line that compaction middlewares (covered in §5.1) bring the public total higher. Confirm every `Module:` path (`vidbyte.middleware.builtins.<x>`) still resolves (they do via `builtins/__init__.py`); note compaction lives in `vidbyte/middleware/compaction/` re-exported through `builtins/context_compaction.py`. Verify `MiddlewareContext`/`MiddlewareDecision` import path used in the custom example (`vidbyte.lib.dataclasses.middleware`) — confirm during implementation.

### 6.5 `skills/vidbyte-sdk/pipelines.md`
**Type:** Modified

- Add a **MapReducePipeline** subsection under Topology Types (constructor `map_stages=[...], reduce_stage=...`, default separator `"\n\n---\n\n"`, raises `PipelineExecutionError` if `map_stages` empty), mirroring `create_pipeline.md`.
- **Module layout** block: add `map_reduce.py`.
- **"What pipelines are NOT":** the bullet "Pipelines do not retry, vote, or reduce — those are future topology types" is now wrong about reduce; revise to "do not retry or vote (future); map-reduce is supported via `MapReducePipeline`."
- **Error Handling table:** add MapReduce empty-`map_stages` row; note `MapReducePipeline` uses `asyncio.gather` like Parallel.

### 6.6 `skills/vidbyte-sdk/context-algorithm-to-tool.md`
**Type:** Modified

- Every reference to `vidbyte/context/primitives.py` (Step 1, §6 File Placement Rules, §7 "`_truncate_text` is in `primitives.py`") → the `vidbyte/context/primitives/` package. Identify the correct submodule for each primitive (`TrajectoryCheckpointContextItem`, `ReflexionContextItem`, `_truncate_text`) and update the guidance to "add to the appropriate module under `vidbyte/context/primitives/` and export from `vidbyte/context/primitives/__init__.py`." Verify `ReflexionTool`/`TrajectoryCheckpointTool` file paths (`vidbyte/tools/builtins/reflexion.py`, `.../trajectory_checkpoint.py`) — confirmed present.

### 6.7 `skills/vidbyte-sdk/context-window-templates.md` & `adding-context-window-algorithms.md`
**Type:** Modified (verification + targeted fixes)

- These reference `vidbyte/context/algorithms/`, `vidbyte/agents/algorithms/`, `vidbyte/lib/templates/`, `vidbyte/context/templates/`, `vidbyte/context/runtime.py`, `ContextWindow.preset.*` — verify each path/symbol against source and fix any drift. The `context-window-templates.md` File Reference and instrumentation-point tables must match current file locations (e.g. `vidbyte/context/algorithms/trajectory_checkpoints.py`). Confirm the `from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm` import in the §8 example still resolves; correct if the symbol moved.

### 6.8 `skills/usage/available_features.md`
**Type:** Modified

- **Middleware section:** replace 4-hook `ALLOW/BLOCK/SKIP` table + `CustomGuardMiddleware` example with the real 9-hook API; replace the vague "Logging/Rate limiting/Content filtering/Validation" built-in list with the real catalog (or link to `middleware.md`), and add the compaction middlewares.
- **Provider Support:** add `OPENROUTER`, `ELEVENLABS`, `PLAYAI` (and fix model descriptions as needed).
- **Prompt Collection:** "15 prompt families" → 13; the example enum `Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT` no longer exists — use a real one (e.g. `Prompt.REFLEXION_REFLECT_PROMPT`, `Prompt.GOALS_GOAL_PROMPT`, or `Prompt.HANDOFF_SYSTEM_PROMPT`).
- **Tools/Built-in Tools:** mention compaction is middleware now; add context-primitives + memory tool categories.
- **Budgets & Permissions:** presets are `TIGHT/BALANCED/EXPLORATORY/UNBOUNDED` and `SANDBOXED/READ_ONLY/TOOLS_ONLY/TRUSTED` (the doc omits `UNBOUNDED`/`SANDBOXED`).

### 6.9 `skills/usage/available_tools.md`
**Type:** Modified

- **Context section:** reframe `ContextCompactionTool` as legacy/manual; point to compaction middleware (`middleware.md` §5.1) as the recommended path.
- **Add Context Primitives section:** `ContextUpsertTool`, `ContextListTool`, `ContextRemoveTool` from `vidbyte.tools.builtins.context_primitives`.
- **Add Memory section:** Cognee/Letta/Mem0/Supermemory/Zep tool families from `vidbyte.tools.builtins.memory`.
- **Add Context Algorithm Tools:** `ReflexionTool`, `TrajectoryCheckpointTool`.
- Verify the filesystem import path note `vidbyte/lib/tools/filesystem/backends/` and the `@vidbyte_tool`/`ToolRegistry` lines against source.

### 6.10 `skills/usage/create_agent.md`
**Type:** Modified

- **Adding Middleware example (lines ~96–115):** `LoggingMiddleware.before_model_call(self, agent, prompt)` returning `MiddlewareDecision.ALLOW` is wrong — rewrite to `async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ... return MiddlewareDecision.continue_()`.
- **Constructor signature:** verify against `BaseAgent.__init__` — add `runtime: AgentRuntimeType` and any actor params (`dynamic_actors`, `max_loop`, `termination_mode`, `worker_model`) if they are real constructor params; confirm `context_items`, `context_manager`, `algorithm`, `handoff` params. Provider string list should include the new providers.

### 6.11 `skills/usage/import_prompt.md`
**Type:** Modified (substantial rewrite of the listing)

- Replace the entire "Complete Prompt Listing" and "Direct String Imports" with the **actual** 13 families / 34 enum members from `vidbyte/lib/enums/prompts.py`. Header counts ("30+ prompts across 16 prompt families") → real counts. Every direct-import example must be a real generated name (verify against `Prompts().import_names()`).

### 6.12 `skills/usage/create_agents.md`
**Type:** Modified (light)

- Verify `AgentRegistry` API (`register/get/all/cards/find`) against `vidbyte/agents/` — `AgentRegistry` is exported (confirmed). Remove/replace any lingering "strategy" framing; fix the typo "its own name, system prompt, model, tools, and tools."

### 6.13 `skills/usage/create_pipeline.md`, `create_tool.md`, `create_agent_with_tools.md`
**Type:** Modified (verification only; likely minor)

- `create_pipeline.md`: already covers MapReduce; just verify `run_sync()`/`BaseStrategy.run()` reference wording (BaseStrategy is internal now — reword to `BasePipeline`/runtime).
- `create_tool.md`, `create_agent_with_tools.md`: verify imports (`PermissionPolicy` import in the example is used without import — add it), permission preset names, and `add_tool` API. Mostly accurate.

### 6.14 `skills/vidbyte-sdk-doc/SKILL.md`
**Type:** Modified (largest single edit)

- **Repository Snapshot / Verification:** `python -c "... print(type(sdk.strategies).__name__)"` is broken (`sdk.strategies` gone). Replace with a valid check (e.g. `sdk.agents`).
- **Package Map:** remove `strategies/`; add `agents/runtimes/`, `agents/algorithms/`, `context/handoff/`, `context/primitives/` (package), `context/compaction.py`, `context/templates/`, `middleware/compaction/`, `evals/`, `trace/`, `pipelines/map_reduce.py`.
- **Public Import Surface:** reconcile against actual `vidbyte/__init__.py __all__` (133 entries) — remove the Strategy classes block; add handoffs (`Handoff`, `EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`, `HandoffAgent`), context-window algorithms (`ReflexionAlgorithm`, `TrajectoryCheckpointAlgorithm`, `MultiProviderAgenticGraderAlgorithm`, `InnerContextWindowAlgorithm`), new context items (`PlanContextItem`, `TrajectoryCheckpointContextItem`), `MapReducePipeline`, middleware exports.
- **Root SDK Client:** remove `sdk.strategies: StrategyClient`; clients are `agents/harnesses/tools/providers`.
- **Strategies / Multi-Agent Orchestration sections:** rewrite as **Agent Runtimes** (linear/search/actor, `AgentRuntimeType`, prebuilt actor personas) and **Context-Window Algorithms** (reflexion/trajectory/grader, `ContextWindow.preset`), cross-linking `agent-runtimes/SKILL.md` and `adding-context-window-algorithms.md`. Keep `StrategyResult` as the internal runtime result.
- **Prompt families:** replace the wrong 15-family list with the real 13 families.
- **Providers:** add openrouter/elevenlabs/playai adapters + audio/embedding selectors.
- **Context And Dataclasses:** `vidbyte/context/primitives.py` → package; add handoff/compaction/templates; verify each `ContextItem` dataclass name against the primitives package and `context/__init__.py` exports.
- **Test Suite Map:** reconcile against the current `tests/` directory (strategy-named tests likely renamed; new tests for handoff/compaction/runtimes/evals exist). Update the list to match actual files.
- **Design Doc Index:** add the new design docs present in `docs/design/` (handoff, compaction-middleware, context-algorithms-as-tools, etc.).
- **Common Change Playbooks / Guardrails:** replace "Adding a strategy" with "Adding a context-window algorithm" + "Adding an agent runtime"; fix `vidbyte/strategies/multi_agent/` guardrail.

### 6.15 NEW: `skills/vidbyte-sdk/evals.md`
**Type:** New file

- Document `vidbyte/evals/` : `EvalSuite`/`suite.py`, `runner.py`, `registry.py`, graders (`contains`, `exact_match`, `json_schema`, `llm_judge`, `regex_match`, `rubric`), `client.py` (`sdk`/eval client surface), `base.py`, `types.py`, and the `evals` prompt family (`EVALS_LLM_JUDGE`, `EVALS_RUBRIC`). Include: what an eval/grader is, how to define a suite, how to run it, how to add a new grader (file placement + `__init__` export + tests), and verification commands. Structure mirrors `pipelines.md`/`middleware.md`. Cross-link from `sdk/SKILL.md` reference table and `update-skill-files.md`.

### 6.16 NEW: `skills/usage/memory_tools.md` (or `skills/vidbyte-sdk/memory-tools.md`)
**Type:** New file

- Document `vidbyte/tools/builtins/memory/`: the five provider families (Cognee, Letta, Mem0, Supermemory, Zep), their tool classes, import paths, required config/credentials posture (no secrets in docs), permission levels, and an attach-to-agent example. Add a row to `available_tools.md` and the reference tables.

### 6.17 NEW: `skills/vidbyte-sdk/context-primitives.md`
**Type:** New file

- Document the `vidbyte/context/primitives/` package + `ContextManager` + the model-callable `context_primitives` tools (`ContextUpsertTool`, `ContextListTool`, `ContextRemoveTool`) and how they relate to context-window algorithms (links `context-algorithm-to-tool.md`). Explains `place_after_system_prompt`/`place_after_tools`/`upsert`. Cross-link from `SKILL.md`.

> The exact filename/placement of the three new skills, and whether all three are added in this PR vs. a subset, is an **open question** (see §13) for approval.

---

## 7. Data Model Changes

N/A — documentation only, no schema, dataclass, or storage changes.

---

## 8. API Changes

N/A — no runtime API is added, modified, or removed. (Skill text is corrected to match APIs that already changed in prior merged PRs.)

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/vidbyte-sdk-skills-audit.md` | This design doc |
| MODIFY | `skills/sdk/SKILL.md` | Middleware API, strategy→runtime, tool categories, layout, providers, prompt count |
| MODIFY | `skills/sdk/update-skill-files.md` | Replace strategy change-types; add runtime/compaction/memory/eval/primitive change-types; fix counts |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Layout (primitives package, map_reduce, compaction, handoff), tool categories, strategy→runtime |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | Clarify built-in count incl. compaction; verify module paths |
| MODIFY | `skills/vidbyte-sdk/pipelines.md` | Add MapReducePipeline; fix "no reduce" claim; module layout; error table |
| MODIFY | `skills/vidbyte-sdk/context-algorithm-to-tool.md` | `primitives.py` → `primitives/` package paths |
| MODIFY | `skills/vidbyte-sdk/context-window-templates.md` | Verify/fix file-reference + import paths |
| MODIFY | `skills/vidbyte-sdk/adding-context-window-algorithms.md` | Verify/fix paths + symbols |
| MODIFY | `skills/usage/available_features.md` | Middleware API, providers, prompt count, presets, compaction |
| MODIFY | `skills/usage/available_tools.md` | Compaction-as-legacy; add context_primitives, memory, algorithm tools |
| MODIFY | `skills/usage/create_agent.md` | Middleware example API; constructor params (runtime, etc.); providers |
| MODIFY | `skills/usage/import_prompt.md` | Replace stale prompt families with real 13 families / 34 prompts |
| MODIFY | `skills/usage/create_agents.md` | Verify AgentRegistry API; remove strategy framing; fix typo |
| MODIFY | `skills/usage/create_pipeline.md` | Reword `BaseStrategy.run()` → pipeline/runtime |
| MODIFY | `skills/usage/create_tool.md` | Add missing imports; verify permission presets |
| MODIFY | `skills/usage/create_agent_with_tools.md` | Add missing `PermissionPolicy` import; verify |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Largest: strategy→runtime, prompt families, providers, primitives package, package map, public surface, test map, playbooks, verification |
| CREATE | `skills/vidbyte-sdk/evals.md` | New skill for `vidbyte/evals/` subsystem |
| CREATE | `skills/vidbyte-sdk/memory-tools.md` | New skill for memory tool providers |
| CREATE | `skills/vidbyte-sdk/context-primitives.md` | New skill for context primitives + ContextManager + tools |
| (none) | `skills/creating-system-prompts.md` | Verified accurate — no change |
| (none) | `skills/mcp-server/*.md` | Verified accurate vs `vidbyte/mcp_server/` — no change |
| (none) | `skills/agent-runtimes/SKILL.md` | Verified accurate vs `vidbyte/agents/runtimes/` — no change |
| (none) | `skills/docs/*.md` | Design-note style; accurate — no change |

**Counts:** CREATE 4 (1 doc + 3 skills), MODIFY 16, unchanged-but-verified 5 groups. (Per decision: no committed verification script — checks are run ad-hoc during implementation instead.)

---

## 10. Testing / Verification Plan

Because this is documentation, the "tests" are verification checks that the docs are factually true. Per decision, **no verification script is committed**; instead these checks are run ad-hoc (one-off shell/Python during implementation) and must all pass before the PR leaves draft.

### Verification Checks (run ad-hoc during implementation)

- **[Silent Failure] Broken relative links:** parse every `[text](relative/path)` in every `skills/**/*.md`; assert each resolves to an existing file. Catches dead cross-references (the most likely silent rot).
- **[Hidden Assumption] Documented imports actually import:** extract `from vidbyte... import X` and `from vidbyte.prompts import name` examples (the deterministic ones) and `Prompt.<NAME>` enum references; assert each symbol exists. Deliberately violates the assumption that "documented = real" — would have caught `chain_of_thought_reason_prompt`.
- **[Silent Failure] Stale-term scan:** grep all skills for forbidden stale tokens (`vidbyte/strategies/`, `sdk.strategies`, `MiddlewareBlockedError`, `MiddlewareDecision.ALLOW`, `MiddlewareDecision.BLOCK`, `context/primitives.py`, `ChainOfThoughtStrategy`); assert zero matches remain after edits. Catches a wrong answer that still "looks right."
- **[Edge Case] Empty/zero results:** if the link extractor finds 0 links or 0 imports in a file expected to have them, flag it (guards against a regex that silently matches nothing).
- **[Hidden Failure] Count consistency:** assert the prompt-family count stated in `sdk/SKILL.md`, `available_features.md`, and `import_prompt.md` all equal the real family count derived from the `Prompt` enum; same for `ModelProvider` member count across files. Catches one file fixed while another drifts.
- **[Hidden Assumption] Provider/middleware/tool lists are supersets of source:** assert every `ModelProvider` member and every public middleware in `middleware/__init__.__all__` appears in the docs that claim to enumerate them.

### Manual / QA Checks

1. Given the edited `sdk/SKILL.md`, when a reader copies the middleware example, then it matches `AgentMiddleware`'s real signature — [Hidden Assumption].
2. Given `import_prompt.md`, when every listed `Prompt.<X>` is looked up via `Prompts().get(...)`, then none raise `KeyError` — [Silent Failure].
3. Given `available_tools.md`, when each documented tool class is imported from its stated package, then all import — [Hidden Assumption].
4. Given the new `evals.md`, when the "add a grader" steps are followed against `vidbyte/evals/graders/`, then the file placement + `__init__` export instructions match the existing graders — [Edge Case: new file must mirror real structure].

### Gate

All ad-hoc verification checks above must pass and `python -m compileall vidbyte` must succeed (proves no code file was touched) before the PR leaves draft.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib (`pathlib`, `re`, `importlib`) | local | verify script | none |
| Vidbyte SDK package (local) | current `main` | import verification | none — read-only |

No network or external services.

---

## 12. Rollout & Deployment

- No feature flags. Not a breaking change (docs only).
- Single PR targeting `main`, opened as draft, body = this design doc.
- Rollback = revert the docs commit(s); zero runtime impact.
- Deployment order: N/A (no services).

---

## 13. Open Questions

- [ ] **New-skill scope:** add all three new skills (evals, memory tools, context primitives) in this PR, or only the highest-value subset (recommend: evals + memory tools now, context primitives folded into the existing `context-algorithm-to-tool.md` if preferred)?
- [ ] **New-skill placement:** `skills/vidbyte-sdk/` (reference style, recommended) vs `skills/usage/` (task style) for memory tools and context primitives?
- [ ] **`vidbyte-sdk-doc/SKILL.md` Test Suite Map:** rewrite fully to match current `tests/` (more accurate, larger diff) vs trim to only-verified entries (smaller diff)? Recommend full rewrite for accuracy.
- [ ] **README:** in scope to fix concrete factual errors if the audit finds any, or leave entirely to a follow-up? (Recommend: fix only outright-wrong statements if trivial.)
- [x] **Verification script:** RESOLVED — no committed script; checks run ad-hoc during implementation.
- [x] **New-skill scope:** RESOLVED (default) — add all three (evals, memory-tools, context-primitives), since adding missing skills was an explicit ask.

---

## 14. Alternatives Considered

### Alternative 1: Delete `vidbyte-sdk-doc/SKILL.md` and fold it into `sdk/SKILL.md`
- What: collapse the exhaustive reference into the structure skill.
- Why rejected: it is a distinct, deliberately exhaustive reference with its own `name:`/`description:` frontmatter (agent-discoverable). Removing it loses the "single complete map" entry point; rework is lower-risk than deletion.

### Alternative 2: Only fix the compaction tool→middleware change (the one the user explicitly named)
- What: minimal patch touching just compaction references.
- Why rejected: the user explicitly asked to cross-reference **every** skill; the audit found far larger drift (strategy layer removal, wrong prompt families, wrong middleware API) that would leave the docs broken if ignored.

### Alternative 3: Auto-generate skill reference sections from source
- What: build a generator that emits provider/prompt/tool tables from the code.
- Why rejected: out of scope and higher-risk; the skills are prose with judgment and examples, not just tables. A verification script (not a generator) gives most of the safety with none of the lock-in. Could be a future follow-up.

---

END OF DESIGN DOC
