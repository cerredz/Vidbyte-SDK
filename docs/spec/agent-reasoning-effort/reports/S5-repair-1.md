# S5 repair, iteration 1 of 8: agent-reasoning-effort

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-reasoning-effort`, branch `feat/agent-reasoning-effort`, started at HEAD 63a34334 (test snapshot 20b49e0c), spec r4. PR https://github.com/cerredz/Vidbyte-SDK/pull/1193. `origin/main` is still 98a5d37b (fetched during this iteration), so no merge was needed.

## Starting state (reproduced)

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py tests/test_agent_modality_routing.py` at 63a34334:

```
FAILED tests/features/agent_reasoning_effort/test_agent_reasoning_effort_refusals.py::test_an_earlier_guard_reason_outranks_the_algorithm_text
FAILED tests/features/agent_reasoning_effort/test_agent_reasoning_effort_wire.py::test_an_options_effort_reaches_the_text_config_and_the_wire
25 failed, 723 passed in 3.58s
```

The 25 were exactly the briefing's list: the `refuse_algorithm_models` pin, AC-21 ×4, AC-22 ×2, AC-23 ×3, EC-31, the 8 non-text cases, AC-26, AC-27 ×3 and EC-36 ×2.

## Gate matrix (final, at the pushed head)

Every gate below ran in this worktree in this iteration against the code at f45f63ac. The docs commit after it changes only `docs/spec/`.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (pack + pins + modality) | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py tests/test_agent_modality_routing.py` | PASS (was 25 failed, 723 passed) | `748 passed in 3.36s` |
| area suite | pack line plus `tests/features/sdk_managed_text tests/features/sdk_provider_keys tests/features/loop_spend_cap tests/features/jev_cli_root_exports tests/test_gemini_provider_text.py tests/test_compatible_provider_text.py tests/test_deepseek_provider.py tests/test_agent_pricing.py tests/test_jev_agent.py tests/test_independent_critic_algorithm.py tests/test_multi_provider_agentic_grader.py tests/test_algorithms_honor_middleware_abort.py` | PASS | `1213 passed in 9.48s` |
| lint ratchet | `lint/run.py`, run as the first step of the source gate with `PYTHONPATH=$(pwd)` | PASS, 0 REGRESSED; zero-slack rules equal base: S051 259, A001 642, A006 34, A007 255, C008 45, S008 19, S015 13, S020 1, S060 32, S062 889; A002 602 (baseline 703, unchanged, see R-8); A009 0; C016 0 | `S062   no-implicit-string-concatenation          889    889 RATCHETED` / `SDK-LINT: PASS` |
| full source gate | `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` | PASS except the 2 briefed local-only reds | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` / `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `=========== 2 failed, 8385 passed, 18 skipped in 314.52s (0:05:14) ============` |
| package gate | `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| whole-tree I001 | `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, per file, head against a `git archive 98a5d37b` tree | PASS, per-file counts identical | `TOTAL 223 FILES 217` (head) / `TOTAL 223 FILES 217` (base) / `I001 per-file identical` |
| semgrep | `git add -A`, then `PATH="$(cygpath -u .../s3-semgrep-venv)/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Ran 1 rule on 1034 files: 0 findings.` |
| public-API contract | `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 654deee6d2893e83f67164bd331e0f92c941cd85 (vidbyte-sdk 0.4.0, 736 exports).` |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1193` | dispatch-only; not run by S5 | `no checks reported on the 'feat/agent-reasoning-effort' branch` |

The two source-gate failures are the inherited local-only reds the briefing names. Neither is a defect, CI skips both (they need `origin/main`), and both clear on merge. They are not reds at the base commit itself: they compare this branch with its merge-base. Their assertions name nothing new. `:270-278` lists exactly the 2 S3 files (`Left contains 2 more items, first extra item: 'vidbyte/lib/configs/__init__.py'`; the second is `vidbyte/lib/configs/reasoning_effort.py`). `:309` lists exactly the three root names (`'DecisionModelMode'`, `'ReasoningEffort'`, `'DecisionModelConfig'`). S3's run gave `2 failed, 8340 passed`; the 45 extra passing tests are S2b's.

## Per finding

### R-1 (Blocker): fixed @5da7f7fb (code) and @f45f63ac (row 30 README)

- `vidbyte/agents/reasoning_effort.py`: new `@staticmethod refuse_algorithm_models(*, agent_name, runner_config, algorithm) -> None` (row 11). It returns when `runner_config.reasoning_effort is None`. Otherwise it builds a dict from each fixed key to whether that configuration builds its own runners: `multi_provider_agentic_grader is not None`; `independent_critic is not None and independent_critic.reviewer_provider is not None`; any of `prosecutor`, `defender`, `judge` with `provider is not None and model is not None`. It takes the first true key with `next(...)` and raises the exact §8.5 algorithm text as one f-string, with `details={"agent", "field": "reasoning_effort", "reasoning_effort": effort.value, "algorithm": key}`. It never reads `algorithm.name` (EC-33). It has an `@intent algorithm-built-runners-cannot-carry-the-effort` block and narration comments, all at most 72 columns. `ContextWindowAlgorithm` is imported under `TYPE_CHECKING` from `vidbyte.context.window`, between the `vidbyte.agents.fallback` and `vidbyte.lib.dataclasses.agents` imports (I001 order). The A001 header now covers both methods in PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS, WHAT NOT TO DO (never mutate the algorithm; never name it by `ContextWindowAlgorithm.name`) and KNOWN EDGE CASES (at most one algorithm; all-or-nothing pairs; EC-34 not re-checked). `refuse_unsupported` is unchanged.
- `vidbyte/agents/base.py`: one statement on one line, no comment, directly after `self.algorithm = ContextWindow.resolve_algorithm(algorithm)` (now :285): `AgentReasoningEffortGuard.refuse_algorithm_models(agent_name=name, runner_config=self.runner_config, algorithm=self.algorithm)`. `git diff --numstat 98a5d37b -- vidbyte/agents/base.py` gives `14	2`, net **+12**, the NFR-7 limit. Nothing else in base.py changed.
- `vidbyte/agents/README.md` "Reasoning Effort" (row 30(a)): the construction refusals now end "... on an agent that does not name both a provider and a model, and when its context-window algorithm calls models through runners it builds itself (`multi_provider_agentic_grader`, `independent_critic` with a reviewer, or `prosecutor_defender_judge` with a stage model)." Measured with `len(text)` after reading in text mode: section 1,850 characters (from `## Reasoning Effort` up to the next `## ` heading; limit 1,950), whole README 35,134 (A009 limit 40,000).
- Evidence: after 5da7f7fb the pack went from 25 to 14 failures; the 11 R-1 tests (pin, AC-21 ×4, AC-22 ×2, AC-23 ×3, EC-31) passed unedited. AC-24, AC-25, EC-30 and EC-32 stayed green. `tests/test_independent_critic_algorithm.py tests/test_multi_provider_agentic_grader.py tests/test_algorithms_honor_middleware_abort.py`: `45 passed in 1.29s`.
- C901 (`ruff --select C901` at max-complexity 0): `refuse_algorithm_models` 3; `BaseAgent.__init__` 19 at base 98a5d37b and 19 at head (no branch added).

