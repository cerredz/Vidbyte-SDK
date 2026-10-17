VERDICT: SOUND WITH FIXES — The design is sound and closely grounded in vendor probes and #1036's code, but one acceptance criterion contradicts the specified wire reader. Several statements also drift from the code or the vendor docs, and these should be fixed before S2 writes tests.

WHAT THE SPEC GETS RIGHT
- The key isolation is grounded in probes. Inherited `ANTHROPIC_*`/`CLAUDE*` variables are removed through the existing `env_remove` (runner.py:278-279: `os.environ` minus `env_remove`, with the overlay on top). Each workspace gets a private `CLAUDE_CONFIG_DIR`, and `--setting-sources user` stops the workspace settings from loading (vendor-facts e2, e7, w2, k4, m2). §8.3 rejects the smaller design and names the concrete failure it would cause.
- The `--resume` title hazard (p13) is closed by the lowercase-UUID input pattern (D-8). The wire reader never judges an answer by `subtype` (p16).
- The spec mirrors the Grok sibling faithfully. Every reused signature it names matches the code (see VERIFIED CLAIMS). The deletion plan matches `git diff 72a4ade1 HEAD` exactly. Restoring from `72a4ade1` rather than from the moving `origin/main` is correct.
- The prompt goes on stdin and the pipe is closed (runner `_feed_stdin` writes, drains and closes, and the drains start first). The 200,000-character cap goes through a new `NATIVE_STDIN_PROMPT_HARNESSES` set, so Grok, opencode and Muse behave exactly as before.

FINDINGS

R-1 [Blocker] [L9/L10] §6.2 AC-3 vs §12.3 row 20 / INV-12 — A continue answered with an upper-case id cannot both succeed and be read by the specified `_session`
  Evidence: AC-3 (spec line 195) requires continue to succeed "also when the stand-in answers with the id in upper case". The stand-in's `continue_upper_id` mode returns `resume.upper()` (tests/support fake_harness.py:313). Row 20 defines `_session` as `session_id` only when `RecordFieldValidator.accepts_text(..., pattern=CLAUDE_THREAD_ID_PATTERN)` accepts it. That pattern is lowercase-only (`^[0-9a-f]{8}-…$`), and `accepts_text` uses a case-sensitive `re.fullmatch` (validation.py:120-127). An upper-case id therefore gives `None`, and step 6 raises `PROTOCOL_MISMATCH`. AC-13 itself says that a `session_id` "that is not a lowercase UUID" raises `protocol_mismatch`. That makes INV-12's "compared case-insensitively" unreachable.
  Failure: S2 writes the AC-3 upper-case test, the implementation built from row 20 fails it, and S3 cannot change tests, so the run ends BLOCKED. If S3 loosened `_session` instead, AC-13 would fail.
  Smallest fix: Delete "(also when the stand-in answers with the id in upper case)" from AC-3 and "compared case-insensitively" from INV-12. Any id outside the pattern is `claude.protocol_mismatch`, which matches A-4 and the input rule. Add one sentence telling S2 that `continue_upper_id` is Grok-only (test_harness_threads_threads.py:137-142) and is not applied to Claude.

R-2 [Major] [L8] §12.4 — The size budget omits lint S008, which has zero headroom, and the wire reader is specified at exactly the complexity ceiling
  Evidence: S008 (C901 > 10, PLR0912 > 12, PLR0915 > 50; selectors in lint/core/ruff.py) is ratcheted at 19/19 in lint/baseline.json. Measured: `GrokWire.read` has C901 = 9 and `MuseWire.read` has 10. `ClaudeWire.read` as row 20 specifies it has 9 `if` statements, which gives complexity 10, the ceiling. Ruff counts `if` statements, not conditional expressions or `and`/`or`.
  Failure: Any extra `if` raises a new S008 finding and the lint stage fails. Writing the key-vs-run choice in step 4, or the marker test in step 5, as an if/else statement is enough to cause it. §12.4 gives S3 no warning about this.
  Smallest fix: Add a §12.4 line saying that S008 has zero headroom, that `ClaudeWire.read` must stay at C901 ≤ 10, and that key-vs-run and the marker choice are written as conditional expressions or in a leaf helper. Name the check: `python -m ruff check vidbyte/harnesses/native --isolated --select C901,PLR0912,PLR0915`. Other zero-headroom ratchets that new code could trip: A007 255/255, S009 350/350, S015 13/13, S051 259/259, S017 79/79, S019 5/5, A006 34/34, C006 104/104, C008 45/45. A001 has 2 headroom (640/642).

