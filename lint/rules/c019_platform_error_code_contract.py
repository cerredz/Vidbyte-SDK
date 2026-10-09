"""FILE: lint/rules/c019_platform_error_code_contract.py

PURPOSE: Detect SDK code that branches on, maps, or defines a platform error code the vendored platform contract does not export: a literal in a platform error-code family that is not in error_codes, or a near miss (likely typo) of an exported code.
ROLE IN CODEBASE: Enforces C019, the SDK consumer side of cross-repo contract X07. cerredz/Vidbyte exports every error code its API can return in lint/contracts/vidbyte-platform-contract.json; SDK handling written for a code the platform never sends never runs.
ARCHITECTURE NOTE: Only literals in decision positions count: operands of ==, !=, in, and not in (with tuple, list, set, and frozenset elements), match-case values, dict-literal keys and values, and module- or class-level constants. A literal is attributed to the platform only by evidence from the contract itself, a shared multi-token family prefix or a difflib near miss, so the SDK's own tokens that happen to equal generic platform codes are never reported.
FUNCTION INVENTORY: ErrorVocabulary derives families and near misses from the contract; CodeSite and CodeSites collect decision-position literals; PlatformErrorCodeContractRule reports and explains.
COMMON MODIFICATION PATTERNS: A new decision position needs a branch in CodeSites plus a scratch fixture; never widen attribution to single-token prefixes, which would claim the SDK's own vocabulary.
WHAT NOT TO DO: Do not import vidbyte, edit the vendored contract, or report an exact contract code.
KNOWN EDGE CASES: Exact contract codes never produce a finding. Two-token codes such as not_found are below the three-token shape, so the SDK's patch-tool and workflow tokens that equal them are out of scope. A literal that is both a family member and a near miss is a near-miss.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C019); lint/contracts/README.md; lint catalog X07.
TESTS: python lint/run.py --rule C019; scratch fixtures, fail-closed contract cases, and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

import ast
import difflib
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.platform_contract import PLATFORM_CONTRACT_REL, REFRESH_DOC_REL, PlatformContract, PlatformContractLoader
from lint.core.registry import Rule

_UNKNOWN = "unknown-code"
_NEAR_MISS = "near-miss"
_KINDS = frozenset({_UNKNOWN, _NEAR_MISS})
_CODE_SHAPE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}")
NEAR_MISS_RATIO = 0.9
MIN_FAMILY_TOKENS = 2
MIN_FAMILY_SIZE = 2
_COMPARE_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)
_COLLECTION_CALLS = frozenset({"frozenset", "set", "tuple", "list"})
_SDK_FAILURE_CLASS = "FailureCode"
_LISTED = 3


@dataclass(frozen=True, slots=True)
class ErrorVocabulary:
    """The contract's error codes, the multi-token families they share, and how a literal relates to them."""

    codes: frozenset[str]
    ordered: tuple[str, ...]
    families: tuple[str, ...]

    @classmethod
    def from_contract(cls, contract: PlatformContract) -> ErrorVocabulary:
        # A family is a prefix of at least two whole tokens shared by at least two codes; longest families first.
        counts: Counter[str] = Counter()
        for code in contract.error_codes:
            tokens = code.split("_")
            for size in range(MIN_FAMILY_TOKENS, len(tokens)):
                counts["_".join(tokens[:size]) + "_"] += 1
        families = tuple(sorted((prefix for prefix, count in counts.items() if count >= MIN_FAMILY_SIZE), key=lambda prefix: (-len(prefix), prefix)))
        return cls(codes=frozenset(contract.error_codes), ordered=contract.error_codes, families=families)

    def family_of(self, literal: str) -> str:
        return next((family for family in self.families if literal.startswith(family)), "")

    def members(self, family: str) -> tuple[str, ...]:
        return tuple(code for code in self.ordered if code.startswith(family))

    def near_miss(self, literal: str) -> tuple[str, float]:
        # The closest exported code at or above NEAR_MISS_RATIO, with its ratio, or ("", 0.0).
        best = difflib.get_close_matches(literal, self.ordered, n=1, cutoff=NEAR_MISS_RATIO)
        return (best[0], difflib.SequenceMatcher(None, literal, best[0]).ratio()) if best else ("", 0.0)


@dataclass(frozen=True, slots=True)
class CodeSite:
    """One code-shaped string literal in a decision position."""

    source: SourceFile
    node: ast.Constant
    position: str
    holder: str


