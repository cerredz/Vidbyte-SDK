# Design Doc: Non-Linear Agent Runtime Algorithms

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This document covers the addition of four non-linear agent runtime algorithms to the Vidbyte SDK: **Beam Search**, **DAG Dataflow**, **Market Auction**, and **Gossip/Epidemic**. Each algorithm is a context-window algorithm registered under `ContextWindow.preset.<name>`, following the same layered architecture as the existing `reflexion` and `multi_provider_agentic_grader` algorithms. Unlike linear strategies (PlanAndExecute, SelfRefinement), these runtimes cannot be expressed as a single sequential `while not done: step()` loop — they require a fundamentally different execution topology: beam-width state tracking, dependency-graph execution, dynamic task auction, or decentralized peer-to-peer knowledge exchange.

---

## 2. Goals & Non-Goals

### Goals
- Add `ContextWindow.preset.beam_search`, `ContextWindow.preset.dag_dataflow`, `ContextWindow.preset.market_auction`, and `ContextWindow.preset.gossip` as first-class SDK presets
- Implement each as a `<Name>RuntimeAlgorithm` in `vidbyte/agents/algorithms/` that uses existing `AgentRuntime._arun_once` and `_invoke_with_middleware` helpers
- Implement each public configuration dataclass in `vidbyte/context/algorithms/` with full `ConfigurationError` validation at construction time
- Register each preset in `ContextWindowAlgorithm`, `ContextWindowPresets`, and the `AgentRuntimeContextAlgorithms` dispatcher
- Preserve all existing runtime contracts: tools, permissions, middleware, tracing, provider formatting, `StrategyResult` metadata
- Write `tests/test_<name>_algorithm.py` for each runtime and a unified `scripts/test-non-linear-runtimes.py` verification script

### Non-Goals
- Real concurrency using OS threads or worker processes — `asyncio.gather` is used where parallelism is needed, but no new threading primitives
- Modifying `AgentRuntime._arun_once` or `AgentRuntime.arun` — they remain algorithm-neutral
- Adding prompt catalog assets in `vidbyte/prompts/prompts/` — all prompts are either developer-overrideable fields or inline system-level instructions small enough to inline
- Changing the pipeline or strategy layer
- Supporting streaming output from non-linear runtimes in this iteration

---

## 3. Background & Context

The existing `agents/algorithms/` layer has `reflexion` (trial-reflect-retry loop) and `multi_provider_agentic_grader` (concurrent provider dispatch with LLM grading). Both are non-linear relative to a plain `_arun_once` call but are still single-agent. The four algorithms added here extend this pattern into genuinely different control topologies:

- **Beam Search**: maintains k parallel hypothesis tracks, scores each, and prunes — the runtime state is a set of k live `StrategyResult` objects, not one
- **DAG Dataflow**: the agent first generates a dependency graph, then the runtime executes nodes in topological order with parallelism at each level
- **Market Auction**: the runtime simulates a competitive bidding protocol among specialist roles, selects a winner, and executes the task under the winning role's system prompt
- **Gossip**: N agents start with partial knowledge, exchange it in random pairwise rounds until convergence, then a final synthesis step produces the answer

Each algorithm is accessed via `algorithm=ContextWindow.preset.<name>` on an `Agent`/`BaseAgent`, requiring no additional wiring by the developer.

---

## 4. Requirements

### Functional Requirements

1. `ContextWindow.preset.beam_search` returns a `ContextWindowAlgorithm` with `name="beam_search"` and a valid `BeamSearchAlgorithm` instance
2. `ContextWindow.preset.dag_dataflow` returns a `ContextWindowAlgorithm` with `name="dag_dataflow"` and a valid `DAGDataflowAlgorithm` instance
3. `ContextWindow.preset.market_auction` returns a `ContextWindowAlgorithm` with `name="market_auction"` and a valid `MarketAuctionAlgorithm` instance
4. `ContextWindow.preset.gossip` returns a `ContextWindowAlgorithm` with `name="gossip"` and a valid `GossipAlgorithm` instance
5. `ContextWindow.resolve_algorithm("<name>")` resolves each of the four preset names correctly
6. Unknown algorithm names raise `ValueError` (existing behavior)
7. Each public config class raises `ConfigurationError` at construction time for invalid numeric fields, empty prompt overrides, and non-string metadata keys
8. Each runtime adapter runs its algorithm-specific loop using `runtime._arun_once` for full agent trials and `runtime._invoke_with_middleware` for lightweight model calls (scoring, planning, merging, bidding)
9. The final `StrategyResult.metadata` from each algorithm contains a structured trace object keyed by algorithm name (e.g., `result.metadata["beam_search"]`)
10. All existing middleware, permission, tracing, and tool-call contracts are preserved across all four algorithms
11. `AgentRuntimeContextAlgorithms.detect_algorithm()` identifies each algorithm correctly; `return_algorithm()` returns the correct runtime adapter
12. At most one runtime algorithm field may be set in a single `ContextWindowAlgorithm` (existing `__post_init__` constraint extended to include all four new fields)

### Non-Functional Requirements
- No live provider calls in tests — fake runners only
- `ConfigurationError` from `vidbyte.lib.errors` for all validation failures
- No mutable shared state between parallel `_arun_once` calls
- Each algorithm's metadata trace must be a tuple or dict of serializable values (no raw provider response objects)
- Algorithm config classes use `@dataclass(frozen=True, slots=True)` and `Mapping[str, Any]` for `metadata`

