# S4 findings verifier — byok-api-keys (SDK half)

- Diff: `origin/main...8bd1963d` (merge base 595a7260; code final at 3481ed66). Worktree untouched except `review.md` and this report. No commits.
- Scratch: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/5bfc4a32-d2a9-4a4d-a6e5-3f472a0fe403/scratchpad/s4-sdk/verify/`, called `<verify>` below. It holds:
  - `head/` and `base/`: `git archive` copies of 8bd1963d and 595a7260, each `git init`-ed so lint discovery works;
  - `mut_<name>/`: one mutant tree per mutation;
  - `s014fix/` and `r4a/`: fix prototypes;
  - `probe/`: the probe scripts.
- Every run uses `env -u DEEPSEEK_API_KEY PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<tree>`, with Windows-form paths. The probes print `vidbyte from: <tree>` to prove which code was imported. A Git Bash pitfall: `PYTHONPATH="$W\\$t"` silently resolved to the editable main checkout, so use `"$W/$t"`.
- The verdict is **MERGEABLE AFTER FIXES**, with 1 Blocker, 9 Majors, 8 Minors, 0 refuted, 0 downgraded, and 3 sub-claims corrected.

## 1. Merge map

The three reviews share no root cause, so no two findings were merged. R-C1 and R-C2 both touch the M-18 path, but they have different causes: ordering versus wording. R-C1's fix narrows R-C2's exposure to DIRECT and to the Agent root.

| Original | Lens | Proposed | Merged | Verified severity | Owner |
|---|---|---|---|---|---|
| R-V1 | conventions | Blocker | R-1 | Blocker (confirmed) | code |
| R-E2 | engineering | Major | R-2 | Major (confirmed) | test |
| R-E4 | engineering | Major | R-3 | Major (confirmed) | test |
| R-E3 | engineering | Major | R-4 | Major (confirmed) | test |
| R-E1 | engineering | Major | R-5 | Major (confirmed; one sub-case dropped) | test |
| R-C1 | conformance | Major | R-6 | Major (confirmed) | code (+ test T-6) |
| R-V5 | conventions | Major | R-7 | Major (confirmed) | code |
| R-V3 | conventions | Major | R-8 | Major (confirmed) | code |
| R-V2 | conventions | Major | R-9 | Major (confirmed) | code |
| R-V4 | conventions | Major | R-10 | Major (confirmed; needs ruling) | code |
| R-V8 | conventions | Minor | R-11 | Minor, trivial | code |
| R-V7 | conventions | Minor | R-12 | Minor, trivial | code |
| R-C2 | conformance | Minor | R-13 | Minor, trivial | code |
| R-E7 | engineering | Minor | R-14 | Minor, trivial | code |
| R-E5 | engineering | Minor | R-15 | Minor, trivial | code |
| R-V6 | conventions | Minor | R-16 | Minor, follow-up | code |
| R-E6 | engineering | Minor | R-17 | Minor, follow-up (OPEN ITEM 2) | code |
| R-E8 | engineering | Minor `[scope-adding]` | R-18 | Minor, follow-up for the user | — |

Ordering: Blocker first. Within the Majors, the smallest fix comes first: four test-only additions, then a 3-line move (R-6), the match rewrite, the comment blocks, the lint helper, and finally the ruling-gated annotation change.

## 2. Verification of every Blocker and Major

### R-1 (R-V1): call depth in `TextModelConfig` — CONFIRMED, Blocker kept

AGENTS.md §1, verbatim: "Inside a class, or a module of plain functions, a function may call another of its own functions, but that second function should not call a third. The shape to aim for is one main function that calls a flat list of helpers, where each helper does its job and returns without calling further helpers of its own. When a helper starts to need another helper, lift that call up into the main function…"

Evidence: `python <verify>/calldepth.py <tree>/vidbyte/lib/dataclasses/model_configs.py TextModelConfig,TextCredentials`.

- **Base 595a7260:** no CHAIN lines. `validate -> …, normalized_provider, is_vidbyte_managed, _require_managed_shape, resolved_vidbyte_api_key` are all leaves.
- **HEAD:**
  - Edges:
    ```
    validate -> _require_model, …, credentials
    credentials -> normalized_provider, _refuse_missing_provider_key, _require_relayable_length
    resolved_api_key -> credentials
    ```
  - Chains:
    ```
    CHAIN validate -> credentials -> normalized_provider
    CHAIN validate -> credentials -> _refuse_missing_provider_key
    CHAIN validate -> credentials -> _require_relayable_length
    CHAIN resolved_api_key -> credentials -> {the same three}
    ```
- **Diff-wide:** `python <verify>/chaindiff.py <base> <head> <every changed vidbyte/ and lint/ .py>` finds exactly these six new chains and no others.

Adjudication of the orchestrator's question:

- `credentials()` is the feature's main function (row 7), but `validate()` and `resolved_api_key()` are own functions that call it. On those paths, `credentials()` is "the second function", and it calls a third. AGENTS.md has no exemption for public entry points.
- The spec saw this coming. §12.4 says "`credentials()` calls registry methods plus at most one own helper (`_require_gateway_shape`), and that helper calls no own helper". The implementation calls three own helpers, and neither §17 nor the S3 report records the deviation (grep of both for `_require_relayable_length|_refuse_missing_provider_key|call depth`: no hit outside spec row 7 and §12.4).
- Rubric: "contradicts AGENTS.md" means Blocker. The fix is mechanical and changes no behavior.

After the reviewer's fix, `validate -> credentials -> normalized_provider` remains. That is the single leaf helper §12.4 sanctions, not a residual defect. `credentials()` will be about 47 lines, at the top of house style's ~40–50.

### R-2 (R-E2): Vidbyte key filed as a provider key in a hand-built record — CONFIRMED, Major

- **Mutation:** `kk_record_allows_vidbyte_key` replaces `provider_keys.py:204` with `sendable = re.fullmatch(VIDBYTE_PROVIDER_KEY_PATTERN, key) is not None`.
  - Full suite, first run (3 runs in parallel): `4101 passed, 13 skipped in 40.18s`.
  - Sequential re-run: `4101 passed, 13 skipped in 36.85s`.
  - The mutation SURVIVES.
- **Effect** (`probe/probe_gaps.py`):
  - HEAD: `R-E2 record: ConfigurationError: TextModelConfig.api_keys is a ProviderKeys record whose key 0 does not fit deepseek; …`
  - Mutant: `R-E2 record: BUILT; DIRECT provider key -> VB`
- **Existing guards:** M-14 in `find_provider_api_key` covers only environment values. `ProviderKeys.__post_init__` does not refuse a `vb_live_` key in `keys`; the probe builds the record. No other guard exists.
- **Spec:** INV-13 ("A Vidbyte key never reaches a provider and is never sent as a provider key").

### R-3 (R-E4): default aggregator as a primary — CONFIRMED, Major

- **Mutation:** `vv_default_aggregator_not_primary` deletes `aggregation.py:219-220`. Full suite: `4101 passed, 13 skipped in 39.63s`. The mutation SURVIVES.
- **Effect:**
  - HEAD: `ConfigurationError: api_keys holds keys for openai but none for anthropic …`
  - Mutant: `R-E4 aggregate: BUILT (default aggregator not checked)`
- **Spec:** INV-24 ("every spec-built proposer's provider and the spec-built aggregator's provider are primaries") and the `@intent aggregate-models-all-need-their-keys` block ("the default one is this agent's own provider and model"). AC-37's test passes only an explicit aggregator or a prebuilt one (`test_provider_keys_agents.py:272-291`).

### R-4 (R-E3): VIDBYTE_MANAGED never reads the provider variable — CONFIRMED, Major

- **Mutation:** `ad_managed_reads_provider_key` adds `_unused = ProviderModelRegistry.find_provider_api_key(provider, self.api_keys)` to the VIDBYTE_MANAGED case. Full suite: `4101 passed, 13 skipped in 38.72s`. The mutation SURVIVES.
- **Effect** (no `api_keys`; `OPENAI_API_KEY` holds a Vidbyte key):
  - HEAD: `credentials ok: mode=vidbyte_managed provider_key=None`
  - Mutant: `ConfigurationError: OPENAI_API_KEY holds a Vidbyte API key; set it as VIDBYTE_API_KEY …`
- **Why the existing test cannot fail:** `test_provider_keys_acceptance.py:257-270` passes `api_keys=[K_OPENAI]`. `find_provider_api_key` returns the record's key first, so `environment.reads` never contains `OPENAI_API_KEY`.
- **Spec:** INV-5 ("never reads the provider keys or the provider's environment variable").

### R-5 (R-E1): non-text runners take their own provider's key — CONFIRMED, Major (one sub-case dropped)

- **Mutations** (both full-suite runs SURVIVE):
  - `o_runner_first_key` (`utility.py:130` → `next(iter(self.api_keys.keys), None)`): `4101 passed, 13 skipped in 40.18s`, and sequentially `in 36.47s`.
  - `an_detector_first_key` (`modality_detector.py:226` → the first key of the matched record): `4101 passed, 13 skipped in 40.18s`.
- **Effect** (`api_keys=[K_XAI, K_OPENAI]`, provider openai, `gpt-image-1`):
  - HEAD: `Runner image options api_key -> K_OPENAI`; `detector image api_key -> K_OPENAI`.
  - `o` mutant: Runner gives `K_XAI`.
  - `an` mutant: detector gives `K_XAI`.
- **Sub-claim refuted:** the reviewer's extra case ("the list holds only another provider's key … assert `api_key is None`") cannot be built:
  - `Agent(provider="openai", api_keys=[K_XAI])` raises M-18 (INV-24);
  - `ModalityDetector._config_options` calls `match(api_keys, primary=provider)` with `require_primary_key` defaulting to True.

  T-5 omits that case. The other-key-first case kills both mutations.

### R-6 (R-C1): INV-8 ordering in `TextModelConfig.__post_init__` — CONFIRMED, Major

Probe (`probe/probe_c1.py`, cleared environment) at HEAD:

```
AUTO mistral + xai key: ConfigurationError: TextModelConfig.api_keys holds keys for xai but none for mistral, … or pass no provider keys to use MISTRAL_API_KEY or Vidbyte's own mistral account.
AUTO mistral, no keys: UnsupportedProviderError: The Vidbyte gateway serves only: anthropic, deepseek, gemini, kimi, openai, xai. Use mode=TextModelMode.DIRECT …
MANAGED openrouter + xai key: ConfigurationError: … none for openrouter …
AUTO xai + anthropic key + endpoint: ConfigurationError: … holds keys for anthropic but none for xai …
AUTO xai, no keys + endpoint: ConfigurationError: A custom endpoint is not allowed … Use mode=TextModelMode.DIRECT …
```

- **Spec reading:**
  - INV-8 says the config "is refused when it is built, before any key or environment is read". `ProviderKeyMatcher.match` reads (classifies) every key.
  - Row 7 lists match and then shape, but it states no order between them. The only "then" in row 7 refers to the `prompt_index`/mode checks.
  - INV-8 is the specific ordering statement. D-15 adds: "Wrong advice … is a bug". The M-18 remedy ("Add your mistral key" or "Vidbyte's own mistral account") leads straight into M-12.
- **No existing guard:** none.
- **Fix proof:** mutant `c1_shape_before_match` (the shape block moved above the match):
  - Full suite: `4101 passed, 13 skipped in 39.42s`, so no S2 test pins the old order, and the M-18 tests (AC-33 uses openai, which is served) are unaffected.
  - The probe now gives `UnsupportedProviderError: The Vidbyte gateway serves only…` for mistral and openrouter with a key, and `A custom endpoint is not allowed…` for the endpoint with an anthropic key.
  - The Agent root is unchanged: `BaseAgent` matches with INV-24 before any `TextModelConfig` exists, as the orchestrator asked to check.
- **Edge:** an unknown provider string (`"nosuch"`) raises `Unsupported model provider: 'nosuch'` both before and after the fix.

### R-7 (R-V5): mode ladder in `TextCredentials.__post_init__` — CONFIRMED, Major

- `model_configs.py:256-261` is `if self.mode is DIRECT … elif VIDBYTE_MANAGED … else: <AUTO rule>`.
- The `isinstance` guard at `:252` only makes the `else` reachable by a mode that is a `TextModelMode` but none of the three named members. A fourth member would silently get AUTO's rule.
- §12.4: "Mode dispatch uses `match` with an explicit `case _:` that raises" (house style). `credentials()` in the same file follows it at `:128-152`.
- No behavior changes today. The finding is kept at Major because the §12.4 bullet is explicit and the same file shows the right pattern, so a reviewer would flag it.

### R-8 (R-V3): A002 count worsened — CONFIRMED, Major

- `lint/run.py --rule A002 --all --format json` on the archive copies:
  - head `found 585 baseline 703 verdict IMPROVED`;
  - base `found 584 baseline 703 verdict IMPROVED`.
- Set difference:
  ```
  added:   [('vidbyte/agents/aggregation.py', '_build_aggregator'), ('vidbyte/agents/settings/fallback.py', '_inherited_provider'), ('vidbyte/agents/settings/fallback.py', 'named_providers'), ('vidbyte/lib/dataclasses/model_configs.py', 'relays')]
  removed: [('vidbyte/agents/aggregation.py', '__init__'), ('vidbyte/agents/aggregation.py', '_build_proposer_agent'), ('vidbyte/agents/settings/fallback.py', 'to_fallback')]
  ```
- All four are flagged with category `external boundaries`, because the token `provider` appears in their bodies (A002 `POLICY_TOKENS`).
- Kept at Major, not downgraded to Minor. §12.4 makes it a checklist item ("Every business rule has an `@intent` within 20 lines of its `def`"), the PR moved a blocking-severity rule's count the wrong way, and `relays` is the predicate that decides whether a secret goes on the wire.

### R-9 (R-V2): S014 strictness — CONFIRMED, Major

`python <verify>/s014_mut.py <tree> head|base` edits `vidbyte/lib/registries/models.py`. On base it replaces the whole literal, and on HEAD the alias line `:91`. Then it runs `python lint/run.py --rule S014 --format json`:

```
[head] control-unmutated: exit 0 found 0 verdict CLEAN
[head] registry = {}: exit 0 found 0 verdict CLEAN
[head] registry line deleted: exit 0 found 0 verdict CLEAN
[head] registry = DEFAULT_TEXT_MODELS: exit 0 found 0 verdict CLEAN
[head] registry = DEFAULT_ENDPOINTS-like other name: exit 0 found 0 verdict CLEAN
[head] jev.py OPENAI row dropped: exit 1 found 1 verdict REGRESSED files ['vidbyte/lib/constants/jev.py']
[base] control-unmutated: exit 0 found 0 verdict CLEAN
[base] registry = {}: exit 1 found 14 verdict REGRESSED files ['vidbyte/lib/registries/models.py']
[base] registry literal deleted: exit 1 found 14 verdict REGRESSED files ['vidbyte/lib/registries/models.py']
[base] registry = DEFAULT_TEXT_MODELS: exit 1 found 14 verdict REGRESSED files ['vidbyte/lib/registries/models.py']
[base] registry OPENAI row dropped: exit 1 found 1 verdict REGRESSED files ['vidbyte/lib/registries/models.py']
```

Measured against the ruling (pipeline.md, 0d0b484b):

- The ruling says to read `jev.py` "when the registry attribute is not a literal", and it requires that "Parity stays equally strict".
- `= {}` is a literal, yet HEAD reads it as an alias. That breaks the ruling's own text.
- Deletion and a wrong alias are "not a literal" in the narrow sense, but they break "equally strict": base reports 14 for each, HEAD reports 0.
- The cause is `:46 aliased = set(maps["API_KEY_ENV_VARS"]) == {"__line__"}`. `_class_dict` returns `{"__line__": n}` for `{}`, for a missing attribute, and for any non-`Dict` value alike.

Calibration (Major, not Blocker):

- `python <verify>/mut.py s014_registry_emptied` (the full suite, with the registry table set to `{}`) fails 11+ tests, starting with `tests/features/sdk_managed_text/test_managed_text_acceptance.py::…test_each_managed_provider_posts_its_byok_body_once…`.
- So an emptied table cannot ship. What is lost is the static guarantee the lint rule gave.

Fix proof: the prototype in `<verify>/s014fix` sets `aliased` only when the class body has `API_KEY_ENV_VARS: … = PROVIDER_API_KEY_ENV_VARS` as an `ast.Name`. On the same matrix it gives:

```
control CLEAN; = {} found 14 (models.py); deleted found 14; = DEFAULT_TEXT_MODELS found 14; = OTHER_TABLE found 14; jev.py row dropped found 1 (jev.py)
```

That is the reviewer's expected shape, as the orchestrator anticipated.

### R-10 (R-V4): public annotations reject the documented list — CONFIRMED, Major (needs ruling)

- **mypy:** `python -m mypy --config-file lint/mypy.ini --no-incremental --follow-imports=silent <verify>/probe/typing_probe.py`, run with mypy 2.3.1 against the HEAD copy:
  ```
  typing_probe.py:11:60: error: Argument "api_keys" to "TextModelConfig" has incompatible type "list[str]"; expected "ProviderKeys"  [arg-type]
  typing_probe.py:12:27: error: Argument "api_keys" to "JevAgentSettings" has incompatible type "list[str]"; expected "ProviderKeys"  [arg-type]
  typing_probe.py:13:30: error: Argument "api_keys" to "JevRunBriefSettings" has incompatible type "list[str]"; expected "tuple[str, ...]"  [arg-type]
  typing_probe.py:14:57: error: Argument "api_keys" to "AgentRoleSettings" has incompatible type "list[str]"; expected "tuple[str, ...]"  [arg-type]
  ```
  - `Agent(... api_keys=keys)` raised no arg-type error. The probe's only other errors are missing-`name` call-args, which come from the probe itself.
- **Option (a) prototype** (`<verify>/r4a`) widens the two `ProviderKeys` fields to `ProviderKeys | Iterable[str | None]` and the two tuple fields to `Iterable`/`Sequence[str | None]`. It moves S009 from `head found 350 baseline 350 RATCHETED` to `r4a found 355 REGRESSED`. All five new errors sit at read sites of the two `ProviderKeys` fields:
  - `model_configs.py`: `find_provider_api_key(provider, self.api_keys)` ×2, `self.api_keys.providers`, and `self.api_keys.key_for`;
  - `jev/brief/writer.py:56`: `settings.api_keys.vidbyte_api_key`.

  Widening the two tuple fields adds 0 errors.
- **Sub-claim corrected:** "mypy flags every README example" is overstated. The README's list examples use `Agent`/`Session.resume`, which type-check cleanly. What fails is the call form used by the spec's ACs and the repo's `scripts/test-*.py` (`TextModelConfig(..., api_keys=[FAKE_…])`).
- **Spec:** §8.5, §9.1, and row 7 prescribe these annotations. §9.2 says the field "accepts a list", and NG-19 says the docs show only the list form. That is an internal tension in the spec, so this is OPEN ITEM 1, not a repair the agent can take alone.

## 3. Minors (de-duplicated; spot-checked)

Each Minor was spot-checked with its own evidence:

- **R-11 (R-V8):** `awk 'length($0) > 72 && /^[[:space:]]*#/'` on `vidbyte/agents/fork.py` gives `:45 119` and `:62 73`. The diff shows `:45` was edited in this PR ("so the key and backup checks" → "so the backup check"). The file has 23 other wide comment lines that predate the PR and are untouched; leave them.
- **R-12 (R-V7):**
  - Grep shows `ProviderKeyMatcher.match` callers at `utility.py:44`, `modality_detector.py:226`, and `writer.py:56`, none named in the `provider_keys.py:4` ROLE line.
  - `text.py:57` branches on `uses_gateway`, but `:91` branches on `vidbyte_api_key is not None`.
  - The `jev.py:9` TESTS line omits the provider-keys pack.
- **R-13 (R-C2):** the probe in DIRECT says "…or pass no provider keys to use MISTRAL_API_KEY or Vidbyte's own mistral account."
- **R-14 (R-E7):**
  - `role padded: ConfigurationError The managed Vidbyte API key must be a live key in the vb_live_ format.`
  - `agent padded: accepted`
- **R-15 (R-E5):**
  - `is_secret_key('X-Vidbyte-Provider-Key') = False`
  - `mapping dump leaks provider key: True | leaks vidbyte key: False`
  - `free-text dump leaks provider key: True`
  - A grep of `vidbyte/trace`, `vidbyte/harnesses`, and `lib/http` finds no path that dumps request headers, so the reviewer's Minor tier holds.
- **R-16 (R-V6):** `git grep "must be a live key" 8bd1963d -- vidbyte` finds `agents.py:281` and `models.py:209`. `git grep "pass one key per provider"` finds `provider_keys.py:239` and `:275`.
- **R-17 (R-E6):** `vidbyte_gateway.py:111`. The paid 402 reason is chosen whenever `relays` is False, and `gateway_reason(status, retried, provider, relays)` never receives the mode. `ManagedCall` (`test_managed_text_failures.py:65`) builds an AUTO config, and no test pins a VIDBYTE_MANAGED 402.
- **R-18 (R-E8):** `vb_test_ bound to: ['deepseek'] | is vidbyte key: False`.

## 4. Proposed tests: verified

`<verify>/proposed/test_s4_verify_proposed.py` holds T-2 to T-6 as written in review.md. The verifier ran it per tree with `python -m pytest -q -p no:cacheprovider --rootdir=<tree> <file>` and `PYTHONPATH=<tree>`:

```
head:                              1 failed, 4 passed   (FAILED test_c1_shape_refusal_comes_before_key_matching)
mut_c1_shape_before_match (fix):   5 passed
mut_o_runner_first_key:            2 failed (c1, e1)
mut_an_detector_first_key:         2 failed (c1, e1)
mut_kk_record_allows_vidbyte_key:  2 failed (c1, e2: "ConfigurationError not raised")
mut_ad_managed_reads_provider_key: 2 failed (c1, e3: M-14 raised)
mut_vv_default_aggregator_not_primary: 2 failed (c1, e4: "ConfigurationError not raised")
```

At HEAD, each E-test passes, and each one fails only under its own mutation. The C1 test is red at HEAD and green with the fix.

## 5. Severity blind-spot check

No new Blocker-class defect was found between the lenses. The checks:

- the diff-wide own-method chain scan (only R-1's chains are new);
- request-header dump paths (none);
- the R-6 fix against INV-24 and the M-18 tests (full suite green);
- the S014 fix against the jev.py-side proof (still 1 finding).

Fix interactions the repair agent must respect (no `[verifier]` finding is added):

1. **R-1, R-6, R-7, and R-10 all edit `model_configs.py`.** If OPEN ITEM 1 picks (a), the narrowing inside `credentials()` must be inline (`cast` or an `isinstance` guard with an `@intent`). A new own helper would recreate R-1.
2. **A002 windows.** Neighbouring `@intent` blocks cover `resolved_endpoint` (:165) and `normalized_provider` (:102) only because they are close by. `_refuse_missing_provider_key` (:192) is covered the same way, but R-1 deletes it. After the R-1, R-6, and R-7 edits, re-diff the A002 finding set against base; do not compare only the count (R-8 expects 581).
3. **NFR-4 caps `provider_keys.py` at 300 lines; it is now 296.** R-13, R-16 (the M-7 constant), and R-18 all edit it. Put one-line messages on one line, as the file already does.
4. **R-6 contradicts the sentence order of spec row 7.** Record the change in §17 as INV-8 taking precedence.
5. **R-9 requires the S3 report's S014 proof to include the registry-side edits.** `<verify>/s014_mut.py` reproduces the full matrix.

## 6. Disagreements adjudicated

- **R-V1 Blocker versus "credentials() is the main function".** The Blocker is kept; see §2 R-1.
- **R-V3 Major versus Minor.** Major is kept; see §2 R-8.
- **R-V2 Blocker-worthiness.** It is Major, not Blocker, because the test suite catches an emptied table at runtime.
- **R-V4 "every README example".** Corrected: only the low-level config and settings constructors fail. The finding stands.
- **R-E1 extra sub-case.** Refuted: M-18 fires at any root that holds only another provider's key.
- **Conformance versus conventions on R-C1/row 7.** Conventions raised nothing here. INV-8 governs.

## 7. Open items (detail)

### OPEN ITEM 1 — R-10 annotation of `api_keys` (a §9.2 public signature)

**(a) Widen all four fields.**
- Change:
  - `TextModelConfig.api_keys` and `JevAgentSettings.api_keys` become `ProviderKeys | Iterable[str | None]`, the same union `BaseAgent`, `Runner`, `create_runner`, and `Session.resume` already use.
  - `JevRunBriefSettings.api_keys` and `AgentRoleSettings.api_keys` become `Sequence[str | None]`.
  - Narrow the five read sites (`model_configs.py` ×4 and `jev/brief/writer.py:56`) inline, with `cast(ProviderKeys, …)` next to an `@intent` stating that `__post_init__` always stores the matched record. Never use `# type: ignore`.
  - Update the §8.5, §9.1, and row 7 annotation text.
