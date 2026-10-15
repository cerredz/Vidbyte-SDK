LENS: conformance (post-repair re-review 1)
VERDICT: MERGEABLE AFTER FIXES — all 13 fixes hold, and none introduced a behaviour regression, but `provider_keys.py` now has exactly 300 lines, which fails NFR-4's P0 criterion "The new module is under 300 lines" (a one-line fix).

Reviewed: HEAD `ac0322b9` (code final at `6ac82305`), `git diff 3481ed66..ac0322b9 -- vidbyte lint scripts README.md` hunk by hunk with each whole file open, plus `origin/main...ac0322b9` where a fix touches older code. Every probe ran offline with concatenated fake keys. Mutations ran only on private `git archive` copies under `scratchpad/s5-sdk/rereview/`. The worktree is unchanged (`git status --short` is empty).

## FIX CONFIRMATION

- **R-1 CONFIRMED.**
  - `calldepth.py vidbyte/lib/dataclasses/model_configs.py TextModelConfig,TextCredentials` gives only `CHAIN validate -> credentials -> normalized_provider` and `CHAIN resolved_api_key -> credentials -> normalized_provider`, which is the sanctioned leaf shape.
  - `chaindiff.py <3481ed66 archive> <HEAD archive> <changed .py>` prints nothing, so the repair added no chain. Against the merge base 595a7260, only those two chains are new.
  - `grep _refuse_missing_provider_key|_require_relayable_length` outside docs/spec finds nothing.
  - The M-8 and M-21 texts and `details` are byte-identical to the deleted helpers.
- **R-6 CONFIRMED.**
  - `probe_c1.py`:
    - `AUTO mistral + xai key: UnsupportedProviderError: The Vidbyte gateway serves only: anthropic, deepseek, gemini, kimi, openai, xai. Use mode=TextModelMode.DIRECT to call mistral with your own key.`
    - `AUTO xai + anthropic key + endpoint: ConfigurationError: A custom endpoint is not allowed … Use mode=TextModelMode.DIRECT …`
  - T-6 fails at 8fcc8c63 (archive run) and passes at HEAD.
- **R-7 CONFIRMED.**
  - `model_configs.py:251-259` is a `match` with a raising `case _`.
  - Probe results:
    - the four legal combinations: `BUILT`;
    - DIRECT+V, MANAGED+P, and AUTO with no V: `ConfigurationError`;
    - `TextCredentials("auto", …)`: `TextCredentials.mode must be a TextModelMode value.`
- **R-8 CONFIRMED.**
  - `lint/run.py --rule A002 --all --format json`, set-diffed against `a002_base.json`: `base found 584 now found 580`, `ADDED: []`.
  - `REMOVED`: aggregation `__init__` and `_build_proposer_agent`; fallback `_validate_error_types` and `to_fallback`.
  - The four new `@intent` blocks describe the code they sit in.
- **R-9 CONFIRMED.**
  - `s014_mut.py <archive of ac0322b9> head`:
    - control: `found 0 CLEAN`;
    - `= {}`, line deleted, `= DEFAULT_TEXT_MODELS`, and `= OTHER_TABLE` each give `found 14 REGRESSED` at `models.py`;
    - jev.py OPENAI row dropped: `found 1 REGRESSED` at `jev.py`.
  - My extra mutations:
    - an unannotated alias gives `found 14` at `models.py`;
    - a jev.py table that is `{}`, deleted, a non-literal, or unannotated gives `found 14` at `jev.py`.
  - The rule fails closed everywhere.
