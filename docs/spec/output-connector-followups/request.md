---
slug: output-connector-followups
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-13
flags: none
---

# Request: Output connector follow-ups on PR #882 — rendering, webhook signing, comments, new connectors, update in place

This run adds a second batch of work to an EXISTING draft pull request,
https://github.com/cerredz/Vidbyte-SDK/pull/882 (branch `feat/agent-output-connectors`).
The first batch (11 output connectors plus `outputs=` on agents) was built by an
earlier pipeline run; its spec is `docs/spec/agent-output-connectors/spec.md` (r8,
status `pr-open`). This run's artifacts live in `docs/spec/output-connector-followups/`.

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (start of the conversation, in /talk mode):

````
recently had an idea for the  vidbyte-sdk/, and that is "output connectors". I want users to very easily be able to connect the output of their agent to a 3rd party provider  (github issue, slack channel, email, discord channel etc), and then bolt on this ability to their agent in 1 line using a key and we implement the under-the-hood functionality. How can we do this, what are a list of all platforms that we can do this for, and how are we going to handle credentials (in the vidbyte-cli./ we have a credential command system, im assuming that the api keys just have to go in the agent parameters,  but even do dont some  require oath?). And how do we actually implement something like this; one way I can see is taking in a user's api key, and then we simply tell the model after the user's request to use the mcp server to do X, and then determinstically pass teh structured output of the agent, or is there a better way. Consider multiple approaches and walk me through the best one
````

**Prompt 2:**

````
great, so lets assume no aoath token. can you show me a small code snippet of how someone would connect an output connector and the psuedocode of how that connector would be implemented?
````

**Prompt 3:**

````
but how do they upload their credentials to the agent in the params? or is this done another way?
````

**Prompt 4** (invoked /spec-pipeline; this built the first batch, PR #882):

````
Great, i want you to start with creating a spec and implementing this feature inside of the vidbyte-sdk/ repo. i think that I want this abstraction to live inside of the vidbyte-sdk/vidbyte/agents/output folder, and for all of the provider specific logic they can either go in the lib folder of the repo or the provider folder of the repo, and then our output folder and be responsible for the core logic kind of linking the provider and agent logic, and then of course we bolt the parameter on our BaseAgent (and I think we can bolt it only our JevAgent and CodingAgent as well). What i also want you to do in the spec is come up with a list of popular platforms that we implement like the example above  (without an oauth token) to also integrate with this output connector features (platforms like microsoft teams, gmail, slack, discord, notion, etc come to mind. But double check these and find more examples where we can store agent outputs), want implementation to not be overengineers, clean, modular, and elegant.  best of luck to you kid (will be comparing your output with gpt 6.1 astra)
````

**Prompt 5** (after a session restart): `continue`

**Prompt 6:**

````
and what are all outputs that we have defined?
````

**Prompt 7:**

````
great, walk me through setting up the discord output channel, what is everything that they have to do, how do they connect their agent output to discord, what are the different outputs inside of dioscord that they can connect, and show me the important code snippets under the hood
````

**Prompt 8:**

````
and then question: 1) in terms of all types of outputs for discord, do we have the full implementation space of  all outputs covered. if not, what are we missing from discord and any other platforms (the ones that we can implement and 2) what are the popular output channels that we are missing and we did not add in the pr (think about output channels that software engineers, founder, and other job industrries use that does not require outh token)? try to be extensive with output channel list
````

**Prompt 9:**

````
so what do you suggest all of the changes that we make? give me a checklist?
````

**Prompt 10** (invoked /spec-pipeline — THIS RUN):

````
great, implement these things on the pr
````

## B. Handoff block and decision ledger (verbatim)

"These things" in Prompt 10 refers to the checklist the assistant gave in answer to
Prompt 9. That answer is reproduced verbatim below (everything between the
horizontal rules), because it is the scope of this run.

---

**vidbyte-sdk · PR #882 · output connector follow-ups**
Status: Needs you. I recommend a docs-only pass on #882 before it merges, then five follow-up PRs in the order below. Nothing gets built until you pick.

One correction to the Discord table I gave you earlier: `?wait=true` returns the message's id, not a clickable link, because the webhook URL doesn't include the server id.

