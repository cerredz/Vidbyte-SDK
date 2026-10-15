# Verification log: Agents take vidbyte_api_key and a list of provider api_keys (SDK half)

Gate set (from context/code-map.md §1). Every command runs from the worktree root. Source commands run as `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" …`, with a forward-slash path; the global `vidbyte` is an editable install of the main checkout.

1. **Lint (local).** `PYTHONIOENCODING=utf-8 python lint/run.py` must print `SDK-LINT: PASS`.
2. **Source stage (local).** `python scripts/run_ci.py --stage source` must print `CI passed.`.
3. **Package stage (local).** `python scripts/run_ci.py --stage package`, run WITHOUT PYTHONPATH, must print `CI passed.`.
4. **Semgrep (local)**, using the scratch semgrep venv on PATH. Both must report 0 findings:
   - `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`
   - `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
5. **Review probes (local).** Each lives in `<verify>` = the S4 verifier's scratch `s4-sdk/verify`:
   - R-1: `calldepth.py vidbyte/lib/dataclasses/model_configs.py TextModelConfig,TextCredentials`;
   - R-8: the A002 finding set diffed against `a002_base.json`;
   - R-9: `s014_mut.py <archive copy> head`;
   - R-10: `mypy --config-file lint/mypy.ini --follow-imports=silent probe/typing_probe.py`, plus `lint/run.py --rule S009`.
6. **Remote.** Push, then dispatch `gh workflow run CI` and `gh workflow run "Static policy"` (this repo's PRs get no automatic checks). Required jobs: `Source / Python 3.11`, `Source / Python 3.12`, `Package`, and Static policy.

## Iteration 1 — 2026-10-13 15:00 — agent report: reports/S5-repair-1.md

**Defects in:**
- review.md findings:
  - the Blocker R-1;
  - the Majors R-6, R-7, R-8, R-9, and R-10 (ruled: option a);
  - the Minors R-11 to R-15 (trivial), R-16 (follow-up, conditional on NFR-4), and R-17 (ruled: wording only);
  - R-18, deferred by the orchestrator.
  - R-2 to R-5 were closed by S5 test pass 1.
- Red tests at 8fcc8c63, all four in `tests/features/sdk_provider_keys/`. The pack gave `4 failed, 119 passed`, and the full suite `4 failed, 4103 passed, 13 skipped`.
  - T-6 (R-6): `test_provider_keys_modes.py::GatewayShapeTests::test_an_unserved_provider_or_an_endpoint_is_refused_before_another_providers_key_is_matched`.
  - T-7 (R-17): `test_provider_keys_failures.py::GatewayErrorWordingTests::test_a_vidbyte_managed_402_names_the_wallet_and_offers_a_provider_key_only_as_an_auto_option`.
  - T-9 (R-14): `test_provider_keys_matching.py::SettingsRootTests::test_role_settings_accept_a_padded_vidbyte_key_and_store_what_agent_stores`.
  - T-10 (R-15): `test_provider_keys_security.py::CredentialGuardTests::test_the_relay_header_name_is_a_secret_name_and_the_redactor_scrubs_the_key_under_it`.
- No failing gate other than those four tests.

**Hypotheses and attempts:**

- **R-1 (call depth).**
  - The first edit inlined M-8 into `case DIRECT` and M-21, with its `@intent`, into `case AUTO`, and deleted both helpers. `calldepth.py` then gave two chains, down from six: `validate -> credentials -> normalized_provider` and `resolved_api_key -> credentials -> normalized_provider`.
  - Tried for zero chains:
    1. Call another class's normalizer from `credentials()`. The only one, `Runner._normalize_provider` (`lib/runners/utility.py:175`), strips, lower-cases, and maps blank to None, and its module imports `model_configs`, so it does not fit.
    2. Replace the call with a bare `ModelProvider(self.provider)`. A DIRECT config is never provider-checked at construction (`ProviderKeyMatcher._provider_names` drops unknown names), so `"nosuch"` would raise `ValueError` instead of `ConfigurationError`, a behaviour change.
    3. Inline the try/except. That copies four lines of logic, which the briefing rules out above one line.
  - Kept the single leaf call, the shape §12.4 sanctions and review.md's "Refuted" row 3 accepts.
  - The moved `@intent` block was 75 columns at the deeper indent, so it was rewrapped to 72.
  - `credentials()` is 50 lines, counting the R-10 cast.
- **R-6.**
  - Moved the shape block above `ProviderKeyMatcher.match` and reordered the docstring and comments. T-6 went green on the first try.
  - `probe_c1.py` now gives M-12 for mistral and openrouter with another provider's key, and M-13 for an endpoint with an anthropic key. The unknown provider `nosuch` still raises "Unsupported model provider".
  - No new chain: `__post_init__` calls `_require_gateway_shape` and `normalized_provider`, which are both leaves.
  - §17 records the row-7 order change.
- **R-7.** Replaced the ladder with `match` and a raising `case _`. No behaviour change.
- **R-10 (option a).**
  - Widened the annotations:
    - `TextModelConfig.api_keys` and `JevAgentSettings.api_keys` take `ProviderKeys | Iterable[str | None] | None`, copied from `agents/base.py:98`;
    - `JevRunBriefSettings.api_keys` and `AgentRoleSettings.api_keys` take `Sequence[str | None]`.
  - Narrowing:
    - In `credentials()`, one inline `keys = cast(ProviderKeys, self.api_keys)` sits at the top, after `normalized_provider()`, and covers all four model_configs read sites. There is no helper, so R-1 stays fixed.
    - The writer read site (`jev/brief/writer.py:56`) now reads `settings.vidbyte_api_key`, which `JevAgentSettings.__post_init__` sets to `matched.vidbyte_api_key`. It is the same value and needs no cast.
  - S009 stayed at `350 RATCHETED` on the first try, with an identical finding set (the set diff is empty).
  - The mypy probe gives 0 `arg-type` errors. Its 2 `call-arg` errors come from the probe itself, as the verifier noted.
  - §8.5 and §9.1 were updated, and §17 has a bullet.
- **R-8.**
  - Added four `@intent` blocks, each ≤ 72 columns.
  - A002 is 580, not the 581 the review expected. The set diff against `a002_base.json` adds nothing. It removes `aggregation.__init__`, `_build_proposer_agent`, `fallback.to_fallback`, and `fallback._validate_error_types`.
  - The last one passes only because the new `named_providers` block (fallback.py:100) sits inside its −4/+20 window: incidental proximity, like `resolved_endpoint`'s.
  - `resolved_endpoint` and `normalized_provider` still pass after the R-1, R-6, and R-7 edits. I re-checked them after R-11 too, because R-11 shifted fork.py lines.
- **R-9.**
  - Took the verifier's `s014fix` prototype: an `_aliases` leaf called once from `analyze`. Named the table string once as `KEY_ENV_TABLE`.
  - Corrected the header's ARCHITECTURE NOTE, FUNCTION INVENTORY, and KNOWN EDGE CASES, and the inline comment.
  - The matrix was run on a `git archive` copy, because `s014_mut.py` restores with `git checkout -- .`. It was run at e164d700 and again at the final HEAD 6ac82305, with identical results:
    ```
    [head] control-unmutated: exit 0 found 0 verdict CLEAN error None files []
    [head] registry = {}: exit 1 found 14 verdict REGRESSED error None files ['vidbyte/lib/registries/models.py']
    [head] registry line deleted: exit 1 found 14 verdict REGRESSED error None files ['vidbyte/lib/registries/models.py']
    [head] registry = DEFAULT_TEXT_MODELS: exit 1 found 14 verdict REGRESSED error None files ['vidbyte/lib/registries/models.py']
    [head] registry = DEFAULT_ENDPOINTS-like other name: exit 1 found 14 verdict REGRESSED error None files ['vidbyte/lib/registries/models.py']
    [head] jev.py OPENAI row dropped: exit 1 found 1 verdict REGRESSED error None files ['vidbyte/lib/constants/jev.py']
    ```
- **R-17.**
  - The paid 402 now reads: "…top up the wallet, or, with mode=TextModelMode.AUTO (the default), add your own provider key for {provider} to api_keys so the wallet pays only Vidbyte's fee". It keeps `wallet` and `provider key` for AC-15's PAID_FACTS and `test_managed_text_failures.py:130`.
  - The relayed 402 is unchanged.
  - `VidbyteGatewayTransport` gets no mode parameter.
  - Spec table G's paid 402 cell and §17 were updated. T-7 went green on the first try.
- **R-11.** Rewrapped fork.py:45 and the `children-carry-the-matched-keys` block at :62. The 23 older wide lines were left alone, as the field guide says.
- **R-12.** Corrected the provider_keys.py ROLE line (three more `match` callers), the text.py COMMON MODIFICATION PATTERNS (two gateway branches), and the jev.py TESTS line.
- **R-13.** The M-18 clause "or Vidbyte's own {provider} account" now appears only when the provider is in `VIDBYTE_MANAGED_TEXT_PROVIDERS`.
  - Limitation (no control added): DIRECT with a served provider still offers that clause, because the matcher never learns the mode. The clause is an "or" that is true in the gateway modes.
- **R-14.** The role now strips the Vidbyte key, maps blank to None (the same rule as `ProviderKeyMatcher.match:108`), stores it, then runs the format check. T-9 went green.
- **R-15.** Added the `_provider_key` suffix to `CredentialKeyPolicy` and a `provider[_-]?key` alternative to `HarnessRedactor._ERROR_ASSIGNMENT`, behind the existing #993 lookbehind. T-10 went green, and `application/json` survives redaction.
- **R-16.**
  - `VIDBYTE_API_KEY_FORMAT_MESSAGE` sits beside `VIDBYTE_API_KEY_PATTERN` in `lib/constants/jev.py`. agents.py and models.py use it; agents.py's now-unused `VIDBYTE_API_KEY_PREFIX` import was swapped for it.
  - `ProviderKeyMatcher.DUPLICATE_KEY_MESSAGE` is a `.format` template used at both M-7 sites.
  - provider_keys.py: 296 at the start, 298 after R-13, and 300 after R-16, exactly the NFR-4 cap.
- **R-18.** Not implemented. Status: deferred, per the orchestrator.
- **R-2 to R-5.** Status set to the S5 test-pass SHAs, as briefed.

**Changes:**

| Finding | Commit |
|---|---|
| R-1 | 66bfa272 |
| R-6 | bae3534e |
| R-7 | c72387d3 |
| R-10 | f4e4c16c |
| R-8 | ab841c1f |
| R-9 | e164d700 |
| R-17 | 9150b3cf |
| R-11 | 54cb16de |
| R-12 | a07219f8 |
| R-13 | 940ff97c |
| R-14 | fcc98f17 |
| R-15 | 15907973 |
| R-16 | 6ac82305 |

The docs commit for this log and review.md follows. Spec edits (§8.5, §9.1, table G, §17) ride with R-6, R-10, and R-17.

**Gate matrix out** (code at 6ac82305):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `pytest tests/features/sdk_provider_keys` | PASS (T-6, T-7, T-9, T-10 green) | `123 passed in 5.93s` · the four targets alone: `4 passed in 0.71s` |
| lint | `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| source stage | `python scripts/run_ci.py --stage source` | PASS | `====================== 4107 passed, 13 skipped in 36.73s ======================` / `CI passed.` |
| package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep test | `semgrep --test --config … .semgrep/typed-mapping-boundary-policy.py` | PASS | `1/1: ✓ All tests passed` |
| semgrep scan | `semgrep scan --error --config … vidbyte` | PASS | `Ran 1 rule on 894 files: 0 findings.` |
| R-1 call depth | `calldepth.py … TextModelConfig,TextCredentials` | 2 sanctioned chains (base 0) | `CHAIN validate -> credentials -> normalized_provider` / `CHAIN resolved_api_key -> credentials -> normalized_provider` |
| R-8 A002 set | `lint/run.py --rule A002 --all --format json` vs `a002_base.json` | PASS (0 added) | `found 584 -> 580`, 4 removed, 0 added |
| R-9 S014 matrix | `s014_mut.py <archive of 6ac82305> head` | PASS | 14 / 14 / 14 / 14 at models.py; 1 at jev.py; control CLEAN |
| R-10 mypy | `mypy --config-file lint/mypy.ini … typing_probe.py` | PASS | 0 `arg-type` (2 probe-own `call-arg`) |
| R-10 S009 | `lint/run.py --rule S009` | PASS | `S009   staged-mypy-contracts  350  350 RATCHETED` |
| remote checks | `gh workflow run CI` → 38451268879, `gh workflow run "Static policy"` → 38451272040, both on `6ac82305f1b7…` | PASS 4/4 | `Source / Python 3.12: success` / `Source / Python 3.11: success` / `Package: success` / `Static policy: success` |

