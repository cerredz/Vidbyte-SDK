# S3 implementer report: agent-reasoning-effort

Spec: `docs/spec/agent-reasoning-effort/spec.md` revision 3 · Base: `98a5d37b` (origin/main, unchanged) · Tests: `1fa23b65` · Code HEAD: `182088a3` · Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/1193 · Date: 2026-10-20

## 1. Commits

`git log origin/main..HEAD --oneline`, S3's commits only (the rows beneath `1fa23b65` are S0 to S2; this report's own commit follows `182088a3`):

```
182088a3 style(agents): wrap four new comments at 72 columns [W-2, W-3; NFR-3]
8f304fca docs(spec): record implementation proof for agent-reasoning-effort
fa8b7a37 docs(spec): record draft PR for agent-reasoning-effort
e4e7bee4 fix(agents): pass the reasoning effort to the primary runner only when it is set [W-6; FR-6, AC-8]
745f861d docs(registries): label the reasoning-effort sources rows by vendor name [W-10; FR-12]
e2de2026 docs(agents): document the reasoning effort, its sources and the release record [W-10; FR-12, NFR-4, AC-19]
41a464ca chore(contracts): regenerate the public API contract for the three new root names [W-9; FR-10, AC-13]
654deee6 feat(agents): export ReasoningEffort, DecisionModelConfig and DecisionModelMode from the root package [W-9; FR-10, AC-13]
c15aef71 feat(agents): carry the reasoning effort to forks, side agents and every Jev child [W-7, W-8; FR-8, FR-9, AC-9, AC-12, AC-14]
8dd96a39 feat(agents): take reasoning_effort on BaseAgent and refuse it across the fallback chain at construction [W-6; FR-6, FR-7, FR-11, AC-1, AC-4, AC-5, AC-6, AC-10, AC-11]
335150be feat(agents): send the reasoning effort in each provider's wire form and refuse it on non-text runners [W-4, W-5; FR-4, FR-5, AC-14, AC-15, AC-16]
31a583f6 feat(agents): add ReasoningEffort, its capability table and registry, and TextModelConfig validation [W-1, W-2, W-3; FR-1, FR-2, FR-3, NFR-4, AC-3, AC-10, AC-18]
1fa23b65 docs(spec): agent-reasoning-effort pipeline state after S2
```

## 2. What was built, in data-flow order

