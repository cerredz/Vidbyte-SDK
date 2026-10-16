---
slug: infinite-memory-events
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 22:10
flags: none
---

# Request: InfiniteMemoryAgent native run events and handoff

**This run builds:** the SDK part — the `InfiniteEvents` class (every event, native to InfiniteMemoryAgent), `InfiniteEvent` / `InfiniteEventKind`, the `on_event` settings field, `run_stopped` on failure or cancellation, the run id on the reply, and the deterministic `InfiniteHandoff` with `InfiniteMemoryAgent.handoff()`. Stacked on PR #1084's branch.

**Built by the sibling runs, not here:** see §C "Three sibling pipeline runs". Build only this run's scope; the cross-repo contract in §C is fixed.

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (start of conversation):
````
what features do we have for pr #1084 for vidbyte-sdk/?
````

**Prompt 2** (after a feature summary of Vidbyte-SDK PR #1084, which adds `InfiniteMemoryAgent`):
````
and can you show me the full list of tools that the infinite memory agent has?
````

**Prompt 3** (after the tool list; this is the feature request):
````
okay great, forget this pr for now, I am working on fixes and it will land in main eventually. I want you to think about the following though; here is everything that i want to do with this pr: 1) i want to incorperate this "infinite agent" as a usage agent inside of the vidbyte-cli/. I want to give people the ability to run this infinite memory agent. 2) I dont just want them to be able to run the agent, i want them to be able to, given that these agents may be running for a long time, see alll of the agents that are running and which ones have ran/what they produced. I want to do  this in the following way:  2.1) i want to sync the "infinite memory agents" to the vidbyte/ repo. when the user runs them in the cli I want to sync the prompt, actions, and result of the infinite memory agent to vidbyte's database for the user's api and have a page (lets say "/agents/dashboard"), where the user can see the "artifacts" that each one of these infinite agents produce. Apart from syncing the agent to the database, I think that I want to create a custom trace tailor made to the architecture of the InfiniteMemoryAgent (see how tracing abstraction, the trace should be a high level action trace that is tailor made to the agent (without the user of another agent), things like, "subagent launched: launched a subagent with message ....", "memory created: ...", "file created....", "agent {name} finished", think of all the actual events we can add to the architecture of the infinite memory agent, thinkk about what content should be displayed in each of them, and then how to for each of these events store them in the vidbyte/ database (and also discuss if it is a good idea to store the raw turns as well), then also I want the infinite memory agent to create a "handoff" as another artifact after the run 2.2) I want to promote this agent as a usage-based agent on the "/agents" and "/agents/marketplace" vidbyte/ frontend repo.


so, what are all of the best ways to do this, dont want you to implement just walk me through optimal  implementation of everything
````

**Prompt 4** (the invoking prompt of this pipeline, sent after the design walkthrough reproduced in §B):
````
Yeah I think that a class that implements all events, customly and native to the infinite memory agent, is the right approach to take. Then maybe at certain points thoughtout the run we can "checkpoint" the agent with the vidbyte/ backend when we run it on the cli (once every 50 iterations or something, or however you see fit to this). Make sure dashboard page too generates tokens server side and pass no sensitive info to client, you can make all the prs in each repo using the skill. Also, with the "next step" suggestions can you try to focus on vidbyte-cli/. Feel like we could implement/add more here with the cli
````

## B. Handoff block and decision ledger (verbatim)

No `## HANDOFF —` block was emitted. The design walkthrough the user answered with Prompt 4 is reproduced in full below, including its Re-entry ledger (assistant text, re-transcribed by the orchestrator: substance identical, minor wording may differ from the message the user saw). Two facts changed after it was written, recorded in §C: the #1084 branch already adopted `api_keys`/`vidbyte_api_key`/`model_mode`, and Prompt 4 renamed the sync call a "checkpoint". Prompt 4 accepted it ("a class that implements all events ... is the right approach") and added the checkpoint idea, the server-side token requirement, and the instruction to open PRs in each repo. The three "Needs you" questions were not answered explicitly; §C records the defaults the orchestrator applied.

