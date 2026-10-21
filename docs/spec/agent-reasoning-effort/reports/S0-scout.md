# S0 scout report: agent-reasoning-effort (R2)

Stage S0, 2026-10-20. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-reasoning-effort`, branch `feat/agent-reasoning-effort`, head `db6dd49f`, code at `98a5d37b`.

Output: `docs/spec/agent-reasoning-effort/context/code-map.md` (four numbered sections, 104 distinct repo paths cited).

I made no commits and ran no installs, builds or gates. I fetched no web pages. Under `docs/`, I read only `request.md`, `docs/design/release-0-4-0.md`, and §5 and §9.2 of `docs/spec/loop-spend-cap/spec.md`. I read nothing in the orchestrator's scratchpad except the prompt file.

## 1. Planned file list

The list started from the GUESS. I checked each entry with `git grep` or by listing the directory, then added the files that the reading showed were needed.

**Edited or crossed by the change**

| Group | Files |
|---|---|
| Model config | `vidbyte/lib/dataclasses/model_configs.py` (`TextModelConfig`, `DecisionModelConfig`) |
| Runner build | `vidbyte/lib/runners/utility.py`, `vidbyte/lib/runners/text.py` |
| Agent | `vidbyte/agents/base.py`, `vidbyte/lib/dataclasses/agents.py` (`AgentRunnerConfig`, `FallbackModel`, `AgentForkSettings`) |
| Fallback | `vidbyte/agents/fallback.py`, `vidbyte/agents/settings/fallback.py` |
| Construction checks | `vidbyte/agents/spend_cap.py` |
| Copy paths | `vidbyte/agents/fork.py`, `vidbyte/tools/builtins/fork/fork.py`, `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/sessions/serialization.py`, `vidbyte/lib/dataclasses/config.py`, `vidbyte/lib/dataclasses/agent_descriptor.py`, `vidbyte/lib/config/loader.py` |
| Jev settings | `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/agent.py` |
| Jev children | `bulk_work.py`, `compute/clone.py`, `compute/swarm.py`, `done/handoff.py`, `done/reviewer.py`, `done/run_state.py`, `gate/clarification.py`, `brief/writer.py`, all under `vidbyte/agents/jev/` |
| Jev records | `vidbyte/lib/dataclasses/jev.py` (`JevSpecialist`) |
| Adapters for the 7 CLI providers | `vidbyte/providers/openai.py`, `anthropic.py`, `gemini.py`, `xai.py`, `compatible.py`, and `vidbyte/providers/__init__.py` (dispatch) |
| Gateway | `vidbyte/lib/http/vidbyte_gateway.py`, `vidbyte/lib/constants/jev.py` |
| History echo | `vidbyte/lib/tools/formatter.py` |
| Usage | `vidbyte/agents/pricing/*.py`, `vidbyte/agents/pricing/tracker.py`, `vidbyte/lib/token_usage.py` |
| Enums | `vidbyte/lib/enums/codex.py`, `native_threads.py`, `text_model.py`, `model_provider.py`, `__init__.py` |
| Validation | `vidbyte/lib/dataclasses/validation.py` |
| Root exports | `vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `scripts/generate-sdk-public-api.py` |
| Release record | `docs/design/release-0-4-0.md` |

**Patterns to model on**
- `vidbyte/lib/configs/structured_output.py` with `vidbyte/lib/registries/structured_output.py` (the only existing capability tables).
- `vidbyte/agents/settings/loop.py` (R3's field validation).
- The `AgentSpendCap.model_refusal` call at `base.py:255-257` (R3's construction-time chain check).

**Tests**
- `tests/features/sdk_managed_text/`: wire contract, selection, fixtures.
- `tests/test_gemini_provider_text.py`.
- `tests/features/loop_spend_cap/`: acceptance, copy paths, fixtures, README.
- `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py`.
- `tests/features/harness_threads/test_harness_threads_surface.py`.

**Neighbours**
- `vidbyte/agents/runtime.py` (context-window side calls) and `vidbyte/agents/algorithms/reflexion.py`.
- `vidbyte/lib/runners/streaming_text.py`.
- `vidbyte/providers/openrouter.py`.
- `vidbyte/agents/codex/agent.py` and `vidbyte/agents/codex/fallback.py`.

## 2. Files actually read

**Rules and maps**
- `AGENTS.md` (in full) and `REPO_MAP.md`.
- `request.md` (every section) and the prompt file.
- `C:/Users/422mi/.claude-account3/skills/spec-pipeline/references/vidbyte-gates.md`.
- Field-guide entries under `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`: `local-ci-verification`, `strict-config-dataclasses`, `blocking-lint-invariants`, `comment-format`, `runtime-boundaries`, `fallback-coordination`, `provider-api-contracts`, `jev-capability-layout`.
- `vidbyte/providers/README.md`.
- `vidbyte/agents/README.md`: "Model Fallback" `:185-250` and "Spend Cap" through "Related Layers" `:386-455` only.
- `vidbyte/agents/jev/README.md`: grep-matched lines, plus `:24` and `:28` in full.
- `lint/README.md`, `lint/baseline.json`, and the headers of lint rules A007, A009, C002, C008, S015 and S060.
- `scripts/run_ci.py` and `scripts/generate-sdk-public-api.py`.

**Code**
- `vidbyte/lib/dataclasses/model_configs.py`, `agents.py`, `jev.py` (`JevSpecialist`), `sessions.py`, `config.py`, `agent_descriptor.py`, `validation.py`, `native_threads.py` and `codex.py`.
- `vidbyte/lib/runners/utility.py`, `text.py` and `streaming_text.py`.
- `vidbyte/agents/base.py`, `fallback.py`, `settings/fallback.py`, `settings/loop.py`, `spend_cap.py`, `fork.py`, `runtime.py`, `aggregation.py`, `continual_trace.py`, `handoff.py`, `algorithms/reflexion.py`, the `infinite/` settings and launch code, `codex/agent.py` and `codex/fallback.py`.
- `vidbyte/agents/jev/settings.py`, `agent.py`, `runtime.py`, `gate/gate.py`, `brief/keeper.py`, and the nine child files listed in §1.
- `vidbyte/providers/__init__.py`, `openai.py`, `anthropic.py`, `compatible.py`, `xai.py`, `gemini.py` and `openrouter.py`.
- `vidbyte/lib/http/vidbyte_gateway.py`, `vidbyte/lib/http/transport.py` and `vidbyte/lib/constants/jev.py`.
- `vidbyte/lib/tools/formatter.py`.
- `vidbyte/agents/pricing/` (every provider module and `tracker.py`), the pricing records, and `vidbyte/lib/token_usage.py`.
- `vidbyte/lib/enums/codex.py`, `native_threads.py`, `text_model.py`, `model_provider.py`, `jev.py` and `__init__.py`.
- `vidbyte/lib/configs/structured_output.py`, `vidbyte/lib/registries/structured_output.py` and `vidbyte/lib/errors/base.py`.
- `vidbyte/tools/builtins/fork/fork.py`, `vidbyte/sessions/serialization.py` and `vidbyte/lib/config/loader.py`.
- `vidbyte/__init__.py`, `contracts/sdk-public-api.json`, and `git show 22993b5f` (#1190).

**Tests**
- `tests/features/sdk_managed_text/test_managed_text_wire_contract.py`, `test_managed_text_selection.py` and `managed_text_fixtures.py`.
- `tests/test_gemini_provider_text.py`.
- `tests/features/loop_spend_cap/` fixtures, acceptance and README.
- `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py` and `tests/features/harness_threads/test_harness_threads_surface.py`.

**Docs (as the briefing allowed)**
- `docs/design/release-0-4-0.md`, and `docs/spec/loop-spend-cap/spec.md` §5 and §9.2.

**Not read beyond sizes or headers.** These are listed as unverified in code-map §4.3: `tests/test_jev_agent.py`, `tests/test_deepseek_provider.py`, `tests/features/sdk_loop_settings/test_contract.py`, and the rest of `vidbyte/agents/README.md` and `vidbyte/agents/jev/README.md`.

## 3. What the GUESS got wrong

GUESS: `vidbyte/lib/dataclasses/model_configs.py, vidbyte/providers/*.py, vidbyte/agents/base.py, vidbyte/agents/settings/, vidbyte/lib/dataclasses/jev.py, vidbyte/agents/jev/, vidbyte/lib/enums/, vidbyte/__init__.py, contracts/sdk-public-api.json, docs/design/release-0-4-0.md`

- **`vidbyte/providers/*.py` is too broad.**
  - The seven CLI providers resolve to five adapter files: `openai.py`, `anthropic.py`, `gemini.py`, `xai.py`, and `compatible.py`. `compatible.py` holds `DeepSeekProvider`, `GLMProvider` and `MetaProvider`.
  - `xai.py` overrides only images (`:13-57`).
  - "muse" is `ModelProvider.META` (`compatible.py:243-244`), not a Muse adapter.
- **`vidbyte/lib/dataclasses/jev.py` holds no settings.** It holds `JevSpecialist` (`:660-683`). `JevAgentSettings`, `JevRunBriefSettings` and `JevRuntimeSettings` are all in `vidbyte/agents/jev/settings.py`, which is the first placement exception in AGENTS.md.
- **`vidbyte/agents/settings/` matters through two files only.** `fallback.py` makes a string hop inherit `primary.temperature` (`:146`), and `loop.py` is R3's validation pattern (`:82-89`).
- **`vidbyte/lib/enums/` is a folder, not a file.** The relevant files are `codex.py`, `native_threads.py`, `text_model.py` and `model_provider.py`, plus the export list in `__init__.py`. The three existing effort enums differ in base class and in their extra members (code-map §4.1 item 2).
- **`contracts/sdk-public-api.json` is generated, not hand-edited.** `scripts/generate-sdk-public-api.py` writes it and refuses dirty inputs (`:69-72`).
- **`docs/design/release-0-4-0.md` has "733" twice** (`:17` and `:19`).
- **Missed: the runner build path.** `lib/runners/utility.py` drops unknown options at `:134`. `lib/runners/text.py` runs `validate()` at `:48`, at the first `arun`, not at construction.
- **Missed: the agent records and copy paths.** These are `lib/dataclasses/agents.py` (`FallbackModel`, `AgentForkSettings`, `AgentRunnerConfig`), `agents/fallback.py`, `agents/spend_cap.py`, `agents/fork.py`, and the fork tool, which exposes `temperature` to the model (`fork.py:473`). Sessions and serialization (`RunState.temperature`) and the two YAML records with `lib/config/loader.py` are copy paths too.
- **Missed: eight Jev child builders that copy `settings.temperature`, plus the brief writer.**
- **Missed: other files the change crosses.** These are the usage path (`agents/pricing/*`, `tracker.py`, `lib/token_usage.py`), `lib/tools/formatter.py`, `lib/http/vidbyte_gateway.py`, `lib/constants/jev.py`, and `lib/dataclasses/validation.py`.
- **Missed: the only capability-table precedent.** It is `lib/configs/structured_output.py` with `lib/registries/structured_output.py`.
- **Missed: every test that pins this surface.**
  - The gateway allow-list `EMITTED_KEYS` (`test_managed_text_wire_contract.py:46-54`).
  - The `TextModelConfig` field-order pin `EXPECTED_TEXT_CONFIG_FIELDS` (`test_managed_text_selection.py:54-58`, asserted at `:344`).
  - The root-export identity table (`test_jev_cli_root_exports_contract.py:41-54`).
  - The harness surface test, which also scopes `vidbyte/lib/configs` (`:274`).

## 4. What vidbyte-gates.md got wrong or left out

- **Interpreter.** It writes every command with `python`. This workspace uses `py -3.11`, as the orchestrator briefing says.
- **Commands that AGENTS.md does not state.** Its SDK row gives `python -m pip install -e ".[dev]"`, then `python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py`. AGENTS.md states only `python scripts/run_ci.py`. The stage names do exist (`scripts/run_ci.py:261-262`, `choices=("all", "source", "package")`).
- **Worktree `PYTHONPATH`.** Running from a worktree needs `PYTHONPATH=$(pwd)` for `--stage source` and no `PYTHONPATH` for `--stage package`. This comes from the field guide's `local-ci-verification`, and vidbyte-gates.md does not say it.
- **Remote checks.** It says "CI runs the same `run_ci.py`". `request.md:195` says "ci.yml automatic triggers paused; dispatched CI does not attach to PRs", so merges need `gh pr merge --squash --admin`. The local gate is the only gate that runs on a PR.
- **SDK pins it does not mention.** These are the gateway allow-list test (`EMITTED_KEYS`), the `TextModelConfig` field-order pin, the root-export identity contract, and the C016 stale-contract check on `contracts/sdk-public-api.json`. A new `TextModelConfig` field or body key trips them, and none of them is a lint baseline number.

## 5. Independent verification of the code-map

- **Range check.** A shell loop parsed every full `path:line` and `path:a-b` reference in the code-map. It checked that each file exists and that each line number is within the file's length. Result: 0 missing and 0 out of range.
- **Bare paths.** Every backticked repo path without a line number exists.
- **Spot checks.** I printed the source line behind about 70 short-form anchors in §2 and §4 and compared each with its quote. Ten anchors were wrong and are corrected in the file: reflexion `:110-133`, README `:570-572`, `pricing/anthropic.py:36-125` and `:47-58`, `lib/config/loader.py:259`, `jev/agent.py:63-77`, `to_enum` `:230`, `serialization.py:157,185`, `text_model.py:17-22`, and `loop.py:82-89`. An earlier pass corrected about 30 more.
- **Secret scan.** A grep for key-shaped literals (`sk-`, `AIza`, `ghp_`, `xai-`, bearer tokens) in the code-map found nothing. The Gemini test key is cited by line only and not quoted.
- **Repository state.** `git status --short` shows only the untracked `docs/spec/agent-reasoning-effort/context/` and `reports/` files that this stage was told to create.