---

## 5. High-Level Design

All four algorithms follow the same SDK pattern:

```
Developer writes:
  Agent(algorithm=ContextWindow.preset.beam_search)

→ ContextWindowPresets.beam_search returns ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm())
→ AgentRuntime stores algorithm; AgentRuntimeContextAlgorithms detects "beam_search"
→ arun() delegates to BeamSearchRuntimeAlgorithm.arun(...)
→ BeamSearchRuntimeAlgorithm calls runtime._arun_once / _invoke_with_middleware multiple times
→ Returns StrategyResult with metadata["beam_search"] trace
```

### Beam Search Control Flow

```
Task
  │
  ├─ Trial 1 ──────────────────────────────────── StrategyResult A
  ├─ Trial 2 ──────────────────────────────────── StrategyResult B    (beam_width parallel trials)
  └─ Trial k ──────────────────────────────────── StrategyResult k
        │
        ▼
   [Scorer LLM call per candidate → numeric score]
        │
        ▼
   [Select top-1 by score]
        │
        ▼
   StrategyResult (winner) + metadata["beam_search"]
```

### DAG Dataflow Control Flow

```
Task
  │
  ▼
[Planner LLM call → JSON DAG: list of {id, description, dependencies}]
  │
  ▼
Topological levels:
  Level 0: [Node A, Node B] → asyncio.gather(_arun_once × 2)
  Level 1: [Node C (needs A,B)] → _arun_once(task=C, inputs=A_output+B_output)
  Level 2: [Node D (needs C)] → _arun_once(...)
  │
  ▼
[Synthesizer LLM call → final answer from all node outputs]
  │
  ▼
StrategyResult + metadata["dag_dataflow"]
```

### Market Auction Control Flow

```
Task
  │
  ▼
[Role generation: _invoke_with_middleware → N specialist role names]
  │
  ▼
[Bid round: _invoke_with_middleware × N (one per role) → {can_handle, confidence, approach}]
  │
  ▼
[Winner selection: highest-confidence bidder]
  │
  ▼
[Execution: _arun_once with winner's system prompt]
  │
  ▼
StrategyResult + metadata["market_auction"]
```

### Gossip Control Flow

```
Task
  │
  ├─ Agent 1 (angle: "approach from first principles") → knowledge_1
  ├─ Agent 2 (angle: "focus on edge cases") → knowledge_2    (parallel _arun_once × N)
  ├─ Agent 3 (angle: "consider alternatives") → knowledge_3
  └─ Agent N → knowledge_N
        │
        ▼
  Gossip rounds (R rounds):
    Round 1: pair (1,2) → merge → update both; pair (3,4) → merge → update both
    Round 2: pair (1,3) → merge; pair (2,4) → merge
    ...
        │
        ▼
  [Synthesizer call: all converged knowledge → final answer]
        │
        ▼
  StrategyResult + metadata["gossip"]
```

---

## 6. Detailed Design

### 6.1 BeamSearchAlgorithm (Public Config)

**File:** `vidbyte/context/algorithms/beam_search.py`
**Type:** New file

#### What it does
Immutable public configuration for the Beam Search runtime. Validates numeric limits and prompt override fields.

#### Interface
```python
@dataclass(frozen=True, slots=True)
class BeamSearchAlgorithm:
    beam_width: int = 3
    max_scorer_chars: int = 8000
    scorer_system_prompt: str | None = None
    scorer_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    def render_scorer_prompt(self, task: str, candidate: str) -> str: ...
    def scorer_system_prompt_text(self) -> str: ...
    def truncate_candidate(self, output: str) -> str: ...
```

#### Logic
- `__post_init__` validates `beam_width >= 1`, `max_scorer_chars > 0`, prompt overrides non-empty when set, metadata keys are strings — all via module-level helper functions raising `ConfigurationError`
- `render_scorer_prompt(task, candidate)` formats the scorer prompt with `{task}` and `{candidate}` placeholders; uses an inline default if no override is set
- `scorer_system_prompt_text()` returns override or an inline default: `"You are an impartial evaluator. Score the candidate answer 0-10 for quality, completeness, and correctness. Respond with a single integer."`
- `truncate_candidate(output)` trims to `max_scorer_chars` with a suffix if needed

#### Edge Cases
- `beam_width=0` → `ConfigurationError` at construction
- `scorer_prompt` provided but missing `{task}` or `{candidate}` → `ConfigurationError`
- Empty `scorer_system_prompt=""` → `ConfigurationError`

---

### 6.2 BeamSearchRuntimeAlgorithm

**File:** `vidbyte/agents/algorithms/beam_search.py`
**Type:** New file

#### What it does
Runs `beam_width` independent agent trials in parallel, scores each output using an LLM scorer call, and returns the highest-scored result.

#### Interface
```python
class BeamSearchRuntimeAlgorithm:
    name = "beam_search"

    def __init__(self, runtime: AgentRuntime, algorithm: BeamSearchAlgorithm) -> None: ...
    async def arun(self, message: str, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata=None, options=None, trace_context=None) -> StrategyResult: ...
    async def _run_candidate_trials(self, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata, options, trace_context) -> list[StrategyResult]: ...
    async def _score_candidate(self, result, task, *, runner, context, provider, invoke_runner, runner_output_text, started_at, metadata, trace_context) -> float: ...
    def _select_winner(self, candidates, scores) -> tuple[StrategyResult, int]: ...
    def _with_beam_metadata(self, result, *, candidates, scores, winner_index, started_at) -> StrategyResult: ...
    @staticmethod def _parse_score(text: str) -> float: ...
    @staticmethod def _beam_trial_metadata(metadata, *, trial_index) -> dict: ...
```

