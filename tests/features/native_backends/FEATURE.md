# Feature: Native backend profiles (GLM and DeepSeek)

## High-Level Feature Description

A developer points Claude Code or opencode at GLM (through Z.ai) or DeepSeek with one call. `vidbyte.harnesses.native.backends` holds two declared profiles and six functions over them. `build_claude_backend_env` returns the exact environment Claude Code needs, with the key hidden from every `repr`. `build_opencode_backend_provider` names opencode's built-in provider for the backend. `check_backend_compat` refuses, before any money is spent, a request the backend would silently mangle or whose terms do not allow the harness. `check_backend_ready` and `get_deepseek_balance` check that a key is present, and for DeepSeek read the account balance, without ever making a call that spends money. Three READ tools expose the readiness, balance and listing functions to a model through `HarnessBackendTools`.

## Contract

- `HARNESS_BACKENDS` (`vidbyte.lib.configs.harness_backends`, re-exported from `vidbyte.lib.configs`) is a tuple of two `HarnessBackend` records in `HarnessBackendName` order, GLM then DeepSeek, with exactly the field values of spec §9.1.
- `HarnessBackends` (`vidbyte.harnesses.native.backends.profiles`) has six static methods, re-exported unchanged as the module functions of `vidbyte.harnesses.native.backends`:
  - `list_harness_backends()` returns `HARNESS_BACKENDS`, with no I/O and no key.
  - `build_claude_backend_env(backend, model=None)` returns a `ClaudeBackendEnv`. Its `as_environ()` holds exactly `ANTHROPIC_BASE_URL`, the profile's `claude_env` pairs, the profile's model slots filled with `model` (or the first `claude_models` entry), and `ANTHROPIC_AUTH_TOKEN` set to the value of the profile's `auth_env_var`, read from `os.environ` on this call.
  - `async check_backend_ready(backend)` returns a `BackendReadiness`. GLM checks the key only (`remote_verified=False`). DeepSeek also reads the balance (`remote_verified=True`, `balance` set).
  - `check_backend_compat(backend, request)` returns `None`, or raises `backend.harness_not_allowed` or `backend.feature_unsupported` with every offending feature listed, sorted. It makes no I/O and needs no key.
  - `async get_deepseek_balance()` sends one `GET https://api.deepseek.com/user/balance` with the key as a Bearer header, through `HttpTransport` with `BACKEND_HTTP_TIMEOUT_SECONDS` (15 s) and `BACKEND_MAX_RESPONSE_BYTES` (64 KiB), and returns a `DeepseekBalance` whose amounts are `Decimal`s parsed from the vendor's strings.
  - `build_opencode_backend_provider(backend)` returns an `OpencodeBackendProvider` naming the built-in provider, its source and child key variables and its model ids. It makes no I/O and does not check the key.
- `backend` is a `HarnessBackendName` or one of its value strings. Any other value raises `configuration.invalid_argument` naming `backend`.
- Every failure is a `NativeHostError` with a code from spec §6.3.6, a non-empty next step holding the row's required token, and string-only context. The only other exceptions are `ConfigurationError` while a record is built, and `asyncio.CancelledError`.
- `HarnessBackendTools()` holds `list_harness_backends`, `check_backend_ready` (one required string parameter, `backend`) and `get_deepseek_balance`, all READ. A tool never raises except `CancelledError`. It returns `ToolResult.success` with metadata `{"harness": "backend", "operation", "truncated"}` and sorted-key JSON output, or `ToolResult.error` with `error`, `next_step`, `hint`, `operation` and `harness`.

## Actors / Callers

- Developers who build a Claude Code environment or an opencode provider for GLM or DeepSeek, or check a backend before a run.
- `OpencodeHost`, which calls `build_opencode_backend_provider` for each configured backend.
- Models calling the three backend tools through `HarnessBackendTools`.

## Inputs and Preconditions

- `GLM_API_KEY` and `DEEPSEEK_API_KEY` in `os.environ`. The tests set fake values with `monkeypatch` and delete the real variables for every test.
- For DeepSeek readiness and balance, the endpoint `https://api.deepseek.com/user/balance`. The tests answer it with `httpx.MockTransport` behind a patched `httpx.AsyncClient`. No test reaches the network.

## Observable Outcomes

- The returned records, their fields, `repr` and `str`, and `ClaudeBackendEnv.as_environ()`.
- The raised `NativeHostError`: `failure_code`, `next_step`, `operation`, `context` and message.
- The `ToolResult` status, output and metadata.
- Every HTTP request the fake endpoint received (method, URL, headers), and the options of every `httpx.AsyncClient` that `HttpTransport` built.

## State Transitions

None. The profiles are fixed data, and no function stores anything. `build_claude_backend_env` and `build_opencode_backend_provider` persist nothing. Each call reads the key variables again.

## Invariants

