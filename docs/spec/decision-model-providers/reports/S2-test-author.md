# S2 test author report: decision-model-providers

Spec: `docs/spec/decision-model-providers/spec.md` r3 (approved) · Branch `feat/decision-model-providers` · Base `278448b05155cb25b0a7fb667609256a496404b2` · HEAD after this stage `c07abf492702b98819f4941a206fb45e37bf05e7` · Date 2026-10-10

## Inventory

Pack `tests/features/decision_model_providers/` (new, committed in `f713962d`):

| File | Tests | Spec IDs |
|---|---|---|
| `FEATURE.md`, `README.md` | — | pack doctrine (contract, outcomes, suite map, omitted strategies) |
| `decision_fixtures.py` | — | `ScriptedTransport`, section 4 request, System One / OpenAI response builders, `HOST_ROWS` (section 9.1 table), `decision_config()` / `scripted_runner()`; placeholder key `decision-test-key` |
| `test_decision_contract.py` | 14 | INV-1, INV-2, INV-20, FR-1, FR-2, FR-4, FR-10, FR-12, FR-13, section 9.1, D-4, D-5, D-16, D-18 |
| `test_decision_config.py` | 11 | INV-1 to INV-5, INV-21, AC-7, AC-8, AC-9, AC-14, EC-1 to EC-5, EC-24, FR-3, FR-14, section 9.4 |
| `test_decision_systemone_wire.py` | 10 | INV-5, INV-6, INV-8, INV-9, INV-14, INV-15, INV-23, INV-27, AC-2, AC-3, AC-4, AC-7, AC-11, AC-18, EC-6, EC-9, EC-19, EC-27, NFR-4 |
| `test_decision_openai_wire.py` | 11 | INV-7, INV-8, INV-9, INV-14, INV-15, INV-27, AC-5, AC-6, AC-11, AC-17, EC-7, EC-8, EC-10, EC-11, D-8, D-11 |
| `test_decision_failures.py` | 9 | INV-5, INV-13, INV-16, INV-17, INV-28, AC-10, AC-13, AC-19, EC-12, EC-13, EC-14, EC-20, EC-23, EC-25, EC-28, FR-6, FR-11, NFR-5 |
| `test_decision_usage_metering.py` | 8 | INV-10, INV-11, INV-12, INV-18, INV-19, AC-4, AC-6, AC-12, EC-17, EC-18, EC-21, FR-5, FR-16 |
| `test_decision_acceptance.py` | 2 | AC-1, section 4 prose |
| `test_decision_regression_typesafe.py` | 7 | INV-13, INV-21 to INV-25, AC-14, AC-15, EC-22, D-14, NFR-7 |

Total: 72 tests, all `unittest` classes (`IsolatedAsyncioTestCase` for transport-driven tests), bracket-tag comments, A001 7-field headers on every `.py` file. `docs/spec/decision-model-providers/test-plan.md` holds the coverage map (one row per test), the deliberately-not-written table, the red run, and implementer notes. Spec section 6.2 Proof column filled for AC-1..AC-19 (commit `c07abf49`; the diff is exactly 19 changed table rows, nothing else in `spec.md`).

## Pruning

Not written (full reasons in test-plan.md): `vidbyte.__all__` snapshot (lint C016 owns it); "gpt-6-luna / typesafe/jev-1.13 not catalogued" (green today, vacuous); duplicate re-proofs of `TypeSafeProviderContractTests` (the existing suite pins them, AC-14 requires it unmodified — the regression file instead binds each TypeSafe expectation to a new symbol or a twin host so it is red today); Cloudflare truncation (EC-16, no observable behaviour); managed gateway for new providers (Q-1); `__all__` adjacency; property-based fuzzing (no `hypothesis`); `KeyboardInterrupt` passthrough; live vendor calls.

Two assertions were relaxed during review to avoid pinning an unspecified detail: the OpenAI normalizer's mapping order (tests use `set`/`sorted`); System One order stays request order as today.

## Red run

Bootstrap: `python -m pip install -e ".[dev]"` → `Successfully installed vidbyte-sdk-0.2.0` (worktree import confirmed).

```
python -m pytest tests/features/decision_model_providers/test_decision_acceptance.py -q          → 2 failed in 0.78s
python -m pytest tests/features/decision_model_providers/test_decision_config.py -q              → 11 failed in 0.87s
python -m pytest tests/features/decision_model_providers/test_decision_contract.py -q            → 14 failed in 0.80s
python -m pytest tests/features/decision_model_providers/test_decision_failures.py -q            → 9 failed in 0.92s
python -m pytest tests/features/decision_model_providers/test_decision_openai_wire.py -q         → 11 failed in 0.92s
python -m pytest tests/features/decision_model_providers/test_decision_regression_typesafe.py -q → 7 failed in 0.83s
python -m pytest tests/features/decision_model_providers/test_decision_systemone_wire.py -q      → 10 failed in 0.99s
python -m pytest tests/features/decision_model_providers/test_decision_usage_metering.py -q      → 8 failed in 0.91s
python -m pytest tests/features/decision_model_providers -q                                     → 72 failed in 1.92s
```

