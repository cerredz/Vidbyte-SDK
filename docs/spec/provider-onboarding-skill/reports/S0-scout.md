# S0 scout report: provider-onboarding-skill

- Stage: S0 scout.
- Date: 2026-10-15.
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill`, HEAD `72a4ade1` (= origin/main), no commits on the branch.
- Output: `docs/spec/provider-onboarding-skill/context/code-map.md`. It has 4 `## ` headings and every subsection uses `###`.
- Nothing else was created or modified.
- I made no commits, installs, gate runs, pytest runs or `lint/run.py` runs.
- The only network calls were the two allowed `gh pr list` calls.

## Planned list (built before reading, then extended by tracing)

1. Rules: `AGENTS.md`, `REPO_MAP.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`, `.github/workflows/*` (ci, static-policy, actionlint, publish, agents-md-placement, claude), `.github/actions/claude-setup/action.yml`, `.claude/ci-settings.json`, `pyproject.toml`, `scripts/run_ci.py`.
2. Lint:
   - `lint/core/discovery.py` and `lint/core/ruff.py`;
   - the rules A001, A009, S020, S054, S062, C015, C009, C010, S014, C012 and C020;
   - `lint/baseline.json`;
   - `lint/pricebook_vintage_lock.json`;
   - `lint/README.md`.
3. The skill-folder precedent: `skills/README.md`, the frontmatter of two SKILL.md files, the `skills/codex-harness-roadmap/` layout, and commit `336fe4ec` (stat).
4. Per-provider wiring, traced with `git grep -i kimi|moonshot|mistral|meta` and `git show --stat 81bced94 661a9444`:
   - `vidbyte/lib/enums/model_provider.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/registries/models.py`, `vidbyte/lib/constants/runners.py`;
   - `vidbyte/lib/enums/model_modality.py`, `vidbyte/lib/agents/modality_detector.py`;
   - `vidbyte/providers/compatible.py`, `vidbyte/providers/__init__.py`;
   - `vidbyte/lib/registries/pricing.py`, `vidbyte/lib/registries/provider_keys.py`, `vidbyte/lib/registries/README.md`;
   - `vidbyte/lib/configs/structured_output.py`, `vidbyte/lib/registries/structured_output.py`;
   - `vidbyte/lib/dataclasses/model_configs.py`, `vidbyte/lib/enums/text_model.py`;
   - `vidbyte/lib/tools/formatter.py`, `vidbyte/agents/pricing/compatible.py`, `vidbyte/lib/http/parser.py`, `vidbyte/lib/http/transport.py`;
   - `vidbyte/lib/runners/utility.py`;
   - `vidbyte/providers/README.md`, `README.md`;
   - `skills/usage/create_agent.md`, `skills/sdk/update-skill-files.md`;
   - the MCP preset mentions of mistral (`vidbyte/lib/config/mcp_presets.py:1484`, `vidbyte/tools/mcp/presets.py`), which are unrelated: they name the Mistral MCP server's `MISTRAL_API_KEY`.
5. Tests:
   - all of `tests/features/sdk_provider_keys/`;
   - `tests/features/sdk_managed_text/managed_text_fixtures.py` and `test_managed_text_selection.py`;
   - `tests/features/sdk_model_catalog/test_catalog_pricing_contract.py`;
   - `tests/test_agent_pricing.py`, `tests/test_compatible_provider_text.py`, `tests/test_output_schema_provider_dialect.py`, `tests/test_agent_settings_validation.py`, `tests/test_agent_modality_routing.py`, `tests/test_model_registry.py`, `tests/test_readme_size_limit.py`;
   - `tests/features/harness_threads/test_harness_threads_surface.py` (header and git seam only);
   - the REPO_MAP-reading tests in `tests/features/agent_output_connectors/`.