class CodeSites:
    """Walks one module and yields every code-shaped literal in a comparison, match case, dict literal, or module/class constant."""

    def __init__(self, source: SourceFile) -> None:
        self.source = source
        self._seen: set[int] = set()

    def collect(self) -> Iterator[CodeSite]:
        # Expression positions anywhere in the module, then module- and class-level constant definitions.
        if self.source.tree is None:
            return
        for node in ast.walk(self.source.tree):
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                for index, op in enumerate(node.ops):
                    if isinstance(op, _COMPARE_OPS):
                        yield from self._sites((operands[index], operands[index + 1]), f"a `{type(op).__name__}` comparison", "")
            elif isinstance(node, ast.match_case):
                yield from self._sites([pattern.value for pattern in ast.walk(node.pattern) if isinstance(pattern, ast.MatchValue)], "a match case", "")
            elif isinstance(node, ast.Dict):
                yield from self._sites([*(key for key in node.keys if key is not None), *node.values], "a dict literal", "")
        yield from self._constants(self.source.tree.body, "")

    def _constants(self, body: Sequence[ast.stmt], owner: str) -> Iterator[CodeSite]:
        # Assignments at module or class level (through if/try/with blocks), descending into class bodies.
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                yield from self._constants(statement.body, f"{owner}{statement.name}.")
            elif isinstance(statement, (ast.If, ast.With, ast.Try)):
                nested = [*statement.body, *statement.orelse] if isinstance(statement, (ast.If, ast.Try)) else list(statement.body)
                if isinstance(statement, ast.Try):
                    nested += [*(line for handler in statement.handlers for line in handler.body), *statement.finalbody]
                yield from self._constants(nested, owner)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)) and statement.value is not None:
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                names = [target.id for target in targets if isinstance(target, ast.Name)]
                if names:
                    kind = "a class-level constant" if owner else "a module-level constant"
                    yield from self._sites((statement.value,), kind, f"{owner}{names[0]}")

    def _sites(self, expressions: Sequence[ast.expr], position: str, holder: str) -> Iterator[CodeSite]:
        # String constants in the expressions themselves or as elements of a literal collection or frozenset/set/tuple/list call.
        for expression in expressions:
            for node in self._elements(expression):
                if isinstance(node.value, str) and _CODE_SHAPE.fullmatch(node.value) and id(node) not in self._seen:
                    self._seen.add(id(node))
                    yield CodeSite(source=self.source, node=node, position=position, holder=holder)

    @staticmethod
    def _elements(expression: ast.expr) -> list[ast.Constant]:
        if isinstance(expression, ast.Constant):
            return [expression]
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name) and expression.func.id in _COLLECTION_CALLS and len(expression.args) == 1:
            expression = expression.args[0]
        if isinstance(expression, (ast.Tuple, ast.List, ast.Set)):
            return [element for element in expression.elts if isinstance(element, ast.Constant)]
        return []


