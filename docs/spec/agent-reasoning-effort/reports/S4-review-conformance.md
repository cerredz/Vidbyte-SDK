LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every agent, Jev and config path conforms to spec r3, but `Runner` silently drops an effort supplied through `options`, which INV-3 forbids.

WHAT THE IMPLEMENTATION GETS RIGHT
- The capability tables match spec §9.2 cell for cell: 52 "sent" ids, 193 sent cells, 30 "refused (all)" ids with no row, and 1 alias that resolves to its target. Every wire form equals the spec's "Wire form" line, and `attach` writes exactly that form (`probe_table.py` → `PROBLEMS: 0`).
- All 24 refusal sites (registry capability/no-row/mode, guard, guard no-identity, Jev, TextModelConfig mode/capability/both-set/overlap, Runner non-text, and 12 bad values across 3 carriers) match §8.5 character for character, `details` included (`checked 24; text ok 24; details ok 24`).
- An unset effort leaves the run unchanged (INV-1, AC-8). 43 DIRECT cases across 7 providers, covering runner bodies, URLs, headers, agent bodies and checkpoint `runtime_config`, give the same output on base 98a5d37b and on HEAD (`differ []`).
- Every copy path keeps the effort (fork, ContinualTrace, Handoff, export, restore, `to_fallback`, Jev relation, Runner text option, Jev mode check, TMC thinking_config check, guard mode). Each of 12 one-line mutants is caught by a named pack test (`12/12 KILLED`). The §4 snippet prints exactly its documented output (`PRINTED == EXPECTED: True`).

FINDINGS

R-C1 [Major] [spec conformance] vidbyte/lib/runners/utility.py:134 — `Runner` overwrites a caller's `options["reasoning_effort"]` with `None`, so the effort is silently dropped
  Evidence: `_config_options_for` runs `options["reasoning_effort"] = self.reasoning_effort` unconditionally inside the text branch. The non-text refusal at :137 checks only `self.reasoning_effort`. Probe `probe_edges.py`: `Runner(provider="openai", model_name="gpt-5.5", api_keys=[k], model_mode=DIRECT, options={"reasoning_effort": "high"}).build()` → `config.reasoning_effort = None`, sent body `reasoning = None`. With `options={"reasoning_effort": "minimal"}` (a value gpt-5.5 refuses) the result is `OK -> None`: no refusal and nothing sent. With `options={"reasoning_effort": "high"}` on `gpt-image-1`, an `ImageModelRunner` is built with no error. Precedent: `options={"temperature": 0.4}` is honoured (`config.temperature = 0.4`) because :142-143 overwrite only when `self.temperature is not None`. `TextModelConfig.reasoning_effort` is a public field, so `options` is a natural channel for it.
  Failure: a developer who passes the effort through `Runner(options=...)`, as with any other `TextModelConfig` field, gets a run without reasoning control and no error. Agent paths are not affected, because their `options` carry only `timeout`.
  Smallest fix: at :134, `if self.reasoning_effort is not None: options["reasoning_effort"] = self.reasoning_effort` (the temperature precedent). At :137, refuse when `self.reasoning_effort is not None or options.get("reasoning_effort") is not None` and the runner type is not text. Add one wire test (options effort reaches the body) and one refusals test (options effort on an image model is refused). Amend row 9(b) and add a §17 entry.
  Spec IDs: INV-3 (spec.md:165, "never dropped by `Runner`"), G-2, FR-5, EC-9, AC-16. Row 9(b) (spec.md:1024) prescribes the unconditional line. Part B (INV-3) outranks Part C, so the row is wrong: it did not consider an effort that arrives through `options`.

R-C2 [Minor] [deviations] docs/spec/agent-reasoning-effort/spec.md:1245 — §17 does not record three spec-internal conflicts the code had to resolve
  Evidence: (a) §12.4 (spec.md:1066) says each `ConfigurationError` carries `details["field"]`, but the §8.5 Runner row (spec.md:408) gives `details` without `field`. The code follows §8.5 (probe: `{"provider","model","runner_type"}`). (b) INV-11 (spec.md:173) says every refusal names the field, `provider:model` or mode, and the value. The §8.5 both-set, overlap, Runner and no-identity texts do not, and the code follows §8.5. (c) AC-18 (spec.md:207) says the message names the model "as given, stripped". D-5 (spec.md:306) has the guard normalize through `Runner._normalize_provider_and_model` first, so `Agent(model_name="openai/gpt-5.6", reasoning_effort=MINIMAL)` names `openai:gpt-5.6`, while `TextModelConfig(model="openai/gpt-5.6")` names `openai:openai/gpt-5.6`. AC-18's tests cover prefixed ids only at registry level (`test_agent_reasoning_effort_registry.py:316-339`).
  Failure: a later editor who follows INV-11, §12.4 or AC-18 literally will "fix" correct code or write a test that cannot pass.
  Smallest fix: add a §17 note that §8.5 binds over §12.4 for Runner `details`. Reword INV-11 to "names what is wrong and how to fix it, per §8.5". Narrow AC-18 to "the registry and config texts name the model as given; the agent guard names the id its runner will call (D-5)".
  Spec IDs: INV-11, AC-18, D-5, §8.5, §12.4.

