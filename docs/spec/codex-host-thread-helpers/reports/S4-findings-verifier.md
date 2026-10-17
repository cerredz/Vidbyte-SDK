# S4 findings verifier: codex-host-thread-helpers

Stage: S4 findings verifier · Diff: `git diff c181be6577245e8112d7a781deb814e088b6c1ab...c81ba632` (worktree HEAD `0fc25a35` adds only `pipeline.md`) · Spec r3 · Date: 2026-10-16
Inputs read in full: the three S4 reviews, request.md, spec.md r3, test-plan.md, the S3 report (outcome and commits), house-style.md, the review.md format, and the field-guide index plus `model-facing-tool-contracts.md` and the bounds section of `strict-config-dataclasses.md`.
Writes: `review.md` and this report only. Probes live in the scratchpad folder `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4-verifier/`. The worktree was only read: `git status --short` shows only the three untracked review reports, before and after.

## 1. Merge map (original IDs to merged IDs)

| Original | Lens | Proposed | Merged | Final | Why merged or kept apart |
|---|---|---|---|---|---|
| R-E1 (delete half: `thread_helpers.py:180`, M05) | engineering | Major | **R-4** | Major, CONFIRMED | Split from R-E1's goal-tool half: other file, other invariant (INV-9), other test to write. The verifier adds V05b (delete's `finally` release) to it. |
| R-E1 (goal-tool half: `tools/.../skill_functions.py:98-102`, M36) | engineering | Major | **R-1** | Major, CONFIRMED | Split as above (INV-27). |
| R-V2 + R-C3 | conventions + conformance | Major / Minor | **R-2** | Major, CONFIRMED | Same line (`skill_functions.py:66`), same failure (a wire value defined in a feature file, against §12.4 and request §C). Highest severity kept. |
| R-V1 | conventions | Major | **R-3** | Major, CONFIRMED | — |
| R-E2 | engineering | Major | **R-8** | Minor, DOWNGRADED | — |
| R-C1 | conformance | Minor | **R-5** | Minor | — |
| R-C2 + R-V4 | conformance + conventions | Minor / Minor | **R-6** | Minor | Same line (`toolsets/codex.py:54`), same false docstring. |
| R-C4 + R-V6 (+ verifier) | conformance + conventions | Minor / Minor | **R-7** | Minor | Same three TESTS lines. The verifier adds `vidbyte/lib/enums/failure.py:9`, also modified and also not naming the S2 files. |
| R-V3 | conventions | Minor | **R-9** | Minor | — |
| R-V5 | conventions | Minor | **R-10** | Minor | — |
| R-E4 | engineering | Minor | **R-11** | Minor | — |
| R-E7 | engineering | Minor | **R-12** | Minor | — |
| R-C5 + R-E5 | conformance + engineering | Minor [scope-adding] | **R-13** | Minor | Same code (`wire.py:561-573`), same dropped `SkillsListEntry.errors`. |
| R-E3 | engineering | Minor [scope-adding] | **R-14** | Minor | — |
| R-E6 | engineering | Minor [scope-adding] | **R-15** | Minor | — |

Totals: 4 confirmed Majors, 0 Blockers, 1 downgraded (R-E2), 0 refuted. Minors after de-duplication: 11 (R-5 to R-15).

## 2. Verification of every Blocker and Major

### Harness (my own, not the engineering reviewer's)

