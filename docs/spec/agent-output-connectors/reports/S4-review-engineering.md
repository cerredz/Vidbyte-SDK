LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the retry, cancellation, error-code, and test-pack work is solid, but the feature leaks secret webhook URLs and Telegram bot tokens into ordinary INFO logs, and with email outputs the sync `run()` path is not bounded by the delivery deadline.

Reviewed: `git diff origin/main...9463c348`. The worktree HEAD (0b9bc19e) differs only in `docs/spec/.../pipeline.md`, so every path:line below is the same at both commits.

WHAT THE IMPLEMENTATION GETS RIGHT (keep these as they are)
- **Retry policy (INV-10).** `OutputHttp.post` (`vidbyte/lib/outputs/delivery.py:55-66`) passes `retry_status_codes=(429,)` and `retry_count=2`. `HttpTransport.request` (`vidbyte/lib/http/transport.py:47-56`) retries only a status in that tuple. A `ProviderRequestError` from `_send_once` (network error or read timeout) is re-raised at once, never retried. Mutation M24 (drop `retry_status_codes`) fails 7 tests. Redirects and the size ceiling are tested against the real `_send_once` through `httpx.MockTransport`, not the fake.
- **Cancellation and the failure path (INV-7, INV-20).**
  - `deliver` re-raises any non-`Exception` result of `gather` (`dispatcher.py:65-67`).
  - `_deliver_outputs` (`base.py:948-958`) clears the claimed queue, notifies the session, and re-raises.
  - `FailureRouter.capture_exception` deduplicates by exception identity (`sessions/failure/router.py:378-384`). So `Session.run` plus `_deliver_outputs` record the error once (AC-23 holds).
- **Error codes stay clean (INV-11).**
  - `_error_code` keeps the body only when the whole stripped body fully matches the token pattern.
  - `ProviderRequestError` is turned into a `network` receipt inside its `except` and never chained. Its `response_excerpt`, which can hold the URL, therefore never reaches `__cause__`.
  - Skip, deadline, and unexpected-exception paths all yield receipts in configured order.
- **A strong test pack.** Of 14 single-point mutations run against this implementation, 9 were caught:
  - M4: `_deliver_outputs` no longer notifies the session.
  - M5: `_deliver_outputs` no longer clears the queue.
  - M7: the https check on the link is removed.
  - M11: STARTTLS runs without a context.
  - M13: sends run one after another.
  - M20: the delivery error is swallowed.
  - M22: delivery runs before the schema check.
  - M23: `&` is no longer escaped for Slack.
  - M24: the default retry status codes are used.

  The deadline is read from the module global at call time (`dispatcher.py:92`), so the deadline test is meaningful. The riskiest wiring test (`test_delivery_failure_drops_the_runs_queued_follow_ups_instead_of_running_them_later`) fails for the right reason when the queue clear is removed (M5: 2 failures).

FINDINGS (ranked, most severe first)

