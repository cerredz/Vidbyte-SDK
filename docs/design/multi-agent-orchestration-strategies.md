# Design Doc: Multi-Agent Orchestration Strategies

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

Add first-class multi-agent orchestration to the Vidbyte SDK without pushing orchestration concerns into harness APIs. The SDK will introduce an `agents` package for reusable actor definitions, a minimal strategy framework for composable execution, and `vidbyte/strategies/multi_agent/` for orchestration topologies including consensus judging, AutoGen-style conversation, VMAO-style plan-execute-verify-replan, economic routing, and evolving orchestration. Harnesses remain business boundaries and gain only a `with_strategies()` composition helper that runs multiple strategies, routes their outputs through an evaluator agent, and returns the selected best answer.

Review-driven implementation adjustments:

- Dataclass definitions live under `vidbyte/lib/dataclasses/`; public package modules re-export them for compatibility.
- Context objects are exposed through `vidbyte/context/`, with `BaseContext.build_context()` and optional file paths, strategy metadata, separated tool calls/responses, budget, artifacts, memory, and permissions.
- Budget and permission presets live under `vidbyte/lib/enums/`.
- Agent roles are user-defined strings. Default role prompt templates live in `vidbyte/prompts/prompts/` and are registered in the prompt registry.
- VMAO prompt templates live in `vidbyte/prompts/prompts/vmao.py`; the strategy imports those templates instead of owning long inline prompts.
- Multi-agent DAG and evaluation dataclasses are centralized under `vidbyte/lib/dataclasses/multi_agent.py`; `vidbyte/strategies/multi_agent/types.py` remains a re-export surface.

---

## 2. Goals & Non-Goals

### Goals

- Keep harnesses clean: harnesses define input/output contracts and should not expose "single agent vs multi agent" execution flags.
- Add `vidbyte/agents/` as the actor abstraction that packages a model runner, reasoning strategy, role, capabilities, and tools.
- Add local Agent Card capability declarations inspired by A2A without adding a network protocol.
- Add `vidbyte/strategies/multi_agent/` as the home for orchestration strategies.
- Implement `StrategyMixin.with_strategies()` as a consensus router that runs multiple strategies against the same prompt and sends the candidate outputs to an evaluator agent.
- Preserve tool injection at the agent layer so each agent can carry a different tool set.
- Support async-first orchestration with conservative sync wrappers for simple scripts.
- Keep the first implementation dependency-free and Python 3.11 standard-library only.
- Add focused stdlib `unittest` coverage with fake agent-selected runners and fake agents.

### Non-Goals

- No real MCP, ACP, A2A, or ANP network transport implementation in this PR.
- No reinforcement-learning training loop for Puppeteer-style routing in this PR.
- No decentralized discovery, DIDs, JSON-LD federation, remote agent marketplace, or cross-organization trust model.
- No database, vector store, durable memory, queue, workflow engine, or distributed execution runtime.
- No live provider calls in automated tests.
- No implementation inside the existing `HarnessClient` beyond exposing composition-friendly harness primitives.

---

## 3. Background & Context

- The current `vidbyte-sdk` main branch is still a minimal package scaffold. `VidbyteSDK` exposes `harnesses`, `tools`, and `providers`, while those namespace clients are currently empty.
- Two untracked design docs already exist in `docs/design/`: `prompt-api-strategies-sdk.md` and `agent-abstractions.md`. They are planning artifacts, not committed SDK implementation.
- The new design must work from current main, but it should align with the prior direction: strategies are public SDK behavior, tools are injectable developer-facing capabilities, and harnesses compose strategies rather than owning reasoning logic.
- The user's research synthesis points to a layered architecture:
  - AutoGen supplies the conversation substrate: agents exchange messages and generate replies.
  - MCP/A2A/ACP/ANP research separates tool access, structured messaging, peer delegation, and decentralized discovery scopes.
  - Enterprise orchestration research separates worker, service, and support agents from the orchestration control layer.
  - VMAO adds a verifier that judges collective output and triggers replanning.
  - Puppeteer adds dynamic next-agent selection; the first SDK pass will expose a policy interface and deterministic heuristic policy rather than RL training.
  - Economic orchestration research adds a pre-routing gate to avoid multi-agent overhead when one capable strategy is enough.
- Primary references checked:
  - https://arxiv.org/abs/2601.13671
  - https://arxiv.org/abs/2505.02279
  - https://arxiv.org/abs/2308.08155
  - https://arxiv.org/abs/2603.11445
  - https://arxiv.org/abs/2503.13577
  - https://arxiv.org/abs/2505.19591

---

## 4. Requirements

### Functional Requirements

