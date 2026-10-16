# S5 test author, pass 2: byok-api-keys (SDK half)

Status: DONE. Branch `feat/byok-api-keys`, started at HEAD `ad6965ea`. Inputs: re-review R-C2 and R-C3 (`reports/S5-rereview-conformance-1.md`), LE-1 from the live test (`pipeline.md`), and the orchestrator's briefing for T-11 to T-13. No file outside `tests/`, `test-plan.md`, and this report changed.

`<s5b>` below means my scratch directory, `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/5bfc4a32-d2a9-4a4d-a6e5-3f472a0fe403/scratchpad/s5-mut2`.

## 1. What I added

All paths are under `tests/features/sdk_provider_keys/`.

| ID | Finding | File → class → test | At HEAD | Commit |
|---|---|---|---|---|
| T-11 | R-13 / R-C2 | `test_provider_keys_matching.py` → `ConfiguredPrimaryTests` → `test_m18_offers_vidbytes_own_account_only_for_a_provider_the_gateway_serves` | green | `2d4486ac` |
| T-12 | LE-1 | `test_provider_keys_failures.py` → `GatewayErrorWordingTests` → `test_a_relayed_provider_400_points_at_the_callers_own_key_in_api_keys_and_a_paid_400_does_not` | **red** | `705862f9` |
| T-13 | R-C3 | `test_provider_keys_security.py` → `CredentialGuardTests` → `test_the_bare_name_provider_key_is_a_secret_name_as_the_free_text_redactor_already_treats_it` | **red** | `a576b25e` |

- Each test commit also appends one line to the Known Failure Modes list in `FEATURE.md` (input + state → wrong output), so the commit count stays one per test.
- The failures file gained one import, `answer` from `managed_text_fixtures`.
- No existing assertion was weakened, skipped, or deleted.
- Every feature symbol is imported inside its test.
- Fake keys come only from the fixtures (`K_XAI`, `VIDBYTE_KEY`, `BODY_CANARY`).
- Each environment is cleared with `patch.dict(os.environ, …, clear=True)`. T-12 gets it through the existing `GatewayCall`, which does the same.
- Mocks sit only at the pack's existing seams: the `transport=` argument of `ScriptedGateway`, and `SLEEP_TARGET`.

## 2. Proof

Every run used `env -u DEEPSEEK_API_KEY PYTHONPATH="$(pwd)" … -q -p no:cacheprovider`, from the tree under test. `vidbyte.__file__` was printed first, and it was the tree's own `vidbyte/__init__.py` every time. Each scratch tree is a `git archive` of the branch with `git init` run in it; nothing was applied to the worktree.

### T-11 (green@HEAD, kills the R-13 revert)

- **HEAD:** `1 passed in 0.77s`.
- **`<s5b>/tree_r13_revert`:** an archive of `ad6965ea`, with `git apply -R` of `git show 940ff97c`. The patch applied cleanly, and the unconditional clause is back at `provider_keys.py:295`. The worktree's new matching file was copied in.
  - pytest: `AssertionError: Regex matched: "Vidbyte's own" matches '(?i)Vidbyte\\W?s own' in "TextModelConfig.api_keys holds keys for xai but none for mistral, … to use MISTRAL_API_KEY or Vidbyte's own mistral account."` and `1 failed in 1.29s`.
  - unittest: both unserved subtests fail (`root='TextModelConfig DIRECT'` and `root='Agent DIRECT'`), giving `FAILED (failures=2)`.
- **`<s5b>/tree_r13_never`** (the opposite mutant: the condition replaced by `if False`, so the clause is never offered): `AssertionError: "Vidbyte's own openai account" not found in '… to use OPENAI_API_KEY.'` and `1 failed in 0.91s`.
- **`<s5b>/tree_head`** (control): `1 passed in 0.69s`.

### T-12 (red@HEAD, for the LE-1 reason)

- **HEAD:** `AssertionError: 'api_keys' not found in "Vidbyte gateway xai request failed: xai returned HTTP 400 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed."`. This is the live test's exact wording.
- **`<s5b>/tree_fix`** (HEAD plus a relay-only 400 clause, `sketch.py … fix`): the pack gives `126 passed`.
- **`<s5b>/tree_both400`** (the clause added on every 400, a wrong fix): it fails at the paid control with `AssertionError: 'api_keys' unexpectedly found in "…; some providers answer a wrong key with HTTP 400, so check your own xai key in api_keys."`. So the control half is not vacuous.
- A probe at HEAD shows the paid control is already green: the paid 400 message has no `api_keys`.

### T-13 (red@HEAD, for the R-C3 reason)

- **HEAD, pytest:** `AssertionError: False is not true : provider_key must be a credential name`.
- **HEAD, unittest:** `FAILED (failures=4)`. There is one failure for each spelling (`provider_key`, `providerKey`, `Provider-Key`), plus "`<K_XAI>` unexpectedly found in `{'provider_key': '<K_XAI>', 'provider': 'xai'}`".
- **`<s5b>/tree_fix`** (`"provider_key"` added to `_SECRET_KEYS`): it passes, and the pack gives `126 passed`.

### Pack, full suite, lint