R-E1 [Blocker] [security] vidbyte/lib/outputs/delivery.py:55 — Every HTTP delivery writes its URL to the `httpx` INFO log, and for 5 of the 11 connectors that URL is the credential
  Evidence:
  - httpx 0.28.1 `AsyncClient._send_single_request` logs every request: `logger.info('HTTP Request: %s %s "%s %d %s"', request.method, request.url, ...)`.
  - `OutputHttp.post` sends through it (`delivery.py:55`). Slack, Discord, Teams, Google Chat, and Webhook use the secret URL as `request.url`. Telegram builds `f"{TELEGRAM_API_URL}/bot{self._bot_token}/sendMessage"` (`telegram.py:45`).
  - Repro (offline, `httpx.MockTransport`, `logging.basicConfig(level=logging.INFO)`): scratchpad `exp/httpx_log_leak.py` printed
    `INFO:httpx:HTTP Request: POST https://hooks.slack.com/services/T000/B000/S3CRETslack "HTTP/1.1 200 OK"`
    `INFO:httpx:HTTP Request: POST https://api.telegram.org/bot123456:S3CRETtelegram/sendMessage "HTTP/1.1 200 OK"`
    `secret in log: True`
  - Nothing in `vidbyte/` filters or silences the `httpx` logger (grep for `getLogger("httpx")` finds nothing).
  Failure: an app that configures INFO logging (a common `logging.basicConfig(level=logging.INFO)`, or any log shipper) runs an agent with `SlackOutput()`. Every finished reply writes the full webhook URL to the log. The same happens with the Discord, Teams, and generic-webhook URLs, the Google Chat `key`/`token` query, and the Telegram bot token. Anyone who can read the logs can then post to the channel. Model-provider calls are not affected, because their keys travel in headers.
  Test gap: the security scan (`test_output_connectors_security.py:51-78`) never turns on logging. The test plan maps EC-41 to the AC-7 test only (`test-plan.md:84`), and that test checks receipts and the error, not logs.
  Smallest fix:
  - In `delivery.py`, set a module `ContextVar[bool]` for the duration of `OutputHttp.post`.
  - Register `logging.getLogger("httpx").addFilter(...)`, a static method on `OutputHttp`, so no new class is needed. It returns `False` for `HTTP Request:` records while that flag is set; redacting `record.args[1]` to scheme and host also works.
  - Add a test that runs every URL-secret connector under `caplog.set_level(logging.INFO, logger="httpx")` and asserts `SECRET_MARKER not in caplog.text`.
  Spec IDs: EC-41 ("Never logged"), INV-4 ("A resolved credential appears only in the request that goes to its own destination"), T-1, T-3, request.md §C ("Never logged").

R-E2 [Major] [failure-modes] vidbyte/lib/outputs/email.py:65 — The delivery deadline does not bound `agent.run()` / `Session.run()` for `EmailOutput`, because `asyncio.run` waits for the SMTP worker thread to finish
  Evidence:
  - `EmailOutput.send` runs `await asyncio.to_thread(OutputSmtp.send, ...)` on the loop's default executor.
  - `BaseAgent.run` is `asyncio.run(self._run_releasing_mcp(...))` (`base.py:1025`). `Session.run` has the same shape.
  - On Python 3.11, the repo's floor and this environment, `Runner.close()` runs `loop.run_until_complete(loop.shutdown_default_executor())` with no timeout (`inspect.signature(...) == (self)`).
  - Repro: scratchpad `exp/smtp_deadline.py`. A fake `smtplib.SMTP` takes 3 s in `send_message`, and `dispatcher.OUTPUT_DELIVERY_DEADLINE_SECONDS` is set to 0.2. Output:
    `receipts: [('failed', 'network')]`
    `agent.run returned after 3.02s (deadline 0.2s)`
    `events: [('connect', 0.0), ('sent', 3.0)]`
  Failure: an SMTP server that answers each command just inside the 10 s socket timeout, or trickles bytes (T-5, the stall that EC-47 names), plus `agent.run(...)`. The receipt is FAILED `network` at 35 s. But `run()` does not return or raise until the worker thread ends. That is unbounded on 3.11 against a trickling server, and up to 300 s on 3.12 and later. NFR-2 promises "the hard bound is `OUTPUT_DELIVERY_DEADLINE_SECONDS` (35 s)", and EC-47 promises "A failure within the deadline". `arun()` keeps the bound, but the §4 snippet uses `run()`. EC-19/EC-47 accept that the thread keeps running; they do not accept that the caller waits for it. The test plan treats only the thread as accepted (`test-plan.md:112`), and the deadline test (AC-6 e) covers HTTP on the async path only.
  Smallest fix: run `OutputSmtp.send` somewhere `asyncio.run` does not join, for example `loop.run_in_executor(_SMTP_EXECUTOR, ...)` on a module-level executor, or a daemon thread that resolves a loop future through `call_soon_threadsafe`. Add a sync-`run()` timing test for email. If the team prefers not to change code, at least correct NFR-2, EC-47, and the README "Deadline" bullet to say that `run()` waits for the SMTP thread.
  Spec IDs: NFR-2, EC-47, T-5, D-6.

