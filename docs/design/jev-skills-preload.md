# Design Doc: Jev Skills Preload

**Status:** Approved
**Author:** Codex
**Created:** 2026-09-30
**Last Updated:** 2026-10-01

---

## 1. Overview

Add optional request-time skill selection to `JevAgent`. Callers configure plain skill documents in the existing grouped alignment settings. After the gate and existing prompt/tool alignment, Jev evaluates every configured skill against the current request in one or more bounded decision calls. Ordinary small collections fit in one call; larger collections are split into stable-order batches. The selected skill text is appended to the effective system prompt for that run, and the response records which skills were selected, skipped, or unavailable. The capability is opt-in, performs no source retrieval or code execution, and fails open when the decision service is unavailable.

---

## 2. Goals & Non-Goals

### Goals

- Accept caller supplied `SkillDocument` objects and inline strings in `JevAlignmentSettings.skills`.
- Preserve inline text exactly and assign deterministic names to inline values.
- Reject malformed documents and duplicate skill names at settings construction.
- Ask one request-local relevance question per skill, packing questions into bounded Jev requests.
- Use a configurable, validated yes-probability threshold with the existing Jev default yes threshold.
- Append only skills that meet the threshold to the effective system prompt for the current run.
- Expose per-skill selected, skipped, unavailable status, relevance probability when available, source provenance, and decision usage on `JevAgent.response.skills`.
- Preserve existing gate, specialist, prompt alignment, tool alignment, selector, run-state, and main-loop ordering.
- Keep prompt, tools, and options mutations scoped to one run, including failure and cancellation paths.

### Non-Goals

- Fetching or resolving skills from files, URLs, registries, or third-party providers.
- Provider-specific native skill attachment or adapter code.
- Running scripts, tools, or commands contained in a skill.
- Automatically loading skills when the caller did not configure any.
- Changing the agent's base prompt or its caller-provided context after the run.
- Introducing generic plugin, source, or arbitrary decision registries.

---

## 3. Background & Context

- PR #449 provides the grouped `JevAlignmentSettings` API on which this feature is based; this work stacks on that API while preserving current main's target-outcome and done-check changes.
- In merged main, `DecisionModelConfig` belongs to `JevRuntimeSettings`, not `JevAgentSettings`; `JevAgentAlignment` receives that dependency explicitly from the facade rather than reading it from agent settings.
- Existing prompt alignment, tool alignment, and tool selection execute in `JevRuntime.arun`. The gate runs first; a closed gate and specialist delegation return before those request-time passes.
- Existing `JevPreflight` changes a `Tools` catalog and cannot provide modified `BaseAgentContext`. Skills therefore use a narrow `JevPreload` context-transform contract.
- `JevResponse.start()` replaces the public response record on each run. A new `skills` field follows this latest-run lifetime.
- `DecisionModelHelper` owns the standard Jev transport and `score_noul` scoring. Feature code owns how unavailable answers affect each candidate.
- `BaseAgentContext` is immutable; the preload creates a replacement context with an updated system prompt.
- Skill text is caller-provided untrusted content. It is decision evidence and eventual context material, never executable input.

---

## 4. Requirements

### Functional Requirements

1. `JevAlignmentSettings.skills` defaults to an empty tuple and accepts a tuple or iterable of `SkillDocument` and string values, normalizing to an immutable tuple.
2. Each string becomes a `SkillDocument` with a deterministic index-based name and a fixed inline-source description. Its `text` bytes-as-string are preserved exactly, including leading and trailing whitespace.
3. A `SkillDocument` requires a nonblank name, description, and text. It stores optional source as plain string provenance and never resolves that source.
4. Settings reject duplicate document names after normalization; distinct supplied documents are never merged.
5. `JevRuntimeSettings.skills_threshold` is a finite probability in `[0, 1]`, defaults to the standard Jev yes threshold, rejects booleans and invalid numeric values, and is used independently for each skill.
6. No configured skills means the runtime performs no skill decision call and reports an empty skills result.
7. A closed preflight gate or selected specialist performs no skill decision call.
8. When enabled, the preload builds one indexed `JevSkillRelevanceQuestion` per configured skill and groups those questions into bounded `JevDecisionRequest` batches. The user request and each candidate's name, description, source, and full text are framed as untrusted data. Question rules refer only to fixed indexed identifiers; caller values never enter rule prose.
9. Each answer is independently scored using `DecisionModelHelper.score_noul` with that skill's question name and `skills_threshold`. A passing answer selects only its corresponding skill.
10. A valid yes/no answer for one candidate remains usable when another candidate answer is missing or malformed. A missing or malformed answer marks only that candidate unavailable. A `VidbyteSdkError` or malformed whole response makes only the current batch unavailable and selects none from that batch; cancellation propagates.
11. A known answer below threshold records skipped; an unavailable answer records unavailable. Each result preserves stable name, description, source, answer probability if present, and status.
12. Selected skill texts are appended in configured order to the effective system prompt. Existing prompt content and its suffix are preserved, and the original context object is not mutated.
13. If caller options explicitly supply a system prompt override, that value is the effective baseline before selected skill text is appended. The resulting context prompt is what the provider receives.
14. Runtime-local prompt, user tool catalog, full tool catalog, and run options are restored in a `finally` path, including cancellation and main-loop failure.
15. Runtime skill selection runs after enabled prompt/tool alignment and before `JevRunState.begin()`, selector processing, and the main loop.
16. `JevAgent.response.skills` is replaced with each run's `JevSkillsOutcome`, which carries per-skill records and decision usage. It carries no skill text.
17. Exports expose `SkillDocument` and the response record type through the established lib, Jev, agents, and root SDK exports.

