# S2 test author report: native-grok-opencode-meta-hosts

- **Stage:** S2, test author.
- **Spec:** `spec.md` r3, at HEAD `f2894d03`.
- **Base:** `aa8c380c`.

The tests were written before any implementation, from the spec's own names (§4, §8.5, §9, §12.3). They bind to those names exactly; no name was impossible. No production code, stub or placeholder module was added. No existing test was edited.

## Inventory

There are 4 packs and 47 files, with 1635 tests in all. Every pack has `README.md` (with `## File Index` and `## Logs`), `FEATURE.md` and a `conftest.py`. No pack has an `__init__.py`. Every `.py` file carries the A001 header.

| Pack | Files | Tests | Test files (tests each) |
|---|---|---|---|
| `tests/features/grok_host/` | 14 | 458 | `test_grok_host_acceptance.py` (7), `test_grok_host_errors.py` (204), `test_grok_host_turns.py` (27), `test_grok_host_reads.py` (17), `test_grok_host_process_bounds.py` (15), `test_grok_host_records.py` (38), `test_grok_host_tools.py` (32), `test_grok_host_shared_contract.py` (43), `test_grok_host_process_helpers.py` (19), `test_grok_transport_extension.py` (56) |
| `tests/features/opencode_host/` | 11 | 581 | `test_opencode_host_acceptance.py` (29), `test_opencode_host_errors.py` (405), `test_opencode_host_watcher.py` (22), `test_opencode_host_owned_server.py` (15), `test_opencode_host_security.py` (10), `test_opencode_host_records.py` (63), `test_opencode_host_tools.py` (37) |
| `tests/features/muse_host/` | 13 | 458 | `test_muse_host_acceptance.py` (6), `test_muse_host_errors.py` (261), `test_muse_host_turns.py` (28), `test_muse_host_wire.py` (21), `test_muse_host_reads.py` (13), `test_muse_host_process_bounds.py` (21), `test_muse_host_records.py` (61), `test_muse_host_tools.py` (26), `test_muse_host_wsl.py` (21) |
| `tests/features/native_backends/` | 9 | 138 | `test_native_backends_errors.py` (63), `test_native_backends_profiles.py` (16), `test_native_backends_balance.py` (9), `test_native_backends_security.py` (10), `test_native_backends_records.py` (26), `test_native_backends_tools.py` (14) |

### The error tables

Each table has one `pytest.param` per (function, code), and each row runs once against the host and once through the matching tool.

| Pack | Test | Rows | Covers |
|---|---|---|---|
| Grok | `test_grok_error_row` | 79 | all 13 `grok.*` codes |
| opencode | `test_opencode_error_row` | 125 | 14 codes; `not_installed` and `process_exited` are in the owned-server tests |
| opencode | `test_aenter_error_row` | 6 | |
| Muse | `test_muse_error_row` | 101 | 14 codes; `wsl_unavailable` is in `test_muse_host_wsl.py` |
| Backends | `test_backend_error_row` | 63 | all 9 `backend.*` codes |

All 53 new codes are referenced in their pack (FR-21).

Each case asserts:
- the exact `FailureCode` member, by identity;
- a non-empty `next_step` that holds the row's token;
- the operation;
- context values that are all `str`, with keys from the §13 list;
- what the fake saw (INV-5);
- in tool mode: `ToolResult.error`, `metadata["error"]`, `hint == next_step`, `operation`, `harness`, and the output `"<code>: … Next step: …"`.

### Other files

- `docs/spec/native-grok-opencode-meta-hosts/test-plan.md`: the coverage map, the deliberately skipped tests, the red run and the implementer notes.
- `spec.md` §6.2: the Proof column is filled for AC-1 to AC-20. Nothing else in the spec changed; 20 rows were edited, each only in its last cell.

## Fixtures and fakes

All seams are the §13 ones. Nothing patches `HttpTransport`, `McpStdioTransport`, `CliRunner` or a host class.

- **`grok_host/fake_grok_peer.py`.** A scripted `grok`, run as a real child through `GrokHostSettings.grok_command`.
  - **Roles** (picked from the appended argv): `--version`; `models`; `agent --no-leader … stdio`, which is an ACP peer; and `--single=`, which is a one-shot or fork run.
  - **Scenario keys:**
    - `ignore_eof` and `ignore_term`, for a stubborn peer;
    - `grandchild_roles`;
    - per-method `mode: silent`;
    - `garbage_before`;
    - `hold` with a release file;
    - `env_keys`, which logs only whether a key is present.
  - **Log.** It writes JSONL per process: argv, frames in and out, permission answers, and the pids of itself and its grandchild.
