# S3 Implementer report: managed-generative-models

- **Status:** DONE
- **Stage:** S3 implementer
- **Date:** 2026-10-10
- **Branch:** `feat/managed-generative-models`, pushed to origin.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/759
- **Spec:** r5, `status: implemented`, `pr:` set.

## History of this stage

1. The first pass stopped as BLOCKED at P2 row 6.
   - **Cause.** Main's lint rule S064 (`7f0f5705`) arrived after the spec base `c0752931`. The r4 fixed three-attempt retry loop pushed S064 from 4 to 5.
   - **Decision.** The orchestrator chose option A, a cumulative deadline, and logged it at `596726a1`.
2. Before P2, the binding spec text was revised to r5 in its own commit, `b3df024d`. The revision covers:
   - §2, §4, §5;
   - INV-10, INV-16;
   - AC-18;
   - EC-13, EC-15, EC-38;
   - D-10 and §8.5;
   - §9.2 rows 3, 5 and 6, and the Retries bullet;
   - §12.3 rows 6 and 14, and §12.4;
   - a new row in each of §16 and §17.
3. The P2 and P3 prototype from the blocked pass was rebuilt from the local branch `wip/managed-generative-models-s3-prototype` (`05618483`), and option A was applied to it.
4. Once the real branch held the work, that local branch was deleted with `git branch -D wip/managed-generative-models-s3-prototype`, which printed "Deleted branch wip/managed-generative-models-s3-prototype (was 05618483)." It was never pushed.

## Commits (every row of §12.3, in phase order)

| Phase | Row(s) | Commit | What |
|---|---|---|---|
| P1 | 1 | `cc1702df` | `vidbyte/lib/enums/text_model.py`: `TextModelMode` |
| P1 | 2 | `6a903355` | Export from `vidbyte.lib.enums` |
| P1 | 3 | `1613b899` | 7 constants in `vidbyte/lib/constants/jev.py` |
| P1 | 4 | `75853d3c` | `ProviderModelRegistry.find_vidbyte_api_key` and `resolve_vidbyte_api_key` |
| P1 | 5 | `d0e84a53` | `TextModelConfig` managed state; Decision delegates to the shared resolver |
| P1 | 10 | `0baef4e1` | Re-export from `vidbyte.lib.config` |
| P1 | 13 | `26ff83e3` | C020 baseline 4→2, through `--rule C020 --update-baseline` |
| (spec) | — | `b3df024d` | Spec r5: S064 cumulative retry deadline |
| P2 | 15, 6, 11, 12 | `bbbb87a6` | Endpoint constant, `VidbyteGatewayTransport`, re-vendored contract, Provenance row and Change Log, in one commit |
| P3 | 8 | `b8a46cda` | `TextModelRunner` pinning and per-call gateway transport |
| P3 | 9 | `632dfcc1` | `StreamingTextModelRunner` managed refusal |
| P4 | 14 | `0bc85ac8` | README `### Vidbyte-managed text calls` |
| docs | — | `0ed46446` | Spec `pr:` and `status: implemented` |
| docs | — | `db80235a` | Spec §6.2 proof SHAs, §17 S3 row, implementation deviations |

Row 7 was withdrawn, so it has no commit.

## Option A as built

Code: `vidbyte/lib/http/vidbyte_gateway.py`, `VidbyteGatewayTransport.request`.

**The deadline.**
- Before the first POST, the transport takes `loop = asyncio.get_running_loop()` and `deadline = loop.time() + timeout_seconds`.
- `timeout_seconds` is already floored by the runner to `max(630.0, configured)`.

**The re-send loop.**
- It runs `for resends in range(JEV_DEFAULT_RETRY_COUNT)`.
- It breaks when `not answer.retryable() or loop.time() + retry_wait >= deadline`.
- Otherwise it waits with `await asyncio.sleep(retry_wait)`, adds `retry_wait += JEV_RETRY_BACKOFF_SECONDS` (0.5 s, then 1.0 s), and sends again with the same key and envelope.
- A `for ... else` sets `resends = JEV_DEFAULT_RETRY_COUNT` when every allowed re-send was made.
- Each attempt keeps its full `timeout_seconds`.

