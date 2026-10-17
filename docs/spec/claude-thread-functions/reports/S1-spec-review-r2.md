VERDICT: SOUND WITH FIXES — r2 resolves R-1, R-3, R-5 and R-7 to R-11 cleanly, but four gaps remain. R-4 is only half-fixed: the shared helper ships with one caller while an identical copy stays in Grok. R-2's new leaf helper creates a zero-headroom mypy trap. R-6's memory text misstates fork isolation and the caller's off switch. One row text contradicts R-1. All four are text fixes to the spec; none changes a settled decision.

WHAT THE SPEC GETS RIGHT
- The merge-base formulation of R-3 is robust. `git merge-base origin/main HEAD` is `72a4ade1` now and becomes the merged main commit after the catch-up merge, so every byte-identity rule stays true across that merge. Rows 1–11 match `git diff --name-status 72a4ade1 HEAD` exactly: 7 modified and 21 added files outside docs and tests, plus 14 test files. #1095 touches none of the files this spec edits except `vidbyte/lib/enums/__init__.py`.
- The permission-mode text now matches the headless docs word for word. `dontAsk` "denies every call that would otherwise prompt". `acceptEdits` auto-approves file writes plus "`mkdir`, `touch`, `mv`, and `cp`", and "other shell commands and network requests still need an `--allowedTools` entry". "In a `-p` run with no host, these requests are denied either way." A-2 is confirmed, and INV-18 holds against the enums header rule 1.
- The wire's complexity margin is real. Ruff counts `if` statements, not `and`/`or` or conditional expressions; it measures `GrokWire.read` at 9 and `MuseWire.read` at 10, and row 20 specifies 7 `if`s, so C901 is 8. INV-6's fallback thread id also works: `NativeErrorFactory.failure` uses `request.thread_id` whenever `thread_id` is `None`.
- `NATIVE_STDIN_PROMPT_HARNESSES = {OPENCODE, CLAUDE}` leaves Grok, opencode and Muse exactly as they are (native_threads.py:91 and :101 key on `OPENCODE` today). `NativeHarness.CLAUDE = "claude"` plus `RUN_CLAUDE_THREAD = "run_claude_thread"` satisfies `check_error`'s harness and operation lock, and `"claude_code"` stays refused (records:97).

FINDINGS

