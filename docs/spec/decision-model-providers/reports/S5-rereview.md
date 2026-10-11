# S5 re-review (round 1): decision-model-providers

Reviewed: `git diff 9784a3f6 7ee8ebbd -- vidbyte/ tests/ REPO_MAP.md` (every hunk, every touched file read whole at 7ee8ebbd), plus the full `origin/main...7ee8ebbd` budget and boundary checks. Local HEAD 3d9a8c92 differs from 7ee8ebbd only in `docs/spec/decision-model-providers/pipeline.md`; the tree is clean.

LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — all seven repairs hold and nothing else regressed, but the R-2 fix's `timeout_seconds` check refuses float subclasses that spec row 5 admits, so TypeSafe decisions that worked on main now fail (INV-23), and the spec does not record that deviation.

## Per-fix verdicts (R-1, R-2, R-3, R-4, R-6, R-7, R-16)

| ID | Verdict | My evidence |
|---|---|---|
| R-1 | **fix holds** | Real runner over a scripted transport. OpenRouter: none → `{"true": null, "false": null}`; true(desc) → `{"true": "yes when", "false": null}`; false → `{"true": null, "false": null}`; both → `{"true": "a", "false": "b"}`; `(false, true(desc))` → `{"true": "a", "false": null}`. Perplexity and TypeSafe are unchanged for every subset (true-only gives `{"true": "yes when"}`, none omits `criteria`). An old-vs-new probe of `_TypeSafeCallBuilder.decision` (origin/main source vs 7ee8ebbd; 7 question shapes × direct/retried/managed, with and without a `run_id`) gave **0 mismatches**. `tests/test_jev_agent.py` is green inside the 406-test area run. The README, `SystemOneHost` docstring and `systemone.py` KNOWN EDGE CASES all say "both keys, each with its description or null". |
| R-2 | **fix holds, with one regression (R-C1)** | `DecisionHttpCall` is defined in `vidbyte/lib/dataclasses/jev.py:501`: frozen, slotted, with the seven fields in order, `headers` `repr=False`, and listed in `__all__`. `jev.py` imports nothing from `vidbyte.lib.http`. `vidbyte.providers.decisions.DecisionHttpCall is vidbyte.lib.dataclasses.jev.DecisionHttpCall` is True, and `decisions.__all__ == ['DecisionFailures', 'DecisionHttpCall', 'DecisionTransport']`. `DecisionTransport.send` keeps its `@intent`. All six sends now use `DecisionTransport.send`: systemone.py:270, openai_decisions.py:266, and typesafe.py:247, :280, :306. The docs match rows 5, 12, 18 and 19 word for word. AC-23: each of the 12 listed bad values, plus `method=None`, `retry_count=1.0` and `idempotency_key=5`, gives the exact `Invalid Jev decision call <field>: expected <rule>; received <type> <repr>.` message with `details["field"]`. No message or `details` carries the key, and `repr` omits `headers`. Regression: rule 3 is stricter than row 5 (R-C1). |
| R-3 | **fix holds** | `test_system_one_provider_refuses_a_managed_per_call_config_before_any_call` passes. I deleted the two-line per-call managed guard in memory and re-ran it: `failures=0 errors=1`. Unmutated: `0/0`. So the test can fail. |
| R-4 | **fix holds** | Each main function now calls a flat list of helpers. `build` calls `question` and `text`; `encode` calls `text` and `option`; `normalize` calls `_by_name`, `_require_type`, `_predicate`, `_entries`, `_level`, `_distribution`, `_choice` and `_score`. No helper calls another helper except `self.error`, which review R-4 allows. My own differential probe (9784a3f6 module vs 7ee8ebbd, decoded as UTF-8) covered 4 request shapes and 27 answer sets: refusal, wrong type, probability 1.5 and bool, missing probability, non-list and non-object `probabilities`, a duplicate option (3- and 4-entry forms), missing and extra options, a choice outside the options, a distribution that does not sum to 1, bad confidence, bad score, label and index fallback, a bool or out-of-range index, duplicate, missing, extra and nameless names, and a non-list `answers`. **31 cases, 0 behavioural mismatches.** One raw mismatch was a cp1252 decoding artifact in my first run; re-decoding as UTF-8 made it equal. The INV-8 duplicate guard is still at openai_decisions.py:226. Deleting it in memory turns the new test red (`failures=1`). Every malformed case is a `ProviderResponseError` that keeps `details["usage"]`. No class was added (13/13). |
| R-6 | **fix holds** | The "Keys" bullet lists 16 variables, equal to `{API_KEY_ENV_VARS[p] for p in DECISION_SUPPORTED_PROVIDERS}` with none missing and none extra. The README is 52,543 characters (UTF-8, BOM stripped), within §12.4's 54,000. A009 is CLEAN. |
| R-7 | **fix holds** | `SystemOneProvider._MANAGED_REFUSAL` equals, byte for byte, the sentence that appears twice at 9784a3f6 (2 exact occurrences). Both guards raise it. The config-less constructor error now has a comment saying why it names `"systemone"`. |
| R-16 | **fix holds** | The pack README no longer says every test is red, and its Logs run through the S4 grant ("90 tests, the R-1 cases and the R-2 test red until the repair lands"). |

