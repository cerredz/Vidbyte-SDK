LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — all 47 functions match their §8.5 signatures and the §12.3 plan, but INV-29 fails on the plan/explore evidence path, Grok search breaks INV-7 uniqueness, and 16 tests fail in the user's own environment, where DEEPSEEK_API_KEY is set.

Reviewed: `git diff origin/main...462e6d45` (merge base 239c408a; HEAD 6eafd6c8 only adds docs). I read every changed source file whole. I also ran the area suite with and without DEEPSEEK_API_KEY, lint, the AC-1 snippet test, the INV-28 tests, and three stand-in probes (scripts in the session scratchpad `s4c-inv29/`).

WHAT THE IMPLEMENTATION GETS RIGHT
- Request fidelity and surface match the spec.
  - 47/47 new public functions match §8.5 by name: an ast probe shows no name in the code that is missing from the spec, or the reverse.
  - `vidbyte.harnesses.native.__all__` is 68 names, sorted. The subpackages export 25, 15 and 16.
  - Every §E.2 catalog row is either implemented or excluded in §3, and the README "Not offered" list names each exclusion.
- "Simply" and "extensively handle errors for every single function" both hold.
  - Every wrapper is 4 lines: decorator, def, docstring and one await of its own class's `_call` (NFR-9, INV-25).
  - Each of the 6 `_call`s is the one guarded try, in the order CancelledError, NativeThreadError, ConfigurationError, Exception.
- INV-26 holds and the plan was followed.
  - The only #1036 behaviour change is opencode `--command`, plus `stdin_text=prompt or None`, which is a no-op for #1036 prompts. The GrokHome and MuseChildren moves are value-identical.
  - §8.4 budget is exact: 10 new source files, 20 harness classes, 6 records, 6 enums, 0 dependencies. Every touched file maps to a §12.3 row (tests via row 38).
  - NFR-6 sizes hold: the largest new module is 366 lines; constants are 836 lines.
- §14 "Never" items hold.
  - `lint/baseline.json` is unchanged.
  - Nothing under `tests/features/harness_threads` changed after S2's 5180083f (`git diff --stat 5180083f 462e6d45` is empty).
  - Lint is green, and the AC-1 snippet equals the spec §4 text (ast-identical, 1195 characters) and passes.

FINDINGS (ranked)