#### Logic
1. `arun`: record `started_at = self.runtime.middleware.clock()`, then call `_run_candidate_trials` (parallel), then score each, then `_select_winner`, then `_with_beam_metadata`
2. `_run_candidate_trials`: runs `asyncio.gather(*[runtime._arun_once(..., options=dict(options or {})) for i in range(beam_width)])` — each call gets a fresh copy of `options` to avoid cross-trial message leakage
3. `_score_candidate`: calls `runtime._invoke_with_middleware(runner, scorer_prompt, {"system": scorer_system_prompt}, ...)` to get a score string; parses with `_parse_score`
4. `_select_winner`: returns `(max(zip(candidates, scores), key=lambda x: x[1]), winner_index)`
5. `_parse_score`: extracts first integer in scorer output; returns `0.0` on parse failure (safe fallback)
6. `_with_beam_metadata`: attaches `metadata["beam_search"] = {"beam_width": ..., "winner_index": ..., "candidates": tuple({trial_index, stop_reason, score}...), ...}`

#### Edge Cases
- Scorer returns non-numeric output → `_parse_score` returns `0.0`, first candidate wins on tie
- `_arun_once` returns middleware-aborted result → still included in beam, scored, eligible to win
- All candidates stopped with same stop reason → returns first by index

---

### 6.3 DAGDataflowAlgorithm (Public Config)

**File:** `vidbyte/context/algorithms/dag_dataflow.py`
**Type:** New file

#### Interface
```python
@dataclass(frozen=True, slots=True)
class DAGDataflowAlgorithm:
    max_nodes: int = 10
    max_parallel: int = 3
    max_plan_chars: int = 4000
    max_node_output_chars: int = 3000
    planner_system_prompt: str | None = None
    node_system_prompt: str | None = None
    synthesizer_system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    def planner_system_prompt_text(self) -> str: ...
    def node_system_prompt_text(self) -> str: ...
    def synthesizer_system_prompt_text(self) -> str: ...
    def parse_dag_plan(self, plan_text: str) -> list[dict]: ...
    def truncate_node_output(self, output: str) -> str: ...
```

#### Logic
- Validates: `max_nodes >= 1`, `max_parallel >= 1`, `max_plan_chars > 0`, `max_node_output_chars > 0`, prompt overrides non-empty, metadata keys are strings
- `planner_system_prompt_text()` returns override or default: instructs the model to output a JSON array of `{"id": str, "description": str, "dependencies": [str]}` objects
- `parse_dag_plan(plan_text)` extracts the JSON array from the plan output (strips markdown fences, `json.loads`); raises `StrategyExecutionError` on parse failure
- `node_system_prompt_text()` returns a default that instructs each node to solve its specific subtask given available inputs
- `synthesizer_system_prompt_text()` returns a default for the final synthesis call

---

### 6.4 DAGDataflowRuntimeAlgorithm

**File:** `vidbyte/agents/algorithms/dag_dataflow.py`
**Type:** New file

#### Interface
```python
class DAGDataflowRuntimeAlgorithm:
    name = "dag_dataflow"

    def __init__(self, runtime: AgentRuntime, algorithm: DAGDataflowAlgorithm) -> None: ...
    async def arun(self, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata=None, options=None, trace_context=None) -> StrategyResult: ...
    async def _plan_dag(self, message, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> list[dict]: ...
    async def _execute_dag(self, message, nodes, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata, options, trace_context) -> dict[str, str]: ...
    async def _execute_level(self, level_nodes, node_outputs, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata, options, trace_context) -> None: ...
    async def _execute_node(self, node, node_outputs, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata, options, trace_context) -> str: ...
    async def _synthesize(self, message, node_outputs, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> str: ...
    def _build_node_context(self, node, node_outputs, message, context) -> BaseAgentContext: ...
    def _topological_levels(self, nodes) -> list[list[dict]]: ...
    def _with_dag_metadata(self, output, *, nodes, node_outputs, started_at) -> StrategyResult: ...
```

#### Logic
1. `_plan_dag`: calls `runtime._invoke_with_middleware` with planner system prompt; parses JSON DAG from response; validates node count <= `max_nodes`; checks for cycles using DFS; raises `StrategyExecutionError` on invalid DAG
2. `_topological_levels`: groups nodes into levels by Kahn's algorithm; nodes at the same level have no dependency on each other and can run in parallel
3. `_execute_dag`: iterates levels; for each level, calls `_execute_level`; caps parallel execution at `max_parallel` using a semaphore
4. `_execute_node`: calls `runtime._arun_once` with node description + inputs from parent node outputs concatenated into the task; truncates output to `max_node_output_chars`
5. `_synthesize`: calls `runtime._invoke_with_middleware` with all node outputs formatted as a summary; returns the synthesis output text
6. `_with_dag_metadata`: attaches `metadata["dag_dataflow"] = {"node_count": ..., "level_count": ..., "nodes": tuple({id, description, level_index, output_chars}...), ...}`

