LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the build matches spec r7 file for file, tool for tool and code for code, but Grok maps a no-cursor -32602 to the wrong failure row, and two unrecorded deviations (one in the INV-18 transport defaults, one in the §8.5 surface) need a one-line fix or a §17 record.

Reviewed: `git diff origin/main...de5b7c4c` (126 files, +29475/−10). HEAD is now `41a76491`; `de5b7c4c..HEAD` changes only `pipeline.md`, so every line number below is the same at HEAD.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The cross-PR contract holds byte for byte.**
  - The `native/__init__.py` SHA-256 is `0374a2c8…f497a`.
  - The INV-22 files show an empty diff, and there is no `native/README.md`.
  - Nothing imports codex or claude.
  - The 53 `FailureCode` members are appended after `RULE_EVALUATION_FAILED` with no line removed.
  - The four export lists are append-only. The 47 test files are all additions.
- **The surface matches the spec exactly.**
  - The 68 §12.3 paths match the diff exactly (56 created, 12 modified, nothing extra outside `tests/` and `docs/`).
  - There are 66 records and 13 enums, all under `vidbyte/lib/`.
  - The 43 tools match §9.2 row by row: name, READ/WRITE, every parameter, and which parameters are required.
  - All 55 `NATIVE_HOST_NEXT_STEPS` texts equal §6.3.1 apart from backticks.
  - All 61 rows of the §9.3 constants table hold.
- **The "never approve everything" rule (INV-9) holds on every route I traced.**
  - `GrokPermissionMode` has no `auto` or `bypassPermissions` member.
  - The Grok driver picks only `allow_once` or `reject_once`.
  - The opencode watcher only ever answers `reject`, and the `*`/`*`/`ALLOW` rule is refused at record construction.
  - Muse sends `approvalMode: denyUnmatched` and decides only `denied`/`once`.
  - No `--always-approve`, `yoloMode`, `--dangerously-skip-permissions`, `--yolo` or `allowAll` appears in code.
  - The tools expose neither `permission_mode` nor the allow rules.
- **The Muse and backend error mappings follow their rows exactly.**
  - Muse: EC-98, EC-100 to EC-102, EC-111 to EC-114, EC-117 to EC-121 and EC-156.
  - Backends: EC-122 to EC-133.
  - AC-1 prints the exact §4 line, and AC-20's seven fresh-interpreter imports all succeed.

## FINDINGS

### R-C1 [Blocker] [request fidelity / EC conformance] `vidbyte/harnesses/native/grok/wire.py:55` — Grok reports every -32602 sent without a cursor as `grok.protocol_mismatch` and drops the vendor message, but EC-16 says `grok.api_error`

**Evidence**
- `wire.py:53-55`:
  ```
  _INVALID_PARAMS = -32602
  _MALFORMED_CODES = frozenset({-32700, -32600, _INVALID_PARAMS})
  ```
- `wire.py:244-245`:
  ```
  if isinstance(code, int) and code in _MALFORMED_CODES:
      return self._errors.build(self._errors.code("protocol_mismatch"), ..., context={"vendor_code": str(code), "method": method})
  ```
- Reproduction, `GrokWire.vendor_error` on `session/new`:
  ```
  grok -32602 grok.protocol_mismatch {'vendor_code': '-32602', 'method': 'session/new'} | Run check_grok_ready and use a Grok Build release this SDK supports (1.0.13 or newer).
  grok -32603 grok.api_error {'vendor_code': '-32603', 'vendor_error': 'Invalid params: modelId'} | Retry later; ...
  muse -32602 muse.api_error {'vendor_code': '-32602', 'vendor_error': 'Invalid params'}
  ```
- What the spec and request say:
  - EC-14 sends only "-32700 or -32600" to protocol_mismatch.
  - EC-16: "any other JSON-RPC error … Everything else raises `grok.api_error`, whose context holds `vendor_code` … and `vendor_error`".
  - For the twin case, spec line 685 says: "With no cursor, a -32602 answer is not a stale cursor and falls under EC-102 (`muse.api_error`)".
  - The ACP mapping table in request.md has no -32602 row.
