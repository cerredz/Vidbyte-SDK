---
slug: native-grok-opencode-meta-hosts
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts
branch: feat/native-grok-opencode-meta-hosts
base_commit: aa8c380c4cd1d5791526dd545f5ef1020b28a5cc
s3_head: de5b7c4c
s2_head: 91e874b2 (cfad74f8 → a716c858 [D-1..D-3] → 762b68e7 [r5 catalog row] → 91e874b2 [D-4..D-6])
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1036
until: none
started: 2026-10-13 01:30 UTC
---

# Pipeline: GrokHost, OpencodeHost, MuseHost (Meta Muse Code), and GLM / DeepSeek backend profiles, with exhaustive error handling

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-13 01:30 UTC | 2026-10-13 02:20 UTC | reports/S0-scout.md | base_commit aa8c380c; code-map.md, 4 sections, 21 notes |
| S1 spec + review | done | 2026-10-13 02:22 UTC | 2026-10-13 05:40 UTC | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | spec r3 @f1b2fa31 approved; r1 review SOUND WITH FIXES (15/15 accepted), r2 review SOUND WITH FIXES (11/11 accepted) |
| S2 tests | done | 2026-10-13 05:50 UTC | 2026-10-13 07:35 UTC | reports/S2-test-author.md | 1635 tests (grok 458, opencode 581, muse 458, backends 138), all red; S2_HEAD cfad74f8 |
| S3 implement | done | 2026-10-13 08:20 UTC | 2026-10-13 13:40 UTC | reports/S3-implementer.md | S3_HEAD de5b7c4c; draft PR #1036; 51 commits; budget 56/56 create, 12/12 modify, 66/66 records, 13/13 enums, 53/53 codes; 1616 passed, 19 skipped (re-run by orchestrator); full gate + Semgrep green; ci.yml 38379243965 dispatched, static-policy 38379248609 success |
| S4 adversarial review | running | 2026-10-13 13:50 UTC | | reports/S4-review-{conformance,conventions,engineering}.md | 3 reviewers launched in parallel on de5b7c4c |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (round 2 focused on the r2 changes)
- S5 repair iterations: 0/8
- S5 re-review rounds: 0/2

## Decisions the orchestrator made

- **2026-10-13 01:30 — Scope is the catalog's ★ set for each target, plus `build_opencode_backend_provider`.**
  - Why: Prompt 2's "for now" applied the same way as the upstream Codex first PR. The added function is the only runnable GLM/DeepSeek route while ClaudeHost is unmerged.
  - Recorded as request.md Q-1, default ★ only.
- **2026-10-13 01:30 — GrokHost's ACP code is protocol-generic but not a public `AcpHost`.**
  - Why: Prompt 2 narrows to five targets, and the upstream ledger rejects a base class that has only one implementation.
- **2026-10-13 01:30 — This PR follows the codex-host/claude-host shared-file contract.**
  - `native/__init__.py` must have SHA-256 `0374a2c8…497a`.
  - Tests go only in host-named folders.
  - Export indexes are edited append-only.
  - `pyproject.toml` stays unchanged unless Q-2 is resolved with evidence.
  - Why: three PRs create `vidbyte/harnesses/native/` in parallel.
- **2026-10-13 02:20 — Muse transport wording.** request.md §C quotes the catalog verbatim, so it still says "Talks MSP through `muse-code-sdk`" (request.md:598). That line is the catalog's description, not a decision. Q-2 (default: no new dependency) governs how Muse is reached.
  - Why: the scout flagged the two lines as conflicting (code-map §4.11).

- 2026-10-13 03:50 — S1 review r1 (SOUND WITH FIXES; 2 Blocker, 9 Major, 4 Minor) was passed to the author by path instead of pasted. The report file holds the findings verbatim (reports/S1-spec-review.md:23-219). Why: the findings are 25 KB and the author can read files, which keeps the orchestrator's context small.
- 2026-10-13 03:50 — The author was told the in-distro WSL kill (R-4) is the orchestrator's request.md Q-8 default, not a user decision. Downgrading it needs evidence beyond idle-only runs. Why: the user asked for "extensively handle errors for every single function", and an orphaned Muse process could keep editing files.