## WHAT THE IMPLEMENTATION GETS RIGHT
- **TypeSafe call bytes are unchanged.** Comparing origin/main's `_TypeSafeCallBuilder.decision` with 7ee8ebbd's over 7 question shapes in direct, retried and managed mode gives 0 mismatches in method, URL, headers, timeout, JSON body, retry count and idempotency-key presence. `repr(call)` hides both headers and the `vb_live_` key (INV-23, INV-24). Do not re-split the shared pieces.
- **The R-2 placement matches spec r11 exactly.** The record is in `lib/dataclasses/jev.py` and `send` is in the providers layer (`DecisionTransport`). The re-export is the same class object. The rule order and the field and rule strings match row 5 (apart from R-C1). The headers are never inspected. Keep `retry_count` on `JevCount.require`: it gives rule 5's text verbatim and rejects bool.
- **The R-4 flattening changes no behaviour** across 31 old-vs-new cases, and it adds no class, so §8.4 holds at 3 new files and 13 new classes (I counted 13 `+class` against 4 relocated `-class`). Do not lift these helpers into a new class.
- **Gates and boundaries hold.** Pack: 90 passed. Area suite: 406 passed. `python lint/run.py` exits 0 with `SDK-LINT: PASS` and 0 REGRESSED (C002 9/9, C009 1/1, C010 0, S014 0, A009 0, S009 349/350). Both test-contract diffs and the `lint/baseline.json` diff are 0 bytes. No `noqa` or `type: ignore` was added. Every touched file is a §12.3 row or the C010 lock. The §4 snippet reproduces AC-1.

## FINDINGS

