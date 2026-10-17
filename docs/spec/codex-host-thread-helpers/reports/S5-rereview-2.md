LENS: conformance
VERDICT: SOUND — R-16, R-17 and R-18 hold against their original evidence. Each of the three main merges kept both sides exactly. The PR's net diff against main still carries every behaviour this run built, and I found no regression and no new finding.

Scope: post-repair re-review, round 2 of 2 (the last round). I reviewed every PR-authored commit in `git log --first-parent --no-merges 13a61e67..40eeebc4` and the three merges `b96b64cc`, `0ded7dc7` and `fca03aea`. I re-walked the spec IDs those changes touch. The code under review is `40eeebc4`, which is the PR head on GitHub and `origin/feat/codex-host`.

While I worked, the local HEAD moved to `0bd107c3`. That is the orchestrator's own commit, and it changes only `pipeline.md`. It is not pushed. I wrote no file except this report, and `git status --porcelain` was empty after every gate I ran.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Each of the three merges is exact in both directions.** I compared, with `-U0` and without index lines or hunk headers:
  - the PR's net diff before each merge with its net diff after it;
  - main's own diff with what each merge brought in.

  `b96b64cc` differs only on the one resolved line, `CodexAgentError.__init__(…, error_type="", next_step="", thread_id="")`. `0ded7dc7` and `fca03aea` differ by 0 lines. The net diff now covers 57 files, +14712/-23, and `40eeebc4` matches `fca03aea` there. Both intents still work:
  - **Main's #1116.** The transport sets `thread_id=str(thread.id)` (`agents/codex/transport.py`), and `_run_turn` adopts it (`agent.py:302-305`). `tests/test_codex_failure_recovery.py` passes in the area run.
  - **This PR.** `next_step` drives `repair_approaches` (`lib/errors/base.py:162-163`). A probe prints `both th_1 Do Y. ('Do Y.',)` · `main_style th_2 ''` · `pr_style '' Do Z.`.
  - **Main's #1121.** The context capture in `CodexToolCallHandler.__init__` (`agents/codex/tools.py:148`) reaches the PR's per-thread `bridge.handler(…)` (`host.py:668`).
- **The R-17 and R-18 fixes keep exactly what INV-22, INV-35 and codex-host EC-52 promise.** These are the only two sites that rebuild a `CodexAgentError` from another one. A grep of every `exc.failure_code` / `.thread_id` / `.next_step` read in the Codex packages finds `skill_functions.py:248` and `host.py:477`, and nothing else.
  - A direct probe of `_unchecked` reports `r17_changed []`. Only `message`, and `actual`, which mirrors it, differ.
  - My own mutants are each killed by S2's tests: drop `error_type`, drop `thread_id`, drop `next_step`, or revert to the pre-fix line. Any of these at `skill_functions.py:248` fails both `CodexRunReRaiseTests` tests. Any of the first two, or the revert, at `host.py:477` fails `CodexHostLaunchRebuildFieldTests`. The unmutated control passes all 3, and each run imported `vidbyte` from its scratch copy.
- **The user's settled asks are intact after the merges.**
  - `CodexHost` has 27 public async functions, and `CodexHostTools` has 26 tools. `"delete_codex_thread" in names()` is `False`.
  - All 57 test names in the spec's Proof cells exist, and every one passes. The codex_host pack has no skips. The area run's only 2 skips are platform skips in `harness_threads`.
  - Importing the native package loads no `openai_codex` module (INV-31).
  - `host.py` has 893 lines, under the cap of 900.
- **The gates match the briefing on my own runs.**
  - Lint: `SDK-LINT: PASS`, with A001 642, A007 255, C008 45, S008 19, S024 25 and S064 4, all RATCHETED, and no REGRESSED row.
  - Source stage: `1 failed, 6236 passed, 26 skipped`. The one failure is inherited: main's `FailureCode` has 148 members at both `f7f32b19` and `d5c1532d`, and the test asserts 120.
  - Public API: current, 640 exports.
  - The 4 remote checks on `40eeebc4` are `completed success`.

FINDINGS (ranked, most severe first, max 15)
None. I raise no R-C2xx finding. Each candidate I checked is listed under "Checked and left alone" below, with the reason it is not a defect against the spec, `request.md` or a settled decision.

