"""FILE: vidbyte/agents/infinite/memory.py

PURPOSE: Defines InfiniteAgentMemory, one agent's handle on the shared workspace with its role, its remember quota, its new-file allowance, and its pair's staged entries; and the four memory tools built on it: remember, write_note, edit_file (FULL preset only), and drop_entry (verifiers only).
ROLE IN CODEBASE: Built by InfiniteMemoryRuntime (runtime.py) for the root and by InfinitePair (launch.py) for each generator and verifier, whose two memories share one staged list and one dropped list. Calls InfiniteWorkspace (workspace.py) for every rule and write; InfinitePair reads files_written and the staged and dropped lists after each agent returns.
ARCHITECTURE NOTE: The root's remember commits at once, while a pair agent's remember only stages the entry in memory, after the same rule check, so nothing a pair wrote reaches entries.jsonl before its verifier has judged it. Every tool returns ToolResult.error with what to fix and the remaining quota instead of raising, so a refused call changes nothing and the tool stays usable. Every model-facing description and reply comes from the infinite_memory prompt family.
FUNCTION INVENTORY: InfiniteAgentMemory.tools picks the tools for the role and preset; remember, write_note, edit_file, and drop carry out one tool call each and return its message; answer and refusal add the quota line to a message or a problem; quota renders the quota line, which InfinitePair also puts in a pair agent's first message. InfiniteRememberTool, InfiniteWriteNoteTool, InfiniteEditFileTool, and InfiniteDropEntryTool each have spec and execute; InfiniteRememberTool._draft turns the model's arguments into an InfiniteEntryDraft.
COMMON MODIFICATION PATTERNS: A new memory tool is one BaseTool subclass here, one method on InfiniteAgentMemory, one case in tools, its name in vidbyte/lib/constants/infinite.py (and INFINITE_RESERVED_TOOL_NAMES), and its description leaves in the prompt family.
WHAT NOT TO DO IN THIS FILE: 1. Do not write to entries.jsonl from a pair agent; stage instead. 2. Do not count a refused call against the quota. 3. Do not raise out of execute for a rule violation; return ToolResult.error. 4. Do not put module-level constants here; they live in vidbyte/lib/constants/infinite.py.
KNOWN EDGE CASES: A staged key is s<staged + dropped + 1>, so keys never repeat within a pair even after drops. A generator and its verifier have separate quotas but share the staged list, so a verifier sees and can drop the generator's entries. write_note records a path once per agent in files_written even when the agent writes it several times.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 6.1 INV-15 to INV-18 and INV-32, and 9.2); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_workspace.py and tests/features/infinite_memory_agent/test_infinite_memory_verification.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.infinite.workspace import InfiniteWorkspace
from vidbyte.lib.constants.infinite import (
    INFINITE_DROP_ENTRY_TOOL_NAME,
    INFINITE_EDIT_FILE_TOOL_NAME,
    INFINITE_MAX_REFS,
    INFINITE_MAX_TAGS,
    INFINITE_NEW_FILES_PER_AGENT,
    INFINITE_REMEMBER_TOOL_NAME,
    INFINITE_WRITE_NOTE_TOOL_NAME,
)
from vidbyte.lib.dataclasses.infinite import InfiniteEntryDraft, InfiniteStagedEntry
from vidbyte.lib.enums.infinite import (
    InfiniteAgentRole,
    InfiniteEntryKind,
    InfiniteMemoryPreset,
)
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, ToolExecutionError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class InfiniteAgentMemory:
    """One agent's view of the shared workspace: its role, quota, new-file allowance, and its pair's staged entries."""

    def __init__(self, workspace: InfiniteWorkspace, *, key: str, role: InfiniteAgentRole, run_id: str, staged: list[InfiniteStagedEntry] | None = None, dropped: list[str] | None = None) -> None:
        self.workspace = workspace
        self.key = key
        self.role = role
        self.run_id = run_id
        # A generator and its verifier share these two lists; the root
        # has none, because its entries are committed at once.
        self.staged = staged if staged is not None else []
        self.dropped = dropped if dropped is not None else []
        self.accepted = 0
        self.created = 0
        self.files_written: list[str] = []

    def tools(self) -> tuple[BaseTool, ...]:
        """Return this agent's memory tools: remember and write_note, edit_file under FULL, and drop_entry for a verifier."""
        # @intent memory-tools-follow-role-and-preset
        # Only FULL may change written text, and only a verifier judges
        # staged entries, so each agent gets exactly the tools of INV-6.
        tools: list[BaseTool] = [InfiniteRememberTool(self), InfiniteWriteNoteTool(self)]
        match self.workspace.settings.preset:
            case InfiniteMemoryPreset.FULL:
                tools.append(InfiniteEditFileTool(self))
            case _:
                pass
        match self.role:
            case InfiniteAgentRole.VERIFIER:
                tools.append(InfiniteDropEntryTool(self))
            case _:
                pass
        return tuple(tools)

    def remember(self, draft: InfiniteEntryDraft) -> str:
        """Commit the root's entry at once, or stage a pair agent's entry for its verifier, and return the reply."""
        # @intent memory-is-sparse-and-staged
        # Each agent may keep only a few entries, refused calls cost
        # nothing, and a pair's entries wait for the verdict.
        if self.accepted >= self.workspace.settings.max_entries_per_agent:
            raise ToolExecutionError(f"You have used all {self.workspace.settings.max_entries_per_agent} of your memory entries; keep only what matters most, or write it into a note.")
        prompts = Prompts()
        if self.role is InfiniteAgentRole.ROOT:
            entry = self.workspace.commit_entry(draft, by=self.key, verified_by=None, run=self.run_id)
            self.accepted += 1
            return prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_SAVED_PROMPT).format(id=entry.id)
        self.workspace.check_entry(draft, tuple(self.staged))
        staged = InfiniteStagedEntry(key=f"s{len(self.staged) + len(self.dropped) + 1}", author=self.key, draft=draft)
        self.staged.append(staged)
        self.accepted += 1
        return prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_STAGED_PROMPT).format(key=staged.key)

    def write_note(self, path: str, text: str, description: str | None) -> str:
        """Create or append to a note, counting a created file against this agent's allowance, and return the reply."""
        created = self.workspace.write_note(path, text, description, by=self.key, run=self.run_id, may_create=self.created < INFINITE_NEW_FILES_PER_AGENT)
        self.created += int(created)
        if path not in self.files_written:
            self.files_written.append(path)
        return Prompts().get(Prompt.INFINITE_MEMORY_NOTE_SAVED_PROMPT).format(path=path)

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Replace the one match of old_text in a note and return the reply."""
        self.workspace.edit_file(path, old_text, new_text)
        if path not in self.files_written:
            self.files_written.append(path)
        return Prompts().get(Prompt.INFINITE_MEMORY_NOTE_SAVED_PROMPT).format(path=path)

    def drop(self, key: str) -> str:
        """Drop one staged entry by its key so it is never committed, and return the reply naming the keys left."""
        staged = next((item for item in self.staged if item.key == key), None)
        if staged is None:
            raise ToolExecutionError(f"{key!r} is not a staged entry; the staged keys are {', '.join(item.key for item in self.staged) or 'none'}.")
        self.staged.remove(staged)
        self.dropped.append(f"{staged.key} ({staged.draft.text}): dropped by the verifier")
        remaining = ", ".join(item.key for item in self.staged) or "-"
        return Prompts().get(Prompt.INFINITE_MEMORY_ENTRY_DROPPED_PROMPT).format(key=key, remaining=remaining)

    def answer(self, message: str) -> str:
        """Return a success message followed by this agent's quota line."""
        return f"{message}\n{self.quota()}"

    def refusal(self, problem: str) -> str:
        """Return the rejection message for a problem, followed by this agent's quota line."""
        return f"{Prompts().get(Prompt.INFINITE_MEMORY_MEMORY_REJECTED_PROMPT).format(problem=problem)}\n{self.quota()}"

    def quota(self) -> str:
        """Return the quota line: how many entries and new files this agent may still add."""
        entries_max = self.workspace.settings.max_entries_per_agent
        return Prompts().get(Prompt.INFINITE_MEMORY_QUOTA_LINE).format(entries_left=entries_max - self.accepted, entries_max=entries_max, files_left=INFINITE_NEW_FILES_PER_AGENT - self.created, files_max=INFINITE_NEW_FILES_PER_AGENT)


