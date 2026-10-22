# S1 spec author report: agent-reasoning-effort (run R2)

- **Spec:** `docs/spec/agent-reasoning-effort/spec.md`, revision 1, committed as `96cd9e62` on `feat/agent-reasoning-effort`. The base is `98a5d37b`, and the previous HEAD was `b076ebd8`.
- **Report:** this file is not committed.

## What I read

**Pipeline inputs.** The stage template and the orchestrator briefing (the prompt file). I also read, in full:
- `request.md`: §A prompts, §C structured notes and Q1–Q5 defaults, §D weighted words.
- `context/code-map.md`.
- `pipeline.md`: niche facts and the 2026-10-20 gateway ruling.
- The house style.

**Code, re-opened wherever a design choice depended on it:**
- Records and validation: `vidbyte/lib/dataclasses/model_configs.py` (TextModelConfig, DecisionModelConfig), `agents.py` (AgentRunnerConfig), `validation.py` (`RecordFieldConverter.to_enum`), `native_threads.py` (the GrokThreadConfig precedent).
- Enums: `vidbyte/lib/enums/text_model.py`, `__init__.py`, `native_threads.py` (StrEnum note).
- Registry: `vidbyte/lib/registries/models.py` (normalize_model, aliases, endpoints).
- Runner: `vidbyte/lib/runners/utility.py` (`Runner.__init__`, `from_model`, `build`, `_config_options_for`).
- The four payload builders and their `_attach_extra_body`: `vidbyte/providers/openai.py`, `anthropic.py`, `gemini.py`, `compatible.py`.
- Agent layer: `vidbyte/agents/base.py`, `fallback.py`, `settings/fallback.py`, `fork.py`, `continual_trace.py`, `handoff.py`, `spend_cap.py` (the sibling, read in full).
- Jev: `vidbyte/agents/jev/settings.py`, `agent.py`, and the 8 Jev child builders.
- Other code: the fork tool (`tools/builtins/fork/fork.py`), `CodingAgent` (`**kwargs`), the pricing parsers, `runtime.py` (`_assistant_message`), the actor broker, and the root `vidbyte/__init__.py` (header bullet, imports, `__all__`).
- Lint rule sources: A001, A002, A007, A009, S060, and `lint/baseline.json` (C008, S008, S009).

**Tests that pin layouts or signatures:**
- `tests/features/sdk_managed_text/test_managed_text_selection.py:54-58`
- `tests/features/sdk_provider_keys/test_provider_keys_contract.py:120-221`
- `test_output_connectors_agent_wiring.py:112`
- `test_coding_agent_contract.py:117`
- `test_jev_cli_root_exports_contract.py`
- `test_harness_threads_surface.py:218-309`
- The R3 spend-cap test pack (seams and fixtures).

**Vendor docs.** I used about 170 raw downloads under the scratch folder `r2e-s1/raw/`, with three fetch logs giving URL, HTTP status, UTC time and bytes. All were fetched on 2026-10-20. I fetched 9 more OpenAI model pages myself (`s1-own-fetchlog.tsv`) to close gaps: `gpt-5.5-pro`, `gpt-5.4-pro`, `gpt-5.4-nano`, `gpt-5.3-codex`, `o1`, `o3`, `o4-mini`, `gpt-5-nano`, `gpt-4o`.

## Approaches weighed

