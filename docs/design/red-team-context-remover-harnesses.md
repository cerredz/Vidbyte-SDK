# Design Doc: Red-Team Challenge and Context Remover Harnesses

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

Add two advanced harness paradigms to `vidbyte-sdk`: `RedTeamChallengeHarness`, a dual-agent adversarial simulator that alternates builder and breaker pipelines until a resilience outcome is reached, and `ContextRemoverHarness`, an outer wrapper that periodically compresses noisy execution traces into high-signal semantic summaries. Both harnesses will use shared ledger, state, prompt, tool, and error abstractions planned elsewhere in the SDK while staying additive to the current minimal package scaffold.

---

## 2. Goals & Non-Goals

### Goals

- Implement a red-team/blue-team coordinator that does not use a single `run_iteration()` method.
- Represent blue-team and red-team execution as separate configurable pipelines with distinct model functions, tools, strategies, and role metadata.
- Maintain an unredacted master ledger plus filtered blue/red context views.
- Track artifact revisions, attack attempts, vulnerabilities, patch attempts, and round-level resilience scores.
- Add a `StoppingConditionEvaluator` contract that computes equilibrium from exploit severity and defensive adaptability rather than completion text.
- Raise a typed `ExploitSuccessError` immediately when the red team triggers a fatal violation.
- Return the highest-scoring artifact when the adversarial loop exhausts its step budget.
- Implement `ContextRemoverHarness` as an outer wrapper around any compatible downstream harness or execution callable.
- Periodically freeze execution every configured `purify_every_n_steps` downstream transactions.
- Run purification through `PromptRegistry` key `harnesses.context_remover.purify`.
- Destructively replace noisy active history with a concentrated semantic summary while preserving the original intent anchor.
- Keep Python `>=3.11` and avoid adding runtime dependencies.
- Add focused `unittest` coverage using fake model functions, fake tools, and fake downstream harnesses.

### Non-Goals

- No real vulnerability scanner, fuzzer, chaos injector, sandbox, or destructive tool implementation in this PR.
- No live model-provider calls in automated tests.
- No guarantee that a generated artifact is literally unexploitable outside the configured red-team tools and evaluation budget.
- No external persistence, database timeline storage, or distributed execution engine.
- No UI for viewing attack transcripts or purified traces.
- No replacement for the broader agent, strategy, tool, or prompt-registry designs already documented in this repo.
- No hidden chain-of-thought storage; ledger entries store model-visible inputs, outputs, tool calls, tool results, and structured metadata only.

---

## 3. Background & Context

- The audited source is currently a minimal Python package scaffold. `VidbyteSDK` exposes `harnesses`, `tools`, and `providers`; those namespace clients are empty.
- Existing design docs under `docs/design/` describe planned `BaseTool`, `ToolRegistry`, `ToolExecutor`, `BaseStrategy`, `BaseAgent`, `PromptRegistry`, `BaseHarness`, and `StoppingConditionEvaluator`-style conditional harness concepts, but those are not implemented in source yet.
- `pyproject.toml` declares Python `>=3.11` and `dependencies = []`; this design preserves that constraint.
- Existing package guidance in `skills/vidbyte-sdk/SKILL.md` says not to add concrete implementations until structure is approved. This design is the approval artifact for these two harnesses.
- The user request explicitly requires two distinct operational paradigms:
  - A turn-based adversarial simulator with blue-team and red-team state isolation.
  - A lossy context purifier wrapper that periodically mutates active trace state.
- Several planned designs may land before implementation. The implementation should reuse their concrete classes when present and otherwise introduce the narrow compatibility protocols listed here.

---

## 4. Requirements

### Functional Requirements