R-E3 [Minor] [error-handling] vidbyte/agents/output/README.md:66-80 — The documented recovery recipe resends every FAILED connector, including `network` ones that may already have been delivered
  Evidence:
  - The README recipe filters only on `if receipt.status is DeliveryStatus.FAILED` (line 77) and says "resend only the failed ones".
  - `OutputDeliveryError.repair_approaches` says the same: "Resend only the failed outputs with OutputDispatcher.deliver(failed, err.reply, {})." (`vidbyte/lib/errors/base.py:215`).
  - The spec itself says a `network` receipt can be a delivered post. EC-4: "A failure that may still have posted once." EC-47: a deadline-cancelled request, or an SMTP thread that keeps running.
  - R-E2's repro shows that by the time sync `run()` raises, the "FAILED network" email has already been sent.
  Failure: a Slack read timeout, or an email that passes the deadline, gives FAILED `network`. The caller follows the documented recipe, and the channel or inbox gets the reply twice. That is the double post the 429-only retry policy exists to prevent.
  Smallest fix: wording only, in the README Failure Behavior section, the `lib/outputs` README Deadline bullet, and `repair_approaches`. Say that a `network` receipt may already have been delivered, and check the destination before resending. Optionally, have the example skip `error_code == "network"`.
  Spec IDs: EC-4, EC-42, EC-47, AC-24, INV-10 (intent).

R-E4 [Minor] [error-handling] vidbyte/lib/outputs/delivery.py:122-130 — A mail the server accepted is reported FAILED when the server's QUIT reply is not 221
  Evidence:
  - `send_message` runs inside `with OutputSmtp._client(settings) as client:`.
  - `smtplib.SMTP.__exit__` sends QUIT and does `if code != 221: raise SMTPResponseException(code, message)` (stdlib source printed). That exception lands in `except smtplib.SMTPResponseException` (line 129) after `refused` was already set.
  - Repro: scratchpad `exp/smtp_quit.py` uses the real `__exit__`, with `send_message` succeeding and QUIT answering 250. Output: `mail accepted by server: True | receipt: failed smtp_250`.
  Failure: a relay that answers QUIT with 250 or 421 after accepting DATA. The email is delivered, but the receipt is FAILED `smtp_250` / `smtp_421` and `OutputDeliveryError` is raised. A resend per R-E3 duplicates the email. This is a false failure on the exact path EC-24 guards ("a retry would send them a duplicate").
  Smallest fix: treat the session as decided once `send_message` returns. Close with `contextlib.suppress(smtplib.SMTPException, OSError): client.quit()`, or check a `refused is not None` flag before mapping an exception. Then map only exceptions raised before acceptance. Add a fake QUIT failure step to `SmtpScript`.
  Spec IDs: INV-10, EC-24, INV-11.

R-E5 [Minor] [security] vidbyte/lib/outputs/base.py:35-37 — A header credential with a non-ASCII character passes construction, fails every delivery, and its full value sits in `repr(err.__cause__)`
  Evidence:
  - `credential` only strips whitespace. `"​"` (zero-width space, common in copy-paste) is not whitespace to `str.strip()`.
  - Repro: scratchpad `exp/nonascii_token.py` with `GitHubIssueOutput(repo="acme/shop", token="ghp_S3CRETgithub​")`. No request leaves the process. Output:
    `receipts: [('failed', 'unexpected:UnicodeEncodeError')]`
    `secret in str(cause): False`
    `secret in repr(cause): True`
  - The cause is attached by `raise OutputDeliveryError(...) from first_exception` (`dispatcher.py:77-78`). httpx's `UnicodeEncodeError` keeps the whole header value (`Bearer <token>`) in `.args` and `.object`.
  Failure: every reply fails delivery only after the agent has done its work, contrary to "fail before a long run". Any logger or debugger that renders `repr(exc.__cause__)`, or the exception args, shows the token. GitHub, Linear, and Notion (header credentials) are affected; Jira base64-encodes, and URL credentials are percent-encoded.
  Smallest fix: in `OutputArguments.credential`, reject a resolved value that is not `isascii()` and `isprintable()`. Raise `ConfigurationError` naming the parameter and the variable, never the value, exactly like the missing-credential error.
  Spec IDs: INV-4, INV-5, INV-21.

