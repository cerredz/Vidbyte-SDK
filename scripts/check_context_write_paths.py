"""FILE: scripts/check_context_write_paths.py

PURPOSE:
    Enforces zone-scoped context write-path integrity for the Vidbyte SDK.
    Managed context (registry primitives / placement injections) must be written
    through ContextManager public APIs or ContextWindowRunContext. Private
    registry access and inner-loop provider-message mutation fail closed in CI.
ROLE IN CODEBASE:
    Invoked by scripts/run_ci.py during the source gate. Coding agents and PRs
    use the same entry point so architecture bypasses cannot land silently.
ARCHITECTURE NOTE:
    Pure-stdlib AST scan with path-scoped rules (CWP001/CWP002/CWP004) and an
    embedded self-check so the rule engine cannot silently no-op.
FUNCTION INVENTORY:
    main() -> int: CLI entry; runs self-check then package scan.
    scan_tree(root) -> list[Finding]: walk vidbyte/ and apply hard rules.
    self_check() -> list[str]: validate good/bad fixture snippets.
WHAT NOT TO DO IN THIS FILE:
    1. Do not ban AgentRuntime transcript message appends (zone 4).
    2. Do not flag unrelated _registry names outside the scoped paths.
    3. Do not add third-party lint dependencies.
RELATED DOCS:
    docs/design/context-write-path-integrity.md
    skills/vidbyte-sdk/context-primitives.md
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "vidbyte"

PRIVATE_STORE_ATTRS = frozenset({"_registry", "_placements"})
MESSAGE_MUTATION_METHODS = frozenset({"append", "insert", "pop", "clear"})
INNER_LOOP_EXPLICIT = frozenset(
    {
        "error_correction.py",
        "problem_space_search.py",
        "trajectory_checkpoints.py",
    }
)
CWP001_PREFIXES = (
    "vidbyte/context/",
    "vidbyte/agents/",
    "vidbyte/tools/builtins/context_primitives/",
    "vidbyte/tools/builtins/context/",
)
MANAGER_REL = "vidbyte/context/manager.py"
ALGORITHMS_PREFIX = "vidbyte/context/algorithms/"
CONTEXT_PRIMITIVES_PREFIX = "vidbyte/tools/builtins/context_primitives/"


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule violation at a file location."""

    rule: str
    path: str
    line: int
    message: str

    def format(self) -> str:
        return f"{self.rule} {self.path}:{self.line}: {self.message}"


def _posix_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_under(rel: str, prefixes: tuple[str, ...]) -> bool:
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in prefixes)


def _expr_is_messages(node: ast.AST) -> bool:
    if isinstance(node, ast.Name) and node.id == "messages":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "messages":
        return True
    return False


def _is_ctx_messages(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "messages"
        and isinstance(node.value, ast.Name)
        and node.value.id == "ctx"
    )