### Non-Functional Requirements

- A no-skill run adds no request latency and performs zero extra Jev calls.
- Selection packs questions into bounded requests using conservative UTF-8 JSON byte counts: at most 60,000 bytes per request and at most 30,000 bytes for state plus the largest question. These local safety bounds leave room under TypeSafe's documented 64k total / 32k state-plus-largest-question token limits; they are not vendor byte caps. Small collections use one request.
- All runtime work fails open: skill selection errors preserve the effective prompt and continue the main run.
- Skill text is explicitly labeled as untrusted evidence in the Jev question; this code does not interpret or execute its contents.
- No source text or skills are written to logs or response records. Usage and non-sensitive metadata may be recorded.
- There is no shared mutable per-run preload state; outcomes are written to the per-agent response only.

---

## 5. High-Level Design

The public settings layer normalizes skill documents once. `JevAgent` constructs a preload object only when skills are configured and passes it, the alignment settings, threshold, and response writer into each runtime. Existing gate behavior remains first: a stopped request or specialist handoff returns before the main agent's preload. Prompt and tool alignment continue in their current order.

After alignment, the runtime constructs the effective baseline system prompt from the caller's explicit options override when present, otherwise from the aligned context. The preload greedily packs indexed questions into bounded requests in settings order, keeping the user request and only that batch's full candidate records in each state. It scores answers independently, keeps stable global indices, and records every candidate. A failed batch marks only its candidates unavailable; a candidate too large to fit alone is unavailable without truncation. Other batches continue. Selected full skill texts are appended in settings order to a replacement `BaseAgentContext`. The runtime then enters run-state setup, tool selection, and the main loop. Its `finally` block restores runtime fields so a later call cannot inherit an earlier prompt or tools.

```text
Jev gate -> prompt alignment -> tool alignment -> bounded skill batches
                                                | selected docs
                                                v
                                   replacement run context
                                                |
                                   run state -> selector -> loop
```

---

## 6. Detailed Design

### 6.1 Validated skill document

**File(s):** `vidbyte/lib/dataclasses/skills.py`
**Type:** New file

#### What it does

Defines the immutable public plain-text contract for one skill and validates required metadata without changing the supplied text.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SkillDocument:
    name: str
    description: str
    text: str
    source: str | None = None
```

#### Logic / Algorithm

1. Require nonblank name, description, and text; retain each original string exactly.
2. Require source to be `None` or a nonblank string and retain it exactly.
3. Export the type through the existing dataclass package.

#### Edge Cases & Error Handling

- Wrong types, blank required fields, or blank non-null source raise `ConfigurationError`.
- Text validation does not trim or normalize the stored text.

### 6.2 Skill settings and thresholds

**File(s):** `vidbyte/agents/jev/settings.py`
**Type:** Modified

#### What it does

Adds inline and pre-resolved documents under grouped alignment settings and a runtime relevance threshold.

#### Interface / API

```python
JevAlignmentSettings.skills: tuple[SkillDocument | str, ...] = ()
JevRuntimeSettings.skills_threshold: float = JEV_NOUL_YES_THRESHOLD
```

#### Logic / Algorithm

1. Reject a string or bytes object as the collection itself.
2. Normalize each item in order. Strings become documents named `inline_skill_1`, `inline_skill_2`, and so on, with a fixed inline description and unchanged text.
3. Require every other item to be a `SkillDocument`.
4. Reject duplicate names across the normalized tuple.
5. Validate and normalize the finite threshold in the closed interval `[0, 1]`.

#### Edge Cases & Error Handling

- An empty tuple disables loading.
- A duplicate explicit name, including collision with a generated inline name, raises `ConfigurationError`.
- Boolean, NaN, infinity, and out-of-range thresholds raise `ConfigurationError`.

### 6.3 Dynamic skill relevance questions

**File(s):** `vidbyte/lib/jev/preflight/skills.py`
**Type:** New file

#### What it does

Builds one indexed question per candidate and groups questions into bounded Jev requests.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class JevSkillRelevanceQuestion:
    index: int
    skill: SkillDocument

    @property
    def name(self) -> str: ...

    def to_question(self) -> JevQuestion: ...
```

