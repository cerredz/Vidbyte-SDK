# Code map: loop-spend-cap (R3)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap`, branch `feat/loop-spend-cap`, HEAD `22993b5f` (R1 #1190 merged). Scout run 2026-10-19.

Every `path:line` below was opened at this HEAD. "Inference:" marks a conclusion drawn from code I read, not something I ran. "unverified:" marks something I could not confirm. Nothing here is a design decision.

---

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### 1.1 Rules (quoted, with their AGENTS.md heading)

**Repository Map**
- "**Do not grep, glob, or read files under `docs/` as part of ordinary work:** those design documents are large and not kept in sync with the implementation, so treat the folder as opaque unless a human names a specific document and asks you to read it." The orchestrator named only `docs/spec/loop-spend-cap/request.md` and `docs/design/release-0-4-0.md`.
- "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder. Its closing `## Notes for agents` section, where one exists, records mistakes that review has already caught there". Finding: no folder this change touches has a `## Notes for agents` section. Only `vidbyte/agents/coding_context/`, `vidbyte/agents/infinite/` and `vidbyte/agents/skills/` READMEs have one. `vidbyte/agents/README.md` (407 lines), `vidbyte/agents/jev/README.md` (55) and `vidbyte/lib/README.md` (56) have none. `vidbyte/agents/settings/`, `vidbyte/agents/pricing/`, `vidbyte/sessions/failure/`, `vidbyte/lib/dataclasses/`, `vidbyte/lib/enums/`, `vidbyte/lib/constants/` and `vidbyte/tools/builtins/fork/` have no README at all.
- "lint rule A009 keeps every folder README at or under 40,000 characters".
- "The map ... Read it before you create a file, move code, or search for where something lives". REPO_MAP.md lines that bind this change:
  - `REPO_MAP.md:109` (`vidbyte/agents/settings/`): "A new configurable behavior for agents should be added as a setting here rather than as another constructor parameter."
  - `REPO_MAP.md:81` (agent contracts): "Anyone adding a new class of agent configuration should consider whether it needs a floor defined here."
  - `REPO_MAP.md:191` (`vidbyte/lib/constants/`): "if a literal value would otherwise need to appear in two places, it belongs here instead."
  - `REPO_MAP.md:199` (`vidbyte/lib/enums/`): "Extending an existing enumeration is treated as an interface change with its own weight, since code elsewhere may be matching against it exhaustively."
  - `REPO_MAP.md:203` (`vidbyte/lib/errors/`): "A new failure mode should usually reuse an existing error type with a clear message rather than growing the hierarchy."

**General Coding Style Guidelines**
- 1. Keep Call Chains One Level Deep: "a function may call another of its own functions, but that second function should not call a third."
- 2. Narrate Main Functions in Plain English: "When you change the steps of a main function, update its comments in the same edit so they never describe behavior that is gone." `AgentRuntime._arun_once` (`vidbyte/agents/runtime.py:297`) is narrated this way.
- 3. Build in Layers: "nothing in `vidbyte/lib/` may import from a layer above it." And: "Keep files well below 1,000 lines; when a file heads toward four digits, split it into smaller modules along subsystem lines before adding more." **This bites:** `vidbyte/agents/runtime.py` is 2,304 lines, `vidbyte/agents/base.py` 1,830, and `vidbyte/lib/dataclasses/jev.py` 4,694.
- 4. Use Validated Dataclasses: "Each dataclass validates itself strictly when it is created, in `__post_init__` ... raises a clear error that names the field and the bad value." "Prefer `@dataclass(frozen=True, slots=True)`". "type any field whose value comes from a small, closed set as an enum."
- 5. Write Shared Logic Once, as a Canonical Helper in `lib/`: "Before you write logic like this, look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it rather than copying it".

**Placement Rules**
- "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`**". Exception 1: "**Agent settings objects.** A `*Settings` class that configures an agent lives in `vidbyte/agents/settings/`". `AgentLoopSettings` is there (`vidbyte/agents/settings/loop.py:46`).
- "**Every new enum ... is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
- Existing code: "Many modules on `main` still define dataclasses or enums outside these two folders; they predate these rules. Do not copy them as precedent. Editing one in place (adding a field or a member) is fine." This covers `AgentStopReason`, an enum defined in a dataclasses module (`vidbyte/lib/dataclasses/agents.py:61-80`), and `AgentRuntimeConfig` (`:126-152`).
- New JEV code: "**A new JevAgent capability** is a named, validated field on `JevAgentSettings`." This applies only if the spec makes something Jev-specific. The request says the cap "must not be a JevAgent-only feature" (`request.md:51`).

### 1.2 Commands

AGENTS.md states exactly one command: the full gate `python scripts/run_ci.py`. It states **no** install, lint, single-file test, or area test command. The commands below come from other sources, each named:

| Purpose | Command | Source |
|---|---|---|
| Full gate | `python scripts/run_ci.py` | AGENTS.md. Workspace rule: run Python as `py -3.11`, never bare `python`. |
| Source stage in a worktree | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | field guide `local-ci-verification.md:5` |
| Package stage | `python scripts/run_ci.py --stage package` with no `PYTHONPATH` | field guide `local-ci-verification.md:5` |
| What the source stage runs | no tracked bytecode; `lint/run.py`; `compileall`; 3 check scripts; `python -m pytest` | `scripts/run_ci.py:79-93` |
| Install (once) | `python -m pip install -e ".[dev]"` | `vidbyte-gates.md` (not AGENTS.md) |
| Lint, all / one rule | `python lint/run.py` / `python lint/run.py --rule <ID>` | `vidbyte-gates.md`; `lint/rules/a007_operational_constants.py:11` |
| One test file | `python -m pytest -q <file>`; in a worktree, `PYTHONPATH=$(pwd) python -m pytest -q <file>` | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py:11` |
| One area | `python -m pytest -q tests/features/sdk_loop_settings` | `tests/features/sdk_loop_settings/FEATURE.md:45` |
| All tests | `python -m pytest` (testpaths `tests`) | `scripts/run_ci.py:93`; `pyproject.toml:78-81` |
| Public API contract | `python scripts/generate-sdk-public-api.py --check`, then the same command without `--check`, run after the source commit | `contracts/README.md` "Regenerating" |
| Semgrep (tracked files only) | `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (`semgrep==1.170.1`) | field guide `local-ci-verification.md:12` |

Conflict to resolve outside this map: the workspace memory index says "never export PYTHONPATH before SDK run_ci.py", while the field guide (`local-ci-verification.md:5`) puts an inline `PYTHONPATH=$(pwd)` on the source stage only. unverified: which of these the orchestrator wants.

