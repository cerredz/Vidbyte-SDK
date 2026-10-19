"""FILE: vidbyte/lib/tools/filesystem/usage.py

PURPOSE: Defines FolderUsage, the canonical way to measure what a folder holds, counted from disk every time: the estimated tokens of each file under it, leaving out named top-level folders, and the file count and token total it would hold after a set of writes, so a caller can refuse a write that would pass its caps before writing anything.
ROLE IN CODEBASE: Called by InfiniteWorkspace (vidbyte/agents/infinite/workspace.py) when an agent attaches, before every memory write, and to draw the workspace map. Any feature that keeps a size-capped folder an agent can write to, such as a scratch or memory folder, should measure it here instead of walking the folder itself.
ARCHITECTURE NOTE: Static methods only, with no state and no cache: bash, the developer, or another agent can change the folder between two calls, so every measurement reads the disk. Tokens are TokenEstimate's character estimate (vidbyte/lib/util/text.py) of each file decoded with errors="replace", so a binary or broken file still counts. Totals are returned as a FolderTotals record (vidbyte/lib/dataclasses/filesystem.py). The caller owns the caps and the wording of a refusal.
FUNCTION INVENTORY: tokens_by_file(root, skip, encoding) -> dict of each file's root-relative POSIX path to its estimated tokens, sorted by path; totals(counts, changed) -> FolderTotals the folder would hold after writing each changed path's full new text.
COMMON MODIFICATION PATTERNS: A new measure of a folder, such as bytes, is one more static method here that reads the disk the same way; a new cap belongs to its caller.
WHAT NOT TO DO IN THIS FILE: 1. Do not cache counts between calls. 2. Do not write to the folder. 3. Do not import from a layer above vidbyte/lib.
KNOWN EDGE CASES: skip names top-level folders only, matched exactly, so ".runs" skips root/.runs but not root/notes/.runs. Folders and symlinked folders add no count of their own; a file reached through a symlink counts. totals with an empty changed mapping is the folder as it is now. A changed path already on disk replaces its old count rather than adding to it.
RELATED DOCS: vidbyte/agents/infinite/README.md (workspace caps); vidbyte/lib/README.md
TESTS: tests/test_folder_usage.py; and through InfiniteWorkspace, tests/features/infinite_memory_agent/test_infinite_memory_workspace.py
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

from vidbyte.lib.dataclasses.filesystem import FolderTotals
from vidbyte.lib.util.text import TokenEstimate


class FolderUsage:
    """Static-method home for measuring a folder from disk and projecting a write's effect on its totals."""

    @staticmethod
    def tokens_by_file(root: Path, *, skip: Collection[str] = (), encoding: str = "utf-8") -> dict[str, int]:
        """Return each file under root, outside the skipped top-level folders, mapped to its estimated tokens."""
        # @intent folder-usage-is-counted-from-disk
        # Every file counts, whoever wrote it, so nothing written around
        # the caller's own tools slips past its caps.
        counts: dict[str, int] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if path.is_file() and relative.parts[0] not in skip:
                counts[relative.as_posix()] = TokenEstimate.count(path.read_text(encoding=encoding, errors="replace"))
        return counts

    @staticmethod
    def totals(counts: Mapping[str, int], changed: Mapping[str, str]) -> FolderTotals:
        """Return the file count and token total the folder would hold after writing each changed path's full new text."""
        # @intent totals-are-projected-over-the-write
        # A changed path that already exists swaps its old count for the
        # new text's; a new one adds a file. The counts must be fresh
        # from tokens_by_file, so the projection matches the disk.
        files = len(counts) + sum(1 for relative in changed if relative not in counts)
        tokens = sum(counts.values()) - sum(counts.get(relative, 0) for relative in changed) + sum(TokenEstimate.count(text) for text in changed.values())
        return FolderTotals(files=files, tokens=tokens)


__all__ = ["FolderUsage"]