1. A developer passes `reasoning_effort` (a `ReasoningEffort`, or its exact value string) to `BaseAgent` / `Agent`. — `vidbyte/agents/base.py`
2. `AgentRunnerConfig.__post_init__` stores it as the enum through `RecordFieldConverter.to_enum`. — `vidbyte/lib/dataclasses/agents.py`
3. A fallback chain is built with it: `AgentFallbackSettings.to_fallback` hands it to `AgentFallback`, and `from_spec` passes the runner config's value. — `vidbyte/agents/settings/fallback.py`, `vidbyte/agents/fallback.py`
4. Right after the spend-cap refusal, `AgentReasoningEffortGuard.refuse_unsupported` checks every hop (`fallback.models` when there is a chain, else the primary), each normalized with `Runner._normalize_provider_and_model` the way its runner will read it. It raises the identity text when a hop lacks a provider or model, else joins each hop's unique reason in chain order. — `vidbyte/agents/reasoning_effort.py`
5. Each reason comes from `ReasoningEffortRegistry.refusal`: the gateway-mode reason first, then the table. `supported` resolves the id with `ProviderModelRegistry.normalize_model` (own prefix dropped, aliases applied) and lower case, and reads `REASONING_EFFORT_SUPPORT`. — `vidbyte/lib/registries/reasoning_effort.py`
6. The table holds the §9.2 "sent" cells per exact id, and `REASONING_EFFORT_FORMS` holds each provider's wire fragment per value. — `vidbyte/lib/configs/reasoning_effort.py`
7. At call time `_runner_for_model` passes the effort to `Runner.from_model` only when it is set; each fallback hop's `build_runner` passes its own copy. — `vidbyte/agents/base.py`, `vidbyte/agents/fallback.py`
8. `Runner` stores it, sets `options["reasoning_effort"]` for a text runner, and raises the §8.5 Runner text for any other runner type. — `vidbyte/lib/runners/utility.py`
9. `TextModelConfig` validates it last in `__post_init__`: enum conversion, the mode and capability refusal, then `thinking_config` beside it, then an `extra_body` key the fragment uses. — `vidbyte/lib/dataclasses/model_configs.py`
10. Each DIRECT payload builder calls `ReasoningEffortRegistry.attach` immediately before `_attach_extra_body`; `attach` returns at once for `None`, otherwise deep-copies the fragment and deep-merges it. — `vidbyte/providers/openai.py`, `anthropic.py`, `gemini.py`, `compatible.py`
11. Copy paths: a fork, `ContinualTraceAgent` and `HandoffAgent` pass `runner_config.reasoning_effort`; `_export_runtime_config` writes `runtime_config["reasoning_effort"]` as a plain string only when set, and `restore` reads it back. — `vidbyte/agents/fork.py`, `continual_trace.py`, `handoff.py`, `base.py`
12. Jev: `JevAgentSettings.reasoning_effort` is checked against Jev's own provider, model and mode, then passed to the main agent, the fresh-continuation partial and the eight children (9 sites). The run-brief writer, the specialists and the decision calls do not get it. — `vidbyte/agents/jev/settings.py`, `agent.py` and rows 20 to 26
13. The root package exports `ReasoningEffort`, `DecisionModelConfig` and `DecisionModelMode`, and the regenerated contract lists 736 exports. — `vidbyte/__init__.py`, `contracts/sdk-public-api.json`

## 3. §12.3 rows: 39 of 39 done