R-C1 [Major] [deviations / spec row 5 / INV-23] vidbyte/lib/dataclasses/jev.py:525 — `DecisionHttpCall` refuses `float` and `int` subclasses (for example `numpy.float64`) that spec row 5 rule 3 admits. A TypeSafe decision whose `DecisionModelConfig.timeout_seconds` is such a value worked on origin/main and now fails before any request (INV-23). The spec does not record this deviation, and lint C002 did not force it.
  Evidence: the line is `if type(self.timeout_seconds) not in (int, float) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= JEV_TIMEOUT_FLOOR_SECONDS:`. Spec row 5 rule (3) reads: "`timeout_seconds` that is a `bool`, is not an `int` or `float`, is not finite (`math.isfinite`), or is `<= JEV_TIMEOUT_FLOOR_SECONDS`". A float subclass *is* a `float`. `DecisionModelConfig` accepts it (`model_configs.py:387`: `isinstance(self.timeout_seconds, (int, float))`). The repo's own precedent for this exact rule, `JevAgentSettings._validate_timeout` (`vidbyte/agents/jev/settings.py:193`), admits it too. My probe (python stdin; origin/main `typesafe.py` exec'd beside 7ee8ebbd):
  ```
  numpy.float64(30.0) | config accepted; resolved timeout type: float64
     origin/main _TypeSafeCallBuilder.decision -> call built, timeout 30.0
     7ee8ebbd  -> ConfigurationError Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received float64 np.float64(30.0).
  runner Seconds(30.0) vidbyte_managed -> ConfigurationError : Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received Seconds 30.0. | requests sent: 0
  runner numpy.float64(30.0) typesafe -> ConfigurationError : ... | requests sent: 0
  ```
  (`Seconds` is `class Seconds(float): pass`.) The "forced by C002" justification (`reports/S5-repair-1.md`, R-2 second bullet) does not hold. C002's matcher `_bool_guard_identity` (`lint/rules/c002_duplicate_inline_bool_guard_validation.py:86-95`) matches only an `isinstance(<name>, bool)` call whose second argument is the bare name `bool`. A spelling such as `type(x) is bool` is not matched. Spec §17 "Implementation deviations" (items 1–8) has no entry for this.
  Failure: a `DecisionModelConfig(timeout_seconds=numpy.float64(30.0))`, or any float subclass, in direct or `VIDBYTE_MANAGED` TypeSafe mode (the `JevAgent` gateway path) makes every `arun`, `alist_models` and `aclose_run` raise `ConfigurationError` with 0 requests sent, where origin/main sent the call. The message contradicts itself: "expected a finite number of seconds greater than 0; received … 30.0". The 15 new hosts are affected the same way. This is a must-not-regress invariant broken by a fix that went beyond the spec, so a human reviewer would ask for the one-line change before merge.
  Smallest fix: at jev.py:525, replace `type(self.timeout_seconds) not in (int, float)` with `type(self.timeout_seconds) is bool or not isinstance(self.timeout_seconds, (int, float))`, and update the comment above it. This is C002-neutral (no `isinstance(…, bool)`) and does not change the AC-23 messages: `True`, `0`, `-1.0`, `inf` and `nan` are still rejected with the same text. Recommended test grant (optional; the pack stays green either way): one positive subtest in `DecisionHttpCallTests` showing that a `float` subclass timeout (`class Seconds(float)`) constructs. Otherwise a revert to `type(...)` survives.
  Spec IDs: §12.3 row 5 rule (3), AC-23 (scope of the rule), INV-23, FR-12; template "Deviations" (necessary, minimal, recorded).

R-C2 [Minor] [deviations] docs/spec/decision-model-providers/spec.md:919 — §17 implementation deviation 4 still lists `OpenAIDecisionsAnswers._answer`, which R-4 renamed `_require_type` with a narrower job. Deviation 4 does not list `_require_type`.
  Evidence: spec.md:919 reads "`OpenAIDecisionsAnswers._by_name`/`_answer`/`_predicate`/`_choice`/`_score`/`_entries`/`_distribution`/`_level`". At 7ee8ebbd, `openai_decisions.py:185` defines `def _require_type(...)`, and no `def _answer` remains. The R-4 commit 2da50682 also changed the private signatures `question(question, *, instructions)` and `option(name, description, *, key)`. These are not §8.5 contracts, so only the name list is stale.
  Failure: the spec's record of private helpers names a method that no longer exists. A reader checking the deviation list against the code finds a mismatch. There is no behaviour impact.
  Smallest fix: in deviation 4, replace `_answer` with `_require_type`. This is a spec-only edit by the spec owner.
  Spec IDs: §17 deviation 4; FR-9 (helper inventory only).

No other finding. Open follow-ups R-5, R-8 to R-15 and R-17 are not re-raised. The R-7 repair's private `ClassVar` sits beside R-8's open `_LABEL` question but does not make it worse: it is an error sentence, not a wire literal, and the repair gave its reason.

## Conformance pass over the IDs the repair touched

