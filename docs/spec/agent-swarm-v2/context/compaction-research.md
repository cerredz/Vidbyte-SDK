# Compaction research for agent-swarm v2 (S0)

Date: 2026-10-19. Branch `feat/agent-swarm` at `39ce8b20` (read-only; no commits). Web budget: 1 WebSearch of 25 used; everything else was a direct fetch of a primary page or a raw source file. Every external fact below carries the URL it was read from; items that could not be read are listed in section 6, not asserted.

Goal this serves: each `AgentSwarm` member runs one long `BaseAgent` conversation for hours, so its history must be compacted without losing the things a peer-to-peer worker cannot recover by itself (who it is, who its peers are, what they told it, what it promised them, what it changed on disk, where it was). The decision this file supports: which compaction mechanism each member holds as a tool, whether an automatic backstop runs, whether a provider-native fast path is worth wiring, and what the SDK already provides versus what must be built.

---

## 1. What the SDK already has

### 1.1 The Summarizer is a Protocol only; no implementation exists

- `vidbyte/middleware/compaction/base.py:42-47`:
  ```python
  class Summarizer(Protocol):
      """Protocol for optional async model-backed summarizers."""

      async def summarize(self, messages: Sequence[ContextMessage]) -> str:
          # Returns a compact summary of the supplied messages.
          ...
  ```
- `grep -rn "def summarize(" vidbyte` matches only that Protocol. Nothing in `vidbyte/` implements it, so every summarize mode is unusable out of the box.
- The middleware refuses summarize modes without one: `vidbyte/middleware/compaction/context_compaction.py:121-124` raises `ValueError(f"{self.mode.value} needs a summarizer; use SummaryCompactionMiddleware(mode=..., summarizer=...) ...")`, and `SummaryCompactionMiddleware.__init__` (`:261-264`) raises `"Summary compaction requires an injected summarizer."`.
- `ContextCompactionEngine._require_summarizer` (`vidbyte/middleware/compaction/engine.py`) is the same guard at the engine level.

Consequence: any summarizing compaction for swarm members needs a new `Summarizer` implementation. The natural one is runner-backed (see 1.4 and 4.5).

### 1.2 Compaction engine, strategies and the provider-message bridge

- `ContextCompactionEngine` (`vidbyte/middleware/compaction/engine.py:40`): `compact_messages(messages: Sequence[ContextMessage], mode, **options)` and `compact_provider_messages(provider_messages, mode, **options)`. The provider form converts provider dicts to `ContextMessage`, runs the strategy, converts back, then `_repair_tool_pairing` drops orphaned tool calls / tool results across Anthropic, OpenAI and Gemini shapes. `_provider_groups` keeps an assistant tool call and its results in one group so a cut never splits them.
- Token estimate is characters / 4: `_approximate_token_count` at `vidbyte/middleware/compaction/strategies.py:61`. No tokenizer, no provider usage.
- Strategies (`strategies.py`): `TrimWithProviderBoundariesCompaction` (`:605-648`, drop oldest groups until under `max_messages` / `max_tokens`), `SummarizeRangeCompaction` (`:334`, keeps system + `keep_last`, summarizes the middle, inserts `ContextMessage(role="assistant", content=summary_text, kind="summary")`), `SummarizeOldestNCompaction` (`:369`, same shape for the oldest N groups), plus topic-block and trace modes. The summary is therefore an assistant-role message, not a user message.

### 1.3 Middleware that uses the engine, and why none of it persists

- `MessageHistoryCompactionMiddleware` (`vidbyte/middleware/compaction/context_compaction.py:111-253`): runs in `before_model_call` and returns `MiddlewareTransform(provider_messages=...)`. Factory `trim_with_provider_boundaries(max_messages=None, max_tokens=None, token_counter=None)` at `:163`.
- `SummaryCompactionMiddleware(mode, summarizer, **options)` (`:256-283`) with `summarize_range(summarizer, keep_last=3)`, `summarize_oldest_n`, `summarize_by_topic_blocks`. `ToolResultCompactionMiddleware`, `TraceReplacementCompactionMiddleware`, `TraceSummaryTailCompactionMiddleware` live in the same file.
- The loop applies a `before_model_call` transform only to the single call being built: `AgentRuntime._apply_before_model_call_transform` (`vidbyte/agents/runtime.py:1085-1125`) rewrites `call_options["messages"]`, and `_middleware_context` (`:1160-1203`) hands middleware a copy ("Copy each message so middleware reads a snapshot and can never edit the run's live conversation", `:1196`). `state.messages` is never changed. So the swarm's current trim is recomputed on every call, and a summarizing middleware in that hook would re-summarize on every call (a model call per iteration). This is the central reason the existing middleware is not enough on its own.
- `MiddlewareTransform` fields: `model_visible_tool_result`, `provider_messages`, `system`, `metadata` (`vidbyte/lib/dataclasses/middleware.py:66-69`).

### 1.4 The model-callable tool, and the summarizer precedent

- `ContextCompactionTool(state: ContextState, *, summarizer=None)` at `vidbyte/tools/builtins/context/compaction.py:25-112`, tool name `compact_context` (`:36`), 24 modes; `execute` (`:76`) runs `engine.compact_messages` then `self.state.replace_messages(after)` (`:88`). It is not wired to any agent loop; it needs a `ContextState` (`vidbyte/lib/dataclasses/context.py:140-147`: `messages()` / `replace_messages()`), and nothing in `BaseAgent`/`AgentRuntime` exposes the live list through that Protocol.
- The only model-backed summarization in the SDK is `TrajectoryCheckpointAlgorithm` (`vidbyte/context/algorithms/trajectory_checkpoints.py`) driven by `InnerContextWindowAlgorithm.after_tool_calls(ctx)` (`vidbyte/context/runtime.py`) with `ctx.invoke_runner`, prompt `vidbyte/prompts/prompts/trajectory_checkpoints_agentic_summarizer.md`. It produces a JSON checkpoint as a context primitive; it does not rewrite history. It is the precedent for "a prompt leaf + a side call on the member's own runner".
- Side call API: `TextRunner.arun(prompt, *, system, metadata, tools, tool_choice, messages, response_format, prompt_index) -> TextModelResponse` (`vidbyte/lib/runners/text.py:69`); a member's runner comes from `BaseAgent._runner_for_model()` (`vidbyte/agents/base.py:1661`). The offline swarm fixture patches exactly that method (`tests/features/agent_swarm/agent_swarm_fixtures.py:248-280`, `_ScriptedRunner.arun(prompt, **options)`), so a summarizer that calls the member's own runner is scriptable offline.

