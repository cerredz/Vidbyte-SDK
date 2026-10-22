VERDICT: SOUND WITH FIXES — The coordination protocol is correct and the build is well grounded in repo precedent. But the failure-containment premise is false, the exact-tool and exact-prompt acceptance criteria cannot pass against the real agent loop, and the user-named `AgentSwarmRuntime` role went to the wrong class.

Reviewed: spec.md r1 (HEAD a43f5423, base 0f2aeb48), request.md, AGENTS.md, context/code-map.md, and the repo at HEAD. The review is read-only; this report is the only file written.

## WHAT THE SPEC GETS RIGHT

- **The D-3 turn-end design is correct, and it is the only correct option.** At the plain-reply finish, `review_finish` runs before the assistant reply is appended (`vidbyte/agents/runtime.py:559`, `:563-568`). `_continue_finish_attempt` appends the reply after the hook (`:598-601`), and the isDone path is handled at `:656-670`. Driving idle and wake through `FinishReview.continue_with(text)` therefore keeps the transcript ordered, and it needs no change to `runtime.py`. Do not move wake delivery into `_after_tool_iteration`.
- **The quiescence protocol (D-4, D-5, D-6) has no lost wakeup and no double delivery.**
  - Sends happen only from a working agent.
  - The wake is decided synchronously at send time.
  - `end_turn` checks the inbox and marks the agent idle in one synchronous block on one event loop.
  - The end check runs only when an agent goes idle or fails.
  - So "no agent working" is a stable state. The only hang left is a developer's `on_event` that never returns (`middleware/pipeline.py:94-106` has no hook timeout), and that is the developer's own bug.
- **The mid-turn seam (D-2) is right.** `_after_tool_iteration` runs only after a tool iteration that continues, after `after_iteration` (`runtime.py:690-700`). Middleware transforms apply per call and keep `prompt_index` (`runtime.py:1088-1110`). An appended user turn is therefore durable, and the compaction trim keeps the goal.
- **Registration and the count claims match the Infinite precedent exactly**, so rows 22, 31 and 32 are minimal and correct:
  - `AgentRuntimeType` (`lib/enums/agent_runtime.py:43-52`);
  - the registry mapping (`lib/registries/runtimes.py:31-48`);
  - `_LINEAR_LOOP_RUNTIMES` (`agents/base.py:83`);
  - `_runtime_extension_kwargs` (`base.py:1408-1465`);
  - the prompt header count "139 … across 35" → 149/36 (`lib/enums/prompts.py:7`).

  The L2 targets the briefing named also hold up:
  - **FAILED stop reason:** forced once containment exists. Without it, an all-failed run reads as QUIET.
  - **`AgentSwarmMemberAgent`:** forced, because `_runtime_extension_kwargs` lives on the agent.
  - **`AgentSwarmTurnMiddleware`:** forced, because `review_finish` is a middleware hook.

## FINDINGS (ranked, most severe first)

