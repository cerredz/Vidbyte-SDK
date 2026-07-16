# Design Doc: Pairwise Tournament Context-Window Algorithm

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

This feature adds a `pairwise_tournament` return-level context-window algorithm to the Vidbyte SDK. It creates two or more independent candidate answers, assigns opaque SDK-owned candidate IDs, places them into a deterministic single-elimination bracket, and compares one pair at a time until one candidate remains. All matches in a round may run concurrently, but the next round cannot start until the current round's match barrier closes.

Every comparison is position-balanced: the same two exact candidates are judged twice with their A/B positions reversed. A deterministic resolver maps the two slot decisions back to candidate IDs. Unresolved disagreement or abstention receives one bounded bidirectional rejudge; if it still cannot be resolved, the configured fail-closed or lower-seed policy applies. Judges never receive candidate provider/model identity, private producer history, seed, prior wins, bracket path, peer decisions, or another match's rationale.

The winning producer result is authoritative. The returned `AgentResult` uses the winner's exact `output`, `structured`, `calls`, and existing metadata, changes `strategy_name` to `pairwise_tournament`, and adds a bounded bracket report under `metadata["pairwise_tournament"]`. Losing candidate and judge text is not copied into top-level result fields.

---

## 2. Goals & Non-Goals

### Goals

- Expose `ContextWindow.preset.pairwise_tournament` and string resolution for `"pairwise_tournament"`.
- Produce 2-16 independent candidates from an explicit provider/model map or the SDK's active provider map.
- Give every candidate the same original task and authorized producer context without exposing peer candidates.
- Assign neutral `candidate-001` IDs and hide provider/model/source identity from every judge.
- Build a deterministic single-elimination bracket with specified seeding, pairings, round barriers, and byes.
- Compare the exact same candidate pair in both A/B orders to reduce position bias.
- Require strict typed decisions that select only slot A, slot B, or abstain; a judge cannot author a replacement candidate.
- Support exact, deny-by-default judge artifact/tool allowlists and a dedicated judge provider/model.
- Make timeouts, cancellation, candidate failure, match failure, tie, abstention, and fallback behavior explicit.
- Return the exact winning candidate and preserve its structured output, calls, and metadata.
- Provide prompt assets, public types, exports, preset/dispatcher wiring, recorder template, documentation, and manual verification criteria.

### Non-Goals

- No all-pairs ranking, Elo/Bradley-Terry scoring, round robin, Swiss pairing, or reusable leaderboard.
- No free-form synthesis, candidate merge, revision, or judge-written replacement answer.
- No claim that a knockout bracket identifies a globally best candidate or that LLM judging is unbiased.
- No candidate-to-candidate debate and no judge communication across matches or rounds.
- No disclosure of producer scratch reasoning, system/private history, tool transcripts, memory, context-manager state, or provider identity to judges.
- No automatic judge access to producer tools, artifacts, file paths, MCP sessions, or metadata.
- No mutating judge tools; version 1 admits only explicit `SAFE` or `READ` tools.
- No database, persistence migration, HTTP endpoint, new dependency, unit test, or verification script.

---

## 3. Background & Context

### Research basis