1. `vidbyte.agents` must expose `AgentCard`, `AgentMessage`, `AgentSpec`, `BaseAgent`, and `AgentRegistry`.
2. `BaseAgent` must carry a name, role type, strategy, runner, tools, description, and metadata.
3. `BaseAgent.card()` must return a capability declaration suitable for local registry discovery.
4. `BaseAgent.generate_reply()` must execute the agent's configured strategy with the injected runner and tools.
5. `AgentRegistry` must register, retrieve, list, and filter agents by role and capability.
6. `vidbyte.strategies` must expose `BaseStrategy`, `StrategyResult`, `StrategyContext`, `StrategyMixin`, and `StrategyClient`.
7. `BaseStrategy` must be async-first through `arun()` and provide a conservative `run()` wrapper for non-event-loop scripts.
8. `StrategyMixin.with_strategy(strategy)` must attach a single strategy to the harness or object.
9. `StrategyMixin.with_strategies(strategies, evaluator_agent=None, **options)` must wrap the supplied strategies in `MultiAgentConsensusStrategy`.
10. `MultiAgentConsensusStrategy` must execute every candidate strategy against the original prompt with isolated context.
11. `MultiAgentConsensusStrategy` must collect successes and failures without letting one failed strategy cancel the whole consensus run.
12. `MultiAgentConsensusStrategy` must route successful candidates to an evaluator agent or default evaluator prompt.
13. The evaluator must judge candidates against the original prompt and return the selected best final output, with metadata containing candidate grades and selected strategy when parsable.
14. If all candidate strategies fail, consensus must raise `StrategyExecutionError` with safe, redacted failure summaries.
15. `AutoGenConversationStrategy` must support message-passing workflows with max turns, transition policy, and termination predicate.
16. `VerifiedMultiAgentOrchestrationStrategy` must implement a plan-execute-verify-replan loop over a DAG of sub-questions.
17. `EconomicGateStrategy` must wrap a baseline strategy and expensive orchestration strategy, only running the expensive strategy when an appropriateness score crosses a threshold.
18. `EvolvingOrchestrationStrategy` must expose a policy interface for dynamic next-agent selection and ship a deterministic heuristic policy.
19. Multi-agent strategies must pass tools through `BaseAgent` rather than global mutable state.
20. README and SDK skill docs must explain the recommended architecture: agents are actors, strategies are orchestration topologies, harnesses are business contracts.

### Non-Functional Requirements

- Security: no secrets, API keys, provider headers, or raw credentials may be stored in agent metadata or strategy results.
- Reliability: all multi-agent loops must have explicit `max_rounds`, `max_turns`, `max_calls`, or similar stop conditions.
- Cost control: high fanout execution must require explicit strategy lists, thresholds, or max call counts.
- Compatibility: Python `>=3.11`, standard library only.
- Observability: strategy results must preserve structured metadata for candidate outputs, selected strategy, verifier decisions, failed candidates, and call counts.
- Maintainability: public packages must use explicit `__all__`.
- Testability: tests must use fake agent-selected runners, fake strategies, and fake agents, with no network calls.
- Backward compatibility: existing `VidbyteSDK().harnesses`, `.tools`, and `.providers` construction must continue to work.

---

## 5. High-Level Design

The SDK should model multi-agent orchestration as composition, not harness configuration. A harness accepts a strategy and validates domain-specific inputs and outputs. An agent packages the actor triple described in the Puppeteer paper: model runner, reasoning strategy, and tools. A multi-agent strategy is an advanced strategy that directs one or more agents or candidate strategies.

```text
VidbyteSDK
|-- harnesses
|   `-- BaseHarness + StrategyMixin
|          | with_strategy(single)
|          ` with_strategies([...]) -> MultiAgentConsensusStrategy
|
|-- agents
|   |-- BaseAgent(model runner + strategy + tools)
|   |-- AgentCard(local capability declaration)
|   `-- AgentRegistry(local discovery)
|
`-- strategies
    |-- BaseStrategy
    `-- multi_agent
        |-- MultiAgentConsensusStrategy
        |-- AutoGenConversationStrategy
        |-- VerifiedMultiAgentOrchestrationStrategy
        |-- EconomicGateStrategy
        `-- EvolvingOrchestrationStrategy
```

Data flow for `with_strategies()`:

```text
Harness.run(input)
  -> StrategyMixin._strategy is MultiAgentConsensusStrategy
  -> run Strategy A, Strategy B, Strategy C against the same original prompt
  -> collect CandidateResult objects
  -> evaluator agent grades candidates against the original prompt/system context
  -> selected output returns through the normal harness result path
```

This preserves the architectural boundary: harnesses do not know whether the strategy is single-agent, multi-agent, or a consensus wrapper. They only call the strategy contract.

---

## 6. Detailed Design

### 6.1 Tool Protocol Foundation

**File(s):** `vidbyte/tools/types.py`, `vidbyte/tools/base.py`, `vidbyte/tools/__init__.py`, `vidbyte/tools/client.py`
**Type:** New file, New file, Modified, Modified

#### What it does

Adds the minimal public protocol needed for agents to advertise and receive tools without implementing real MCP. This keeps the agent abstraction useful while avoiding the broader tool registry implementation from the separate `agent-abstractions.md` design.

#### Interface / API

```python
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, str]

class ToolLike(Protocol):
    def spec(self) -> ToolSpec: ...
    async def arun(self, **kwargs: Any) -> Any: ...
```

