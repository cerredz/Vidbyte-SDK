"""FILE: lint/rules/c020_api_key_prefix_contract.py

PURPOSE: Detect SDK production code that spells the Vidbyte API-key prefix anywhere but one owner constant, an owner constant whose value is not the vendored platform contract's api_key_prefix, a second owner constant, and literals spelling a key prefix the platform does not issue.
ROLE IN CODEBASE: Enforces C020, the SDK consumer side of cross-repo contract X10. cerredz/Vidbyte exports its API-key prefix (api_key_prefix in lint/contracts/vidbyte-platform-contract.json, generated from the backend's single declaration); the SDK's key-format check and its live-key redaction must follow that one value through one SDK constant.
ARCHITECTURE NOTE: The owner is a module-level `str` constant under vidbyte/lib/constants/ whose name ends in API_KEY_PREFIX (AGENTS.md: constants live in vidbyte/lib/constants/<domain>.py). Every other non-docstring string literal under vidbyte/, f-string parts included, is scanned; code that builds patterns from the owner constant contains no literal prefix and passes.
FUNCTION INVENTORY: PrefixOwner records one owner constant; PrefixScan finds owners, inline copies, and foreign prefixes in the catalog; PlatformApiKeyPrefixRule reports and explains.
COMMON MODIFICATION PATTERNS: A new key kind (a second prefix) must first appear in the platform contract; then extend the contract schema and this rule together, with scratch fixtures.
WHAT NOT TO DO: Do not import vidbyte, edit the vendored contract, or accept a prefix split across literals as a fix.
KNOWN EDGE CASES: The contract prefix counts anywhere in a literal (a message naming the vb_live_ format is a copy too). A foreign prefix counts only when it is key-shaped: at the end of the literal, before a regex token, or before at least 16 key characters, so an identifier such as vb_cache_dir is not a key prefix. Docstrings and bare string statements are skipped; tests are out of scope.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C020); lint/contracts/README.md; lint catalog X10.
TESTS: python lint/run.py --rule C020; scratch fixtures, fail-closed contract cases, and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.platform_contract import PLATFORM_CONTRACT_REL, REFRESH_DOC_REL, PlatformContract, PlatformContractLoader
from lint.core.registry import Rule

_INLINE = "inline-prefix"
_FOREIGN = "foreign-prefix"
_MISMATCH = "owner-mismatch"
_DUPLICATE = "duplicate-owner"
_KINDS = frozenset({_INLINE, _FOREIGN, _MISMATCH, _DUPLICATE})
OWNER_DIR = "vidbyte/lib/constants/"
OWNER_SUFFIX = "API_KEY_PREFIX"
RECOMMENDED_OWNER = "VIDBYTE_API_KEY_PREFIX"
RECOMMENDED_HOME = "vidbyte/lib/constants/jev.py"
_REDACTION_INTENT = "@intent malformed-managed-output-redacts-live-keys"
_KEY_SHAPED_TAIL = re.compile(r"$|[\[({\\.*+?]|[A-Za-z0-9_-]{16,}")
_LISTED = 6


@dataclass(frozen=True, slots=True)
class PrefixOwner:
    """One owner constant: where it is, its name, and its literal value ("" when the value is not a string literal)."""

    rel: str
    line: int
    source_line: str
    name: str
    value: str
    node_id: int

    @property
    def location(self) -> str:
        return f"{self.rel}:{self.line}"


@dataclass(frozen=True, slots=True)
class PrefixLiteral:
    """One string literal that spells a key prefix: the contract's or owner's (inline) or another one (foreign)."""

    source: SourceFile
    line: int
    holder: str
    prefix: str
    foreign: bool


class PrefixScan:
    """Finds the owner constants and every literal outside them that spells a key prefix."""

    def __init__(self, catalog: SourceCatalog, contract: PlatformContract) -> None:
        # The key family head ("vb_" for "vb_live_") bounds which other prefixes count as foreign.
        self.catalog = catalog
        self.prefix = contract.api_key_prefix
        head = self.prefix[: self.prefix.find("_") + 1] if "_" in self.prefix else self.prefix
        self._family = re.compile(rf"(?<![A-Za-z0-9]){re.escape(head)}[a-z0-9]+_")
        self.owners = self._owners()

    def literals(self) -> Iterator[PrefixLiteral]:
        # Every non-docstring literal under vidbyte/ except the owners' own values, in path and line order.
        owned = {owner.node_id for owner in self.owners}
        spelled = {self.prefix, *(owner.value for owner in self.owners if owner.value)}
        exact = re.compile("|".join(rf"(?<![A-Za-z0-9]){re.escape(value)}" for value in sorted(spelled, key=len, reverse=True)))
        for source in self.catalog.python_files():
            if source.tree is None:
                continue
            holders = _holders(source.tree)
            skipped = _docstring_ids(source.tree) | owned
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in skipped:
                    continue
                match = exact.search(node.value)
                if match is not None:
                    yield PrefixLiteral(source=source, line=node.lineno, holder=holders.get(id(node), ""), prefix=match.group(0), foreign=False)
                    continue
                foreign = next((found for found in self._family.finditer(node.value) if _KEY_SHAPED_TAIL.match(node.value, found.end())), None)
                if foreign is not None:
                    yield PrefixLiteral(source=source, line=node.lineno, holder=holders.get(id(node), ""), prefix=foreign.group(0), foreign=True)

    def _owners(self) -> tuple[PrefixOwner, ...]:
        # Module-level assignments under vidbyte/lib/constants/ whose single name target ends in API_KEY_PREFIX.
        found: list[PrefixOwner] = []
        for source in self.catalog.python_files():
            if not source.rel.startswith(OWNER_DIR) or source.tree is None:
                continue
            for statement in _module_statements(source.tree.body):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                if len(targets) != 1 or not isinstance(targets[0], ast.Name) or not targets[0].id.endswith(OWNER_SUFFIX) or statement.value is None:
                    continue
                value = statement.value.value if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str) else ""
                found.append(PrefixOwner(rel=source.rel, line=statement.lineno, source_line=source.line_at(statement.lineno).strip(), name=targets[0].id, value=value, node_id=id(statement.value)))
        return tuple(sorted(found, key=lambda owner: (owner.rel, owner.line)))


class PlatformApiKeyPrefixRule(Rule):
    """Requires the SDK to spell the platform's API-key prefix once, in an owner constant equal to the contract's api_key_prefix."""

    id = "C020"
    name = "api-key-prefix-contract"
    severity = "blocking"
    summary = "The Vidbyte API-key prefix must be spelled only by one *API_KEY_PREFIX constant in vidbyte/lib/constants/, whose value equals api_key_prefix in lint/contracts/vidbyte-platform-contract.json; no other vidbyte/ literal may spell it or another key prefix."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Load the contract (raising when it is unusable), then judge the owners and every prefix literal.
        contract = PlatformContractLoader.load(catalog)
        scan = PrefixScan(catalog, contract)
        literals = sorted(scan.literals(), key=lambda item: (item.source.rel, item.line))
        inline = [item for item in literals if not item.foreign]
        common = {
            "contract_prefix": contract.api_key_prefix,
            "contract_line": contract.cite(contract.line_of('"api_key_prefix"')),
            "contract_commit": contract.source_commit,
            "owner": f"{scan.owners[0].name} at {scan.owners[0].location}" if scan.owners else "",
            "owner_name": scan.owners[0].name if scan.owners else "",
            "sites": ", ".join(f"{item.source.rel}:{item.line}" for item in inline[:_LISTED]) + (f", and {len(inline) - _LISTED} more" if len(inline) > _LISTED else ""),
            "site_count": str(len(inline)),
            "intent": self._intent(catalog),
        }
        findings = [self._owner_finding(owner, index, scan.owners[0], contract, common) for index, owner in enumerate(scan.owners)]
        findings.extend(Finding(rule_id=self.id, rel_path=item.source.rel, line=item.line, source_line=item.source.line_at(item.line).strip(), symbol=item.holder or item.prefix, extra={**common, "kind": _FOREIGN if item.foreign else _INLINE, "prefix": item.prefix, "holder": item.holder}) for item in literals)
        return [finding for finding in findings if finding is not None]

    def _owner_finding(self, owner: PrefixOwner, index: int, first: PrefixOwner, contract: PlatformContract, common: dict[str, str]) -> Finding | None:
        # The first owner must equal the contract; every later one is a duplicate.
        if index > 0:
            kind = _DUPLICATE
        elif owner.value != contract.api_key_prefix:
            kind = _MISMATCH
        else:
            return None
        extra = {**common, "kind": kind, "prefix": owner.value, "holder": owner.name, "first": first.location}
        return Finding(rule_id=self.id, rel_path=owner.rel, line=owner.line, source_line=owner.source_line, symbol=owner.name, extra=extra)

    @staticmethod
    def _intent(catalog: SourceCatalog) -> str:
        return next((f"{source.rel}:{number}" for source in catalog.python_files() for number, line in enumerate(source.text.splitlines(), start=1) if _REDACTION_INTENT in line), "")

    def explain(self, finding: Finding) -> Diagnostic:
        # Shared consequence and examples; what and repair differ per kind.
        extra = finding.extra
        kind = extra.get("kind", "")
        if kind not in _KINDS:
            raise ValueError(f"C020 finding has unknown kind {kind!r}.")
        prefix = extra["contract_prefix"]
        owner = extra["owner_name"] or RECOMMENDED_OWNER
        intent = f" (`{_REDACTION_INTENT}`, {extra['intent']})" if extra["intent"] else ""
        return Diagnostic(
            what_happened=self._what(finding, kind),
            why_blocked=f"cerredz/Vidbyte exports the prefix of every API key it issues as api_key_prefix = `{prefix}` in {PLATFORM_CONTRACT_REL} ({extra['contract_line']}, generated from the backend's single declaration at {extra['contract_commit'][:8]}). The SDK's managed-key format check and its live-key redaction must match that prefix exactly. A copy that drifts makes managed mode reject every valid key, or makes the redaction stop matching so error text can carry a live key{intent}. X10 requires one source for the prefix: the contract on the platform side and one constant in vidbyte/lib/constants/ on the SDK side, so a re-vendor shows the change in one place.",
            how_to_fix=self._repair(finding, kind, owner),
            correct_examples=(
                f'`{owner}: str = "{prefix}"` in {extra["owner"].split(" at ")[-1] if extra["owner"] else RECOMMENDED_HOME} - the one SDK spelling, equal to the contract.',
                f'`re.fullmatch(rf"{{re.escape({owner})}}[A-Za-z0-9_-]{{{{32,}}}}", key)` - a format check or redaction pattern built from the constant, so it follows the contract.',
            ),
            will_not_work=(
                f'Splitting the prefix across literals, such as `"vb_" + "live_"`, or building it with `chr`: the copy still drifts when the platform changes `{prefix}`; only the constant follows a re-vendor.',
                f"Editing api_key_prefix in {PLATFORM_CONTRACT_REL}: the copy must stay byte-identical to cerredz/Vidbyte. A real prefix change lands there first and arrives through a re-vendor ({REFRESH_DOC_REL}).",
                f"Defining a second *{OWNER_SUFFIX} constant in another module: C020 reports every owner after the first, and a constant outside vidbyte/lib/constants/ is just another inline copy.",
                f"Raising C020's baseline in lint/baseline.json: the baseline freezes the {extra['site_count']} known inline copies only until they are moved onto the constant.",
            ),
            verify=self.verify_command(),
        )

    @staticmethod
    def _what(finding: Finding, kind: str) -> str:
        # The site and the specific contract disagreement.
        extra = finding.extra
        where = f"{finding.location()} (`{extra['holder']}`)" if extra["holder"] else finding.location()
        owner = f"the owner constant is {extra['owner']}" if extra["owner"] else f"the SDK has no *{OWNER_SUFFIX} constant in {OWNER_DIR}"
        if kind == _INLINE:
            return f"{where} spells the API-key prefix `{extra['prefix']}` inline, and {owner}. {extra['site_count']} literals under vidbyte/ spell it: {extra['sites']}. Each copy must change by hand when the platform's api_key_prefix (`{extra['contract_prefix']}`, {extra['contract_line']}) changes."
        if kind == _FOREIGN:
            return f"{where} spells the key prefix `{extra['prefix']}`, but the platform issues only `{extra['contract_prefix']}` keys ({extra['contract_line']}), so a key in this form is never valid on Vidbyte."
        if kind == _MISMATCH:
            value = f"`{extra['prefix']}`" if extra["prefix"] else "not a string literal, so C020 cannot read it"
            return f"{where} is the SDK's owner constant for the API-key prefix, but its value is {value}, while the platform contract's api_key_prefix is `{extra['contract_prefix']}` ({extra['contract_line']})."
        return f"{where} is a second API-key prefix constant; {extra['owner']} is already the owner, so the SDK has two spellings that can drift apart."

    @staticmethod
    def _repair(finding: Finding, kind: str, owner: str) -> str:
        # Numbered steps per kind, ending with the rule's own verify command.
        extra = finding.extra
        prefix = extra["contract_prefix"]
        steps: tuple[str, ...]
        if kind == _INLINE:
            create = f"1. Import {extra['owner']}." if extra["owner"] else f'1. Add `{RECOMMENDED_OWNER}: str = "{prefix}"` to {RECOMMENDED_HOME}, beside the other managed-gateway constants.'
            steps = (create, f"2. Replace the literal at {finding.location()} with the constant: build a pattern with `re.escape({owner})`, and a message with an f-string that interpolates it.", f"3. Move every listed copy in the same change ({extra['sites']}), so the format check and the redaction cannot disagree.")
        elif kind == _FOREIGN:
            steps = (f"1. If this is meant to be a Vidbyte key, use `{owner}` (`{prefix}`) instead of `{extra['prefix']}`.", f"2. If the platform has introduced a new key kind, it must be in cerredz/Vidbyte's contract first; re-vendor it ({REFRESH_DOC_REL}), then extend C020 with the new prefix.")
        elif kind == _MISMATCH:
            steps = (f'1. Set `{extra["holder"]}` to the literal `"{prefix}"`.', f"2. If the platform really changed its prefix, the vendored contract is stale: re-vendor it as {REFRESH_DOC_REL} describes instead of diverging from it.")
        else:
            steps = (f"1. Delete `{extra['holder']}` at {finding.location()}.", f"2. Import {extra['owner']} wherever `{extra['holder']}` was used.")
        return "\n".join((*steps, f"{len(steps) + 1}. Run `python lint/run.py --rule C020`."))


def _module_statements(body: Sequence[ast.stmt]) -> Iterator[ast.Assign | ast.AnnAssign]:
    # Module-level assignments, including those inside if/try/with blocks, which still run at import time.
    for statement in body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            yield statement
        elif isinstance(statement, ast.If):
            yield from _module_statements([*statement.body, *statement.orelse])
        elif isinstance(statement, ast.Try):
            yield from _module_statements([*statement.body, *(line for handler in statement.handlers for line in handler.body), *statement.orelse, *statement.finalbody])
        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            yield from _module_statements(statement.body)


def _docstring_ids(tree: ast.Module) -> set[int]:
    # Every bare string expression statement: docstrings and string-as-comment blocks are not code values.
    return {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}


def _holders(tree: ast.Module) -> dict[int, str]:
    # The qualified name of the function, class, or module constant that holds each string literal.
    found: dict[int, str] = {}

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, f"{scope}{child.name}.")
                continue
            if not scope and isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                name = next((target.id for target in targets if isinstance(target, ast.Name)), "")
                for inner in ast.walk(child):
                    if isinstance(inner, ast.Constant):
                        found[id(inner)] = name
                continue
            if isinstance(child, ast.Constant):
                found[id(child)] = scope.rstrip(".")
            visit(child, scope)

    visit(tree, "")
    return found


RULE = PlatformApiKeyPrefixRule()
