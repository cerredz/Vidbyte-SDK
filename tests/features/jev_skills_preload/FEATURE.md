# Feature: Jev Request-Time Skills Preload

## High-Level Feature Description

An SDK caller lists where each skill lives in `JevAlignmentSettings.skills`: one of six declarative entries (`InlineSkill`, `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill`), an already-resolved `SkillDocument`, or an inline string. The first run that reaches the preload resolves the entries through the agent's own `SkillLoader`; then, for each main-agent request, Jev classifies every loaded skill against the request in one or more bounded yes/no calls. The runtime appends only independently passing full skill bodies to that run's effective system prompt and reports selected, skipped, unavailable (with a reason and a detail that names the fix), and usage outcomes through `JevAgent.response.skills`. The empty default makes the feature opt-in.

## Contract

- A caller may configure any of the six entries, a `SkillDocument`, or an inline string, mixed in one tuple; inline strings keep exact text and receive deterministic names, and names are unique across all of them.

## Skill Source Contract

- **Entries.** Each entry is a frozen, validated record whose read-only `type` is fixed by its class. Every field is checked at construction (`ConfigurationError` naming `<Class>.<field>`; `TypeError` for `type=` or a field the class lacks). Construction never reads a file, sends a request, or reads `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`; relative paths are pinned to the working folder at construction.
- **Sources.** `InlineSkill` is its own text (label `inline`). `LocalSkill` reads `<path>/SKILL.md` (label `local:<folder name>`). `SkillsShSkill` reads the copy `npx skills add` installed and checks `skills-lock.json` when the folder is `<root>/.agents/skills` (label `skills_sh:<source>/<name>[@<hash12>]`). `GitHubSkill` makes one commit lookup and at most one tree listing per `(repo, ref, token)` group, then one raw fetch per entry (label `github:<owner>/<repo>@<sha12>/<folder>/SKILL.md`). `AnthropicSkill` and `OpenAISkill` download the version content as a zip or a bare `SKILL.md`, read only `SKILL.md` in memory, and fall back from `latest` to the version the skill record names (label `<vendor>:<skill_id>@<version>`).
- **Content.** Only one `SKILL.md` is read per skill: strict UTF-8 with one byte-order mark removed, YAML frontmatter through `safe_load` with required `name` and `description`, and the exact bytes after the closing line as text. `SKILL.md` is capped at `SKILL_MARKDOWN_MAX_BYTES`, every other download at `SKILL_DOWNLOAD_MAX_BYTES`; nothing is extracted or written to disk, no subprocess runs, and nothing a skill mentions is fetched.
- **Requests.** Every request goes through `HttpTransport` with a 10 s timeout, one retry after 0.5 s for the transport's retryable statuses, a size cap, no redirects, and a 25 s deadline per step. A token or key is sent only in its own host's header, never appears in a repr, label, detail, or response, and a Vidbyte key (`vb_live_…`, padded or not) is never sent: the entry is `auth_failed` with no request.
- **Reasons.** An unusable skill is `unavailable` with exactly one reason and a non-blank detail: `not_installed`, `not_found`, `auth_failed`, `invalid_skill`, `too_large` (loading), `rate_limited`, `fetch_failed` (transient), and, set by the preload only, `decision_failed` (a failed Jev batch, a reply without token counts, or a missing answer) and `too_large` from batching (recomputed every run). A result that never loaded has `description` and `source` set to `None`.
- **Memory.** The loader lives exactly as long as its `JevAgent`. A document or a permanent reason is remembered for the agent's lifetime and never replaced; `rate_limited` and `fetch_failed` are never remembered and are retried on the next run that reaches the preload. Overlapping loads return the first remembered resolution, so `documents()` always matches the last load. A programming error while loading leaves `JevSkillsPreload.run` unchanged and reaches the `arun` caller as the cause of `AgentExecutionError` (the wrapping every failed run gets); cancellation propagates unchanged; neither remembers anything from that load. Two agents never share memory. To pick up a fixed source or a new key, create a new agent.
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

- SDK callers configure skill entries, resolved documents, or inline strings on `JevAgentSettings.alignment.skills` and tune the yes threshold on `JevRuntimeSettings.skills_threshold`.
- `JevAgent` constructs `JevSkillsPreload` only for nonempty settings; the preload builds the agent's one `SkillLoader` and loads pending entries at the start of each run it reaches.
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

