# S0 scout report: meta-muse-managed-text

- Stage: S0 scout
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`
- Branch and HEAD: `feat/meta-muse-managed-text` at `845a4d9b`. The scout made no commits.
- Output: `docs/spec/meta-muse-managed-text/context/code-map.md`
- Files created: 2 (`code-map.md` and this report). Nothing else was modified. The scout ran no installs and no gates.

## Planned file list (before reading)

- **Production code:**
  - `vidbyte/lib/constants/jev.py`
  - `vidbyte/lib/dataclasses/model_configs.py`
  - `vidbyte/lib/http/vidbyte_gateway.py`
  - `vidbyte/lib/runners/text.py`
  - `vidbyte/lib/runners/streaming_text.py`
  - `vidbyte/providers/compatible.py`
  - `vidbyte/lib/registries/{models,provider_keys,pricing}.py`
  - `vidbyte/lib/dataclasses/agents.py` (`ProviderKeys`)
  - `vidbyte/lib/constants/runners.py`
- **Docs:** `README.md` (the managed section), the folder READMEs on the path, `llms.txt`, `REPO_MAP.md`, and `artifacts/file_index.md`.
- **Tests:** `tests/features/sdk_managed_text/*` and `tests/features/sdk_provider_keys/*`.
- **Allowed docs:** `request.md`, `context/wire-contract.md`, and `docs/spec/byok-api-keys/spec.md` (gateway, mode, relay, and table G rules only).

## Files actually read

- **Rules:**
  - `AGENTS.md`, all 81 lines, and the worktree `CLAUDE.md` (it contains only `@AGENTS.md`).
  - `REPO_MAP.md`, `artifacts/file_index.md`, and `llms.txt`, by grep for gateway terms. None of them has a gateway entry.
- **Production code, read in full:**
  - `vidbyte/lib/constants/jev.py`
  - `vidbyte/lib/dataclasses/model_configs.py`
  - `vidbyte/lib/http/vidbyte_gateway.py`
  - `vidbyte/lib/runners/text.py`
  - `vidbyte/providers/compatible.py`
  - `vidbyte/lib/registries/provider_keys.py`
  - `vidbyte/lib/registries/pricing.py`
- **Production code, read in the relevant parts:**
  - `vidbyte/lib/registries/models.py`
  - `vidbyte/lib/runners/streaming_text.py`
  - `vidbyte/lib/enums/text_model.py`
  - `vidbyte/lib/dataclasses/agents.py` (`ProviderKeys`)
  - `vidbyte/providers/__init__.py`
  - `vidbyte/lib/constants/runners.py`
  - `vidbyte/lib/configs/structured_output.py`
  - `vidbyte/lib/enums/model_provider.py`
  - `lint/pricebook_vintage_lock.json`
  - `lint/rules/a009_readme_size_limit.py`
- **Docs:**
  - `README.md`: the managed section (:236-383) and the key-prefix bullets.
  - `vidbyte/providers/README.md`, `vidbyte/lib/registries/README.md`, and `vidbyte/lib/README.md`.
- **Tests:**
  - Every file in `tests/features/sdk_managed_text/`, including `FEATURE.md` and `README.md`. `test_managed_text_failures.py` was read only around its `MANAGED_MODELS` use.
  - From `tests/features/sdk_provider_keys/`: `FEATURE.md`, the fixtures, and the modes, wire-contract, failures, matching, and contract tests.
  - Cross-checks by grep: `test_catalog_pricing_contract.py`, `test_agent_pricing.py`, `test_agent_fork_isolation.py`, and `test_agent_settings_validation.py`.
- **Field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`):
  - local-ci-verification
  - comment-format
  - provider-api-contracts
  - operation-pricebook-rates
  - review-scope
  - blocking-lint-invariants
  - strict-config-dataclasses
  - declarative-config-resolution
  - agents-md-map
- **Gates file:** `~/.claude/skills/spec-pipeline/references/vidbyte-gates.md`.
- **Allowed docs:**
  - `request.md` and `context/wire-contract.md`, read in full.
  - From `docs/spec/byok-api-keys/spec.md`: §6.1 (:304-371), EC-15 and EC-30 (:436, :451), §8.1 (:548-584), and §9.2 (:797-931). From §13, only the opening framework lines and one grep for served-provider rows.

## Deviations to disclose

- **One grep went outside the allowed `docs/` files.** The scout's first `git grep -n VIDBYTE_MANAGED_TEXT_PROVIDERS` had no `':!docs'` exclusion. It printed matching lines from these files:
  - `docs/spec/byok-api-keys/{context/code-map.md, reports/*, request.md, review.md, test-plan.md, verify-log.md}`
  - `docs/spec/managed-generative-models/{reports/*, spec.md}`

  The scout did not open those files, and the code map uses no fact from those lines. Every later grep excluded `docs/`.

## What the hints and the gates file got wrong

- **Request §C and the wire contract §9.2:** they say every `meta` gateway call "answers `output_cap_missing`" unless Run B adds a cap. That is wrong for SDK traffic. `TextModelRunner` sets the cap to 32,768 in every gateway mode (`text.py:57-62`), so `MetaProvider` already sends `max_tokens`. Only a field added through `extra_body` is left to the gateway.
- **Request implementation hint:** it says to model the change on Kimi and DeepSeek. Only Kimi is the same shape: a bare `OpenAICompatibleProvider` subclass. DeepSeek overrides `_extract_chat_text`.
- **Request open question,** whether there is "a gateway-path model/endpoint map, a request builder, a cap rule … or an export": the scout found none. In code, the only gate is the set at `jev.py:74-81`, read at `model_configs.py:204` and `provider_keys.py:308`. Docs and tests must change (code-map §2 and §3).
- **`vidbyte-gates.md` SDK row:** it writes `python`. On this machine the command must be `py -3.11` (request.md §C). The row also does not say that `PYTHONPATH` must be unset for the full `run_ci.py` run and for `--stage package`. The field guide (`local-ci-verification.md:5`) and request.md do say so.
- **`AGENTS.md`:** it names only the full gate. It states no install, lint, test, PR, or commit commands. Those came from the gates file, the test-file headers, and the test-pack `FEATURE.md` files.
- **`llms.txt`, `REPO_MAP.md`, and `artifacts/file_index.md`:** none of them lists the served providers, so the change needs no map edit.

## Unverified items (also marked in the code map)

- The pytest and pytest-asyncio versions, and `testpaths` (the scout did not open `pyproject.toml`).
- Whether Muse's maximum output is at least 32,768 tokens.
- Whether Meta accepts `metadata`, and whether `max_tokens` counts reasoning tokens.
- Which providers `test_managed_text_failures.py` iterates.
- The known red tests on pristine main.
