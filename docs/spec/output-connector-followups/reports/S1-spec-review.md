# S1 spec review — output-connector-followups (spec r1), round 1

VERDICT: SOUND WITH FIXES — the design holds up and its vendor facts mostly check out, but four things need fixing. Telegram's new rich-Markdown path opens an HTML/button channel to model output that the spec never examined. The NFR-7 "inside 35 s" bound does not hold. The §13 "update exactly these" test list misses edits that existing parametrized tests force. Several regexes are left for the implementer to invent.

## WHAT THE SPEC GETS RIGHT

- It handles the request's §C corrections correctly. `webhook-id` is generated once per send, not taken from the local idempotency key, which `_require_idempotency_guard` never sends. Exact-bytes signing goes through a defaulted `content=` keyword on the canonical `HttpTransport` and is threaded through `OutputRequest.content`. All `_send_once` callers and fakes keep working: the fakes take `**kwargs`, and `scripts/test-async-http-transport.py:115` passes explicit keywords.
- New abilities are keyword arguments on existing connectors (D-1). Enums, constants, and records go where AGENTS.md puts them. The job-summary append uses `LocalFileSystemBackend.append_text` on a single-worker executor, which satisfies S061, S047, and S052 with the same pattern as `email.py`. The import probe showed `local.py` loads 0 new modules after `vidbyte.lib.outputs`.
- INV-1 is sound: every read happens first, a read failure writes nothing, and there is at most one write. Discovery uses the list endpoints, never search. Markers in reply text are neutralized before truncation (D-16), so a forged marker cannot survive a cut.
- Most vendor claims checked out against primary docs. Confluence create returns 200. Notion `insert_content` exists and its response has no url. The Standard Webhooks format matches. Typefully's draft is the default, with `private_url` on 201. Linear accepts `LIN-123` identifiers. Telegram's 32,768 limit and `message_thread_id` match. Items the docs do not settle are honestly carried as A-n or L-n (A-1, A-2, A-7, A-9, A-12).

## FINDINGS

R-1 [Major] [L7] §10 T-2(c), D-8, §12.3 row 11 — Telegram rich Markdown passes arbitrary HTML, including inline buttons, so model output can attach buttons to the bot's message
  Evidence:
    - The Bot API (local copy `scratchpad/tg_api.txt:9671`) says: "Rich Markdown is compatible with GitHub Flavored Markdown where possible and can contain arbitrary HTML. Supported rich message HTML tags are parsed as described in Rich HTML style."
    - The Rich HTML examples (`:9637-9641`) include `<tg-button type="callback_data" data="…">`, `type="web_app"`, `type="login_url"`, and `type="url" url="tg://user?id=777000"`.
    - Rich Markdown also supports `[inline mention of a user](tg://user?id=123456789)` (`:9545`), media `![](https://…)`, and `tg://photo?id=` reuse links (`:9524`).
    - T-2(c) considers only "hidden links" and accepts them because of the link alert.
    - Row 11 tells the implementer to write an `@intent` stating that rich Markdown "has no mention ping". That is false: the inline mention notifies by user id, and the README footgun already says Telegram `@username` notifies.
  Failure:
    - A prompt-injected reply containing `<tg-button type="callback_data" data="approve:deploy">Approve</tg-button>` is posted as a real inline button under the bot's name.
    - If the same bot token also backs an app that handles callback queries, a teammate who clicks it sends forged callback data to that app.
    - `[x](tg://user?id=N)` pings any user by id.
    - `![](https://attacker/…)` makes Telegram fetch the URL. If the bot lacks media rights in the chat, the whole send fails with HTTP 400 and the reply is lost.
  Smallest fix:
    - Before capping, neutralize every `<` in the Telegram Markdown to fullwidth `＜`. This is the same mechanism INV-5 uses for Slack, and it removes the whole HTML channel (`tg-button`, `tg-map`, raw `<a>`). The narrower option is to neutralize only `<tg-` sequences, case-insensitive.
    - Add an INV ("Telegram requests carry no HTML tag from reply text").
    - Rewrite row 11's `@intent` and the T-2(c) row to say that personal mentions, including `tg://user?id=`, notify, matching the README "Personal mentions" footgun.
    - Add an EC row: media without media rights → FAILED `http_400`.
    - Optional [scope-adding] Q-n: send `skip_entity_detection: true`. Default: not built.