- 2026-10-13 05:10 — Bootstrap: no `pip install -e` from this worktree. The global Python 3.11.0 has `vidbyte-sdk` 0.2.1 installed editable from the canonical checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`, and its dev tools are already there (pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1). Re-pointing that install would break the parallel codex-host and claude-host pipelines and the main checkout. Every stage runs with `PYTHONPATH=<worktree>` instead, as the field guide's `local-ci-verification.md` says. Why: the editable install is shared state across every pipeline.
- 2026-10-13 05:40 — Spec Q-14, Q-15, Q-17, Q-18 and Q-19 take their stated defaults (no / not built). Request Q-1..Q-13 were resolved in spec §8.1; Q-16 was resolved by building D-23. Why: S1 rule, no planned stop.
- 2026-10-13 07:35 — S2_HEAD = cfad74f8 (tests at e8289019; spec proof column and S2 report at cfad74f8). Later stages diff `tests/` against this SHA. I re-ran the red proof: `native_backends` 138 errors; `grok_host` 89 failed, 13 skipped, 356 errors.
- 2026-10-13 07:35 — S2's 14 spec ambiguities go to the spec author for r4, before S3. The spec must state each reading the tests took. Any reading the author thinks is wrong comes back to me and goes to the test author. Why: the skill says to resolve spec defects before S3, and the tests are the contract.
- 2026-10-13 08:05 — Spec r4 (1f97640b, `status: tests-written`) states the reading the tests took for each of S2's 14 ambiguities, plus S2-15. Nothing was routed back to the test author. The transport's dispatch fix is now named as INV-18's one exception: a server request whose `id` collides with a pending client request is dropped instead of failing that request.
- 2026-10-13 08:05 — The test author was asked to merge its §6.2 Proof values (put in a 7th cell) into the 6-column table. Why: the spec should render correctly on GitHub, and the test author owns that column.
- 2026-10-13 08:55 — S3 reported BLOCKED after P1 on three S2 test defects. I decided them myself, because the spec already answers all three:
  - D-1: a test expected a plain `set` of enum members to be rejected. Spec §9.1, EC-23, EC-134 and §16 S2-4 say a set is accepted.
  - D-2 and D-3: test helpers passed `argv` / `workspace` twice, causing a `TypeError` before any SDK code ran.

  The S2 test author fixed them at 66d5c3bb (3 files, 4+/4−). I checked the diff `git diff cfad74f8..HEAD -- tests/`: exactly those 3 files. S2_HEAD moves to a716c858; later test-tree diffs use this base. I ran the fix and S3's resume one after the other, not in parallel, because both agents commit in the same worktree.
- 2026-10-13 08:55 — The S2 author reports `lint/run.py` SDK-LINT: FAIL. Rule A007 has 263 findings against an allowance of 255, caused by P1 code: `lib/dataclasses/grok.py` 4, `lib/process/runner.py` 4, `lib/process/managed.py` 2. S3 had reported PASS. This was handed to S3 to fix at the source.
- 2026-10-13 09:40 — S3 reported BLOCKED a second time, at the start of P3: in spec §6.3.1, `muse.budget_exhausted`'s exact next-step text did not contain its own required token `continue_muse_session`. I took the implementer's option 1 and put the token into the text, which matches every other row, where the token names the function to call. The fix went in three steps: spec r5 (254ebc53), a one-line change to the test CATALOG row (762b68e7, verified 1 file, 1+/1−), then resuming S3 to update `NATIVE_HOST_NEXT_STEPS`. S2_HEAD moves to 762b68e7.
- 2026-10-13 12:10 — S3 reported BLOCKED a third time, after building all 68 rows. I ruled on four items:
  - D-4: the test's argv guard contradicted itself. The fix makes it match the approve-everything flag only as a whole argv element or as a `--flag=` prefix. Prompt text inside `--single=` is data.
  - D-5: a flaky fixture ordered peer logs by PID. It now uses an atomic launch counter.
  - D-6: wrong expected opencode ids. The fake was right.

  The test author fixed all three at 209c4085 (9 test files, +47/−16; I checked the diff against 762b68e7). Two runs gave 1 failed and 1615 passed; the one failure is the EC-95 test. S2_HEAD moves to 91e874b2.
- 2026-10-13 12:10 — EC-95 (exit code 127 means `muse.not_installed`) needed an exit code that §8.5 did not expose. I approved S3's option 1: spec r6 (f4659a58) adds read-only `McpStdioTransport.returncode` and `NativePeer.exit_code`. The spec author also raised D-3's reversal trigger from about 160 to about 200 changed lines, because the extension now has about 167. I accepted that, but flagged transport size for S4 reviewers to judge independently. Why: the spec row explicitly asks for exit 127, and the 9-line change is already tested.
- 2026-10-13 12:10 — The harness flagged the S2 author's status message as instruction-shaped ("bypass-permissions"). It only described the test guard rejecting the vendor value `bypassPermissions`. Not an injection; no action taken.
- 2026-10-13 14:00 — Remote `ci.yml` run 38379243965 on 9d51a3fb ended `failure`. Source / Python 3.11 passed; Source / Python 3.12 failed with 1 failed, 5572 passed, 31 skipped. The failing test is `tests/features/grok_host/test_grok_host_turns.py::test_interrupt_raises_process_exited_when_the_cancel_write_fails` (EC-51, `@posix_only`, so it skips on Windows): `DID NOT RAISE NativeHostError` at line 335. The log is saved at scratchpad `ci-38379243965-failed.log`. I re-ran the failed job (`gh run rerun --failed`) to tell a flaky test from a defect that depends on the Python version. Either way it goes to the S4 verifier as an item to adjudicate, and S5 must make remote CI green. Why: a Linux-only path (closed-stdin write detection under asyncio 3.12) never ran locally.

## User replies (verbatim)
(none during the run)

## Niche facts accumulated (carried into every later briefing)

### Lint and gates
- **S011 bans `import httpx`** outside `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` (baseline 0).
  - opencode must go through `HttpTransport.request` (`lib/http/transport.py:55`), or change that owner module.
  - `HttpTransport.request` has no SSE, no query params, and creates a new client per call. — *source:* S0 code-map §4.1
- **The full-lint pass line is `SDK-LINT: PASS`**, not `AGENT-LINT`. — *source:* S0
- **Semgrep is not part of `run_ci.py`.**
  - Static policy: `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, using semgrep 1.170.1 from the venv at `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1`. — *source:* S0 code-map §1
