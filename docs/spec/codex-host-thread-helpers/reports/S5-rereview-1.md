LENS: conformance
VERDICT: SOUND — All nine repaired findings (R-1 to R-9) hold against their original evidence, and I found no regression. One Minor gap is left: one modified file's TESTS header still names none of the S2 test files (§12.5).

Scope: post-repair re-review, round 1 of 2. I reviewed `git diff c81ba632..HEAD` (S2 round 2, S5 iteration 1 and docs) and re-walked conformance for `c181be65...8daf854c` where those commits touch it. HEAD is `8daf854c`; origin is at `03e1d7fd`. The only difference between them is `pipeline.md`. The worktree was clean before and after every command I ran (`git status --porcelain` printed nothing). This report is the only file I wrote in it, and it is untracked.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Every test-side fix can fail, and fails for the right reason.** I ran six mutants in a scratch copy, and each loaded from that copy (`loaded_from=…\scratchpad\rr1\mut\vidbyte\__init__.py`). Each was killed by exactly the new test written for it. The unmutated baseline gave `88 passed`.
  - V36: the goal tool releases only on success.
  - V05: delete takes no reservation. It failed with `AssertionError: CodexAgentError not raised`, which means the busy refusal was missing.
  - V05b: delete releases only on success.
  - V02: the read-back accepts any turn.
  - V03: the read-back accepts any skill name.
  - V04: the read-back folds the name's case.
- **The R-2 placement is the only safe one, and deviation 8 states the reason correctly.**
  - `CODEX_USER_MESSAGE_ITEM_TYPE = "userMessage"` sits at `vidbyte/lib/constants/codex.py:325-326`. It is exported right after `"CODEX_COMPACTION_ITEM_TYPE"` (`:559`) and imported by name at `vidbyte/harnesses/native/codex/skill_functions.py:27`. The feature file has no local copy left.
  - An end-append probe gives `1 failed, 20 passed` on `test_section_9_3_constants_hold_their_values_and_are_appended_to_all`, which is the pin at `test_codex_host_helper_surface.py:288`.