- **`opencode_host/conftest.py` `FakeOpencodeServer`.** 22 routes, served through `httpx.MockTransport` by patching `vidbyte.lib.http.transport.httpx.AsyncClient` with a factory over the saved real class.
  - `fake_opencode_serve.py` plays `opencode serve` through `opencode_command`. It logs the SHA-256 and length of the password, never the value.
  - AC-3 uses a real loopback socket that accepts and never answers.
- **`muse_host/fake_muse_peer.py`.** An MSP peer through `muse_command`. It validates every frame against the spec's member sets and answers violations with -32600 or -32602.
  - On win32, `make_wsl_host` builds a fake `wsl.exe` from pip's distlib `t64.exe` launcher, puts it first on PATH, and serves the distro `VidbyteFakeDistro`. The real `wsl.exe -d MuseUbuntu1` is never launched.
- **`native_backends/conftest.py` `FakeDeepseekEndpoint`.** Autouse, over `httpx.MockTransport`.
  - An autouse fixture deletes `GLM_API_KEY`, `DEEPSEEK_API_KEY` and `ZHIPU_API_KEY`.
  - The tests set placeholder values (`fake-glm-value-not-a-key-0001`, `fake-deepseek-value-not-a-key-0002`) with `monkeypatch`.
- **Timings.** They are shrunk only by patching `vidbyte.lib.constants.native_hosts.{NATIVE_STOP_GRACE_SECONDS, NATIVE_KILL_WAIT_SECONDS, OPENCODE_POLL_INTERVAL_SECONDS}`. Each pack also has one default-timing test that asserts the spec's 9 s peer bound.
- **No real CLIs.** No fixture contains a secret, a token or an absolute user path. No test launches the real `grok`, `opencode`, `muse` or WSL distro, and none sends a live prompt.

## Tests deliberately NOT written (pruned)

The full list with reasons is in `test-plan.md` under "Tests deliberately NOT written". In short:

- **Grok.** Host-wide rows EC-11 to EC-17 for functions that re-use a path already proved for a sibling function (about 12 pairs).
- **Re-proofs.** These cases re-prove an already-proved path:
  - the second EC-21 trigger;
  - EC-5 through a host method (proved at the factory and the tool base);
  - opencode EC-56 for each function, and EC-58 on the abort body;
  - Muse EC-97 and EC-98 for every method, EC-102 variants, EC-111 with -32011, and the extra EC-119 kinds;
  - backend duplicates for `check_backend_ready`, and tool-mode copies of the EC-132 shapes and the 128 opencode EC-1 cases.
- **Unreachable with the declared profiles:** EC-62, EC-126 and EC-137.
- **Not deterministic, or tied to the machine:**
  - EC-4's window between "prompt written" and "handle returned";
  - NFR-7 latency;
  - Windows process liveness;
  - EC-151 (the wall clock);
  - the 240 s default of the one-shot tools;
  - the 26 s WSL stop bound and the reap failure paths.
- **Unspecified:**
  - `MuseLauncher` methods;
  - where spawn sends `agent`, `system` and `model` for opencode;
  - an empty `system` or a whitespace `provider_id`;
  - the order of the harness and feature checks.
- **Forbidden by the task:** AC-10 with the literal `C:/w/repo` and `MuseUbuntu1`. The translation and the launch shape are proved with the fake distro instead.

## Red output

Bootstrap:

```
$ PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"
<worktree>\vidbyte\__init__.py
$ python -m pytest --version
pytest 8.3.5
```

