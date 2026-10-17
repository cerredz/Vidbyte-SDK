LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — The code keeps the spec's "never" and "exactly once" rules (no READ resume, the guard comes before every call, every wait is bounded, the slot is released in finally), but five plausible regressions to two safety invariants (INV-9 delete reservation, INV-27 goal-tool slot) and to the skill read-back (INV-34) still pass every codex test, so the test pack does not yet protect them.

Reviewed range: `git diff c181be6577245e8112d7a781deb814e088b6c1ab...c81ba632` (18 vidbyte files plus the tests). HEAD is now 0fc25a35, which changes only pipeline.md (`git diff --stat c81ba632 HEAD` shows 1 file, docs only), so the review stands.

WHAT THE IMPLEMENTATION GETS RIGHT
- There is exactly one `thread/resume`: `_resume` at vidbyte/harnesses/native/codex/thread_helpers.py:271-276. Its only caller is compact, at :166, after the goal refusal. get_codex_goal, delete and every listing helper load nothing. Mutants M06 (goal resumes) and M13 (delete resumes) are both killed.
- Compact (:157-158) and delete (:179-180) call `require_idle` and `reserve` with no await between them, and release in `finally` (:172, :192). Two racing helpers therefore cannot both pass, and a failed call never leaves a slot behind (M10 and M14 are killed).
- The skill read-back is bounded twice: by attempts and by a `loop.time()` deadline that is checked before each wait (vidbyte/harnesses/native/codex/skill_functions.py:203-223). It uses no hidden asyncio timeout. Both the goal path (:111-120) and the skill path (:153-158) interrupt on `BaseException` and then re-raise, so a cancellation still propagates (M07, M09, M15, M22 are killed).
- Every Codex call goes through `CodexConnection.call` (300 s bound, mapped `codex.*` codes). The four new failure codes all have next steps. The listing walk (1000 pages) and lineage (depth 100) are capped, and lineage re-raises any error other than session_not_found (M17 is killed). A hung app-server therefore fails with one bounded api_error and does not hang the caller.

FINDINGS (ranked, max 15)

R-E1 [Major] [test quality] vidbyte/harnesses/native/codex/thread_helpers.py:180 and vidbyte/tools/builtins/codex/skill_functions.py:98-102 — Nothing tests that delete holds a reservation or that a failed run_codex_goal tool call gives its cap slot back
  Evidence: Mutant M05 removes `self._registry.reserve(thread_id)` from delete. It gives `M05_full: exit=0 :: 192 passed` on tests/features/codex_host, and `M05_wide: exit=0 :: 328 passed` when tests/test_codex_output_contracts.py, test_codex_tools.py and test_codex_failure_recovery.py are added. Mutant M36 moves `self._scope.release(ONE_TURN)` out of `finally` in RunCodexGoalTool._perform. It gives `M36_full: exit=0 :: 192 passed`. The AC-23 tests (tests/features/codex_host/test_codex_host_thread_helpers.py:603-647) hold only `thread/compact/start`. `test_a_failed_or_cancelled_run_releases_its_slot` (tests/features/codex_host/test_codex_host_helper_tools.py:281-301) raises only for run_codex_skill and cancels only run_codex_openai_docs; run_codex_goal is used there only as the passing probe. The test-plan row says the slot leak is killed, which holds for two of the three run tools only.
  Failure: If a later change drops the reservation, a continue_codex_thread or start_codex_review call can pass require_idle while `thread/delete` is in flight. That call spends a paid turn on a thread that is being deleted. A goal tool that leaks its slot on failure locks the scope after `max_live_turns` failed goal runs: every later run is refused with session_busy until the scope is rebuilt. Both regressions would ship with the suite green.
  Smallest fix: Two tests only, with no code change (S2 ownership). (a) Hold `thread/delete` and assert that continue, review, compact and delete on that thread are refused with session_busy, and that the thread is free once the hold is released. (b) Add a raises row and a cancel row for `run_codex_goal` to test_a_failed_or_cancelled_run_releases_its_slot, then probe with another tool.
  Spec IDs: INV-9, INV-27, AC-23, INV-32/INV-33 (the shared slot rule)

R-E2 [Major] [test quality] vidbyte/harnesses/native/codex/skill_functions.py:161 and :220 — The skill read-back's name match and turn match are untested, so the "the skill actually ran" check can silently become "some skill ran in some turn"
  Evidence: Three mutants pass the whole pack. M02 removes the `turn.turn_id == handle.turn_id` filter at :220 (`M02_full: exit=0 :: 192 passed`). M03 drops `entry.get("name") == skill` at :161 (`M03_full: ... 192 passed`). M04 compares the name case-insensitively (`M04_full: ... 192 passed`). The fake's only negative switch, `drop_skill_input` (tests/features/codex_host/codex_host_fakes.py:958), removes every skill entry. No test records a skill entry with a different name or different case, and no test puts the userMessage on a turn other than the handle's.
  Failure: INV-34 exists to confirm that Codex recorded this skill for this turn before the handle returns. The check could be weakened to "any skill item", or matched against an earlier turn's userMessage (a pre-seeded thread, or a turn/start that Codex rewrites). The suite would stay green, and run_codex_skill would return a handle for a run whose skill was never attached, which is the paid, unconfirmed run the check is meant to prevent.
  Smallest fix: Tests only. Add a fake switch such as `rename_skill_input=<name>`, which records the skill entry under another name, and assert that the result is codex.command_not_run plus exactly one interrupt. Add a second test for a case-changed name. Add a third where `thread/turns/list` also returns an earlier turn with a matching skill entry while the handle's own turn has none.
  Spec IDs: INV-34, AC-39, the request's weighted wording "check that the command actually ran"