- Consequence:
  - Every documented call type-checks, and there is no runtime change.
  - S009 must stay at 350. The verifier's prototype without narrowing gives 355.
  - About 4 annotation lines and 5 narrowings change.

**(b) Keep the spec annotations and record the mismatch in §17.**
- Consequence: zero churn. A mypy or Pylance user gets `[arg-type]` errors on `TextModelConfig`, `JevAgentSettings`, `JevRunBriefSettings`, and `AgentRoleSettings` when passing a list (only `Agent`/`Session` are clean). This contradicts NG-19's "developers see only the list".

**(c) Split.**
- Change: widen only the two tuple fields to `Sequence[str | None]`; this adds 0 new mypy errors, as the prototype proved. Keep `ProviderKeys` on `TextModelConfig` and `JevAgentSettings`, with a §17 note.
- Consequence: two developer-facing settings records are fixed for free. The two `ProviderKeys` fields stay dishonest.

**Recommendation: (a).**
- The user asked that developers not have to worry about keys.
- `JevAgentSettings` is a developer-built record.
- The union is already the SDK's own pattern on every agent entry point.
- The cost is about 9 lines with no behavior change.

Flip to (c) if the orchestrator wants no spec-annotation change on `TextModelConfig` before the live E2E.

### OPEN ITEM 2 — R-17 VIDBYTE_MANAGED 402 wording (table G has no column for it)

