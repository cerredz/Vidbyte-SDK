# S3 implementer report: native-grok-opencode-meta-hosts

Status: **BLOCKED**. Phase P1 (rows 1-20, except docs row 21) and P2 row 24 are implemented and committed. I stopped because the briefing says to stop when a test is wrong against the spec. Three S2 tests are wrong against the spec, and no correct implementation can pass them. Nothing was pushed, no PR was opened, and the worktree is still in place.

- Branch: `feat/native-grok-opencode-meta-hosts`
- Start: `8b77aba0`
- HEAD: `c3bd8c6f`

## 1. Commits (one per work item)

| SHA | Work item | §12.3 rows | Files |
|---|---|---|---|
| `26f897e9` | W-1; INV-5, INV-8, AC-17 | 1, 2, 3, 4, 5, 6, 13 | `vidbyte/lib/enums/native_hosts.py`, `vidbyte/lib/enums/harness_backends.py`, `vidbyte/lib/enums/process.py`, `vidbyte/lib/enums/failure.py` (53 members appended after `RULE_EVALUATION_FAILED`), `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/dataclasses/validation.py`, `vidbyte/lib/constants/native_hosts.py` |
| `49eae8cc` | W-2; FR-4, EC-23, EC-33, EC-66, EC-91, EC-106, EC-134, EC-152, AC-13, D-13 | 7, 8, 9, 10, 11, 12, 14, 15 | `vidbyte/lib/dataclasses/native_hosts.py`, `grok.py`, `opencode.py`, `muse.py`, `harness_backends.py`, `process.py`; `vidbyte/lib/configs/harness_backends.py`, `vidbyte/lib/configs/__init__.py` |
| `ba78a4da` | W-3; INV-1, INV-8 | 19, 20 | `vidbyte/lib/errors/base.py` (`NativeHostError` appended after `SourceSecurityError`), `vidbyte/lib/errors/__init__.py` (appended at the end of the tuple and of `__all__`) |
| `b137305e` | W-4; FR-16, INV-4 | 16, 17, 18 | `vidbyte/lib/process/__init__.py`, `runner.py`, `managed.py` |
| `c3bd8c6f` | W-14; AC-16, INV-19 | 24 | `vidbyte/harnesses/native/__init__.py` (fixed bytes) |

Not started:

- P2 rows 22 and 25-28 (transport, hostkit)
- P3 rows 29-46 (hosts, backends)
- P4 rows 48-66 (tools, toolsets)
- P5 rows 21, 23, 47, 67 and 68 (docs)

The PR, CI, the spec `pr:`/`status:` fields and the proof cells were not done.

## 2. The blocking test defects

Each of the three tests fails before any SDK code can decide the outcome, or demands behaviour that the spec forbids. In every case my implementation does what the spec says.

### D-1: a plain `set` is expected to be refused by `require_enum_set`

- **Test:** `tests/features/grok_host/test_grok_host_records.py::test_validator_rejects_each_bad_value_naming_the_field`.
- **Bad row:** line 100, `("require_enum_set", ({enums.AcpToolKind.EDIT}, enums.AcpToolKind, "f"), {})`. This is a plain `set` of valid members, listed as a value that must raise.
- **What the spec says:**
  - §9.1 validator table (spec.md:1335): `require_enum_set` accepts "a `set` or `frozenset` whose items are all members of `enum_type`; returns a `frozenset`".
  - §9.1 common rules (spec.md:1318): "Set fields accept a `set` or `frozenset` and are stored as `frozenset`".
  - EC-23 (spec.md:443) and EC-134 (spec.md:751): "a `set` is stored as a `frozenset`".
  - Review decision S2-4 (spec.md:2147) states the same.
- **The test file contradicts itself:** its own header (line 8) says "Do not test that a plain set or list is refused where §9.1 says it is converted."
- **Evidence:** calling the validator directly printed `NO RAISE require_enum_set ({<AcpToolKind.EDIT: 'edit'>}, <enum 'AcpToolKind'>, 'f') {}`. The pytest result is `FAILED ...::test_validator_rejects_each_bad_value_naming_the_field`.
- **Smallest fix to the test:** replace the value on line 100 with one that §9.1 refuses, such as `[enums.AcpToolKind.EDIT]` (a list) or `(enums.AcpToolKind.EDIT,)` (a tuple).