`````
**Vidbyte-SDK · vidbyte-cli-internal · Vidbyte · main · infinite-memory-cli-dashboard**
Status: Needs you — **extend the agent-run sync your backend already has**, feed it from a native `InfiniteEvents` sink in the SDK (not the tracer, not the journal), and ship it through an outbox in the CLI; three product calls are yours.

### What you are really deciding

Three load-bearing choices; everything else follows the repo's grain. (1) Where events originate — the tracer can't carry them and the journal lacks most of them, so it's a new emission seam inside the agent. (2) How events reach Mongo given crashes and resume — this decides the idempotency key. (3) What to store — high-level events, the workspace files and a handoff fit in Mongo; raw turns don't.

### The premise is half-built already

`POST /api/v1/agent-runs`, `…/{encrypted_id}/records`, `PUT …/finish` exist on Vidbyte main (PR #667), with `agent_runs` + `agent_run_records` collections, 90-day TTL, `runtime:write` API-key auth, idempotent start (`Idempotency-Key`) and first-write-wins records (`_id = "<run_id>:<ordinal>"`). The CLI never calls them. Their own headers mark this design as the follow-up: `backend/routes/agent_runs.py` "do not add a read route here" (reads go Next.js → Mongo, the house pattern), `indexes/agent_runs.py:12-13` defers "the list, workflow and repo indexes" to "the follow-up page". So this is an extension, not a second sync path — but three existing guards have to be changed on purpose, with a spec edit: `dtos/agent_runs.py:17` ("do not add a … trace field"), records "never read back" (`queries/agent_runs.py:91`), and `sync.py:15` (records never write the run document).

### 1. SDK — a native event sink and a handoff builder

The tracer can't carry this: `TracerBase` is span-only with a string output (`lib/tracing/base.py:16-50`), `llm.call` spans carry full message histories, and every subagent gets `NullTracer` (`[PR] launch.py:285-298`). The journal can't either: `.runs/<id>.jsonl` holds 4 of the 14 events below and is fsynced under a global lock as the resume source of truth (`journal.py:176-192`). Copy the single-writer pattern of `JevResponse` (`agents/jev/response.py`): one class owns every event, one method per event, called from the sites in `launch.py` and `memory.py` (outside the workspace lock).

```python
# settings.py — the only new public knob
on_event: Callable[[InfiniteEvent], None] | None = None

@dataclass(frozen=True, slots=True)
class InfiniteEvent:
    kind: InfiniteEventKind      # enum, 14 members
    run_id: str                  # the journal's run id
    agent_key: str               # "root", "root/pricing/gen", "root/pricing/gen/sub/ver"
    role: InfiniteAgentRole
    depth: int
    at: datetime                 # UTC, millisecond precision (journal is seconds)
    summary: str                 # one display line, ≤280 chars, built from constants
    details: InfiniteEventDetails  # one frozen record per kind
