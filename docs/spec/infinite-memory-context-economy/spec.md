---
spec: infinite-memory-context-economy
title: InfiniteMemoryAgent context economy
status: approved
revision: 4
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-context-economy
branch: feat/infinite-memory-context-economy
base_commit: 0f2aeb48382b49ecb179b3f3ca94f3807cd1edcc
created: 2026-10-16
updated: 2026-10-16
pr:
---

# Spec: InfiniteMemoryAgent context economy

> **TL;DR** — Ten changes in one PR make every InfiniteMemory root call cheaper and every memory lookup sharper. Reads come back in 200-line windows. Old search outputs are masked while their calls stay visible. The workspace grep is smart-case with no context lines. History is trimmed to a 65K low watermark. Passed cards shrink to one line plus the summary. Bash keeps the head and the tail. A ranked `search_memory` runs on stdlib SQLite FTS5. An opt-in delegated `recall` cites what it found and the code copies it from disk. Two changes are SDK-wide: bash head+tail, and Anthropic `cache_control`. The design decision that matters most is the stable request prefix. The root's system string becomes identical on every call: the map is drawn once, and the per-call loop counter and map changes move into a status message appended after each tool iteration. Anthropic breakpoints are block-level, which the Vidbyte gateway accepts, and they are sent only when this adapter has already sent the same tools and system. No agent whose system string changes per call ever pays the 1.25× cache-write premium.

## §0 User prompts

### 0.1 Invoking request (verbatim)
great,  this looks good. I want you to implement all of these in 1 pr for the vidbyte-sdk/ repo.  I merged 1084 so make sure local main is up to date.