### 1.5 Loop seams and facts the design must respect

- Persistence seam: `AgentRuntime._after_tool_iteration(state, messages)` (`vidbyte/agents/runtime.py:925`, called at `:700`) receives the LIVE `messages` list. `AgentSwarmMemberRuntime._after_tool_iteration` (`vidbyte/agents/agent_swarm/member.py:60`) already overrides it to append delivered mail; its header calls it "the loop's one documented seam for appending to the conversation" (`member.py:5`). An in-place `messages[:] = compacted` there persists for the rest of the run. Shared loop `vidbyte/agents/runtime.py` stays untouched (request.md decision).
- The task/goal prompt is not inside `messages`: it is inserted at the run boundary by the provider via `prompt_index` (`_build_iteration_call_options`, `_messages_with_task`, `_run_boundary`, `runtime.py:1596-1662`), and the system prompt travels as `call_options["system"]`. Compacting `messages` cannot lose the goal or the system prompt.
- Real usage is available: `after_model_response` receives `model_usage=usage_record.usage` (`runtime.py:470-500`; Anthropic usage carries `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`), and `state.tokens_used` is cumulative via `token_usage_from_response` (`vidbyte/lib/token_usage.py:7`). The last call's `input_tokens` is the honest measure of the current context size.
- Dead knobs: `compaction_trigger_tokens` / `compaction_target_tokens` exist on `BaseAgent.__init__` (`vidbyte/agents/base.py:105-106`), flow into `AgentLoopSettings` (`:319-325`), the config whitelist (`:674-675`) and serialization (`:632-633`, `:764`), but `grep -rn compaction_trigger_tokens vidbyte/agents/runtime.py` finds nothing: no runtime code consumes them.
- Anthropic provider sends only `x-api-key`, `anthropic-version: 2023-06-01`, `content-type` (`vidbyte/providers/anthropic.py:72-74`); no `anthropic-beta`. `TextModelConfig` has `extra_body` but no extra-headers field. Precedent for a beta header: `vidbyte/agents/skills/anthropic.py:37` sends `anthropic-beta: ANTHROPIC_SKILLS_BETA` (`vidbyte/lib/constants/skills.py:92`, `"skills-2025-10-02"`).
- Assistant turns: when the reply has tool calls, the stored assistant message keeps the full raw content list (`ToolsFormatter._assistant_turn_anthropic`, `vidbyte/lib/tools/formatter.py:388-396`), so an unknown block type survives; a text-only reply is stored as `{"role":"assistant","content": <str>}`, which drops every non-text block. This matters for any server-returned `compaction` block.
- OpenAI provider uses `/responses` statelessly (chat-shaped transcript converted by `_responses_items`; no `previous_response_id`, no `store`). Gemini supports `cachedContent` via `config.cached_content`.
- Swarm wiring today: `AgentSwarmMemberAgent.__init__` (`member.py:111-130`) sets `middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=AGENT_SWARM_HISTORY_MAX_TOKENS), AgentSwarmTurnMiddleware(swarm_runtime))` (`:126`) and `ToolSettings(result_max_chars=AGENT_SWARM_TOOL_RESULT_MAX_CHARS)` (`:125`). Constants: `AGENT_SWARM_HISTORY_MAX_TOKENS = 90_000`, `AGENT_SWARM_TOOL_RESULT_MAX_CHARS = 100_000`, `AGENT_SWARM_RESERVED_TOOL_NAMES = ("bash", "grep", "read_lines", "write_text", "patch_file", "message")` (`vidbyte/lib/constants/agent_swarm.py:35-46`). Mail is rendered by `Prompt.AGENT_SWARM_INBOX` / `AGENT_SWARM_INBOX_MESSAGE` with sender labels into one user message (`vidbyte/agents/agent_swarm/runtime.py:193-262`); tools are built at `runtime.py:247-250`. `AgentSwarmTurnMiddleware` implements only `after_tool_call` and `review_finish` (`vidbyte/middleware/builtins/agent_swarm_turn.py:34,40`).
- Not on this branch: `CompactCodexThreadTool` and `vidbyte/tools/builtins/codex/thread_helpers.py` (request.md:167 lists them; only `CODEX_COMPACTION_ITEM_TYPE` counters exist in `vidbyte/agents/codex/contracts.py`). Nothing to reuse there.

### 1.6 What is missing, in one list

1. A `Summarizer` implementation (runner-backed, prompt leaf, swarm-aware).
2. A write-back path that persists a compacted history (only `_after_tool_iteration` offers one without touching the shared loop).
3. A trigger based on real `input_tokens`, not chars/4, and a guard against compacting while a tool call is open.
4. A model-callable `compact` tool for members, registered as a reserved name and wired to that write-back path (the existing `ContextCompactionTool` cannot reach the live list).
5. Beta-header plumbing for the Anthropic provider if the native fast path is wanted.
6. An event (`compaction` with before/after tokens, trigger, mode) from an existing seam, and a post-compaction note to the model.

---

## 2. Candidates surveyed

### 2.1 Anthropic on-demand compaction (Claude API, beta)

