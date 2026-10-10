"""FILE: lint/rules/c010_pricebook_vintage_bump.py

PURPOSE: Detect a pricebook whose rate literals changed while its vintage (PRICING_AS_OF / OPERATION_PRICING_AS_OF) did not move, or whose vintage moved without the committed lock being refreshed.
ROLE IN CODEBASE: Enforces C010 so two different sets of SDK rates can never share one vintage string, which the Vidbyte backend uses as the persisted pricebook identity of a resumable run.
ARCHITECTURE NOTE: The lint core has no git base-ref comparison, so this is a static equivalent: lint/pricebook_vintage_lock.json records, per pricebook, the vintage and a digest of every effective rate entry (dataclass defaults filled in, module-level rate tables resolved). The check compares the source with the lock; only the --refresh-lock command writes the lock, and it refuses when rates changed without a later vintage.
FUNCTION INVENTORY: RateTableReader canonicalizes one table; PricebookSnapshot holds digests; LockStore reads, verifies, and writes the lock; VintageJudge classifies drift; PricebookVintageBumpRule reports; LockRefresher and main() implement `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`.
COMMON MODIFICATION PATTERNS: To cover a new pricebook, add a PricebookSpec to _PRICEBOOKS, run --refresh-lock once to add its lock section, and rerun C010. Keep RateTableReader in step with the record dataclasses' field order and defaults.
WHAT NOT TO DO: Do not import vidbyte, read git history, compare against today's date, or let the refresh command write a lock for changed rates under an unchanged vintage.
KNOWN EDGE CASES: Reordering entries, reformatting numbers (272_000 vs 272000), and editing comments change no digest. A changed dataclass default changes every entry that relies on it. An expression the reader cannot resolve is fingerprinted by its source text. A missing or hand-edited lock fails closed.
RELATED DOCS: docs/design/lint-sdk-pricing-usage-contracts.md; vidbyte/lib/registries/pricing.py and operation_pricing.py (Rates verified ... on *_AS_OF); vidbyte backend/lib/enums/research.py ResearchPricebookVersion.
TESTS: python lint/run.py --rule C010; fixture and mutation results are recorded in the S2 pull request body.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

LOCK_PATH = "lint/pricebook_vintage_lock.json"
REFRESH_COMMAND = "python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock"
_SCHEMA_VERSION = 1
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGEST_CHARS = 16
_LISTED_ENTRIES = 8
_CHANGED_WITHOUT_BUMP = "rates-changed-without-vintage-bump"
_LOCK_NOT_REFRESHED = "lock-not-refreshed"
_VINTAGE_BACKWARDS = "vintage-moved-backwards"
_VINTAGE_NOT_DATE = "vintage-not-iso-date"


@dataclass(frozen=True, slots=True)
class PricebookSpec:
    """Where one pricebook's rate table and vintage constant live."""

    name: str
    path: str
    table: str
    vintage: str
    record: str

    def __post_init__(self) -> None:
        # Every field is quoted in diagnostics and used as a lock key, so none may be blank.
        if not all((self.name, self.path, self.table, self.vintage, self.record)):
            raise ValueError(f"PricebookSpec needs every field, got {self!r}.")


_PRICEBOOKS = (
    PricebookSpec(name="model", path="vidbyte/lib/registries/pricing.py", table="PROVIDER_PRICING", vintage="PRICING_AS_OF", record="ModelPricing"),
    PricebookSpec(name="operation", path="vidbyte/lib/registries/operation_pricing.py", table="OPERATION_PRICING", vintage="OPERATION_PRICING_AS_OF", record="OperationPricing"),
)


@dataclass(frozen=True, slots=True)
class PricebookSnapshot:
    """The current vintage and per-entry rate digests of one pricebook."""

    spec: PricebookSpec
    vintage: str
    vintage_line: int
    entries: dict[str, str]
    entry_lines: dict[str, int]

    def __post_init__(self) -> None:
        # A pricebook with no priced entry means the reader lost the table, which must fail closed.
        if not self.entries:
            raise ValueError(f"PricebookSnapshot for {self.spec.path}:{self.spec.table} has no rate entries; the table shape changed.")
        if self.vintage_line < 1:
            raise ValueError(f"PricebookSnapshot.vintage_line must be positive, got {self.vintage_line}.")

    def fingerprint(self) -> str:
        # One digest over every sorted entry digest, so any rate change moves it.
        return Fingerprint.of_entries(self.entries)


