LENS: conformance (final re-review)
VERDICT: SOUND — all 11 repaired findings hold and none regressed. The pack (664), the full suite (4679 passed, 13 skipped), lint (`SDK-LINT: PASS`), the contract, and I001 are green. Every one of the 65 tests the spec cites is collected and passes. What remains is three Minor docs and bookkeeping gaps, all docs-only and none changing behavior.

Reviewed at HEAD `7cab8990`. Its code matches `713657e1` and `8d8ba811`: `git diff 8d8ba811..7cab8990 -- . ':(exclude)docs'` is empty. Repair diff: `d5611f25..713657e1`, 18 files, +75/−28. Whole-batch diff: `336d6c78...713657e1`.

FIX CONFIRMATIONS:
R-1 — confirmed — `VMUT=media_once … -p vmut_plugin` → `1 failed, 663 passed` (killed by `…rendering.py::test_telegram_neutralization_changes_only_tag_starts_and_media_brackets[every-media-block-and-tag]`; was `660 passed`). Reviewer mutant `MUT=telegram_media_once` → `1 failed, 663 passed`. Control `VMUT=media_none` → `7 failed, 657 passed`. The new row also holds two `<`, so a mutant that replaces only the first tag start is killed as well.
R-5 — confirmed — `MUT=sticky_later_read_failure_ignored … -p mut_plugin` → `3 failed, 661 passed`. It is killed by `test_read_failure_on_a_later_page_is_that_reads_receipt_and_nothing_is_written[500|network|non-json]`, where the mutant returns `('github_issue','sent',<comment url>,None)`. Before the fix it gave `660 passed`.
R-2 — confirmed — `lint/run.py --rule A002 --all --format json` gives `found 577, baseline 703, IMPROVED` (was 579). Filtered to touched files, the remaining findings are `errors/base.py 166/299/314/323` and `transport.py 34 (_json_request_headers), 98 (_send_bounded), 124 (SyncHttpTransport.request)`, none of them a function this PR changed. `transport.py:57` `# @intent json-body-or-content-never-both` and `:81` `# @intent content-bytes-go-out-verbatim` are each 61 and 58 columns wide. `transport.py` line 1 is still `from __future__ import annotations`, so no A001 header was added (A001 643/643). The §17 bullet's line numbers match the JSON exactly.
R-6 — confirmed — `s5r1/probe_r6.py`: the unsigned and signed `MappingProxyType` payloads both return `SENT` with wire `{'text': 'Body text'}` (before the fix: `TypeError … mappingproxy is not JSON serializable`). My probe `s5rr/probe_fixes.py` adds three checks. A signed proxy payload gives `sig ok: True` over the wire bytes. A nested `object()` still raises `TypeError` on both paths (EC-19). A list still raises `TypeError payload must return a mapping, got list.` (EC-18). S009 is `350 350 RATCHETED`, and its only touched-file finding is `transport.py:235`, in untouched `SyncHttpTransport` code (base line 227, `for raw_line in response:`).
R-8 — confirmed — `OutputHttp.basic_authorization` (`delivery.py:111-114`) uses the same expression as the base `jira.py:77`. The probe compares the result with the base formula for a non-ASCII token: `helper == base expr: True`. It also reads the Jira and Confluence wire headers (`ok: True`), and both `repr` values are `…(credential='***')`. A runtime mutant that swaps username and password gives `10 failed, 654 passed`, failing on Jira and Confluence in the wire_contract, followup_acceptance AC-34, comments, new_destinations, configuration, and security tests. No same-class call chain: the helper calls only `base64`. `import base64` is gone from both connectors, and S001 has no new F401.
R-9 — confirmed — `README.md:148` and `:218` hold "Links in this section retrieved 2026-10-14." (see R-RR1 for the Footguns section, which R-9 did not cover).
R-10 — confirmed — `README.md` Discord row: "…and so does a `?thread_id=` URL with `forum=True`" (EC-4). Telegram row: "on a chat that is not a forum it fails `http_400`" (EC-10). Job-summary row: "pass only a file you own" (T-5).
R-11 — confirmed — `vidbyte/agents/README.md:252-255` now uses the `vidbyte/lib/README.md:42` category list. A009 is 0/0 CLEAN. The file is 22,296 bytes.
R-12 — confirmed — `s5rr/tests_fields.py`: all ten listed headers name the new covering files, and every named file exists. A grep confirms the named symbols are in those files: `OutputMethod` and `OutputResponses` in followup_contract, `OutputRead` in update_in_place and followup_contract, `TypefullyPlatform` in followup_contract, contract, and new_destinations.
R-13 — confirmed — README step 3 now says "private helpers that `send` calls (static, or async methods when they need the connector's settings, as in `github.py`)", which matches `github.py:78/86/93/114`. Cosmetic only: the rewrap left `README.md:231` at 94 columns. Ten other prose lines in that README are already wider than 80, and README wrapping is not a gate.
R-14 — confirmed — `git grep teams-text-is-plain` finds no hit in `vidbyte/` or `tests/`; the only hits are docs/spec history. `teams.py:48` reads `# @intent teams-text-cannot-mention`. No intent name is duplicated in `vidbyte/lib/outputs` or `vidbyte/lib/http`.
Q-9/Q-10 — confirmed recorded — spec §15 rows after Q-8, both `[scope-adding, S4]`, default **No**. Neither is built: `base.py` has no ASCII, whitespace, or `content-length` value check, and `github_job_summary.py:67` is `except OSError:` only.