### R-3 (Major): fixed @a324ac08

`Runner._config_options_for` (`vidbyte/lib/runners/utility.py`), exactly as row 9(b):
- directly after `options = dict(self.options)`: the comment `# A set keyword wins; an unset one keeps the options effort.` (72 columns with its indent), then `if self.reasoning_effort is not None:` and `options["reasoning_effort"] = self.reasoning_effort` on two lines;
- the `if runner_type == RUNNER_TYPE_TEXT:` block assigns `api_keys` and `mode` only;
- the non-text refusal reads `if options.get("reasoning_effort") is not None and runner_type != RUNNER_TYPE_TEXT:`.
- The `@intent non-text-configs-take-their-providers-key` comment already carried row 9(b)'s sentence from S3 ("An effort exists only for text configs, so another type refuses it rather than letting the field filter drop it."), so it was left as is.
- `_runner_for_model` still passes the effort only when set (the `tests/test_agent_modality_routing.py:74` pin); untouched.
- Evidence: after a324ac08 the pack went from 14 to 8 failures. AC-26, AC-27 ×3 and EC-36 ×2 passed; the 4 options non-text cases now raised, failing only on the r3 text (`- solves to runner type 'audio', which has no reasoning effort.` / `+ solves to a audio runner, ...`), which R-9 owns. AC-29 and EC-35 stayed green; `tests/test_agent_modality_routing.py` stayed green.
- C901 of `_config_options_for`: 4 at base 98a5d37b, 5 at 63a34334, 6 at head (limit 10).

### R-9 (Minor): fixed @afb9e134

The `Runner` refusal is now the r4 §8.5 text, one f-string: `Runner sets reasoning_effort, but model '{self.model_name}' resolves to runner type '{runner_type}', which has no reasoning effort.` The `details` are unchanged. `git grep "has no reasoning effort"` outside `docs/` and `tests/` finds only this line, so no README quoted the old text. After afb9e134 the pack is `748 passed in 3.36s`.

### R-2 and R-4: test-only, closed by S2b @20b49e0c; confirmed green, no source change

`pytest -rA tests/features/agent_reasoning_effort -k "restored_chain or non_text_runner"` at head: `test_a_restored_chain_sends_the_kept_effort_in_each_hops_own_form` and all 8 `test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it[{image,audio,embedding,video}-{keyword,options}]` PASSED.

### R-5 (trivial): fixed @3725feb4

