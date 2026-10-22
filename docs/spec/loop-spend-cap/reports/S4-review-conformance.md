LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The code at daad59fb meets every FR, NFR, INV, AC, EC and §12.3 row I checked. The fixes needed are two README sentences that misstate or leave out the spec's contract for how a run ends and which runtimes are capped, plus one INV-17 clause that no test kills.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The four check points sit exactly where INV-5 puts them, and the pack pins each one:
  - CP1 is the first statement of `_budget_stop` (`runtime.py:2087`, ahead of `max_iterations` at `:2090`).
  - CP2 is inside `if not tool_calls:` (`:517`).
  - CP3 is the first statement of `_enforce_tool_settings` (`:1852`, ahead of `if tool_is_internal:` at `:1855`).
  - CP4 is after the `after_iteration` abort and before `_after_tool_iteration` (`:707`/`:711`).
  - Each placement mutant was killed: M11–M15, M45 (the INV-8 tie) and M47 (child merge).
  - Do not move any check point.
- All 18 user-visible strings match the spec byte for byte: the reached and blind stop texts, the 4 non-linear refusals, the refusals for non-text, unpriced primary and unpriced fallback (in chain order) models, the 2 Jev refusals, the worker and manager literals, and the 3 fork-tool refusals. The OpenRouter exemption also holds.
  - The blind causes are sorted. The unpriced chain keeps configured order (M40–M42 killed).
- INV-14 holds on every path:
  - `AgentLoopSettings`, `AgentRuntimeConfig`, YAML through `vidbyte.config.YamlLoader`, and `lib/config/loader`.
  - It rejects `0`, `-1`, `True`, NaN, ±inf and `'1'` with the spec's exact message and `details`, and accepts `5e-324`.
- On the default path (INV-17/NFR-1) a HEAD run matches a 22993b5f run exactly in output, metadata, `cost_usd`, and the number of `rollup()` and `resolve()` calls, across 5 scenarios. No `AgentSpendCap` code runs.
  - Every INV-23 site and every INV-15 copy path has a test that kills its mutant (M01–M07, M25–M35, M44).

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [docs/INV-23] vidbyte/agents/README.md:410 — "Nothing runs after a cap stop" contradicts INV-23's last paragraph, EC-36 and G-3
  Evidence: README.md:410-412 reads "Nothing runs after a cap stop: no retry, reflection, review, grading, verifier, or queued prompt, and a `MultiAgent` worker's task is blocked."
    - spec.md:269 (INV-23): "The reply then still runs `after_run` middleware and a configured auto-handoff (INV-6 "End of run")."
    - spec.md:43 (G-3): "Only the developer's own end-of-run steps may still spend: `after_run` middleware, a configured auto-handoff, and a session rule…"
    - spec.md:984 records that r2 R-5 fixed this same overclaim in G-3 ("'No component spends again on a run the cap stopped' contradicts INV-23").
    - `scratchpad/r3-s4/conformance/probe_after_run.py` built a capped agent ($0.50, one 1M-input-token reply) with an `after_run` probe middleware. It printed `stop_reason=max_spend output='Agent runtime stopped after reaching max_spend_usd.' hooks_after_stop=['after_run']`.
    - `_finish_result` (`runtime.py:956-958`) runs `after_run` on every stop.
  Failure: a developer configures an auto-handoff or a spending `after_run` middleware on a capped agent. The run stops on the cap. The README says nothing runs afterwards, yet the handoff or middleware runs and spends. That spend shows in `get_usage()` and not in `metadata["usage_rollup"]` (EC-36).
  Smallest fix: replace the sentence with "After a cap stop no SDK step continues the stopped work: no retry, reflection, review, grading, verifier, or queued prompt, and a `MultiAgent` worker's task is blocked. Only your own `after_run` middleware and a configured auto-handoff still run." The section grows by about one line.
  Spec IDs: INV-23, EC-36, G-3, AC-26, row 13

