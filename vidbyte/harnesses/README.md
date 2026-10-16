# Harness execution contract

`vidbyte.harnesses` is a small outer envelope for arbitrary harness
implementations. It standardizes the repeated work around a harness — loading its
behavior config, identifying exact variants, running one execution, and collecting
a self-contained trajectory dataset — **without** standardizing the harness
algorithm and **without** building a second capture system. Per-agent capture and
durable persistence come from `vidbyte.sessions`; this package only adds the run
envelope and the consented, redacted export.

The developer surface is a base class you subclass:

```python
from vidbyte.harnesses import Harness

class ResearchSwarm(Harness):
    type = "research-swarm"      # identity of the implementation *kind* (matches config)
    version = "2"                # code identity; NOT in the YAML

    async def run(self, request):
        planner = self.session(build_planner())   # full-trace, run-tagged session
        plan = await planner.arun(request["topic"])
        for chunk in fan_out(plan):
            worker = self.session(build_worker())
            await worker.arun(chunk)
        return {"answer": "..."}

h = ResearchSwarm(store=store, sink=sink, collect=True)
h.load("harness.yaml")
result = await h.execute({"topic": "durable agent runtimes"})
```

`type`/`version` are class attributes on the code, not YAML fields: version tracks
*implementation code*, so bumping it is a code edit, not a config edit. A foreign
object exposing `run(request)` still works via `HarnessClient.load(implementation=...)`
or `wrap_implementation(...)` — no inheritance required. A `Harness` subclass passed
there (or built by a registered factory) is used as is rather than wrapped, so
`self.session(agent)` keeps working; a supplied `store`/`sink` replaces its own and
`collect=True` turns collection on (`None`/`False` keep what it was built with), and a
factory's `harness_version` stays the code version.

## Configuration is the single source of truth

The YAML holds **every** behavior hyperparameter: each agent, each agent's own
`params` and `tools`, and all between-agent `orchestration` knobs. A behavior
variant is a config edit, never a code edit. The strict top-level envelope is
`schema_version`, `harness`, `agents`, plus optional `metadata` and
`orchestration`; unknown/misspelled top-level keys fail early.

```yaml
schema_version: 1

harness:
  type: research-swarm          # identity of the implementation *kind*; NO version here

metadata:                       # descriptive only — excluded from spec_id
  name: Research swarm (baseline)
  description: Planner fans out to workers, reviewer gates.
  labels: [experimental]

agents:
  - name: planner
    provider: anthropic
    model: claude-sonnet
    system_prompt: { $file: prompts/planner.md }
    params:                     # per-agent hyperparameters live WITH the agent
      temperature: 0.2
      max_tokens: 4096
    tools: [web_search, read_file]
  - name: worker
    provider: anthropic
    model: claude-haiku
    params: { temperature: 0.7 }
    tools: [web_search]

orchestration:                  # harness-level knobs NOT owned by a single agent
  max_workers: 4
  review_rounds: 2
```

Agent validation is strict so an invalid hyperparameter fails at `load()`, not
three agents deep at runtime: `name` is required and unique across agents;
`provider`/`model` are optional strings; `system_prompt` is a string or a
`{$file: ...}` reference; `params` is an open object; `tools` is a list of names
or specs. `metadata` and `orchestration` are optional (absent ⇒ `{}`) so a
single-agent harness stays terse.

Credentials are not behavior hyperparameters. Credential-like config keys are
rejected before hashing or persistence; inject secrets through environments or
provider objects instead.

## Identity: `spec_id` vs `run_id`

An exact `{"$file": "..."}` object is replaced in resolved config by the UTF-8
file content and its SHA-256 digest, so editing a referenced prompt changes the
specification. `spec_id` is the SHA-256 of canonical JSON over
`{type, version, agents, orchestration}`:

- **code `version` is folded in**, so two code versions with identical config never
  collide on one id — a code change is a new variant;
- **`metadata` is excluded**, so renaming a harness never silently forks identity;
- reordering mapping keys yields the same id; changing a prompt, an agent param, a
  tool, orchestration, or the code version yields a different id.

Every execution receives a separate random `run_id`, so repeated trials never
overwrite each other.

```text
implementation code (version) + resolved config -> reusable hspec_...
reusable hspec_... + one invocation              -> unique hrun_...
unique hrun_... + tagged Sessions                -> one TrajectoryRecord
```

## Persistence and capture come from Sessions

There is no bespoke harness store, event stream, or capture enum. `self.session(agent)`
is the auto-instrument seam: it returns a durable `Session` bound to the harness's
`SessionStore`, forced to `PER_STEP` policy and `FULL` trace, and **tagged with the
`run_id`**. The developer writes no tracing code; every model call, tool call, and
reasoning trace is persisted as checkpoints automatically. The `run_id` tag is the
fan-in that later reconstructs the whole multi-agent run
(`store.list_sessions(tag=run_id)`).

