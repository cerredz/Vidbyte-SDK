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
