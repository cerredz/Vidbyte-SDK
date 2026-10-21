# S6 PR author report: agent-reasoning-effort (R2, PR #1193)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-reasoning-effort`, branch `feat/agent-reasoning-effort`. Start head `34954551` (1 docs commit ahead of `origin/feat/agent-reasoning-effort` at `f42bb505`). Base `origin/main` = `98a5d37b`, an ancestor. No source, test or contract file was changed by S6: `git diff --stat f42bb505 HEAD -- . ':!docs'` is empty.

## 1. What the code does (written from the diff, before the spec was opened)

- **Value.** `ReasoningEffort` (`vidbyte/lib/enums/text_model.py`) is a `StrEnum`: none, minimal, low, medium, high, xhigh.
- **Table.** `vidbyte/lib/configs/reasoning_effort.py` holds `REASONING_EFFORT_FORMS` (one request fragment per provider and value) and `REASONING_EFFORT_SUPPORT` (per provider, exact lower-case ids mapped to the documented values in enum order), dated `REASONING_EFFORT_AS_OF = "2026-10-20"`. Wire forms: OpenAI `reasoning.effort`; Anthropic `output_config.effort`, `none` as `thinking: {type: disabled}`; Gemini `generationConfig.thinkingConfig.thinkingLevel` in upper case, `none` as `thinkingBudget: 0` on 2.5 Flash and Flash-Lite only; DeepSeek, xAI and Meta a top-level `reasoning_effort`; GLM `thinking: enabled` plus `reasoning_effort`, `none` as `thinking: disabled`. A value a vendor remaps has no cell.
- **Registry.** `ReasoningEffortRegistry` (`vidbyte/lib/registries/reasoning_effort.py`): `supported` normalizes the id through `ProviderModelRegistry.normalize_model`, strips and lower-cases it, and looks it up; `refusal` returns the gateway-mode reason first, then the capability text (id has a row) or the no-row text (names the as-of date); `attach` merges a deep copy of the fragment key by key, or raises the capability text.
- **Construction path, `BaseAgent`.** `AgentRunnerConfig.__post_init__` converts the value with `RecordFieldConverter.to_enum`. `AgentFallback.from_spec` → `AgentFallbackSettings.to_fallback` carries it into the chain. `AgentReasoningEffortGuard.refuse_unsupported` (called right after R3's spend-cap refusal) reads each hop through `Runner._normalize_provider_and_model`, refuses a hop without both provider and model (identity text), then gathers each hop's registry reason, de-duplicated in chain order, into one `ConfigurationError`. After `ContextWindow.resolve_algorithm`, `refuse_algorithm_models` refuses `multi_provider_agentic_grader` (any form), `independent_critic` with `reviewer_provider`, and `prosecutor_defender_judge` with a stage that sets provider and model, naming the fixed key, never `algorithm.name`.
- **Construction path, `JevAgentSettings`.** `_validate_reasoning_effort` converts and asks the registry against its own provider, model and mode. `JevAgent` then passes the value to `BaseAgent` (main agent) and to 8 child builders: fresh continuation (`jev/agent.py`), bulk worker, clone, swarm, `JevHandoff`, `JevReviewer`, `JevRunState` (and its Relation subclass), `JevClarificationAgent`. Not the brief writer, specialists or decisions.
- **Run path.** `BaseAgent._runner_for_model` (and `AgentFallback.build_runner` per hop) → `Runner.from_model(reasoning_effort=…)` (passed only when set in `_runner_for_model`) → `Runner.build` → `_config_options_for`: a set keyword overwrites `options["reasoning_effort"]`, an unset one keeps it; any non-None effort on a non-text runner type raises the `Runner` text → `TextModelConfig(...)`, whose `_validate_reasoning_effort` re-runs `to_enum`, the registry refusal, the `thinking_config` both-set refusal and the `extra_body` top-level overlap refusal → `TextModelRunner` → the payload builder (`OpenAIProvider._create_text_payload`; `_create_payload` on Anthropic, Gemini and the compatible builder) calls `ReasoningEffortRegistry.attach` immediately before `_attach_extra_body` → `HttpTransport.request`.
- **Copy paths.** Fork (child re-checked by its own `BaseAgent.__init__`), `ContinualTraceAgent`, `HandoffAgent`, checkpoint (`runtime_config["reasoning_effort"]`, written only when set) and `restore` (reads it back with `.get`).
- **Root.** `ReasoningEffort`, `DecisionModelConfig`, `DecisionModelMode` added to `vidbyte.__all__`; contract regenerated at 736.

## 2. The §4 snippet, run as written

Driver: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r2e-s6/run_section4.py`. It extracts the §4 python block from `spec.md` byte for byte (CRLF folded to LF), deletes every environment variable whose name contains `API_KEY` before `vidbyte` loads (5 were present and removed), sets the three variables the snippet reads to provider-shaped placeholders assembled at run time, replaces `HttpTransport.request` with its own recorder (not the pack's `Wire`), and runs the snippet with `runpy` in a fresh `py -3.11` process with `PYTHONPATH=$(pwd)`.

```text
removed env vars: 5
--- snippet stdout (repr) ---
"Agent fast sets reasoning_effort, but gemini:gemini-3.5-flash has no documented form for reasoning effort 'xhigh' (it supports minimal, low, medium, high).\n"
--- matches spec 'Printed output' exactly: True
--- planner requests: 1; all URLs: ['https://api.openai.com/v1/responses']
planner body keys: ['input', 'instructions', 'model', 'reasoning', 'tools']
planner body reasoning: {"effort": "high"}
--- jev requests: 1; URLs: ['https://api.anthropic.com/v1/messages']
jev body output_config: {"effort": "low"} thinking: null
```

The snippet runs as written; AC-1 holds. No OPEN ITEM. The snippet needs the three key variables to exist (it reads `os.environ[...]`), which the spec's AC-1 "Given" already states.

## 3. Deviations found (code against spec §4, §5, §8, §12)

1. **§5 drifted** (fixed in spec text at S6, noted in spec §17 "Recorded at S6"): the r4 diagram had no exit for the identity refusal, the `to_enum` refusal or the `Runner` non-text refusal; it drew `JevAgentSettings` through `AgentRunnerConfig` (the settings check themselves first); it named every builder `_create_payload` (OpenAI's is `_create_text_payload`). §5 now holds the PR's chart, validated by rendering with mermaid 11.4.1 in headless Chromium (`OK nodes=17`; a deliberately broken control diagram failed to parse).
2. Row 12(d): `_runner_for_model` passes the effort only when set (pinned by `tests/test_agent_modality_routing.py:74`). Recorded at S3.
3. Row 29: the sources table labels providers by vendor name because `tests/features/sdk_provider_keys/test_provider_keys_contract.py:341` parses every README line starting `| meta |`. Recorded at S3.
4. Row 33: `skills/usage/create_agent.md` trailing comment and Model clause. Recorded at S3.
5. Row 3 (spec silent): `attach`'s backstop `details`, and `supported` calling the private `ProviderModelRegistry._require_provider`. Recorded at S3.
6. Row 34(c): the PR number was missing from the release record. Closed by S6: `docs/design/release-0-4-0.md:17` now reads "The reasoning effort (#1193) adds", `:19` "and 3 from #1193." (CRLF working copy kept; no test reads the file: `git grep -n "release-0-4-0" -- tests` is empty).

§4, §8 and §12 otherwise match the code: names, paths and the refusal order are as §8.5 states; the §4 snippet runs exactly.

## 4. Docs records changed by S6 (commit `50ad0f88`)

- `spec.md`: frontmatter `status: pr-open`, `updated: 2026-10-21`, `pr:` unchanged (already the PR URL); §5 redrawn and steps 1 and 3 updated; §6.2 Proof cells of AC-21 to AC-29 filled (re-review R-C2), every node id checked with `git grep` and `pytest --collect-only`; §17 row `r4 | 2026-10-21 | S6 PR | finalized for review: …` and a "Recorded at S6" subsection.
- `review.md`: R-7 → "done in spec r4 @346f8c3e (INV-11, AC-18, §12.4, §17)" (re-review R-C1); R-8 and R-10 → "done in the PR body".
- `docs/design/release-0-4-0.md`: the two row 34(c) inserts only.
- `pr-body.md`: new. After its push, one sentence was softened ("which no carrier reaches, because construction refuses first" instead of "unreachable"), committed with this report.

Pack rerun after the edits: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort` → `700 passed in 3.64s`.

R-10 re-checked independently with `git archive` copies: `tests/test_agent_modality_routing.py` gives `1 failed, 18 passed` at `745f861d` (`FAILED …::AgentModalityRoutingTests::test_model_identity_routes_to_image_runner`) and `19 passed` at `e4e7bee4`.

## 5. PR state after the push of `50ad0f88`

`gh pr edit https://github.com/cerredz/Vidbyte-SDK/pull/1193 --title "$TITLE" --body-file …` → `https://github.com/cerredz/Vidbyte-SDK/pull/1193`

`gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1193 --json title,isDraft,baseRefName,url,headRefOid`:
```json
{"baseRefName":"main","headRefOid":"50ad0f8822f03ed06c200af1e8b4898e8abfa329","isDraft":true,"title":"feat(agents): add a provider-neutral reasoning effort for direct text calls","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1193"}
```

`gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1193` → `no checks reported on the 'feat/agent-reasoning-effort' branch` (exit 1). Expected: `ci.yml` and `static-policy.yml` are dispatch-only here and dispatched runs do not attach to a PR. The push triggered no run (`gh run list --branch feat/agent-reasoning-effort` lists only the two dispatched runs). The last remote runs, on `f42bb505` (every later commit is docs only):
- CI [39550863801](https://github.com/cerredz/Vidbyte-SDK/actions/runs/39550863801): `success` (Source / Python 3.11, Source / Python 3.12, Package).
- Static policy [39550865942](https://github.com/cerredz/Vidbyte-SDK/actions/runs/39550865942): `success`.

The remote PR body equals `tail -n +2 pr-body.md` (diff shows only a trailing newline). Title has no `[WIP]`; the PR is still a draft.

## 6. Candidate field-guide lessons (report only; not written to the field guide)

Each in the field guide's shape. None is distilled from human review yet.

### Thread an agent-wide model setting past the algorithms that build their own runners
- **When:** Adding a model-call setting that rides `AgentRunnerConfig` (like `temperature` or `reasoning_effort`) and promising it reaches "every call".
- **Do:** Treat `multi_provider_agentic_grader`, `independent_critic` with `reviewer_provider`, and `prosecutor_defender_judge` with a stage model as separate call paths: they build runners with `ModalityDetector.create_runner`, which never sees the agent's runner config. Either forward the setting there or refuse it at construction right after `ContextWindow.resolve_algorithm`, keyed by the sub-algorithm field, never `algorithm.name`.
- **Because:** A setting threaded through `_runner_for_model` and `AgentFallback.build_runner` alone is silently dropped on those calls; the preset grader also picks its models at run time, so it cannot be checked per model.
- **Check:** `git grep -n "create_runner\|with_runner(" -- vidbyte/agents vidbyte/context`, then probe each algorithm with a fake `HttpTransport.request` and assert the setting is on every request.
- **Evidence:** PR #1193 review R-1 (Blocker); fixed in `5da7f7fb`, tests `20b49e0c`.

### A new `Runner` keyword must not overwrite the same field in `options`
- **When:** Adding a keyword to `Runner` that maps onto a config field a caller can also pass through `options`.
- **Do:** Copy the keyword into the options only when it is set, as `temperature` does, and make any runner-type refusal read the merged options (`options.get(...)`), not the keyword.
- **Because:** `_config_options_for` filters options by the target config's fields, so an unconditional assignment replaces a caller's value with `None`, and the filter drops the field on image, audio, embedding and video configs without a word.
- **Check:** Build `Runner(options={field: v})` with no keyword and assert the built config holds `v`; repeat on one model of each non-text runner type and assert a refusal.
- **Evidence:** PR #1193 review R-3; fixed in `a324ac08`.

### Pin a "non-text runner" rule on all four non-text types and both channels
- **When:** Writing a test for behavior promised "for a non-text runner type".
- **Do:** Parametrize over `gpt-image-2` (image), `tts-1` (audio), `text-embedding-3-small` (embedding) and `sora-2` (video), and over the keyword and `options` channels; first assert the unset build's runner class so a drifted id cannot pass vacuously.
- **Because:** A refusal narrowed to image runners passed the whole pack (mutant V-N05 survived).
- **Check:** The mutant `runner_type == "image"` fails at least the audio, embedding and video cases.
- **Evidence:** PR #1193 review R-2; closed by `20b49e0c`.

### Update the module headers that list what a record or chain carries
- **When:** Threading a new field through `AgentFallback`, `AgentRunnerConfig`, `TextModelConfig` or another record whose header enumerates the carried fields.
- **Do:** Edit the header's Purpose and Architecture lines in the same change, as #1027 did for `model_mode`.
- **Because:** Those headers are the first thing the next agent reads; a list that omits the new field describes a data flow that no longer exists.
- **Check:** `git grep -n "keys and\|text-model mode" -- vidbyte/agents/fallback.py vidbyte/lib/dataclasses/agents.py vidbyte/lib/dataclasses/model_configs.py` after the change.
- **Evidence:** PR #1193 review R-5; fixed in `3725feb4`.

### Do not read an A002 drop as new intent comments
- **When:** `lint/run.py` shows A002 (intent comments) below base after a change that adds `@intent` blocks.
- **Do:** Diff A002 per finding (`lint/run.py --rule A002 --format json`, keyed by path, symbol and line) and say which functions left the list; do not claim an improvement and do not lower `lint/baseline.json`.
- **Because:** `_has_intent` credits a function when an `@intent` marker appears within 20 lines after its first line (`lint/rules/a002_intent_comments.py:23,77-81`), so a new block below small helpers removes them from the count without documenting them.
- **Check:** Every removed finding is a function within 20 lines above a new marker; nothing was added.
- **Evidence:** PR #1193 review R-8 (608 → 602; baseline 703 unchanged).

### Quote a variable noun in an error text instead of computing its article
- **When:** An error message interpolates an enum value or type name after "a"/"an".
- **Do:** Quote the value as a value (`resolves to runner type 'image'`).
- **Because:** `a {runner_type}` read "a image", "a audio", "a embedding", and fixing it later needs a spec edit and a test-pin edit together.
- **Check:** `git grep -n "a {" -- vidbyte` in new f-strings.
- **Evidence:** PR #1193 review R-9; fixed in `afb9e134`.

### Keep every phase commit green when `Runner.from_model` keywords change
- **When:** Adding a keyword that `BaseAgent._runner_for_model` passes to `Runner.from_model`.
- **Do:** Pass it only when it is set, as the timeout already is, from the first commit that adds it.
- **Because:** `tests/test_agent_modality_routing.py:74` pins the exact `from_model` keywords of an agent without the setting, so an unconditional pass reds every later phase commit until fixed (bisecting the branch hits it).
- **Check:** Run `tests/test_agent_modality_routing.py` at each phase commit (`git archive <sha>` into a scratch folder).
- **Evidence:** PR #1193 review R-10 (`8dd96a39` … `745f861d` red, `e4e7bee4` green).

### Label README tables by vendor name, not by enum value
- **When:** Adding a provider table to any folder README.
- **Do:** Start rows with the vendor's display name (`| Meta |`), not the lower-case enum value.
- **Because:** `tests/features/sdk_provider_keys/test_provider_keys_contract.py:341` reads every README line that starts `| meta |` as its own key-format table.
- **Check:** `git grep -n "^| meta |" -- "*.md"` returns only the key-format table.
- **Evidence:** PR #1193 spec §17 implementation deviation 2 (S3).

## 7. Things that looked wrong while reading (none is a code bug)

- **Survived mutant (test gap, known).** Re-review mutant MX2 lets `ReasoningEffort.NONE` through `refuse_algorithm_models` and survives: `vidbyte/agents/reasoning_effort.py:69-71` is correct (`if effort is None: return`), but no test runs AC-21 to AC-23 with `none`. Listed as a follow-up in the PR body.
- **Spec TL;DR is stale against r4.** `docs/spec/agent-reasoning-effort/spec.md:19` still says construction refuses "in four cases" (gateway, `thinking_config`, no documented form, remap). r4 and the code also refuse an overlapping `extra_body`, a non-text runner, a missing identity and an own-runner algorithm. Framing text only; §6, §8.5 and the PR body are correct. Left unedited (outside S6's allowed spec edits).
- **Release record sentence.** `docs/design/release-0-4-0.md:17` (row 34(a)) does not mention the r4 algorithm refusal. Left as written, per the briefing; listed as a follow-up.
- **Briefing wording adjusted to the code.** The briefing phrased D-6 as "the per-hop effort is lost on export_state/restore, while the primary's effort is kept". The code has no per-hop effort: one agent-wide value is stored in the checkpoint and every rebuilt hop sends it (`base.py` export/restore; `test_a_restored_chain_sends_the_kept_effort_in_each_hops_own_form`). The PR body states it that way.
- **Commit-SHA literal.** The contract `--check` line quotes a 40-hex commit SHA; the body shortens it to `654deee6…` so nothing hex-shaped reaches the public PR text.

No dead code found. No vacuous test found beyond the MX2 gap.