**How to read the list:**
- **S** means one connector file plus tests.
- **M** means a new transport ability or a Markdown converter.
- 🧪 means it needs one test against your real workspace, since we never call real endpoints with credentials.
- Every item comes with tests in `tests/features/agent_output_connectors/` and a README row.
- No item touches `BaseAgent`, so the S008 lint limit on `_generate_reply` (zero headroom) stays safe.

### 0 · Docs pass on #882, before merge (no code changes, so nothing to re-review)
- [ ] **Discord row** (`vidbyte/lib/outputs/README.md`, line 63): say it works in text and announcement channels. Explain that adding `?thread_id=` to the URL posts into an existing thread or forum post, and that new forum posts fail with `http_400` until the Rendering PR lands.
- [ ] **Teams row and the note at line 110:**
  - Microsoft now labels "Anyone" a Legacy setting.
  - Group chats work with the "Send webhook alerts to a chat" template.
  - If a tenant turns "Anyone" off, use the channel's email address with `EmailOutput`.
- [ ] **Telegram row:** channels work with `chat_id="@name"` once the bot is an admin.
- [ ] **Jira row:** Atlassian API tokens expire within a year.
- [ ] **New "Email-in" section:**
  - About 12 tools with setup links: Linear intake, Trello, Asana, ClickUp, monday.com, Todoist, PagerDuty, Zendesk, Freshdesk, Help Scout, Slack/Teams channel addresses, Evernote.
  - Caveats: some tools read the subject line as commands, and some accept mail only from known senders.
  - Note that `render=` can already set a fixed subject, e.g. Basecamp's `FWD:` or Evernote's trailing `+` to append to a note.
- [ ] **Webhook section:** Google Apps Script answers with a 302 redirect. The row still gets written, but the receipt says FAILED `http_302`. Recommend sending Sheets through n8n, Make or Zapier instead.
- [ ] **Spec §9.2(b) corrections:**
  - HubSpot tasks qualify.
  - X, LinkedIn, Bluesky, Mastodon and Threads are reachable through Typefully or Buffer.
  - Pushover and ntfy are reachable through Apprise.
  - Nine JSON-based SMS providers exist.
  - Retirements: Zendesk, Shopify, Greenhouse and Bandwidth are moving to OAuth-only; Bitbucket issues, Relay.app, OneNote email-in and LINE Notify are gone.
- [ ] **Then your usual merge routine:**
  1. Merge main into the branch (it was 5 commits behind, and the merge was conflict-free).
  2. Re-measure S008.
  3. Dispatch `ci.yml` and `static-policy.yml`.
  4. Mark the PR ready.

### 1 · Rendering PR: replies look right (same credentials)
- [ ] **Discord `forum=True`**, plus optional `forum_tags=`: the reply's title becomes the forum post's name (up to 100 chars). It has to be opt-in because Discord rejects that field on normal text channels. **S**
- [ ] **Slack:** send Slack's `markdown` block (up to 12,000 chars), with plain `text` for the notification. Longer replies keep today's escaped text. **S** 🧪 Check that webhooks accept the block and that `<!channel>` inside it doesn't ping everyone.
- [ ] **Telegram:** use `sendRichMessage` with Markdown. The length limit goes from 4,096 to 32,768 chars. **S** 🧪
- [ ] **Teams:** show the title as its own bold line above the body, on a full-width card. **S**
- [ ] **Jira:** support headings, bulleted and numbered lists, and code blocks. Today every line becomes a plain paragraph. **M**
- [ ] **Google Chat:** turn on its Markdown option, but only if the test shows webhooks honor it. **S** 🧪
- [ ] **Optional — Telegram `topic_id=`** for groups that use forum topics. **S**

### 2 · Webhook PR: `WebhookOutput` can reach any JSON receiver
- [ ] **`headers=`** for fixed headers such as `Authorization`. Hidden in `repr` and never logged. **S**
- [ ] **`payload=`**: a function that builds the JSON for a specific receiver. The default `{agent, title, body, structured}` stays the same. **S**
- [ ] **`secret=`**: signs requests using the Standard Webhooks headers (`webhook-id`, `webhook-timestamp`, `webhook-signature`). The request's existing idempotency key doubles as `webhook-id`, so receivers can drop retried duplicates. **M**, because the signature must cover the exact bytes sent, and today `HttpTransport` turns `json_body` into bytes itself.
- [ ] **README examples instead of new classes:** ntfy, Gotify, Home Assistant, Pushcut, Apprise, Inngest, incident.io, Mattermost/Rocket.Chat, n8n with header auth, Jira Automation.

