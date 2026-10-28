LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The diff implements every FR, INV, AC, and EC of spec r3 and every user answer in request.md §A/§D. The shared loop is untouched. One P0 NFR is violated (NFR-8: 72-column comment blocks in runtime.py). Fixing it collides with the test suite's 400-line cap, so S2 or the orchestrator must route that first. Four Minor accuracy gaps remain.

Reviewed: `git diff 39ce8b20...936e3278`, against spec r3 FR-1..FR-18, NFR-1..NFR-8, INV-1..INV-37, AC-1..AC-25, EC-1..EC-16, §8.4 budget, §12.3 rows 1–40, §14, and request.md §A/§D.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **Exactly-once outcomes are structural.** Each runtime state change is one await-free block followed by one awaited outbox flush. `_stop` decides the reason once (INV-12). `_run_member` ends each agent with exactly one of released, cancelled, failed, or exited (INV-14). Every message gets exactly one outcome, delivered or undelivered (INV-7). On a timeout, `_stop(TIMEOUT)` cancels the tasks that never started, in member order (EC-10).
- **Loose messaging matches D-4/INV-6 and the user's "message any agent anything".** Only blank text and an unknown name are refused, and both are recorded as `message_refused`. The `validate_call` override (member.py:177-182) is the smallest way to keep the loop's own required-parameter check from preempting those refusals. A self-message is queued. A message to a stopped recipient, or one sent after the stop decision, is a success reply recorded as `message_sent` + `message_undelivered` in the same block.
- **Compaction is built on the SDK engine, not a bespoke one** (D-11/D-12, FR-8..FR-10).
  - It runs in `_after_tool_iteration`, before mail.
  - It calls `ContextCompactionEngine.compact_provider_messages(SUMMARIZE_RANGE, keep_last)`.
  - The trigger measures `total_prompt_tokens` against 72,000; the target is 27,000.
  - The summary side call is metered once: UsageTracker, `tokens_used`, the budget, and `model_called`, in the EC-6 order (`model_called`, then `compaction`).
- **Settled decisions are honored exactly.**
  - The settings live in `vidbyte/lib/dataclasses/agent_swarm.py` and import nothing from higher layers.
  - Web search is a validated provider table.
  - The limits are exact to §11: 500 agents, 10,000,000,000 tokens, and the stated time and message caps.
  - All 24 event kinds have a per-kind field table, and `AgentSwarmResult` checks for exactly one `swarm_stopping`.
  - All 23 leaves meet their sentence counts, and the prompt enum holds 162 members in 36 families.
  - `vidbyte/agents/runtime.py`, `base.py`, `lib/dataclasses/validation.py`, and `lint/baseline.json` show an empty diff (NFR-1, NG-1).

## FINDINGS (ranked)

R-C1 [Major] [conformance/NFR-8, §12.4, row 34] vidbyte/agents/agent_swarm/runtime.py:51 (and 54, 65, 95, 98, 102, 108, 113, 118, 128, 131, 137, 140, 146, 159, 174, 175, 181, 183, 188, 213, 215, 220, 227, 236, 255, 274, 276, 320, 327, 333, 339, 347, 358, 377, 390, 398, 405) — runtime.py breaks the P0 rule that comment blocks are wrapped at 72 columns
  Evidence:
  - NFR-8 (P0, spec.md:350) requires "72-column comment blocks". The §12.4 checklist (spec.md:941) repeats it: "comment blocks are wrapped at 72 columns — source: A002; comment-format.md". Row 34 cites `comment-format.md`.
  - In runtime.py, 38 of 55 comment lines carry more than 72 columns of text after `# `. The widest is 385 columns, at line 146.
  - The r5 runtime.py had 93 comment lines and none over 72. Every other changed module (member.py, compaction.py, events.py, swarm.py, the observer/trim middleware, the turn middleware, the toolset, and lib/dataclasses/agent_swarm.py) has none.
  - S3's report lists this only under tricky parts. It is not listed as a deviation, and it is not in spec §17.
  - The cause is a hidden conflict. `runtime.py` is at 398 lines after its header. Rewrapping those 38 comments at 72 columns adds 61 lines, which makes 459. The S2 test `test_new_modules_stay_inside_the_complexity_budget_and_never_sleep` (tests/features/agent_swarm/test_agent_swarm_contract.py:834) asserts `<= 400` as a hard cap. Row 34 calls 400 a "target" with a "hard limit 1,000", and NFR-8 says "well under 1,000".
  Failure: A human reviewer applying AGENTS.md comment-format.md to the PR's largest module finds 38 one-line comments of up to 385 columns. Each one needs horizontal scrolling. The rule is a P0 NFR, so the module does not meet its acceptance gate. Fixing it in place turns the contract test red. The implementer may not edit tests, so the fix cannot land without a decision.
  Smallest fix: Route the conflict to S2/the orchestrator first. Relax the contract test's cap for runtime.py to match row 34: for example, `<= 480` for runtime.py, or a `< 1,000` hard check plus a 400 target that is reported but not asserted. Then rewrap the 38 comments at 72 columns, with no change in wording. Alternatively, keep the 400 cap and move `_render_system_prompt`/`_build_member` (about 40 lines) into member.py. That is a larger change and touches row 34's inventory.
  Spec IDs: NFR-8, §12.4 checklist row (spec.md:941), §12.3 row 34, D-row field guide `comment-format.md` (spec.md:788)