Pairwise comparison is a common alternative to asking a model for an absolute score. [LLM-Blender](https://arxiv.org/abs/2306.02561) uses pairwise ranking to compare candidates before fusion, while [Pairwise Reward Model for LLMs](https://arxiv.org/abs/2501.13007) evaluates knockout-style pairwise selection. These support the comparison primitive, not a guarantee that one bracket is globally optimal.

Position is itself a source of judge bias. [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) documents position and related biases. Version 1 therefore runs both A/B orders and resolves decisions only after mapping slot choices back to stable candidate IDs. The algorithm records unresolved comparisons instead of converting judge uncertainty into silent certainty.

### Repository audit

The implementation base is clean `main` at `213d337`; the current user checkout is dirty and is used only to hold this approval-gated document. The SDK already has a closely related return-level algorithm, `MultiProviderAgenticGraderAlgorithm`, which resolves provider/model candidates, runs provider trials with `asyncio.gather`, invokes a grader, and constructs an `AgentResult`. It is precedent for candidate production and provider substitution, but it exposes labeled candidates to one grader and accepts loose text matching. Pairwise Tournament replaces that final stage with opaque identities, strict typed choices, isolated judge runtimes, deterministic rounds, and exact referential checks.

`AgentRuntimeContextAlgorithms` dispatches return-level algorithms after configuration validation. `ContextWindowAlgorithm` enforces one active algorithm. `Tools.subset` performs exact-name selection, and clean main's fork work establishes `clone_for_fork` as the safe path for tools with mutable bindings. `AgentRuntime` currently injects `isDone`; exact judge allowlists therefore require the same backward-compatible `include_internal_tools=False` option specified by the sibling adversarial-review designs.

### Core invariants

For a match containing canonical candidates X and Y:

```text
leg 1 visible input = original task + exact X as slot A + exact Y as slot B + permitted evidence
leg 2 visible input = original task + exact Y as slot A + exact X as slot B + permitted evidence
```

The system/user prompt bytes other than the swapped candidate slots are identical. A judge sees neither `candidate-###` IDs nor source/provider labels. Candidate digests, seed, round, match, prior results, and bracket metadata remain coordinator-only.

---

## 4. Requirements

### Functional Requirements

1. `PairwiseTournamentAlgorithm` is a frozen slots dataclass and is selectable directly or through `ContextWindow.preset.pairwise_tournament`.
2. `provider_models` is an optional ordered provider-to-model mapping resolved by `ProviderModelRegistry`; runtime resolution must yield 2-16 distinct candidate sources.
3. Each source runs the original task once through the normal producer loop with its selected runner and an isolated candidate-local runtime/context state. Candidate tasks launch concurrently and cannot observe peer output.
4. Candidate producer middleware, tools, permission policy, output schema, and authorized producer context remain producer concerns. Candidate-local mutable tool/context objects must not be shared concurrently; cloneable tools use `clone_for_fork`, and unsupported live bindings fail preflight.
5. All candidate sources receive the same original message and equivalent producer-visible starting context. No previous candidate output or candidate failure is appended to another candidate's context.
6. Candidate failures are collected behind a full candidate barrier. The default `require_all_candidates=True` fails if any configured source fails; an explicit false value may continue only when at least two candidates succeed and must record omitted source IDs without error bodies.
7. Successful candidates are restored to configured source order and receive SDK-owned IDs `candidate-001` through `candidate-NNN`. Provider/model/source labels are stored only in coordinator provenance and never rendered for judges.
8. A candidate must be nonblank and no longer than `max_candidate_chars`. It is never normalized, summarized, or truncated before judging.
9. Seeding is deterministic: `INPUT_ORDER` uses candidate ID order; `CONTENT_HASH` sorts by SHA-256 digest then candidate ID. The effective seed order is recorded as IDs/hashes, never candidate text.
10. A round pairs adjacent seeded entrants. With an odd count, the final unpaired entrant receives the round's only bye. Bye placement and advancement are deterministic and recorded.
11. All non-bye matches in a round are scheduled before one `asyncio.gather(..., return_exceptions=True)` barrier. No next-round match starts until every current-round match settles or the round fails.
12. `max_concurrency` limits in-flight matches without changing pairings or result order. Match records remain bracket order regardless of completion order.
13. Every judgment leg uses a fresh `AgentRuntime`, empty middleware pipeline, no context manager, no output contract, a `NullRecorder`, the strict judge output schema, `include_internal_tools=False`, and a newly constructed allowlist-only context with `agentic_loop=False`.
14. Judge input contains exactly the original task, slot A candidate, slot B candidate, and exact permitted artifacts. It excludes all candidate histories, system prompts, tool calls/results, raw responses, structured values, metadata, source labels, private options, and peer decisions.
15. Judge artifacts are selected by exact unique name. Missing names, ambiguous duplicate names, per-artifact oversize, or total evidence oversize fail preflight; evidence is never truncated.
16. Judge tools are selected from `runtime.user_tools` by exact name. Selected tools use `clone_for_fork` when available; unknown, mutating, agent-bound, session-bound, MCP/live, or otherwise unsafe uncloneable tools fail preflight.
17. A dedicated judge provider/model pair is optional; both values or neither are required. With neither, the incoming runner is used only as stateless transport by a fresh judge runtime.
18. Each judge leg returns provider-native structured output with `winner_slot` equal to `A`, `B`, or `abstain`, plus bounded criteria assessments and rationale. Extra fields and free-form candidate replacements are forbidden.
19. The runtime maps slot decisions to canonical candidate IDs. If both legs select the same canonical candidate, that candidate advances.
20. If legs disagree, both abstain, or exactly one abstains, the match is unresolved. The runtime may run at most `max_tiebreak_attempts` additional bidirectional pairs, each with fresh runtimes and no prior decision/rationale in its prompt.
21. After the tiebreak limit, `UnresolvedMatchPolicy.RAISE` fails the tournament by default. Explicit `LOWER_SEED` advances the lower effective seed and marks the advancement as policy-selected, not judge-selected.
22. `MatchFailurePolicy.RAISE` is the default. Explicit `LOWER_SEED` may resolve an ordinary leg failure only after sibling legs/tasks are cancelled and awaited; process/caller cancellation always propagates.
23. Per-leg, per-match, and optional per-round timeouts are independently validated. A timeout cannot publish a partial winner before cleanup and policy resolution.
24. The judge cannot select a candidate outside its pair. Typed slot output and coordinator mapping enforce this without exposing candidate IDs to the model.
25. Winners advance in canonical match order. The tournament terminates only when exactly one entrant remains or a configured fail-closed condition raises.
26. The returned `AgentResult.output`, `structured`, `calls`, and pre-existing metadata come from the winning candidate result. Losing producer and judge calls are not merged into the winner's top-level calls or `metadata["tool_calls"]`.
27. `strategy_name` is `pairwise_tournament`. Versioned additive metadata contains winner ID/hash/source provenance, candidate hashes, seed order, rounds, byes, leg slot decisions mapped to candidate IDs, resolution source, failures, timing, and bounded accounting. It contains no candidate body, prompt, rationale, tool argument/result, or raw exception.
28. Recorder slots are deterministic: `system_prompt`, `pairwise_tournament_candidate_fanout`, `pairwise_tournament_candidate_barrier`, one `pairwise_tournament_round` per completed round, and `pairwise_tournament_winner`; failures append `pairwise_tournament_failure` after the last completed structural slot.
29. Semantic tracing creates candidate, round, match, and leg child spans. Algorithm-specific attributes are content-free IDs, hashes, counts, status, timing, and configured policy labels; raw task/candidate/artifact/decision/tool/exception content is forbidden.
30. Prompt bodies are catalog-backed, overrideable only through validated templates, and treat task/candidate/artifact text as untrusted evidence.

### Non-Functional Requirements

- **Determinism:** identical successful candidates, configuration, and decisions yield the same IDs, bracket, byes, resolution, and metadata ordering.
- **Isolation:** judge contexts are positive projections. New producer-context fields remain excluded unless a future explicit allowlist adds them.
- **Bias control:** every decisive comparison uses both candidate orders; one unbalanced leg can never directly advance a candidate.
- **Boundedness:** candidate count, input/output/evidence sizes, calls, tiebreaks, timeouts, concurrency, and report size have defensive maxima.
- **Reliability:** all fan-outs have barriers, cancellations are awaited, defaults fail closed, and fallback winners are explicitly labeled.
- **Compatibility:** default/raw behavior and existing algorithms are unchanged when the field is unset.
- **Implementation style:** every implementation function and method signature is exactly one line, followed immediately by a one- or two-line explanatory code comment; non-trivial orchestration is class-first.

### Acceptance Criteria & Manual Verification

1. A four-candidate fake run starts every candidate before releasing the candidate barrier and produces the declared seed order.
2. Three, five, and six candidates produce deterministic byes/pairings and exactly one final entrant.
3. Captured leg prompts prove exact swapped candidate bytes and no source ID/provider/history/prior-match sentinel leakage.
4. Reversed completion order does not change match or round metadata order.
5. Two legs that map to one canonical winner advance it; disagreement triggers only the configured bounded tiebreak path.
6. Persistent disagreement raises by default and is visibly lower-seed-selected only with explicit policy.
7. Unknown/ambiguous/oversized artifacts and unsafe tools fail before the first judge call.
8. The returned output/structured/calls/metadata equal the winning producer result except for strategy name and namespaced tournament metadata.
9. Structural trace attributes contain no prompt, candidate, artifact, rationale, tool, or exception bodies.
10. Run `python -m compileall vidbyte`, the existing repository regression suite, and package build commands. No new test or verification file is added.

---

## 5. High-Level Design

`PairwiseTournamentRuntimeAlgorithm` is a return-level adapter with three phases: isolated candidate fan-out, deterministic bracket execution, and winner-result assembly. Candidate production follows the multi-provider grader's provider-resolution precedent but does not expose provider labels to judges. Candidate output and structured data remain attached to an immutable `_TournamentCandidate` record.

The coordinator builds a `_TournamentBracket` from candidate IDs and digests. Each round snapshots entrants, creates match coroutines in bracket order, and waits at one barrier. A `_PairwiseMatchRunner` executes two fresh judge legs concurrently or as one locally coordinated pair, maps their slot outputs to candidate IDs, and invokes a bounded position-balanced tiebreak when necessary. Reviewer runtimes have no reference to the bracket object or result collection.

```text
original task + authorized producer context
                    |
        isolated candidate fan-out
                    |
             candidate barrier
                    |
        deterministic seed + byes
                    |
     round 1 matches (A/B + B/A) -- barrier
                    |
     round 2 matches (A/B + B/A) -- barrier
                    |
                  ...
                    |
             one winning record
                    |
    winning AgentResult + bracket metadata
```

---

## 6. Detailed Design

### 6.1 Public configuration and contracts

**File(s):** `vidbyte/context/algorithms/pairwise_tournament.py`, `vidbyte/lib/dataclasses/pairwise_tournament.py`
**Type:** New files

The configuration defines `TournamentSeeding`, `UnresolvedMatchPolicy`, `MatchFailurePolicy`, and frozen `PairwiseTournamentAlgorithm`. Core fields are `provider_models`, `require_all_candidates`, `seeding`, `judge_provider`, `judge_model`, `judge_artifact_names`, `judge_tool_names`, `max_concurrency`, `max_tiebreak_attempts`, leg/match/round timeouts, exact input limits, report limits, prompt overrides, and metadata.

Strict Pydantic `PairwiseJudgePayload` contains only `winner_slot`, bounded `summary`, and bounded criterion records. Trusted frozen records represent candidates, legs, matches, rounds, and the final report. Model output never supplies candidate IDs, bracket position, source provenance, or advancement policy.

Validation rejects booleans used as counts, unordered/invalid provider maps, fewer than two or more than sixteen resolved sources, partial judge provider/model pairs, duplicate resource names, negative/oversized limits, invalid policy values, and prompt overrides missing `{payload_json}`.

### 6.2 Candidate production

**File:** `vidbyte/agents/algorithms/pairwise_tournament.py`
**Type:** New file

`_CandidateRuntimeFactory` resolves provider/model sources, clones candidate-local mutable tools using the same rules as clean main's forking machinery, snapshots the authorized starting context, and constructs independent producer runtimes. Each candidate calls `_arun_once` with the exact original message, copied options, normal producer permission/output-schema behavior, and its own run state/context manager. No candidate runtime contains peer output or shared mutable branch state.

`asyncio.gather(..., return_exceptions=True)` forms the candidate barrier and retains configured source order. After policy checks, the coordinator validates exact outputs, assigns neutral IDs, stores SHA-256 digests, and retains provider/model labels only in trusted coordinator provenance.

### 6.3 Judge isolation and resource projection

`_JudgeRuntimeFactory` builds a fresh runtime for every leg with an empty `MiddlewarePipeline`, exact cloned safe/read tool subset, shared permission policy/tracer, local limits, `NullRecorder`, `context_manager=None`, the strict output schema, default context algorithm, and `include_internal_tools=False`. Its fresh `BaseAgentContext` contains only the judge system prompt, permitted tool specs/artifacts, safe opaque lineage, and `agentic_loop=False`.

Artifact projection indexes exact names and rejects duplicate matches. It copies only `name`, `artifact_type`, and exact `content`; metadata is empty. Tool projection starts at `runtime.user_tools`, rejects unknown or unsafe/live-bound tools, and clones when supported. Producer middleware and invocation options never enter judge runtimes.

### 6.4 Match resolution and bracket engine

`_PairwiseMatchRunner` renders one immutable payload per orientation and invokes two fresh legs. Each valid result is mapped from slot to canonical candidate ID. Agreement advances the common candidate. Unresolved results create another two-leg attempt up to the configured bound; prior rationales/decisions are not shown to the tiebreak judges.

`_TournamentBracket` pairs adjacent entrants, records an odd final entrant as a bye, schedules every match for the round, awaits the barrier, applies only configured failure/unresolved policies, and builds the next entrant tuple in bracket order. Lower-seed fallback is deterministic but recorded with `resolution="policy_lower_seed"` and `judge_consensus=False`.

### 6.5 Result assembly, tracing, and recorder

The adapter uses `dataclasses.replace(winner.result, strategy_name="pairwise_tournament", metadata=merged_metadata)`. Winner output/structured/calls remain exact. The report includes hashes and structural decisions, not candidate or rationale text. Candidate and judge token/model/tool counts are bounded summaries; raw stage calls remain in their own traces and never contaminate winning producer history.

Tracing opens `algorithm.pairwise_tournament` children for fan-out, candidates, rounds, matches, and legs. Only structural attributes are set. Recorder writes occur in coordinator order outside concurrent tasks. `PairwiseTournamentContextWindowTemplate(candidate_count, round_count)` validates the deterministic structural sequence.

### 6.6 Runtime flag, registry, prompts, and docs

`AgentRuntime.__init__` gains the backward-compatible `include_internal_tools: bool = True`; judge runtimes pass false. Add the algorithm field to `ContextWindowAlgorithm`, preset resolution, return-level dispatcher, exports, prompt enum/assets, template export, and README guidance. Prompt assets are a system role and a `{payload_json}` user template registered by one JSON descriptor.

---

## 7. Data Model Changes

`ContextWindowAlgorithm` gains:

```python
pairwise_tournament: PairwiseTournamentAlgorithm | None = None
```

New in-memory public types include the configuration/policy enums, strict judge payload, and immutable candidate/leg/match/round/report records. Successful configured runs add versioned JSON-safe `metadata["pairwise_tournament"]`; no stored schema, database, checkpoint format, or migration changes.

The report shape includes `schema_version`, status, candidate hashes/source provenance, seed order, round records, match/leg structural decisions, byes, fallback markers, winner ID/hash/source, counts, durations, and configured metadata. Content-bearing task/candidate/artifact/judge fields are excluded.

---

## 8. API Changes

Public Python additions are `PairwiseTournamentAlgorithm`, the policy enums, typed report contracts, `ContextWindow.preset.pairwise_tournament`, prompt enum values, and `PairwiseTournamentContextWindowTemplate`. Example:

```python
algorithm = PairwiseTournamentAlgorithm(
    provider_models={"openai": "configured-model", "anthropic": "configured-model"},
    judge_provider="openai",
    judge_model="configured-judge-model",
    judge_artifact_names=("requirements",),
)
```

Runtime errors use `ConfigurationError` for static/preflight invalidity and `AgentExecutionError` for candidate, match, timeout, unresolved, or bracket failure. Caller/process cancellation always propagates. No HTTP API changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-window-pairwise-tournament.md` | This design document |
| CREATE | `vidbyte/context/algorithms/pairwise_tournament.py` | Public config, policies, validation, and prompt rendering |
| CREATE | `vidbyte/agents/algorithms/pairwise_tournament.py` | Candidate fan-out, isolated judging, bracket, and result assembly |
| CREATE | `vidbyte/lib/dataclasses/pairwise_tournament.py` | Typed judge and trusted bracket/report contracts |
| CREATE | `vidbyte/lib/templates/pairwise_tournament.py` | Deterministic recorder template |
| CREATE | `vidbyte/prompts/prompts/pairwise_tournament/pairwise_tournament.json` | Prompt descriptor |
| CREATE | `vidbyte/prompts/prompts/pairwise_tournament/judge_system_prompt.md` | Judge role and isolation instructions |
| CREATE | `vidbyte/prompts/prompts/pairwise_tournament/judge_prompt.md` | Exact pair/evidence payload template |
| MODIFY | `vidbyte/agents/runtime.py` | Backward-compatible exact-tool-surface option |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add optional field and mutual exclusion |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public config/policies |
| MODIFY | `vidbyte/context/presets.py` | Add preset |
| MODIFY | `vidbyte/context/__init__.py` | Re-export public contracts |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect and dispatch return-level adapter |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export internal adapter |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export typed contracts |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Register two prompt keys |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export template |
| MODIFY | `vidbyte/__init__.py` | Root public exports |
| MODIFY | `README.md` | Usage, cost, bias, and failure guidance |
| MODIFY | `vidbyte/context/README.md` | Algorithm/result/isolation documentation |
| MODIFY | `skills/vidbyte-sdk/context-window-templates.md` | Document recorder slots |

Manifest totals: **8 created, 14 modified, 0 deleted (22 total)**. No test or verification-script file is added or modified.

---

## 10. Dependencies & External Services

No new dependency or service is introduced. Python 3.11 `asyncio` supplies fan-out/barriers/timeouts; existing Pydantic validates strict judge output; existing provider runners create candidates and judgments; existing tools/artifacts are available only through explicit projection. Cost is candidate runs plus at least two judgment calls per match, with additional bounded tiebreak calls. Rate limits and tail latency scale with candidate count and bracket depth.

---

## 11. Rollout & Deployment

- Implement only after explicit approval, from updated clean `main`, in `feat/context-window-pairwise-tournament` within an isolated worktree.
- Re-audit shared isolation infrastructure. If an earlier adversarial-review PR already added `include_internal_tools`, reuse it and update this manifest before material divergence.
- Start with two candidates, empty judge tools/artifacts, fail-closed policies, and a dedicated judge model in a non-production environment.
- Manually inspect exact candidate equality, swapped prompts, source-identity hiding, bracket/byes, fallback labels, winner-result equality, traces, latency, and cost.
- Release as opt-in; no feature flag or migration ordering is required.
- Rollback removes the preset/field/adapter/assets/exports/docs. Existing default algorithms remain unchanged; persisted metadata remains an opaque optional mapping.
- Add automated isolation, bracket, bias, failure, timeout, and result-preservation tests only in a separately authorized change.

---

## 12. Open Questions

- [ ] Should v1 support repeated samples from one provider/model, or only one candidate per ordered provider key? Current design follows the existing provider-map precedent; repeated sampling needs a separately named candidate-source contract.
- [ ] Should persistent disagreement default to lower-seed advancement for guaranteed completion? Current design defaults to `RAISE` so uncertainty is not silently converted into quality.
- [ ] Should a judge leg expose no tools at all in the first release? Current design permits explicit safe/read tools, but tool latency and closure state complicate exact position-balanced comparisons.
- [ ] Should each leg use a different judge model for correlated-bias reduction? Current design supports one configured judge transport and relies on context isolation; model-diverse judging would need a deterministic aggregation contract.
- [ ] Should the full typed tournament report gain a top-level `AgentResult` field later? Current design uses versioned metadata and preserves the winner's `structured` field.

---

## 13. Alternatives Considered

### Alternative 1: One grader sees all labeled candidates

Rejected. It reproduces Multi-Provider Agentic Grader, exposes source labels and all candidates at once, and does not implement pairwise advancement or round barriers.

### Alternative 2: One orientation per match

Rejected. A slot preference can determine advancement. Two reversed legs make position disagreement observable and mechanically resolvable.

### Alternative 3: Round robin or all-pairs ranking

Rejected. It gives richer global ordering but changes the requested knockout algorithm and increases comparisons from linear to quadratic.

### Alternative 4: Let the judge return revised/synthesized text

Rejected. The tournament must choose one of two exact candidates. Typed slot selection prevents invention and preserves winner provenance.

### Alternative 5: Feed prior wins or rationales into later rounds

Rejected. It creates anchoring and reputation effects. Every match judges only the original task, exact current pair, and permitted evidence.

### Alternative 6: Resolve every tie by lower seed without marking it

Rejected. It guarantees termination but falsely presents an arbitrary deterministic fallback as judge preference. Lower-seed advancement is explicit and opt-in.

### Alternative 7: Truncate oversized candidates or artifacts

Rejected. The judge would not compare the exact candidates/evidence claimed by the report. Oversize input fails before judgment.

### Alternative 8: Reuse the producer runtime for judges

Rejected. It can leak producer tools, middleware, history, context manager, output schema, and future fields. Fresh allowlist-built judge runtimes make isolation auditable.
