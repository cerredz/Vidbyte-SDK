VERDICT: SOUND WITH FIXES — The R-3 split kept the termination protocol intact and the wiring matches precedent. But three statements the blind tests will rely on are false against the real loop: the member-runtime refusal reaches `arun` callers as `AgentExecutionError`, tool exceptions never become `AGENT_FAILED`, and the member runtime's type check needs an import cycle that A006 rejects.

Reviewed: spec.md r2 (HEAD b4e8ca05, base 0f2aeb48), request.md, AGENTS.md, context/code-map.md, reports/S1-spec-review.md, house-style.md, and the repo at HEAD. The review is read-only. This report is the only file written, and the two Python probes below ran from stdin with no bytecode written. `docs/spec/agent-swarm/pipeline.md` shows as modified in the worktree; that change is the orchestrator's, not this stage's.

## WHAT THE SPEC GETS RIGHT

- **The R-3 move did not reintroduce a lost wakeup or a hang.**
  - All coordination state now lives on one fresh `AgentSwarmRuntime` per run. Every member part reaches it through its constructor, so no state crosses runs.
  - Sends, drains, idle marks and the end check are still synchronous decisions taken before any `await`. A woken agent counts as working until it resumes. `end_turn` creates its wait future before it flushes, so a wake that lands during the flush resolves an already-created future.
  - The TIMEOUT mechanism works on the local interpreter (3.11.0). A probe of `asyncio.timeout(0.2)` around a `TaskGroup` with two children parked on futures and one sleeping returned in 0.22 s. All three children unwound, and the probe raised `TimeoutError`. Keep D-4, D-5, D-8 and the FR-16 refusal on `AgentSwarm` as they are.
- **The registry and enum wiring is minimal and lint-clean.**
  - Row 31's lazy `from vidbyte.agents.agent_swarm import AgentSwarmMemberRuntime` passes A006, because `__init__.py` targets are not graph nodes (`a006_directed_dependency_graph.py:62-64`). This is the same shape as `runtimes.py:32` for Infinite.
  - `agent_swarm_member` appears automatically in the fork tool's enum (`tools/builtins/fork/fork.py:471`) and in the YAML choices (`lib/dataclasses/config.py:663-668`).
  - No existing test iterates or pins the runtime list (a grep of `tests/` found none), so P3's new member breaks nothing.
- **The root-cause rule for model failures (D-7, EC-12, AC-7) is correct.** The loop re-raises a runner's exception bare (`agents/runtime.py:819`), and `BaseAgent` wraps it with `from exc` (`agents/base.py:975-978`). So `__cause__` is the provider error and AC-7 can pass.
- **`member.py` holding four small classes is acceptable; do not split it.**
  - The sibling already does this: `infinite/memory.py` holds five classes in 263 lines, and `launch.py` holds two in 380.
  - The four classes serve one subsystem, a member's connection to the swarm, and each is forced by an SDK base class. The file stays well under NFR-3's 400-line cap.
  - No rule forces a split: S015's completeness check binds only the root (`s015_public_export_integrity.py:44-45`). "Very minimal" argues for one file.

## FINDINGS (ranked, most severe first)

