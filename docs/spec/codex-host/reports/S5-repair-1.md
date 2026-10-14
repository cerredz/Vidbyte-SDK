# S5 · Repair report, iteration 1 — codex-host

Stage: S5 repair, iteration 1 of 8 · Start HEAD `bbe9672f` · Code HEAD `fb76e558` (pushed), with this report and `verify-log.md` committed on top · Branch `feat/codex-host` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 (draft, title and body untouched) · Inputs: `review.md` (R-1 to R-18 open, R-19 to R-25 follow-ups), spec r5 (`bbe9672f`).

Environment for every command below:

```
W=C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host
PY=C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python.exe   # Python 3.11, openai-codex 0.162.1
```

No real `codex` binary or app-server was started; every host test runs over the in-memory fake at the section 13 seam.

## 1. Findings fixed

One commit per finding. Each one ran green on the pack before it was committed, and lint ran green before each source commit.

| Finding | Commit | What changed | Proof |
|---|---|---|---|
| R-1 | `2f098372` | `_accept_review` wraps the D-23 read-back in `try/except BaseException`: watch the turn, give it its one stop, re-raise. After R-4 the stop is `turn.stop(connection, None)`. | New test `CodexHostReviewReadBackCancellationTests`, red before the fix (verify-log) |
| R-2 | `6856645b` | New `CodexParamsTranslator.reject_unusable_schema(request)` turns the schema into JSON with `pydantic_core.to_jsonable_python`, exactly as the turn would send it. It runs in spawn, continue and launch next to the other build-first checks, before any request. `TypeError`, `ValueError` and `PydanticUserError` become `ConfigurationError("output_schema must be a Pydantic model type or a mapping that serializes to JSON. <reason>")`. The formatter's own `ConfigurationError` for a non-model type passes through unchanged (EC-82). | New test `CodexHostOutputSchemaRefusalTests`: 3 FAIL + 3 ERROR before the fix |
| R-3 | `8f6975e8` | Goal status, sandbox readiness and the approval default travel as `CodexGoalStatus`, `CodexSandboxReadiness` and `CodexApprovalMode`, converted once at the wire edge (turns.py, connection.py, preflight.py). `GOAL_PROBLEM_CODES` and `CODEX_GOAL_TERMINAL_STATUSES` are keyed by members, and `CODEX_HOST_DEFAULT_APPROVAL_MODE = CodexApprovalMode.AUTO_REVIEW`. The constants test still reads `"auto_review"`, because the enum is a `str`. | Pack green; lint green |
| R-4 | `846ce849` | `spawn_task` with its task set, and `stopped()`, move onto `CodexConnection`. The one stop moves onto `CodexLiveTurn.stop(connection, reason)`, and the turn's timer calls it. `watch(connection, on_event)` takes the connection. The review registration is a new leaf, `_track_review`. Both read-backs call `CodexPreflight.require_thread(..., include_turns=True)` under `suppress(CodexAgentError)`, so `_read_back` is gone. Header line 5 now names who sends, who owns and who stops. | AST scan of same-class call chains over `vidbyte/harnesses/native/codex/*.py`: 16 before, 0 after |
| R-5 | `08d498d8` | Every comment paragraph the branch added with a line over 72 columns is rewrapped. Only comment lines change, and `# @intent` lines stay alone. A local script rewrapped only paragraphs whose too-long lines are all branch-added. It found no paragraph that mixes branch lines with main's. | `git diff $(git merge-base origin/main HEAD) -- vidbyte \| grep -E '^\+\s*#' \| awk 'length($0) > 73' \| wc -l` gives 0 (was 176) |
| R-6 | `4d597f91` | Launch catches `BaseException`, stops every started turn, and rewrites the message only for a `CodexAgentError`. | New test `CodexHostLaunchCancellationTests`, red before the fix |
| R-7 | `52e9e313` | `__aexit__` closes the goal streams and the connection in a `finally` around the close interrupts. `CodexConnection.close` also shuts its executor down in a `finally`. | New test `CodexHostCloseCancellationTests`, red before the fix |
| R-8 | `f2e9db7e` | `wait_codex_turn` calls `_reject_bad_seconds("wait_codex_turn", "timeout_seconds", …)`, and `_launch_items` calls `_reject_small_int("launch_codex_subagents", "limit", …, CODEX_HOST_MIN_LIVE_TURNS)`. Both are imported privately from `vidbyte.lib.dataclasses.codex_host`. `BAD_TIMEOUT_MESSAGE` and `LAUNCH_LIMIT_MESSAGE` are dropped. Spec r5 had already withdrawn deviation 1. | `lint/run.py --rule C002`: 9 = baseline 9 |
| R-9 | `fad8c55f` | `# @intent` blocks on the seven functions the finding names. | `lint/run.py --rule A002 --all`: no finding under the branch's new paths. The 4 hits left in `lib/errors/base.py` are main's own `__init__`s, and the branch changed none of them. A002 found 600 against a baseline of 703 |
| R-10 | `874bd5a3` | `CodexConnection` remembers each thread whose start it handed over (`_starting`). `require_idle` refuses that thread while `connection.starting(thread_id)`. `_post_late` now always posts `_land` to the loop. `_land` frees the thread, then adopts an accepted start in the same callback, so no await can slip in between. A withdrawn start (`future.cancel()`) never marks the thread. | New tests `CodexHostInFlightStartTests`: one red before the fix, one red under a mutant |
| R-11 | `528e5ef6` | 11 constants are appended at the end of `vidbyte/lib/constants/codex.py` and at the end of `__all__`. `CODEX_THREAD_START_METHOD` is reused. All 15 inline sites use the constants, and errors.py compares with `CODEX_THREAD_READ_METHOD` and `CODEX_THREAD_FORK_METHOD` instead of private copies. | `grep` for quoted method names in `vidbyte/harnesses/native/codex/*.py`: none left |
| R-12 | `bbe9672f` (spec r5) + `4a9ecc49` | `OUTPUT_SCHEMA_DESCRIPTION` is rewritten per D-36 in 5 sentences with no examples. The `CodexSpawnRequest` docstring gains a D-36 paragraph that also covers the Pydantic model check and the EC-82 refusal. New EC-83/EC-32 pin. | New test `CodexHostMappingSchemaTests`, red under a mutant |
| R-13 | `d894d87a` | Tests only: a late goal run gets one `cancel_goal_operation` and problem None, and a late turn with a `timeout_seconds` gets one interrupt and problem None. | Red under M1 and M2 |
| R-14 | `168282f4` | Tests only, CI-visible over `StubCodexHost`: a launch that fails or is cancelled while it holds the whole cap must give every slot back. | Red under M3 (both subtests) |
| R-15 | `1169ad68` | BRANCH and SHA descriptions: "The other review targets refuse it." | Pack green |
| R-16 | `7d4c21fa` | `interrupt_codex_turn` returns when `turn.snapshot is not None or turn.stop_sent`. | Pack green |
| R-17 | `9dee1619` | The goal-start cleanup calls `state.finish()` and `unregister_goal_operation` in a `finally` around the cancel await. | Pack green |
| R-18 | `4e222e3c` | The ledger `CodexRunResult` gets keyword arguments, the review pricing call passes `turn_model=""`, and `turn_problem` uses `if`/`elif`. | Pack green |