1. `RedTeamChallengeHarness` must be importable from `vidbyte.harnesses.red_team`.
2. `ContextRemoverHarness` must be importable from `vidbyte.harnesses.context_remover`.
3. Red-team execution must be modeled as a dual-agent coordinator with separate blue and red pipelines.
4. Blue and red pipelines must each accept their own model function, tools, strategy object, role metadata, and optional prompt key overrides.
5. The adversarial loop must execute in alternating blue then red turns.
6. The blue pipeline must receive the current artifact plus the prior red finding summary, not the full unredacted red private context by default.
7. The red pipeline must receive the latest artifact as target plus the red-filtered attack history, not private blue planning context by default.
8. The state must maintain one unredacted master ledger.
9. The state must maintain separate filtered context views for blue and red turns.
10. Each blue turn must emit a structural artifact update.
11. Each red turn must emit an attack result that may include warnings, exceptions, contract violations, payloads, and severity.
12. Each full round must run a stopping/evaluation judge after one blue step and one red step.
13. The evaluator must compute a `0.0` to `1.0` equilibrium score from exploit severity and defensive adaptability.
14. Exploit severity must increase when red-team output includes unhandled exceptions, contract violations, security findings, or stability crashes.
15. Defensive adaptability must increase when the latest blue artifact addresses vulnerabilities found in previous red logs.
16. A defensive win must terminate when the red team fails to surface warnings or exceptions for a configurable number of consecutive attack iterations against the latest artifact.
17. An adversarial win must terminate immediately when red triggers a configured fatal threshold.
18. Fatal adversarial wins must raise `ExploitSuccessError` with the exact exploit payload and safe structured metadata.
19. Exhaustion must terminate when `max_rounds` or `max_steps` is reached.
20. Exhaustion must return the highest-scoring artifact revision generated during the run.
21. `ContextRemoverHarness` must wrap a downstream execution target rather than owning a custom model loop.
22. `ContextRemoverHarness` must count downstream model transactions, tool executions, or generic steps.
23. If `purify_every_n_steps = 3`, three downstream steps must run normally, then purification must occur before the fourth step proceeds.
24. Purification must receive the immutable anchor, raw execution ledger, and target extraction contract.
25. Purification must use `PromptRegistry` key `harnesses.context_remover.purify` by default.
26. Purification must run in an isolated background context that does not append its raw intermediate trace to the active primary ledger.
27. After purification, the harness must purge the bloated active history array in the active state.
28. After purification, the harness must inject the semantic summary as the new baseline context.
29. After purification, token/accounting metadata must be recalibrated from the new baseline.
30. Both harnesses must expose structured final results containing outcome status, scores, artifacts or summaries, and ledger metadata.

### Non-Functional Requirements

- Security: fatal exploit payloads must be stored exactly in `ExploitSuccessError.payload`, but logs and string representations should avoid dumping large secrets or full raw ledgers by default.
- Security: red-team tools are developer-injected; the SDK must not ship destructive host tools in this PR.
- Security: filtered context views must prevent accidental sharing of private pipeline instructions unless explicitly configured.
- Reliability: all loops must have explicit bounded stop conditions.
- Reliability: evaluator failures must surface as typed harness errors, not silent defensive wins.
- Cost control: fanout, max rounds, consecutive clean attacks, purification frequency, and retained ledger size must be configurable.
- Observability: round metadata must include current score, exploit severity, defensive adaptability, best artifact revision, and termination reason.
- Maintainability: public packages must use explicit `__all__`.
- Compatibility: Python `>=3.11`, standard library only.
- Testability: fake pipelines and fake purifier model functions must support deterministic unit tests without network calls.

---

## 5. High-Level Design

The feature adds a shared harness core for ledger entries, filtered views, state mutation, model-call protocols, and score/evaluation types. The red-team harness then composes two `HarnessPipeline` instances and alternates them through a coordinator loop. The context remover harness wraps any compatible downstream executor and uses the same ledger/state contracts to periodically replace noisy history with a compressed summary.

```text
RedTeamChallengeHarness
  |-- blue_pipeline(model_fn, strategy, tools, role)
  |-- red_pipeline(model_fn, strategy, tools, role)
  |-- RedTeamChallengeState
  |     |-- master_ledger
  |     |-- blue_context_view
  |     `-- red_context_view
  `-- StoppingConditionEvaluator
        `-- ResilienceScore(0.0..1.0)

ContextRemoverHarness
  |-- downstream executor / harness
  |-- original_intent_anchor
  |-- raw execution ledger
  `-- purifier model via PromptRegistry("harnesses.context_remover.purify")
        `-- destructive state mutation -> compact baseline context
