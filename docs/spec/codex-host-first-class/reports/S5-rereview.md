LENS: re-review (conformance + conventions + engineering, focused on the repair diff)
VERDICT: MERGEABLE AFTER FIXES — every repair is correct, pinned by a test that fails when it is reverted, and free of regressions, but R-1 is not closed at its root: `create_codex_worktree` still lets a raw `PermissionError` reach its caller through the repository record (INV-2), so one one-line Blocker fix remains, plus two Minors.

Scope: `git diff 8ea8734f...ec17d5ce -- vidbyte/` (11 commits, 22 files) plus the S2 tests of `9ad2771e`. HEAD `e736c93f` differs from `ec17d5ce` only under `docs/` (`git diff --stat ec17d5ce HEAD -- vidbyte tests lint` is empty), so every line number below is the reviewed code.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-3's `_fits_alone` is the spec-correct variant, not just an equivalent one.** It applies the host bound only once the log is attached (`turn_stream.py:247`), which is what INV-20 says ("A log that was never attached has the per-turn bounds only"). Both of the following leave the turn's window unchanged:
  - an event over the turn bound, which skips the loop and then fails `_fits`;
  - an event over the host bound on an attached log.

  The verifier's inline form would refuse to evict for an unattached log whose host bound is below the turn bound, even though that log has no host bound. At the shipped constants (2,000,000 per turn, 32,000,000 per host) the two forms are identical.
- **R-4 partitions the resume failures exactly as INV-31 r6 does:**
  - no cancel when `reserve_goal_operation` or `activate_turn_routing` fails (`turn_starts.py:206-209`);
  - a cancel from `sent = True` onward (`:210`), unless the failure is a `JsonRpcError` (`:218`).

  In openai-codex 0.163, `JsonRpcError` is raised only from a server `"error"` answer (`_message_router.py:267-276` via `map_jsonrpc_error`). So a pydantic failure, `TransportClosedError` or the elapsed window all cancel, and a refusal never does. The cancel lives in one `except` and runs at most once. `connection.start` calls `on_late` only on success, so a failed resume is never cancelled a second time.
- **R-5 keeps the R-14 posture and every other field.**
  - The resets are spread after the explicit narrowing keywords (`thread_actions.py:128`, `:130`), and no reset name collides with them.
  - The test compares the whole request to an oracle built from a test-side literal row (`assertEqual(request, _side_chat_view(defaults))`).
  - Dropping the thread posture kills 5 tests.
- **R-1's handler is shaped exactly as r6 says.**
  - `_guard` sits outside the `try` (`thread_methods.py:160`), so EC-3 keeps its own path.
  - The `CodexAgentError` of the existing-folder refusal passes through the handler.
  - Nothing is logged, the error is raised `from None`, and `mkdir` still runs before git.
  - Each of the three root failures now gives a typed packet with no branch and no request (verifier probe).