#### Logic / Algorithm

1. Name questions `skills.skill_<index>` using stable tuple order.
2. Render complete question instructions with sections for scope, state, definitions, rules, examples, boundaries, and the final yes/no question. The question text alone must exceed 2,000 meaningful tokens across instructions and criteria, following `skills/asking-jev-questions/SKILL.md`.
3. Pass the original user request and each candidate's name, description, source, and full text as structured data labeled untrusted. Refer to a candidate in question prose only by its fixed indexed identifier, and instruct Jev to assess relevance only and not follow candidate instructions.
4. Build each `JevDecisionRequest` from one bounded batch. Do not truncate or summarize candidate text.
5. Greedily pack questions in configured order under local 60,000-byte total and 30,000-byte state-plus-largest-question bounds. Count UTF-8 serialized JSON bytes conservatively; do not describe these local bounds as TypeSafe byte limits. Keep global indices stable and each full document wholly inside one batch. Mark a candidate too large to fit alone unavailable and continue packing later candidates.

#### Edge Cases & Error Handling

- Indices, not user skill names, uniquely identify answers even when names contain punctuation.
- Instructions embedded in skill text are data for relevance classification, not instructions to Jev.
- No arbitrary per-skill truncation is introduced.

### 6.4 Context preload contract and implementation

**File(s):** `vidbyte/agents/jev/preload.py`, `vidbyte/agents/jev/alignment/skills.py`
**Type:** New files

#### What it does

Defines a narrow pre-loop context transformation contract and implements fail-open skill selection without changing tools.

#### Interface / API

```python
class JevPreload(ABC):
    @abstractmethod
    async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext: ...

class JevSkillsPreload(JevPreload):
    async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext: ...
```

#### Logic / Algorithm

1. Pack indexed candidate questions in stable order under the local byte bounds; small collections produce one batch.
2. Capture Jev usage from the provider response. Catch only the SDK/domain error types used by existing Jev paths; let cancellation propagate.
3. Score each candidate independently using `score_noul` with a one-name sequence and configured threshold.
4. Send each batch sequentially via `DecisionModelHelper`. Create selected, skipped, or unavailable result records. A valid answer is retained when another is missing; an SDK/request failure marks only that batch unavailable and later batches continue.
5. Append selected full texts in settings order after an explicit section separator; preserve the entire baseline prompt.
6. Sum usage once across successful batches. Return `dataclasses.replace(context, system_prompt=...)`; a failed batch leaves only its candidates unavailable while successful batches remain usable.
7. Do not mutate caller context, tools, agent settings, or provider options.

#### Edge Cases & Error Handling

- A missing answer or non-noul answer marks only its candidate unavailable.
- A `VidbyteSdkError` for one batch marks only that batch unavailable and must not silently select a skill. An individually oversized skill is unavailable without truncation. Cancellation and unexpected programming errors propagate after runtime cleanup; ordinary SDK/provider failures leave those candidates out while successful batches remain usable.
- Usage may be absent; records then use `None`.

### 6.5 Runtime orchestration and cleanup

**File(s):** `vidbyte/agents/jev/agent.py`, `vidbyte/agents/jev/alignment/agent.py`, `vidbyte/agents/jev/runtime.py`
**Type:** Modified

#### What it does

Constructs the preload only for nonempty configuration, orders it after alignment, exposes effective prompt overrides, and isolates mutations to a single runtime call.

#### Interface / API

The public method remains `JevAgent.arun(...)`. Internal `JevRuntime` receives the optional `JevPreload` and `skills_threshold` through its constructor extension arguments. `JevAgentAlignment` receives the owner `DecisionModelConfig` explicitly from `JevRuntimeSettings`.

#### Logic / Algorithm