- Nothing records or tests this:
  - It is not among deviations 1–8.
  - The only Grok test that sends -32602 is the EC-41 cursor row (`tests/features/grok_host/test_grok_host_errors.py:339`), so nothing pins this path.

**Failure**
- Grok answers `session/new`, `session/resume` or `session/prompt` with -32602 Invalid params, for example for a parameter value it rejects.
- The caller then gets `grok.protocol_mismatch` with no `vendor_error`, and a next step telling them to run `check_grok_ready` and upgrade Grok.
- The result is a wrong code and a non-semantic message on a reachable path. That contradicts request.md §D ("return semantic error messages", "handle errors for every single function") and fails AC-2 for EC-16's trigger.

**Smallest fix**
- Remove `_INVALID_PARAMS` from `_MALFORMED_CODES` (`wire.py:55`). A -32602 sent without a cursor then reaches the `api_error` branch at `wire.py:246-247`. The EC-41 branch at `:242` is unchanged.
- Add one `Row` to `test_grok_host_errors.py` with -32602 on `session/new`, expecting `grok.api_error` with `vendor_code` "-32602".

**Spec IDs:** EC-14, EC-16, AC-2, FR-21, request.md §D

### R-C2 [Major] [deviation / INV-18] `vidbyte/tools/mcp/transport.py:303` — the default `request()` path now bounds `stdin.drain()`, a second, unrecorded exception to INV-18

**Evidence**
- The diff hunk:
  ```
  -                await self._process.stdin.drain()
  +                await asyncio.wait_for(self._process.stdin.drain(), seconds)
  ```
- `:314`: `"reason": "timeout" if isinstance(exc, TimeoutError) else "stdin_write_failed"`.
- `_call_timeout(None)` returns `self.request_timeout` (`:397-398`), so the bound applies with the defaults.
- INV-18: "`McpStdioTransport` behaves exactly as at `base_commit` when the new options are left at their defaults (… `request(...)` without `timeout_seconds`). The one exception is the dispatch fix".
- Nobody recorded it:
  - The S3 report (§7.1) only says "With the defaults, `close()` takes the old path".
  - Deviations 1–8 do not mention the drain.
  - `grep drain spec.md` finds no rule for the default path.

**Failure**
- Take an existing MCP client using the defaults, whose request fills the stdin pipe while the server reads slowly.
- At `base_commit` the write simply waits.
- Now the call raises `McpProtocolError(reason="timeout")` once `request_timeout` passes during the write.
- So an existing caller's behaviour changes with no option set, which is exactly what INV-18 forbids. The change is protective, and that is why this is Major rather than Blocker.

**Smallest fix**
- Option A: keep the unbounded `await self._process.stdin.drain()` when `timeout_seconds is None`, and bound it only for an explicit per-call deadline.
- Option B: record the drain bound as INV-18's second exception, in INV-18 and §17.

**Spec IDs:** INV-18, FR-15, D-3

### R-C3 [Minor] [scope / §8.5 surface] `vidbyte/harnesses/native/opencode/host.py:106` — `OpencodeHost.mcp_servers` is a public member that §8.5 does not list and §17 does not record

**Evidence**
- Enumerating the public members prints `OpencodeHost 19 [… 'mcp_servers', …]`, against `GrokHost 10` and `MuseHost 12`.
- §9.2: "§8.5 is the full list: three host classes with 40 methods".
- §12.3 row 35: "`OpencodeHost` with its 18 methods plus `__aenter__` and `__aexit__`".
- Its only caller is `tools/builtins/opencode/session_tools.py:214`.

**Failure**
- The public API gains an undocumented member that downstream code can come to depend on, beyond the ★ scope the user fixed for this PR.
- It exists for a sound reason: the EC-146 tool looks up a config the developer registered and never builds one from model text. But that reason is written down nowhere in the spec.

**Smallest fix**
- Record it as §17 deviation 9: a read-only view of `settings.mcp_servers` for the EC-146 tool.
- Alternatively, have `OpencodeTools` hand the tool the settings mapping, and drop the property.

**Spec IDs:** §8.5, §9.2, §12.3 row 35, EC-146

