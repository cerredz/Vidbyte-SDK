# Design Doc: Codex Failure Vocabulary and Model Fallback

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

When a Codex turn fails, the adapter raises a `CodexAgentError` carrying one of eight `codex.*` failure codes and nothing else — no phase, no severity, no statement of whether retrying could help. The SDK meanwhile has a complete canonical failure vocabulary (`Failure`, with phase/status/disposition/severity and credential-safe details) and an ordered model-fallback chain (`AgentFallbackSettings` / `AgentFallback`), and a Codex agent participates in neither. This change translates Codex failures into canonical `Failure` records with an explicit retryability classification, then uses that classification to drive a model fallback chain at the turn boundary. The two ship together because a fallback that cannot tell a rate limit from a bad sandbox setting will retry the unretryable and burn a second turn to fail identically.

---

## 2. Goals & Non-Goals

### Goals

- Translate every `CodexAgentError` into a canonical `Failure` with a correct `FailurePhase`, `FailureSeverity`, `FailureDisposition`, and `FailureStatus`.
- Classify each of the eight `codex.*` codes as retryable-on-another-model, retryable-as-is, or terminal, and expose that as data rather than as scattered conditionals.
- Expose the turn's failure records on the agent and on `AgentMessage.metadata`, so a caller can read what went wrong without catching and re-parsing an exception.
- Accept `AgentFallbackSettings` on `CodexHarnessAgentSettings` and reuse `AgentFallback.is_model_error()` / `.advance()` unchanged for the switch decision.
- Reject at construction any chain entry naming a provider a Codex thread cannot reach, and any chain with no primary model to fall back from.
- Attempt a fallback only at a turn boundary, never mid-turn, and record which model actually answered.

### Non-Goals

