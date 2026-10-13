# Feature: Vidbyte-managed text calls

## High-Level Feature Description

A developer who holds only a Vidbyte key (`VIDBYTE_API_KEY=vb_live_…`), or who asks for `mode=TextModelMode.VIDBYTE_MANAGED`, gets every non-streaming text call from `TextModelRunner`, and so from every agent, sent to one Vidbyte gateway route instead of to the vendor. The backend pays the provider with its own key and bills the call at provider cost plus 2%. Since byok-api-keys (`docs/spec/byok-api-keys/spec.md`, G-1, INV-1, INV-2), a developer who also holds their own provider key for the call's provider still goes through the gateway in the default `AUTO` mode: the SDK relays that key in `X-Vidbyte-Provider-Key` and the call is billed the fee only. A developer who wants vendor-direct calls with no Vidbyte key sets `mode=TextModelMode.DIRECT`, and those requests stay byte-identical to the base commit. If this feature regresses, one of three things happens: Vidbyte pays the provider for a call the user meant to pay with their own key, the `vb_live_` key leaks to a vendor host or into an error, or a managed call is paid twice because a retry minted a new idempotency key.

## Contract

- Keys come from two fields (byok-api-keys D-24, D-25): `api_keys` (a list of provider keys, matched to providers by format; a `vb_live_` entry in it is the Vidbyte key) and `vidbyte_api_key`. `api_key` is gone from `TextModelConfig`.
- With `mode=AUTO` (the default), every call goes to the gateway (G-1, INV-1). The Vidbyte key is `vidbyte_api_key`, the list's Vidbyte entry, or `VIDBYTE_API_KEY`; without one the runner raises M-9 naming `TextModelMode.DIRECT`. The provider key is `api_keys`' key for the call's provider, then the provider's own env var; when one is found it is relayed (INV-2), otherwise Vidbyte pays the provider. A `vb_live_` value in a provider env var is refused (EC-13).
- With `mode=VIDBYTE_MANAGED`, the key is `vidbyte_api_key`, the list's Vidbyte entry, or `VIDBYTE_API_KEY`; the provider env var is never read and no provider key is relayed.
- With `mode=TextModelMode.DIRECT`, the call goes to the vendor with the provider key, `VIDBYTE_API_KEY` is never read, and the request is byte-identical to the base commit (INV-6). Only `DIRECT` accepts a custom endpoint, an unserved provider, or streaming.
- A gateway call sends `POST https://vidbyte-backend.onrender.com/api/v1/models/generate` with exactly three headers (`authorization: Bearer <vb_live_ key>`, `content-type: application/json`, `Idempotency-Key: <32 lowercase hex>`), plus a fourth, `X-Vidbyte-Provider-Key: <provider key>`, only when it relays, and the body `{"provider", "model", "body"}`, where `body` is the adapter's own vendor-direct body for the pinned config. No request goes anywhere else.
- A 409, a 502, or an answer that is not a JSON object is re-sent at most twice with the same key and envelope, after 0.5 s and 1.0 s, and only while the call's one deadline (its own timeout, at least 630 s, counted from the first POST) still covers the wait. Each attempt keeps the full timeout, and the error states how many re-sends the call made. Nothing else is retried, including a missing response.
- Every managed failure is `ProviderRequestError(provider="vidbyte")` with no response excerpt, no chained exception, and no byte of the gateway or provider body.
- A gateway-mode config (`AUTO` or `VIDBYTE_MANAGED`) has a non-secret placeholder as `resolved_api_key()`, refuses a custom endpoint and unmanaged providers when it is built (D-23), carries an output cap (32,768 unless the caller set one), and waits at least 630 s per attempt, relayed or not (INV-20).

## Actors / Callers

SDK users calling `TextModelRunner.run/arun`; agents through `Runner.build`; `StreamingTextModelRunner` callers (refused in every mode except `DIRECT`, INV-11); `DecisionModelConfig`, which shares the managed-key resolver.

## Inputs and Preconditions

`TextModelConfig` fields, the process environment (`VIDBYTE_API_KEY`, `<PROVIDER>_API_KEY`), and the transport. Tests inject a scripted transport and always run under `patch.dict(os.environ, …, clear=True)`, so a developer's real keys never change an outcome.

## Observable Outcomes

The recorded transport calls (URL, method, headers, body, `timeout_seconds`, `idempotency_key`, attempt count), the parsed `TextModelResponse`, the raised error's type, message, `details`, `status_code`, `response_excerpt`, `__cause__` and `__context__`, and `repr(TextModelConfig)`.

## State Transitions

The mode is fixed in the config, and a gateway-mode runner resolves its Vidbyte key and its relayed provider key once, at construction (INV-12). Changing the environment afterwards changes nothing it sends. A `DIRECT` runner never sends the Vidbyte key anywhere.

## Invariants

- The `vb_live_` key reaches only the gateway URL as the bearer; never a vendor request, the relay header, a header an adapter builds, a repr, or an error.
- A relayed provider key appears only in the `X-Vidbyte-Provider-Key` header of a gateway request; never in the body, another header, a repr, a log, or an error.
- One `Idempotency-Key` per `arun` call; the same key and byte-identical envelope on that call's retries; different keys for different calls, including concurrent ones.
- `DIRECT` requests stay byte-identical to the base commit's BYOK requests (INV-6).
- An `AUTO` call with no provider key sends exactly what the base commit sends in managed state (INV-16).

## External Dependencies

