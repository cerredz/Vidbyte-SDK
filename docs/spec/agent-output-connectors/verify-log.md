# Verification log: Agent output connectors

Gate set (from context/code-map.md §1), in CI order:

- **feature pack** (local): `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`
- **lint** (local, also inside run_ci): `python lint/run.py`, ending `SDK-LINT: PASS`
- **run_ci source** (local): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
- **run_ci full** (local): `python scripts/run_ci.py` with PYTHONPATH unset (source and package stages)
- **public API contract** (local, C016): `python scripts/generate-sdk-public-api.py --check`
- **Semgrep** (local and remote, `static-policy.yml`): `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1 in its own venv)
- **remote ci.yml** (remote only, dispatch-only): Source 3.11, Source 3.12, Package
- **remote static-policy.yml** (remote only, dispatch-only)

## Iteration 1 — 2026-10-12 — agent report: reports/S5-repair-1.md

**Defects in:**
- Confirmed findings: R-1 (Blocker), R-2, R-3, R-4 (Major).
- Trivial Minors: R-6, R-7, R-8, R-9, R-10, R-11, R-12, R-15.
- Failing gate: the feature pack, `16 failed, 324 passed` at 78321115. Every failure is an S4 case for R-1, R-2, R-3, R-12, or R-15.
- Out of scope by orchestrator decision:
  - R-5 was already fixed in spec r6.
  - R-13 is [scope-adding]; it is recorded as Q-11 and not built.
  - R-14 is test-only; its tests are already added and pass.

**Step 0, catch up with main (orchestrator-directed):**
- Ran `git fetch origin`, then `git merge origin/main`, which brought in 25 commits since db3988ff.
- Git merged without conflicts. Three files overlap with this PR:
  - `vidbyte/agents/README.md` keeps both the CodingContext text and the Output Connectors section.
  - `vidbyte/agents/fork.py` keeps `outputs=()` with `# @intent forks-never-deliver` and #884's `ProviderModelRegistry.vidbyte_key_follows_provider` check in `_api_key`.
  - `vidbyte/lib/enums/__init__.py` keeps `CodingContextSection`, `TextModelMode`, `DeliveryStatus`, and `OutputDestination`.
- `contracts/sdk-public-api.json` did not conflict. `--check` reports it current at 623 exports, so it was not regenerated.
- Git wrote its default message, which was reworded on the unpushed commit to `chore(merge): catch up with origin/main [gate:mergeability]` (ba83c953, parents 9db8a702 and e6d42359).
- Results after the merge:
  - feature pack: `16 failed, 324 passed`, the same 16;
  - `SDK-LINT: PASS`;
  - `_generate_reply` still measures 10 / 9 / 50 (C901 / PLR0912 / PLR0915).
- Lint count shift that came from main: S009 is 350/350 at ba83c953. The S3 review recorded 349 before the merge. The S009 finding set at ba83c953 and at the final HEAD is identical (diffed with line numbers stripped), so no S009 finding comes from this iteration.

**Hypotheses and attempts (in order):**
- R-1. Hypothesis: httpx's own `HTTP Request:` INFO line carries the full URL, and nothing scopes or filters it.
  - Tried the spec r6 shape. Module `ContextVar` `_OUTPUT_POST_ACTIVE` ("vidbyte_output_post_active", default False). It is set just before `HttpTransport().request` and reset in a `finally` on the same `try` as the `ProviderRequestError` handler. `OutputHttp._keep_log_record` is added once, at import, with `logging.getLogger("httpx").addFilter`.
  - Worked first time: 6/6 security cases pass, and the caller's own request is still logged.
  - Not tried, and not to try: raising the httpx level, setting `disabled` or `propagate`, or `import httpx`. The test catches the first three, and the NFR-7 layering test catches the import.
- R-2. Hypothesis: a `runtime_checkable` Protocol checks attribute presence only, and `_deliver_one` never checks what `send` returned.
  - Added the destination `isinstance` check in `connectors()` (spec message, with no trailing period).
  - Added a `DeliveryReceipt` check after the `wait_for`, mirroring the render check.
  - Worked first time. `connectors` now measures 8 / 7 / 15 and `_deliver_one` 4 / 3 / 10.