- **The R-3 bounds equal the runtime rules and change no runtime path.**
  - The probe reads `{'minimum': 1, 'maximum': 1000}` on the three listing `limit`s, `{'minimum': 1}` on the turns `limit` and on `token_budget`, and `{}` on `since`.
  - These are the bounds already enforced at `native/codex/thread_helpers.py:140,208` and `lib/dataclasses/codex_host.py:119`.
  - Nothing in `vidbyte/` reads `minimum` or `maximum` from a tool schema, so a value over 1,000 still reaches the host and becomes `configuration.invalid_argument` (AC-9's tool half passes).
- **The names and boundaries the owner cares about are intact.**
  - `CodexHost` has 27 public async functions, `CodexHostTools` has 26 tools, and `"delete_codex_thread" in names()` is `False`.
  - `host.py` has 892 lines.
  - These pinned files have an empty diff: `toolsets/__init__.py:11` (Q-18), `native/__init__.py`, `native/codex/__init__.py`, `REPO_MAP.md`, the harnesses README, `pyproject.toml`, `contracts/` and `lint/baseline.json`.
  - Since S3, the only file added under `vidbyte/` or `tests/` is `tests/features/codex_host/codex_host_helper_fakes.py`, and S2 removed no test function.

FINDINGS (ranked, most severe first, max 15)
R-C101 [Minor] [conformance: §12.5 / completeness of the R-7 fix] vidbyte/lib/enums/__init__.py:33-35 — A modified file's TESTS block still names no S2 test file, so §12.5 is unmet on a file that R-7's list missed
  Evidence: `vidbyte/lib/enums/__init__.py` is modified by §12.3 row 3. Its diff adds `CodexSkillScope` at `:57` and `:213`. Its header still reads:
    `TESTS:` / `tests/test_jev_agent.py and tests/test_jev_run_brief.py.` / `Configuration and runtime tests cover the exported enum namespace.`
    That export is pinned by the S2-created `tests/features/codex_host/test_codex_host_helper_surface.py:238-244` (`import vidbyte.lib.enums as enums` … `self.assertIs(enums.CodexSkillScope, CodexSkillScope)`) and by `test_codex_host_packaging.py:70` (`ENUMS_CODEX_ORDER`, "the Codex* order in vidbyte.lib.enums.__all__").
    `grep -n "enums/__init__"` over review.md, S4-findings-verifier.md and S5-repair-1.md finds no mention. R-7 listed four files, and S5 fixed exactly those four (`4fbc88b6`).
    The other modified file without such a line, `vidbyte/tools/builtins/__init__.py` (row 17), has a "Context Protocol Header" with no TESTS field at all, so §12.5 has nothing to update there.
  Failure: §12.5 says "`TESTS:` lines of the new and modified files name the test files S2 created in `tests/features/codex_host/`". After the repair, 17 of the 18 modified files meet this or have no TESTS field. This one does not. An agent that changes the enum export list reads this header and sees only Jev tests, not the two Codex pins that turn red. The behavior is unchanged.
  Smallest fix: Append `tests/features/codex_host/test_codex_host_helper_surface.py and tests/features/codex_host/test_codex_host_packaging.py (the Codex* export order).` to the TESTS block at `:33-35`. Keep the block's indented multi-line form. This is one header line and needs no test change. Otherwise, list it as a PR-body follow-up beside R-10.
  Spec IDs: §12.5 (TESTS lines); NFR-8 (A001 headers stay true); review R-7

VERIFIED CLAIMS: each claim checked, and whether it held
- **R-1, fixed @6c5eca2a: HELD.** `test_a_failed_or_cancelled_goal_run_releases_its_slot` (`test_codex_host_helper_tools.py:303`) PASSED. Mutant V36 is now killed by it. Before the fix, the review recorded `864 passed`. The code under test is `vidbyte/tools/builtins/codex/skill_functions.py:102-103` (`finally: self._scope.release(ONE_TURN)`).
- **R-4, fixed @6a434afd: HELD.** Both new tests PASSED: `test_a_delete_in_flight_holds_the_thread_until_it_ends` (`test_codex_host_thread_helpers.py:649`) and `test_a_failed_or_cancelled_delete_releases_the_thread` (`:689`). Mutant V05 (no reserve at `native/codex/thread_helpers.py:180`) is killed by the first. Mutant V05b (release moved out of the `finally` at `:192`) is killed by the second.
  - INV-9's four refusals (continue, review, compact and a second delete) are each asserted with `BUSY_TEXT` and an empty log.
- **R-8, fixed @30a0a0ac: HELD.** The two new tests at `test_codex_host_goal_skills.py:509` and `:533` PASSED.
  - V03 and V04 (the name clause at `native/codex/skill_functions.py:160`) are killed by the first test.
  - V02 (the turn-id filter at `:219`) is killed by the second.
  - Each test first asserts that the fake recorded a skill entry, so only the clause under test can explain the miss.
- **The fake split @72e34b81 is a move: HELD.** Every removed line reappears in `codex_host_helper_fakes.py`. The only exceptions are lines rewritten to reach the shared module through `_fakes()` or to pass the thread explicitly (`source_kind(thread)`), the moved `_record_turn_input`, and header text.
  - The two new switches, `recorded_skill_name` (None) and `input_on_earlier_turn` (False), are off by default (`:99-100`). With both off, `_record_turn_input` (`:153-166`) does exactly what the old inline block did.
  - The handler table splices in the same seven entries in the same order (`:106-115`).
- **R-2, fixed @54f599de: HELD.** See "gets right": the probe, the end-append probe and ruff `I001,F401,F821` ("All checks passed!").
  - §17 deviation 8 is accurate. The tail pin at `:288` compares the set of the last `len(new_names)` names to the §9.3 and enum names, which is "exactly the §9.3 names".
- **R-3, fixed @dd3fe2c2: HELD.** The bounds were checked by value in the probe. `A007 255/255 RATCHETED`.
  - `since` stays unbounded. No existing zero-valued constant names a timestamp floor: the only candidates are `CODEX_ROOT_FORK_DEPTH`, `CODEX_ZERO_DURATION_MS`, `CODEX_PRIMARY_CHAIN_INDEX`, `CODEX_COMMAND_SUCCESS_EXIT_CODE` and the exclusive `CODEX_HOST_MIN_EXCLUSIVE_SECONDS = 0.0`. So a bound without a numeric literal would mean a new constant, and that is not raised.
- **R-5, fixed @3d1ff4e2: HELD.**
  - INV-19 now reads "One `thread/delete` is sent per call, through the raw path, which the SDK may resend after an overload refusal (EC-24, A-14)."
  - The code matches it. `native/codex/thread_helpers.py:189` uses `connection.raw`. `connection.py:209-210` keeps `request_with_retry_on_overload` for every method outside `SPENDING_RAW_METHODS = {review/start, thread/goal/set}`.
  - The parallel weighted words in INV-18 ("`thread/compact/start` is sent exactly once … no retry") also hold. openai-codex 0.162.1 `client.py:534-539` `thread_compact` calls `self.request`, not `request_with_retry_on_overload` (`:731`).
- **R-6, fixed @c3a3ef98: HELD.** The docstring at `toolsets/codex.py:54` names the exception. `git grep "one agent tool per CodexHost"` finds no test pin. The pinned bullet `toolsets/__init__.py:11` is unchanged (pin at `test_codex_host_packaging.py:249`).
  - The rewrite of §17 deviation 5 is accurate:
    - S3 left the old docstring: `git show c81ba632:vidbyte/tools/toolsets/codex.py`, line 54.
    - The new text is quoted correctly.
    - The header (`:3`, `:5`) and the `__init__` comment ("delete_codex_thread has none, so no model can delete a thread (INV-2)") both say that delete has no tool.
- **R-7, fixed @4fbc88b6: HELD for the four files named. §12.5 is still unmet on one file (R-C101).**
  - S5's `result.py` refinement is right. An `items()` mutant fails `thread_helpers` (4 failed), `goal_skills` (10 failed) and `helper_lifecycle` (3 failed). It passes `helper_surface` (10 passed), `records` (11 passed) and `helper_tools` (11 passed).
  - `grep` confirms that helper_surface mentions `list_codex_turns` only as a signature tuple (`:114`).
- **R-9, fixed @549c7475: HELD.** `host.py:6` gives the collaborator recipe. `:122-124` names `_threads` and `_skills`, and they are declared at `:136-137` and built at `:192-193`. The file has 892 lines.
  - No added `#` line in `c181be65...HEAD` is wider than 72 columns. I scanned every added line of every vidbyte file in the run diff.
- **Gate claims from the briefing: HELD.**
  - Area tests: `1 failed, 678 passed, 2 skipped`, inherited test only.
  - Lint: `SDK-LINT: PASS`. A007, C008, S008, S024 and S064 are at 255, 45, 19, 25 and 4, each RATCHETED. Only IMPROVED rows move.
  - API: current, 639 exports.
  - Source stage: `1 failed, 5957 passed, 25 skipped`, inherited test only.
  - Remote checks on `03e1d7fd`: Package, Static policy and Source / Python 3.11 and 3.12 are all `completed success`.
  - I did not re-run the semgrep and package stages locally. Semgrep needs `git add -A`, which changes state, and the package stage builds into the tree. Their remote twins passed on `03e1d7fd`, which carries all code.
- **The S5 commit hygiene claims: HELD.** Each fix commit touches only its finding's files, cites its R-ID and carries `Co-Authored-By: Claude Opus 5.5`.
- **AC-1 and the §4 snippet: HELD, but only through the automated proof.** `test_the_section_4_snippet_prints_its_seven_lines` PASSED. I did not run the live snippet, because it spends the user's plan and briefing §6 forbids paid turns. The fixes do not touch the call path in §5: they rename one constant and change schemas, headers and docstrings.
- **Re-walk of the IDs the changes touch: no divergence.** I checked INV-2, INV-9, INV-18, INV-19, INV-27, INV-34, AC-9, AC-21, AC-23, AC-33, AC-39, the §9.2 tool table, the §9.3 and §12.4 constant rules (deviation 8), §12.5, NG-14 and Q-18, NFR-2, NFR-7, NFR-8 and the §8.4 budget.
  - The §8.4 budget still has 4 new vidbyte files and no new dependency, configuration key or class from S5.
  - AC-21's "Exactly one `thread/delete`" still holds under its Given, and its test pins it.
- **Checked and left alone (not findings).**
  - Wire keys `"type"`, `"name"` and `"content"` stay literal at `native/codex/skill_functions.py:160,219`. They are dict keys on a translated record, not fixed wire values like `"userMessage"`, and no review raised them.
  - `"userMessage"` also appears in `CODEX_SUPPORTED_ITEM_TYPES` (`constants/codex.py:85`). `"contextCompaction"` sets the same precedent.
  - §17 has no S5 revision row. The S5 prompt does not require one.
  - A delete that is cancelled while its request is in flight releases the hold before Codex answers. INV-9 mandates exactly this ("released on every outcome: … cancellation"), so it is outside this lens and not a defect against the spec.

COMMANDS RUN: each command with its final lines (VPY = `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`; S = scratchpad `rr1` folder)
- `PYTHONPATH=$(pwd) $VPY -m pytest -q -rA tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 678 passed, 2 skipped in 51.65s`. The five S2 round-2 tests and `test_the_section_4_snippet_prints_its_seven_lines` are each `PASSED`.
- `$VPY lint/run.py` → `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS` · exit=0.
- `PYTHONPATH=$(pwd) $VPY scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 998dc0da01d5f4519e76a3d92f08c4cd9d59d0df (vidbyte-sdk 0.3.0, 639 exports).` · exit=0.
- `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` → `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 5957 passed, 25 skipped in 96.31s (0:01:36)` · `CI failed: Command failed with exit code 1: …python.exe -m pytest`. `git status --porcelain` afterwards printed nothing.
- `$VPY -I S/mutate.py S/mut $VPY` (scratch copy from `git archive HEAD vidbyte tests pyproject.toml`) → each of V36, V05, V05b, V02, V03 and V04 gives `exit=1` and exactly one `FAILED`, its own new test. Baseline: `88 passed in 6.14s`.
- V05 with `--tb=line` → `AssertionError: CodexAgentError not raised` · `1 failed, 3 passed`.
- End-append probe (`"CODEX_USER_MESSAGE_ITEM_TYPE"` moved to the end of `__all__`, run over helper_surface and records) → `FAILED …::test_section_9_3_constants_hold_their_values_and_are_appended_to_all` · `1 failed, 20 passed in 1.11s`.
- `items()` mutant (raises) → helper_surface `10 passed` · records `11 passed` · thread_helpers `4 failed, 27 passed` · goal_skills `10 failed, 14 passed` · helper_lifecycle `3 failed, 2 passed` · helper_tools `11 passed`.
- `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 $VPY S/probe_facts.py` → `R-2 value userMessage slot_after CODEX_COMPACTION_ITEM_TYPE is_last False` · the R-3 lines quoted above · `R-6 tools 26 delete_in_names False host_public_async 27` · `R-6 docstring Catalog of one agent tool per CodexHost function except delete_codex_thread, over one host.`
- `$VPY -m ruff check --config lint/ruff.toml --select I001,F401,F821 --no-cache` on the six touched code paths → `All checks passed!`
- An awk scan of every added `#` line in `git diff -U0 c181be65...HEAD -- vidbyte/` for width over 72 → no output.
- `git diff c181be65...HEAD -- lint/baseline.json | wc -l` → `0`. A test-function name diff between `c81ba632` and HEAD over the changed test files removed no test. The pinned-file diff (toolsets/__init__, native/__init__, native/codex/__init__, REPO_MAP, harnesses README, pyproject, contracts) → `0` lines.
- `gh api repos/cerredz/Vidbyte-SDK/commits/03e1d7fd…/check-runs` → `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success`. For `8daf854c`: `No commit found` (HTTP 422, not pushed). `gh pr view 1055` → `draft=true head=03e1d7fd state=OPEN`.
- `grep -n "def thread_compact" -A5 …/openai_codex/client.py` → `return self.request("thread/compact/start", …)`, with no retry wrapper.
- `wc -l` → `host.py 892`, `native thread_helpers.py 279`, `native skill_functions.py 250`, `tool thread_helpers.py 240`, `tool skill_functions.py 212`, `codex_host_fakes.py 894`, `codex_host_helper_fakes.py 237`, largest test file `724`.
