# Design Doc: Critique-Adjudicate-Revise Context-Window Algorithm

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

This feature adds a `critique_adjudicate_revise` return-level context-window algorithm to the Vidbyte SDK. A normal producer run first creates a candidate. Multiple critics then inspect the same original task and candidate concurrently in fresh, mutually isolated contexts. Their structured findings remain quarantined from the producer and revision worker while a separate adjudicator deduplicates them, rejects unsupported claims, and resolves contradictions. The runtime deterministically constructs an accepted-findings envelope from the adjudicator's references, and only that envelope is given to a fresh revision worker. The algorithm exists to obtain the quality benefit of adversarial review without allowing raw criticism, judge-authored allegations, producer scratch history, or peer influence to leak across stage boundaries.

---

## 2. Goals & Non-Goals

### Goals

- Expose `ContextWindow.preset.critique_adjudicate_revise` and support `ContextWindow.resolve_algorithm("critique_adjudicate_revise")`.
- Preserve a strict four-stage boundary: producer -> isolated critic fan-out -> adjudicator -> isolated revision worker.
- Launch every critic concurrently over the exact same task/candidate payload, and prevent critics from seeing peer findings before the critic barrier closes.
- Quarantine raw findings from the producer and revision worker; the revision worker receives only runtime-validated accepted findings.
- Represent findings, evidence, adjudication references, and accepted findings with immutable typed contracts and deterministic IDs.
- Prevent the adjudicator from inventing revision instructions by making accepted findings a runtime-built projection of referenced critic findings and evidence.
- Give critic, adjudicator, and revision stages independent artifact/tool allow-lists, model selection, timeouts, and failure policies.
- Preserve normal agent tools, permissions, middleware, tracing, provider formatting, result metadata, calls, and user output-schema behavior for the producer while giving every downstream stage a fresh, empty middleware boundary.
- Provide catalog-backed role prompts, deterministic recorder slots, a reusable context-window template, public exports, presets, and documentation.

### Non-Goals

- No iterative review loop after the first revision; this algorithm performs one producer pass, one critic round, one adjudication, and at most one revision.
- No specialist responsibilities or critic-to-critic debate; those are separate Specialist Panel and Parallel Panel algorithms.
- No prosecutor/defender exchange, pairwise candidate tournament, or generation of multiple producer candidates.
- No environment transaction or rollback. Producer and allowed stage tools may have irreversible side effects.
- No claim that an LLM adjudicator is a ground-truth verifier. Structural provenance can be enforced; semantic judgment remains model-dependent.
- No automatic exposure of producer history, memory, metadata, file paths, prior responses, tool calls, context items, or private reasoning to downstream stages.
- No database, persistence, CLI, MCP endpoint, hosted service, or provider API change.
- No unit tests or verification scripts in this change, per the requested no-tests workflow.

---

## 3. Background & Context

### Research basis

Several primary sources motivate the shape while also showing why a separate adjudication gate is necessary:

- [Constitutional AI](https://arxiv.org/abs/2212.08073) applies critique followed by revision and reports that critiques can be inaccurate or overstated. That is direct evidence against forwarding every critique to a worker as if it were true.
- [Self-Refine](https://arxiv.org/abs/2303.17651) demonstrates the general feedback-then-refinement pattern, but uses the same model as generator, feedback provider, and refiner; this design deliberately separates contexts and roles.
- [CRITIC](https://arxiv.org/abs/2305.11738) shows that external tools can provide useful evidence for critique and revision. This design therefore supports tools, but only through explicit per-stage allow-lists.
- [ChatEval](https://arxiv.org/abs/2308.07201) supports multi-agent evaluation and finds role/communication structure affects results. The requested first-round isolation is stricter than debate: reviewers do not communicate at all.
- [Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685) documents position, verbosity, self-enhancement, and reasoning biases. The adjudicator is therefore constrained to references and dispositions rather than trusted to synthesize new allegations.
- Python 3.11's [`asyncio.gather`](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.gather) runs awaitables concurrently, preserves input order in returned results, and can collect exceptions; [`asyncio.wait_for`](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.wait_for) supplies bounded cancellation. These match the SDK's Python `>=3.11` baseline and existing multi-provider fan-out conventions.

### Current SDK state

The audit was performed against clean `main` commit `213d3378f2b5a8c981318a9e1619daa998890f62`. `ContextWindowAlgorithm` permits at most one active runtime algorithm. `ReflexionAlgorithm` and `MultiProviderAgenticGraderAlgorithm` are return-level configurations with adapters under `vidbyte/agents/algorithms/`; trajectory checkpoints, problem-space search, and error correction are inner-loop algorithms invoked through `after_tool_calls`. Critique-adjudicate-revise belongs to the return-level family because it must obtain a completed producer result before review and replace the result only after adjudication/revision.

The existing multi-provider grader establishes concurrent `asyncio.gather(..., return_exceptions=True)` fan-out, runner substitution, candidate collection, and final `AgentResult` assembly. Reflexion establishes catalog prompts, trial/stage orchestration, result metadata, and recorder slots. The prompt catalog auto-discovers JSON/Markdown assets keyed by `Prompt`, while `ContextWindowTemplate` validates deterministic recorder slot sequences. Middleware per-run state is already isolated through a fresh `run_state` per `_arun_once`, which makes concurrent stage runtimes compatible with current built-ins.

The unmerged Devil's Advocate branch at `worktree-sdk-devils-advocate` was inspected as read-only family precedent. It confirms the expected additive surface: frozen configuration, one preset field, dispatcher wiring, prompt enum/assets, public exports, recorder template, and documentation. Its inner-loop stack machine is not reused because this feature has different data-flow and isolation requirements.

### Terminology and trust boundaries

- **Original task:** the exact user message supplied to this run. Producer system instructions are private by default; callers may expose requirement text only through an explicitly allowlisted artifact.
- **Candidate:** the producer's exact `AgentResult.output`; it is never silently truncated.
- **Raw finding:** a critic's parsed, evidence-bearing finding before adjudication.
- **Accepted finding:** a runtime-constructed copy of one canonical raw finding plus referenced evidence and provenance IDs. The adjudicator cannot author its claim or recommendation.
- **Scratch/private history:** reasoning text, stage conversation history, tool interaction history, judge rationale, and producer history that is not part of a stage's explicit envelope.
- **Barrier:** the point after every critic has either completed, failed, or timed out. No adjudication starts before it.

---

## 4. Requirements

### Functional Requirements

1. `ContextWindow.preset.critique_adjudicate_revise` returns a `ContextWindowAlgorithm` named `"critique_adjudicate_revise"` containing a default `CritiqueAdjudicateReviseAlgorithm`.
2. `ContextWindowAlgorithm` continues to reject configurations with more than one active runtime algorithm.
3. The producer stage invokes the existing `_arun_once` path exactly once with the caller's original `RunnerHandle`, `BaseAgentContext`, metadata, options, and trace parent. Its complete `AgentResult` becomes the candidate record.
4. The runtime builds a new immutable stage envelope; it must not derive downstream contexts with `dataclasses.replace(context, ...)` because that would retain history, memory, file paths, metadata, tool calls, responses, or context items.
5. The original-task envelope contains only the exact user message. The candidate envelope contains the exact producer output. If either would make a stage payload exceed `max_stage_input_chars`, the algorithm fails closed rather than truncating it.
6. Artifacts are included only by exact name from the stage's `allowed_artifact_names`. Missing names and duplicate source artifact names are preflight errors. Artifact content is serialized exactly and participates in the stage input limit; file paths are never dereferenced implicitly.
7. User tools are included only by exact name from the stage's `allowed_tool_names`, resolved from `runtime.user_tools` through `Tools.subset`. Selected tools use `clone_for_fork()` when available; tools with live producer/agent/context/session bindings that cannot be reviewer-safely cloned are rejected. Every stage runtime uses `include_internal_tools=False`, so its configured allowlist is exact and no implicit completion tool is present.
8. A non-empty parallel critic tool allow-list with `critic_count > 1` requires `allow_parallel_critic_tools=True`. This explicit opt-in acknowledges that the SDK cannot infer whether arbitrary custom tools are concurrency-safe or side-effect-free.
9. Every critic receives the same serialized original-task, candidate, and critic-artifact payload and the same critic role prompt. A fresh stage runtime, context, message list, and run state is created per critic; no context manager or producer middleware is inherited.
10. Critics launch concurrently with `asyncio.gather(..., return_exceptions=True)`. Each critic is wrapped in its own `asyncio.wait_for(..., critic_timeout_seconds)`. Returned results are restored to configured critic-index order, not completion order.
11. Critics never receive another critic's findings, result metadata, trace, tool output, or failure. The adjudicator cannot start until the barrier has observed every critic as successful, failed, or timed out.
12. `CriticFailurePolicy.REQUIRE_ALL` (default) fails after the barrier if any critic failed. `REQUIRE_QUORUM` continues only when `min_successful_critics` is explicitly configured and met. Failed critic content is not included in adjudication.
13. A critic returns strict JSON with `findings`. Unknown fields, malformed JSON, excess counts, blank required text, invalid enums, or ungrounded evidence make that critic result invalid.
14. The runtime assigns IDs, never the model: `critic-001`, `critic-001:finding-001`, and `critic-001:finding-001:evidence-001`. IDs are stable by configured critic index and parsed list position.
15. Each finding contains category, severity, claim, recommendation, and at least one evidence item. Evidence contains a source kind (`task`, `candidate`, `artifact`, or `tool`), source name, locator, and exact excerpt.
16. Task/candidate/artifact evidence excerpts must be exact substrings of the named source. Tool evidence must reference a completed, allow-listed critic-stage tool call and an exact substring of its output. Structural evidence validation occurs before adjudication.
17. The adjudicator receives only the original task, exact candidate, successfully parsed raw findings, its allowed artifacts/tools, and its adjudicator prompt. It receives no critic conversation history or scratch output.
18. The adjudicator returns strict JSON disposition groups. An accepted group names one `canonical_finding_id`, all `source_finding_ids` treated as duplicates/equivalents, and selected `evidence_ids`. Rejected groups name finding IDs and a bounded reason code (`unsupported`, `duplicate`, `contradicted`, `out_of_scope`, or `not_actionable`).
19. Referential-integrity validation requires every successful raw finding ID to appear exactly once across accepted and rejected groups; all references must exist; a canonical ID must be a member of its group; evidence references must belong to grouped findings; and IDs may not appear in more than one group.
20. The adjudicator cannot write accepted claim, recommendation, category, severity, or evidence prose. After validation, the runtime deterministically sorts accepted groups, assigns `accepted-001` IDs, copies the canonical finding fields, copies only referenced evidence, and attaches all source finding IDs.
21. Deduplication is represented by one accepted finding with multiple source IDs. Contradictions are resolved by accepting one supported group and rejecting competing IDs, or rejecting all; the adjudicator cannot create a compromise allegation.
22. The revision worker receives only the original task, exact candidate, runtime-built accepted findings, its allowed artifacts/tools, and the reviser prompt. It receives no raw findings, rejected findings, judge dispositions/rationale, producer history, or stage scratch.
23. If adjudication accepts zero findings, the revision stage is skipped and the exact producer result is returned with `status="unchanged_no_accepted_findings"`.
24. Otherwise the revision worker returns strict JSON with `revised_candidate` and `applied_finding_ids`. The applied-ID set must equal the accepted-ID set exactly; unknown, duplicate, omitted, or unapplied accepted IDs invalidate the revision.
25. The revised candidate must be non-empty, must not exceed `max_candidate_chars`, and is not accepted through fuzzy extraction or silent truncation.
26. If the original agent configured `output_schema`, the revised candidate is validated with the same `OutputSchemaFormatter`. Invalid revised structured output is a revision failure; valid parsed data becomes final `AgentResult.structured`. If revision is skipped or falls back, producer `structured` is preserved.
27. Adjudicator and revision calls are each bounded by their configured timeout. `StageFailurePolicy.RAISE` is the default. An explicit `RETURN_CANDIDATE` policy returns the producer candidate unchanged with degraded status; it never returns a partial revision.
28. Algorithm-level retries are not added. Producer middleware remains confined to the producer, and a stage is not replayed by this algorithm because allowed tools may have side effects; any provider/runner-internal transport retry remains governed by its existing contract.
29. The final `AgentResult` has `strategy_name="critique_adjudicate_revise"`. Its output is the revised candidate or exact producer candidate according to the defined outcome.
30. `AgentResult.calls` concatenates producer calls and completed stage tool-call contexts in deterministic stage order: producer, critics by critic index, adjudicator, revision. Stage call metadata includes algorithm, stage, and critic ID where applicable.
31. Top-level producer metadata is preserved. Top-level `metadata["tool_calls"]` remains the producer's tool-call sequence so later producer history is not contaminated with review-stage tool output. Stage calls are exposed through `AgentResult.calls` and sanitized algorithm summaries.
32. `metadata["critique_adjudicate_revise"]` reports status, requested/successful critic counts, critic failure types, raw/accepted/rejected finding counts, accepted findings, adjudication disposition IDs/reason codes, applied IDs, stage models, stage timeouts, stage call/token counts, allow-list names, and total elapsed time. It omits raw/rejected finding prose, stage prompts, scratch text, and raw tool outputs.
33. Semantic tracing creates one existing root `algorithm.critique_adjudicate_revise` span plus producer, critic (one per index), adjudication, and revision child spans. Algorithm-specific attributes are content-free identifiers, hashes, counts, timing, and statuses; they never contain task/candidate/artifact text, tools arguments/results, findings, dispositions, revisions, provider responses, or raw exceptions. Child model/tool spans use the existing global tracer policy. No trace object or trace output is injected into another stage.
34. Recorder slots are deterministic and never appended from concurrent critic tasks: `system_prompt`, `critique_adjudicate_revise_producer`, `critique_adjudicate_revise_critic_fanout`, `critique_adjudicate_revise_critic_barrier`, `critique_adjudicate_revise_adjudication`, then exactly one of `critique_adjudicate_revise_revision` or `critique_adjudicate_revise_revision_skipped`. Failures add `critique_adjudicate_revise_failure` after the last begun stage.
35. Prompt bodies live in the Markdown-backed prompt catalog and may be replaced only by validated non-empty config override strings.
36. The algorithm is supported only by the linear text runtime, matching all existing non-default context-window algorithms.

### Non-Functional Requirements

- **Isolation:** downstream contexts are constructed from explicit immutable envelopes, never inherited mutable producer/stage context.
- **Concurrency:** all critics are scheduled before the barrier await; no critic output becomes input to a peer. Result ordering is deterministic despite nondeterministic completion.
- **Performance:** default cost is one producer run, three concurrent critic runs, one adjudicator run, and at most one revision run. Wall-clock critic latency is bounded by the slowest per-critic timeout rather than their sum.
- **Reliability:** defaults are fail-closed (`REQUIRE_ALL`, `RAISE`, `RAISE`). Degraded return behavior requires explicit configuration and is visible in metadata.
- **Security:** stage data is treated as untrusted JSON data; candidate/artifact text cannot alter the control-plane role prompt merely by containing prompt-like text. Default stage tool/artifact allow-lists are empty.
- **Provenance:** accepted text and evidence are copied from identified raw findings, with complete one-time adjudication coverage and no unknown references.
- **Boundedness:** field counts, field lengths, candidate size, serialized stage input size, per-stage iterations/tool calls, and timeouts are validated.
- **Observability:** spans, recorder slots, and sanitized metadata make stage timing/outcomes auditable without injecting raw review text into later contexts.
- **Compatibility:** the default context-window algorithm and all existing presets behave unchanged when this field is unset.
- **Implementation style:** every implementation function and method signature is written on exactly one line, followed immediately by a one- or two-line explanatory code comment; non-trivial orchestration is class-first.

### Acceptance Criteria

- A three-critic run proves all three critics start before any is released, and the adjudicator is not called until all three settle.
- Each critic-stage request contains byte-equivalent task/candidate JSON values and no sentinel values placed in producer history, memory, metadata, responses, tool calls, file paths, or context items.
- A judge response containing an unknown finding/evidence ID, duplicate coverage, omitted raw ID, or judge-authored accepted prose fails before revision.
- A revision-stage request contains accepted findings and does not contain rejected/raw finding prose or judge rationale.
- A no-accepted-findings decision returns the exact producer output/structured value and does not call the revision worker.
- Tool and artifact access is empty by default and exact-name limited when configured.
- Final calls, metadata, structured output, tracing parents, and recorder slots match the contracts above for revised, skipped, timeout, quorum, and degraded-return outcomes.

### Risks & Mitigations

- **Judge bias or correlated model errors:** critics and adjudicator may share blind spots, especially when they use the same model. Mitigation: preserve critic independence, allow per-stage model overrides, require grounded evidence, expose accepted/rejected counts, and never describe adjudication as ground truth.
- **Prompt injection in candidate/artifacts:** reviewed content can contain instructions aimed at reviewers. Mitigation: serialize it as JSON data beneath fixed role prompts, start fresh contexts, reject non-schema output, and default all stage tools to unavailable.
- **Duplicate or irreversible tool side effects:** producer, concurrent critics, adjudicator, or revision tools may mutate external state. Mitigation: empty defaults, exact allow-lists, inherited permission enforcement, explicit parallel-tool opt-in, no algorithm retries, and prominent degraded-return/rollback warnings.
- **Sensitive observability data:** existing provider and semantic tracers may record model-visible task, candidate, findings, or allowed artifact content. Mitigation: do not add raw stage content to algorithm attributes/result metadata or downstream contexts, document tracer retention as an operator concern, and use existing trace controls for sensitive runs.
- **Cost and tail latency:** default execution adds three critic runs, adjudication, and revision. Mitigation: critics run concurrently; every stage has count, iteration, tool-call, input-size, and time bounds; metadata exposes usage and timing.
- **Over-strict evidence matching:** exact substring checks can reject semantically valid paraphrased evidence. Mitigation: prompts require exact excerpts, task evidence can support omission claims, and strictness is preferred to silently admitting unsupported findings.
- **Large accepted set degrades revision:** even supported findings can collectively produce an unwieldy revision. Mitigation: cap findings/evidence per critic, deduplicate before revision, bound all fields and input size, and perform only one revision pass.

---

## 5. High-Level Design

The feature uses the SDK's return-level algorithm architecture. `AgentRuntimeContextAlgorithms.arun()` dispatches to `CritiqueAdjudicateReviseRuntimeAlgorithm`, which first calls the normal `_arun_once` producer path. It then creates explicit JSON stage envelopes and isolated child `AgentRuntime` instances. Each child runtime receives an exact subset of user tools, inherited permission enforcement, bounded runtime config, an empty middleware pipeline, the existing tracer, a fresh per-run state, no context manager, no context algorithm, and `include_internal_tools=False`.

Critic fan-out uses one immutable serialized payload and separate stage runtimes. `asyncio.gather(..., return_exceptions=True)` provides a full barrier and stable input-order result mapping. Each critic's strict JSON is parsed and grounded before the adjudicator sees it. The adjudicator does not author accepted content; it emits only reference groups and dispositions. This is the central design decision: semantic adjudication remains model-driven, but the information crossing into revision is mechanically limited to selected source material.

The revision worker is another fresh stage runtime. Its input envelope is rebuilt from the original task, candidate, accepted findings, and revision allow-lists, so neither Python object reuse nor prompt assembly can accidentally carry raw findings or stage history. The final result preserves the producer's compatible metadata surface while adding sanitized algorithm metadata and deterministic call ordering.

```text
[Original Agent Context]
          |
          v
 [Producer _arun_once] ---------------------------> candidate AgentResult
          |
          | build explicit task + candidate + critic allow-list envelope
          v
 +---------------- isolated, concurrent ----------------+
 | [Critic 001]   [Critic 002]   ...   [Critic N]       |
 | fresh context  fresh context        fresh context     |
 +-----------------------+-------------------------------+
                         | full barrier; validate/ID findings
                         v
                [Adjudicator fresh context]
                refs/dispositions only
                         |
                         | runtime copies canonical source fields/evidence
                         v
                  [AcceptedFinding ...]
                         |
                zero ----+---- nonzero
                 |                |
          return candidate   [Revision worker fresh context]
                              task + candidate + accepted only
                                      |
                                      v
                              final AgentResult
```

---

## 6. Detailed Design

### 6.1 Public configuration and typed review contracts

**File(s):** `vidbyte/context/algorithms/critique_adjudicate_revise.py`
**Type:** New file

#### What it does

Defines immutable configuration, failure-policy enums, per-stage access policy, typed findings/evidence, accepted findings, strict parsers, prompt rendering, bounds, and referential-integrity validation. Non-trivial parsing/validation is class-first and split into small semantically named methods.

#### Interface / API

```python
class CriticFailurePolicy(str, Enum):
    REQUIRE_ALL = "require_all"
    REQUIRE_QUORUM = "require_quorum"

class StageFailurePolicy(str, Enum):
    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"

@dataclass(frozen=True, slots=True)
class ReviewStageAccess:
    allowed_artifact_names: tuple[str, ...] = ()
    allowed_tool_names: tuple[str, ...] = ()
    max_iterations: int = 4
    max_tool_calls: int = 4

@dataclass(frozen=True, slots=True)
class FindingEvidence:
    evidence_id: str
    source_kind: str
    source_name: str
    locator: str
    excerpt: str

@dataclass(frozen=True, slots=True)
class CriticFinding:
    finding_id: str
    critic_id: str
    category: str
    severity: str
    claim: str
    recommendation: str
    evidence: tuple[FindingEvidence, ...]

@dataclass(frozen=True, slots=True)
class AcceptedFinding:
    accepted_id: str
    canonical_finding_id: str
    source_finding_ids: tuple[str, ...]
    category: str
    severity: str
    claim: str
    recommendation: str
    evidence: tuple[FindingEvidence, ...]

@dataclass(frozen=True, slots=True)
class CritiqueAdjudicateReviseAlgorithm:
    critic_count: int = 3
    min_successful_critics: int | None = None
    critic_failure_policy: CriticFailurePolicy = CriticFailurePolicy.REQUIRE_ALL
    adjudication_failure_policy: StageFailurePolicy = StageFailurePolicy.RAISE
    revision_failure_policy: StageFailurePolicy = StageFailurePolicy.RAISE
    critic_access: ReviewStageAccess = field(default_factory=ReviewStageAccess)
    adjudicator_access: ReviewStageAccess = field(default_factory=ReviewStageAccess)
    revision_access: ReviewStageAccess = field(default_factory=ReviewStageAccess)
    allow_parallel_critic_tools: bool = False
    critic_provider: str | None = None
    critic_model: str | None = None
    adjudicator_provider: str | None = None
    adjudicator_model: str | None = None
    revision_provider: str | None = None
    revision_model: str | None = None
    critic_timeout_seconds: float = 90.0
    adjudication_timeout_seconds: float = 90.0
    revision_timeout_seconds: float = 120.0
    max_findings_per_critic: int = 8
    max_evidence_per_finding: int = 4
    max_field_chars: int = 2000
    max_candidate_chars: int = 100_000
    max_stage_input_chars: int = 250_000
    critic_prompt: str | None = None
    adjudicator_prompt: str | None = None
    reviser_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    def critic_system_prompt_text(self) -> str: ...
    def adjudicator_system_prompt_text(self) -> str: ...
    def reviser_system_prompt_text(self) -> str: ...
    def parse_critic_output(self, critic_id: str, payload: str, sources: Mapping[str, str], tool_calls: Sequence[ToolCallContext]) -> tuple[CriticFinding, ...]: ...
    def build_accepted_findings(self, payload: str, findings: Sequence[CriticFinding]) -> tuple[AcceptedFinding, ...]: ...
    def parse_revision_output(self, payload: str, accepted: Sequence[AcceptedFinding]) -> tuple[str, tuple[str, ...]]: ...
```

#### Logic / Algorithm

1. `__post_init__` normalizes enum values and tuple fields; validates positive counts/limits/timeouts; validates metadata string keys; validates provider/model pairs as both set or both absent; validates non-empty prompt overrides; validates unique allow-list names; and validates quorum relationships.
2. Critic parsing uses `json.loads` on the entire stripped output. Markdown-fence/substring extraction is intentionally not used because surrounding scratch text must not be accepted.
3. The parser rejects unknown keys at every object level, bounds list lengths/text, assigns IDs by position, and validates evidence against immutable source maps/tool results.
4. Adjudication parsing validates group schema and complete one-time coverage, then ignores group order and sorts accepted groups by their smallest source finding ID before assigning accepted IDs.
5. `AcceptedFinding` fields are copied from the canonical `CriticFinding`; selected evidence objects are copied by ID. Adjudicator output has no accepted-content fields.
6. Revision parsing requires exact accepted-ID coverage and returns the candidate plus applied IDs.

#### Edge Cases & Error Handling

- `critic_count < 1`, non-positive timeouts/limits, blank overrides, partial provider/model pairs, duplicate allow-list names, and invalid metadata keys raise `ConfigurationError` at construction.
- `REQUIRE_QUORUM` without an explicit `min_successful_critics`, or a quorum outside `1..critic_count`, raises `ConfigurationError`.
- Empty findings are valid for an otherwise valid critic. All critics returning no findings leads to zero accepted findings and a skipped revision.
- A critic claiming an omission may cite the task requirement as evidence; it need not fabricate a candidate quote for absent text.
- Exact-substring grounding is intentionally strict. Unicode normalization is not performed because it could make evidence differ from the exact stage source.
- A judge may reject every finding. It may not omit difficult findings or reference a new one.
- Judge rationale is represented only by a reason code for rejected IDs and never enters accepted findings.

### 6.2 Runtime orchestration and isolated stage runtimes

**File(s):** `vidbyte/agents/algorithms/critique_adjudicate_revise.py`, `vidbyte/agents/runtime.py`
**Type:** New adapter file and modified generic runtime

#### What it does

Coordinates producer, critic fan-out, barrier, adjudication, revision, stage runtime construction, timeout/failure handling, result assembly, tracing, and recorder slots.

#### Interface / API

```python
class CritiqueAdjudicateReviseRuntimeAlgorithm:
    name = "critique_adjudicate_revise"

    def __init__(self, runtime: AgentRuntime, algorithm: CritiqueAdjudicateReviseAlgorithm) -> None: ...
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
    async def _run_producer(self, message: str, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult: ...
    async def _run_critics(self, envelope: Mapping[str, Any], handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> tuple[_CriticOutcome, ...]: ...
    async def _run_adjudicator(self, envelope: Mapping[str, Any], handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> _StageOutcome: ...
    async def _run_revision(self, envelope: Mapping[str, Any], handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> _StageOutcome: ...
    def _build_stage_runtime(self, stage: str, access: ReviewStageAccess, context: BaseAgentContext) -> AgentRuntime: ...
    def _build_stage_context(self, stage: str, system_prompt: str, access: ReviewStageAccess, context: BaseAgentContext) -> BaseAgentContext: ...
    def _build_final_result(self, producer: AgentResult, output: str, structured: Any, outcomes: Sequence[_StageOutcome], metadata: Mapping[str, Any] | None) -> AgentResult: ...
```

Private `_StageOutcome` and `_CriticOutcome` dataclasses retain parsed output, calls, token/model-call counts, elapsed time, error type, and stage identifiers within orchestration; they are not public exports.

#### Logic / Algorithm

1. Record `system_prompt` and the producer slot; run the producer through `runtime._arun_once` beneath a producer span.
2. Preflight candidate size, source artifact names, all allow-list references, and parallel critic tool opt-in before launching review stages.
3. Serialize one critic envelope with `json.dumps` and reuse that immutable string for every critic.
4. Record the fan-out slot, create one coroutine per critic, wrap each in its timeout, and await `gather(..., return_exceptions=True)`.
5. Record the barrier slot only after gather returns. Convert results to index-ordered outcomes and apply `REQUIRE_ALL`/quorum policy.
6. Parse successful critic outputs, assign canonical IDs, and create the adjudicator envelope.
7. Record the adjudication slot; run the adjudicator in a fresh stage runtime and validate complete referential integrity.
8. Deterministically build accepted findings. If none exist, record `revision_skipped` and return the producer result with algorithm metadata.
9. Otherwise build a new revision envelope from the original task, candidate, accepted findings, and revision artifacts; record the revision slot; run the fresh worker; validate applied IDs and user structured output.
10. Build deterministic `calls`, preserve producer top-level metadata, add sanitized algorithm metadata, and return.

Each stage runtime is constructed with the default/no-op context algorithm, `output_schema=None`, `context_manager=None`, a `NullRecorder`, a fresh run state, an exact `runtime.user_tools.subset(...)`, the same permission policy and tracer, bounded `AgentRuntimeConfig`, an empty `MiddlewarePipeline`, and `include_internal_tools=False`. Its context is built from the algorithm role prompt and explicit JSON message only, with `agentic_loop=False`; explicitly permitted user-tool calls still use the bounded normal tool-call/result loop. The producer's `BaseAgentContext` is used solely for explicitly named artifact lookup and is never inherited wholesale.

The runtime change is backward-compatible: `AgentRuntime.__init__` gains `include_internal_tools: bool = True`. Existing callers retain the internal completion tool; isolated critique, adjudication, and revision stages pass `False` so no undeclared tool crosses the boundary.

#### Edge Cases & Error Handling

- A producer failure propagates exactly as it does today; no reviewers run.
- Critic exceptions/timeouts are collected through the barrier. Failure metadata contains critic ID and exception type, not raw exception text that might include sensitive payloads.
- Cancellation of the parent cancels fan-out and is re-raised; it is never converted into a quorum result.
- An unexpected stage result without the required valid payload is treated as a stage failure.
- A stage model override creates a text runner through `ModalityDetector`; absent override reuses the caller's runner handle.
- Stage tool calls execute under the original permission policy in addition to the narrower tool subset. An allow-list never grants permission the producer lacked.
- `RETURN_CANDIDATE` after adjudication/revision failure cannot undo completed tool calls. Metadata reports `degraded_adjudication_failure` or `degraded_revision_failure`.
- Recorder appends occur outside concurrent critic tasks, avoiding nondeterministic slot order and recorder thread-safety assumptions.
- Stage spans close on `BaseException`, matching existing runtime tracing behavior.

### 6.3 Preset, algorithm container, and dispatcher wiring

**File(s):** `vidbyte/context/algorithms/tool_results.py`, `vidbyte/context/algorithms/__init__.py`, `vidbyte/context/presets.py`, `vidbyte/agents/algorithms/__init__.py`, `vidbyte/agents/context_algorithms.py`
**Type:** Modified

#### What it does

Registers the public config in the one-active-algorithm container and routes configured runs to the new runtime adapter.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    # Existing fields remain unchanged.
    critique_adjudicate_revise: CritiqueAdjudicateReviseAlgorithm | None = None

class ContextWindowPresets:
    @property
    def critique_adjudicate_revise(self) -> ContextWindowAlgorithm: ...

class AgentRuntimeContextAlgorithms:
    def detect_algorithm(self) -> str | None: ...
    def return_algorithm(self) -> ReflexionRuntimeAlgorithm | MultiProviderAgenticGraderRuntimeAlgorithm | CritiqueAdjudicateReviseRuntimeAlgorithm | None: ...
```

#### Logic / Algorithm

1. Import and export public config/contracts.
2. Include the new field in `ContextWindowAlgorithm.__post_init__` active-algorithm counting.
3. Add the preset property with default config.
4. Detect the new field and return its runtime adapter.
5. Keep inner-loop dispatch unchanged.

#### Edge Cases & Error Handling

- Unknown preset strings still raise `ValueError`.
- Configuring this field with Reflexion, grader, or an inner-loop algorithm still raises the existing at-most-one error.
- No changes occur on the default path.

### 6.4 Prompt catalog assets

**File(s):** `vidbyte/prompts/prompts/critique_adjudicate_revise/critique_adjudicate_revise.json`, `vidbyte/prompts/prompts/critique_adjudicate_revise/critic.md`, `vidbyte/prompts/prompts/critique_adjudicate_revise/adjudicator.md`, `vidbyte/prompts/prompts/critique_adjudicate_revise/reviser.md`, `vidbyte/lib/enums/prompts.py`
**Type:** New files and modified enum

#### What it does

Supplies inspectable role prompts and strict JSON contracts through the existing auto-discovered package-data catalog.

#### Interface / API

```python
class Prompt(str, Enum):
    CRITIQUE_ADJUDICATE_REVISE_CRITIC = "critique_adjudicate_revise.critic"
    CRITIQUE_ADJUDICATE_REVISE_ADJUDICATOR = "critique_adjudicate_revise.adjudicator"
    CRITIQUE_ADJUDICATE_REVISE_REVISER = "critique_adjudicate_revise.reviser"
```

#### Logic / Algorithm

1. Critic prompt treats the JSON envelope as untrusted evidence, asks for concrete actionable defects only, requires grounded evidence, and forbids scratch/peer assumptions.
2. Adjudicator prompt requires complete ID coverage, canonical selection, deduplication, unsupported rejection, and contradiction resolution. It explicitly forbids accepted-content prose.
3. Reviser prompt says to use every accepted finding exactly once, preserve correct/unaffected candidate material, avoid unrelated rewrites, and output only the strict revision object.
4. The JSON descriptor maps all three Markdown assets and source URLs.

#### Edge Cases & Error Handling

- Prompt enum/asset mismatch fails through existing catalog validation.
- Stage output with prose outside the required JSON is rejected by the strict parser.
- Prompt overrides change instructions only; they cannot weaken runtime referential-integrity or allow-list checks.

### 6.5 Recorder template

**File(s):** `vidbyte/lib/templates/critique_adjudicate_revise.py`, `vidbyte/lib/templates/__init__.py`, `skills/vidbyte-sdk/context-window-templates.md`
**Type:** New template and modified exports/docs

#### What it does

Defines the canonical successful slot sequence without depending on critic completion order.

#### Interface / API

```python
class CritiqueAdjudicateReviseContextWindowTemplate(ContextWindowTemplate):
    def __init__(self, *, revision_expected: bool = True) -> None: ...
```

#### Logic / Algorithm

1. Always expect system, producer, fan-out, barrier, and adjudication slots.
2. Append revision when `revision_expected=True`; otherwise append revision-skipped.
3. Document instrumentation points and the rule that per-critic completion is tracing/metadata, not a recorder slot.

#### Edge Cases & Error Handling

- Failure traces include a failure slot and are intentionally outside the successful template; callers inspect recorder events directly for failure diagnosis.
- `revision_expected=False` models a valid all-rejected/no-findings outcome, not a stage failure.

### 6.6 Public exports and usage documentation

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/__init__.py`, `vidbyte/context/README.md`, `README.md`
**Type:** Modified

#### What it does

Makes the config/contracts discoverable and documents the preset, isolation guarantees, defaults, cost, failure behavior, allow-lists, and side-effect warning.

#### Interface / API

```python
from vidbyte import CritiqueAdjudicateReviseAlgorithm, ReviewStageAccess
from vidbyte import ContextWindow

agent = Agent(
    name="reviewed-worker",
    system_prompt="Complete the task and satisfy every stated requirement.",
    provider="openai",
    model_name="gpt-4.1",
    algorithm=ContextWindow.preset.critique_adjudicate_revise,
)
```

Custom access remains explicit:

```python
algorithm = ContextWindowAlgorithm(
    name="critique_adjudicate_revise",
    critique_adjudicate_revise=CritiqueAdjudicateReviseAlgorithm(
        critic_access=ReviewStageAccess(allowed_artifact_names=("requirements",)),
        revision_access=ReviewStageAccess(allowed_artifact_names=("requirements",), allowed_tool_names=("apply_patch",)),
    ),
)
```

#### Logic / Algorithm

1. Re-export the algorithm, access/failure policy types, evidence, raw finding, and accepted finding from `vidbyte.context` and the root package.
2. Add a concise context README family entry.
3. Add root README usage plus the warning that parallel stage tools and revision tools can cause side effects.

#### Edge Cases & Error Handling

- Documentation states that empty allow-lists are the default and that artifact names refer only to `BaseContext.artifacts`.
- Documentation does not imply that returning the original candidate rolls back prior actions.

---

## 7. Data Model Changes

### 7.1 In-memory review provenance types

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class FindingEvidence:
    evidence_id: str
    source_kind: str
    source_name: str
    locator: str
    excerpt: str

@dataclass(frozen=True, slots=True)
class CriticFinding:
    finding_id: str
    critic_id: str
    category: str
    severity: str
    claim: str
    recommendation: str
    evidence: tuple[FindingEvidence, ...]

@dataclass(frozen=True, slots=True)
class AcceptedFinding:
    accepted_id: str
    canonical_finding_id: str
    source_finding_ids: tuple[str, ...]
    category: str
    severity: str
    claim: str
    recommendation: str
    evidence: tuple[FindingEvidence, ...]
```

**Migration strategy:** N/A - these are ephemeral immutable Python values stored in one `AgentResult`; no database or serialized session schema changes are required. Session/checkpoint metadata may carry the additive algorithm summary as ordinary mappings.

---

## 8. API Changes

N/A - no HTTP API endpoints are added or modified.

The additive public Python API consists of:

- `ContextWindow.preset.critique_adjudicate_revise`.
- `CritiqueAdjudicateReviseAlgorithm`, `ReviewStageAccess`, `CriticFailurePolicy`, `StageFailurePolicy`, `FindingEvidence`, `CriticFinding`, and `AcceptedFinding` exports.
- Three new `Prompt` enum members and one template export.
- Additive `AgentResult.metadata["critique_adjudicate_revise"]` for configured runs only.

Error cases are Python exceptions or explicitly configured degraded results:

| Condition | Behavior |
|-----------|----------|
| Invalid static config/allow-list shape | `ConfigurationError` before execution |
| Missing runtime artifact/tool name | `ConfigurationError` during preflight, before critic launch |
| Producer failure | Existing exception/result behavior propagates |
| Critic failures below policy | `AgentExecutionError` after full barrier |
| Malformed/ungrounded critic output | Critic failure, then critic policy applies |
| Invalid adjudication references | `AgentExecutionError`, or exact producer candidate with explicit adjudication fallback |
| Invalid/incomplete revision | `AgentExecutionError`, or exact producer candidate with explicit revision fallback |

---

## 9. File Change Manifest

Complete implementation manifest for the approval-gated phase:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-window-critique-adjudicate-revise.md` | This design doc |
| CREATE | `vidbyte/context/algorithms/critique_adjudicate_revise.py` | Public config, typed findings/evidence, strict parsers, provenance validation |
| CREATE | `vidbyte/agents/algorithms/critique_adjudicate_revise.py` | Producer/critic/adjudicator/revision orchestration and isolated stage runtimes |
| CREATE | `vidbyte/prompts/prompts/critique_adjudicate_revise/critique_adjudicate_revise.json` | Prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/critique_adjudicate_revise/critic.md` | Critic role and strict finding schema |
| CREATE | `vidbyte/prompts/prompts/critique_adjudicate_revise/adjudicator.md` | Referential adjudication role and strict disposition schema |
| CREATE | `vidbyte/prompts/prompts/critique_adjudicate_revise/reviser.md` | Accepted-findings-only revision role and strict output schema |
| CREATE | `vidbyte/lib/templates/critique_adjudicate_revise.py` | Deterministic outer-stage recorder template |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add config field and one-active-algorithm validation |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public algorithm/contracts |
| MODIFY | `vidbyte/context/presets.py` | Add preset property |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export runtime adapter |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect and dispatch return-level adapter |
| MODIFY | `vidbyte/agents/runtime.py` | Add the backward-compatible `include_internal_tools` isolation option |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add three prompt keys |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export template |
| MODIFY | `vidbyte/context/__init__.py` | Re-export public algorithm/contracts |
| MODIFY | `vidbyte/__init__.py` | Root re-exports |
| MODIFY | `vidbyte/context/README.md` | Document algorithm family and trust boundary |
| MODIFY | `README.md` | Add public usage, cost, failure, and side-effect guidance |
| MODIFY | `skills/vidbyte-sdk/context-window-templates.md` | Document slots and instrumentation points |

Manifest totals: **8 created, 13 modified, 0 deleted**.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `asyncio` | Standard library, Python `>=3.11` | Concurrent critic fan-out, per-stage timeouts, cancellation | Tool/model cancellation is best-effort; side effects already completed cannot be rolled back |
| Python `json` / `dataclasses` | Standard library | Strict envelopes and immutable provenance types | Semantic support still requires model judgment after structural checks |
| `Tools.subset` / `AgentRuntime` | In-repo | Exact tool allow-lists and isolated stage loops | Custom tool objects may not be concurrency-safe; parallel critic tools require explicit opt-in |
| `Prompts` catalog | In-repo package assets | Critic/adjudicator/reviser instructions | Enum/asset drift prevents catalog load; packaging must include nested assets |
| Configured LLM provider(s) | Existing runner or explicit stage provider/model | Producer, critique, adjudication, revision | Added cost/latency, provider failure, nondeterminism, judge bias, sensitive trace content |

No new third-party dependency or external service is introduced. Existing provider credentials and permission policies are reused.

---

## 11. Rollout & Deployment

- Ship as an additive opt-in preset; no feature flag is needed because existing agents remain on `default` unless configured.
- Deploy Python code and all three Markdown prompt assets in the same release. Existing `pyproject.toml` nested package-data patterns cover the new directory.
- This is not a breaking API change. Serialized code that explicitly names the new preset requires a release containing it; older releases will continue to reject the unknown name.
- Recommended initial rollout uses empty stage tool allow-lists, `REQUIRE_ALL`, and terminal `RAISE` policies. Enable stage tools only after confirming permission and side-effect behavior.
- Observe stage latency, timeout frequency, accepted/rejected counts, degraded statuses, and provider spend before widening use.
- Rollback removes the preset/field/exports/runtime adapter/prompts/docs. Existing default and other preset paths remain unchanged. Runs/checkpoints configured with the removed preset must be migrated back to `default` before rollback.

### Manual Verification

No test or verification script is added. During the implementation phase, manually verify with deterministic fake runners and existing commands:

1. Hold each critic on an async event, assert all critics started, then release them and assert adjudication starts only after the barrier.
2. Put unique sentinels in every excluded producer context field and inspect captured stage requests to confirm no sentinel crosses.
3. Return overlapping, unsupported, and contradictory findings; verify accepted IDs are copied from canonical sources and every raw ID has one disposition.
4. Return an unknown judge ID and verify revision is never called.
5. Return zero accepted groups and verify producer output/structured data are byte-for-byte preserved.
6. Exercise critic timeout under `REQUIRE_ALL` and `REQUIRE_QUORUM`; inspect stable critic ordering and sanitized failure metadata.
7. Configure distinct artifact/tool allow-lists for each stage and verify no unlisted name/schema/content appears.
8. Configure an output schema; verify revised valid output populates `structured` and invalid revision follows the configured failure policy.
9. Inspect recorder slots and semantic span parents for revised and revision-skipped outcomes.
10. Run `python -m compileall vidbyte`, `python -m unittest discover -s tests`, and package build/twine checks as existing repository regression gates; these commands validate the repo but are not new feature tests/scripts.

---

## 12. Open Questions

- [ ] Should a future version add an explicit public field for caller-authorized producer instructions? Version 1 sends only the exact user message; requirement text from a private producer system prompt remains private unless the caller deliberately exposes it through an allowlisted artifact.
- [ ] Confirm whether opt-in `RETURN_CANDIDATE` terminal failure policies should ship publicly in the first release. Defaults remain fail-closed, and any fallback is explicitly degraded in metadata.
- [ ] Confirm whether non-empty parallel critic tool allow-lists should be supported behind `allow_parallel_critic_tools`, or deferred until the SDK has a formal concurrency-safety/side-effect declaration on `BaseTool`.

---

## 13. Alternatives Considered

### Alternative 1: Send raw critic findings directly to the revision worker

- What: Skip adjudication and concatenate all critique text into a revision prompt.
- Why rejected: Violates the requested quarantine, amplifies duplicate/unsupported/contradictory criticism, and gives inaccurate critiques direct control over the final candidate.

### Alternative 2: Let the adjudicator synthesize accepted allegation prose

- What: Judge writes a clean consolidated critique in its own words.
- Why rejected: Referential IDs alone would not prevent new claims from entering the revision boundary. Copying canonical source fields makes non-invention mechanically enforceable.

### Alternative 3: Reuse producer context with `dataclasses.replace`

- What: Replace only the system prompt on the producer `BaseAgentContext` for each stage.
- Why rejected: It would retain history, memory, metadata, responses, tool calls, file paths, artifacts, and context items, violating the core isolation contract.

### Alternative 4: Run critics serially

- What: Await one critic and then start the next while withholding findings.
- Why rejected: It preserves informational isolation but not the requested same-time review, and makes latency the sum of critic durations.

### Alternative 5: Use an inner-loop `after_tool_calls` algorithm

- What: Inject periodic critique/adjudication primitives during one producer run.
- Why rejected: The requested workflow evaluates a completed candidate and returns a revised candidate. Inner-loop hooks operate before final result construction and would expose review material to the producer.

### Alternative 6: Use one shared child runtime for all critics

- What: Reuse one stage runtime/context and invoke it concurrently.
- Why rejected: Shared message/run/context state creates accidental information and race channels. Fresh runtimes make isolation an object-graph property.

### Alternative 7: Retry failed stages automatically

- What: Replay critics, adjudication, or revision after timeout/parse failure.
- Why rejected: Stage tools may already have caused side effects, and hidden algorithm retries make cost and call semantics difficult to reason about. Provider/runner transport behavior remains outside this orchestration layer.
