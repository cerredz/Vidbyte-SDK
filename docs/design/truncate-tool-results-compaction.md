"""Context Protocol Header

Description:
    Design document for the truncate_tool_results context compaction strategy.
Purpose:
    Defines the architectural plan, functional requirements, detailed design, and test cases
    for truncating large tool results to conserve context window space while retaining early output data.
Architecture:
    - Overview, goals, high-level and detailed design specifications.
    - Testing plan addressing edge cases, hidden failures, silent failures, and assumptions.
Relations:
    Related to vidbyte.tools.builtins.context.compaction and tests.test_context_compaction_tools.
"""

# Design Doc: Smart Truncation of Tool Results Compaction

**Status:** Draft
**Author:** Codex / Antigravity
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This feature implements a new context compaction method, `truncate_tool_results`, in the `vidbyte-sdk` library. Unlike the existing `strip_tool_result_bodies` strategy (which removes tool-result output entirely and replaces it with a static placeholder), this strategy truncates large tool-result messages to a configurable limit (`max_chars`, default `1000`) and appends a customizable truncation indicator indicating the count of omitted characters. This enables long-running developer agents to preserve the schemas, headers, or initial parts of large tool outputs (such as directory listings, search results, or database dumps) without consuming excessive tokens in the LLM context window.

---

## 2. Goals & Non-Goals

### Goals

- Implement a new compaction mode `truncate_tool_results` in the `CompactionMode` enum.
- Update `ContextCompactionTool` to handle `truncate_tool_results` in its `execute` method, accepting optional inputs `max_chars` and `truncation_indicator`.
- Support dynamic replacement of the `{count}` placeholder in the truncation indicator to reflect the exact number of characters truncated.
- Add complete metadata to the mutated message object (such as original character count and truncated character count).
- Write a full test suite checking edge cases, hidden failure modes, silent failures, and implicit assumptions.

### Non-Goals

- Modifying existing compaction modes like `strip_tool_result_bodies` or `clear_except_system_and_log`.
- Changing how other modules construct `ContextMessage` or handle messages.
- Providing an AI-driven summary within this strategy (which is handled by `summarize_range` / `summarize_oldest_n`).

---

## 3. Background & Context

Currently, the SDK offers `strip_tool_result_bodies` which replaces the entire tool-result content with `"[tool result stripped by compaction]"`. While this is highly effective for reducing token count to an absolute minimum, it removes *all* context. Often, the agent only needs the first few lines of a tool response (such as a list of files or structural output) to remain functional. By providing a smart truncation option, developers can optimize their agents' prompt structures to retain valuable partial context without blowing past context windows.

---

## 4. Requirements

### Functional Requirements

1. The `CompactionMode` enum must be updated to include `truncate_tool_results = "truncate_tool_results"`.
2. The `ContextCompactionTool`'s `spec` declaration must include `truncate_tool_results` in the mode description, and define two optional arguments: `max_chars` (integer) and `truncation_indicator` (string).
3. If `mode` is `truncate_tool_results`, the tool must iterate through all messages:
   - Identify messages where `kind == "tool_result"`.
   - If the content length is strictly greater than `max_chars`, slice the content to `max_chars` and append the `truncation_indicator`.
   - If the `truncation_indicator` contains `{count}`, replace it with the string representation of the number of characters truncated (`original_len - max_chars`).
   - Add metadata fields: `compaction = "truncate_tool_results"`, `original_chars = original_len`, and `truncated_chars = original_len - max_chars`.
4. If a message's content length is less than or equal to `max_chars`, the message must remain unmodified and receive no compaction metadata.
5. If `max_chars` is negative, the tool must return an error response.

### Non-Functional Requirements

- **Performance**: Operation must be synchronous and complete within `<1ms` for standard message lists (up to thousands of messages).
- **Security**: The operation only mutates in-memory message lists within the sandbox of the agent call. No network or filesystem activity is triggered.
- **Observability**: Metadata on compacted messages provides explicit tracing of how much text was removed.

---

## 5. High-Level Design

The context compaction framework uses `ContextCompactionTool` (a subclass of `BaseTool`) which acts upon an injected `ContextState` object. 

```text
[Agent Loop] -> [Calls Tool: compact_context]
                       |
                       v
         [ContextCompactionTool.execute]
                       |
     (dispatches to _truncate_tool_results)
                       |
                       v
     [Mutates Tool Results exceeding max_chars]
                       |
                       v
  [Updates ContextState and returns ToolResult]
```

When the tool is called with `mode="truncate_tool_results"`, it extracts the arguments `max_chars` and `truncation_indicator` (falling back to default values if not supplied), validates them, and invokes a helper method `_truncate_tool_results`. The updated sequence of messages is then written back to the mutable `ContextState`.

---

## 6. Detailed Design

### 6.1 CompactionMode Enum Expansion

**File(s):** `vidbyte/tools/builtins/context/compaction.py`
**Type:** Modified

#### What it does
Registers the new compaction mode in the enum.

#### Interface / API
```python
class CompactionMode(str, Enum):
    ...
    TRUNCATE_TOOL_RESULTS = "truncate_tool_results"
```

