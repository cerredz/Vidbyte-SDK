---
slug: infinite-memory-context-economy
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-16 16:05
flags: none
---

# Request: InfiniteMemoryAgent context economy — bounded reads, masked search output, ranked memory search, cache-stable prompts, and opt-in delegated recall

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening question):
````
Question for InfiniteMemoryAgent inside of the vidbyte-sdk/. Right now we are using the GrepTool for trying to retrieve memory. Do you think that we can add a 'deterministic node' in the runtime where when the agent tries to retrieve a memory, it writes a description of what it is trying to find, passes this to another agent with a Greptool, and then that agent searches and returns a handoff when it actually finds this information. Think that this could be a way we save tokens for the main agent, what do you think, if it is a good idea how would we implement?
````

**Prompt 2** (after the assistant's first analysis):
````
okay new idea, I forget to think about the extra token cost of launching subagents for this. here is what i want you to think about now: .5) i thought that we merged the InfiniteMemoryAgent in a sucessor pr to pr #1084, can you check this. or did we merge it into 1084 and now we have to merge that one? 1) I like the read_lines cap, figure out how to implement this, walk me through it. 2) can you try to find any better implementations of "grep" that is faster, more accurate, and saves on tokens, feel like this could be a good idea to implement, as well as any other "better versions" of the tools that this agent has. 3) I want to add a node of determinism in the runtime for the agent that does the following: after the agent finds the memory that it needs using Grep, i want to "compact" and remove all of the tools call inputs/outputs (escept the final ones/ones that it needs) from the context window because the agent no longer needs this in the context window and I feel like we can prune these things deterministically (note,  if there is no obvious way to prune specific ooutputs deterministically, would it just be a better idea to prune the inputs)) 4) you see how these are very small changes to the architectural that can all have drastic effects, come up with  more ideas like this for me. Comment and talk me through all of this
````

