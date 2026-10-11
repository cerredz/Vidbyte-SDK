"""FILE: vidbyte/agents/coding_context/agents_md.py

PURPOSE: Defines AgentsMdLoader, which reads the root folder's AGENTS.md once, capped at 32 KiB, into the AGENTS_MD section of a CodingAgent's context window, so the model follows the rules the repository already wrote down.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the system prompt. Reads its file name and cap from vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: Plain deterministic code with no model involvement. Only the root folder's direct children are looked at, never a parent folder. The file is read at construction, so every run of one agent shows the same text, and a later chdir or edit changes nothing until a new agent is built. A missing or blank file means no section; a file that is there but cannot be read fails construction, because a silent skip would hide it.
FUNCTION INVENTORY: AgentsMdLoader.load is the narrated main function; _find_file picks the file among the root folder's children; _read_capped reads at most the cap and the file's total size; _decode decodes UTF-8 without splitting a character at the cut; _with_truncation_note appends the line that says where the cut is and how to read the rest.
COMMON MODIFICATION PATTERNS: Change the cap or the preferred name in vidbyte/lib/constants/coding.py. A new kind of section is a new loader file in this package, not a branch here.
WHAT NOT TO DO IN THIS FILE: 1. Do not walk parent folders or merge nested AGENTS.md files; the user asked for the root folder's file only. 2. Do not read the file per run. 3. Do not read past the cap; a huge file must never be loaded whole. 4. Do not skip a present-but-broken file silently.
KNOWN EDGE CASES: The exact name AGENTS.md wins over a case variant; with several variants and no exact name, the first in sorted order is used. Invalid UTF-8 becomes U+FFFD and a leading byte-order mark is dropped. A multibyte character that straddles the cap is left out of the shown text. A symlinked AGENTS.md is followed and still capped. A directory, a dangling symlink, or an unreadable file named AGENTS.md raises ConfigurationError naming the path.
RELATED DOCS: docs/design/coding-agent-agents-md.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py
"""

from __future__ import annotations

import codecs
import os
from pathlib import Path

from vidbyte.lib.constants.coding import CODING_AGENTS_MD_FILE_NAME, CODING_AGENTS_MD_MAX_BYTES
from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError


class AgentsMdLoader:
    """Reads the root folder's AGENTS.md once, capped at 32 KiB, into the AGENTS_MD context section."""

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None:
        """Return the AGENTS.md section for settings.root_dir, or None when loading is off or there is nothing to show."""
        # A caller who turned loading off gets no section, and the root
        # folder is never listed or read for it.
        if not settings.load_agents:
            return None

        # Look for AGENTS.md among the root folder's own files only. A
        # missing file is normal and simply adds nothing.
        path = cls._find_file(Path(settings.root_dir))
        if path is None:
            return None

        # Read no more than the cap, so a huge file can never fill the
        # model's context, and learn how big the whole file is.
        data, total_bytes = cls._read_capped(path)

        # Turn the bytes into text. When the file was cut, a character
        # split by the cut is left out instead of shown as garbage.
        text, shown_bytes = cls._decode(data, truncated=total_bytes > len(data))

        # An empty or whitespace-only file gives the model nothing.
        if not text.strip():
            return None

        # Tell the model where a cut file stops and how to read the
        # rest.
        if shown_bytes < total_bytes:
            text = cls._with_truncation_note(text, path.name, shown_bytes, total_bytes)
        return CodingContextSectionText(section=CodingContextSection.AGENTS_MD, title=f"Repository instructions ({path.name})", content=text, source=str(path))

    @staticmethod
    def _find_file(root: Path) -> Path | None:
        """Return root's AGENTS.md, else its first case variant in sorted order, else None."""
        # @intent agents-md-name-is-case-insensitive
        # One listing serves every platform: Linux needs it to find a
        # lowercase agents.md, and on Windows it gives the real name.
        try:
            names = os.listdir(root)
        except OSError as exc:
            raise ConfigurationError(f"CodingAgent could not list {root} to look for {CODING_AGENTS_MD_FILE_NAME}.", details={"root_dir": str(root), "error": type(exc).__name__}) from exc
        matches = sorted(name for name in names if name.lower() == CODING_AGENTS_MD_FILE_NAME.lower())
        if not matches:
            return None
        return root / (CODING_AGENTS_MD_FILE_NAME if CODING_AGENTS_MD_FILE_NAME in matches else matches[0])

    @staticmethod
    def _read_capped(path: Path) -> tuple[bytes, int]:
        """Return at most the cap's worth of path's bytes and the file's total size, or raise naming path."""
        # @intent present-but-broken-agents-md-fails-construction
        # A directory, a dangling link, or an unreadable file named
        # AGENTS.md is there but broken; skipping it would hide that.
        if not path.is_file():
            raise ConfigurationError(f"CodingAgent found {path}, but it is not a readable regular file.", details={"path": str(path)})
        try:
            with path.open("rb") as handle:
                total_bytes = os.fstat(handle.fileno()).st_size
                return handle.read(CODING_AGENTS_MD_MAX_BYTES), total_bytes
        except OSError as exc:
            raise ConfigurationError(f"CodingAgent could not read {path}.", details={"path": str(path), "error": type(exc).__name__}) from exc

    @staticmethod
    def _decode(data: bytes, *, truncated: bool) -> tuple[str, int]:
        """Return data decoded as UTF-8 and how many of its bytes the text covers."""
        # An incremental decoder keeps a character the cut split in its
        # buffer instead of emitting it, so only whole characters are
        # shown. Invalid bytes become U+FFFD; "utf-8-sig" drops a BOM.
        decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="replace")
        text = decoder.decode(data, final=not truncated)
        pending, _flag = decoder.getstate()
        return text, len(data) - len(pending)

    @staticmethod
    def _with_truncation_note(text: str, name: str, shown_bytes: int, total_bytes: int) -> str:
        """Return text followed by a line naming the cut and the read_lines call that reads the rest."""
        # The next line to read is the one the cut stopped in; reading
        # from it again shows that partial line in full.
        next_line = text.count("\n") + 1
        note = f"[{name} was truncated at {shown_bytes} of {total_bytes} bytes. Read the rest with the read_lines tool (path \"{name}\"), starting at line {next_line}.]"
        return f"{text}\n\n{note}"


__all__ = ["AgentsMdLoader"]
