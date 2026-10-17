"""FILE: lint/rules/c021_native_host_constants_in_lib.py

PURPOSE: Detect module-level constants defined inside the native harness hosts under vidbyte/harnesses/native/.
ROLE IN CODEBASE: Enforces C021, the rule that every fixed value a native host reads (wire tables, bounds, field rules and message text) lives in vidbyte/lib/constants/<domain>.py.
ARCHITECTURE NOTE: Side-effect-free AST scan of each module's top-level statements; a binding is a constant when its name is PEP 8 UPPER_CASE, with or without a leading underscore. __all__ is the module's export list, not a constant.
FUNCTION INVENTORY: NativeHostConstantsInLibRule reports each top-level UPPER_CASE Assign or AnnAssign target in scope and explains the lib move.
COMMON MODIFICATION PATTERNS: Widen SCOPE_PREFIX only after measuring the new scope; keep the diagnostic naming the canonical lib modules.
WHAT NOT TO DO: Do not flag class attributes or locals, and do not exempt a host module because its constants are private.
KNOWN EDGE CASES: A module-level TypeVar is CamelCase by convention and is not reported. Text a lib constant needs from openai-codex is stored as a name the host resolves at call time, as CODEX_HOST_RAW_RESPONSE_MODELS does, because vidbyte/lib never imports an optional SDK.
RELATED DOCS: lint/README.md; AGENTS.md (Placement Rules); vidbyte/lib/constants/codex_host.py and native_threads.py (the canonical homes)
TESTS: Exercised by python lint/run.py --rule C021.
"""

from __future__ import annotations

import ast
import re

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

SCOPE_PREFIX = "vidbyte/harnesses/native/"
CONSTANT_NAME = re.compile(r"_?[A-Z][A-Z0-9_]*")
EXPORT_LIST = "__all__"


class NativeHostConstantsInLibRule(Rule):
    """Reject module-level constants in native harness host modules."""

    id = "C021"
    name = "native-host-constants-in-lib"
    severity = "blocking"
    summary = "Native harness hosts read every fixed value from vidbyte/lib/constants/, never from module-level constants of their own."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Reports every top-level UPPER_CASE binding in a native host module.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(SCOPE_PREFIX):
                continue
            for node in source.tree.body:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
                for target in targets:
                    if isinstance(target, ast.Name) and target.id != EXPORT_LIST and CONSTANT_NAME.fullmatch(target.id):
                        findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=target.id))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Points the repair at the lib constants layer every other native
        # host already uses, and cites the review that set the rule.
        return Diagnostic(
            what_happened=f"{finding.location()} defines the module-level constant {finding.symbol} inside a native harness host.",
            why_blocked="vidbyte/lib/ is the bottom layer that owns every fixed value the hosts read, so a reader finds a host's wire tables, bounds, field rules and message text in one place and a sibling host can reuse them. Review of PR #1055 (comments 4301484278, 4301488494, 4301744297) rejected CodexHost constants defined in connection.py, errors.py and preflight.py with 'wrong file location, put inside of lib'; Grok, Muse, Opencode and hostkit already keep theirs in vidbyte/lib/constants/.",
            how_to_fix=f"Move {finding.symbol} to vidbyte/lib/constants/<domain>.py under a domain-prefixed name, add it to that module's sorted __all__, and import it here. A value that needs an optional SDK type is stored as its name and resolved where the host calls the SDK.",
            correct_examples=(
                "vidbyte/lib/constants/codex_host.py holds CODEX_HOST_SPENDING_RAW_METHODS, which vidbyte/harnesses/native/codex/connection.py imports.",
                "vidbyte/lib/constants/native_threads.py holds the NATIVE_* tables NativeErrorFactory and the Grok, Muse and Opencode wires read.",
            ),
            will_not_work=(
                "Renaming the constant to lowercase or moving it into a class body to dodge the scan; the value still lives in the wrong layer.",
                "Adding an inline suppression or raising the C021 baseline.",
            ),
            verify=self.verify_command(),
        )


RULE = NativeHostConstantsInLibRule()
