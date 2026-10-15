# S1 spec review — output-connector-followups (spec r2), round 2

VERDICT: SOUND WITH FIXES — the r2 edits hold, but three things need fixing before the freeze: `OutputHttp`'s new shared `_write` breaks AGENTS.md's one-level call rule, Telegram media blocks still let model output post any https file as the bot, and Teams' "body without its title line" is undefined for the bodies the existing tests send.

## WHAT THE SPEC GETS RIGHT

- R-1 is applied consistently across INV-18, EC-43, AC-5, the §9.2 Telegram row, T-2(c), the row 11 `@intent`, and the README row. `＜` (U+FF1C) is one code point and one UTF-16 unit, so applying the replacement before the 32,768 cap gives the same result as applying it after. Nothing truncates differently, and tables and headings still render, because neither uses `<`.
- The deadline story is now honest. Header line 7's invariant is kept for each single request. EC-38 says a cut during the reads writes nothing. EC-45 says a cut during the write is an ambiguous `network`, including the keyed-issue duplicate on resend. The budget check is left to optional Q-7. All of this is testable through the dispatcher's `asyncio.wait_for(…, 35)` → FAILED `network`.
- The webhook key is consistent everywhere: 24–64 bytes in D-5, AC-14, §8.5, §9.2(b), and the constants. The §4 example `whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw` decodes to exactly 24 bytes, and `whsec_AA==` (1 byte) is refused. AC-14 covers the non-string case without echoing the value, which matters because `OutputArguments.text`, `texts`, `identifier`, `matching`, and `address` all echo `{value!r}` (`base.py:64,71,86,100,107`).
- §13 now carries the facts round 1 asked for. All four new `WIRE_ROWS` rows are listed. The Confluence site is `acme-wiki.atlassian.net`, so it no longer collides with Jira's `acme.atlassian.net` fragment. The job-summary credential `S3CRET-no-such-dir/summary.md` raises `OSError` → `file_error` and leaves no stray file. The `GitHubJobSummaryOutput(credential='***')` repr is stated, and `GITHUB_STEP_SUMMARY` is added to `OUTPUT_ENV_VARS`. The exact patterns block scheme, path, userinfo, traversal, and marker forgery.

## FINDINGS

R-9 [Blocker] [L4] §12.3 row 6, D-2, §8.2 — `OutputHttp.post → _write → _error_code / _link` is a two-level call chain inside one class, which AGENTS.md Style 1 forbids
  Evidence:
    - Row 6: "`post` delegates to the private `_write(destination, request, OutputMethod.POST)`. New `patch` → `_write(..., OutputMethod.PATCH)`." D-2 says the same: "`post` and `patch` share a private `_write(...)`".
    - §8.2 (spec line 958): "`vidbyte/lib/outputs/delivery.py:OutputHttp._error_code`, `_link`: shared by `read` and `_write`."
    - Today `post` calls `OutputHttp._error_code(response)` (`delivery.py:85`) and `OutputHttp._link(response, request)` (`:90`) itself. Moving that body into `_write` pushes both calls one level deeper.
    - AGENTS.md §1: "a function may call another of its own functions, but that second function should not call a third … Calls out to another class … do not count."
    - The spec applies this exact rule to GitHub. D-23 says "send → mode helper → builder would be two levels inside one class", and that is why `GitHubRequests` and `GitHubResponses` exist. It does not apply the rule to `OutputHttp`, and row 6's standards column does not cite Style 1.
  Failure: An implementer who follows row 6 builds `post`/`patch` → `_write` → `_error_code`/`_link` in one class. The `@claude` review raises the convention comment D-23 was written to avoid, and code moves after the tests are frozen.
  Smallest fix:
    - In row 6 and §8.2, move the two response readers into a second static class in `delivery.py`, for example `OutputResponses.error_code(response)` and `OutputResponses.link(response, request)`. Both `_write` and `read` call them. This is the D-23 pattern, and a call into another class does not count toward the limit.
    - Add "Style 1" to row 6's standards column.
    - No public name and no behavior changes.

