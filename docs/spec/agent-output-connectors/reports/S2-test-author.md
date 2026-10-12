# S2 · Test author report: agent-output-connectors

Branch `feat/agent-output-connectors`, base `db3988ff`, started at `4af2a665`. Spec r3 was the only design input; besides it, the only files under `docs/` that were read are `request.md` and `context/code-map.md`.

Commits:
- `d90400d2` test(outputs): add failing tests for agent-output-connectors [AC-1..AC-26]
- `1b4407f6` docs(spec): record test proof for agent-output-connectors (only the §6.2 Proof cells changed: 26 lines, each a filled trailing cell)
- this report

## Inventory built

Every spec ID with an observable behavior was mapped to at least one candidate test before any test was written. All of them are in `test-plan.md` → Coverage map:
- AC-1 … AC-26 (AC-22 is proved by the gate commands, not by pytest)
- INV-1 … INV-28 (INV-27 and INV-28 are lint-gated)
- EC-1 … EC-47, except the accepted or destination-side ones listed under pruning
- T-1 … T-5, D-19, D-20, D-21, FR-5, FR-11, FR-12, FR-18, §9.1, NFR-2, NFR-4, NFR-6, NFR-7, NFR-8

The result is 86 test functions and 313 collected cases in nine modules under `tests/features/agent_output_connectors/`:

| Module | Functions | Covers |
|---|---|---|
| `test_output_connectors_acceptance.py` | 6 | AC-1, AC-4, AC-5, AC-21, AC-23, INV-7 (direct `agent.run` on a bound agent) |
| `test_output_connectors_agent_wiring.py` | 11 | AC-12 … AC-15, AC-18, INV-7 queue drop, drained follow-ups (INV-5, INV-6), EC-20, EC-43, FR-5 |
| `test_output_connectors_dispatch.py` | 12 | AC-8, AC-11, AC-19 (structural), AC-6 (e), AC-24, INV-9/10/12/13, render failures, diagnostic packet, EC-27 |
| `test_output_connectors_wire_contract.py` | 13 | AC-9, AC-10, AC-17, §9.2 rows per destination, D-21 link table, caps, Slack escape after truncation, title injection, webhook `structured` |
| `test_output_connectors_http_failures.py` | 6 | AC-6 (a–d), AC-7, AC-25, INV-11 token grammar, 2xx range, size ceiling |
| `test_output_connectors_email.py` | 6 | AC-16 (all parts), SMTP failure table, partial refusal, sender rules |
| `test_output_connectors_configuration.py` | 11 | AC-2, AC-20 (30-row table), outputs validation, env/explicit precedence for all 11 connectors, EC-37 rotation, UUID forms |
| `test_output_connectors_security.py` | 5 | AC-3 across 11 destinations × all surfaces, record repr masking, cross-destination credential isolation, model steering, D-19 |
| `test_output_connectors_contract.py` | 16 | §8.5 public names (18 package / 17 root), §12.3 placement, enum values, record validation, constants, AST layering (lib vs agent side), AC-26 docs |

## What was pruned and why

The full table is in `test-plan.md` → "Tests deliberately NOT written". In short:
- **AC-19 wall-clock bound.** Replaced by an event-gated test. The second send finishes first, and the test fails deterministically if sends run one after another. A real-time bound would be flaky on Windows.
- **`KeyboardInterrupt` during delivery (EC-19).** Raising it inside a loop task tears down the test loop. `CancelledError` exercises the same `except BaseException` block.
- **Accepted or destination-side behavior.** Covers EC-19/EC-47 (the thread cannot be cancelled), EC-28 (serializer drop), EC-29, EC-30, EC-46 (destination quirks), EC-39 (existing `run_sequentially`), and EC-44/EC-45 (a user agent used as a specialist).
- **Default-only paths.** INV-16 Jev bulk/clone/swarm/continuation agents and `Session.resume`/`fork_from`, plus a per-`AgentRuntimeType` matrix. These would only re-prove the `()` default or re-run the same inline block.
- **Transport arguments.** `idempotency_key`, `retry_count`, `retry_status_codes`, and `follow_redirects` are not visible at `_send_once`, so their behavior is asserted instead (the AC-6 table, and AC-25 via `MockTransport`).
- **Size tests for the existing edited READMEs.** `tests/test_readme_size_limit.py` already enforces these, and a new test would have passed before implementation, so it would not be red. Only the two new READMEs are tested.
- **Gate-only checks (AC-22, INV-27, INV-28, NFR-1, NFR-3, NFR-5).** Covered by `python lint/run.py`, `python scripts/run_ci.py`, and `python scripts/generate-sdk-public-api.py --check`.
- **Q-1 … Q-10 and NG-1 … NG-12.** Not built. Only the Q-5 default is pinned, as part of AC-11 (e).
- **Draft-only cuts.** A duplicate `mock_destination` fixture and an unused `_row_case` helper were removed.