R-C2 [Minor] [conformance/INV-24, INV-13] vidbyte/middleware/builtins/agent_swarm_observer.py:88-99 with the tuple order at vidbyte/agents/agent_swarm/member.py:223 — After the stop is decided, `history_trimmed` is still recorded for a model call that the observer then refuses
  Evidence:
  - The middleware order is `(AgentSwarmTrimMiddleware, AgentSwarmTurnMiddleware, AgentSwarmObserverMiddleware)`.
  - `MiddlewarePipeline` runs the `before_model_call` hooks in sequence. The trim's hook runs first and awaits `record_history_trim` whenever the transform reports `changed`, without checking `swarm_runtime.stopping`. Only after that does the observer return `ABORT_RUN agent_swarm_stopping`.
  - In the probe, a fake swarm had `stopping=True`, and 10 messages of 40,000 characters each went through the real two-middleware pipeline. The result was `decision: MiddlewareAction.ABORT_RUN agent_swarm_stopping` and `history_trimmed recorded while stopping: [('ada', 1)]`.
  - INV-13 says that after the decision "no agent calls the model again", and the package README (line 38) repeats it. INV-24 ties `history_trimmed` to the call the trim changed.
  Failure: A member reaches `before_model_call` with a history over 90,000 estimated tokens after `swarm_stopping` has been recorded, for example after a budget stop. The log then shows `swarm_stopping`, then `history_trimmed` for that agent, then `agent_exited`/`agent_released`. That `history_trimmed` describes a model call that never happened. The only consumer of the trim record is someone reading the log, and it misleads them about what was sent after the stop.
  Smallest fix: In `AgentSwarmTrimMiddleware.before_model_call`, return `MiddlewareDecision.continue_()` early when `self.swarm_runtime.stopping` is set, so the observer's abort follows. Or keep the trim and skip only the `record_history_trim` call. Add one fixture case for "trim after stop records nothing".
  Spec IDs: INV-13, INV-24, FR-14, §5 hook order

R-C3 [Minor] [deviations/INV-26, D-14] vidbyte/agents/agent_swarm/runtime.py:255-259 — `file_changed` takes its path from the call arguments, not the tool result metadata that INV-26/D-14 name, and S3 did not report the change
  Evidence:
  - INV-26 (spec.md:224) and D-14 (spec.md:379) say the path is "`write_text`'s `metadata["path"]`; `patch_file`'s `metadata["file_path"]` resolved". A-7 is the assumption behind it.
  - The code reads `call.arguments.get(_FILE_TOOLS[call.tool_name])` and resolves `self._root / raw`.
  - Today the two give the same path:
    - `WriteTextTool` reports `resolve_scoped_path` = `(root / Path(path)).expanduser().resolve()`. `expanduser` has no effect on a path that starts at an absolute root, and an absolute path outside the root fails before SUCCESS.
    - `PatchTool` reports the raw `file_path` argument.
  - Neither S3's deviations list nor spec §17 records this. D-14's "Revisit when" trigger is "`PatchTool` starts reporting the resolved path". That trigger presumes the metadata is the source, so it no longer fits.
  Failure: Nothing changes today. If `WriteTextTool` later normalizes the target differently from `root / raw`, for example by following a symlinked root or adding case folding, `file_changed` keys would split from what the tool actually wrote. INV-26's peer detection would then miss a collision. D-14's revisit trigger would not fire, because the code never reads the metadata.
  Smallest fix: Read `result.metadata.get("path")` for `write_text` and `result.metadata.get("file_path")` for `patch_file`, then resolve against the root, as D-14 states. Or keep the argument read and add a one-line deviation to S3's report and to spec §17 (D-14).
  Spec IDs: INV-26, D-14, A-7, EC-16