- R-3. Hypothesis: on Python 3.11, `asyncio.run` joins the default executor (`asyncio.to_thread`) with no timeout.
  - Used a module-level `_SMTP_EXECUTOR = ThreadPoolExecutor()` with `loop.run_in_executor`. Worked first time; S006, S046, and S052 stay CLEAN.
  - Updated the `OutputSmtp.send` docstring and the lib README "Deadline" bullet. The bullet also says the interpreter still joins the thread at exit.
- R-4. Added `OUTPUT_EMAIL_ADDRESS_PATTERN` and `OUTPUT_HTTPS_PREFIX` in a new `# Validation` group, as spec row 2 places them.
  - `_is_address` and `OutputArguments.address` both `re.fullmatch` the pattern.
  - `_HTTPS` is removed. The https checks stay different (D-19 versus §9.1 and D-21).
  - `ruff --select I001 --fix` was needed on two PR-created files (`dataclasses/outputs.py`, `outputs/base.py`). C008 is unchanged at 45.
- R-12. Hypothesis: `smtplib.SMTP.__exit__` raises `SMTPResponseException` on a non-221 QUIT, inside the receipt-deciding `try`.
  - Replaced the `with` block with an inner `try` whose `finally` calls `client.quit()` under `contextlib.suppress(smtplib.SMTPException, OSError)`. Nesting depth stays 3 (S024 unchanged).
  - No extra `client.close()` was added. Real `quit()` closes the socket on every path, and an extra close would add a second "close" step in the fake.
  - The verifier's real-smtplib `v_e4_e5.py` now prints `QUIT=250 … receipt sent` and `QUIT=421 … receipt sent`.
- R-15. Hypothesis: neither `urlsplit` nor `.port` was guarded.
  - A bare `parts.port` statement is flagged by ruff B018, so the value is bound (`host, _port = parts.hostname, parts.port`) inside the `try`. `ValueError` becomes `ConfigurationError … from None`.
  - The message is now "must be an https:// URL with a host and a valid port". It is used for both failure paths and never echoes the value.
  - Not fixed, out of scope: verifier `v_blind_urls.py` still shows a URL with a `\x7f` control character passing construction and failing as `unexpected:InvalidURL`. That is the R-13 / Q-11 class (unprintable credential validation), [scope-adding], and not built.
- R-6. Moving `@intent jira-site-is-a-bare-atlassian-host` into `__init__` would leave `JiraIssueOutput.send` with no `@intent`, and A002 flags `send`.
  - So `send` got its own accurate block, `jira-issue-link-is-built-from-the-key`. It replaces the inline "Jira returns only the issue key" comment above the request.
  - `is_deliverable` got `only-accepted-answers-are-delivered` above its return. A002 has no findings in output files.
- R-8. The message comes from the shared `OutputArguments.text`, so it cannot change there.
  - `TelegramOutput.__init__` now uses an if / elif / else: an int passes, a str goes through `OutputArguments.text` (spec row 12), and anything else raises "chat_id must be an int or a non-blank string".
  - The receipt url error is deliberately not changed.
- R-7, R-9, R-10, and R-11 are wording or constants only. Each worked first time. R-11 uses the spec r6 caution sentence (AC-24, EC-42).

**Changes:**
- ba83c953 chore(merge): catch up with origin/main [gate:mergeability]
- 228c0fdc fix(outputs): keep credential URLs out of the httpx request log [R-1]
- b0b403f8 fix(outputs): reject a non-enum destination and a non-receipt send result [R-2]
- e6ae0fa2 fix(outputs): run SMTP on a dedicated executor so run() keeps the deadline [R-3]
- f73ae753 fix(outputs): give the email-address rule one owner in the constants [R-4]
- 50eb32c9 fix(outputs): decide the SMTP receipt before QUIT [R-12]
- fa4a67bb fix(outputs): map a malformed webhook URL port or host to ConfigurationError [R-15]
- 0cb2dbc8 fix(outputs): put each intent block above the rule it explains [R-6]
- e41c535f fix(outputs): name the Jira issue and browse paths as constants [R-9]
- 540b8501 fix(outputs): make the delivery and Jev module headers accurate [R-7]
- a432dcde fix(outputs): say an int or a non-blank string in the Telegram chat_id error [R-8]
- ad96036f docs(outputs): add a Non-Goals section to the agents/output README [R-10]
- a9230d46 docs(outputs): warn before resending a network failure [R-11]

