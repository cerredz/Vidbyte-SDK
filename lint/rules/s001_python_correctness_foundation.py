"""FILE: lint/rules/s001_python_correctness_foundation.py

PURPOSE:
    Declares S001, the SDK lint suite's Python correctness foundation rule:
    undefined/unused names, broken import placement, statement-level
    correctness, and parser/runtime errors.
ROLE IN CODEBASE:
    Registered by lint/core/registry.py; its ruff_selectors are unioned into
    the one Ruff invocation lint/core/ruff.py makes, and its find() then
    filters that shared result set down to this rule's codes.
ARCHITECTURE NOTE:
    This rule intentionally excludes Ruff's BLE001 (broad `except Exception`).
    vidbyte/agents/pricing/tracker.py and vidbyte/agents/runtime.py
    deliberately catch broad exceptions in usage-tracking code so a metering
    bug can never crash a host agent run; a correctness rule must not fight
    a pattern the codebase already ships on purpose.
WHAT NOT TO DO IN THIS FILE:
    Do not widen ruff_selectors beyond F/E4/E7/E9 in this rule; a new
    selector family (for example B904 exception chaining) belongs in its own
    sNNN rule module with its own diagnostic, per docs/design/
    sdk-lint-python-correctness.md Section 13.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    field-guide/vidbyte-sdk/diagnostic-context.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from lint.core.diagnostic import Finding, RuleDiagnostic

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.ruff import RuffFinding


class PythonCorrectnessFoundationRule:
    """S001: pyflakes plus core pycodestyle correctness selectors."""

    rule_id: ClassVar[str] = "S001"
    ruff_selectors: ClassVar[tuple[str, ...]] = ("F", "E4", "E7", "E9")

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns S001's fixed summary/impact/repair/verify-command text.
        return RuleDiagnostic(
            summary=(
                "Ruff's pyflakes (F) selector plus its core pycodestyle import-placement "
                "(E4), statement-correctness (E7), and parser/runtime (E9) selectors found "
                "this. These four families catch names, imports, and statements that are "
                "objectively wrong regardless of house style: an unused import, an undefined "
                "name, a bare `except:`, a comparison to None or True with `==` instead of "
                "`is`, or a file that fails to parse."
            ),
            impact=(
                "This is not a style preference. Left in place it either hides a real bug "
                "(an undefined name raises NameError the first time that branch actually "
                "runs; a bare `except:` swallows every exception, including "
                "KeyboardInterrupt and SystemExit, not just the one the code meant to "
                "handle) or actively misleads the next reader (an unused import implies a "
                "dependency the code no longer uses; a variable assigned but never read "
                "looks load-bearing when it is dead)."
            ),
            repair=(
                "Remove the unused import or variable, reference or rename the undefined "
                "name, replace `except:` with the specific exception type the code actually "
                "expects, and replace `== None` / `== True` with `is None` / `is True`. Do "
                "not silence an S001 finding with a `# noqa` comment: every code in this "
                "selector union is an objective defect this analyzer proved exists, not a "
                "judgment call, so the fix belongs in the source."
            ),
            verify_command="python lint/run.py --rule S001",
        )

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Filters the shared Ruff findings to this rule's selector prefixes and wraps each as a Finding.
        matched = (f for f in ruff_findings if f.code.startswith(PythonCorrectnessFoundationRule.ruff_selectors))
        return tuple(
            Finding(rule_id="S001", code=f.code, file=f.file, line=f.line, column=f.column, message=f.message)
            for f in matched
        )


__all__ = ["PythonCorrectnessFoundationRule"]
