LENS: conformance (post-repair re-review 2)
VERDICT: SOUND — all four fixes hold against their evidence and against attempts to break them, nothing regressed (full suite, source gate, and all 90 lint rules match the pre-repair state), and the only new findings are two Minor items: a test gap and a defence-in-depth gap.

Reviewed: HEAD `0db58657`; code final at `76657bba` (`git diff b1c76a2b..0db58657 -- vidbyte tests lint scripts README.md` is empty). I read `git diff 36897094..0db58657 -- vidbyte lint scripts README.md` hunk by hunk, with each whole file open: `vidbyte_gateway.py`, `credential_keys.py`, `provider_keys.py`, and the `constants/jev.py` header. I also read the spec, review.md, and test edits in that range.

Every probe ran offline with fake keys built by concatenation, and patched only the inner transport. Mutations ran on private `git archive` copies under `scratchpad/s5-sdk/rereview2/`. `git status --short` was empty before I wrote this report.

## FIX CONFIRMATION

- **R-C1 CONFIRMED.**
  - `wc -l vidbyte/lib/registries/provider_keys.py` gives `299`. A byte count agrees: `newlines 299 ends_with_newline True splitlines 299 crlf False`.
  - `git show <c>:…provider_keys.py | wc -l` gives `36897094 300`, `a1cea1bd 299`, and `0db58657 299`.
  - NFR-4's other criteria hold. `lint/run.py --rule A006` gives `A006 … 34 34 RATCHETED`, and `base.py` is untouched in this range.
  - The hunk only deletes a blank line. The R-13 condition is intact at `:295`.
- **R-C2 CONFIRMED.**
  - Table M M-18 (`spec.md:913`) now shows `{own}` only for a served primary, and it states the DIRECT limitation. §17 has an R-13 bullet, and its R-6 bullet names INV-24 (`spec.md:1493-1494`).
  - `probe_rc2.py` matches the row in every case:
    - `TextModelConfig DIRECT mistral + xai key: … to use MISTRAL_API_KEY.`
    - `TextModelConfig AUTO mistral + xai key: UnsupportedProviderError: The Vidbyte gateway serves only: … Use mode=TextModelMode.DIRECT to call mistral with your own key.` This is the R-6/INV-24 note.
    - `Agent AUTO openai + xai key: … to use OPENAI_API_KEY or Vidbyte's own openai account.`
    - `Agent DIRECT kimi + xai key: … MOONSHOT_API_KEY or Vidbyte's own kimi account.` This is the accepted limitation.
  - T-11 kills the revert. `mut.py r13_revert` gives `FAILED …test_m18_offers_vidbytes_own_account_only_for_a_provider_the_gateway_serves` / `1 failed, 302 passed`. In round 1, the same revert passed the full suite.
- **R-C3 CONFIRMED** for every spelling it names.
  - `probe_rc3.py` gives `True` for `provider_key`, `providerKey`, `Provider-Key`, `PROVIDER_KEY`, `ProviderKey`, and `X-Vidbyte-Provider-Key` in `CredentialKeyPolicy`, `HarnessSecretPolicy`, and `_YamlSecretKeyPolicy`.
  - Redaction holds: `mapping provider_key: False` and `text provider_key=: False` (False means no leak).
  - There are no false positives. `provider`, `providers`, `provider_kind`, `key_providers`, `provider_key_header`, `provider_key_source`, `VIDBYTE_PROVIDER_KEY_HEADER`, `VIDBYTE_PROVIDER_KEY_MAX_LENGTH`, `keys`, and `matched_primary` are all `False`.
  - Blast radius: a grep for the bare spellings over `vidbyte tests scripts examples skills lint` READMEs, YAML, TOML, and JSON (excluding `docs/`) finds only local variables and parameters. Those are `model_configs.py:138,157`, `modality_detector.py:226`, `utility.py:130`, and the test parameters in `test_billed_unusable_replies.py:53`, `test_prompt_sits_at_run_boundary.py:106`, `test_streaming_text_runner.py:241`, and `test_sync_runner_default_transport.py:99`. No mapping key, dataclass field, `details` key, or YAML config uses the name, so nothing is newly scrubbed or refused.
  - `mut.py rc3_revert` gives `FAILED …test_the_bare_name_provider_key_is_a_secret_name…` / `1 failed, 302 passed`.
  - Residual spellings are in R-D2.
