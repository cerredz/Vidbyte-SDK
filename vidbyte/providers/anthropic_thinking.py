"""FILE: vidbyte/providers/anthropic_thinking.py

PURPOSE: Keeps a request from sending Claude a thinking block whose prefix changed after the block was signed. It records the prefix (top-level system, tools, and earlier messages) each thinking or redacted_thinking block was signed under. Before each request, it removes the oldest block whose prefix changed and every thinking block after it, which is the minimum removal Anthropic's troubleshooting guide prescribes, so the request is accepted rather than failing with HTTP 400 ("The block is bound to a different conversation"). Intact blocks before it keep their reasoning.
ROLE IN CODEBASE: AnthropicProvider._create_payload calls AnthropicThinkingBindings.strip_stale on every body it builds, and AnthropicProvider.run_text calls AnthropicThinkingBindings.record with every answer. The gateway transport forwards the adapter's body unchanged, so DIRECT, AUTO, and VIDBYTE_MANAGED calls all pass through this guard. Agents that legitimately change the prefix mid-run, such as InfiniteMemoryAgent (its workspace map is in system) and JevAgent SWARM (launch_swarm joins tools), lose only the reasoning that the API could no longer read.
ARCHITECTURE NOTE: One process-wide record, keyed by a digest of each block's signature (or redacted data). It is not kept per provider, because a runner, a fork, or a resumed agent can replay a history that another runner's provider produced. Prefixes are compared as digests of the parts the API checks: cache_control markers and earlier thinking blocks are not part of the prefix. The record is bounded (least recently used first out), and a lock guards it for agents run on threads.
COMMON MODIFICATION PATTERNS: A new block type that Anthropic binds to its prefix joins _BOUND_TYPES and AnthropicThinkingPrefix.block_key. A change to what the API counts as the prefix changes AnthropicThinkingPrefix and the docs link below together.
WHAT NOT TO DO IN THIS FILE: 1. Do not remove a stale block and keep a later one that was signed with it in place; the API refuses every block after the first invalid one. 2. Do not put back a block an earlier request removed. 3. Do not edit any other block of a turn. 4. Do not mutate the caller's history; the payload's messages are copies, but their content lists are shared, so build new lists.
KNOWN EDGE CASES: A block this process never saw signed (another process, or a record evicted after _CAPACITY newer blocks) is left as it was, which is the behavior before this guard. A removed block stays out even if the prefix later changes back. Under extended (manual) thinking the API expects the final assistant turn to open with thinking, so a removal there can still be refused; adaptive thinking, the default on these models, has no such rule.
RELATED DOCS: https://platform.claude.com/docs/en/build-with-claude/preserved-thinking ("Keeping the prefix unchanged", "What counts as an edit"); https://platform.claude.com/docs/en/build-with-claude/thinking-troubleshooting; docs/design/anthropic-stale-thinking-after-prefix-change.md.
TESTS: tests/test_thinking_block_stale_prefix.py, tests/test_thinking_block_replay_prefix.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

_BOUND_TYPES = ("thinking", "redacted_thinking")
_CAPACITY = 16_384
_REMOVED = b""
_JSON_FORM: dict[str, Any] = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False, "default": str}


class AnthropicThinkingPrefix:
    """Digests of the parts of a request Anthropic's prefix check reads, and the record key of one thinking block."""

    @classmethod
    def digests(cls, payload: Mapping[str, Any]) -> list[bytes]:
        """Return digests where entry i covers system, tools, and messages[:i], ignoring cache_control and thinking blocks."""
        # Start from the top-level system prompt and the tool list, then add one message at a time,
        # so every message position gets the digest of everything before it.
        running = hashlib.sha256(json.dumps([cls._canonical(payload.get("system")), cls._canonical(payload.get("tools"))], **_JSON_FORM).encode())
        digests = [running.digest()]
        messages = payload.get("messages")
        for message in messages if isinstance(messages, list) else ():
            running.update(b"," + json.dumps(cls._canonical(message), **_JSON_FORM).encode())
            digests.append(running.digest())
        return digests

    @staticmethod
    def block_key(block: Mapping[str, Any]) -> bytes | None:
        """Identify a thinking block by its signature and a redacted one by its data; anything else has no key."""
        kind = block.get("type")
        token = block.get("signature") if kind == "thinking" else block.get("data") if kind == "redacted_thinking" else None
        if not isinstance(token, str) or not token:
            return None
        return hashlib.sha256(f"{kind}:{token}".encode()).digest()

    @staticmethod
    def _canonical(value: Any) -> Any:
        # The value without cache_control markers and thinking blocks, which the API leaves out of the check.
        if isinstance(value, Mapping):
            return {key: AnthropicThinkingPrefix._canonical(item) for key, item in value.items() if key != "cache_control"}
        if isinstance(value, list):
            return [AnthropicThinkingPrefix._canonical(item) for item in value if not (isinstance(item, Mapping) and item.get("type") in _BOUND_TYPES)]
        return value