```

The design intentionally avoids tying the harnesses to one concrete agent implementation. If the agent/strategy/prompt-registry designs are already implemented when this work starts, these harnesses will depend on those classes directly. If not, this PR will add small protocols under `vidbyte/shared/` that let developers pass async model functions and strategy-like objects without pulling in a broader implementation prematurely.

---

## 6. Detailed Design

### 6.1 Shared Harness Execution Types

**File(s):** `vidbyte/shared/harness_execution.py`
**Type:** New file

#### What it does

Defines common ledger, context, artifact, model-call, and downstream-step types used by both harnesses.

#### Interface / API

```python
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

class HarnessRole(str, Enum):
    BLUE = "blue"
    RED = "red"
    JUDGE = "judge"
    PURIFIER = "purifier"
    SYSTEM = "system"

@dataclass(frozen=True, slots=True)
class LedgerEntry:
    role: HarnessRole
    kind: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class FilteredContextView:
    role: HarnessRole
    entries: list[LedgerEntry] = field(default_factory=list)
    redaction_rules: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ArtifactRevision:
    revision: int
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

class ModelFunction(Protocol):
    def __call__(self, prompt: str, *, context: Sequence[LedgerEntry], tools: Sequence[object]) -> Awaitable[str]: ...
```

#### Logic / Algorithm

1. Store model-visible messages as `LedgerEntry` objects.
2. Preserve master ledger ordering exactly as events occur.
3. Build filtered context views by copying only entries allowed for a role.
4. Keep artifact revisions immutable so best-scoring revisions can be returned safely.
5. Use protocols so existing or future `BaseAgent` and `BaseStrategy` objects can adapt without inheritance.

#### Edge Cases & Error Handling

- Empty ledgers are valid at harness start.
- Redaction rules are metadata, not a cryptographic security boundary.
- Large ledger entries may be summarized by `ContextRemoverHarness`, but the red-team master ledger remains unredacted unless the caller explicitly wraps it.

---

### 6.2 Shared Harness Errors

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
**Type:** New file or Modified

#### What it does

Adds typed harness exceptions, including the fatal adversarial success path.

#### Interface / API

```python
class VidbyteSdkError(Exception): ...
class HarnessExecutionError(VidbyteSdkError): ...
class HarnessConfigurationError(VidbyteSdkError): ...
class EvaluationError(HarnessExecutionError): ...

class ExploitSuccessError(HarnessExecutionError):
    def __init__(
        self,
        message: str,
        *,
        payload: str,
        severity: str,
        metadata: Mapping[str, object] | None = None,
    ) -> None: ...
```

#### Logic / Algorithm

1. Reuse the SDK error hierarchy if it exists.
2. Add only missing harness-specific exception classes.
3. Store exploit payload separately from the human-readable message.
4. Keep `__str__` concise and safe by default.

#### Edge Cases & Error Handling

- If `vidbyte/lib/errors/base.py` already exists from another feature branch, implementation should extend it rather than replace it.
- `ExploitSuccessError.payload` intentionally keeps exact payload text for debugging and reproduction.

---

### 6.3 Red-Team Types

**File(s):** `vidbyte/harnesses/red_team/types.py`
**Type:** New file

#### What it does

Defines configuration, state, scoring, attack result, and final result dataclasses for the adversarial harness.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class HarnessPipeline:
    name: str
    model_fn: ModelFunction
    tools: tuple[object, ...] = ()
    strategy: object | None = None
    prompt_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class RedTeamHarnessConfig:
    max_rounds: int = 5
    max_steps: int | None = None
    consecutive_clean_attacks_for_win: int = 3
    fatal_severity_threshold: float = 1.0
    warning_severity_threshold: float = 0.25
    return_best_on_exhaustion: bool = True

@dataclass(frozen=True, slots=True)
class AttackFinding:
    payload: str
    severity: float
    category: str
    description: str
    fatal: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ResilienceScore:
    exploit_severity: float
    defensive_adaptability: float
    equilibrium: float
    consecutive_clean_attacks: int

@dataclass(slots=True)
class RedTeamChallengeState:
    original_prompt: str
    master_ledger: list[LedgerEntry]
    blue_view: FilteredContextView
    red_view: FilteredContextView
    artifacts: list[ArtifactRevision]
    findings: list[AttackFinding]
    scores: list[ResilienceScore]
    round_index: int = 0
    step_index: int = 0

@dataclass(frozen=True, slots=True)
class RedTeamChallengeResult:
    outcome: str
    artifact: ArtifactRevision
    score: ResilienceScore
    rounds: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. `HarnessPipeline` carries the separate blue and red execution dependencies.
2. Config validates positive rounds and clean-attack counts.
3. Severity values are clamped to `0.0..1.0`.
4. State keeps all mutable runtime structures in one object.
5. Final result names the outcome: `defensive_win`, `exhausted`, or a raised `ExploitSuccessError`.

#### Edge Cases & Error Handling

- A missing artifact after blue execution raises `HarnessExecutionError`.
- Invalid severity values from custom red parsers are clamped and recorded in metadata.
- `max_steps` is optional because rounds are the primary budget.

---

### 6.4 Stopping Condition Evaluator

**File(s):** `vidbyte/harnesses/red_team/evaluator.py`
**Type:** New file

#### What it does

Computes resilience equilibrium after every blue/red round and detects fatal thresholds.

#### Interface / API

```python
class StoppingConditionEvaluator:
    def evaluate_round(
        self,
        *,
        state: RedTeamChallengeState,
        latest_artifact: ArtifactRevision,
        latest_findings: Sequence[AttackFinding],
    ) -> ResilienceScore: ...

    def is_fatal(self, finding: AttackFinding, config: RedTeamHarnessConfig) -> bool: ...
