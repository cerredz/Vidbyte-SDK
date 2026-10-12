# S0 scout report: managed-generative-models

- **Stage:** S0 scout
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-managed-generative-models` @ `c07529316a5325bce986f84868ecbabb3b7f3056`
- **Output:** `docs/spec/managed-generative-models/context/code-map.md`
- **Commits:** none. **Installs:** none. **Gate runs:** none. **Files created:** only this report and the code map.

## Planned file list (from the areas hint, confirmed with git grep)

**Binding docs and commands**
- AGENTS.md, CLAUDE.md, REPO_MAP.md
- lint/README.md, scripts/run_ci.py, lint/run.py, pyproject.toml (pytest config)

**Request**
- docs/spec/managed-generative-models/request.md (the only file read under docs/)

**Config, constants, enums**
- vidbyte/lib/dataclasses/model_configs.py
- vidbyte/lib/constants/jev.py, vidbyte/lib/constants/__init__.py
- vidbyte/lib/enums/decision_model.py, vidbyte/lib/enums/__init__.py, vidbyte/lib/enums/model_provider.py, vidbyte/lib/enums/usage.py

**Jev managed pattern**
- vidbyte/lib/jev/managed.py
- vidbyte/providers/typesafe.py
- vidbyte/lib/dataclasses/jev.py (header and JevManagedRunScope)

**Registry and HTTP**
- vidbyte/lib/registries/models.py, vidbyte/lib/config/constants.py
- vidbyte/lib/http/transport.py, parser.py, __init__.py

**Runners**
- vidbyte/lib/runners/text.py, streaming_text.py, utility.py, decision.py, types.py
- vidbyte/lib/agents/modality_detector.py

**Adapters**
- vidbyte/providers/openai.py, anthropic.py, gemini.py, compatible.py, openrouter.py, xai.py, client.py, __init__.py, README.md

**Usage (read-only)**
- vidbyte/lib/usage_ledger.py, vidbyte/agents/pricing/tracker.py

**Key-crossing guards (read-only)**
- vidbyte/agents/settings/fallback.py, vidbyte/agents/fork.py, vidbyte/agents/aggregation.py

**Agent wiring (read-only, targeted)**
- vidbyte/agents/runtime.py (retry region), vidbyte/agents/base.py (`_runner_for_model`), vidbyte/agents/fallback.py

**Lint rules and contract**
- lint/rules c017, c018, c019 (header), c020, a001, a002, a006, a007, s014
- lint/core/platform_contract.py, url_flow.py, string_flow.py (parts)
- lint/contracts/vidbyte-platform-contract.json (grep), lint/contracts/README.md, lint/baseline.json (grep)

**Docs**
- README.md (grep), llms.txt (grep), .env.example (absent), CONTRIBUTING.md, .github/pull_request_template.md
- .github/workflows/ci.yml and static-policy.yml (grep), .semgrep/typed-mapping-boundary-policy.yml
- vidbyte/lib/README.md, vidbyte/lib/registries/README.md, skills/jev-agent/SKILL.md (grep)

**Tests**
- tests/test_jev_managed_gateway.py, test_jev_managed_runs.py, test_text_model_runner.py, test_config_validation.py, test_model_registry.py, test_streaming_text_runner.py, test_sync_runner_default_transport.py
- Targeted ranges in test_agent_fork_isolation.py, test_agent_settings_validation.py, test_aggregate_agent.py, test_fork_tool.py, test_multi_provider_agentic_grader.py

**Field guide**
- C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md and local-ci-verification.md

## Files actually read

**In full**
- AGENTS.md, CLAUDE.md, REPO_MAP.md, lint/README.md, request.md
- model_configs.py, constants/jev.py, lib/jev/managed.py, providers/typesafe.py, enums/decision_model.py, enums/__init__.py, constants/__init__.py
- registries/models.py, lib/http/* (all three files)
- runners text.py, streaming_text.py, utility.py, types.py
- modality_detector.py
- providers openai.py, anthropic.py, gemini.py, compatible.py, openrouter.py, xai.py, client.py, __init__.py, README.md
- usage_ledger.py, enums/usage.py
- lint rules c017, c018, c020, a001, a002, a006, a007, s014; lint/core/platform_contract.py
- lint/contracts/README.md, scripts/run_ci.py, lint/run.py, CONTRIBUTING.md, .github/pull_request_template.md, .semgrep/typed-mapping-boundary-policy.yml
- vidbyte/lib/README.md, vidbyte/lib/registries/README.md
- The 5 core test files: test_jev_managed_gateway, test_jev_managed_runs, test_text_model_runner, test_config_validation, test_model_registry
- test_streaming_text_runner.py, test_sync_runner_default_transport.py
- field-guide init.md, local-ci-verification.md

**In part**
- lint/core/url_flow.py; lint/core/string_flow.py (lines 1-40 and 650-740); c019 header
- decision.py, enums/model_provider.py, pricing/tracker.py, dataclasses/jev.py (header and around line 3971), config/constants.py
- agents/runtime.py (around 600-730), agents/base.py:1444-1448, agents/fallback.py:162
- settings/fallback.py:145-156, fork.py:84-96, aggregation.py:329-350
- test_agent_fork_isolation.py:375-420, test_agent_settings_validation.py:1-80
- Greps over the contract JSON, baseline.json, README.md, llms.txt, ci.yml, static-policy.yml, test_aggregate_agent.py, test_fork_tool.py, test_multi_provider_agentic_grader.py

**Not read**
- scripts/test-jev-managed-gateway.py (exists)
- The other test files that `git grep` matched (listed in code-map §3)
- Field-guide entries other than the two above

## What the areas hint or workspace-facts file got wrong or left out

1. **Commands come from other files, not AGENTS.md.** AGENTS.md names only `python scripts/run_ci.py`. The install command `python -m pip install -e ".[dev]"`, the lint command `python lint/run.py`, and `--stage source` come from CONTRIBUTING.md, ci.yml, lint/README.md, and scripts/run_ci.py. AGENTS.md also states no PR or commit conventions; CONTRIBUTING.md and the PR template hold them.
2. **The worktree PYTHONPATH step is undocumented in AGENTS.md.** lint/README.md gives it in PowerShell form, and the field guide's local-ci-verification.md gives the Bash form. The source stage needs `PYTHONPATH=<worktree>`; the package stage needs it unset.
3. **The request's guard line numbers are slightly off.** Actual ranges: fallback.py:147-155 (request says ~142-149), fork.py:85-95 (~85-94), aggregation.py:331-349 (~342-349, which misses `_resolve_key_owner` at 331-340).
4. **The target host is not live.** The hint and request assume `https://api.vidbyte.pro`. The vendored platform contract marks that host `planned`; only `https://vidbyte-backend.onrender.com` is `live`. A new literal on the planned host regresses C018, whose baseline of 1 is the existing Jev constant.
5. **C017 adds a cross-repo sequencing dependency.** A new Vidbyte route cannot pass C017 (baseline 0) until the backend contract is regenerated and re-vendored into lint/contracts/. This conflicts with "independently mergeable and green".
6. **lib already imports providers.** text.py, streaming_text.py, decision.py, and jev/managed.py all do. A006 treats lib and providers as one tier. "lib is the bottom layer" is AGENTS.md prose, not what the lint enforces.
7. **There is no prefix owner constant.** C020 requires a `*API_KEY_PREFIX` owner under vidbyte/lib/constants/. None exists today, and inline `vb_live_` copies remain.
8. **Missing READMEs and notes.** lib/http/ has no README. vidbyte/lib/README.md and vidbyte/providers/README.md have no `## Notes for agents` section. There is no .env.example. README.md and llms.txt have no managed or VIDBYTE_API_KEY content.
9. **A stale header path.** model_configs.py's header names `vidbyte/lib/models/registry.py`, which does not exist. The folder holds only `__init__.py`.
10. **The idempotency guard does not fire on text calls.** The hint's idempotency premise holds only when `retry_count > 0`. Text adapters never set it, and model retries live in agents/runtime.py, outside lib.
11. **Env-resolved Vidbyte keys pass the guards.** The hint asked whether an env-resolved VIDBYTE_API_KEY trips the key-crossing guards. It does not: they filter only explicit keys, and the child resolves from env itself.
12. **The reference test pins the host.** tests/test_jev_managed_gateway.py asserts the api.vidbyte.pro URLs (:120, :154, :163).
