# Feature: Agent output connectors

## High-Level Feature Description

A developer adds `outputs=[SlackOutput(), GitHubIssueOutput(repo="acme/shop")]` to `BaseAgent`, `Agent`, `CodingAgent`, or `JevAgentSettings`, and supplies one credential per destination (a constructor argument or an environment variable). After every finished, validated reply, the SDK itself sends the reply to each destination: Slack, Discord, Microsoft Teams, Google Chat, Telegram, email over SMTP, GitHub issues, Linear, Jira, Notion, or a generic webhook; since the follow-ups also GitLab, the GitHub Actions job summary, Confluence, Typefully drafts, and HubSpot tasks, plus comment, append, and update-in-place modes. The model never sees the credential and never chooses the destination. The caller gets one receipt per destination in `reply.metadata["deliveries"]`, and an `OutputDeliveryError` naming every failed destination.

If this regressed, the damage is external and often irreversible: a post goes out twice, an unvalidated or "Agent runtime stopped …" notice is posted to a channel, `@everyone` pings a whole server, a webhook URL or token appears in a log, an exception, or a checkpoint, a credential is forwarded to another host, or a revoked webhook fails silently for weeks.

## Contract

- **One line, one key.** Adding a connector to `outputs` and setting its documented environment variable (or passing the credential) is the whole integration. A missing credential, a non-`https://` URL, a malformed addressing argument, or an invalid `outputs` value raises `ConfigurationError` at construction, naming the parameter and never echoing a credential.
- **When.** Delivery runs only after the reply has passed `output_schema` validation and has been recorded (history, `last_reply`, bound session), and before queued follow-up prompts drain. A reply whose content is blank, or whose `stop_reason` is anything other than absent, `final_response`, or `is_done`, is SKIPPED for every connector, and no request is made.
- **What.** Each connector receives one `OutputContent(title, body)`: the connector's `render(reply)` when it has one, or else the structured `title` and `body` fields, falling back to the first line of the text and the agent's name. Each destination receives exactly one write request in its documented wire shape (since the follow-ups, GitHub `key=` first makes up to ten GET reads, and the job summary writes a file instead), with channel-wide mentions neutralized, bodies cut to the destination's cap with a `[truncated]` marker, and titles collapsed to one line of at most 250 characters.
- **How often.** Each configured connector is attempted once per reply, concurrently with the others. Only HTTP 429 is retried, at most twice. Every connector's send is bounded by `OUTPUT_DELIVERY_DEADLINE_SECONDS`.
- **Outcome.** `reply.metadata["deliveries"]` holds one receipt per connector, in configured order. If any receipt is FAILED, `OutputDeliveryError` is raised after every connector finished, carrying `.reply`, `.receipts`, and `.failed`. Error codes follow a fixed grammar and never contain a URL, header, credential, or response text beyond one validated token.
- **Never.** Forks and `as_tool()` children never deliver. Outputs are never serialized. Cancellation propagates unchanged.

## Actors / Callers

- SDK callers constructing `Agent`, `BaseAgent`, `CodingAgent`, or `JevAgentSettings` with `outputs=`, and calling `run`, `arun`, `generate_reply`, or `Session.run`.
- Callers resending failed destinations with `OutputDispatcher.deliver(failed, err.reply, {})`.
- Callers writing their own connector class that satisfies the `OutputConnector` protocol.
- `BaseAgent.restore(state, outputs=...)` re-attaching connectors.

## Inputs and Preconditions

- Credentials come from the connector's constructor argument or one environment variable per destination: `SLACK_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`, `GOOGLE_CHAT_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `SMTP_PASSWORD`, `GITHUB_TOKEN`, `LINEAR_API_KEY`, `JIRA_API_TOKEN`, `NOTION_API_KEY`, `VIDBYTE_OUTPUT_WEBHOOK_URL`, and since the follow-ups `GITLAB_TOKEN`, `GITHUB_STEP_SUMMARY` (a file path), `CONFLUENCE_API_TOKEN`, `TYPEFULLY_API_KEY`, `HUBSPOT_ACCESS_TOKEN`.
- Addressing arguments: `repo`, `labels`, `team_id`, `site`, `project`, `email`, `issue_type`, `parent_page_id`, `chat_id`, `to`, `host`, `username`, `sender`, `port`.
- The tests need no network and no real credential. The autouse fixture clears every variable above, so a developer's real `GITHUB_TOKEN` never reaches a test.

## Observable Outcomes