R-2 [Major] [L5] §7 NFR-7, EC-38, §12.3 row 3 — "at most 10 reads + 1 write, all inside the unchanged 35 s deadline" is not a bound the design can meet
  Evidence:
    - `HttpTransport.request` makes `retry_count + 1` attempts with `asyncio.sleep(delay)` between them, at 0.5 s and then 1.0 s (`vidbyte/lib/http/transport.py:58-67`).
    - The outputs use `OUTPUT_RETRY_STATUS_CODES = (429,)`, retried twice, with a 10 s timeout. httpx timeouts apply per phase, not per request.
    - So one request alone can take about 31.5 s. That is exactly why the constants header line 7 says "The delivery deadline must stay above three request timeouts plus the 429 backoff". The spec rewrites that line instead of keeping the invariant.
    - EC-38 covers a cut that lands during the reads, but not one that lands during the write.
  Failure:
    - A sticky send whose first GET is rate-limited once spends about 0.5 s plus the read time. Two slow reads leave less than one write's budget.
    - The dispatcher's `asyncio.wait_for(…, 35)` can cancel the PATCH or POST after GitHub has applied it, giving FAILED `network` for a write that happened.
    - In keyed-issue mode (FR-32), if the cut lands on a create that GitHub applied, the resend finds the new issue and POSTs the same text again as a comment, which is a visible duplicate.
    - NFR-7 is a P0 requirement that no test can show and that the implementation cannot satisfy.
  Smallest fix:
    - Restate NFR-7 honestly: each attempt is under 10 s; a multi-request send may be cut by the 35 s deadline; a cut during the reads writes nothing; a cut during the write is ambiguous, which is the existing `network` resend caution.
    - Add an EC row for a cut during the write, including the keyed-issue duplicate comment on resend.
    - Optional Q-n, default not built: skip the write and return FAILED `network` when the remaining budget is below one write's worst case.

R-3 [Major] [L10] §13 "Update exactly these" — the list misses edits that the new keys force on existing parametrized tests, and one factory choice silently breaks a test
  Evidence:
    - (a) `test_each_http_connector_sends_its_documented_request` (`test_output_connectors_wire_contract.py:92-107`) is parametrized over `HTTP_DESTINATION_KEYS` and indexes `WIRE_ROWS[key]`. Adding four HTTP keys without four new `WIRE_ROWS` rows raises KeyError. The spec lists only the Slack, Teams, and Telegram row edits.
    - (b) `test_each_credential_travels_only_in_its_own_destinations_request` (`test_output_connectors_security.py:100-112`) answers every case by `case.host` and unpacks `[send] = fake_http.sends_to(case.host)`. The Jira row's host fragment is `"acme.atlassian.net"` (`factories.py:106`). If the Confluence row reuses the AC-23 site `acme.atlassian.net`, both routes match both URLs: the unpack fails, and Jira's scripted 201 can be consumed by Confluence's POST. `httpx_destination` keys routes by `request.url.host`, so the two also collide there.
    - (c) `test_no_surface_shows_the_credential_even_when_the_destination_echoes_it` (`security.py:55`, `any_case` over `ALL_DESTINATION_KEYS`) expects `pytest.raises(OutputDeliveryError)` with one `failed` receipt. For `github_job_summary`, `_arrange_echoing_failure` only scripts HTTP. A placeholder "credential" such as a bare `S3CRET…` filename is appended relative to the current working directory. The send is SENT, the test fails, and a stray file lands in the repo.
    - (d) `contract.py:112` and `security.py:82` assert `repr(connector) == f"{class_name}(credential='***')"` for every `any_case`, which constrains the job summary's repr. The spec never states that form for it.
    - (e) `dispatch.py:315` is listed as changing. In fact it still passes, because the title equals the one-line text. This is harmless, but "exactly these" is then not exact.
  Failure: an S2 test author who follows §13 literally ends with red, KeyError, or collision failures in the wire-contract, security, and contract tests, and has to rediscover the factory constraints.
  Smallest fix: add these to §13:
    - four new `WIRE_ROWS` rows, all POST, 10.0 s, and 1,000,000 bytes;
    - "the Confluence `ConnectorCase` uses a site distinct from Jira's, for example `acme-wiki.atlassian.net`";
    - "the job-summary `ConnectorCase` credential is a path under a missing directory containing `S3CRET`, so the append raises `OSError` → FAILED `file_error`";
    - "`GitHubJobSummaryOutput` repr is `GitHubJobSummaryOutput(credential='***')`".
  Then drop `:315` from the changed list.