R-8 [Major] [L10] §6.2 AC-12 (also INV-24, EC-35) — A plain `BaseAgent(runtime="agent_swarm_member")` that runs raises `AgentExecutionError`, not `ConfigurationError`
  Evidence:
    - The spec:
      - AC-12: "a plain `BaseAgent(runtime="agent_swarm_member")` | it runs | it raises `ConfigurationError` whose message names `AgentSwarm`".
      - INV-24: "refuses to run with a `ConfigurationError` that names `AgentSwarm`".
      - EC-35, user sees: "`ConfigurationError`".
    - The repo:
      - `_runtime()` is first called from `_build_context` (`agents/base.py:1280`). `_generate_reply` calls `_build_context` at `:942`, inside the `try` opened at `:918`.
      - The `except Exception` at `:965-978` re-raises only `UsageAccountingError`, `FailureRaisedError` and `AllModelsFailedError`. It wraps everything else as `AgentExecutionError(f"Agent '{self.name}' failed to generate a reply.") from exc`.
      - `AgentExecutionError` and `ConfigurationError` are sibling `VidbyteSdkError` subclasses (`lib/errors/base.py:134`, `:289`).
    - Probe on this worktree, using the existing `infinite_memory` runtime (the same refusal shape) with an offline runner:
      - `arun` raised `AgentExecutionError | Agent 'plain' failed to generate a reply.`;
      - `isinstance(e, ConfigurationError)` was `False`;
      - `__cause__` was `ConfigurationError | The 'infinite_memory' runtime is only available through InfiniteMemory…`;
      - `_runtime()` called directly raised `ConfigurationError`.
    - The sibling's test and the field guide both check `_runtime()`, not `arun`: `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:214-219`, and `runtime-boundaries.md:34`, "Check: `BaseAgent(runtime="x")._runtime()` raises a message naming the real agent".
  Failure: S2 writes AC-12 literally, as `with pytest.raises(ConfigurationError, match="AgentSwarm"): await BaseAgent(..., runtime="agent_swarm_member").arun(...)`, and the test fails with `AgentExecutionError`. The only code fix is in `agents/base.py`, which §14 puts under "Ask first". The only test fix is loosening the test, which §14 lists under "Never". With no human gate, the run stops BLOCKED.
  Smallest fix:
    - Restate AC-12: "When `_runtime()` is called on a plain `BaseAgent(runtime="agent_swarm_member")`, and on `fork()` of a member, each raises `ConfigurationError` whose message starts "The 'agent_swarm_member' runtime is only available through AgentSwarm". When the plain agent's `arun` is awaited, it raises `AgentExecutionError` whose `__cause__` is that `ConfigurationError`."
    - Use the same wording in INV-24 and in EC-35's "User sees", and add one §13 bullet stating the wrapping.
    - §9.2's sentence ("building `AgentSwarmMemberRuntime` outside a swarm raises `ConfigurationError`") is already accurate.

R-9 [Major] [L5/L10] §6.3 EC-16 (also §8.1 D-7, INV-17, A-4, §12.3 row 30) — A tool's exception never becomes `AGENT_FAILED`, and an `after_tool_call` exception does not name its cause
  Evidence:
    - The spec:
      - INV-17 and D-7: catching `VidbyteSdkError` "covers every model, tool, middleware and turn-end exception".
      - EC-16: "A bug raises inside a member's reply — a `TypeError` in a tool, a `KeyError` in the swarm's own `end_turn` … | `AGENT_FAILED` naming the bug's type".
      - Row 30's README note: "a bug inside a member's reply, even in the swarm's own turn code, surfaces as `AGENT_FAILED` naming its cause".
    - The repo:
      - **Tools.** `_execute_tool` turns any `Exception` into `ToolExecutionError` (`agents/runtime.py:1480-1483`). `_run_tool_call` then turns `ToolExecutionError` (`:1331-1340`) and every other `Exception` (`:1341-1348`) into `ToolResult.error(call.tool_name, f"Tool execution failed: {exc}", …)`, and the loop continues. Nothing reaches `BaseAgent`'s wrapper.
      - **`after_tool_call`.** `MiddlewarePipeline._run` catches `Exception` (`middleware/pipeline.py:144-146`). `_exception_decision` returns `abort("middleware_error", metadata={"error_type", "error"})` because `AgentMiddleware.fail_closed` defaults to `True` (`middleware/base.py:28`; `pipeline.py:214-215`). The member's run then returns early with a middleware-abort stop reason (the EC-15 path), and there is no `__cause__`.
      - Only three paths reach the wrapper with the bug as `__cause__`:
        - `review_finish`, whose exceptions propagate (`pipeline.py:94-106`);
        - `_after_tool_iteration`, which is called outside any `try` (`runtime.py:700`);
        - the model call.
  Failure:
    - A `search_tool` whose `execute` raises `TypeError` is the one tool a developer or a test controls. The model reads "Tool execution failed: …" and continues, and the swarm ends QUIET with `TOOL_CALLED(status=error)` and no `AGENT_FAILED`. An S2 test for EC-16 written that way fails, and it can pass only by editing `runtime.py` (forbidden).
    - A bug inside `post_message`, the swarm's own code reached through the `message` tool, is likewise a tool error that the model may retry, not `AGENT_FAILED`. The README note tells every later reader the opposite.
    - A bug in `record_tool_call` yields `AGENT_FAILED` whose text names the middleware abort, not `KeyError`.
  Smallest fix: State the contained set by where the exception is raised. The design does not change.
    - INV-17 and D-7:
      - An exception from the model call, from `review_finish` (`end_turn`), or from `_after_tool_iteration` (`collect_messages`) reaches the swarm as a `VidbyteSdkError` with the bug as `__cause__`, and the swarm records `AGENT_FAILED` naming the cause.
      - An exception from a tool, including `message` and `post_message`, becomes a tool error the model reads (`TOOL_CALLED` with status error), and the agent continues.
      - An exception from `after_tool_call` (`record_tool_call`) aborts that member through the fail-closed middleware, and the swarm records `AGENT_FAILED` naming the middleware abort (EC-15).
    - EC-16: replace the tool example with these three cases.
    - Row 26: `AgentSwarmTurnMiddleware` keeps the default `fail_closed = True`, so a recording bug never silently drops a `TOOL_CALLED` event.
    - Row 30: the README note says that a bug in the swarm's turn code surfaces as `AGENT_FAILED`, and a bug in a tool (including `message`) surfaces as a tool error in `TOOL_CALLED`.

