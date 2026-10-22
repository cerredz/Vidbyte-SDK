# S4 review: conventions

LENS: conventions

VERDICT: SOUND. Under the conventions lens there is no Blocker and no Major. Every lint rule, the import order, the public contract, layering, placement, comment width and the commit attribution hold at head 8e773244. The five Minors are all text fixes, and S5 can batch them.

Range reviewed: `git diff 98a5d37b...8e773244` (64 files, +7744/-36). Pristine base: a temporary worktree at 98a5d37b (`C:/Users/422mi/vidbyte-repos/worktrees/r2e-s4-conventions-base`), which was removed after the review.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The ratchet holds rule by rule, not only by totals (NFR-3).**
  - `lint/run.py` prints SDK-LINT PASS at head and at base. The two summary tables differ in one row only, A002 (608 to 602; see R-V2).
  - ruff I001 gives the same per-file list at head and base: 217 files, 223 findings. The new names in the two blocks that were already flagged (`vidbyte/agents/base.py` enums import, `vidbyte/lib/registries/__init__.py`) are wrapped in place, never moved.
  - S062 is 889 = 889 at head and base, identical per file.
  - On all 25 touched files, the C901/PLR0912/PLR0915 findings are the same three at head and base.
  - Semgrep (typed-mapping policy) reports 0 findings on 1034 files.
  - `lint/baseline.json` is unchanged.
- **Placement and layering follow AGENTS.md Placement Rules and §3, and field guide declarative-config-resolution.md:38-43.**
  - The enum is in `lib/enums`, the tables are in `lib/configs` (they import only enums and typing), the resolver is in `lib/registries`, and the construction guard is in `vidbyte/agents/reasoning_effort.py`.
  - No new import cycle appears.
  - No file newly passes 1000 lines (`base.py` goes from 1847 to 1858).
  - All three new modules carry the A001 FILE…TESTS header in the `spend_cap.py` shape. A001 stays at 642 = 642.
- **The comments follow field guide comment-format.md.**
  - No added comment line is longer than 72 columns.
  - Each of the four builders has its `@intent reasoning-effort-joins-before-extra-body` block directly above the `attach` line: anthropic.py:63-68, compatible.py:66-70, gemini.py:69-74 and openai.py:261-265.
  - The new helpers narrate their steps in plain English (AGENTS.md §2).
  - The style commit 182088a3 changes comment lines only: 0 non-comment lines change.
- **Where the spec gives exact text, the public surface and the docs match it byte for byte.**
  - `scripts/generate-sdk-public-api.py --check` reports the contract current at 736 exports.
  - The root header bullet equals spec row 27(a).
  - `docs/design/release-0-4-0.md:17` and `:19` carry the row 34 sentences.
  - The README sections are within the A009 limit (A009 is 0) and within the row targets.
  - The S2 test pack follows the `loop_spend_cap` layout: FEATURE.md, a README index of every file, and unique basenames.

## FINDINGS (ranked)

### R-V1 [Minor] [headers] `vidbyte/agents/fallback.py:10-11`: three module headers still describe the data flow from before the effort existed