#### Edge Cases
- Planner output is not valid JSON → `StrategyExecutionError` with message
- DAG contains a cycle → `StrategyExecutionError`
- A node's dependencies are not all in the plan → node marked as having unsatisfied deps, skipped (logged in metadata)
- Node count exceeds `max_nodes` → only first `max_nodes` nodes used, metadata includes truncation flag

---

### 6.5 MarketAuctionAlgorithm (Public Config)

**File:** `vidbyte/context/algorithms/market_auction.py`
**Type:** New file

#### Interface
```python
@dataclass(frozen=True, slots=True)
class MarketAuctionAlgorithm:
    num_agents: int = 3
    max_bid_chars: int = 600
    max_executor_chars: int = 8000
    roles: tuple[str, ...] | None = None
    auctioneer_system_prompt: str | None = None
    bidder_system_prompt: str | None = None
    executor_system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    def auctioneer_system_prompt_text(self) -> str: ...
    def bidder_system_prompt_text(self, role: str) -> str: ...
    def executor_system_prompt_text(self, role: str, approach: str) -> str: ...
    def parse_bid(self, bid_text: str) -> dict: ...
    def select_winner(self, bids: list[dict], roles: list[str]) -> tuple[str, dict]: ...
```

#### Logic
- Validates: `num_agents >= 1`, `max_bid_chars > 0`, `max_executor_chars > 0`, `roles` tuple non-empty when provided, prompt overrides non-empty when set, metadata keys are strings
- If `roles` is set, must have exactly `num_agents` entries (validated in `__post_init__`)
- `auctioneer_system_prompt_text()` returns a default that instructs the model to output `num_agents` specialist role names as a JSON array
- `bidder_system_prompt_text(role)` returns a default instructing the bidder to respond with JSON `{"can_handle": bool, "confidence": 0-10, "approach": str}`
- `parse_bid(bid_text)` extracts JSON bid; returns safe default `{"can_handle": false, "confidence": 0, "approach": ""}` on parse failure
- `select_winner(bids, roles)` returns `(winning_role, winning_bid)` — highest `confidence` among `can_handle=true` bids; falls back to first role if no bidder claims to handle it

---

### 6.6 MarketAuctionRuntimeAlgorithm

**File:** `vidbyte/agents/algorithms/market_auction.py`
**Type:** New file

#### Interface
```python
class MarketAuctionRuntimeAlgorithm:
    name = "market_auction"

    def __init__(self, runtime: AgentRuntime, algorithm: MarketAuctionAlgorithm) -> None: ...
    async def arun(self, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata=None, options=None, trace_context=None) -> StrategyResult: ...
    async def _generate_roles(self, message, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> list[str]: ...
    async def _collect_bids(self, message, roles, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> list[dict]: ...
    async def _run_bid(self, message, role, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> dict: ...
    async def _execute_winner(self, message, role, bid, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata, options, trace_context) -> StrategyResult: ...
    def _build_executor_context(self, context, role, bid) -> BaseAgentContext: ...
    def _with_auction_metadata(self, result, *, roles, bids, winning_role, winning_bid, started_at) -> StrategyResult: ...
```

#### Logic
1. `_generate_roles`: if `algorithm.roles` is set, use those; else call `_invoke_with_middleware` with auctioneer prompt to generate `num_agents` role names (parse JSON array)
2. `_collect_bids`: call `_run_bid` for each role in parallel using `asyncio.gather`
3. `_run_bid`: calls `_invoke_with_middleware` with bidder system prompt (role-specific); parses bid JSON with `algorithm.parse_bid`; truncates `approach` to `max_bid_chars`
4. `_execute_winner`: calls `runtime._arun_once` with executor system prompt injected into context system prompt via `dataclasses.replace`
5. `_with_auction_metadata`: attaches `metadata["market_auction"] = {"role_count": ..., "winning_role": ..., "winning_confidence": ..., "bids": tuple({role, can_handle, confidence}...), ...}`

#### Edge Cases
- All bids have `can_handle=false` → `select_winner` falls back to first role; metadata notes fallback
- Role generation returns fewer roles than `num_agents` → use what was returned, metadata notes count mismatch
- Winner's `_arun_once` returns middleware-aborted result → propagate directly, attach auction metadata

---

### 6.7 GossipAlgorithm (Public Config)

**File:** `vidbyte/context/algorithms/gossip.py`
**Type:** New file

#### Interface
```python
@dataclass(frozen=True, slots=True)
class GossipAlgorithm:
    num_agents: int = 4
    gossip_rounds: int = 3
    max_knowledge_chars: int = 2000
    agent_system_prompt: str | None = None
    merge_system_prompt: str | None = None
    synthesizer_system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    def agent_system_prompt_text(self) -> str: ...
    def merge_system_prompt_text(self) -> str: ...
    def synthesizer_system_prompt_text(self) -> str: ...
    def render_merge_prompt(self, knowledge_a: str, knowledge_b: str) -> str: ...
    def render_synthesis_prompt(self, task: str, knowledge_stores: list[str]) -> str: ...
    def truncate_knowledge(self, output: str) -> str: ...
    def build_angle_for_agent(self, agent_index: int, num_agents: int, task: str) -> str: ...
```

