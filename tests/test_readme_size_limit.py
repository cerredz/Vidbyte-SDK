"""FILE: tests/test_readme_size_limit.py

PURPOSE: Prove lint rule A009 bounds the folder READMEs that the @claude workflow's notes stage appends to.
ROLE IN CODEBASE: The offline spec for lint/rules/a009_readme_size_limit.py.
ARCHITECTURE NOTE: Each case builds a throwaway git repository under tmp_path, because the rule reads only tracked files from the shared source catalogue.
COMMON MODIFICATION PATTERNS: A change to the ceilings or the exemptions gets a case here.
KNOWN EDGE CASES: The rule counts characters, so every fixture README is written with Unix line endings.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lint.core.discovery import SourceCatalog
from lint.rules.a009_readme_size_limit import RULE as README_SIZE_RULE


def _readme_repository(root: Path, readmes: dict[str, int]) -> SourceCatalog:
    # Each README is a tracked file of exactly the given number of characters.
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for rel, size in readmes.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Folder\n\n## Notes for agents\n\n" + "x" * (size - 31), encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return SourceCatalog(root)


def test_a009_reports_a_folder_readme_over_its_ceiling_at_the_notes(tmp_path: Path) -> None:
    catalog = _readme_repository(tmp_path, {"pkg/README.md": 40_001, "fits/README.md": 40_000})
    findings = README_SIZE_RULE.check(catalog)
    assert [(finding.rel_path, finding.line) for finding in findings] == [("pkg/README.md", 3)]
    assert findings[0].extra == {"characters": "40001", "ceiling": "40000", "target": "30000"}
    assert "30,000" in README_SIZE_RULE.explain(findings[0]).what_happened


def test_a009_exempts_the_root_readme_and_keeps_legacy_ceilings(tmp_path: Path) -> None:
    catalog = _readme_repository(tmp_path, {"README.md": 90_000, "vidbyte/providers/README.md": 50_000, "vidbyte/agents/codex/README.md": 65_001})
    findings = README_SIZE_RULE.check(catalog)
    assert [(finding.rel_path, finding.extra["target"]) for finding in findings] == [("vidbyte/agents/codex/README.md", "55000")]