| Row | File | Commit(s) | Done |
|---|---|---|---|
| 1 | `vidbyte/lib/enums/text_model.py` | 31a583f6 | [x] `ReasoningEffort(StrEnum)`, six members; header and `__all__` |
| 2 | `vidbyte/lib/enums/__init__.py` | 31a583f6 | [x] import and export |
| 2a | `vidbyte/lib/configs/reasoning_effort.py` (new, 170 lines) | 31a583f6 | [x] A001 header; `REASONING_EFFORT_AS_OF`, `GEMINI_THINKING_BUDGET_OFF`, `REASONING_EFFORT_FORMS`, `REASONING_EFFORT_SUPPORT` with one vendor URL per provider |
| 2b | `vidbyte/lib/configs/__init__.py` | 31a583f6 | [x] the four names imported and exported |
| 3 | `vidbyte/lib/registries/reasoning_effort.py` (new, 115 lines) | 31a583f6, 182088a3 | [x] `supported`, `refusal`, `attach`, `_mode_refusal`, `_capability_refusal`, `_merge` |
| 3a | `vidbyte/lib/registries/__init__.py` | 31a583f6 | [x] one import line; four names in `__all__`; the base I001 finding neither fixed nor worsened |
| 4 | `vidbyte/lib/dataclasses/model_configs.py` | 31a583f6, 182088a3 | [x] field appended last; `_validate_reasoning_effort` last in `__post_init__` |
| 5 | `vidbyte/providers/openai.py` | 335150be | [x] attach before `_attach_extra_body` in `_create_text_payload` |
| 6 | `vidbyte/providers/anthropic.py` | 335150be | [x] same, `_create_payload` |
| 7 | `vidbyte/providers/gemini.py` | 335150be | [x] same |
| 8 | `vidbyte/providers/compatible.py` | 335150be | [x] same (DeepSeek, xAI, GLM, Meta) |
| 9 | `vidbyte/lib/runners/utility.py` | 335150be | [x] keyword, text-runner option, non-text refusal |
| 10 | `vidbyte/lib/dataclasses/agents.py` | 8dd96a39 | [x] `AgentRunnerConfig.reasoning_effort` appended last, enum-converted |
| 11 | `vidbyte/agents/reasoning_effort.py` (new, 61 lines) | 8dd96a39 | [x] `AgentReasoningEffortGuard.refuse_unsupported` |
| 12 | `vidbyte/agents/base.py` | 8dd96a39, e4e7bee4 | [x] parameter, config, guard call, restore, export; `_runner_for_model` (deviation 1) |
| 13 | `vidbyte/agents/fallback.py` | 8dd96a39 | [x] `__init__`, `from_spec`, `build_runner` |
| 14 | `vidbyte/agents/settings/fallback.py` | 8dd96a39 | [x] `to_fallback` keyword |
| 15 | `vidbyte/agents/fork.py` | c15aef71 | [x] |
| 16 | `vidbyte/agents/continual_trace.py` | c15aef71 | [x] |
| 17 | `vidbyte/agents/handoff.py` | c15aef71 | [x] |
| 18 | `vidbyte/agents/jev/settings.py` | c15aef71 | [x] field appended last; `_validate_reasoning_effort` after `_validate_timeout` |
| 19 | `vidbyte/agents/jev/agent.py` | c15aef71 | [x] main agent and fresh partial (2 sites) |
| 20 | `vidbyte/agents/jev/bulk_work.py` | c15aef71 | [x] |
| 21 | `vidbyte/agents/jev/compute/clone.py` | c15aef71 | [x] |
| 22 | `vidbyte/agents/jev/compute/swarm.py` | c15aef71 | [x] |
| 23 | `vidbyte/agents/jev/done/handoff.py` | c15aef71 | [x] |
| 24 | `vidbyte/agents/jev/done/reviewer.py` | c15aef71 | [x] |
| 25 | `vidbyte/agents/jev/done/run_state.py` | c15aef71 | [x] |
| 26 | `vidbyte/agents/jev/gate/clarification.py` | c15aef71 | [x] |
| 27 | `vidbyte/__init__.py` | 654deee6 | [x] header bullet, eager imports, `__all__` |
| 28 | `contracts/sdk-public-api.json` | 41a464ca | [x] generated, never hand-edited; `--check` lists 736 |
| 29 | `vidbyte/lib/registries/README.md` | e2de2026, 745f861d | [x] "## Reasoning Effort Sources" (deviation 2) |
| 29a | `REPO_MAP.md` | e2de2026 | [x] configs sentence, verbatim |
| 29b | `vidbyte/lib/README.md` | e2de2026 | [x] registries bullet names `ReasoningEffortRegistry` |
| 30 | `vidbyte/agents/README.md` | e2de2026 | [x] "## Reasoning Effort" and the Key Modules bullet |
| 31 | `vidbyte/agents/jev/README.md` | e2de2026 | [x] the sentence, verbatim |
| 32 | `vidbyte/providers/README.md` | e2de2026 | [x] Contract Invariant 6 |
| 33 | `skills/usage/create_agent.md` | e2de2026 | [x] signature line and Model clause (deviation 3) |
| 34 | `docs/design/release-0-4-0.md` | e2de2026 | [x] line 17 append and line 19 tally, exact; no PR number (deviation 6) |

Row 34 was checked by script against the spec row: `line17 == before+space+append: True`, `line19 contains after: True | before gone: True`, `no '#N' or '(#' placeholder added: True`.

