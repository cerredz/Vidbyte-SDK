# Vidbyte-managed text calls

## Folder Description / Intent

This folder holds the feature tests for Vidbyte-managed text calls. With only `VIDBYTE_API_KEY` set, or with `mode=TextModelMode.VIDBYTE_MANAGED`, a `TextModelRunner` call goes to one Vidbyte gateway route instead of the vendor, while BYOK calls stay byte-identical. The tests are offline: the only fakes are the inner HTTP transport and the retry wait. The behavior itself lives in `vidbyte/lib/` (`dataclasses/model_configs.py`, `registries/models.py`, `http/vidbyte_gateway.py`, `runners/text.py`, `runners/streaming_text.py`), not here. The contract comes from `docs/spec/managed-generative-models/spec.md`.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` defines the contract, the invariants, the known failure modes, and the strategies left out on purpose.
- `managed_text_fixtures.py` provides the scripted inner transport, provider-shaped answers, gateway and relayed error bodies that carry a canary and a key-shaped string, and the retry-wait recorder.
- `test_managed_text_acceptance.py` runs the README snippet, all six managed providers end to end, the per-provider BYOK rule, the agent path, and the README fee disclosure.
- `test_managed_text_selection.py` covers key selection, explicit managed mode, the refusals managed state owes before any request, runner pinning, other modalities, the config field contract, and key hygiene.
- `test_managed_text_wire_contract.py` covers output caps per dialect, `extra_body` passthrough, the 630 s timeout floor, and the allowed body keys per dialect.
- `test_managed_text_failures.py` covers credential-safe errors, remedy facts, edge failures, cancellation, same-key retries, one key per call, and concurrent calls.

## Logs

- 2026-10-10 - Pack added red, ahead of the implementation, from spec r4 (S2 test author).