**Messages.**
- The row 3, 409 and 502 messages say "the SDK re-sent it with the same Idempotency-Key (re-sends in this call: N)".
- When the deadline left no time for the first wait, they say "the SDK did not re-send it, because the call's <timeout> s timeout left no time for another attempt".

**Budget.** Nothing new was added: no constant, class or file.

**Scratch check with a fake event-loop clock** (`scratchpad/s3/deadline_check.py`, not a repo test). Every attempt answered 502 after `step` seconds:
```
step=0.0: POSTs=3 :: ... (re-sends in this call: 2).
step=300.0: POSTs=3 :: ... (re-sends in this call: 2).
step=600.0: POSTs=2 :: ... (re-sends in this call: 1).
step=629.8: POSTs=1 :: ... the SDK did not re-send it, because the call's 630 s timeout left no time for another attempt.
```

## Gate results at code HEAD `0bc85ac8` (later commits are docs only)

**(a) Pack tests.** Run: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/sdk_managed_text`.
```
................................                                         [100%]
32 passed in 0.96s
```

**(b) Full suite.** Run: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=line`. `tests/test_mcp_stdio_transport.py` passed in this run, so no separate re-run was needed.
```
...................................................................s.... [ 98%]
.....................................................                    [100%]
3004 passed, 1 skipped in 15.51s
```

**(c) Lint.** Run: `python lint/run.py`. Every other rule is CLEAN, RATCHETED or IMPROVED. The IMPROVED verdicts already existed before this branch, and no baseline other than C020 was touched.
```
C017   platform-route-contract                     0      0 CLEAN
C018   canonical-api-host                          1      1 RATCHETED
C019   platform-error-code-contract                0      0 CLEAN
C020   api-key-prefix-contract                     2      2 RATCHETED
S064   retry-overall-deadline                      4      4 RATCHETED
SDK-LINT: PASS
```

**(d1) CI source stage.** Run: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`. Exit code 0.
```
tests\test_web_operation_client_retry.py ..                              [100%]