1. Build `JevAgentAlignment` with the validated agent settings and `runtime_settings.decision`; alignment never reads a decision model from `JevAgentSettings`.
2. Preserve current gate and specialist early returns.
3. Snapshot `self.system_prompt`, `self.user_tools`, and `self.tools` before request-time mutation.
4. Run existing prompt alignment and tool alignment.
5. Resolve the effective system prompt: explicit `options["system"]` if supplied, else the aligned `context.system_prompt`.
6. Apply the skill preload to a replacement context using that effective prompt as baseline; pass the resulting context prompt to the provider even when options previously carried an override.
7. Continue with run-state initialization, selector, and main loop.
8. Restore snapshots in `finally`; preserve tool-alignment resource cleanup.

#### Edge Cases & Error Handling

- Alignment errors and skill errors follow their existing or declared fail-open behavior.
- The explicit caller override is preserved as the effective system prompt and has selected skills appended.
- Cancellation, exception, and success all restore runtime fields and close attachments.
- Gate closure and specialist execution create no skill relevance request.

### 6.6 Public response

**File(s):** `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/agents/jev/response.py`
**Type:** Modified

#### What it does

Records per-skill decision outcomes for the latest run without retaining candidate text.

#### Interface / API

```python
class JevSkillStatus(str, Enum):
    SELECTED = "selected"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"

@dataclass(frozen=True, slots=True)
class JevSkillResult:
    name: str
    description: str
    source: str | None
    status: JevSkillStatus
    probability: float | None = None

@dataclass(frozen=True, slots=True)
class JevSkillsOutcome:
    results: tuple[JevSkillResult, ...] = ()
    usage: ProviderUsage | None = None

JevAgentResponse.skills: JevSkillsOutcome = field(default_factory=JevSkillsOutcome)
```

#### Logic / Algorithm

1. Add `JevResponse.skills(...)` to replace the latest-run outcome.
2. Reset naturally through `JevResponse.start()`.
3. Record every configured candidate in stable order, including skills not selected, and attach decision usage when available.

#### Edge Cases & Error Handling

- Missing answer probabilities remain `None`.
- The response never includes skill text.
- A no-skill, gate-stop, or specialist run has an empty outcome.

---

## 7. Data Model Changes

### 7.1 SkillDocument

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class SkillDocument:
    name: str
    description: str
    text: str
    source: str | None = None
```

**Migration strategy:** No persisted schema or database migration. The type is a new optional configuration value.

### 7.2 Jev skill result

**Change type:** Modified

```python
class JevAgentResponse:
    skills: JevSkillsOutcome = field(default_factory=JevSkillsOutcome)
```

**Migration strategy:** Existing response consumers receive an empty outcome with no results and no usage.

---

## 8. API Changes

### 8.1 Python settings API

**Change type:** Modified

**Request:**

```python
JevAgentSettings(
    ...,
    alignment=JevAlignmentSettings(
        skills=(
            SkillDocument(name="review", description="Review code changes", text="..."),
            "Caller supplied skill body",
        )
    ),
)
```

**Response:**

```python
agent.response.skills  # JevSkillsOutcome(results, usage)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| `ConfigurationError` | Invalid document, duplicate name, or invalid threshold |
| Per-item `unavailable` | Missing or malformed answer for that skill |
| Batch items `unavailable` | Jev request/provider failure; other batches can still inject selected skill text |

---

## 9. File Change Manifest

