# S5 repair, iteration 2: byok-api-keys (SDK half)

Status: DONE. Branch `feat/byok-api-keys`, started at HEAD `d9ef911c` with a clean tree. Inputs: `verify-log.md` iteration 1, `reports/S5-rereview-conformance-1.md` (R-C1 to R-C3), `reports/S5-test-author-2.md` (T-11 to T-13), `pipeline.md` (LE-1 and the rulings), spec r5 (§17, table G, table M's M-18 row, NFR-4), AGENTS.md, and the field guide's `comment-format.md` and `local-ci-verification.md`. No test was edited.

`<sp>` below means `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/5bfc4a32-d2a9-4a4d-a6e5-3f472a0fe403/scratchpad/s5-repair2`.

## 1. Defects in

- At `d9ef911c`:
  - pack `tests/features/sdk_provider_keys`: `2 failed, 124 passed in 1.75s`. The two failures were exactly T-12 (`test_provider_keys_failures.py::GatewayErrorWordingTests::test_a_relayed_provider_400_points_at_the_callers_own_key_in_api_keys_and_a_paid_400_does_not`) and T-13 (`test_provider_keys_security.py::CredentialGuardTests::test_the_bare_name_provider_key_is_a_secret_name_as_the_free_text_redactor_already_treats_it`);
  - `wc -l vidbyte/lib/registries/provider_keys.py`: `300`.
- `vidbyte.__file__` resolved to the worktree (`…\vidbyte-sdk-byok-api-keys\vidbyte\__init__.py`) with `PYTHONPATH="$(pwd)"`.
- A002 at `d9ef911c`: `found 580`, saved as `<sp>/a002_head.json`, so later runs could be set-diffed against it (`<sp>/a002_diff.py`, which compares path and symbol and ignores line numbers).

## 2. Fixes, in commit order

### R-C1 (Major): `a1cea1bd`

- Deleted the blank line at `provider_keys.py:66`, between `RESERVED_PREFIXES` and `DUPLICATE_KEY_MESSAGE`, as the re-review suggested. `DUPLICATE_KEY_MESSAGE` has no comment block of its own, so it now sits directly under the constant before it, and no comment is moved. The two blank lines before `__all__` are the PEP 8 pair and stay.
- `wc -l` now gives `299`, which is under 300 as NFR-4 requires. NFR-4 was not amended.
- R-13's condition `if missing in VIDBYTE_MANAGED_TEXT_PROVIDERS` is intact at `:295`.
- Proof:
  - T-11 alone: `1 passed in 0.67s`;
  - pack: `2 failed, 124 passed in 1.79s` (only the two known reds);
  - `ruff check … --config lint/ruff.toml`: `All checks passed!`.
- The earlier record says "≤ 300" in several places (`reports/S5-repair-1.md:29`, `verify-log.md:92`, `review.md:136`, `pipeline.md:119,135`). Those are history and were not rewritten. The iteration 2 entry in `verify-log.md` states the count as `299 < 300`.

### R-C3 (Minor): `ac5099fb`

- Added `"provider_key"` to `CredentialKeyPolicy._SECRET_KEYS`, after `"apikey"`. Extended the comment over `_SECRET_SUFFIXES` (now 3 lines, each ≤ 72 columns) to say the bare name sits in `_SECRET_KEYS`.
- Effect:
  - `providerKey` and `Provider-Key` normalize to `provider_key` (`credential_keys.py:86-88`), so the one name covers all three spellings;
  - `_YamlSecretKeyPolicy` (`lib/dataclasses/config.py:65`) unions `CredentialKeyPolicy._SECRET_KEYS`, so YAML config rejection follows.
- Blast-radius check: `git grep` finds no `vidbyte/`, `examples/`, `skills/`, or script mapping key or config field named `provider_key`, only local variables. So no existing config is newly rejected and no existing capture is newly scrubbed.
- Proof:
  - T-13 alone: `1 passed in 0.77s`;
  - pack plus `tests/test_harness_redaction.py` and `tests/test_durable_sessions.py`: `1 failed, 263 passed` (the one failure is T-12, still red at that point).

### LE-1 (Major): `76657bba`

- **The change.** In `_GatewayAnswer.failure_reason` (`vidbyte_gateway.py:102-104`), after the `relayed = …` line, a clause is appended, but only when `relays and status == HTTPStatus.BAD_REQUEST`. The clause reads "; some providers answer a wrong API key with HTTP 400, so check your own {provider} key in api_keys or {ENV}".
- **`{ENV}`** is `PROVIDER_API_KEY_ENV_VARS[provider]`, newly imported from `vidbyte.lib.constants.jev`, the module this file already imports from.
  - Why name the variable: AUTO relays the provider's environment variable when no list is passed (review.md, "With no list, AUTO relays `XAI_API_KEY`"). The transport never learns the key's source, and "api_keys" alone would point that developer at a list they never passed.
  - All six gateway-served providers are keys of that table, and M-12 refuses any other provider in a gateway mode at construction.
- **What is kept.** "withheld" and "not billed" stay, no body text is copied, and the `retried` suffix still applies only to 409 and 502.
- **The `@intent relayed-refusal-blames-the-callers-own-key` block** grows from 4 to 7 lines, each ≤ 72 columns. It now says that some providers (xAI, seen live) answer a wrong key with a 400, that a relayed 400 names the caller's own key as one cause, and that a Vidbyte-paid 400 does not, because it answered Vidbyte's own account. No `@intent` block moved.
- **The `vidbyte/lib/constants/jev.py` header** now says that `PROVIDER_API_KEY_ENV_VARS` names each provider's variable "in the key matcher's messages and in the gateway's relayed-400 reason". This keeps the header true, which was the R-12 lesson. jev.py is §12.3 row 2.
- **Probe** (`_GatewayAnswer(HttpResponse(s, <xai-shaped body>, {}), None).failure_reason(XAI, 630, 0, relays)`):
  ```
  True 400 -> xai returned HTTP 400 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed; some providers answer a wrong API key with HTTP 400, so check your own xai key in api_keys or XAI_API_KEY
  True 401 -> xai refused the call made with your own xai key (HTTP 401): … the provider's message is withheld, and Vidbyte did not bill the call
  True 429 -> xai returned HTTP 429 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed
  False 400 -> xai returned HTTP 400 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed
  ```
- **Proof:**
  - T-12 alone: `1 passed in 0.70s`;
  - `tests/features/sdk_provider_keys` plus `tests/features/sdk_managed_text`: `165 passed in 1.87s`;
  - `ruff check` on the four touched source files: `All checks passed!`;
  - A002 set diff against `<sp>/a002_head.json`: `base found 580 now found 580` / `ADDED: []` / `REMOVED: []`.
- **No pinned wording broke.** `git grep "through the Vidbyte gateway|call was not billed"` over tests, scripts, and READMEs finds no test that pins the exact relayed-400 text. No README documents the relayed-status wording.
- **One deviation from the briefing's example wording:** "api_keys or {ENV}" instead of "api_keys". T-12 needs "api_keys", which is still present. The paid control is unaffected.

### R-C2 (Minor) and LE-1's spec rows: `17121734` (`docs(spec): …`)

- **Table M, M-18 (`spec.md:913`).** The message now ends "…to use {ENV}{own}." `{own}` is " or Vidbyte's own {primary} account" only when `{primary}` is in `VIDBYTE_MANAGED_TEXT_PROVIDERS`. The DIRECT limitation is stated, and the facts column adds "Vidbyte's own" only for a served primary.
- **Table G (`spec.md:929`).** A new row, "relayed provider 400", gives the paid text (unchanged) and the relay text, plus the facts T-12 binds.
- **§17:**
  - The R-6 bullet now also says INV-8's order overrides INV-24's "in every mode" (the re-review's related note).
  - A new R-13 bullet sits in the iteration 1 list.
  - A new "Repair deviations (S5, iteration 2)" list holds the LE-1 bullet ("LE-1, found by the live E2E") and a row 14 bullet recording the `_provider_key` suffix (R-15) and the bare `provider_key` (R-C3). Row 14 lists only `api_keys` and `_api_keys`, and §17 had not recorded R-15.
- Frontmatter `status` and `revision` are unchanged, because the orchestrator owns them.

## 3. Gates (all run this iteration, at code `17121734`)

Every source run used `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)"` from the worktree root. Full logs: `<sp>/source.log` and `<sp>/package.log`.

1. **Lint.** `PYTHONIOENCODING=utf-8 … python lint/run.py`:
   ```
   S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

   S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

   SDK-LINT: PASS
   ```
   From the source-stage summary:
   - `A001 641 641 RATCHETED`, `A006 34 34 RATCHETED`, `C017 0 0 CLEAN`, `C020 2 2 RATCHETED`, `S009 350 350 RATCHETED`, `S014 0 0 CLEAN`, and `A002 580 703 IMPROVED`;
   - every IMPROVED line predates this iteration, and `lint/baseline.json` is unchanged.
2. **Source stage.** `python scripts/run_ci.py --stage source`:
   ```
   tests\test_web_operation_client_retry.py ...                             [ 99%]
   tests\test_workflow_agent_forks.py ......                                [100%]

   ====================== 4110 passed, 13 skipped in 35.94s ======================
   CI passed.
   ```
   The flaky `test_mcp_stdio_transport` test did not fail, so no re-run was needed.
3. **Package stage.** `env -u DEEPSEEK_API_KEY -u PYTHONPATH python scripts/run_ci.py --stage package`:
   ```
   No broken requirements found.
   …
   Installed vidbyte-sdk 0.2.1 passed smoke checks.
   CI passed.
   ```
4. **Semgrep** (`semgrep 1.170.1` from the scratch venv):
   - `semgrep --test …`: `1/1: ✓ All tests passed`
   - `semgrep scan --error … vidbyte`: `Ran 1 rule on 894 files: 0 findings.`
5. **Size and A002.**
   - `wc -l vidbyte/lib/registries/provider_keys.py`: `299 vidbyte/lib/registries/provider_keys.py`.
   - A002 set diff of `<sp>/a002_final.json` against `<sp>/a002_head.json`: `base found 580 now found 580` / `ADDED: []` / `REMOVED: []`.
6. **Discipline checks** on `git diff d9ef911c..HEAD`:
   - It touches 5 files: spec.md, jev.py, vidbyte_gateway.py, provider_keys.py, and credential_keys.py (20 insertions, 6 deletions).
   - The `tests/` and `lint/baseline.json` diffs are empty (0 lines).
   - It adds 0 `type: ignore`, `noqa`, or `nosemgrep`.
   - No added `#` line is over 72 columns.
7. **Remote.** See §4.

## 4. Remote checks

- Pushed: `git push origin feat/byok-api-keys` gave `d9ef911c..17121734  feat/byok-api-keys -> feat/byok-api-keys`.
- Dispatched:
  - `gh workflow run CI --ref feat/byok-api-keys` → run 38471474040;
  - `gh workflow run "Static policy" --ref feat/byok-api-keys` → run 38471477788.
- `gh run list --branch feat/byok-api-keys --limit 4 --json …` gave `headSha` `17121734fe59a38910ce8e50cd3474c3bdae94d7` for both runs, which is the pushed HEAD.
- `gh run watch 38471474040 --exit-status` exited 0 (`CI exit=0`). `gh run view 38471474040 --json conclusion,headSha,jobs`:
  ```
  success 17121734fe59a38910ce8e50cd3474c3bdae94d7
  Source / Python 3.12: success
  Source / Python 3.11: success
  Package: success
  ```
- `gh run watch 38471477788 --exit-status` exited 0 (`Run Static policy (38471477788) has already completed with 'success'`). `gh run view 38471477788 …`:
  ```
  success 17121734fe59a38910ce8e50cd3474c3bdae94d7
  Static policy: success
  ```
- The only annotation was GitHub's notice that the `ubuntu-latest` label moves to Ubuntu 26 from 2026-10-19. It is informational and needs no change.
- The docs commit that follows (this report, review.md, and verify-log.md) changes only `docs/spec/byok-api-keys/`. CI and Static policy are dispatched again on that final HEAD, and the result is in this stage's STATUS message, because writing it here would need another commit.

## 5. Niche facts for the next agent

- `provider_keys.py` has 299 lines. Any further line in it must be paid for by removing one, because NFR-4 says "under 300". The blank line the re-review named has already been used.
- In this spec, "under N" means `< N`. Treat a cap stated as "under" as strict.
- The relayed-400 clause names `{ENV}` from `PROVIDER_API_KEY_ENV_VARS[provider]`. A provider missing from that table would raise `KeyError` in the error path. Only the six gateway-served providers reach this transport (M-12), and all six are in the table.
- `_YamlSecretKeyPolicy` unions `CredentialKeyPolicy._SECRET_KEYS`, so a name added there is also refused in YAML configs. Check `git grep` for a config field with that name before adding one.
- A002 is still 580, with the same set as `d9ef911c`. `<sp>/a002_head.json` and `<sp>/a002_diff.py` let you re-diff it.
