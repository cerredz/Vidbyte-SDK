LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the PR does what the user asked and meets the spec on every P0 path I checked, including the §4 snippet run against an independent stand-in; one avoidable error-detail gap (output_too_large drops stderr) should be closed first.

Reviewed: `git diff origin/main...0a2752dd` (merge base `b28c3027`; origin/main has since moved to `c04e5ef5`, which leaves the three-dot diff unchanged). HEAD `dd5db847` differs from `0a2752dd` only in `docs/spec/claude-thread-functions/pipeline.md`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- The user's request is met end to end. The §4 snippet, taken verbatim from spec.md, prints exactly `claude True True` and then the fork's answer. I ran it against my own stand-in `claude.exe`, which shares no code with the test pack's `fake_harness.py`. The argv in each call is exactly the AC-5 form: `--print --output-format json --setting-sources user --permission-mode acceptEdits`, then `[--model sonnet] [--resume <id>] [--fork-session]`. The prompt arrives only on stdin, and the child's working folder is the resolved workspace.
- The key isolation holds in a hostile environment, not only in the sandbox. My run inherited the agent shell's 12 real `ANTHROPIC_*`/`CLAUDE*` variables, including a real `ANTHROPIC_API_KEY`, `CLAUDE_CONFIG_DIR`, `CLAUDECODE` and `CLAUDE_CODE_MESSAGING_TOKEN`. The child saw exactly `ANTHROPIC_API_KEY` (the digest of the caller's fake key), `CLAUDE_CONFIG_DIR` (`<tmp home>/.vidbyte/claude-configs/e3a70a5a2403e685`, which equals my own computation of sha256(normcase(resolved ws))[:16]), `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` and the kept `CLAUDE_CODE_GIT_BASH_PATH`, plus `DISABLE_AUTOUPDATER=1` (INV-4, INV-17, AC-6). The user's real `~/.vidbyte/claude-configs` was never created.
- Scope and removal are exact. 21 code files changed, and they are exactly the §12.3 rows. `pyproject.toml`, `vidbyte/tools/`, `vidbyte/lib/errors/__init__.py`, `lint/`, `vidbyte/lib/configs/`, root `vidbyte/__init__.py` and `contracts/` are byte-identical to `b28c3027`. Every #1044 module, folder and name is gone, and `git grep claude_agent_sdk -- vidbyte pyproject.toml` is empty. Of the sibling harnesses, only `grok/threads.py` changed: `_prepare_home` was lifted into `NativePrivateFolders.prepare` with Grok's own constants, and the method body matches line for line with the constants turned into parameters (INV-19, INV-20, AC-20).
- The public surface matches #1036 for all four harnesses ("Whatever you choose should apply to all four harnesses"). All twelve functions are coroutines with the identical `(thread_id,) prompt, *, api_key, workspace, model, skills=(), config=None` shape. `vidbyte.harnesses.native.__all__` has 23 names. `FailureCode` has 148 + 9 members, in §8.5 order after `MUSE_WSL_UNAVAILABLE`. `import vidbyte` leaves the native package unloaded (INV-1, INV-2, INV-21, INV-22, AC-18).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [deviations / user's words] vidbyte/harnesses/native/claude/wire.py:43-44 — `claude.output_too_large` throws away the stderr that every sibling harness attaches, and §17 records this as a deviation it did not need
  Evidence: wire.py:44 `raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)`, with no `vendor_text`. Every sibling passes it: grok/wire.py:44, opencode/wire.py:64, muse/wire.py:99 and :154 all have `vendor_text=outcome.stderr`. My direct probe of `ClaudeWire.read`, with `CliOutcome(stdout="{", stdout_truncated=True, stderr="Claude Code: output limit notice")`, printed `d output_too_large w/ stderr: claude.output_too_large thread_id=None vendor=None`. spec.md:788, §17 deviation 3, says "unlike Grok, no stderr text is attached". In fact Claude is unlike all three siblings.
  Failure: a run whose stdout passes 64 MiB while Claude Code explains the cause on stderr. The error's message and `vendor_message` lose that text, and the developer sees only the byte cap. INV-6 lists "the scrubbed and capped vendor text" as an element of every Claude error message, and G-4 asks for "the same detail as #1036's harnesses". KD-6 cites the owner's resolved #1036 comment "error messages need to be in much more detail". Row 20 step (2) only fails to list `vendor_text`; it does not forbid it, and INV-6 and G-4 outrank it. So the deviation was neither necessary nor minimal.
  Smallest fix: add `vendor_text=outcome.stderr` to the wire.py:44 call. Then delete §17 deviation 3, or reword it to say the gap was closed. No test pins the absence: `test_stdout_past_the_cap_is_output_too_large_naming_it` calls `check_error` without `vendor=`, so it keeps passing.
  Spec IDs: INV-6, G-4, FR-11, AC-10 (message elements), §17 deviation 3