```

The emitter wraps every `on_event` call in `try/except` and swallows: an observer must never break a run. Also: wrap `runtime.py:101` so a failed or cancelled run emits `run_stopped` then re-raises (journal untouched, still resumable); put the journal run id on `reply.metadata` (today the caller never learns it); and — while you're in #1084 — `main` replaced `api_key` with `api_keys`/`vidbyte_api_key`/`model_mode` with no alias, and the PR still passes `api_key=` at `agent.py:73` and `launch.py:290`. Passing all three through to every child is what makes every generator and verifier call bill through the gateway at rate + 2% (`TextModelMode.AUTO` already routes through it when a Vidbyte key is present, `vidbyte/agents/README.md:56`). That one fix is the entire "usage agent" billing story.

**The 14 events.** One rule picks them: **emit at each state-changing agent action; summarize outcomes at pair finish.** Tool calls (bash/grep/read_lines) and model calls are deliberately excluded; they are raw-turn level and would turn a readable trace into a log.

| Event | Fires at (PR #1084) | Display line | Details (caps) |
|---|---|---|---|
| `run_started` | runtime.py:82 (new journal) | "Run started — *task…*" | task excerpt ≤500, model, preset, limits, extras, seed names |
| `run_resumed` | runtime.py:82 (`self.resuming`) | "Resumed — 4 tasks done earlier, 1 will rerun" | finished count, interrupted keys |
| `run_finished` | runtime.py:105 | "Finished (final_response) — *answer first line*" | stop_reason, answer ≤2,000, totals, usage |
| `run_stopped` | new try around runtime.py:101 | "Stopped (cancelled) — resume with…" | reason `failed\|cancelled`, error code, message ≤500 |
| `batch_rejected` | launch.py:127 | "launch_subagent refused: *problem*" | launcher key, problem ≤500 |
| `subagent_launched` | launch.py:133 | "root launched **pricing**: *goal*" | name, parent, depth, goal ≤1k, criteria ≤10×300, both prompts ≤2k, context refs, granted tools |
| `subagent_replayed` | launch.py:143-148 | "pricing already finished — result reused" | status, verdict |
| `generator_finished` | launch.py:232 | "pricing generator: done — *summary*" | status, stop_reason, summary ≤1,600, tool_calls, usage, duration |
| `subagent_finished` | launch.py:358 | "pricing: **passed** — 2 memories saved, 1 dropped, 1 file" | verdict, review ≤1,600, committed `[{staged_key, entry_id, kind, text}]`, dropped `[{key, text, reason: verifier\|unchecked\|rule}]`, files, usage (gen+ver) |
| `memory_saved` | memory.py:85 (root) | "Memory #12 (decision): …" | id, kind, text, tags, refs, supersedes |
| `memory_staged` | memory.py:88-92 | "pricing/gen proposed s1 (fact): … — awaiting verifier" | staged key, kind, text, supersedes |
| `memory_dropped` | memory.py:114 | "pricing/ver dropped s2: …" | key, text |
| `file_written` | memory.py:96 / :104 | "pricing/gen created notes/pricing.md — *description*" | path, change `created\|appended\|edited`, added chars, excerpt ≤500 |
| `tool_refused` | memory.py:161/215/248/273 | "remember refused for pricing/gen: quota used" | tool, problem ≤300 |

There is no `verifier_started`: "verifying" is derived (a `generator_finished` whose status ≠ failed with no `subagent_finished` yet). `dropped` gets a reason enum because today's card mixes three reasons into free text.

### 2. CLI — `vidbyte-cli agents infinite-memory run | resume`

**Command.** Copy `agents suggest` — the only gateway-metered sibling; it already gets `--model`, `--reasoning-effort`, `--send-to` and the local runs ledger through `AgentCommand` (`agents/agent_command.py:3-8`). Lazy SDK adapter in `services/infinite_memory/sdk.py` (C011). The CLI passes its resolved Vidbyte key as `vidbyte_api_key` — no CLI gateway code at all. Needs a release containing #1084, then the `>=0.3.0,<0.4` pin bump and re-vendored SDK API and platform contract (C028/C029/C030). Foreground run; `resume` is the crash story — the CLI has no daemon, and MCP jobs die with their server (`services/mcp/process.py:3-7`). `resume` continues whatever is unfinished: the agent run, or only its sync.

**Sync service** in `services/agent_runs/`, used by this agent only (not `AgentCommand`-wide: `skills/agent-building/SKILL.md:108-112` says local agents "must **never** send task content to the backend"; the gateway-metered exception requires the card to say so — a CLI-wide hook would violate it for bug-finder and the rest).

1. The sink receives each `InfiniteEvent`, assigns `seq`, applies the credential scrubber to text fields, and appends a line to `data_root/infinite-memory/<run_id>/outbox.jsonl` (outbox pattern; bug-finder's `data_root/<agent>` precedent). Thread-safe append; fsync per flush, not per event.
2. On `run_started`, an in-process uploader calls `start` with `Idempotency-Key = <journal run id>` — a resume (even from another machine with the workspace) maps to the same backend run.
3. Every 10 s while events are pending, and ≥ every 60 s as a heartbeat: `POST …/events` with ≤200 events + cumulative `progress`. Honor `Retry-After`. **Sync failure never fails the run** — the outbox holds the data; the dashboard shows the heartbeat as stale.
4. At the end: flush, upload the handoff record (ordinal 0) and one record per note file (ordinals 1..N in sorted path order, so a retry is idempotent), then `finish` last as the existing contract requires.
5. **Budget:** on each event, compare `agent.get_usage().cost_usd` with `--max-cost-usd`; over budget → cancel the run task. The journal stays resumable; `finish` gets `cancelled` with `error_code: budget_exceeded`. Overshoot is bounded by the in-flight pairs, because a child's usage merges into the root only when it finishes (`base.py:896-904`) — say so in the help text.

**Resume-safe sequence numbers.** `start` returns `last_seq` (new field); the sink continues from `max(outbox tail, last_seq) + 1`. Without this, a resume from a fresh machine restarts `seq` at 0, collides with stored `<run_id>:<seq>` ids, and first-write-wins silently drops the new events.

### 3. Backend — extend `agent_runs`

`AgentRunWorkflow.INFINITE_MEMORY`, `AgentRunRecordKind.ARTIFACT`, a `POST /api/v1/agent-runs/{encrypted_id}/events` route on the same router and `RouteRule`, and a child collection copying `research_action_trace_events` (one document per event, a typed `action`, a bounded `summary`, typed `details` — `dtos/research_action_trace.py:167-174`):

```python
# agent_run_events — bulkWrite of $setOnInsert upserts (ordered=False): a retried batch is a no-op
{_id: "<run_id>:<seq>", user_id, run_id, seq, kind, at, recorded_at,
 agent_key, role, depth, summary, details, expires_at}   # expires_at copied from the run