R-12 [Major] [L4] D-15, NG-13, §2, §12.3 rows 25 and 32, §14 — The new hostkit helper has one caller while an identical copy stays in Grok, so the logic still exists twice
  Evidence: D-15 says "Grok's `_prepare_home` is not switched in this PR (NG-13)". Row 32 says "Body = `GrokThreadRun._prepare_home` (`grok/threads.py:134-152`) with its constants turned into the keyword parameters … Grok keeps its own copy". §2 says "written once for any harness that needs it", which is not true under NG-13. AGENTS.md principle 5 says to write the logic once as a canonical helper "and have every caller use that helper instead of re-implementing the job inline", and "if one is close, add the option you need to it rather than copying it into a variant beside your feature". The hostkit header (`hostkit/__init__.py:7`) says "Plumbing that a second harness needs goes here". NG-13 cites "Do not rewrite untouched code just to make it conform", but this PR derives the helper from Grok's method, so the PR itself creates the duplicate. The field-guide rule "Leave converging the two to a PR about that feature" (`review-scope.md`) applies only "When: A reviewer says a feature … should not be in this PR", and no reviewer said that. The switch is also test-safe:
    - `git grep _prepare_home 72a4ade1 -- tests` is empty.
    - Grok's folder and errors are pinned by `conftest.private_home` (:62-66), `test_unpreparable_private_home_is_launch_failed` (launcher:243) and `test_undeterminable_user_home_is_launch_failed`. The last one patches `pathlib.Path.home`, which the helper calls in the same way.
    - `GROK_PRIVATE_HOMES_PARTS` and `GROK_HOME_KEY_HEX_CHARS` are pinned in the surface test's `CONTRACT_CONSTANTS` and stay as the arguments Grok passes.
  Failure: The diff shows `hostkit/folders.py` as a near-copy of grok/threads.py:134-152, and its own header says that Grok keeps a copy. This is the duplication principle 5 forbids, and it is the convention comment the @claude review is built to raise. r2's middle path pays for a new module and still keeps the duplicate, so it is worse than both alternatives. r1's private copy in Claude is R-4 itself.
  Smallest fix: Switch Grok in this PR. This is not scope-adding: it changes no behavior, control, constant, text, test or public name, and AGENTS.md principle 5 requires it.
    - Add one P3 row for `vidbyte/harnesses/native/grok/threads.py`, after row 22 and independent of rows 18–21.
    - In that row, `execute` step 2 becomes `await asyncio.to_thread(NativePrivateFolders.prepare, request, errors, parts=GROK_PRIVATE_HOMES_PARTS, key_hex_chars=GROK_HOME_KEY_HEX_CHARS, skills_dir=GROK_SKILLS_DIR, unknown_detail=GROK_HOME_UNKNOWN_DETAIL, failure_detail=GROK_HOME_FAILURE_DETAIL)`.
    - The same row deletes `_prepare_home` and the now-unused `hashlib`, `os` and `NativeSkillFolders` imports, and updates the header FUNCTION INVENTORY and ROLE.
    - Delete NG-13. Make D-15's runner-up (b) the decision.
    - Add one sentence to INV-20: Grok's home is prepared by the shared helper with its existing constants, giving the same folder, errors and texts.
    - Widen §14's hostkit exception to this one call-site change.
    - Name both callers in rows 25 and 32. §2's "written once" then becomes true.
    - §8.4 is unchanged (no new file).

R-13 [Major] [L8] §12.3 row 20, §12.4 — Moving the exit-0 checks into `_missing_member` leaves `ClaudeWire.read` with no type narrowing, so the design as written adds 4 mypy errors against S009's zero headroom
  Evidence: Row 20's design:
    - Step 6: `_missing_member` "returns the first bad member … `CLAUDE_RESULT_FIELD` when `result` is not a `str`".
    - Step 7: `NativeErrorFactory.wrong_thread(request, session)`, whose parameter is `answered: str` (hostkit/errors.py).
    - Step 8: `text=result[:NATIVE_RESULT_TEXT_MAX_CHARS], text_truncated=len(result) > cap`.
    S009 runs `mypy --config-file lint/mypy.ini vidbyte` (lint/core/mypy.py:56) with `check_untyped_defs = True`, and its count is 350/350. A scratch probe with row 20's shape, checked under lint/mypy.ini, reports 4 errors:
    - `Argument 1 to "wrong_thread" has incompatible type "str | None"`
    - the same error for the result's thread id
    - `Value of type "object" is not indexable`
    - `Argument 1 to "len" has incompatible type "object"`
    `_error_text` has the same gap: it hands the `errors` member (type `object`) to `NativeErrorFactory.listing(items: Iterable[str])`. `GrokWire.read` avoids all of this because its `isinstance` checks sit inline (grok/wire.py:63-68). §12.4 names S009 as a zero-headroom ratchet but gives no check for it.
  Failure: S3 builds row 20 as written, lint reports S009 above 350, and the gate fails. The quick repairs are each bad:
    - a `cast` is a type lie that review flags;
    - re-checking in `read` spends the C901 margin that R-2 bought;
    - `str(result)` hides a protocol error.
  Smallest fix:
    - In row 20 and §8.5, make the leaves return typed values: `_session -> str | None` (as now) and a new leaf `_text(answer) -> str | None`, which returns `result` when it is a `str`.
    - `read` then has one check, `if answer.get(CLAUDE_IS_ERROR_FIELD) is not False or session is None or text is None:`, which raises `PROTOCOL_MISMATCH` with `missing_member=ClaudeWire._missing_member(answer, session, text)`. mypy narrows both values after the raise. The probe gives 0 mypy errors, and `read` keeps C901 = 8.
    - `_error_text` uses the `errors` member only when it is a `list`.
    - Add a §12.4 line: "S009: `python lint/run.py --rule S009` reports no more than 350."
    - `_text` is a helper, not a class, so the §8.4 budget is unchanged.

