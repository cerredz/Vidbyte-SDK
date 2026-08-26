"""FILE: lint/run.py

PURPOSE:
    Provides the one command developers, coding agents, and CI use to run
    the Vidbyte SDK's lint suite: `python lint/run.py`.
ROLE IN CODEBASE:
    scripts/run_ci.py's run_source() invokes this module before pytest.
    CONTRIBUTING.md and lint/README.md direct local agents here.
ARCHITECTURE NOTE:
    Mirrors scripts/run_ci.py's own shape (a config dataclass, a
    parse_args function, a main function, `if __name__ == "__main__":
    raise SystemExit(main())`) since that is the nearest existing CLI
    entry point in this repo.
FUNCTION INVENTORY:
    LintCliConfig: Validated command-line contract for one invocation.
    parse_args() -> LintCliConfig: Parses --rule/--format/--all/--update-baseline.
    main() -> int: Runs the suite (or updates the baseline) and renders one report.
COMMON MODIFICATION PATTERNS:
    Add a new rule under lint/rules/ and register it in lint/core/registry.py;
    this file does not change for that.
WHAT NOT TO DO IN THIS FILE:
    Do not raise a bare unhandled exception from main(); every
    LintConfigurationError/LintAnalyzerError must be caught here and printed
    as an actionable failure, matching scripts/run_ci.py's own main().
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    lint/README.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
# `python lint/run.py` puts only lint/ on sys.path, not the repository root, so the
# `lint.core...` absolute imports below would fail with ModuleNotFoundError without this.
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lint.core.baseline import BaselineStore  # noqa: E402
from lint.core.diagnostic import DiagnosticRenderer, RuleDiagnostic  # noqa: E402
from lint.core.registry import RuleRegistry  # noqa: E402
from lint.core.rule import LintAnalyzerError, LintConfigurationError  # noqa: E402
from lint.core.runner import LintRunner, RuleOutcome, RunReport  # noqa: E402

PACKAGE_ROOT = REPOSITORY_ROOT / "vidbyte"
BASELINE_PATH = REPOSITORY_ROOT / "lint" / "baseline.json"
DEFAULT_FINDING_LIMIT = 20


@dataclass(frozen=True)
class LintCliConfig:
    """Validated command-line settings for one lint invocation."""

    rule_ids: tuple[str, ...] | None
    output_format: str
    show_all: bool
    update_baseline: bool


class LintReportPrinter:
    """Renders a RunReport as text or JSON to stdout."""

    @staticmethod
    def print_text(report: RunReport, show_all: bool) -> None:
        # Prints each rule's findings (capped unless show_all) then a final pass/fail line.
        for outcome in report.outcomes:
            rule = RuleRegistry.by_id(outcome.rule_id)
            LintReportPrinter._print_rule_text(outcome, rule.diagnostic(), show_all)
        LintReportPrinter._print_key_mismatches(report)
        LintReportPrinter._print_verdict_line(report)

    @staticmethod
    def _print_rule_text(outcome: RuleOutcome, diagnostic: RuleDiagnostic, show_all: bool) -> None:
        # Prints one rule's header line and its findings, capped at DEFAULT_FINDING_LIMIT.
        print(
            f"{outcome.rule_id}: {outcome.verdict.value} "
            f"(baseline={outcome.baseline_count}, actual={outcome.actual_count})"
        )
        if outcome.error:
            print(f"  ERROR: {outcome.error}")
            return
        shown = outcome.findings if show_all else outcome.findings[:DEFAULT_FINDING_LIMIT]
        for finding in shown:
            print(DiagnosticRenderer.render_text(finding, diagnostic))
        remaining = len(outcome.findings) - len(shown)
        if remaining > 0:
            print(f"  ... {remaining} more {outcome.rule_id} findings (rerun with --all to see them)")

    @staticmethod
    def _print_key_mismatches(report: RunReport) -> None:
        # Prints any baseline key that is stale (no matching rule) or missing (no baseline entry).
        for rule_id in report.stale_baseline_keys:
            print(f"BASELINE ERROR: lint/baseline.json has a stale entry for unregistered rule {rule_id!r}.")
        for rule_id in report.missing_baseline_keys:
            print(f"BASELINE ERROR: registered rule {rule_id!r} has no lint/baseline.json entry.")

    @staticmethod
    def _print_verdict_line(report: RunReport) -> None:
        # Prints the final AGENT-LINT verdict line the local CI gate and agents key off of.
        if report.passed:
            print("AGENT-LINT: PASS - every selected rule is at or below its recorded baseline.")
        else:
            print("AGENT-LINT: FAIL - see REGRESSED/ERRORED rules and any BASELINE ERROR lines above.")

    @staticmethod
    def print_json(report: RunReport) -> None:
        # Prints a compact JSON report for machine consumption.
        payload = {
            "passed": report.passed,
            "stale_baseline_keys": list(report.stale_baseline_keys),
            "missing_baseline_keys": list(report.missing_baseline_keys),
            "rules": [
                {
                    "rule_id": outcome.rule_id,
                    "verdict": outcome.verdict.value,
                    "baseline_count": outcome.baseline_count,
                    "actual_count": outcome.actual_count,
                    "error": outcome.error,
                    "findings": [DiagnosticRenderer.render_json(f) for f in outcome.findings],
                }
                for outcome in report.outcomes
            ],
        }
        print(json.dumps(payload, indent=2))


def parse_args(argv: list[str] | None = None) -> LintCliConfig:
    """Parse and normalize the stable local lint command-line interface."""
    parser = argparse.ArgumentParser(description="Run the Vidbyte SDK lint suite locally.")
    parser.add_argument("--rule", action="append", dest="rules", help="Restrict the run to one rule id; repeatable.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--all", action="store_true", help="Show every finding per rule, not just the first 20.")
    parser.add_argument("--update-baseline", action="store_true", help="Recompute and write lint/baseline.json.")
    args = parser.parse_args(argv)
    rule_ids = tuple(args.rules) if args.rules else None
    return LintCliConfig(rule_ids=rule_ids, output_format=args.format, show_all=args.all, update_baseline=args.update_baseline)


def main(argv: list[str] | None = None) -> int:
    """Run the lint suite (or update the baseline) and render one report."""
    config = parse_args(argv)
    runner = LintRunner(REPOSITORY_ROOT, PACKAGE_ROOT, BASELINE_PATH)
    try:
        if config.update_baseline:
            report = runner.run(rule_ids=None)
            counts = {outcome.rule_id: outcome.actual_count for outcome in report.outcomes}
            BaselineStore.save(BASELINE_PATH, counts)
            print(f"Wrote {BASELINE_PATH} with counts: {counts}")
            return 0
        report = runner.run(rule_ids=config.rule_ids)
    except (LintConfigurationError, LintAnalyzerError) as exc:
        print(f"Lint suite failed: {exc}", file=sys.stderr)
        return 1
    if config.output_format == "json":
        LintReportPrinter.print_json(report)
    else:
        LintReportPrinter.print_text(report, config.show_all)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
