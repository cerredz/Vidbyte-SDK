"""FILE: scripts/check_context_primitive_introductions.py

PURPOSE: Enforces the shared introduction on every concrete context primitive renderer.
ROLE IN CODEBASE: The canonical source CI stage runs this repository contract before packaging the SDK.
ARCHITECTURE NOTE: Static AST inspection finds concrete ContextItem renderers without importing runtime modules.
COMMON MODIFICATION PATTERNS: Update recognized renderer/helper shapes only when the context primitive contract changes.
KNOWN EDGE CASES: Parse failures fail closed, abstract ContextItem is excluded, and every concrete class must define its own renderer.
RELATED DOCS: docs/design/context-window-primitives.md and field-guide/vidbyte-sdk/local-ci-verification.md.
TESTS: Its embedded fixture checks and the source stage in scripts/run_ci.py exercise this script.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIMITIVES_ROOT = REPOSITORY_ROOT / "vidbyte" / "context" / "primitives"
INTRODUCTION_HELPERS = frozenset({"_truncate_text", "_with_context_intro"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One context-primitive introduction violation."""

    path: str
    line: int
    message: str

    def format(self) -> str:
        return f"CWP005 {self.path}:{self.line}: {self.message}"


def _method(tree: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _uses_introduction_helper(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in INTRODUCTION_HELPERS
        for node in ast.walk(method)
    )


def scan_source(source: str, *, rel_path: str) -> list[Finding]:
    """Find concrete context-item renderers that bypass the shared introduction."""
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        raise ValueError(f"syntax error in {rel_path}: {exc}") from exc

    findings: list[Finding] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name == "ContextItem" or not node.name.endswith("ContextItem"):
            continue
        renderer = _method(node, "to_context_text")
        if renderer is None:
            findings.append(Finding(rel_path, node.lineno, f"{node.name} must define to_context_text()."))
        elif not _uses_introduction_helper(renderer):
            findings.append(
                Finding(
                    rel_path,
                    renderer.lineno,
                    f"{node.name}.to_context_text() must use _truncate_text() or _with_context_intro() so its 3-line context introduction is rendered first.",
                )
            )
    return findings


def iter_primitive_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted((root / "vidbyte" / "context" / "primitives").glob("*.py"))
        if path.name not in {"__init__.py", "base.py"} and "__pycache__" not in path.parts
    )


def scan_tree(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_primitive_files(root):
        rel_path = path.resolve().relative_to(root.resolve()).as_posix()
        findings.extend(scan_source(path.read_text(encoding="utf-8-sig"), rel_path=rel_path))
    return findings


_SELF_CHECK_CASES = (
    (
        "good",
        """
class GoodContextItem:
    def to_context_text(self):
        return _truncate_text("body", 100)
""",
        False,
    ),
    (
        "bad",
        """
class BadContextItem:
    def to_context_text(self):
        return "body"
""",
        True,
    ),
)


def self_check() -> list[str]:
    errors: list[str] = []
    for name, source, should_fail in _SELF_CHECK_CASES:
        findings = scan_source(source, rel_path=f"vidbyte/context/primitives/{name}.py")
        failed = bool(findings)
        if failed != should_fail:
            errors.append(f"self-check {name}: expected finding={should_fail}, got {findings}")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce context primitive introduction rendering.")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--skip-self-check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.skip_self_check:
        errors = self_check()
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
    try:
        findings = scan_tree(args.root.resolve())
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"context primitive introduction checker error: {exc}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(finding.format(), file=sys.stderr)
        print(f"context primitive introduction check failed with {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print("context primitive introductions: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
