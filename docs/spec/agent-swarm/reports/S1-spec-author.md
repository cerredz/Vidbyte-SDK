# S1 spec author report — agent-swarm (spec r1)

Spec: `docs/spec/agent-swarm/spec.md` (revision 1, base `0f2aeb48`). Inputs: `request.md`, `context/code-map.md`, `reports/S0-scout.md`, the spec template, and the code listed below. No production code or tests were written.

## What I read (beyond the scout's map)

- `AGENTS.md` in full; `REPO_MAP.md` agent entries; the template at `~/.claude-work/skills/spec-pipeline/references/spec-template.md`.
- The loop's finish and delivery paths in `vidbyte/agents/runtime.py`: `:460-480` (iteration outputs published to `run_state`), `:540-708` (both finish points, `review_finish`, `_continue_finish_attempt`, `_after_tool_iteration`), `:1160-1202` (`_middleware_context`: snapshot copies of messages, live `run_state`), `:1770-1800` (`after_tool_call` gets `tool_call`, `tool_result`, `tool_is_internal` for executed and denied calls).
- `vidbyte/middleware/base.py` (all hooks), `vidbyte/middleware/pipeline.py:94-106` (`review_finish`: first refusal wins, no timeout), `vidbyte/lib/dataclasses/middleware.py:165-191` (`MiddlewareContext`), `vidbyte/lib/dataclasses/agents.py` (`FinishReview`, `AgentMessage`, `ProviderKeys`).
- The whole InfiniteMemoryAgent package on main: `agent.py`, `runtime.py`, `settings.py`, `memory.py` (tool shape), `__init__.py`, plus `vidbyte/lib/enums/infinite.py`, `vidbyte/lib/dataclasses/infinite.py` (headers), `vidbyte/lib/constants/infinite.py` (budget header), `vidbyte/tools/toolsets/infinite.py`, and the #1084 commit footprint (`git show --stat 2c84049c`) to mirror its file list.
- `vidbyte/agents/base.py:75-135, 1098-1112` (`BaseAgent.__init__` parameters, `_LINEAR_LOOP_RUNTIMES`, `arun`), `:1000-1004` (reply `sender = self.name`); `vidbyte/lib/registries/runtimes.py`; `vidbyte/lib/enums/agent_runtime.py`.
- `vidbyte/lib/dataclasses/validation.py` (every method; `require_number` refuses 0, `require_text` full-matches a pattern, `to_folder` refuses an existing file); `lint/rules/c008_shared_validator_owner.py` header and grammar (flags validator definitions by name, not inline checks).
- `vidbyte/lib/registries/provider_keys.py:113` (`primary` accepts a tuple) and its precedent `vidbyte/agents/aggregation.py:238`; `vidbyte/lib/registries/models.py` imports (lib-safe, already used by lib records).
- Tools: `vidbyte/tools/base.py:79-110` (`validate_call` checks only required presence, so `message` must re-check its arguments), `FileSystemToolConfig`, `WriteTextTool`, `ReadLinesTool`, `PatchTool`, `GrepTool`, `CodingAgentTools.get_tools`; grep confirmed no existing tool is named `message`.
- `vidbyte/agents/settings/loop.py` and `tool.py` (no default iteration, tool-call or time cap; `result_max_chars` default `None`).
- Test layer: `tests/features/infinite_memory_agent/infinite_memory_fixtures.py` (`ScriptedTree`, steps, `Gate`/`Signal`, `GUARD_SECONDS`), the pack README run lines, the `@pytest.mark.asyncio` style, `pyproject.toml` pins.

## Approaches weighed

1. **Turn-per-run** (each turn a fresh `agent.arun(text)`): smallest, no runtime type. Rejected: a working agent cannot receive messages until its turn ends (fails the "between tool calls" decision), and a new run sees earlier turns only as reply text in the system body (`BaseAgent.history` holds replies only), drops the goal from history, and grows the system prompt each turn.
2. **One long run + `_continue_finish_attempt` override** for idle/wake: rejected on evidence. At the plain-reply finish point the loop appends the assistant reply *after* the hook has appended its own message (`runtime.py:598-601`), so a delivered message would sit above the reply it answers. JevRuntime already relies on this path; this is worth a separate look (see Findings).
3. **One long run + `review_finish` middleware + `_after_tool_iteration` runtime hook** (chosen, D-1–D-3): `review_finish` fires at both finish points and appends `assistant(reply)` then `user(feedback)` on CONTINUE (`:563-568`, `:669-670`), which is exactly a new user turn; idle is an `await` inside that hook, so the agent keeps one append-only conversation. `_after_tool_iteration` is the only seam that may append to the live conversation mid-turn (middleware gets copies).
4. **Overriding the private `_finish_result`** in the runtime: rejected — private surface and it would leave a dangling `isDone` call.
5. **Actor runtime reuse**: rejected — one completion per message, no tools, auto-reply to sender, 10 ms polling quiescence, silent drop of unknown recipients.

