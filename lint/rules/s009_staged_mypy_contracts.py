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
    summary = "Package type errors may only decrease; every new contract mismatch fails."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Converts cached mypy errors to source-enriched native findings.
        source = {item.rel: item for item in catalog.python_files()}
        return [Finding(rule_id=self.id, rel_path=record.rel_path, line=record.line, source_line=source.get(record.rel_path).line_at(record.line) if record.rel_path in source else "", symbol=record.code, extra={"message": record.message, "column": str(record.column), "code": record.code}) for record in MypyStore.records()]

    def explain(self, finding: Finding) -> Diagnostic:
        # Explains why a static mismatch is part of the SDK's callable contract.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} has mypy {finding.extra.get('code', 'error')}: {finding.extra.get('message', '')}", why_blocked="SDK annotations are consumed by users, IDEs, and internal dispatch. A mismatch often represents a real coroutine/transport/provider/result contract bug even when one dynamic path has not executed yet.", how_to_fix="Repair the source contract: align parameter/return types, await async results, narrow optional values, or correct the implementation. Keep ignore_missing_imports limited to absent third-party stubs; do not add local type ignores.", correct_examples=("vidbyte/lib/http/transport.py - separate async and synchronous transport contracts",), will_not_work=("Adding type: ignore or weakening the value to Any only to reduce the count.", "Narrowing mypy's checked package or raising the baseline."), verify=self.verify_command())


RULE = StagedMypyContractsRule()