R-C2 [Minor] [docs/§9.2] vidbyte/agents/README.md:416 — the README's version of the §9.2 per-runtime table leaves out the last row, the SDK-built sub-runtimes that run with no cap
  Evidence: README.md:416-417 reads "`Agent`, `CodingAgent`, `JevAgent`, and `InfiniteMemoryAgent` enforce it, as does every fork, clone, helper, or subagent built from the same settings, against its own spend."
    - No sentence in README.md:386-424 covers spec.md:607: "Jev fixed-prompt agents, critic and judge reviewer sub-runtimes | built by the SDK with their own loop limits and no cap."
    - Row 13 (spec.md:798) requires "the per-runtime table of §9.2 in prose". AC-26 (spec.md:308) requires "the per-runtime answer of §9.2".
    - In code, the reviewer configs carry no cap: `independent_critic.py:126-128` is `AgentRuntimeConfig(max_iterations=…, max_tokens=…)`, and `prosecutor_defender_judge.py:242` is `AgentRuntimeConfig(max_iterations=…, max_tokens=…, max_tool_calls=…)`. `git grep -n max_spend daad59fb` over both files gives no hits in those constructors, which matches D-18 as intended.
  Failure: a developer caps an agent that uses `independent_critic` at $0.50 and reads "every … helper, or subagent … enforce[s] it". The producer finishes at $0.49, and the uncapped reviewer then spends $0.30. The reply returns `final_response` with `cost_usd` of $0.79 (EC-22), which the README never discloses.
  Smallest fix: after README.md:417, add one sentence: "SDK-built reviewer runs (the independent critic's and prosecutor-defender-judge's reviewers) and JevAgent's fixed-prompt agents carry no cap of their own. Their spend counts at the parent's next check, so one review can carry a reply past the cap."
  Spec IDs: AC-26, row 13, §9.2 (spec.md:607), EC-22, D-18

R-C3 [Minor] [scope-adding] [coverage/INV-17] vidbyte/agents/runtime.py:1886 — no pack test pins INV-17's "No cap code computes a rollup" on an uncapped run
  Evidence: mutant M39 moves the `self.usage_tracker.rollup()` call above the `if self.config.max_spend_usd is None: return None` check at runtime.py:1886-1888, so every check point computes a rollup when the agent is uncapped.
    - `py -3.11 mutate.py <mut> M39` gives `M39 NFR-1 rollup computed when uncapped: SURVIVED | 174 passed in 1.64s`.
    - M38 (the early return rewritten as a conditional expression) also survives, but it is an equivalent mutant.
    - test-plan.md:69 hands NFR-1 to S4 ("S4 can mutate the early return") because a wall-clock test would be flaky. A call-count test avoids that objection.
    - Behavior at HEAD is correct: `probe_default_path.py` gives the same `rollup` and `resolve` counts on base and HEAD (2/3, 2/1, 2/1, 2/1, 7/3) and `spend_cap=0`.
  Failure: a later refactor that hoists the rollup goes green and adds an O(records) rollup to every check point of every uncapped run in the SDK. That breaks NFR-1 and INV-17 with no test going red.
  Smallest fix: S2 or S5 add one deterministic test. It wraps `UsageTracker.rollup` and `ModelPricingRegistry.resolve` with counters, runs a scripted tool, tool, isDone reply with `AgentLoopSettings()` (cap `None`), and asserts both counts equal the counts of the same run with `AgentSpendCap` patched out. It reuses the scenario in `probe_default_path.py`. No source change is needed.
  Spec IDs: INV-17, NFR-1