```

#### Logic / Algorithm

1. Compute `exploit_severity` as the maximum latest finding severity, or `0.0` when no findings exist.
2. Compute `defensive_adaptability` by comparing unresolved previous findings with latest artifact metadata and patch notes.
3. Compute `equilibrium = clamp(defensive_adaptability * (1.0 - exploit_severity), 0.0, 1.0)`.
4. If no findings meet warning threshold, increment consecutive clean attacks.
5. If any finding meets fatal threshold or has `fatal=True`, mark as fatal.
6. Store score in state.

#### Edge Cases & Error Handling

- If custom artifact metadata cannot be parsed, adaptability falls back to `0.0`.
- Evaluator exceptions are wrapped in `EvaluationError`.
- A perfect score alone is not a defensive win unless clean attack count also satisfies config.

---

### 6.5 Red-Team Challenge Harness

**File(s):** `vidbyte/harnesses/red_team/harness.py`, `vidbyte/harnesses/red_team/__init__.py`
**Type:** New file, New file

#### What it does

Implements the turn-based dual-agent coordinator.

#### Interface / API

```python
class RedTeamChallengeHarness:
    def __init__(
        self,
        *,
        blue_pipeline: HarnessPipeline,
        red_pipeline: HarnessPipeline,
        evaluator: StoppingConditionEvaluator | None = None,
        config: RedTeamHarnessConfig | None = None,
    ) -> None: ...

    async def arun(self, prompt: str, *, initial_artifact: str = "") -> RedTeamChallengeResult: ...
    def run(self, prompt: str, *, initial_artifact: str = "") -> RedTeamChallengeResult: ...
