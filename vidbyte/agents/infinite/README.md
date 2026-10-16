# InfiniteMemory agent

`InfiniteMemoryAgent` is a root agent for long tasks of any kind. It treats its own context window as scarce: it delegates the work to fresh subagents, which run in pairs of a generator and a verifier, and it gets back only one short result card per pair. Everything worth keeping goes into one workspace folder that every agent in the tree shares, guarded by fixed limits. Every run is journaled, so an interrupted run can resume without running finished pairs again.

```python
from vidbyte import InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings

agent = InfiniteMemoryAgent(
    InfiniteMemoryAgentSettings(
        name="analyst",
        system_prompt="You research markets and report sourced findings.",
        provider="openai",
        model_name="gpt-4.1",
        root_dir=".",
        workspace=InfiniteWorkspaceSettings(root="memory", seed_files=("brief.md",)),
    )
)
reply = agent.run("Compare the list prices of our five competitors.")
```

## What it is for

- One long task that would outgrow one conversation: research, writing, analysis, operations, or code. Nothing in the prompts or the tools is specific to coding.
- Work that splits into checkable pieces. The root writes a task card for each piece (a name, a goal, done criteria, a generator prompt, a verifier prompt, and optionally entry ids, file paths, and extra tools), and `launch_subagent` runs up to `max_parallel` pairs at once. A generator may delegate further until `max_depth`; a verifier never does.
- Memory that survives history trimming and restarts. Agents save short typed entries with `remember` and longer material with `write_note`. A pair's entries are staged and reach `entries.jsonl` only after its verifier gives a verdict.
- Runs that must be resumable. `resume()` or `aresume()` continues the newest unfinished run, or a named one.

Every agent holds `bash` (in `root_dir`), `grep` and `read_lines` (in the workspace), `remember`, and `write_note`. The FULL preset adds `edit_file`, the root and every generator hold `launch_subagent`, and verifiers hold `drop_entry`. Which memory tools each agent holds is one table, `InfiniteMemoryToolRegistry` in `vidbyte/lib/registries/infinite.py`. The root also holds every developer tool it was given, including tools added with `add_tool` and MCP tools; a pair gets only the extras its task card names.

## What it is not for

- No CLI command; build the agent from Python.
- No hooks, skill packs, domain packs, or shareable presets.
- No live tree view and no transcript archive. A run's live events and its handoff, described below, are how you watch and summarize a run.
- No consolidation or automatic compaction of files; a write over a cap is refused with a message.
- No run-level final verifier and no second verification round.
- No domain write policies such as one writer per file.
- No cost cap, token budget, budget split between pairs, or wind-down.
- No scan or undo of what `bash` does to the workspace.
- No semantic or vector search; agents use `grep` and `read_lines`.
- The SDK's other private token heuristics are not moved onto `TokenEstimate`.
- No durable `Session` persistence and no working `fork()`.
- No "save now" or "consider delegating" reminders and no structured run-state file.
- No per-task model tier or budget share, and no extras handed to children without a task card naming them.
- No cross-process lock on a workspace or a run.
- No vidbyte-cli runtime primitive.

## Workspace layout

Everything lives as plain files under the workspace root, so a person or `bash` can read and repair it.

- `entries.jsonl` holds one live memory entry per line: `id`, `kind` (decision, fact, lesson, open_question, or pointer), one-line `text`, up to eight `tags` and eight `refs`, `supersedes`, the author `by`, the verifier `verified_by` (null for the root), the `run` id, and a UTC `at` stamp. Ids never repeat.
- `superseded.jsonl` holds entries that a newer entry replaced, moved there unchanged; `grep` skips it.
- `files.jsonl` holds one line per note created through `write_note`, with its one-line description for the map.
- Notes are any other text files (`.md`, `.txt`, `.json`, `.jsonl`) under the root. Seed files are copied to `seed/` when the agent is built and are read-only to the tools.
- `.runs/<run_id>.jsonl` is one journal per run: `run_started` with the task, `pair_started` and `pair_finished` with each pair's card, and `run_finished` with the stop reason, the root's final `answer`, and the `files` the root wrote. A `run_finished` written before `answer` and `files` existed still loads. Journals do not count toward the caps and are never deleted for you.
- `.runs/<run_id>.handoff.md` is the handoff `run_handoff` saved for that run, if it was called; it is rebuilt from the journal and the workspace on every call.

