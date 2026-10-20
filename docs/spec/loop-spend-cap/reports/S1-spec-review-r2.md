VERDICT: SOUND WITH FIXES — all ten round-1 findings (R-1..R-10) are closed in the r2 text and hold against the code, and runs with no cap keep the same behavior. One Major remains: a documentation obligation that §12 omits. Four Minors, each one sentence or one row, remove a wrong "if and only if", a test-fixture trap, a misstated red window, and a goal that contradicts INV-23.

WHAT THE SPEC GETS RIGHT (max 4 bullets, concrete, so the author does not "fix" what works)

- **The construction refusal (R-3) is exact, not a guess.** `AgentSpendCap.model_refusal` reads the same facts that `Runner.build` and the tracker use: `resolve_runner_type` (`vidbyte/lib/runners/utility.py:54-70`), and `ModelPricingRegistry.default().resolve` (`tracker.py:58-60`, `:97`). It walks the chain that is fixed at construction (`base.py:192-203`, `fallback.py:132-142`). A probe through the public constructor classified every case as §8.5 says: the primary, fallbacks, slugs, the OpenRouter exemption, image runners, a provider with no model, and no model at all. The run-time blind stop remains as the backstop, which it needs (D-5).
- **Row 25 reuses the existing Codex refusal, with no special case.** `CODEX_UNSUPPORTED_LOOP_FIELDS` (`vidbyte/lib/constants/codex.py:336-349`) is read by `CodexContractValidator` (`contracts.py:82-89`). `CodexHarnessAgent` is not a `BaseAgent` (`codex/agent.py:55`), so no BaseAgent refusal can fire first. The probe produced exactly the error shape that §9.2 promises.
- **The INV-23 coverage (R-2) is complete and correctly bounded.** Rows 18–24 cover every `MIDDLEWARE_ABORT` run-ending site in `vidbyte/` (see VERIFIED CLAIMS), and add the InfiniteMemory verifier that round 1 missed. Leaving `finalize` untouched is correct, because `orchestrator.py:173-175` already raises for every stop outside `OUTPUT_DELIVERABLE_STOP_REASONS`.
- **The drain fix (R-7) puts its check in the `while` condition (`base.py:1195`).** It reuses the existing truncation code (`:1203-1205`) and does not touch `_generate_reply`, which ruff measures at C901 10 of 10.

FINDINGS (ranked, most severe first, max 15)

