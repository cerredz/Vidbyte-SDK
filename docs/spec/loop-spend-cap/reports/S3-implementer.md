# S3 implementer report: loop-spend-cap (r3)

- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap`
- **Branch:** `feat/loop-spend-cap`, pushed; tracks `origin/feat/loop-spend-cap`
- **Base:** `22993b5f` (`origin/main` at the start and again at the end of the run; no drift)
- **Spec:** `docs/spec/loop-spend-cap/spec.md` r3, now `status: implemented`
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1192 (draft, base `main`, placeholder body)
- **Run date:** 2026-10-20

## Commits

`git log origin/main..HEAD --oneline` (S3's commits first; the rest are S0-S2):

```
e4ee6050 docs(spec): correct the Spend Cap section line count in the S3 deviations
73170e0d docs(spec): record implementation proof for loop-spend-cap
e1fa7351 docs(spec): record draft PR for loop-spend-cap
2a69ffee style(agents): wrap the spend-cap comment blocks at 72 columns [W-5, W-10; FR-4, FR-11]
c554521e docs(agents): document the loop spend cap [W-9; FR-10, AC-26]
bcfc2654 feat(agents): refuse unenforceable caps, carry the cap through every copy, and end the run on a cap stop [W-6, W-7, W-10; FR-7, FR-8, FR-11, AC-11, AC-12, AC-13, AC-16, AC-23, AC-27, AC-28, AC-29, AC-30, AC-31, AC-32]
711db90d feat(agents): enforce max_spend_usd at the four agent loop check points [W-4, W-5, W-8; FR-3, FR-4, FR-5, FR-9, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-17, AC-18, AC-22]
e34ec9cf feat(agents): add max_spend_usd, the MAX_SPEND stop reason and UsageRollup.cost_measured [W-1, W-2, W-3; FR-1, FR-2, FR-5, FR-6, AC-2, AC-3, AC-19]
61e781f8 docs(spec): record loop-spend-cap S2 completion and S3 launch
b5a9e689 docs(spec): add loop-spend-cap S2 test-author report
19bfde45 docs(spec): record test proof for loop-spend-cap
021f73dc test(agents): add failing tests for loop-spend-cap [AC-1..AC-32]
643a52f6 docs(spec): record loop-spend-cap S1 approval
c95acf23 docs(spec): add loop-spend-cap S1 author r3 addendum
f1e7677e docs(spec): revise loop-spend-cap spec to r3 (review round 2, approved)
bd5458c1 docs(spec): add loop-spend-cap S1 review round 2
439ebf31 docs(spec): add loop-spend-cap S1 author r2 addendum
d49469ee docs(spec): revise loop-spend-cap spec to r2 (review round 1)
90f89924 docs(spec): add loop-spend-cap S1 review round 1
e5edcfef docs(spec): add loop-spend-cap S1 author report
a246ef08 docs(spec): add loop-spend-cap spec r1
6db4207e docs(spec): add loop-spend-cap request capture, recon, and pipeline state
```

Phase map: P1 = `e34ec9cf`, P2 = `711db90d`, P3 = `bcfc2654`, P4 = `c554521e`. `2a69ffee` only rewraps comments. The test tree is byte-identical to `b5a9e689` (`git diff --quiet b5a9e689 HEAD -- tests` exits 0).

## What was built, in data-flow order

1. **The setting.** `AgentLoopSettings(max_spend_usd=...)` validates through `RecordFieldValidator.require_number(..., "AgentLoopSettings.max_spend_usd", maximum=sys.float_info.max)`. It has no new `raise`. `to_runtime_config()` passes the value on, and `__repr__` shows it. File: `vidbyte/agents/settings/loop.py`.
2. **The runtime contract.**
   - `AgentRuntimeConfig.max_spend_usd` is appended last and validated in `__post_init__` the same way.
   - `AgentStopReason.MAX_SPEND = "max_spend"` sits right after `TIMEOUT`.
   - File: `vidbyte/lib/dataclasses/agents.py`.
3. **The completeness flag.** `UsageRollup.cost_measured` is a derived `@property`, exactly INV-2. It is not a field, so writing to it raises. File: `vidbyte/agents/pricing/records.py`.
4. **The policy.** `AgentSpendCap.stop_output(cap, rollup)` returns, in this order:
   - the reached text when `cost_usd is not None and cost_usd >= cap`;
   - else, when the rollup is not measured, the blind text with its causes in INV-9 order;
   - else `None`.

   `AgentSpendCap.model_refusal(cap, runner_config, fallback)` implements INV-13. It checks the runner type of the primary, then lists the unpriced chain entries in chain order, with OpenRouter exempt and a missing part shown as `?`. File: `vidbyte/agents/spend_cap.py` (new).
5. **The four check points.** `AgentRuntime._spend_cap_stop` returns `None` when no cap is set. Otherwise it reads `self.usage_tracker.rollup()` and builds `_stopped_result(..., stop_reason=MAX_SPEND)`. It is called at:
   - CP1, the first statement of `_budget_stop`;
   - CP2, the first statement of the `if not tool_calls:` finish branch;
   - CP3, the first statement of `_enforce_tool_settings`, before the internal-tool early return;
   - CP4, after the `after_iteration` abort and before `_after_tool_iteration`.

   File: `vidbyte/agents/runtime.py`.
6. **Routing.**
   - `FailureMetadataNormalizer._STOP_CODES["max_spend"] = RESOURCE_EXHAUSTED` (`vidbyte/sessions/failure/router.py`).
   - `EfficiencyBehavior._BUDGET_STOP_REASONS` includes `max_spend` (`vidbyte/evals/behavior/efficiency.py`).
7. **The construction refusals.**
   - `BaseAgent.__init__`, after the output-contract refusal, refuses a capped non-linear runtime, then any `model_refusal` text (`vidbyte/agents/base.py`).
   - `JevAgent._require_capped_specialists` refuses a specialist whose cap is missing or higher than JevAgent's (`vidbyte/agents/jev/agent.py`).
   - Codex refuses the cap through `CODEX_UNSUPPORTED_LOOP_FIELDS` (`vidbyte/lib/constants/codex.py`).
8. **The copy paths.** The cap survives:
   - `_export_loop_settings`, through the `base.py` field tuple;
   - `AgentForker._loop_settings` (`vidbyte/agents/fork.py`);
   - the fork tool's `_inherited_guardrails`, so the model cannot override it (`vidbyte/tools/builtins/fork/fork.py`);
   - YAML `agent.loop`, through `_LOOP_FIELDS` (`vidbyte/lib/dataclasses/config.py`).
9. **A cap stop ends the run.**
   - The queued-prompt drain stops (`base.py`).
   - Reflexion never reflects on it (`vidbyte/context/algorithms/reflexion.py`).
   - The critic, PDJ, and grader return the stopped result unreviewed (`vidbyte/agents/algorithms/*.py`).
   - A MultiAgent worker's task is blocked (`vidbyte/agents/multi/transfer.py`).
   - A manager phase raises `MultiAgentExecutionError` (`vidbyte/agents/multi/orchestrator.py`).
   - An InfiniteMemory generator is `FAILED`, so it gets no verifier (`vidbyte/agents/infinite/launch.py`).
10. **Docs.**
    - The agents README gains a Spend Cap section and a Key Modules bullet.
    - The Jev README gains the specialist rule.
    - `llms.txt` gets a table row plus its validation and projection text.
    - The failure vocabulary maps `max_spend` to `resource.exhausted`.
    - The two skill guides are updated.
    - The 0.4.0 release record gets its sentence.

## §12.3 rows

| Row | Path | Status | Commit |
|---|---|---|---|
| 1 | `vidbyte/agents/spend_cap.py` (CREATE) | done | `711db90d` (+ `@intent` on helpers in `bcfc2654`) |
| 2 | `vidbyte/agents/settings/loop.py` | done | `e34ec9cf` |
| 3 | `vidbyte/lib/dataclasses/agents.py` | done | `e34ec9cf` |
| 4 | `vidbyte/agents/pricing/records.py` | done | `e34ec9cf` |
| 5 | `vidbyte/agents/runtime.py` | done | `711db90d`, comments `2a69ffee` |
| 6 | `vidbyte/agents/base.py` | done | `bcfc2654` |
| 7 | `vidbyte/agents/fork.py` | done | `bcfc2654` |
| 8 | `vidbyte/tools/builtins/fork/fork.py` | done; not added to `_LOOP_SETTING_FIELDS` or the schema | `bcfc2654` |
| 9 | `vidbyte/lib/dataclasses/config.py` | done | `bcfc2654` |
| 10 | `vidbyte/agents/jev/agent.py` | done | `bcfc2654` |
| 11 | `vidbyte/sessions/failure/router.py` | done | `711db90d` |
| 12 | `vidbyte/evals/behavior/efficiency.py` | done | `711db90d` |
| 13 | `vidbyte/agents/README.md` | done | `c554521e` |
| 14 | `llms.txt` | done | `c554521e` |
| 15 | `skills/failure/vocabulary.md` | done | `c554521e` |
| 16 | `docs/design/release-0-4-0.md` | done; a pure append after the byte-identical before-text, with no PR number | `c554521e` |
| 17 | `vidbyte/agents/jev/README.md` | done | `c554521e` |
| 18 | `vidbyte/context/algorithms/reflexion.py` | done | `bcfc2654` |
| 19 | `vidbyte/agents/algorithms/independent_critic.py` | done | `bcfc2654` |
| 20 | `vidbyte/agents/algorithms/prosecutor_defender_judge.py` | done | `bcfc2654` |
| 21 | `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` | done (both sites) | `bcfc2654` |
| 22 | `vidbyte/agents/multi/transfer.py` | done | `bcfc2654` |
| 23 | `vidbyte/agents/multi/orchestrator.py` | done; `finalize` untouched | `bcfc2654` |
| 24 | `vidbyte/agents/infinite/launch.py` | done | `bcfc2654` |
| 25 | `vidbyte/lib/constants/codex.py` | done; `CodexContractValidator` untouched | `bcfc2654` |
| 26 | `tests/test_codex_output_contracts.py` | S2's row; not touched by S3 | `021f73dc` |
| 27 | `skills/agentic-loop-settings/SKILL.md`, `skills/output-contracts/SKILL.md` | done; only the named rows and the §6 list changed | `c554521e` |

**§12.4 checklist.** Every item holds. The evidence is under "Gates" below.
- The A001 header has all fields, and A001 stays at 642.
- Every new policy function or branch has its own `@intent`. A002 has the same 61 findings in the touched files at base and at HEAD.
- Every added or edited comment line is ≤ 72 columns: the `awk` check over the diff prints nothing.
- C001 is 26, C002 9, C006 104, A007 255, S008 19 and S024 25, all at baseline.
- `_process_tool_call` and `_generate_reply` are not edited.
- runtime.py adds 37 lines (≤ 40) and base.py 20 (≤ 25).
- There is no new dataclass, enum or error class.
- `lib/` imports only `lib`.
- No key-shaped literal: a grep of the added lines for `sk-…`, `vb_live_…` and `AKIA…` is empty.
- The version is still 0.4.0.
- "Measured", never "capped", is used for unseen spend.

**§12.5.**
- The READMEs, `llms.txt`, the vocabulary, the skills and the release record are done.
- There is no `__init__` export, registration or REPO_MAP change.
- `--update-baseline` was never run.
- This PR lowers no rule. The IMPROVED rules (A002 703→608, S010, S025, S061, S063) show the same counts as base: the touched files hold the same 61 A002 findings before and after.

## Deviations

These are also recorded under spec §17.

1. **`AgentSpendCap` has three private static helpers beyond the two methods.** They are `_blind_causes`, `_chain_runners` and `_unpriced_pairs`. With them, each method calls helpers one level deep (AGENTS.md principle 1) and stays at C901 ≤ 5. The behavior is exactly §8.5. A002 asked for an `@intent` on each, because each touches `provider`.
2. **The README Spend Cap section is 46 lines including its heading (45 of body).** *(Corrected in S5 iteration 1, S4 R-M3: it was 39 lines at this report's head `daad59fb`, not 38. S5 added 7 lines for spec r4's delegated-path check, R-M1 and R-M2.)* Row 13 asks for "at most about 36". The example is 7 code lines plus fences. Every clause row 13 requires is present. Cutting more would drop one of them.
3. **Comments are wrapped at 72 columns.** This follows field guide `comment-format.md`, which says a single line over 72 also becomes a block. The rewrap covers:
   - the CP2 and CP4 narration;
   - the edited lead comments of `_budget_stop`, `_enforce_tool_settings`, `_structured_phase` and `_inherited_guardrails`;
   - the six extended `@intent` blocks.

   In the `@intent` blocks the existing words are unchanged; only the line breaks moved.
4. **Row 6's `@intent spend-cap-is-never-silently-unenforced` covers both construction refusals.** It sits above the non-linear runtime check and the `model_refusal` call, because it states the reason for both.
5. **Row 22's branch reads `reply.metadata.get("stop_reason")` directly.** The `stop_reason` local is assigned only after the `@intent limit-stops-are-failed-attempts` block. The branch still sits after the middleware-abort branch and before `worker_stopped`.
6. **The placeholder PR body already existed** (written by the orchestrator) and was used as it was. Its wording paraphrases the briefing's sentence: S3 complete, spec path, replaced at S6, do not review yet.

## Files outside §12.3

None. `git diff --stat 61e781f8 HEAD` lists 27 files beyond the spec itself and this report. Every one of them is a §12.3 path.

## Budget (§8.4)

| Item | Allowed | Used |
|---|---|---|
| New files | 1 | 1 (`vidbyte/agents/spend_cap.py`) |
| New classes | 1 | 1 (`AgentSpendCap`) |
| New dependencies | 0 | 0 |
| New config keys | 1 | 1 (`max_spend_usd`) |
| NFR-5 `runtime.py` | ≤ 40 added | 37 added, 2 removed |
| NFR-5 `base.py` | ≤ 25 added | 20 added, 3 removed |

These are from `git diff --numstat 22993b5f -- vidbyte/agents/runtime.py vidbyte/agents/base.py`.

## Gates (final lines, at HEAD `2a69ffee` for code; docs-only commits follow)

1. **The pack plus the codex file** (re-run at `e4ee6050`):
   `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap tests/test_codex_output_contracts.py`
   ```
   174 passed in 1.43s
   ```
2. **The area suite** (the briefing's list without the pack):
   ```
   681 passed in 8.07s
   ```
   The same list plus `tests/test_jev_agent.py` gives `721 passed in 8.22s`.

   `tests/features/harness_threads/test_harness_threads_surface.py` plus the config and fork tests gives `1 failed, 66 passed`. The failure is the inherited red named below.
3. **Lint** (`PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py`, also run inside the source stage at `2a69ffee`): no rule REGRESSED.
   ```
   S008   bounded-function-complexity                19     19 RATCHETED
   A002   intent-comments                           608    703 IMPROVED
   SDK-LINT: PASS
   ```
4. **Import order** (`ruff check vidbyte --config lint/ruff.toml --select I001`): the per-file finding counts at HEAD are identical to a `git archive` of `22993b5f` (`diff` exit 0, 219 files). `spend_cap.py` has no finding.
5. **Complexity** (ruff C901, PLR0912 and PLR0915 at 10, 12 and 50, HEAD against base):
   - Only the baselined `BaseAgent.__init__` (17→19) and `_arun_once` (45→47) changed among the over-limit functions.
   - Exact C901 changes: `_enforce_tool_settings` 6→7, `_budget_stop` 5→6, `AgentRuntimeConfig.__post_init__` 4→5, `_structured_phase` 6→7, `default_report_parser` 4→5 and `InfinitePair._status` 3→4.
   - New functions: `_spend_cap_stop` 3, `stop_output` 3, `model_refusal` 4, `_blind_causes` 5, `_chain_runners` 2, `_unpriced_pairs` 4, `_require_capped_specialists` 4 and `cost_measured` 1.
   - `_process_tool_call` and `_generate_reply` are unchanged.
6. **Public API** (`scripts/generate-sdk-public-api.py --check`):
   ```
   contracts/sdk-public-api.json is current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).
   ```
   `git diff 22993b5f -- contracts/sdk-public-api.json vidbyte/lib/enums/failure.py vidbyte/__init__.py vidbyte/agents/__init__.py` is empty.
7. **Semgrep** (after `git add -A`, at `e4ee6050`):
   ```
   • Findings: 0 (0 blocking)
   Ran 1 rule on 1031 files: 0 findings.
   ```
8. **The source stage** (`PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`, at `2a69ffee`):
   ```
   SDK-LINT: PASS
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
   =========== 1 failed, 7672 passed, 18 skipped in 251.50s (0:04:11) ============
   CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-loop-spend-cap).
   ```
   The only failure is the **inherited local-only red** the briefing names. Its assertion reads:
   ```
   E         Left contains one more item: 'vidbyte/tools/builtins/fork/fork.py'
   ```
   That file is row 8's required edit. CI skips the merge-base clause, and the red clears on merge. The test was not edited. The MCP stdio flake did not occur.
9. **The package stage** (`env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package`, at `2a69ffee`):
   ```
   No broken requirements found.
   Installed vidbyte-sdk 0.4.0 passed smoke checks.
   CI passed.
   ```

## Tricky parts (look here first)

- **`model_refusal` on an agent with a model but no provider.** An agent built with only `model_name="gpt-5.4-mini"` and a cap is refused as `?:gpt-5.4-mini`. That is the spec's "a missing part shown as `?`" rule, and `Runner.build()` refuses such an agent anyway. A reviewer may still find it surprising that the agent runs uncapped but is refused once capped. Normalization goes through `Runner.from_model`, so `deepseek/deepseek-chat` with no provider resolves to `deepseek:deepseek-chat` and is priced.
- **The runner-type check reads only the primary.** A non-text fallback model is checked only for a price. That is §8.5 as written.
- **CP3 runs before `tool_is_internal`.** So isDone after the cap is reached stops the run with `max_spend` instead of finishing. This is intended (AC-6), but a cap stop now wins over an isDone that arrives in the same turn as the crossing call's result.
- **The drain.** `last_stop` is seeded from the primary reply's `metadata["stop_reason"]`. In `vidbyte/agents/multi/post_run.py:64`, which also calls `_drain_queued_prompts(metadata)`, a metadata without `stop_reason` yields `None` and changes nothing.
- **The `__init__` refusal order.** The non-linear refusal comes before `model_refusal`, so an MCTS agent on an image model reports the runtime, not the runner.
- **The hardest test** was not a test but the comment-format rule: the first lint pass showed A002 findings on the three `spend_cap.py` helpers, which became `@intent` blocks.

## For the reviewers

- **Check-point placement** (`vidbyte/agents/runtime.py` at HEAD):
  - **CP1:** `:2087`, the first statement of `_budget_stop` (`def :2077`), before the `max_iterations` check at `:2090`. `_budget_stop` is called at `:368`, after the context-window side calls and before `before_iteration`.
  - **CP2:** `:517`, inside `if not tool_calls:` (`:514`), before the `max_tokens` finish check.
  - **CP3:** `:1852`, the first statement of `_enforce_tool_settings` (`def :1845`), before `if tool_is_internal:` at `:1855`. `_process_tool_call` reaches it before `before_tool_call` (`:1761-1764`, unchanged).
  - **CP4:** `:707`, after the `after_iteration` abort (`:696-706`) and before `_after_tool_iteration` (`:711`).
- **Spend paths:**
  - `record_call` at `:478` (main call) is followed by CP2 or CP3 in the same iteration.
  - `record_billed_failure` at `:804` happens inside the model segment.
  - `record_call` at `:1060` (context-window side calls) happens before CP1 of the iteration.
  - `record_operation` at `:1399` happens inside the tool segment, and the next CP3 or CP4 sees it.
  - A child merge (`base.py:914`) happens when the child reply finishes, and the parent's next check sees it.
  - INV-6 lists what can still spend inside a segment.
- **Cap enforcement:** the per-runtime answers of §9.2 are each covered by a passing pack test:
  - linear: `test_loop_spend_cap_runtime.py`;
  - Jev: `test_loop_spend_cap_jev.py`;
  - refusals: `test_loop_spend_cap_refusals.py`;
  - copy paths: `test_loop_spend_cap_copy_paths.py`;
  - run ending: `test_loop_spend_cap_run_ending.py`;
  - children: `test_loop_spend_cap_children.py`.
- **Exact strings:**
  - The reached and blind texts are in `spend_cap.py:42,46`, and the cause wording in `:78-89`.
  - The model refusals are in `spend_cap.py:65,68`, and the runtime and agent prefixes in `base.py:254,257`.
  - The Jev message and details are in `jev/agent.py`.
  - The worker blocker is in `transfer.py`, and the manager message in `orchestrator.py`.
  - The pack asserts every one of them verbatim and passes.
- **Files outside §12.3:** none (see above).
- **Gate output:** quoted above.
