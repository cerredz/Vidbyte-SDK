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
