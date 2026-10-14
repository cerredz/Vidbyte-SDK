# Output Providers

This folder holds the provider classes that send a finished agent reply's
title and body to one destination each: Slack, Discord, Microsoft Teams,
Google Chat, Telegram, email over SMTP, GitHub issues and issue or pull
request comments, the GitHub Actions job summary, GitLab issues and merge
request notes, Linear, Jira Cloud, Confluence Cloud, Notion, Typefully
drafts, HubSpot tasks, and any HTTPS webhook. It does provider work only:
reading the credential, building the destination's requests, suppressing
channel-wide mentions, applying the destination's length cap, and turning
the response into a `DeliveryReceipt`.

The `OutputConnector` contract, the rule for which replies are delivered, the
default title and body shaping, and the dispatcher that runs every connector
live in [`vidbyte/agents/output/`](../../agents/output/README.md). Attach
connectors with `Agent(..., outputs=[...])`; nothing here decides when a reply
is sent.

## Non-goals

- **No OAuth.** Every destination takes one pasted credential, or, for the
  job summary, a file path: a webhook URL, a token, an API key, or an SMTP
  password. Destinations that only accept OAuth (the Gmail API, Microsoft
  Graph, Google Sheets, and similar) are not here.
- **No MCP delivery, no YAML configuration, and no CLI commands.** Connectors
  are built in Python and passed to the agent.
- **No retries beyond HTTP 429.** A 429 is retried at most
  `OUTPUT_RATE_LIMIT_RETRIES` extra times. Nothing else is retried, because a
  duplicate post is worse than a reported failure. There is no outbox, queue,
  or resend helper.

## Modules

- `base.py`: `BaseOutput`, the abstract base every connector extends (a masked
  `repr` and the optional `render` hook), and `OutputArguments`, the shared
  constructor checks (credential lookup, `https://` URLs, identifiers, header
  maps, signing keys, and mutually exclusive modes).
- `text.py`: `OutputText`, the plain-text helpers: first line, chat text,
  truncation with a marker, and one-line titles.
- `adf.py`: `OutputAdf`, which turns reply Markdown (headings, bullet and
  numbered lists, fenced code, paragraphs) into an Atlassian Document Format
  document for Jira and Confluence.
- `delivery.py`: `OutputHttp`, which sends one JSON or exact-bytes `POST` or
  `PATCH`, or reads one JSON `GET`, through `HttpTransport` and maps the
  response to a receipt, and builds the HTTP Basic header value that Jira
  and Confluence share; `OutputResponses`, which reads an error code or a
  link from a response; and `OutputSmtp`, the single SMTP send.
- `slack.py`: `SlackOutput`, an incoming-webhook message.
- `discord.py`: `DiscordOutput`, a channel-webhook message or forum post with
  every mention suppressed.
- `teams.py`: `TeamsOutput`, an Adaptive Card posted to a Workflows webhook.
- `google_chat.py`: `GoogleChatOutput`, a space-webhook message.
- `telegram.py`: `TelegramOutput`, a bot `sendRichMessage` call.
- `email.py`: `EmailOutput`, one plain-text email over SMTP.
- `github.py`: `GitHubIssueOutput`, a new GitHub issue, a comment on an issue
  or pull request, or one comment or one issue per key kept up to date.
- `github_api.py`: `GitHubRequests` and `GitHubResponses`, the GitHub request
  builders and response readers `github.py` uses.
- `github_job_summary.py`: `GitHubJobSummaryOutput`, an append to the GitHub
  Actions job summary file.
- `gitlab.py`: `GitLabIssueOutput`, a new GitLab issue or a merge request note.
- `linear.py`: `LinearIssueOutput`, a new Linear issue or a comment on one,
  through GraphQL.
- `jira.py`: `JiraIssueOutput`, a new Jira Cloud issue or a comment on one.
- `confluence.py`: `ConfluencePageOutput`, a new Confluence Cloud page.
- `notion.py`: `NotionPageOutput`, a new Notion page under a parent page, or
  the reply appended to an existing page.
- `typefully.py`: `TypefullyDraftOutput`, a Typefully draft that a person
  publishes.