Docstring-only edits, following the shape #1027 (72a4ade1) used for `model_mode` on the same lines:
- `vidbyte/agents/fallback.py:10-12`: "every backup runner gets the agent's matched ProviderKeys, text-model mode and reasoning effort."
- `vidbyte/lib/dataclasses/agents.py:9`: "AgentRunnerConfig: Primitive backend configuration, with the matched keys, the text-model mode and the reasoning effort."
- `vidbyte/lib/dataclasses/model_configs.py:6,8`: Purpose adds "and reasoning-effort checks to ReasoningEffortRegistry"; the TextModelConfig line adds "and checks its reasoning effort against its mode and model at construction."
`lint/run.py --rule A001`: `A001 RATCHETED: 642 known finding(s)`, `SDK-LINT: PASS`.

### R-6 (trivial): fixed @f9989cb9

`vidbyte/lib/registries/README.md` "Reasoning Effort Sources": "a value the docs contradict (Muse `xhigh`; grok-4.5 and grok-4.3 `xhigh`)". This matches `vidbyte/lib/configs/reasoning_effort.py:145-146` (grok-4.5 `(LOW, MEDIUM, HIGH)`, grok-4.3 `(NONE, LOW, MEDIUM, HIGH)`) and §9.2 (spec.md:587-588, docs conflict XA-7 against XA-11 and XA-13). Section 2,955 characters (2,924 before by the same count; limit 3,500).

### Not mine (unchanged)

R-7 (done in r4), R-8 and R-10 (S6). No `--update-baseline` was run; `lint/baseline.json` is unchanged.

## Independent checks beyond the pack

**Mutation check of the new code** (my own script, each mutant applied to the worktree, the pack run with `-x`, the file restored with `git checkout`): all 9 killed.

```
M1 critic reviewer ignored: KILLED exit=1 :: 1 failed, 263 passed in 2.42s
M2 debate stages ignored: KILLED exit=1 :: 1 failed, 265 passed in 2.65s
M3 grader ignored: KILLED exit=1 :: 1 failed, 259 passed in 2.56s
M4 critic refused even without reviewer: KILLED exit=1 :: 1 failed, 690 passed in 3.30s
M5 user-chosen name in text: KILLED exit=1 :: 1 failed, 261 passed in 2.62s
M6 guard call removed: KILLED exit=1 :: 1 failed, 259 passed in 2.54s
M7 non-text refusal reads keyword only: KILLED exit=1 :: 1 failed, 247 passed in 2.56s
M8 keyword overwrites options unconditionally: KILLED exit=1 :: 1 failed, 247 passed in 2.44s
M9 options wins over keyword: KILLED exit=1 :: 1 failed, 688 passed in 3.19s
```

**Per-finding lint comparison in the touched files** (tree at 63a34334 against the head; findings compared by content with line numbers removed), rules A001, A002, A003, A006, A007, A009, S008, S062, C008, S060, S051, S015, S020: no added finding except one S008 entry whose message changed. `BaseAgent.__init__` PLR0915 reads "Too many statements (94 > 50)" instead of "(93 > 50)", because of the one statement row 12(h) prescribes. It is the same baselined finding: S008 stays 19 = 19.

**Scope.** `git diff --name-only 63a34334 HEAD` (code commits) touches only §12.3 rows 4, 9, 10, 11, 12, 13, 29 and 30. `git diff --name-only $(git merge-base origin/main HEAD) -- vidbyte/tools vidbyte/lib/configs` still names only `vidbyte/lib/configs/__init__.py` and `vidbyte/lib/configs/reasoning_effort.py` (rows 2a and 2b), so the inherited `:270-278` red is not widened. No file under `tests/` changed (`git diff --stat 20b49e0c HEAD -- tests` is empty).

## Test changes proposed

None. No test contradicts spec r4.

## Findings I believe are wrong

None.

## Decisions and deviations

- **review.md edits.** The procedure says to set each finding's status to `fixed @<sha>`, and the final message lists review.md, while the briefing's §7 says only verify-log.md and this report may be edited. I followed the procedure and changed only the Status cells of R-1 to R-6 and R-9; no other text in review.md changed.
- **Row 30 commit tag.** The README change belongs to R-1's spec amendment (row 30(a) r4), so its commit is tagged `[R-1]`.
- **The R-5 commit** was first committed as `docs(agents)` and reworded, before any push, to `fix(agents)` to match the commit convention.

## Open

No confirmed finding of this iteration's list is open: R-1, R-3, R-5, R-6 and R-9 are fixed, and R-2 and R-4 are closed by S2b and confirmed green. R-7 is done in r4. R-8 and R-10 belong to S6 and were not touched.

The remote checks are the only gate not run. They are dispatch-only and do not attach to the PR, the briefing forbids S5 from dispatching them, and the orchestrator dispatches them before merge. If a dispatched run fails, try these first. Each is a local pass that could differ on the Linux runner. (1) `tests/features/agent_reasoning_effort` under Linux path handling; nothing in the new code touches paths. (2) Semgrep's newer version on the runner; the local scan is 0 findings at 1034 files. (3) The harness_threads clauses, which skip on CI without `origin/main`.