The flaky `test_mcp_stdio_transport` test passed in the source stage, so it needed no re-run. No gate failure is inherited from the merge base.

**Still open:**
- R-18: deferred by the orchestrator, as a user follow-up.
- R-1: the two leaf chains through `normalized_provider()` remain by design (see above). Count it as open only if the orchestrator rejects the §12.4 reading.

## Iteration 2 — 2026-10-13 — agent report: reports/S5-repair-2.md

**Defects in:**
- From re-review round 1 (`reports/S5-rereview-conformance-1.md`):
  - R-C1 (Major): `provider_keys.py` had 300 lines, but NFR-4 requires "under 300".
  - R-C2 (Minor): spec table M's M-18 row and §17 did not record R-13.
  - R-C3 (Minor): `CredentialKeyPolicy` did not know the bare name `provider_key`.
- From the live E2E: LE-1 (Major). A relayed provider 400 never pointed at the caller's own key.
- Red tests at d9ef911c, from S5 test pass 2: the pack gave `2 failed, 124 passed in 1.75s`.
  - T-12 (LE-1): `test_provider_keys_failures.py::GatewayErrorWordingTests::test_a_relayed_provider_400_points_at_the_callers_own_key_in_api_keys_and_a_paid_400_does_not`.
  - T-13 (R-C3): `test_provider_keys_security.py::CredentialGuardTests::test_the_bare_name_provider_key_is_a_secret_name_as_the_free_text_redactor_already_treats_it`.
  - T-11 (green; it pins R-13) had to stay green.