class PlatformErrorCodeContractRule(Rule):
    """Requires every platform-attributed error code in SDK decision positions to be exported by the platform contract."""

    id = "C019"
    name = "platform-error-code-contract"
    severity = "blocking"
    summary = "A flat snake_case literal of three or more tokens that vidbyte/ code compares, matches, maps, or defines as a constant, and that starts with a platform error-code family or nearly equals an exported code, must be one of the error_codes in lint/contracts/vidbyte-platform-contract.json."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Load the contract (raising when it is unusable), derive its vocabulary, and judge every decision-position literal.
        contract = PlatformContractLoader.load(catalog)
        vocabulary = ErrorVocabulary.from_contract(contract)
        sdk_example = self._sdk_example(catalog)
        findings: list[Finding] = []
        for source in catalog.python_files():
            for site in CodeSites(source).collect():
                finding = self._judge(site, contract, vocabulary, sdk_example)
                if finding is not None:
                    findings.append(finding)
        return findings

    def _judge(self, site: CodeSite, contract: PlatformContract, vocabulary: ErrorVocabulary, sdk_example: str) -> Finding | None:
        # Exact codes pass; a near miss outranks family membership; anything with neither is SDK vocabulary.
        literal = str(site.node.value)
        if literal in vocabulary.codes:
            return None
        closest, ratio = vocabulary.near_miss(literal)
        family = vocabulary.family_of(literal)
        if not closest and not family:
            return None
        members = vocabulary.members(family) if family else ()
        nearest = closest or difflib.get_close_matches(literal, members, n=1, cutoff=0.0)[0]
        extra = {
            "kind": _NEAR_MISS if closest else _UNKNOWN,
            "code": literal,
            "position": site.position,
            "holder": site.holder,
            "family": family,
            "family_size": str(len(members)),
            "family_codes": ", ".join(members[:_LISTED]) + (f", and {len(members) - _LISTED} more" if len(members) > _LISTED else ""),
            "closest": nearest,
            "ratio": f"{ratio:.2f}" if closest else f"{difflib.SequenceMatcher(None, literal, nearest).ratio():.2f}",
            "closest_line": contract.cite(contract.code_line(nearest)),
            "codes_line": contract.cite(contract.line_of('"error_codes"')),
            "code_count": str(len(vocabulary.codes)),
            "contract_commit": contract.source_commit,
            "sdk_example": sdk_example,
        }
        line = site.node.lineno
        return Finding(rule_id=self.id, rel_path=site.source.rel, line=line, source_line=site.source.line_at(line).strip(), symbol=site.holder or literal, extra=extra)

    @staticmethod
    def _sdk_example(catalog: SourceCatalog) -> str:
        # The first dotted member of the SDK's own FailureCode enum, cited as the vocabulary SDK-internal codes use.
        for source in catalog.python_files():
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.ClassDef) and node.name == _SDK_FAILURE_CLASS:
                    for statement in node.body:
                        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str) and "." in statement.value.value and isinstance(statement.targets[0], ast.Name):
                            return f'`{_SDK_FAILURE_CLASS}.{statement.targets[0].id} = "{statement.value.value}"` at {source.rel}:{statement.lineno}'
        return ""

    def explain(self, finding: Finding) -> Diagnostic:
        # One consequence for both kinds; the what and the first repair step differ by kind.
        extra = finding.extra
        kind = extra.get("kind", "")
        if kind not in _KINDS:
            raise ValueError(f"C019 finding has unknown kind {kind!r}.")
        code, closest = extra["code"], extra["closest"]
        sdk = extra["sdk_example"] or "a dotted SDK failure code such as `model.not_found`"
        return Diagnostic(
            what_happened=self._what(finding, kind),
            why_blocked=f"cerredz/Vidbyte exports every error code its API can return in {PLATFORM_CONTRACT_REL} (error_codes, {extra['code_count']} codes at {extra['contract_commit'][:8]}). SDK code that branches on or maps a code the platform never sends is dead: the handling never runs, and the real platform error falls through to generic handling, so users get the wrong retry, message, or failure kind. X07 requires every platform error code the SDK handles to match the export. Literals are attributed to the platform only by contract evidence (a family prefix of two or more tokens that two or more exported codes share, or a difflib ratio of at least {NEAR_MISS_RATIO} to an exported code), so the SDK's own tokens are never claimed.",
            how_to_fix=self._repair(finding, kind),
            correct_examples=(
                f'`if payload.get("code") == "{closest}":` - branches on a code the contract exports ({extra["closest_line"]}).',
                f"{sdk} - SDK-internal codes are dotted, so they never take the platform's flat snake_case shape or its family prefixes.",
            ),
            will_not_work=(
                f"Adding `{code}` to {PLATFORM_CONTRACT_REL}: the copy must stay byte-identical to cerredz/Vidbyte. If the platform adds the code, its regenerated contract carries it and a re-vendor ({REFRESH_DOC_REL}) clears this finding.",
                f'Building the code at run time, for example `"{extra["family"] or code[: code.rfind("_") + 1]}" + suffix`, to hide it from C019: the platform still never sends it, so the branch stays dead.',
                "Raising C019's baseline in lint/baseline.json: the baseline is 0, and every frozen finding is handling that never runs.",
            ),
            verify=self.verify_command(),
        )

    @staticmethod
    def _what(finding: Finding, kind: str) -> str:
        # The site, its decision position, and the contract evidence that makes it a platform code.
        extra = finding.extra
        holder = f" `{extra['holder']}`" if extra["holder"] else ""
        site = f"{finding.location()} uses `{extra['code']}` in {extra['position']}{holder}"
        if kind == _NEAR_MISS:
            return f"{site}. It is not an exported platform error code, and it is {extra['ratio']} similar to the exported code `{extra['closest']}` ({extra['closest_line']}), so it is almost certainly a misspelling: the platform sends `{extra['closest']}`, and this literal never equals it."
        return f"{site}. It starts with the platform error-code family `{extra['family']}`, which {extra['family_size']} exported codes share ({extra['family_codes']}), but {PLATFORM_CONTRACT_REL} does not export `{extra['code']}` ({extra['codes_line']}). The closest code in that family is `{extra['closest']}`."

    @staticmethod
    def _repair(finding: Finding, kind: str) -> str:
        # Numbered steps: use the exported code, or confirm the platform added it and re-vendor, or rename SDK vocabulary.
        extra = finding.extra
        first = f"1. Replace `{extra['code']}` with the exported code `{extra['closest']}` ({extra['closest_line']})." if kind == _NEAR_MISS else f"1. If this handling is for an existing platform error, use the exported code it means; the closest in the family is `{extra['closest']}` ({extra['closest_line']})."
        return "\n".join((
            first,
            f"2. If cerredz/Vidbyte has added `{extra['code']}`, land that change there first, then re-vendor the contract as {REFRESH_DOC_REL} describes, so the code is in error_codes before the SDK depends on it.",
            "3. If the literal is SDK-internal vocabulary, not a platform code, rename it to the SDK's dotted failure-code form so it stops looking like the platform's.",
            "4. Run `python lint/run.py --rule C019`.",
        ))


RULE = PlatformErrorCodeContractRule()