R-10 [Major] [L4] §12.3 row 26 (also §8.5 `AgentSwarmMemberRuntime.__init__`) — "Refuses anything but an `AgentSwarmRuntime`" cannot be written while `member.py` imports `AgentSwarmRuntime` only under `TYPE_CHECKING`, except through an import cycle that A006 rejects
  Evidence:
    - Row 26: "`__init__(*, swarm_runtime=None, **kwargs)` refuses anything but an `AgentSwarmRuntime` (… details naming the received type) … `AgentSwarmRuntime` imported only under `TYPE_CHECKING`".
    - Row 27: `runtime.py` builds the member agent, the tool and the middleware, so it imports `member.py` at module level.
    - The precedent refuses with `isinstance` on classes it imports at runtime (`agents/infinite/runtime.py:53`).
    - A006 (`lint/rules/a006_directed_dependency_graph.py`):
      - `ImportCollector` records every import, including those inside function bodies, and skips only `TYPE_CHECKING` blocks (`:133-139`).
      - Every edge of an import cycle is reported as "concrete import cycle".
      - Its diagnostic lists "Adding a local import inside a function to hide the cycle" under will-not-work.
      - The rule is blocking, with baseline 34 (`lint/baseline.json:6`).
      - Imports of an `__init__.py` are not graph edges. A function-local `from vidbyte.agents.agent_swarm import AgentSwarmRuntime` would therefore pass lint, but it is the same runtime ↔ member cycle that AGENTS.md principle 3 forbids ("no two modules depend on each other in a cycle").
  Failure: The implementer must check `isinstance` against a class it may not import.
    - A function-local `from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime` makes A006 report member ↔ runtime, so the count goes above 34 and the lint stage of the gate fails.
    - Importing through the package instead hides the cycle from lint and draws a review comment.
    - A top-level import fails at import time with a partially initialized module.
  Smallest fix: Row 26 and §9.2 say the member runtime refuses when `swarm_runtime is None`, with `details={"received_swarm_runtime": type(swarm_runtime).__name__}`.
    - This is the only way it is built outside a swarm: `BaseAgent._runtime_extension_kwargs()` returns `{}` for a plain agent (`agents/base.py:1463-1465`), and a fork is a plain `BaseAgent` (`agents/fork.py:56-58`).
    - INV-24 and AC-12 hold unchanged, and `AgentSwarmRuntime` stays a `TYPE_CHECKING` import.

R-11 [Minor] [L9] §6.3 EC-38, §15 A-12 — Python 3.11's `TaskGroup` does not wrap `KeyboardInterrupt` or `SystemExit` in an exception group
  Evidence:
    - The spec:
      - EC-38: the exception "propagates from `arun` (a member's is wrapped in the task group's exception group)".
      - A-12: "wrapped in the task group's `BaseExceptionGroup`. — If wrong: unwrap the single exception before re-raising."
    - The local `asyncio/taskgroups.py` (3.11.0): `_is_base_error` is `isinstance(exc, (SystemExit, KeyboardInterrupt))` (`:145-147`), and such an error is stored and re-raised bare (`:104-105`).
    - A probe on 3.11.0: a `KeyboardInterrupt` raised in one `TaskGroup` child under `asyncio.timeout` surfaced from `asyncio.run` as a bare `KeyboardInterrupt`, and `arun`'s `finally` ran.
    - Only an `Exception` raised by the runtime's own code inside a member task arrives as an `ExceptionGroup`.
  Failure: Following A-12's "if wrong" branch produces unwrap code that never runs. A test author asserting `BaseExceptionGroup` would assert on behaviour that does not happen. EC-38 is the outcome this round was asked to pin down, and as written it is inaccurate.
  Smallest fix:
    - Rewrite EC-38 to say:
      - a `KeyboardInterrupt` or `SystemExit` from a member propagates bare;
      - an `Exception` from the runtime's own code inside a member task arrives as an `ExceptionGroup`;
      - either way, the other members are cancelled, no `SWARM_ENDED` is recorded, `on_event` receives no further event, and `AgentSwarm`'s in-progress flag is cleared.
    - Drop A-12's "unwrap" branch.