6. Allowed docs: `docs/spec/provider-onboarding-skill/request.md` and, under `docs/spec/byok-api-keys/`, spec.md, request.md, review.md, verify-log.md, pr-body.md and test-plan.md.
7. Field guide: `field-guide/vidbyte-sdk/init.md` plus provider-api-contracts, local-ci-verification, declarative-config-resolution, blocking-lint-invariants, comment-format, review-scope, diagnostic-context and operation-pricebook-rates. Also the spec-pipeline `references/vidbyte-gates.md` and the memory `sdk-main-known-red-tests.md`.
8. `gh pr list`: both allowed calls.

## Files actually read

**In full:**

- `AGENTS.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`, `.claude/ci-settings.json`, `pyproject.toml`, `scripts/run_ci.py`, `skills/README.md`
- `lint/core/discovery.py`
- `vidbyte/lib/enums/model_provider.py`, `vidbyte/lib/registries/provider_keys.py`, `vidbyte/lib/registries/README.md`, `vidbyte/lib/registries/models.py`, `vidbyte/lib/constants/runners.py`, `vidbyte/providers/compatible.py`, `vidbyte/providers/__init__.py`
- `vidbyte/lib/enums/model_modality.py`, `vidbyte/lib/agents/modality_detector.py`, `vidbyte/lib/registries/pricing.py`, `vidbyte/lib/enums/text_model.py`, `vidbyte/lib/configs/structured_output.py`
- `tests/features/sdk_provider_keys/` README.md, FEATURE.md, `provider_keys_fixtures.py`, `test_provider_keys_matching.py`, `test_provider_keys_property.py`, `test_provider_keys_modes.py` and `test_provider_keys_contract.py`
- `tests/features/sdk_managed_text/managed_text_fixtures.py`
- `docs/spec/provider-onboarding-skill/request.md`
- the field-guide entries listed above

**In part, with the reason:**

- `REPO_MAP.md`: the entries for root, `.claude/`, `docs/`, `skills/` and `vidbyte/providers/`. It is a long map, and only these entries bind the change.
- `vidbyte/lib/constants/jev.py` (790 lines): the header and lines 60-121, the gateway set and the key-variable table. The rest is TypeSafe Jev policy.
- `vidbyte/lib/dataclasses/model_configs.py`: lines 1-260, which cover the TextModelConfig mode default, `__post_init__` and `_require_gateway_shape`.
- `vidbyte/providers/README.md`: lines 55-114, 362-430 and 596-619 (contract, matrix, docs table, Meta and Mistral maps, invariants, "Adding A Provider"), plus the heading list and character count.
- The lint rules S014, C009, C010, C012, C015, C020, A001, A009, S020, S054 and S062: headers and the detection or analyzer code that matters for providers.
- `lint/pricebook_vintage_lock.json`: shape and the first entries.
- `lint/baseline.json`: the relevant counts.
- `vidbyte/lib/registries/structured_output.py`, `vidbyte/lib/tools/formatter.py:35-85` and `vidbyte/lib/runners/utility.py:60-82`.
- The `sdk_provider_keys` acceptance, wire_contract, agents, failures, security and sessions modules: header, constants and every provider enumeration found with `grep`, plus the full DIRECT-golden test (`acceptance:216-256`) and the wire-contract constants (`:1-90`). I skimmed them for provider lists and seams rather than reading every assertion, because none of them enumerates all providers. The wire contract covers served providers only.
- `tests/features/sdk_model_catalog/test_catalog_pricing_contract.py`: lines 1-160 and 355-382, plus the test index.
- `tests/test_compatible_provider_text.py`: the header and the test index.
- `tests/test_agent_pricing.py:116-140`, `tests/test_agent_settings_validation.py:205-225`, `tests/test_model_registry.py:50-65` and `tests/features/sdk_managed_text/test_managed_text_selection.py` (header, `:135-160`, `:245-261`).
- The byok docs: the verify-log head (gate set), pr-body Verification, Deviations and Follow-ups, test-plan §3 and §4, the review findings table, and the spec lines found by grepping for table F, table A, D-19, D-28 and NFR-4. I skimmed them as the briefing allowed.

**Read before the context compaction and not reopened:**

