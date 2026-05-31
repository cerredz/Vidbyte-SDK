# Design Doc: Remove Strategies

**Status:** Approved
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

Remove the entire `vidbyte/strategies/` abstraction layer from the SDK. This includes all strategy implementation classes (ChainOfThought, ReAct, Reflexion, etc.), the StrategyClient namespace, StrategyTool, strategy prompt bundles, strategy-only prompt assets, strategy test files, strategy design docs, strategy references in skills documentation, and the strategy section of the README. The core agent runtime continues to work — agents without a strategy (the default, direct tool-loop path) are unaffected. Strategy-named types that are structurally shared with the core runtime (`StrategyResult`, `StrategyContext`) are renamed to agent-neutral equivalents.

---

## 2. Goals & Non-Goals

### Goals
- Delete `vidbyte/strategies/` and every `.py` file inside it
- Delete `vidbyte/tools/strategy_tool.py`
- Delete `vidbyte/prompts/strategies/` and every `.py` file inside it
- Delete strategy-only prompt JSON assets (`chain_of_thought.json`, `step_back.json`, etc.) from `vidbyte/prompts/prompts/`
- Remove `strategy` / `strategies` constructor parameters from `BaseAgent`
- Remove `StrategyClient` from `VidbyteSDK` (`sdk.strategies`)
- Remove all strategy exports from `vidbyte/__init__.py` and sub-packages
- Remove `StrategyExecutionError` and `StrategyConfigurationError` from errors
- Rename `StrategyResult` → `AgentResult` (used by AgentRuntime as a neutral result container)
- Rename `StrategyContext` → remove it (empty subclass of `BaseContext`; usages replaced with `BaseContext`)
- Rename `strategy_metadata` field in `BaseContext` → `run_metadata`
- Remove `VMAOContext` (extends deleted `StrategyContext`, only used by deleted VMAO strategy)
- Remove strategy-related entries from `Prompt` enum and corresponding JSON assets
- Remove 7 strategy test files
- Remove 3 strategy design docs
- Update README to remove strategy chain sections
- Update skill files to remove strategy content

### Non-Goals
- Do not change the core agent tool loop runtime (`AgentRuntime`)
- Do not change `BaseAgent.run()`, `BaseAgent.arun()`, `BaseAgent.generate_reply()` behaviour for tool-using agents
- Do not change pipelines, middleware, tools, evals, or context subsystems
- Do not remove prompt assets that are used by non-strategy features (`agentic_loop.json`, `evals.json`, `reflexion/`, `multi_provider_agentic_grader/`, `context_engineering.json`, `goals/`, `mimic_behavior/`, `prompt_engineering.json`, `templates/`)
- Do not remove `ReflexionAlgorithm` or `MultiProviderAgenticGraderAlgorithm` (context window algorithms, not strategies)
- Do not remove `StrategyMixin` exports from public __all__ without considering downstream; it IS deleted since it only exists to compose strategies

---

## 3. Background & Context

The strategies abstraction was added as a way to wrap prompt-engineering recipes (chain-of-thought, reflexion, tree-of-thoughts, etc.) into composable objects that could be passed to agents. In practice this created a premature abstraction: every agent already has a direct tool-calling loop that covers the common case, and the strategy layer added significant surface area (30+ classes, a parallel StrategyClient namespace, duplicate context types, strategy-specific error classes) for functionality that could be provided via system prompts or pipelines instead. The decision is to remove strategies entirely and simplify the SDK surface.

---

## 4. Requirements

### Functional Requirements
1. `from vidbyte import VidbyteSDK; sdk = VidbyteSDK()` must not expose a `.strategies` attribute
2. `from vidbyte.strategies import ...` must produce `ModuleNotFoundError`
3. `Agent(name=..., system_prompt=..., strategy=...)` must produce a `TypeError` (unexpected kwarg)
4. `from vidbyte import BaseStrategy` must produce `ImportError`
5. `from vidbyte import StrategyResult` must produce `ImportError`
6. The existing agent tool loop (`Agent(name=..., runner=..., tools=[...])`) must continue to work identically
7. `from vidbyte.lib.dataclasses.strategies import AgentResult` must succeed and return a frozen dataclass with `output`, `strategy_name`, `calls`, `metadata` fields
8. `from vidbyte.lib.dataclasses.context import BaseAgentContext` must succeed with `BaseContext` as the ancestor
9. `python -m compileall vidbyte` must complete with zero errors
10. `python -m unittest discover -s tests` must complete with zero errors (after removing strategy test files)
11. `vidbyte/prompts/prompts/` must not contain strategy-only JSON files after removal
12. Skill files must not reference `strategy`, `strategies`, `StrategyChain`, or `StrategyClient`
13. README must not contain Strategy Chain or strategy constructor documentation

