# S6 PR author report: loop-spend-cap (R3, vidbyte-sdk PR #1192)

STATUS: DONE. PR #1192 is still a draft, now titled `feat(agents): add a USD spend cap that every agent loop enforces`. Its body is `docs/spec/loop-spend-cap/pr-body.md` from line 2 on. Head `995cfdfb`, pushed (fast-forward from `eba8bf85`, no force). No source, test, or contract file changed in this stage.

## 1. What the code does (written from the diff, before the spec was opened)

- **Setting.** `AgentLoopSettings(max_spend_usd=...)` (`vidbyte/agents/settings/loop.py`) is validated by `RecordFieldValidator.require_number(..., maximum=sys.float_info.max)`. That refuses bool, NaN, ±inf, ≤ 0, and non-numbers with `ConfigurationError`. An `int` beyond float range raises `OverflowError` instead, which I checked: `10**400`. The value is copied to `AgentRuntimeConfig.max_spend_usd` (`vidbyte/lib/dataclasses/agents.py`), which validates it again, and it is carried by `__repr__` and `BaseAgent._export_loop_settings`. It is also carried by `AgentForker._loop_settings` and YAML `_LOOP_FIELDS`. `ForkConversationTool._inherited_guardrails` re-applies it as a guardrail the model cannot override.
- **Construction refusals** (`vidbyte/agents/base.py:249-257`).
  - A capped non-linear runtime is refused.
  - `AgentSpendCap.model_refusal` (`vidbyte/agents/spend_cap.py:49-69`) builds one `Runner.from_model` per chain entry, primary first. It refuses when the primary resolves to a non-text runner, or when any non-OpenRouter entry has no pricebook price; each pair is named once, in chain order, with `?` for a missing part. It returns `None` when the agent has neither a provider nor a model.
  - `JevAgent._require_capped_specialists` (`vidbyte/agents/jev/agent.py:128-144`) refuses a specialist whose own cap is missing or above JevAgent's.
  - `CodexHarnessAgent` refuses through `CODEX_UNSUPPORTED_LOOP_FIELDS`.
- **Run-time check.** `AgentRuntime._spend_cap_stop` (`vidbyte/agents/runtime.py:1881-1891`) returns at once when uncapped. Otherwise it calls `AgentSpendCap.stop_output(cap, usage_tracker.rollup())`. That returns the reached text when `cost_usd >= cap` (checked first), or the blind text naming each cause when `not rollup.cost_measured`, or else `None`. A text result becomes `_stopped_result(text, MAX_SPEND)`.
- **Where it is checked.** The tool calls of a turn run one at a time, because the runtime has no parallel tool path, so CP3 sees each call.
  - CP1: the first clause of `_budget_stop` (`:2087`), called at the top of each iteration (`:368`), after the context-window side calls.
  - CP2: first in the plain-text branch (`:517`), before `max_tokens` and all finish work.
  - CP3: the first step of `_enforce_tool_settings` (`:1852`), before the internal-tool early return.
  - CP4: after the `after_iteration` abort and before `_after_tool_iteration` (`:707`).
  - Delegated CP1: `JevRuntime._delegate` (`vidbyte/agents/jev/runtime.py:227-229`, with its `@intent` at `:222`), after `begin_delegated`/`require_accounted()` and before `specialist.agent.arun`. It returns through `response.finished(stop, usage.settle())`, so `usage_rollup` is the run total, and it skips `_finish_result`.
- **Ledger.** `UsageRollup.cost_measured` (`vidbyte/agents/pricing/records.py:93-109`) is True only when recording is intact, no call was unaccounted, and every call and operation has a price. An empty ledger is measured.
- **The run ends after a stop.**
  - The stop reason maps to `resource.exhausted` (`vidbyte/sessions/failure/router.py:48`).
  - Evals count it as a budget stop.
  - Reflexion does not reflect.
  - The critic and PDJ return the producer.
  - The grader returns the trial.
  - A MultiAgent worker is BLOCKED (`retryable=False`), and a manager phase raises `MultiAgentExecutionError` with `details["stop_reason"]`.
  - `InfinitePair` marks the run FAILED, so no verifier runs.
  - The queued-prompt drain stops (`base.py:1211`).
  - Still running after a stop: `after_run` middleware (through `_finish_result`) and a configured auto-handoff.

## 2. Snippet output (spec §4, verbatim)