#### Logic
- Validates: `num_agents >= 2`, `gossip_rounds >= 1`, `max_knowledge_chars > 0`, prompt overrides non-empty when set, metadata keys are strings
- `agent_system_prompt_text()` returns default instructing agents to produce a dense knowledge summary
- `merge_system_prompt_text()` returns default instructing the merge model to combine two knowledge stores into one
- `render_merge_prompt(a, b)` returns a formatted prompt with both knowledge stores
- `render_synthesis_prompt(task, stores)` returns a prompt with all converged stores for final answer generation
- `build_angle_for_agent(index, num_agents, task)` generates a perspective prefix: `"Focus on: [angle]"` — distributes angles: first principles, edge cases, alternatives, examples, constraints, etc., cycling if `num_agents > len(angles)`
- `truncate_knowledge(output)` trims to `max_knowledge_chars` with suffix

---

### 6.8 GossipRuntimeAlgorithm

**File:** `vidbyte/agents/algorithms/gossip.py`
**Type:** New file

#### Interface
```python
class GossipRuntimeAlgorithm:
    name = "gossip"

    def __init__(self, runtime: AgentRuntime, algorithm: GossipAlgorithm) -> None: ...
    async def arun(self, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata=None, options=None, trace_context=None) -> StrategyResult: ...
    async def _initialize_agents(self, message, *, runner, context, provider, invoke_runner, runner_output_text, runner_output_metadata, metadata, options, trace_context) -> list[str]: ...
    async def _run_gossip_rounds(self, knowledge_stores, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> list[str]: ...
    async def _merge_pair(self, knowledge_a, knowledge_b, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> str: ...
    async def _synthesize(self, message, knowledge_stores, *, runner, context, provider, invoke_runner, runner_output_text, metadata, trace_context) -> str: ...
    def _gossip_pairs(self, n: int) -> list[tuple[int, int]]: ...
    def _build_agent_context(self, context, agent_index) -> BaseAgentContext: ...
    def _with_gossip_metadata(self, output, *, initial_stores, final_stores, gossip_rounds_completed, started_at) -> StrategyResult: ...
```

#### Logic
1. `_initialize_agents`: calls `asyncio.gather(*[runtime._arun_once(message + "\n\n" + angle, ...) for i in range(num_agents)])` where `angle = algorithm.build_angle_for_agent(i, num_agents, message)`; extracts output from each result; truncates to `max_knowledge_chars`
2. `_run_gossip_rounds`: for each round 1..gossip_rounds:
   a. `_gossip_pairs(n)` produces pairs by shuffling agent indices (deterministic per round using `round_index` as seed for reproducibility) → returns `[(0,1),(2,3),...]`
   b. For each pair, call `_merge_pair` in parallel → get merged knowledge
   c. Both agents in pair receive the merged knowledge (symmetric update of `knowledge_stores[i]`)
3. `_merge_pair`: calls `runtime._invoke_with_middleware` with merge system prompt + `algorithm.render_merge_prompt(a, b)`; returns truncated output
4. `_synthesize`: calls `runtime._invoke_with_middleware` with synthesizer system prompt + `algorithm.render_synthesis_prompt(task, stores)` on final converged stores
5. `_with_gossip_metadata`: attaches `metadata["gossip"] = {"num_agents": ..., "gossip_rounds": ..., "initial_knowledge_chars": tuple(...), "final_knowledge_chars": tuple(...), ...}`

#### Edge Cases
- `num_agents` is odd → last agent is unpaired in that round, keeps its knowledge unchanged; noted in metadata
- `_arun_once` for an agent returns an empty output → knowledge store initialized to `"(no output)"`, still participates in gossip
- Merge call returns empty text → pair keeps agent A's knowledge (conservative fallback)

---

### 6.9 ContextWindowAlgorithm Update

**File:** `vidbyte/context/algorithms/tool_results.py`
**Type:** Modified

Add four new optional fields and update `__post_init__` to include them in the "at most one" constraint:

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    reflexion: ReflexionAlgorithm | None = None
    multi_provider_agentic_grader: MultiProviderAgenticGraderAlgorithm | None = None
    beam_search: BeamSearchAlgorithm | None = None
    dag_dataflow: DAGDataflowAlgorithm | None = None
    market_auction: MarketAuctionAlgorithm | None = None
    gossip: GossipAlgorithm | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        active = [x for x in (
            self.reflexion, self.multi_provider_agentic_grader,
            self.beam_search, self.dag_dataflow, self.market_auction, self.gossip,
        ) if x is not None]
        if len(active) > 1:
            raise ValueError("At most one runtime context-window algorithm can be configured.")
```

---

### 6.10 ContextWindowPresets Update

**File:** `vidbyte/context/presets.py`
**Type:** Modified

Add four new preset properties:

```python
@property
def beam_search(self) -> ContextWindowAlgorithm:
    """Run beam_width parallel agent trials, score each, return the highest-scored result."""
    return ContextWindowAlgorithm(name="beam_search", beam_search=BeamSearchAlgorithm())

@property
def dag_dataflow(self) -> ContextWindowAlgorithm:
    """Plan a dependency graph, execute nodes in topological order with parallelism."""
    return ContextWindowAlgorithm(name="dag_dataflow", dag_dataflow=DAGDataflowAlgorithm())

@property
def market_auction(self) -> ContextWindowAlgorithm:
    """Run a specialist bidding protocol to select and execute the best-fit role."""
    return ContextWindowAlgorithm(name="market_auction", market_auction=MarketAuctionAlgorithm())

