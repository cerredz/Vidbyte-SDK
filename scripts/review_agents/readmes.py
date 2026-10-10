"""FILE: scripts/review_agents/readmes.py

PURPOSE: Finds the folder README.md each review comment belongs to, so every agent prompt can name it.
ROLE IN CODEBASE: run.py's prompt step adds a "Folder README" line under each comment; the notes writer records lessons in that file's closing `## Notes for agents` section, and the resolver and preventer read it first.
ARCHITECTURE NOTE: The search walks up from the commented file's folder and stops below the repository root, because the root README.md is the package's description on PyPI and a root file has no folder of its own whose notes could hold a lesson.
COMMON MODIFICATION PATTERNS: Keep this in step with lint/rules/a009_readme_size_limit.py, which exempts the same root README from the size ceiling.
KNOWN EDGE CASES: A comment with no file, such as a summary-only review, has no README; a folder without one falls back to its nearest parent that has one.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py builds a temporary tree of READMEs.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from review_agents.review_data import Review


class ReadmeLocator:
    """Walks up from a commented file to the nearest README.md below the repository root."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def for_review(self, review: Review) -> dict[int, str]:
        # A comment with no file, such as a summary-only review, has no folder to look in.
        found = {comment.id: self.nearest(comment.path) for comment in review.comments}
        return {comment_id: readme for comment_id, readme in found.items() if readme}

    def nearest(self, path: str | None) -> str | None:
        # The file's own folder first, then each parent, stopping before the root itself.
        if not path:
            return None
        folder = PurePosixPath(path).parent
        while folder.parts:
            candidate = folder / "README.md"
            if (self._root / candidate).is_file():
                return candidate.as_posix()
            folder = folder.parent
        return None