`vidbyte.lib.http` (the inner transport is the only fake), the retry wait (`asyncio.sleep`, patched where `vidbyte.lib.http.vidbyte_gateway` looks it up), the provider adapters in `vidbyte/providers/` (real, unchanged), and `README.md` (the fee disclosure).

## Known Failure Modes

Each line is input + state → wrong output.

- `OPENAI_API_KEY=sk-…` and `VIDBYTE_API_KEY` both set, in `AUTO` → no `X-Vidbyte-Provider-Key` header → Vidbyte pays the provider for a user who brought a key (byok-api-keys INV-2).
- `MOONSHOT_API_KEY=sk-…` with provider kimi, env name guessed as `KIMI_API_KEY` → kimi's key is not relayed → Vidbyte pays.
- Blank `OPENAI_API_KEY=""` with `VIDBYTE_API_KEY` → treated as a provider key → "Missing API key" instead of managed.
- `OPENAI_API_KEY=vb_live_A`, `VIDBYTE_API_KEY=vb_live_B` → bearer B, or the Vidbyte key sent to api.openai.com (EC-5).
- `VIDBYTE_API_KEY` with a trailing newline → newline inside the `authorization` header.
- Explicit `vb_live_` key with provider openrouter → key sent to OpenRouter (EC-3).
- Only `VIDBYTE_API_KEY`, provider openrouter → a confusing managed error instead of today's "Missing API key" (EC-2).
- Managed state plus `endpoint` → the bearer follows a caller URL (EC-6, EC-7).
- Adapter header built from the real key → the `vb_live_` key rides in `x-api-key` to Anthropic on direct adapter use (EC-21).
- Relayed Anthropic/OpenAI error body `{"error": {...}}` read as the gateway's `"error": true` → wrong remedy message.
- 200 with an HTML or JSON-array body → handed to the adapter → adapter error copies the page into `response_excerpt`.
- Error raised inside `except` → `__context__` holds the inner error whose `response_excerpt` has the body (D-17).
- Retry mints a fresh key per attempt → the gateway bills each attempt.
- Key kept on shared runner or transport state → concurrent calls swap keys across retries.
- `except BaseException` → agent cancellation swallowed and turned into a provider error.
- `max(timeout, 630.0)` → a NaN timeout stays NaN.
- Default cap applied with `max`/`min` → a caller's 100 or 20,000 is overridden.
- Streaming refusal keyed on "`VIDBYTE_API_KEY` is set" instead of on the mode → `DIRECT` streaming breaks, or an `AUTO` stream bypasses the gateway (byok-api-keys INV-11).
- `mode` inserted before `timeout_seconds` → positional construction breaks.

## Historical Regressions

None yet. Add one line per fixed bug with the test that protects it.

## Test Suite Map

- `test_managed_text_acceptance.py`: the README snippet run as written (AC-1), all six providers end to end (AC-2, AC-23), the per-provider relay rule with byte-identical `DIRECT` goldens (AC-3, EC-30), the agent path (AC-24), and the README fee disclosure (AC-18).
- `test_managed_text_selection.py`: the key-resolution table (relay in `AUTO`, vendor only in `DIRECT`), explicit mode, credential errors, endpoint and provider refusals, streaming refusal, runner pinning, other modalities untouched, the config field contract, repr, the adapter placeholder, and the resolver shared with `DecisionModelConfig`.
- `test_managed_text_wire_contract.py`: output caps per dialect, `extra_body` passthrough, the 630 s attempt floor, and the emitted-key allowlist per dialect (AC-26).
- `test_managed_text_failures.py`: credential-safe errors per status, remedy wording, relayed provider errors, missing responses, edge pages, unexpected exceptions, cancellation, same-key retries, one key per call, and concurrent calls.
- `managed_text_fixtures.py`: the scripted inner transport, provider-shaped answers, gateway error bodies carrying a canary and a key-shaped string, and the retry-wait recorder.

Run `python -m pytest tests/features/sdk_managed_text` (from a worktree, with `PYTHONPATH` set to the worktree).

## Omitted Testing Strategies

- Property-based and fuzz: `hypothesis` is not a dependency and NFR-6 forbids adding one. The algebraic invariants (one key per call, the timeout floor, the retry rule) are covered by exhaustive tables over their small domains instead.
- Stress and performance: the feature adds one `uuid4` and one JSON parse per answer (NFR-7). No limit in the SDK depends on volume; the 2,000,000-byte cap is the gateway's.
- Browser, accessibility, migration: no UI, no persisted state.
- Live end-to-end against the backend: tests never touch the network (NFR-6). The backend PR owns the gateway's behavior.
- Agent-runtime retries reusing a key (NG-9, Q-1 = No) and the controls not built (Q-8 to Q-11): nothing to test.
- `vidbyte.lib.http` not re-exporting `VidbyteGatewayTransport` (R-10): a failure there would not change what any caller sees.
- C017 route presence and the C020 count: enforced by `lint/run.py` through `python scripts/run_ci.py`, not duplicated in pytest.

The relay itself (matching `api_keys`, `DIRECT`, relay headers, relay failure wording, agents and sessions) is covered by `tests/features/sdk_provider_keys/`. Existing module tests that also guard this boundary: `tests/test_text_model_runner.py` (BYOK request shapes, including Anthropic's 1,024 default), `tests/test_jev_managed_gateway.py` (Decision managed mode), `tests/test_streaming_text_runner.py` (provider refusal).
