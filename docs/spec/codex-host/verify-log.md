# Verification log: CodexHost: small atomic Codex functions with one agent tool per function

Gate set (from context/code-map.md §1): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` (lint, compileall, the three check scripts, pytest; must end `CI passed.`), then `python scripts/run_ci.py --stage package` with no `PYTHONPATH`, `python lint/run.py` (`SDK-LINT: PASS`), `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1), `python scripts/generate-sdk-public-api.py --check`, the feature pack `tests/features/codex_host` with and without openai-codex, and the remote `ci.yml` and `static-policy.yml` runs, dispatched by hand.

## Iteration 1 — 2026-10-14 02:10 — agent report: reports/S5-repair-1.md

**Defects in.** `review.md` has 18 open confirmed findings. The Blockers are R-1 (a review cancelled during its D-23 read-back is never watched or interrupted), R-2 (an unusable `output_schema` fails only after `thread/start`), R-3 (goal status, sandbox readiness and the approval default are typed `str`), R-4 (host helpers chain 2 to 3 calls deep, and header line 5 is false) and R-5 (176 added comment lines are wider than 72 columns). The Majors are R-6 (a cancelled launch leaves its started turns running), R-7 (a cancelled close leaks the client and the executor), R-8 (two argument checks are reshaped so C002 cannot see them), R-9 (seven new functions lack `# @intent`), R-10 (continue and review release the thread while their start is in flight), R-11 (16 inline method names), R-12 (the texts promise a schema check on a mapping), R-13 (mutants M1 and M2 survive) and R-14 (mutant M3 survives). The trivial Minors are R-15 to R-18. Failing gates in: none. At `bbe9672f` the pack passes 101 of 101, lint gives `SDK-LINT: PASS`, and remote CI on `099fac83` is green.

**Hypotheses and attempts.**
- R-1: wrap the read-back in `try/except BaseException`, then watch, stop and re-raise. This worked the first time. After R-4, the same handler calls `turn.watch(connection, …)` and `turn.stop(connection, None)`.
- R-2, first idea: call `turn_start` itself as the pre-check. Rejected, because it would also run the approval and sandbox translation and depend on a thread id. What shipped is `to_jsonable_python` over `CodexVidbyteTranslator.output_schema(...)`, the same value `turn_start` sends. A probe sorted the failure types. A cyclic mapping raises `ValueError`. A lock raises `TypeError` from the formatter's copy. A model with a callable field raises `PydanticInvalidForJsonSchema`, which is a `PydanticUserError` and therefore a `RuntimeError`, so it is caught by name. A `set` is serialized as a list, as the wire also does. A non-model type gets the formatter's own `ConfigurationError`, which already names `output_schema`.
- R-4: the finding's text proposes moving `_stop` onto `CodexConnection`. Rejected, because `stop → interrupt → call` would form a new same-class chain inside the connection. `stop` went onto `CodexLiveTurn`, where it is a leaf that calls out. The review registration was split into `_track_review`, so `_adopt_late_review` can register synchronously, which R-10 relies on. An AST scan of same-class call chains found 16 before and 0 after.
- R-10: the finding offered to keep the registry reservation and release it from `_adopt_late_turn`, `_adopt_late_review` and `_post_late`. Rejected: that adds three release sites to the registry. What shipped is the connection's own in-flight set, freed in one loop callback (`_land`) right before the late start is adopted. A withdrawn start never marks its thread.
- R-12: the EC-83/EC-32 pin passes on the shipped code, because R-12 is a text fix. Its red comes from a mutant that also checks the mapping's required keys, the check the old description promised.
- R-13 and R-14 are tests-only, so their reds come from the review's mutants M1, M2 and M3. Each mutant was rebuilt in memory and run in its own subprocess.
- R-5: a first count with `git diff origin/main -- vidbyte` (two dots, against the working tree) showed 4 leftover lines. They were main's newer lines, not the branch's. The recount against `git merge-base origin/main HEAD` gives 0.
- R-9: the A002 JSON listed 7 findings in branch files, plus 4 in `lib/errors/base.py`. The base.py `__init__`s are main's, and the branch changed only lines 143 and 151 there. A002 went from 607 to 600 against a baseline of 703.

