# S6 PR author report: AgentSwarm

Stage: S6 · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm` · Branch `feat/agent-swarm` · Started at `91d6c37f` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1174 (draft)

## What the code does (written from the diff, before reading the spec)

`AgentSwarm(settings).arun(goal)` refuses a second run on the same object and a goal that is not text, then `AgentSwarmWorkplace(settings.workplace).prepare()` creates the folder (parents included, contents kept; an `OSError` becomes `ConfigurationError` naming the path), and a fresh `AgentSwarmRuntime(settings, root).arun(goal)` runs. The `_running` flag is cleared in `finally`.

`AgentSwarmRuntime.arun` checks the goal again, refuses a second run of the same runtime, rebuilds the event record (so `elapsed_ms` counts from here), builds one `AgentSwarmMemberAgent` per member (the member's own system prompt, then the catalog swarm prompt naming it and its peers; tools = `AgentSwarmTools(root).all()`, then `message`, then the optional search tool; allow-all policy; history trim 90,000 tokens; tool-result cap 100,000 characters; `AgentSwarmTurnMiddleware`), records `AGENT_STARTED` per member, sets `turns = len(agents)`, and runs `async with asyncio.timeout(timeout_seconds), asyncio.TaskGroup()`: the start events are flushed inside the limit, then one `_run_member` task per agent. On `TimeoutError` the stop reason becomes TIMEOUT unless one was already decided. It then records `SWARM_ENDED`, flushes, and returns `AgentSwarmResult(stop_reason, events, replies, event_error_types)`; replies are the released agents' run results in member order.

Each member runs one `BaseAgent.arun(goal)` for the whole swarm on `AgentSwarmMemberRuntime`, which overrides only `_after_tool_iteration` to append `collect_messages` output as one user message. A `message` call goes to `post_message`, which refuses blank text, a non-peer, or a failed recipient with `ToolExecutionError` (turned into a tool error by the tool), queues the `MESSAGE_SENT` event itself in the recipient's inbox, and, when the recipient is waiting and turns remain, counts a turn, marks it working, records `AGENT_WOKE` and resolves its future, all with no `await`; only the flush is awaited. A finish attempt (plain reply or `isDone`) reaches `AgentSwarmTurnMiddleware.review_finish`, which calls `end_turn(name, reply)`: it records `AGENT_IDLE(text=reply)`; with mail waiting and turns left it records `AGENT_WOKE`, drains (one `MESSAGE_DELIVERED` per message) and returns the rendered inbox, which becomes `FinishReview.continue_with(text)`; otherwise it removes the agent from `_working`, creates a wake future, runs `_end_check`, flushes and awaits the future. After the wait, an agent still not in `_working` was released, so `end_turn` returns `""` and the middleware accepts the finish. `after_tool_call` records `TOOL_CALLED` for every non-internal tool.

`_end_check` does nothing while any agent works or a reason is decided; otherwise the reason is FAILED if every agent failed, MAX_TURNS if a non-failed agent still has mail, else QUIET, and every waiting future is resolved. `_run_member` contains a `VidbyteSdkError` (text = the `__cause__`'s type and message), a run that returns before release (text names the run's stop reason), and a `CancelledError` with `cancelling() == 0` and no decided reason (fails the agent, runs the end check, re-raises); every other cancel is re-raised untouched. `AgentSwarmEvents` is an outbox: `record` assigns the sequence synchronously; `flush` delivers undelivered events in order under a one-slot semaphore, marking each delivered before awaiting the callback, and keeps the type name of any `Exception` the callback raises.

## Section 4 snippet: ran as written

Run from a scratch folder with `PYTHONPATH=<worktree>`, the spec §4 snippet pasted unchanged inside `ScriptedSwarm(...).install()` (the test pack's scripted model; no API key, `OPENAI_API_KEY` unset; script `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s6/run_section4.py`, the same script as the AC-1 test). `vidbyte.__file__` resolved to the worktree. Output, exit 0:

```text
1 agent_started builder 
2 agent_started tester 
3 tool_called builder 
4 message_sent builder tester
5 tool_called builder 
6 agent_idle builder 
7 agent_idle tester 
8 agent_woke tester 
9 message_delivered tester builder
10 agent_idle tester 
11 swarm_ended  
quiet
True
swarm_ended
builder Wrote c2f.py.
tester Tests pass.
```

`swarm-workplace/c2f.py` existed afterwards and `event_error_types` was `()`. A second probe (`probe_idle_text.py`, same folder) confirmed that `AGENT_IDLE.text` is the model's plain reply after earlier tool calls in the same turn, and `isDone`'s answer for an `isDone` finish (not a stale tool result).

## Deviations found (code against spec r5)

Every one is already recorded in spec §17 or accepted by review; none is new:
1. `asyncio.Semaphore()` instead of `asyncio.Lock` (`events.py:151`), lint TID251/S039.
2. `ModelProvider(self.provider)` instead of `RecordFieldConverter.to_enum` (`lib/dataclasses/agent_swarm.py:70-73`), lint C012.
3. `callable(self.on_event)` instead of `require_instance(..., Callable)` (`settings.py:96`), mypy.
4. `AGENT_STARTED` flushed inside the time limit (`runtime.py:97-98`).
5. Sorted placement of imports and README/REPO_MAP entries.
6. `post_message(sender, recipient: object, text: object)` (`runtime.py:160`), wider than §8.5.
7. Event record built in `__init__` as a placeholder (`runtime.py:53`) and rebuilt at `arun` start (`runtime.py:79`).
8. Turn middleware in `vidbyte/middleware/builtins/agent_swarm_turn.py` (spec r4 adopted it; r5 matches).

Spec drift I fixed in the spec (docs only, commit `40a9f8d5`): §5's flowchart recorded `SWARM_ENDED` at the end check and drew no failure or time-limit path; replaced with the PR's two charts. The TL;DR said the swarm ends "at a turn or time limit"; a spent budget only stops wakes (INV-9, INV-10, EC-9), so it now says MAX_TURNS happens when a spent budget left a message waiting.

## Gates re-run by me at `91d6c37f` (code identical to `4a993f98`)

| Gate | Result |
|---|---|
| `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` | `171 passed in 5.56s` |
| neighbours (`tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/multi_agent tests/test_prompts_interface.py`) | `189 passed in 6.49s` |
| `python scripts/generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at 698f913b594f9cbeac6513d4883c0e4f0f1f4175 (vidbyte-sdk 0.3.0, 649 exports).` |
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | `SDK-LINT: PASS` (0 `REGRESSED`, `S063 IMPROVED 4 -> 3`); pytest `3 failed, 6414 passed, 16 skipped in 127.49s`, the three inherited `harness_threads` surface tests (`assert 148 == 120`; `At index 30 diff: 'AgentSwarm' != 'JevAgent'`) |
| `env -u PYTHONPATH python scripts/run_ci.py --stage package` | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Semgrep 1.170.1 (`scratchpad/semgrep-venv`, venv `Scripts` first on `PATH` in `/c/...` form) | `Findings: 0 (0 blocking)` / `Ran 1 rule on 995 files: 0 findings.` |
| mermaid 11.4.1 parser (`scratchpad/s6/mmd/check.mjs`) on pr-body.md and spec.md | every block `OK`; both PR charts also rendered with Playwright and read cleanly |

Logs: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s6/` (`source-stage.log`, `package-stage.log`, `semgrep.log`, `flow1.png`, `flow2.png`).

