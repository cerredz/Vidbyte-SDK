# Design Doc: Deterministic Compaction Middleware Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

This feature expands the existing Vidbyte SDK middleware compaction layer with deterministic, code-only compaction methods that do not call another model. The current middleware compaction engine already handles the original tool-result, message-history, and explicit summarization modes; this change adds token-budget trimming, provider-boundary trimming, deletion by id/range, sliding-window tool-output compaction, exclusion-based tool-output clearing, head/tail previews, mechanical bloat scrubbing, deterministic backref summaries, rule-based pruning, salience scoring, lexical query filtering, and snapshot branch trimming.

---

## 2. Goals & Non-Goals

### Goals

- Add deterministic compaction modes to the existing `vidbyte.middleware.compaction` engine instead of reintroducing model-visible compaction tools.
- Keep all new behavior model-free, provider-call-free, and dependency-free.
- Preserve raw tool results in runtime metadata when model-visible tool outputs are compacted.
- Preserve provider message boundaries well enough that assistant/tool pairs are not corrupted by trimming.
- Expose ergonomic factory methods on `ToolResultCompactionMiddleware` and `MessageHistoryCompactionMiddleware`.
- Keep `ContextCompactionTool` as a legacy/manual wrapper over the same shared engine.
- Add focused unit, integration, and script verification coverage for each new mode.
- Update README and SDK skill docs so future agents know deterministic compactions belong in middleware.

### Non-Goals

- Do not add model-backed summarization, semantic fact extraction, procedural skill extraction, learned prompt compression, embeddings, vector search, or provider calls.
- Do not implement `parallel_block_compaction` or `async_background_compaction` in this PR; those are orchestration/scheduling concerns and need a separate runtime design.
- Do not change provider-specific tool-call parsing or provider tool schema formatting.
- Do not change non-linear runtime behavior.
- Do not remove or deprecate `ContextCompactionTool`.
- Do not add third-party tokenizers. Token-budget trimming will use a deterministic approximate counter by default and allow an injected counter.

---

## 3. Background & Context

- The SDK currently has a middleware compaction package under `vidbyte/middleware/compaction/`.
- `CompactionMode`, `BaseCompaction`, `CompactionStats`, and `Summarizer` live in `vidbyte/middleware/compaction/base.py`.
- `ContextCompactionEngine` lives in `vidbyte/middleware/compaction/engine.py` and compacts generic `ContextMessage` records, provider message dictionaries, and single `ToolResult` objects.
- Strategy classes live in `vidbyte/middleware/compaction/strategies.py`.
- Public middleware wrappers live in `vidbyte/middleware/compaction/context_compaction.py` and are re-exported from middleware public surfaces.
- `MiddlewareTransform` and `MiddlewareDecision.continue_(transform=...)` already exist.
- `AgentRuntime` already applies `before_model_call` provider-message transforms and `after_tool_call` model-visible tool-result transforms.
- Audit caveat: I fetched `origin/main`, but local `main` was dirty and behind by 8 commits, so I did not pull. During this Phase 2 pass, the checked-out branch later changed to `feat/gemini-payload-transport-retries`. Implementation must start from a clean, updated worktree after approval.

---

## 4. Requirements

### Functional Requirements

1. `CompactionMode` must add deterministic modes:
   - `trim_to_token_budget`
   - `trim_with_provider_boundaries`
   - `delete_messages_by_id_or_range`
   - `tool_output_sliding_window`
   - `tool_result_clearing_with_exclusions`
   - `head_tail_tool_preview`
   - `mechanical_bloat_scrubber`
   - `summary_with_backrefs`
   - `selective_context_pruning`
   - `salience_score_eviction`
   - `query_relevance_filter`
   - `context_snapshot_branch_trim`