Complete list of every file planned for this change:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-skills-preload.md` | Feature design |
| CREATE | `vidbyte/lib/dataclasses/skills.py` | Validated public document |
| CREATE | `vidbyte/lib/jev/preflight/skills.py` | Dynamic relevance question and request construction |
| CREATE | `vidbyte/agents/jev/preload.py` | Narrow context-preload contract |
| CREATE | `vidbyte/agents/jev/alignment/skills.py` | Skill selection and context injection |
| CREATE | `tests/test_jev_skill_preload.py` | Focused contract, response, and runtime tests |
| MODIFY | `tests/test_jev_tool_alignment.py` | Verify the alignment runner receives runtime-owned decision settings |
| CREATE | `tests/features/jev_skills_preload/FEATURE.md` | Feature test pack and regression map |
| CREATE | `scripts/test-jev-skills-preload.py` | Focused executable gate |
| MODIFY | `vidbyte/agents/jev/settings.py` | Skills configuration and threshold |
| MODIFY | `vidbyte/agents/jev/agent.py` | Build and pass preload |
| MODIFY | `vidbyte/agents/jev/alignment/agent.py` | Receive the decision config from runtime settings |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Run ordering, prompt baseline, cleanup |
| MODIFY | `vidbyte/agents/jev/response.py` | Write per-run skill outcomes |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Skill result and response field |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Public dataclass export |
| MODIFY | `vidbyte/lib/__init__.py` | Public lib namespace export |
| MODIFY | `vidbyte/lib/enums/jev.py` | Skill outcome enum |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Public enum namespace |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Jev exports |
| MODIFY | `vidbyte/agents/__init__.py` | Agents namespace export |
| MODIFY | `vidbyte/__init__.py` | Root SDK export |
| MODIFY | `vidbyte/lib/jev/preflight/README.md` | Preflight question module index |
| MODIFY | `skills/jev-agent/SKILL.md` | Document runtime skill capability |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] `test_skill_document_validates_required_metadata_and_preserves_text_exactly`
- [Hidden Assumption] `test_alignment_settings_normalize_inline_strings_with_stable_names`
- [Edge Case] `test_alignment_settings_reject_duplicate_named_documents`
- [Edge Case] `test_runtime_settings_reject_invalid_skill_thresholds`
- [Hidden Assumption] `test_skill_request_has_one_question_per_skill_and_preserves_candidate_text`
- [Silent Failure] `test_skill_question_exceeds_meaningful_token_floor`
- `test_skill_preload_selects_only_answers_over_threshold`
- [Hidden Failure] `test_skill_preload_records_skipped_and_unavailable_independently`
- [Hidden Failure] `test_provider_failure_marks_all_unavailable_and_returns_original_context`
- [Silent Failure] `test_no_skills_skips_decision_call`
- `test_response_start_resets_skills_for_repeated_runs`

### Integration Tests

- Verify `test_alignment_uses_the_runtime_decision_configuration` proves a caller-provided `JevRuntimeSettings.decision` reaches the alignment runner without adding a field to `JevAgentSettings`.
- Verify ordering after prompt/tool alignment and before run-state/main loop.
- Verify gate stop and specialist handoff make zero skill calls.
- Verify selected full text is appended while original caller context and prompt suffix remain intact.
- Verify an explicit `options["system"]` override is passed to the provider with selected skill text appended.
- [Hidden Failure] Verify runtime prompt and tool fields restore after success, provider error, main-loop error, and cancellation.
- Mock `DecisionModelHelper` and the runner; no external provider is contacted.

### Manual / QA Test Cases

1. Given an empty skills tuple, run a JevAgent request and confirm the ordinary call path runs with no extra TypeSafe request.
2. Given two skills and one above-threshold answer, confirm only that full skill text reaches the provider and both outcomes appear in response order.
3. Given one missing answer and one valid yes answer, confirm the yes skill is still injected and only the missing candidate is unavailable.
4. Given a failing decision provider, confirm no skill is injected and the main agent still runs.
5. Given a caller system prompt override, confirm the provider receives that value plus selected skill content.

Required automated gates: `python scripts/test-jev-skills-preload.py`, Jev agent scaffold and multipart done scripts, `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py`.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing TypeSafe decision model | Existing `DecisionModelHelper` contract | Batched relevance classification | Request/provider failure yields no selected skills |
| Existing Jev context and runtime | Repository implementation | Append selected prompt text for this run | Runtime state must be restored on every exit |

No new package or external service is introduced.

---

## 12. Rollout & Deployment

- No feature flag is required: the empty tuple is the disabled default.
- This is an additive Python configuration and response API.
- Rollback removes the optional settings and runtime hook; existing calls with default settings remain unchanged.
- No source adapter ordering or deployment step is required.

---

## 13. Open Questions

- [ ] None for the core caller-provided document contract. Source resolvers and provider-native attachments are explicitly deferred to separate adapter work.

---

## 14. Alternatives Considered

### Alternative 1: Add a separate top-level Jev skills setting

- What: Place `skills` directly on `JevAgentSettings`.
- Why rejected: Grouped request-time adjustments already live in `JevAlignmentSettings`, and PR #449 establishes this public grouped API.

### Alternative 2: Reuse JevPreflight

- What: Extend the existing `JevPreflight` interface for skill injection.
- Why rejected: It returns `Tools`, whereas skills must replace `BaseAgentContext` while preserving the existing tool catalog.

### Alternative 3: Load every configured skill

- What: Append every skill without a Jev relevance decision.
- Why rejected: The requested runtime capability is selective; unconditional injection defeats per-request relevance and increases prompt size.

### Alternative 4: Resolve URLs and provider-native skill formats in core

- What: Fetch remote skill content and attach vendor-native skill references here.
- Why rejected: Source resolution and native provider contracts are separate adapters; the core contract stays a validated plain document and never invents remote content endpoints.
