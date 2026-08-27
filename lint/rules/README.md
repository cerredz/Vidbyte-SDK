# lint/rules/ -- independently baselined SDK policies

## Responsibility

Each file in this folder owns one stable rule ID, one conceptual invariant, its
scope/counterexamples, and its repair diagnostic. Analyzer-backed rules select
cached external findings; semantic rules inspect the shared source catalogue.

## Non-Goals

- Do not combine unrelated policies to reduce file count.
- Do not walk/read source again when `SourceCatalog` already provides it.
- Do not add inline suppression syntax as a repair strategy.
- Do not mutate SDK source or initialize baselines without inspecting findings.

## File Index

- `__init__.py` -- rule package marker.
- `s001_python_correctness_foundation.py` -- Pyflakes/syntax correctness.
- `s002_exception_cause_chaining.py` -- explicit translated causes.
- `s003_strict_zip.py` -- explicit zip length behavior.
- `s004_timezone_aware_datetime.py` -- aware timestamp construction.
- `s005_immutable_class_defaults.py` -- shared mutable class state.
- `s006_async_task_ownership.py` -- retained async task lifetimes.
- `s007_public_function_annotations.py` -- typed public seams.
- `s008_bounded_function_complexity.py` -- branch/statement complexity.
- `s009_staged_mypy_contracts.py` -- package type-contract ratchet.
- `s010_transport_parity.py` -- async/sync transport compatibility.
- `s011_raw_http_client_ownership.py` -- transport adapter ownership.
- `s012_explicit_outbound_timeout.py` -- explicit outbound timeouts.
- `s013_bounded_untrusted_responses.py` -- ingestion response ceilings.
- `s014_provider_model_registry_parity.py` -- declarative registry parity.
- `s015_public_export_integrity.py` -- package export bindings.
- `s016_typed_boundary_errors.py` -- typed public failures.
- `s017_no_raw_exception_disclosure.py` -- stable redacted public errors.
- `s018_priced_operation_attempts.py` -- retry-aware operation usage.
- `s019_cancellation_propagation.py` -- preserved cancellation.
- `s020_readme_file_index_parity.py` -- opt-in documentation parity.
- `s021_class_bound_registry_helpers.py` -- class-owned registry behavior.
- `s024_maximum_control_flow_nesting.py` -- maximum semantic control-flow depth.
- `a001_agent_readable_file_headers.py` -- structured SDK source headers.
- `a002_intent_comments.py` -- intent markers for load-bearing policy functions.
- `a003_context_rich_error_packets.py` -- stable diagnostic fields on errors.
- `a005_typed_dependency_seams.py` -- concrete injected dependency interfaces.
- `a006_directed_dependency_graph.py` -- concrete import cycles and layer edges.
- `a007_operational_constants.py` -- named operational policy values.
- `a008_library_stdout_boundary.py` -- CLI-only builtin stdout calls.

## Change Log

- 2026-08-23: Created with S001-S021.