("All of these" is the approved checklist quoted verbatim in `docs/spec/infinite-memory-context-economy/request.md` §B.1. The orchestrator verified that PR #1084 is merged and that local `main` equals `origin/main` at `0f2aeb48`.)

### 0.2 User replies during the run
_None yet. The orchestrator appends any reply the user sends during the run here verbatim, labeled with the revision it produced._

---

## Part A — Framing

## §1 Goal

The user runs InfiniteMemoryAgent for long sessions of several hundred calls and pays for every token each call re-sends. Today a root call at the 90,000-token history cap re-sends about 100,000 tokens. Several things inflate that and defeat provider caching:

- **Whole-file reads.** One read of a 40,000-character note put 10,037 tokens into history (measured, request.md §C).
- **Grep context lines.** Default grep spent 2,394 tokens on 3 hits, where a compact form takes 284 (8.4×, measured).
- **Letter case.** Case decided 0 versus 1 gold hits.
- **Old search outputs.** They stay in history until the trim drops them.
- **Exact-cap trim.** At steady state it drops the oldest group on nearly every call, so the first history message keeps changing.
- **Result cards.** A batch can reach about 64,000 tokens (`vidbyte/lib/constants/infinite.py:61-65`).
- **Head-only bash output.** It keeps only the first 50,000 bytes (`vidbyte/tools/builtins/bash.py:35`), so test summaries and stack traces at the end are lost and the agent re-runs the command.
- **A system string that changes every call.** The root's map is re-rendered after every tool iteration (`vidbyte/agents/infinite/runtime.py:104-110`), and the loop-settings block renders `- max_iterations: n/500` inside the system string (`vidbyte/agents/runtime.py:1690`). Any cached prefix is therefore invalidated on every call.
- **No Anthropic caching at all.** No cache field is ever sent to Anthropic (`git grep cache_control -- vidbyte` is empty), so Claude models never get prompt caching.

| ID | Goal (outcome) | How we will know | Source |
|---|---|---|---|
| G-1 | Each InfiniteMemory root call re-sends fewer billed input tokens, and the leading part of its request is identical from call to call so providers bill it at the cache-read price. | The root's system string and tool schemas are byte-identical on every call of a run (INV-7.1). Masked, windowed, and trimmed views stay under the caps that INV-1.x, INV-2.x, and INV-4.x name. In a real-key run, `cache_read_input_tokens` is greater than 0 from the third root call on (Anthropic, direct or gateway). | request.md §B.1 items 1, 2, 4, 5, 7; Prompt 1 "save tokens for the main agent" |
| G-2 | A memory lookup finds the right entry or note line in one call, in a few hundred tokens. | `search_memory` ranks by BM25 and returns at most 10 snippet lines plus a total line (FR-8.x). A lowercase grep pattern matches capitalized text in the workspace (FR-3.1). | request.md §B.1 items 3, 8; Prompt 2 "faster, more accurate, and saves on tokens" |
| G-3 | A long tool output keeps the part the agent needs: the end of a bash run, and a bounded window of a file with a pointer to the rest. | Bash output over the cap shows its first and last bytes and the omitted count between them (FR-6.x). A read past the window ends with a footer that names the next start line (FR-1.x). | request.md §B.1 items 1, 6 |
| G-4 | Claude models get prompt caching across the SDK, without raising the cost of any agent and without breaking gateway runs. | Repeat requests from one adapter carry block-level `cache_control` marks. A request whose tools and system were not sent before carries none (FR-9.x). The gateway admits the body (backend `provider/generative_models/client.py:260-278`, `_require_short_cache`). | request.md §B.1 item 9; pipeline.md ruling "Item 9 must survive the Vidbyte gateway" |
| G-5 | A developer can opt in to delegated recall for multi-step memory questions. The caller then receives cited text copied from disk, never the retriever's words, and no default run changes. | With `InfiniteRecallMode.DIRECT`, the default, no agent holds `recall`. Under `DELEGATED`, a recall card holds only transcribed citations, within its token cap (FR-10.x). | request.md Prompt 1, §B.1 item 10, §C Q-ORCH-1 |

## §2 Objective

When this PR merges into `main`, the following exist that do not exist today:

- **Read window.** `FileSystemToolConfig.max_read_lines` and the `ReadLinesTool` window with its footer.
- **Masking scope.** A `tools` scope and a `placeholder` on the per-tool sliding-window compaction and its middleware builder.
- **Trim hysteresis.** A `low_watermark_tokens` option on the provider-boundary trim. Both edited strategies move into one new module, so `strategies.py` shrinks below 1,000 lines.
- **Grep options.** `smart_case` and `context_lines` constructor options on `GrepTool`.
- **Bash head and tail.** `BashTool` output that keeps a head and a tail (SDK-wide).
- **Anthropic caching.** Repeat-gated block-level `cache_control` breakpoints in the Anthropic adapter (SDK-wide).
- **Full-text index.** A canonical `FullTextIndex` helper on stdlib `sqlite3` FTS5.

InfiniteMemoryAgent also wires these in. Every agent gets 200-line read windows, smart-case grep with no context lines, masking of old `grep`/`read_lines`/`search_memory` outputs, and the 65K low watermark. Passed and fixed result cards are compact. The root's system string is stable: the map is drawn once per run, and a status message after each tool iteration carries the map changes and the loop counters. Every agent holds a new `search_memory` tool. With `InfiniteRecallMode.DELEGATED`, a `recall` tool runs a fresh retriever agent, then parses, checks, and transcribes its citations. The role prompts, the folder READMEs, the public API contract and the lint baseline change with them. This is the whole slice; nothing in the §B.1 checklist is left for a later PR. §3 lists what was deliberately left out.

## §3 Non-goals

- **NG-1** — A stable request prefix for generators, verifiers, and the retriever. They keep the loop-settings block in their system strings. — *Why not:* the orchestrator ruled that the iteration-counter fix is InfiniteMemory-root-scoped (pipeline.md). Children run on the plain `AgentRuntime` and would need a runtime of their own. The cost is a stated limitation (EC-7.6, EC-9.4); extending the fix is the optional Q-2.
- **NG-2** — Moving the loop-settings block out of the system string for every SDK agent. — *Why not:* pipeline.md rules it out of scope as an optional Q-n with default no (Q-3).
- **NG-3** — Semantic or vector search, ripgrep, bm25s, or tantivy as the memory search backend. — *Why not:* rejected in request.md §C. FTS5 is lexical, so the README non-goal "No semantic or vector search" stays true.
- **NG-4** — Pruning or stubbing tool-call inputs. This covers read tools, `launch_subagent` (whose task cards exist nowhere else), and `write_note`/`edit_file`. — *Why not:* rejected in request.md §C. Inputs are under 1% of read-tool tokens and are the agent's record of what it already searched.
- **NG-5** — Using `DeduplicateToolCallsCompaction` alongside masking. — *Why not:* it keeps the first copy of a repeated call, so re-running a masked call would loop until `max_iterations` (request.md §B.1 "Don't").
- **NG-6** — Run events such as `memory_recalled`. — *Why not:* `vidbyte/agents/infinite/events.py` is not on `main` (unmerged #1159).
- **NG-7** — Any change to the Vidbyte gateway, or Anthropic's top-level automatic `cache_control`. — *Why not:* the gateway is another repository. It refuses a top-level `cache_control` (backend `provider/generative_models/client.py:119`, the Anthropic allowed fields) and admits block-level marks.
- **NG-8** — Giving the model-facing `compact_context` tool the new `tools` scope. — *Why not:* not in the conversation (optional Q-4).
- **NG-9** — Making `DELEGATED` the default recall mode. — *Why not:* the checklist says to measure first. DIRECT stays the default (request.md §C Q-ORCH-1).
- **NG-10** — Rewriting the `grep` and `read_lines` descriptions to the field guide's 4–5 sentences. — *Why not:* it would change every agent's tool schema, which was not discussed (optional Q-5). This PR appends sentences only when a non-default option is set.
- **NG-11** — A canonical `vidbyte/lib` head+tail helper adopted by the existing head/tail implementations. — *Why not:* the bash window streams bytes with bounded memory, while `strategies._head_tail_text`, `setup_commands._output_tail`, and the HEAD_TAIL preview slice finished strings. Unifying them is unrelated refactoring (optional Q-6).
- **NG-12** — Prompt caching for Claude models reached through OpenRouter or another OpenAI-compatible adapter, and any change to OpenAI or Gemini caching. — *Why not:* the checklist names `providers/anthropic.py`. OpenAI and Gemini cache prefixes automatically and gain from G-1 with no adapter change.
- **NG-13** — Line numbers on every `read_lines` line. — *Why not:* rejected in request.md §C. They cost 2–3 tokens per line, and models paste them into `edit_file` old_text.
- **NG-14** — Scoped child maps, a "parallel tool calls in one turn" prompt nudge, and deferred tool schemas. — *Why not:* discussed but not in the §B.1 checklist (request.md §C rejected alternatives).
- **NG-15** — A new `InfiniteAgentRole.RETRIEVER` member. — *Why not:* roles key the memory-tool registry. Every role must hold `remember` and `write_note` (`tests/features/infinite_memory_agent/test_infinite_memory_contract.py:383-387`), but the retriever holds no memory tools, so it is built without a role (D-14).

## §4 Developer usage

```python
import asyncio
from pathlib import Path

from vidbyte import InfiniteRecallMode, InfiniteWorkspaceSettings
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.tools.filesystem.read_lines import ReadLinesTool
from vidbyte.tools.types import ToolCall

notes = Path("notes")
notes.mkdir(exist_ok=True)
(notes / "long.md").write_text("\n".join(f"line {n}" for n in range(1, 1001)), encoding="utf-8")

reader = ReadLinesTool(FileSystemToolConfig(root=notes, max_read_lines=200))
result = asyncio.run(reader.execute(ToolCall(tool_name="read_lines", arguments={"path": "long.md"})))
print(result.output.splitlines()[-1])
print(result.metadata["truncated"], result.metadata["total_lines"], result.metadata["next_start"])

workspace = InfiniteWorkspaceSettings(root="memory", recall_mode="delegated")
print(workspace.max_read_lines, workspace.recall_mode is InfiniteRecallMode.DELEGATED)
```

Prints exactly:

```text
[lines 1-200 of 1000 shown; read on with start=201]
True 1000 201
200 True
```

A developer who builds an `InfiniteMemoryAgent` changes nothing to get the savings. Every agent in the tree reads in 200-line windows, masks old search outputs, trims with hysteresis, and holds `search_memory`. The root sends the same system string on every call, and Claude models cache it. `recall_mode=InfiniteRecallMode.DELEGATED` (or the string `"delegated"`) is the only new opt-in. Any other toolset that builds `ReadLinesTool` without `max_read_lines` reads to EOF as before.

## §5 Flow diagram

```mermaid
flowchart TD
  A[InfiniteMemoryAgent.run] --> B[InfiniteMemoryRuntime.arun]
  B -->|map drawn once, TOP_OF_CONTEXT| C[AgentRuntime loop]
  C -->|system: fixed + map + body, no loop block| D[_build_iteration_call_options]
  D -->|provider messages| M1[Mask: ToolOutputSlidingWindowCompaction, tools scope, keep 3]
  M1 -->|masked view| M2[Trim: TrimWithProviderBoundariesCompaction, low_watermark_tokens]
  M2 -->|suffix view| M3[DelegationLimitsMiddleware]
  M3 --> E[TextModelRunner.arun]
  E --> F[AnthropicProvider._create_payload]
  F -->|tools+system digest seen before? add block cache_control| G[(Anthropic Messages API, direct or via gateway)]
  G -->|tool calls| H[Tool execution]
  H --> T1[read_lines: 200-line window + footer]
  H --> T2[grep: smart-case, 0 context lines]
  H --> T3[search_memory: InfiniteSearchMemoryTool -> the workspace's FullTextIndex FTS5, in a worker thread]
  H --> T4[bash: head + tail]
  H --> T5[launch_subagent: compact cards for passed/fixed]
  H --> T6[recall, DELEGATED only: InfiniteRecallTool -> retriever BaseAgent]
  T6 -->|FOUND/NOT FOUND lines| T7[parse, check, copy cited text from disk]
  H -->|tool results appended| I[InfiniteMemoryRuntime._after_tool_iteration]
  I -->|one user status message: map changes if any + loop counters| C
```

The run starts in `InfiniteMemoryRuntime.arun`, which draws the workspace map once into a run-local context. Each call then goes through the loop:

1. The runtime builds a system string that holds no per-call counter.
2. The three middlewares transform only that call's view of the history: masking, then trim, then delegation limits.
3. The Anthropic adapter adds cache breakpoints only when the same tools and system went out before.

After each tool iteration, the runtime appends one plain user message with the changed map lines, when there are any, and the loop counters. Raw history stays append-only, so the masked and trimmed views are pure functions of it.

Validation happens at the boundaries:

- Settings and record `__post_init__` checks run first.
- The recall request is a validated dataclass.
- Each citation is checked against the live entries and the workspace path rules.

Every tool returns `ToolResult.error` instead of raising. A missing FTS5 build fails only `search_memory`, with an error that names it.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §6 Behavior

IDs are grouped by item: `x.n` belongs to item x of request.md §B.1 (1 read window, 2 masking, 3 grep defaults, 4 hysteresis, 5 card diet, 6 bash, 7 stable root prefix, 8 search_memory, 9 Anthropic caching, 10 recall). Item 0 is cross-cutting. `AC-1` alone is the §4 snippet.

### 6.1 Invariants

**Cross-cutting (0)**
- **INV-0.1** — The run's raw history (the live `messages` list the loop appends to) is append-only. Masking and trimming change only the per-call view a middleware returns, and cache marks exist only on the adapter's payload copy. No item rewrites or removes an entry of the raw list.
- **INV-0.2** — Every new option on a shared SDK class defaults to main's behavior. Items 6 (bash) and 9 (Anthropic) are the only SDK-wide behavior changes. With every new option at its default, any agent other than InfiniteMemoryAgent sends the same requests and gets the same tool outputs as on `main`, except where those two items apply.
- **INV-0.3** — No prompt leaf names a deterministic limit's number. New caps are constants plus a check in code whose refusal or marker names them (`vidbyte/agents/infinite/README.md` Notes for agents).
- **INV-0.4** — The middleware order on every InfiniteMemory agent is masking, then the history trim, then delegation limits, wherever an agent holds them. The root and generators have all three; verifiers and the retriever have masking and trim.

**Item 1 — read window**
- **INV-1.1** — With `FileSystemToolConfig.max_read_lines=None`, `ReadLinesTool`'s output, metadata, and spec are identical to `main`.
- **INV-1.2** — With `max_read_lines=N`, the call's requested range is lines `start..min(end, total)`, or `start..total` when `end` is omitted, where `total` is the file's line count. When that range holds more than N lines, the output is its first N lines, then `"\n"`, then the footer `[lines {start}-{start+N-1} of {total} shown; read on with start={start+N}]`. `{start}`, `{total}`, and `{start+N}` are plain integers with no separators.
- **INV-1.3** — With `max_read_lines=N`, a requested range of N lines or fewer gives an output byte-identical to `main` for the same call, with no footer.
- **INV-1.4** — With `max_read_lines` set, the metadata keeps `path`, `start`, and `end` with their `main` meaning (`end` is the argument as given, `None` when omitted). It adds `truncated` (bool), `total_lines` (int), and `next_start` (`start+N` when truncated, otherwise `None`). With `max_read_lines=None` these three keys are absent.
- **INV-1.5** — `FileSystemToolConfig.max_read_lines` accepts `None` or an `int` of at least 1. `InfiniteWorkspaceSettings.max_read_lines` accepts an `int` of at least 1. Each refuses a `bool`, a non-`int`, or a value below 1 with a `ConfigurationError` that names its field.
- **INV-1.6** — A `start` past EOF returns an empty output with no footer, as on `main`. The errors for `start < 1`, `end < start`, and a missing file are unchanged.
- **INV-1.7** — With `max_read_lines` set, the spec description is main's sentence followed by exactly one sentence that names the limit. With it unset, the spec is unchanged.

**Item 2 — masking**
- **INV-2.1** — `ToolOutputSlidingWindowCompaction` with `tools=()` (the default) compacts every tool's older outputs exactly as on `main`.
- **INV-2.2** — With a non-empty `tools` scope, only `tool_result` messages whose tool name is in the scope are counted and compacted. Every other message is returned unchanged, including every `launch_subagent`, `recall`, `bash`, `remember`, `write_note`, `edit_file`, and `drop_entry` result.
- **INV-2.3** — For each scoped tool name, the newest `keep_recent` outputs stay whole. In STRIP mode each older output's content becomes the placeholder, and its metadata gains `compaction` and `original_chars`, as on `main`.
- **INV-2.4** — Masking never changes or removes a tool call (input) message.
- **INV-2.5** — The masked view is a pure function of the history it receives: the same messages always give the same view.
- **INV-2.6** — InfiniteMemory's placeholder is the text of the `masked_output` leaf. It says that the tool call above shows what was asked and that calling the tool again with the same arguments shows the output again.

**Item 3 — workspace grep**
- **INV-3.1** — `GrepTool` built without the new options behaves as on `main`: case-sensitive, a default of 2 context lines, and the same spec.
- **INV-3.2** — With `smart_case=True`, a pattern with no uppercase character matches without regard to case, and a pattern with one matches case exactly. In regex mode, a letter right after an unescaped backslash (as in `\S`, `\W`, `\D`, `\B`, `\A`, `\Z`) does not count as uppercase.
- **INV-3.3** — With `context_lines=K`, a call that omits the `context_lines` argument shows K lines around each match. A call that passes it still wins, clamped to 0–5 as on `main`.
- **INV-3.4** — The workspace grep of every InfiniteMemory agent (and of the retriever) is built with `smart_case=True` and `context_lines=0`. `CodingAgentTools` and `paradigm_minimal` build `GrepTool` as on `main`.

**Item 4 — trim hysteresis**
- **INV-4.1** — `TrimWithProviderBoundariesCompaction` with `low_watermark_tokens=None`, or with any value at or above `max_tokens`, returns the same output as `main` for every input.
- **INV-4.2** — With `0 <= L < M` (L = `low_watermark_tokens`, M = `max_tokens`), define B = M minus the tokens of the system groups, N = the tokens of the non-system groups, and S = M − L.
  - System groups are always kept.
  - If N ≤ B, nothing is dropped.
  - Otherwise, the trim drops the shortest prefix of non-system groups whose cumulative tokens reach `ceil((N − B) / S) · S`, or every non-system group when no prefix reaches it.
  - The kept non-system groups are always one contiguous suffix whose tokens are ≤ B.
- **INV-4.3** — No trim ever separates a tool call from its results (whole provider groups only, as on `main`).
- **INV-4.4** — Take two successive views where the later one equals the earlier one plus appended groups, and `ceil((N − B) / S)` has the same value for both. The first kept non-system group is then the same message in both views.
- **INV-4.5** — Every InfiniteMemory agent trims with `max_tokens=INFINITE_HISTORY_MAX_TOKENS` (90,000) and `low_watermark_tokens=INFINITE_HISTORY_LOW_WATERMARK_TOKENS` (65,000).

**Item 5 — result-card diet**
- **INV-5.1** — A card with status `done` and verdict `passed` or `fixed` renders as `InfinitePair.finished_lines((card,))`, then `"\n"`, then the summary, or `-` when the summary is empty.
- **INV-5.2** — Every other card renders exactly as on `main`, through the full `result_card` template.
- **INV-5.3** — A replayed card is rendered by the same rule and keeps the replayed label line before it.
- **INV-5.4** — The journal's `pair_finished` record still holds the whole card.

**Item 6 — bash head + tail**
- **INV-6.1** — When a command prints at most `BASH_MAX_OUTPUT_BYTES` bytes in total, the result is byte-identical to `main`. In that case the kept head and tail are joined before decoding, so a multi-byte character that straddles the head/tail edge decodes as on `main`.
- **INV-6.2** — Let T = `min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES // 2)` and H = `BASH_MAX_OUTPUT_BYTES − T`, so every cap keeps both a head and a tail (H ≥ T), and suppose a command prints more than H + T bytes and exits. The success output is then:
  - the first H bytes, decoded;
  - then `"\n[output truncated: {omitted:,} bytes not shown]\n"`, where omitted = total − H − T;
  - then the last T bytes, decoded;
  - then `"\nexit code: {n}"`.

  `metadata["truncated"]` is `True`.
- **INV-6.3** — The tool holds at most H + T bytes of output plus one read chunk, however much the command prints.
- **INV-6.4** — On a timeout, the error output is the head held so far, then the INV-6.2 marker with the count of bytes left out so far (only when that count is above 0, that is, when more than H + T bytes were read), then the tail held so far, then main's stopped line. A command that printed H + T bytes or fewer before the timeout shows all of them and no marker, with head and tail joined before decoding as in INV-6.1. The metadata keys are unchanged, and `truncated` is `True` exactly when bytes were left out. The count survives the timeout because `_collect` keeps it where `execute` can still read it after `wait_for` cancels the read.
- **INV-6.5** — `BASH_TIMEOUT_SECONDS`, `BASH_MAX_OUTPUT_BYTES`, `BASH_READ_CHUNK_BYTES`, and `BASH_KILL_GRACE_SECONDS` keep their values. All five `BASH_*` constants are read as module globals at call time.
- **INV-6.6** — The bash spec description says that the first and the last bytes are kept and that the bytes left out are counted.

**Item 7 — stable root prefix**
- **INV-7.1** — Within one root run without a caller `system` option, every model call's system string is byte-identical. The tool schemas are identical unless the root's catalog changed (an MCP attach or `add_tool` mid-run).
- **INV-7.2** — The root's system string holds no loop-settings block. The map item is drawn once at run start and is not upserted again during the run.
- **INV-7.3** — After each tool iteration that reaches `_after_tool_iteration`, the runtime appends at most one message `{"role": "user", "content": text}`:
  - **The workspace changed since the last report:** `text` is the `map_update` leaf with `{header}` set to the current map header line, and `{changes}` set to the current map line of every added or changed file plus `- {path}: removed` for every removed file, in the map's path order and then removed paths. The change lines are capped by the map's own rule and constants: when the header and the change lines together exceed `INFINITE_MAP_MAX_TOKENS` (TokenEstimate), only the first lines that fit are kept, and the last line is `INFINITE_MORE_FILES` naming how many change lines were left out. `InfiniteWorkspace.fit_map_lines`, lifted from `map_text`, applies the cut to both. When the loop-settings block is non-empty, `"\n\n"` and that block follow.
  - **Nothing changed, and the loop-settings block is non-empty:** `text` is the loop-settings block alone, with no leaf text, header, or change lines.
  - **Nothing changed, and the block is empty:** nothing is appended.

  The loop-settings block is the base `_render_loop_settings_block` rendered with the live counters, counting tool calls as the system-string path does: `tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts))` (`vidbyte/agents/runtime.py:406`). With the default loop settings (`max_iterations` 500) the root's block is never empty, so the root appends one status message on every tool iteration (NFR-7.2).
- **INV-7.4** — The first report diffs against the snapshot taken when the map was drawn. Every later report diffs against the previous report. A file is "changed" when its map line text differs, which means its token count or description changed. A report whose change lines were cut still advances the baseline to the current snapshot, so the lines left out are not repeated in the next report.
- **INV-7.5** — Generators, verifiers, and the retriever keep a map drawn at build and the loop-settings block in their system strings, as on `main`.
- **INV-7.6** — A caller `system` option still replaces the root prompt and the map for that run (prior spec D-27). Status messages are appended as for any other run.

**Item 8 — search_memory**
- **INV-8.1** — `search_memory` has permission READ and never writes the workspace.
- **INV-8.2** — The query is split on whitespace, and words holding no letter or digit are dropped. Each remaining word is wrapped in double quotes, with any `"` inside it doubled, before the words are joined into the MATCH expression. When no word remains, the search returns zero hits without running a MATCH. The match is the AND of those phrases. No query text can raise an FTS5 syntax error or act as an operator or a column filter.
- **INV-8.3** — Hits are ordered by `bm25()` ascending, best first. At most `INFINITE_SEARCH_MAX_HITS` (10) hit lines are returned, entries as `#{id} {kind}: {snippet}` and note lines as `{path}:{line}: {snippet}`. A last line follows that states how many hits are shown and how many matched in total.
- **INV-8.4** — Before each search, the tool compares every indexable file's fingerprint (`st_mtime_ns`, `st_size`) with the one it indexed. It re-reads files that changed or are new and drops files that are gone, so a search always reflects the disk at call time, including writes made by `bash`. The fingerprint recorded for a file is the one taken before its content is read, so a write that lands between the stat and the read leaves a fingerprint that differs from the disk, and the next search reads the file again.
- **INV-8.5** — The index holds:
  - one row per live entry in `entries.jsonl` (its `text`);
  - one row per non-blank line of every other text file under the workspace root, numbered as `grep` and `read_lines` number lines.

  It excludes everything under `.runs/`, `superseded.jsonl`, `files.jsonl`, files larger than the grep byte cap, and files whose first 2,048 bytes hold a NUL byte (the existing code-search text-file rule).
- **INV-8.6** — Each snippet is at most `INFINITE_SEARCH_SNIPPET_TOKENS` (12) tokens. `FullTextIndex.search` refuses `snippet_tokens` outside 1–64 and `limit` below 1.
- **INV-8.7** — When the interpreter's SQLite lacks FTS5, `search_memory` returns `ToolResult.error` with `metadata["error"] == "fts5_unavailable"`, and the message names FTS5 and the SQLite version. Building the agent and every other tool keep working.
- **INV-8.8** — A malformed line in `entries.jsonl` is left out of the index and never fails a search.
- **INV-8.9** — Every agent in one InfiniteMemory tree (the root, every generator and verifier, and every retriever) searches one shared `FullTextIndex`, owned by the `InfiniteWorkspace` object as `full_text`. Each `search_memory` call runs its refresh and its search in a worker thread (`asyncio.to_thread`) while holding the index's lock across both, so the event loop keeps serving the other agents and one call sees one consistent index.

**Item 9 — Anthropic cache_control**
- **INV-9.1** — The adapter never adds a top-level `cache_control` key.
- **INV-9.2** — A request whose tools-and-system digest this adapter instance has not sent before carries no marks, and its body is byte-identical to `main`.
- **INV-9.3** — A repeat request carries at most three marks, each exactly `{"type": "ephemeral"}` with no `ttl`:
  - on the system, sent as `[{"type": "text", "text": <system>, "cache_control": ...}]`, when the system is non-empty;
  - when `config.messages` is non-empty, on the last markable block of the last message;
  - when `config.messages` is non-empty, on the last markable block of the last message before the newest assistant message.

  A markable block is a non-empty `text` block, or a `tool_result`, `tool_use`, `image`, or `document` block. A non-empty string content is sent as one text block carrying the mark. Only a message that gets a mark is converted; every other message keeps its string form. Anthropic's Messages API documents a string content as shorthand for one `text` block, so the conversion changes the wire shape, not what the model reads (EC-9.10).
- **INV-9.4** — A request that already holds a `cache_control` key anywhere (top level through `extra_body`, system, tools, or any message block) gets no marks from the adapter.
- **INV-9.5** — The caller's `config.messages`, their content lists and blocks, and the `system` string are never mutated. Marks live only on new dicts and lists inside the payload.
- **INV-9.6** — The adapter remembers at most `ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT` digests and clears them when full.
- **INV-9.7** — The set of top-level payload keys is unchanged, so `EMITTED_KEYS[ModelProvider.ANTHROPIC]` still covers every body.

**Item 10 — recall**
- **INV-10.1** — With `InfiniteRecallMode.DIRECT` (the default), no agent holds `recall`, and `InfiniteMemoryToolRegistry.tool_names(preset, role)` returns main's names for every preset and role.
- **INV-10.2** — With `DELEGATED`, the root and every generator hold `recall` and do not hold `grep`, while keeping `read_lines` and `search_memory`. Verifiers hold `grep` and not `recall`.
- **INV-10.3** — The retriever holds exactly `grep`, `read_lines` (windowed), and `search_memory`, plus the loop's internal tools. It never holds `bash`, `remember`, `write_note`, `edit_file`, `drop_entry`, `launch_subagent`, or `recall`.
- **INV-10.4** — Every text under the card's found section is copied by code from disk: entries through `InfiniteWorkspace.entries`, line ranges from the file's lines. No retriever-written text appears there.
- **INV-10.5** — The tool accepts an entry citation only when the entry is live. It accepts a range citation only when all of these hold:
  - its path resolves inside the workspace to an existing file;
  - no part of the resolved workspace-relative path, compared case-insensitively, is one of `INFINITE_BOOKKEEPING_NAMES` (`.runs`, `entries.jsonl`, `superseded.jsonl`, `files.jsonl`), the tuple `search_memory` also ignores. Superseded memory, raw entry JSON, and run journals can therefore never be transcribed as found, and entries are cited only by `#id`;
  - `1 <= start <= end <= total lines`;
  - `end − start + 1 <= max_read_lines`.

  Every other citation is listed as rejected, with the reason. A FOUND line that matches the reply grammar but whose numbers fail the citation record's own checks (for example `FOUND notes/p.md:5-3` or `FOUND #0`) is rejected the same way: it never fails the recall, and every other citation in the reply is still checked.
- **INV-10.6** — Each agent's `recall` runs at most `INFINITE_RECALLS_PER_AGENT` retrievers. A call refused for validation or quota starts no agent and costs no quota.
- **INV-10.7** — The retriever's loop is capped at `INFINITE_RECALL_MAX_ITERATIONS` iterations. The card is `TokenEstimate.cap(rendered, INFINITE_RECALL_CARD_MAX_TOKENS - TokenEstimate.count(INFINITE_TRUNCATION_MARKER), INFINITE_TRUNCATION_MARKER)`. `cap` appends the marker after its cut, so subtracting the marker's own count keeps every card at most `INFINITE_RECALL_CARD_MAX_TOKENS` tokens (TokenEstimate); a card within the marker's count of the cap is cut by at most the marker's length. A cut card ends with `INFINITE_TRUNCATION_MARKER`. It renders `{question}`, `{not_found}`, `{rejected}`, and `{searches}` before `{found}`, so a cut removes transcribed text first. What was not found and which searches ran stay visible unless those sections alone exceed the cap (EC-10.6).
- **INV-10.8** — A recall does not count toward `max_agents` and writes no journal record. Its model usage reaches the run's usage through the existing ledger ContextVar.
- **INV-10.9** — The `recall` spec is internal (`metadata={"internal": True}`).
- **INV-10.10** — When the request names `terms`, the code runs one `search_memory` search per term, in the order given, before the retriever starts. Each term's own words are ANDed as INV-8.2 states; terms are never ANDed with each other, because each index row is one line. Each result goes under its term in the retriever's first message, which therefore holds at most `INFINITE_RECALL_MAX_TERMS` × `INFINITE_SEARCH_MAX_HITS` hit lines plus one total line per term.

**Must not regress:**
- **INV-R.1** — `CodingAgentTools` and `paradigm_minimal` build `ReadLinesTool` and `GrepTool` without the new options, so their output and schemas are unchanged (`vidbyte/tools/toolsets/coding.py`, `vidbyte/tools/toolsets/paradigm_minimal.py`).
- **INV-R.2** — `tests/test_filesystem_tools.py::test_read_lines_returns_selected_lines_newline_joined` and every overwrite-cap test pass unchanged. The `max_overwrite_lines` and `max_rewrite_lines` refusal text stays `"{parameter} must be None or an int of at least 1."`.
- **INV-R.3** — `from vidbyte.middleware.compaction import ToolOutputSlidingWindowCompaction, TrimWithProviderBoundariesCompaction` keeps working, and every existing compaction test passes unchanged (`tests/test_deterministic_compaction_middleware.py`, `tests/test_context_compaction_middleware.py`).
- **INV-R.4** — `tests/features/sdk_managed_text/test_managed_text_wire_contract.py` passes unchanged.
- **INV-R.5** — InfiniteMemory delegation caps, the journal, resume, and the workspace guardrails behave as on `main` (the resume, verification, and acceptance packs pass, apart from the deliberately changed tests named in §13).
- **INV-R.6** — `JevRuntime._after_tool_iteration` and the base hook contract (`vidbyte/agents/runtime.py:925`) are unchanged.

### 6.2 Acceptance criteria

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | a clean checkout of this branch | the §4 snippet runs | it prints exactly the three shown lines | P0 | `test_read_lines_window.py::test_section_4_snippet_prints_exactly_the_three_documented_lines` |
| AC-1.1 | a 1,000-line note and `ReadLinesTool(FileSystemToolConfig(root, max_read_lines=200))` | `read_lines` is called with only `path` | the output is lines 1–200 joined by `\n`, then `\n[lines 1-200 of 1000 shown; read on with start=201]`, and the metadata has `truncated=True, total_lines=1000, next_start=201` | P0 | `test_read_lines_window.py::test_a_long_file_returns_the_window_then_a_footer_naming_the_next_start` |
| AC-1.2 | a 50-line note and the same tool | `read_lines` is called with only `path` | the output equals main's output for the same call (no footer), and `truncated=False, next_start=None` | P0 | `test_read_lines_window.py::test_a_range_within_the_window_is_identical_to_main_with_no_footer` |
| AC-1.3 | the same 1,000-line note | `read_lines` is called with `start=950, end=2000` | the output is lines 950–1000 with no footer | P1 | `test_read_lines_window.py::test_a_range_running_past_the_end_returns_the_rest_without_a_footer` |
| AC-1.4 | `ReadLinesTool(FileSystemToolConfig(root))` (no window) | any call | the output, the metadata keys, and the spec equal `main` | P0 | `test_read_lines_window.py::test_without_a_window_output_metadata_and_spec_equal_main` |
| AC-1.5 | `InfiniteWorkspaceSettings` | it is built with `max_read_lines` set to 0, −1, `True`, or `2.5` | `ConfigurationError` names `InfiniteWorkspaceSettings.max_read_lines`, and `FileSystemToolConfig` names `max_read_lines` the same way | P0 | `test_read_lines_window.py::test_a_bad_window_is_refused_naming_the_field`<br>`test_infinite_memory_economy.py::test_the_workspace_read_window_validates_and_reaches_read_lines` |
| AC-1.6 | an InfiniteMemory agent with default settings | a root, generator, or verifier calls `read_lines` on a 1,000-line note | it gets 200 lines and the footer | P0 | `test_infinite_memory_economy.py::test_every_agent_reads_a_long_note_in_a_200_line_window_with_a_footer` |
| AC-2.1 | a root history with 5 `grep` calls and results | the masking middleware runs | the newest 3 grep outputs are whole, the older 2 are the `masked_output` text, and all 5 grep calls (inputs) are unchanged | P0 | `test_compaction_windows.py::test_a_scope_compacts_only_the_named_tools_and_keeps_the_newest_per_tool`<br>`test_infinite_memory_economy.py::test_the_root_masks_the_two_oldest_of_five_grep_outputs_and_keeps_every_call` |
| AC-2.2 | a history mixing `launch_subagent`, `bash`, `remember`, and 4 `read_lines` results | the InfiniteMemory masking runs | only the oldest `read_lines` output is masked, and every other result is unchanged | P0 | `test_infinite_memory_economy.py::test_only_read_lines_outputs_are_masked_among_launch_bash_and_remember_results` |
| AC-2.3 | `MessageHistoryCompactionMiddleware.tool_output_sliding_window()` with no new arguments | it compacts a history | the result equals main's | P0 | `test_compaction_windows.py::test_the_builder_with_no_new_arguments_equals_main` |
| AC-2.4 | an InfiniteMemory root whose masked view is over 90K tokens | one model call runs | the trim runs on the masked view: masking first, trim second | P1 | `test_infinite_memory_economy.py::test_masking_runs_before_the_trim_so_a_masked_view_under_the_cap_keeps_every_call` |
| AC-3.1 | an InfiniteMemory workspace note containing `Enterprise plan 999 USD` | an agent greps `enterprise plan` | the line matches, shown as `path:N` and `N: line` with no surrounding lines | P0 | `test_grep_smart_case.py::test_a_lowercase_pattern_ignores_case_and_an_uppercase_one_matches_exactly`<br>`test_infinite_memory_economy.py::test_every_agents_workspace_grep_is_smart_case_with_no_context_lines` |
| AC-3.2 | the same note | an agent greps `Enterprise` and then `ENTERPRISE` | the first matches and the second does not | P1 | `test_grep_smart_case.py::test_a_lowercase_pattern_ignores_case_and_an_uppercase_one_matches_exactly`<br>`test_infinite_memory_economy.py::test_every_agents_workspace_grep_is_smart_case_with_no_context_lines` |
| AC-3.3 | `GrepTool(root, smart_case=True)` | a regex pattern `\Senterprise` is searched with `regex=true` | it matches without regard to case (the `S` in `\S` does not count) | P1 | `test_grep_smart_case.py::test_a_letter_after_a_regex_backslash_does_not_count_as_uppercase` |
| AC-3.4 | `GrepTool(root)` (defaults) | any call | the output and the spec equal `main` | P0 | `test_grep_smart_case.py::test_grep_built_without_the_new_options_equals_main` |
| AC-4.1 | a trim with `max_tokens=90_000, low_watermark_tokens=65_000`, no system groups (so B = 90,000 and S = 25,000), and a non-system history of N = 91,000 tokens in groups of at most 500 tokens each, as the trim's token counter measures them | it runs | the kept history is one contiguous suffix of the newest groups, holding at most N − S = 66,000 tokens and more than 66,000 − 500 = 65,500 | P0 | `test_compaction_windows.py::test_a_91k_history_keeps_one_suffix_between_65_5k_and_66k` |
| AC-4.2 | that same history | groups of at most 500 tokens each, at most 24,000 tokens in total, are appended (so `ceil((N − B) / S)` stays 1) and it runs again | the first kept message is the same as in AC-4.1 | P0 | `test_compaction_windows.py::test_appending_up_to_24k_more_keeps_the_same_first_message` |
| AC-4.3 | `low_watermark_tokens=None` or ≥ `max_tokens` | it trims any history | the result equals main's (including main's non-contiguous keep) | P0 | `test_compaction_windows.py::test_without_a_low_watermark_the_trim_equals_main` |
| AC-4.4 | the InfiniteMemory middleware pair (masking, then the trim with the low watermark) and a root history grown past 90K by appending `read_lines` call-and-result groups whose outputs all have the same size, so masking never lowers N | the per-call view is computed after each append | from the first view that trims on, the first kept message changes at most `ceil(G / S)` times, G being the tokens appended after that view | P1 | `test_infinite_memory_economy.py::test_with_equal_outputs_the_cut_moves_at_most_once_per_s_tokens_appended` |
| AC-4.5 | the same pair at a view where N − B exceeds a multiple of S by less than the next append's net shrink (its `read_lines` output is smaller than the output it pushes past the newest 3) | that append is made, and later appends raise N − B past the multiple again | the first kept message moves back to an earlier message once and forward again once: two moves for one dip, as EC-4.3 states | P1 | `test_infinite_memory_economy.py::test_one_masking_dip_moves_the_cut_back_once_and_forward_once` |
| AC-5.1 | a batch whose pair finished `done`/`passed` | the parent reads the `launch_subagent` result | the card is `- {name}: done, verdict passed, entries {ids}` plus a newline plus the summary, and no review, dropped list, or files appear | P0 | `test_infinite_memory_economy.py::test_passed_and_fixed_cards_are_compact_while_failed_unchecked_and_partial_cards_stay_whole`<br>`test_infinite_memory_delegation.py::test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator` |
| AC-5.2 | a pair with verdict `failed`, `unchecked`, or status `partial` | the parent reads the card | it is the full `result_card` rendering, as on `main` | P0 | `test_infinite_memory_economy.py::test_passed_and_fixed_cards_are_compact_while_failed_unchecked_and_partial_cards_stay_whole` |
| AC-5.3 | a finished `passed` pair relaunched under the same name | the batch returns | the replayed label line is followed by the compact card | P1 | `test_infinite_memory_economy.py::test_a_replayed_passed_card_is_the_label_then_the_compact_card` |
| AC-6.1 | a command printing 60,000 bytes and exiting 1 | `BashTool` runs it | the output is the first 25,000 bytes, then `\n[output truncated: 10,000 bytes not shown]\n`, then the last 25,000 bytes, then `\nexit code: 1` | P0 | `test_bash_tool_head_tail.py::test_sixty_thousand_bytes_keep_the_first_and_last_25000_with_10000_counted_between` |
| AC-6.2 | a command printing 20 MB | `BashTool` runs it | traced peak memory stays bounded as in today's bound test, and the last line before `exit code` is the command's last line | P0 | `test_bash_tool_contract.py::test_large_output_keeps_the_first_bytes_counts_the_rest_and_memory_stays_bounded` |
| AC-6.3 | a command printing 1,000 bytes | `BashTool` runs it | the output equals `main` | P0 | `test_bash_tool_head_tail.py::test_output_within_the_cap_equals_main_even_with_a_character_across_the_head_tail_edge` |
| AC-6.4 | `BASH_TIMEOUT_SECONDS` patched short, and a command that prints exactly `BASH_MAX_OUTPUT_BYTES` bytes and then sleeps past the limit | `BashTool` runs it | the error output is every printed byte, then the stopped line, with no truncation marker, and `metadata["truncated"]` is `False` | P1 | `test_bash_tool_head_tail.py::test_timeout_after_exactly_the_cap_shows_every_byte_then_the_stopped_line_and_no_marker` |
| AC-6.5 | `BASH_MAX_OUTPUT_BYTES` patched to 1,000 (as `test_bash_tool_process_bounds.py` does) and a command printing 5,000 bytes and exiting 0 | `BashTool` runs it | the output is the first 500 bytes, then `\n[output truncated: 4,000 bytes not shown]\n`, then the last 500 bytes, then `\nexit code: 0` | P1 | `test_bash_tool_head_tail.py::test_small_caps_split_into_a_head_and_a_tail_by_the_spec_formula` |
| AC-7.1 | an InfiniteMemory root run of several tool iterations that write a note, append an entry, and run bash | the run finishes | every root call's `system` string is identical, and none of them contains `max_iterations:` | P0 | `test_infinite_memory_stable_prefix.py::test_one_root_run_keeps_one_system_string_and_one_tool_list_while_children_keep_their_block` |
| AC-7.2 | the same run | after the iteration that wrote `notes/new.md` | the next call's messages end with one user message holding the `map_update` text, the line `- notes/new.md ({n} tokens): {description}`, and `- max_iterations: {i}/500` | P0 | `test_infinite_memory_stable_prefix.py::test_each_tool_iteration_appends_one_status_message_with_the_changed_map_lines_and_the_loop_block` |
| AC-7.3 | a generator or verifier | it runs | its system still holds the loop-settings block and its map drawn at build, as on `main` | P1 | `test_infinite_memory_stable_prefix.py::test_one_root_run_keeps_one_system_string_and_one_tool_list_while_children_keep_their_block` |
| AC-7.4 | a root run whose tool iteration writes so many files that the map header and their change lines exceed `INFINITE_MAP_MAX_TOKENS` | the next call runs | its status message's header and change lines together are at most `INFINITE_MAP_MAX_TOKENS` tokens (TokenEstimate), the last change line is `INFINITE_MORE_FILES` with the number of change lines left out, and the report after it does not repeat the left-out lines | P0 | `test_infinite_memory_stable_prefix.py::test_a_report_over_the_map_cap_is_cut_by_the_maps_rule_and_its_left_out_lines_are_never_repeated` |
| AC-7.5 | a root run whose tool iteration changes nothing in the workspace (a developer tool that only returns text) | the next call runs | its last message is a user message whose content is exactly the loop-settings block rendered with the live counters (ending `- max_iterations: {i}/500`), with no `map_update` text and no map header | P0 | `test_infinite_memory_stable_prefix.py::test_each_tool_iteration_appends_one_status_message_with_the_changed_map_lines_and_the_loop_block` |
| AC-8.1 | a workspace with entry `#7 fact: Zeta lists Enterprise at 999 USD` | an agent calls `search_memory` with `enterprise zeta` | the first hit line starts with `#7 fact: `, and the last line states the shown and total counts | P0 | `test_infinite_memory_search.py::test_an_entry_hit_comes_first_as_id_and_kind_and_the_last_line_counts_shown_and_total` |
| AC-8.2 | any workspace | the query is `price:59 "x" NEAR(a b) -c *` | the tool returns a normal result (hits or zero), never an FTS5 syntax error | P0 | `test_infinite_memory_search.py::test_fts5_syntax_in_a_query_is_searched_as_text_and_never_raises` |
| AC-8.3 | a note written by `bash` after the previous search | `search_memory` runs again | the new note's lines are searchable | P0 | `test_infinite_memory_search.py::test_a_note_bash_writes_after_a_search_is_found_by_the_next_search` |
| AC-8.4 | an interpreter whose `sqlite3` lacks FTS5 (simulated at the helper seam) | `search_memory` runs | it returns an error result with `metadata["error"] == "fts5_unavailable"` naming FTS5, and the agent and the other tools work | P0 | `test_infinite_memory_search.py::test_without_fts5_the_tool_returns_fts5_unavailable_naming_fts5_and_the_version`<br>`test_infinite_memory_search.py::test_without_fts5_the_agent_still_runs_and_grep_still_works` |
| AC-8.5 | 30 matching lines | `search_memory` runs | 10 hit lines plus the total line, with each snippet at most 12 tokens | P1 | `test_infinite_memory_search.py::test_at_most_ten_hits_are_shown_with_snippets_of_at_most_twelve_tokens` |
| AC-8.6 | the AC-8.1 workspace | the query is `enterprise pricing zeta` ("pricing" stems to "price", which no row holds) | the result has no hit line, only the total line with 0 shown of 0 matched | P1 | `test_infinite_memory_search.py::test_a_word_no_row_holds_gives_only_the_total_line_with_zero_of_zero` |
| AC-8.7 | an InfiniteMemoryAgent whose root, one generator, and its verifier each call `search_memory` in one run | the run finishes | `FullTextIndex` was constructed exactly once for the workspace (counted at the class), and every call's result reflects the disk at call time | P1 | `test_infinite_memory_search.py::test_one_index_serves_the_whole_tree_and_every_search_sees_the_disk_at_call_time` |
| AC-9.1 | one `AnthropicProvider` and a request with tools, a system, and history | `_create_payload` runs twice with the same tools and system | the first body has `system` as a string and no `cache_control` anywhere. The second has `system` as a one-block list with `cache_control: {"type": "ephemeral"}`, and marks on the last block of the last message and on the last message before the newest assistant turn | P0 | `test_anthropic_cache_breakpoints.py::test_a_repeat_marks_the_system_the_last_message_and_the_message_before_the_newest_assistant` |
| AC-9.2 | an agent whose system string changes on every call | it makes several calls | no body carries `cache_control` | P0 | `test_anthropic_cache_breakpoints.py::test_an_agent_whose_system_changes_every_call_sends_no_marks`<br>`test_anthropic_cache_breakpoints.py::test_adapter_level_a_system_that_changes_every_call_is_never_marked` |
| AC-9.3 | a request whose `extra_body` sets a top-level `cache_control`, or whose messages already carry one | `_create_payload` runs twice | the adapter adds no marks | P1 | `test_anthropic_cache_breakpoints.py::test_caller_supplied_cache_control_anywhere_stops_all_marking` |
| AC-9.4 | a repeat body | it is checked against the gateway rules (backend `_require_short_cache`: object or null, `ttl` absent or `"5m"`) and the SDK `EMITTED_KEYS` | every mark passes and no top-level key is new | P0 | `test_anthropic_cache_breakpoints.py::test_a_repeat_body_passes_the_gateway_rule_and_adds_no_top_level_key`<br>`test_anthropic_cache_breakpoints.py::test_a_gateway_run_forwards_the_marked_repeat_body` |
| AC-9.5 | the caller's `config.messages` | two payloads are built | the caller's message dicts and content lists hold no `cache_control` | P0 | `test_anthropic_cache_breakpoints.py::test_the_callers_messages_are_never_marked_and_marks_never_pile_up` |
| AC-10.1 | default settings | the root and a pair run | no agent is offered `recall`, and every agent is offered `grep`, `read_lines`, and `search_memory` | P0 | `test_infinite_memory_recall.py::test_each_agent_is_offered_its_modes_tools[direct]` |
| AC-10.2 | `recall_mode=DELEGATED` | the root and a pair run | the root and the generator are offered `recall` and not `grep`, and the verifier is offered `grep` and not `recall` | P0 | `test_infinite_memory_recall.py::test_each_agent_is_offered_its_modes_tools[delegated]` |
| AC-10.3 | DELEGATED, and a retriever whose reply cites `FOUND #7 (price)` and `FOUND notes/p.md:3-5 (table)` | the root calls `recall` | the card holds entry #7's text from `entries.jsonl` and lines 3–5 of `notes/p.md` from disk, and no text the retriever wrote beyond the not-found reasons | P0 | `test_infinite_memory_recall.py::test_a_recall_card_holds_only_text_copied_from_disk_under_its_code_built_labels` |
| AC-10.4 | a retriever reply citing a superseded entry, a range in `superseded.jsonl`, a range in `entries.jsonl`, a range of a journal under `.runs/`, a path outside the workspace, a range longer than the window, `FOUND notes/p.md:5-3 (x)`, and `FOUND #0 (x)`, plus one valid citation | `recall` runs | the recall succeeds; each invalid citation is listed as rejected with its reason and none is transcribed, and the valid one is transcribed | P0 | `test_infinite_memory_recall.py::test_every_invalid_citation_is_listed_as_rejected_and_only_the_valid_one_is_transcribed` |
| AC-10.5 | an agent that has used its recall quota | it calls `recall` again | an error result names the quota, and no agent starts | P1 | `test_infinite_memory_recall.py::test_a_recall_refused_for_validation_costs_nothing_and_the_quota_counts_failed_attempts` |
| AC-10.6 | DIRECT | `InfiniteMemoryToolRegistry.tool_names(preset, role)` is called for every pair | the names equal `main` | P0 | `test_infinite_memory_recall.py::test_the_registry_names_main_tools_in_direct_and_adds_recall_and_withholds_grep_in_delegated` |
| AC-10.7 | DELEGATED, and a retriever reply with one valid 200-line range citation whose text alone exceeds `INFINITE_RECALL_CARD_MAX_TOKENS`, plus one NOT FOUND line | `recall` runs | the card is at most `INFINITE_RECALL_CARD_MAX_TOKENS` tokens, shows the question, the not-found line, and the searches line in full, cuts the found block to an exact prefix of the text on disk, and ends with `INFINITE_TRUNCATION_MARKER` | P0 | `test_infinite_memory_recall.py::test_a_card_over_its_cap_cuts_the_found_text_to_a_prefix_of_the_disk_and_keeps_the_other_sections` |
| AC-10.8 | DELEGATED, and a recall with `terms` `("zeta", "acme price")` over a workspace where each term matches a different note line and no line holds all three words | `recall` runs | the retriever's first message holds two `search_memory` results, in that order, each with its hit | P1 | `test_infinite_memory_recall.py::test_terms_are_searched_one_by_one_in_order_before_the_retriever_starts` |

### 6.3 Edge cases and failure modes

| ID | Trigger (input + state) | System behavior | User sees | Guarded by (INV-/D-) |
|---|---|---|---|---|
| EC-1.1 | `read_lines` on a 40,000-character note with no `end`, on InfiniteMemory. Without the window, 10,037 tokens enter history in one call. | It returns 200 lines and the footer. | The model reads on with `start=201` if it needs more. | INV-1.2, D-1 |
| EC-1.2 | One line is longer than the 200,000-character loop cap. The window counts lines, not characters. | The loop's result cap still cuts it, as on `main`. | The loop's existing truncation. | accepted limitation; `INFINITE_TOOL_RESULT_MAX_CHARS` |
| EC-1.3 | `max_read_lines=True` or `2.5` would quietly set a limit of 1 or 2. | `LineLimit` refuses it and names the field. | `ConfigurationError` at construction. | INV-1.5 |
| EC-1.4 | `start=0` or `end<start` with the window on. | Same `ToolExecutionError` text as `main`. | The error result. | INV-1.6 |
| EC-2.1 | Masking scoped to every tool, as `main`'s unscoped window would be, would replace `launch_subagent` cards. Those cards exist only in history, because the journal stores only the key. | The scope limits masking to `grep`, `read_lines`, and `search_memory`. | The cards stay whole. | INV-2.2, D-2 |
| EC-2.2 | The agent re-runs a masked grep with the same arguments while `DeduplicateToolCallsCompaction` is present. Dedup keeps the first copy, so the agent would loop. | InfiniteMemory never installs dedup. | The re-run output is visible. | NG-5, INV-0.4 |
| EC-2.3 | Each newly masked output changes a message in the middle of the view, so the cached suffix after it misses the cache once. | Accepted cost: one cache write of the suffix after the masked message, per masking event. | A higher `cache_creation_input_tokens` on that call. | accepted limitation (Q-7) |
| EC-2.4 | A tool result whose tool name cannot be read from metadata (`_message_tool_name` returns None). | It is out of every non-empty scope, so it is never masked. | Unchanged output. | INV-2.2 |
| EC-3.1 | A regex pattern `(?P<Name>…)` has an uppercase letter in a group name, which smart case counts. | The search is case-sensitive. | Matches as written. | accepted limitation (ripgrep behaves the same) |
| EC-3.2 | A non-ASCII uppercase letter such as `É`. | `str.isupper()` counts it, so the search is case-sensitive. | Exact-case matches. | INV-3.2 |
| EC-4.1 | The steady state under exact-cap trimming drops the oldest group on almost every call, so every call misses the history cache. | Hysteresis moves the cut once per 25,000 tokens of growth. | Fewer cache writes. | INV-4.4, D-5 |
| EC-4.2 | The newest single group is larger than the budget B. | With hysteresis, every non-system group is dropped, because the kept part must be a contiguous suffix ≤ B. On `main` the trim also drops that group but keeps older small ones. | The task, the rules, and the map remain, as the root prompt already states. A result over half the cap cannot happen with `INFINITE_TOOL_RESULT_MAX_CHARS`, and a status message is capped at `INFINITE_MAP_MAX_TOKENS` (EC-7.8). | INV-4.2, accepted |
| EC-4.3 | Masking lowers N: a new `grep`/`read_lines`/`search_memory` output that is smaller than the output it pushes past the newest 3 lowers N by about the size difference. When N − B sat less than that drop above a multiple of S, `ceil((N−B)/S)` falls by one. | The cut moves back by up to S tokens: older groups reappear and the view grows toward B. Once appends carry N back over the multiple, the cut moves forward again. That is two full-history cache writes per dip, and the chance per masking event is about net drop / S (about 10% for a 2,500-token drop). | Two extra cache writes per dip; the stated cost of the stateless cut. | accepted limitation (D-5; a monotone cut is Q-11) |
| EC-4.4 | A test patches `INFINITE_HISTORY_MAX_TOKENS` to 250 while the low watermark stays 65,000. | L ≥ M, so the trim behaves as on `main`. | `test_infinite_memory_context.py:46` keeps passing. | INV-4.1, D-5 |
| EC-4.5 | A root whose system groups alone exceed `max_tokens`, so B < 0. | Every non-system group is dropped, as on `main`. | Only system groups remain. | INV-4.2 |
| EC-5.1 | A `passed` pair's files are no longer listed on its card. | The summary names its output paths (the generator prompt asks for "the paths holding the detail"), and `pair_finished` keeps the list. | The root reads the summary. | INV-5.1, INV-5.4, accepted |
| EC-5.2 | A `partial`/`passed` card. | The full card is rendered (status is not `done`). | Review and lists visible. | INV-5.1/5.2 |
| EC-6.1 | A UTF-8 character is split at the head/tail edge. | Each part is decoded with `errors="replace"`, so a replacement character appears at the edge. | One `�` at the cut. | accepted limitation |
| EC-6.2 | A test monkeypatches `BASH_MAX_OUTPUT_BYTES` to a small cap below `BASH_TAIL_OUTPUT_BYTES` (`test_bash_tool_process_bounds.py:244` uses 1,000). | T = cap // 2 and H = cap − T, so the output still keeps a head and a tail. | The first and the last bytes, with the marker between them. | INV-6.2, INV-6.5 |
| EC-6.3 | A timeout after more than H + T bytes were printed, or after exactly the cap was printed. | More than H + T: the head, the marker with the count left out so far, the tail, then the stopped line. H + T or fewer: every byte and the stopped line, with no marker. | The end of the output before the stop, and a marker only when bytes were left out. | INV-6.4 |
| EC-6.4 | `VerifyCommandMiddleware` relays the bash output into finish feedback. | The feedback now carries the head, the marker, and the tail. | Test failures at the end of a verify run are visible. | INV-6.2 (deliberate SDK-wide change) |
| EC-7.1 | Without the fix, a re-upserted map and `max_iterations: n/500` change the system string on every call, so no history is ever read from cache. | The map is drawn once and the counter moves into the status message. | Cache reads from the third call on. | INV-7.1, D-9 |
| EC-7.2 | `bash` writes a workspace file. | It appears as a changed line in the next status message. | `- path (n tokens): (no description)`. | INV-7.3 |
| EC-7.3 | A refused finish or a contract rejection takes the loop's `continue` path, which skips `_after_tool_iteration`. | No status message is appended for that iteration. The next normal iteration's report covers all changes since the last one. | The counter is updated one iteration later. | INV-7.4, accepted |
| EC-7.4 | The root's first call has no status message yet. | The root sees no loop budgets until its first tool iteration finishes (usage 0 at that point). | Budgets appear from the second call on. | accepted (D-9) |
| EC-7.5 | Old status messages are trimmed away, possibly including the last one that carried a map header. | Totals change only when the workspace does, so the newest status message with a header holds the current totals. Once that one is trimmed, the root sees the run-start map's totals until the next change. Earlier change lines may be lost. | The root greps or searches for files it needs. | accepted |
| EC-7.6 | Generators, verifiers, and the retriever keep the per-call loop counter in their system string. | Their requests never reuse a cached history (and get no Anthropic marks, EC-9.4). Once past the 90K cap they keep 65K–90K tokens of history instead of about 90K: they trade up to S tokens of history mid-task for fewer billed tokens per call, with no cache gain. | Lower cost per call than on `main`, and up to 25,000 tokens less history in a long child task. | NG-1, INV-4.5, Q-2 |
| EC-7.7 | A file passes the map cap of 8,000 tokens of lines. | The status diff uses the uncapped snapshot, so a file beyond the map cap is still reported when it changes, within the status cap of EC-7.8. | The change line. | INV-7.4, D-10 |
| EC-7.8 | One iteration changes many files: a 20-pair batch whose 40 agents create up to 400 files, or one root `bash` loop that writes 1,500 notes. Uncapped, the next status message would be one indivisible group of tens of thousands of tokens, re-sent until trimmed, and over B it would make the trim drop every other group (EC-4.2). | The change lines are cut by the map's rule at `INFINITE_MAP_MAX_TOKENS` and end with `INFINITE_MORE_FILES`. The report baseline still advances. | `… and n more files`; the root finds the rest with `search_memory` or `grep`. | INV-7.3, INV-7.4 |
| EC-8.1 | Without quoting, the query `price:59` makes FTS5 read `price` as a column filter, which raises a syntax error. | Every word is quoted. | Normal results. | INV-8.2 |
| EC-8.2 | A query that is empty or whitespace only. | `ToolResult.error` asks for at least one word, and nothing is indexed. | The error. | FR-8.6 |
| EC-8.3 | A binary or huge file in the workspace, which would fill the index with noise rows. | Files over the grep byte cap and files with a NUL byte in their first 2,048 bytes are skipped, as grep skips them. Other files are decoded with `errors="replace"` and indexed line by line. | No hits from those files. | INV-8.5 |
| EC-8.4 | Parallel `search_memory` calls: the root and its pairs at once, two calls in one turn, or one agent object run from two threads. | One index per workspace. Each call refreshes and searches in a worker thread while holding the index's lock across both, so calls wait for each other, the connection allows cross-thread use, and the event loop keeps running the other agents. | Consistent results. | INV-8.9, D-11 |
| EC-8.5 | A file rewritten with the same size within one filesystem timestamp tick of the indexed version (about 2 s on FAT/exFAT, 1 s on many network shares, about 1–4 ms on ext4), as with a same-length numeric edit such as a `bash` `sed -i` that turns "49 USD" into "59 USD". | The fingerprint misses the change until a later write changes the size or lands on a later tick. | `search_memory` can show the old text for that file until then. | accepted (mtime_ns and size, as decided) |
| EC-8.6 | Linux CI Python built without FTS5. | INV-8.7 applies. Tests depending on FTS5 would fail there. | The CI result. | A-1 |
| EC-8.7 | A word with only punctuation, for example `...` or `--`. Quoted, it would be an empty phrase whose FTS5 behavior the code would rely on. | The word is dropped before quoting. A query made only of such words returns zero hits without a MATCH. | The total line with 0 of 0. | INV-8.2 |
| EC-9.1 | A one-shot call, for example a utility agent called once. | The digest is new, so no marks are sent and there is no 1.25× write. | Cost unchanged. | INV-9.2, D-13 (Q-ORCH-2) |
| EC-9.2 | Repeated one-shot calls with one stable system and no history. | The second call marks the system only (a 0.25× premium on the system tokens once). Later calls read it at 0.1×. | Cheaper repeats. | INV-9.3 |
| EC-9.3 | A system shorter than the model's minimum cacheable length (512–4,096 tokens). | Anthropic ignores the mark and charges no write (vendor documentation, A-7). | Nothing. | A-7 |
| EC-9.4 | An agent whose system string changes on every call: a loop limit set, InfiniteMemory children, or Jev subagents. Marks on such requests would cost 1.25× on every call and never be read. | The digest never repeats, so no marks are sent. | Cost unchanged from `main`. | INV-9.2, D-13 |
| EC-9.5 | Caller messages already marked. Adding three more marks could pass Anthropic's limit of four, which returns a 400. | The adapter adds none. | The caller's own caching. | INV-9.4 |
| EC-9.6 | Mutating `config.messages` in place would make marks pile up across calls, giving more than four breakpoints and a 400. | Only payload copies are marked. | Nothing. | INV-9.5 |
| EC-9.7 | More than 20 blocks between the previous breakpoint and the newest one, for example a parallel tool turn. Anthropic's automatic lookback reaches about 20 blocks. | A second message breakpoint on the previous call's last message hits exactly. | Cache read. | INV-9.3 |
| EC-9.8 | The last block is a `thinking` block, which Anthropic does not allow to carry a mark. | The adapter marks the last markable block before it, or none. | Nothing. | INV-9.3 |
| EC-9.9 | Gateway (AUTO mode). | Block-level marks without `ttl` are admitted (backend `provider/generative_models/client.py:260-278`), and `plan()` forwards the body unchanged (`:176`; `send()` posts `plan.wire`, `:195`). | Cached gateway runs. | INV-9.1, A-6 |
| EC-9.10 | A message that gets a mark has string content: the task prompt, review feedback, a status message, or a plain chat turn. On a repeat request the task is often the message right before the newest assistant turn. | It goes out as one text block carrying the mark, in a new message dict. Unmarked messages keep their string form. A test that compares such a message on a repeat body with a string sees the block form instead; exactly one existing test does (§13, A-5). | The same answers, and cache hits on string-only histories. | INV-9.3, INV-9.5 |
| EC-10.1 | A retriever reply with no citation lines (prose only). | The card lists `Found: -` and the retriever's not-found reasons, or `-`. | An empty card, with the quota counted. | INV-10.4 |
| EC-10.2 | A citation of a superseded entry (`#id`); a range in `superseded.jsonl`, `entries.jsonl`, `files.jsonl`, or anywhere under `.runs/`; a path such as `../secret`; or a range longer than the read window. | Rejected with a reason. Bookkeeping paths are refused by name (`INFINITE_BOOKKEEPING_NAMES`), and paths outside the workspace by `FileSystemPermissions.resolve_scoped_path`. | Rejected lines. | INV-10.5, T-2 |
| EC-10.3 | The retriever hits its iteration cap or raises a VidbyteSdkError, OSError, or ValueError. | Whatever citations its reply holds are used. On an error the tool returns an error result. The quota counts the attempt. | A partial card or an error. | INV-10.6/10.7 |
| EC-10.4 | `recall` under a tool timeout. | It is internal, so the loop's tool timeout does not cut it, as with `launch_subagent`. Its own iteration cap bounds it. | No timeout cut. | INV-10.9, D-14 |
| EC-10.5 | A developer tool named `recall` or `search_memory`. | Settings refuse it, because both names are reserved. | `ConfigurationError`. | FR-8.7, FR-10.9 |
| EC-10.6 | A retriever reply with so many NOT FOUND lines, rejected citations, or searches that those sections alone exceed the card cap. | The card is still cut at its end, so the found blocks are cut, and part of the sections before them may be too. | The marker at the end of the card. | INV-10.7, accepted |
| EC-10.7 | A retriever reply line that matches the FOUND grammar but holds numbers the citation record refuses (`FOUND notes/p.md:5-3`, `FOUND notes/p.md:0-4`, `FOUND #0`), written by mistake or steered by a hostile note (T-2). | `InfiniteRecallTool` catches the record's `ConfigurationError` for that line and lists it as `- reply line {n}: {reason}`, with the record's refusal text as the reason. The other citations are checked as usual. | A rejected line; the recall still returns its card. | INV-10.5, D-16 |

**Rollback of the user action:** Every change is code and configuration; nothing migrates data on disk.

- **Delegated recall:** a developer sets `recall_mode` back to `DIRECT`, the default.
- **Read window:** a developer who builds `FileSystemToolConfig` directly omits `max_read_lines` to read to EOF again.
- **Everything else:** reverting the PR restores `main` exactly. Workspaces written by this PR's agents use the same files and formats as on `main`, because no workspace file name or record shape changes.

## §7 Requirements

**Functional**
| ID | Requirement | Priority | Source (request.md / G-) |
|---|---|---|---|
| FR-0.1 | All ten §B.1 items ship in one PR against `main`, built on `0f2aeb48`, which contains #1084. | P0 | Prompt 4 "all of these in 1 pr", "make sure local main is up to date"; G-1–G-5 |
| FR-1.1 | `FileSystemToolConfig` gains `max_read_lines: int \| None = None` as its last field. `ReadLinesTool` applies the window, the footer, the metadata, and the description sentence of INV-1.2–1.7 when it is set. | P0 | §B.1 item 1, §B.2; G-3 |
| FR-1.2 | `OverwriteLineLimit` is generalized and renamed `LineLimit` and validates both `max_overwrite_lines` and `max_read_lines`. `CodingAgentSettings` uses it unchanged in behavior. | P0 | §B.2 pre-answered question |
| FR-1.3 | `InfiniteWorkspaceSettings.max_read_lines` (default `INFINITE_DEFAULT_MAX_READ_LINES` = 200) reaches every InfiniteMemory `read_lines`, including the retriever's. | P0 | §B.1 item 1, §C |
| FR-2.1 | `ToolOutputSlidingWindowCompaction` gains `tools`. The engine forwards `tools` and `placeholder`. `MessageHistoryCompactionMiddleware.tool_output_sliding_window` gains keyword-only `placeholder` and `tools`. | P0 | §B.1 item 2, §B.2 |
| FR-2.2 | Every InfiniteMemory agent holds a STRIP window with `keep_recent=INFINITE_MASK_KEEP_RECENT` (3), scoped to `INFINITE_MASKED_TOOL_NAMES` (`grep`, `read_lines`, `search_memory`), with the `masked_output` leaf as placeholder, placed first in its middleware tuple. | P0 | §B.1 item 2, §C; Prompt 2 "prune … deterministically" |
| FR-3.1 | `GrepTool` gains `smart_case` and `context_lines` constructor options with INV-3.1–3.3 behavior. Its spec gains one sentence per non-default option. | P0 | §B.1 item 3 |
| FR-3.2 | `InfiniteMemoryAgentTools` builds the workspace grep with `smart_case=True, context_lines=INFINITE_GREP_CONTEXT_LINES` (0). | P0 | §B.1 item 3, §C |
| FR-4.1 | `TrimWithProviderBoundariesCompaction` gains `low_watermark_tokens` with INV-4.1–4.4 behavior, forwarded by the engine and the `trim_with_provider_boundaries` builder. | P0 | §B.1 item 4, §C |
| FR-4.2 | Every InfiniteMemory agent's trim passes `low_watermark_tokens=INFINITE_HISTORY_LOW_WATERMARK_TOKENS` (65,000). | P0 | §B.1 item 4; Q-ORCH-4 |
| FR-5.1 | `InfinitePair.render` renders `done` plus `passed`/`fixed` cards compactly (INV-5.1–5.4), for fresh and replayed cards. | P0 | §B.1 item 5, §C |
| FR-6.1 | `BashTool` keeps a head and a tail of its output as in INV-6.1–6.6, with the new `BASH_TAIL_OUTPUT_BYTES = 25_000`. | P0 | §B.1 item 6 |
| FR-7.1 | `InfiniteMemoryRuntime` draws the map once per run, renders no loop-settings block into the root's system string, and appends the status message of INV-7.3/7.4 after each tool iteration. | P0 | §B.1 item 7; pipeline.md ruling (iteration counter) |
| FR-7.2 | `InfiniteWorkspace.map_snapshot()` returns an `InfiniteMapSnapshot` (header plus uncapped `(path, line)` pairs). `map_text()` renders from it with today's cap and text. | P0 | §B.1 item 7 |
| FR-8.1 | Every InfiniteMemory agent holds `search_memory` (`InfiniteSearchMemoryTool`, a code-search tool beside `GrepTool`), built by `InfiniteMemoryAgentTools.get_tools` after `read_lines` on the workspace's shared index (INV-8.9). | P0 | §B.1 item 8; request.md §C "Index in memory per workspace" |
| FR-8.2 | `search_memory` behaves as in INV-8.1–8.8, on `FullTextIndex` (stdlib `sqlite3`, FTS5, `tokenize='porter unicode61'`, `bm25()`, `snippet()`). | P0 | §B.1 item 8, §C |
| FR-8.3 | `FullTextIndex` lives in `vidbyte/lib/util/` and is exported from `vidbyte.lib.util`. Its records are in `vidbyte/lib/dataclasses/code_search.py`. | P0 | AGENTS.md principle 5, Placement Rules |
| FR-8.4 | `FullTextIndex()` opens nothing, so building a workspace never fails. Its first use creates the in-memory table, and a missing FTS5 raises `ConfigurationError` there, which the tool turns into the `fts5_unavailable` error result. | P0 | §C "fail clearly"; briefing |
| FR-8.5 | `search_memory`'s description and parameter description are literal text of 4–5 sentences each, with no examples. | P1 | field guide `model-facing-tool-contracts.md`; lint S025 |
| FR-8.6 | An empty or whitespace-only query returns `ToolResult.error` with `metadata["error"] == "invalid_argument"`. | P1 | INV-8.2 |
| FR-8.7 | `search_memory` joins `INFINITE_RESERVED_TOOL_NAMES`. | P0 | toolset header recipe |
| FR-8.8 | The role prompts and `map_header.md` name `search_memory` where they name `grep` as the memory search, in one short added clause each. | P1 | request.md §C constraint (prompt edits where an item needs them) |
| FR-9.1 | `AnthropicProvider._create_payload` adds the block-level, repeat-gated breakpoints of INV-9.1–9.7, for `run_text` and `stream_text` alike. | P0 | §B.1 item 9; pipeline.md ruling |
| FR-10.1 | `InfiniteRecallMode` (`DIRECT`, `DELEGATED`) is added to `vidbyte/lib/enums/infinite.py`, exported from `vidbyte.lib.enums` and `vidbyte`, and used as `InfiniteWorkspaceSettings.recall_mode` (default `DIRECT`, text accepted). | P0 | §C, Q-ORCH-1 |
| FR-10.2 | `InfiniteMemoryToolRegistry.tool_names` gains `recall_mode` (default DIRECT) and names `recall` for ROOT and GENERATOR under DELEGATED. A new `withheld_tool_names(recall_mode, role)` names `grep` for ROOT and GENERATOR under DELEGATED, and nothing otherwise. | P0 | §C design ("root and generators get recall and lose grep") |
| FR-10.3 | `InfiniteRecallTool` validates an `InfiniteRecallRequest`, enforces the quota, pre-runs `search_memory` over `terms`, runs a fresh retriever `BaseAgent`, parses `FOUND`/`NOT FOUND` lines into `InfiniteRecallCitation`s, checks them, transcribes accepted ones from disk, and returns the capped card. | P0 | §C recall design |
| FR-10.4 | The root and generators get `recall` and lose `grep` under DELEGATED, through the registry, at the two wiring sites (the root's run setup and the pair's agent builder). | P0 | §C |
| FR-10.5 | The retriever's system prompt is the developer's `system_prompt` plus the `retriever_system_prompt` leaf. It holds the map drawn at its start, the masking and trim middleware, and a loop of `INFINITE_RECALL_MAX_ITERATIONS`. | P0 | §C ("small turn cap (~8)") |
| FR-10.6 | `recall` adds no run event and no journal record. | P0 | NG-6 |
| FR-10.7 | Ten new prompt leaves are registered in `infinite_memory.json` and `Prompt`: `masked_output`, `map_update`, `recall_tool_description`, `recall_question_description`, `recall_purpose_description`, `recall_known_description`, `recall_terms_description`, `retriever_system_prompt`, `retriever_task_prompt`, `recall_card`. | P0 | prompt-families field guide; memory.py header recipe |
| FR-10.8 | The root and generator prompts say that, when they hold `recall`, they should use it for questions that would take several searches. They state no number. | P1 | request.md §C constraint |
| FR-10.9 | `recall` joins `INFINITE_RUN_BOUND_TOOL_NAMES` and so is reserved. | P0 | runtime clash check recipe |

**Non-functional**
| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-0.1 | "Very small changes" (Prompt 2): the design stays within the §8.4 budget. | P0 | 4 new `.py` files (D-18) and 10 new prompt leaves, no new dependency |
| NFR-0.2 | Every module listed in `BUDGET_MODULES` stays at or under 400 lines after its header; the list gains `vidbyte/agents/infinite/recall.py`, so it holds 13 modules. `vidbyte/agents/infinite/` has at most 9 `.py` files: its 8 plus `recall.py` (D-18). | P0 | `test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget` (`:471-479` at base), deliberately changed (§13) |
| NFR-0.3 | No `lint/baseline.json` count rises. Any count that falls is ratcheted down with `--update-baseline`. | P0 | `python lint/run.py` exit 0 |
| NFR-0.4 | Every file this PR creates or edits keeps under 1,000 lines. `vidbyte/middleware/compaction/strategies.py` drops from 1,020 lines to below 1,000. | P0 | AGENTS.md principle 3 |
| NFR-0.5 | "Drastic effects" (Prompt 2), checked with real keys after merge rather than as a gate: in an Anthropic root run of at least 5 calls, every call from the third on reports `cache_read_input_tokens` of at least the token count of the root's tool schemas plus system string. | P2 | real-key trace (§12.5) |
| NFR-1.1 | A `read_lines` result on InfiniteMemory is at most 200 lines plus one footer line. | P0 | INV-1.2 |
| NFR-2.1 | The masking placeholder is at most 60 tokens (TokenEstimate), against an average grep output of about 3,000 tokens. | P1 | leaf length |
| NFR-3.1 | A workspace grep with the defaults returns 2 lines per hit (location and line). | P1 | INV-3.3 |
| NFR-4.1 | For the bare trim strategy (nothing upstream changes earlier messages), at steady state with appended small groups, the trimmed history's first message changes at most once per 25,000 tokens of growth. With InfiniteMemory's masking upstream, each masking dip adds two moves (EC-4.3, AC-4.5). | P0 | INV-4.4; AC-4.2 |
| NFR-5.1 | A batch of 20 passed cards with summaries at the 800-token cap takes at most about 17,000 tokens, against about 64,000 on `main`. | P1 | INV-5.1 |
| NFR-6.1 | Bash memory stays within today's bound test (`PEAK_TRACED_BYTES` in `test_bash_tool_contract.py:29`) for a 20 MB output. | P0 | INV-6.3 |
| NFR-7.1 | Across a root run, `system` is byte-identical on every call (0 differing calls). | P0 | INV-7.1 |
| NFR-7.2 | The root's per-iteration status overhead is bounded. With the default loop, one status message is appended on every tool iteration. With no workspace change it is the loop-settings block alone: 33 tokens with the default loop, at most 40 (a loop that also sets `max_tokens` and `max_tool_calls` adds about 15). With changes, its header and change lines are at most `INFINITE_MAP_MAX_TOKENS` (8,000) tokens, plus the leaf text and the block. Status messages are ordinary history: masking never touches them (masking them is Q-12) and the trim bounds them. | P1 | INV-7.3; TokenEstimate of a no-change status message ≤ 40 with the default loop |
| NFR-8.1 | At the default workspace caps on the dev machine, a `search_memory` call with the index already built returns in under 50 ms of tool time. The first call, which builds the index, returns in under 2 s. Measured: 0.1 ms query, 125 ms build (request.md §C). | P1 | timing in a test or benchmark |
| NFR-8.2 | A `search_memory` result with 10 hits is at most 600 tokens (TokenEstimate). Measured: 284 tokens for the gold set. | P1 | INV-8.3, INV-8.6 |
| NFR-8.3 | Accuracy: on the request's measured setup (12 gold facts at the workspace cap), `search_memory` with lowercase queries finds at least as many gold facts as main's grep with the same words. Measured: 12/12 against 0–1/12. | P2 | real-key or seeded benchmark, not a gate |
| NFR-9.1 | No request from an agent whose tools-and-system digest never repeats carries `cache_control` (0 extra cost). | P0 | INV-9.2 |
| NFR-10.1 | A recall card is at most 1,500 tokens (TokenEstimate), the marker included. | P0 | INV-10.7 |
| NFR-10.2 | The retriever runs at most 8 iterations. | P0 | INV-10.7 |
| NFR-10.3 | "Returns a handoff when it actually finds this information": transcribed text in a card equals the text on disk at the cited place, as `read_lines` and `InfiniteWorkspace.entries` read it, never a paraphrase. A found block cut by the card cap is an exact prefix of that text. | P0 | INV-10.4; Prompt 1 weighted words |

---

## Part C — Design

## §8 Architecture and decisions

The design adds options with no-change defaults to five shared SDK pieces: the read tool's config, the per-tool output window, the provider-boundary trim, the code-search grep, and the bash tool's output buffer. It adds one canonical full-text helper to the bottom layer, and repeat-gated cache marks to the Anthropic adapter. InfiniteMemoryAgent then turns the options on. Its runtime moves the per-call changes out of the root's system string, and it gains two tools, `search_memory` (every agent) and `recall` (opt-in).

### 8.1 Decisions

| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | The read window is a `FileSystemToolConfig.max_read_lines` field read by `ReadLinesTool`. It is validated by the existing overwrite-cap record, renamed `LineLimit` and shared by both fields. The footer uses ASCII digits and a hyphen (`lines 1-200`), not the handoff's en dash. | It is the request's settled design (§C), and one validator serves both line caps (§B.2 "generalize it into one validator … Do not ask"). An ASCII footer tokenizes predictably and greps cleanly. | An InfiniteMemory-only wrapper tool around `read_lines`. Rejected: a second read tool with the same name, and the cap would not be reusable by other toolsets. | Another toolset needs a window counted in characters, not lines. |
| D-2 | Masking reuses the per-tool output window in STRIP mode with a new `tools` scope: keep the newest 3 outputs per scoped tool and replace older outputs with a leaf placeholder. It runs first in every InfiniteMemory agent's middleware tuple. | The scope keeps `launch_subagent` cards, `bash`, and the memory-tool replies whole (EC-2.1). Running before the trim means the trim measures the masked view, so fewer groups are dropped. | The existing clear-all-except-named-tools strategy. Rejected: it is an exclusion list, so every new tool would be masked by default, and it keeps no newest-n per tool. | A tool other than the three search/read tools produces large outputs that the agent re-derives cheaply. |
| D-3 | The two strategies this PR edits move unchanged into a new compaction module, `windows`, and gain their new options there. `strategies` keeps its other classes and the private helpers, which `windows` imports. | `strategies` is already 1,020 lines. AGENTS.md principle 3 says to split before adding more (NFR-0.4). Importing the private `_provider_groups` from `strategies` already has precedent in `context_compaction`. | Editing them in place. Fails NFR-0.4. | Never; the split is mechanical. |
| D-4 | Grep gains two constructor options, `smart_case` and `context_lines`, whose defaults keep today's behavior. InfiniteMemory sets smart case and 0 context lines. A call's own `context_lines` argument still wins. | Smart case decided 0 versus 1 gold hits, and context lines cost 8.4× (request.md §C, measured). Constructor options leave `CodingAgent` and the minimal paradigm unchanged (INV-R.1). | Changing GrepTool's defaults SDK-wide. Rejected: not discussed, and it changes the coding agent. | The coding agent's owners want the same defaults. |
| D-5 | Hysteresis is stateless and quantized. With S = max − low, the trim drops whole multiples of S tokens from the oldest non-system groups, as INV-4.2 states. The cut point therefore moves about once per S tokens of growth, with no stored state. | The strategy is rebuilt on every call (engine), so a pure function of the history needs no state carried through the engine and no reset between runs (Q-ORCH-4), and the kept part is always one contiguous suffix. | A remembered cut point kept per run in `run_state` under a private key class (which avoids a type-key collision with the masking middleware) and moved only forward. Not built: the engine's strategy API is stateless (options in, view and stats out), so the cut would need plumbing through the middleware, the engine, and the strategy, plus a reset rule between runs. Its only gain is removing the masking dips of EC-4.3 (optional Q-11). | Raw history stops being append-only, for example through a history-editing middleware upstream, or real-key traces show that EC-4.3's dips cost more cache writes than the quantized cut saves (Q-11). |
| D-6 | The watermark is the constant `INFINITE_HISTORY_LOW_WATERMARK_TOKENS = 65_000`. A watermark at or above the cap, or `None`, falls back to today's algorithm. | 65K is the conversation's figure (Q-ORCH-4). The fallback keeps `test_infinite_memory_context.py:46`, which patches the cap to 250, on today's behavior (EC-4.4) and avoids a construction error in any other caller. | Raising an error when low ≥ max. Rejected: it would break the existing patched-cap test and any caller that shrinks the cap. | — |
| D-7 | A card with status `done` and verdict `passed` or `fixed` renders as its finished-pair line plus its summary. Every other card renders in full, for fresh and replayed cards alike. The journal is unchanged. | A passed pair's review, dropped list, and files are noise to the parent. The summary already names the output paths. A batch of 20 shrinks from about 64K to about 17K tokens (NFR-5.1). It reuses `finished_lines`, so no new leaf is needed. | A new compact leaf template. Rejected: one more leaf for text `finished_lines` already renders. | Traces show roots re-reading passed pairs' files because the card no longer lists them. |
| D-8 | Bash keeps a 25,000-byte head and a rolling 25,000-byte tail inside today's 50,000-byte cap, with the omitted count between them. When nothing is omitted, head and tail are joined before decoding. | Test summaries and stack traces sit at the end of the output. The cap and the memory bound stay as they are (NFR-6.1). | Tail only. Rejected: it loses the command's opening errors and the header lines that explain the output. A shared lib helper is NG-11. | — |
| D-9 | The root's system string becomes stable. `InfiniteMemoryRuntime` draws the map once per run and overrides `_build_system_string` to drop the loop-settings block. After each tool iteration it appends one plain user message: the map header and the changed map lines followed by the loop-settings block rendered by the base method, or that block alone when nothing changed. | The pipeline.md ruling scopes the counter fix to the root. A user message after tool results already exists in the base runtime (review feedback, `runtime.py:670`). The map header carries totals against caps, which answers Q-ORCH-3. | The delta inside the newest tool result. Rejected: three provider shapes, and "newest" is ambiguous after a parallel batch. Also rejected: an end-of-conversation item, which renders as a trailing assistant message, an Anthropic prefill. | A provider rejects a user message right after tool results (A-2). |
| D-10 | The workspace exposes an uncapped snapshot (header plus `(path, line)` pairs), and `map_text` renders it with today's cap. The runtime diffs snapshots by line text. | One source for the map and the delta. A file beyond the map cap still reports its changes (EC-7.7). | Diffing rendered map text. Rejected: the cap would hide changes to files past it. | — |
| D-11 | The full-text index is a canonical lib helper, `FullTextIndex`, on stdlib `sqlite3`. It uses an in-memory FTS5 table with `tokenize='porter unicode61'`, `bm25()` ranking, and `snippet()`. Every query word is quoted and the words are joined with AND. One index exists per workspace (`InfiniteWorkspace.full_text`), shared by every agent's `search_memory` and every retriever's. Each call refreshes it per file from an `(mtime_ns, size)` fingerprint and searches it in a worker thread under the index's lock, as `SemanticSearchTool` indexes and ranks off the event loop (`vidbyte/tools/builtins/code_search/semantic.py:78-81`). The index opens nothing until its first use, where a missing FTS5 raises `ConfigurationError`. | This is the request's settled backend (§C), and the measured gains are 12/12 versus 0–1/12 at 284 tokens. In memory, the index adds no workspace file and no write path, so the caps and the journal are untouched. Quoting makes any query text safe (INV-8.2). One index per workspace is the request's wording ("Index in memory per workspace", request.md:112): a 20-pair batch builds it once instead of up to 41 times, and no search blocks the event loop the parallel pairs share. | An on-disk index in the workspace. Rejected: it counts toward the caps, goes stale after `bash` writes, and needs cross-process locking. Also rejected: the trigram tokenizer, which gives a larger index and no stemming. Also rejected: one index per tool instance, which rebuilds the same table for every agent and searches on the event loop. | Build time at the caps exceeds NFR-8.1. |
| D-12 | `search_memory` is `InfiniteSearchMemoryTool`, a `BaseCodeSearchTool` subclass in a new code-search module beside `GrepTool`. `InfiniteMemoryAgentTools` composes it. | REPO_MAP says the toolsets folder introduces no new tool capability, and code search lives in `builtins/code_search`. The base class already gives the ignore rules, the byte cap, the NUL-byte skip, and line numbering identical to grep (`read_text_lines`). | Defining it inside the toolset module. Rejected: against REPO_MAP, and it would spend about 120 of that budget module's lines. | — |
| D-13 | Anthropic caching uses block-level `{"type": "ephemeral"}` marks with no `ttl`. They go on the system, the last message, and the message before the newest assistant turn, and only when this adapter instance already sent the same tools and system. The adapter remembers digests in a bounded set. | The gateway refuses a top-level `cache_control` and admits block-level marks (backend `provider/generative_models/client.py:119`, `:260-278`). Repeat-gating means one-shot calls and agents whose system varies per call never pay the 1.25× write (Q-ORCH-2). The second breakpoint lets a long parallel turn still hit the previous call's breakpoint (EC-9.7). | Marking every request. Rejected: 1.25× on every one-shot call. Also rejected: marking whenever history is non-empty, which charges 1.25× on every call of an agent whose system changes per call, such as InfiniteMemory children, Jev subagents, and critics. | Anthropic or the gateway accepts top-level automatic caching (NG-7), or a caller needs caching on the first call. |
| D-14 | `recall` is `InfiniteRecallTool`. The memory module's builder table builds it, and the class lives in its own module, `recall.py` (D-18). It runs a fresh retriever `BaseAgent` built from the shared settings, with no role and no memory tools. It parses the retriever's `FOUND`/`NOT FOUND` lines, and the code copies the cited text from disk. | This is the request's settled design (§C). Building the retriever without a role keeps the registry invariant that every role holds `remember` and `write_note` (contract `:383-387`). The memory module's builder table is where the header recipe grants a new memory tool. | A new `InfiniteAgentRole.RETRIEVER` member. Rejected: the registry grants preset tools to every role, so the retriever would hold `remember`/`write_note`, or the tested invariant would break (Q-9). Also rejected: `AgentTool`, which forwards the whole conversation (request.md §C). | The user wants the retriever visible as a role in the journal or events (NG-6). |
| D-15 | The recall mode is the enum `InfiniteRecallMode` (`DIRECT` default, `DELEGATED`) on `InfiniteWorkspaceSettings`. The registry gains a `recall_mode` argument on `tool_names` and a new `withheld_tool_names`. | AGENTS.md says a closed set is an enum. The registry is the one table of which tools an agent holds. | A bool switch. Rejected: it is a closed set of two named modes, and C007 bool proofs would be needed. | A third mode appears. |
| D-16 | Citation parsing is a `parse` classmethod on the `InfiniteRecallCitation` record (precedent: `lib/dataclasses/prompts.py:42`). `parse` returns `None` for a line that is not a citation and lets the record's `ConfigurationError` propagate for a grammar-matching line with refused numbers; `InfiniteRecallTool` catches it per line and lists that line as rejected (EC-10.7). Ranges are copied through the agent's own windowed `read_lines` and entries through `InfiniteWorkspace.entries`. | The grammar belongs with the record it builds (the precedent), and keeping it there leaves `recall.py` (D-18) with only the tool's own steps, well inside its 400 lines. Reusing the read tool reuses its scoping, its window, and its line numbering, so a citation is checked by the same rules the retriever read with. | Parsing and file reading inside the tool's module. Rejected: they would repeat the record's validation and the read tool's scoping. (r3 also cited the memory module's 149 lines of headroom; D-18 moved the tool out of that module.) | — |
| D-17 | The Anthropic seen-digest set holds at most `ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT = 256` sha256 digests of the JSON of `[tools, system]` as sent, and is cleared when full. | It bounds memory for a long-lived adapter. A clear costs one unmarked call per live prefix. | An LRU cache. Rejected: more code for no measured need. | Traces show the clear cost matters. |
| D-18 | `InfiniteRecallTool` lives in a 9th package module, `vidbyte/agents/infinite/recall.py`, which holds only that tool and its private steps: pre-search, retriever, citation check, transcription, and card. `memory.py` keeps what it owns: the `settings` keyword, the `recalled` counter, and the `INFINITE_RECALL_TOOL_NAME: InfiniteRecallTool` builder entry, importing the class from `recall.py`. `recall.py` imports `InfiniteAgentMemory` only under `TYPE_CHECKING`, so at run time the import edge runs one way, memory to recall. The budget test moves from 8 to 9 package files, and `BUDGET_MODULES` gains `recall.py` (§13). | Measured in r4 with the budget test's own line count: `memory.py` has 251 lines after its header, so 149 lines of headroom. S2's bare reference `InfiniteRecallTool` in it already reaches 402 lines (about 450 at house style). No other package module can take the tool without breaking AGENTS.md principle 3 ("split a large feature into several small classes and files … rather than growing one large class"; "no two modules depend on each other in a cycle"). `launch.py` (32 lines free) and `workspace.py` (68) have no room. `runtime.py` (294), `agent.py` (289), `journal.py` (243), and `settings.py` (204) each own another subsystem. `tools/toolsets/infinite.py` is in the tools layer, which never imports `vidbyte.agents` (§12.2), while the retriever is a `BaseAgent`; REPO_MAP also says the toolsets add no capability. A006 skips `TYPE_CHECKING` edges (`lint/rules/a006_directed_dependency_graph.py:74`, `:138`), so the type-only import back is not a cycle. The 8-file count is a review aid pinned by the previous feature, not a user decision. | Fitting the tool into `memory.py` by thinning its narration. Rejected: that breaks AGENTS.md principle 2 and still leaves no room for fixes. Also rejected: `runtime.py` or `workspace.py`, which breaks principle 3. Also rejected: a module outside the package, such as `vidbyte/agents/infinite_recall.py`, which hides the 9th file and splits the feature's folder. | `recall.py` heads past 400 lines, or the owner wants the 8-file count kept. |

### 8.2 Patterns inherited
- **Options default to today** — every new SDK option defaults to main's behavior, so callers that do not set it see no change (INV-0.2). The repo already does this with `FileSystemToolConfig.max_overwrite_lines = None` (`vidbyte/lib/dataclasses/filesystem.py:75`).
- **Description sentence appended by `dataclasses.replace`** — a configured limit adds one sentence to a tool spec (`vidbyte/tools/filesystem/write_text.py:28-31`).
- **Validated frozen records with `__post_init__`** — `OverwriteLineLimit` (`vidbyte/lib/dataclasses/filesystem.py:46-63`) and `InfiniteTaskCard` (`vidbyte/lib/dataclasses/infinite.py:42`).
- **Policy as data in a registry, construction in the agents layer** — `InfiniteMemoryToolRegistry` (`vidbyte/lib/registries/infinite.py`).
- **Memory tool recipe** — one `BaseTool` subclass, one builder in `InfiniteAgentMemory.tools`, a name constant, a reserved name, and description leaves (`vidbyte/agents/infinite/memory.py:7` header). `recall` follows it, with its subclass in `recall.py` (D-18).
- **Internal tool spec for subagent launchers** — `metadata={"internal": True}` exempts the tool from the loop's timeout and result cap (`vidbyte/agents/infinite/launch.py:114`, `vidbyte/agents/runtime.py:1500`, `:1985`).
- **Specialized runtime hooks** — `_after_tool_iteration` may append to messages (`vidbyte/agents/runtime.py:925` docstring). `InfiniteMemoryRuntime._after_tool_iteration` (`vidbyte/agents/infinite/runtime.py:104`) and `JevRuntime` already use it.
- **Child agent built from shared settings** — `InfinitePair._agent` (`vidbyte/agents/infinite/launch.py:252-291`).
- **Capped text with a marker** — `TokenEstimate.cap(text, max_tokens, marker)` (`vidbyte/lib/util/text.py:104`), used for card fields (`launch.py:219`).
- **Code-search base** — `BaseCodeSearchTool.iter_files` / `read_text_lines` (`vidbyte/tools/builtins/code_search/base.py:73-120`).
- **Tool/provider-local operational constants as module globals read at call time** — `BASH_*` (`vidbyte/tools/builtins/bash.py:34-37`).

### 8.3 Smaller design rejected

The smallest design is the request's own first sketch: mask with the unscoped window, freeze the map with `primitive_frozen`, add a top-level `cache_control`, and leave the loop block alone. It fails on four counts:

- **Unscoped masking** replaces `launch_subagent` cards, which exist only in history (fails INV-2.2, EC-2.1).
- **`primitive_frozen`** makes the existing re-upsert raise (`vidbyte/context/manager.py:82-85`). And the system string still changes on every call, through `- max_iterations: n/500` (fails INV-7.1).
- **A top-level `cache_control`** is refused by the gateway, which InfiniteMemory's AUTO mode always uses (fails G-4, INV-9.1).
- **Without repeat-gating**, every agent whose system varies per call pays 1.25× on every call (fails NFR-9.1).

A second smaller design, which skips `search_memory` and keeps only grep, fails G-2 and FR-8.x. The request settled that FTS5 is in scope.

### 8.4 Complexity budget

| Item | Count | Justification for each |
|---|---|---|
| New files | 14 | Four `.py` modules: (1) the compaction `windows` module (D-3, forced by NFR-0.4); (2) the `fulltext` lib helper (D-11, AGENTS.md principle 5); (3) the `search_memory` code-search module (D-12, REPO_MAP placement); (4) the `recall` module in `vidbyte/agents/infinite/` (D-18, forced by the 400-line budget and AGENTS.md principle 3). The package goes from 8 to 9 `.py` files, a deliberate budget change (§13). Ten prompt leaves (FR-10.7): one per new model-facing text. |
| New classes/modules | 10 classes, 4 modules | `FullTextIndex`, `FullTextRow`, `FullTextHit`, `FullTextMatches` (helper and its records); `InfiniteSearchMemoryTool`; `InfiniteRecallTool`, `InfiniteRecallRequest`, `InfiniteRecallCitation` (recall and its validated input and citation); `InfiniteMapSnapshot` (D-10); `InfiniteRecallMode` (D-15). `LineLimit` is a rename, not a new class. |
| New dependencies | 0 | `sqlite3` and `hashlib` are stdlib. |
| New config keys | 3 settings fields + 4 constructor/builder options | Settings fields: `FileSystemToolConfig.max_read_lines`, `InfiniteWorkspaceSettings.max_read_lines`, `InfiniteWorkspaceSettings.recall_mode`. Options: `GrepTool(smart_case, context_lines)`, `ToolOutputSlidingWindowCompaction(tools)`, and `TrimWithProviderBoundariesCompaction(low_watermark_tokens)`. The window's existing `placeholder` option, which the engine already forwards, is newly exposed on the middleware builder. |
| New collections/tables | 1 in-memory FTS5 virtual table per `InfiniteWorkspace` object | Never persisted. It lives and dies with the workspace object and is shared by every agent in the tree (INV-8.9). |
| New public endpoints/commands | 0 commands; 1 public export; 2 model-facing tools | `InfiniteRecallMode` joins `vidbyte.__all__` and the public API contract. `search_memory` (every InfiniteMemory agent) and `recall` (DELEGATED only). |

_The implementer may not exceed this budget without stopping and reporting BLOCKED._

### 8.5 Key interfaces

```python
# --- lib/dataclasses/filesystem (item 1) ---------------------------------
@dataclass(frozen=True, slots=True)
class LineLimit:                       # renamed from OverwriteLineLimit
    lines: int | None
    parameter: str                     # refusal: "{parameter} must be None or an int of at least 1."

@dataclass(frozen=True, slots=True)
class FileSystemToolConfig:
    root: Path | str
    allow_write: bool = False
    encoding: str = "utf-8"
    platform: Platform | str = Platform.LOCAL
    backend: BaseFileSystemBackend | None = None
    max_overwrite_lines: int | None = None
    max_read_lines: int | None = None  # NEW, last field; None = read to EOF as today

# ReadLinesTool.execute with max_read_lines=N, range longer than N:
#   output   = "\n".join(lines[start-1 : start-1+N]) + "\n" + f"[lines {start}-{start+N-1} of {total} shown; read on with start={start+N}]"
#   metadata = {"path", "start", "end", "truncated": bool, "total_lines": int, "next_start": int | None}

# --- middleware/compaction/windows (items 2, 4) ---------------------------
class ToolOutputSlidingWindowCompaction(BaseCompaction):
    def __init__(self, keep_recent: int = 2, mode: CompactionMode | str = CompactionMode.TRUNCATE_TOOL_RESULTS,
                 max_chars: int = 600, placeholder: str = "[older tool result cleared by compaction]",
                 head_chars: int = 400, tail_chars: int = 200, tools: Sequence[str] = ()) -> None: ...
        # tools=() -> every tool (today); otherwise only these tool names; a blank name -> ValueError

class TrimWithProviderBoundariesCompaction(BaseCompaction):
    def __init__(self, max_messages: int | None = None, max_tokens: int | None = None,
                 token_counter: TokenCounter | None = None, low_watermark_tokens: int | None = None) -> None: ...
        # negative low_watermark_tokens -> ValueError; None or >= max_tokens -> today's algorithm

class MessageHistoryCompactionMiddleware:
    @classmethod
    def trim_with_provider_boundaries(cls, max_messages: int | None = None, max_tokens: int | None = None,
                                      token_counter: TokenCounter | None = None, *,
                                      low_watermark_tokens: int | None = None) -> "MessageHistoryCompactionMiddleware": ...
    @classmethod
    def tool_output_sliding_window(cls, keep_recent: int = 2, window_mode: CompactionMode | str = CompactionMode.TRUNCATE_TOOL_RESULTS,
                                   max_chars: int = 600, *, placeholder: str = "[older tool result cleared by compaction]",
                                   tools: tuple[str, ...] = ()) -> "MessageHistoryCompactionMiddleware": ...

# --- tools/builtins/code_search (items 3, 8) ------------------------------
CODE_SEARCH_MAX_FILE_BYTES = 1_000_000          # base module; replaces the literal default
GREP_DEFAULT_CONTEXT_LINES = 2                  # grep module
GREP_MAX_CONTEXT_LINES = 5                      # grep module

class GrepTool(BaseCodeSearchTool):
    def __init__(self, root_dir: str | Path, *, ignore_patterns: Sequence[str] | None = None,
                 max_file_bytes: int = CODE_SEARCH_MAX_FILE_BYTES, smart_case: bool = False,
                 context_lines: int = GREP_DEFAULT_CONTEXT_LINES) -> None: ...
        # smart_case must be a bool and context_lines an int in 0..GREP_MAX_CONTEXT_LINES -> else ConfigurationError

class InfiniteSearchMemoryTool(BaseCodeSearchTool):   # name "search_memory", READ
    def __init__(self, workspace_root: str | Path, *, index: FullTextIndex, max_file_bytes: int) -> None: ...
    # execute: await asyncio.to_thread(<refresh by fingerprint + search, holding index.lock across both>)
    # parameters: query (string, required)
    # output: up to INFINITE_SEARCH_MAX_HITS lines "#{id} {kind}: {snippet}" | "{path}:{line}: {snippet}",
    #         then one line naming shown and total counts
    # errors: blank query -> metadata["error"] == "invalid_argument"; no FTS5 -> "fts5_unavailable"

# --- tools/builtins/bash (item 6) -----------------------------------------
BASH_TAIL_OUTPUT_BYTES = 25_000
class BashTool(BaseTool):
    async def _collect(self, process, head: bytearray, tail: bytearray, omitted: list[int]) -> int: ...
        # returns the exit code; omitted[0] counts the bytes left out so far, still readable after a timeout
        # H = BASH_MAX_OUTPUT_BYTES - T, T = min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES // 2)
    def _render(self, head: bytearray, tail: bytearray, omitted: int, exit_code: int) -> ToolResult: ...

# --- lib/util/fulltext (item 8) -------------------------------------------
FULLTEXT_SNIPPET_MAX_TOKENS = 64
class FullTextIndex:
    lock: threading.RLock                               # every method takes it; a caller holds it across refresh + search
    def __init__(self) -> None: ...                     # opens nothing; first use creates the table, ConfigurationError when FTS5 is missing
    def fingerprint(self, source: str) -> str | None: ...
    def replace(self, source: str, fingerprint: str, rows: Sequence[FullTextRow]) -> None: ...
    def retain(self, sources: Collection[str]) -> None: ...   # drop every other source
    def search(self, words: Sequence[str], *, limit: int, snippet_tokens: int) -> FullTextMatches: ...
    @staticmethod
    def match_expression(words: Sequence[str]) -> str: ...    # '"w1" "w2"' with inner '"' doubled

# lib/dataclasses/code_search
@dataclass(frozen=True, slots=True)
class FullTextRow:     source: str; label: str; text: str
@dataclass(frozen=True, slots=True)
class FullTextHit:     label: str; snippet: str
@dataclass(frozen=True, slots=True)
class FullTextMatches: hits: tuple[FullTextHit, ...]; total: int

# --- providers/anthropic (item 9) -----------------------------------------
ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT = 256
class AnthropicProvider:
    def _create_payload(self, config, prompt, system, metadata) -> dict[str, Any]: ...
        # ... existing attach steps ..., then self._attach_cache_breakpoints(payload, config)
    def _attach_cache_breakpoints(self, payload: dict[str, Any], config: TextModelConfig) -> None: ...
        # a marked string content goes out as [{"type": "text", "text": <string>, "cache_control": {"type": "ephemeral"}}]
        # in a new message dict; unmarked messages keep their string form (INV-9.3, EC-9.10)

# --- lib/enums/infinite, settings (item 10, item 1) -----------------------
class InfiniteRecallMode(str, Enum):
    DIRECT = "direct"
    DELEGATED = "delegated"

@dataclass(frozen=True, slots=True)
class InfiniteWorkspaceSettings:
    ...                                                   # existing fields unchanged, in order
    max_read_lines: int = INFINITE_DEFAULT_MAX_READ_LINES  # NEW (200)
    recall_mode: InfiniteRecallMode | str = InfiniteRecallMode.DIRECT  # NEW; text converted to the enum

# --- lib/registries/infinite ----------------------------------------------
class InfiniteMemoryToolRegistry:
    @classmethod
    def tool_names(cls, preset: InfiniteMemoryPreset, role: InfiniteAgentRole,
                   recall_mode: InfiniteRecallMode = InfiniteRecallMode.DIRECT) -> tuple[str, ...]: ...
    @classmethod
    def withheld_tool_names(cls, recall_mode: InfiniteRecallMode, role: InfiniteAgentRole) -> tuple[str, ...]: ...

# --- lib/dataclasses/infinite ---------------------------------------------
@dataclass(frozen=True, slots=True)
class InfiniteMapSnapshot:
    header: str
    lines: tuple[tuple[str, str], ...]     # (workspace-relative path, rendered map line), map order, uncapped

@dataclass(frozen=True, slots=True)
class InfiniteRecallRequest:
    question: str
    purpose: str
    known: str = ""
    terms: tuple[str, ...] = ()            # at most INFINITE_RECALL_MAX_TERMS, each non-blank

@dataclass(frozen=True, slots=True)
class InfiniteRecallCitation:
    why: str
    entry_id: int | None = None
    path: str | None = None
    start: int | None = None
    end: int | None = None                 # entry XOR (path, start, end); neither = NOT FOUND
    @classmethod
    def parse(cls, line: str) -> "InfiniteRecallCitation | None": ...
        # None for a line that is not a citation; ConfigurationError for a grammar-matching line with
        # refused numbers, which InfiniteRecallTool lists as rejected (EC-10.7)

# --- agents/infinite ------------------------------------------------------
class InfiniteWorkspace:
    full_text: FullTextIndex               # NEW, built in __init__ (opens nothing): the one index every agent's search_memory shares
    def map_snapshot(self) -> InfiniteMapSnapshot: ...
    def map_text(self) -> str: ...         # unchanged output, now rendered from map_snapshot() through fit_map_lines
    @staticmethod
    def fit_map_lines(header: str, lines: Sequence[str]) -> tuple[str, ...]: ...
        # today's map cut, lifted: the lines to show after header within INFINITE_MAP_MAX_TOKENS,
        # the last one INFINITE_MORE_FILES when cut; also caps the status message's change lines

class InfiniteAgentMemory:
    def __init__(self, workspace: InfiniteWorkspace, *, key: str, role: InfiniteAgentRole, run_id: str,
                 settings: InfiniteMemoryAgentSettings, staged: list[InfiniteStagedEntry] | None = None,
                 dropped: list[str] | None = None) -> None: ...   # NEW required keyword: settings; NEW counter: recalled

# vidbyte/agents/infinite/recall.py (new module, D-18); it imports InfiniteAgentMemory only under TYPE_CHECKING
class InfiniteRecallTool(BaseTool):        # name "recall", READ, metadata={"internal": True}
    def __init__(self, memory: InfiniteAgentMemory) -> None: ...
    # parameters: question (string, required), purpose (string, required),
    #             known (string, optional), terms (array of string, optional)

class InfiniteMemoryRuntime(AgentRuntime):
    def _build_system_string(self, context: BaseAgentContext, *, loop_settings_block: str = "") -> str: ...  # drops the block
    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None: ...

class InfiniteMemoryAgentTools(Tools):
    def __init__(self, root_dir: Path, workspace_root: Path, max_tokens: int, max_read_lines: int, index: FullTextIndex) -> None: ...
    @staticmethod
    def get_tools(root_dir: Path, workspace_root: Path, max_tokens: int, max_read_lines: int, index: FullTextIndex) -> tuple[BaseTool, ...]: ...
        # (bash, grep, read_lines, search_memory)

# --- lib/constants/infinite (new) -----------------------------------------
INFINITE_DEFAULT_MAX_READ_LINES = 200
INFINITE_MASK_KEEP_RECENT = 3
INFINITE_MASKED_TOOL_NAMES = ("grep", "read_lines", INFINITE_SEARCH_MEMORY_TOOL_NAME)
INFINITE_GREP_CONTEXT_LINES = 0
INFINITE_HISTORY_LOW_WATERMARK_TOKENS = 65_000
INFINITE_SEARCH_MEMORY_TOOL_NAME = "search_memory"     # joins INFINITE_RESERVED_TOOL_NAMES
INFINITE_SEARCH_MAX_HITS = 10
INFINITE_SEARCH_SNIPPET_TOKENS = 12
INFINITE_BOOKKEEPING_NAMES = (INFINITE_RUNS_DIRNAME, INFINITE_ENTRIES_FILE, INFINITE_SUPERSEDED_FILE, INFINITE_FILES_FILE)
                                                       # search_memory ignores them; recall refuses citations into them
INFINITE_MAP_REMOVED_LINE = "- {path}: removed"
INFINITE_RECALL_TOOL_NAME = "recall"                   # joins INFINITE_RUN_BOUND_TOOL_NAMES
INFINITE_RECALLS_PER_AGENT = 10
INFINITE_RECALL_MAX_TERMS = 8
INFINITE_RECALL_MAX_ITERATIONS = 8
INFINITE_RECALL_CARD_MAX_TOKENS = 1_500
INFINITE_RECALL_FOUND_ENTRY_PATTERN = ...              # FOUND #<id> (<why>)
INFINITE_RECALL_FOUND_RANGE_PATTERN = ...              # FOUND <path>:<start>-<end> (<why>)
INFINITE_RECALL_NOT_FOUND_PATTERN = ...                # NOT FOUND (<what was searched>)

# --- lib/enums/prompts (Prompt members, one per new leaf) -----------------
INFINITE_MEMORY_MASKED_OUTPUT, INFINITE_MEMORY_MAP_UPDATE, INFINITE_MEMORY_RECALL_TOOL_DESCRIPTION,
INFINITE_MEMORY_RECALL_QUESTION_DESCRIPTION, INFINITE_MEMORY_RECALL_PURPOSE_DESCRIPTION,
INFINITE_MEMORY_RECALL_KNOWN_DESCRIPTION, INFINITE_MEMORY_RECALL_TERMS_DESCRIPTION,
INFINITE_MEMORY_RETRIEVER_SYSTEM_PROMPT, INFINITE_MEMORY_RETRIEVER_TASK_PROMPT, INFINITE_MEMORY_RECALL_CARD
```

Prompt leaf placeholders (contract):

| Leaf | Placeholders |
|---|---|
| `masked_output.md` | none |
| `map_update.md` | `{header}`, `{changes}` |
| `retriever_task_prompt.md` | `{question}`, `{purpose}`, `{known}`, `{hits}` |
| `recall_card.md` | `{question}`, `{not_found}`, `{rejected}`, `{searches}`, `{found}`, in this order |
| `retriever_system_prompt.md` and the five `recall_*_description.md` leaves | none |

## §9 Data, API, configuration, migration

### 9.1 Data model

**No persisted entity changes.** `entries.jsonl`, `superseded.jsonl`, `files.jsonl`, notes, seeds, and the run journal keep their shapes and names. No journal record is added (FR-10.6).

**In-memory FTS5 table**, one per `FullTextIndex`, which is one per `InfiniteWorkspace` object and shared by every agent's `search_memory` (INV-8.9):

```sql
create virtual table rows using fts5(source UNINDEXED, label UNINDEXED, body, tokenize='porter unicode61');
-- query: select label, snippet(rows, 2, '', '', '…', :n) from rows where rows match :expr order by bm25(rows) limit :k
-- total: select count(*) from rows where rows match :expr
```

- **Natural key:** `(source, label)`. `source` is the workspace-relative POSIX path of the file the row came from.
- **Refresh:** `replace(source, …)` deletes a source's rows by the rowids recorded when they were inserted, then inserts the new rows and records their rowids. `retain` deletes dropped sources the same way. Fingerprints and rowids are kept beside the table, in memory, keyed by source. FTS5 builds no index on the UNINDEXED `source` column, so a delete by `source` would scan the whole table while holding the shared lock (review round 2 measured 4.8 ms per note and 26.3 ms for `entries.jsonl` at 33,760 rows, against 0.98 ms by rowid).
- **Volume:** at the default caps, about 33,700 rows (measured at 8,000 entries plus 80 notes). The table is bounded by the workspace caps, which `InfiniteWorkspace` enforces.
- **Lifecycle:** created on the first search from any agent, refreshed per call, and gone with the workspace object.

**New records** (all frozen and slotted, validated in `__post_init__`):

| Record | Fields and validation |
|---|---|
| `FullTextRow` | `source`, `label`, and `text` are `str`. `source` and `label` must be non-blank. |
| `FullTextHit` | `label` and `snippet` are `str`. |
| `FullTextMatches` | `hits` is a tuple of `FullTextHit`. `total` is an `int` ≥ `len(hits)`. |
| `InfiniteMapSnapshot` | `header` is a `str`. `lines` is a tuple of `(str, str)` pairs with unique paths. |
| `InfiniteRecallRequest` | `question` and `purpose` must be non-blank `str`. `known` is a `str`. `terms` is a tuple of non-blank `str`, at most `INFINITE_RECALL_MAX_TERMS` long. Any violation raises `ConfigurationError` naming the field. |
| `InfiniteRecallCitation` | `why` is a `str`. It holds exactly one of: `entry_id` (an `int` ≥ `INFINITE_FIRST_ENTRY_ID`); `path` with `start` and `end` (`1 <= start <= end`); or neither, meaning NOT FOUND. `parse` returns `None` for a line that is not a citation. A grammar-matching line with refused numbers raises `ConfigurationError`, which `InfiniteRecallTool` turns into a rejected line (EC-10.7). |

Every numeric range check in these records (`FullTextMatches.total`, `InfiniteRecallCitation.entry_id`, `start`, `end`) goes through `RecordFieldValidator.require_int`, which refuses `True`, non-`int` values, and values below the minimum, so lint C006 gains no finding (NFR-0.3).

### 9.2 API and interface surface

**Python API** (all additive; defaults keep today's behavior): the §8.5 signatures.

- **Breaking:** `InfiniteMemoryAgentTools(...)` and `get_tools(...)` gain a required `max_read_lines` and a required `index`, and `InfiniteAgentMemory` gains a required `settings`. Both are called only inside `vidbyte/agents/infinite/` (verified with `git grep`).
- **Renamed:** `OverwriteLineLimit` becomes `LineLimit`. It is not in `vidbyte.__all__`, `vidbyte/lib/dataclasses/__init__.py`, or `contracts/sdk-public-api.json`.

**Model-facing tool `search_memory`** (READ). Parameter: `query`, a string, required. The tool description and the parameter description are literal text of 4–5 sentences each, with no examples (FR-8.5). They say:

- the tool ranks memory entries and note lines by how well they match all the query's words;
- word forms are matched loosely and letter case is ignored;
- each hit names an entry id or a file and line to read next;
- the result says how many hits matched in total;
- `query` is plain words, not a pattern.

The descriptions state no number (INV-0.3).

Result shapes:

| Case | Status | Output | Metadata |
|---|---|---|---|
| Matches found | success | ``"\n".join(hit lines) + "\n" + total line`` | `{"hits": len(hits), "total": total}` |
| No match | success | the total line only | `{"hits": 0, "total": 0}` |
| Blank query | error | asks for at least one word | `{"error": "invalid_argument"}` |
| No FTS5 | error | names FTS5 and `sqlite3.sqlite_version` | `{"error": "fts5_unavailable"}` |

**Model-facing tool `recall`** (READ, internal). Parameters:

- `question` (string, required);
- `purpose` (string, required): what the caller will do with the answer;
- `known` (string, optional): what the caller already knows;
- `terms` (array of strings, optional): words to pre-search.

Descriptions come from the five `recall_*` leaves.

Result:

| Case | Status | Output |
|---|---|---|
| A retriever ran | success | `recall_card` filled and capped as INV-10.7 states: at most `INFINITE_RECALL_CARD_MAX_TOKENS` tokens, the `INFINITE_TRUNCATION_MARKER` included |
| Validation or quota refusal | error | `InfiniteAgentMemory.refusal(problem)` |
| The retriever raised `VidbyteSdkError`, `OSError`, or `ValueError` | error | names the error class and that one recall was used |

`CancelledError` always propagates.

The card's fields:

- **`{not_found}`:** one `- {what}` line per NOT FOUND line.
- **`{rejected}`:** one `- {citation}: {reason}` line per rejected citation, where code rebuilds `{citation}` as `#{id}` or `{path}:{start}-{end}` from the parsed fields, never with the retriever's `why`. A grammar-matching line with refused numbers is listed as `- reply line {n}: {reason}`, with the record's refusal text as the reason (EC-10.7).
- **`{searches}`:** one line per search that ran. Each pre-search term gets its own line. Each retriever call to `grep` or `search_memory` lists the tool name and its pattern or query.
- **`{found}`:** one block per accepted citation: `#{id} {kind}: {text}` for an entry, or `{path}:{start}-{end}` followed by the transcribed lines. A block holds only that code-built label and the text copied from disk. An accepted citation's `why` is not rendered anywhere in the card (INV-10.4, AC-10.3, T-2).

The leaf renders them in this order after `{question}`, so the card cap cuts transcribed text first (INV-10.7). An empty field renders as `-`.

**Retriever construction**, mirroring `InfinitePair._agent`:

```python
BaseAgent(
    name=f"{settings.name}/{memory.key}/recall",            # e.g. "analyst/root/recall"
    system_prompt=f"{settings.system_prompt}

{retriever_system_prompt}",
    provider=settings.provider, model_name=settings.model_name, api_keys=settings.api_keys,
    model_mode=settings.model_mode, temperature=settings.temperature, timeout_seconds=settings.timeout_seconds,
    tools=<get_tools(root_dir, workspace.root, max_tokens, max_read_lines, workspace.full_text) without bash>,
    permission_policy=settings.permission_policy,
    agent_loop_settings=AgentLoopSettings(max_iterations=INFINITE_RECALL_MAX_ITERATIONS, tool_settings=settings.loop.tool_settings),
    context_manager=<a ContextManager with the map drawn at TOP_OF_CONTEXT>,
    middleware=(<masking as on every agent>, <trim with the low watermark>),
)
```

The first message is `retriever_task_prompt` filled with the request and `{hits}`. `{hits}` is the pre-search output, one `search_memory` result under each term in the order given (INV-10.10), or `-` when no `terms` were given. The pre-search runs through the retriever's `search_memory`, which shares the workspace's index (INV-8.9), so a recall re-reads only files that changed since the last search from any agent.

**Retriever reply grammar** (parsed per line by `InfiniteRecallCitation.parse`; other lines are ignored):

- `FOUND #<id> (<why>)`
- `FOUND <path>:<start>-<end> (<why>)`
- `NOT FOUND (<what was searched>)`

The keyword may be wrapped in the same markdown decorations `INFINITE_VERDICT_PATTERN` tolerates (`*`, `_`, backticks, and surrounding whitespace). A leading `- ` bullet is allowed. The keywords are upper case and case-sensitive.

**Anthropic wire shape on a repeat request** (illustrative):

```json
{"model": "...", "max_tokens": 1024, "tools": [...],
 "system": [{"type": "text", "text": "<system>", "cache_control": {"type": "ephemeral"}}],
 "messages": [ ..., {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "...", "cache_control": {"type": "ephemeral"}}]},
               {"role": "assistant", "content": [...]},
               {"role": "user", "content": [{"type": "text", "text": "<status>", "cache_control": {"type": "ephemeral"}}]} ]}
```

A marked message whose content was a string, such as `<status>` above or the task prompt when it sits right before the newest assistant turn, goes out as that one marked text block; unmarked messages keep their string form (EC-9.10). The top-level keys are unchanged. Every mark sits inside `system` or a message content block, which the gateway admits: `_require_short_cache` checks the value is an object or null and that `ttl`, when present, is `"5m"` (backend `provider/generative_models/client.py:260-278`). `plan()` then builds `wire = {**body, "model": request.model}` (`:176`) and `send()` posts `plan.wire` unchanged (`:195`).

### 9.3 Configuration and flags

| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `FileSystemToolConfig.max_read_lines` | no | `None` (read to EOF) | Lines one `read_lines` call returns | `vidbyte/lib/dataclasses/filesystem.py` |
| `InfiniteWorkspaceSettings.max_read_lines` | no | `INFINITE_DEFAULT_MAX_READ_LINES` (200) | Read window of every InfiniteMemory agent, including the retriever | `vidbyte/agents/infinite/settings.py` |
| `InfiniteWorkspaceSettings.recall_mode` | no | `InfiniteRecallMode.DIRECT` | Whether the root and generators get `recall` instead of `grep` | `vidbyte/agents/infinite/settings.py` |
| `GrepTool(smart_case=…)` | no | `False` | Smart-case matching | `vidbyte/tools/builtins/code_search/grep.py` |
| `GrepTool(context_lines=…)` | no | `GREP_DEFAULT_CONTEXT_LINES` (2) | Context lines when a call omits the argument | same |
| `ToolOutputSlidingWindowCompaction(tools=…)` and the builder's `tools` | no | `()` (every tool) | Which tools' outputs are counted and compacted | `vidbyte/middleware/compaction/windows.py`, `context_compaction.py` |
| builder `placeholder` | no | `"[older tool result cleared by compaction]"` | The STRIP text, which the engine already forwards | `context_compaction.py` |
| `TrimWithProviderBoundariesCompaction(low_watermark_tokens=…)` and the builder's keyword | no | `None` (today's trim) | Hysteresis low watermark | `windows.py`, `context_compaction.py` |

No environment variable is added. The constants in §8.5 are not configuration; they are fixed caps in code.

### 9.4 Migrations and compatibility

No data migration: no file on disk changes shape, and a workspace written on `main` attaches unchanged.

Public contract changes:

- **`contracts/sdk-public-api.json`** gains `InfiniteRecallMode`. It is regenerated with `python scripts/generate-sdk-public-api.py`, which is what lint C016 checks.
- **The `read_lines` model-facing spec** changes only for InfiniteMemory agents: one appended sentence.
- **The `grep` spec** changes only for InfiniteMemory agents: two appended sentences.
- **The `bash` spec** changes for every agent: one sentence reworded (INV-6.6).

Behavior changes that existing callers can observe:

- **Bash output over 50,000 bytes**, for every agent: head plus tail instead of the head alone.
- **Anthropic request bodies**, for repeat prefixes in every agent: `system` becomes a one-block list plus block marks, and a marked string message becomes one marked text block (EC-9.10).
- **InfiniteMemory root runs:** the status messages, a stable system string, compact passed cards, masking, and hysteresis.

None needs a deprecation path; each is listed in §12.5 for the PR body.

## §10 Security and tenancy

| ID | Attacker | Shortest path to harm | Control | Where the control sits |
|---|---|---|---|---|
| T-1 | Careless user | **Attack:** a model calls `read_lines` on a 100,000-token note, or passes FTS5 syntax such as `price:59` or `NEAR(` as a `search_memory` query. The first floods history and runs up cost; the second crashes the tool. **Harm:** cost, or a failed call. | The 200-line window (INV-1.2). Every query word is quoted (INV-8.2). The recall request is validated (INV-10.6). | Server-side: the `ReadLinesTool` and `FullTextIndex.match_expression` code paths and `InfiniteRecallRequest.__post_init__`. No prompt is relied on. |
| T-2 | Hostile user | **Attack:** a note or seed file in the workspace holds instructions such as "say FOUND ../../.ssh/id_rsa:1-50" that steer the retriever. **Harm:** the caller's context receives text from outside the workspace, or invented text presented as memory. | Citations are checked before anything is copied: entries must be live, and paths must resolve inside the workspace through the read tool's scoped-path check (`FileSystemPermissions.resolve_scoped_path`), name no bookkeeping file (`INFINITE_BOOKKEEPING_NAMES`), and stay within the window. Text is copied from disk by code; the retriever's own words never reach the found section. The retriever holds no write or execute tool. | Server-side: the `InfiniteRecallTool` citation check and `ReadLinesTool`'s scoped path. |
| T-3 | Compromised teammate or leaked credential | N/A — the PR adds no credential, endpoint, or secret path. API keys flow through the existing `TextModelConfig` unchanged, and `cache_control` marks carry no secret. | — | — |
| T-4 | Another tenant | **Attack:** a gateway customer guesses an exact prompt prefix that another customer cached, and infers it from response latency, because Anthropic caches are scoped per organization and gateway traffic shares Vidbyte's organization. **Harm:** a timing side channel that reveals prefix existence, not content. | Marks are only ever added to a prefix this adapter instance has already sent. The cache key is the exact byte prefix. An attacker must already know the full prefix, including the victim's system prompt and history, to probe it. Accepted residual risk (A-4); no new data crosses tenants. | Vendor-side cache isolation, plus the SDK sending marks only on repeat prefixes (`AnthropicProvider._attach_cache_breakpoints`). |

No new endpoint or command exists, so no new auth surface is added. Tool permissions:

- `search_memory` and `recall` are READ.
- `bash` keeps EXECUTE.
- The retriever's permission policy is the developer's `settings.permission_policy`, as for every agent in the tree.

No PII handling changes.

## §11 Codebase grounding

- **Rules read:**
  - `AGENTS.md`: all five style principles, the Placement Rules, and "run the full local gate".
  - `REPO_MAP.md`: the `vidbyte/tools/builtins/`, `vidbyte/tools/toolsets/`, and `vidbyte/agents/infinite/` entries.
  - Folder READMEs:
    - `vidbyte/agents/infinite/README.md` (all, including Notes for agents);
    - `vidbyte/agents/README.md:146`, `:177`;
    - `vidbyte/tools/README.md:89-91`;
    - `vidbyte/providers/README.md` (Anthropic section);
    - `vidbyte/lib/README.md:48`;
    - `vidbyte/prompts/README.md:67`, `:229-250`;
    - `tests/features/infinite_memory_agent/README.md:24`.
  - Lint rule headers:
    - `lint/rules/a002_intent_comments.py`;
    - `a006_directed_dependency_graph.py`;
    - `a007_operational_constants.py`;
    - `c007_strict_bool_switches.py`;
    - `c008_shared_validator_owner.py`;
    - `c015_package_data_coverage.py`;
    - `s020_readme_file_index_parity.py`;
    - `s025_model_facing_description_depth.py`.
- **Field-guide entries applied** (root `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`, as quoted in `context/code-map.md` §1):
  - `local-ci-verification.md`: source stage with `PYTHONPATH=$(pwd)`, package stage without; `git add` new files before Semgrep; `harness_threads` failures are pre-existing; run the public-API `--check`; append dataclass fields at the end.
  - `runtime-boundaries.md`: reuse the shared compaction infrastructure; deterministic caps live in code.
  - `strict-config-dataclasses.md`: validate with `RecordFieldValidator`/`RecordFieldConverter`; constants in the shared constants package; the constants header states the token-budget sum.
  - `prompt-families.md`: one `.md` per leaf, no numbers in prompt text, a leaf-count contract test.
  - `comment-format.md`: 72-column comment blocks; `@intent` within 20 lines of its `def`.
  - `model-facing-tool-contracts.md`: 4–5 sentence descriptions, no examples.
  - `blocking-lint-invariants.md`: A006 and A003.
  - `class-bound-helpers.md`: search `vidbyte/lib/` first; prefer a static helper class.
- **Stack (from manifests):**
  - Python 3.11+ (dev interpreter 3.11.0; stdlib `sqlite3` reports SQLite 3.38.4 with FTS5, request.md §C).
  - pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48-49`).
  - No database server; SQLite is in-memory and stdlib only.
- **Commands (exact, from `context/code-map.md` §1/§3 and AGENTS.md):**
  - Install: none. The worktree has no `.venv`. Use the global Python 3.11.0 (stdlib SQLite 3.38.4, FTS5 present), with `PYTHONPATH=$(pwd)` at the worktree root for the source stage and every test command, and without it for the package stage (field guide `local-ci-verification.md`). AGENTS.md defines no install command.
  - Lint: `python lint/run.py`. One rule: `python lint/run.py --rule A007`. Ratchet after a genuine IMPROVED: `python lint/run.py --rule <ID> --update-baseline`.
  - Typecheck: inside the source stage (`lint/run.py` runs the staged mypy rule S009). There is no separate command.
  - Test (focused):
    - InfiniteMemory pack: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`.
    - Other affected areas: `PYTHONPATH=$(pwd) python -m pytest tests/test_deterministic_compaction_middleware.py tests/test_context_compaction_middleware.py tests/test_filesystem_tools.py tests/test_code_search_tools.py tests/features/coding_agent tests/features/sdk_managed_text -q`.
  - Test (full): `python -m pytest tests -q`, run inside the source stage.
  - Full local gate: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` without `PYTHONPATH`.
  - Public API: `python scripts/generate-sdk-public-api.py --check`.
  - Remote-only checks: GitHub CI `ci.yml`, which runs manually per memory notes and is dispatched by the orchestrator, not by this spec; the `AGENTS.md placement` workflow; the `@claude` review.
- **Baseline on clean `origin/main`:**
  - Every `lint/baseline.json` count is at its recorded value (`A007: 255`, `S025: 263`, `S020: 1`, `C016: 0`).
  - The `harness_threads` tests fail on any branch that touches `vidbyte/tools`. This is pre-existing (field guide), so never edit them.
  - Linux CI's FTS5 is unverified (A-1).
- **Directory layout relevant to this change:**
  ```text
  vidbyte/
    agents/infinite/{agent,launch,memory,recall*,runtime,settings,workspace}.py   (* new)
    agents/runtime.py                         (read only: base hooks)
    lib/constants/infinite.py
    lib/dataclasses/{filesystem,coding,code_search,infinite}.py
    lib/enums/{infinite,prompts,__init__}.py
    lib/registries/infinite.py
    lib/util/{__init__,fulltext*}.py          (* new)
    middleware/compaction/{strategies,windows*,engine,context_compaction,__init__}.py
    prompts/prompts/infinite_memory/*.md + infinite_memory.json
    providers/anthropic.py
    tools/builtins/bash.py
    tools/builtins/code_search/{base,grep,search_memory*}.py
    tools/filesystem/read_lines.py
    tools/toolsets/{infinite,__init__}.py
    __init__.py
  contracts/sdk-public-api.json
  lint/baseline.json
  ```
- **Nearest sibling feature (the template to copy):**
  - The memory tools in `vidbyte/agents/infinite/memory.py`, for the spec/execute shape, leaf-based descriptions, refusal plus quota, and the builder in `tools()`.
  - `InfinitePair._agent` in `vidbyte/agents/infinite/launch.py:252-291`, for building a child agent from settings with a map and middleware.
  - `GrepTool` in `vidbyte/tools/builtins/code_search/grep.py`, for a code-search tool's shape.
- **Reusable pieces:**
  - `vidbyte/lib/util/text.py:TokenEstimate.cap`: caps card text with a marker.
  - `vidbyte/lib/tools/filesystem:LineEndings.split_bare_lines`: line numbering used by read_lines and grep.
  - `vidbyte/tools/builtins/code_search/base.py:BaseCodeSearchTool.iter_files`, `read_text_lines`: file walk, byte cap, NUL skip.
  - `vidbyte/agents/infinite/workspace.py:InfiniteWorkspace.entries`: live-entry lookup that raises for non-live ids.
  - `vidbyte/agents/infinite/launch.py:InfinitePair.finished_lines`: the compact card line.
  - `vidbyte/agents/runtime.py:AgentRuntime._render_loop_settings_block`: the counter block, reused in the status message.
  - `vidbyte/lib/registries/infinite.py:InfiniteMemoryToolRegistry`: tool grants.
  - `vidbyte/lib/dataclasses/validation.py:RecordFieldValidator`/`RecordFieldConverter`, as used by `InfiniteWorkspaceSettings`: settings validation.
  - `vidbyte/tools/catalog.py:Tools.without` (`:90`): removes withheld tools. It takes tool objects, not names, so a caller passes the catalog's tools whose `name` is in `withheld_tool_names(...)`.
- **Code-style exemplar** (`vidbyte/agents/infinite/runtime.py:104-110`, verbatim):
  ```python
      async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
          """Render the workspace map again after each tool iteration, so the root's next call sees what changed."""
          # @intent the-roots-map-follows-the-disk
          # Tools, bash, and finished pairs change the workspace between
          # calls, and the map is the root's only view of it.
          if self.context_manager is not None:
              self.context_manager.upsert(self._map(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)
  ```
- **Domain glossary:**
  - **root, generator, verifier, pair:** the InfiniteMemory agent roles. A pair is a generator plus its verifier.
  - **workspace:** the shared memory folder.
  - **map:** the per-file token and description list.
  - **entry:** one line in `entries.jsonl`.
  - **result card:** a pair's report to its parent.
  - **masking:** replacing an old tool output with a placeholder while keeping the call.
  - **low watermark:** the size the trim cuts down to.
  - **breakpoint / mark:** a `cache_control` block field.
  - **retriever:** the agent `recall` runs.
  - **citation:** a `FOUND` line.
  - **transcription:** copying cited text from disk.
- **Prior specs / design docs / ADRs that constrain this:**
  - `docs/spec/infinite-memory-agent/spec.md`, cited by the module headers. Not opened, per the `docs/` rule; its IDs (D-27, INV-6) are quoted from code headers only.
  - `docs/spec/infinite-memory-context-economy/request.md` and `pipeline.md`.
  - `docs/design/coding-agent-max-rewrite-lines.md` names `OverwriteLineLimit`. It is left unchanged, because docs are not maintained per AGENTS.md.
- **Conflicts between house style and AGENTS.md:**
  - `vidbyte/tools/filesystem/read_lines.py` and `vidbyte/middleware/compaction/strategies.py` have no A001 header. AGENTS.md says not to rewrite untouched code, so no header is added to them. The new `windows` module gets one.
  - `CompactionMode` lives outside `vidbyte/lib/enums/`. It is used, not moved.

---

## §12 Work breakdown — everything this PR has to do

### 12.1 Feature list

| ID | Feature (capability this PR adds) | Serves | Visible to |
|---|---|---|---|
| W-1.1 | A read window on `ReadLinesTool` through `FileSystemToolConfig.max_read_lines`: footer, metadata, and description sentence. `LineLimit` validates both line caps. | FR-1.1, FR-1.2, INV-1.1–1.7, AC-1, AC-1.1–1.5 | developer |
| W-1.2 | Every InfiniteMemory agent reads in windows of `InfiniteWorkspaceSettings.max_read_lines` (200). | FR-1.3, AC-1.6, NFR-1.1 | developer, end user (cost) |
| W-2.1 | A `tools` scope on the per-tool output window, and `placeholder`/`tools` on its middleware builder. The window and the trim move to the new `windows` module. | FR-2.1, INV-2.1–2.5, AC-2.3, NFR-0.4 | developer |
| W-2.2 | InfiniteMemory masks older `grep`/`read_lines`/`search_memory` outputs (keep 3, STRIP, leaf placeholder), first in every agent's middleware. | FR-2.2, INV-2.6, INV-0.1, INV-0.4, AC-2.1, AC-2.2, AC-2.4, NFR-2.1 | end user (cost) |
| W-3.1 | `GrepTool` options `smart_case` and `context_lines`, and the `CODE_SEARCH_MAX_FILE_BYTES` constant. | FR-3.1, INV-3.1–3.3, INV-R.1, AC-3.3, AC-3.4 | developer |
| W-3.2 | The InfiniteMemory workspace grep is smart-case with 0 context lines. | FR-3.2, INV-3.4, AC-3.1, AC-3.2, NFR-3.1 | end user |
| W-4.1 | A `low_watermark_tokens` hysteresis option on the provider-boundary trim. | FR-4.1, INV-4.1–4.4, AC-4.1–4.5, NFR-4.1 | developer |
| W-4.2 | InfiniteMemory trims to 65K under the 90K cap. | FR-4.2, INV-4.5 | end user (cost) |
| W-5.1 | Compact `done`/`passed`/`fixed` result cards. | FR-5.1, INV-5.1–5.4, AC-5.1–5.3, NFR-5.1 | end user |
| W-6.1 | Bash keeps the head and the tail of a long output. | FR-6.1, INV-6.1–6.6, AC-6.1–6.5, NFR-6.1 | developer, end user |
| W-7.1 | The root's system string is stable: the map is drawn once, there is no loop block in the system string, and a status message follows each tool iteration. | FR-7.1, FR-7.2, INV-7.1–7.6, AC-7.1–7.5, NFR-7.1, NFR-7.2 | end user (cost) |
| W-8.1 | The canonical `FullTextIndex` lib helper and its records. | FR-8.3, FR-8.4, INV-8.2, INV-8.6 | developer |
| W-8.2 | The `search_memory` tool on every InfiniteMemory agent, with prompt mentions. | FR-8.1, FR-8.2, FR-8.5–8.8, INV-8.1–8.9, AC-8.1–8.7, NFR-8.1–8.3 | end user |
| W-9.1 | Repeat-gated block-level Anthropic cache breakpoints. | FR-9.1, INV-9.1–9.7, INV-R.4, AC-9.1–9.5, NFR-9.1, NFR-0.5 | developer, end user (cost) |
| W-10.1 | `InfiniteRecallMode` and the registry's recall grants and withheld tools. | FR-10.1, FR-10.2, FR-10.4, FR-10.9, INV-10.1, INV-10.2, AC-10.1, AC-10.2, AC-10.6 | developer |
| W-10.2 | The `recall` tool: request validation, quota, pre-search, retriever, citation check, transcription, and card. | FR-10.3, FR-10.5–10.8, INV-10.3–10.10, AC-10.3–10.5, AC-10.7, AC-10.8, NFR-10.1–10.3 | end user |
| W-0.1 | Docs, contract, and lint ratchet for all of the above, plus the cross-cutting rules every row keeps. | FR-0.1, NFR-0.1–0.4, AC-1, INV-0.2, INV-R.5 | developer |

### 12.2 Folder and module map

| Folder | Kind of code (per repo rules) | New? | README / header obligation | May import from |
|---|---|---|---|---|
| `vidbyte/lib/dataclasses/` | Validated frozen records (Placement Rules) | no | No README file index. New records go in existing domain modules (`filesystem`, `code_search`, `infinite`) and are added to each module's `__all__`. | `vidbyte/lib/` only |
| `vidbyte/lib/enums/` | Enums, exported from `__init__` | no | Export the public enum | `vidbyte/lib/` only |
| `vidbyte/lib/constants/` | Named constants, no model-facing sentences | no | Keep the header budget sum true | nothing above `vidbyte/lib/` |
| `vidbyte/lib/registries/` | Policy-as-data registries | no | Update the module header inventory | `vidbyte/lib/` only (never `agents`/`tools`) |
| `vidbyte/lib/util/` | Canonical helpers "equally at home in an unrelated project" | no (new module) | A001 header on `fulltext.py`; re-export from `__init__`; list in `vidbyte/lib/README.md:48` | stdlib and `vidbyte/lib/` only |
| `vidbyte/middleware/compaction/` | Compaction strategies, engine, and middleware builders | no (new module) | A001 header on `windows.py`; there is no folder README | `vidbyte/lib/`, own package |
| `vidbyte/tools/builtins/code_search/` | Root-scoped code-search tools | no (new module) | A001 header on `search_memory.py`; update the package docstring and exports | `vidbyte/lib/`, `vidbyte/tools/` (never `vidbyte.agents`) |
| `vidbyte/tools/builtins/` | Built-in tools (`bash.py`) | no | Keep the `bash.py` header true | `vidbyte/lib/`, `vidbyte/tools/` |
| `vidbyte/tools/filesystem/` | Filesystem tools | no | none (`read_lines.py` has no header; do not add one) | `vidbyte/lib/`, `vidbyte/tools/` |
| `vidbyte/tools/toolsets/` | Pre-assembled catalogs, no new capability (REPO_MAP) | no | Keep the header and package docstring true | `vidbyte/lib/`, `vidbyte/tools/` (never `vidbyte.agents`) |
| `vidbyte/providers/` | Provider adapters (payload shapes) | no | `vidbyte/providers/README.md` Anthropic section | `vidbyte/lib/` |
| `vidbyte/agents/infinite/` | The InfiniteMemory agent: at most 9 modules (its 8 plus `recall.py`, D-18), each at most 400 lines after its header | no (new module) | A001 header on `recall.py`; the README File Index lists it (S020); the README sections named in §12.5; every changed module's header | everything below `agents/`; `recall.py` imports `memory.py` only under `TYPE_CHECKING` |
| `vidbyte/prompts/prompts/infinite_memory/` | One `.md` per leaf plus the family JSON | no | Register every leaf in `infinite_memory.json`; list them in `vidbyte/prompts/README.md:67`; no numbers in the text | — |
| `contracts/` | Generated public API contract | no | Regenerate, never hand-edit | — |
| `lint/` | Count baseline | no | Ratchet down only | — |

### 12.3 File-by-file actions

| # | Action | Path | Kind of code | What exactly changes (symbols, signatures, exports, registrations) | Governing standard | Serves | Phase |
|---|---|---|---|---|---|---|---|
| 1 | MODIFY | `vidbyte/lib/dataclasses/filesystem.py` | dataclass | <ul><li>Rename `OverwriteLineLimit` to `LineLimit` and `_MIN_OVERWRITE_LINES` to `_MIN_LINE_LIMIT`. Keep the refusal text `"{parameter} must be None or an int of at least 1."` and the `details` keys.</li><li>Generalize its `@intent` slug and comment to "line caps".</li><li>Append `max_read_lines: int \| None = None` as the last field of `FileSystemToolConfig`. `__post_init__` checks it with `LineLimit(self.max_read_lines, "max_read_lines")` after the existing check.</li><li>Update `__all__`.</li></ul> | AGENTS.md principle 4; field guide `local-ci-verification.md` ("append new dataclass fields at the end"); lint C006/C007 (strict int, bool refused); A002 | W-1.1, FR-1.1, FR-1.2, INV-1.5, INV-R.2 | P1 |
| 2 | MODIFY | `vidbyte/lib/dataclasses/coding.py` | dataclass | <ul><li>The import and the use at `:28`/`:90` become `LineLimit`.</li><li>Header FUNCTION INVENTORY (line 6): "checked by OverwriteLineLimit" becomes "checked by LineLimit".</li><li>No behavior change.</li></ul> | AGENTS.md "Existing code" (edit in place) | W-1.1, FR-1.2, INV-R.2 | P1 |
| 3 | MODIFY | `vidbyte/tools/filesystem/read_lines.py` | tool | <ul><li>`ReadLinesTool.spec()`: when `self._config.max_read_lines` is set, return `dataclasses.replace(spec, description=f"{spec.description} At most {limit:,} lines come back from one call; when more lines remain in the requested range, the result ends with a line naming the next start line.")`.</li><li>`execute`: compute `total`, the clipped range, the window, the footer, and the three metadata keys (INV-1.2–1.4). Narrate the steps.</li><li>With no cap, the output, the metadata, and the spec are unchanged.</li></ul> | Pattern `write_text.py:28-31`; AGENTS.md principles 1–2; S025 (a description built by `replace` is not resolved); INV-0.3 does not apply (the sentence is in code, not a leaf) | W-1.1, FR-1.1, AC-1, AC-1.1–1.4 | P1 |
| 4 | CREATE | `vidbyte/middleware/compaction/windows.py` | middleware strategy | <ul><li>A001 header (PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS, WHAT NOT TO DO, KNOWN EDGE CASES, RELATED DOCS, TESTS).</li><li>Move `TrimWithProviderBoundariesCompaction` and `ToolOutputSlidingWindowCompaction` here from `strategies`.</li><li>Trim: add `low_watermark_tokens` (INV-4.1–4.4). Lift the nested `cost` function into a private method (principle 1, changed code). When `low_watermark_tokens` is `None` or ≥ `max_tokens`, keep today's algorithm byte for byte.</li><li>Window: add `tools: Sequence[str] = ()` as the last parameter, refuse a blank name with `ValueError`, count and compact only scoped tool names (INV-2.1–2.3).</li><li>Import `_provider_groups`, `_message_tokens`, `_message_tool_name`, `_replace_message_content`, `_head_tail_text`, and the other helpers the two classes use from `strategies`.</li><li>`__all__` lists both classes.</li></ul> | AGENTS.md principle 3 (split before 1,000 lines), principle 1 (no nested functions in changed code), principle 2; A001; A002 (`@intent` on the hysteresis rule); A006 (no cycle: `windows` imports `strategies`, never the reverse); A007 (move the existing literal defaults unchanged; add none); C006 (guard the new option as `low_watermark_tokens is not None and (isinstance(low_watermark_tokens, bool) or not isinstance(low_watermark_tokens, int) or low_watermark_tokens < 0)` raising `ValueError`, never the `max_messages < 0` shape of the moved guards; the moved classes' existing findings, `strategies.py:599`, `:601`, `:670`, move with them and leave the count unchanged) | W-2.1, W-4.1, FR-2.1, FR-4.1, NFR-0.4, NFR-0.3 | P1 |
| 5 | MODIFY | `vidbyte/middleware/compaction/strategies.py` | middleware strategy | Delete the two moved classes (`:594-636`, `:663-711`) and their `__all__` entries (`:994-`). Keep every helper. Do not re-export from `windows` (no cycle). The file drops below 1,000 lines. | AGENTS.md principle 3; A006 | W-2.1, NFR-0.4 | P1 |
| 6 | MODIFY | `vidbyte/middleware/compaction/engine.py` | middleware engine | <ul><li>Import both classes from `windows`.</li><li>Trim branch (`:195-198`): pass `low_watermark_tokens=options.get("low_watermark_tokens")` unchanged, with no `int()`, so the strategy's guard (row 4) sees the caller's value and refuses a `bool`, a float, or a negative number.</li><li>Window branch (`:203-206`): pass `tools=self._string_tuple(options.get("tools", ()))`.</li></ul> | runtime-boundaries field guide (reuse the compaction engine) | W-2.1, W-4.1, FR-2.1, FR-4.1 | P1 |
| 7 | MODIFY | `vidbyte/middleware/compaction/context_compaction.py` | middleware | <ul><li>Import the window from `windows`.</li><li>`trim_with_provider_boundaries` gains keyword-only `low_watermark_tokens`.</li><li>`tool_output_sliding_window` gains keyword-only `placeholder` and `tools`, forwarded as options.</li><li>`_validate_options` builds the validation window with the `tools` option, so a blank scope name fails at construction. When `low_watermark_tokens` is given, it likewise builds `TrimWithProviderBoundariesCompaction(low_watermark_tokens=...)` once, so the strategy's guard is the one check and a bad value fails at construction. The key does not join the `int()` non-negative tuple, which would accept `True` and `2.5`.</li></ul> | Existing `@intent sliding-window-refuses-modes-it-cannot-apply`; A007 (keyword defaults are `None`/`()`/str) | W-2.1, W-4.1, FR-2.1, FR-4.1, AC-2.3 | P1 |
| 8 | MODIFY | `vidbyte/middleware/compaction/__init__.py` | package exports | Import the two classes from `windows` instead of `strategies`. `__all__` is unchanged. | INV-R.3 (public import path kept); S015 | W-2.1 | P1 |
| 9 | MODIFY | `vidbyte/tools/builtins/code_search/base.py` | tool base | Add `CODE_SEARCH_MAX_FILE_BYTES = 1_000_000` and use it as `BaseCodeSearchTool.__init__`'s `max_file_bytes` default. This removes one A007 finding. | A007 (UPPERCASE constant exempt); ratchet `A007` down | W-3.1, NFR-0.3 | P1 |
| 10 | MODIFY | `vidbyte/tools/builtins/code_search/grep.py` | tool | <ul><li>Add `GREP_DEFAULT_CONTEXT_LINES = 2` and `GREP_MAX_CONTEXT_LINES = 5`.</li><li>Add `GrepTool.__init__(root_dir, *, ignore_patterns=None, max_file_bytes=CODE_SEARCH_MAX_FILE_BYTES, smart_case=False, context_lines=GREP_DEFAULT_CONTEXT_LINES)`. It calls the base, then checks `smart_case` with `RecordFieldValidator.require_bool` and `context_lines` with `RecordFieldValidator.require_int(minimum=0, maximum=GREP_MAX_CONTEXT_LINES)`, both raising `ConfigurationError`.</li><li>`spec()` appends one sentence per non-default option: the smart-case sentence of D-4 and "When a call leaves context_lines out, it shows {n} lines around each match."</li><li>`execute`: the default clamp uses the constants and `self.context_lines`, and `re.IGNORECASE` is added when smart case applies (INV-3.2).</li></ul> | A007; C006 (the shared validators refuse `True`, NaN, and infinities, so no new finding); C007 is not triggered (not a config class; the bool is still checked); S025 (the base sentence is unchanged; appended sentences go through `replace`); NG-10 | W-3.1, FR-3.1, INV-3.1–3.3, AC-3.3, AC-3.4 | P1 |
| 11 | MODIFY | `vidbyte/lib/dataclasses/code_search.py` | dataclass | Add `FullTextRow`, `FullTextHit`, `FullTextMatches` (§9.1 validation) and `__all__` entries. | Placement Rules (dataclasses in `lib/dataclasses/<domain>.py`); principle 4; C006 (`total` through `RecordFieldValidator.require_int(minimum=len(hits))`) | W-8.1, FR-8.3 | P1 |
| 12 | CREATE | `vidbyte/lib/util/fulltext.py` | lib helper | <ul><li>A001 header.</li><li>`FULLTEXT_SNIPPET_MAX_TOKENS = 64`.</li><li>`FullTextIndex`: `__init__` opens nothing and creates the public `lock` (a `threading.RLock`), so building a workspace never fails. The first method that needs the table opens the in-memory `sqlite3` connection with `check_same_thread=False` and creates the FTS5 table of §9.1; a failure there becomes `ConfigurationError` naming FTS5 and `sqlite3.sqlite_version`. Every method takes `lock`, and a caller may hold it across a refresh and a search.</li><li>Methods: `fingerprint`, `replace` and `retain` (both delete by the rowids recorded per source, never by `source`, §9.1), `search` (refuses `limit < 1` and `snippet_tokens` outside 1..64 with `ValueError`, each in the shape `isinstance(x, bool) or not isinstance(x, int) or …`), and static `match_expression`.</li><li>Imports nothing above `vidbyte/lib/`.</li></ul> | AGENTS.md principle 5 (canonical helper in `lib/`); class-bound-helpers field guide; A001; A002 (`@intent` on quoting, on the lock, and on the lazy table); A003; A006; C006 | W-8.1, FR-8.2–8.4, INV-8.2, INV-8.6, INV-8.9 | P1 |
| 13 | MODIFY | `vidbyte/lib/util/__init__.py` | package exports | Re-export `FullTextIndex` and add it to `__all__`. | `lib/util/__init__.py` header; S015 | W-8.1, FR-8.3 | P1 |
| 14 | MODIFY | `vidbyte/tools/builtins/bash.py` | tool | <ul><li>Add `BASH_TAIL_OUTPUT_BYTES = 25_000`.</li><li>`execute` keeps `head` and `tail` bytearrays and a one-item `omitted` count. `_collect(process, head, tail, omitted)` fills the head to H, then keeps a rolling tail of T bytes and adds what it drops to `omitted[0]`, which `execute` can still read after a timeout cancels the read. T and H follow INV-6.2 (`T = min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES // 2)`).</li><li>The timeout path shows the INV-6.2 marker with the count so far only when `omitted[0]` is above 0, and sets `truncated` from it (INV-6.4).</li><li>`_render(head, tail, omitted, exit_code)` joins before decoding when nothing is omitted (INV-6.1). Otherwise it renders INV-6.2.</li><li>The `spec()` sentence follows INV-6.6.</li><li>Header: ARCHITECTURE NOTE ("only the first … are kept"), FUNCTION INVENTORY (`_collect`), and "five BASH_* constants".</li><li>The read loop holds no numeric literal (A007).</li></ul> | bash.py header COMMON MODIFICATION PATTERNS (flat helpers, constants as globals); A007; A002 (keep `@intent one-limit-over-reading-and-waiting`, add one for head+tail); S025 (literal description stays at least 4 sentences) | W-6.1, FR-6.1, AC-6.1–6.5 | P2 |
| 15 | MODIFY | `vidbyte/providers/anthropic.py` | provider adapter | <ul><li>Add `ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT = 256`.</li><li>`__init__` gains `self._seen_prefixes: set[str] = set()`.</li><li>`_create_payload` calls `self._attach_cache_breakpoints(payload, config)` last.</li><li>`_attach_cache_breakpoints` checks the conditions:<ol><li>caller-supplied `cache_control` anywhere means stop;</li><li>a sha256 digest of `json.dumps([payload.get("tools"), payload.get("system")], sort_keys=True, ensure_ascii=False)` not seen before means record it and stop;</li><li>otherwise mark per INV-9.3.</li></ol></li><li>Marks go on copies, so `payload["messages"]` entries that get a mark are replaced with new dicts and new content lists. The adapter's own `dict(message)` copies share the caller's content lists, so the list must be copied too. A full set is cleared before the add.</li><li>A marked message whose content is a non-empty string gets a new dict whose content is `[{"type": "text", "text": <string>, "cache_control": {"type": "ephemeral"}}]`; unmarked messages keep their string form (INV-9.3, EC-9.10). This deliberately changes one existing test (§13).</li><li>No top-level key is added.</li></ul> | provider-api-contracts field guide (mirror the vendor reference); one guarded try per call is unchanged; S050 (sha256 is allowed); A002 (`@intent` on repeat-gating and on copy-not-mutate); backend gateway rules (`provider/generative_models/client.py:119`, `:260-278`) | W-9.1, FR-9.1, INV-9.1–9.7, AC-9.1–9.5 | P2 |
| 16 | MODIFY | `vidbyte/lib/constants/infinite.py` | constants | <ul><li>Add the §8.5 constants, with comments in the file's style. P3: `INFINITE_DEFAULT_MAX_READ_LINES`, `INFINITE_MASK_KEEP_RECENT`, `INFINITE_MASKED_TOOL_NAMES`, `INFINITE_GREP_CONTEXT_LINES`, `INFINITE_HISTORY_LOW_WATERMARK_TOKENS`, `INFINITE_MAP_REMOVED_LINE`, and `INFINITE_SEARCH_MEMORY_TOOL_NAME` (the name only, because `INFINITE_MASKED_TOOL_NAMES` uses it). P4: `INFINITE_SEARCH_MAX_HITS`, `INFINITE_SEARCH_SNIPPET_TOKENS`, `INFINITE_BOOKKEEPING_NAMES` (built from the four existing layout names). P5: `INFINITE_RECALL_TOOL_NAME`, `INFINITE_RECALLS_PER_AGENT`, `INFINITE_RECALL_MAX_TERMS`, `INFINITE_RECALL_MAX_ITERATIONS`, `INFINITE_RECALL_CARD_MAX_TOKENS`, `INFINITE_RECALL_FOUND_ENTRY_PATTERN`, `INFINITE_RECALL_FOUND_RANGE_PATTERN`, `INFINITE_RECALL_NOT_FOUND_PATTERN`.</li><li>`INFINITE_SEARCH_MEMORY_TOOL_NAME` joins `INFINITE_RESERVED_TOOL_NAMES` in P4, when the tool arrives; `INFINITE_RECALL_TOOL_NAME` joins `INFINITE_RUN_BOUND_TOOL_NAMES` in P5.</li><li>Update the header's 105,000-token sum to the new tool descriptions, and the `:61-65` comment (a batch of passed cards is now finished lines plus summaries).</li><li>Add every new name to the alphabetical `__all__`.</li></ul> | constants header WHAT NOT TO DO 2 (no model-facing sentences; the citation patterns and the removed-line label are formats/labels); strict-config field guide (header states the budget sum); NFR-0.2 | W-1.2, W-2.2, W-3.2, W-4.2, W-7.1, W-8.2, W-10.2 | P3 (item 1–7 constants), P4 (search), P5 (recall) |
| 17 | MODIFY | `vidbyte/agents/infinite/settings.py` | settings (Placement exception 1) | <ul><li>`InfiniteWorkspaceSettings` gains `max_read_lines: int = INFINITE_DEFAULT_MAX_READ_LINES`, checked with `RecordFieldValidator.require_int(minimum=INFINITE_MIN_CAP)` under the name `"InfiniteWorkspaceSettings.max_read_lines"`.</li><li>It also gains `recall_mode: InfiniteRecallMode \| str = InfiniteRecallMode.DIRECT`, converted with `RecordFieldConverter.to_enum`. Both fields go at the end.</li><li>Header PURPOSE/FUNCTION INVENTORY text.</li></ul> | settings header COMMON MODIFICATION PATTERNS (one field, one validator call, a named default, one README limits row); C006/C007/C008 | W-1.2, W-10.1, FR-1.3, FR-10.1, AC-1, AC-1.5 | P3 (`max_read_lines`), P5 (`recall_mode`) |
| 18 | MODIFY | `vidbyte/tools/toolsets/infinite.py` | toolset | <ul><li>`__init__`/`get_tools` gain `max_read_lines` (P3) and `index: FullTextIndex` (P4).</li><li>Grep gets `smart_case=True, context_lines=INFINITE_GREP_CONTEXT_LINES`, and read_lines gets `FileSystemToolConfig(root=workspace_root, max_read_lines=max_read_lines)`.</li><li>In P4, append `InfiniteSearchMemoryTool(workspace_root, index=index, max_file_bytes=largest_file_bytes)`.</li><li>Header and class docstring say four tools. Never import `vidbyte.agents`.</li></ul> | toolset header (a tool every agent holds goes in `get_tools`, the reserved names, and the README tool table together); NFR-0.2 | W-1.2, W-3.2, W-8.2, FR-1.3, FR-3.2, FR-8.1 | P3, P4 |
| 19 | MODIFY | `vidbyte/tools/toolsets/__init__.py` | package docstring | Docstring line 11 names `search_memory` beside grep and read_lines. | S015 | W-8.2 | P4 |
| 20 | CREATE | `vidbyte/tools/builtins/code_search/search_memory.py` | tool | <ul><li>A001 header.</li><li>`InfiniteSearchMemoryTool(BaseCodeSearchTool)`: takes the workspace's `index`; `ignore_patterns=INFINITE_BOOKKEEPING_NAMES`.</li><li>`spec()` holds literal 4–5 sentence descriptions (FR-8.5).</li><li>`execute` (narrated) refuses a blank query, then awaits `asyncio.to_thread` for the refresh and the search, which hold `index.lock` across both (`@intent search-memory-runs-off-the-event-loop`). The refresh goes by fingerprint: entries come from `entries.jsonl`, with malformed lines skipped, and note lines come from `iter_files` + `read_text_lines`. A `ConfigurationError` from the index's first use becomes `fts5_unavailable`. It renders INV-8.3.</li><li>File reading and every SQLite call happen in the worker thread, never on the event loop (lint S047 and S052 do not cover `sqlite3`, so the marker and review guard it).</li></ul> | REPO_MAP (`builtins/` holds tool capabilities); D-12; S025 (literal, at least 4 sentences); S047 (no `open` in `async def`); precedent `vidbyte/tools/builtins/code_search/semantic.py:78-81` (`asyncio.to_thread`, `@intent semantic-search-runs-off-the-event-loop`); A001; A002; A006 (imports `vidbyte/lib/` and `vidbyte/tools/` only) | W-8.2, FR-8.1, FR-8.2, FR-8.5, FR-8.6, INV-8.1–8.9, AC-8.1–8.7 | P4 |
| 21 | MODIFY | `vidbyte/tools/builtins/code_search/__init__.py` | package exports | Import and export `InfiniteSearchMemoryTool`, and list it in the docstring. | S015 | W-8.2 | P4 |
| 22 | MODIFY | `vidbyte/agents/infinite/agent.py` | agent | <ul><li>Root tools: `InfiniteMemoryAgentTools(Path(settings.root_dir), self.workspace.root, settings.workspace.max_tokens, settings.workspace.max_read_lines, self.workspace.full_text)` (the index argument from P4).</li><li>In P5, without the tools whose `name` is in `InfiniteMemoryToolRegistry.withheld_tool_names(settings.workspace.recall_mode, InfiniteAgentRole.ROOT)` (`Tools.without` takes tool objects, not names).</li><li>Middleware: `(MessageHistoryCompactionMiddleware.tool_output_sliding_window(INFINITE_MASK_KEEP_RECENT, CompactionMode.STRIP_TOOL_RESULT_BODIES, placeholder=Prompts().get(Prompt.INFINITE_MEMORY_MASKED_OUTPUT), tools=INFINITE_MASKED_TOOL_NAMES), MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS, low_watermark_tokens=INFINITE_HISTORY_LOW_WATERMARK_TOKENS), DelegationLimitsMiddleware(...))`.</li><li>Header ARCHITECTURE NOTE.</li></ul> | INV-0.4; NFR-0.2 (≤ 400 lines after header) | W-1.2, W-2.2, W-3.2, W-4.2, W-8.2, W-10.1 | P3, P4, P5 |
| 23 | MODIFY | `vidbyte/agents/infinite/launch.py` | agent pipeline | <ul><li>P5: in `InfinitePair.run`, both memories get `settings=launch.settings`.</li><li>`_agent`: `get_tools(..., launch.workspace.settings.max_read_lines, launch.workspace.full_text)` (the index from P4) with the withheld tools filtered out by name for GENERATOR (P5), and middleware `(masking, trim with low watermark, *limits)` as in row 22.</li><li>`render`: compact form per INV-5.1, otherwise unchanged. Replays use `render`, so INV-5.3 follows.</li><li>Update the header lines that describe the card and the tools. Keep edits minimal and local (request.md §C, #1159 merge).</li></ul> | NFR-0.2 (32 lines of headroom: no new helpers here); launch header WHAT NOT TO DO 5 (no module-level constants) | W-2.2, W-4.2, W-5.1, W-8.2, W-10.1, FR-5.1 | P3, P4, P5 |
| 24 | MODIFY | `vidbyte/agents/infinite/workspace.py` | agent state | <ul><li>Add `map_snapshot() -> InfiniteMapSnapshot`, which recounts from disk as `map_text` does today (no caching, WHAT NOT TO DO 1).</li><li>Lift `map_text`'s cut loop into the static `fit_map_lines(header, lines)`, which returns the lines to show after the header, the last one `INFINITE_MORE_FILES` when cut. `map_text()` renders the snapshot through it with byte-identical output, and the runtime's status message uses it for the change lines (INV-7.3).</li><li>P4: `__init__` sets `self.full_text = FullTextIndex()` (opens nothing), the one index of INV-8.9.</li><li>Header: ARCHITECTURE NOTE, FUNCTION INVENTORY, and WHAT NOT TO DO 1 name `full_text` as the one held index, re-checked against file fingerprints before every search (EC-8.5 names the one blind spot).</li></ul> | workspace header WHAT NOT TO DO 1; AGENTS.md principle 5 (one cut rule for map and status); NFR-0.2 (68 lines of headroom) | W-7.1, W-8.2, FR-7.2, INV-7.3, INV-8.9 | P3, P4 |
| 25 | MODIFY | `vidbyte/agents/infinite/runtime.py` | agent runtime | <ul><li>Override `_build_system_string`, which calls `super()._build_system_string(context)` without the block.</li><li>`arun` draws the map once, sets `self._reported` from `map_snapshot()`, and, from P5, builds memory with `settings=self.settings`.</li><li>`_after_tool_iteration` diffs snapshots. When something changed, it renders the change lines through `InfiniteWorkspace.fit_map_lines` (the map's cap and `INFINITE_MORE_FILES`) into the `map_update` leaf, followed by the block; when nothing changed, the message is the block alone. The block is `self._render_loop_settings_block(iteration_count=state.iteration_count, tokens_used=state.tokens_used, tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts)))`, counted as at `vidbyte/agents/runtime.py:396-407`. It appends at most one user status message (INV-7.3) and updates `_reported` to the current snapshot even when lines were cut. The re-upsert is removed.</li><li>Update the `@intent` slug and comment, and the header (FUNCTION INVENTORY, WHAT NOT TO DO, KNOWN EDGE CASES for EC-7.3/7.4).</li></ul> | principle 2 (narrate `arun` and the hook); runtime-boundaries field guide; INV-R.6 (base hook unchanged) | W-7.1, FR-7.1, INV-7.1–7.6, AC-7.1, AC-7.2, AC-7.4, AC-7.5, NFR-7.2 | P3, P5 |
| 26 | MODIFY | `vidbyte/lib/dataclasses/infinite.py` | dataclass | Add `InfiniteMapSnapshot` (P3), and `InfiniteRecallRequest` and `InfiniteRecallCitation` with `parse` (P5), validated per §9.1. Add `__all__` entries. | Placement Rules; principle 4; precedent `lib/dataclasses/prompts.py:42` (`parse` classmethod); NFR-0.2; C006 (`entry_id`, `start`, and `end` through `RecordFieldValidator.require_int`) | W-7.1, W-10.2 | P3, P5 |
| 27 | MODIFY | `vidbyte/agents/infinite/memory.py` | agent tools | <ul><li>`InfiniteAgentMemory.__init__` gains required keyword `settings` and `self.recalled = 0`.</li><li>`tools()` adds the `INFINITE_RECALL_TOOL_NAME: InfiniteRecallTool` builder and passes `self.workspace.settings.recall_mode` to the registry.</li><li>Import `InfiniteRecallTool` from `vidbyte.agents.infinite.recall` for that builder entry. The class itself is row 57 (D-18).</li><li>Header: PURPOSE and FUNCTION INVENTORY name the `recall` builder and point to `recall.py` for the tool.</li></ul> | memory header recipe (`:7`); WHAT NOT TO DO 2–4; NFR-0.2 (149 lines of headroom, so the tool is in row 57, D-18) | W-10.2, FR-10.3 | P5 |
| 57 | CREATE | `vidbyte/agents/infinite/recall.py` | agent tool | <ul><li>A001 header (FILE through TESTS), naming `tests/features/infinite_memory_agent/test_infinite_memory_recall.py`.</li><li>`InfiniteRecallTool(BaseTool)` with `__init__(self, memory: InfiniteAgentMemory)`: spec from leaves with `metadata={"internal": True}`; `execute` narrated per FR-10.3, catching only `VidbyteSdkError`, `OSError`, and `ValueError` around the retriever. The citation check refuses any range whose resolved workspace-relative path has a part equal, case-folded, to one of `INFINITE_BOOKKEEPING_NAMES` (INV-10.5). The retriever's tools get `memory.workspace.full_text` (INV-8.9), and the card renders `{found}` last (INV-10.7). Each reply line is parsed on its own, and a `ConfigurationError` from `parse` becomes a `- reply line {n}: {reason}` rejected line (EC-10.7). The card is capped as INV-10.7 states, and the pre-search runs one `search_memory` search per term (INV-10.10).</li><li>`InfiniteAgentMemory` is imported only under `if TYPE_CHECKING:` (the module has `from __future__ import annotations`), so the run-time import edge runs memory to recall only.</li><li>No module-level constants; they live in `vidbyte/lib/constants/infinite.py`, as `memory.py` WHAT NOT TO DO 4 says.</li></ul> | AGENTS.md principle 3 (one subsystem per file, no import cycle); A001; A006 (`TYPE_CHECKING` edges skipped, `lint/rules/a006_directed_dependency_graph.py:74`, `:138`); memory header recipe; S019 (cancellation propagates); NFR-0.2 (at most 400 lines after the header) | W-10.2, FR-10.3–10.8 | P5 |
| 28 | MODIFY | `vidbyte/lib/registries/infinite.py` | registry | <ul><li>`tool_names(preset, role, recall_mode=InfiniteRecallMode.DIRECT)` appends `INFINITE_RECALL_TOOL_NAME` for ROOT and GENERATOR under DELEGATED.</li><li>New classmethod `withheld_tool_names(recall_mode, role)` returns `("grep",)` for ROOT and GENERATOR under DELEGATED, otherwise `()`. Both are table-driven `MappingProxyType` data.</li><li>Header.</li></ul> | registry header (policy as data; never import `agents`/`tools`); S021 | W-10.1, FR-10.2, AC-10.6 | P5 |
| 29 | MODIFY | `vidbyte/lib/enums/infinite.py` | enum | Add `InfiniteRecallMode(str, Enum)` with `DIRECT = "direct"` and `DELEGATED = "delegated"`, plus `__all__`. | Placement Rules (enums) | W-10.1, FR-10.1 | P5 |
| 30 | MODIFY | `vidbyte/lib/enums/__init__.py` | package exports | Import and add `InfiniteRecallMode` to `__all__` (`:80-86`, `~:223`). | Placement Rules ("every public enum is added to the export list") | W-10.1 | P5 |
| 31 | MODIFY | `vidbyte/__init__.py` | public API | Add `InfiniteRecallMode` to the docstring "Agent exports" (`:12`), the import, and `__all__` (`~:760`). | S015; C016 | W-10.1, AC-1 | P5 |
| 32 | MODIFY | `contracts/sdk-public-api.json` | generated contract | Regenerate with `python scripts/generate-sdk-public-api.py`. It gains `InfiniteRecallMode`. | C016; `local-ci-verification.md` | W-10.1 | P5 |
| 33 | MODIFY | `vidbyte/lib/enums/prompts.py` | enum | Add the 10 `Prompt` members after `:152`, each valued `"infinite_memory.<leaf>"`. P3: `INFINITE_MEMORY_MASKED_OUTPUT`, `INFINITE_MEMORY_MAP_UPDATE`. P5: `INFINITE_MEMORY_RECALL_TOOL_DESCRIPTION`, `INFINITE_MEMORY_RECALL_QUESTION_DESCRIPTION`, `INFINITE_MEMORY_RECALL_PURPOSE_DESCRIPTION`, `INFINITE_MEMORY_RECALL_KNOWN_DESCRIPTION`, `INFINITE_MEMORY_RECALL_TERMS_DESCRIPTION`, `INFINITE_MEMORY_RETRIEVER_SYSTEM_PROMPT`, `INFINITE_MEMORY_RETRIEVER_TASK_PROMPT`, `INFINITE_MEMORY_RECALL_CARD`. | prompt-families field guide | W-2.2, W-7.1, W-10.2, FR-10.7 | P3 (2 members), P5 (8 members) |
| 34 | CREATE | `vidbyte/prompts/prompts/infinite_memory/masked_output.md` | prompt leaf | The STRIP placeholder per INV-2.6, at most 60 tokens, with no number. | prompt-families; INV-0.3; NFR-2.1 | W-2.2, FR-2.2 | P3 |
| 35 | CREATE | `vidbyte/prompts/prompts/infinite_memory/map_update.md` | prompt leaf | The status message: says what changed in the workspace since the last report, then `{header}`, then `{changes}`. No number. | prompt-families; INV-0.3 | W-7.1, FR-7.1 | P3 |
| 36 | CREATE | `vidbyte/prompts/prompts/infinite_memory/recall_tool_description.md` | prompt leaf | The `recall` description, 4–5 sentences: asks a fresh helper to find memory; the answer is copied from the workspace; use it for questions that need several searches; it states what was not found. No number, no example. | model-facing-tool-contracts field guide; S025 does not resolve `prompts.get` | W-10.2 | P5 |
| 37 | CREATE | `vidbyte/prompts/prompts/infinite_memory/recall_question_description.md` | prompt leaf | 4–5 sentences on `question`. | same | W-10.2 | P5 |
| 38 | CREATE | `vidbyte/prompts/prompts/infinite_memory/recall_purpose_description.md` | prompt leaf | 4–5 sentences on `purpose`. | same | W-10.2 | P5 |
| 39 | CREATE | `vidbyte/prompts/prompts/infinite_memory/recall_known_description.md` | prompt leaf | 4–5 sentences on `known`. | same | W-10.2 | P5 |
| 40 | CREATE | `vidbyte/prompts/prompts/infinite_memory/recall_terms_description.md` | prompt leaf | 4–5 sentences on `terms`. | same | W-10.2 | P5 |
| 41 | CREATE | `vidbyte/prompts/prompts/infinite_memory/retriever_system_prompt.md` | prompt leaf | The retriever's operating manual: find, read only what the question needs, and end with only the three line forms (§9.2). It writes no memory and states no number. | prompt-families; INV-0.3; CODING_ONLY_WORDS check (contract test `:455-459`) | W-10.2, FR-10.5 | P5 |
| 42 | CREATE | `vidbyte/prompts/prompts/infinite_memory/retriever_task_prompt.md` | prompt leaf | The retriever's first message, with `{question}`, `{purpose}`, `{known}`, `{hits}`. | same | W-10.2, INV-10.10 | P5 |
| 43 | CREATE | `vidbyte/prompts/prompts/infinite_memory/recall_card.md` | prompt leaf | The card, with `{question}`, `{not_found}`, `{rejected}`, `{searches}`, then `{found}` last, so the card cap cuts transcribed text first (INV-10.7). | same | W-10.2, NFR-10.1, AC-10.7 | P5 |
| 44 | MODIFY | `vidbyte/prompts/prompts/infinite_memory/infinite_memory.json` | prompt registry | Add the 10 entries (`path`, and `source_url` in the existing URL pattern). Extend `description` to name the masking placeholder, the map update, the retriever, the recall card, and `recall`. | prompt-families; C015 (`*/*.md` already ships) | FR-10.7 | P3, P5 |
| 45 | MODIFY | `vidbyte/prompts/prompts/infinite_memory/map_header.md` | prompt leaf | "found with grep" becomes "found with search_memory or grep". | request.md §C (prompt edits where an item needs them) | W-8.2, FR-8.8 | P4 |
| 46 | MODIFY | `vidbyte/prompts/prompts/infinite_memory/root_system_prompt.md` | prompt leaf | <ul><li>P4: line 7, memory search names `search_memory` first.</li><li>P3: lines 39-47, passed and fixed cards show the finished line plus the summary.</li><li>P3: line 51, the map is drawn at the start, and changes arrive in a short update after each tool call; P4 adds `search_memory` to that line.</li><li>P3: line 64, reads come in windows; continue from the line the footer names.</li><li>P5: when `recall` is held, use it for questions that need several searches.</li><li>One clause each, no numbers.</li></ul> | INV-0.3; request.md §C (minimal edits; another branch rewrites the family) | W-2.2, W-5.1, W-7.1, W-8.2, FR-8.8, FR-10.8 | P3, P4, P5 |
| 47 | MODIFY | `vidbyte/prompts/prompts/infinite_memory/generator_system_prompt.md` | prompt leaf | P4: line 9, `search_memory`. P3: line 20, compact cards. P3: line 26, the map is drawn at start; P4 adds `search_memory` there. P5: the recall clause. | same | W-5.1, W-8.2, FR-10.8 | P3, P4, P5 |
| 48 | MODIFY | `vidbyte/prompts/prompts/infinite_memory/verifier_system_prompt.md` | prompt leaf | Lines 11 and 29: name `search_memory` beside grep. | same | W-8.2, FR-8.8 | P4 |
| 49 | MODIFY | `vidbyte/prompts/prompts/infinite_memory/launch_tool_description.md` | prompt leaf | "How it behaves": a passed or fixed pair's card is its finished line and summary, and other cards are in full. | same; S025 is not resolved for leaves | W-5.1 | P3 |
| 50 | MODIFY | `vidbyte/agents/infinite/README.md` | folder README | <ul><li>Lines 28 and 40: tools, now including `search_memory` and, under DELEGATED, `recall`. Line 40 keeps "No semantic or vector search", now "agents use `search_memory`, `grep`, and `read_lines`".</li><li>Line 58: the map is drawn once, plus status messages.</li><li>Lines 60-81: the limits table, with read window, masking, hysteresis, recall caps, and the restated budget sum.</li><li>Notes: one line on the status message and one on DELEGATED. Line 111 ("one tool output larger than that is dropped whole") is restated per EC-4.2: with hysteresis, a newest group larger than the budget drops every non-system group.</li><li>Stay ≤ 40,000 characters. File Index (S020): add `recall.py`, "the `recall` tool, `InfiniteRecallTool`, which runs a fresh retriever and copies what it cites from disk"; the `memory.py` line stays true.</li></ul> | AGENTS.md (README read to the end; Notes for agents); A009; S020 | W-0.1 | P3–P5 |
| 51 | MODIFY | `vidbyte/agents/README.md` | folder README | Line 146: bash keeps the first and the last bytes. Line 177: InfiniteMemory agents also hold `search_memory`. | A009 | W-0.1, W-6.1 | P2, P4 |
| 52 | MODIFY | `vidbyte/tools/README.md` | folder README | Line 91: `InfiniteMemoryAgentTools` adds `search_memory`. Line 89: code search lists `search_memory`. Add one line on `GrepTool`'s new options and the read window. | A009 | W-0.1 | P1, P4 |
| 53 | MODIFY | `vidbyte/providers/README.md` | folder README | Anthropic section: repeat-gated block-level `cache_control`, never top-level, no `ttl`, and that the caller's own marks disable it. | A009 | W-0.1, W-9.1 | P2 |
| 54 | MODIFY | `vidbyte/lib/README.md` | folder README | Line 48: list `FullTextIndex` among the util helpers. | A009 | W-0.1, W-8.1 | P1 |
| 55 | MODIFY | `vidbyte/prompts/README.md` | folder README | Line 67: list the 10 new leaves. Lines 229-250: the family section names the new texts. | A009; prompt-families | W-0.1 | P3, P5 |
| 56 | MODIFY | `lint/baseline.json` | lint baseline | Lower `A007` from 255 to 254 with `python lint/run.py --rule A007 --update-baseline`, only after `lint/run.py` reports A007 IMPROVED. Lower any other IMPROVED count the same way. Never raise one. | lint ratchet; §14 | NFR-0.3 | P1 (and re-check at the end) |

### 12.4 Standards checklist for this change

- [ ] Every new dataclass is `@dataclass(frozen=True, slots=True)`, lives in `vidbyte/lib/dataclasses/<domain>.py`, validates every field in `__post_init__`, and raises `ConfigurationError` naming the field and the bad value. — *source:* AGENTS.md principle 4, Placement Rules
- [ ] `InfiniteRecallMode` lives in `vidbyte/lib/enums/infinite.py` and is exported from `vidbyte/lib/enums/__init__.py` and `vidbyte/__init__.py`. — *source:* AGENTS.md Placement Rules; C016
- [ ] New settings fields are appended last, validated with `RecordFieldValidator`/`RecordFieldConverter` (no local helper), and have named defaults in `vidbyte/lib/constants/infinite.py`. — *source:* settings.py header; `strict-config-dataclasses.md`; `local-ci-verification.md`
- [ ] Each new `.py` file (`windows.py`, `fulltext.py`, `search_memory.py`, `recall.py`) opens with the A001 header: FILE, PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS, WHAT NOT TO DO IN THIS FILE, KNOWN EDGE CASES, RELATED DOCS, TESTS. — *source:* lint A001; exemplar `vidbyte/tools/builtins/bash.py:1-13`
- [ ] Every main function this PR adds or changes is narrated in plain-English comments, and comments of changed steps are updated in the same edit. This covers `ReadLinesTool.execute`, `BashTool.execute`, `GrepTool.execute`, `InfiniteSearchMemoryTool.execute`, `InfiniteRecallTool.execute`, `InfiniteMemoryRuntime.arun` and `_after_tool_iteration`, `AnthropicProvider._attach_cache_breakpoints`, and `TrimWithProviderBoundariesCompaction.compact`. — *source:* AGENTS.md principle 2
- [ ] Call chains are one level deep, and no function is defined inside another in changed code. The trim's nested `cost` becomes a method. — *source:* AGENTS.md principle 1
- [ ] Comment blocks wrap at 72 columns, and every `@intent <slug>` sits within 20 lines of its `def`. Run `python lint/run.py --rule A002` and add markers where it reports new findings. — *source:* `comment-format.md`; lint A002
- [ ] No numeric literal default on a parameter whose name holds timeout/retry/attempt/backoff/delay/token/char/byte/truncate/limit/budget/status/depth/interval. Use an UPPERCASE constant. — *source:* lint A007
- [ ] Nothing in `vidbyte/lib/` imports from `vidbyte/tools/`, `vidbyte/middleware/`, `vidbyte/agents/`, or `vidbyte/prompts/`. `vidbyte/tools/` never imports `vidbyte.agents`. `windows` imports `strategies`, never the reverse. — *source:* AGENTS.md principle 3; lint A006; toolset header
- [ ] No prompt leaf states a number. Every cap is a constant plus a code check, and its refusal names it. — *source:* `vidbyte/agents/infinite/README.md` "Where each limit is enforced"; `prompt-families.md`
- [ ] Every new prompt leaf is registered in `infinite_memory.json` and keyed by a `Prompt` member. — *source:* `prompt-families.md`; memory.py header recipe
- [ ] Literal tool descriptions (`search_memory`, bash) have at least 4 sentences, and no new S025 finding appears. — *source:* lint S025; `model-facing-tool-contracts.md`
- [ ] No `open()`/`Path.read_text` call sits directly inside an `async def`. File reads go in sync helpers, and `search_memory` runs its file reads and SQLite calls through `asyncio.to_thread`, as `SemanticSearchTool` does. — *source:* lint S047; `vidbyte/tools/builtins/code_search/semantic.py:78-81` (S047 and S052 do not cover `sqlite3`)
- [ ] No new C006 finding. Every new numeric range guard (`low_watermark_tokens`, `context_lines`, `FullTextMatches.total`, the `InfiniteRecallCitation` id and lines, and `FullTextIndex.search`'s `limit` and `snippet_tokens`) uses `RecordFieldValidator.require_int` or the shape `isinstance(x, bool) or not isinstance(x, int) or x < bound`. Run `python lint/run.py --rule C006`. — *source:* lint C006 (`lint/rules/c006_finite_numeric_guards.py`, baseline 104); NFR-0.3
- [ ] Async code never swallows `CancelledError`. `recall` catches only `VidbyteSdkError`, `OSError`, and `ValueError`. — *source:* lint S019; `launch.py` precedent
- [ ] Every `vidbyte/agents/infinite/` module stays at or under 400 lines after its header, and the package has at most 9 `.py` files, its 8 plus `recall.py` (D-18). `lib/constants`, `lib/enums`, `lib/dataclasses/infinite.py`, and `tools/toolsets/infinite.py` stay under 400 too. — *source:* `test_infinite_memory_contract.py:471-479` at base; the budget test is deliberately changed to 9 files and 13 modules (§13)
- [ ] Every file edited stays under 1,000 lines, and `strategies.py` ends below 1,000. — *source:* AGENTS.md principle 3
- [ ] Each changed module header (ROLE, ARCHITECTURE NOTE, FUNCTION INVENTORY, WHAT NOT TO DO, KNOWN EDGE CASES) still describes the code. — *source:* lint A001 practice; module headers
- [ ] Each folder README touched stays ≤ 40,000 characters, and its "Notes for agents" was read before editing. — *source:* AGENTS.md; lint A009
- [ ] `contracts/sdk-public-api.json` is regenerated and `--check` passes. — *source:* lint C016; `local-ci-verification.md`
- [ ] New files are `git add`ed before the local gate, so Semgrep scans them. — *source:* `local-ci-verification.md`
- [ ] No suppression comments (`noqa`, `type: ignore`, lint skips) are added, and no baseline count rises. — *source:* lint S035/S037/S038; orchestrator constraints

### 12.5 Non-code actions

- Update the README lines of rows 50–55. — `vidbyte/agents/infinite/README.md`, `vidbyte/agents/README.md`, `vidbyte/tools/README.md`, `vidbyte/providers/README.md`, `vidbyte/lib/README.md`, `vidbyte/prompts/README.md` — *source:* AGENTS.md (folder READMEs document the folder)
- Regenerate the public API contract. — `contracts/sdk-public-api.json` — *source:* C016
- Ratchet the lint baseline down. — `lint/baseline.json` — *source:* lint ratchet
- Add exports in `__init__` — `vidbyte/__init__.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/util/__init__.py`, `vidbyte/tools/builtins/code_search/__init__.py`. *Source:* Placement Rules and S015.
- PR body: list the SDK-wide behavior changes (§9.4), which are bash head+tail and Anthropic repeat-gated marks. List the deliberately changed tests by name (§13). Note that `REPO_MAP.md`, `llms.txt`, and `artifacts/file_index.md` need no change: verified that none lists these files or the moved classes, nor the package's modules, so the new `recall.py` needs no entry there either. *Source:* request.md Q-ORCH-5; `agents-md-map.md`.
- After merge, outside this PR's gate, run a real-key InfiniteMemory root run on an Anthropic model, direct and through the gateway. Record `cache_read_input_tokens` per call against NFR-0.5. Record whether DELEGATED roots search in fewer calls (Q-1), which is the measurement Q-ORCH-1 defers to. Count how often the root's first kept history message changes, against the growth (EC-4.3), which is the measurement Q-11 defers to. *Source:* request.md §B.1 item 10 and Q-ORCH-1.
- Nothing applies for: `.env.example` (no new variable), the changelog (the repo keeps none per AGENTS.md), `llms.txt`, and `REPO_MAP.md`.

### 12.6 Phases and dependency order

Each phase leaves the package importable and the full gate green, except the deliberately changed tests that §13 names for that phase. The test author updates those against the spec IDs.

**P1 — SDK options with no-change defaults** (ships: `max_read_lines`, the masking scope, hysteresis, grep options, `FullTextIndex`, and the `windows` split). Every default equals `main`, so every agent behaves exactly as on `main`. Rows 1–13, 52 (grep/read lines part), 54, 56.

**P2 — SDK-wide behavior changes** (ships: bash head+tail and Anthropic cache marks). This is the first observable change for non-InfiniteMemory agents. Deliberately changed tests: the bash group and the run-boundary test in §13. Rows 14, 15, 51 (line 146), 53.

**P3 — InfiniteMemory wiring for items 1–5 and 7** (ships: read windows, masking, smart grep, hysteresis, compact cards, and the stable root prefix). Deliberately changed tests: the card, map, and leaf-count tests in §13. Rows 16 (items 1–7 constants), 17 (`max_read_lines`), 18 (window and grep options), 22 and 23 (without P4 and P5 parts), 24 (snapshot and `fit_map_lines`), 25 (without the memory `settings`), 26 (`InfiniteMapSnapshot`), 33 (2 members), 34, 35, 44 (2 entries), 46, 47, and 49 (P3 clauses), 50, 55.

**P4 — `search_memory`** (ships: ranked memory search on every agent). Deliberately changed tests: the tool-set tests in §13. Rows 16 (search constants), 18 (fourth tool and `index`), 19, 20, 21, 22 and 23 (the `index` argument), 24 (`full_text`), 45, 46–48 (P4 clauses), 51 (line 177), 52 (`search_memory` part), 50.

**P5 — opt-in `recall`** (ships: `InfiniteRecallMode` and delegated recall). With DIRECT, the default, the behavior equals P4. Deliberately changed tests: leaf count 50, the registry signature tests, and the complexity-budget test (9 files, 13 modules; D-18). Rows 16 (recall constants), 17 (`recall_mode`), 22, 23 (withheld filter and settings), 25 (memory `settings`), 26 (recall records), 27–33, 57, 36–44, 46, 47 (P5 clauses), 50 (with the File Index entry), 55.

**Dependency order:**

- P1 → P3 → P4 → P5.
- Within P1: row 1 before row 3; rows 4–5 before rows 6–8; rows 9–10 independent; rows 11–13 independent of the rest.
- Row 26 (records) and rows 28–30 before rows 57 and 27 (recall). Row 57 (the tool) before row 27 (its builder entry, which imports it). Row 33 before rows 34–43 are read by code.

**Independent:**

- P2 depends on nothing in P1, P3, P4, or P5 and may land at any point.
- Rows 14 and 15 are independent of each other.
- Rows 50–55 can be written alongside their phases.

---

## §13 Test seams (facts for the test author — no tests here)

- **Framework:**
  - pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48-49`), run with `--strict-config --strict-markers` (`pyproject.toml:78-80`, `testpaths = ["tests"]`).
  - The compaction, filesystem, code-search, and managed-wire modules are `unittest.TestCase` classes collected by pytest.
  - The InfiniteMemory pack is plain pytest functions.
- **Layout and naming:**
  - Shared SDK pieces have root-level `tests/test_<area>.py` files.
  - Feature packs live under `tests/features/<feature>/`, each with `FEATURE.md`, `README.md`, and a fixtures module. The InfiniteMemory files are named `test_infinite_memory_<area>.py`.
  - Contract tests pin exact sets and counts (`EXPECTED_LEAVES`, `PRESET_TOOLS`, `BUDGET_MODULES`).
  - The field guide says no test pins a cap with a literal, so import the `INFINITE_*`, `BASH_*`, `GREP_*`, and `ANTHROPIC_*` constants.
- **Prior art to copy, per item:**
  - Item 1: `tests/test_filesystem_tools.py` (read_lines and the overwrite cap, including `test_read_lines_returns_selected_lines_newline_joined`).
  - Items 2 and 4: `tests/test_deterministic_compaction_middleware.py` and `tests/test_context_compaction_middleware.py`.
  - Item 3: `tests/test_code_search_tools.py`.
  - Item 6: `tests/features/coding_agent/test_bash_tool_contract.py` and `test_bash_tool_process_bounds.py`.
  - Item 8, the helper: `tests/test_folder_usage.py` (a lib helper over a real tmp folder).
  - Item 9: `tests/test_output_schema_provider_dialect.py:143`, which calls `AnthropicProvider(model=..., api_keys=[...], mode=TextModelMode.DIRECT)._create_payload(config, prompt, None, None)` directly. Also `tests/features/sdk_managed_text/test_managed_text_wire_contract.py`, the `EMITTED_KEYS` oracle at `:49` and `:172-185`.
  - Items 5, 7, 8, and 10: `tests/features/infinite_memory_agent/test_infinite_memory_delegation.py` and `test_infinite_memory_workspace.py`.
- **Fixtures / factories:**
  - `tests/features/infinite_memory_agent/infinite_memory_fixtures.py` (556 lines):
    - `ScriptedTree` replaces `BaseAgent._runner_for_model` and records each call's prompt, `system`, `messages`, and tools per agent name. It has `install()`, `calls_by(agent)`, and `assert_complete()`.
    - Name helpers: `ROOT = "analyst"`, `generator(name)`, `verifier(name)`. Children are named `f"{settings.name}/{memory.key}"`. The retriever will be named `f"{settings.name}/{memory.key}/recall"`, for example `analyst/root/recall`, so a test scripts it by that name.
    - Helpers: `map_section`, `prompt_text(leaf)`, `renderings`, `tool_results` (role `"tool"`), `finished_cards`, `workspace_root`, `write_jsonl`, `entry_record`, and `build_agent`.
  - `tests/features/coding_agent/conftest.py`: `bash_module`, `coding_agent_cls`, `script_model`, and `fake_provider_http`.
- **Real seams (do not mock):**
  - the filesystem (`tmp_path`);
  - the bash subprocess (POSIX bash, or Git for Windows bash on Windows);
  - stdlib `sqlite3` with FTS5;
  - the `Prompts` catalog and the leaf files;
  - the compaction engine and middleware;
  - `InfiniteWorkspace` and its caps.

  Only the model is scripted (`ScriptedTree`, `script_model`), and provider HTTP is faked at the transport, or `_create_payload` is called directly. A missing FTS5 is simulated only at the `FullTextIndex` table-creation seam, its first use (AC-8.4). AC-8.7 counts `FullTextIndex` constructions at the same class.
- **Where new behavior is observable:**
  - **The status message** (INV-7.3) is a `{"role": "user", "content": ...}` entry. It appears in the root's recorded `messages` after the tool results of the iteration that produced it.
  - **The root's recorded `system`** is the stable string of INV-7.1.
  - **Masking** shows in the per-call `messages` a model call receives. Raw history is not observable through `ScriptedTree`.
  - **Anthropic marks** show only on a second `_create_payload` call on the same adapter instance with the same tools and system.
  - **The shared index** (INV-8.9) is `InfiniteWorkspace.full_text`; every agent's `search_memory` in one tree uses it.
- **Existing tests whose asserted behavior this PR deliberately changes** (request.md Q-ORCH-5; the test author updates each against the cited ID; the implementer never edits them):
  - `tests/features/coding_agent/test_bash_tool_contract.py::test_large_output_keeps_the_first_bytes_counts_the_rest_and_memory_stays_bounded` (`:173`): the output is now head, marker, tail (INV-6.2, INV-6.3). The bounds tuple test at `:74` stays green, because the four constants are unchanged.
  - `tests/features/coding_agent/test_bash_tool_process_bounds.py::test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker` (`:241`): the timeout marker and the tail (INV-6.4). The file patches `BASH_MAX_OUTPUT_BYTES` to `SMALL_CAP_BYTES = 1000` (`:41`, `:244`); with T = `min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES // 2)` that cap keeps a 500-byte head and a 500-byte tail. A test that wants other sizes patches `BASH_TAIL_OUTPUT_BYTES` as well; both are module globals read at call time (INV-6.5).
  - `tests/features/coding_agent/test_coding_agent_verify_command.py` `:361-367`: the feedback ends with head, marker, tail, exit code (EC-6.4).
  - `tests/features/coding_agent/FEATURE.md:23`: the bash output description (INV-6.2).
  - `tests/test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire` (`:238`), the Anthropic subtest only (P2):
    - In the 2nd, 3rd, and 4th Anthropic requests the task is the message right before the newest assistant turn, so it is marked. It goes out as `{"role": "user", "content": [{"type": "text", "text": TASK, "cache_control": {"type": "ephemeral"}}]}` (INV-9.3, EC-9.10).
    - The helper `_task_and_first_call` (`:128`) finds the task only by `turn.get("content") == TASK`, so it must also accept that one-block form.
    - The assertions stay as they are: exactly one task turn, before the first call turn (index 1 before index 2 in each of those requests). The DeepSeek and Gemini subtests are unchanged.
  - `tests/features/infinite_memory_agent/test_infinite_memory_delegation.py`:
    - `:134`: a passing batch now renders compact cards, not 2 `result_card` renderings (INV-5.1).
    - `:63-65`: `MEMORY_TOOLS`, `GENERATOR_TOOLS`, and `VERIFIER_TOOLS` gain `search_memory` (FR-8.1).
  - `tests/features/infinite_memory_agent/test_infinite_memory_contract.py`:
    - `:49` and `:178-185`: `EXPECTED_LEAVES` grows from 40 to 50 leaves (FR-10.7).
    - `:118` and `:373`: `PRESET_TOOLS` gains `search_memory` (FR-8.1).
    - `test_new_modules_stay_inside_the_complexity_budget` (`:471-479` at base, `:483-491` at 5e930f3b) and `BUDGET_MODULES` (`:104-117` at 5e930f3b), in P5. The package bound becomes `len(list(package.glob("*.py"))) <= 9`. `BUDGET_MODULES` gains `"vidbyte/agents/infinite/recall.py"`, so 13 modules are each checked at `<= 400` lines after the header. The docstring and the `BUDGET_MODULES` comment then say 9 package modules and 13 new modules (D-18, NFR-0.2).
  - `tests/features/infinite_memory_agent/test_infinite_memory_workspace.py::test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration` (`:340-372`): the root's later system map no longer changes, and the change arrives as a status message (INV-7.2, INV-7.3).
  - `tests/features/infinite_memory_agent/FEATURE.md`, where it describes the root's map redraw, the card shape, or the tool set.
- **Tests that must stay green unchanged (checked against the design):**
  - `test_infinite_memory_context.py:46` patches the agent module's `INFINITE_HISTORY_MAX_TOKENS` to 250. With L ≥ M the trim keeps today's algorithm (D-6, EC-4.4). Its four `fetch_page` iterations change nothing in the workspace, so each status message is the loop-settings block alone, about 33 tokens (INV-7.3). Review round 2 replayed the test and found the pass threshold for that message at roughly 110 tokens (R-13).
  - `test_infinite_memory_delegation.py:305-316` and `:545-549` exercise a passed card (its summary is still shown) and an `unchecked` card (still full, four markers).
  - `test_infinite_memory_contract.py:378-390` (registry coverage) calls `tool_names(preset, role)` with the DIRECT default, so the result is unchanged.
  - The coding-agent tests that read `requests[0]["system"]` read runner kwargs of the first request, not a repeat Anthropic body (A-5).
  - Every other existing test keeps its result under INV-9.1–9.7. r4 checked this by running the full existing suite against a scratch prototype of the marks (A-5).
  - `test_infinite_memory_recall.py:203` imports `InfiniteRecallTool` from `vidbyte.agents.infinite.memory`. That import keeps working, because `memory.py` imports the class for its builder table (D-18). The class is defined in `vidbyte.agents.infinite.recall`; switching the import is optional.
  - `test_managed_text_wire_contract.py:181` is unchanged, because no top-level key is added (INV-9.7).
- **Known pre-existing failures:** the `harness_threads` tests fail on any branch that touches `vidbyte/tools`. Never edit them (field guide `local-ci-verification.md`).
- **Per-area config:**
  - None beyond `pyproject.toml`.
  - The InfiniteMemory pack README (`tests/features/infinite_memory_agent/README.md:24`) runs it with `PYTHONPATH=$(pwd)`.
  - Bash cases need a POSIX bash, or Git for Windows bash.
  - The changed endless-printer test in `test_bash_tool_process_bounds.py` is POSIX-only. A Windows run skips it, so its proof of INV-6.4 is the Linux CI run.
- **Run one file:** `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_contract.py -q`
- **Run all:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`.

## §14 Agent boundaries

- **Always:**
  - Work only in `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-context-economy`.
  - Build phase by phase (§12.6). After each W item, run the focused tests (§11) and `python lint/run.py`.
  - `git add` new files before the gate.
  - Before pushing, run `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` without `PYTHONPATH`, then `python scripts/generate-sdk-public-api.py --check`.
  - Cite W-, FR-, and INV- IDs in commit messages.
  - Keep edits to `vidbyte/agents/infinite/runtime.py` and `launch.py` minimal and local, because PR #1159 must merge with them later.
  - Use the exact names of §4 and §8.5.
  - Shell commands carry a timeout and `</dev/null`, and git runs with `GIT_TERMINAL_PROMPT=0 GIT_EDITOR=true`.
- **Ask first (stop and report BLOCKED):**
  - **never modify a test file**, including every file under `tests/` such as `FEATURE.md` and the deliberately changed tests of §13; the test author owns them;
  - exceeding the §8.4 budget, a 10th module in `vidbyte/agents/infinite/` (D-18 allows 9), or any budget module over 400 lines after its header;
  - a new dependency;
  - touching a file not in §12.3;
  - changing a public contract beyond §9.2/§9.4;
  - adding an `InfiniteAgentRole` member (Q-9);
  - changing a prompt leaf beyond the clauses §12.3 names;
  - any change that needs the gateway (backend) repo.
- **Never:**
  - raise a `lint/baseline.json` count or add a suppression (`noqa`, `type: ignore`, lint skips);
  - delete, skip, or weaken a test;
  - edit the main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` or the backend repo `C:/Users/422mi/vidbyte-repos/vidbyte/backend`;
  - run a bare `git stash`;
  - push to `main`;
  - implement any Q-n whose default is no, or anything outside §12;
  - add run events (NG-6);
  - install `DeduplicateToolCallsCompaction` on an InfiniteMemory agent (NG-5);
  - send a top-level `cache_control` or a `ttl` (INV-9.1, INV-9.3);
  - mutate a caller's messages (INV-9.5);
  - state a number in a prompt leaf (INV-0.3);
  - read under `docs/` beyond the files the orchestrator named.

## §15 Assumptions and open questions

**Assumptions** (stand unless the user corrects them):

- **A-1** — The Python on Linux CI (ubuntu-latest) has `sqlite3` built with FTS5. The Windows dev Python (SQLite 3.38.4) and CPython's Windows and macOS builds do (request.md §C); the Linux one is unverified. — *If wrong:* the CI runs of the FTS5 tests fail. Runtime behavior is already safe (INV-8.7), and the user decides how CI gets FTS5. Tests are never skipped to hide it.
- **A-2** — Every supported provider accepts a plain user message right after tool results, because the base runtime already appends review feedback there (`vidbyte/agents/runtime.py:670`), and Anthropic combines consecutive user turns. — *If wrong:* D-9 flips to another placement for the status message.
- **A-3** — The retriever's reply (`AgentMessage`) carries `metadata["tool_calls"]` as `ToolCallContext` items with `.tool_name` and `.arguments` (`vidbyte/agents/runtime.py:2125`). — *If wrong:* the card's searches list shows only the pre-search terms; nothing else changes.
- **A-4** — Anthropic prompt caches are isolated per organization, and gateway customers share Vidbyte's organization (T-4). — *If wrong (narrower isolation):* the T-4 residual risk disappears.
- **A-5** — (restated in r4, S2 defect 1) Apart from the run-boundary test that §13 names, no existing test reads the `system` of a repeat Anthropic body, or the content of a message the marks convert, as a string. The r3 grep checked only `system`, and missed that the task prompt is a string message that INV-9.3 converts when it is marked. r4 ran the full existing suite (6,378 tests collected) against a scratch prototype of INV-9.1–9.7, a patched `_create_payload` that is not committed. Exactly that one test went from green to red, and no other existing test changed result. — *If wrong:* that test joins the §13 deliberately changed list.
- **A-6** — The gateway forwards block-level marks inside `system` and `messages` to Anthropic unchanged. Admission and forwarding are verified in backend code (`backend/provider/generative_models/client.py`): `_require_short_cache` (`:260-278`) admits them, `plan()` builds `wire = {**body, "model": request.model}` (`:176`), and `send()` posts `plan.wire` (`:195`); `tests/features/model_gateway/test_generative_gateway_refusals.py:289` and `generative_gateway_fakes.py:102` show `system` as a list of blocks. Not verified with a live key. — *If wrong:* gateway runs get no cache hits, but no 422 either, and G-4 holds only for DIRECT mode.
- **A-7** — Anthropic ignores a mark on a prefix shorter than the model's minimum cacheable length, without error or charge (vendor docs, request.md §C). — *If wrong:* small repeat prefixes pay a small write premium once per prefix.
- **A-8** — Under DELEGATED, the root and generators keep `search_memory` as well as `read_lines`. request.md §C says only that they "lose `grep`, keeping `read_lines` for known paths", and the DIRECT row lists `search_memory` as an ordinary tool. — *If wrong:* Q-10 flips and `withheld_tool_names` also names `search_memory`.
- **A-9** — A recall quota of 10 per agent and at most 8 pre-search terms are generous starting values. The conversation set that a quota and a turn cap exist ("a per-agent quota and the turn cap bound it") but not the quota's value. 8 iterations is the conversation's "~8". — *If wrong:* change the two constants; no design change.
- **A-10** — The status message's loop block can reuse the base `_render_loop_settings_block` unchanged. It reads `self.config` limits and the live counters passed in, exactly as the system-string path does today (`vidbyte/agents/runtime.py:1596-1604`, `:1679-1700`), with the tool count taken as `len(self._non_internal_tool_contexts(state.call_contexts))`, as at `:406`. — *If wrong:* the runtime renders the same lines from its own copy, which costs one more helper in `runtime.py`.

**Open questions** (max 5 blocking):

| ID | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| Q-1 | (Q-ORCH-1) Build delegated `recall` in this PR even though §B.1 listed it under "only if measurement says so"? | non-blocking | **Yes, built opt-in**: DIRECT is the default, so no run changes unless the developer sets DELEGATED. The real-key measurement in §12.5 decides any later default. |
| Q-2 | Extend the stable prefix (no loop block in the system string, map drawn once, status messages) to generators, verifiers, and the retriever? | non-blocking | No (NG-1). |
| Q-3 | Move the loop-settings block out of the system string for every SDK agent? | non-blocking | No (NG-2). |
| Q-4 | Give the model-facing `compact_context` tool the new `tools` scope? | non-blocking | No (NG-8). |
| Q-5 | Rewrite the base `grep` and `read_lines` descriptions to the field guide's 4–5 sentences for every agent? | non-blocking | No (NG-10). |
| Q-6 | Add a canonical `vidbyte/lib` head/tail helper and adopt it in the three existing implementations? | non-blocking | No (NG-11). |
| Q-7 | Batch masking, for example masking only once a minimum number of tokens can be cleared, to cut the per-masking cache miss of EC-2.3? | non-blocking | No. |
| Q-8 | When the AND search finds nothing, retry with OR? | non-blocking | No. |
| Q-9 | request.md §C names "new role RETRIEVER". Add an `InfiniteAgentRole.RETRIEVER` member? | non-blocking | **No.** The retriever is built without a role (D-14), because a role member would either grant it `remember`/`write_note` or break the tested invariant that every role holds them (`test_infinite_memory_contract.py:383-387`). |
| Q-10 | Under DELEGATED, should the root and generators lose `search_memory` too, keeping only `recall` and `read_lines`? | non-blocking | No (A-8). |
| Q-11 | (Review R-6) Make the trim's cut monotone within a run, keeping the last multiple in `run_state` under a private key class and moving it only forward, so masking can never move the cut back (EC-4.3)? | non-blocking | No. The stateless cut ships, and the real-key trace (§12.5) counts cut moves per root run to decide. |
| Q-12 | (Review R-13, scope-adding) Mask every status message except the newest, with the same placeholder mechanism, so stale loop counters and change lines stop taking history? | non-blocking | No, not built. A no-change status message is already only the loop-settings block (NFR-7.2). |

## §16 Review log

| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|
| 1 | R-1 | Blocker | §12.3 rows 4, 10, 11, 26; checklist | New numeric guards in the `x < 0` shape would raise C006 above its baseline of 104. | Accepted | Rows 4, 10, 11, 12, and 26 name C006 and the safe guard (`RecordFieldValidator.require_int`/`require_bool`, or `isinstance(x, bool) or not isinstance(x, int) or x < bound`); §9.1 states it for the records; the checklist (§12.4; the review said §14) gains "No new C006 finding". Checked with `lint/run.py --rule C006 --all`: the moved classes' findings (`strategies.py:599`, `:601`, `:670`) move with them, and the history middleware's option loop is not a C006 site. |
| 1 | R-2 | Blocker | §6.2 AC-4.1, AC-4.2 | Both P0 trim ACs contradicted INV-4.2's quantized cut. | Accepted | AC-4.1 fixes B = 90,000, groups ≤ 500 tokens, kept in (65,500, 66,000]; AC-4.2 appends at most 24,000 tokens so the ceiling stays 1. |
| 1 | R-3 | Major | §6.1 INV-7.3, EC-7.7 | The root's status message was uncapped, and its per-iteration overhead was unstated. | Accepted | `{changes}` is capped by the map's own constants (`INFINITE_MAP_MAX_TOKENS`, `INFINITE_MORE_FILES`) through `InfiniteWorkspace.fit_map_lines`, lifted from `map_text` with byte-identical map output; no new constant or mechanism. INV-7.4 advances the baseline; new EC-7.8, AC-7.4 (P0), NFR-7.2; EC-4.2, EC-7.7, rows 24 and 25 updated. |
| 1 | R-4 | Major | §6.1 INV-10.5, EC-10.2 | A range citation could transcribe superseded memory, raw entry JSON, or run journals as found. | Accepted | New `INFINITE_BOOKKEEPING_NAMES`, shared by `search_memory`'s ignore patterns and the citation check (any path part, case-folded); entries only by `#id`. INV-10.5, EC-10.2, AC-10.4, T-2, rows 16, 20, 27. |
| 1 | R-5 | Major | §8 D-11, §9.1, rows 12, 20 | The index was one per tool instance and ran on the event loop. | Accepted | One lazy `FullTextIndex` per workspace (`InfiniteWorkspace.full_text`, the request's "per workspace"), passed as `index` through `InfiniteMemoryAgentTools`/`get_tools`; refresh and search run in `asyncio.to_thread` under the index's `RLock` (precedent `semantic.py:78-81`). New INV-8.9, AC-8.7; FR-8.1, FR-8.4 (construction never fails, first use raises), D-11, §5, §8.4, §8.5, §9.1, §9.2, EC-8.4, rows 12, 18, 20, 22–24, 27, §12.6, §13. |
| 1 | R-6 | Major | §6.3 EC-4.3, §7 NFR-4.1, §6.1 INV-4.4 | Masking ahead of the trim lets the cut dip back: two full writes per dip, not one. | Accepted; the optional monotone cut became Q-11 | EC-4.3 restated (two writes per dip, about net drop / S per masking event); NFR-4.1 scoped to the bare strategy; new P1 AC-4.4 (equal-size outputs, at most `ceil(G / S)` moves) and AC-4.5 (one dip, two moves); D-5's reason, runner-up, and flip condition rewritten; §12.5 counts cut moves. Weighed and not built: an original-size measure (stateless and monotone, but it would keep far less than B once outputs are masked) and the `run_state` cut (needs plumbing through middleware, engine, and strategy). A review-suggested control, so it is Q-11, default no. |
| 1 | R-7 | Major | §7 NFR-10.1, §8.5 leaf table, INV-10.7 | The card cap cut exactly the not-found list and the searches. | Accepted | The card renders `{question}`, `{not_found}`, `{rejected}`, `{searches}`, then `{found}`; INV-10.7, §8.5 leaf table, §9.2, row 43; new AC-10.7 (P0) and EC-10.6. |
| 1 | R-8 | Minor | §6.2 AC-8.1 | The query `enterprise pricing zeta` can never hit (porter turns "pricing" into "price"). | Accepted | AC-8.1 queries `enterprise zeta` and expects `#7 fact: ` first; new negative AC-8.6. |
| 1 | R-9 | Minor | §6.1 INV-6.2, INV-6.4 | Caps at or below 25,000 went tail-only, and the timeout marker could claim a drop that never happened. | Accepted | T = `min(TAIL, MAX // 2)`; the timeout path shows the counted marker only when bytes were left out, since the count now survives the timeout; EC-6.2, EC-6.3, §8.5 `_collect`, row 14; new AC-6.4, AC-6.5; §13 tells the test author to patch both constants. |
| 1 | R-10 | Minor | §6.3 EC-8.5 | The fingerprint blind spot is the timestamp tick, not a nanosecond. | Accepted | EC-8.5 restated (ms to 2 s by filesystem; same-length edits). The `(mtime_ns, size)` decision is unchanged. |
| 1 | R-11 | Minor | §6.3 EC-7.6 | The children's cost claim was inaccurate, and their history loss was unstated. | Accepted | EC-7.6 states that children trade up to S tokens of history for fewer billed tokens, with no cache gain. Trim targets unchanged. |
| 1 | R-12 | Minor | §15 A-6 (the review said §16), EC-9.9, §9.2 | Wrong backend path; forwarding is verifiable in code. | Accepted | The path is now `backend/provider/generative_models/client.py` (`:119`; `_require_short_cache` `:260-278`, re-measured, where the review had `:276`; `plan()` `:176`; `send()` `:195`) in G-4, NG-7, EC-9.9, D-13, §9.2, row 15, A-6. A-6 now says forwarding is verified in code, not with a live key. |
| 2 | R-13 | Blocker | §6.1 INV-7.3, §7 NFR-7.2, §13 | A no-change status message within the 150-token bound turns `test_infinite_memory_context.py:46` red (the review measured the threshold between 89 and 126 tokens). | Accepted; the scope-adding part became Q-12 | INV-7.3 split into three cases: when nothing changed, the message is the loop-settings block alone (33 tokens with the default loop). NFR-7.2 bound is now 40 tokens; new AC-7.5 (P0); EC-7.5, row 25, and the §13 stays-green reasoning updated. Masking every status message but the newest is Q-12, not built. |
| 2 | R-14 | Blocker | §9.2 `{found}` | The found section rendered the retriever's `({why})`, which INV-10.4, AC-10.3, and T-2 forbid. | Accepted | `{found}` holds only the code-built label and the copied text, and an accepted citation's `why` renders nowhere; `{rejected}` rebuilds the citation from parsed fields. The alternative (allow a labelled `why`) was not taken, because it would amend three normative clauses. |
| 2 | R-15 | Major | §6.1 INV-10.7, §7 NFR-10.1, NFR-10.3, AC-10.7 | `TokenEstimate.cap` appends the marker after its cut, so a 1,500 cap gives 1,502. | Accepted | The card is `TokenEstimate.cap(rendered, CAP - TokenEstimate.count(MARKER), MARKER)`, so it holds at most CAP with the marker. NFR-10.1 says "marker included"; NFR-10.3 and AC-10.7 say a cut block is an exact prefix of the disk text; §9.2 result table and row 27 updated. |
| 2 | R-16 | Major | §6.1 INV-10.5, §9.1, D-16 | A grammar-valid FOUND line with refused numbers made the whole recall fail. | Accepted | `parse` returns `None` for non-citations and lets the record's `ConfigurationError` propagate; the tool catches it per line and lists `- reply line {n}: {reason}`. INV-10.5, D-16, §8.5, §9.1, §9.2, row 27; new EC-10.7; AC-10.4 gains `FOUND notes/p.md:5-3`, `FOUND #0`, and a valid citation that is still transcribed. |
| 2 | R-17 | Minor | §9.1 `FullTextIndex.replace` | Deleting by the UNINDEXED `source` column scans the whole table under the shared lock. | Accepted | `replace` and `retain` delete by the rowids recorded per source, kept in memory beside the fingerprint; §9.1 Refresh and row 12, with the review's measurements. |
| 2 | R-18 | Minor | §6.1 INV-8.4 | The stat/read order was unstated, and one order loses writes for good. | Accepted | INV-8.4: the recorded fingerprint is the one taken before the content is read. |
| 2 | R-19 | Minor | §12.3 rows 6, 7 | The engine's `int()` coercion meant the strategy guard never saw a bool or float. | Accepted | Row 6 forwards `low_watermark_tokens` unchanged. Row 7 builds the trim once in `_validate_options` (the sliding-window precedent), so the strategy's guard is the one check and fails at construction; the key stays out of the `int()` tuple. |
| 2 | R-20 | Minor | §12.6, rows 16, 23, 25, 46, 47 | Some P3 rows used names that only P4 or P5 create. | Accepted | `INFINITE_SEARCH_MEMORY_TOOL_NAME` (name only) moves to P3, and it joins the reserved names in P4. The memory `settings=` edits in rows 23 and 25 are P5. Rows 46 and 47 tag each clause with its phase; the §12.6 lists match. |
| 2 | R-21 | Minor | §12.3 rows 24, 50 | The workspace header and README line 111 would state behavior the spec contradicts. | Accepted | Row 24's header text now names EC-8.5 as the one blind spot. Row 50 restates README line 111 per EC-4.2. |
| 2 | R-22 | Minor | A-10, row 25 | The status message's loop block must count tools as the system path does. | Accepted | INV-7.3, row 25, and A-10 name `tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts))`, as at `runtime.py:406`. |
| 2 | R-23 | Minor | §11 Commands | "`.venv` is already set up" is false. | Accepted | Install line: the global Python 3.11.0 (SQLite 3.38.4, FTS5) with `PYTHONPATH=$(pwd)` for the source stage and tests, without it for the package stage; the focused test command now sets `PYTHONPATH`. |
| 2 | R-24 | Minor | §6.1 INV-10.10 | Pre-searching all terms as one AND over single-line rows usually returns nothing. | Accepted | One `search_memory` search per term, in order, each term's words ANDed as INV-8.2 states. This is the same search, run per term, so it is not a fallback (OR retry stays Q-8, default no). INV-10.10, §9.2 `{hits}` and `{searches}`, row 27; new AC-10.8 (P1). |
| S2 | S2 defect 1 | Blocker | §6.1 INV-9.3, §15 A-5, §13 | INV-9.3 turns `test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire` (Anthropic subtest) red: repeat bodies send the task as a marked text block, while A-5 checked only `system`. | Accepted: option (a), the new shape is intended | Evidence: a scratch prototype of INV-9.1–9.7 (a patched `_create_payload`, not committed) run over the full existing suite of 6,378 tests. Under the r3 rule exactly this test turns red, and all 14 tests in `tests/test_anthropic_cache_breakpoints.py` pass. Under option (b), where string contents are never converted and a mark moves to the nearest earlier list message, this test stays green. But three of those new tests stay red (`test_a_different_history_with_the_same_tools_and_system_is_still_a_repeat`, `test_a_thinking_block_or_an_empty_text_block_is_never_marked`, `test_an_agent_whose_system_changes_every_call_sends_no_marks`), and a history made only of strings gets no message breakpoint, which loses G-4's caching for plain chats. Anthropic documents a string content as shorthand for one text block, so (a) changes the wire shape and not the model's input. The test's purpose is the task's position, and its matcher alone compares the shape. Changes: INV-9.3 sentence; new EC-9.10; §8.5 sketch comment; §9.2 wire note; §9.4; row 15; §12.6 P2; §13 (the test joins the deliberately changed list with its exact new expectation, plus a stays-green line); A-5 restated with the evidence. |
| S2 | S2 defect 2 | Blocker | §7 NFR-0.1, NFR-0.2; §8 D-14, D-16, §8.4; §12.3 row 27; §13; §14 | `test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget` (at most 400 lines per module after the header, at most 8 package `.py` files) was missing from §13, and a bare reference `InfiniteRecallTool` already takes `memory.py` to 402 lines. | Accepted: option (b), a 9th module `recall.py` (D-18) | Evidence: measured lines after the header and headroom: memory 251 (149 free), launch 368 (32), workspace 332 (68), runtime 106 (294), agent 111 (289), journal 157 (243), settings 196 (204). Option (a) would put the tool into a module that owns another subsystem (AGENTS.md principle 3), or into the tools layer, which cannot import the retriever's `BaseAgent`. Changes: new D-18; D-14 and D-16 reasons; NFR-0.1 (4 `.py` files) and NFR-0.2 (9 files, 13 modules); §8.2; §8.4 (14 files, 4 modules); §8.5 sketch; §11 layout; §12.2; row 27 trimmed and new CREATE row 57; row 50 File Index entry (S020); §12.4; §12.5; §12.6 P5 rows and order; §13 (the budget test joins the deliberately changed list with its new numbers, and the recall test's import note); §14 now asks first only for a 10th module. |
| S2 | S2 notes | — | §9.2, §13 | The test author left open the rejection reasons, the `{searches}` wording, the `{hits}` layout, and how an empty `known` renders. Tests accept either 0- or 1-based `reply line {n}`, and either `AgentExecutionError` or the original error class. The changed endless-printer test in `test_bash_tool_process_bounds.py` is POSIX-only. | Agreed; none pinned | These stay open, and the tests check content and order only. The one spec change: §13 Per-area config says the POSIX-only bash test is skipped on Windows, so its proof is the Linux CI run. |

## §17 Revision history

| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-16 | S1 spec | Initial spec |
| r2 | 2026-10-16 | S1 review round 1 | All 12 findings accepted (R-6's optional monotone cut became Q-11): C006-safe guards; AC-4.1/4.2 numbers; masking-dip cost stated with AC-4.4/4.5; capped status message and its overhead; bookkeeping paths refused in recall; one off-loop index per workspace; card renders found last; AC-8.1 query; bash head/tail split and timeout marker; EC-8.5 and EC-7.6 wording; backend path. |
| r3 | 2026-10-16 | S1 review round 2; approved | All 12 findings accepted (R-13's masking idea became Q-12, not built): a no-change status message is the loop block alone; `{found}` holds no retriever text; exact card cap; refused citation numbers rejected per line; delete by rowid; fingerprint before read; trim guard sees the caller's value; phase order fixed; two agent docs corrected; tool count as at `runtime.py:406`; real interpreter setup; pre-search per term. Status set to approved. |
| r4 | 2026-10-16 | S2 defects from the test author; status stays approved | Defect 1: the marked task goes out as one text block, so the run-boundary test joins §13 as deliberately changed. A-5 is restated with full-suite prototype evidence, and EC-9.10 is new. Defect 2: `InfiniteRecallTool` moves to a 9th module `recall.py` (D-18, CREATE row 57), and the budget test joins §13 with 9 files and 13 modules. Nothing from the S2 notes is pinned. |