---

### 6.2 ContextCompactionTool Class

**File(s):** `vidbyte/tools/builtins/context/compaction.py`
**Type:** Modified

#### What it does
Defines the spec schema, validates parameters, and dispatches the execution logic.

#### Interface / API

```python
class ContextCompactionTool(BaseTool):
    # Added parameters in spec()
    # Added handler in execute()
    # Added private method _truncate_tool_results
```

#### Logic / Algorithm

1. In `spec()`, include two new optional `ToolParameter` declarations:
   - `ToolParameter("max_chars", "integer", "Maximum characters to keep for tool results when truncating.", required=False)`
   - `ToolParameter("truncation_indicator", "string", "Custom indicator suffix or replacement text.", required=False)`
2. In `execute()`, add:
   ```python
   elif mode is CompactionMode.TRUNCATE_TOOL_RESULTS:
       max_chars = call.arguments.get("max_chars", 1000)
       if max_chars is None:
           max_chars = 1000
       else:
           try:
               max_chars = int(max_chars)
           except (ValueError, TypeError):
               return ToolResult.error(self.name, "max_chars must be a valid integer.")
       
       if max_chars < 0:
           return ToolResult.error(self.name, "max_chars must be non-negative.")
           
       truncation_indicator = str(call.arguments.get("truncation_indicator", " [... truncated {count} characters ...]"))
       after = self._truncate_tool_results(before, max_chars, truncation_indicator)
   ```
3. Implement `_truncate_tool_results` as a helper:
   ```python
   def _truncate_tool_results(
       self,
       messages: Sequence[ContextMessage],
       max_chars: int,
       truncation_indicator: str,
   ) -> tuple[ContextMessage, ...]:
       # Truncates tool-result message bodies exceeding max_chars and updates their metadata.
       result = []
       for message in messages:
           if message.kind == "tool_result" and len(message.content) > max_chars:
               count = len(message.content) - max_chars
               formatted = truncation_indicator.replace("{count}", str(count))
               truncated_content = message.content[:max_chars] + formatted
               result.append(
                   dataclasses.replace(
                       message,
                       content=truncated_content,
                       metadata={
                           **dict(message.metadata),
                           "compaction": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                           "original_chars": len(message.content),
                           "truncated_chars": count,
                       },
                   )
               )
           else:
               result.append(message)
       return tuple(result)
   ```

#### Edge Cases & Error Handling

- **Negative `max_chars`**: Validated and returns a clear `ToolResult.error`.
- **String input for `max_chars` that cannot be converted to int**: Validated and returns a clear `ToolResult.error`.
- **Extremely small `max_chars` (e.g., 0)**: Allowed. Cuts the tool result body completely and appends only the indicator.
- **Empty `truncation_indicator`**: Allowed. Performs clean truncation without any suffix.

---

## 7. Data Model Changes

N/A - This change only affects in-memory runtime datatypes (`ContextMessage` / `ContextState`), not persistent databases or schemas.

---

## 8. API Changes

N/A - The SDK tool interface schema is modified (two optional inputs added), but it introduces no breaking API changes and maintains absolute backward compatibility.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/tools/builtins/context/compaction.py` | Add `truncate_tool_results` enum, parameters, and handler implementation. |
| MODIFY | `tests/test_context_compaction_tools.py` | Add unit tests testing the new compaction mode. |

---

## 10. Testing Plan

### Unit Tests

We will add a new test class/methods within `tests/test_context_compaction_tools.py` targeting all required behaviors:

1. **[Edge Case] Zero Max Characters**
   - Verify that when `max_chars=0` is provided, the tool result body becomes empty apart from the truncation indicator.
2. **[Edge Case] Non-Tool-Result Messages**
   - Ensure that system, user, assistant, and general non-tool-result messages (even if they exceed `max_chars` in length) are left completely untouched.
3. **[Hidden Failure] Invalid and Negative Limits**
   - Verify that passing negative bounds (e.g., `max_chars=-10`) or non-numeric strings returns a clean `ToolResult.error` and leaves the state intact.
4. **[Silent Failure] Boundary Length Matches**
   - Verify that if a tool result's character length is exactly equal to `max_chars`, it is not truncated and receives no metadata mutations.
5. **[Hidden Assumption] Placeholder Replacement**
   - Verify that when `{count}` placeholder is used in the indicator, it is correctly replaced with the exact number of characters truncated. If no `{count}` is present, check that the indicator is appended verbatim.

---

## 11. Dependencies & External Services

N/A - No new dependencies are introduced. The strategy utilizes the existing Python standard library and SDK dataclasses.

---

## 12. Rollout & Deployment

- Since this only adds an optional new mode and preserves all existing APIs, rollout is completely safe and fully backward-compatible.

---

## 13. Open Questions

- None. The feature requirement is precise and maps directly to the existing modular compaction system.

---

## 14. Alternatives Considered

### Alternative 1: Stripping completely
- Already exists under `strip_tool_result_bodies`. Stripping is useful when memory pressure is extreme, but it does not support retaining headers or early content. Adding `truncate_tool_results` offers a better middle ground.
