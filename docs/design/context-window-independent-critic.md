# Design Doc: Independent Critic Context-Window Algorithm

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

This feature adds an `independent_critic` context-window algorithm to the Vidbyte SDK. A normal producer run creates one candidate, then a logically separate reviewer examines that candidate in a freshly projected context that contains only the original task, the exact candidate, explicitly allowlisted artifacts, and explicitly allowlisted tools. The reviewer never receives the producer's system prompt, conversation history, scratch reasoning, tool-call history, context-manager state, run metadata, provider messages, or private options. Version 1 is deliberately review-only: it preserves the producer candidate as `AgentResult.output` and attaches bounded, structured, explicitly unadjudicated critic findings to result metadata. It does not revise the candidate; critique-adjudicate-revise owns that separate behavior.

---

## 2. Goals & Non-Goals

### Goals

- Expose `ContextWindow.preset.independent_critic` and support `ContextWindow.resolve_algorithm("independent_critic")`.
- Run the producer through the existing direct agent loop, then run exactly one separate critic stage over the completed candidate.
- Enforce a narrow reviewer input projection: original task, exact candidate, explicitly allowlisted artifact contents, explicitly allowlisted tool schemas/results, and algorithm-owned review instructions only.
- Prevent every SDK-managed producer-private channel from reaching the reviewer, including history, scratch/context memory, prior provider messages, system prompt, context primitives, metadata, middleware transforms, tool-call records, and the producer's mutable `ContextManager`.
- Keep the producer candidate unchanged as the public output while publishing bounded structured findings, verdict, summary, reviewer accounting, and isolation evidence in `AgentResult.metadata["independent_critic"]`.
- Default to fail-closed when the critic cannot run or returns an invalid report; provide an explicit `return_candidate` policy for callers that consciously prefer a marked unreviewed result.
- Support an optional dedicated reviewer provider/model and otherwise reuse the producer runner only as a stateless invocation transport with a fresh context and fresh options.
- Support explicitly permitted artifacts by exact artifact name and explicitly permitted standalone tools by exact model-facing tool name.
- Preserve producer tools, permissions, tracing, provider formatting, output contracts, and result metadata on the producer stage.
- Provide Markdown-backed reviewer prompts and a deterministic context-window template/recorder shape.
- Remain backward compatible and opt-in.

### Non-Goals

- No automatic revision, retry, or replacement of the producer candidate. That would collapse this algorithm into critique-adjudicate-revise.
- No adjudication of whether a critic finding is true. Findings are untrusted review output and are marked `adjudicated=False`.
- No parallel panel, specialist routing, prosecutor/defender exchange, pairwise comparison, or multi-candidate tournament.
- No access to producer scratch reasoning, private chain of thought, hidden provider state, or private history, even when such context might help the reviewer.
- No inheritance of producer middleware into the critic stage. In particular, a producer middleware `system` or `provider_messages` transform must not become an accidental disclosure channel.
- No implicit inheritance of producer artifacts, context items, tools, MCP handles, or context-manager primitives.
- No reviewer-specific MCP attachment or agent/session-bound tool support in version 1; tools that cannot be safely detached from producer-owned state are rejected during preflight.
- No new database, persistence, HTTP API, provider endpoint, third-party dependency, test file, or verification script.
- No implementation directly on the current branch; implementation begins only after approval and worktree setup under the Design Doc (No Tests) workflow.

---

## 3. Background & Context

### Research basis