R-E6 [Minor] [error-handling] vidbyte/agents/output/dispatcher.py:45 — `connectors()` accepts a caller-written connector whose `destination` is not an `OutputDestination`; delivery then crashes with `ConfigurationError` and loses every receipt
  Evidence:
  - The runtime-checkable Protocol checks only that the attribute exists.
  - Each receipt is built from `connector.destination` (`dispatcher.py:57` and `:102`), and `DeliveryReceipt.__post_init__` rejects a non-enum value.
  - Repro: scratchpad `exp/str_destination.py`, with `outputs=[OkOutput(), PagerDutyOutput()]` where the second has `destination = "pagerduty"` and a failing send. Output:
    `construction accepted: 2`
    `ConfigurationError | destination must be an OutputDestination, got 'pagerduty'.`
    `ok connector sent: 1 | deliveries key: False`
  Failure: a user writes their own connector (FR-5 invites it) with a string destination for a platform outside the 11. Construction passes. The first skip or failure raises a bare `ConfigurationError` after the other connectors have already posted. No `deliveries` are recorded, `except OutputDeliveryError` (§4) does not catch it, and the AC-24 recipe cannot run.
  Smallest fix: in `OutputDispatcher.connectors`, also raise `ConfigurationError` naming the index when `not isinstance(item.destination, OutputDestination)`, and add that case to the AC-20 test.
  Spec IDs: INV-21, INV-6, FR-5.

R-E7 [Minor] [test-quality] tests/features/agent_output_connectors/test_output_connectors_wire_contract.py:244,270 — The one-line title rule (INV-15) is tested only for GitHub and email; removing it from Jira, Linear, or Notion breaks no test
  Evidence:
  - The AC-10 test (line 244) and the EC-18 test (line 270) send long or multi-line titles only to `GitHubIssueOutput` and `EmailOutput`. The `WIRE_ROWS` titles are single short lines.
  - Mutation run on a scratch copy of 9463c348:
    `M1 jira-summary-not-single-line => 313 passed`
    `M2 linear-title-not-single-line => 313 passed`
    `M3 notion-title-not-single-line => 313 passed`
  Failure: a regression that sends `content.title` raw to Jira passes CI. A structured title such as `"Weekly report\nBcc: …"` then gives Jira a multi-line summary, a 400 that EC-18 calls out, and every such reply fails. Linear and Notion get multi-line titles of 250+ characters.
  Smallest fix: parametrize the EC-18 and AC-10 title assertions over `jira_issue` (`fields.summary`), `linear_issue` (`variables.input.title`), and `notion_page` (`properties.title.title[0].text.content`).
  Spec IDs: INV-15, EC-18.

