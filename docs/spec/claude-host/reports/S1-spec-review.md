VERDICT: SOUND WITH FIXES — The host design, its readings of claude-agent-sdk 0.2.165 and the shared-file inserts hold; the three Blockers and three Majors are local spec edits (how the marker hash is taken, a bounded stop after an interrupt, `repr=False` on secret fields, one verified CLI flag, Windows CLI discovery, one lint obligation), and none of them reverses a settled decision.

WHAT THE SPEC GETS RIGHT

- The optional-extra seam is right. There is one literal import in `ClaudeSdkLoader.load`, the tools and toolset import the host only under `TYPE_CHECKING`, and there is no root export. As a result, `import vidbyte` never loads `claude_agent_sdk`, and `contracts/sdk-public-api.json` stays unchanged, because C016 derives only the root `__all__` and the pyproject name and version (`lint/core/public_api_contract.py:PyprojectReader.read`).
- The SDK readings that drive the design are correct:
  - `system_prompt=None` sends `--system-prompt ""` (`subprocess_cli.py:576-577`), so D-10's preset default is needed.
  - `ResultMessage.origin`, together with "treat anything unrecognized as not human", backs D-28.
  - Cost fields are cumulative across turns (DTS:5738), which backs INV-20.
  - The exception table runs from subclass to base (`CLINotFoundError` ⊂ `CLIConnectionError`, `ResultError` ⊂ `ProcessError`).
  - `MessageParseError` really is not exported.
- The shared-file inserts land where each file's own order puts them:
  - `failure.py` :34/:35;
  - the enums at :40/:41, with the names going between `"CircularityVerdict"` and `"CodexApprovalMode"`;
  - builtins :28/:29;
  - `"ClaudeTools"` before `"CodingAgentTools"`;
  - REPO_MAP :147/:151;
  - the harnesses README bullet after :177.

  The request.md:175-184 bytes, joined with LF, hash to `0374a2c8…942f497a`. `packages.find include=["vidbyte*"]`, together with rows 1, 2 and 15, ships all three new packages in the wheel.
- §12.4 is accurate for every rule it names: A001 (no headroom), A002 (its tokens and window), A003 (the error packet), S012 (`REQUEST_METHODS`), S016 and S017 (their scopes), S025 (at least 4 sentences), S039, S045 and C011. D-12 and D-13 keep permission, budget and `cli_path` fields with the developer, never the model.

FINDINGS

R-1 [Blocker] [L10] §6.1 INV-21, §6.2 AC-19, §14 — The marker hash is taken over the bytes on disk, but on this machine git checks the file out as CRLF, so AC-19's test fails the local gate in every checkout except the one that wrote the file
  Evidence:
  - Spec:
    - INV-21 (spec:246): "byte-identical … with LF line endings and a final newline".
    - AC-19 (spec:279): "the bytes of the `vidbyte.harnesses.native` marker are hashed".
    - spec:1301: "Verify the marker file's SHA-256 after every commit that touches it."
  - Repo:
    - `git config --show-origin --get core.autocrlf` → `file:C:/Program Files/Git/etc/gitconfig true`, and there is no root `.gitattributes`.
    - `git ls-files --eol vidbyte/harnesses/__init__.py` → `i/lf w/crlf`, both in this worktree and in `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`.
    - The repo already solves this for byte-exact files. `contracts/.gitattributes` says "keep LF on every platform" (`*.json text eol=lf`), and `lint/core/public_api_contract.py:CommittedPublicApi.load` reads "without newline translation, so a CRLF checkout is caught".
  Failure:
  - S2 writes AC-19 as `sha256(Path(native.__file__).read_bytes())`. The test passes in the implementer's worktree, because that worktree wrote the file with LF.
  - The committed blob is LF, but git checks the file out as CRLF in the S3/S4 review worktrees and in `vidbyte-sdk/` after the merge. There the hash differs, pytest fails, and `python scripts/run_ci.py` fails for every later change on this machine.
  - The §14 check reports the same false mismatch, which invites someone to "fix" the contract bytes.
  Smallest fix:
  - For the orchestrator and §14 checks, define the hash over the committed blob: `git show <rev>:vidbyte/harnesses/native/__init__.py`.
  - For AC-19, define it over the file's bytes with `\r\n` normalized to `\n`.
  - Add a §13 fact: `core.autocrlf=true` here, and there is no root `.gitattributes`.
  - The contract bytes do not change.
  - The repo-precedent alternative is a `vidbyte/harnesses/native/.gitattributes` with `__init__.py text eol=lf`. It adds a file to the shared folder, so it is the orchestrator's call for both PRs.