R-C4 [Minor] [deviation record] docs/spec/loop-spend-cap/spec.md:997 — the recorded README length is 38 lines; the section is 39 lines including its heading
  Evidence: spec.md:997 and reports/S3-implementer.md:145 both say "38 lines including its heading (37 of body)".
    - `git show daad59fb:vidbyte/agents/README.md | sed -n '386,425p'` shows `## Spend Cap` at line 386 and its last text line at 424 ("stops with `middleware_abort`, the cap reads the priced ledger and fails closed.").
    - Line 425 is the blank line before `## Key Modules` at 426.
    - That is 39 lines with the heading and 38 of body. The awk range including the trailing blank prints `40`.
  Failure: S5 judges the deviation against "at most about 36" using a number that is one line short. R-C1's fix adds about one more line.
  Smallest fix: change "38 … (37 of body)" to "39 … (38 of body)" in spec.md:997 and reports/S3-implementer.md:145, and re-count after R-C1 and R-C2.
  Spec IDs: §17 deviation, row 13

VERIFIED CLAIMS:
- §4 snippet, AC-1: held.
  - The snippet extracted from spec.md is byte-identical to the test constant (True).
  - cap (1M input tokens) printed "stopped at $0.7500: reached the $0.50 cap" with max_spend.
  - blind printed "stopped: spend could not be fully measured (at least $0.0000)" with max_spend.
  - finished printed "finished; spent $0.0008".
  - 666,666 tokens finished at $0.5000. 666,667 tokens stopped with max_spend.
  - The wire was called once per case.
- FR-1 (`AgentLoopSettings.__init__` is keyword-only, loop.py:52-54): held.
- FR-5 and the enum order (`MAX_SPEND` after `TIMEOUT`): held.
- INV-2 (`cost_measured` is a derived property, empty ledger counts as measured; M36/M37 killed): held.
- INV-4 order, reached before blind (M43 killed): held.
- INV-13 and FR-7, construction refusals:
  - non-linear runtime ×4: held.
  - non-text runner: held. `image`, `embedding`, and typesafe/jev-1.13 are refused as `decision`.
  - unpriced primary and unpriced fallback in chain order: held.
  - OpenRouter exempt: held.
  - Jev specialist without a cap, or with a greater cap: held.
  - Codex tuple: held.
  - A provider-less `gpt-5.4-mini` is refused as `?:gpt-5.4-mini`. It cannot run uncapped either (`AgentExecutionError`), which matches the spec.
  - No raw `ValueError` path was found.
- INV-15 copy paths: held. These carry the cap: `to_runtime_config`, `__repr__`, `_export_loop_settings`, `AgentForker`, the fork tool's guardrails, `_LOOP_FIELDS`, and the YAML loader. A fork-tool override keeps 1.0, and the 3 fork-tool override refusals are exact.
- INV-23 sites: held, every mutant killed.
  - reflexion
  - critic
  - PDJ
  - grader scan and trial
  - transfer BLOCKED with `retryable=False`
  - `_structured_phase` raise
  - InfinitePair FAILED
  - the drain `last_stop` check
- Router `max_spend` maps to `RESOURCE_EXHAUSTED`; `efficiency._BUDGET_STOP_REASONS` has it: held.
- §5 diagram: held in substance, with two differences that have no behavior effect.
  - The diagram puts `to_runtime_config()` before `BaseAgent.__init__`. In code, `__init__` runs both refusals on `agent_loop_settings` first (base.py:253-257) and then calls `to_runtime_config()` (base.py:258). Both still happen at construction, before any spend.
  - CP2 sits after `after_model_response` middleware, which the diagram does not show.
