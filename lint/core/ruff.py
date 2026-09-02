"""FILE: lint/core/ruff.py

PURPOSE: Runs pinned Ruff once and adapts records to native SDK lint rules.
ROLE IN CODEBASE: S001-S002, S007-S008, S025-S054 share analyzer work while retaining separate baselines.
ARCHITECTURE NOTE: Isolated selectors prevent ambient repo/user config drift.
FUNCTION INVENTORY: RuffStore.records(); RuffBackedRule check/explain.
WHAT NOT TO DO: Never accept a missing analyzer, malformed JSON, or nonzero engine error.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by S001-S002, S007-S008, and S025-S054 through python lint/run.py.
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

SELECTORS = (
    "ANN,B904,B905,C901,DTZ,E4,E7,E9,F,PLR0912,PLR0915,RUF006,RUF012,"
    "RUF007,RUF008,RUF009,RUF015,RUF017,RUF018,RUF019,RUF024,RUF043,RUF100,RUF200,"
    "PGH003,PGH004,TID251,TID252,PLW1514,TRY002,TRY401,G004,"
    "ASYNC109,ASYNC210,ASYNC230,ASYNC251,S506,S324,"
    "I001,UP006,UP007,UP035,UP045,"
    "ASYNC100,ASYNC105,ASYNC110,ASYNC220,ASYNC221,"
    "B017,B023,B028,B039,"
    "S105,S106,S107,S108,S301,S302,S501"
)


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
        # Executes the explicit lint policy over package code and project metadata.
        command = [sys.executable, "-m", "ruff", "check", "pyproject.toml", "vidbyte", "--config", str(repo_root() / "lint" / "ruff.toml"), "--select", SELECTORS, "--output-format", "json", "--exit-zero", "--no-cache"]
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
    impact = "This analyzer finding violates a supported SDK correctness contract."
    repair = "Apply the analyzer guidance without adding a suppression."
    examples: tuple[str, ...] = ()

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
        # Matches exact selectors or numeric Ruff families without treating F as FAST.
        if code in self.codes:
            return True
        return any(code.startswith(prefix) and code[len(prefix):].startswith(tuple("0123456789")) for prefix in self.prefixes)

    def explain(self, finding: Finding) -> Diagnostic:
        # Adds several sentences of SDK-specific context to Ruff's local fact.
        code = finding.extra.get("code", "Ruff")
        message = finding.extra.get("message", "Ruff reported a violation.")
        return Diagnostic(
            what_happened=(
                f"{finding.rel_path} line {finding.line} violates {code}: {message}. "
                "Ruff identified this construct at the displayed source location. "
                f"The finding belongs to the `{self.name}` SDK policy and is counted independently in the baseline. "
                "The code may parse and pass a narrow example, but it does not satisfy the repository contract represented by this rule. "
                "Review the owning boundary before changing the source."
            ),
            why_blocked=(
                f"{self.impact} "
                "A later caller, model interaction, retry, or packaging step can observe the difference even when the local line looks harmless. "
                "Keeping the finding blocking makes the contract visible to maintainers and future coding agents."
            ),
            how_to_fix=(
                f"{self.repair} "
                f"Ruff reported column {finding.extra.get('column', '1')}. "
                "After editing, rerun the focused command and inspect the count rather than accepting a silent suppression."
            ),
            correct_examples=self.examples,
            will_not_work=(
                "Adding `# noqa`, a per-file ignore, or changing lint/ruff.toml to hide the finding; that removes evidence without repairing the SDK contract.",
                "Raising lint/baseline.json for a newly introduced violation; the baseline freezes existing debt and does not authorize new debt.",
                "Moving the same construct into a helper or renaming it when the rule concerns the underlying API, lifetime, or data flow."
            ),
            verify=self.verify_command(),
        )