- No failing gate other than those two tests.

**Hypotheses and attempts:**

- **R-C1.** Deleted the blank line at `provider_keys.py:66`, as the re-review suggested. That gives 299 lines, which is < 300, so NFR-4 now holds as written. Iteration 1's "≤ 300" was the wrong reading. The M-18 condition at `:295` is intact, and T-11 gave `1 passed`. NFR-4 was not amended.
- **R-C3.**
  - Added `"provider_key"` to `_SECRET_KEYS`. As the test author found, `providerKey` and `Provider-Key` normalize to it, and `_YamlSecretKeyPolicy` unions the set.
  - `git grep` finds no mapping key or config field named `provider_key` under `vidbyte/`, examples, skills, or scripts, so nothing that exists today is newly rejected or scrubbed.
  - T-13 went green on the first try.
- **LE-1.**
  - Added the clause after `relayed = …`, only when `relays and status == HTTPStatus.BAD_REQUEST`. A Vidbyte-paid 400 gains nothing, because it answered Vidbyte's own account. T-12 went green on the first try.
  - Wording: "; some providers answer a wrong API key with HTTP 400, so check your own {provider} key in api_keys or {ENV}". `{ENV}` comes from `PROVIDER_API_KEY_ENV_VARS`, because AUTO relays the provider's variable when no list is passed, and the transport never learns the source. Naming only `api_keys` would mislead that developer.
  - "Withheld" and "not billed" are kept, and no body text is copied.
  - The `@intent relayed-refusal-blames-the-callers-own-key` block covers the 400 case. It grew from 4 to 7 lines, each ≤ 72 columns, and did not move.
  - The `constants/jev.py` header names the new reader of the table.
  - A002 set diff: `580 -> 580`, nothing added or removed.