- Extracted from `spec.md:78-98` (CRLF stripped) to `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r3-s6/snippet_s4.py`.
- **Live form.** `PYTHONPATH=$(pwd) py -3.11` from the worktree, with `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `VIDBYTE_API_KEY`, `GROK_API_KEY`, and `DEEPSEEK_API_KEY` unset. Exit 1. The agent constructs, then `agent.run` raises `AgentExecutionError: Agent 'researcher' failed to generate a reply.`. Its cause is `ConfigurationError: Missing Vidbyte API key. Pass vidbyte_api_key or set VIDBYTE_API_KEY, or use mode=TextModelMode.DIRECT to call the provider with your own key and no Vidbyte fee.`. That error is raised in `TextRunner.__init__` → `model_configs.validate` → `resolve_vidbyte_api_key`, before any request. The snippet runs as written and needs a live call, so this is not a deviation.
- **Offline form.** Script `.../scratchpad/r3-s6/drive_snippet.py`. It runs the verbatim file with `runpy`, in a fresh interpreter per case. The Vidbyte key is built at run time, and only `HttpTransport.request` is replaced, which is the AC-1 seam. Output, from `.../scratchpad/r3-s6/snippet_offline.out`:
  ```
  == cap      [driver] usage={'input_tokens': 1024000, 'output_tokens': 10}  wire calls=1
  stopped at $0.7680: reached the $0.50 cap
  == blind    [driver] usage=None  wire calls=1
  stopped: spend could not be fully measured (at least $0.0000)
  == finished [driver] usage={'input_tokens': 1000, 'output_tokens': 10}  wire calls=1
  finished; spent $0.0008
  ```
  Each case exited 0. The cap case shows the overshoot: one call took a $0.50 cap to $0.7680.
- **Offline surface probe.** Script `.../scratchpad/r3-s6/offline_surface.py`, output `.../offline_surface.out`.
  - Settings: the round trip holds (0.5 in, 0.5 out of `to_runtime_config()`, and in the repr), and the six invalid values are refused with the §9.2 message.
  - Refusals: the unpriced model is refused, the same model uncapped constructs, and MCTS is refused.
  - Copy path: `export_state` carries the key.
  - `stop_output`: an empty rollup gives `None`, a cost of 0.5 gives the reached text, an unaccounted call gives "1 model calls reported no usage", and a corrupted ledger gives "usage recording failed".
  - Ledger and routing: `UsageRollup().cost_measured` is True while `cost_complete` is False, and `max_spend` routes to `resource.exhausted`.

## 3. Deviations found (all are in the PR body)

1. `AgentSpendCap` has three private helpers beyond §8.5's two methods. Behavior is §8.5 (S3 record).
2. The README `## Spend Cap` section is 46 lines against "about 36". The re-review found no cut.
3. One `@intent spend-cap-is-never-silently-unenforced` block covers both construction refusals, where row 6 puts it above `model_refusal` only.
4. Row 22's branch reads `reply.metadata.get("stop_reason")` directly, because the local is assigned later. Placement matches the row.
5. Six extended `@intent` blocks were reflowed to 72 columns (`2a69ffee`).

Checked and not deviations:
- §4: the snippet runs as written, live or over the AC-1 seam.
- §5: it still matches the code at its level of detail, including the r4.2 `DL` node, so I did not change it. Its line citations are `base_commit` lines: the child merge it cites as `base.py:882-886` is at `base.py:914` on this branch.
- §8.5: the signatures and messages match the code.
- §12.3: all 28 rows are present.

## 4. Changes made in S6

- `b4f564a9` `docs(release): name #1192 in the 0.4.0 record's loop spend cap sentence`. It inserts ` (#1192)` after "The loop spend cap" at `docs/design/release-0-4-0.md:17`. A byte-level replace asserted exactly one match. The word diff is `+(#1192)` only, and CRLF count is 19 → 19. `:19` is untouched. No test reads the file (`git grep release-0-4-0 -- tests` is empty).
- `995cfdfb` `docs(spec): finalize loop-spend-cap for PR`. It adds `pr-body.md`, which is LF so the title line carries no CR. In `spec.md` it sets `status: pr-open` and appends one §17 row (`r4 | 2026-10-20 | S6 PR | finalized for review...`), with CRLF 1016 → 1017 lines. `pr:` and `updated: 2026-10-20` were already correct.
- Pack rerun after `b4f564a9`: `188 passed in 1.53s`. I did not run `run_ci.py`, per the briefing.
- Mermaid checks:
  - It was parsed and rendered with mermaid 11.4.1 in a headless browser: `OK nodes=20 edges=28`, which equals the declared counts.
  - A first render showed two defects, now fixed. `__init__` rendered as bold "init", and the five-way stop edge repeated its long label five times.
  - The live PR page renders it in GitHub's viewscreen iframe, 1690px tall, with no error box. Screenshot: `.../scratchpad/r3-s6/pr_mermaid.png`.