R-14 [Major] [L5] D-22, EC-37, FR-3, A-14, §9.1, T-4, Q-8 — The R-6 disposition is honest about INV-3, INV-4 and INV-14, but four statements around it are wrong or missing
  Evidence: The spec says:
    - D-22: "It also breaks no stated invariant … memory adds persistence, not a new channel".
    - FR-3: "the source is unchanged (p06)".
    - EC-37, A-14 and §9.1: memory lives in `projects/<mangled cwd>/memory/`.
    - T-4: "no shared store".
  The memory docs (code.claude.com/docs/en/memory) say:
    - "The `<project>` path is derived from the git repository, so all worktrees and subdirectories within the same repo share one auto memory directory."
    - "Both are loaded at the start of every conversation."
    - "When you ask Claude to remember something … Claude saves it to auto memory."
    - "To disable auto memory via environment variable, set `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`."
  D-6 and AC-6 drop every inherited `CLAUDE*` name except `CLAUDE_CODE_GIT_BASH_PATH`.
  Failure:
    (a) Notes saved during `fork_claude_thread(..., "Try it with argparse instead.")` load into the next `continue_claude_thread` of the source. The source's transcript is unchanged, but its next turn is not, and that undercuts the reason to fork.
    (b) A developer who exported `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` has it silently dropped by D-6. `--setting-sources user` also stops the workspace's `autoMemoryEnabled` from being read, so the caller has no off switch at all; deleting the folder is the only remedy.
    (c) For a workspace inside a git repository, the README's path to `memory/` is wrong.
    (d) Two callers that pass different keys for one workspace path share memory automatically, with no thread id needed. That contradicts T-4.
  No INV-* breaks once INV-14's r2 scope sentence is accepted, and fork still does what KD-5 says (copy, run, new id). So under the user's no-scope-additions rule the switch stays optional; the fix is text only.
  Smallest fix:
    - FR-3 and EC-37: "the source's transcript is unchanged; auto-memory notes the fork saves reach the source's later turns". Qualify D-22's "breaks no stated invariant" to match.
    - EC-37, D-22 and README row 29: state that the SDK drops an inherited `CLAUDE_CODE_DISABLE_AUTO_MEMORY`.
    - Change the path to `projects/<git repository root, else the workspace>/memory/`.
    - T-4: the per-workspace folder is a store shared by every caller of that workspace path.
    - Restate Q-8 with (a) and (b) as its stakes. Q-8 stays [scope-adding], optional, default no. If the owner says yes, the build is one overlay entry and one `NativeEnvironmentVariable` member.

R-15 [Minor] [L9] §12.3 rows 23 and 32 — Two r2 row texts invite a wrong edit
  Evidence: Row 23 rewrites the `wrong_thread` comment to "Grok, opencode and Claude Code fold the case of a thread id". After R-1, Claude never folds case: `_session` refuses any id outside the lowercase pattern before `wrong_thread` runs (INV-12, AC-13). Row 32 says to import "`NativeErrorFactory` from `.errors`". S040 bans relative imports (TID252, baseline 0, CLEAN), and hostkit/launcher.py imports `vidbyte.harnesses.native.hostkit.errors` with an absolute path.
  Failure: A maintainer who trusts the comment "fixes" Claude to accept upper-case ids, which reopens R-1. A literal `from .errors import` fails S040.
  Smallest fix: Row 23: "Grok and opencode fold the case of a thread id; Claude Code ids reach this compare already checked as lowercase UUIDs by ClaudeWire." Row 32: "`NativeErrorFactory` from `vidbyte.harnesses.native.hostkit.errors`".

