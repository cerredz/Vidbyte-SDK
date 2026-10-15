# S5 repair, iteration 1 of 8: byok-api-keys (SDK half)

Branch `feat/byok-api-keys`. Iteration start: 8fcc8c63. Code final: 6ac82305. PR https://github.com/cerredz/Vidbyte-SDK/pull/1027. The per-finding hypotheses, the commit list, and the full gate matrix with final lines are in `verify-log.md` § Iteration 1. This report covers decisions, limitations, and what the next reader should know.

## 1. Outcome

- Every confirmed finding in review.md is closed: R-1, R-6 to R-17, and R-2 to R-5 through their test-pass SHAs. R-18 is deferred by the orchestrator.
- All four red tests are green (T-6, T-7, T-9, T-10). The pack gives `123 passed`, and the source stage gives `4107 passed, 13 skipped`.
- Lint, the package stage, both semgrep commands, and the four review probes all pass locally.
- Remote CI (run 38451268879) and Static policy (run 38451272040) passed on 6ac82305: `Source / Python 3.11`, `Source / Python 3.12`, `Package`, and `Static policy` all succeeded. The docs commit that follows changes only `docs/spec/byok-api-keys/`.
- No test was edited. No baseline was raised, no suppression added, no check loosened.

## 2. Decisions worth checking

1. **R-1 leaves two chains through `normalized_provider()`, base 0.**
   - The briefing's target of zero new chains conflicts with its own fallback clause. I took the fallback:
     - `normalized_provider()` is a four-line try/except that wraps `ValueError` in `ConfigurationError`.
     - No other class offers the same contract: `Runner._normalize_provider` strips, lower-cases, and maps blank to None, and its module imports model_configs.
     - A bare `ModelProvider(self.provider)` would change a DIRECT `"nosuch"` config from `ConfigurationError` to `ValueError`, because DIRECT configs are not provider-checked at construction.
   - The result is the shape §12.4 sanctions and review.md's "Refuted" row 3 accepts.
   - Flip condition: if the orchestrator wants zero chains, the smallest route is to validate the provider in `__post_init__` for every mode, then use `ModelProvider(self.provider)` in `credentials()`. That moves a DIRECT unknown-provider error from `validate()` to construction, which is a behaviour change needing a ruling.
2. **R-10 writer narrowing reads `settings.vidbyte_api_key`, not `cast(...)`.**
   - `JevAgentSettings.__post_init__` stores `matched.vidbyte_api_key` in that field (settings.py:159), so the value is identical, and the read needs neither a cast nor an import.
   - In `credentials()`, one `cast` at the top covers all four read sites.
3. **R-8 lands at 580, not 581.**
   - The extra drop is `fallback._validate_error_types`, which now sits inside the 20-line window of the new `named_providers` block. It is proximity coverage, like `resolved_endpoint`'s.
   - The set diff against base adds nothing.
4. **R-16 brings provider_keys.py to exactly 300 lines.**
   - That is the NFR-4 cap (≤ 300), with no headroom left for R-18 or any later message change in that file.
   - Two lines could be recovered by dropping the blank line before `DUPLICATE_KEY_MESSAGE`. That costs readability, so I did not do it.
5. **R-17 wording.**
   - "…top up the wallet, or, with mode=TextModelMode.AUTO (the default), add your own provider key for {provider} to api_keys so the wallet pays only Vidbyte's fee."
   - It reads correctly in both AUTO without a key and VIDBYTE_MANAGED. It keeps `wallet` and `provider key` for PAID_FACTS and `test_managed_text_failures.py:130`.
   - The transport signature is unchanged.
6. **Spec edits.** These are confined to what each fix requires:
   - §8.5: four annotation lines;
   - §9.1: one sentence;
   - table G: the paid 402 cell;
   - §17: a new "Repair deviations (S5, iteration 1)" list with three bullets (R-6, R-10, R-17).

## 3. Stated limitations (no control added; scope ruling)

- **M-18 in DIRECT for a served provider.** After R-13, the message still says "…or Vidbyte's own openai account", because `ProviderKeyMatcher` never learns the mode. That way out is real only in the gateway modes.
- **R-15 is defense in depth.** No current path dumps request headers. The new `_provider_key` suffix also classifies any future mapping key ending in `provider_key` as a secret. A grep of `vidbyte/` found no non-secret key with that ending.

## 4. Environment notes

- `s014_mut.py` restores with `git checkout -- .`, so run it only on a `git archive` copy with its own `git init`, never on the worktree.
- The remote branch was at 57596097 before this push. The orchestrator's 8fcc8c63 had not been pushed; this push carried it.
- The flaky `test_mcp_stdio_transport` test passed in the one source-stage run.
