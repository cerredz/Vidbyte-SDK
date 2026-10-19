# S1 spec review, round 2 — harness-browser-tools (spec r2, 9921722e)

VERDICT: SOUND WITH FIXES — r2 resolves most of round 1, but moving the seam's `run` and `tool_calls` into `<H>Mounts` creates an import cycle in every harness subpackage, the prescribed record validator still quotes keys, and the reason given for not building a Muse-on-Windows browser is contradicted by the machine.

## WHAT THE SPEC GETS RIGHT

- **Fail-closed narrowing is exactly what the follow-up probes confirmed.** Keep D-10, AC-6 and EC-41 as written. Vendor facts §9 (2026-10-17) shows:
  - opencode `{"vidbyte-canary_*":"deny","vidbyte-canary_canary_ping":"allow"}` exposes exactly the allowed tool, and the reverse key order hides every tool;
  - Grok's exact `MCPTool(srv__tool)` allow and deny work, and a tool that is neither allowed nor denied cancels the turn with rc 0.
- **D-25's writer satisfies S061 and the native rules.**
  - S061's exemption tests `node.func.value.attr == "backend"` (`lint/rules/s061_bounded_safe_path.py:37-40`), so `NativeBrowserTools.backend.write_text(...)` is exempt.
  - `LocalFileSystemBackend()` takes no arguments and confines no path (`vidbyte/lib/tools/filesystem/backends/local.py:16-46`).
  - Importing `vidbyte.lib.tools…` passes INV-20, whose test bans only `vidbyte.tools` and `vidbyte.tools.*` (`test_harness_threads_static_policy.py:28,128`).
  - A Protocol body of `...` passes the literal rule, which flags only str, bytes, int and float.
- **The ratchet counts hold, and the plain path is safe to wrap.**
  - Counts, by running each rule: S061 5 of 6, A007 255 of 255, S020 1 of 1, S041/S047/S052 0, S009 346 of 350, C019 0.
  - None of 204 vendor tool names and new literals (`tool_install_failed`, `run_grok_with_browser`, `tool_call_update`, …) hits a C019 family or near miss.
  - No harness test references a `ThreadRun`, `Wire` or `_prepare_*` internal.
  - All four `NativeErrorFactory` constructors go through `_error` (`hostkit/errors.py:127,142,159,175`), so row 18 covers every error.
- **T-6 and the Muse settings shape match the probes.**
  - Grok servers inherit the whole environment, agent-file servers included (§9: the canary exposed `env_inherit_yes`).
  - opencode servers get `{...process.env, ...environment}`.
  - Muse servers get only `HOME LANG LOGNAME PATH SHELL TERM USER` plus the entry's `env`.
  - The probed Muse shape is used: `{"schema_version":1,"mcpServers":…}` with a string `command`, an `args` list, `streamable_http`, and no `env` on an HTTP entry.

## ROUND-1 RESOLUTION CHECK

Tally: 11 resolved, 4 partially resolved, 0 not resolved.

- **R-1 — resolved.**
  - §9.1 gives the top-level object and the three entry rules.
  - AC-26, EC-39, row 21 and `MUSE_SETTINGS_SCHEMA_VERSION` are added.
  - All of it matches vendor facts §1:17-45.
- **R-2 — partially resolved.**
  - Done: §11 counts, the §12.4 ratchet section, NFR-7, the §13 S020 File Index fact and the semgrep rule are present and correct (each verified).
  - Still wrong: A006 (34 of 34, zero slack) is missing from the list, and the pass marker is wrong (R-25).
  - New problem: the Muse write path cannot be followed as written (R-21).
- **R-3 — resolved.**
  - `NativeThreadResultRecord` is a StrEnum, and the keyword is typed with it.
  - The `TYPE_CHECKING` import pattern it relies on exists at `lib/errors/base.py:61-65`.
