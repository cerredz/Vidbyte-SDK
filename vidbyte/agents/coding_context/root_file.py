"""FILE: vidbyte/agents/coding_context/root_file.py

PURPOSE: Defines RootFileLoader, the shared base of the section loaders that read one named file from a CodingAgent's root folder once, capped, into one context section: AgentsMdLoader (AGENTS.md) and MapMdLoader (MAP.md).
ROLE IN CODEBASE: Subclassed by vidbyte/agents/coding_context/agents_md.py and map_md.py, whose load() CodingAgent.__init__ (vidbyte/agents/coding.py) calls with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the system prompt.
ARCHITECTURE NOTE: Plain deterministic code with no model involvement. A subclass sets FILE_NAME, MAX_BYTES, SECTION, and TITLE and returns its own settings switch from _enabled; the finding, reading, decoding, and truncation live here once. Only the root folder's direct children are looked at, never a parent folder. The file is read at construction, so every run of one agent shows the same text, and a later chdir or edit changes nothing until a new agent is built. A missing or blank file means no section; a file that is there but cannot be read fails construction, because a silent skip would hide it.
FUNCTION INVENTORY: RootFileLoader.load is the narrated main function; _enabled returns the subclass's switch; _find_file picks the file among the root folder's children; _read_capped reads at most the cap and the file's total size; _decode decodes UTF-8, or UTF-16 after a UTF-16 BOM, without splitting a character at the cut; _with_truncation_note appends the line that says where the cut is and how to read the rest.
COMMON MODIFICATION PATTERNS: Another root-file section is a small subclass in its own module that sets the four class attributes and _enabled. A section that is not one root file is its own loader, not a branch here.
WHAT NOT TO DO IN THIS FILE: 1. Do not walk parent folders or merge nested files. 2. Do not read the file per run. 3. Do not read past the cap; a huge file must never be loaded whole. 4. Do not skip a present-but-broken file silently. 5. Do not name a specific file here; each subclass names its own.
KNOWN EDGE CASES: The exact FILE_NAME wins over a case variant; with several variants and no exact name, the first in sorted order is used. Invalid UTF-8 becomes U+FFFD and a leading byte-order mark is dropped; a file that starts with a UTF-16 BOM, as Windows PowerShell 5.1 writes, is read as UTF-16. A multibyte character that straddles the cap is left out of the shown text. A symlinked file is followed and still capped. A directory, a dangling symlink, or an unreadable file under the name raises ConfigurationError naming the path.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-map-md.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py and tests/features/coding_agent/test_coding_agent_map_md.py
"""

from __future__ import annotations

import codecs
import os
from pathlib import Path
from typing import ClassVar

from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError


class RootFileLoader:
    """Reads one named file from the root folder once, capped, into one context section; each subclass names the file and the section."""

    FILE_NAME: ClassVar[str]
    MAX_BYTES: ClassVar[int]
    SECTION: ClassVar[CodingContextSection]
    TITLE: ClassVar[str]

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None:
        """Return this loader's section for settings.root_dir, or None when loading is off or there is nothing to show."""
        # A caller who turned this section off gets no section, and the
        # root folder is never listed or read for it.
        if not cls._enabled(settings):
            return None

        # Look for the file among the root folder's own files only. A
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
        return CodingContextSectionText(section=cls.SECTION, title=f"{cls.TITLE} ({path.name})", content=text, source=str(path))

    @staticmethod
    def _enabled(settings: CodingAgentSettings) -> bool:
        """Return the settings switch that turns this section on; each subclass returns its own."""
        raise NotImplementedError("A RootFileLoader subclass must return its settings switch from _enabled.")

    @classmethod
    def _find_file(cls, root: Path) -> Path | None:
        """Return root's FILE_NAME, else its first case variant in sorted order, else None."""
        # @intent root-file-name-is-case-insensitive
        # One listing serves every platform: Linux needs it to find a
        # lowercase name such as agents.md, and on Windows it gives the
        # real name.
        try:
            names = os.listdir(root)
        except OSError as exc:
            raise ConfigurationError(f"CodingAgent could not list {root} to look for {cls.FILE_NAME}.", details={"root_dir": str(root), "error": type(exc).__name__}) from exc
        matches = sorted(name for name in names if name.lower() == cls.FILE_NAME.lower())
        if not matches:
            return None
        return root / (cls.FILE_NAME if cls.FILE_NAME in matches else matches[0])

    @classmethod
    def _read_capped(cls, path: Path) -> tuple[bytes, int]:
        """Return at most MAX_BYTES of path's bytes and the file's total size, or raise naming path."""
        # @intent present-but-broken-root-file-fails-construction
        # A directory, a dangling link, or an unreadable file under the
        # name is there but broken; skipping it would hide that.
        if not path.is_file():
            raise ConfigurationError(f"CodingAgent found {path}, but it is not a readable regular file.", details={"path": str(path)})
        try:
            with path.open("rb") as handle:
                total_bytes = os.fstat(handle.fileno()).st_size
                return handle.read(cls.MAX_BYTES), total_bytes
        except OSError as exc:
            raise ConfigurationError(f"CodingAgent could not read {path}.", details={"path": str(path), "error": type(exc).__name__}) from exc

    @staticmethod
    def _decode(data: bytes, *, truncated: bool) -> tuple[str, int]:
        """Return data decoded as UTF-8, or UTF-16 when it starts with a UTF-16 BOM, and how many of its bytes the text covers."""
        # An incremental decoder keeps a character the cut split in its
        # buffer instead of emitting it, so only whole characters are
        # shown. Invalid bytes become U+FFFD; both codecs drop their BOM.
        # @intent powershell-utf16-root-files-are-read
        # Windows PowerShell 5.1's > and Out-File write UTF-16 with a BOM, as the manifest reader already handles.
        encoding = "utf-16" if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig"
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
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


__all__ = ["RootFileLoader"]