R-2 [Blocker] [L5] §8.1 D-4, §9.2 `interrupt_claude_turn` row, §7 EC-53 — Neither the time budget nor an interrupt bounds a turn: after an acknowledged interrupt that never gets a result, the turn stays RUNNING with a live process until `aclose`, and the spec contradicts itself on this case
  Evidence:
  - Spec:
    - D-4 (spec:451): "the watchdog … calls `interrupt()`. If the interrupt raises, it disconnects."
    - spec:733: "if that raises, the client is disconnected, and either way the turn ends INTERRUPTED."
    - EC-53 (spec:354): "The turn stays RUNNING until `aclose` disconnects it. Accepted limitation."
  - request.md:
    - request.md:881: "(Codex's list from last turn still applies)".
    - request.md:494: "never hang. This exact kind of hang happened before (the 0.147 cancel-hang)".
  - SDK: `Query.close` is anyio-shielded, and `transport.close` is bounded at about 20 s, so a disconnect always returns.
  Failure:
  - A turn has `timeout_seconds=600`. The CLI is stuck in an aborted tool call: it acknowledges the interrupt but never emits the result.
  - At 600 s, `interrupt()` succeeds and then nothing more happens. The handle stays RUNNING forever:
    - `wait` keeps returning RUNNING snapshots;
    - the session id stays busy, so INV-4 refuses `continue`;
    - the `max_live_sessions` slot stays taken;
    - the `claude` process lives until `aclose`.
  - An implementer must also choose between spec:733 and EC-53, which contradict each other.
  Smallest fix:
  - After any `interrupt()` that returns, whether the watchdog or the caller sent it, wait up to a new constant `CLAUDE_INTERRUPT_GRACE_SECONDS` (row 14) for the result.
  - If no result arrives, disconnect once and finish the turn: FAILED with `budget_exhausted` for the watchdog, INTERRUPTED for the caller.
  - Replace EC-53's limitation with this rule.
  - Make spec:733 say the turn ends "when the result arrives or the grace period expires".
  - Add an AC with a fake whose `interrupt()` succeeds but whose stream never yields a result.

R-3 [Blocker] [L7] §8.5 `ClaudeMcpServer`, §9.2 `env` row — The `env` and `headers` fields carry secrets but keep the default dataclass repr, which breaks a rule in the strict-config guide that the spec itself cites for row 11
  Evidence:
  - Spec:
    - spec:581: `env: Mapping[str, str] = field(default_factory=dict) … headers: Mapping[str, str] = field(default_factory=dict)`.
    - spec:882: `env | Mapping[str, str], {}`.
    - T-3 (spec:909): "Secrets passed in `env` or MCP `headers` leak through error messages, tool outputs or logs".
  - Repo:
    - `field-guide/vidbyte-sdk/strict-config-dataclasses.md:13`: "Mark key fields `repr=False`."
    - `vidbyte/lib/dataclasses/coding.py:5,8`: "Key fields are repr=False, so printing the record never shows a key." and "Do not drop repr=False from a key field."
    - `coding.py:55-58` and `model_configs.py:51` both follow this rule.
  Failure:
  - `repr(request)` prints every `env` value and every MCP header, for example `ANTHROPIC_API_KEY` or `Authorization`. This happens in a pytest assertion diff, in a developer's log line, or in any error `details` that embeds the record.
  - INV-12 polices only reasons and tool output, so nothing in the spec stops this.
  - Review flags it against the guide that row 11 lists.
  Smallest fix:
  - Declare `ClaudeSpawnRequest.env`, `ClaudeMcpServer.env` and `ClaudeMcpServer.headers` as `field(default_factory=dict, repr=False)`.
  - Add this rule to §12.4 "Records and validation".
  - Extend AC-24 so the record's `repr` contains no `env` or header marker.