R-C2 [Minor] [snippet and diagram] docs/spec/claude-thread-functions/spec.md:172 (INV-11) — "No other program is started" is false on the win32 timeout and cancel path. The code is right; the spec text is wrong.
  Evidence: vidbyte/lib/process/runner.py:118 `asyncio.create_subprocess_exec(program, *native_threads.NATIVE_TASKKILL_ARGUMENTS, str(pid), ...)`. INV-9 requires this tree stop through `ProcessStopper`, so a Claude call that times out or is cancelled on Windows also starts `taskkill.exe`. taskkill inherits only the caller's `os.environ`, never the overlay, so the key does not reach it. The user's weighted words "Each call runs `claude` once, headless" therefore hold on every path. Only the spec's stronger restatement does not.
  Failure: a reader, or the S6 PR body if it quotes INV-11, states a guarantee the code cannot keep without breaking INV-9.
  Smallest fix: in spec INV-11, add "apart from the tree stop's `taskkill` on win32 (INV-9)". No code change.
  Spec IDs: INV-11, INV-9, NFR-1

VERIFIED CLAIMS:
- AC-1, by my own run of the spec §4 text against an independent stand-in: HOLDS. Exactly `claude True True` / `answer to: Try it with argparse instead.`, 3 child starts, one per call.
- AC-5 argv order, the permission-mode value, stdin-only prompt and cwd: HOLDS (stand-in log).
- AC-6 / INV-4 with the real inherited agent environment (12 names): HOLDS. Only `CLAUDE_CODE_GIT_BASH_PATH` was kept.
- INV-13 folder formula: HOLDS (`e3a70a5a2403e685` computed independently). AC-9 shared folder: one `CLAUDE_CONFIG_DIR` across run, continue and fork, `skills/` = `["write-tests"]`.
- S3 "4 new files, 8 classes, `claude/*.py` = 360 lines": HOLDS (22 + 190 + 148). NFR-3 ≤ 400 holds. NFR-7: constants file 518 ≤ 600. README 13,772 characters ≤ 40,000.
- §8.4: 0 dependencies (`pyproject.toml` identical), 0 config keys, 0 collections, 3 functions plus 3 re-exports: HOLDS.
- S3 "changed files outside docs/spec and tests are exactly §12.3": HOLDS (21 files, all listed). This equals the test's `ALLOWED_CHANGED`.
- S3 "no stage-3 commit touches tests/": HOLDS (`git log --no-merges 3839c7bc..0a2752dd --not origin/main -- tests` is empty). Every existing-test change is in test-plan.md's "Changes to existing tests" list: surface/errors/static_policy pins, conftest, the stand-in roles, the pack's FEATURE/README, and the 140cc2fa fix. No assertion was removed from a Grok, opencode or Muse test.
- S3 did not edit request.md, context/ or pipeline.md (only the orchestrator's commits touch them). S3's spec.md edits are only `status: implemented` and §17.
- `lint/` diff empty; no `noqa`, `type: ignore`, `pragma`, `nosec` or `cast(` added under `vidbyte/`.
- INV-21 against `b28c3027` explicitly: `failure.py` diff is only the nine appended `CLAUDE_*` lines; `len(FailureCode) == 157`. HOLDS.
- INV-20: only `grok/threads.py` differs among grok/opencode/muse (`git diff --stat b28c3027 0a2752dd`). The helper body is identical to the old `_prepare_home` with the constants turned into parameters. The full pack is green. HOLDS.
- INV-1 / INV-2 / INV-22 by `inspect`: HOLDS. `ClaudeThreads`, `ClaudeThreadRun`, `ClaudeWire`, `ClaudeFlag` and `NativePrivateFolders` are not exported from the native package or root `vidbyte`.
- INV-6 / INV-7 / INV-12 on paths the tests do not reach, probed directly through `ClaudeWire.read`: HOLD.
  - A fork answer with no session reports the source id.
  - A continue that gets a 401 answer on another session is key_rejected with the caller's id.
  - A run answer with an upper-case session is protocol_mismatch with thread_id None.
  - Exit 1 with a well-formed success JSON is run_failed carrying stderr and Claude's session.
  - A continue answered on another valid id is thread_not_found with the caller's id.
  - A continue that times out keeps the caller's id and stderr.
- §17 deviation 1 (newest id): necessary, minimal and recorded. INV-6 ("a failed continue reports the caller's id") outranks row 20's literal `thread_id=session`.
- §17 deviation 2 (`_missing_member` keeps an unused `text` parameter): recorded, and it follows the §8.5 signature. Not a conformance defect.
- §17 deviation 3: not necessary (R-C1). Its record is also inaccurate ("unlike Grok"; it is unlike all three siblings).
- §17 deviation 4 (README/REPO_MAP "plumbing" wording): necessary, because "the three" became false, and minimal.
- Unreported deviations: none found. I checked rows 13–34 symbol by symbol, including the `@intent` placement, the narration, the header items row 19 lists, the row 23 comment text, the hostkit export order and the Grok imports removed.
- AC-23: HOLDS. The README covers the three functions, `ClaudeThreadConfig`, the key rule, `--setting-sources user` and EC-9, EC-10 and EC-30. It covers what each permission mode allows in a headless call (EC-20), EC-21, EC-22, EC-28, EC-37 (fork notes, the dropped inherited switch, the git-repository naming), T-4 and the native `claude.exe` requirement. REPO_MAP names the functions, `~/.vidbyte/claude-configs/` and the setting-sources consequence.
- Row 16 likely-cause and next-step content against the spec's per-code list: HOLDS for all nine codes, and each text is unique.
- request.md §A/§C: every "What #1044 would become" bullet is built. The "Deleted" list is fully removed. Nothing from §3 or the Q-n list is built: no `--session-id`, no `CLAUDE_CODE_MAX_RETRIES`, no memory switch, no extra config fields, no `NoDefaultCurrentDirectoryInExePath`, no composition functions. The one change the user did not ask for is the Grok switch (row 34). AGENTS.md principle 5 requires it (D-15, R-12), and it is behaviour-preserving, so it is not scope creep.
- Spec §5 against the actual call path: the order is the same, `_call` → `NativeLauncher.resolve` → `NativePrivateFolders.prepare` via `to_thread` → `register_secret` → `CliRunner.run` → `ClaudeWire.read`. Three divergences are documentation-only:
  - (a) The flowchart has no failure edge from `prepare` (claude.launch_failed raised at threads.py:98-107).
  - (b) A runner launch failure is raised in `execute` through `from_launch_failure` (threads.py:127-129), not in the wire. The flowchart's only F edge goes to G.
  - (c) `register_secret` is not drawn.
  The §5 prose below the diagrams covers (a) and (b).
- CI on cf9c541d, which holds the same code as 0a2752dd: Package, Static policy, Source 3.11 and Source 3.12 are all `completed success`. The briefing's "Source still running" is now stale.
- FR-15: every module header that counts the harnesses names Claude Code. A note for the conventions lens: the inline comment at vidbyte/lib/dataclasses/native_threads.py:127-128, "Grok and Muse take an optional bare model id", now also applies to Claude Code.

FOLLOW-UPS (not defects of this PR)
- Q-1 is still unanswered by the user: should the input be one dataclass per call, for all four harnesses? S6's PR body should put it to the owner, together with Q-8 (auto memory).
- PR #1044 is non-draft but titled `[WIP] …`. S6 should drop the prefix when it finalises the body.

COMMANDS RUN:
- `git merge-base origin/main 0a2752dd` → `b28c3027aafd…` (origin/main `c04e5ef5…`).
- `git diff --stat origin/main...0a2752dd -- . ':!docs'` → `38 files changed, 2532 insertions(+), 121 deletions(-)`.
- `git diff --name-status origin/main...0a2752dd` (code paths outside tests and docs) → the 21 §12.3 files.
- `git diff --stat origin/main...0a2752dd -- pyproject.toml vidbyte/tools vidbyte/lib/errors/__init__.py lint/ vidbyte/lib/configs vidbyte/__init__.py contracts/` → (empty).
- `git log --no-merges --oneline 3839c7bc..0a2752dd --not origin/main -- tests` → (empty).
- `git grep -n claude_agent_sdk 0a2752dd -- vidbyte pyproject.toml` → (empty). The #1044 paths all report `absent`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ -k claude` → `195 passed, 437 deselected in 33.67s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/` → `630 passed, 2 skipped in 83.23s`. This is the pack alone; the briefing's 668 included main's two extra test files.
- The §4 snippet, extracted from spec.md with only the two paths swapped, run in a child Python with PATH = the stand-in folder only, HOME/USERPROFILE = a temp home, `MY_ANTHROPIC_KEY=sk-ant-test-0000`, and the shell's real `CLAUDE*`/`ANTHROPIC*` variables inherited → `exit 0`, `STDOUT: 'claude True True\nanswer to: Try it with argparse instead.\n'`, plus the stand-in log quoted above.
- A direct `ClaudeWire.read` probe with 12 crafted `CliOutcome`s → the results quoted under R-C1 and in VERIFIED CLAIMS.
- `python -m ruff check vidbyte/harnesses/native/claude … --isolated --select C901,PLR0912,PLR0915` → `All checks passed!`. With max-complexity 7: `C901 read is too complex (8 > 7)`, which confirms complexity 8.
- `diff <(git show b28c3027:vidbyte/lib/enums/failure.py) <(git show 0a2752dd:…)` → only the nine `CLAUDE_*` lines are added.
- `gh api repos/cerredz/Vidbyte-SDK/commits/cf9c541d/check-runs …` → Package, Static policy, Source / Python 3.12 and Source / Python 3.11 are all `completed success`.
- Not run, as the briefing says: `scripts/run_ci.py`, `lint/run.py`, and the real `claude`.
