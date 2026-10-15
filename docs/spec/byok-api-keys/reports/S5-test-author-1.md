# S5 test author, pass 1: byok-api-keys (SDK half)

Status: DONE. Branch `feat/byok-api-keys`, started at HEAD `c5076f91`. Inputs: `review.md` § "Test cases for the test author (R-2 to R-6)", plus the orchestrator's specs for T-7 (R-17), T-9 (R-14), and T-10 (R-15). There is no T-8 (R-9; see §6). No file outside `tests/`, `test-plan.md`, and this report changed.

`<verify>` below means the S4 verifier's scratch directory, `…/scratchpad/s4-sdk/verify`. `<s5>` means my scratch directory, `…/scratchpad/s5-mut`. Both sit in the session scratchpad `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/5bfc4a32-d2a9-4a4d-a6e5-3f472a0fe403/scratchpad`.

## 1. What I added

All paths are under `tests/features/sdk_provider_keys/`.

| ID | Finding | File → class → test | Kind | At HEAD | Commit |
|---|---|---|---|---|---|
| T-2 | R-2 | `test_provider_keys_matching.py` → `RecordPassThroughTests` → `test_a_hand_built_record_whose_key_does_not_fit_its_provider_is_refused_at_construction` | one row added to the existing `records` table (allowed by hard rule 2) and one comment line | green | `f1f6a4f4` |
| T-3 | R-3 | `test_provider_keys_agents.py` → `AgentRootRefusalTests` → `test_an_aggregate_needs_every_spec_built_models_key_unless_its_list_holds_none` | one block added inside the existing cleared-environment block; no existing line changed | green | `e6ae4990` |
| T-4 | R-4 | `test_provider_keys_acceptance.py` → `TextCallAcceptanceTests` → `test_vidbyte_managed_with_no_list_never_reads_the_provider_variable_even_when_it_holds_a_vidbyte_key` | new test | green | `32cf23e5` |
| T-5 | R-5 | `test_provider_keys_agents.py` → `NonTextModelKeyTests` → `test_a_non_text_runner_takes_its_own_providers_key_when_another_providers_key_comes_first` | new test | green | `d971f491` |
| T-6 | R-6 | `test_provider_keys_modes.py` → `GatewayShapeTests` → `test_an_unserved_provider_or_an_endpoint_is_refused_before_another_providers_key_is_matched` | new test | **red** | `8b158ed7` |
| T-7 | R-17 | `test_provider_keys_failures.py` → `GatewayErrorWordingTests` → `test_a_vidbyte_managed_402_names_the_wallet_and_offers_a_provider_key_only_as_an_auto_option` | new test | **red** | `6f282122` |
| T-9 | R-14 | `test_provider_keys_matching.py` → `SettingsRootTests` → `test_role_settings_accept_a_padded_vidbyte_key_and_store_what_agent_stores` | new test | **red** | `e213bcfd` |
| T-10 | R-15 | `test_provider_keys_security.py` → `CredentialGuardTests` → `test_the_relay_header_name_is_a_secret_name_and_the_redactor_scrubs_the_key_under_it` | new test | **red** | `963881dd` |
| — | all of the above | `FEATURE.md` → Known Failure Modes | 8 lines appended (input + state → wrong output) | — | `aeebf97f` |

No existing assertion was weakened, skipped, xfailed, or deleted. Every feature symbol is imported inside its test. Every fake key comes from the fixtures (`K_XAI`, `K_OPENAI`, `K_ANTHROPIC`, `VIDBYTE_KEY`, `OTHER_VIDBYTE_KEY`); the only new string built from one is `" " + VIDBYTE_KEY + " "`. Each environment is cleared with `patch.dict(os.environ, …, clear=True)` or replaced by `RecordingEnviron`. Mocks sit only at the pack's existing seams: `RUNNER_TRANSPORT_TARGET`, the `transport=` argument, and `SLEEP_TARGET`.

## 2. Proof

### 2.1 Method: why the briefing's mutant command was not used as written

From the worktree root, `PYTHONPATH=<verify>/mut_<name> python …` imports `vidbyte` from the **worktree**, not from the mutant tree. Python puts the current directory (`''`) at `sys.path[0]`, ahead of `PYTHONPATH`. Checked:

```
env -u DEEPSEEK_API_KEY PYTHONPATH="<verify>/mut_kk_record_allows_vidbyte_key" python -c "import vidbyte, sys; print(vidbyte.__file__); print(sys.path[:3])"
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-byok-api-keys\vidbyte\__init__.py
['', '…\\verify\\mut_kk_record_allows_vidbyte_key', '…\\python311.zip']
```

A mutant proof run that way would have tested HEAD and "proved" nothing. I used `<s5>/s5_mut.py <name> [targets]` instead. It works in five steps:

