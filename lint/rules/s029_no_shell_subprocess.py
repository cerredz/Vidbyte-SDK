"""FILE: lint/rules/s029_no_shell_subprocess.py

PURPOSE: Rejects shell-interpreting subprocess execution anywhere in the SDK package.
ROLE IN CODEBASE: Protects McpStdioTransport's create_subprocess_exec-only convention from regressing.
ARCHITECTURE NOTE: Pure syntactic AST match; no taint tracking of the command argument is attempted.
FUNCTION INVENTORY: NoShellSubprocessRule scans every call for shell-interpreting execution APIs.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S029.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

_SHELL_METHODS = frozenset({"run", "call", "check_call", "check_output", "Popen"})


def _dotted_name(node: ast.expr) -> str | None:
    # Reconstructs a dotted call target such as "subprocess.run" or "os.system".
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _has_shell_true(call: ast.Call) -> bool:
    # Confirms the call carries an explicit shell=True keyword.
    return any(kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in call.keywords)


class NoShellSubprocessRule(Rule):
    """Rejects shell=True subprocess calls, os.system, and asyncio.create_subprocess_shell."""

    id = "S029"
    name = "no-shell-subprocess"
    severity = "blocking"
    summary = "Subprocess execution never routes through a shell."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Walks every call expression looking for shell-interpreting execution.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.Call):
                    continue
                dotted = _dotted_name(node.func)
                if dotted is None:
                    continue
                tail = dotted.rsplit(".", 1)[-1]
                is_shell_subprocess = tail in _SHELL_METHODS and dotted == f"subprocess.{tail}" and _has_shell_true(node)
                is_os_system = dotted == "os.system"
                is_shell_create = dotted == "asyncio.create_subprocess_shell"
                if is_shell_subprocess or is_os_system or is_shell_create:
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=dotted, extra={"call": dotted}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the exact call and the fixed-executable-array replacement.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} executes {finding.symbol} through a shell.",
            why_blocked="Shell execution parses the command string for metacharacters, turning any input that reaches the command (directly or through a formatting helper) into an injection vector, and makes the actual executable and arguments harder for a reviewer or agent to verify at a glance.",
            how_to_fix="Replace the call with subprocess.run([executable, *args], shell=False, ...) or asyncio.create_subprocess_exec(executable, *args, ...) using a fixed executable path and an explicit argument list, matching the pattern already used in vidbyte/tools/mcp/transport.py's start().",
            correct_examples=("vidbyte/tools/mcp/transport.py - McpStdioTransport.start() uses asyncio.create_subprocess_exec(*self.command, ...) with no shell involved.",),
            will_not_work=("Passing shell=False alongside a manually shell-quoted string.", "Sanitizing the string with a custom escaper instead of using an argument array."),
            verify=self.verify_command(),
        )


RULE = NoShellSubprocessRule()