`review.md` marks R-1 to R-18 `fixed @<sha>`. It marks R-12 `fixed @bbe9672f (spec r5) + @4a9ecc49 (code/tests)`. R-19 to R-25 are follow-ups and stay open.

## 2. The new test file

`tests/features/codex_host/test_codex_host_review_gaps.py` (330 lines) is the only new test file. README.md has 2 added lines and FEATURE.md has 1, both list it, and neither has a deletion. `git diff --numstat 1d110811..HEAD -- tests/features/codex_host` gives `1 0 FEATURE.md`, `2 0 README.md`, `330 0 test_codex_host_review_gaps.py`. No fake, support file or existing test changed.

| Class | Finding | SDK needed | Red evidence |
|---|---|---|---|
| `CodexHostReviewReadBackCancellationTests` | R-1 | yes | pre-fix: no `turn/interrupt` in 10 s |
| `CodexHostOutputSchemaRefusalTests` | R-2 | yes | pre-fix: `thread/start` or `thread/resume` sent for a dataclass type; `PydanticSerializationError` for a non-JSON mapping |
| `CodexHostLaunchCancellationTests` | R-6 | yes | pre-fix: no `turn/interrupt` in 10 s |
| `CodexHostCloseCancellationTests` | R-7 | yes | pre-fix: client never closed |
| `CodexHostInFlightStartTests` (2 tests) | R-10 | yes | pre-fix: `thread/resume` count 2 != 1; mutant: thread busy forever after a failed start |
| `CodexHostMappingSchemaTests` | R-12 | yes | mutant (required keys checked): schema problem on valid JSON |
| `CodexHostLateStopTests` (2 tests) | R-13 | yes | M1: no goal cancel; M2: `codex.turn_timed_out` problem |
| `CodexHostLaunchToolSlotTests` | R-14 | no (CI-visible) | M3: `codex.session_busy` on the second launch |