- **Evidence:**
  - `git diff 98a5d37b...8e773244 -- vidbyte/agents/fallback.py vidbyte/lib/dataclasses/agents.py vidbyte/lib/dataclasses/model_configs.py | grep '^@@'` shows no hunk above line 30 in any of the three files. Their headers still read as follows:
    - `fallback.py:10-11`: "AgentFallback: Immutable chain plus advance/transform policy helpers; every backup runner gets the agent's matched ProviderKeys and text-model mode." `build_runner` now also passes `reasoning_effort` (spec row 13(c)).
    - `vidbyte/lib/dataclasses/agents.py:9`: "AgentRunnerConfig: Primitive backend configuration, with the matched keys and the text-model mode." The record now also holds `reasoning_effort`.
    - `vidbyte/lib/dataclasses/model_configs.py:6`: "Stores model configurations and delegates API key and endpoint validation and resolution to ProviderModelRegistry."
    - `model_configs.py:8`: "TextModelConfig: dataclass for text/chat completions; matches its api_keys list to its provider at construction." Construction now also refuses an effort it cannot send (`_validate_reasoning_effort`, :220-256, through `ReasoningEffortRegistry`).
  - All four of these header lines were written by 72a4ade1 (#1027) when it threaded `model_mode` through the same files. `git log -S"matches its api_keys list to its provider at construction"` returns 72a4ade1, and `git show 72a4ade1` shows both the fallback.py:10-11 and the agents.py:9 header edits.
  - Spec row 14 (spec.md:1029) asked for the same kind of header edit in `vidbyte/agents/settings/fallback.py`, and S3 made it there (:15). Rows 4, 10 and 13 did not ask for one.
- **Failure:**
  - **Rule:** the agentic-engineering file-header principle (`~/.claude/skills/agentic-engineering/references/file_headers.md:2`) says a header must be "complete enough to serve as a miniature architecture document."
  - **Effect:** an agent that reads fallback.py's Architecture line learns that each backup runner gets keys and mode. It does not learn about the effort, which is the field this PR adds to every hop (FR-11).
  - **What a human reviewer would write:** "#1027 updated these same header lines when it threaded model_mode. Do the same for reasoning_effort."
- **Smallest fix:** edit three docstrings and nothing else (no lint or test change):
  - fallback.py:11: "... matched ProviderKeys, text-model mode and reasoning effort."
  - agents.py:9: "... with the matched keys, the text-model mode and the reasoning effort."
  - model_configs.py:8: append "and refuses a reasoning effort the call cannot send".
  - model_configs.py:6: name ReasoningEffortRegistry beside ProviderModelRegistry.
- **Spec IDs:** rows 4, 10 and 13 (a spec gap; row 14 is the in-spec model), FR-2, FR-6, FR-11.

### R-V2 [Minor] [lint/ratchet] `vidbyte/providers/anthropic.py:63`: the A002 drop from 608 to 602 is a side effect of the lint window, not new intent coverage

- **Evidence:**
  - Running `a002_diff.py` on `lint/run.py --rule A002 --all --format json` at base and at head prints "base 608 head 602". The six cleared findings are:
    - `anthropic._config`
    - `compatible._config`
    - `compatible._build_text_config`
    - `gemini._build_text_config`
    - `openai._build_text_config`
    - `openai._video_config_for`
  - None of these six functions gained a comment.
  - The new `@intent` blocks sit inside the payload builders. For example, anthropic.py:63 is inside `_create_payload`, which starts at :55.
  - A002 credits an `@intent` to any `def` that starts up to 4 lines below it or up to 20 lines above it (`lint/rules/a002_intent_comments.py:24`, `:79-80`). So the comment at anthropic.py:63 is credited to `_config` at :44, 19 lines above it. The other five are credited the same way.
  - The S3 report claims this drop as its own work: "`@intent` on every function A002 names (A002 608 → 602)" (`reports/S3-implementer.md:87`) and "A002, which improved" (`:162`).
  - The head lint run invites a baseline change: "A002 IMPROVED 703 -> 602. Lower it with: python lint/run.py --rule A002 --update-baseline" (`lint-head.txt:97`).
- **Failure:**
  - **Rule:** field guide class-bound-helpers.md:42 says "a new boundary function needs its own `@intent` block". comment-format.md:7 says the credit depends on the 20-line distance.
  - **Effect:** if S6 or a later PR lowers the A002 baseline to 602, a coincidence of line distance becomes something the gate depends on. Moving or rewording the attach comment in any of the four builders would then raise A002 again, on an unrelated function, in an unrelated PR.
  - **What a human reviewer would write:** "Those six functions still have no @intent. Don't claim the drop, and don't lower the baseline on it."
- **Smallest fix:** no code change.
  - Keep the A002 baseline at 703 in this PR.
  - In the S6 PR body, describe the 602 as a side effect of the 20-line window, not as coverage. Do not carry the S3 report's claim forward.
  - [scope-adding] A separate follow-up can give the six functions their own `@intent` blocks.
- **Spec IDs:** NFR-3 (spec.md:270).

### R-V3 [Minor] [docs] `vidbyte/lib/registries/README.md:89-93`: the README's list of refused cells leaves out xhigh on grok-4.5 and grok-4.3, and grok-4.5 is the SDK's default xAI model

- **Evidence:**
  - README:89-93 says: "A value the vendor remaps to another level (DeepSeek `minimal`, `medium` and `xhigh`; GLM-5.2 `minimal`, `low`, `medium` and `xhigh`), a value the docs contradict (Muse `xhigh`), and a model whose page lists no values are refused, never mapped to the nearest level."
  - The table refuses xhigh on two more models: `"grok-4.5": (_LOW, _MEDIUM, _HIGH)` and `"grok-4.3": (_NONE, _LOW, _MEDIUM, _HIGH)` (`vidbyte/lib/configs/reasoning_effort.py:145-146`).
  - The spec marks both cells "refused (docs conflict: ...)" (§9.2, spec.md:560-561), and D-4 (spec.md:305) names "grok-4.5 `xhigh`".
  - `ModelProvider.XAI: "grok-4.5"` is the default xAI model (`vidbyte/lib/registries/models.py:77`).
  - The README's xAI row (:105) gives only the wire form and the sources.
- **Failure:**
  - **Rule:** AGENTS.md:11 says each folder README "documents that folder in more depth" and is read before any change.
  - **Effect:** the parenthetical lists read as the complete set of exceptions. A reader concludes that every listed xAI model takes xhigh, including the default model, which refuses it.
  - **What a human reviewer would write:** "Add grok-4.5 and grok-4.3 xhigh to the docs-conflict list. grok-4.5 is our default xAI model."
- **Smallest fix:** change README:91 to "a value the docs contradict (Muse `xhigh`; grok-4.5 and grok-4.3 `xhigh`)". This adds about 35 characters, so the section stays under its 3,500-character target (it is 2,923 now).
- **Spec IDs:** row 29 (spec.md:1044), FR-12, D-4, §9.2.

### R-V4 [Minor] [error text] `vidbyte/lib/runners/utility.py:139`: the Runner refusal for a non-text model reads "a image runner", and the spec mandates that template

- **Evidence:**
  - utility.py:139 builds the message `f"Runner sets reasoning_effort, but model '{self.model_name}' resolves to a {runner_type} runner, which has no reasoning effort."`.
  - The runner types are "image", "video", "audio", "embedding" and "decision" (`vidbyte/lib/constants/runners.py:40-45`). With "image", "audio" and "embedding", the article "a" is wrong.
  - The test pins the wrong article: "resolves to a image runner" (`tests/features/agent_reasoning_effort/test_agent_reasoning_effort_refusals.py:614`).
  - The template comes from the spec's §8.5 table (spec.md:408), and test-plan.md:139 repeats it.
- **Failure:**
  - **Why the spec is wrong:** the template puts a fixed article in front of a variable noun. For three of the five non-text runner types the sentence is ungrammatical, and the pin means nobody can correct it without editing a test.
  - **Rule:** the agentic-engineering server-side error-message principle (`references/error_messages.md`) asks for a message that reads as a clear diagnosis.
  - **What a human reviewer would write:** "'a image runner'. Reword it so the article does not depend on the type."
- **Smallest fix:** use "... resolves to the '{runner_type}' runner type, which has no reasoning effort." in four places: spec.md:408, test-plan.md:139, utility.py:139 and the test pin at :614. The details dict stays the same.
- **Spec IDs:** §8.5 (spec.md:408), FR-5, AC-16.

### R-V5 [Minor] [commit hygiene] `8dd96a39`: six phase commits, from P3 to P6, leave an existing test failing, against §12.6

- **Evidence:**
  - In the base worktree, I checked out each commit with `git checkout --detach -q <sha>` and ran `py -3.11 -m pytest -q tests/test_agent_modality_routing.py`:
    - 335150be (P2): "19 passed".
    - 8dd96a39 (P3), c15aef71 (P4), 654deee6 and 41a464ca (P5), e2de2026 and 745f861d (P6): "1 failed, 18 passed". The failing test is `FAILED tests/test_agent_modality_routing.py::AgentModalityRoutingTests::test_model_identity_routes_to_image_runner`.
    - e4e7bee4, "fix(agents): pass the reasoning effort to the primary runner only when it is set": "19 passed in 1.35s".
  - S3 records the cause as its deviation 1 (`reports/S3-implementer.md:95`, `:338`), but committed the fix only after P6.
- **Failure:**
  - **Rule:** spec.md:1114 says "Each phase leaves every existing test passing, except the three layout pins". This test is not one of the three pins.
  - **Effect:** main squash-merges (98a5d37b and its parents each have one parent and a "(#NNNN)" subject), so main never carries these commits. The cost falls only on bisecting the PR branch and on per-phase claims.
  - **What a human reviewer would write:** "The fix belongs in the P3 commit."
- **Smallest fix:** nothing is needed for the merge, and history should not be rewritten at this stage. The S6 PR body should note that P3 to P6 fail `test_model_identity_routes_to_image_runner` until e4e7bee4.
- **Spec IDs:** §12.6 (spec.md:1114), row 12(d), FR-6.

## VERIFIED CLAIMS

1. **The lint gate passes at head and at base, and only A002 differs.** `lint/run.py` prints "SDK-LINT: PASS" with exit 0 on both sides. `diff` of summary lines 1-95 shows only line 4 differs (A002 602 against 608). A001 642, A007 255, C008 45, S008 19, S009 346, S020 1, S051 259 and S060 32 are equal; A009 and C016 are 0.
2. **I001 is unchanged across the whole tree.** ruff I001 prints "Found 223 errors." at head and at base, and the per-file lists (217 files each) are identical. `i001_moves.py` shows that the new names change only by wrapping.
3. **S062 is unchanged per file.** The S062 JSON counts are base 889 and head 889, identical per file.
4. **The complexity findings on touched files are unchanged.** On the 25 touched files there are three findings at base and three at head:
   - `base.py __init__` C901 19 (same at both).
   - `base.py __init__` PLR0912 19 (same at both).
   - `base.py __init__` PLR0915: 92 statements at base, 93 at head. It is the same baselined finding, and the extra statement is the spec row 12 guard call.
5. **Semgrep is clean.** Semgrep 1.170.1 with `.semgrep/typed-mapping-boundary-policy.yml` reports "Ran 1 rule on 1034 files: 0 findings."
6. **The public contract is current.** The generator's `--check` prints "contracts/sdk-public-api.json is current at 654deee6… (vidbyte-sdk 0.4.0, 736 exports)."
7. **The tests pass.** I ran the pack, the two pins S2 modified (`test_managed_text_selection.py`, `test_provider_keys_contract.py`), `jev_cli_root_exports` and `test_agent_modality_routing.py`: "724 passed in 5.48s".
8. **The root bullet and the release record match the spec text exactly.** `doc_checks.py` prints:
   - "root bullets: 1 | equals spec row 27(a): True"
   - "line 17 ends with the row 34(a) sentence: True"
   - "line 19 contains the row 34(b) sentence: True"
9. **The diff is clean.** It adds 0 key-shaped literals (GH013), 0 lines to `lint/baseline.json` and 0 comment lines over 72 columns. Only S2's two test files are modified; every other test change is an addition. 182088a3 changes comment lines only.
10. **Private access across modules is accepted.**
    - `Runner._normalize_provider_and_model` (`agents/reasoning_effort.py:45`) has precedents at base.py:193 and :600, fallback.py:140 and fork.py:133.
    - `ProviderModelRegistry._require_provider` is used for the first time from another module, at `registries/reasoning_effort.py:39`, `:58` and `:72`, but that module is in the same package.
    - No lint rule bans private access: ruff.toml enables no SLF rule. Deviation 6 stands.
11. **AGENTS.md §1 (one-level call chains) holds.**
    - The one call to another method of the same class from inside a new helper is `self.normalized_provider()` at model_configs.py:233. It is a leaf accessor that calls nothing further.
    - Spec row 4(d) prescribes it, so that `__post_init__` gains no new branch (S008).
    - The class already uses this shape: `validate` (:120) calls `credentials`, which calls `normalized_provider` (:138).
    - The Jev sibling passes the raw provider instead (`jev/settings.py:257`).
    - This is not a finding.
12. **The commits match the phases.** The commit series follows the §12.6 phases P1 to P6, and every implementation commit carries the attribution lines.
13. **The comment-placement option the spec offers is acceptable.** The fork.py `@intent` block (:64-69) sits 5 lines above `reasoning_effort=` (:75). Spec row 15 (spec.md:1030) allows extending that block, so this is not a finding.

## COMMANDS RUN

In this section, S is the scratch folder `.../scratchpad/r2e-s4/conventions` and B is the base worktree `C:/Users/422mi/vidbyte-repos/worktrees/r2e-s4-conventions-base`. Every Python command uses `py -3.11` with an inline `PYTHONPATH=$(pwd)` (most also set `PYTHONDONTWRITEBYTECODE=1`). No installs, no `scripts/run_ci.py`, no network.

| # | Command | Final lines |
|---|---|---|
| 1 | `git worktree add --detach B 98a5d37b` | Created B at 98a5d37b. It was used for the base runs and the phase-commit checks, and removed at the end. |
| 2 | `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py > S/lint-head.txt` (head), and the same in B to `S/lint-base.txt` | head: "A002 IMPROVED 703 -> 602. Lower it with: …" / "SDK-LINT: PASS" / exit=0<br>base: "A002 IMPROVED 703 -> 608." / "SDK-LINT: PASS" / exit=0 |
| 3 | `py -3.11 lint/run.py --rule A002 --all --format json > S/a002-{head,base}.json`, then `py -3.11 S/a002_diff.py S/a002-base.json S/a002-head.json` | "base 608 head 602", then six "base=1 head=0" lines (listed in R-V2) |
| 4 | `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --output-format concise > S/i001-{head,base}.txt`; per-file diff; `S/i001_moves.py` | "Found 223 errors." at both; 217 = 217 files, identical; new names wrapped only (base.py enums line, registries/__init__.py) |
| 5 | `py -3.11 lint/run.py --rule S062 --all --format json` at head and in B, then a per-path Counter compare | "S062 base 889 head 889 per-file identical: True" |
| 6 | `py -3.11 S/s008_compare.py B .` (ruff C901, PLR0912, PLR0915 over vidbyte) | "touched-file findings base: 3 head: 3"; SAME C901 19, SAME PLR0912 19; PLR0915 92 to 93 (one finding) |
| 7 | `semgrep scan --metrics=off --disable-version-check --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (s3-semgrep-venv on PATH through cygpath) | "Ran 1 rule on 1034 files: 0 findings." |
| 8 | `py -3.11 scripts/generate-sdk-public-api.py --check` | "contracts/sdk-public-api.json is current at 654deee6d2893e83f67164bd331e0f92c941cd85 (vidbyte-sdk 0.4.0, 736 exports)." |
| 9 | `py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/jev_cli_root_exports tests/test_agent_modality_routing.py tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py` | "724 passed in 5.48s" |
| 10 | In B, for each of 335150be, 8dd96a39, c15aef71, 654deee6, 41a464ca, e2de2026, 745f861d and e4e7bee4: `git checkout --detach -q <sha> && py -3.11 -m pytest -q -p no:cacheprovider tests/test_agent_modality_routing.py`; then `git checkout --detach -q 98a5d37b` | 335150be: "19 passed"; 8dd96a39 to 745f861d: "1 failed, 18 passed" (the failing test is named in R-V5); e4e7bee4: "19 passed in 1.35s"; B was restored to 98a5d37b, clean |
| 11 | `py -3.11 S/doc_checks.py .` | "root bullets: 1 \| equals spec row 27(a): True" / "line 17 ends with the row 34(a) sentence: True" / "line 19 contains the row 34(b) sentence: True" |
| 12 | `git diff 98a5d37b...8e773244 -- 'vidbyte/*.py' \| grep -E '^\+\s*#' \| awk 'length>72' \| wc -l`; the key-literal grep; `git diff … -- lint/baseline.json \| wc -l` | 0; 0; 0 |
| 13 | `git diff 98a5d37b...8e773244 -- vidbyte/agents/fallback.py vidbyte/lib/dataclasses/agents.py vidbyte/lib/dataclasses/model_configs.py \| grep '^@@'`; `git log -S"matches its api_keys list to its provider at construction" -- vidbyte/lib/dataclasses/model_configs.py`; `git show 72a4ade1 -- vidbyte/agents/fallback.py vidbyte/lib/dataclasses/agents.py` | first hunk at line 30 in all three files; "72a4ade1 feat(lib,agents): agents take vidbyte_api_key and a list of api_keys …"; that commit's header edits at fallback.py:10-11 and agents.py:9 |
| 14 | `git log -4 --format="%h %p %s" 98a5d37b` | one parent per commit, each subject ending "(#1192)", "(#1190)", "(#1147)" and "(#1159)" (squash merges) |
| 15 | `wc -l` on base.py at head and at base; on the three new modules | 1858 and 1847; 170, 115 and 61 |
