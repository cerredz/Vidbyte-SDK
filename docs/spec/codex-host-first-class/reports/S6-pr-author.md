# S6 PR author: codex-host-hardening + codex-host-first-class

- **Stage:** S6, the PR author. One PR body covers both slices.
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1181. It stays a draft, and its base stays `ai/resolve-pr-1055-comments` (#1178, head `8baff351`).
- **Code under review:** HEAD `6cd11f99` before S6. Its last source commit is `bd89e5b8`. S6 changed no source, test or `lint/` file.
- **S6 commits:** `5ebb4aec` (both specs' frontmatter and §17, and `pr-body.md`), then this report's commit, which also carries the final `pr-body.md` wording.

## What the code does

**Slice 1** makes the existing `CodexHost` safe to run unattended.

*Server requests.* The host used to auto-accept every approval. Now a router fails closed and answers each server request exactly once.
- A developer may pass an async `approval_handler`. It runs on the host's own loop, within the 300 s tool-call bound.
- An answer that raises, hangs, has the wrong type, or does not fit the request falls back to the method's default. The defaults are: decline, no answers, nothing granted.
- Close cancels pending handler calls, and a request that arrives once close has begun gets its default.
- A `USER` reviewer is refused before any request, but only on a host without a handler.

*Errors.* Every `CodexAgentError` carries `retryable`, which is true for exactly five codes. The four read-only methods retry one overload. Spending methods are sent once. A `thread/read` refusal is told apart from its other failures.

*Logging.* Every Codex call writes exactly one record, cancelled calls included. Ids and origins render as one bounded token (`LogToken.of`, `ExceptionOrigin.describe`). No record carries exception text: handed-over starts are no longer shielded, so asyncio never logs their failure text (R-11).

*Turns.* A turn whose events fail, or whose watcher read fails, ends `FAILED` after one stop, so no turn can stay `RUNNING`. `forget_codex_turns` releases ended turns.

*Settings.* openai-codex moves to 0.163.0, and the host gains the settings it was missing:
- MAX and ULTRA effort;
- validated service tiers;
- `networkAccess` and `writableRoots`;
- fork points with `before_turn_id` and `defer_goal_continuation`;
- review caps;
- listing limits and `force_reload`.

**Slice 2** adds 25 methods. `CodexHost` inherits them from four mixins that do not import openai-codex, all built over `CodexHostCore`.

*How a call runs.* Each method guards, builds a validated input record, and passes an experimental gate when its method is experimental. It then talks to Codex through `CodexConnection.call` or `raw`. For an unmodeled method, `raw` runs the parse inside the call, so drift surfaces as `codex.protocol_mismatch`.

*Plan mode.* `run_codex_plan` reads Codex's own presets and starts a plan turn. `collaboration_mode` rides on spawn, continue, launch and side-chat requests.

*Streams and waits.* `stream_codex_turn` reads a bounded event window, with a per-turn bound and a host-wide bound. A reader that falls behind gets a GAP event, and every stream ends with exactly one ENDED event. Raw reasoning is never streamed. `wait_codex_turns` waits on the turns' own end futures and never cancels a turn.

*Side chat.* `start_codex_side_chat` follows Codex's own `/side` flow: an ephemeral fork, a check of the fork's reviewer before the tool handler is shared, an injected boundary message, then a turn on the fork.

*Worktrees.* `create_codex_worktree` runs `git worktree add` through the canonical `GitWorktrees` helper in lib, with no shell, no prompt, a 120 s bound and a 64 KiB output cap. Any root, stat or path failure becomes a `configuration.invalid_argument` packet.

*Goals and history.*
- Goal changes carry `origin: "user"`.
- A resume sends a status-only set and cancels unless Codex refused the set.
- An edit never sends a status.
- History changes (archive, revert, inject, clear) share one idle-thread helper.

*Tools.* There are 16 new tools, 42 in all. On the settings tools a model can set only the model and the effort. The side-chat tool forces `READ_ONLY` and `never` on both the fork and the turn. Nine methods have no tool, by design.

## What S6 produced
- **`docs/spec/codex-host-first-class/pr-body.md`.**
  - Line 1 is `feat(codex-host): production hardening plus 25 first-class Codex functions and 16 tools`.
  - The nine required headings appear in the required order.
  - It is 64,093 bytes (`wc -c`), under 65,536.
  - The PR received the body without line 1. Diffed against `gh pr view --json body`, the only difference is gh's trailing newline.
- **How it was built.** `scratchpad/s6_build_pr_body.py` took the two AC tables' proof cells from each spec's §6.2, so no test id was retyped. It also asserts that every AC row is present and in order: 41 rows for slice 1 and 44 for slice 2.
- **AC id check.** `scratchpad/s6_ac_proof_check.py` parses each cited test file with AST and resolves every cited id: `TOTAL ids=168 missing=0`.
- **Specs.** In both: `status: pr-open`, `updated: 2026-10-18`, and one §17 row: slice 2 `r8 | 2026-10-18 | S6 PR | finalized for review`, slice 1 `r6 | 2026-10-18 | S6 PR | finalized for review`. No revision was bumped, and no other line changed (`git diff` showed 5 insertions and 3 deletions). §5 of both specs matches the code, so it was not edited.

## Snippet output

**Live run: not performed; it requires a Codex login.** No `codex` binary ran, and `VIDBYTE_CODEX_LIVE_TESTS` stayed unset.

**Local check, without Codex** (`scratchpad/s6_snippet_check.py`, `V` interpreter):
```
python 3.11.0
slice1: CodexHost(approval_handler=answer) built without starting a process: CodexHost
slice1: USER reviewer request builds: user
slice1: handler on git status: accept
slice1: handler on terminal input: decline
slice1: a sync handler is refused at construction: ConfigurationError
slice2: imports ok; CodexHost() built without starting a process: CodexHost
slice2: CodexThreadSettingsUpdate: high
slice2: collaboration_mode: default
slice2: enums: plan_delta ALL_COMPLETED
slice2: CodexHostTools tool count: 42
slice2: the 25 new methods present on CodexHost: 25
slice2: unopened host refuses run_codex_plan: ConfigurationError - run_codex_plan needs an open CodexHost, and this host is not open: it was never entered, or its async with block already
```

**Both §4 snippets, verbatim, through the suite's fake app-server.** The fake patches `CodexClient` and `shutil.which`, so no binary runs. Result: `3 passed in 1.25s`.
- `test_codex_host_first_class_snippet.py::CodexFirstClassSnippetTests::test_the_section_4_snippet_prints_the_streamed_plan_then_both_statuses_then_the_server_names`
- `test_codex_host_approvals.py::CodexApprovalSnippetTests` (2 tests)

## Gates S6 re-ran at HEAD `6cd11f99`

| Gate | Result |
|---|---|
| area tests | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1306 passed, 3 skipped in 82.81s` |
| source stage, run alone | `SDK-LINT: PASS` (C021 `0 0 CLEAN`, A002 IMPROVED 703 → 582), then `reasoning trace contracts: ok (182 tools, 55 shapes)`, then the same single inherited failure: `1 failed, 6837 passed, 27 skipped in 138.00s`. These are iteration 3's exact counts |
| 72-column comments, on added lines only | 0 of 1,172 added comment lines are over 72 columns |
| line ceilings | `host.py` 786 · `wire.py` 839 · `codex_host.py` 891 · `codex_host_inputs.py` 785 |
| test contract | `git diff 2bdb5e95..HEAD -- tests \| wc -l` gives `0` |

The package stage was not re-run, because it installs the package and S6 runs no pip. Iteration 3 at `bd89e5b8` gave `CI passed.`, and nothing outside `docs/` has changed since.

## Final `gh` output

Captured after the last `gh pr edit`, before this report's own commit:
```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1181 --json title,isDraft,baseRefName,url
{"baseRefName":"ai/resolve-pr-1055-comments","isDraft":true,"title":"feat(codex-host): production hardening plus 25 first-class Codex functions and 16 tools","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1181"}
$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1181
no checks reported on the 'feat/codex-host-first-class' branch
```
CHECKS: 0/0 (none configured). Every workflow is `workflow_dispatch` only.

## Deviations

**From the spec, slice 2.** These are §17 "Implementation deviations", 14 items. The body carries one line each:
1. A goal-resume JSON-RPC error names `thread/goal/set`.
2. `_change_idle` lives in `host_core.py`.
3. `_resume_now` suppresses a failing cancel and keeps the original error.
4. Defaults apply only to `None`.
5. The gate's feature words, including the child filter key.
6. The stream translator narrows by type, so `turn_stream` imports the SDK at module level.
7. `feature_wire` uses `require_instance`, and two public helpers are unlisted.
8. Blank text is allowed in a few records, the rename takes one line, and `GitWorktreeSpec` is bounded by the native limits.
9. Wire details: the static `collaboration_mode`, the `sandbox_policy` dump, and `finish` closing the stream.
10. The side chat's turn view is the request unchanged.
11. Tool texts and `__all__`.
12. The resume tool resets both of its tables.
13. Tool headers name `forget_codex_turns`.
14. Slice 1's reviewer refusals call `reject_routed_reviewer`.

**From the spec, slice 1.** These are §17 "Implementation deviations (S3)", 11 items:
1. Row 13 landed in P3.
2. One shared `_reject_bad_list_limit`.
3. `_reject_goal_fields` lost its owner; superseded by r5.
4. "any model" was a literal; superseded by r5.
5. An interim `approvals_answered=False`.
6. The host.py row was split across five commits.
7. `_schedule` was split out for S008 and S024.
8. A local `code` variable.
9. `AGENT-LINT` vs `SDK-LINT`.
10. `VALIDATE_SPAWN_REQUEST` was kept.
11. semgrep-core was run per file.

**From the briefing, by S6.**
- **File path.** The briefing names `vidbyte/lib/validation.py`, which does not exist. The file is `vidbyte/lib/dataclasses/validation.py`, and the body and the follow-up use that path.
- **The validation follow-up.** The briefing says the other callers "likely leak". S6 probed `NativeThreadRequest` read-only (`scratchpad/s6_probe_native_paths.py`, no source change), and both leaks are real: `PROBE bad-fspath: builtins.TypeError` and `PROBE stat-refused: builtins.PermissionError`. A valid control built (`WindowsPath`). The body states the confirmed result. That wording landed after `5ebb4aec`, so this report's commit also carries the 2-line `pr-body.md` change, and the PR body was re-applied from it.
- **Summary length.** The Summary has a 5-sentence lead, then a five-bullet list of what slice 1 adds, then the slash-command table the briefing asked for. It was not squeezed into 3–6 sentences.
- **Package stage.** It was not re-run, as explained above.

## Candidate field-guide lessons
These are drafted from both `review.md` files: the conventions lens, plus repo-specific conformance and engineering findings that recurred. They are not written to the field guide. Link for each: https://github.com/cerredz/Vidbyte-SDK/pull/1181

1. **Check comment width on added lines only.**
   - *Trigger:* any commit that adds `#` lines under `vidbyte/`.
   - *Preferred action:* run the `comment-format.md` check over the diff's added lines, not whole files.
   - *Reason:* both slices shipped over-wide lines that were held at Blocker (6 lines, then 14). Meanwhile, a whole-file run flags dozens of legacy lines, for example in `vidbyte/lib/constants/codex.py`, which buries the real hits.
   - *Quick check:* `git diff -U0 <base>...HEAD -- 'vidbyte/*.py' | tr -d '\r' | grep '^+' | grep -v '^+++' | cut -c2- | awk 'length($0)>72 && /^[ \t]*#/'` prints nothing.
2. **A record that checks a caller's path must also map `OSError` and `TypeError`.**
   - *Trigger:* a record calls `RecordFieldConverter.to_path`, `RecordFieldValidator.require_directory`, or `Path.is_dir` / `exists` on input.
   - *Preferred action:* catch `(ConfigurationError, OSError, TypeError)`, re-raise the field's `ConfigurationError` `from None`, and let a caller's own `__fspath__` `ValueError` pass through.
   - *Reason:* on Python 3.11, `Path.is_dir()` re-raises a refused `stat`, because pathlib ignores only errnos 2, 9, 20 and 10062. `os.fspath` raises `TypeError` for a bad `__fspath__`. Each surfaced in a separate re-review round (R-RR1, R-RR2-1), and `NativeThreadRequest` still leaks both.
   - *Quick check:* build the record with a PathLike whose `__fspath__` returns `5`, and with `Path.stat` patched to raise `PermissionError` for that path. Both must raise `ConfigurationError`.
3. **Give every bound and guard its own failing test.**
   - *Trigger:* adding a size bound, grace, re-check or "sent once" guard.
   - *Preferred action:* for each constant, write one test that patches it where it is imported and fails if its comparison becomes `True`.
   - *Reason:* both slices' reviews found 3–5 Majors of "no test can fail" (R-4 to R-8, then R-6 and R-7). A test plan claimed "four bounds patched", and one was never patched.
   - *Quick check:* grep the tests for a `patch` of each bound constant, then run the `cmp → True` mutant against the whole `tests/features/codex_host` directory.
4. **Never `asyncio.shield` an executor future you stop reading.**
   - *Trigger:* awaiting a `concurrent.futures` future with a timeout, and handing it over on cancel.
   - *Preferred action:* `await asyncio.wait_for(asyncio.wrap_future(future), bound)` with no shield, and put the late-outcome callbacks on the concurrent future.
   - *Reason:* the shielded inner wrapper is never read, so asyncio logs "Future exception was never retrieved" with Codex's stderr tail (R-11). An ordinary close after a cancelled spawn was enough to trigger it.
   - *Quick check:* in a test, capture the `asyncio` and `concurrent.futures` loggers, run `gc.collect()` and `await asyncio.sleep(0)`, and assert there is no ERROR record.
5. **Ids that Codex or a caller chose go through `LogToken.of`.**
   - *Trigger:* logging a `method`, `threadId`, `turnId`, `itemId` or handle id, or an exception origin.
   - *Preferred action:* `LogToken.of(value, CODEX_HOST_LOG_TOKEN_MAX_CHARS)`; origins through `ExceptionOrigin.describe`.
   - *Reason:* a crafted `itemId` forged a `handled_by=handler answer=accept` record (R-9), and `<frozen os>` split an origin into two tokens (R-12).
   - *Quick check:* make the test's `log_fields` refuse any token without `=`, then feed an id that contains spaces and a newline.
6. **A tool built from `spawn_defaults` must first reset the method's rejected-fields row.**
   - *Trigger:* a new model tool over a host method that has a `CODEX_HOST_REJECTED_FIELDS` row.
   - *Preferred action:* reset every path of that row to a fresh record's value, read from the host table as `ResumeCodexGoalTool._resume_defaults` does, and only then narrow.
   - *Reason:* without the reset, the side-chat tool failed in every scope whose defaults set `tools`, `name` or a personality, and the refusal told the model to change a field it cannot reach (R-5).
   - *Quick check:* run the tool with `spawn_defaults` that set every rejectable field. It must succeed.
7. **Treat a spending request as applied from the moment it is sent.**
   - *Trigger:* a compensating cancel after `thread/goal/set`, `turn/start` or `review/start`.
   - *Preferred action:* mark it sent before the call, and compensate on any failure except Codex's own JSON-RPC refusal, as openai-codex does (`client.py:643-645`).
   - *Reason:* an answer Codex applied but that failed validation left an untracked paid goal running (R-4).
   - *Quick check:* have the fake apply the set and echo a bad status. The test must see one pause set and at most one interrupt.
8. **A header that promises narration binds every method under it.**
   - *Trigger:* adding public methods to a module whose header says "each method is a narrated main function".
   - *Preferred action:* put a one-line step comment above each step group, even in a 6–9 statement method.
   - *Reason:* 13 methods shipped unnarrated under such headers. The verifier held it at Major because of the false header claim, even though `host.py` has older thin methods (R-8).
   - *Quick check:* count tokenize comments per public method body; each must be at least 1.

## Things that looked wrong while reading

**1. Validation helpers that leak raw exceptions.** These are outside this PR: `validation.py` and `native_threads.py` are untouched, and they are listed as a follow-up.
- `vidbyte/lib/dataclasses/validation.py:133`: `require_directory` lets a refused `stat` escape as `PermissionError`.
- `:198` (`to_path`), `:210` (`to_folder`) and `:231` (`to_files`): each calls `os.fspath`, which raises `TypeError` for a bad `__fspath__`.
- Confirmed through `vidbyte/lib/dataclasses/native_threads.py:119-120` (`NativeThreadRequest._checked_workspace`) by the S6 probe above. `:145-146` (`_checked_skills`) has the same shape and was not probed.

**2. A cosmetic label.** `vidbyte/lib/dataclasses/codex_host_features.py:134` passes the hand-written label `"update_codex_thread_settings network_access"` to `require_bool`. Every sibling check in that record builds `f"{owner} <field>"`. The text is identical, so behaviour is unchanged. It belongs with m-7.

**3. Not a defect: tool and host checks are layered.** `WaitCodexTurnsTool` (`vidbyte/tools/builtins/codex/live.py:227`) checks shape and ownership only, and the host's `CodexTurnsWaitRequest` refuses duplicate and oversize tuples. Its errors become tool error results through `_run`.

**4. No red checks.** None are configured remotely, and the only local failure is the inherited `harness_threads` test, which fails with `assert 167 == 120` at merge-base `6f5a7310` too.