2. `ContextCompactionEngine.compact_messages(...)` must support all new modes for generic `ContextMessage` records.
3. `ContextCompactionEngine.compact_provider_messages(...)` must support all new message-history modes where provider-message conversion supplies enough structure.
4. `ContextCompactionEngine.compact_tool_result(...)` must support `tool_result_clearing_with_exclusions`, `head_tail_tool_preview`, and `mechanical_bloat_scrubber` for single tool outputs.
5. Token-budget trimming must use an approximate deterministic counter by default.
6. Token-budget trimming must accept an optional injected token counter callable.
7. Provider-boundary trimming must preserve system messages and avoid keeping orphaned tool-result messages when their paired tool call was removed.
8. Delete-by-id/range compaction must support provider indexes, explicit ids, and inclusive numeric ranges.
9. Tool-output sliding-window compaction must keep the newest N tool-result messages raw and compact older tool-result messages by truncate, strip, clear, or head/tail preview behavior.
10. Exclusion-based clearing must clear tool outputs except for configured tool names, tool ids, or kinds.
11. Head/tail preview must keep deterministic prefix and suffix portions and include omitted-character metadata.
12. Mechanical bloat scrubbing must replace ANSI escape sequences, long base64-like blobs, repeated identical lines, and oversized JSON/string payloads using deterministic rules.
13. Summary-with-backrefs must create a deterministic summary manifest with message indexes, roles, kinds, character counts, and optional excerpts; it must not attempt semantic summarization.
14. Selective context pruning must remove empty, duplicate, boilerplate, or low-information messages using deterministic rules.
15. Salience-score eviction must score messages deterministically from role, kind, recency, error status, pin metadata, and content length, then keep the highest-ranked messages while preserving final output order.
16. Query-relevance filtering must use lexical term overlap against a configured query or `ctx.message`.
17. Snapshot branch trimming must keep messages whose metadata matches the active branch/snapshot ancestry and remove inactive sibling branches.
18. `ToolResultCompactionMiddleware` must add factory methods for clear-except, head/tail preview, and bloat scrubbing.
19. `MessageHistoryCompactionMiddleware` must add factory methods for every new message-history mode.
20. All new factory methods must validate constructor arguments eagerly and raise `ValueError` for invalid inputs.
21. Existing compaction modes and tests must continue to pass.
22. Existing public imports must continue to work.
23. README and skills must document the new deterministic modes as middleware features.
24. The executable verification script must cover every test case in Section 10.

### Non-Functional Requirements

- **Performance:** Default implementations must be O(n) over message count plus O(total text length) for scrubbers.
- **Reliability:** Invalid mode options must fail before mutating state.
- **Security:** Clearing/hiding modes must not leak raw compacted tool output into model-visible provider messages.
- **Compatibility:** Provider messages with unknown shapes must be preserved unless explicitly selected by id/range.
- **Dependency control:** No new dependencies.
- **Observability:** Compacted messages/results must carry metadata with mode, original sizes, removed counts, and relevant selection decisions.
- **Testability:** All logic must be testable with fake messages, fake tools, fake runners, and fake token counters.

---

## 5. High-Level Design

The change extends the existing class-based compaction engine rather than introducing a new middleware architecture. New `BaseCompaction` subclasses will be added to `vidbyte/middleware/compaction/strategies.py`, and `ContextCompactionEngine._build_strategy(...)` will dispatch the new `CompactionMode` values to those classes. Tool-result-specific behavior will be added to `ContextCompactionEngine.compact_tool_result(...)` where the runtime has a single `ToolCall` and `ToolResult`.

Factory methods on `ToolResultCompactionMiddleware` and `MessageHistoryCompactionMiddleware` will provide the public API. The runtime will continue to invoke them through existing `after_tool_call` and `before_model_call` hooks. No runtime hook expansion is needed for this PR.

```text
Agent middleware hook
  -> ToolResultCompactionMiddleware.after_tool_call(...)
      -> ContextCompactionEngine.compact_tool_result(...)
      -> MiddlewareTransform(model_visible_tool_result=...)

Agent middleware hook
  -> MessageHistoryCompactionMiddleware.before_model_call(...)
      -> ContextCompactionEngine.compact_provider_messages(...)
      -> MiddlewareTransform(provider_messages=...)
```

The key design decision is to treat these as deterministic runtime transforms. If a proposed method needs semantic understanding, background scheduling, vector search, or hidden provider calls, it stays out of this PR.

---

## 6. Detailed Design

### 6.1 Compaction Modes and Shared Base Contracts

**File(s):** `vidbyte/middleware/compaction/base.py`
**Type:** Modified

#### What it does

Adds new deterministic `CompactionMode` enum values and optional token-counter typing.

#### Interface / API

```python
class CompactionMode(str, Enum):
    TRIM_TO_TOKEN_BUDGET = "trim_to_token_budget"
    TRIM_WITH_PROVIDER_BOUNDARIES = "trim_with_provider_boundaries"
    DELETE_MESSAGES_BY_ID_OR_RANGE = "delete_messages_by_id_or_range"
    TOOL_OUTPUT_SLIDING_WINDOW = "tool_output_sliding_window"
    TOOL_RESULT_CLEARING_WITH_EXCLUSIONS = "tool_result_clearing_with_exclusions"
    HEAD_TAIL_TOOL_PREVIEW = "head_tail_tool_preview"
    MECHANICAL_BLOAT_SCRUBBER = "mechanical_bloat_scrubber"
    SUMMARY_WITH_BACKREFS = "summary_with_backrefs"
    SELECTIVE_CONTEXT_PRUNING = "selective_context_pruning"
    SALIENCE_SCORE_EVICTION = "salience_score_eviction"
    QUERY_RELEVANCE_FILTER = "query_relevance_filter"
    CONTEXT_SNAPSHOT_BRANCH_TRIM = "context_snapshot_branch_trim"
```