### Non-Functional Requirements
- Zero new imports added to any non-strategy file
- No dead code (unused imports, orphaned variables) left behind in modified files
- All `__all__` lists must be kept consistent with actual exports

---

## 5. High-Level Design

The removal is a pure-deletion + rename pass. No new abstractions are introduced.

**Phase A — Core type renames:** `StrategyResult` → `AgentResult` (rename class and file), `StrategyContext` removed (replace usages with `BaseContext`), `strategy_metadata` → `run_metadata` in `BaseContext`, `VMAOContext` deleted, `StrategyExecutionError`/`StrategyConfigurationError` deleted.

**Phase B — Strategy package deleted:** Entire `vidbyte/strategies/` directory removed. All imports of it in `vidbyte/__init__.py`, `vidbyte/agents/base.py`, `vidbyte/client.py` cleaned.

**Phase C — Tool/prompt cleanup:** `vidbyte/tools/strategy_tool.py` deleted, `vidbyte/prompts/strategies/` deleted, strategy-only JSON assets removed from `vidbyte/prompts/prompts/`, corresponding `Prompt` enum entries removed, `vidbyte/prompts/__init__.py` strategy bundle imports removed.

**Phase D — Agent constructor simplified:** `strategy` / `strategies` params removed from `BaseAgent.__init__()`, `from_run_id()`, and `fork()`. The `_normalize_strategy()` static method and all `self.strategy is None` branches removed. `_bind_agent_tool_context` simplified by removing `StrategyTool` reference.

**Phase E — Documentation/skills:** README strategy sections removed. Skill files updated to remove strategy content. 7 test files deleted. 3 design docs deleted.

```
Before:
  BaseAgent.__init__(strategy=..., strategies=...) → _normalize_strategy → StrategyChain
                                                  ↓
                                    strategy.arun(prompt, runner, context)
                                    
After:
  BaseAgent.__init__(no strategy param) → _run_without_strategy always
```

---

## 6. Detailed Design

### 6.1 vidbyte/lib/dataclasses/strategies.py

**File:** `vidbyte/lib/dataclasses/strategies.py`
**Type:** Modified (rename class only)