VERIFIED CLAIMS: each claim checked, and whether it held
- **R-16, fixed @ddc432fe: HELD.** `vidbyte/lib/enums/__init__.py:36-38` now names `test_codex_host_helper_surface.py` and `test_codex_host_packaging.py`. The commit message says that dropping `CodexSkillScope` from `__all__` "fails only the packaging file", and that holds. My mutant gives `2 failed, 198 passed`: `test_existing_export_lists_gain_only_the_new_names_in_place`, plus `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores`. The second one is an artifact of the copy, which has no `REPO_MAP.md`: the unmutated copy fails it the same way (`1 failed, 6 passed` over packaging).
- **R-17, fixed @5e30a226: HELD.** See the mutants above. `exc.safe_runtime_details.get("error_type", "")` is needed, because `CodexAgentError` has no `error_type` attribute (probe: `has_error_type_attr False`; `base.py:152-166`).
  - The rebuilt error is raised `from None`, and so is the original: `connection.py:201,255` map with `from None`. So no chained cause is lost.
  - The new comment lines are 66, 64 and 53 columns wide.
- **R-18, fixed @804bbc91: HELD.** It keeps codex-host EC-52's promise of "the mapped error, saying k turns were started and interrupted" (`docs/spec/codex-host/spec.md:489`), together with INV-37 (`:376-377`) and D-22 (`:624`). The new comment line is 68 columns wide.
  - The fix changes no reachable behaviour of an existing method (INV-1, INV-30). No codex-host path sets either field today: `CodexErrorMapper.error` passes neither (`errors.py:65`), and `from_exception` always goes through `error()` (`errors.py:66-94`).
- **The spec rewording @04aa8cbe, and §17 deviation 9: HELD.**
  - INV-22 and INV-35 now read "keeps every field it carried (code, operation, next step, error type and thread id), and only its message changes". The code and the probe agree.
  - Deviation 9 is accurate. Its precedent claim is true: `c181be65:host.py:459-460` is the old rebuild that §12.3 row 10 cites. The rewording left no stale "code, operation and next step" field list in the spec, in review.md or in the code comments (grep). The test-plan rows for R-17 and R-18 match the tests.
- **The tests were not weakened: HELD.** `b769621c` moves `FieldCarryingMapper`, `KEPT_ERROR_FIELDS` and `changed_error_fields` into `codex_host_support.py` unchanged. The old inline "exactly one mapped error" assert became `FieldCarryingMapper.only()`, which raises the same `AssertionError`.
  - The `tests/` lines removed since `13a61e67` are all main's, from its Jev and prompt tests.
  - `test_codex_host_threads.py` and `lint/baseline.json` have a 0-line diff from `c181be65` (AC-35, §14).
- **The PR's net diff carries every behaviour this run built: HELD.** Between round 1 (`8daf854c` against `72a4ade1`) and now (`40eeebc4` against `f7f32b19`), the PR's own vidbyte lines changed in exactly three places: the R-16 header, the two fix lines, and the base.py union line. Everything else is S2's test text.
  - The run-authored commits added exactly the 4 vidbyte files of §8.4, plus S2's test files.
  - The run-authored commits made no change to `native/__init__.py`, `native/codex/__init__.py`, `toolsets/__init__.py`, `REPO_MAP.md`, the harnesses README, `pyproject.toml`, `contracts/`, `lint/baseline.json`, `preflight.py`, `errors.py`, `turns.py`, `oneshot.py`, `dataclasses/codex.py` or `lib/errors/`.
  - `base.py` differs from main only through the original #1055 `next_step` change, carried by the merge.