#### Logic / Algorithm

1. Append new enum values without changing existing names.
2. Add a `TokenCounter` protocol or type alias if useful for constructor typing.
3. Keep `CompactionStats` unchanged unless strategy-specific metadata requires no new top-level fields.

#### Edge Cases & Error Handling

- Unknown raw strings still raise through `CompactionMode(str(mode))`.
- Existing enum values remain stable for legacy imports and tests.

---

### 6.2 Deterministic Message Strategies

**File(s):** `vidbyte/middleware/compaction/strategies.py`
**Type:** Modified

#### What it does

Adds one class per deterministic message-history compaction strategy.

#### Interface / API

```python
class TrimToTokenBudgetCompaction(BaseCompaction): ...
class TrimWithProviderBoundariesCompaction(BaseCompaction): ...
class DeleteMessagesByIdOrRangeCompaction(BaseCompaction): ...
class ToolOutputSlidingWindowCompaction(BaseCompaction): ...
class ToolResultClearingWithExclusionsCompaction(BaseCompaction): ...
class HeadTailToolPreviewCompaction(BaseCompaction): ...
class MechanicalBloatScrubberCompaction(BaseCompaction): ...
class SummaryWithBackrefsCompaction(BaseCompaction): ...
class SelectiveContextPruningCompaction(BaseCompaction): ...
class SalienceScoreEvictionCompaction(BaseCompaction): ...
class QueryRelevanceFilterCompaction(BaseCompaction): ...
class ContextSnapshotBranchTrimCompaction(BaseCompaction): ...
```

#### Logic / Algorithm

1. `TrimToTokenBudgetCompaction` preserves system messages, then walks non-system messages newest to oldest until the token budget is met, returning messages in original order.
2. `TrimWithProviderBoundariesCompaction` builds logical groups for assistant tool calls plus their tool results, then trims whole groups from the oldest side.
3. `DeleteMessagesByIdOrRangeCompaction` removes messages matching explicit ids or inclusive indexes.
4. `ToolOutputSlidingWindowCompaction` identifies tool-result messages, keeps the newest `keep_recent` tool results raw, and compacts older tool results using a configured sub-mode.
5. `ToolResultClearingWithExclusionsCompaction` replaces tool-result bodies with a placeholder unless the detected tool name/id is excluded.
6. `HeadTailToolPreviewCompaction` replaces long tool-result bodies with `head + indicator + tail`.
7. `MechanicalBloatScrubberCompaction` applies deterministic scrubbers for ANSI escapes, base64-like blobs, repeated lines, and oversized scalar strings.
8. `SummaryWithBackrefsCompaction` replaces selected messages with a compact manifest containing indexes, roles, kinds, character counts, optional excerpts, and backref metadata.
9. `SelectiveContextPruningCompaction` removes empty messages, exact duplicates, configured boilerplate patterns, and low-information messages.
10. `SalienceScoreEvictionCompaction` scores messages, keeps required/system/recent messages, then keeps highest remaining scores under message/token limits and restores original order.
11. `QueryRelevanceFilterCompaction` tokenizes query and message text into lowercase word terms, scores overlap, keeps required/system/recent messages, then keeps matching messages.
12. `ContextSnapshotBranchTrimCompaction` keeps messages whose metadata branch/snapshot values match the active branch and optional ancestors.

#### Edge Cases & Error Handling

- Token budgets less than or equal to zero raise `ValueError`.
- Negative keep counts raise `ValueError`.
- Empty messages return empty messages.
- Unknown provider/message shapes are treated as ordinary messages.
- If all non-system messages would be removed, required/system messages still remain.
- Boundary trimming must not return an orphan `tool_result` without its triggering call group.

---

### 6.3 Engine Dispatch and Provider Message Metadata

**File(s):** `vidbyte/middleware/compaction/engine.py`
**Type:** Modified

#### What it does

Dispatches new modes and enriches provider-message conversion with deterministic ids, indexes, and best-effort tool names.

#### Interface / API

```python
class ContextCompactionEngine:
    async def compact_messages(self, messages, *, mode, options=None): ...
    async def compact_provider_messages(self, messages, *, mode, options=None): ...
    def compact_tool_result(self, call, result, *, mode, options=None): ...
```

