# Feature: provider keys (`api_keys`), the relay, and `TextModelMode.DIRECT`

## High-Level Feature Description

Agents and `TextModelConfig` take two kinds of keys: `api_keys`, a list of provider keys in any order, and `vidbyte_api_key`. `ProviderKeyMatcher` matches the list once, at the root the developer handed it to, and produces a `ProviderKeys` record that travels unchanged to every fallback, fork, and child agent. In the default `AUTO` mode every text call goes through the Vidbyte gateway. A call with a matched key for its provider (or that provider's environment variable) carries that key in the single header `X-Vidbyte-Provider-Key`, so the provider bills the caller and Vidbyte bills only its fee. Without one, Vidbyte pays the provider, as before. `TextModelMode.DIRECT` is the one explicit way to call a provider with no Vidbyte key, and its requests are byte-identical to the base commit's BYOK requests. Contract: `docs/spec/byok-api-keys/spec.md` (r4).

If this feature regresses, one of four things happens: a provider key reaches the wrong vendor (or any log, repr, or error), Vidbyte pays the provider for a call the user meant to pay with their own key, a list is silently mis-matched instead of refused, or a `DIRECT` caller's requests change.

## Known Failure Modes

Each line is input + state → wrong output. The test that catches it is in the Test Suite Map.

- `api_keys="sk-…"` (a bare string) → iterated into one-character keys → garbage matching, or a key leaked character by character into an error (EC-1, M-1).
- `api_keys=[K_x, K_a]` and `[K_a, K_x]` → different matches → order-dependent billing (AC-7, INV-9).
- An unproven key guessed from its length or characters → a DeepSeek key sent to Moonshot (INV-25, D-2).
- Two unproven `sk-` keys with a deepseek agent and an openai backup → bound by order → the wrong vendor gets a key (AC-38, M-19).
- A list without the agent's own provider's key → that provider's calls silently go Vidbyte-paid while the user believes they are relaying (INV-24, M-18).
- A fork, fallback, or aggregate child re-matches the raw list against its own providers → a key bound to deepseek at the root reaches kimi in the child (D-13, AC-34).
- A restored session re-matches against the restored agent's providers instead of the stored names → M-6, or a different binding than the root (D-30, AC-41).
- A Vidbyte key in `api_keys` treated as a provider key → `vb_live_…` sent in `X-Vidbyte-Provider-Key` or to a vendor (INV-13, AC-11).
- `OPENAI_API_KEY=vb_live_…` → the Vidbyte key relayed as a provider key (EC-13, M-14).
- `AUTO` with a provider key → no relay header → Vidbyte pays (AC-2, INV-2); or the key also lands in the body or another header (INV-2, FR-7).
- `AUTO` with no provider key → a fourth, empty header, or a changed envelope → base commit's managed call changes (AC-3, INV-16).
- `AUTO` with no Vidbyte key → silently vendor-direct with the provider key (the old BYOK path) instead of M-9 (AC-4, INV-7).
- `DIRECT` reads `VIDBYTE_API_KEY` → a malformed value breaks a pure-BYOK caller (AC-5, INV-6).
- `VIDBYTE_MANAGED` reads `OPENAI_API_KEY` → relays a key the caller asked not to use (AC-13, INV-5).
- An unserved provider or a custom endpoint in a gateway mode → refused only at `validate()` or not at all → the Vidbyte bearer follows a caller URL (AC-12, INV-8, D-23).
- Streaming in `AUTO` → bypasses the gateway (AC-6, INV-11).
- A relayed provider 401/402/403 → the message blames the Vidbyte key or wallet, or is re-sent (AC-14, table G).
- A relayed key with an inner space, or longer than 512 characters → a gateway 422 blaming the body, or the key inside an HTTP library error (AC-40, M-21).
- A runner re-reads the environment per call → keys change mid-run (INV-12).
- `repr()` of a record, a config, or a settings object → shows a key (AC-20, INV-4).
- `api_keys=['xai-a…', 'sk-ant-b…']` in free text → the harness redactor removes only the first key (AC-22, EC-49).
- Old `api_key=` keyword → silently ignored or accepted → a key used for the wrong provider (AC-24).
- A hand-built `ProviderKeys` that files a Vidbyte key under a provider → `vb_live_…` sent to that vendor in `DIRECT` (INV-13, review R-2).
- An aggregate with no `aggregator` (the default is its own provider and model) and a list without that provider's key → every synthesis call silently goes Vidbyte-paid (INV-24, D-27, review R-3).
- `VIDBYTE_MANAGED` with no list and `OPENAI_API_KEY=vb_live_…` → the provider variable is read, and M-14 fails a mode that never uses it (INV-5, EC-13, review R-4).
- An image or audio model with `api_keys=[K_x, K_o]` → the runner takes the first key, and xAI's key goes to OpenAI's endpoint (INV-3, AC-23, review R-5).
- A gateway-mode config for an unserved provider or with an endpoint, plus another provider's key → M-18 ("add your mistral key") instead of M-12 or M-13 naming `DIRECT`, a remedy that cannot work (INV-8, D-15, review R-6).
- A `VIDBYTE_MANAGED` call answered 402 → the message says to add a key to `api_keys`, which that mode ignores (INV-5, D-15, review R-17).
- `AgentRoleSettings(vidbyte_api_key=" vb_live_… ")` → refused as malformed although `Agent` accepts and strips the same value (INV-26, review R-14).
- A dump of a relay request's headers → `X-Vidbyte-Provider-Key` is not a credential name, so the provider key survives redaction while the bearer is scrubbed (NFR-1, INV-22, review R-15).

## Contract

- **Matching (table F, table A, INV-10, INV-25).** A key whose prefix proves a provider goes to that provider. A Vidbyte-prefixed entry is the Vidbyte key. Any other key binds to the one configured provider that can take it, or, as the list's only unproven key, to the one keyless primary that can take it. Anything else is refused with a `ConfigurationError` that names indexes, lengths, and providers but never key characters.
- **Primaries (INV-24, D-27).** A list that holds any provider key must hold one for every primary: the agent's own provider, or every spec-built proposer's and the aggregator's provider.
- **One record (D-13, INV-15).** Every child gets the root's `ProviderKeys` and `model_mode` unchanged. A checkpoint stores `model_mode` and `key_providers` (names only), never a key (INV-14).
- **Table R (`credentials()`).** `DIRECT`: provider key or M-8. `VIDBYTE_MANAGED`: Vidbyte key or M-9/M-10; no provider key. `AUTO`: Vidbyte key (or M-9) plus the provider key from the record, then the environment, or none.
- **Wire (INV-2, INV-16, FR-7).** A relay call sends the base commit's three headers plus `X-Vidbyte-Provider-Key`, and nothing else changes. A paid call sends exactly the base commit's request.
- **Failures (table G, INV-17).** Every gateway failure is `ProviderRequestError(provider="vidbyte")` with the prefix "Vidbyte gateway {provider} request failed:" and no body text, excerpt, or chained exception.

## Actors / Callers

SDK users building `TextModelConfig`, `Agent`/`BaseAgent`, `AggregateAgent`, `JevAgentSettings`, `JevRunBriefSettings`, `AgentRoleSettings`; `Session.resume`/`continue_`/`fork_from`/`fork` and fork recovery; `StreamingTextModelRunner` callers; `ModalityDetector.create_runner` callers.

## Inputs and Preconditions

`api_keys` (list, tuple, `ProviderKeys`, or `None`), `vidbyte_api_key`, `mode`/`model_mode`, the process environment, and the inner HTTP transport. Every test builds its agents and runners under `patch.dict(os.environ, …, clear=True)` (or `RecordingEnviron`) and a scripted transport, so no real key or network is touched.

## Observable Outcomes

Recorded transport calls (URL, headers, body, timeout, attempt count); the `ProviderKeys` record (`key_for`, `providers`, `matched_primary`, `matched_others`); `TextCredentials`; raised errors (type, message, `details`); `repr()` output; captured log records; exported checkpoint state.

## State Transitions

Matching happens once, when the root is built. A gateway runner pins its credentials when it is built (INV-12). A restored agent re-matches its list against the stored `key_providers` (D-30); a checkpoint without the entry restores `AUTO` and matches as a root (EC-53).

## Invariants

- A provider key is sent only with a call to the provider it was matched to (INV-3).
- A Vidbyte key reaches only the gateway, as the bearer (INV-13).
- No key appears in any repr, log, error, or checkpoint (INV-4, INV-14, INV-17).
- Matching ignores list order and the environment, and has exactly two outcomes (INV-9, INV-10).

## External Dependencies

The inner HTTP transport (the only fake besides the retry wait and the environment), the real adapters in `vidbyte/providers/`, `vidbyte/lib/http/vidbyte_gateway.py`, and `README.md` (AC-27).

## Historical Regressions

None yet. Add one line per fixed bug with the test that protects it.

## Test Suite Map

- `provider_keys_fixtures.py`: runtime-built fake keys per table F/A, per-dialect `isDone` answers, `ProviderRouter`, `RecordingEnviron`, `key_view`, `flat`.
- `test_provider_keys_acceptance.py`: the §4 snippet run as written (AC-1); `AUTO` relay vs paid (AC-2, AC-3); missing Vidbyte key (AC-4); `DIRECT` byte identity (AC-5); Vidbyte entries and variables (AC-11); unserved providers and endpoints (AC-12, AC-36); `VIDBYTE_MANAGED` (AC-13); README facts (AC-27).
- `test_provider_keys_matching.py`: list shapes (AC-8), table F and A (AC-29), unique assignment (AC-10, AC-42), primaries (INV-24), Vidbyte entries (AC-35), record pass-through (AC-39), settings roots.
- `test_provider_keys_property.py`: seeded random and exhaustive permutation checks of INV-9 and INV-10 (no `hypothesis`).
- `test_provider_keys_agents.py`: agent relay and fallback (AC-7, AC-16, AC-17, AC-31, AC-38), root refusals (AC-9, AC-32, AC-33, AC-37), children (AC-18, AC-34), model mode (AC-25, AC-26), non-text runners (AC-23).
- `test_provider_keys_sessions.py`: restore paths (AC-19, AC-41), exported state (INV-14), old checkpoints (EC-53).
- `test_provider_keys_modes.py`: `TextCredentials`, table R, M-8/M-9/M-14, gateway shape (INV-8), streaming (AC-6), pinning (INV-12), unsendable keys (AC-40).
- `test_provider_keys_wire_contract.py`: relay header, body, cap and floor, re-sends, and concurrency (INV-2, INV-16, INV-20, INV-21).
- `test_provider_keys_failures.py`: table G per status in both modes (AC-15), relayed provider refusals (AC-14).
- `test_provider_keys_security.py`: reprs (AC-20), leak scenarios (AC-21), credential guards and the harness redactor (AC-22).
- `test_provider_keys_contract.py`: names, constants, exports, field orders, signatures, the old keyword (AC-24), and the manual scripts (AC-30).

Run `python -m pytest tests/features/sdk_provider_keys` from a worktree, with `PYTHONPATH` set to the worktree and `DEEPSEEK_API_KEY` unset.

## Omitted Testing Strategies

- `hypothesis`: not a dependency (NFR-6). `test_provider_keys_property.py` uses seeded random lists plus every permutation of small lists instead.
- Live calls and the live E2E with real keys (NG-15): tests never touch the network.
- The backend relay, fee-only billing, and the Sentry scrub (NG-1): the companion run `byok-fee-relay` owns them.
- `credential_mismatch` and the open questions answered "no" (Q-3 to Q-6), and every rejected feature (NG-1 to NG-19): nothing to test.
- AC-28 (lint and the full gate): enforced by `python lint/run.py` and `scripts/run_ci.py`, not duplicated in pytest.