| ID | Result | Evidence |
|---|---|---|
| INV-6 / EC-6 | holds | R-1 probe above. AC-4's `{"true": null, "false": null}` holds for an optionless noul. |
| INV-23 | **violated on one path** | 0 old-vs-new mismatches for ordinary configs, but R-C1 for float-subclass timeouts. A `bool`, `inf` or `nan` timeout also fails now, but row 5 itself rules those out, so they are spec-sanctioned and not a finding. |
| INV-24 | holds | `tests/test_jev_managed_gateway.py` is green. Probe: `"headers" in repr(call)` is False and `vb_live_` is not in `repr`. `_TypeSafeCallBuilder(parser).decision(config, request, run_id=...)` is unchanged. |
| INV-28 | holds | The R-3 test is green and a mutant makes it fail. `_config_for` raises `_MANAGED_REFUSAL` with `provider="typesafe"` and 0 requests. |
| INV-8 | holds | Duplicate option, probability 1.5, a sum other than 1, a bad score and a choice probability of 1.5 are each a `ProviderResponseError` with usage. `normalize` raises no bare `ConfigurationError`, because every record-building step sits inside its `try`. |
| AC-17 | holds | `(true(desc), false)`, `(true(desc),)` and `(false(desc),)` are all refused before any call, identically before and after R-4. The test gap for the single-description input is still R-13, open. |
| AC-19 | holds | `test_adapter_refuses_a_config_for_another_provider_before_any_call` is green. The `_config_for` provider check is unchanged. |
| AC-23 | holds | Every listed value gives the exact message and `details["field"]`, the key never appears, `repr` omits headers, and the class identity is True. |
| FR-6 / D-3 / row 12 | holds | `DecisionTransport` plus `DecisionFailures`, the record re-exported, `__all__` as specified, and the header fields updated as row 12 lists them. |
| FR-12 / row 5 | holds except R-C1 | Placement, fields, order, `repr`, imports, `__all__` and header lines are as specified. Rule 3 over-rejects. |
| §8.4 | holds | 3 new files, 13 new classes (4 relocated plus 9 new), 0 dependencies. The repair added no config key, collection or endpoint. All 22 touched paths are §12.3 rows 1–21 or `lint/pricebook_vintage_lock.json`. |
| §8.5 | holds | `DecisionTransport.send(call, transport) -> HttpResponse` is a static async method, and the record shape matches the §8.5 block. |
| Rows 13, 14, 15 | holds | Sends via `DecisionTransport.send` with the import widened. ARCHITECTURE NOTEs say "via `DecisionTransport.send`". |
| Rows 18, 19 | holds | The README `decisions.py` bullet and the two REPO_MAP rows match the spec text word for word. |
| AC-1 (§4) / §5 | holds | See COMMANDS. The call path `run_decision → _call (SystemOneRequest/OpenAIDecisionsRequest build+encode) → DecisionTransport.send → HttpTransport.request` matches the §5 flowchart. |
| §14 Never | holds | Both test-contract diffs and the baseline diff are 0 bytes. 0 added `noqa` or `type: ignore`. No TODO or stub markers. |

VERIFIED CLAIMS:
1. S5-repair-1 "pack 90 passed": **held** (90 passed in 1.03s).
2. "area suite 406 passed": **held** (406 passed in 2.53s).
3. "lint PASS; C002 9/9, S009 349/350, S051 257/259, A001 643/643; no REGRESSED": **held** (exit 0, 0 REGRESSED lines).
4. "both test-contract diffs empty": **held** (0 bytes each). The `lint/baseline.json` diff against origin/main is also 0 bytes.
5. "R-4 old-vs-new probe MISMATCHES 0": **held** on my own independent 31-case probe.
6. "R-7 sentence byte-identical": **held** (2 exact occurrences at 9784a3f6 equal `_MANAGED_REFUSAL`).
7. "R-6: 16 variables, README 52,543 characters": **held**.
8. "`jev.py` imports nothing from `vidbyte.lib.http`": **held** (import block lines 14–98 at 7ee8ebbd).
9. "`retry_count` via `JevCount.require` gives rule 5's text verbatim and rejects bool": **held** (`received bool True`).
10. "`timeout_seconds` exact-type check is forced by C002; float-subclass refusal is acceptable": **did not hold.** C002 matches only `isinstance(<name>, bool)` (c002…py:86-95), so a spec-conformant C002-neutral spelling exists. The refusal breaks TypeSafe (R-C1).
11. "§8.4 class budget 13/13": **held** (13 `+class`).
12. Spec r11 row 5 "the record imports nothing above `vidbyte/lib/`; rules in declaration order": **held**.
13. Review "What the implementation gets right": "§4 snippet reproduces AC-1 exactly": **held** at 7ee8ebbd.
14. Test plan rows 48, 77 and 80 (R-1, R-3, AC-23 coverage): **held**. All three tests exist, pass, and the R-3 and R-4 guard tests fail under their mutants.