| Option | Shape | Verdict |
|---|---|---|
| A (smallest) | The agent builds a per-vendor dict and sends it through `extra_body` or `thinking_config`. | **Rejected.** Every adapter applies `extra_body` with `payload.update`. On Anthropic that erases `output_config.format`, which breaks every structured-output agent, including the Jev machinery. On Gemini it erases `generationConfig` (temperature, schema). `thinking_config` is ignored by OpenAI and the compatible adapters, and `Runner` drops unknown options. It fails INV-2, INV-3 and INV-7. |
| B | Validate only in `TextModelConfig`. | **Rejected.** It refuses only at the first `arun`, and only for the hop in use, because fallback configs are built on a switch (`base.py:1375`). A bad primary in front of a good fallback would pay for a failed call every turn. It fails INV-4 and INV-6. |
| **Chosen** | A typed `TextModelConfig.reasoning_effort` field, plus a lib registry `ReasoningEffortRegistry`. The registry holds one explicit per-model table, the refusal texts, and a deep-merging `attach`. Each of the 4 payload builders gets one `attach` call, placed right before `_attach_extra_body`. A construction-time guard, `AgentReasoningEffortGuard`, mirrors R3's `AgentSpendCap`. The effort is threaded down the copy paths that already carry `temperature`. | **Chosen.** One audited table instead of four adapters; loud refusals before any spend. Budget: 2 new files, 3 classes, 3 root names, 0 dependencies, 0 config keys, 0 `FailureCode` members. |

## Disagreements with the scout and the request, with evidence

1. **The pinned layout tests cannot pass unedited.** The briefing asks how they pass. They do not:
   - `EXPECTED_TEXT_CONFIG_FIELDS` (`test_managed_text_selection.py:54-58`, asserted at `:344`) and the `RecordLayoutTests` lists (`test_provider_keys_contract.py:128-140`) are exact field lists.
   - Their own docstring says "new fields are appended". Appending `"reasoning_effort"` keeps their purpose, which is a positional layout.
   - I assigned those edits to S2 (§12.5, §13, §14). The implementer must never touch them.
2. **Several vendor "supported" values are actually remaps, so the spec refuses them** (D-P9 "never silently ignore"):
   - DeepSeek `minimal`/`medium`/`xhigh` (DS-6: "minimal is accepted and mapped to low, and medium / xhigh are accepted and mapped to high").
   - GLM-5.2 `minimal`/`low`/`medium`/`xhigh` (GL-7).
   - Meta `xhigh` (MS-11 "maps to the same reasoning strength as `high`").
   - grok-4.5 `xhigh` (XA-7 "treated as `high`").

   A scout reading that counted these values as "supported" would send values the user never gets.
