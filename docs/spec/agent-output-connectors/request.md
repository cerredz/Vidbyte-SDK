---
slug: agent-output-connectors
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-11 17:36
flags: none
---

# Request: Agent output connectors (deterministic delivery of an agent's reply to third-party destinations)

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening message of the conversation):

````text
recently had an idea for the  vidbyte-sdk/, and that is "output connectors". I want users to very easily be able to connect the output of their agent to a 3rd party provider  (github issue, slack channel, email, discord channel etc), and then bolt on this ability to their agent in 1 line using a key and we implement the under-the-hood functionality. How can we do this, what are a list of all platforms that we can do this for, and how are we going to handle credentials (in the vidbyte-cli./ we have a credential command system, im assuming that the api keys just have to go in the agent parameters,  but even do dont some  require oath?). And how do we actually implement something like this; one way I can see is taking in a user's api key, and then we simply tell the model after the user's request to use the mcp server to do X, and then determinstically pass teh structured output of the agent, or is there a better way. Consider multiple approaches and walk me through the best one
````

**Prompt 2** (after the assistant recommended deterministic SDK-native connectors):

````text
great, so lets assume no aoath token. can you show me a small code snippet of how someone would connect an output connector and the psuedocode of how that connector would be implemented?
````

**Prompt 3** (after the assistant showed the usage snippet and connector pseudocode):

````text
but how do they upload their credentials to the agent in the params? or is this done another way?
````

**Prompt 4** (the pipeline invocation, after the assistant explained credential resolution):

````text
/spec-pipeline Great, i want you to start with creating a spec and implementing this feature inside of the vidbyte-sdk/ repo. i think that I want this abstraction to live inside of the vidbyte-sdk/vidbyte/agents/output folder, and for all of the provider specific logic they can either go in the lib folder of the repo or the provider folder of the repo, and then our output folder and be responsible for the core logic kind of linking the provider and agent logic, and then of course we bolt the parameter on our BaseAgent (and I think we can bolt it only our JevAgent and CodingAgent as well). What i also want you to do in the spec is come up with a list of popular platforms that we implement like the example above  (without an oauth token) to also integrate with this output connector features (platforms like microsoft teams, gmail, slack, discord, notion, etc come to mind. But double check these and find more examples where we can store agent outputs), want implementation to not be overengineers, clean, modular, and elegant.  best of luck to you kid (will be comparing your output with gpt 6.1 astra)
````

## B. Handoff block and decision ledger (verbatim, if present)

No `## HANDOFF` block was produced (the user invoked this pipeline instead of replying "go"). The last Re-entry card's `Decided:` ledger, verbatim (written by the assistant immediately before Prompt 4; the user replied "Great" and invoked the pipeline):

````text
Decided: deterministic SDK-native connectors set with `outputs=[...]`; delivery runs after the schema check and is shared by `BaseAgent` and `CodexHarnessAgent`; no OAuth. Credentials live on the connector: an explicit argument, else an environment variable, resolved by `OutputCredentials.resolve` (copied from `ModelRegistry.resolve_api_key`), validated at construction, never serialized or sent to Vidbyte. Retries happen only on 429 or when the provider accepts an idempotency key.
Open: whether Slack's `markdown` block works on incoming webhooks; whether the CLI's GitHub link token can write issues.
Needs you:
1. Which destinations are in v1? Default: Slack webhook, Discord webhook, GitHub issue, SMTP email, signed generic webhook.
2. What happens when a delivery fails? Default: raise `OutputDeliveryError` after the turn is recorded, with the reply and receipts attached.
````

