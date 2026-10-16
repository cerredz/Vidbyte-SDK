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

---

## r2 addendum — S1 review round 1 (2026-10-16)

The reviewer returned SOUND WITH FIXES (0 Blocker, 3 Major, 4 Minor, optional Q-11). I verified each finding against the code before editing and accepted all seven. §16 has one row per finding; §17 has the r2 row. `status` stays `draft`.

**Dispositions**

- **R-1 (Major), accepted.** `BaseAgent.generate_reply` catches every `Exception` and either re-raises an SDK error or wraps it in `AgentExecutionError("Agent '<name>' failed to generate a reply.") from exc` (`vidbyte/agents/base.py:965-979`; `BaseException` takes the branch at :980). So r1's set `(VidbyteSdkError, OSError, ValueError)` was really just `VidbyteSdkError`, and it also catches bugs. r2 states this honestly: contained = `VidbyteSdkError` or an early return (INV-17, D-7, FR-11, A-4). `AGENT_FAILED` names the root cause from `__cause__`, the way `vidbyte/agents/infinite/launch.py:356-361` `_error_text` does, plus the cause's type name (AC-7, EC-12, §9.1). New EC-38 covers what still propagates: a `BaseException`, or the runtime's own code. The README notes that a bug shows up as `AGENT_FAILED` (EC-16, row 30). Q-11 is recorded, default no.
- **R-2 (Major), accepted.** Confirmed in code:
  - `include_internal_tools=True` by default (`runtime.py:189`), so isDone is always added (`:194`).
  - `BaseAgent` passes `agentic_loop=True` (`base.py:947`), so the agentic-loop prompt is appended (`runtime.py:254`).
  
  G-1, FR-3, INV-21, AC-13 and AC-14 now include `isDone` and the prompt order: own prompt, then the swarm prompt, then the agentic-loop prompt. AC-14 also states that `isDone` ends only the turn, and row 8 tells the model so. §13 states both facts. `runtime.py` is untouched.
- **R-3 (Major), accepted with the orchestrator's mapping.**
  - `AgentSwarmRuntime` is one swarm run: mailboxes, turns, ending, and the member task group. It is built fresh per `arun` and runs once.
  - `AgentSwarm` is a thin entry point.
  - The member loop is `AgentSwarmMemberRuntime(AgentRuntime)`, registered as `AgentRuntimeType.AGENT_SWARM_MEMBER = "agent_swarm_member"`. It is exported from the package because the registry imports it through the package (blocking-lint-invariants.md:24-29, A006).
  - Precedent for a coordinator named `*Runtime`: `BaseActorRuntime` (`vidbyte/agents/runtimes/actor/broker.py:44`).
  - The run-state reset clauses are gone. FR-16's in-progress refusal stays, because it keeps two runs' event sequences out of one `on_event`.
  - New files stay at 23. Behavior classes go from 9 to 10, and W-11 is added.
- **R-4 (Minor), accepted.** `elapsed_ms: int` is checked by `require_int(minimum=0)` and converted with the existing `AGENT_SPEED_MILLISECONDS_PER_SECOND` (`vidbyte/lib/constants/speed.py:18`). Row 4, D-14 and INV-27 are withdrawn (struck through); D-16 replaces them. Modified files go from 14 to 13. §14 now asks first before any change to `validation.py`.
- **R-5 (Minor), accepted.** `AgentSwarmTools.get_tools(root)` returns the five file and shell tools only (prebuilt-agents.md:5). `AgentSwarmRuntime` builds each member's tools as `(*AgentSwarmTools(root).all(), message tool[, settings.search_tool])`, following `vidbyte/agents/infinite/agent.py:77`. Web search stays opt-in.
- **R-6 (Minor), accepted.** Added the §13 bullet: set a `Signal` from `on_event`, gate the sender with `after(signal, tool_call("message", …))`, and use the named gate for AC-2.
- **R-7 (Minor), accepted.**
  - P3 order: row 22 comes first.
  - S025: catalog text is exempt, so the 4–5 sentence rule is cited from model-facing-tool-contracts.md / prompt-families.md and left to the S2 contract tests.
  - The `validate_provider_model_pair` citation is now `vidbyte/lib/dataclasses/config.py:514` (its only lib caller).
  - Row 8's section is now "how the swarm works".

**Self-check after r2** (scripted over the spec text):
- All 18 FRs and 21 ACs land on a W row and a §12.3 row.
- W-1 through W-11 each have rows.
- §12.3 has CREATE 23 and MODIFY 13, matching §8.4.
- Every `AgentSwarm*` name used in §4 appears in §8.5 and §12.3.
- No stale `AGENT_SWARM` (bare), `allow_zero`, `elapsed_seconds` or `swarm=` references remain outside the withdrawn rows and the review log.

**What the round-2 reviewer should look at first**
- §8.5 (new `AgentSwarmRuntime` / `AgentSwarmMemberRuntime` split and the thin `AgentSwarm.arun`).
- §9.2: `AgentSwarmRuntime` is public but `AgentSwarm` is the supported entry, and `arun` runs once.
- Rows 26–29 and 31–33, and the §12.6 order. All of P3 effectively lands in one commit, because the package `__init__` imports `swarm.py` and `runtime.py`.

**Least-sure assumptions (r2)**
1. A-2: the R-3 mapping now follows the user's words. If the user meant the member loop, the fix is a rename only.
2. A-5 and A-8 are unchanged. Only live-model QA can settle them.
3. The member runtime's enum value `agent_swarm_member` is my choice. It names what it resolves to and cannot collide with the five role names.