OpenAI's CriticGPT work models the critic boundary as a `(question, answer)` input that produces specific comments attached to answer excerpts. The paper separately measures comprehensiveness, hallucinated bugs, nitpicks, and helpfulness, which is why this design treats findings as useful but unadjudicated review evidence rather than truth: [LLM Critics Help Catch LLM Bugs](https://cdn.openai.com/llm-critics-help-catch-llm-bugs-paper.pdf). OpenAI also reports that critic suggestions can be wrong and that long, complex tasks and dispersed errors remain difficult: [Finding GPT-4's mistakes with GPT-4](https://openai.com/index/finding-gpt4s-mistakes-with-gpt-4/).

The context barrier is not merely aesthetic. Pan et al. compare online judges that share iterative history with offline judges shown one candidate at a time. They report stronger reward-hacking divergence when author and judge share symmetric context and diminished divergence under asymmetric context. This supports constructing a reviewer context from an explicit allowlist instead of copying the producer context and deleting a few known fields: [Spontaneous Reward Hacking in Iterative Self-Refinement](https://arxiv.org/abs/2407.04549).

### Repository audit

The implementation base is clean `main` at commit `213d337` in `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-main-job-applier`. The user-facing working copy is currently on a dirty feature branch and contains unrelated untracked files, which must be preserved. A separate unmerged `feat/devils-advocate-context-window-algorithm` worktree was inspected as likely series precedent, but it is not treated as merged source of truth. If that predecessor or another algorithm lands before implementation, the approved implementation must re-audit latest `main` and extend shared registries without dropping newly merged fields or exports.

Clean `main` currently has five attached context-window algorithms. Return-level algorithms (`reflexion`, `multi_provider_agentic_grader`) use a public frozen config under `vidbyte/context/algorithms/`, a runtime adapter under `vidbyte/agents/algorithms/`, and dispatcher wiring in `AgentRuntimeContextAlgorithms`. Inner-loop algorithms use the single `after_tool_calls` lifecycle. Independent Critic is return-level because it wraps one complete producer run and then executes one complete review stage.

`AgentRuntime._arun_once(...)` is the correct producer path because it preserves the normal model/tool loop, permission enforcement, provider formatting, middleware, tracing, token accounting, output contracts, and structured result. `AgentRuntime._invoke_with_middleware(...)` is not sufficient for the reviewer because an explicitly permitted reviewer may need a tool loop. Reusing `_arun_once` on the producer runtime is also unsafe: that runtime owns the producer tool catalog, `ContextManager`, middleware pipeline, and algorithm state.

Clean `main` has robust `BaseAgent.fork(AgentForkSettings)` isolation for user-invoked child branches. That API clones known bound tools and can clear history when every override is supplied. The context-window adapter, however, operates at `AgentRuntime` level and must also work in direct runtime tests with injected `RunnerHandle` objects. The narrower solution is therefore a fresh reviewer `AgentRuntime` plus a whitelist-built `BaseAgentContext`, not a dependency from the runtime adapter back up into `BaseAgent`.

The current runtime always adds the internal `isDone` tool. That is appropriate for ordinary agents but violates the exact reviewer-tool allowlist. This design adds a backward-compatible runtime constructor flag so the isolated reviewer receives no implicit tools. The reviewer context also sets `agentic_loop=False`, avoiding an instruction to call an unavailable `isDone` tool while retaining the standard tool-call/result loop for any explicitly permitted tools.

### Core invariant

For critic model call `R`, the SDK-managed visible information set is:

```text
visible(R) = {
  independent-critic system/review instructions,
  original_task,
  producer_candidate,
  artifacts whose names are in allowed_artifact_names,
  tools whose names are in allowed_tool_names,
  results returned by those explicitly allowed tools,
  reviewer-local budget state and reviewer-local tool history
}
```

It explicitly excludes every other producer-owned field. A custom tool explicitly placed on the allowlist is an authority boundary: the SDK cannot prevent that tool's own implementation from revealing data it is designed to expose, but it will not pass producer-private data to the tool or reviewer implicitly.

---

## 4. Requirements

### Functional Requirements

1. `ContextWindow.preset.independent_critic` must return a `ContextWindowAlgorithm` named `"independent_critic"` containing a default `IndependentCriticAlgorithm`.
2. `ContextWindow.resolve_algorithm("independent_critic")` must resolve the preset; unknown names must continue to raise `ValueError`.
3. `IndependentCriticAlgorithm` must be a frozen slots dataclass and validate every limit, enum, name sequence, mapping, provider/model pair, prompt override, and required prompt placeholder at construction time with `ConfigurationError`.
4. `CriticFailurePolicy` must expose `RAISE = "raise"` and `RETURN_CANDIDATE = "return_candidate"`; the default must be `RAISE`.
5. The default preset must permit zero producer artifacts and zero producer tools. It must still review the original task and candidate.
6. The producer stage must call `self.runtime._arun_once(...)` exactly once with the original message, original `BaseAgentContext`, original options copied into a fresh dict, original middleware path, and the active trace context.
7. The candidate reviewed must be exactly `producer_result.output`; it must not be summarized, rewritten, normalized, or truncated. If it exceeds `max_candidate_chars`, the review cannot claim to cover the exact candidate and must follow the configured failure policy.
8. The reviewer stage must be a new `AgentRuntime` instance with the default context-window algorithm, a new middleware pipeline, no `ContextManager`, no output contract inherited from the producer, and a reviewer-local runtime budget.
9. The reviewer runtime must receive `include_internal_tools=False`, so neither `isDone` nor any other internal tool is implicitly exposed.
10. The reviewer context must be built from a new `BaseContext`/`BaseAgentContext`, never with `dataclasses.replace(producer_context, ...)`.
11. Reviewer `history`, `file_paths`, `run_metadata`, `tool_calls`, `responses`, `memory`, `metadata`, and `context_items` must be empty. Reviewer `context_manager` must be `None`.
12. The reviewer must not receive the producer system prompt. It receives only the independent-critic system prompt from the prompt catalog or the explicit reviewer override.
13. Reviewer invocation options must start from `{}` and must not copy producer options. In particular, producer `messages`, `system`, `tools`, `response_format`, provider-private options, or mutable option objects must not cross the stage boundary.
14. The review prompt must contain a JSON-encoded payload with exactly `original_task`, `candidate`, and `permitted_artifacts`. JSON encoding is transport escaping only; the underlying task, candidate, and artifact contents must remain exact and untruncated.
15. `allowed_artifact_names` must select only matching entries from `producer_context.artifacts`. No file paths, memory, responses, metadata, context items, or context-manager primitives may be inferred as artifacts.
16. Every requested artifact name must resolve before review. Artifact contents must satisfy both the per-artifact and total artifact character limits; otherwise review follows the configured failure policy rather than silently truncating evidence.
17. Artifact transport must include only `name`, `artifact_type`, and `content`; artifact metadata must not be copied.
18. `allowed_tool_names` must select an exact subset of `runtime.user_tools`. Unknown names must fail preflight explicitly.
19. Producer tools not on the allowlist must not appear in reviewer context, provider tool schemas, lookup, or metadata.
20. Selected tools that implement `clone_for_fork()` must be cloned before reviewer use so producer bindings are not reused.
21. SDK agent-bound, session-bound, dynamic-attachment, or parent-live-handle tools that cannot operate safely without a `BaseAgent` owner must be rejected with an actionable configuration error. Version 1 must not silently reuse their producer binding.
22. The reviewer runtime must enforce the producer's `PermissionPolicy` for every explicitly allowed tool call. The reviewer cannot escalate tool permissions.
23. If `reviewer_provider` and `reviewer_model` are both absent, the reviewer must reuse the current `RunnerHandle` as invocation transport while still using a fresh runtime, fresh context, and fresh options. If one is supplied, both are required and a fresh text runner must be created through `ModalityDetector`.
24. The reviewer must return strict JSON with `verdict`, `summary`, and `findings`. Verdict values are `pass`, `needs_changes`, or `uncertain`.
25. Each finding must normalize to bounded fields: `severity`, `category`, `claim`, `candidate_excerpt`, `evidence`, and `recommendation`. Severity values are `critical`, `major`, `minor`, or `note`.
26. Missing or malformed required review fields, invalid JSON, unsupported enum values, or a reviewer runtime stop that does not yield a valid report must count as critic failure.
27. The final `AgentResult` must preserve the producer result's `output`, `strategy_name`, `calls`, `structured`, and all existing metadata. Only a new `independent_critic` metadata object may be added or replaced.
28. Successful metadata must include `status="reviewed"`, `review_only=True`, `candidate_revised=False`, `adjudicated=False`, verdict, bounded summary/findings, reviewer provider/model, allowed artifact/tool names, reviewer stop reason, reviewer iteration/tool/token accounting, and configured algorithm metadata.
29. Reviewer tool calls must not be merged into producer top-level calls or top-level `tool_calls`. A bounded reviewer-call summary belongs under `metadata["independent_critic"]["reviewer"]` so producer audit semantics remain stable.
30. Under `CriticFailurePolicy.RAISE`, critic invocation/parsing/isolation failures must raise an `AgentExecutionError` that names the independent-critic stage and chains the original error.
31. Under `CriticFailurePolicy.RETURN_CANDIDATE`, the producer result must be returned unchanged except for explicit `status="review_failed"`, `reviewed=False`, bounded error type/message, and the same isolation/allowlist accounting. It must never pretend a review passed.
32. `asyncio.CancelledError`, `KeyboardInterrupt`, and other `BaseException` subclasses must always propagate regardless of failure policy.
33. The algorithm must never feed the critique back to the producer, run another producer call, or modify candidate text.
34. Recorder slots must be deterministic: `system_prompt`, `independent_critic_candidate`, `independent_critic_review`, and, only after a critic-stage exception, `independent_critic_failure`.
35. The dispatcher must open the existing semantic `algorithm.independent_critic` span. Producer and reviewer model/tool spans must be children of that algorithm span when semantic tracing is active.
36. Algorithm-specific trace attributes must be content-free. They may include stage, opaque reviewer/run identifiers, configured allowlist names, provider/model labels, verdict category, counts, hashes, timing, and truncation flags, but never the original task, candidate, artifact contents, tool arguments/results, findings, provider response text, or raw exception bodies.

### Non-Functional Requirements

- **Isolation/security:** The reviewer boundary must be allowlist-built rather than denylist-scrubbed. New fields added to `BaseAgentContext` in the future must remain excluded by default because the reviewer constructs a new context rather than copying the producer context.
- **Latency:** Default overhead is one sequential reviewer model call after the producer completes. Explicit reviewer tools may add calls up to reviewer-local caps.
- **Cost:** Reviewer defaults are bounded by `reviewer_max_iterations=4`, `reviewer_max_tokens=8000`, and `reviewer_max_tool_calls=4`; provider-reported token limitations remain visible in metadata.
- **Reliability:** Reviewer state is run-local. Fresh dicts/tuples are used across stage boundaries, cancellation propagates, and fail-open behavior requires explicit configuration.
- **Observability:** Structured metadata and recorder slots distinguish candidate generation, review, failure, and reviewer-local tool usage without copying raw producer history.
- **Backward compatibility:** All new `ContextWindowAlgorithm` and `AgentRuntime` parameters have defaults preserving current behavior. Existing presets and callers are unchanged.
- **Context bounds:** Exact task/candidate/artifact inputs are rejected when configured limits are exceeded rather than silently truncated; only critic output metadata is bounded/truncated with explicit flags.
- **Maintainability:** Algorithm-specific orchestration stays outside `AgentRuntime`. The only generic runtime change is the opt-out flag for automatic internal tools.
- **No unconfigured overhead:** The new adapter and isolation path are unreachable unless `independent_critic` is selected.

### Acceptance Criteria & Manual Verification

1. A default run makes one producer pass and one reviewer pass; the returned output is byte-for-byte equal to the producer candidate.
2. Captured reviewer inputs contain the original task and candidate, but no sentinel values placed in producer system prompt, history, memory, metadata, tool-call records, context items, context-manager primitives, or producer options.
3. With no allowlists, reviewer tool schemas contain zero tools, including no internal `isDone` tool.
4. With artifact/tool allowlists, only named resources appear; an unknown name fails explicitly.
5. A producer-bound SDK tool is never reused with its producer binding.
6. Reviewer JSON becomes bounded, structured, `adjudicated=False` metadata; it never changes the candidate.
7. Invalid reviewer JSON raises by default and returns a marked `review_failed` candidate only under explicit `RETURN_CANDIDATE`.
8. Semantic traces distinguish the producer and reviewer stages under `algorithm.independent_critic` without reviewer-side producer-private attributes.
9. After implementation, run `python -m compileall vidbyte` and the existing regression suite `python -m unittest discover -s tests`. No new tests or verification scripts are added in this change.
10. Manually inspect a fake-runner trace/payload for the isolation sentinel scenario before opening the PR and record the result in the handoff report.

---

## 5. High-Level Design

Independent Critic is a return-level runtime adapter. It first delegates candidate production to the unchanged direct loop. Once the producer returns, the adapter resolves the explicit artifact/tool allowlists, validates exact-input limits, constructs a fresh reviewer runtime, constructs a fresh reviewer context, and invokes the reviewer. It then normalizes the review report and attaches it to a copy of the producer result. There is no edge from review output back to the producer.

The key security decision is positive projection. The implementation does not copy the producer context and clear known sensitive fields; it creates a new context whose empty defaults exclude all producer-private state. The review payload is JSON with exactly three keys. The reviewer runtime has a separate tool catalog, middleware pipeline, local budgets, algorithm setting, and provider message history. Producer middleware is intentionally not inherited because middleware can transform model-visible system/messages.

The default reviewer is a distinct logical role and model call, not necessarily a distinct model family. Reusing the current `RunnerHandle` keeps the preset usable without extra provider configuration, while fresh context/options preserve independence. Users who require model diversity can configure a validated reviewer provider/model pair.

```text
                         producer-only state
                  history / scratch / tools / manager
                              |
                              X  (no copy)
                              |
[Original task] -> [Producer AgentRuntime._arun_once] -> [Exact candidate]
                                                         |
                    explicit allowlists                  |
 [named artifacts] --------------------------+           |
 [named standalone tools] -------------------+           |
                                             v           v
                                   [Reviewer input projection]
                                     task + candidate +
                                     permitted artifacts
                                             |
                                             v
                                   [Fresh reviewer runtime]
                                   no inherited middleware,
                                   manager, history, options,
                                   or implicit internal tools
                                             |
                                             v
                                   [Structured critic report]
                                             |
                                             v
 [Producer candidate unchanged] + [bounded unadjudicated metadata]
```

Key design decisions:

1. **Review-only result semantics:** candidate output is preserved; critique appears only in metadata. This keeps Independent Critic distinct from algorithm 7.
2. **Fresh runtime, not same-runtime reuse:** a separate runtime makes tool catalogs, messages, budgets, middleware state, context manager, and algorithm state independent by construction.
3. **Fresh context, not `replace`:** future producer context fields cannot accidentally become reviewer-visible.
4. **No implicit control tool:** the reviewer is the rare direct runtime that must expose exactly the allowlisted tools; ordinary final text/structured JSON ends its run.
5. **No producer middleware inheritance:** isolation takes priority over reusing model-visible middleware transforms. Core permission checks, provider parsing, runtime budgets, and tracing remain active.
6. **Exact evidence or explicit failure:** task, candidate, and permitted artifacts are never silently truncated before review.
7. **Unadjudicated findings:** the critic may hallucinate or nitpick; metadata names that limitation instead of converting review into a hidden judge stage.

---

## 6. Detailed Design

### 6.1 IndependentCriticAlgorithm and CriticFailurePolicy

**File(s):** `vidbyte/context/algorithms/independent_critic.py`
**Type:** New file

#### What it does

Defines the immutable public configuration, validation, prompt rendering, exact artifact serialization, review JSON parsing, and bounded report normalization. It contains no runner calls, tool execution, middleware dispatch, tracing operations, filesystem access, or network access.

#### Interface / API

```python
class CriticFailurePolicy(str, Enum):
    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"


@dataclass(frozen=True, slots=True)
class IndependentCriticAlgorithm:
    reviewer_provider: str | None = None
    reviewer_model: str | None = None
    reviewer_system_prompt: str | None = None
    review_prompt: str | None = None
    allowed_artifact_names: tuple[str, ...] = ()
    allowed_tool_names: tuple[str, ...] = ()
    reviewer_max_iterations: int = 4
    reviewer_max_tokens: int = 8000
    reviewer_max_tool_calls: int = 4
    max_candidate_chars: int = 100_000
    max_artifact_chars: int = 50_000
    max_total_artifact_chars: int = 100_000
    max_critique_chars: int = 20_000
    max_findings: int = 20
    max_finding_chars: int = 2_000
    failure_policy: CriticFailurePolicy = CriticFailurePolicy.RAISE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    def reviewer_system_prompt_text(self) -> str: ...
    def render_review_prompt(self, task: str, candidate: str, artifacts: Sequence[ContextArtifact]) -> str: ...
    def normalize_review(self, value: object) -> dict[str, Any]: ...
```

All implementation functions/methods must follow the Design Doc (No Tests) style: one-line signatures, a 1-2 line explanatory comment immediately below every signature, and class-first decomposition for non-trivial behavior.

#### Logic / Algorithm

1. Normalize name sequences to tuples, reject blanks/duplicates, validate positive limits and safeguard maxima, normalize the failure-policy enum, and validate string metadata keys.
2. Require both reviewer provider/model or neither; validate configured values through `ProviderModelRegistry`.
3. Validate non-empty prompt overrides. A custom review prompt must contain `{review_payload}`.
4. `render_review_prompt` checks the exact task/candidate/artifact limits, serializes each permitted artifact as `{name, artifact_type, content}`, then uses `json.dumps` to create a payload with exactly `original_task`, `candidate`, and `permitted_artifacts`.
5. `normalize_review` accepts provider structured output or parsed JSON text, validates verdict/findings, discards unknown keys, bounds output fields, caps finding count, and reports truncation flags.
6. Normalized metadata always sets `adjudicated=False` and does not claim that findings were accepted.

#### Edge Cases & Error Handling

- Empty task/candidate strings remain valid exact inputs; the critic can flag them.
- Candidate/artifact oversize is an explicit review failure, not a truncation.
- Duplicate artifact/tool allowlist names fail at config construction.
- If more than one producer artifact has an allowed name, preflight fails because the positive selection is ambiguous; the reviewer never receives an arbitrary or combined match.
- `findings=[]` with `verdict="pass"` is valid.
- A finding can omit `candidate_excerpt` for omissions, but `claim` and `evidence` remain required.
- Code-fenced JSON is stripped before parsing for provider compatibility.
- Unknown review keys are discarded so model output cannot inject arbitrary metadata.

### 6.2 IndependentCriticRuntimeAlgorithm

**File(s):** `vidbyte/agents/algorithms/independent_critic.py`
**Type:** New file

#### What it does

Owns the producer/reviewer orchestration, strict input projection, reviewer runtime construction, tool isolation, failure policy, recorder slots, and final metadata merge.

#### Interface / API

```python
class IndependentCriticRuntimeAlgorithm:
    name = "independent_critic"

    def __init__(self, runtime: AgentRuntime, algorithm: IndependentCriticAlgorithm) -> None: ...
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
    async def _run_candidate(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult: ...
    async def _run_review(self, task: str, candidate: str, *, artifacts: Sequence[ContextArtifact], tools: Tools, handle: RunnerHandle, trace_context: SpanContext | None) -> AgentResult: ...
    def _build_reviewer_runtime(self, *, tools: Tools) -> AgentRuntime: ...
    def _build_reviewer_context(self, *, tools: Tools) -> BaseAgentContext: ...
    def _with_review_metadata(self, candidate: AgentResult, review: Mapping[str, Any], reviewer_result: AgentResult, *, artifacts: Sequence[ContextArtifact], tools: Tools, handle: RunnerHandle) -> AgentResult: ...
```

#### Logic / Algorithm

1. Record `system_prompt` and resolve artifact/tool names before the producer call so obvious allowlist misconfiguration fails without paying producer cost.
2. Record `independent_critic_candidate`, then call the producer runtime once with normal context/options and stage metadata.
3. Validate the exact candidate length and render the review payload.
4. Resolve reviewer handle: current handle for the default; `ModalityDetector.create_runner(...)` plus `handle.with_runner(...)` for an explicit reviewer model.
5. Build reviewer tools with `runtime.user_tools.subset(allowed_tool_names)`. Clone safely cloneable tools. Reject SDK tools that retain or require producer agent/session/MCP ownership.
6. Build a fresh reviewer `AgentRuntime` with reviewer-local config, producer permission policy, shared tracer/recorder, empty middleware, default context-window algorithm, no context manager, no output contract, the independent-critic JSON output schema, and `include_internal_tools=False`.
7. Build a fresh context through `reviewer_runtime.build_context(...)` using a new base context, empty histories/metadata/tool calls/context items, and `agentic_loop=False`.
8. Record `independent_critic_review`, then call `reviewer_runtime._arun_once(...)` with the JSON review prompt, reviewer handle, fresh context, safe stage metadata, `{}` options, and the algorithm trace context.
9. Normalize reviewer structured output when present, otherwise normalize reviewer text.
10. Use `dataclasses.replace(candidate_result, metadata=merged_metadata)` to preserve every producer result field.
11. On ordinary reviewer exceptions, record `independent_critic_failure`. Raise by default; under `RETURN_CANDIDATE`, attach explicit failure metadata and return the candidate. Never catch `BaseException`.

#### Edge Cases & Error Handling

- Producer failure propagates unchanged; there is no candidate to review and no fail-open result.
- Reviewer permission denial/tool failure becomes part of reviewer-local runtime state; if no valid final JSON follows, critic failure policy applies.
- Producer `options` may contain mutable `messages`; only the producer receives a copied dict. Reviewer options are always new and empty.
- Producer/result metadata may contain scratch summaries or raw tool results; only candidate `.output` crosses the boundary.
- If a visibly returned candidate itself contains reasoning, that text is part of the candidate contract and is reviewed. Hidden/private reasoning is not requested or copied.
- Reviewer tool results are permitted reviewer-local observations but are never merged into producer top-level calls.
- Concurrent runs use separate reviewer runtimes and message lists. Explicit custom tools remain subject to their own documented concurrency guarantees.

### 6.3 AgentRuntime internal-tool isolation flag

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds a backward-compatible constructor option allowing a specialized child runtime to expose exactly its supplied tool catalog rather than automatically adding `isDone`.

#### Interface / API

```python
class AgentRuntime:
    def __init__(..., include_internal_tools: bool = True, ...) -> None: ...
```

#### Logic / Algorithm

1. Preserve `self.user_tools = tools`.
2. Set `self.tools = with_internal_agent_tools(tools)` when `include_internal_tools` is true.
3. Set `self.tools = tools` exactly when false.
4. Leave every existing construction path unchanged through the default value.
5. Independent Critic passes false and uses `agentic_loop=False`; ordinary final JSON without a tool call terminates through the existing final-response path.

#### Edge Cases & Error Handling

- Existing agents retain `isDone` and current behavior.
- A reviewer with allowed tools can call them and then return ordinary JSON on a later iteration.
- A reviewer attempting to call undeclared `isDone` receives normal provider/tool validation behavior; the reviewer prompt never instructs it to call `isDone`.

### 6.4 Prompt assets

**File(s):** `vidbyte/prompts/prompts/independent_critic/independent_critic.json`, `vidbyte/prompts/prompts/independent_critic/reviewer_system_prompt.md`, `vidbyte/prompts/prompts/independent_critic/review_prompt.md`
**Type:** New files

#### What it does

Adds a prompt family with separate system-role instructions and a user review-payload template.

#### Interface / API

```json
{
  "key": "independent_critic",
  "prompts": {
    "reviewer_system_prompt": {"path": "reviewer_system_prompt.md"},
    "review_prompt": {"path": "review_prompt.md"}
  }
}
```

`review_prompt.md` contains the required `{review_payload}` placeholder. The system prompt tells the reviewer that candidate/artifact strings are untrusted data, not instructions; forbids speculation about unseen producer reasoning; requires concrete evidence; allows a clean pass; labels all findings as proposed/unadjudicated; and requires the strict JSON schema.

#### Logic / Algorithm

1. Catalog auto-discovery reads the descriptor and Markdown bodies through existing package-data globs.
2. Runtime inserts the JSON-encoded payload into the one validated placeholder.
3. The schema asks for verdict, summary, and atomic findings ordered by severity.

#### Edge Cases & Error Handling

- Candidate text containing XML tags, Markdown fences, braces, or prompt-like commands stays a JSON string and is explicitly treated as data.
- The prompt permits zero findings.
- Prompt overrides are text only; file-path overrides are not supported.

### 6.5 Prompt enum

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds stable prompt keys.

#### Interface / API

```python
INDEPENDENT_CRITIC_REVIEWER_SYSTEM_PROMPT = "independent_critic.reviewer_system_prompt"
INDEPENDENT_CRITIC_REVIEW_PROMPT = "independent_critic.review_prompt"
```

#### Logic / Algorithm

The public config resolves these entries through `Prompts().get(...)`. Dynamic direct prompt exports continue to work without modifying `vidbyte/prompts/__init__.py`.

#### Edge Cases & Error Handling

Missing descriptor paths fail through the existing prompt catalog error path.

### 6.6 ContextWindowAlgorithm field and preset

**File(s):** `vidbyte/context/algorithms/tool_results.py`, `vidbyte/context/presets.py`
**Type:** Modified

#### What it does

Adds the optional config field, preserves at-most-one runtime algorithm validation, and registers the default preset.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    independent_critic: IndependentCriticAlgorithm | None = None


class ContextWindowPresets:
    @property
    def independent_critic(self) -> ContextWindowAlgorithm:
        # Reviews one producer candidate in a fresh critic-only context.
        return ContextWindowAlgorithm(name="independent_critic", independent_critic=IndependentCriticAlgorithm())
```

#### Logic / Algorithm

Include `independent_critic` in the active-algorithm list. Attribute-based string resolution requires no special branch.

#### Edge Cases & Error Handling

When implementation starts from a newer `main`, preserve all other algorithm fields, including Devil's Advocate if merged.

### 6.7 Runtime dispatcher and adapter exports

**File(s):** `vidbyte/agents/context_algorithms.py`, `vidbyte/agents/algorithms/__init__.py`
**Type:** Modified

#### What it does

Wires the public config to the return-level runtime adapter and exports the adapter internally.

#### Interface / API

```python
def detect_algorithm(self) -> str | None: ...  # adds independent_critic
def return_algorithm(self) -> ReflexionRuntimeAlgorithm | MultiProviderAgenticGraderRuntimeAlgorithm | IndependentCriticRuntimeAlgorithm | None: ...
```

#### Logic / Algorithm

1. Detect `runtime.algorithm.independent_critic`.
2. Return `IndependentCriticRuntimeAlgorithm(runtime, config)`.
3. Reuse the existing dispatcher `arun` delegation and semantic algorithm span.
4. Leave `inner_loop_algorithm()` unchanged for this return-level algorithm.

#### Edge Cases & Error Handling

No config means dispatcher behavior remains unchanged. The adapter must not be returned based only on the algorithm name string; the typed field must be present.

### 6.8 Context-window template

**File(s):** `vidbyte/lib/templates/independent_critic.py`, `vidbyte/lib/templates/__init__.py`, `skills/vidbyte-sdk/context-window-templates.md`
**Type:** New file / Modified files

#### What it does

Defines and documents the deterministic structural slot sequence.

#### Interface / API

```python
class IndependentCriticContextWindowTemplate(ContextWindowTemplate):
    def __init__(self, *, review_fails: bool = False) -> None: ...
```

Successful slots:

```text
system_prompt
independent_critic_candidate
independent_critic_review
```

Critic-stage failure adds `independent_critic_failure` after `independent_critic_review`, regardless of whether policy raises or returns the marked candidate.

#### Logic / Algorithm

The template constructs the invariant sequence and exports it from `vidbyte.lib.templates`. The skill reference documents slot meanings, emit points, and the no-tests deferral.

#### Edge Cases & Error Handling

Producer failure ends before a critic report exists and is not represented as `independent_critic_failure`.

### 6.9 Public package exports

**File(s):** `vidbyte/context/algorithms/__init__.py`, `vidbyte/context/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Exports `IndependentCriticAlgorithm` and `CriticFailurePolicy` from the algorithm, context, and root SDK namespaces, matching existing user-facing algorithm config conventions.

#### Interface / API

```python
from vidbyte import CriticFailurePolicy, IndependentCriticAlgorithm
from vidbyte.context import CriticFailurePolicy, IndependentCriticAlgorithm
from vidbyte.context.algorithms import CriticFailurePolicy, IndependentCriticAlgorithm
```

#### Logic / Algorithm

Add imports and `__all__` entries without removing or reordering unrelated public exports unnecessarily.

#### Edge Cases & Error Handling

Circular imports are avoided by keeping model/runtime imports out of the public config module.

### 6.10 User documentation

**File(s):** `README.md`, `vidbyte/context/README.md`
**Type:** Modified

#### What it does

Documents review-only semantics, strict reviewer visibility, default fail-closed behavior, metadata access, and custom allowlists/model configuration.

#### Interface / API

```python
from vidbyte import Agent, ContextWindow

agent = Agent(
    name="reviewed-worker",
    system_prompt="Solve the task carefully.",
    provider="openai",
    model_name="gpt-5.4",
    algorithm=ContextWindow.preset.independent_critic,
)

reply = await agent.arun("Produce the migration plan.")
review = reply.metadata["independent_critic"]
```

Custom configuration is shown with an explicit `ContextWindowAlgorithm` carrying `IndependentCriticAlgorithm(allowed_artifact_names=(...), allowed_tool_names=(...), reviewer_provider=..., reviewer_model=...)`.

#### Logic / Algorithm

The docs state plainly that the candidate is not revised and findings are not adjudicated.

#### Edge Cases & Error Handling

The example does not imply that all producer tools/artifacts are inherited; default allowlists are empty.

---

## 7. Data Model Changes

### 7.1 IndependentCriticAlgorithm

**Change type:** New public immutable config

```python
IndependentCriticAlgorithm(
    reviewer_provider=None,
    reviewer_model=None,
    allowed_artifact_names=(),
    allowed_tool_names=(),
    failure_policy=CriticFailurePolicy.RAISE,
    ...bounded reviewer settings,
)
```

**Migration strategy:** N/A - additive in-memory configuration with conservative defaults.

### 7.2 CriticFailurePolicy

**Change type:** New string enum

```python
class CriticFailurePolicy(str, Enum):
    RAISE = "raise"
    RETURN_CANDIDATE = "return_candidate"
```

**Migration strategy:** N/A - no stored values or existing callers.

### 7.3 ContextWindowAlgorithm

**Change type:** Modified

```python
independent_critic: IndependentCriticAlgorithm | None = None
```

**Migration strategy:** Additive optional field defaulting to `None`; existing constructors remain valid.

### 7.4 AgentRuntime

**Change type:** Modified internal runtime configuration

```python
include_internal_tools: bool = True
```

**Migration strategy:** Default `True` preserves existing behavior. Only the isolated critic passes `False`.

### 7.5 Independent critic result metadata

**Change type:** New nested, transient result shape

```python
{
  "independent_critic": {
    "status": "reviewed",
    "review_only": True,
    "candidate_revised": False,
    "adjudicated": False,
    "verdict": "needs_changes",
    "summary": "...",
    "findings": (
      {
        "severity": "major",
        "category": "correctness",
        "claim": "...",
        "candidate_excerpt": "...",
        "evidence": "...",
        "recommendation": "..."
      },
    ),
    "input_projection": {
      "original_task": True,
      "candidate": True,
      "artifact_names": (),
      "tool_names": ()
    },
    "reviewer": {
      "provider": "openai",
      "model": "gpt-5.4",
      "stop_reason": "final_response",
      "iteration_count": 1,
      "tool_call_count": 0,
      "tokens_used": 1234,
      "tool_calls": ()
    },
    "config_metadata": {}
  }
}
```

**Migration strategy:** N/A - opt-in nested metadata. Existing producer metadata remains intact.

---

## 8. API Changes

N/A - no HTTP endpoints. The public Python API gains:

- `ContextWindow.preset.independent_critic`
- `ContextWindow.resolve_algorithm("independent_critic")`
- `IndependentCriticAlgorithm`
- `CriticFailurePolicy`
- `IndependentCriticContextWindowTemplate`
- Two `Prompt` enum members for the reviewer system and review payload prompts

Custom usage:

```python
from vidbyte import Agent, CriticFailurePolicy, IndependentCriticAlgorithm
from vidbyte.context.algorithms import ContextWindowAlgorithm

algorithm = ContextWindowAlgorithm(
    name="independent_critic",
    independent_critic=IndependentCriticAlgorithm(
        reviewer_provider="anthropic",
        reviewer_model="claude-sonnet-4-5",
        allowed_artifact_names=("requirements",),
        allowed_tool_names=("read_text",),
        failure_policy=CriticFailurePolicy.RAISE,
    ),
)

agent = Agent(
    name="reviewed-worker",
    system_prompt="Produce the best candidate you can.",
    provider="openai",
    model_name="gpt-5.4",
    tools=[read_text],
    context_items=[requirements_artifact],
    algorithm=algorithm,
)
```

Backward compatibility: all API changes are additive. The intentional behavioral choice is limited to users selecting the new preset.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-window-independent-critic.md` | Approved source of truth for the feature |
| CREATE | `vidbyte/context/algorithms/independent_critic.py` | Public config, validation, prompt rendering, report normalization, failure policy |
| CREATE | `vidbyte/agents/algorithms/independent_critic.py` | Producer/reviewer orchestration and isolation boundary |
| CREATE | `vidbyte/prompts/prompts/independent_critic/independent_critic.json` | Prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/independent_critic/reviewer_system_prompt.md` | Independent reviewer role and output rules |
| CREATE | `vidbyte/prompts/prompts/independent_critic/review_prompt.md` | JSON payload review template |
| CREATE | `vidbyte/lib/templates/independent_critic.py` | Deterministic recorder slot template |
| MODIFY | `vidbyte/agents/runtime.py` | Add backward-compatible opt-out for implicit internal tools |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export runtime adapter internally |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect and return the independent critic adapter |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add config field and at-most-one validation entry |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public config and failure policy |
| MODIFY | `vidbyte/context/presets.py` | Register default preset |
| MODIFY | `vidbyte/context/__init__.py` | Re-export public config and failure policy |
| MODIFY | `vidbyte/__init__.py` | Re-export public config and failure policy from root SDK |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add reviewer prompt enum values |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export independent critic template |
| MODIFY | `vidbyte/context/README.md` | Add context-layer feature summary and semantics |
| MODIFY | `README.md` | Add user-facing preset/customization example |
| MODIFY | `skills/vidbyte-sdk/context-window-templates.md` | Document slots and instrumentation points |

Manifest totals: **7 files created, 13 files modified, 0 files deleted**.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None new | Python standard library (`json`, `enum`, `dataclasses`) | Payload isolation, enums, immutable result copies | Low |
| Existing `pydantic`, `httpx` | Existing project constraints | No new usage introduced by this feature | None added |
| Existing provider runners | User-configured provider/model | Producer and optional dedicated reviewer calls | Reviewer latency/cost/provider availability |
| Existing explicitly allowed tools | Agent-local tool catalog | Optional reviewer evidence gathering | Tool behavior is an explicit authority boundary |

No provider-specific endpoint or remote Vidbyte service is added. Research sources inform the design but are not runtime dependencies.

---

## 11. Rollout & Deployment

- **Feature flag:** None. The preset is the opt-in gate.
- **Implementation base:** After explicit approval, create `feat/context-window-independent-critic` from freshly pulled `main` in an isolated worktree. Reconcile any algorithm fields/exports merged since commit `213d337`, especially the Devil's Advocate predecessor.
- **Deployment order:** One SDK package release; prompt assets ship through existing package-data globs.
- **Breaking change:** No. `AgentRuntime.include_internal_tools` defaults to current behavior and the context algorithm field defaults to `None`.
- **Operational rollout:** Start with default empty artifact/tool allowlists and fail-closed policy. Users add reviewer evidence capabilities deliberately.
- **Rollback:** Revert the implementation commits. No data migration, persisted state, or external service cleanup is required.
- **Verification before PR:** Compile the package, run existing tests, perform the manual isolation-sentinel inspection, self-critique against this doc, and resolve every critical/notable refinement item.
- **No-tests workflow:** Do not add test files or verification scripts in this feature PR. Any dedicated automated isolation suite is a follow-up unless the user changes scope.

---

## 12. Open Questions

- [ ] Should a future version accept direct per-call artifact objects in addition to `allowed_artifact_names`? Current choice: names only, so dynamic run context stays explicit and the public config remains serializable enough to inspect.
- [ ] Should `RETURN_CANDIDATE` be available on the preset at all? Current choice: available only through custom config; the preset remains fail-closed.
- [ ] Should reviewer-safe middleware gain a separate explicit configuration surface later? Current choice: no producer middleware inheritance in version 1 because model-visible transforms are an isolation channel.
- [ ] Should dedicated reviewer provider/model become mandatory? Current choice: no; a distinct invocation with a fresh context is an independent reviewer, while model diversity remains configurable.
- [ ] Should safely cloned `AgentTool` receive the reviewer task/candidate as its local active prompt? Current choice: reject agent/session-bound tool families in version 1 rather than invent partial binding semantics inside `AgentRuntime`.
- [ ] Should an oversized exact candidate under `RETURN_CANDIDATE` use `status="review_skipped"` rather than `status="review_failed"`? Current choice: `review_failed` with reason `candidate_limit_exceeded`, keeping one machine-readable failure state.

---

## 13. Alternatives Considered

### Alternative 1: Self-critique inside the producer context

- What: Ask the producer model to critique its own answer while retaining its full conversation and scratch history.
- Why rejected: It violates the explicit independent-reviewer boundary and preserves anchoring/shared-context effects. The asymmetric-context research above specifically supports an offline reviewer that sees the candidate without the author's iterative history.

### Alternative 2: Copy producer context and clear known private fields

- What: Use `dataclasses.replace(context, history=(), tool_calls=(), ...)` for the reviewer.
- Why rejected: This is a fragile denylist. Existing fields such as memory, responses, metadata, artifacts, context items, and future context additions can leak silently. Building a fresh context is fail-safe under schema evolution.

### Alternative 3: One `_invoke_with_middleware` critic call on the producer runtime

- What: Run a single prompt-only reviewer stage through the existing runtime middleware.
- Why rejected: It cannot support explicitly permitted reviewer tools, and producer middleware can inject system/messages or retain stage state. A fresh reviewer runtime preserves the normal tool loop while enforcing a clean boundary.

### Alternative 4: Reuse producer `_arun_once` with temporary tool/context overrides

- What: Swap `runtime.tools` and `runtime.context_manager` before the critic call, then restore them.
- Why rejected: Mutable swapping is unsafe under cancellation and concurrency and can contaminate producer state. A fresh runtime is simpler and correct.

### Alternative 5: Use `BaseAgent.fork()` directly

- What: Thread a parent-agent fork callback into `AgentRuntime`, then fork with empty history/context and selected tools.
- Why rejected: It expands the lower runtime's dependency on the higher agent layer, complicates direct runtime/fake-runner usage, and requires overriding every inheritable fork field correctly. The reviewer needs a smaller projection than a general branch fork.

### Alternative 6: Automatically send criticism back for revision

- What: After review, call the producer again with findings and return a revised candidate.
- Why rejected: That is a different algorithm with different failure, trust, and reward-hacking dynamics. Critique-adjudicate-revise explicitly owns revision and an adjudication gate.

### Alternative 7: Return a combined candidate-and-critique string

- What: Replace `AgentResult.output` with Markdown containing both outputs.
- Why rejected: It changes the producer's output contract, breaks structured outputs, and makes review text look like part of the answer. Nested metadata preserves both role separation and backward compatibility.

### Alternative 8: Truncate candidate/artifacts to fit configured limits

- What: Review a bounded prefix and mark it truncated.
- Why rejected: The algorithm promises review of the candidate, not review of a prefix. Explicit failure is more honest; callers can raise limits or reduce the candidate deliberately.

---

## Follow-Ups (Out of Scope)

- Dedicated automated isolation tests using sentinels in every producer-private channel.
- Reviewer-safe explicit middleware profiles, if a concrete use case justifies them.
- Reviewer-owned MCP/tool-agent binding through a separately designed isolated agent factory.
- Cross-algorithm shared review-result dataclasses if panel/adjudication implementations converge on the same schema.
- Tool form of Independent Critic under `context-algorithm-to-tool.md`.