### 3 · Comments PR: comment on an existing issue or PR (one POST each, no transport change)
- [ ] **GitHub `comment_on=<issue or PR number>`:** the receipt links to the comment. This is the main win for CI review agents. **S**
- [ ] **Linear `comment_on="ENG-123"`** via `commentCreate`. **S**
- [ ] **Jira `comment_on="PROJ-12"`:** the link uses `focusedCommentId`. **S**
- [ ] **Notion:** add to an existing page instead of creating a child page. **S** 🧪 Need to confirm the name of the operation that updates a page's Markdown.
- [ ] **`labels=` on Linear** (label ids) **and Jira** (label names), matching GitHub's existing `labels=`. **S**

### 4 · New connectors PR (pick 3–5)
- [ ] **GitLab issue** (plus a merge-request comment): `PRIVATE-TOKEN`, link from `web_url`, `host=` for self-hosted GitLab. **S** For engineers.
- [ ] **GitHub job summary:** appends the reply's Markdown to `$GITHUB_STEP_SUMMARY`. No key and no network call; it shows up on the Actions run page. **S** For CI agents.
- [ ] **Confluence page:** same Atlassian token as Jira, and reuses Jira's rich-text builder. Needs the space's numeric id. **M**
- [ ] **Typefully drafts:** reaches X, LinkedIn, Threads, Bluesky and Mastodon with one key. It only ever makes drafts, because it never sends `publish_at`. **S** 🧪 Need to confirm the request format of their v2 API. For founders.
- [ ] **HubSpot task:** uses a private-app token; HubSpot returns no link. **S** HubSpot now files these tokens under "legacy apps", so they may be retired.
- **Next, if you want them:** Grafana annotations, Azure DevOps work items, PagerDuty Change Events, a local Markdown/JSONL file (for example, an Obsidian vault folder).

### 5 · Update-in-place PR: update instead of creating duplicates (largest change)
- [ ] **Transport:** `OutputHttp` gains GET and PATCH and returns the response JSON to the connector. Reads always happen first and the single write happens last. **M**
- [ ] **GitHub "sticky" comment:** a hidden `<!-- vidbyte:<key> -->` marker. If a comment with the marker exists, PATCH it; otherwise create one. **M**
- [ ] **GitHub one-issue-per-key:**
  - List open issues that carry the label `vidbyte:<key>`, then comment on the match or create a new issue.
  - Don't use the search API: newly created issues show up there late, and it allows only 30 requests a minute.
  - **M**
- [ ] **Linear and Jira versions**, only if you ask for them. **M**
- **Limit to document:** two runs racing on the same key can both create an issue.

### Don't build these unless you ask
- **Editing chat messages in place** (Discord, Telegram): we'd have to store message ids between runs, which means a new place to keep state.
- **File uploads** (Discord, Telegram, Jira, Notion): need multipart requests. Wait until a user actually needs files.
- **Form-encoded APIs** (Twilio, Mailgun, Zulip REST, Jenkins): need a new request body type for little reach.
- **HTML email:** `pyproject.toml` has no Markdown renderer, so this means adding a dependency.
- **Slack and Discord bot tokens:** these open DMs, threads and Slack canvases, but Slack calls its `xoxb` token an "OAuth token". Your call.
- **A client-credentials helper** (Zendesk, Shopify): would bend the "no OAuth" rule.
- **Quiet posts, custom bot names, opt-in pings:** each platform supports a different subset, and the value is low.
- **Outputs that reach customers or the public** (SMS, LINE, OneSignal, status pages, published social posts): they need consent and approval controls this feature doesn't have.
- **Treating Apps Script's 302 as success:** a general "302 means sent" rule would also count login redirects from single-sign-on (SSO) gateways as delivered.

