# Design Doc: Aggregate Agent (Mixture-of-Agents)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-13
**Last Updated:** 2026-06-13

---

## 1. Overview

`AggregateAgent` adds a Mixture-of-Agents (MoA) capability to the Vidbyte SDK: a single request is fanned out concurrently to several **proposer** models, and the resulting candidate answers are routed to a configurable **aggregator** model that *synthesizes a new response* from all of them (it composes its own answer; it does not select a winner). The feature is exposed three ways — a standalone `AggregateAgent` class under `vidbyte/agents`, an agent-callable tool via the existing `as_tool()` path, and a native `BaseAgent` overload that activates aggregation automatically when the agent is constructed with more than one model.

---

## 2. Goals & Non-Goals

### Goals
- A `MultiProviderAggregator` engine that fans out to N proposer agents concurrently and synthesizes their outputs through an aggregator agent.
- An `AggregateAgent` (subclass of `BaseAgent`) configured with a rich list of proposer specs and one aggregator spec.
- Proposer specs allow **same-provider duplicates** (e.g. two OpenAI models) via an explicit label.
- Synthesis (not selection): the aggregator writes a new answer grounded in the candidate set.
- Expose the aggregator as an agent tool through the existing `BaseAgent.as_tool()` / `AgentTool` machinery (no new tool type required).
- Native `BaseAgent` overload: passing `model_name=["a", "b", ...]` (or `proposers=[...]`) makes `arun()`/`generate_reply()` run the aggregation under the hood.
- Resilient partial failure: a failed proposer is dropped; synthesis proceeds when at least `min_successful` proposers succeed.
- A reusable synthesis prompt asset added to the prompt catalog (mirrors the existing grader family).