- What: send the history with top-level `"compaction": {"type": "summarize"}` and the model returns one `{"type":"compaction","content":"<summary>","signature":"..."}` block with `stop_reason: "compaction"`; that block then replaces the summarized messages at the front of `messages`. Optional `instructions` (up to 16,384 characters) replace the default summarization prompt. Keep-recent-turns = send only the older messages to the compaction request, cut at a point where no tool call is open; the returned block goes first and the kept turns follow.
- Trigger: the client decides (usage-based or any other rule). Preserves: whatever the summarization prompt keeps; images and documents are lost. Shape: Messages API request; header `anthropic-beta: compact-2026-09-04` on the compaction request AND every later request that carries the block; one block per request, must be first (`compaction_block_misplaced` 400); cannot be combined with `context_management`; rejected if the last assistant turn has an unanswered tool call. Summarization usage is reported in `usage.iterations`.
- Cost: one extra model call per compaction (the summary is generated by the same model you call), plus the block's tokens on later requests. Availability: beta on Claude API, AWS, Google Cloud, Microsoft Foundry; models include claude-fable-5-1, claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5, claude-sonnet-4-6, claude-opus-4-6 to 4-8.
- URL: https://platform.claude.com/docs/en/build-with-claude/compaction-on-demand

### 2.2 Anthropic background compaction (same beta)

- What: the same request taken off the conversation's path. Record `sent = len(history)`, submit the compaction request on a copy, keep appending turns, and when the block arrives replace exactly the first `sent` messages with it: "Replace exactly the messages the compaction request held. Later turns stay after the block." Any other `stop_reason` means no summary; keep the full history and retry later. Two requests are open at once and both count against rate limits.
- Why it matters for a swarm: a member can keep answering peers while its summary is being written; the swap is a pure list splice, which maps onto the `_after_tool_iteration` seam.
- URL: https://platform.claude.com/docs/en/build-with-claude/compaction-background

### 2.3 Anthropic threshold compaction (`compact_20260112`, beta)

- What: a `context_management.edits` entry `{"type":"compact_20260112","trigger":{"type":"input_tokens","value":150000},"pause_after_compaction":false,"instructions":null}` makes the API summarize server-side mid-request when input tokens cross the trigger (default 150,000; minimum 50,000). The compaction block is appended after the messages and the API ignores everything before it on later requests.
- Limits quoted by the docs: "Same model for summarization"; "Compaction might fail when tools are defined" (the model may return `content: null`; the fix is an `instructions` line such as "Do not call any tools..."). Header `anthropic-beta: compact-2026-01-12`.
- Trap for this SDK: the block arrives inside a normal reply; a text-only reply is flattened to a string by the formatter (1.5), so the block would be lost unless the formatter is changed. Not recommended for v2.
- URL: https://platform.claude.com/docs/en/build-with-claude/compaction

### 2.4 Anthropic context editing (`clear_tool_uses_20250919`, `clear_thinking_20251015`)

- What: `context_management.edits` with `clear_tool_uses_20250919` (`trigger` default 100,000 input tokens, `keep` 3 most recent tool uses, `clear_at_least`, `exclude_tools`, `clear_tool_inputs` false) and `clear_thinking_20251015`. Server-side per request; the client keeps the full history; the response reports `context_management.applied_edits`. Header `anthropic-beta: context-management-2025-06-27`. Cannot be combined with on-demand `compaction`.
- Fit: pruning, not summarization; useful as a free first layer on Anthropic only. Equivalent client-side pruning already exists in the SDK (`ToolResultCompactionMiddleware`, trim modes).
- URL: https://platform.claude.com/docs/en/build-with-claude/context-editing

### 2.5 Anthropic memory tool (`memory_20250818`)

- What: a client-side file tool (`{"type":"memory_20250818","name":"memory"}`) the model uses to write durable notes; no beta header; the docs recommend pairing it with compaction so that what the summary drops is still on disk.
- Fit: the swarm already has a shared workplace with `write_text`/`patch_file`; a per-agent notes file is the same idea without a new tool type.
- URL: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool

### 2.6 Claude Code and the Claude Agent SDK (auto-compact)

- What: auto-compact runs when the conversation nears the model's context limit (1M-context models at about 967K by default); `/autocompact 500k`, the `autoCompactWindow` setting and `CLAUDE_CODE_AUTO_COMPACT_WINDOW` lower it; `/compact <instructions>` compacts on demand with focus instructions; a "Compact instructions" section in CLAUDE.md steers every compaction. The summary is produced by a separate request that appends the summarization instruction as the final user message (cache-warm). After compaction the system prompt, CLAUDE.md, memory and MCP instructions are reloaded, up to five recently modified files are re-read, and invoked skills are re-injected.
- Hooks: `PreCompact` input carries `trigger` (`manual` | `auto`) and `custom_instructions` and can block; `PostCompact` carries `compact_summary`. Agent SDK: automatic compaction emits a system message with subtype `compact_boundary`; `/compact` can be sent as a prompt string.
- Fit: the behavioural template (manual tool + automatic backstop + instructions + reload what survives) is what this research recommends; the code itself is not reusable.
- URLs: https://code.claude.com/docs/en/costs ; https://code.claude.com/docs/en/hooks ; https://code.claude.com/docs/en/agent-sdk/sessions

### 2.7 OpenAI Responses compaction (server-side, and `POST /responses/compact`)

- What: `context_management: [{"type":"compaction","compact_threshold":200000}]` on a Responses request compacts server-side when the threshold is crossed (works with `store=false`, ZDR); the standalone `POST /responses/compact` takes `model` and `input` and "Returns a compacted response object" whose output includes an encrypted `compaction` item that must be echoed back and never pruned. `previous_response_id` chaining bills all prior tokens as input each turn; responses are stored 30 days by default.
- Fit for this SDK: `extra_body` can carry `context_management`, but the returned opaque item would have to roundtrip through `_responses_items`, which rebuilds input from a chat-shaped transcript (unverified; see 6). OpenAI only.
- URLs: https://developers.openai.com/api/docs/guides/conversation-state ; https://developers.openai.com/api/reference/resources/responses/methods/compact