- **R-C2 and the LE-1 spec rows (docs only).**
  - The M-18 row now shows `{own}` only for a gateway-served primary, plus the DIRECT limitation.
  - Table G has a "relayed provider 400" row.
  - §17 has an R-13 bullet in the iteration 1 list, and the R-6 bullet names INV-24.
  - A new iteration 2 list records LE-1 and row 14's `provider_key` names (R-15, R-C3).
- Nothing failed along the way, and no second attempt was needed.

**Changes:**

| Finding | Commit |
|---|---|
| R-C1 | a1cea1bd |
| R-C3 | ac5099fb |
| LE-1 (code) | 76657bba |
| R-C2 + LE-1 (spec) | 17121734 |

The docs commit for this log, review.md, and the report follows.

**Gate matrix out** (code at 17121734):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `pytest tests/features/sdk_provider_keys` (+ `sdk_managed_text`) | PASS (T-11, T-12, T-13 green) | `165 passed in 1.87s` · T-12 alone `1 passed in 0.70s` · T-13 alone `1 passed in 0.77s` · T-11 alone `1 passed in 0.67s` |
| lint | `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| source stage | `python scripts/run_ci.py --stage source` | PASS | `====================== 4110 passed, 13 skipped in 35.94s ======================` / `CI passed.` |
| package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep test | `semgrep --test --config … .semgrep/typed-mapping-boundary-policy.py` | PASS | `1/1: ✓ All tests passed` |
| semgrep scan | `semgrep scan --error --config … vidbyte` | PASS | `Ran 1 rule on 894 files: 0 findings.` |
| NFR-4 size | `wc -l vidbyte/lib/registries/provider_keys.py` | PASS (299 < 300) | `299 vidbyte/lib/registries/provider_keys.py` |
| A002 set | `lint/run.py --rule A002 --all --format json` vs d9ef911c | PASS (0 added) | `base found 580 now found 580` / `ADDED: []` / `REMOVED: []` |
| S009 / A006 / C017 | source-stage lint summary | PASS | `S009 350 350 RATCHETED` · `A006 34 34 RATCHETED` · `C017 0 0 CLEAN` |
| remote checks | `gh workflow run CI` → 38471474040, `gh workflow run "Static policy"` → 38471477788, both on `17121734fe59…` | PASS 4/4 | `Source / Python 3.12: success` / `Source / Python 3.11: success` / `Package: success` / `Static policy: success` |

The flaky `test_mcp_stdio_transport` test passed in the source stage, so it needed no re-run. `git diff d9ef911c..HEAD -- tests lint/baseline.json` is empty, and the diff adds no `type: ignore`, `noqa`, or `nosemgrep`.

**Still open:**
- R-18: deferred by the orchestrator, as a user follow-up (unchanged).
- None of R-C1, R-C2, R-C3, or LE-1 is open.