```

#### Logic / Algorithm

1. Validate blue and red pipeline names and model functions.
2. Initialize `RedTeamChallengeState`.
3. Seed the artifact list with `initial_artifact` when provided.
4. For each round:
   1. Build the blue filtered view from artifact state and latest unresolved red findings.
   2. Render or assemble the blue prompt.
   3. Call `blue_pipeline.model_fn(...)`.
   4. Parse the blue output into an `ArtifactRevision`.
   5. Append blue input/output events to the master ledger.
   6. Build the red filtered view from latest artifact and red-visible attack history.
   7. Render or assemble the red prompt.
   8. Call `red_pipeline.model_fn(...)`.
   9. Parse red output into `AttackFinding` objects.
   10. Append red input/output events to the master ledger.
   11. If a fatal finding exists, raise `ExploitSuccessError`.
   12. Evaluate the round and store `ResilienceScore`.
   13. If consecutive clean attacks satisfy config, return defensive win.
5. On exhaustion, return the highest-equilibrium artifact revision.

#### Edge Cases & Error Handling

- `run()` uses `asyncio.run()` and raises a clear error if called inside an active loop.
- Pipeline model failures are stored in the ledger and re-raised as `HarnessExecutionError`.
- Red parser defaults can infer findings from structured JSON or fallback text markers such as `severity`.
- The harness must not swallow `KeyboardInterrupt`, `SystemExit`, or `asyncio.CancelledError`.

---

### 6.6 Context Remover Types

**File(s):** `vidbyte/harnesses/context_remover/types.py`
**Type:** New file

#### What it does

Defines wrapper configuration, purification contracts, state, and results.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class PurificationContract:
    include_core_facts: bool = True
    include_tool_values: bool = True
    include_verified_state_changes: bool = True
    exclude_failed_attempts_unless_relevant: bool = True
    max_summary_chars: int = 8000

@dataclass(frozen=True, slots=True)
class ContextRemoverConfig:
    purify_every_n_steps: int = 3
    prompt_key: str = "harnesses.context_remover.purify"
    retain_last_entries: int = 0
    max_raw_ledger_chars: int = 200_000

@dataclass(slots=True)
class ConditionalHarnessState:
    original_intent: str
    history: list[LedgerEntry] = field(default_factory=list)
    baseline_context: str = ""
    token_offset: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class PurificationResult:
    summary: str
    before_entries: int
    after_entries: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. `ConditionalHarnessState` is the shared mutable state matrix used by the wrapper.
2. `PurificationContract` renders into the target extraction instructions for the purifier prompt.
3. Config validates `purify_every_n_steps > 0`.
4. `max_raw_ledger_chars` protects purifier prompts from unbounded trace size.

#### Edge Cases & Error Handling

- Empty history purification returns a no-op result.
- If retained entries are configured, they remain after the injected summary.
- Token offsets are approximate unless a caller supplies a tokenizer hook later.

---

### 6.7 Context Remover Harness

**File(s):** `vidbyte/harnesses/context_remover/harness.py`, `vidbyte/harnesses/context_remover/__init__.py`
**Type:** New file, New file

#### What it does

Wraps downstream execution and periodically mutates active context state into a compact semantic baseline.

#### Interface / API

```python
class ContextRemoverHarness:
    def __init__(
        self,
        *,
        original_intent: str,
        purifier_model_fn: ModelFunction,
        config: ContextRemoverConfig | None = None,
        contract: PurificationContract | None = None,
        prompt_registry: object | None = None,
    ) -> None: ...

    async def intercept_step(
        self,
        state: ConditionalHarnessState,
        step_fn: Callable[[ConditionalHarnessState], Awaitable[Any]],
    ) -> Any: ...

    async def purify(self, state: ConditionalHarnessState) -> PurificationResult: ...
```

#### Logic / Algorithm

1. Increment an internal downstream step counter for every intercepted step.
2. Let steps `1..N` run normally and append their structured trace to `state.history`.
3. Before step `N + 1`, freeze the current state and call `purify(state)`.
4. `purify()` renders `harnesses.context_remover.purify` with:
   - immutable anchor,
   - raw execution ledger,
   - target extraction contract.
5. Run `purifier_model_fn` with an isolated purifier context.
6. Replace `state.history` with one summary ledger entry plus any configured retained tail entries.
7. Set `state.baseline_context` to the new summary.
8. Recompute `state.token_offset` from retained context length.
9. Unfreeze and execute the pending downstream step.

#### Edge Cases & Error Handling

- Purifier failures raise `HarnessExecutionError` by default; optional fallback-to-raw can be added later.
- The purifier's own raw intermediate trace is not appended to primary history.
- If a downstream step mutates state while purification is running, the harness rejects concurrent calls with a state lock.

---

### 6.8 Prompt Registry Additions

**File(s):** `vidbyte/prompts/translations/harnesses/context_remover.py`, `vidbyte/prompts/builtins/vidbyte_defaults.py`
**Type:** New file, Modified

#### What it does

Adds the default purifier prompt used by `ContextRemoverHarness`.

#### Interface / API

```python
PromptKey("harnesses.context_remover", "purify")
```

Template variables:

```text
{immutable_anchor}
{raw_execution_ledger}
{target_extraction_contract}
{max_summary_chars}
```

#### Logic / Algorithm

1. Register the purifier prompt with default prompt registration.
2. Instruct the model to output only:
   - core semantic facts,
   - definitive tool values used downstream,
   - verified state changes,
   - open blockers or next required actions.
3. Explicitly exclude redundant formatting, failed attempts unless relevant, filler, and unreferenced arrays.

#### Edge Cases & Error Handling

- If `PromptRegistry` is not implemented when this feature starts, add the prompt key as a local template constant and document the deviation before PR creation.
- Prompt output remains plain text in the first implementation; strict JSON can be a later option.

---

### 6.9 Harness Client And Public Exports

**File(s):** `vidbyte/harnesses/client.py`, `vidbyte/harnesses/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified, Modified, Modified