R-1 [Major] [L8] §12.3/§12.5 — §12 omits `skills/agentic-loop-settings/SKILL.md`, the repo's ground-truth list of every `AgentLoopSettings` parameter and stop reason, which the repo's skill-update rule says to change
  Evidence:
  - The spec adds an `AgentLoopSettings` parameter and a new stop reason (rows 2 and 3).
  - §12.3 rows 13–17 and §12.5 list `vidbyte/agents/README.md`, `llms.txt`, `skills/failure/vocabulary.md`, the release record, and the Jev README. They do not list this skill. §12.1 (`spec.md:778`) lists only `skills/failure/` among the skill folders.
  - Repo side:
    - `skills/agentic-loop-settings/SKILL.md:4-8` describes the file as the "Ground-truth reference for all agentic loop settings… Documents every parameter available on AgentLoopSettings".
    - Its parameter table is at §3.1 (`:86-96`), its validation table at §4 (`:164-178`), and its stop-reason table, "one of:", at §5 (`:182-199`). Its §6 (`:226`) lists the fields left out of the model's context window.
    - `skills/sdk/update-skill-files.md:3` says: "When you change the Vidbyte SDK repository, you must update the corresponding skill files". Both neighbouring change types list this file: Tool Settings (`:92`, "stop reasons if budgets change") and Output Contracts (`:118`).
    - `skills/output-contracts/SKILL.md:58` routes "Cost *ceilings* that abort the run" only to `CostBudgetMiddleware`.
  - `git grep` finds no lint rule or test that reads these files, so no gate catches the omission. That is why this is Major rather than Blocker. The file is also already stale: `:158` lists `timeout_seconds` as "Reserved (Not Yet Enforced)", but `runtime.py:2084` enforces it.
  Failure: An implementer who follows §12 exactly ships a new loop parameter and a new `stop_reason`. The skill that agents and developers read as the complete list then omits both, and the routing table still sends cost ceilings only to `CostBudgetMiddleware`. A reviewer who applies `update-skill-files.md` raises a convention comment.
  Smallest fix: Add §12.3 row 27 (P4, MODIFY, human doc). Governing standard: `skills/sdk/update-skill-files.md:3`, `:92`. Serves FR-10 and W-9. Add `skills/agentic-loop-settings/` and `skills/output-contracts/` to §12.1 and one bullet to §12.5. Row 27 changes `skills/agentic-loop-settings/SKILL.md` as follows:
  - (a) Add a §3.1 row after `max_tool_calls` (`:94`): `max_spend_usd` | `float \| None` | `None` | Optional USD cap on one reply's measured spend. The loop checks it before every model call, tool call, finish attempt, and compute checkpoint, and stops with `stop_reason=max_spend`. It is a threshold, not a maximum bill. See `vidbyte/agents/README.md` "Spend Cap".
  - (b) Add a §4 row: `max_spend_usd` is not a finite number greater than 0 → `AgentLoopSettings.max_spend_usd must be a finite number greater than 0…`.
  - (c) Add a §5 row: `"max_spend"` | `max_spend_usd` reached, or a capped run's spend could not be measured.
  - (d) Add `max_spend_usd` to the §6 exclusion list (`:226`), because row 5(g) keeps it out of the context window.

  In `skills/output-contracts/SKILL.md:58`, change the right-hand cell to "`AgentLoopSettings.max_spend_usd` (measured spend), or `CostBudgetMiddleware`".

R-2 [Minor] [L9] §9.2 rule 1 — "if and only if" is false for a MultiAgent, which the spec's own row 23 makes raise for a cap stop
  Evidence:
  - Rule 1 (`spec.md:579-582`) says: "The cap stopped the run if and only if either" one of two things happened: a reply whose `stop_reason` is `"max_spend"`, or an `OutputSchemaViolationError`.
  - Row 23 raises `MultiAgentExecutionError(…, details={…, "stop_reason": "max_spend"})` from `_structured_phase`.
  - The unchanged `finalize` raises `MultiAgentExecutionError(…, details={"phase": "finalize", "stop_reason": stop_reason})` for a capped synthesis (`orchestrator.py:175`).
  - Probe: `'MultiAgentExecutionError' in vidbyte.__all__` printed True, and `.details` carries `stop_reason`.
  Failure: C3 applies rule 1 to a capped MultiAgent run that the cap stopped. It finds neither condition, so it reports the stop as a generic failure, and the "if and only if" in rule 1 promises that this report is correct.
  Smallest fix: Add a third bullet to rule 1: "for a `MultiAgent`, the call raised `MultiAgentExecutionError` with `exc.details.get("stop_reason") == "max_spend"` (row 23; `orchestrator.py:175`)". Add `MultiAgentExecutionError` to the list of root names in the contract preamble.

