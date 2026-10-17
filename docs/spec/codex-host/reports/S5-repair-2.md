# S5 · Repair report, iteration 2 — codex-host

Stage: S5 repair, iteration 2 of 8 · Start HEAD `130dd828` · Code HEAD `77c92838` (pushed), with this report and `verify-log.md` committed on top · Branch `feat/codex-host` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 (draft; title and body untouched) · Inputs: `review.md` rows R-26 to R-29, spec r6 (`130dd828`), reports/S5-findings-verifier-r1.md.

Environment for every command below:

```
W=C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host
PY=C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python.exe   # Python 3.11, openai-codex 0.162.1
R=C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/codex-repair2
```

No real `codex` binary or app-server was started. Every host test and probe runs over the in-memory fake at the section 13 seam.

## 1. Gate matrix

Local runs are on `1461ddf4`, which has the same code and tests as the pushed `77c92838`; `77c92838` adds only the `review.md` statuses.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host/test_codex_host_review_gaps.py -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` | PASS | `15 passed in 1.91s` |
| Feature pack | same, over `tests/features/codex_host` | PASS | `116 passed in 7.39s` |
| Feature pack, CI view | same, with `sys.modules['openai_codex'] = None` | PASS | `36 passed, 80 skipped in 1.69s` |
| run_ci source | `PYTHONPATH=$W $PY scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` … `====================== 4122 passed, 22 skipped in 38.59s ======================` / `CI passed.` |
| run_ci package | `$PY scripts/run_ci.py --stage package` (no `PYTHONPATH`) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Lint | `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| Semgrep | `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS (exit 0) | `Ran 1 rule on 911 files: 0 findings.` |
| Public API | `PYTHONPATH=$W $PY scripts/generate-sdk-public-api.py --check` | PASS (exit 0) | `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).` |
| Remote CI | `gh workflow run ci.yml --ref feat/codex-host -R cerredz/Vidbyte-SDK` → run 38526282824 on `77c92838` | success (3/3 jobs) | Source 3.11: `4045 passed, 99 skipped in 43.96s` / `CI passed.`; Source 3.12: `4045 passed, 99 skipped, 19 warnings in 42.92s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Remote static policy | `gh workflow run static-policy.yml --ref feat/codex-host -R cerredz/Vidbyte-SDK` → run 38526285681 on `77c92838` | success (1/1 job) | `Ran 1 rule on 911 files: 0 findings.` |

The 5 new tests account for the moves from 4117 to 4122 passed locally, from 111 to 116 in the pack, and from 94 to 99 skipped remotely (CI installs only `.[dev]`, so it skips them).

Lint rows with no headroom are unchanged: A001 643/643, S054 3/3, C002 9/9, C011 2/2, A007 255/255. A002 lists nothing under the branch's paths. No baseline was edited.

