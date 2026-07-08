# Design Doc: Remove BaseAgent Aggregation Configuration

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Remove the legacy transparent aggregation configuration path from `BaseAgent`/`Agent` while keeping the first-class `AggregateAgent` API intact. After this change, developers cannot activate aggregation by passing `model_name=[...]`, `proposers=...`, `aggregator=...`, or `aggregate=...` to the base agent class; multi-model aggregation remains available only through the dedicated aggregation agent/factory.

---

## 2. Goals & Non-Goals

### Goals

- Remove `BaseAgent` constructor parameters that configure transparent aggregation: `proposers`, `aggregator`, and `aggregate`.
- Change `BaseAgent.model_name` to accept only `str | None` and reject list/tuple/sequence values at runtime with a clear `ConfigurationError`.
- Delete the internal BaseAgent aggregation plan/delegation logic: `_aggregate_agent`, `_aggregate_plan`, `_resolve_aggregate_plan`, `_build_aggregate_agent`, `_first_spec_model`, and the early `generate_reply` delegation branch.
- Keep `AggregateAgent`, `MultiProviderAggregator`, `ProposerSpec`, `AggregateConfig`, top-level exports, and `sdk.agents.aggregate(...)` available as the explicit aggregation surface.
- Update tests and developer-facing text that currently describe or assert the removed BaseAgent overload.
- Preserve existing single-model BaseAgent behavior, modality detection, runner creation, middleware/runtime validation, forking, and tool execution.

### Non-Goals

- Removing `AggregateAgent`, `MultiProviderAggregator`, aggregation prompt assets, `ProposerSpec`, or `AggregateConfig`.
- Changing aggregation engine behavior, candidate synthesis, proposer failure handling, or `AggregateAgent.as_tool()`.
- Adding a replacement hidden BaseAgent aggregation shortcut under another parameter name.
- Refactoring unrelated agent runtime, provider, tool, context, MCP, trace, eval, or pipeline code.
- Changing historical design docs wholesale beyond targeted stale references needed to avoid misleading future implementation work.

---

## 3. Background & Context

The repo is a Python 3.11+ SDK (`pyproject.toml`) using dataclasses, Pydantic, `httpx`, and `unittest`. Public package exports flow through `vidbyte/__init__.py`, package-level agent exports through `vidbyte/agents/__init__.py`, and namespace factories through `vidbyte/agents/client.py`.

`BaseAgent` in `vidbyte/agents/base.py` is the core developer-facing agent class. It currently accepts `model_name: str | Sequence[str] | None`, plus `proposers`, `aggregator`, and `aggregate`. During construction it resolves an internal aggregate plan, builds an internal `AggregateAgent`, and `generate_reply()` delegates to that child before the normal runtime path. This is the feature being removed.

The dedicated aggregation implementation already exists in `vidbyte/agents/aggregation.py`: `MultiProviderAggregator` fans out proposer agents, `AggregateAgent` owns proposer/aggregator child agents, and `AgentClient.aggregate()` constructs it explicitly. This matches the requested architecture: proposer/aggregator logic lives in separate agent classes rather than hidden inside BaseAgent.

Existing tests in `tests/test_aggregate_agent.py` include both the dedicated aggregation tests and a `BaseAgentOverloadTests` class that asserts the old overload works. Those tests must be updated because they currently preserve the behavior being removed. The repo also has a dirty working tree with unrelated untracked files; implementation must avoid reverting or editing unrelated changes.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__` must no longer declare or accept `proposers`, `aggregator`, or `aggregate` keyword arguments.
2. Passing `proposers=...`, `aggregator=...`, or `aggregate=...` to `BaseAgent` or `Agent` must fail as an unexpected keyword argument.
3. `BaseAgent.__init__` must declare `model_name: str | None = None`, not `str | Sequence[str] | None`.
4. Passing a list, tuple, or other non-string sequence as `model_name` to `BaseAgent` must raise `ConfigurationError` before runner creation.
5. A single-element model list such as `model_name=["gpt-4.1"]` must also be rejected; it must not be unwrapped into a single-model configuration.
6. `BaseAgent.generate_reply()` must no longer delegate to an internal aggregate agent.
7. `BaseAgent` instances must no longer create or store `_aggregate_agent` or `_aggregate_plan`.
8. Single string `model_name` and `model_name=None` behavior must remain unchanged.
9. `BaseAgent.fork()` must keep passing only the normalized string/None `runner_config.model_name` into the child.
10. `AggregateAgent` must continue to construct child `BaseAgent`s with single string model names.
11. `sdk.agents.aggregate(...)`, `AggregateAgent`, `MultiProviderAggregator`, `ProposerSpec`, and `AggregateConfig` must remain importable and usable.
12. Tests that currently assert BaseAgent aggregation activation must be removed or replaced with tests asserting BaseAgent rejects multi-model configuration.
13. Module and test docstrings must stop saying aggregation is reused by or native to BaseAgent.
14. Public usage guidance must not show `Agent`/`BaseAgent` accepting multiple model names.

### Non-Functional Requirements

- **Performance:** No new runtime overhead on normal BaseAgent construction or `generate_reply`; removing plan detection should slightly simplify construction.
- **Scalability:** N/A - this removes a construction path and does not add execution fan-out.
- **Security:** No new permissions, credential handling, tools, or external calls.
- **Observability:** No new tracing spans. Existing `AggregateAgent` metadata stays unchanged.
- **Reliability / error tolerance:** Invalid multi-model BaseAgent configuration must fail fast with an explicit `ConfigurationError` rather than reaching provider/modality code with a list value.
- **Compatibility:** This is an intentional breaking change for callers using the hidden BaseAgent overload. Dedicated `AggregateAgent` callers remain compatible.

---

## 5. High-Level Design

The implementation narrows BaseAgent back to a single-agent constructor. `BaseAgent.__init__` will remove aggregation-specific kwargs and imports, validate that `model_name` is not a sequence, and then proceed directly into the existing `AgentRunnerConfig` setup. The normal runner/modality/runtime flow remains the only `generate_reply()` path.

The dedicated aggregation layer remains the explicit path:

```text
Before:
BaseAgent(model_name=[...]) -> internal AggregateAgent -> MultiProviderAggregator
BaseAgent(proposers=...)    -> internal AggregateAgent -> MultiProviderAggregator
AggregateAgent(...)         -> MultiProviderAggregator