Reasons (tally from `--tb=line`): 31 × `AttributeError: PERPLEXITY|LIQUID|BASETEN|CLOUDFLARE`; 15 × `UnsupportedProviderError: DecisionModelRunner supports: typesafe.`; 4 × `'DecisionModelConfig' object has no attribute 'resolved_model'`; 4 × `ProviderModelRegistry` has no `DECISION_DEFAULT_MODELS` / `decision_default_model`; 7 × `ModuleNotFoundError` (`vidbyte.providers.decisions` ×3, `systemone` ×2, `openai_decisions` ×2); 4 × `ImportError` (`SystemOneHost` ×2, `DecisionAuthScheme`, `OpenAIDecisionsWireQuestion`); 1 × missing `PERPLEXITY_DECISIONS_PATH`; 1 × `ConfigurationError: model must be non-empty.` (`model=None`); 1 × `ConfigurationError: Unsupported model provider: 'perplexity'` (`JevAgentSettings`); 4 × assertion on today's values (`supports: typesafe.` message, `None != 'decision'`, `'2026-07-30' != '2026-10-10'`, `SystemOneProvider` not in `vidbyte.providers.__all__`). None of the 72 fails inside a fixture or for a test bug; collection is clean (no module-level import of a new symbol).

Existing area suite, unmodified (`python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q`): `395 passed in 2.25s` (same count as before the pack).

Lint (`git add -A` then `python lint/run.py`), final lines:

```
S051 IMPROVED 259 -> 258. Lower it with: python lint/run.py --rule S051 --update-baseline
SDK-LINT: PASS
```

Exit code 0. No rule regressed. The run also printed `IMPROVED` lines for A002 (703→681), S001 (59→57), S009 (350→340), S010 (5→0), S017 (79→78), S024 (25→21), S025 (263→261); not ratcheted (orchestrator rule: report, never edit `lint/baseline.json`). The two lint runs this stage reported different IMPROVED sets (the first showed only S024/S025/S051), so the IMPROVED figures look run-dependent; worth a glance by whoever owns the lint ratchet, but nothing in this stage touched `lint/` or `vidbyte/`.

## Fixtures and helpers added

Only inside the new pack: `decision_fixtures.py` (copied `ScriptedTransport` from `tests/test_jev_agent.py` rather than importing it, so the pack never imports a sibling test module). No existing test file, fixture, or assertion was modified; `git show --stat f713962d` lists only the 11 pack files plus `test-plan.md`.

## Spec defects and hard-to-test items

- Not a defect, but an implementer trap: spec row 15 does not say explicitly that `OpenAIDecisionsAnswers` wraps `ConfigurationError` from `JevProbability.require` / `JevAnswer` into `self.error(...)`. INV-8/EC-9 require `ProviderResponseError` for a malformed answer, and today's `_TypeSafeAnswerNormalizer._answer` does the wrap; the test `test_missing_extra_duplicate_or_mistyped_answers_raise_with_usage` ("bad probability" case) encodes INV-8. Flagged in test-plan.md notes.
- Row 12's `DecisionFailures.unexpected(..., message=None)` is described only as "the caller passes a pre-redacted message"; the test reads it as "replaces `str(exc)` in the template". If the implementer reads it as a wholesale message override, one assertion in `test_decision_failures_mapper_is_shared_by_every_adapter` will need the spec author's ruling.
- AC-16 (lint) is a command, not a test; its Proof cell says so and records this stage's `SDK-LINT: PASS` baseline.
- INV-26 (`vidbyte.__all__` unchanged) is left to lint C016 (listed under deliberately not written).
- AC-12's "ledger's unaccounted count is unchanged" for unpriced vendors is asserted as `unaccounted_call_count == 0` after one call (the only call in that tracker).
- The spec's section 9.1 answer-kind matrix is the source of the literal wire bodies; `provider-research.md` section 3.1 was used only to confirm the OpenAI `answers[].name` / `probabilities[{value, probability}]` / `{value, label, probability}` shapes and Perplexity's `usage{input_tokens, output_tokens}`.

## Corrections to the briefing

- The briefing said lint A001 scans only `vidbyte/**/*.py`. `lint/rules/a001_agent_readable_file_headers.py` uses `catalog.all_python_files()`, which covers every tracked `.py` including tests (baseline 643 files), so every new test module and `decision_fixtures.py` carries the 7-field header. S062 (no implicit string concatenation) and C018 also scan tests. Lint passed with the pack staged.
- pytest collects the pack under prepend import mode without `__init__.py`; the fixture module is imported as `tests.features.decision_model_providers.decision_fixtures` (namespace chain under `tests/__init__.py`), verified by the runs above. Basenames `test_decision_*.py` are unique across `tests/`, so no basename collision with `tests/features/sdk_loop_settings/test_contract.py`.

## Open items for S3

- Implementer notes in `test-plan.md` list the seams the tests pin that the spec states only implicitly (ConfigurationError wrapping in the OpenAI normalizer, `message=` semantics of `DecisionFailures.unexpected`, `response.raw` staying the parsed mapping, TypeSafe row present in `SystemOneProvider.HOSTS`, `_TypeSafeCallBuilder.decision` returning `DecisionHttpCall` with managed headers intact).
- This report is uncommitted by instruction.