Other checks:
- The shared-file blob `vidbyte/harnesses/native/__init__.py` hashes to `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- `git diff --numstat 1d110811..HEAD -- tests/features/codex_host` gives `5 0 FEATURE.md`, `3 0 README.md` and `440 0 test_codex_host_review_gaps.py`. This iteration changed no other file under `tests/`.
- Same-class call chains of depth 2 or more in `vidbyte/harnesses/native/codex/*.py`: 0 (`$PY -I $R/chains.py vidbyte/harnesses/native/codex`).
- Branch-added comment lines over 72 columns: 0 of 740.
- `git rev-list --count HEAD..origin/main` printed `0` after `git fetch origin`, so no merge was needed. `origin/main` is `8387d666`.

## 2. Findings

| Finding | Commit | What changed | Proof |
|---|---|---|---|
| R-26 | `30109e89` | wire.py `reject_unusable_schema`: the refusal reads `f"{UNUSABLE_SCHEMA_MESSAGE} Got {type(exc).__name__}."` and is raised `from None`. `PydanticUserError` is still caught by name. | New test `CodexHostSchemaRefusalTextTests.test_an_unusable_mapping_schema_is_refused_without_the_library_text_or_its_cause`: red at `130dd828`, and red under a mutant that drops only the cause (section 3) |
| R-26, extension | `736d4a58` | The same `except` also catches `RecursionError`, and the `@intent` block says why. | New test method `test_a_schema_with_a_cycle_under_a_schema_keyword_is_refused_before_any_request`: red with `bbaa5a8b`'s wire.py and at `30109e89` (section 3) |
| R-27 | `ad363725` | `CodexLiveTurn.stop_pending`; `async send_stop(connection, operation, *, quiet=False)` awaits `connection.interrupt` and clears the mark in `finally`; `stop()` marks the stop pending and spawns `send_stop`; `interrupt_codex_turn` returns on `snapshot is not None or stop_pending`, sets `stop_sent` and `stop_pending`, and awaits `send_stop`. Narration at host.py:401-404 is updated. `send_stop` has `# @intent a-stop-turns-others-away-only-while-in-flight` (A002). `over_cap()` and `stop()`'s `stop_sent` check are unchanged. | New class `CodexHostInterruptAfterFailedStopTests`: cases A and B red at `130dd828`; the in-flight case red under the revert alternative. The verifier's `probe_rc1` with `VARIANT=current` now prints exactly its `pending` lines |
| R-28 | `3d26abfe` | `TITLE_DESCRIPTION`: "The other review targets refuse it."; `INSTRUCTIONS_DESCRIPTION`: "The other review targets refuse them." | `lint/run.py --rule S025` passes; `CodexReviewTarget` still refuses `title` on a base-branch target and `instructions` on uncommitted-changes and commit targets |
| R-29 | `130dd828` (spec r6, before this iteration) | No code. | `review.md` marks it `fixed @130dd828 (spec r6)` |

`1461ddf4` adds lines only to the pack's FEATURE.md (three known failure modes and one suite-map entry) and README.md (one log entry). `77c92838` sets the statuses in `review.md`.

### R-26, and the defect found next to it

The verifier's fix is one line, and it worked the first time. The test reads the library's own text by running `pydantic_core.to_jsonable_python` on the same schema. It then asserts three things: that text is in no part of `error_texts(error)`, which follows the visible chain; `__cause__` is None; and the spawn tool's result, which is what the model reads, does not contain it.

While writing the cyclic case, my first schema put the cycle under `properties`. That raised `RecursionError`, not the `ValueError` the review expected. `OutputSchemaFormatter.annotate` (providers/output_schema.py:66-73, `_annotate_node` at :113-118) walks the schema keywords recursively. A cycle under `properties` or `items` never ends, while a cycle at a key it skips (`schema["self"]`) reaches `to_jsonable_python` and fails as `ValueError`. Probe `$R/probe_nested_cycle.py` at `30109e89`:

```
[properties cycle] builtins.RecursionError: 'maximum recursion depth exceeded' cause=None requests_sent=[]
[items cycle] builtins.RecursionError: 'maximum recursion depth exceeded' cause=None requests_sent=[]
[5000-deep nesting] builtins.RecursionError: 'maximum recursion depth exceeded while calling a Python object' cause=None requests_sent=[]
[tool properties cycle] ESCAPED RecursionError
[tool items cycle] ESCAPED RecursionError
[tool 5000-deep nesting] ESCAPED RecursionError
```

That breaks INV-8 (only `CodexAgentError`, `ConfigurationError` and `CancelledError` escape), INV-10 (tools never raise) and EC-82. It was there before R-2 too, but after `thread/start`. I fixed it in its own commit, because it is the same refusal, the fix is one name in the same `except`, and the next review is the last. I weighed three options:
1. **Catch `Exception`.** Rejected. It would also catch the formatter's own `ConfigurationError` for a non-model type (`output_schema must be a Pydantic BaseModel subclass or a dict, got 'type'.`) and rewrite that message.
2. **Detect cycles before the formatter runs.** Rejected. It adds logic beside a shared helper that NG-5 keeps unchanged.
3. **Add `RecursionError` to the caught types.** Chosen.

After the fix, the same probe prints `ConfigurationError: '… Got RecursionError.' cause=None requests_sent=[]` for all three cases, and `status=ToolStatus.ERROR output='configuration.invalid_argument: … Got RecursionError. Next step: …'` on the tool path. It is labelled `[R-26]` and recorded in R-26's status cell, because no finding row exists for it.

### R-27

I applied the verifier's recommended shape as written. One ordering detail matters: `stop()` sets `stop_pending` itself, before it spawns `send_stop`. A spawned task's first step runs a loop iteration later, so if `send_stop` set the mark, a user call scheduled in between would pass the guard and send a second interrupt.

The verifier's probe, `VARIANT=current PYTHONPATH="$W;$S" $PY -P -m unittest probe_rc1`, on the fixed code:

```
[current] A: retry returned None; turn/interrupt sent after retry: 2; turn: interrupted problem=None
[current] B: user interrupt returned None; turn/interrupt sent: 2; turn: interrupted problem=codex.turn_timed_out
[current] C: user interrupt returned None; turn/interrupt sent: 2; turn: interrupted problem=codex.budget_exhausted
[current] D: user call returned None; turn/interrupt sent in all: 1; turn: interrupted problem=codex.turn_timed_out
[current] E: second returned None; turn/interrupt sent in all: 1; turn: interrupted problem=None
[current] F: AC-16: interrupts=1 status=interrupted problem=None; finished-turn interrupt sent nothing more: True
```

Those are the verifier's `pending` lines. C also shows that a second cap crossing after the failed cap stop sends nothing (`cap interrupts sent (after a 2nd crossing): 1`), so D-7 and EC-30 hold.

Code around the fix that I re-checked:
- The close path (host.py:200-206) sends its cleanup interrupts directly and does not read `stop_pending`. It did not read `stop_sent` either, so it is unchanged.
- Goal runs inherit `send_stop`, which passes `self.state`, so they still go through `cancel_goal_operation`.
- `self.handle` equals the caller's handle, because `_owned` looks the turn up by that handle and handles compare by their two ids.
- No same-class chain of depth 2 was added: `stop → send_stop → connection.interrupt` is one level.
- The headers of host.py and turns.py still hold: each turn sends its stops through `CodexConnection`.

## 3. Red runs of the new tests

All runs use `python -m unittest <class>`. A mutant is compiled in memory by `$R/mutant_run.py <mutant> <class>`, and nothing on disk changes. `git status --short` was empty after each run.

- `CodexHostSchemaRefusalTextTests` (R-26), at `130dd828`:
  ```
  FAIL: ... (schema='a mapping with an object value')
  AssertionError: PydanticSerializationError(Unable to serialize unknown type: <class 'object'>) is not None
  FAIL: ... (schema='a cyclic mapping')
  AssertionError: ValueError('Circular reference detected (id repeated)') is not None
  Ran 1 test in 0.337s
  FAILED (failures=2)
  ```
  Under `text_kept` (`from None`, with `{exc}` kept), the text assertion fails in both subtests: `AssertionError: "Unable to serialize unknown type: <class 'object'>" unexpectedly found in "output_schema must be … JSON. Unable to serialize unknown type: <class 'object'>"`, `Ran 1 test in 0.018s`, `FAILED (failures=2)`.
- The recursion method, under `no_recursion` (the state at `30109e89`):
  ```
  ERROR: test_a_schema_with_a_cycle_under_a_schema_keyword_is_refused_before_any_request (schema='a cycle under properties')
  RecursionError: maximum recursion depth exceeded
  ERROR: ... (schema='a cycle under items')
  RecursionError: maximum recursion depth exceeded
  Ran 2 tests in 0.056s
  FAILED (errors=2)
  ```
  With `bbaa5a8b`'s `wire.py` copied in and then restored, the whole class gave `Ran 2 tests in 0.382s`, `FAILED (failures=2, errors=2)`: the two R-26 failures above, plus these two recursion errors.
- `CodexHostInterruptAfterFailedStopTests` (R-27), at `130dd828`:
  ```
  FAIL: test_a_user_interrupt_after_a_failed_timeout_stop_is_sent_and_the_timeout_label_stays
  AssertionError: 1 != 2
  FAIL: test_a_user_interrupt_that_failed_is_sent_again_when_retried
  AssertionError: 1 != 2
  Ran 3 tests in 0.826s
  FAILED (failures=2)
  ```
  The in-flight test pins R-16, so it passes at `bbaa5a8b`, which has R-16's guard. It goes red under `revert_guard`, the verifier's smaller alternative: `AssertionError: 2 != 1`, `Ran 3 tests in 0.821s`, `FAILED (failures=1)`. Under `pending_sticks` (`send_stop` never clears its mark), A and B fail with `1 != 2`.
- Stability: the gaps file passed 12 runs in a row, each `15 passed` in 1.88 s to 1.99 s.

## 4. Test changes proposed

None. No existing test, fake or support file changed. Every addition is a new class or method in `test_codex_host_review_gaps.py`, or a new line in the pack's README.md and FEATURE.md.

## 5. Findings I believe are wrong

None. Both Majors reproduced exactly as the verifier described.

## 6. Still open, and what I would try next

- **No confirmed finding is open.** R-19 to R-25 are follow-ups and were not handed in. I did not touch them.
- **R-24 (mutant M5) still survives.** No new test crosses a cap after a user interrupt. I kept `turn.stop_sent = True` on the user path as the briefing required. To kill M5, add a test with a user interrupt, then a cap crossing, asserting one interrupt and `problem=None`.
- **R-27 residual.** The verifier considered it and did not raise it. Suppose a user interrupt's caller is cancelled while its `turn/interrupt` is already running on a worker. `finally` clears `stop_pending` before the request ends, so an immediate second call can send a second interrupt. That is the pre-R-16 behaviour, in a narrower window. Closing it would mean tracking the worker future past cancellation, inside `CodexConnection.call`, which is out of proportion for a Minor. `$R/probe_cancelled_interrupt.py` holds `turn/interrupt`, cancels the first `interrupt_codex_turn` task and calls again. It prints `first call cancelled` / `turn/interrupt count after retry while first still held: 2` / `final: interrupted problem=None`. The second call returns normally, and the turn ends as AC-16 says.
- **R-1 residual, accepted in S4.** A review that finished before its registration, and whose caller is also cancelled during the read-back, stays RUNNING until close.

## 7. Commits

| Commit | Subject |
|---|---|
| `30109e89` | fix(codex-host): refuse an unusable output_schema by type name only [R-26] |
| `736d4a58` | fix(codex-host): refuse an output_schema whose walk never ends [R-26] |
| `ad363725` | fix(codex-host): skip a user interrupt only while a stop is in flight [R-27] |
| `3d26abfe` | fix(codex-host): say the other review targets refuse title and instructions [R-28] |
| `1461ddf4` | docs(codex-host): list the R-26 and R-27 tests in the pack's README and FEATURE |
| `77c92838` | docs(spec): mark codex-host R-26..R-29 fixed in review.md |
| (next) | docs(spec): verify-log iteration 2 for codex-host |