R-3 [Minor] [L10] §13 — the default test-agent builder uses an unpriced model, so a capped fixture built the usual way is refused at construction
  Evidence:
  - `tests/agent_test_support.py:70-71` calls `setdefault("provider", "openai")` and `setdefault("model_name", "gpt-4.1-mini")`.
  - Probe: `ModelPricingRegistry.default().resolve(ModelProvider.OPENAI, "gpt-4.1-mini") is not None` printed False, and the same check for `gpt-5.4-mini` printed True.
  - The AC-31 prior art that §13 cites, `tests/test_queued_prompt_usage.py` (`spec.md:880`), builds every agent with `build_test_agent` (for example `:62`, `:76`).
  - §13 (`spec.md:893`) lists the priced models but does not connect them to this default.
  Failure: The blind S2 author copies the AC-31 prior art, adds `agent_loop_settings=AgentLoopSettings(max_spend_usd=…)`, and gets `ConfigurationError` from `__init__` before `bind_test_runner` runs. Every capped linear fixture built this way fails for a reason unrelated to the behavior it means to test.
  Smallest fix: Add one §13 sentence: "`build_test_agent` defaults to `gpt-4.1-mini`, which the pricebook lacks (`tests/agent_test_support.py:70-71`), so a capped fixture must pass `model_name="gpt-5.4-mini"`, or a DeepSeek `deepseek-v4-flash` agent. Its scripted `TextModelResponse` must name a priced model as well."

R-4 [Minor] [L11] §12.6 — the red window and the row-25 dependency are stated backwards
  Evidence:
  - `spec.md:857` says: "Row 26 … lands with the S2 pack, so the codex pin is red only between row 25 and that pack".
  - `spec.md:860` says: "Row 25 needs row 3 and row 26".
  - Row 26 is assigned to "S2 (before P3)", so S2 commits the new `cases` key before row 25 exists. At that point the pin `assertEqual(set(cases), set(CODEX_UNSUPPORTED_LOOP_FIELDS))` (`tests/test_codex_output_contracts.py:411`) fails. The loop at `:412-416` also needs row 2, the new keyword.
  - Row 25 is a constant append, and it needs no code row.
  Failure: An implementer who reads ":860" may look for a code dependency of row 25 that does not exist. An S6 reviewer reading ":857" expects the pin to be green on the S2 commit, but it is red there.
  Smallest fix:
  - Reword `:857` to: "Row 26 lands with the S2 pack, so the codex pin is red from that pack until row 25 (P3), and needs row 2 (P1) to pass."
  - Reword `:860` to: "Row 25 needs no other row. The codex pin goes green only when rows 2, 25, and 26 are all in."

R-5 [Minor] [L9] §2 G-3 — "no component spends again on a run the cap stopped" contradicts INV-23 and EC-33
  Evidence:
  - G-3 (`spec.md:43`) says: "…and no component spends again on a run the cap stopped".
  - INV-23 (`spec.md:269`) says: "The reply then still runs `after_run` middleware and a configured auto-handoff". EC-36 (`:355`) says that spend lands in `get_usage()`.
  - EC-33 (`:352`) says: "The manager may still replan the work onto another worker".
  - `FailureMetadataNormalizer` routes the stop as `EXHAUSTED`/`ROUTE` (`router.py:130-131`, design line `spec.md:125`). A session binding for `resource.exhausted` therefore runs its handler (`router.py:442-456`).
  Failure: A blind test author who writes a test from G-3 asserts that an auto-handoff or `after_run` model call makes no spend after a cap stop. That assertion contradicts INV-23, and the test is red by design.
  Smallest fix: Change G-3's clause to: "…and no SDK component reviews, grades, reflects on, verifies, retries, or drains queued prompts after a run the cap stopped (INV-23). Only the developer's own end-of-run steps (`after_run`, an auto-handoff, or a bound session rule) may still run."

VERIFIED CLAIMS:

Round-1 closures (each checked against the code, not against §16):
- **R-1 (Codex) is closed.**
  - `CODEX_UNSUPPORTED_LOOP_FIELDS` has 12 entries, the last being `"tool_settings"` (`codex.py:336-349`).
  - The validator flags fields that are not None (`contracts.py:63-89`), and `translate_agent` calls it (`codex/config.py:58-66`).
  - `CodexHarnessAgent` wraps the error with `FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value` (`codex/agent.py:65-73`).
  - Probe (`r3-s1-review-r2/codex_probe.py`, using a field that is already refused): `raised CodexAgentError`, `failure_code: codex.vidbyte_translation_failed`, `cause type: ConfigurationError`, `cause text: Codex cannot enforce AgentLoopSettings max_tool_calls: …`.
  - Row 26's target exists: `cases` is at `test_codex_output_contracts.py:397-410` and the pin at `:411`. Row 26 is correctly assigned to S2. Only its wording is off (R-4).