Prompt 4 supersedes parts of that ledger: (a) placement is now `vidbyte/agents/output/` for the abstraction plus provider-specific logic in `vidbyte/lib/` or `vidbyte/providers/` (the ledger's earlier proposal was a top-level `vidbyte/outputs/` package); (b) the parameter goes on `BaseAgent`, `JevAgent`, and `CodingAgent` (the ledger said `BaseAgent` + `CodexHarnessAgent`); (c) "Which destinations are in v1?" is answered by Prompt 4: a researched list of popular non-OAuth platforms that the PR implements.

## C. Structured conversation notes

### Key decisions
- **Deterministic delivery, not model-driven delivery.** The model *authors* the content (through `output_schema` fields or plain text); ordinary SDK code *delivers* it after the run finishes. The model never holds the credential and never chooses the destination. — Reasoning: delivery must happen exactly once, to the configured destination; a model with a write token reading untrusted input is a prompt-injection channel; MCP tool schemas cost tokens every iteration; model-driven posting happens inside the loop, before the output schema is validated. The user accepted this ("great", Prompt 2; "Great", Prompt 4).
- **No OAuth.** Prompt 2: "lets assume no aoath token". Every connector in this PR uses a credential the user pastes (webhook URL, API key/token, bot token, SMTP credentials). Destinations that only work with OAuth are out of scope (listed as researched-but-excluded).
- **One parameter on the agent: `outputs=[...]`**, a sequence of connector objects, e.g. `Agent(..., outputs=[SlackOutput(), GitHubIssueOutput(repo="acme/shop")])`. The user's goal (Prompt 1): "bolt on this ability to their agent in 1 line using a key and we implement the under-the-hood functionality".
- **Placement (Prompt 4, user decision):** "this abstraction to live inside of the vidbyte-sdk/vidbyte/agents/output folder"; "all of the provider specific logic they can either go in the lib folder of the repo or the provider folder of the repo"; "our output folder [...] be responsible for the core logic kind of linking the provider and agent logic". Dataclasses, enums and constants still follow AGENTS.md Placement Rules (`vidbyte/lib/dataclasses/<domain>.py`, `vidbyte/lib/enums/<domain>.py`, `vidbyte/lib/constants/<domain>.py`). The choice between `vidbyte/lib/` and `vidbyte/providers/` for provider-specific logic is left to the spec, constrained by the layering rule (`vidbyte/lib/` never imports a higher layer).
- **Which agents get the parameter (Prompt 4, user decision):** "we bolt the parameter on our BaseAgent (and I think we can bolt it only our JevAgent and CodingAgent as well)" — read "only" as "onto": `BaseAgent`, `JevAgent`, `CodingAgent`.
- **Credentials live on the connector, not on `Agent(...)`.** Resolution order copies `ModelRegistry.resolve_api_key` (`vidbyte/lib/registries/models.py:152`): an explicit constructor argument wins; else a documented per-destination environment variable; else `ConfigurationError` naming the variable (never the value). Whitespace is stripped. Resolved and validated when the connector is constructed (fail before a long run, not after). Never logged, never in `repr`, never serialized into `RunState`/traces/settings, never sent to Vidbyte; only ever sent to the destination itself. The SDK never reads the vidbyte-cli keyring (the CLI may later pass values in; not part of this PR). — Reasoning: the agent object is serialized in several places (`RunState` export/`restore()`, fork settings, traces, agent-run-sync settings); the connector can mask and exclude its own secret.
- **Lifecycle position:** delivery runs in `BaseAgent`'s reply path *after* `_assert_schema_satisfied(result)` and *before* queued follow-up prompts drain, so only a validated reply ever leaves the process. Sibling pattern: `_run_auto_handoff` (a post-reply side effect configured by one constructor parameter, recorded into reply metadata).
- **Content shaping rule:** each destination has a typed payload (issue: title/body/labels; email: subject/body; chat: text). Fill it by: (1) same-named fields of `reply.structured` (works with pydantic models, dataclasses, or mappings); else (2) derive from text — title = first non-empty line with leading `#` stripped and length-capped, body = full output; (3) a `render=` callable (`AgentMessage -> payload`) replaces both rules.
- **Retries only where a duplicate is impossible.** Retry on HTTP 429 only (`retry_status_codes=(429,)`), because a rate-limited request was not processed. Timeouts and 5xx are reported as failures, not retried (the first post may have landed). Providers that accept an idempotency key (e.g. Resend `Idempotency-Key`, Linear client-chosen issue `id`, PagerDuty `dedup_key`) may retry fully.
- **Receipts:** every connector returns a `DeliveryReceipt(destination, status, url=None, error_code=None)` with status `SENT | FAILED | SKIPPED`; receipts are recorded in `reply.metadata["deliveries"]` in configured order. `error_code` is an HTTP status plus a short provider code (e.g. `http_404:channel_not_found`) or `network` — never the request URL, never exception text.
- **Failure behavior (proposed default, the user never objected):** attempt every output; if any failed, raise `OutputDeliveryError` after the turn is recorded, carrying the reply and all receipts, with `.failed`. Callers can resend only the failed connectors. — Reasoning: the realistic failure is a revoked webhook on a scheduled agent; a quiet metadata entry would hide it for weeks.
- **Concurrent delivery:** all outputs for one reply are sent concurrently (`asyncio.gather`); receipts keep configured order; a per-connector timeout constant (about 10 s) bounds the added latency.
- **Safety of delivered content:** suppress mass mentions (Discord `allowed_mentions: {"parse": []}`; escape `<`, `>`, `&` in Slack text) so model output quoting "@everyone" can never ping a server.
- **Skips:** an empty reply (no text, no structured value) or a middleware-aborted reply delivers nothing (receipt `SKIPPED`).
- **Composition edges:** forks do not inherit outputs; `restore()` accepts `outputs=` like it accepts `middleware=` (outputs are never serialized); an agent used through `as_tool` delivers on every call (documented, not prevented).
- **Implementation quality bar (Prompt 4):** "not be overengineers, clean, modular, and elegant." Each destination is small: shape the payload, send it, return a receipt.

### Rejected alternatives
- **Tell the model to call an MCP server to deliver** (the user's first idea in Prompt 1) — nondeterministic (skip/duplicate/wrong channel/post before finishing), runs before `_assert_schema_satisfied` so schema-invalid output can be posted, gives a write-capable token to a model reading untrusted input, costs tokens every iteration, and the SDK's relevant MCP presets are broken: the Discord, SendGrid, Resend, Telegram and webhook presets in `vidbyte/lib/config/mcp_presets.py` run `python -m mcp_server_<name>` and every one of those package names returned 404 on PyPI (checked 2026-10-11); `@modelcontextprotocol/server-slack` is marked "Package no longer supported" on npm. MCP stays the right tool when the model must *decide* an action mid-run (that is a tool, not an output connector).
- **An `after_run` middleware** — `MiddlewareContext` (`vidbyte/lib/dataclasses/middleware.py:160`) has no result field (only `provider_messages`); `_finish_result` (`vidbyte/agents/runtime.py:838`) runs before the `AgentMessage` is built and before the schema check; the MCTS and actor runtimes reject middleware (`vidbyte/agents/base.py` ~line 128); middleware's continue/abort decision model does not fit "send and return a link". Flip condition: if `after_run` moved after schema validation and received the final `AgentMessage`.
- **Wrapping Apprise** (BSD-2-Clause, v2.0.1) as the engine — credentials embedded in URL strings leak through logs/traces/exceptions; no GitHub issues or Linear; no receipts/links; brings its own HTTP stack, against REPO_MAP's rule that nothing outside `vidbyte/lib/http/` reaches for an HTTP client; a new dependency.
- **Hosted broker / OAuth (Composio, Pipedream Connect, Nango, Arcade model)** — out of scope: the user chose no OAuth (Prompt 2).
- **A credential parameter on `Agent(...)`** — the agent is serialized in several places; the secret would leak unless every path excluded it.
- **A `webhook_url_env=` knob** — one more setting with no use that `os.environ[...]` in user code does not cover.
- **A `Secret` wrapper class** — one caller; a private attribute plus a masked `__repr__` does the job.
- **Passing transport error text into receipts** — `ProviderRequestError` from `HttpTransport` carries `response_excerpt=str(exc)`, which can contain the request URL; for webhooks the URL is the secret.

### Constraints and assumptions
- All outbound HTTP goes through `vidbyte/lib/http/transport.py` (`HttpTransport.request`); REPO_MAP: "Nothing else in the package should reach for an HTTP client directly outside of this layer." Email over SMTP may use the standard library (`smtplib`, run off the event loop).
- No new runtime dependency (Apprise was rejected partly for this; the assistant's design used stdlib `smtplib` for email "so no new dependency").
- `HttpTransport.request` refuses to retry a POST unless `idempotency_key` is supplied (`_require_idempotency_guard`, line ~22); the key is only a guard — it is NOT sent to the server as a header. Its backoff is exponential from 0.5 s and ignores `Retry-After`. Its default `retry_status_codes` include 500–504, so connectors must pass `retry_status_codes=(429,)` explicitly where duplicates are possible.
- `AgentMessage` (`vidbyte/lib/dataclasses/agents.py:269`) is frozen but its `metadata` is the same dict `generate_reply` built, so writing `metadata["deliveries"]` after the reply exists works (`_run_auto_handoff` already does `metadata["handoff"] = produced`).
- The SDK does not load `.env` files; users load them themselves.
- AGENTS.md: dataclasses in `vidbyte/lib/dataclasses/<domain>.py`; enums in `vidbyte/lib/enums/<domain>.py` exported from `vidbyte/lib/enums/__init__.py`; constants in `vidbyte/lib/constants/`; agent `*Settings` classes may live with the agent; call chains one level deep; narrated main functions; validated frozen dataclasses for core inputs/outputs; files well under 1,000 lines; full gate `python scripts/run_ci.py` before complete; `docs/` is opaque.
- Owner preference (from prior sessions): never add CLI commands to the SDK; "a way to run something" means its Python API.
- Research facts gathered in the conversation (2026-10-11): Microsoft Teams' Office 365 connector incoming webhooks are retired; the replacement is a Workflows (Power Automate) webhook URL taking an Adaptive Card payload. Resend supports an `Idempotency-Key` header on `POST /emails` (24 h window; `Resend-Idempotency-Key` header over SMTP). Linear: personal API key in header `Authorization: <key>` (no `Bearer`); `IssueCreateInput.id` accepts a client-chosen UUIDv4. Discord rejects message `content` over 2,000 characters. A GitHub issue body tops out at 65,536 characters. Telegram messages cap at 4,096 characters. Slack's newer `markdown` block accepts standard markdown, but whether incoming webhooks accept it was not verified.

### Clarifications and answers
- Q (Prompt 1): "even do dont some require oath?" — A (assistant): some destinations do (sending as a person via Gmail/Outlook API, writing to a person's Docs/Drive, one-click installs into other people's workspaces), but none of Slack/Discord/GitHub issue/email need OAuth when the developer sends into a workspace they control. Then Prompt 2: "lets assume no aoath token."
- Q (Prompt 1): "im assuming that the api keys just have to go in the agent parameters" — A (assistant): the key goes on the connector (constructor parameter or env var), the same way model keys work; not on `Agent(...)`.
- Q (Prompt 3): "how do they upload their credentials to the agent in the params? or is this done another way?" — A (assistant): nothing is uploaded; the SDK runs in the user's process; the credential is a connector constructor argument or an environment variable (e.g. `SLACK_WEBHOOK_URL`, `GITHUB_TOKEN`) set locally, in CI secrets, or by the hosting platform. Two destinations of the same kind use explicit arguments. The user replied "Great" and invoked this pipeline.
- Q (assistant, "Which destinations are in v1?") — A: superseded by Prompt 4: "come up with a list of popular platforms that we implement like the example above (without an oauth token) [...] (platforms like microsoft teams, gmail, slack, discord, notion, etc come to mind. But double check these and find more examples where we can store agent outputs)".
- Q (assistant, "What happens when a delivery fails?") — not explicitly answered; the proposed default (raise `OutputDeliveryError` after the turn is recorded) stands.

### Terminology
- **Output connector** — a user-instantiated object (e.g. `SlackOutput(...)`) that sends a finished agent reply to one third-party destination. Passed in `outputs=[...]`.
- **Destination** — the third-party target kind (Slack, Discord, GitHub issue, email, ...); a closed set, so an enum.
- **Authoring vs delivery** — authoring = the model writing the content; delivery = code choosing the destination, holding the credential, sending, handling limits and failures.
- **Delivery receipt** — the per-connector result record: destination, status (`SENT`/`FAILED`/`SKIPPED`), optional link, optional error code.
- **Render** — a user-supplied callable that turns an `AgentMessage` into a destination's payload, overriding the default shaping rule.
- **Gmail** (Prompt 4) — without OAuth, Gmail is reachable only via SMTP with an app password (requires 2-Step Verification); the spec must double-check this.

### Implementation hints
- Usage shape the user approved (assistant-written, Prompt 2 answer):

````python
from pydantic import BaseModel
from vidbyte import Agent
from vidbyte.outputs import GitHubIssueOutput, SlackOutput   # import path will follow the agents/output placement

class BugReport(BaseModel):
    title: str
    body: str

agent = Agent(
    name="checkout-scout",
    system_prompt="Find the worst bug in the checkout flow.",
    provider="openai",
    model_name="gpt-4.1",
    output_schema=BugReport,                                   # the model writes title + body
    outputs=[
        SlackOutput(),                                         # reads SLACK_WEBHOOK_URL
        GitHubIssueOutput(repo="acme/shop", labels=("bug",)),  # reads GITHUB_TOKEN
    ],
)

reply = agent.run("Scan checkout")
reply.metadata["deliveries"]
# (DeliveryReceipt(destination=SLACK, status=SENT),
#  DeliveryReceipt(destination=GITHUB_ISSUE, status=SENT, url="https://github.com/acme/shop/issues/412"))

try:
    reply = agent.run("Scan checkout")
except OutputDeliveryError as err:
    reply = err.reply
    for receipt in err.failed:
        log.warning("delivery to %s failed: %s", receipt.destination, receipt.error_code)
````

- Connector pseudocode the user approved (assistant-written, Prompt 2 answer; names indicative, placement must follow Prompt 4):

````python
class OutputConnector(ABC):
    destination: ClassVar[OutputDestination]

    def __init__(self, *, render=None):
        self._render = render

    async def deliver(self, reply: AgentMessage, delivery_key: str) -> DeliveryReceipt:
        # Skip a reply with nothing in it, so a channel never gets an empty post.
        if not reply.content.strip() and reply.structured is None:
            return DeliveryReceipt(self.destination, DeliveryStatus.SKIPPED)
        # Shape the reply into this destination's message: the user's render wins, else the default rule.
        payload = self._render(reply) if self._render else self._default_payload(reply)
        # Send it. A network failure becomes a receipt, not an exception, so the other outputs still go out.
        try:
            return await self._send(payload, delivery_key)
        except ProviderRequestError:
            # The error text can contain the request URL, which for a webhook is the secret; keep only a code.
            return DeliveryReceipt(self.destination, DeliveryStatus.FAILED, error_code="network")

    @abstractmethod
    def _default_payload(self, reply: AgentMessage) -> object: ...
    @abstractmethod
    async def _send(self, payload: object, delivery_key: str) -> DeliveryReceipt: ...

class ReplyText:   # field picking lives in its own small class so the one-hop call-chain rule holds
    @staticmethod
    def field(reply, name) -> str | None: ...      # same-named field from structured (model object or dict)
    @staticmethod
    def first_line(reply) -> str: ...              # first non-empty line, leading '#' stripped

class SlackOutput(OutputConnector):
    destination = OutputDestination.SLACK
    def __init__(self, *, webhook_url=None, render=None):
        super().__init__(render=render)
        self.__webhook_url = OutputCredentials.resolve(OutputDestination.SLACK, webhook_url)  # + prefix check "https://hooks.slack.com/"
    def __repr__(self): return "SlackOutput(webhook_url=***)"
    def _default_payload(self, reply): return SlackMessage(text=SlackEscaper.escape(ReplyText.field(reply, "text") or reply.content))
    async def _send(self, message, delivery_key):
        response = await HttpTransport().request(method="POST", url=self.__webhook_url,
            headers={"Content-Type": "application/json"}, json_body={"text": message.text},
            timeout_seconds=OUTPUT_TIMEOUT_SECONDS, retry_count=OUTPUT_RATE_LIMIT_RETRIES,
            retry_status_codes=(429,), idempotency_key=delivery_key)
        # 200 -> SENT (webhooks return no link); else FAILED with f"http_{status}:{body[:40]}"

class GitHubIssueOutput(OutputConnector):   # POST https://api.github.com/repos/{owner}/{repo}/issues, Bearer token
    # _default_payload: title = ReplyText.field(reply,"title") or ReplyText.first_line(reply); body = field "body" or content; caps
    # _send: 201 -> SENT with url=html_url; else FAILED http_<status>

class OutputCredentials:   # mirrors ModelRegistry.resolve_api_key
    @staticmethod
    def resolve(destination, explicit) -> str: ...   # explicit.strip() > os.environ[OUTPUT_CREDENTIAL_ENV_VARS[destination]].strip() > ConfigurationError naming the variable

class OutputDispatcher:
    async def deliver(self, reply) -> DeliveryReport:   # gather all connectors, each with uuid4().hex key; report.failed

# BaseAgent reply path, after self._assert_schema_satisfied(result):
#     report = await self._dispatcher.deliver(reply); metadata["deliveries"] = report.receipts
#     if report.failed: raise OutputDeliveryError(reply=reply, report=report)
````

- Files named in the conversation (verify; line numbers as of 2026-10-11 main):
  - `vidbyte/agents/base.py` — `BaseAgent.__init__` (~81–115, keyword-only params incl. `middleware`, `output_schema`, `handoff`, `fallback`); reply path (~900–934: builds `AgentMessage`, appends history, `_run_auto_handoff`, `_notify_session`, `_assert_schema_satisfied`, queued-prompt drain); `_assert_schema_satisfied` (~947); `_run_auto_handoff` (~1136); `_export_output_schema`/`restore()` (~539–570, 686–733).
  - `vidbyte/agents/runtime.py` — `_finish_result` (~838) runs `after_run` middleware.
  - `vidbyte/agents/jev/agent.py` — `class JevAgent(BaseAgent)`; JEV capabilities are named validated fields on `JevAgentSettings` (AGENTS.md "New JEV code").
  - `vidbyte/agents/coding.py` — `CodingAgent` (base class not yet checked).
  - `vidbyte/agents/codex/agent.py` — `CodexHarnessAgent` is NOT a `BaseAgent` subclass; settings object `CodexHarnessAgentSettings`; returns `AgentMessage` too.
  - `vidbyte/agents/fork.py` (~59–77) — copies middleware, output_schema, handoff to forks.
  - `vidbyte/lib/dataclasses/agents.py:269` — `AgentMessage(sender, recipient, content, message_type, metadata, structured, codex)`.
  - `vidbyte/lib/http/transport.py` — `HttpTransport.request(...)`, `HttpResponse(status_code, body, headers, raw_bytes, attempts)`, POST retry guard.
  - `vidbyte/lib/registries/models.py:152` — `ModelRegistry.resolve_api_key` (the credential-resolution sibling), `API_KEY_ENV_VARS`.
  - `vidbyte/lib/errors/base.py` — `ConfigurationError` (~235), `ProviderRequestError` (~247).
  - `vidbyte/middleware/builtins/` — shape sibling for "user-instantiated behavior class configured by constructor kwargs".
  - `vidbyte/sources/` — the inbound analog (documents in), for naming symmetry.
  - `vidbyte/providers/` — exists; REPO_MAP says it is about model providers (the user named it as a possible home for provider-specific output logic).
  - `vidbyte/lib/config/mcp_presets.py` / `vidbyte/tools/mcp/presets.py` — do NOT build on these; broken presets are a separate issue.
- Platform credential facts from the conversation (to be double-checked by the spec): Slack incoming webhook URL; Discord channel webhook URL; GitHub fine-grained PAT (Issues: read & write) or Actions `GITHUB_TOKEN` with `permissions: issues: write`; email via SMTP URL (Resend, SendGrid, Postmark, SES, Gmail app password); generic webhook URL + optional HMAC secret (reaches Zapier/Make/n8n/Pipedream); Microsoft Teams Workflows webhook URL (Adaptive Card); Google Chat space webhook URL; Linear personal API key; Telegram bot token + chat id; Jira Cloud email + API token; Notion internal integration secret (page must be shared with the integration); PagerDuty Events v2 routing key; Mattermost/Rocket.Chat Slack-compatible webhook; Twilio SID + auth token; Google Sheets via service-account key (would need JWT signing); Airtable/Asana/monday.com/ClickUp/HubSpot personal or private-app tokens; ntfy topic URL; Pushover app + user key. OAuth-only (excluded): Gmail/Outlook API send-as-user, Google Docs/Drive as the user, Salesforce, X, LinkedIn, multi-workspace "Add to Slack".

### Open questions
- Does `CodexHarnessAgent` also get the parameter? The assistant's ledger included it (every vidbyte-cli agent is built on it), but Prompt 4 names only `BaseAgent`, `JevAgent`, `CodingAgent`. Resolve from the code (e.g. whether `CodingAgent` is built on `CodexHarnessAgent`) or carry as a `Q-n` whose default follows Prompt 4's list.
- `vidbyte/lib/` vs `vidbyte/providers/` for provider-specific logic, and how the base contract is placed so no lower layer imports a higher one.
- Which researched platforms are implemented in this PR vs listed as researched-but-excluded (and why), under "not over-engineered" and "no new dependency".
- Exact environment-variable name per destination.
- Whether Slack incoming webhooks accept the `markdown` block (else use `text`).
- How `JevAgent` receives the parameter (constructor pass-through vs a `JevAgentSettings` field) per AGENTS.md "New JEV code".
- Whether declarative YAML config (`vidbyte/config/`) must accept `outputs` (default: no, Python API only, unless a repo rule forces parity).
- How a middleware-aborted reply is detected (for the `SKIPPED` rule).

## D. Weighted words

- "I want users to very easily be able to connect the output of their agent to a 3rd party provider" — Prompt 1
- "bolt on this ability to their agent in 1 line using a key and we implement the under-the-hood functionality" — Prompt 1
- "what are a list of all platforms that we can do this for" — Prompt 1
- "determinstically pass teh structured output of the agent" — Prompt 1
- "for all of the provider specific logic they can either go in the lib folder of the repo or the provider folder of the repo" — Prompt 4
- "of course we bolt the parameter on our BaseAgent" — Prompt 4
- "come up with a list of popular platforms that we implement like the example above  (without an oauth token)" — Prompt 4
- "But double check these and find more examples where we can store agent outputs" — Prompt 4
- "want implementation to not be overengineers, clean, modular, and elegant" — Prompt 4
- "lets assume no aoath token" — Prompt 2
