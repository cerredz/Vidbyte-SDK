# S6 PR author report: claude-host

Stage: S6 · Date: 2026-10-14 · Branch `feat/claude-host` · Head pushed: `a6245d5a` (was `3ff4479d` local, `490e627b` on origin) · PR: https://github.com/cerredz/Vidbyte-SDK/pull/1044 (draft, base `main`)

## 1. What the code does (written from the diff, before the spec was opened)

`ClaudeHost` (`vidbyte/harnesses/native/claude/host.py`) is an async context manager. `__aenter__` binds it to the running event loop and resolves the `claude` executable once through `ClaudeProbe.locate_cli`: a given path is kept unless it is a Windows `.cmd`/`.bat`; otherwise `shutil.which("claude")`, and on Windows only a native `.exe`/`.com` is accepted, falling back to `which("claude.exe")` and `~/.local/bin/claude.exe`; on POSIX, the SDK's six install locations. The SDK's bundled CLI is never used.

Every public method runs the same steps: `_guard` (entered, not closed, same loop, else `action.precondition_failed`), `ClaudeSdkLoader.load()` (the one `claude_agent_sdk` import, inside the function, so importing vidbyte never needs the extra; a missing extra is `claude.sdk_unavailable`), argument checks through `_ClaudeFieldRules`, then one delegate.

The turn path: `spawn_claude_session` (and `continue`, `launch`) calls `_admit`, a plain `def` with no await, which checks the CLI path, the live cap, busy session ids and refusing rate-limit windows, then builds every `ClaudeLiveSession` and registers and starts them all or none. The handle comes back QUEUED. Continue first reads the session's summary in a worker thread, re-runs `_guard` (a close could have happened during that await), refuses a live session id and a different cwd, and resumes exactly that session with its other session fields cleared. Launch refuses a template that names one session for several prompts and bounds connections with one `asyncio.Semaphore(limit)`.

`ClaudeLiveSession.run` is the pump: wait for a launch slot; stop early if already stopping; `_connect` (build the `vidbyte` MCP tool server, translate the request to `ClaudeAgentOptions`, `connect()`); `_check_process` (`get_server_info`, minimum version 2.1.296, API-key source when `betas` or `bare`); mark RUNNING and arm the watchdog; then loop `_query` → `_read` to the prompt's own result (origin absent or `human`; injected results only update cumulative usage) → `_take_steer` (yield once while a steer is pending, take it, clear the interrupted result's seven per-result fields) → `_query` again. `finally`: mark stopping, drop the steer, cancel the watchdog, grace and interrupt tasks, start or reuse the one close task (`client.disconnect()`), wait for it under `asyncio.shield` (re-waiting with `asyncio.wait` if cancelled), then `_publish`: `ClaudeFailureMapper.classify_turn` picks one status and one failure by fixed precedence, done fires, the launch slot is released.

Stops: `interrupt()` marks the turn stopping and INTERRUPTED; with no client it publishes at once, and for a RUNNING turn it sends `interrupt()` from a session-owned task. Every `interrupt()` that returns arms one grace task (30 s, `CLAUDE_INTERRUPT_GRACE_SECONDS`) aimed at the prompt number it stopped; if that prompt's result never arrives, the grace starts the close. The watchdog does the same for `timeout_seconds` but records `budget_expired`, so the turn ends FAILED `claude.budget_exhausted`. `steer()` stores one numbered message, interrupts from a task, waits for that task without cancelling it, raises the interrupt's mapped error, and raises `action.precondition_failed` if the message was discarded before it was sent. `aclose` marks the host closed, closes each session, and waits for every pump.

History (`history.py`) runs `list_sessions`, `get_session_info`, `get_session_messages` and `fork_session` in `asyncio.to_thread`, reads SDK record fields directly, and maps every failure through `ClaudeFailureMapper`. An empty transcript is checked against `session_info` to tell an unknown session from an empty one.

`ClaudeFailureMapper.from_exception` walks an ordered exception table (subclass before base, `ResultError` by subtype; `ValueError`/`TypeError` are invalid arguments only from connect and fork; `OSError` from a history read is `session_not_found`) and names only the operation and exception class in the reason. `usage_limited` refuses for a rejected, not-per-model window whose reset is in the future and whose overage is not allowed.