WHAT THE IMPLEMENTATION GETS RIGHT
- The §4 snippet is copied verbatim into `test_output_connectors_followup_acceptance.py`; a line diff against spec §4 finds no missing line. The test asserts `capsys` output equal to the five literal §4 lines, and it passes (`11 passed`).
- The repairs are surgical. `git diff 05fbe43e..713657e1 -- tests/` is empty, and the R-1/R-5 test commit only adds rows and one test (no assertion removed). `lint/baseline.json`, `lint/`, and `pyproject.toml` are untouched, and the diff adds no `noqa`, `type: ignore`, or `nosemgrep`. Every added `vidbyte/` comment line is at most 72 columns.
- The budget holds exactly. The diff adds 7 new modules and 12 new `class` lines: 5 connectors, `OutputAdf`, `OutputResponses`, `GitHubRequests`, `GitHubResponses`, `OutputRead`, `OutputMethod`, and `TypefullyPlatform`. It adds 0 dependencies and 5 `OUTPUT_CREDENTIAL_ENV_VARS` entries. 34 non-test files changed: the 33 §12.3 rows plus the approved `vidbyte/agents/README.md`. `BaseAgent`, `dispatcher.py`, and `connector.py` are untouched (INV-15, INV-17).
- The scope matches the user's words. Q-1…Q-10 are not built, there is no OAuth, Typefully never sends `publish_at`, `plan_at`, or `share` (INV-7), and the PR stays a draft. Every in-scope §B 0–5 checkbox maps to built code, and all 65 test nodes the spec cites are collected and green.

FINDINGS
R-RR1 [Minor] [conformance: NFR-8] vidbyte/lib/outputs/README.md:242, :244, :248, :280 — The four vendor links this batch added to Footguns have no retrieval date.
  Evidence: `git show 336d6c78:vidbyte/lib/outputs/README.md | awk '/^## Footguns/{f=1} f' | grep "](http"` prints nothing, so base Footguns had no links. Now `:242` ([Power Automate auth]), `:244` ([Teams workflows]), `:248` ([channel email]), and `:280` ([project access tokens]) are links, and the section has no date line. The only date lines are `:103` (Provider Reference table), `:148` (Email-in), and `:218` (Webhook receivers).
  Failure: the batch's Teams-note and GitLab-token facts are vendor citations with no retrieval date, which NFR-8 forbids ("Every vendor fact in it is cited with an official URL and a retrieval date"). This is the same gap R-9 closed for the other two new sections.
  Smallest fix: one line, "Links in this section retrieved 2026-10-14.", at the end of the Footguns list, as R-9 did.
  Spec IDs: NFR-8, FR-1 (Teams note), §12.3 row 29

