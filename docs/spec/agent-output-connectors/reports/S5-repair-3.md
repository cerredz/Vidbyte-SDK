# S5 repair, iteration 3 of 8: agent-output-connectors

**Branch:** feat/agent-output-connectors
**PR:** https://github.com/cerredz/Vidbyte-SDK/pull/882 (draft; not marked ready, not merged)
**Start HEAD:** cc79a564. Its code equals 81f9cba0's, because every later commit is docs only.
**Code HEAD:** 563efc51

## Outcome

- RR2-C1 is fixed with a wording change only.
  - The `OutputDeliveryError` resend caution, and the matching sentence in both output READMEs, now name every receipt code that can follow a request the destination already stored.
  - No control, field, method, or code path was added.
- The local gates are green: feature pack, SDK lint, run_ci source, run_ci full, contract, and Semgrep.
- Remote ci.yml and static-policy.yml are dispatched once, after the docs push. Their run IDs and conclusions are in the S5 STATUS block, because this report is part of the commit those runs test.
- No test, test-plan, spec, pr-body, baseline, or config file changed.

## RR2-C1: the resend caution named only network failures

**The finding.** reports/S5-rereview-2.md R-C1, lines 30–46.
- The hint at `vidbyte/lib/errors/base.py:215` ended: "a failed network output may already have posted, so check its destination first."
- EC-5 (GitHub answers 502 after creating the issue) and EC-24 (SMTP accepts one of two recipients) are also failures where the content may already be at the destination.
- request.md §C: "Timeouts and 5xx are reported as failures, not retried (the first post may have landed)."
- The reviewer's probe followed the hint after an EC-5 502 and got two GitHub issues.

**Pinned wording check (before any edit).** No test blocks the fix.
- `grep -rn "may already\|check its destination\|already have posted\|repair_approaches" tests/` finds only `test_output_connectors_dispatch.py:265` (the field list) and `:273` (`assert err.likely_causes and err.repair_approaches`).
- No test pins the hint text or either README sentence.

**Deriving the list.** I read every code form in INV-11, the EC table, D-21, and the code that builds each code:
- `delivery.py:78-93` for HTTP;
- `delivery.py:156-167` for SMTP;
- `dispatcher.py:96` for the deadline.

I then checked each candidate with a probe that stores the content at the fake destination first and then fails.

| Code | Can it follow a stored post? | Source |
|---|---|---|
| `network` | Yes: a read timeout (EC-4), an oversize body (EC-34), or the deadline (EC-47; email may still arrive) | already in the caution |
| `http_<5xx>[:token]` | Yes: EC-5 | reviewer |
| `smtp_recipients_refused` | Yes: EC-24, when some recipients got it | reviewer |
| `invalid_response` | Yes. It is returned only after a 2xx (`delivery.py:84-92`, D-21). For GitHub, Jira, and Notion, a 2xx means the object exists even if the link cannot be read. | new in this iteration |
| `smtp_error` | Yes. smtplib's `getreply` turns a read `OSError` (timeout or reset) into `SMTPServerDisconnected`. That class is an `SMTPException`, which `OutputSmtp.send` catches before `OSError`. A server that stores the body and then stalls past `OUTPUT_TIMEOUT_SECONDS` before its 250 gives `smtp_error`, not `network`. | new in this iteration |
| `http_4xx`, `smtp_<code>` | No: the destination refused (EC-1, EC-3, EC-23, EC-25, EC-31 to EC-33). EC-48 keeps QUIT out of the receipt. | left out |
| `unexpected:<Type>` | No for built-in connectors: raised before any request (EC-16, EC-40, EC-49). A caller-written connector is the caller's own code. | left out |
| `http_3xx` | EC-35 treats it as a refused redirect. | left out |

Flip condition: if a destination is found that answers 3xx or 4xx after storing a post, add that code.

**Probe.** `<session scratchpad>/s5r3/probe_rr2_c1.py`, kept outside the repo. It makes no network call.
- HTTP runs through the real `GitHubIssueOutput.send`, `OutputHttp.post`, and `HttpTransport._send_once` with `httpx.MockTransport`.
- SMTP runs through the real `OutputSmtp.send` with a real `smtplib.SMTP` on an in-process `socket.socketpair()`, on port 465 so that STARTTLS is skipped.
- It reads the caution from a live `OutputDeliveryError(...).repair_approaches[2]`.