#### Logic / Algorithm

1. Add new mode branches in `_build_strategy(...)`.
2. Extend `_provider_to_context_message(...)` metadata with `provider_index`, `provider_id`, `tool_name`, and original `provider_message`.
3. Keep `_context_message_to_provider(...)` update-only behavior for known content shapes.
4. Add tool-result single-output handling for clearing, head/tail preview, and mechanical bloat scrubbing.
5. Keep raw `ToolResult` unchanged when a compact mode determines no compaction is needed.

#### Edge Cases & Error Handling

- Invalid option values raise `ValueError` before any state is replaced.
- Provider messages that cannot expose ids still support range/index deletion.
- Mechanical scrubber must cap replacements without throwing on malformed text.

---

### 6.4 Public Middleware Factory Methods

**File(s):** `vidbyte/middleware/compaction/context_compaction.py`, `vidbyte/middleware/builtins/context_compaction.py`
**Type:** Modified

#### What it does

Adds public factory methods for deterministic compaction modes on existing middleware classes.

#### Interface / API

```python
ToolResultCompactionMiddleware.clear_except(exclude_tools=(), placeholder="[tool result cleared by compaction]")
ToolResultCompactionMiddleware.head_tail_preview(head_chars=400, tail_chars=200)
ToolResultCompactionMiddleware.scrub_bloat()

MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens, token_counter=None, preserve_system=True)
MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_messages=None, max_tokens=None, token_counter=None)
MessageHistoryCompactionMiddleware.delete_by_id_or_range(message_ids=(), start=None, end=None)
MessageHistoryCompactionMiddleware.tool_output_sliding_window(keep_recent=2, mode="truncate_tool_results", max_chars=600)
MessageHistoryCompactionMiddleware.clear_tool_outputs_except(exclude_tools=(), placeholder="[tool result cleared by compaction]")
MessageHistoryCompactionMiddleware.head_tail_tool_preview(head_chars=400, tail_chars=200)
MessageHistoryCompactionMiddleware.scrub_bloat()
MessageHistoryCompactionMiddleware.summary_with_backrefs(start=None, end=None, excerpt_chars=120)
MessageHistoryCompactionMiddleware.selective_prune(remove_empty=True, remove_duplicates=True, boilerplate_patterns=())
MessageHistoryCompactionMiddleware.salience_score_eviction(max_messages, max_tokens=None, token_counter=None)
MessageHistoryCompactionMiddleware.query_relevance_filter(query=None, max_messages=None, min_score=1)
MessageHistoryCompactionMiddleware.snapshot_branch_trim(active_branch, include_ancestors=True)
```

#### Logic / Algorithm

1. Each factory builds the existing middleware class with a `CompactionMode` and options.
2. Constructor validation remains in `_validate_options()`.
3. `query_relevance_filter(query=None, ...)` falls back to `ctx.message` at hook time if `query` is not configured.
4. `builtins/context_compaction.py` remains a re-export wrapper unless its header/docs need updating.

#### Edge Cases & Error Handling

- Empty `active_branch` raises `ValueError`.
- `head_chars=0` and `tail_chars=0` are allowed only if the indicator is non-empty.
- `max_messages` and `max_tokens` cannot both be omitted for trimming/eviction modes that need a limit.
- Invalid sliding-window sub-modes raise `ValueError`.

---

### 6.5 Legacy ContextCompactionTool Compatibility

**File(s):** `vidbyte/tools/builtins/context/compaction.py`, `vidbyte/tools/builtins/context/__init__.py`
**Type:** Modified

#### What it does

Keeps `compact_context` available while expanding its mode list and optional parameters for deterministic modes that can operate over `ContextState.messages()`.

#### Interface / API

```python
ToolCall("compact_context", {"mode": "head_tail_tool_preview", "head_chars": 100, "tail_chars": 50})
```

#### Logic / Algorithm

1. Update tool description mode list.
2. Add optional `ToolParameter` entries for new generic options such as `max_tokens`, `message_ids`, `start`, `end`, `head_chars`, `tail_chars`, `query`, and `active_branch`.
3. Keep execution path delegated to `ContextCompactionEngine`.
4. Preserve old error shape for bad modes and missing summarizers.

#### Edge Cases & Error Handling

- The legacy tool should return `ToolResult.error(...)` for invalid values instead of raising through the tool boundary.
- New modes that require provider-only metadata should still work as generic message transforms where possible and preserve unknown metadata.

---

### 6.6 Public Exports and Documentation