R-1 [Major] [L5] §8.1 D-7 (also INV-17, EC-12, EC-16, A-12) — The containment filter cannot tell a bug from a model failure, and the failure text it records is a generic wrapper
  Evidence:
    - The spec:
      - D-7: "A failure is contained per agent (`VidbyteSdkError`, `OSError`, `ValueError`, or a run that returns before release) … Anything else propagates."
      - EC-16: "An exception outside `VidbyteSdkError`, `OSError`, `ValueError` escapes an agent's run (a bug) | Not contained: … propagates from `arun` (wrapped by the task group)".
      - EC-12: "`AGENT_FAILED` with text "<ErrorType>: <message>"".
    - The repo:
      - `vidbyte/agents/base.py:965-979` (`generate_reply`) catches every `Exception`. It re-raises only `UsageAccountingError`, `FailureRaisedError` and `AllModelsFailedError`, all of which are `VidbyteSdkError` subclasses (`lib/errors/base.py:68`, `:168`, `:410`, `:506`).
      - Everything else becomes `raise AgentExecutionError(f"Agent '{self.name}' failed to generate a reply.", details={"agent": …, "error_type": type(exc).__name__}) from exc`, where `AgentExecutionError(VidbyteSdkError)` is at `:134`.
      - The sibling already handles this. `vidbyte/agents/infinite/launch.py:356-361` (`_error_text`) reads `error.__cause__` because "A runner's failure arrives wrapped".
  Failure: Every exception raised inside a member's model call, tool, middleware hook or `end_turn` reaches the swarm as a `VidbyteSdkError`.
    - A real bug, such as a `KeyError` in `end_turn` or a `TypeError` in a tool, is silently contained as `AGENT_FAILED`. EC-16 can never happen.
    - An S2 test for EC-16 that injects a bug through the model runner gets AGENT_FAILED or stop reason FAILED instead of an exception group. The implementer must then "fix" the code against the spec, or weaken the test, which §14 forbids.
    - EC-12's text becomes "AgentExecutionError: Agent 'tester' failed to generate a reply." The provider's message, the only useful part, is lost. A fresh implementer following EC-12 literally writes `f"{type(exc).__name__}: {exc}"` and produces exactly this.
  Smallest fix:
    - D-7 and INV-17: the contained set is `VidbyteSdkError` (which, through `BaseAgent`, covers every `Exception` raised inside a member's reply) plus "a run that returns before release". Drop `OSError` and `ValueError`; they can never arrive unwrapped.
    - EC-12: the text is the root cause, `"<type of __cause__ or the error>: <cause text or error text>"`, rendered the way `launch.py:_error_text` does, as a private helper in `swarm.py`.
    - EC-16 and A-12: only non-`Exception` `BaseException`s (cancellation, `KeyboardInterrupt`) and exceptions raised by `arun`'s own code outside a member run propagate.
    - Add one README "Notes for agents" line: a member's bug surfaces as `AGENT_FAILED` naming the cause type, so QUIET or FAILED can hide one.
    - Optional, `[scope-adding]` Q-11: move `_error_text` into `vidbyte/lib/errors/` as a canonical helper. Default: no.

R-2 [Major] [L9/L10] §6.2 AC-13, AC-14 (also INV-21, G-1, FR-3, §12.3 row 8) — The "exactly these tools" and "own prompt followed by the swarm prompt" criteria are false for every `BaseAgent`, so the literal tests cannot pass without touching forbidden files
  Evidence:
    - The spec:
      - AC-13: "its tool names are exactly `bash`, `grep`, `read_lines`, `write_text`, `patch_file`, `message` (plus the search tool's name when given)".
      - INV-21: "Every agent holds exactly the tools …".
      - AC-14: "its system prompt is its own system prompt followed by the swarm prompt".
    - The repo:
      - `vidbyte/agents/runtime.py:193-194` sets `self.tools = with_internal_agent_tools(tools)`, so `IsDoneTool` is always present. `tools/_internal.py` gives it the description "Call this when you are done with the problem; this is how you stop the loop."
      - `runtime.py:254` sets `system_prompt=append_agentic_loop_prompt(system_prompt)`, which appends the `agentic_loop` context prompt *after* the caller's system prompt. That prompt says "When you are finished, call the isDone tool with the final answer."
      - The sibling's tests pin isDone inside exact sets: `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:118` and `test_infinite_memory_delegation.py:64-65` and `:209-212`. Their header says "Do not loosen the exact tool-name sets to subset checks".
  Failure:
    - S2 writes `assert {t.name for t in call.tools} == {"bash", …, "message"}`, and the test fails, because isDone is there. `assert call.system == own + swarm` fails too, because the loop prompt follows.
    - The only code fix is editing `runtime.py`, which §14 lists as "Ask first". The only test fix is loosening, which §14 forbids under "Never". With no human gate after S1, the run stops BLOCKED.
    - The model-facing text also disagrees. Row 8 tells the model "replying without a tool call ends your turn", while the loop prompt and the isDone description say isDone stops "the loop". The model is never told that isDone ends only its turn, although EC-5 handles that case in code. prompt-families.md requires the prompt to match the code.
  Smallest fix:
    - Add `isDone` to the exact sets in AC-13, INV-21, G-1 and FR-3.
    - Restate AC-14 as: the system prompt is the agent's own prompt, then the swarm prompt, then the loop's standard agentic-loop prompt.
    - Add one sentence to row 8: "Calling isDone also ends only your turn; you may be woken again."
    - §13 should say that `ModelCall.tools` includes isDone.

R-3 [Major] [L1/L4] §8.1 D-12 (also A-2, FR-18, rows 27–28) — The user-named "AgentSwarmRuntime" role became a one-hook member subclass, while an unnamed sixth class holds the swarm's runtime
  Evidence:
    - The user (Prompt 3): "decompose the AgentSwarm into different classes that have different roles (AgentSwarmTools, AgentSwarmSettings, AgentSwarmRuntime, …)".
    - request.md §Open questions, line 162: "Whether there is a thin `AgentSwarm` facade with `arun(goal)` over `AgentSwarmRuntime`".
    - The spec, D-12: "`AgentSwarm` is the public entry point and coordinator; `AgentSwarmRuntime` is each member's loop … In this SDK a `*Runtime` is an `AgentRuntime` subclass bound to an `AgentRuntimeType`".
    - Row 27 makes `AgentSwarmRuntime` a single `_after_tool_iteration` override.
    - Row 28 gives `AgentSwarm` the `arun` entry point, `post_message`, `collect_messages`, `end_turn`, `record_tool_call`, the in-progress guard and the run-state reset.
    - The repo contradicts D-12's rationale: `vidbyte/agents/runtimes/actor/broker.py:44` defines `class BaseActorRuntime(ABC)`, "broker orchestrating actor lifecycles, execution, and loops". It is not an `AgentRuntime` subclass, yet it is registered as `ACTOR_MODEL*` in `lib/registries/runtimes.py:44-46`. A multi-agent coordinator named `*Runtime` is already precedent.
    - AGENTS.md principle 3: "If describing the job of a function or a class needs the word 'and', it is probably two functions or two classes". D-12's own description is "entry point and coordinator".
  Failure: The user asked for the AgentSwarm to be decomposed into the five roles. The spec instead keeps a thick `AgentSwarm` that does the runtime's job, and spends the name `AgentSwarmRuntime` on a 15-line hook the user never asked about. A-2 already names this risk. With no approval gate, it ships unconfirmed, and the user will see it at PR review as "the runtime is in the wrong class". The thick `AgentSwarm` also needs per-run state that must be reset in `finally`, plus an in-progress guard (FR-16, INV-19, EC-19, EC-30), only because coordination state lives on a long-lived object.
  Smallest fix: Apply A-2's own "if wrong" branch now; behavior does not change.
    - `AgentSwarmRuntime` (row 27's file) is the per-run coordinator that row 28 currently describes. `AgentSwarm.arun` builds a fresh one per call and awaits it.
    - `AgentSwarm` (row 28's file) becomes the thin entry point: hold settings, validate the goal, prepare the workplace, run one `AgentSwarmRuntime`.
    - The member loop subclass becomes `AgentSwarmMemberRuntime(AgentRuntime)` in `member.py`, registered as `AGENT_SWARM`. It must be exported from `vidbyte.agents.agent_swarm`, because row 31's registry import is package-only.
    - Per-run state then dies with its runtime object, so INV-19's "run state is reset" clauses and EC-19's reset go away. Keep the in-progress refusal (FR-16) only if the author still wants it.
    - File count stays at 23. Update D-12, A-2, FR-18, §8.5 and rows 26–29 and 31.

R-4 [Minor] [L2] §8.1 D-14 (also row 4, INV-27, §11 checklist) — The `allow_zero` change to the shared validator exists only to accept a float clock reading
  Evidence: D-14: "`AgentSwarmEvent.elapsed_seconds` is checked by `RecordFieldValidator.require_number` with a new `allow_zero` option". Row 4 modifies `vidbyte/lib/dataclasses/validation.py`. The same spec already checks `message_id` with `require_int(minimum=0)` (§9.1, line 578), and `require_int` takes a minimum today.
  Failure: A "very minimal" first version changes a canonical lib validator used by every record. That adds a row, an invariant (INV-27), a decision, a checklist line and a test file (`tests/test_record_field_validation.py`), all for one timestamp field. Events are already ordered by `sequence`.
  Smallest fix: Make the field `elapsed_ms: int`, checked by `require_int(minimum=0)`. Drop row 4, INV-27, D-14 and the §11 `allow_zero` checklist line. File count is unchanged; the MODIFY count drops by one.

R-5 [Minor] [L4] §12.3 row 19 — The toolset catalog takes the caller's search tool, contrary to the prebuilt-agent rule
  Evidence:
    - Row 19: `get_tools(root, search_tool)` returns `(BashTool(root), …, PatchTool(root)[, search_tool])`.
    - The field guide's `prebuilt-agents.md:5`: "The catalog holds only the agent's own tools. The agent appends caller tools as a tuple".
    - Precedent: `vidbyte/tools/toolsets/infinite.py` has no caller tools, and `vidbyte/agents/infinite/agent.py:77` appends them.
  Failure: The catalog's static signature takes a caller-owned tool, so `AgentSwarmTools` stops being a fixed catalog. The review bot cites this field-guide rule.
  Smallest fix: `AgentSwarmTools.get_tools(root)` returns the five file and shell tools. `AgentSwarm` builds each member's tuple as `AgentSwarmTools.get_tools(root) + (message_tool,) + ((search_tool,) if search_tool else ())`. AC-13 is unchanged.

R-6 [Minor] [L10] §13 — The deterministic seam for "builder sends only after tester is idle" (AC-3, AC-5, EC-7) is not named
  Evidence: §13 lists the ScriptedTree steps `after(Gate | Signal, then)`, but every gate in the fixture is set from a model call. Becoming idle happens inside the swarm (`end_turn`), not on a model call. AC-3 requires "`AGENT_IDLE(tester)` < `MESSAGE_SENT`".
  Failure: A test author guesses: they add a sleep, which is flaky, or they gate on "tester answered n", which fires before `end_turn` marks it idle. The resulting test is racy and passes or fails by scheduling.
  Smallest fix: Add one §13 bullet. "To wait for a state change in the swarm, pass an `on_event` callback that sets a `Signal` on the event (for example `AGENT_IDLE` for `tester`), and gate the sender's next step with `after(signal, tool_call("message", …))`. For AC-2, gate `tester`'s tool-call step on a `Signal` set after `builder`'s `message` call."

R-7 [Minor] [L9/L11] §8.4, §11, §12.6, NG-10 — Four statements are inaccurate and would mislead the builder
  Evidence and fix:
  - **§12.6 order.** It reads "23, 24, 25 → 26, 27 → 28 → 29 → 22 + 31 + 32", but row 26's member agent uses `AgentRuntimeType.AGENT_SWARM`, which row 22 creates. Fix: move row 22 into P1, or before 26.
  - **§8.4's S025 reason.** It says "S025 needs the three description leaves", but `lint/rules/s025_model_facing_description_depth.py` states "Descriptions built by a method call or a non-literal attribute are exempted, not flagged". Catalog-loaded descriptions are never checked by S025. Fix: cite `prompt-families.md` and `model-facing-tool-contracts.md` as the reason, and require the S2 contract test to assert that each description leaf has 4–5 sentences, since no lint enforces it.
  - **§11 citation.** It says `validate_provider_model_pair` is "already used by lib records (`vidbyte/lib/dataclasses/agent_descriptor.py`, `model_configs.py`)". The only lib caller is `vidbyte/lib/dataclasses/config.py:514`. Fix: correct the citation.
  - **"workflow" wording.** NG-10 rules out "any workflow advice in the swarm prompt", while row 8 asks for a "workflow" section. Fix: rename the section "how the swarm works", to match its actual content: messaging, idling, waking.

## VERIFIED CLAIMS

Held:
1. **D-3: the plain-reply finish order.** `runtime.py:559`, `:563-568` and `:598-601`; isDone at `:656-670`.
2. **D-2: `_after_tool_iteration` runs only after a continuing tool iteration, after `after_iteration`.** `runtime.py:690-700`, and transforms are per call (`:1088-1110`).
3. **The specialized-runtime wiring.**
   - `_LINEAR_LOOP_RUNTIMES` is at `base.py:83`.
   - `_runtime()` and `_runtime_extension_kwargs` are at `base.py:1408-1465`.
   - The registry is at `lib/registries/runtimes.py:31-48`.
   - The enum is at `lib/enums/agent_runtime.py:43-52`.
4. **`lib/enums/prompts.py:7` says "139 … across 35".** The count 149/36 after ten new leaves and one new family is right.
5. **C011 counts inherited `run`/`arun`.** Its `_ENTRY_SUFFIXES` are ("Agent", "Runner", "Harness", "Session", "Machine"). So `AgentSwarmMemberAgent` is covered by `BaseAgent`'s twins, and neither `AgentSwarm` nor `AgentSwarmRuntime` needs a sync twin.
6. **`RecordFieldValidator.require_number` refuses values <= 0** (`validation.py:93-98`). `to_folder` resolves but never creates (`:204-218`), so `AgentSwarmWorkplace.prepare()` must create the folder, as row 24 says.
7. **`ToolParameter` has no `enum` field.** `ToolSpec.input_schema` exists, with `additionalProperties: False` precedent at `agents/infinite/memory.py:139`. Row 26's `to` enum must go through `input_schema`.
8. **`review_finish` has no timeout, and its exceptions propagate** (`middleware/pipeline.py:94-106`). `FinishReview` refuses a blank CONTINUE (`lib/dataclasses/agents.py:83-123`), so `end_turn` must never return blank text, which holds because the inbox render is non-empty.
9. **D-7's set matches Infinite's** (`infinite/launch.py:244`). But BaseAgent's wrapping (`base.py:965-979`) makes the set non-discriminating; see R-1.
10. **The ScriptedTree fixture matches §13.** It patches `BaseAgent._runner_for_model` and routes by agent name, with the steps `tool_call`, `reply`, `fail`, `observe` and `after`, `GUARD_SECONDS = 20.0` and `MODEL = "gpt-4.1"` (`infinite_memory_fixtures.py:200-400`).
11. **The `harness_threads` surface-test failures are pre-existing** (`field-guide local-ci-verification.md:45-50`).
12. **`PermissionPolicy.allow_all()` exists** (`tools/security.py:58-61`). On cancel, `BashTool` kills only the launcher on Windows, which makes row 30's README note accurate.

Did not hold:

13. **D-12: "a `*Runtime` is an `AgentRuntime` subclass".** False: `BaseActorRuntime(ABC)` (`runtimes/actor/broker.py:44`) is a registered multi-agent coordinator (R-3).
14. **AC-13, INV-21 and AC-14: exact tools and exact prompt.** False: isDone is always added (`runtime.py:193-194`), and the agentic-loop prompt is appended last (`runtime.py:254`) (R-2).
15. **§8.4: "S025 needs the three description leaves".** False: S025 exempts descriptions loaded from the catalog (R-7).
16. **§11: `validate_provider_model_pair` is used by `agent_descriptor.py` and `model_configs.py`.** False: the only lib caller is `config.py:514` (R-7).
17. **§12.6: the dependency order inside P3.** Row 22 is ordered after row 26, which depends on it (R-7).

Optional questions raised by this review (scope-adding, default no):
- Q-11: Move `_error_text`-style cause rendering into `vidbyte/lib/errors/` as a canonical helper shared with InfiniteMemoryAgent? Default: no; use a private helper in `swarm.py`.
