LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every FR/AC/INV I checked and the §4 snippet and §5 call path hold, but the NFR-6 per-rule lint box does not hold as the spec words it and as S3 reports it (A002 still flags two transport functions this PR changed), and the README misses one T-5 control and retrieval dates on two new sections.

WHAT THE IMPLEMENTATION GETS RIGHT
- §4 is reproduced verbatim in the follow-up acceptance test, which checks exactly the five printed lines (AC-1). The §5 diagram matches the real call path. The feature pack passes 660/660.
- INV-1 (reads first, then exactly one write, no POST fallback after a failed PATCH/PUT) and INV-8 (exact-bytes signing, headers built once and reused across 429 retries, D-4 signing headers set after caller headers) hold on every path I traced. `read()` passes GET, OUTPUT_MAX_READ_BYTES, retries 429 only, and follows no redirects. `_write` passes `idempotency_key=uuid4().hex`.
- Construction rules raise ConfigurationError naming the parameter and never echo a secret or a bad header name. Probes covered AC-3/6/10/14/20/32 and EC-13/14/15/16/27/41: Discord tags without forum, Telegram `topic_id=True/0`, GitHub key length and charset, Linear/Jira/Notion exclusive targets, GitLab host and project shapes, Typefully platforms, Webhook header CRLF/duplicate/bad-name, `whsec_` length and base64, Confluence space id. Do not loosen any of them.
- The budget is met exactly: 33 non-test files = §12.3 rows 1–33, 7 new modules (max 243 lines), 12 new classes, 5 env vars, 6 root exports, 0 dependencies. `lint/baseline.json` and `pyproject.toml` are untouched, the contract `--check` is current, and the first-batch test edits match the §13 list (3d974a1f snapshots `opened` before `read_text`, which is not a weakening).

FINDINGS
R-C1 [Major] [boundaries] vidbyte/lib/http/transport.py:55 and :78 — NFR-6's per-rule A002 check is not clean on functions this PR changed, though S3 and the r3 history say it is
  Evidence: `python lint/run.py --rule A002 --all --format json`, filtered to files this diff touches, returns transport.py:55 `HttpTransport.request` and :78 `HttpTransport._send_once`. These are the two functions the diff edits (hunks `@@ -55 +55`, `-56,0 +57,4`, `-74 +78`, `-75,0 +80,2`, which add `content: bytes | None = None` and the "Pass json_body or content, not both." refusal). Base 336d6c78 has no `@intent` on either. The same check also flags untouched code in touched files: errors/base.py 166/299/314/323 (`__init__` of classes the diff does not touch; the only hunk is :215) and S001 F401 at vidbyte/__init__.py 434/436/581/588 (the added imports are 267–289). Spec §12.4 says: "`python lint/run.py --rule <ID> --all` for A002, … shows no finding in any file this change creates or modifies." S3 report :44 says "§12.4: every box holds", and spec §17 r3 says "the seven NFR-6 rule checks … pass".
  Failure: A reviewer or the merge routine reruns the NFR-6 box and gets 9 findings in touched files where the record says 0. A002 has ratchet room (579/703), so `SDK-LINT: PASS` hides this, which is exactly the risk accepted r1 R-4 was written to close.
  Smallest fix: Add a `# @intent <name>` block to `HttpTransport.request` and `_send_once`, the code this PR changed. A002 drops to 577, IMPROVED, with no baseline edit. Then add one §17 line saying the other 7 findings are in untouched `__init__`s and pre-existing re-export imports, left alone under AGENTS.md "Do not rewrite untouched code", and correct the S3 "every box holds" claim.
  Spec IDs: NFR-6, §12.4 (last lint box), accepted R-4