Edits were limited to the following. None of them touches `vidbyte/agents/base.py`, `tests/`, `lint/baseline.json`, or CI config.
- Source: `delivery.py`, `dispatcher.py`, `email.py`, `base.py` (lib/outputs), `constants/outputs.py`, `dataclasses/outputs.py`, `jira.py`, `telegram.py`, and `connector.py`.
- Headers only: the two Jev files.
- Wording only: `errors/base.py` (`repair_approaches`).
- Docs: the two output READMEs.

**Gate matrix out** (code at a9230d46):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` | PASS | `340 passed in 2.14s` |
| lint | `python lint/run.py` | PASS | `A002 IMPROVED 703 -> 638` · `S051 IMPROVED 259 -> 258` · `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `3743 passed, 13 skipped in 41.21s` · `CI passed.` |
| run_ci full | `python scripts/run_ci.py` (PYTHONPATH unset) | PASS | `3743 passed, 13 skipped in 32.76s` · `No broken requirements found.` · `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).` |
| Semgrep | `semgrep --test …` · `semgrep scan --error …` | PASS | `1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.` (exit 0) |
| remote ci.yml | run 38211640430 on a9230d46 | PASS | success: Source / Python 3.11 (`3738 passed, 18 skipped in 36.26s` · `CI passed.`), Source / Python 3.12 (`CI passed.`), Package (`Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.`) |
| remote static-policy.yml | run 38211642693 on a9230d46 | PASS | success: Static policy (`1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.`) |

The remote runs ran on the code commit a9230d46. The docs-only commit that records this log is dispatched again afterwards; its run IDs and results are in the S5 STATUS block.

**Still open:** none of the findings handed to this iteration. R-5 (spec-only, done in r6), R-13 (Q-11, not built), and R-14 (tests already added) were not this iteration's.

## Iteration 1 addendum (polish) — 2026-10-12

**Defects in:** two trivial Minors from the final re-review (reports/S5-rereview.md, verdict SOUND).
- R-C2: `email.py:32` had one blank line before `class EmailOutput` (E302). The R-3 edit left it.
- R-C1: the R-8 `chat_id` check raises inline in `TelegramOutput.__init__`. That contradicts the §12.4 line "Connector constructors contain no `raise` themselves", and the spec did not record it as a deviation.

**Changes:**
- ad4ed50a style(outputs): restore two blank lines before EmailOutput [rereview R-C2]. `ruff check --no-cache --preview --select E302 vidbyte/lib/outputs/email.py` gives `All checks passed!`.
- 0ca19568 docs(spec): record the TelegramOutput chat_id deviation [rereview R-C1]. It adds one bullet to the §17 "Implementation deviations" list and changes no other spec line. The code is kept as it was.

**Gate matrix out** (at 0ca19568):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` | PASS | `340 passed in 2.93s` |
| lint | `python lint/run.py` | PASS | `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `3743 passed, 13 skipped in 38.70s` · `CI passed.` |
| remote ci.yml and static-policy.yml | dispatched on the commit that records this addendum | see the S5 STATUS reply | — |

**Still open:** none.