Proposed reason text, in table G's style, keeping the paid column's facts (`wallet`, `provider key`):

> "your own Vidbyte wallet balance is too low for this call (HTTP 402, which never means a provider's billing); top up the wallet, or use mode=TextModelMode.AUTO and add your own provider key for {provider} to api_keys so the wallet pays only Vidbyte's fee"

Plumbing: `VidbyteGatewayTransport.__init__` (§8.5) gains a keyword-only `mode: TextModelMode`, or a `can_relay: bool`. `TextModelRunner.arun` passes `self._credentials.mode`, and `gateway_reason` picks the managed text when `mode is VIDBYTE_MANAGED`.

Options:
1. Adopt the wording now, in S5. This changes a §8.5 signature and adds one table-G column.
2. Shorter: in VIDBYTE_MANAGED, say only "top up the wallet". This needs the same plumbing and drops the cheaper path.
3. Leave it as a follow-up and record it in §17.

**Recommendation: 3, defer as a follow-up.** The defect is advice-only, in an opt-in mode, outside the spec, and needs a signature change. If the orchestrator wants it in this PR, use option 1's text.

### Note for the user (no ruling needed now)

R-18, `vb_test_` not reserved, is `[scope-adding]`; keep it as a user follow-up.

## 8. Commands run (final lines)