FINDINGS (ranked, most severe first, max 15)
R-RR1 [Blocker] [conformance + engineering; pre-existing since S3, so R-1's root is not closed] vidbyte/lib/dataclasses/codex_host_inputs.py:589-592 (with vidbyte/lib/dataclasses/validation.py:133) — `create_codex_worktree` still lets a raw `PermissionError` reach the caller, because the repository record's `is_dir()` re-raises a refused `stat` and the record catches only `ConfigurationError`. This violates INV-2 r6 ("No … `OSError` … ever reaches the caller").
  Evidence:
  - **The record.** `codex_host_inputs.py:589-592` reads:
    ```
    try:
        repository = RecordFieldValidator.require_directory(RecordFieldConverter.to_path(self.repository, "repository"), "repository")
    except ConfigurationError:
        raise ConfigurationError(CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE, ...) from None
    ```
    `validation.py:133` reads `... or not value.is_dir():`. The record is built at `thread_methods.py:161`, outside R-1's `try` (`:166-177`).
  - **Python 3.11's `Path.is_dir`** re-raises every `OSError` except the ignored errnos. The venv prints `pathlib._IGNORED_ERRNOS = [2, 9, 20, 10062]` and `_IGNORED_WINERRORS = (21, 123, 1921)`, so EACCES (13) and ERROR_ACCESS_DENIED (5) propagate. `pyproject.toml:10` says `requires-python = ">=3.11"`, with classifiers 3.11 and 3.12.
  - **Probe.** `scratchpad/s5-rereview/probe_rr_repo_stat.py` uses real git and the real host, and simulates only the one refused `stat`, as the S4 verifier simulated `mkdir`. It printed:
    - `RRPROBE repo-stat-refused: builtins.PermissionError typed=False: [Errno 13] Permission denied: 'C:\\Users\\422mi\\AppData\\Local\\Temp\\tmpnn56qsca\\repo\\locked\\inner'`
    - `RRPROBE branches: ['master'] sent: [] logs: []`
  - **The S4 review's own premise was wrong.** It said lines 162-166 are "the only raw-exception gap on this path". A grep of the new records and mixins for `is_dir`, `exists`, `resolve` and `to_folder` finds only this call and `target.exists()`.
  Failure:
  - **Input:** `create_codex_worktree("/srv/team/repo", "feat/x")`, where `/srv/team` is mode 0700 and owned by another user (POSIX), or the folder's ACL denies read-attributes (Windows).
  - **Wrong outcome:** an untyped `PermissionError` whose text holds the absolute path, instead of §9.1 record 9's `ConfigurationError(CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE)` ("must be the absolute path of an existing folder").
  - **Why it is Blocker:** the user's weighted words are "exception handle everything that could potentially go wrong" (request.md §D). S4 held this same class at Blocker (R-1).
  Smallest fix:
  - **Code:** one token at `codex_host_inputs.py:591`, `except (ConfigurationError, OSError):`. It raises the same message `from None`.
  - **Not the canonical helper:** widening `RecordFieldValidator.require_directory` in `validation.py` instead would be outside §12.3 (the same reason m-7 used).
  - **S2 regression row:** patch `pathlib.Path.stat` to raise `PermissionError(13, "Permission denied", str(path))` for the repository path. Expect:
    - `ConfigurationError` with `CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE` and `details["field"] == "repository"`;
    - `__cause__ is None`;
    - no path canary in the message;
    - an unchanged branch list and no request.
  - **Spec:** no change. §9.1 row 9 and INV-2 already require this.
  Spec IDs: INV-2, INV-29, §9.1 record 9 (`CodexWorktreeRequest`), FR-28, request.md §D

R-RR2 [Minor] [conventions] vidbyte/tools/builtins/codex/thread_actions.py:57, :116-127 — The side-chat reset copies `ResumeCodexGoalTool._resume_defaults` line for line, and `THREAD_FIELD_PREFIX = "thread."` is now defined in two sibling tool modules. The new comment also misstates the continue tool.
  Evidence:
  - **The copy.** `thread_actions.py:123-127` repeats `skill_functions.py:325-329` (tools layer) step for step: `fresh, fresh_thread = CodexSpawnRequest(), CodexThreadSettings()`, the `paths` row, `thread_names = [path.removeprefix(THREAD_FIELD_PREFIX) ...]` and the two `getattr(fresh…)` dicts.
  - **The constant twice.** `grep -rn '"thread\."' vidbyte/` shows `skill_functions.py:53` and `thread_actions.py:57`.
  - **The comment.** It says the fields are "read from the host's own table as the continue and resume tools do" (`:118-119`). But `ContinueCodexThreadTool._continue_defaults` (`threads.py:204-216`) hand-lists its fields and reads no table.
  Failure: AGENTS.md §5 says "write the logic once as a canonical helper … and have every caller use that helper instead of re-implementing the job inline". This job now exists three times (continue, resume, side chat), two of them copy-pasted. A reviewer would write "lift this into `_CodexHostTool`". AGENTS.md §2 also asks that comments never describe behaviour that is not there. The implementer rejected importing the constant across sibling modules (verify-log R-5) but did not consider the shared parent, `_base.py`.
  Smallest fix:
  - Add one static helper to `_CodexHostTool` in `vidbyte/tools/builtins/codex/_base.py` (§12.3 row 31 already MODIFY), for example `_reset_to_fresh(defaults, paths) -> CodexSpawnRequest`, with the prefix constant.
  - Have `_resume_defaults` and `_side_chat_defaults` call it, and delete both module constants.
  - Reword `:118-119` to "as the resume tool does".
  - There is no behaviour change, and the existing argument tests pin both views.
  - If the orchestrator rules against a new helper, fix only the comment.
  Spec IDs: n/a (INV-43 is satisfied)

R-RR3 [Minor] [conformance; fixer: spec] docs/spec/codex-host-first-class/spec.md:373 (INV-20 "What is dropped"), :797 (D-39) — INV-20 still describes the pre-fix drop order for an oversize event, so the corrected code contradicts INV-20's literal text, and no deviation records it.
  Evidence:
  - **INV-20 today:** "When a new event would pass a per-turn or a per-host bound, the recording log drops its own oldest events until it fits. When it keeps nothing older and the new event still does not fit, the new event is dropped." For an event that never fits, that literally means evict everything, which is what the pre-fix loop did.
  - **D-39 today:** "drops its own oldest events, then the new one."
  - **The review asked for the sentence.** `review.md` R-3, "Smallest fix" cell: "**spec:** one INV-20 sentence, 'an event that alone passes a character bound is dropped at once, without dropping older events'".
  - **It was never added.** `git diff 8ea8734f HEAD -- docs/spec/codex-host-first-class/spec.md | grep '^[+-].*\(INV-20\|EC-19\|D-39\)'` shows only the §8.4 config-key row. r6 and r7 never touched INV-20, D-39 or EC-19. The briefing's "spec r6: INV-20 and D-39" does not hold.
  - **The code cites INV-20 anyway.** `turn_stream.py:144`, `:246` and the new test (`test_codex_host_stream_wait.py`, `# EC-19, INV-20 (review R-3)`) cite INV-20 for behaviour that only EC-19 states.
  Failure:
  - **The risk:** a later implementer or reviewer who applies INV-20 as written removes `_fits_alone` and re-opens EC-19. The regression row would catch it, but only by contradicting the invariant it cites.
  - **Why the code is right:** EC-19 ("Subscribers see `GAP(dropped=1)` in its place") is the more specific rule.
  Smallest fix (spec author, docs only):
  - In INV-20's "What is dropped", add: "An event that alone passes a character bound (the turn's, or the host's once the log is attached) is dropped at once, and no older event is dropped for it (EC-19)."
  - Append the same clause to D-39's last sentence.
  Spec IDs: INV-20, D-39, EC-19

VERIFIED CLAIMS: <each claim checked and whether it held>
- **R-1: CLOSED for the three steps it names; NOT CLOSED at its root (R-RR1).**
  - **Code:** `thread_methods.py:166-177` matches spec r6 INV-29, EC-63 and row 28 word for word (the r6 triple is verbatim at `codex_host.py:578-580`, in sorted `__all__`).
  - **Verifier probe:** all three cases (`FileExistsError`, `RuntimeError`, `PermissionError`) now give `typed=True … configuration.invalid_argument`, with `branches: ['master'] sent: []`.
  - **Test vs revert:**
    - `R1-revert` (handler removed) is killed;
    - `R1-no-oserror`, `R1-no-runtimeerror` and `R1-chained` (`from exc`) are each killed by `test_a_worktree_root_that_cannot_be_prepared_…`.
  - **Other `RuntimeError` sources inside the `try`:** only `Path.home()` (and the theoretical `RecursionError`), so nothing is wrongly mapped.
  - **`OSError` outside the `try`:** the repository record (R-RR1). `GitWorktreeSpec`'s relative-path message carries no path.
- **R-2: CLOSED.**
  - The awk check over all 38 `vidbyte/*.py` changed since `a7730107` prints nothing.
  - `wire.py` is 839/840.
  - The `@intent` rename is unreferenced.
  - No test is possible (docs).
- **R-3: CLOSED in code; the spec half is NOT done (R-RR3).**
  - **Verifier stream probe:** `[oversize] kept after oversize: (3, 3)`, with kinds `… 'message_delta' ×3, 'gap', 'message_delta' …`.
  - **Test vs revert:**
    - `R3-revert` (the pre-fix loop) and `R3-alone-ignores-turn` are killed by `test_an_oversize_event_costs_a_lagging_subscriber_only_its_own_gap` (`1 failed, 455 passed`).
    - `R3-alone-ignores-host` survives the whole `tests/features/codex_host` directory (`598 passed, 1 skipped`). It is an equivalent mutant at the shipped constants: no event can pass the 32,000,000 host bound without also passing the 2,000,000 turn bound. So it is not a finding.
    - `R3-verifier-variant` also survives, as expected.
  - **Residual, spec-sanctioned:** an event that fits alone, on a host whose bound other turns fill, still evicts its own log's events before it is dropped too. EC-62 and D-39 prescribe exactly this, and the implementer weighed it (verify-log). It is not a finding.
- **R-4: CLOSED.**
  - **Verifier probe:** goal `paused`, turn statuses `['completed', 'interrupted']`, goal-op calls `['cancel_goal_operation', 'finish', 'unregister_goal_operation']`, `interrupts: 1`, host not busy.
  - **Test vs revert:**
    - `R4-revert` (`sent` after `activate`) is killed by `test_a_resume_set_codex_applied_but_answered_badly_is_cancelled_once_and_cleaned_up`;
    - `R4-no-jsonrpc-exemption` and `R4-always-cancel` are killed by `test_a_refused_resume_set_sends_no_cancel_and_still_cleans_up` (EC-37 sends no cancel);
    - `R4-never-cancel` is killed by the EC-64 and window-elapse tests.
  - **Transport failure:** a `TransportClosedError` is a `CodexError` and not a `JsonRpcError`, so it cancels (and the cancel is suppressed if it cannot be sent), as INV-31 r6 says.
  - **Exactly once:** the test asserts `START_FAILURE_CLEANUP` exactly, so there is one cancel.
- **R-5: CLOSED.**
  - **Verifier probe:** `side-chat tool with tools default: success`.
  - **Test vs revert:** `R5-revert`, `R5-no-thread-reset` and `R5-no-request-reset` are each killed by both new tests (argument and host). `R5-thread-posture-lost` is killed (5 failed).
  - **`READ_ONLY` and `DENY_ALL` are kept, and so is every other field (whole-record oracle).**
- **R-6 and R-7 (S2 tests): CLOSED.** All four rows pass. S2's report records the kills of S7, S3b and S3c, and the S3c and S3b messages are quoted in test-plan.md. R-3's revert mutant is caught by its own row, not by these.
- **R-8: CLOSED.**
  - **Count:** my own AST plus tokenize count gives all 25 public mixin methods 2-14 body comment lines; the 13 named methods have 3-6 each.
  - **Language:** plain English, step by step, each comment above its step group; I read all 13. INV citations follow the module's existing style.
  - **No test is possible.**
- **m-2: CLOSED.** The gate word is now the experimental filter key, through one `child_filter_key` (`feature_wire.py:239-243`).
  - **Call depth:** `child_threads` calls one same-class helper, and the mixin calls it across classes, so the depth is 1.
  - **§8.4:** functions are not counted there.
  - **Spec r7:** deviation 5 now matches.
  - **Test vs revert:** `m2-revert` SURVIVES (`598 passed`), so no test pins the gate word. The S4 m-2 row did not ask S2 for one, and it is Minor, so this is noted, not filed. `m2-swapped` is killed by `test_child_listing_names_the_parent_or_ancestor_and_every_source_kind`.
- **m-3: CLOSED.** In the venv, the six SDK enums are value-equal to ours apart from our empty member:
  - `ModeKind`, `McpAuthStatus`, `McpServerConnectionStatus`, `McpServerStatusDetail` and `TurnPlanStepStatus` all compare True;
  - `ThreadMemoryMode` equals `CodexMemoryMode` (`{'enabled', 'disabled'}`);
  - `TurnSettingsUpdateStatus` is absent (False).
- **m-4: CLOSED.**
  - Both headers name `CODEX_HOST_WORKTREE_FAILED_MESSAGE` as the one message that quotes stderr.
  - The root message names only the type (EC-63).
- **m-5: CLOSED.** The spec rows confirm each citation:
  - D-8 is the plan run, and D-16 is goal raw sets;
  - AC-11 is the missing plan preset;
  - EC-12 and EC-13 are the plan effort and model;
  - INV-29 is the worktree texts.
- **Other claims checked:**
  - **Area suite:** `1 failed, 1302 passed, 3 skipped`. The one failure is the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`). The implementer's figure holds.
  - **Lint:** `SDK-LINT: PASS`, with C021 CLEAN; A002 (582 vs baseline 703), S001 (56 vs 59) and S009 (346 vs 350) IMPROVED; nothing REGRESSED. `lint/` is untouched (the diff stat is empty).
  - **Test contract:** `git diff 25c2de9b ec17d5ce -- tests | wc -l` = 0.
  - **Scope:** every changed `vidbyte/` file maps to a §12.3 row; nothing is touched outside `docs/`, `vidbyte/` and `tests/`; no tracked `.pyc` or `__pycache__` file.
  - **Commits:** all 11 repair commits cite their finding ID and carry the Co-Authored-By trailer, and each `fix` commit touches only its finding's files.
  - **Line ceilings:** `thread_methods.py` 370/600, `codex_host.py` (constants) 764/900, `host.py` 786/900.

COMMANDS RUN: <each with its final lines>
- `git diff 8ea8734f...ec17d5ce -- vidbyte/` (read in full) and `git diff --stat ec17d5ce HEAD -- vidbyte tests lint` → `(empty)`
- `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1302 passed, 3 skipped in 90.87s (0:01:30)`
- `PYTHONIOENCODING=utf-8 "$V" lint/run.py` → `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS`
- `tr -d '\r' < f | awk 'length($0)>72 && /^[ \t]*#/'` over the 38 `vidbyte/*.py` changed since `a7730107` → no output, `files=38`. `wc -l` gives `wire.py` 839.
- Revert mutants, using `scratchpad/s5-rereview/rr_mutant.py` (in-memory rewrite plus `pytest.main`; no worktree file is edited):
  - `R1-revert`, `R1-no-oserror`, `R1-no-runtimeerror`, `R1-chained`, on `test_codex_host_worktree.py -k cannot_be_prepared` → each `1 failed, 13 deselected`
  - `R3-revert`, then `R3-alone-ignores-turn`, on `tests/features/codex_host -x` → `1 failed, 455 passed, 1 skipped` (stream R-3 row)
  - `R3-alone-ignores-host` and `R3-verifier-variant` → `598 passed, 1 skipped` (equivalent at the shipped constants)
  - `R4-revert` → `1 failed, 597 passed` (EC-64 row)
  - `R4-no-jsonrpc-exemption` and `R4-always-cancel` → `1 failed, 597 passed` (EC-37 row)
  - `R4-never-cancel` → `2 failed, 596 passed`
  - `R5-revert`, `R5-no-thread-reset`, `R5-no-request-reset` → `2 failed, 596 passed` each
  - `R5-thread-posture-lost` → `5 failed, 14 passed`
  - `m2-revert` → `598 passed, 1 skipped` (survives)
  - `m2-swapped` → `1 failed, 597 passed`
- `PYTHONPATH="$(pwd);<verifier dir>" "$V" -m unittest probe_v_worktree probe_v_engineering` → `Ran 16 tests … OK`. Its `VPROBE` lines are quoted above.
- `… -m unittest probe_v_stream` → `Ran 2 tests … OK` · `[oversize] kept after oversize: (3, 3)`
- `PYTHONPATH="$(pwd);scratchpad/s5-rereview" "$V" -m unittest probe_rr_repo_stat` → `RRPROBE python 3.11.0` · `EACCES ignored by is_dir: False` · `repo-stat-refused: builtins.PermissionError typed=False: [Errno 13] Permission denied: '…\\repo\\locked\\inner'` · `branches: ['master'] sent: [] logs: []`
- An AST plus tokenize narration count over the four mixins → `public methods: 25`, minimum `comments=2` (`set_codex_thread_memory_mode`, unchanged by R-8)
- An enum value comparison in the venv (m-3) → five `True`, `ThreadMemoryMode == CodexMemoryMode`, `TurnSettingsUpdateStatus` absent `False`
- `git diff 8ea8734f HEAD -- docs/spec/codex-host-first-class/spec.md | grep '^[+-].*\(INV-20\|EC-19\|D-39\)'` → only the §8.4 config-key row
- `git rev-list 3d285f78..ec17d5ce`, with the subject, trailer count and files of each commit → 11 commits, each with a trailer of 1
