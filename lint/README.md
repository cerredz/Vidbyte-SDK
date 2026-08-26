# Vidbyte SDK Lint Suite

A developer-only, agent-facing static analysis tool. It reads tracked
`vidbyte/**/*.py` source and runs a pinned Ruff analysis against it; it never
imports or executes `vidbyte`, and it never contacts a provider or network
service.

## Non-Goals

- No mypy integration, formatter, or autofix. See
  `docs/design/sdk-lint-python-correctness.md` for the rules explicitly
  deferred to future work (transport parity, registry parity, export
  integrity, typed boundary errors, and others).
- No ban on broad `except Exception` (Ruff's `BLE001`). The SDK's
  usage-tracking code deliberately catches broad exceptions so a metering
  bug can never crash a host agent run; this suite does not fight that.
- Never raise a number in `lint/baseline.json` by hand to make a run pass.
  The only sanctioned way to change a count is `--update-baseline` after
  manually reviewing the new findings it represents.

## Commands

```bash
python lint/run.py                    # run every registered rule
python lint/run.py --rule S001        # run one rule
python lint/run.py --rule S001 --all  # every finding for one rule, not just the first 20
python lint/run.py --format json      # machine-readable report
python lint/run.py --update-baseline  # recompute and write lint/baseline.json
```

Exit code `0` means every selected rule is `clean`, `ratcheted` (holding
steady at existing debt), or `improved`. Exit code `1` means a rule
`regressed`, a rule's `find()` raised (`errored`), or `lint/baseline.json`
has a stale or missing entry for a registered rule.

## Rule Catalogue

`S`-prefixed rules filter Ruff's own output (`ruff_selectors` is non-empty).
`C`-prefixed ("contract") rules parse `vidbyte/**/*.py` themselves and
enforce an SDK-specific domain convention that no stock analyzer selector
covers; `ruff_selectors` is empty for these.

| ID | Name | Kind | File |
|----|------|------|------|
| S001 | Python correctness foundation (`F`, `E4`, `E7`, `E9`) | Ruff-backed | `lint/rules/s001_python_correctness_foundation.py` |
| C001 | Settings-class `ConfigurationError` placement | AST | `lint/rules/c001_settings_class_configuration_error_placement.py` |
| C002 | Duplicate inline `isinstance(x, bool)` validation | AST | `lint/rules/c002_duplicate_inline_bool_guard_validation.py` |
| C003 | No dynamic import from non-literal data | AST | `lint/rules/c003_no_dynamic_import_from_data.py` |
| C004 | `OPERATION_PRICING` rate implausibility floor | AST | `lint/rules/c004_operation_pricing_rate_floor.py` |
| C005 | Cost arithmetic confined to two known sites | AST | `lint/rules/c005_cost_arithmetic_site_parity.py` |

See `docs/design/sdk-lint-contract-rules.md` for what each `C`-rule found
when it was verified against the live tree, and why each one is scoped the
way it is.

## Adding a Rule

1. Create `lint/rules/sNNN_<name>.py` (a rule with non-empty
   `ruff_selectors`, filtering the shared Ruff output) or
   `lint/rules/cNNN_<name>.py` (a pure-AST rule using
   `lint/core/parsing.PythonSourceParser`), exposing `rule_id`,
   `ruff_selectors`, `diagnostic()`, and `find(files, ruff_findings)` (see
   `lint/core/rule.py`'s `LintRule` protocol). `find()` must return
   fully-formed `Finding` objects with `rule_id` and `code` already set.
2. Register the class in `_RULES` in `lint/core/registry.py`.
3. Run `python lint/run.py --rule <id>` and manually review the findings for
   scope before trusting them.
4. Run `python lint/run.py --update-baseline` once you are satisfied, then
   commit the updated `lint/baseline.json` alongside the new rule.
