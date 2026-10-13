# S3 implementer report: claude-host

- **Stage:** S3 implementer
- **Status:** DONE
- **Branch:** `feat/claude-host`, pushed. Draft PR [#1044](https://github.com/cerredz/Vidbyte-SDK/pull/1044) has the placeholder body.
- **Tests frozen at:** `9a8ecc3c`. `git diff 9a8ecc3c..HEAD --stat -- tests/` prints nothing.
- **Spec:** frontmatter now has `status: implemented` and `pr:` set. §17 has the `r4 | S3 implement` row, and an "Implementation deviations" list follows it.

## Commits

These are the S3 commits, `b0d6c4c3..HEAD`, oldest last:

```
4e14f870 docs(spec): record draft PR for claude-host
5edf1a4d style(claude-host): wrap the new comments in 72-column blocks [§12.4; W-1, W-13, W-14, W-15, W-16, W-17]
14dd7231 docs(harnesses): map the native hosts package in REPO_MAP and the harnesses README [W-21; FR-24, AC-32]
bc82d9b0 feat(tools): export ClaudeTools from vidbyte.tools.toolsets [W-17; FR-20, AC-13]
57c9e722 feat(tools): add ClaudeTools, the fifteen Claude tools over one host [W-17; FR-20, AC-13, AC-29]
cd7e91bf feat(tools): export the Claude tools from vidbyte.tools.builtins [W-16; FR-19, AC-12]
47f7a422 feat(tools): export the fifteen Claude tools from builtins.claude [W-16; FR-19, AC-12]
7977493c feat(tools): add the wait, result, steer, interrupt and usage Claude tools [W-16; FR-19, INV-14, AC-12, AC-26]
372c0d8e feat(tools): add the saved-session history Claude tools [W-16; FR-19, INV-14, AC-12]
d4541c33 feat(tools): add the spawn, continue, fork and launch Claude tools [W-16; FR-19, INV-14, AC-12, AC-26]
f7788954 feat(tools): add the readiness, model and rate-limit Claude tools [W-16; FR-19, INV-14, AC-12]
39f57d21 feat(tools): add the shared Claude tool base with closed schemas and code-based error results [W-16; FR-19, AC-12, AC-24, AC-26]
0981a55e feat(tools): add the model-facing text of the fifteen Claude tools [W-16; FR-19, AC-12]
8a08732e feat(harnesses): export ClaudeHost from the claude package [W-1; FR-1, AC-1]
b7e5332a feat(harnesses): add ClaudeHost with the fifteen Claude Code functions, admission and close [W-1..W-12; FR-1..FR-15, AC-1, AC-3, AC-7, AC-11, AC-16, AC-21, AC-30, AC-35, AC-38]
e7382a26 refactor(harnesses): return the initialize answer with readiness and add a text check for host arguments [W-2, W-16; FR-2, FR-3, FR-19, AC-26, AC-34]
ca0be69a feat(harnesses): add ClaudeLiveSession to run one turn with steer, interrupt, budget and one close [W-4, W-8..W-11; FR-5, FR-11..FR-14, FR-25, AC-3, AC-4, AC-9, AC-10, AC-15, AC-25, AC-28, AC-31, AC-36, AC-37, AC-39, AC-40]
dceb2dfe fix(harnesses): add intent markers to signed_in and ClaudeThinking checks [W-1, W-13; FR-3, FR-16, AC-38, AC-18]
5982f9e5 feat(harnesses): add ClaudeToolServer to carry request tools over the vidbyte MCP server [W-15; FR-18, AC-20]
e13f35ae feat(harnesses): add ClaudeProbe for CLI lookup and the prompt-free initialize probe [W-1, W-2; FR-1, FR-2, FR-3, AC-22, AC-34, AC-38, AC-39]
75eef0b4 feat(harnesses): add ClaudeHistory for offline session list, info, messages and fork [W-6, W-7; FR-7..FR-10, AC-8, AC-14]
f0c84cd0 refactor(harnesses): name each history operation and keep invalid_argument to connect and fork [W-14; FR-17, AC-6]
8429f941 feat(harnesses): add ClaudeOptionsTranslator for request-to-SDK options [W-13; FR-16, AC-17]
5168fb9a feat(harnesses): add ClaudeFailureMapper for exceptions and turn outcomes [W-14; FR-17, AC-5, AC-6, AC-24, AC-39]
a38b8e37 feat(harnesses): add ClaudeSdkLoader, the one claude_agent_sdk import [W-14; FR-17, AC-2]
450b7c35 feat(harnesses): add the native harness package marker [W-19; FR-22, AC-19]
47ba638d build(pyproject): add the claude extra pinning claude-agent-sdk [W-18; FR-21, AC-33]
04290c3b feat(dataclasses): add the fifteen ClaudeHost output records [W-1, W-4; FR-1, FR-25, AC-4, AC-15, AC-28]
8facd70d feat(dataclasses): add ClaudeSpawnRequest and its seven validated records [W-13; FR-16, AC-18, AC-24]
eb5f34d6 feat(errors): export ClaudeOperationError [W-14; FR-17]
2a6de8ae feat(errors): add ClaudeOperationError with the A003 packet [W-14; FR-17, AC-2]
ae6d6482 feat(constants): add the ClaudeHost constants and next steps [W-13, W-14; FR-16, FR-17, AC-23]
6d8a311f feat(enums): add the sixteen claude.* failure codes [W-14; FR-17, AC-23]
7dbcc818 feat(enums): export the Claude enums from vidbyte.lib.enums [W-20; FR-23, AC-27]
34f27cdc feat(enums): add the seventeen Claude enums [W-20; FR-23, FR-16, AC-27]
```

A last commit, `docs(spec): record implementation proof for claude-host`, adds the §17 row, the deviations list and this report.

## What was built, in data-flow order

1. **Developer entry.**
   - `ClaudeTools(host, request=None)` (`vidbyte/tools/toolsets/claude.py`) builds the 15 tools in §9.2 order over one `ClaudeHost` and one base request.
   - A missing request defaults to `ClaudeSpawnRequest()`.
2. **Tools.** Each tool lives in `vidbyte/tools/builtins/claude/`: `readiness.py`, `sessions.py`, `history.py` or `turns.py`.
   - `spec()` returns a closed schema through `_ClaudeBuiltinTool._spec`.
   - `execute()` reads arguments with `BaseTool._optional_argument` (JSON null means omitted), calls one host function, and returns `json.dumps` of the record or records.
   - A `ClaudeOperationError` becomes an error `ToolResult`: `"<code>: <reason> Next step: <next_step>"`, with metadata `{"error", "error_type"}` (INV-13).
   - The spawn and launch tools replace only the prompt of the base request. The continue tool passes the request whole, and the host clears its session fields (D-13).
   - Turn tools resolve `handle_id` through `ClaudeHost.get_handle` (D-14).
   - Model-facing text lives in `descriptions.py`.
3. **Host.** `ClaudeHost` (`vidbyte/harnesses/native/claude/host.py`) runs the same steps for every call: guard (open, same loop), then the lazy SDK load, then argument checks, then delegation.
   - `_admit` checks paths, the live cap, held session ids and rejected rate windows, all before any process starts.
   - It then registers and starts one `ClaudeLiveSession` per turn, so spawn, continue and launch return handles at once.
   - `aclose` closes every session and waits for every pump.
4. **Lazy SDK seam.** `ClaudeSdkLoader.load` (`sdk.py`) is the only `claude_agent_sdk` import. It returns `ClaudeSdkTypes`, or raises `claude.sdk_unavailable`.
5. **Options.** `ClaudeOptionsTranslator.to_options` (`options.py`) maps each set request field to its SDK option, CLI flag or environment variable, and leaves unset fields out.
   - Request tools ride the in-process `vidbyte` MCP server built by `ClaudeToolServer` (`tool_server.py`).
6. **Turn runtime.** `ClaudeLiveSession.run` (`session.py`) is the pump.
   - It waits for a launch slot, connects, checks the version and login type, and sends the prompt.
   - It reads up to the prompt's own result, then sends any stored steer as the next prompt.
   - Throughout, it records rate windows, usage, assistant errors and denials.
   - It closes the client exactly once, in a task that nothing cancels, and only then publishes the terminal status.
   - The watchdog (time budget), caller interrupts and steers send `interrupt()` from tasks the session owns. Each `interrupt()` that returns arms a grace aimed at the prompt it stopped.
7. **Classification.** `ClaudeFailureMapper` (`failures.py`) handles both exceptions and finished turns:
   - `from_exception` maps exceptions to the 16 `claude.*` codes plus the configuration codes.
   - `classify_turn` gives every finished turn exactly one status and at most one failure.
8. **Offline reads.** `ClaudeHistory` (`history.py`) lists sessions, reads session info and messages, and forks, in worker threads. `ClaudeProbe` (`probe.py`) does the CLI lookup and the prompt-free initialize probe used by readiness and models.
9. **Records and vocabulary.**
   - Request-side records with their validation: `vidbyte/lib/dataclasses/claude.py`.
   - Output records: `vidbyte/lib/dataclasses/claude_host.py`.
   - 17 enums: `vidbyte/lib/enums/claude.py`.
   - Constants and next steps: `vidbyte/lib/constants/claude.py`.
   - 16 failure codes: `vidbyte/lib/enums/failure.py`.
   - `ClaudeOperationError`: `vidbyte/lib/errors/base.py`.
10. **Packaging and docs.**
    - The `claude` extra in `pyproject.toml`.
    - The byte-exact `vidbyte/harnesses/native/__init__.py` marker.
    - The request.md §C texts in `REPO_MAP.md` and `vidbyte/harnesses/README.md`.

## §12.3 rows

| Row | File | Commit(s) | Done |
|---|---|---|---|
| 1 | `vidbyte/harnesses/native/__init__.py` | 450b7c35 | ✔ committed blob SHA-256 `0374a2c8…942f497a` matches |
| 2 | `vidbyte/harnesses/native/claude/__init__.py` | 8a08732e | ✔ |
| 3 | `vidbyte/harnesses/native/claude/host.py` | b7e5332a, 5edf1a4d | ✔ |
| 4 | `vidbyte/harnesses/native/claude/sdk.py` | a38b8e37, 5edf1a4d | ✔ |
| 5 | `vidbyte/harnesses/native/claude/options.py` | 8429f941, 5edf1a4d | ✔ |
| 6 | `vidbyte/harnesses/native/claude/failures.py` | 5168fb9a, f0c84cd0, ca0be69a, 5edf1a4d | ✔ |
| 7 | `vidbyte/harnesses/native/claude/session.py` | ca0be69a, 5edf1a4d | ✔ |
| 8 | `vidbyte/harnesses/native/claude/history.py` | 75eef0b4 | ✔ |
| 9 | `vidbyte/harnesses/native/claude/probe.py` | e13f35ae, dceb2dfe, e7382a26, 5edf1a4d | ✔ |
| 10 | `vidbyte/harnesses/native/claude/tool_server.py` | 5982f9e5, 5edf1a4d | ✔ |
| 11 | `vidbyte/lib/dataclasses/claude.py` | 8facd70d, dceb2dfe, e7382a26, 5edf1a4d | ✔ |
| 12 | `vidbyte/lib/dataclasses/claude_host.py` | 04290c3b | ✔ |
| 13 | `vidbyte/lib/enums/claude.py` | 34f27cdc | ✔ |
| 14 | `vidbyte/lib/constants/claude.py` | ae6d6482, 5168fb9a, f0c84cd0, e13f35ae, 5edf1a4d | ✔ |
| 15 | `vidbyte/tools/builtins/claude/__init__.py` | 47f7a422 | ✔ |
| 16 | `vidbyte/tools/builtins/claude/_base.py` | 39f57d21, 5edf1a4d | ✔ |
| 17 | `vidbyte/tools/builtins/claude/descriptions.py` | 0981a55e | ✔ 28 constants, each 4–5 sentences |
| 18 | `vidbyte/tools/builtins/claude/readiness.py` | f7788954 | ✔ |
| 19 | `vidbyte/tools/builtins/claude/sessions.py` | d4541c33, 5edf1a4d | ✔ |
| 20 | `vidbyte/tools/builtins/claude/history.py` | 372c0d8e | ✔ |
| 21 | `vidbyte/tools/builtins/claude/turns.py` | 7977493c | ✔ |
| 22 | `vidbyte/tools/toolsets/claude.py` | 57c9e722, 5edf1a4d | ✔ |
| 23 | `vidbyte/lib/enums/failure.py` | 6d8a311f | ✔ insert-only (+16 −0) |
| 24 | `vidbyte/lib/enums/__init__.py` | 7dbcc818 | ✔ insert-only (+36 −0) |
| 25 | `vidbyte/lib/errors/base.py` | 2a6de8ae, 5edf1a4d | ✔ insert-only (+32 −0) |
| 26 | `vidbyte/lib/errors/__init__.py` | eb5f34d6 | ✔ insert-only (+2 −0) |
| 27 | `vidbyte/tools/builtins/__init__.py` | cd7e91bf | ✔ insert-only (+33 −0), CRLF kept |
| 28 | `vidbyte/tools/toolsets/__init__.py` | bc82d9b0 | ✔ insert-only (+3 −0) |
| 29 | `pyproject.toml` | 47ba638d | ✔ insert-only (+3 −0) |
| 30 | `REPO_MAP.md` | 14dd7231 | ✔ request.md §C text, taken programmatically from request.md:202-204 (+4 −0) |
| 31 | `vidbyte/harnesses/README.md` | 14dd7231 | ✔ request.md §C bullet, taken from request.md:208 (+1 −0) |

**§12.4.**
- Every checklist item was re-checked by grep or by lint:
  - every `zip` passes `strict`;
  - no `asyncio.Lock`, no `print`, no `shell=True` and no `open(`;
  - no `def request`;
  - no `str(exc)` or `repr(exc)` outside header prose;
  - `claude_agent_sdk` is imported only in `sdk.py`;
  - `ClaudeHost` is imported only under `TYPE_CHECKING` in the tools;
  - every file is under 1,000 lines (the largest is `dataclasses/claude.py` at 578).
- Every comment line the branch adds fits in 72 columns. The comment-format check `awk 'length($0) > 72' | grep '^\s*#'` finds no added lines.

**§12.5.** All four exports, the extra and both doc inserts are done. Nothing listed under "Deliberately not done" was done.

## Deviations

The full list, with reasons, is in spec.md under "Implementation deviations" (§17), items 1–11. In short:

1. Row 14 has extra constants: operation names and initialize-answer field keys. They keep literals out of code (A007, S054).
2. `invalid_argument` covers only the connect and fork operations.
   - `from_exception` has no try of its own.
   - `ClaudeProbe.models` maps its own conversion failures.
3. New helpers, each replacing code that would repeat: `ClaudeFailureMapper.error` and `.usage_limited`, `_ClaudeFieldRules.text`, and the host's `_empty`.
4. `ClaudeProbe.readiness` returns `(readiness, answer)`, so models probes once. A private `_suffix` helper normalizes Windows suffixes.
5. The second wait after a cancellation is `asyncio.wait({closing})`, not a second `shield`. It still never cancels the close.
6. The options helpers name their parameter `spawn`, because lint treats `request` as an external-boundary token.
7. Session state:
   - Live and busy are derived from snapshot statuses, with no session-id map.
   - Snapshots are updated with `replace`.
   - Private helpers `_take_steer`, `_stop_waiting`, `_on_assistant` and `_refused`, plus steer numbers.
8. Host checks:
   - Continue's busy check runs inline, in the spec order.
   - Launch's template checks run before `_admit`.
   - Re-entry is not refused (EC-61).
9. Row 16:
   - `_argument` is the existing `BaseTool._optional_argument`.
   - Specs use `input_schema` only, through `_spec`, which carries an `@intent` for its `permission` name.
   - `_rendered` takes a JSON-ready payload.
10. Parameter descriptions with one meaning are shared constants.
11. The 72-column comment rewrap is one style commit, `5edf1a4d`. It also restored a lost space in `_base.py` (`schema = {`).

## Files touched outside §12.3

None. All 31 changed source files are §12.3 rows: 22 created and 9 modified. Besides those, only `docs/spec/claude-host/spec.md` (frontmatter, the §17 row and the deviations list) and this report changed, which the briefing allows.

## Budget (§8.4)

| Item | Allowed | Used |
|---|---|---|
| New files | 22 | 22 |
| New classes | 69 | 69 |

The 69 classes are made up of:
- 10 in the host;
- 9 in `dataclasses/claude.py`: 8 records and `_ClaudeFieldRules`;
- 15 in `dataclasses/claude_host.py`;
- 17 enums;
- 1 error (in `errors/base.py`);
- 16 tool classes;
- 1 toolset.

| Item | Allowed | Used |
|---|---|---|
| New dependencies | 1 optional | 1: `claude-agent-sdk>=0.2.165,<0.3.0` in the `claude` extra |
| Root `vidbyte` exports | 0 | 0 (public API contract unchanged) |
| CLI commands | 0 | 0 |

## Gates (final lines)

All gates ran from the worktree. `vidbyte` resolves to `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-claude-host\vidbyte\__init__.py`.

- **Pack:** `PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host -q -p no:cacheprovider`
  ```
  ........................................................................ [ 87%]
  .....................                                                    [100%]
  165 passed in 7.23s
  ```
- **Pack without the extra** (the CI view, with `sys.modules['claude_agent_sdk'] = None`):
  ```
  165 passed in 6.06s
  ci-view exit=0
  ```
- **Lint:** `PYTHONPATH=$(pwd) python lint/run.py`
  ```
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

  SDK-LINT: PASS
  ```
  `lint/run.py --all --format json` reports `exit_code 0` and zero findings on any path containing `claude`.
- **Full gate, source stage:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
  ```
  reasoning trace contracts: ok (182 tools, 55 shapes)
  ====================== 4100 passed, 27 skipped in 55.11s ======================
  CI passed.
  exit=0
  ```
  The baseline without the pack was 3935 passed and 27 skipped; 3935 + 165 = 4100.
- **Full gate, package stage:** `python scripts/run_ci.py --stage package`, with no `PYTHONPATH`
  ```
  ...vidbyte_sdk-0.2.1-py3-none-any.whl: PASSED   (twine)
  Installed vidbyte-sdk 0.2.1 passed smoke checks.
  CI passed.
  exit=0
  ```
- **Semgrep 1.170.1:** `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, with the semgrep venv's `Scripts` first on `PATH`
  ```
  ✅ Scan completed successfully.
   • Findings: 0 (0 blocking)
  Ran 1 rule on 915 files: 0 findings.
  ```
- **Public API:** `python scripts/generate-sdk-public-api.py --check`
  ```
  contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).
  ```
- **Offline SDK smoke:** `cd scratchpad/smoke && python -I claude_smoke.py`. It runs against claude-agent-sdk 0.2.165, starts no process and connects no client.
  ```
  image prompt messages: 1
  SMOKE: PASS
  ```
- **mypy** (`--config-file lint/mypy.ini`): no finding on any claude path.
- **Ruff** on the touched files: one finding, `vidbyte\lib\errors\__init__.py:22:1: I001`. It predates this branch: `CodexAgentError`, `AllModelsFailedError` and `TaskLedgerError` are already out of order on main. It is within the S051 baseline, and fixing it would reorder shared lines, which the contract forbids. All new files are clean.

## Tricky parts

- **The pump's call depth.** `ClaudeLiveSession.run` calls `_read`, which hands each message kind to an `_on_<kind>` helper through a short `isinstance` chain. That is one level deeper than principle 1 strictly allows. Folding the handlers into `run` would push it past the S008 complexity and S024 nesting limits. A reviewer may flag it.
- **Steers and grace.**
  - A steer stores its message under a number. The pump sends the message after the interrupted prompt's own result.
  - `_steered` records the last number sent, so a steer can tell whether its message went out or was dropped.
  - The grace is aimed by prompt number (`_prompts_sent` and `_results_read`), so a late result never cancels the grace of a later prompt.
  - This is the most timing-sensitive code in the PR. The fake-SDK tests in `test_claude_host_stops.py` and `test_claude_host_turns.py` cover it, but no real CLI has run it.
- **Lint vocabulary.**
  - A007 treats `request` as an operational call name. `several = len(prompts) > 1` has to be a separate statement in the host's launch.
  - A002 flags any `_request` attribute or `permission` name. That is why the tool base, the toolset and three session tools carry `@intent` blocks.
  - The options helpers take `spawn`, not `request`.
- **Shared `__all__` with a comment.** `vidbyte/tools/builtins/__init__.py` has a `# Memory providers` comment inside `__all__`. A comment-aware script inserted the 15 names at their sorted places and kept the file's CRLF.
- **mypy `Any | None`.** `call.arguments.get(...)` is rejected for typed host parameters. Every argument is read through `BaseTool._optional_argument`, which returns `Any`.
- **Late comment rewrap.**
  - The §12.4 rule of 72-column comments was applied in one style commit across 13 files.
  - The automatic refill merged two `@intent` blocks with the step narration under them, in `failures.py` and `options.py`. A bare `#` line now separates them again, and the same was done in `toolsets/claude.py`.
  - Comments in shared files that predate the branch were left alone.
- **No live run.** By rule, no `claude` process was started. Behaviour is proven against the S2 fake SDK, and option building against the real SDK package offline.

## Open items

- **Not verified live** (the briefing forbids starting the real `claude` CLI). These need a live check:
  - that Claude Code 2.1.296 or later accepts `--permission-prompts none`;
  - the initialize-answer keys `account`, `apiKeySource` and `apiProvider` with value `firstParty`;
  - how quickly a real CLI answers `interrupt()`, relative to `CLAUDE_INTERRUPT_GRACE_SECONDS`;
  - the shape of real `rate_limit_event` windows;
  - the native `claude.exe` lookup on a real Windows install.
- **Behind main.** `feat/claude-host` is 41 commits behind `origin/main`.
  - `git merge-tree` shows a clean merge.
  - Among the files this PR touches and `lint/`, main changed only `vidbyte/harnesses/stores/file.py`.
  - Catch up by merge, never rebase, when the orchestrator decides.
- **CI not dispatched,** per the briefing.