VERIFIED CLAIMS
- Round 1, all checked against r2:
  - R-1: resolved in AC-3, INV-12, AC-13 and §13 (continue_upper_id is Grok-only: threads:136-142, fake_harness:313). Row 23 still drifts (R-15).
  - R-2: resolved for C901. It introduced the S009 trap (R-13).
  - R-3: resolved. No remaining byte-identity rule or restore instruction is tied to `base_commit` (grep of the spec).
  - R-4: half-resolved (R-12).
  - R-5: resolved; the docs quotes held.
  - R-6: documented, but incomplete (R-14).
  - R-7 to R-11: resolved (INV-21 order, EC-31, EC-36, row 33, §12.5/§14 baseline, T-6/A-15/Q-9, Q-1).
- D-15 premise: Grok's private-home constants equal Claude's except the noun. `GROK_SKILLS_DIR = "skills"`; `GROK_HOME_KEY_HEX_CHARS = 16`. `GROK_HOME_FAILURE_DETAIL` uses `{home}`, `{error_type}`, `{reason}`; `GROK_HOME_UNKNOWN_DETAIL` uses `{error_type}` (constants:113-115, 325-326). HELD.
- No test references `_prepare_home`, and the Grok home path and errors are pinned by tests (R-12 evidence). HELD, so the Grok switch is test-safe.
- Zero-headroom ratchets, measured with `lint/run.py --rule <id> --format json` at HEAD: S008 19/19, A007 255/255, S015 13/13, S017 79/79, S019 5/5, A006 34/34, C006 104/104, C008 45/45, S051 259/259. A001 is 640/642, A002 578/703, S040 0, S052 0. #1044's Claude files contribute 0 findings to every one of these, so P1 frees no headroom. Grok, hostkit and the native records also contribute 0, so code that copies their patterns adds none. HELD.
- A007: uppercase constants are exempt and no specified body uses a numeric literal; `key_hex_chars` splits to "chars", not "char". C008: no new name matches the validator grammar. HELD.
- C901 thresholds: ruff defaults (C901 > 10, PLR0912 > 12, PLR0915 > 50). Measured GrokWire.read = 9 and MuseWire.read = 10; `or` is not counted. Row 20's ClaudeWire.read gives 8. HELD.
- S009 runs mypy over all of `vidbyte` with `check_untyped_defs`. Row 20's shape type-checks cleanly. NOT HELD (R-13).
- `NativeErrorFactory.failure(thread_id=None)` falls back to `request.thread_id`, and `NATIVE_TESTED_VERSIONS[harness]` feeds the protocol-mismatch sentence. HELD (INV-6).
- `FailureCode`'s last member is `MUSE_WSL_UNAVAILABLE` (failure.py:172). The surface test's `PROBLEMS` order equals `NativeThreadProblem` order equals §8.5 order. HELD (INV-21).
- `ClaudePermissionMode` has no approve-everything member (enums header line 8, rule 1). vendor-facts §2 lists `default` as a hidden alias (f2), and `auto` and `bypassPermissions` are excluded. HELD.
- Auto memory per the docs: on by default, `MEMORY.md` loaded each session (200 lines or 25 KB), excluded from the `cleanupPeriodDays` sweep, turned off by `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. HELD. The folder is keyed "<mangled cwd>": NOT HELD inside a git repository (R-14).
- Static policy (`test_harness_threads_static_policy.py`): its `rglob` covers `hostkit/folders.py`; the specified bodies use only `""` (bool constants are skipped) and have no module-level statements. HELD.
- C016 covers only the root `__all__` and `pyproject.toml`, and `scripts/test-session-failure-vocabulary.py` is not in `run_ci.py`. HELD (§9.4, NG-11).
- Layering: `folders.py` importing `hostkit.errors` and `hostkit.skills` makes no cycle; `launcher.py` already imports `hostkit.errors` directly. HELD (A006).
- §8.4 budget (4 files, 8 classes) matches §8.5 and §12.3, and `vidbyte.harnesses.native.__all__` has 17 names at the merge base. HELD.
