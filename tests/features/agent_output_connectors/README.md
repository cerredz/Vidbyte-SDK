# Agent output connectors feature tests

## Folder Description / Intent

This folder checks the public promise of `outputs=[...]`. One connector in the list plus one credential delivers each finished, validated reply to Slack, Discord, Teams, Google Chat, Telegram, email, GitHub Issues, Linear, Jira, Notion, a generic webhook, and since the follow-ups GitLab, the GitHub Actions job summary, Confluence, Typefully, or HubSpot. Every connector is attempted. Each one leaves one receipt in `reply.metadata["deliveries"]`, and a failure raises `OutputDeliveryError` without losing the reply. The tests drive the real `BaseAgent._generate_reply` path, the real `OutputDispatcher`, `OutputShaping` and connectors, and the real `HttpTransport` retry loop. Only the model runner, the single HTTP send, and the `smtplib` client classes are faked.

The implementations belong in `vidbyte/agents/output/` (the `OutputConnector` contract, shaping and skip rules, and the dispatcher) and `vidbyte/lib/outputs/` (one class per destination, argument checks, text helpers, and HTTP and SMTP send). The records, enums, and constants belong in `vidbyte/lib/dataclasses/outputs.py`, `vidbyte/lib/enums/outputs.py`, and `vidbyte/lib/constants/outputs.py`, and the error in `vidbyte/lib/errors/base.py`. The agent wiring belongs in `vidbyte/agents/base.py`, `vidbyte/agents/fork.py`, and `vidbyte/agents/jev/`.

## Non-Goals

- Do not reach a real destination or SMTP server, or use a real credential. `conftest.py` fakes `HttpTransport._send_once` and the `smtplib` classes and refuses sockets.
- Do not test OAuth destinations, YAML configuration, CLI commands, or per-user mention suppression. The specs leave them out (first batch NG-1 to NG-12 and Q-1 to Q-10; follow-ups Q-1 to Q-8). Webhook signing is in scope since the follow-ups.
- Do not test the transport's own retry, backoff, or size-ceiling code. `tests/test_web_operation_client_retry.py` and the HTTP transport tests own it; this pack only checks the arguments the connectors pass to it. The one exception is the follow-ups' `content=` keyword (AC-15): `test_output_connectors_webhook_options.py` checks that it puts exact bytes on the wire, because signed webhooks depend on it.
- Do not re-check the coding-agent constructor contract or the pinned `JevAgent.__init__` signature in place of their own tests. `tests/features/coding_agent/test_coding_agent_contract.py` and `tests/test_jev_agent.py` own them.

## File Index

- `README.md` explains the boundary of the pack and routes changes to their owners.
- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py` imports the feature lazily (`output_api`, `output_constants`, `dispatcher_module`), clears the sixteen credential variables, and installs the scripted HTTP send (`fake_http`), the in-memory httpx transport (`httpx_destination`), and the scripted SMTP server (`fake_smtp`). It also parametrizes over destinations (`http_case`, `any_case`).
- `factories.py` holds the placeholder credentials, the sixteen-destination table, the HTTP and SMTP fakes, the offline model runner, a caller-written connector, and the reply and receipt helpers.
- `test_output_connectors_acceptance.py` runs the spec's own snippet and the caller-visible outcomes end to end. Start here for a caller-visible regression.
- `test_output_connectors_agent_wiring.py` checks forks, `AgentTool`, export and restore, `JevAgentSettings`, `CodingAgent`, cancellation, drained follow-ups, capped runs, and a caller-written connector.
- `test_output_connectors_dispatch.py` checks the skip rule, title and body shaping, `render`, concurrency and receipt order, the per-connector deadline, the error's diagnostic packet, and resending only the failed connectors.
- `test_output_connectors_wire_contract.py` checks each destination's exact request, link extraction, mention neutralizing, body caps, one-line titles, and the webhook's structured payload.
- `test_output_connectors_http_failures.py` checks retries, error codes, redirects, and the response size ceiling.
- `test_output_connectors_email.py` checks the SMTP sequence, TLS, the worker thread, every SMTP failure code, the QUIT reply after acceptance, and sync `run()` at the deadline.
- `test_output_connectors_configuration.py` checks argument validation, the `outputs` value, and credential resolution from arguments and environment variables.
- `test_output_connectors_security.py` checks that credentials never reach a rendered surface, httpx's request log, or another destination, and that model output cannot steer delivery.
- `test_output_connectors_contract.py` checks the public names, enums, records, constants, import layering, and the required documentation.
- `test_output_connectors_followup_acceptance.py` runs the follow-up spec's snippet end to end and guards the first-batch headers. Start here for a follow-up regression.
- `test_output_connectors_rendering.py` checks Discord forum posts, Slack Markdown, Telegram rich messages, Teams cards, and Jira ADF.
- `test_output_connectors_webhook_options.py` checks webhook `headers=`, `payload=`, `secret=` signing, and the transport's `content=` bytes.
- `test_output_connectors_comments.py` checks comment, append, and label modes, and the forbidden mode combinations.
- `test_output_connectors_new_destinations.py` checks GitLab, the job summary file, Confluence, Typefully, and HubSpot.
- `test_output_connectors_update_in_place.py` checks GitHub sticky comments and keyed issues, read failures, and the read and patch transport rules.
- `test_output_connectors_followup_contract.py` checks the follow-ups' enums, class placement, and documentation.

## Logs

- 2026-10-11 - The pack was written red before implementation from the agent-output-connectors spec - every test fails until `vidbyte/agents/output/` and `vidbyte/lib/outputs/` exist.
- 2026-10-11 - Tests were added for the S4 review findings R-1, R-2, R-3, R-12, R-14, and R-15 - each new case was red against the first implementation (R-14's by mutation) and passes once its fix lands.
- 2026-10-14 - Follow-up tests were written red from the output-connector-followups spec, and the first-batch expectations its §13 names were updated - every new test fails until the follow-ups are built, except the AC-34 header guard, the Slack escaped-text case above 12,000 characters, and the OutputRequest list-body case, which pin unchanged behavior.
