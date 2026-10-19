# S5 hotfix split: meta-muse-managed-text

Hotfix worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-llm-key-shape`, branch `fix/meta-llm-key-shape` (pushed, no PR). Run B worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`, branch `feat/meta-muse-managed-text`, draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1180.

## Outcome

The Meta key-shape fix now exists as two self-contained commits that apply to main alone, and Run B carries those exact commits through a merge that changes nothing in Run B's tree.

- **T** `22fe9fc539434153b93b4e159bc4cdbc3a9fb87a`: `test(provider-keys): prove Meta's documented LLM_ key shape [R-1]`.
- **P'** `c6d88e8873239e073e79aa54e48bb72aaf073034`: `git cherry-pick -x` of P `9309eed0`. It applied with no conflict, and its diff is byte-identical to P's (`diff <(git diff HEAD^ HEAD -- vidbyte) <(git diff 9309eed0^ 9309eed0 -- vidbyte)` printed nothing).
- **Merge** `db5ad22be77326ee60ee97550230b1bb9a7267fe` on `feat/meta-muse-managed-text`, with parents `91c77abf` (PRE) and `c6d88e88`. The tree hash is `f98262f8` both before and after the merge.

On unpatched main, a key in the shape Meta documents is not just refused; it is sent to the wrong vendor. I reproduced this before writing any test. In `AUTO`, an agent with `api_keys=[K_ANTHROPIC, <LLM_ key>]`, an `anthropic` primary that gets a relayed 401, and a `kimi` fallback sent the Meta key in the kimi call's `X-Vidbyte-Provider-Key`. It did so whether or not a `meta/muse-spark-1.1` fallback was also configured. The `LLM|` form was not relayed. The probe was `<scratchpad>/s5h_probe_meta_fallback.py`. The AC-17 (i) test in T now pins this case.

## One deviation from the procedure: the hotfix forks from `845a4d9b`, not from the origin/main tip

origin/main `6f5a7310` is one commit ahead of Run B's base `845a4d9b`. That commit is #1055 (CodexHost), which changes 110 files and adds 28,811 lines, and its parent is `845a4d9b`. A branch forked from `6f5a7310` cannot be merged into Run B without also bringing #1055 into Run B. Run B's tree would then change in 110 files, and Run B's converged gates (area 192, lint, source stage, package CI) would need re-running against code this stage never reviewed. That contradicts the claim the briefing most wants checked ("The Run B tree is unchanged by the merge") and the scope rule ("only the key-shape fix").

So I followed the release-branch rule the brief itself names: fork the fix at the oldest commit it must merge into. That is `845a4d9b`, main's own commit just before #1055 and the merge-base of origin/main and Run B. The worktree was created from origin/main as instructed, and then moved with `git reset --hard 845a4d9b` before any commit. The result:

- `git log --oneline origin/main..HEAD` on the hotfix branch shows exactly 2 commits, `c6d88e88` and `22fe9fc5`.
- The coordinator's own check (branch from the origin/main tip, cherry-pick T then P') passes. Because of the deviation, that check ran on a scratch branch rather than on the hotfix branch itself; see below. Its tree delta is byte-identical to the hotfix branch's.
- The merge into Run B changes nothing (tree hash `f98262f8` before and after).

**Flip condition.** If the coordinator wants the hotfix branch itself to sit on the tip, run `git merge origin/main` on `fix/meta-llm-key-shape` only, never on Run B. It merges cleanly, because #1055 touches neither path. A hotfix PR's CI already tests the tip combination through the PR merge ref, and I ran that combination locally (below).

## Files each commit touches

```
22fe9fc5 (T): 8 files, +311/-29
 tests/features/sdk_provider_keys/FEATURE.md                  |  18 ++-
 tests/features/sdk_provider_keys/README.md                   |   1 +
 tests/features/sdk_provider_keys/provider_keys_fixtures.py   |  10 +-
 tests/features/sdk_provider_keys/test_provider_keys_agents.py   |  33 ++++-
 tests/features/sdk_provider_keys/test_provider_keys_contract.py |  82 ++++++++++-
 tests/features/sdk_provider_keys/test_provider_keys_matching.py | 158 ++++++++++++++++++++-
 tests/features/sdk_provider_keys/test_provider_keys_modes.py    |  29 ++--
 tests/features/sdk_provider_keys/test_provider_keys_property.py |   9 +-
c6d88e88 (P'): 2 files, +8/-4
 vidbyte/lib/registries/README.md        |  2 +-
 vidbyte/lib/registries/provider_keys.py | 10 +++++++---
```

