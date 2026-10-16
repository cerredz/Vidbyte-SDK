# S5 · Repair agent — iteration 1 of 8

Status: DONE
Start: HEAD `0b5af348` (pushed). The working tree was clean except for the orchestrator's uncommitted `pipeline.md` edit, which is not mine. I left it untouched and never staged it.
End: code HEAD `8d8ba811` (pushed, CI dispatched on it), then one docs-only commit for verify-log.md, the review.md statuses, and this report.
Scratch: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/ece663b4-5090-422c-ad68-c3b2451a23f6/scratchpad/s5r1/` holds `probe_r6.py`, `touched.py` (filters a lint JSON to the PR's touched files), `r12_tests_fields.py`, `review_status.py`, the lint JSONs, and the CI logs.

## Inputs read
house-style.md, review.md, reports/S4-findings-verifier.md, and the S4 conventions review (R-V2…R-V6). AGENTS.md (in context). Spec §6 rows EC-4/EC-10/EC-18/EC-19/EC-30, INV-15, §7 FR-5/NFR-6/NFR-8, §10 T-5, §15, and §17. Code map §1. The A002 rule source (window and policy tokens). The verify-log format in report-formats.md.

## Defects in
R-2 (Major), R-6, R-8, R-9, R-10, R-11, R-12, R-13, R-14 (Minor), plus spec §15 Q-9/Q-10 bookkeeping. No failing gate came in.

## Per-finding work

| ID | Reproduced by | Change | Verified by | Commit |
|---|---|---|---|---|
| R-2 | `lint/run.py --rule A002 --all --format json`: 579, with touched-file hits `transport.py` 34, **55**, **78**, 96, 122 and `errors/base.py` 166/299/314/323 | Added `# @intent json-body-or-content-never-both` in `request` and `# @intent content-bytes-go-out-verbatim` in `_send_once`, each directly above the comment the PR added (def+2, ≤ 72 columns). Added a spec §17 deviation bullet with the NFR-6 reading and the untouched findings: A002 `errors/base.py:166/299/314/323`; A002 `transport.py:34/98/124` (34/96/122 before the insert); S001 F401 `vidbyte/__init__.py:434/436/581/588`. I checked every number against the final JSON | A002 577/703 IMPROVED; the touched-file list no longer holds 55/78; pack `664 passed` | a39cf95b |
| R-6 | Probe: `payload=lambda r, c: MappingProxyType({...})` → unsigned and signed both `TypeError: Object of type mappingproxy is not JSON serializable` | `body = dict(body)` after the mapping check in `WebhookOutput.send`, with a two-line comment | The probe shows both paths `SENT` with wire `{'text': 'Body text'}`; S009 350/350; pack `664 passed` | 1e678c38 |
| R-8 | `jira.py:77` and `confluence.py:68` hold the identical `"Basic " + base64…` line | New `OutputHttp.basic_authorization(username, password) -> str` in `delivery.py`, called from both. Removed the now-unused `import base64` from both. One clause each in the `delivery.py` header and the README module entry | `-k "jira or confluence or first_batch or wire"` → `124 passed`; pack `664 passed`; S001 56 (unchanged); I001 clean | efb2c26b |
| R-9 | README Email-in and Webhook receivers sections had no date line | "Links in this section retrieved 2026-10-14." under each table | pack `664 passed` (AC-35 doc tests) | 47696121 |
| R-10 | README rows :86/:89/:92 lacked the EC-4, EC-10, and T-5 clauses | One clause per row | pack `664 passed`; README 32,050 characters (limit 40,000) | 3bc709e3 |
| R-11 | `vidbyte/agents/README.md:252` listed only first-batch kinds | The sentence now uses the category list from `vidbyte/lib/README.md:42` | A009 clean; pack `664 passed` | bde205cd |
| R-12 | The TESTS fields of ten headers omitted the new covering files | One line 9 rewrite per file. The script refuses to run if line 9 is not the expected text. Files chosen by grep evidence | A001 643/643 RATCHETED; pack `664 passed` | 3f5623ca |
| R-13 | README step 3 said "private static helpers"; `github.py:79/86/93/114` are async instance methods | Reworded and rewrapped step 3 | pack `664 passed` | 9fb29e3b |
| R-14 | `teams.py:48` `# @intent teams-text-is-plain` | Renamed to `teams-text-cannot-mention` | `git grep` finds no other reference in vidbyte/ or tests/; A002 577 | a1405d71 |
| Q-9/Q-10 | — | Spec §15 rows after Q-8, both `[scope-adding, S4]`, non-blocking, default **No**; not built | — | 8d8ba811 |