@property
def gossip(self) -> ContextWindowAlgorithm:
    """Run N agents with partial knowledge through gossip rounds until convergence."""
    return ContextWindowAlgorithm(name="gossip", gossip=GossipAlgorithm())
```

---

### 6.11 AgentRuntimeContextAlgorithms Dispatcher Update

**File:** `vidbyte/agents/context_algorithms.py`
**Type:** Modified

Extend `detect_algorithm`, `return_algorithm`, and imports to include all four new algorithms. The dispatcher remains the single wiring point — no changes to `AgentRuntime.arun`.

---

### 6.12 Context Algorithms __init__ Update

**File:** `vidbyte/context/algorithms/__init__.py`
**Type:** Modified

Export `BeamSearchAlgorithm`, `DAGDataflowAlgorithm`, `MarketAuctionAlgorithm`, `GossipAlgorithm`.

---

### 6.13 Agents Algorithms __init__ Update

**File:** `vidbyte/agents/algorithms/__init__.py`
**Type:** Modified

Export `BeamSearchRuntimeAlgorithm`, `DAGDataflowRuntimeAlgorithm`, `MarketAuctionRuntimeAlgorithm`, `GossipRuntimeAlgorithm`.

---

## 7. Data Model Changes

No database, schema, or persistent storage changes. All state is in-memory and scoped to a single `arun` call. The only "state" is:

- `list[str]` of knowledge stores in `GossipRuntimeAlgorithm`
- `dict[str, str]` of node outputs in `DAGDataflowRuntimeAlgorithm`
- `list[dict]` of bids in `MarketAuctionRuntimeAlgorithm`
- `list[StrategyResult]` of beam candidates in `BeamSearchRuntimeAlgorithm`

All of these are local to each `arun` call and not shared across calls.

**N/A — no migration strategy needed.**

---

## 8. API Changes

N/A — no HTTP API endpoints. These are Python SDK algorithm presets.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/context/algorithms/beam_search.py` | BeamSearchAlgorithm public config |
| CREATE | `vidbyte/context/algorithms/dag_dataflow.py` | DAGDataflowAlgorithm public config |
| CREATE | `vidbyte/context/algorithms/market_auction.py` | MarketAuctionAlgorithm public config |
| CREATE | `vidbyte/context/algorithms/gossip.py` | GossipAlgorithm public config |
| CREATE | `vidbyte/agents/algorithms/beam_search.py` | BeamSearchRuntimeAlgorithm |
| CREATE | `vidbyte/agents/algorithms/dag_dataflow.py` | DAGDataflowRuntimeAlgorithm |
| CREATE | `vidbyte/agents/algorithms/market_auction.py` | MarketAuctionRuntimeAlgorithm |
| CREATE | `vidbyte/agents/algorithms/gossip.py` | GossipRuntimeAlgorithm |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export four new public config classes |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add four new fields to ContextWindowAlgorithm + __post_init__ |
| MODIFY | `vidbyte/context/presets.py` | Register four new preset properties |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export four new runtime adapters |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Wire four new algorithms in dispatcher |
| CREATE | `tests/test_beam_search_algorithm.py` | Beam Search tests |
| CREATE | `tests/test_dag_dataflow_algorithm.py` | DAG Dataflow tests |
| CREATE | `tests/test_market_auction_algorithm.py` | Market Auction tests |
| CREATE | `tests/test_gossip_algorithm.py` | Gossip tests |
| CREATE | `scripts/test-non-linear-runtimes.py` | Unified verification script |

---

## 10. Testing Plan

All tests use fake runners. No live provider calls.

### Unit Tests

#### Beam Search (`tests/test_beam_search_algorithm.py`)

- `test_context_window_preset_exposes_beam_search_algorithm` — [Hidden Assumption] preset name and type correct
- `test_beam_search_algorithm_raises_on_zero_beam_width` — [Edge Case] `beam_width=0` raises `ConfigurationError`
- `test_beam_search_algorithm_raises_on_negative_scorer_chars` — [Edge Case]
- `test_beam_search_algorithm_rejects_empty_scorer_system_prompt` — [Edge Case]
- `test_beam_search_algorithm_rejects_scorer_prompt_missing_placeholders` — [Hidden Assumption] `{task}` and `{candidate}` required
- `test_beam_search_algorithm_accepts_valid_scorer_prompt_override` — [Hidden Assumption]
- `test_beam_search_algorithm_truncates_candidate_output` — [Silent Failure] truncation preserves suffix
- `test_dispatcher_detects_beam_search_algorithm` — [Hidden Assumption] dispatcher wired correctly
- `test_dispatcher_returns_beam_search_runtime_algorithm` — [Hidden Failure]
- `test_beam_search_runtime_runs_beam_width_trials` — [Hidden Failure] exactly k trials invoked
- `test_beam_search_runtime_returns_highest_scored_candidate` — [Silent Failure] winner selection correct
- `test_beam_search_runtime_handles_non_numeric_scorer_output` — [Hidden Failure] `_parse_score` fallback
- `test_beam_search_runtime_attaches_beam_metadata` — [Hidden Assumption] metadata structure present
- `test_beam_search_runtime_does_not_share_options_across_trials` — [Hidden Failure] message leakage prevention
- `test_beam_search_runtime_preserves_normal_runtime_metadata` — [Silent Failure] middleware metadata not dropped

#### DAG Dataflow (`tests/test_dag_dataflow_algorithm.py`)

