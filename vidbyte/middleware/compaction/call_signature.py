"""FILE: vidbyte/middleware/compaction/call_signature.py

PURPOSE: Builds an id-free signature (tool names plus arguments) for one tool-call message.
ROLE IN CODEBASE: Gives DeduplicateToolCallsCompaction a key that matches repeated calls across provider wires.
ARCHITECTURE NOTE: Reads the raw provider message the engine stores in ContextMessage.metadata["provider_message"]; stdlib only.
COMMON MODIFICATION PATTERNS: Add a provider shape by extending the list of (name, arguments) pairs, never by keying on ids.
KNOWN EDGE CASES: Without a provider message the ContextMessage content is the key; non-call messages return None.
RELATED DOCS: docs/design/dedupe-tool-calls-ignore-ids.md
TESTS: tests/test_deterministic_compaction_middleware.py, tests/test_context_compaction_tools.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from vidbyte.lib.dataclasses.context import ContextMessage


def tool_call_signature(message: ContextMessage) -> str | None:
    # Returns the comparable key for a tool-call message, or None when the message makes no tool call.
    # @intent dedupe-ignores-call-ids
    # Every provider stamps each call with a fresh id, so two identical calls only compare equal when the
    # key is the tool names and arguments alone; keying on the rendered message would never dedupe anything.
    raw = message.metadata.get("provider_message") if isinstance(message.metadata, Mapping) else None
    raw = raw if isinstance(raw, Mapping) else {}
    calls, blocks, parts = (raw.get(key) if isinstance(raw.get(key), list) else [] for key in ("tool_calls", "content", "parts"))
    functions = [c.get("function") for c in calls if isinstance(c, Mapping)]
    gemini = [p.get("functionCall") or p.get("function_call") for p in parts if isinstance(p, Mapping)]
    signature = [[f.get("name"), f.get("arguments")] for f in functions if isinstance(f, Mapping)]
    signature += [[b.get("name"), b.get("input")] for b in blocks if isinstance(b, Mapping) and b.get("type") == "tool_use"]
    signature += [[f.get("name"), f.get("args")] for f in gemini if isinstance(f, Mapping)]
    if signature:
        return json.dumps(signature, sort_keys=True, default=str)
    return message.content if message.kind == "tool_call" else None