### Non-Goals
- Multi-layer / recursive MoA (proposers → aggregator → re-propose). Single layer only; layering is a follow-up.
- Changing or refactoring the existing `MultiProviderAgenticGrader` (select-a-winner) algorithm.
- Wiring aggregation as a `ContextWindow` context-window algorithm / preset (the grader's path). The native surface here is the constructor + `arun` overload, per the chosen design.
- Streaming, cross-proposer shared context, or tool-use by the aggregator (the aggregator only synthesizes text).
- New provider adapters or runner types.

---

## 3. Background & Context

The SDK already ships the *sibling* of this feature: `MultiProviderAgenticGrader` (`vidbyte/agents/algorithms/multi_provider_agentic_grader.py`) fans a task out across providers and then runs a **meta-grader** that **selects** the single best candidate. The requested feature is the same fan-out with a different tail: **synthesize** a new answer instead of selecting one.

`MapReducePipeline` (`vidbyte/pipelines/map_reduce.py`) is the string-in/string-out version of fan-out + reduce, but pipelines deliberately drop structured metadata (per-proposer outputs, token usage, partial-failure info) and cannot be used as an agent tool. The agent-layer `AggregateAgent` preserves that structure and plugs into `as_tool()`, registries, and pipelines because every SDK agent is duck-typed by `async generate_reply(message, **opts) -> AgentMessage`.

The grader keys candidates by **provider name** (`Mapping[str, str]`), which structurally cannot represent two models from the same provider. The aggregator therefore introduces a richer `ProposerSpec` (provider + model + label) keyed by label.

Constraint: no live LLM calls in tests. The codebase tests agents with fakes that implement only `generate_reply` (see `tests/test_pipelines.py`). The engine is designed to accept any such agent-like object so it is fully testable offline.

---

## 4. Requirements

### Functional Requirements
1. `MultiProviderAggregator(proposers, aggregator, config)` runs all proposers concurrently on the same prompt and returns an `AggregateResult` containing the synthesized text, the per-label candidate map, and metadata.
2. The aggregator receives a message composed of the original request plus a labeled block of all surviving candidate outputs, under a synthesis system prompt instructing it to compose (not choose).
3. A proposer that raises, times out, or returns blank is dropped from the candidate set.
4. If fewer than `min_successful` proposers succeed, an `AggregateExecutionError` (subclass of `AgentExecutionError`) is raised.
5. `AggregateAgent(name, system_prompt, proposers=[...], aggregator=..., ...)` builds proposer `BaseAgent`s and an aggregator `BaseAgent`, and `generate_reply()` returns the synthesized `AgentMessage`.
6. `ProposerSpec` supports `provider`, `model`, optional `label` (defaults to a deterministic unique label), and optional per-proposer `system_prompt`. Proposers may also be supplied as pre-built agent-like objects (injection seam / custom proposers).
7. Same-provider duplicates are supported and produce distinct candidate labels.
8. `AggregateAgent.as_tool()` returns an `AgentTool` (validating `agent_metadata`), usable inside another agent's `tools=[...]`.
9. `AggregateAgent.fork()` returns an `AggregateAgent` preserving proposer/aggregator/config so the `as_tool()` execution path aggregates correctly.
10. `BaseAgent(..., model_name=["a","b"])` or `BaseAgent(..., proposers=[...], aggregator=...)` activates aggregation: `generate_reply()` delegates to an internal `AggregateAgent`. With 0 or 1 proposer the existing single-model path is unchanged.
11. `model_name=["a","b"]` sugar expands to proposers `[(self.provider, "a"), (self.provider, "b")]`; cross-provider requires explicit `proposers=[("openai","o3"), ("anthropic","claude-...")]`.
12. The aggregator defaults to the host agent's own `(provider, model_name)` when not explicitly given; if neither is resolvable, construction raises `ConfigurationError`.
13. A `multi_provider_aggregator` prompt family (`synthesis_system_prompt`, `synthesis_prompt`) is added to the catalog and used as the defaults.
14. `sdk.agents.aggregate(...)` factory constructs an `AggregateAgent`.
15. `AggregateAgent`, `ProposerSpec`, `AggregateConfig`, `MultiProviderAggregator` are importable from `vidbyte`.

### Non-Functional Requirements
- **Performance:** proposers run concurrently via `asyncio.gather`; total latency ≈ slowest surviving proposer + one synthesis call. Optional `max_concurrency` semaphore and `per_proposer_timeout`.
- **Cost:** N + 1 model calls; documented, with metadata reporting per-label success/failure.
- **Reliability:** fan-out uses `return_exceptions=True`; one proposer failure never aborts the run unless it breaches `min_successful`.
- **Observability:** result metadata carries `candidates`, `successful_labels`, `failed_labels`, `proposer_count`. No new tracer required; child `BaseAgent`s emit their own spans.
- **Security:** no new permissions. Proposers inherit the host agent's tools/permission policy; the aggregator runs tool-free.
- **Compatibility:** zero behavior change for any agent constructed with a single (or no) model.

---

## 5. High-Level Design

Three layers, one engine.

```
                         ┌─────────────────────────────────────────┐
 BaseAgent(model_name=   │  generate_reply(prompt)                  │
   ["a","b"])  ────────► │   if multi-model plan: delegate ─────────┼──► AggregateAgent
 AggregateAgent(...)  ─► │   else: existing single-model path       │        │
                         └─────────────────────────────────────────┘        │
                                                                            ▼
                                                  MultiProviderAggregator.aggregate(prompt)
                                                    │ 1. _run_proposers  (gather, return_exceptions)
                                                    │ 2. _collect_candidates (drop failures, min_successful)
                                                    │ 3. _build_candidates_block (label-keyed, truncated)
                                                    │ 4. _synthesize (aggregator.generate_reply)
                                                    ▼
                                                  AggregateResult(content, candidates, metadata)
```

- **Engine** (`MultiProviderAggregator`): pure orchestration over agent-like objects; no `BaseAgent` import, so it is testable with fakes.
- **`AggregateAgent`** (`BaseAgent` subclass): normalizes `ProposerSpec`s into child `BaseAgent`s and an aggregator `BaseAgent`, owns one engine, and overrides `generate_reply`/`fork`. Inherits `run`, `arun`, `as_tool`, registry compatibility for free.
- **`BaseAgent` overload**: constructor detects a multi-model plan, builds an internal `AggregateAgent`, and `generate_reply` short-circuits to it. The single-model code path is untouched when there is no plan.

Key decisions:
- **Compose child `BaseAgent`s rather than re-implement runners.** Each proposer is a real agent, so existing provider/runner/middleware/tool machinery is reused unchanged.
- **Subclass `BaseAgent` for `AggregateAgent`** to inherit the public agent surface (`run`/`arun`/`as_tool`/`fork`/registry), overriding only `__init__`, `generate_reply`, `fork`.
- **Synthesis prompt lives in the catalog** for parity with the grader and developer override-ability.
- **`as_tool()` reuse** — no new tool class; `AgentTool` already forwards parent context to `fork().generate_reply()`.

---

## 6. Detailed Design

### 6.1 ProposerSpec & AggregateConfig

**File:** `vidbyte/lib/dataclasses/multi_agent.py`
**Type:** Modified (append two dataclasses)

#### What it does
Typed, validated configuration for proposers and the aggregation run.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ProposerSpec:
    provider: str
    model: str
    label: str | None = None
    system_prompt: str | None = None

@dataclass(frozen=True, slots=True)
class AggregateConfig:
    synthesis_system_prompt: str | None = None   # None -> catalog default at agent build time
    synthesis_prompt_template: str | None = None  # None -> catalog default; must contain {request} and {candidates}
    max_candidate_chars: int = 8000               # per-candidate truncation
    max_concurrency: int | None = None
    per_proposer_timeout: float | None = None
    min_successful: int = 1
```

#### Logic / Algorithm
1. Frozen dataclasses; no behavior beyond carrying values.
2. Validation of `min_successful >= 1`, `max_candidate_chars > 0`, and template placeholders is performed by the engine/agent at construction (Section 6.2/6.3), keeping these pure carriers consistent with existing dataclasses in this module.

#### Edge Cases & Error Handling
- `label=None` → engine derives a unique deterministic label.
- Conflicting/duplicate explicit labels → engine raises `ConfigurationError`.

---

### 6.2 MultiProviderAggregator (engine)

**File:** `vidbyte/agents/aggregation.py`
**Type:** New file

#### What it does
Fans out a prompt to proposer agent-likes concurrently and synthesizes the surviving candidates through an aggregator agent-like.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AggregateResult:
    content: str
    candidates: Mapping[str, str]
    metadata: Mapping[str, Any]

class MultiProviderAggregator:
    def __init__(self, proposers: Sequence[LabeledAgent], aggregator: object, config: AggregateConfig, prompt_template: str) -> None: ...
    async def aggregate(self, prompt: str) -> AggregateResult: ...
    async def _run_proposers(self, prompt: str) -> list[tuple[str, object]]: ...
    def _collect_candidates(self, results: list[tuple[str, object]]) -> dict[str, str]: ...
    def _build_candidates_block(self, candidates: Mapping[str, str]) -> str: ...
    async def _synthesize(self, prompt: str, candidates_block: str) -> object: ...
```
`LabeledAgent` is a small `(label, agent)` pairing; `agent` is any object with `async generate_reply(str, **opts) -> AgentMessage`.

#### Logic / Algorithm
1. `aggregate` calls `_run_proposers`, `_collect_candidates`, `_build_candidates_block`, `_synthesize`, and assembles `AggregateResult`.
2. `_run_proposers`: build one task per proposer (each optionally wrapped in `asyncio.wait_for` and a shared `asyncio.Semaphore`); `asyncio.gather(..., return_exceptions=True)`; return `(label, result_or_exception)` pairs preserving order.
3. `_collect_candidates`: keep entries whose result is a non-blank `AgentMessage`; map `label -> content`. If `len(kept) < config.min_successful`, raise `AggregateExecutionError` listing failures.
4. `_build_candidates_block`: for each label, append `### Candidate [{label}]\n{truncated_text}\n` where text is truncated to `max_candidate_chars`.
5. `_synthesize`: format `prompt_template` with `request=prompt` and `candidates=block`; call `aggregator.generate_reply(message)`; return its `AgentMessage`.
6. Metadata: `{ "aggregate": { candidates, successful_labels, failed_labels, proposer_count } }`.

#### Edge Cases & Error Handling
- All proposers fail → `AggregateExecutionError`.
- Proposer returns empty/whitespace content → treated as failure (silent-failure guard).
- Timeout → `asyncio.TimeoutError` captured as a failure for that proposer, not a run abort.
- Aggregator raises → propagates (the synthesis step is required).

---

### 6.3 AggregateAgent

**File:** `vidbyte/agents/aggregation.py`
**Type:** New (same file as engine)

#### What it does
A `BaseAgent` whose `generate_reply` runs MoA aggregation over child agents built from `ProposerSpec`s and an aggregator spec.

#### Interface / API
```python
class AggregateAgent(BaseAgent):
    def __init__(self, *, name: str, system_prompt: str, proposers: Sequence[ProposerSpec | tuple | object], aggregator: ProposerSpec | tuple | object | None = None, config: AggregateConfig | None = None, api_key: str | None = None, agent_metadata: AgentMetadata | None = None, tools: Sequence[object] | Tools = (), middleware: Sequence[AgentMiddleware] = (), temperature: float | None = None, metadata: dict | None = None, **base_kwargs) -> None: ...
    async def generate_reply(self, message: str | AgentInput, **options) -> AgentMessage: ...
    def fork(self, *, name: str | None = None, **overrides) -> "AggregateAgent": ...
```

#### Logic / Algorithm
1. `__init__` calls `super().__init__` with `system_prompt` and no model (single-model machinery stays dormant), then `_build_proposers`, `_build_aggregator`, `_build_engine`.
2. `_build_proposers`: normalize each item — a `ProposerSpec`/tuple becomes a child `BaseAgent(provider, model, system_prompt=spec.system_prompt or self.system_prompt, tools=..., middleware=..., api_key=...)`; an object already exposing `generate_reply` is used as-is. Assign labels (explicit, else `f"{provider}:{model}"`, de-duplicated with `#2`, `#3`).
3. `_build_aggregator`: resolve aggregator spec, defaulting to `(self.provider, self.model_name)`; build a tool-free `BaseAgent` with the synthesis system prompt (config override or catalog default). Raise `ConfigurationError` if unresolvable.
4. `_build_engine`: resolve the synthesis prompt template (config override or catalog default), construct `MultiProviderAggregator`.
5. `generate_reply`: normalize input to text, call `engine.aggregate(prompt)`, wrap into an `AgentMessage(sender=self.name, recipient=..., content=result.content, metadata=result.metadata)`, append to history.
6. `fork`: rebuild an `AggregateAgent` with the same proposers/aggregator/config (overridable), preserving aggregation under `as_tool()`.

#### Edge Cases & Error Handling
- Empty `proposers` → `ConfigurationError` at construction.
- `as_tool()` without `agent_metadata` → inherited `ConfigurationError` from `BaseAgent.as_tool()`.
- Duplicate explicit labels → `ConfigurationError`.

---

### 6.4 BaseAgent native overload

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Lets a plain `BaseAgent` act as an aggregate agent when configured with multiple models.

#### Interface / API
New constructor keyword args: `proposers: Sequence[...] | None = None`, `aggregator: ProposerSpec | tuple | None = None`, `aggregate: AggregateConfig | None = None`. `model_name` accepts `str | Sequence[str] | None`.

#### Logic / Algorithm
1. Early in `__init__`, `_resolve_aggregate_plan` inspects `proposers` and `model_name`:
   - If `proposers` has ≥1 entry, or `model_name` is a non-string sequence of ≥2 entries → build a plan.
   - `model_name` list expands to `[ProposerSpec(self.provider, m) for m in model_name]`.
   - Store `self._aggregate_agent = AggregateAgent(...)` (lazy import to avoid a cycle) and set the host's own `model_name` to `None` so single-model machinery stays inert.
   - Otherwise `self._aggregate_agent = None`.
2. Validate: a plan combined with a non-linear runtime (`MCTS_SEARCH`/`ACTOR_*`) raises `ConfigurationError` (mirrors existing guards at `base.py:101`).
3. In `generate_reply`, first line: `if self._aggregate_agent is not None: return await self._aggregate_agent.generate_reply(message, **options)`.

#### Edge Cases & Error Handling
- Single-element `model_name=["a"]` → treated as single model (no plan), `provider`+`"a"` as normal.
- `proposers` set but aggregator unresolvable → `ConfigurationError` (from `AggregateAgent`).
- `output_schema` + plan → schema is applied to the aggregator child only (documented).

---

### 6.5 Synthesis prompt catalog family

**Files:**
- `vidbyte/prompts/prompts/multi_provider_aggregator/multi_provider_aggregator.json` (New)
- `vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_system_prompt.md` (New)
- `vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_prompt.md` (New)
- `vidbyte/lib/enums/prompts.py` (Modified — add two members)

#### What it does
Adds developer-inspectable/override-able default prompts: the aggregator system prompt ("synthesize a single best answer from the candidates; compose your own response, do not merely pick one") and the synthesis user template containing `{request}` and `{candidates}`.

#### Logic / Algorithm
1. JSON manifest mirrors the grader manifest: `name`, `description`, `key="multi_provider_aggregator"`, `prompts` map referencing the two `.md` files.
2. Enum members `MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_SYSTEM_PROMPT = "multi_provider_aggregator.synthesis_system_prompt"` and `MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_PROMPT = "multi_provider_aggregator.synthesis_prompt"`.
3. The catalog auto-discovers the family; `Prompts._validate_enum_sync` enforces enum⇄asset parity (both files + both enum members required).

#### Edge Cases & Error Handling
- Missing `.md` or enum member → `ConfigurationError` at catalog load (caught by tests/`compileall`).
- `synthesis_prompt.md` must contain `{request}` and `{candidates}`; the engine validates placeholders when a custom template is provided.

---

### 6.6 Exports & factory

**Files:** `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/agents/client.py` (all Modified)

- `agents/__init__.py`: export `AggregateAgent`, `MultiProviderAggregator`, `AggregateResult`.
- `vidbyte/__init__.py`: re-export `AggregateAgent`, `MultiProviderAggregator`, `ProposerSpec`, `AggregateConfig`.
- `agents/client.py`: add `def aggregate(self, **kwargs) -> AggregateAgent` returning `AggregateAgent(**kwargs)`.

---

## 7. Data Model Changes

N/A — no persistent store. New in-memory dataclasses (`ProposerSpec`, `AggregateConfig`, `AggregateResult`) are covered in Section 6.

---

## 8. API Changes

N/A — no HTTP/RPC endpoints. The public Python API additions are the classes, constructor kwargs, and factory listed in Sections 6.3–6.6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/aggregate-agent.md` | This design doc |
| CREATE | `vidbyte/agents/aggregation.py` | `MultiProviderAggregator` engine, `AggregateResult`, `AggregateAgent` |
| CREATE | `vidbyte/prompts/prompts/multi_provider_aggregator/multi_provider_aggregator.json` | Prompt family manifest |
| CREATE | `vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_system_prompt.md` | Aggregator system prompt |
| CREATE | `vidbyte/prompts/prompts/multi_provider_aggregator/synthesis_prompt.md` | Synthesis user template (`{request}`,`{candidates}`) |
| CREATE | `tests/test_aggregate_agent.py` | Unit test suite |
| CREATE | `scripts/test_aggregate_agent.py` | Standalone verification script |
| MODIFY | `vidbyte/lib/dataclasses/multi_agent.py` | Add `ProposerSpec`, `AggregateConfig` |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add two `Prompt` members |
| MODIFY | `vidbyte/agents/base.py` | Multi-model plan detection + `generate_reply` delegation |
| MODIFY | `vidbyte/agents/__init__.py` | Export aggregation symbols |
| MODIFY | `vidbyte/agents/client.py` | `agents.aggregate(...)` factory |
| MODIFY | `vidbyte/__init__.py` | Top-level exports |
| MODIFY | `vidbyte/lib/errors/__init__.py` (or `base.py`) | Add `AggregateExecutionError` if not present |

---

## 10. Testing Plan

Engine tests use fake agent-likes (a la `tests/test_pipelines.py`); no live models. Agent/overload tests inject fakes through the proposer/aggregator object seam.

### Unit Tests
- `MultiProviderAggregator` → `it synthesizes from multiple candidates` — happy path: 3 fakes + aggregator that echoes the candidates block; assert all candidate texts present in synthesis input. — [Edge Case]
- `MultiProviderAggregator` → `it runs with a single proposer` — list of 1. — [Edge Case]
- `MultiProviderAggregator` → `it passes the SAME prompt to every proposer` — recording fakes; assert identical inputs. — [Silent Failure]
- `MultiProviderAggregator` → `it drops a failing proposer and still synthesizes` — one raising fake; survivor synthesized; `failed_labels` records it. — [Hidden Failure]
- `MultiProviderAggregator` → `it raises AggregateExecutionError when all proposers fail` — every fake raises. — [Edge Case]
- `MultiProviderAggregator` → `it raises when successes < min_successful` — 1 success, `min_successful=2`. — [Hidden Assumption]
- `MultiProviderAggregator` → `it treats blank proposer output as failure` — fake returns `"   "`. — [Silent Failure]
- `MultiProviderAggregator` → `it truncates candidate text to max_candidate_chars` — long output; assert block length bounded and ellipsis/cut applied. — [Silent Failure]
- `MultiProviderAggregator` → `it distinguishes same-provider duplicates by label` — two `openai:gpt-4.1` proposers get distinct labels; both appear. — [Silent Failure]
- `MultiProviderAggregator` → `it honors per_proposer_timeout` — a slow fake exceeds timeout and is dropped. — [Hidden Failure]
- `AggregateAgent` → `it raises ConfigurationError when proposers is empty` — [Edge Case]
- `AggregateAgent` → `it raises ConfigurationError when aggregator unresolvable` — no aggregator and no host model. — [Hidden Assumption]
- `AggregateAgent` → `it returns an AgentMessage whose metadata carries candidates` — with injected fakes. — [Edge Case]
- `AggregateAgent` → `it forks preserving aggregation behavior` — `fork()` then `generate_reply` still aggregates. — [Hidden Assumption]
- `AggregateAgent` → `it exposes as_tool only when agent_metadata is filled` — missing metadata raises; filled returns an `AgentTool`. — [Hidden Assumption]
- `AggregateAgent` → `as_tool execution aggregates and forwards parent context` — call the tool; assert synthesized output. — [Hidden Failure]
- `AggregateAgent` → `it builds distinct child agents per proposer spec` — assert proposer count. — [Edge Case]
- `BaseAgent overload` → `model_name list of 2 builds an aggregate plan` — assert `_aggregate_agent is not None`. — [Edge Case]
- `BaseAgent overload` → `model_name single string does NOT build a plan` — `_aggregate_agent is None`, normal path. — [Silent Failure]
- `BaseAgent overload` → `generate_reply delegates to the aggregate agent` — inject fakes; assert synthesized output returned. — [Hidden Failure]
- `BaseAgent overload` → `multi-model plan with MCTS runtime raises ConfigurationError` — [Hidden Assumption]
- `BaseAgent overload` → `single-model agent behavior is unchanged` — regression guard against existing path. — [Silent Failure]
- `prompts` → `multi_provider_aggregator family loads with both assets` — `Prompts().family("multi_provider_aggregator")` has both keys. — [Hidden Assumption]
- `prompts` → `synthesis template exposes {request} and {candidates}` placeholders. — [Silent Failure]
- `exports` → `AggregateAgent/ProposerSpec/AggregateConfig importable from vidbyte` — [Edge Case]

### Integration Tests
- End-to-end with fakes through the public `vidbyte` import surface: build `AggregateAgent` via `sdk.agents.aggregate(...)` using injected proposer/aggregator agent objects, call `run_sync`/`arun`, assert synthesized content + metadata. Mock boundary = the agent-like objects (no provider/runner). Silent-failure path: ensure metadata `candidates` count matches surviving proposers, not the configured count, when one fails. Hidden assumption surfaced only here: `AgentTool` context-forwarding works when an `AggregateAgent.as_tool()` is placed in a parent `BaseAgent.tools`.

### Manual / QA Test Cases
1. Given valid API keys for OpenAI + Anthropic, when running `AggregateAgent(proposers=[("openai","gpt-4.1"),("anthropic","claude-opus-4-8")], aggregator=("openai","gpt-4.1"))` on a real prompt, then a synthesized answer returns and `metadata["aggregate"]["successful_labels"]` lists both. — [Edge Case]
2. Given one invalid model name among proposers, when running, then the run still returns a synthesis from the valid proposer and the invalid one appears in `failed_labels`. — [Hidden Failure]
3. Given `model_name=["gpt-4.1","gpt-4.1-mini"]` + `provider="openai"`, when calling `arun`, then aggregation runs across both. — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` (stdlib) | — | Concurrent fan-out, timeouts, semaphore | Low |
| Existing `BaseAgent`/runner stack | in-repo | Proposer + aggregator execution | Low — reused unchanged |
| Prompt catalog (`Prompts`) | in-repo | Default synthesis prompts | Low — enum⇄asset parity enforced |

No new third-party packages.

---

## 12. Rollout & Deployment

- Purely additive; no feature flag. New constructor kwargs default to `None`, preserving all existing behavior.
- Not a breaking change: `model_name: str` callers are unaffected; only a ≥2-element sequence activates the new path.
- No deployment ordering or migration. Rollback = revert the PR.

---

## 13. Open Questions

- [ ] Should the aggregator be allowed tools/middleware in a later iteration (currently intentionally tool-free)?
- [ ] Should multi-layer MoA be a follow-up `layers=` parameter on `AggregateConfig`?
- [ ] Should an `AggregatePipeline` convenience wrapper be added to `vidbyte/pipelines` for the string-in/out crowd? (Deferred; `MapReducePipeline` already covers it.)

---

## 14. Alternatives Considered

### Alternative 1: Implement aggregation as a `ContextWindow` algorithm/preset (the grader's path)
- What: add `MultiProviderAggregatorAlgorithm` + runtime adapter + `ContextWindow.preset.multi_provider_aggregator`, and trigger it from `BaseAgent` via `algorithm=`.
- Why rejected: deep coupling to the 66k-line runtime and its `provider_models: Mapping[str,str]` shape (cannot express same-provider duplicates, a hard requirement). The chosen design composes real `BaseAgent`s, supports rich proposer specs natively, and is testable with fakes. (A future PR could still add the preset as a thin wrapper.)

### Alternative 2: Standalone `AggregateAgent` (not subclassing `BaseAgent`)
- What: a fresh class implementing the agent surface from scratch.
- Why rejected: would re-implement `run`/`as_tool`/`fork`/registry compatibility. Subclassing inherits these and overrides only three methods.

### Alternative 3: Overload `arun` to inspect `model_name` at call time
- What: detect list models inside `arun` each call.
- Why rejected: construction-time plan detection fails fast on invalid combos (non-linear runtime, unresolvable aggregator) and keeps `generate_reply` a one-line delegation. Same ergonomics, earlier errors.

### Alternative 4: Reuse `MapReducePipeline`
- What: build aggregation as a map-reduce of per-model forks.
- Why rejected: pipelines are string-in/out and cannot be an agent tool or carry per-proposer/token metadata. Kept as the complementary lightweight option.

---

END OF DESIGN DOC