### 1.3 PR and commit conventions

AGENTS.md gives no commit-message or PR-body format. It says only that "the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code" and that "The `@claude` review workflow appends to those notes after every review." The run's own conventions come from `request.md`, not AGENTS.md:
- `:62` "Do not change the version number ... Record the change in `docs/design/release-0-4-0.md`."
- `:63` "update it with the repo's own generator, never by hand."
- `:75` the orchestrator squash-merges with `--admin`.

---

## 2. Files this change will touch

Each entry gives: what the file does today, what the request implies will change, and the pattern to follow. "Touched only if" marks a file whose change depends on a spec choice.

### 2A. The setting itself

**`vidbyte/agents/settings/loop.py`** (235 lines)
- Today: `AgentLoopSettings` is a *plain mutable class*, not a dataclass (`:10` "Plain class with __init__-level validation"; `:46`). Its constructor is keyword-only (`:49-67`). It stores every field, then calls `_validate()` (`:86`, `:93-100`), which raises `ConfigurationError`. `to_runtime_config()` (`:195-208`) copies an explicit subset of fields into `AgentRuntimeConfig`. `__repr__` (`:210-235`) lists fields by name.
- Will change: the request adds an optional USD cap field (`request.md:40`). It must also flow through `to_runtime_config()` and `__repr__`. Both list fields explicitly, so a new field is invisible to them until it is added.
- Pattern for a finite positive number (`:112-118`):
  ```python
  value = self.timeout_seconds
  if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0):
      raise ConfigurationError(f"AgentLoopSettings.timeout_seconds must be a finite positive number when provided, got {value!r}.")
  ```
  Integer budgets use `_POSITIVE_INT_FIELDS` (`:32-43`) and `_validate_positive_int_fields` (`:102-110`, with `@intent invalid-budgets-never-disable-loop-guards`). Floors are checked against ceilings in `_validate_contract_ceiling` (`:152-173`) through `contract.ceiling_key`.

**`vidbyte/lib/dataclasses/agents.py`** (478 lines)
- Today: `AgentRuntimeConfig` (`:126-152`) is frozen and slotted, with fields at `:130-137`. Its `__post_init__` (`:139-152`) raises **`ValueError`**, not `ConfigurationError`, on values `<= 0`. `AgentStopReason(str, Enum)` (`:61-80`) has 17 members. `MAX_TOKENS = "max_tokens"` is at `:67`. `AgentRuntimeStats` is at `:187-194`.
- Will change: `AgentRuntimeConfig` gains the runtime copy of the cap. A new `AgentStopReason` member is added only if the spec chooses a distinct stop reason. Editing in place is allowed (§1.1).
- Pattern: append the field after `allowed_tools` (`:137`) and add it to the `__post_init__` loop or as its own check (`:141-152`).

### 2B. Enforcement in the shared runtime

**`vidbyte/agents/runtime.py`** (2,304 lines, already over the 1,000-line rule)
- Today: `AgentRuntime` is the linear loop shared by `LINEAR`, `JEV` and `INFINITE_MEMORY` (`vidbyte/agents/base.py:83`). `self.config` is set at `:199` and `self.usage_tracker` at `:212`. Each `_arun_once` (`:297`) builds a fresh `BaseAgentRuntimeLoopState` (`:300`), so `tokens_used` is per attempt.
- Every loop-budget enforcement point today:

| Budget | Where checked | How it stops | stop_reason | FailureCode (mapped later, `vidbyte/sessions/failure/router.py:36-51`) |
|---|---|---|---|---|
| `max_iterations` | `_budget_stop` `:2055`, called at the top of each iteration `:367-374` | `_stopped_result` `:2091-2109` → `_finish_result` | `max_iterations` | `RUNTIME_MAX_ITERATIONS` `:37` |
| `max_tokens` | `_budget_stop` `:2063` (top of iteration), and the final-answer path with no tool calls `:513-522` | same. The text output is replaced by `"Agent runtime stopped after reaching max_tokens."` (`:516`) | `max_tokens` | `RUNTIME_MAX_TOKENS` `:38` |
| `max_tool_calls` | `_budget_stop` `:2073`, and mid-iteration before each non-internal call `_tool_settings_budget_stop` `:1862-1870` via `_enforce_tool_settings` `:1834-1841` | same | `max_tool_calls` | `RUNTIME_MAX_TOOL_CALLS` `:39` |
| `timeout_seconds` | `_budget_stop` `:2081` only (top of iteration) | same | `timeout` | `RUNTIME_TIMEOUT` `:47` |
| ToolSettings hard budgets | `_tool_settings_hard_budget_stop` `:1872-1876`, reason map `:1879-1888` | same, plus metadata `"tool_settings_budget": reason, **meta` (`:1876`) | e.g. `max_identical_calls` | `TOOL_*` `:40-45` |
| Middleware (e.g. `CostBudgetMiddleware`) | `before_iteration` `:376-380`, `after_model_response` `:490-504`, `after_iteration` `:690-698` | `_middleware_abort_result` `:1204-1231`: output `"Agent runtime stopped by middleware: <reason>"`, plus `middleware_abort_reason` and `middleware_decision` | `middleware_abort` | `RUNTIME_MIDDLEWARE_ABORT` `:48` (TERMINAL/STOP `:130`) |

- What the caller sees on any stop: `_runtime_metadata` (`:2111-2127`) puts `stop_reason`, `iteration_count`, `tokens_used`, `tool_call_count`, `tool_call_states`, `tool_calls` and `"usage_rollup": self.usage_tracker.rollup()` on the result. `_finish_result` (`:945-969`) runs `after_run` and lifts run-state metadata (`:971-991`). `BaseAgent._generate_reply` merges all of it into the reply metadata (`vidbyte/agents/base.py:986-997`). No budget stop puts its *limit* in the metadata today, except ToolSettings (`:1876`) and middleware (`:1225-1229`).
- When a call's cost becomes known: right after each main model response, at `usage_record = self.usage_tracker.record_call(raw_result)` (`:477`). That is after `tokens_used` is updated (`:476`) and before `after_model_response` (`:490`). The tracker also records:
  - side calls in `_invoke_context_window_runner` (`:1043-1050`, record `:1049`);
  - billed failures (`:793`);
  - priced tool operations in `_record_operation_usage` (`:1377-1397`, `record_operation` `:1388`).
  
  The runtime can read the cumulative cost at any point as `self.usage_tracker.rollup().cost_usd`.