- `test_context_window_preset_exposes_dag_dataflow_algorithm` — [Hidden Assumption]
- `test_dag_dataflow_algorithm_raises_on_zero_max_nodes` — [Edge Case]
- `test_dag_dataflow_algorithm_raises_on_zero_max_parallel` — [Edge Case]
- `test_dag_dataflow_algorithm_rejects_empty_planner_prompt` — [Edge Case]
- `test_dag_dataflow_algorithm_parse_dag_plan_valid_json` — [Hidden Assumption] JSON parsing
- `test_dag_dataflow_algorithm_parse_dag_plan_strips_markdown_fences` — [Hidden Failure] fences stripped before parse
- `test_dag_dataflow_algorithm_parse_dag_plan_invalid_json_raises` — [Edge Case]
- `test_dag_dataflow_topological_levels_linear_chain` — [Hidden Assumption] correct level ordering
- `test_dag_dataflow_topological_levels_parallel_roots` — [Hidden Failure] independent nodes at level 0
- `test_dag_dataflow_runtime_detects_cycle_and_raises` — [Edge Case]
- `test_dag_dataflow_runtime_executes_nodes_in_dependency_order` — [Hidden Assumption]
- `test_dag_dataflow_runtime_caps_parallel_execution` — [Hidden Failure] max_parallel respected
- `test_dag_dataflow_runtime_passes_parent_outputs_to_child_nodes` — [Silent Failure] outputs wired correctly
- `test_dag_dataflow_runtime_skips_nodes_exceeding_max_nodes` — [Edge Case]
- `test_dag_dataflow_runtime_attaches_dag_metadata` — [Hidden Assumption]
- `test_dag_dataflow_runtime_synthesizes_from_all_node_outputs` — [Silent Failure]

#### Market Auction (`tests/test_market_auction_algorithm.py`)

- `test_context_window_preset_exposes_market_auction_algorithm` — [Hidden Assumption]
- `test_market_auction_algorithm_raises_on_zero_num_agents` — [Edge Case]
- `test_market_auction_algorithm_raises_on_roles_length_mismatch` — [Edge Case] roles tuple != num_agents
- `test_market_auction_algorithm_rejects_empty_role_string` — [Edge Case]
- `test_market_auction_algorithm_parse_bid_valid_json` — [Hidden Assumption]
- `test_market_auction_algorithm_parse_bid_falls_back_on_malformed` — [Hidden Failure] no crash
- `test_market_auction_algorithm_select_winner_picks_highest_confidence` — [Silent Failure]
- `test_market_auction_algorithm_select_winner_falls_back_when_no_handler` — [Edge Case] all `can_handle=false`
- `test_market_auction_runtime_generates_roles_when_none_provided` — [Hidden Assumption]
- `test_market_auction_runtime_uses_predefined_roles_when_provided` — [Hidden Assumption]
- `test_market_auction_runtime_collects_bids_from_all_roles` — [Hidden Failure] N bid calls issued
- `test_market_auction_runtime_executes_winning_role` — [Silent Failure] winner system prompt injected
- `test_market_auction_runtime_attaches_auction_metadata` — [Hidden Assumption]
- `test_market_auction_runtime_handles_middleware_aborted_winner` — [Hidden Failure]

#### Gossip (`tests/test_gossip_algorithm.py`)

- `test_context_window_preset_exposes_gossip_algorithm` — [Hidden Assumption]
- `test_gossip_algorithm_raises_on_num_agents_less_than_two` — [Edge Case]
- `test_gossip_algorithm_raises_on_zero_gossip_rounds` — [Edge Case]
- `test_gossip_algorithm_raises_on_zero_max_knowledge_chars` — [Edge Case]
- `test_gossip_algorithm_truncates_knowledge` — [Silent Failure] truncation with suffix
- `test_gossip_algorithm_build_angle_cycles_when_more_agents_than_angles` — [Hidden Failure]
- `test_gossip_algorithm_render_merge_prompt_includes_both_stores` — [Hidden Assumption]
- `test_gossip_algorithm_render_synthesis_prompt_includes_all_stores` — [Hidden Assumption]
- `test_gossip_runtime_initializes_n_agents` — [Hidden Failure] exactly N `_arun_once` calls
- `test_gossip_runtime_runs_correct_number_of_rounds` — [Hidden Assumption]
- `test_gossip_runtime_pairs_agents_symmetrically` — [Silent Failure] both agents in pair updated
- `test_gossip_runtime_handles_odd_number_of_agents` — [Edge Case] unpaired agent keeps knowledge
- `test_gossip_runtime_handles_empty_agent_output` — [Edge Case] fallback knowledge store
- `test_gossip_runtime_synthesizes_from_final_knowledge_stores` — [Silent Failure]
- `test_gossip_runtime_attaches_gossip_metadata` — [Hidden Assumption]
- `test_gossip_runtime_does_not_share_options_across_agents` — [Hidden Failure]

### Integration Tests

- Dispatcher detection chain: set `algorithm=ContextWindow.preset.<name>` on a fake `AgentRuntime`, confirm `AgentRuntimeContextAlgorithms.arun(...)` returns the correct result type without falling through to `_arun_once` directly
- The silent failure path: dispatcher returns `None` (no algorithm) → falls through to `_arun_once` correctly; algorithm present → never falls through
- `ContextWindowAlgorithm.__post_init__` with two algorithm fields set simultaneously → `ValueError`