**Red runs of the new tests** (`tests/features/codex_host/test_codex_host_review_gaps.py`, via `python -m unittest <class>`, or `pytest` for R-1):

- R-1, `CodexHostReviewReadBackCancellationTests`, pre-fix `bbe9672f`:
  ```
  AssertionError: timed out waiting for 1 x turn/interrupt; requests so far: ['initialize', 'account/read', 'account/rateLimits/read', 'windowsSandbox/readiness', 'thread/read', 'review/start', 'thread/read']
  1 failed in 11.48s
  ```
- R-2, `CodexHostOutputSchemaRefusalTests`, pre-fix `2f098372`:
  ```
  ERROR (schema='a mapping that is not JSON', operation='spawn'|'continue'|'launch'): pydantic_core._pydantic_core.PydanticSerializationError: Unable to serialize unknown type: <class 'object'>
  FAIL (schema='a dataclass type', operation='spawn'): AssertionError: Lists differ: ['account/read', 'account/rateLimits/read'[40 chars]art'] != []
  FAIL (schema='a dataclass type', operation='continue'): AssertionError: Lists differ: ['account/read', 'account/rateLimits/read'[56 chars]ume'] != []
  FAIL (schema='a dataclass type', operation='launch'): AssertionError: Lists differ: ['account/read', 'account/rateLimits/read'[40 chars]art'] != []
  Ran 1 test in 0.423s  FAILED (failures=3, errors=3)
  ```
- R-6, `CodexHostLaunchCancellationTests`, pre-fix `846ce849`:
  ```
  AssertionError: timed out waiting for 1 x turn/interrupt; requests so far: ['initialize', 'account/read', 'account/rateLimits/read', 'windowsSandbox/readiness', 'thread/start', 'turn/start', 'thread/start']
  Ran 1 test in 10.376s  FAILED (failures=1)
  ```
- R-7, `CodexHostCloseCancellationTests`, pre-fix `4d597f91`:
  ```
  AssertionError: timed out waiting for the client to close; requests so far: ['initialize', 'account/read', 'account/rateLimits/read', 'windowsSandbox/readiness', 'thread/start', 'turn/start', 'turn/interrupt']
  Ran 1 test in 10.398s  FAILED (failures=1)
  ```
- R-10, `CodexHostInFlightStartTests`, pre-fix `f2e9db7e`:
  ```
  FAIL: test_a_continue_whose_start_is_in_flight_keeps_the_thread_busy_until_it_lands
      self.assertEqual(self.count("thread/resume"), 1)
  AssertionError: 2 != 1
  Ran 2 tests in 10.402s  FAILED (failures=1)
  ```
  The same class at `874bd5a3` under a mutant that posts nothing for a failed in-flight start, as the pre-fix `_post_late` did:
  ```
  FAIL: test_a_failed_in_flight_start_frees_its_thread_when_it_returns
  vidbyte.lib.errors.base.CodexAgentError: The thread already has a running turn on this host. Thread: thr-1.
  AssertionError: the thread stayed busy after its failed start returned
  Ran 2 tests in 10.122s  FAILED (failures=1)
  ```
- R-12, `CodexHostMappingSchemaTests`, under a mutant whose local check also compares a mapping answer's required keys:
  ```
  FAIL: ... (answer='valid JSON that misses the schema')
  AssertionError: CodexProblem(code=<FailureCode.CODEX_SCHEMA_VIOLATION: 'codex.schema_violation'>, message="Codex's final answer is not JSON that matches output_schema.", ...) is not None
  Ran 1 test in 0.377s  FAILED (failures=1)
  ```
- R-13, `CodexHostLateStopTests`, under M1 (`_adopt_late_goal` never stops the run):
  ```
  FAIL: test_a_goal_spawn_cancelled_during_its_goal_start_is_cancelled_once_without_a_problem
  AssertionError: timed out waiting for the late goal run's cancel; requests so far: ['initialize', 'account/read', 'account/rateLimits/read', 'windowsSandbox/readiness', 'thread/start', 'thread/read', 'thread/goal/clear', 'thread/goal/set']
  Ran 2 tests in 10.390s  FAILED (failures=1)
  ```
  The same class under M2 (a late turn is stopped with `CODEX_TURN_TIMED_OUT`):
  ```
  FAIL: test_a_late_turn_is_interrupted_once_without_a_stop_reason
  AssertionError: CodexProblem(code=<FailureCode.CODEX_TURN_TIMED_OUT: 'codex.turn_timed_out'>, message='Vidbyte interrupted the turn because its timeout_seconds elapsed.', ...) is not None
  Ran 2 tests in 0.396s  FAILED (failures=1)
  ```