- `reply.metadata["deliveries"]`: the receipt tuple (destination, status, url, error_code).
- `OutputDeliveryError`: `.reply`, `.receipts`, `.failed`, its message, its A003 diagnostic packet, and its `__cause__`.
- The requests that reach `HttpTransport._send_once` (method, URL, headers, JSON body, timeout, response-size ceiling) and the number of attempts.
- The SMTP session: client class, host, port, timeout, TLS context, step order, login, the `EmailMessage`, and the thread it ran on.
- `ConfigurationError` messages; the `repr`/`str` of connectors, records, settings, receipts, errors, metadata, exported state, and session ledgers.
- `agent.outputs`, `fork().outputs`, `restore(...).outputs`, the session's head checkpoint, `session.failures.history()`.

## State Transitions

- Construction either raises `ConfigurationError` or yields a connector whose credential is resolved once and frozen (a later environment change does not affect it).
- Per reply: recorded → schema-checked → (skipped | delivered concurrently) → receipts written → (returned | `OutputDeliveryError` raised, queued prompts cleared, session notified) → drain.
- Receipts are terminal (SENT, FAILED, SKIPPED) and never mutate. Nothing is persisted, so there is nothing to roll back.

## Invariants

- Delivery never precedes schema validation or the turn's recording (INV-1, INV-7, INV-26).
- Each connector's `send` runs at most once per reply; exactly once unless skipped (INV-2).
- The destination and credential come only from construction (INV-3, INV-5).
- No credential appears outside the request to its own destination (INV-4).
- One receipt per connector, in configured order, whatever the finish order (INV-6).
- Only 429 is retried, at most `OUTPUT_RATE_LIMIT_RETRIES` times (INV-10).
- Error codes match the INV-11 grammar.
- No channel-wide or mass mention is delivered (INV-12).
- Bodies never exceed the destination cap; titles are one line of at most 250 characters with no marker (INV-14, INV-15).
- Email always uses verified TLS, off the event loop (INV-18, INV-19).
- Cancellation is never converted into a receipt (INV-20).
- Agents the SDK builds internally deliver nothing; outputs are never serialized (INV-16, INV-17).
- An agent without outputs behaves exactly as before (INV-22).

## External Dependencies