Before the fix (at 81f9cba0's code):

```
caution: a failed network output may already have posted, so check its destination first.
github 502                                 -> http_502                   stored at destination: 1  caution names it: False
github 201-no-link                         -> invalid_response           stored at destination: 1  caution names it: False
github read-timeout                        -> network                    stored at destination: 1  caution names it: True
email body stored then reply timed out     -> smtp_error                 stored at destination: 1  caution names it: False
email 1 of 2 recipients refused            -> smtp_recipients_refused    stored at destination: 1  caution names it: False
```

After the fix (563efc51):

```
caution: if a failed receipt's error_code is network, invalid_response, smtp_error, or smtp_recipients_refused, or starts with http_5, that output may already have been delivered, so check its destination first.
github 502                                 -> http_502                   stored at destination: 1  caution names it: True
github 201-no-link                         -> invalid_response           stored at destination: 1  caution names it: True
github read-timeout                        -> network                    stored at destination: 1  caution names it: True
email body stored then reply timed out     -> smtp_error                 stored at destination: 1  caution names it: True
email 1 of 2 recipients refused            -> smtp_recipients_refused    stored at destination: 1  caution names it: True
```

**Wording choices.**
- **`starts with http_5`, not `http_5xx`.** No receipt carries the spelling `http_5xx`. `_error_code` builds `http_<status>` or `http_<status>:<token>` (`delivery.py:99-103`), so "starts with http_5" is exact, and a caller can test it with `str.startswith`.
- **Condition before the advice.** "if a failed receipt's error_code is …, that output may already have been delivered" names the field the caller actually reads (`error_code`). The old wording said "a failed network output", but outputs have no code; receipts do.
- **The inverse ("only X is safe to resend") was rejected.** It came out longer, and it would have had to rule on `http_3xx` and `unexpected:`.
- **One literal on one line (S062).** The zip recipe before the last `;` is byte-identical to S6-2's.

**Final hint literal** (for spec r8; `vidbyte/lib/errors/base.py:215`):

```
Resend only the failed connectors, not err.failed (those are receipts): failed_connectors = [c for c, r in zip(agent.outputs, err.receipts, strict=True) if r.status is DeliveryStatus.FAILED], then await OutputDispatcher.deliver(failed_connectors, err.reply, {}); if a failed receipt's error_code is network, invalid_response, smtp_error, or smtp_recipients_refused, or starts with http_5, that output may already have been delivered, so check its destination first.
```

**README sentences.**
- `vidbyte/agents/output/README.md:98-101`: "If a FAILED receipt's `error_code` is `network` (which includes a send that passed the deadline), `invalid_response`, `smtp_error`, or `smtp_recipients_refused`, or starts with `http_5`, that output may already have been delivered, so check its destination before resending it." The bracketed note stays, because nothing near that paragraph says the deadline gives `network`.
- `vidbyte/lib/outputs/README.md:144-148` (the Deadline bullet): the same sentence without the bracketed note. The bullet's first sentence already says the deadline gives `network`.
- `## Notes for agents` was not touched in either README.

**Commit:** 563efc51 `fix(outputs): widen the resend caution to every failure that may already have landed [RR2-C1]`. It touches `vidbyte/lib/errors/base.py`, `vidbyte/agents/output/README.md`, and `vidbyte/lib/outputs/README.md`.

## Gate matrix (code at 563efc51)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` | PASS | `341 passed in 3.76s` |
| lint | `python lint/run.py` | PASS | `S062 RATCHETED: 889 known finding(s).` · `S063 RATCHETED: 4 known finding(s).` · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS (exit 0) | `tests\test_workflow_agent_forks.py ......  [100%]` · `3824 passed, 13 skipped in 32.31s` · `CI passed.` |
| run_ci full | `python scripts/run_ci.py`, PYTHONPATH unset (`env \| grep -c ^PYTHONPATH=` gave 0) | PASS (exit 0) | `No broken requirements found.` · `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.`; the source stage in the same run gave `SDK-LINT: PASS` and `3824 passed, 13 skipped in 32.78s` |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 839e8e33a369743d0643463137f05a6b5eb39282 (vidbyte-sdk 0.2.1, 623 exports).` |
| Semgrep test | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` (1.170.1) | PASS (exit 0) | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| Semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (1.170.1) | PASS (exit 0) | `Ran 1 rule on 911 files: 0 findings.` |
| remote ci.yml | dispatched after the docs push | see the STATUS block | — |
| remote static-policy.yml | dispatched after the docs push | see the STATUS block | — |

Lint ratchet lines from the same run:
- `S009 staged-mypy-contracts 350 350 RATCHETED`;
- `S051 … 258 259 IMPROVED`;
- `A002 … 639 703 IMPROVED`.

Every other listed rule is IMPROVED or RATCHETED, and none regressed. No `--update-baseline` was run, and `lint/baseline.json` is unchanged.

**Test tree check:**
- `git diff d87fcbaf..HEAD -- tests/features/agent_output_connectors docs/spec/agent-output-connectors/test-plan.md | wc -l` gives 0.
- `git diff d4100704..HEAD -- tests/ | wc -l` gives 0.

## Test changes proposed

None.

## Findings I believe are wrong

None. R-C1 holds, and it was wider than reported: `invalid_response` and `smtp_error` can also follow a stored post.

## Open items and next hypotheses

- **Spec r8 (spec author).**
  - Align §9.2, AC-24, and EC-42 with the final literal above. The list now also has `invalid_response` and `smtp_error`.
  - §12.3 row 25's `repair_approaches` paraphrase (from S6-2) says "the network caution" and needs the same change.
- **EC-46 is inaccurate (spec text only).** It says `EmailOutput(port=2465)` fails "giving FAILED `network`".
  - The greeting wait goes through the same smtplib `getreply`. The offline probe gives `SMTPServerDisconnected | Connection unexpectedly closed: timed out | SMTPException: True | OSError: True`.
  - `OutputSmtp.send` catches `SMTPException` before `OSError`, so the receipt is `smtp_error`.
  - No README or code comment states a code for that case, so only the spec row needs a fix.
  - `delivery.py:163`'s comment "Unknown host, refused connection, timeout, bad cert." is still accurate, because a connect timeout from `socket.create_connection` is a plain `OSError`.
- **RR2-C2 (pr-body.md)** belongs to S6.
  - The PR body should also say the resend caution now covers these five codes.

**Watch out:** in Git Bash, `semgrep --test … > /dev/null` exits 2 on this machine even though the tests pass. Without the redirect, or with output sent to a file, it exits 0. Read Semgrep's exit code from an unredirected run, or from one redirected to a file.
