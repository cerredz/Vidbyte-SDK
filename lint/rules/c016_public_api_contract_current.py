"""FILE: lint/rules/c016_public_api_contract_current.py

PURPOSE: Detect a committed contracts/sdk-public-api.json that is missing, malformed, stale against vidbyte/__init__.py `__all__` or pyproject.toml, or not byte-identical to the generator's canonical output.
ROLE IN CODEBASE: Enforces C016, the owner side of cross-repo contract X03: vidbyte-cli vendors this file and lets its code import only the SDK names it lists, so the file must always equal what scripts/generate-sdk-public-api.py derives now.
ARCHITECTURE NOTE: Derivation, schema, and rendering live in lint/core/public_api_contract.py, shared with the generator, so the rule and the writer cannot disagree. The rule never imports vidbyte and never runs git beyond the shared catalogue's ls-files.
FUNCTION INVENTORY: ContractFacts gathers derivation, committed file, and tracking state; PublicApiFindings turns each disagreement into one Finding; PublicApiContractCurrentRule reports and explains.
COMMON MODIFICATION PATTERNS: A new finding kind needs a branch in PublicApiFindings, a what/repair entry in the rule, and a scratch fixture. Schema changes belong in lint/core/public_api_contract.py with a schema_version bump coordinated with vidbyte-cli.
WHAT NOT TO DO: Do not import vidbyte, edit the contract, compare against git history (CI checks out at depth 1), or report not-canonical on top of a data drift the generator would fix in the same run.
KNOWN EDGE CASES: An untracked contract on disk counts as missing because CI would not see it. A CRLF checkout is not-canonical. An unresolvable `__all__` reports source-unresolvable and skips the data comparison, since no honest expected value exists.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md; contracts/README.md; lint implementation plan "Cross-repo contract files"; lint catalog X03.
TESTS: python lint/run.py --rule C016; python scripts/generate-sdk-public-api.py --check; fixture and mutation results are recorded in the S4 pull request body.
"""

from __future__ import annotations

from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.public_api_contract import CONTRACT_REL, GENERATOR_REL, INIT_REL, PYPROJECT_REL, CommittedPublicApi, DerivedPublicApi, ExportResolutionError, PublicApiCodec, PublicApiDeriver
from lint.core.registry import Rule

_LISTED_NAMES = 12
_MISSING = "contract-missing"
_MALFORMED = "contract-malformed"
_EXPORTS = "exports-stale"
_VERSION = "version-stale"
_DISTRIBUTION = "distribution-stale"
_NOT_CANONICAL = "not-canonical"
_UNRESOLVABLE = "source-unresolvable"
_GENERATOR = "generator-missing"
_KINDS = frozenset({_MISSING, _MALFORMED, _EXPORTS, _VERSION, _DISTRIBUTION, _NOT_CANONICAL, _UNRESOLVABLE, _GENERATOR})
_GENERATE = f"python {GENERATOR_REL}"


@dataclass(frozen=True, slots=True)
class ContractFacts:
    """Everything C016 compares: the fresh derivation (or why it failed), the committed file, and what git tracks."""

    derived: DerivedPublicApi | None
    unresolvable: ExportResolutionError | None
    committed: CommittedPublicApi
    contract_tracked: bool
    generator_tracked: bool

    def __post_init__(self) -> None:
        # Exactly one of a derivation and its failure must be present, or the comparison has no expected value.
        if (self.derived is None) == (self.unresolvable is None):
            raise ValueError("ContractFacts needs exactly one of derived and unresolvable.")

    @classmethod
    def gather(cls, catalog: SourceCatalog) -> ContractFacts:
        # Derive the contract from source, read the committed copy, and note what git tracks.
        tracked = set(catalog.tracked_paths())
        try:
            derived, failure = PublicApiDeriver(catalog).derive(), None
        except ExportResolutionError as exc:
            derived, failure = None, exc
        return cls(derived=derived, unresolvable=failure, committed=CommittedPublicApi.load(catalog.root / CONTRACT_REL), contract_tracked=CONTRACT_REL in tracked, generator_tracked=GENERATOR_REL in tracked)