Deviation judgments (spec §17 items 1-6): 1 is necessary and minimal. The unconditional kwarg fails `tests/test_agent_modality_routing.py:74`, the request is unchanged, and the item is recorded. 2 is necessary: the `| meta |` parser is at `tests/features/sdk_provider_keys/test_provider_keys_contract.py:341`. 3 is harmless. 4 is harmless, and its `details` follow §12.4. 5 meets row 3's "raises its `ConfigurationError`", which `resolve_provider` (returns `None`) cannot do. Cross-module private access belongs to the conventions lens. 6 is permitted by the settled briefing (PR number at S6). There is no undisclosed deviation other than R-C1. §5 diagram: the code matches it, with two benign differences. `_runner_for_model` passes the kwarg only when set (item 1). TextModelConfig validation runs again on each call, because `TextModelRunner.arun` uses `dataclasses.replace`. The overlap check attaches into a scratch dict.

VERIFIED CLAIMS
- S3: "pack 655/655 green". Pack + area + modality pins: `1094 passed in 8.86s`. The mutation control on a git-archive copy gave `653 passed, 2 deselected` (the 2 deselected are contract tests that need `contracts/`).
- S3: "733 → 736 exports". `py -3.11 scripts/generate-sdk-public-api.py --check` → `current at 654deee6… (vidbyte-sdk 0.4.0, 736 exports)`.
- S3: "`base.py` +11 ≤ 12". `git diff --numstat … -- vidbyte/agents/base.py` → `13 2`.
- S3: "no files outside §12.3". Script: `rows: 39`, `12.3 not changed: []`, and the only changed files outside the rows are `S3-implementer.md` and `spec.md` (the §17/pr/status edits the template assigns to S3).
- S3: "tests untouched since S2". `git diff --stat 1fa23b65 8e773244 -- tests` is empty.
- §14 Never list: `lint/` diff is empty, `runtime.py`, tools and http diffs are empty, no `FailureCode` line changed (count `0`), and pyproject/requirements are unchanged.
- Row 34: `docs/design/release-0-4-0.md` changes only lines 17 and 19, the text is exact, and there is no PR number (item 6).
- Budget §8.4: 3 new files (170, 115 and 61 lines), 3 new classes, 3 root names, 7 new keyword parameters or fields, 0 dependencies and 0 config keys.
- README sources sections are placed as row 29 says (registries :80 between Provider Key Format Sources and Browser Tool Sources; agents :433 between Spend Cap and Key Modules). All five READMEs fit the A009 size limits.
- INV-18 order: the spend-cap refusal text is unchanged with the effort set, and it comes first (`test_the_spend_cap_refusal_still_runs_before_the_effort_guard`).
- Fallback chain: a bad third hop is refused at construction and named (`gemini:gemini-3.5-flash`); `restore` and `fork` keep `HIGH`; the checkpoint stores `'high'`, a plain string.

COMMANDS RUN (scratch dir `…/scratchpad/r2e-s4/conformance/`, all with inline `PYTHONPATH=$(pwd) py -3.11`, network patched out, key fixtures built at run time)
- `probe_snippet.py` → `PRINTED == EXPECTED: True`; planner `reasoning {'effort': 'high'}`; gemini requests `[]`; jev `output_config {'effort': 'low'}`
- `probe_table.py` → `spec sent-lines ids: 52; code rows: 52; code sent cells: 193; refused-all ids: 30; aliases: 1` / `PROBLEMS: 0`
- `probe_texts.py` → `checked 24; text ok 24; details ok 24`
- `probe_unset.py` on base and HEAD archives → `cases: 43 errors: 0` ×2; JSON diff `differ []`
- `probe_edges.py` → `[options text] config.reasoning_effort = None`, `body reasoning = None`, `[options text minimal] OK -> None`, `[options temperature] config.temperature = 0.4`, `[options image] OK -> ImageModelRunner`, agent prefixed → `openai:gpt-5.6`, tmc prefixed → `openai:openai/gpt-5.6`
- `py -3.11 -m pytest -q tests/features/agent_reasoning_effort <area + modality pins>` → `1094 passed in 8.86s`
- `mutate.py <HEAD archive>` → `CONTROL 0 653 passed, 2 deselected`; 12/12 `KILLED`
- `py -3.11 scripts/generate-sdk-public-api.py --check` → current, 736 exports
- `git diff --stat|--numstat|--name-only 98a5d37b...8e773244` (lint/, tests since 1fa23b65, runtime/tools/http, base.py, §12.3 compare, row 34 lines)
