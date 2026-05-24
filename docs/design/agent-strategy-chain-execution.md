# Design Doc: Agent Strategy Chain Execution

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-24
**Last Updated:** 2026-05-24

---

## 1. Overview

This feature makes prompt-engineering strategies a first-class alternative to the default agentic tool loop. Agents with no strategy continue to run the existing `AgentRuntime` loop with `isDone`, tool schemas, middleware hooks, and agentic-loop instructions. Agents configured with one or more strategies bypass that loop and execute the strategy recipe directly. When multiple strategies are supplied, they run sequentially and pass only the previous strategy's textual `StrategyResult.output` into the next strategy.

---

## 2. Goals & Non-Goals

### Goals

- Add a public `strategies` constructor parameter to `Agent` / `BaseAgent`.
- Preserve the existing `strategy` parameter for backward compatibility.
- Reject ambiguous construction when both `strategy` and `strategies` are supplied.
- Normalize `strategies=[a, b, c]` into a sequential strategy chain.
- Ensure chained strategies pass only output text between stages.
- Ensure strategy-backed agents do not append the agentic-loop prompt and do not expose the internal `isDone` tool in strategy context.
- Keep no-strategy agents on the existing direct tool loop behavior.
- Bridge existing synchronous strategy implementations so they can be executed through the agent's async `arun()` path.
- Update tests and README examples to document the new strategy semantics.

### Non-Goals

- Do not remove the existing `strategy` parameter in this change.
- Do not remove or redesign `AgentRuntime`.
- Do not change multi-agent orchestration strategies such as consensus, AutoGen, VMAO, economic gate, or evolving policy routing.
- Do not make `strategies=[...]` mean consensus, voting, routing, parallel execution, or multi-agent orchestration.
- Do not add persistence, database migrations, external network services, or feature flags.
- Do not redesign pipelines; pipelines still compose agents and pipelines, while strategies compose prompt-engineering behavior inside one agent execution.

---

## 3. Background & Context

- The SDK already has `BaseAgent(strategy=...)`, and `BaseAgent.generate_reply()` already branches between strategy execution and `_run_without_strategy()`.
- The current context builder lives in `AgentRuntime.build_context()` and always appends `append_agentic_loop_prompt(system_prompt)`.
- `AgentRuntime` also wraps agent tools with internal loop tools, including `isDone`, at runtime construction.
- `BaseStrategy._run_model()` currently appends the agentic-loop prompt to strategy model calls, which leaks loop behavior into non-loop prompt-engineering strategies.
- Many concrete strategies, especially under `vidbyte/strategies/reasoning/` and `vidbyte/strategies/sampling/`, implement synchronous `run()` but not async `arun()`. Agents currently call `strategy.arun()`, so the implementation needs an async bridge to reuse these existing strategies.
- `StrategyMixin.with_strategies()` currently wraps multiple strategies in `MultiAgentConsensusStrategy`. That helper is a separate host-object mixin, not the `Agent` constructor API, and this feature should avoid changing its behavior unless documentation notes the distinction.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__` must accept `strategies: Sequence[BaseStrategy] | None = None`.
2. Passing both `strategy` and `strategies` must raise `ConfigurationError`.
3. Passing `strategies=[]` must raise `ConfigurationError`.
4. Passing `strategies=[single]` must use that strategy directly.
5. Passing `strategies=[a, b, c]` must execute strategies sequentially in declaration order.
6. In a strategy chain, each stage after the first receives only the previous stage's `StrategyResult.output` as its prompt.
7. Strategy chain metadata may include stage names and stage metadata, but stage input must not include prior metadata, full result objects, calls, tools, or hidden history.
8. Agents with any normalized strategy must bypass `AgentRuntime.arun()`.
9. Agents with no strategy must continue using `AgentRuntime.arun()` for text modality and single runner calls for non-text modality.
10. Strategy-backed agents must receive a context whose `system_prompt` is the base system prompt without agentic-loop instructions.
11. Strategy-backed agents must receive only user-provided tool specs in `context.tools`; internal `isDone` must not appear.
12. No-strategy direct-loop agents must continue receiving agentic-loop instructions and the internal `isDone` tool.
13. `BaseStrategy._run_model()` must not append agentic-loop instructions.
14. `BaseStrategy.arun()` must support existing synchronous strategies by calling the concrete `run()` implementation when a subclass overrides `run()` but not `arun()`.
15. `BaseAgent.from_run_id()` and `BaseAgent.fork()` must preserve the normalized strategy behavior and support the new `strategies` input.
16. Public exports must include the new strategy chain class.
17. README usage must describe `strategy` vs. `strategies` and the no-loop behavior for strategy-backed agents.

### Non-Functional Requirements

- Performance: Strategy chaining must add only lightweight Python dispatch overhead beyond the underlying model calls.
- Scalability: No new global mutable state; strategy instances remain explicit constructor inputs.
- Security: Internal loop tools must not leak into non-loop strategy context. User tools passed to strategies remain explicit and unchanged.
- Observability: Preserve `StrategyResult.metadata`; chain metadata should expose stage names and per-stage metadata.
- Reliability: Constructor validation must fail early for ambiguous or empty strategy configuration.
- Compatibility: Existing `strategy=...` callers and no-strategy tool loop callers must continue to work.

---

## 5. High-Level Design

The implementation adds a small `StrategyChain` strategy and teaches `BaseAgent` to normalize `strategy` and `strategies` constructor inputs into one executable `self.strategy`. A single strategy remains unchanged. Multiple strategies become `StrategyChain(strategies=(...))`. The chain calls each strategy in order and threads only the previous output string into the next strategy.

Context construction will distinguish agentic-loop mode from strategy mode. Loop mode keeps the current behavior: append the agentic-loop prompt and include internal loop tools such as `isDone`. Strategy mode builds a neutral context: original system prompt, history, user tool specs, and budget, without loop prompt text or internal loop tools.

The direct no-strategy path continues to use `AgentRuntime.arun()` for text agents. The strategy path bypasses `AgentRuntime.arun()` entirely and calls the normalized strategy. This gives a clean execution boundary:

```text
Agent.arun(prompt)
  |
  +-- strategy exists --> neutral context --> Strategy or StrategyChain --> AgentMessage
  |
  `-- no strategy -----> loop context -----> AgentRuntime tool loop -----> AgentMessage
```