R-4 [Minor] [L8] §7 NFR-6, §12.4 — "`SDK-LINT: PASS`, no baseline raised" cannot catch new A002 or S061 violations, because those rules have slack
  Evidence: `lint/run.py` is count-ratcheted: a rule regresses only when its count exceeds the allowance. Current counts against the baseline are A002 579/703 (124 slack) and S061 5/6 (1 slack). The other cited rules have no slack: A001 643/643, A007 255/255, S008 19/19, S024 25/25, S051 259/259.
  Failure: a new `send` or `_signed_headers` without `@intent`, or a raw `path.open("a")` in `github_job_summary.py`, still prints PASS. The spec relies on A002 `@intent`s for rows 7, 11, 14, and 20, and on S061 for D-18.
  Smallest fix: in NFR-6 and §12.4, require `python lint/run.py --rule A002 --all` and `--rule S061 --all` to show no finding in any file this change touches.

R-5 [Minor] [L8] §12.3 row 29 — the README pass misses existing lines that the change makes false
  Evidence (`vidbyte/lib/outputs/README.md`):
    - :19 Non-goals: "Every destination takes one pasted credential". The job summary takes a path, or nothing.
    - :37 Modules: `delivery.py` is "the single JSON `POST`". It now also does PATCH, GET, and exact bytes.
    - :44 `telegram.py` is "a bot `sendMessage` call".
    - :46-49 GitHub, Linear, Jira, and Notion are each "a new …" issue or page. They now also comment or append.
    - :50 `webhook.py` is "a JSON `POST`".
    - :98-102 "How To Add A Destination" step 3: "only `__init__` and `send` … send through `OutputHttp.post` or `OutputSmtp.send`". The spec's connectors add private static helpers and `OutputHttp.patch`/`read`, and the job summary uses the executor.
    - :137 "Personal mentions" lists Telegram `@username` only.
  Row 29's detail adds new Modules lines and footguns but edits none of these.
  Failure: the README contradicts the code, the kind of thing a convention-review comment flags on a docs pass this PR claims to do.
  Smallest fix: add a bullet to row 29 to update those seven lines, and add the Telegram inline-mention case (R-1) to the "Personal mentions" footgun.

R-6 [Minor] [L3] §9.2(b), §12.3 row 3 — four argument patterns are named but never given, so the test author and the implementer will diverge
  Evidence:
    - `LINEAR_ISSUE_REF_PATTERN` ("a team-key identifier such as `ENG-123`, or a UUID"), `GITLAB_HOST_PATTERN` ("a bare host with an optional port"), `GITLAB_PROJECT_PATH_PATTERN` ("namespace/…/name"), and `ADF_HEADING_PATTERN`, `ADF_BULLET_PATTERN`, and `ADF_ORDERED_PATTERN` have no values (spec :819, :825-826, :1074, :1080, :1084).
    - Every sibling pattern has one: `JIRA_ISSUE_KEY_PATTERN`, `CONFLUENCE_ID_PATTERN`, `GITHUB_KEY_PATTERN`, and `OUTPUT_HEADER_NAME_PATTERN`.
  Failure:
    - It is undecided whether `eng-123`, an uppercase UUID, `gitlab.example.com:8443`, `1. ` versus `1) `, or `*` versus `-` bullets are accepted.
    - T-3's "blocks scheme, path, and userinfo tricks" mitigation depends on a regex nobody wrote.
    - INV-2's Jira byte-identity holds only for "a body with no Markdown block syntax", which these undefined patterns define.
  Smallest fix: give each pattern as an exact `r"…"` value in the row-3 constants list.

R-7 [Minor] [L7] §6.3 EC-42, §10 T-2(d) — the planted-marker row covers only the "token can edit" branch, not the permanent-failure branch
  Evidence:
    - D-14 and FR-31 PATCH the oldest marked comment.
    - EC-42 assumes the token can edit the planted comment. A token without rights to edit another user's comment gets 403.
  Failure: a commenter posts `<!-- vidbyte:ci-review -->` on a PR before the bot's first run. The key is readable in a public workflow file. Every later send on that PR PATCHes the human's comment, gets FAILED `http_403`, and never posts. Because the oldest match wins, this lasts for the life of the PR.
  Smallest fix:
    - Add the 403 branch to EC-42 and to the README planted-marker footgun.
    - Optional [scope-adding] Q-n: match only comments whose `user.type` is `Bot` or whose author is the token's login. Default: not built.

R-8 [Minor] [L4] §9.2(b) Webhook `secret` — `signing_key` accepts a 1-byte key, but the format the spec adopts sets 24–64 bytes
  Evidence: Standard Webhooks spec (standardwebhooks.com, read in this review): the secret is "Between 24 bytes and 64 bytes". The spec at :816 says "decodes to at least one byte".
  Failure: `secret="whsec_AA=="` is accepted and signs with a 1-byte HMAC key, which is brute-forceable. Receivers on the reference libraries may also reject such secrets at setup.
  Smallest fix: `signing_key` requires 24–64 decoded bytes, with the error naming `secret` and never echoing it. Name a `WEBHOOK_KEY_MIN_BYTES` constant, plus a max constant, for A007.