- No key value appears in a message, a context value, a next step, a `repr`, a tool output or tool metadata. Vendor text is scrubbed, every exact occurrence of the injected key becomes `<redacted>`, and the text is capped at `NATIVE_VENDOR_MESSAGE_MAX_CHARS` (INV-6).
- Argument and key checks happen before any HTTP request (INV-5).
- A readiness check never spends money: GLM makes no remote call, and DeepSeek makes only the balance `GET` (D-17).
- `CancelledError` always propagates (INV-2).
- `HttpTransport` failures never escape raw. A status-less `ProviderRequestError` becomes `backend.server_unreachable`, and its excerpt is never shown (INV-1, T-3).
- `check_backend_compat` refuses exactly the requests whose harness is not allowed or whose features intersect the profile's unsupported set.

## External Dependencies

- `HttpTransport` (`vidbyte/lib/http/transport.py`), which builds a fresh `httpx.AsyncClient` for each call.
- `HarnessRedactor` (`vidbyte/harnesses/serialization.py`), through `NativeErrorFactory`.
- `CredentialKeyPolicy` (`vidbyte/lib/util/credential_keys.py`), for the `claude_env` check.

## Known Failure Modes

These are the failure inventory the tests were chosen from, given as input → wrong output.

- **Wrong environment.**
  - A model slot is left at the default when a model was chosen.
  - The haiku pair is overwritten.
  - A key from the other backend is used.
  - `as_environ()` gains or loses a key, so Claude Code talks to Anthropic with a GLM key (AC-13).
- **Cached key.** The key is read once and cached, so a rotated or removed key is not seen (§13).
- **Default next step for a missing key.** The default text names both variables, so it hides which one is missing. The rows require the backend's own variable (EC-123, EC-127).
- **Union model check.** A DeepSeek model is accepted for GLM, because the check runs against all declared models (EC-125).
- **Silent mangling.** DeepSeek is accepted with MCP servers or other ignored features, or only the first offending feature is reported (EC-136). GLM is accepted for Grok or Muse, which its terms forbid (EC-135).
- **Spending readiness.** A one-token test call is made, or GLM is called remotely (D-17, NG-6).
- **HTTP mapping.**
  - Every status is mapped to `api_error`.
  - A size-ceiling `ProviderRequestError` with status 200 becomes `server_unreachable` instead of `protocol_mismatch`.
  - A redirect is followed and the Bearer header is sent to another host (EC-127 to EC-132).
- **Lenient parsing.** A balance is parsed through `float`, a number is accepted where a decimal string is required, or a wrong shape raises `KeyError` or `TypeError` raw (EC-132, INV-1).
- **Leaks.** An echoed key reaches `vendor_error`, the message or a tool result. `ProviderRequestError.response_excerpt` is shown. Vendor text is not capped (AC-5, INV-6).
- **Swallowed cancellation.** `CancelledError` becomes `runtime.error` or a tool error result (INV-2, EC-141).
- **Tool argument parsing.** `"GLM"` (wrong case), `7` or a missing `backend` raise instead of returning `configuration.invalid_argument` (EC-147, EC-138).

## Test Suite Map

- `test_native_backends_errors.py` holds the §6.3.6 error table. Each row runs against the function, and the readiness and balance rows also run against their tool. Each row asserts the code, the token, the exact or default next step, the context, and what the endpoint received.
- `test_native_backends_profiles.py` checks the declared profiles, the module functions, `list_harness_backends`, `build_claude_backend_env` (AC-13 and exhaustive over the models), `check_backend_compat` (AC-14 and exhaustive over the feature subsets and harnesses) and `build_opencode_backend_provider`.
- `test_native_backends_balance.py` checks the balance request, its deadline, decimal parsing, readiness for each backend, and cancellation.
- `test_native_backends_security.py` checks the AC-5 echo for the error and the tool, the classified statuses, unparseable bodies, transport exception text, the vendor-text cap, and `repr`s.
- `test_native_backends_records.py` checks the field validation of the seven records, frozen copies, the hidden token, and the defaults.
- `test_native_backends_tools.py` checks the toolset, the tool classes, the success shapes, EC-147 and EC-138, `ToolExecutor` under the default policy, and EC-141.

Run everything with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends`.

## Omitted Testing Strategies

- **EC-126 and EC-137.** No declared profile lacks `CLAUDE_CODE` or `OPENCODE` in `allowed_harnesses`, and the profiles are fixed data rather than a §13 seam.
- **Harness checked before features in `check_backend_compat`.** No declared profile has both a disallowed harness and an unsupported feature.
- **EC-5 (`runtime.error`) per function.** It needs a defect inside the function. `NativeErrorFactory.from_unexpected` is tested in the grok_host pack.
- **Live calls and real keys.** These are forbidden. HTTP is faked at `httpx.AsyncClient` under `HttpTransport`.
- **Wall-clock timeouts.** The 15 s deadline is checked through the client options, not by waiting.