`execute()` owns the lifecycle: it assigns the `run_id`, runs your `run()` (with an
optional `timeout_seconds`), and returns `HarnessExecutionResult(output, run)` where
`run` is the lightweight operational manifest (`run_id`, `spec_id`, `status`,
timestamps, `session_ids`). Failures raise `HarnessExecutionError`/`HarnessTimeoutError`
carrying the finalized run.

## Trajectory collection, consent, and redaction

The sellable unit is a self-contained `TrajectoryRecord`. Collection is automatic,
in `execute()`'s `finally`, and **fail-open — it can never fail the run**:

```python
store = sdk.harnesses.file_store(".vidbyte/sessions")   # operational source of truth
sink  = sdk.harnesses.file_sink("datasets/research.jsonl")  # LICENSED, redacted export

h = ResearchSwarm(store=store, sink=sink, collect=True)     # collect = opt-in consent
h.load("harness.yaml")
await h.execute({"topic": "..."})
```

- The operational `SessionStore` and the licensed `TrajectorySink` are **distinct
  surfaces on purpose** so the consent/redaction boundary stays sharp.
- `collect=True` is the per-run/tenant consent gate. With it off, or with no sink,
  nothing leaves the box.
- Every `task`, `output`, and `history`/`trace` value passes through one redaction
  pass (`HarnessRedactor`) before it reaches the sink — key- and free-text
  credential scrubbing, not just top-level keys. The redactor is pluggable.
- `TrajectoryRecord.spec` inlines the full resolved config (prompts, tools,
  orchestration) so a buyer consumes one JSONL line with no dependency on our store.
  Override `Harness.score(request, output)` to attach an optional eval `reward`.

A future `WarehouseTrajectorySink` / `S3TrajectorySink` in `providers/` implements
the same `TrajectorySink` protocol with zero harness changes.

## Relationship to adjacent layers

- `vidbyte.sessions` is the operational persistence layer this envelope binds; a
  harness run is a fan-in over N tagged session checkpoint DAGs.
- `vidbyte.trace` is optional observability and may be sampled or provider-hosted.
- `vidbyte.evals` grades behavior; a `reward` label can be attached to a record.
- `vidbyte.paradigms` contains concrete algorithms; a paradigm can be adapted behind
  this envelope while the envelope itself stays algorithm-free.

## Key modules

- `client.py`: store/sink constructors, foreign-implementation load, Sessions namespace.
- `config.py`: strict config-as-source-of-truth envelope, `$file` resolution, spec ids.
- `contracts.py`: public specification, run manifest, and trajectory-record records.
- `registry.py`: structural `run(request)` implementation protocol and exact registry.
- `execution.py`: the `Harness` base class — load/execute/session lifecycle.
- `dataset.py`: `TrajectoryCollector` — joins tagged Sessions into one redacted record.
- `stores/`: `TrajectorySink` port (`base.py`) plus in-memory and atomic-JSONL file
  sinks (`memory.py`, `file.py`), mirroring the `vidbyte/sessions/stores/` layout.