====================== 3004 passed, 1 skipped in 17.08s =======================
CI passed.
```

**(d2) CI package stage.** Run: `unset PYTHONPATH; python scripts/run_ci.py --stage package`. Exit code 0, and `env | grep -c '^PYTHONPATH='` printed 0.
```
No broken requirements found.
...
Installed vidbyte-sdk 0.2.1 passed smoke checks.
CI passed.
```

**(e) Semgrep.** Run: `pysemgrep.exe scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off`. Exit code 0.
```
Ran 1 rule on 872 files: 0 findings.
```

**P2 checked on its own.** With the P3 files set aside, at P2 commit `bbbb87a6`, `python lint/run.py` printed `S064 ... 4 4 RATCHETED` and `SDK-LINT: PASS`. The full suite there was "24 failed, 2980 passed"; every failure was a pack test waiting on P3 or P4.

**Test tree.** `git diff e91cf822..HEAD -- tests` is empty, and no test file was changed.

**Production files.** `git diff --name-only e91cf822..HEAD` lists production `.py` files only under `vidbyte/lib/`:
- `config/__init__.py`
- `constants/jev.py`
- `dataclasses/model_configs.py`
- `enums/__init__.py`
- `enums/text_model.py`
- `http/vidbyte_gateway.py`
- `registries/models.py`
- `runners/streaming_text.py`
- `runners/text.py`

## Contract re-vendor (§12.5)

All commands ran from Git Bash.
- `git -C C:/Users/422mi/vidbyte-repos/vidbyte fetch origin` ran first.
- `log -1 --format=%H origin/main..feat/generative-model-gateway -- contracts/vidbyte-platform-contract.json` returned `ceabda93ea8f782d0d91f897c05b0ee974f2c5a3` ("chore(contract): regenerate platform contract with the models.generate route").
- The route check matched: `{"name": "models.generate", "methods": ["POST"], "path": "/api/v1/models/generate", "access": "API_KEY", "scope": "models:invoke", ...}`.
- The copy was made with `git show <commit>:contracts/vidbyte-platform-contract.json > lint/contracts/vidbyte-platform-contract.json`.
- Blobs match: `rev-parse` = `git hash-object` = `56d4d0b373994f5de6affd675ed4c209e64d589d`. The file starts with `{\n`, so it has no BOM.
- `source.commit` is `74b6b015e7938e2c6084272a42fae70277ff77e0`.
- Hosts, envelope and headers are unchanged.

## §8.4 budget

| Item | Used |
|---|---|
| New files | 2: `vidbyte/lib/enums/text_model.py`, `vidbyte/lib/http/vidbyte_gateway.py` |
| New classes | 3: `TextModelMode`, `VidbyteGatewayTransport`, module-private `_GatewayAnswer` |
| New config keys | 1 field (`TextModelConfig.mode`) and 8 constants (`VIDBYTE_API_KEY_PREFIX`, `VIDBYTE_API_KEY_PATTERN`, `VIDBYTE_API_KEY_ENV_VAR`, `VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT`, `VIDBYTE_MANAGED_TEXT_PROVIDERS`, `VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS`, `VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS`, `VIDBYTE_MANAGED_KEY_PLACEHOLDER`) |
| Env vars | 0 |
| Dependencies | 0 |

`_GatewayAnswer` holds one attempt: its answer, its decoded body, and the kind of exception its send raised. Its methods are `retryable`, `failure_reason` and `gateway_reason`.

## Implementation deviations

These are also recorded in spec §17 under "Implementation deviations (S3)".

1. **EC-26.** A 404 `{"detail":"Not Found"}` is decided by §9.2 row 6: "<provider> returned HTTP 404 through the Vidbyte gateway; the provider's message is withheld, and the call was not billed". No row was added for it.
2. **Contract copy.** `ceabda93` already carries backend main's agent_runs routes and four agent_run error codes, which the §15 risk note expected the branch copy to lack. This is harmless.
3. **README example.** The comments moved off column 0, because the AC-18 test ends the section at the first line that starts with `# `.
4. **Re-send wording.** It follows r5, as shown above.

## Completeness pass

- **§12.3.** Every row has a commit (row 7 is withdrawn).
- **Narration.** These main functions are narrated: `TextModelRunner.__init__` and `arun`, `VidbyteGatewayTransport.request`, and the new step in `StreamingTextModelRunner.__init__`.
- **`@intent` comments.** Every new key, request, provider and retry function carries one.
- **Literals and messages.**
  - There are no numeric literals in the new code.
  - The only `vb_live_` literal is `VIDBYTE_API_KEY_PREFIX`.
  - There are no `model_gateway_*` literals.
- **Exceptions.** Only `Exception` is caught, and the error is raised after the `except` block. Every inner `.request` call passes `timeout_seconds`.
- **Size.** Every touched file is under 1,000 lines (`jev.py` is about 757).
- **Not changed:**
  - `vidbyte/lib/http/__init__.py` (row 7 withdrawn, R-10);
  - `vidbyte/providers/`, `vidbyte/agents/`;
  - `pyproject.toml`.

## Niche facts for the next agent

- **A007** flags any numeric literal whose enclosing statement, within 7 AST levels, names a retry, timeout or status token. The loop therefore counts re-sends with `for resends in range(JEV_DEFAULT_RETRY_COUNT)` plus `for ... else`, never with `+ 1`.
- **S064** counts `loop.time() + retry_wait >= deadline` inside the loop as a deadline check. Shortening the per-attempt timeout is forbidden (INV-10).
- **C017** traces the headers through a local built from `bearer_headers(...)` plus `headers[JEV_IDEMPOTENCY_KEY_HEADER] = key`, passed by keyword into the private `_send(...)`.
- **S051/I001** flags an over-long single-line import. Wrap multi-name imports in parentheses.
- **README test.** The section runs until the next line matching `^#{1,3} `. That includes `# ` comment lines inside code blocks, so keep README code comments off column 0.
- **Full-suite flake.** `tests/test_mcp_stdio_transport.py` failed once under full-suite load earlier in this stage (it passes alone, 16 passed). It passed in the final run.

## Open items

- None blocking.
- Backend merge order (§15): if the backend PR is squash-merged, re-vendor the contract from backend `main` in a follow-up SDK PR. The orchestrator owns any later re-vendor.