Every agent sees a map of the workspace at the top of its context: the file and token totals against their caps, the live-entry count, and one line per file with its token count and description. The root's map is rendered again after every tool iteration; a child's map is rendered once, when the child is built.

## Limits and defaults

The defaults are generous on purpose: the point of this agent is work that outgrows one context, so a cap should stop a runaway tree, not a large honest task. All of them live in `vidbyte/lib/constants/infinite.py`.

- `max_depth` 20, `max_parallel` 20 tasks per call, `max_agents` 1,000 agents per run (each pair counts as two, including pairs started before a resume).
- Workspace: `max_files` 2,000, `max_tokens` 2,000,000 in total, `max_file_tokens` 100,000 per note or seed. The bookkeeping files count only toward the total.
- Memory: entries of at most `max_entry_tokens` (150) tokens with up to eight tags and eight refs, `max_entries_per_agent` (25) accepted `remember` calls per agent, ten new files per agent, and up to 100 context items per task card.
- Every agent stops after 500 model turns and cuts each ordinary tool result at 200,000 characters, unless you pass another `loop`; one `loop` applies to every agent in the tree.
- Each agent's history is trimmed to 90,000 tokens by dropping the oldest tool exchanges first; the task, the rules, and the map are never trimmed. With the largest role prompt (about 2,100 tokens), the tool descriptions (about 5,000), and an 8,000-token map, an agent's whole context stays near 105,000 tokens, inside a 128,000-token model.
- A card's summary and review are each cut to 800 tokens, and so are its dropped entries and its files in the text the parent reads; the journal keeps both lists whole. The map is cut at 8,000 tokens.
- Tokens are estimated as characters divided by four everywhere (`TokenEstimate`).
- `on_event` defaults to `None`: no events are built and nothing is logged for them.
- `model_name` must be in `ProviderModelRegistry`'s catalog under `provider`, as the SDK's declarative `BaseAgentSettings` require. A plain `BaseAgent` accepts more names, such as `gpt-4.1-2025-04-14`, which these settings refuse. Set `ProviderModelRegistry.STRICT_MODEL_VALIDATION = False` to accept the names a plain `BaseAgent` accepts, such as a model released after this SDK version.

### Where each limit is enforced

Limits are enforced in code, and the prompts only describe behavior: no prompt states a number the code could contradict, and a refusal names the limit it hit.

- `max_depth` and `max_parallel` are enforced by `DelegationLimitsMiddleware` (`vidbyte/middleware/builtins/delegation_limits.py`), which the root and every generator carry at their own depth. It denies a `launch_subagent` call at the depth cap, or one carrying more tasks than `max_parallel`, before the tool runs, so nothing starts. The tool schema still declares `maxItems` for the model.
- `max_agents` is checked by `launch_subagent` itself, because only the run's journal knows how many agents have started and which task names are replays that start none.
- The workspace and memory caps are checked by `InfiniteWorkspace` against the files on disk, counted with `FolderUsage`.

The caps are checked against the files on disk before every tool write, so files that `bash` wrote count too; a refused write changes nothing.

## Resume

`resume(run_id=None)` and `aresume(run_id=None)` continue a run whose journal has no `run_finished`: the newest one, or the one named. A malformed run id, an unknown or finished run, or no unfinished run raises `ConfigurationError` before any model call. The resumed root starts a fresh conversation whose first message holds the original task, one short line per finished pair, and the names of pairs that started but never finished. Launching a finished name again returns its recorded card and runs nothing; an interrupted pair runs again from scratch, and its staged entries are lost by design. A cut-off last journal line is ignored; any other malformed line refuses the resume with its line number.

## Events and handoff

Pass a plain function as `on_event` to watch a run live, and call `run_handoff` afterwards for a summary that needs no model:

```python
events = []
agent = InfiniteMemoryAgent(InfiniteMemoryAgentSettings(..., on_event=events.append))
reply = agent.run("Compare the list prices of our five competitors.")
run_id = reply.metadata["infinite_run_id"]  # the journal's run id, also accepted by resume()
handoff = agent.run_handoff(run_id)         # also saved as <workspace>/.runs/<run_id>.handoff.md
```

`on_event` must be `None` or a synchronous callable, such as a function, a bound method like `list.append`, or an object with a plain `__call__`. An `async def` function, an object with an async `__call__`, or a `partial` of one is refused when the settings are built, because events are delivered from code that cannot await.

Each event is an `InfiniteEvent` whose `kind` is an `InfiniteEventKind`:

- `run_started`: a new run opened its journal; its task, model, preset, limits, the root's extra tool names, and the seed file names.
- `run_resumed`: a resumed run; its task, how many pairs finished earlier, and which started pairs will run again.
- `run_finished`: the root's loop returned and `run_finished` is journaled; the stop reason, the answer, the pairs and agents, and the run's tokens and cost.
- `run_stopped`: the run raised after its journal opened; `failed` for an `Exception`, `cancelled` for any other `BaseException`, with the error's class and message. The error is raised again unchanged, and the run stays resumable.
- `batch_rejected`: `launch_subagent` refused a batch itself (unreadable tasks, a repeated name, a tool it cannot grant, an unknown entry, or `max_agents`). A call `DelegationLimitsMiddleware` denies never reaches the tool and has no event.
- `subagent_launched`: a new pair, right after its `pair_started` record; its name, keys, depth, and task card.
- `subagent_replayed`: a task whose name already finished in this run; its recorded card is reused and nothing runs.
- `generator_finished`: a generator replied; its status, stop reason, summary, tool calls, usage, and time since its pair launched.
- `subagent_finished`: a pair's card is journaled; its status, verdict, review, committed and dropped entries, notes, and the usage of both agents.
- `memory_saved`: the root committed an entry to `entries.jsonl`.
- `memory_staged`: a pair agent staged an entry for its verifier.
- `memory_dropped`: a verifier dropped a staged entry.
- `file_written`: a note was created, appended to, or edited.
- `tool_refused`: a memory tool refused a call, with the problem the model was told.

Every event has `run_id`, `agent_key`, `role`, `depth`, `at`, a one-line `summary`, and typed `details`, a record from `vidbyte.lib.dataclasses.infinite` that serializes with `dataclasses.asdict`. Launch and pair-outcome events carry the launching agent (`root`, or a generator); memory events carry the agent that acted. The root is at depth 0 and a pair's agents at their launcher's depth plus 1; `at` is UTC, to the millisecond.

- Caps: a summary is at most 280 characters, texts 500, paths 500, lines 120, and labels 64; a list shows its first five items and counts the rest in its `*_omitted` field; every count is at most 2^63 - 1. Cut text ends with ` … [cut]`, and a lone surrogate becomes `?`. Every details record is at most 32,768 bytes as JSON (27,015 at worst), and a whole event at most 31,093.
- Keys: a pair key over 508 characters becomes `~`, 16 hexadecimal digits of its SHA-256, a slash, and its last 490 characters; an agent key keeps its `/gen` or `/ver`. Keys are never cut with the marker.
- Usage: `tokens` sums the replies' `UsageRollup`s, and `cost_usd` is `None` whenever any part of the cost is unknown, never 0.
- Note paths are workspace-relative POSIX paths, so `./notes/a.md` and `notes/a.md` are one note.

Delivery is synchronous: the sink is called inline, on the thread that runs the agent's event loop, after the change it reports is on disk, so events arrive in the order they happen. Keep the sink fast, for example by only enqueueing the event, and make it thread-safe when one agent runs from several threads; `run_id` tells the runs apart. An `Exception` raised by the sink, or by building one event, drops that event and logs one `WARNING` on the `vidbyte.agents.infinite.events` logger that names the run id, the kind, and the exception class, never event text; the run goes on. A `KeyboardInterrupt` or `CancelledError` raised by the sink stops the run. A sink that returns a coroutine has it closed and counted as a failure.

`reply.metadata["infinite_run_id"]` holds the journal's run id on every successful `run`, `arun`, `resume`, and `aresume`; a failed or cancelled run has no reply, so its id comes from its events.

`run_handoff(run_id=None)` builds an `InfiniteHandoff` (`vidbyte/context/handoff/infinite.py`, a `Handoff` subclass usable as a context item) from the journal and the workspace, with no model call, for the named run or the newest run in any state. Its nine sections are Outcome, Work done, Decisions, Facts, Lessons, Open questions, Files, Unverified or failed work, and How to continue. Every list line is one line of at most 1,000 characters; the Outcome is cut to 239,000 characters and every other section to 15,900, so the whole text stays within 366,500. It writes `.runs/<run_id>.handoff.md` as one atomic swap with `\n` line ends and changes no other file. A malformed or unknown run id, or a workspace with no runs, raises `ConfigurationError` for `run_id`; a malformed journal or `entries.jsonl` line raises its usual error; on any error nothing is written.

