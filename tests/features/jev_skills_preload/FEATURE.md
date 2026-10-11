# Feature: Jev Request-Time Skills Preload

## High-Level Feature Description

An SDK caller can supply immutable skill documents through `JevAlignmentSettings.skills`. For each main-agent request, Jev classifies every configured skill against the request in one or more bounded yes/no calls. The runtime appends only independently passing full skill bodies to that run's effective system prompt and reports selected, skipped, unavailable, and usage outcomes through `JevAgent.response.skills`. The empty default makes the feature opt-in.

## Contract

- A caller may configure a `SkillDocument` or inline string; inline bodies keep exact text and receive deterministic names.
- Every candidate has a unique name and receives one fixed-index relevance question, grouped into stable-order batches when needed.
- Requests stay under conservative local UTF-8 JSON byte bounds; full skill text is never truncated. A candidate too large to fit alone is unavailable while other candidates continue.
- Caller fields remain structured, untrusted decision state. Question wording contains only generated identifiers, never caller-provided metadata or body text.
- Each candidate answer is scored with `DecisionModelHelper.score_noul` and the configured `skills_threshold` independently.
- A valid answer remains usable when a sibling answer is missing; missing or malformed answers make only their own candidate unavailable.
- Every batch is asked concurrently. A Jev SDK/request failure leaves only that batch's skills unavailable, every other batch keeps its outcome, and the main agent continues.
- Only selected full bodies are appended, in configuration order, after the existing effective system prompt. Caller context and agent settings remain unchanged.
- An explicit `options["system"]` value is the effective baseline and the provider receives that value with selected skill text appended.
- Gate stop and specialist delegation precede preload; both perform zero skill relevance calls.
- No configured skills perform zero skill relevance calls.
- `JevAgent.response.skills` holds ordered candidate metadata/status/probability and Jev usage, never candidate text, and resets for each run.
- Runtime prompt and tool mutations are restored on success, errors, and cancellation.

## Actors / Callers

- SDK callers configure inline or resolved documents on `JevAgentSettings.alignment.skills` and tune the yes threshold on `JevRuntimeSettings.skills_threshold`.
- `JevAgent` constructs `JevSkillsPreload` only for nonempty settings.
- `JevRuntime` invokes the narrow `JevPreload` context transform after prompt/tool alignment and before run-state setup, tool selection, and the main loop.
- `DecisionModelHelper` sends each TypeSafe batch and scores per-question noul answers.
- `JevResponse` writes the per-run result record exposed by `JevAgent.response`.

## Inputs and Preconditions

- The gate has passed and no specialist was chosen.
- Skill documents have nonblank name, description, and text; optional source is nonblank when supplied.
- Skill names are unique after inline strings are normalized.
- The relevance threshold is a finite probability from 0 through 1, inclusive.
- Each decision state contains the original request and only that batch's full candidate records without truncation.

## Observable Outcomes

- No configured skills produce no TypeSafe skill request and an empty outcome.
- A passing answer adds only its corresponding full skill text to the provider's system prompt.
- A below-threshold answer is skipped and does not alter the prompt.
- A missing/non-noul answer marks only that skill unavailable; sibling passing answers still inject their text.
- A request/provider SDK failure, including a reply without both token counts, sends no further batches; earlier batches can still inject selected skills, and the main run continues.
- An explicit `system` option remains the prompt baseline; the effective provider option includes selected text.
- The original context remains unchanged and repeated runs do not inherit prior skill text or temporary tools.
- Usage is carried with candidate outcomes as `JevUsage.total` of the answered requests; it is zero tokens when no request was answered.

## State Transitions

1. `JevResponse.start()` resets latest-run response fields.
2. The gate stops the request or delegates to a specialist, returning before skill preload; otherwise the main path continues.
3. Enabled prompt and tool alignment finish and update the run context.
4. The runtime selects the explicit caller `system` option as baseline when it is a string; otherwise the aligned context prompt is the baseline.
5. The preload greedily packs indexed questions under conservative UTF-8 JSON byte bounds, preserving global indices and full candidate text. Every batch is sent concurrently; an SDK failure leaves only that batch's skills unavailable.
6. Code scores each normalized noul independently, records every result, and appends selected full bodies in settings order.
7. Run-state setup, selector processing, and the inherited loop execute with the resulting context.
8. A `finally` block restores system prompt and tool fields and releases attached tool sessions.

## Invariants

- The default settings contain no skills and make no extra Jev call.
- Small collections fit in one skill request; larger collections use multiple bounded requests in stable configured order.
- Candidate identifiers depend only on configured tuple order; names and bodies cannot steer question prose or answer mapping.
- Every candidate body appears whole in decision state and, if selected, whole in the final run prompt.
- A missing answer affects only its candidate; a batch request failure selects none from that batch and leaves other batches unchanged.
- The response contains no skill body.
- No runtime mutation or injected prompt text is retained by a later run.
- The classifier checks relevance only; skill content is not executed or retrieved.

## External Dependencies

- Existing TypeSafe System One endpoint and `DecisionModelHelper` are the only external boundary.
- The generic `SkillDocument` is already resolved plain text; network/source loaders and native provider skill references are deferred.
- Tests replace the decision helper boundary and text runner with scripted fakes; no live credentials or network calls are required.

## Known Failure Modes

- A batch request failure makes its candidates and every later candidate unavailable; no text is truncated and batches answered before it retain independent results.
- A single candidate that exceeds local request bounds is unavailable without preventing later candidates from being classified.
- A missing or malformed individual answer is unavailable rather than a negative answer.
- Skill relevance is a model judgment and can be misclassified; the threshold remains caller configurable.
- A selected skill can contain unhelpful or unsafe instructions; this feature classifies topical usefulness and does not validate trust or safety.
- Cancellation and unexpected programming failures propagate, while runtime cleanup still restores mutations.
- A TypeSafe outage means no skills are injected; the user's ordinary request continues without them.

## Historical Regressions

None yet. Add a dated entry and a focused regression test for each fixed defect.

## Test Suite Map

- `tests/test_jev_skill_preload.py` covers settings, exact content, fixed question structure/token floor, independent scoring, failure behavior, response reset, runtime order, caller options, and cleanup.
- `scripts/test-jev-skills-preload.py` runs the complete focused module with PASS/FAIL reporting.
- `python scripts/test-jev-agent-scaffold.py`, `python scripts/test-jev-multipart-done-criteria.py`, `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py` cover existing Jev contracts, source rules, packaging, and the full suite.

## Omitted Testing Strategies

- Live TypeSafe/provider tests are omitted because they require credentials and make classification nondeterministic; scripted decision and text runners cover the boundary.
- Browser, UI, accessibility, persistence, and migration tests are omitted because this is an in-process request-time context transform with no UI or durable state.
- Concurrency and load tests are omitted because one JevAgent instance has no concurrent-run safety contract and the implementation adds one decision request per run.
- Provider-native skill source tests are deferred with the separate adapter work; this feature accepts resolved plain text only.
