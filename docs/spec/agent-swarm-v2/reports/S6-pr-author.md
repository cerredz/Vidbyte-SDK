# S6 PR author report: AgentSwarm v2 (PR #1174)

Stage: S6, the last stage. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2`, branch `feat/agent-swarm`. Start head `c86dda43`, which is clean and pushed. No source or test file was changed. Written: `docs/spec/agent-swarm-v2/pr-body.md`, the spec frontmatter, §5 and §17, and this report.

## What the code does, in my own words (written from the diff, before the spec)

- **Entry.** `AgentSwarm.arun(goal)` (`vidbyte/agents/agent_swarm/swarm.py:36`) does three things:
  - It refuses a second concurrent run and a non-text goal.
  - It creates the folder with `AgentSwarmWorkplace.prepare()`, which returns whether this run created it.
  - It hands over to a fresh `AgentSwarmRuntime(settings, root, workplace_created=...)`.

  `AgentSwarmSettings` (`vidbyte/lib/dataclasses/agent_swarm.py:212`) has already validated everything at construction. That covers 2–500 unique names, the folder, the limits, the web-search provider and key pair, a callable `on_event`, and keys matched to providers. Each refusal names `AgentSwarmSettings.<field>`. The key fields have `repr=False`.
- **Run setup.** `AgentSwarmRuntime.arun` (`runtime.py:97`) records `workplace_prepared` with `folder_state`. For each member it then:
  - renders the shared prompt with `_render_system_prompt`: the nine `system_*` sections, with the web-search section only when set, and only `{name}`, `{peers}`, `{workplace}`, and `{search_tool}` substituted;
  - builds the member with `_build_member`, which supplies the five workplace tools, `message`, `compact`, then the search tool, with the loop adding `isDone` last;
  - records `agent_created`, then `agent_started`, in member order.

  It counts N turns, then runs `asyncio.timeout(timeout_seconds)` around one `TaskGroup`, with one `_run_member` task per member. The start flush is inside the time limit.
- **One member.** A member is one long `BaseAgent` loop under `AgentSwarmMemberRuntime` (`AgentRuntimeType.AGENT_SWARM_MEMBER`, resolved by `RuntimeRegistry`). Its middleware runs in this order (`member.py:251`):
  - `AgentSwarmTrimMiddleware` trims each outgoing call to 90,000 tokens and records `history_trimmed` with the trim's own count. It skips once the swarm is stopping.
  - `AgentSwarmTurnMiddleware` records `tool_called`. Its `review_finish` turns a finish into `end_turn`.
  - `AgentSwarmObserverMiddleware` aborts every call once the swarm is stopping. `after_model_response` calls `record_model_call`, which records `model_called` and checks the budget. `on_model_error` records `model_error` and always continues. `after_tool_call` calls `record_tool_outcome`, which records `tool_result_truncated`, `file_changed`, and `command_failed`.
- **After every tool iteration.** `AgentSwarmMemberRuntime._after_tool_iteration` (`member.py:80`) runs these steps in order:
  1. It takes the pending `compact` request, if any.
  2. It computes the whole-message chars/4 estimate and the measured context (`last_prompt_tokens`, or the estimate when no usage was reported).
  3. A compaction is due on a request, or automatically when the measured context is at least 72,000. After the first compaction, the estimate must also have grown by 27,000 since the last one.
  4. If a compaction is due and the swarm is not stopping, it calls `ContextCompactionEngine.compact_provider_messages(SUMMARIZE_RANGE, keep_last)` through `_compact`. `AgentSwarmHandoffSummarizer` writes the 10-section summary through the member's own runner (`call_model` → `_runner_for_model` / `_invoke_runner`).
  5. When a summary call was made, it snapshots the new estimate. `_count_side_call` then records the usage in the UsageTracker, `tokens_used`, the budget, and `model_called`, followed by `record_compaction`.
  6. Only then does `collect_messages` append the inbox as one user message.

  A failed summary call records `model_error` and keeps the history (`_compact` catches it).
- **Messaging.** `post_message` (`runtime.py:203`) refuses only two inputs, each recorded as `message_refused` with nothing queued: blank or non-text text, and an unknown name. A message to a failed or exited agent, or any message sent after the stop, is recorded as `message_sent` plus `message_undelivered` and gets a success reply. Otherwise the message is queued. An idle recipient is woken (`agent_woke`, one turn counted), or, with no turn left, `wake_refused` is recorded. All of this happens in one block with no `await`.
- **Turn end.** `end_turn` (`runtime.py:251`) records `agent_idle`. It then does one of three things:
  - After the stop, it returns `""`.
  - With mail and a turn left, it starts the next turn at once.
  - Otherwise it records `wake_refused` per waiting message, parks the agent, and runs `_end_reason`. When that returns a reason, `_stop(reason)` runs in the same block.
- **Stop.** `_end_reason` (`runtime.py:447`) is pure. When nobody is working it returns FAILED if no agent is left, MAX_TURNS if a running agent holds mail, and QUIET otherwise. `_stop` (`runtime.py:424`) is the only setter, and it runs in this order:
  1. On TIMEOUT only, it records `agent_cancelled` (working) for members still counted as working, whose tasks never ran a cancel branch.
  2. It records `swarm_stopping`.
  3. It marks every queued message `message_undelivered` and empties the inboxes.
  4. It resolves every parked agent's wait.

  The `max_tokens` stop comes from `record_model_call` (`runtime.py:337`). The time-limit stop comes from `arun` after the task group (`runtime.py:139`).
- **Endings.** `_run_member` (`runtime.py:150`) gives each agent exactly one ending:
  - An SDK error becomes `agent_failed`.
  - A stray cancel (`task.cancelling() == 0` before the stop) becomes `agent_failed`, and the cancel is raised again.
  - The swarm's own cancel becomes `agent_cancelled` with `working` or `idle`, recorded without a flush.
  - A return after release or after the stop becomes `agent_released`, and the reply is kept.
  - An early return becomes `agent_exited`, with the loop's stop reason as text.
- **End.** `arun` records `swarm_ended` last and flushes. `AgentSwarmResult.__post_init__` checks the numbering, one `swarm_stopping` with the result's reason, and `swarm_ended` last. Callback exceptions are kept by type name in `event_error_types`.
- **Untouched.** `git diff 39ce8b20..fc89377b^1 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py` is empty (NFR-1). `vidbyte/agents/base.py` differs from main by the PR's own 12-line registration of `AGENT_SWARM_MEMBER` in `_LINEAR_LOOP_RUNTIMES`, from the first revision.

## The §4 snippet, run as written (scripted)

Driver: `<scratchpad>/s6/scripts/snippet_driver.py`. It pastes spec §4 verbatim inside `_snippet_swarm().install()` and `FakeTavily().install()`, run from `<scratchpad>/s6/snippet-run` with `PYTHONPATH=<worktree>`. stderr confirmed that `vidbyte` loaded from the worktree. Tavily queries were `['celsius to fahrenheit formula']`, there were 0 unscripted calls, and `c2f.py` was written. No real model or search provider was called. stdout:

```text
1 workplace_prepared
2 agent_created ada
3 agent_created ben
4 agent_created cleo
5 agent_started ada
6 agent_started ben
7 agent_started cleo
8 model_called ada
9 tool_called ada
10 file_changed ada
11 model_called ada
12 message_sent ada ben c2f.py is ready; please test it.
13 tool_called ada
14 model_called ada
15 agent_idle ada  Wrote c2f.py.
16 model_called ben
17 agent_idle ben  Waiting for the code.
18 agent_woke ben
19 message_delivered ben ada
20 model_called ben
21 agent_idle ben  Tests pass.
22 model_called cleo
23 tool_called cleo
24 model_called cleo
25 agent_idle cleo  Formula checked.
26 swarm_stopping
27 agent_released cleo
28 agent_released ada
29 agent_released ben
30 swarm_ended
quiet 30 3
```

AC-1's test, `test_agent_swarm_acceptance.py::test_the_section_4_snippet_runs_as_written`, gives `1 passed in 0.78s`. The snippet needed no correction.

## Gates I ran myself (on `c86dda43`)

- Pack: `281 passed in 7.75s`. Pack plus `tests/test_prompts_interface.py`: `286 passed in 7.98s`. Codex host: `215 passed in 15.36s`.
- `python lint/run.py`: `SDK-LINT: PASS`.
- `python lint/run.py --all --format json`: exit 0, 91 rules (48 CLEAN, 36 RATCHETED, 7 IMPROVED), 3,937 findings. Only one finding names a swarm line: S051 I001 at `vidbyte/lib/registries/runtimes.py:33`.
  - It is the lazy import `from vidbyte.agents.agent_swarm import AgentSwarmMemberRuntime`, placed before the infinite and jev imports.
  - Main's copy of the same block fails I001 too: `git show origin/main:vidbyte/lib/registries/runtimes.py`, checked with `ruff --select I001`, gives `I001 … runtimes.py:33:9`.
  - S051 is at its baseline, 259 of 259 (RATCHETED). The swarm's own modules are clean (`ruff --select I001` on them: `All checks passed!`).
- `python scripts/generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at 654deee6d2893e83f67164bd331e0f92c941cd85 (vidbyte-sdk 0.4.0, 742 exports).`
- `python scripts/run_ci.py --stage source`: `SDK-LINT: PASS` … `2 failed, 8666 passed, 18 skipped in 294.59s` · `CI failed: Command failed with exit code 1: … -m pytest`.
  - The two failures are main's `tests/features/harness_threads/test_harness_threads_surface.py` tests:
    - `:278`: `Left contains 2 more items, first extra item: 'vidbyte/tools/README.md'`;
    - `:309`: the six `AgentSwarm*` root names are not in `vidbyte.harnesses.native.__all__`.
  - Both diff against `git merge-base origin/main HEAD`, and `merge_base()` (`:139-143`) skips when CI's shallow clone has no `origin/main`.
- Not run by me:
  - The package stage, because it installs a wheel and this stage may install nothing.
  - Local semgrep. The scratchpad venv's semgrep resolves the global `mcp` 2.x and dies on `mcp.server.fastmcp`, an environment fault and not a code fault.
  - Both are cited from the orchestrator's merge record (pipeline.md: `CI passed.` and `Ran 1 rule on 1047 files: 0 findings.`). Static policy re-runs semgrep remotely on the final head.
- AC proofs: every test named in spec §6.2 exists in its module. The parametrization counts match §6.2: AC-4 has 7 rows; AC-8, AC-12, and AC-17's first test have 2 each; the property module has 36 cases. `assert_event_invariants` has 67 call sites.

## Deviations found (code vs spec)

1. The S3 deviations 1–10 are in spec §17 and confirmed in the code. Deviation 7 was superseded by R-16: `_changed_path` and `_command_failure` exist again at `runtime.py:463` and `:474`.
2. The R-8 variant: the member-runtime refusal's details name the first missing part (`member.py:58-67`).
3. The merge edit `9ed61e09` to main's `tests/features/codex_host/test_codex_host_packaging.py`, which adds `AgentSwarmTools` to the exact `toolsets.__all__` pin.
4. §5 drift, now fixed in the spec and noted in §17:
   - The r7 flowchart drew `agent_released`, `agent_cancelled`, `agent_failed`, and `agent_exited` as edges out of `_stop`. They come from `_run_member` (`runtime.py:163,176,184,192,195`). `_stop` records only `agent_cancelled`, on TIMEOUT, for tasks that never started (`runtime.py:433-436`).
   - The §5 prose said `request_compaction` records events. It records none (`runtime.py:350-356`).
   - The prose listed `_fail` and `_stop` as flushing. Both are synchronous, and their callers flush.
   - §5's sequence diagram is still accurate and was left alone.

None of these changes behavior against the ACs.

## PR state after the edit

The title and body were edited in place from `pr-body.md` (title = line 1, body = `tail -n +2`). A read-back of the live body matches the file byte for byte, except for one trailing newline that `--jq` adds. The body ends with the `Generated with Claude Code` line.

```text
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1174 --json title,isDraft,baseRefName,headRefName,headRefOid,url
{"baseRefName":"main","headRefName":"feat/agent-swarm","headRefOid":"c86dda43ae9606ab1de0b7359d6cb367c7cc37fc","isDraft":true,"title":"feat(agents): add AgentSwarm — agents share one prompt and one folder, message any agent, compact their own history, and report 24 kinds of events","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1174"}
$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1174
claude	skipping	0	https://github.com/cerredz/Vidbyte-SDK/actions/runs/39707409737/job/119590618965
```

That read-back was taken before this report's commit was pushed, so `headRefOid` is the old head. The only check listed is the `@claude` review workflow, which the body edit triggered, and it is skipping, not failing. CI and Static policy run only when dispatched. Their runs on the commit that adds this report are named in the PR body's Verification table and in the S6 STATUS block, because a commit cannot name its own runs.

The flow chart renders on GitHub without a syntax error. I checked this in a browser (`agent-browser`, public PR page): the page has one `viewscreen.githubusercontent.com/markdown/mermaid` frame, no "Unable to render" text, and a screenshot showing the drawn chart (`<scratchpad>/s6/mermaid-pr.png`).

Review threads: each got a reply naming its fixing commits and was then resolved. A `reviewThreads` read-back shows all four `isResolved=true`:

| Thread | Original comment | Reply comment | Gist |
|---|---|---|---|
| `PRRT_kwDOShl6qc6uGVej` | 4318715506 (settings location) | 4343754771 | Moved to `vidbyte/lib/dataclasses/agent_swarm.py` (`adb0b316`); `settings.py` deleted (`20dbbcd9`); user chose lib ("7) lib folder.") over AGENTS.md exception 1. |
| `PRRT_kwDOShl6qc6uGWYn` | 4318721573 (general messaging tool) | 4343754975 | Quotes answer 6, "forget this, keep the messaging tool specific to this runtime". The tool stays in `member.py`, now loose (`c19fdddb`, `20dbbcd9`). |
| `PRRT_kwDOShl6qc6uGXgX` | 4318728824 (caps) | 4343755151 | Quotes answer 8. New limits, and the token budget with `max_tokens` (`17b99742`, `adb0b316`, `20dbbcd9`); "5,00" read as 500. |
| `PRRT_kwDOShl6qc6uGXyu` | 4318730679 (web search) | 4343755317 | Quotes answer 9. `web_search` plus `web_search_api_key`, five providers, refusals at settings time (`61ecccd4`, `adb0b316`). |

## Candidate field-guide lessons (not written to the field guide; this PR has no human review yet)

1. **A line cap hides comment wrapping.**
   - When: a module sits near a test-enforced line budget and its comments run long.
   - Do: count comment lines over 72 columns (`awk 'length($0) > 72' f | grep -cE '^\s*#'`) before trusting that the module "fits". Raise the per-module budget with the test owner rather than squeezing the narration that AGENTS.md §2 requires.
   - Because: here, 52 over-wide lines were the only reason `runtime.py` passed its 400-line check.
   - Check: that count is 0 for every touched file.
   - Evidence: R-3, `6455f9e9`, `c9a5d0db`.
2. **An IMPROVED ratchet hides new findings.**
   - When: a rule's verdict is IMPROVED or RATCHETED.
   - Do: run `python lint/run.py --all --format json` and filter its findings to the touched files. Do not read `SDK-LINT: PASS` as "no new findings".
   - Because: A002 (`@intent`) found 565 against a baseline of 703, so it printed PASS while three new policy functions lacked `@intent`.
   - Check: the JSON has no finding in a touched file, or each one is shown to exist on main too.
   - Evidence: R-4, `a12973e7`.
3. **Estimate the whole provider message.**
   - When: code estimates a provider message's size.
   - Do: count the whole message (`str(message)`, or the engine's per-message text), never only `message["content"]`.
   - Because: Gemini tool turns carry `parts` and no `content`, and OpenAI tool-call turns carry `content: None` with the arguments in `tool_calls`. Both counted 0, and compaction never fired.
   - Check: a test with a Gemini-shaped and a write-only OpenAI history compacts.
   - Evidence: R-2, `8e56aaea`; R-20, `ce8053ed`.
4. **Main pins export lists exactly.**
   - When: a branch adds a name to a package `__all__` (such as `vidbyte/tools/toolsets/__init__.py`) and then merges main.
   - Do: grep main's tests for exact pins of that `__all__` and run them on the merge commit.
   - Because: git flagged no conflict, but main's Codex-host test pinned `toolsets.__all__` without the new name.
   - Check: `rg -n "__all__ ==" tests` covering the touched package, run on the merge.
   - Evidence: `9ed61e09`.
5. **Docs must not promise retries the code lacks.**
   - When: docs or a spec describe retry behavior.
   - Do: trace it to a reader of the setting.
   - Because: `AgentLoopSettings.max_retries` is stored but read by no loop code, and a test-installed retry made AC-10 pass.
   - Check: `grep -rn max_retries vidbyte --include=*.py` shows a reader, or the docs say there is no retry.
   - Evidence: R-5, `360ceab1`.
6. **Main's branch-scoped tests fail other branches locally.**
   - When: the source stage fails `tests/features/harness_threads/test_harness_threads_surface.py`.
   - Do: check whether the failure is the branch's own new files or root names compared against `origin/main`, before calling it a regression.
   - Because: those tests assert that a branch leaves `vidbyte/tools` and root `__all__` as main has them, and they skip on CI's shallow clone.
   - Check: `merge_base()` at `:139-143`.
   - Evidence: this PR's 2 failures.

## Observations while reading (no change made)

- `vidbyte/middleware/builtins/agent_swarm_observer.py:61` and `:62-65`: the `on_model_error` docstring says to "let the loop's own retry and fallback decide", and the comment says "the loop's retry policy is untouched". AgentSwarm installs no retry (R-5). The comment is true only of a retry a caller installs at the seam. This is a wording nit, listed in the PR's Follow-ups.
- `vidbyte/lib/registries/runtimes.py:33`: a lazy `vidbyte.agents` import from `vidbyte/lib/`. INV-19's "every other module under `vidbyte/lib/`" literally covers it, but main's registry already lazy-imports Jev and Infinite the same way. The line dates from the first revision. It is not a new violation. It is also the S051 I001 site.
- `vidbyte/agents/agent_swarm/compaction.py:59-60`: a summary call that succeeds with empty text still compacts, so the older history becomes the prefix alone and `compaction` is recorded. Spec EC-24 accepts this on purpose ("a thin summary; the kept groups and the workplace remain ground truth"), so it is not a deviation. I list it in the PR's Follow-ups as an owner decision, because a model that returns no text loses the agent's record of earlier messages.
- `member.py:166`: `_compact` catches only `VidbyteSdkError`. A non-SDK exception from the summarizer leaves the loop, and `BaseAgent` wraps it, so the agent ends as `agent_failed`. That matches the package README's note on summary-call bugs.
- No dead code, vacuous test, or unguarded `None` found in the swarm modules. `member.py`'s side-call usage is read behind a `None` guard, as INV-35 and EC-8 require.

## Not done, by rule

- The PR stays a draft. No field-guide write. No source or test change. No package-stage or semgrep run, because the first installs and the local semgrep environment is broken (see above).