Coordination design drawn from actor systems and distributed termination detection: per-recipient FIFO mailboxes; wake decided atomically at send (no lost wake-up); quiescence detected structurally — on one event loop a send is queued in the sender's own step, so "no agent working" implies "no message in transit", which makes the end check exact without polling (Dijkstra–Scholten-style reasoning collapses to a counter because there is no network). Events use an outbox: sequence assigned in the same synchronous block as the state change, delivery to the callback by an ordered flush under one lock, so callback order equals causal order regardless of which task flushes.

## Where I disagree with the request or scout (with evidence)

- **Request: "AgentSwarmRuntime" as the swarm-level object** (request.md §C open question frames `AgentSwarm` as a facade "over AgentSwarmRuntime"). In this SDK a `*Runtime` is an `AgentRuntime` subclass bound to an `AgentRuntimeType` (`RuntimeRegistry.resolve`), and the swarm needs exactly one such subclass for mid-turn delivery. I made `AgentSwarmRuntime` the member loop and `AgentSwarm` the coordinator (D-12, A-2). If the user meant the other split, it is a rename only.
- **Scout §4 item 5: "no seam between tool calls".** Agreed; I specified delivery between tool *iterations* and made it an explicit assumption (A-1) rather than touching the shared loop.
- **Scout §4 item 9 / request: on_event "pattern MultiAgent already uses".** MultiAgent's callback takes `(event, snapshot)`; the swarm's takes one `AgentSwarmEvent` (no snapshot exists). Containment of callback exceptions follows MultiAgent.
- **Request: "web search".** Kept opt-in via one `search_tool` setting (request.md §C already says so); no `web_fetch`.
- **A finding outside this feature (not fixed, not in scope):** `_continue_finish_attempt` at the plain-reply finish point produces `user(continuation)` then `assistant(reply)` ordering (`runtime.py:598-601`; JevDoneContinuation appends inside the hook, `vidbyte/agents/jev/continuation/done.py:86-92` per the scout). If unintended, JevAgent's done-continuations are mis-ordered today. Worth a separate issue.

## Decisions a reviewer may push on

- **FAILED stop reason (fourth reason).** The user named three end conditions; I added FAILED for "every agent failed" so an all-crashed run never reads as QUIET. Traced to "reliable ... valuable data" and the request's open failure-semantics question.
- **`allow_zero` option on `RecordFieldValidator.require_number`.** Needed because `elapsed_seconds` can legitimately be 0 and AGENTS.md principle 5 / C008 say to add an option to the canonical validator. Adds one modified file; an alternative is dropping `elapsed_seconds`.
- **No event cap.** "the full ordered tuple" was asked for; bounded only by the time limit (Q-8 offers a cap).
- **Fixed `PermissionPolicy.allow_all()` per member** (D-10): the default policy denies bash/write/patch.

## Least-sure assumptions

1. **A-5** — that `trim_with_provider_boundaries` keeps the goal (first user message) in a long run. Only InfiniteMemoryAgent's comment says so; I did not trace the trim code. If false, long-running agents lose the goal.
2. **A-8** — that the loop's provisional "finish attempt not accepted yet; continue with the next message" text before a wake's messages (isDone path) does not confuse models. Only live-model QA can tell.
3. **A-7** — that one search tool instance is safe across concurrent members.
4. **A-3** — the meaning and defaults of `max_turns` (swarm-wide activations, 500) and the one-hour default time limit.

## Self-check (Stage E)

- FR → INV/AC: all 18 FRs map (e.g. FR-5 → INV-6/AC-2; FR-18 → AC-17).
- AC → W/§12.3: all 21 ACs land on rows (listed in each row's Serves column).
- §12.3 → FR/NFR/W: every row names an FR and a W.
- Every EC names its guard (INV-/D-) or a stated limitation (EC-20, EC-24, EC-25, EC-32).
- Every T row names its control and where it sits; T-4 is N/A with a reason.
- Names in §4 = §8.5 = §12.3 (checked symbol by symbol).
- New files in §12.3 = 23 = §8.4 budget (11 Python, 1 README, 1 JSON, 10 leaves).
- §12.4 has at least one obligation per file kind (enum, constants, record, validator, settings, toolset, agent package, prompt, README, contract, registry, base file).
- Every §D weighted phrase appears as an INV, NFR or AC (backlog → NFR-3).
- §11 commands are copied from code-map.md / AGENTS.md; no test cases anywhere; every item traces to request.md or a cited rule.

## Open items

- No blocking questions. Q-1–Q-10 are optional, default no.
- Live-model QA after S3 (not a test): run the §4 snippet against a real provider to check A-5 and A-8.