- **R-10 CONFIRMED.**
  - Typing:
    - `mypy --config-file lint/mypy.ini --follow-imports=silent typing_probe.py` gives 0 `arg-type` errors. The 2 `call-arg` errors come from the probe itself.
    - mypy over `vidbyte/agents/jev`, `model_configs.py`, `paradigms/context_minimal_fanout`, `runners/text.py`, and `runners/utility.py` reports 0 errors that mention `api_keys`, `ProviderKeys`, or `vidbyte_api_key`.
    - S009: `350 RATCHETED`, with a finding set identical to the S4 head (line-insensitive).
  - Runtime: list, tuple, generator, `None`, record, `replace(api_keys=[…])`, `deepcopy`, and `pickle` all store a `ProviderKeys`.
  - No `__new__`, `__setstate__`, subclass, or external `object.__setattr__(…, "api_keys", …)` exists in `vidbyte/`. Every other read goes through `AgentRunnerConfig.api_keys`, which stays `ProviderKeys` and is isinstance-checked (`agents.py:312`).
  - So the `cast` hides no un-matched path.
- **R-11 CONFIRMED.** An awk scan of every comment line added since 3481ed66 finds none over 72 columns under `vidbyte/`. The only hit is a single-line comment in the lint rule (`s014…py:105`, 80 columns), and the rule covers multi-line blocks.
- **R-12 CONFIRMED.**
  - A grep of `ProviderKeyMatcher.match` callers (`base.py:181,566`, `aggregation.py:221`, `jev/settings.py:158`, `writer.py:56`, `model_configs.py:100`, `utility.py:44`, `modality_detector.py:226`) matches the ROLE line.
  - `text.py:88-91` branches on `vidbyte_api_key is not None`, as the header now says.
- **R-13 CONFIRMED.**
  - Probe results:
    - `DIRECT mistral + xai key: … pass no provider keys to use MISTRAL_API_KEY.`
    - `Agent mistral + xai key: … to use MISTRAL_API_KEY.`
    - `Agent openai + xai key: … OPENAI_API_KEY or Vidbyte's own openai account.`
  - No test pins this fix (see R-C2).
- **R-14 CONFIRMED.**
  - Probe: `role == stripped: True | agent == stripped: True`; a blank key becomes `None`; a non-str key raises the same M-11 as `Agent`.
  - T-9 fails at 8fcc8c63 and passes at HEAD.
- **R-15 CONFIRMED** for the header name.
  - Name and redactor:
    - `is_secret_key('X-Vidbyte-Provider-Key') = True`.
    - The mapping dump and the free-text dump both scrub the key.
  - Regex and prose:
    - The #993 lookbehind is kept (`serialization.py:75`).
    - Prose is unchanged: "provider key for openai", "the provider key: is optional", and `content-type: application/json`.
  - T-10 fails at 8fcc8c63 and passes at HEAD.
  - The bare name `provider_key` gap is R-C3.
- **R-16 CONFIRMED.**
  - `VIDBYTE_API_KEY_FORMAT_MESSAGE == base f-string text: True`. The M-7 text is unchanged (probe: `TextModelConfig.api_keys[0] and TextModelConfig.api_keys[1] are both openai keys; pass one key per provider.`).
  - INV-18's identical-message tests pass in the full suite.
  - The side effect, a 300-line file, is R-C1.
- **R-17 CONFIRMED.**
  - `_GatewayAnswer.gateway_reason(402, …, relays=False)`: `…top up the wallet, or, with mode=TextModelMode.AUTO (the default), add your own provider key for openai to api_keys so the wallet pays only Vidbyte's fee`. That is true in AUTO without a key and in VIDBYTE_MANAGED.
  - `relays=True`: `…top up the wallet`, with no provider key.
  - It matches spec table G (`spec.md:923`).
  - `VidbyteGatewayTransport(` is built only at `text.py:92`, so no Jev or decision path gets this wording.
  - T-7 fails at 8fcc8c63 and passes at HEAD.