- Other hooks: `_after_tool_iteration` (`:925-931`) is called at `:700`, after a tool iteration that continues. `_continue_finish_attempt` (`:917-923`) is called at `:598` and `:673`. Both are overridden by JevRuntime.
- Model-visible budget text: `_render_loop_settings_block` (`:1679-1701`), called at `:1599`, renders `max_iterations`, `max_tokens` and `max_tool_calls` as "current/limit" into the system prompt. Its docstring: "timeout_seconds is enforced at the budget check but kept out of model-visible prompt text." Touched only if the spec shows the cap to the model.
- Contract counters: `_contract_counters` (`:2129-2148`) has `"cost_spent_usd": self._cost_spent_usd(run_state)` (`:2146`). `_cost_spent_usd` (`:2174-2181`) returns the **CostBudgetMiddleware flat-rate estimate, else 0.0**, not priced usage.
- Will change: a cap check at one or more of the points above. Which points is the spec's choice.
- Pattern (`:2063-2070`):
  ```python
  if self.config.max_tokens is not None and tokens_used is not None and tokens_used >= self.config.max_tokens:
      return self._stopped_result("Agent runtime stopped after reaching max_tokens.", stop_reason=AgentStopReason.MAX_TOKENS, iteration_count=iteration_count, tokens_used=tokens_used, contexts=contexts)
  ```

### 2C. Places that copy or list loop fields by name (a new field silently drops if one is missed)

**`vidbyte/agents/base.py`** (1,830 lines)
- Today:
  - `_resolve_loop_settings` (`:316-332`) builds `AgentLoopSettings` from flat kwargs. Only `max_iterations`, `max_tokens` and the compaction pair are flat parameters, and passing both forms raises (`:326-329`).
  - `self.runtime_config = self.agent_loop_settings.to_runtime_config()` (`:248`).
  - Non-linear runtimes refuse some loop features: `tool_error_policy` (`:223-232`), `tool_settings` (`:233-242`) and output contracts (`:243-247`).
  - `_runtime()` (`:1408-1461`) passes `usage_tracker=self._usage_tracker` only for linear runtimes (`:1435-1442`) and `config=self.runtime_config` (`:1453`).
  - Export and restore:
    - `_export_runtime_config` (`:624-659`) lists budget keys explicitly at `:627-631`.
    - `_export_loop_settings` (`:661-684`) lists fields in an explicit tuple at `:663-675`.
    - `_restore_loop_settings` (`:753-774`) rebuilds with `AgentLoopSettings(**values)` (`:774`), so an exported key passes through.
- Will change: `_export_loop_settings` must name the field, or `export_state`/`restore` loses the cap. The non-linear refusal block is touched only if the spec refuses the cap on MCTS and actor runtimes.
- Pattern: add the name to the tuple at `:663-675`.

**`vidbyte/agents/fork.py`** (252 lines)
- Today: no budget enforcement. `_loop_settings` (`:150-173`) returns the parent's object when there is no override (`:152-155`). With a `max_iterations` override, it rebuilds `AgentLoopSettings(...)` from an **explicit field list** (`:157-173`).
- Will change: the new field must be added to `:157-173`, or a fork with a `max_iterations` override loses the cap.

**`vidbyte/tools/builtins/fork/fork.py`** (587 lines; the model-facing `fork_conversation` tool)
- Today:
  - `_LOOP_SETTING_FIELDS` (`:52-63`) is the field set the model may override.
  - `_resolve_loop_settings` (`:299-332`) rebuilds the child loop from those fields plus `_inherited_guardrails()` (`:334-343`), which holds `tool_settings`, `tool_error_policy`, `output_contracts`, `max_contract_rejections` and `max_queued_prompts`.
  - Only `max_iterations` is capped at the parent's value (`:328-331`).
  - The JSON schema (`:484-500`) has `"additionalProperties": False` and says "Complete AgentLoopSettings override surface."
- Will change: whenever the model passes any loop override, a field in neither list resets to its default. The spec decides whether the cap goes in the overridable set or the guardrails. `tests/test_fork_tool.py:319-338` pins the guardrail inheritance.
- Trap: editing anything under `vidbyte/tools` turns a branch-scoped harness test red locally (field guide `local-ci-verification.md:45-49`; see §4.3).

**`vidbyte/lib/dataclasses/config.py`** (828 lines; YAML `agent.loop`)
- Today: `_LOOP_FIELDS` (`:92-98`) "Mirrors the AgentLoopSettings keyword arguments" (`:90`). `_loop` (`:670-688`) rejects any key outside it (`:678`) before calling `AgentLoopSettings(**mapping)` (`:686`).
- Will change: add the field name to `:92-98`, or YAML cannot set the cap. I found no test that pins `_LOOP_FIELDS` against the constructor signature (a grep for `_LOOP_FIELDS` finds only the codex constant).

**`vidbyte/lib/config/loader.py`** (447 lines)
- Today: `_construct_base_agent` passes `**loop_raw` into `AgentLoopSettings` (`:204-221`).
- Will change: nothing. Inference: a new keyword passes through automatically.

**JevAgent and its children** (neighbours; none needs an edit to receive the field)
- `JevAgentSettings.loop: AgentLoopSettings` (`vidbyte/agents/jev/settings.py:144`), checked with `isinstance` (`:181-182`).
- The **same `settings.loop` object** goes to:
  - the main agent: `vidbyte/agents/jev/agent.py:97`;
  - the fresh-continuation agent: `agent.py:76`;
  - bulk workers: `vidbyte/agents/jev/bulk_work.py:60`;
  - clones: `vidbyte/agents/jev/compute/clone.py:45`;
  - swarm helpers: `vidbyte/agents/jev/compute/swarm.py:57`.
- Jev's fixed-prompt agents build their **own** `AgentLoopSettings` without it: `brief/writer.py:60`, `done/handoff.py:161`, `done/reviewer.py:37`, `done/run_state.py:281`, `gate/clarification.py:54`.
- `InfiniteMemoryAgent` passes `settings.loop` too (`vidbyte/agents/infinite/agent.py:87`, `launch.py:311`).

### 2D. Where a stop reason reaches callers (edited if a new stop reason is added)

**`vidbyte/sessions/failure/router.py`** (552 lines)
- Today: `FailureMetadataNormalizer._STOP_CODES` (`:36-51`) maps a stop_reason string to a `FailureCode`. The `@intent stop-codes-cover-agentstopreason` comment (`:52-54`) says every member except `FINAL_RESPONSE` and `IS_DONE` is covered. `_append_stop_failure` (`:112-131`) maps an unknown reason to `FailureCode.RUNTIME_ERROR` (`:118`). Its details are exactly `{"stop_reason", "iteration_count", "tokens_used"}` (`:131`). Status is EXHAUSTED/ROUTE except middleware abort (`:130`).
- Will change: one `_STOP_CODES` entry if there is a new stop reason.
- Pattern: `"max_tokens": FailureCode.RUNTIME_MAX_TOKENS,` (`:38`).