class PublicApiFindings:
    """Turns each disagreement between source and the committed contract into one anchored finding."""

    def __init__(self, catalog: SourceCatalog, rule_id: str) -> None:
        # Binds the catalogue for source lines and the rule ID every finding carries.
        self.catalog = catalog
        self.rule_id = rule_id
        self.codec = PublicApiCodec()

    def collect(self, facts: ContractFacts) -> list[Finding]:
        # Source problems first, then the file's presence and shape, then data drift, then formatting.
        findings: list[Finding] = []
        if facts.unresolvable is not None:
            findings.append(self._unresolvable(facts.unresolvable))
        if not facts.generator_tracked:
            findings.append(self._finding(CONTRACT_REL, 1, _GENERATOR, GENERATOR_REL, {"generator": GENERATOR_REL}, facts))
        committed = facts.committed
        if not committed.exists or not facts.contract_tracked:
            reason = "it does not exist" if not committed.exists else "it exists on disk but is not tracked by git, so CI and every consumer would not see it"
            findings.append(self._finding(CONTRACT_REL, 1, _MISSING, CONTRACT_REL, {"reason": reason}, facts))
            return findings
        if committed.contract is None:
            findings.append(self._finding(CONTRACT_REL, committed.problem_line, _MALFORMED, committed.problem_field, {"field": committed.problem_field, "problem": committed.problem}, facts))
            return findings
        if facts.derived is None:
            return findings
        drift = self._drift(facts)
        findings.extend(drift)
        if not drift and committed.text != self.codec.render(committed.contract):
            findings.append(self._finding(CONTRACT_REL, self._first_difference(committed.text, self.codec.render(committed.contract)), _NOT_CANONICAL, CONTRACT_REL, {"crlf": "yes" if "\r\n" in committed.text else "no"}, facts))
        return findings

    def _drift(self, facts: ContractFacts) -> list[Finding]:
        # One finding per stale field: the export set, the version, and the distribution name.
        if facts.derived is None or facts.committed.contract is None:
            return []
        old, new, text = facts.committed.contract.data, facts.derived.data, facts.committed.text
        findings: list[Finding] = []
        added = sorted(set(new.exports) - set(old.exports))
        removed = sorted(set(old.exports) - set(new.exports))
        if added or removed:
            listed_added = "; ".join(f"`{name}` ({facts.derived.export_origins[name]})" for name in added[:_LISTED_NAMES])
            listed_removed = "; ".join(f"`{name}` ({CONTRACT_REL}:{self.codec.export_line(text, name)})" for name in removed[:_LISTED_NAMES])
            extra = {"added": listed_added, "removed": listed_removed, "added_count": str(len(added)), "removed_count": str(len(removed)), "committed_count": str(len(old.exports)), "derived_count": str(len(new.exports))}
            findings.append(self._finding(CONTRACT_REL, self.codec.key_line(text, "exports"), _EXPORTS, f"exports +{len(added)} -{len(removed)}", extra, facts))
        if old.version != new.version:
            findings.append(self._finding(CONTRACT_REL, self.codec.key_line(text, "version"), _VERSION, f"version {old.version}", {"committed": old.version, "derived": new.version, "source": f"{PYPROJECT_REL}:{facts.derived.version_line}"}, facts))
        if old.distribution != new.distribution:
            findings.append(self._finding(CONTRACT_REL, self.codec.key_line(text, "distribution"), _DISTRIBUTION, f"distribution {old.distribution}", {"committed": old.distribution, "derived": new.distribution, "source": f"{PYPROJECT_REL}:{facts.derived.name_line}"}, facts))
        return findings

    def _unresolvable(self, exc: ExportResolutionError) -> Finding:
        # Anchors at the declaration that blocks a static answer.
        source = next((item for item in self.catalog.python_files() if item.rel == exc.rel), None)
        line_text = source.line_at(exc.line) if source is not None else ""
        return Finding(rule_id=self.rule_id, rel_path=exc.rel, line=exc.line, source_line=line_text, symbol=_UNRESOLVABLE, extra={"kind": _UNRESOLVABLE, "problem": exc.message, "where": f"{exc.rel}:{exc.line}"})

    def _finding(self, rel: str, line: int, kind: str, symbol: str, extra: dict[str, str], facts: ContractFacts) -> Finding:
        # Builds one contract-anchored finding with the committed line text when the file exists.
        lines = facts.committed.text.splitlines()
        source_line = lines[line - 1] if 0 < line <= len(lines) else ""
        return Finding(rule_id=self.rule_id, rel_path=rel, line=line, source_line=source_line, symbol=symbol, extra={"kind": kind, **extra})

    @staticmethod
    def _first_difference(actual: str, canonical: str) -> int:
        # The first 1-based line where the committed bytes leave the canonical rendering.
        for index, (left, right) in enumerate(zip(actual.split("\n"), canonical.split("\n"), strict=False), start=1):
            if left != right:
                return index
        return min(actual.count("\n"), canonical.count("\n")) + 1


