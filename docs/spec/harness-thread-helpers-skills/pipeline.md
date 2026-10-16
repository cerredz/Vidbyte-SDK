---
slug: harness-thread-helpers-skills
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-helpers-skills
branch: feat/harness-thread-helpers-skills
base_commit: 77efd25a (rebased from 0f69f7b7 before S3)
pr:
until: none
started: 2026-10-15 18:12
---

# Pipeline: Thread helpers and built-in skill functions for the Grok, opencode and Muse harnesses

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-15 18:12 | 2026-10-15 18:55 | reports/S0-scout.md | base_commit 72a4ade1 (ff from f216fdcf); code-map.md 4 sections, ~45 files |
| S1 spec + review | done | 2026-10-15 19:00 | 2026-10-15 22:30 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | spec r3 approved (e6b2cdbd); 2 rounds, 25 findings all accepted |
| S2 tests | done | 2026-10-15 22:35 | 2026-10-16 01:50 | reports/S2-test-author.md | 563 new tests (12 files + fake_harness_helpers.py); red 568 failed/430 passed/3 skipped (re-run by orchestrator); b502b6f2, a2053e68 |
| S3 implement | running | 2026-10-16 01:55 | | reports/S3-implementer.md | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (cap reached; final author revision r3 sets status approved) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-15 18:12 — Fast-forwarded local `main` to origin/main f216fdcf (PR #1036 merged) before creating the worktree — Prompt 5: "Make sure the local main is up to date".
- 2026-10-15 18:12 — Unset the worktree branch's upstream (it auto-tracked origin/main) — prevents an accidental push to main; S3 pushes with `git push -u origin feat/harness-thread-helpers-skills`.
- 2026-10-15 18:25 — Codex excluded from this PR; a separate spec-pipeline run on PR #1055 (`feat/codex-host`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-thread-helpers`) adds the Codex helpers and skill functions — Prompt 6 asked for that run; PR #1055's `CodexHost` already owns the Codex thread vocabulary, so Codex helpers here would duplicate it (request.md §C KD-2).
- 2026-10-15 18:25 — Each concurrent pipeline uses its own venv (`C:/Users/422mi/vidbyte-repos/worktrees/.venvs/<slug>`); nobody runs `pip install -e` into the global Python — the global `vidbyte-sdk` editable install points at the main checkout, and two worktrees re-pointing it would make each run test the other's code.
- 2026-10-15 18:25 — Raw research captures (opencode export, Grok inspect, Muse skills, MSP schema) stay in the session scratchpad and are never committed — they may contain the user's real session content; tests use synthetic fixtures of the same shape.

- 2026-10-15 18:55 — Fast-forwarded the worktree branch and local `main` from f216fdcf to origin/main 72a4ade1 (#1027) before any code commit — Prompt 5 wants work on current main; #1027 touches only `vidbyte/harnesses/serialization.py` and `lint/rules/s014_provider_model_registry_parity.py` among mapped areas, neither of which code-map.md maps, so the map stays valid.
- 2026-10-15 18:55 — S0 spot-check passed: code-map.md has §1–§4; `grok/threads.py:141-143` (private-home key) and `errors/base.py:599` (hardcoded "returning a NativeThreadResult") match the scout's citations.

- 2026-10-15 20:00 — Both the S1 spec author and the PR #1055 orchestrator stopped on an API usage limit (HTTP 429, session limit). The limit reset at 8pm, and I resumed both with SendMessage instead of relaunching, because their partial work (an uncommitted spec.md here; S0 done at 53d62851 in the #1055 worktree) was saved and a fresh agent would redo it.

- 2026-10-15 20:15 — S1 author r1 spot-check passed: commit 7910f151, revision 1, 17 template sections, report present. Spec r1: 45 functions (22 helpers, 23 skill functions), 10 new files, FailureCode 148→152, 0 blocking Q. Launched S1 reviewer round 1.

- 2026-10-15 20:40 — S1 review round 1: SOUND WITH FIXES, 1 Blocker (R-1 call depth), 9 Major, 4 Minor, none tagged scope-adding. All 14 go to the author for triage. R-4 restores `run_grok_imagine_video`/`run_grok_code_review`, which were already in the accepted catalog (request.md §E.2), so it is in scope.
- 2026-10-15 20:40 — Rebased the 3 docs-only, unpushed commits from 72a4ade1 onto origin/main 0f69f7b7 (#1095, #1103) and fast-forwarded local main. #1095 touches `vidbyte/__init__.py`, `contracts/sdk-public-api.json` and `vidbyte/lib/enums/__init__.py`; the public API contract has 0 harness entries (C016 does not cover `vidbyte.harnesses.native`), so nothing in the spec changes.

- 2026-10-15 21:00 — S1 r2 spot-check passed: commit 7a0d170f, revision 2, §16 has a disposition row for each of R-1..R-14 (all accepted). The scope is now 47 functions (22 helpers, 25 skill functions) and 68 exports. Because accepted findings changed §8, §8.5, §9 and §10, I launched review round 2 (the last allowed), focused on those sections and what depends on them, as the playbook's S1 rule requires.

- 2026-10-15 21:30 — S1 review round 2: SOUND WITH FIXES, 1 Blocker (R-15: opencode `session list` holds only root sessions and no `parentID`, so D-26's get/lineage cannot work), 5 Major, 5 Minor; 13 of 14 round-1 findings resolved. Sent to the author for the final revision (r3) with `status: approved`; anything still disputed becomes a Q-n with a default. For R-15 I pointed the author to the request's own mechanism (`opencode db`, request.md §E.2) because it reads metadata without moving transcripts (the concern behind R-10); the author decides with evidence.

- 2026-10-15 22:30 — S1 r3 spot-check passed: commit e6b2cdbd, `status: approved`, revision 3, §16 has 12 round-2 rows (R-15..R-25 + R-10 re-disposition). S1 summary printed to the user; continuing to S2 without a stop (playbook rule 8).
- 2026-10-15 22:35 — Authorized S2 to modify existing test files exactly as spec §12.3 rows 35–38 specify (surface test expected exports 68 / 25/15/16, `EXPECTED_ENUMS`, `NEW_FAILURE_CODES` 32, the stale lines 193 and 195; the errors-test key set; `fake_harness.py` stand-ins; conftest/FEATURE.md/README/static-policy test). This is an exception to the S2 template's "never modify an existing test's assertions": these pins encode the public surface this PR is specified to change, line 193 is already red on main, and the gate cannot pass without them. No other existing assertion may change.

- 2026-10-16 01:05 — Second usage-limit outage (HTTP 429; reset at 1am) stopped S2 mid-write: 6 test files modified and 4 new, nothing committed. Resumed the same S2 agent with SendMessage rather than a fresh one, since its inventory and partial files are saved. Also resumed the PR #1055 orchestrator, which was at its S1 round-2 review.

- 2026-10-16 01:50 — S2 spot-check passed: re-ran `tests/features/harness_threads` in the venv → `568 failed, 430 passed, 3 skipped` (matches the report); `git diff --name-only 9cdf80d0..HEAD` touches only tests/features/harness_threads/ and docs/spec/harness-thread-helpers-skills/. S2's 5 open spec gaps (MUSE_GOAL_PROMPT_TEMPLATE value, EC-74 vs §12.4 placement of features.video_gen, EC-67 detail order, Muse session/list limit, mismatch-detail field naming) are tolerated by the tests; S3 resolves each within the spec's words and records it in its report. No spec revision needed.

- 2026-10-16 02:00 — Rebased the unpushed docs+test commits from 0f69f7b7 onto origin/main 77efd25a (16 commits; mapped files touched: only `vidbyte/lib/errors/base.py` +2 lines in `CodexAgentError` and `REPO_MAP.md` 5 lines) and fast-forwarded local main. Red re-run after rebase: 568 failed, 430 passed, 3 skipped — unchanged. Done before S3 so the implementer starts on current main.

## User replies (verbatim)
- 2026-10-15 ~18:25 — "note, ccan you also in a subagent launch this "spec-pipeline" process for pr #1055 and explain the changes that we want to make with the implementation of the existing pr"

## Niche facts accumulated (carried into every later briefing)
- The venv for this run is `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills`; install with `<venv>/Scripts/python -m pip install -e ".[dev]"` from the worktree, then `--stage source` per vidbyte-gates.md — *source:* orchestrator (S0)
- SDK CI `ci.yml` triggers are paused: dispatch `gh workflow run ci.yml --ref feat/harness-thread-helpers-skills` and `gh workflow run static-policy.yml --ref feat/harness-thread-helpers-skills`, read `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`; Actions billing may block runs — *source:* memory vidbyte-release-gates
- Git Bash mangles `/usr/...` args to `wsl.exe`; set `MSYS_NO_PATHCONV=1` — *source:* S0 research
- Muse headless `exec` passes `/goal …` to the model as plain text (verified with `--provider echo`) — *source:* S0 research
- The venv was created by the orchestrator at S0 as `python -m venv --system-site-packages <venv>` + `<venv>/Scripts/python -m pip install --no-deps -e .` (borrows the global dev tooling incl. pytest and semgrep; only `vidbyte` is shadowed). Verified: from a neutral cwd `vidbyte` resolves to this worktree; the global install still points at the main checkout — *source:* orchestrator (S0)
- BASELINE RED ON MAIN: with the venv, `tests/features/harness_threads` → `1 failed, 435 passed, 2 skipped` at f216fdcf. The failure is `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: it reads `failure.py` from git ref `main` and asserts `len(main_members) == 120`, but main now holds 148 because #1036 merged (`assert 148 == 120`, line 193). The test was PR-scoped and went stale on merge; this PR appends more FailureCodes, so the test must be rewritten as a post-merge invariant (main's 148 members unchanged, new codes appended). The gate forces this fix (scope rule 11) — *source:* orchestrator (S0)
- Grok threads live in the private home `~/.vidbyte/grok-homes/<16 hex>` (`grok/threads.py:141-143`); opencode and Muse threads created by #1036 land in the user's normal stores (opencode overrides only `OPENCODE_CONFIG_CONTENT`/`OPENCODE_DISABLE_AUTOUPDATE`; Muse sessions live under `XDG_DATA_HOME`, not the per-call temp `XDG_CONFIG_HOME`; on Windows inside WSL so only `muse` can read them) — *source:* S0 scout
- #1036 plumbing does not fit the helpers as-is: `NativeThreadRequest` requires prompt + API key; launcher/launch-failure need that record; `NativeThreadOperation` has only the 9 existing names; `NativeThreadError.expected` hardcodes "returning a NativeThreadResult" (`errors/base.py:599`); test helper `check_error` builds `<verb>_<harness>_thread` names — *source:* S0 scout
- Pinned-surface hazards: INV-15 `ast` test forbids literals in every module under `native/`; surface/errors tests pin export lists, enum members and exactly 28 FailureCodes; lint baselines allow no new findings (A001 headers, A007 numeric defaults like `limit=20`); semgrep typed-Mapping rule runs only in `static-policy.yml`; `constants/native_threads.py` is 452/1,000 lines — *source:* S0 scout
- One new FailureCode touches 6 places: `failure.py`, `NativeThreadProblem`, summaries + observations tables, `NATIVE_THREAD_FAILURE_CODES`, per-code likely-cause/next-step texts (unique per harness), two pinned tests — *source:* S0 scout
- Grok CLI: `sessions list/search` are text-only (no JSON, no `--cwd`, default limit 20); `export` is Markdown; no `compact` subcommand; `sessions *` take `--leader-socket` (default `~/.grok/leader.sock`); search query is a positional arg, which `CliArgv` does not guard (`argv.py:9`, vs INV-7) — *source:* S0 scout
- opencode CLI: `session list --format json -n` (no `--dir`, so INV-18's PWD guarantee has no equivalent); no search, no compact; `run --command`; `opencode db [query] --format json` — *source:* S0 scout
- Muse CLI: no list/delete command; `muse export` writes into cwd unless `--out` (forbidden in the workspace by AC-19/INV-12; on Windows `--out` needs `/mnt/...`); `MuseMethod` lacks `session/list`/`session/compact`; fake `muse serve` returns -32602 for frames without `sessionId`+`excludeItems`; `wsl.exe -e muse` fails on the default distro — use `-d MuseUbuntu1 -e /usr/local/bin/muse` — *source:* S0 scout
- Reading Grok `summary.json` reverses #1036 D-17 ("Grok's storage layout is a vendor detail the SDK should not read"); the private-home non-isolation finding contradicts EC-44, still stated at `vidbyte/harnesses/README.md:178`; `vidbyte/lib` has no timestamp-parsing helper — *source:* S0 scout
- Spec r1 contract: shared `NativeThreadSummary`, plus new types `NativeCommandOutput`, `GrokThreadScope`, `GrokCommand`; the root `__all__` grows from 17 to 66; new FailureCodes `grok.command_not_run`, `opencode.command_not_run`, `muse.command_not_run`, `grok.store_unreadable` — *source:* S1 author
- Pattern to copy: #1036's `GrokThreads._call` (catch order CancelledError → NativeThreadError → ConfigurationError → Exception), a narrated `<X>Run.execute`, `NativeErrorFactory` with a closed code table; helper child processes list every key variable in `env_remove`; no helper takes `api_key`; read helpers never create the private Grok home (EC-1) — *source:* S1 author
- S052 lint: no blocking file I/O inside `async def`; route file work through `asyncio.to_thread` — *source:* S1 author
- Grok one-shot uses `--single` (not `-p`); A-7 (does `--single "/goal …"` expand the slash command) is unverified, and the manual QA probe goes in the PR body (§12.5) — *source:* S1 author
- Grok store holds non-session files (`~/.grok/sessions/session_search.sqlite`, `permission*.toml` in group folders); scans must take directories only — *source:* S1 review R-2
- C002 (blocking, baseline 9) flags inline `isinstance(x, bool)` guards; use `RecordFieldValidator.require_int`/`require_bool` (`vidbyte/lib/dataclasses/validation.py:85,:92`) — *source:* S1 review R-3
- Grok headless takes `-s/--session-id <UUID>` for a new session; the runner's output cap keeps the first N bytes, so the final `end` event carrying the id is lost on overflow — *source:* S1 review R-6
- Stale surface test: line 195 is stale as well as line 193; `fake_harness.py:562` returns Muse `forkedFrom` as a string, but real MSP gives an object with `sessionId`. MSP `session/list` max 200, sorted by `updatedAt` desc, with `nextCursor` — *source:* S1 review
- `contracts/sdk-public-api.json` and lint C016 do not cover `vidbyte.harnesses.native` (0 harness entries at 0f69f7b7) — *source:* orchestrator
- Spec r2: `GrokStore.threads` serves list and search only; `GrokStore.thread(..., thread_id=)` serves get, read, delete, lineage and evidence; `GrokHelperRun.export` serves both `read_grok_thread` and the code-review evidence; Grok command runs pass an internal minted UUID4 as `--session-id` (D-29); named Grok wrappers refuse flag tokens and reserved `/goal` words, while `run_grok_command` stays raw (D-30) — *source:* S1 author r2
- Highest-risk assumptions, all for manual probe in the PR body: A-7 (slash expansion under `--single`), A-25 (`--session-id` together with `--single`), A-26 (bundled skills resolve under a private GROK_HOME; if not, 11 of the 13 named Grok wrappers always raise `command_not_run`), A-27, A-24 — *source:* S1 author r2
- opencode 1.18.31: `session list` returns root sessions only, defaults to 100 rows per project, and its rows are exactly `{id,title,updated,created,projectId,directory}`; `Session.fork` sets no `parentID` (only subagent children have one); `export` gives `{info: <full session incl. parentID>, messages}`; `opencode db "<sql>" --format json` runs in-CLI (no sqlite3 needed); an unknown `--command` produces the error event `Command not found: "<name>". Available commands: …` and exit 1 — *source:* S1 review r2
- Grok docs: summary.json members at 17-sessions.md:420-431; a same-named workspace/user skill overrides the bundled one (08-skills.md:213); `--session-id` with `--single` is documented (14-headless-mode.md:364) — *source:* S1 review r2
- The existing TIMED_OUT/OUTPUT_TOO_LARGE advice texts (`vidbyte/lib/constants/native_threads.py:390-445`) describe runs only; Muse `anchoredSnapshot` history starts at the compaction boundary — *source:* S1 review r2
- Spec r3 contract for S2/S3: 47 functions (§8.5); exported types `NativeThreadSummary`, `NativeCommandOutput`, `GrokThreadScope`, `GrokCommand` (11 members); FailureCode appends `GROK_COMMAND_NOT_RUN`, `OPENCODE_COMMAND_NOT_RUN`, `MUSE_COMMAND_NOT_RUN`, `GROK_STORE_UNREADABLE` (148→152); `NativeThreadProblem` gains `COMMAND_NOT_RUN`, `STORE_UNREADABLE`; `NativeThreadOperation` gains 47 members equal to the function names; constants `NATIVE_LIST_DEFAULT_LIMIT` 20, `NATIVE_RECENT_DEFAULT_LIMIT` 10, `NATIVE_LIST_MAX_LIMIT` 200, `NATIVE_OPENCODE_SCAN_MAX` 10000, `GROK_SUMMARY_GRACE_SECONDS` 60, `GROK_CODE_REVIEW_FRAGMENT`, `OPENCODE_SESSION_QUERY`, `OPENCODE_COMMAND_NOT_FOUND_TEXT`, `GROK_TEXT_OPTION_FLAGS`; exports 68 (grok 25, opencode 15, muse 16) — *source:* S1 author r3
- opencode get/lineage use `opencode db --format=json "<OPENCODE_SESSION_QUERY>"` (a constant SELECT with a pattern-checked id; falls back to `export` `info` per D-26); opencode lists pass `--max-count=NATIVE_OPENCODE_SCAN_MAX`, and exactly the cap raises `opencode.protocol_mismatch`; opencode forks record no parent (EC-76) — *source:* S1 author r3
- Test contract from S2:
  - Grok argv order: `--output-format=streaming-json`, `--session-id=<uuid4>`, `--cwd`, `--permission-mode`, optional `--model`/`--reasoning-effort`/`--agent`, then `--single=<line>`.
  - Grok env: `GROK_WORKFLOWS=0` for the goal run only.
  - opencode: `--command=<c>` with the arguments on stdin (empty stdin when there are none); get is a single `db --format=json <OPENCODE_SESSION_QUERY>`.
  - `NATIVE_CONTROL_TIMEOUT_SECONDS` is read from the constants module at call time (monkeypatched in tests).
  - Helper children drop `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `META_API_KEY` and `OPENCODE_CONFIG_CONTENT`.
  - Muse `session/list` params are exactly `{workspaceRoot, limit, updatedAfter?}`; get and lineage send `excludeItems: true`; the skill evidence read sends `excludeItems: false` once; export runs `export --session <id> --out <tmp>/export/thread.json` with cwd `<tmp>/export`; ties are returned ascending by id and the SDK reverses them; each helper call gets a fresh private `XDG_CONFIG_HOME`.
  — *source:* S2
- Test fixtures `helper`/`skill` take `config=` or `raw_config=`. The stand-in roles and scenario fields are in test-plan.md "Notes for the implementer". The guard test `test_root_export_lists_are_untouched` passes on purpose: the root `__all__` must not grow — *source:* S2
- Lint (`python lint/run.py`) ends `SDK-LINT: PASS` (not AGENT-LINT); it reports IMPROVED for A001, A002, S025, S061 and S063, and S2 did not lower those baselines. S062 flags adjacent-literal string concatenation — *source:* S2