- The TypeSafe System One endpoint through `DecisionModelHelper` decides relevance.
- Skill sources are resolved by the agent-agnostic `vidbyte.agents.skills` package (`SkillLoader`, one resolver per source, the shared `SkillFetch` step and `SkillMarkdown` parser): the local filesystem, `api.github.com`, `api.anthropic.com/v1`, and `api.openai.com/v1`, all through `HttpTransport`. `SkillDocument` remains the already-resolved form and is accepted unchanged.
- Tests replace the decision helper, the text runner, and `HttpTransport._send_once` with scripted fakes; local and skills.sh files live under `tmp_path`; no live credentials or network calls are required.

## Known Failure Modes

- A batch request failure makes its candidates and every later candidate unavailable; no text is truncated and batches answered before it retain independent results.
- A single candidate that exceeds local request bounds is unavailable without preventing later candidates from being classified.
- A missing or malformed individual answer is unavailable rather than a negative answer.
- Skill relevance is a model judgment and can be misclassified; the threshold remains caller configurable.
- A selected skill can contain unhelpful or unsafe instructions; this feature classifies topical usefulness and does not validate trust or safety.
- Cancellation and unexpected programming failures propagate, while runtime cleanup still restores mutations.
- A TypeSafe outage means no skills are injected; the user's ordinary request continues without them.
- A missing, private, moved, malformed, oversized, or unauthorized skill source makes only that skill unavailable with its reason; a hostile `SKILL.md`, lock file, tree listing, skill record, or archive ends as `invalid_skill` (or `too_large`) instead of crashing the run.
- A source whose egress is blocked or that never finishes costs each run up to one deadline per step, because transient failures are retried on every run.
- A permanent failure (for example a skill installed after `not_installed` was remembered, or a key set after `auth_failed`) persists until a new agent is created.

## Historical Regressions

None yet. Add a dated entry and a focused regression test for each fixed defect.

## Test Suite Map

- `tests/test_jev_skill_preload.py` covers settings, exact content, fixed question structure/token floor, independent scoring, failure behavior, response reset, runtime order, caller options, and cleanup.
- `scripts/test-jev-skills-preload.py` runs the complete focused module with PASS/FAIL reporting.
- `tests/features/jev_skills_preload/conftest.py` holds the pack's offline fixtures: a URL-routed fake of `HttpTransport._send_once`, a Jev stand-in that answers by skill name, a main-model stand-in, `SKILL.md` writers, and a file/environment recorder.
- `test_skill_sources_entries.py` covers entry construction, validation, path pinning, and settings normalization; `test_skill_sources_contract.py` covers exports, enum values, and the `JevSkillResult` and `SkillResolution` records.
- `test_skill_sources_markdown.py` covers the shared `SKILL.md` parser; `test_skill_sources_local.py`, `test_skill_sources_skills_sh.py`, `test_skill_sources_github.py`, and `test_skill_sources_vendor.py` cover each source's loading, labels, status map, caps, and malformed inputs (including a seeded archive-corruption sweep).
- `test_skill_sources_fetch.py` covers the shared request step, retries, and the per-step deadline; `test_skill_sources_memory.py` covers the loader's memory, grouping, concurrency, and crash and cancellation handling.
- `test_skill_sources_security.py` covers secrets, the Vidbyte-key guard, redirects, processes, and disk writes; `test_skill_sources_jev_wiring.py` covers exact appending and the preload's reasons; `test_skill_sources_acceptance.py` runs the developer snippet and checks lazy construction and gate bypass.
- Run the pack with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload tests/test_jev_skill_preload.py`.
- `python scripts/test-jev-agent-scaffold.py`, `python scripts/test-jev-multipart-done-criteria.py`, `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py` cover existing Jev contracts, source rules, packaging, and the full suite.

## Omitted Testing Strategies

- Live TypeSafe/provider tests are omitted because they require credentials and make classification nondeterministic; scripted decision and text runners cover the boundary.
- Browser, UI, accessibility, persistence, and migration tests are omitted because this is an in-process request-time context transform with no UI or durable state.
- Load tests are omitted because one JevAgent instance has no concurrent-run safety contract; the loader's own concurrency (groups resolved at once, overlapping first runs) is covered with event-ordered fakes instead of timing.
- Live GitHub, Anthropic, OpenAI, and skills.sh tests are omitted: they need credentials and network access, and the vendor content routes are pending real-key QA (spec A-1, A-4). Every request is answered at the transport seam.
- WellKnownSkill, VidbyteSkill, PackageSkill, GitLab sources, refresh APIs, and TTLs are not built (spec section 3), so they have no tests.