R-10 [Major] [L7] §10 T-2(c), INV-18, EC-44 — Telegram media blocks still let model output post an attacker-chosen photo, video, or file under the bot's name; T-2(c) only controls the case where the post fails
  Evidence:
    - T-2(c) names the threat "`![](https://…)` media". Its only control is "Media the bot may not send fails the whole message (EC-44)."
    - INV-18: "Markdown links, images, and `tg://user?id=` mentions are not touched".
    - The Bot API copy (`scratchpad/tg_api.txt`) shows the media syntax and rules:
      - `:9575-9586`: Rich Markdown media blocks `![](https://telegram.org/example/photo.jpg)`, `…/video.mp4`, `…/audio.mp3`, `…/animation.gif`, and `…/document.zip`, each with an optional `"caption"`.
      - `:9673`: "Media blocks support only HTTP and HTTPS URLs".
      - `:9850`: "If the message contains a block with a media element, then the bot must have the right to send the media to the chat."
    - The alert T-2(c) relies on (`:5140`) applies only "before opening an inline link". A media block is not a link: Telegram fetches the file and posts it in the message.
  Failure:
    - A prompt-injected reply contains `![](https://attacker.example/payroll-q3.pdf "Updated payroll, please review")` or `…/hotfix.apk`. The injection could come, for example, from an issue body the agent read.
    - In a group where the bot may send media, Telegram downloads the file and posts it as a real document from the bot, with no "Open this link?" prompt. That is the usual state for a bot allowed to post.
    - Where the bot may not send media, EC-44 loses the whole reply.
    - So the media channel either delivers attacker content or drops the reply. Neither branch helps the user.
  Smallest fix:
    - Extend INV-18 so reply text cannot open a media block. Replace `![` with `!［` (U+FF3B: one code point, so the cap stays exact), using a second constant pair next to `TELEGRAM_TAG_*`. This covers inline, reference-style, and `tg://` media links.
    - Add the case to AC-5: a reply holding `![](https://…/x.pdf)` gives markdown that contains `!［](` and no `![`.
    - Reword EC-44 to the literal-text outcome, and update the row 11 `@intent` and the README Telegram row.
    - What is lost is custom-emoji and `tg://time` entities in reply text, which these agents do not produce. This is the same mechanism as R-1, not a new feature.
    - If the author prefers to keep media, T-2(c) and the README must say plainly that reply text can post any https file as the bot.

R-11 [Major] [L10] AC-7, D-9, §12.3 row 12, §13 Teams rows — "the body without its leading title line" is undefined when the body does not open with the title, and that is exactly what the existing Teams wire and cap tests send
  Evidence:
    - D-9: "a body `TextBlock` with the body's leading title line removed, capped at 7,000 and left out when blank." AC-7 covers only "the default shaping (body opens with the title line)". Row 12 names `_body_without_title(content) -> str` but gives no rule.
    - Both existing tests send a body that does not open with its title:
      - `_send_one(…, TITLE, BODY)` calls `connector.send(reply, OutputContent(title, body))` (`test_output_connectors_wire_contract.py:83-87`), where `BODY = "Applying SAVE10 leaves the total unchanged.\n\nSteps: …"`.
      - The cap tests send `OutputContent("Load test", "x" * 7_000)` (`:174-177`).
    - §13 keeps both tests and points `CAPPED["teams"]` at `body[1]` with `cap_includes_title=False`.
    - The first batch already has a rule for "the body opens with the title": `OutputText.chat_text` checks `first_line(body) == title` (`text.py:28-32`), and `first_line` skips blank lines and strips `#`.
  Failure:
    - Three readings are plausible:
      - (a) Always drop the first non-blank line.
      - (b) Drop it only when `first_line(body) == title`.
      - (c) Drop the first line of `chat_text(content)`.
    - Reading (a) turns the cap test's one-line body into a one-block card, so `body[1]` raises IndexError. It also deletes the first sentence of BODY.
    - Reading (c) yields `"\nApplying…"` and fails the expected-BODY comparison.
    - The blind test author and the implementer will choose independently, and the mismatch surfaces only at S3.
  Smallest fix:
    - D-9 and AC-7 state the rule: "When `OutputText.first_line(body) == title`, drop the lines up to and including that first non-blank line, then any leading blank lines. Otherwise use the body unchanged. Cap at 7,000, and leave the block out when the result is blank."
    - Extend AC-7 with a body that does not open with the title.
    - §13 says the Teams `WIRE_ROWS` body block is exactly `BODY`.