@dataclass(frozen=True, slots=True)
class VintageDrift:
    """How one pricebook disagrees with its lock entry."""

    snapshot: PricebookSnapshot
    kind: str
    locked_vintage: str
    changed: tuple[str, ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]

    def __post_init__(self) -> None:
        # The kind selects the repair, so it must be one the diagnostic knows how to explain.
        if self.kind not in {_CHANGED_WITHOUT_BUMP, _LOCK_NOT_REFRESHED, _VINTAGE_BACKWARDS, _VINTAGE_NOT_DATE}:
            raise ValueError(f"VintageDrift.kind {self.kind!r} is not a known C010 drift kind.")


class Fingerprint:
    """Hashes canonical rate entries deterministically."""

    @staticmethod
    def of_value(value: object) -> str:
        # A short digest of one entry's canonical JSON.
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]

    @staticmethod
    def of_entries(entries: dict[str, str]) -> str:
        # A digest over the sorted key=digest lines of a whole table.
        body = "\n".join(f"{key}={entries[key]}" for key in sorted(entries))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


class ModuleBindings:
    """Finds module-level bindings and dataclass fields in one parsed pricebook module."""

    @staticmethod
    def targets(node: ast.stmt) -> list[tuple[str, ast.expr]]:
        # (name, value) pairs bound by one module-level assignment, annotated or not.
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            return [(node.target.id, node.value)]
        if isinstance(node, ast.Assign):
            return [(target.id, node.value) for target in node.targets if isinstance(target, ast.Name)]
        return []

    @staticmethod
    def constants(tree: ast.Module) -> dict[str, ast.expr]:
        # Every module-level name with its bound expression, so rate tables can reference them.
        return {name: value for node in tree.body for name, value in ModuleBindings.targets(node)}

    @staticmethod
    def line_of(tree: ast.Module, name: str) -> int:
        # The line of the module-level statement that binds `name`, or 0 when nothing binds it.
        return next((node.lineno for node in tree.body for bound, _value in ModuleBindings.targets(node) if bound == name), 0)

    @staticmethod
    def record_fields(tree: ast.Module, record: str) -> list[tuple[str, ast.expr | None]]:
        # The rate dataclass's instance fields in declaration order with their defaults, so omitted keywords still count.
        node = next((item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == record), None)
        if node is None:
            return []
        return [(item.target.id, item.value) for item in node.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and "ClassVar" not in ast.unparse(item.annotation)]

    @staticmethod
    def key_text(key: ast.expr | None) -> str:
        # ModelProvider.OPENAI -> OPENAI; "gpt-5.6-sol" -> itself; ("search", "exa", "auto") -> search/exa/auto.
        if isinstance(key, ast.Attribute):
            return key.attr
        if isinstance(key, ast.Constant):
            return str(key.value)
        if isinstance(key, ast.Tuple):
            return "/".join(str(item.value) if isinstance(item, ast.Constant) else ast.unparse(item) for item in key.elts)
        return ast.unparse(key) if key is not None else "**"


class LiteralResolver:
    """Evaluates a rate argument to plain JSON data, following module-level rate constants."""

    def __init__(self, constants: dict[str, ast.expr]) -> None:
        # Binds the module's constants so `tier_rates=OPENAI_GPT56_TIER_RATES["gpt-5.6-sol"]` resolves to its numbers.
        self.constants = constants

    def resolve(self, node: ast.expr | None) -> object:
        # Literals become data with every integer as a float (5 == 5.0); a constant or a constant subscript is followed; anything else is fingerprinted by its source text.
        if node is None:
            return {"$required": True}
        if isinstance(node, ast.Name) and node.id in self.constants:
            return self.resolve(self.constants[node.id])
        table = self.constants.get(node.value.id) if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) else None
        if isinstance(node, ast.Subscript) and isinstance(table, ast.Dict) and isinstance(node.slice, ast.Constant):
            match = next((value for key, value in zip(table.keys, table.values, strict=True) if isinstance(key, ast.Constant) and key.value == node.slice.value), None)
            if match is not None:
                return self.resolve(match)
        try:
            value = ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return {"$expr": ast.unparse(node)}
        return json.loads(json.dumps(value, default=str), parse_int=float)