### 2.8 OpenAI Codex CLI compaction (open source, Apache-2.0)

- What: `codex-rs/core/src/compact.rs` summarizes with `SUMMARIZATION_PROMPT` and injects the summary as a user message prefixed by `SUMMARY_PREFIX`; it keeps the initial context plus recent user messages within `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000` and retained tool outputs. Trigger (`context_window.rs`): `auto_compact_scope_tokens >= limit || active_context_tokens >= context_window * effective_context_window_percent / 100` (fallback model: context_window 272_000, 95 percent, no auto limit). Config: `model_auto_compact_token_limit`, `compact_prompt`, `experimental_compact_prompt_file`, provider `capabilities.remote_compaction: unsupported | v2`.
- Prompt (verbatim, `codex-rs/prompts/templates/compact/prompt.md`): "You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task. Include: - Current progress and key decisions made - Important context, constraints, or user preferences - What remains to be done (clear next steps) - Any critical data, examples, or references needed to continue. Be concise, structured, and focused on helping the next LLM seamlessly continue the work."
- Prefix (verbatim, `summary_prefix.md`): "Another language model started to solve this problem and produced a summary of its thinking process. You also have access to the state of the tools that were used by that language model. Use this to build on the work that has already been done and avoid duplicating work. Here is the summary produced by the other language model, use the information in this summary to assist with your own analysis:"
- Fit: the prompt and the "summary as a user message with a prefix" shape are directly reusable (text, not code).
- URLs: https://raw.githubusercontent.com/openai/codex/main/codex-rs/prompts/templates/compact/prompt.md ; https://raw.githubusercontent.com/openai/codex/main/codex-rs/prompts/templates/compact/summary_prefix.md ; https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs ; https://github.com/openai/codex/blob/main/docs/config.md

### 2.9 OpenAI Agents SDK `OpenAIResponsesCompactionSession` (MIT)

- What: `OpenAIResponsesCompactionSession(session_id, underlying_session, client, model="gpt-4.1", compaction_mode="auto" | "previous_response_id" | "input", should_trigger_compaction, max_rollback_items)`; default trigger is at least 10 candidate items (user messages and compaction items excluded); `run_compaction` calls `client.responses.compact(...)`. `session_input_callback` lets you trim input yourself.
- Fit: OpenAI-only wrapper over 2.7; the trigger-callback shape is a good interface precedent.
- URL: https://openai.github.io/openai-agents-python/sessions/

### 2.10 Google ADK `EventsCompactionConfig`; Gemini caching

- What: `App(events_compaction_config=EventsCompactionConfig(compaction_interval=N, overlap_size=M, summarizer=LlmEventSummarizer(llm=Gemini(model="gemini-flash-latest"))))` summarizes the event log every N invocations with an overlap window; the TS runtime has a token-based compactor. Gemini context caching (implicit on 2.5+, explicit `cachedContents` with `ttl`, `cachedContent` on the request) lowers cost but does not shrink the window; it is not compaction.
- Fit: the "interval + overlap" rule is a reasonable alternative trigger; `LlmEventSummarizer` is Gemini-specific.
- URLs: https://adk.dev/context/compaction/ ; https://ai.google.dev/gemini-api/docs/caching

### 2.11 LangChain `SummarizationMiddleware`, `ContextEditingMiddleware`, langmem (MIT)

- What: `SummarizationMiddleware(model, trigger=None, keep=("messages", 20), token_counter=count_tokens_approximately, summary_prompt=DEFAULT_SUMMARY_PROMPT, trim_tokens_to_summarize=4000)`; triggers `("tokens", N)` | `("fraction", f)` | `("messages", N)`; a list is OR, a dict is AND. `_find_safe_cutoff_point` never splits an AI message from its tool messages. The summary replaces history via `RemoveMessage(REMOVE_ALL_MESSAGES)` plus a `HumanMessage("Here is a summary of the conversation to date:\n\n{summary}")` tagged `lc_source: summarization`. The default prompt is a checklist with sections SESSION INTENT, SUMMARY, ARTIFACTS, NEXT STEPS and says "This section prevents silent loss of artifact information." `ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=100000, clear_at_least=0, keep=3, clear_tool_inputs=False, exclude_tools=(), placeholder="[cleared]")])` mirrors 2.4 client-side. langmem `summarize_messages(..., running_summary=...)` keeps an incremental `RunningSummary`.
- Fit: the SDK already has the trim/pairing half; the prompt sections and the "summary as the first user message" shape are reusable text. Code is LangGraph-bound.
- URLs: https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/langchain_v1/langchain/agents/middleware/summarization.py ; https://docs.langchain.com/oss/python/langchain/middleware ; https://langchain-ai.github.io/langmem/guides/summarization/

### 2.12 Letta (Apache-2.0 server; cloud API)

- What: automatic compaction when the context is too long; `compaction_settings.mode` in `all | sliding_window (default, sliding_window_percentage 0.3) | self_compact_all | self_compact_sliding_window`, plus `model` and `clip_chars`; manual `POST /v1/agents/{agent_id}/summarize`. Memory blocks are pinned in the system prompt, so identity and persona survive compaction by construction; old messages stay retrievable from storage.
- Fit: the "pinned blocks outside the history" idea is already true in this SDK (system prompt and task are outside `messages`); the self-compact modes (the agent summarizes its own context) match the proposed `compact` tool.
- URLs: https://docs.letta.com/guides/agents/context-engineering ; https://docs.letta.com/api-reference/agents/summarize

### 2.13 Mastra Observational Memory (Elastic-2.0 / commercial)

- What: an observer condenses the history into dated observations once `observation.messageTokens` (30,000) accumulate; a reflector condenses observations once `reflection.observationTokens` (40,000) accumulate; observations live in the system message and about 6k tokens of recent messages remain.
- Fit: a two-level scheme worth copying later (summary-of-summaries) but heavier than v2 needs.
- URL: https://mastra.ai/docs/memory/observational-memory