class AnthropicThinkingBindings:
    """The prefix each Claude thinking block was signed under, and the removal of blocks whose prefix has since changed."""

    # @intent one-record-per-process
    # Shared on purpose: a fork, a resumed agent, or another runner can
    # replay a history this process signed through a different provider.
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _signed: ClassVar[OrderedDict[bytes, bytes]] = OrderedDict()

    @classmethod
    def strip_stale(cls, payload: dict[str, Any]) -> int:
        """Remove the oldest thinking block whose prefix changed and every thinking block after it, plus every block an earlier request removed; return how many."""
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return 0
        with cls._lock:
            # Work out the prefix every message position has in this request.
            prefixes = AnthropicThinkingPrefix.digests(payload)

            # Find each thinking block the history sends back. The API refuses the oldest block whose
            # prefix changed since it was signed, and every thinking block after it, so those go, as
            # the docs' fix says; so does any block an earlier request removed. Earlier intact blocks stay.
            located = cls._locate(messages)
            removed = cls._stale(located, prefixes)
            if not removed:
                return 0

            # Take those blocks out of their turns; every other block of each turn stays where it was.
            cls._remove(messages, removed)

            # Remember the removed blocks, so a later request never puts one back.
            cls._mark_removed(removed)

        # Say that reasoning was dropped, as the docs ask of code that edits a caller's history.
        logger.info("anthropic_stale_thinking_removed blocks=%d", len(removed))
        return len(removed)

    @classmethod
    def record(cls, payload: Mapping[str, Any], answer: Mapping[str, Any]) -> None:
        """Record the prefix of this request as the one every thinking block in its answer was signed under."""
        content = answer.get("content")
        keys = [key for key in (AnthropicThinkingPrefix.block_key(block) for block in content if isinstance(block, Mapping)) if key is not None] if isinstance(content, list) else []
        if not keys:
            return
        with cls._lock:
            # The answer's blocks come after every message of the request, so their prefix is the whole request.
            prefix = AnthropicThinkingPrefix.digests(payload)[-1]
            for key in keys:
                cls._signed[key] = prefix
                cls._signed.move_to_end(key)
            while len(cls._signed) > _CAPACITY:
                cls._signed.popitem(last=False)

    @staticmethod
    def _locate(messages: list[Any]) -> list[tuple[int, int, bytes | None]]:
        # Every thinking block in the history, oldest first: (message index, block index, record key).
        located = []
        for message_index, message in enumerate(messages):
            content = message.get("content") if isinstance(message, Mapping) else None
            for block_index, block in enumerate(content if isinstance(content, list) else ()):
                if isinstance(block, Mapping) and block.get("type") in _BOUND_TYPES:
                    located.append((message_index, block_index, AnthropicThinkingPrefix.block_key(block)))
        return located

    @classmethod
    def _stale(cls, located: list[tuple[int, int, bytes | None]], prefixes: list[bytes]) -> list[tuple[int, int, bytes | None]]:
        # The blocks to leave out: each one already removed, and from the oldest block signed under
        # another prefix onward, every block. A block this process never saw signed has no record.
        records = [cls._signed.get(key) if key is not None else None for _, _, key in located]
        changed = next((position for position, (message_index, _, _) in enumerate(located) if records[position] not in (None, _REMOVED) and records[position] != prefixes[message_index]), len(located))
        return [entry for position, entry in enumerate(located) if position >= changed or records[position] == _REMOVED]

    @staticmethod
    def _remove(messages: list[Any], removed: list[tuple[int, int, bytes | None]]) -> None:
        # Give each touched message a new content list without its removed blocks; the caller's lists stay as they were.
        by_message: dict[int, set[int]] = {}
        for message_index, block_index, _ in removed:
            by_message.setdefault(message_index, set()).add(block_index)
        for message_index, block_indexes in by_message.items():
            message = dict(messages[message_index])
            message["content"] = [block for index, block in enumerate(message["content"]) if index not in block_indexes]
            messages[message_index] = message

    @classmethod
    def _mark_removed(cls, removed: list[tuple[int, int, bytes | None]]) -> None:
        # Record each removed block as removed instead of by its prefix.
        for _, _, key in removed:
            if key is not None:
                cls._signed[key] = _REMOVED
                cls._signed.move_to_end(key)
        while len(cls._signed) > _CAPACITY:
            cls._signed.popitem(last=False)


__all__ = ["AnthropicThinkingBindings", "AnthropicThinkingPrefix"]
