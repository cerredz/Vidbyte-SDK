LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — Sixteen of the eighteen fixes hold against their review.md rows and spec r5. Two do not. R-16 turns a user's interrupt of a still-running turn into a silent no-op after any earlier stop failed. R-2's new refusal puts library exception text into a harness error, which §12.4 forbids.

Scope: post-repair re-review, round 1 of 2. It covers fix commits 2f098372..08d498d8 (R-1..R-18), the granted test file `tests/features/codex_host/test_codex_host_review_gaps.py`, and the code around each fix, at bbaa5a8b. The merge fb76e558 (main's 41 commits) is out of scope. Counts: 0 Blocker, 2 Major, 2 Minor.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-4 holds without new chains or cycles.**
  - An AST scan of direct `self.<helper>()` calls in `vidbyte/harnesses/native/codex/*.py` finds 0 same-class chains of depth 2 or more.
  - The one stop is `CodexLiveTurn.stop(connection, reason)`. `turns.py` imports `CodexConnection` only under `TYPE_CHECKING`, so no import cycle forms.
  - The review read-backs reuse `CodexPreflight.require_thread`.
  - Leave this shape alone. Moving `stop` onto `CodexConnection` would create the stop → interrupt → call chain that R-4 removed.
- **The cancellation repairs close their windows, and the new tests fail for the right reason.**
  - R-6, R-7, R-10, R-13 and R-17 are fixed. R-1 is fixed except for the residual the verifier accepted.
  - The 10 new tests pass.
  - The CI-visible R-14 test fails under mutant M3 (the launch tool frees its slots only on success). The second launch then returns `codex.session_busy: This toolset already holds 2 of its 2 live turns…`.
  - R-10's `_land` frees the thread and adopts the late start in one loop callback, with no await in between.
- **R-3 converts each value once, and every conversion succeeds.**
  - `CodexGoalStatus(...)` and `CodexSandboxReadiness(...)` cover every member of openai-codex 0.162.1's `ThreadGoalStatus` (6 members) and `WindowsSandboxReadiness` (3 members).
  - `CODEX_HOST_DEFAULT_APPROVAL_MODE` is `CodexApprovalMode.AUTO_REVIEW`, which equals `"auto_review"`.
  - R-11 leaves no quoted JSON-RPC method literal in the host package or the tools.
- **The contract and the budget are untouched.**
  - The native `__init__` blob hashes to `0374a2c8…942f497a`.
  - `lint/baseline.json`, `pyproject.toml`, `contracts/` and `vidbyte/__init__.py` show 0 diff lines.
  - Counts are identical at 099fac83 and bbaa5a8b: 18 new files, 30 classes, 15 records and 23 Codex enums.
  - R-5 changes comment lines only. 0 of the 729 comment lines the branch adds are wider than 72 columns.
  - In the repair range, the test tree has additions only (330 + 2 + 1 lines, 0 deletions).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [spec conformance — regression from R-16] `vidbyte/harnesses/native/codex/host.py:407` — `interrupt_codex_turn` sends nothing for a turn that is still running once any earlier stop of that turn failed, violating AC-16 and the §9.2 interrupt row
  Evidence:
  - The changed line:
    ```
    if turn.snapshot is not None or turn.stop_sent:
        return
    ```
    `stop_sent` is never reset. It stays True after the stop's request ends, whether that request succeeded or failed.
  - Probe `scratchpad/codex-rereview1/probe_r16_r2.py`, run as a HostTestCase over the fake.
  - Case 1: the user's interrupt fails once, then the user retries.
    ```
    first user interrupt raised: codex.api_error
    turn/interrupt sent after first call: 1
    second user interrupt returned: None
    turn/interrupt sent after retry: 1
    turn status after retry: inProgress
    ```
  - Case 2: the `timeout_seconds` interrupt fails, then the user interrupts.
    ```
    timeout interrupts sent: 1
    user interrupt returned: None
    turn/interrupt sent after user interrupt: 1
    turn status after user interrupt: inProgress
    ```
  - Control run `probe_r16_prefix.py`: the same probe with the pre-R-16 guard (`if turn.snapshot is not None`) restored in memory.
    ```
    turn/interrupt sent after retry: 2
    turn status after retry: interrupted
    turn/interrupt sent after user interrupt: 2
    turn status after user interrupt: interrupted
    ```
  Failure:
  - **The trigger.** A running turn's earlier interrupt failed. That can be the user's own interrupt, which raised `codex.api_error`, or Vidbyte's quiet timeout or cap interrupt (EC-27).
  - **What happens.** Every later `interrupt_codex_turn` returns `None` and sends nothing.
  - **What the caller is told.**
    - `codex.api_error`'s next step says "Retry with backoff", and that retry is a silent no-op.
    - The interrupt tool still answers "Interrupt requested for turn <id>…".
  - **Nothing else can stop the turn.** `over_cap()` is also gated on `not self.stop_sent`, and the timeout fires only once. So the turn keeps spending until Codex ends it or the host closes.
  - **The rules this breaks.**
    - §9.2 sends nothing only "when the turn has already finished".
    - AC-16 requires one `turn/interrupt` for a running turn.
    - EC-25 limits the no-op to a finished turn.
    - D-7 and EC-27 forbid Vidbyte retrying its own stop. They do not cover dropping the caller's request.
  - **Scope of R-16's row.** It asked only that the host not send a second interrupt while a stop "is still in flight". It did not ask to suppress interrupts after the stop ended.
  Smallest fix: skip only while an earlier stop's request is in flight.
  - Give `CodexLiveTurn` a `stop_pending` flag.
  - `stop()` sets it, and so does `interrupt_codex_turn`. Each clears it in a `finally` after `connection.interrupt` returns.
  - `interrupt_codex_turn` returns early on `turn.snapshot is not None or turn.stop_pending`.
  - `stop_sent` keeps its D-7 meaning for `stop()` and `over_cap()`.
  - This adds one attribute and no class.
  - If that is too much for this round, revert to `if turn.snapshot is not None:` (the pre-R-16 line, which matches §9.2) and move R-16 to the follow-ups.
  - Either way, a regression test needs a grant (tests-only). Case 1 above is the test.
  Spec IDs: FR-12, AC-16, EC-25, EC-27, D-7, §9.2 (`interrupt_codex_turn` row), INV-8 ("each funciton shoulllld make sure to handle errors", request.md §D)

R-C2 [Major] [spec conformance — §12.4 rule broken by the R-2 fix] `vidbyte/harnesses/native/codex/wire.py:262` — the unusable-schema refusal puts a library exception's text into the harness error and chains it as the cause, which §12.4, §12.3 row 10 and INV-9 forbid
  Evidence:
  - The changed line:
    ```
    except (PydanticUserError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"{UNUSABLE_SCHEMA_MESSAGE} {exc}") from exc
    ```
  - Probe output, `ProbeR2.test_messages`, through `host.spawn_codex_thread`:
    ```
    [object() value] message="output_schema must be a Pydantic model type or a mapping that serializes to JSON. Unable to serialize unknown type: <class 'object'>"
    [object() value] __cause__=PydanticSerializationError suppress_context=True
    [cyclic mapping] message='output_schema must be a Pydantic model type or a mapping that serializes to JSON. Circular reference detected (id repeated)'
    [cyclic mapping] __cause__=ValueError suppress_context=True
    ```
  Failure:
  - **Which rules.**
    - §12.4, "No exception text in harness errors": a message is never built from `str(exc)`, `repr(exc)` or `f"{exc}"`, and errors are raised `from None`.
    - §12.4 adds that "S017's scan covers `vidbyte/tools/` but not `vidbyte/harnesses/`, so review holds this rule there". Lint therefore cannot catch this.
    - §12.3 row 10: "never `from exc`".
    - INV-9: messages carry "only Codex's own error message, the method, the JSON-RPC code, or an exception's type name".
  - **Python callers.** They get pydantic's own text and a chained pydantic or `TypeError` cause.
  - **The tool path.** Suppose a developer's `spawn_defaults.output_schema` cannot be serialized.
    - Every spawn, continue and launch tool call then returns `configuration.invalid_argument: output_schema must be … <pydantic text> Next step: …`, because `_CodexHostTool._run` forwards `exc.message`.
    - That is the exception disclosure S017 bans in tools, done one layer lower.
  Smallest fix:
  - Replace the line with `raise ConfigurationError(f"{UNUSABLE_SCHEMA_MESSAGE} Got {type(exc).__name__}.") from None`. That is the type name only, as INV-9 allows.
  - `CodexHostOutputSchemaRefusalTests` asserts only `"output_schema" in str(error)`, so it passes unchanged.
  Spec IDs: INV-9, INV-8, EC-82, §12.3 row 10, §12.4 ("No exception text in harness errors")

R-C3 [Minor] [model-facing text fidelity — R-15 left half done] `vidbyte/tools/builtins/codex/descriptions.py:60-61` — `TITLE_DESCRIPTION` and `INSTRUCTIONS_DESCRIPTION` still imply that other review targets ignore the field, but `CodexReviewTarget` refuses it
  Evidence:
  - The current text:
    - `TITLE_DESCRIPTION`: "It is used only when the review target is one commit."
    - `INSTRUCTIONS_DESCRIPTION`: "They are used only when the review target is custom."
  - Probe: `CodexReviewTarget(kind=BASE_BRANCH, branch="main", title="t")` raises `ConfigurationError Codex review target baseBranch needs branch; got empty [] and unused ['title'].`
  - `CodexReviewTarget(kind=COMMIT, sha="abc", instructions="i")` raises `… unused ['instructions'].`
  Failure:
  - A model that reads "used only when" sends a title with a base-branch review and gets `configuration.invalid_argument`.
  - This is R-15's own defect, which R-15 fixed for `BRANCH_DESCRIPTION` and `SHA_DESCRIPTION` only.
  - §9.1 says "Fields the kind does not use must stay empty."
  - A human reviewer would write: "you fixed two of the four target-field descriptions."
  Smallest fix: replace the third sentence of each with "The other review targets refuse it." (or "refuse them."). Both stay at 4 sentences (NFR-7, S025).
  Spec IDs: §9.1 `CodexReviewTarget` row, §9.2 tool 15, NFR-7, INV-34

R-C4 [Minor] [spec–code drift — R-11 not recorded in the spec] `vidbyte/lib/constants/codex.py:441-455` — the 11 method-name constants R-11 added are not in the §9.3 constants table, which row 4 treats as the full list
  Evidence:
  - `git show 528e5ef6 -- vidbyte/lib/constants/codex.py` adds these 11 constants, appended to `__all__`:
    - `CODEX_INITIALIZE_METHOD`, `CODEX_ACCOUNT_READ_METHOD`;
    - `CODEX_THREAD_RESUME_METHOD`, `CODEX_THREAD_FORK_METHOD`, `CODEX_THREAD_NAME_SET_METHOD`, `CODEX_THREAD_LIST_METHOD`, `CODEX_THREAD_READ_METHOD`;
    - `CODEX_TURN_START_METHOD`, `CODEX_TURN_STEER_METHOD`, `CODEX_TURN_INTERRUPT_METHOD`;
    - `CODEX_GOAL_CANCEL_CALL`.
  - spec.md:1039 lists only the five raw-path method names.
  - §12.3 row 4(b) says "add every §9.3 constant".
  Failure:
  - review.md R-11 authorized the constants, so the code is correct.
  - The spec is now an incomplete record of the constants module. The next spec reader or implementer will not know these names exist, and could add duplicates.
  Smallest fix (spec-change, no code): add one §9.3 row naming the 11 constants and their values, citing R-11.
  Spec IDs: §9.3, §12.3 row 4

VERIFIED CLAIMS
1. R-4, "16 chains → 0": **holds** for direct calls.
   - My AST scan (`chains.py`) prints no `CHAIN` line for `vidbyte/harnesses/native/codex`.
   - Seven callback-mediated chains remain, for example `start_codex_review ~> _adopt_late_review -> _accept_review`. In each, another class or the loop invokes the callback, so R-4's metric does not count it.
   - The tools layer has `ContinueCodexThreadTool: execute -> _perform -> _continue_defaults`. It predates the repair and is outside R-4's row, so it is not raised here.
2. R-5, 0 comment lines over 72 columns: **holds**.
   - Against merge base 8387d666, `git diff … | grep -E '^\+\s*#' | awk 'length($0) > 73' | wc -l` gives 0 of 729.
   - The non-comment diff of 08d498d8 is empty.
   - Its `vidbyte/agents/codex/tools.py` hunks rewrap only comments the branch added in its row-7 extraction.
3. R-9, no A002 finding under the new paths: **holds**. `lint/run.py --rule A002 --all --format json` reports 579 against a baseline of 703. Filtered to branch paths, it lists 4 hits, all in main's other classes in `lib/errors/base.py` (lines 161, 251, 266, 275).
4. R-11, no inline method literal: **holds**. Grep for `"x/y"` literals in `harnesses/native/codex` and `tools/builtins/codex` finds none. `GOAL_START_CALL` is still a single definition in errors.py.
5. R-3, conversions at the wire edge: **holds**.
   - Both enum conversions are total over the generated enums.
   - `CODEX_HOST_DEFAULT_APPROVAL_MODE == "auto_review"` is True, so the S2 constants test is untouched.
6. R-10, "busy while in flight; freed and adopted in one loop callback": **holds**.
   - By reading: `_hand_over` marks the thread only when `future.cancel()` is False, and `_land` discards the thread, then calls `on_late`.
   - Both `CodexHostInFlightStartTests` pass.
7. R-1, the except branch: **holds**, and it brings no new hazard (by reading, not run).
   - It calls `turn.watch` even when close or death came first.
   - openai-codex's `unregister_turn` closes the subscription and leaves it in its map, so the new watcher's `next()` fails and the watcher exits.
   - The accepted residual is unchanged.
8. R-16, "pack green": **holds**, but the behaviour regressed. See R-C1, reproduced against both the current guard and the pre-R-16 guard.
9. R-2, "refused before any request": **holds**, because the test checks `methods()[before:] == []`. The message violates §12.4; see R-C2.
10. The budget, "repair added none": **holds**.
    - `budget.py` gives `099fac83 classes 30 records 15 codex enums total 23 functions 218` and `bbaa5a8b classes 30 records 15 codex enums total 23 functions 221`.
    - It lists 18 added files under `vidbyte/` for the branch, none of them added in the repair range.
    - Every `vidbyte/` file the repair touched is a §12.3 row.
11. Shared file and boundaries: **holds**.
    - The native blob hashes to `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
    - `git diff origin/main...bbaa5a8b -- lint/baseline.json` has 0 lines, and so does the same diff for `pyproject.toml contracts vidbyte/__init__.py`.
    - No test outside `tests/features/codex_host/` changed, and the pack has no deleted lines.
12. AC-1, the §4 snippet: **holds**. `CodexHostSnippetTests` passes and asserts exactly `["True", "completed The readme describes the SDK.", "15 check_codex_ready"]`.
13. The R-14 test fails for the right reason: **holds**. Under in-memory mutant M3 it reports `M3 failures: 2`, both `codex.session_busy` on the second launch.
14. R-12 and D-36 texts: **holds**.
    - `OUTPUT_SCHEMA_DESCRIPTION` has 5 sentences that say the answer is "checked only for being valid JSON and is not compared with the schema".
    - The `CodexSpawnRequest` docstring adds the Pydantic model check and the EC-82 refusal.

COMMANDS RUN
- The pack: `PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q …` → `111 passed in 7.29s`
- The gaps file alone → `10 passed in 1.52s`. The AC-1 class `CodexHostSnippetTests` → `1 passed in 1.05s`
- Lint: `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` → `S061 IMPROVED 6 -> 5 …` / `SDK-LINT: PASS`
- A002 JSON: `lint/run.py --rule A002 --all --format json` → `found 579, baseline 703, verdict IMPROVED`, with 0 findings under the branch's new paths
- The R-16 and R-2 probe: `PYTHONPATH="$W;$S" $PY -P -m unittest probe_r16_r2` → `Ran 3 tests … OK`, printing the lines quoted in R-C1 and R-C2
- The pre-R-16 control: `$PY -P $S/probe_r16_prefix.py` → `turn/interrupt sent after retry: 2` / `turn status after retry: interrupted`
- The review-target probe (`CodexReviewTarget` with `title` or `instructions` on another kind) → `ConfigurationError … unused ['title']` and `… unused ['instructions']`
- The chain scan: `$PY -I $S/chains.py $W/vidbyte/harnesses/native/codex` → no `CHAIN` lines and 7 `CALLBACK-CHAIN` lines. At 099fac83 the same scan counted 39 lines in all.
- The budget script: `$PY -I $S/budget.py <rev> $W` → the counts quoted in claim 10
- Enum totality: `$PY -P -c "…ThreadGoalStatus…WindowsSandboxReadiness…"` → `missing in CodexGoalStatus: []` and `missing in CodexSandboxReadiness: []`
- Comment width: `git diff 8387d666 bbaa5a8b -- vidbyte | grep -E '^\+\s*#' | awk 'length($0) > 73' | wc -l` → `0`
- The native blob: `$PY -I -c "…git cat-file -p bbaa5a8b:vidbyte/harnesses/native/__init__.py…"` → `0374a2c8…942f497a`
- The M3 mutant: `$PY -P $S/mutant_r14.py $W` → `FAILED (failures=2)` / `M3 failures: 2 errors: 0`
- The worktree after all runs: `git status --short` prints nothing (clean)

$S is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/codex-rereview1`. Every mutant and pre-fix body was patched in memory; nothing was written to the worktree except this report.