The verbatim red output of every test is quoted in `verify-log.md`. Mutants were patched in memory, one subprocess per mutant (`unittest` over the class), and never written to the tree.

## 3. Design notes

- **R-4.** `stop` cannot live on `CodexConnection`, because `stop → interrupt → call` would be a new same-class chain there. On `CodexLiveTurn` it is a leaf that calls out to the connection. `turns.py` imports `CodexConnection` only under `TYPE_CHECKING`, and `connection.py` does not import `turns.py`, so no cycle forms. `stopped()` is true once close began (`begin_close` or `reap`) or the process died, which is what the host's `_stopped` returned.
- **R-10.** `_post_late` runs on a worker. Freeing the thread there would race with the loop, so freeing and adopting happen together in one loop callback (`_land`). The finding's other option was to keep the registry reservation and release it from three places. That needs more code and adds an ownership path to the registry.
- **R-2.** The check uses `to_jsonable_python` on `CodexVidbyteTranslator.output_schema(...)`, which builds exactly what `turn_start` sends. A cyclic mapping (`ValueError`), a mapping holding a lock (`TypeError`, raised by the formatter's copy), a model with a callable field (`PydanticInvalidForJsonSchema`, a `PydanticUserError`) and a non-JSON object (`PydanticSerializationError`) are all refused. A `set` passes, because the wire's `model_dump(mode="json")` also turns it into a list.

## 4. Invariants checked this iteration

- The shared file is unchanged: `git show HEAD:vidbyte/harnesses/native/__init__.py | sha256sum` gives `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- The §8.4 budget holds. No file, class, record, enum or dependency was added under `vidbyte/`. The new methods are on existing classes (`CodexConnection.stopped`, `spawn_task`, `starting`, `_land`; `CodexLiveTurn.stop`; `CodexHost._track_review`; `CodexParamsTranslator.reject_unusable_schema`), and the 11 new names in `lib/constants/codex.py` are constants.
- No lint baseline number was raised, and no suppression, skip, xfail or config change was added.
- Same-class call chains of depth 2 or more in `vidbyte/harnesses/native/codex/*.py`: 0.
- The catch-up merge `fb76e558` of `origin/main` (41 commits) had no conflicts and touched none of the branch's files.

## 5. Gates

All gates ran in this iteration on `fb76e558`, the merge commit; `verify-log.md` quotes the final lines.

| Gate | Result |
|---|---|
| New test file | `10 passed` |
| Feature pack, with openai-codex | `111 passed` |
| Feature pack, CI view (`openai_codex` hidden) | `36 passed, 75 skipped` |
| `run_ci.py --stage source` | `4117 passed, 22 skipped` / `CI passed.` |
| `run_ci.py --stage package` (no `PYTHONPATH`) | smoke checks passed / `CI passed.` |
| `lint/run.py` | `SDK-LINT: PASS` |
| Semgrep typed-mapping policy | `0 findings` |
| `generate-sdk-public-api.py --check` | current, 606 exports |
| Remote `ci.yml`, run 38519843721 | success: Source 3.11, Source 3.12, Package |
| Remote `static-policy.yml`, run 38519846158 | success |

## 6. Residuals and open items

- **R-1 residual, as the verifier noted.** Suppose a review finished before its registration, so its events were dropped, and its caller is also cancelled during the read-back. The review is then watched and sent one quiet interrupt, but it stays RUNNING until close, because no completion will ever arrive. This needs Codex to finish the review inside the window between `review/start` returning and the registration read-back.
- R-19 to R-25 are follow-ups and were not touched. R-25 (local JSON Schema validation) is scope-adding and stays Q-10.
- R-9 says "do this with R-21". R-21 (intent tags that narrate) is a follow-up, so only R-9's seven missing markers were added.