Tools (`vidbyte/tools/builtins/claude/`): fifteen thin `BaseTool`s over one host and one developer base request; closed JSON schemas; WRITE for spawn, continue, fork, launch, steer and interrupt, READ for the rest; each catches `ClaudeOperationError` and returns `ToolResult.error("<code>: <reason> Next step: <next_step>")`. `ClaudeTools` (`vidbyte/tools/toolsets/claude.py`) bundles them in order. The host is imported only under `TYPE_CHECKING`.

Records, enums, constants, the error class and the sixteen `claude.*` failure codes live in `vidbyte/lib/`. The PR changes 68 files with 0 deleted lines.

## 2. The §4 snippet

Extracted from spec.md §4 by awk into `scratchpad/s6/snippet_s4.py` and run unchanged through `runpy` under `FakeClaudeSdk().patched()` plus `mock.patch(WHICH_TARGET, return_value=FAKE_CLI_PATH)` (`scratchpad/s6/run_snippet.py`). No real `claude` was started.

```text
=== ready ===
completed Answer: List the TODO comments in this repository.
0.0123
--- fake clients constructed: 2 | queries: ['List the TODO comments in this repository.'] | disconnect calls: [1, 1]
exit=0
=== not ready ===   (ClaudeProbe.locate_cli patched to return "")
claude.not_installed Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.
--- fake clients constructed: 0 | queries: [] | disconnect calls: []
exit=0
```

It runs as written, so AC-1 holds and the body uses the snippet unchanged. The agent snippet in §4 needs a real model; it was not run by me, and the body cites `AgentSnippetTests` (scripted runner) instead.

## 3. Deviations found (code vs spec §4, §5, §8, §12)

- §17 deviations 1–14 are accurate against the code; each is summarized in one line in the body.
- **§5 diagrams simplify three steps** (not edited; noted in the new §17 row):
  1. §5 shows `classify_turn` before the close task; the code classifies inside `_publish`, after the close finishes (`session.py:191-193`, `:445-452`). No behaviour difference: nothing can change the outcome during the close.
  2. §5's steer edge goes straight from the result to `query`; the code yields once, takes the message and clears the interrupted result's fields first (`session.py:253-270`, deviation 14 and R-23).
  3. §5's sequence diagram has the host send `interrupt()`; the code sends every `interrupt()` from a task the session owns (`session.py:383`, `:470`, `:499`).

  In round 1 I did not edit §5, because the briefing limited spec.md edits to the frontmatter and the §17 row. In round 2 the coordinator lifted that limit, and §5 is now redrawn (section 9).
- **R-C5:** §12.3 row 7 and §17 do not describe R-23's reset (`session.py:264-269`). Listed as a follow-up.
- §4 snippet, §8 decisions D-1..D-33 and the §12.3 file list match the code. `ClaudeSpawnRequest` has 58 fields (`lib/dataclasses/claude.py:379-436`), and there are 17 enums and 16 codes.

## 4. What I verified (commands and final lines)

- AC proof references: all 62 test references in spec §6.2 exist in `pytest --collect-only` (181 tests collected); none missing.
- Pack: `181 passed in 5.67s`. CI view (`sys.modules['claude_agent_sdk']=None`): `181 passed in 5.53s`.
- `PYTHONPATH=$W $PY scripts/run_ci.py --stage source` at 3ff4479d: `SDK-LINT: PASS` / `4182 passed, 27 skipped in 38.56s` / `CI passed.` / exit 0.
- `$PY scripts/run_ci.py --stage package --dist-dir scratchpad/s6/dist`: `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / exit 0. All 22 new `vidbyte/` files are in `vidbyte_sdk-0.2.1-py3-none-any.whl` (zip listing; missing: `[]`).
- `generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).`
- Marker: `git show HEAD:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- Diff scan: no `.pyc`, `__pycache__`, dist or build paths; no credential patterns (`sk-`, `ghp_`, `AKIA`, `xox`, private keys) in added lines.
- Semgrep was not re-run locally; static-policy ran it remotely on a6245d5a (`Ran 1 rule on 915 files: 0 findings.`).
- origin/main is still 8387d666 (`git rev-list --count HEAD..origin/main` = 0), so no catch-up merge was needed.

## 5. Commit, push, PR

- Commit `a6245d5a docs(spec): finalize claude-host for PR` adds `pr-body.md` and changes spec.md: frontmatter `status: pr-open` (`pr` and `updated: 2026-10-14` were already set) and one §17 row `r6 | 2026-10-14 | S6 PR | Finalized for review …`.
- Push: `490e627b..a6245d5a feat/claude-host -> feat/claude-host`. It carried two earlier docs commits (deafe420, 3ff4479d), not three as the briefing said.
- Dispatched: CI 38523773941 and Static policy 38523776541 on a6245d5a.