- **The briefing's niche facts mostly HELD. Two are out of date, and neither is a defect.**
  - Held: R-2 (`__all__` puts `CODEX_USER_MESSAGE_ITEM_TYPE` right after `CODEX_COMPACTION_ITEM_TYPE`, and `__all__` has no duplicates).
  - Held: R-3 (`thread_helpers.py:62,94,127,187` and `skill_functions.py:85` carry their bounds; `since` at `:92` has none).
  - Held: R-7 (the TESTS lines of `result.py:10`, `constants/codex.py:9`, `enums/codex.py:9` and `enums/failure.py:9`).
  - Held: deviation 5 (the docstring at `toolsets/codex.py:54` names the exception; `c81ba632:…:54` had the old line; the pinned `toolsets/__init__.py:11` is unchanged).
  - Out of date: "host.py is 892 lines". It is 893, as `S5-repair-4.md` says.
  - Out of date: "mergeStateStatus BLOCKED". GitHub now answers `BEHIND`, `MERGEABLE`, because main moved to `d5c1532d` (#1162) after `fca03aea`. #1162 changes only `vidbyte/middleware/compaction/strategies.py` and `tests/test_context_compaction_middleware.py`. It shares no file with the PR, and a trial `git merge-tree` against it has 0 conflicts.
- **The gate claims from the briefing: HELD.**
  - Area: `1 failed, 738 passed, 2 skipped` over the four suites I chose (686 + 52 from `test_codex_failure_recovery.py`).
  - Lint passes, and the API is current with 640 exports.
  - Source: `1 failed, 6236 passed, 26 skipped`.
  - The 4 remote checks on `40eeebc4` are success.
- **AC-1 and the §4 snippet: HELD, through the automated proof only.** `test_the_section_4_snippet_prints_its_seven_lines` PASSED. I did not run the live snippet, because it spends the user's plan (briefing §6). Since round 1, no change touches the §5 call path.
- **Commit hygiene: HELD.** Every PR-authored commit since `13a61e67`, the three merges included, ends with `Co-Authored-By: Claude Opus 5.5`. No added line adds `noqa`, `type: ignore`, a skip, an xfail or a baseline change. No `.pyc` file is tracked.
- **Checked and left alone (not findings).**
  - `host.py`'s TESTS header does not list `test_codex_host_review_gaps.py`, which now holds the R-18 test. §12.5 asks only for the test files this run's S2 created, and review_gaps predates this run. It was already missing from the header before this run, along with router, bridge and sdk_contract.
  - The R-17 and R-18 tests patch the connection's `CodexErrorMapper` with a wrapper over the real mapper. §13's do-not-mock list (`CodexHost`, collaborators, `CodexConnection`, translators) does not include the mapper. The pack already patches names in the connection module through `patch_connection`, and test-plan rows 66-67 record the seam. That helper's docstring still says "one bound" (`codex_host_support.py:344`): a test-text nit.
  - Spec §17 lists S5 deviations 5, 8 and 9 under the heading "Implementation deviations (S3)", and has no revision row for the INV-22/INV-35 rewording. Each item names S5 itself. Round 1 accepted the same shape for R-5's INV-19 rewording.
  - The two rebuild sites now hold identical copy-every-field logic (AGENTS.md §5). The shared helper is an orchestrator-settled follow-up, because `base.py` and `errors.py` are outside §12.3.
  - `CodexErrorMapper.error` still sets neither field, so R-17 and R-18 are latent today. That is settled as an owner follow-up.
  - Main's #1121 binds a host thread's tool calls to the ceiling active at spawn. Briefing §4 settles this as a follow-up.

COMMANDS RUN: each command with its final lines (VPY = `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`; S = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/rr2`)
- `git log --first-parent --no-merges --oneline 13a61e67..HEAD` → 15 commits, from `ddc432fe` to `40eeebc4`. `git rev-parse HEAD origin/feat/codex-host` later gives `0bd107c3…` and `40eeebc4…` (`0bd107c3` changes only `pipeline.md`).
- `git show b96b64cc -- vidbyte/lib/errors/base.py` → `++    def __init__(self, message: str, *, failure_code: str, operation: str, error_type: str = "", next_step: str = "", thread_id: str = "") -> None:`, with main's `self.thread_id` lines auto-merged.
- Net-diff comparisons (`git diff -U0 <base> <tip> -- . ':!docs'`, without index lines or hunk headers):
  - `net(72a4ade1..13453ea3) vs net(cb554ed3..b96b64cc): 6 differing lines` (the signature only);
  - `net(cb554ed3..2e60369c) vs net(8da41971..0ded7dc7): 0`;
  - `net(8da41971..04aa8cbe) vs net(f7f32b19..fca03aea): 0`;
  - `net(f7f32b19..fca03aea) vs net(f7f32b19..40eeebc4): 0`, which is `57 files changed, 14712 insertions(+), 23 deletions(-)`.
  - Main's side: `main(72a4ade1..cb554ed3) vs merge(13453ea3..b96b64cc): 6` (the signature) · `main(cb554ed3..8da41971) vs merge(2e60369c..0ded7dc7): 0` · `main(8da41971..f7f32b19) vs merge(04aa8cbe..fca03aea): 0`.
- `PYTHONPATH=$(pwd) $VPY -m pytest -q -rA …::CodexRunReRaiseTests …::CodexHostLaunchRebuildFieldTests` → 3 `PASSED` · `3 passed in 1.20s`.
- `PYTHONPATH=$(pwd) $VPY -m pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py tests/test_codex_failure_recovery.py` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 738 passed, 2 skipped in 53.05s`. The run with `-rs` over codex_host and harness_threads gives `1 failed, 635 passed, 2 skipped`. Its skips are the two `harness_threads` platform skips (launcher:100, runner:245).
- `$VPY -I S/mutate.py S/base S/mut $VPY …` (each copy from `git archive HEAD vidbyte tests pyproject.toml`; `loaded_from=…\scratchpad\rr2\mut\<mutant>\vidbyte\…`):
  - `control: exit=0 :: 3 passed`;
  - `r17_no_error_type`, `r17_no_thread_id`, `r17_no_next_step` and `r17_pre_fix`: each `exit=1 :: 2 failed`;
  - `r18_no_error_type`, `r18_no_thread_id` and `r18_pre_fix`: each `exit=1 :: 1 failed`;
  - `r16_drop_from_all: exit=1 :: 2 failed, 198 passed`. The control copy over packaging gives `1 failed, 6 passed`, with the same REPO_MAP artifact.
- `$VPY lint/run.py` → `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` · `exit=0`, and the porcelain is empty.
- `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` → `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 6236 passed, 26 skipped in 100.06s (0:01:40)` · `CI failed: Command failed with exit code 1: …python.exe -m pytest`. Then `generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at d08e89ef75ff4a6ee07465ee5097363e7d0d26c4 (vidbyte-sdk 0.3.0, 640 exports).` · `api_exit=0`, and the porcelain is empty.
- `PYTHONPATH=$(pwd) $VPY S/probe_facts.py` → `host_public_async 27` · `tools 26 delete_in_names False` · `signature (self, message: 'str', *, failure_code: 'str', operation: 'str', error_type: 'str' = '', next_step: 'str' = '', thread_id: 'str' = '')` · `has_error_type_attr False` · `r17_changed []` · `r17_details_equal_but_actual {'actual': 'm Suffix.'}`.
- `git show <ref>:vidbyte/lib/enums/failure.py | $VPY -I -c <AST count>` → `f7f32b19 148` · `origin/main 148`. The test asserts `== 120` at the merge base, so it fails on main too.
- `gh pr view 1055 --json mergeable,mergeStateStatus` → `{"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE"}`. `gh api …/commits/40eeebc4…/check-runs` → `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success`.
- `git merge-tree $(git merge-base HEAD origin/main) HEAD origin/main` (the legacy mode, which writes nothing) → 0 conflict blocks. `git diff --name-only f7f32b19 origin/main` compared with the PR's files → no shared file.
- The proof-name check (57 `test_codex_host_*.py::test_*` names in spec.md) → `proof names: 57, missing: 0`. The pytest run `-rA` over helper_lifecycle and the two AC-35 tests → `7 passed in 1.35s`, the snippet test included.
- The comment-width scan of the net vidbyte diff against main → `0` added `#` lines over 72 columns.
- The suppression and trailer scan of `13a61e67..40eeebc4` → no hits. Every commit has `Claude Opus 5.5 <noreply@anthropic.com>`. `git ls-files '*.pyc'` → `0`.
- The INV-31 probe → `openai_codex loaded: []`. `grep` finds no `host` import in `native/codex/skill_functions.py`.
- `wc -l` → `host.py 893`, native `skill_functions.py 251`, native `thread_helpers.py 279`, tool `thread_helpers.py 240`, tool `skill_functions.py 212`, `codex_host_support.py 710`.