I read the engineering harness (`s4-engineering/mutate.py`, `run_all.py`, `mutant_plugin.py`). Its method is sound: a meta-path finder serves one module from a mutated copy, so the worktree is never edited. I did not reuse its files or results. I wrote my own:
- `verifier_plugin.py`: the same meta-path technique for any number of modules. The report header prints `loaded_from_mutant=True/False` for each module, so a probe that fell back to the worktree source is visible.
- `probe.py` / `probe2.py`: each probe applies exact-once text edits and runs the **widest codex set**: `tests/features/codex_host`, `tests/features/harness_threads` and all seven `tests/test_codex_*.py` modules (867 tests). Only the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` is deselected (`-k "not …"`).
- `a007_check.py`: runs the repo's own `OperationalConstantAnalyzer` (A007) on a file before and after a proposed fix.

Harness sanity:
- `V00_noop: exit=0 :: 864 passed, 2 skipped, 1 deselected in 52.55s`. A no-op edit passes, so the harness adds no failure of its own.
- `V01_since_exclusive: exit=1 :: 1 failed, 863 passed … FAILED …test_since_returns_the_inclusive_window_and_stops_at_the_first_older_thread`. A known bug is killed, so the mutated module really loads.
- Controls V36b and V36c (below) are killed, so the tool-module probes load too.

### R-1 (from R-E1, goal-tool half) — CONFIRMED Major, owner `tests`

- **Code read.** `vidbyte/tools/builtins/codex/skill_functions.py:98-103`: `RunCodexGoalTool._perform` reserves `ONE_TURN`, calls `run_codex_goal`, and releases in `finally`. Today the code is correct.
- **Spec.** INV-27: the run tools "hold one cap slot while the turn starts". The test plan's INV-27 row claims the mutant "a leaked slot" is killed.
- **Probe: `V36_goal_tool_slot_leak` (release only on success).**
  - Result: `exit=0 :: 864 passed, 2 skipped, 1 deselected in 53.08s`, with `loaded_from_mutant=True`. It **survives the whole codex set**.
- **Controls, the same mutation on the two other run tools.** Both are killed by `test_codex_host_helper_tools.py::CodexHelperToolScopeTests::test_a_failed_or_cancelled_run_releases_its_slot`:
  - `V36b_skill_tool_slot_leak: exit=1 :: 1 failed, 863 passed`
  - `V36c_docs_tool_slot_leak: exit=1 :: 1 failed, 863 passed`
- **Why it survives.** I read that test (`:281-301`). It raises only for `run_codex_skill` and cancels only `run_codex_openai_docs`. `run_codex_goal` is used only as the final success probe.
- **Consequence of the regression.** A goal tool that leaks on failure locks the scope after `max_live_turns` failed goal runs. Every later run tool is then refused with `codex.session_busy`. Failed goal runs are common: `command_not_run`, `usage_limited` and spawn refusals.
- **Smallest fix (tests only).** In `test_a_failed_or_cancelled_run_releases_its_slot`, add a raising row and a cancel row for `run_codex_goal`. Then probe with another run tool. The pattern already exists in that test.

### R-4 (from R-E1, delete half, plus verifier V05b) — CONFIRMED Major, owner `tests`

- **Code read.** `vidbyte/harnesses/native/codex/thread_helpers.py:179-192`: `require_idle`, `reserve`, `try … finally: release`.
- **The reservation is the only guard.**
  - `CodexPreflight.require_idle` (`preflight.py:162-167`) refuses only when `self._registry.busy(thread_id)` or a start is in flight.
  - `CodexTurnRegistry.busy` (`turns.py:326-329`) is `thread_id in self._running or thread_id in self._reserved`.
  - So without `reserve`, a `continue_codex_thread` or `start_codex_review` started while `thread/delete` is in flight passes `require_idle`. It then resumes and starts a paid turn on a thread that is being deleted.
- **Spec.** INV-9 covers both compact and delete: "While `compact_codex_thread` or `delete_codex_thread` runs, the thread is reserved … released on every outcome". AC-23's proof covers compact only.
- **Probes.**
  - `V05_delete_no_reserve` (the M05 shape): `exit=0 :: 864 passed, 2 skipped, 1 deselected in 52.41s`, `loaded_from_mutant=True`. **Survives.**
  - `V05b_delete_release_only_on_success` (verifier addition: the release moved out of `finally`): `exit=0 :: 864 passed, 2 skipped, 1 deselected in 53.01s`. **Survives.**
- **Why V05b survives.** I read `test_an_unknown_thread_is_not_found_and_a_second_delete_finds_nothing` (`test_codex_host_thread_helpers.py:559-574`).
  - The failed delete on `thr-never` leaks its reservation, but the next call on that id is `get_codex_goal`, which never runs `require_idle`.
  - In the double-delete half, the failing second delete is the last call.
  - The compact twin, `test_a_failed_or_cancelled_compact_releases_the_thread` (`:630-647`), exists only for compact.
- **Smallest fix (tests only).** Two tests that mirror compact's AC-23 pair:
  - Hold `thread/delete` (`server.hold`). Assert that continue, review, compact and a second delete on that thread raise `codex.session_busy` and send nothing. Release, then show the thread is free. This kills V05.
  - Fail `thread/delete` once with -32603, then cancel a held delete. Assert that a following compact or delete on the same thread goes through. This kills V05b.

### R-2 (R-V2 + R-C3) — CONFIRMED Major, owner `code`, with a spec §17 line

- **Code read.**
  - `vidbyte/harnesses/native/codex/skill_functions.py:65-66` defines `USER_MESSAGE_ITEM_TYPE = "userMessage"`, and `:220` uses it.
  - `git grep '"userMessage"' -- vidbyte` finds that line and `vidbyte/lib/constants/codex.py:85`, inside `CODEX_SUPPORTED_ITEM_TYPES`.
  - The house precedent for one item-type value is `CODEX_COMPACTION_ITEM_TYPE = "contextCompaction"` (`constants/codex.py:324`, exported at `__all__` line ~556). There is a counter-precedent, `_COMMAND_ITEM` in `vidbyte/agents/codex/contracts.py:52`, but it predates this PR, and the AGENTS.md "Existing code" rule says not to copy such code.
- **Spec and request.**
  - §12.4: "Every bound, method name and fixed value is a named constant in `vidbyte/lib/constants/codex.py` … except message text constants." This value is not message text.
  - request.md §C Constraints: "Constants and flags go in `vidbyte/lib/constants/codex.py` … Never in feature files."
  - §17's seven deviations do not record it.
- **Adjudication (conformance said Minor, conventions said Major).** I keep Major. Behavior does not change, but the rubric's Major test is "would surface in human review". The owner has made this exact review comment before: field guide `model-facing-tool-contracts.md` cites PR #384 ("all enums/constants... should be defined in backend/lib"). The request records the rule as a constraint.
- **The pin trap (verified).** `test_codex_host_helper_surface.py:288` asserts `set(constants.__all__[-len(new_names):]) == new_names`. So appending the new name at the end of `__all__`, as R-V2 proposed, turns that S2-owned test red. Probe F02b below shows it.
- **Smallest code-only fix (probe F02, test-neutral):**
  - Define `CODEX_USER_MESSAGE_ITEM_TYPE = "userMessage"`, with a one-line comment, right after `CODEX_COMPACTION_ITEM_TYPE` (`constants/codex.py:324`).
  - Export it right after `"CODEX_COMPACTION_ITEM_TYPE"` in `__all__`. That is mid-list, beside its sibling, so the §9.3 tail is unchanged.
  - Import it in `skill_functions.py` and delete lines 65-66.
  - Record it as S3 deviation 8 in spec §17: a constant not in §9.3, exported beside its sibling instead of at the end.
  - Alternative (conformance's): record the deviation only and move the constant in a follow-up.
- **Probe results:**
  - `F02_user_message_constant_mid: exit=0 :: 864 passed, 2 skipped, 1 deselected in 54.18s`, with `loaded_from_mutant=True` for both `vidbyte.lib.constants.codex` and `skill_functions`. The fix is test-neutral.
  - `F02b_user_message_constant_end: exit=1 :: 1 failed, 863 passed … FAILED tests/features/codex_host/test_codex_host_helper_surface.py::CodexHelperConstantTests::test_section_9_3_constants_hold_their_values_and_are_appended_to_all`. The end-append variant breaks the S2 pin, so S5 must not use it.
  - The diff of the F02 constants file against the worktree is exactly 3 added lines (`324a325,326` and `556a559`).
  - `ruff check --select I001,F401,F821` passes on both F02 files (`--stdin-filename` with the real paths).
  - There is no numeric literal, so A007 cannot change. S015 needs `__all__` names to be statically bound, which they are.

### R-3 (R-V1) — CONFIRMED Major, owner `code`

- **Code read.** `git grep -n '"type": "integer"\|"type": "number"' -- vidbyte/tools/builtins/codex/` returns 12 numeric properties.
  - All 6 older ones carry a bound: `threads.py:92,96,167` (`"minimum": CODEX_HOST_MIN_TOKEN_LIMIT`) and `threads.py:97,168` and `live.py:61` (`"exclusiveMinimum": CODEX_HOST_MIN_EXCLUSIVE_SECONDS`).
  - None of the 6 new ones does: `tools/builtins/codex/thread_helpers.py:60,90,92,125,185` and `tools/builtins/codex/skill_functions.py:84`.
  - The same concept is inconsistent across two tools: `spawn_codex_thread.goal_token_budget` has a `minimum`, and `run_codex_goal.token_budget` has none.
- **Existing guards (they reduce the impact, but do not refute the finding).**
  - The tool's `_resolve_count` and `_resolve_timestamp` and the host's `RecordFieldValidator` refuse out-of-range values with `configuration.invalid_argument`.
  - The prose descriptions state the floors (`LIMIT_DESCRIPTION`: "a whole number of at least one"; `SINCE_DESCRIPTION`: "at least zero").
  - The ceiling of 1,000 is never stated: `LIMIT_DESCRIPTION` says only "Very large values are refused".
  - vidbyte does no JSON-schema validation of tool arguments (`git grep jsonschema|Draft7Validator -- vidbyte` is empty). So the bounds are model-facing and provider-facing only, and adding them changes no SDK-side execution path.
- **Spec.** The §9.2 tool table names types only, and says "The `limit` upper bound is enforced by the host". Schema bounds are additive and do not contradict that.
- **Why Major.** The finding breaks the grain of the repo in a model-facing contract: 6 of 6 sibling numeric schemas carry a bound. The owner's review history on tool schemas is the reason `model-facing-tool-contracts.md` exists. The fix is test-neutral and lint-neutral (below), so it costs almost nothing.
- **Smallest fix (refined from R-V1).** Add `"minimum": CODEX_HOST_MIN_LIST_LIMIT, "maximum": CODEX_HOST_THREAD_LIST_MAX_LIMIT` to the three listing `limit`s, `"minimum": CODEX_HOST_MIN_LIST_LIMIT` to the turns `limit`, and `"minimum": CODEX_HOST_MIN_TOKEN_LIMIT` to `token_budget`, with the imports. **Leave `since` alone**, unless a named zero constant is added through the spec.
- **A007 evidence** (`a007_check.py`, the repo's own analyzer):
  - `F01 vidbyte/tools/builtins/codex/thread_helpers.py: A007 before=0 after=0`
  - `F01 vidbyte/tools/builtins/codex/skill_functions.py: A007 before=0 after=0`
  - R-V1's literal `"minimum": 0` for `since` would be a new finding: `since-literal-0 …: A007 before=0 after=1 new=[(90, '0', "operational context contains 'limit'")]`. The ratchet is 255/255 with no slack, so lint would fail.
- **Test neutrality.**
  - `F01_schema_bounds: exit=0 :: 864 passed, 2 skipped, 1 deselected in 54.08s`, with `loaded_from_mutant=True` for both tool modules.
  - The schema tests compare only property names, order, `required` and `type` (`test_codex_host_helper_tools.py:142-147`, `test_codex_host_tools.py:160-161`). They call `tool.execute` directly.
  - `ruff check --select I001` passes on both F01 files.

## 3. The downgrade

### R-8 (from R-E2) — DOWNGRADED to Minor, owner `tests`, follow-up

- **Probes (my own).** All three survive the whole codex set, with `loaded_from_mutant=True`:
  - `V02_any_turn` (turn-id filter dropped): `exit=0 :: 864 passed, 2 skipped, 1 deselected in 53.75s`.
  - `V03_any_skill_name` (name clause dropped): `exit=0 :: 864 passed … in 54.19s`.
  - `V04_casefold_name`: `exit=0 :: 864 passed … in 53.93s`.
  - The fake's only negative switch, `drop_skill_input` (`codex_host_fakes.py:958`), removes every skill entry.
- **Spec.** INV-34 does name both clauses: the turn whose id equals `handle.turn_id`, and an entry with type `skill` and **the sent name**. AC-39 proves only "no skill entry" and "never recorded". So the finding is real.
- **Why Minor.** For every input the current code can produce, the mutants behave exactly like the code. `run_skill` always reads a **brand-new** thread:
  - `spawn_codex_thread` always sends `thread/start`.
  - The thread's **first** turn is read with `limit=CODEX_HOST_INPUT_CHECK_TURN_LIMIT` (1) and `sortDirection: "asc"` (`wire.py:309-317`), and that turn is the handle's turn.
  - The input carries **exactly one** skill entry, the one sent (`skill_functions.py:147`).
  - So dropping the turn-id filter (M02), or the name clause (M03, M04), changes no result. A regression could only show after Codex rewrote the recorded skill name or put another turn first. The rollout evidence behind A-20 shows Codex records the sent `{type, name, path}` as sent.
  - This fails the Major test: it changes no behavior today, and it is not the kind of gap a human code review flags.
  - The tests to close it are a new fake switch plus 2-3 tests, which is follow-up sized.
- **Interaction.** It can ride along with R-1 and R-4 when the S2 test author is dispatched anyway. It is not a must-fix.

## 4. Minors passed through (verified only enough to set the owner and tag)

- **R-5 (R-C1).** `connection.py:89`: `SPENDING_RAW_METHODS = frozenset({CODEX_REVIEW_START_METHOD, CODEX_GOAL_SET_METHOD})`. `:203-210`: other raw methods keep `request_with_retry_on_overload` with its default attempts. So `thread/delete` may be resent after an overload, as EC-24, D-14 and A-14 accept. INV-19's "exactly once" contradicts the spec's own EC-24. Owner `spec`, trivial.
- **R-6 (R-C2 + R-V4).** `toolsets/codex.py:54` reads `"""Catalog of one agent tool per CodexHost function over one host.` There are 27 public methods and 26 tools. `git grep "Catalog of one agent tool\|one agent tool per" -- tests contracts` finds only the `FEATURE.md` title, which is not a pin. No lint rule checks docstring parity: the docstring-aware rules A001, C018, C020, S025 and S060 do not read class docstrings against package bullets. The pinned line is `toolsets/__init__.py:11`, so leave it alone (Q-18). Owner `code`, trivial.
- **R-7 (R-C4 + R-V6 + verifier).** These TESTS lines are stale:
  - `constants/codex.py:9`: `TESTS: python scripts/run_ci.py.`
  - `enums/codex.py:9`: the same.
  - `agents/codex/result.py:10`: `TESTS: Offline typed-result checks and python scripts/run_ci.py.`
  - `enums/failure.py:9`: `TESTS: python scripts/test-session-failure-vocabulary.py.`, which is also modified and pinned by `test_codex_host_helper_surface.py` and `test_codex_host_records.py`. This one is the verifier's addition.

  No test or lint rule pins these header texts. A001 needs only the field. Owner `code`, trivial.
- **R-8.** Section 3.
- **R-9 (R-V3).** `host.py:6` still gives the pre-collaborator recipe. `:121-123` narrates "connection, translators, registry and preflight", without `_threads` and `_skills`. The file is 891 lines, under the spec's cap of 900, so edit in place and add no lines beyond the headroom. Owner `code`, trivial.
- **R-10 (R-V5).** `tools/builtins/codex/delegation.py:4` reads "CodexHostTools lists these last". The file is outside §12.3, and §14 says to ask before touching any file outside it. Q-7 also leaves pre-existing modules alone. Owner `follow-up`.
- **R-11 (R-E4).** `GOAL_UNCHECKED_MESSAGE` and `SKILL_UNCHECKED_MESSAGE` say "was interrupted" even when `_interrupt` swallowed a failure (`skill_functions.py:229`). Both texts are exact §9.2 strings, pinned in `codex_host_support.py:221,224` and in `test_codex_host_helper_surface.py:98-101`. Owner `follow-up` (spec plus tests).
- **R-12 (R-E7).** `INPUT_NOT_RECORDED_MESSAGE` prints `CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS` (10.0). With the defaults (10 attempts, 0.5 s apart), the waits end after about 4.5 s. The text, its `{seconds}` source and the attempt count are pinned by the spec (§9.2, §9.3, A-19) and by tests (AC-39's exact 10 reads; the 600.0 and 0.25 expectations). Owner `follow-up` (spec).
- **R-13 (R-C5 + R-E5).** `wire.py:561-573` reads `entry.skills` only, so `SkillsListEntry.errors` is dropped. Tagged [scope-adding], owner `follow-up`.
- **R-14 (R-E3).** `_item` (`result.py:87-99`) keeps full payloads, `aggregatedOutput` included, and `ListCodexTurnsTool` is READ. These are the spec's chosen semantics (INV-17, D-25). Tagged [scope-adding], owner `follow-up`.
- **R-15 (R-E6).** `list_codex_skills` and its tool are unbounded. Tagged [scope-adding], owner `follow-up` (it is the skills twin of Q-19).

## 5. Disagreements adjudicated

1. **R-V2 (Major) against R-C3 (Minor).** Kept Major (section 2, R-2). Both reviewers' facts hold. The difference is calibration: "no behavior change" does not settle a placement rule that the owner states and has enforced in review. R-C3's own observation decides the fix shape: an end-of-`__all__` append breaks the S2 pin. I propose the mid-list placement, which neither reviewer offered.
2. **R-V1's `since` floor.** The reviewer offered `"minimum": 0` "or a named zero constant if A007 flags the literal". I ran A007: it does flag the literal (section 2, R-3). So the fix leaves `since` alone.
3. **R-E2 (Major).** Downgraded (section 3). The engineering reviewer's mutants do survive, but each of them is equivalent to the code on every path the current host can drive.
4. **R-E1.** Split in two, because the two halves have different owners in the test file, different invariants and different tests to write. My V05b widens the delete half: its `finally` release is untested too.

## 6. Severity blind spots checked (between the lenses)

- **Convention fixes that would break a conformance pin.** R-2: an end-append breaks `test_codex_host_helper_surface.py:288` (probe F02b). R-3: a literal 0 breaks the A007 ratchet. Both traps are in the fix text. No other confirmed fix touches a pinned text: `NATIVE_INIT_SHA256`, `REPO_MAP_SECTION`, `README_BULLET`, `toolsets/__init__.py:11`, `LIMIT_MESSAGE`, `SINCE_MESSAGE` and `QUERY_MESSAGE` are all untouched by R-2, R-3, R-6, R-7 and R-9.
- **host.py size.** R-9's edit must not push `host.py` past the spec's 900-line cap (NFR-2). It has 9 lines of headroom.
- **No new Blocker found.** I also checked these, and they hold:
  - `_unchecked` keeps code, operation and next step (INV-22, INV-35).
  - Compact's goal refusal releases the reservation (in `try`).
  - Lineage catches only `session_not_found`.
  - `thread_compact` is typed with no retry.
  - No READ path calls `_resume`: `grep -n "_resume(" thread_helpers.py` gives `:166` (in compact) and `:271` (the def).

## 7. Commands run (all read-only for the worktree)

- `git log --oneline -3`; `git status --short` (before and after); `git diff --stat c181be65…c81ba632 -- vidbyte tests`; `git diff --stat c81ba632 HEAD` (pipeline.md only).
- `git grep` for `"userMessage"|USER_MESSAGE`, `CODEX_COMPACTION_ITEM_TYPE`, `"type": "integer"|"number"`, `"minimum"`/`"maximum"`, `jsonschema`, `Catalog of one agent tool`, `ONE_TURN` and TESTS header lines; `sed -n` reads of every cited line.
- `VPY probe.py …` (V00, V01, V05, V05b, V36, V36b, V36c, V02, V03, V04, F01), `VPY probe2.py` (F02, F02b) and `VPY a007_check.py`. VPY is `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`. Every pytest run used `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`.
- `VPY -m ruff check --config lint/ruff.toml --select I001[,F401,F821] --no-cache --stdin-filename <real path> -` on the four fix files (F01, F02): `All checks passed!` each.
- Not run: the full `lint/run.py` and `run_ci.py` on the proposed fixes. Lint scans git-tracked files only, and the fixes exist only in scratch copies. A007 was run on the fix text through the rule's own analyzer instead. S5 must run the full gate after applying the fixes.