**`vidbyte/lib/enums/failure.py`** (354 lines)
- Today: `FailureCode` (`:22-201`). The header (`:6`) says "Add a category-prefixed code with docs, mapping coverage, and a focused test". Runtime codes are at `:119-129`, then `RESOURCE_EXHAUSTED = "resource.exhausted"` (`:130`), `USAGE_RECORDING_CORRUPTED` (`:159`) and `RULE_EVALUATION_FAILED` (`:163`), followed by the 32 harness/browser codes (`:164-201`).
- Will change: touched only if the spec adds a code. Read §4.3 first.

**`vidbyte/evals/behavior/efficiency.py`** (301 lines)
- Today: `_BUDGET_STOP_REASONS` (`:31-43`), with `@intent budget-stop-covers-every-runtime-budget` ("The runtime's _budget_stop and the ToolSettings hard budgets both end runs on these reasons"). It is an explicit set of 9 values, used by `did_not_stop_on_budget` (`:199-201`).
- Will change: add a new budget stop reason here, or the eval treats it as a non-budget stop. `vidbyte/evals/behavior/stop.py` has one predicate per reason (e.g. `did_not_hit_max_tokens` `:63-65`).

**`vidbyte/lib/constants/outputs.py`**
- Today: `OUTPUT_DELIVERABLE_STOP_REASONS = {final_response, is_done}` (`:34-36`). Any other stop sends nothing to output connectors (`vidbyte/agents/README.md:377-379`: "a run stopped by a budget, guard, or middleware sends nothing").
- Will change: nothing (listed as a consumer).

**`skills/failure/vocabulary.md`** (138 lines)
- Today: the human failure-code catalogue. The runtime section is at `:98-106`. Its rule: "Use the most specific existing code. Do not create a new code because an error message has a different wording." I found no test or lint rule that enforces coverage of this file (searched `tests/`, `lint/`, `scripts/`).

### 2E. The pricing and ledger path (read-only neighbours, the source of "what was spent")

**`vidbyte/agents/pricing/tracker.py`** (292 lines)
- `UsageTracker` (`:55`) holds a default pricebook (`:60`).
- `record_call` (`:76-81`) → `_record` (`:87-111`):
  - no parseable usage, or an unknown provider: `_unaccounted_calls += 1`, no record (`:94-96`);
  - otherwise `cost = usage.cost_usd(self._pricing.resolve(provider, str(model)))` (`:97`), which **is `None` when the model is unpriced**;
  - an exception marks the ledger corrupted (`:98-100`).
- `merge(rollup)` (`:133-166`) appends a nested run's records.
- `rollup(kind=None)` (`:168-193`):
  - `cost_usd=_sum_or_none(...)` (`:185`) **sums only the non-None costs** (`:251-260`), so a partly unpriced run reports a too-low number;
  - `cost_complete` (`:186`) is False if any item is unpriced, and also False when there are no records.
- `reset()` (`:195-200`).

**`vidbyte/agents/pricing/records.py`** (97 lines)
- `UsageRollup` (`:68-89`) is the live run rollup: `calls`, `model_call_count`, token sums, `cost_usd: float | None`, `cost_complete`, `operations`, `recording_integrity`, `unaccounted_call_count`. `UsageRecord` (`:39-53`) has `cost_usd`, `kind` and `failed`.
- This is the **root-exported** `vidbyte.UsageRollup` (`vidbyte/__init__.py:46` `from vidbyte.agents import (`, `:283`; `vidbyte/agents/__init__.py:249`).

**`vidbyte/lib/dataclasses/sessions.py`** (153 lines; GUESS listed it, but it is not on the live path)
- A *different* `UsageRollup` (`:126-140`) with `cost: float | None` and `per_agent: tuple[AgentUsage, ...]`, plus `AgentUsage` (`:115-123`). It is built only by `SessionUsageBuilder.build` (`vidbyte/sessions/usage.py:27-41`) from persisted session history, with caller-supplied flat prices (`:82-91`, `:107-119`). It is not live run spend.

**`vidbyte/lib/registries/pricing.py`** (391 lines)
- `PROVIDER_PRICING` (`:147-315`).
- `ModelPricingRegistry.resolve` (`:333-358`) tries an exact match, then a normalized name, then a release-suffix prefix, and otherwise returns None.
- OpenRouter has an empty table (`:274-276`) and uses provider-reported cost.
- TypeSafe Jev models are priced (`:304-314`, e.g. `"jev-latest"` `:312`: input 0.042/M, output 0.0).
- Some rates vary by tier or time of day (`tier_rates=OPENAI_GPT56_TIER_RATES[...]` `:162`; `DEEPSEEK_TIME_OF_DAY_RATES` `:136`, `:239`).

**`vidbyte/lib/registries/models.py`**
- `DEFAULT_PROVIDER_MODELS` (`:73-88`). The 7 CLI providers (`request.md:129`: openai, claude→anthropic, grok→xai, deepseek, glm, muse→meta, gemini) and their SDK defaults are **all priced**:

  | Provider | Default model | Pricebook line |
  |---|---|---|
  | openai | `gpt-5.6-sol` | `pricing.py:162` |
  | anthropic | `claude-sonnet-5` | `:193` |
  | gemini | `gemini-3.5-flash` | `:214` |
  | xai | `grok-4.5` | `:229` |
  | deepseek | `deepseek-v4-pro` | `:239` |
  | glm | `glm-5.2` | `:248` |
  | meta | `muse-spark-1.1` | `:284` |

  minimax, kimi and mistral defaults are priced (`:261`, `:271`, `:296`). `openrouter/auto` has no entry. `STRICT_MODEL_VALIDATION` (`models.py:70-71`) can be set False "to accept any non-blank model name".

**`vidbyte/lib/usage_ledger.py`** (57 lines)
- `UsageLedger` Protocol (`:23-36`).
- A ContextVar ledger: `active_usage_ledger` (`:42-44`) and `usage_ledger_scope` (`:47-54`).
- Header: "DecisionModelRunner.arun records every Jev call into whichever ledger is active" (`:4`); "asyncio tasks copy the ledger in effect when they were created" (`:7`).

**`vidbyte/lib/runners/decision.py`** (76 lines)
- `DecisionModelRunner.arun` (`:39-56`) records `ledger.record_call(response, kind=UsageKind.DECISION)` (`:55`) and billed failures (`:50-52`) into the active ledger (`:46`).