## Red run (exact output)

Bootstrap: none (deps present globally); PYTHONPATH=$(pwd)

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors
...
ERROR tests/features/agent_output_connectors/test_output_connectors_wire_contract.py::test_webhook_structured_field_is_a_json_value_or_none[other-object-dropped]
ERROR tests/features/agent_output_connectors/test_output_connectors_wire_contract.py::test_webhook_structured_mapping_with_a_non_json_value_is_failed_unexpected_type_error
21 failed, 292 errors in 4.71s
```

The pack was re-run at `d90400d2`, and the result above is from that run. Grouped reasons (from `--tb=line`):
```
292 E   ModuleNotFoundError: No module named 'vidbyte.agents.output'
 12 ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.outputs'
  2 AssertionError: vidbyte/lib/outputs/README.md is missing
  1 AssertionError: vidbyte/agents/output/README.md is missing
  1 AssertionError: spec 12.3 rows 4-18 modules missing from vidbyte/lib/outputs: [...]
  1 AssertionError: assert ['__init__', ... 'dispatcher'] == []
  1 AssertionError: assert 'outputs=' in '# Agents ...'
  1 TypeError: JevAgentSettings.__init__() got an unexpected keyword argument 'outputs'
  1 ImportError: cannot import name 'GitHubIssueOutput' from 'vidbyte'
  1 AttributeError: 'OfflineTestAgent' object has no attribute 'outputs'