**File(s):** `vidbyte/middleware/compaction/__init__.py`, `vidbyte/context/compaction.py`, `README.md`, `skills/vidbyte-sdk/middleware.md`, `skills/vidbyte-sdk-doc/SKILL.md`
**Type:** Modified

#### What it does

Updates public exports and documentation to describe the deterministic compaction expansion.

#### Interface / API

```python
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware, ToolResultCompactionMiddleware
```

#### Logic / Algorithm

1. Export new strategy classes from `vidbyte.middleware.compaction` only if they are intended advanced public API.
2. Keep `CompactionMode` available from `vidbyte.context.compaction` and legacy tool imports.
3. README adds examples for token-budget trimming and head/tail tool previews.
4. Middleware skill lists deterministic compaction categories and warns that semantic/model compaction is out of scope.
5. SDK doc skill updates the package reference and test map.

#### Edge Cases & Error Handling

- Do not add model-dependent claims to docs.
- Do not document unimplemented parallel/background orchestration as available.

---

## 7. Data Model Changes

### 7.1 `CompactionMode`

**Change type:** Modified

```python
class CompactionMode(str, Enum):
    TRIM_TO_TOKEN_BUDGET = "trim_to_token_budget"
    TRIM_WITH_PROVIDER_BOUNDARIES = "trim_with_provider_boundaries"
    DELETE_MESSAGES_BY_ID_OR_RANGE = "delete_messages_by_id_or_range"
    TOOL_OUTPUT_SLIDING_WINDOW = "tool_output_sliding_window"
    TOOL_RESULT_CLEARING_WITH_EXCLUSIONS = "tool_result_clearing_with_exclusions"
    HEAD_TAIL_TOOL_PREVIEW = "head_tail_tool_preview"
    MECHANICAL_BLOAT_SCRUBBER = "mechanical_bloat_scrubber"
    SUMMARY_WITH_BACKREFS = "summary_with_backrefs"
    SELECTIVE_CONTEXT_PRUNING = "selective_context_pruning"
    SALIENCE_SCORE_EVICTION = "salience_score_eviction"
    QUERY_RELEVANCE_FILTER = "query_relevance_filter"
    CONTEXT_SNAPSHOT_BRANCH_TRIM = "context_snapshot_branch_trim"
```

**Migration strategy:** Backward-compatible enum expansion.

- Forward migration: Add enum members and dispatch branches.
- Rollback plan: Remove enum members, strategy classes, factory methods, and tests.

### 7.2 Provider Message Metadata

**Change type:** Modified internal metadata

```python
ContextMessage.metadata = {
    "provider_message": original_message,
    "provider_index": index,
    "provider_id": id_or_call_id,
    "tool_name": detected_tool_name,
}
```

**Migration strategy:** Internal in-memory metadata only.

- Forward migration: Add metadata during provider-message conversion.
- Rollback plan: Remove metadata fields and restore current conversion.

---

## 8. API Changes

### 8.1 Python SDK: Deterministic Tool Result Compaction

**Change type:** Modified

**Request:**

```python
agent = Agent(
    name="worker",
    system_prompt="Work.",
    tools=[lookup],
    middleware=[
        ToolResultCompactionMiddleware.head_tail_preview(head_chars=200, tail_chars=120),
        ToolResultCompactionMiddleware.scrub_bloat(),
    ],
)
```

**Response:**

