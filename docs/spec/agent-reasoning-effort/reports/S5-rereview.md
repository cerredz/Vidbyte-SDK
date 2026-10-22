LENS: conformance
VERDICT: SOUND — all seven repairs match spec r4 rows 9(b), 11, 12(h), 29 and 30 and AC-21 to AC-29 and EC-30 to EC-36, character for character, and none of them causes a regression. What remains is two Minor ledger cells in the spec documents.

Re-review round 1 of at most 2. Head f42bb505 (worktree clean). I reviewed `git diff ce751768 f42bb505` hunk by hunk, with each changed source file read whole, and checked the squash with `git diff origin/main...f42bb505`. The base is 98a5d37b, and I checked out a pristine copy of it at `worktrees/r2e-rereview-pristine` (removed after the review). My probes live in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r2e-s5-rereview/`. Each one uses its own fake `HttpTransport.request` (`probewire.py`) and builds its keys at run time.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-1 is closed on every agent path, and there is no fourth path.** `git grep "create_runner\|with_runner(\|Runner("` over `vidbyte/agents` and `vidbyte/context` finds only the three algorithms (`multi_provider_agentic_grader.py:96,152`, `independent_critic.py:214`, `prosecutor_defender_judge.py:250`). It also finds the fallback (`fallback.py:162,210`), `_runner_for_model` (`base.py:1691`) and `spend_cap.py:97-98`, which builds runners for pricing only and never calls them.
  - The other context-window algorithms (`reflexion`, `trajectory_checkpoints`, `problem_space_search`, `error_correction`) call `ctx.runner`, which is the agent's own runner.
  - Each of the guard's three conditions mirrors its runtime branch exactly: `independent_critic.py:212` (`reviewer_provider is None`) and `prosecutor_defender_judge.py:248` (`provider is None or model is None`).
  - Fork (`AgentForkSettings.algorithm`), `restore(algorithm=...)` and the fork tool all rebuild through `BaseAgent.__init__`, so each of them is refused too (probe: `[fork + grader] REFUSED`, `[restore + grader] REFUSED`).
- **The guard method and its `base.py` line follow §8.5 and row 12(h) to the letter.**
  - The text is one f-string, equal to the §8.5 algorithm row.
  - `details` holds exactly the four keys.
  - `{algorithm}` is always the fixed key. The custom names `my-grader` and `"default"` both give `multi_provider_agentic_grader`.
  - The `base.py` change is one statement directly after `resolve_algorithm` (`base.py:285`), with no comment and no branch. `git diff --numstat 98a5d37b f42bb505 -- vidbyte/agents/base.py` gives `14 2` (NFR-7).
- **R-3: an options effort always ends sent or refused, never dropped.**
  - Sent: the string `"high"` and the member `ReasoningEffort.HIGH` both send `reasoning={'effort': 'high'}`.
  - Kept apart from the keyword: when both are set, the keyword wins. `options={"reasoning_effort": None}` counts as unset.
  - Refused: an overlapping `extra_body` gets the overlap text, `thinking_config` the both-set text, AUTO the mode text, `minimal` the capability text, and `"HIGH"` or `""` the `to_enum` text. Image, audio, embedding and video models get the r4 Runner text and its `details`.
  - Every refusal records 0 requests.
- **There is no regression against base.**
  - With the effort unset, the agent and `Runner(options={"reasoning_effort": None})` requests on all 7 providers are identical at head and at 98a5d37b. That covers the method, URL, headers and body (`diff unset-base.txt unset-head.txt` → IDENTICAL).
  - The unset algorithm agents (grader, critic with a reviewer, a debate stage model) construct at both commits.
  - `_runner_for_model` still passes the effort only when it is set, and `restore` and fork are unchanged since ce751768.
  - Every lint rule count equals base except A002 (608 → 602), and that rule's per-finding diff is 6 removed and 0 added.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [deviations] docs/spec/agent-reasoning-effort/review.md:28 — the R-7 status cell still reads "open — trivial (spec text)", but spec r4 already applied R-7
  Evidence: `review.md:28` reads `| R-7 | ... | open — trivial (spec text) |`. Spec r4 (346f8c3e) records the fix in three places:
  - `spec.md:1267`: `| S4 (review.md) | R-7 | Minor | §6 INV-11, §6.2 AC-18, §12.4, §17 | ... | Accepted |`;
  - INV-11 at `spec.md:175` (`r4 (review R-7): ...`) and AC-18 at `spec.md:209` were reworded;
  - `spec.md:1292-1294` are the §17 entries "Recorded in r4" items 2 to 4.

  The repair's own report says `R-7 (done in r4)` (`reports/S5-repair-1.md:78`), but its commit f42bb505 updated the status cells of R-1 to R-6 and R-9 only.
  Failure: S6 writes the PR body from review.md. It would list R-7 as an open follow-up, although that work already merged into the spec, so the PR body would misstate what is open.
  Smallest fix: set the cell to `done in spec r4 @346f8c3e (INV-11, AC-18, §12.4, §17 items 2-4)`.
  Spec IDs: n/a (pipeline ledger; R-7, INV-11, AC-18).

R-C2 [Minor] [every ID] docs/spec/agent-reasoning-effort/spec.md:212-220 — the Proof cells of AC-21 to AC-29 are blank, although S2b's tests prove each of them
  Evidence:
  - Each of rows AC-21 to AC-29 ends `| P0 | |` (AC-29 ends `| P1 | |`). Every row from AC-1 to AC-20 names its test node, or says "not tested" (AC-19).
  - The tests exist and pass, mapped at `test-plan.md:28,33-38`: `test_an_algorithm_that_builds_its_own_runners_refuses_the_effort`, `test_an_algorithm_on_the_agents_own_runner_sends_the_effort_on_every_call`, `test_an_unset_effort_keeps_every_algorithm_configuration_running_as_before`, `test_an_options_effort_reaches_the_text_config_and_the_wire`, `test_an_options_effort_the_text_config_cannot_send_is_refused_like_the_keyword`, `test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it[*-options]` and `test_the_keyword_effort_wins_over_an_options_effort`.
  - The pack, pins, modality and three algorithm files give `793 passed`.

  Failure: §6.2 is the spec's traceability table. For the nine r4 criteria, which include the Blocker's AC-21 to AC-23, a reader of the spec, or S6 writing the PR's test section, finds no proof and has to fall back on the test plan.
  Smallest fix: copy the test-plan node ids into the nine Proof cells (spec text only, no code).
  Spec IDs: AC-21, AC-22, AC-23, AC-24, AC-25, AC-26, AC-27, AC-28, AC-29.

No Blocker and no Major. I prosecuted each sub-lens and found nothing more:
- **Every ID.** I walked the r4 IDs one at a time; the per-ID results are under VERIFIED CLAIMS. The IDs the repair did not touch rest on S4's conformance evidence (table 52/193/30/1, 24/24 texts) plus my fresh unset and §4 runs.
- **The user's words.** The repair adds nothing the user or the spec did not ask for, and it reverses no §C decision. It refuses an own-runner algorithm and does not forward the effort into it, as Q-11 = No requires. JevAgent has no algorithm field (`git grep algorithm -- vidbyte/agents/jev` is empty), so the C5 contract is unchanged.
- **Budget and boundaries.**
  - The repair adds no new file and no new class. Its one new static method is what §8.4 r4 allows.
  - Every changed path outside the pack and `docs/spec/` is named in the spec. The two exceptions are S2's layout pins (§12.5).
  - The `lint/baseline.json` diff against base is empty, and the tests have not changed since 20b49e0c.
  - The `vidbyte/tools`, `runtime.py` and `lint/` diffs are empty, and `vidbyte/lib/configs` holds only rows 2a and 2b.
- **Deviations.** The repair reported two. It edited only status cells in review.md, which the procedure allows, and it tagged the row 30 commit `[R-1]`, which does no harm. I found no unreported deviation.

VERIFIED CLAIMS: <each claim checked and whether it held>
- **Repair: "pack, pins and modality give 748 passed".** HELD, and it is a superset: the pack, pins, modality and the three algorithm test files give `793 passed in 3.79s`.
- **Repair: "C901 `_config_options_for` 6, `BaseAgent.__init__` 19, `refuse_algorithm_models` 3".** HELD: `ruff --select C901 --config lint.mccabe.max-complexity=0` gives 6, 19 and 3, plus 4 for `refuse_unsupported`.
- **Repair: "base.py numstat 14 2".** HELD. The line sits directly after `resolve_algorithm`, with no comment.
- **Repair: "SDK-LINT PASS, every zero-slack rule equal to base".** HELD, and I widened the check to every rule. A full `lint/run.py` at head and at pristine 98a5d37b differs only in A002 (602 against 608). The A002 per-finding diff (`--format json`, keyed by path, symbol and source line) shows 6 removed, all provider `_config`/`_build_text_config` helpers that moved inside the credit window (that is R-8, which belongs to S6), and 0 added.
- **Repair: "the contract is current at 736".** HELD: `generate-sdk-public-api.py --check` reports `current at 654deee6… (vidbyte-sdk 0.4.0, 736 exports)`.
- **Repair: "9 hand mutants were all killed".** HELD, independently. I re-ran the repair's mutants M2, M3, M5, M6, M7, M8 and M9 in my own forms, on a `git archive f42bb505` copy and never the worktree. With MX1 to MX12 (control `719 passed`), MX1, MX3 to MX12 were all KILLED.
  - Observation, not a finding (the engineering lens owns test quality): MX2, which lets `ReasoningEffort.NONE` through `refuse_algorithm_models`, SURVIVED with `719 passed`. The code at head refuses `none` correctly (`if effort is None: return`), but no test pins AC-21 to AC-23 for the value `none`.
- **Repair: "README sections 1,850 / 2,955, agents README 35,134".** HELD: `len()` in text mode gives 1,851 and 2,956 (each counts the trailing newline), within the limits of 1,950 and 3,500, and 35,134 against A009's 40,000. The other READMEs are jev 18,487, providers 41,232 (its legacy ceiling is 55,000) and lib 4,838.
- **Docs truth (R-1 docs, R-5, R-6).** HELD. Every added sentence is true of the code:
  - The agents README names the three own-runner algorithms.
  - The `fallback.py` header is true at `build_runner` `reasoning_effort=self._reasoning_effort` (`:216`).
  - The `agents.py` and `model_configs.py` headers are true at `_validate_reasoning_effort` (`model_configs.py:220`).
  - The registries README cells are true at grok-4.5 `(LOW, MEDIUM, HIGH)` and grok-4.3 `(NONE, LOW, MEDIUM, HIGH)` (`configs/reasoning_effort.py:145-146`), which matches §9.2 spec.md:587-588 ("docs conflict").
  - The guard header's FUNCTION INVENTORY, WHAT NOT TO DO 2 and 4, and KNOWN EDGE CASES (EC-34) match the code.
- **Row 9(b).** HELD:
  - the comment line comes directly after `options = dict(self.options)` and is 68 columns;
  - the conditional assignment spans two lines;
  - the text block assigns only `api_keys` and `mode`;
  - the refusal reads `options.get("reasoning_effort")`;
  - the `@intent` sentence is present.

  Every new source comment line is at most 72 columns (the widest is 72).
- **§4 snippet (AC-1).** HELD. Run verbatim from spec.md on the seam, it printed `PRINTED EXACTLY SHOWN: True`, and `planner` sent `reasoning={'effort': 'high'}` to `/v1/responses` with model `gpt-5.6-sol`. The jev main-model body is pinned by the passing AC-1 test.
- **§5 against the call path.** It holds with one divergence that does not matter: between `refuse_unsupported` (`base.py:262`) and `refuse_algorithm_models` (`:285`), `__init__` runs other construction checks (presets, the capabilities string check), so a bad `capabilities` value is raised before the algorithm text. Neither is an effort path.
- **review.md status cells.** Five held: R-1 @5da7f7fb (2 files: the guard method and the `base.py` line) and @f45f63ac (`vidbyte/agents/README.md` only); R-3 @a324ac08 (utility.py +4/−2, as the smallest fix says); R-9 @afb9e134 (one line, the r4 text); R-5 @3725feb4 (3 docstrings); R-6 @f9989cb9 (README only). R-2 and R-4 are closed by S2b @20b49e0c and green. One did not hold: R-7 (R-C1).
- **CI on f42bb505.** HELD: `gh run view 39550863801` → `"conclusion":"success","headSha":"f42bb505…","name":"CI"`, and `gh run view 39550865942` → `"success"`, `"Static policy"`.
- **Note: one path outside the contract.** A hand-built `AgentRuntime` with a hand-built `RunnerHandle` whose runner carries an effort, plus an own-runner algorithm, never meets `BaseAgent.__init__`, so no guard runs. `AgentRuntime` is exported from `vidbyte.agents`, not from the root. The §9.2 "Every agent" table does not cover this path, and refusing in the runtime would be a new control, so it is a stated limitation or a `[scope-adding]` follow-up at most, not a finding.

COMMANDS RUN: <each with its final lines>
- `git status --short` → (clean); `git rev-parse HEAD` → `f42bb505b037f539e55a6eff2b8ea61034b5e7eb`
- `git diff ce751768 f42bb505 -- vidbyte/` → 8 files: agents README, base.py +1, fallback.py header, reasoning_effort.py, dataclasses/agents.py header, model_configs.py header, registries README, runners/utility.py
- `git diff --numstat 98a5d37b f42bb505 -- vidbyte/agents/base.py` → `14	2	vidbyte/agents/base.py`
- `git diff 98a5d37b f42bb505 --stat -- lint/baseline.json` → (empty); `git diff --stat 20b49e0c f42bb505 -- tests` → (empty); `git diff --name-only 98a5d37b...f42bb505 -- vidbyte/tools vidbyte/lib/configs vidbyte/agents/runtime.py lint` → `vidbyte/lib/configs/__init__.py`, `vidbyte/lib/configs/reasoning_effort.py`
- `git grep -n "create_runner\|with_runner(\|Runner(\|Runner.from_model\|\.build(" -- vidbyte/agents vidbyte/context` → only the three algorithms, fallback, `_runner_for_model` and spend_cap; `git grep -n "with_runner" -- vidbyte` → 4 call sites (3 algorithms + fallback)
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py tests/test_agent_modality_routing.py tests/test_independent_critic_algorithm.py tests/test_multi_provider_agentic_grader.py tests/test_algorithms_honor_middleware_abort.py` → `793 passed in 3.79s`
- `probe_options.py` (head) → `[options str high] … reasoning={'effort': 'high'}`, `[options enum HIGH] … {'effort': 'high'}`, `[options None] … reasoning=None`, `[keyword LOW + options high] … {'effort': 'low'}`, `[options high + extra_body overlap] REFUSED … extra_body also sets reasoning …`, `[options high + extra_body disjoint] … extra_keys=['input','model','reasoning','store']`, `[options high AUTO] REFUSED … TextModelMode.AUTO …`, `[options high image gpt-image-2] REFUSED: Runner sets reasoning_effort, but model 'gpt-image-2' resolves to runner type 'image', which has no reasoning effort. | details={'provider': 'openai', 'model': 'gpt-image-2', 'runner_type': 'image'} | requests=0` (audio, embedding and video alike), `[options None image gpt-image-2] BUILT ImageModelRunner`
- `probe_algorithms.py` (head) → AC-21 ×4, AC-22 ×2, AC-23 ×3 `REFUSED … its <fixed key> algorithm … | details={'agent': 'planner', 'field': 'reasoning_effort', 'reasoning_effort': 'high', 'algorithm': '<fixed key>'} | requests=0`; AC-24 critic and pdj: `constructed`, each request `reasoning={'effort': 'high'}`; AC-25 `constructed`; EC-31 AUTO / `minimal` / `gpt-4o` → the mode, capability and no-row guard texts; `[fork + grader] REFUSED`, `[restore + grader] REFUSED`
- `probe_unset.py` at head and at pristine 98a5d37b → 17 lines each; `diff unset-base.txt unset-head.txt` → `IDENTICAL`
- `probe_snippet.py <spec.md>` → `PRINTED EXACTLY SHOWN: True "Agent fast sets reasoning_effort, but gemini:gemini-3.5-flash has no documented form for reasoning effort 'xhigh' (it supports minimal, low, medium, high).\n"`; `-> https://api.openai.com/v1/responses model= gpt-5.6-sol reasoning= {'effort': 'high'}`
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py` (head) → `S051 … 259 259 RATCHETED`, `A001 642`, `A006 34`, `A007 255`, `C008 45`, `S008 19`, `S015 13`, `S020 1`, `S060 32`, `S062 889`, `S001 56/59`, `S009 346/350`, `A002 602/703`, `A009 0`, `C016 0` / `SDK-LINT: PASS`; the same at pristine; `diff` of the rule lines → only A002 `608` against `602`
- `lint/run.py --rule A002 --format json` at head and base, compared by (path, symbol, source line) → `added at head: []`, 6 removed
- `py -3.11 -m ruff check vidbyte/lib/runners/utility.py vidbyte/agents/reasoning_effort.py vidbyte/agents/base.py --select C901 --config "lint.mccabe.max-complexity=0"` → `__init__ (19)`, `refuse_unsupported (4)`, `refuse_algorithm_models (3)`, `_config_options_for (6)`
- `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 654deee6d2893e83f67164bd331e0f92c941cd85 (vidbyte-sdk 0.4.0, 736 exports).`
- `mutate.py <git archive f42bb505 copy>` → control `719 passed`; MX1, MX3 to MX12 `KILLED`; MX2 `SURVIVED exit=0 :: 719 passed`
- section and README lengths with `len()` → `agents section 1851 | whole 35134`, `registries section 2956`
- `gh run view 39550863801|39550865942 --repo cerredz/Vidbyte-SDK --json name,conclusion,headSha,status` → both `success` on `f42bb505…`
- `git worktree add --detach …/r2e-rereview-pristine 98a5d37b`, then `git worktree remove …/r2e-rereview-pristine` after the review