```

Every reason is a missing spec name, module, keyword, or doc. None is a collection crash, a fixture typo, or a network attempt. The feature imports are deferred into fixtures, so all 313 cases collect.

The rest of the suite is unaffected:
```
$ PYTHONPATH=$(pwd) python -m pytest -q
21 failed, 3203 passed, 12 skipped, 292 errors in 24.27s     # every failure and error is in the new pack
$ PYTHONPATH=$(pwd) python -m pytest -q tests/test_jev_agent.py tests/features/coding_agent tests/test_restore_output_schema.py tests/test_agent_tool.py tests/test_agent_fork_isolation.py tests/test_custom_exception_constructors.py tests/test_readme_size_limit.py
202 passed, 11 skipped in 5.95s
$ python lint/run.py
SDK-LINT: PASS        # A001 at its 643 allowance; lint/baseline.json untouched
```

## Fixtures added or extended

All fixtures are new and live in the pack. No existing fixture, conftest, or test was modified.
- `conftest.py`:
  - `isolated_output_env` (autouse) deletes all 11 credential variables, `SMTP_PASSWORD` included.
  - `output_api` and `output_constants` are lazy imports.
  - `dispatcher_module` is used for deadline patching.
  - `fake_http` patches `HttpTransport._send_once` and `transport_module.asyncio.sleep`, so retries never sleep.
  - `fake_smtp` replaces `delivery.smtplib.SMTP` and `SMTP_SSL` with recorders that keep the real signatures.
  - `http_case` and `any_case` are per-destination builders.
- `factories.py` holds the shared helpers:
  - `AnswerRunner` (`repeat_last=` handles the runtime's output-schema re-prompt)
  - `HttpScript` (routes by URL substring and skips exhausted routes)
  - `ScriptedConnector` (a Protocol-only connector with an optional gate or error)
  - the destination case tables and placeholder credentials
- In the module itself, `test_output_connectors_http_failures.py` adds the `httpx_destination` fixture. It swaps `transport_module.httpx.AsyncClient` for an `httpx.MockTransport`-backed client, for the redirect and size-ceiling tests.
- Placeholders only: example.com and acme hosts, `T/B/X` webhooks, and fake tokens. No real credential or address is used.

## Validation beyond red

A throwaway prototype was written from the spec alone in the session scratchpad, outside the repo, and none of it was committed. On it, all 313 cases pass, and so does the whole suite (3516 passed). Then 72 single-point mutations were run against it, and 71 were caught. The survivor drops the explicit single-connector check, and it is an equivalent mutant: a connector is not iterable, so the `outputs` error is raised anyway. Three tests were added because of surviving mutants:
- Slack escapes after truncation.
- A direct `agent.run` on a session-bound agent notifies the session.
- A delivery failure drops the run's queued follow-ups.

## Spec defects found

1. **AC-18 "`agent._queued_prompts` is empty" is vacuous as written.** After any run, the attribute is a fresh list (the claim model). The test instead holds the claimed list object from before `arun` and asserts that it was emptied. The same approach is used for INV-7 on delivery failure.
2. **AC-19's wall-clock bound ("under 0.35 s") is not deterministic.** It was replaced by an event-gated structural test, which keeps the "second finishes first, receipts in configured order" intent.
3. **§13 says patching `_send_once` reaches every HTTP behavior. It does not.** `follow_redirects`, `retry_count`, `retry_status_codes`, `idempotency_key`, and the response-size ceiling are applied above or inside the client. AC-25 and the size ceiling need an `httpx.MockTransport` that replaces `transport_module.httpx.AsyncClient`.
4. **AC-4 assumes one model call.** The runtime re-prompts on invalid structured output, so a scripted runner must keep returning the invalid answer.
5. **AC-12 `AgentTool(agent)` fails as written for an agent without a name** (`ToolSpec.name cannot be empty`). The test passes `agent_metadata=AgentMetadata(name=...)`.
6. **The AC-23 / INV-7 inline `_notify_session_exception(exc)` cannot be observed through `session.run`.** `Session.run` notifies the session itself. Only a direct `agent.run` on a bound agent proves the inline block does it, and a separate test covers that.
7. **AC-20 `outputs=SlackOutput(...)` cannot be told apart from the generic "not iterable" rejection.** Both raise the `outputs` error, so a dedicated single-connector check is untestable (the equivalent mutant above).

## Addendum: S4 follow-up (2026-10-11)

The coordinator asked for failing tests for the defects S4 confirmed. Inputs:
- `review.md`;
- `reports/S4-findings-verifier.md`;
- spec r6 (`a270e6ed`): §16 S4-R1 to S4-R15, INV-2, INV-4, INV-15, INV-19, INV-21, AC-10, AC-11 (f), AC-16, AC-20, EC-13, EC-14, EC-16, EC-41, EC-47, EC-48, EC-49, NFR-2, §13, and §12.3 rows 2, 5, 7, 13, 16, and 22.

The code under test is S3_HEAD `9463c348`; nothing under `vidbyte/` was touched. The work produced two commits:
- `45ba29cc` test(outputs): add failing tests for S4 findings [R-1, R-2, R-3, R-12, R-14, R-15]
- `975f8d9d` docs(spec): record S4 test proof for agent-output-connectors. This commit extends only the AC-10, AC-11, and AC-20 Proof cells.

### Tests added
The pack grows by 6 test functions and 27 cases, from 313 to 340 cases.

| Finding | Test (file → name [case ids]) | Red today because |
|---|---|---|
| R-1 Blocker | security.py → `test_url_credential_never_reaches_the_httpx_request_log_while_the_callers_own_requests_still_do` [slack, discord, teams, google-chat, telegram, webhook] | httpx's `HTTP Request: POST https://…S3CRET…` INFO record is captured |
| R-2 | configuration.py → `test_invalid_outputs_value_is_rejected_when_the_agent_is_built[destination-not-an-enum]` | `DID NOT RAISE ConfigurationError` |
| R-2 | dispatch.py → `test_send_that_returns_anything_but_a_delivery_receipt_fails_only_its_connector` [none, str] | `unexpected:NoneType` / `unexpected:str` instead of `unexpected:ConfigurationError` |
| R-3 | email.py → `test_sync_run_returns_at_the_delivery_deadline_without_waiting_for_a_stalled_smtp_session` | `run() waited for the SMTP worker thread instead of returning at the deadline` |
| R-12 | email.py → `test_quit_reply_after_the_server_accepted_the_message_never_changes_the_receipt` [quit-answers-250, quit-answers-421, partial-refusal-then-quit-421; connection-dropped-at-quit passes today] | FAILED `smtp_250` / `smtp_421` for an accepted mail |
| R-14 | wire_contract.py → `test_long_first_line_becomes_a_250_character_one_line_title_at_every_titled_destination`, `test_title_whitespace_runs_and_newlines_collapse_to_one_space_at_every_titled_destination` [github_issue, linear_issue, jira_issue, notion_page, email] | Pass today, because the code is correct and the gap was coverage; proven by mutation instead (below) |
| R-15 | configuration.py → `test_invalid_connector_argument_is_rejected_at_construction_naming_the_parameter_and_no_secret` [slack-unparseable-ipv6-host, slack-non-numeric-port, slack-port-out-of-range] | bare `ValueError: Invalid IPv6 URL`; `DID NOT RAISE` for both ports |