- **R-4 — resolved.**
  - Narrowing fails closed in FR-12, D-10, AC-6 and EC-41.
  - A-17 and A-18 are now probe-confirmed (vendor facts §9).
- **R-5 — resolved.**
  - D-24 makes server-flag capabilities additive.
  - The §9.1 arithmetic checks out: `playwright:devtools,pdf` allows 39 and denies 0; `firecrawl:search` allows 1 and denies 25.
- **R-6 — resolved.**
  - opencode server ids are `vidbyte-<tool>` with `"enabled": true`.
  - Vendor facts §9 shows the hyphen survives in tool names (`vidbyte-canary_canary_ping`).
- **R-7 — partially resolved.**
  - Registry refusals no longer quote the item (FR-5, §9.1, AC-25).
  - The record-level validator the spec prescribes still quotes `tools` items and `tool_keys` values, and the `tool_keys` field name carries the mapping key (R-17).
- **R-8 — resolved.**
  - The T-6 table matches vendor facts §1, §2 and §3.
  - Q-14 (`--ignore-scripts`) is added.
- **R-9 — partially resolved.**
  - The limit is now stated consistently in §2, §4, FR-11, AC-19, EC-42 and row 35.
  - The reason given for not building the bridge does not hold (R-18).
  - "On Windows" does not match row 21's `wsl_mode` test (R-23).
- **R-10 — resolved.**
  - opencode's guarantee is renamed honestly.
  - Muse's silent MCP disable is prevented by construction (AC-26), with EC-39 and Q-17 for the residual.
- **R-11 — resolved.**
  - Q-16 asks the user about the seed set.
  - The uvx reason is reworded to the first start only.
  - scrapling moves to "Not verified".
- **R-12 — partially resolved.**
  - Done: one `NativeBrowserRun.execute` exists, and no `<H>BrowserRun` text remains anywhere in the spec.
  - New problem: moving `run` and `tool_calls` into `<H>Mounts` introduced import cycles (R-16).
  - D-26 (keep `BrowserToolCache` in hostkit) is reasoned and acceptable.
- **R-13 — resolved.**
  - INV-14 and INV-16 name the exceptions, and D-22 widens the five next-step texts.
  - New evidence makes A-14 and EC-31 false (R-24), but that is separate from R-13.
- **R-14 — resolved.** INV-12 says removal is best effort, which matches EC-22.
- **R-15 — resolved.**
  - Readers return a `BrowserToolCalls` record.
  - §8 and §11 state that the SDK serves no tool.
  - Row 36 keeps the REPO_MAP "no model-facing tools or servers" sentence true.

## FINDINGS

**R-16 [Blocker] [L4] §8.5, §12.3 rows 19–21 and 25–28, §12.6 — r2 puts `run` and `tool_calls` into `<H>Mounts`, which creates an import cycle in all three harness subpackages**

Evidence:
- **Grok.**
  - Row 20: `GrokMounts.run` "writes the agent file …, then `GrokThreadRun.execute(mount=…)`". That is an edge from mounts to threads.
  - Row 26: `GrokThreadRun.execute` adds "`GrokMounts.options` before `--single`". That is an edge from threads to mounts.
- **opencode.**
  - Row 19: `OpencodeMounts.run` "calls `OpencodeThreadRun.execute(mount=…)`", and §8 item 3 sends its `tool_calls` "through `<H>Wire`".
  - Row 25: `execute` "adds `env_remove`", which is `OpencodeMounts.env_remove` (§8.5).
  - Row 28: `config_content` "adds the `mcp` and `permission` members from `OpencodeMounts.config`".
  - Result: mounts → threads → mounts, and mounts → wire → mounts.
- **Muse.**
  - Row 21: `MuseMounts.run` calls `MuseThreadRun.execute(mount=…)`.
  - Row 27: `execute` must write the settings that only `MuseMounts.settings(mount)` compiles.