The existing `StrategyMixin.with_strategies()` remains a consensus helper for mixin hosts. The new `Agent(strategies=[...])` API has different semantics by design: it is sequential output chaining, not consensus.

---

## 6. Detailed Design

### 6.1 BaseAgent Constructor and Normalization

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds the public `strategies` parameter and centralizes validation/normalization into a helper used by construction and forking.

#### Interface / API

```python
class BaseAgent(McpAttachableMixin):
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        strategy: BaseStrategy | None = None,
        strategies: Sequence[BaseStrategy] | None = None,
        ...
    ) -> None: ...

    @staticmethod
    def _normalize_strategy(
        strategy: BaseStrategy | None,
        strategies: Sequence[BaseStrategy] | None,
    ) -> BaseStrategy | None: ...
```

#### Logic / Algorithm

1. Validate `name` and `system_prompt` as today.
2. Call `_normalize_strategy(strategy, strategies)`.
3. If both are provided, raise `ConfigurationError`.
4. If `strategies is None`, return `strategy`.
5. Convert `strategies` to a tuple.
6. If tuple is empty, raise `ConfigurationError`.
7. If tuple length is one, return that strategy.
8. Otherwise return `StrategyChain(strategies=tuple_value)`.
9. Store the result in `self.strategy`.

#### Edge Cases & Error Handling

- `strategies=[]`: fail early with `ConfigurationError`.
- `strategy=...` and `strategies=[...]`: fail early with `ConfigurationError`.
- Non-`BaseStrategy` items are not explicitly runtime-checked in the first implementation; type hints and failures at execution remain consistent with existing loose SDK style.

---

### 6.2 BaseAgent Strategy Execution Context

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Ensures strategy-backed agents use neutral context while no-strategy agents use loop context.

#### Interface / API

```python
def _build_context(
    self,
    message: str,
    *,
    context: StrategyContext | None,
    history: Sequence[AgentMessage],
    input_metadata: Mapping[str, Any] | None = None,
    modality: ModelModality | None = None,
    agentic_loop: bool = True,
) -> BaseAgentContext: ...
```

#### Logic / Algorithm

