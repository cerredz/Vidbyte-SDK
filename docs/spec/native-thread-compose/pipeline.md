---
slug: native-thread-compose
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose
branch: feat/native-thread-compose
base_commit: 5c08c35edcb1827e190ca4e2b2b1370808ef24be
pr_base: feat/native-grok-opencode-meta-hosts
pr:
until: none
started: 2026-10-15 18:04
---

# Pipeline: Composite thread functions across Grok, opencode and Muse

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-15 18:04 | 2026-10-15 18:52 | reports/S0-scout.md | base_commit 5c08c35e; code-map.md (4 sections, ~90 files read) |
| S1 spec + review | running (author r1 done at 7df09460 after two rate-limit resumes; review round 1 running) | 2026-10-15 19:05 | | reports/S1-spec-author.md; reports/S1-spec-review.md (pending) | spec r1 (~197 KB, 18 sections, 27 §12.3 rows, 40 new files, 42 public names; FR 18, NFR 11, AC 23, EC 72, INV 36, D 28, W 13, A 11, Q 10 non-blocking) |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Key SHAs
- BASE_COMMIT: 5c08c35edcb1827e190ca4e2b2b1370808ef24be (head of PR #1036 at S0; the base moved from 4a7987c7 during S0 via a merge of main that touched 2 unrelated files)
- S2_HEAD: (pending) · S3_HEAD: (pending)

## Decisions the orchestrator made
- 2026-10-15 18:05 — PR_BASE = `feat/native-grok-opencode-meta-hosts` (stacked on PR #1036), not `main` — the parent session's non-negotiable facts and request.md §C; the nine functions exist only there.
- 2026-10-15 18:05 — Worktree created with `git worktree add --no-track` — `branch.autoSetupMerge` is unset, so a plain `-b` from the remote ref would have made the new branch track the base branch; nobody may push to `feat/native-grok-opencode-meta-hosts`.
- 2026-10-15 18:10 — Remote gate = dispatched runs on `feat/native-thread-compose`: `gh workflow run ci.yml --ref feat/native-thread-compose` and `gh workflow run static-policy.yml --ref feat/native-thread-compose` — `ci.yml` and `static-policy.yml` have automatic triggers disabled (workflow_dispatch only), so `gh pr checks` reports no checks on any PR; this is how PR #1036's head was verified. Baseline: CI run 38814538787 on 5c08c35e = success.
- 2026-10-15 18:20 — Local static-policy gate uses an isolated venv (semgrep 1.170.1, mcp 1.23.3) at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/semgrep-venv` — the global semgrep is broken by an mcp 2.x import clash. Baseline at 5c08c35e: fixture test "1/1: ✓ All tests passed"; scan "Ran 1 rule on 958 files: 0 findings."
- 2026-10-15 18:55 — No agent runs `pip install -e` in the worktree — every dev extra is already installed globally at its pinned version (pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1, build 1.5.0, twine 6.2.0), and the shared editable install points at the main checkout that other live sessions use. All source-stage and pytest runs use `PYTHONPATH=<worktree>`; the package stage runs without it.
- 2026-10-15 18:56 — Corrected my own request.md note: the CLI ensemble folder holds ten prompt `.md` files plus `SKILL.md` and `library.py` (scout C-14).
- 2026-10-15 18:58 — Precedence ruling for S1, from request.md (no owner question needed): (a) scout C-2: base INV-1 pins `vidbyte.harnesses.native.__all__`; ledger 9 explicitly allows `vidbyte.harnesses.native.compose`, so the composites are exported from `.compose` and `native.__all__` stays exactly as pinned. (b) scout C-5: base NG-3/INV-19 ("no diff operation anywhere in the PR") scoped PR #1036; the owner's verbatim Prompt 2 ("Implement with capture_diff around the writer") and ledger 5 require `capture_diff` in this PR, so the specific later words win; the nine functions themselves still never diff. Ledger 1 is read as binding the behavioural and security INV-/EC-/T- items of the nine functions. Both become recorded D- decisions in the spec.
- 2026-10-15 18:58 — Baseline gate run at BASE_COMMIT in a separate detached worktree `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/base-5c08c35e`, so inherited failures can be told apart without touching the pipeline worktree; log at `.../scratchpad/baseline-source.log`.

- 2026-10-15 19:05 — Local Windows baseline at BASE_COMMIT finished: `python scripts/run_ci.py --stage source` (detached worktree, PYTHONPATH set) → `SDK-LINT: PASS`; pytest "1 failed, 5640 passed, 16 skipped in 109.07s"; wall 3m04s. The one failure, `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`, is the known timing flake (field guide `local-ci-verification.md`); isolated reruns at base: pass, pass, fail → inherited, never owned by this PR.
- 2026-10-15 19:50 — Interruption 1: the S1 author was stopped by an API rate limit (HTTP 429, session limit) mid-grounding, nothing on disk (verified 20:02: HEAD 1362785a, clean). The coordinator asked to continue; I resumed the SAME author via SendMessage at 20:02 (its notice said its work was saved; coordinator rule: resume rather than relaunch). Gave it the baseline facts above.
- 2026-10-15 ~21:55 — Interruption 2: the S1 author was stopped by the same limit while assembling. Verified 2026-10-16 01:39: HEAD 1362785a, clean; parts `p0-verbatim.md`, `p1a.md`, `p1b.md` (§1–§5), `p2a.md`/`p2b.md`/`p2c.md` (§6–§7), `p3a.md`/`p3b.md` (§8–§10) in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/spec-parts/`. Coordinator (2026-10-16): resume the same author, do not relaunch. Resumed via SendMessage to finish §11–§17, assemble, commit, report.

## User replies (verbatim)
- none (coordinator relay messages on 2026-10-15 20:0x and 2026-10-16 01:3x concerned rate-limit resumption only; no product decisions)

## Niche facts accumulated (carried into every later briefing)
- Lint's final line is `SDK-LINT: PASS` (not `AGENT-LINT`), from `lint/core/report.py:58` — *source:* S0 scout, orchestrator verified.
- The INV-15 static scan (`tests/features/harness_threads/test_harness_threads_static_policy.py`) covers every `*.py` under `vidbyte/harnesses/native/` (so any `compose/` too): no module-level assignment except `__init__` bindings; no str/int constant except `""`, `0`, `1`, f-string text included; every JSON key, git argv word, default number and prompt file name must come from `vidbyte/lib/constants` — *source:* S0 scout (code-map §4 C-3).
- The surface test pins `vidbyte.harnesses.native.__all__`, 14 enums, the FailureCode tail (exactly 28 harness codes, `len == 120 + 28`), `NativeThreadOperation` (9), `NativeThreadProblem`, and `vidbyte.lib.process.__all__` (3 names); new members of those break it — *source:* S0 scout (C-2, C-4).
- Failure codes are not all `<harness>.<problem>`: argument refusals are `configuration.invalid_argument`, defects `runtime.error`; `NativeThreadError` has no `problem` attribute (reverse lookup via `NATIVE_THREAD_FAILURE_CODES`); `OutputSchemaViolationError` already exists — *source:* S0 scout (C-1).
- Grok and Muse prompts cap at 24,000 characters (plus 30,000 command-line units on Windows); opencode 200,000; one result text can be 100,000; CLI `planner_system.md` is 58,578 and `implementer_system.md` 35,852 characters; the nine functions have no system-prompt parameter; prompts must be NUL-free and non-blank — *source:* S0 scout (C-11, G-13).
- `functools.partial` reprs show `api_key='…'` (breaks base INV-2); bind with a record using `field(repr=False)` — *source:* S0 scout (G-1).
- A Grok thread is reachable only from the workspace that created it; forks stay on the source harness; each new worktree path leaves a ~1 MB Grok home that is never removed; Muse WSL mode needs a drive-letter path — *source:* S0 scout (C-9, G-2, G-3).
- Fake harness gaps: no workspace-writing mode, no permission modelling, no fail-then-succeed counter, one release file frees every held process, opencode stand-in ignores `--dir`, sandbox `PATH` holds only its `bin` so `git` is not found — *source:* S0 scout (§3.2, G-4..G-6, G-11).
- Lint rules that bite: S063 (`gather(return_exceptions=True)` results need a `BaseException` check), S064 (a sleeping retry loop needs an overall deadline), S006/RUF006 (keep every `create_task` result; baseline 0), S019 (re-raise cancellation), A007 (named constants for caps), A001 (headers), A009 (README ≤ 40,000 chars), C015 (package data for assets), S051 (import order; check over the whole tree) — *source:* S0 scout.
- CLI prompts use `{{name}}` with literal replace; SDK catalog consumers use `str.format`; the CLI enforced JSON via Codex's host schema, which the native functions lack — *source:* S0 scout (C-12, C-13).
- The CLI has a fixed per-stage effort and no ladder; its classifier keys on Codex error info; native effort enums differ per harness (Grok to `max`, Muse to `ultra`, opencode only a free-form `variant`) — *source:* S0 scout (C-16).
- Gate commands: `python lint/run.py`; `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`; `python scripts/run_ci.py --stage package` (no PYTHONPATH); `PYTHONPATH=$(pwd) python -m pytest -q <path>`; semgrep needs `export PATH="/c/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/semgrep-venv/Scripts:$PATH"` first (POSIX form; a `C:/` entry breaks PATH), then `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` after `git add` of new files — *source:* orchestrator, verified.
- Git Bash mangles `<rev>:<path>` arguments; prefix with `MSYS_NO_PATHCONV=1` for `git show <rev>:<path>` — *source:* orchestrator.
- Inherited flake: `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` (fails ~1 in 3 locally at BASE_COMMIT; on CI rerun with `gh run rerun <id> --failed`). A pytest failure stops `run_ci.py --stage source` before later steps, so when only this test fails, rerun it in isolation and run `python scripts/run_ci.py --stage package` separately — *source:* orchestrator baseline + owner memory note.
- `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` reads FailureCode at `git merge-base origin/main HEAD` and expects that count + 28; it passed at BASE_COMMIT in the local baseline. It fails on pristine `main` (owner memory note), so never "fix" it from this branch; never merge `main` into this branch — *source:* owner memory note + orchestrator baseline.
- This checkout has `core.autocrlf=true` (git warns "LF will be replaced by CRLF") — *source:* orchestrator (S0 commit).
- Writing files through bash heredocs collapses `\\` to `\`; write backslash-bearing content with the Write tool — *source:* owner memory note.
- Spec r1 contract (S1 author): package `vidbyte.harnesses.native.compose` (42 public names: `chain_threads`, `verify_with`, `handoff_thread`, `run_staged_threads`, `run_ensemble`, nine generated aliases, `bind_thread`, `bind_continue`, `capture_diff`, `in_worktree`, `parse_json_answer`); 7 enums in `vidbyte/lib/enums/native_compose.py` (`VerdictDecision`, `StageDecision`, `EnsembleStage`, `ThreadComposeProblem`, `ComposePrompt` (22), `ComposeField` (34), `GitFlag` (17)); 12 records in `vidbyte/lib/dataclasses/native_compose.py`, 6 in `native_ensemble.py`; `ThreadComposeError` in `vidbyte/lib/errors/base.py`; `JsonText` in `vidbyte/lib/util/json_text.py`; `RecordFieldValidator.require_template` and `command_line_units`; `native.__all__` and root `__all__` unchanged — *source:* S1 author.
- Sibling: `vidbyte/harnesses/native/grok/threads.py` (static-method class, guarded try at 69–86); test pack `tests/features/harness_compose/` (named by `ThreadComposeError.relevant_tests`) with its own `conftest.py`, `FEATURE.md`, `README.md` — *source:* S1 author.
- Test seams: bind each step with `<harness>_command` set to the stand-in argv; put real git on PATH (sandbox PATH holds only `bin`, `conftest.py:257`); commits in test repos need `-c user.name=… -c user.email=…`; `tempfile.tempdir` is the sandbox `tmp`, a sibling of `ws`; compose constants are read at call time (monkeypatchable via `vidbyte.lib.constants.native_compose`), but `NATIVE_ARGV_PROMPT_MAX_CHARS` is imported by name into the base record — *source:* S1 author.
- `fake_harness.py` cannot yet vary its answer per launch, write into its workspace, or echo the key; extend only with scenario fields read via `.get` with a default; base tests stay unmodified — *source:* S1 author.
- The package stage does not check the compose prompt files, so AC-21 needs an explicit look inside the built wheel — *source:* S1 author.
