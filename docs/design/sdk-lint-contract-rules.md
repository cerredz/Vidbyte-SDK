# Design Doc: SDK Lint Suite — Domain Contract Rules (C001–C005)

**Status:** Draft
**Created:** 2026-08-28

## Overview

Add five static, SDK-specific contract checks to the lint suite already present
on `main`. The rules inspect the tracked `vidbyte/**/*.py` source catalogue and
return the existing `Finding`/`Diagnostic` contracts; they do not import or
execute the SDK. This is the conflict-resolution form of the original PR: the
current lint engine and its existing S/A rules remain authoritative, while the
older stacked #368 engine files are not reintroduced.

## Rules

| ID | Contract | Detection |
|---|---|---|
| C001 | Plain `*Settings` classes delegate `ConfigurationError` validation to a dataclass. | AST scan of settings classes and their methods. |
| C002 | Meaningful names do not repeat the same inline `isinstance(..., bool)` guard across functions. | AST grouping by identity and function. |
| C003 | Runtime data cannot choose an imported module. | AST scan of `import_module` and `__import__` calls. |
| C004 | Nonzero `OPERATION_PRICING` rates clear the established `1e-5` floor. | AST scan of the literal pricebook. |
| C005 | Token/rate multiplication stays in the reviewed agent-pricing and session-replay owners. | AST scan with two explicit path boundaries. |

## Integration with the current lint setup

Each rule subclasses `lint.core.registry.Rule`, implements `check(SourceCatalog)`
and `explain(Finding)`, and exports a `RULE` instance. The five modules are
registered in `lint/core/registry.py`; their allowances are stored alongside
the existing S and A baselines in `lint/baseline.json`. Existing source
discovery, analyzer isolation, reporting, baseline validation, and CI wiring
remain unchanged.

The baseline is measured against the current `main` tree, not copied from the
older stacked branch. C001 and C002 are initialized only after their focused
findings are inspected; C003–C005 are regression guards when the current tree
has no findings. A later source refactor may lower an allowance with the
focused `--update-baseline` command, but no allowance may be raised to hide a
regression.

## Boundaries and repair guidance

- C001 points to `vidbyte/lib/dataclasses/` and a validated `__post_init__`.
- C002 points to one shared validated dataclass for a genuinely shared field;
  generic names such as `value`, `raw`, and `data` are intentionally excluded
  to avoid unrelated matches.
- C003 points declarative configuration at fixed registries under
  `vidbyte/lib/registries/`, never at computed import paths.
- C004 mirrors the existing runtime pricebook invariant without importing test
  code or parsing free-text source comments.
- C005 keeps live pricing in `vidbyte/agents/pricing/` and persisted-session
  reconstruction in `vidbyte/sessions/usage.py`; a new third site requires a
  separately reviewed boundary.

## Verification

```bash
python lint/run.py --rule C001 --format json
python lint/run.py --rule C002 --format json
python lint/run.py --rule C003 --format json
python lint/run.py --rule C004 --format json
python lint/run.py --rule C005 --format json
python lint/run.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package
```