R-C2 [Minor] [deviation] vidbyte/lib/constants/outputs.py (removed `TELEGRAM_TEXT_MAX_CHARS = 4_096` and its `__all__` entry) — an exported first-batch constant was deleted without being asked for
  Evidence: the diff shows `-TELEGRAM_TEXT_MAX_CHARS = 4_096` and `-    "TELEGRAM_TEXT_MAX_CHARS",`. Spec §17 :1491: "Row 11 removed the now-dead `TELEGRAM_TEXT_MAX_CHARS` constant". §17 :1489 heads that list "none changes a public name". It is not in contracts/sdk-public-api.json, and no consumer exists in vidbyte-repos besides the old first-batch worktree.
  Failure: Code that imports `vidbyte.lib.constants.outputs.TELEGRAM_TEXT_MAX_CHARS` (a name in that module's `__all__`) gets ImportError. INV-14/FR-34 promise first-batch public names "keep working unchanged". §14 lists changing a public name under "Ask first". No lint rule flags an unused constant, so removing it was not repo-forced.
  Smallest fix: Restore the constant and its `__all__` entry, or have the orchestrator record that the owner approves the removal and reword §17 :1489.
  Spec IDs: INV-14, FR-34, §14 Ask first

R-C3 [Minor] [docs] vidbyte/lib/outputs/README.md:123 and :179 — the new Email-in and Webhook receivers sections cite vendor docs with no retrieval date, and the T-5 "pass only a file you own" control is missing
  Evidence: `grep -n "Retrieved" README.md` finds only :83 (table header) and :102 ("Retrieved 2026-10-11; rows changed by the follow-ups retrieved 2026-10-14."), which cover the Provider Reference table only. `## Email-in` (:123) and `## Webhook receivers` (:179) state vendor facts (address locations, the Apps Script redirect to `script.googleusercontent.com`) with no date. T-5 (spec :890) requires the README text "pass only a file you own". The job-summary row (:92) does not have it, and grep for "own" finds no such phrase. EC-4 and EC-10 name "README row" as their guard, but the Discord row (:86) does not say that `?thread_id=` plus `forum=True` fails `http_400`, and the Telegram row (:89) does not say that `topic_id` on a non-forum chat fails `http_400`.
  Failure: NFR-8 ("Every vendor fact … cited with an official URL and a retrieval date") and the T-5/EC-4/EC-10 doc controls are unmet. A developer can point `path=` at a shared file, or set both thread and forum, without the documented warning.
  Smallest fix: Add "Retrieved 2026-10-14." under each of the two sections, add "Pass only a file you own." to row :92, and add one clause each to rows :86 and :89 naming the `http_400` case.
  Spec IDs: NFR-8, T-5, EC-4, EC-10, §12.3 row 29

VERIFIED CLAIMS:
- All 33 §12.3 rows built, phase order, commit messages cite FR/AC/W IDs: HELD.
- §4 snippet verbatim and prints the five lines (AC-1); §5 call path: HELD.
- INV-1, INV-2 byte identity for first-batch args (GitHub, Linear, Jira plain, Notion, Discord, Webhook, Google Chat), INV-3/5/6/7/8/9/10/11/12/13/16/17/18: HELD.
- INV-14: constructors keyword-only, new kwargs defaulted, `team_id`/`project`/`parent_page_id` optional with exclusive(required=True), CLI #166 usages still valid, root `OutputDispatcher` intact: HELD, except R-C2.
- AC-1…AC-36 behaviors: HELD (probes plus pack). ADF AC-8 order, loose list → one orderedList, `* * *` → paragraph: HELD.
- All 65 `file::test` proofs cited in spec §6.2 exist: HELD.
- D-2 (OutputResponses not re-exported from lib.outputs), D-4, D-5 (no env var for secret), D-12, D-16, D-17, D-18, D-24 (Google Chat untouched), row 6 ContextVar rename `_OUTPUT_SEND_ACTIVE`: HELD.
- GitHub body cap: 70k input plus forged marker → 65,536 chars, ends with own marker, forged `<!-- vidbyte:x` stripped: HELD.
- Job summary on a directory → FAILED `file_error`: HELD.
- S3 reported deviations (raw-line paragraphs so `- ` gives text `"- "`; empty fence between list items keeps one list; read ignores body; inline literals; Discord inline ConfigurationError; issue title single-lined; signing_key strips whitespace; extra @intent blocks; `body: object`; I001 wraps): each is necessary, minimal, and recorded in §17. ACCEPTED.
- No unreported deviation, no §C decision reversed, no Q-1…Q-8 built: HELD.
- No baseline raise, no new suppression, `_generate_reply` unchanged: HELD.
- "the seven NFR-6 rule checks pass" (S3 :44, §17 r3): NOT HELD for A002 and S001 in touched files (R-C1). S061/S017/S025/C011/C012 clean: HELD.
- README ≤ 40,000 chars (31,755), no leftover "eleven": HELD. Retrieval dates on every vendor fact: NOT HELD (R-C3).

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` → `660 passed in 4.99s`
- `PYTHONIOENCODING=utf-8 python lint/run.py` → `S061 IMPROVED 6 -> 5 …` / `SDK-LINT: PASS` (exit 0)
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at eadefa3f… (vidbyte-sdk 0.2.1, 630 exports).`
- `python lint/run.py --rule {A002,S061,S001,S017,S025,C011,C012,S008} --all --format json`, filtered to touched `vidbyte/` files (scratchpad s4c/touched.py) → A002: 9 (transport.py 34, 55, 78, 96, 122; errors/base.py 166, 299, 314, 323); S001: 4 (vidbyte/__init__.py 434, 436, 581, 588); all others 0
- `git diff -U0 336d6c78...d5611f25 -- vidbyte/lib/http/transport.py | grep ^@@` → hunks at 55–67 and 78–87 only (`request`, `_send_once`)
- `git diff -U0 336d6c78...d5611f25 -- vidbyte/lib/errors/base.py vidbyte/__init__.py | grep ^@@` → base.py :215 only; __init__.py 20, 267–289, 1001–1022
- `git show 336d6c78:vidbyte/lib/http/transport.py | grep -n @intent` → no intent on `request`/`_send_once` at base
- `git diff 336d6c78...d5611f25 -- lint/baseline.json pyproject.toml | wc -l` → `0`
- `git diff 336d6c78...d5611f25 -- contracts/ | grep TELEGRAM` → no match (constant never in contract)
- `grep -n "Retrieved" vidbyte/lib/outputs/README.md` → :83, :102 only
- `python s4c/probe1.py` (no network) → every construction probe `[ok-err]` naming the parameter; no `[NO-ERROR]` or `[WRONG-TYPE]`; values as listed under VERIFIED CLAIMS
- `git status --short` → only untracked S4 report files
