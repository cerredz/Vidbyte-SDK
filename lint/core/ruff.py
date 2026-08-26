"""FILE: lint/core/ruff.py

PURPOSE: Runs pinned Ruff once and adapts records to native SDK lint rules.
ROLE IN CODEBASE: S001-S008 share analyzer work while retaining separate baselines.
ARCHITECTURE NOTE: Isolated selectors prevent ambient repo/user config drift.
FUNCTION INVENTORY: RuffStore.records(); RuffBackedRule check/explain.
WHAT NOT TO DO: Never accept a missing analyzer, malformed JSON, or nonzero engine error.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by S001-S008 through python lint/run.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, repo_root
from lint.core.registry import Rule

SELECTORS = "ANN,B904,B905,C901,DTZ,E4,E7,E9,F,PLR0912,PLR0915,RUF006,RUF012"


class RuffAnalyzerError(RuntimeError):
    """Ruff could not provide a complete trustworthy finding set."""


@dataclass(frozen=True, slots=True)
class RuffRecord:
    """One normalized Ruff diagnostic."""

    code: str
    message: str
    rel_path: str
    line: int
    column: int


class RuffStore:
    """Caches one isolated Ruff JSON scan for every Ruff-backed rule."""

    _cache: tuple[RuffRecord, ...] | None = None

    @classmethod
    def records(cls) -> tuple[RuffRecord, ...]:
        # Returns cached records or executes the analyzer exactly once.
        if cls._cache is None:
            cls._cache = cls._run()
        return cls._cache

    @classmethod
    def _run(cls) -> tuple[RuffRecord, ...]:
        # Executes Ruff without a shell and validates process/payload boundaries.
        command = [sys.executable, "-m", "ruff", "check", "vidbyte", "--isolated", "--select", SELECTORS, "--output-format", "json", "--exit-zero", "--no-cache"]
        try:
            result = subprocess.run(command, cwd=repo_root(), check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuffAnalyzerError(f"Could not start Ruff from {repo_root()} with {command!r}: {exc}. Install the project dev extra.") from exc
        if result.returncode != 0:
            raise RuffAnalyzerError(f"Ruff failed with exit code {result.returncode} from {repo_root()}; command={command!r}; stderr={result.stderr.strip() or '<empty>'}.")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuffAnalyzerError(f"Ruff returned malformed JSON: {exc}; stdout began {result.stdout[:500]!r}.") from exc
        if not isinstance(payload, list):
            raise RuffAnalyzerError(f"Ruff JSON must be a list, received {type(payload).__name__}.")
        return tuple(cls._record(item) for item in payload)

    @classmethod
    def _record(cls, item: object) -> RuffRecord:
        # Validates one record and normalizes absolute/relative filenames.
        if not isinstance(item, dict) or not isinstance(item.get("code"), str) or not isinstance(item.get("filename"), str) or not isinstance(item.get("location"), dict):
            raise RuffAnalyzerError(f"Unexpected Ruff diagnostic record: {item!r}.")
        location = item["location"]
        if not isinstance(location.get("row"), int):
            raise RuffAnalyzerError(f"Ruff diagnostic has no integer row: {item!r}.")
        filename = Path(item["filename"])
        absolute = filename if filename.is_absolute() else repo_root() / filename
        try:
            rel = absolute.resolve().relative_to(repo_root().resolve()).as_posix()
        except ValueError as exc:
            raise RuffAnalyzerError(f"Ruff reported path outside repository: {absolute}.") from exc
        return RuffRecord(code=item["code"], message=str(item.get("message", "")), rel_path=rel, line=location["row"], column=int(location.get("column", 1)))


class RuffBackedRule(Rule):
    """Selects one conceptual policy from the cached Ruff record set."""

    codes: frozenset[str] = frozenset()
    prefixes: tuple[str, ...] = ()
    excluded_prefixes: tuple[str, ...] = ()
    impact = (
        "This analyzer finding identifies a source pattern that can violate a supported SDK correctness contract. "
        "The analyzer reports the local syntax fact, but the operational consequence depends on the boundary where that fact occurs. "
        "Without rule-specific context, an agent may suppress a real defect or repair the symptom while preserving the underlying risk. "
        "Concrete impact prose connects the reported line to the caller-visible behavior that the rule protects."
    )
    repair = (
        "Read the analyzer code, message, source line, and surrounding contract before editing. "
        "Apply the smallest canonical repair that restores the rule's invariant at the owning boundary. "
        "Preserve intentional exceptions through explicit source structure rather than suppressions or baseline changes. "
        "Run the focused rule and the affected repository gate after verifying the repaired behavior."
    )
    examples: tuple[str, ...] = ()
    will_not_work: tuple[str, ...] = (
        "Adding noqa, per-file ignores, or analyzer configuration exceptions.",
        "Raising lint/baseline.json because pre-existing debt is already frozen.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Filters cached Ruff records and enriches them with source lines.
        source = {item.rel: item for item in catalog.python_files()}
        findings: list[Finding] = []
        for record in RuffStore.records():
            if not self._matches(record.code) or record.rel_path.startswith(self.excluded_prefixes):
                continue
            findings.append(Finding(rule_id=self.id, rel_path=record.rel_path, line=record.line, source_line=source.get(record.rel_path).line_at(record.line) if record.rel_path in source else "", symbol=record.code, extra={"code": record.code, "message": record.message, "column": str(record.column)}))
        return findings

    def _matches(self, code: str) -> bool:
        # Matches exact selectors or an explicitly declared selector family.
        return code in self.codes or code.startswith(self.prefixes)

    def explain(self, finding: Finding) -> Diagnostic:
        # Adds SDK-specific consequence and repair guidance to Ruff's local fact.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} violates {finding.extra.get('code', 'Ruff')}: {finding.extra.get('message', '')}", why_blocked=self.impact, how_to_fix=f"{self.repair} Ruff reported column {finding.extra.get('column', '1')}.", correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())