VERIFIED CLAIMS
1. **"313 passed" (S3 report, gate 1): held.** It is reproduced below.
2. **INV-10 / FR-11, retry only on 429: held.** See `transport.py:49` with `OUTPUT_RETRY_STATUS_CODES = (429,)` and `OUTPUT_RATE_LIMIT_RETRIES = 2` (`constants/outputs.py:22-23`). Network errors are never retried. Mutation M24 is caught.
3. **"A `wait_for` timeout is FAILED network with no retry": held.** See `dispatcher.py:91-94`; the cancelled request is not retried. EC-4 accepts that a delivered post may get this receipt; see R-E3 for the recipe consequence.
4. **AC-18 / INV-20, `CancelledError` propagates unwrapped and the claimed queue is cleared: held.** See `dispatcher.py:65-67` and `base.py:952-958`. Mutation M5 fails 2 tests.
5. **AC-23, the session captures the error once: held.** It is deduplicated by exception identity (`router.py:378-384`).
6. **D-7 / AC-12, forks never deliver: held.** `fork.py` passes `outputs=()`. Mutation M8, which drops it, survives because `BaseAgent`'s default is already `()`: an equivalent mutant, not a gap. Jev bulk, clone, swarm, and continuation agents and `HandoffAgent.from_source_agent` build agents without `outputs` (grep plus `handoff.py:60-68`). EvalRunner forks `BaseAgent` targets (`evals/runner.py:130,161`).
7. **INV-22, no await without outputs: held.** The `if self.outputs:` guard is at `base.py:936`.
8. **"The deadline is read from the module global at call time" (S3 tricky parts): held.** See `dispatcher.py:92`.
9. **NFR-2 / EC-47, "the hard bound is 35 s … a failure within the deadline": did NOT hold** for sync `run()` with `EmailOutput` (R-E2).
10. **EC-41, a credential in a URL query or path is "Never logged": did NOT hold** (R-E1).
11. **NFR-7 layering: held.** Nothing under `vidbyte/lib/` imports `vidbyte.agents`, and `vidbyte/agents/output/` imports only the stdlib, `vidbyte.lib`, and itself (grep).
12. **INV-27, `pyproject.toml` unchanged: held.** `git diff --stat` is empty.
13. **SSRF (§10): no model-driven path found.** The URL, repo, site, and recipient come only from the constructor (INV-3 test). Redirects are refused, as tested with a real httpx `MockTransport`. `JIRA_SITE_PATTERN` is used with `re.fullmatch`.
14. **Data and scale: nothing applies.** There are no queries, collections, or migrations. `metadata["deliveries"]` is bounded at `len(outputs)` per reply.

COMMANDS RUN
- `git log --oneline -3`, then `git diff 9463c348 HEAD --stat`: HEAD is 0b9bc19e, and the diff touches only `pipeline.md`.
- `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` gives `313 passed in 3.08s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/coding_agent tests/test_restore_output_schema.py tests/test_jev_agent.py` gives `134 passed, 11 skipped in 5.34s`.
- `python --version` gives `Python 3.11.0`. `python -c "import httpx; print(httpx.__version__)"` gives `0.28.1`.
- `inspect.getsource(httpx.AsyncClient._send_single_request)` contains `logger.info('HTTP Request: %s %s "%s %d %s"', request.method, request.url, ...)`.
- `inspect.getsource(asyncio.runners.Runner.close)` shows `loop.run_until_complete(loop.shutdown_default_executor())`, with signature `(self)` and no timeout.
- `inspect.getsource(smtplib.SMTP.__exit__)` shows `if code != 221: raise SMTPResponseException(code, message)`.
- Scratchpad experiments (offline, with fakes or MockTransport), run with `PYTHONPATH=<worktree> python <scratchpad>/exp/<file>.py`:
  - `httpx_log_leak.py` ends with `secret in log: True`.
  - `smtp_deadline.py` ends with `agent.run returned after 3.02s (deadline 0.2s)` and `events: [('connect', 0.0), ('sent', 3.0)]`.
  - `nonascii_token.py` ends with `secret in repr(cause): True`.
  - `smtp_quit.py` ends with `mail accepted by server: True | receipt: failed smtp_250`.
  - `str_destination.py` ends with `ok connector sent: 1 | deliveries key: False`.
- Mutation harness: `git archive 9463c348 vidbyte tests pyproject.toml REPO_MAP.md` into `<scratchpad>/mut`, then `run_mut.sh` for each mutation. The baseline is `313 passed`. Results:
  - Caught: M4 (1 failed), M5 (2 failed), M7 (1 failed), M11 (1 failed), M13 (7 failed), M20 (18 failed), M22 (11 failed), M23 (2 failed), M24 (7 failed).
  - Survived: M1, M2, M3 (R-E7), M6 (chain `from` the last rather than the first exception; low value), and M8 (equivalent mutant).
- I did not run `lint/run.py` or `scripts/run_ci.py`, as instructed. No file in the worktree was modified; all experiment and mutation files are in the session scratchpad.