- `.github/workflows/*` and `.github/actions/claude-setup/action.yml`
- `lint/core/ruff.py` (re-anchored at `:68`)
- `skills/codex-harness-roadmap/`
- `field-guide` init and its entries
- commit stats for `336fe4ec`, `72a4ade1`, `81bced94` and `661a9444`

**Not read:** any other `docs/` file, which is outside the briefing. `vidbyte/agents/pricing/*` beyond the grep hits, because it needs no per-provider change: the usage class comes from the enum map. `vidbyte/lib/http/transport.py` beyond its one Kimi comment at `:240`.

## What the areas hint and the workspace-facts file got wrong

**`request.md` (the briefing's hints):**

1. **"`Existing Meta wiring`" (`request.md:56`) is incomplete.** It names 9 places. The trace finds about 30 to 37 touch points; code-map §2b lists them. The missing ones:
   - `_usage_class_map` (`model_provider.py:54-74`);
   - `PROVIDER_DEFAULT_RUNNER_TYPE_MAP` and `MODEL_PREFIX_RUNNER_TYPE_MAP`;
   - `structured_output.py` `PROVIDER_SUPPORT`;
   - `PRICING_AS_OF` plus `lint/pricebook_vintage_lock.json` (C010) plus the vintage pin `test_catalog_pricing_contract.py:376-379`;
   - `UNMANAGED_TEXT_PROVIDERS`;
   - the pinned table F test `test_provider_keys_contract.py:70-75`;
   - `VENDOR_BASES`;
   - the root, providers and skills docs.

   "The pricing package" in that list means `vidbyte/lib/registries/pricing.py`. `vidbyte/agents/pricing/` needs no change.
2. **Table A's "any" row** is described as part of `FORMAT_BOUND_PROVIDERS` (`request.md:37,93`). It is not in the code. The row lives only in the registries README (`:64`). In code it is the fall-through `True` in `accepts_unproven` (`provider_keys.py:105`).
3. **"Follow the repo's rule for unpriced models"** (`request.md:38`) assumes an unpriced path exists for a new provider. C009 (baseline 0) requires the **default** text model to be priced. Its only exemption is OpenRouter's per-response cost (`c009_default_model_priced.py:29-31`). The "omit unverifiable rates" rule (`pricing.py:61-64`) covers only non-default models.
4. **"Ruff S105 flags any string constant whose name contains TOKEN/SECRET/PASSWORD"** (`request.md:81`). This holds only under `vidbyte/`. The lint core runs ruff on `pyproject.toml vidbyte` alone (`lint/core/ruff.py:68`), so tests and `.claude/` are not scanned.
5. **"check how `.claude/` interacts with lint, packaging ..., and any repo map"** (`request.md:103`). The answers:
   - Lint reaches `.claude/` only through tracked `.py` files (A001 and S062) and files named `README.md` (A009, and S020 when opted in).
   - Packaging excludes it (`include = ["vidbyte*"]`, no MANIFEST.in).
   - The `REPO_MAP.md:9-11` `.claude/` entry becomes stale, since it describes only CI settings.

**`~/.claude/skills/spec-pipeline/references/vidbyte-gates.md`:**

6. **"CI runs the same `run_ci.py`; semgrep is part of it."** Wrong on both counts. `run_ci.py` has no semgrep step (`scripts/run_ci.py:79-115`). CI and Static policy are dispatch-only (`.github/workflows/ci.yml:4-8`, `static-policy.yml:4-6`).
7. **"Final line must read `AGENT-LINT: PASS`".** The SDK lint prints `SDK-LINT: PASS` (`lint/core/report.py:58`). AGENT-LINT is the `vidbyte/` backend's wording.

**Memory `sdk-main-known-red-tests.md`:**

8. It does not mention that the harness-threads test **skips** when `origin/main` is missing, as in a shallow clone (`test_harness_threads_surface.py:5,103`). On a fresh full clone it still fails.

**`REPO_MAP.md` (repository text, not a hint, noted for the next agent):**

9. The `.claude/` entry says interactive sessions do not load it and that it forbids every `git push`. Both statements are true only of `ci-settings.json` as loaded by `claude.yml:50`. They are not true of project skills.
