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

Every agent holds `bash` (in `root_dir`), `grep` and `read_lines` (in the workspace), `remember`, and `write_note`. The FULL preset adds `edit_file`, the root and generators below `max_depth` hold `launch_subagent`, and verifiers hold `drop_entry`. The root also holds every developer tool it was given, including tools added with `add_tool` and MCP tools; a pair gets only the extras its task card names.

## What it is not for

- No CLI command; build the agent from Python.
- No hooks, skill packs, domain packs, or shareable presets.
- No live tree view, event stream, transcript archive, or end-of-run report.
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

- `entries.jsonl` holds one live memory entry per line: `id`, `kind` (decision, fact, lesson, open_question, or pointer), one-line `text`, up to three `tags` and `refs`, `supersedes`, the author `by`, the verifier `verified_by` (null for the root), the `run` id, and a UTC `at` stamp. Ids never repeat.
- `superseded.jsonl` holds entries that a newer entry replaced, moved there unchanged; `grep` skips it.
- `files.jsonl` holds one line per note created through `write_note`, with its one-line description for the map.
- Notes are any other text files (`.md`, `.txt`, `.json`, `.jsonl`) under the root. Seed files are copied to `seed/` when the agent is built and are read-only to the tools.
- `.runs/<run_id>.jsonl` is one journal per run: `run_started` with the task, `pair_started` and `pair_finished` with each pair's card, and `run_finished` with the stop reason. Journals do not count toward the caps and are never deleted for you.

Every agent sees a map of the workspace at the top of its context: the file and token totals against their caps, the live-entry count, and one line per file with its token count and description. The root's map is rendered again after every tool iteration; a child's map is rendered once, when the child is built.

## Limits and defaults

- `max_depth` 10, `max_parallel` 10 tasks per call, `max_agents` 200 agents per run (each pair counts as two, including pairs started before a resume).
- Workspace: `max_files` 200, `max_tokens` 250,000 in total, `max_file_tokens` 20,000 per note or seed. The bookkeeping files count only toward the total.
- Memory: entries of at most `max_entry_tokens` (60) tokens, `max_entries_per_agent` (5) accepted `remember` calls per agent, and one new file per agent.
- Every agent stops after 100 model turns and cuts each ordinary tool result at 100,000 characters, unless you pass another `loop`; one `loop` applies to every agent in the tree.
- Each agent's history is trimmed to 60,000 tokens, newest tool exchanges first; the task, the rules, and the map are never trimmed.
- A card's summary and review are each cut to 400 tokens, and so are its dropped entries and its files in the text the parent reads; the journal keeps both lists whole.
- Tokens are estimated as characters divided by four everywhere (`TokenEstimate`).

The caps are checked against the files on disk before every tool write, so files that `bash` wrote count too; a refused write changes nothing.

## Resume

`resume(run_id=None)` and `aresume(run_id=None)` continue a run whose journal has no `run_finished`: the newest one, or the one named. A malformed run id, an unknown or finished run, or no unfinished run raises `ConfigurationError` before any model call. The resumed root starts a fresh conversation whose first message holds the original task, one short line per finished pair, and the names of pairs that started but never finished. Launching a finished name again returns its recorded card and runs nothing; an interrupted pair runs again from scratch, and its staged entries are lost by design. A cut-off last journal line is ignored; any other malformed line refuses the resume with its line number.

## File Index

- `__init__.py`: the package facade, exporting the agent, its two settings objects, and the runtime.
- `agent.py`: `InfiniteMemoryAgent`, which builds the workspace and the root, and its `resume` and `aresume`.
- `settings.py`: `InfiniteMemoryAgentSettings` and `InfiniteWorkspaceSettings`, validated when they are created.
- `runtime.py`: `InfiniteMemoryRuntime`, which opens the journal, adds the run-bound tools and the map, runs the loop, and records the run's end.
- `workspace.py`: `InfiniteWorkspace`, the shared folder and every guardrail on writing to it, plus the map.
- `journal.py`: `InfiniteRunJournal`, the append-only, fsynced record of one run, and finding a run to resume.
- `memory.py`: `InfiniteAgentMemory` and the `remember`, `write_note`, `edit_file`, and `drop_entry` tools.
- `launch.py`: the `launch_subagent` tool and `InfinitePair`, which runs one generator and its verifier and commits or drops their entries.
- `README.md`: this file.

## Notes for agents

- An explicit `system=` run option replaces the root's prompt and its map for that run; the runtime leaves the caller's option alone.
- `bash` can write anything in the workspace, past every rule. Nothing is undone; the caps are recounted from disk, so later tool writes are refused until the files are removed.
- On Windows, cancelling a run (Ctrl-C) while `bash` runs may leave that command running; the run itself is cancelled and stays resumable.
- Use one process per workspace. The workspace lock is per process, so two processes can lose an entry, mint the same id twice, and interleave journal lines.
- A crash after a pair committed its entries but before its `pair_finished` record re-runs that pair on resume, which can repeat near-duplicate entries and note text.
- A parent's `timeout_seconds` includes the time it waits on its children, so a short timeout can end the root while it waits on a batch.
- History past 60,000 tokens is trimmed by whole tool exchanges, and one tool output larger than that is dropped whole; read a smaller range or save the content to a note.
- A skill reaches every agent through `system_prompt`, which every child inherits, or as a developer tool that task cards name.
- Do not put secrets in the workspace: entries, notes, and journals are plain files that every agent and `bash` can read.