1. Copy `<verify>/mut_<name>` (or `<verify>/head` for a control) to `<s5>/tree_<name>`.
2. Copy the worktree's current `tests/features/sdk_provider_keys/*.py` into that copy.
3. Check that the verifier's mutation, imported from `<verify>/mut.py`'s `MUTATIONS` table, is present.
4. Print `vidbyte.__file__` under the exact run environment.
5. Run pytest with the current directory and `PYTHONPATH` both set to the tree, and `DEEPSEEK_API_KEY` unset.

Every run below printed `vidbyte.__file__ = …\s5-mut\tree_<name>\vidbyte\__init__.py`. The verifier's `head` tree equals the worktree's `vidbyte/`, `tests/`, and `lint/` except for line endings (`diff -rq --strip-trailing-cr` is empty). `mut.py` itself was not usable, because it re-copies `head`, which lacks the new tests.

To re-run a proof: `cd <s5> && python s5_mut.py <mutant> tests/features/sdk_provider_keys`.

### 2.2 Per test (final pytest lines)

At HEAD, I ran in the worktree with `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)"`, after checking that `vidbyte.__file__` is the worktree's.

- **T-2:** green@HEAD (`1 passed`). On `kk_record_allows_vidbyte_key`, with the matching file: `E AssertionError: ConfigurationError not raised` · `1 failed, 27 passed in 1.36s`. Control on `head` with the same file: `28 passed in 1.07s`.
- **T-3:** green@HEAD. On `vv_default_aggregator_not_primary`, with the agents file: `AssertionError: ConfigurationError not raised` at `test_provider_keys_agents.py:286` (the new block) · `1 failed, 20 passed in 1.31s`.
- **T-4:** green@HEAD. On `ad_managed_reads_provider_key`, with the acceptance file: `ConfigurationError: OPENAI_API_KEY holds a Vidbyte API key; set it as VIDBYTE_API_KEY …` · `1 failed, 10 passed in 1.27s`.
- **T-5:** green@HEAD (`NonTextModelKeyTests`: `2 passed`). With the agents file:
  - On `o_runner_first_key`: `AssertionError: 'xai-XXX…' != 'sk-proj-PPP…'` at `:452` (the agent's runner) · `1 failed, 21 passed in 1.28s`.
  - On `an_detector_first_key`: the same message at `:453` (`ModalityDetector.create_runner`) · `1 failed, 21 passed in 1.28s`.
- **T-6:** red@HEAD. Under pytest: `ConfigurationError: TextModelConfig.api_keys holds keys for xai but none for mistral, …` (M-18). Under `python -m unittest`, all four subtests are red: `FAILED (failures=2, errors=2)`. The 2 errors are M-18 for the unserved provider in each mode. The 2 failures are `'custom endpoint' not found in "TextModelConfig.api_keys holds keys for anthropic but none for xai…"`. On the fix tree `c1_shape_before_match`, the modes file gives `17 passed in 1.27s`.
- **T-7:** red@HEAD: `AssertionError: 'TextModelMode.AUTO' not found in "Vidbyte gateway openai request failed: your own Vidbyte wallet balance is too low for this call (HTTP 402, …); top up the wallet, or add your own provider key for openai to api_keys so the wallet pays only Vidbyte's fee."` This confirms the briefing's reading of `vidbyte_gateway.py:111`: `api_keys` advice without AUTO.
- **T-9:** red@HEAD: `ConfigurationError: The managed Vidbyte API key must be a live key in the vb_live_ format.` It is raised at `:432`, the role's construction. `Agent` with the same padded key passed the line before. Agent stores the stripped key (probe: `stored == VIDBYTE_KEY` True, `== padded` False).
- **T-10:** red@HEAD: `AssertionError: False is not true : X-Vidbyte-Provider-Key must be a credential name`. A probe of the other halves at HEAD (booleans only) shows:
  - The mapping dump keeps the provider key (True) and drops the bearer (False).
  - Both free-text texts keep the provider key under both `redact` and `safe_error_message`.

  With only the `_provider_key` policy suffix applied to a scratch tree, the test still fails, now at `:256`, the free-text half. So the regex alternation is needed too.

### 2.3 Mutation matrix, whole pack (`python s5_mut.py <tree> tests/features/sdk_provider_keys`)

| Tree | Final line | Failures beyond the 4 red (T-6, T-7, T-9, T-10) |
|---|---|---|
| `head` (control) | `4 failed, 119 passed in 2.36s` | none |
| `kk_record_allows_vidbyte_key` | `5 failed, 118 passed in 2.30s` | T-2 only |
| `vv_default_aggregator_not_primary` | `5 failed, 118 passed in 2.35s` | T-3 only |
| `ad_managed_reads_provider_key` | `5 failed, 118 passed in 2.29s` | T-4 only |
| `o_runner_first_key` | `5 failed, 118 passed in 2.30s` | T-5 only |
| `an_detector_first_key` | `5 failed, 118 passed in 2.29s` | T-5 only |
| `c1_shape_before_match` (R-6 fix) | `3 failed, 120 passed in 2.26s` | T-6 green; T-7, T-9, T-10 remain |

Each mutant fails exactly its own case. No new test fails for an unrelated reason under any tree.

### 2.4 Pack and full suite at HEAD (worktree)

- Pack: `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" python -m pytest tests/features/sdk_provider_keys -q -p no:cacheprovider` gives `4 failed, 119 passed in 1.80s`.
- Full suite: `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" python -m pytest -q -p no:cacheprovider` gives `4 failed, 4103 passed, 13 skipped in 36.29s`.

The previous result was `4101 passed, 13 skipped`. The difference is +6 new test functions, and the only failures are T-6, T-7, T-9, and T-10. The flaky MCP stdio test did not fail.

### 2.5 Satisfiability of the red tests

`<s5>/s5_fixsketch.py` starts from the `c1_shape_before_match` tree, copies in the pack, and applies one-line sketches of the ruled fixes:

- R-14: strip the role's Vidbyte key and store it, then check it.
- R-15: add a `"_provider_key"` suffix, and add `provider[_-]?key` to `_ERROR_ASSIGNMENT`.
- R-17: the 402 text becomes "…top up the wallet, or, with TextModelMode.AUTO, add your own provider key for {provider} to api_keys…".

Full suite there: `4107 passed, 13 skipped in 36.35s`. So the four red tests can go green together, and the ruled wording keeps the existing table G and managed-pack tests green. The sketches are evidence only; the repair agent writes the real fixes.

### 2.6 Lint

`python lint/run.py` gives `SDK-LINT: PASS`, with no REGRESSED rule. C020 (`api-key-prefix-contract`) is unchanged at `2 / 2 RATCHETED`.

## 3. Choices and deviations

- **T-6:** I added no-key-text checks (D-17) beyond review.md's spec. Each mode/case pair is its own subtest with its assertions inside it, so all four reasons show at HEAD rather than only the first one.
- **T-7:** for the "no key text" check I used the failures file's own `FailureAssertions.assert_credential_safe`, not the agents module's `assert_no_key_text`. It is stricter: it searches the message, `details`, and the formatted traceback for the Vidbyte key, every provider key, and the body canary, and it checks the "Vidbyte gateway openai request failed:" prefix. Importing a helper from another test module would break the pack's idiom. The call is written inline rather than by adding a `mode` to `GatewayCall`, whose docstring defines it as a default-mode call.
- **T-9:** I placed it in `test_provider_keys_matching.py` `SettingsRootTests`, the pack's existing home for `AgentRoleSettings`; the briefing allowed this. The model is deepseek, which matches that class's other role cases.
- **T-10:** I added a kept non-secret header (`Content-Type: application/json`), so a fix that drops everything fails. I also added a combined text that holds both the header and the bearer.
- **FEATURE.md:** I added eight Known Failure Modes lines in one extra `test(sdk):` commit, so each new test ties to a failure-inventory item (feature-test-pack doctrine). The Test Suite Map already names every file used, so it is unchanged.

## 4. Facts for the S5 repair agent

The four targets and their exact assertions are in `test-plan.md` §4, "S5 red targets (pass 1)". In short:

- **R-6:** move the INV-8 shape check above `ProviderKeyMatcher.match`. The `c1` tree proves this is enough for T-6.
- **R-17:** the 402 text must match `wallet`. Any `api_keys` in it must come with `TextModelMode.AUTO`. Keep `provider key` in the paid text, because AC-15's `PAID_FACTS` still requires it. The relay text must still not say `provider key`.
- **R-14:** the role must strip and store the key before the check, so that `role.vidbyte_api_key == VIDBYTE_KEY`.
- **R-15:** both the policy suffix and the free-text regex alternation are needed.
- **Running tests against a scratch tree:** run from inside the tree (`cd <tree>`). Setting `PYTHONPATH` from the worktree root still imports the worktree (§2.1).

## 5. Commits (all on `feat/byok-api-keys`)

`f1f6a4f4` T-2 · `e6ae4990` T-3 · `32cf23e5` T-4 · `d971f491` T-5 · `8b158ed7` T-6 · `6f282122` T-7 · `e213bcfd` T-9 · `963881dd` T-10 · `aeebf97f` FEATURE.md · then `docs(spec): record S5 test pass 1 for byok-api-keys` (this report and test-plan.md).

## 6. Not done, on purpose

- **No T-8 (R-9):** the repo has no S014 rule tests, and creating that harness is outside this pass (orchestrator decision).
- **No case where the list holds only another provider's key (R-5):** it cannot be built, because M-18 fires at every root.
- **No test for R-1, R-7, R-8, R-10 to R-13, R-16, or R-18:** none was specified for this pass (see test-plan.md §2).