```text
CI success a6245d5a Source / Python 3.12:success, Source / Python 3.11:success, Package:success
Static policy success a6245d5a Static policy:success
Source / Python 3.12 | SDK-LINT: PASS | 4190 passed, 19 skipped, 19 warnings in 48.36s | CI passed.
Source / Python 3.11 | SDK-LINT: PASS | 4190 passed, 19 skipped in 46.00s | CI passed.
Package | Installed vidbyte-sdk 0.2.1 passed smoke checks. | CI passed.
Static policy | Ran 1 rule on 915 files: 0 findings.
```

`gh api repos/cerredz/Vidbyte-SDK/commits/a6245d5a/check-runs`: Package, Static policy, Source / Python 3.11, Source / Python 3.12, all `completed/success` (4/4).

Final `gh pr view --json title,isDraft,baseRefName,url`:
```json
{"baseRefName":"main","head":"a6245d5a","isDraft":true,"title":"feat(harnesses): add ClaudeHost with one agent tool per Claude Code function","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1044"}
```
Final `gh pr checks`: `no checks reported on the 'feat/claude-host' branch` (exit 1). Both workflows are dispatch-only, so this is expected; the check-runs API above is the evidence.

**The posted PR body differs from the committed `pr-body.md` in two places**, because the run ids exist only after the commit that carries the file:
1. The "remote CI, PR head" row: the file says the runs were dispatched after its commit; the PR body carries the run ids and per-job final lines above.
2. The file count: the file says "All 67 files … 17,816 lines added"; the PR body says "All 68 files, this description's own `pr-body.md` included, … 18,068 lines added". `git diff --shortstat origin/main...HEAD` → `68 files changed, 18068 insertions(+)`.

Everything else is byte-identical (`tail -n +2` of the file, then those two replacements). The body's last line is exactly `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## 6. Candidate field-guide lessons (report only; not written to the field guide)

Shape: trigger · preferred action · project-specific reason · quick check · link.

1. **Reading vendor SDK records** · Read each field the pinned SDK dataclass declares by attribute; keep `or ""` only where an SDK `str | None` meets a record `str`, and `.get` only for plain dict payloads · `vars()`/`.get` with empty defaults turns a field an allowed SDK release renamed into empty text instead of `claude.protocol_mismatch` (R-3, conventions R-V1; agrees with class-bound-helpers.md) · `git grep -n "vars(" vidbyte/harnesses` finds nothing in converters · PR #1044, fix 52a482d4.
2. **A one-pass yield in async code** · Use a named constant (`asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)` with the constant `= 0` in `lib/constants`) · lint A007 rejects a literal `asyncio.sleep(0)` next to timing names, and it is blocking (R-2) · `python lint/run.py --rule A007` · PR #1044, 4ad8f35d.
3. **Yielding before handing off a pending message** · Yield while the message is still in its slot, then take it · a stop that lands during the yield can only withdraw what is still in the slot; yielding after the take silently sends a cancelled message (R-22) · a stop scheduled into the yield pass discards the message, `StopInSteerWindowTests` · PR #1044, b5989730.
4. **A call chain lint forces two levels deep** · Keep the forced shape and record it as a spec deviation naming the rule that forces it (S024 nesting limit, the class budget) instead of folding or adding a class · AGENTS.md principle 1 asks for one level, but S024 (max depth 3) is blocking, so an unrecorded two-level chain reads as a convention breach in review (R-4) · `python lint/run.py --rule S024` on the folded draft · PR #1044, spec r5 deviation 12.
5. **`@intent` markers** · One slug per rule, and one rule per slug, reused at every site that enforces that rule · A002 needs the marker, and reviewers read the slug as the rule's identity; two rules under one slug, or one rule under four slugs, fails review (R-14, conventions R-V6) · `git grep -h "@intent" <paths> | sort | uniq -c` · PR #1044, 04e0254b.
6. **Narration of a host class's public methods** · Narrate every public "★" method, not only the long ones · AGENTS.md principle 2 applies per main function, and five one-screen methods without comments were a confirmed finding (R-13, conventions R-V5) · read each public method body for `#` lines · PR #1044, 5093e792.
7. **Branching on a string kind with three or more cases** · Use `match` with an explicit `case _` · the house dispatch rule is applied in review even where lint is silent (R-11, conventions R-V7) · search the diff for `elif kind ==` · PR #1044, c5d243a9.
8. **Spec IDs in source comments and docstrings** (not fixed; R-16) · Prefer stating the rule in words over citing `(INV-3)`, `(D-29)` · AGENTS.md tells agents not to read `docs/`, so an ID in a comment points at a document the next agent may not open, and it shows in `help()` · `git grep -nE "\((INV|D|EC|AC)-[0-9]+" vidbyte` · PR #1044 review R-16. Hold this one until a human reviewer agrees, since it was downgraded to Minor and left open.