No test was added for R-4, as directed: the AC-16 and AC-20 address cases cover it. R-5 to R-11 and R-13 need no test from me, because they are wording, placement, or not-built items.

### Fixtures extended
No existing assertion was changed or removed.
- `factories.py`, `SmtpScript`:
  - `quit_reply` holds a `(code, text)` pair or an exception.
  - `hold(step)` returns a `threading.Event` gate.
  - `released` is set when a held step stops waiting.
  - `HOLD_SAFETY_SECONDS = 10.0`.
  - `answer_quit()` plays the scripted reply.
- `factories.py`, `ScriptedSmtp`:
  - `__exit__` now behaves like `smtplib.SMTP.__exit__`: it sends QUIT, raises `SMTPResponseException` on a non-221 reply, swallows a disconnect, and always closes.
  - `quit()` behaves like `smtplib.SMTP.quit`: it returns the reply, and a disconnect raises.
  - Both record a `quit` step before `close`.
  - With the default 221 reply, every earlier test behaves as before.
- `factories.py`, other changes:
  - `ScriptedConnector(result=…)` lets `send` return any value.
  - `HttpxRequests` holds the MockTransport recorder and router.
- `conftest.py`: the `httpx_destination` fixture moved here unchanged from `test_output_connectors_http_failures.py`, which now uses it under the same name.

### Red output (exact)
```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors
16 failed, 324 passed in 11.67s
$ PYTHONPATH=$(pwd) python -m pytest -q
16 failed, 3527 passed, 12 skipped in 33.84s
$ python lint/run.py
SDK-LINT: PASS        # A001 643 = allowance; lint/baseline.json untouched
```
The grouped reasons are in `test-plan.md` → "S4 additions". All 313 earlier cases pass. Every failure is one of the 16 new cases.

### Validation
The r6 fixes were applied to a throwaway copy of the tree in the scratchpad. That copy was never committed.
- **Fixed copy.** The pack passes (`340 passed`), and so does the whole suite (`3543 passed, 12 skipped`).
- **One fix left out at a time.** Exactly that fix's cases turn red: R-1 → 6, R-2 → 3, R-3 → 1, R-12 → 3, R-15 → 3.
- **Wrong-fix mutations.** All 16 were caught:
  - R-1: five ways to silence or mis-scope the httpx guard;
  - R-2: either check missing;
  - R-3: `asyncio.to_thread`, and `run_in_executor(None, …)`;
  - R-12: `quit()` unsuppressed, and suppressing only `SMTPResponseException`; both are caught by the `connection-dropped-at-quit` row that passes today;
  - R-15: `.port` never read;
  - R-14: Jira, Linear, or Notion sends the raw title (3 mutations), and Jira cuts the title without collapsing whitespace.
- **Determinism.** The stalled-SMTP test passed 25 of 25 runs on the fixed copy.

### Deviations from the brief
1. **R-1 sets INFO on the root logger instead of `caplog.set_level(logging.INFO, logger="httpx")`.** A level set on `httpx` would mask a wrong fix that raises httpx's own level at import, because caplog would override it. With INFO on the root, that mutation is caught. httpx's logger level is NOTSET in this suite, and no test sets it.
2. **R-15 values contain `SECRET_MARKER`**: `https://[::1/services/T000/B000/S3CRETipv6` and `https://hooks.slack.com:abc/services/T000/B000/S3CRETport`. This makes the table's no-echo checks bite. They have the same shape as the r6 literals in AC-20 and EC-13. I also added an out-of-range port row, because INV-21 and row 5 name "a number in range".
3. **The R-3 test is ordering-based, with a 10 s backstop on the held step.** On the current code it fails after about 10 s, and it never hangs. On a fixed copy it takes about 0.5 s, the shortened deadline. It never asserts elapsed time.

### Spec items found (none blocking)
- **R-1, R-3, and R-12 have no AC row.** Their proof is INV-4/EC-41, NFR-2/EC-47/INV-19, and EC-48, so no Proof cell names them. AC-3's surface list does not include logs.
- **AC-20's `"pagerduty"` case cannot use a built-in connector.** Every built-in connector has an enum `destination`, so the case uses the pack's caller-written `ScriptedConnector("pagerduty")`. This is not a spec defect.
