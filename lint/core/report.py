"""FILE: lint/core/report.py

PURPOSE: Renders SDK lint outcomes as concise text or complete JSON.
ROLE IN CODEBASE: Gives agents a scope-first summary and focused repair instructions.
ARCHITECTURE NOTE: Counts always include untruncated findings.
FUNCTION INVENTORY: RunReport text/json/exit_code; DiagnosticRenderer renders sections.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by text/JSON lint commands.
"""

from __future__ import annotations

import json

from lint.core.diagnostic import Finding
from lint.core.runner import RuleResult


class DiagnosticRenderer:
    """Renders one finding in a stable agent-facing section order."""

    @classmethod
    def render(cls, result: RuleResult, finding: Finding) -> str:
        # Formats location, consequence, repair, precedent, rejected shortcuts, and verify.
        diagnostic = result.rule.explain(finding)
        sections = [f"SDK-LINT {result.rule.id} {result.rule.name} [{result.rule.severity.upper()}]", f"WHERE\n  {finding.location()}\n  {finding.source_line.strip()}", cls._section("WHAT HAPPENED", diagnostic.what_happened), cls._section("WHY THIS IS BLOCKED", diagnostic.why_blocked), cls._section("HOW TO FIX", diagnostic.how_to_fix), cls._section("CORRECT EXAMPLES", "\n".join(f"- {item}" for item in diagnostic.correct_examples) or "No local example exists yet; follow HOW TO FIX."), cls._section("WHAT WILL NOT WORK", "\n".join(f"- {item}" for item in diagnostic.will_not_work)), cls._section("VERIFY", diagnostic.verify or result.rule.verify_command())]
        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _section(title: str, body: str) -> str:
        # Indents multi-line diagnostic prose under one stable title.
        return f"{title}\n" + "\n".join(f"  {line}" for line in body.splitlines()) if body else ""


class RunReport:
    """Aggregates rule results and owns process status/presentation."""

    def __init__(self, results: tuple[RuleResult, ...], truncate: int = 20, expand_all: bool = False) -> None:
        # Retains complete results and presentation-only truncation settings.
        self.results = results
        self.truncate = truncate
        self.expand_all = expand_all

    def exit_code(self) -> int:
        # Returns failure when any selected rule regressed or errored.
        return 1 if any(result.failing() for result in self.results) else 0

    def render_text(self) -> str:
        # Renders the complete summary followed by only actionable detail blocks.
        blocks = [self._summary()]
        for result in self.results:
            detail = self._detail(result)
            if detail:
                blocks.append(detail)
        blocks.append("SDK-LINT: PASS" if self.exit_code() == 0 else "SDK-LINT: FAIL")
        return "\n\n".join(blocks)

    def render_json(self) -> str:
        # Serializes every untruncated finding for automation and baseline inspection.
        return json.dumps({"exit_code": self.exit_code(), "rules": [self._json_rule(result) for result in self.results]}, indent=2)

    def _summary(self) -> str:
        # Builds the rule/count/baseline/verdict table shown before diagnostics.
        rows = [f"{'RULE':<6} {'NAME':<38} {'FOUND':>6} {'BASE':>6} VERDICT", "-" * 72]
        rows.extend(f"{result.rule.id:<6} {result.rule.name[:38]:<38} {len(result.findings):>6} {result.allowance:>6} {result.verdict}" for result in self.results)
        return "\n".join(rows)

    def _detail(self, result: RuleResult) -> str:
        # Renders failures, improvements, or expanded known debt without flooding normal passes.
        if result.error:
            return f"SDK-LINT {result.rule.id} ERRORED\n{result.error}"
        if result.verdict == "IMPROVED":
            return f"{result.rule.id} IMPROVED {result.allowance} -> {len(result.findings)}. Lower it with: python lint/run.py --rule {result.rule.id} --update-baseline"
        if result.verdict == "RATCHETED" and not self.expand_all:
            return f"{result.rule.id} RATCHETED: {len(result.findings)} known finding(s). Inspect with: python lint/run.py --rule {result.rule.id} --all"
        if result.verdict == "CLEAN":
            return ""
        findings = result.findings if self.expand_all else result.findings[: self.truncate]
        blocks = [f"{result.rule.id} {result.verdict}: {len(result.findings)} finding(s), allowance {result.allowance}."]
        blocks.extend(DiagnosticRenderer.render(result, finding) for finding in findings)
        return "\n\n".join(blocks)

    def _json_rule(self, result: RuleResult) -> dict[str, object]:
        # Converts one result to a stable machine-readable object.
        return {"id": result.rule.id, "name": result.rule.name, "found": len(result.findings), "baseline": result.allowance, "verdict": result.verdict, "error": result.error or None, "findings": [{"path": item.rel_path, "line": item.line, "symbol": item.symbol, "source_line": item.source_line, "extra": item.extra} for item in result.findings]}