| Tree | Pack | Full suite |
|---|---|---|
| worktree HEAD `a576b25e` | `2 failed, 124 passed in 1.79s` | `2 failed, 4108 passed, 13 skipped in 36.89s` |
| `<s5b>/tree_fix` | `126 passed in 1.82s` | `4110 passed, 13 skipped in 37.37s` |
| `<s5b>/tree_both400` | `2 failed, 124 passed in 2.08s` | — |

- At HEAD, the only failures are T-12 and T-13. The flaky MCP stdio test did not fail.
- The previous total was `4107 passed`; the difference is +3 tests.
- `python lint/run.py` gives `SDK-LINT: PASS`.
- `ruff check` on the three edited files gives the same 11 findings before (`ad6965ea`) and after, so the edits add none.

## 3. Choices and deviations

- **T-11 file.** The briefing allowed "wherever the pack already asserts M-18 wording". `grep "holds keys for"` finds only an `assertNotIn` in `modes`. The pack's M-18 class is `ConfiguredPrimaryTests` in `test_provider_keys_matching.py` (its docstring is "INV-24, D-5, D-27, M-18"), so T-11 lives there and uses that class's `refused` helper (a `ConfigurationError` with no key text). `test_provider_keys_failures.py` covers table G gateway failures, not construction errors.
- **T-11 served half in the default mode, not DIRECT.** The briefing said to "build the same" (DIRECT) for openai. The orchestrator's ruling is that DIRECT offering "Vidbyte's own openai account" is an accepted limitation. Asserting it there would turn the limitation into a requirement, and a later fix that teaches the matcher the mode would turn the test red for the wrong reason. The default mode is where the clause is true. That half still kills the opposite mutant.
- **T-11 unserved Agent root in DIRECT.** An `Agent` in AUTO on mistral reaches M-18 today. A later change that moves Agent's served-provider check earlier (as R-6 did for `TextModelConfig`) would turn it into M-12 and redden the test for the wrong reason. `model_mode=TextModelMode.DIRECT` reaches M-18 on any ordering.
- **T-11 negative check is a regex** (`(?i)Vidbyte\W?s own`), so swapping in a typographic apostrophe cannot pass it vacuously.
- **T-12 body.** It is the briefing's provider-shaped body. Its `"error"` string also echoes `K_XAI` and `BODY_CANARY`, as xAI's real body echoes a masked key, so `assert_credential_safe` would catch any copied body text. Beyond the briefing, it asserts `400`, one request, no retry wait, and no `quota|daily|wallet`, which are the existing relayed-400 facts. It also proves the relay header before it judges the wording.
- **T-12 class.** It is in `GatewayErrorWordingTests`, as briefed, beside the R-17 test, because it compares the relay and the paid wording for one status.
- **T-13 extras.** `providerKey` and `Provider-Key` normalize to `provider_key` (`credential_keys.py:86-88`), so the one-line fix covers them. The re-review listed them as false too. The test adds `provider` must stay False and the `"provider": "xai"` value must survive, so an over-broad policy fails. It also adds the free-text `provider_key=<key>` check, which is green at HEAD and documents the agreement the finding asks for.

## 4. Facts for repair iteration 2

The exact assertions are in `test-plan.md` §4, under "S5 pass 2 red targets". In short:

- **LE-1:** in `_GatewayAnswer.failure_reason` (`vidbyte_gateway.py`, the `relayed = …` line after the 401/402/403 branch), add a clause only when `relays and status == HTTPStatus.BAD_REQUEST`. The clause must contain `api_keys` and must keep "withheld" and "not billed". A clause on every 400 fails T-12's paid control. The 401/402/403 branch must keep its no-`wallet` rule.
- **R-C3:** add `"provider_key"` to `CredentialKeyPolicy._SECRET_KEYS`. `_YamlSecretKeyPolicy` unions that set when the class is defined, so it follows automatically.
- **R-C1:** deleting the blank line at `provider_keys.py:66` must leave the M-18 condition (`if missing in VIDBYTE_MANAGED_TEXT_PROVIDERS`) in place, or T-11 goes red.
- **Proving against a copy:** run from inside the copy. From the worktree root, `PYTHONPATH=<copy>` still imports the worktree's `vidbyte`.

## 5. Commits (all on `feat/byok-api-keys`)

`2d4486ac` T-11 · `705862f9` T-12 · `a576b25e` T-13 · then `docs(spec): record S5 test pass 2 for byok-api-keys` (`test-plan.md` and this report).

## 6. Not done, on purpose

- **No test for R-C1:** a line count is a `wc -l` fact (test-plan §2).
- **No relayed-400 case for other providers:** the live test caught xai. The existing openai relayed-400 test does not forbid `api_keys` (test-plan §2).
- **No assertion either way about M-18 for a served provider in DIRECT:** that is an accepted limitation.

## 7. Scratch artefacts (`<s5b>`)

- `probe_t11.py` and `probe_t12_t13.py`: behaviour probes at HEAD. They print no real key.
- `940ff97c.patch`: the R-13 commit, reverse-applied in `tree_r13_revert`.
- `sketch.py <tree> fix|both400`: the evidence-only fix sketches.
- The trees: `tree_head`, `tree_r13_revert`, `tree_r13_never`, `tree_fix`, `tree_both400`.