`git diff --name-only 845a4d9b c6d88e88 | grep -E 'constants/jev.py|sdk_managed_text|^README.md$'` printed nothing. There is no gateway file, no managed-text file, and no root README.

## How T was ported

For each file I took Run B's version (`263fa4e9`) and removed only what needs gateway-served `meta`. Test names, subTest labels, table rows and assertions are byte-identical to Run B's.

- `test_provider_keys_contract.py` and `test_provider_keys_property.py` were touched only by the r4 commits, so they are Run B's files verbatim (`git checkout 263fa4e9 -- <file>`).
- In `test_provider_keys_matching.py`, the RELATED DOCS line returns to main's text, the S2 test `test_m18_offers_vidbytes_own_meta_account_…` is dropped, and the malformed-key test's `meta` root is dropped, with a 3-line comment saying why.
- `provider_keys_fixtures.py`, `test_provider_keys_modes.py` and `test_provider_keys_agents.py` are main's files with Run B's r4 hunks applied. The modes DIRECT test, including its comment, is identical to Run B's. The agents test sits in a new `MetaAgentTests` class, so its node id matches Run B's and the spec's AC-17 (i) proof id.

The only change to an existing assertion is the granted one: `test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes` pinned the last row's prefixes as `{"LLM|"}` before and as `{"LLM|", "LLM_"}` after. Every comment line T adds or edits is at most 72 columns (`git diff -U0 -- '*.py' | grep -E '^\+\s*#' | awk 'length($0) > 73'` printed nothing). No added line holds `LLM_` or `LLM|` followed by a digit (`grep -E 'LLM[_|][0-9]'` over the added lines printed nothing); every fake key is built by concatenation.

### Ported tests (12: 9 new, 3 extended), plus fixture and pool data

