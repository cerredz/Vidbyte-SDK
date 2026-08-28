"""FILE: lint/run.py

PURPOSE: Provides the SDK lint suite's stable command-line entry point.
ROLE IN CODEBASE: Used by coding agents and scripts/run_ci.py source stage.
ARCHITECTURE NOTE: Baseline updates are explicit and never hide analyzer errors.
FUNCTION INVENTORY: LintApplication.run(); ArgumentParserFactory.build(); main().
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised directly and by canonical CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lint.core.baseline import BaselineContractError
from lint.core.registry import RuleRegistry, RuleSelectionError
from lint.core.report import RunReport
from lint.core.runner import RuleRunner


class ArgumentParserFactory:
    """Builds the stable lint CLI without mixing parsing into execution."""

    @staticmethod
    def build() -> argparse.ArgumentParser:
        # Declares focused selection, output, expansion, and baseline maintenance flags.
        parser = argparse.ArgumentParser(description="Run the Vidbyte SDK agent-facing lint suite.")
        parser.add_argument("--rule", help="Run one rule ID, for example S010.")
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument("--all", action="store_true", help="Render every known finding.")
        parser.add_argument("--update-baseline", action="store_true", help="Record current counts after reviewing findings.")
        return parser


class LintApplication:
    """Coordinates selection, execution, baseline maintenance, and rendering."""

    def run(self, argv: list[str] | None = None) -> int:
        # Executes one complete CLI request and returns its process status.
        args = ArgumentParserFactory.build().parse_args(argv)
        try:
            registry = RuleRegistry()
            rules = registry.select(args.rule)
            runner = RuleRunner(rules, {rule.id for rule in registry.all()}, validate_baseline=not args.update_baseline)
            results = runner.run()
        except (BaselineContractError, RuleSelectionError) as exc:
            print(f"SDK lint setup failed: {exc}", file=sys.stderr)
            return 2
        if args.update_baseline:
            counts = runner.counts(results)
            existing = runner.store.load()
            existing.update(counts)
            runner.store.write(existing)
            print(f"Updated lint/baseline.json for {', '.join(sorted(counts))}.")
            return 0
        report = RunReport(results, truncate=20, expand_all=args.all)
        print(report.render_json() if args.format == "json" else report.render_text())
        return report.exit_code()


def main(argv: list[str] | None = None) -> int:
    # Runs the class-bound application from Python and console entry points.
    return LintApplication().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