COMMANDS RUN:
- `git log --oneline -15`; `git status --short | wc -l` → `0`; `git diff 3d9a8c92 7ee8ebbd --stat` → only `docs/spec/decision-model-providers/pipeline.md`.
- `git diff 9784a3f6 7ee8ebbd -- vidbyte/ tests/ REPO_MAP.md` (read in full); `git show 7ee8ebbd:<file>` for each touched module.
- `python -m pytest tests/features/decision_model_providers -q` → `90 passed in 1.03s`.
- `python -m pytest tests/test_jev_agent.py tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_jev_usage_ledger.py tests/test_jev_preflight.py tests/test_jev_done.py tests/test_model_registry.py tests/test_agent_pricing.py tests/test_embedding_runner.py tests/test_agent_settings_validation.py -q` → `406 passed in 2.53s`.
- `python lint/run.py` → `SDK-LINT: PASS`, exit 0, `grep -c REGRESSED` = 0; C002 `9 9 RATCHETED`, S009 `349 350 IMPROVED`, S051 `257 259 IMPROVED`, A009 `0 0 CLEAN`, C009 `1 1`, C010 `0 0 CLEAN`, S014 `0 0 CLEAN`.
- `git diff 90ed9a29 7ee8ebbd -- tests/features/decision_model_providers/ | wc -c` → `0`; `git diff $(git merge-base origin/main 7ee8ebbd) 7ee8ebbd -- tests/ ':(exclude)tests/features/decision_model_providers' | wc -c` → `0`; `git diff origin/main...7ee8ebbd -- lint/baseline.json | wc -c` → `0`.
- `git diff origin/main...7ee8ebbd -- vidbyte/ | grep -E "^[+-]class "` → 13 added, 4 removed; `git diff --name-only origin/main...7ee8ebbd` → 22 non-docs, non-pack paths, all §12.3 rows or the lock.
- §4 snippet (python stdin): no keys → `ConfigurationError Missing API key for provider perplexity. Pass api_key or set PERPLEXITY_API_KEY.`; scripted → `perplexity: 0.8 billing (<ModelProvider.PERPLEXITY: 'perplexity'>, 'pplx-decider-v1.1-27b') https://api.perplexity.ai/v1/decisions Bearer`, `openai: {'true': 0.8, 'false': 0.19999999999999996} gpt-6-luna https://api.openai.com/v1/decisions`, `cloudflare constructed: clef-flash`, and without an endpoint `No default endpoint registered for provider 'cloudflare'. Pass endpoint explicitly with the provider's base URL.`
- R-1 criteria probe and TypeSafe old-vs-new call probe (python stdin) → `typesafe old-vs-new call mismatches: 0` plus the criteria table above.
- R-4 differential probe (python stdin, 9784a3f6 source exec'd as UTF-8) → `cases 31, mismatches 0`.
- AC-23 probe (python stdin) → all 17 bad values rejected with the row 5 text; `same class: True`; `frozen: True | slots: True`; `headers` field `repr=False`.
- Float-subclass probe (python stdin, numpy 2.2.6 present in the env) → output quoted in R-C1.
- In-memory mutation runs (python stdin, unittest): per-call managed guard dropped → `failures=0 errors=1`; duplicate guard dropped → `failures=1 errors=0`; unmutated → `0/0` for both.
- Read `lint/rules/c002_duplicate_inline_bool_guard_validation.py` (matcher: `node.func.id == "isinstance"` and `node.args[1].id == "bool"` only).