- **R-2 (stops that slip past the run-ending checks) is closed.**
  - `git grep MIDDLEWARE_ABORT -- vidbyte` finds these run-ending sites: `reflexion.py:95`, `independent_critic.py:75`, `prosecutor_defender_judge.py:402`, `multi_provider_agentic_grader.py:65` and `:110`, `transfer.py:188`, and `orchestrator.py:169` and `:209`. Rows 18–23 cover every one except `orchestrator.py:169`, which is `finalize`; its `:173-175` branch already raises for `max_spend`.
  - `tests/multi_agent/test_manager_middleware_abort.py:226-235` runs every stop reason through `finalize`.
  - Row 24 is valid: `InfinitePair._status` (`launch.py:335-344`) feeds the verifier gate (`:250-253`).
  - Row 22 leaves the retryable `worker_stopped` shape that `test_worker_stop_report.py:55-60` pins.
- **R-3 (an unpriced model found only after a paid call) is closed.**
  - Probe (`r3-s1-review-r2/refusal_probe.py`), building agents through `Agent(...)`:
    - `gpt-5.4-mini` and `deepseek-v4-flash`: text, priced.
    - `gpt-image-2`: image runner, so the runner refusal fires first.
    - The slug `deepseek/deepseek-v4-flash` with no provider normalizes to deepseek, priced.
    - `openrouter`: exempt.
    - A fallback `deepseek/not-a-real-model`: unpriced at index 1.
    - Provider `openai` with no model: unpriced, shown as `openai:?`.
    - Neither provider nor model: `resolve_runner_type` raises, so the §8.5 early `None` is required, and the spec has it.
  - A model changed after construction (`paradigm.py:218`, a response that names another model) is caught by the run-time blind stop (D-5, EC-19, AC-25).
  - There are no false refusals for priced or OpenRouter chains.
  - NFR-5 (`base.py` ≤ 25 lines) is feasible: row 6 is about 20 lines.
- **R-4 (usage-less failures and the relay fee) is closed.** INV-3 now lists both, and rule 3 says "measured spend", never "your bill". Q-13 is `[scope-adding]` with default No.
- **R-5 (the C3 contract with root names only) is closed, except for one gap (R-2 above).**
  - `vidbyte.UsageRollup is vidbyte.agents.pricing.records.UsageRollup` is True.
  - `OutputSchemaViolationError` and `CodexAgentError` subclass `AgentExecutionError` and are root names.
  - `UsageAccountingError` is not a root name. Its `error_kind` is `"usage_accounting"` (`lib/errors/base.py:564`), so rule 5 works without a new export.
  - Rules 2–9 can each be applied with only root names.
- **R-6 (concurrent replies on one agent object) is stated honestly.** `reset()` clears the records, the unaccounted count, and the corruption flag (`tracker.py:195-200`). EC-35, T-4, rule 9, and row 13 all state the limitation, and Q-14 is `[scope-adding]` with default No.
- **R-7 (queued prompts after a cap stop) is closed.**
  - The `while` is at `base.py:1195`, and the truncation code at `:1203-1205` sets `queued_prompts_truncated`.
  - `_drain_queued_prompts` measures C901 6, and row 6 keeps it at 6.
  - `_generate_reply` is untouched.
  - EC-20, EC-41, and AC-31 agree with each other.