| Test | Kind | Spec |
|---|---|---|
| `matching::TableFAndATests::test_each_table_f_sample_proves_its_provider_and_every_unsourced_shape_is_unproven` | extended: +3 proven `LLM_` rows, +10 unproven rows | FR-9, INV-16, D-9, AC-16 |
| `matching::TableFAndATests::test_every_meta_shaped_key_is_reserved_to_meta_and_no_provider_takes_it_unproven` | new | INV-16, INV-17, EC-8, AC-17 (iii) |
| `matching::UniqueAssignmentTests::test_a_meta_key_in_either_shape_goes_to_meta_beside_every_provider_that_takes_unproven_keys` | new | INV-16, EC-17 |
| `matching::UniqueAssignmentTests::test_two_meta_keys_in_different_shapes_are_refused_and_the_same_documented_key_twice_is_one_key` | new | INV-16, M-7 |
| `matching::UniqueAssignmentTests::test_a_malformed_llm_key_is_refused_at_construction_on_every_root_whatever_its_providers` | new (6 of Run B's 7 roots) | AC-17 (iii), EC-8 |
| `matching::ConfiguredPrimaryTests::test_a_lone_meta_key_for_a_provider_that_takes_unproven_keys_is_refused_with_m18` | new | AC-17 (ii), EC-17 |
| `agents::MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own` | new; all 4 subtests run on main | AC-17 (i), EC-17, INV-4 |
| `modes::UnsendableKeyTests::test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct` | extended: subTest per shape, exact URL | AC-16 (iii), INV-11 |
| `contract::NamesAndConstantsTests::test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes` | extended: the granted prefix pin | §8.5 grant |
| `contract::NamesAndConstantsTests::test_the_meta_row_is_the_section_8_5_row_and_every_other_row_keeps_its_rule` | new | §8.5, D-8, D-9, INV-17 |
| `contract::KeyFormatSourceTests::test_the_comment_above_the_meta_row_names_the_llm_shape_and_cites_metas_page` | new | AC-18 |
| `contract::KeyFormatSourceTests::test_the_registries_readme_meta_row_quotes_metas_llm_sentence_and_keeps_the_older_source` | new | AC-18 |

The data changes are `K_META_DOC` (with its `__all__` entry and `LLM_` on the KNOWN EDGE CASES line), and `POOL` and `PROVEN` in the property test gaining `K_META_DOC` (FR-9). FEATURE.md gains the 6 r4 failure-mode lines and the Test Suite Map sentences, in Run B's wording wherever that wording is true on main. The pack README gains one log line.

### Run B-only r4 key-shape coverage, with the reason

| Coverage | Reason it cannot run on main |
|---|---|
| `acceptance::SnippetAcceptanceTests::test_meta_muse_snippet_…`, subTest `shape="LLM_"` (AC-1, AC-16 (i)) | The whole test is a `meta` agent in `AUTO` plus a `VIDBYTE_MANAGED` Muse call. On main, `TextModelConfig._require_gateway_shape` raises `UnsupportedProviderError` (M-12). |
| `acceptance::TextCallAcceptanceTests::test_vidbyte_managed_meta_never_reads_meta_api_key_or_sends_a_meta_key`, the `K_META_DOC` row (AC-4) | `VIDBYTE_MANAGED` `meta`: M-12 on main. |
| `wire_contract::MetaRelayTests::test_a_meta_call_relays_…`, rows "LLM_ key in a mixed list beats META_API_KEY" and "LLM_ META_API_KEY with no list" (AC-16 (i), (ii)) | An `AUTO` relay for `meta`: M-12 on main. |
| The `RELAY_KEYS[META]` comment edit (r4) | It edits a row the gateway work added. |
| Matching, malformed-key test, root `"meta"` (`TextModelConfig(provider="meta", …)` in `AUTO`) | On main the gateway-shape check (`model_configs.py:96`) runs before matching (`:100`), so this root raises `UnsupportedProviderError`, which is not a `ConfigurationError` (probe: MRO `UnsupportedProviderError → VidbyteSdkError`). It is only a control row: meta takes no unproven key, so it passes with or without the fix. |
| r4 and tidy comment rewraps inside S2-only tests (agents, failures, security) | They are comments in gateway-era tests. |

## Gates on the hotfix branch (`845a4d9b` + T + P')

**Red: T over unpatched production (`22fe9fc5`):**
```
$ PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_provider_keys -q -p no:cacheprovider
FAILED …test_provider_keys_agents.py::MetaAgentTests::test_a_meta_key_in_either_shape_never_rides_on_a_kimi_fallback_that_holds_no_key_of_its_own
FAILED …test_provider_keys_contract.py::NamesAndConstantsTests::test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes
FAILED …test_provider_keys_contract.py::NamesAndConstantsTests::test_the_meta_row_is_the_section_8_5_row_and_every_other_row_keeps_its_rule
FAILED …test_provider_keys_contract.py::KeyFormatSourceTests::test_the_comment_above_the_meta_row_names_the_llm_shape_and_cites_metas_page
FAILED …test_provider_keys_contract.py::KeyFormatSourceTests::test_the_registries_readme_meta_row_quotes_metas_llm_sentence_and_keeps_the_older_source
FAILED …test_provider_keys_matching.py::TableFAndATests::test_each_table_f_sample_proves_its_provider_and_every_unsourced_shape_is_unproven
FAILED …test_provider_keys_matching.py::TableFAndATests::test_every_meta_shaped_key_is_reserved_to_meta_and_no_provider_takes_it_unproven
FAILED …test_provider_keys_matching.py::UniqueAssignmentTests::test_a_malformed_llm_key_is_refused_at_construction_on_every_root_whatever_its_providers
FAILED …test_provider_keys_matching.py::UniqueAssignmentTests::test_a_meta_key_in_either_shape_goes_to_meta_beside_every_provider_that_takes_unproven_keys
FAILED …test_provider_keys_matching.py::UniqueAssignmentTests::test_two_meta_keys_in_different_shapes_are_refused_and_the_same_documented_key_twice_is_one_key
FAILED …test_provider_keys_matching.py::ConfiguredPrimaryTests::test_a_lone_meta_key_for_a_provider_that_takes_unproven_keys_is_refused_with_m18
FAILED …test_provider_keys_modes.py::UnsendableKeyTests::test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct
12 failed, 126 passed in 2.27s
```
The 126 passing tests are every pre-existing test of main's pack except the three that T extends.

A subtest audit under `unittest` (`<scratchpad>/s5h_subtest_audit.py`) found 136 failing rows in those 12 tests and **0 rows for an `LLM|` shape or sample**. In the three extended pre-existing tests, only the new rows fail: the 3 proven `LLM_` samples, `shape="LLM_"` in DIRECT, and the granted pin. The rows fail for these reasons:

| Rows | Failure | What it means |
|---|---|---|
| 64 | `accepts_unproven` returned True | `LLM_` keys are not reserved to meta |
| 42 | "ConfigurationError not raised" | 36 malformed-key roots, 5 lone-key M-18 cases, and 1 M-7 case with a kimi backup |
| 10 | `key_view` names kimi, deepseek, mistral, glm or minimax where it must name meta | The key binds to that provider by elimination |
| 4 | M-6 raised where the call must succeed | The meta-primary split twice, the same documented key twice, and DIRECT with an `LLM_` key |
| 3 | `provider_of` returned None | The 3 proven `LLM_` samples |
| 2 | The kimi relay header holds the Meta key | Both `LLM_` cases of the agent test |
| 1 | M-6 where M-7 is due | The two-shapes case |
| 10 | Contract failures | The §8.5 row, the prefix pin, and the r4 source text (8 rows) |

**Green, with P' (`c6d88e88`):**
```
$ PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_provider_keys -q -p no:cacheprovider
138 passed in 1.94s
```
Audit: `tests run: 138; subtests run: 654; failing rows: 0`.

**Lint:** `py -3.11 lint/run.py` exited 0, ended `SDK-LINT: PASS`, and had 0 REGRESSED lines. The IMPROVED lines, such as `A002 703 -> 562`, are main's own baseline slack and were not touched.

**Source stage:** `PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 scripts/run_ci.py --stage source`. This shell exports `DEEPSEEK_API_KEY`; the pack's FEATURE.md requires it unset, and CI has neither key, so I unset only that variable. The lint step reported `SDK-LINT: PASS`, the three contract checks reported ok, and pytest ended:
```
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 6254 passed, 16 skipped in 106.33s (0:01:46) ============
```
The failure is `AssertionError: assert 148 == 120`. **It is inherited:** on the pristine base `845a4d9b`, before T existed, `pytest tests/features/harness_threads/test_harness_threads_surface.py` gave `1 failed, 8 passed` with the same `assert 148 == 120`. The test pins main's `FailureCode` count at 120 and reads the count at `merge-base origin/main HEAD`. At `845a4d9b` that count is 148; at `6f5a7310` it is 167.

## Coordinator check (origin/main tip `6f5a7310` + T + P')

This ran in a detached scratch worktree under the scratchpad, which I have since removed (`git worktree list` no longer shows it).
1. Before any cherry-pick, `test_harness_threads_surface.py` gave `1 failed, 8 passed` with `AssertionError: assert 167 == 120`. That proves the inherited failure on the tip.
2. `git cherry-pick 22fe9fc5 c6d88e88` exited 0 with no conflict. `git log --oneline origin/main..HEAD` then showed exactly `527fd18f fix(provider-keys): …` and `a7884b5b test(provider-keys): …`. `diff <(git diff 6f5a7310 HEAD) <(git diff 845a4d9b c6d88e88)` printed `identical`.
3. T alone (`a7884b5b`): `12 failed, 126 passed in 2.61s`. T then P' (`527fd18f`): `138 passed in 3.16s`.
4. Source stage on the tip combination: `SDK-LINT: PASS` with no REGRESSED, then `=========== 1 failed, 6454 passed, 16 skipped in 133.56s (0:02:13) ============`. The only failure was the same test with `assert 167 == 120`.

The hotfix branch is not this scratch branch, because of the deviation above. It holds the same two commits on main's previous commit, with a byte-identical tree delta.

Push: `git push -u origin fix/meta-llm-key-shape` created `[new branch]`. `git ls-remote` shows `c6d88e8873239e073e79aa54e48bb72aaf073034 refs/heads/fix/meta-llm-key-shape`. No PR was opened.

## Merge-forward into Run B

- `PRE=91c77abf47b8748914d055540529bae3f1c02030`. That is the orchestrator's pipeline commit, which already equalled origin. `git merge-base HEAD fix/meta-llm-key-shape` gave `845a4d9b`, so the merge brings in only T and P'.
- `git merge --no-ff --no-commit fix/meta-llm-key-shape` merged the two registries files, `test_provider_keys_contract.py` and `test_provider_keys_property.py` cleanly, because both sides made identical changes. Six pack files conflicted, with 11 hunks in all: FEATURE.md 2, README.md 1, fixtures 2, agents 3, matching 2, modes 1. Each hunk is a place where both sides inserted at the same spot, and Run B's side covers T's:

| File | Run B's side | T's side |
|---|---|---|
| matching | the `meta` root, and the S2 test `test_m18_offers_vidbytes_own_meta_account_…` | a 3-line comment explaining the left-out root, and nothing |
| modes and agents | ROLE lines that cite S2 plus r4 AC-16 / AC-17 | ROLE lines that cite r4 only |
| agents | `K_META_2`; `MetaAgentTests` with its S2 docstring and 3 S2 tests | nothing; T's 1-line docstring |
| fixtures | `K_META_2` and its `__all__` entry | nothing |
| FEATURE.md | 5 S2 failure modes and the S2+r4 suite-map lines | nothing; r4-only suite-map lines |
| README.md | the S2, r4 and r4-tidy log lines | the hotfix's own log line |

- **Superset proof before resolving.** I ran `<scratchpad>/s5h_superset_check.py 22fe9fc5 91c77abf 845a4d9b`. For every test method in T it computes the code lines T adds over the base, comments and blank lines removed (every table row is one line). It then requires the same `class::test` in Run B to hold each of those lines at least as often. It also requires every module-level name T adds or changes (`K_META_DOC`, `__all__`, `POOL`, `PROVEN`, `MATCHER_SOURCE`, `REGISTRIES_README`, `META_EXAMPLE_KEY`) to have the same source text in Run B. Output: `tests T adds or extends: 12; added code lines checked: 174` and `RESULT: Run B contains every test, row and module name of T`. T has no test or row that Run B lacks, so I added nothing to Run B's tests.
- The doc text on T's side is the r4 wording for main, and Run B's r4 lines say the same in full. The hotfix's README log line is the only T-only sentence; it is subsumed by Run B's "S2 r4" line, so it is not carried.
- Resolution: `git checkout --ours <file> && git add <file>` for all six files. `git ls-files -u | wc -l` then printed 0, and `git diff --cached 91c77abf --name-only | wc -l` printed 0.
- Commit `db5ad22be77326ee60ee97550230b1bb9a7267fe` has the prescribed message.

**Verification:**
```
$ git diff 91c77abf HEAD --stat          # (empty)
$ git rev-parse 91c77abf^{tree} HEAD^{tree}
f98262f8f20f2c324371dde751a1ed0d1e469cdd
f98262f8f20f2c324371dde751a1ed0d1e469cdd
$ git diff 263fa4e9 HEAD --stat -- tests # (empty)
$ git merge-base --is-ancestor 22fe9fc5… HEAD; echo $?   # 0
$ git merge-base --is-ancestor c6d88e88… HEAD; echo $?   # 0
$ PYTHONPATH=$(pwd) env -u DEEPSEEK_API_KEY py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider
192 passed in 2.77s
$ git push origin feat/meta-muse-managed-text
   91c77abf..db5ad22b  feat/meta-muse-managed-text -> feat/meta-muse-managed-text
```
This report is committed on Run B after the merge, as a docs-only commit.

## Things noticed and not fixed (out of scope)

- **The root README on main names no Meta prefix.** The Prefixes bullet at `README.md:290-293` lists only the Anthropic, OpenRouter, OpenAI, xAI and Gemini prefixes; it has left Meta out since #1027. The hotfix does not make it false, but if the hotfix ships alone, main documents neither Meta form until Run B's `874890bd` lands. The root README was out of scope by rule.
- **FEATURE.md says "Historical Regressions: None yet." on both branches.** That is despite a fixed misrouting bug, and the feature-pack doctrine asks for one line per fixed bug. Adding the line on T alone would have auto-merged into Run B and changed its tree, so the line belongs in Run B, or in both branches together, in a later pass.
- **`test_failure_codes_keep_main_…`** is stale on main (it expects 120 but finds 148 or 167). That is inherited; see the field guide's local-ci-verification entry.
- **Main's lint baselines have slack** (for example, A002 703 → 562 and S010 5 → 0). Those are not mine to lower.

## Notes for the next agent

- If the hotfix PR is **squash-merged**, then the next time main is merged into Run B, these same 6 pack files will conflict again. The registries files will not, because their content is identical. Resolve each pack file to Run B's side; this report proves Run B's side is a superset. If the hotfix PR is merged with a merge commit, main contains T and P' themselves and no conflict arises.
- The spec IDs cited in T's comments (meta-muse-managed-text FR-9, INV-16, and so on) point at `docs/spec/meta-muse-managed-text/spec.md`, which exists only on Run B until it lands. The pack README log line on the hotfix says where that spec lives.
- This shell exports `DEEPSEEK_API_KEY` and `VIDBYTE_API_KEY`. Run every provider-keys gate with `env -u DEEPSEEK_API_KEY`.
- The scratch tools, all under `<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`:
  - `s5h_subtest_audit.py`: per-subtest failure reasons for the pack.
  - `s5h_superset_check.py <T> <RunB> <base>`: proves T is a subset of Run B.
  - `s5h_probe_meta_fallback.py`: the live misroute probe.
  - Logs: `s5h_red_audit.txt`, `s5h_source_hotfix.txt`, `s5h_source_tip.txt`, `s5h_lint_hotfix.txt`, `s5h_merge_conflicts.diff`.
