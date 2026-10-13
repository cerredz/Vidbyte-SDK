# Native backend profile feature tests

## Folder Description / Intent

This folder checks the public promise of `vidbyte.harnesses.native.backends`. Two declared profiles, GLM through Z.ai and DeepSeek, let a developer point Claude Code or opencode at either backend with one call. Six functions build the Claude Code environment and the opencode provider, check compatibility and readiness, and read the DeepSeek balance. Three READ tools expose the readiness, balance and listing functions to a model. The tests run the real functions, records, `HttpTransport` and tools. Only the network is faked, with `httpx.MockTransport` behind a patched `httpx.AsyncClient`, and the key variables come from `monkeypatch`.

The implementations belong in these places:
- `vidbyte/harnesses/native/backends/` holds `HarnessBackends` and the module functions.
- `vidbyte/lib/configs/harness_backends.py` holds `HARNESS_BACKENDS`.
- `vidbyte/lib/dataclasses/harness_backends.py` holds the records.
- `vidbyte/lib/enums/harness_backends.py` holds `HarnessBackendName` and `BackendFeature`.
- `vidbyte/lib/constants/native_hosts.py` holds the `BACKEND_*` constants and the next steps.
- `vidbyte/tools/builtins/harness_backends/` holds the three tools.
- `vidbyte/tools/toolsets/harness_backends.py` holds `HarnessBackendTools`.

## Non-Goals

- Do not test the shared vocabulary here: the code catalog, `NativeHostError`, `NativeErrorFactory`, `RecordFieldValidator` and the enum members. The grok_host pack owns them.
- Do not test `OpencodeHost`'s use of the providers, such as `ZHIPU_API_KEY` in the server's environment or EC-61 and EC-62. The opencode_host pack owns that.
- Do not make live calls or use real keys. `conftest.py` deletes the real key variables, and its fake endpoint is autouse.

## File Index

- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py` provides the following:
  - The lazy imports (`backends_api`, `backend_tools_api`).
  - The autouse fake DeepSeek endpoint (`deepseek_endpoint`), which also records client options.
  - The autouse key isolation, and fake keys (`backend_keys`).
  - The error-shape checks (`check_native_error`, `check_tool_error`).
  - A tool lookup (`backend_tool`).
- `test_native_backends_errors.py` holds the §6.3.6 error table, with one case per function and code. It runs each row against the function and, where a tool exists, against the tool. Start here for a wrong code or next step.
- `test_native_backends_profiles.py` checks the declared profiles and the four functions that make no network call: AC-13, AC-14, and the exhaustive compatibility and environment properties. Start here when Claude Code or opencode reaches the wrong endpoint, model or key.
- `test_native_backends_balance.py` checks the DeepSeek balance call and both readiness checks: the request, the deadline, decimal parsing, the no-spend rule and cancellation.
- `test_native_backends_security.py` checks that an echoed key becomes `<redacted>` and never reaches an error or a tool result (AC-5), that transport exception text is never shown, and the vendor-text cap.
- `test_native_backends_records.py` checks the field validation of the seven backend records, and that they are frozen and hide their token.
- `test_native_backends_tools.py` checks the three tools and `HarnessBackendTools`: the names, permissions, success shapes, EC-147, `ToolExecutor` and cancellation.

## Logs

- 2026-10-13 - The pack was written red before implementation, from spec r3 of `native-grok-opencode-meta-hosts`. Every test fails at setup until `vidbyte.harnesses.native.backends` and its records, enums, constants and tools exist.
