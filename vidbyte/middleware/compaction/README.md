# Compaction Middleware

## Folder Intent

This folder owns context compaction primitives, strategies, trace rendering, and the compaction engine used by middleware/runtime flows.

## Non-Goals

Do not add unrelated agent-loop policy here; keep this package focused on reducing context while preserving traceable summaries.

## File Index

- `__init__.py`: Defines package re-exports and the public import surface for this folder. Key symbols: BaseCompaction, ClearExceptSystemAndLogCompaction, CompactionMode, CompactionStats, ContextSnapshotBranchTrimCompaction, ContextCompactionEngine.
- `base.py`: Defines the base class or shared contract for this SDK layer. Key symbols: CompactionMode, Summarizer, CompactionStats, BaseCompaction, TokenCounter.
- `context_compaction.py`: Owns context compaction behavior inside the vidbyte/middleware layer. Key symbols: ToolResultCompactionMiddleware, MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, TraceReplacementCompactionMiddleware, TraceSummaryTailCompactionMiddleware.
- `engine.py`: Routes compaction modes to strategies and converts between provider and context messages. Key symbols: ContextCompactionEngine.
- `strategies.py`: Defines concrete deterministic context compaction strategies. Key symbols: ClearExceptSystemAndLogCompaction, RemoveAllToolCallsCompaction, RemoveLastNCompaction, RemoveToolCallPercentageCompaction, KeepLastNMessagesCompaction, StripToolResultBodiesCompaction.
- `trace_render.py`: Pure renderer that turns a continual-trace artifact dict into bounded Markdown. Lets trace-backed compaction inject a readable, size-bounded trace summary into the context window without coupling the rendering logic to any runtime state. Key symbols: TraceArtifactRenderer.

## Subfolder Routing

- No source subfolders.

## Logs

- 2026-07-07: Compaction changes should preserve enough provenance to debug what content was summarized or removed.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