## Shared helpers

This package builds on canonical helpers in `vidbyte/lib/` rather than private copies: `RecordFieldValidator` and `RecordFieldConverter` (`vidbyte/lib/dataclasses/validation.py`) check every settings and record field; `ToolArguments.records` (`vidbyte/lib/tools/arguments.py`) reads the task cards; `FolderUsage` (`vidbyte/lib/tools/filesystem/usage.py`) counts the workspace; `LocalFileSystemBackend.write_text(atomic=True)` swaps in whole files; `AppendOnlyJsonl` (`vidbyte/lib/util/jsonl.py`) writes and repairs the journal; `TokenEstimate.cap` cuts card text; `TokenEstimate.truncate_chars` (`vidbyte/lib/util/text.py`) cuts event and handoff text with the infinite marker, through `OutputText.truncate` (`vidbyte/lib/outputs/text.py`) in events and `run_handoff` and directly in the handoff's list lines; and `InfiniteMemoryToolRegistry` (`vidbyte/lib/registries/infinite.py`) names each agent's memory tools.

## File Index

- `__init__.py`: the package facade, exporting the agent, its two settings objects, the runtime, and `InfiniteEvent`, `InfiniteEventKind`, and `InfiniteHandoff`.
- `agent.py`: `InfiniteMemoryAgent`, which builds the workspace and the root, its `resume` and `aresume`, and `run_handoff`.
- `settings.py`: `InfiniteMemoryAgentSettings` and `InfiniteWorkspaceSettings`, validated when they are created.
- `runtime.py`: `InfiniteMemoryRuntime`, which opens the journal, adds the run-bound tools and the map, runs the loop, and records the run's end.
- `workspace.py`: `InfiniteWorkspace`, the shared folder and every guardrail on writing to it, plus the map.
- `journal.py`: `InfiniteRunJournal`, the append-only, fsynced record of one run, and finding a run to resume.
- `memory.py`: `InfiniteAgentMemory` and the `remember`, `write_note`, `edit_file`, and `drop_entry` tools.
- `launch.py`: the `launch_subagent` tool and `InfinitePair`, which runs one generator and its verifier and commits or drops their entries.
- `events.py`: `InfiniteEvents`, the single writer of a run's events, which caps each event and keeps a failing sink from changing the run.
- `README.md`: this file.

## Notes for agents

- An explicit `system=` run option replaces the root's prompt and its map for that run; the runtime leaves the caller's option alone.
- `bash` can write anything in the workspace, past every rule. Nothing is undone; the caps are recounted from disk, so later tool writes are refused until the files are removed.
- On Windows, cancelling a run (Ctrl-C) while `bash` runs may leave that command running; the run itself is cancelled and stays resumable.
- Use one process per workspace. The workspace lock is per process, so two processes can lose an entry, mint the same id twice, and interleave journal lines.
- A crash after a pair committed its entries but before its `pair_finished` record re-runs that pair on resume, which can repeat near-duplicate entries and note text.
- A parent's `timeout_seconds` includes the time it waits on its children, so a short timeout can end the root while it waits on a batch.
- History past 90,000 tokens is trimmed by whole tool exchanges, and one tool output larger than that is dropped whole; read a smaller range or save the content to a note.
- A skill reaches every agent through `system_prompt`, which every child inherits, or as a developer tool that task cards name.
- Do not put secrets in the workspace: entries, notes, and journals are plain files that every agent and `bash` can read.
- Keep deterministic limits out of the prompt families. A new cap is a constant, a settings field, and a check in code (middleware for a per-call cap, `InfiniteWorkspace` for a disk cap) whose refusal names it; the prompts say only that limits exist and are enforced.
- Pairs that keep running after an error escaped their batch can deliver events after `run_finished` or `run_stopped`, so a consumer must not assume the terminal event is the last one of its run.
- `vidbyte/context/handoff/infinite.py` must not import `vidbyte.lib.outputs`: `vidbyte.lib.dataclasses` imports `vidbyte.context` while it loads, and the outputs package needs the finished dataclasses package back, so that import breaks `import vidbyte`. It calls `TokenEstimate.truncate_chars` (`vidbyte/lib/util/text.py`), the cut `OutputText.truncate` delegates to, instead of copying it.
- Before adding a private helper here, look in `vidbyte/lib/` for a canonical one and add an option to it, as `RecordFieldValidator`'s `one_line` and `require_text_items` were added for this package.
