# Design Doc: SDK Consolidated (PRs 10–15)

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

PRs 10–15 on `cerredz/Vidbyte-SDK` each implemented different slices of the SDK in parallel, resulting in overlapping edits to shared files (`vidbyte/__init__.py`, `vidbyte/strategies/base.py`, `vidbyte/lib/errors/base.py`, etc.) and divergent implementations of common concepts (PromptRegistry, BaseStrategy). This design doc describes how all six PRs are merged into a single clean PR (#16) against `main`, resolving all conflicts by picking the most complete version of each component, deduplicating duplicated request logic, and adding unique features from every branch.

---

## 2. Goals & Non-Goals

### Goals
- Absorb every unique feature from PRs 10–15 into a single coherent branch
- Produce a branch that compiles cleanly (`python -m compileall vidbyte`)
- Produce a branch where all tests pass (`python -m unittest discover -s tests`)
- Resolve every file-level conflict by producing a single authoritative version of each shared file
- Close PRs 10–15 once PR 16 is open

### Non-Goals
- Adding new features beyond what already exists across PRs 10–15
- Upgrading or adding external dependencies
- Merging the vidbyte-cli or vidbyte (app) repos

---

## 3. Background & Context

The SDK repo started as an empty namespace scaffold. Six PRs were opened in parallel by AI agents resolving review comments from other repos and prototyping feature subsystems:

| PR | Branch | Core content |
|----|--------|-------------|
| 10 | `feat/agent-abstractions` | BaseTool, ToolRegistry/Executor, BasePrompt, PromptRegistry (class-based), prompt translations (ReAct, Reflexion, ToT, etc.), ConditionalHarnesses, simple strategy skeletons |
| 11 | `ai/resolve-sdk-pr-3-comments` | SelfRefinementStrategy, TextModelRunner, lib/config, providers (Anthropic/OpenAI/Gemini/xAI), reasoning/sampling/routing strategies |
| 12 | `ai/resolve-sdk-pr-4-comments` | Superset of PR11 + JSON prompt assets, expanded filesystem tools, lib/http, lib/prompts/registry (JSON-based), lib/tools/filesystem backends, PromptRegistry dataclass approach |
| 13 | `ai/resolve-sdk-pr-5-comments` | BaseAgent, AgentRegistry, StrategyContext, multi-agent strategies (Consensus, AutoGen, VMAO, EconomicGate, Evolving), lib/dataclasses, lib/enums |
| 14 | `ai/resolve-sdk-pr-6-comments` | Subset of PR15 (ToolsFormatter, code_search, security, MCP bridge) |
| 15 | `feat/mcp-server-attachment` | Superset of PR13+14 + MCP attach API (McpServerHandle), agent mixins, full MCP lifecycle |

PRs 13 and 14 are fully contained in PR 15. PR 12 is a superset of PR 11 (except PR 11 adds `SelfRefinementStrategy` which PR 12 omits). The three branches that contribute unique content not in PR 15 are: **PR 10**, **PR 11** (for `self_refinement`), and **PR 12**.

---

## 4. Requirements

### Functional Requirements

1. All public exports from every PR must be available under `vidbyte.*` after consolidation.
2. `vidbyte/lib/errors/base.py` must contain the union of error classes from PR 12 (Provider/Config errors) and PR 15 (MCP/Agent errors).
3. `vidbyte/strategies/__init__.py` must export strategies from all PRs: multi-agent (PR15), reasoning/routing/sampling (PR12), agent_loops (PR12), ReAct/Reflexion/ToT etc. (PR10).
4. `vidbyte/harnesses/__init__.py` must export both `BaseHarness`/`HarnessClient` (PR15) and `ConditionalLoopAgentHarness`/`ConditionalStoppingEvaluator` (PR10).
5. `vidbyte/prompts/__init__.py` must expose the class-based `BasePrompt`/`PromptRegistry` (PR10), JSON-based `PromptRegistry` from `lib/prompts` (PR12), and `AgentRolePrompt`/`VMAOPrompts` (PR15).
6. `vidbyte/strategies/base.py` must provide both `BaseStrategy` (async-first, PR15 contract) and `BaseStrategyUtils` (PR12 helpers) — resolving the two divergent implementations into one.
7. The full filesystem tool suite (PR12: append, copy, delete, diff, find, move, read_binary, stat, zip) must be present alongside the advanced tool builtins (PR15: code_search, context compaction, patch editing, security sandbox).
8. The simple builtins from PR10 (calculator, web_search, code_execution, document_retrieval) must be present alongside the advanced builtins from PR15.
9. All existing tests across every PR must pass without modification.

### Non-Functional Requirements
- Zero new external dependencies (standard library + `pydantic>=2` only)
- Thread-safe registries (PromptRegistry singleton, ToolRegistry)
- `python -m compileall vidbyte` passes with no errors
- All test suites pass: `python -m unittest discover -s tests`

---

## 5. High-Level Design

The consolidation uses PR 15 (`feat/mcp-server-attachment`) as the base because it is a confirmed superset of PRs 13 and 14. On top of that base, unique content from PR 10, PR 11, and PR 12 is layered in without conflict (these are all new files relative to PR 15). The ~10 shared files that differ between branches are resolved by manually producing a unified version that contains all exports and no duplicate definitions.

```
main
  └─ feat/sdk-consolidated  (new PR 16 branch)
        │
        ├─ [merge] feat/mcp-server-attachment   (PR15 — base, ~90 files)
        │       └── agents/, context/, multi-agent/, MCP attach, code_search,
        │           security, context-compaction, patch, ToolsFormatter
        │
        ├─ [checkout unique] feat/agent-abstractions  (PR10 — ~30 new files)
        │       └── prompts/translations/, prompts/builtins/, prompts/types.py,
        │           prompts/base.py, harnesses/conditional/, strategies/react.py,
        │           strategies/reflexion.py, strategies/tree_of_thoughts.py,
        │           tools/builtins/calculator|web_search|code_execution|doc_retrieval
        │
        ├─ [checkout unique] ai/resolve-sdk-pr-3-comments  (PR11 — 3 files)
        │       └── strategies/agent_loops/self_refinement.py,
        │           prompts/strategies/self_refinement.py,
        │           tests/test_self_refinement_strategy.py
        │
        ├─ [checkout unique] ai/resolve-sdk-pr-4-comments  (PR12 — ~70 new files)
        │       └── providers/, lib/runners/, lib/config/, lib/http/,
        │           lib/prompts/registry.py, lib/tools/filesystem/,
        │           lib/dataclasses/filesystem|model_configs|strategy_types|tool_types,
        │           lib/enums/model_provider|platform, tools/filesystem/,
        │           strategies/agent_loops/plan_and_execute, strategies/reasoning/,
        │           strategies/routing/, strategies/sampling/,
        │           prompts/prompts/*.json, prompts/strategies/strategy_prompts.py
        │
        └─ [manual merge] ~10 shared files resolved by hand
                └── vidbyte/__init__.py, strategies/__init__.py,
                    strategies/base.py, harnesses/__init__.py,
                    lib/errors/base.py, lib/dataclasses/__init__.py,
                    lib/enums/__init__.py, prompts/__init__.py,
                    prompts/registry.py, tools/__init__.py
```

---

## 6. Detailed Design

### 6.1 Merge Strategy: Use PR15 as Base

**Branch:** `feat/mcp-server-attachment`
**Action:** `git merge --no-ff origin/feat/mcp-server-attachment`

PR15 is a clean divergence from `main` with no path that conflicts with `main`'s current tip (`89e2404`). The merge will produce a fast-forwardable state carrying all ~90 files from PR15 intact.

#### Files brought in (~90 files, see Section 9 for full list)
- `vidbyte/agents/` — BaseAgent, AgentCard, AgentMessage, AgentRegistry, AgentRunnerConfig, AgentSpec, AgentMixin
- `vidbyte/context/` — BaseContext, ContextBudget, ContextPermissions
- `vidbyte/strategies/multi_agent/` — Consensus, AutoGen, VMAO, EconomicGate, Evolving strategies
- `vidbyte/tools/builtins/code_search/` — Glob, Grep, Semantic search
- `vidbyte/tools/builtins/context/` — ContextCompaction tool
- `vidbyte/tools/builtins/editing/` — Patch tool
- `vidbyte/tools/mcp/` — McpClient, McpBridge, McpTransport, McpAttach (McpServerHandle)
- `vidbyte/tools/security/` — SecurityExecutor, PermissionPolicy
- `vidbyte/lib/tools/formatter.py` — ToolsFormatter (OpenAI/Anthropic/Grok/Gemini schema emitters)
- `vidbyte/lib/dataclasses/` — agents, code_search, context, mcp, multi_agent, sandbox, security, strategies, tools
- `vidbyte/lib/enums/context.py` — BudgetPreset, PermissionPreset

### 6.2 Add Unique PR10 Content

**Branch:** `feat/agent-abstractions`
**Action:** `git checkout origin/feat/agent-abstractions -- <files>`

#### Files to checkout (~30 files)
| File | Purpose |
|------|---------|
| `vidbyte/prompts/types.py` | PromptKey, PromptVersion, RenderedPrompt dataclasses |
| `vidbyte/prompts/base.py` | Abstract BasePrompt, PromptError, PromptNotFoundError, PromptRenderError |
| `vidbyte/prompts/builtins/__init__.py` | Package marker |
| `vidbyte/prompts/builtins/vidbyte_defaults.py` | `register_defaults()` auto-registers all translation prompts |
| `vidbyte/prompts/translations/__init__.py` | Package marker |
| `vidbyte/prompts/translations/strategies/__init__.py` | Exports all strategy translations |
| `vidbyte/prompts/translations/strategies/react.py` | ReActSystemPrompt, ReActIterationPrompt |
| `vidbyte/prompts/translations/strategies/reflexion.py` | ReflexionActorPrompt, EvaluatorPrompt, ReflectorPrompt |
| `vidbyte/prompts/translations/strategies/self_consistency.py` | SelfConsistencyPrompt |
| `vidbyte/prompts/translations/strategies/step_back.py` | StepBackAbstractionPrompt, ReasoningPrompt |
| `vidbyte/prompts/translations/strategies/tree_of_thoughts.py` | ToTBranchPrompt, ScoringPrompt |
| `vidbyte/prompts/translations/harnesses/__init__.py` | Package marker |
| `vidbyte/prompts/translations/harnesses/conditional/__init__.py` | Exports conditional harness prompts |
| `vidbyte/prompts/translations/harnesses/conditional/loop_agent.py` | ConditionalLoopAgentPrompt |
| `vidbyte/prompts/translations/harnesses/conditional/stopping_evaluator.py` | ConditionalStoppingEvaluatorPrompt |
| `vidbyte/harnesses/conditional/__init__.py` | Exports ConditionalLoopAgentHarness, ConditionalStoppingEvaluator |
| `vidbyte/harnesses/conditional/loop_agent.py` | ConditionalLoopAgentHarness implementation |
| `vidbyte/harnesses/conditional/stopping_evaluator.py` | ConditionalStoppingEvaluator implementation |
| `vidbyte/strategies/react.py` | ReActStrategy skeleton |
| `vidbyte/strategies/reflexion.py` | ReflexionStrategy skeleton |
| `vidbyte/strategies/tree_of_thoughts.py` | TreeOfThoughtsStrategy skeleton |
| `vidbyte/tools/builtins/calculator.py` | Sandboxed math evaluator |
| `vidbyte/tools/builtins/web_search.py` | Mock web search tool |
| `vidbyte/tools/builtins/code_execution.py` | Mock code sandbox tool |
| `vidbyte/tools/builtins/document_retrieval.py` | Mock document retrieval tool |
| `tests/test_agent_abstractions.py` | Tests for PR10's prompt registry + tool executor |

#### Edge Cases
- `vidbyte/strategies/self_consistency.py` and `vidbyte/strategies/step_back.py` from PR10 must **not** be checked out — PR12 has more complete versions of these strategy families under `vidbyte/strategies/sampling/` and `vidbyte/strategies/reasoning/`. PR10's standalone skeleton files will conflict; omit them.
- `vidbyte/prompts/registry.py` from PR10 differs from PR15's version. **Handled in Section 6.5.**

### 6.3 Add Unique PR11 Content

**Branch:** `ai/resolve-sdk-pr-3-comments`
**Action:** `git checkout origin/ai/resolve-sdk-pr-3-comments -- <files>`

#### Files to checkout (3 files)
| File | Purpose |
|------|---------|
| `vidbyte/strategies/agent_loops/self_refinement.py` | SelfRefinementStrategy (feedback/refine loop) |
| `vidbyte/prompts/strategies/self_refinement.py` | SelfRefinementCreatePrompt, FeedbackPrompt, RefinePrompt |
| `tests/test_self_refinement_strategy.py` | Test coverage for SelfRefinementStrategy |

### 6.4 Add Unique PR12 Content

**Branch:** `ai/resolve-sdk-pr-4-comments`
**Action:** `git checkout origin/ai/resolve-sdk-pr-4-comments -- <files>`

#### Files to checkout (~70 files, grouped by area)

**Providers:**
- `vidbyte/providers/anthropic.py`, `openai.py`, `gemini.py`, `xai.py`, `compatible.py`
- `vidbyte/providers/__init__.py` — provider factory and adapters

**Runners:**
- `vidbyte/lib/runners/__init__.py`, `base.py`, `text.py`, `image.py`, `video.py`, `types.py`

**Config:**
- `vidbyte/lib/config/__init__.py`, `base.py`, `models.py`, `constants.py`

**HTTP:**
- `vidbyte/lib/http/__init__.py`, `parser.py`, `transport.py`

**Lib Prompts (JSON-based registry):**
- `vidbyte/lib/prompts/__init__.py`, `registry.py`

**Lib Tools Filesystem:**
- `vidbyte/lib/tools/__init__.py`, `filesystem/__init__.py`, `backends/__init__.py`, `backends/base.py`, `backends/local.py`, `permissions.py`

**Additional dataclasses:**
- `vidbyte/lib/dataclasses/filesystem.py`, `model_configs.py`, `strategy_types.py`, `tool_types.py`

**Additional enums:**
- `vidbyte/lib/enums/model_provider.py`, `platform.py`

**Filesystem tools:**
- `vidbyte/tools/filesystem/__init__.py`, `_base_tool.py`, `base.py`, `list_dir.py`, `make_dir.py`, `read_text.py`, `write_text.py`, `append_text.py`, `copy.py`, `delete.py`, `diff.py`, `find.py`, `move.py`, `read_binary.py`, `stat.py`, `zip_tools.py`

**Strategy sub-packages:**
- `vidbyte/strategies/agent_loops/__init__.py`, `plan_and_execute.py`
- `vidbyte/strategies/reasoning/__init__.py`, `chain_of_draft.py`, `chain_of_thought.py`, `skeleton_of_thought.py`, `step_back.py`
- `vidbyte/strategies/routing/__init__.py`, `paradigm_router.py`
- `vidbyte/strategies/sampling/__init__.py`, `self_consistency.py`, `answer_convergence.py`, `budget_forcing.py`

**JSON Prompt assets:**
- `vidbyte/prompts/prompts/agentic_rag.json`, `answer_convergence.json`, `budget_forcing.json`, `chain_of_draft.json`, `chain_of_thought.json`, `context_engineering.json`, `expert_prompting.json`, `multi_agent_reflexion.json`, `paradigm_router.json`, `plan_and_execute.json`, `self_consistency.json`, `skeleton_of_thought.json`, `step_back.json`, `tree_of_thoughts.json`

**Strategy prompt dataclasses:**
- `vidbyte/prompts/strategies/__init__.py`, `strategy_prompts.py`

**Skills doc:**
- `skills/vidbyte-sdk/adding-prompts.md`

**Tests:**
- `tests/test_config_validation.py`, `test_filesystem_tools.py`, `test_image_video_runners.py`, `test_prompt_registry.py`, `test_reasoning_strategies.py`, `test_sampling_strategies.py`, `test_strategy_router.py`, `test_text_model_runner.py`

### 6.5 Manual Merge: Shared Conflicting Files

These ~10 files exist in multiple branches with different content. Each must be hand-authored as a merged version.

#### 6.5.1 `vidbyte/lib/errors/base.py`

**Strategy:** Union of PR12 errors (Provider/Config family) + PR15 errors (MCP/Agent family).

```python
# vidbyte/lib/errors/base.py — merged
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

class VidbyteSdkError(Exception):
    """Base SDK exception with structured details."""
    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})

# Provider/config family (PR12)
class ConfigurationError(VidbyteSdkError): ...
class UnsupportedProviderError(VidbyteSdkError): ...
class ProviderSelectionError(VidbyteSdkError): ...
class ProviderRequestError(VidbyteSdkError): ...
class ProviderConfigurationError(ProviderRequestError): ...
class ProviderResponseError(ProviderRequestError): ...
class StrategyConfigurationError(VidbyteSdkError): ...

# Tool/registry/security family (PR15)
class ToolRegistryError(VidbyteSdkError): ...
class ToolExecutionError(VidbyteSdkError): ...
class PermissionDeniedError(VidbyteSdkError): ...
class McpProtocolError(VidbyteSdkError): ...
class StrategyExecutionError(VidbyteSdkError): ...
class AgentExecutionError(VidbyteSdkError): ...
class AgentRegistryError(VidbyteSdkError): ...

# MCP family (PR15)
class McpError(VidbyteSdkError): ...
class McpConnectionError(McpError): ...
class McpInitializeError(McpError): ...
class McpToolDiscoveryError(McpError): ...
class McpToolExecutionError(McpError): ...
class McpAttachmentError(McpError): ...
```

#### 6.5.2 `vidbyte/strategies/base.py`

**Strategy:** PR15's async-first `BaseStrategy` + PR12's `BaseStrategyUtils` helpers. PR12's runner-aware pattern is expressed by concrete strategies passing a runner in `__init__`; the abstract base stays async-first.

```python
class BaseStrategy:
    name: ClassVar[str] = "base"
    async def arun(self, prompt, *, context=None, tools=(), **options) -> StrategyResult: ...
    def run(self, prompt, **kwargs) -> StrategyResult: ...  # asyncio.run wrapper

class BaseStrategyUtils:
    @staticmethod def extract_final_answer(text) -> str: ...
    @staticmethod def normalize_answer(text) -> str: ...
    @staticmethod def parse_numbered_lines(text) -> tuple[str,...]: ...
    @staticmethod def require_positive(value, *, field_name) -> None: ...
```

PR12's concrete strategies (`ChainOfThought`, `SelfRefinement`, etc.) use their own `__init__` to accept `runner=` and call `runner.run()` inside their `arun()`. No changes needed to those files.

#### 6.5.3 `vidbyte/strategies/__init__.py`

**Strategy:** Export everything from all three PRs' strategy namespaces.

```python
from vidbyte.strategies.agent_loops import PlanAndExecuteStrategy, SelfRefinementStrategy
from vidbyte.strategies.base import BaseStrategy, BaseStrategyUtils
from vidbyte.strategies.client import StrategyClient
from vidbyte.strategies.mixins import StrategyMixin
from vidbyte.strategies.multi_agent import (ConsensusStrategy, AutoGenStrategy, VMAOStrategy, EconomicGateStrategy, EvolvingOrchestrationStrategy)
from vidbyte.strategies.react import ReActStrategy
from vidbyte.strategies.reflexion import ReflexionStrategy
from vidbyte.strategies.reasoning import (ChainOfDraftStrategy, ChainOfThoughtStrategy, SkeletonOfThoughtStrategy, StepBackStrategy)
from vidbyte.strategies.routing import ParadigmRouterStrategy
from vidbyte.strategies.sampling import (AnswerConvergenceStrategy, BudgetForcingStrategy, SelfConsistencyStrategy)
from vidbyte.strategies.tree_of_thoughts import TreeOfThoughtsStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult
```

#### 6.5.4 `vidbyte/harnesses/__init__.py`

**Strategy:** PR15 base + PR10 conditional harnesses.

```python
from vidbyte.harnesses.base import BaseHarness
from vidbyte.harnesses.client import HarnessClient
from vidbyte.harnesses.conditional import ConditionalLoopAgentHarness, ConditionalStoppingEvaluator
```

#### 6.5.5 `vidbyte/prompts/__init__.py`

**Strategy:** Expose all three prompt namespaces.

```python
# Class-based system (PR10)
from vidbyte.prompts.base import BasePrompt, PromptError, PromptNotFoundError, PromptRenderError
from vidbyte.prompts.types import PromptKey, PromptVersion, RenderedPrompt

# Agent-role + VMAO prompts (PR15)
from vidbyte.prompts.prompts import AgentRolePrompt, VMAOPrompts
from vidbyte.prompts.registry import PromptRegistry, prompt_registry

# JSON-backed strategy prompts (PR12)
from vidbyte.prompts.strategies import (
    ChainOfThoughtPrompts, ChainOfDraftPrompts, StepBackPrompts,
    TreeOfThoughtsPrompts, SelfConsistencyPrompts, PlanAndExecutePrompts,
    ParadigmRouterPrompts, AnswerConvergencePrompts, BudgetForcingPrompts,
    SkeletonOfThoughtPrompts, AgenticRagPrompts, ContextEngineeringPrompts,
    ExpertPromptingPrompts, MultiAgentReflexionPrompts,
)
from vidbyte.lib.prompts import PromptRegistry as LibPromptRegistry, PrompRegistry
```

#### 6.5.6 `vidbyte/prompts/registry.py`

**Strategy:** Keep PR15's version (simple, includes `prompt_registry` singleton with `AgentRolePrompt`/`VMAOPrompts`). PR10's class-based `PromptRegistry` (key-version lookup) lives in `vidbyte/prompts/registry.py` AND is also needed. Merge them:
- The primary `PromptRegistry` export is PR10's thread-safe key-version singleton (BasePrompt-based).
- Add a `prompt_registry` module-level singleton (PR15's usage) as a convenience alias.

#### 6.5.7 `vidbyte/lib/dataclasses/__init__.py`

**Strategy:** Export the union of all dataclass modules from PR12 and PR15.

```python
from vidbyte.lib.dataclasses.agents import *
from vidbyte.lib.dataclasses.code_search import *
from vidbyte.lib.dataclasses.context import *
from vidbyte.lib.dataclasses.filesystem import *
from vidbyte.lib.dataclasses.mcp import *
from vidbyte.lib.dataclasses.model_configs import *
from vidbyte.lib.dataclasses.multi_agent import *
from vidbyte.lib.dataclasses.sandbox import *
from vidbyte.lib.dataclasses.security import *
from vidbyte.lib.dataclasses.strategies import *
from vidbyte.lib.dataclasses.strategy_types import *
from vidbyte.lib.dataclasses.tool_types import *
from vidbyte.lib.dataclasses.tools import *
```

#### 6.5.8 `vidbyte/lib/enums/__init__.py`

**Strategy:** Export from all enum modules.

```python
from vidbyte.lib.enums.context import BudgetPreset, PermissionPreset
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.platform import Platform
```

#### 6.5.9 `vidbyte/tools/__init__.py`

**Strategy:** PR15's version is already a superset of PR10's. Keep PR15's as-is (it already exports `BaseTool`, `ToolCall`, `ToolExecutor`, `ToolParameter`, `ToolPermission`, `ToolRegistry`, `ToolResult`, `ToolSpec`, `ToolStatus`, `ToolsFormatter`, `ToolsClient`).

#### 6.5.10 `vidbyte/__init__.py`

**Strategy:** Expand PR15's version to also export strategy classes from PR12/PR10 and the prompt system.

```python
# Existing PR15 exports: AgentCard, BaseAgent, BaseContext, BaseTool, BudgetPreset,
#   ContextBudget, ContextPermissions, McpError family, McpServerConfig, McpServerHandle,
#   McpToolPermission, PermissionPreset, StrategyContext, StrategyResult,
#   ToolCall, ToolExecutor, ToolParameter, ToolPermission, ToolRegistry, ToolResult,
#   ToolSpec, ToolStatus, ToolsFormatter, VidbyteSDK

# Add from PR12/10:
from vidbyte.prompts import BasePrompt, PromptKey, PromptRegistry, RenderedPrompt
from vidbyte.strategies import (BaseStrategyUtils, ReActStrategy, ReflexionStrategy,
    TreeOfThoughtsStrategy, ChainOfThoughtStrategy, ChainOfDraftStrategy,
    SelfConsistencyStrategy, StepBackStrategy, SkeletonOfThoughtStrategy,
    PlanAndExecuteStrategy, SelfRefinementStrategy, ParadigmRouterStrategy,
    AnswerConvergenceStrategy, BudgetForcingStrategy, ...)
```

---

## 7. Data Model Changes

N/A — All data models are in-memory Python dataclasses. No database schemas.

---

## 8. API Changes

### 8.1 `VidbyteSDK` (no change to constructor)

The root client's `__init__` is unchanged. All new functionality is accessible via namespace clients or direct imports.

### 8.2 New public imports

```python
# Prompt system (new)
from vidbyte import BasePrompt, PromptKey, PromptRegistry, RenderedPrompt

# Strategies (new)
from vidbyte import (
    ReActStrategy, ReflexionStrategy, TreeOfThoughtsStrategy,
    ChainOfThoughtStrategy, SelfRefinementStrategy, PlanAndExecuteStrategy,
    SelfConsistencyStrategy, BudgetForcingStrategy, AnswerConvergenceStrategy,
    ParadigmRouterStrategy, StepBackStrategy, ChainOfDraftStrategy
)

# Conditional harnesses (new)
from vidbyte.harnesses import ConditionalLoopAgentHarness, ConditionalStoppingEvaluator

# Filesystem tools (new)
from vidbyte.tools.filesystem import ReadTextTool, WriteTextTool, AppendTextTool, DeleteTool, ...

# Providers (new)
from vidbyte.providers import AnthropicProvider, OpenAIProvider, GeminiProvider, XAIProvider

# Agent-first model execution (new)
from vidbyte import AgentInput, BaseAgent, ModelModality
```

---

## 9. File Change Manifest

> Legend: **M** = Modify (manual merge), **A** = Add (checkout from branch), **K** = Keep (from PR15 merge)

### 9.1 Manual-merge files (~10 files)

| Action | File | Source |
|--------|------|--------|
| M | `vidbyte/__init__.py` | PR15 base + PR10/12 prompt/strategy exports |
| M | `vidbyte/lib/errors/base.py` | Union of PR12 + PR15 error classes |
| M | `vidbyte/lib/errors/__init__.py` | Re-export merged errors |
| M | `vidbyte/lib/dataclasses/__init__.py` | Union of PR12 + PR15 dataclass modules |
| M | `vidbyte/lib/enums/__init__.py` | Union of PR15 + PR12 enum modules |
| M | `vidbyte/strategies/__init__.py` | Union of PR10 + PR12 + PR15 strategy exports |
| M | `vidbyte/strategies/base.py` | PR15 async BaseStrategy + PR12 BaseStrategyUtils |
| M | `vidbyte/harnesses/__init__.py` | PR15 base + PR10 conditional harness exports |
| M | `vidbyte/prompts/__init__.py` | Union of PR10 + PR12 + PR15 prompt exports |
| M | `vidbyte/prompts/registry.py` | PR10 thread-safe PromptRegistry + PR15 prompt_registry alias |
| M | `vidbyte/lib/tools/__init__.py` | PR15 ToolsFormatter + PR12 filesystem tools |

### 9.2 Kept from PR15 merge (~90 files)

| Action | File |
|--------|------|
| K | `vidbyte/agents/__init__.py` |
| K | `vidbyte/agents/base.py` |
| K | `vidbyte/agents/mixins.py` |
| K | `vidbyte/agents/registry.py` |
| K | `vidbyte/agents/types.py` |
| K | `vidbyte/context/__init__.py` |
| K | `vidbyte/client.py` |
| K | `vidbyte/harnesses/base.py` |
| K | `vidbyte/harnesses/client.py` |
| K | `vidbyte/lib/__init__.py` |
| K | `vidbyte/lib/dataclasses/agents.py` |
| K | `vidbyte/lib/dataclasses/code_search.py` |
| K | `vidbyte/lib/dataclasses/context.py` |
| K | `vidbyte/lib/dataclasses/mcp.py` |
| K | `vidbyte/lib/dataclasses/multi_agent.py` |
| K | `vidbyte/lib/dataclasses/sandbox.py` |
| K | `vidbyte/lib/dataclasses/security.py` |
| K | `vidbyte/lib/dataclasses/strategies.py` |
| K | `vidbyte/lib/dataclasses/tools.py` |
| K | `vidbyte/lib/enums/context.py` |
| K | `vidbyte/lib/tools/formatter.py` |
| K | `vidbyte/prompts/prompts/__init__.py` |
| K | `vidbyte/prompts/prompts/agent_roles.py` |
| K | `vidbyte/prompts/prompts/vmao.py` |
| K | `vidbyte/strategies/client.py` |
| K | `vidbyte/strategies/mixins.py` |
| K | `vidbyte/strategies/multi_agent/__init__.py` |
| K | `vidbyte/strategies/multi_agent/autogen.py` |
| K | `vidbyte/strategies/multi_agent/base.py` |
| K | `vidbyte/strategies/multi_agent/consensus.py` |
| K | `vidbyte/strategies/multi_agent/economic_gate.py` |
| K | `vidbyte/strategies/multi_agent/evolving.py` |
| K | `vidbyte/strategies/multi_agent/types.py` |
| K | `vidbyte/strategies/multi_agent/vmao.py` |
| K | `vidbyte/strategies/types.py` |
| K | `vidbyte/tools/base.py` |
| K | `vidbyte/tools/builtins/__init__.py` |
| K | `vidbyte/tools/builtins/code_search/__init__.py` |
| K | `vidbyte/tools/builtins/code_search/base.py` |
| K | `vidbyte/tools/builtins/code_search/glob.py` |
| K | `vidbyte/tools/builtins/code_search/grep.py` |
| K | `vidbyte/tools/builtins/code_search/semantic.py` |
| K | `vidbyte/tools/builtins/context/__init__.py` |
| K | `vidbyte/tools/builtins/context/compaction.py` |
| K | `vidbyte/tools/builtins/context/types.py` |
| K | `vidbyte/tools/builtins/editing/__init__.py` |
| K | `vidbyte/tools/builtins/editing/patch.py` |
| K | `vidbyte/tools/client.py` |
| K | `vidbyte/tools/executor.py` |
| K | `vidbyte/tools/mcp/__init__.py` |
| K | `vidbyte/tools/mcp/attach.py` |
| K | `vidbyte/tools/mcp/bridge.py` |
| K | `vidbyte/tools/mcp/client.py` |
| K | `vidbyte/tools/mcp/transport.py` |
| K | `vidbyte/tools/mcp/types.py` |
| K | `vidbyte/tools/registry.py` |
| K | `vidbyte/tools/security/__init__.py` |
| K | `vidbyte/tools/security/permissions.py` |
| K | `vidbyte/tools/security/sandbox.py` |
| K | `vidbyte/tools/types.py` |
| K | `README.md` |
| K | `skills/vidbyte-sdk/SKILL.md` |
| K | `tests/test_agent_base.py` |
| K | `tests/test_agent_registry.py` |
| K | `tests/test_autogen_conversation.py` |
| K | `tests/test_code_search_tools.py` |
| K | `tests/test_context_compaction_tools.py` |
| K | `tests/test_context_dataclasses.py` |
| K | `tests/test_economic_gate.py` |
| K | `tests/test_evolving_orchestration.py` |
| K | `tests/test_mcp_attachment.py` |
| K | `tests/test_mcp_bridge.py` |
| K | `tests/test_multi_agent_consensus.py` |
| K | `tests/test_patch_tool.py` |
| K | `tests/test_security_executor.py` |
| K | `tests/test_strategy_mixin.py` |
| K | `tests/test_tool_core.py` |
| K | `tests/test_vmao.py` |
| K | `docs/design/advanced-tool-ecosystem.md` |
| K | `docs/design/mcp-server-attachment.md` |
| K | `docs/design/multi-agent-orchestration-strategies.md` |

### 9.3 Added from PR10 (~27 files)

| Action | File |
|--------|------|
| A | `vidbyte/prompts/types.py` |
| A | `vidbyte/prompts/base.py` |
| A | `vidbyte/prompts/builtins/__init__.py` |
| A | `vidbyte/prompts/builtins/vidbyte_defaults.py` |
| A | `vidbyte/prompts/translations/__init__.py` |
| A | `vidbyte/prompts/translations/strategies/__init__.py` |
| A | `vidbyte/prompts/translations/strategies/react.py` |
| A | `vidbyte/prompts/translations/strategies/reflexion.py` |
| A | `vidbyte/prompts/translations/strategies/self_consistency.py` |
| A | `vidbyte/prompts/translations/strategies/step_back.py` |
| A | `vidbyte/prompts/translations/strategies/tree_of_thoughts.py` |
| A | `vidbyte/prompts/translations/harnesses/__init__.py` |
| A | `vidbyte/prompts/translations/harnesses/conditional/__init__.py` |
| A | `vidbyte/prompts/translations/harnesses/conditional/loop_agent.py` |
| A | `vidbyte/prompts/translations/harnesses/conditional/stopping_evaluator.py` |
| A | `vidbyte/harnesses/conditional/__init__.py` |
| A | `vidbyte/harnesses/conditional/loop_agent.py` |
| A | `vidbyte/harnesses/conditional/stopping_evaluator.py` |
| A | `vidbyte/strategies/react.py` |
| A | `vidbyte/strategies/reflexion.py` |
| A | `vidbyte/strategies/tree_of_thoughts.py` |
| A | `vidbyte/tools/builtins/calculator.py` |
| A | `vidbyte/tools/builtins/web_search.py` |
| A | `vidbyte/tools/builtins/code_execution.py` |
| A | `vidbyte/tools/builtins/document_retrieval.py` |
| A | `tests/__init__.py` |
| A | `tests/test_agent_abstractions.py` |
| A | `docs/design/agent-abstractions.md` |

### 9.4 Added from PR11 (3 files)

| Action | File |
|--------|------|
| A | `vidbyte/strategies/agent_loops/self_refinement.py` |
| A | `vidbyte/prompts/strategies/self_refinement.py` |
| A | `tests/test_self_refinement_strategy.py` |

### 9.5 Added from PR12 (~70 files)

| Action | File |
|--------|------|
| A | `vidbyte/providers/__init__.py` |
| A | `vidbyte/providers/anthropic.py` |
| A | `vidbyte/providers/openai.py` |
| A | `vidbyte/providers/gemini.py` |
| A | `vidbyte/providers/xai.py` |
| A | `vidbyte/providers/compatible.py` |
| A | `vidbyte/lib/config/__init__.py` |
| A | `vidbyte/lib/config/base.py` |
| A | `vidbyte/lib/config/models.py` |
| A | `vidbyte/lib/config/constants.py` |
| A | `vidbyte/lib/http/__init__.py` |
| A | `vidbyte/lib/http/parser.py` |
| A | `vidbyte/lib/http/transport.py` |
| A | `vidbyte/lib/prompts/__init__.py` |
| A | `vidbyte/lib/prompts/registry.py` |
| A | `vidbyte/lib/runners/__init__.py` |
| A | `vidbyte/lib/runners/base.py` |
| A | `vidbyte/lib/runners/text.py` |
| A | `vidbyte/lib/runners/image.py` |
| A | `vidbyte/lib/runners/video.py` |
| A | `vidbyte/lib/runners/types.py` |
| A | `vidbyte/lib/tools/filesystem/__init__.py` |
| A | `vidbyte/lib/tools/filesystem/backends/__init__.py` |
| A | `vidbyte/lib/tools/filesystem/backends/base.py` |
| A | `vidbyte/lib/tools/filesystem/backends/local.py` |
| A | `vidbyte/lib/tools/filesystem/permissions.py` |
| A | `vidbyte/lib/dataclasses/filesystem.py` |
| A | `vidbyte/lib/dataclasses/model_configs.py` |
| A | `vidbyte/lib/dataclasses/strategy_types.py` |
| A | `vidbyte/lib/dataclasses/tool_types.py` |
| A | `vidbyte/lib/enums/model_provider.py` |
| A | `vidbyte/lib/enums/platform.py` |
| A | `vidbyte/tools/filesystem/__init__.py` |
| A | `vidbyte/tools/filesystem/_base_tool.py` |
| A | `vidbyte/tools/filesystem/base.py` |
| A | `vidbyte/tools/filesystem/list_dir.py` |
| A | `vidbyte/tools/filesystem/make_dir.py` |
| A | `vidbyte/tools/filesystem/read_text.py` |
| A | `vidbyte/tools/filesystem/write_text.py` |
| A | `vidbyte/tools/filesystem/append_text.py` |
| A | `vidbyte/tools/filesystem/copy.py` |
| A | `vidbyte/tools/filesystem/delete.py` |
| A | `vidbyte/tools/filesystem/diff.py` |
| A | `vidbyte/tools/filesystem/find.py` |
| A | `vidbyte/tools/filesystem/move.py` |
| A | `vidbyte/tools/filesystem/read_binary.py` |
| A | `vidbyte/tools/filesystem/stat.py` |
| A | `vidbyte/tools/filesystem/zip_tools.py` |
| A | `vidbyte/strategies/agent_loops/__init__.py` |
| A | `vidbyte/strategies/agent_loops/plan_and_execute.py` |
| A | `vidbyte/strategies/reasoning/__init__.py` |
| A | `vidbyte/strategies/reasoning/chain_of_draft.py` |
| A | `vidbyte/strategies/reasoning/chain_of_thought.py` |
| A | `vidbyte/strategies/reasoning/skeleton_of_thought.py` |
| A | `vidbyte/strategies/reasoning/step_back.py` |
| A | `vidbyte/strategies/routing/__init__.py` |
| A | `vidbyte/strategies/routing/paradigm_router.py` |
| A | `vidbyte/strategies/sampling/__init__.py` |
| A | `vidbyte/strategies/sampling/self_consistency.py` |
| A | `vidbyte/strategies/sampling/answer_convergence.py` |
| A | `vidbyte/strategies/sampling/budget_forcing.py` |
| A | `vidbyte/prompts/strategies/__init__.py` |
| A | `vidbyte/prompts/strategies/strategy_prompts.py` |
| A | `vidbyte/prompts/prompts/agentic_rag.json` |
| A | `vidbyte/prompts/prompts/answer_convergence.json` |
| A | `vidbyte/prompts/prompts/budget_forcing.json` |
| A | `vidbyte/prompts/prompts/chain_of_draft.json` |
| A | `vidbyte/prompts/prompts/chain_of_thought.json` |
| A | `vidbyte/prompts/prompts/context_engineering.json` |
| A | `vidbyte/prompts/prompts/expert_prompting.json` |
| A | `vidbyte/prompts/prompts/multi_agent_reflexion.json` |
| A | `vidbyte/prompts/prompts/paradigm_router.json` |
| A | `vidbyte/prompts/prompts/plan_and_execute.json` |
| A | `vidbyte/prompts/prompts/self_consistency.json` |
| A | `vidbyte/prompts/prompts/skeleton_of_thought.json` |
| A | `vidbyte/prompts/prompts/step_back.json` |
| A | `vidbyte/prompts/prompts/tree_of_thoughts.json` |
| A | `skills/vidbyte-sdk/adding-prompts.md` |
| A | `tests/test_config_validation.py` |
| A | `tests/test_filesystem_tools.py` |
| A | `tests/test_image_video_runners.py` |
| A | `tests/test_prompt_registry.py` |
| A | `tests/test_reasoning_strategies.py` |
| A | `tests/test_sampling_strategies.py` |
| A | `tests/test_strategy_router.py` |
| A | `tests/test_text_model_runner.py` |
| A | `docs/design/prompt-api-strategies-sdk.md` |

---

## 10. Testing Plan

### Unit Tests

All existing tests from all PRs must pass without modification:

**From PR15:** test_agent_base, test_agent_registry, test_autogen_conversation, test_code_search_tools, test_context_compaction_tools, test_context_dataclasses, test_economic_gate, test_evolving_orchestration, test_mcp_attachment, test_mcp_bridge, test_multi_agent_consensus, test_patch_tool, test_security_executor, test_strategy_mixin, test_tool_core, test_vmao

**From PR10:** test_agent_abstractions

**From PR11:** test_self_refinement_strategy

**From PR12:** test_config_validation, test_filesystem_tools, test_image_video_runners, test_prompt_registry, test_reasoning_strategies, test_sampling_strategies, test_strategy_router, test_text_model_runner

### Automated Test Commands

```bash
python -m compileall vidbyte           # must exit 0
python -m unittest discover -s tests   # all tests must pass
```

### Manual Verification

1. Import smoke: `python -c "from vidbyte import VidbyteSDK, BaseAgent, ReActStrategy, BasePrompt, PromptRegistry, ToolsFormatter; print('OK')"`
2. Prompt registry: instantiate `PromptRegistry()`, register a test prompt, override it, confirm override takes effect
3. MCP attach: confirm `McpServerHandle`, `McpServerConfig` importable
4. Strategy list: confirm `ConsensusStrategy`, `ChainOfThoughtStrategy`, `SelfRefinementStrategy`, `PlanAndExecuteStrategy` all importable

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| pydantic | >=2,<3 | Existing SDK dep (unchanged) | None |
| Python stdlib | 3.11+ | All new code uses stdlib only | None |

No new dependencies added.

---

## 12. Rollout & Deployment

- No feature flags
- This is a non-breaking additive change (new public exports only)
- Once PR 16 is merged to `main`, close PRs 10–15 with a comment linking to PR 16
- No deployment steps; this is a library package

---

## 13. Open Questions

- [ ] **`vidbyte/strategies/react.py` (PR10) vs `vidbyte/strategies/reasoning/step_back.py` (PR12)**: PR10 has standalone `step_back.py` and `self_consistency.py` as agent-abstractions skeletons. PR12 has more complete implementations in reasoning/sampling sub-packages. Should the PR10 standalone files be included as aliases, or omitted in favor of PR12's sub-packages? **Recommendation: omit PR10's standalone `step_back.py` and `self_consistency.py`; export PR12's versions instead.**
- [ ] **`vidbyte/prompts/registry.py` conflict**: PR10 defines a full class-based `PromptRegistry` (BasePrompt key-version system), while PR15 defines a simpler `PromptRegistry` + `prompt_registry` singleton for agent-role lookups. Can these coexist under the same module, or should PR15's simpler registry be moved to a submodule (e.g. `vidbyte/prompts/agent_registry.py`)? **Recommendation: keep PR10's full `PromptRegistry` as the primary; alias PR15's simpler one under a different name.**
- [ ] **Import of `vidbyte/lib/tools/__init__.py`**: PR15 only exports `ToolsFormatter`. PR12 wants to add `vidbyte/lib/tools/filesystem/`. These can coexist if `lib/tools/__init__.py` exports both.

---

## 14. Alternatives Considered

### Alternative 1: Cherry-pick individual commits
- **What**: Instead of checking out entire files, cherry-pick the relevant commits from each branch.
- **Why rejected**: The branches were built independently from `main` and have no shared commit ancestry with each other. Cherry-picking across diverged histories would produce conflicts identical to the file-checkout approach but with worse tooling support.

### Alternative 2: Pick the "best" branch and discard others
- **What**: Use only PR15 (most complete) and throw away PR10/11/12 content.
- **Why rejected**: PR10 contains the class-based PromptRegistry and ConditionalHarnesses that PR15 lacks. PR12 contains providers, runners, HTTP transport, filesystem tools, and reasoning strategies that are entirely absent from PR15. Discarding these loses significant implemented functionality.

### Alternative 3: Sequential merge (PR10 → PR11 → PR12 → PR13 → PR14 → PR15)
- **What**: Merge the PRs in order, resolving conflicts at each step.
- **Why rejected**: PRs 13, 14, 15 form a superset chain (13⊂15, 14⊂15). Merging all six sequentially would produce redundant conflict-resolution work for content already resolved in PR15. The chosen approach (PR15 as base, unique content added from PR10/11/12) minimizes conflict surface.
