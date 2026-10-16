# S0 scout report: byok-api-keys (SDK)

- Stage: S0 scout. Read-only.
- Base: `52aab816` on `feat/byok-api-keys`. HEAD: no commits.
- Output: `docs/spec/byok-api-keys/context/code-map.md`, with four `##` sections.
- This scout ran no installs, tests, lint, or gate. The only executed code was a scratch script in the session scratchpad. It re-implemented the four credential-name policies from their source and read the harness regex from `vidbyte/harnesses/serialization.py:70` with `ast.literal_eval`. It did not import vidbyte.

## Planned list

I built the plan from request §0, §B.2, §B.4, §C, and the orchestrator briefing, then confirmed each entry with `git grep`.

- **Lib.**
  - `vidbyte/lib/enums/text_model.py`
  - `vidbyte/lib/dataclasses/model_configs.py`
  - `vidbyte/lib/registries/models.py`
  - `vidbyte/lib/registries/pricing.py` (the pricebook question)
  - `vidbyte/lib/constants/jev.py`
  - `vidbyte/lib/http/vidbyte_gateway.py` and `vidbyte/lib/http/parser.py`
  - `vidbyte/lib/runners/text.py`, `streaming_text.py`, `utility.py`, and `router.py`
  - `vidbyte/lib/agents/modality_detector.py`
- **Agents.**
  - `vidbyte/agents/base.py`
  - `vidbyte/lib/dataclasses/agents.py`
  - `vidbyte/agents/fallback.py`, `vidbyte/agents/settings/fallback.py`, and `vidbyte/agents/fork.py`
  - Found by the grep: `vidbyte/agents/aggregation.py`, `continual_trace.py`, and `handoff.py`, plus the Jev settings and their consumers
  - `vidbyte/sessions/session.py` and `fork_recovery.py`
  - The `context_minimal_fanout` paradigm
- **Guards.**
  - `vidbyte/lib/util/credential_keys.py`
  - `vidbyte/lib/dataclasses/config.py`
  - `vidbyte/lib/dataclasses/agent_descriptor.py`
  - `vidbyte/harnesses/serialization.py`
  - `vidbyte/sessions/serialization.py`
  - The `base.py` trace scrubbers
- **Lint.** `lint/rules/c017`–`c020`, `a001`, and `a009`; `lint/run.py` flags; `lint/core/discovery.py`; `lint/core/report.py`; `lint/baseline.json`; `lint/contracts/vidbyte-platform-contract.json` (the route entry and the prefix).
- **Tests.** Every file in `tests/features/sdk_managed_text/`, and the module tests that pin key inheritance and scrubbing.
- **Docs.** The `README.md` managed section, `vidbyte/agents/README.md`, `llms.txt`, the folder READMEs, `REPO_MAP.md`, and `AGENTS.md`.

## Files actually read

**In full:**
- `AGENTS.md`
- `request.md`
- `REPO_MAP.md` (the lib entries reread)
- `vidbyte/lib/dataclasses/model_configs.py`
- `vidbyte/lib/enums/text_model.py`
- `vidbyte/lib/registries/models.py`
- `vidbyte/lib/registries/pricing.py`
- `vidbyte/lib/constants/jev.py`
- `vidbyte/lib/http/vidbyte_gateway.py`
- `vidbyte/lib/runners/text.py`, `streaming_text.py`, `utility.py`, and `router.py`
- `vidbyte/lib/agents/modality_detector.py`
- `vidbyte/lib/dataclasses/agents.py`
- `vidbyte/agents/fallback.py`, `vidbyte/agents/settings/fallback.py`, and `vidbyte/agents/fork.py`
- `vidbyte/lib/util/credential_keys.py`
- `vidbyte/sessions/serialization.py`
- `vidbyte/harnesses/serialization.py`
- `vidbyte/lib/dataclasses/config.py`
- `vidbyte/lib/dataclasses/agent_descriptor.py`
- In `tests/features/sdk_managed_text/`: `FEATURE.md`, `README.md`, `managed_text_fixtures.py`, `test_managed_text_selection.py`, `test_managed_text_acceptance.py`, and `test_managed_text_wire_contract.py`
- `lint/rules/c020_api_key_prefix_contract.py`
- `vidbyte/lib/README.md` and `vidbyte/lib/registries/README.md`
- The relevant field-guide topics: init, local-ci-verification, blocking-lint-invariants, fallback-coordination, strict-config-dataclasses, prebuilt-agents, comment-format, class-bound-helpers, provider-api-contracts, and review-scope

