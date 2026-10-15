# S4 · Findings verifier — report

Status: DONE. Produced `review.md`. No source edits, no commits, no state-changing git commands.
Scratch files (outside the worktree): `<scratch>/s4v/` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/ece663b4-5090-422c-ad68-c3b2451a23f6/scratchpad/s4v/`. They hold `a002.json`, `s001.json`, `touched.txt`, `a002_base.py`, `probe_surfaces.py`, `vmut_plugin.py`, and `pack.txt`.

## Inputs read
- All three reviews in full: S4-review-conformance.md, S4-review-conventions.md, S4-review-engineering.md.
- spec.md r3: §6 (INV, AC, EC), §7 (FR, NFR), §8.5, §9.2(b) row :826, §9.3–§11, §12.3 rows 1–17, §12.4, §12.5, §14, §17.
- request.md §C, test-plan.md (coverage rows, §13 exception), and S1-spec-review.md R-4.
- S3-implementer.md :40-50 and :150-191.
- AGENTS.md, field guide `init.md` and `comment-format.md`, house-style.md, and the review.md format in report-formats.md.
- Diff `git diff 336d6c78...d5611f25 -- . ':(exclude)docs/spec/output-connector-followups'`: 48 files, +4076/−266. `git diff 1f1bb12a d5611f25 -- vidbyte tests` is empty, so the code under review equals HEAD.

## Baseline evidence (my own runs)
- Pack: `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors </dev/null`
  ```
  ............                                                             [100%]
  660 passed in 5.14s
  exit=0
  ```
- GitHub CI on `d5611f25`, read with `gh api repos/cerredz/Vidbyte-SDK/commits/d5611f25…/check-runs`:
  ```
  Package             completed  success  …/runs/38540755703/job/115775562426
  Static policy       completed  success  …/runs/38540758273/job/115774629578
  Source / Python 3.12 completed success  …/runs/38540755703/job/115774618276
  Source / Python 3.11 completed success  …/runs/38540755703/job/115774618099
  ```
  No CI check fails, so there is no `[verifier]` CI finding.

## Merge map (original IDs → merged IDs)
| Original | Lens | Proposed | Merged ID | Disposition |
|---|---|---|---|---|
| R-E2 | engineering | Major | R-1 | CONFIRMED Major (tests) |
| R-C1 | conformance | Major | R-2 | CONFIRMED Major, narrowed to the two changed functions plus a §17 line (code + docs). The untouched-code half is refuted as a fix target. |
| R-E1 | engineering | Major | R-3 | DOWNGRADED to Minor `[scope-adding]`; the secret-leak claim is refuted |
| R-V1 | conventions | Major | R-4 | DOWNGRADED to Minor (tests) |
| R-E3 | engineering | Minor | R-5 | Minor, passed through (verified by rerun) |
| R-E4 | engineering | Minor | R-6 | Minor, passed through |
| R-E5 | engineering | Minor | R-7 | Minor, passed through, tagged `[scope-adding]` |
| R-V2 | conventions | Minor | R-8 | Minor, passed through |
| R-C3 (dates part) + R-V7 | conformance + conventions | Minor | R-9 | Merged: same root cause (Email-in and Webhook-receivers sections have no retrieval date) |
| R-C3 (T-5, EC-4, EC-10 part) | conformance | Minor | R-10 | Split from R-C3: a different failure (missing doc controls) |
| R-V3 | conventions | Minor | R-11 | Minor; the file is outside §12.3, so it needs approval |
| R-V4 | conventions | Minor | R-12 | Minor |
| R-V5 | conventions | Minor | R-13 | Minor |
| R-V6 | conventions | Minor | R-14 | Minor |
| R-C2 | conformance | Minor | R-15 | REFUTED (accept as recorded) |

Totals: 15 original findings became 15 merged IDs (R-C3 split in two, R-C3 dates merged with R-V7). 2 are confirmed Majors, 12 are Minors (2 of them downgraded from Major), and 1 is refuted.

## Verifications

### R-1 (R-E2): INV-18 "every `![`" is not pinned. CONFIRMED Major.
- The code is correct today. `vidbyte/lib/outputs/telegram.py:62`: `text = OutputText.chat_text(content).replace(TELEGRAM_TAG_PREFIX, TELEGRAM_TAG_REPLACEMENT).replace(TELEGRAM_MEDIA_PREFIX, TELEGRAM_MEDIA_REPLACEMENT)` has no count argument.
- Reading the tests: `HOSTILE_BODY` (`rendering.py:201`) holds one `![`. The rows at `:229-238` each hold at most one `![` (`"!![x](…)"` contains the substring `![` once). The `<` neutralization is already exercised with more than one `<` (`comparisons` row `"if a < b and x <= y"`, `heredoc` row `"cat <<EOF"`).
- My own mutation run (`<scratch>/s4v/vmut_plugin.py`, a runtime monkeypatch of `TelegramOutput.send` in `pytest_configure`; it edits no worktree file):
  ```
  -- VMUT=media_none     (control: drop the "![" replacement)
  FAILED …test_telegram_sends_rich_markdown_with_no_html_tag_and_no_media_block[no-topic]
  FAILED …[channel-username]
  FAILED …test_telegram_neutralization_changes_only_tag_starts_and_media_brackets[reference-image]
  FAILED …[custom-emoji]
  FAILED …[double-bang]
  6 failed, 654 passed in 5.22s
  -- VMUT=media_once     (replace only the first "![")
  660 passed in 5.11s
  ```
  The control shows that the patch reaches the pack's `output_api` fixture. The reviewer's plugin `MUT=telegram_media_once` also gave `660 passed in 5.08s`, and its sanity test gave `1 passed`.
- Spec check: INV-18 says "every `[` … directly after a `!` becomes `［`". test-plan.md row AC-5/INV-18 claims this risk is covered. T-2(c) is the attack path.
- Severity: kept at Major. This is a security invariant with an explicit "every", and its regression guard has a hole a one-character refactor (`, 1`) slips through. The fix is one parametrize row. Owner is `tests`, so it goes to the S2 test author; the repair agent cannot edit tests.

### R-2 (R-C1): A002 on `transport.py:55/78`. CONFIRMED Major, narrowed.
- My run: `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) timeout 900 python lint/run.py --rule A002 --all --format json </dev/null` gives exit 0, `A002 579 703 IMPROVED`. Filtered to the 30 touched `vidbyte/` files:
  ```
  vidbyte/lib/errors/base.py 166 __init__ retries
  vidbyte/lib/errors/base.py 299 __init__ external boundaries
  vidbyte/lib/errors/base.py 314 __init__ external boundaries
  vidbyte/lib/errors/base.py 323 __init__ external boundaries
  vidbyte/lib/http/transport.py 34 _json_request_headers external boundaries
  vidbyte/lib/http/transport.py 55 request external boundaries, retries
  vidbyte/lib/http/transport.py 78 _send_once external boundaries
  vidbyte/lib/http/transport.py 96 _send_bounded external boundaries
  vidbyte/lib/http/transport.py 122 request external boundaries, retries
  ```
- Base comparison with no checkout. `<scratch>/s4v/a002_base.py` runs `lint.rules.a002_intent_comments.IntentAnalyzer` on `git show <rev>:<path>`:
  ```
  336d6c78 vidbyte/lib/http/transport.py [(34, '_json_request_headers'), (55, 'request'), (74, '_send_once'), (90, '_send_bounded'), (116, 'request')]
  336d6c78 vidbyte/lib/errors/base.py [(166, '__init__'), (299, '__init__'), (314, '__init__'), (323, '__init__')]
  d5611f25 vidbyte/lib/http/transport.py [(34, '_json_request_headers'), (55, 'request'), (78, '_send_once'), (96, '_send_bounded'), (122, 'request')]
  d5611f25 vidbyte/lib/errors/base.py [(166, '__init__'), (299, '__init__'), (314, '__init__'), (323, '__init__')]
  ```
  The PR added no finding. `request` and `_send_once` were already flagged at base. The conventions reviewer's "predate the PR" is correct about the findings, and the conformance reviewer's "functions this PR changed" is correct about the code.
- The hunks (`git diff 336d6c78...d5611f25 -- vidbyte/lib/http/transport.py`) sit only in `request` (signature, the new `if json_body is not None and content is not None: raise ProviderRequestError("Pass json_body or content, not both.")` with its two-line why-comment) and `_send_once` (signature, the `body = content` path with its two-line why-comment). Both new comments explain why a rule exists, which is what `@intent` is for, but neither carries the marker.
- S001: `lint/run.py --rule S001 --all --format json` gives `S001 56 59 IMPROVED`. Touched-file findings are only `vidbyte/__init__.py` 434 (`ContinualTraceAgentDescriptor,`), 436, 581 (`FunctionTool,`), and 588 (`ToolMixin,`), all F401. The `__init__.py` hunks are 20, 267, 273-274, 276, 288-289, 1001, 1007-1008, 1010, and 1022-1023, so all four findings are untouched.
- `errors/base.py`: the only hunk is :215, inside `class OutputDeliveryError` (line 184). The flagged `__init__`s belong to `AllModelsFailedError` (163), `ProviderRequestError` (296), `ProviderConfigurationError` (311), and `ProviderResponseError` (320), all untouched.
- The spec's wording, quoted:
  - NFR-6: "in addition, `python lint/run.py --rule <ID> --all` for each of those seven must show no finding in any file this change touches".
  - §12.4 last box: "shows no finding in any file this change creates or modifies".
  - §12.4 A002 box: "Every function whose name, body names, or attributes hold a policy token … has a `# @intent <name>` comment within def−4…def+20".
  - §17 r3 S3 row: "the seven NFR-6 rule checks … pass".
  - S3 report :157-160 disclosed the narrower reading: "no finding in a touched file that was not already there". §17 does not mention it.
- See Adjudication A for the reading. Result: the two changed functions should carry `@intent` markers (the code part), and §17 should state the reading and list the untouched-code findings left alone (the docs part).
- Severity: kept at Major. NFR-6 is P0, the box is explicit, it exists because of accepted review finding R-4, and the record claims the box passes. Any reviewer who reruns the box gets 9 + 4 findings against a record of 0. The fix is the smallest possible: two comment lines and one §17 bullet.

### R-3 (R-E1): header values and credentials. DOWNGRADED to Minor `[scope-adding]`.
My probe `<scratch>/s4v/probe_surfaces.py` uses MockTransport for the encoding cases, and for the h11 cases a loopback socket on 127.0.0.1 behind a URL-rewriting `httpx.AsyncHTTPTransport`, so the request runs through real httpcore and h11. No outside network. It checks `str(err)`, `repr(err)`, `err.details`, the receipts, `logger.exception` output, `traceback.format_exception`, `str(cause)`, and `repr(cause)`:
```
== MockTransport (httpx header encoding runs before any transport) ==
webhook headers= NBSP value (new): RAISED OutputDeliveryError [('failed', 'unexpected:UnicodeEncodeError')] cause=UnicodeEncodeError
   secret visible in: {'repr(cause)': True}
github token= U+2011 (first-batch connector, first-batch args): RAISED OutputDeliveryError [('failed', 'unexpected:UnicodeEncodeError')] cause=UnicodeEncodeError
   secret visible in: {'repr(cause)': True}
gitlab token= U+2011 (new connector): RAISED OutputDeliveryError [('failed', 'unexpected:UnicodeEncodeError')] cause=UnicodeEncodeError
   secret visible in: {'repr(cause)': True}
== Loopback through real httpcore/h11 ==
webhook headers= trailing space: RAISED OutputDeliveryError [('failed', 'network')] cause=NoneType
   secret visible in: nowhere
webhook headers= content-length override: RAISED OutputDeliveryError [('failed', 'unexpected:LocalProtocolError')] cause=LocalProtocolError
   secret visible in: nowhere
webhook headers= plain good value (control): RECEIPTS [('sent', None)]
github token= trailing space (credential() strips): RAISED OutputDeliveryError [('failed', 'invalid_response')] cause=NoneType
   secret visible in: nowhere
```
(The last case reached the server: `invalid_response` only because the loopback answers `ok`, which is not JSON.)

- **Secret on the exception chain: refuted as an INV-3/T-1 breach.** INV-3 lists these surfaces: `repr()` of a connector or record, an exception message or `details`, a receipt, and an httpx `HTTP Request:` log line. The secret appears only in `repr(err.__cause__)`, the repr of httpx's own `UnicodeEncodeError`. It does not appear in the message, details, receipts, a logged exception, or a printed traceback. The identical exposure exists for the first-batch `GitHubIssueOutput` token. That path runs through `OutputArguments.credential` (unchanged: `git diff` shows no hunk in it, and base `credential` at :36-42 is identical) and the dispatcher's `raise OutputDeliveryError(…) from first_exception` (`dispatcher.py:80`), which INV-15 freezes. This PR did not introduce it.
- **Credential leading or trailing whitespace: refuted.** `credential()` returns `candidate.strip()` (base.py:50-51), and the probe's GitHub token with a trailing space reached the server.
- **Construction-time value check: real behavior, but not a spec defect.** spec.md:826 (§9.2(b), Webhook `headers`) says "Each value is a str with no CR, LF, or NUL", and AC-10 and EC-16 say the same. `base.py:170` implements exactly `any(mark in text for mark in "\r\n\x00")`. INV-11's "every invalid argument" points at those rules. The proposed stricter grammar is a new control, so under the no-scope-additions rule (memory, pipeline rule 11) it becomes an optional Q-n. The failure is loud (every send FAILED), and the `content-length` path's unwrapped `h11.LocalProtocolError` in `HttpTransport.request` predates this PR for any caller.

### R-4 (R-V1): 133 test comment lines over 72 columns. DOWNGRADED to Minor.
- My count of added lines over 72 columns that start with `#`: `vidbyte/` 0, `tests/` 133. This matches the reviewer.
- Field-guide scope. `comment-format.md` says "When: Writing or editing any `#` comment in SDK code" and "Evidence: … Not a lint rule: 4,325 of 5,965 existing comment lines are wider". My count at its commit `f7a02bae`: `vidbyte` total=5968 wide=4320 and `tests` total=2009 wide=1487. The entry's numbers are the `vidbyte/` package's, so "SDK code" means the package. Today: `tests` total=3166 wide=2306 (73% wide), so the test folder's existing style is wide comments.
- The spec's §12.4 box "Comment blocks are at most 72 columns" cites `comment-format.md` as its source, so it covers the same scope. §14 "Always" binds S3, the implementer, who wrote no tests.
- So this is not a field-guide or AGENTS.md violation, and nothing behaves differently. It stays Minor, owner `tests`, follow-up.

### R-5 (R-E3): verified by rerun
`MUT=sticky_later_read_failure_ignored PYTHONPATH="$WT;<scratch>/mutplug" python -m pytest -q -p no:cacheprovider -p mut_plugin tests/features/agent_output_connectors` gives `660 passed in 5.05s`. Sanity: `1 passed`. It stays Minor as proposed. The regression would create a duplicate marked comment, not a security failure, and the current loop checks `read.failure` the same way on every page.

### Minors passed through (R-6…R-14)
I spot-checked each, and the evidence held:
- `confluence.py:68` and `jira.py:77` hold the identical Basic header line.
- The `README.md` sections at :123 and :179 have no date. The only date line is :102. Nothing in the README contains "own" in the T-5 sense.
- The TESTS fields read as R-V4 says. For example, `github.py: TESTS: …wire_contract.py and test_output_connectors_update_in_place.py`, which omits `comments.py`.
- README :220-222 says "private static helpers", while `github.py:79/86/93/114` defines `async def _…(self, …)`.
- `teams.py:48` holds `# @intent teams-text-is-plain`. Besides the docs, `git grep` finds that name only in `context/code-map.md:284` and the review.
- `vidbyte/agents/README.md:252-253` reads "Slack, email, an issue tracker, Notion, or any HTTPS webhook".

R-6 and R-7 were not re-probed. They are Minors and pass through as written.

### R-15 (R-C2): `TELEGRAM_TEXT_MAX_CHARS`. REFUTED.
- `git grep TELEGRAM_TEXT_MAX_CHARS 336d6c78 -- . ':(exclude)docs'` finds `constants/outputs.py:81`, `:159` (`__all__`), and `telegram.py:16`, `:51`. The only consumer was the old `sendMessage` path.
- `scripts/generate-sdk-public-api.py` header: the contract is written "from vidbyte/__init__.py `__all__`". The name was never in it, and conformance confirmed that.
- The first-batch spec row 2 (agent-output-connectors/spec.md:1086) says "`__all__` lists all of them. Do not add this module to `vidbyte/lib/constants/__init__.py`." The module is an internal constants module, so its `__all__` is a convention, not part of the SDK's public surface.
- FR-34: no first-batch name may "change meaning". A kept `TELEGRAM_TEXT_MAX_CHARS = 4_096` would no longer describe Telegram's cap, which the approved FR-8/D-8 raised to 32,768. §17 :1491 records the removal. Accept it as recorded.

## Adjudications
**A. NFR-6 wording and A002 on `transport.py:55/78` (R-C1 vs conventions).** Both reviewers have half of it. The findings predate the PR (verified above), so conventions is right that the PR added none. But the PR changed both functions and added policy logic to them, so conformance is right that the code this PR wrote lacks the marker. NFR-6 says "any file this change touches", and §12.4 says "creates or modifies". Read literally, they would require fixing the A002 `__init__`s in `errors/base.py` and the F401s in `vidbyte/__init__.py`, which this PR never touched. AGENTS.md says "Do not rewrite untouched code just to make it conform; that belongs in its own pull request", and house-style says the repo wins over the spec. The box came from S1 R-4, which names its target as "a new `send` or `_signed_headers` without `@intent`", meaning new code. Ruling: the box means no finding in code this change creates or modifies. Under that reading, `request` and `_send_once` fail, because AGENTS.md says the principles "apply to new code and to code you change", and §12.4's A002 box covers them. The 7 untouched-code findings pass and need only a §17 record. The briefing asked whether the S3 "every box holds" claim stands. It does not stand as worded in §17, and the §17 bullet corrects it. The historical S3 report needs no edit, because it disclosed its reading at :157-160.

**B. R-V1, the field-guide scope.** Decided by the numbers. The entry's comment counts are the `vidbyte/` package's (4,320/5,968 at `f7a02bae` against the entry's 4,325/5,965), so "SDK code" means the package. Minor, owner `tests`.

**C. R-C2, restore or accept.** Accept, for the reasons above. INV-14 protects public names. The repo defines public as the contract (root `__all__`), and this module was explicitly kept out of the package exports.

**D. R-E1, required or scope-adding.** Scope-adding. The spec defines the value rule, and the code matches it to the character. The security half fails on evidence: the secret reaches no INV-3 surface, and `repr(__cause__)` behaves the same as first-batch credentials.

**E. R-E2, owner.** `tests`, so route it to the S2 test author. R-5 (R-E3) and R-4 (R-V1) are in the same lane and can share one dispatch.

## Blind-spot check (step 6)
- **Changing `_send_once`'s signature could break fakes in other repos.** `request` now always passes `content=` to `_send_once`, and the first batch names `_send_once` as the test seam, so a fake without `**kwargs` would raise TypeError. `git grep _send_once` in `vidbyte`, `vidbyte-cli`, and `vidbyte-sdk` (main checkouts): the backend fake `backend/tests/features/research_harness_platform/test_research_search_client_retry.py:46` is `scripted_send_once(transport, client, **kwargs)`; vidbyte-cli has none; every SDK fake (`scripts/test-async-http-transport.py`, `tests/features/coding_agent/conftest.py`, `tests/test_web_operation_client_retry.py`) runs in the full suite, which CI passed on `d5611f25`. No finding.
- **Fix interactions checked.**
  - R-2's comment-only fix must not add an A001 header to `transport.py` (spec §11). It also must not touch `_json_request_headers`, whose `@intent` sits at def−5, just outside the window. That finding is untouched and predates the PR.
  - R-8's shared Basic helper must keep Jira's header byte-identical. INV-2 requires it, and AC-34's `test_first_batch_connectors_keep_their_headers_and_send_no_raw_bytes` and `WIRE_ROWS["jira_issue"]` guard it.
  - The README edits (R-9, R-10, R-13) sit under AC-35's doc tests in `test_output_connectors_followup_contract.py`, and the README must stay at most 40,000 characters (31,755 now).
- No `[verifier]` finding was added.

## Commands run (all with `timeout` and `</dev/null`; `GIT_TERMINAL_PROMPT=0 GIT_EDITOR=true`)
- `git log --oneline -5`, `git diff --stat 336d6c78...d5611f25 -- . ':(exclude)docs/spec/output-connector-followups'`, `git diff 1f1bb12a d5611f25 --stat -- vidbyte tests` (empty)
- `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` → `660 passed in 5.14s`
- `gh api repos/cerredz/Vidbyte-SDK/commits/d5611f25…/check-runs --jq …` → 4 × `success`
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) timeout 900 python lint/run.py --rule A002 --all --format json` → `A002 579 703 IMPROVED` (filtered list above)
- `… --rule S001 --all --format json` → `S001 56 59 IMPROVED` (filtered list above)
- `python <scratch>/s4v/a002_base.py <wt> vidbyte/lib/http/transport.py vidbyte/lib/errors/base.py` → base/head lists above
- `git diff -U0 336d6c78...d5611f25 -- vidbyte/__init__.py vidbyte/lib/errors/base.py | grep '^@@'` → hunks listed above
- `PYTHONPATH=$(pwd) python <scratch>/s4v/probe_surfaces.py` → output above
- `VMUT=media_none|media_once PYTHONPATH="$WT;<scratch>/s4v" python -m pytest … -p vmut_plugin tests/features/agent_output_connectors` → `6 failed, 654 passed` / `660 passed`
- `MUT=telegram_media_once|sticky_later_read_failure_ignored PYTHONPATH="$WT;<scratch>/mutplug" python -m pytest … -p mut_plugin …` → `660 passed in 5.08s` / `660 passed in 5.05s`; sanity `1 passed` each
- Comment-width counts over `git ls-files` and `git show f7a02bae:*` (numbers above). Added-line counts: `vidbyte` 0, `tests` 133.
- `git grep -n TELEGRAM_TEXT_MAX_CHARS 336d6c78 -- . ':(exclude)docs'`; `git grep -n _send_once -- '*.py'` in `vidbyte`, `vidbyte-cli`, and `vidbyte-sdk`
- Read-only greps of README.md, the TESTS headers, teams.py, jira.py, confluence.py, github.py, and agents/README.md
