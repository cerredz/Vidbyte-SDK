"""FILE: vidbyte/lib/constants/coding.py

PURPOSE: Defines the fixed AGENTS.md file name and byte cap that CodingAgent uses when it loads a repository's AGENTS.md into the model's context, and the paths, cap, template, and model-facing text of the agent's own progress notes file.
ROLE IN CODEBASE: Read by AgentsMdLoader (vidbyte/agents/coding_context/agents_md.py), ProgressNotesLoader (vidbyte/agents/coding_context/progress_notes.py), and the coding-agent feature tests.
ARCHITECTURE NOTE: Immutable constants only; the loaders own the reading, decoding, and truncation behavior.
COMMON MODIFICATION PATTERNS: Change the cap here, never at the read call, so the loader, its truncation line, and the tests stay in step.
KNOWN EDGE CASES: The cap counts bytes, not characters; the loader moves the cut back to a whole UTF-8 character, so the shown text can be up to three bytes shorter.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-progress-notes.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py and tests/features/coding_agent/test_coding_agent_progress_notes.py
"""

from __future__ import annotations

# The preferred file name; any case variant is accepted when this exact
# name is absent from the root folder.
CODING_AGENTS_MD_FILE_NAME = "AGENTS.md"

# 32 KiB, Codex's default project-doc cap, so a huge file cannot fill
# the model's context.
CODING_AGENTS_MD_MAX_BYTES = 32_768

# The agent's own notes folder and file under the root folder. They are
# local working files, not a repository convention.
CODING_PROGRESS_NOTES_DIR = ".vidbyte"
CODING_PROGRESS_NOTES_FILE_NAME = "progress.md"

# Written as .vidbyte/.gitignore, so the folder ignores itself the way
# pytest's .pytest_cache does and the user's .gitignore is never edited.
CODING_PROGRESS_NOTES_GITIGNORE = "*\n"

# 32 KiB, the same cap as AGENTS.md; notes are meant to stay short.
CODING_PROGRESS_NOTES_MAX_BYTES = 32_768

# The text of a new notes file: a heading and three empty headings.
CODING_PROGRESS_NOTES_TEMPLATE = "# Progress notes\n\n## Done\n\n## Next\n\n## Decisions\n"

# Shown to the model above the notes.
CODING_PROGRESS_NOTES_INSTRUCTION = "This is your own notes file for this repository. It is kept between runs and is never committed. Read it before you start.\nAfter each meaningful step, update .vidbyte/progress.md with write_text or replace_text: what is done, what is next, and any decisions.\nKeep it short."

# Shown after notes cut at the cap.
CODING_PROGRESS_NOTES_TRUNCATION_NOTE = "[The notes were cut at 32 KiB. Read the rest of .vidbyte/progress.md with read_lines, then shorten it.]"

__all__ = [
    "CODING_AGENTS_MD_FILE_NAME",
    "CODING_AGENTS_MD_MAX_BYTES",
    "CODING_PROGRESS_NOTES_DIR",
    "CODING_PROGRESS_NOTES_FILE_NAME",
    "CODING_PROGRESS_NOTES_GITIGNORE",
    "CODING_PROGRESS_NOTES_INSTRUCTION",
    "CODING_PROGRESS_NOTES_MAX_BYTES",
    "CODING_PROGRESS_NOTES_TEMPLATE",
    "CODING_PROGRESS_NOTES_TRUNCATION_NOTE",
]