R-E3 [Minor] [security] [scope-adding] vidbyte/tools/builtins/codex/thread_helpers.py:177 with vidbyte/harnesses/native/codex/wire.py:576-590 and vidbyte/agents/codex/result.py:87-99 — The READ-permission list_codex_turns tool returns raw command output and file diffs of any thread on the account
  Evidence: ListCodexTurnsTool is `permission=ToolPermission.READ` (:177). `turn_page` serializes items with `CodexResultSerializer.items`, and `_item` dumps the full payload of every supported type, excluding only `content` for `reasoning` (result.py:92-97). For commandExecution that includes `aggregatedOutput`; for fileChange it includes the diffs. The tool description says "Any thread the account can see is accepted, including threads this host never ran" (vidbyte/tools/builtins/codex/descriptions.py:33). ListCodexSkillsTool is also READ, and it takes a model-chosen `cwd` (vidbyte/tools/builtins/codex/skill_functions.py:115-130), so the model can list the skill paths of any folder.
  Failure: Under the default policy, which allows READ, a model-driven agent can pull terminal output (environment dumps, printed secrets, test logs) from other projects' Codex threads into its own context. The T-3 control covers reasoning only, not tool output. The spec chose these semantics (any visible thread, READ, no usage check), so this is an exposure to note, not a defect.
  Smallest fix: Follow-up, not this PR. Scope the READ tools to threads this host owns or to `spawn_defaults.thread.cwd`, or drop `aggregatedOutput` from tool-facing turn pages. At minimum, name the exposure in the tool description so a developer can choose a WRITE posture.
  Spec IDs: INV-17, T-3, INV-23, D-25

R-E4 [Minor] [error handling] vidbyte/harnesses/native/codex/skill_functions.py:53, :56, :113, :155, :225-230 — The error text says "was interrupted" even when the interrupt failed, and a turn that failed to stop escapes the scope's cap
  Evidence: `_interrupt` swallows CodexAgentError (`with suppress(CodexAgentError)`, :229). The messages at :53 and :56 still state "was interrupted". On the goal path, openai-codex `cancel_goal_operation` already swallows its own pause and interrupt failures (openai_codex/client.py:572-597), so a failure there cannot be detected at all. The raising tool never reaches `self._scope.own(...)` (vidbyte/tools/builtins/codex/skill_functions.py:103), so the scope does not track a live turn that survived. The codex.command_not_run next step says "...then start the run again" (vidbyte/lib/constants/codex.py:510).
  Failure: If the interrupt fails, the turn keeps running and spending while the caller reads "was interrupted". The turn does not count toward `max_live_turns`, the scope's interrupt tool cannot reach it, and the next step invites a second paid run.
  Smallest fix: Keep EC-29's decision to ignore the failure, but make the claim honest. For example, say "an interrupt was sent", or change the text when `_interrupt` caught an error. Optionally make the next step say "check list_codex_turns for a running turn before starting again".
  Spec IDs: EC-29, INV-22, INV-35

R-E5 [Minor] [error handling] [scope-adding] vidbyte/harnesses/native/codex/wire.py:561-573 — Skill load errors from Codex are dropped, so a broken SKILL.md is reported as "no skill named X"
  Evidence: `skills()` iterates only `entry.skills`. `SkillsListEntry.errors` (`list[SkillErrorInfo{message, path}]` in the generated model) is never read, either by list_codex_skills or by the run_codex_skill resolution in `_skill_path` (skill_functions.py:190-201).
  Failure: A developer whose skill fails to parse gets codex.skill_not_found plus a list of enabled skills, with no hint that Codex tried to load it and why it failed. That turns a one-line fix into a search.
  Smallest fix: When resolution fails and the entry has errors, append "Codex could not load N skill file(s), for example <path>: <message>" to the skill_not_found message, capped like the name list.
  Spec IDs: INV-23, INV-24, EC (skill not found)