- **LE-1 CONFIRMED.**
  - `probe_le1.py` reports `PROBLEMS: 0` over three parts:
    1. `failure_reason` on all 14 `ModelProvider` members, with the relay flag both true and false, raised no `KeyError`, and the clause appeared exactly when the call relayed.
    2. A runner matrix of 6 gateway providers × 3 body shapes × 5 cases. The shapes were a nested provider error, the xAI `{"code":"invalid-argument","error":"<string>"}`, and the gateway `"error": true`. The cases were AUTO with a key in the list, AUTO with the env var, AUTO paid, VIDBYTE_MANAGED with a list, and VIDBYTE_MANAGED with the env var.
    3. Relayed 401, 402, 403, 404, 409, 413, 422, 429, and 502: none gained the clause.
  - In every case of part 2:
    - The clause appears only on a relayed provider 400, and it reads `check your own {p} key in api_keys or {ENV}` with the right variable (`MOONSHOT_API_KEY` for kimi).
    - VIDBYTE_MANAGED never sends the header.
    - A gateway `error: true` 400 stays `Vidbyte returned HTTP 400` in both modes.
    - "withheld" and "not billed" survive, and there is exactly 1 attempt.
    - `status_code == 400`, `provider == "vidbyte"`, and there is no `__cause__` or `__context__`.
    - No sentinel appears in the message, details, or traceback: the canary, the leaked key, the Vidbyte key, the 6 provider keys, `Incorrect API key`, `invalid-argument`, `invalid_request_error`, or `model_gateway_refused`.
  - DIRECT never uses the gateway: `DIRECT xai: url=https://api.x.ai/v1/chat/completions; clause=False; gateway wording=False`, and the same holds for openai.
  - Sample output:
    - Relay: `Vidbyte gateway xai request failed: xai returned HTTP 400 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed; some providers answer a wrong API key with HTTP 400, so check your own xai key in api_keys or XAI_API_KEY.`
    - Paid: `… and the call was not billed.`
  - The `KeyError` cannot ship silently. Dropping `ModelProvider.KIMI` from `PROVIDER_API_KEY_ENV_VARS` (in a `tree_kimi` copy) gives `S014 … 1 0 REGRESSED` / `SDK-LINT: FAIL` and `13 failed, 152 passed`.
  - T-12 kills both the revert and the paid-too variant:
    - `mut.py le1_revert`: `AssertionError: 'api_keys' not found …` / `1 failed, 302 passed`.
    - `mut.py le1_paid_too`: `'api_keys' unexpectedly found …` / `1 failed, 302 passed`.
- **Round 1 confirmations still hold.**
  - Full suite: `4110 passed, 13 skipped in 52.85s`. `run_ci.py --stage source`: `4110 passed, 13 skipped in 36.16s` / `CI passed.`
  - `lint/run.py`: `SDK-LINT: PASS`.
  - All 90 lint rules compared between the 36897094 archive and HEAD, by count and by path+symbol set, give `rules differing: 0`.
  - The iteration 2 code touches only the four files above, so no round 1 code path changed.

## WHAT THE REPAIRS GET RIGHT

- **LE-1 is gated exactly where the facts differ.** It runs only after the `"error": true` dispatch and the relayed 401/402/403 branch, and only when `relays and status == 400`. Gateway errors, paid calls, VIDBYTE_MANAGED, and DIRECT are byte-identical to before (probe: 0 problems in 118 cases), and the new code copies no body text.
- **The `{ENV}` lookup is total and guarded.** The table covers all 14 enum members, the transport receives only `normalized_provider()` (`text.py:94`), and a missing gateway row fails S014 (blocking) and 13 pack tests.
- **Each fix is pinned by a test that kills its revert, and nothing else moved.** The diffs for `tests/` and `lint/baseline.json` since d9ef911c are empty. The diff adds 0 `type: ignore`, `noqa`, or `nosemgrep`, and no added comment line is over 72 columns. Remote CI and Static policy succeeded at `17121734` (38471474040 / 38471477788) and at `b1c76a2b` (38471973768 / 38471976852).
- **The spec edits are true to the code.** The M-18 row and its facts column, the table G "relayed provider 400" row, and the §17 R-6, R-13, LE-1, and row-14 bullets each match a probe output above, except one overstatement noted in R-D2.

## NEW FINDINGS

