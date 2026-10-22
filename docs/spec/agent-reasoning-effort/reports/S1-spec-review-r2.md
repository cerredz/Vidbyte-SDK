VERDICT: SOUND WITH FIXES — All seven round-1 findings are closed against the code and the raw files, but the r2 move to `vidbyte/lib/configs/` added two lint regressions (an I001 import order that fails the zero-slack S051 gate, and an unused import that S001 reports) and one AC-4 wording gap a blind test author can turn into a red test that cannot be made green; each needs a one-line fix.

Reviewer: S1 adversarial spec reviewer, round 2 (final). Spec: `docs/spec/agent-reasoning-effort/spec.md` r2 (commit a7717324), code at 98a5d37b. Probes: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r2e-s1-review-r2/` (`rq2.py`, `dsfind.py`, `probe_to_enum.py`, `probe_catalog.py`, `probe_construct.py`, `probe_jev.py`). No request was sent to a vendor. I did not use the author's scripts' verdicts as evidence.

ROUND-1 CLOSURE

| Round-1 finding | Status | Evidence (independent of the author's table) |
|---|---|---|
| R-1 [Blocker] `to_enum` accepts a foreign str-valued member | CLOSED | `probe_to_enum.py` with a six-member `StrEnum` stand-in: `'max'`, `''`, `'HIGH'` and `3` give `AgentRunnerConfig.reasoning_effort must be one of none, minimal, low, medium, high, xhigh; got 'max'.` (and `got ''.`, `got 'HIGH'.`, `got 3.`). `'high'`, `GrokReasoningEffort.HIGH`, `CodexReasoningEffort.HIGH` (a `(str, Enum)`), `MuseReasoningEffort.HIGH`, and even a member named `DEEP` whose value is `'high'` are all accepted as the `HIGH` member. That matches r2 INV-8 and AC-10 exactly. `CredentialKeyPolicy.is_secret_key("reasoning_effort")` is False, so the value is quoted, not redacted. Residual nit, not a finding: AC-10 writes `got <value>.` while the real text is the repr (`got 'max'.`). §8.5's `<repr>` is the exact form, so S2 should copy §8.5. |
| R-2 [Major] false NG-14 reason | CLOSED | NG-14, EC-10, the §9.2 reading notes, rows 2a and 3 and §13 now give the scope-choice reason. `probe_catalog.py` compares the §9.2 ids with the exact text ids in `MODEL_PROVIDER_RUNNER_TYPE_MAP`. Every catalog text id for the 7 providers has a §9.2 line (OpenAI 23, Anthropic 14, Gemini 10, DeepSeek 3, xAI 11, GLM 10, Meta 5). The ids outside the catalog (`gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-5-mini`, `gpt-5-nano`, `deepseek-chat`, `deepseek-reasoner`, `glm-4`) have no "sent" cell, so no `REASONING_EFFORT_SUPPORT` row is built outside the catalog. |
| R-3 [Major] no-row text claimed a vendor fact | CLOSED, with a new gap (R-3 below) | The §8.5 no-row text names the value, `REASONING_EFFORT_AS_OF` and the README section. The capability text is used only for an id with a row. Both are deterministic and exactly testable. INV-11, AC-4, EC-10, EC-11, EC-23, EC-24 and C5 item 4 follow. The split leaves 7 ids whose §9.2 line is all "refused" but not marked "refused (all)", and AC-4 points them at the wrong text (R-3). |
| R-4 [Major] tables broke the capability-data convention | CLOSED, with regressions (R-1, R-2, R-4 below) | Row 2a puts the tables in `vidbyte/lib/configs/reasoning_effort.py`, and row 3a exports the registry. The precedent is real: `vidbyte/lib/registries/__init__.py:26` imports all 6 config names plus `StructuredOutputRegistry`, and `registries/structured_output.py`'s `__all__` lists all of them. The import rule (only `vidbyte.lib.enums` and `typing`) matches `configs/structured_output.py:25-29` (stdlib plus `vidbyte.lib.enums`). No lint rule restricts what `lib/configs` may import beyond A006. A006 draws no edge to the `vidbyte.lib.enums` facade, and no `vidbyte/lib/enums/*` module imports `vidbyte.lib.configs` (`git grep`), so no cycle forms. A006 has zero slack (34/34). §11 and §13 name `:270-278` as an inherited local red. |
| R-5 [Minor] AC-5 earlier refusal | CLOSED | `probe_construct.py` gives `TextModelConfig(provider="glm", model="glm-5.2")` with AUTO → `UnsupportedProviderError` "The Vidbyte gateway serves only: anthropic, deepseek, gemini, kimi, openai, xai. Use mode=TextModelMode.DIRECT to call glm with your own key". The endpoint text at `model_configs.py:201` also names DIRECT. `Agent` and `JevAgentSettings` in AUTO construct today with no key, so their AC-5 refusal is the guard's or the settings' mode text. |
| R-6 [Minor] GL-20, GL-21, XA-29 not verbatim | CLOSED | `rq2.py` is a byte-level substring check for every non-HTML file, with no whitespace or escape normalization. GL-18 is at raw lines 439 and 651, GL-20 at 718, GL-21 at 727, and every locator matches. XA-29 occurs byte for byte in `xai-openapi.json`. The JSON path `components.schemas.Message.oneOf[3].properties.reasoning_content.description` is `"Assistant reasoning content."` on the `role: assistant` schema. G103 is at line 6343 and XA-38 at line 51, as their locators say. The whole catalog has 224 lines: 198 are byte-exact in non-HTML files, 20 are HTML page text (9 under the spaced-tag rule, 11 DeepSeek lines with inline tags flattened, `dsfind.py`), and 6 absence checks pass. All 74 cited (URL, UTC) pairs are logged with HTTP 200 and the logged size. |
| R-7 [Minor] provable assumptions | CLOSED (residual R-5 below) | A-6 (G103) held. A-7: a DOM-depth probe puts `reasoning_effort` at depth 26 with `model`, `max_tokens` and `temperature`. `messages`, `thinking` and `tools` are at 28, so array and object fields render 2 deeper, and `reasoning_effort` is top level. A-8: `broker.py:168-171` and `base.py:1534-1537`, where `_call_with_supported_kwargs` (`:1694-1711`) drops `model_name`, and `TextModelRunner.arun` (`text.py:69`) has no such parameter. A-4 for grok-4.7: XA-38 sits inside `client.chat.completions.create(` with `base_url="https://api.x.ai/v1"`. |

WHAT THE SPEC GETS RIGHT

- **Wire placement and guard placement still match the code.** The four builders attach before `_attach_extra_body`. The guard is one statement after the spend-cap raise at `base.py:255-257`. `_config_options_for` stays at C901 5 after row 9 (scratch copy measured with `--config lint.mccabe.max-complexity=1`). `TextModelConfig.__post_init__` and `JevAgentSettings.__post_init__` gain a call and no branch. Do not "simplify" any of this.
- **The vendor table survives a strict independent re-check** (see R-6 above), and every remap is refused. Every SDK/CLI default model has a usable row. The defaults are `DEFAULT_PROVIDER_MODELS` at `vidbyte/lib/registries/models.py:73-82`:
  - gpt-5.6-sol: none, low to xhigh;
  - claude-sonnet-5: none, low to xhigh;
  - grok-4.5: low, medium, high;
  - deepseek-v4-pro: none, low, high;
  - glm-5.2: none, high;
  - muse-spark-1.1: minimal to high;
  - gemini-3.5-flash: minimal to high.
- **The root slice and release record are exact.**
  - `len(vidbyte.__all__) == 733`, none of the three names exists yet, and `"TextModelMode"` is at `:1128`.
  - Row 27's import positions are I001-sorted (`model_configs` between `handoff_agent_descriptor` and `multi_agent_descriptor`; `DecisionModelMode` after `BudgetPreset`; `ReasoningEffort` after `Prompt`).
  - The one-line header bullet satisfies `PART_BREAK`/`HEADER_BULLET` in `test_jev_cli_root_exports_contract.py:35-37,173-184`.
  - The release before-texts are verbatim: line 17 ends with the #1192 sentence, and line 19 contains the tally sentence once.
  - The §4 snippet's `JevAgent` constructs today in DIRECT with no Vidbyte key (`probe_jev.py`).
- **The scope is right.** No addition goes beyond the conversation. The configs module, its exports, `REASONING_EFFORT_AS_OF` and the README sources section all come from round-1 placement and the repo's README and sources obligations. Q-10 is `[scope-adding]`, non-blocking, default No, and there are 0 blocking questions.

FINDINGS (ranked, most severe first)

R-1 [Blocker] [L8/L4] §12.3 row 2b, §12.4 — Row 2b puts the new configs import after `structured_output`. Ruff I001 rejects that order, and S051 has zero slack, so the lint gate fails. §12.4 has no import-order obligation, although the field-guide entry that §11 cites records this exact trap.
  Evidence:
    - Row 2b says "Add `from vidbyte.lib.configs.reasoning_effort import (...)` after the `structured_output` import".
    - Scratch copy of `vidbyte/lib/configs/__init__.py` with that edit, checked with `py -3.11 -m ruff check ... --config lint/ruff.toml --select I001`: `vidbyte\lib\configs\__init__.py:3:1: I001 [*] Import block is un-sorted or un-formatted`. Ruff sorts `reasoning_effort` before `structured_output`.
    - `lint/rules/s051_modernized_import_and_syntax_hygiene.py:23` owns I001.
    - `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule S051` on the base prints `S051 ... 259 259 RATCHETED`, which is zero slack.
    - The file is I001-clean at base. So are `model_configs.py`, `lib/dataclasses/agents.py`, `lib/enums/__init__.py`, `text_model.py`, `anthropic.py`, `gemini.py`, `compatible.py`, `agents/settings/fallback.py`, `fork.py`, `continual_trace.py`, `handoff.py`, `jev/settings.py`, `jev/agent.py` and `vidbyte/__init__.py`. Every import edit in those files must land in sorted order.
    - Row 10 says "`RecordFieldConverter` beside `RecordFieldValidator`". The probe `from ...validation import RecordFieldValidator, RecordFieldConverter` gives I001 as well.
    - Field guide `local-ci-verification.md:38-42`: "Check S051 import sorting with ruff over the whole `vidbyte` tree". §11 cites this entry only for the staged gate.
  Failure: S3 builds row 2b exactly. S051 goes to 260 against 259, `lint/run.py` fails, and so does `scripts/run_ci.py`. The implementer can turn the gate green only by deviating from §12.3.
  Smallest fix:
    - Row 2b: "before the `structured_output` import (module order)".
    - Row 10: "`RecordFieldConverter, RecordFieldValidator` (names sorted)".
    - Add to §12.4: "Every added import and imported name is in ruff isort order. `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` lists no file that is I001-clean at `base_commit`. S051 has zero slack (259/259). Source: field guide `local-ci-verification.md:38`."

R-2 [Major] [L8/L9] §12.3 row 3(b), §8.5 — The registry imports `GEMINI_THINKING_BUDGET_OFF` but neither uses nor re-exports it. Ruff F401 (S001) reports that, which breaks NFR-3's "zero new findings per rule".
  Evidence:
    - Row 3(b) says "Import `REASONING_EFFORT_AS_OF`, `REASONING_EFFORT_FORMS`, `REASONING_EFFORT_SUPPORT` and `GEMINI_THINKING_BUDGET_OFF` from `vidbyte.lib.configs.reasoning_effort`".
    - Row 3(c)'s `__all__` leaves it out, and so does §8.5 ("the registry re-exports all but GEMINI_THINKING_BUDGET_OFF").
    - No registry method needs the constant. `attach` copies the fragment, which already holds the value from `REASONING_EFFORT_FORMS` (row 2a).
    - S001 selects `("F", "E4", "E7", "E9")` (`s001_python_correctness_foundation.py:23`). A scratch probe of a module with an unused import absent from `__all__` gives `F401 ... imported but unused`.
    - `lint/run.py --rule S001` on the base prints `56 59 IMPROVED`. The gate total passes on slack, but the per-rule count goes from 56 to 57.
  Failure: S3 follows row 3. S4's per-rule comparison (NFR-3, §14 "compare lint per rule with `base_commit`") reports a new S001 finding. Either the implementer silently deviates from row 3, or the PR ships an unused import.
  Smallest fix: Remove `GEMINI_THINKING_BUDGET_OFF` from row 3(b)'s import list. The alternative is to re-export it, as `registries/structured_output.py` does with all six of its config names, and add it to row 3(c), row 3a and §8.5.

R-3 [Major] [L10/L9] §6.2 AC-4, §9.2 C5 contract item 4 — For 7 ids, AC-4 names the wrong text. Each has a §9.2 line whose six cells all say "refused", but the line is not marked "refused (all)". AC-4 sends them to the capability text "(an id with a row)". Row 2a builds no `REASONING_EFFORT_SUPPORT` row for them, so the code must return the no-row text. "Never an empty tuple" is not an INV.
  Evidence:
    - AC-4: "`ConfigurationError` is raised with the §8.5 capability text (an id with a row) or the §8.5 no-row text (an id without one)".
    - C5 item 4: "for every "refused" cell (the capability text)".
    - The §9.2 lines are OpenAI `` `o1`, `o3`, `o4-mini`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4o` `` ("refused" ×6, "unverified") and Gemini `` `gemini-2.5-pro` `` ("refused [G88] \| refused \| …" ×6). `probe_catalog.py` lists exactly these 7 as "zero 'sent' and not 'refused (all)'".
    - Reading note: "A "refused (all)" line records why an id has no row in `REASONING_EFFORT_SUPPORT`". Row 2a(d): "exactly the §9.2 rows that have at least one "sent" cell".
    - §8.5 capability text: "Used only when the id has a row, so the list is never empty".
    - The non-empty-tuple rule appears only in the §8.5 comment, row 2a and the §12.4 checklist. No INV or AC states it.
  Failure: S2 parametrizes AC-4 over every refused cell of the §9.2 table. For `gemini-2.5-pro` with `high`, or `o3` with `high`, it asserts the capability text (`"... has no documented form for reasoning effort 'high' (it supports"`). S3, following row 2a, returns the no-row text. The test is red. Turning it green would take an empty tuple, which row 2a and §12.4 forbid, so the test can never pass.
  Smallest fix:
    - AC-4 and C5 item 4 say: "the capability text (an id with at least one "sent" cell, that is, a `REASONING_EFFORT_SUPPORT` row) or the no-row text (any other id, including a §9.2 line with no "sent" cell)".
    - Optionally relabel those two lines "refused (all; …)".
    - Add an INV: "`REASONING_EFFORT_SUPPORT` holds exactly the §9.2 ids that have at least one "sent" cell. Each tuple is non-empty and in enum order."

R-4 [Minor] [L8] §12.5 — The REPO_MAP entry for `vidbyte/lib/configs/` says the folder "currently holds one such object, describing how a model's structured output is requested and subsequently validated". Rows 2a and 2b make that false, and §12 has no row for it.
  Evidence:
    - `REPO_MAP.md:185-187`.
    - AGENTS.md: the map "is expected to drift, so regenerate a wrong entry from the tree".
    - Both review workflows read REPO_MAP on every PR (`.github/prompts/agents-md-placement.md:13`, `.github/workflows/claude.yml:57`).
    - Field guide `agents-md-map.md:3`: "Keep Map folder entries as general intent, never file, subfolder, or command references".
    - A related precedent: `vidbyte/lib/README.md:40` names each newly added registry, with "(their sources are in `registries/README.md`)", as #1183 and #1159 did when they edited it.
    - §12.5 says only "No `llms.txt`, `.env.example`, changelog or baseline change".
  Failure: The PR leaves a map sentence that the PR itself makes untrue, in the file the placement and review workflows read first. That is a likely convention comment. No gate fails.
  Smallest fix:
    - Add a P6 doc row (a MODIFY, not a new file). Replace "It currently holds one such object, describing how a model's structured output is requested and subsequently validated." with a general-intent sentence, for example: "It holds fixed per-feature capability data, such as which request shapes and reasoning levels each provider and model accepts, that registries read." Use no file names.
    - Optionally add `ReasoningEffortRegistry` to `vidbyte/lib/README.md:40`.

R-5 [Minor] [L1] §15 A-4 — A-4 stays open for grok-4.6 only, but grok-4.5 has the same evidence gap. grok-4.5 is the SDK's and CLI's default xAI model.
  Evidence:
    - Raw `xai-model-grok-4.6.md` and `xai-model-grok-4.5.md` list no API surface.
    - `xai-grok-4-6.md` is a "404 — Page not found" body.
    - Every `model=` example in `xai-legacy-chat-completions.md`, `xai-function-calling.md` and `xai-cost-tracking.md` is `grok-4.7` or `grok-4`.
    - `xai-reasoning.md:146-147` gives grok-4.6 and grok-4.5 only in the Responses `reasoning.effort` form.
    - `models.py:77`: `ModelProvider.XAI: "grok-4.5"`.
    - The chat-side evidence for both is XA-1 (the chat reference documents `reasoning_effort` with per-model values) plus XA-2 (which names both models).
  Failure: Nothing new breaks. If xAI does not serve either model on chat completions, calls fail whatever the effort is, and the failure is loud. The risk is that a reader takes grok-4.5's cells as proven when they rest on the same assumption as grok-4.6's.
  Smallest fix: A-4 reads "xAI serves `grok-4.6` and `grok-4.5` on chat completions …", with the same "if wrong" clause.

VERIFIED CLAIMS

1. The lib/configs module and its imports held. Only `structured_output.py` lives there today, and it imports stdlib plus `vidbyte.lib.enums`. `configs/__init__.py` imports one module eagerly. `model_configs.py:47` already imports `vidbyte.lib.registries.models`, so importing `registries.reasoning_effort` from it adds no package-init cycle. `registries.models` imports `lib.dataclasses` only under `TYPE_CHECKING`. A006 is clean for the new edges.
2. Row 3a's export precedent held: `vidbyte/lib/registries/__init__.py:26`. Excluding `GEMINI_THINKING_BUDGET_OFF` is a valid API choice, but row 3(b)'s import of it is not (R-2). The `registries/__init__.py` import block already carries an I001 (`actors` is last), so row 3a adds no new S051 finding.
3. The inherited local red is real and correctly named, with one nit.
   - `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` is at `tests/features/harness_threads/test_harness_threads_surface.py:270-278`. It diffs `vidbyte/lib/configs` against `merge_base()`, which skips without `origin/main` (`:139-143`). §11 names the test, and §13 names the lines.
   - Rows 2a and 2b make it red locally, both while the new file is untracked (`ls-files --others`) and after it is committed.
   - `ci.yml:27,48` checks out with no `fetch-depth`, so it gets the shallow default, which matches A-9's mechanism.
   - Nit: the `:309` clause uses `optional_merge_base()` (`:131-137`, `if base is not None`) rather than `merge_base()`'s skip, so "Both skip … (`:139-143`)" is imprecise for `:309`. The effect is the same, because the clause does not run in CI.
4. The no-row text held. Its README section is row 29 (`## Reasoning Effort Sources`) and §12.5. The registries README is 12,262 characters, and adding at most 3,500 keeps it under A009's 40,000. The agents README goes from 33,180 to about 35,000. The providers README is 40,944 against its legacy ceiling of 55,000. The text is deterministic.
5. Row ids held. Every "row N" reference in §12–§14 resolves (2a, 2b, 3a, 5, 27, 32, 34, 1–34). The new-file count is 3 (rows 2a, 3 and 11), equal to §8.4. The template defines CREATE/MODIFY/DELETE (`spec-template.md:230`), and no stage prompt parses the Action column, so "MODIFY (generated)" reads as a MODIFY with a note. That is acceptable.
6. Line anchors held at 98a5d37b:
   - `base.py:112` (`temperature`), `:193-201`, `:250-257`, `:1676-1691`, `:42`, `:58`;
   - `agents.py:36,38`, `fallback.py:33,193-215`, `settings/fallback.py:29`;
   - `jev/settings.py:151` (`system_prompt_presets`) and `:178` (`_validate_timeout`);
   - `enums/__init__.py:214`, `"ReasoningStrategyEnum"` at `:350`;
   - `utility.py:117-134`, `validation.py:221-230`, `model_configs.py:95-96,193-208`.
7. Per-rule lint slack at base held, and two rules have none to spare. Zero slack: A001 642, A006 34, A007 255, C008 45, S008 19, S015 13, S020 1, S060 32 and S051 259. Slack: S001 56/59, A002 608/703, and S009 346/350 (from request.md §C, "Known traps"; not re-run). `_validate_reasoning_effort` does not match C008's primitive-name grammar. The registry's `attach(payload: dict[str, Any])` is in `lib/registries`, which is outside S060's scope (`s060_typed_public_seam_mappings.py:24`).
8. The field-guide citation held. `declarative-config-resolution.md:38-43` says what D-17 quotes.
9. The weight held. The spec has 37 rows (34 numbered, plus 2a, 2b and 3a). No addition is scope the conversation lacks.