- R-14, `CodexHostLaunchToolSlotTests` (CI-visible), under M3 (the launch tool releases its slots only on success):
  ```
  FAIL: ... (launch='failed')
  AssertionError: <ToolStatus.ERROR: 'error'> != <ToolStatus.SUCCESS: 'success'> : codex.session_busy: This toolset already holds 2 of its 2 live turns, so 2 more cannot start. ...
  FAIL: ... (launch='cancelled')
  AssertionError: <ToolStatus.ERROR: 'error'> != <ToolStatus.SUCCESS: 'success'> : codex.session_busy: This toolset already holds 2 of its 2 live turns, so 2 more cannot start. ...
  Ran 1 test in 0.012s  FAILED (failures=2)
  ```

**Changes.**

| Commit | Subject |
|---|---|
| `2f098372` | fix(codex-host): watch and stop a review cancelled during its read-back [R-1] |
| `6856645b` | fix(codex-host): refuse an unusable output_schema before any request [R-2] |
| `8f6975e8` | fix(codex-host): type goal status, sandbox readiness and approval default as enums [R-3] |
| `846ce849` | fix(codex-host): keep CodexHost helpers one call deep [R-4] |
| `4d597f91` | fix(codex-host): stop the turns a cancelled launch already started [R-6] |
| `52e9e313` | fix(codex-host): close the client even when close is cancelled [R-7] |
| `f2e9db7e` | fix(codex-host): check wait timeout and launch limit with the record guards [R-8] |
| `874bd5a3` | fix(codex-host): keep a thread busy while its handed-over start is in flight [R-10] |
| `528e5ef6` | fix(codex-host): name every app-server method through a constant [R-11] |
| `4a9ecc49` | fix(codex-host): say a mapping output_schema is only parsed as JSON [R-12] |
| `d894d87a` | fix(codex-host): test that late goal runs and late turns stop without a problem [R-13] |
| `168282f4` | fix(codex-host): test that the launch tool frees its slots on failure and cancel [R-14] |
| `1169ad68` | fix(codex-host): say the other review targets refuse branch and sha [R-15] |
| `7d4c21fa` | fix(codex-host): send no second interrupt to a turn already stopping [R-16] |
| `9dee1619` | fix(codex-host): release a failed goal start's stream even when cancelled twice [R-17] |
| `4e222e3c` | fix(codex-host): name record arguments and split a chained conditional [R-18] |
| `fad8c55f` | fix(codex-host): add the missing intent markers to seven new functions [R-9] |
| `08d498d8` | fix(codex-host): wrap the branch's comments at 72 columns [R-5] |
| `1ee06bb5`, `6a933f4e`, `6b6199bb`, `cee85d37`, `d78483d8` | docs(spec): review.md status checkpoints |
| `fb76e558` | Merge remote-tracking branch 'origin/main' into feat/codex-host (41 commits, no conflicts) |

`fb76e558` was pushed to `origin/feat/codex-host`, after `099fac83`. This log and the report are committed after it.

**Gate matrix out.**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$W python -P -m pytest tests/features/codex_host/test_codex_host_review_gaps.py -q` | pass | `10 passed in 1.42s` |
| Feature pack | `PYTHONPATH=$W python -P -m pytest tests/features/codex_host -q` | pass | `111 passed in 7.32s` |
| Feature pack, CI view | same, with `sys.modules['openai_codex'] = None` | pass | `36 passed, 75 skipped in 1.80s` |
| run_ci source | `PYTHONPATH=$W python scripts/run_ci.py --stage source` | pass | `4117 passed, 22 skipped in 40.35s` / `CI passed.` |
| run_ci package | `python scripts/run_ci.py --stage package` (no `PYTHONPATH`) | pass | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Lint | `PYTHONPATH=$W python lint/run.py` | pass | `SDK-LINT: PASS` |
| Semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | pass | `Ran 1 rule on 911 files: 0 findings.` |
| Public API | `PYTHONPATH=$W python scripts/generate-sdk-public-api.py --check` | pass | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| Remote CI | `gh workflow run ci.yml --ref feat/codex-host` → run 38519843721 on `fb76e558` | success | Source 3.11: `4045 passed, 94 skipped in 41.35s` / `CI passed.`; Source 3.12: `4045 passed, 94 skipped, 19 warnings in 43.31s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Remote static policy | `gh workflow run static-policy.yml --ref feat/codex-host` → run 38519846158 on `fb76e558` | success | `Ran 1 rule on 911 files: 0 findings.` |