### 2.14 Vercel AI SDK `pruneMessages` / `prepareStep` (Apache-2.0, TypeScript)

- What: `prepareStep({messages})` can return a pruned `messages` array; `pruneMessages({reasoning:'all', toolCalls:'before-last-3-messages', emptyMessages:'remove'})` removes reasoning and old tool calls. No summarizer.
- Fit: pruning only; the SDK's trim modes already cover it.
- URL: https://ai-sdk.dev/docs/agents/loop-control

### 2.15 Pydantic AI `ProcessHistory` (MIT)

- What: a capability whose processors replace the state history before each model call; the user supplies the summarizing agent.
- Fit: same "bring your own summarizer" gap as this SDK.
- URL: https://pydantic.dev/docs/pydantic-ai/capabilities/#processhistory

### 2.16 Others, briefly

- CrewAI `respect_context_window=True` summarizes when exceeded (opaque, no prompt or trigger exposed). smolagents step callbacks drop observations/images (truncation). AutoGen `BufferedChatCompletionContext` / `HeadAndTailChatCompletionContext` / `TokenLimitedChatCompletionContext` (truncation). AG2 `TransformMessages` with `MessageHistoryLimiter`, `MessageTokenLimiter`, `TextMessageCompressor` (LLMLingua; found via the one WebSearch and a notebook fetch, not the API reference). Mem0 extracts facts into a store; it is memory, not compaction. None adds anything the candidates above lack.

---

## 3. Comparison table

| Candidate | What it does | Who triggers | What it preserves | Native / client | API shape | Cost per compaction | License / availability | Fit for a swarm member |
|---|---|---|---|---|---|---|---|---|
| 2.1 Anthropic on-demand | Model writes a signed summary block that replaces older messages | Client (any rule) | Whatever `instructions` ask; images/documents lost | Provider-native, client-placed | Messages API + `compaction` field + `compact-2026-09-04` header | 1 model call on the summarized span | Beta, Claude models only (API, AWS, GCP, Foundry) | Best native path; needs header plumbing and the block-at-front rule |
| 2.2 Anthropic background | Same, while the conversation continues; splice at `sent` | Client | Same | Native | Same + concurrency | Same + 2 open requests | Beta, Claude only | Ideal for members that keep answering peers; splice maps on `_after_tool_iteration` |
| 2.3 Anthropic threshold | Server summarizes mid-request past N input tokens | Server (`trigger.input_tokens`) | Per `instructions`; same model only | Native | `context_management` edit + `compact-2026-01-12` | Hidden in the request | Beta, Claude only | Not for v2: block lost by text-only formatting; "might fail when tools are defined" |
| 2.4 Anthropic context editing | Clears old tool results / thinking server-side | Server (`trigger`) | Everything except cleared blocks | Native (client keeps full history) | `context_management` edits + `context-management-2025-06-27` | None (fewer input tokens) | Beta, Claude only | Optional free layer; SDK trim already equivalent |
| 2.5 Anthropic memory tool | Model writes durable notes to files | Model | Notes on disk | Client-side files | Tool type `memory_20250818` | Tool calls only | GA (no beta header) | Swarm workplace already provides it via `write_text` |
| 2.6 Claude Code / Agent SDK | Auto-compact near limit + `/compact <instructions>` + hooks | Both | Summary + reloaded system prompt/CLAUDE.md + 5 recent files + skills | Client-side (separate request) | CLI/SDK only | 1 model call | Product, not a library | Behavioural template only |
| 2.7 OpenAI Responses compaction | Server compacts past `compact_threshold`; `/responses/compact` returns encrypted item | Server or client | Opaque encrypted item | Native | `context_management` or `POST /responses/compact` | Hidden / 1 call | GA on Responses, OpenAI only | Item roundtrip through `_responses_items` unverified; defer |
| 2.8 Codex CLI | Summarize with handoff prompt, inject as prefixed user message | Auto (token limit or 95 percent window) or `/compact` | Initial context, recent user messages (20k), retained tool outputs | Client-side | Rust, not importable | 1 model call | Apache-2.0 | Prompt + prefix text reusable verbatim |
| 2.9 OpenAI Agents SDK session | Wraps 2.7 with trigger callback | Callback (default 10 items) | Opaque | Native | Python class | 1 call | MIT, OpenAI only | Interface precedent |
| 2.10 Google ADK | Summarize events every N invocations with overlap | Interval | Summary event | Client-side | `EventsCompactionConfig` | 1 Gemini call | Apache-2.0, Gemini summarizer | Alternative trigger rule |
| 2.11 LangChain middleware | Summarize past trigger, safe cutoff, summary as first user message | Tokens / fraction / messages | Checklist prompt: intent, summary, artifacts, next steps | Client-side | LangGraph middleware | 1 call | MIT | Prompt sections reusable; SDK trim already matches the cutoff logic |
| 2.12 Letta | Auto sliding-window or self-compaction; manual `/summarize` | Server or agent | Memory blocks pinned; old messages retrievable | Server (hosted) | REST | 1 call | Apache-2.0 server | Validates "pinned identity outside history" and self-compaction |
| 2.13 Mastra | Observer + reflector two-level condensation | Token thresholds | Observations in system message | Client-side | TS config | 2 kinds of calls | Elastic-2.0 | Later refinement |
| 2.14 Vercel AI SDK | Prune reasoning / old tool calls | `prepareStep` | No summary | Client-side | TS | None | Apache-2.0 | Pruning only |
| 2.15 Pydantic AI | History processors | Per call | User-defined | Client-side | Python | User-defined | MIT | Same gap as SDK |

Fit ranking for the member's held tool and backstop: client-side summarizer built from 2.8 + 2.11 prompt shapes on the SDK engine (universal, offline-testable) first; 2.1/2.2 as the Anthropic fast path; 2.3, 2.7 deferred; 2.4 optional later.