- **r1 had no cycle.** Its `<H>Mounts` held only compile helpers (`check`, `config`, `options`, …), and `<H>BrowserRun` in `browser.py` called both sides (r1 rows 19–24).
- **Today's imports are absolute and at module level.** `grok/__init__.py:16` imports `threads`, and `grok/threads.py:23` imports `wire`.
- **A006 blocks the obvious workaround.**
  - It counts imports inside functions and reports every concrete cycle (`a006_directed_dependency_graph.py:55-61`).
  - It stands at 34 of 34, with zero slack.
  - Its diagnostic lists "Adding a local import inside a function to hide the cycle" under "will not work".
- AGENTS.md principle 3: "no two modules depend on each other in a cycle".

Failure:
- Built as written, `import vidbyte.harnesses.native` raises `ImportError`. When `grok/mounts.py` imports `GrokThreadRun`, `grok/threads.py` is only partly initialized.
- That breaks the nine plain functions too (INV-14).
- A lazy import hides the runtime error but still adds an A006 finding, so AC-20 fails.
- The §12.6 order "the mounts (19–21) come before the threads and wire rows" cannot be followed, because each side needs the other.

Smallest fix:
- Restore one-way edges.
  - Keep `<H>Mounts` in `mounts.py` as pure compile helpers (`check`, `config`, `options`, `environment`, `env_remove`, `agent_text`, `settings`), importing only lib and hostkit.
  - Move the `NativeBrowserHarness` implementation (`run`, `tool_calls`, `missing`, and a `check` that delegates) into `<h>/browser.py` beside `<H>BrowserThreads`, for example as `<H>BrowserHarness(config)`.
  - The edges become browser → {threads, wire, mounts}, threads → {wire, mounts}, wire → mounts. This satisfies every FR and INV, and the file count is unchanged.
- Update §8, the §8.4 class count, §8.5, rows 19–24 and the §12.6 order (mounts → wire and threads → browser).
- Add A006 (34 of 34) to §12.4's zero-slack list.
- An alternative fix: pass a lib-level compiled-plan record into `execute`, so threads and wire never import mounts.

**R-17 [Major] [L7] §9.1 `BrowserToolRequest`, FR-4, EC-6, EC-7, AC-25 — the validator the spec prescribes quotes refused `tools` items and `tool_keys` values in the error text**

Evidence:
- **What the spec prescribes.**
  - §9.1: records are "validated in `__post_init__` with `RecordFieldValidator` and `RecordFieldConverter`".
  - Each `tool_keys` value is checked against "`NATIVE_API_KEY_PATTERN` and ≤ `NATIVE_API_KEY_MAX_CHARS`, named `tool_keys[<name>]`".
  - Each `tools` item must be "one line and ≤ 128".
- **What that validator does.**
  - `require_text` and `require_text_items` end their message with `got {_received(value, field_name)}` (`vidbyte/lib/dataclasses/validation.py:41-48,65-76`).
  - `_received` quotes any value whose repr is at most 80 characters (`NATIVE_QUOTED_VALUE_MAX_CHARS = 80`), unless `CredentialKeyPolicy.is_secret_key(field_name)` is true (`validation.py:150-157`).
  - I ran that check: it returns False for `tools`, `tools[0]`, `tool_keys` and `tool_keys[brave]`.
  - The sibling `NativeThreadRequest` is safe only because its field is named `api_key` (`lib/dataclasses/native_threads.py:106`).
- **Nothing later removes the value.**
  - The record is built in `_call`, before layer 3 registers any key.
  - `HarnessRedactor._ERROR_ASSIGNMENT` matches only assignment forms such as `api_key=` or `token:` (`vidbyte/harnesses/serialization.py:76`). So text like `got 'fc-…\n'` survives `from_configuration_error`.
- **The mapping key is user input too.** EC-6 and AC-8 name `tool_keys[<name>]`, and that name is never registered as a secret.

