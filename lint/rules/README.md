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
- `c001_settings_class_configuration_error_placement.py` -- settings validation ownership.
- `c002_duplicate_inline_bool_guard_validation.py` -- duplicate meaningful bool guards.
- `c003_no_dynamic_import_from_data.py` -- fixed import targets.
- `c004_operation_pricing_rate_floor.py` -- operation pricebook magnitude floor.
- `c005_cost_arithmetic_site_parity.py` -- reviewed cost-arithmetic locations.
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
- `s025_model_facing_description_depth.py` -- ToolSpec/ToolParameter description depth.
- `s026_pairwise_zip.py` -- explicit zip length behavior.
- `s027_mutable_dataclass_default.py` -- per-instance dataclass defaults.
- `s028_dataclass_default_call.py` -- dataclass default evaluation timing.
- `s029_unnecessary_first_element_allocation.py` -- lazy first-item selection.
- `s030_quadratic_list_summation.py` -- linear list aggregation.
- `s031_assignment_in_assert.py` -- always-active validation assignments.
- `s032_unnecessary_key_check.py` -- direct mapping missing-key behavior.
- `s033_mutable_dict_fromkeys.py` -- independent mutable mapping values.
- `s034_ambiguous_pytest_raises_match.py` -- precise pytest exception patterns.
- `s035_unused_noqa.py` -- active-only noqa suppressions.
- `s036_invalid_pyproject.py` -- valid project metadata.
- `s037_blanket_type_ignore.py` -- diagnostic-specific type ignores.
- `s038_blanket_noqa.py` -- diagnostic-specific noqa suppressions.
- `s039_banned_api_policy.py` -- repository-owned banned imports.
- `s040_relative_imports.py` -- absolute package imports.
- `s041_unspecified_encoding.py` -- explicit text encodings.
- `s042_raise_vanilla_class.py` -- typed runtime exceptions.
- `s043_verbose_log_message.py` -- concise structured exception logs.
- `s044_logging_f_string.py` -- parameterized logging.
- `s045_async_function_with_timeout.py` -- connected async deadlines.
- `s046_blocking_http_call_in_async_function.py` -- non-blocking async HTTP.
- `s047_blocking_open_in_async_function.py` -- non-blocking async file access.
- `s048_blocking_sleep_in_async_function.py` -- cooperative async delays.
- `s049_unsafe_yaml_load.py` -- safe YAML construction.
- `s050_insecure_hash.py` -- security-appropriate hashing.
- `s051_modernized_import_and_syntax_hygiene.py` -- sorted imports, non-deprecated typing syntax.
- `s052_async_blocking_io.py` -- blocking calls inside async functions not already owned by S045-S048.
- `s053_defensive_python_bugbear.py` -- warning stacklevel, test exceptions, closures, ContextVars.
- `s054_bandit_security_subset.py` -- unsafe deserialization, TLS bypass, credentials (weak-hash/unsafe-YAML in S049/S050).
- `s055_no_shell_subprocess.py` -- shell-interpreting subprocess execution.
- `s056_retryable_idempotent_methods.py` -- idempotency guard on retrying HTTP transports.
- `s057_no_model_construct_without_review.py` -- validation-skipping Pydantic construction.
- `s058_forbid_unknown_fields_at_boundary.py` -- explicit extra-field policy at public seams.
- `s059_explicit_serialization_mode.py` -- explicit model_dump() wire/Python mode.
- `s060_typed_public_seam_mappings.py` -- named mapping shapes at public seams.
- `s061_bounded_safe_path.py` -- resolved, contained file/archive I/O paths.
- `a001_agent_readable_file_headers.py` -- structured SDK source headers.
- `a002_intent_comments.py` -- intent markers for load-bearing policy functions.
- `a003_context_rich_error_packets.py` -- stable diagnostic fields on errors.
- `a005_typed_dependency_seams.py` -- concrete injected dependency interfaces.
- `a006_directed_dependency_graph.py` -- concrete import cycles and layer edges.
- `a007_operational_constants.py` -- named operational policy values.
- `a008_library_stdout_boundary.py` -- CLI-only builtin stdout calls.

## Change Log

- 2026-08-23: Created with S001-S021.
- 2026-08-26: Added article-derived S024 and A001-A003/A005-A008 policies.
- 2026-08-27: Added S025 model-facing tool/parameter description depth policy.
- 2026-08-28: Added the sequential S026-S050 analyzer-backed policy catalogue.
- 2026-08-28: Added C001-C005 SDK domain-contract policies.
- 2026-08-28: Added catalog-expansion S051-S061 policies (renumbered from an initial S025-S035
  draft after S025-S050 landed on main concurrently; S052/S054 dropped the Ruff codes S045-S050
  already own).