R-12 [Minor] [L5] §9.2 (also §8.5 `AgentSwarmRuntime.arun`, INV-18) — The public `AgentSwarmRuntime.arun` does not check the goal
  Evidence:
    - §9.2 makes `AgentSwarmRuntime(settings, root)` and `arun(goal)` public, "as one of the five named roles".
    - Its pseudocode in §8.5 starts with "refuse if this runtime already ran" and goes straight to building members. Only `AgentSwarm.arun` checks the goal.
    - INV-18: "A refused setting, member, or goal raises `ConfigurationError` … before any … agent is built, or any model is called."
  Failure: `await AgentSwarmRuntime(settings, root).arun("  ")` builds every member and hands each one a blank first message. INV-18's `ConfigurationError` becomes whatever each member's run does with a blank prompt: either N `AGENT_FAILED` events and stop reason FAILED, or N model calls on blank input.
  Smallest fix: `AgentSwarmRuntime.arun` runs the same `RecordFieldValidator.require_text(goal, "goal")` check first; this adds one line to row 27. `AgentSwarm.arun` keeps its own check, so a bad goal still creates no folder.

R-13 [Minor] [L4] §12.3 row 27 (also the §12.4 narration item) — `arun → _run_member → end check / root-cause helper` is the two-level chain that AGENTS.md principle 1 rules out, unless `_run_member` is declared a main function
  Evidence:
    - §8.5: "`_run_member(agent, goal)`: … On `VidbyteSdkError`: mark the agent failed, record `AGENT_FAILED` with the root cause …, run the end check, flush".
    - Row 27 lists the root-cause text and the end check as "private flat helpers", and `arun` starts one `_run_member` per member.
    - AGENTS.md:23: "a function may call another of its own functions, but that second function should not call a third".
    - §12.4's list of narrated main functions omits `_run_member`.
  Failure: The `@claude` review cites principle 1. Or the implementer dodges it by inlining the end check in both `end_turn` and `_run_member`, which splits the one quiescence rule that D-4 needs in one place.
  Smallest fix: §12.4 names `_run_member` as the main function of each member task, narrated like the others, so its root-cause helper and the end check sit one level below it. No code shape changes.

## VERIFIED CLAIMS

Claims checked in this round:

1. **Row 31 and the import graph: held, subject to R-10.**
   - The registry imports runtimes through the package `__init__` (`lib/registries/runtimes.py:32`). A006 does not count `__init__.py` targets (`a006…py:62-64`).
   - `runtime.py → member.py` at module level, with `member.py → runtime.py` only under `TYPE_CHECKING`, forms no cycle (`a006…py:133-139`). The one exception is the type check that R-10 removes.
2. **§9.4: the fork-tool enum and the YAML choices list every `AgentRuntimeType`: held.** Sources: `fork.py:471` and `config.py:663-668`. No test iterates or pins the list.
3. **INV-24 "refuses": held at `_runtime()`, false through `arun` (R-8).**
   - A fork of a member is a plain `BaseAgent` (`fork.py:56-58`), so it is refused too.
   - Neither `AgentRuntimeConfig.timeout_seconds` (`lib/dataclasses/agents.py:133`) nor `AgentLoopSettings` (`agents/settings/loop.py:52-58`) has a default run-wide cap. `BaseAgent`'s `timeout_seconds` applies to each model call (`base.py:1661-1662`). A long idle wait inside `review_finish` therefore never trips a timeout.
4. **D-10: `PermissionPolicy.allow_all()` is at `vidbyte/lib/dataclasses/security.py:59`: held.** The spec's §11 citation is right; round 1's `tools/security.py` citation was itself wrong.
5. **D-7, EC-12 and AC-7, the root cause for model errors: held.** The loop re-raises the runner's exception bare (`runtime.py:819`), and `base.py:975-978` wraps it `from exc`. Tools and `after_tool_call`: false (R-9).
6. **TIMEOUT (INV-12, NFR-9) and the release path: held.**
   - The 3.11.0 probe: a 0.2 s limit returned in 0.22 s, two children parked on futures and one sleeping child all unwound, and the probe raised `TimeoutError`.
   - In a second probe, a child that resolves the others' futures and returns early leaves them returning normally.
