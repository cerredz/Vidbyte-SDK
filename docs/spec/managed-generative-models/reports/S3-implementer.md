# S3 Implementer report: managed-generative-models

- **Status:** BLOCKED
- **Stage:** S3 implementer
- **Date:** 2026-10-10
- **Branch:** `feat/managed-generative-models`. HEAD is `26ff83e3`. Nothing has been pushed and no PR exists.
- **Prototype:** local branch `wip/managed-generative-models-s3-prototype` at `05618483`. It is never pushed.

## BLOCKED AT

P2, §12.3 row 6, `VidbyteGatewayTransport` same-key retry loop (D-10, INV-16). Main's new lint rule S064 rejects the loop the spec requires. The gate cannot pass without one of the following, and each one needs a decision:
- raising a baseline;
- changing the decided retry semantics;
- gaming the detector.

## DONE SO FAR

All of P1 is committed and passes the full lint gate.

| Row | Commit | What |
|---|---|---|
| 1 | `cc1702df` | `vidbyte/lib/enums/text_model.py`: `TextModelMode` |
| 2 | `6a903355` | `vidbyte/lib/enums/__init__.py` export |
| 3 | `1613b899` | 7 constants in `vidbyte/lib/constants/jev.py` |
| 4 | `75853d3c` | `ProviderModelRegistry.find_vidbyte_api_key` / `resolve_vidbyte_api_key` |
| 5 | `d0e84a53` | `TextModelConfig` managed state; Decision delegates to the shared resolver |
| 10 | `0baef4e1` | `vidbyte/lib/config/__init__.py` re-export |
| 13 | `26ff83e3` | `lint/baseline.json` C020 4→2 (`--rule C020 --update-baseline`) |