- Wiring `FailureRouter` and its recovery handlers. `FailureRouter.__init__` binds to a `Session`, and Codex session support is still an open PR (#417). This change produces the `Failure` records a router would consume; binding the router follows once sessions land.
- `Session` failure capture. Same reason.
- Cross-provider fallback. A Codex thread is a Codex thread; a chain entry naming `anthropic` cannot be honored, because switching provider mid-conversation is not a model swap but a different agent with no access to the history.
- Retrying a turn on the *same* model. `AgentFallback.advance` moves to the next chain index; a same-model retry is a different feature (roadmap B04) that must first solve whether the previous turn's side effects happened.
- Contract-driven fallback. Whether an unmet `OutputContract` should trigger a model switch is PR 2's question, and it needs the contract evaluation this PR does not add.

---

## 3. Background & Context

`CodexAgentError` (`vidbyte/lib/errors/base.py:129`) already carries the eight-field `DIAGNOSTIC_FIELDS` packet A003 requires, plus `failure_code` and `operation`. Its `failure_code` values are real members of the shared `FailureCode` enum (`vidbyte/lib/enums/failure.py:35-42`), so a Codex code is already a legal `Failure.code` — `Failure.__post_init__` resolves it through `FailureCode.from_value` without complaint.

What is missing is every other classification dimension. `Failure` carries `phase` (configuration, input, model, tool, output, session, resource…), `status` (observed, recovering, recovered, exhausted, terminal), `disposition` (record, continue, route, stop, raise), and `severity`. All four default, so a Codex failure recorded today would claim `FailurePhase.RUNTIME` and `FailureDisposition.RECORD` regardless of whether it was a bad config or a lost connection. `FailureSafety.sanitize_mapping` also exists to bound and redact detail mappings, and the adapter currently produces no details at all beyond `operation` and `error_type`.

On the fallback side, `AgentFallbackSettings` (`vidbyte/agents/settings/fallback.py:34`) takes `models: Sequence[str | FallbackModel]`, `fallback_on: tuple[type[BaseException], ...] | None`, and `enabled`, validates entries, and exposes `resolved_models(primary=...)` and `to_fallback(primary=...)`. `AgentFallback` (`vidbyte/agents/fallback.py:57`) holds the resolved chain and offers exactly two decision methods:

```python
def is_model_error(self, error: BaseException) -> bool:
    return isinstance(error, self.fallback_on)

def advance(self, error: BaseException, index: int) -> int | None:
    if not self.is_model_error(error) or index + 1 >= len(self.models):
        ...
```

Neither touches a runner or a provider client, so **both are reusable by this adapter unchanged**. Only `AgentFallback.from_spec` is coupled to the direct runtime: it derives chain index 0 from an `AgentRunnerConfig`, which a Codex agent does not have. This design therefore supplies the primary `FallbackModel` itself from `CodexAgentSettings` and calls `AgentFallbackSettings.to_fallback(primary=...)`, which is the seam that already exists for exactly this.

Two field-guide constraints bind this work. *Fallback Coordination → "Keep fallback policy state and decisions behind `AgentFallback`"* (PR #345) says the policy decision must not become a pile of methods on the caller — satisfied by reusing `is_model_error`/`advance`. *Fallback Coordination → "Put fallback validation in shared contracts"* (PR #339) says validation belongs in the shared dataclasses, and attempt records must stay credential-free and share one shape — which is why `CodexFallbackAttempt` records a provider and model name and never an `api_key`.

A third constraint comes from *Class-Bound Helpers → "Audit every surface of a shared abstraction before calling its translation complete"* (PR #412). §5 carries that audit for `AgentFallbackSettings`.

The roadmap tracks this as **B03** ("Expand failure classification") and **B05** ("Translate fallback policies"), whose completion criterion is that recovery reconciles native state before retry and a timeout cannot silently duplicate a side effect.

---

## 4. Requirements

### Functional Requirements

1. A new `CodexFailureTranslator` converts a `CodexAgentError` into a `Failure` whose `code` is the error's `failure_code`, `source` names the Codex adapter, and whose `phase`, `severity`, and `disposition` come from a per-code classification table.
2. The classification table covers all eight existing `codex.*` codes and maps each to exactly one `CodexFailureClass`: `MODEL_RETRYABLE`, `TRANSIENT`, or `TERMINAL`.
3. `codex.sdk_unavailable`, `codex.vidbyte_translation_failed`, and `codex.content_translation_failed` classify as `TERMINAL` with `FailurePhase.CONFIGURATION` or `INPUT`: a different model cannot fix a missing extra or an invalid setting.
4. `codex.turn_failed` and `codex.thread_start_failed` classify as `MODEL_RETRYABLE` with `FailurePhase.MODEL`, because a different model or a fresh thread can survive them.
5. `codex.thread_resume_failed`, `codex.fork_failed`, and `codex.response_invalid` classify as `TRANSIENT` with their own phases: retrying the same operation may work, but switching model will not.
6. `Failure.details` is built through `FailureSafety.sanitize_mapping`, so no credential-shaped key can reach a failure record.
7. An unrecognized `codex.*` code — one added later without a table entry — classifies as `TERMINAL` with `FailureSeverity.CRITICAL` and a detail naming the missing entry, rather than defaulting to retryable.
8. `CodexHarnessAgent` exposes `failures` returning the immutable tuple of `Failure` records observed during the current or most recent turn.
9. The failure ledger is reset at the start of each turn, matching the `UsageTracker` lifecycle already merged in PR #413.
10. `CodexHarnessAgentSettings` accepts `fallback: AgentFallbackSettings | None`, defaulting to `None`.
11. Construction raises `ConfigurationError` when a fallback chain is declared but neither `turn.model` nor `thread.model` names a primary model, because a chain needs a model to fall back from.
12. Construction raises `ConfigurationError` naming the offending entry when a chain entry's provider differs from the thread's effective provider — `openai` when `thread.model_provider` is empty, otherwise that value.
13. The switch decision delegates to `AgentFallback.is_model_error(error)` and `AgentFallback.advance(error, index)`; this adapter adds no second copy of that policy.
14. A fallback attempt runs a **new native turn** with `turn.model` replaced by the next chain entry's model, on the same thread, and never interrupts an in-flight turn.
15. A fallback attempt is made only when the failure classifies as `MODEL_RETRYABLE` **and** `AgentFallback.is_model_error` accepts the exception, so both the Vidbyte trigger filter and the Codex classification must agree.
16. Attempts are bounded by the chain length; an exhausted chain re-raises the **last** error, and the reply metadata is not produced at all.
17. On success after one or more fallbacks, `AgentMessage.metadata` records the answering model, the attempt count, and one credential-free `CodexFallbackAttempt` record per attempt.
18. An agent with `fallback=None` performs exactly one turn and behaves identically to before this change.

### Non-Functional Requirements

- **Performance:** classification is a dict lookup. A fallback attempt costs a full extra Codex turn, which is why requirement 15 requires two independent conditions to agree before spending one.
- **Scalability:** the failure ledger is reset per turn and bounded by attempts-per-turn, so it cannot grow across a long-lived thread.
- **Security:** every detail mapping passes through `FailureSafety.sanitize_mapping`, and `CodexFallbackAttempt` records provider and model names only — never `FallbackModel.api_key`.
- **Observability:** this change is the observability work for failures. A caller can read `agent.failures` and `metadata["failures"]` instead of catching an exception and re-deriving its meaning.
- **Reliability:** a fallback attempt is a new turn on the same thread, so the previous failed attempt's side effects are **not** undone. §13 records that limit as an open question rather than implying rollback.

---

## 5. High-Level Design

Two collaborators, in dependency order, plus two settings fields.

**`CodexFailureTranslator`** (`vidbyte/agents/codex/failures.py`) owns the classification. It is a table plus three small readers, not a chain of conditionals: `CODEX_FAILURE_CLASSIFICATION` in the constants module maps each `codex.*` code to a `(CodexFailureClass, FailurePhase, FailureSeverity, FailureDisposition)` tuple, and the translator looks the code up and builds the `Failure`. Keeping it as data means adding a ninth failure code is one table row, and an omission is detectable — requirement 7 turns a missing row into a loud `TERMINAL/CRITICAL` classification rather than a silent default.

**`CodexFallbackCoordinator`** (`vidbyte/agents/codex/fallback.py`) owns the chain walk. It holds the `AgentFallback` built from the caller's settings and the Codex primary, asks it whether to advance, and produces the per-attempt `CodexTurnSettings` override. It does not decide *whether* an error is a model error — `AgentFallback.is_model_error` does — and it does not decide *whether* the code is retryable — the failure translator does. Both must agree, which is the design's central rule: the Vidbyte-side exception filter and the Codex-side code classification are independent judgments, and spending a whole extra turn requires both.

The **primary model** question is the one genuine design decision. `AgentFallback.from_spec` derives chain index 0 from `AgentRunnerConfig.provider` / `.model_name`, which a Codex agent has neither of. The Codex equivalents are `turn.model or thread.model` for the model, and `thread.model_provider or "openai"` for the provider — the same provider resolution PR #413 already settled for the usage record, reused here so the two cannot disagree. When neither layer names a model there is nothing to fall back *from*, and requirement 11 rejects that at construction rather than at the first failure.

```
CodexHarnessAgent.arun()
   |
   |-- self._failures.reset()          <- per-turn, mirrors the merged UsageTracker
   v
attempt loop (bounded by chain length)
   |
   |-- CodexTransport.run(settings with turn.model = chain[index].model)
   |        |
   |        | success -> record answering model + attempts -> AgentMessage
   |        |
   |        | CodexAgentError
   |        v
   |   CodexFailureTranslator.translate(error) -> Failure(+ CodexFailureClass)
   |        |
   |        |-- record into the turn's failure ledger
   |        v
   |   class is MODEL_RETRYABLE  AND  AgentFallback.is_model_error(error)?
   |        |                                    |
   |        | no -> re-raise                     | yes
   |        v                                    v
   |     (terminal)              AgentFallback.advance(error, index)
   |                                     |            |
   |                                     | None       | next index
   |                                     v            v
   |                            re-raise last     loop again (new native turn)
```

---

## 6. Detailed Design

### 6.1 Failure classification table

**File(s):** `vidbyte/lib/constants/codex.py`, `vidbyte/lib/enums/codex.py`
**Type:** Modified

#### What it does

Holds the per-code classification as data, so the supported vocabulary is inspectable in one place.

#### Interface / API

```python
class CodexFailureClass(str, Enum):
    """Whether a Codex failure can be survived, and by what kind of retry."""

    MODEL_RETRYABLE = "model_retryable"
    TRANSIENT = "transient"
    TERMINAL = "terminal"
```

```python
CODEX_FAILURE_CLASSIFICATION: Mapping[str, CodexFailureRule] = {...}
CODEX_FAILURE_SOURCE = "codex_harness_agent"
```

`CodexFailureRule` is a frozen slots dataclass holding `failure_class`, `phase`, `severity`, and `disposition`.

#### Logic / Algorithm

1. One row per `codex.*` code, keyed by the enum member's `.value`.
2. `codex.sdk_unavailable` → TERMINAL / CONFIGURATION / CRITICAL / RAISE.
3. `codex.vidbyte_translation_failed` and `codex.content_translation_failed` → TERMINAL / INPUT / ERROR / RAISE.
4. `codex.turn_failed` and `codex.thread_start_failed` → MODEL_RETRYABLE / MODEL / ERROR / ROUTE.
5. `codex.thread_resume_failed` → TRANSIENT / SESSION / ERROR / ROUTE.
6. `codex.fork_failed` → TRANSIENT / RESOURCE / ERROR / ROUTE.
7. `codex.response_invalid` → TRANSIENT / OUTPUT / ERROR / ROUTE.

#### Edge Cases & Error Handling

- **A code with no row.** Requirement 7: the translator returns TERMINAL / RUNTIME / CRITICAL and a detail naming the code. Defaulting to retryable would make an unclassified failure spend the whole chain.

### 6.2 CodexFailureTranslator

**File(s):** `vidbyte/agents/codex/failures.py`
**Type:** New file

#### What it does

Converts one `CodexAgentError` into a canonical `Failure` plus its retry class, and holds the per-turn ledger.

#### Interface / API

```python
class CodexFailureTranslator:
    """Converts Codex adapter errors into canonical Vidbyte failure records."""

    @classmethod
    def translate(cls, request: CodexFailureTranslationRequest) -> CodexFailureRecord: ...

    @staticmethod
    def _rule(code: str) -> CodexFailureRule: ...

    @staticmethod
    def _details(error: CodexAgentError, attempt: int) -> Mapping[str, Any]: ...


class CodexFailureLedger:
    """Bounded per-turn record of the failures one agent observed."""

    def reset(self) -> None: ...
    def record(self, record: CodexFailureRecord) -> CodexFailureRecord: ...
    @property
    def failures(self) -> tuple[Failure, ...]: ...
    @property
    def records(self) -> tuple[CodexFailureRecord, ...]: ...
```

`CodexFailureRecord` is a frozen slots dataclass pairing the `Failure` with its `CodexFailureClass`.

#### Logic / Algorithm

1. `translate` reads the error's `failure_code`, looks up the rule, and builds `Failure(code=..., source=CODEX_FAILURE_SOURCE, phase=..., severity=..., disposition=..., summary=str(error), details=...)`.
2. `_details` assembles `operation`, `error_type`, `attempt`, and `chain_index`, then passes the mapping through `FailureSafety.sanitize_mapping`.
3. The ledger appends and bounds by `CODEX_MAX_TURN_FAILURES`, keeping the most recent.

#### Edge Cases & Error Handling

- **`Failure.__post_init__` rejects the code.** Cannot happen for the eight members, but a future non-enum string would raise `ValueError`; the translator lets that propagate because a failure record that cannot be constructed is a programming error in the table, not a runtime condition to swallow.
- **A non-`CodexAgentError` exception.** Not translated. Only the adapter's own classified errors have a `failure_code`; anything else propagates untouched, because inventing a classification for an arbitrary exception is exactly the dishonesty this design avoids.

### 6.3 CodexFallbackCoordinator

**File(s):** `vidbyte/agents/codex/fallback.py`
**Type:** New file

#### What it does

Resolves the chain, asks `AgentFallback` whether to advance, and produces each attempt's settings override.

#### Interface / API

```python
class CodexFallbackCoordinator:
    """Walks a Vidbyte fallback chain across Codex turn boundaries."""

    def __init__(self, chain: AgentFallback | None) -> None: ...

    @classmethod
    def build(cls, settings: CodexHarnessAgentSettings) -> CodexFallbackCoordinator: ...

    @property
    def enabled(self) -> bool: ...

    def next_index(self, request: CodexFallbackDecision) -> int | None: ...
    def settings_for(self, codex: CodexAgentSettings, index: int) -> CodexAgentSettings: ...
    def attempt(self, index: int, error: BaseException | None) -> CodexFallbackAttempt: ...

    @staticmethod
    def primary_model(codex: CodexAgentSettings) -> FallbackModel: ...
```

#### Logic / Algorithm

`build`:
1. Return a disabled coordinator when `settings.fallback` is `None`.
2. Derive the primary through `primary_model`, which raises when no model is named at either layer.
3. Call `settings.fallback.to_fallback(primary=primary)`, reusing the shared conversion.
4. Validate every resolved entry's provider against the primary's, raising on the first mismatch.

`next_index` requires both conditions from requirement 15: the record's class is `MODEL_RETRYABLE`, and `AgentFallback.advance(error, index)` returns an index.

`settings_for` returns `replace(codex, turn=replace(codex.turn, model=chain[index].model))` — only the turn model changes, because the thread is already open and its model was fixed at start.

#### Edge Cases & Error Handling

- **A chain entry naming another provider.** Rejected at `build`, naming the entry's index and provider. Honoring it would mean resuming a Codex thread on a provider that has never seen it.
- **`temperature` on a chain entry.** Codex exposes no temperature control, so a chain entry setting one is accepted and its temperature ignored; the design records this in §13 rather than rejecting an otherwise-valid chain over a field Codex simply lacks.
- **Chain of length one.** `resolved_models` always prepends the primary, so a single-entry chain yields two models and one possible fallback.

### 6.4 Agent wiring

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### Interface / API

```python
class CodexHarnessAgent:
    @property
    def failures(self) -> tuple[Failure, ...]: ...
```

#### Logic / Algorithm

1. `__init__` builds `self._failures = CodexFailureLedger()` and `self._fallback = CodexFallbackCoordinator.build(self.settings)`.
2. `arun` resets the ledger where the merged `self._usage.reset()` already sits, then enters `_attempt_turn`.
3. `_attempt_turn` loops: run the transport with `settings_for(index)`, and on `CodexAgentError` translate, record, ask `next_index`, and either advance or re-raise.
4. On success it records the answering model and attempts for the result translator.

#### Edge Cases & Error Handling

- **Cancellation.** `asyncio.CancelledError` is a `BaseException`, not a `CodexAgentError`, so it is never translated, never triggers a fallback, and propagates unchanged. The S019 lint rule enforces that.
- **Usage across attempts.** The merged `UsageTracker` reset happens once per `arun`, before the attempt loop, and each attempt's usage is recorded when it succeeds. A failed attempt reports no usage because `usage_available` is false on a raised turn — so the rollup describes the successful attempt, not the sum. §13 records that.

### 6.5 Result metadata

**File(s):** `vidbyte/agents/codex/result.py`
**Type:** Modified

#### Logic / Algorithm

1. Add `failures`, `fallback_attempts`, and `answering_model` to `CodexResultTranslationRequest`.
2. Publish each under its own constant key, omitting a key entirely when there is nothing to report so absent stays distinct from empty.

---

## 7. Data Model Changes

N/A - no persisted records, no database, no migration. Five in-memory dataclasses are added (`CodexFailureRule`, `CodexFailureRecord`, `CodexFailureTranslationRequest`, `CodexFallbackDecision`, `CodexFallbackAttempt`) and two fields are added to existing records. Nothing is serialized; PR #417's checkpoint work does not carry any of them.

---

## 8. API Changes

N/A - no HTTP endpoints. The public Python surface gains one settings field, one agent property, one enum, and three metadata keys, all additive.

---

## 9. Abstraction Surface Audit

Required by the field guide's *audit every surface* entry. `AgentFallbackSettings` has three constructor fields and two public methods:

| Surface | Disposition |
|---|---|
| `models` | **Translated** — through `resolved_models`/`to_fallback`, with a provider gate |
| `fallback_on` | **Translated** — passed to `AgentFallback`, whose `is_model_error` this adapter calls |
| `enabled` | **Translated** — `to_fallback` returns `None` when false, yielding a disabled coordinator |
| `resolved_models(primary=)` | Not a translation — a query, called by `to_fallback` |
| `to_fallback(primary=)` | Not a translation — the conversion this adapter reuses rather than reimplements |

`FallbackModel` has four fields: `provider` (**translated** — gated), `model` (**translated** — becomes `turn.model`), `api_key` (**deliberately dropped** — Codex authenticates through its own client config and CLI login, and copying a key into a turn override would be both ineffective and a credential-handling risk), `temperature` (**genuinely dropped** — Codex exposes no temperature control; recorded in §13).

`Failure` has fifteen fields. Translated: `code`, `source`, `phase`, `status`, `disposition`, `severity`, `summary`, `details`. Left at defaults with a reason: `handled_by` and `parent_id` belong to a `FailureRouter` this PR does not bind; `iteration` is unavailable because Codex owns its iterations; `step` has no Codex counterpart; `id` and `occurred_at` are generated.

---

## 10. Testing Plan

All tests run offline against a fake transport. `openai-codex` is never imported: the failure translation and the fallback decision both run before and after the transport call.

### Unit Tests

- `CodexFailureTranslator` -> `classifies every codex code in the enum` — [Hidden Assumption] — iterates the `FailureCode` members whose value starts with `codex.` and asserts each has a table row, so adding a ninth code without a row fails this test rather than silently classifying as terminal at runtime.
- `CodexFailureTranslator` -> `classifies an unknown codex code as terminal and critical` — [Hidden Failure] — the inverse guard: an unrecognized code must not default to retryable, or one omission spends the whole chain on every failure.
- `CodexFailureTranslator` -> `sets the phase from the table, not the Failure default` — [Silent Failure] — a translator that built `Failure` without a phase would report `RUNTIME` for a configuration error and look plausible.
- `CodexFailureTranslator` -> `redacts a credential-shaped detail key` — [Hidden Assumption] — asserts a detail named `api_key_hint` does not survive; `FailureSafety` owns the rule but nothing proves the translator routes through it.
- `CodexFailureTranslator` -> `carries the operation and error_type into details` — [Silent Failure]
- `CodexFailureTranslator` -> `carries the attempt and chain index into details` — [Silent Failure] — without these a three-attempt failure looks like three unrelated failures.
- `CodexFailureLedger` -> `resets between turns` — [Edge Case]
- `CodexFailureLedger` -> `bounds retained failures` — [Edge Case] — records more than the cap and asserts the most recent are kept.
- `CodexFallbackCoordinator.build` -> `is disabled for fallback=None` — [Edge Case]
- `CodexFallbackCoordinator.build` -> `is disabled for enabled=False settings` — [Edge Case]
- `CodexFallbackCoordinator.build` -> `raises when no model is named at either layer` — [Hidden Assumption] — a chain with nothing to fall back from must fail at construction, not at the first failure.
- `CodexFallbackCoordinator.build` -> `raises naming the entry whose provider differs` — [Hidden Failure] — the headline rejection: honoring an `anthropic` entry would resume a Codex thread on a provider that never saw it.
- `CodexFallbackCoordinator.build` -> `accepts an entry whose provider matches a custom thread model_provider` — [Edge Case] — proves the gate compares against the effective provider, not a hardcoded `openai`.
- `CodexFallbackCoordinator.primary_model` -> `prefers the turn model over the thread model` — [Silent Failure]
- `CodexFallbackCoordinator.next_index` -> `returns None for a TERMINAL classification even when is_model_error accepts` — [Hidden Failure] — requirement 15's first half; without it a config error spends the chain.
- `CodexFallbackCoordinator.next_index` -> `returns None when is_model_error rejects even for MODEL_RETRYABLE` — [Hidden Failure] — requirement 15's second half; without it the caller's `fallback_on` filter is ignored.
- `CodexFallbackCoordinator.next_index` -> `returns None at the end of the chain` — [Edge Case]
- `CodexFallbackCoordinator.settings_for` -> `replaces only the turn model` — [Silent Failure] — asserts sandbox, approval mode, and thread settings are untouched; a fallback that silently widened the sandbox would be a security regression.
- `CodexFallbackAttempt` -> `never carries an api key` — [Hidden Assumption] — asserts the record's fields, since the field guide requires credential-free attempt records.

### Integration Tests

The flow to prove is a real `arun` walking the chain. Only `CodexTransport` is faked; the real `AgentFallbackSettings`, the real `AgentFallback`, and the real translator all run, because the defect this guards against — the two conditions disagreeing, or a retry on the wrong error — only appears wired together.

- A transport failing once with `codex.turn_failed` then succeeding returns the reply, and `metadata["answering_model"]` is the second chain entry. [Silent Failure] — a caller reading a fallback result as a first-attempt result is the whole reason this key exists.
- The same scenario records two `CodexFallbackAttempt` entries and `metadata["fallback_attempts"] == 2`. [Silent Failure]
- A transport failing with `codex.sdk_unavailable` re-raises immediately and the transport is called exactly **once**. [Hidden Failure] — proves a terminal classification does not spend a second turn.
- A transport failing every attempt re-raises the **last** error, and the transport is called exactly `len(chain)` times. [Edge Case]
- A `CancelledError` from the transport propagates unchanged and triggers no fallback attempt. [Hidden Failure] — a cancelled turn retried on another model would run work the caller explicitly cancelled.
- `agent.failures` after a recovered turn holds one `Failure` for the failed attempt, with `phase == MODEL`. [Silent Failure] — proves a recovered failure is still recorded rather than discarded on success.
- An agent with `fallback=None` calls the transport once and its reply metadata carries none of the three new keys. [Hidden Assumption] — the no-fallback path must be untouched.
- Each attempt's transport request carries the chain entry's model in `settings.turn.model`. [Silent Failure] — proves the override actually reaches the provider rather than being computed and dropped.

### Manual / QA Test Cases

1. Given a Codex agent with `fallback=AgentFallbackSettings(models=["gpt-5-codex-mini"])` and a primary that rate-limits, when a turn runs, then the reply arrives from the second model and `metadata["answering_model"]` says so. — [Silent Failure]
2. Given a Codex agent with a fallback chain and no `openai-codex` installed, when a turn runs, then it fails once with `codex.sdk_unavailable` and does not attempt the rest of the chain. — [Hidden Failure]
3. Given a chain entry `FallbackModel(provider="anthropic", model="claude-opus-5")`, when the agent is constructed, then construction fails naming that entry's provider. — [Hidden Assumption]
4. Given a recovered turn, when `agent.failures` is read, then the failed attempt is still listed with its phase and sanitized details. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Each attempt is a native turn | A fallback attempt costs real tokens; requirement 15 gates it behind two agreeing conditions |
| Existing `AgentFallback` | in-repo | The switch decision, reused unchanged | None — no signature change |

No dependency additions.

---

## 12. Rollout & Deployment

No feature flag. The default is `fallback=None`, so an existing agent performs one turn and behaves identically; the failure ledger is additive and the three metadata keys are omitted when empty.

This branches from `origin/main` at `6b7d848d`, which includes the merged usage tracking (#413) but not the still-open #412, #414, #415, or #417. It is PR 1 of three and should merge first: PR 2 (output contracts) reads the failure classification this PR adds.

Rollback is a revert of this branch. No persisted state is written, so nothing survives a revert.

---

## 13. Open Questions

- [ ] A fallback attempt is a new turn on the same thread, so the failed attempt's file edits are **not** undone. Should a Codex fallback optionally fork the thread first (roadmap F04) so each attempt starts from the same conversation state? That composes native forking with fallback and needs its own design.
- [ ] The merged `UsageTracker` reset happens once per `arun`, so a recovered turn's rollup describes the successful attempt only. Should failed attempts' usage be recorded too, given `usage_available` is false on a raised turn and the tokens were nonetheless spent?
- [ ] `FallbackModel.temperature` has no Codex counterpart and is ignored. Should a chain entry setting it be rejected instead, at the cost of failing an otherwise-valid chain over a field Codex simply lacks?
- [ ] Binding `FailureRouter` and its recovery handlers needs Session support (#417). Once that lands, should the Codex ledger feed the router, or should the router replace the ledger entirely?

---

## 14. Alternatives Considered

### Alternative 1: Reimplement the switch decision in the Codex package

- What: A Codex-local `should_fallback` walking the chain itself.
- Why rejected: `AgentFallback.is_model_error` and `.advance` take no runner and no provider client, so they already work here. The field guide's *Fallback Coordination* entry exists precisely because that policy must not be duplicated per caller; a second copy is a second behavior that drifts.

### Alternative 2: Use `AgentFallback.from_spec`

- What: Call the existing constructor helper instead of deriving the primary here.
- Why rejected: `from_spec` requires an `AgentRunnerConfig` and calls `_primary_model` on it, and a Codex agent has no runner config. `AgentFallbackSettings.to_fallback(primary=...)` is the seam that already exists for a caller who knows its own primary, which is exactly this case.

### Alternative 3: Classify retryability from the exception type instead of the failure code

- What: Rely only on `AgentFallback.is_model_error`, since every adapter failure is a `CodexAgentError`.
- Why rejected: every Codex failure is the *same* exception class, so `isinstance` cannot distinguish a rate limit from a missing SDK extra. Without the per-code table, either every failure spends the chain or none does.

### Alternative 4: Allow cross-provider fallback

- What: Let a chain entry name `anthropic` and construct a different agent type for it.
- Why rejected: a Codex thread cannot move to another provider — the conversation, the cached prefixes, and the thread id are all Codex's. Presenting a fresh Anthropic agent with none of that history as a "fallback" would return an answer to a different question.

### Alternative 5: Ship the failure vocabulary alone, fallback in a later PR

- What: Two PRs instead of one.
- Why rejected: the classification's only consumer in this change is the fallback decision, so shipping it alone adds a table nothing reads, and shipping fallback alone means retrying the unretryable. Requirement 15 — that both judgments must agree — is only testable when both exist.