Failure:
- `tool_keys={"firecrawl": open("key.txt").read()}`: the trailing newline fails the pattern, and the refusal reads `tool_keys[firecrawl] must …; got 'fc-…\n'`.
  - The key then sits in `str(error)`, in `actual` and in any trace.
  - This breaks KD-6, INV-4 and EC-7.
- A key pasted into `tools` with a newline hits the same record check. AC-25 covers only the registry path.
- A swapped mapping, `tool_keys={key: "firecrawl"}`, puts the key into the field name.

Smallest fix:
- In §9.1, name the mechanism. Check `tools` items and `tool_keys` values with the existing non-quoting predicate `RecordFieldValidator.accepts_text(...)` (`validation.py:51`). Raise a constant message from row 7 that names only `tools[i]` or the entry.
- Name a `tool_keys` entry by its key only when that key is a registry name, mountable or excluded. Otherwise name it by position, for example `tool_keys entry 2`.
- Extend AC-25 with a multi-line key-shaped item.
- Add an AC for a key with a trailing newline and an AC for a swapped mapping.

**R-18 [Major] [L1] §8.1 D-9 runner-up, §15 Q-15 — the reason given for not building a Muse-on-Windows browser is not what the probe showed**

Evidence:
- **What the spec says.**
  - D-9: "verified that a Windows `127.0.0.1` HTTP MCP is reachable from WSL, but only under mirrored networking (not WSL's default NAT mode)".
  - Q-15: "verified reachable from WSL only under mirrored networking".
- **What the evidence shows.**
  - Vendor facts §1:92 says only "reachable from WSL (mirrored networking)". No NAT run was ever made.
  - `wsl.exe -l -v` on this machine prints `MuseUbuntu1 … VERSION 1`, and there is no `%USERPROFILE%\.wslconfig`.
  - A WSL 1 distro runs on the Windows network stack, so it shares Windows' loopback by design.
  - Mirrored networking is a WSL 2-only `.wslconfig` mode, and it is not set here.

Failure:
- The user will decide Q-15, the only route to a browser for `run_muse_with_browser` on Windows.
- They will believe it needs a non-default networking mode, when on their own Muse distro the loopback route worked with default settings.

