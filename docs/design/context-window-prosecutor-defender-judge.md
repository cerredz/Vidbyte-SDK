# Design Doc: Prosecutor/Defender/Judge Context-Window Algorithm

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

This feature adds a `prosecutor_defender_judge` context-window algorithm to the Vidbyte SDK. A normal producer run first creates one immutable candidate. Three logically isolated review stages then execute in strict sequence: a prosecutor receives the original task, the exact candidate, and only explicitly permitted evidence/tools and emits typed allegations; a defender receives those exact allegations and must answer every allegation exactly once without adding unrelated defense claims; and a judge receives the candidate, the normalized allegations, their matching defenses, and only permitted evidence/tools and decides which allegation IDs survive. Version 1 is review/verdict-only: it preserves the producer's `AgentResult.output`, `structured`, `calls`, strategy name, and existing metadata, and attaches a bounded, typed debate verdict under `AgentResult.metadata["prosecutor_defender_judge"]`. It never revises or replaces the candidate.

---

## 2. Goals & Non-Goals

### Goals

- Expose `ContextWindow.preset.prosecutor_defender_judge` and support `ContextWindow.resolve_algorithm("prosecutor_defender_judge")`.
- Run exactly one normal producer pass followed by prosecutor, defender, and judge stages in that order.
- Build every review stage from a positive projection rather than by copying and scrubbing producer context.
- Prevent producer scratch reasoning, system prompt, history, provider messages, tool-call history, context primitives, memory, mutable `ContextManager`, run metadata, middleware state, and private invocation options from reaching any review stage.
- Give each stage its own explicit artifact and tool allowlists, optional provider/model, prompt, runtime budget, and timeout through immutable public configuration.
- Require typed, evidence-bearing allegations; assign stable SDK-owned allegation IDs; require an exact one-to-one defense and decision for every allegation ID.
- Structurally prevent the defender from adding unrelated top-level defense claims and the judge from inventing new allegations.
- Preserve the exact producer candidate through all review stages and in the returned result.
- Derive the overall verdict deterministically from the judge's per-ID decisions rather than trusting a redundant free-form verdict.
- Bound all review inputs, outputs, metadata, accounting, and trace attributes without silently truncating any input that is claimed to have been reviewed exactly.
- Fail closed by default on stage failure, timeout, malformed structured output, or referential-integrity failure; allow an explicit marked `return_candidate` policy.
- Preserve producer tools, permissions, middleware, tracing, output contracts, structured output, and accounting during the producer pass.
- Provide Markdown-backed prompts, prompt enum entries, public exports, a preset, deterministic recorder/template slots, documentation, and manual-verification criteria.
- Remain opt-in and backward compatible when the algorithm is not configured.

### Non-Goals

- No candidate revision, retry, repair, or second producer call. Critique-adjudicate-revise owns the workflow that feeds accepted findings back to a worker.
- No independent-critic-only mode, parallel panel, specialist panel, finding deduplication panel, or multi-candidate tournament.
- No prosecutor access to producer scratch reasoning or private history, even if that context might make allegations easier to generate.
- No free-form multi-round debate. Version 1 has one prosecutor report, one allegation-by-allegation defense report, and one judge report.
- No new allegations from the defender or judge. A judge rationale may explain a decision about an existing allegation but cannot create another finding record.
- No aggregation of reviewer calls into producer `AgentResult.calls` or producer top-level `metadata["tool_calls"]`.
- No implicit inheritance of producer artifacts, tools, file paths, MCP connections, sessions, agent-bound tools, middleware, output schema, context-manager state, or provider options.
- No mutating review tools. Version 1 accepts only allowlisted tools classified `SAFE` or `READ`; `WRITE` and `EXECUTE` tools are rejected even if named.
- No claim that an LLM judge is a truth oracle. The report is a model-produced, evidence-linked review verdict with provenance.
- No database, persistence format, migration, HTTP endpoint, third-party dependency, test file, or verification script.
- No implementation on the current user branch. Implementation begins only after explicit approval and isolated-worktree setup.

---

## 3. Background & Context

### Research basis