class RateTableReader:
    """Turns one pricebook module's literal table into canonical, default-filled rate entries."""

    def __init__(self, source: SourceFile, spec: PricebookSpec) -> None:
        # Binds the parsed module, its module-level constants, and a resolver over them.
        if source.tree is None:
            raise RuntimeError(f"C010 cannot parse {spec.path} ({source.parse_error}); fix the syntax error first.")
        self.tree = source.tree
        self.spec = spec
        self.constants = ModuleBindings.constants(source.tree)
        self.resolver = LiteralResolver(self.constants)

    def snapshot(self) -> PricebookSnapshot:
        # Read the vintage literal and its line, then digest every entry of the rate table.
        vintage = self.constants.get(self.spec.vintage)
        table = self.constants.get(self.spec.table)
        fields = ModuleBindings.record_fields(self.tree, self.spec.record)
        if vintage is None or not isinstance(table, ast.Dict) or not fields:
            raise RuntimeError(f"C010 needs `{self.spec.vintage} = \"YYYY-MM-DD\"`, a literal `{self.spec.table}` dict, and the `{self.spec.record}` dataclass in {self.spec.path}; update _PRICEBOOKS if the pricebook moved.")
        vintage_text = vintage.value if isinstance(vintage, ast.Constant) and isinstance(vintage.value, str) else ast.unparse(vintage)
        entries: dict[str, str] = {}
        lines: dict[str, int] = {}
        for key, node in self._entries(table, ()):
            entries[key] = Fingerprint.of_value(self._canonical(node, fields))
            lines[key] = node.lineno
        return PricebookSnapshot(spec=self.spec, vintage=vintage_text, vintage_line=ModuleBindings.line_of(self.tree, self.spec.vintage), entries=entries, entry_lines=lines)

    def _entries(self, table: ast.Dict, prefix: tuple[str, ...]) -> list[tuple[str, ast.expr]]:
        # Walks nested dicts down to each entry, naming it by its key path (OPENAI/gpt-5.6-sol, search/exa/auto).
        found: list[tuple[str, ast.expr]] = []
        for key, value in zip(table.keys, table.values, strict=True):
            path = (*prefix, ModuleBindings.key_text(key))
            if isinstance(value, ast.Dict):
                found.extend(self._entries(value, path))
            else:
                found.append(("/".join(path), value))
        return found

    def _canonical(self, node: ast.expr, fields: list[tuple[str, ast.expr | None]]) -> dict[str, object]:
        # Every field of the record as it takes effect (positional, keyword, else the dataclass default); a non-record entry by its resolved value.
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == self.spec.record):
            return {"$entry": self.resolver.resolve(node)}
        given: dict[str, ast.expr | None] = dict(fields)
        given.update({name: argument for (name, _default), argument in zip(fields, node.args, strict=False)})
        given.update({keyword.arg: keyword.value for keyword in node.keywords if keyword.arg is not None})
        canonical: dict[str, object] = {name: self.resolver.resolve(value) for name, value in given.items()}
        unpacked = [ast.unparse(keyword.value) for keyword in node.keywords if keyword.arg is None]
        if unpacked:
            canonical["**"] = unpacked
        return canonical


