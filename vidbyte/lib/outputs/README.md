# Output Providers

This folder holds the provider classes that send a finished agent reply's
title and body to one destination each: Slack, Discord, Microsoft Teams,
Google Chat, Telegram, email over SMTP, GitHub Issues, Linear, Jira Cloud,
Notion, and any HTTPS webhook. It does provider work only: reading the
credential, building the destination's request, suppressing channel-wide
mentions, applying the destination's length cap, and turning the response
into a `DeliveryReceipt`.

The `OutputConnector` contract, the rule for which replies are delivered, the
default title and body shaping, and the dispatcher that runs every connector
live in [`vidbyte/agents/output/`](../../agents/output/README.md). Attach
connectors with `Agent(..., outputs=[...])`; nothing here decides when a reply
is sent.

## Non-goals

- **No OAuth.** Every destination takes one pasted credential: a webhook URL,
  a token, an API key, or an SMTP password. Destinations that only accept
  OAuth (the Gmail API, Microsoft Graph, Google Sheets, and similar) are not
  here.
- **No MCP delivery, no YAML configuration, and no CLI commands.** Connectors
  are built in Python and passed to the agent.
- **No retries beyond HTTP 429.** A 429 is retried at most
  `OUTPUT_RATE_LIMIT_RETRIES` extra times. Nothing else is retried, because a
  duplicate post is worse than a reported failure. There is no outbox, queue,
  or resend helper.

## Modules

- `base.py`: `BaseOutput`, the abstract base every connector extends (a masked
  `repr` and the optional `render` hook), and `OutputArguments`, the shared
  constructor checks (credential lookup, `https://` URLs, identifiers).
- `text.py`: `OutputText`, the plain-text helpers: first line, chat text,
  truncation with a marker, and one-line titles.
- `delivery.py`: `OutputHttp`, the single JSON `POST` through `HttpTransport`
  that maps a response to a receipt, and `OutputSmtp`, the single SMTP send.
- `slack.py`: `SlackOutput`, an incoming-webhook message.
- `discord.py`: `DiscordOutput`, a channel-webhook message with every mention
  suppressed.
- `teams.py`: `TeamsOutput`, an Adaptive Card posted to a Workflows webhook.
- `google_chat.py`: `GoogleChatOutput`, a space-webhook message.
- `telegram.py`: `TelegramOutput`, a bot `sendMessage` call.
- `email.py`: `EmailOutput`, one plain-text email over SMTP.
- `github.py`: `GitHubIssueOutput`, a new GitHub issue.
- `linear.py`: `LinearIssueOutput`, a new Linear issue through GraphQL.
- `jira.py`: `JiraIssueOutput`, a new Jira Cloud issue.
- `notion.py`: `NotionPageOutput`, a new Notion page under a parent page.
- `webhook.py`: `WebhookOutput`, a JSON `POST` to any HTTPS receiver
  (Make, n8n, Pipedream, Zapier, Power Automate).
- `__init__.py`: exports the connectors and the provider helpers.

## Provider Reference

Each connector reads its credential from the argument first, then from the
environment variable below. The SDK never loads a `.env` file. Body caps are
in characters; longer text is cut and ends with a truncation marker.