All four packs:

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends -rfEs --tb=no
94 failed, 19 skipped, 1522 errors in 16.48s
```

Per pack:

```
grok_host:       89 failed, 13 skipped, 356 errors in 11.83s
opencode_host:    1 failed,  1 skipped, 579 errors in 3.21s
muse_host:        4 failed,  5 skipped, 449 errors in 2.68s
native_backends: 138 errors in 1.37s
```

Reasons, grouped over all 1616 failures and errors:

```
1350 ModuleNotFoundError: No module named 'vidbyte.harnesses.native'
  63 ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.opencode'
  35 AttributeError: module 'vidbyte.tools.toolsets' has no attribute 'OpencodeTools'
  27 AttributeError: module 'vidbyte.tools.toolsets' has no attribute 'GrokTools'
  23 AttributeError: module 'vidbyte.tools.toolsets' has no attribute 'MuseTools'
  15 ModuleNotFoundError: No module named 'vidbyte.lib.process'
  15 ModuleNotFoundError: No module named 'vidbyte.tools.builtins.harness_backends'
  10 AssertionError: Traceback ... (the AC-1 snippet and AC-20 fresh interpreters; the child's stderr ends in
     ModuleNotFoundError: No module named 'vidbyte.harnesses.native')
  10 AttributeError: 'McpStdioTransport' object has no attribute 'respond'
   9 AttributeError: 'McpStdioTransport' object has no attribute 'send_request'
   9 AttributeError: 'McpStdioTransport' object has no attribute 'notify'
   9 TypeError: McpStdioTransport.request() got an unexpected keyword argument 'timeout_seconds'
   9 TypeError: McpStdioTransport.__init__() got an unexpected keyword argument 'exit_grace_seconds'
   5 TypeError: McpStdioTransport.__init__() got an unexpected keyword argument 'stop_process_tree'
   4 ModuleNotFoundError: No module named 'vidbyte.lib.constants.native_hosts'
   3 AttributeError: module 'vidbyte.lib.errors' has no attribute 'NativeHostError'
   2 ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.validation'
   2 ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.native_hosts'
   2 ModuleNotFoundError: No module named 'vidbyte.lib.enums.native_hosts'
   2 TypeError: McpStdioTransport.__init__() got an unexpected keyword argument 'on_message'
   1 each: ModuleNotFoundError for vidbyte.lib.dataclasses.grok, .dataclasses.process, .enums.harness_backends,
     .enums.process, vidbyte.tools.builtins.grok, vidbyte.tools.builtins.opencode
   1 AssertionError: assert [] == ['grok.not_in...t_found', ...]      (the 53 members are not appended)
   1 AssertionError: assert 120 >= (120 + 53)
   1 AttributeError: GROK_NOT_INSTALLED
   1 FileNotFoundError: ... vidbyte\harnesses\native\__init__.py      (INV-19)
   1 AssertionError: []                                               (AC-18: the toolset modules are not loaded)
   1 vidbyte.lib.errors.base.McpProtocolError: MCP response result must be an object   (the dispatch bug)