agent_run_events_owner_run_seq  {user_id: 1, run_id: 1, seq: 1}       # timeline keyset; owner-first (B077)
agent_run_events_expires_ttl    {expires_at: 1}, expireAfterSeconds: 0
agent_runs_owner_started        {user_id: 1, started_at: -1, _id: -1} # dashboard list keyset
```

Timeline read: `find({user_id, run_id, seq: {$gt: after}}).sort({seq: 1}).limit(251)` — equality, equality, then sort+range on `seq`; not covering, fine at ≤250 docs. `details` is a pydantic discriminated union on `kind` (`extra="forbid"`), so a new event kind is a coordinated change, backend first; the CLI maps SDK events onto the kinds in its vendored contract and drops unknown ones, so a newer SDK never causes 422s.

The same events call updates the run document: `last_seq`, `heartbeat_at`, `progress{pairs_started, pairs_finished, entries, files, tokens, cost_usd}`, all with **`$max`** (idempotent under retries and out-of-order batches), filtered `{_id, user_id, status: "running"}` — a late batch after `finish` gets 409. "Stalled" is derived on read (`running` and `heartbeat_at` older than 5 min), never written; this closes the crashed-run-shows-running-for-90-days gap.

**Workspace files fit in Mongo, so no S3 yet.** The agent's own caps bound them: 250k tokens ≈ 1M chars total, 20k tokens ≈ 80k chars per file. One record holds 24 × 16k = 384k chars and a run allows 2,000 records, so each note is one record (title = path, sections = chunks), zstd-compressed under the existing TTL. Only paths in `files.jsonl` are uploaded, not files `bash` wrote. Operator steps: `scripts/manage_indexes.py agent-run-indexes`, a `collMod` for the validator, and a regenerated platform contract.

### 4. Raw turns — not in Mongo

History is re-sent each call (up to 60k tokens) and tool results are capped at 100k chars, so even storing only deltas, one large run (200 agents × ≤100 iterations) can reach hundreds of MB, against about 1 MB for the high-level events. Policy agrees: research traces declare "raw model/provider data is impossible" (`dtos/research_action_trace.py:5`), and bash output routinely contains secrets the event scrubber never sees. **Flip condition:** if you want raw turns for support debugging or trace sales, the path is SDK tracer pass-through to children (`fork.py:82` already does `tracer=agent._tracer`) → a local transcript file → explicit opt-in upload to object storage with `HarnessRedactor` — its own project, with a consent step.

### 5. The handoff — deterministic, no model call

Subclass the SDK's `Handoff` (`context/handoff/base.py:22`) as `InfiniteHandoff`, built from the journal's cards, this run's entries and files, and the root's final answer — which already is the model-written summary, so an extra paid call would repeat it. Sections: **Outcome** (answer, stop reason) · **Work done** (one line per task card) · **Decisions** · **Facts** · **Lessons** · **Open questions** · **Files** (paths + descriptions) · **Unverified or failed work** · **How to continue** (the exact `run --workspace …` or `resume` command). Uploaded as record kind `handoff` ordinal 0, written locally to `.runs/<run_id>.handoff.md` (grep skips it), and delivered by `--send-to` (add it to `OUTPUT_TEXT_RESULT_KINDS`).

### 6. Frontend

**`/agents/dashboard`** — copy `app/research/page.jsx`: `force-dynamic`, `noStore`, noindex, degrade-to-empty; listed in `middleware.js` `protectedRoutes` and `matcher` (N049); kept out of the sitemap and `publicPaths`. Reads go through new Mongoose mirrors `AgentRun.js` / `AgentRunEvent.js` / `AgentRunRecord.js` with matching index names and key order (`database/models/ResearchActionTraceEvent.js:4-9`). The list is all `agent_runs` rows, not only this agent: workflow badge, derived status (incl. "stalled"), task, duration, progress, cost; refreshed with `router.refresh()` every 15 s while any run is running (`StatusBoard.jsx` pattern).

**`/agents/dashboard/[encryptedId]`** (N048) — left rail: the agent tree from grouping `agent_key`; right: the timeline plus a detail pane in the layout of `ResearchArtifactTrace.jsx`, built route-local in `_components/` (the research component is coupled to research fields and uses `uppercase`, which N036 forbids); SWR polling of a no-store route handler `app/api/agents/runs/[runId]/events/route.js` by `after_seq` (`useResearchRun.js` pattern), stopping at a terminal status; tabs Timeline · Memories (from events) · Files (`SkillMarkdown` for `.md`, `MintlifyCodeBlock` otherwise) · Handoff. A pure model module maps kind → label, icon and allowlisted fields, so a Python contract test can execute it. N047 allowlist: drop `run_id`, `user_id`, `api_key_id`, `idempotency_key`; expose the journal id as `resume_id` so a stalled run prints its exact resume command.

**Marketplace** — `constants/agents/infinite-memory-agent/catalog.js` copied from `suggestion-agent/catalog.js` (Usage-based), one `AGENT_CATALOG` line, an `ART_BY_SLUG` scene, `publicPaths`. Ship it as `status: "planned"` until the CLI command is in the vendored `cli-commands.json` (N050 blocks the commands section until then). The product page states that prompts, events and results are stored for 90 days (the product-type rule). Add "Dashboard" to the "Surfaces" column and a signed-in button in `AgentHeroActions`.

### Pre-mortem — the one that bites first

**The rate limit kills the agent before sync matters.** `models.generate` and the agent-run routes share `API_KEY_STANDARD` (`route_rules.py:163`): 120 requests per hour at `tier_0` (`lib/enums/api_keys.py`). Ten parallel pairs × 2 agents × ~30 iterations ≈ 600 model calls in roughly the first 10 minutes, so a run hits 429 within minutes and waits on `Retry-After`. Gateway calls are already money-guarded (wallet balance, $100/day cap), so a request count per hour is the wrong guard for them. Measure a real 10-parallel run, then give metered generation and the agent-run sync routes their own bucket. Smaller ones: two processes resuming one run concurrently would read the same `last_seq` (guard: the runs ledger's existing per-run lock); clock skew between machines (order by `seq`, never by `at`).

**Scale.** A typical run of about 20 pairs is about 200 events × ~1 KB; the largest (200 agents) about 1,100. At 100× — say 10k runs a month — that is about 6M live event documents under the TTL (≈6 GB plus ≈0.5 GB of index), and files at most 1 MB per run, usually far less after zstd. The lever if that grows is a shorter TTL for events and files, or object storage for file bodies; measure first.

**Ship order:** SDK (#1084 with the `api_keys` fix, then a follow-up PR with events, `run_stopped`, the run id and the handoff; release) → backend (deploy, then the operator runs indexes and the validator) → CLI (release) → frontend dashboard, then the catalog flips to `available` once `cli-commands.json` is re-vendored. The catalog entry can ship as `planned` at any time.

Checked: CLI `agent_command.py`, `skills/agent-building/SKILL.md`, client/retry and runs ledger; backend `routes/agent_runs.py`, `lib/enums/agent_runs.py`, `dtos/agent_runs.py`, `route_rules.py:163`, `lib/enums/api_keys.py`, the index manifests, the research trace DTO; SDK `lib/tracing/base.py`, `agents/README.md:50-58`, `base.py:105-107`, `context/handoff/base.py`, and the #1084 files `runtime.py`, `launch.py`, `memory.py`, `journal.py`, `agent.py`; frontend catalog, `research/page.jsx`, `useResearchRun.js`, `StatusBoard.jsx`, `middleware.js` — all at `origin/main` or the PR head `1f445405`. Rejected: an SDK tracer exporter (span-only, carries raw messages, children get `NullTracer`); tailing the journal (4 of 14 events; fsynced and locked because resume depends on it); sync on `AgentCommand` for every agent (breaks the product-type rule); events as `agent_run_records` (sections-shaped, capped at 2,000 ordinals, never read back); an events array on `agent_runs` (unbounded); S3/R2 now (the workspace caps keep files small enough for Mongo); a model-written handoff (a paid call that repeats the root's answer); a detached daemon (resume makes crashes cheap, and the Windows Job Object kills the process tree anyway).

---
**Re-entry · infinite-memory-cli-dashboard**
Decided: SDK `on_event` sink with 14 typed events (single writer, like `JevResponse`); journal unchanged; deterministic `InfiniteHandoff`; #1084 adopts `api_keys`/`vidbyte_api_key`/`model_mode` (gateway billing) · Backend: extend `agent_runs` with `/events`, `agent_run_events` (`_id = run:seq`, owner-first index, TTL), `$max` progress and heartbeat, `last_seq` on start, `ARTIFACT` record kind, list index · CLI: `agents infinite-memory run|resume`, outbox plus uploader, sync scoped to this agent, budget by cancellation · Frontend: protected `/agents/dashboard` list and detail read straight from Mongo (tree, timeline, memories, files, handoff); catalog entry shipped `planned` first · Raw turns not stored in Mongo.
Open: the size of the separate rate-limit bucket (needs a measured run).
Needs you: 1. Sync on by default, with `--no-sync` and a first-run notice? — default: **yes**  2. Separate rate-limit bucket for metered generation and agent-run sync, sized from a measured run? — default: **yes**  3. Default `--max-cost-usd`? — default: **$5**
*Reply "go" to accept all defaults.*
Next: on your reply I write four HANDOFF prompts — SDK, backend, CLI, frontend — in ship order; "save" writes each to `docs/pre-design/` in its repo.
`````