```python
# Runtime sends compacted tool output to the model and keeps raw tool output in metadata.
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Negative `head_chars`, `tail_chars`, or limits raise `ValueError`. |
| N/A | Internal tools are skipped by default. |

### 8.2 Python SDK: Deterministic Message History Compaction

**Change type:** Modified

**Request:**

```python
agent = Agent(
    name="worker",
    system_prompt="Work.",
    middleware=[
        MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens=8000),
        MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_messages=30),
    ],
)
```

**Response:**

```python
# Runner receives bounded provider messages through MiddlewareTransform.provider_messages.
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing limits for limit-based modes raise `ValueError`. |
| N/A | Unknown message ids are ignored unless every selection is empty, in which case messages are preserved. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/deterministic-compaction-middleware-expansion.md` | Design doc for this feature |
| CREATE | `tests/test_deterministic_compaction_middleware.py` | Unit and integration tests for new deterministic modes |
| CREATE | `scripts/test-deterministic-compaction-middleware.py` | Required script verification for Section 10 |
| MODIFY | `vidbyte/middleware/compaction/base.py` | Add new `CompactionMode` values and token counter typing |
| MODIFY | `vidbyte/middleware/compaction/strategies.py` | Add deterministic message-level compaction strategy classes |
| MODIFY | `vidbyte/middleware/compaction/engine.py` | Dispatch new strategies and support provider metadata/tool-result modes |
| MODIFY | `vidbyte/middleware/compaction/context_compaction.py` | Add public middleware factory methods and validation |
| MODIFY | `vidbyte/middleware/compaction/__init__.py` | Export advanced strategy classes if public |
| MODIFY | `vidbyte/middleware/builtins/context_compaction.py` | Update re-export header/docs if needed |
| MODIFY | `vidbyte/context/compaction.py` | Re-export any new shared public contracts |
| MODIFY | `vidbyte/tools/builtins/context/compaction.py` | Update legacy tool mode list and option parameters |
| MODIFY | `vidbyte/tools/builtins/context/__init__.py` | Preserve/re-export expanded `CompactionMode` surface |
| MODIFY | `tests/test_context_compaction_middleware.py` | Add focused compatibility tests around existing middleware behavior |
| MODIFY | `tests/test_context_compaction_tools.py` | Add legacy tool coverage for new deterministic modes |
| MODIFY | `README.md` | Document deterministic compaction middleware usage |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | Add implementation/user guidance for deterministic compaction modes |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Update repository reference and test map |

Summary: 3 files created, 14 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

Add `tests/test_deterministic_compaction_middleware.py` with:

- `[Edge Case] TrimToTokenBudgetCompaction keeps empty messages empty`.
- `[Edge Case] TrimToTokenBudgetCompaction with exact budget keeps all messages`.
- `[Hidden Failure] TrimToTokenBudgetCompaction preserves system messages even when budget is tiny`.
- `[Silent Failure] TrimToTokenBudgetCompaction returns kept messages in original order, not reverse scoring order`.
- `[Hidden Assumption] TrimToTokenBudgetCompaction uses injected token_counter when supplied`.
- `[Edge Case] TrimWithProviderBoundariesCompaction with no tool messages behaves like keep-last trimming`.
- `[Hidden Failure] TrimWithProviderBoundariesCompaction does not return orphan tool_result messages`.
- `[Silent Failure] TrimWithProviderBoundariesCompaction removes whole oldest tool groups before newer groups`.
- `[Hidden Assumption] Provider-boundary grouping tolerates unknown provider dictionaries`.
- `[Edge Case] DeleteMessagesByIdOrRange with empty ids and no range keeps messages unchanged`.
- `[Hidden Failure] DeleteMessagesByIdOrRange ignores missing ids without deleting unrelated messages`.
- `[Silent Failure] DeleteMessagesByIdOrRange treats end index inclusively as documented`.
- `[Hidden Assumption] DeleteMessagesByIdOrRange can delete by provider_index metadata even without provider_id`.
- `[Edge Case] ToolOutputSlidingWindowCompaction with keep_recent=0 compacts all tool results`.
- `[Hidden Failure] ToolOutputSlidingWindowCompaction preserves non-tool messages`.
- `[Silent Failure] ToolOutputSlidingWindowCompaction keeps newest tool results raw, not oldest ones`.
- `[Hidden Assumption] ToolOutputSlidingWindowCompaction validates unsupported sub-mode values`.
- `[Edge Case] ToolResultClearingWithExclusionsCompaction with empty exclusions clears every tool result`.
- `[Hidden Failure] ToolResultClearingWithExclusionsCompaction does not clear excluded tool names`.
- `[Silent Failure] ToolResultClearingWithExclusionsCompaction records original_chars metadata`.
- `[Hidden Assumption] ToolResultClearingWithExclusionsCompaction treats absent tool name as non-excluded`.
- `[Edge Case] HeadTailToolPreviewCompaction with short content leaves content unchanged`.
- `[Hidden Failure] HeadTailToolPreviewCompaction with head=0 keeps only tail and indicator`.
- `[Silent Failure] HeadTailToolPreviewCompaction computes omitted character count correctly`.
- `[Hidden Assumption] HeadTailToolPreviewCompaction rejects negative head/tail sizes`.
- `[Edge Case] MechanicalBloatScrubberCompaction handles content with no bloat unchanged`.
- `[Hidden Failure] MechanicalBloatScrubberCompaction removes ANSI escape sequences`.
- `[Silent Failure] MechanicalBloatScrubberCompaction replaces long base64-like blobs without deleting surrounding text`.
- `[Hidden Assumption] MechanicalBloatScrubberCompaction repeated-line limit keeps the first occurrences`.
- `[Edge Case] SummaryWithBackrefsCompaction with empty selected range keeps messages unchanged`.
- `[Hidden Failure] SummaryWithBackrefsCompaction records backref indexes in metadata`.
- `[Silent Failure] SummaryWithBackrefsCompaction counts characters from original messages, not compacted text`.
- `[Hidden Assumption] SummaryWithBackrefsCompaction uses excerpts only up to excerpt_chars`.
- `[Edge Case] SelectiveContextPruningCompaction preserves a single non-empty message`.
- `[Hidden Failure] SelectiveContextPruningCompaction removes exact duplicates but keeps first occurrence`.
- `[Silent Failure] SelectiveContextPruningCompaction does not remove system messages as boilerplate`.
- `[Hidden Assumption] SelectiveContextPruningCompaction supports configured boilerplate regex strings`.
- `[Edge Case] SalienceScoreEvictionCompaction with max_messages greater than count keeps all messages`.
- `[Hidden Failure] SalienceScoreEvictionCompaction preserves pinned messages from metadata`.
- `[Silent Failure] SalienceScoreEvictionCompaction returns selected messages in original chronology`.
- `[Hidden Assumption] SalienceScoreEvictionCompaction gives tool errors higher priority than tool successes`.
- `[Edge Case] QueryRelevanceFilterCompaction with empty query keeps required/system/recent messages only`.
- `[Hidden Failure] QueryRelevanceFilterCompaction keeps messages sharing lexical terms with query`.
- `[Silent Failure] QueryRelevanceFilterCompaction applies min_score exactly, not greater-than-only`.
- `[Hidden Assumption] QueryRelevanceFilterCompaction lowercases and tokenizes punctuation deterministically`.
- `[Edge Case] ContextSnapshotBranchTrimCompaction with no branch metadata preserves messages`.
- `[Hidden Failure] ContextSnapshotBranchTrimCompaction removes inactive sibling branch messages`.
- `[Silent Failure] ContextSnapshotBranchTrimCompaction keeps ancestor branch messages when include_ancestors=True`.
- `[Hidden Assumption] ContextSnapshotBranchTrimCompaction rejects empty active_branch`.

Middleware factory and tool-result tests:

- `[Edge Case] ToolResultCompactionMiddleware.head_tail_preview skips internal tools by default`.
- `[Hidden Failure] ToolResultCompactionMiddleware.clear_except preserves excluded tool raw output`.
- `[Silent Failure] ToolResultCompactionMiddleware.scrub_bloat returns transformed visible result while raw result remains unchanged`.
- `[Hidden Assumption] MessageHistoryCompactionMiddleware.query_relevance_filter without explicit query uses ctx.message`.
- `[Hidden Assumption] All new factory methods reject invalid constructor values before runtime`.

Legacy tool tests in `tests/test_context_compaction_tools.py`:

- `[Edge Case] ContextCompactionTool supports head_tail_tool_preview`.
- `[Hidden Failure] ContextCompactionTool reports invalid max_tokens as ToolResult.error`.
- `[Silent Failure] ContextCompactionTool summary_with_backrefs returns expected before/after counts`.
- `[Hidden Assumption] ContextCompactionTool unknown new-mode typo still reports bad_mode`.

### Integration Tests

- `[Edge Case] Runtime with trim_to_token_budget sends a bounded message list to the runner`.
- `[Hidden Failure] Runtime with trim_with_provider_boundaries does not send an orphan tool result to the runner`.
- `[Silent Failure] Runtime with tool_output_sliding_window keeps the newest tool output raw and compacts older tool outputs before the next model call`.
- `[Hidden Assumption] Runtime with query_relevance_filter(query=None) uses the original user task as query`.
- `[Hidden Failure] Runtime with mechanical_bloat_scrubber removes bloat from model-visible messages without mutating original caller options`.
- `[Silent Failure] Runtime composes head_tail_tool_preview and trim_to_token_budget deterministically in middleware order`.
- `[Hidden Assumption] Runtime with primitive binding still stores raw successful tool output when tool-result scrubber middleware is active`.

External dependencies:

- Use fake runners, fake responses, fake token counters, and fake tools only.
- No real providers, network calls, MCP subprocesses, or filesystem traversal.

### Manual / QA Test Cases

1. `[Edge Case]` Given `MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens=10)` and a fake token counter, when the agent runs with several old messages, then the runner receives only messages within the deterministic budget.
2. `[Hidden Failure]` Given `trim_with_provider_boundaries`, when old assistant tool-call messages are trimmed, then their paired tool-result messages are removed too.
3. `[Silent Failure]` Given `ToolResultCompactionMiddleware.head_tail_preview(head_chars=3, tail_chars=2)`, when a tool returns `abcdefghi`, then the model-visible result contains `abc`, `hi`, and correct omitted count.
4. `[Hidden Assumption]` Given `QueryRelevanceFilterCompaction(query="billing invoice")`, when messages differ only by punctuation/case, then lexical matching still keeps relevant messages.
5. `[Hidden Failure]` Given `MechanicalBloatScrubberCompaction`, when a tool returns ANSI-colored repeated logs and a long base64 blob, then the second model call does not include those raw bloated spans while final metadata keeps the raw result.

Script verification:

- Create `scripts/test-deterministic-compaction-middleware.py`.
- The script must load `tests.test_deterministic_compaction_middleware`, `tests.test_context_compaction_middleware`, and `tests.test_context_compaction_tools`.
- The script must print `PASS` or `FAIL` per test case.
- The script must print `X/Y tests passed`.
- The script must exit non-zero if any test fails.

Full verification commands:

```powershell
python -m compileall vidbyte
python -m unittest tests.test_deterministic_compaction_middleware tests.test_context_compaction_middleware tests.test_context_compaction_tools tests.test_agent_runtime tests.test_agent_middleware
python scripts/test-deterministic-compaction-middleware.py
python -m unittest discover -s tests
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python >=3.11 | dataclasses, regex, typing, unittest | Existing runtime only |
| pydantic | Existing `>=2,<3` | Not used directly by this feature | No new risk |
| httpx | Existing dependency | Not used by this feature | No new risk |
| Live LLM providers | N/A | Not required | Must not be used |

