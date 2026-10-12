# S2 test author report: managed-generative-models

Stage: S2 test author · Spec: `docs/spec/managed-generative-models/spec.md` r4 · Branch: `feat/managed-generative-models` · Commits: `2eb7e3e5` (tests and test plan), `6069160f` (spec Proof column)

## What was done
- I wrote 32 failing tests in a new feature pack, `tests/features/sdk_managed_text/`:
  - 4 test modules;
  - 1 shared fixture module;
  - `FEATURE.md` and `README.md`.
- They bind only to names the spec commits to (§4, §8.5, §9.2, §12.3).
- All 32 fail at base for the intended reason: a missing feature symbol, or the missing managed behavior.
- The 69 existing area tests pass, and the full suite still collects and passes apart from the new tests.
- I filled the §6.2 Proof column (only that column; `git diff --word-diff` shows additions only) and wrote `test-plan.md`.
- I added no production code, stubs or placeholders. Nothing was installed. Nothing was pushed.

## Inventory (what each module covers)
| Module | Tests | Spec IDs |
|---|---|---|
| `test_managed_text_acceptance.py` | 5 | AC-1, AC-2, AC-3, AC-18, AC-23, AC-24; EC-1, EC-30; INV-1..3, INV-12, INV-17 |
| `test_managed_text_selection.py` | 13 | AC-4..AC-7, AC-13..AC-16, AC-21, AC-22; INV-4, INV-5, INV-7, INV-8, INV-13, INV-14, INV-18..INV-22; EC-2..EC-7, EC-16..EC-19, EC-21, EC-28 |
| `test_managed_text_wire_contract.py` | 4 | AC-8, AC-9, AC-26; INV-2, INV-9, INV-10; EC-8, EC-20 |
| `test_managed_text_failures.py` | 10 | AC-10..AC-12, AC-20, AC-25, AC-27; INV-11, INV-16; EC-9..EC-15, EC-24, EC-25, EC-32..EC-34, EC-36..EC-38 |

AC-17 (the `python scripts/run_ci.py` gate) and AC-19 (a diff review) are proved outside pytest. Their Proof cells say so.

**Levels:**
- acceptance: 2;
- e2e (agent): 1;
- integration: 5;
- contract: 9;
- security: 10;
- concurrency: 2;
- unit: 3.

There are no property-based tests, because `hypothesis` is unavailable and NFR-6 forbids new dependencies. Small exhaustive tables replace them.

**Techniques that keep the tests from passing vacuously:**
- **BYOK oracle.** The managed body must equal the body the same adapter builds in BYOK state with the pinned config (AC-2, AC-26).
- **Base-recorded goldens.** The BYOK requests in AC-3 and the Decision outcomes in AC-14 were recorded at base.
- **Pairing.** Each "must not regress" half, which passes at base, sits in the same test as a discriminating managed half that fails at base:
  - AC-3, AC-6 and AC-13 pair it with the BYOK contrast;
  - AC-22 and INV-21 pair it with `is_vidbyte_managed()`;
  - AC-14 pairs it with `resolve_vidbyte_api_key`.
- **Canary bodies.** Every scripted error body carries `BODY_CANARY` and a key-shaped `LEAKED_KEY`. Each error is checked through `str`, `details` and the formatted traceback.
- **Concurrency overlap proof.** In EC-24, the first four POSTs must carry four different keys.

## Pruning (candidates considered and dropped)
All entries in the test plan's "Tests deliberately NOT written" table, plus three tests dropped while writing:
1. **INV-12 structured-output parse with every field set** (wire module). It duplicated the AC-2 assertions on text and usage.
2. **"A 201 success is never retried."** It depended on whether the adapter accepts non-200 2xx statuses, which is not the feature's behavior. The single-POST success case is already pinned by AC-1 and AC-2.
3. **A direct unit test of `ProviderModelRegistry.find_vidbyte_api_key`.** Its whole contract shows through the INV-4 fall-through table, where routing and the bearer are observed. A second table would duplicate it, and the interface is internal enough that S3 may reasonably refine it.

## Exact red output
Each command ran from the worktree with `PYTHONPATH=$(pwd)`. The import check printed `...\worktrees\vidbyte-sdk-managed-generative-models\vidbyte\__init__.py`.

`PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider --tb=line` (failure reasons, one per test, abbreviated paths):
```
models.py:161: ConfigurationError: Missing API key for provider openai. Pass api_key or set OPENAI_API_KEY.   [A AC-2]
test_managed_text_acceptance.py:133: AttributeError: 'TextModelConfig' object has no attribute 'is_vidbyte_managed'   [A AC-3]
test_managed_text_acceptance.py:147: ImportError: cannot import name 'VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS' from 'vidbyte.lib.constants.jev'   [A AC-18]
test_managed_text_acceptance.py:56: ImportError: cannot import name 'TextModelMode' from 'vidbyte.lib.config'   [A AC-1]
agents/base.py:818: AgentExecutionError: Agent 'greeter' failed to generate a reply.   [A AC-24, caused by the missing-key error]
pkgutil.py:715: AttributeError: module 'vidbyte.lib.http' has no attribute 'vidbyte_gateway'   [all 10 F tests, at SLEEP_TARGET]
test_managed_text_selection.py:122/143/171/190/207/279/305: ImportError: cannot import name 'TextModelMode'   [S AC-4..AC-7, AC-13, INV-20, AC-16]
AssertionError: Lists differ: ['https://api.openai.com/v1/responses'] != ['https://vidbyte-backend.onrender.com/api/v1/models/generate']   [S INV-4]
test_managed_text_selection.py:237: ImportError: cannot import name 'VIDBYTE_MANAGED_KEY_PLACEHOLDER'   [S AC-21]
test_managed_text_selection.py:262/115: AttributeError: ... no attribute 'is_vidbyte_managed'   [S AC-22, INV-21]
test_managed_text_selection.py:340: AttributeError: type object 'ProviderModelRegistry' has no attribute 'resolve_vidbyte_api_key'   [S AC-14]
AssertionError: 'vb_live_aaaa…' unexpectedly found in "TextModelConfig(provider='openai', model='gpt-5.5', api_key='vb_live_aaaa…', …)"   [S AC-15]
models.py:161: ConfigurationError: Missing API key for provider gemini|openai ...   [all 4 W tests: managed call attempted at base]
32 failed in 0.77s
```
Area command (unchanged tests):
```
PYTHONPATH=$(pwd) python -m pytest tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_text_model_runner.py tests/test_config_validation.py tests/test_model_registry.py tests/test_streaming_text_runner.py tests/test_sync_runner_default_transport.py -q
.....................................................................    [100%]
69 passed in 0.93s
```
Full suite: `PYTHONPATH=$(pwd) python -m pytest -q --tb=no` → `32 failed, 2742 passed, 1 skipped in 25.77s`. The 32 failures are exactly the new tests.

