# S4 findings verifier — report

Diff: `git diff origin/main...9463c348` (merge base `db3988ff`). `git diff --quiet 9463c348 HEAD -- vidbyte tests` succeeds, so HEAD `0b9bc19e` has the same code. Inputs read in full: the three S4 reviews, spec.md r5 (§0–§10), the review.md format, house-style.md, AGENTS.md, field-guide `init.md`, `strict-config-dataclasses.md` and `class-bound-helpers.md`. request.md and test-plan.md were read for the cited rows.

I wrote only review.md and this report. All scripts and the mutation copy are under `scratchpad/verifier/`. One slip: my first mutation loop wrote four `.bak` copies of connector modules to `C:\Program Files\Git\tmp_*.bak` (the Git Bash `/`). I deleted them at once (`ls /tmp_*.bak` → none), and the worktree was never touched.

## Verdict
MERGEABLE AFTER FIXES. Confirmed: 1 Blocker, 3 Majors, 11 Minors (one of them mine). No whole finding was refuted; one sub-claim was refuted (R-V1's "https drift"). No severity was downgraded. R-E6 rose from Minor to Major by merging into R-2.

## Merge map (original → merged)
| Original | Lens | Proposed | Merged | Final | Note |
|---|---|---|---|---|---|
| R-E1 | engineering | Blocker | R-1 | Blocker | Count corrected from 5 to 6 connectors |
| R-C1 | conformance | Major | R-2 | Major | Same root cause as R-E6 (`dispatcher.py:45`) |
| R-E6 | engineering | Minor | R-2 | Major | Merge keeps the highest severity |
| R-E2 | engineering | Major | R-3 | Major | |
| R-V1 | conventions | Major | R-4 | Major (narrowed) | "https drift" sub-claim refuted; fix changed to a pattern constant |
| R-C2 | conformance | Minor | R-5 | Minor | owner: spec-author |
| R-V2 | conventions | Minor | R-6 | Minor | |
| R-V3 | conventions | Minor | R-7 | Minor | |
| R-V4 | conventions | Minor | R-8 | Minor | Receipt-url echo half not recommended (T-1) |
| R-V5 | conventions | Minor | R-9 | Minor | |
| R-V6 | conventions | Minor | R-10 | Minor | |
| R-E3 | engineering | Minor | R-11 | Minor | Pair with R-3 |
| R-E4 | engineering | Minor | R-12 | Minor | Reproduced; not upgraded |
| R-E5 | engineering | Minor | R-13 | Minor | Reproduced; not Blocker-class; [scope-adding] |
| R-E7 | engineering | Minor | R-14 | Minor | Reproduced by mutation; owner: test-author |
| — | verifier | — | R-15 | Minor | `https_url` raises a bare ValueError and passes an invalid port |

Ordering: the Blocker first. Majors are ordered by how much code the fix touches: R-2 is two checks in one file; R-3 is one executor plus one call in one file, with spec wording; R-4 touches three or four files.

## Verifications (my evidence)

### R-1 (R-E1): secrets in `httpx` INFO logs. CONFIRMED, Blocker.
- **Code.** `OutputHttp.post` → `HttpTransport().request` (`delivery.py:55`) → `httpx.AsyncClient`, which logs `HTTP Request: %s %s …` with the full `request.url`. Telegram puts the token in the path (`telegram.py:45`). The other five connectors pass the secret URL itself.
- **Existing guard.** `git grep -n "httpx" -- vidbyte/ | grep -i log` → empty. `git grep -nE 'getLogger\(("|')(httpx|httpcore)'` → empty. `git grep -nE "addFilter|logging\.Filter" -- vidbyte/` → empty. The test pack has no `caplog` or `logging` use. Every pack test scripts `_send_once` (`conftest.py:68-80`), so httpx's own log call never runs in those tests.
- **Run.** `PYTHONPATH=<wt> python scratchpad/verifier/v_e1_logs.py` drives a real `agent.run()` with the six URL-secret connectors, the real `_send_once`, and `httpx.MockTransport`:
  ```
  root=WARNING receipts=['sent'] leaked=[] loggers=[]
  root=INFO receipts=['sent'] leaked=['slack', 'discord', 'teams', 'google_chat', 'telegram', 'webhook'] loggers=['httpx']
      httpx|INFO|HTTP Request: POST https://hooks.slack.com/services/T0/B0/VSECslack "HTTP/1.1 200 OK"
      httpx|INFO|HTTP Request: POST https://api.telegram.org/bot123456:VSECtelegram/sendMessage "HTTP/1.1 200 OK"
      (and Discord, Teams sig, Google Chat token, webhook)
  root=DEBUG receipts=['sent'] leaked=[...all six...] loggers=['httpx']
  ```
  The leak is real under plain INFO logging. It does not occur at Python's default WARNING level. At DEBUG, httpcore adds no URL.
- **Spec reading.**
  - EC-41 targets these exact credential locations: "A credential carried in a URL query (Google Chat `key` and `token` …) or path (the Telegram bot token). | Never logged."
  - request.md:58 records the user-approved decision: "Never logged".
  - request.md:73 rejected Apprise because "credentials embedded in URL strings leak through logs".
  - §4:128 promises the developer does not have to "keep secrets out of logs".

  The words have no "by the SDK's own loggers" qualifier, and the developer cannot prevent this without knowing httpx internals. "Never logged" therefore covers a third-party log line emitted by a call the SDK makes with a URL the SDK built. INV-4's list does not name logs, but EC-41 does, and EC-41 cites INV-4. A doc-only fix is not acceptable.
- **Calibration.** Blocker. It is unsafe, it contradicts a settled user decision and a spec edge case, and it affects 6 of 11 connectors on every finished reply.
- **Fix feasibility.** `v_e1_fix_probe.py` wraps `OutputHttp.post` in a module `ContextVar` and adds one `httpx` logger filter. Without editing source, it printed:
  ```
  receipts: [('slack', 'sent'), ('telegram', 'sent')]
  secret in log after filter: False
  user's own httpx request still logged: True
  ```
- **Constraints checked.**
  - A module-level `ContextVar` has precedent at `vidbyte/lib/usage_ledger.py:39`.
  - The NFR-7 test (`test_output_connectors_contract.py:270-281`) checks imports only. `logging.getLogger("httpx")` imports nothing, but importing `httpx` would fail it.
  - S008 on `post` is 5/4/8 against limits of 10/12/50.
  - Changing `lib/http/transport.py` would be outside §12.3 and would also hide the user's own model-call logs. Raising the logger level globally would change users' logging.

### R-2 (R-C1 + R-E6): non-enum `destination` from a caller-written connector. CONFIRMED, Major.
- **Code.** `connectors()` checks `isinstance(item, OutputConnector)` (`dispatcher.py:45`). That is a `runtime_checkable` Protocol, so only presence is tested. Receipts built by the dispatcher use `connector.destination` at `:57` (skip), `:94` (deadline) and `:102` (unexpected). `DeliveryReceipt.__post_init__` rejects a non-enum value (`dataclasses/outputs.py:62`). The `:102` call runs inside `deliver` itself, outside the gathered tasks, so its `ConfigurationError` escapes `deliver` and is re-raised by `_deliver_outputs`.
- **Run.** `v_c1_destination.py`:
  ```
  A. str destination, send succeeds: construction: accepted / run returned normally / webhook POSTs made: 1 | 'deliveries' on last_reply: True
  B. str destination, send raises TypeError: construction: accepted / raised ConfigurationError | destination must be an OutputDestination, got 'pagerduty'. / webhook POSTs made: 1 | 'deliveries' on last_reply: False
  C. str destination, skipped reply (stop_reason=max_iterations): raised ConfigurationError | destination must be an OutputDestination, got 'pagerduty'.
  D. enum destination attribute, send returns None: OutputDeliveryError [('webhook','sent',None), ('webhook','failed','unexpected:NoneType')] | cause: NoneType
  ```
  In D, `type(err.__cause__).__name__ == "NoneType"`, which means there is no cause.
- **Spec reading.**
  - INV-21 says an item that "does not satisfy `OutputConnector`" raises "before any model call", and FR-5 types the member as `destination: OutputDestination`.
  - B breaks INV-6 (receipts lost), INV-7 and FR-10 (no `OutputDeliveryError` with `.reply`/`.receipts`), and C breaks INV-8 and AC-8 ("nothing is raised").
  - D's `unexpected:NoneType` is outside INV-11's `unexpected:<ExceptionTypeName>`.
- **Guards.** No existing guard. No test builds a non-enum destination: `grep "ScriptedConnector("` lists 6 constructions, all with `OutputDestination.*`, so the fix cannot break the pack.
- **Severity adjudication.** Conformance said Major; engineering said Minor. I chose Major. The wrong outcome lands after side effects (other connectors have posted). It raises the wrong exception type, so §4's `except OutputDeliveryError` misses it. And `OutputConnector` is a root export: the pack's own `ScriptedConnector` (`factories.py:279`) models a caller-written connector. It is not a Blocker because a type-checked caller (mypy) would be flagged, and built-in connectors are unaffected.
- **S008 headroom** (ruff with limits of 1): `connectors` C901 7, `_deliver_one` C901 3, against a limit of 10.

### R-3 (R-E2): sync `run()` with email outlives the deadline. CONFIRMED, Major.
- **Code.**
  - `email.py:65`: `await asyncio.to_thread(OutputSmtp.send, …)` runs on the default executor.
  - `base.py:1025` and `:1076`, and `sessions/session.py:174`: `asyncio.run(...)`.
  - `inspect`: `Runner.close` contains `loop.run_until_complete(loop.shutdown_default_executor())`, and `shutdown_default_executor` has signature `(self)`, so there is no timeout on 3.11. The repo floor is `requires-python = ">=3.11"`.
  - The SMTP client does get `timeout=OUTPUT_TIMEOUT_SECONDS` (`delivery.py:145-146`). That bounds each socket call, not the session (about 10 command round trips), and not a server that trickles bytes (each `recv` restarts the timeout). It is not a reason to downgrade.
- **Run.** `v_e2_deadline.py` (fake SMTP whose `send_message` sleeps 3 s; deadline patched to 0.2 s):
  ```
  python 3.11.0 | socket timeout passed to SMTP: 10.0
  1 sync run(): run() gave OutputDeliveryError [('failed', 'network')] after 3.03s (deadline 0.2s); events=[('connect', 0.0), ('accepted', 3.0)]
  2 arun(): coroutine raised after 0.20s; asyncio.run returned after 3.00s; events=[('connect', 0.0), ('accepted', 3.0)]
  3 sync run() with dedicated executor: run() gave OutputDeliveryError [('failed', 'network')] after 0.22s (deadline 0.2s); events=[('connect', 0.0)]
  3 after executor drained: events=[('connect', 0.0), ('accepted', 3.0)] (the late send that EC-19/EC-47 accept)
  ```
- **Spec reading.**
  - NFR-2 (P0) says "the hard bound is `OUTPUT_DELIVERY_DEADLINE_SECONDS` (35 s)".
  - EC-47's trigger includes "an SMTP server stalls between replies", and its user-visible promise is "A failure within the deadline. Without the guard, one trickling endpoint could hold `run()` for hours".
  - EC-19 and EC-47 accept that the thread keeps running and may send. They do not accept that `run()` waits for it, and test-plan.md:112 declines a test only for "thread still sending".
  - The §4 snippet uses `run()`.
- **Fix choice.** I recommend a dedicated module-level executor, as probe 3 shows; the reviewer named it first too.
  - The email test asserts only `session.thread_id != loop_thread` (`test_output_connectors_email.py:56`, `:67`), and no test patches `asyncio.to_thread` (grep).
  - S052 claims `ASYNC100/105/110/220/221` and S006 claims `RUF006`, so neither flags `run_in_executor`.
  - The literal spec text in INV-19, FR-17, §5 and §8.5 says `asyncio.to_thread`, so the spec author must reword it or record the change in §17. INV-19's weighted clause, "No blocking I/O runs on the event loop", still holds.
  - The executor's threads are still joined at interpreter exit (concurrent.futures atexit). That is process exit, not `run()`, and it is the same limitation EC-19 accepts.
  - A daemon thread was the runner-up. It would need loop-closed handling and could cut a session mid-send at exit.
  - Doc-only was rejected because it gives up a P0 NFR.

### R-4 (R-V1): duplicated email-address rule. CONFIRMED (narrowed), Major.
- **Code.**
  - `dataclasses/outputs.py:35-37` `_is_address`, and `outputs/base.py:84-88` `OutputArguments.address`, have identical bodies: `isinstance(value, str) and "@" in value and not any(char.isspace() or char == "," for char in value)`.
  - `email.py:51-52` calls `OutputArguments.address` and then `SmtpSettings.__post_init__` (`:107-108`), so both copies run on the same values.
  - `_is_text` vs `OutputArguments.text` is a one-expression non-blank check, not a drift risk.
- **Is it a behavior defect?** No. The two address predicates agree today.
- **The "https already drifted" claim: REFUTED.** The difference is specified, not drifted:
  - D-19 says webhook arguments are checked for "an `https://` scheme and a host";
  - §9.1 says `OutputRequest.url` "starts with `https://`" and the receipt `url` "a `str` starting with `https://`";
  - D-21 step 5 says the link must "start with `https://`".

  Every `OutputRequest` URL comes from an `https_url`-validated argument, a constant, or a `JIRA_SITE_PATTERN` host, so no input reaches a prefix-only check that the host check would have rejected.
- **Repo rules.**
  - Field guide `strict-config-dataclasses.md`, "Any primitive value validated inline in more than one call site…", Because: "Two independent inline copies of the same rule drift silently". Evidence: PR #352, the owner's own review comment.
  - Lint C008's PURPOSE: "so each primitive check has one owner instead of drifting copies". Its grammar covers only numeric and bool primitives: `python lint/run.py --rule C008` → `C008 RATCHETED: 45 known finding(s)` / `SDK-LINT: PASS`.
  - Spec §8.3 itself claims "The checks are already single-sourced in OutputArguments … so no check is duplicated inline", which the address rule contradicts.
- **Severity adjudication.** Major, not Minor and not Blocker. It does not change behavior, but it is the exact pattern this owner has commented on before (PR #352) and built a lint rule against, so it would surface in human review. It is not a Blocker because nothing is wrong or unsafe, and the spec made a recorded decision (§8.3) about the dataclass half of the lesson.
- **Fix adjudication.** The reviewer proposed making the private helpers public. Rejected:
  - `class-bound-helpers.md` says "Prefer a static helper class over a bag of module-level free functions";
  - `lib/dataclasses/outputs.py` cannot import `lib/outputs/base.py`, which imports it (a cycle).

  My fix is a pattern constant, following the precedents `JIRA_SITE_PATTERN` (`constants/outputs.py:94`) and `OUTPUT_ERROR_TOKEN_PATTERN` (`:46`). Equivalence check: `re.fullmatch(r"[^\s,]*@[^\s,]*", v)` against `_is_address(v)` over all 1,114,112 code points, in three positions each → `mismatches: 0`; a trailing newline is rejected by both.
  - The public-API contract derives only from root `vidbyte/__init__.py` `__all__` (`scripts/generate-sdk-public-api.py:3`), so a new constant in the module's own `__all__` needs no regeneration unless it is root-exported.

### Minor-tier checks (not Blocker/Major; reproduced where the lead asked)
- **R-12 (R-E4).** I used a subclass of `smtplib.SMTP` that keeps the real `__exit__` (`v_e4_e5.py`): `QUIT=221 -> sent None`; `QUIT=250 -> failed smtp_250`; `QUIT=421 -> failed smtp_421`; the server accepted the mail each time. Not upgraded: RFC 5321 says the QUIT reply MUST be 221, so only non-conformant servers or a 421 shutdown trigger it, and the error is a false failure, not a lost one. Its harm is the duplicate through R-11, which R-11's wording addresses.
- **R-13 (R-E5).** `GitHubIssueOutput(token="ghp_VSECgithub\u200b")` gives `receipts: [('failed', 'unexpected:UnicodeEncodeError')]`. The secret is in `str(err)`/`details`: False False; in `str(cause)`: False; in `repr(cause)`: True; in `traceback.format_exception(err)`: False. The session ledger records `type(exc).__name__` plus sanitized `details` only (`lib/dataclasses/failure.py:112-118`); `router.py:378-384` walks the cause chain only for identity. So none of INV-4's listed surfaces leaks and `logger.exception` is clean: Minor, not Blocker. The fix adds a validation rule INV-5 does not contain, so it is tagged [scope-adding].
- **R-14 (R-E7).** On `git archive 9463c348` in `scratchpad/verifier/mut`, one mutation at a time with the file restored between runs: baseline `313 passed`. Removing `single_line` from jira → `313 passed`; linear → `313 passed`; notion → `313 passed`; github → `2 failed, 311 passed`; restored → `313 passed`.
- **R-5 (R-C2).** `test_output_connectors_dispatch.py:157-163` asserts `("github_issue","failed",None,"unexpected:ConfigurationError")` and `fake_http.sends_to("api.github.com") == []`. INV-2 (spec.md:197) says "exactly once unless the reply is skipped". It is a spec contradiction; the code follows AC-11 (e).
- **R-6..R-10 (conventions).** Every anchor was re-read and holds:
  - `jira.py:52` (the check) vs `:60-63` (the `@intent`);
  - `delivery.py:5` "The only place…" vs `dispatcher.py:94`, `:102`;
  - the jev `settings.py:9` and `agent.py:9` TESTS lines lack the wiring test;
  - the Jira path is inline at `jira.py:73`;
  - `agents/output/README.md` headings are Modules, When Delivery Runs, Forks And Sub-Agents, Failure Behavior.
- **R-8 adjudication.** Keep only the Telegram half. Echoing the receipt `url` in its error would print the wrong value, which from a caller-written connector could be a secret webhook URL. The current omission matches T-1's posture.
- **R-11 (R-E3).** The recipe text is the spec's own (§9.2, AC-24, EC-42), so the fix is wording only. My R-3 run shows the mail was `accepted` at 3.0 s before sync `run()` raised FAILED `network`, which confirms the duplicate path.

### Blind-spot search (step 6)
- **R-15, added by me.** `v_blind_urls.py`:
  ```
  'https://hooks.slack.com:abc/services/T/B': ['unexpected:InvalidURL']; secret in formatted traceback: False; in repr(cause): False
  'https://hooks.slack.com/services/T/B/VSE' (\x7f): ['unexpected:InvalidURL']; secret in formatted traceback: False
  'https://[::1/services/VSECipv6': construction raised ValueError; secret in message: False
  ```
  So `https_url` (`base.py:43`) can raise a non-`ConfigurationError` (INV-21), and it accepts a bad port that only fails after the run. There is no secret leak, so it is Minor.
- **Other surfaces.** `agent.outputs` flows only to `base.py:235/576/936/951`, `fork.py:83`, `jev/agent.py:102` and `jev/settings.py:170`. No generic serializer (`vars(self)`, `__dict__`) touches it.
- **Fix interactions checked.**
  - R-1 and the NFR-7 import test: compatible if no `import httpx`.
  - R-2 and the AC-20 message rule: the message must contain `outputs`.
  - R-3 and the email thread test: compatible.
  - R-3 and spec INV-19's wording: needs the spec author.
  - R-3 and R-11: do them together.
  - R-4 and C016: no contract change.
  - No fix touches `base.py`, so `_generate_reply`'s S008 10/9/50 is safe.
- **Baseline at S3_HEAD (mine).** `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` → `313 passed in 1.65s`.

## Reproduce commands (all offline; run from the worktree)
```
PYTHONPATH=$(pwd) python <scratchpad>/verifier/v_e1_logs.py         # R-1
PYTHONPATH=$(pwd) python <scratchpad>/verifier/v_e1_fix_probe.py    # R-1 fix feasibility
PYTHONPATH=$(pwd) python <scratchpad>/verifier/v_c1_destination.py  # R-2
PYTHONPATH=$(pwd) python <scratchpad>/verifier/v_e2_deadline.py     # R-3 (+ fix probe)
PYTHONPATH=$(pwd) python <scratchpad>/verifier/v_e4_e5.py           # R-12, R-13
PYTHONPATH=$(pwd) python <scratchpad>/verifier/v_blind_urls.py      # R-15
```
`<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/ece663b4-5090-422c-ad68-c3b2451a23f6/scratchpad`.

## Disagreements adjudicated
1. R-C1 (Major) vs R-E6 (Minor): Major, for the reasons under R-2.
2. R-E1 says 5 connectors; the evidence shows 6.
3. R-V1's "https drift": refuted by D-19, §9.1 and D-21.
4. R-V1's proposed fix (public helpers): replaced with a pattern constant (class-bound-helpers lesson; import cycle).
5. R-V4's receipt-url echo: not recommended (T-1).
6. R-E2's doc-only fallback: rejected, because it gives up NFR-2 (P0).
7. R-E5 as a possible Blocker under T-1: no INV-4 surface or formatted traceback leaks, so it stays Minor.
