# Verification log: Output connector follow-ups on PR #882

Gate set (from context/code-map.md §1.3). Every gate runs locally except where a row says remote-only.
- Pack: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors`
- Lint: `PYTHONIOENCODING=utf-8 python lint/run.py` (`SDK-LINT: PASS`), plus the seven NFR-6 rules (A002, S061, S001, S017, S025, C011, C012) as `--rule <ID> --all --format json`, filtered to the files this change touches
- Import order (S051): `python -m ruff check <touched .py> --config lint/ruff.toml --select I001 --no-cache`
- Contract: `python scripts/generate-sdk-public-api.py --check`
- Semgrep: `semgrep scan --metrics=off --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (its own venv, no PYTHONPATH). Locally it is a manual run; in CI it runs only in `static-policy.yml`
- Full local gate: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH
- Remote-only: `ci.yml` (Source / Python 3.11, Source / Python 3.12, Package) and `static-policy.yml` (Static policy). Both are dispatch-only. Read the results by commit through the check-runs API, because `gh pr checks` stays empty for dispatched runs

## Iteration 1 — 2026-10-14 — agent report: reports/S5-repair-1.md
**Defects in:** R-2 (Major, code + docs) · R-6, R-8, R-9, R-10, R-11, R-12, R-13, R-14 (Minor) · spec §15 Q-9/Q-10 bookkeeping. No failing gate: every gate was green at `0b5af348`, so this iteration was findings-only.

**Hypotheses and attempts:**
- **R-2.** Reproduced with `lint/run.py --rule A002 --all --format json`: A002 579, with `transport.py:55` (`request`) and `:78` (`_send_once`) flagged. Hypothesis: one `# @intent` line above each comment the PR added, which sits at def+2 inside A002's def−4…def+20 window. It worked on the first try: A002 dropped to 577 (IMPROVED, no baseline edit), and the touched-file list lost exactly those two lines. Because the two inserted lines shift the rest of the file, the untouched transport findings moved from 34/96/122 to 34/98/124. The §17 bullet gives both sets of numbers, and I checked every number in the bullet against the final JSON. Per spec §11, I added no A001 header to `transport.py`.
- **R-6.** Reproduced with a scratch probe that sends a `MappingProxyType` payload through a patched `httpx.AsyncClient.send`. Before the fix, the unsigned and signed paths both raised `TypeError: Object of type mappingproxy is not JSON serializable`. Fix: `body = dict(body)` right after the mapping check. After the fix, both paths return `SENT`, and the wire JSON is `{'text': 'Body text'}`. S009 (mypy) stays at 350, because assigning to the declared `body: object` narrows it to `dict`. EC-18 (a non-mapping fails as `unexpected:TypeError`) and EC-19 (a non-JSON value inside fails as `unexpected:TypeError`) still hold, because only the top level is copied. One false start: the probe's first print read a `receipt.error` attribute that does not exist. That was a bug in the probe, not in the code. The probe was fixed and rerun.
- **R-8.** I weighed `OutputArguments` (it owns `credential()`) against `OutputHttp`. I chose `OutputHttp.basic_authorization(username, password) -> str`, the conventions reviewer's proposal. The header is built at send time, it is an HTTP-scheme concern, and `OutputArguments` only checks arguments at construction. I rejected building the header once in `__init__`: it would add a second attribute that carries the secret, and today the header is built per send. The helper calls only `base64`, so Style 1 holds. Jira and Confluence call it, and both had their now-unused `import base64` removed, so S001 shows no new F401. Jira's bytes are unchanged: the -k jira/confluence/wire subset gives `124 passed`, and the pack gives `664 passed`. The README `delivery.py` entry and the `delivery.py` header (COMMON MODIFICATION PATTERNS) name the helper. No class was added, so the budget is unchanged.
- **Side check (not a defect).** Plain `ruff check` with ruff's default config reports 4 findings in `transport.py` (UP012 ×3, PIE810), at lines 227–237. The same findings are at 225–235 in `0b5af348`. They are untouched code outside the repo's ruff selection (`lint/ruff.toml`), so I left them alone. Plain `ruff format --check` also says "would reformat" for the original copies of the touched files, and it is not a gate.
- **R-9.** I added "Links in this section retrieved 2026-10-14." after the Email-in table and after the Webhook receivers table. Each line covers the section's bullet links too.
- **R-10.** I added one clause each: the job-summary row gets "pass only a file you own" (T-5), the Discord row gets "`?thread_id=` with `forum=True` fails `http_400`" (EC-4), and the Telegram row gets "`topic_id=` on a chat that is not a forum fails `http_400`" (EC-10).
- **R-11.** In `vidbyte/agents/README.md`, the sentence now uses the category list from `vidbyte/lib/README.md:42`. The orchestrator approved editing this file outside §12.3. A009 is clean (22,296 characters).
- **R-12.** I chose each TESTS field from grep evidence of which new test files exercise the module. No new test imports `vidbyte.lib.constants.outputs`; their headers forbid it, because they write expected values out. So the constants header names the files that pin the follow-up caps, URLs, and patterns through those written-out wire values. A001 stays at 643/643.
- **R-13.** "private static helpers" became "private helpers … (static, or async methods when they need the connector's settings, as in `github.py`)". The first edit left a ragged wrap, so I rewrapped step 3 and amended my own unpushed commit before the push.
- **R-14.** The intent was renamed to `teams-text-cannot-mention`. `git grep` over `vidbyte` and `tests` finds no other reference. The code map, under docs/, still cites the old name; this stage may not edit that file.
- **Spec bookkeeping.** I added Q-9 (from R-3) and Q-10 (from R-7) after Q-8. Both are `[scope-adding, S4]`, non-blocking, and default to **No**. Neither was built.