class InfiniteRememberTool(BaseTool):
    """The remember tool: save one short memory entry, or stage it for the pair's verifier."""

    def __init__(self, memory: InfiniteAgentMemory) -> None:
        self.memory = memory

    def spec(self) -> ToolSpec:
        """Return the remember declaration, with kind limited to the InfiniteEntryKind values."""
        prompts = Prompts()
        properties = {
            "kind": {"type": "string", "enum": [kind.value for kind in InfiniteEntryKind], "description": prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_KIND_DESCRIPTION)},
            "text": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_TEXT_DESCRIPTION)},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": INFINITE_MAX_TAGS, "description": prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_TAGS_DESCRIPTION)},
            "refs": {"type": "array", "items": {"type": "string"}, "maxItems": INFINITE_MAX_REFS, "description": prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_REFS_DESCRIPTION)},
            "supersedes": {"type": "integer", "description": prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_SUPERSEDES_DESCRIPTION)},
        }
        return ToolSpec(
            name=INFINITE_REMEMBER_TOOL_NAME,
            description=prompts.get(Prompt.INFINITE_MEMORY_REMEMBER_TOOL_DESCRIPTION),
            permission=ToolPermission.WRITE,
            input_schema={"type": "object", "properties": properties, "required": ["kind", "text"], "additionalProperties": False},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Save or stage the entry, or return what to fix; either way the reply ends with the quota line."""
        try:
            message = self.memory.remember(self._draft(call.arguments))
        except (ConfigurationError, ToolExecutionError) as exc:
            return ToolResult.error(INFINITE_REMEMBER_TOOL_NAME, self.memory.refusal(exc.message))
        return ToolResult.success(INFINITE_REMEMBER_TOOL_NAME, self.memory.answer(message))

    @staticmethod
    def _draft(arguments: Mapping[str, Any]) -> InfiniteEntryDraft:
        # The model sends JSON lists; the record takes tuples and refuses
        # anything else, so a bare string is never split into tags.
        kind, tags, refs = arguments.get("kind"), arguments.get("tags"), arguments.get("refs")
        if kind not in [item.value for item in InfiniteEntryKind]:
            raise ToolExecutionError(f"kind must be one of {', '.join(item.value for item in InfiniteEntryKind)}; got {kind!r}.")
        return InfiniteEntryDraft(
            kind=InfiniteEntryKind(kind),
            text=arguments.get("text", ""),
            tags=tuple(tags) if isinstance(tags, list) else () if tags is None else tags,
            refs=tuple(refs) if isinstance(refs, list) else () if refs is None else refs,
            supersedes=arguments.get("supersedes"),
        )


class InfiniteWriteNoteTool(BaseTool):
    """The write_note tool: create a described note or append to one."""

    def __init__(self, memory: InfiniteAgentMemory) -> None:
        self.memory = memory

    def spec(self) -> ToolSpec:
        """Return the write_note declaration."""
        prompts = Prompts()
        properties = {
            "path": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_NOTE_PATH_DESCRIPTION)},
            "text": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_WRITE_NOTE_TEXT_DESCRIPTION)},
            "description": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_WRITE_NOTE_FILE_DESCRIPTION)},
        }
        return ToolSpec(
            name=INFINITE_WRITE_NOTE_TOOL_NAME,
            description=prompts.get(Prompt.INFINITE_MEMORY_WRITE_NOTE_TOOL_DESCRIPTION),
            permission=ToolPermission.WRITE,
            input_schema={"type": "object", "properties": properties, "required": ["path", "text"], "additionalProperties": False},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Write the note, or return what to fix; either way the reply ends with the quota line."""
        path, text, description = call.arguments.get("path"), call.arguments.get("text"), call.arguments.get("description")
        try:
            if not isinstance(path, str) or not isinstance(text, str) or not text:
                raise ToolExecutionError("path and text must both be text, and text must not be empty.")
            message = self.memory.write_note(path, text, description if isinstance(description, str) else None)
        except (ConfigurationError, ToolExecutionError) as exc:
            return ToolResult.error(INFINITE_WRITE_NOTE_TOOL_NAME, self.memory.refusal(exc.message))
        return ToolResult.success(INFINITE_WRITE_NOTE_TOOL_NAME, self.memory.answer(message))


class InfiniteEditFileTool(BaseTool):
    """The edit_file tool: replace one unique passage of an existing note."""

    def __init__(self, memory: InfiniteAgentMemory) -> None:
        self.memory = memory

    def spec(self) -> ToolSpec:
        """Return the edit_file declaration."""
        prompts = Prompts()
        properties = {
            "path": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_NOTE_PATH_DESCRIPTION)},
            "old_text": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_EDIT_FILE_OLD_TEXT_DESCRIPTION)},
            "new_text": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_EDIT_FILE_NEW_TEXT_DESCRIPTION)},
        }
        return ToolSpec(
            name=INFINITE_EDIT_FILE_TOOL_NAME,
            description=prompts.get(Prompt.INFINITE_MEMORY_EDIT_FILE_TOOL_DESCRIPTION),
            permission=ToolPermission.WRITE,
            input_schema={"type": "object", "properties": properties, "required": ["path", "old_text", "new_text"], "additionalProperties": False},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Make the edit, or return what to fix; either way the reply ends with the quota line."""
        path, old_text, new_text = call.arguments.get("path"), call.arguments.get("old_text"), call.arguments.get("new_text")
        try:
            if not isinstance(path, str) or not isinstance(old_text, str) or not isinstance(new_text, str):
                raise ToolExecutionError("path, old_text, and new_text must all be text.")
            message = self.memory.edit_file(path, old_text, new_text)
        except (ConfigurationError, ToolExecutionError) as exc:
            return ToolResult.error(INFINITE_EDIT_FILE_TOOL_NAME, self.memory.refusal(exc.message))
        return ToolResult.success(INFINITE_EDIT_FILE_TOOL_NAME, self.memory.answer(message))


class InfiniteDropEntryTool(BaseTool):
    """The drop_entry tool: a verifier removes one staged entry so it is never committed."""

    def __init__(self, memory: InfiniteAgentMemory) -> None:
        self.memory = memory

    def spec(self) -> ToolSpec:
        """Return the drop_entry declaration."""
        prompts = Prompts()
        return ToolSpec(
            name=INFINITE_DROP_ENTRY_TOOL_NAME,
            description=prompts.get(Prompt.INFINITE_MEMORY_DROP_ENTRY_TOOL_DESCRIPTION),
            permission=ToolPermission.SAFE,
            input_schema={"type": "object", "properties": {"id": {"type": "string", "description": prompts.get(Prompt.INFINITE_MEMORY_DROP_ENTRY_ID_DESCRIPTION)}}, "required": ["id"], "additionalProperties": False},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Drop the staged entry, or return what to fix; either way the reply ends with the quota line."""
        try:
            message = self.memory.drop(str(call.arguments.get("id")))
        except ToolExecutionError as exc:
            return ToolResult.error(INFINITE_DROP_ENTRY_TOOL_NAME, self.memory.refusal(exc.message))
        return ToolResult.success(INFINITE_DROP_ENTRY_TOOL_NAME, self.memory.answer(message))


__all__ = ["InfiniteAgentMemory", "InfiniteDropEntryTool", "InfiniteEditFileTool", "InfiniteRememberTool", "InfiniteWriteNoteTool"]