R-12 [Minor] [L5] D-8, INV-18, A-4, L-2 — the cost of replacing every `<` is understated, and no live check exercises it
  Evidence:
    - D-8 says only: "code samples then show `＜` in place of `<`". The row 29 README bullet says only "every `<` shows as `＜`". L-2 checks a group, an @channel, a topic, and a 5,000-character reply.
    - The scratch check (`s1r2_regex_out.txt:156-166`) shows what changes:
      - `if a < b` → `if a ＜ b`;
      - `x <= y` → `x ＜= y`, and `a <- b` → `a ＜- b`;
      - `cat <<EOF` → `cat ＜＜EOF`;
      - `Vec<String>` → `Vec＜String>`;
      - `<https://example.com>` → `＜https://example.com>`, so the autolink is lost;
      - a fenced `<div>` and the code span `` `a<b` `` change too.
    - The rule is consistent in intent with Slack's INV-5/D-7 (`<!` and `<@` only), because Telegram's risk is any tag, not only mention syntax.
    - Rich Markdown also parses inline `$…$` formulas (`tg_api.txt:9597`, `$x^2 + y^2$`). Whether prose such as "costs $5 and $10" triggers that is undocumented.
  Failure: A teammate copies `if retries < 3:` or `cat <<EOF` from a Telegram report. The code looks identical but does not run: Python reports "invalid character '＜' (U+FF1C)". The README warns only that `<` "shows as ＜". A-4 ("accepts ordinary reply Markdown") cannot be closed honestly, because nothing sends a `<`-heavy or `$`-bearing reply.
  Smallest fix:
    - Keep the rule.
    - In D-8 and the README Telegram footgun, say that copied code containing `<` will not run, and that `<https://…>` autolinks lose their link form.
    - Add to L-2 a reply holding `<tg-button …>` (expect literal text), `a < b`, a fenced `<div>`, and "costs $5 and $10".
    - Record the tag-start rule `<(?=[A-Za-z/!?])` as the D-8 runner-up. It keeps comparisons and arrows and still changes every tag start (`s1r2_regex_out.txt:167-178`), but whether Telegram accepts a bare `<` is undocumented, so L-2 decides; do not switch now.

R-13 [Minor] [L5] D-10 — the ADF builder breaks loose numbered lists and turns `* * *` dividers into bullets in Jira and Confluence
  Evidence:
    - D-10: "Ordered lists: runs of `N.` or `N)` items → one `orderedList`. Lists are flat"; "Blank lines end a list." Nothing reads the item number.
    - Scratch check (`s1r2_regex_out.txt:16,18,21`): `* * *` and `- - -` match `ADF_BULLET`, and `2026. was a year` matches `ADF_ORDERED`.
  Failure: Model replies often use loose lists, such as `"1. Reproduce\n\n2. Fix\n\n3. Verify"`. Each item becomes its own one-item `orderedList` starting at 1, so the Jira description, the Jira comment, and the Confluence page all show "1. 1. 1.". A `* * *` divider becomes a bullet holding `* *`.
  Smallest fix:
    - In D-10: "a blank line ends a list unless the next non-blank line is an item of the same kind", and "a line made only of `-`, `*`, or `_` characters and spaces is a paragraph".
    - Add both cases to the ADF acceptance rows. No new node types.