- **R-2 to R-5 CONFIRMED (tests).** On the HEAD archive, each mutation fails exactly its own test and leaves the other 122 passing:
  - R-2: `kk_record_allows_vidbyte_key` fails `test_a_hand_built_record_whose_key_does_not_fit_its_provider_is_refused_at_construction`.
  - R-3: `vv_default_aggregator_not_primary` fails `test_an_aggregate_needs_every_spec_built_models_key_unless_its_list_holds_none`.
  - R-5: `o_runner_first_key` and `an_detector_first_key` each fail `test_a_non_text_runner_takes_its_own_providers_key_when_another_providers_key_comes_first`.
  - R-4: `ad_managed_reads_provider_key`, re-shaped onto R-1's new `credentials()`, fails `test_vidbyte_managed_with_no_list_never_reads_the_provider_variable_even_when_it_holds_a_vidbyte_key`.

## WHAT THE REPAIRS GET RIGHT

- **R-6 is the smallest correct reorder.**
  - INV-8 now holds: the shape check runs before any key is matched.
  - `__post_init__` calls only leaf helpers.
  - Only error precedence changed. An unknown provider in AUTO still raises `Unsupported model provider: 'nosuch'`, as before.
- **The R-10 narrowing hides nothing.**
  - Every construction path ends in `ProviderKeys`.
  - The brief writer's switch to `settings.vidbyte_api_key` reads the same object that `__post_init__` stores (`settings.py:159`).
- **The S014 fix is now strict in both files.** It fails closed on all nine registry-side and jev-side mutations, five of which the repair's matrix never tried.
- **The repair kept its discipline.**
  - Across all 90 lint rules, only A002's finding set changed between 3481ed66 and HEAD (585 to 580, nothing added).
  - No `tests/` change since 8fcc8c63, no baseline change, and no `type: ignore`, `noqa`, or `nosemgrep` added.
  - `ruff --select F` is clean on every changed file.
  - Remote CI run 38451268879 and Static policy run 38451272040 both succeeded at `6ac82305`.

## NEW FINDINGS

R-C1 [Major] [conformance] `vidbyte/lib/registries/provider_keys.py:300` (whole file; blank line at `:66`) — the new module has exactly 300 lines, but NFR-4 requires it to be "under 300 lines"
  Evidence:
  - `spec.md:519`: `| NFR-4 | … | P0 | … The new module is under 300 lines. …`
  - `wc -l vidbyte/lib/registries/provider_keys.py` gives `300`.
  - `git show <c>:vidbyte/lib/registries/provider_keys.py | wc -l` gives 296 at 8fcc8c63, 298 at 940ff97c (R-13), and 300 at 6ac82305 (R-16).
  - The record states the requirement as "≤ 300" in several places: `reports/S5-repair-1.md:29` ("That is the NFR-4 cap (≤ 300)"), `verify-log.md:92` ("exactly the NFR-4 cap"), `review.md:136` ("296 lines (≤ 300)"), and `pipeline.md:119,135`. The spec says "under", and nothing in the spec defines it as "at most".
  Failure: a reviewer who checks NFR-4's measurable criterion against the merged tree finds 300, which is not under 300. A P0 requirement fails its own proof, and the repair record reports it as met.
  Smallest fix: delete the blank line at `provider_keys.py:66`, between `RESERVED_PREFIXES` and `DUPLICATE_KEY_MESSAGE`. The file drops to 299 lines, with no behaviour change and no test needed. Then correct "≤ 300" to "< 300" in the repair report and verify log. Alternatively, the orchestrator could amend NFR-4 to "at most 300 lines" and record that in §17. Its own routing note (`pipeline.md:119`, "R-16 only if provider_keys.py stays ≤ 300 lines") already reads it that way.
  Spec IDs: NFR-4, §8.4.

