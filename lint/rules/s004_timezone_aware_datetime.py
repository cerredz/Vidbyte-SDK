"""FILE: lint/rules/s004_timezone_aware_datetime.py

PURPOSE: Defines S004 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps timezone aware datetime findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S004.
"""

from lint.core.ruff import RuffBackedRule


class TimezoneAwareDatetimeRule(RuffBackedRule):
    """Enforces the timezone-aware-datetime policy."""

    id = "S004"
    name = "timezone-aware-datetime"
    summary = (
        "This rule keeps SDK timestamps anchored to an explicit timezone at construction and conversion boundaries. "
        "It covers trace events, retries, evaluations, billing observations, persisted records, and provider payloads that may cross machines or regions. "
        "A finding identifies a timestamp whose meaning depends on the process's local timezone or on an implicit parser default. "
        "Making the zone explicit keeps chronological comparisons and serialized history stable for both humans and agents."
    )
    prefixes = ("DTZ",)
    impact = (
        "A naive timestamp can represent different instants when the same code runs on developer machines, CI workers, provider hosts, or customer systems. "
        "That ambiguity can reorder retries, misstate evaluation duration, or associate usage with the wrong billing window. "
        "Once a naive value is persisted or emitted in a trace, the lost offset usually cannot be reconstructed from the value alone. "
        "The defect therefore threatens reproducibility, operational diagnosis, and any decision that compares events across boundaries."
    )
    repair = (
        "Choose UTC as the canonical internal representation unless the surrounding contract explicitly requires a preserved user timezone. "
        "Construct new values with an aware UTC clock, parse external values with an explicit zone policy, and convert rather than strip offsets. "
        "Keep the serialized format and field type compatible with existing callers while rejecting or normalizing ambiguous input at the boundary. "
        "Run the focused rule plus timestamp, trace, and persistence checks across a non-UTC environment when the change affects those paths."
    )
    examples = (
        "datetime.now(timezone.utc) for a new SDK event timestamp",
        "An explicit offset retained while parsing a provider or persisted timestamp",
    )
    will_not_work = (
        "Calling replace(tzinfo=None) or stripping an offset to make comparisons type-compatible.",
        "Relying on the host timezone or an undocumented parser default to define event meaning.",
    )


RULE = TimezoneAwareDatetimeRule()