After:
BaseAgent(model_name="...") -> normal single-agent runtime
BaseAgent(model_name=[...]) -> ConfigurationError
BaseAgent(proposers=...)    -> TypeError
AggregateAgent(...)         -> MultiProviderAggregator
```

This keeps orchestration boundaries clear: `BaseAgent` handles one configured model/runner; `AggregateAgent` handles proposer fan-out and synthesis. It also makes API failure modes obvious instead of silently changing `agent.arun(...)` into a multi-agent run based on constructor shape.

---

## 6. Detailed Design

### 6.1 BaseAgent Constructor Cleanup

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Removes aggregation configuration from the base agent constructor and ensures `model_name` is a single model identifier.

#### Interface / API

```python
class BaseAgent(McpAttachableMixin):
    def __init__(self, *, name: str, system_prompt: str, runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR, runner: object | None = None, runners: Mapping[ModelModality | str, object] | None = None, tools: Sequence[object] | Tools = (), permission_policy: PermissionPolicy | None = None, agent_loop_settings: AgentLoopSettings | None = None, max_tool_rounds: int | None = None, max_iterations: int | None = None, max_tokens: int | None = None, compaction_trigger_tokens: int | None = None, compaction_target_tokens: int | None = None, middleware: Sequence[AgentMiddleware] = (), api_key: str | None = None, provider: ModelProvider | str | None = None, model_name: str | None = None, modality: ModelModality | str = ModelModality.AUTO, temperature: float | None = None, run_id: str | None = None, runner_options: dict[str, Any] | None = None, description: str = "", capabilities: Sequence[str] = (), agent_metadata: AgentMetadata | None = None, context_items: Sequence[ContextItem] = (), context_manager: ContextManager | None = None, algorithm: ContextWindowAlgorithm | str | None = None, metadata: dict[str, Any] | None = None, tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None, output_schema: type | Mapping[str, Any] | None = None, handoff: Handoff | None = None, trace_option: TraceOption | None = None) -> None:
```

#### Logic / Algorithm

1. Remove `AggregateConfig` and `ProposerSpec` imports from `base.py`.
2. Remove `proposers`, `aggregator`, and `aggregate` from the constructor signature.
3. Add a small validation step before `AgentRunnerConfig` is created:
   - if `model_name is not None and not isinstance(model_name, str)`, raise `ConfigurationError("BaseAgent model_name must be a single model name string; use AggregateAgent for multi-model aggregation.")`.
4. Remove `_aggregate_agent` and `_aggregate_plan` initialization.
5. Remove the non-linear-runtime aggregation compatibility guard, since BaseAgent can no longer create aggregate plans.
6. Keep existing non-linear runtime guards for middleware, continual tracing, and non-default context-window algorithms.
7. Pass the validated `model_name` unchanged into `AgentRunnerConfig`.

#### Edge Cases & Error Handling

- `model_name=["only"]` raises `ConfigurationError`; no unwrapping.
- `model_name=("a", "b")` raises `ConfigurationError`.
- `model_name=123` raises `ConfigurationError` because it is not a string.
- `proposers=...`, `aggregator=...`, and `aggregate=...` raise Python's standard unexpected-keyword `TypeError`.

---

### 6.2 BaseAgent Aggregation Method Removal

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Deletes private methods that only existed to support transparent BaseAgent aggregation.

#### Interface / API

```python
# Removed:
# def _resolve_aggregate_plan(...) -> tuple[dict[str, Any] | None, str | None]: ...
# def _build_aggregate_agent(self) -> BaseAgent: ...
# def _first_spec_model(specs: Sequence[Any]) -> str | None: ...
```

#### Logic / Algorithm

1. Delete `_resolve_aggregate_plan`.
2. Delete `_build_aggregate_agent`.
3. Delete `_first_spec_model`.
4. Confirm no remaining references to `_aggregate_plan`, `_aggregate_agent`, `AggregateConfig`, or `ProposerSpec` in `base.py`.

#### Edge Cases & Error Handling

- N/A - removed private code paths are no longer reachable.

---

### 6.3 BaseAgent Generate Reply Path

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Ensures `generate_reply()` always uses the normal BaseAgent runtime path.

#### Interface / API

```python
async def generate_reply(self, message: str | AgentInput, *, modality: ModelModality | str | None = None, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage:
```

#### Logic / Algorithm

1. Remove the first-branch delegation:
   ```python
   if self._aggregate_agent is not None:
       return await self._aggregate_agent.generate_reply(...)
   ```
2. Leave `_ensure_mcp_connected()`, input normalization, modality resolution, tracing, context building, runtime invocation, history updates, handoff handling, and metadata handling unchanged.

#### Edge Cases & Error Handling

- Normal no-runner behavior remains `AgentExecutionError("Agent requires a runner.")`.
- Modality detection continues to receive only `str | None` model names because constructor validation now rejects other shapes.

---

### 6.4 AggregateAgent Documentation Cleanup

**File(s):** `vidbyte/agents/aggregation.py`
**Type:** Modified

#### What it does

Updates module-level comments so the dedicated aggregation module no longer claims it is reused by BaseAgent's native overload.

#### Interface / API

```python
# No public API changes.
```

#### Logic / Algorithm

1. Replace references such as "Reused by BaseAgent's native multi-model overload" with language describing `AggregateAgent` as the explicit aggregation surface.
2. Do not alter aggregation engine behavior or class signatures.

#### Edge Cases & Error Handling

- N/A - documentation-only change in this component.

---

### 6.5 Tests and Verification Artifacts

**File(s):** `tests/test_aggregate_agent.py`, `scripts/test_aggregate_agent.py`, `tests/test_agent_base.py`
**Type:** Modified

#### What it does

Updates existing offline tests so the suite reflects the removed BaseAgent overload while retaining coverage for dedicated aggregation.

#### Interface / API

```python
class BaseAgentAggregationRemovalTests(unittest.TestCase):
    def test_model_name_list_rejected(self) -> None: ...
    def test_single_element_model_name_list_rejected(self) -> None: ...
    def test_proposers_keyword_rejected(self) -> None: ...
```

#### Logic / Algorithm

1. In `tests/test_aggregate_agent.py`, update the file docstring to remove claims about BaseAgent's native overload.
2. Remove `BaseAgentOverloadTests` tests that assert `_aggregate_agent` exists or `generate_reply()` delegates to aggregation.
3. Add rejection tests for list-valued `model_name` and unexpected aggregation kwargs on `BaseAgent`.
4. Keep all `MultiProviderAggregator`, `AggregateAgent`, prompt catalog, and export tests.
5. Update `scripts/test_aggregate_agent.py` wording if it describes the old BaseAgent overload; the script can continue loading `tests.test_aggregate_agent`.
6. Optionally place BaseAgent-specific rejection tests in `tests/test_agent_base.py` if that is cleaner than keeping them in the aggregation suite.

#### Edge Cases & Error Handling

- The test for unexpected kwargs should assert `TypeError`, not `ConfigurationError`, because the signature no longer accepts those names.
- The test for list model names should assert `ConfigurationError`, including the single-element list case.

---

### 6.6 Indirect Model Name Type Cleanup

**File(s):** `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/types.py`
**Type:** Modified

#### What it does

Removes stale type hints that allow model-name sequences in settings that are later passed into `BaseAgent`.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class MultiplePromptFanoutSettings:
    splitter_model_name: str | None = None
    implementation_model_name: str | None = None
```

#### Logic / Algorithm

1. Change `splitter_model_name` and `implementation_model_name` type hints from `str | Sequence[str] | None` to `str | None`.
2. Add validation in `__post_init__` rejecting non-string non-None values with `ConfigurationError`.
3. Leave harness construction logic unchanged; it will pass only validated single model names to BaseAgent.

#### Edge Cases & Error Handling

- Existing callers using string model names are unaffected.
- Existing callers using list model names through this harness receive a clear configuration error before agent construction.

---

## 7. Data Model Changes

### 7.1 AgentRunnerConfig

**Change type:** N/A - no schema change

```python
@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    model_name: str | None = None
```

**Migration strategy:** N/A - this field is already `str | None`; the change aligns BaseAgent inputs with the existing data contract.

### 7.2 AggregateConfig and ProposerSpec

**Change type:** N/A - retained

```python
@dataclass(frozen=True, slots=True)
class ProposerSpec:
    provider: str
    model: str

@dataclass(frozen=True, slots=True)
class AggregateConfig:
    min_successful: int = 1
```

**Migration strategy:** N/A - dedicated aggregation APIs continue using these types.

---

## 8. API Changes

### 8.1 Python API: `BaseAgent` / `Agent`

**Change type:** Modified

**Request:**

```json
{
  "model_name": "str | None - a single model id only",
  "proposers": "removed",
  "aggregator": "removed",
  "aggregate": "removed"
}
```

**Response:**

```json
{
  "single_model": "constructs a normal BaseAgent",
  "model_name_sequence": "raises ConfigurationError",
  "aggregation_kwargs": "raises TypeError"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `model_name` is list/tuple/sequence or otherwise not a string/None -> `ConfigurationError` |
| N/A | `proposers`, `aggregator`, or `aggregate` passed to `BaseAgent` -> `TypeError` |

### 8.2 Python API: `AggregateAgent`

**Change type:** N/A - unchanged

**Request:**

```json
{
  "proposers": "Sequence[ProposerSpec | tuple | agent-like]",
  "aggregator": "ProposerSpec | tuple | agent-like | None",
  "config": "AggregateConfig | None"
}
```

**Response:**

```json
{
  "reply": "AgentMessage with aggregate metadata"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Existing AggregateAgent validation errors remain unchanged |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/remove-base-agent-aggregation.md` | Approval design doc for the removal |
| MODIFY | `vidbyte/agents/base.py` | Remove BaseAgent aggregation kwargs, plan construction, delegate path, and sequence model handling |
| MODIFY | `vidbyte/agents/aggregation.py` | Remove stale docstring reference to BaseAgent native overload |
| MODIFY | `tests/test_aggregate_agent.py` | Replace old BaseAgent overload assertions with removal/rejection assertions while preserving AggregateAgent coverage |
| MODIFY | `scripts/test_aggregate_agent.py` | Update script wording if it references the old BaseAgent overload |
| MODIFY | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/types.py` | Align indirect model-name settings with BaseAgent single-model contract |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `collections.abc.Sequence` | Python 3.11+ | Existing type import remains needed elsewhere in `base.py`; used to detect invalid model-name sequences if desired | Low |
| Existing `ConfigurationError` | In-repo | Clear fast failure for list-valued `model_name` | Low |

No new third-party packages or external services.

---

## 11. Rollout & Deployment

- This is an intentional breaking Python API cleanup.
- No feature flag is needed because the removed behavior is construction-time SDK behavior.
- Migration path: callers using hidden BaseAgent aggregation must switch to `AggregateAgent(...)` or `sdk.agents.aggregate(...)`.
- Deployment order: normal SDK release process only.
- Rollback procedure: revert the implementation PR to restore the BaseAgent overload.

---

## 12. Open Questions

- [ ] Should historical `docs/design/aggregate-agent.md` be edited to mark the BaseAgent overload sections as superseded, or should the new design doc alone serve as the supersession record?
- [ ] Should `BaseAgent(model_name=123)` raise `ConfigurationError` as designed, or should only list/tuple/sequence values be rejected while other values continue to be coerced elsewhere?

---

## 13. Alternatives Considered

### Alternative 1: Keep kwargs but raise ConfigurationError

- What: Leave `proposers`, `aggregator`, and `aggregate` in the BaseAgent signature and raise `ConfigurationError` if callers pass them.
- Why rejected: The request is to remove these parameter configurations entirely from the base agent class. Keeping them in the signature preserves the API shape and suggests the feature still belongs there.

### Alternative 2: Silently coerce single-element model lists

- What: Continue accepting `model_name=["gpt-4.1"]` and unwrap it to `"gpt-4.1"` while rejecting longer lists.
- Why rejected: The requested rule is that devs should no longer be able to pass multiple models to the agent class, and retaining list acceptance keeps the old mental model alive. A strict string-only contract is clearer.

### Alternative 3: Remove all aggregation APIs

- What: Delete `AggregateAgent`, `MultiProviderAggregator`, `ProposerSpec`, prompt assets, exports, and tests.
- Why rejected: The user explicitly said aggregator/proposer logic has moved to separate agent classes. The desired change is removing BaseAgent configuration/delegation, not removing the dedicated aggregation classes.