R-E6 [Minor] [data/scale] [scope-adding] vidbyte/harnesses/native/codex/host.py:586-594 and vidbyte/tools/builtins/codex/skill_functions.py:127-130 — list_codex_skills and its tool have no output bound, while the error path caps names at 50
  Evidence: The host returns every skill of every folder, and the tool JSON-dumps the full tuple with descriptions and paths. The spec caps the error message at `CODEX_HOST_SKILL_NAMES_IN_ERROR=50` names and the turns tool at a default page of 3 (D-25), but the skills tool has no limit or cursor. The S0 probe saw 284 user skills, which is about 100 KB of tool output in one call.
  Failure: One model call can fill a large part of the context window, and the cost grows with the developer's skill count, not with anything the model asked for.
  Smallest fix: Follow-up. Add an optional `limit` or name filter to the tool (the host API can stay unbounded), or truncate the descriptions in the tool's JSON.
  Spec IDs: INV-23, D-25

R-E7 [Minor] [observability] vidbyte/harnesses/native/codex/skill_functions.py:163 with vidbyte/lib/constants/codex.py:416-420 — The read-back failure says "within 10.0 seconds", but with the defaults it gives up after about 4.5 s of waits
  Evidence: `CODEX_HOST_INPUT_CHECK_ATTEMPTS = 10` and `INTERVAL = 0.5`, so 9 waits add up to 4.5 s, plus the time the reads take. That ends well before `DEADLINE = 10.0`, and the message prints the DEADLINE value.
  Failure: An operator tuning the timeout reads "10.0 seconds" and raises the deadline, which changes nothing. The attempt count is what bounds the wait.
  Smallest fix: Print the elapsed time, or keep the spec text and raise ATTEMPTS to 20 so the deadline is the bound that actually applies. The text is spec-mandated, so either change is a spec-owner call.
  Spec IDs: INV-34, the read-back constants (Q-defaults)

VERIFIED CLAIMS:
1. "The new tests are stable": 76 passed on each of 3 consecutive runs of the five new files (5.52 s, 5.45 s, 5.33 s). HOLDS.
2. "Lint passes and the area gate fails only on the inherited test": `S064 RATCHETED: 4 known finding(s)`, `SDK-LINT: PASS`, then `1 failed, 673 passed, 2 skipped in 51.63s`. The only failure is test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes. HOLDS (the failure is not this PR's, as settled).
3. "S3 did not edit tests": `git diff 33787d9a..c81ba632 -- tests/` is empty. HOLDS.
4. "The skill and thread modules do not import the host or openai-codex at import time": skill_functions does not import host, and importing the codex modules leaves `openai_codex loaded: False`. HOLDS.
5. "Only compact resumes, after the goal check": grep shows `_resume(` only at thread_helpers.py:166 (call) and :271 (def). M06 and M13 are killed. HOLDS.
6. "The read-back is bounded by both attempts and the deadline": skill_functions.py:213-216. M15 and M22 are killed. HOLDS.
7. "thread_compact is a single request with no retry, and delete uses the raw path with overload retries only": checked in the SDK client source and connection.py `raw()` (:203-210). `SPENDING_RAW_METHODS` is unchanged (:89). HOLDS (A-14 is accepted).
8. "The test-plan's INV-27 row kills a leaked slot for all three run tools": PARTIAL. It holds for skill and docs; the goal tool's leak survives (M36, see R-E1).
9. "AC-23 covers both compact and delete holds": PARTIAL. Only compact is held; the delete reservation removal survives (M05, see R-E1).
10. File sizes: thread_helpers.py 279, skill_functions.py 251, host.py 891, tool modules 238 and 211 lines. HOLDS (all within the module size rule).

COMMANDS RUN:
- `git log --oneline -4`; `git status --short`; `git diff --stat c181be6577245e8112d7a781deb814e088b6c1ab...c81ba632`; `git diff --stat c81ba632 HEAD` (pipeline.md only); `git diff 33787d9a..c81ba632 -- tests/` (empty).
- `wc -l` on the five new or changed vidbyte modules.
- `VPY -m pytest -q <5 new test files>` ×3 → `76 passed` each time.
- Lint loop plus area gate → `SDK-LINT: PASS`; `1 failed, 673 passed, 2 skipped in 51.63s`.
- Import-boundary probe → `openai_codex loaded: False`.
- Collection: codex_host pack 192 tests; codex_host plus tests/test_codex_output_contracts.py 238; harness_threads 438.
- Mutation harness (scratchpad s4-engineering/mutate.py plus mutant_plugin.py, a meta-path finder; the worktree is never edited), against the 5 new files, then the full pack for the survivors:
  - M00 no-op → 76 passed (the harness is sound); M01 since `<`→`<=` → killed.
  - Killed: M06, M07, M08, M09, M10, M11, M12, M13, M14, M15, M16, M17, M22, M26.
  - Survived: M02 → `192 passed`; M03 → `192 passed`; M04 → `192 passed`; M05 → `192 passed`, and `328 passed` with the codex output-contract, tools and failure-recovery suites; M36 → `192 passed`.
- Greps: `thread_compact`/`request_with_retry_on_overload` in openai-codex; `cancel_goal_operation` (openai_codex/client.py:572-597); `CodexConnection.interrupt` (connection.py:284-302); `SkillsListEntry` and `CommandExecutionThreadItem` in the generated models; tool permissions in both tool modules.