### 2F. Jev (neighbours; read in full)

**`vidbyte/agents/jev/runtime.py`** (293 lines)
- `JevRuntime(AgentRuntime)` (`:40`). `self.usage = JevUsageAccount(self.usage_tracker, ...)` (`:84`).
- `arun` (`:86-102`) wraps the run in `JevManagedRun` and `self.usage.scope()`.
- `_arun_metered` (`:104-155`) runs these phases before `super().arun` (`:145`):
  - preflight gate (`:120`);
  - `require_accounted` (`:122`);
  - specialist delegation (`:129-130`);
  - skill preload (`:131`);
  - compute begin (`:134`);
  - run-state writer (`:136`);
  - tool selector (`:143`);
  - bulk-work tool (`:144`).
- After the loop: `self.response.finished(result, self.usage.settle())` (`:155`).
- `_continue_finish_attempt` (`:252-279`) grows only finite `max_iterations`, `max_tokens` and `max_tool_calls` through `replace(self.config, **limits)` (`:260-275`).
- `_after_tool_iteration` (`:282-290`) runs the compute checkpoint.
- No budget check of its own.

**`vidbyte/agents/jev/usage.py`** (94 lines)
- `JevUsageAccount.require_accounted` (`:39-58`) raises `UsageAccountingError` ("...stopped because Vidbyte could not calculate this run's usage. This is an error on our side...") when `failures()` (`:73-81`) finds `RECORDING_ERROR`, `UNREPORTED_USAGE` or `UNPRICED_CALL`. `unpriced()` (`:83-91`) names `provider:model`. `report()` (`:60-66`) returns total, generative and decision rollups.
- Header: "Checks run at phase boundaries, so one main-loop pass can spend before the error" (`:7`).

**`vidbyte/agents/jev/response.py`** (157 lines)
- `_with_usage` (`:148-154`) sets `state.usage` and replaces `metadata["usage_rollup"]` with the run total, to keep "get_usage(), result metadata, and JevAgent.response.usage" in agreement.
- `JevAgentResponse` (`vidbyte/lib/dataclasses/jev.py:3856-3898`) has **no stop_reason field**. The stop reason reaches a Jev caller only through `reply.metadata`.

**`vidbyte/agents/jev/agent.py`** (132 lines)
- `_require_metered_specialists` (`:113-125`) rejects a specialist that does not reply through `BaseAgent.generate_reply`, "so its usage counts toward the run total". `_runtime_extension_kwargs` (`:127-129`).

**Jev children, all plain `BaseAgent`s**
- `JevCloneAgent.attempt` uses `asyncio.gather` (`compute/clone.py:48-53`) and is called from the checkpoint (`compute/controller.py:99-107`).
- `JevSwarmAgent.attempt` uses `asyncio.gather` (`compute/swarm.py:61-69`), called from `JevSwarmTool.execute` (`compute/swarm_tool.py:104-122`), which first asks Jev a plan check (`:116`).
- `JevBulkWorkTool.execute` runs `ParallelPipeline(workers).run(...)` (`bulk_work.py:119-137`, pipeline `:134`).
- Both launch tools are `metadata={"internal": True}` (`bulk_work.py:116`; `swarm_tool.py:101`).

### 2G. Existing cost features that overlap

**`vidbyte/middleware/builtins/cost_budget.py`** (96 lines; not a root export)
- `CostBudgetMiddleware(*, max_spend_usd, cost_per_million_tokens)` (`:36-39`) validates with `positive_real` (`limit_validation.py:27-31`, which raises **ValueError**).
- It estimates spend as `accumulated_tokens / 1_000_000 * cost_per_million_tokens` (`:60-70`), a flat rate rather than pricebook prices.
- It aborts in `before_iteration` when `spend >= self.max_spend_usd` (`:72-84`), with `MiddlewareDecision.abort("cost_budget_exceeded", metadata={"max_spend_usd", "estimated_spend_usd", "tokens_used"})`.
- Per-run state lives in `CostBudgetRunState` (`vidbyte/lib/dataclasses/middleware.py:223-229`).
- It is used by `paradigms/context_minimal_fanout/paradigm.py:333-334` from `types.py:484` `max_cost_usd`.

**`vidbyte/agents/contracts/floors.py`** (183 lines)
- `MinCostSpent` (`:144-183`) is a *floor* with `ceiling_key = None` (`:148`). It reads the `cost_spent_usd` counter (the middleware estimate or 0.0, `runtime.py:2174-2181`) and falls back to rate × tokens (`:173-183`).
- Its `__init__` (`:151-159`) checks only `<= 0` (no bool or finite check).
- Other floors pair with a ceiling through `ceiling_key` (`:29-58`).

**`vidbyte/lib/dataclasses/middleware.py`** (271 lines)
- `MiddlewareContext` (`:164-191`) carries per-call `model_usage` (`:184`) and `tokens_used`, but **no cumulative cost**.

**`vidbyte/lib/dataclasses/context.py`**
- `ContextBudget.max_cost_usd` (`:58`). A grep finds no reader in `vidbyte/` other than the paradigm's own same-named field.

### 2H. Contracts, release record, catalogs

**`contracts/sdk-public-api.json`**
- Records names only. The schema keys are `("schema_version","source","distribution","version","exports")` (`lint/core/public_api_contract.py:32`).
- It already lists `AgentLoopSettings`, `AgentRuntimeConfig`, `AgentStopReason`, `ConfigurationError`, `FailureCode`, `UsageRollup` and `UsageTracker`. `UsageAccountingError` and `CostBudgetMiddleware` are **not** root exports.
- It changes only if a new root name is added (`request.md:64`). Regenerate it, never edit it by hand (`contracts/README.md`).

**`docs/design/release-0-4-0.md`** (19 lines; read as allowed)
- Format: one intro paragraph (`:3`), then "What 0.4.0 changes ..." (`:5`) and a bullet list (`:7-17`), one bolded lead-in per change with its PR number.
- Post-baseline merges go in the **"Later changes on `main`."** bullet (`:17`), e.g. "#1190 makes `AgentLoopSettings`, ... root exports, 4 names, so vidbyte-cli can ...".
- The closing paragraph (`:19`) carries the export count ("The contract now lists 733 exports ... 4 from #1190"). It changes only if root names change.
- A `FailureCode` growth was recorded inline before ("`FailureCode` gains 28 members", `:11`).

---

## 3. Tests that cover those files