#### Logic / Algorithm

1. `ToolSpec` stores stable model-facing tool metadata.
2. `ToolLike` is a structural protocol, so external developer tools do not need to inherit SDK base classes.
3. `BaseAgent.card()` reads `tool.spec().name` when available and falls back to class names when a developer passes a lighter object.

#### Edge Cases & Error Handling

- If a tool does not expose `spec()`, the agent can still store it, but its Agent Card lists the class name as an opaque capability.
- Tool invocation itself is not implemented here; strategies may pass tools into model prompts or agent logic, but real execution loops remain separate work.

---

### 6.2 Agent Types

**File(s):** `vidbyte/agents/types.py`
**Type:** New file

#### What it does

Defines stable dataclasses for local agent messages, capability cards, role types, and execution specs.

#### Interface / API

```python
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

AgentRole = Literal["worker", "service", "support", "evaluator"]

@dataclass(frozen=True, slots=True)
class AgentCard:
    name: str
    role: AgentRole
    description: str
    capabilities: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class AgentMessage:
    sender: str
    recipient: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    role: AgentRole
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Role types map the enterprise architecture paper to SDK terms.
2. Messages are local in-process payloads, not wire protocol packets.
3. Cards enable registry lookup and future A2A-style delegation without committing to A2A network behavior now.

#### Edge Cases & Error Handling

- Empty agent names are rejected by `BaseAgent`.
- Metadata is treated as non-secret developer context and must not store credentials.

---

### 6.3 Base Agent

**File(s):** `vidbyte/agents/base.py`, `vidbyte/agents/__init__.py`
**Type:** New file, New file

#### What it does

Implements the reusable actor abstraction. An agent owns a strategy, runner, role, capabilities, and tools. Multi-agent strategies call `BaseAgent.generate_reply()` instead of reaching directly into model providers.

#### Interface / API

```python
from collections.abc import Sequence
from typing import Any