---
**Re-entry · output connector follow-ups**
Decided: the reviewed #882 code stays as it is (563efc51); build only what you pick; nothing built yet; the plan is saved to memory.
Open: which follow-up PRs to build, and in what order.
Needs you:
1. Do the docs pass on #882 before merging? Default: yes.
2. Build order: Rendering, then Webhook, then Comments, and decide on New connectors and Update-in-place after that? Default: yes.
3. Should Slack `xoxb` and Discord bot tokens count as "no OAuth"? Default: no.
4. Add a Markdown dependency for HTML email? Default: no.

*Reply "go" to accept all defaults.*

Next: on "go", I do the #882 docs pass (README plus spec §9.2(b)), push it to the PR branch and dispatch both workflows. The follow-up PRs start from main once you merge #882. I can also write a short script you run with your own webhooks to clear the 🧪 checks.

---

## C. Structured conversation notes

### Key decisions
- **Everything lands on PR #882 itself**, not in separate follow-up PRs. The checklist recommended five follow-up PRs after #882 merges; the user overrode that with "implement these things on the pr" (Prompt 10). The "Rendering PR", "Webhook PR", etc. names in §B are now just names for groups of work inside #882.
- **Scope = every checkbox item in sections 0–5 of §B**, with these orchestrator readings of the user's reply (logged in pipeline.md):
  - Section 0 step "Mark the PR ready" is NOT done. Marking ready and merging stay the user's call; the PR stays a draft.
  - Section 0 step "Merge main into the branch" is DONE already by the orchestrator at S0 (merge commit `336d6c78`, conflict-free). "Re-measure S008" and "dispatch ci.yml and static-policy.yml" happen as part of the normal gates.
  - Section 0 "Discord row" text must describe the final behavior of this run (forum posts become possible with the new Discord option), not "fail until the Rendering PR lands".
  - Section 1 "Optional — Telegram `topic_id=`" IS built: it is a checkbox in the checklist the user said to implement.
  - Section 1 Google Chat Markdown is conditional ("only if the test shows webhooks honor it"). Nobody can run that live test in this pipeline. The spec author decides from Google's official documentation: build it only if the docs show the field is accepted by the same message-create call that incoming webhooks use; otherwise do not build it and list it as a live check for the user.
  - Section 4 said "pick 3–5"; the user did not narrow it, so ALL FIVE listed connectors are built (GitLab, GitHub job summary, Confluence, Typefully, HubSpot task). The "Next, if you want them" line is NOT built.
  - Section 5 "Linear and Jira versions, only if you ask for them" is NOT built (the user did not ask).
  - The "Don't build these unless you ask" list is NOT built.
  - Needs-you question 3 (bot tokens count as "no OAuth"?): default **no** — not built.
  - Needs-you question 4 (Markdown dependency for HTML email?): default **no** — not built.
- **No OAuth.** Every connector takes a pasted static credential (or none). This has held since Prompt 2 ("lets assume no aoath token").
- **Deterministic delivery after the reply** (decided in the first batch): connectors are plain Python that run after the agent replies; the model is never asked to call a tool or MCP server to deliver.
- **Placement** (Prompt 4, first batch): the abstraction lives in `vidbyte/agents/output/`; provider-specific logic lives in `vidbyte/lib/outputs/`.

### Rejected alternatives
- Separate follow-up PRs after #882 merges — overridden by the user ("on the pr").
- One class per push service (ntfy, Gotify, Home Assistant, ...) — `WebhookOutput(payload=..., headers=...)` plus README examples covers them.
- Writing a Markdown-to-Slack-mrkdwn converter — Slack's native `markdown` block exists.
- The GitHub search API for one-issue-per-key — newly created issues appear in search late, and search allows only 30 requests a minute.
- Treating any 302 as delivered (for Google Apps Script) — single-sign-on gateways answer unauthenticated POSTs with a 302 to a login page, so that rule would report undelivered replies as sent.
- Everything on the §B "Don't build" list (chat edit-in-place, files/multipart, form bodies, HTML email, bot tokens, client-credentials helper, quiet/persona/ping controls, customer- or public-facing outputs).