Framework: pytest (`pyproject.toml:78-81`, `testpaths=["tests"]`). Many files use `unittest.TestCase` or `IsolatedAsyncioTestCase` collected by pytest. The narrow `scripts/test-*.py` scripts are not run by `run_ci.py` (`:79-93`).

| Test file | Covers | Fixtures / shape | Run one file |
|---|---|---|---|
| `tests/features/sdk_loop_settings/test_contract.py` (160) + `FEATURE.md`, `README.md` | `AgentLoopSettings` validation and `to_runtime_config` | Offline, no runner. `INTEGER_FIELDS` parametrize (`:24-28`); bool, NaN and inf probes (`:31-41`); `pytest.raises(ConfigurationError, match=field)`; `test_valid_limits_reach_runtime_config` (`:75-78`). Header: "Add an invalid value when a new public count or timeout field is introduced" | `python -m pytest -q tests/features/sdk_loop_settings/test_contract.py` |
| `tests/features/sdk_model_usage/test_nested_usage_bill.py` (134) | Nested-agent bill through the ledger | Scripted `HttpTransport.request` wire (`_Wire` `:54-79`), DeepSeek DIRECT with fake keys (`_kw` `:34-36`, model `deepseek-v4-flash`, priced `pricing.py:238`). Counts wire calls against `get_usage()` (`:97-110`). The closest end-to-end model for "stop after N priced calls" | `python -m pytest -q tests/features/sdk_model_usage` (`FEATURE.md:51`) |
| `tests/features/sdk_model_usage/test_usage_contract.py` (74) | `UsageTracker` parsing and pricing | `SimpleNamespace(provider=, model=, usage=)` responses; an unpriced model gives `cost_usd is None` and `cost_complete is False` (`:59-65`) | same area |
| `tests/test_agent_runtime.py` (1,417) | Runtime budget stops | `FakeRunner`/`FakeResponse` with `AgentRuntime(... config=AgentRuntimeConfig(max_tokens=1))` (`:606-633`); `AgentLoopSettings(max_tool_calls=2).to_runtime_config()` (`:879-894`). Inference: a `FakeResponse` has no `provider`/`model`, so `record_call` counts it as unaccounted with no price (`tracker.py:80-96`); priced tests need a response carrying provider, model and usage | `python -m pytest -q tests/test_agent_runtime.py` |
| `tests/test_jev_usage_ledger.py` (226) | Jev one-ledger total and fail-closed | `ScriptedGenerativeRunner` returns `TextModelResponse(provider=OPENAI, model="gpt-5.4-mini", usage=...)` (`:41-50`); decision calls faked at `TypeSafeProvider.run_decision` (`:33`, `:65-73`); `bind_test_runner` (`tests/agent_test_support.py:62-65`); the Vidbyte key fixture is concatenated at runtime (`:78`). Unpriced case `:154-157` | `python -m pytest -q tests/test_jev_usage_ledger.py` |
| `tests/test_session_failures.py` | stop_reason → FailureCode | `test_stop_reasons_map_to_specific_codes` (`:422-428`); `test_loop_stop_failure_keeps_tokens_used` pins the **exact** details dict (`:430-435`); `test_every_code_has_category_prefix` (`:141-143`) | `python -m pytest -q tests/test_session_failures.py` |
| `tests/test_fork_tool.py` | fork tool loop overrides and guardrails | `test_loop_overrides_keep_parent_tool_guardrails` (`:319-338`); null fields keep parent values (`:372-385`) | `python -m pytest -q tests/test_fork_tool.py` |
| `tests/features/harness_threads/test_harness_threads_surface.py` | `FailureCode` membership | `test_failure_codes_keep_main_and_append_exactly_the_32_harness_codes` (`:218-241`) | not this run's test; do not edit (`request.md:66`) |
| `tests/features/codex_host/test_codex_host_helper_surface.py:252-264`, `test_codex_host_records.py:424-430` | position of codex codes in `FailureCode` | ordered slices of the enum | — |
| `tests/test_codex_failure_recovery.py:280-292` | every `codex.*` code has a classification row, and every row names a real code | set differences; affects only a new `codex.` code | — |
| `tests/features/agent_output_connectors/test_output_connectors_dispatch.py:41`, `tests/multi_agent/test_manager_middleware_abort.py:64`, `tests/test_multi_provider_agentic_grader.py:793` | iterate every `AgentStopReason` | A new member is picked up automatically as "unfinished" | — |
| `tests/test_new_middleware_builtins.py:371-479`, `tests/features/sdk_middleware_limits/` | `CostBudgetMiddleware` | Direct hook calls | `python -m pytest -q tests/features/sdk_middleware_limits` |
| `tests/features/jev_cli_root_exports/` (R1 pack) | root identity of `AgentLoopSettings` | No field or signature pins. Header: "do not pin an export count" | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_cli_root_exports` |
| `scripts/test-agent-loop-settings.py` (405) | narrow script, not in CI | Calls `_render_loop_settings_block` (`:337-369`). unverified: whether it still passes | `python scripts/test-agent-loop-settings.py` |

Feature pack shape to copy: `tests/features/<pack>/` holds `README.md` (Folder Description / Intent, Non-Goals, File Index, Logs), `FEATURE.md` (Contract, Actors, Inputs, Observable Outcomes, State Transitions, Invariants, External Dependencies, Known Failure Modes, Historical Regressions, Test Suite Map, Omitted Testing Strategies) and `test_*.py` files with the FILE/PURPOSE/ROLE/... header. Examples: `tests/features/sdk_loop_settings/`, `tests/features/sdk_model_usage/`.

---

## 4. Notes for the spec author

### 4.1 Contradictions: request assumes X, code shows Y

1. **Which `UsageRollup`.**
   - Request assumes: money comes from "`UsageRollup.cost` in `vidbyte/lib/dataclasses/sessions.py:127-135`" (`request.md:46`), and children count "if ... (`UsageRollup.per_agent`)" (`:58`).
   - Code shows: the live run rollup is `vidbyte/agents/pricing/records.py:68-89` (`cost_usd`, `cost_complete`, no `per_agent`), returned by `UsageTracker.rollup()` (`tracker.py:168-193`) and put on every result (`runtime.py:2126`). The sessions.py class (`:126-140`) is built after the fact from session history with flat caller prices (`vidbyte/sessions/usage.py:27-41`). Children reach the parent through ledger *merges* (`base.py:882-886`), not through `per_agent`.
2. **Where the failure code comes from.**
   - Request assumes: the cap stops "the same way ... `max_tokens` at `runtime.py:514-516`, with failure code `RUNTIME_MAX_TOKENS` in `failure.py:120`" (`:40`).
   - Code shows: the runtime sets only `AgentStopReason` (`runtime.py:516-517`). `FailureCode` is assigned later by the session router (`router.py:36-51`, `:118`). Also, `:513-522` is only the final-answer check; the per-iteration check is `_budget_stop` (`:2046-2089`, called at `:367-374`).
3. **Decision calls.**
   - Request assumes: "They are billed by the Vidbyte gateway, not priced by the SDK's provider rates" (`:59`).
   - Code shows: the SDK prices them. TypeSafe rates are at `pricing.py:304-314`. They are recorded into the active ledger as `UsageKind.DECISION` (`decision.py:46-55`) and reported split out (`jev/usage.py:60-66`; `JevUsageReport` docstring `jev.py:3809-3814`). unverified: whether the gateway's actual charge equals those rates.
4. **"Every loop that enforces max_tokens and max_tool_calls."**
   - Request assumes: these loops are in `fork.py`, `jev/runtime.py` and `contracts/floors.py` (`:53`).
   - Code shows:
     - `fork.py` copies settings and enforces nothing (`:150-173`);
     - `jev/runtime.py` only *grows* finite limits (`:260-275`) and checks usage *accounting* at phase boundaries;
     - `floors.py` holds minimum floors, not ceilings (`:29-183`).
     
     The only enforcement is in `runtime.py` (table in §2B), plus middleware.
5. **Validation location.**
   - Request assumes: "The repo validates other budgets in `loop.py:11`" (`:56`).
   - Code shows: `loop.py:11` is docstring text. The validators are `:102-118`. The class raises `ConfigurationError`, while `AgentRuntimeConfig.__post_init__` (`agents.py:139-152`) and `positive_real` (`limit_validation.py:27-31`) raise `ValueError`.
6. **"Every agent."**
   - Request assumes: a cap in "the shared runtime path that every `BaseAgent` subclass uses" (`:51`).
   - Code shows: only the `LINEAR`, `JEV` and `INFINITE_MEMORY` runtimes are `AgentRuntime` (`base.py:83`, `:1435`).
     - MCTS and actor runtimes do not subclass it (`vidbyte/lib/registries/runtimes.py:41-49`). A grep of `vidbyte/agents/runtimes/` finds no use of `max_iterations`, `max_tokens`, `max_tool_calls` or `timeout_seconds`. Some loop features are refused on them at construction (`base.py:223-247`).
     - `MultiAgent` and `AggregateAgent` override the run and open their own ledger (`multi/agent.py:117-127`; `aggregation.py:263-268`). Neither file references `agent_loop_settings`.
7. **An existing USD ceiling already exists.** `CostBudgetMiddleware` (`cost_budget.py:33-84`) estimates spend at a flat rate. The `cost_spent_usd` contract counter (`runtime.py:2146`, `:2174-2181`) and `MinCostSpent` (`floors.py:144-183`) read that estimate, not priced usage. The field guide (`runtime-boundaries.md:24-26`) says: "Don't duplicate general agent/loop budget settings ... Reuse the existing general mechanism (`AgentLoopSettings.timeout_seconds`, `CostBudgetMiddleware`)". The request excludes "changing what any existing budget does" (`:73`).

### 4.2 The five product questions: what the code says

**Q1 Value type and validation**
- Every existing USD value is `float`: `max_spend_usd` (`cost_budget.py:36`), `max_cost_usd` (`context.py:58`), `cost_usd: float | None` (`records.py:68-89`), `estimated_spend_usd` (`middleware.py:229`). I found no `Decimal` on these paths.
- The finite-positive float pattern is `loop.py:112-118`.
- Existing names: `max_spend_usd`, `max_cost_usd`, `cost_spent_usd`. The request's word is `max_spend` (`request.md:40`, CLI `--max-spend`).
- A007 operational-literal tokens (`lint/rules/a007_operational_constants.py:23-38`) include `budget`, `limit` and `token`, but not `spend`, `cost` or `usd`. "Zero and one remain findings when they define operational policy" (`:9`).
- The field guide (`strict-config-dataclasses.md:34`, `:63`) wants named bounds in `vidbyte/lib/constants/` and `RecordFieldValidator` (`vidbyte/lib/dataclasses/validation.py`).
- `MinCostSpent` has `ceiling_key = None` (`floors.py:148`), so `_validate_contract_ceiling` (`loop.py:152-173`) does not today compare a spend floor with a spend ceiling.

**Q2 Unpriced calls**
- `cost_usd` is None when `resolve` misses (`tracker.py:97`). A call with no usage, or an unknown provider, leaves *no* record and increments `unaccounted_call_count` (`:94-96`).
- `rollup().cost_usd` silently sums only priced items (`:185`, `:251-260`). Only `cost_complete` (`:186`) reveals the gap.
- Precedent for failing closed: `JevUsageAccount.require_accounted` (`jev/usage.py:39-58`). It runs at phase boundaries, not at construction.
- Construction-time facts available:
  - `ModelPricingRegistry.default()` (`tracker.py:60`) and `resolve` (`pricing.py:333-358`);
  - the agent's provider and model (`runner_config`);
  - the fallback chain (`base.py:639-642`). A mid-run fallback switch (`runtime.py:430-459`) can move to a different model.
- Jev children may use other models: the brief writer can use its own provider and model (`brief/writer.py:55-64`), and specialists bring their own agents.
- Lint C009 (`lint/rules/c009_default_model_priced.py:285`) requires every default text model to be priced. All 7 CLI providers' defaults are priced (§2E).

**Q3 Child agents**
- The runtime's tracker is the agent's own `_usage_tracker` for linear runtimes (`base.py:1437`).
- A child's `generate_reply` records into the child's own tracker. It then merges into the parent ledger **once, in `finally`, when the child's reply finishes** (`base.py:854-857`, `:882-886`, `:897-905`). Inference: the parent's tracker shows a child's spend only after that child returns.
- Children run inside a parent step:
  - bulk workers inside the `run_bulk_work` tool call (`bulk_work.py:119-137`);
  - swarm helpers inside the `launch_swarm` tool call (`swarm_tool.py:104-122`);
  - clones inside the post-tool-iteration checkpoint (`controller.py:99-107`, via `runtime.py:700`);
  - the specialist replaces the main loop entirely (`jev/runtime.py:215-221`);
  - the fresh continuation runs at a finish attempt;
  - `as_tool()` sub-agents run inside a tool call (`test_nested_usage_bill.py:97-110`).
- Internal tools skip `_enforce_tool_settings` (`runtime.py:1836-1837`), and both launch tools are internal (§2F).
- Each Jev child gets the **same** `AgentLoopSettings` object as the main agent (§2C). Inference: a per-loop cap would also apply to each child separately against the child's own tracker, which resets at the child's run start (`base.py:923`).
- Children run concurrently (`clone.py:52`, `swarm.py:68`, `bulk_work.py:134`).

**Q4 Jev decision calls**
- They are priced (`pricing.py:304-314`) and recorded into the active ledger (`decision.py:46-55`).
- Inside a Jev run, the active ledger is the main agent's tracker. `JevUsageAccount.scope()` opens it over `self.usage_tracker` (`jev/usage.py:33-37`; `jev/runtime.py:84`, `:101`), which is the agent's `_usage_tracker` (`base.py:1437`). Inference: the main runtime's `self.usage_tracker.rollup()` includes decision costs as soon as each decision call returns.
- Decision calls happen at these points:
  - before the main loop: gate `:120`, selector `:182-202`, skill preload `:223-237` (all `jev/runtime.py`);
  - mid-run: compute recognizer `controller.py:86`, swarm plan check `swarm_tool.py:116`;
  - at finish attempts: done checks, via `_continue_finish_attempt` `jev/runtime.py:257`.
- The release-suffix match prices `jev-1.13.0` through the `jev-1.13` entry (`test_jev_usage_ledger.py:35`, `:99-100`).

**Q5 Overshoot**
- Cost is known only after a response (`runtime.py:477`).
- Rates can depend on tier or time of day (`pricing.py:162`, `:239`), and output tokens are not known in advance. Inference: an exact pre-call estimate is not available from the pricebook alone.
- Between two top-of-iteration checks (`:367-374`), one iteration can spend all of the following:
  - one main model call, plus retries and billed failures (`:793`);
  - context-window side calls (`:1049`);
  - every tool call in the turn, including priced operations (`:1388`) and whole child agents;
  - the compute checkpoint, with clones and Jev calls (`:700`);
  - finish-attempt done checks.
  
  "At most one call" (`request.md:60`) holds only for a run with no tools and no children.
- Algorithms re-enter `_arun_once` with a fresh state (`runtime.py:300`) while the tracker keeps accumulating: reflexion (`algorithms/reflexion.py:101`), the grader (`multi_provider_agentic_grader.py:96`), the critic (`independent_critic.py:94`, `:103`) and PDJ (`prosecutor_defender_judge.py:473`, `:507`). The tracker is reset only per agent run (`base.py:923`, `:1216`). Inference: `max_tokens` is per attempt, while tracker spend is per agent run.
- In Jev, the pre-loop phases spend before the main loop's first `_budget_stop` (`jev/runtime.py:118-145`).

### 4.3 Traps and pins

- **FailureCode pins** (`tests/features/harness_threads/test_harness_threads_surface.py:218-241`):
  - `:224-227` runs everywhere, CI included. The members after `RULE_EVALUATION_FAILED` must equal `NEW_FAILURE_CODES` (`:76-78`) exactly, so **appending any new member at the end fails it.**
  - `:228-236` runs only where `origin/main` has a merge base (local, not CI). Main's members must be an in-order prefix, so **inserting mid-enum fails it locally** until merge.
  - `:241` requires that members after main's prefix are only missing harness codes.
  - Codex tests pin ordered slices too (§3).
  - Inference: any new `FailureCode` member trips one of these. Reusing an existing code (e.g. `RESOURCE_EXHAUSTED` `failure.py:130`, or `RUNTIME_MIDDLEWARE_ABORT`) trips none.
  - The field guide entry about `assert 167 == 120` (`local-ci-verification.md:66-71`) is stale. The test was renamed to "32 harness codes" and no longer pins a count.
- **Branch-scoped harness tests**: "fail locally on any branch that touches `vidbyte/tools`, `vidbyte/lib/configs`, or root exports" (`local-ci-verification.md:45-49`). Editing `vidbyte/tools/builtins/fork/fork.py` (§2C) triggers it. Classify it as pre-existing; do not edit the test.
- **Exact details pin**: `tests/test_session_failures.py:430-435` asserts the stop failure details equal `{"stop_reason", "iteration_count", "tokens_used"}`, so adding a key to `router.py:131` for every stop breaks it.
- **Stop-reason gap already present**: `FINISH_REVIEW_REJECTED` (`agents.py:79`) is not in `_STOP_CODES` (`router.py:36-51`) despite the `@intent` at `:52-54`. Inference: it maps to `RUNTIME_ERROR` (`:118`). A new stop reason left out of `_STOP_CODES` behaves the same way.
- **Silent field drops**: a new loop field must be named in all of these, or it vanishes on that path:
  - `loop.py` `to_runtime_config` `:199-208` and `__repr__` `:214-229`;
  - `base.py` `_export_loop_settings` `:663-675`;
  - `fork.py` `_loop_settings` `:157-173`;
  - the fork tool's `_LOOP_SETTING_FIELDS` `:52-63` or `_inherited_guardrails` `:334-343`;
  - `lib/dataclasses/config.py` `_LOOP_FIELDS` `:92-98`.
- **Jev's result**: `JevResponse._with_usage` (`response.py:148-154`) overwrites `metadata["usage_rollup"]` with the run total, which includes children and decisions. `JevAgentResponse` has no stop-reason field (`jev.py:3877-3898`). The field guide (`jev-capability-layout.md`) says Jev outcomes are reported through `JevResponse` into `JevAgentResponse`, not `AgentResult.metadata`.
- **Jev `settle()` after the loop** (`jev/runtime.py:155`) raises `UsageAccountingError` on any unpriced call, even after a budget stop. `BaseAgent._generate_reply` re-raises that error type unwrapped (`base.py:967-975`).
- **File length**: AGENTS.md principle 3 versus `runtime.py` (2,304) and `base.py` (1,830).

### 4.4 Unverified

- unverified: whether a gateway (`TextModelMode.AUTO`) response is priced the same as DIRECT. Inference from `vidbyte/lib/runners/text.py:3-5`: the same provider adapters parse it. Whether the gateway's actual charge equals the pricebook rate was not checked.
- unverified: the exact CLI default model per provider (`request.md:191` lists it as unknown). Only the SDK defaults were checked.
- unverified: whether lint C019 (`lint/rules/c019_platform_error_code_contract.py:3-4`) would flag a new stop-reason literal in a decision position. It compares 3+-token literals with the platform contract, which I did not read.
- unverified: whether `scripts/test-agent-loop-settings.py` still passes. It is not run by CI.
- unverified: which `PYTHONPATH` rule applies to the gate (see §1.2).