- `HttpTransport` (real; only `_send_once` is scripted, plus the transport's backoff sleep). The redirect, size-ceiling, and request-log tests go one level lower and script `httpx` itself with `httpx.MockTransport`, so the real redirect policy, the real response-size ceiling, and httpx's own INFO request log run.
- `smtplib` (scripted `SMTP` and `SMTP_SSL` classes on the module that `vidbyte/lib/outputs/delivery.py` imports; `socket.create_connection` refuses as a guard; the fakes mirror smtplib's `__exit__` and `quit`) and the worker thread the session runs on (real).
- The model runner (scripted Responses-shape `isDone` turns bound with `bind_test_runner`).
- `Session`, `InMemorySessionStore`, `AgentTool`, `JevAgent`, `CodingAgent` (real).

## Known Failure Modes

Each line is input + state → wrong output; the test that guards it is in `docs/spec/agent-output-connectors/test-plan.md`.

- **Timing.** An invalid structured reply → posted before `OutputSchemaViolationError`. Delivery placed after the drain → follow-up reply posted before the reply that queued it. Delivery placed before `record_turn` → session loses the turn when delivery fails.
- **Skips.** A `max_iterations` stop → "Agent runtime stopped after reaching max_iterations." posted and an issue opened. A middleware abort → abort notice posted. A deny-list of stop reasons → `contract_unsatisfied` or `finish_review_rejected` answers posted. Whitespace content → Slack 400 `no_text` reported as a failure.
- **Duplicates.** Retrying 5xx, 408, 409, or 425 (the transport default) → two issues. The same connector listed twice → every reply posted twice. Fork inherits outputs → one `as_tool()` call posts N times. A drained reply delivered twice, or not at all.
- **Silent failure.** 3 of 4 destinations fail and the run returns normally. Linear 200 with `errors[]` reported as SENT. A missing `html_url` reported as SENT.
- **Leaks.** `repr(SlackOutput(...))` prints the webhook URL. A `ProviderRequestError` excerpt with the URL copied into the error code. A 4xx body echoing the token copied into the code. The GitHub token sent with the Linear request. A 302 forwards the `Authorization` header to the `Location` host. A credential in `ConfigurationError`, `err.details`, metadata, exported state, or the session failure ledger. httpx's INFO line `HTTP Request: POST <url>` prints a webhook URL or the Telegram token.
- **Steering.** The model's structured `url`/`repo` fields change the request target. A `site` such as `acme.atlassian.net.evil.example` or a `repo` with `../` sends Basic or Bearer credentials to another endpoint. A title with `\nBcc:` adds an email header.
- **Content.** `<!channel>`, `@everyone`, `<users/all>`, `<mention-user …/>` notify everyone. `&` escaped after `<` → `&amp;lt;`. Off-by-one at the cap → Discord 400 on every long reply. A truncation marker with newlines put into an email subject or Jira summary. Jira, Linear, or Notion sending the raw multi-line or 400-character title. A structured `dict` (JSON-schema output) ignored because shaping only uses `getattr`.
- **Transport.** No `max_response_bytes` → a 50 MB body read into memory. No `idempotency_key` → the transport's POST retry guard fails every send. Following redirects. A trickling endpoint holds `run()` for hours. An unparseable webhook URL escapes as a bare `ValueError`, or a non-numeric port passes construction and fails only after the run. Sequential delivery → latency is the sum.
- **Email.** STARTTLS unavailable → login in plaintext. `ssl._create_unverified_context()` or no context. SMTP on the event loop. `apikey` used as the `From` address. A partial refusal reported as SENT. A non-221 QUIT after the server accepted the mail turns a delivered email into FAILED (and a resend mails twice). Sync `run()` waits for a stalled SMTP thread past the deadline, because `asyncio.run` joins the default executor.
- **Composition.** `JevAgent` gains an `outputs` keyword (breaks the pinned signature). `JevAgentSettings(outputs="slack")` iterates characters. `restore` silently drops or serializes outputs. A user-written connector rejected because it is not a `BaseOutput`. Passing the class `SlackOutput` instead of an instance passes the protocol check. A caller-written connector whose `destination` is a `str` is accepted, then loses every receipt after the run. A `send` that returns `None` becomes `unexpected:NoneType` with no cause.
- **Cancellation.** `CancelledError` swallowed into a FAILED receipt or wrapped in `OutputDeliveryError`.

## Historical Regressions

None in code yet: this pack was written red, before the implementation, from spec r3. The spec reviews found these failure mechanisms before any code existed, and the pack guards each: budget-stop notices posted as answers (R-2), a truncation marker leaking newlines into titles (R-4), the Jira link check rejecting every success (R-5), Notion mention tags (R-9), validator errors naming record fields instead of constructor parameters (R-12), and an unbounded trickling send (R-18). The S4 review of the first implementation then found defects the pack did not catch, and a test now guards each: the httpx request log printing URL credentials (S4 R-1), a non-enum `destination` and a non-receipt `send` result (R-2), sync `run()` held by the SMTP thread (R-3), a non-221 QUIT failing a delivered email (R-12), Jira, Linear, and Notion titles left untested (R-14), and `urlsplit` errors escaping as `ValueError` (R-15).

## Test Suite Map

- `test_output_connectors_acceptance.py`: the §4 snippet as written (AC-1), partial failure through `agent.run` (AC-5), schema violation sends nothing (AC-4), an agent without outputs is unchanged (AC-21), session recording and failure capture through `session.run` and through a direct `agent.run` on a bound agent (AC-23, INV-7). Start here for a caller-visible regression.
- `test_output_connectors_agent_wiring.py`: forks and `AgentTool` (AC-12), export and restore (AC-13), `JevAgentSettings.outputs` (AC-14), `CodingAgent` (AC-15), cancellation (AC-18), drained replies (INV-2, EC-20), capped runs (EC-43), user-written connectors (FR-5).
- `test_output_connectors_dispatch.py`: the skip rule (AC-8), content shaping, `render`, and a `send` that returns no receipt (AC-11, EC-16, EC-17), concurrency and order (AC-19), the deadline (AC-6 e), unexpected exceptions (EC-36), the error packet, resending (AC-24).
- `test_output_connectors_wire_contract.py`: each destination's documented request and receipt link (AC-17), link validation (D-21), mention neutralization (AC-9), Slack escaping after truncation, body caps and titles at every titled destination (AC-10, INV-14, INV-15, EC-18), the webhook's structured payload (EC-40).
- `test_output_connectors_http_failures.py`: retry policy (AC-6 a–d, INV-10), error-code grammar (AC-7, INV-11), redirects (AC-25), the response-size ceiling (EC-34).
- `test_output_connectors_email.py`: SMTP over STARTTLS and implicit TLS, failure mapping, refusal, the QUIT reply after acceptance (EC-48), sync `run()` at the deadline with a stalled session (NFR-2, EC-47), off-loop execution, sender rules (AC-16, EC-24 to EC-26).
- `test_output_connectors_configuration.py`: invalid configuration, including unparseable URLs and a non-enum `destination` (AC-20, EC-13, EC-14), credential resolution order (AC-2), the environment variable per destination (§9.3), duplicate and distinct instances (EC-15), rotation after construction (EC-37).
- `test_output_connectors_security.py`: the secret scan across every surface (AC-3), record reprs, cross-destination credential isolation, httpx's request log (EC-41), model output cannot steer the destination (INV-3), addressing arguments cannot steer credentials (D-19).
- `test_output_connectors_contract.py`: public names (FR-18), destination values, the protocol and base, receipt record rules (§9.1), layering (NFR-7), provider README and maps (AC-26).

Run everything with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`. The follow-up files are mapped under Follow-ups below.

## Omitted Testing Strategies

- **Live destinations and real credentials.** Forbidden. Every request stops at `HttpTransport._send_once` (or at `httpx.MockTransport`), and every SMTP session at a scripted client.
- **Property-based testing with a generator library.** No such library is a dependency, and adding one is out of scope. The algebraic rules (truncation length, single-line titles, the error-token grammar) are covered by explicit boundary tables instead.
- **Wall-clock performance.** AC-19's "under 0.35 s" is proven structurally: one connector cannot finish until the other has started, which only concurrent delivery allows.
- **`KeyboardInterrupt` during delivery (INV-20).** Raising it inside an event-loop task tears down the test's loop; `CancelledError` exercises the same `BaseException` path.
- **Stress and fuzz.** One reply fans out to at most a handful of connectors; nothing grows at runtime.
- **Accepted behaviors with no new code:** a specialist or aggregate proposer delivering on its own runs (EC-44, EC-45), receipts dropped from checkpoints (EC-28), `run_sequentially` stopping (EC-39), SES port 2465 (EC-46), a Teams 202 that never posts (EC-30).
- **Gates.** Lint, mypy, Semgrep, the public-API contract file, and `pyproject.toml` dependencies (AC-22, INV-27, INV-28) are proven by `python lint/run.py`, `scripts/run_ci.py`, and `scripts/generate-sdk-public-api.py --check`, not by pytest.

## Follow-ups (docs/spec/output-connector-followups, 2026-10-14)

### Feature Boundary

The follow-ups change what a connector puts on the wire and add five destinations, but not when or how often delivery runs: the dispatcher's skip rule, shaping, concurrency, receipt order, deadline, and error behave as above (INV-15). In scope:

- **Rendering:** Discord forum posts (`forum`, `forum_tags`), the Slack `markdown` block up to 12,000 characters, Telegram `sendRichMessage` with `topic_id`, the two-block Teams card, and Jira descriptions built by `OutputAdf.document`.
- **Webhook options:** fixed `headers=`, a `payload=` callable, and Standard Webhooks signing with `secret=`, which sends exact bytes through the new `HttpTransport` `content=` keyword.
- **Comment and append modes:** GitHub, Linear, and Jira `comment_on`; Linear and Jira `labels`; Notion `append_to`; and construction errors for every forbidden or missing combination.
- **New destinations:** `GitLabIssueOutput`, `GitHubJobSummaryOutput`, `ConfluencePageOutput`, `TypefullyDraftOutput`, and `HubSpotTaskOutput`.
- **GitHub update-in-place:** a sticky comment marked `<!-- vidbyte:<key> -->`, one issue per `vidbyte:<key>` label, reads before the single write, and marker neutralization.

Out of scope: every open question Q-1 to Q-8 (none is built, so no test expects a plain-text fallback after a Telegram 400 or a Slack 4xx, an author filter on markers, or a deadline budget check), Google Chat Markdown (D-24), OAuth, and any real vendor call.

### Failure Inventory

Each line is input + state → wrong output. The guarding test is in `docs/spec/output-connector-followups/test-plan.md`.

- **Rendering.** A long reply → a Slack `markdown` block over 12,000 characters, rejected on every send. `<!channel>` inside the block → a channel-wide ping. `<tg-button>` or `![](…)` in reply text → a real Telegram button or a fetched file. A Discord thread name with newlines or over 100 characters → 400. Forum tags on a non-forum webhook → accepted, then 400 on every send. A Teams body that repeats its title, or an empty body block. A Jira body with a heading or list sent as raw `#` and `-`, or an empty ADF text node, which Jira rejects.
- **Webhook options.** A header value or an invalid header name echoed in an error. `content-type` overridden by a caller header. A signature computed over a re-serialized body, which never verifies. A 429 retry that re-signs with a new id or timestamp. A short or non-base64 secret accepted. `json_body` and `content` both sent.
- **Comments and modes.** A comment on a PR and a new issue both created. Linear `errors[]` on 200 reported as SENT. A Jira comment link without `focusedCommentId`. A Notion append that replaces the page. `team_id` and `comment_on` both accepted, so the target is ambiguous.
- **New destinations.** A GitLab path not URL-encoded → 404. `host="gitlab.com/evil"` or `"bot@gitlab.com"` sends the token elsewhere. A job summary written on the event loop, interleaved by two threads, or into a newly created directory. A Confluence `value` sent as an object instead of a JSON string. A Typefully draft with `publish_at`, so it is published. A HubSpot `hs_timestamp` in local time or without milliseconds.
- **Update in place.** A write before the reads finish, or a second write after a failed PATCH. An eleventh page read. A read failure followed by a POST, which duplicates the comment. A read retried on 500. A forged marker in model output that another key's search then edits. A marker appended before truncation, so the cap cuts it off. A 1 MB page refused by the write ceiling. A redirect followed on a read. The httpx request log left on during reads and patches.

### Strategies Selected

- **Exact wire values at the real seam.** Every new request is asserted whole at `HttpTransport._send_once` (`fake_http`). Signed bytes, size ceilings, redirects, and the request log use the real `_send_once` over `httpx.MockTransport` (`httpx_destination`), whose route may be a callable when a host gets a GET and then a PATCH.
- **Boundary tables instead of property generators.** These cover the Slack 12,000/12,001 switch, every new cap at and one past its limit, and key length 42/43. Validation tables cover each new argument, and `OutputAdf.document` gets a block-rule table.
- **A real file and real threads for the job summary.** The file lives under `tmp_path` and goes through the real `LocalFileSystemBackend`. Which thread opened the file is recorded by a Python audit hook on the `open` event, so nothing in the write path is replaced. Two concurrent 200,000-character appends must use one non-loop thread and leave whole blocks.
- **Signatures recomputed with the standard library** from the recorded bytes and headers; the timestamp is bracketed, never frozen.
- **Regression guards, green by design:** the exact first-batch headers and no `content` for the ten first-batch HTTP connectors (AC-34), and the Slack escaped-text path above 12,000 characters.

### Strategies Omitted

- **Property-based generators.** Not a dependency; the tables above stand in.
- **Live checks L-1 to L-n.** These cover Slack mentions in the block, Telegram channel posting, Google Chat markup, and the other vendor behaviors marked A-n. They need real workspaces, so they stay manual.
- **Documented limits with no code:** the sticky and per-key races (EC-35, EC-36), labels dropped without push access (EC-37), the planted-marker branches (EC-42), the deadline cutting a read, a write, or a job-summary append (EC-38, EC-45, EC-46), and vendor-side rejections (EC-32 to EC-34). The deadline itself is already covered for every connector above.
- **Gates.** `scripts/generate-sdk-public-api.py --check` (AC-26), Semgrep, and lint are proven by their own commands, not by pytest.

### Follow-up Test Suite Map

- `test_output_connectors_followup_acceptance.py`: the follow-up §4 snippet run as written (AC-1), and the first-batch header guard (AC-34).
- `test_output_connectors_rendering.py`: Discord forum posts (AC-2, AC-3), Slack Markdown (AC-4, EC-6), Telegram rich messages (AC-5, AC-6, INV-18), Teams cards (AC-7), Jira ADF (AC-8) and the `OutputAdf.document` block table (D-10, EC-12 to EC-14).
- `test_output_connectors_webhook_options.py`: `headers=` (AC-10), `payload=` (AC-11, EC-18, EC-19), signing and retries (AC-12, AC-13, INV-8, EC-17), secret validation (AC-14), and the transport's `content=` (AC-15).
- `test_output_connectors_comments.py`: GitHub, Linear, and Jira `comment_on`, Linear and Jira `labels`, Notion `append_to` (AC-16 to AC-19, EC-22 to EC-25), and the forbidden combinations (AC-20, EC-41).
- `test_output_connectors_new_destinations.py`: GitLab (AC-21, EC-26, EC-27), the job summary (AC-22, EC-28 to EC-31), Confluence (AC-23), Typefully (AC-24), HubSpot (AC-25), titles (INV-13), and the `file_error` caution (AC-36).
- `test_output_connectors_update_in_place.py`: sticky comments (AC-27, AC-29, EC-39), marker rules (AC-31, FR-33, D-16), read failures (AC-28), keyed issues (AC-30), key and number checks (AC-32), read and patch transport rules (AC-33, EC-40), and the `OutputRead` and `OutputRequest` records.
- `test_output_connectors_followup_contract.py`: the new enums and class placement, `OutputResponses`, and the README, REPO_MAP, and first-spec documentation (AC-35).