R-C4 [Minor] [conformance/FR-18, D-4] vidbyte/prompts/README.md:112 — The prompts README still says "`message_sent` and the three refusals are its replies", which is the r5 design that D-4 rejected
  Evidence:
  - D-4 (spec.md:369) lists "Keep the three r5 refusals" as the rejected alternative.
  - INV-6 and the rewritten leaf `message_stopped_recipient.md` ("Message recorded for {recipient}, but {recipient} has stopped and will not receive it.") make the stopped-recipient reply a successful tool result.
  - runtime.py:178-187 calls `_refuse` only for `message_blank_text` and `message_unknown_recipient`, and returns `message_stopped_recipient` as a success.
  - FR-18 (P0) requires the prompts README to "describe the revised feature".
  Failure: A maintainer who edits the leaves from the README rewords `message_stopped_recipient` as a refusal. That contradicts INV-6 and AC-5, which require a success result.
  Smallest fix: Change the clause to "`message_sent` and `message_stopped_recipient` are its replies, `message_blank_text` and `message_unknown_recipient` its two refusals".
  Spec IDs: FR-18, D-4, INV-6, AC-5

R-C5 [Minor] [conformance/FR-18] vidbyte/agents/agent_swarm/README.md:117 — The README's debugging guide says a `record_model_call` bug always shows up as `agent_exited`. A bug on the compaction side call shows up as `agent_failed`
  Evidence:
  - README line 117 says a bug in "the observer's ... `record_model_call` ... surfaces as `agent_exited` with text `middleware_abort`".
  - That holds for the observer path (agent_swarm_observer.py:53). But `record_model_call` is also awaited from `AgentSwarmMemberRuntime._count_side_call` (member.py:152), inside `_after_tool_iteration`, where no fail-closed middleware wraps it.
  - The runtime header (runtime.py:4) itself says "the first two also by the member runtime for its summary call".
  Failure: A recording bug that occurs only after an automatic or requested compaction ends the member as `agent_failed`, and `text` names the exception. Someone following the README's "check `agent_exited`" guidance looks in the wrong place.
  Smallest fix: Add "(or `agent_failed`, when the call is the compaction summary's)" to the `record_model_call` clause.
  Spec IDs: FR-18, INV-14

Not findings (recorded for the next stage):
- The §5 flow diagram diverges from the code and from the spec's own text in three places, and the code follows the text each time:
  - The summary call's order is `model_called` then `compaction`, per EC-6. The diagram shows the reverse.
  - Terminal events come from `_run_member`, except the never-started cancels inside `_stop(TIMEOUT)`, per INV-12/INV-14. The diagram draws them from `_stop`.
  - `_run_member` passes `provider` to `_build_member`. This is S3 deviation 5, and it is not drawn.
- `_compact` catches only `VidbyteSdkError` (member.py:137-141), as the §8.5 pseudocode says. The HTTP transport wraps transport errors in that type.
- `_end_check` → `_stop` is a two-level call chain. Row 34 mandates it ("`_end_check` calls `_stop`"), so it is not an NFR-8 finding.

## VERIFIED CLAIMS