P2 (rows 15, 6, 11, 12) and P3 (rows 8, 9) were built as specified, to confirm the conflict. They were then saved and reverted, and the working tree is clean:
- Saved as a WIP commit on `wip/managed-generative-models-s3-prototype` (`05618483`, parent `26ff83e3`).
- Also saved as a patch: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/89243902-3a54-44fb-81e0-5240b0f89dfc/scratchpad/s3/p2p3-prototype.patch`.

P4 (row 14, README) is not started. Its retry and worst-case wording depends on the answer below.

## QUESTION

S064 arrived on main after the spec's base. It rejects the D-10 sleeping retry loop because no cumulative deadline bounds it. Which of these is approved?
- (A) Bound the retries by the call's own timeout. This changes the worst-case wording of D-10, INV-10 and EC-38.
- (B) Raise the S064 baseline from 4 to 5 to accept the loop as specified.
- (C) Something else.

## OPTIONS

1. **A: a cumulative deadline taken from the call's own timeout.**
   - **What changes.** Take `deadline = loop.time() + timeout_seconds` once per call, where `timeout_seconds` is already `max(630, configured)`. Before each retry wait, stop re-sending when `loop.time() + retry_wait >= deadline`, then raise the last answer's error.
   - **What stays.** Each attempt keeps its full 630 s floor (INV-10 and D-9; the tests pin 630.0 on every attempt). Fast retryable answers are re-sent exactly as now: edge pages, 409s and quick 502s. All 32 pack tests stay green, because they run instantly. There is no new constant, class or test change, and every gate passes with S064 at 4.
   - **Consequences.**
     - A slow 502 (for example at the gateway's 600 s deadline) gets at most one more attempt.
     - The worst case falls from about 32 min to about 21 min (2 × 630 + 0.5 s).
     - A deadline 502 is re-forwarded upstream at most once (EC-38).
     - Messages must state the actual number of re-sends.
   - **Spec edits needed:** D-10, INV-10, INV-16, the §9.2 Retries bullet, EC-38, and AC-18 with README row 14 ("about 21 minutes").
2. **B: keep D-10 exactly and accept a fifth S064 finding by raising the baseline from 4 to 5.**
   - The loop has the same shape as the already-baselined `vidbyte/lib/http/transport.py:47` (`HttpTransport.request`, a per-attempt timeout with sleeping retries).
   - The spec, tests and README are unchanged, and the prototype is final as it stands.
   - It needs your explicit approval. The S064 diagnostic itself lists "Raising S064's baseline" under WILL NOT WORK, so S4 review may object.
3. **C: get past the detector without a real deadline. Not recommended.** Ways to do it:
   - rename identifiers away from the retry vocabulary;
   - move the sleep into another module;
   - wrap the loop in `asyncio.timeout(None)`;
   - use a deadline of 3 × timeout + 1.5 s, which the diagnostic calls the bound it objects to.

   Each of these is gaming the rule, and review would reject it.

## RECOMMENDATION

**Option 1 (A).**
- It is the only path where every gate passes with no baseline change and no test change.
- It keeps the retries that matter: fast edge, 409 and 502 answers.
- It removes the costliest path, repeated upstream re-forwarding after a deadline 502 (EC-38).

It does change an orchestrator decision's worst-case wording, so it needs sign-off. Choose B if D-10's rule of "up to two retries regardless of elapsed time" must stay word for word.

## EVIDENCE

**1. S064 is not in the spec base.** `git cat-file -e c0752931:lint/rules/s064_retry_overall_deadline.py` printed:
```
fatal: path 'lint/rules/s064_retry_overall_deadline.py' exists on disk, but not in 'c0752931'
```
The rule arrived with `7f0f5705 feat(lint): add SDK Jev, packaging, and async rules C013-C015, S063-S064 (#600)`, through merge `e91cf822`.

**2. Full lint on the prototype.** Run: `python lint/run.py`. Every other verdict was CLEAN, RATCHETED or IMPROVED, and those IMPROVED verdicts were already there before this change.
```
S064   retry-overall-deadline                      5      4 REGRESSED
S064 REGRESSED: 5 finding(s), allowance 4.
SDK-LINT: FAIL
```

**3. The new S064 finding.** Run: `python lint/run.py --rule S064 --all`.
```
vidbyte/lib/http/vidbyte_gateway.py:165
  for _ in range(JEV_DEFAULT_RETRY_COUNT):
... this for loop retries (JEV_DEFAULT_RETRY_COUNT, retry_wait, JEV_RETRY_BACKOFF_SECONDS, retryable) and sleeps between attempts (`asyncio.sleep(retry_wait)`), but nothing in it compares a clock reading with a deadline ... `timeout_seconds` applies to each attempt, so it restarts with every retry.
```

**4. Contract rules on the prototype.** These show that P2's re-vendor and tracing work.
```
C017   platform-route-contract                     0      0 CLEAN
C018   canonical-api-host                          1      1 RATCHETED
C020   api-key-prefix-contract                     2      2 RATCHETED
```

**5. The spec requires the loop.**
- §9.2 "Retries (binding, D-10)".
- INV-10: "One call makes at most three attempts, so the worst case is about three times the timeout plus 1.5 s".
- §12.6: "Every phase passes the full lint gate".
- NFR-5: "every other rule ≤ its baseline".
- The task rule allows no baseline raise other than the C020 ratchet.

## Prototype results (before the revert)

**Pack tests.** Run: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=short tests/features/sdk_managed_text`. The only failure was the README test, because row 14 was not written.
```
FAILED tests/features/sdk_managed_text/test_managed_text_acceptance.py::ManagedTextAcceptanceTests::test_readme_managed_section_states_the_fee_and_the_limits_that_match_the_constants
1 failed, 31 passed in 1.13s
```

**Full suite.** Run: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=line`.
```
FAILED tests/features/sdk_managed_text/test_managed_text_acceptance.py::ManagedTextAcceptanceTests::test_readme_managed_section_states_the_fee_and_the_limits_that_match_the_constants
1 failed, 3003 passed, 1 skipped in 16.21s
```

**§12.5 contract lookup** (Git Bash):
- `log -1 --format=%H origin/main..feat/generative-model-gateway -- contracts/...` returned `ceabda93ea8f782d0d91f897c05b0ee974f2c5a3`.
- That commit's contract contains `{"name": "models.generate", "methods": ["POST"], "path": "/api/v1/models/generate", "access": "API_KEY", "scope": "models:invoke", ...}`.
- Blob check: `rev-parse` = `git hash-object` = `56d4d0b373994f5de6affd675ed4c209e64d589d`, and the file has no BOM.
- The hosts are unchanged.
- The copy also brings unrelated rows: the agent_runs routes and four error codes (see Open items).

## Gate results at HEAD `26ff83e3` (end of P1)

**Full lint.** Run: `python lint/run.py`.
```
C017   platform-route-contract                     0      0 CLEAN
C020   api-key-prefix-contract                     2      2 RATCHETED
S064   retry-overall-deadline                      4      4 RATCHETED
SDK-LINT: PASS
```

**Area suite.** Run: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=no tests/test_jev_managed_gateway.py tests/test_jev_managed_runs.py tests/test_text_model_runner.py tests/test_config_validation.py tests/test_model_registry.py tests/test_streaming_text_runner.py tests/test_sync_runner_default_transport.py`.
```
69 passed in 0.93s
```

**Full suite.** Run: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=no`. All 24 failures are pack tests that need P2–P4.
```
24 failed, 2980 passed, 1 skipped in 16.90s
```

**Semgrep.** Run: `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off`.
```
Ran 1 rule on 872 files: 0 findings.
```

**Test tree.** `git diff e91cf822..HEAD -- tests` is empty.

## Niche facts for the next agent

- **A007** flags any numeric literal whose enclosing statement, within 7 AST levels, names an operational token. That makes `range(JEV_DEFAULT_RETRY_COUNT + 1)` a finding. The prototype avoids literals: it sends the first attempt, then loops `for _ in range(JEV_DEFAULT_RETRY_COUNT)`, with `retry_wait += JEV_RETRY_BACKOFF_SECONDS`.
- **S051 (I001)** flags a single-line import longer than the line limit. Wrap `from vidbyte.lib.constants.jev import (...)` in `runners/text.py`.
- **C017** passes when the headers come from a local assigned from `bearer_headers(...)` plus `headers[JEV_IDEMPOTENCY_KEY_HEADER] = key`, with the headers passed by keyword into a private `_send(...)` helper whose `self._inner.request(url=VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT, ...)` takes the URL constant.
- The prototype respects the §8.4 budget, using 3 classes: `TextModelMode`, `VidbyteGatewayTransport`, and the module-private `_GatewayAnswer`. `_GatewayAnswer` holds one attempt, decodes once, and has `retryable`, `failure_reason` and `gateway_reason`.
- Each `except` block records only the exception class (`raised = ProviderRequestError` or `raised = Exception`), so `__cause__` and `__context__` are None.
- In this worktree, `tests/test_mcp_stdio_transport.py` failed once under full-suite load and passes alone (16 passed). It has nothing to do with this change.

## Open items

- **EC-26 wording (implementation deviation, pending until S3 resumes).** A 404 `{"detail":"Not Found"}` falls under §9.2 row 6, so the message reads "openai returned HTTP 404 through the Vidbyte gateway; ...", not "Vidbyte returned HTTP 404". No row is added for it.
- **§15 risk note is stale.** The vendored branch copy (`ceabda93`) already contains backend main's agent_runs routes and their error codes, which the note says the branch lacks. This is harmless: all contract rules pass.
- **DONE-path work not done yet:**
  - spec frontmatter (`pr:`, `status`);
  - §6.2 proof SHAs;
  - the §17 row and the deviations list;
  - push and the draft PR;
  - README row 14.