R-4 [Major] [L1] §9.2 Field mapping `permission_prompts`, A-2, D-9 — The default `permission_prompts=NONE` passes nothing, so the CLI keeps its own default `host`, and the headless "deny" behavior rests on an unverified assumption even though the matching flag is verified
  Evidence:
  - Spec:
    - spec:845: "HOST gives `can_use_tool` … NONE gives no prompt tool."
    - `ClaudeCliFlag` (spec:637) has no `permission-prompts` member.
    - A-2 (spec:1327): "a tool call that needs permission is denied rather than left waiting".
  - CLI 2.1.296:
    - `claude --help` shows `--permission-prompts <target> Who answers permission prompts with --print: "host" (the SDK host or --permission-prompt-tool) or "none" (nobody: anything that would prompt is denied automatically…) (choices: "host", "none", default: "host")`.
    - The installed claude.exe contains the string "--permission-prompts none: permission prompts are answered with a local deny".
  - SDK:
    - The SDK passes `--permission-prompt-tool stdio` only when `can_use_tool` is set (`types.py:_configure_can_use_tool`).
    - With no callback set, `_internal/query.py:_handle_control_request` (:590-591) answers a `can_use_tool` request with an error control_response: "canUseTool callback is not provided".
  Failure:
  - On every default spawn, a tool call that needs permission goes to the SDK host, and the SDK answers with a control error.
  - What the CLI does with that error is exactly assumption A-2.
  - A-2's "if wrong" branch is a turn that waits until the time budget fires, which is the unbounded case in R-2.
  Smallest fix:
  - Map NONE to `extra_args["permission-prompts"]="none"`, and add `ClaudeCliFlag.PERMISSION_PROMPTS`. List the flag in D-9 and with the §11 verified flags.
  - Map HOST to no flag (the CLI default) plus `can_use_tool`.
  - Update AC-17 and EC-42.
  - Narrow A-2 to "local denials appear in `permission_denials`".

R-5 [Major] [L5] §8.1 D-5, §12.3 row 3 — A plain `shutil.which("claude")` drops the SDK's Windows discovery rules, so an npm `claude.cmd` shim, or a native `claude.exe` that is not on PATH, breaks the host, and the error's next step sends agents into a retry loop
  Evidence:
  - Spec:
    - D-5 (spec:452): "`cli_path` is resolved at entry with `shutil.which("claude")`, never by the SDK".
    - Row 3: `shutil.which(CLAUDE_CLI_NAME) or ""`.
    - §9.2 maps `CLIConnectionError` to `claude.process_exited`, whose next step is "Respawn, then resume by id."
  - SDK `_internal/transport/subprocess_cli.py`:
    - `_find_cli`, on Windows, replaces a `which` hit that is not a native exe ("npm's claude.cmd shim (which connect() refuses to spawn)") with `shutil.which("claude.exe")`, then with `~/.local/bin/claude.exe`.
    - `_reject_windows_batch_cli` (:415, called at :807) raises `CLIConnectionError("Refusing to execute batch script …")`.
  Failure:
  - Two Windows setups break:
    - npm's `claude.cmd` comes earlier on PATH than the native `claude.exe`;
    - `claude.exe` sits only in `~/.local/bin`, which is not on PATH.
  - In both cases, the SDK on its own would run the native exe.
  - The host instead passes the shim, or `""`, which gives `not_installed`. Every spawn and every readiness probe then fails with `process_exited`.
  - An agent that follows the "Respawn" next step retries forever.
  - This machine is not affected: `which` returns `C:\users\422mi\.local\bin\claude.EXE`, and there is no `.cmd` on PATH.
  Smallest fix:
  - In D-5 and row 3, resolve the CLI the way `_find_cli` does, minus the bundled copy:
    - on Windows, a `which` hit that is not a native `.exe` falls back to `which("claude.exe")`, then to `~/.local/bin/claude.exe`;
    - a path that still ends in `.cmd` or `.bat` reports `claude.not_installed` before connect, with "install the native claude.exe or pass cli_path".
  - Add one EC for this case.

R-6 [Major] [L8] §12.4 — The checklist omits S054, which has no headroom, even though A-7 and the "policy strings are constants" rule lead straight to an S105 finding
  Evidence:
  - Spec:
    - §12.4 (spec:1127-1200) has no S054 line.
    - A-7 (spec:1332): "`tokenSource` or `apiKeySource` is present and not `none`".
    - §12.4 also says: "Numeric bounds and policy strings are `CLAUDE_*` constants".
  - Repo:
    - `lint/rules/s054_bandit_security_subset.py` covers `{S105,S106,S107,S108,S301,S302,S501}`.
    - `lint/baseline.json:81` sets `"S054": 3`.
    - `ruff check --no-cache --isolated --select S105,S106,S107,S108,S301,S302,S501 vidbyte` (the pinned ruff 0.16.4) finds exactly 3 findings, among them `TOKEN_BUDGET_FINAL_RESPONSE_NOTICE` and `TRIM_TO_TOKEN_BUDGET`.
  - A stdin ruff probe:
    - flags `CLAUDE_TOKEN_SOURCE_NONE = "none"` and `token_source != "none"`;
    - does not flag `CLAUDE_MAX_OUTPUT_TOKENS_ENV` or `account.get("tokenSource") not in (None, "none")`.
  Failure: Suppose `ClaudeProbe.signed_in` keeps `tokenSource` in a local named `token_source` and compares it with `"none"`, or defines the constant the checklist asks for. That adds a fourth S054 finding, and lint ends with `SDK-LINT: FAIL`.
  Smallest fix:
  - Add to §12.4: "S054: no string literal is assigned to, or compared with, a name that contains token, password, secret or pwd as a whole word. For example, compare `account.get("tokenSource")` inline."
  - Add S054 to the one-rule lint list in §14.

