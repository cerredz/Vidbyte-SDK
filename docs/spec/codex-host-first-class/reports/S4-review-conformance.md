LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — slice 2 matches the spec on every table, text, budget, order and boundary checked. The exception is `create_codex_worktree`, which lets a raw `FileExistsError` (or `PermissionError` or `RuntimeError`) reach the caller, against INV-2's "Every failure … is one of two kinds".

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **The moves are faithful.** The D-1/D-2 moves (`_guard`, `_owned` into `host_core.py`; the six start helpers into `turn_starts.py`) keep each body byte-identical. The only addition is the allowed mode-model check. A request without `collaboration_mode` produces a `turn/start` param dict byte-identical to the old `TurnStartParams` dump, sandbox defaults included (NFR-10, INV-48).
- **The texts and values are verbatim.** All 46 message/cause/next-step texts of §9.2 and §9.3 match the constants, as does every non-message value and table: the 9 unmodeled methods, `SPENDING_RAW`, the RESUME==CONTINUE rejected-field rows, the review tail, `GIT_NO_PROMPT_ENV` as a mappingproxy, and archive/unarchive not retried. The §8.4 budget is met exactly: 13 files, 69 classes, 0 dependencies, 46 config keys, 42 endpoints. So are the INV-50 orders: 25 operations between `FORGET_CODEX_TURNS` and `LAUNCH_CODEX_SUBAGENTS`, 12 after `START_CODEX_REVIEW`, 28 public methods on `CodexHost` and 25 inherited.
- **The gate is placed as INV-4 asks.** `require_experimental_api` sits directly after the input record in all 11 INV-4 functions (`settings_methods.py:74,105,129,186,213,227,239`, `thread_methods.py:251,265,281,295`) and once in `CodexPreflight.run` for a mode (`preflight.py:97`). Every stable function is ungated.
- **The side chat and the plan run follow the spec.** The side-chat flow matches §5's sequence diagram: the fork's resolved reviewer is checked inside `fork(..., starts_turn=True)` before the handler is shared, then the boundary is injected and the turn starts on the fork. The side-chat tool forces READ_ONLY plus DENY_ALL on both the thread and the turn view. `run_codex_plan` follows INV-16 step for step (`skill_functions.py:176-195`).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [conformance: weighted word, user's words, §5] vidbyte/harnesses/native/codex/thread_methods.py:162-166 — create_codex_worktree lets a raw OSError or RuntimeError reach the caller
  Evidence: the three filesystem steps run outside any mapping:
    `root = Path.home().joinpath(*CODEX_HOST_WORKTREE_ROOT_PARTS)` (:162)
    `if target.exists():` (:164)
    `root.mkdir(parents=True, exist_ok=True)` (:166)
  Probe `scratchpad/s4-slice2/probe_worktree_oserror.py` reuses `CodexWorktreeHostTests` (real git, `Path.home` patched) with `<home>/.vidbyte` written as a regular file, then calls `host.create_codex_worktree(repo, "feat/x")`. Output:
    `PROBE RAISED: builtins.FileExistsError: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\...\\home\\.vidbyte'`
  Neither §12.3 row 28 nor §5 has the `mkdir` step. §5 says the worktree branch returns "CodexWorktree, or a configuration.invalid_argument packet".
  Failure: the probe's input (`~/.vidbyte` is a file) gives a bare `FileExistsError` with the full home path in its text, not a packet. A read-only home, as in many containers, gives a raw `PermissionError` from `mkdir`. A denied `stat` gives one from `exists()`. An unresolvable home gives a `RuntimeError` from `Path.home()`. Callers that catch `ConfigurationError | CodexAgentError`, as INV-2 promises they may, crash.
  Smallest fix: wrap lines 162-166 in `try: … except (OSError, RuntimeError): raise CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, <root-unusable message>, operation, likely_cause=…, next_step=…) from None`. This needs one new message/cause/next-step triple in `vidbyte/lib/constants/codex_host.py`, which names the `~/.vidbyte/codex-worktrees` root and not the absolute path. Do not simply delete the `mkdir`. I checked real git 2.49: `git worktree add` makes the leading folders itself, but when it cannot, it exits 128 *after* creating the branch (`feat-y` stayed in `git branch --list`). That would break INV-29's "refused before git runs".
  Spec IDs: INV-2, FR-28, INV-29, §5 (worktree branch), §12.3 row 28; request.md §A Prompt 2 "exception handle everything that could potentially go wrong"

R-C2 [Minor] [conformance: NG-19, §12.3] vidbyte/harnesses/native/codex/host.py:347,749 — slice-1 reviewer refusal restyled outside §12.3 and not recorded as a deviation
  Evidence: in `continue_codex_thread` and `_open_thread`, `git diff a7730107...8ea8734f -- vidbyte/harnesses/native/codex/host.py` shows
    `-            if self._approval_handler is None and self._responses.routes_to_user(resumed):`
    `-                raise CodexErrorMapper.reviewer_refusal(operation, thread_id)`
    `+            self._preflight.reject_routed_reviewer(operation, thread_id, self._responses.routes_to_user(resumed))`
  Row 30 lists "No public method is added, removed or reordered" and the moves, but not this edit. Row 23 and D-36 introduce `reject_routed_reviewer` for the side-chat fork only. The S3 report's 13 deviations do not mention it.
  Failure: there is no behavioural failure. `approvals_answered=handler is not None` (`host.py:202`) makes the refusal identical. It is an unlisted edit to slice-1 code that NG-19 forbids unless §12.3 lists it.
  Smallest fix: record it as deviation 14 in spec §17 (S3 row) and the S3 report, since it is the canonical-helper move AGENTS.md §5 favours. Alternatively, revert the two call sites to the inline check.
  Spec IDs: NG-19, §12.3 row 30, §17

R-C3 [Minor] [conformance: deviation 5] vidbyte/harnesses/native/codex/thread_methods.py:295 — the child-thread gate tells the developer that thread/list itself is experimental
  Evidence: `self._preflight.require_experimental_api(operation, CODEX_THREAD_LIST_METHOD)` formats `CODEX_HOST_EXPERIMENTAL_FEATURE_MESSAGE` as "list_codex_child_threads needs Codex's experimental API for thread/list, …". `list_codex_threads` (slice 1) sends the same `thread/list` on a host with `experimental_api=False`. Only the injected `parentThreadId` / `ancestorThreadId` are experimental (spec line 277, D-24).
  Failure: on a host opened with `experimental_api=False`, `list_codex_child_threads(t)` names the wrong feature. A developer reading it would think `list_codex_threads` is gated too.
  Smallest fix: pass the experimental field as the feature word, for example `"parentThreadId"`, and update deviation 5's bullet. The tests pin only the message template and `details["field"]`.
  Spec IDs: INV-4 (feature argument), D-24, §17 deviation 5

VERIFIED CLAIMS:
1. AC-1, the §4 snippet: run verbatim against the fake app-server, it prints the two plan lines, `['completed', 'completed']` and `['docs', 'github']`. HELD (1 passed).
2. §9.2/§9.3 texts and values verbatim (probe_messages.py): 46 texts, 0 mismatches; every config value and table correct. HELD.
3. NFR-10 / INV-48, `turn_start` byte-identical without a mode (probe_turn.py, against the old `TurnStartParams` dump). HELD.
4. §8.4 budget:
   - 13 new files: 8 native, 3 lib, 2 tools.
   - 69 new classes: 70 added `class` lines minus the re-declared `CodexHost`. That is 11 native + 1 lib helper + 14 records + 17 inputs + 10 enums + 16 tools.
   - 46 config keys: 47 added non-message constant names minus `CODEX_HOST_GOAL_REJECTED_FIELDS`, which was modified, not added.
   - 0 dependencies. 42 endpoints: 25 methods + 1 field + 16 tools.
   HELD.
5. INV-50 orders (probe_order.py): 25 operations between FORGET and LAUNCH; 12 after START_CODEX_REVIEW; 28 public methods defined on `CodexHost` and 25 inherited; MRO `CodexHost, CodexSettingsMethods, CodexStreamMethods, CodexThreadMethods, CodexGoalMethods, CodexHostCore`. HELD.
6. INV-53 export lists: `native/codex/__init__.py` and `lib/dataclasses/codex_host.py` `__all__` untouched; `lib/process/__init__.py` changed only in its header text. HELD.
7. INV-47 / NFR-1 ceilings:
   - host 786 ≤ 900; wire 839 ≤ 840; `dataclasses/codex_host` 891 ≤ 900; inputs 779 < 900.
   - The largest new module is 362 lines, under 600.
   - `dataclasses/codex.py` and `constants/codex.py` are unchanged.
   HELD.
8. §12.3 coverage: all 39 `vidbyte/` files in the diff map to a §12.3 row, including `lib/README.md`, `lib/process/__init__.py` and `tools/builtins/__init__.py`. HELD at file level. One unlisted edit inside a listed file is R-C2.
9. §14 "Never":
   - `git diff a7730107...8ea8734f -- lint/` is empty, and no commit touches a baseline.
   - `git diff e3d41513..8ea8734f -- tests` is empty, and the only 4 commits touching `tests/` are S2's `test(...)` commits.
   - The lint loop ends `SDK-LINT: PASS`.
   HELD.
10. INV-4: the gate comes right after the record in all 11 functions, and the mode gate is in `run`. HELD.
11. INV-2 on every new-method path: FAILED on the worktree path (R-C1, probe output above). The other paths map through `CodexErrorMapper` or record `ConfigurationError`. `_resume_now`'s bare SDK `CodexError` (`turn_starts.py:211`) is raised inside `connection.start`, which maps it to `codex.api_error`.
12. D-1/D-2 moves byte-identical (NG-19 exception). HELD.
13. The 13 §17 deviations:
   - 1 (`thread/goal/set` naming): necessary, because `test_codex_host_goal_control.py` and the `feature_contract` row require it. Minimal and recorded.
   - 2 (`_change_idle`), 3 (suppressed cancel), 4 (`None`-only defaults), 6 (`TypeError` on an unknown delta, shown as a GAP), 7, 8, 9, 10, 11, 12 and 13: minimal, recorded, and none changes a specified behaviour.
   - 5: the `run_codex_plan` part is fine; the child-thread word is R-C3.
   - The reviewer restyle is a 14th change, unrecorded (R-C2).
   HELD apart from R-C2 and R-C3.
14. The fix choice for R-C1: real git 2.49 makes the worktree's leading folders itself, but it leaves the new branch behind when it cannot (exit 128, `feat-y` listed). So the `mkdir` must stay, wrapped. VERIFIED.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) "$V" -m pytest -q tests/features/codex_host/test_codex_host_first_class_snippet.py -p no:cacheprovider` → `1 passed in 1.37s`
- `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1293 passed, 3 skipped in 100.71s`. The one failure is inherited (167 != 120), not slice 2's.
- `"$V" lint/run.py` → `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`
- `git diff --stat a7730107...8ea8734f -- lint/` → (empty)
- `git diff --stat e3d41513..8ea8734f -- tests` → (empty)
- `git log --oneline a7730107..8ea8734f -- tests` → `32e1a404`, `893f1df4`, `ab13e1e7`, `fa27a3ad` (all `test(codex-host)`, S2)
- `git diff --name-status a7730107...8ea8734f -- . ':!docs' ':!tests'` → 39 files (13 A, 26 M), each in §12.3
- `wc -l <17 files>` → host 786, wire 839, codex_host 891, inputs 779, features 354, modes 93, feature_wire 362, goal_methods 172, host_core 117, settings_methods 245, stream_methods 73, thread_methods 320, turn_starts 258, turn_stream 277, git_worktree 61, controls 206, thread_actions 303
- `git diff a7730107...8ea8734f -- vidbyte | grep -E '^[-+](    )?class '` → 70 added, 1 removed (`class CodexHost:` re-declared with its bases)
- Count of added non-message constants in `vidbyte/lib/constants` → 47 names, with `CODEX_HOST_GOAL_REJECTED_FIELDS` the one removed and re-added (46 new)
- `"$V" scratchpad/s4-slice2/probe_order.py` → `between FORGET and LAUNCH: 25` / `after START_CODEX_REVIEW: 12` / `public methods defined on CodexHost: 28` / `inherited public: 25`
- `"$V" -m pytest -q -s scratchpad/s4-slice2/probe_worktree_oserror.py -k probe` → `PROBE RAISED: builtins.FileExistsError: [WinError 183] Cannot create a file when that file already exists: '...\\home\\.vidbyte'` / `9 passed`
- `git -C <scratch repo> worktree add -b feat-y -- <home2>/.vidbyte/codex-worktrees/repo-feat-y HEAD` with `.vidbyte` a file → `fatal: could not create leading directories of '...': Not a directory` / `exit=128`; `git branch --list` → `feat-y` present
- `"$V" scratchpad/s4-slice2/probe_messages.py`, `probe_wire.py`, `probe_turn.py` (earlier in this review) → 46 texts, 0 mismatches; sandbox and turn_start dumps identical