1. In `generate_reply()`, resolve prompt, modality, runner, and input metadata as today.
2. Build context with `agentic_loop=(self.strategy is None)`.
3. If `self.strategy is None`, call `_run_without_strategy()` unchanged.
4. Otherwise call `await self.strategy.arun(prompt, runner=runner, context=agent_context, tools=self._agent_tool_items, **options)`.
5. Preserve reply metadata format with `"strategy": result.strategy_name`.

#### Edge Cases & Error Handling

- Strategy execution errors continue to be wrapped in `AgentExecutionError`.
- Strategy-backed agents may run without an executable runner only if their strategy does not need one; this preserves existing strategy contract behavior.
- No-strategy agents still require an executable runner.

---

### 6.3 AgentRuntime Context Modes

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Separates user tools from runtime loop tools so context building can include or exclude agentic-loop behavior.

#### Interface / API

```python
class AgentRuntime:
    def __init__(..., tools: Tools, ...) -> None:
        self.user_tools = tools
        self.tools = with_internal_agent_tools(tools)

    def build_context(
        self,
        message: str,
        *,
        base_context: StrategyContext | None,
        history: Sequence[AgentMessage],
        agent_history: Sequence[AgentMessage],
        agent_metadata: Mapping[str, Any],
        existing_tool_calls: Sequence[ToolCallContext],
        input_metadata: Mapping[str, Any] | None = None,
        modality: ModelModality | None = None,
        agentic_loop: bool = True,
    ) -> BaseAgentContext: ...
```

#### Logic / Algorithm

1. Resolve base system prompt from provided `StrategyContext` or agent system prompt.
2. If `agentic_loop` is true, append the agentic-loop prompt.
3. If `agentic_loop` is false, leave the system prompt unchanged.
4. If `agentic_loop` is true, set `context.tools` to `self.tools.specs()` including internal loop tools.
5. If `agentic_loop` is false, set `context.tools` to `self.user_tools.specs()` only.
6. Preserve existing history and budget behavior.

#### Edge Cases & Error Handling

- Existing direct runtime tests should keep passing with default `agentic_loop=True`.
- Strategy context tests must be updated because `isDone` should no longer be present for strategy-backed agents.

---

### 6.4 StrategyChain

**File(s):** `vidbyte/strategies/chain.py`
**Type:** New file

#### What it does

Implements sequential strategy composition where output text is the only stage-to-stage input.

#### Interface / API

```python
class StrategyChain(BaseStrategy):
    name: ClassVar[str] = "strategy_chain"

    def __init__(self, strategies: Sequence[BaseStrategy]) -> None: ...

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult: ...
```

#### Logic / Algorithm

1. Validate at least one strategy.
2. Set `current = prompt`.
3. For each strategy:
   1. Execute `await strategy.arun(current, runner=runner, context=context, tools=tools, **options)`.
   2. Append the returned result to a local `results` list.
   3. Set `current = result.output`.
4. Return a `StrategyResult` whose `output` is the final `current`.
5. Set `strategy_name="strategy_chain"`.
6. Set `calls` to the tuple of stage `StrategyResult` objects.
7. Set metadata such as `stage_names`, `stage_count`, and `stages`.

#### Edge Cases & Error Handling

- Empty strategies fail in `__init__`.
- A stage failure stops the chain and propagates the underlying exception to the agent wrapper.
- No prior stage metadata is inserted into a later stage prompt.

---

### 6.5 BaseStrategy Async Bridge and Prompt Behavior

**File(s):** `vidbyte/strategies/base.py`
**Type:** Modified

#### What it does

Lets existing synchronous strategies run from agents and removes implicit agentic-loop prompt injection from strategy runner calls.

#### Interface / API

```python
class BaseStrategy:
    async def arun(...): ...

    def _run_model(self, runner: object, prompt: str, **kwargs: Any) -> Any: ...
```

#### Logic / Algorithm

1. In `BaseStrategy.arun()`, detect whether the concrete subclass overrides `run()`.
2. If it does, call `self.run(prompt, runner=runner, context=context, tools=tools, **options)`.
3. If the return value is awaitable, await it.
4. Return the resulting `StrategyResult`.
5. If no concrete `run()` exists, raise the current `NotImplementedError`.
6. In `_run_model()`, pass through `system` exactly as supplied and do not call `append_agentic_loop_prompt()`.

#### Edge Cases & Error Handling