class PublicApiContractCurrentRule(Rule):
    """Requires contracts/sdk-public-api.json to equal the generator's output for the current source."""

    id = "C016"
    name = "public-api-contract-current"
    severity = "blocking"
    summary = "contracts/sdk-public-api.json is the SDK's published import surface (the sorted names of vidbyte.__all__ plus the pyproject distribution and version) that vidbyte-cli vendors. It must exist, be tracked, follow the fixed schema_version 1 schema, carry the current exports, version, and distribution, and be byte-identical to what scripts/generate-sdk-public-api.py writes."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Gather the derivation and the committed file once, then report every disagreement.
        return PublicApiFindings(catalog, self.id).collect(ContractFacts.gather(catalog))

    def explain(self, finding: Finding) -> Diagnostic:
        # One what/repair pair per kind, with the same consequence and rejected shortcuts.
        kind = finding.extra.get("kind", "")
        if kind not in _KINDS:
            raise ValueError(f"C016 finding has unknown kind {kind!r}.")
        return Diagnostic(
            what_happened=self._what(finding, kind),
            why_blocked=f"{CONTRACT_REL} is the SDK's published import surface. vidbyte-cli's lint lane (PR C5) vendors it at lint/contracts/sdk-public-api.json and lets CLI code import only the names it lists, because the CLI imported 22 SDK names through deep internal paths that the SDK's placement rules move code between (lint catalog X03; the implementation plan's \"Cross-repo contract files\" section fixes this schema). A missing, malformed, or stale file misinforms that consumer: a new export missing from the file is blocked in the CLI, and a name dropped from `__all__` but still listed lets the CLI keep importing something the next SDK release no longer exports, which fails at import time after an upgrade. The file must therefore equal what {GENERATOR_REL} derives from {INIT_REL} and {PYPROJECT_REL}, byte for byte (docs/design/lint-sdk-cross-repo-contracts.md).",
            how_to_fix=self._repair(finding, kind),
            correct_examples=(
                f"{CONTRACT_REL} at f8b048ab - written by {GENERATOR_REL} from the 593 names of vidbyte.__all__; `{_GENERATE} --check` exits 0 on it.",
                "cerredz/Vidbyte contracts/vidbyte-platform-contract.json with scripts/generate-platform-contract.py and rule B065 - the platform contract's generator and freshness rule, which this contract mirrors.",
            ),
            will_not_work=(
                f"Editing {CONTRACT_REL} by hand: its bytes and source.commit must come from the generator, and C016 compares it with a fresh derivation of the source.",
                f"Running the generator while {INIT_REL} or {PYPROJECT_REL} has uncommitted changes: it refuses, because source.commit would name a commit that does not contain the inputs it read.",
                "Hiding a name with a conditional or computed `__all__`: C016 and the generator both fail closed on any `__all__` they cannot resolve statically.",
                "Raising C016's baseline in lint/baseline.json: the baseline is 0, and every finding means the published surface is wrong.",
            ),
            verify=f"{self.verify_command()} && {_GENERATE} --check",
        )

    @staticmethod
    def _what(finding: Finding, kind: str) -> str:
        # States the exact disagreement with paths, lines, and values.
        extra = finding.extra
        where = finding.location()
        if kind == _EXPORTS:
            added = f" Added to `__all__` but missing from the file ({extra['added_count']}): {extra['added']}." if extra["added"] else ""
            removed = f" Listed in the file but no longer in `__all__` ({extra['removed_count']}): {extra['removed']}." if extra["removed"] else ""
            return f"{where} `exports` is stale: the file lists {extra['committed_count']} names, and {INIT_REL} `__all__` resolves to {extra['derived_count']}.{added}{removed}"
        if kind in {_VERSION, _DISTRIBUTION}:
            field = "version" if kind == _VERSION else "distribution"
            return f"{where} `{field}` is {extra['committed']!r}, but {extra['source']} declares {extra['derived']!r}."
        if kind == _MISSING:
            return f"{CONTRACT_REL} is missing: {extra['reason']}."
        if kind == _MALFORMED:
            return f"{where} is malformed at `{extra['field']}`: {extra['problem']}."
        if kind == _NOT_CANONICAL:
            crlf = " The file has CRLF line endings; contracts/.gitattributes pins LF." if extra["crlf"] == "yes" else ""
            return f"{where} holds the current data but is not byte-identical to the generator's canonical rendering from this line on.{crlf}"
        if kind == _GENERATOR:
            return f"{GENERATOR_REL}, the only writer of {CONTRACT_REL} and the path its source.generator field names, is not tracked."
        return f"{extra['where']} cannot be resolved statically: {extra['problem']}. No honest {CONTRACT_REL} can be derived until it can."

    @staticmethod
    def _repair(finding: Finding, kind: str) -> str:
        # Numbered steps for this kind; every path ends with the generator and the focused check.
        regenerate = f"From the repository root run `{_GENERATE}`. It rewrites {CONTRACT_REL} and records HEAD as source.commit, and it refuses while {INIT_REL} or {PYPROJECT_REL} has uncommitted changes."
        if kind in {_EXPORTS, _VERSION, _DISTRIBUTION}:
            removal = " If any export was removed or renamed, say so in the pull request body: vidbyte-cli must update its imports and its vendored copy before it upgrades to this SDK version." if kind == _EXPORTS and finding.extra.get("removed") else ""
            return "\n".join((
                f"1. Confirm the change to {INIT_REL} `__all__` or {PYPROJECT_REL} [project] is intended. If a name was removed or renamed by accident, restore it and stop here.",
                f"2. Commit that source change, then {regenerate[0].lower()}{regenerate[1:]}",
                f"3. Commit {CONTRACT_REL} in the same pull request as the source change.{removal}",
                f"4. Run `{_GENERATE} --check` and `python lint/run.py --rule C016`.",
            ))
        if kind == _MISSING:
            return "\n".join((f"1. Restore the file with `git checkout -- {CONTRACT_REL}`, or regenerate it: {regenerate}", f"2. `git add {CONTRACT_REL}` so CI and vidbyte-cli see the same file you do.", f"3. Run `{_GENERATE} --check`."))
        if kind in {_MALFORMED, _NOT_CANONICAL}:
            return "\n".join((f"1. Do not repair {CONTRACT_REL} by hand. Restore it with `git checkout -- {CONTRACT_REL}` if it was edited, or run `{_GENERATE}`; when the data is unchanged it only restores the canonical bytes and keeps source.commit.", "2. Confirm contracts/.gitattributes still pins `*.json text eol=lf`, so a Windows checkout cannot reintroduce CRLF.", f"3. Run `{_GENERATE} --check`."))
        if kind == _GENERATOR:
            return "\n".join((f"1. Restore {GENERATOR_REL} with `git checkout -- {GENERATOR_REL}`; it and C016 share lint/core/public_api_contract.py, so neither can be rebuilt from the other.", f"2. Run `{_GENERATE} --check`."))
        return "\n".join((
            f"1. Rewrite the construct at {finding.extra['where']} into a static module-level form: a list or tuple of string literals, `+` concatenation, `*name` of an earlier list, `__all__ += [...]`, `__all__.extend([...])`, or `__all__.append(\"Name\")`, or import another vidbyte module's `__all__` and concatenate it. Keep `[project].version` a static string in {PYPROJECT_REL}.",
            "2. If the public surface really must be computed, extend AllResolver in lint/core/public_api_contract.py with a fixture in the same change, so the generator and C016 still agree.",
            f"3. Run `{_GENERATE} --check`.",
        ))


RULE = PublicApiContractCurrentRule()