class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        strategy: BaseStrategy,
        runner: object,
        tools: Sequence[ToolLike] = (),
        role: AgentRole = "worker",
        description: str = "",
        capabilities: Sequence[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def card(self) -> AgentCard: ...

    async def receive(self, message: AgentMessage) -> None: ...

    async def generate_reply(
        self,
        message: str,
        *,
        context: StrategyContext | None = None,
        history: Sequence[AgentMessage] = (),
        **options: Any,
    ) -> AgentMessage: ...
```

#### Logic / Algorithm

1. Validate name and strategy at construction.
2. Store incoming messages in an in-memory history list.
3. Build a `StrategyContext` containing the agent name, role, history, tools, and metadata.
4. Call `self.strategy.arun(message, runner=self.runner, context=context, tools=self.tools, **options)`.
5. Convert the resulting `StrategyResult.output` into an `AgentMessage`.

#### Edge Cases & Error Handling

- Missing runner raises `AgentExecutionError` only when the strategy requires one.
- Strategy exceptions are wrapped with agent name and role, without exposing secrets.
- Tool spec extraction tolerates developer-provided objects that only partially implement the protocol.

---

### 6.4 Agent Registry

**File(s):** `vidbyte/agents/registry.py`
**Type:** New file

#### What it does

Provides local in-process agent discovery by name, role, capability, and tool. This is the SDK's first local approximation of A2A Agent Cards.

#### Interface / API

```python
class AgentRegistry:
    def register(self, agent: BaseAgent) -> None: ...
    def get(self, name: str) -> BaseAgent: ...
    def all(self) -> tuple[BaseAgent, ...]: ...
    def cards(self) -> tuple[AgentCard, ...]: ...
    def find(
        self,
        *,
        role: AgentRole | None = None,
        capability: str | None = None,
        tool_name: str | None = None,
    ) -> tuple[BaseAgent, ...]: ...
```

#### Logic / Algorithm

1. Store agents by unique name.
2. Return immutable tuples from public list methods.
3. Use `AgentCard` fields for filtering.

#### Edge Cases & Error Handling

- Duplicate names raise `AgentRegistryError`.
- Missing names raise `AgentRegistryError`.
- Registry state is local to the instance, not global singleton state.

---

### 6.5 Strategy Foundation

**File(s):** `vidbyte/strategies/types.py`, `vidbyte/strategies/base.py`, `vidbyte/strategies/__init__.py`, `vidbyte/strategies/client.py`, `vidbyte/client.py`, `vidbyte/__init__.py`
**Type:** New file, New file, New file, New file, Modified, Modified

#### What it does

Creates the minimal strategy contract needed for single and multi-agent strategies. This is intentionally smaller than the earlier `prompt-api-strategies-sdk.md` design but compatible with it.

#### Interface / API

```python
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

@dataclass(frozen=True, slots=True)
class StrategyContext:
    system_prompt: str | None = None
    agent_name: str | None = None
    role: str | None = None
    history: Sequence[object] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class StrategyResult:
    output: str
    strategy_name: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

class BaseStrategy:
    name = "base"

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult: ...

    def run(self, prompt: str, **kwargs: Any) -> StrategyResult: ...
```

#### Logic / Algorithm

1. `arun()` is the primary implementation hook.
2. `run()` calls `asyncio.run(self.arun(...))` for simple scripts and raises a clear error if called inside an active loop.
3. `StrategyClient` exposes constructors for multi-agent strategies.
4. `VidbyteSDK.__init__()` adds `self.strategies = StrategyClient()` while preserving existing namespace clients.

#### Edge Cases & Error Handling

- Empty outputs are allowed, but strategy metadata should indicate why when applicable.
- `run()` inside a running event loop raises a guidance error telling users to `await strategy.arun(...)`.

---

### 6.6 Strategy Mixin and Harness Composition

**File(s):** `vidbyte/strategies/mixins.py`, `vidbyte/harnesses/base.py`, `vidbyte/harnesses/__init__.py`, `vidbyte/harnesses/client.py`
**Type:** New file, New file, Modified, Modified

#### What it does

Adds composition methods to any SDK object that needs strategy attachment. Harnesses can use this mixin without understanding whether the strategy is single or multi-agent.

#### Interface / API

```python
class StrategyMixin:
    def with_strategy(self, strategy: BaseStrategy) -> "StrategyMixin": ...

    def with_strategies(
        self,
        strategies: Sequence[BaseStrategy],
        *,
        evaluator_agent: BaseAgent | None = None,
        evaluator_strategy: BaseStrategy | None = None,
        **options: object,
    ) -> "StrategyMixin": ...

class BaseHarness(StrategyMixin):
    async def arun(self, prompt: str, *, runner: object | None = None, **options: object) -> StrategyResult: ...
```

#### Logic / Algorithm

1. `with_strategy()` stores the provided strategy on `self._strategy`.
2. `with_strategies()` validates that at least one strategy is present.
3. It constructs `MultiAgentConsensusStrategy(strategies=strategies, evaluator_agent=evaluator_agent, evaluator_strategy=evaluator_strategy, **options)`.
4. It stores that consensus strategy on `self._strategy`.
5. Harness execution delegates to the stored strategy.

#### Edge Cases & Error Handling

- Calling `BaseHarness.arun()` before setting a strategy raises `StrategyExecutionError`.
- Passing an empty strategy list to `with_strategies()` raises `ValueError`.
- `with_strategies()` does not mutate the individual strategies.

---

### 6.7 Multi-Agent Types

**File(s):** `vidbyte/strategies/multi_agent/types.py`
**Type:** New file

#### What it does

Defines internal result types shared by consensus, VMAO, economic gate, and evolving orchestration.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class CandidateResult:
    index: int
    strategy_name: str
    output: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class CandidateFailure:
    index: int
    strategy_name: str
    error_type: str
    message: str

@dataclass(frozen=True, slots=True)
class EvaluationDecision:
    selected_index: int
    final_output: str
    grades: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""
```

#### Logic / Algorithm

1. Candidate successes and failures are represented separately.
2. Evaluator parsing returns `EvaluationDecision` when structured output is available.
3. Strategy metadata includes these dataclasses converted to serializable dicts.

#### Edge Cases & Error Handling

- Evaluator output that is not parseable JSON falls back to the best-effort raw evaluator text.
- Candidate indexes are one-based in prompts and zero-based internally only if explicitly documented. The implementation should use one-based indexes everywhere user-facing.

---

### 6.8 Base Multi-Agent Strategy

**File(s):** `vidbyte/strategies/multi_agent/base.py`, `vidbyte/strategies/multi_agent/__init__.py`
**Type:** New file, New file

#### What it does

Provides shared validation, safe error formatting, max-call enforcement, and helper execution methods for multi-agent strategies.

#### Interface / API

```python
class BaseMultiAgentStrategy(BaseStrategy):
    def __init__(self, *, max_calls: int = 20) -> None: ...
    def _safe_error(self, exc: BaseException) -> str: ...
    async def _run_agent(self, agent: BaseAgent, prompt: str, **options: Any) -> AgentMessage: ...
```

#### Logic / Algorithm

1. Inherit from `BaseStrategy`.
2. Track call counts in per-run metadata.
3. Provide common exception redaction.
4. Keep orchestration state local to each run.

#### Edge Cases & Error Handling

- Max call exhaustion raises `StrategyExecutionError`.
- Exceptions are summarized by type and message only.

---

### 6.9 Multi-Agent Consensus Strategy

**File(s):** `vidbyte/strategies/multi_agent/consensus.py`
**Type:** New file

#### What it does

Implements the requested `with_strategies()` behavior: solve the prompt using all listed strategies, send the candidate outputs to an evaluator, and return the best answer.

#### Interface / API

```python
class MultiAgentConsensusStrategy(BaseMultiAgentStrategy):
    def __init__(
        self,
        *,
        strategies: Sequence[BaseStrategy],
        evaluator_agent: BaseAgent | None = None,
        evaluator_strategy: BaseStrategy | None = None,
        require_json_decision: bool = False,
        max_calls: int = 20,
    ) -> None: ...
```

#### Logic / Algorithm

1. Validate that `strategies` is non-empty.
2. Build one isolated `StrategyContext` per strategy, preserving original system prompt and caller metadata.
3. Execute candidate strategies concurrently with `asyncio.gather(..., return_exceptions=True)`.
4. Convert successful results to `CandidateResult`.
5. Convert exceptions to `CandidateFailure`.
6. If no candidates succeeded, raise `StrategyExecutionError`.
7. Render the evaluator prompt:

```text
You are an expert evaluator. Given the original task and candidate answers,
grade each candidate for correctness, completeness, instruction following,
and risk. Return JSON with selected_index, final_output, grades, and rationale.
```

8. If `evaluator_agent` is provided, call `evaluator_agent.generate_reply(evaluator_prompt, ...)`.
9. Else if `evaluator_strategy` is provided, run it with the original runner.
10. Else call the original runner through a tiny default direct-call evaluator helper when the runner exposes `arun()` or `run()`.
11. Parse JSON evaluator output into `EvaluationDecision`.
12. Return `StrategyResult(output=decision.final_output, strategy_name="multi_agent.consensus", metadata={...})`.

#### Edge Cases & Error Handling

- If evaluator parsing fails and `require_json_decision=False`, return the raw evaluator text as the output with metadata noting parse failure.
- If evaluator parsing fails and `require_json_decision=True`, raise `StrategyExecutionError`.
- If evaluator selects an invalid candidate index, fall back to candidate 1 and include metadata.
- Failed candidate outputs are not sent as answers, but their failure summaries are included for evaluator awareness.

---

### 6.10 AutoGen Conversation Strategy

**File(s):** `vidbyte/strategies/multi_agent/autogen.py`
**Type:** New file

#### What it does

Implements local AutoGen-style message passing. Agents exchange `AgentMessage` objects according to a transition policy until a max-turn count or termination predicate fires.

#### Interface / API

```python
class AutoGenConversationStrategy(BaseMultiAgentStrategy):
    def __init__(
        self,
        *,
        agents: Sequence[BaseAgent],
        initial_agent: str,
        transition_policy: Callable[[Sequence[AgentMessage], AgentRegistry], str | None],
        max_turns: int = 8,
        termination_predicate: Callable[[AgentMessage], bool] | None = None,
    ) -> None: ...
```

#### Logic / Algorithm

1. Register agents locally.
2. Send the original prompt to the initial agent.
3. Append each reply to transcript.
4. Ask `transition_policy` which agent should act next.
5. Stop when the policy returns `None`, termination predicate returns true, or `max_turns` is reached.
6. Return the final message content and transcript metadata.

#### Edge Cases & Error Handling

- Unknown next-agent names raise `StrategyExecutionError`.
- Empty transcripts return a clear orchestration error.
- Max-turn termination is marked in metadata.

---

### 6.11 Verified Multi-Agent Orchestration Strategy

**File(s):** `vidbyte/strategies/multi_agent/vmao.py`
**Type:** New file

#### What it does

Implements VMAO's plan-execute-verify-replan algorithm. It decomposes a complex prompt into a DAG, executes independent nodes in parallel, verifies completeness, and replans missing work.

#### Interface / API

```python
class VerifiedMultiAgentOrchestrationStrategy(BaseMultiAgentStrategy):
    def __init__(
        self,
        *,
        planner: BaseAgent,
        workers: Sequence[BaseAgent],
        verifier: BaseAgent,
        synthesizer: BaseAgent | None = None,
        max_rounds: int = 3,
        completeness_threshold: float = 0.85,
        max_parallel_tasks: int = 4,
    ) -> None: ...
```

#### Logic / Algorithm

1. Ask the planner to return a JSON DAG of sub-questions:
   - `id`
   - `question`
   - `depends_on`
   - `preferred_capability`
2. Validate that the graph is acyclic and all dependencies exist.
3. Execute nodes whose dependencies are satisfied, bounded by `max_parallel_tasks`.
4. Route each node to the best worker by capability match; fall back to the first worker.
5. Propagate upstream node outputs into downstream prompts.
6. Synthesize node outputs into a draft answer with `synthesizer` or deterministic concatenation.
7. Ask the verifier to score completeness and list gaps.
8. If score >= threshold, return the synthesized answer.
9. If score < threshold and rounds remain, ask planner to create a follow-up DAG for the gaps.
10. Repeat execute, synthesize, and verify until approved or `max_rounds` is exhausted.

#### Edge Cases & Error Handling

- Invalid planner JSON triggers one repair attempt through the planner; if still invalid, raise `StrategyExecutionError`.
- Cycles in the DAG are rejected.
- Worker failure marks a node failed; verifier receives failure context.
- If max rounds are exhausted, return the best synthesized answer with metadata showing verifier score and gaps.

---

### 6.12 Economic Gate Strategy

**File(s):** `vidbyte/strategies/multi_agent/economic_gate.py`
**Type:** New file

#### What it does

Implements an appropriateness-of-orchestration gate. It decides whether to run a cheap baseline strategy or a more expensive orchestration strategy.

#### Interface / API

```python
class EconomicGateStrategy(BaseMultiAgentStrategy):
    def __init__(
        self,
        *,
        baseline_strategy: BaseStrategy,
        orchestration_strategy: BaseStrategy,
        scorer: Callable[[str, StrategyContext | None], float] | None = None,
        threshold: float = 0.6,
    ) -> None: ...
```

#### Logic / Algorithm

1. Score prompt complexity, ambiguity, expected need for parallelism, and estimated value of verification.
2. If score < threshold, run `baseline_strategy`.
3. If score >= threshold, run `orchestration_strategy`.
4. Return the selected result with metadata containing the score and route.

#### Edge Cases & Error Handling

- The default scorer is heuristic and deterministic.
- Custom scorer exceptions fall back to baseline execution unless `strict=True` is added in a later PR.
- Threshold must be between 0 and 1.

---

### 6.13 Evolving Orchestration Strategy

**File(s):** `vidbyte/strategies/multi_agent/evolving.py`
**Type:** New file

#### What it does

Implements the inference-time shape of Puppeteer-style orchestration without RL training. A policy chooses which agent acts next based on evolving transcript state.

#### Interface / API

```python
class OrchestrationPolicy(Protocol):
    def select_next(
        self,
        *,
        prompt: str,
        transcript: Sequence[AgentMessage],
        registry: AgentRegistry,
    ) -> str | None: ...

class HeuristicPolicy:
    def select_next(...) -> str | None: ...

class EvolvingOrchestrationStrategy(BaseMultiAgentStrategy):
    def __init__(
        self,
        *,
        agents: Sequence[BaseAgent],
        policy: OrchestrationPolicy | None = None,
        max_turns: int = 8,
        exploration_width: int = 1,
    ) -> None: ...
```

#### Logic / Algorithm

1. Register agent pool.
2. Initialize transcript with the original user prompt.
3. Ask policy to select the next agent.
4. Execute selected agent and append reply.
5. Repeat until policy returns `None` or `max_turns` is reached.
6. Return final reply or synthesize transcript if no single final reply is marked.

#### Edge Cases & Error Handling

- The first implementation does not train policies.
- `exploration_width > 1` can run several selected agents per turn in parallel only when the policy supports it; otherwise it behaves as 1.
- Cyclic routing is allowed but bounded by `max_turns`.

---

### 6.14 Error Types

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
**Type:** New file, Modified

#### What it does

Adds SDK exception types used by agents and strategies.

#### Interface / API

```python
class VidbyteSdkError(Exception): ...
class AgentExecutionError(VidbyteSdkError): ...
class AgentRegistryError(VidbyteSdkError): ...
class StrategyExecutionError(VidbyteSdkError): ...
```

#### Logic / Algorithm

1. Exceptions carry human-readable messages.
2. Optional detail dictionaries are allowed but must be safe to print.

#### Edge Cases & Error Handling

- No exception should store API keys, raw headers, or large model responses by default.

---

### 6.15 Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified, Modified

#### What it does

Documents the new public concepts and explains the recommended architectural route.

#### Interface / API

```python
harness = BaseHarness().with_strategies(
    [
        sdk.strategies.direct(),
        sdk.strategies.multi_agent.consensus(...),
    ],
    evaluator_agent=evaluator,
)
```

#### Logic / Algorithm

1. README adds a short multi-agent section.
2. The SDK skill adds rules:
   - agents package model, strategy, and tools
   - multi-agent topologies live under `strategies/multi_agent`
   - harnesses do not expose multi-agent execution toggles

#### Edge Cases & Error Handling

- Documentation examples should use agents with fake runner mappings or placeholders, not real API keys or direct concrete runner construction.

---

## 7. Data Model Changes

### 7.1 Agent and Strategy Dataclasses

**Change type:** New

```python
ToolSpec
AgentCard
AgentMessage
AgentSpec
StrategyContext
StrategyResult
CandidateResult
CandidateFailure
EvaluationDecision
```

**Migration strategy:** N/A - these are in-memory SDK dataclasses only. There is no database or persisted schema.

---

## 8. API Changes

N/A - this package change does not add HTTP endpoints.

Python SDK public API additions:

```python
from vidbyte.agents import BaseAgent, AgentRegistry
from vidbyte.strategies import BaseStrategy, StrategyMixin
from vidbyte.strategies.multi_agent import (
    MultiAgentConsensusStrategy,
    AutoGenConversationStrategy,
    VerifiedMultiAgentOrchestrationStrategy,
    EconomicGateStrategy,
    EvolvingOrchestrationStrategy,
)
```

Modified SDK root:

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.strategies
```

Harness composition:

```python
harness.with_strategy(single_strategy)
harness.with_strategies([strategy_a, strategy_b], evaluator_agent=evaluator_agent)
```

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/multi-agent-orchestration-strategies.md` | Design doc for this feature |
| MODIFY | `README.md` | Document agents, multi-agent strategies, and `with_strategies()` |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add SDK structure guidance for agents and multi-agent orchestration |
| MODIFY | `vidbyte/__init__.py` | Export public agent and strategy types |
| MODIFY | `vidbyte/client.py` | Add `sdk.strategies` namespace |
| MODIFY | `vidbyte/tools/__init__.py` | Export minimal tool protocol types |
| MODIFY | `vidbyte/tools/client.py` | Expose tool protocol helpers if needed |
| CREATE | `vidbyte/tools/types.py` | `ToolSpec` dataclass |
| CREATE | `vidbyte/tools/base.py` | `ToolLike` protocol |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export SDK error hierarchy |
| CREATE | `vidbyte/lib/errors/base.py` | Agent and strategy exception types |
| CREATE | `vidbyte/agents/__init__.py` | Agent package exports |
| CREATE | `vidbyte/agents/types.py` | Agent role, card, message, and spec dataclasses |
| CREATE | `vidbyte/agents/base.py` | `BaseAgent` implementation |
| CREATE | `vidbyte/agents/registry.py` | Local `AgentRegistry` |
| CREATE | `vidbyte/strategies/__init__.py` | Strategy package exports |
| CREATE | `vidbyte/strategies/types.py` | `StrategyContext` and `StrategyResult` |
| CREATE | `vidbyte/strategies/base.py` | Async-first `BaseStrategy` |
| CREATE | `vidbyte/strategies/client.py` | Strategy namespace client |
| CREATE | `vidbyte/strategies/mixins.py` | `with_strategy()` and `with_strategies()` |
| MODIFY | `vidbyte/harnesses/__init__.py` | Export `BaseHarness` |
| MODIFY | `vidbyte/harnesses/client.py` | Expose harness base helpers if needed |
| CREATE | `vidbyte/harnesses/base.py` | Minimal `BaseHarness` using `StrategyMixin` |
| CREATE | `vidbyte/strategies/multi_agent/__init__.py` | Multi-agent strategy exports |
| CREATE | `vidbyte/strategies/multi_agent/types.py` | Candidate and evaluation dataclasses |
| CREATE | `vidbyte/strategies/multi_agent/base.py` | Shared multi-agent strategy helpers |
| CREATE | `vidbyte/strategies/multi_agent/consensus.py` | Consensus/evaluator strategy for `with_strategies()` |
| CREATE | `vidbyte/strategies/multi_agent/autogen.py` | AutoGen-style message-passing strategy |
| CREATE | `vidbyte/strategies/multi_agent/vmao.py` | Verified multi-agent orchestration strategy |
| CREATE | `vidbyte/strategies/multi_agent/economic_gate.py` | Appropriateness-of-orchestration router |
| CREATE | `vidbyte/strategies/multi_agent/evolving.py` | Dynamic policy-based orchestration strategy |
| CREATE | `tests/test_agent_base.py` | Agent card, reply, and tool injection tests |
| CREATE | `tests/test_agent_registry.py` | Registry lookup and filtering tests |
| CREATE | `tests/test_strategy_mixin.py` | `with_strategy()` and `with_strategies()` tests |
| CREATE | `tests/test_multi_agent_consensus.py` | Candidate execution, evaluator selection, failure handling tests |
| CREATE | `tests/test_autogen_conversation.py` | Message routing and max-turn tests |
| CREATE | `tests/test_vmao.py` | DAG validation, worker routing, verifier replan tests |
| CREATE | `tests/test_economic_gate.py` | Threshold routing tests |
| CREATE | `tests/test_evolving_orchestration.py` | Policy selection and bounded cyclic routing tests |

Summary: 30 files created, 9 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_agent_base.py` -> creates fake strategy, fake runner, and fake tools; verifies `BaseAgent.card()` and `generate_reply()` pass tools through strategy context.
- `tests/test_agent_registry.py` -> verifies duplicate-name rejection, missing-name errors, role filtering, capability filtering, and tool-name filtering.
- `tests/test_strategy_mixin.py` -> verifies `with_strategy()` stores the exact strategy and `with_strategies()` wraps strategies in `MultiAgentConsensusStrategy`.
- `tests/test_multi_agent_consensus.py` -> verifies all candidate strategies run, one failed candidate does not fail the whole run, all failed candidates raise, evaluator JSON is parsed, invalid evaluator JSON fallback works, and selected output is returned.
- `tests/test_autogen_conversation.py` -> verifies transition policy routing, transcript metadata, termination predicate, and max-turn stop metadata.
- `tests/test_vmao.py` -> verifies valid DAG execution order, cycle rejection, dependency context propagation, verifier approval, verifier rejection with replan, and max-round fallback.
- `tests/test_economic_gate.py` -> verifies low scores run baseline, high scores run orchestration, invalid thresholds fail, and scorer failures fall back to baseline.
- `tests/test_evolving_orchestration.py` -> verifies heuristic policy selection, unknown selected agent errors, cyclic routing bounded by max turns, and final transcript metadata.

### Integration Tests

- N/A - no live provider integrations or remote protocols in this PR.
- Use fake agent runner mappings and fake agents to exercise end-to-end harness composition locally.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte` from repository root.
2. Run `python -m unittest discover -s tests`.
3. Run an import smoke test:

```python
from vidbyte import VidbyteSDK
from vidbyte.agents import BaseAgent, AgentRegistry
from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy

sdk = VidbyteSDK()
print(type(sdk.strategies).__name__)
print(BaseAgent, AgentRegistry, MultiAgentConsensusStrategy)
```

4. Create two fake strategies that return different text and a fake evaluator that selects candidate 2; verify `BaseHarness().with_strategies([...]).arun(...)` returns candidate 2.
5. Create a VMAO strategy with fake planner, worker, verifier, and synthesizer; verify verifier rejection triggers a second planning round.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | Dataclasses, protocols, asyncio, tests | Limited ergonomics but keeps SDK dependency-free |
| arXiv 2601.13671 | https://arxiv.org/abs/2601.13671 | Role layering and orchestration layer inspiration | Paper is architectural; SDK must choose a narrow first implementation |
| arXiv 2505.02279 | https://arxiv.org/abs/2505.02279 | Protocol scope separation and Agent Card inspiration | Network protocols are intentionally out of scope |
| arXiv 2308.08155 | https://arxiv.org/abs/2308.08155 | AutoGen-style conversable agents | Full AutoGen compatibility is not a goal |
| arXiv 2603.11445 | https://arxiv.org/abs/2603.11445 | VMAO plan-execute-verify-replan strategy | DAG planning output can be malformed and needs validation |
| arXiv 2503.13577 | https://arxiv.org/abs/2503.13577 | Economic orchestration gate | First scorer is heuristic, not a learned cost model |
| arXiv 2505.19591 | https://arxiv.org/abs/2505.19591 | Dynamic evolving orchestration policy shape | RL training is out of scope |

---

## 12. Rollout & Deployment

- This is a package-only SDK change. No deployed service is updated.
- Implementation must happen in an isolated feature worktree after design approval.
- This is additive and should not break the existing scaffold API.
- Rollout path:
  1. Commit this design doc first in the feature branch.
  2. Implement foundation errors, strategy types, and tool protocol.
  3. Implement agents and registry.
  4. Implement multi-agent strategies.
  5. Wire `VidbyteSDK().strategies` and harness mixin.
  6. Add tests and docs.
- Rollback is reverting the feature branch merge commit.
- If the prior provider/strategy SDK PR lands first, this implementation should reuse its compatible `BaseStrategy`, `StrategyResult`, and tool types rather than duplicating them. Any such reuse must be recorded as a design-doc deviation before PR creation.

---

## 13. Open Questions

- [ ] Should the implementation wait for the prior `prompt-api-strategies-sdk.md` strategy framework PR to merge, or should it implement the minimal compatible strategy foundation described here?
- [ ] Should evaluator output require strict JSON by default, or should raw evaluator text fallback remain the default for better developer ergonomics?
- [ ] Should `BaseAgent` require a runner, or allow strategy-only agents for deterministic/local strategies?
- [ ] Should `AgentRegistry` be per-orchestrator only, or should `VidbyteSDK` expose a root `sdk.agents` registry namespace in this first PR?
- [ ] Should VMAO planner/verifier prompts live as plain internal templates for now, or wait for a full prompt registry abstraction?
- [ ] Should `with_strategies()` live only on `StrategyMixin`, or should `StrategyClient` also expose a direct helper such as `sdk.strategies.consensus([...])`?

---

## 14. Alternatives Considered

### Alternative 1: Add a `multi_agent=True` parameter to harnesses

- What: Let harness constructors or run calls switch between single-agent and multi-agent execution.
- Why rejected: It pushes orchestration topology into business/domain harnesses, mixes concerns, and makes every harness carry execution-mode branching.

### Alternative 2: Put every orchestration mode in one generic `agents` folder

- What: Create one agent package with configuration toggles for consensus, VMAO, conversation, and evolving orchestration.
- Why rejected: Agents are actors. Orchestration topologies are controllers. Mixing them would make tool injection, registry discovery, and execution policy harder to reason about.

### Alternative 3: Implement real MCP, ACP, A2A, and ANP now

- What: Add JSON-RPC tool servers, REST multipart messaging, peer network delegation, and DID-based discovery.
- Why rejected: The first SDK need is in-process developer orchestration. Network protocols require security, auth, transport, and compatibility designs that would swamp the core abstraction.

### Alternative 4: Implement Puppeteer RL training now

- What: Train a policy that learns next-agent selection from rewards.
- Why rejected: Training requires datasets, reward definitions, persistence, evaluation harnesses, and compute. The SDK should first expose an inference-time policy interface and deterministic policy.

### Alternative 5: Put consensus judging directly inside `BaseStrategy`

- What: Make every strategy able to run with siblings and judge results.
- Why rejected: Consensus is a specific orchestration topology. Keeping it in `strategies/multi_agent/consensus.py` makes the base strategy simple and preserves zero overhead when unused.

---

END OF DESIGN DOC
