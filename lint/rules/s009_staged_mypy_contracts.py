"""FILE: lint/rules/s009_staged_mypy_contracts.py

PURPOSE: Exposes the complete package mypy result as one staged debt ratchet.
ROLE IN CODEBASE: Catches incompatible calls, coroutine misuse, and contract drift.
ARCHITECTURE NOTE: Optional integration imports are tolerated; local types are not.
FUNCTION INVENTORY: StagedMypyContractsRule check/explain.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S009.
"""

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.mypy import MypyStore
from lint.core.registry import Rule


class StagedMypyContractsRule(Rule):
    """Ratchets every mypy error across the complete production package."""

    id = "S009"
    name = "staged-mypy-contracts"
    severity = "blocking"
    summary = "This rule makes the package-wide mypy result a staged contract rather than an all-or-nothing migration. Every existing error is counted as explicit debt, while any increase is treated as a new defect in the SDK interface or implementation. The scan covers production code so provider, transport, runner, tool, and result mismatches cannot hide behind untyped callers. The ratchet lets the repository improve incrementally without allowing new ambiguity to accumulate. A lower count is evidence of progress, but it must be deliberately ratcheted into the checked-in baseline after review."
    impact = "A mypy finding often represents a runtime mismatch even when the failing branch has not been exercised by a test. Examples include awaiting a synchronous transport, passing an optional value to a required boundary, or returning a result with the wrong public shape. Allowing new errors makes the type surface less trustworthy for SDK users, IDEs, and future agents. Raising the baseline would hide that regression and make the remaining debt harder to reduce honestly. The debt count is therefore a guard against new contract drift, not permission to leave newly introduced errors unresolved."
    repair = "Read the full mypy message and inspect both the producer and consumer named by the type mismatch. Align the implementation with the real contract by correcting annotations, narrowing optional values, awaiting async results, or changing the call shape. Keep third-party import tolerance limited to missing external stubs and do not add a local ignore or weaken a value to Any. Run the focused rule, then mypy and the affected source tests, and lower the baseline only after the improvement is intentional. When the count changes, review the complete diff and update only the exact allowance that the verified improvement justifies."
    examples = (
        "vidbyte/lib/http/transport.py - separate async and synchronous transport contracts",
        "A mypy error whose producer and consumer annotations agree after the repair",
    )
    will_not_work = (
        "Adding type: ignore or broadening a meaningful type to Any only to reduce the count.",
        "Narrowing mypy's checked package or increasing lint/baseline.json to make new debt appear historical.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Converts cached mypy errors to source-enriched native findings.
        source = {item.rel: item for item in catalog.python_files()}
        return [Finding(rule_id=self.id, rel_path=record.rel_path, line=record.line, source_line=source.get(record.rel_path).line_at(record.line) if record.rel_path in source else "", symbol=record.code, extra={"message": record.message, "column": str(record.column), "code": record.code}) for record in MypyStore.records()]

    def explain(self, finding: Finding) -> Diagnostic:
        # Explains why a static mismatch is part of the SDK's callable contract.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} has mypy {finding.extra.get('code', 'error')}: {finding.extra.get('message', '')}", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = StagedMypyContractsRule()