- **NFR-1/NG-1.** `git diff --stat 39ce8b20...936e3278 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py lint/` is empty. The shared loop, BaseAgent, the validators, and the lint baseline are untouched.
- **§12.3 scope.** Every product file in the diff appears in §12.3 rows 1–40, and none is outside it. The test tree changes are S2's only (fix commit 1ddc6b9d). Its three edits fix the harness and loosen no assertion.
- **§8.4 budget.** 16 files, 8 new classes, 0 new dependencies, and 3 settings fields. All are on budget.
- **AC-1.** `test_the_section_4_snippet_runs_as_written` passes against the scripted runner. No real provider was called.
- **Feature pack.** 268 tests pass, including AC-2..AC-25 as mapped in the test plan.
- **FR-1/INV-1.** The prompt enum has 162 members in 36 families. There are 23 `agent_swarm` leaves. Each `system_*` section has at least 6 sentences, and each tool description has 6–8. The constants header's estimate of about 2,697 tokens for 8 sections (about 182 for web search) checks out arithmetically.
- **FR-17/C016.** `scripts/generate-sdk-public-api.py --check` reports the contract current at 650 exports.
- **Lint.** `lint/run.py` prints SDK-LINT: PASS with exit 0. It also prints `S061 IMPROVED 6 -> 5`. S3 reported only S063 (4 -> 3), so S061 is an unreported improvement. The baseline is unchanged, so this is not a defect.
- **S3 deviation 1** (`validate_call` returns None). It is minimal. `BaseTool.validate_call` checks only missing or `None` required parameters, and the swarm's own refusals cover both.
- **S3 deviation 5** (provider passed by `_run_member`). It has no effect for real runners. On a real `TextModelRunner`, `BaseAgent._runner_provider(runner)` returns `'anthropic'`, the same as `runner_config.provider`, and `_run_direct` pops `provider` anyway.
- **INV-26 equivalence today.** `resolve_scoped_path` gives the same key as `(root / raw).resolve()` for every input that reaches SUCCESS. R-C3 is about the unrecorded mechanism, not a wrong path today.
- **INV-37.** No `sleep` and no `Lock` appear in the swarm package or the swarm middleware; the only mention is in a header docstring.
- **request.md §A/§D.** All of the following are implemented and covered by named tests:
  - the four user-listed event groups
  - the Prompt 5 answers 1–10
  - Q-1..Q-5 defaults: messaging is loose, blank text is refused, the limits are generous, the settings live in lib, and every agent gets the same prompt

## COMMANDS RUN

- `PYTHONPATH=<wt> python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` → `268 passed in 7.55s`
- `PYTHONPATH=<wt> python -m pytest "tests/features/agent_swarm/test_agent_swarm_acceptance.py::test_the_section_4_snippet_runs_as_written" -q -p no:cacheprovider` → `1 passed in 0.85s`
- `git -C <wt> diff --stat 39ce8b20...936e3278 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py lint/` → (empty)
- `PYTHONPATH=<wt> python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at a319f44d... (vidbyte-sdk 0.3.0, 650 exports).`
- prompt-count probe (Prompt enum + leaf glob) → `members 162 families 36` / `agent_swarm leaves 23`
- `PYTHONPATH=<wt> python lint/run.py` → `S061 IMPROVED 6 -> 5 ... S063 IMPROVED 4 -> 3 ... SDK-LINT: PASS` / `exit=0`
- awk comment-width count (text after `# ` > 72) → runtime.py `comment-lines=55 over72text=38`; r5 runtime.py (at 39ce8b20) `comment-lines=93 over72text=0`; member.py, compaction.py, events.py, swarm.py, observer, turn middleware, toolset, lib dataclass: `over72text=0`
- `_lines_after_header(runtime.py)` + textwrap(72) probe → `lines after header: 398` / `extra lines if rewrapped at 72: 61`
- scratchpad probe `s4_conf_probe_trim_after_stop.py` (real `MiddlewarePipeline` with trim + observer, fake swarm `stopping=True`) → `decision: MiddlewareAction.ABORT_RUN agent_swarm_stopping` / `history_trimmed recorded while stopping: [('ada', 1)]`
- runner-provider probe (builds a `BaseAgent` with a dummy key, no model call) → `TextModelRunner text` / `has _config: True provider label: anthropic` / `runner_config.provider: 'anthropic'`
- `grep -n "sleep\|Lock" vidbyte/agents/agent_swarm/*.py vidbyte/middleware/builtins/agent_swarm_*.py` → header-docstring mention only