Hypotheses that failed or were rejected, so the next agent does not retry them:
- R-6: my probe's first print used a non-existent `receipt.error`. The bug was in the probe, not in the code; the corrected probe passes.
- R-8: I rejected `OutputArguments` as the home, because it checks constructor arguments while the header is built at send time. I also rejected caching the header in `__init__`, because it would add a second attribute that carries the secret.
- R-13: the first edit left a ragged line, so I rewrapped step 3 and amended my own unpushed commit. No pushed history changed.
- Side check: plain `ruff check` with the default config reports UP012 ×3 and PIE810 at `transport.py:227–237`. They predate this iteration (225–235 at `0b5af348`), sit in untouched code, and fall outside `lint/ruff.toml`'s selection. Plain `ruff format --check` also flags the original touched files. Neither is a gate, so I left both alone.

## Test changes proposed
None. No fix needed a test change. Tests are untouched since `05fbe43e`.

## Findings I believe are wrong
None.

## Gate matrix
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (pack) | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` | PASS | `664 passed in 5.08s` |
| lint | `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `A002 IMPROVED 703 -> 577` … `S064 RATCHETED: 4 known finding(s)` · `SDK-LINT: PASS` (exit 0). Every other count equals S3's (S001 56, S061 5, S017 78, S025 261, C011 1, C012 23, S008 19, S009 350, A001 643, S054 3). No baseline edited |
| NFR-6 seven rules | `lint/run.py --rule <A002,S061,S001,S017,S025,C011,C012> --all --format json`, filtered to touched files | PASS (reading per §17) | A002 577/703: only `errors/base.py` 166/299/314/323 and `transport.py` 34/98/124 (untouched, listed in §17); S001 56/59: only `vidbyte/__init__.py` 434/436/581/588 F401 (untouched); S061, S017, S025, C011, C012: no touched-file finding |
| import order (S051) | `python -m ruff check <6 touched .py> --config lint/ruff.toml --select I001 --no-cache` | PASS | `All checks passed!` |
| comment width | added `#` lines in `vidbyte/*.py` since `0b5af348`, wider than 72 | PASS | none |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at eadefa3f… (vidbyte-sdk 0.2.1, 630 exports).` exit 0 |
| Semgrep | `semgrep scan --metrics=off --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (own venv, no PYTHONPATH) | PASS | `Ran 1 rule on 921 files: 0 findings.` exit 0 |
| full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `4679 passed, 13 skipped in 36.62s` · `CI passed.` exit 0 |
| full local gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` exit 0 |
| remote checks | `gh workflow run ci.yml` (run 38547530415) and `static-policy.yml` (run 38547533790) on `8d8ba811`; read through `gh api …/commits/8d8ba811…/check-runs` | PASS 4/4 | `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success` |

CI covered `8d8ba811`, which holds every code fix. The verify-log/report commit that follows is docs-only and was not dispatched.

## Open items
None: every gate is green, and no finding assigned to this iteration is open. Not mine and untouched: R-3, R-4, and R-7 are deferred follow-ups (R-3 → spec Q-9, R-7 → spec Q-10, both default No). R-1 and R-5 were fixed by the test author (05fbe43e). R-15 is refuted. The code map (`context/code-map.md:284`) still cites the old Teams intent name; this stage may not edit it, and it is a historical record.

If a later iteration has to touch R-8 again: the Jira header bytes are pinned by AC-34 and `WIRE_ROWS["jira_issue"]`, and the Confluence header by `test_output_connectors_new_destinations.py`. `OutputHttp.basic_authorization` must keep calling only `base64` (Style 1).

## Commands run (all with `timeout` and `</dev/null`; `GIT_TERMINAL_PROMPT=0 GIT_EDITOR=true`)
- `lint/run.py --rule A002|S001 --all --format json` before the fixes; A002, S061, S001, S017, S025, C011, and C012 `--all --format json` after them, filtered with `touched.py`
- `python probe_r6.py` before and after R-6
- pack after every fix; `-k "jira or confluence or first_batch or wire"` after R-8
- `lint/run.py --rule S009`, `--rule S001`, `--rule A001`, `--rule A002`, `--rule A009` after the relevant fixes; full `lint/run.py` at the end
- `ruff check … --config lint/ruff.toml --select I001 --no-cache` on the touched .py files
- `generate-sdk-public-api.py --check`; Semgrep; `run_ci.py --stage source` and `--stage package`
- `git push origin HEAD:feat/agent-output-connectors`; `git ls-remote`; `gh workflow run ci.yml` and `static-policy.yml`; `gh run list`; `gh run watch`; `gh api …/commits/<sha>/check-runs`
