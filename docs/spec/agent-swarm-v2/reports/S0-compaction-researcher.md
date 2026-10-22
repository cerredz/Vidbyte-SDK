# S0 compaction researcher: report

Date: 2026-10-19. Branch `feat/agent-swarm` at `39ce8b20`. No commits, no installs, no gate runs, no model calls, no environment dumps. Repo was read-only apart from the two files this stage owns.

## Produced

- `docs/spec/agent-swarm-v2/context/compaction-research.md` (the decision-ready file: SDK inventory, 16 candidates, comparison table, recommendation, evidence, unverified list).
- `docs/spec/agent-swarm-v2/reports/S0-compaction-researcher.md` (this report).

## Web budget

- WebSearch: 1 of 25 used (AG2 `TransformMessages` / `TextMessageCompressor`, because the AG2 docs URLs I had were 404).
- Direct fetches (WebFetch and three raw-file curls into the scratchpad `fetched/` folder): about 40. Primary pages only; no other search engines or proxies.

## What was searched and fetched

Repository (grep / sed / git grep at `39ce8b20`):
- Compaction package `vidbyte/middleware/compaction/{base,engine,strategies,context_compaction,__init__}.py`; shims `vidbyte/middleware/builtins/context_compaction.py`, `vidbyte/context/compaction.py`; tool `vidbyte/tools/builtins/context/compaction.py`; `vidbyte/lib/dataclasses/context.py` (`ContextState`); `vidbyte/context/{window,runtime}.py`, `vidbyte/context/algorithms/trajectory_checkpoints.py` and its prompt leaf.
- Loop seams in `vidbyte/agents/runtime.py` (call build, usage, `after_model_response`, `_after_tool_iteration`, `_apply_before_model_call_transform`, `_middleware_context`, run boundary / task placement); `vidbyte/agents/base.py` (ctor knobs, `_resolve_loop_settings`, `_runner_for_model`); `vidbyte/lib/runners/text.py`; `vidbyte/lib/token_usage.py`.
- Swarm files `vidbyte/agents/agent_swarm/{member,runtime,settings}.py`, `vidbyte/middleware/builtins/agent_swarm_turn.py`, `vidbyte/tools/toolsets/agent_swarm.py`, `vidbyte/lib/constants/agent_swarm.py`, `tests/features/agent_swarm/agent_swarm_fixtures.py`.
- Providers `vidbyte/providers/{anthropic,openai,gemini}.py`, `vidbyte/lib/dataclasses/model_configs.py`, `vidbyte/lib/tools/formatter.py`, `vidbyte/agents/skills/anthropic.py`, `vidbyte/lib/constants/skills.py`, `vidbyte/agents/codex/contracts.py`.
- `docs/` was treated as opaque except `docs/spec/agent-swarm-v2/request.md`.

Web (all fetched, facts recorded with URLs in the research file):
- Anthropic: compaction-on-demand, compaction-background, compaction (threshold), context-editing, memory-tool; Claude Code costs, hooks, Agent SDK sessions.
- OpenAI: conversation-state guide, `/responses/compact` API reference (first 100k characters only), Codex `config.md`, `context_window.rs`, `compact.rs`, raw `prompts/templates/compact/prompt.md` and `summary_prefix.md`; Agents SDK sessions page.
- Google: ADK compaction page, Gemini caching page.
- LangChain: raw `summarization.py` (signature, cutoff, summary message, `DEFAULT_SUMMARY_PROMPT`), middleware docs, langmem summarization guide.
- Letta context-engineering guide and `/summarize` API reference; Mastra observational memory; Vercel AI SDK loop-control; Pydantic AI capabilities; CrewAI, smolagents, AutoGen, AG2 (notebook), Mem0.

## Key findings

1. No `Summarizer` implementation exists in the SDK; only the Protocol at `vidbyte/middleware/compaction/base.py:42-47`. Summarize modes refuse to construct without one (`context_compaction.py:121-124`, `:261-264`). Anything that summarizes needs new code.
2. The existing trim middleware never persists: `before_model_call` transforms rewrite one call's `messages` only (`runtime.py:1085-1125`, snapshot at `:1196`). The only persistence seam without touching the shared loop is `AgentSwarmMemberRuntime._after_tool_iteration` (`member.py:60`), which already receives the live list.
3. `compaction_trigger_tokens` / `compaction_target_tokens` are accepted, validated and serialized but consumed nowhere in the runtime.
4. The task prompt and system prompt live outside `messages`, so compaction cannot lose the goal.
5. Anthropic's on-demand/background compaction (beta `compact-2026-09-04`) is the strongest provider-native mechanism and its "splice at `sent`" rule maps directly onto the seam in 2; it needs beta-header plumbing the provider lacks (`anthropic.py:72-74`).
6. The best reusable artefacts from others are prompt texts, not code: Codex's handoff prompt and summary prefix, LangChain's sectioned checklist prompt and "summary as the first user message" shape.
7. `CompactCodexThreadTool` / `thread_helpers.py`, listed in request.md:167, do not exist on this branch.

## Rejected and why

- Anthropic threshold compaction (`compact_20260112`): the block arrives inside a normal reply; the formatter flattens text-only replies to a string (`formatter.py:388-396`), so the block would be lost; docs also say it may fail when tools are defined and must use the same model.
- OpenAI server-side compaction / `POST /responses/compact`: opaque encrypted item must be echoed back; `_responses_items` rebuilds input from a chat-shaped transcript, so the roundtrip is unverified and OpenAI-only.
- Reusing `ContextCompactionTool` as the member tool: wrong name (`compact_context`), 24 modes exposed to the model, needs a `ContextState` the loop does not expose, summarizes synchronously inside the tool call.
- A summarizing `before_model_call` middleware: would re-summarize on every call because transforms never persist.
- Google ADK / LangChain / Letta / Mastra code: framework-bound (LangGraph, ADK runtime, hosted server); only their rules and prompts transfer.
- Pruning-only mechanisms (Vercel `pruneMessages`, AutoGen contexts, smolagents, AG2 limiters, Anthropic context editing): already covered by the SDK's trim modes; cannot preserve peer promises.

## Not reachable / unverified

- 404: Codex `core/templates/compact/prompt.md` (old path; the `prompts/templates/compact/` path worked), AG2 advanced-concepts pages (2), Gemini CLI docs (3), Letta `guides/agents/compaction`.
- 403: `platform.openai.com` API reference (the `developers.openai.com` mirror worked but was truncated before the response schema).
- Redirects handled: platform.openai.com to developers.openai.com; ai.pydantic.dev to pydantic.dev/docs; google adk to adk.dev; platform.claude.com/agent-sdk to code.claude.com.
- Unverified: OpenAI compact response schema / encrypted field name; OpenAI item roundtrip in this SDK; Gemini CLI compression; Gemini explicit-cache default TTL; AG2 compressor parameters; cost of a real swarm compaction.

## Scratchpad files (untrusted downloads, kept out of the repo)

`C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\6308f8f2-185f-45a5-b1b7-9102079fc8ee\scratchpad\fetched\codex_summary_prefix.md`, `...\fetched\codex_prompt.md`, `...\fetched\langchain_summarization.py`.