Smallest fix:
- Restate D-9 and Q-15: "verified on MuseUbuntu1, a WSL 1 distro that shares Windows' loopback; a WSL 2 distro would need mirrored networking (untested)".
- Keep the other stated reasons (a new SDK-owned server lifecycle, an unauthenticated local endpoint, only Playwright's `--port` is known) and the default "not built". I do not ask for the bridge.

**R-19 [Major] [L5] §9.1 Readers, `BrowserToolCall` — a tool name the model writes can turn a finished run into `configuration.invalid_argument`**

Evidence:
- **The record refuses bad names.** §9.1 says `BrowserToolCall.name` "follows `NATIVE_NAME_PATTERN` ≤ 64" (`^[A-Za-z0-9][A-Za-z0-9._-]*$`, `lib/constants/native_threads.py:58`), and a refused field raises `ConfigurationError`.
- **On Grok the name is model text.**
  - The Grok reader takes the name from `rawInput.tool_name`, which the model writes inside `use_tool`.
  - Grok answers an unknown name with a failed `tool_call_update`, "Tool not found" (vendor facts §2 and §9). It does not reject the event.
- **`_call` misreports it.** It turns any `ConfigurationError` into `configuration.invalid_argument` (`_call` step 5).
- **The non-raising check already exists.** `RecordFieldValidator.accepts_text` is documented as being "for a reader that must not raise, such as a vendor answer it only inspects" (`validation.py:51-53`).

Failure:
- The model calls `use_tool{"tool_name":"playwright__browser navigate"}` (a space) or writes a name longer than 64 characters.
- The reader's record refuses it.
- The finished, paid run raises `configuration.invalid_argument`, which tells the caller their arguments were wrong, and `discard` deletes the artifacts.
- The same happens on opencode when the split leaves a leading `_`, as in `vidbyte-playwright__x`.

Smallest fix:
- In §9.1 Readers, skip any call whose name fails `accepts_text(name, max_chars=…, pattern=NATIVE_NAME_PATTERN)`, or record it as failed with no name.
- Add an EC for the case.

**R-20 [Major] [L10] §12.3 row 13, §13 — AC-13 cannot pass on the Linux CI runner, because the test sandbox hides `ps`**

Evidence:
- Row 13 runs `ps -A -ww -o pid=,args=` on POSIX "through `CliRunner.find_program`", which searches PATH.
- The `sandbox` fixture sets PATH to the stand-in folder only (`tests/features/harness_threads/conftest.py:256`).
- CI runs on `ubuntu-latest` (`.github/workflows/ci.yml:17,44`).
- On POSIX, `CliRunner.run` also passes the bare program name to the OS, which searches that same PATH (`lib/process/runner.py:196`).
- EC-22 says a reaper that cannot start "is not raised", so the stand-in browser survives without any error.

Failure:
- AC-13 (P0) passes on Windows, where PowerShell comes from System32 by absolute path, and fails in CI.
- A test author who sees only the spec has no way to know this.

Smallest fix:
- Resolve `ps` from fixed absolute locations held in constants (`/bin/ps`, `/usr/bin/ps`). This is how the Windows reaper takes PowerShell from System32 and how `ProcessStopper` takes taskkill.
- This also stops a `ps` planted earlier on PATH from hiding processes.
- State the fact in §13.

**R-21 [Minor] [L9] §12.3 row 27, §9.2 — the synchronous `_prepare_config` is told to call the asynchronous `NativeBrowserTools.write_file`**

Evidence:
- §8.5 declares `async def write_file(path, text)`.
- Row 27 and §9.2 say `_prepare_config(request, errors, settings=None)` "writes … through `NativeBrowserTools.write_file`".
- `_prepare_config` is a plain `def` that runs inside a shielded `asyncio.to_thread` (`muse/threads.py:109,149`).

Failure: the instruction cannot be followed. An implementer either writes `Path.write_text` there (S061 then sits at 6 of 6), or moves the write, and its cancel handling, somewhere ad hoc.

Smallest fix: row 27 should say which of these two to use.
- In `_prepare_config`, call `NativeBrowserTools.backend.write_text(..., encoding=BROWSER_FILE_ENCODING, create_parents=True, atomic=True)` directly. The receiver is S061-exempt, and the code already runs off the event loop.
- Or split the helper: a synchronous `write_text` used there, and the asynchronous wrapper that Grok uses.

**R-22 [Minor] [L5] FR-8, NFR-5, INV-1 — Node is required even when every selected tool is remote**

Evidence:
- FR-8 checks `node` unconditionally.
- NFR-5 says a call starts "exactly one extra child before the harness (`node --version`)".
- INV-1 exempts only the Chrome check and the install.
- §2 says Muse in WSL mode can mount only jina and parallel, both remote.

Failure:
- A Windows Muse user without Node calls `run_muse_with_browser(tools=["jina"])` and gets `browser.runtime_missing`. That is the one combination that needs no Node.
- The same happens with opencode and `["browserbase"]`.

Smallest fix:
- Run the Node check only when a selection is stdio, the same rule as the Chrome check.
- Update FR-8, NFR-5 and INV-1's example.

**R-23 [Minor] [L10] §2, §4, EC-42 against row 21; INV-11 — two testable statements contradict the design**

Evidence:
- **"On Windows" versus WSL mode.**
  - §2, §4 and EC-42 say "On Windows … any stdio tool … refused".
  - Row 21 refuses "in WSL mode".
  - `MuseLauncher.wsl_mode` is `muse_command is None and wsl_distro is not None` (`muse/launcher.py:65-68`). That is a config test, not a platform test.
  - So the test pack's fake Muse on Windows, which is passed as `muse_command`, counts as native.
- **INV-11 promises "the same compiled mount bytes".** But every mount embeds the random per-call folder (`--user-data-dir`, `--output-dir`, `--agent=`).

Failure:
- An EC-42 test run on Windows with the fake expects a refusal that the implementation does not raise.
- An INV-11 test that compares bytes across two calls always fails.

Smallest fix:
- Word §2, §4 and EC-42 as "in WSL mode (`wsl_distro` set, no `muse_command`)".
- Word INV-11 as "the same bytes apart from the per-call folder path".

**R-24 [Minor] [L9] §8.1 D-9, §15 A-4, A-14, A-17, A-18, Q-18, EC-31 — vendor facts §9 now settles six of these, and one result contradicts the spec**

Evidence (vendor facts §9, 2026-10-17):
- **A-17 confirmed.** Deny-then-allow keeps exactly the allowed tool, and the reverse order hides every tool, so key order matters.
- **A-18 confirmed.** Exact allow and deny work, and an unlisted tool cancels the turn with rc 0.
- **A-4 confirmed.** JSON frontmatter, the joined flags, and `--agent` together with `--resume` and `--fork-session` all work.
- **Agent-file servers inherit Grok's environment.** The canary exposed `env_inherit_yes`.
- **A-14 is false.** After `--resume <id>` with no `--agent`, "the resumed request's system prompt still contained the agent file's body".
- **Q-18 is now probed.** Keyless HTTP entries (url only, or headers as a map or a sequence) mount and complete under `-p`. `${VAR}` is not expanded in headers.

Failure:
- A-14 and EC-31 say a plain continue makes Grok "fall back to its default agent". In fact the stored system prompt, with `GROK_BROWSER_AGENT_BODY`, persists while the tools are gone.
- D-9 still gives "unprobed" as the reason Grok refuses remote tools.

Smallest fix:
- Mark A-4, A-17 and A-18 verified, and keep the key-order sentence in D-10.
- Rewrite A-14 and EC-31: the body persists, so D-18's body must not claim the tools are present.
- Update D-9 and Q-18 with the probe results, and let the user choose the default for keyless remote tools on Grok. How real servers answer the `server/discover` request is still unverified.
- Keyed remote tools stay refused under KD-6, because a key would have to be written into the agent file.

**R-25 [Minor] [L11] §11, AC-20, NFR-7, §12.4, row 36 — gate and repo-map facts are wrong or missing**

Evidence:
- **The pass marker is wrong.** Lint's last line is `SDK-LINT: PASS` (`lint/core/report.py:58`), and every focused run I made printed exactly that. The spec says `AGENT-LINT: PASS` at lines 202, 301 and 724, and code-map §1.2 repeats the error.
- **A006 is missing.** It is at 34 of 34 with zero slack, but it is not in §12.4's ratchet list.
- **A REPO_MAP row goes stale.** The `vidbyte/lib/process/` row (`REPO_MAP.md:219-221`) lists exactly three helpers: "a one-shot command runner…, one argv builder…, and a stopper". Row 36 updates only the native rows.

Failure:
- An implementer checks for a marker that never appears.
- REPO_MAP stops describing `vidbyte/lib/process/` once `ProcessReaper` lands (AGENTS.md §Repository Map).

Smallest fix:
- Replace the marker in all three places.
- Add A006 to the zero-slack list.
- Widen row 36 to cover the `vidbyte/lib/process/` row.

**R-26 [Minor] [L1] FR-5, §9.1 Grammar — an unknown name with no close match gets no suggestion**

Evidence:
- §9.1: refusals name the suggested registry name only "where one exists", with a `difflib` cutoff of 0.6.
- KD-4: "unknown strings fail with a suggestion".
- The field guide's `declarative-config-resolution.md` asks for a "`ConfigurationError` naming the available names", the `runtimes.py` shape.

Failure: `tools=["skyvern"]` or `["stagehand"]` names a tool the request mentions but that is in neither list. The refusal then has neither a suggestion nor the list of names.

Smallest fix: when `get_close_matches` returns nothing, name the 13 mountable tools. That text is owned by the registry, so the no-quoting rule (R-7) still holds.

## VERIFIED CLAIMS

**Held**
- **Lint counts** (`py -3.11 lint/run.py --rule <ID>`; the run left no files behind):
  - S061 is 5 against a baseline of 6, and its `X.backend.<method>(…)` exemption is real (s061:37-40,63-68).
  - A007 255 of 255; S020 1 of 1; S041, S047 and S052 0; C019 0; S009 346 of 350.
  - A006 is 34 of 34. It holds, but §12.4 does not list it.
- **The reviewed writer.**
  - `LocalFileSystemBackend.write_text(path, content, *, encoding, create_parents, newline=None, atomic=False)` is at `local.py:25`.
  - The precedent is `vidbyte/agents/infinite/workspace.py:68` (`self.backend = LocalFileSystemBackend()`) and `:153` (`self.backend.write_text(...)`).
- **The INV-20 static-policy test** bans only `vidbyte.tools` and its submodules, so `vidbyte.lib.tools` is allowed. Its literal rule ignores `...` and booleans.
- **The error path.**
  - `NativeErrorFactory` builds every error through `_error`.
  - `NativeThreadError.expected` is hard-coded today.
  - `lib/errors/base.py` imports `NativeHarness` and `NativeThreadOperation` under `TYPE_CHECKING` (lines 61-65). It does import `DeliveryStatus` at runtime (line 59), which is harmless.
- **The §13 pins are complete.**
  - `EXPECTED_ENUMS["NativeThreadOperation"]` is `list(FUNCTIONS)`.
  - The subpackage `__all__` must equal exactly the three `*_thread` names.
  - `lib.process.__all__` is pinned.
  - `DELETED_FILES` and `OLD_NAMES` do not collide with any new path or name.
  - No test references a harness internal.
- **Sandbox facts.** `sandbox` sets `USERPROFILE`, `HOME`, `PATH` and `tempfile.tempdir` (`conftest.py:249-257`).
- **Name and argv facts.**
  - `NATIVE_NAME_PATTERN` accepts hyphenated names such as apify's and linkup's.
  - Muse's `--` is an operand (`muse/threads.py:219`), so appending `--disable-web-tools` to the options is safe.
- **No other repo-map obligations.**
  - No touched source folder has a README `## File Index`, so S020 applies only to the tests folder.
  - `llms.txt` and `artifacts/file_index.md` list no native modules, so §12.5's "none" holds.
- **Stack and docs facts.**
  - Python ≥ 3.11 (`pyproject.toml:10`); pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48-49`); pytest options at `pyproject.toml:78-81`.
  - The semgrep command matches `.github/workflows/static-policy.yml:30`.
  - README sizes: harnesses 10,972; registries 7,424; lib 4,037; harness_threads tests 2,831.
- **Vendor facts §9** confirms A-4, A-17 and A-18, and that agent-file servers inherit Grok's environment (D-7 holds).

**Did not hold**
- **Row 27:** `_prepare_config` is synchronous, so it cannot await `write_file` (R-21).
- **§2 and EC-42 "On Windows":** `MuseLauncher.wsl_mode` is config-based (R-23).
- **"AGENT-LINT: PASS":** the marker is `SDK-LINT: PASS` (R-25).
- **D-9 and Q-15 "only under mirrored networking":** MuseUbuntu1 is WSL 1, and no `.wslconfig` exists (R-18).
- **A-14 "falls back to its default agent":** vendor facts §9 shows the agent body persists (R-24).
- **"No refusal quotes a value" under the prescribed validator:** `_received` quotes non-secret fields, and `tool_keys[…]` is not secret-named (R-17).
- **Phase order "mounts before threads and wire":** under r2's responsibilities the dependency is mutual (R-16).