Other checks on `fb76e558`:
- The shared-file blob SHA-256 is `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- `git diff --numstat 1d110811..HEAD -- tests/features/codex_host` gives `1 0 FEATURE.md`, `2 0 README.md` and `330 0 test_codex_host_review_gaps.py`.
- Same-class call chains of depth 2 or more in `vidbyte/harnesses/native/codex/*.py`: 0.
- `lint/run.py --rule A002 --all` lists nothing under the branch's new paths, and `--rule C002` gives 9 against a baseline of 9.
- Branch-added comment lines over 72 columns: 0.

**Still open.**
- No confirmed finding is open. R-19 to R-25 are follow-ups and are out of scope for this iteration. R-25 is scope-adding (Q-10).
- R-1 residual, accepted by the verifier: a review that finished before its registration, and whose caller is also cancelled during the read-back, stays RUNNING until close.

## Iteration 2 — 2026-10-14 03:10 — agent report: reports/S5-repair-2.md

**Defects in.** The S5 re-review, round 1, and its findings verifier (reports/S5-findings-verifier-r1.md) confirmed two regressions from iteration 1's own fixes, and two Minors. R-26 (Major): R-2's refusal at wire.py:262 put pydantic's exception text into the `ConfigurationError` and raised it `from exc` (INV-9, §12.3 row 10, §12.4). R-27 (Major): R-16's guard at host.py:407 made every user interrupt a silent no-op once any earlier stop of the turn had failed (§9.2, AC-16, EC-25). R-28 (Minor, trivial): the title and instructions descriptions said "used only when". R-29 (Minor, spec text) was already fixed by spec r6 at `130dd828`. Failing gates in: none. At `bbaa5a8b` every local gate and both remote runs were green.

**Hypotheses and attempts.**
- R-26, as the verifier gave it: end the message with `Got {type(exc).__name__}.` and raise `from None`. This worked the first time. The new test reads the library's own text by running `to_jsonable_python` on the same schema, then asserts that text is in no part of the error chain and not in the spawn tool's result, and that `__cause__` is None. Under a mutant that raises `from None` but keeps `{exc}`, the text assertion still fails, so it is not vacuous.
- R-26, found while writing its test: the first draft of the cyclic case put the cycle under `properties`. It raised `RecursionError`, not `ValueError`. `OutputSchemaFormatter.annotate` walks `properties`, `items` and the other schema keywords, so such a cycle never ends. A cycle at a key it skips (`schema["self"]`) reaches `to_jsonable_python` and fails as `ValueError`, which is the case iteration 1 probed. A probe (`scratchpad/codex-repair2/probe_nested_cycle.py`) showed the `RecursionError` escaping spawn, and the spawn tool raising it, which breaks INV-8, INV-10 and EC-82. A 5000-deep schema without a cycle does the same. This was not handed in as a finding. It is the same refusal, the fix is one name in the same `except`, and the next review is the last one, so it is fixed in its own commit, `736d4a58`. Three options were weighed. Catching `Exception` was rejected, because it would also catch the formatter's own `ConfigurationError` for a non-model type and rewrite its message. Detecting cycles before the formatter was rejected, because it adds logic beside a shared helper that this PR must not change (NG-5). What shipped adds `RecursionError` to the caught types.
- R-27, the verifier's recommended shape. `CodexLiveTurn` gets `stop_pending`. One async method, `send_stop(connection, operation, *, quiet=False)`, awaits `connection.interrupt` and clears the mark in `finally`. `stop()` marks the stop pending, then spawns `send_stop`. The user path returns early only on `snapshot is not None or stop_pending`, then sets `stop_sent` and `stop_pending` and awaits `send_stop`. This worked the first time. The verifier's `probe_rc1` gives exactly its `pending` output (A, B and C send 2; D and E send 1; F as AC-16).
- The verifier's smaller alternative (revert host.py:407 to `if turn.snapshot is not None:`) was not used, because it re-opens R-16. The new in-flight test fails under it (`2 != 1`), so a later agent cannot take that route without a red test.
- `stop()` must set `stop_pending` before it spawns `send_stop`, and not inside `send_stop`. A spawned task's first step runs a loop iteration later, and a user call scheduled in between would pass the guard.
- R-28, two string edits. `lint/run.py --rule S025` passes, and `CodexReviewTarget` still refuses `title` on a base-branch target and `instructions` on uncommitted-changes and commit targets.

**Red runs of the new tests** (`tests/features/codex_host/test_codex_host_review_gaps.py`, via `python -m unittest <class>`; mutants via `scratchpad/codex-repair2/mutant_run.py`, compiled in memory, nothing on disk changed):

- R-26, `CodexHostSchemaRefusalTextTests.test_an_unusable_mapping_schema_is_refused_without_the_library_text_or_its_cause`, against the code at `130dd828` (equal to `bbaa5a8b` under `vidbyte/`):
  ```
  FAIL: ... (schema='a mapping with an object value')
  AssertionError: PydanticSerializationError(Unable to serialize unknown type: <class 'object'>) is not None
  FAIL: ... (schema='a cyclic mapping')
  AssertionError: ValueError('Circular reference detected (id repeated)') is not None
  Ran 1 test in 0.337s  FAILED (failures=2)
  ```
  The same test under the `text_kept` mutant (`from None`, but the `{exc}` text kept):
  ```
  AssertionError: "Unable to serialize unknown type: <class 'object'>" unexpectedly found in "output_schema must be a Pydantic model type or a mapping that serializes to JSON. Unable to serialize unknown type: <class 'object'>"
  AssertionError: 'Circular reference detected (id repeated)' unexpectedly found in 'output_schema must be a Pydantic model type or a mapping that serializes to JSON. Circular reference detected (id repeated)'
  Ran 1 test in 0.018s  FAILED (failures=2)
  ```
- R-26 recursion, `CodexHostSchemaRefusalTextTests.test_a_schema_with_a_cycle_under_a_schema_keyword_is_refused_before_any_request`, with `wire.py` from `bbaa5a8b` copied in and then restored. The whole class ran: the 2 failures are the R-26 subtests above, and the 2 errors are this method's two subtests.
  ```
  ERROR: test_a_schema_with_a_cycle_under_a_schema_keyword_is_refused_before_any_request (schema='a cycle under items')
  RecursionError: maximum recursion depth exceeded
  Ran 2 tests in 0.382s  FAILED (failures=2, errors=2)
  ```
  Under the `no_recursion` mutant, which is the state at `30109e89`:
  ```
  ERROR: ... (schema='a cycle under properties')
  RecursionError: maximum recursion depth exceeded
  ERROR: ... (schema='a cycle under items')
  RecursionError: maximum recursion depth exceeded
  Ran 2 tests in 0.056s  FAILED (errors=2)
  ```
- R-27, `CodexHostInterruptAfterFailedStopTests`, against the code at `130dd828`:
  ```
  FAIL: test_a_user_interrupt_after_a_failed_timeout_stop_is_sent_and_the_timeout_label_stays
  AssertionError: 1 != 2
  FAIL: test_a_user_interrupt_that_failed_is_sent_again_when_retried
  AssertionError: 1 != 2
  Ran 3 tests in 0.826s  FAILED (failures=2)
  ```
  The third test, `test_a_user_interrupt_while_the_timeout_stop_is_in_flight_sends_nothing_more`, pins R-16. It passes at `bbaa5a8b`, because R-16's guard is there. It fails under the `revert_guard` mutant, the verifier's smaller alternative:
  ```
  FAIL: test_a_user_interrupt_while_the_timeout_stop_is_in_flight_sends_nothing_more
  AssertionError: 2 != 1
  Ran 3 tests in 0.821s  FAILED (failures=1)
  ```
  Under the `pending_sticks` mutant (`send_stop` never clears its mark), A and B fail with `1 != 2`.
- The gaps file passed 12 runs in a row (`15 passed in 1.88s` to `1.99s`).

**Changes.**

| Commit | Subject |
|---|---|
| `30109e89` | fix(codex-host): refuse an unusable output_schema by type name only [R-26] |
| `736d4a58` | fix(codex-host): refuse an output_schema whose walk never ends [R-26] |
| `ad363725` | fix(codex-host): skip a user interrupt only while a stop is in flight [R-27] |
| `3d26abfe` | fix(codex-host): say the other review targets refuse title and instructions [R-28] |
| `1461ddf4` | docs(codex-host): list the R-26 and R-27 tests in the pack's README and FEATURE |
| `77c92838` | docs(spec): mark codex-host R-26..R-29 fixed in review.md |

`77c92838` was pushed to `origin/feat/codex-host`, after `bbaa5a8b`, together with the four docs commits from `fbe64628` to `130dd828`. `origin/main` is still `8387d666`, so no merge was needed (`git rev-list --count HEAD..origin/main` printed `0`). This log and the report are committed after it.

**Gate matrix out** (local runs on `1461ddf4`, which has the same code and tests as `77c92838`):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$W python -P -m pytest tests/features/codex_host/test_codex_host_review_gaps.py -q` | pass | `15 passed in 1.91s` |
| Feature pack | `PYTHONPATH=$W python -P -m pytest tests/features/codex_host -q` | pass | `116 passed in 7.39s` |
| Feature pack, CI view | same, with `sys.modules['openai_codex'] = None` | pass | `36 passed, 80 skipped in 1.69s` |
| run_ci source | `PYTHONPATH=$W python scripts/run_ci.py --stage source` | pass | `SDK-LINT: PASS` … `4122 passed, 22 skipped in 38.59s` / `CI passed.` |
| run_ci package | `python scripts/run_ci.py --stage package` (no `PYTHONPATH`) | pass | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Lint | `PYTHONPATH=$W python lint/run.py` | pass | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| Semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | pass | `Ran 1 rule on 911 files: 0 findings.` |
| Public API | `PYTHONPATH=$W python scripts/generate-sdk-public-api.py --check` | pass | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| Remote CI | `gh workflow run ci.yml --ref feat/codex-host` → run 38526282824 on `77c92838` | success | Source 3.11: `4045 passed, 99 skipped in 43.96s` / `CI passed.`; Source 3.12: `4045 passed, 99 skipped, 19 warnings in 42.92s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Remote static policy | `gh workflow run static-policy.yml --ref feat/codex-host` → run 38526285681 on `77c92838` | success | `Ran 1 rule on 911 files: 0 findings.` |

Other checks on `1461ddf4`:
- The shared-file blob SHA-256 is `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- `git diff --numstat 1d110811..HEAD -- tests/features/codex_host` gives `5 0 FEATURE.md`, `3 0 README.md` and `440 0 test_codex_host_review_gaps.py`. This iteration changed no other test file.
- Same-class call chains of depth 2 or more in `vidbyte/harnesses/native/codex/*.py`: 0 (`scratchpad/codex-repair2/chains.py`). `stop → send_stop → connection.interrupt` is one level, because `interrupt` is another class's method.
- `lint/run.py --rule A002 --all` lists nothing under the branch's paths. C002 is 9 of 9, C011 is 2 of 2, A001 is 643 of 643 and S054 is 3 of 3.
- Branch-added comment lines over 72 columns: 0 of 740.

**Still open.**
- No confirmed finding is open. R-19 to R-25 are follow-ups and were not handed in. R-24 (mutant M5) still survives, because `turn.stop_sent = True` stays on the user path and no new test crosses a cap after a user interrupt.
- R-27 residual, which the verifier considered and did not raise: if the caller of a user interrupt is cancelled while its request is already running on a worker, `finally` clears `stop_pending` before the request ends, so an immediate second call can send a second interrupt. That is the pre-R-16 behaviour, in a narrower window. Probe `scratchpad/codex-repair2/probe_cancelled_interrupt.py`: `turn/interrupt count after retry while first still held: 2` / `final: interrupted problem=None`.
- R-1 residual, accepted in S4: a review that finished before its registration, and whose caller is also cancelled during the read-back, stays RUNNING until close.