**§12.4 standards (all ticked).** Enum placement and typing; A001 headers on the three new modules (lint A001 at its count); `@intent` on every function A002 names (A002 608 → 602); every added comment at most 72 columns (`... | awk 'length($0) > 72' | wc -l` → `0`, after 182088a3 rewrapped four 73- and 74-column lines); narration in the main functions; flat helper calls, with `_merge` the only self-call; import direction (configs imports enums and typing only; the guard imports `AgentFallback` and `AgentRunnerConfig` under `TYPE_CHECKING`); I001 identical to base; S001 at 56; `to_enum` for every new field and no new primitive validator (C008 at 45); `GEMINI_THINKING_BUDGET_OFF` is the only numeric literal; no new S008, and no branch in `BaseAgent.__init__`, `TextModelConfig.__post_init__` or `JevAgentSettings.__post_init__`; S009 and S060 at their counts; root names eager and in `__all__`, contract regenerated; one root-header bullet; README sizes 15,187 / 34,930 / 18,487 / 41,232 / 4,838 characters, all within A009; no `FailureCode` member and no `EMITTED_KEYS` change (`git diff 1fa23b65 HEAD | grep -E '^[+-]' | grep -cE 'EMITTED_KEYS|class FailureCode|...'` → `0`); no key-shaped literal in an added line (→ `0`); tests, `lint/baseline.json`, `vidbyte/tools/` and `vidbyte/agents/runtime.py` unchanged (`git diff --stat 1fa23b65 HEAD -- tests lint/baseline.json vidbyte/tools vidbyte/agents/runtime.py` prints nothing); the table equals §9.2 (the pack's INV-20 sweep); texts match §8.5 (mutants M26 to M32 below).

**§12.5 actions (all done).** The contract regeneration, the five README and skill-doc additions, and the release record (rows 28 to 34). No `llms.txt`, `.env.example`, changelog or baseline change. The three layout pins were S2's and were not touched.

## 4. Deviations, with reasons

Also listed under spec §17 "Implementation deviations".

1. **Row 12(d), `_runner_for_model`.** The row passes `reasoning_effort=self.runner_config.reasoning_effort` always. I pass it only when it is set, the same way the function already omits an unset timeout. `tests/test_agent_modality_routing.py:74` pins the exact `Runner.from_model` keywords of an agent without the effort, so the unconditional form fails that existing test (mutant M35 below reproduces it: `FAILED tests/test_agent_modality_routing.py::AgentModalityRoutingTests::test_model_identity_routes_to_image_runner`). The request is unchanged, because `Runner` defaults the effort to `None`.
2. **Row 29, README labels.** The "Reasoning Effort Sources" table labels providers by vendor name (OpenAI, Anthropic, Gemini, DeepSeek, xAI, GLM, Meta), not by lowercase enum value. `tests/features/sdk_provider_keys/test_provider_keys_contract.py:341` reads every README line that starts `| meta |` as a row of its own table, so a lowercase `| meta |` row made that test see two tables.
3. **Row 33, skill doc.** The new signature line carries a trailing comment like its neighbours, and the Model bullet's parameter list also names `reasoning_effort`.
4. **Row 3, spec silent.** `attach`'s backstop `ConfigurationError` carries `details` `field`, `provider`, `model` and `reasoning_effort`. The spec gives only its text. Construction refuses first, so no carrier reaches it.
5. **Row 3, spec silent on how.** `supported` and `refusal` resolve the provider with the private `ProviderModelRegistry._require_provider`, the same helper `normalize_model` calls (`vidbyte/lib/registries/models.py:252`), so an unknown provider fails with the registry's own "Unrecognized provider" text.
6. **Row 34(c) and §14.** The spec has the S3 author insert the PR number; the S3 briefing assigns that to S6 and forbids a `#<n>` placeholder, so the release record has no PR number yet.

Minor, not behavior: the contract commit is typed `chore(contracts)`; there are two follow-up commits (745f861d docs, e4e7bee4 fix) and one comment-wrap commit (182088a3).

## 5. Files outside §12.3

None. The comparison script over `git diff --name-only 1fa23b65 HEAD` printed:

```
rows in 12.3: 38
changed files: 40
changed but not a 12.3 row: ['contracts/sdk-public-api.json', 'docs/spec/agent-reasoning-effort/spec.md']
12.3 rows not changed: []
```

The script's regex missed row 28, whose kind is "MODIFY (generated)", so it counted 38 rows instead of 39. `contracts/sdk-public-api.json` is row 28. `spec.md` holds only the `pr:`, `status:`, the AC-19 Proof cell and §17, which the template assigns to S3. This report is the template's own output.

## 6. Budget used against allowed (§8.4, NFR-7)

| Item | Used | Allowed |
|---|---|---|
| New files | 3 (170, 115 and 61 lines) | 3 |
| New classes or modules | 3 (`ReasoningEffort`, `ReasoningEffortRegistry`, `AgentReasoningEffortGuard`) | 3 |
| New dependencies | 0 | 0 |
| New config keys | 0 | 0 |
| New collections or tables | 0 | 0 |
| Root names | 3 (733 → 736 exports) | 3 |
| New keyword parameters or fields | 7 (`BaseAgent`, `Runner`, `AgentFallback`, `to_fallback`, `TextModelConfig`, `AgentRunnerConfig`, `JevAgentSettings`) | 7 |
| `base.py` net lines | +11 (`git diff --numstat 1fa23b65 HEAD -- vidbyte/agents/base.py` → `13	2`) | +12 |
| `runtime.py` | untouched | untouched |

## 7. Gates (final lines, quoted)

All runs are at code HEAD `182088a3`, from the worktree root, unless a line says otherwise.

**1. The pack plus the three pins.** `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py`, then the pack alone:

```
684 passed in 2.63s
655 passed in 2.67s
```

**2. The touched area.** The pack plus `tests/features/sdk_managed_text tests/features/sdk_provider_keys tests/features/loop_spend_cap tests/features/jev_cli_root_exports tests/test_gemini_provider_text.py tests/test_compatible_provider_text.py tests/test_deepseek_provider.py tests/test_agent_pricing.py tests/test_jev_agent.py`:

```
1075 passed in 7.63s
```

The rest of the suite named in the briefing, plus the modality-routing pin, `tests/test_fork_tool.py tests/multi_agent tests/features/agent_output_connectors tests/features/coding_agent/test_coding_agent_contract.py tests/test_agent_modality_routing.py` (the briefing's `tests/test_coding_agent_contract.py` lives under `tests/features/coding_agent/`):

```
758 passed in 6.64s
```

**3. Lint.** `lint/run.py`, inside the source stage:

```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Every row of the lint summary table equals the `1fa23b65` run except A002, which improved: `rows that differ from 1fa23b65: [('A002', (608, 703, 'IMPROVED'), (602, 703, 'IMPROVED'))]`. `lint/baseline.json` is unchanged.

I001 over the whole tree, `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, compared per file with the base snapshot:

```
Found 223 errors.
base files: 217 final files: 217 identical: True
only base: [] only final: []
```

Semgrep, after `git add -A`: `Ran 1 rule on 1034 files: 0 findings.`

Contract: `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 654deee6d2893e83f67164bd331e0f92c941cd85 (vidbyte-sdk 0.4.0, 736 exports).`

**4. The full local gate, source stage.** `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`. Lint, compileall and the three check scripts pass; pytest runs last:

```
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
...
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
=========== 2 failed, 8340 passed, 18 skipped in 262.30s (0:04:22) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-agent-reasoning-effort).
```

The two failures are the inherited local reds that spec §13 and the briefing name. CI skips both and both clear on merge. Their assertions show the expected cause and nothing else:

```
tests\features\harness_threads\test_harness_threads_surface.py:278
E         Left contains 2 more items, first extra item: 'vidbyte/lib/configs/__init__.py'
tests\features\harness_threads\test_harness_threads_surface.py:309
E             Extra items in the left set:
E             'DecisionModelConfig'
E             'ReasoningEffort'
E             'DecisionModelMode'
```

Any other failure would be mine; there is none.

**5. The full local gate, package stage.** `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package`:

```
Successfully built vidbyte_sdk-0.4.0.tar.gz and vidbyte_sdk-0.4.0-py3-none-any.whl
...vidbyte_sdk-0.4.0-py3-none-any.whl: PASSED
...vidbyte_sdk-0.4.0.tar.gz: PASSED
No broken requirements found.
Installed vidbyte-sdk 0.4.0 passed smoke checks.
CI passed.
exit=0
```

## 8. Answers to the reviewers' hunt list

I ran 44 single-line mutants in a throwaway detached worktree at `8f304fca` (`git worktree add --detach`, removed afterwards; script `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3/mutate.py`). Each mutant edits one line, runs the pack with `pytest -x`, and restores the file. Control first:

```
CONTROL exit=0 655 passed in 3.39s (6s)
```

All 44 were killed; the tree was clean afterwards (`TREE CLEAN AFTER RUN: True`). The first failing test for each is quoted under the hunt item it answers.

**A builder without the attach, or with a shallow merge.** The four call sites, each the line before `_attach_extra_body`:

```
vidbyte/providers/anthropic.py:68:        ReasoningEffortRegistry.attach(payload, provider=config.normalized_provider(), model=config.model, effort=config.reasoning_effort)
vidbyte/providers/compatible.py:70:       (same)
vidbyte/providers/gemini.py:74:           (same)
vidbyte/providers/openai.py:265:          (same)
```

```
M01 KILLED [deep merge]                 ... test_agent_reasoning_effort_copy_paths.py::test_side_agents_built_from_a_source_carry_its_effort[handoff]
M02 KILLED [deep copy]                  ... test_agent_reasoning_effort_registry.py::test_attach_gives_each_payload_a_private_copy_and_never_touches_the_table
M03 KILLED [builder attach openai]      ... test_agent_reasoning_effort_acceptance.py::test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev
M04 KILLED [builder attach anthropic]   ... test_agent_reasoning_effort_acceptance.py::test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev
M05 KILLED [builder attach gemini]      ... test_agent_reasoning_effort_wire.py::test_each_sent_cell_adds_exactly_its_fragment_to_the_vendor_body[gemini:gemini-3.8-flash:low]
M06 KILLED [builder attach compatible]  ... test_agent_reasoning_effort_wire.py::test_each_sent_cell_adds_exactly_its_fragment_to_the_vendor_body[deepseek:deepseek-v4-pro:none]
```

**A fallback hop the guard skips.** The guard reads `fallback.models` (primary first, every backup after) when there is a chain.

```
M07 KILLED [guard: primary only]               ... test_every_chain_entry_is_checked_in_either_order[bad_fallback]
M08 KILLED [guard: skip last hop]              ... test_every_chain_entry_is_checked_in_either_order[bad_fallback]
M09 KILLED [guard: skip first hop]             ... test_every_chain_entry_is_checked_in_either_order[bad_primary]
M10 KILLED [guard call removed]                ... test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev
M11 KILLED [fallback hop runner drops effort]  ... test_agent_reasoning_effort_wire.py::test_a_chain_that_can_take_the_value_sends_each_hops_own_form
M12 KILLED [fallback from_spec drops effort]   ... test_agent_reasoning_effort_wire.py::test_a_chain_that_can_take_the_value_sends_each_hops_own_form
```

**A remapped value that gets sent.** DeepSeek `minimal`/`medium`/`xhigh`, GLM-5.2 `minimal`/`low`/`medium`/`xhigh` and Muse `xhigh` have no cell (`_DEEPSEEK = (_NONE, _LOW, _HIGH)`, `"glm-5.2": (_NONE, _HIGH)`, `_MUSE = (_MINIMAL, _LOW, _MEDIUM, _HIGH)`). Adding any one back is caught:

```
M13 KILLED [remap: deepseek medium sent]  ... test_every_refused_cell_is_refused_on_every_carrier_before_any_request[deepseek:deepseek-v4-pro:minimal]
M14 KILLED [remap: glm-5.2 low sent]      ... test_every_refused_cell_is_refused_on_every_carrier_before_any_request[glm:glm-5.2:minimal]
M15 KILLED [remap: muse xhigh sent]       ... test_every_refused_cell_is_refused_on_every_carrier_before_any_request[meta:muse-spark-1.1:none]
```

(The first failing case is another cell on the same line, because the refusal text lists the line's supported values.)

**A Jev child that misses the effort, or an excluded role that gets it.** Every Jev construction that carries Jev's temperature also carries the effort, except the run-brief writer, which uses its own `brief.temperature`:

```
$ grep -rnE "temperature=[a-z_.]*temperature" vidbyte/agents/jev vidbyte/lib/jev --include=*.py
vidbyte/agents/jev/agent.py:71, :104 · bulk_work.py:56 · compute/clone.py:39 · compute/swarm.py:51 · done/handoff.py:166 · done/reviewer.py:42 · done/run_state.py:286 · gate/clarification.py:59   -> each followed by reasoning_effort=settings.reasoning_effort
vidbyte/agents/jev/brief/writer.py:65:            temperature=brief.temperature,    -> no effort (excluded)
```

`grep -rln reasoning_effort vidbyte/agents/jev/brief vidbyte/lib/jev` prints nothing, so neither the brief writer nor the decision layer sees it. Specialists are agents the user builds and passes in, so the SDK never constructs one.

```
M16 KILLED [jev main agent misses it]       ... test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev
M17 KILLED [jev fresh partial misses it]    ... test_each_agent_on_jevs_model_sends_the_effort[fresh_continuation]
M18 KILLED [jev bulk_work misses it]        ... [bulk_worker]
M19 KILLED [jev clone misses it]            ... [clone]
M20 KILLED [jev swarm misses it]            ... [swarm]
M21 KILLED [jev done handoff misses it]     ... [handoff]
M22 KILLED [jev reviewer misses it]         ... [reviewer]
M23 KILLED [jev run_state misses it]        ... [run_state_relation]
M24 KILLED [jev clarification misses it]    ... [clarification]
M25 KILLED [excluded brief writer gets it]  ... test_the_run_brief_writer_keeps_its_own_settings
M43 KILLED [jev settings check skipped]     ... test_every_refused_cell_is_refused_on_every_carrier_before_any_request[openai:gpt-5.6-sol:minimal]
```

**A refusal text that drifted.** Each mutant changes one word of one §8.5 text:

```
M26 KILLED [text drift: capability]       ... test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev
M27 KILLED [text drift: no-row]           ... test_an_id_with_no_row_is_refused_with_the_no_row_text[openai:o1]
M28 KILLED [text drift: mode]             ... test_a_gateway_mode_is_refused_with_the_text_naming_direct[default-openai]
M29 KILLED [text drift: guard identity]   ... test_an_agent_without_both_a_provider_and_a_model_is_refused[no_model]
M30 KILLED [text drift: runner]           ... test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it
M31 KILLED [text drift: thinking_config]  ... test_effort_beside_thinking_config_or_an_overlapping_extra_body_is_refused[anthropic:claude-sonnet-5:high:0]
M32 KILLED [text drift: extra_body]       ... test_effort_beside_thinking_config_or_an_overlapping_extra_body_is_refused[openai:gpt-5.5:low:3]
```

**A body change when the effort is unset.** Independent of the pack, `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3/unset_bodies.py` builds 28 DIRECT bodies (7 providers × 4 option sets: plain; temperature and max tokens; a JSON schema; `extra_body` plus `thinking_config`) with no effort, once on the base tree and once on the branch:

```
28
IDENTICAL: 28 bodies, base 1fa23b65 vs branch
0          (errors)
```

```
M33 KILLED [unset: attach adds a key]           ... test_each_agent_on_jevs_model_sends_the_effort[main]
M34 KILLED [unset: checkpoint key always]       ... test_agent_reasoning_effort_unset.py::test_an_unset_checkpoint_has_no_effort_key[DIRECT]
M35 KILLED [unset: from_model kwarg always]     ... tests/test_agent_modality_routing.py::AgentModalityRoutingTests::test_model_identity_routes_to_image_runner
```

The other construction checks and copy paths:

```
M36 KILLED [runner non-text not refused]             ... test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it
M37 KILLED [thinking_config beside effort accepted]  ... test_effort_beside_thinking_config_or_an_overlapping_extra_body_is_refused[anthropic:claude-sonnet-5:high:0]
M38 KILLED [extra_body overlap accepted]             ... test_effort_beside_thinking_config_or_an_overlapping_extra_body_is_refused[openai:gpt-5.5:low:3]
M39 KILLED [fork drops effort]                       ... test_a_plain_fork_carries_the_effort_onto_the_wire
M40 KILLED [continual trace drops effort]            ... test_side_agents_built_from_a_source_carry_its_effort[continual_trace]
M41 KILLED [handoff drops effort]                    ... test_side_agents_built_from_a_source_carry_its_effort[handoff]
M42 KILLED [restore drops effort]                    ... test_a_checkpoint_carries_the_effort_and_the_restored_agent_sends_it
M44 KILLED [text config check skipped]               ... test_every_refused_cell_is_refused_on_every_carrier_before_any_request[openai:gpt-5.6-sol:minimal]
```

**A touched file outside §12.3.** None; see section 5.

**A gate claimed without its quoted output.** Section 7 quotes every gate's final lines.

## 9. Tricky parts: where to look first

1. **Private calls.** The registry calls `ProviderModelRegistry._require_provider`, and the guard calls `Runner._normalize_provider_and_model(...)[:2]`, which the spec prescribes. Both are private helpers of another class. If either changes shape, the effort checks change with it.
2. **The text runner always sets `options["reasoning_effort"]`.** A user-supplied `options["reasoning_effort"]` on a text runner is overwritten by the runner's own value, as `mode` and `api_keys` already are. I found no test or row about a user `options` key.
3. **Check order in `TextModelConfig`.** The effort check runs last in `__post_init__`, as row 4 says. So in a gateway mode, a provider the gateway does not serve, or a custom endpoint, fails first with the earlier `_require_gateway_shape` error, not with the mode text (the spec's AC-5 caveat). In DIRECT mode, an unknown provider string fails with "Unrecognized provider" before any effort text.
4. **§12.4 against §8.5 on `details`.** §12.4 says each `ConfigurationError` carries `details["field"]`, but §8.5 gives the Runner refusal `details={"provider", "model", "runner_type"}` with no `field`, and the pack compares it exactly. I followed §8.5.
5. **The README parser collision (deviation 2)** was the least obvious failure: a doc row broke a contract test in another feature's pack.
6. **The modality-routing pin (deviation 1)** was the test hardest to satisfy. It is an existing test outside the pack that pins `from_model`'s exact keywords, so row 12(d) as written could not pass it.
7. **`attach` inside the `extra_body` overlap check.** `TextModelConfig` finds the overlap by attaching the fragment into an empty dict and comparing top-level keys. A nested overlap, such as `extra_body={"generationConfig": {...}}` beside a Gemini effort, is refused as a whole top-level key, which is stricter than a key-path comparison. This is what §8.5's text describes ("extra_body also sets {keys}").
8. **Inherited local reds.** `test_harness_threads_surface.py:278` ("Left contains 2 more items, first extra item: 'vidbyte/lib/configs/__init__.py'") and `:309` ("Extra items in the left set: 'DecisionModelMode' 'DecisionModelConfig' 'ReasoningEffort'"). Both are named in §13, CI skips both, and both clear on merge. Nothing else is red.