#### What it does

Makes both harnesses discoverable through direct imports and the root SDK namespace.

#### Interface / API

```python
from vidbyte.harnesses.red_team import RedTeamChallengeHarness
from vidbyte.harnesses.context_remover import ContextRemoverHarness

class HarnessClient:
    @property
    def red_team_challenge(self) -> type[RedTeamChallengeHarness]: ...

    @property
    def context_remover(self) -> type[ContextRemoverHarness]: ...
```

#### Logic / Algorithm

1. Preserve `VidbyteSDK().harnesses` construction.
2. Add properties that return classes rather than instantiating configured harnesses.
3. Export all public types with explicit `__all__`.

#### Edge Cases & Error Handling

- Root imports should not initialize provider clients, call networks, or register destructive tools.
- Existing package imports must remain backward-compatible.

---

### 6.10 Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified, Modified

#### What it does

Documents both harnesses and updates SDK structure guidance.

#### Interface / API

```python
blue = HarnessPipeline(name="builder", model_fn=blue_model, tools=(safe_patch_tool,))
red = HarnessPipeline(name="breaker", model_fn=red_model, tools=(fuzzer_tool,))

harness = RedTeamChallengeHarness(blue_pipeline=blue, red_pipeline=red)
result = await harness.arun("Build a validator for uploaded metadata")

context_wrapper = ContextRemoverHarness(
    original_intent="Keep the long-running process focused on the migration.",
    purifier_model_fn=purifier_model,
)
await context_wrapper.intercept_step(state, downstream_step)
```

#### Logic / Algorithm

1. README explains that red-team tools are injected by the developer and may require their own sandbox.
2. README explains that context removal is destructive by design.
3. SDK skill allows these two concrete harness packages after design approval.

#### Edge Cases & Error Handling

- Documentation examples must use fake model functions and placeholder tools.
- Avoid claiming real security assurance beyond configured adversarial coverage.

---

## 7. Data Model Changes

### 7.1 Shared Harness Ledger Types

**Change type:** New

```python
HarnessRole
LedgerEntry
FilteredContextView
ArtifactRevision
ModelFunction
```

**Migration strategy:** N/A - in-memory SDK dataclasses and protocols only.

### 7.2 Red-Team Harness Runtime Types

**Change type:** New

```python
HarnessPipeline
RedTeamHarnessConfig
AttackFinding
ResilienceScore
RedTeamChallengeState
RedTeamChallengeResult
```

**Migration strategy:** N/A - in-memory SDK runtime types only.

### 7.3 Context Remover Runtime Types

**Change type:** New

```python
PurificationContract
ContextRemoverConfig
ConditionalHarnessState
PurificationResult
```

**Migration strategy:** N/A - in-memory SDK runtime types only.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

Python SDK public API additions:

```python
from vidbyte.harnesses.red_team import (
    AttackFinding,
    HarnessPipeline,
    RedTeamChallengeHarness,
    RedTeamChallengeResult,
    RedTeamHarnessConfig,
    ResilienceScore,
    StoppingConditionEvaluator,
)

from vidbyte.harnesses.context_remover import (
    ConditionalHarnessState,
    ContextRemoverConfig,
    ContextRemoverHarness,
    PurificationContract,
    PurificationResult,
)

from vidbyte.lib.errors import ExploitSuccessError
```

