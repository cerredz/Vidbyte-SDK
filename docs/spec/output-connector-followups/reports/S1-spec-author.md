# S1 spec author report: output-connector-followups

- **Spec:** `docs/spec/output-connector-followups/spec.md` r1, committed `09f7c42d` on `feat/output-connector-followups` (base `336d6c78`). It has 18 `## §` headings.
- **Scope:** request.md §B sections 0–5 as read in §C. All 33 in-scope checkboxes map to an FR and a §12.3 row (spec §7, traceability table).

## What I read

- **Rules:** `AGENTS.md` (`CLAUDE.md` is `@AGENTS.md`), plus the `REPO_MAP.md` entries for `lib/outputs`, `agents/output`, and `lib/http`.
- **This run's docs:** `request.md`, `pipeline.md`, `context/code-map.md`, and `reports/S0-scout.md`.
- **The first batch's spec:** `docs/spec/agent-output-connectors/spec.md`, §4 and §9.2.
- **Code at base:**
  - Every module in `vidbyte/lib/outputs/`, read in full: base, delivery, discord, slack, teams, telegram, google_chat, github, linear, jira, notion, webhook, email (executor parts), text, and `__init__`.
  - `vidbyte/lib/dataclasses/outputs.py`, and `vidbyte/lib/constants/outputs.py` lines 1–106.
  - `vidbyte/lib/http/transport.py`, lines 1–30 and 60–244.
  - `LocalFileSystemBackend.append_text`, and checked that importing it adds no modules.
  - `vidbyte/agents/output/connector.py:65` (the default title is the body's first line).
  - The `OutputDeliveryError` repair text at `errors/base.py:215`, and the root export lines.
- **Tests:**
  - `factories.py` (`CONNECTOR_CASES`, `HttpScript`) and the pack's `README.md` and `FEATURE.md`.
  - The pinned rows and assertions in `test_output_connectors_wire_contract.py`, `_contract.py`, `_dispatch.py`, `_acceptance.py`, `_agent_wiring.py`, and `_security.py`.
  - Every other `_send_once` fake.
- **Baselines run at base (2026-10-14):**
  - `python lint/run.py` → `SDK-LINT: PASS`.
  - The pack → `341 passed in 4.21s`.
- **Vendor docs:** official pages only, one primary page per vendor where possible, read 2026-10-14. That includes my own read of the saved Telegram Bot API copy and two WebFetches: Notion's update-page-markdown page and Discord's Channel resource. Four research subagents (chat, trackers, webhooks and new connectors, email-in and retirements) read the rest. No credentialed calls, and no calls to a vendor API endpoint.

## Approaches weighed

- **Shape: options on existing connectors plus five new classes (chosen, D-1),** against one class per mode. The single-class approach keeps "1 line using a key" and one README row per product.
- **`OutputHttp` verbs `post`/`patch`/`read` (chosen, D-2),** against a `method` field on `OutputRequest` plus one generic `send`:
  - The verbs keep `post` meaning what it meant, and make "reads first, one write last" visible at the call site.
  - `OutputMethod` exists only because the placement rule says a closed set is an enum.
- **Exact-bytes signing.**
  - Chosen (D-3): add `content=` to `HttpTransport` (AGENTS.md Style 5).
  - Rejected: signing `json.dumps(json_body)` and trusting the transport to serialize identically. That is brittle, and breaks every receiver silently if serialization ever changes.
- **GitHub update-in-place driven by one `key=` (chosen, D-14):**
  - `comment_on` + `key` = sticky comment.
  - `key` alone = one issue per key.
  - Rejected runner-up: two separate parameters.
  - Pagination is by page number, at most 10 pages (D-15). `Link` headers were rejected, because the test fake returns no headers and nothing else reads them.
- **The GitHub multi-mode send.** It is split into mode methods, plus two static helper classes in `github_api.py` (D-23). This keeps Style 1 (one level deep) and S008.
- **Notion append (D-13).**
  - `insert_content` is the only documented append command, even though it is deprecated.
  - `replace_content` was rejected: it replaces the whole page.
  - The 200 response has no `url`, so the receipt is SENT with no link.
- **Rejected, smaller (§8.3):**
  - Connectors calling `HttpTransport` directly for GET and PATCH (fails INV-3 and INV-4, and the `delivery.py` rule).
  - No `OutputAdf` (fails FR-11 and FR-26).

## Where I disagreed with the scout or the request

- **§B 2 "the request's existing idempotency key doubles as `webhook-id`".** This cannot be done, because the key is a local guard and is never sent. request.md §C already corrects it. The spec generates `msg_<uuid4 hex>` once per send, and the transport's 429 retries reuse it (D-4). That matches the Standard Webhooks rule that the id stays the same across retries.
- **§B 0 "Nine JSON-based SMS providers".** Only eight are verified: Telnyx, Plivo, Vonage Messages, Sinch, Infobip, ClickSend, Bird, and Textmagic. Telesign's send call is `application/x-www-form-urlencoded`. The §9.2(b) correction (row 33) says eight and gives the reason.
- **§B 0 "Jira row: tokens expire within a year".** The README Footguns already say so (line 119). The row gets a short mention, citing "1 to 365 days".
- **§B 0 "Telegram channels work with `chat_id=\"@name\"`".** The code already accepts it. This is a docs-only change. The "bot must be admin" wording is not a sentence in the Bot API (A-18); only the `can_post_messages` right is documented.
- **§B 1 Google Chat.** I did not build it (D-24). Google offers `markup_syntax` "for messages sent using the Chat API". The webhook and create pages say nothing about Markdown, and request.md §C asks for documentary proof. It becomes L-3 and Q-4.
- **§B 3 "one POST each, no transport change".** Notion append is a PATCH (`/v1/pages/{id}/markdown`), so it depends on the G5 `OutputHttp.patch`.
- **§B 4 GitLab "link from `web_url`".** It holds for issues only. The documented MR-note response has no URL, so a note returns SENT with no link (D-21).
- **§B 4 HubSpot.** The date-versioned `2026-03` endpoint requires associations. I used v3, where associations are optional (D-20, A-13).
- **Scout code-map (2.x) "the vidbyte-gates AGENT-LINT" phrasing.** The real pass line is `SDK-LINT: PASS` (`lint/core/report.py:58`), and the spec uses that.

## Vendor facts verified and unverified

**Verified from official docs, read 2026-10-14** (quotes are in spec §8.1 and §9.2):
- **Discord:**
  - `thread_name`, `applied_tags`, `thread_id`, and `wait`.
  - Error codes 220001, 220002, 220003, 220004, and 40067.
  - Thread name "1-100 character" (Channel resource).
- **Slack:**
  - `markdown` block shape and the 12,000 cumulative limit.
  - Webhooks accept "all the usual formatting and layout blocks".
- **Telegram:**
  - `sendRichMessage`, `InputRichMessage`, `message_thread_id`, and `skip_entity_detection`.
  - Limits: 32,768 characters, 500 blocks, 16 nesting levels.
- **Teams:**
  - The `msteams.width` "Full" sample.
  - TextBlock Markdown support (no headers).
  - "Anyone" is labelled Legacy.
  - The chat template name.
  - The channel email address.
- **GitHub:**
  - Issue comments: POST, PATCH, and list (ascending id; max `per_page` 100).
  - Issues list parameters and the `pull_request` key.
  - Labels are silently dropped without push access.
  - Search: 30 requests a minute.
  - Job summary: `>>` appends; 1 MiB per step; 20 summaries per job.
- **Linear:** `commentCreate`, `Comment.url`, `issueId` accepts "LIN-123", and `labelIds`.
- **Jira:**
  - The comment endpoint and its 201 `id`.
  - `labels` is an array of strings with no spaces.
  - ADF `heading`, list, `codeBlock`, `text`, and `paragraph` rules.
- **Notion:**
  - `PATCH /v1/pages/{id}/markdown` with the exact `insert_content` body.
  - `insert_content` is deprecated but supported.
  - The response has no `url`.
- **Confluence:**
  - v2 `POST /wiki/api/v2/pages` fields; success is **200**, not 201.
  - `_links.webui` and `_links.base`.
  - Basic auth.
- **Standard Webhooks:** header names, the id reused across retries, timestamp in seconds, `msg_id.timestamp.payload`, `v1,` base64, HMAC-SHA256, and the `whsec_` secret format.
- **GitLab:**
  - Issue create fields, including the 1,048,576-character description and comma-separated labels.
  - `web_url`; URL-encoded paths; `PRIVATE-TOKEN`.
  - MR note body limited to 1,000,000 characters.
  - Project tokens need Premium; tokens last at most 365 days by default.
- **Typefully v2:** base URL, Bearer auth, the drafts path, `platforms`, `publish_at` "Omit to save as a draft", and 201 with `private_url`.
- **HubSpot:** v3 tasks, `hs_timestamp` required, and the "Legacy private apps" Bearer token.
- **Atlassian tokens:** "1 to 365 days". One token works for Jira and Confluence. Scoped tokens need `api.atlassian.com`.
- **Email-in:** all 13 tools plus Basecamp 2. JSM rejects `Auto-Submitted`; Zendesk suspends `Precedence`.
- **Retirement facts:** all 8.
- **Others:** Typefully and Buffer reach; Apprise reaches Pushover and ntfy; 8 SMS providers.
- **Recipe facts:** ntfy, Gotify (JSON via OpenAPI), Home Assistant (PUT recommended, POST allowed, local-only by default), Apprise API, Inngest, incident.io (Bearer is the alert source's secret; 202), Mattermost, Rocket.Chat, n8n Header Auth, and Jira Automation.

**Unverified.** Each is an assumption with a live check (spec §15):
- A-1, A-2, A-3: Slack webhook block acceptance, mentions inside the block, `text` fallback.
- A-4: Telegram Markdown robustness.
- A-5: Discord tag limit on webhooks.
- A-6: Teams enum casing.
- A-7: `whsec_` key decoding.
- A-8: Jira `focusedCommentId` on Cloud.
- A-9: GitHub label auto-create and the 50-character limit.
- A-10: Notion `insert_content` lifetime.
- A-11: Confluence link build and title uniqueness.
- A-12: Typefully `settings`, id type, long text.
- A-13: HubSpot v3 without associations, ISO timestamp, body cap.
- A-14: GitLab self-managed https `web_url`.
- A-15: Pushcut path.
- A-16: Apps Script "302".
- A-17: GitHub comment cap.
- A-18: the Telegram admin sentence.

## Assumptions I am least sure of

- **A-1 (Slack accepts the `markdown` block through incoming webhooks).** If it is wrong, every short Slack reply fails `http_400` the moment this ships. L-1 must run before the PR leaves draft. Q-5 (fall back to escaped text on 4xx) is the cheap fix if it fails.
- **A-9 (GitHub creates a missing `vidbyte:<key>` label on issue create).** If it is wrong, one-issue-per-key creates a new issue every run until the user creates the label by hand.
- **A-13 (HubSpot v3 tasks without associations).** HubSpot's own two references disagree.
- **Body choice in Typefully drafts.** `content.body` is the post text and the title becomes `draft_title`. That is a judgment call, not a vendor fact.

## Revision r2 addendum (S1 review round 1)

The review found 0 Blocker, 3 Major, and 5 Minor issues. All eight are accepted. The scope-adding parts became optional questions, each defaulting to no, and none is built. Every finding is recorded in spec §16, and §17 has an r2 row.

- **R-1 (Major), accepted.** Every `<` in Telegram Markdown becomes `＜` before the cap. This adds INV-18, EC-43, and EC-44, and changes D-8, AC-5, FR-8, the §9.2 row, T-2(c), the row 11 `@intent`, A-4, and the README. Personal `tg://user?id=` mentions notify, as documented. `skip_entity_detection` is Q-6.
- **R-2 (Major), accepted.** NFR-7 now bounds each attempt and states honestly what a deadline cut means. EC-45 covers a cut during the write, including the duplicate comment it can cause in keyed-issue mode. Row 3 keeps the header line 7 invariant and adds a note. D-15 and the README footgun are aligned. The budget check is Q-7.
- **R-3 (Major), accepted.** §13 now lists the four new `WIRE_ROWS`, a Confluence site distinct from Jira's, a missing-directory `S3CRET` path for the job-summary credential, and the job-summary repr. `dispatch.py:315` moved to "still passes".
- **R-4 (Minor), accepted.** NFR-6 and §12.4 require `--rule A002 --all` and `--rule S061 --all` to be clean on every touched file.
- **R-5 (Minor), accepted.** Row 29 lists the README lines the change makes false: :19, :37, :44, :46-49, :50, :98-102, and :137.
- **R-6 (Minor), accepted.** Row 3 gives exact regex values, with the fullmatch-after-`rstrip()` rule and the fence rules. They were checked locally against the stated examples. EC-14 is aligned.
- **R-7 (Minor), accepted.** EC-42 and the README footgun cover both planted-marker branches. The author filter is Q-8.
- **R-8 (Minor), accepted.** `signing_key` requires 24–64 decoded bytes, using `WEBHOOK_KEY_MIN_BYTES` and `WEBHOOK_KEY_MAX_BYTES`. D-5, AC-14, §8.5, and §9.2(b) are updated. The §4 example key decodes to 24 bytes.

Self-check rerun: 18 `## §` headings; INV-1…18, EC-1…45, Q-1…8, AC-1…36, and FR-1…35 have no gaps; every referenced ID is defined; D-24 is still Google Chat. No blocking questions.

## Revision r3 addendum (S1 review round 2, final)

The review found 1 Blocker, 2 Major, and 7 Minor issues, none scope-adding. All ten are accepted; R-17 uses a variant that has the same effect. Every finding is recorded in spec §16, and §17 has an r3 row. The frontmatter is now `status: approved`, `revision: 3`.

- **R-9 (Blocker), accepted.** `OutputHttp._error_code` and `_link` move unchanged into a static `OutputResponses` class in `delivery.py` (the D-23 pattern), so `post`/`patch` → `_write` stays one level deep. The class budget goes from 11 to 12; new files stay at 7. Changed D-2, §8 intro, §8.2, §8.4, §8.5, §11, row 6 (now cites Style 1), §5, and §13.
- **R-10 (Major), accepted.** INV-18 also turns every `![` into `!［` (U+FF3B, one code point, so the length is unchanged), using `TELEGRAM_MEDIA_PREFIX` and `TELEGRAM_MEDIA_REPLACEMENT`. Only two characters ever change: every `<` becomes U+FF1C, and every `[` directly after `!` becomes U+FF3B. EC-44 now gives literal text. AC-5, D-8, FR-8, §9.2, T-2(c), A-4, the row 11 `@intent`, and the README are updated.
- **R-11 (Major), accepted.** D-9 rule: when `OutputText.first_line(body) == title`, drop the lines through that first non-blank line, then leading blank lines; otherwise keep the body unchanged. AC-7 has three cases. In §13, the Teams `WIRE_ROWS` body block is exactly `BODY`, and `CAPPED["teams"]` is `(7_000, body[1].text, False)`.
- **R-12 (Minor), accepted.** The rule is kept. D-8 and the README footgun state its cost. L-2 adds a probe reply. The tag-start rule `<(?=[A-Za-z/!?])` is recorded as the D-8 runner-up, to be decided by L-2.
- **R-13 (Minor), accepted.** In D-10, a loose list stays one list, and a line made only of `-`, `*`, `_`, and spaces is a paragraph (`ADF_BREAK_PATTERN`). AC-8 gains both cases.
- **R-14 (Minor), accepted.** HubSpot `hs_timestamp` uses `unittest.mock.ANY`, with its format asserted separately. Confluence compares `json.loads(value)`. `agent_wiring.py:62` moved to "still passes", and the parametrization names are corrected.
- **R-15 (Minor), accepted.** Row 29 edits the README Deadline footgun (:140-148: adds `file_error` and the job-summary-after-deadline case). The two repeated footguns become edits of :115-116 and :119-120. EC-46 is added.
- **R-16 (Minor), accepted.** Row 30 now cites EC-45 and drops the count, which does not exist. Because of that, FR-5 no longer lists row 30, row 30 serves W-15 and W-21, and row 7 gains W-3. NFR-7 now says the timeout is per phase. §8.2 lists Slack and Telegram as the fullwidth cases and the GitHub marker separately.
- **R-17 (Minor), accepted with a variant.** The port in `GITLAB_HOST_PATTERN` is now `[1-9][0-9]{0,4}`, which refuses `0` and leading zeros. `gitlab.py` then reads `urlsplit("https://" + host).port`, which raises above 65,535. The result equals the reviewer's "None or 1–65535" without a numeric literal (A007). EC-27 gains the bad hosts, and the README says "dashed UUID".
- **R-18 (Minor), accepted.** An invalid header name is reported only by its position, and a non-mapping `headers` only by its type name. AC-10 adds the `S3CRET` inputs. INV-11, T-1, NFR-5, D-26, §8.5, and §9.2(b) are updated.
- **Lint.** NFR-6, §12.4, and §12.5 name the seven rules that have room: A002, S061, S001, S017, S025, C011, and C012. S054 has no room; S010 does not cover outputs.

**Final sweep, as checked by script:**
- 18 `## §` headings. FR 35, NFR 10, AC 36, EC 46, D 26, Q 8, INV 18, A 18, L 15, T 6, W 22, with no gaps; every referenced ID is defined.
- The §4 names and keyword arguments match §8.5, and every §8.5 helper is in §12.3.
- 7 CREATE rows equal the 7-file budget.
- Every FR maps to a row through W. FR-34 is the exception: it is covered by a new cross-cutting §C traceability row. Row 6 gains W-11, and row 29 gains W-19 and W-21.
- The regexes pass their stated examples, including the new port and break cases.
- No stale r1 or r2 phrasing remains.
