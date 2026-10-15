# Provider keys and the relay

## Folder Description / Intent

This folder holds the feature tests for `api_keys`, `vidbyte_api_key`, `ProviderKeyMatcher`/`ProviderKeys`, the `X-Vidbyte-Provider-Key` relay, and `TextModelMode.DIRECT`. The tests are offline: the only fakes are the inner HTTP transport, the retry wait, and the process environment. Matching, credential resolution, the adapters, `TextModelRunner`, and `VidbyteGatewayTransport` all run for real. The behavior lives in `vidbyte/lib/` (`registries/provider_keys.py`, `registries/models.py`, `dataclasses/model_configs.py`, `dataclasses/agents.py`, `http/vidbyte_gateway.py`, `runners/`) and `vidbyte/agents/`, not here. The contract comes from `docs/spec/byok-api-keys/spec.md`.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` lists the known failure modes, the contract, the invariants, and the strategies left out on purpose.
- `provider_keys_fixtures.py` provides runtime-built fake keys per provider format, per-dialect answers, the per-provider scripted transport, and the recording environment.
- `test_provider_keys_acceptance.py` runs the spec's section 4 snippet and the developer-facing text-call promises in each mode.
- `test_provider_keys_matching.py` covers `ProviderKeyMatcher`: list shapes, key formats, unique assignment, primaries, Vidbyte entries, and record pass-through.
- `test_provider_keys_property.py` checks that matching ignores list order and the environment, with seeded random and exhaustive permutations.
- `test_provider_keys_agents.py` covers agents, fallbacks, aggregates, forks, and other children carrying one record.
- `test_provider_keys_sessions.py` covers checkpoints, resume, continue, fork, and fork recovery.
- `test_provider_keys_modes.py` covers `TextCredentials`, credential resolution per mode, gateway-shape refusals, streaming, pinning, and unsendable keys.
- `test_provider_keys_wire_contract.py` covers the relay header, body, cap, timeout floor, re-sends, and concurrent calls.
- `test_provider_keys_failures.py` covers gateway failure wording for paid and relay calls, and relayed provider refusals.
- `test_provider_keys_security.py` covers reprs, leak scenarios, the credential guards, and the harness redactor.
- `test_provider_keys_contract.py` covers names, constants, exports, field orders, signatures, the old keyword, and the manual scripts.

## Logs

- 2026-10-13 - Pack added red, ahead of the implementation, from spec r4 (S2 test author).
