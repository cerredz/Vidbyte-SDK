# S1 spec author report: managed-generative-models

- **Spec:** `docs/spec/managed-generative-models/spec.md`, r1, committed as `8ee7ed1e`.
- **Base:** `c07529316a5325bce986f84868ecbabb3b7f3056`.

## What I read

**Pipeline inputs**
- `docs/spec/managed-generative-models/request.md` (all of it).
- `docs/spec/managed-generative-models/context/code-map.md`.
- The backend spec `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-generative-model-gateway/docs/spec/generative-model-gateway/spec.md` (r1 at `263ed4e0e`), in particular §9.2, which is the wire contract, and §15. No other file under `docs/`.

**Repo rules**
- `AGENTS.md`, `REPO_MAP.md` (lib, constants, enums, errors and http sections).
- `vidbyte/lib/README.md`, `vidbyte/lib/registries/README.md`, `lint/contracts/README.md`.

**Code**
- `vidbyte/lib/dataclasses/model_configs.py` (TextModelConfig, DecisionModelConfig)
- `vidbyte/lib/registries/models.py` (resolve_api_key, resolve_endpoint, resolve_active, _resolve_from_environment)
- `vidbyte/lib/runners/text.py`, `vidbyte/lib/runners/streaming_text.py`, `vidbyte/lib/runners/utility.py` (build path)
- `vidbyte/lib/http/transport.py`, `vidbyte/lib/http/parser.py`, `vidbyte/lib/http/__init__.py`
- `vidbyte/lib/constants/jev.py`, `vidbyte/lib/enums/decision_model.py`, `vidbyte/lib/enums/model_provider.py`
- `vidbyte/lib/config/__init__.py`, `vidbyte/lib/errors/base.py`
- The adapters: `vidbyte/providers/openai.py`, `anthropic.py`, `gemini.py`, `compatible.py` (`run_text`, cap fields, `extra_body`)
- `vidbyte/providers/typesafe.py` (managed headers, failure mapping)
- `vidbyte/agents/base.py:_runner_for_model`
- `vidbyte/lib/registries/pricing.py`, for the priced default models

**Lint rules**
- `lint/rules/` A007, C008, C017 (with `lint/core/url_flow.py`), C020, S010, S012, S054.
- `lint/baseline.json`.

**Field guide**
- `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`: strict-config-dataclasses, provider-api-contracts, blocking-lint-invariants, local-ci-verification, class-bound-helpers.

**Tests**
- `tests/test_config_validation.py`, read to check that BYOK whitespace handling and missing-key behavior stay intact.

**Verification probe**
- I checked that mypy accepts the `HttpTransport.request` override shape. I wrote a replica in the scratchpad and ran `mypy 2.3.1 --strict --cache-dir=nul`; it printed "Success". Nothing was written in the worktree.

## Approaches weighed

1. **Transport decorator in lib http (chosen, D-1).**
   - `TextModelRunner` wraps its transport in `VidbyteGatewayTransport`.
   - The adapter builds its native body as usual. The decorator discards the adapter's URL and headers, wraps the body in `{provider, model, body}`, and POSTs it to the one route with the bearer key and an `Idempotency-Key`.
   - Zero adapter edits. Every change sits in `vidbyte/lib/`.
   - C017 traces the inner call to the constant URL, the same mechanism TypeSafe passes with.
2. **Endpoint redirect plus a header builder called by adapters** (request.md §E.2/E.3). Rejected, because the adapters append four suffixes:
   - it reaches four paths, not the 1 route;
   - C017 fails on non-contract paths;
   - it needs edits in `vidbyte/providers/`, outside lib.
3. **Fall-through inside `ProviderModelRegistry.resolve_api_key`** (request.md §E.2). Rejected. That method also serves the image, video, audio and embedding configs and direct-mode Decision, so `vb_live_` keys would reach vendors. The fall-through moved into two new classmethods instead.
4. **Content-addressed idempotency keys.** Rejected, because identical repeated prompts would replay a stale billed answer.
5. **Host.** I chose a new live-host literal (`vidbyte-backend.onrender.com`) over deriving it from the Jev constant (`api.vidbyte.pro`). Evidence:
   - C018's repair text says only live origins may appear.
   - The contract marks `api.vidbyte.pro` as `planned`.

## Disagreements with the scout or the request (with evidence)

- **Four routes versus one.** request.md §E.2–E.4 has "no adapter change to the URL logic" through suffix paths. That conflicts with Prompt 5's one route, and the user's prompt wins. Evidence: the adapter suffixes in `providers/openai.py:30`, `anthropic.py:25`, `gemini.py:27`, `compatible.py:32`.
- **"Adapters call one shared header builder"** (request.md §C, E.3 step 12). Under D-1 the adapters never address the gateway, so a builder they call would have no caller. I recorded "one shared header builder" as the single managed-header construction inside `VidbyteGatewayTransport` (D-3).
- **"`HttpTransport` refuses to retry a POST without an idempotency key"** (request.md §C). This holds only when `retry_count > 0` (`lib/http/transport.py:22-25`), and text adapters pass 0. The SDK sends a fresh key per request. Reusing a key across agent-runtime retries needs `agents/runtime.py`, so it became Q-1, default no.
- **Host `api.vidbyte.pro`** (request.md E.2/E.3). It is not live per the contract (`lint/contracts/vidbyte-platform-contract.json:207-208`), so D-4 uses the live Render host.
- **Key-crossing guards need relaxing** (request.md §E.3 step 11). They drop only an explicit key, so an environment `VIDBYTE_API_KEY` already works for children (code-map §4.10). They are unchanged; Q-4, default no.
- **Scout §4.9 risk on `tests/test_model_registry.py:57-61`.** Because `resolve_api_key` is untouched, that test stays valid on a machine with `VIDBYTE_API_KEY` set. Only text-config tests that do not clear the environment are affected; this is noted in §13.
- **The constant move** in request.md §E.2/E.3 step 9 (header names into a shared gateway module) is not needed and is out of scope (NG-8). The existing `JEV_IDEMPOTENCY_KEY_HEADER` is reused.

## Least-sure assumptions

1. **A-1: the backend contract may change.** The backend spec reviewer is still running. The decorator design survives any single-route contract, but the envelope keys, the discriminator and the provider list are consumed verbatim from r1.
2. **A-3: mypy acceptance of the override.** It is verified only on a replica, not through `lint/mypy.ini` / S009 on the real package.
3. **D-8 / A-6: an 8,192-token default cap for all six providers**, Anthropic included, where the BYOK default is 1,024. Output limits were not checked against vendor docs. A model whose output limit is below 8,192 returns a relayed 400 until the caller sets `max_output_tokens`.
4. **A-2: C017 tracing.** I believe the tracer evaluates the decorator's inner call with the constant URL and the `bearer_headers` + subscript header shape and judges it API_KEY-credentialed. This is from reading `lint/core/url_flow.py`, not from running it, because the contract cannot be re-vendored at S1.
5. **D-12: the placeholder key.** `resolved_api_key()` returns `"vidbyte-managed"` in managed state, which keeps the real key out of adapter-built headers. It is a new convention, and a reviewer could prefer another shape.
6. **EC-27: behavior change for Jev users.** Anyone who already has `VIDBYTE_API_KEY` set and no provider key used to get an error from text calls. They are now billed. This is intended by the request, but it is money-affecting.