### R-C4 [Minor] [error-contract consistency] `vidbyte/harnesses/native/opencode/host.py:87` — the three hosts answer the same shared mistake differently

**Evidence**
- The opencode constructor does not wrap the settings check:
  - `opencode/host.py:87`: `RecordFieldConverter.require_instance(settings, "settings", OpencodeHostSettings)` sits outside any `try`.
  - `grok/host.py:77-80` and `muse/host.py:87-90` convert the same failure through `from_configuration_error`.
- Running each constructor with a wrong argument (`cls('not settings')`):
  ```
  GrokHost NativeHostError FailureCode.CONFIGURATION_INVALID_ARGUMENT
  OpencodeHost ConfigurationError None
  MuseHost NativeHostError FailureCode.CONFIGURATION_INVALID_ARGUMENT
  ```
- The EC-2 and EC-3 next steps differ for Muse:
  - `muse/host.py:69-70` keep the markdown backticks: "Open the host with \`async with\` …" and "Create a new host object for each \`async with\` block."
  - `grok/host.py:64-65` and `opencode/host.py:58-59` drop them, following §6.3.1 / S2-3.

**Failure**
- The §4 pattern `except NativeHostError` catches a wrong settings object for Grok and Muse, but not for opencode.
- A Muse tool's error output prints literal backticks where the other two hosts print plain text for the same EC row.

**Smallest fix**
- Wrap `opencode/host.py:87` the same way `grok/host.py:77-80` does, with operation `"OpencodeHost"`.
- Remove the backticks from `muse/host.py:69-70`. The tokens `async with` and `new host` still match.

**Spec IDs:** INV-1 (Grok and Muse treat construction as covered), EC-2, EC-3, §6.3.1 backtick rule (S2-3), request.md §D

### R-C5 [Minor] [EC-35/36/39] `vidbyte/harnesses/native/grok/host.py:497-501`, `grok/wire.py:339` — the fork compares ids case-sensitively right after accepting mixed-case UUIDs, and adds an unlisted EC-39 trigger

**Evidence**
- The argument check ignores case:
  - `host.py:302` compares `new_session_id.lower() == session_id.lower()`.
  - `require_uuid` accepts upper case, and `tests/features/grok_host/test_grok_host_records.py:66` pins that.
- The later checks compare exact case:
  - `host.py:498`: `if session_id not in known:`
  - `host.py:501`: `new_session_id in known`
  - `wire.py:339`: `if result.session_id == source or (target is not None and result.session_id != target):`
- EC-39 lists only "lacks `sessionId`, or its `sessionId` equals `session_id`". The `!= target` clause is not recorded anywhere.
- Reproduction: `check_fork_result(result lower-case, target upper-case)` raises `NativeHostError grok.protocol_mismatch {'reason': 'fork_session_id'}`.

**Failure**
- **Upper-case source id.** An existing session given in upper case raises `grok.session_not_found` (wrong row, though nothing is spent).
- **Upper-case `new_session_id`.**
  - EC-36's duplicate check misses an existing lower-case id.
  - If Grok echoes the new id in lower case, the paid fork succeeds but the call raises `grok.protocol_mismatch` after the money is spent.

**Smallest fix**
- Compare casefolded ids in `_check_fork_listing` and `check_fork_result`, as line 302 already does.
- Record the `!= target` check under EC-39 in §17.

**Spec IDs:** EC-35, EC-36, EC-39, request.md §D ("validated before … any money is spent")

### R-C6 [Minor] [deviation 7 record] `vidbyte/tools/builtins/harness_backends/tools.py:49` — deviation 7 gives a reason that does not hold

**Evidence**
- §17 deviation 7: opencode tools wrap tuple results "so that every tool output is a JSON object".
- `read_tools.py:86,98,112,127` wrap them (`{"models": …}`, `{"providers": …}`, `{"sessions": …}`).
- But `ListHarnessBackendsTool` returns the bare tuple. Running it prints `ToolResult [{"allowed_harnesses": ["claude_code", "codex", "opencode"], …` (a JSON array).
- §9.2 itself says the output is "the result record as JSON … tuples as lists".