## PR state

Commit `40a9f8d5` (`docs(spec): finalize agent-swarm for PR`: spec frontmatter `status: pr-open`, §5 charts, TL;DR, §17 row, and `pr-body.md`) was pushed without force (`91d6c37f..40a9f8d5`). `gh pr edit` set the title and body; GitHub's stored body equals `pr-body.md` minus line 1, apart from the trailing newline GitHub trims.

`gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1174 --json title,isDraft,baseRefName,headRefOid,url` after the edit:

```text
{"baseRefName":"main","headRefOid":"40a9f8d5d09f578757fb8bd7a3ae1154da7bc42d","isDraft":true,"title":"feat(agents): add AgentSwarm — agents you define share one folder, run their tools, and message each other until the swarm goes quiet","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1174"}
```

`gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1174`:

```text
no checks reported on the 'feat/agent-swarm' branch
```

That is by design: CI and static policy run only on manual dispatch. I dispatched both on `40a9f8d5` and watched them to the end (`gh run watch --exit-status`, exit 0 for both):

| Workflow | Run | Jobs | Final lines |
|---|---|---|---|
| CI `ci.yml` | 39010164516 | Source / Python 3.11 success · Source / Python 3.12 success · Package success | 3.11: `SDK-LINT: PASS` / `6376 passed, 57 skipped in 112.22s` / `CI passed.` · 3.12: `SDK-LINT: PASS` / `6376 passed, 57 skipped, 19 warnings in 117.28s` / `CI passed.` · Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Static policy `static-policy.yml` | 39010166215 | Static policy success | `Findings: 0 (0 blocking)` / `Ran 1 rule on 995 files: 0 findings.` |

`agents-md-placement.yml` was not dispatched. The next commit adds only this report and the run table in `pr-body.md`, then the body is re-applied with `gh pr edit`. The PR stays a draft; `gh pr ready` and merge were not run.

## Candidate field-guide lessons (not written to the field guide; this PR has no human review yet)