R-C2 [Minor] [conformance] `docs/spec/byok-api-keys/spec.md:913`, `:1490-1494`; code at `vidbyte/lib/registries/provider_keys.py:296` — §17's repair-deviation list omits R-13's change to M-18, and no test pins that change
  Evidence:
  - Table M M-18 (`spec.md:913`) still reads "…or pass no provider keys to use {ENV} or Vidbyte's own {primary} account." with no condition.
  - The code adds that clause only for `VIDBYTE_MANAGED_TEXT_PROVIDERS`. Probe: `DIRECT mistral + xai key: … to use MISTRAL_API_KEY.`
  - The §17 "Repair deviations (S5, iteration 1)" list has bullets for R-6, R-10, and R-17 only.
  - Replacing the condition with `if True` (restoring the old wording) on the HEAD archive gives `4107 passed, 13 skipped in 38.81s`, so nothing pins the fix.
  - Related and smaller: the R-6 bullet says INV-8 overrides "row 7's sentence order". The new order also means a gateway-mode `TextModelConfig` root with an unserved primary and another provider's key raises `UnsupportedProviderError`, not the M-18 that INV-24 (`spec.md:353`) promises "in every mode". That is correct behaviour, but it is not recorded.
  Failure: the next agent or a human checks M-18 against table M and sees a mismatch with no record. A later change that reverts the clause would pass every gate.
  Smallest fix: amend table M M-18 to say "…to use {ENV}, plus "or Vidbyte's own {primary} account" when {primary} is a gateway-served provider". Add an R-13 bullet to §17, and name INV-24 in the R-6 bullet. Optionally, add one assertion to the existing M-18 test: for an unserved primary, `"Vidbyte's own" not in message`.
  Spec IDs: INV-24, INV-8, table M (M-18), §17.

R-C3 [Minor] [conventions] `vidbyte/lib/util/credential_keys.py:55-78` vs `vidbyte/harnesses/serialization.py:75` — the R-15 fix taught the redactor the bare name `provider_key` but taught the name policy only the suffix, so the two guards disagree
  Evidence:
  - Probe results:
    - `is_secret_key('provider_key') = False`; `providerKey` and `Provider-Key` are also `False`.
    - `HarnessRedactor().redact({'provider_key': K})` returns K unchanged ("leaks=True").
    - `HarnessRedactor().redact('provider_key=K')` returns `provider_key=<redacted>`.
  - The file's own COMMON MODIFICATION PATTERNS (`credential_keys.py:24-27`) pairs each exact name with its suffix ("api_keys and _api_keys sit beside api_key and _api_key"). `_SECRET_KEYS` gained no `provider_key`.
  - `grep` finds no current `vidbyte/` path that builds a mapping with that bare key, so this is defence in depth, like R-15 itself.
  Failure: a future capture of a mapping such as `{"provider_key": <key>}` (a plausible name beside `provider_api_key`) keeps the key in harness output, while the same name in free text is scrubbed.
  Smallest fix: add `"provider_key"` to `CredentialKeyPolicy._SECRET_KEYS`.
  Spec IDs: INV-22, NFR-1 (review R-15).

## VERIFIED CLAIMS

1. "provider_keys.py: 296 at the start, 298 after R-13, and 300 after R-16" (verify-log): **held** (296 / 298 / 300). "exactly the NFR-4 cap (≤ 300)": **did not hold**; NFR-4 says "under 300" (R-C1).
2. "A002 is 580 … the set diff against a002_base.json adds nothing" (repair §2.3): **held** (`ADDED: []`, 4 removed).
3. "S009 stayed at 350 RATCHETED … identical finding set": **held**, as a line-insensitive set compared with the verifier's `s009_head.json`.
4. "R-9 matrix … 14 / 14 / 14 / 14 at models.py; 1 at jev.py; control CLEAN": **held** on my own archive. It also held for five further mutations.
5. "Red tests at 8fcc8c63 … T-6, T-7, T-9, T-10": **held** (`4 failed in 0.96s` at 8fcc8c63, `4 passed in 0.75s` at HEAD).
6. "R-10 mypy: 0 arg-type (2 probe-own call-arg)": **held**.
7. "R-1: two leaf chains through normalized_provider() … base 0": **held**. The repair added no chain against 3481ed66.
8. "Remote CI (run 38451268879) and Static policy (run 38451272040) passed on 6ac82305": **held** (`gh run view`: three jobs `success`, `Static policy` `success`, sha `6ac82305`).
9. "No test was edited. No baseline was raised, no suppression added": **held**. The diffs for `tests/` since 8fcc8c63 and for `lint/baseline.json` since 3481ed66 are empty, and no suppressions were added.
10. "credentials() is 50 lines, counting the R-10 cast": **close**. The AST gives 49 (`123-171`), which is within house style.
11. "R-15 … `application/json` survives redaction": **held**.
12. "Full suite 4107 passed, 13 skipped": **held** (`4107 passed, 13 skipped in 42.81s`; source gate `4107 passed, 13 skipped in 37.06s` / `CI passed.`).