**Failure**
- List-shaped tool outputs now come in two shapes across the 43 tools.
- The recorded reason for departing from §9.2 is false, so the next reader cannot tell which shape is intended.

**Smallest fix**
- Correct the deviation 7 text in §17 to "opencode tools wrap their tuple results" and drop "every tool output is a JSON object". This is a docs-only change.
- If uniformity is wanted, wrap `list_harness_backends` as `{"backends": […]}` instead.

**Spec IDs:** §9.2 Tool results, §17 deviation 7

## VERIFIED CLAIMS

**Cross-PR contract and budget**
- INV-19 hash `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`: **held**.
- INV-22 (`vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `tools/builtins/__init__.py`, `pyproject.toml`, `lint/`, `mcp_server/`) byte-identical: **held** (empty diffstat).
- No `vidbyte/harnesses/native/README.md`, and no import of `native.codex` or `native.claude` (0 matches): **held**.
- 53 FailureCodes appended after `RULE_EVALUATION_FAILED` (`failure.py:144`), not next to the CODEX block, with 0 removed lines: **held**.
- Export lists in `lib/enums`, `lib/errors`, `lib/configs` and `tools/toolsets` `__init__` are append-only: **held** (only `+` lines).
- §8.4 budget of 56 new and 12 modified files, 66 records and 13 enums: **held**. The 68 §12.3 paths match the diff exactly, and nothing outside §12.3 changed apart from `tests/` and `docs/`.
- The test tree is additions only (47 files added, 0 modified): **held**.
- §14 "Never" items:
  - No `# noqa`, `type: ignore` or `nosemgrep`; `lint/` unchanged; no absolute path in `vidbyte/` or `tests/`: **held**.
  - Absolute user paths do appear in the committed `docs/spec` artifacts, the spec's own header included. For S3 this is `reports/S3-implementer.md:189`. That is the pipeline's convention, so I report it here and not as a finding.

**Tool and catalog surface**
- 43 tools match §9.2 in name, permission, parameters and which are required; `harness` is `grok`, `opencode`, `muse` or `backend`: **held**.
- `NATIVE_HOST_NEXT_STEPS` has 55 entries equal to §6.3.1 apart from backticks: **held**.
- All 61 rows of the §9.3 constants table equal the module values: **held**.
- Only ★ functions were built (plus `build_opencode_backend_provider`, which was settled):
  - Grok has 10 public methods plus the module-level `run_grok_once`.
  - Muse has 12, and the backends have 6.
  - opencode has 18 plus `mcp_servers`: **held except R-C3**.

**Behaviour checks**
- AC-1, the §4 snippet with no `grok` on PATH and none at `~/.grok/bin`, prints the exact spec line: **held**.
- AC-20, seven entry modules each imported first in a fresh interpreter, with no vendor SDK in `sys.modules`: **held**.
- §5 diagram against the real call path: **held**.
  - Grok: reserve → peer `agent --no-leader [--model=] [--reasoning-effort=] stdio` → `initialize` → model check → `session/new` → `session/prompt` → handle.
  - opencode: reserve → `GET /config/providers` → `POST /session` → `prompt_async`.
  - Muse: handshake → `model/list` → `session/start` → `turn/start`.
  - One divergence is diagram-level only: node B says "resolve launcher" per spawn, but launchers are resolved once at `__aenter__` (EC-11, EC-54, D-19).
- Transport extension size is +166/−8, under the r6 trigger of about 200: **held**.
- INV-18 default path unchanged except the dispatch fix: **failed** (R-C2).
- EC-14 and EC-16 Grok JSON-RPC mapping: **failed** for -32602 (R-C1).
- Muse EC-94 to EC-121 and EC-156: **held** on reading.
  - Codes −32700/−32600/−32601/−32010/−32020/−32011/−32021/−32002/−32023/−32024/−32051/−32053/−32013/−32014/−32030 are each mapped as their rows say.
  - D-11 decides each requirement once.
  - EC-115's next step is used in steer, interrupt and wait.
- Backends EC-122 to EC-133: **held** on reading.
  - Status rows 401/403, 402, 429 and other.
  - The no-status `ProviderRequestError` maps to unreachable, and the over-cap one to protocol_mismatch.
  - `follow_redirects=False` is the transport default.
- Test coverage by EC id: every EC-1 to EC-156 id appears in the four test packs except EC-28, EC-32 and EC-139.
  - EC-28 and EC-32 are covered by the parametrized bad-id rows (`test_grok_host_errors.py:473`).
  - EC-139 is covered by the tool tests.
  - No test covers the R-C1 path.

**Deviations 1–8**
- **1 (invalid-argument next step).** Necessary for the EC-1 token, and recorded. The methods that take no argument keep three handlers, which is fine.
- **2 (`to_enum`, `to_decimal`).** Necessary and minimal.
- **3 (CLAUDE_CODE label).** Harmless: backend errors use explicit `backend.*` codes, so the label never surfaces.
- **4 (`from_unexpected` message).** Fine.
- **5 (private model-slot map).** Fine.
- **6 (`OpencodeHostTool` in `read_tools.py`).** Fine.
- **7 (wrapped results).** Not necessary, and its stated reason is false (R-C6).
- **8 (no try in `list_harness_backends`).** Fine.
- **Unreported deviations:** R-C1, R-C2, R-C3, R-C4 (the opencode constructor), and the extra EC-39 trigger in R-C5.

## COMMANDS RUN

| Command | Final output |
|---|---|
| `PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends` | `1616 passed, 19 skipped in 150.59s (0:02:30)` |
| `PYTHONPATH=$(pwd) python -B lint/run.py` | `SDK-LINT: PASS` |
| The §4 snippet (spec lines 109-131) under `env -i PATH=<python dir> USERPROFILE=HOME=<empty dir>` | `grok.not_installed -> Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command.` |
| `git show de5b7c4c:vidbyte/harnesses/native/__init__.py \| sha256sum` | `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a *-` |
| `git diff --stat origin/main...de5b7c4c -- vidbyte/__init__.py contracts/sdk-public-api.json vidbyte/tools/builtins/__init__.py pyproject.toml lint/ vidbyte/mcp_server/` | (empty) |
| `git diff --name-status origin/main...de5b7c4c -- tests \| grep -vc '^A'` | `0` (47 files total) |
| `git diff --name-status origin/main...de5b7c4c` | `114 A`, `12 M`; the 68 §12.3 paths minus the changed non-test, non-doc paths gives an empty `comm` output both ways |
| `git diff origin/main...de5b7c4c -- vidbyte/lib/enums/failure.py` | 53 `+` members after `RULE_EVALUATION_FAILED`, 0 `-` lines |
| `git diff --stat origin/main...de5b7c4c -- vidbyte/tools/mcp/transport.py` | `1 file changed, 166 insertions(+), 8 deletions(-)` |
| `GrokWire.vendor_error` and `MuseWire.vendor_failure` reproduction (R-C1) | `grok -32602 grok.protocol_mismatch …` / `muse -32602 muse.api_error …` |
| `check_fork_result` reproduction (R-C5) | `NativeHostError grok.protocol_mismatch {'reason': 'fork_session_id'}` |
| Constructing each host with `'not settings'` (R-C4) | `OpencodeHost ConfigurationError None` |
| Public-member enumeration of the three hosts | `GrokHost 10`, `OpencodeHost 19 [... 'mcp_servers' ...]`, `MuseHost 12` |
| Tool-spec dump of the four toolsets | 43 rows, all matching §9.2 |
| `ListHarnessBackendsTool().execute(...)` | `ToolResult [{"allowed_harnesses": ...` |
| `NATIVE_HOST_NEXT_STEPS` compared with §6.3.1 | only backtick-formatting differences |
| §9.3 constants compared with the module | `rows 61`, no real difference |
| Records and enums count | `records 66`, `enums 13` |
| AC-20 fresh-interpreter imports (7 modules) | all `ok []` |
| EC-id grep over the four test packs | `EC-28 EC-32 EC-139` not named |
| `git status --porcelain` before writing | only another reviewer's untracked `S4-review-engineering.md` |