R-RR2 [Minor] [conformance: deviations] docs/spec/output-connector-followups/spec.md §17 — Two deviations made in the repair are not recorded in §17.
  Evidence: (a) R-8 added a public static method, `OutputHttp.basic_authorization`, at `delivery.py:111-114`. `OutputHttp` is exported from `vidbyte.lib.outputs` (`__init__.py:17,50`). But §8.5 lists only `post`, `patch`, `read`, and private `_write`, and D-2 says "`OutputHttp` gets the verbs `post` …, `patch`, and `read`". (b) R-11 edited `vidbyte/agents/README.md`, which is outside §12.3; §14 makes that an "Ask first" item. `grep -n "basic_authorization\|agents/README" spec.md` finds nothing. Both appear only in `pipeline.md:92` and `verify-log.md:22`, which are not the spec.
  Failure: someone who reads the spec against the diff finds an `OutputHttp` method that no §8.5 interface or §17 bullet explains, and an edited file that is not in §12.3. Both changes are justified (review R-8 and R-11, with orchestrator approval). Only the record is missing.
  Smallest fix: two §17 "Implementation deviations" bullets. One says `OutputHttp.basic_authorization(username, password) -> str` was added for Jira and Confluence (R-8, Style 5), with Jira's header bytes unchanged (AC-34). The other says `vidbyte/agents/README.md` "Output Connectors" sentence was updated with orchestrator approval (R-11).
  Spec IDs: §8.5, D-2, §12.3, §14, §17

R-RR3 [Minor] [conformance: NFR-2] vidbyte/lib/constants/outputs.py:1-326 — The constants module is 326 lines, over NFR-2's 300-line target, and the spec does not record it.
  Evidence: `git show 336d6c78:vidbyte/lib/constants/outputs.py | wc -l` → `160`; `git show d5611f25:… | wc -l` → `326`; at HEAD → `326`. NFR-2 (spec.md:477) says "Every module stays under 300 lines." No report and no §17 entry mentions the overrun (`grep -n 300` over spec.md, the reports, and review.md finds only NFR-2 itself). S4's review says "largest 243 lines", which reads NFR-2 as covering new modules only.
  Failure: none at runtime. The spec's own §12.3 row 3 requires every new literal to live in this file, and AGENTS.md Style 3's limit is "well below 1,000", so the file is within the repo rule. The spec's NFR, however, is not met as written.
  Smallest fix: one §17 bullet that reads NFR-2's 300-line cap as covering code modules, and notes that row 3 puts every new constant in `constants/outputs.py`, now 326 lines (AGENTS.md limit 1,000). Splitting the file would add an eighth file, which is over the §8.4 budget, so do not split it.
  Spec IDs: NFR-2, §8.4, §12.3 row 3

VERIFIED CLAIMS:
- The tests have not changed since `05fbe43e`: `git diff --stat 05fbe43e..713657e1 -- tests/` prints nothing — held.
- There are no baseline, lint, or pyproject edits: `git diff --stat 336d6c78...713657e1 -- lint/baseline.json lint/ pyproject.toml` prints nothing — held.
- The diff adds no suppression: grepping added lines for `noqa|type: ignore|nosemgrep|pragma: no cover` finds nothing — held.
- The code at `7cab8990` equals `8d8ba811`, the commit CI ran on: `git diff --stat 8d8ba811..7cab8990 -- . ':(exclude)docs'` prints nothing — held. I did not re-query the remote check runs, to avoid credentialed network calls; the 4/4 success comes from the orchestrator.
- `SDK-LINT: PASS`, with A002 577/703 IMPROVED, S009 350/350, S008 19/19, A001 643/643, A007 255/255, A006 34/34, S054 3/3, A009 0/0 — held.
- The seven NFR-6 rules show touched-file findings only in untouched code: A002 at `base.py 166/299/314/323` and `transport.py 34/98/124`; S001 F401 at `__init__.py 434/436/581/588`; none for S061, S017, S025, C011, or C012 — held, and this matches the §17 bullet exactly.
- `@intent` as the second line of a contiguous comment block (transport `:57`, `:81`) has precedent: 142 of 975 `# @intent` lines in `vidbyte/` follow another comment line (`s5rr/intent_prev.py`) — held, not a finding.
- The contract is current: `generate-sdk-public-api.py --check` → `current at eadefa3f… (vidbyte-sdk 0.2.1, 630 exports)` — held. `basic_authorization` does not touch the contract, because `OutputHttp` is not a root export.
- I001 is clean on every touched `vidbyte/*.py` file: `All checks passed!` — held.
- The full suite passes and changes no tracked file: `4679 passed, 13 skipped in 37.51s`, and `git status` shows only this report — held.
- The §4 snippet lines all appear in the acceptance test, and the printed block is exact — held.
- All 65 test nodes cited in spec §6.2 are collected (`664 tests collected`, 0 missing) — held.
- INV-4 constants: `OUTPUT_TIMEOUT_SECONDS = 10.0`, `OUTPUT_RATE_LIMIT_RETRIES = 2`, `OUTPUT_RETRY_STATUS_CODES = (429,)`, `OUTPUT_MAX_READ_BYTES = 16_000_000`. `read` and `_write` pass `follow_redirects=False` (`delivery.py:94,139`) — held.
- INV-16: the only non-stdlib, non-`vidbyte.lib` import in `vidbyte/lib/outputs/*.py` is `pydantic.BaseModel` (`webhook.py`) — held.
- INV-18 / INV-5 / INV-6: `telegram.py:63` replaces every `<` and every `![` (no count argument), `slack.py:55` neutralizes `<!` and `<@`, and `discord.py:56` always sends `allowed_mentions: {"parse": []}` — held.
- Q-1…Q-10 are not built, by grep for `owner`, `WEBHOOK_SECRET`, `sendMessage`, `markupSyntax`, `skip_entity`, deadline checks, `user`/`Bot`, value ASCII checks, and `except (OSError, ValueError)` — held.
- The 300-line NFR-2 target holds for every new module (max 249, `delivery.py`) but not for `constants/outputs.py` (326) — partly held, see R-RR3.
- Doc-header accuracy outside R-12: `jira.py:9` TESTS omits `test_output_connectors_rendering.py`, where Jira's ADF description is tested. R-12 did not list `jira.py`, and this is cosmetic, so it is not reported.