class LockStore:
    """Reads, verifies, and writes lint/pricebook_vintage_lock.json."""

    def __init__(self, root: Path) -> None:
        # The lock lives at a fixed path under the repository root the catalogue reads.
        self.path = root / LOCK_PATH

    def load(self) -> dict[str, dict[str, object]]:
        # Fails closed on a missing, malformed, or hand-edited lock, naming the one command that rebuilds it.
        if not self.path.is_file():
            raise RuntimeError(f"C010 lock {LOCK_PATH} is missing. Restore it from git, or create it with `{REFRESH_COMMAND}` only when bootstrapping a new pricebook.")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"C010 lock {LOCK_PATH} is not valid JSON ({exc}). Restore it from git; never edit it by hand.") from exc
        books = payload.get("pricebooks") if isinstance(payload, dict) and payload.get("schema_version") == _SCHEMA_VERSION else None
        if not isinstance(books, dict) or set(books) != {spec.name for spec in _PRICEBOOKS}:
            raise RuntimeError(f"C010 lock {LOCK_PATH} must have schema_version {_SCHEMA_VERSION} and one section per pricebook {[spec.name for spec in _PRICEBOOKS]}. Restore it from git.")
        for name, book in books.items():
            entries = book.get("entries") if isinstance(book, dict) else None
            if not isinstance(entries, dict) or not isinstance(book.get("vintage"), str) or Fingerprint.of_entries(entries) != book.get("fingerprint"):
                raise RuntimeError(f"C010 lock section {name!r} in {LOCK_PATH} does not match its own fingerprint, so it was edited by hand. Restore it from git and rerun `{REFRESH_COMMAND}` after bumping the vintage.")
        return books

    def write(self, snapshots: list[PricebookSnapshot]) -> None:
        # Rewrites the whole lock deterministically from the current source snapshots.
        payload = {
            "about": f"C010 pricebook vintage lock: the rates each vintage stands for. Written only by `{REFRESH_COMMAND}`, which refuses changed rates under an unchanged vintage. Do not edit by hand; the SDK never reads this file.",
            "schema_version": _SCHEMA_VERSION,
            "pricebooks": {snapshot.spec.name: {"source": snapshot.spec.path, "table": snapshot.spec.table, "vintage_constant": snapshot.spec.vintage, "vintage": snapshot.vintage, "fingerprint": snapshot.fingerprint(), "entries": dict(sorted(snapshot.entries.items()))} for snapshot in snapshots},
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class VintageJudge:
    """Decides whether one pricebook agrees with its locked vintage and rates."""

    def judge(self, snapshot: PricebookSnapshot, locked: dict[str, object]) -> VintageDrift | None:
        # A vintage must be an ISO date; equal vintages need equal rates; a moved vintage needs a refreshed lock.
        locked_vintage = str(locked["vintage"])
        locked_entries = locked["entries"] if isinstance(locked["entries"], dict) else {}
        changed = tuple(sorted(key for key in snapshot.entries.keys() & locked_entries.keys() if snapshot.entries[key] != locked_entries[key]))
        added = tuple(sorted(snapshot.entries.keys() - locked_entries.keys()))
        removed = tuple(sorted(locked_entries.keys() - snapshot.entries.keys()))
        rates_moved = bool(changed or added or removed)
        if not self.is_iso_date(snapshot.vintage):
            kind = _VINTAGE_NOT_DATE
        elif snapshot.vintage == locked_vintage:
            kind = _CHANGED_WITHOUT_BUMP if rates_moved else ""
        else:
            kind = _VINTAGE_BACKWARDS if snapshot.vintage < locked_vintage else _LOCK_NOT_REFRESHED
        return VintageDrift(snapshot=snapshot, kind=kind, locked_vintage=locked_vintage, changed=changed, added=added, removed=removed) if kind else None

    @staticmethod
    def is_iso_date(value: str) -> bool:
        # YYYY-MM-DD and a real calendar date; ISO strings then sort chronologically.
        if not _ISO_DATE.match(value):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True


class PricebookReader:
    """Builds the current snapshot of every registered pricebook from the source catalogue."""

    @staticmethod
    def snapshots(catalog: SourceCatalog) -> list[PricebookSnapshot]:
        # Fails closed when a pricebook module is no longer tracked.
        files = {source.rel: source for source in catalog.python_files()}
        missing = [spec.path for spec in _PRICEBOOKS if spec.path not in files]
        if missing:
            raise RuntimeError(f"C010 requires the tracked pricebook modules {missing}; restore them or update _PRICEBOOKS.")
        return [RateTableReader(files[spec.path], spec).snapshot() for spec in _PRICEBOOKS]


class PricebookVintageBumpRule(Rule):
    """Requires a pricebook vintage to move, and the lock to be refreshed, whenever its rates change."""

    id = "C010"
    name = "pricebook-vintage-bump"
    severity = "blocking"
    summary = "Each SDK pricebook (PROVIDER_PRICING with PRICING_AS_OF, OPERATION_PRICING with OPERATION_PRICING_AS_OF) has a vintage that names the rates in force. When any effective rate entry is added, removed, or changed, the vintage must move to the later date the rates were verified, and lint/pricebook_vintage_lock.json must be refreshed in the same change; a moved vintage with a stale lock, a vintage moved backwards, or a vintage that is not an ISO date also fails."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Compare each pricebook's current vintage and rate digests with its locked section.
        locked = LockStore(catalog.root).load()
        judge = VintageJudge()
        findings: list[Finding] = []
        for snapshot in PricebookReader.snapshots(catalog):
            drift = judge.judge(snapshot, locked[snapshot.spec.name])
            if drift is not None:
                findings.append(self._finding(drift, catalog))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # One explanation per drift kind, always ending in the same bump-then-refresh sequence.
        extra = finding.extra
        return Diagnostic(
            what_happened=self._what(finding),
            why_blocked=f"`{extra['vintage_constant']}` is the vintage of {extra['path']}: its comment says the rates were verified against the official pricing pages on that date, and the Vidbyte backend persists `vidbyte-sdk-models-{{PRICING_AS_OF}}+operations-{{OPERATION_PRICING_AS_OF}}` as each run's pricebook version (backend/lib/enums/research.py ResearchPricebookVersion), and refuses to resume a run whose stored version differs (backend/lib/usage/ledger.py:161; field-guide vidbyte research-usage-tracking.md:32, \"Only the active SDK model and operation pricebook vintages may resume a run\"). New rates under an old vintage make two different pricebooks indistinguishable, so a run started on the old rates resumes and settles on the new ones. This has happened twice: PR #438 added the TypeSafe rates (checked 2026-09-21) under PRICING_AS_OF 2026-07-30, and a71fac66 added the Exa highlights rates without moving OPERATION_PRICING_AS_OF.",
            how_to_fix=self._repair(extra),
            correct_examples=("vidbyte/lib/registries/operation_pricing.py OPERATION_PRICING_AS_OF - commit 7e5683b9 corrected the Parallel rates and moved the vintage 2026-08-03 -> 2026-08-08 in the same change.", "vidbyte/lib/registries/pricing.py PRICING_AS_OF - commit c6af16e0 added the GPT-5.6 tier rates and moved the vintage 2026-07-22 -> 2026-07-30 in the same change."),
            will_not_work=(f"Running `{REFRESH_COMMAND}` without moving the vintage: it refuses to lock changed rates under an unchanged vintage.", f"Editing {LOCK_PATH} by hand: its fingerprint no longer matches its entries and C010 fails closed.", "Moving the vintage to an earlier or arbitrary date: it must be the later date you actually re-read the vendor pages.", "Raising C010's baseline in lint/baseline.json: the baseline is 0 and each finding is a pricebook whose vintage misidentifies its rates."),
            verify=f"{self.verify_command()} && python -m pytest tests/test_agent_pricing.py -q",
        )

    @staticmethod
    def _finding(drift: VintageDrift, catalog: SourceCatalog) -> Finding:
        # Anchors at the vintage constant, which every repair touches, and stores the entry facts.
        snapshot = drift.snapshot
        lines = snapshot.entry_lines
        listed = [f"{key} ({snapshot.spec.path}:{lines[key]})" for key in drift.changed + drift.added][:_LISTED_ENTRIES]
        removed_more = f", and {len(drift.removed) - _LISTED_ENTRIES} more" if len(drift.removed) > _LISTED_ENTRIES else ""
        source = next(item for item in catalog.python_files() if item.rel == snapshot.spec.path)
        facts = {"kind": drift.kind, "path": snapshot.spec.path, "table": snapshot.spec.table, "vintage_constant": snapshot.spec.vintage, "vintage": snapshot.vintage, "locked_vintage": drift.locked_vintage}
        counts = {"changed": str(len(drift.changed)), "added": str(len(drift.added)), "removed": str(len(drift.removed)), "rates_moved": "yes" if drift.changed or drift.added or drift.removed else "no"}
        entries = {"listed": "; ".join(listed), "unlisted": str(len(drift.changed) + len(drift.added) - len(listed)), "removed_keys": ", ".join(drift.removed[:_LISTED_ENTRIES]) + removed_more}
        return Finding(rule_id=PricebookVintageBumpRule.id, rel_path=snapshot.spec.path, line=snapshot.vintage_line, source_line=source.line_at(snapshot.vintage_line), symbol=f"{snapshot.spec.vintage}={snapshot.vintage}", extra={**facts, **counts, **entries})

    @staticmethod
    def _what(finding: Finding) -> str:
        # States the vintage facts first, then whether and exactly which rate entries moved.
        extra = finding.extra
        head = f"{finding.location()} `{extra['vintage_constant']} = \"{extra['vintage']}\"`"
        more = f", and {extra['unlisted']} more" if int(extra["unlisted"]) > 0 else ""
        entries = f" Changed or added: {extra['listed']}{more}." if extra["listed"] else ""
        removed = f" Removed: {extra['removed_keys']}." if extra["removed_keys"] else ""
        diff = f"`{extra['table']}` differs from the rates locked for {extra['locked_vintage']} ({extra['changed']} changed, {extra['added']} added, {extra['removed']} removed).{entries}{removed}"
        rates = f" {diff}" if extra["rates_moved"] == "yes" else f" `{extra['table']}` still matches the rates locked for {extra['locked_vintage']}."
        if extra["kind"] == _CHANGED_WITHOUT_BUMP:
            return f"{head} is still the locked vintage, but {diff}"
        if extra["kind"] == _LOCK_NOT_REFRESHED:
            return f"{head} moved forward from the locked vintage {extra['locked_vintage']}, but {LOCK_PATH} was not refreshed.{rates}"
        if extra["kind"] == _VINTAGE_BACKWARDS:
            return f"{head} is earlier than the locked vintage {extra['locked_vintage']}, and a vintage only moves forward.{rates}"
        return f"{head} is not an ISO calendar date (YYYY-MM-DD), so it cannot be ordered against the locked vintage {extra['locked_vintage']}.{rates}"

    @staticmethod
    def _repair(extra: dict[str, str]) -> str:
        # The same three steps for every kind, with the first step adapted to what is wrong.
        target = f"a later date (after {extra['locked_vintage']}) on which you re-verified every changed rate" if extra["rates_moved"] == "yes" else f"the locked date {extra['locked_vintage']}, or a later date on which you re-verified the whole table"
        first = {
            _CHANGED_WITHOUT_BUMP: f"1. Re-read the vendor pricing page cited above each changed entry in {extra['path']}, confirm every new number against its column header, then set `{extra['vintage_constant']}` to that verification date (YYYY-MM-DD, later than {extra['locked_vintage']}). If the rate edit was not intended, revert it instead and stop here.",
            _LOCK_NOT_REFRESHED: f"1. Confirm `{extra['vintage_constant']} = \"{extra['vintage']}\"` is the date you re-verified the rates in {extra['path']}; if it is not, correct it to that date (still later than {extra['locked_vintage']}).",
            _VINTAGE_BACKWARDS: f"1. Set `{extra['vintage_constant']}` to {target}.",
            _VINTAGE_NOT_DATE: f"1. Write `{extra['vintage_constant']}` as one plain ISO date string literal (`{extra['vintage_constant']}: str = \"YYYY-MM-DD\"`) set to {target}.",
        }[extra["kind"]]
        return "\n".join((
            first,
            f"2. From the repository root, run `{REFRESH_COMMAND}`. It rewrites {LOCK_PATH} with the new vintage and rate digests (or reports that nothing needs refreshing), and refuses while a rate change is still paired with an unchanged, earlier, or non-ISO vintage.",
            f"3. Commit {extra['path']} and {LOCK_PATH} together, naming the vendor pages and the new vintage in the commit message, because the backend treats a new vintage as a new pricebook version for resumable runs.",
        ))


class LockRefresher:
    """Writes the lock from source, refusing any rate change that kept its vintage."""

    def refresh(self, catalog: SourceCatalog) -> tuple[int, str]:
        # Bootstrap a missing lock; otherwise judge every pricebook and write only when each one is legitimately locked.
        store = LockStore(catalog.root)
        snapshots = PricebookReader.snapshots(catalog)
        if not store.path.is_file():
            store.write(snapshots)
            return 0, f"Created {LOCK_PATH} for {', '.join(f'{item.spec.name} {item.vintage}' for item in snapshots)}."
        locked = store.load()
        judge = VintageJudge()
        drifts = [drift for drift in (judge.judge(snapshot, locked[snapshot.spec.name]) for snapshot in snapshots) if drift is not None]
        refused = [drift for drift in drifts if drift.kind != _LOCK_NOT_REFRESHED]
        if refused:
            reasons = "; ".join(f"{drift.snapshot.spec.vintage}={drift.snapshot.vintage!r} ({drift.kind}, locked {drift.locked_vintage})" for drift in refused)
            return 1, f"Refusing to refresh {LOCK_PATH}: {reasons}. Move each vintage to the later date you re-verified its rates, then rerun."
        if not drifts:
            return 0, f"{LOCK_PATH} already matches every pricebook; nothing to refresh."
        store.write(snapshots)
        return 0, f"Refreshed {LOCK_PATH}: {', '.join(f'{drift.snapshot.spec.vintage} {drift.locked_vintage} -> {drift.snapshot.vintage}' for drift in drifts)}."


def main(argv: list[str] | None = None) -> int:
    # Implements the one supported way to update the lock.
    parser = argparse.ArgumentParser(description="Maintain the C010 pricebook vintage lock.")
    parser.add_argument("--refresh-lock", action="store_true", help=f"Rewrite {LOCK_PATH} after moving a pricebook vintage.")
    args = parser.parse_args(argv)
    if not args.refresh_lock:
        parser.print_help()
        return 2
    status, message = LockRefresher().refresh(SourceCatalog())
    print(message, file=sys.stderr if status else sys.stdout)
    return status


RULE = PricebookVintageBumpRule()

if __name__ == "__main__":
    raise SystemExit(main())