#### What it does
Holds the `AgentResult` dataclass (previously `StrategyResult`). All other files that imported `StrategyResult` are updated to import `AgentResult`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AgentResult:
    output: str
    strategy_name: str
    calls: tuple[Any, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Edge Cases & Error Handling
- The `strategy_name` field is kept with its existing name; it records which execution path ran (e.g. `"direct_runner"`). Renaming it would be noise with no benefit.

---

### 6.2 vidbyte/lib/dataclasses/context.py

**File:** `vidbyte/lib/dataclasses/context.py`
**Type:** Modified

#### What it does
Holds core context dataclasses. Changes:
- Remove `StrategyContext` class (empty subclass of `BaseContext` — replace all usages with `BaseContext`)
- Remove `VMAOContext` class (used only by deleted VMAO strategy)
- Rename field `strategy_metadata` → `run_metadata` in `BaseContext`
- `BaseAgentContext` inherits from `BaseContext` directly (was inheriting from `StrategyContext`)

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class BaseContext:
    # ... existing fields ...
    run_metadata: Mapping[str, Any] = field(default_factory=dict)  # renamed from strategy_metadata
    # ... metadata field remains ...

@dataclass(frozen=True, slots=True)
class BaseAgentContext(BaseContext):  # was BaseAgentContext(StrategyContext)
    pass
```

---

### 6.3 vidbyte/agents/base.py

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Removes all strategy-related constructor parameters and execution branches.

#### Changes
- Remove `strategy: BaseStrategy | None = None` and `strategies: Sequence[BaseStrategy] | None = None` from `__init__` signature
- Remove `self.strategy = self._normalize_strategy(strategy, strategies)` line
- Remove `if self.strategy is None: ... else: result = await self.strategy.arun(...)` branch in `generate_reply()` — always takes the `_run_without_strategy` path
- Remove `_normalize_strategy()` static method
- Remove `StrategyTool` import and reference in `_bind_agent_tool_context()`
- Remove `strategy` and `strategies` params from `from_run_id()` and `fork()`
- Update imports (remove `BaseStrategy`, `StrategyChain`, `StrategyContext`, `StrategyResult` from strategies)
- Import `AgentResult` from `vidbyte.lib.dataclasses.strategies` instead of `StrategyResult`
- Import `BaseAgentContext` from `vidbyte.lib.dataclasses.context` directly
- Update `generate_reply()` tracer line: `strategy=type(self.strategy).__name__ if self.strategy else "direct"` → `"direct"`
- Update `generate_reply()` reply metadata: `"strategy": result.strategy_name` stays as-is

---

### 6.4 vidbyte/agents/runtime.py

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Replaces `StrategyResult` import with `AgentResult`, updates `strategy_metadata` references to `run_metadata`.

#### Changes
- Change `from vidbyte.strategies.types import BaseAgentContext, StrategyContext, StrategyResult` → `from vidbyte.lib.dataclasses.strategies import AgentResult` and `from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext`
- All `StrategyResult(...)` constructor calls → `AgentResult(...)`
- `base_context: StrategyContext | None` → `base_context: BaseContext | None`
- `strategy_metadata=dict(managed_context.strategy_metadata)` → `run_metadata=dict(managed_context.run_metadata)`

---

### 6.5 vidbyte/client.py

**File:** `vidbyte/client.py`
**Type:** Modified

#### What it does
Removes `StrategyClient` from `VidbyteSDK`.

#### Changes
- Remove `from vidbyte.strategies.client import StrategyClient`
- Remove `self.strategies = StrategyClient()` from `__init__`

---

### 6.6 vidbyte/__init__.py

**File:** `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Removes all strategy-related imports and `__all__` entries.

#### Changes
- Remove: `from vidbyte.strategies import (BaseStrategy, BaseStrategyUtils, ChainOfDraftStrategy, ...)`
- Remove: `from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy`
- Remove all corresponding entries from `__all__`
- Keep `StrategyContext` removed (was re-exported; callers should use `BaseContext`)
- Update docstring header to remove strategy mention

---

### 6.7 vidbyte/lib/errors/base.py

**File:** `vidbyte/lib/errors/base.py`
**Type:** Modified

#### What it does
Removes `StrategyExecutionError` and `StrategyConfigurationError`.

#### Changes
- Delete class `StrategyExecutionError(VidbyteSdkError)`
- Delete class `StrategyConfigurationError(StrategyExecutionError)`
- Update module docstring

---

### 6.8 vidbyte/lib/errors/__init__.py

**File:** `vidbyte/lib/errors/__init__.py`
**Type:** Modified

#### Changes
- Remove `StrategyConfigurationError` and `StrategyExecutionError` from import and `__all__`

---

### 6.9 vidbyte/__init__.py — error exports

**File:** `vidbyte/__init__.py`
**Type:** Modified (included in 6.6)

#### Changes
- Remove `StrategyExecutionError`... wait, checking original — `StrategyExecutionError` is NOT in vidbyte root `__init__.py` exports (only in `lib/errors/__init__.py`). Confirmed: strategy errors are not in the top-level `__all__`.

---

### 6.10 vidbyte/context/__init__.py

**File:** `vidbyte/context/__init__.py`
**Type:** Modified

#### Changes
- Remove `StrategyContext` and `VMAOContext` from imports and `__all__`

---

### 6.11 vidbyte/prompts/strategies/ — DELETED

**Files:** Entire `vidbyte/prompts/strategies/` directory
**Type:** Deleted

Deletes:
- `vidbyte/prompts/strategies/__init__.py`
- `vidbyte/prompts/strategies/strategy_prompts.py`
- `vidbyte/prompts/strategies/self_refinement.py`

---

### 6.12 vidbyte/prompts/__init__.py

**File:** `vidbyte/prompts/__init__.py`
**Type:** Modified

#### Changes
- Remove all imports from `vidbyte.prompts.strategies`
- Remove all strategy prompt bundle names from `__all__`

---

### 6.13 vidbyte/lib/enums/prompts.py

**File:** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### Changes
Remove strategy-only `Prompt` enum values:
- `AGENTIC_RAG_RETRIEVE_PROMPT`, `AGENTIC_RAG_ANSWER_PROMPT`
- `ANSWER_CONVERGENCE_ATTEMPT_PROMPT`
- `BUDGET_FORCING_INITIAL_PROMPT`, `BUDGET_FORCING_CONTINUE_PROMPT`
- `CHAIN_OF_DRAFT_DRAFT_PROMPT`
- `CHAIN_OF_THOUGHT_REASON_PROMPT`
- `MULTI_AGENT_REFLEXION_DRAFT_PROMPT`, `MULTI_AGENT_REFLEXION_CRITIC_PROMPT`, `MULTI_AGENT_REFLEXION_FINAL_PROMPT`
- `PARADIGM_ROUTER_ROUTE_PROMPT`
- `PLAN_AND_EXECUTE_PLAN_PROMPT`, `PLAN_AND_EXECUTE_EXECUTE_PROMPT`, `PLAN_AND_EXECUTE_FINAL_PROMPT`
- `SELF_CONSISTENCY_SAMPLE_PROMPT`
- `SKELETON_OF_THOUGHT_SKELETON_PROMPT`, `SKELETON_OF_THOUGHT_EXPAND_PROMPT`
- `STEP_BACK_PRINCIPLE_PROMPT`, `STEP_BACK_ANSWER_PROMPT`
- `TREE_OF_THOUGHTS_BRANCH_PROMPT`, `TREE_OF_THOUGHTS_EVALUATE_PROMPT`, `TREE_OF_THOUGHTS_FINAL_PROMPT`
- `VMAO_PLANNER`, `VMAO_PLANNER_REPAIR`, `VMAO_SYNTHESIZER`, `VMAO_VERIFIER`, `VMAO_GAP_PLANNER`

Keep: `AGENTIC_LOOP_*`, `EVALS_*`, `REFLEXION_*`, `MULTI_PROVIDER_AGENTIC_GRADER_*`, `CONTEXT_ENGINEERING_*`, `GOALS_*`, `MIMIC_BEHAVIOR_*`, `PROMPT_ENGINEERING_*`, `TEMPLATES_*`

---

### 6.14 vidbyte/prompts/prompts/ — strategy JSON assets DELETED

**Files:** Strategy-only JSON prompt files
**Type:** Deleted

Delete:
- `agentic_rag.json`
- `answer_convergence.json`
- `budget_forcing.json`
- `chain_of_draft.json`
- `chain_of_thought.json`
- `multi_agent_reflexion.json`
- `paradigm_router.json`
- `plan_and_execute.json`
- `self_consistency.json`
- `skeleton_of_thought.json`
- `step_back.json`
- `tree_of_thoughts.json`
- `vmao.json`

Keep: `agentic_loop.json`, `evals.json`, `context_engineering.json`, `prompt_engineering.json`, `goals/`, `mimic_behavior/`, `multi_provider_agentic_grader/`, `reflexion/`, `templates/`

---

### 6.15 vidbyte/tools/__init__.py

**File:** `vidbyte/tools/__init__.py`
**Type:** Check and remove any StrategyTool export

---

### 6.16 vidbyte/lib/dataclasses/strategy_types.py — DELETED

**File:** `vidbyte/lib/dataclasses/strategy_types.py`
**Type:** Deleted (duplicate `StrategyResult` definition, only imported by strategy code)

---

### 6.17 README.md

**File:** `README.md`
**Type:** Modified

#### Changes
- Remove line 21: `sdk.strategies`
- Remove "Multi-Agent Orchestration" section strategy import example (lines ~64-79)
- Remove entire "Strategy Chains" section (lines ~82-117)
- Remove `StrategyContext` usage example in "Context Objects" section (~lines 124-134)
- Remove `sdk.strategies` from Package Structure diagram
- Remove `StrategyMixin` mention from README
- Remove `ToolRegistry` / `ToolExecutor` / `vidbyte_tool` strategy-compatibility footnote

---

### 6.18 skills/ — strategy content removal

**Files:** Multiple skill `.md` files
**Type:** Modified

Files to update:
- `skills/usage/available_features.md` — remove entire "Strategies" section and "Strategy Composability" section, remove `sdk.strategies` from SDK client example, remove `StrategyExecutionError` from error hierarchy
- `skills/usage/create_agent.md` — remove `strategy: BaseStrategy | None = None` from constructor table, remove strategy mentions in parameter descriptions and "Next Steps"
- `skills/usage/create_agents.md` — remove strategy mentions
- `skills/vidbyte-sdk/SKILL.md` — remove `strategies/` from layout, remove strategy-related rules
- Other skill files: remove individual strategy references

---

## 7. Data Model Changes

N/A — no database schema changes.

The `BaseContext` dataclass field rename (`strategy_metadata` → `run_metadata`) is a Python dataclass change with no persistence impact.

---

## 8. API Changes

N/A — this is a pure SDK library, no HTTP endpoints.

**Breaking change for callers of `BaseAgent`:** `strategy=` and `strategies=` constructor kwargs are removed. Any code passing these will get `TypeError: unexpected keyword argument 'strategy'`.

**Breaking change for importers:** `from vidbyte.strategies import ...` raises `ModuleNotFoundError`. `from vidbyte import BaseStrategy, StrategyResult, StrategyChain, ...` raises `ImportError`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| DELETE | `vidbyte/strategies/__init__.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/base.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/chain.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/client.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/mixins.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/types.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/react.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/reflexion.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/tree_of_thoughts.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/codeact.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/agent_loops/__init__.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/agent_loops/plan_and_execute.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/agent_loops/self_refinement.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/reasoning/__init__.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/reasoning/chain_of_thought.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/reasoning/chain_of_draft.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/reasoning/skeleton_of_thought.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/reasoning/step_back.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/sampling/__init__.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/sampling/self_consistency.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/sampling/budget_forcing.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/sampling/answer_convergence.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/routing/__init__.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/routing/paradigm_router.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/__init__.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/base.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/consensus.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/autogen.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/vmao.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/economic_gate.py` | Strategy package removed |
| DELETE | `vidbyte/strategies/multi_agent/evolving.py` | Strategy package removed |
| DELETE | `vidbyte/tools/strategy_tool.py` | Strategy tool removed |
| DELETE | `vidbyte/prompts/strategies/__init__.py` | Strategy prompt bundles removed |
| DELETE | `vidbyte/prompts/strategies/strategy_prompts.py` | Strategy prompt bundles removed |
| DELETE | `vidbyte/prompts/strategies/self_refinement.py` | Strategy prompt bundles removed |
| DELETE | `vidbyte/lib/dataclasses/strategy_types.py` | Duplicate StrategyResult, only used by strategies |
| DELETE | `vidbyte/prompts/prompts/agentic_rag.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/answer_convergence.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/budget_forcing.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/chain_of_draft.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/chain_of_thought.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/multi_agent_reflexion.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/paradigm_router.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/plan_and_execute.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/self_consistency.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/skeleton_of_thought.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/step_back.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/tree_of_thoughts.json` | Strategy-only prompt asset |
| DELETE | `vidbyte/prompts/prompts/vmao.json` | Strategy-only prompt asset |
| DELETE | `tests/test_strategy_chain.py` | Strategy test |
| DELETE | `tests/test_strategy_tool.py` | Strategy test |
| DELETE | `tests/test_strategy_router.py` | Strategy test |
| DELETE | `tests/test_reasoning_strategies.py` | Strategy test |
| DELETE | `tests/test_sampling_strategies.py` | Strategy test |
| DELETE | `tests/test_self_refinement_strategy.py` | Strategy test |
| DELETE | `tests/test_strategy_mixin.py` | Strategy test |
| DELETE | `docs/design/agent-strategy-chain-execution.md` | Strategy design doc |
| DELETE | `docs/design/multi-agent-orchestration-strategies.md` | Strategy design doc |
| DELETE | `docs/design/prompt-api-strategies-sdk.md` | Strategy design doc |
| MODIFY | `vidbyte/lib/dataclasses/strategies.py` | Rename StrategyResult → AgentResult |
| MODIFY | `vidbyte/lib/dataclasses/context.py` | Remove StrategyContext, VMAOContext; rename strategy_metadata → run_metadata; BaseAgentContext parent → BaseContext |
| MODIFY | `vidbyte/lib/errors/base.py` | Remove StrategyExecutionError, StrategyConfigurationError |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Remove strategy error exports |
| MODIFY | `vidbyte/agents/base.py` | Remove strategy/strategies params and all strategy execution branches |
| MODIFY | `vidbyte/agents/runtime.py` | Replace StrategyResult→AgentResult, StrategyContext→BaseContext, strategy_metadata→run_metadata |
| MODIFY | `vidbyte/client.py` | Remove StrategyClient import and self.strategies |
| MODIFY | `vidbyte/__init__.py` | Remove all strategy exports |
| MODIFY | `vidbyte/context/__init__.py` | Remove StrategyContext, VMAOContext exports |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Remove strategy-only Prompt enum entries |
| MODIFY | `vidbyte/prompts/__init__.py` | Remove strategy bundle imports and exports |
| MODIFY | `README.md` | Remove strategy sections |
| MODIFY | `skills/usage/available_features.md` | Remove strategy content |
| MODIFY | `skills/usage/create_agent.md` | Remove strategy param references |
| MODIFY | `skills/usage/create_agents.md` | Remove strategy references |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Remove strategy rules from layout |

---

## 10. Testing Plan

### Unit Tests
The test suite is verified by running `python -m unittest discover -s tests` after deletions.

- `python -m compileall vidbyte` — [Hidden Assumption] verifies no broken imports remain after deletions
- `python -m unittest discover -s tests` with zero strategy test files — [Edge Case] all remaining tests pass with the refactored type names
- Verify `from vidbyte.strategies import BaseStrategy` raises `ModuleNotFoundError` — [Hidden Assumption]
- Verify `Agent(name="x", system_prompt="y", strategy=None)` raises `TypeError` — [Edge Case]
- Verify `VidbyteSDK().strategies` raises `AttributeError` — [Hidden Failure]
- Verify `from vidbyte import AgentResult` raises `ImportError` (AgentResult is internal, not re-exported at root) — [Silent Failure]
- Verify `from vidbyte.lib.dataclasses.strategies import AgentResult` succeeds — [Hidden Assumption]
- Verify `Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)` raises `AttributeError` — [Edge Case]
- Verify `python -c "from vidbyte import Agent, Tools, VidbyteSDK, tool; sdk = VidbyteSDK(); print(Agent.__name__, Tools.__name__, type(sdk.agents).__name__, callable(tool))"` matches README verification command — [Silent Failure]

### Integration Tests
- Full agent run with tools (no strategy) must continue to produce `AgentMessage` via `arun()` — [Hidden Assumption]
- `AgentResult` returned by `AgentRuntime.arun()` must have `output`, `strategy_name`, `calls`, `metadata` — [Silent Failure]
- `BaseAgentContext` must be buildable from `AgentRuntime.build_context()` with `run_metadata` field — [Hidden Failure]

### Manual / QA Test Cases
1. Given `from vidbyte import VidbyteSDK; sdk = VidbyteSDK()`, when accessing `sdk.strategies`, then `AttributeError` is raised — [Edge Case]
2. Given the local verification command in README, when run, then it prints agent/tools names without error — [Hidden Assumption]

---

## 11. Dependencies & External Services

N/A — pure internal refactor, no external service changes.

---

## 12. Rollout & Deployment

- Breaking change: callers using `strategy=`, `strategies=`, or importing from `vidbyte.strategies` will break
- This is an internal package marked `UNLICENSED` — no migration path needed for external consumers
- Single PR, no feature flags
- Rollback: revert the branch

---

## 13. Open Questions

None — scope is fully defined.

---

## 14. Alternatives Considered

### Alternative 1: Deprecation warnings instead of deletion
- What: Keep strategy classes but print deprecation warnings, remove in a future release
- Why rejected: The user explicitly requested complete removal. Deprecation warnings keep dead weight in the codebase.

### Alternative 2: Keep StrategyResult / StrategyContext names
- What: Rename nothing — just delete the strategy implementations but keep the result/context type names
- Why rejected: Leaving `StrategyResult` and `StrategyContext` as type names in a codebase with no strategies is confusing. Renaming to `AgentResult` and removing `StrategyContext` (replacing with `BaseContext`) is cleaner.

### Alternative 3: Move strategy implementations to a separate opt-in package
- What: Extract to `vidbyte-strategies` package
- Why rejected: The user's intent is removal, not relocation.