### Manual / QA Test Cases

1. Given `Agent(algorithm=ContextWindow.preset.beam_search, ...)`, when `.run("solve task")` is called, then the result output is the best of `beam_width` trials and `result.metadata["beam_search"]` contains a `winner_index` — [Hidden Assumption]
2. Given a DAG where node B depends on A, when the DAG runtime executes, then node B's agent call receives node A's output in its task context — [Silent Failure]
3. Given `MarketAuctionAlgorithm(num_agents=3)` and all roles returning `can_handle=false`, then the auction falls back to the first role and completes without raising — [Edge Case]
4. Given `GossipAlgorithm(num_agents=3)` (odd number), when gossip runs, then the unpaired agent keeps its knowledge and the round still completes — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` (stdlib) | Python 3.11+ | Parallel `asyncio.gather` for beam/gossip/DAG parallel execution | Low — already used in runtime |
| `json` (stdlib) | Python 3.11+ | DAG plan and bid parsing | Low |
| `vidbyte.lib.errors.ConfigurationError` | internal | Validation errors | None |
| `vidbyte.strategies.types.BaseAgentContext` | internal | Context dataclass replacement | None |

No new third-party dependencies.

---

## 12. Rollout & Deployment

- Not a breaking change — four new preset properties added; existing presets unaffected
- `ContextWindowAlgorithm.__post_init__` change is additive only (more fields in the "at most one" check)
- No feature flags needed
- No migration required — pure Python SDK additions
- Rollback: revert the PR; existing agents using other presets are unaffected

---

## 13. Open Questions

- [ ] Should BeamSearch support multi-step expansion (run → score → expand each winner → score again) or is single-round (run k → score → return best) sufficient for the first implementation? Single-round is proposed here.
- [ ] For DAGDataflow: should the planner stage be a full `_arun_once` with tools, or a lightweight `_invoke_with_middleware` model call? Lightweight call proposed (no tool access in planning stage) to keep planning fast.
- [ ] For Gossip: should agent initialization angles be hardcoded (first principles, edge cases, alternatives, ...) or configurable via a `angles: tuple[str, ...]` config field? Hardcoded with cycling is proposed for simplicity.
- [ ] Should the Market Auction runtime support multi-round bidding (iterative bid refinement) or single-round? Single-round proposed for this implementation.

---

## 14. Alternatives Considered

### Alternative 1: Implement as `strategies/multi_agent/` instead of `agents/algorithms/`
- **What**: Put beam_search, dag_dataflow, market_auction, gossip under `vidbyte/strategies/multi_agent/` following the existing autogen/consensus/vmao pattern
- **Why rejected**: The skill guide (`adding-context-window-algorithms.md`) explicitly defines the `agents/algorithms/` pattern for runtime behaviors attached to an agent via `ContextWindow.preset.<name>`. Multi-agent strategies in `strategies/multi_agent/` are strategy-layer orchestration that compose multiple `Agent` instances. The four runtimes here modify the control flow of a single agent's run, not the inter-agent topology.

### Alternative 2: Add concurrency using `concurrent.futures.ThreadPoolExecutor`
- **What**: Use thread-based parallelism for the parallel agent trials in beam search and gossip
- **Why rejected**: `asyncio.gather` is sufficient for I/O-bound LLM calls and matches the existing async patterns in `AgentRuntime`. Thread pools add complexity without benefit for async model API calls.

### Alternative 3: Store beam/gossip intermediate state in ContextManager
- **What**: Write intermediate candidate outputs and knowledge stores to the agent's `ContextManager`
- **Why rejected**: Context items are for model-visible context, not algorithm intermediate state. Mixing algorithm scratch space into the context manager violates the separation of concerns described in the skill guide.

### Alternative 4: Use prompt catalog Markdown files for scorer/planner/merge prompts
- **What**: Add `vidbyte/prompts/prompts/beam_search/`, `vidbyte/prompts/prompts/dag_dataflow/`, etc. following the Reflexion prompt pattern
- **Why rejected**: The inline prompts for these algorithms are small enough (1-3 sentences) to not warrant the full prompt-catalog machinery. Reflexion uses catalog prompts because its multi-step prompt templates are large and benefit from independent editability. For these four algorithms, inline defaults with override fields are simpler and sufficient. If prompts grow significantly, they can be migrated to the catalog in a follow-up.

---

## Summary

**Files to create:** 9 (4 public configs, 4 runtime adapters, 1 test script)
**Files to modify:** 6 (ContextWindowAlgorithm, presets, 2 `__init__` files, dispatcher, + 4 test files to create)
**Total files touched:** 19

**Key risks:**
1. `asyncio.gather` across multiple `_arun_once` calls — must ensure each call gets a fresh copy of `options` dict to avoid provider message leakage across trials
2. DAG cycle detection — must be correct; a cycle will cause infinite loops without it
3. Dispatcher wiring — each new algorithm must be in `detect_algorithm`, `return_algorithm`, AND the import list in `__init__.py`; missing any one causes a silent no-op where the algorithm preset exists but never runs

**Open questions before proceeding:**
1. Single-round vs multi-step beam search?
2. Planner stage: full agent (`_arun_once`) or lightweight call (`_invoke_with_middleware`)?
3. Gossip angles: hardcoded or configurable?
4. Market auction: single-round or multi-round bidding?