### Constraints and assumptions
- **No real network calls with credentials**, ever, in any stage. Tests fake the transport (seam: `HttpTransport._send_once`; see the first batch's niche facts). Reading public vendor documentation pages on the web is allowed and expected.
- **🧪 items cannot be live-tested here.** Each external request shape must be confirmed from the vendor's official docs (cite the URL and the date read in the spec). Whatever stays unconfirmed is listed in the PR body as a live check the user runs with their own webhooks/keys.
- **Backward compatibility of the first batch's public API.** Existing constructors, parameters, env var names, `OutputDestination` values, receipt shapes, error codes, and the default webhook JSON envelope `{agent, title, body, structured}` must keep working unchanged. A separate draft PR in another repo (vidbyte-cli #166, `--send-to slack|github|linear`) builds on `SlackOutput`, `GitHubIssueOutput`, `LinearIssueOutput`, and the root-package `OutputDispatcher` export added in commit `4272c308`.
- **Do not touch `BaseAgent._generate_reply`.** Lint rule S008 has zero headroom on it. Nothing in this scope needs an agent-level change.
- **The PR stays a draft.** Never force-push; never push to main. After the PR is pushed, catch up with main by merging origin/main, never by rebasing.
- **Not over-engineered, clean, modular, elegant** (Prompt 4). Prefer parameters on existing connectors over new classes where the destination is the same product; prefer README examples over classes for receivers `WebhookOutput` can reach.
- Correction carried from §B: in vidbyte-sdk, `HttpTransport`'s `idempotency_key` is a local guard and is never sent on the wire (first batch's S0 scout). So the §B sentence "the request's existing idempotency key doubles as `webhook-id`" is not literally possible; a `webhook-id` must be generated and sent as a header by the signing code. `HttpTransport` also sends JSON bodies only (no form encoding) and serializes `json_body` itself.
- Correction carried from §B: Discord's `?wait=true` returns the created message's id and channel id, not a clickable link (the webhook URL has no server id).

### Clarifications and answers
- Q: Do some providers need OAuth? — A (Prompt 2): "lets assume no aoath token."
- Q: How do users pass credentials? (Prompt 3) — Answered in the first batch: an explicit constructor argument, else an environment variable, else a `ConfigurationError` naming both.
- Q: Which checklist items, and in which PR? — A (Prompt 10): "implement these things on the pr".

### Terminology
- **Connector / output:** one `BaseOutput` subclass in `vidbyte/lib/outputs/` (e.g. `SlackOutput`), passed to an agent as `outputs=[...]`.
- **Receipt:** the `DeliveryReceipt` each connector returns (status `sent`/`failed`/`skipped`, optional `url`, optional `error_code`).
- **Rendering / Webhook / Comments / New connectors / Update-in-place:** the five work groups of §B sections 1–5.
- **Sticky comment:** one comment, found again by a hidden marker, that is edited on every run instead of a new comment being added.
- **One-issue-per-key:** a caller-chosen key maps to at most one open issue; later runs comment on it instead of creating a new issue.
- **Email-in:** a tool's inbound email address that turns a received email into a task, card, ticket, or note; `EmailOutput` can already send to it.
- **🧪 live check:** a one-time test against a real workspace that only the user can run.

