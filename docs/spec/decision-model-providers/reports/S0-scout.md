# S0 scout report: decision-model-providers

## Planned file list (from AGENTS.md, REPO_MAP.md JEV table, request §C, and `git grep` for `TYPESAFE`, `JevUsage`, `run_decision`, `DecisionModelConfig`, `logprob`)

vidbyte/lib/enums/{model_provider,decision_model,jev,usage,__init__}.py; vidbyte/lib/dataclasses/{model_configs,jev}.py; vidbyte/lib/config/{models,__init__}.py; vidbyte/lib/constants/{jev,runners}.py; vidbyte/lib/registries/{models,pricing,operation_pricing,structured_output}.py; vidbyte/providers/{__init__,typesafe,compatible,openai,anthropic,gemini,xai,openrouter,base,client}.py; vidbyte/lib/runners/{decision,embedding,types,utility,__init__}.py; vidbyte/lib/jev/decision.py; vidbyte/lib/usage_ledger.py; vidbyte/agents/pricing/{base,tracker,records,typesafe,__init__}.py; vidbyte/agents/jev/{settings,runtime,usage,decision_failures,preflight,__init__}.py; vidbyte/lib/http/{transport,parser}.py; vidbyte/lib/errors/{base,__init__}.py; AGENTS.md; REPO_MAP.md; CONTRIBUTING.md; pyproject.toml; lint/README.md; lint/rules/README.md; lint/baseline.json; lint rule files; scripts/run_ci.py; .semgrep/*; skills/jev-agent/SKILL.md; tests named in headers.

## Files actually read in this session (full unless noted)

- Rules/docs: AGENTS.md (73 lines, full, twice); REPO_MAP.md (lines 71-84, 179-200, 255-262, 345-384; headings index); CONTRIBUTING.md (full earlier; lines 28-36, 51-72 re-read); lint/README.md; lint/rules/README.md; scripts/run_ci.py; pyproject.toml; .github/workflows/ci.yml; .semgrep/typed-mapping-boundary-policy.yml; skills/jev-agent/SKILL.md (185 lines); vidbyte/providers/README.md; vidbyte/lib/registries/README.md; vidbyte/agents/jev/README.md; request.md (full, twice); vidbyte-gates.md (full, twice); field guide init.md plus provider-api-contracts, operation-pricebook-rates, strict-config-dataclasses, blocking-lint-invariants, local-ci-verification, declarative-config-resolution, class-bound-helpers, jev-capability-layout (headings + checks), review-scope, runtime-boundaries.
- Lint rules read in full: a001, a002, a003, a006, a007, c004, c005, c017, c018, c019, c020, s010, s011, s012, s013, s014, s015, s016, s020, s021, s042, s056, s060; one-line PURPOSE of every other rule file; lint/baseline.json.
- Source read in full: vidbyte/lib/enums/{model_provider,decision_model,usage,jev,__init__}.py; vidbyte/lib/dataclasses/model_configs.py; vidbyte/lib/dataclasses/jev.py (lines 1-4435 across two passes; records 231-495 re-read with line numbers); vidbyte/lib/config/{models,__init__,constants}.py; vidbyte/lib/constants/{jev,runners}.py; vidbyte/lib/registries/{models,pricing,operation_pricing}.py (structured_output.py head only); vidbyte/providers/{__init__,typesafe,compatible,openai,xai,openrouter,anthropic,gemini,base,client}.py; vidbyte/lib/runners/{decision,embedding,types,utility,__init__}.py; vidbyte/lib/jev/{decision,managed,__init__}.py; vidbyte/lib/usage_ledger.py; vidbyte/agents/pricing/{base,tracker,records,typesafe,__init__}.py; vidbyte/agents/jev/{settings,runtime,usage,decision_failures,preflight,__init__}.py; vidbyte/lib/http/{transport,parser}.py; vidbyte/lib/errors/{base,__init__}.py; targeted ranges of vidbyte/agents/jev/gate/gate.py, compute/recognizer.py, done/run_state.py, response.py, vidbyte/lib/jev/done/expert_depth.py, vidbyte/__init__.py.
- Tests read in full: tests/test_jev_agent.py, test_jev_managed_gateway.py, test_jev_managed_runs.py, test_jev_usage_ledger.py, test_jev_preflight.py, test_embedding_runner.py, test_model_registry.py, test_agent_pricing.py, test_deepseek_provider.py, test_openrouter_provider.py, tests/agent_test_support.py, tests/features/sdk_model_usage/*, tests/features/sdk_operation_costs/FEATURE.md; scripts/test-jev-agent-scaffold.py, scripts/test-jev-managed-gateway.py; tests/test_jev_done.py header only.
- Not read: anything under docs/ except request.md; docs/design/* named in headers (recorded as pointers); docs/spec/decision-model-providers/context/provider-research.md (research scout's file).

## What the AREAS_HINT / gates reference / request got wrong or that needed correction

1. The field guide is not inside the worktree (`ls field-guide` fails there); it lives at `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`. The gates reference's `<vidbyte-repos-root>/field-guide/<repo>/init.md` path is correct.
2. AGENTS.md contains a single command (`python scripts/run_ci.py`, line 11 under "Repository Map"). Install/lint/stage commands come from CONTRIBUTING.md "Development Setup"/"Verification" and lint/README.md; the request's gate list is right but attributes them to AGENTS.md.
3. `AGENT-LINT: PASS` (gates reference) is not a literal found by `git grep` in lint/, scripts/, CONTRIBUTING.md, or AGENTS.md; recorded as unverified.
4. Request §C "Constraints" invents a "boolean" question kind distinct from "noul". Code: NOUL is the boolean kind (true/false options, `noul` = P(true), no confidence); CHOICE is the kind the request omits.
5. Request names `vidbyte/lib/config/models.py` as a definition site; it is a re-export of `vidbyte/lib/dataclasses/model_configs.py`.
6. REPO_MAP.md:374, skills/jev-agent/SKILL.md:46 and vidbyte/lib/jev/done/expert_depth.py:5 attribute `score_noul` to `DecisionModelRunner`; it lives on `DecisionModelHelper` (vidbyte/lib/jev/decision.py:35).
7. `tests/conftest.py` does not exist (summary of an earlier attempt to read it).
8. No test references the runner-catalog maps directly; S014 (baseline 0) is the only guard, and it also demands `DEFAULT_PROVIDER_MODELS`/`API_KEY_ENV_VARS`/`DEFAULT_ENDPOINTS` entries per enum member.
9. `git grep -i logprob` is empty: nothing in the repo handles log-probabilities or constrained yes/no from a chat model.
10. The `claude --cloud` sentence in the briefing was ignored as instructed.

## Output

- `docs/spec/decision-model-providers/context/code-map.md` (four numbered sections).
- This report. No other files created or modified; no commits, installs, or gate runs. `git status --short` shows only the untracked `docs/spec/` tree.