**In part (the key-relevant regions, by grep and line windows):**
- `vidbyte/agents/base.py`, which is 1,725 lines: `__init__`, `restore`, `_runner_for_model`, the trace scrubbers, and the capabilities guard
- `vidbyte/agents/aggregation.py`, the key-owner methods
- `vidbyte/agents/jev/settings.py`
- `vidbyte/sessions/session.py`
- The `context_minimal_fanout` `types.py` and `paradigm.py`
- `vidbyte/providers/typesafe.py` and `vidbyte/providers/tracing/langsmith.py`, the redaction regexes
- `vidbyte/lib/dataclasses/runner.py` and `vidbyte/lib/enums/model_provider.py`
- `vidbyte/lib/config/__init__.py` and `vidbyte/lib/enums/__init__.py`, the exports
- `test_managed_text_failures.py` (`:1-175`) and `test_managed_text_deadline.py` (its header and test list)
- The C017, C018, C019, A001, and A009 rule headers and logic
- `lint/core/discovery.py`, `lint/core/report.py`, and `lint/run.py`
- The `scripts/run_ci.py` stages
- `.github/workflows/static-policy.yml` and `.semgrep/typed-mapping-boundary-policy.yml`
- `pyproject.toml`, the pytest settings
- `README.md:205-300`
- `vidbyte/agents/README.md:145-185`
- The `llms.txt` grep hits
- `tests/test_model_registry.py:50-61`

**Not read, by instruction:** anything else under `docs/`, the backend repo, and the companion worktree.

## What the areas hint and vidbyte-gates.md got wrong

**`vidbyte-gates.md`** (`C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`) has three errors:
1. It says "Final line must read `AGENT-LINT: PASS`". The SDK prints `SDK-LINT: PASS` (`lint/core/report.py:58`).
2. Its SDK row says "CI runs the same `run_ci.py`; semgrep is part of it". Semgrep is NOT in `scripts/run_ci.py`, whose source stage is lint, compileall, three check scripts, and pytest. It runs only in `.github/workflows/static-policy.yml:24-30`.
3. Its SDK gate column runs `run_ci.py --stage source` and then `run_ci.py`, which re-runs the source stage. In a worktree, the field guide's split is right: source stage with `PYTHONPATH`, package stage without it.

**The request's implementation hints and the briefing** were mostly accurate. These items were off or missing:
- **Pricebook.** Prompt 5 suggests the pricebook could match keys. It cannot: `ModelPricingRegistry.resolve` takes a provider. Model→provider comes from `provider_for_model`, which reads the runner maps.
- **Agents-layer list.** The hints name `fork.py`, `settings/fallback.py`, and `fallback.py` only. The provider-key surface also covers:
  - `AggregateAgent`, which has its own key-owner rule
  - `ContinualTraceAgent` and `HandoffAgent`
  - `JevAgentSettings` and `JevRunBriefSettings`
  - `Session.resume`, `continue_`, and `fork_from`, and `fork_recovery`
  - The paradigm role settings
  - `Runner._config_options_for`, which passes the agent key to the image, video, audio, and embedding configs
- **"Every existing test" unchanged.** B.4's list of things that do not change ends with "every existing test". On the SDK side, the managed-text pack pins today's BYOK-wins AUTO behavior and the `api_key=vb_live_…` switch, so the new AUTO must change those tests.
- **Header precedent.** The hints say the header name is "mirrored as a constant". The precedent is `JEV_MANAGED_RUN_ID_HEADER` (`jev.py:55`). The contract JSON carries no header names, which confirms §B.4 step 1.
- **New-file visibility.** Neither source mentions it: lint, like semgrep, scans only `git ls-files` (`lint/core/discovery.py:76-85`). A new file is invisible to lint until it is `git add`ed.
- **C020 scope.** Neither source says this: C020 does not flag provider prefixes such as `sk-ant-`, `xai-`, or `AIza`. It flags any literal containing `vb_live_`, including an error message.