- Calling `BaseStrategy.run()` from an active loop still raises as today.
- Concrete async strategies that override `arun()` are unaffected.
- Concrete sync strategies that require a runner continue to rely on `_resolve_runner()`.

---

### 6.6 Public Exports

**File(s):** `vidbyte/strategies/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Exports `StrategyChain` for direct use by SDK users.

#### Interface / API

```python
from vidbyte.strategies import StrategyChain
from vidbyte import StrategyChain
```

#### Logic / Algorithm

1. Import `StrategyChain` from `vidbyte.strategies.chain`.
2. Add it to `__all__`.
3. Re-export at the root SDK level if current root export patterns include strategy classes.

#### Edge Cases & Error Handling

- Avoid importing multi-agent strategies through this path to preserve existing circular import boundary.

---

### 6.7 README Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents `strategies=[...]` as sequential prompt-engineering composition and clarifies the difference from the default agentic loop.

#### Interface / API

```python
agent = Agent(
    name="writer",
    system_prompt="Write precise release notes.",
    runner=runner,
    strategies=[
        StepBackStrategy(),
        ChainOfDraftStrategy(),
    ],
)
```

#### Logic / Algorithm

1. Add a short section after the strategy example.
2. State that no-strategy agents run the agentic loop.
3. State that strategy-backed agents bypass the loop.
4. State that multiple strategies pass only output text between stages.

#### Edge Cases & Error Handling

- Existing multi-agent orchestration README text remains intact.

---

## 7. Data Model Changes

### 7.1 Persistent Data Models

**Change type:** N/A - this SDK change does not modify persistent schemas, databases, files on disk, or serialized migrations.

```python
# N/A
```

**Migration strategy:** N/A - no persistence migration.

- Forward migration: N/A.
- Rollback plan: Revert code changes.

---

## 8. API Changes

### 8.1 Python Constructor API: BaseAgent / Agent

**Change type:** Modified

**Request:**

```json
{
  "strategy": "BaseStrategy | None - existing single strategy input",
  "strategies": "Sequence[BaseStrategy] | None - new sequential strategy input"
}
```

**Response:**

```json
{
  "AgentMessage.metadata.strategy": "string - strategy name, 'strategy_chain' for multi-strategy chains"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `ConfigurationError` when both `strategy` and `strategies` are provided |
| N/A | `ConfigurationError` when `strategies` is empty |
| N/A | `AgentExecutionError` wraps strategy execution failures |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-strategy-chain-execution.md` | Design source of truth for the change |
| CREATE | `vidbyte/strategies/chain.py` | New sequential output-only strategy composition |
| CREATE | `tests/test_strategy_chain.py` | Unit tests for output-only strategy chaining |
| MODIFY | `vidbyte/agents/base.py` | Add `strategies` parameter, normalize strategy configuration, and build neutral strategy context |
| MODIFY | `vidbyte/agents/runtime.py` | Support loop and non-loop context building without leaking `isDone` into strategy context |
| MODIFY | `vidbyte/strategies/base.py` | Add async bridge for sync strategies and remove implicit agentic-loop prompt injection |
| MODIFY | `vidbyte/strategies/__init__.py` | Export `StrategyChain` |
| MODIFY | `vidbyte/__init__.py` | Re-export `StrategyChain` from the root SDK namespace |
| MODIFY | `tests/test_agent_base.py` | Cover constructor validation, strategy context without `isDone`, and no-strategy loop preservation |
| MODIFY | `tests/test_agent_tool_loop.py` | Update strategy path expectations for user tools only |
| MODIFY | `tests/test_agent_runtime.py` | Cover new `agentic_loop=False` context behavior while preserving default loop behavior |
| MODIFY | `tests/test_vmao.py` | Update VMAO verifier strategy context expectation to exclude internal `isDone` |
| MODIFY | `README.md` | Document strategy-backed no-loop execution and output-only chains |

No files will be deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_strategy_chain.py` -> `test_chain_threads_only_output_between_strategies`
- `tests/test_strategy_chain.py` -> `test_chain_metadata_records_stage_names_and_metadata`
- `tests/test_strategy_chain.py` -> `test_empty_chain_fails`
- `tests/test_agent_base.py` -> `test_agent_accepts_strategies_sequence_and_returns_chain_result`
- `tests/test_agent_base.py` -> `test_agent_rejects_strategy_and_strategies_together`
- `tests/test_agent_base.py` -> `test_agent_rejects_empty_strategies`
- `tests/test_agent_base.py` -> `test_strategy_context_excludes_agentic_loop_prompt_and_is_done`
- `tests/test_agent_base.py` -> preserve existing `test_agent_without_strategy_calls_runner_once`
- `tests/test_agent_runtime.py` -> `test_runtime_builds_non_agentic_context_without_internal_tools`
- `tests/test_agent_tool_loop.py` -> update `test_strategy_path_still_receives_tools` to verify only user tools are visible.
- `tests/test_vmao.py` -> update verifier strategy context assertion to expect no internal `isDone` tool.
- `tests/test_reasoning_strategies.py` or new agent test -> verify a sync concrete strategy can run through `await Agent(..., strategy=ChainOfThoughtStrategy()).arun(...)`.

### Integration Tests

- Run `python -m unittest discover -s tests`.
- Run `python -m compileall vidbyte`.
- Run the README smoke import command:

```bash
python -c "from vidbyte import Agent, StrategyChain, VidbyteSDK; sdk = VidbyteSDK(); print(Agent.__name__, StrategyChain.__name__, type(sdk.agents).__name__)"
```

### Manual / QA Test Cases

1. Given an agent with no strategy and a fake runner that calls `isDone`, when `agent.arun("task")` runs, then output comes from the loop final answer and runner system prompt contains the agentic-loop text.
2. Given an agent with `strategies=[AppendStrategy('a'), AppendStrategy('b')]`, when `agent.arun("x")` runs, then stage two receives exactly stage one's output string and final output is `"xab"`.
3. Given an agent with `strategy=EchoStrategy()` and a user tool, when `agent.arun("task")` runs, then context tool specs include the user tool and exclude `isDone`.
4. Given `Agent(strategy=a, strategies=[b])`, construction fails before model execution.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` from `pyproject.toml` | Runtime language | Low; existing project requirement |
| pydantic | `>=2,<3` from `pyproject.toml` | Existing SDK dependency | None for this change |
| unittest | Python standard library | Test framework | Low |

No new dependencies or external services are required.

---

## 12. Rollout & Deployment

- Feature flags: None.
- Breaking change: The intended public behavior changes for strategy-backed agents by removing agentic-loop instructions and internal `isDone` from strategy context. This is the requested semantic correction, but tests relying on `isDone` in strategy context must be updated.
- Migration path: Existing `strategy=...` callers continue to work. New callers can use `strategies=[...]` for output-only chains. Callers that want consensus should keep using `MultiAgentConsensusStrategy` explicitly.
- Deployment order: Single SDK package update.
- Rollback procedure: Revert the feature branch commits. No data migration rollback is needed.

---

## 13. Open Questions

- [ ] Should `StrategyMixin.with_strategies()` be renamed or deprecated in a future PR to avoid semantic confusion with `Agent(strategies=[...])`?
- [ ] Should `BaseAgent.card()` expose strategy names or chain metadata in `AgentCard.metadata` in a later docs/API pass?

---

## 14. Alternatives Considered

### Alternative 1: Reuse `MultiAgentConsensusStrategy` for `strategies=[...]`

- What: Keep current `StrategyMixin.with_strategies()` meaning and wrap any sequence in consensus.
- Why rejected: The user explicitly wants prompt-engineering techniques chained together with output-only handoff, not multi-agent voting or evaluator selection.

### Alternative 2: Use existing pipelines for strategy chains

- What: Model each strategy as an agent or pipeline node and reuse `SequentialPipeline`.
- Why rejected: Pipelines compose agents and pipelines. The requested change is inside one agent's strategy execution mode and should preserve agent-level runner, context, tools, and metadata contracts.

### Alternative 3: Pass full `StrategyResult` objects between strategies

- What: Give later strategies access to prior calls, metadata, stage names, and tool state.
- Why rejected: The user clarified that only output should pass between strategies. Full-result handoff would create hidden coupling and make prompt recipes less predictable.

### Alternative 4: Remove `strategy` and only support `strategies`

- What: Replace the single strategy parameter entirely.
- Why rejected: This would be an unnecessary breaking change. Keeping `strategy` while adding `strategies` provides a clean migration path.
