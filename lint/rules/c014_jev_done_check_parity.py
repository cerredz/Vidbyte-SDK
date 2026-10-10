"""FILE: lint/rules/c014_jev_done_check_parity.py

PURPOSE: Detect a JevDoneCheck member that lacks one of the parts the done-check pipeline dispatches on, or a done-question module with no member.
ROLE IN CODEBASE: Enforces C014 so a new or renamed done check cannot silently ask nothing, fail open, or crash mid-run because one of its registry entries, handoff section, or handler-map entries was forgotten.
ARCHITECTURE NOTE: Static cross-file AST parity over the JevDoneCheck and JevDoneQuestionKey enums, the vidbyte/lib/jev/done/ question modules and package exports, the JevDoneRegistry tables, JevHandoff._SECTIONS (including its `{**_SECTIONS, ...}` re-assignments), and the `handlers` maps in JevRunState._section, JevRunState._judge, and JevDoneContinuation._explain. JevRunState._SECTIONS is deliberately not required: it holds only request-derived checks, and tests/test_jev_done.py pins its explicit subset.
FUNCTION INVENTORY: DoneLiterals reads enums, tables, imports, and handler maps; DoneParityAnalyzer coordinates the per-member comparison; JevDoneCheckParityRule reports and explains.
COMMON MODIFICATION PATTERNS: When a dispatcher or table moves, change the path and owner constants together; when a new required part joins the skills/jev-continuation checklist, add one Part and its consequence text.
WHAT NOT TO DO: Do not import vidbyte, require a run-state section for post-run checks, or treat a missing table or handler map as zero findings.
KNOWN EDGE CASES: A question key belongs to a check when its value equals the check value (FAITHFUL_SCOPE) or starts with the check value and a dot (CUMULATIVE_OBLIGATION_FULFILLED's member name differs from its check). `__init__.py`, `done.py`, and `state.py` are shared done-package infrastructure, not question modules.
RELATED DOCS: docs/design/lint-sdk-jev-packaging-async.md; skills/jev-continuation/SKILL.md (checklist and important files); field-guide/vidbyte-sdk/jev-capability-layout.md.
TESTS: python lint/run.py --rule C014; fixture and mutation results are recorded in the S3 pull request body.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

ENUM_FILE = "vidbyte/lib/enums/jev.py"
DONE_DIR = "vidbyte/lib/jev/done/"
DONE_PACKAGE = "vidbyte.lib.jev.done"
REGISTRY_FILE = "vidbyte/lib/jev/done/done.py"
EXPORT_FILE = "vidbyte/lib/jev/done/__init__.py"
HANDOFF_FILE = "vidbyte/agents/jev/done/handoff.py"
RUN_STATE_FILE = "vidbyte/agents/jev/done/run_state.py"
CONTINUATION_FILE = "vidbyte/agents/jev/continuation/done.py"
CHECK_ENUM = "JevDoneCheck"
KEY_ENUM = "JevDoneQuestionKey"
REGISTRY_CLASS = "JevDoneRegistry"
_REGISTRY_TABLES = ("_questions", "_thresholds", "_descriptions")
_INVENTORY_TABLE = "_inventory_questions"
_INFRASTRUCTURE = frozenset({"__init__", "done", "state"})
# (file, class, method) of every handler map a done check needs an entry in.
_DISPATCHERS = ((RUN_STATE_FILE, "JevRunState", "_section"), (RUN_STATE_FILE, "JevRunState", "_judge"), (CONTINUATION_FILE, "JevDoneContinuation", "_explain"))
_MODULE = "module-missing"
_KEY = "question-key-missing"
_REGISTRY = "registry-entry-missing"
_MISWIRED = "question-miswired"
_EXPORT = "question-not-exported"
_HANDOFF = "handoff-section-missing"
_DISPATCH = "dispatch-missing"
_ORPHAN = "orphan-module"
_KINDS = (_MODULE, _KEY, _REGISTRY, _MISWIRED, _EXPORT, _HANDOFF, _DISPATCH, _ORPHAN)
# What breaks at run time when each part is missing; quoted in the diagnostic.
_CONSEQUENCES = {
    "_questions": "JevDoneRegistry.validate calls questions(check) for every enabled check, so enabling this check raises ConfigurationError (\"has no registered question\") when the agent is built.",
    "_thresholds": "JevDoneRegistry.validate calls threshold(check) for every enabled check, so enabling this check raises ConfigurationError when the agent is built, and JevRunState._failed_questions cannot score it.",
    "_descriptions": "JevDoneRegistry.validate checks description coverage on every call, so every JevAgent with any done check enabled raises ConfigurationError (\"Jev done gate descriptions must cover every check exactly once\") at construction, and the continuation cannot explain the gate.",
    "_section": "JevRunState._section falls back to `({}, ())` for an unregistered check, so the check adds no state and no questions to the one Jev request; its scorer then finds no answers and the check fails open on every finish attempt, silently.",
    "_judge": "JevRunState._judge returns `JevDoneResult(check=check, score=None, available=False)` for an unregistered check, so the check is reported unavailable and fails open on every finish attempt, silently.",
    "_explain": "JevDoneContinuation._explain indexes `handlers[result.check]`, so the first time this check fails the continuation raises KeyError while building the message for the main agent, mid-run.",
    _HANDOFF: "JevHandoff.schema reads `cls._SECTIONS[check]` for every enabled check, so enabling this check raises KeyError when the handoff schema is built, and the handoff never compiles its evidence.",
    _MODULE: "the check's questions have no home in the one done-question folder, so they end up defined somewhere else (often the agents layer, which must hold no question text) and JevDoneRegistry cannot import them from the module the skill names.",
    _KEY: "the check's questions cannot be named with the check's own prefix, so their answers come back under names that belong to no check (or to another check) and the scorer reads the wrong answers or none.",
    _MISWIRED: "a question registered for this check is either defined in another check's module or keyed by another check's question key, so its answers are filed under the wrong check and that check's scorer and failed-question text read them.",
    _EXPORT: "vidbyte.lib.jev.done does not export the question, so tests and callers that pin the question contract through the package (the package header says tests import the question dataclasses from it) cannot reach it.",
    _ORPHAN: "the module holds done questions that no JevDoneCheck member can enable, which is dead question text left behind by a removed or renamed check, or a new check whose enum member was never added.",
}


@dataclass(frozen=True, slots=True)
class Gap:
    """One missing or miswired part of one done check, anchored where the repair goes."""

    kind: str
    member: str
    part: str
    rel: str
    line: int
    detail: str

    def __post_init__(self) -> None:
        # The kind picks the repair text, and the anchor must be a real tracked line.
        if self.kind not in _KINDS:
            raise ValueError(f"Gap.kind must be one of {_KINDS}, got {self.kind!r}.")
        if not self.member or not self.part or not self.rel or self.line < 1:
            raise ValueError(f"Gap needs a member, part, path, and positive line, got {self.member!r}/{self.part!r}/{self.rel!r}/{self.line}.")


@dataclass(frozen=True, slots=True)
class KeyedMap:
    """The JevDoneCheck members one table or handler map is keyed by, with the line that declares it."""

    members: frozenset[str]
    line: int
    values: dict[str, ast.expr]


class DoneLiterals:
    """Reads the literal enums, registry tables, imports, and handler maps the done-check contract is declared with."""

    def __init__(self, files: dict[str, SourceFile]) -> None:
        # Binds the parsed catalogue once for every lookup.
        self.files = files

    def tree(self, rel: str) -> ast.Module:
        # Fails closed: a missing or unparsable contract file is an analyzer error, never zero findings.
        source = self.files.get(rel)
        if source is None or source.tree is None:
            raise RuntimeError(f"C014 requires the tracked, parsable file {rel}; restore it or update the rule's path constants if the done-check pipeline moved.")
        return source.tree

    def enum(self, class_name: str) -> dict[str, tuple[str, int]]:
        # Member name -> (string value, line) for one str Enum class in ENUM_FILE.
        found = self.class_def(self.tree(ENUM_FILE), class_name)
        members = {} if found is None else {item.targets[0].id: (item.value.value, item.lineno) for item in found.body if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)}
        if not members:
            raise RuntimeError(f"C014 could not read the members of {class_name} in {ENUM_FILE}; update ENUM_FILE if the enum moved.")
        return members

    @staticmethod
    def class_def(tree: ast.Module, name: str) -> ast.ClassDef | None:
        # The module-level class with this name.
        return next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name), None)

    @staticmethod
    def members(node: ast.Dict) -> dict[str, ast.expr]:
        # `JevDoneCheck.X: value` entries of one dict display, keyed by member name.
        return {key.attr: value for key, value in zip(node.keys, node.values, strict=True) if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name) and key.value.id == CHECK_ENUM}

    @classmethod
    def mapping(cls, value: ast.expr | None) -> ast.Dict | None:
        # A dict display, bare or wrapped in `MappingProxyType(...)`.
        if isinstance(value, ast.Call) and len(value.args) == 1:
            value = value.args[0]
        return value if isinstance(value, ast.Dict) else None

    def class_table(self, rel: str, class_name: str, name: str) -> KeyedMap:
        # A class attribute's members, following `name = MappingProxyType({**name, ...})` re-assignments in order.
        found = self.class_def(self.tree(rel), class_name)
        members: dict[str, ast.expr] = {}
        line = 0
        for node in [] if found is None else found.body:
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None
            table = self.mapping(node.value) if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(target, ast.Name) and target.id == name else None
            if table is None:
                continue
            keeps = any(key is None and isinstance(value, ast.Name) and value.id == name for key, value in zip(table.keys, table.values, strict=True))
            members = {**(members if keeps else {}), **self.members(table)}
            line = node.lineno
        if not line:
            raise RuntimeError(f"C014 could not read the literal {class_name}.{name} table in {rel}; update the rule if it moved or stopped being a dict display.")
        return KeyedMap(members=frozenset(members), line=line, values=members)

    def handler_map(self, rel: str, class_name: str, method: str) -> KeyedMap:
        # The literal `handlers = {...}` dict inside one method.
        found = self.class_def(self.tree(rel), class_name)
        function = None if found is None else next((node for node in found.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method), None)
        for node in [] if function is None else ast.walk(function):
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None
            if isinstance(target, ast.Name) and target.id == "handlers" and isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict):
                members = self.members(node.value)
                return KeyedMap(members=frozenset(members), line=node.lineno, values=members)
        raise RuntimeError(f"C014 could not read the `handlers` dispatch map in {class_name}.{method} ({rel}); update the rule if that dispatcher stopped being a literal handler map.")

    def import_sources(self, rel: str) -> dict[str, str]:
        # Imported name -> module stem for every `from vidbyte.lib.jev.done.<stem> import Name` in one file.
        sources: dict[str, str] = {}
        for node in self.tree(rel).body:
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(f"{DONE_PACKAGE}."):
                sources.update((alias.asname or alias.name, node.module.rsplit(".", 1)[-1]) for alias in node.names)
        return sources

    def exports(self) -> tuple[frozenset[str], int]:
        # The string entries of the done package's `__all__`, with its line.
        for node in self.tree(EXPORT_FILE).body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets) and isinstance(node.value, (ast.List, ast.Tuple)):
                return frozenset(item.value for item in node.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)), node.lineno
        raise RuntimeError(f"C014 could not read a literal __all__ in {EXPORT_FILE}; restore the done package's export list.")

    def question_key(self, stem: str, class_name: str) -> str | None:
        # The `key: JevDoneQuestionKey = JevDoneQuestionKey.X` member a question class declares in its module, or None.
        source = self.files.get(f"{DONE_DIR}{stem}.py")
        found = None if source is None or source.tree is None else self.class_def(source.tree, class_name)
        for node in [] if found is None else found.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "key" and isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name) and node.value.value.id == KEY_ENUM:
                return node.value.attr
        return None


class DoneParityAnalyzer:
    """Compares every JevDoneCheck member with each part the done-check pipeline needs."""

    def analyze(self, files: dict[str, SourceFile], tracked: tuple[str, ...]) -> list[Gap]:
        # Read the check vocabulary, its question keys, and the question modules in the done folder.
        literals = DoneLiterals(files)
        checks = literals.enum(CHECK_ENUM)
        keys = literals.enum(KEY_ENUM)
        modules = {rel[len(DONE_DIR):-3] for rel in tracked if rel.startswith(DONE_DIR) and rel.endswith(".py") and "/" not in rel[len(DONE_DIR):]}

        # Read the registry tables, the class each question entry constructs, and where done.py imports each class from.
        tables = {name: literals.class_table(REGISTRY_FILE, REGISTRY_CLASS, name) for name in (*_REGISTRY_TABLES, _INVENTORY_TABLE)}
        imported = literals.import_sources(REGISTRY_FILE)
        exported, export_line = literals.exports()

        # Read the handoff sections and the three handler maps every check dispatches through.
        handoff = literals.class_table(HANDOFF_FILE, "JevHandoff", "_SECTIONS")
        dispatchers = {(rel, owner, method): literals.handler_map(rel, owner, method) for rel, owner, method in _DISPATCHERS}

        # Compare each member with every part, then report question modules that no member owns.
        gaps: list[Gap] = []
        for member, (value, line) in checks.items():
            gaps.extend(self._structure(member, value, line, modules, keys))
            gaps.extend(Gap(_REGISTRY, member, name, REGISTRY_FILE, table.line, f"{REGISTRY_CLASS}.{name}") for name, table in tables.items() if name in _REGISTRY_TABLES and member not in table.members)
            gaps.extend(self._wiring(member, value, tables, imported, exported, export_line, keys, literals))
            if member not in handoff.members:
                gaps.append(Gap(_HANDOFF, member, _HANDOFF, HANDOFF_FILE, handoff.line, "JevHandoff._SECTIONS"))
            gaps.extend(Gap(_DISPATCH, member, method, rel, table.line, f"{owner}.{method}") for (rel, owner, method), table in dispatchers.items() if member not in table.members)
        owned = {value for value, _ in checks.values()}
        gaps.extend(Gap(_ORPHAN, stem, _ORPHAN, f"{DONE_DIR}{stem}.py", 1, stem) for stem in sorted(modules - owned - _INFRASTRUCTURE))
        return gaps

    @staticmethod
    def _structure(member: str, value: str, line: int, modules: set[str], keys: dict[str, tuple[str, int]]) -> Iterator[Gap]:
        # The check's own question module and at least one question key carrying its prefix.
        if value not in modules:
            yield Gap(_MODULE, member, _MODULE, ENUM_FILE, line, f"{DONE_DIR}{value}.py")
        if not any(belongs(key_value, value) for key_value, _ in keys.values()):
            yield Gap(_KEY, member, _KEY, ENUM_FILE, line, f"`{value}` or `{value}.<name>`")

    @staticmethod
    def _wiring(member: str, value: str, tables: dict[str, KeyedMap], imported: dict[str, str], exported: frozenset[str], export_line: int, keys: dict[str, tuple[str, int]], literals: DoneLiterals) -> Iterator[Gap]:
        # Every question class registered for the check comes from the check's module, carries the check's key, and is exported.
        for name in ("_questions", _INVENTORY_TABLE):
            table = tables[name]
            entry = table.values.get(member)
            calls = () if entry is None else entry.elts if isinstance(entry, ast.Tuple) else (entry,)
            for call in (item for item in calls if isinstance(item, ast.Call)):
                class_name = call.func.id if isinstance(call.func, ast.Name) else ast.unparse(call.func)
                stem = imported.get(class_name, "")
                key = literals.question_key(stem, class_name) if stem else None
                key_value = keys.get(key or "", ("", 0))[0]
                if stem != value:
                    yield Gap(_MISWIRED, member, class_name, REGISTRY_FILE, call.lineno, f"{class_name} is imported from {DONE_PACKAGE}.{stem or '<not a done module>'}, not {DONE_PACKAGE}.{value}")
                elif key is None:
                    yield Gap(_MISWIRED, member, class_name, REGISTRY_FILE, call.lineno, f"{class_name} declares no `key: {KEY_ENUM} = {KEY_ENUM}.<member>` in {DONE_DIR}{value}.py")
                elif not belongs(key_value, value):
                    yield Gap(_MISWIRED, member, class_name, REGISTRY_FILE, call.lineno, f"{class_name}.key is {KEY_ENUM}.{key} (`{key_value}`), which belongs to another check")
                if class_name not in exported:
                    yield Gap(_EXPORT, member, class_name, EXPORT_FILE, export_line, f"{class_name} is missing from __all__")


def belongs(key_value: str, check_value: str) -> bool:
    # A question key belongs to a check when it is the check value itself or the check value followed by a dot.
    return key_value == check_value or key_value.startswith(f"{check_value}.")


class JevDoneCheckParityRule(Rule):
    """Requires every JevDoneCheck member to have each part the done-check pipeline dispatches on."""

    id = "C014"
    name = "jev-done-check-parity"
    severity = "blocking"
    summary = "Every JevDoneCheck member has its question module in vidbyte/lib/jev/done/, a JevDoneQuestionKey with its prefix, JevDoneRegistry _questions/_thresholds/_descriptions entries whose question classes come from its own module with its own keys and are exported, a JevHandoff._SECTIONS entry, and entries in the JevRunState._section, JevRunState._judge, and JevDoneContinuation._explain handler maps; every done-question module belongs to a member."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # One finding per missing or miswired part, anchored at the table, map, enum member, or module that needs the edit.
        files = {source.rel: source for source in catalog.python_files()}
        gaps = DoneParityAnalyzer().analyze(files, catalog.tracked_paths())
        return [self._finding(gap, files) for gap in sorted(gaps, key=lambda item: (item.rel, item.line, item.member, item.part))]

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the member, the missing part, what breaks at run time, and the one edit that repairs it.
        extra = finding.extra
        kind, member, part = extra["kind"], extra["member"], extra["part"]
        consequence = _CONSEQUENCES.get(part, _CONSEQUENCES.get(kind, ""))
        return Diagnostic(
            what_happened=self._what(finding),
            why_blocked=f"A done check runs only when every part of the pipeline knows it: here, {consequence} The jev-continuation skill lists each part as a checklist step (skills/jev-continuation/SKILL.md section 3, steps 2, 4, 7, 8, 9, 10, 12, and 13), and the field guide records the owner's layout for a new check from the PR #452 and #470 reviews: a `_SECTIONS` entry in JevHandoff, plus a case (now a handler-map entry) in JevRunState._section and _judge and in JevDoneContinuation._explain (jev-capability-layout.md).",
            how_to_fix="\n".join((
                f"1. {self._repair(extra)}",
                "2. Follow the model of an existing check of the same shape end to end (MULTI_PART for request-derived items, CLAIMS for post-run items), so the new entry matches its neighbors' form.",
                f"3. Re-run `{self.verify_command()}`: it reports every other part of {CHECK_ENUM}.{member} that is still missing, so repeat steps 1 and 2 until it is clean.",
                "4. Run the focused done-check tests, which pin the handoff sections and gate descriptions against every member.",
            )),
            correct_examples=(
                f"{REGISTRY_FILE} {REGISTRY_CLASS} - JevDoneCheck.MULTI_PART has a _questions, _thresholds, and _descriptions entry, and MultiPartDeliveredQuestion is imported from {DONE_PACKAGE}.multi_part with key {KEY_ENUM}.MULTI_PART_DELIVERED.",
                f"{RUN_STATE_FILE} JevRunState._section and _judge, and {CONTINUATION_FILE} JevDoneContinuation._explain - each handler map has one entry per {CHECK_ENUM} member.",
                f"{HANDOFF_FILE} JevHandoff._SECTIONS - later checks extend the table with `_SECTIONS = MappingProxyType({{**_SECTIONS, JevDoneCheck.X: Payload}})`.",
            ),
            will_not_work=(
                "Adding a fallback such as `handlers.get(check, default)` or a try/except around the lookup: the check would still ask nothing, fail open, or explain nothing, just without an error.",
                f"Removing the {CHECK_ENUM} member to make the finding disappear while its questions stay registered: the parts and the vocabulary drift apart again.",
                "Raising C014's baseline in lint/baseline.json: each finding is a done check that cannot run, cannot fail, or crashes when it fails.",
            ),
            verify=f"{self.verify_command()} && python -m pytest tests/test_jev_done.py -q",
        )

    @staticmethod
    def _finding(gap: Gap, files: dict[str, SourceFile]) -> Finding:
        # Stores every quoted fact, so explain() never re-reads source.
        source = files.get(gap.rel)
        symbol = gap.member if gap.kind == _ORPHAN else f"{CHECK_ENUM}.{gap.member}"
        return Finding(rule_id=JevDoneCheckParityRule.id, rel_path=gap.rel, line=gap.line, source_line="" if source is None else source.line_at(gap.line), symbol=symbol, extra={"kind": gap.kind, "member": gap.member, "part": gap.part, "detail": gap.detail})

    @staticmethod
    def _what(finding: Finding) -> str:
        # One sentence per kind, quoting the member and the exact part that is missing or miswired.
        extra = finding.extra
        kind, member, detail = extra["kind"], extra["member"], extra["detail"]
        head = f"{finding.location()}: {CHECK_ENUM}.{member}"
        sentences = {
            _MODULE: f"{head} has no question module; {detail} is not tracked.",
            _KEY: f"{head} has no question key: no {KEY_ENUM} member has the value {detail}.",
            _REGISTRY: f"{head} has no entry in {detail}.",
            _MISWIRED: f"{head} registers a question that is wired to the wrong check: {detail}.",
            _EXPORT: f"{head} registers a question the done package does not export: {detail} in {EXPORT_FILE}.",
            _HANDOFF: f"{head} has no entry in {detail}, the handoff's evidence sections.",
            _DISPATCH: f"{head} has no entry in the `handlers` map of {detail}.",
            _ORPHAN: f"{finding.location()}: the done-question module {DONE_DIR}{member}.py belongs to no {CHECK_ENUM} member (no member has the value `{member}`).",
        }
        return sentences[kind]

    @staticmethod
    def _repair(extra: dict[str, str]) -> str:
        # The one edit that adds the missing part, in the file that owns it.
        kind, member, part = extra["kind"], extra["member"], extra["part"]
        repairs = {
            _MODULE: f"Create {extra['detail']} with the check's JevDoneQuestion subclasses (one per question, laid out like multi_part.py and following skills/asking-jev-questions/SKILL.md), and import them in {REGISTRY_FILE} from that module.",
            _KEY: f"Add `{member}_<NAME> = \"<check value>.<name>\"` to {KEY_ENUM} in {ENUM_FILE} for each of the check's questions, and set each question class's `key` to it.",
            _REGISTRY: f"Add `{CHECK_ENUM}.{member}: ...` to {REGISTRY_CLASS}.{part} in {REGISTRY_FILE}: the check's question instances for _questions, its JEV_<CHECK>_THRESHOLD constant from vidbyte/lib/constants/jev.py for _thresholds, or its JevDoneGateDescription for _descriptions.",
            _MISWIRED: f"Define {part} in the check's own module and import it in {REGISTRY_FILE} from there, with `key: {KEY_ENUM} = {KEY_ENUM}.<one of this check's keys>`; if it belongs to another check, register it under that check instead.",
            _EXPORT: f"Import {part} in {EXPORT_FILE} from its done module and add \"{part}\" to `__all__`.",
            _HANDOFF: f"Add `{CHECK_ENUM}.{member}: <its evidence section payload>` to JevHandoff._SECTIONS in {HANDOFF_FILE}, by a new `_SECTIONS = MappingProxyType({{**_SECTIONS, ...}})` line like its neighbors, and convert the section in JevHandoff._record.",
            _DISPATCH: f"Write the typed helper for {CHECK_ENUM}.{member} and register it as `{CHECK_ENUM}.{member}: self._<helper>` in the `handlers` map of {extra['detail']}.",
            _ORPHAN: f"Either add the {CHECK_ENUM} member whose value is `{member}` with every part C014 checks, or delete {DONE_DIR}{member}.py and its registry and export references if its check was removed or renamed.",
        }
        return repairs[kind]


RULE = JevDoneCheckParityRule()