Modified SDK client:

```python
sdk = VidbyteSDK()
sdk.harnesses.red_team_challenge
sdk.harnesses.context_remover
```

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/red-team-context-remover-harnesses.md` | Design doc for both requested harnesses |
| MODIFY | `README.md` | Document red-team and context-remover harness usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update SDK structure guidance for approved harness packages |
| MODIFY | `vidbyte/__init__.py` | Export public harness and error types where appropriate |
| MODIFY | `vidbyte/harnesses/__init__.py` | Export red-team and context-remover harness packages |
| MODIFY | `vidbyte/harnesses/client.py` | Add discoverability properties for both harnesses |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export harness error types |
| CREATE | `vidbyte/lib/errors/base.py` | SDK exception hierarchy if not already present |
| CREATE | `vidbyte/shared/harness_execution.py` | Shared ledger, context view, artifact, and model function types |
| CREATE | `vidbyte/harnesses/red_team/__init__.py` | Red-team harness exports |
| CREATE | `vidbyte/harnesses/red_team/types.py` | Red-team config, state, scoring, and result dataclasses |
| CREATE | `vidbyte/harnesses/red_team/evaluator.py` | `StoppingConditionEvaluator` and resilience scoring |
| CREATE | `vidbyte/harnesses/red_team/harness.py` | `RedTeamChallengeHarness` coordinator |
| CREATE | `vidbyte/harnesses/context_remover/__init__.py` | Context-remover harness exports |
| CREATE | `vidbyte/harnesses/context_remover/types.py` | Purification config, contract, state, and result dataclasses |
| CREATE | `vidbyte/harnesses/context_remover/harness.py` | `ContextRemoverHarness` wrapper and state mutation logic |
| CREATE | `vidbyte/prompts/translations/harnesses/context_remover.py` | Default purifier prompt translation |
| MODIFY | `vidbyte/prompts/builtins/vidbyte_defaults.py` | Register context-remover purifier prompt if prompt registry exists |
| CREATE | `tests/test_red_team_harness.py` | Unit tests for turn order, scoring, fatal exploit, defensive win, exhaustion |
| CREATE | `tests/test_context_remover_harness.py` | Unit tests for step interception, purification, destructive state mutation, isolated purifier trace |

Summary: 13 files created, 7 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_red_team_harness.py` -> `test_alternates_blue_then_red_each_round`
- `tests/test_red_team_harness.py` -> `test_blue_receives_latest_artifact_and_previous_finding_summary`
- `tests/test_red_team_harness.py` -> `test_red_receives_latest_artifact_without_private_blue_context`
- `tests/test_red_team_harness.py` -> `test_evaluator_computes_equilibrium_from_severity_and_adaptability`
- `tests/test_red_team_harness.py` -> `test_consecutive_clean_attacks_returns_defensive_win`
- `tests/test_red_team_harness.py` -> `test_fatal_violation_raises_exploit_success_error_with_payload`
- `tests/test_red_team_harness.py` -> `test_exhaustion_returns_highest_scoring_artifact`
- `tests/test_red_team_harness.py` -> `test_pipeline_failure_is_wrapped_as_harness_execution_error`
- `tests/test_context_remover_harness.py` -> `test_allows_n_steps_before_purification`
- `tests/test_context_remover_harness.py` -> `test_purifies_before_n_plus_one_step`
- `tests/test_context_remover_harness.py` -> `test_purifier_receives_anchor_raw_ledger_and_contract`
- `tests/test_context_remover_harness.py` -> `test_purification_replaces_history_with_summary`
- `tests/test_context_remover_harness.py` -> `test_retains_configured_tail_entries`
- `tests/test_context_remover_harness.py` -> `test_purifier_trace_is_not_appended_to_primary_history`
- `tests/test_context_remover_harness.py` -> `test_rejects_concurrent_intercept_step_calls`

### Integration Tests