3. **The two Gemini doc pages conflict.** The Interactions-API page (G100) lists `low, medium, high` levels for `gemini-2.5-flash`. The generateContent page that the SDK's adapter calls says "Gemini 2.5 series models don't support `thinkingLevel`" (G16). The spec follows the generateContent page: on 2.5 Flash and Flash-Lite only `none` (`thinkingBudget: 0`) is sent.
4. **`none` on Anthropic is model-specific, and the effort page qualifies it.** The `disabled` column of the thinking table (A80–A87, A17, A18, A20) and A98 say `thinking: disabled` works "at `high` effort or below", with 400 at `xhigh`. The SDK sends only the `thinking` field for `none`, so the call runs at the model's default effort, which is high or medium (A56). That makes `none` safe on Opus 5 and Haiku 5.5, and it is refused on the 5.5, Fable and Mythos models.
5. **Checks of earlier assumptions:**
   - Gemini `none` on 3.x stays refused. `thinking_budget` is still accepted on 3.5 Flash "for backward compatibility" (G101, G102), but no page says a budget of 0 turns thinking off there. G14 says 3 Flash and Flash-Lite cannot fully turn thinking off.
   - Each of the 6 older OpenAI pages (`o1`, `o3`, `o4-mini`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4o`) contains no "effort" text at all. Those ids are "unverified → refused" (OA-1…OA-6), not guessed.
6. **The briefing defers to REPO_MAP's "a setting here rather than another constructor parameter".** The code's grain is different: `temperature` is a `BaseAgent` constructor parameter (`base.py:112`). The spec follows the code and records the conflict in §11.

## Assumptions I am least sure of

- **A-4:** grok-4.7 (and 4.6) are served on chat completions. XA-2 names the parameter, but the grok-4.7 page lists only the Responses API (XA-37). If this is wrong, those calls fail whatever the effort is, and the cells must flip to refused.
- **A-1:** the Anthropic display-name → id pairs for Opus 5, Fable 5, Mythos 5, Mythos 5.1 and Opus 4.8. The ids appear verbatim in the effort page's `supportedModels` list, but no page shows "Model ID:" for these five.
- **A-3:** GLM `completion_tokens` includes reasoning. No reasoning field exists, and the example totals add up as prompt + completion. If this is wrong, it is a pre-existing under-count.
- **A-8:** actor and algorithm side calls use the agent's own model. The broker sets `model_name` from a target model (`broker.py:168`).
- **A-6 / A-7:** wire spellings. Gemini takes upper-case level names. DeepSeek takes a top-level `reasoning_effort` over raw HTTP.
- **D-9 (Q-3):** the Jev machinery (RunState, Handoff, Reviewer, Clarification) inherits the effort, following the `temperature` precedent. A user who wants cheap machinery calls would answer Q-3 Yes.

## Verifier result

Three scripts in `r2e-s1/scripts/` check the spec. The last two are independent of the generator (they share no code with `s1-build-catalog.py`), and all ran with `py -3.11 -I`:

1. **`s1-build-catalog.py`** builds the §9.2 source catalog: 222 entries, 216 verbatim quotes and 6 absence checks. It re-locates every quote in the extracted text and takes each URL and UTC time from the fetch logs, never from scout notes.
2. **`s1-verify-spec.py`** reads only the spec's catalog lines, the three fetch logs and `raw/`. For each line it checks that:
   - the URL is logged with HTTP 200;
   - the cited UTC time is logged for that URL;
   - the raw file's size equals the logged size;
   - the quote occurs in the raw file. It uses its own extraction: html.parser for HTML, json.dumps for JSON, whitespace-normalized text, and adjacent text nodes for table rows;
   - the quote ends on a token boundary, and a one-token model-id list item is a whole line;
   - each "absent" word never occurs.

   It also checks that every quote ID cited outside the catalog has a line.

   **Result: 222 lines, 0 failures.**

   A mutation test was run on a copy with 5 planted defects: a changed quote, a truncated model id, a wrong fetch time, a wrong absence word, and a cited ID with no catalog line. It reported exactly those 5 failures and exited 1.
3. **`s1-crosscheck-table.py`** checks every "sent" cell of the mapping tables against the value words in that row's cited quotes. A documented off form counts as proof of `none`: Anthropic "Thinking off" in the `disabled` cell, or Gemini `thinkingBudget = 0`. **Result: 0 rows with an unproven sent value.**

   Every "refused but named" case is either a documented remap, a documented conflict, or an explicit "not supported" or 400. The cases are: gpt-6.1-sol and gpt-6-astra `none`; gemini-3.8-flash and 3.1-pro `minimal`; DeepSeek; GLM-5.2; grok-4.5 and grok-4.3 `xhigh`; Muse `none` and `xhigh`.

**Stage E self-check:**
- Traceability:
  - FR→W/AC: all 12 FRs covered.
  - AC→W/§12.3: all 20 ACs covered, after adding AC-8 and AC-17 to W-4 and W-6.
  - §12.3: all 34 rows name an FR/NFR/W.
  - All 29 ECs are guarded or accepted as limitations.
- Contract names are identical in §4, §8.5 and §12.3 (scripted count; no variant spellings found).
- 2 CREATE rows equal the §8.4 budget.
- Every §11 command exists: `run_ci.py --stage`, `generate-sdk-public-api.py --check`, `lint/run.py --rule/--all/--format`.
- Each T row names a server-side control.
- All 13 weighted words in request.md §D are mapped.
- Tables: every row has its header's cell count, including the strict GFM pipe check.
- No test cases, and no key-shaped literal.

Not run: the repo gate, lint and tests. S1 writes no code, so the spec does not claim any of them passed.

## Revisions from review round 1

spec.md is now revision 2. Every finding in `reports/S1-spec-review.md` was accepted; none was declined. The spec records the round in §16 (review log, one row per finding) and §17 (r2 row). §0 has no revision log of its own: §0.2 is reserved for the user's verbatim replies, which the orchestrator appends, so I left it unchanged. Settled decisions are unchanged: DIRECT only, and the root names `ReasoningEffort`, `DecisionModelConfig` and `DecisionModelMode`.

| Finding | Disposition | Change in spec r2 |
|---|---|---|
| R-1 [Blocker] | Accepted | INV-8 no longer refuses "a member of another enum". It says a str-valued member whose value is one of the six (for example `GrokReasoningEffort.HIGH`) is accepted by value, as `RecordFieldConverter.to_enum` does (`vidbyte/lib/dataclasses/validation.py:221-230`). AC-10 refuses only `"max"`, `""`, `"HIGH"` and `3`, and lists `GrokReasoningEffort.HIGH` as accepted and stored as the `ReasoningEffort` member. |
| R-2 [Major] | Accepted | NG-14 now gives the true reason, a scope choice. The table covers the exact text ids of `MODEL_PROVIDER_RUNNER_TYPE_MAP` (`vidbyte/lib/constants/runners.py:47`), the catalog `ProviderModelRegistry` publishes (`models.py:316-325`). The prefix map (`utility.py:71`) builds other ids (`claude-opus-4-7`, `gpt-5.5-2026-04-23`, `gemini-3.5-flash-001`), and they get the no-row refusal. The same wording is in EC-10, the §9.2 reading notes, row 2a's WHAT NOT TO DO, row 3's KNOWN EDGE CASES and §13 (which offers these ids as a test seam for the no-row text). |
| R-3 [Major] | Accepted | §8.5 adds a "registry, no row" text: `{provider}:{model} is not in the SDK's reasoning-effort table, so reasoning effort '{effort}' cannot be sent to it; the table was checked against vendor docs on {REASONING_EFFORT_AS_OF} (see "Reasoning Effort Sources" in vidbyte/lib/registries/README.md)`. The capability text ("it supports a, b") is used only for an id with a row, and `REASONING_EFFORT_SUPPORT` never holds an empty tuple, so `()` always means no row. INV-11, AC-4, EC-10, EC-11, EC-23, EC-24, the C5 contract item 4, the §8.5 method comments and rows 3, 4 and 29 follow. EC-24's stale "Q-10" reference is corrected to Q-9. |
| R-4 [Major] | Accepted: follow the convention (option a) | The tables move to `vidbyte/lib/configs/reasoning_effort.py` (new row 2a; it imports only `vidbyte.lib.enums` and `typing`), exported from `vidbyte/lib/configs/__init__.py` (row 2b). `ReasoningEffortRegistry` stays in `vidbyte/lib/registries/reasoning_effort.py` (row 3), imports and re-exports the tables like `registries/structured_output.py`, and is exported from `registries/__init__.py` (row 3a). D-17 cites `declarative-config-resolution.md:38-43`, and r1's choice becomes its runner-up. Also updated: §2, §8.2, §8.4 (3 new files), §8.5, §9.3, §11 (field-guide bullet, baseline, layout), §12.2 (new configs row), §12.4, §12.5, §12.6 P1 order, §14 ask-first and rows 29 and 32. §11 and §13 name `test_harness_threads_surface.py:270-278` as an inherited local red that skips without `origin/main` (`:139-143`). Row ids 2a, 2b and 3a keep every existing row number stable. |
| R-5 [Minor] | Accepted | AC-5 says that, for `TextModelConfig` only, GLM, Meta or a custom `endpoint` keeps the earlier refusal from `_require_gateway_shape` (`model_configs.py:95-96`, `:193-208`). That refusal is `UnsupportedProviderError` or the endpoint `ConfigurationError`, and both name `TextModelMode.DIRECT`. |
| R-6 [Minor] | Accepted, and widened | GL-20 and GL-21 are requoted as their verbatim `description:` lines (raw lines 718 and 727), with the YAML path moved to an `(at ...)` locator. XA-29 is requoted with the raw spacing, `"description":"Assistant reasoning content."`, with its JSON path as a locator. The stricter verifier also caught GL-18, which the review did not list: it quoted a folded YAML scalar as one line. GL-18 is now its verbatim last line, with a locator. The catalog intro documents the locator, the HTML page-text rule and the `\| cell \| cell` row form. |
| R-7 [Minor] | Accepted | A-6 is resolved by the new quote G103 (raw `gem_discovery.json` line 6343: the `ThinkingConfig.thinkingLevel` enum, upper case) with G4, G64, G65 and G5. A-7 is resolved by DS-37 plus a raw-HTML check: `reasoning_effort` sits at the same request-schema depth (26) as `model`, `max_tokens` and `temperature`, while object fields such as `thinking` sit at 28. A-8 is resolved as a code fact: `broker.py:168-174` → `base.py:1534-1537`, where `_call_with_supported_kwargs` (`:1694-1711`) drops the `model_name` that `TextModelRunner.arun` (`text.py:69`) does not take. A-4 is resolved for `grok-4.7` by the new quote XA-38 (the legacy chat-completions page's `model="grok-4.7",` example, raw line 51), which is added to that row's sources. A-4 stays open for `grok-4.6` only. A-9 now cites the skip mechanism. |
| Q-1 [scope-adding] | Kept as an optional question, default No | Added as spec Q-10 (non-blocking, default No): sourced rows for `claude-opus-4-7`, `claude-opus-4-6`, `claude-opus-4-5-20251101` and `claude-sonnet-4-6`, and snapshot-to-alias mapping. Until Q-10 is answered, these ids are a stated limitation (NG-14, EC-10). |

Also fixed while re-reading (not review findings):
- Row 8 said no adapter overrides `_create_payload`. It now says `OpenRouterProvider` overrides it but calls `super()` first (`openrouter.py:56`).
- NFR-4 now places the per-provider URL comments in the table module.
- The §12.5 "D-20" reference is qualified as byok-api-keys D-20, the decision the pinned layout tests cite.

r2 verifier result (scripts under `scratchpad/r2e-s1/scripts/`):
- The strict `s1-verify-spec.py` (no JSON re-serialization, no flattened YAML, no whitespace normalization outside HTML; optional locator) checked 224 catalog lines (218 quotes, 6 absence checks) with 0 failures.
- A mutation run planted 4 defects (flattened GL-20, re-spaced XA-29, XA-38 and GL-21), and the verifier caught all 4.
- `s1-crosscheck-table.py`: 0 rows with an unproven sent value.
- `s1-table-shape.py`: 0 rows with a wrong cell count.
- New `s1-trace.py`: 0 problems.
  - Counts: FR 12, NFR 7, AC 20, EC 29, W 10, INV 19, D 18, Q 10, A 13, NG 15.
  - Every referenced id is defined. Every FR has a §12.3 row, and every AC is in a W row.
  - 37 §12.3 rows. 3 CREATE rows (2a, 3, 11) equal the §8.4 budget.
  - Every "row N" reference resolves, and no retired text survives outside the review log.
- A key-shaped literal scan found none.

## Revisions from review round 2

spec.md is now revision 3, with `status: approved`, per the coordinator: the two review rounds are the approval. The review is `reports/S1-spec-review-r2.md`, and it marks the round-1 findings CLOSED. All five round-2 findings and both nits are accepted; none is declined. §16 records them as round 2, and §17 has the r3 row. Settled decisions are unchanged: DIRECT only, and the root names `ReasoningEffort`, `DecisionModelConfig` and `DecisionModelMode`.

| Finding | Disposition | Change in spec r3 |
|---|---|---|
| R-1 [Blocker] | Accepted | Row 2b puts the configs import before `structured_output`, one name per line. Row 10's validation import names are sorted and wrapped. Row 4 and row 3a state their order. Row 3a also notes that `registries/__init__.py` already carries one I001 at base (`actors` last), so the new line adds none. §12.4 adds this obligation: a whole-tree run of `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, filtered to the touched paths, lists no file that is I001-clean at base. S051 is 259/259 (`lint/baseline.json:79`, `lint/README.md:130`). The obligation names the field-guide trap (`local-ci-verification.md:38`). |
| R-2 [Major] | Accepted: do not import | Row 3(b) imports three names, not four, and says why: no method uses `GEMINI_THINKING_BUDGET_OFF`, and an unused import is an F401 finding. The §8.5 comment is updated. §12.4 adds "No added import is unused; S001 stays at 56". |
| R-3 [Major] | Accepted | AC-4 and C5 item 4 choose the capability text only when the id's §9.2 line has a "sent" cell. Otherwise they choose the no-row text. The `o1`… line and the `gemini-2.5-pro` line are relabelled "refused (all; …)", and the reading note says every line with no "sent" cell is so marked. New INV-20 states the exact `REASONING_EFFORT_SUPPORT` contents and what `supported` returns. Rows 2a(d) and §12.4 cite INV-20. |
| R-4 [Minor] | Accepted | New P6 row 29a (`REPO_MAP.md:185-187`) replaces the stale configs sentence with a general-intent one, with no file names (`agents-md-map.md:3`). New row 29b names `ReasoningEffortRegistry` in `vidbyte/lib/README.md:40`, following #1183 and #1159. §12.6 P6 lists rows 29, 29a, 29b and 30–34. Neither row is a new file. |
| R-5 [Minor] | Accepted | A-4 now covers `grok-4.6` and `grok-4.5`. It says plainly that their "sent" cells rest on it, and that `grok-4.5` is the SDK default (`models.py:77`). A note under the xAI table says the same. A new quote, XA-39 (grok-4.6's Responses row on the reasoning page), sits beside XA-8. |
| Nit: AC-10 | Accepted | AC-10 reads `got <repr>.`, with `got 'max'.` as the example, matching §8.5. |
| Nit: `:309` mechanism | Accepted | §11, §13 and A-9 name both mechanisms: `merge_base()` (`:139-143`) for `:270-278`, and `optional_merge_base()` (`:131-137`) for `:309`. A-9 cites `ci.yml:27,48` (no `fetch-depth`). |

How I checked R-1 independently:
- I ran `py -3.11 -m ruff check --config lint/ruff.toml --select I001 --no-cache` on throwaway scratch copies (since deleted).
- `configs/__init__.py` with the new import before `structured_output` passes; after it, I001.
- Row 10's sorted names on one line fail at 89 columns, and `--diff` wants them wrapped. The registry's three-name import wraps the same way.
- That is why §12.4 states the rule as "wrapped as ruff writes it" and does not prescribe hand-written lines.

r3 verifier result:
- `s1-verify-spec.py` (strict): 225 catalog lines (219 quotes, 6 absence checks), 0 failures.
- `s1-crosscheck-table.py`: 0 unproven sent values.
- `s1-table-shape.py`: 0 bad rows.
- `s1-trace.py`: 0 problems.
  - Counts: FR 12, NFR 7, AC 20, EC 29, W 10, INV 20, D 18, Q 10, A 13, NG 15.
  - 39 §12.3 rows. 3 CREATE rows (2a, 3, 11) equal the §8.4 budget.
- A separate scan of all 53 §9.2 model lines found no line without a "sent" cell that is not marked "refused (all)" (INV-20).