Lint, after `git add`: `PYTHONPATH=$(pwd) python lint/run.py` →
```
S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all

SDK-LINT: PASS
```
`python lint/run.py --format json --all` contains 0 findings under `tests/features/sdk_managed_text/`. That run was repeated once after a final edit to the acceptance module.

## Fixtures added
`tests/features/sdk_managed_text/managed_text_fixtures.py` imports only symbols that exist at base:
- `ScriptedGateway(*steps)`: the inner-transport stand-in.
  - It records a deep copy of each `request(**kwargs)`.
  - The last step repeats, and `BaseException` steps are raised.
  - `__call__` returns itself, so it can replace the `HttpTransport` class at `vidbyte.lib.runners.text.HttpTransport`.
- `BackoffRecorder(cancel_with=None)`: replaces `asyncio.sleep` at `SLEEP_TARGET`. It records delays and yields once through the real `sleep(0)`, so concurrent calls interleave. It can cancel.
- Factories and helpers:
  - `answer`, `edge_page`, `provider_answer` (a realistic 200 per dialect), `provider_usage`;
  - `gateway_error(status)`: `"error": true` and a message echoing `Bearer <LEAKED_KEY>` plus the canary;
  - `relayed_provider_error(provider, status)`: vendor shapes that nest an object under `"error"`;
  - `header`, `idempotency_key`.
- Constants: `VIDBYTE_KEY` and `OTHER_VIDBYTE_KEY` (the `"vb_live_" + "a"*32` prior art), `LEAKED_KEY`, `BODY_CANARY`, the literal `GATEWAY_URL`, `MANAGED_MODELS`, `UNMANAGED_TEXT_PROVIDERS`.

Defined locally in a test module:
- `FakeStreamingTransport` (selection);
- `ManagedCall`, `CredentialSafeAssertions` and `PerKeyGateway` (failures). `PerKeyGateway` answers 502 to the first attempt of each key and 200 echoing the prompt to the second.

## Spec defects and frictions found
1. **EC-26 contradicts §9.2 rows 5–6** (minor). EC-26 expects "Vidbyte returned HTTP 404" when the route is not deployed. But FastAPI's default 404 body `{"detail": "Not Found"}` is a JSON object without `"error": true`, so row 6 classifies it as a relayed provider error ("openai returned HTTP 404 through the Vidbyte gateway; provider message withheld"). Not tested. The orchestrator or S3 should pick one reading.
2. **§13 says "Tests are flat: `tests/test_<area>.py`"**, but the repository already has `tests/features/sdk_*` feature packs (FEATURE.md + README.md + tests) for this kind of cross-module behavior. I followed the pack convention. Each basename is unique repo-wide, because pytest's prepend import mode imports the test modules as top-level modules.
3. **No README heading is named for AC-18.** The test finds the section by a level-2 to level-4 heading containing "Vidbyte-managed" (or "Vidbyte managed"), the spec's own term. This is a soft binding S3 must honor; the plain word "Management" is excluded on purpose, because "## Context Management" exists.
4. **INV-11 against §9.2 "exact wording is the implementer's".** INV-11 says the message "names the provider and the status", so `assert_credential_safe` requires the managed provider's value and `str(status)` in every message (status `None` excepted). Every other message check uses only the §9.2 facts, as loose case-insensitive patterns.
5. **AC-15 names only the `vb_live_` key, while §8.5/§9.1 make `api_key` `repr=False`,** which hides every key. The test checks both a Vidbyte and an `sk-` key, which matches §8.5 and INV-17's stated exception.
6. **AC-14 and AC-17 require `python lint/run.py --rule C020` to report 2.** It reports 4 today (baseline 4), so S3's Decision delegation must remove two findings. Recorded as a gate proof, not a pytest.

## Notes for S3 (also in test-plan.md)
- The retry wait must be `asyncio.sleep` looked up as `vidbyte.lib.http.vidbyte_gateway.asyncio.sleep`, so the module must `import asyncio`. The inner call must use keyword arguments (`HttpTransport.request` is keyword-only anyway) and send `idempotency_key=` with no `retry_count`, or with 0.
- The endpoint refusal message must contain `endpoint`.
- The unmanaged-provider refusal must list all six lowercase provider values.
- The streaming refusal must contain `managed`, `TextModelRunner` and `<PROVIDER>_API_KEY`, with `details["mode"] == "vidbyte_managed"` (§12.3 row 9).
- Do not edit the fixtures to make a test pass.