| Destination | Connector | Credential (environment variable) | How to get it; least privilege | Body cap | Official docs | Retrieved |
| --- | --- | --- | --- | --- | --- | --- |
| Slack | `SlackOutput(webhook_url=None)` | Incoming webhook URL (`SLACK_WEBHOOK_URL`) | App settings, then Incoming Webhooks, then Add New Webhook, then choose a channel. The URL posts only to that channel. | 40,000 | [Incoming webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/) | 2026-10-11 |
| Discord | `DiscordOutput(webhook_url=None)` | Channel webhook URL (`DISCORD_WEBHOOK_URL`) | Channel settings, then Integrations, then Webhooks. The URL posts only to that channel. | 2,000 | [Webhook resource](https://docs.discord.com/developers/resources/webhook) | 2026-10-11 |
| Microsoft Teams | `TeamsOutput(webhook_url=None)` | Workflows webhook URL (`TEAMS_WEBHOOK_URL`) | In the channel, open Workflows and choose "Send webhook alerts to a channel", with "Who can trigger" set to **Anyone**. | 7,000 | [Teams connector](https://learn.microsoft.com/en-us/connectors/teams/) | 2026-10-11 |
| Google Chat | `GoogleChatOutput(webhook_url=None)` | Space webhook URL (`GOOGLE_CHAT_WEBHOOK_URL`) | Space, then Apps & integrations, then Add webhooks. Google Workspace Business or Enterprise only. | 8,000 | [Webhooks quickstart](https://developers.google.com/workspace/chat/quickstart/webhooks) | 2026-10-11 |
| Telegram | `TelegramOutput(chat_id, bot_token=None)` | Bot token (`TELEGRAM_BOT_TOKEN`) | Create the bot with @BotFather, then add it to the chat. | 4,096 | [Bot API](https://core.telegram.org/bots/api) | 2026-10-11 |
| Email (SMTP) | `EmailOutput(to, host, username, password=None, sender=None, port=587)` | SMTP password (`SMTP_PASSWORD`) | A provider SMTP credential; see Email Providers below. Prefer a send-only credential where the provider offers one. | none | [Python smtplib](https://docs.python.org/3/library/smtplib.html) | 2026-10-11 |
| GitHub Issues | `GitHubIssueOutput(repo, labels=(), token=None)` | Token (`GITHUB_TOKEN`) | A fine-grained personal access token with the repository permission Issues set to write, or in Actions `GITHUB_TOKEN` with `permissions: issues: write`. | 65,536 | [Create an issue](https://docs.github.com/en/rest/issues/issues#create-an-issue) | 2026-10-11 |
| Linear | `LinearIssueOutput(team_id, api_key=None)` | Personal API key (`LINEAR_API_KEY`) | Settings, then Account, then Security & Access. Limit the key to "Create issues" on the teams it posts to. | none documented | [GraphQL API](https://linear.app/developers/graphql) | 2026-10-11 |
| Jira Cloud | `JiraIssueOutput(site, project, email, issue_type="Task", api_token=None)` | API token (`JIRA_API_TOKEN`) | id.atlassian.com, then API tokens. The account needs only Browse projects and Create issues. | 32,767 | [Basic auth for REST APIs](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/) | 2026-10-11 |
| Notion | `NotionPageOutput(parent_page_id, api_key=None)` | Integration token or personal access token (`NOTION_API_KEY`) | An internal integration shared with only the parent page (•••, then Add connections), or a personal access token, which acts as you. | none documented | [Create a page](https://developers.notion.com/reference/post-page) | 2026-10-11 |
| Generic webhook | `WebhookOutput(url=None)` | Receiver URL (`VIDBYTE_OUTPUT_WEBHOOK_URL`) | The automation tool creates the URL. The request is unsigned, so keep the URL unguessable. | none | [Make webhooks](https://help.make.com/webhooks) | 2026-10-11 |

Retrieved 2026-10-11. Provider limits, API versions, and setup screens change;
re-check the linked pages before changing a connector.

### Email Providers

`EmailOutput` covers every provider that accepts SMTP with a username and
password. Port 465 uses implicit TLS; any other port uses STARTTLS.
Set `sender` when the username is not an email address.

| Provider | Credential notes | Docs |
| --- | --- | --- |
| Gmail | `smtp.gmail.com`, port 465 or 587, with an **app password** | [App passwords](https://support.google.com/accounts/answer/185833) |
| Google Workspace | App passwords only if the admin allows them; 2,000 messages a day | [Sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace) |
| Microsoft 365 | SMTP AUTH works until December 2026, then is off by default | [Authenticated SMTP](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission) |
| Resend | Username `resend`; set `sender` | [SMTP](https://resend.com/docs/send-with-smtp) |
| SendGrid | Username `apikey`; set `sender` | [SMTP API](https://www.twilio.com/docs/sendgrid/for-developers/sending-email/integrating-with-the-smtp-api) |
| Postmark | STARTTLS only (ports 25, 2525, 587) | [SMTP](https://postmarkapp.com/developer/user-guide/send-email-with-smtp) |
| Amazon SES | A region-specific SMTP password; port 465 or 587 | [SMTP credentials](https://docs.aws.amazon.com/ses/latest/dg/smtp-credentials.html) |
| Mailgun | Per-domain SMTP credentials | [Send over SMTP](https://documentation.mailgun.com/docs/mailgun/user-manual/sending-messages/send-smtp) |

## How To Add A Destination

1. Add a member to `OutputDestination` in `vidbyte/lib/enums/outputs.py`.
2. Add its environment variable to `OUTPUT_CREDENTIAL_ENV_VARS`, and any cap,
   URL, or version to `vidbyte/lib/constants/outputs.py`.
3. Add one module here with one `BaseOutput` subclass that has only
   `__init__` and `send`. Check every argument in `__init__` with
   `OutputArguments`, and send through `OutputHttp.post` or `OutputSmtp.send`
   so status codes, timeouts, and secrets are handled in one place.
4. Export it from this folder's `__init__.py`, from `vidbyte.agents.output`,
   and from the root `vidbyte` package, then regenerate the public API
   contract.
5. Add a row to the Provider Reference table above with its retrieval date.

## Footguns

- **Teams:** only flows whose trigger allows **Anyone** work; tenant-auth
  flows need OAuth. A 202 response means the flow accepted the request, not
  that the message was posted.
- **Gmail:** an app password needs 2-Step Verification, and it is unavailable
  when security keys are enforced.
- **GitHub:** labels are silently dropped unless the token's user has push
  access to the repository.
- **Notion:** an internal integration sees only pages shared with it; share
  the parent page first.
- **Jira:** API tokens expire within 365 days. Scoped API tokens are not
  supported, because they need a different host.
- **Slack:** an incoming webhook URL cannot be deleted once it is created, so
  treat it as a long-lived secret.
- **Amazon SES:** SMTP passwords are region-specific, and SES's implicit-TLS
  port 2465 is not supported; use 465 or 587.
- **Postmark:** STARTTLS only, so port 465 fails.
- **Environment:** the SDK does not load `.env`; export the variables or pass
  the credential explicitly.
- **Skipped runs:** a run stopped by a budget, guard, or middleware, or one
  with a blank reply, is skipped: every receipt is SKIPPED and nothing is
  sent.
- **Sub-agents:** a user agent with outputs delivers on its own runs even when
  used as a Jev specialist, an AggregateAgent proposer or aggregator, a
  pipeline or workflow stage, or an MCP-served agent. Forks never deliver.
- **Delegated receipts:** a JevAgent's delegated reply carries the
  specialist's `deliveries`, and an AggregateAgent proposer whose delivery
  fails counts as a failed proposer.
- **Personal mentions:** GitHub `@user` and `@org/team`, and Telegram
  `@username`, in the delivered text notify the named person. Only
  channel-wide and mass mentions are suppressed.
- **Deadline:** a destination that has not answered within
  `OUTPUT_DELIVERY_DEADLINE_SECONDS` is FAILED `network`, but an SMTP send may
  still finish afterwards. The SMTP session runs on its own worker thread, not
  the loop's default executor, so `run()` returns at the deadline instead of
  waiting for it; the interpreter still waits for that thread at exit. If a
  FAILED receipt's `error_code` is `network`, `invalid_response`,
  `smtp_error`, or `smtp_recipients_refused`, or starts with `http_5`, that
  output may already have been delivered, so check its destination before
  resending it.
- **Restored sessions:** `Session.resume` and `fork_from` return agents with
  `outputs=()`; pass `outputs=` to `BaseAgent.restore` to deliver again.