## C. Structured conversation notes

### Three sibling pipeline runs (one per repository; they never share a worktree)
| Run | Repository | Worktree | Branch | Base / PR base | Scope |
|---|---|---|---|---|---|
| SDK | `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` (cerredz/Vidbyte-SDK) | `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-events` | `feat/infinite-memory-events` | `origin/feat/infinite-memory-agent` @ `ff1bc933` (PR #1084, not yet on main) | the native event class, `on_event`, `run_stopped`, run id on the reply, the deterministic handoff |
| Vidbyte | `C:/Users/422mi/vidbyte-repos/vidbyte` (cerredz/Vidbyte) | `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-agent-run-dashboard` | `feat/agent-run-dashboard` | `origin/main` @ `acf4016af` | backend checkpoint ingest on `agent_runs`; `/agents/dashboard` list + run detail; marketplace listing |
| CLI | `C:/Users/422mi/vidbyte-repos/vidbyte-cli` (cerredz/vidbyte-cli-internal) | `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-infinite-memory-agent-command` | `feat/infinite-memory-agent-command` | `origin/main` @ `64b04b3` | `vidbyte-cli agents infinite-memory run / resume`, the checkpoint sync service, budget, handoff output |

Each run builds only its own scope. The cross-repo contract below is fixed by the orchestrator so the three specs agree; a run may refine names that are internal to its repo, never the contract names.

### Cross-repo contract — SDK → CLI (Python API)
- `InfiniteMemoryAgentSettings.on_event: Callable[[InfiniteEvent], None] | None = None` — the only new public settings field.
- `InfiniteEvent` — frozen validated dataclass in `vidbyte/lib/dataclasses/infinite.py`. Fields: `kind: InfiniteEventKind`, `run_id: str` (the journal run id), `agent_key: str` ("root", "root/pricing/gen", nested "root/pricing/gen/sub/ver"), `role: InfiniteAgentRole`, `depth: int`, `at: datetime` (UTC, millisecond precision), `summary: str` (one display line, ≤ 280 chars, built from constants, never a model call), `details` (per-kind content). It has no `to_dict()` (the header of `vidbyte/lib/dataclasses/infinite.py` forbids serialization methods on lib records). Instead every field of `InfiniteEvent` and of its `details` record is JSON-representable after `dataclasses.asdict` (only str, int, float, bool, None, tuples/lists, str-valued enums, and `datetime`); the CLI serializes with `dataclasses.asdict`, turning enums into their values and datetimes into ISO-8601 UTC with milliseconds and a trailing `Z`. Usage inside details is primitive fields (`tokens: int`, `cost_usd: float | None`), never an SDK usage object.
- `InfiniteEventKind` — `str` enum in `vidbyte/lib/enums/infinite.py` with exactly these 14 values: `run_started`, `run_resumed`, `run_finished`, `run_stopped`, `batch_rejected`, `subagent_launched`, `subagent_replayed`, `generator_finished`, `subagent_finished`, `memory_saved`, `memory_staged`, `memory_dropped`, `file_written`, `tool_refused`. Per-kind details and caps are the table in §B ("The 14 events").
- The single class that implements every event: `InfiniteEvents` in `vidbyte/agents/infinite/events.py`, one method per event kind, the one writer of events (pattern: `vidbyte/agents/jev/response.py`, `JevResponse`). Call sites in `launch.py`, `memory.py`, `runtime.py` call its methods outside the workspace lock.
- A sink exception never reaches the run (caught and swallowed by `InfiniteEvents`). No event is produced by a model call.
- `run_stopped` is emitted when a run fails or is cancelled (including `KeyboardInterrupt`/`asyncio.CancelledError`), then the original exception is re-raised; the journal is untouched so the run stays resumable.
- `reply.metadata["infinite_run_id"]` carries the journal run id for every run and resume.
- `InfiniteHandoff` — subclass of `vidbyte.context.handoff.base.Handoff`; `InfiniteMemoryAgent.run_handoff(run_id: str | None = None) -> InfiniteHandoff` (named `run_handoff`, not `handoff`, because `BaseAgent.handoff` already exists at `vidbyte/agents/base.py:1222` as an async model-calling method and must not be overridden incompatibly) builds it deterministically (no model call) from the journal's cards, the run's entries and files, and the root's final answer; also written to `<workspace>/.runs/<run_id>.handoff.md`. Sections, in order: Outcome · Work done · Decisions · Facts · Lessons · Open questions · Files · Unverified or failed work · How to continue.
- New public names exported from `vidbyte` and `vidbyte.agents`: `InfiniteEvent`, `InfiniteEventKind`, `InfiniteHandoff`.

### Cross-repo contract — CLI → Vidbyte backend (HTTP, API key, scope `runtime:write`)
- **Start (existing route, extended):** `POST /api/v1/agent-runs` with `workflow: "infinite_memory"` (new `AgentRunWorkflow` member), `client_run_id` = the journal run id, header `Idempotency-Key` = the journal run id (a resume, even from another machine with the same workspace, returns the same backend run). `request.goal_or_task` = the task; `request.settings` = model, provider, preset, limits; `request.context_manifest` = the seed files (`kind`, `source`, `chars`, `sha256`). The response gains `last_seq: int` (highest stored event seq; `0` when none). Event `seq` starts at 1.
- **Checkpoint (new route):** `POST /api/v1/agent-runs/{encrypted_id}/checkpoints`, body `{"events": [AgentRunEvent, ... ≤ 200], "progress": AgentRunProgress}`; `events` may be empty (a heartbeat). Response `{"encrypted_id", "status", "last_seq"}`. Each event is upserted with `$setOnInsert` under `_id = "<run_id>:<seq>"` (a retried checkpoint is a no-op). `progress` fields and `heartbeat_at` (server time) are written with `$max`. The run document also keeps the latest event (kind, summary, at) of the highest seq, written so an out-of-order or retried checkpoint never moves it backwards. A checkpoint after `finish` gets 409 `agent_run_already_finished`.
- **AgentRunEvent:** `seq` (int ≥ 1, below a per-run cap), `kind` (the 14 values above, as backend enum `AgentRunEventKind`), `at` (ISO-8601 UTC), `agent_key` (bounded string), `role` (`root` | `generator` | `verifier`), `depth` (int ≥ 0), `summary` (1–280 chars), `details` (a JSON object bounded by a compact-UTF-8 byte cap, validated like `AgentRunRequestDto.settings` in `backend/lib/dtos/agent_runs.py` — not one schema per kind; the kind enum is strict, so a new kind is a coordinated change, backend first).
- **AgentRunProgress** (cumulative, so `$max` is correct): `pairs_started`, `pairs_finished`, `entries`, `files`, `tokens`, `cost_usd_micros` (all ints ≥ 0).
- **Records (existing route, extended):** new `AgentRunRecordKind.ARTIFACT` = one workspace note file: `title` = workspace-relative path, `sections` = the content in chunks of ≤ 16,000 chars, `agent_name` = the writer's agent key, `truncated` when cut. `handoff` (existing kind) = the `InfiniteHandoff`, ordinal 0. Artifacts take ordinals 1..N in sorted path order, so a retried upload is idempotent. Only files listed in the workspace's `files.jsonl` are uploaded, never files `bash` wrote.
- **Finish (existing route):** sent only after the journal records `run_finished`, after the last checkpoint, the handoff and the artifacts. Status mapping: stop reason `final_response` or `is_done` → `completed`; `max_iterations` → `partial`; anything else → `failed`. An interrupted, failed, or budget-cancelled run is **not** finished: it stays `running` so a later `resume` can keep checkpointing into it. The dashboard derives "interrupted (resumable)" when the latest event is `run_stopped`, and "stalled" when `heartbeat_at` is older than 10 minutes and the latest event is not terminal. Neither is ever written to the database.

### Checkpoint cadence (the user's "once every 50 iterations or something, or however you see fit")
The CLI sends a checkpoint: right after `start` on `run_started` / `run_resumed`; whenever a `subagent_finished` arrives; whenever 50 events are buffered; at least every 120 s while the run is live (heartbeat, may carry no events); and on `run_stopped` / `run_finished` (final flush). Non-terminal checkpoints are coalesced to at most one per 15 s. Root iterations are not directly observable from outside the agent, so "every 50 events" stands in for "every 50 iterations". All of these numbers are constants in the CLI's constants location. At the maximum rate this is ≤ 240 checkpoints per hour per run.

### Key decisions
- A native event class inside InfiniteMemoryAgent is the trace — the user: "a class that implements all events, customly and native to the infinite memory agent, is the right approach to take." Not the SDK tracer, not the journal.
- Checkpoints carry events + progress and double as the heartbeat; the journal stays the only resume source of truth (resume never reads from the backend).
- Sync is scoped to this agent (not `AgentCommand`-wide) because `vidbyte-cli/skills/agent-building/SKILL.md:108-112` forbids local agents from sending task content except gateway-metered ones whose card says so.
- Billing: the CLI passes its resolved Vidbyte key as `vidbyte_api_key`; with `TextModelMode.AUTO` every generator and verifier call goes through `POST /api/v1/models/generate` at the model's rate + 2%. No CLI gateway code.
- Handoff: deterministic, no model call; the root's final answer is the narrative.
- Raw model turns are not stored anywhere in this work (size and policy; see §B "Raw turns").
- Workspace note files are stored inline in Mongo as `artifact` records (the agent's own caps bound them: ≤ ~1M chars total, ≤ ~80k chars per file), uploaded once at the end with the handoff. Interrupted runs show events only.
- Dashboard reads go Next.js → Mongo through Mongoose mirrors (house pattern; `backend/routes/agent_runs.py` forbids a read route). The list shows every `agent_runs` row, any workflow.
- The dashboard's polling and any server action use tokens generated server-side, and the client receives only allowlisted fields — the user: "Make sure dashboard page too generates tokens server side and pass no sensitive info to client".
- Marketplace entry ships `status: "planned"` until the CLI command exists in Vidbyte's vendored `lint/contracts/cli-commands.json` (lint N050).
- Foreground `run`; `resume` continues whatever is unfinished: the agent run, or only its sync (pending checkpoints, handoff, artifacts, finish).

### Defaults the orchestrator applied (the user did not answer these three; logged in pipeline.md)
1. Sync is on by default; `--no-sync` turns it off; a one-time notice says prompts, events and results are stored in the user's Vidbyte account for 90 days.
2. Separate rate limit: the agent-run sync routes (start, checkpoints, records, finish) get their own throttle bucket so checkpoints never compete with model calls. The `models.generate` throttle is **not** changed in this work: it is a money-sensitive shared route and the user did not confirm. A heavy run at `tier_0` (120 requests/hour shared with `models.generate`) can hit 429; that is a stated limitation to measure before launch.
3. `--max-cost-usd` defaults to 5. Over budget, the CLI cancels the run (the journal stays resumable); overshoot is bounded by the pairs still in flight.

### Rejected alternatives
- SDK tracer exporter — span-only API with a string output, `llm.call` spans carry raw message histories, every subagent gets `NullTracer`.
- Tailing the journal — has 4 of the 14 events; fsynced under a global lock because resume depends on it; its header forbids writing settings into a record.
- Sync wired into `AgentCommand` for every agent — breaks the product-type rule above.
- Events as `agent_run_records` — records are handoff-shaped sections, capped at 2,000 ordinals, first-write-wins, never read back.
- An events array on the `agent_runs` document — unbounded growth.
- S3/R2 object storage now — the workspace caps keep files small enough for Mongo.
- A model-written handoff — a paid call that repeats the root's answer.
- A detached background daemon — `resume` makes crashes cheap; Windows Job Objects kill the process tree.
- Finishing an interrupted run as `cancelled` — `finish` only matches `running`, so a later resume could never checkpoint again.

### Constraints and assumptions
- The InfiniteMemoryAgent code exists only on `feat/infinite-memory-agent` (PR #1084, head `ff1bc933`), which the user is still fixing and merging main into; it "will land in main eventually". The #1084 branch already passes `api_keys`, `vidbyte_api_key`, `model_mode` to every child (`vidbyte/agents/infinite/agent.py:73-74`, `launch.py:290-291`).
- Existing backend agent-run sync (Vidbyte PR #667): `backend/routes/agent_runs.py`, `backend/services/agent_runs/sync.py`, `backend/database/queries/agent_runs.py`, `backend/database/indexes/agent_runs.py`, `backend/lib/dtos/agent_runs.py`, `backend/lib/enums/agent_runs.py`, `backend/lib/config/agent_runs.py`, `backend/lib/errors/agent_runs.py`, tests in `backend/tests/features/agent_runs`. 90-day TTL; unpriced; `API_KEY_STANDARD` throttle today.
- `tier_0` API keys allow 120 requests/hour (`backend/lib/enums/api_keys.py`), shared by every `API_KEY_STANDARD` route.
- There is no blob storage and no push channel (SSE/websocket) for product data; the web app polls.
- The CLI's live paid key is in the OS keyring: tests must never call the real backend or a real model.

### Clarifications and answers
- Q: Should events come from a native class or the tracer? — A: "Yeah I think that a class that implements all events, customly and native to the infinite memory agent, is the right approach to take."
- Q: How often should the CLI sync? — A: "at certain points thoughtout the run we can "checkpoint" the agent with the vidbyte/ backend when we run it on the cli (once every 50 iterations or something, or however you see fit to this)."
- Q: Dashboard security? — A: "Make sure dashboard page too generates tokens server side and pass no sensitive info to client"
- Q: Store raw turns? — The walkthrough recommended not storing them; the user did not object.

### Terminology
- **checkpoint** — one CLI → backend call carrying the events since the last acknowledged one plus cumulative progress; it is also the heartbeat. Not a resume checkpoint (resume reads only the local journal).
- **run id** — the InfiniteMemoryAgent journal id (shape `20261015T150131Z-f4cc56a3`), used as `client_run_id` and `Idempotency-Key`.
- **pair** — one generator + verifier launched by `launch_subagent` for one task card; **agent key** — `root`, `root/<task>/gen`, `root/<task>/ver`, nested `…/gen/<task>/…`.
- **entry / memory** — a short typed record in `entries.jsonl` (`decision`, `fact`, `lesson`, `open_question`, `pointer`); **staged** — held in memory until the pair's verdict; **note / file** — a workspace file written by `write_note` / `edit_file`.
- **artifact** — a workspace note file uploaded to the backend as an `artifact` record; the **handoff** is the other artifact.
- **usage-based agent** — billed per model call through the gateway (marketplace tag `USAGE`, label "Usage-based").

### Implementation hints
- SDK single-writer precedent: `vidbyte/agents/jev/response.py`. Event sites: `[PR] runtime.py:82,101,105`, `launch.py:127,133,143-148,232,246-247,338-359`, `memory.py:85,88-92,96,104,114,161,215,248,273`. `Handoff` base: `vidbyte/context/handoff/base.py:22`.
- CLI sibling: `agents suggest` (`commands/agents/suggestion/suggest.py`, `services/suggestions/sdk.py`, `lib/constants/suggestions.py`); `AgentCommand` (`commands/agents/agent_command.py`); registration checklist `skills/agent-building/references/registration-points.md`; durable data dir precedent `services/bug_finder/ledger.py`; `ApiClient` + typed endpoint groups in `lib/api/endpoints/`; `--send-to` result shaping `services/outputs/service.py:205-219`, `types/outputs.py:34-36`.
- Backend sibling for an event collection: `research_action_trace_events` (`backend/database/queries/research/action_traces.py`, `backend/database/indexes/research.py:25-39`, `backend/lib/dtos/research_action_trace.py`). Routes + rule: `backend/lib/app/route_rules.py:164-167`; index manifests installed by an operator via `scripts/manage_indexes.py`.
- Frontend siblings: `next-app/app/research/page.jsx` (server page), `next-app/components/Research/useResearchRun.js` + `next-app/app/api/research/runs/[runId]/route.js` (SWR polling a no-store route handler), `next-app/app/status/_client/StatusBoard.jsx` + `statusBoardModel.js` (refresh + pure model), `next-app/components/Research/ResearchArtifactTrace.jsx` (timeline layout), `next-app/app/agents/skills/_components/SkillMarkdown.jsx`, `next-app/constants/agents/suggestion-agent/catalog.js`, `next-app/middleware.js`, `next-app/database/models/ResearchActionTraceEvent.js`.

### Open questions (resolve from the code, or carry as Q-n with the stated default)
- Exact byte cap for `details` and the per-run event cap (backend; default: pick from the precedent caps in `backend/lib/config/agent_runs.py`, with a reason).
- Size of the new sync throttle bucket (backend; default: large enough for one run at the maximum checkpoint rate plus start/records/finish, with a reason).
- Workspace default location and model default for the CLI command (CLI; default: follow `agents suggest` constants for the model; a workspace folder under the current directory).

## D. Weighted words
- "see alll of the agents that are running and which ones have ran/what they produced" — Prompt 3
- "the trace should be a high level action trace that is tailor made to the agent (without the user of another agent)" — Prompt 3
- "think of all the actual events we can add to the architecture of the infinite memory agent" — Prompt 3
- "I want the infinite memory agent to create a "handoff" as another artifact after the run" — Prompt 3
- "a class that implements all events, customly and native to the infinite memory agent" — Prompt 4
- "once every 50 iterations or something, or however you see fit to this" — Prompt 4
- "Make sure dashboard page too generates tokens server side and pass no sensitive info to client" — Prompt 4
- "you can make all the prs in each repo using the skill" — Prompt 4