**Prompt 3** (after the assistant's talk-mode walkthrough):
````
great, return to me a small checklist of things that you think  we do/add to the InfiniteMemoryAgent in the repo?
````

**Prompt 4** (the invocation of this pipeline, `/spec-pipeline`):
````
great,  this looks good. I want you to implement all of these in 1 pr for the vidbyte-sdk/ repo.  I merged 1084 so make sure local main is up to date.
````

"All of these" refers to the checklist in §B.1 (the assistant's reply to Prompt 3). The orchestrator confirmed before S0: PR #1084 is MERGED (2026-10-16 19:45 UTC, merge commit `2c84049c`); local `main` and `origin/main` are both at `0f2aeb48`, which contains it.

## B. Handoff block and decision ledger (verbatim)

### B.1 The checklist the user approved with "implement all of these in 1 pr" (assistant reply to Prompt 3, verbatim)

````
**Before anything else**
- [ ] **Merge #1084 into main.** Dispatch SDK CI on `feat/infinite-memory-agent` first, then retarget #1159 to main. Everything below needs the agent on main.

**Small changes, each independent, one small PR each**
- [ ] **Cap read_lines at a 200-line window.** Add `FileSystemToolConfig.max_read_lines`, a footer naming the next start line, and `InfiniteWorkspaceSettings.max_read_lines`. This stops one read from flushing half the history, and SWE-agent found a 100-line window beat whole-file reads (18.0 vs 12.7).
- [ ] **Mask old grep and read_lines outputs, keeping the inputs.** Reuse `ToolOutputSlidingWindowCompaction` with a new `tools` scope option, keep 3 per tool, and place it before the trim in `agent.py:87` and `launch.py:313`. The handoff from last turn covers this item and the read_lines window.
- [ ] **Change the workspace grep defaults.** Make it case-insensitive unless the pattern has a capital letter, and set `context_lines=0`. Both are options on `GrepTool`, set by `InfiniteMemoryAgentTools`. Measured: letter case alone decided 0 vs 1 gold hits, and the context lines caused the 8.4× overhead.
- [ ] **Trim with hysteresis.** When history goes over 90K, trim it to about 65K instead of to exactly 90K. This is one option on `TrimWithProviderBoundaries`, and it keeps the cached prefix stable between trims (modeled: −15% input tokens).
- [ ] **Shrink passed and fixed result cards.** Render them as `finished_lines` plus the summary, and keep the review and dropped entries only for failed, partial or unchecked cards. A full batch can reach about 64K tokens today.
- [ ] **Keep both the head and the tail of bash output.** `bash.py:34` keeps only the first 50 KB, so test summaries and stack traces get lost and the agent re-runs the command.

**Medium changes, each needing its own spec**
- [ ] **Take the map out of the cached prefix.** Freeze the map at run start and append one-line deltas when the workspace changes. This is the biggest modeled saving (−40% billed). It changes prompt wording, so fold it into the `feat/infinite-memory-prompts` spec.
- [ ] **Add `search_memory` on stdlib SQLite FTS5.** It uses BM25 ranking and 12-token snippets, keeps the index in memory, and refreshes it from file fingerprints. Quote every term before the MATCH. Measured: 12/12 matched, against 0–1/12 for plain grep, at 284 tokens against 3,003.
- [ ] **Send Anthropic `cache_control`.** The fix is in `providers/anthropic.py`, and it is SDK-wide, so it should be a separate PR. Claude models get no prompt caching today.

**Later, only if measurement says so**
- [ ] **Add the delegated `recall` subagent for multi-step questions.** The retriever cites locations and the code copies the text from disk. Build it only if, after `search_memory`, real-key traces still show root searches taking 2 or more calls.

**Don't:** combine masking with `DeduplicateToolCallsCompaction`. It keeps the first copy of a repeated call, which traps the agent in a re-run loop. And never stub `launch_subagent` inputs: task cards aren't journaled, so the history holds the only copy.
````

The user then overrode the per-item packaging in Prompt 4: everything goes in **one PR**, including the items the checklist called "separate PR" or "own spec" or "fold into the prompts spec". #1084 is already merged by the user.

### B.2 HANDOFF from the talk-mode turn (assistant reply to Prompt 2, verbatim)

````markdown
Goal: InfiniteMemory agents read files in bounded windows and stop carrying old grep/read_lines outputs, both enforced in code.
Repo / base: vidbyte-sdk. The generic parts (FileSystemToolConfig.max_read_lines, ReadLinesTool window, ToolOutputSlidingWindowCompaction `tools` option) branch off origin/main now. The InfiniteMemory wiring branches off origin/main after #1084 merges. PRs target main.
Scope: max_read_lines config + ReadLinesTool window and footer; `tools` scope option on the sliding-window strategy and its builder; InfiniteMemory wiring (constants, InfiniteWorkspaceSettings.max_read_lines, InfiniteMemoryAgentTools param, middleware tuples in agent.py and launch.py, README limits section).
Non-goals: no prompt text changes; CodingAgent and paradigm_minimal stay uncapped (default None); no input pruning; no DeduplicateToolCalls middleware; no FTS5 search (separate change).
Approach: reuse ToolOutputSlidingWindowCompaction in STRIP mode, scoped to ("grep", "read_lines"), keep_recent=3, placed before the history trim. Rejected: an "after found" trigger, because "found" is not observable and proxies misfire when searches and writes interleave.
Patterns to follow: lib/dataclasses/filesystem.py:75 + write_text.py:28 + coding.py:85 (config line limit); bash.py truncation marker; middleware/compaction/strategies.py:649 (window).
Files to touch: lib/dataclasses/filesystem.py (field + generalized line-limit validator); tools/filesystem/read_lines.py (clamp, footer "[lines A–B of N shown; read on with start=B+1]", metadata truncated/total_lines/next_start); middleware/compaction/strategies.py + engine.py + context_compaction.py (`tools` option); lib/constants/infinite.py (INFINITE_DEFAULT_MAX_READ_LINES=200, INFINITE_MASK_KEEP_RECENT=3, INFINITE_MASKED_TOOL_NAMES); agents/infinite/settings.py; tools/toolsets/infinite.py; agents/infinite/agent.py:87; agents/infinite/launch.py:309,313; agents/infinite/README.md.
Data / index decisions: none.
Failure modes to handle: file shorter than the window gives byte-identical output; start past EOF unchanged; an explicit end beyond the window is clamped with the footer; launch_subagent/remember/write_note outputs are never masked; middleware order is masking → trim → delegation limits.
Pre-answered questions:
- If OverwriteLineLimit's name no longer fits, generalize it into one validator used by both fields (it is not in the public contract). Do not ask.
- If an existing infinite feature test assumes read_lines reads to EOF, update it to the window behavior. Do not ask.
Decide yourself: footer wording, metadata key names, the placeholder wording (it must say the call above shows what was asked and that re-running restores it), test names.
Stop and ask only if: a CodingAgent test changes (the default leaked), or masking would require rewriting tool-call arguments.
Acceptance criteria:
- read_lines with no end on a 1,000-line workspace note returns 200 lines plus a footer naming next_start=201; a 50-line note returns exactly what it returns today.
- With 5 grep calls in a root history, the model-visible view shows the newest 3 grep outputs whole and the older 2 as the placeholder, while their tool calls (inputs) stay visible.
- launch_subagent cards are never masked; the trim runs on the masked view.
- InfiniteWorkspaceSettings rejects max_read_lines of 0, a negative number, a bool, or a float, naming the field.
Verification: python scripts/run_ci.py (full gate per AGENTS.md; run without PYTHONPATH).
````

Note: this handoff's "Non-goals" (no prompt text changes, no FTS5) were written for a smaller PR. Prompt 4 widened the PR to every checklist item in §B.1, so prompt-text changes are now in scope where a §B.1 item needs them (the map wording, the new tools), and FTS5 `search_memory` is in scope.

### B.3 The latest Re-entry `Decided:` ledger (assistant reply to Prompt 3, verbatim)

````
Decided: the 11-item order above · read window 200 lines · mask outputs, keep inputs · FTS5 `search_memory` · recall subagent only after measuring.
Open: the real-key 120-call run, which would confirm or overturn the modeled cache numbers.
Needs you: 1. Dispatch CI on #1084 now? — default: yes. 2. Bundle the five small changes as one PR or five? — default: one PR per item. *Reply "go" to accept all defaults.*
````

Prompt 4 answered "Needs you" 2 by overriding the default: one PR for everything. Item 1 is moot (#1084 merged).

## C. Structured conversation notes

### Key decisions
- **Scope = every build item in §B.1, in one PR, against `main`.** Ten build items: (1) read_lines window, (2) masking old search outputs, (3) workspace grep defaults, (4) trim hysteresis, (5) result-card diet, (6) bash head+tail, (7) map out of the cached prefix, (8) `search_memory` on SQLite FTS5, (9) Anthropic `cache_control`, (10) delegated `recall` subagent. Plus the two "Don't" rules as constraints.
- **read_lines window: 200 lines** for InfiniteMemory agents, via `FileSystemToolConfig.max_read_lines` (default `None` = today's behavior for every other toolset) and `InfiniteWorkspaceSettings.max_read_lines` (default constant 200). Footer names the shown range, the total line count, and the next start line; metadata carries `truncated`, `total_lines`, `next_start`. No per-line numbering (costs 2–3 tokens/line and models paste numbers into `edit_file` old_text). Reasoning: one read of a 40k-char note put 10,037 tokens into history (measured); worst case ~50K tokens (the 200,000-char loop cap). SWE-agent Table 3: 100-line viewer 18.0% resolved vs 30 lines 14.3% vs full file 12.7%. 200 chosen over 100 because each extra root call at the history cap re-sends ~100K tokens, so the window must fit "read the passage search found" in one call; flip condition: traces show ≥3 consecutive windows of one file → raise it.
- **Masking ("the deterministic node" of Prompt 2 item 3): mask outputs, keep inputs.** Reuse `ToolOutputSlidingWindowCompaction` (`vidbyte/middleware/compaction/strategies.py`) through `MessageHistoryCompactionMiddleware.tool_output_sliding_window(...)` in STRIP mode, keep the newest 3 outputs **per tool**, scoped by a new `tools` option to the search/read tools (`grep`, `read_lines`, and `search_memory`). Placeholder wording must say the call above shows what was asked and that re-running it restores the output. Place it before the history trim. Inputs stay because a grep input is ~20 tokens vs ~3,000 output (<1%), and the inputs are the agent's record of what it already searched (SWE-agent: repeated iterative search "can exhaust an agent's cost budget"). Evidence: JetBrains "The Complexity Trap" (arXiv 2508.21433) — observation masking halves cost vs the raw agent while matching LLM summarization's solve rate; Anthropic context editing defaults to keeping 3 tool uses.
- **No "after it finds" trigger.** The window is trigger-free: the final search outputs are the newest, so they are always kept; older ones drop out as newer ones arrive.
- **Workspace grep defaults:** smart-case (case-insensitive unless the pattern contains an uppercase letter) and `context_lines=0`, as constructor options on `GrepTool` that `InfiniteMemoryAgentTools` sets for the workspace instance; `GrepTool`'s own defaults stay as they are for every other caller.
- **Trim hysteresis:** when history exceeds 90K tokens, trim down to ~65K (a low watermark) instead of to exactly 90K; an option on the shared `TrimWithProviderBoundaries` strategy/builder, set by InfiniteMemory. Reason: at steady state the exact-cap trim drops the oldest group on nearly every call, so the first history message changes and the whole history misses the provider's prefix cache.
- **Result-card diet:** cards with verdict passed or fixed render as the existing `InfinitePair.finished_lines` format plus the summary; failed, partial, and unchecked cards keep the full card (review, dropped entries, files). The journal keeps every card whole (unchanged). Reason: four card fields capped at 800 tokens each → up to ~3.2K tokens per card; at `max_parallel` 20 a batch result reaches ~64K tokens, and `launch_subagent` is an internal tool, so the loop's 200K-char result cap never applies.
- **Bash head + tail:** `BashTool` keeps only the first `BASH_MAX_OUTPUT_BYTES` (50,000) bytes; keep a head and a tail instead so test summaries, stack traces, and the exit-code line survive. This is SDK-wide (BashTool is shared).
- **Map out of the cached prefix:** the root's workspace map is upserted at `TOP_OF_CONTEXT` (rendered in the system context zone, before the system body and the whole history) and re-rendered after every tool iteration (`InfiniteMemoryRuntime._after_tool_iteration`). Any workspace change therefore changes the system zone and invalidates the cached prefix for the whole history. Decision: freeze the map at run start and send one-line deltas when the workspace changes (assistant default; the alternative `END_OF_CONVERSATION` placement was rejected as the default because it renders as a trailing assistant-role message, which Anthropic treats as a prefill). The root prompt currently says the map is "redrawn after each of your tool calls", so its wording changes in this PR (Prompt 4 put everything in one PR, overriding "fold it into the feat/infinite-memory-prompts spec").
- **`search_memory` on stdlib SQLite FTS5:** a new read-only tool for every InfiniteMemory agent. Porter + unicode61 tokenizer, `bm25()` ranking (smaller = better), `snippet()` capped (the token-count argument must be 1–64; 12 was measured), default top-10 plus a total-match line; entries projected as `#id kind: snippet`, notes as `path:line: snippet`. Index in memory per workspace, refreshed from file fingerprints (mtime + size) before each search so `bash` writes are caught. Every query term is quoted before building the MATCH (FTS5 syntax treats `word:` as a column filter and supports operators; `price:59` would raise). grep stays for exact/regex needs. FTS5 is lexical, so the README non-goal "No semantic or vector search" stays true.
- **Anthropic `cache_control`:** `vidbyte/providers/anthropic.py` sends `system` as a plain string and `cache_control` appears nowhere under `vidbyte/`, so Claude models never get prompt caching. Anthropic's automatic mode needs one top-level `cache_control` field. SDK-wide change in the Anthropic adapter.
- **Delegated `recall` subagent (the Prompt 1 idea):** see "Open questions" Q-ORCH-1 for how it is scoped in this PR. Design settled in the conversation: a `recall` tool taking `question`, `purpose`, optional `known`, optional `terms`; code validates the request and a per-agent recall quota; code pre-runs `search_memory(terms)` and puts the hits in the retriever's first message; the retriever is a fresh `BaseAgent` (new role RETRIEVER) holding only `search_memory`, `grep` (notes), and `read_lines` (capped) — no `bash`, `remember`, `write_note`, `edit_file`, `launch_subagent`, or `recall` — with a small turn cap (~8); it ends with lines `FOUND #<id> (why)`, `FOUND <path>:<start>-<end> (why)`, or `NOT FOUND (what was searched)`; code parses the citations, checks each (entry live, path inside the workspace, range within the line cap), and **copies the cited text from disk** (the retriever never writes the content the caller reads); the card is capped (~1,500 tokens) and lists what was not found and which searches ran. Mode is an enum on `InfiniteWorkspaceSettings`: DIRECT (today: grep + read_lines + search_memory) or DELEGATED (root and generators get `recall` and lose `grep`, keeping `read_lines` for known paths; verifiers keep raw `grep` because they check sources). Same model as the rest of the tree. A recall does not count toward `max_agents`; a per-agent quota and the turn cap bound it. Nested agent usage already bills into the root's ledger through a ContextVar (`vidbyte/lib/usage_ledger.py`), so the retriever's tokens appear in the run's usage with no extra work.

### Rejected alternatives
- Pruning tool-call **inputs** for read tools — <1% of their tokens and it removes the search record.
- An "after the agent finds it" trigger for compaction — "found" is not observable; proxies (the next non-search call) misfire when searches and writes interleave.
- Stubbing `launch_subagent` inputs — `InfiniteRunJournal.pair_started` journals only `{"key": key}`, so the task card exists nowhere else.
- Stubbing `write_note`/`edit_file` inputs — recoverable from disk in principle, but it rewrites provider-specific tool-call argument shapes and invites the model to copy a stub into a new write; Anthropic ships `clear_tool_inputs` defaulting to false. Not in this PR.
- `DeduplicateToolCallsCompaction` alongside masking — it keeps the first copy of a repeated call; because compaction is a per-call view, a re-run of a masked call would be deleted on every call and the agent would loop until `max_iterations`.
- ripgrep as the memory search backend — 74 ms (Python GrepTool) vs 10 ms (rg, incl. spawn) vs 0.1 ms (FTS5 query) at the 2M-token workspace cap; speed is invisible next to model latency; packaging gaps (PyPI `ripgrep` 15.x has no Windows wheel; `python-ripgrep` caps Python < 3.13; `ripgrepy` is GPL-3.0 and needs a system rg).
- bm25s (needs numpy + scipy), tantivy (heavy for an 8 MB index), semantic/hybrid search (README non-goal).
- Anthropic server-side context editing — Claude-only; its default trigger (100,000 input tokens) never fires under a 90K history cap.
- `AgentTool` (`vidbyte/tools/agent_tool.py`) for the retriever — it forwards the parent's whole conversation, the opposite of what recall needs.
- `END_OF_CONVERSATION` placement for the map as the default fix — trailing assistant-role message = Anthropic prefill.
- Scoped child maps, a "parallel tool calls in one turn" prompt nudge, deferred tool schemas — discussed in the talk turn but **not** in the §B.1 checklist; out of scope.

### Constraints and assumptions
- One PR, base `main`, at `0f2aeb48` (contains #1084). Do not depend on PR #1159 (`feat/infinite-memory-events`, open, targets `feat/infinite-memory-agent`): `vidbyte/agents/infinite/events.py` and `vidbyte/context/handoff/infinite.py` are **not on main**, so this PR adds no run events (no `memory_recalled` event). #1159 will need to merge with this PR's edits to `runtime.py`/`launch.py` later; keep edits to those files minimal and local.
- A separate in-flight spec branch `feat/infinite-memory-prompts` (docs only, S1 review round 2) is rewriting the InfiniteMemory prompt family. This PR changes prompt text only where a §B.1 item requires it (the map wording; descriptions of new tools; mentions of `search_memory`/`recall` where the role prompts list the memory tools). Keep those edits minimal.
- Repo rule (agents/infinite/README.md "Notes for agents"): keep deterministic limits out of prompts; a new cap is a constant, a settings field, and a check in code whose refusal or marker names it.
- The compaction middlewares are a **per-call view**: `AgentRuntime._apply_before_model_call_transform` (`vidbyte/agents/runtime.py`) replaces the messages sent on that call; raw history is unchanged. Transforms chain across middlewares (`vidbyte/middleware/pipeline.py` applies each decision to `ctx` before the next middleware runs). Consequence for hysteresis: a stateless view cannot "trim to 65K once and let it grow"; the strategy must remember its cut point between calls and reset when the history is not an extension of the last one (a new run clears the root's history).
- Each agent builds its own middleware instances (agents/infinite/agent.py "WHAT NOT TO DO" 3: do not share one middleware instance between agents).
- SDK CI is dispatch-only; the local gate is the evidence: `python scripts/run_ci.py` with `PYTHONPATH` unset.
- The measured numbers in this file came from seeded scratch benchmarks run on 2026-10-16 against the code of the #1159 worktree (GrepTool, ReadLinesTool, and the compaction strategies are identical on main). The cost-model numbers (−40% billed, −15% input) are a model, not a measurement.

### Clarifications and answers
- Q (Prompt 2 .5): was InfiniteMemoryAgent merged through a successor PR? — A (assistant, checked with gh): #1113 merged into #1084's branch, not main; #1084 had to merge. — Then the user (Prompt 4): "I merged 1084 so make sure local main is up to date." Verified: #1084 MERGED, local main = origin/main = `0f2aeb48`.
- Q (Prompt 2 item 3): if outputs cannot be pruned deterministically, prune inputs instead? — A (assistant): no for read tools (numbers above); outputs can be pruned deterministically with the existing sliding-window strategy, keeping inputs as the receipt.
- Q (Prompt 1): is a delegated retrieval agent a good idea? — A (assistant): yes for multi-step questions; a deterministic compact search captures most of the win for plain lookups; the retriever must cite and the code must transcribe from disk.
- Q (Prompt 2 opener): what about the extra token cost of launching subagents? — A (assistant): a retriever turn costs ~10–15K tokens (estimate) while a root call at the 90K history cap re-sends ~100K, so delegation wins when a search would take the root ≥2 calls and loses on a 1-call lookup.

### Terminology
- **InfiniteMemoryAgent / root / generator / verifier / pair** — as defined in `vidbyte/agents/infinite/README.md`.
- **workspace map** — the `TextContextItem` with id `INFINITE_MAP_PRIMITIVE_ID` built from `InfiniteWorkspace.map_text()`.
- **masking** — replacing an older tool **output** in the model-visible view with a short placeholder while the tool **call** (input) stays visible.
- **read window** — the cap on lines one `read_lines` call returns, with a footer saying how to read on.
- **trim hysteresis / low watermark** — trimming history to a lower target than the cap so trims are rare and the cached prefix stays stable between them.
- **card diet** — rendering passed/fixed result cards compactly to the parent.
- **cached prefix** — the leading part of a provider request unchanged since the previous call, which the provider bills at a cache-read price.
- **search_memory** — the new FTS5-backed ranked memory search tool.
- **recall / retriever** — the delegated retrieval tool and the fresh subagent it runs.
- **DIRECT / DELEGATED** — the two values of the recall-mode enum.

### Implementation hints
- Line numbers quoted in §B came from the #1159 worktree; **re-verify every line on main** (main's infinite package has no `events.py`).
- read_lines window: `FileSystemToolConfig` in `vidbyte/lib/dataclasses/filesystem.py` already has `max_overwrite_lines` validated by `OverwriteLineLimit` (not exported in `contracts/sdk-public-api.json` or `vidbyte/lib/dataclasses/__init__.py`); `vidbyte/tools/filesystem/write_text.py` reads `self._config.max_overwrite_lines`; `vidbyte/tools/toolsets/coding.py` sets it. `ReadLinesTool` is used by `tools/toolsets/coding.py`, `tools/toolsets/infinite.py`, `tools/toolsets/paradigm_minimal.py` — only the infinite toolset sets the window. Existing test `tests/test_filesystem_tools.py::test_read_lines_returns_selected_lines_newline_joined` must stay green.
- Masking: `ToolOutputSlidingWindowCompaction` counts tool outputs from newest to oldest **per tool name** (`_message_tool_name`) and compacts those beyond `keep_recent`; engine dispatch in `vidbyte/middleware/compaction/engine.py` reads `options.get("placeholder")`; builder `MessageHistoryCompactionMiddleware.tool_output_sliding_window` in `vidbyte/middleware/compaction/context_compaction.py` does not expose `placeholder` today. InfiniteMemory middleware tuples: root in `vidbyte/agents/infinite/agent.py` (`middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS), DelegationLimitsMiddleware(...))`), children in `vidbyte/agents/infinite/launch.py` `InfinitePair._agent`.
- Trim: `TrimWithProviderBoundariesCompaction` in `strategies.py` keeps system groups first, then the newest whole groups that fit `max_tokens`.
- Grep: `vidbyte/tools/builtins/code_search/grep.py` — literal by default via `re.escape`, case-sensitive, `context_lines` default 2 (clamped 0–5), `max_results` default 50, `max_chars` default 12,000 (cap 50,000); `InfiniteMemoryAgentTools.get_tools` (`vidbyte/tools/toolsets/infinite.py`) builds it with `ignore_patterns=(INFINITE_RUNS_DIRNAME, INFINITE_SUPERSEDED_FILE)` and a derived `max_file_bytes`.
- Bash: `vidbyte/tools/builtins/bash.py` — `BASH_MAX_OUTPUT_BYTES = 50_000`, keeps the first bytes, reads and counts the rest, appends `[output truncated: N bytes not shown]` and `exit code: N`; the four BASH_* constants are read as module globals at call time.
- Result cards: `InfinitePair.render` and `InfinitePair.finished_lines` in `launch.py`; template `vidbyte/prompts/prompts/infinite_memory/result_card.md`; `INFINITE_CARD_TEXT_MAX_TOKENS = 800`.
- Map: `InfiniteMemoryRuntime.arun` upserts `self._map()` at `ContextWindowPlacement.TOP_OF_CONTEXT`; `_after_tool_iteration` re-upserts it; `ContextManager._items_for_context_zone` renders TOP and END_OF_CONTEXT items in the system zone; `ContextWindowPlacement` has TOP_OF_CONTEXT, END_OF_CONTEXT, TOP_OF_CONVERSATION, END_OF_CONVERSATION; conversation placements render as assistant messages (`render_conversation_messages`); `AgentRuntime._build_system_string` order: fixed header, loop settings, primitives zone, body. Children draw their map once at build (`InfinitePair._agent`).
- Anthropic: `vidbyte/providers/anthropic.py` builds `payload["system"] = instructions`; pricing for cache reads/writes lives in `vidbyte/agents/pricing/anthropic.py` (`cache_creation_input_tokens`, `cache_read_input_tokens`). Anthropic docs (verified 2026-10-16): automatic mode = "Add a single `cache_control` field at the top level of your request"; default TTL 5 minutes; cache writes 1.25× base input, reads 0.1× (0.05× on Opus 5.5/Sonnet 5.5, 0.025× on Fable 5.1); minimum cacheable length 512 tokens on the 5.5 models and Fable 5.1, 1,024 on Sonnet 4.5/4.6, 2,048 on Opus 4.7, 4,096 on Opus 4.5/4.6 and Haiku 4.5.
- FTS5 (verified 2026-10-16): stdlib `sqlite3` here is SQLite 3.38.4 with FTS5 and the trigram tokenizer; CPython's Windows and macOS builds define `SQLITE_ENABLE_FTS5`; Linux CPython uses the system SQLite (FTS5 presence there unverified — the code must fail clearly if FTS5 is missing). `snippet()` last argument: "The maximum number of tokens in the returned text. This must be greater than zero and equal to or less than 64." `bm25()`: "The better the match, the numerically smaller the value returned." Measured at the cap (8,000 entries + 80 notes, 33,737 rows): index build 125 ms, query 0.1 ms, row insert 0.04 ms.
- Workspace: `InfiniteWorkspace` (`vidbyte/agents/infinite/workspace.py`) owns entries (`entries(ids)` raises for non-live ids), commits, descriptions, `map_text()`, `relative(path)`; grep skips `.runs/` and `superseded.jsonl`.
- Memory tools registry: `InfiniteMemoryToolRegistry` (`vidbyte/lib/registries/infinite.py`) names memory tools by preset and role; new tool names go in `vidbyte/lib/constants/infinite.py` and `INFINITE_RESERVED_TOOL_NAMES` (and `INFINITE_RUN_BOUND_TOOL_NAMES` if run-bound).
- Prompts: one `.md` file per text in `vidbyte/prompts/prompts/infinite_memory/`, registered in `infinite_memory.json`, keyed by `vidbyte/lib/enums/prompts.py` `Prompt` members.
- Placement (AGENTS.md): dataclasses in `vidbyte/lib/dataclasses/<domain>.py`, enums in `vidbyte/lib/enums/<domain>.py` exported from `vidbyte/lib/enums/__init__.py`, constants in `vidbyte/lib/constants/<domain>.py`; `vidbyte/lib/` never imports a higher layer; `vidbyte/tools/` may not import `vidbyte.agents`.
- Public API changes require regenerating `contracts/sdk-public-api.json` with `scripts/generate-sdk-public-api.py`.

### Open questions
- **Q-ORCH-1 — the `recall` item.** §B.1 lists it under "Later, only if measurement says so", and the §B.3 ledger says "recall subagent only after measuring"; Prompt 4 says "implement all of these in 1 pr". Orchestrator default, to be carried by the spec as an explicit Q with this default: **build it, opt-in** — `InfiniteRecallMode.DIRECT` is the default, so no run changes behavior unless the developer sets DELEGATED; the measurement then decides whether DELEGATED ever becomes the default. No run event for recall (events are not on main).
- **Q-ORCH-2 — Anthropic `cache_control` reach.** Automatic mode charges 1.25× on cache writes; a one-shot Anthropic call that is never re-read pays more. The spec must decide whether the field is sent on every Anthropic request or only where a loop re-sends the prefix, from what the adapter and its callers allow, and state the cost trade-off.
- **Q-ORCH-3 — map deltas.** Where the one-line delta lands (inside the newest tool result, or another position valid for every provider and not a trailing assistant message), what it says, and how the root still learns totals against caps.
- **Q-ORCH-4 — low watermark value** (~65K was the conversation's figure) and how the hysteresis state resets between runs.
- **Q-ORCH-5 — existing tests whose asserted behavior this PR deliberately changes** (card rendering for passed/fixed pairs, the root's per-iteration map redraw, bash truncation shape): the spec must list them by name so the test author can update them, citing the spec ID.

## D. Weighted words

- "implement **all** of these in **1** pr for the vidbyte-sdk/ repo." — Prompt 4
- "**make sure** local main is up to date." — Prompt 4
- "remove **all** of the tools call inputs/outputs (escept the final ones/ones that it needs) from the context window" — Prompt 2
- "the agent **no longer needs** this in the context window and I feel like we can prune these things **deterministically**" — Prompt 2
- "better implementations of "grep" that is **faster, more accurate, and saves on tokens**" — Prompt 2
- "these are **very small** changes to the architectural that can all have **drastic** effects" — Prompt 2
- "returns a handoff when it **actually finds** this information" — Prompt 1
- "a way we **save tokens** for the main agent" — Prompt 1
