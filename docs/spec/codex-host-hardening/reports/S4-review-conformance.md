LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the spec is built nearly row for row, but one review path still leaves a registered turn RUNNING forever and lets a raw exception escape (the user's "exception handle everything" bar), and cancelled calls break INV-7's "exactly one record".

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The user's #1055 conventions hold. All 12 §9.2 messages, the changed REVIEWER_MESSAGE, USER_REVIEWER_TEXT, both NEXT_STEPS rows and all three LIKELY_CAUSES rows match the spec word for word. Every new table and bound lives in `vidbyte/lib/constants/codex_host.py`, with a sorted `__all__`. C021 passes at baseline 0. Every new input is a field on a `codex_host_inputs.py` record, and `CodexHostSetup` is built first in the constructor (D-31…D-33, INV-47, INV-48). The toolset stays at 26 tools.
- The router matches INV-15…INV-21. `handle` has one `try`. The close check, the parse and `_schedule` run under the lock, and `future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)` runs outside it. `cancel_pending` cancels a snapshot. The defaults are fail-closed. The AC-1 test drives the §4 snippet verbatim against the fake and asserts `["completed","1"]`, `approvalsReviewer` user, and started/closed `(1,1)`.
- Fork follows INV-28 step by step. `_reject_experimental_fork_fields` runs before any request, and with `experimental_api=False` zero requests are sent (AC-22). The injected `beforeTurnId` and `deferGoalContinuation` are asserted on the wire. INV-30 substitutes `CodexSpawnRequest()` only for `None`.
- The scope is exactly the §8.4 budget:
  - 3 new files, 13 new classes, 0 new dependencies, 9 config keys;
  - the 24 non-docs, non-test files are exactly the §12.3 rows;
  - no lint, semgrep, scripts or CI change, and no test change after fadec47f;
  - host.py is 923 lines, under 940.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [request-fidelity / weighted word] vidbyte/harnesses/native/codex/reviews.py:139 — A review that has already ended, whose snapshot fails to build, leaves its turn RUNNING forever and escapes as a raw exception
  Evidence: reviews.py:139-142, the one completion path that is not guarded:
    `if stored is not None and stored.status.value != CodexTurnStatus.RUNNING.value:`
    `    client.unregister_turn_notifications(handle.turn_id)`
    `    self._registry.finish(turn, self._responses.turn_snapshot(turn, stored.items, stored))`
    `    return handle`
  The other two completion paths are guarded: `on_event` at turn_events.py:69-88 (INV-11) and `complete_review` at turn_events.py:105-111 (INV-12).
  An in-process probe used HostTestCase and the fake. It patched `CodexResponseTranslator.stored_turn` to return a completed turn, and `turn_snapshot` to raise RuntimeError, which is the AC-7 fault seam. It printed:
    `FIRST REVIEW raised: builtins RuntimeError`
    `SECOND REVIEW raised: CodexAgentError codex.session_busy`
    `FORGET raised: CodexAgentError codex.session_busy`
    `REGISTRY live turns: [('turn-2', None)]`
    `WAIT (no timeout) still pending after 2.0 s`
  Failure: Take a review that Codex finishes before it is registered, which is the D-23 fast path the read-back exists for, and give it any non-Codex fault while its snapshot is built, such as a stored item the translator cannot map or a status value outside `CodexTurnStatus`. The outcomes:
    - `start_codex_review` raises a raw RuntimeError instead of a packet-shaped `CodexAgentError`.
    - The turn is registered with no snapshot, and its notifications are already unregistered, so nothing ever ends it.
    - `wait_codex_turn(handle)` never returns, which breaks INV-14 "returns for every turn the host registered".
    - Every later `start_codex_review`, spawn, continue or `forget_codex_turns` on that thread is refused `codex.session_busy` until the host closes.
    - For a late review (`_adopt_late`, reviews.py:101, `spawn_task(self._accept(..., late=True))`), the raise dies inside a background task. The host logs nothing, and only asyncio's "Task exception was never retrieved" report remains, which carries the exception text outside the INV-10 contract.
  This is exactly the outcome request.md X3 names ("turns can end up stuck as RUNNING"). It also violates NFR-1's weighted words "exception handle everything that could potentially go wrong" ("Zero exceptions escape … a loop callback"). The S3 report did not note it.
  Smallest fix: Wrap the `finish` at reviews.py:141 in `try: … except Exception as exc: events.fail(turn, exc)`. This means renaming `CodexTurnEvents._fail` to a public `fail`, or adding a public one-line alias. The path then ends `FAILED` `codex.protocol_mismatch` with `CODEX_HOST_EVENT_FAILED_MESSAGE`, as INV-11 and INV-12 do. Add one AC-9-family test that applies the two patches above, then asserts that the start returns a handle, the unbounded wait returns `failed`/`codex.protocol_mismatch`, and a second review is accepted.
  Spec IDs: NFR-1, INV-14, INV-12 (by analogy), FR-8, X3 (request.md §C.9), AC-9 (does not cover it)

R-C2 [Major] [spec conformance / unreported deviation] vidbyte/harnesses/native/codex/connection.py:342 — A cancelled call, and a spending start that is handed over, write no INV-7 record, although INV-7 says "exactly one"
  Evidence:
  - INV-7 (spec.md:255) says: "Each call through `CodexConnection.call` or `CodexConnection.start` emits exactly one record."
  - `call` catches only `except Exception as exc:` (connection.py:342), so `asyncio.CancelledError` skips `_log_call`.
  - `start` has `except asyncio.CancelledError: self._hand_over(future, on_late, thread_id); raise` (connection.py:399-401). Neither `_post_late` nor `_land` (connection.py:453-465) logs.
  - The connection.py FILE header at line 7 adds a carve-out that the spec does not contain: "a call refused for that reason sent nothing, so it writes no log record, and neither does a cancelled call". Neither the S3 report §5 nor the spec's "Implementation deviations (S3)" list mentions it.
  - An in-process probe held each method in the fake, cancelled the caller, released the hold and drained the loop. It printed:
    `thread/read sent: 1 records: []`
    `turn/start sent: 1 records: []`
  Failure: A caller that times out or cancels `spawn_codex_thread`, `continue_codex_thread` or `start_codex_review` while its `turn/start` or `review/start` is in flight leaves no `codex_host_call` record of that start, on either the cancellation or the late landing. The start is spending, so Codex accepted it and it uses quota, and an operator reading the INV-7 log cannot see it. The same holds for any cancelled typed read or raw call that was already sent. FR-3 (P0, "One DEBUG or WARNING record per app-server call") is not met on these paths. AC-18 tests only a completed and a failed call, so no test catches it.
  Smallest fix: In `_land`, log the late outcome with `_log_call`: DEBUG on success, WARNING with the mapped code on failure. The `started` time is passed through `_hand_over`. In `call`, add `except asyncio.CancelledError:` that attaches the same done-callback logger to the executor future before re-raising. If the carve-out is intended, amend INV-7 and list it under "Implementation deviations (S3)" instead. Either way, the code and the spec must say the same thing.
  Spec IDs: INV-7, FR-3, X2 (request.md §C.9), AC-18 (does not cover it)

R-C3 [Minor] [user decision D-31] vidbyte/harnesses/native/codex/preflight.py:205 — Part of a user-facing message is a literal in the native host
  Evidence: `named = CODEX_HOST_LIST_SEPARATOR.join(sorted(names)) if names else "any model"`. INV-47 (spec.md:466-470) says "Every new table, bound, field rule and message text lives in `vidbyte.lib.constants.codex_host`". The deviation is recorded in spec.md:1621 and S3 §5, so it is disclosed. But C021 cannot see a call-site literal, and the user's #1055 comment ("wrong file location, put inside of lib") is about exactly this kind of placement.
  Failure: The words of the `CODEX_HOST_UNKNOWN_TIER_MESSAGE` refusal are split between lib and the native host. A future text edit to the lib table misses this slot, and the next reviewer applying D-31 flags it again.
  Smallest fix: Add a `CODEX_HOST_ANY_MODEL_TEXT = "any model"` constant to `vidbyte/lib/constants/codex_host.py` (with `__all__`), import it by name, and bump the §8.4 config-key count from 9 to 10. Alternatively, amend INV-47 to name this exception explicitly.
  Spec IDs: INV-47, D-31, NFR-11

R-C4 [Minor] [spec conformance] vidbyte/harnesses/native/codex/host.py:696 — NG-13 says the row-26 gaps "are documented as limitations", but no docstring documents them
  Evidence: The spec (spec.md:102) says: "NG-13 — Images, mentions or several skills per `run_codex_skill` (row 26). … They are documented as limitations." `run_codex_skill` (host.py:696) and `run_codex_openai_docs` (host.py:707) have no docstring. A search with `grep -n -i "image\|mention\|one skill\|several skills"` over host.py, skill_functions.py and codex_host_inputs.py returned nothing. FR-36 and AC-39 list NG-5…NG-12 and NG-20, but not NG-13, so no test pins it.
  Failure: A developer reading `run_codex_skill` is not told that images, mentions and more than one skill per run are unsupported. NG-13's own condition for deferring row 26 is therefore unmet.
  Smallest fix: Add a one-line docstring to `run_codex_skill` (and to `run_codex_openai_docs`, which runs a skill too) that names the limitation. Optionally add NG-13 to FR-36 so AC-39 pins it.
  Spec IDs: NG-13, FR-36, row 26 (request.md §C.9)

VERIFIED CLAIMS:
1. §8.4 budget (S3: "budget used exactly"): 3 new files (reviews.py, turn_events.py, lib/util/exception_origin.py), 13 new classes matching the §8.4 list, 0 dependencies, 9 config keys. HELD.
2. §12.3 coverage (S3: "all 24 rows built"): `git diff --name-only` minus docs and tests gives 24 files, which are exactly the §12.3 rows. HELD.
3. No guard-rail edits: the diff under lint, .semgrep, scripts and .github is 0 lines, and `git diff fadec47f..c9150d63 -- tests` is 0 lines. The fadec47f test corrections are narrow (`endswith("thread_id")`, and the filter covers only TransportClosedError). HELD.
4. Texts verbatim: all 12 §9.2 messages and every changed text match the spec, and the two approval constants were removed. Values: grace 0.5, review read-back limit 1, `notLoaded`, `default`, `currentTime/read`. Retryable codes are exactly api_error, response_invalid, session_busy, thread_resume_failed and usage_limited. `client_version` is "0.163.0", and pyproject pins `openai-codex>=0.163.0,<0.164.0`. HELD.
5. AC-1 is proved by its test: `CodexApprovalSnippetTests` runs the §4 `snippet_main` and `answer` verbatim against the fake and asserts the decision, the reviewer and one start and one close. The test can fail. HELD.
6. AC-22 and INV-28: the experimental gate sends zero requests, the fork order is record → gate → reviewer → thread read → preflight → scan → fork, as the text states, and the injected params are asserted. §5 diagram versus the call path: they match. HELD.
7. INV-4 and INV-6 (errors.py `_rpc_code`): thread/read is not found only when refused, and turn/steer is not found when `refused and not malformed`. HELD.
8. X8 and INV-23: the tool `_run` wraps the whole `_perform` coroutine, logs `codex_host_tool_failed` and returns codex.api_error. HELD.
9. File sizes: host.py 923, connection.py 556, wire.py 797, dataclasses/codex_host.py 871, reviews.py 150, turn_events.py 152. All are well under 1,000 lines, and host.py is under 940. HELD.
10. S3 results: the area suite gives 1 failed (the inherited harness_threads test), 1024 passed, 3 skipped, and lint gives `SDK-LINT: PASS`. Reproduced exactly. HELD.
11. INV-14, "waiting always ends for every turn the host registered": the already-ended review path leaves the turn RUNNING (R-C1 probe). DID NOT HOLD.
12. INV-7, "exactly one record per call through call or start": a cancelled call and a handed-over start write none (R-C2 probe). DID NOT HOLD.
13. HEAD e7fd9289 differs from c9150d63 only in docs/spec/codex-host-hardening/pipeline.md, so the reviewed commit is the code at HEAD. HELD.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) "$V" -B -m pytest tests/features/codex_host tests/test_codex_*.py -q -p no:cacheprovider` → `589 passed, 1 skipped in 23.01s`
- `"$V" lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS` / `LINT EXIT=0`
- `PYTHONPATH=$(pwd) "$V" -B -m pytest <codex area + tests/features/harness_threads> -q -p no:cacheprovider` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1024 passed, 3 skipped in 64.64s` (the inherited failure, which is not relitigated)
- `git diff origin/ai/resolve-pr-1055-comments...c9150d63 -- lint .semgrep scripts .github | wc -l` → `0`
- `git diff fadec47f..c9150d63 -- tests | wc -l` → `0`
- `git diff --name-only c9150d63 e7fd9289` → `docs/spec/codex-host-hardening/pipeline.md`
- `git diff --name-only --diff-filter=A origin/ai/resolve-pr-1055-comments...c9150d63 -- vidbyte` → reviews.py, turn_events.py, lib/util/exception_origin.py
- `git diff --name-only origin/ai/resolve-pr-1055-comments...c9150d63 | grep -v "^docs/\|^tests/" | wc -l` → `24`
- `wc -l host.py connection.py wire.py reviews.py turn_events.py lib/dataclasses/codex_host.py` → `923 / 556 / 797 / 150 / 152 / 871`
- Probe 1 (R-C1), run in-process through stdin with `"$V" -B -` (HostTestCase plus the fake; patches `stored_turn` to return a completed turn and `turn_snapshot` to raise) → `FIRST REVIEW raised: builtins RuntimeError` / `SECOND REVIEW raised: CodexAgentError codex.session_busy` / `FORGET raised: CodexAgentError codex.session_busy` / `REGISTRY live turns: [('turn-2', None)]`
- Probe 2 (R-C1, same setup, with an unbounded `wait_codex_turn` under a 2.0 s outer bound) → `WAIT (no timeout) still pending after 2.0 s`
- Probe 3 (R-C2: hold `thread/read` and `turn/start`, cancel the caller, release, drain) → `thread/read sent: 1 records: []` / `turn/start sent: 1 records: []`
- `grep -n -i "image\|mention\|one skill\|several skills" host.py skill_functions.py codex_host_inputs.py` → no output
- No probe wrote a file, ran pip or the real `codex`, or enabled `VIDBYTE_CODEX_LIVE_TESTS`.