R-7 [Minor] [L9] §6.3 NFR-1 — The package-smoke target is false
  Evidence:
  - spec:399: "Every module named in INV-1 imports in the package smoke."
  - `scripts/run_ci.py` `_smoke_program` imports only `vidbyte`, `Prompts` and `VidbyteSDK`, and then runs the two entry points. Because of D-17 (no root export), it never imports `vidbyte.harnesses.native` or `vidbyte.harnesses.native.claude`.
  Failure: An implementer either edits `scripts/run_ci.py`, which is outside §12.3, or leaves NFR-1 unmet.
  Smallest fix: Reword the target: AC-1 and AC-2 prove INV-1 in the source stage with the extra absent; the package smoke covers only the builtins and toolsets chain that `import vidbyte` loads.

R-8 [Minor] [L9] FR-17, §9.2, row 14 — FR-17 promises a next step for every code, but the spec gives no text for the four generic codes the host raises
  Evidence:
  - FR-17 (spec:386): "Each has a next step, mapped as §9.2 states."
  - INV-2 requires a non-empty `next_step`.
  - §9.2 and row 14 define next steps only for the 16 `claude.*` codes and `CLAUDE_LIVE_CAP_NEXT_STEP`.
  - AC-23 limits `CLAUDE_FAILURE_NEXT_STEPS` to exactly those 16 codes.
  Failure: Each call site that raises `configuration.invalid_argument`, `configuration.unsupported_combination`, `input.empty` or `action.precondition_failed` invents its own wording, either inline or as constants that row 14 does not list.
  Smallest fix: Add four `CLAUDE_*_NEXT_STEP` constants, one sentence each, to row 14 and to the §9.2 code table.

R-9 [Minor] [L1] FR-12, D-3, row 17 — The steer contract does not say that a steer stops the current step and kills background tasks
  Evidence:
  - FR-12 (spec:381): "redirects a running turn with a new message".
  - DTS:4571: when `perTaskStopAffordance` is absent, "the interrupt kills background tasks".
  - The 0.2.165 `Query.initialize` request never sends `perTaskStopAffordance`.
  Failure: The steer tool's 4–5 sentences describe a gentle redirect. A calling model then steers while a background agent or a long Bash job is running, and that work is lost without any message.
  Smallest fix: State in FR-12, and in the steer tool and parameter descriptions (row 17), that steering stops the current step and any background work before the new message runs.

R-10 [Minor] [L7] §10 T-2/T-4, D-12, EC-45/EC-53 — The accepted security limitations are written only in `docs/`, which AGENTS.md makes opaque, so no code header carries them
  Evidence:
  - T-4 (spec:910): "The ungated MCP path is an accepted limitation (Q-2)".
  - T-2 (spec:908): "The history tools can still read any project".
  - D-12 runs custom tools with `PermissionPolicy.allow_all()` once Claude Code approves them.
  - When `setting_sources` is unset, spawned sessions inherit the user's own settings and permission rules.
  - AGENTS.md says to treat `docs/` "as opaque".
  Failure: Rows 3, 15 and 22 ask only for "an A001 header", so the KNOWN EDGE CASES field comes out generic. Neither the next agent nor a developer who serves `ClaudeTools` through `McpStudioServer` learns that WRITE tools run ungated there.
  Smallest fix: Name these limitations in the KNOWN EDGE CASES of row 22 (`toolsets/claude.py`) and row 15 (`builtins/claude/__init__.py`). Name EC-45, EC-47 and EC-53 in row 3 (`host.py`). This adds no new controls.

VERIFIED CLAIMS:

**Shared files and packaging**
- **Marker bytes — held.** request.md:175-184, joined with LF plus a final newline, is 911 bytes with SHA-256 `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`. Any checkout on this machine is CRLF on disk (R-1).
- **`failure.py` — held.** `CONFIGURATION_INVALID_ARGUMENT` is at :34 and `CODEX_SDK_UNAVAILABLE` at :35; the CODEX block runs :35-46. Only two places iterate FailureCode, and both are prefix checks: `tests/test_codex_failure_recovery.py:194,200` and `tests/test_session_failures.py:139`. Adding the CLAUDE block is safe.
- **Export-list insert points — held.**
  - `lib/enums/__init__.py`: :40/:41, with the names going between `"CircularityVerdict"` and `"CodexApprovalMode"`.
  - `tools/builtins/__init__.py`: bash :28, code_execution :29.
  - `tools/toolsets/__init__.py`: `"ClaudeTools"` sorts first.
  - `lib/errors/__init__.py`: AggregateExecutionError :34 and ConfigurationError :35 are adjacent.
  - In `errors/base.py`, seven classes sit between AggregateExecutionError :194 and ConfigurationError :235, so "directly before :235" is the instruction that matters there.
- **pyproject and the public-API contract — held.**
  - `packages.find include=["vidbyte*"]`, together with rows 1, 2 and 15, puts the new packages in the wheel.
  - The `codex` extra is at :42-44.
  - C016 reads only the root `__all__` and the pyproject name and version, so the new extra and the submodule exports leave `contracts/sdk-public-api.json` unchanged.

**CLI 2.1.296 (`claude --version` / `--help`)**
- **Verified flags — held.** `--fallback-model` (comma list), `--file`, `--restricted`, `--safe-mode`, `--bare`, `--autocompact`, `-n/--name`, `--agent`, `--no-session-persistence` ("only works with --print"), `-w/--worktree [name]`, `--plugin-dir` and `--plugin-url`.
- **Max-output env variable — held.** `CLAUDE_CODE_MAX_OUTPUT_TOKENS` occurs 8 times in claude.exe, including "CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable".
- **`--permission-prompts` — exists but is unmapped (R-4).** It takes `host|none`, with default `host`.
- **`ClaudePermissionMode.DEFAULT="default"` — held.** The help lists "manual" instead of "default". However, DTS:6898 says "'manual' is accepted as an alias for 'default'", and the PermissionMode literal in both SDKs includes 'default'.

**claude-agent-sdk 0.2.165 source (read, not executed)**
- **`_build_command` — held.**
  - `system_prompt=None` → `--system-prompt ""`.
  - `extra_args` is emitted as `--flag`, as `--flag=value` (for a value starting with `-`) or as `--flag value` (spec:1045).
  - `can_use_tool` → `--permission-prompt-tool stdio`.
  - No `--print` is passed, so A-3 stays an assumption.
- **Error classes — held.** `MessageParseError` (`_errors.py:129`) is not exported. `CLINotFoundError` ⊂ `CLIConnectionError`, and `ResultError` ⊂ `ProcessError`.
- **`ResultMessage.origin` and `MessageOriginKind` ("treat anything unrecognized as not human") — held (D-28).**
- **Cumulative totals, DTS:5738/5746 — held (A-11, INV-20).** Resumed and forked sessions continue from their saved totals. The same doc text says crash and startup-error results may carry zeroed values; the spec does not mention this.
- **Cross-task disconnect — held.** `_task_compat.spawn_detached` says it is "Safe to .cancel() from any task", which supports A-9 and disconnecting from another task.
- **`_find_cli` and `_reject_windows_batch_cli` — read in full (R-5).**

**Claims that did not hold**
- **NFR-1's package-smoke claim — did not hold (R-7).**
- **S054 headroom.** The baseline is 3 and the current count is 3, so there is zero headroom (R-6).

**Other checks**
- **Row 7's async `run` naming — held; not a convention break.** Async `run` already exists in `pipelines/base.py:38`, `harnesses/execution.py:174` and `mcp_server/server/core.py:124`. C011 fires only on a class that defines an async `arun`.
- **README File Index — held.** No README in a touched folder has a `## File Index`; only agents/codex, agents/multi, config and workflows have one.
- **Doc insert points — held.** REPO_MAP :147/:151, and the harnesses README "## Key modules" at :167 with the serialization bullet at :177.
- **Permissions and agent wiring — held.**
  - `PermissionPolicy` defaults to {SAFE, READ} and has `allow_all()`.
  - The `BaseAgent` keywords in §4's second snippet are valid.
  - Fork's `_clone_tool` keeps a tool it cannot clone (EC-46).
- **CLI on this machine — held.** `shutil.which("claude")` returns `C:\users\422mi\.local\bin\claude.EXE`, and there is no `claude.cmd` on PATH.