## VERIFIED CLAIMS

- `HttpTransport.request` and `_send_once` match the code-map signatures. `_send_once` serializes `json.dumps(json_body)` itself, and `idempotency_key` is used only by `_require_idempotency_guard`, never sent. Every `_send_once` caller (four fakes with `**kwargs`, plus the real call at `scripts/test-async-http-transport.py:115`) survives a defaulted `content`. `VidbyteGatewayTransport.request` (`vidbyte/lib/http/vidbyte_gateway.py:141`) takes `**transport_options` and stays override-compatible. HELD.
- S010 checks caller-mode parity, not signature parity, so adding `content` to the async path only is fine. S056 needs only `idempotency_key`. HELD.
- S008 is Ruff C901, PLR0912, and PLR0915 at the defaults 10/12/50 (`lint/ruff.toml` selects only TID251). S024 has a maximum depth of 3. HELD.
- A002 matches on identifier segments split by `_` and `.`, with tokens such as secret, request, send, fetch, transport, and retry. HELD, but the rule has 124 slack (R-4).
- S061's allowlist is only `vidbyte/lib/tools/filesystem/backends/local.py`. `append_text(path, content, *, encoding, create_parents, newline=None)` is synchronous. HELD.
- Confluence v2 create page returns 200, and 413 above 5 MB. Query parameters are `embedded`, `private`, and `root-level`. HELD.
- Notion `PATCH /v1/pages/{id}/markdown`: `insert_content` is "still supported but may be deprecated", omitting the position appends at the end, version is `2026-03-11`, and the response is a `page_markdown` object with no url. HELD.
- Standard Webhooks:
  - The id is the same across retries.
  - The timestamp is integer seconds.
  - The signed content is `id.timestamp.payload`.
  - The signature is `v1,<base64>`.
  - The secret is base64 with a `whsec_` prefix.
  - The decoding of the HMAC key is not stated, so A-7 is correctly marked as an assumption.
  HELD. The 24–64-byte secret length is R-8.
- Typefully v2: `POST /v2/social-sets/{id}/drafts` with Bearer auth; `platforms` is required; omitting `publish_at` makes a draft; a 201 carries `private_url`. HELD. The docs type `social_set_id` as an integer. The spec's string pattern is harmless in a URL path, and A-12 covers it.
- Slack `markdown` block: the 12,000-character cumulative limit and the "Messages" surface. Incoming-webhook support and mention handling are not documented, so A-1 and A-2 are correctly unverified. HELD.
- Telegram `sendRichMessage`: `rich_message` takes exactly one of `html`, `markdown`, or `blocks`; the limit is 32,768 characters; `message_thread_id` applies to "forum supergroups and private chats … forum topic mode". HELD. T-2(c) and row 11's "no mention ping" did NOT hold (R-1).
- Linear `CommentCreateInput.issueId` "Can be a UUID or issue identifier (e.g., 'LIN-123')". `labelIds` is `[String!]`. `CommentPayload` has `comment`. HELD.
- Code-map line facts HELD:
  - `delivery.py`: `_OUTPUT_POST_ACTIVE` at :49 and the hard-coded POST at :67.
  - The `OutputRequest` docstring reads "One HTTPS JSON POST".
  - The constants header deadline rule is at line 7, with `OUTPUT_DELIVERY_DEADLINE_SECONDS = 35.0`.
  - The dispatcher wraps each send in `wait_for(…, 35)`.
  - The `OutputDeliveryError` resend caution lists `network`.
  - The README has `## Modules`, no `## Notes for agents`, and about 11.7 K characters.
  - "eleven" appears at `vidbyte/__init__.py:20`, `vidbyte/agents/output/__init__.py:3`, and `vidbyte/lib/outputs/base.py:4`.
- D-9: for a plain reply, `OutputShaping` makes the body the full text and the title its first line, so the body starts with the title. HELD.
- `llms.txt` and `artifacts/file_index.md` name no output connector (spec :1212). HELD.
- First-batch WIRE_ROWS still match where §13 says they stay unchanged: every HTTP row asserts `method == "POST"`, `timeout_seconds == 10.0`, and `max_response_bytes == 1_000_000`, and all four new HTTP connectors POST. HELD. The rows the new keys require are R-3(a).