R-C1 [Blocker] [INV-29 weighted "Every"] vidbyte/harnesses/native/grok/commands.py:243 — Plan/explore evidence-read failures lose the minted thread id
  Evidence:
  - After the stream is read, `GrokStore.thread(home, request, errors, thread_id=thread_id)` uses `thread_id` only to build the path.
  - `GrokStore._read` (store.py:221, :227) and `GrokHelperWire.thread_file` (wire.py:197, :199, and the member errors after them) call `errors.failure(..., request=request)` with no `thread_id`.
  - `request` is the run's `NativeThreadRequest` (verb RUN, `thread_id=None`), so the factory's fallback is also None.
  - Repro (stand-in grok that ends the stream on the minted `--session-id`, then leaves `{not json` as that id's `summary.json`):
    - `run_grok_plan` raised `FailureCode.GROK_PROTOCOL_MISMATCH thread_id= None`.
    - The same stand-in with `agent_name: "build"` raised `GROK_COMMAND_NOT_RUN` with the id.
  - The code-review export path was fixed for exactly this (deviation 2; `test_a_failed_code_review_export_carries_the_minted_id`). Plan and explore got no equivalent, and no test covers it.
  Failure:
  - INV-29 says "Every error raised after the child started carries that id in `error.thread_id`", and EC-50 says the point is "so the caller can read, continue or delete the paid thread".
  - A Grok `summary.json` schema drift (a field type, a timestamp format), a half-written file, or an unreadable folder makes every plan/explore call orphan a paid, existing thread, with no id to delete it by.
  - The same holds for the `store_unreadable` paths (store.py:180, :227). `_in_scope` returns before :205 for a run request.
  Smallest fix:
  - Thread a `thread_id: str | None = None` keyword through `GrokStore.thread` → `_directories`/`_in_scope`/`_read` → `GrokHelperWire.thread_file`/`_optional_text`, and pass it to each `errors.failure`. Helpers keep None; the run passes the minted id.
  - S2 adds a test: a stand-in with an `end` event and a malformed own `summary.json` gives `grok.protocol_mismatch` with `thread_id == minted(sandbox)`.
  Spec IDs: INV-29, EC-50, INV-5 ("thread id when known"), INV-8, D-29.

R-C2 [Major] [INV-7 uniqueness] vidbyte/harnesses/native/grok/helpers.py:157 — `search_grok_threads` matches before it dedupes, so it can return a stale copy that the list has replaced
  Evidence:
  - `matching = (found.summary for found in files if NativeThreadListing.matches(...))`, then `NativeThreadListing.newest(matching, ...)`. S3 reports this as deviation 7 ("Grok search matches before the dedupe").
  - Repro (one id `T1` under two groups; the older copy is titled "fix the login bug" on 10-02, the newer "write the docs" on 10-09):
    - `list_grok_threads` → `[('T1', 'write the docs', '2026-10-09')]`
    - `search_grok_threads(ws, "LOGIN")` → `[('T1', 'fix the login bug', '2026-10-02')]`
  - S2's oracle (test_harness_threads_listing_properties.py:56-66) dedupes first and then matches, so it expects `()`.
  - The property test cannot see the difference: `draw_store` gives every duplicate the same texts (line 51-52).
  Failure:
  - INV-7 applies to "every list and search helper": "A duplicate keeps the entry with the newer `updated_at`".
  - Search returns the older entry, with a stale title, `updated_at` and sort position, for a thread whose current record does not match. This is reachable through EC-17 (two encodings of one workspace, USER scope) and any SDK-scope id kept in two groups.
  Smallest fix:
  - Dedupe the `GrokThreadFile`s by id, keeping the newer `updated_at` (the rule `newest` already applies), before `matches`; or match on the winner of `newest`.
  - S2 makes one generated duplicate carry different texts so the property test can fail.
  Spec IDs: INV-7, EC-17, FR-9, AC-7.

R-C3 [Major] [test/impl contract split, NFR-10] tests/features/harness_threads/fake_harness.py:36 vs vidbyte/lib/constants/native_threads.py:453 — 16 helper tests fail whenever DEEPSEEK_API_KEY (or ZAI_API_KEY) is set, as it is on the user's machine
  Evidence:
  - `DEEPSEEK_API_KEY=x pytest tests/features/harness_threads` → 16 failed, 982 passed, 3 skipped. `env -u DEEPSEEK_API_KEY` → 998 passed, 3 skipped. The ambient shell here has DEEPSEEK_API_KEY set.
  - The failing assertion is `all(value is None for value in start["credentials"].values())`, for example at test_harness_threads_opencode_helpers.py:59. It checks all six `CREDENTIAL_NAMES`.
  - `NATIVE_HELPER_REMOVED_VARIABLES` removes only the four INV-2 names. The `sandbox` fixture (conftest.py:260-268) sets HOME, USERPROFILE and PATH but never clears credentials, so the pack is not hermetic.
  - S3 also wrote a new user-facing promise into vidbyte/harnesses/README.md:179: "other variables of your environment, such as `DEEPSEEK_API_KEY`, are inherited as by any child process". FR-20 never asked for it, and §17 deviation 13 reports only that the gates ran with the variable unset.
  Failure:
  - The implementation meets INV-2's enumeration and AC-10, but:
    - D-18 says "Helper children carry no key".
    - T-3 says "helper children strip all key variables".
    - S2's oracle reads it the same way, so the tie goes to the prosecution.
  - In practice, AGENTS.md's mandatory `python scripts/run_ci.py` is red in the user's normal shell. The S3 "green" gates (NFR-10, AC-22) were obtained only by changing the environment.
  Smallest fix:
  - Preferred: add `DEEPSEEK_API_KEY` and `ZAI_API_KEY` members to `NativeEnvironmentVariable` and to `NATIVE_HELPER_REMOVED_VARIABLES`. This is least privilege, still a superset of INV-2, and passes the pack in any environment. S2 updates the `NativeEnvironmentVariable` surface pin.
  - Delete the README "are inherited" sentence.
  - Either way, S2 makes `sandbox` delenv every `CREDENTIAL_NAMES` entry so the pack never depends on the runner's shell.
  Spec IDs: INV-2, D-18, T-3, NFR-2, NFR-10, AC-10, AC-22, FR-20.

R-C4 [Major] [EC-61 / INV-5 "thread id when known"] vidbyte/harnesses/native/muse/helpers.py:268 — Some Muse evidence-read failures drop the new thread's id
  Evidence:
  - `MuseHelperRun.tool_calls` (line 268) and `transcript` (line 286) open their config folder with `MuseChildren.open_config((), request, errors)`.
  - `_prepare_config` raises `launch_failed` with `request=request` only (children.py:131). `request` is the RUN request, whose `thread_id` is None.
  - `_export`'s `await asyncio.to_thread(target.parent.mkdir)` (helpers.py:333) has no handler, so an OSError there reaches `_call` as `runtime.error` through `from_unexpected(exc, request)`, also without the id.
  - The code comment at muse/commands.py:140 claims "every error from here on names the new thread". These paths contradict it.
  Failure: EC-61 says "Raises with the new thread id attached" when a skill's evidence read fails after the run succeeded. On these paths (temp folder full or unwritable), the caller gets no id for the paid thread the exec just created.
  Smallest fix:
  - Give `open_config`/`_prepare_config` a `thread_id: str | None = None` keyword passed to `errors.failure`.
  - Map the `mkdir` OSError in `_export` to a `launch_failed` carrying `thread_id`.
  - Or wrap the evidence block in `MuseCommandRun.execute` and re-raise with the id.
  Spec IDs: EC-61, INV-5, INV-8.

R-C5 [Minor] [spec text] docs/spec/harness-thread-helpers-skills/spec.md:352 — AC-22 and NFR-5 (line 492) name a lint banner the tool never prints
  Evidence: `python lint/run.py` ends `SDK-LINT: PASS` (exit 0). `grep -rn AGENT-LINT lint/*.py` finds nothing. request.md §C repeats "AGENT-LINT".
  Failure: read literally, AC-22 and NFR-5 can never pass. The intent (lint green, baseline unchanged) holds. Reported as deviation 11.
  Smallest fix: change "AGENT-LINT" to "SDK-LINT" in AC-22 and NFR-5.
  Spec IDs: AC-22, NFR-5.

R-C6 [Minor] [spec text vs design] vidbyte/lib/dataclasses/native_threads.py:374 — INV-18 "every existence check runs in to_thread" contradicts the prescribed record validation
  Evidence:
  - `GrokCommandArguments._checked_design_doc` calls `path.is_file()`, and `NativeHelperRequest` resolves and `is_dir()`-checks `workspace`. Both run in `__post_init__` on the event loop, inside `_call`.
  - This follows D-1 and INV-3 and the #1036 records. INV-18 and NFR-4, however, say every existence check is off-loop.
  Failure: the spec contradicts itself. The code follows the more specific design (D-1), so the risk is only that a blocking stat runs on a network path.
  Smallest fix: amend INV-18 to exempt boundary-record validation, as #1036 does; or check `design_doc` in `asyncio.to_thread` inside `_call`.
  Spec IDs: INV-18, NFR-4, D-1, INV-3.

VERIFIED CLAIMS
- AC-1: test_harness_threads_acceptance_helpers.py passes (4 passed). Its SNIPPET is identical to spec §4.
- §5 matches the real call path, including Grok argv `--output-format`, `--session-id`, `--cwd`, `--permission-mode`, [`--model`], [`--reasoning-effort`], [`--agent`] and `--single=` (JOINED). The one exception: the agent_name and code-review checks use `require_value` and `require_text`, not `require`.
- Proof references: all 78 named in the 34 AC rows exist as test functions.
- ID walk:
  - INV-1, 2, 8, 9, 11, 13, 14, 16, 17, 20, 21, 22, 23, 24, 25, 26, 27 and 28 hold, from the code and the passing suite.
  - INV-7 fails (R-C2), INV-29 fails (R-C1), INV-5 partly fails (R-C4), and INV-18 holds only as the spec's design allows (R-C6).
  - FR-1 to FR-20 hold apart from the README sentence (R-C3).
  - NFR-6 and NFR-9 hold. NFR-10 holds only with DEEPSEEK unset (R-C3).
  - Of the 81 EC rows, EC-17 (search) and EC-61 have gaps.
- PWD: `NativeEnvironmentVariable.PWD.value == 'PWD'` (deviation 9). The opencode helper child gets `PWD=ws` (EC-31).
- Deviation 3 (all four variables removed in every helper child) is a superset of INV-2 and conforms. Deviation 6 (`_call -> Any`) leaves every public annotation exact, so it conforms.
- Deviations 1, 2, 4, 5, 8, 10 and 12 conform. 7 holds for the Muse cut but not for the Grok search (R-C2). 11 is R-C5 and 13 is R-C3.
- Unreported deviations:
  - R-C1, R-C4 and the README promise in R-C3.
  - `OpencodeWire._unknown_command` (opencode/wire.py:153) does a substring match where D-8 says "starts with". This is benign.
  - `delete_*` wrappers use a bare `await`, not `return await`. This is benign.
- INV-28: tests/test_session_failures.py and tests/test_codex_failure_recovery.py pass (97 passed).
- The branch is current: `git log 462e6d45..origin/main` is empty (Prompt 5: "local main is up to date").

COMMANDS RUN
- `git diff origin/main...462e6d45 -- <each source file, README.md, REPO_MAP.md, lint/baseline.json>`
- `git diff --name-status --diff-filter=A origin/main...462e6d45`
- `git diff --stat 5180083f 462e6d45 -- tests/features/harness_threads`
- `git log --oneline 462e6d45..origin/main`
- `env -u DEEPSEEK_API_KEY $PY -m pytest tests/features/harness_threads -q -p no:cacheprovider` → 998 passed, 3 skipped
- `DEEPSEEK_API_KEY=x $PY -m pytest tests/features/harness_threads -q -p no:cacheprovider -rf` → 16 failed, 982 passed, 3 skipped
- `$PY -m pytest tests/features/harness_threads/test_harness_threads_acceptance_helpers.py -q -p no:cacheprovider` → 4 passed
- `$PY -m pytest tests/test_session_failures.py tests/test_codex_failure_recovery.py -q -p no:cacheprovider` → 97 passed
- `$PY lint/run.py` → `SDK-LINT: PASS`, exit 0; `git status --short` clean afterwards
- Scratchpad probes (`$PY <scratchpad>/s4c-inv29/...`), with HOME and USERPROFILE redirected to the scratchpad:
  - `repro.py` (INV-29)
  - `search_dupe.py` (INV-7)
  - `wrappers.py` (NFR-9, INV-25 and naming)
  - `ac_proofs.py` (AC proof references)
- `wc -l` on every touched file, and `grep` and `sed` reads of spec.md, request.md and test-plan.md