---

## 4. Recommendation

### 4.1 The tool each agent holds: `compact`

Give every member a swarm-specific tool named `compact` (add it to `AGENT_SWARM_RESERVED_TOOL_NAMES`), with one optional argument `focus: str` ("what to keep in detail", the Claude Code `/compact <instructions>` idea). Its `execute` does not rewrite history itself (tool results cannot reach the live list); it records a pending compaction request on the member runtime, and `AgentSwarmMemberRuntime._after_tool_iteration` performs the rewrite in place right after the iteration's tool results are appended, before mail is delivered. The tool result tells the model that compaction will apply before its next turn. This keeps the shared loop untouched and uses the one documented seam.

Why a tool at all: Letta's self-compact modes, Claude Code's `/compact`, Codex's `/compact` and the Anthropic docs all expose on-demand compaction to the operator or the agent; a swarm member is its own operator for hours, and it knows when a phase ended (for example after finishing a sub-task or a round of messages) better than a token counter does.

Do not reuse `ContextCompactionTool` as-is: its name `compact_context` would leak 24 modes to the model, it needs a `ContextState`, and it summarizes synchronously inside the tool call. Reuse its engine and the `_repair_tool_pairing` guarantee instead.

### 4.2 Automatic backstop: yes, and the 90,000-token trim stays as the last line

Run two automatic layers in the member runtime:

1. Auto-summarize when the last model call's real `input_tokens` (from `after_model_response` `model_usage`, recorded by a small swarm middleware into run state) crosses a trigger. Make the dead knobs live for members: `compaction_trigger_tokens` (default: 80 percent of `AGENT_SWARM_HISTORY_MAX_TOKENS`, that is 72,000) and `compaction_target_tokens` (default: 30 percent, that is 27,000, the share Letta's default sliding window keeps). The runtime already carries them in `runtime_config`; today nothing reads them. Fall back to the chars/4 estimate when usage is missing (offline fixtures).
2. Keep `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=90_000)` exactly where it is. It is per-call, never persists, and only bites if a summary failed or a single tool result is huge; it is the safety net, not the mechanism. Order the new middleware before it so a fresh summary is what the trim sees.