R-14 [Minor] [L10] §13 — two of the four new `WIRE_ROWS` cannot be written as exact bodies, and three §13 statements are inexact
  Evidence:
    - `test_each_http_connector_sends_its_documented_request` asserts `send["json_body"] == json_body` (`test_output_connectors_wire_contract.py:101`). §13 asks for each new row's "§9.2(a) URL, headers, and body".
    - HubSpot's `hs_timestamp` is the send time (D-20). §13 says "the test can read these from the request rather than freeze them", but a static `WIRE_ROWS` row cannot read anything.
    - Confluence's `body.value` is a JSON string, `json.dumps(OutputAdf.document(…))`. Its exact text depends on the separators and on the key order inside each ADF node, which D-10 does not fix.
    - `test_output_connectors_agent_wiring.py:62` is listed as "must read `json_body["blocks"][0]["text"]`". Every Slack reply it reads (lines 96, 110, 132, 178) is one line, so the escaped title equals the text and the helper still passes unchanged. This is the same case as `dispatch.py:315`, which §13 already moved to "still passes".
    - §13 says "the env-var and missing-credential tests are parametrized over `CONNECTOR_CASES`". They are actually parametrized over `HTTP_DESTINATION_KEYS` (`test_output_connectors_configuration.py:178`) and `ALL_DESTINATION_KEYS` (`:193`). The outcome holds: EC-28's message matches the exact format asserted at `:203`.
  Failure: A blind test author writes a literal timestamp or an exact `value` string. The HubSpot row then fails on every run, and the Confluence row fails as soon as the implementer orders a node's keys differently.
  Smallest fix:
    - In §13, say the HubSpot row uses `unittest.mock.ANY` for `hs_timestamp`, with its format asserted separately.
    - Say the Confluence row compares `json.loads(value)`, or have D-10 pin node key order and default separators.
    - Move `agent_wiring.py:62` to "still passes".
    - Correct the two parametrization names.

R-15 [Minor] [L8] §12.3 row 29 — the README pass leaves the existing "Deadline" footgun stale and duplicates two footguns that already exist
  Evidence:
    - `vidbyte/lib/outputs/README.md:140-148` lists the resend-caution codes "`network`, `invalid_response`, `smtp_error`, or `smtp_recipients_refused`, or starts with `http_5`". It explains only that "an SMTP send may still finish afterwards", because SMTP runs on its own worker thread.
    - Row 27 adds `file_error` to `OutputDeliveryError`'s list, and row 30 adds it to `vidbyte/agents/output/README.md`. Row 29 adds a separate "`file_error` …" footgun but never edits :144-148.
    - D-18 runs the summary append on its own single-worker executor, the same shape as SMTP. So a deadline cut gives FAILED `network` while the append still lands. No EC row or README line says so.
    - Row 29's new "labels dropped without push access" and "scoped Atlassian tokens" bullets already exist at :115-116 and :119-120.
  Failure: The README ends up with two different lists of codes that "may already have been delivered", and the footgun list grows with repeats.
  Smallest fix:
    - Row 29: edit :140-148 to add `file_error`, and add that the job-summary append, like SMTP, can finish after the deadline.
    - Add a matching EC row next to EC-45.
    - Turn the two duplicate bullets into edits of the existing GitHub and Jira bullets.

R-16 [Minor] [L9] §12.3 row 30, NFR-7, §8.2 — leftovers still describe the r1 deadline wording, a count that does not exist, and the GitHub marker as fullwidth
  Evidence:
    - Row 30: "Note that one connector `send` may make several requests (reads, then one write) inside the unchanged deadline". NFR-7 and EC-45 now say the deadline may cut such a send.
    - Row 30: "The connector count becomes 16". `vidbyte/agents/output/README.md` has no count; line 7 reads "The provider classes (Slack, email, GitHub, and the rest)".
    - NFR-7: "Each HTTP attempt has a 10 s timeout (INV-4)". httpx applies the 10 s to each phase, so a response that trickles bytes keeps one attempt open until the 35 s deadline. The first-batch FEATURE.md already notes that a trickling endpoint holds `run()`.
    - §8.2: "Length-preserving mention neutralization with a fullwidth `＜`. Slack, and the GitHub marker." D-16's GitHub replacement `<!-- vidbyte-quoted:` is neither fullwidth nor length-preserving, and Telegram (INV-18), which does use `＜`, is missing.
  Failure: The implementer writes a README line that contradicts EC-45 and looks for a count to change. An S3 reviewer reads §8.2 as requiring a fullwidth GitHub replacement.
  Smallest fix:
    - Row 30: "…may make several requests (reads, then one write), and the deadline may cut it (EC-45)". Delete the count sentence.
    - NFR-7: "each attempt has a 10 s timeout per phase".
    - §8.2: "Slack and Telegram". List the GitHub marker replacement as its own, non-fullwidth item.

