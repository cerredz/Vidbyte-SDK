# lint/core/ -- lint engine infrastructure

## Responsibility

This folder owns source discovery, analyzer subprocess boundaries, the rule
interface, debt comparison, execution isolation, and reporting. It contains no
SDK architecture policy beyond analyzer transport and baseline integrity.

## Non-Goals

- Do not add provider, registry, tool, or documentation policy here; add a rule.
- Do not import or execute the installed SDK.
- Do not let analyzer failures become empty finding lists.
- Do not read ambient Ruff/mypy configuration.

## File Index

- `__init__.py` -- core package marker.
- `baseline.py` -- strict rule-count debt store and verdicts.
- `diagnostic.py` -- immutable finding/diagnostic contracts.
- `discovery.py` -- tracked package/repository-wide source and README catalogues.
- `mypy.py` -- cached pinned mypy subprocess adapter.
- `platform_contract.py` -- vendored platform-contract reader (fails closed), Vidbyte host classification, and route matching.
- `public_api_contract.py` -- SDK public-API contract schema, canonical rendering, and static `__all__` derivation.
- `python_index.py` -- static index of vidbyte modules, classes, functions, and imports for source tracing.
- `registry.py` -- rule interface and S001-S021 catalogue.
- `report.py` -- text/JSON result rendering.
- `ruff.py` -- cached pinned Ruff subprocess adapter.
- `runner.py` -- fail-closed execution and baseline comparison.
- `string_flow.py` -- evaluates expressions to possible string values, receiver classes, and header credentials.
- `url_flow.py` -- static tracer for request URLs, methods, and headers, and Vidbyte API URL literals.

## Change Log

- 2026-08-23: Created for the first SDK agent-facing lint suite.