- `hubspot.py`: `HubSpotTaskOutput`, a HubSpot CRM task.
- `webhook.py`: `WebhookOutput`, a JSON `POST` to any HTTPS receiver (Make,
  n8n, Pipedream, Zapier, Power Automate), optionally with fixed headers, a
  custom payload, and a Standard Webhooks signature.
- `__init__.py`: exports the connectors and the provider helpers.

## Provider Reference

Each connector reads its credential from the argument first, then from the
environment variable below. The SDK never loads a `.env` file. Body caps are
in characters; longer text is cut and ends with a truncation marker. Where a
connector has several modes, pass the mode's argument; arguments that cannot
be honoured together raise `ConfigurationError` when the connector is built.

| Destination | Connector | Credential (environment variable) | How to get it; least privilege | Body cap | Official docs | Retrieved |
| --- | --- | --- | --- | --- | --- | --- |
| Slack | `SlackOutput(webhook_url=None)` | Incoming webhook URL (`SLACK_WEBHOOK_URL`) | App settings, then Incoming Webhooks, then Add New Webhook, then choose a channel. The URL posts only to that channel. A reply of up to 12,000 characters is sent as one `markdown` block, so its Markdown renders; a longer one is sent as escaped text. | 12,000 as a `markdown` block; 40,000 as text | [Incoming webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/), [Markdown block](https://docs.slack.dev/reference/block-kit/blocks/markdown-block/) | 2026-10-14 |
| Discord | `DiscordOutput(webhook_url=None, forum=False, forum_tags=())` | Channel webhook URL (`DISCORD_WEBHOOK_URL`) | Channel settings, then Integrations, then Webhooks. Works in text and announcement channels; the URL posts only to that channel. Add `?thread_id=<id>` to the URL to post into an existing thread or forum post. In a forum channel, `forum=True` creates a forum post titled with the reply title; pass `forum_tags=` (tag ids) when the forum requires tags. A forum webhook without either fails `http_400`, and so does a `?thread_id=` URL with `forum=True`. Adding `?wait=true` makes Discord return the message and channel ids, not a link, so the receipt never has a link. | 2,000 | [Webhook resource](https://docs.discord.com/developers/resources/webhook), [Channel resource](https://docs.discord.com/developers/resources/channel) | 2026-10-14 |
| Microsoft Teams | `TeamsOutput(webhook_url=None)` | Workflows webhook URL (`TEAMS_WEBHOOK_URL`) | In the channel, open Workflows and choose "Send webhook alerts to a channel" (for a group chat, "Send webhook alerts to a chat"), with "Who can trigger" set to **Anyone**. The reply is a full-width Adaptive Card whose first block is the title in bold. | 7,000 | [Teams connector](https://learn.microsoft.com/en-us/connectors/teams/), [Card format](https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-format) | 2026-10-14 |
| Google Chat | `GoogleChatOutput(webhook_url=None)` | Space webhook URL (`GOOGLE_CHAT_WEBHOOK_URL`) | Space, then Apps & integrations, then Add webhooks. Google Workspace Business or Enterprise only. Markdown (`markupSyntax`) is not sent, because Google documents it only for Chat API calls, not for webhooks. | 8,000 | [Webhooks quickstart](https://developers.google.com/workspace/chat/quickstart/webhooks), [Format messages](https://developers.google.com/workspace/chat/format-messages) | 2026-10-14 |
| Telegram | `TelegramOutput(chat_id, topic_id=None, bot_token=None)` | Bot token (`TELEGRAM_BOT_TOKEN`) | Create the bot with @BotFather, then add it to the chat. For a channel, pass `chat_id="@channelname"` once the bot is a channel administrator with "Post Messages". `topic_id=` posts into a forum topic; on a chat that is not a forum it fails `http_400`. The reply is sent as rich Markdown with `sendRichMessage`; every `<` shows as `＜` and every `![` as `!［`, so no HTML, buttons, or media pass. | 32,768 | [Bot API](https://core.telegram.org/bots/api) | 2026-10-14 |
| Email (SMTP) | `EmailOutput(to, host, username, password=None, sender=None, port=587)` | SMTP password (`SMTP_PASSWORD`) | A provider SMTP credential; see Email Providers below. Prefer a send-only credential where the provider offers one. | none | [Python smtplib](https://docs.python.org/3/library/smtplib.html) | 2026-10-11 |
| GitHub Issues | `GitHubIssueOutput(repo, labels=(), comment_on=None, key=None, token=None)` | Token (`GITHUB_TOKEN`) | A fine-grained personal access token with the repository permission Issues set to write, or in Actions `GITHUB_TOKEN` with `permissions: issues: write`; comments also accept Pull requests set to write. With no mode argument each reply opens a new issue. `comment_on=<number>` comments on that issue or pull request. `comment_on` with `key=` keeps one comment, marked `<!-- vidbyte:<key> -->`, and edits it on every run. `key=` alone keeps one open issue labelled `vidbyte:<key>`, opening it on the first run and commenting on it after. Labels, the key label too, are silently dropped unless the token's user has push access. | 65,536 | [Issues](https://docs.github.com/en/rest/issues/issues), [Issue comments](https://docs.github.com/en/rest/issues/comments) | 2026-10-14 |
| GitHub Actions job summary | `GitHubJobSummaryOutput(path=None)` | Summary file path (`GITHUB_STEP_SUMMARY`) | Nothing to create: GitHub Actions sets `GITHUB_STEP_SUMMARY` for every step, and the reply is appended to that file as Markdown, shown on the run's summary page. Outside Actions, pass `path=`, and pass only a file you own. A missing directory is not created, and any file error is FAILED `file_error`. | 262,144 per reply | [Workflow commands](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands) | 2026-10-14 |
| GitLab | `GitLabIssueOutput(project, host="gitlab.com", labels=(), merge_request=None, token=None)` | Access token (`GITLAB_TOKEN`) | A project access token with the `api` scope, or a personal or group access token. `project` is a path such as `acme/shop` or a numeric id; `host` is a self-managed server's host name, with an optional port. `merge_request=<iid>` adds the reply as a note on that merge request instead of opening an issue; the note's receipt has no link. `labels=` applies to issues only. | 1,048,576 for issues; 1,000,000 for notes | [Issues API](https://docs.gitlab.com/api/issues/), [Notes API](https://docs.gitlab.com/api/notes/), [Project access tokens](https://docs.gitlab.com/user/project/settings/project_access_tokens/) | 2026-10-14 |
| Linear | `LinearIssueOutput(team_id=None, labels=(), comment_on=None, api_key=None)` | Personal API key (`LINEAR_API_KEY`) | Settings, then Account, then Security & Access. Limit the key to "Create issues" (or "Create comments" for `comment_on`) on the teams it posts to. Pass `team_id` for a new issue, or `comment_on` (an identifier such as `ENG-123`, or a dashed UUID) to comment on that issue. `labels=` takes label UUIDs and applies to new issues only. | none documented | [GraphQL API](https://linear.app/developers/graphql), [Schema](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql) | 2026-10-14 |
| Jira Cloud | `JiraIssueOutput(site, email, project=None, issue_type="Task", labels=(), comment_on=None, api_token=None)` | API token (`JIRA_API_TOKEN`) | id.atlassian.com, then API tokens, then a token without scopes. API tokens expire within a year: Atlassian sets 1 to 365 days. The account needs only Browse projects and Create issues, or Add comments for `comment_on`. Pass `project` for a new issue, or `comment_on` (an issue key such as `PROJ-12`) to comment on it. `labels=` takes label names without spaces and applies to new issues only. Descriptions and comments keep the reply's headings, lists, and code blocks. | 32,767 | [Basic auth for REST APIs](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/), [Issue comments](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/), [API tokens](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/) | 2026-10-14 |
| Confluence Cloud | `ConfluencePageOutput(site, space_id, email, parent_id=None, api_token=None)` | API token (`CONFLUENCE_API_TOKEN`) | The same kind of Atlassian API token as Jira (id.atlassian.com, then API tokens, without scopes; it may be the same token). The account needs permission to add pages in the space. `space_id` and `parent_id` are numeric ids. Each reply becomes a page titled with the reply title, with its headings, lists, and code blocks kept. | 500,000 | [Create page](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/#api-pages-post), [Basic auth](https://developer.atlassian.com/cloud/confluence/basic-auth-for-rest-apis/) | 2026-10-14 |
| Notion | `NotionPageOutput(parent_page_id=None, append_to=None, api_key=None)` | Integration token or personal access token (`NOTION_API_KEY`) | An internal integration shared with only the target page (•••, then Add connections), or a personal access token, which acts as you. Pass `parent_page_id` for a new child page, or `append_to` (a page id) to add the reply as Markdown at the end of that page, which must be shared with the integration. | none documented | [Create a page](https://developers.notion.com/reference/post-page), [Update page markdown](https://developers.notion.com/reference/update-page-markdown) | 2026-10-14 |
| Typefully | `TypefullyDraftOutput(social_set_id, platforms, api_key=None)` | API key (`TYPEFULLY_API_KEY`) | Generate the key in Typefully's settings; it has its creator's access. `social_set_id` is the account set to draft in, and `platforms` lists `TypefullyPlatform` values (x, linkedin, threads, bluesky, mastodon). Each reply is saved as one draft with the body as one post on each platform, and is never published or scheduled. The receipt links the draft. | none documented | [Typefully API](https://typefully.com/docs/api) | 2026-10-14 |
| HubSpot | `HubSpotTaskOutput(access_token=None)` | Private app access token (`HUBSPOT_ACCESS_TOKEN`) | Development, then Legacy apps, then Create legacy app, then Private, with only the `crm.objects.contacts.write` scope the tasks guide names; copy the token from the Auth tab. HubSpot now files these apps under "Legacy apps". Each reply becomes one task with the title as its subject, the body as its notes, and the send time as its due time, with no owner and no association. | 65,536 | [Tasks API](https://developers.hubspot.com/docs/api-reference/crm-tasks-v3/guide), [Legacy private apps](https://developers.hubspot.com/docs/apps/legacy-apps/private-apps/overview) | 2026-10-14 |
| Generic webhook | `WebhookOutput(url=None, headers=None, payload=None, secret=None)` | Receiver URL (`VIDBYTE_OUTPUT_WEBHOOK_URL`) | The automation tool creates the URL; keep it unguessable. `headers=` adds fixed headers, such as a receiver's API key, to every request. `payload=` is a function of the reply and its content that returns the JSON object to send instead of the default envelope. `secret=` (a `whsec_` base64 key of 24 to 64 bytes) signs each request with Standard Webhooks headers; see Webhook receivers below. | none | [Make webhooks](https://help.make.com/webhooks), [Standard Webhooks](https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md) | 2026-10-14 |

Retrieved 2026-10-11; rows changed by the follow-ups retrieved 2026-10-14.
Provider limits, API versions, and setup screens change; re-check the linked
pages before changing a connector.

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

## Email-in

Many tools turn an email sent to a project, board, or channel address into a
new item. `EmailOutput` reaches them with no connector of its own: send the
reply to that address, and the tool reads the title as the subject and the
body as the text.

| Tool | Where to find the address | Docs |
| --- | --- | --- |
| Linear | Team settings: create an email intake address for the team or for one of its templates | [Create issues by email](https://linear.app/docs/creating-issues) |
| Trello | The board's menu, then Settings, then Email-to-board settings | [Creating cards by email](https://support.atlassian.com/trello/docs/creating-cards-by-email/) |
| Asana | The project's menu, then its email address; only project members can send | [Email tasks to Asana](https://help.asana.com/s/article/email-tasks-to-asana) |
| ClickUp | The List's menu, then Email to List | [Email to ClickUp](https://help.clickup.com/hc/en-us/articles/6309707288599) |
| monday.com | The board's menu, then Email to board | [Email to board](https://support.monday.com/hc/en-us/articles/115005339645-Email-to-board) |
| Todoist | The project's ••• menu, then Manage data, then Email tasks to this project | [Forward emails](https://www.todoist.com/help/articles/forward-emails-to-todoist-JPJ1V339) |
| PagerDuty | The service's Integrations tab, then an Email integration | [Email integration guide](https://support.pagerduty.com/main/docs/email-integration-guide) |
| Zendesk | The support address, `support@<subdomain>.zendesk.com` by default | [Forwarding email](https://support.zendesk.com/hc/en-us/articles/4408886828698) |
| Freshdesk | Admin Settings, then Channels, then Email | [Support email](https://support.freshdesk.com/support/solutions/articles/37541-setting-up-your-support-email) |
| Help Scout | The inbox's settings, then Connect Email, then Copy | [Get your email in](https://docs.helpscout.com/article/830-get-your-email-into-help-scout) |
| Slack | The channel's details, then its email address; paid plans only | [Send emails to Slack](https://slack.com/help/articles/206819278-Send-emails-to-Slack) |
| Teams | The channel's More options, then Get email address; an admin must enable it | [Email a channel](https://support.microsoft.com/en-us/teams/teams-channels/send-an-email-to-a-channel-in-microsoft-teams) |
| Evernote | Account settings, then the address to email notes to | [Save emails](https://help.evernote.com/hc/en-us/articles/209005347-Save-emails-into-Evernote) |
| Basecamp | The project's "Email content to this project" link; this is the Basecamp 2 guide, the only one found | [Email-In](https://basecamp.com/help/2/guides/projects/email-in) |

Links in this section retrieved 2026-10-14.

- **Subject commands:** Trello reads `#label` and `@member` in the subject,
  Todoist reads priority, label, and date words, ClickUp reads `<tag>`
  commands, and Evernote reads `@notebook #tag !reminder +`. A model-written
  title can trigger them, so pass a `render=` with a fixed subject.
- **monday.com** files mail only from a board member's account address, so
  set `sender` to one.
- **Asana** requires the sender to be a member of the project.
- **PagerDuty** email filters can drop mail silently.
- **Slack** channel addresses need a paid plan, and **Teams** channel
  addresses need an admin to enable them.
- **Never add `Auto-Submitted` or `Precedence: bulk`:** Jira Service
  Management rejects such mail
  ([mail handler](https://support.atlassian.com/jira/kb/emails-sent-by-customers-are-rejected-by-jira-service-management-mail-handler/)),
  and Zendesk suspends it
  ([ticket suspension](https://support.zendesk.com/hc/en-us/articles/4408828416282-Causes-for-ticket-suspension)).
  `EmailOutput` sends neither header.

```python
from vidbyte import EmailOutput, OutputContent

smtp = {"host": "smtp.example.com", "username": "agent@example.com"}

# A fixed subject, so no model-written word becomes a subject command.
trello = EmailOutput(to="<board address>", **smtp, render=lambda reply: OutputContent(title="Agent report", body=reply.content))

# Basecamp 2 files a subject that starts with FWD: as a forwarded email.
basecamp = EmailOutput(to="<project address>", **smtp, render=lambda reply: OutputContent(title="FWD: Agent report", body=reply.content))

# Evernote: a trailing + appends to the newest note with that title.
evernote = EmailOutput(to="<Evernote address>", **smtp, render=lambda reply: OutputContent(title="Agent log @Reports +", body=reply.content))
```

## Webhook receivers

`WebhookOutput` posts JSON to any HTTPS URL, so a service with an incoming
webhook needs no connector of its own: `headers=` carries its key, and
`payload=` builds the body it expects.

- **Google Apps Script:** a web app answers the POST with a redirect to
  `script.googleusercontent.com`
  ([Content service](https://developers.google.com/apps-script/guides/content)).
  The SDK does not follow redirects, so the script runs but the receipt is
  FAILED `http_302`. Send to Google Sheets through n8n, Make, or Zapier
  instead.
- **Verifying `secret=`:** each signed request carries `webhook-id`,
  `webhook-timestamp`, and `webhook-signature: v1,<base64>`. Base64-decode
  the key after `whsec_`, recompute the base64 HMAC-SHA256 over
  `"{webhook-id}.{webhook-timestamp}."` followed by the raw body, compare it
  in constant time, reject old timestamps, and drop a `webhook-id` already
  seen. The official libraries do all of this
  ([Standard Webhooks](https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md)).

One recipe per receiver; each needs its URL served over https:

| Receiver | Recipe | Docs |
| --- | --- | --- |
| ntfy | `WebhookOutput(url="https://ntfy.sh/", payload=lambda reply, content: {"topic": "agent-runs", "title": content.title, "message": content.body})`: JSON goes to the root URL and names the topic | [Publish as JSON](https://docs.ntfy.sh/publish/#publish-as-json) |
| Gotify | `WebhookOutput(url="https://gotify.example.com/message", headers={"X-Gotify-Key": app_token}, payload=lambda reply, content: {"title": content.title, "message": content.body})` | [Push messages](https://gotify.net/docs/pushmsg) |
| Home Assistant | `WebhookOutput(url="https://home.example.com/api/webhook/<id>")`: a webhook trigger is local-only by default, so turn that off and reach it over https | [Webhook trigger](https://www.home-assistant.io/docs/automation/trigger/#webhook-trigger) |
| Pushcut | `WebhookOutput(url="https://api.pushcut.io/v1/notifications/<name>", headers={"API-Key": api_key}, payload=lambda reply, content: {"title": content.title, "text": content.body})`: the path is unverified, because the official page renders blank to fetchers | [Web API](https://www.pushcut.io/webapi) |
| Apprise API | `WebhookOutput(url="https://apprise.example.com/notify/<key>", payload=lambda reply, content: {"title": content.title, "body": content.body})` | [Apprise API](https://github.com/caronc/apprise-api) |
| Inngest | `WebhookOutput(url="https://inn.gs/e/<event key>", payload=lambda reply, content: {"name": "agent/reply.sent", "data": {"title": content.title, "body": content.body}})` | [Send events](https://www.inngest.com/docs/durable-execution/guides-and-advanced/events-and-triggers/send-events) |
| incident.io | `WebhookOutput(url="<alert source URL>", headers={"Authorization": f"Bearer {source_secret}"}, payload=lambda reply, content: {"title": content.title, "description": content.body, "status": "firing"})`: success is 202 | [HTTP alert sources](https://docs.incident.io/alerts/custom-http-sources) |
| Mattermost | `WebhookOutput(url="<incoming webhook URL>", payload=lambda reply, content: {"text": content.body})` | [Incoming webhooks](https://docs.mattermost.com/developers/integrate/webhooks/incoming) |
| Rocket.Chat | `WebhookOutput(url="<incoming webhook URL>", payload=lambda reply, content: {"text": content.body})` | [Integrations](https://docs.rocket.chat/docs/integrations) |
| n8n | `WebhookOutput(url="<webhook node URL>", headers={"x-api-key": api_key})`: the Webhook node's Header Auth checks the header | [Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/) |
| Jira Automation | `WebhookOutput(url="<incoming webhook URL>", headers={"X-Automation-Webhook-Token": webhook_secret})`: the rule reads the body as `{{webhookData}}` | [Automation triggers](https://support.atlassian.com/cloud-automation/docs/jira-automation-triggers/) |

Links in this section retrieved 2026-10-14.

## How To Add A Destination

1. Add a member to `OutputDestination` in `vidbyte/lib/enums/outputs.py`.
2. Add its environment variable to `OUTPUT_CREDENTIAL_ENV_VARS`, and any cap,
   URL, or version to `vidbyte/lib/constants/outputs.py`.
3. Add one module here with one `BaseOutput` subclass that has `__init__`,
   `send`, and, when `send` has several modes, private helpers that `send`
   calls (static, or async methods when they need the connector's
   settings, as in `github.py`). Check every argument in `__init__` with
   `OutputArguments`, and send through `OutputHttp.post`, `OutputHttp.patch`,
   `OutputHttp.read`, or `OutputSmtp.send` so status codes, timeouts, and
   secrets are handled in one place. Blocking work, such as SMTP or a file append, runs on the
   module's own executor, as `email.py` and `github_job_summary.py` do.
4. Export it from this folder's `__init__.py`, from `vidbyte.agents.output`,
   and from the root `vidbyte` package, then regenerate the public API
   contract.
5. Add a row to the Provider Reference table above with its retrieval date.

## Footguns

- **Teams:** only flows whose trigger allows **Anyone** work; tenant-auth
  flows need OAuth. Microsoft labels the **Anyone** setting "Legacy"
  ([Power Automate auth](https://learn.microsoft.com/en-us/power-automate/oauth-authentication)).
  Group chats use the "Send webhook alerts to a chat" template
  ([Teams workflows](https://support.microsoft.com/en-us/office/create-incoming-webhooks-with-workflows-for-microsoft-teams-8ae491c7-0394-4861-ba59-055e33f75498)).
  If a tenant turns **Anyone** off, send `EmailOutput` to the channel's email
  address instead (More options, then Get email address, which an admin must
  enable;
  [channel email](https://support.microsoft.com/en-us/teams/teams-channels/send-an-email-to-a-channel-in-microsoft-teams)).
  A 202 response means the flow accepted the request, not that the message
  was posted.
- **Gmail:** an app password needs 2-Step Verification, and it is unavailable
  when security keys are enforced.
- **GitHub:** labels are silently dropped unless the token's user has push
  access to the repository. With `key=` alone, that means no issue ever
  carries the key label, so a new issue opens on every run.
- **GitHub update in place:** two runs with the same key at the same moment
  can both find nothing and both write, leaving two marked comments or two
  key issues; later runs use the oldest. Only the first 1,000 comments of an
  issue or pull request are searched for the marker, so a sticky comment
  past that point is not found and a new one is posted.
- **Planted markers:** anyone who can comment can post
  `<!-- vidbyte:<key> -->` before the first run, and the oldest marked
  comment wins. If the token can edit that person's comment, each run
  overwrites it with the report; if it cannot, every run fails `http_403`
  for the life of the pull request.
- **Notion:** an internal integration sees only pages shared with it; share
  the parent page, or the `append_to` page, first.
- **Jira and Confluence:** API tokens expire within 365 days. Scoped API
  tokens are not supported by either connector, because they need a
  different host.
- **Confluence:** a page title already used in the space is refused, so two
  replies with the same title fail; give replies distinct titles with
  `render=`.
- **Typefully** never publishes or schedules: each draft waits for a person
  to publish it in Typefully.
- **HubSpot:** HubSpot now files private apps under "Legacy apps"
  (Development, then Legacy apps); the token comes from there.
- **GitLab:** project access tokens need Premium on GitLab.com, and by
  default last at most 365 days
  ([project access tokens](https://docs.gitlab.com/user/project/settings/project_access_tokens/)).
- **Job summary:** GitHub caps each step's summary at 1 MiB and shows 20
  summaries per job, so a long run may hide later replies.
- **Telegram:** every `<` shows as `＜` and every `![` as `!［`. Code in a
  reply that contains `<` will not run when copied from Telegram, and
  `<https://…>` autolinks lose their link form.
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
- **Personal mentions:** GitHub `@user` and `@org/team`, Telegram
  `@username`, and Telegram inline mentions `[name](tg://user?id=N)`, which
  notify by user id, in the delivered text notify the named person. Only
  channel-wide and mass mentions are suppressed.
- **Multi-request sends:** a GitHub send with `key=` reads comments or
  issues, then makes one write. The deadline can cut it during the reads,
  which writes nothing, or during the write, which is reported `network`
  but may have been applied. In key-only mode a resend after a cut issue
  create finds the new issue and adds the same text as a comment.
- **Deadline:** a destination that has not answered within
  `OUTPUT_DELIVERY_DEADLINE_SECONDS` is FAILED `network`, but an SMTP send or
  a job-summary append may still finish afterwards. Each runs on its own
  worker thread, not the loop's default executor, so `run()` returns at the
  deadline instead of waiting for it; the interpreter still waits for that
  thread at exit. If a FAILED receipt's `error_code` is `network`,
  `invalid_response`, `smtp_error`, `smtp_recipients_refused`, or
  `file_error`, or starts with `http_5`, that output may already have been
  delivered, so check its destination before resending it.
- **Restored sessions:** `Session.resume` and `fork_from` return agents with
  `outputs=()`; pass `outputs=` to `BaseAgent.restore` to deliver again.