**Test tree check:** `git diff 7f3bb7ff..HEAD -- tests/` is not empty. It shows 38 files and +3929/−34 lines, all of which came in with the main catch-up merge. The output is byte-identical to `git diff db3988ff e6d42359 -- tests/` (main's own test changes). None of those files is under `tests/features/agent_output_connectors/`. Both `git diff 7f3bb7ff 9db8a702 -- tests/` (the branch before the merge) and `git diff ba83c953..HEAD -- tests/` (everything after the merge) are empty. So no test was edited by this pipeline.

## Iteration 2 — 2026-10-12 — agent report: reports/S5-repair-2.md

**Defects in:**
- S6-1 (Minor, from the S6 author): `EmailOutput(to=[])` or `to=()` raised a `ConfigurationError` naming the internal `recipients` field, not `to` (AC-20, INV-21).
- S6-2 (Minor, from the S6 author): the `OutputDeliveryError.repair_approaches` resend hint passed `failed`, which reads as `err.failed`, the receipts, to `OutputDispatcher.deliver`.
- Failing gate: the feature pack, `1 failed, 340 passed` at d87fcbaf. The failure is `[email-empty-to]`, the test author's red test for S6-1 (4b063c28).
- Mergeability: the PR was BEHIND origin/main by 8 commits.

**Step 0, catch up with main (orchestrator-directed):**
- Ran `git fetch origin`, then `git merge origin/main`, which brought in #890, #885, #889, #767, #888, #887, #746, and #763. Git merged without conflicts.
- The merge commit is d4100704 `chore(merge): catch up with origin/main [gate:mergeability]`, with parents d87fcbaf and ab7182d3.
- Overlapping files: `vidbyte/lib/enums/__init__.py` and `vidbyte/agents/README.md`. Both keep both sides. The contract did not conflict and is current at 623 exports.
- After the merge, the feature pack gave `1 failed, 340 passed` (the same red test).
- **#889 and #887 against INV-9.** Main changes which messages the end-of-run hooks see after a review STOP, and no stop reason changes.
  - A review-refused finish still reports `CONTRACT_UNSATISFIED` (`runtime.py:873-877`).
  - `AgentStopReason` is unchanged (its diff is empty).
  - So `OUTPUT_DELIVERABLE_STOP_REASONS = {final_response, is_done}` still matches the spec, and a review-stopped run is skipped.
- **#888 against the lowercase header-key deviation.** `_json_request_headers` adds `content-type` only when no spelling is present.
  - Slack and Google Chat pass a lowercase `content-type`, which is kept; the other connectors get the default once.
  - The `OutputRequest` lowercase-key check is unchanged.
- From main: `lint/baseline.json` C018 1 → 0 (#763). A002 now counts 639, against 638 at b18ac7d1, whose code equals d87fcbaf. This iteration's two fixes add no function that A002 inspects. A002 has no finding in this PR's output files; the 4 in `errors/base.py` are in other error classes (lines 166, 299, 314, 323). So the +1 came in with the merge. Which of main's files carries it was not isolated.

**Hypotheses and attempts (in order):**
- S6-1. Root cause: `OutputArguments.texts` accepts an empty sequence, so `()` reached `SmtpSettings`, whose `__post_init__` names its own field.
  - Rejected: make `texts` reject an empty sequence. GitHub's `labels=()` default goes through `texts`.
  - Rejected: an inline raise in `EmailOutput.__init__`. It breaks §12.4's "no `raise` in connector constructors" and would be a second deviation beside TelegramOutput's.
  - Rejected: a `minimum=` keyword on `texts`. It acts as a flag with one non-default caller, and it changes a §8.5 signature.
  - Chosen, and it worked first time: a new leaf `OutputArguments.non_empty(values, *, parameter)` wraps the `texts` result in `EmailOutput.__init__`. The message is "to must list at least one value." with `details={"parameter": "to"}`. `SmtpSettings` is unchanged and still rejects `recipients=()` when built directly.
  - Spec follow-up, not done here because the briefing limits my `docs/` writes: this is a ninth `OutputArguments` method beyond §8.5. §8.5, §12.3 row 13, and the §17 TelegramOutput bullet ("rather than adding a ninth `OutputArguments` method") each want one line.
- S6-2. Root cause: the hint's variable `failed` collides with the `err.failed` property.
  - The new single string gives the README and spec recipe, `failed_connectors = [c for c, r in zip(agent.outputs, err.receipts, strict=True) if r.status is DeliveryStatus.FAILED]`, then `await OutputDispatcher.deliver(failed_connectors, err.reply, {})`. It says outright that `err.failed` holds receipts, and keeps R-11's network caution.
  - **Failed first:** splitting the literal over two lines, as `errors/base.py:496-497` does, gives lint S062 (no-implicit-string-concatenation) **SDK-LINT: FAIL**. The diagnostic requires one literal on one line; `+` and `''.join()` do not work either. The `:496` precedent predates S062, so do not copy it.
  - Verified: `scratchpad/s5r2/verify_s6_2_hint.py` evaluates the two expressions taken from the live hint string and prints `selected: 1 of 2` and `resend receipts: [('webhook', 'sent')]`. Before the fix, the literal hint gave `[('webhook', 'unexpected:AttributeError')]`.

**Changes:**
- d4100704 chore(merge): catch up with origin/main [gate:mergeability]
- 5b437f24 fix(outputs): name the to parameter when EmailOutput gets no recipients [S6-1]
- 2334385b fix(outputs): give OutputDeliveryError the working resend recipe [S6-2]

Edits were limited to `vidbyte/lib/outputs/base.py`, `vidbyte/lib/outputs/email.py`, and `vidbyte/lib/errors/base.py`. Nothing under `tests/`, `lint/`, `.github/`, `.semgrep/`, or `vidbyte/agents/base.py` changed.

**Gate matrix out** (code at 2334385b):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` | PASS | `341 passed in 3.87s` |
| lint | `python lint/run.py` | PASS | `S025 IMPROVED 263 -> 261` · `S051 IMPROVED 259 -> 258` · `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `3824 passed, 13 skipped in 32.43s` · `CI passed.` |
| run_ci full | `python scripts/run_ci.py` (PYTHONPATH unset) | PASS | `3824 passed, 13 skipped in 33.12s` · `No broken requirements found.` · `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` (exit 0) |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).` |
| Semgrep | `semgrep --test …` · `semgrep scan --error …` (1.170.1, own venv) | PASS | `1/1: ✓ All tests passed` · `Ran 1 rule on 911 files: 0 findings.` (both exit 0) |
| remote ci.yml | run 38217488376 on 2334385b | PASS | success: Source / Python 3.11 (`3819 passed, 18 skipped in 41.70s` · `CI passed.`), Source / Python 3.12 (`3819 passed, 18 skipped, 19 warnings in 53.88s` · `CI passed.`), Package (`Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.`) |
| remote static-policy.yml | run 38217490653 on 2334385b | PASS | success: Static policy (`1/1: ✓ All tests passed` · `Ran 1 rule on 911 files: 0 findings.`) |

The full suite grew from 3743 to 3824 passing because of main's 8 commits. The remote runs ran on the code commit 2334385b. The docs-only commit that records this log is dispatched again afterwards, and its run IDs are in the S5 STATUS block.

**Test tree check:**
- `git diff d87fcbaf..HEAD -- tests/features/agent_output_connectors` is empty.
- `git diff d4100704..HEAD -- tests/` is empty.

**Still open:** none of S6-1 or S6-2. The spec §8.5, §12.3 row 13, and §17 line for `OutputArguments.non_empty` is a docs follow-up for the orchestrator.

## Iteration 3 — 2026-10-12 — agent report: reports/S5-repair-3.md

**Defects in:**
- RR2-C1 (Minor, conformance, from reports/S5-rereview-2.md R-C1): the `OutputDeliveryError` resend caution at `vidbyte/lib/errors/base.py:215` named only network failures. EC-5 (`http_502` after GitHub created the issue) and EC-24 (`smtp_recipients_refused` after one of two recipients got the email) may already be delivered, so following the hint can post twice.
- Failing gates: none. Every gate was green at 81f9cba0, and cc79a564 differs only in docs.
- Not this iteration's: RR2-C2 (pr-body.md) belongs to S6.

**Hypotheses and attempts (in order):**
- Checked for pinned wording first. `grep -rn "may already\|check its destination\|repair_approaches" tests/` finds only `test_output_connectors_dispatch.py:265` and `:273`, which assert that the field exists and is non-empty. No test pins the hint text or the README sentence, so no test blocks the fix.
- Hypothesis: the caution should name every receipt code that can follow a request the destination already stored. I derived the list from INV-11's code forms, the EC table, D-21, and the code that builds each code (`delivery.py:78-93`, `:156-167`; `dispatcher.py:96`), then checked each one with a probe.
  - Probe: `scratchpad/s5r3/probe_rr2_c1.py` (session scratchpad, not in the repo). It runs the real `OutputHttp.post` and `_send_once` through `httpx.MockTransport`, and the real `OutputSmtp.send` through a real smtplib client on an in-process `socket.socketpair()`. It makes no network call. Each case stores the content at the fake destination first, then fails.
  - Before the fix, it printed this: `http_502` stored 1, caution names it False; `invalid_response` stored 1, False; `network` stored 1, True; `smtp_error` stored 1, False; `smtp_recipients_refused` stored 1, False.
  - Two codes go beyond the reviewer's proposal:
    - `invalid_response` is returned only after a 2xx (`delivery.py:84-92`, D-21). For GitHub, Jira and Notion, a 2xx means the object was created even when the link cannot be read (probe: GitHub 201 with a truncated JSON body).
    - `smtp_error` covers an SMTP reply timeout. smtplib's `getreply` turns a read `OSError` into `SMTPServerDisconnected`. That class is an `SMTPException`, and `OutputSmtp.send` catches `SMTPException` before `OSError`, so a server that stores the body and then stalls past `OUTPUT_TIMEOUT_SECONDS` gives `smtp_error`, not `network`.
  - Left out, with the reason for each:
    - `http_4xx` and `smtp_<code>`: the destination refused the request (EC-1, EC-3, EC-23, EC-25, EC-31 to EC-33). EC-48 keeps the QUIT reply from changing the receipt.
    - `unexpected:<Type>`: from a built-in connector it is raised before any request is made (EC-16, EC-40, EC-49). From a caller-written connector, the caller owns the code.
    - `http_3xx`: EC-35 treats it as a refused redirect.
    - Flip condition: if a destination is found that answers 3xx or 4xx after storing a post, add that code.
- Wording: the reviewer's sentence used `http_5xx`, but no receipt carries that spelling. `_error_code` builds `http_<status>` or `http_<status>:<token>` (`delivery.py:99-103`), so the caution says "starts with http_5". A caller can test that with `str.startswith`.
  - The inverse wording, which names what is safe to resend, came out longer. It would also have had to rule on `http_3xx` and `unexpected:`.
  - Worked first time.
- The hint stays one literal on one line (S062). The zip recipe is byte-identical to S6-2's; only the clause after the last `;` changed.
- After the fix, the probe printed True for all five codes, and the feature pack gave `341 passed in 3.76s`.

**Changes:**
- 563efc51 fix(outputs): widen the resend caution to every failure that may already have landed [RR2-C1]
  - `vidbyte/lib/errors/base.py:215`: the caution is now "if a failed receipt's error_code is network, invalid_response, smtp_error, or smtp_recipients_refused, or starts with http_5, that output may already have been delivered, so check its destination first."
  - `vidbyte/agents/output/README.md:98-101`: the same list, with "(which includes a send that passed the deadline)" after `network`, because nothing near that paragraph says the deadline gives `network`.
  - `vidbyte/lib/outputs/README.md:144-148` (the Deadline bullet): the same list. The bullet's first sentence already says the deadline gives `network`.

Nothing under `tests/`, `lint/`, `.github/`, `.semgrep/`, `contracts/`, spec.md, pr-body.md, or `vidbyte/agents/base.py` changed.

**Gate matrix out** (code at 563efc51):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` | PASS | `341 passed in 3.76s` |
| lint | `python lint/run.py` | PASS | `S009 RATCHETED: 350 known finding(s).` · `S051 IMPROVED 259 -> 258` · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `3824 passed, 13 skipped in 32.31s` · `CI passed.` (exit 0) |
| run_ci full | `python scripts/run_ci.py` (PYTHONPATH unset) | PASS | `SDK-LINT: PASS` · `3824 passed, 13 skipped in 32.78s` · `No broken requirements found.` · `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` (exit 0) |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).` |
| Semgrep | `semgrep --test …` · `semgrep scan --error …` (1.170.1, own venv) | PASS | `1/1: ✓ All tests passed` · `Ran 1 rule on 911 files: 0 findings.` (both exit 0) |
| remote ci.yml | dispatched on the docs commit that records this entry | see the S5 STATUS block | — |
| remote static-policy.yml | dispatched on the docs commit that records this entry | see the S5 STATUS block | — |

Remote runs are dispatched once, after the docs push, so they cover the final SHA. The code they test is 563efc51's, because the docs commit changes only `docs/spec/`.

**Test tree check:**
- `git diff d87fcbaf..HEAD -- tests/features/agent_output_connectors docs/spec/agent-output-connectors/test-plan.md` is empty (0 lines).
- `git diff d4100704..HEAD -- tests/` is empty (0 lines).

**Still open:**
- RR2-C1 is fixed in code. The spec author aligns spec §9.2, AC-24 and EC-42 with the literal above (r8). That list now also has `invalid_response` and `smtp_error`.
- Spec text only, for the spec author: EC-46 says `EmailOutput(port=2465)` fails "giving FAILED `network`". The greeting wait goes through the same smtplib `getreply`. A probe gives `SMTPServerDisconnected | Connection unexpectedly closed: timed out | SMTPException: True | OSError: True`, and `OutputSmtp.send` catches `SMTPException` first, so the receipt is `smtp_error`. No code or README states the code for that case, so nothing else needs to change.