R-17 [Minor] [L5] §9.2(b) GitLab `host`, §12.3 row 3 — `GITLAB_HOST_PATTERN` accepts ports 0 and 65,536–99,999, so a bad port passes construction and fails only at send, against INV-11
  Evidence:
    - The pattern ends `(?::[0-9]{1,5})?`. Scratch check: `gitlab.com:99999` → True and `gitlab.com:0` → True (`s1r2_regex_out.txt:61-62`).
    - httpx 0.28.1 builds a request to `https://gitlab.com:99999/…` without error. Only `urllib.parse.urlsplit(...).port` raises.
    - INV-11: "Every invalid argument … raises `ConfigurationError` at construction". The first batch's `https_url` checks the port, and `test_output_connectors_configuration.py:55` (`slack-port-out-of-range`, port 70000) pins construction-time rejection for URLs.
  Failure: `GitLabIssueOutput(project="acme/shop", host="gitlab.acme.dev:84430")`, a typo for 8443, constructs fine. Every send then fails at the network layer instead of raising a `ConfigurationError` that names `host`.
  Smallest fix:
    - Row 3 and §9.2(b): after the pattern, require `urlsplit("https://" + host).port` to be None or 1–65535, the same check `https_url` makes.
    - Add `host="gitlab.com:99999"` to the invalid-argument examples.
    - Aside: `LINEAR_ISSUE_REF_PATTERN` rejects the compact 32-hex UUID that `OutputArguments.identifier` accepts for Linear `labels`. That is harmless, since Linear issue ids are dashed, but the README should say "dashed UUID".

R-18 [Minor] [L7] AC-10, §9.2(b) Webhook `headers` — "errors name the header" echoes a secret when the name itself holds it
  Evidence:
    - AC-10: "A header name with a space or colon … raises `ConfigurationError` naming `headers` and the header name, never its value." §9.2(b) says the same.
    - A name with a colon is what a pasted curl line produces: `headers={"Authorization: Bearer sk-live-…": ""}`. A list such as `headers=["Authorization: Bearer sk-live-…"]` has no stated error rule, and the nearest precedent, `OutputArguments.texts`, echoes `{value!r}` (`base.py:71`).
    - T-1 names this actor: "Careless user … logs an error".
  Failure: The `ConfigurationError` text, which reaches logs and CI output, contains `Authorization: Bearer sk-live-…`.
  Smallest fix:
    - AC-10 and §9.2(b): report a name that fails the token pattern only up to its first space or colon, or by position. Report a non-Mapping `headers` by type name only.
    - Put `S3CRET` inside the bad name and inside a list in AC-10's input.

## VERIFIED CLAIMS

- Webhook key (D-5, AC-14, §9.2(b), constants) — **held**.
  - `whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw` decodes to 24 bytes, `whsec_AA==` to 1 byte (refused), and 86 `A` + `==` to 64 bytes; 66 bytes is refused.
  - Strict base64 refuses a leading space, a trailing `\n`, and URL-safe `-`. This fails loudly at construction, though unlike `credential()` it does not strip.
  - AC-14 forbids echoing a non-string secret.
- Telegram facts (D-8, A-4) — **held**.
  - "Up to 32768 UTF-8 characters" holds, and Rich Markdown "can contain arbitrary HTML" (`tg_api.txt:9671`).
  - `<tg-button>` exists only as an HTML tag, so INV-18 closes buttons.
  - `＜` is 1 code point, 1 UTF-16 unit, and 3 UTF-8 bytes, so the cap gives the same result before or after the replacement.
  - The media blocks and the media-rights rule are confirmed (`:9575-9586`, `:9673`, `:9850`) and lead to R-10.
- INV-18 and Slack INV-5 (D-7) — **held** (consistent in intent). Slack's block replaces only `<!` and `<@`; the §13 mention expectation `"＜!channel> & @everyone <users/all>"` is exact.
- Deadline (NFR-7, EC-38, EC-45, header line 7) — **held**, except NFR-7's per-attempt wording (R-16).
  - The constants header line 7 invariant is kept as stated.
  - The dispatcher wraps `connector.send` in `asyncio.wait_for(…, 35)` and maps the timeout to FAILED `network`.
  - The transport retries a 429 after 0.5 s and then 1.0 s.
