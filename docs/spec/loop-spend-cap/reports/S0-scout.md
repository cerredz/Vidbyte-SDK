# S0 scout report: loop-spend-cap (R3)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap`, branch `feat/loop-spend-cap`, HEAD `22993b5f`. Run date 2026-10-19.

Outputs:
- the code-map at `docs/spec/loop-spend-cap/context/code-map.md`;
- this report.

I created no other files, made no commits, and ran no installs or gates. The only shell commands were `git grep`, `git log`, `git show`, `ls`, `sed -n`, `wc` and `cat` (read-only).

## 1. Planned file list (step 3, before reading code)

| Group | Files |
|---|---|
| Rules | `AGENTS.md`, `REPO_MAP.md`, the READMEs for the touched folders, field guide `init.md` and its matching entries, `vidbyte-gates.md` |
| Request and release | `docs/spec/loop-spend-cap/request.md`, `docs/design/release-0-4-0.md` (allowed by the briefing) |
| Settings | `vidbyte/agents/settings/loop.py`, `vidbyte/agents/base.py` |
| Runtime | `vidbyte/agents/runtime.py` |
| Pricing | `vidbyte/agents/pricing/` (tracker, records, base, providers), `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/lib/registries/pricing.py`, `vidbyte/lib/registries/models.py` |
| Failure | `vidbyte/lib/enums/failure.py` and the tests that pin it |
| Jev | `vidbyte/agents/jev/` (runtime, usage, response, agent, settings, bulk_work, compute/*) |
| Other | `vidbyte/agents/fork.py`, `vidbyte/agents/contracts/floors.py`, `vidbyte/evals/behavior/stop.py` |
| Contract | `lint/core/public_api_contract.py`, `contracts/README.md`, `contracts/sdk-public-api.json` |
| Tests | `tests/features/` packs covering `max_tokens` and `max_tool_calls` |

I confirmed each entry with `git grep` or `ls` before reading it.

## 2. Files actually read (in full unless a range is given)

**Rules and context**
- `AGENTS.md`, `REPO_MAP.md`
- `vidbyte/agents/README.md`, `vidbyte/agents/jev/README.md`, `vidbyte/lib/README.md`
- `docs/spec/loop-spend-cap/request.md`, `docs/design/release-0-4-0.md`
- field guide: `init.md`, `local-ci-verification.md`, `runtime-boundaries.md`, `strict-config-dataclasses.md`, `operation-pricebook-rates.md`, `blocking-lint-invariants.md`, `comment-format.md`, `jev-capability-layout.md`
- `vidbyte-gates.md`
- `skills/failure/vocabulary.md`

**Settings and config**
- `vidbyte/agents/settings/loop.py`
- `vidbyte/lib/dataclasses/agents.py`
- `vidbyte/lib/dataclasses/config.py`
- `vidbyte/lib/config/loader.py`
- `vidbyte/agents/jev/settings.py`

**Runtime and agents**
- `vidbyte/agents/runtime.py`
- `vidbyte/agents/base.py`
- `vidbyte/agents/fork.py`
- `vidbyte/tools/builtins/fork/fork.py`
- `vidbyte/lib/registries/runtimes.py` (registry block)
- `vidbyte/agents/multi/agent.py` (:100-140), `vidbyte/agents/aggregation.py` (ledger and stop-reason ranges)

**Pricing and ledger**
- `vidbyte/agents/pricing/tracker.py`, `records.py`, `base.py`, `anthropic.py`, `openrouter.py`, `typesafe.py`
- `vidbyte/lib/dataclasses/sessions.py`
- `vidbyte/sessions/usage.py`
- `vidbyte/lib/registries/pricing.py`, `vidbyte/lib/registries/models.py`
- `vidbyte/lib/enums/model_provider.py`
- `vidbyte/lib/runners/text.py` (header)
- `vidbyte/lib/usage_ledger.py`
- `vidbyte/lib/runners/decision.py`
- `vidbyte/lib/enums/usage.py`
- `vidbyte/lib/constants/pricing.py`, `vidbyte/lib/constants/failure.py`, `vidbyte/lib/constants/outputs.py`

**Jev**
- `vidbyte/agents/jev/runtime.py`, `usage.py`, `response.py`, `agent.py`, `bulk_work.py`
- `compute/clone.py`, `compute/swarm.py`, `compute/swarm_tool.py`, `compute/controller.py`
- the `AgentLoopSettings` lines in `brief/writer.py`, `done/handoff.py`, `done/reviewer.py`, `done/run_state.py`, `gate/clarification.py`, `infinite/agent.py`, `infinite/launch.py`
- `vidbyte/lib/dataclasses/jev.py`: `JevUsageReport` and `JevAgentResponse` ranges only. The file is 4,694 lines and was not read in full.

**Middleware and contracts**
- `vidbyte/middleware/builtins/cost_budget.py`, `limit_validation.py`, `runtime_limits.py`, `token_budget.py`
- `vidbyte/lib/dataclasses/middleware.py`
- `vidbyte/agents/contracts/floors.py`
- `vidbyte/lib/dataclasses/context.py` (:40-70)

**Failure and evals**
- `vidbyte/sessions/failure/router.py`
- `vidbyte/lib/enums/failure.py`
- `vidbyte/lib/errors/base.py` (`ConfigurationError` and `UsageAccountingError` ranges)
- `vidbyte/evals/behavior/efficiency.py`, `vidbyte/evals/behavior/stop.py`

**Lint, contract and CI**
- `lint/rules/a007_operational_constants.py`, `c009_default_model_priced.py` (rule core), `c011_agent_owned_usage_and_sync_twins.py` (rule core), `c019_platform_error_code_contract.py` (header)
- `lint/core/public_api_contract.py`
- `contracts/README.md`, `contracts/sdk-public-api.json` (by grep for the relevant names)
- `scripts/run_ci.py`, `pyproject.toml` (pytest section)

**Tests**
- `tests/features/sdk_loop_settings/` (all 3 files)
- `tests/features/sdk_model_usage/test_nested_usage_bill.py`, `test_usage_contract.py`, `FEATURE.md`
- `tests/test_agent_runtime.py`
- `tests/test_jev_usage_ledger.py`
- `tests/agent_test_support.py` (:55-75)
- `tests/test_session_failures.py` (failure ranges)
- `tests/test_fork_tool.py` (:300-390)
- `tests/features/harness_threads/test_harness_threads_surface.py` (:60-80, :210-245)
- `tests/features/codex_host/` pins (ranges), `tests/test_codex_failure_recovery.py` (:280-292)
- `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py`
- `tests/test_new_middleware_builtins.py` (:371-479)
- `tests/features/sdk_middleware_limits/` (FEATURE.md and contract)
- `scripts/test-agent-loop-settings.py`

A second pass over this list added nothing new. So the "stop when a full pass adds nothing" condition holds.

## 3. What the GUESS list got wrong

GUESS: `loop.py, runtime.py, base.py, agents/pricing/, lib/dataclasses/sessions.py, lib/registries/pricing.py, lib/enums/failure.py, agents/jev/, agents/fork.py, tests/features/`

**Wrong or misleading entries**
- `vidbyte/lib/dataclasses/sessions.py` is the wrong `UsageRollup`. The live, root-exported run rollup is `vidbyte/agents/pricing/records.py:68-89` (`cost_usd`, `cost_complete`, no `per_agent`). The sessions class (`:126-140`) is built after the run from session history with flat caller prices (`vidbyte/sessions/usage.py:27-41`, `:82-91`). The request (`:46`, `:58`) and the briefing (§3.2-3.3) both name the sessions class.
- `vidbyte/agents/pricing/` and `vidbyte/lib/registries/pricing.py` are read-only neighbours. They are where "what was spent" comes from, but nothing in them needs to change for a cap.
- `vidbyte/lib/enums/failure.py` changes only if the spec adds a code, and any new member trips the harness_threads pin (code-map §4.3). The stop_reason → FailureCode mapping lives in `vidbyte/sessions/failure/router.py:36-51`, which GUESS omitted.
- `vidbyte/agents/jev/` is a neighbour only. Jev receives `settings.loop` unchanged, and `jev/runtime.py` enforces no loop budget; it only grows finite limits at `:260-275`.
- `vidbyte/agents/fork.py` enforces nothing. It copies loop fields from an explicit list (`:157-173`), so its only role is the silent-drop risk.
- `AgentStopReason` and `AgentRuntimeConfig` are defined in `vidbyte/lib/dataclasses/agents.py`, which GUESS did not name.

**Files GUESS missed**
- Settings and config:
  - `vidbyte/lib/dataclasses/agents.py` (`AgentRuntimeConfig`, `AgentStopReason`);
  - `vidbyte/lib/dataclasses/config.py` (`_LOOP_FIELDS` `:92-98`: without the new key, YAML rejects it);
  - `vidbyte/lib/config/loader.py` (passes keys through, no edit).
- Field-drop risk: `vidbyte/tools/builtins/fork/fork.py` (`_LOOP_SETTING_FIELDS`, `_inherited_guardrails`, the `additionalProperties: False` schema). Touching it also triggers the field guide's local harness_threads red.
- Stop-reason consumers:
  - `vidbyte/sessions/failure/router.py`;
  - `vidbyte/evals/behavior/efficiency.py` (`_BUDGET_STOP_REASONS`);
  - `vidbyte/lib/constants/outputs.py` (a consumer, not an edit).
- Existing USD features that overlap:
  - `vidbyte/middleware/builtins/cost_budget.py`;
  - `vidbyte/agents/contracts/floors.py` (`MinCostSpent`);
  - the `cost_spent_usd` counter at `runtime.py:2146`.
- Ledger path: `vidbyte/lib/usage_ledger.py`, `vidbyte/lib/runners/decision.py`.
- Records: `docs/design/release-0-4-0.md`; `contracts/sdk-public-api.json` (only if a root name is added); `skills/failure/vocabulary.md` (human catalogue, not test-enforced).
- Tests:
  - `tests/test_session_failures.py` (exact details-dict pin `:430-435`);
  - `tests/test_agent_runtime.py`;
  - `tests/test_fork_tool.py`;
  - `tests/test_jev_usage_ledger.py`;
  - the feature packs `tests/features/sdk_loop_settings/` and `tests/features/sdk_model_usage/`.

## 4. What vidbyte-gates.md (and nearby workspace notes) got wrong or left out

- It writes every command with `python`. In this workspace the interpreter is `py -3.11`, never bare `python` (briefing §2). AGENTS.md itself also says `python scripts/run_ci.py`.
- It gives `python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py`. It leaves out the worktree nuance in the field guide (`local-ci-verification.md:5`): inline `PYTHONPATH=$(pwd)` on the source stage only, and the package stage without it. The memory index says "never export PYTHONPATH before SDK run_ci.py". These two notes conflict, and I did not determine which one is right.
- It leaves out that semgrep scans tracked files only, so `git add -A` must run before the local gate (`local-ci-verification.md:10-14`).
- It leaves out the pre-existing local red: branch-scoped harness_threads tests fail on any branch that touches `vidbyte/tools` (`local-ci-verification.md:45-49`). This branch will touch it if the fork tool's field lists change.
- Stale field-guide entry: the `assert 167 == 120` note (`local-ci-verification.md:66-71`, under the old `_28_harness_codes` name) no longer matches the test. The test is now `test_failure_codes_keep_main_and_append_exactly_the_32_harness_codes` (`test_harness_threads_surface.py:218-241`) and pins exact membership, not a count.
- AGENTS.md states no install, lint or test command and no commit or PR convention. Every such command in the code-map is attributed to its real source (vidbyte-gates.md, the field guide, `contracts/README.md`, or `FEATURE.md`).

## 5. Unverified items carried into the code-map

- Whether a gateway (`TextModelMode.AUTO`) charge equals the SDK pricebook rate.
- The CLI's default model per provider (`request.md:191`). Only the SDK defaults were checked, and all 7 are priced.
- Whether lint C019 flags a new stop-reason literal.
- Whether `scripts/test-agent-loop-settings.py` still passes (it is not run in CI).
- Which PYTHONPATH rule applies to the local gate.
- Whether `ContextBudget.max_cost_usd` (`vidbyte/lib/dataclasses/context.py:58`) has a reader. A grep found none outside the paradigm's own same-named field.
