# Design Doc: Parallel Panel Context-Window Algorithm

**Status:** Draft

**Author:** Codex

**Created:** 2026-07-16

**Last Updated:** 2026-07-16

**Target repository:** vidbyte-sdk

**Implementation base:** clean main at 213d337

**Related precedent:** Devil's Advocate context-window worktree, through 97e8025

---

## 1. Overview

Add a public Parallel Panel context-window algorithm that produces one candidate answer and then asks several independent reviewers to inspect that exact candidate concurrently. Every first-round reviewer receives the same review prompt: the original task, the producer candidate, and only explicitly allowlisted context artifacts. Reviewers do not receive producer scratch reasoning, private history, tool transcripts, runtime context, or one another's findings.

The runtime holds a strict collection barrier: no review is exposed or collected into the returned result until all scheduled reviewers have completed, failed, timed out, or been cancelled under the configured policy. Successful reviews are attached to the producer result as bounded, deterministically ordered metadata. The producer candidate remains AgentResult.output. Version 1 does not revise, adjudicate, synthesize, rank, or replace that candidate.

This is an outer runtime algorithm because it must coordinate a complete producer run followed by multiple model-only reviewer calls. The design follows the repository's established public-config / dispatcher / runtime-adapter / prompt-catalog / context-template structure and the nearby Devil's Advocate implementation precedent, while reconciling all interfaces against current main.

## 2. Goals & Non-Goals

### Goals

1. Provide a frozen, validated public ParallelPanelAlgorithm configuration and ContextWindow.preset.parallel_panel convenience constructor.
2. Run one normal producer pass using the existing AgentRuntime path, preserving its tools, middleware, provider behavior, recorder, and tracing.
3. Render one immutable reviewer-input snapshot and give that exact same snapshot to every reviewer.
4. Prevent reviewers from seeing producer-private context or peer findings.
5. Schedule reviewers concurrently when the configured runner is asynchronously capable, with optional bounded concurrency.
6. Enforce a first-round collection barrier before publishing any finding.
7. Return successful reviews and bounded failure summaries in stable reviewer-index order, independent of completion order.
8. Define explicit branch timeout, panel timeout, cancellation, partial-failure, and minimum-success policies.
9. Preserve the producer candidate as the final output and expose review results as advisory artifacts in metadata.
10. Add deterministic context-window template slots and semantic tracing without recording candidate or review bodies in trace attributes.
11. Keep the change additive and compatible with the existing one-context-window-algorithm-at-a-time contract.

### Non-Goals

1. Revising or regenerating the producer candidate. Critique-adjudicate-revise owns that workflow.
2. Adjudicating, voting on, deduplicating, or synthesizing reviewer findings.
3. Giving reviewers different roles. Specialist Panel owns heterogeneous responsibilities.
4. Comparing multiple producer candidates. Pairwise Tournament owns candidate competition.
5. Running prosecutor, defender, and judge roles.
6. Giving reviewers access to tools, MCP servers, mutable agent history, memory, or unlisted artifacts in version 1.
7. Supporting different reviewer providers or model configurations in version 1.
8. Guaranteeing wall-clock parallelism for a custom synchronous runner.
9. Claiming that multiple reviews necessarily improve correctness.
10. Adding test files or verification scripts under this design-doc-no-tests workflow.

## 3. Background & Context

The current SDK exposes context-window algorithms through frozen public configuration objects in vidbyte/context/algorithms, wraps them with ContextWindowAlgorithm, provides presets in vidbyte/context/presets.py, and dispatches outer runtime algorithms from vidbyte/agents/context_algorithms.py. Outer adapters run a normal producer with AgentRuntime._arun_once and can invoke additional model-only stages through AgentRuntime._invoke_with_middleware. Prompt bodies live in the prompt catalog, and deterministic context-window structure is documented through recorder-backed templates under vidbyte/lib/templates.

Current main also wraps outer algorithms in an algorithm.<name> semantic trace span and closes spans for BaseException, including cancellation. The standard asynchronous runner can overlap network calls. A custom runner that exposes only synchronous run executes on the event-loop thread and therefore cannot provide actual wall-clock overlap merely because its calls are placed in asyncio tasks.

The Devil's Advocate predecessor confirms the intended extension shape: public algorithm config, runtime adapter, prompt assets, dispatcher and export wiring, a deterministic context template, and context-window documentation. It is useful precedent, but current main remains the implementation source of truth because it contains newer fork and tracing behavior.

Research supports the orchestration shape while also setting limits on the claim:

- OpenAI's Agents SDK orchestration guidance presents code-driven parallel agents with asyncio.gather when agents can work independently: [OpenAI Agents SDK — Orchestrating multiple agents](https://openai.github.io/openai-agents-python/multi_agent/).
- Anthropic describes parallelization as independently running the same task or different perspectives, noting the cost tradeoff rather than a universal quality guarantee: [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents).
- Python 3.11 documents that asyncio.gather schedules awaitables concurrently and returns results in input order; return_exceptions=True allows all branches to settle, while cancellation propagates to unfinished tasks: [Python asyncio task documentation](https://docs.python.org/3.11/library/asyncio-task.html).
- Multi-agent debate research starts agents independently and exposes peer answers only after all initial responses exist, which motivates the explicit first-round barrier here: [Du et al. — Improving factuality and reasoning in language models through multiagent debate](https://arxiv.org/abs/2305.14325).
- Later evaluation finds that debate-style methods do not consistently outperform single-agent baselines, so reviews must remain advisory evidence rather than presumed truth: [The Debate Over Multi-Agent Debate](https://arxiv.org/abs/2502.08788).
- Critic-model research reports useful error discovery alongside hallucinated or nitpicky critiques, reinforcing the need to label findings as unadjudicated: [OpenAI — CriticGPT paper](https://cdn.openai.com/llm-critics-help-catch-llm-bugs-paper.pdf).

The central design constraint is stronger than merely starting several tasks: every reviewer must operate on the same immutable, sanitized snapshot, publish nothing until the barrier, and never receive another reviewer's output during round one.

## 4. Requirements

### Functional Requirements

1. A caller can configure ParallelPanelAlgorithm directly or through ContextWindow.preset.parallel_panel.
2. reviewer_count defaults to 3 and must be at least 2.
3. min_successful_reviews defaults to 2 and must be between 2 and reviewer_count, inclusive.
4. max_concurrency is optional. When set, it must be between 2 and reviewer_count, inclusive.
5. Per-reviewer and whole-panel timeouts are independently optional and must be positive when present.
6. The algorithm runs the producer exactly once through AgentRuntime._arun_once.
7. Blank producer output is rejected before any reviewer call.
8. A candidate above max_candidate_chars is rejected before any reviewer call. It is never truncated, because truncation would violate the exact-same-candidate contract.
9. A reviewer snapshot contains only:
   - the original user task passed to the algorithm;
   - the exact producer candidate;
   - context artifacts whose names appear in artifact_names, in configured name order.
10. Unknown artifact names fail closed before reviewers start.
11. Each allowed artifact must fit `max_artifact_chars`, and all allowed artifacts together must fit `max_total_artifact_chars`; an oversized evidence set fails preflight rather than being truncated.
12. Every reviewer receives byte-identical system and user prompt strings.
13. Reviewers do not receive producer messages, system prompt, scratch reasoning, tool calls, tool results, context items, memory, raw provider response, runtime metadata, filesystem paths, or unlisted artifacts.
14. Reviewers are model-only in version 1: no tools or MCP access are bound to reviewer calls.
15. Reviewer tasks use local return values; they do not append findings to shared state while running.
16. No finding is copied into AgentResult metadata, recorder slots, another prompt, or a callback until the first-round gather completes.
17. Successful reviews are bounded to max_review_chars and returned in reviewer-1 through reviewer-N configuration order.
18. Reviewer errors and timeouts are represented by bounded, sanitized failure summaries in the same stable order.
19. Each reviewer call runs through a fresh reviewer runtime with an empty middleware pipeline, `include_internal_tools=False`, no context manager, no output contract, and a freshly constructed allowlist-only context.
20. Ordinary raw runner results are converted with RunnerHandle.extract_text and must contain a nonblank review.
21. If at least min_successful_reviews succeed after the barrier, the producer result is returned with review metadata.
22. If fewer than min_successful_reviews succeed, the algorithm raises AgentExecutionError and does not publish partial findings.
23. A panel timeout cancels unfinished reviewers and fails the whole algorithm without publishing findings.
24. Caller cancellation propagates, cancels unfinished reviewer tasks, closes trace spans, and publishes no findings.
25. AgentResult.output and AgentResult.structured remain the producer values.
26. Producer calls and existing producer metadata remain available on the returned result.
27. The returned `strategy_name` remains exactly the producer strategy; `metadata["parallel_panel"]` identifies the reviewing algorithm without changing the producer result contract.
28. Version 1 stops after review collection. It performs no worker revision, second review round, judge call, or synthesis call.

### Non-Functional Requirements

1. Reviewer ordering is deterministic and independent of task completion order.
2. Algorithm-specific semantic spans do not copy review bodies or the full candidate into their structural attributes; nested llm.call spans retain the SDK's existing bounded prompt/output tracing policy.
3. Metadata, error text, artifact text, and review text are bounded.
4. Standard SDK asynchronous runners may overlap reviewer calls; custom synchronous runners are supported with documented constrained-concurrency semantics.
5. The implementation must not offload arbitrary custom synchronous runners to threads because their thread-safety is unknown.
6. The implementation uses no new third-party runtime dependency.
7. Configuration validation raises the repository-standard ConfigurationError with field-specific messages.
8. Runtime failures use AgentExecutionError and preserve cancellation as cancellation.
9. The feature remains additive: existing context-window configurations behave unchanged.
10. Linear text runtime restrictions and the existing at-most-one-context-window-algorithm rule remain unchanged.
11. The result metadata shape uses immutable tuples where practical and does not expose mutable internal branch state.
12. Producer middleware remains unchanged, but no producer middleware object or model-visible transform is inherited by reviewer calls.
13. Timeout guarantees are cooperative: they can cancel asynchronous runner calls, but they cannot preempt a custom synchronous runner while it blocks the event-loop thread.
14. Every implementation function and method signature is written on exactly one line, followed immediately by a one- or two-line explanatory code comment; non-trivial orchestration is class-first.

### Acceptance Criteria

1. A three-reviewer run invokes one producer and three review calls, and every review call receives identical rendered prompt strings.
2. A controlled completion order of reviewer-3, reviewer-1, reviewer-2 still yields metadata ordered reviewer-1, reviewer-2, reviewer-3.
3. Inspection of reviewer call arguments confirms that only task, exact candidate, and allowlisted artifacts are present.
4. No reviewer prompt contains a peer finding, even when bounded concurrency causes later batches to start after earlier calls finish.
5. No review appears in the returned object or recorder before the gather barrier.
6. One branch failure can still return a result when the success threshold is met; falling below the threshold fails the algorithm.
7. Per-reviewer timeout behaves as a branch failure; panel timeout and caller cancellation publish no findings.
8. The final output exactly equals the producer candidate and no revision call occurs.
9. The context template validates the configured count of review-scheduling slots and one barrier/collection sequence.
10. Existing non-parallel-panel configurations resolve and run unchanged.

## 5. High-Level Design

The runtime sequence is:

    original task
         |
         v
    normal producer run
         |
         v
    validate exact candidate and select allowlisted artifacts
         |
         v
    render one immutable reviewer snapshot
         |
         +--------------+--------------+
         |              |              |
         v              v              v
    reviewer-1     reviewer-2     reviewer-N
    local result    local result    local result
         |              |              |
         +--------------+--------------+
                        |
                        v
             first-round gather barrier
                        |
             +----------+----------+
             |                     |
             v                     v
       threshold met        threshold not met,
       stable collection    panel timeout, or cancel
             |                     |
             v                     v
    producer output plus       fail without
    advisory metadata          publishing findings

The public configuration is converted into an outer ParallelPanelRuntimeAlgorithm by the existing dispatcher. The producer uses the host RunnerHandle and the original runtime context. The adapter then builds a new sanitized BaseAgentContext for each model-only reviewer call, but every call receives the same pre-rendered system and user strings. Reviewer identity is carried only by the coordinator and the algorithm-specific reviewer trace span; it is not passed to model-visible input or middleware metadata.

All reviewer coroutines are created before collection. asyncio.gather(..., return_exceptions=True) is used as the barrier because the design intentionally permits partial branch failure and needs all branches to settle before policy is applied. An optional semaphore constrains in-flight calls without weakening isolation. Results are processed by configured index, not completion time.

The adapter returns the original producer result fields unchanged with a namespaced parallel_panel metadata record. Reviews are not treated as accepted defects: they are labeled independent, first-round, and unadjudicated.

## 6. Detailed Design

### 6.1 Public configuration

Create vidbyte/context/algorithms/parallel_panel.py with:

    @dataclass(frozen=True, slots=True)
    class ParallelPanelAlgorithm:
        reviewer_count: int = 3
        min_successful_reviews: int = 2
        max_concurrency: int | None = None
        per_reviewer_timeout_seconds: float | None = None
        panel_timeout_seconds: float | None = None
        max_candidate_chars: int = 50_000
        max_review_chars: int = 6_000
        artifact_names: tuple[str, ...] = ()
        max_artifact_chars: int = 4_000
        max_total_artifact_chars: int = 16_000
        reviewer_system_prompt: str | None = None
        reviewer_prompt: str | None = None
        metadata: Mapping[str, Any] = field(default_factory=dict)

Validation in __post_init__ follows the existing frozen-config style:

- Reject bool where integer counts are expected.
- reviewer_count must be between 2 and a defensive upper bound of 16.
- min_successful_reviews must be between 2 and reviewer_count.
- max_concurrency, when present, must be between 2 and reviewer_count.
- Both timeouts must be finite positive numbers no greater than 3,600 seconds when present.
- max_candidate_chars must be between 1 and 100,000.
- max_review_chars, max_artifact_chars, and max_total_artifact_chars must each be between 1 and their documented defensive maxima.
- artifact_names must contain unique, nonblank strings.
- Custom prompt strings must be nonblank.
- The set of named placeholders in reviewer_prompt must be exactly {task}, {candidate}, and {artifacts}; repeated uses are allowed, while unknown or missing names are rejected.
- metadata keys must be strings. The runtime copies metadata at its use boundaries, matching neighboring algorithm configs.

The prompt overrides allow advanced callers to change review criteria without changing isolation. They do not permit new model-visible inputs.

### 6.2 Prompt catalog

Add a parallel_panel prompt family with:

- reviewer_system_prompt.md: define an independent reviewer, require concrete and supported findings, distinguish blocking from nonblocking issues, cite candidate or artifact evidence, avoid inventing missing context, and state that no peer finding is available.
- review_prompt.md: delimit Original Task, Candidate, and Permitted Artifacts; request a stable Markdown response with Summary, Findings, and Overall Assessment sections.
- parallel_panel.json: register both assets with the existing prompt loader.

Add matching Prompt enum values in vidbyte/lib/enums/prompts.py. The existing dynamic prompt package export and package-data wildcards already cover the new family; no prompt package initializer or packaging change is needed.

The default user prompt is rendered exactly once. The implementation must use named interpolation that rejects missing or extra fields rather than progressively formatting separate reviewer copies.

### 6.3 Artifact selection and sanitized reviewer context

Before scheduling reviewers, the adapter snapshots context artifacts by exact ContextArtifact.name:

1. Build a name-to-artifact index from runtime context artifacts only.
2. Reject duplicate available artifact names if they would make selection ambiguous.
3. Resolve every configured artifact name in artifact_names order.
4. Raise AgentExecutionError if a requested name does not exist.
5. Render only artifact name, declared type, and exact content. Do not include artifact metadata unless a future explicit field permits it.
6. Reject any artifact above `max_artifact_chars` or an evidence set above `max_total_artifact_chars`; never truncate reviewer evidence.
7. Render a fixed no-permitted-artifacts marker when artifact_names is empty.

Each review call receives a newly constructed empty BaseAgentContext rather than the producer's context object. The call has no messages, tools, context items, memories, or handles attached. It uses call_options containing only the reviewer system prompt and the same model-visible user prompt.

The adapter constructs a fresh reviewer `AgentRuntime` with an empty `MiddlewarePipeline`, empty `Tools`, `include_internal_tools=False`, no context manager, no output contract, a `NullRecorder`, the default/no-op context-window algorithm, and the shared tracer. The model-only review call uses that fresh runtime's `_invoke_with_middleware`; it must never use the producer runtime or inherit producer middleware. The fresh runtime preserves provider parsing and `llm.call` tracing while making the model-visible boundary auditable.

### 6.4 Producer stage

The runtime adapter invokes:

    await runtime._arun_once(message, handle=handle, context=context, metadata=producer_metadata, options=dict(options or {}), trace_context=trace_context)

It records the algorithm system-prompt slot and parallel_panel_producer slot at the same structural points used by existing outer algorithms.

After the producer completes:

- Convert output to the established text form without changing producer output semantics.
- Reject blank output.
- Reject output longer than max_candidate_chars rather than truncating it.
- Calculate candidate length and a SHA-256 digest for identity checks. The full candidate is not duplicated into metadata.
- Preserve calls, structured output, and existing producer metadata for the final result.

### 6.5 Reviewer scheduling, isolation, and barrier

Reviewer identities are reviewer-1 through reviewer-N. Identity is stable and appears in the coordinator's local outcome and the algorithm-specific reviewer trace span, but not in the reviewer prompt. Every invocation receives its own empty `run_state` dictionary; the reviewer pipeline itself is empty, so producer middleware cannot inject messages or share state.

For every reviewer index, create a coroutine that:

1. Enters the optional semaphore.
2. Opens a semantic parallel_panel.review child span beneath algorithm.parallel_panel.
3. Calls the fresh reviewer runtime's `_invoke_with_middleware` with a new sanitized context, identical prompt strings, minimal stage metadata, and a fresh empty run_state.
4. Wraps the call in asyncio.wait_for when per_reviewer_timeout_seconds is configured.
5. Treats any unexpected non-text runtime result as a controlled reviewer failure rather than criticism.
6. Converts ordinary raw responses with handle.extract_text and treats blank output as a branch failure.
7. Applies deterministic max_review_chars bounding after successful completion.
8. Returns a local immutable success or failure value.
9. Closes the child span for success, Exception, timeout, and BaseException cancellation.

The coordinator records parallel_panel_review scheduling slots synchronously in reviewer-index order before awaiting the tasks. It then awaits:

    asyncio.gather(*reviewer_coroutines, return_exceptions=True)

The optional whole-panel timeout wraps that gather. This choice has deliberate semantics:

- gather creates the collection barrier and preserves input order in its result sequence.
- return_exceptions=True prevents one ordinary reviewer failure from cancelling healthy peers.
- The collector does not inspect any local success value until gather returns.
- A semaphore limits in-flight calls but never passes completed findings into waiting calls.
- A panel timeout cancels the gather and therefore unfinished tasks. The adapter awaits their cancellation cleanup before raising.
- Caller cancellation is re-raised after cleanup and is never converted to an ordinary branch failure.
- Collection checks BaseException values so cancellation-like outcomes cannot be mistaken for successful reviews.

For a standard runner with arun, the calls can overlap. For a custom runner with only synchronous run, the event loop may be blocked and true overlap cannot be promised. In that case, asyncio timeouts also cannot fire until the runner yields or returns. The implementation records runner_async_capable and a concurrency mode such as unbounded_async, bounded_async, or sync_constrained. It does not use asyncio.to_thread because custom runner thread-safety is outside the SDK contract.

The same RunnerHandle is used for every reviewer so the evaluation setup is identical. This assumes a custom asynchronous runner is safe for concurrent calls; that limitation is documented and remains an open extension point.

### 6.6 Failure policy and deterministic collection

After the barrier, the collector walks the gather result in reviewer-index order.

A successful review record contains:

    {
        "reviewer_id": "reviewer-1",
        "reviewer_index": 0,
        "content": "...bounded review...",
        "content_chars": 1234,
        "truncated": false
    }

A failure record contains:

    {
        "reviewer_id": "reviewer-2",
        "reviewer_index": 1,
        "error_type": "TimeoutError",
        "reason": "...bounded and sanitized..."
    }

Failure reasons must not include prompt bodies, candidate bodies, provider response bodies, secrets, or unbounded exception representations. Known failures use stable SDK-authored reason strings; unknown exception messages are conservatively bounded and sanitized using the repository's existing error conventions.

If the success count is below min_successful_reviews, raise AgentExecutionError after all branches settle. Although local results existed, no recorder collection slot or AgentResult metadata is emitted. If the threshold is met, record parallel_panel_barrier followed by parallel_panel_collection and build the final result.

Panel timeout is not a partial-success condition. It fails the entire algorithm because the first-round barrier did not complete. Caller cancellation has the same no-publication guarantee.

### 6.7 Result contract

Construct a new AgentResult that preserves:

- output from the producer unchanged;
- structured from the producer unchanged;
- calls from the producer unchanged;
- strategy_name from the producer unchanged;
- all producer metadata, subject to the current merge convention.

Add the following namespaced metadata without replacing the producer strategy:

    {
        "context_window_algorithm": "parallel_panel",
        "parallel_panel": {
            "candidate_chars": 1234,
            "candidate_sha256": "...",
            "configured_reviewer_count": 3,
            "successful_review_count": 2,
            "minimum_successful_reviews": 2,
            "review_order": ("reviewer-1", "reviewer-3"),
            "reviews": (...ordered success records...),
            "failures": (...ordered failure records...),
            "barrier_completed": true,
            "peer_findings_visible_during_round": false,
            "findings_adjudicated": false,
            "candidate_revised": false,
            "concurrency": {
                "max_concurrency": null,
                "runner_async_capable": true,
                "mode": "unbounded_async"
            },
            "artifact_names": (...),
            "...caller metadata...": "..."
        }
    }

Caller-supplied algorithm metadata is nested or merged only where it cannot overwrite SDK-owned invariants. Reviews are explicitly first-round, independent, and unadjudicated. The candidate itself is not repeated in this metadata.

### 6.8 Dispatcher, wrapper, preset, and exports

Extend ContextWindowAlgorithm's supported algorithm union with ParallelPanelAlgorithm while preserving its frozen validation and single-runtime-algorithm rule.

Add:

    ContextWindow.preset.parallel_panel(...)

The preset accepts the same public fields, constructs ParallelPanelAlgorithm, and returns the normal ContextWindowAlgorithm wrapper. String resolution in vidbyte/agents/context_algorithms.py recognizes parallel_panel and instantiates ParallelPanelRuntimeAlgorithm.

Export the public class and preset path through:

- vidbyte/context/algorithms/__init__.py
- vidbyte/context/__init__.py
- vidbyte/__init__.py
- vidbyte/agents/algorithms/__init__.py for the internal adapter

No behavior changes for existing algorithm identifiers or preset constructors.

### 6.9 Tracing and recorder template

The clean-main dispatcher already supplies algorithm.parallel_panel as the parent semantic span. Add one parallel_panel.review child span per reviewer so sibling calls are identifiable even though their prompt is identical. _invoke_with_middleware continues to create its normal llm.call child span.

Allowed trace attributes are bounded structural data:

- reviewer_id and reviewer_index;
- configured reviewer count;
- success, failure, or timeout status;
- character counts and review-output truncation flags;
- configured concurrency mode;
- barrier completion and success count.

The algorithm.parallel_panel and parallel_panel.review structural attributes must not add the original task, full candidate, artifacts, review content, provider response content, or raw exception bodies. The nested llm.call span continues to follow the repository's existing tracing contract, which records bounded provider-visible system/user prompts and bounded model output. This feature does not silently change global trace observability; callers who enable a remote tracer must treat the permitted task, candidate, artifacts, and review as trace-visible under that existing policy.

Create ParallelPanelContextWindowTemplate(reviewer_count) with expected slots:

1. system_prompt
2. parallel_panel_producer
3. parallel_panel_review repeated reviewer_count times, recorded at scheduling in index order
4. parallel_panel_barrier
5. parallel_panel_collection

The barrier slot records only structural completion metadata. The collection slot records counts and ordering, never review bodies. When panel timeout, cancellation, or insufficient success prevents publication, no collection slot is recorded. Update the context-window template skill documentation with this exact slot contract.

### 6.10 Documentation

Update vidbyte/context/README.md with:

- direct configuration and preset examples;
- the exact reviewer input allowlist;
- the fact that reviews are advisory metadata and output is not revised;
- cost and latency implications;
- timeout and partial-failure behavior;
- asynchronous versus synchronous custom-runner concurrency;
- a warning that custom asynchronous runners must support concurrent calls;
- a pointer to the context-window template.

Do not describe the algorithm as a specialist panel, voting panel, adjudicator, or revision workflow.

### 6.11 Manual verification

No test file or verification script is added. Before implementation handoff is considered complete, run:

1. python -m compileall vidbyte
2. python -m unittest discover -s tests
3. A one-off in-memory asynchronous fake-runner check that:
   - gives reviewers different delays;
   - captures their system prompt, user prompt, tools, context, stage metadata, and reviewer runtime identity;
   - verifies byte-identical prompts, distinct fresh runtimes, empty middleware pipelines, distinct empty run-state dictionaries, and empty reviewer capabilities;
   - verifies result ordering follows reviewer index rather than completion;
   - verifies AgentResult.output is the producer candidate.
4. Repeat the fake-runner check with one reviewer exception and a satisfied threshold.
5. Repeat below threshold and verify AgentExecutionError with no collection slot.
6. Exercise per-reviewer timeout, panel timeout, and caller cancellation; inspect task cleanup and trace closure.
7. Exercise a synchronous-only fake runner and verify metadata reports sync_constrained without claiming actual overlap.
8. Render a ContextWindow recorder trace and validate it with ParallelPanelContextWindowTemplate for two and three reviewers.

The one-off harness is not committed. Existing repository tests are regression evidence only; this workflow intentionally adds no new tests.

## 7. Data Model Changes

### 7.1 ParallelPanelAlgorithm

**Type:** New frozen public Python dataclass

**Persistence:** None

**Migration:** None

Fields are specified in section 6.1. The type is wrapped by the existing ContextWindowAlgorithm union. The runtime snapshots metadata before asynchronous scheduling so caller mutation during a run cannot alter reviewer behavior or result assembly.

### 7.2 Internal reviewer outcome

**Type:** New private immutable success/failure value in the runtime adapter

**Persistence:** None

**Migration:** None

The private type carries reviewer index, stable identifier, bounded content or bounded failure classification, character count, truncation flag, and status. It is returned locally by a reviewer coroutine and is not placed into shared mutable state.

### 7.3 AgentResult metadata

**Type:** Additive namespaced metadata

**Persistence:** Existing caller-controlled result handling only

**Migration:** None

The parallel_panel record described in section 6.7 is new. Existing top-level producer metadata remains compatible. Consumers that ignore unknown metadata are unaffected. Review records must be documented as unadjudicated observations, not validated defects.

### 7.4 Context artifacts

No ContextArtifact schema change is required. The algorithm reads existing artifact name, type, and content fields. It intentionally does not expose artifact metadata to reviewer prompts in version 1.

## 8. API Changes

### 8.1 Python: ParallelPanelAlgorithm

**Change type:** Additive public API

    from vidbyte import ParallelPanelAlgorithm

    algorithm = ParallelPanelAlgorithm(
        reviewer_count=3,
        min_successful_reviews=2,
        artifact_names=("requirements", "evidence"),
        per_reviewer_timeout_seconds=30.0,
    )

**Input:** Configuration fields in section 6.1.

**Output:** A validated immutable algorithm config.

**Errors:** ConfigurationError for invalid counts, timeouts, limits, artifact names, prompt placeholders, or metadata.

### 8.2 Python: ContextWindow.preset.parallel_panel

**Change type:** Additive public convenience API

    context_window = ContextWindow.preset.parallel_panel(
        reviewer_count=3,
        min_successful_reviews=2,
        max_concurrency=3,
    )

**Input:** The ParallelPanelAlgorithm configuration fields.

**Output:** ContextWindowAlgorithm wrapping ParallelPanelAlgorithm.

**Errors:** Same ConfigurationError behavior as direct construction.

### 8.3 Internal runtime isolation option

**Change type:** Backward-compatible internal constructor option

```python
def __init__(..., include_internal_tools: bool = True, ...) -> None:
    # Preserve current agents by default while allowing an exact-empty reviewer tool surface.
    ...
```

`AgentRuntime` keeps today's behavior when the option is omitted. Parallel-panel reviewer runtimes pass `False`; the producer runtime is unchanged.

### 8.4 Runtime result

**Change type:** Additive result metadata for runs configured with parallel_panel

**Request behavior:** The original message is processed once by the producer, then reviewed according to the configured panel.

**Response behavior:** AgentResult.output remains the producer candidate. AgentResult.metadata.parallel_panel contains bounded ordered reviews, failures, barrier state, and concurrency facts.

**Errors:**

| Condition | Behavior |
|---|---|
| Blank or oversized candidate | AgentExecutionError before review calls |
| Missing allowlisted artifact | AgentExecutionError before review calls |
| Ambiguous or oversized allowlisted artifact set | AgentExecutionError before review calls |
| Individual reviewer timeout/error | Ordered branch failure after barrier |
| Successful reviews below threshold | AgentExecutionError after all branches settle |
| Whole-panel timeout | Cancel unfinished tasks; AgentExecutionError; publish no findings |
| Caller cancellation | Cancel unfinished tasks; re-raise cancellation; publish no findings |

No HTTP endpoint, wire protocol, database schema, or environment variable changes are required.

## 9. File Change Manifest

### Files to Create

| # | File | Purpose |
|---:|---|---|
| 1 | docs/design/context-window-parallel-panel.md | Approved implementation contract and rationale |
| 2 | vidbyte/context/algorithms/parallel_panel.py | Frozen public configuration and validation |
| 3 | vidbyte/agents/algorithms/parallel_panel.py | Producer/reviewer orchestration, isolation, barrier, and result assembly |
| 4 | vidbyte/lib/templates/parallel_panel.py | Deterministic recorder template |
| 5 | vidbyte/prompts/prompts/parallel_panel/parallel_panel.json | Prompt family manifest |
| 6 | vidbyte/prompts/prompts/parallel_panel/reviewer_system_prompt.md | Independent reviewer system instructions |
| 7 | vidbyte/prompts/prompts/parallel_panel/review_prompt.md | Task/candidate/artifact review prompt |

### Files to Modify

| # | File | Purpose |
|---:|---|---|
| 1 | vidbyte/__init__.py | Export the public algorithm |
| 2 | vidbyte/agents/algorithms/__init__.py | Export the internal runtime adapter |
| 3 | vidbyte/agents/context_algorithms.py | Resolve and dispatch parallel_panel |
| 4 | vidbyte/agents/runtime.py | Add the backward-compatible `include_internal_tools` reviewer-isolation option |
| 5 | vidbyte/context/__init__.py | Export the public algorithm in the context namespace |
| 6 | vidbyte/context/algorithms/__init__.py | Export ParallelPanelAlgorithm |
| 7 | vidbyte/context/algorithms/tool_results.py | Add the algorithm to the supported wrapper union |
| 8 | vidbyte/context/presets.py | Add ContextWindow.preset.parallel_panel |
| 9 | vidbyte/lib/enums/prompts.py | Register the two prompt assets |
| 10 | vidbyte/lib/templates/__init__.py | Export ParallelPanelContextWindowTemplate |
| 11 | skills/vidbyte-sdk/context-window-templates.md | Document slot order and repetition |
| 12 | vidbyte/context/README.md | Document usage, guarantees, limits, and result semantics |

### Files to Delete

None.

### Manifest Summary

- Create: 7 files
- Modify: 12 files
- Delete: 0 files
- Total touched by implementation: 19 files

No test file, test fixture, verification script, root README, package initializer for the prompt family, or packaging configuration is included.

## 10. Dependencies & External Services

| Dependency or service | Change | Notes |
|---|---|---|
| asyncio, Python standard library | Existing | gather, Semaphore, wait_for, cancellation cleanup |
| hashlib, Python standard library | Existing | Candidate identity digest without storing candidate in metadata |
| Existing runner/provider | Increased calls | One producer call plus reviewer_count review calls |
| Existing tracer | Reused | Per-reviewer semantic spans and existing bounded model-call observability |
| Existing prompt loader | Reused | New prompt family is discovered by current packaging wildcard |
| New third-party package | None | No dependency update |

Provider rate limits, cost, and tail latency increase with reviewer_count. max_concurrency controls in-flight pressure, not total call count. A whole-panel timeout is a local orchestration policy and does not guarantee that a remote provider can retract already accepted work.

## 11. Rollout & Deployment

1. Obtain explicit approval of this design document.
2. Implement from clean main, using the Devil's Advocate branch only as non-authoritative structural precedent.
3. Keep the feature opt-in through direct configuration or the new preset; no feature flag or environment variable is necessary.
4. Run the manual verification in section 6.11 and the existing test suite.
5. Confirm generated/imported public API documentation includes the new export.
6. Review trace samples to ensure no task, candidate, artifact, or review body appears in attributes.
7. Release as an additive SDK feature under the repository's normal versioning process.

Rollback removes the new preset, union member, dispatcher branch, exports, runtime adapter, prompt family, template, and documentation. There is no persisted data or migration to reverse. Existing configurations never select the new algorithm implicitly.

## 12. Open Questions

1. Should a later version accept dedicated reviewer runner/provider specifications so reviewers can be model-diverse while still receiving identical inputs? The version-1 recommendation is no: use the host handle to keep one exact evaluation setup and avoid overlapping Multi-Provider Grader responsibilities.
2. Should a later version allow an explicit, immutable reviewer-tool allowlist backed by ephemeral isolated runtimes? The version-1 recommendation is no because shared mutable tools, MCP sessions, and tool results weaken the isolation guarantee.
3. Should caller metadata be stored under a dedicated user_metadata key rather than merged into parallel_panel? The implementation should follow the final convention established by the most recently merged context-window algorithm, while preventing overwrite of SDK-owned invariant keys.
4. Should insufficient-success failures expose only success/failure counts in AgentExecutionError, or also bounded reviewer IDs and failure classes? The recommendation is counts plus IDs/classes, never finding content.

## 13. Alternatives Considered

### Alternative 1: Reuse ParallelPipeline

Rejected. ParallelPipeline joins independent outputs into text and does not implement producer-then-review sequencing, sanitized reviewer input, threshold policy, per-reviewer identity, or an explicit no-publication barrier.

### Alternative 2: Run each reviewer with AgentRuntime._arun_once

Rejected. That path is designed for complete agent turns and would make tools, history, context items, memory, and mutable runtime state much easier to leak into reviewers. Model-only `_invoke_with_middleware` calls on fresh reviewer runtimes with sanitized contexts provide the required boundary.

### Alternative 3: Use asyncio.TaskGroup

Rejected for version 1. TaskGroup is fail-fast: an ordinary reviewer failure cancels siblings. This design intentionally lets all reviewers settle and permits partial success when the configured minimum survives. gather with return_exceptions=True matches that policy while still propagating coordinator cancellation.

### Alternative 4: Collect with asyncio.as_completed

Rejected. Completion-order collection would create nondeterministic output and tempt early publication. Input-ordered gather gives a natural first-round barrier and stable result order.

### Alternative 5: Stream findings to the producer or later reviewers

Rejected. It directly violates reviewer independence and the barrier. Bounded concurrency would also create an accidental hierarchy in which later batches see earlier batches.

### Alternative 6: Truncate an oversized producer candidate

Rejected. Reviewers would no longer inspect the exact candidate returned to the caller. Failing before review makes the contract honest and lets callers explicitly raise the bound.

### Alternative 7: Automatically synthesize, adjudicate, or revise

Rejected. Synthesis can conceal disagreement; adjudication and revision belong to Critique-Adjudicate-Revise; role-based opposition belongs to Prosecutor/Defender/Judge. Parallel Panel returns raw, ordered, advisory first-round findings only.

### Alternative 8: Fork full BaseAgent instances for reviewers

Rejected for version 1. The runtime adapter holds AgentRuntime and RunnerHandle, not the public BaseAgent orchestration boundary. Current BaseAgent.fork also shares a context manager unless explicitly replaced. Fresh sanitized model-call contexts are smaller and make the isolation boundary directly auditable.

### Alternative 9: Offload synchronous custom runners to worker threads

Rejected. The SDK does not currently guarantee that arbitrary custom runners, providers, middleware, or callbacks are thread-safe. The design reports sync_constrained semantics rather than manufacturing unsafe apparent concurrency.

### Alternative 10: Treat reviewer agreement as validated truth

Rejected. Same-model reviewers can share correlated blind spots, and critic models can hallucinate or nitpick. Findings remain unadjudicated evidence; consumers decide how to use them.