R-D1 [Minor] [tests] `tests/features/sdk_provider_keys/test_provider_keys_failures.py:183-191` (and T-12 at `:140`) — the relayed-400 clause's status scope and its `{ENV}` name are unpinned, and the "unchanged wording" test still lists 400 as table G's last row
  Evidence:
  - `:184` says `# Table G last row: a relayed 400 or 429 is still the provider's answer, withheld, with no gateway remedy.` and `:185` iterates over `(400, 429)`. Since LE-1, a relayed 400 has its own row (`spec.md:929`), and its wording changed. The file header PURPOSE (`:3`) still lists only "a relayed provider 401/402/403".
  - `mut.py le1_all_relayed_statuses` changes the guard to `if relays:`, which adds the clause to every relayed provider status. The full suite gives `4110 passed, 13 skipped in 40.70s`.
  - `mut.py le1_wrong_env` changes `{ENV}` to always be `OPENAI_API_KEY`. The full suite gives `4110 passed, 13 skipped in 63.68s`.
  - test-plan.md:138 already notes that the old test "does not forbid `api_keys`".
  Failure:
  - A later edit that widens the guard gives a relayed xAI 429 (the provider's own rate limit) the text "…; some providers answer a wrong API key with HTTP 400, so check your own xai key in api_keys or XAI_API_KEY". That is a wrong remedy, it contradicts table G's "other relayed provider status | unchanged", and every gate stays green.
  - A wrong variable name is not caught either. For example, the message could name `KIMI_API_KEY`, while the SDK reads `MOONSHOT_API_KEY`.
  Smallest fix:
  - In the old test, iterate over `(429,)` only, because T-12 now owns 400. Add `self.assertNotIn("api_keys", message)`, which follows from the row's "unchanged" status, and fix the `:184` comment and the `:3` PURPOSE.
  - Optionally, add `XAI_API_KEY` to T-12's assertions and `{ENV}` to table G's relay facts column (`spec.md:929`). The orchestrator accepted that wording, but the facts column does not bind it.
  Spec IDs: table G ("relayed provider 400", "other relayed provider status"), LE-1, D-15.

R-D2 [Minor] [conventions] `vidbyte/lib/util/credential_keys.py:55-80` vs `vidbyte/harnesses/serialization.py:75` and `spec.md:1501` — the R-C3 fix leaves the run-on spelling `providerkey` disagreeing between the two guards, and leaves out the plural that the file's own rule asks for
  Evidence:
  - Probe output, where `policy` is the `CredentialKeyPolicy` verdict and `leaks` means the key survived:
    - `providerkey policy=False mapping_leaks=True text_leaks=False`
    - `PROVIDERKEY policy=False mapping_leaks=True text_leaks=False`
    - `provider_keys policy=False mapping_leaks=True text_leaks=True`
    - `providerKeys policy=False mapping_leaks=True text_leaks=True`
  - The redactor's alternative `provider[_-]?key` matches the run-on form, and `_SECRET_KEYS` holds `"apikey"` for exactly that reason beside `api_key`.
  - The header (`:26-28`) says "A name that holds a list of credentials needs its plural too".
  - §17 row 14 (`spec.md:1501`) claims the policy "agrees with the harness redactor's `provider[_-]?key` alternative", but that does not hold for the run-on form.
  - No `vidbyte/` path uses these names today, so this is defence in depth, as R-C3 was.
  Failure: a captured mapping `{"providerkey": <key>}` keeps the key in harness output, while `providerkey=<key>` in free text is scrubbed. That is R-C3's disagreement in a third spelling. `{"provider_keys": [<key>]}` escapes both guards.
  Smallest fix: add `"providerkey"` and `"provider_keys"` to `_SECRET_KEYS`, and `"_provider_keys"` to `_SECRET_SUFFIXES`. Optionally, change the redactor alternative to `provider[_-]?keys?`. Alternatively, narrow the §17 row-14 claim to the separated spellings.
  Spec IDs: INV-22, NFR-1, §17 row 14.

## VERIFIED CLAIMS

1. "`wc -l` now gives 299": **held** (`299`, with a trailing newline).
2. "T-12 and T-13 were the only reds at d9ef911c; each went green": **held** in effect. The pack at HEAD gives `126 passed in 2.38s`, and reverting each fix fails only its own test (`1 failed, 302 passed`).
3. "A002 580 → 580, ADDED [] REMOVED []": **held, and more broadly**. `A002 … 580 703 IMPROVED`, and all 90 rules have identical finding sets against 36897094 (`rules differing: 0`).
4. "S009 350, A006 34, C017 0 CLEAN, S014 0 CLEAN": **held** (`S009 … 350 350 RATCHETED`, `A006 … 34 34 RATCHETED`, `C017 … 0 0 CLEAN`, `S014 … 0 0 CLEAN`).
5. "Source stage 4110 passed, 13 skipped / CI passed.": **held** (`4110 passed, 13 skipped in 36.16s` / `CI passed.`).
6. "The probe output for True 400 / True 401 / True 429 / False 400": **held**. My runner probe reproduces the relay-400 and paid-400 texts byte for byte.
7. "`providerKey` and `Provider-Key` normalize to `provider_key`; `_YamlSecretKeyPolicy` unions the set": **held**. Both are `True` in all three policies, and `config.py:65` is `_SECRET_KEYS = CredentialKeyPolicy._SECRET_KEYS | _CONFIG_SECRET_KEYS`.
8. "No mapping key or config field is named `provider_key`": **held** (only locals and parameters; see R-C3 above).
9. "All six gateway-served providers are keys of that table": **held**, and all 14 members are keys.
10. "No test pins the exact relayed-400 text; no README documents it": **held**. `git grep "through the Vidbyte gateway|call was not billed|wrong API key"` finds no test or README that pins it.
11. "The diff touches 5 files (+20/−6); the `tests/` and baseline diffs are empty; no suppressions; no comment over 72 columns": **held** (`5 files changed, 20 insertions(+), 6 deletions(-)`; both diffs empty; `0` suppressions; the awk scan prints nothing).
12. "Remote CI and Static policy succeeded on 17121734": **held**. They also succeeded on b1c76a2b.
13. "`ruff check` on the touched files: All checks passed!": **held**, on the 4 source files and the 3 test files.

## COMMANDS RUN

All commands ran from the worktree root with `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" PYTHONIOENCODING=utf-8`. Mutants ran from inside their own copy. `vidbyte.__file__` resolves to the worktree, or to the mutant tree for a mutant run.

- **Tests and gates**
  - `python -m pytest -q -p no:cacheprovider`: `4110 passed, 13 skipped in 52.85s`
  - `python scripts/run_ci.py --stage source`: `4110 passed, 13 skipped in 36.16s` / `CI passed.`
  - `python -m pytest tests/features/sdk_provider_keys -q -p no:cacheprovider`: `126 passed in 2.38s`
- **Lint**
  - `python lint/run.py`: `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS`
  - `--rule S009/A006/C017/S014/A002`: `350 350 RATCHETED` / `34 34 RATCHETED` / `0 0 CLEAN` / `0 0 CLEAN` / `580 703 IMPROVED`
  - `--all --format json` in the 36897094 archive (with its own `git init`) and at HEAD, compared per rule: `rules 90 90` / `rules differing: 0`
  - `python -m ruff check --config lint/ruff.toml <7 changed files>`: `All checks passed!`
- **Probes** (in `scratchpad/s5-sdk/rereview2/`)
  - `probe_le1.py`: `PROBLEMS: 0` (outputs quoted above)
  - `probe_rc3.py`: outputs quoted above; run-on and plural spellings in R-D2
  - `probe_rc2.py`: outputs quoted above
- **Mutations** (`mut.py <mutant>`, on the packs plus `test_harness_redaction.py` and `test_durable_sessions.py`)
  - `control`: `303 passed`
  - `le1_revert`, `le1_paid_too`, `rc3_revert`, `r13_revert`: each `1 failed, 302 passed`, failing its own test
  - `le1_wrong_env`, `le1_no_env`, `le1_all_relayed_statuses`: `303 passed`. Two of them were re-run on the full suite:
    - `le1_wrong_env`: `4110 passed, 13 skipped in 63.68s`
    - `le1_all_relayed_statuses`: `4110 passed, 13 skipped in 40.70s`
  - The `tree_kimi` env-row drop: `S014 … 1 0 REGRESSED` / `SDK-LINT: FAIL`; packs `13 failed, 152 passed`
- **Read-only git and gh**
  - `gh run list --branch feat/byok-api-keys`:
    - `38471976852 Static policy b1c76a2b completed success`
    - `38471973768 CI b1c76a2b completed success`
    - `38471477788 / 38471474040 … 17121734 … success`
  - `git diff --stat d9ef911c..0db58657 -- tests lint/baseline.json`: empty
  - `git diff b1c76a2b..0db58657 -- vidbyte tests lint scripts README.md`: empty
  - The grep sweeps quoted above
  - `git status --short` before writing this report: empty