7. **EC-38, `KeyboardInterrupt` wrapped by the `TaskGroup`: false (R-11).** Evidence: `taskgroups.py:104-105`, `:145-147`, and the probe.
8. **AC-13: only `isDone` is added: held.** `tools/_internal.py:51-53` (`tools.add(IsDoneTool(), replace=True)`).
9. **Row 26's reply-text rule: held.**
   - `review_finish` runs at `runtime.py:559` (plain reply, no `tool_result`) and at `:664` (`isDone`, with `tool_call` and `tool_result`).
   - `ITERATION_OUTPUTS` is published at `:473-474`.
   - `IsDoneTool` returns the answer as its output (`tools/_internal.py:43-44`).
10. **Row 19's constructors: held.**
    - `BashTool(root_dir)`: `bash.py:42`.
    - `GrepTool(root_dir)`: `code_search/base.py:27`; `resolve_under_root` refuses escapes (`:28-34`), so INV-21 holds for grep too.
    - `PatchTool(root_dir)`: `editing/patch.py:27`.
    - `ReadLinesTool(config)` and `WriteTextTool(config)`: `filesystem/_base_tool.py:17`.
    - `FileSystemToolConfig(root, allow_write)`: `lib/dataclasses/filesystem.py`.
    - Precedent: `CodingAgentTools.get_tools`, `toolsets/coding.py:79-86`.
11. **Row 23 and §9.1 validators: held.**
    - `ProviderKeyMatcher.match(…, primary=<tuple>, field_name=…)`: `provider_keys.py:113`.
    - `require_int(minimum, maximum)` rejects `bool` (`validation.py:101-107`).
    - `to_folder`, `to_tuple` and `require_instance` signatures: `:204`, `:165`, `:242`.
    - `validate_provider_model_pair`: `models.py:344`; its lib caller is `config.py:514`.
12. **D-16: held.** `AGENT_SPEED_MILLISECONDS_PER_SECOND = 1000` is at `lib/constants/speed.py:18` and is exported from `lib/constants/__init__.py:80` and `:132`.
13. **Layering of the lib record: held.** `AgentMessage` (`lib/dataclasses/agents.py:385`) and `ToolStatus` (`lib/dataclasses/tools.py:40`) are both in lib, so `AgentSwarmResult` and `AgentSwarmEvent` import only lib (A006).
14. **§12.6 phases: held.**
    - P1 and P2 add only lib, prompt and toolset modules.
    - P3 leaves `import vidbyte` untouched, because `vidbyte.agents` imports the swarm package only from row 33 in P4.
    - Row 29 imports rows 23–28, so P3 is one commit in effect.
    - The two `harness_threads` failures are `test_harness_threads_surface.py:224-232` and `:235-258`, as stated.
    - No touched folder (lib/enums, lib/constants, lib/dataclasses, tools/toolsets) has an S020 `## File Index` README, so no README row is missing.
15. **Counts and leftovers: held.**
    - 23 new files and 13 modified files match §12.3.
    - 12 constants, 10 prompt keys and 10 leaves; 139/35 → 149/36.
    - No member-loop `AgentSwarmRuntime`, bare `AgentRuntimeType.AGENT_SWARM`, live `allow_zero`, search tool on `get_tools`, or run-state reset clause survives. "reset" and `allow_zero` appear only in §8.2 and D-11, D-16 and the withdrawn rows, as the rejected alternative.

Round-1 findings:

- **R-1: resolved for its original defect.** `OSError` and `ValueError` are dropped, and the text is the root cause from `__cause__`. The restatement overclaims for tools and `after_tool_call` (R-9).
- **R-2: resolved.** AC-13, AC-14, INV-21, FR-3, row 8 and §13 now include `isDone` and the agentic-loop prompt (`runtime.py:189-194`, `:254`).
- **R-3: resolved.** The vocabulary is consistent across the TL;DR, §2, §4, §5, D-2–D-4, D-11, D-12, D-15, §8.5, §9.2, rows 22 and 26–33, and A-2. It introduced R-10.
- **R-4: resolved.** `elapsed_ms` uses the existing `require_int(minimum=0)`; `validation.py` is untouched; row 4, INV-27 and D-14 are withdrawn.
- **R-5: resolved.** Row 19 is `get_tools(root)` only, and row 27 appends `message` and the optional search tool.
- **R-6: resolved.** §13 names the `on_event` → `Signal` seam. It is deterministic for AC-3, because `end_turn` marks the agent idle before its flush calls `on_event`.
- **R-7: resolved.**
  - Row 22 is first in P3.
  - The S025 exemption is stated correctly.
  - The `config.py:514` citation is fixed.
  - Row 8's section is "how the swarm works".

Optional questions raised by this review: none.