## COMMANDS RUN

All commands ran from the worktree root with `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" PYTHONIOENCODING=utf-8`, except where a run happened inside an archive copy. `vidbyte.__file__` resolves to the worktree.

- **Tests and gates**
  - `python -m pytest -q -p no:cacheprovider`: `4107 passed, 13 skipped in 42.81s`
  - `python scripts/run_ci.py --stage source`: `4107 passed, 13 skipped in 37.06s` / `CI passed.`
  - `python -m pytest tests/features/sdk_provider_keys -q -p no:cacheprovider`: `123 passed in 1.62s`
  - T-6, T-7, T-9, T-10 in the 8fcc8c63 archive: `4 failed in 0.96s`; at HEAD: `4 passed in 0.75s`
- **Lint**
  - `python lint/run.py`: `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`
  - `--rule S009`: `S009 RATCHETED: 350 known finding(s).` / `SDK-LINT: PASS`
  - `--rule S014`, `--rule C017`, `--rule A006`: each `SDK-LINT: PASS`
  - `--rule A002 --all --format json`, set diff: `base found 584 now found 580` / `ADDED: []`
  - `--all --format json` in the 3481ed66 and HEAD archives, compared per rule: `A002 585 -> 580 added: []` / `compared 90 rules`
  - `python -m ruff check --select F <14 changed files>`: `All checks passed!`
  - awk scan for added comment lines over 72 columns: one hit, `s014…py:105: 80` (a single-line comment)
- **Mutation and call-depth tools**
  - `s014_mut.py <archive> head`: control `found 0 CLEAN`; four registry-side edits each `found 14 REGRESSED` at `models.py`; jev row dropped `found 1 REGRESSED` at `jev.py`
  - `s014_extra.py` (mine): unannotated alias `found 14` at `models.py`; jev `{}`, deleted, non-literal, and unannotated each `found 14` at `jev.py`
  - `calldepth.py … TextModelConfig,TextCredentials`: two `CHAIN … -> credentials -> normalized_provider`
  - `chaindiff.py`: none new against 3481ed66; two sanctioned chains against the merge base
  - Mutations on the HEAD archive (pack runs): kk, vv, o, an, and re-shaped ad each give `1 failed, 122 passed` (own test)
  - R-13 revert (full suite): `4107 passed, 13 skipped in 38.81s`
- **Typing probes**
  - `mypy … typing_probe.py`: only two `[call-arg]` errors, both from the probe
  - `mypy` over the jev, model_configs, paradigm, and runner read sites, filtered for key names: no output
- **Runtime probes**
  - `probe_c1.py`, `probe_minors.py`: outputs quoted above
  - `probe_r15.py`, `probe_fixes.py` (mine, in `scratchpad/s5-sdk/rereview/`): outputs quoted above
- **Other checks**
  - `gh run view 38451268879` / `38451272040` (read-only): `success` at `6ac82305`
  - `git diff --stat 8fcc8c63..ac0322b9 -- tests`: empty
  - `git diff --stat 3481ed66..ac0322b9 -- lint/baseline.json`: empty
  - `git status --short` at the end: empty