```

Nothing passes. Every failure names a missing module, attribute or keyword, or an assertion on behaviour that does not exist yet.

The 19 skips are platform guards:
- 15 POSIX-only liveness checks;
- 2 Windows closed-pipe cases (EC-27 and EC-51);
- 1 win32-specific Muse PATH case;
- 1 reap script that needs `sh` and `/proc`.

The whole suite still collects: `5604 tests collected`.

Neighbours, unedited:
- **Command:** `tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent/test_coding_agent_contract.py`
- **Result:** `171 passed in 4.15s`.

Lint, on the staged files:
- `python -m ruff check tests/features --config lint/ruff.toml` gives `All checks passed!`.
- `python lint/run.py --rule A001` gives no findings in the packs.
- `python lint/run.py` gives `SDK-LINT: PASS`.

## Spec defects and ambiguities found

None of these blocks the work. The tests take the reading stated here, and S3 or a spec revision may want to settle each one.

1. **AC-5 (spec l.288 and l.292)** asks for `<redacted>` in the tool result's metadata, but no metadata field carries vendor text. The tests assert that the value is absent from the message, `next_step`, context, args, tool output and metadata. They also assert that `<redacted>` appears in the message or the context.
2. **T-2 vs §6.3.3.** T-2 says values only in `--name=value`, but the §6.3.3 fork argv shows `--output-format json --cwd <workspace>` in space form. The tests require caller values in `=` form, and accept either form for host-fixed flags.
3. **§6.3.1 contains markdown backticks**, so "verbatim" is ambiguous. The comparison ignores backticks. Two cells also end with an implementer note in parentheses (`grok.turn_timed_out`, `backend.not_signed_in`), and either form is accepted.
4. **§9.1 says "set fields converted to frozenset", but EC-23 says "not a frozenset".** The tests pass a `frozenset` of strings. The same tension exists in §9.1 (l.1309) vs EC-134 (l.749) for backends, and in the JSON encoding of frozensets in `list_harness_backends` (l.1513).
5. **Context keys that no row names:** EC-68 and AC-7 (the model list; the tests use `available_models`); EC-133 (currencies); EC-88 (the interrupt source).
6. **Unnamed `operation` values:** for `check_backend_ready`, and for a Muse turn failure (l.702–705).
7. **`GrokReadiness.version` format** is unspecified. The tests assume the bare semver, `"1.0.52"`.
8. **The allow, deny and max-turns flag names** for `grok --single` are unspecified. Only the `--x=value` form is asserted.
9. **EC-58 (l.524) vs EC-87 (l.609).** It is unclear whether a malformed poll body fails at once or counts as a failed poll. EC-153 (l.788): until the exit is collected, a call after the server dies may see EC-55. The test accepts `server_unreachable` until `process_exited` appears.
10. **INV-15 (l.260):** whether a total is computed or only reported. The tests keep a reported total, and leave an unreported total as `None`.
11. **EC-2 (l.395):** the state of a host after a failed `__aenter__` is unspecified.
12. **§9.1 (l.1381–1382):** it does not say which field a cross-field rule names in its error.
13. **EC-66 (l.556) "empty" vs `require_text`,** which rejects blank text. Blank is treated as empty.
14. **Muse:**
    - `MuseLauncher` has no named method (l.1211 and l.2010).
    - `to_wsl`'s exception type is unspecified (l.1211). The tests accept `ConfigurationError` or `NativeHostError` with `configuration.invalid_argument`.
    - AC-10's literal settings (l.293) vs §9.1 (l.1405).
    - Both `wsl_distro` and `muse_command` set (l.1405).
    - A denied `decide` outcome (l.872 and l.1351).
    - The EC-121 decision record (l.706).
    - EC-115's custom next step, token `continue_muse_session` (l.693–697), vs the default (l.365).
    - The type of `forked_from`, `display_name`, `kind` and `cachedTokens` (l.1410).
    - Event order and the `promptTokens` mapping (l.875).
    - -32602 with no cursor (l.683).

## Handoff

- **For the implementer.** The notes are in `test-plan.md` under "Notes for the implementer". The two that most often cause a false red are:
  - read the timing constants through the module at call time;
  - resolve `wsl.exe` with `shutil.which`. `CreateProcess` searches System32 before PATH, so a bare `wsl.exe` launches the real one.
- **Not committed:** the orchestrator's `pipeline.md` change.

## Addendum: test fixes after S3 (commit `66d5c3bb`)

The S3 implementer reported three test defects, and the coordinator adjudicated them against spec r4. I fixed each with a test-only edit and changed no other assertion.

- **D-1.**
  - **Test:** `tests/features/grok_host/test_grok_host_records.py::test_validator_rejects_each_bad_value_naming_the_field`.
  - **Problem:** the reject row `{AcpToolKind.EDIT}` contradicted §9.1, EC-23, EC-134 and §16 S2-4, under which a `set` of members is accepted and stored as a `frozenset`.
  - **Fix:** the row now uses `{"edit"}`, a plain set holding a value string, which the spec refuses. The file header's edge-case note now says the same.
- **D-2.**
  - **Test:** `tests/features/grok_host/test_grok_host_process_helpers.py::test_cli_invocation_validates_and_hides_env_and_stdin`.
  - **Problem:** the `argv` rows raised `TypeError: invocation() got multiple values for argument 'argv'` inside the helper.
  - **Fix:** the call is now `invocation(process_api, **{"argv": ("grok",), field_name: bad})`.
- **D-3.**
  - **Test:** `tests/features/opencode_host/test_opencode_host_records.py::test_host_settings_reject_each_bad_field`.
  - **Problem:** the `workspace-*` rows raised `TypeError: attached_settings() got multiple values for argument 'workspace'`.
  - **Fix:** the call is now `attached_settings(records_api, **{"workspace": tmp_path, **overrides})`.

Re-run at `66d5c3bb`. The command was `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider <three node ids>`, and its final lines were:

```
E       ModuleNotFoundError: No module named 'vidbyte.harnesses.native.grok'
ERROR tests/features/grok_host/test_grok_host_records.py::test_validator_rejects_each_bad_value_naming_the_field
ERROR tests/features/grok_host/test_grok_host_process_helpers.py::test_cli_invocation_validates_and_hides_env_and_stdin
1 passed, 2 errors in 0.95s
```

- **D-3 passes.**
- **D-1 and D-2 still error, for an unrelated reason.** Their shared `grok_api` fixture imports `vidbyte.harnesses.native.grok`, which is not built yet; only P1 is built. They will run once the Grok host lands.
- **Their test bodies pass.** I ran both bodies outside pytest from a scratch script. The script replaced only the fixture: it gave `ConfigurationError` from `vidbyte.lib.errors`, as `grok_api` does, and used the real `CliInvocation` record. Both printed `body passed`.
