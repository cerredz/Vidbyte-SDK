"""FILE: vidbyte/tools/builtins/_note_ids.py

PURPOSE: Picks the next free counter for an append-only note tool id such as "reflexion:2".
ROLE IN CODEBASE: Shared by reflexion, trajectory_checkpoint, the CoT event tools, and the single-step reasoning tools.
ARCHITECTURE NOTE: Reads ContextManager.get_by_id only; callers still build the id and upsert the note themselves.
COMMON MODIFICATION PATTERNS: Keep the "<prefix>:<n>" shape in sync with every caller's id format.
KNOWN EDGE CASES: Several tool instances can write into one shared manager, so their counters overlap.
RELATED DOCS: docs/design/note-tool-ids-skip-taken.md
TESTS: tests/test_context_algorithm_tools.py (shared-manager id tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


def next_free_counter(manager: ContextManager, prefix: str, counter: int) -> int:
    """Return the first counter at or after ``counter`` whose ``prefix:counter`` id is unused."""
    # @intent note-tool-ids-never-overwrite-shared-notes
    # Another tool instance on a shared manager may already own this id, and upsert would replace its note.
    while manager.get_by_id(f"{prefix}:{counter}") is not None:
        counter += 1
    return counter


__all__ = ["next_free_counter"]