**Changes:** a39cf95b (R-2) · 1e678c38 (R-6) · efb2c26b (R-8) · 47696121 (R-9) · 3bc709e3 (R-10) · bde205cd (R-11) · 3f5623ca (R-12) · 9fb29e3b (R-13) · a1405d71 (R-14) · 8d8ba811 (spec Q-9/Q-10) · this docs commit (verify-log, review.md statuses, S5 report)

**Gate matrix out:**
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

**Still open:** none from this iteration's list. R-3, R-4, and R-7 are deferred as follow-ups (orchestrator decision; R-3 → Q-9, R-7 → Q-10, both default No).

## Iteration 2 — 2026-10-14 — agent report: reports/S5-repair-2.md
**Defects in:** R-RR1, R-RR2, R-RR3, all Minor and docs-only, from the final re-review (reports/S5-rereview.md, verdict SOUND). No failing gate: every gate was green at `8d8ba811`, and no code changed after it.

**Hypotheses and attempts:**
- **R-RR1.** Fix: one "Links in this section retrieved 2026-10-14." line at the end of the Footguns list, in the R-9 style (47696121). One line covers the four links at :242, :244, :248, and :280. In the same commit I rewrapped the 94-column line R-13 left in step 3 of How To Add A Destination, without changing its words. A `grep` over `tests/` found no assertion on either phrase. Pack `664 passed`. The README is 32,180 characters. First try; no false starts.
- **R-RR2.** Added two §17 bullets: `OutputHttp.basic_authorization` (efb2c26b, R-8) and the approved `vidbyte/agents/README.md` edit (bde205cd, R-11). The bullet list opens with "none changes a public name or a tested behavior", so the first bullet says the helper adds a name and changes none, and that the contract is unaffected (`OutputHttp` is not a root export).
- **R-RR3.** Added one §17 bullet with the count from `wc -l`: 326 lines now, 160 at `336d6c78`. While checking it I found that the re-review's "max 249, `delivery.py`" names a modified module, not a new one. The largest new modules are `adf.py` and `github_api.py`, at 109 lines each. Of the touched modules, two others are over 300, both from before this batch: `vidbyte/__init__.py` (1,336 → 1,348, the six budgeted root exports) and `errors/base.py` (552, unchanged). The bullet records all of this. The file is not split (§8.4 budget of 7 new files).
- **review.md.** Added a "Final re-review (S5) Minors — 3" table. The existing tables are unchanged.

**Changes:** 44b71741 (R-RR1) · 42018c13 (R-RR2) · b1c32edd (R-RR3) · this docs commit (verify-log, review.md table, S5 report)

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (pack) | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` | PASS | `664 passed in 5.18s` (on `b1c32edd`) |
| lint | `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s)` · `S064 RATCHETED: 4 known finding(s)` · `SDK-LINT: PASS` (exit 0). A009 `0 0 CLEAN`; A002 `577 703 IMPROVED`; S009 `350 350 RATCHETED`. No baseline edited |
| full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `4679 passed, 13 skipped in 36.69s` · `CI passed.` exit 0 |
| full local gate, package | `python scripts/run_ci.py --stage package` | SKIPPED | docs-only; last run at 8d8ba811: green |
| NFR-6 seven rules, I001, Semgrep, contract | as in iteration 1 | SKIPPED | docs-only; last run at 8d8ba811: green. `git diff 7a12530d..b1c32edd --name-only -- vidbyte` → only `vidbyte/lib/outputs/README.md` |
| remote checks | `gh workflow run ci.yml` (run 38550257344) and `static-policy.yml` (run 38550260311) on `b1c32edd`; read through `gh api …/commits/b1c32edd…/check-runs` | PASS 4/4 | `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success` |

CI covered `b1c32edd`, the last commit that touches the README or the spec. This verify-log commit is docs-only and was not dispatched.

**Still open:** none. R-3, R-4, and R-7 remain deferred follow-ups (orchestrator decision; R-3 → Q-9, R-7 → Q-10, both default No).