### Implementation hints
- First batch code: `vidbyte/lib/outputs/` holds `base.py` (`BaseOutput`, `OutputArguments`), `delivery.py` (`OutputHttp.post` — POST only, `method="POST"` hard-coded; `OutputSmtp`), `text.py` (`OutputText`), and one file per connector: `slack.py`, `discord.py`, `teams.py`, `google_chat.py`, `telegram.py`, `email.py`, `github.py`, `linear.py`, `jira.py`, `notion.py`, `webhook.py`. Records live in `vidbyte/lib/dataclasses/outputs.py` (`OutputRequest`, `DeliveryReceipt`, `OutputContent`, `SmtpSettings`), enums in `vidbyte/lib/enums/outputs.py` (`OutputDestination`, `DeliveryStatus`), constants in `vidbyte/lib/constants/outputs.py`. The dispatcher is `vidbyte/agents/output/dispatcher.py`; each connector's `send()` runs under a 35 s deadline, so a connector may make more than one request inside `send()` without a dispatcher change.
- `vidbyte/lib/outputs/README.md` rows to edit: Discord (line 63), Teams (line 64), Telegram (line 66), Jira (line 70), the Teams note (line 110); it has an "Email Providers" section (line 77).
- First-batch spec to correct (§9.2(b) platform table): `docs/spec/agent-output-connectors/spec.md`.
- Tests: `tests/features/agent_output_connectors/` (first batch). Run with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`.
- `webhook.py` header rule: "Add a payload key here only when every receiver can ignore it" — `payload=` keeps the default envelope frozen.
- The first batch's accumulated niche facts (lint rules A001/A002/A006/A007/S008/S009/S012/S052/S054/S062/S063/C016, test seams, Semgrep setup) are in `docs/spec/agent-output-connectors/pipeline.md` § "Niche facts accumulated" and are copied into this run's `pipeline.md`.
- Research findings from the conversation (UNVERIFIED until the spec author confirms each from official docs):
  - Discord execute-webhook: `thread_name` creates a forum/media post (max 100 chars); `applied_tags` = tag ids; forum/media channels reject posts without `thread_name` or `thread_id` (error 220001); `thread_name` on a non-forum channel is rejected (error 220003); forums can require a tag. `?thread_id=` posts into an existing thread. Docs: https://docs.discord.com/developers/resources/webhook
  - Slack: `markdown` block type, cumulative 12,000-char limit per payload; incoming-webhook support for this block is not explicitly named in Slack's webhook doc.
  - Telegram Bot API 10.1 (June 11, 2026) added `sendRichMessage` (rich messages; Markdown, HTML, or blocks; up to 32,768 chars; up to 500 blocks). A local copy of the Bot API page and changelog: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/ece663b4-5090-422c-ad68-c3b2451a23f6/scratchpad/tg_api.txt` and `tg_changelog.txt` (saved 2026-10-12). Forum topics use `message_thread_id`.
  - Google Chat: `markupSyntax: MARKUP_SYNTAX_MARKDOWN` on the message (support for incoming webhooks unconfirmed; 32,000-byte message limit).
  - Teams Adaptive Card: TextBlock `weight`/`size`; `msteams: {"width": "Full"}`; TextBlock Markdown supports bold, italic, lists, links only.
  - Jira ADF: `heading` (attrs.level 1–6), `bulletList`/`orderedList` → `listItem` → `paragraph`, `codeBlock` (attrs.language).
  - GitHub: `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` `{body}` → `html_url` (works for PRs too); `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}`; list issues `GET /repos/{owner}/{repo}/issues?labels=...&state=open`; list comments `GET /repos/{owner}/{repo}/issues/{n}/comments` (paginated).
  - Linear: `commentCreate(input: {issueId, body})` → `comment { url }`; `issueCreate` accepts `labelIds`; issue identifiers like "ENG-123" are accepted where an issue id is expected (verify for `commentCreate`).
  - Jira: `POST /rest/api/3/issue/{issueIdOrKey}/comment` `{body: ADF}` → `id`; link `https://{site}/browse/{KEY}?focusedCommentId={id}`; issue `fields.labels` = list of strings.
  - Notion: `PATCH /v1/pages/{page_id}/markdown` with an operation such as `replace_content` or `update_content` (operation name unconfirmed); the first batch creates pages with a `markdown` field on `notion-version 2026-03-11`.
  - Standard Webhooks: headers `webhook-id`, `webhook-timestamp` (unix seconds), `webhook-signature: v1,<base64 HMAC-SHA256 over "{id}.{timestamp}.{body}">`; the secret is `whsec_` + base64; the signature header may hold a space-separated list. Spec: https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md
  - GitLab: `POST /api/v4/projects/:id/issues` (`title`, `description`, `labels`; header `PRIVATE-TOKEN`; returns `web_url`) https://docs.gitlab.com/api/issues/#new-issue ; MR notes `POST /projects/:id/merge_requests/:iid/notes` https://docs.gitlab.com/api/notes/ ; project tokens need Premium; tokens last at most 365 days.
  - GitHub job summary: append Markdown to the file named by `$GITHUB_STEP_SUMMARY`; 1 MiB per step; up to 20 summaries shown per job.
  - Confluence Cloud v2: `POST /wiki/api/v2/pages` with `spaceId` (numeric), optional `parentId`, `title`, `body: {representation: "atlas_doc_format", value: <JSON string>}`; same Atlassian email + API token as Jira. https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/
  - Typefully v2: API key; creates drafts for X, LinkedIn, Threads, Bluesky, Mastodon; sending `publish_at` (e.g. "now") publishes publicly. https://typefully.com/docs/api
  - HubSpot: `POST /crm/v3/objects/tasks` with properties `hs_task_subject`, `hs_task_body`, `hs_timestamp` (required), optional status/priority/owner; private-app token; tasks show in the assignee's task list without an association; response has an id but no URL. https://developers.hubspot.com/docs/api-reference/crm-tasks-v3/guide
  - Email-in setup docs: Linear https://linear.app/docs/creating-issues · Trello https://support.atlassian.com/trello/docs/creating-cards-by-email/ · ClickUp https://help.clickup.com/hc/en-us/articles/6309707288599 · monday.com https://support.monday.com/hc/en-us/articles/115005339645-Email-to-board · Slack https://slack.com/help/articles/206819278-Send-emails-to-Slack · Apps Script web apps https://developers.google.com/apps-script/guides/web . Others (Asana, Todoist, PagerDuty, Zendesk, Freshdesk, Help Scout, Teams channel email, Evernote) need their official links found.
  - Email-in caveats: never add `Auto-Submitted` (Jira Service Management drops the mail) or `Precedence: bulk` (Zendesk suspends it); some tools check SPF/DKIM; subjects are parsed as commands (Trello `#label @member`, Evernote `@notebook #tag !reminder +`, ClickUp `<tag>`, Wrike `[Folder]`).
  - Retirement facts for §9.2(b): Zendesk API tokens — no new tokens from 2026-10-27, all stop 2027-04-30 (https://developer.zendesk.com/documentation/authentication/oauth-migration/); Shopify custom apps moved to the client-credentials grant from 2026-01-01; Greenhouse Harvest v1/v2 removal 2026-08-31 (v3 is OAuth); Bandwidth Basic auth ends 2026-12-02; Bitbucket Cloud issues and wikis removed 2026-08-20 (seen only in search snippets); Relay.app shut down September 2026; OneNote email-in retired March 2025; LINE Notify ended 2025-03-31. Microsoft labels the Teams/Power Automate "Anyone" trigger a "Legacy setting".

### Open questions (for the spec author to resolve from the code and the docs, or carry as Q-n with a default)
- Exact parameter names and types for every new option (`forum`, `forum_tags`, `topic_id`, `comment_on`, the Notion append option, `labels`, `headers`, `payload`, `secret`, the sticky/one-issue-per-key key parameter), and how sticky comment and one-issue-per-key relate to `comment_on`.
- Whether Slack's `markdown` block is accepted by incoming webhooks and whether `<!channel>` / `<!here>` inside it stays inert; what the fallback is if the docs cannot confirm it.
- How signing gets the exact bytes on the wire, given `HttpTransport` serializes `json_body` itself.
- Notion's append operation name; Confluence's numeric space id (how the user finds it); Typefully v2 request shape; HubSpot's required `hs_timestamp`.
- How the GitHub job summary connector resolves its target path (explicit argument, then `GITHUB_STEP_SUMMARY`, then an error?) and writes a file without a blocking call in async code (lint S052 flags blocking I/O in async).
- New `OutputDestination` values, env var names, and README rows for the five new connectors.
- How GET/PATCH reach `OutputHttp` while keeping the first batch's guarantees (credential URLs never logged, no redirects, 429-only retries, receipts never carry response text).

## D. Weighted words

- "I want users to very easily be able to connect the output of their agent to a 3rd party provider" — Prompt 1
- "bolt on this ability to their agent in 1 line using a key and we implement the under-the-hood functionality" — Prompt 1
- "lets assume no aoath token" — Prompt 2
- "want implementation to not be overengineers, clean, modular, and elegant" — Prompt 4
- "(without an oauth token)" — Prompt 4
- "do we have the full implementation space of  all outputs covered" — Prompt 8
- "that does not require outh token" — Prompt 8
- "try to be extensive with output channel list" — Prompt 8
- "so what do you suggest all of the changes that we make?" — Prompt 9
- "implement these things on the pr" — Prompt 10