- Regex patterns (§12.3 row 3), run in `scratchpad/s1r2_regex_check.py`:
  - `GITLAB_HOST_PATTERN` **held** for T-3: it refuses `user@host`, `host/path`, `https://…`, `#`, `?`, `evil.com\@gitlab.com`, and `[::1]`. It **failed** on port range (R-17).
  - `GITLAB_PROJECT_PATH_PATTERN` **held**: it refuses `acme shop`, `../x`, `shop`, `acme/../x`, `acme/.hidden`, `acme/-x`, a trailing `/`, and `//`, and `quote(…, safe="")` gives `acme%2Fshop`.
  - `LINEAR_ISSUE_REF_PATTERN` **held** for `ENG-123`, `eng-123`, and a dashed UUID in either case; it refuses a compact UUID (aside in R-17).
  - `OUTPUT_HEADER_NAME_PATTERN` **held**: it refuses `x api`, `x:y`, and `Authorization: Bearer abc`.
  - `GITHUB_KEY_PATTERN` **held**: it refuses `-->` and `<!--`, and the `vidbyte-quoted:` replacement cannot recreate a marker.
  - `JIRA_ISSUE_KEY_PATTERN` **held**.
  - The ADF patterns **held** for `## `, `-`/`*`/`+` bullets (indented or tabbed), `1.`/`1)`, fences, and EC-14's `- ` → paragraph. They **failed** on thematic breaks and loose lists (R-13).
- Lint (NFR-6, §12.4) — **held**. Base gives `SDK-LINT: PASS`, with A002 at 579/703 and S061 at 5/6.
  - Other rules with room: S001 56/59, S017 78/79 (no-raw-exception-disclosure), S025 261/263, C011 1/2, C012 23/24, and S010 0/5. S010 is scoped to runners, providers, and builtins, so it does not cover outputs.
  - S054 is at 3/3 with no room, and it covers Ruff S105–S108.
- §11 commands — **held**. `lint/run.py --rule … --all`, `scripts/run_ci.py --stage {all,source,package}`, `scripts/generate-sdk-public-api.py --check`, and `.semgrep/typed-mapping-boundary-policy.yml` all exist.
- README line references (row 29) — **held** for :19, :37, :44, :46-49, :50, :62-72, :74 ("Retrieved 2026-10-11."), :98-102, :110, and :137. :140-148 is **missed** (R-15).
- Row 30 "connector count becomes 16" — **failed**: no count exists (R-16).
- "eleven" appears only at `vidbyte/__init__.py:20`, `vidbyte/agents/output/__init__.py:3`, and `vidbyte/lib/outputs/base.py:4`, which rows 26, 25, and 7 cover — **held**.
- §13 re-walk — **held** for all of these, with exceptions in R-14 and R-11:
  - `WIRE_ROWS` Slack, Teams, and Telegram edits; `CAPPED` Teams and Telegram;
  - dispatch `:124/:125/:147/:148`, and `:315` still passing;
  - acceptance `:97`;
  - `ROOT_NAMES` 18 → 24 with `CONNECTOR_NAMES = ROOT_NAMES[7:]`; `LIB_OUTPUT_MODULES` +7; ordered destinations +5;
  - the operational-constants and docs-date tests;
  - the factories, including the literal `(*HTTP_DESTINATION_KEYS, "email")`;
  - the distinct Confluence site and the job-summary missing-directory credential;
  - the repr at `contract.py:112` and `security.py:82`;
  - `GITHUB_STEP_SUMMARY` cleared by `isolated_output_env`;
  - `**kwargs` fakes and `scripts/test-async-http-transport.py:115` surviving.
- EC-28's message equals the missing-credential test's exact format (`test_output_connectors_configuration.py:193-203`) — **held**.
- EC-42 now covers both the overwrite branch and the 403 branch, and the README footgun matches — **held**.
- D-23's Style 1 reasoning for GitHub — **held**. The same reasoning is not applied to `OutputHttp` (`delivery.py:85,90` today) — **failed** (R-9).
- The first batch's `https_url` rejects out-of-range ports via `urlsplit().port`; httpx 0.28.1 does not — **verified** (R-17).