No new dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- This is an SDK-only additive change.
- No feature flag is required.
- The implementation branch must be created from clean, updated `main`.
- Existing middleware and legacy compaction tool behavior should remain backward-compatible.
- New factory methods are opt-in.

Deployment order after approval:

1. Resolve the dirty/behind local `main` state and create an isolated worktree from updated `main`.
2. Commit this design doc first.
3. Add enum modes and strategy classes.
4. Wire engine dispatch and provider metadata.
5. Add public middleware factory methods.
6. Update legacy tool mode declarations.
7. Add unit/integration tests.
8. Add script verification.
9. Update README and skills.
10. Run compile, focused tests, script, and full test discovery.
11. Push the branch and open a draft PR.

Rollback procedure:

1. Revert the feature branch merge commit.
2. Remove new `CompactionMode` members and strategy classes.
3. Remove new factory methods and docs.
4. Remove deterministic expansion tests and script.
5. Existing compaction middleware remains intact.

---

## 13. Open Questions

- [ ] Local `main` was dirty and behind `origin/main` by 8 commits during audit. Should I clean generated artifacts and pull, or should implementation start from a fresh worktree created directly from `origin/main`?
- [ ] Should `parallel_block_compaction` and `async_background_compaction` get a separate runtime-orchestration design after these deterministic modes land?
- [ ] Should token-budget trimming wire into existing `compaction_trigger_tokens` / `compaction_target_tokens` in this PR, or remain explicit middleware only?
- [ ] Should root `vidbyte` export any advanced strategy classes, or should only middleware factories be public?
- [ ] Should `ContextCompactionTool` document all new deterministic modes or only the subset useful for legacy/manual contexts?