## 7. Anything that looked wrong while reading

No new bug found. Every concern I checked is already a recorded follow-up:
- `vidbyte/harnesses/native/claude/host.py:171`, `:281`, `:292`, `:304`, `:315`, `:326`: a non-record `request` or `handle` raises a raw `AttributeError` (R-17).
- `vidbyte/harnesses/native/claude/host.py:91-115`: `aclose` does not wait for an in-flight readiness or models probe (R-21).
- `vidbyte/harnesses/native/claude/session.py:78`, `:124`, `:137`: finished sessions keep their request, client and interrupt tasks until `aclose` (R-18).
- `tests/features/claude_host/test_claude_host_review_gaps.py:358-373`: the R-23 test pins only one of the three kept fields (R-C4); its file header lists only R-1 to R-12.
- Observation, not a finding: `host.py:33` imports the private `_ClaudeFieldRules` from `vidbyte/lib/dataclasses/claude.py`. The lib module's header documents this sharing, and no lint rule flags it.

## 8. Files

- Produced: `docs/spec/claude-host/pr-body.md` (a6245d5a, updated in the round-2 commit), `docs/spec/claude-host/spec.md` (frontmatter and §17 row in a6245d5a; §5 and the §17 row in the round-2 commit), and this report (committed in the round-2 commit).
- Scratch: `scratchpad/s6/snippet_s4.py`, `run_snippet.py`, `gate-source.txt`, `gate-package.txt`, `gate-api.txt`, `dist/`.

## 9. Round 2 (coordinator's follow-up, same day)

The coordinator checked the PR and asked for three docs-only changes.

1. **Compatibility section: my omission.** The round-1 body had no `## Compatibility` section, although I had planned one, and my round-1 STATUS wrongly said the body added it. It is now in `pr-body.md`, after `## Motivation`. Each claim was checked against the code before it was written:
   - `git diff origin/main...HEAD -- pyproject.toml` adds only the three `claude = ["claude-agent-sdk>=0.2.165,<0.3.0"]` lines. `requires-python = ">=3.11"`, the base dependencies, `codex` and `dev` are unchanged.
   - `git diff --stat origin/main...HEAD -- contracts/ vidbyte/__init__.py` is empty. `generate-sdk-public-api.py --check` reports the contract current with 606 exports, and the contract names no Claude symbol.
   - `git diff --numstat origin/main...HEAD -- vidbyte pyproject.toml` sums to 0 deleted lines, so the four export lists (`vidbyte.lib.enums`, `vidbyte.lib.errors`, `vidbyte.tools.builtins`, `vidbyte.tools.toolsets`) only gain names.
   - The CLI floor is `CLAUDE_MIN_CLI_VERSION = "2.1.296"` (`vidbyte/lib/constants/claude.py:24`). `ClaudeProbe.version_ok` enforces it in readiness (`probe.py:126`) and in each turn before the first query (`session.py:222`). The next steps are taken from `CLAUDE_FAILURE_NEXT_STEPS` (`constants/claude.py:72-89`).
2. **§5 redrawn.** The flowchart is now the PR body's flow chart, unchanged. The sequence diagram adds the session-owned interrupt task, the grace, the `_take_steer` yield and reset, and `_publish` after the close. The prose has four bullets: validation, state changes, interrupts and failures. The new §17 row now says §5 was redrawn, instead of recording the drift. In the body's Deviations, the §5 bullet is gone; R-C5 (§12.3 row 7 and the §17 deviations) stays a follow-up.
3. **One commit, `docs(spec): redraw claude-host §5 and add Compatibility to the PR body`,** carries spec.md, pr-body.md and this report. It was then pushed, the PR title and body were edited from `pr-body.md`, and `ci.yml` and `static-policy.yml` were re-dispatched on the new head. The new head's run ids exist only after this commit, so they are in the PR description and the STATUS block, not in this file. The committed `pr-body.md` lists the a6245d5a runs (CI 38523773941, Static policy 38523776541, both green), and its last remote row is filled in when the body is posted.