- **R-8 is closed.** It is now D-18, Q-10 is struck through, and the reviewer sub-runtimes stay uncapped (`independent_critic.py:123-127`, `prosecutor_defender_judge.py:242`).
- **R-9 is closed.** `pricing.py:131-135` rates DeepSeek at its peak rate, with no clock.
- **R-10 is closed.** Validator probe through `RecordFieldValidator.require_number(..., maximum=sys.float_info.max)`:
  - `5` and `0.01` are accepted.
  - `True`, `0`, `-1.0`, `inf`, `nan`, and `'1'` raise `ConfigurationError` with the message §9.2 quotes.
  - `10**400` raises `OverflowError`, as INV-14 now states.

Runs with no cap (the rule is the same behavior, byte for byte):
- `_spend_cap_stop` returns at its first statement when `max_spend_usd is None`. CP3 sits before `if tool_is_internal` (`runtime.py:1836`) but costs nothing when there is no cap.
- `_export_loop_settings` drops values that are None (`base.py:683`), and `__repr__` shows only fields that are not None (`loop.py:210-211`). Checkpoints and repr are therefore unchanged.
- `_export_runtime_config` lists its fields explicitly (`base.py:624-659`), so the new `AgentRuntimeConfig` field does not leak into it. No test pins `AgentRuntimeConfig` fields or its repr.
- The fork tool's `_inherited_guardrails` (`fork.py:334-343`) passes `max_spend_usd=None`, which is the default. It is not in `_LOOP_SETTING_FIELDS`, so no keyword is duplicated.
- Rows 18–24 and the drain test change only for the value `"max_spend"`, which an uncapped run never produces.
- `AgentRuntimeConfig.max_spend_usd` is appended last, so positional construction is unchanged.
- The public contract check passes unchanged: `generate-sdk-public-api.py --check` reports "contracts/sdk-public-api.json is current … (vidbyte-sdk 0.4.0, 733 exports)".

Executability and gates:
- S008 is count-ratcheted: the baseline is 19 (`lint/baseline.json`), and `lint/core/ruff.py` counts C901, PLR0912, and PLR0915 as separate findings for each function.
- Ruff measurements, run with zero thresholds, match every §12 number:
  - `__init__` C901 17, branches 17, statements 87. It is already flagged on all three codes, so growth adds no finding.
  - `_generate_reply` C901 10, `_process_tool_call` 10, and `_arun_once` 45 (already flagged).
  - `_drain_queued_prompts` 6, `_enforce_tool_settings` 6, and `_budget_stop` 5.
  - `_structured_phase` 6, `default_report_parser` 4, and `InfinitePair._status` 3.
  - `AgentRuntimeConfig.__post_init__` 4.
  - After the stated +1 changes, every touched function stays at C901 ≤ 10, branches ≤ 12, and statements ≤ 50.
- All cited code lines exist as stated. These were checked: `base.py:83`, `:91`, `:192`, `:203`, `:243`, `:660-683`, `:907`, `:1060-1076`, `:1116-1118`, and `:1186-1220`; `runtime.py:513`, `:699-700`, `:1834-1836`, and `:2046-2089`; `transfer.py:185-196`; `orchestrator.py:161-179` and `:190-215`; `launch.py:250-253` and `:335-344`; `reflexion.py:87-95`; `jev/agent.py:41` and `:113-125`; and `a001_agent_readable_file_headers.py:24-32`, which lists the seven required header fields.
- Sessions: `"max_spend"` maps to `resource.exhausted` with `EXHAUSTED`/`ROUTE` (`router.py:130-131`). A recovery runs only for an explicit per-code binding (`router.py:442-444`), so no default handler spends after a cap stop.

Scope:
- r2 adds nothing that the findings did not force. Rows 18–24 come from R-2, row 25 from R-1, and row 26 from row 25. Row 1 grew for R-3, and row 6 grew for R-3 and R-7.
- Q-13 and Q-14 are both `[scope-adding]` with default No.
- The settled decisions stand: D-P1, D-P2, D-P6, Q7, and Q2; no new root name; no new `FailureCode`.