### D-2: the CliInvocation argv rows cannot reach the SDK

- **Test:** `tests/features/grok_host/test_grok_host_process_helpers.py::test_cli_invocation_validates_and_hides_env_and_stdin`.
- **The helper:** `invocation(api, argv, **fields)` (line 56).
- **The call:** line 94 calls `invocation(process_api, ("grok",), **{field_name: bad})`. For the rows `("argv", ())` and `("argv", ("",))` this binds `argv` twice.
- **Evidence:** `TypeError: invocation() got multiple values for argument 'argv'` at `test_grok_host_process_helpers.py:94`. Python raises this before `CliInvocation` is constructed, so no implementation can pass the test.
- **What the spec says:** §9.1 `CliInvocation`, where `argv` goes through `require_argv`. My record raises `ConfigurationError` naming `CliInvocation.argv` for both values. I checked this by building the record directly.
- **Smallest fix to the test:** for the `argv` rows, pass the bad value as the helper's positional `argv`. Alternatively, build `CliInvocation` directly.

### D-3: the OpencodeHostSettings workspace rows cannot reach the SDK

- **Test:** `tests/features/opencode_host/test_opencode_host_records.py::test_host_settings_reject_each_bad_field`.
- **The helper:** `attached_settings(api, workspace, **overrides)` (lines 65-67).
- **The call:** line 281 calls `attached_settings(records_api, tmp_path, **overrides)`.
- **The rows that break:** lines 238-241 (`workspace-relative`, `workspace-missing`, `workspace-file`, `workspace-str`) put `workspace` in `overrides`, so `workspace` is bound twice.
- **Evidence:** `TypeError: attached_settings() got multiple values for argument 'workspace'` at `test_opencode_host_records.py:281`. The run ended with `1 failed, 62 passed`.
- **What the spec says:** §9.1 `OpencodeHostSettings` (spec.md:1400) and EC-152.
- **Check against my implementation:** a scratch script built every row of `settings_cases` straight into `OpencodeHostSettings(**{**fields, **overrides})`. It passed all rows, including the four workspace rows: `rows checked; failures: []`.
- **Smallest fix to the test:** when `overrides` carries `workspace`, the helper should let it win, for example `workspace = overrides.pop("workspace", workspace)`. Alternatively, pass `workspace` only through `overrides`.

I did not edit `tests/`. Running `git diff cfad74f8..HEAD -- tests/ | wc -l` gives `0`.

More defects of this kind may exist in tests that need P2-P4 code. Those tests error at fixture import today (`ModuleNotFoundError: vidbyte.harnesses.native.{grok,muse,backends}`), so I could not check them.

## 3. Verification at HEAD `c3bd8c6f`

- **New packs, P1-level tests.** I used a throwaway, uncommitted `vidbyte/harnesses/native/grok/__init__.py` stub. It is needed only because the `grok_api` fixture imports `GrokHost`, and I deleted it afterwards.
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_records.py tests/features/grok_host/test_grok_host_process_helpers.py`
    ```
    FAILED tests/features/grok_host/test_grok_host_records.py::test_validator_rejects_each_bad_value_naming_the_field
    FAILED tests/features/grok_host/test_grok_host_process_helpers.py::test_cli_invocation_validates_and_hides_env_and_stdin
    2 failed, 51 passed, 4 skipped in 2.91s
    ```
    The 4 skips are POSIX-only process-group tests on this Windows box. The 2 failures are D-1 and D-2.
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_records.py`
    ```
    FAILED tests/features/opencode_host/test_opencode_host_records.py::test_host_settings_reject_each_bad_field
    1 failed, 62 passed in 0.95s
    ```
    The 1 failure is D-3.