- **Source and package stages need different `PYTHONPATH` settings.**
  - Source stage: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`.
  - Package stage and full gate: run with no `PYTHONPATH`. — *source:* S0 code-map §1
- **S039 bans `asyncio.Lock`.** The precedent is `asyncio.Semaphore(1)` at `vidbyte/agents/codex/agent.py:82-86`. — *source:* S0
- **S045 (ASYNC109) flags an async parameter named `timeout`.** Use `timeout_seconds`. — *source:* S0
- **S012 flags every `.request(` call without a timeout** (baseline 0). — *source:* S0
- **C012 requires `ProviderModelRegistry` proof for model fields.**
  - It applies to `model` / `*_model` str fields on `*Settings`, `*Config`, `*Spec` and `*Options` classes, and the registry is strict.
  - Vendor model strings (Grok, opencode `provider/model`, Muse, `glm-5.3[1m]`) are not in that registry.
  - Exemptions are rows inside the rule file; editing that file may count as weakening a rule. — *source:* S0 code-map §4.14

### Module layout and packaging
- **Don't copy the `builtins/sessions/` layout for headers or error handling.** It is baseline debt: a non-A001 header, raw exception text (S017), adjacent literals (S062), and a sync `_caught`.
  - Headers: copy `vidbyte/tools/toolsets/coding.py:1-12`.
  - Error translation: copy `vidbyte/agents/codex/transport.py`. — *source:* S0
- **`vidbyte/tools/mcp/transport.py` does not fit ACP or MSP as-is.**
  - It drops notifications (`:416-418`).
  - It can't answer server requests (`:419-450`).
  - `request()` has no timeout keyword (`:222-226`).
  - A006 does allow the `harnesses` → `tools.mcp` import. — *source:* S0 code-map §4.2
- **No process-tree kill exists in the SDK.** On Windows the SDK kills only the direct child (`bash.py:9`). The Muse `.cmd` shim routes arguments through `cmd.exe` `%*` parsing. — *source:* S0 code-map §4.9-10
- **Commit order for the public API.**
  - `scripts/generate-sdk-public-api.py` refuses to run while `vidbyte/__init__.py` has uncommitted changes.
  - So commit the export first, then regenerate `contracts/sdk-public-api.json`. — *source:* S0 code-map §4.16
- **C015 plus the frozen `pyproject.toml`:** no non-.py, non-README data files may live under `vidbyte/` (no vendored JSON schemas or fixtures). — *source:* S0 code-map §4.17

### Failure codes
- **`FailureCode` spans `vidbyte/lib/enums/failure.py:25-144`.**
  - The CODEX block is lines 35-46. Line 34 sits directly before it (Claude's suggested spot) and line 47 directly after it (Codex's spot).
  - Safe insertion spots for this PR: after 144, between 67 and 68, between 99 and 100, or between 129 and 130. — *source:* S0
- **Only `codex.*` codes need classification rows,** enforced by `tests/test_codex_failure_recovery.py:192-202`. No table exists for other prefixes. — *source:* S0

### Tool exposure
- **MCP runs tools without a permission check.** `mcp_server/handlers.py:84-88` calls `tool.execute` with no `PermissionPolicy`, no validation and no timeout.
  - The server is serial, so a blocking `wait_*` tool stalls every other call.
  - It serves only the tools passed to `McpStudioServer(tools=...)`. — *source:* S0 code-map §4.5, §4.7
- **Every public `BaseTool` exported from `vidbyte.tools.builtins` becomes YAML-declarable,** including WRITE tools (`lib/registries/components.py:101-124`). — *source:* S0 code-map §4.6
- **Dynamic tools inside a Codex agent are cancelled at 300 s** (`lib/constants/codex.py:193`). — *source:* S0 code-map §4.8
- Installed Grok is 1.0.52, not 1.0.13: the facts marked verified in the spec come from 1.0.52 (spec A-2); the version floor stays 1.0.13. — *source:* S1 author
- S054: no string literal may be assigned to a password/token/secret-named identifier (hence `OPENCODE_SERVER_LOGIN`, `server_password: str | None`). — *source:* S1 author
- Spec contract names: launchers are argv prefixes `grok_command`/`opencode_command`/`muse_command` (D-19); fake Grok/Muse peers are `(sys.executable, "-u", script)`; opencode HTTP is faked by patching `vidbyte.lib.http.transport.httpx.AsyncClient` with `httpx.MockTransport`; one error type `NativeHostError(AgentExecutionError)`; 53 codes appended after `RULE_EVALUATION_FAILED`; shared plumbing in `vidbyte.harnesses.native.hostkit`; process helpers in new `vidbyte.lib.process`. — *source:* S1 author
- Byte-identical files (spec INV-22): root `vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `vidbyte/tools/builtins/__init__.py`, `lib/dataclasses/__init__.py`, `lib/constants/__init__.py`, `pyproject.toml`. Transport-extension tests live in `tests/features/grok_host/` (no existing test file may be edited). — *source:* S1 author
- PR body must state limitations T-1, T-2, T-5, T-7 (spec §10) and assumptions A-5 (headless Grok refuses approval-needing tools, unverifiable without a prompt) and A-7 (opencode revert restores files). — *source:* S1 author
- MSP 1.0.1 requires a client-made UUIDv7 `commandId` on session/start, resume, fork, approval/decide, userInput/cancel and turn/*. `turn/steer` needs `expectedTurnId`. Fork takes `cutPoint:{lastTurnId}`. A fresh turn's `turnId` equals its `commandId`. Stdlib `uuid.uuid7` exists only on Python 3.14+, so `MuseWire.new_command_id()` builds the id itself. — *source:* S1 review r1 R-1
- `grok agent` must get `--no-leader`, because the user's `[cli] use_leader` config otherwise attaches to a shared leader. — *source:* S1 review r1 R-7
- `ToolsFormatter` forwards the metadata keys `hint`, `retryable` and `detail`, not `next_step`. `ToolExecutor` runs `validate_call` before `execute` (`executor.py:61-66`). — *source:* S1 review r1
- Transport: the new options are `exit_grace_seconds: float | None = None` and `stop_process_tree: bool = False`. With both at defaults, close behaves exactly as before (INV-18). C002 and C006 traps apply to inline `isinstance(x, bool)` and to `__init__` guards, so both go through `RecordFieldValidator`. — *source:* S1 author r2
- AC-20: each entry module must import cleanly in a fresh interpreter. If it passes only with a function-level import, report BLOCKED (spec §14). — *source:* S1 author r2
- The installed Grok is 1.0.52, not 1.0.13. A top-level `grok --single` run has no `--no-leader` flag (A-18). The Grok argv is `grok agent --no-leader --model=MODEL stdio`, with `--name=value` argument form. — *source:* S1 r3
- Muse in-distro cleanup is `wsl.exe -d <distro> -e sh -s <mark>`, with the script on stdin. There is deliberately no `--`. The mark is 32 lowercase hex characters checked against `MUSE_PEER_MARK_PATTERN`. The cleanup env is `NativeChildEnvironment.build({})`, never the peer's overlay. The script can be tested on Linux CI. — *source:* S1 r3
- `stop_tree` assumes `start_new_session=True`. On POSIX it always kills the process group (TERM then KILL), even after the leader has exited. Windows uses `taskkill /T /F`. The residual risk is stated in EC-10, A-9 and T-7. — *source:* S1 r3
- `muse/wire.py` reads `vidbyte.__version__` at call time through a module-level `import vidbyte`, for MSP `clientInfo.version`. — *source:* S1 r3
- Timing constants must be read through the module at call time (for example `native_hosts.NATIVE_STOP_GRACE_SECONDS`). Tests patch the module, so a `from … import` copy breaks the time-bound tests. — *source:* S2
- Resolve `wsl.exe` with `shutil.which`. A bare `wsl.exe` finds System32 before PATH and runs the real one instead of the test fake. — *source:* S2
- In AC-1 on Windows, `grok` is a `grok.cmd` shim on a PATH limited to that folder plus System32, and HOME/USERPROFILE are empty. The fake grok reads its role from argv: `models`/`agent` must come first, `--version` can appear anywhere, and a one-shot is recognised by `--single=`. — *source:* S2
- opencode's `abort` returns `200 true` and `diff` returns `200 []` even for a missing session, so the host calls `GET /session/{id}` first. Take the message baseline before `prompt_async`. — *source:* S2
- AC-18 needs `import vidbyte` to load `vidbyte.tools.toolsets.{grok,opencode,muse,harness_backends}`. `test_method_frames_are_dropped_without_a_callback` is the regression proof for the transport dispatch fix. — *source:* S2
- The suite runs fast: all four packs red in about 16 s on Windows. The 19 skips are platform guards that should run on Linux CI. — *source:* S2
- Lint rules A002 and A007 skip untracked files, so `git add` new files before running `python lint/run.py`. S3's first "PASS" was false for this reason. — *source:* S3
- A007 matches whole split tokens (`byte` yes, `bytes` no) and flags literals near read/send/request/sleep calls. A002 wants `# @intent` near any `def` whose identifiers contain request/send/transport/subprocess/provider/permission; its slack is 625/703. S024 allows nesting depth 3 at most. — *source:* S3
- `NativePeer.call` re-raises JSON-RPC error answers as `McpProtocolError` with `details["error"]`, for each host's wire code to map; transport failures become `NativeHostError`. The transport change came out at +156/−8 lines. — *source:* S3
- Semgrep on this machine needs `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH"`. The global pysemgrep breaks under mcp 2.x. — *source:* S3
- `McpStdioTransport.returncode` is saved in `_detach_process_state`, so it survives `close()`. The transport diff is +166/−8. — *source:* S3
- S3 deviations are listed under spec §17 "Implementation deviations". Two of them:
  - (8) `list_harness_backends` has no §12.4 try, because it returns a constant.
  - The opencode list tools return wrapped objects such as `{"models": ...}`, which S6 must state.
  — *source:* S3
- An untested race: when `turn/completed` and a -32030 answer arrive together, a Muse steer may raise `api_error` (vendor_code -32030) instead of `turn_not_found`. That follows EC-115/EC-102 as written. — *source:* S3