R-3 [Major] [L9/L11] INV-19, INV-22, AC-20 — Byte-identity checks pinned to `base_commit` 72a4ade1 become false after the planned catch-up merge
  Evidence: `origin/main` is 0754e01f. Its #1095 changed 41 files (`git diff --shortstat 72a4ade1 0754e01f`). Among them are root `vidbyte/__init__.py`, which adds `SystemPromptPreset` to the root `__all__`, plus `contracts/sdk-public-api.json`, `vidbyte/lib/README.md`, `README.md`, `llms.txt` and many `vidbyte/agents/**` files. The author's report says #1095 touched only `enums/__init__.py` and `llms.txt`; that is wrong. The timing is also inconsistent: pipeline.md:62 says the catch-up merge happens before the S3 push, while §9.4 (line 484) says after S6.
  Failure: After the merge, INV-19 ("every path … §12.3 does not list is byte-identical to `base_commit`"), INV-22 ("root `vidbyte.__all__` … as at `base_commit`"), §12.6 P1 "the tree equals `base_commit`" and AC-20's `git diff` checks all fail. S4/S5 then see dozens of false violations, or S2 pins a check that fails after the merge.
  Smallest fix: State the invariants against `git merge-base origin/main HEAD`, as the existing surface test already does (test_harness_threads_surface.py:86-103, 235-258). Keep 72a4ade1 only as D-17's P1 restore source. Make §9.4 and pipeline.md agree on when the merge happens. Correct the #1095 file list.