- Body round trip: `gh pr view --json body` equals `pr-body.md` from line 2 on, 34,225 characters each. The key-literal scan of the body (`sk-`, `vb_live`, `ghp_`, `AKIA`, `xox`) finds nothing.

## 5. Final PR state

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1192 --json title,isDraft,baseRefName,url
{"baseRefName":"main","headRefOid":"995cfdfb574c0ea28593f40430a9fac1e7361674","isDraft":true,"title":"feat(agents): add a USD spend cap that every agent loop enforces","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1192"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1192
no checks reported on the 'feat/loop-spend-cap' branch        (exit 1)

$ gh run list --branch feat/loop-spend-cap
39422108655 Static policy workflow_dispatch eba8bf85 completed success
39422105237 CI workflow_dispatch eba8bf85 completed success   (jobs: Source / Python 3.11, Source / Python 3.12, Package: success)
```
- `.github/workflows/ci.yml` has its automatic triggers removed ("TEMPORARILY DISABLED"), so the push started no run on `995cfdfb`.
- The last green remote runs are on `eba8bf85`: 2 of 2 workflows, 4 of 4 jobs.
- `git diff --stat 0be0545d HEAD -- . ':!docs/spec'` lists only `docs/design/release-0-4-0.md`.
- `origin/main` (`22993b5f`) is an ancestor of the head.

## 6. Candidate field-guide lessons (not written to the field guide)

Each entry is in the field guide's shape (When · Do · Because · Check · Evidence), and each comes from a confirmed finding in `review.md` or the re-review.

1. **S009 slack is not permission for a new mypy error** (conventions, R-2)
   - When: a change adds or edits a file under `vidbyte/` and `lint/run.py` prints `SDK-LINT: PASS`.
   - Do: run `py -3.11 -m mypy --config-file lint/mypy.ini vidbyte` at base and head, and diff the findings keyed on (path, code, message with line numbers masked, source line). Zero new findings.
   - Because: S009's baseline is 350 while 346 errors are found, so PASS hides up to four new errors. The rule says "any increase is treated as a new defect" (`lint/rules/s009_staged_mypy_contracts.py:26-27`). Lint discovers files through `git ls-files`, so a `git archive` copy shows every finding as NEW unless you run `git init && git add -A` in it first.
   - Check: S009 `found` equals base.
   - Evidence: PR #1192 R-2, `b7e13995`.
2. **Keep a hard-wrapped Markdown file's width, and keep token pairs a docs test greps together on one line** (conventions, R-M4)
   - When: adding a sentence to a hard-wrapped skill file such as `skills/failure/vocabulary.md` (81 columns at most).
   - Do: hand-wrap to the file's width, and keep tokens a docs test expects on one line together, such as `max_spend` with `resource.exhausted`.
   - Because: an unwrapped 106-column line breaks the file's convention, and a `textwrap` reflow at 76 to 80 columns splits the pair and turns `test_each_named_doc_mentions_the_cap` red.
   - Check: the file's maximum line width, plus the pack's docs test.
   - Evidence: PR #1192 R-M4, `977086ff`.
3. **A check added to `AgentRuntime`'s loop must also run on JevAgent's delegated path** (engineering, R-1)
   - When: adding any per-run limit or guard at `_budget_stop`, `_enforce_tool_settings`, or another loop check point.
   - Do: also call it in `JevRuntime._delegate`, after `begin_delegated`/`require_accounted()` and before `specialist.agent.arun`, and return through `self.response.finished(result, self.usage.settle())`.
   - Because: `_arun_metered` returns `await self._delegate(...)` before `super().arun` (`jev/runtime.py:129-130`), so no loop check runs on a delegated run, and the specialist's own ledger starts at $0.
   - Check: a test where the gate picks a specialist and the pre-loop spend reaches the limit asserts 0 specialist runner calls.
   - Evidence: PR #1192 R-1, `54a11a21`, AC-33.
4. **A construction check on the model must read it the way the runner reads it** (engineering, R-4 and R-M5)
   - When: a constructor check reads `runner_config.provider` or `model_name`, or the fallback chain.
   - Do: build `Runner.from_model(...)` per chain entry (index 0 is the primary), and test three cases: `provider=None` with a slug-form `openai/<model>`, a bad primary in front of a good fallback, and a duplicated bad fallback.
   - Because: `Runner` normalizes slug-form models, so `runner_config.provider` can be `None` while the call is billed under `openai`. Tests that always pass `provider=` let `or`→`and` and `models[1:]` mutants survive.
   - Check: both mutants are killed.
   - Evidence: PR #1192 R-4, `b3796d74`.
5. **"Costs nothing when unset" needs a test that pins the caller, not an output** (engineering and conformance, R-3)
   - When: an opt-in feature promises no work on the default path, as NFR-1 or INV-17 do here.
   - Do: wrap the shared method, here `UsageTracker.rollup`, to record `sys._getframe(1).f_code.co_name`. Assert no call from the feature's helper on an uncapped run, plus a capped control that does make such calls.
   - Because: output-equality tests cannot fail on wasted work, and absolute call counts vary by scenario (reviewers measured 2/6, the verifier 1/8).
   - Check: a mutant that computes the rollup before the `None` return is killed.
   - Evidence: PR #1192 R-3, `test_an_uncapped_run_computes_no_spend_cap_rollup_or_price`.
6. **Do not write "nothing runs after a stop"** (conformance, R-M1)
   - When: documenting what follows a runtime stop reason.
   - Do: say that no SDK step continues the stopped work, and name `after_run` middleware and a configured auto-handoff as still running, and able to spend.
   - Because: every loop stop leaves through `_finish_result`, which runs `after_run`, and `BaseAgent` then runs the auto-handoff, session notification, delivery, and the drain (`base.py:1022-1036`).
   - Check: probe the hooks and the handoff spend after a stop.
   - Evidence: PR #1192 R-M1, `de093778`.
7. **Each drained queued prompt is a new reply with a reset ledger** (re-review R-C1)
   - When: designing a per-run limit on an agent that can hold queued prompts (`enqueue_prompts`, `run_prompts_sequentially`).
   - Do: state the bound per reply, and stop the drain on the limit's stop reason.
   - Because: `_drain_queued_prompts` calls `generate_reply` once per prompt, which resets the tracker. A parent that delegates to such an agent therefore sees up to `1 + max_queued_prompts` fresh limits (probe: 3.201×C).
   - Check: probe with `max_queued_prompts` ≥ 1.
   - Evidence: PR #1192 A-9, `68b67231`.

(The inherited local-only red from `test_harness_threads_surface.py:270-278` is already in `field-guide/vidbyte-sdk/local-ci-verification.md`, per spec §12.3 row 8, so it is not repeated here.)

## 7. Things that looked wrong while reading (none blocks this PR; no source was changed)

- `vidbyte/agents/spend_cap.py:5`: the ARCHITECTURE NOTE lists the four loop check points but not the delegated CP1 in `JevRuntime._delegate`. This is re-review R-C2, code half, and it is a follow-up in the body.
- `vidbyte/lib/dataclasses/jev.py:3863`: the `JevAgentResponse.specialist` docstring says "the title of the JevSpecialist that ran the task", which is false after a delegated cap stop (A-8). It is a follow-up in the body.
- `docs/design/release-0-4-0.md:19`: "Do not tag until the Meta key fix, #1184, is on `main`" is stale, because #1184 is on `main` as `513aa614`. It is a follow-up in the body and was left untouched, per the briefing.
- `docs/design/release-0-4-0.md:17`: the spec-prescribed sentence lists "every model call, tool call, finish attempt, and compute checkpoint" and does not mention the delegated check before a Jev specialist. It is accurate but incomplete. I did not edit it beyond `(#1192)`.
- `vidbyte/agents/spend_cap.py:63`: the runner-type refusal reads only `runners[0]`, the primary. A text primary with a non-text fallback (`FallbackModel("openai", "gpt-image-2")`) is refused today, but by the pricing rule, with the message "the pricebook has no price for openai:gpt-image-2", not by the runner-type rule. This is a latent edge rather than a defect. It fails closed now, but if the pricebook ever priced that model, a capped text agent with an image fallback would construct. Probe: `.../scratchpad/r3-s6/probe_fallback_kind.py`.
- I found no vacuous test. Test strength rests on the recorded mutation runs: S2b, 11 of 11 killed; S4, M0 to M3; re-review, M1 to M6 plus five R-1 mutants, all killed. I did not run mutants myself.

## 8. Notes for the orchestrator

- This report is written but not committed. `git add` it with your pipeline record before you dispatch CI on the final head.
- PR authors take note: in a mermaid label on GitHub, `__init__` renders as bold "init". Write "constructor" instead.