def _module_defines_inner_loop(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "InnerContextWindowAlgorithm":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "InnerContextWindowAlgorithm":
                return True
    return False


def _class_is_base_tool(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseTool":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseTool":
            return True
    return False


def _init_has_context_manager_param(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = list(func.args.args) + list(func.args.kwonlyargs)
    for arg in args:
        if arg.arg in {"self", "cls"}:
            continue
        if arg.arg in {"context_manager", "manager"}:
            return True
        if arg.annotation is None:
            continue
        ann = ast.unparse(arg.annotation)
        if "ContextManager" in ann:
            return True
    return False


def scan_source(source: str, *, rel_path: str) -> list[Finding]:
    """Apply CWP rules to one module's source text."""
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        raise ValueError(f"syntax error in {rel_path}: {exc}") from exc

    findings: list[Finding] = []
    is_manager = rel_path == MANAGER_REL
    in_cwp001_scope = (not is_manager) and _is_under(rel_path, CWP001_PREFIXES)
    is_inner = rel_path.startswith(ALGORITHMS_PREFIX) and (
        Path(rel_path).name in INNER_LOOP_EXPLICIT or _module_defines_inner_loop(tree)
    )
    in_context_primitives = rel_path.startswith(CONTEXT_PRIMITIVES_PREFIX)

    for node in ast.walk(tree):
        if in_cwp001_scope and isinstance(node, ast.Attribute) and node.attr in PRIVATE_STORE_ATTRS:
            findings.append(
                Finding(
                    rule="CWP001",
                    path=rel_path,
                    line=getattr(node, "lineno", 1),
                    message=(
                        f"private ContextManager storage access '.{node.attr}' is forbidden "
                        "outside manager.py; use public ContextManager APIs "
                        "(registry_items, upsert, place_after_*, get_by_id, remove_by_id)."
                    ),
                )
            )

        if is_inner:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in MESSAGE_MUTATION_METHODS and _expr_is_messages(node.func.value):
                    findings.append(
                        Finding(
                            rule="CWP002",
                            path=rel_path,
                            line=getattr(node, "lineno", 1),
                            message=(
                                f"inner-loop algorithms must not mutate provider messages via "
                                f".{node.func.attr}(); write managed context through "
                                "ctx.place_after_* / ContextManager.upsert instead."
                            ),
                        )
                    )
            if isinstance(node, ast.Delete):
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and _expr_is_messages(target.value):
                        findings.append(
                            Finding(
                                rule="CWP002",
                                path=rel_path,
                                line=getattr(node, "lineno", 1),
                                message=(
                                    "inner-loop algorithms must not delete provider message "
                                    "entries; use ContextManager/ContextWindowRunContext."
                                ),
                            )
                        )
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if _is_ctx_messages(target):
                        findings.append(
                            Finding(
                                rule="CWP002",
                                path=rel_path,
                                line=getattr(node, "lineno", 1),
                                message=(
                                    "inner-loop algorithms must not assign to ctx.messages; "
                                    "provider transcripts are runtime-owned."
                                ),
                            )
                        )

    if in_context_primitives:
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not (_class_is_base_tool(node) or node.name == "ContextWindowFactory"):
                continue
            init_fn: ast.FunctionDef | ast.AsyncFunctionDef | None = None
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                    init_fn = item
                    break
            if init_fn is None:
                continue
            if not _init_has_context_manager_param(init_fn):
                findings.append(
                    Finding(
                        rule="CWP004",
                        path=rel_path,
                        line=getattr(init_fn, "lineno", getattr(node, "lineno", 1)),
                        message=(
                            f"{node.name}.__init__ must accept a ContextManager "
                            "(parameter name context_manager/manager or ContextManager annotation)."
                        ),
                    )
                )

    return findings


def iter_python_files(package_root: Path) -> list[Path]:
    files = sorted(package_root.rglob("*.py"))
    return [path for path in files if "__pycache__" not in path.parts]


def scan_tree(root: Path) -> list[Finding]:
    package = root / "vidbyte"
    if not package.is_dir():
        raise FileNotFoundError(f"package root missing: {package}")
    findings: list[Finding] = []
    for path in iter_python_files(package):
        rel = _posix_rel(path, root)
        # utf-8-sig strips a leading BOM so AST parse matches the compiler on Windows checkouts.
        source = path.read_text(encoding="utf-8-sig")
        findings.extend(scan_source(source, rel_path=rel))
    return findings


_SELF_CHECK_CASES: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "good_inner_place",
        '''
from vidbyte.context.runtime import InnerContextWindowAlgorithm, ContextWindowRunContext
class GoodAlg(InnerContextWindowAlgorithm):
    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        ctx.place_after_tools(item)
        history = list(ctx.messages or [])
        _ = history
''',
        frozenset(),
    ),
    (
        "bad_inner_append",
        '''
from vidbyte.context.runtime import InnerContextWindowAlgorithm, ContextWindowRunContext
class BadAlg(InnerContextWindowAlgorithm):
    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        ctx.messages.append({"role": "assistant", "content": "x"})
''',
        frozenset({"CWP002"}),
    ),
    (
        "bad_private_registry",
        '''
class ContextListTool:
    def execute(self):
        return self._manager._registry
''',
        frozenset({"CWP001"}),
    ),
    (
        "good_tool_init",
        '''
from vidbyte.tools.base import BaseTool
class ContextListTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None:
        self._manager = context_manager
''',
        frozenset(),
    ),
    (
        "bad_tool_init",
        '''
from vidbyte.tools.base import BaseTool
class ContextListTool(BaseTool):
    def __init__(self) -> None:
        self._store = {}
''',
        frozenset({"CWP004"}),
    ),
)


def self_check() -> list[str]:
    """Return error strings when embedded fixtures do not match expectations."""
    errors: list[str] = []
    for name, source, expected_rules in _SELF_CHECK_CASES:
        if name.startswith("bad_private") or name.startswith("good_tool") or name.startswith("bad_tool"):
            rel = f"vidbyte/tools/builtins/context_primitives/{name}.py"
        elif name.startswith("good_inner") or name.startswith("bad_inner"):
            rel = f"vidbyte/context/algorithms/{name}.py"
        else:
            rel = f"vidbyte/context/algorithms/{name}.py"
        try:
            findings = scan_source(source, rel_path=rel)
        except ValueError as exc:
            errors.append(f"self-check {name}: parse failed: {exc}")
            continue
        actual = frozenset(item.rule for item in findings)
        if actual != expected_rules:
            errors.append(
                f"self-check {name}: expected rules {sorted(expected_rules)}, "
                f"got {sorted(actual)} ({[f.format() for f in findings]})"
            )
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce context write-path integrity rules.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="Repository root containing vidbyte/ (default: parent of scripts/).",
    )
    parser.add_argument(
        "--skip-self-check",
        action="store_true",
        help="Skip embedded fixture self-check (not used by run_ci.py).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    if not args.skip_self_check:
        self_errors = self_check()
        if self_errors:
            for err in self_errors:
                print(err, file=sys.stderr)
            print("context write-path checker self-check failed", file=sys.stderr)
            return 1
    try:
        findings = scan_tree(root)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"context write-path checker error: {exc}", file=sys.stderr)
        return 2
    if findings:
        for item in sorted(findings, key=lambda f: (f.path, f.line, f.rule)):
            print(item.format(), file=sys.stderr)
        print(
            f"context write-path integrity failed with {len(findings)} finding(s)",
            file=sys.stderr,
        )
        return 1
    print("context write-path integrity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