R-4 [Major] [L4] D-15 / §10 "Conflicts" — D-15 settles a conflict with AGENTS.md principle 5 against AGENTS.md, and its premise is false
  Evidence: Row 18 copies Grok's `_prepare_home` (grok/threads.py:134-152, 18 lines: home lookup, SHA-256 key, mkdir, `NativeSkillFolders.replace`, error mapping) and changes only constants. D-15 says that "the folder parts, error texts and skills folder differ per harness". But `GROK_SKILLS_DIR = "skills"` equals `CLAUDE_SKILLS_DIR`, `GROK_HOME_KEY_HEX_CHARS = 16` equals `CLAUDE_CONFIG_KEY_HEX_CHARS`, and the Grok failure and unknown detail templates (constants lines 325-326) differ from Claude's only in the noun. The hostkit header (hostkit/__init__.py:7) says "Plumbing that a second harness needs goes here". AGENTS.md principle 5 says "whenever a canonical helper … would save writing the same logic a second time, build it that way", and AGENTS.md outranks the field guide.
  Failure: The logic now exists in two places, with a third copy coming from the parallel native-thread-compose work. This is the convention comment the `@claude` review is built to raise.
  Smallest fix: Add one hostkit helper that locates and prepares the private workspace folder, taking the parts, hex length, skills folder name and detail templates as parameters. Claude uses it (+1 file in §8.4 and §12.3; §14's hostkit ban gets an "adding" exception). Grok's existing copy is untouched code: either switch it in this PR with identical behavior (the `conftest.private_home` hash pins it) or name the switch as a follow-up. Correct D-15's rationale either way.

R-5 [Major] [L1/L3] EC-20 / D-12 / row 29 — DONT_ASK and PLAN are presented as remedies, but neither permits an edit or a command
  Evidence: Docs (code.claude.com/docs/en/headless, Auto-approve tools section): "`dontAsk`: Claude Code denies every call that would otherwise prompt … Actions that need no approval in Manual mode still run … and so do actions your `--allowedTools` entries or `permissions.allow` rules cover". On `acceptEdits`, the same page says "Apart from the read-only command set, other shell commands and network requests still need an `--allowedTools` entry or a `permissions.allow` rule". The permissions docs say `plan` "doesn't edit your source files". The private config holds no allow rules (INV-13), and Q-5 keeps `allowed_tools` out.
  Failure: EC-20 tells a developer whose task needs an edit or a command to pick "`ACCEPT_EDITS`, `DONT_ASK` or `PLAN`". Two of those three grant nothing more than DEFAULT. No allowed mode runs a test or build command. A README written from EC-20 (row 29, AC-23) would mislead production users.
  Smallest fix: Rewrite EC-20 and D-12, and add a line to the README: ACCEPT_EDITS allows file edits and common file commands only; DONT_ASK and PLAN never widen anything; running arbitrary commands needs Q-5's `allowed_tools`, which is optional and not built by default. The same headless page confirms A-2 ("In a `-p` run with no host, these requests are denied either way"). Cite it, and drop EC-20's "If A-2 is wrong the run waits until `claude.timed_out`" and D-12's flip condition.

R-6 [Major] [L5/L7] §9.1 / EC-28 / T-3 / rollback paragraph — Claude Code's auto memory is shared by every thread of a workspace and is never swept
  Evidence: vendor-facts §4 shows that `cfg01/projects/<key>/memory/` is created, and that `CLAUDE_CONFIG_DIR` relocates "the auto-memory folder". The memory docs (code.claude.com/docs/en/memory) say: "Auto memory is on by default in local sessions"; `MEMORY.md` is "loaded into every session" (first 200 lines or 25KB); memory files are excluded from the `cleanupPeriodDays` sweep. The headless docs say a `-p` run without `--bare` loads auto memory. The same page names `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` as the switch that turns it off.
  Failure: `run_claude_thread` does not start a clean thread. Notes Claude saved during any earlier thread in the same workspace load into it, including details from another caller's prompts or text a hostile repository steered Claude into saving. EC-8, EC-28, NG-10, the T-3 residual and the README describe only transcripts and the 30-day sweep, but memory files outlive that sweep.
  Smallest fix: Document the behavior as accepted. Add one EC row ("auto memory shared by all threads of a workspace, never swept"), name it in §9.1's state list, the T-3 residual, EC-28 and README row 29, and run one free stand-in probe that seeds `<cfg>/projects/<key>/memory/MEMORY.md` and checks the request body. Optional Q-8 [scope-adding], not built by default: set `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` in the INV-17 overlay.

R-7 [Minor] [L9] INV-21 / INV-13 / EC-36 — Three cross-references contradict their targets
  Evidence: (a) INV-21 says the nine codes come "in INV-7's problem order" (timed_out, then output_too_large, key_rejected, run_failed, thread_not_found, protocol_mismatch). §8.5, row 15 and AC-18 use `NativeThreadProblem` order instead (not_installed, launcher_refused, launch_failed, key_rejected, thread_not_found, timed_out, output_too_large, protocol_mismatch, run_failed), which is the order the surface test's PROBLEMS list uses. (b) INV-13 cites EC-33 (cancellation) for the case where the workspace contains the home folder; the right row is EC-31. (c) EC-36 lists `true` as "no status", but `isinstance(True, int)` holds, so step 4 formats it as "status True".
  Failure: The text is ambiguous for an exact-order pin in (a), and (b) and (c) send readers to the wrong place.
  Smallest fix: (a) Change INV-21 to "in §8.5 order". (b) Change the citation to EC-31. (c) Either test `type(status) is int`, or drop `true` from EC-36.

R-8 [Minor] [L8] §12.3 — `vidbyte/lib/dataclasses/validation.py`'s ROLE header will go stale
  Evidence: validation.py:4 lists "the output readers GrokWire, OpencodeWire, MuseWire and MuseExecOutput" as callers of `accepts_text`. `ClaudeWire._session` will also call it. §12.3 has no row for this file, and §14 makes touching an unlisted file BLOCKED.
  Smallest fix: Add a header-only row that appends `ClaudeWire` to that sentence.

R-9 [Minor] [L9] §12.5 last bullet — The `--update-baseline` invitation conflicts with NFR-4
  Evidence: Nine rules already report IMPROVED on this tree for reasons unrelated to #1044: A001 642→640, A002 703→578, C011, C012, S001, S010 5→0, S025, S061, S063. NFR-4 and AC-21 require `lint/baseline.json` unchanged.
  Smallest fix: Say that IMPROVED results are pre-existing, and that `lint/run.py --update-baseline` is not run in this PR.

R-10 [Minor] [L7] T-2 — Unverified: Claude Code's startup `git` call may run a workspace-shipped `git` on Windows with the key in its environment
  Evidence: The system prompt carries a git status section (vendor-facts help line 124 lists "git status" among the per-machine sections). Building it runs `git` with the workspace as the working folder and the key in the environment. On win32, launchers that search the current folder first would pick up a `git.exe` the workspace ships. T-2 traces settings, hooks, MCP servers and the SDK's own launcher, but not this path.
  Smallest fix: Run one free probe: a temp workspace with a marker-writing `git.exe`, and `claude -p` with no key. If the probe confirms it, record a T-2 residual. Optional Q-9 [scope-adding], not built by default: set `NoDefaultCurrentDirectoryInExePath=1` in the child environment on win32.

R-11 [Minor] [L2] §15 Q-1 — The question's framing leaves out the precedent that already answers identical wording
  Evidence: Field guide `strict-config-dataclasses.md` (#690→#747) resolved the same owner wording ("pass all of the parameters of the function into a dataclass with strict input validation") by keeping the keyword signature and building one validated record first. #1036's `_call` already does this with `NativeThreadRequest`. The owner's comment (21:42 UTC) came before #1036 merged (22:09 UTC) and is still unresolved.
  Smallest fix: State both options concretely in Q-1: keep the signature and build one record first, per the #747 precedent; or change all twelve public signatures in one cross-harness PR. The default stays unchanged.

VERIFIED CLAIMS
- Grok package size: `__init__` 22 lines, `threads` 188, `wire` 95 (305 in total). It uses a static-method class with module bindings, a guarded try in `_call` (lines 68-86) and a narrated `execute`. `_fallback` uses `NATIVE_WINDOWS_EXECUTABLE_SUFFIX` and `NATIVE_WINDOWS_PLATFORM`. Held.
- Output caps: Grok uses `GROK_CLI_MAX_OUTPUT_BYTES` (4 MiB); opencode and Muse use `NATIVE_PROCESS_MAX_OUTPUT_BYTES` (67,108,864). opencode passes `stdin_text` (opencode/threads.py:103-105) and Muse passes `env_remove` (muse/threads.py:199). Held.
- Reused signatures, all held:
  - `CliInvocation(argv, env_overlay[repr=False], timeout_seconds, max_output_bytes, cwd, stdin_text[repr=False], env_remove)`.
  - `CliArgv.build(launcher, *, command, options, style, operands)`; the SEPARATE style refuses values that start with a dash.
  - `NativeLauncher.resolve(...)` and `NativeSkillFolders.replace`.
  - `NativeErrorFactory.failure(problem, *, request, thread_id, outcome, vendor_text, seconds, cap_bytes, missing_member, searched)`, plus `wrong_thread` (casefold), `listing` and `from_launch_failure`.
  - `RecordFieldValidator.require_number(..., maximum=)`, `accepts_text(value, *, max_chars, pattern)` and `require_argv`.
  - `RecordFieldConverter.to_enum` and `require_instance(..., optional)`.
- `NativeThreadRequest` keys the cap on `harness is OPENCODE` (native_threads.py:91) and checks the Windows unit at :101-102. `NATIVE_STDIN_PROMPT_HARNESSES` is new and leaves the other three harnesses unchanged. Held.
- These constants exist with the stated values: 1800.0, 14400.0, 200000, 100000, `"1"`, `"config"`, `NATIVE_WRONG_THREAD_DETAILS`, `NATIVE_SUCCESS_EXIT_CODE`. Held.
- `vidbyte.harnesses.native.__all__` has 17 names. The static-policy rules (rglob, ALLOWED_VALUES ("", 0, 1), f-strings counted) can pass for the specified modules. Held.
- These line references all held:
  - `enums/__init__` at base: 111-126 and 182-183. At HEAD: 41-58 and 202-218.
  - `failure.py`: `MUSE_WSL_UNAVAILABLE` at :172; HEAD 35-50.
  - `errors/base.py`: :46. `REPO_MAP`: 159-161. `pyproject`: 42-44.
  - conftest fixtures; `fake_harness` `CREDENTIAL_NAMES` at :34; the surface test's FUNCTIONS at :30 and `len == 120` at :193.
- `git diff --name-status 72a4ade1 HEAD` lists exactly the 42 non-docs files of rows 1-12 (9 harness, 4 lib, 7 tools, 1 toolset, 7 modified, 14 tests), and `docs/spec/claude-host` has 24 files. Held.
- `vidbyte/harnesses/README.md` is 10,972 bytes with no Notes for agents. `llms.txt`, `artifacts` and `contracts` do not name the native functions. No Claude name collides at base. Held.
- The §11 commands exist: `run_ci.py --stage all|source|package` and `lint/run.py --rule`. Held.
- The headless docs confirm A-2: in `-p` with no host, prompting requests are denied and the run continues. Held. AC-5 always passes `--permission-mode`, so the docs' "built-in starting mode can be `auto`" never applies. Held.
- `--permission-prompts none` exists in 2.1.301 help with default `host`; it matters only when there is a host. D-12's omission is fine. Held.
- INV-7's wire order is consistent with row 20, and `failure()` defaults `thread_id` to `request.thread_id`, so the INV-6 fallback holds. Held.
- The author's report says #1095 changed only `enums/__init__.py` and `llms.txt`. NOT HELD: it changed 41 files, including root `vidbyte/__init__.py` (R-3).
- AC-3 "upper case succeeds" against row 20 and AC-13. NOT HELD (R-1).
- D-15 "skills folder and texts differ per harness". NOT HELD (R-4).
- EC-20 "DONT_ASK or PLAN" as remedies. NOT HELD (R-5).
- Checked and not raised as findings:
  - Semgrep typed-mapping policy: no match for the specified signatures.
  - A002: within headroom.
  - The 184.5 s key retry: covered by D-11, Q-4 and EC-4.
  - `CLAUDECODE` nested refusal: none.
  - The CLAUDE.md consequence: NG-7 and Q-2.
  - Untracked `__pycache__` in the deleted `claude/` folder: harmless.
  - Over-engineering: nothing material.