---

## 14. Alternatives Considered

### Alternative 1: Add These as Model-Visible Tools

- What: Re-add deterministic compaction methods to `ContextCompactionTool` as the primary API.
- Why rejected: The repo has already moved compaction to middleware. Model-visible compaction makes the model choose context hygiene and can pollute tool schemas.

### Alternative 2: Add Another `ContextWindow.preset.*` Catalog

- What: Expose every deterministic mode as a `ContextWindow` algorithm preset.
- Why rejected: These are hook-local runtime transforms, not full context-window algorithms. Middleware is the existing pattern for deterministic runtime policy.

### Alternative 3: Add Third-Party Tokenizers or BM25 Libraries

- What: Use provider tokenizers, embeddings, or search libraries for token budget and relevance filtering.
- Why rejected: The user specifically asked for deterministic code-only implementation without another model. The SDK also avoids new dependencies unless an approved design requires them.

### Alternative 4: Implement Parallel and Background Compaction Now

- What: Add scheduler-aware compaction wrappers in the same PR.
- Why rejected: Parallel/background compaction changes runtime scheduling, cancellation, and trace semantics. The current middleware hook contract can support deterministic transforms synchronously or asynchronously, but not background replacement safely without a separate design.

### Alternative 5: One Generic `DeterministicCompactionMiddleware` Class

- What: Add one new public class with a mode string for every deterministic behavior.
- Why rejected: Existing public API already splits tool-result, message-history, and summary compaction. Adding factory methods to those classes preserves hook ownership and avoids a second kitchen-sink middleware.