COMMANDS RUN:
- `git log --oneline -20`; `git status --short` → HEAD `7cab8990`; only this report is untracked.
- `git diff --stat|--name-status …` (repair, batch, tests, lint, docs-only) → as quoted above.
- `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors </dev/null` → `664 passed in 5.13s`.
- `VMUT=media_once|media_none PYTHONPATH="$W;<scratch>/s4v" python -m pytest … -p vmut_plugin …` → `1 failed, 663 passed` / `7 failed, 657 passed`.
- `MUT=sticky_later_read_failure_ignored|telegram_media_once PYTHONPATH="$W;<scratch>/mutplug" python -m pytest … -p mut_plugin …` → `3 failed, 661 passed` / `1 failed, 663 passed`.
- `R8MUT=swap PYTHONPATH="$W;<scratch>/s5rr" python -m pytest … -p r8_mut_plugin …` → `10 failed, 654 passed in 5.25s`.
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) python lint/run.py --rule <A002|S001|S061|S017|S025|C011|C012|S009|S008|A001|A007|A006> --all --format json` + `s5r1/touched.py` → as in VERIFIED CLAIMS.
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) python lint/run.py` → exit 0, `SDK-LINT: PASS`.
- `python <scratch>/s5r1/probe_r6.py` → `unsigned -> … SENT … {'text': 'Body text'}`, `signed -> … SENT …`.
- `python <scratch>/s5rr/probe_fixes.py` → `1 signed proxy: sent sig ok: True`; `2 nested non-JSON … -> TypeError` (both paths); `3 non-mapping -> TypeError`; `4 default envelope: {'agent','title','body','structured'} application/json`; `5 helper == base expr: True`; Jira and Confluence wire header `ok: True`, repr `credential='***'`.
- `python scripts/generate-sdk-public-api.py --check` → `current at eadefa3f…`, exit 0.
- `python -m ruff check <touched vidbyte .py> --config lint/ruff.toml --select I001 --no-cache` → `All checks passed!`.
- Added `vidbyte/*.py` comment lines wider than 72 columns in `d5611f25..713657e1` → none.
- `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider -x tests` → `4679 passed, 13 skipped in 37.51s`.
- `python -m pytest --collect-only tests/features/agent_output_connectors` + `s5rr/ac_nodes.py` → `664 tests collected`; `spec test refs: 65 missing: []`.
- `python -m pytest … test_output_connectors_followup_acceptance.py -v` → `11 passed in 0.19s`; `s5rr/snippet_cmp.py` → `spec snippet lines not found verbatim in test: []`.
- `python <scratch>/s5rr/tests_fields.py` → every TESTS field names existing files.
- `python <scratch>/intent_prev.py vidbyte` → `total @intent 975 preceded by another comment line 142`.
- `git grep -n teams-text-is-plain|teams-text-cannot-mention`; grep for Q-1…Q-10 markers; `wc -l` base/S3/now for the touched modules; `git show 336d6c78:vidbyte/lib/outputs/README.md | awk …Footguns… | grep "](http"` → empty.