1. **Agent-specific middleware lives in the middleware layer** (R-4). Trigger: a feature needs an `AgentMiddleware` subclass for one agent. Preferred action: define it in `vidbyte/middleware/builtins/<feature>.py`, import the agent-layer types under `TYPE_CHECKING`, do not re-export it from `vidbyte.middleware.builtins`, and import it where the agent is built. Reason: the owner asked on PR #399 that middleware "should be defined in the middleware layer", and every other agent-specific middleware (`delegation_limits`, `verify_command`) lives there. Quick check: `grep -rn "(AgentMiddleware)" vidbyte | grep -v "^vidbyte/middleware/"` prints nothing. Link: PR #1174, `034ca1cb`.
2. **Lib records keep per-kind checks in `__post_init__`, not in `_check_*` helpers** (R-13). Trigger: a `vidbyte/lib/dataclasses` record whose valid fields depend on a kind enum. Preferred action: a module-level table of allowed fields per kind plus one pass in `__post_init__`, with every primitive check a `RecordFieldValidator` call. Reason: strict-config-dataclasses.md asks for no private `_..._field` helpers; folding them in kept S008 at baseline. Quick check: `grep -n "def _check" vidbyte/lib/dataclasses/<domain>.py` is empty. Link: PR #1174, `965bd9ea`.
3. **A reserved tool name the lib layer cannot import is refused in the agent's settings** (R-2). Trigger: a developer-supplied tool must not shadow a loop-internal tool such as `isDone`. Preferred action: refuse `(*<FEATURE>_RESERVED_TOOL_NAMES, IS_DONE_TOOL_NAME)` in the `*Settings.__post_init__`, importing `IS_DONE_TOOL_NAME` from `vidbyte.tools._internal`; leave the lib constant tuple alone. Reason: the loop does `tools.add(IsDoneTool(), replace=True)` and silently drops a same-named tool, and A006 forbids `vidbyte/lib/constants` importing `vidbyte.tools`. Quick check: build the settings with a search tool named `isDone` and expect `ConfigurationError`. Link: PR #1174, `fee22acb`.
4. **TaskGroup member tasks must handle a stray `CancelledError`** (R-3). Trigger: a coordinator runs long-lived member tasks in an `asyncio.TaskGroup` and tracks "who is working". Preferred action: `except asyncio.CancelledError:` that marks the member failed and re-runs the end check only when `asyncio.current_task().cancelling() == 0` and no end is decided, then always `raise`. Reason: Python 3.11's TaskGroup ignores a cancelled child, so the coordinator otherwise waits out its whole time limit; S019 fails a swallowed cancel. Quick check: a tool that raises `CancelledError` ends the run in well under `timeout_seconds` with one `AGENT_FAILED`. Link: PR #1174, `fbb2f445`, `87df4fc9`.
5. **Model-facing prompt families state facts, never working advice** (R-1). Trigger: writing a swarm or multi-agent prompt leaf or tool description. Preferred action: describe what a call does and how it can fail; drop "so do X" clauses ("keep working", "say what is left", "read the file again"). Reason: the owner does not want prompts to "influence the same biases as the InfiniteMemoryAgent", and the contract test's role-word list cannot see these clauses. Quick check: grep the family for "so keep", "so say", "instead of waiting". Link: PR #1174, `68813700`.
6. **Validate model-emitted values no stricter than the spec** (R-8). Trigger: a record built from a model's tool call inside middleware with `fail_closed=True`. Preferred action: require only what the spec states (here, non-blank); no `one_line=True`. Reason: a refusal inside fail-closed middleware aborts the whole member run instead of producing a tool error the model can correct. Quick check: a tool call named `'bash\nrm'` ends as a tool error, not `agent_failed`. Link: PR #1174, `ccf4e52d`.
7. **Edited comment blocks are re-wrapped at 72 columns** (R-7). Trigger: a PR touches an existing long `#` comment, such as `_LINEAR_LOOP_RUNTIMES` in `vidbyte/agents/base.py`. Preferred action: re-wrap the whole block at 72 columns. Reason: comment-format.md. Quick check: `awk 'length > 72' <file>` over the edited block. Link: PR #1174, `e40b2f95`.
8. **A File Index names out-of-folder files dotted, not as paths with a suffix** (S5 iteration 1). Trigger: a package README's `## File Index` mentions a module in another folder. Preferred action: name it as a dotted module (`vidbyte.middleware.builtins.agent_swarm_turn`). Reason: S020 reads every backticked token with a file suffix in a File Index as an entry that must be a tracked direct child; the path form regressed S020 from 1 to 2. Quick check: `python lint/run.py --rule S020`. Link: PR #1174, `034ca1cb`.

## Things that looked wrong while reading

- `tests/features/agent_swarm/FEATURE.md:5`: "The swarm ends when no agent is working and no message is waiting, or at a turn or time limit." Same class as R-6/R-17: a spent turn budget stops wakes but does not end the swarm by itself. Test-pack prose only; I fixed the identical sentence in the spec TL;DR but may not edit tests. Minor.
- The briefing says two tests assert their events directly because the oracle is stricter than r4. On the branch it is three: `test_the_time_limit_firing_after_the_end_was_decided_keeps_the_decided_stop_reason`, `test_a_cancelled_error_raised_by_on_event_on_an_idle_agent_fails_it_instead_of_waking_it`, and `test_an_unrequested_cancel_after_the_end_was_decided_does_not_fail_the_released_agent` (the third came in S2 round 3). The PR body names all three. Not a defect.
- `contracts/sdk-public-api.json:3` records `source.commit` `698f913b`, an older commit; `--check` reports it current, so the generator does not pin the head. Not a defect.
- No product bug found. No vacuous test seen in the AC-mapped tests; I did not audit the property module in depth.