- **Archive copies:** `git archive 8bd1963d | tar -x -C <verify>/head`, `git archive 595a7260 | tar -x -C <verify>/base`, then `git init && git add -A && git commit` in each scratch copy. Output: `ok`.
- **Full suite on the unmutated head copy:** `python -m pytest -q -p no:cacheprovider` gives `4101 passed, 13 skipped in 37.59s`.
- **Mutations:** `python <verify>/mut.py <name>`. Each copies `head` to `mut_<name>`, applies one string edit, and runs the full suite:
  - `o_runner_first_key`: `4101 passed, 13 skipped in 40.18s`; sequential re-run `4101 passed, 13 skipped in 36.47s`.
  - `an_detector_first_key`: `4101 passed, 13 skipped in 40.18s`.
  - `kk_record_allows_vidbyte_key`: `4101 passed, 13 skipped in 40.18s`; sequential re-run `4101 passed, 13 skipped in 36.85s`.
  - `ad_managed_reads_provider_key`: `4101 passed, 13 skipped in 38.72s`.
  - `vv_default_aggregator_not_primary`: `4101 passed, 13 skipped in 39.63s`.
  - `c1_shape_before_match` (the R-6 fix): `4101 passed, 13 skipped in 39.42s`.
  - `s014_registry_emptied`: `exit 1`, with 11+ `FAILED tests/features/sdk_managed_text/...` lines.
- **Probes:** `python <verify>/probe/probe_gaps.py`, `probe_c1.py`, and `probe_minors.py`, per tree; outputs are quoted above.
- **S014 matrix:** `python <verify>/s014_mut.py <tree> head|base`; output quoted in §2 R-9.
- **A002:** `python lint/run.py --rule A002 --all --format json`; head 585, base 584; set diff quoted in §2 R-8.
- **S009:** `python lint/run.py --rule S009 --all --format json` gives head `found 350 baseline 350 RATCHETED` and r4a `found 355 REGRESSED`.
- **mypy:** `python -m mypy --config-file lint/mypy.ini --no-incremental --follow-imports=silent <verify>/probe/typing_probe.py`; four `[arg-type]` errors quoted in §2 R-10.
- **Call depth:** `python <verify>/calldepth.py` and `python <verify>/chaindiff.py`; output quoted in §2 R-1.
- **Proposed tests:** `python -m pytest -q -p no:cacheprovider --rootdir=<tree> <verify>/proposed/test_s4_verify_proposed.py`, per tree; results in §4.
- **Not run:** `run_ci.py` and semgrep. No source changed, and the orchestrator's gate results stand.