- `serialization.py`: the single redaction pass and shared secret-key policy.
- `native/`: the harness thread functions, which run an installed vendor coding CLI headless once per call with the caller's API key: `run_grok_thread`, `continue_grok_thread` and `fork_grok_thread` (Grok Build), `run_opencode_thread`, `continue_opencode_thread` and `fork_opencode_thread` (opencode), and `run_muse_thread`, `continue_muse_thread` and `fork_muse_thread` (Muse Code, through WSL on Windows). Each takes the prompt (after `thread_id` for continue and fork) and the keyword arguments `api_key`, `workspace`, `model`, `skills` and an optional `GrokThreadConfig`, `OpencodeThreadConfig` or `MuseThreadConfig`, and returns a `NativeThreadResult(harness, thread_id, text, text_truncated)` or raises one `NativeThreadError` with a closed failure code, the likely cause and a next step. The key is passed on every call and reaches only the vendor child: Grok runs with a private home under `~/.vidbyte/grok-homes/`, keyed by the workspace, so no stored `grok login` can win; opencode gets the key in an inline config bound to the provider before the slash in `model`; Muse gets a fresh private config folder per call. Skills are folders holding a `SKILL.md`: Grok and Muse get copies, opencode reads the folders in place. GLM and DeepSeek are reached through opencode, for example `model="zai-coding-plan/glm-5.3"` or `model="deepseek/deepseek-v4-pro"`, and only providers that take an API key work (EC-39). Concurrent Grok calls in one workspace share one private home, so calls with different skill sets can collide while its `skills/` folder is rebuilt (EC-27). Every new workspace path creates a Grok home that the SDK never removes; delete old homes by hand, and each home's `sessions/<encoded-cwd>` folder names its workspace (EC-43). SDK Grok runs use a private home, but Grok still loads your `~/.claude` hooks, skills and MCP servers inside them (verified with `grok inspect`; EC-63, T-6), so your own hooks run in SDK Grok runs. opencode also reads a workspace's own `opencode.json`, so pass only trusted workspaces to the opencode functions (T-6). The shared plumbing (error factory, launcher resolution, skills folders) lives in `hostkit/`, which only the harness subpackages import.
  - Thread helpers: 22 keyless functions read and manage the threads each vendor keeps: `list_<h>_threads`, `list_recent_<h>_threads`, `list_<h>_threads_since`, `get_<h>_thread`, `read_<h>_thread` and `get_<h>_thread_lineage` for `<h>` = `grok`, `opencode` and `muse`, plus `search_grok_threads`, `search_opencode_threads`, `delete_grok_thread` and `delete_opencode_thread`, and `init_muse_workspace` (`muse init`, with `dry_run=True` to only show what it would create). They take the workspace (after `thread_id` for one thread) and no key or model, and return `NativeThreadSummary(harness, thread_id, title, created_at, updated_at, parent_thread_id, model)` records newest first with UTC times, at most `limit`; `read_<h>_thread` returns the whole vendor document as a `NativeThreadResult`, a delete returns `None`, and `init_muse_workspace` a `NativeCommandOutput`. Grok helpers read each thread's `summary.json` themselves and take `scope`: `GrokThreadScope.SDK` (the default) is the private home the SDK's own runs use, `GrokThreadScope.USER` is your own `~/.grok`, filtered to the workspace; a read never creates a home. opencode helpers start `opencode session list`, `opencode db`, `export` or `session delete` in the workspace, and Muse helpers a short `muse serve` batch, `muse export` or `muse init` in a fresh private config folder. Every helper child runs with the SDK's key variables (`XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `META_API_KEY`, `OPENCODE_CONFIG_CONTENT`) removed and self-update off, within a fixed control timeout; other variables of your environment, such as `DEEPSEEK_API_KEY`, are inherited as by any child process. The opencode helpers start opencode in the workspace too, so its `opencode.json` applies to them as well (T-6).
  - Command and skill functions: 24 functions run one bundled command, agent or skill with the caller's key and the keyword arguments of the thread functions: `run_grok_command(GrokCommand, arguments)` and its named wrappers `run_grok_goal`, `run_grok_implement`, `run_grok_design`, `run_grok_execute_plan`, `run_grok_review`, `run_grok_code_review`, `run_grok_resume_claude`, `run_grok_resume_codex`, `run_grok_resume_cursor`, `run_grok_imagine`, `run_grok_imagine_video`, `run_grok_plan` and `run_grok_explore`; `run_opencode_command`, `run_opencode_review`, `run_opencode_init` and `run_opencode_plan`; and `run_muse_skill`, `run_muse_goal`, `run_muse_plan`, `run_muse_import`, `run_muse_scaffold` and `run_muse_browser_app`. A call returns only when the run's own record shows the command ran: a Grok stream tool call (the new thread's `agent_name` for plan and explore, the run's own `grok export` for `/code-review`), opencode's own dispatch of `--command`, or a Muse `read_skill` or `create_goal` item (the run's `muse export` after a compaction). Otherwise it raises `<harness>.command_not_run` with the new thread's id; every Grok command run carries an SDK-minted `--session-id`, so even a run that times out names its thread. Pass `config=GrokThreadConfig(permission_mode=GrokPermissionMode.ACCEPT_EDITS)` for editing Grok commands such as implement, design and execute-plan, because the default mode refuses edits headless; `auto_pr=True` pushes branches and opens pull requests, and `pr=` posts a pending review. Not offered: usage, cost and balance helpers; Grok's background `/deep-research` and `/workflow`; compaction; commands that need a person or run in the background, such as `/pr-babysit` and `/loop`; search and delete for Muse, whose threads have no title and which has no delete; and generic skill runners that no evidence rule could check.
  - Limits: Grok and Muse list subagent child threads as ordinary threads, so your own threads can fall below `limit` (EC-72). opencode lineage shows subagent nesting only; a thread made by `fork_opencode_thread` is its own root (EC-76). `run_grok_imagine_video` needs Grok's video tools on (`features.video_gen`), or it raises `command_not_run` (EC-74). A same-named skill or command in the workspace, in `~/.claude` or `~/.grok`, or in `skills=` replaces Grok's bundled one: a `skills=` folder named like the command is refused before the run, and any other shadow makes the call fail with `command_not_run` (EC-78).

The full architecture and rejected alternatives are recorded in
[`docs/design/harness-execution-contract.md`](../../docs/design/harness-execution-contract.md).