- **Neighbour tests.**
  - Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent`
    ```
    ........................................................................ [ 94%]
    .........................                                                [100%]
    445 passed, 12 skipped in 18.09s
    ```
- **Full existing suite, excluding the four new packs:** see §3a.
- **Lint.**
  - Command: `python lint/run.py`
    ```
    S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

    SDK-LINT: PASS
    ```
    The exit code was 0. A002 improved from 703 to 601 with no baseline change.
- **Fresh-interpreter imports.** Each of these imports alone with no error: `vidbyte`, `vidbyte.lib.process`, `vidbyte.lib.dataclasses.{opencode,grok,muse,harness_backends}`, `vidbyte.lib.errors`, `vidbyte.lib.configs`, `vidbyte.harnesses.native`.
- **Fixed marker bytes.**
  - Command: `git show HEAD:vidbyte/harnesses/native/__init__.py | sha256sum`
    ```
    0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a *-
    ```
- **INV-22 byte-identical files.** `git diff --quiet 8b77aba0..HEAD -- vidbyte/__init__.py contracts/sdk-public-api.json vidbyte/tools/builtins/__init__.py vidbyte/lib/dataclasses/__init__.py vidbyte/lib/constants/__init__.py vidbyte/harnesses/__init__.py vidbyte/mcp_server pyproject.toml lint` printed `INV-22 files unchanged`.
- **Not run (blocked before the gates):** `scripts/run_ci.py` (source and package stages) and Semgrep.

## 3a. Full existing suite

- Command: `PYTHONPATH=$(pwd) python -m pytest -q -x --ignore=tests/features/grok_host --ignore=tests/features/opencode_host --ignore=tests/features/muse_host --ignore=tests/features/native_backends`
  ```
  ................s....................................................... [ 99%]
  .........                                                                [100%]
  3956 passed, 13 skipped in 33.23s
  ```
  The exit code was 0, so P1 broke no existing test.

## 4. Options

1. **The S2 test author fixes the three tests with the one-line fixes in §2, then S3 resumes at P2 row 22 on top of `c3bd8c6f`.**
   - Consequence: the gate "all S2 tests pass" becomes reachable, and the committed P1 stands unchanged.
   - Cost: a small test-only commit, after which the orchestrator must move the `cfad74f8` diff base to the new test commit.
2. **Change the implementation to make D-1 pass, by refusing a plain `set` in `require_enum_set`.**
   - Consequence: this contradicts §9.1, EC-23, EC-134 and S2-4, and changes a §8.5/§9.1 contract, so it needs spec approval.
   - It still leaves D-2 and D-3, which no implementation can pass.
3. **Let S3 continue P2-P5 now and treat D-1 to D-3 as known test defects for S2 to fix in parallel.**
   - Consequence: the work moves forward.
   - Cost: S3 cannot report DONE with all 1635 tests green until the tests are fixed, and the gate run has to be repeated after the fix.

## 5. Recommendation

Option 1, run alongside option 3 if the orchestrator wants to save time. All three fixes are mechanical edits to test helpers or values and do not touch any assertion about SDK behaviour, and the spec is clear in each case.

## 6. Niche facts for the next agent

- **I001 import order:** `lint/core/ruff.py` runs `ruff check pyproject.toml vidbyte --config lint/ruff.toml --select I001,...`. It wraps any `from x import a, b` that is longer than the isort line length into a parenthesised block, so a plain `ruff check` with the default selection misses it. Run `python -m ruff check <files> --config lint/ruff.toml --select I001 --fix --no-cache` on new files only. `vidbyte/lib/errors/__init__.py` and `vidbyte/lib/enums/model_provider.py` already had I001 at the base and still count once each; do not reorder them.
- **S009 (mypy) on this Windows box:**
  - mypy flags `os.killpg` unless it sits behind an `if sys.platform == "win32": return` guard that mypy can narrow.
  - `require_text` returns `str`, so use that return value to narrow an optional field before passing it on.
- **The `grok_api` fixture:** it imports `vidbyte.harnesses.native.grok` (`GrokHost`, `run_grok_once`), so every grok-pack test, including the lib-only record and process tests, errors until row 29+ exists.
- **Line endings:** `core.autocrlf=true`, and new files are written with LF. Git warns "LF will be replaced by CRLF", which is harmless. The marker blob is LF and its hash matches.
- **Constants and records:**
  - Timing constants are read at call time through `from vidbyte.lib.constants import native_hosts as native_host_constants`. The `fast_stop` fixture patches them there.
  - `RecordFieldConverter` (`to_tuple`, `to_mapping`, `require_instance`) sits beside `RecordFieldValidator` in `vidbyte/lib/dataclasses/validation.py` and is used by all the record modules.

## 7. Report file

This report is written to `docs/spec/native-grok-opencode-meta-hosts/reports/S3-implementer.md` and left uncommitted for the orchestrator's pipeline-state commit.