The original AI-safety debate proposal uses two agents making opposed, bounded statements followed by a judge selecting which side supplied more true and useful information. It treats the judge as the final decision-maker and explicitly notes that practical success is empirical rather than guaranteed: [AI safety via debate](https://arxiv.org/abs/1805.00899). This SDK design is a one-round, fixed-role adaptation for reviewing a completed artifact, not an implementation of debate training or the paper's full zero-sum game.

Later empirical work found that debate can help weaker model and human judges select truthful answers under information asymmetry, supporting the value of exposing both an allegation and its rebuttal to the judge rather than sending criticism directly to the producer: [Debating with More Persuasive LLMs Leads to More Truthful Answers](https://arxiv.org/abs/2402.06782). Broader scalable-oversight experiments found that debate's benefit varies by task and information asymmetry and can be mixed against direct judging, so this design publishes provenance, evidence, and per-allegation decisions rather than presenting a single opaque score as ground truth: [On scalable oversight with weak LLMs judging strong LLMs](https://arxiv.org/abs/2407.04622).

LLM judges also exhibit position, verbosity, and self-enhancement biases. A fixed, typed transcript; one defense per allegation; SDK-assigned IDs; no free-form final finding list; and deterministic verdict derivation reduce avoidable degrees of freedom, although they do not eliminate model bias: [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685).

### Repository audit

The implementation source of truth is clean `main` at commit `213d337` in `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-main-job-applier`. The user-facing `C:\Users\422mi\vidbyte-repos\vidbyte-sdk` checkout is on a dirty feature branch with many unrelated untracked design artifacts; this document is the only file this phase creates there, and all other user files must remain untouched.

Clean `main` is a Python 3.11+ SDK using frozen/slotted dataclasses for public runtime configuration, Pydantic v2 for provider-native structured-output contracts, `asyncio` for orchestration, and no dependency beyond the existing `pydantic` and `httpx` requirements. Context-window presets resolve through `ContextWindowPresets`; `ContextWindowAlgorithm` enforces at most one attached runtime algorithm; and `AgentRuntimeContextAlgorithms` dispatches return-level algorithms before the generic direct loop.

The current attached algorithms have two relevant shapes. Inner-loop algorithms implement `after_tool_calls(...)` and mutate `ContextManager` during one producer run. Return-level algorithms such as Reflexion and the multi-provider grader wrap one or more complete calls and return an `AgentResult`. Prosecutor/Defender/Judge is return-level because all review activity begins only after the producer candidate is final and because version 1 must not inject review text back into the producer's context window.

`AgentRuntime._arun_once(...)` is the correct producer path: it retains the ordinary model/tool loop, permission checks, middleware, output contract, structured output, tracing, token accounting, and stop semantics. It is not safe to reuse the producer runtime for a reviewer because that runtime owns the producer tool catalog, middleware pipeline, context manager, output schema, recorder, and algorithm state. Each review stage therefore uses a fresh `AgentRuntime`, a fresh allowlisted tool catalog, a fresh `BaseAgentContext`, empty invocation options, its own runtime limits, and the default context-window algorithm.

The generic runtime currently adds the internal `isDone` tool to every tool catalog. That violates an exact stage allowlist, so the design adds a backward-compatible `include_internal_tools: bool = True` constructor option. Isolated review runtimes pass `False` and use final-response stop behavior plus explicitly allowlisted tools only.

The unmerged `feat/devils-advocate-context-window-algorithm` branch was inspected as family precedent, but it is an inner-loop anticipatory-reflection design and is not a source dependency. Its useful conventions are frozen public configs, prompt-catalog assets, preset/dispatcher/export wiring, template slots, bounded metadata, and rebase-time preservation of other algorithm fields. Completed Independent Critic and Specialist Panel design docs were also inspected for shared vocabulary and isolation invariants: producer candidate, allowlist-built projection, fresh reviewer runtime, candidate preservation, stage-local accounting, and review-only metadata. If one of those features lands first, implementation should reuse an already-merged isolation helper or internal-tool opt-out rather than duplicate it, while keeping this approved protocol unchanged.

### Information-flow invariant

For a producer result `P`, prosecutor `A`, defender `D`, and judge `J`, the SDK-managed model-visible sets are:

```text
visible(A) = {
  prosecutor instructions,
  original_task,
  exact producer_candidate,
  prosecutor-allowlisted artifact contents,
  prosecutor-allowlisted tool schemas and their stage-local results
}

visible(D) = {
  defender instructions,
  original_task,
  exact producer_candidate,
  normalized allegations with SDK-owned IDs,
  defender-allowlisted artifact contents,
  defender-allowlisted tool schemas and their stage-local results
}

visible(J) = {
  judge instructions,
  original_task,
  exact producer_candidate,
  normalized allegations,
  exactly matching normalized defenses,
  judge-allowlisted artifact contents,
  judge-allowlisted tool schemas and their stage-local results
}
```

Every set excludes the producer's private/system/history channels and the raw conversational or tool transcript of earlier review stages. Only normalized structured stage outputs cross a stage boundary. Evidence copied by a prosecutor or defender into its typed report becomes explicitly visible downstream; this is intentional protocol data, not implicit context inheritance.

An explicitly allowlisted custom tool is an authority boundary. The SDK can guarantee that it does not pass producer-private context to that tool, rejects known bound/live/mutating tool types, applies the producer's permission policy, and exposes only the named tool. It cannot guarantee that a developer-authored tool does not reveal information from its own closure or external service.

---

## 4. Requirements

### Functional Requirements

1. `ContextWindow.preset.prosecutor_defender_judge` must return a `ContextWindowAlgorithm` named `"prosecutor_defender_judge"` containing a default `ProsecutorDefenderJudgeAlgorithm`.
2. `ContextWindow.resolve_algorithm("prosecutor_defender_judge")` must resolve that preset; unknown names must continue to raise `ValueError`.
3. `ProsecutorDefenderJudgeAlgorithm` and `DebateStageSettings` must be frozen slots dataclasses and validate all limits, enums, tuples, provider/model pairs, prompt overrides, prompt placeholders, metadata keys, and stage settings at construction time with `ConfigurationError`.
4. `ProsecutorDefenderJudgeFailurePolicy` must expose `RAISE = "raise"` and `RETURN_CANDIDATE = "return_candidate"`; the default must be `RAISE`.
5. Default prosecutor, defender, and judge settings must inherit the producer's current provider/runner only as a stateless invocation transport, expose zero artifacts and zero tools, and use bounded stage-local runtime budgets and timeouts.
6. The producer stage must call `self.runtime._arun_once(...)` exactly once with the original message, original `BaseAgentContext`, copied original options, original middleware/runtime state, and active trace context.
7. The reviewed candidate must be exactly `producer_result.output`. It must not be normalized, summarized, repaired, or truncated. If the original task or candidate exceeds its configured exact-input limit, the review must follow the failure policy rather than claim coverage of a truncated value.
8. Producer `output`, `strategy_name`, `calls`, `structured`, and all existing metadata must remain unchanged in the successful returned result except for adding/replacing `metadata["prosecutor_defender_judge"]`.
9. The runtime adapter must execute prosecutor, defender, and judge strictly sequentially. A later stage cannot start before the previous stage has completed, validated, normalized, and passed referential-integrity checks.
10. Each review stage must use a new `AgentRuntime` instance with default context-window behavior, a new middleware pipeline, `context_manager=None`, no inherited producer output contract, no inherited producer output schema, no inherited producer recorder state, and `include_internal_tools=False`.
11. Each stage context must be constructed from a new `BaseAgentContext`, never `dataclasses.replace(producer_context, ...)`. Its `history`, `file_paths`, `run_metadata`, `tool_calls`, `responses`, `memory`, `metadata`, and `context_items` must be empty, and `agentic_loop=False` must avoid instructions for an unavailable internal completion tool while retaining the bounded explicit user-tool call/result loop.
12. Review stages must not receive the producer's system prompt. Each receives only its algorithm-owned prompt-catalog system prompt or explicit stage prompt override.
13. Review stage invocation options must start from `{}`. Producer `messages`, `system`, `tools`, `response_format`, sampling settings, provider-private fields, mutable option values, and other options must not cross the boundary. The stage runtime may add its own tool schemas and response format.
14. The prosecutor prompt payload must contain exactly `original_task`, `candidate`, and `permitted_artifacts`. The defender payload must contain exactly `original_task`, `candidate`, `allegations`, and `permitted_artifacts`. The judge payload must contain exactly `original_task`, `candidate`, `allegations`, `defenses`, and `permitted_artifacts`.
15. Payloads must be serialized as JSON using explicit delimiters that label candidate/artifact data as untrusted evidence, not instructions. JSON escaping is transport encoding only; exact task, candidate, artifact, allegation, and defense values must remain semantically unchanged.
16. `artifact_names` in each `DebateStageSettings` must select only exact names from `producer_context.artifacts`. Unknown or ambiguous duplicate names must fail preflight. No producer file path, memory, response, metadata, context item, or context-manager primitive may be inferred as an artifact.
17. Artifact transport must include only `name`, `artifact_type`, and exact `content`; producer artifact metadata must not cross the boundary. Per-artifact and per-stage total size limits must be checked before invocation, and oversize inputs must fail rather than truncate.
18. `tool_names` in each stage must select an exact subset of `runtime.user_tools`; unknown names must fail preflight and no unlisted tool may appear in stage context, provider schemas, runtime lookup, accounting, or metadata.
19. A selected tool must be classified `ToolPermission.SAFE` or `ToolPermission.READ`. `WRITE` and `EXECUTE` tools, MCP attachment/bridge tools, agent delegation tools, fork tools, session-bound tools, context-manager-bound tools, dynamic attachment tools, and any other known live-parent binding must be rejected with an actionable error.
20. A safe selected tool exposing `clone_for_fork()` must be cloned before stage use. Standalone tools without a clone method may be reused only as explicitly granted capabilities; the stage never binds producer context to them. The producer's `PermissionPolicy` must still govern every stage tool call.
21. If a stage's `provider` and `model` are absent, it must use the incoming `RunnerHandle` with a fresh runtime/context/options. If either is supplied, both are required and the stage must create a fresh text runner through `ModalityDetector` after provider/model validation.
22. Every stage must execute inside its own `asyncio.timeout(stage.timeout_seconds)` boundary. A timeout must cancel and await the stage invocation before applying the configured failure policy.
23. The prosecutor must return provider-native structured output validated as `ProsecutorReportPayload`. The model payload may contain a bounded summary and zero to `max_allegations` typed allegations, but it must not supply authoritative IDs.
24. Every prosecutor allegation must include bounded `severity`, `category`, `claim`, `candidate_excerpt`, `evidence`, and `recommended_fix` fields. Evidence must contain one or more typed citations identifying `original_task`, `candidate`, an explicitly permitted artifact, or a stage-local permitted tool as its source, plus a bounded excerpt/support explanation.
25. An allegation lacking evidence, referring to an unpermitted source name, or exceeding any field/report limit must invalidate the prosecutor stage. Every citation excerpt must be an exact substring of its named source body: the original task, candidate, permitted artifact content, or output of the named prosecutor-stage tool call. The allegation's `candidate_excerpt`, when non-empty, must also be an exact candidate substring. Missing-requirement allegations may use the original task as evidence and may leave `candidate_excerpt` empty.
26. After prosecutor validation, the SDK must assign immutable IDs in report order using `ALG-001`, `ALG-002`, and so on. IDs and the normalized allegation content must not change in later stages.
27. The defender must receive only the normalized allegation records, not a raw prosecutor assistant response, prosecutor system prompt, prosecutor tool transcript, or free-form prosecutor summary.
28. The defender must return `DefenderReportPayload` containing exactly one `DefenseResponsePayload` for every allegation ID and no extra IDs. The SDK must reject missing, duplicate, unknown, or reordered IDs; canonical allegation order is required.
29. Every defense response must contain only `allegation_id`, `position` (`concede`, `contest`, or `partial`), a bounded allegation-specific response, and bounded typed evidence. Pydantic `extra="forbid"` and the fixed list shape must prevent unrelated top-level defense claims.
30. Defense evidence may cite the original task, candidate, the defender's permitted artifacts/tools, or the matching allegation. Artifact/tool source names must be permitted for the defender stage, and every excerpt must be an exact substring of the named source body or stage-local tool output. An empty response, a citation to a different allegation ID, or any other source-integrity violation must invalidate the defender stage.
31. The judge must receive only the normalized allegations and matching defenses, not raw prosecutor/defender conversations, prompts, model metadata, or tool transcripts. It must receive every allegation-defense pair in canonical allegation order.
32. The judge must return `JudgeReportPayload` containing exactly one `JudgeDecisionPayload` for every allegation ID and no extra IDs. Missing, duplicate, unknown, or reordered IDs must invalidate the judge stage.
33. Every judge decision must contain only `allegation_id`, `decision` (`survives` or `rejected`), `reason_code`, and a bounded rationale grounded in the allegation, matching defense, candidate, task, or permitted evidence. The schema must contain no field where the judge can author a new allegation, replacement claim, or fix.
34. Judge `reason_code` must be one of `supported_unrebutted`, `supported_after_rebuttal`, `conceded`, `unsupported`, `rebutted`, `duplicate`, or `out_of_scope`. A surviving decision may use only `supported_unrebutted`, `supported_after_rebuttal`, or `conceded`; a rejected decision must use one of the remaining codes.
35. An empty allegation set is valid. The defender and judge stages must still run and return empty response/decision lists, preserving the three-stage audit trail and making any invented ID a schema/integrity failure.
36. The SDK must derive `surviving_allegation_ids` from judge decisions, preserving allegation order. It must derive `verdict="pass"` when the set is empty and `verdict="needs_changes"` when one or more allegations survive. The judge must not supply a competing overall verdict.
37. Successful metadata must use a versioned, JSON-safe shape and include `status="reviewed"`, `review_only=True`, `candidate_revised=False`, `candidate_sha256`, verdict, counts, surviving IDs, bounded normalized allegations/defenses/decisions, stage provider/model/tool/artifact provenance, stop reasons, duration, iteration/model/tool/token accounting, and configured algorithm metadata.
38. Stage tool calls and result bodies must not be appended to producer `calls` or top-level producer `tool_calls`. Bounded stage call summaries may include tool names, states, and counts under that stage's metadata, but raw arguments/results remain in tracing subject to existing trace policy.
39. Stage reports must be bounded by count, per-field, per-citation, and total serialized-character limits. Inter-stage values must be rejected if oversized rather than truncated so the defender and judge always receive the exact normalized records described by metadata.
40. Under `ProsecutorDefenderJudgeFailurePolicy.RAISE`, any preflight, timeout, invocation, parsing, validation, evidence, or referential-integrity failure must raise `AgentExecutionError` naming the failed stage and chaining the original exception.
41. Under `RETURN_CANDIDATE`, a failure must return the producer result unchanged except for a bounded metadata object with `status="review_failed"`, `reviewed=False`, `failed_stage`, safe error type/category/message, candidate hash, stage completion statuses, and allowlist/isolation accounting. It must not emit a verdict or imply that later stages ran.
42. `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, and other cancellation/process-level `BaseException` values must always propagate regardless of failure policy. Cancellation must close active trace spans and stage runtime cleanup before propagation.
43. The review output must never be sent back to the producer, trigger another producer call, modify `ContextManager`, or alter producer output/structured data.
44. Recorder slots must be deterministic: `system_prompt`, `prosecutor_defender_judge_candidate`, `prosecutor_defender_judge_prosecutor`, `prosecutor_defender_judge_defender`, `prosecutor_defender_judge_judge`, and, only after a review-stage failure, `prosecutor_defender_judge_failure`.
45. The existing dispatcher must create an `algorithm.prosecutor_defender_judge` span. The adapter must create child spans for `producer`, `prosecutor`, `defender`, and `judge`; stage model/tool/parser spans must remain under their stage span when semantic tracing is active.
46. Algorithm-specific stage trace attributes must be content-free. They may contain stage name, opaque run/reviewer IDs, provider/model labels, candidate hash/length, permitted resource names, counts, decision IDs, timing, and status, but never task/candidate/artifact text, tool arguments/results, allegations, defenses, decisions, report summaries, provider response text, or raw exception bodies.
47. The prompt catalog must expose separate system and user prompt assets for prosecutor, defender, and judge, and all six prompts must be overrideable with validated required placeholders.
48. `ProsecutorDefenderJudgeContextWindowTemplate` must validate the successful fixed slot sequence and a canonical completed-stage prefix plus failure slot, including a resource-preflight failure before any review stage starts.

### Non-Functional Requirements

- **Isolation/security:** All three review contexts are allowlist-built. New fields added to `BaseAgentContext` remain excluded by default because review code constructs a new instance rather than copying producer state. Candidate and artifacts are explicitly labelled untrusted data to reduce prompt-injection risk.
- **Sequentiality:** At most one review stage is active. The defender cannot observe incomplete prosecutor output, and the judge cannot observe incomplete or unmatched defenses.
- **Latency:** Default overhead is three sequential model calls after the producer. Explicit safe/read tools may add calls within each stage's local caps. Default timeout is 120 seconds per stage.
- **Cost:** Default stage caps are `max_iterations=4`, `max_tokens=8000`, and `max_tool_calls=4`; total review cost is bounded by the sum of the three stage caps and provider enforcement limitations remain visible in metadata.
- **Reliability:** Exact-input size failures are explicit, stage state is run-local, mutable inputs are copied, structured outputs use strict schemas, referential integrity is checked between every stage, and fail-open behavior requires explicit configuration.
- **Observability:** Recorder slots, nested semantic spans, candidate hash, stage provenance, normalized transcript, survivor IDs, and safe failure metadata make the debate auditable without mixing review calls into producer accounting.
- **Backward compatibility:** New optional `ContextWindowAlgorithm` and `AgentRuntime` parameters default to current behavior. Existing presets, direct agents, imports, and results are unchanged.
- **No unconfigured overhead:** The new adapter and isolated-stage path are unreachable unless the preset/config is selected.
- **Context bounds:** Task, candidate, artifacts, allegations, and defenses that cross a stage boundary are exact or rejected. Only safe failure messages and display summaries may be truncated, with truncation flags.
- **Maintainability:** Protocol orchestration stays in its runtime adapter. The generic runtime change is limited to opting out of internal tools. Non-trivial logic uses classes with small semantic methods; every implementation function/method has a one-line signature and an immediate 1–2 line intent comment, per the approved workflow.

### Acceptance Criteria & Manual Verification

1. A successful default run performs one producer pass followed by prosecutor, defender, and judge in observable sequential order; no two review stages overlap.
2. Returned `output`, `strategy_name`, `calls`, and `structured` are equal to the producer result, and all pre-existing metadata keys/values remain intact.
3. Sentinel values placed in producer system prompt, history, memory, run metadata, context items, context-manager primitives, tool-call records, responses, and invocation options do not appear in any captured stage prompt, context, tool schema, or trace attribute.
4. Prosecutor input contains the exact task and candidate plus only prosecutor-allowlisted artifacts/tools. Defender input additionally contains exactly the normalized allegations. Judge input additionally contains exactly the matching defenses.
5. With empty allowlists, every stage has zero tools, including no internal `isDone` tool, and zero artifact contents.
6. Unknown/ambiguous artifacts, unknown tools, mutating/bound/live tools, oversize exact inputs, and candidate excerpt/source-integrity violations fail before the affected model call.
7. Captured invocation times prove prosecutor completion precedes defender start and defender completion precedes judge start.
8. The SDK assigns `ALG-001...` IDs. Missing, duplicate, reordered, or invented defense/decision IDs are rejected.
9. A defender output cannot add an unrelated top-level claim, and a judge output cannot add a new allegation field; Pydantic rejects extra fields.
10. Zero allegations produce empty defense and decision lists after all three stages and a deterministic `pass` verdict.
11. One or more `survives` decisions produce `needs_changes` and survivor IDs in allegation order; rejected allegations never appear in survivors.
12. Invalid stage JSON/structured output raises by default and returns a marked, no-verdict `review_failed` candidate only under explicit `RETURN_CANDIDATE`.
13. A stage timeout is attributed to that stage; cancellation propagates and leaves no active stage task or unclosed semantic span.
14. Stage-local tool accounting remains nested under review metadata and never changes producer calls/tool-call accounting.
15. Recorder/template validation passes for success and for failures at each of the three review stages.
16. After implementation, run `python -m compileall vidbyte` and the existing regression suite `python -m unittest discover -s tests`. No new test or verification file is added by this no-tests change.
17. Before opening the PR, manually inspect captured fake-runner payloads, structured records, traces, and result equality for the isolation, referential-integrity, timeout, and zero-allegation scenarios and record evidence in the handoff report.

---

## 5. High-Level Design

`ProsecutorDefenderJudgeRuntimeAlgorithm` is a return-level adapter. It calls the existing direct loop once to produce the candidate. It then resolves and validates stage-specific resources, constructs an immutable debate transcript, and runs three fresh stage runtimes in sequence. Each stage returns provider-native structured output, which is revalidated and normalized before it can become the next stage's input. The only final mutation is `dataclasses.replace(producer_result, metadata=merged_metadata)`; the producer candidate and public result fields remain authoritative.

The central design choice is an append-only, typed transcript with SDK-owned identity. The prosecutor proposes allegation content, but the SDK assigns IDs. The defender must return the same ordered ID set, and the judge must return it again. Pydantic `extra="forbid"`, exact-set/order validation, source validation, and deterministic verdict derivation constrain each role to its responsibility. Natural-language instructions still matter inside a response body, but the public data model offers no place for the defender or judge to append another finding.

Every stage runtime is a capability sandbox at the SDK-context level. It gets a stage prompt, a minimal JSON evidence payload, an allowlisted `Tools` catalog, inherited permission policy, local limits, and tracing. It does not inherit producer middleware or context. Earlier-stage raw conversations and tool records are not forwarded; only validated normalized records become downstream evidence.

```text
[Original task + producer BaseAgentContext]
                    |
                    v
          [normal _arun_once producer]
                    |
              AgentResult P
           candidate = P.output
                    |
                    v
       +--------------------------------+
       | fresh prosecutor runtime       |
       | task + candidate + allowed A/T |
       +--------------------------------+
                    |
       typed allegations; SDK assigns
              ALG-001 ... ALG-N
                    |
                    v
       +--------------------------------+
       | fresh defender runtime         |
       | task + candidate + allegations |
       | + defender-allowed A/T         |
       +--------------------------------+
                    |
       exactly one defense per ALG-ID
                    |
                    v
       +--------------------------------+
       | fresh judge runtime            |
       | candidate + allegation/defense |
       | pairs + judge-allowed A/T      |
       +--------------------------------+
                    |
       exactly one survives/rejected
              decision per ALG-ID
                    |
                    v
       derive pass / needs_changes
       attach bounded review metadata
                    |
                    v
       P.output / P.structured / P.calls
              remain unchanged
```

The protocol deliberately does not use `ContextManager` primitives. These reviews occur after candidate production and are not model-visible to the producer. `AgentResult.metadata` is the existing extension point for post-run review provenance, while the producer's `structured` field continues to belong to its configured output schema.

---

## 6. Detailed Design

### 6.1 Public algorithm and stage configuration

**File(s):** `vidbyte/context/algorithms/prosecutor_defender_judge.py`
**Type:** New file

#### What it does

Defines immutable public configuration, failure policy, prompt rendering, exact-input limits, stage budgets, resource allowlists, and provider/model overrides. It contains no runtime execution or mutable debate state.

#### Interface / API

```python
class ProsecutorDefenderJudgeFailurePolicy(str, Enum):
    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"

@dataclass(frozen=True, slots=True)
class DebateStageSettings:
    provider: str | None = None
    model: str | None = None
    artifact_names: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    max_iterations: int = 4
    max_tokens: int = 8000
    max_tool_calls: int = 4
    timeout_seconds: float = 120.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ProsecutorDefenderJudgeAlgorithm:
    prosecutor: DebateStageSettings = field(default_factory=DebateStageSettings)
    defender: DebateStageSettings = field(default_factory=DebateStageSettings)
    judge: DebateStageSettings = field(default_factory=DebateStageSettings)
    failure_policy: ProsecutorDefenderJudgeFailurePolicy = ProsecutorDefenderJudgeFailurePolicy.RAISE
    max_task_chars: int = 20000
    max_candidate_chars: int = 100000
    max_artifact_chars: int = 50000
    max_total_artifact_chars: int = 100000
    max_allegations: int = 20
    max_evidence_per_item: int = 8
    max_field_chars: int = 4000
    max_stage_report_chars: int = 100000
    max_failure_message_chars: int = 1000
    prosecutor_system_prompt: str | None = None
    prosecutor_prompt: str | None = None
    defender_system_prompt: str | None = None
    defender_prompt: str | None = None
    judge_system_prompt: str | None = None
    judge_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def render_prosecutor_prompt(self, payload_json: str) -> str: ...
    def render_defender_prompt(self, payload_json: str) -> str: ...
    def render_judge_prompt(self, payload_json: str) -> str: ...
```

All methods use one-line signatures and immediate intent comments. Prompt overrides must be nonblank and user-prompt overrides must contain `{payload_json}`. Provider and model are both absent or both present. Names are nonblank, unique tuples. Numeric safeguards have hard upper bounds to prevent accidental unbounded reports.

#### Logic / Algorithm

1. Normalize enum values and stage tuples in `__post_init__` without mutating the frozen instance.
2. Validate each stage's provider/model pair through existing provider/model registries when supplied.
3. Validate that resource names are unique and nonblank.
4. Validate positive runtime, timeout, field, artifact, count, report, and failure-message limits against documented safeguards.
5. Resolve default prompt text lazily from `Prompts()` and format only the single JSON payload placeholder.

#### Edge Cases & Error Handling

- One provider/model value without the other raises `ConfigurationError` before a run.
- Duplicate artifact/tool names are rejected rather than silently deduplicated.
- Empty prompt overrides and missing/unknown format placeholders fail at construction time.
- Mapping metadata must have string keys and is copied into result provenance only after JSON-safe normalization.

### 6.2 Typed debate payloads, transcript, and final report

**File(s):** `vidbyte/lib/dataclasses/prosecutor_defender_judge.py`
**Type:** New file

#### What it does

Defines strict Pydantic structured-output models and frozen SDK-owned transcript/report records. Model-authored payloads remain distinct from trusted provenance: the SDK, not the prosecutor model, owns allegation IDs, stage identity, candidate hash, and accounting.

#### Interface / API

```python
class EvidenceSource(str, Enum):
    ORIGINAL_TASK = "original_task"
    CANDIDATE = "candidate"
    ARTIFACT = "artifact"
    TOOL = "tool"
    ALLEGATION = "allegation"

class AllegationSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NOTE = "note"

class DefensePosition(str, Enum):
    CONCEDE = "concede"
    CONTEST = "contest"
    PARTIAL = "partial"

class JudgeDecision(str, Enum):
    SURVIVES = "survives"
    REJECTED = "rejected"

class JudgeReasonCode(str, Enum):
    SUPPORTED_UNREBUTTED = "supported_unrebutted"
    SUPPORTED_AFTER_REBUTTAL = "supported_after_rebuttal"
    CONCEDED = "conceded"
    UNSUPPORTED = "unsupported"
    REBUTTED = "rebutted"
    DUPLICATE = "duplicate"
    OUT_OF_SCOPE = "out_of_scope"

class EvidenceCitationPayload(BaseModel): ...
class ProsecutorAllegationPayload(BaseModel): ...
class ProsecutorReportPayload(BaseModel): ...
class DefenseResponsePayload(BaseModel): ...
class DefenderReportPayload(BaseModel): ...
class JudgeDecisionPayload(BaseModel): ...
class JudgeReportPayload(BaseModel): ...

@dataclass(frozen=True, slots=True)
class AllegationRecord: ...

@dataclass(frozen=True, slots=True)
class DefenseRecord: ...

@dataclass(frozen=True, slots=True)
class JudgeDecisionRecord: ...

@dataclass(frozen=True, slots=True)
class DebateStageRecord: ...

@dataclass(frozen=True, slots=True)
class ProsecutorDefenderJudgeReport: ...
```

Every Pydantic model uses strict field constraints and `ConfigDict(extra="forbid")`. The model payloads use lists for JSON Schema compatibility; trusted records convert them to tuples. `ProsecutorAllegationPayload` has no ID field. `JudgeDecisionPayload` has no claim, finding, evidence-summary, or recommendation field.

#### Logic / Algorithm

1. Validate provider output through `AgentRuntime.output_schema` and then explicitly call `model_validate(...)` on `result.structured` or its mapping equivalent.
2. Convert prosecutor allegations to `AllegationRecord` in emitted order, assigning `ALG-{index:03d}`.
3. Validate evidence source names against the stage projection and exact candidate excerpts against candidate text.
4. Validate defender response IDs equal the allegation IDs as an ordered sequence; create `DefenseRecord` values by zipping allegations and responses.
5. Validate judge decision IDs equal the same ordered sequence and decision/reason-code compatibility.
6. Derive survivor IDs and verdict in SDK code.
7. Serialize the versioned report to a JSON-safe mapping for result metadata.

#### Edge Cases & Error Handling

- Model output text is not parsed with a permissive fallback when `structured` is absent. Unsupported/malformed structured output is a stage failure.
- Zero allegations requires zero defense responses and zero judge decisions.
- Duplicate allegations are allowed as separate prosecutor allegations because semantic duplicate detection is a judge responsibility; the judge may reject one with `duplicate` but cannot merge IDs.
- Referential integrity uses exact order, not sets alone, preventing silent reorder/omission.
- Total serialized output size is checked after validation and before forwarding.

### 6.3 Runtime adapter and isolated-stage factory

**File(s):** `vidbyte/agents/algorithms/prosecutor_defender_judge.py`
**Type:** New file

#### What it does

Runs the producer and sequential debate, builds stage projections, validates evidence/references, applies timeouts/failure policy, assembles provenance, and preserves the producer result. Non-trivial responsibilities are split among small classes rather than one large method.

#### Interface / API

```python
class ProsecutorDefenderJudgeRuntimeAlgorithm:
    name = "prosecutor_defender_judge"

    def __init__(self, runtime: AgentRuntime, algorithm: ProsecutorDefenderJudgeAlgorithm) -> None: ...
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...

class DebateStageRuntimeFactory:
    def build(self, role: str, settings: DebateStageSettings, schema: type[BaseModel], handle: RunnerHandle) -> tuple[AgentRuntime, RunnerHandle]: ...

class DebateResourceProjector:
    def project_artifacts(self, names: Sequence[str], context: BaseAgentContext) -> tuple[PermittedArtifact, ...]: ...
    def project_tools(self, names: Sequence[str], tools: Tools) -> Tools: ...

class DebateTranscriptValidator:
    def normalize_allegations(self, payload: ProsecutorReportPayload, projection: StageProjection, candidate: str) -> tuple[AllegationRecord, ...]: ...
    def normalize_defenses(self, payload: DefenderReportPayload, allegations: Sequence[AllegationRecord], projection: StageProjection) -> tuple[DefenseRecord, ...]: ...
    def normalize_decisions(self, payload: JudgeReportPayload, allegations: Sequence[AllegationRecord], defenses: Sequence[DefenseRecord]) -> tuple[JudgeDecisionRecord, ...]: ...
```

Internal frozen records (`PermittedArtifact`, `StageProjection`, `StageOutcome`) carry exact stage inputs, allowed source names, result accounting, and durations. They are private to the adapter module unless a merged sibling feature already supplies equivalent internal infrastructure.

#### Logic / Algorithm

`arun(...)` performs:

1. Record `system_prompt` and run the producer exactly once through `_arun_once(...)` inside the `producer` trace child.
2. Capture `candidate = producer_result.output`, validate exact task/candidate bounds, compute SHA-256, and record `prosecutor_defender_judge_candidate`.
3. Preflight all three stage resource projections before the first review call so an invalid later allowlist does not incur a partial debate cost. Attribute a failure to the affected role with `phase="preflight"`, even though no review-stage slot has completed yet.
4. Build and run the prosecutor stage with `ProsecutorReportPayload`; normalize evidence and assign IDs; record the prosecutor slot only after validation.
5. Build defender payload from the exact normalized allegation mappings, run with `DefenderReportPayload`, validate ordered one-to-one IDs/evidence, and record its slot only after validation.
6. Build judge payload from the exact allegation/defense pairs, run with `JudgeReportPayload`, validate ordered one-to-one decisions and reason codes, and record its slot only after validation.
7. Derive survivors and verdict, assemble `ProsecutorDefenderJudgeReport`, and attach its mapping to a `dataclasses.replace(...)` copy of the producer result.
8. On an ordinary failure, record one failure slot and either raise a stage-labelled `AgentExecutionError` or attach marked failure metadata according to policy. Re-raise process/cancellation `BaseException` values.

`DebateStageRuntimeFactory.build(...)` performs:

1. Resolve inherited or dedicated runner/provider/model without copying producer options.
2. Create `AgentRuntimeConfig` from stage-local iteration/token/tool caps.
3. Create a fresh `AgentRuntime` with stage tools, inherited permission policy and tracer, empty middleware, default algorithm, `context_manager=None`, a `NullRecorder`, stage output schema, no producer output contract, and `include_internal_tools=False`.
4. Create a fresh `BaseAgentContext` with only stage system prompt and selected tool specs, set `agentic_loop=False`, and supply all other fields as explicit empty defaults.

Each `_run_stage(...)` call uses a stage trace span and `asyncio.timeout`, passes the rendered payload as the only user message, passes `options={}`, and requires a valid structured result. Stage `AgentResult.calls` and raw outputs are consumed for validation/accounting only and never merged into the producer result.

#### Edge Cases & Error Handling

- Preflight rejects unknown/ambiguous resources, unsafe permissions, bound/live tools, oversize exact inputs, and provider/model errors before prosecutor invocation.
- A provider that does not support native response format may still emit JSON, but the SDK's ordinary output-schema validator must produce a valid Pydantic instance; otherwise the stage fails.
- Stage stop reasons such as max iterations/tokens/tool calls are acceptable only if a valid complete structured payload was produced; otherwise they fail.
- Error messages are mapped to stable safe categories and bounded. Raw provider prompt/response bodies are not copied into failure metadata.
- `asyncio.timeout` cancellation is distinguished from caller cancellation. Timeout becomes a stage failure; external cancellation propagates.
- The semantic inability to detect every unrelated sentence inside a defense response is documented; the schema prevents separate claims, prompts constrain content, and the judge is instructed to reject non-responsive defenses.

### 6.4 Generic runtime internal-tool opt-out

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds a backward-compatible constructor switch that lets isolated reviewer runtimes use exactly their allowlisted catalog without automatic `isDone` injection.

#### Interface / API

```python
class AgentRuntime:
    def __init__(..., include_internal_tools: bool = True, ...) -> None: ...
```

#### Logic / Algorithm

1. Preserve `self.user_tools = tools`.
2. Set `self.tools = with_internal_agent_tools(tools)` when `include_internal_tools` is true and `self.tools = tools` otherwise.
3. Preserve every existing caller's behavior through the true default.
4. Pass false only from isolated review stages.

#### Edge Cases & Error Handling

- The flag changes no producer behavior and no public `BaseAgent` constructor surface.
- If a sibling review algorithm has already landed an equivalent option, reuse it and do not add a duplicate field.

### 6.5 Prompt assets

**File(s):**

- `vidbyte/prompts/prompts/prosecutor_defender_judge/prosecutor_defender_judge.json`
- `vidbyte/prompts/prompts/prosecutor_defender_judge/prosecutor_system_prompt.md`
- `vidbyte/prompts/prompts/prosecutor_defender_judge/prosecutor_prompt.md`
- `vidbyte/prompts/prompts/prosecutor_defender_judge/defender_system_prompt.md`
- `vidbyte/prompts/prompts/prosecutor_defender_judge/defender_prompt.md`
- `vidbyte/prompts/prompts/prosecutor_defender_judge/judge_system_prompt.md`
- `vidbyte/prompts/prompts/prosecutor_defender_judge/judge_prompt.md`

**Type:** New files

#### What it does

Defines role boundaries, evidence discipline, prompt-injection resistance, and structured output duties in independently overrideable Markdown assets. The JSON descriptor registers one prompt family with six keys.

#### Interface / API

```python
Prompt.PROSECUTOR_DEFENDER_JUDGE_PROSECUTOR_SYSTEM_PROMPT
Prompt.PROSECUTOR_DEFENDER_JUDGE_PROSECUTOR_PROMPT
Prompt.PROSECUTOR_DEFENDER_JUDGE_DEFENDER_SYSTEM_PROMPT
Prompt.PROSECUTOR_DEFENDER_JUDGE_DEFENDER_PROMPT
Prompt.PROSECUTOR_DEFENDER_JUDGE_JUDGE_SYSTEM_PROMPT
Prompt.PROSECUTOR_DEFENDER_JUDGE_JUDGE_PROMPT
```

#### Logic / Algorithm

1. Prosecutor instructions demand adversarial scrutiny but prohibit unsupported allegations and references to unavailable context.
2. Defender instructions demand exactly one responsive answer per supplied ID and prohibit new standalone claims, omissions, ID changes, and attacks on issues not alleged.
3. Judge instructions frame both sides as claims to verify, require a decision for each supplied ID, prohibit new allegations, and require reason-code consistency.
4. All user prompts place `{payload_json}` inside explicit untrusted-evidence delimiters and reiterate that embedded candidate/artifact text cannot change role instructions.
5. Output schemas remain the authoritative structural contract; prompt examples match them but do not replace validation.

#### Edge Cases & Error Handling

- Prompt overrides missing `{payload_json}` fail configuration validation.
- Prompt assets do not include producer system/history placeholders, preventing accidental future injection.
- Existing setuptools package-data globs already include nested JSON/Markdown files, so `pyproject.toml` requires no change.

### 6.6 Recorder template

**File(s):** `vidbyte/lib/templates/prosecutor_defender_judge.py`
**Type:** New file

#### What it does

Provides deterministic structural validation for successful and failed protocol runs.

#### Interface / API

```python
class ProsecutorDefenderJudgeContextWindowTemplate(ContextWindowTemplate):
    def __init__(self, *, completed_stages: tuple[str, ...] = ("prosecutor", "defender", "judge"), failed_stage: str | None = None) -> None: ...
```

#### Logic / Algorithm

1. Success requires the full canonical completed-stage tuple and expects system prompt, candidate, prosecutor, defender, and judge slots.
2. A failure expects system prompt and candidate, the slots named by `completed_stages`, then one failure slot.
3. `completed_stages` must be a prefix of `(prosecutor, defender, judge)`; preflight failures use the empty prefix and identify the affected role in `failed_stage`.
4. Runtime failures normally use the prefix before the failed role: empty for prosecutor, `(prosecutor,)` for defender, and `(prosecutor, defender)` for judge.
5. Unknown, duplicate, or non-prefix stage sequences raise `ValueError`.

#### Edge Cases & Error Handling

- Preflight failures are attributed to the earliest affected review stage and use the corresponding prefix.
- Caller cancellation is not converted to a failure slot unless an ordinary stage error has actually been classified.

### 6.7 Registry, dispatcher, presets, and exports

**File(s):**

- `vidbyte/context/algorithms/tool_results.py`
- `vidbyte/context/algorithms/__init__.py`
- `vidbyte/context/presets.py`
- `vidbyte/context/__init__.py`
- `vidbyte/agents/context_algorithms.py`
- `vidbyte/agents/algorithms/__init__.py`
- `vidbyte/lib/dataclasses/__init__.py`
- `vidbyte/lib/enums/prompts.py`
- `vidbyte/lib/templates/__init__.py`
- `vidbyte/__init__.py`

**Type:** Modified

#### What it does

Adds the algorithm to the existing mutually exclusive context-window namespace, routes it as a return-level adapter, registers prompt enum values, and exposes public configuration/report/template contracts through established import surfaces.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    prosecutor_defender_judge: ProsecutorDefenderJudgeAlgorithm | None = None

class ContextWindowPresets:
    @property
    def prosecutor_defender_judge(self) -> ContextWindowAlgorithm: ...
```

`AgentRuntimeContextAlgorithms.detect_algorithm()` returns `"prosecutor_defender_judge"` when configured, and `return_algorithm()` returns `ProsecutorDefenderJudgeRuntimeAlgorithm`. It does not enter `inner_loop_algorithm()`.

#### Logic / Algorithm

1. Add the optional field to the at-most-one-active validation tuple without removing current or newly merged algorithms.
2. Add preset construction, imports, `__all__` entries, dispatcher detection, and return type union.
3. Add six prompt enum values that exactly match the prompt descriptor.
4. Export public config, settings, failure policy, enums, payloads, records, report, and template from their normal context/dataclass/template/root surfaces; keep the runtime adapter internal to `vidbyte.agents.algorithms`.

#### Edge Cases & Error Handling

- Rebase against latest `main` before implementation and preserve any Devil's Advocate, Independent Critic, panel, or other fields that landed after this audit.
- Prompt enum/catalog mismatch remains a startup `ConfigurationError` through the existing catalog validator.

### 6.8 User documentation

**File(s):** `README.md`, `vidbyte/context/README.md`
**Type:** Modified

#### What it does

Documents the preset, custom per-stage configuration, review-only result contract, isolation boundary, evidence/tool allowlists, latency/cost, failure policy, metadata shape, and relationship to revision algorithms.

#### Interface / API

```python
from vidbyte import ContextWindow

agent = Agent(
    name="producer",
    runner=runner,
    algorithm=ContextWindow.preset.prosecutor_defender_judge,
)

reply = await agent.arun("Evaluate this implementation against the requirements.")
debate = reply.metadata["prosecutor_defender_judge"]
```

The advanced example constructs `ProsecutorDefenderJudgeAlgorithm` with different artifact/tool/provider settings per role.

#### Logic / Algorithm

1. State that output/structured/calls remain the producer's.
2. Show verdict and survivor inspection.
3. Explain that default stages receive no producer artifacts/tools/private context.
4. Explain that review tools are safe/read only and explicit custom tools are authority boundaries.
5. Point users needing a revised candidate to critique-adjudicate-revise rather than implying this preset edits output.

#### Edge Cases & Error Handling

- Documentation must not call allegations ground truth or claim that debate always improves review accuracy.
- Examples must use only public exports added by this manifest.

---

## 7. Data Model Changes

### 7.1 ContextWindowAlgorithm

**Change type:** Modified

```python
prosecutor_defender_judge: ProsecutorDefenderJudgeAlgorithm | None = None
```

The field joins existing mutual-exclusion validation. Its default is `None`, so existing construction and preset behavior remain unchanged.

**Migration strategy:**

- Forward migration: no action for current callers; opt in through the preset or explicit config.
- Rollback plan: remove the optional field/preset/dispatcher/exports; serialized results retain an opaque metadata key only on runs that used the feature.

### 7.2 Public structured-output models

**Change type:** New

```python
ProsecutorReportPayload
DefenderReportPayload
JudgeReportPayload
```

These strict Pydantic models are provider-output contracts, not persistence schemas. They use `extra="forbid"`, bounded fields/lists, and enum values.

**Migration strategy:** N/A - no stored schema is changed.

### 7.3 Trusted transcript and report records

**Change type:** New

```python
AllegationRecord
DefenseRecord
JudgeDecisionRecord
DebateStageRecord
ProsecutorDefenderJudgeReport
```

The records separate model-authored claims from SDK-owned IDs, provenance, accounting, and derived verdict. `ProsecutorDefenderJudgeReport` serializes to the value stored under `AgentResult.metadata["prosecutor_defender_judge"]`.

**Migration strategy:** N/A - in-memory SDK types and optional metadata only.

### 7.4 AgentResult metadata

**Change type:** New optional metadata key

```json
{
  "prosecutor_defender_judge": {
    "schema_version": 1,
    "status": "reviewed",
    "review_only": true,
    "candidate_revised": false,
    "candidate_sha256": "...",
    "verdict": "needs_changes",
    "allegation_count": 2,
    "surviving_allegation_ids": ["ALG-002"],
    "allegations": [
      {
        "allegation_id": "ALG-001",
        "severity": "major",
        "category": "correctness",
        "claim": "...",
        "candidate_excerpt": "...",
        "evidence": [],
        "recommended_fix": "..."
      }
    ],
    "defenses": [
      {
        "allegation_id": "ALG-001",
        "position": "contest",
        "response": "...",
        "evidence": []
      }
    ],
    "decisions": [
      {
        "allegation_id": "ALG-001",
        "decision": "rejected",
        "reason_code": "rebutted",
        "rationale": "..."
      }
    ],
    "stages": {
      "prosecutor": {"status": "completed", "provider": "...", "model": "..."},
      "defender": {"status": "completed", "provider": "...", "model": "..."},
      "judge": {"status": "completed", "provider": "...", "model": "..."}
    }
  }
}
```

The full structure is bounded and JSON-safe. Existing producer metadata remains. No `structured` or `calls` migration occurs.

---

## 8. API Changes

N/A for HTTP/network endpoints. Public Python additions are:

- `ContextWindow.preset.prosecutor_defender_judge`
- `ContextWindow.resolve_algorithm("prosecutor_defender_judge")`
- `ProsecutorDefenderJudgeAlgorithm`
- `DebateStageSettings`
- `ProsecutorDefenderJudgeFailurePolicy`
- evidence/severity/position/decision/reason-code enums
- strict prosecutor, defender, and judge payload types
- trusted allegation, defense, decision, stage, and final report records
- `ProsecutorDefenderJudgeContextWindowTemplate`
- six `Prompt.PROSECUTOR_DEFENDER_JUDGE_*` values

Example custom configuration:

```python
from vidbyte import (
    ContextWindowAlgorithm,
    DebateStageSettings,
    ProsecutorDefenderJudgeAlgorithm,
)

debate = ProsecutorDefenderJudgeAlgorithm(
    prosecutor=DebateStageSettings(
        artifact_names=("requirements",),
        tool_names=("grep",),
    ),
    defender=DebateStageSettings(
        artifact_names=("requirements", "implementation-notes"),
        tool_names=("grep",),
    ),
    judge=DebateStageSettings(
        provider="openai",
        model="configured-judge-model",
        artifact_names=("requirements",),
    ),
)

agent = Agent(
    name="producer",
    runner=runner,
    algorithm=ContextWindowAlgorithm(
        name="prosecutor_defender_judge",
        prosecutor_defender_judge=debate,
    ),
)
```

No existing method signature becomes breaking; the internal runtime constructor gains a defaulted opt-out parameter.

---

## 9. File Change Manifest

Complete list of every file expected on the currently audited `main`:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-window-prosecutor-defender-judge.md` | This design document |
| CREATE | `vidbyte/context/algorithms/prosecutor_defender_judge.py` | Public algorithm, stage settings, failure policy, validation, and prompt rendering |
| CREATE | `vidbyte/agents/algorithms/prosecutor_defender_judge.py` | Producer pass, isolated sequential stages, projections, validation, tracing, and result assembly |
| CREATE | `vidbyte/lib/dataclasses/prosecutor_defender_judge.py` | Strict model payloads and trusted transcript/report contracts |
| CREATE | `vidbyte/lib/templates/prosecutor_defender_judge.py` | Deterministic successful/failed recorder slot template |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/prosecutor_defender_judge.json` | Prompt-family descriptor |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/prosecutor_system_prompt.md` | Prosecutor role, evidence, and isolation instructions |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/prosecutor_prompt.md` | Prosecutor evidence payload template |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/defender_system_prompt.md` | Allegation-by-allegation defense instructions |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/defender_prompt.md` | Defender transcript/evidence payload template |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/judge_system_prompt.md` | Existing-ID-only adjudication instructions |
| CREATE | `vidbyte/prompts/prompts/prosecutor_defender_judge/judge_prompt.md` | Judge transcript/evidence payload template |
| MODIFY | `vidbyte/agents/runtime.py` | Add default-on internal-tool injection switch for exact isolated tool catalogs |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add optional config field and mutual-exclusion validation entry |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public algorithm/config contracts |
| MODIFY | `vidbyte/context/presets.py` | Add default preset |
| MODIFY | `vidbyte/context/__init__.py` | Re-export public algorithm/config contracts |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect and dispatch return-level runtime adapter |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export internal runtime adapter |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export typed payload/transcript/report contracts |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add six prompt catalog enum keys |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export recorder template |
| MODIFY | `vidbyte/__init__.py` | Add root public exports |
| MODIFY | `README.md` | Document preset, custom stages, verdict inspection, and cost |
| MODIFY | `vidbyte/context/README.md` | Document protocol, isolation, allowlists, metadata, and review-only semantics |

**Manifest counts:** 12 files created, 13 files modified, 0 files deleted (25 files total). No file under `tests/` or `scripts/` is added or modified.

If a sibling adversarial-review algorithm merges shared isolation infrastructure before implementation, update this design document and its manifest for approval before deviating; do not silently duplicate or omit the merged contract.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| No new package dependency | Python 3.11 `asyncio.timeout` | Per-stage deadlines and cancellation cleanup | Provider cancellation behavior varies; cleanup and trace closure must be verified manually |
| Existing `pydantic` | `>=2,<3` | Strict provider-native prosecutor/defender/judge schemas | Provider-native schema support varies; missing validated `structured` output fails closed |
| Existing configured model provider(s) | Inherited runner or explicit stage provider/model | Producer and three sequential review calls | Review adds latency/cost and may hit rate limits; three local budgets expose usage |
| Existing configured tools | Exact stage-specific `SAFE`/`READ` subset | Optional evidence retrieval | Explicit custom tools may reveal their own external/closure state; bound/live/mutating tools are rejected |
| Existing tracing provider | Current tracer/controller configuration | Nested producer/stage/model/tool provenance | Review evidence can be sensitive; existing trace privacy policy still governs permitted stage payloads |

Research links in Section 3 are design evidence, not runtime dependencies.

---

## 11. Rollout & Deployment

- **Opt-in:** no feature flag is required. Default context-window behavior remains unchanged; work occurs only when the preset/config is selected.
- **Implementation base:** after explicit approval, update clean `main`, stop if it is dirty or cannot pull, create `feat/context-window-prosecutor-defender-judge` in an isolated worktree, and commit this design document before implementation code.
- **Predecessor reconciliation:** re-audit latest `main`. Preserve any newly merged context-window field, dispatcher branch, prompt enum, template export, runtime isolation helper, and documentation entry. Amend this doc before material manifest/API changes.
- **Manual rollout:** begin with empty tools/artifacts and one provider in a non-production environment. Inspect candidate equality, stage projections, structured transcript, traces, timeouts, and cost before adding artifacts or tools.
- **Compatibility:** the default-on internal-tool setting and default-`None` algorithm field preserve current callers. No data migration or service deployment ordering exists beyond publishing one SDK version.
- **Rollback:** remove the preset/dispatcher/exports/runtime option and new files. There is no stored migration. Previously persisted results retain a versioned metadata object that older clients can treat as opaque.
- **Automated verification follow-up:** add configuration, isolation, exact-input, evidence, ID-integrity, zero-allegation, failure-policy, timeout, tracing, prompt-catalog, export, and candidate-preservation tests in a separate tests-authorized change.

---

## 12. Open Questions

- [ ] Should prosecutor, defender, and judge default to the same inherited runner or require an explicit independent judge model? Current design inherits each stage independently for ease of use while preserving logical context isolation; production guidance recommends a dedicated judge where correlated model bias matters.
- [ ] Should `RETURN_CANDIDATE` retain validated partial allegations/defenses in failure metadata? Current design records stage completion/count/provenance but omits partial substantive transcript to avoid consumers treating an unadjudicated prefix as a verdict.
- [ ] Should zero allegations skip defender/judge calls to save cost? Current design still runs both with empty typed lists so the named three-stage protocol and audit trail remain complete and any invented allegation is detected.
- [ ] Should version 1 allow explicitly opted-in `EXECUTE` tools for sandboxed verification? Current design rejects both `WRITE` and `EXECUTE`; expanding review capabilities without compromising review-only side effects needs a separately designed sandbox contract.
- [ ] Should future versions expose the report outside generic metadata? Current design follows existing `AgentResult.metadata` extension practice and preserves producer `structured`; a typed top-level review-results channel would be a broader API change.
- [ ] Can custom standalone tools be proven free of private closure state? Current design treats explicitly selected custom tools as caller-granted authority, rejects known live/bound types, and documents the residual limitation; a formal `clone_for_review()` capability protocol could be designed later.

---

## 13. Alternatives Considered

### Alternative 1: Give the producer critique and ask it to defend itself

- **What:** reuse the producer runtime/history for the defense stage.
- **Why rejected:** this exposes private scratch/history, creates self-anchoring, and makes the defense depend on information the prosecutor and judge cannot inspect. A fresh defender context keeps the debate transcript auditable and matches the requested allegation-specific flow.

### Alternative 2: Run prosecutor and defender in parallel

- **What:** have both independently assess the candidate at the same time.
- **Why rejected:** the defender must answer the prosecutor's specific allegation IDs. Without those allegations it can only write a generic positive review, which is a panel rather than a rebuttal protocol.

### Alternative 3: Let the defender or judge add new findings

- **What:** allow either later role to return a general list of candidate issues.
- **Why rejected:** this destroys referential integrity and bypasses the requested burdens: the defender responds to allegations and the judge decides which claims survive. New issues belong in a separate prosecutor pass or another review algorithm.

### Alternative 4: Use one model call to impersonate all three roles

- **What:** prompt one model to generate prosecution, defense, and verdict in one response.
- **Why rejected:** there is no stage isolation or true sequential information boundary, tools/artifacts cannot be independently scoped, malformed references are difficult to detect, and a single response can retroactively coordinate all roles.

### Alternative 5: Reuse the producer runtime and scrub its context

- **What:** call `_arun_once` with `dataclasses.replace(producer_context, system_prompt=...)` and remove known private fields.
- **Why rejected:** it retains producer tools, middleware, context manager, output schema, options, and any future fields omitted from the denylist. Fresh runtimes and contexts make isolation the default under schema evolution.

### Alternative 6: Forward raw reviewer conversations and tool transcripts

- **What:** give each later stage the entire preceding model/tool history.
- **Why rejected:** it leaks stage-local implementation details, expands prompt-injection surface, obscures the formal protocol, and makes bounds unpredictable. Only validated normalized allegations and defenses cross stages.

### Alternative 7: Truncate oversized candidate/evidence inputs

- **What:** clip task, candidate, artifacts, allegations, or defenses to stay within context limits.
- **Why rejected:** the reviewer could no longer claim to have reviewed the exact candidate or answered every exact allegation. Oversize exact inputs fail explicitly; callers can raise configured limits or reduce explicitly permitted evidence.

### Alternative 8: Trust a free-form judge verdict

- **What:** ask the judge for a top-level `pass`/`fail` plus prose.
- **Why rejected:** it may contradict per-allegation decisions and can hide invented/omitted issues. The SDK derives the verdict from the exact ordered ID decisions.

### Alternative 9: Feed surviving allegations into an automatic revision

- **What:** run the producer again with the judge's survivor list and return the revision.
- **Why rejected:** that is critique-adjudicate-revise, changes candidate/output semantics, and introduces another failure/retry lifecycle. Version 1 is deliberately verdict-only.

### Alternative 10: Permit all explicitly named tool permissions

- **What:** allow `WRITE` and `EXECUTE` tools when the caller names them.
- **Why rejected:** a review/verdict-only algorithm should not mutate the environment, and executable tools complicate isolation/cancellation guarantees. `SAFE`/`READ` supplies evidence gathering while keeping version 1's operational boundary narrow.