- Use fake async model functions for blue, red, judge, and purifier.
- Use simple object placeholders for tools; no live `ToolExecutor` or provider calls are required.
- If `PromptRegistry` exists in the implementation branch, verify `ContextRemoverHarness` can retrieve and render `harnesses.context_remover.purify`.
- If `BaseAgent` and `BaseStrategy` exist in the implementation branch, add compatibility tests showing `HarnessPipeline` can wrap or adapt them.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte`.
2. Run `python -m unittest discover -s tests`.
3. Run a fake red-team harness where red returns no findings for three consecutive rounds and confirm `outcome == "defensive_win"`.
4. Run a fake red-team harness where red returns `fatal=True` and confirm `ExploitSuccessError.payload` matches the exact test payload.
5. Run a fake context remover with `purify_every_n_steps=3`, execute four intercepted steps, and confirm purification happened exactly once before step four.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | Dataclasses, protocols, asyncio, enum, unittest | Requires small local protocols instead of relying on third-party orchestration libraries |

No package dependencies or external services are added.

---

## 12. Rollout & Deployment

- This is a package-only SDK change; no deployed service is updated.
- Implementation must happen in an isolated feature worktree after explicit design approval.
- This feature is additive for the current scaffold.
- Rollout sequence:
  1. Commit this design doc first in the feature branch.
  2. Add or extend shared harness errors.
  3. Add shared ledger/context/artifact protocols.
  4. Implement red-team types, evaluator, and harness coordinator.
  5. Implement context-remover types and wrapper.
  6. Add purifier prompt translation or local prompt fallback.
  7. Wire public exports and `HarnessClient` properties.
  8. Add unit tests and docs.
- Rollback is reverting the feature branch merge commit.
- If prior agent/tool/prompt/strategy PRs land first, reuse their concrete contracts and record any deviations from this design before PR creation.

---

## 13. Open Questions

- [ ] Should `RedTeamChallengeHarness` require structured JSON outputs from blue and red pipelines, or should the first implementation support permissive text parsing for easier fake/model use?
- [ ] Should fatal exploit threshold default to `1.0`, or should categories such as `security` always be fatal regardless of numeric severity?
- [ ] Should the master ledger in `RedTeamChallengeHarness` be eligible for context removal when wrapped by `ContextRemoverHarness`, or should adversarial transcripts stay unredacted by default for auditability?
- [ ] Should `ContextRemoverHarness` return plain-text summaries initially, or require a structured JSON schema for downstream reliability?
- [ ] Should token offset recalibration use approximate character counts in the first PR, or wait for a tokenizer abstraction?
- [ ] Should the purifier prompt live in the prompt registry immediately, or temporarily in the context-remover package until the prompt-registry PR lands?

---

## 14. Alternatives Considered

### Alternative 1: Implement red-team simulation as one `run_iteration()` override

- What: Keep the existing/simple harness pattern and let one method perform both build and attack behavior.
- Why rejected: The user explicitly requires a core architecture split with two distinct sub-execution pipelines and turn-based coordination. One method would blur state boundaries and make filtered context views harder to enforce.

### Alternative 2: Model blue and red as ordinary tools

- What: Treat the attacker and defender as tools invoked by a single agent strategy.
- Why rejected: The two roles need separate model functions, prompts, tools, strategies, and context filters. A tool abstraction is too narrow for that lifecycle.

### Alternative 3: Make `ContextRemoverHarness` a compaction tool only

- What: Implement purification as another tool that a strategy may call when it wants.
- Why rejected: The requested behavior is an outer-level meta-harness that intercepts standard execution calls and enforces purification by counter, independent of whether inner strategies remember to clean context.

### Alternative 4: Physically delete the master ledger during purification

- What: Replace every trace, including audit history, with the purified summary.
- Why rejected: `ContextRemoverHarness` should destructively mutate the active state matrix, but red-team audit trails and external callers may still need an unredacted ledger depending on configuration. The first implementation purges active `ConditionalHarnessState.history`; broader persistence policy remains caller-owned.

### Alternative 5: Add real fuzzers and vulnerability scanners in the first PR

- What: Ship concrete destructive or diagnostic tools with the red-team harness.
- Why rejected: Tool safety, sandboxing, and permissions need their own boundary. This harness should orchestrate developer-injected tools and findings first, then later plug into approved scanner/fuzzer tools.

---

END OF DESIGN DOC
