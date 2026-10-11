"""FILE: vidbyte/agents/coding_context/progress_notes.py

PURPOSE: Defines ProgressNotesLoader, which keeps a CodingAgent's own notes file, <root>/.vidbyte/progress.md, and shows it in the PROGRESS_NOTES section with a short instruction to keep it up to date, so a second run picks up where the first stopped.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places last among the sections. Reads its paths, cap, template, and text from vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: The notes are the agent's local working file, not a repository convention. The loader creates the file from a template, and a .vidbyte/.gitignore holding "*" so the folder ignores itself, each only when missing; exclusive-create mode means an existing file is never overwritten. The agent edits the file with write_text or replace_text; the section is read once, at construction.
FUNCTION INVENTORY: ProgressNotesLoader.load is the narrated main function; _create_if_missing writes a file only when it does not exist; _read_capped reads at most the cap and appends the cut note when the file is longer.
COMMON MODIFICATION PATTERNS: Change the paths, cap, template, or model-facing text in vidbyte/lib/constants/coding.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not overwrite or reset an existing notes file or .gitignore; the notes are kept between runs on purpose. 2. Do not edit the user's own .gitignore. 3. Do not raise when the root cannot be written; the switch is on by default and read-only use must keep working.
KNOWN EDGE CASES: Any OSError while creating or reading the files (a read-only root, a permission error, a file named .vidbyte, a folder named progress.md) gives no section. On a read-only root where both files already exist nothing is written, so the section is still shown. A character split by the cap, and any byte that is not UTF-8, is dropped from the shown text.
RELATED DOCS: docs/design/coding-agent-progress-notes.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_progress_notes.py
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.lib.constants.coding import (
    CODING_PROGRESS_NOTES_DIR,
    CODING_PROGRESS_NOTES_FILE_NAME,
    CODING_PROGRESS_NOTES_GITIGNORE,
    CODING_PROGRESS_NOTES_INSTRUCTION,
    CODING_PROGRESS_NOTES_MAX_BYTES,
    CODING_PROGRESS_NOTES_TEMPLATE,
    CODING_PROGRESS_NOTES_TRUNCATION_NOTE,
)
from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection


class ProgressNotesLoader:
    """Keeps the agent's own <root>/.vidbyte/progress.md and shows it, capped at 32 KiB, in the PROGRESS_NOTES section."""

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None:
        """Return the progress-notes section for settings.root_dir, or None when notes are off or the root cannot be written."""
        # A caller who turned notes off gets no section, and nothing is
        # created in the root folder.
        if not settings.progress_notes:
            return None

        folder = Path(settings.root_dir) / CODING_PROGRESS_NOTES_DIR
        path = folder / CODING_PROGRESS_NOTES_FILE_NAME
        try:
            # Make the notes folder and have it ignore itself, so git
            # never shows the notes and the user's .gitignore is never
            # touched.
            folder.mkdir(exist_ok=True)
            cls._create_if_missing(folder / ".gitignore", CODING_PROGRESS_NOTES_GITIGNORE)

            # Start the notes from the template the first time. A file
            # that is already there holds the last run's notes and is
            # kept as it is.
            cls._create_if_missing(path, CODING_PROGRESS_NOTES_TEMPLATE)

            # Read the notes, never more than the cap.
            notes = cls._read_capped(path)
        except OSError:
            # @intent read-only-root-gets-no-progress-notes
            # An agent that cannot write here cannot keep notes. Notes
            # are on by default, so a read-only checkout must still
            # build an agent; it just gets no notes section.
            return None

        # Show the instruction first, then the notes themselves.
        return CodingContextSectionText(
            section=CodingContextSection.PROGRESS_NOTES,
            title=f"Progress notes ({CODING_PROGRESS_NOTES_DIR}/{CODING_PROGRESS_NOTES_FILE_NAME})",
            content=f"{CODING_PROGRESS_NOTES_INSTRUCTION}\n\n{notes}",
            source=str(path),
        )

    @staticmethod
    def _create_if_missing(path: Path, text: str) -> None:
        """Write text to path as UTF-8 only when path does not exist yet."""
        # Exclusive create fails when the file is there, so an existing
        # file is never overwritten, even one made a moment ago.
        try:
            with path.open("xb") as handle:
                handle.write(text.encode("utf-8"))
        except FileExistsError:
            return

    @staticmethod
    def _read_capped(path: Path) -> str:
        """Return path's text, at most the cap, followed by the cut note when the file is longer."""
        # One byte past the cap tells whether the file is longer.
        with path.open("rb") as handle:
            data = handle.read(CODING_PROGRESS_NOTES_MAX_BYTES + 1)
        text = data[:CODING_PROGRESS_NOTES_MAX_BYTES].decode("utf-8-sig", errors="ignore")
        if len(data) > CODING_PROGRESS_NOTES_MAX_BYTES:
            return f"{text}\n\n{CODING_PROGRESS_NOTES_TRUNCATION_NOTE}"
        return text


__all__ = ["ProgressNotesLoader"]