Trigger rule, in the Codex shape: `input_tokens >= trigger OR estimate >= cap`. Guards: never compact while a tool call is open (Anthropic rejects it; the engine's `_repair_tool_pairing` would otherwise drop the call), never run two compactions at once (background rule from 2.2), and skip when fewer than two provider groups would be summarized.

### 4.3 Provider-native fast path: Anthropic on-demand compaction, behind one interface

Define one internal interface `SwarmCompactor.compact(messages, *, focus, keep_recent_groups) -> list[dict]` with two implementations chosen per member at construction:

- `AnthropicNativeCompactor` when the member's provider is Anthropic and the model is on the supported list: send the older messages (cut at a closed tool boundary) with `compaction={"type":"summarize","instructions": <swarm prompt + focus>}` and header `anthropic-beta: compact-2026-09-04`; on `stop_reason == "compaction"` splice `[{"role":"assistant","content": response.content}] + kept` into the live list; on any other stop reason keep the history and fall through to the summarizer. Every later request must carry the same beta header while the block is in the history, and exactly one block may exist, at index 0; a second compaction must send the block plus the messages after it, and the API returns a new single block. Needs beta-header plumbing in `AnthropicProvider._create_headers` (a `betas: tuple[str, ...]` on `TextModelConfig` or an `extra_headers` mapping; precedent `vidbyte/agents/skills/anthropic.py:37`). This path is optional for v2; if the header knob is out of scope, ship the summarizer path alone and leave the interface so the native compactor is a follow-up.
- `RunnerSummarizerCompactor` everywhere else (OpenAI, Gemini, any other provider, offline tests, and Anthropic fallback): a new `Summarizer` implementation that calls the member's own runner (`BaseAgent._runner_for_model()` result, `arun(prompt, system=..., messages=...)`) with the swarm handoff prompt, then uses `ContextCompactionEngine.compact_provider_messages(..., mode=summarize_range, keep_last=K)` or an equivalent splice so pairing is repaired by the engine. The summary message follows the Codex/LangChain shape: a user message that begins with a fixed prefix ("Another language model started to solve this problem and produced a summary ... Here is the summary ...") and contains the structured summary; the model's next turn then continues normally. Note the engine's summarize strategies emit the summary as an assistant message with `kind="summary"`; for provider safety (Anthropic requires alternating roles and a user message first after the task prompt is spliced at the run boundary), the swarm compactor should emit the user-role prefix form and let `_repair_tool_pairing` validate.

Do not adopt threshold compaction (2.3) or OpenAI server compaction (2.7) in v2: both hand the SDK an opaque block inside a normal reply, the formatter drops non-text blocks on text-only replies, and `_responses_items` cannot roundtrip the encrypted item without new code.

### 4.4 What the summary must preserve for a swarm agent

The prompt leaf (new `vidbyte/prompts/prompts/agent_swarm/compaction_summarizer.md`, same checklist discipline as LangChain's "populate it or state None") must force these sections, in this order:

1. IDENTITY: my agent name and role in the swarm (from the system prompt; restated so the model never addresses itself as a peer).
2. PEERS: every peer name and what each is responsible for.
3. GOAL: the shared task and my own assignment inside it.
4. MESSAGES RECEIVED: sender, gist, and whether I acted on it (the inbox renders sender labels; keep names verbatim).
5. MESSAGES SENT: recipient, gist, and whether a reply is still expected.
6. PROMISES TO PEERS: what I told a peer I would deliver, to whom, and its status (this is the one item no other framework's prompt has and the one a swarm cannot recover).
7. FILES CHANGED: absolute paths in the workplace and what changed (LangChain: "prevents silent loss of artifact information").
8. WORK IN PROGRESS: the current step, partial results, exact commands and errors.
9. DECISIONS AND REJECTED OPTIONS, with reasons.
10. NEXT STEPS.

Pass `focus` from the tool as an extra instruction. For the Anthropic native path, send the same text as `instructions` (limit 16,384 characters). After compaction, add one short note in the summary message that the history was compacted and that mail received after the cut follows unchanged; the system prompt and task survive automatically because they are outside `messages`. Compaction should never summarize the inbox message delivered in the current iteration (keep the last K groups where K covers at least the most recent inbox delivery and the current tool round).

### 4.5 SDK pieces reused

- `ContextCompactionEngine.compact_provider_messages` and `_repair_tool_pairing` / `_provider_groups` (`vidbyte/middleware/compaction/engine.py`).
- `TrimWithProviderBoundariesCompaction` via the existing member middleware (`member.py:126`).
- `Summarizer` Protocol (`base.py:42-47`) as the type of the new implementation.
- `AgentSwarmMemberRuntime._after_tool_iteration` (`member.py:60`) as the write-back and event seam.
- `after_model_response` `model_usage` (`runtime.py:470-500`) and `state.tokens_used` for the trigger.
- `compaction_trigger_tokens` / `compaction_target_tokens` in `AgentLoopSettings` / `runtime_config` as the configuration surface (already whitelisted and serialized).
- `BaseAgent._runner_for_model()` for the side call, so `ScriptedSwarm` can script the summary offline.
- Prompt catalog pattern from `trajectory_checkpoints_agentic_summarizer.md` and the `agent_swarm/` leaves.
- Constants module `vidbyte/lib/constants/agent_swarm.py` for the new names, and `AGENT_SWARM_RESERVED_TOOL_NAMES` for `compact`.

### 4.6 New pieces needed

1. `SwarmHandoffSummarizer` (implements `Summarizer`; runner-backed; prompt leaf above) in `vidbyte/agents/agent_swarm/` (not `vidbyte/lib/`, which must not import `vidbyte.tools` or runners).
2. `compact` tool (swarm-specific, next to `AgentSwarmMessageTool` in `member.py` or the toolset), plus its reserved name and a prompt line telling members when to call it.
3. Compaction state on `AgentSwarmMemberRuntime`: `pending_focus`, `last_input_tokens`, `compacting` flag, `compactions` counter; the in-place rewrite in `_after_tool_iteration` ordered before mail delivery.
4. `AgentSwarmUsageMiddleware` (or an extension of `AgentSwarmTurnMiddleware`) implementing `after_model_response` to record `model_usage.input_tokens` into run state for the trigger.
5. Optional `AnthropicNativeCompactor` + beta-header plumbing in `AnthropicProvider` / `TextModelConfig`, with the "block first, header on every request, one block only" invariants.
6. New constants: `AGENT_SWARM_COMPACTION_TRIGGER_TOKENS = 72_000`, `AGENT_SWARM_COMPACTION_TARGET_TOKENS = 27_000`, `AGENT_SWARM_COMPACTION_KEEP_GROUPS`, `AGENT_SWARM_COMPACT_TOOL_NAME = "compact"`, `ANTHROPIC_COMPACTION_BETA = "compact-2026-09-04"` (if 5 ships).
7. A swarm event (`compaction`) with agent name, trigger (`tool` | `auto`), tokens before/after, groups summarized, mode (`native` | `summarizer`), emitted from `_after_tool_iteration` through the existing `on_event` callback.
8. Tests on `ScriptedSwarm`: tool-triggered compaction, auto trigger from scripted usage, open-tool-call guard, inbox-after-cut preserved, promises/peers present in the scripted summary prompt, native path header assertion if 5 ships.

### 4.7 Risks

- Summary quality: a bad summary silently loses a promise to a peer; mitigation is the mandatory section checklist plus keeping the last K groups verbatim and the shared workplace as ground truth (peers can re-ask).
- Role alternation: inserting a user-role summary right after an assistant message is fine, but inserting it after a user message (inbox) breaks Anthropic alternation; always splice before the mail append in `_after_tool_iteration`.
- Double compaction: a tool-triggered and an auto-triggered compaction in the same iteration must coalesce (one flag).
- Cost: each compaction is one model call on up to ~70k tokens; with 100 agents and 500 turns this is bounded by the trigger; record it in the event so operators see it.
- Beta dependence: the native path is beta and header-gated; keep the summarizer path as the default so a beta change cannot stall a swarm.
- Trim still drops silently: if the summarizer fails repeatedly (model error), the 90k trim keeps the run alive but loses old peer mail; emit a warning event when trim bites after a failed summary.

---

## 5. Evidence (quoted lines and URLs)

- Anthropic on-demand: "compaction": {"type": "summarize"}; block `{"type":"compaction","content":..., "signature":...}`; `stop_reason: "compaction"`; header `compact-2026-09-04`; `instructions` up to 16,384 characters; one block per request, must be first (`compaction_block_misplaced`); cannot combine with `context_management`; rejected when the last assistant turn has an unanswered tool call; images and documents are lost. https://platform.claude.com/docs/en/build-with-claude/compaction-on-demand
- Anthropic background: "Replace exactly the messages the compaction request held. Later turns stay after the block."; "If the response has any other `stop_reason`, no summary was produced ... Keep the full history"; "don't start another compaction request until this one is swapped in or has failed"; "while it runs your application has two requests open at once". https://platform.claude.com/docs/en/build-with-claude/compaction-background
- Anthropic threshold: `{"type":"compact_20260112","trigger":{"type":"input_tokens","value":150000},"pause_after_compaction":false,"instructions":null}`; minimum trigger 50,000; "Same model for summarization"; "Compaction might fail when tools are defined"; header `compact-2026-01-12`. https://platform.claude.com/docs/en/build-with-claude/compaction
- Anthropic context editing: `clear_tool_uses_20250919` with `trigger` (default 100,000 input tokens), `keep` (default 3), `clear_at_least`, `exclude_tools`, `clear_tool_inputs` (false); `clear_thinking_20251015`; response `context_management.applied_edits`; header `context-management-2025-06-27`. https://platform.claude.com/docs/en/build-with-claude/context-editing
- Anthropic memory tool: `{"type":"memory_20250818","name":"memory"}`; client-side file operations; no beta header; pair with compaction. https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- Claude Code: `/autocompact 500k`, `autoCompactWindow`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `/compact <instructions>`, "Compact instructions" in CLAUDE.md; summary built by appending the summarization instruction as the final user message; after compaction system prompt/CLAUDE.md/memory/MCP reload, up to five recently modified files re-read, skills re-injected. https://code.claude.com/docs/en/costs
- Claude Code hooks: `PreCompact` input `trigger: "manual" | "auto"`, `custom_instructions`; `PostCompact` input `compact_summary`. https://code.claude.com/docs/en/hooks
- Claude Agent SDK: automatic compaction emits a system message with subtype `compact_boundary`. https://code.claude.com/docs/en/agent-sdk/sessions
- OpenAI conversation state: `context_management=[{"type":"compaction","compact_threshold":200000}]`; compaction item is encrypted and must not be pruned; `previous_response_id` bills prior tokens as input; 30-day storage default. https://developers.openai.com/api/docs/guides/conversation-state
- OpenAI compact endpoint: parameters `model`, `input`; "Returns a compacted response object" (response schema not read; see 6). https://developers.openai.com/api/reference/resources/responses/methods/compact
- Codex prompt and prefix: quoted verbatim in 2.8 from the raw files. Trigger `auto_compact_scope_tokens >= limit || active_context_tokens >= context_window * effective_context_window_percent / 100`; fallback `context_window 272_000`, `effective_context_window_percent 95`; `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000`. https://github.com/openai/codex/blob/main/codex-rs/core/src/context_window.rs ; https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs
- Codex config: `model_auto_compact_token_limit`, `compact_prompt`, `experimental_compact_prompt_file`, `capabilities.remote_compaction: unsupported | v2`. https://github.com/openai/codex/blob/main/docs/config.md
- OpenAI Agents SDK: `OpenAIResponsesCompactionSession(... model="gpt-4.1", compaction_mode="auto" ...)`, default trigger 10 candidate items, `run_compaction` calls `client.responses.compact`. https://openai.github.io/openai-agents-python/sessions/
- Google ADK: `EventsCompactionConfig(compaction_interval, overlap_size, summarizer=LlmEventSummarizer(...))` on `App`. https://adk.dev/context/compaction/
- Gemini caching: implicit caching on 2.5+, explicit `cachedContents` with `ttl`, request field `cachedContent`. https://ai.google.dev/gemini-api/docs/caching
- LangChain: signature `SummarizationMiddleware(model, trigger=None, keep=("messages", 20), token_counter=count_tokens_approximately, summary_prompt=DEFAULT_SUMMARY_PROMPT, trim_tokens_to_summarize=4000)`; `_find_safe_cutoff_point`; `RemoveMessage(id=REMOVE_ALL_MESSAGES)`; `content=f"Here is a summary of the conversation to date:\n\n{summary}"`; prompt sections "## SESSION INTENT", "## SUMMARY", "## ARTIFACTS" ("This section prevents silent loss of artifact information."), "## NEXT STEPS". https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/langchain_v1/langchain/agents/middleware/summarization.py
- LangChain context editing: `ClearToolUsesEdit(trigger=100000, clear_at_least=0, keep=3, clear_tool_inputs=False, exclude_tools=(), placeholder="[cleared]")`. https://docs.langchain.com/oss/python/langchain/middleware
- Letta: `compaction_settings.mode` in `all | sliding_window | self_compact_all | self_compact_sliding_window`, `sliding_window_percentage` 0.3 default, `model`, `clip_chars`; `POST /v1/agents/{agent_id}/summarize`. https://docs.letta.com/guides/agents/context-engineering ; https://docs.letta.com/api-reference/agents/summarize
- Mastra: observer at `observation.messageTokens` 30,000, reflector at `reflection.observationTokens` 40,000. https://mastra.ai/docs/memory/observational-memory
- Vercel AI SDK: `prepareStep({messages})` returning `messages`; `pruneMessages({reasoning:'all', toolCalls:'before-last-3-messages', emptyMessages:'remove'})`. https://ai-sdk.dev/docs/agents/loop-control
- Pydantic AI: `ProcessHistory` capability. https://pydantic.dev/docs/pydantic-ai/capabilities/
- SDK facts: all `path:line` references in section 1 were re-checked at `39ce8b20` on 2026-10-19 with `grep -n`.

---

## 6. Unverified items and what was skipped

Unverified (not asserted above beyond what is marked):
- OpenAI `POST /responses/compact` full response schema and the exact field name of the encrypted payload (`encrypted_content` is inferred from the Agents SDK docs; the API reference page was truncated at 100k characters and the rest was not read).
- Whether an OpenAI `compaction` item can be echoed through this SDK's `_responses_items` without new code (no fetch can answer this; it is a code change to test).
- Gemini CLI compression settings (three documentation URLs returned 404).
- Gemini explicit-cache default TTL.
- AG2 `TextMessageCompressor` parameters (read from a notebook and one WebSearch result, not the API reference; two advanced-concepts pages returned 404).
- Letta `guides/agents/compaction` page (404); facts come from the context-engineering guide and the API reference instead.
- Anthropic on-demand compaction's summarization usage accounting inside `usage.iterations` was read from the docs but not exercised.
- Exact token cost of a swarm compaction (depends on the member model and history size; no model calls were made).

Skipped under the web budget or because the primary page was unreachable: a second pass over OpenAI's API reference (truncated), a deeper read of Codex `compact.rs` beyond the constants and the trigger (the prompt files were fetched raw instead), and Gemini CLI. One WebSearch of 25 was used (AG2); all other sources were direct fetches.