- §8.4 / NFR-5 budget: held. numstat gives runtime.py +37/-2 (≤40) and base.py +20/-3 (≤25). `spend_cap.py` is the only new non-test file. There is no baseline change, and no noqa or type-ignore was added.
- §14 "Never" / do-not-touch (AST comparison of 15 functions, the `BaseAgent.__init__` signature, and 12 files): held, all unchanged. `CostBudgetMiddleware` is unchanged.
- AC-24: held. The contract is current with 733 exports. The diff over the contract, `failure.py` and both `__init__.py` files is empty. `FailureCode` has 206 members on both sides.
- AC-26 docs rows 13(b), 14(a/b/c), 15, 16, 17, 27(a/b/c/d) and output-contracts: held. Row 16 is a byte-exact append with no "(#". The section precedes Key Modules. The README is 32,671 characters (A009 ≤ 40,000). Exceptions: AC-26's per-runtime answer is partial (R-C2), and one sentence overclaims (R-C1).
- AC-26 (c554521e touches exactly the 7 docs files): held.
- NFR-1: held at HEAD by count, but not pinned by a test (R-C3).
- NFR-2: held. One capped check over 10,000 records takes 2.80 ms against a 10 ms target.
- NFR-6 (no version literal change): held.
- NFR-7 (no key-shaped literals in the diff): held.
- The test tree is unchanged since S2 (`git diff b5a9e689 daad59fb -- tests` is empty): held.
- The S3 check-point lines, "174 passed", NFR-5 numbers, "no files outside §12.3", and "733 exports": held.
- S3's "38 lines including its heading": did not hold, it is 39 (R-C4).
- The inherited red `test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (:270-278) comes from row 8 editing `fork.py`. It is not a finding.

COMMANDS RUN:
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/test_codex_output_contracts.py` gives `174 passed in 1.45s`.
- The area suite plus pins (agents, harness_threads, codex_host, output connectors, test_jev_agent) gives `1 failed, 2982 passed, 4 skipped in 212.27s`. The 1 failure is the inherited red at harness_threads :278.
- `py -3.11 scripts/generate-sdk-public-api.py --check` gives `contracts/sdk-public-api.json is current at 731f094c… (vidbyte-sdk 0.4.0, 733 exports)`.
- `git diff 22993b5f daad59fb -- contracts/sdk-public-api.json vidbyte/lib/enums/failure.py vidbyte/__init__.py vidbyte/agents/__init__.py` is empty.
- `git diff --numstat 22993b5f daad59fb -- vidbyte/agents/runtime.py vidbyte/agents/base.py` gives `37 2` and `20 3`.
- `git diff b5a9e689 daad59fb -- tests` is empty.
- `probe_snippet.py` gives the 5 AC-1 lines above, with the wire called once each.
- `probe_strings.py` gives 18/18 exact.
- `probe_validation.py` gives every invalid input → `ConfigurationError … must be a finite number greater than 0 and at most 1.7976931348623157e+308; got X.`. `10**400` → `OverflowError`. YAML `details` field is `agent.loop`.
- `probe_default_path.py` was run on base (22993b5f) and on HEAD. The transcripts are identical, the counts are `2/3, 2/1, 2/1, 2/1, 7/3`, and HEAD gives `spend_cap=0`.
- `probe_untouched.py` gives every target `unchanged`.
- `probe_docs.py` gives every row check `True`. Its section count is `40` (includes the trailing blank).
- `probe_refusal_edges.py` gives the refusal edges listed under INV-13.
- `probe_after_run.py` gives `stop_reason=max_spend output='Agent runtime stopped after reaching max_spend_usd.' hooks_after_stop=['after_run']`.
- `mutate.py <mut> [ids]` ran 47 single-fault mutants against the pack plus the codex test.
  - 44 were KILLED.
  - M16 (unsorted set) SURVIVED this run but is killed under 5 of 6 hash seeds, and its deterministic twin M40 is KILLED.
  - M38 SURVIVED as an equivalent mutant.
  - M39 SURVIVED (`174 passed in 1.64s`).
  - M47 was KILLED (`1 failed, 116 passed in 1.14s`).
- NFR-2 timing: 2.80 ms per capped check over 10,000 records.
- `git show daad59fb:vidbyte/agents/README.md | sed -n '386,425p'` shows heading 386, last text line 424, blank 425, and `## Key Modules` at 426.
- `git status --short` (before writing this report) printed nothing. Worktree HEAD is 78f947e0.
