# S6 PR author — output-connector-followups (PR #882)

Status: DONE. HEAD `ffb7a52c` pushed; PR #882 title and body replaced; still a draft; 4/4 check runs green on `b1c32edd` (the commit CI ran on; every later commit is docs/spec only).

## 1. What the code does (from the diff, before the specs)

Written after reading `git diff 336d6c78...HEAD` (source files in full) and before opening either spec.

**The path is unchanged above the connector.** `agent.run()` → `BaseAgent._generate_reply` records the reply, runs the schema check, then `_deliver_outputs` → `OutputDispatcher.deliver` (skip rule, `asyncio.gather` of `_deliver_one`, each under `asyncio.wait_for(…, 35 s)`, receipts in configured order into `reply.metadata["deliveries"]`, `OutputDeliveryError` after all finish). `vidbyte/agents/base.py`, `vidbyte/agents/output/{dispatcher,connector}.py`, `fork.py`, `jev/`, `google_chat.py`, `email.py`, `text.py`, `pyproject.toml`, and `lint/` have no change in `336d6c78...HEAD`. Everything new happens inside each connector's `send` or below it.

**Shared plumbing.**
- `HttpTransport.request(content=)` (`vidbyte/lib/http/transport.py`): exact bytes go out verbatim with no content-type added; `json_body` and `content` together raise `ProviderRequestError` before any send.
- `OutputRequest` (`vidbyte/lib/dataclasses/outputs.py`): `json_body` may now be `None`; new `content: bytes | None`; both set is refused. New `OutputRead(failure, data)`: a read's parsed JSON or the FAILED receipt that ends the send.
- `OutputHttp` (`vidbyte/lib/outputs/delivery.py`): `post` and new `patch` share `_write` (429-only retry ×2, no redirects, 1 MB write ceiling, httpx URL log line dropped). New `read` = GET with the same retry/redirect rules and its own 16 MB ceiling (`OUTPUT_MAX_READ_BYTES`); non-2xx → FAILED `http_<n>`, non-JSON → FAILED `invalid_response`, transport error/oversize → FAILED `network`. `basic_authorization` builds the Atlassian Basic header once. Response helpers moved to `OutputResponses` (`error_code`, `link`).
- `OutputArguments` (`vidbyte/lib/outputs/base.py`): new `flag`, `number`, `reference`, `members`, `headers` (RFC 9110 token names, lowercased, no CR/LF/NUL in values, no case-insensitive duplicates, errors never echo a value or a bad name), `signing_key` (optional `whsec_` + strict base64, 24–64 decoded bytes, never echoed), `exclusive` (at most one / exactly one of a set; `None` and empty list count as unset).
- `OutputAdf` (`vidbyte/lib/outputs/adf.py`): line-by-line Markdown → ADF: `#`–`######` headings, flat bullet and ordered lists (runs grouped by kind; a thematic break stays a paragraph), fenced code blocks with a language attr (unclosed fence runs to end), everything else a paragraph kept as written. No inline marks. Empty code blocks and blank lines add nothing.
- Enums: `OutputDestination` +5 members; new `OutputMethod` (GET/POST/PATCH); new `TypefullyPlatform` (x, linkedin, threads, bluesky, mastodon). New error code `file_error`, added to the "may already have been delivered" list in `OutputDeliveryError`'s resend hint.

**Changed connectors (all keyword-only additions with defaults; first-batch calls still build).**
- Slack: chat text ≤ 12,000 chars → `{"text": <escaped one-line title>, "blocks": [{"type": "markdown", "text": …}]}` with `<!`→`＜!` and `<@`→`＜@`; longer → first-batch escaped plain text (cap 40,000).
- Telegram: `sendRichMessage` with `{"chat_id", "rich_message": {"markdown": …}}` cut at 32,768; every `<`→`＜` and `![`→`!［`; new `topic_id=` → `message_thread_id`. (First batch: `sendMessage`, plain text, 4,096.)
- Teams: card has `msteams.width = "Full"`, a bold Medium title TextBlock, then a body TextBlock with the title line removed when the body opens with it.
- Discord: `forum=True` adds `thread_name` (one-line title, 100 chars); `forum_tags=` (snowflake strings) adds `applied_tags`, refused without `forum=True`.
- Jira: description is `OutputAdf.document(body)` (was one paragraph per line); `labels=` (no spaces); `comment_on="PROJ-123"` posts an ADF comment, link `https://{site}/browse/{key}?focusedCommentId={id}`. `project` now optional; exactly one of `project` / `comment_on`.
- Linear: `labels=` (UUIDs → `labelIds`); `comment_on=` (team key or UUID) → GraphQL `commentCreate`, link `data.commentCreate.comment.url`. `team_id` now optional; exactly one of the two.
- Notion: `append_to=<page UUID>` → `PATCH /v1/pages/{id}/markdown` with `insert_content`, mentions neutralized, no link. `parent_page_id` now optional; exactly one of the two.
- GitHub: four modes in `send` — new issue (unchanged); `comment_on=N` → POST comment (chat text); `comment_on=N, key=k` → read comment pages (100/page, ≤10 pages) for `<!-- vidbyte:k -->`, PATCH the oldest marked one or POST a new marked one; `key=k` alone → GET open issues labelled `vidbyte:k` (oldest first, one page), POST a comment on the first non-PR one or POST the issue with that label added. Every body quotes `<!-- vidbyte:` → `<!-- vidbyte-quoted:` before cutting. `labels` and `comment_on` are exclusive. Builders/readers in new `github_api.py`.
- Webhook: `headers=`, `payload=` (any Mapping copied to a dict; non-Mapping → `TypeError` → FAILED `unexpected:TypeError`), `secret=` → Standard Webhooks signing over the exact bytes sent as `content=`; signing headers overwrite caller headers. Unsigned path unchanged.

**New connectors.** `GitLabIssueOutput` (PRIVATE-TOKEN; issue linked by `web_url`, or MR note with no link; bare host[:port]; URL-encoded project path) · `GitHubJobSummaryOutput` (path from argument or `GITHUB_STEP_SUMMARY`; append through `LocalFileSystemBackend.append_text(create_parents=False)` on a one-thread executor; `OSError` → `file_error`) · `ConfluencePageOutput` (v2 pages, `atlas_doc_format` JSON string, link `https://{site}/wiki` + `_links.webui`) · `TypefullyDraftOutput` (v2 drafts, one post per platform, never publish/schedule, link `private_url`) · `HubSpotTaskOutput` (CRM v3 task, `hs_timestamp` = send time UTC ms, no owner/association, no link).

**Exports.** Root `vidbyte` +6 (`ConfluencePageOutput`, `GitHubJobSummaryOutput`, `GitLabIssueOutput`, `HubSpotTaskOutput`, `TypefullyDraftOutput`, `TypefullyPlatform`) = 24 output names; `vidbyte.lib.outputs` also exports `OutputAdf`; `vidbyte.lib.enums` exports `OutputMethod` and `TypefullyPlatform`. Contract 630 exports, `--check` current.

## 2. Snippet run

Spec §4 runs as written (no deviation, AC-1 holds). Scratch script `…/scratchpad/run_s4_snippet.py` (outside the worktree): `HttpTransport._send_once` patched, `AnswerRunner` bound with `bind_test_runner`, real job-summary temp file, two runs on one agent. Output:

```text
--- run 1
github_issue sent https://github.com/acme/shop/pull/412#issuecomment-2400000001
github_job_summary sent None
discord sent None
telegram sent None
webhook sent None
requests: ['GET https://api.github.com/repos/acme/shop/issues/412/comments', 'POST https://api.github.com/repos/acme/shop/issues/412/comments', 'POST https://discord.com/api/webhooks/1/fake', 'POST https://api.telegram.org/bot<token>/sendRichMessage', 'POST https://hook.eu1.make.com/fake']
--- run 2
(same five lines)
requests: ['GET https://api.github.com/repos/acme/shop/issues/412/comments', 'PATCH https://api.github.com/repos/acme/shop/issues/comments/2400000001', 'POST https://discord.com/api/webhooks/1/fake', 'POST https://api.telegram.org/bot<token>/sendRichMessage', 'POST https://hook.eu1.make.com/fake']
--- job summary file after two runs:
'Review of pull request 412\nThe coupon check was removed from checkout.py.\n\nReview of pull request 412\nThe coupon check was removed from checkout.py.\n\n'
```

A second block for the PR body (`…/scratchpad/run_more_modes.py`: GitHub `key=` alone, Linear `comment_on`, Notion `append_to`, GitLab MR note, Typefully, HubSpot, webhook `payload=`) printed seven SENT receipts (GitHub, Linear, Typefully with links; the rest `None`) and made exactly one GET (GitHub keyed issues), one PATCH (Notion), and six POSTs. Both outputs are quoted in the PR body.

Feature pack on HEAD: `664 passed in 5.41s`.

## 3. Deviations found

Spec §4: none (snippet runs as written, prints the documented lines).

Spec §5: **drifted, corrected in this stage.** The old chart sent every non-GitHub-key connector to `post` (Notion `append_to` is a direct `patch` with no read) and sent a found key-issue match to `patch` (it gets a POSTed comment; only the sticky comment is PATCHed). §5 now matches the PR flow chart; recorded as a §17 bullet. Review.md had called §5 accurate; the code, §8.5's pseudocode, and the tests were right.

Spec §8 / §12: the 13 deviations S3–S5 already recorded in §17 (summarized in the PR body): `OutputHttp.basic_authorization` (not in §8.5), `TELEGRAM_TEXT_MAX_CHARS` removed, `read` returns any JSON with the list check in `GitHubResponses.items`, `OutputAdf` raw paragraph lines, Discord inline `forum_tags` check, `GitHubRequests.issue` single-lines the title, `signing_key` strips whitespace, inline literals, GitHub mode `@intent` blocks, `body: object` for mypy, I001 wraps, NFR-6 read as "code this change creates or modifies", the approved `vidbyte/agents/README.md` edit, constants module 326 lines. I found no further code-vs-spec deviation in §8.5 signatures or §9.2 wire shapes.

First batch: its seven §17 deviations carried into the body; one sentence updated (Telegram's inline `chat_id` check is no longer the only inline constructor check — Discord `forum_tags` and the GitLab port also raise inline).

## 4. PR body

`docs/spec/output-connector-followups/pr-body.md`. Title: `feat(outputs): agents deliver each finished reply to 16 destinations: chat, email, issue trackers, docs, CRM, drafts, and signed webhooks`. Body 46,588 characters (≤ 55,000), ends with the required line, no email address, no raw HTML outside code spans, fences balanced.

Sections: Summary · How to use (§4 snippet + observed output + second block) · Flow (mermaid of the actual path) · Destinations (16 rows) · What changed (11 grouped rows) · Acceptance criteria (36 batch-2 rows; first batch's 26 in `<details>`) · Verification · Adversarial review · Live checks (L-1…L-15, L-1 first then L-2) · Deviations · Follow-ups.

Every test name in the body (116 references, both batches) was checked against `pytest --collect-only` on this branch: 0 missing; the six parametrized ids cited were checked separately.

Gates rerun in this stage on HEAD `eff95946` code: pack `664 passed in 5.41s`; `python lint/run.py` → `SDK-LINT: PASS`; `run_ci.py --stage source` → `4679 passed, 13 skipped in 37.36s` · `CI passed.`; contract `--check` → current, 630 exports. Package gate, Semgrep, I001, and the seven NFR-6 rules are quoted from verify-log iteration 1 (`8d8ba811`; only a README line changed after it).

## 5. Push, PR update, check-runs

- Commit `ffb7a52c` `docs(spec): finalize output-connector-followups for PR` (spec frontmatter `status: pr-open`, §5 chart, §17 row and bullet; `pr-body.md` created).
- `git push origin HEAD:feat/agent-output-connectors` → `eff95946..ffb7a52c`. `git ls-remote` → `ffb7a52cf582d18d8f0ad197dcc519f833978e28 refs/heads/feat/agent-output-connectors`.
- `gh pr edit 882 --title … --body-file <scratchpad>/pr-882-body.md` → ok.
- `gh pr view 882 --json title,isDraft,baseRefName,url,headRefOid,headRefName`:
  `{"baseRefName":"main","headRefName":"feat/agent-output-connectors","headRefOid":"ffb7a52cf582d18d8f0ad197dcc519f833978e28","isDraft":true,"title":"feat(outputs): agents deliver each finished reply to 16 destinations: chat, email, issue trackers, docs, CRM, drafts, and signed webhooks","url":"https://github.com/cerredz/Vidbyte-SDK/pull/882"}` — no `[WIP]`, draft, base `main`, head = pushed HEAD. Body length on GitHub 46,588.
- Check runs on `b1c32edda44487518b37300e5e5c491586dfdf7c`: `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success`. Job logs: Source 3.11 `4673 passed, 19 skipped in 51.82s` `CI passed.`; Source 3.12 `4673 passed, 19 skipped, 19 warnings in 52.18s` `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` `CI passed.`; Static policy `1/1: ✓ All tests passed` `Ran 1 rule on 921 files: 0 findings.`
- `git diff --stat b1c32edd..HEAD -- . ':!docs'` is empty (last Python change `a1405d71`, last non-docs change `44b71741`, both inside `b1c32edd`). Branch is 0 commits behind `origin/main` (fetched 2026-10-14). No new CI dispatch needed.
- This report is not committed (the stage allows one docs commit); it is untracked in the worktree for the orchestrator to commit, as the first batch did in `ae6115f4`.

## 6. Candidate field-guide lessons (report only; not written to the field guide)

Shape follows `field-guide/vidbyte-cli/*.md` (When · Do · Because · Check · Evidence). Sources: conventions-lens findings R-V1…R-V7 (review IDs R-4, R-8, R-9, R-11, R-12, R-13, R-14) and the repo-rule finding R-2.

### A function you add a rule to gets an `# @intent` marker, even when the rule is one guard
- **When:** You add a guard, a raise, or a policy branch inside an existing `vidbyte/` function, and you write a comment explaining why.
- **Do:** Put `# @intent <kebab-name>` directly above that comment, inside A002's window (def−4…def+20). Fix only functions your diff changes; list older findings in touched files in the spec instead of fixing them.
- **Because:** A002 is ratcheted globally, so `SDK-LINT: PASS` stays green while a changed function goes unmarked; the marker is how the next agent finds the rule. AGENTS.md says not to rewrite untouched code.
- **Check:** `python lint/run.py --rule A002 --all --format json`, filtered to the line ranges of your hunks, is empty.
- **Evidence:** PR #882 review R-2 → `a39cf95b` (A002 579 → 577).

### A second caller of the same header or request logic means a helper on the class that owns that concern
- **When:** A new connector needs a header or request fragment another connector already builds inline (Atlassian Basic auth for Confluence and Jira).
- **Do:** Add one static helper to the class that owns the HTTP concern (`OutputHttp.basic_authorization`), call it at send time from both, and keep the first caller's bytes pinned by its wire test. Do not precompute it into a second secret-bearing attribute.
- **Because:** AGENTS.md Style 5 (write shared logic once in `lib/`); a stored header is one more place a credential can leak through `repr` or state export.
- **Check:** `git grep -n b64encode vidbyte/lib/outputs` shows one site; the existing connector's wire test is unchanged.
- **Evidence:** PR #882 review R-8 → `efb2c26b`.

### Every README section that links vendor docs ends with its retrieval date
- **When:** You add or extend a README section or table that links to third-party docs (provider rows, recipes, footguns).
- **Do:** End the section with "Links in this section retrieved YYYY-MM-DD." Apply it to every new section in the same pass, including Footguns.
- **Because:** Vendor limits and setup screens change; an undated link cannot be re-checked. The same PR was flagged twice (R-9 for two sections, then R-RR1 for Footguns).
- **Check:** Every `##` section in the touched README that contains `https://` also contains `retrieved`.
- **Evidence:** PR #882 R-9 → `47696121`, R-RR1 → `44b71741`.

### A module header's TESTS field names every test file that now covers it
- **When:** A new test file exercises new behavior of an existing module.
- **Do:** Add that file to the module's `TESTS:` header line in the same PR, choosing files by grep evidence of the module's symbols.
- **Because:** Agents find a module's tests from its header; A001 checks the header exists, not that it is complete.
- **Check:** For each touched module, the new test files that import or name its symbols all appear in its `TESTS:` line.
- **Evidence:** PR #882 R-12 → `3f5623ca` (ten headers).

### Rename an `@intent` when the behavior it names changes
- **When:** A change alters what a marked block guarantees (Teams "text is plain" became a card with a bold title).
- **Do:** Rename the intent to what still holds (`teams-text-cannot-mention`) and grep for the old name.
- **Because:** Intent names are the searchable contract; a stale one sends the next reader looking for behavior that is gone.
- **Check:** `git grep <old-intent-name> -- vidbyte tests` is empty.
- **Evidence:** PR #882 R-14 → `a1405d71`.

### When a feature widens an enumerated set, update every doc that lists the set
- **When:** You add members to a set that READMEs, headers, or REPO_MAP enumerate (connectors, destination kinds, "eleven").
- **Do:** Grep the count word and the category list across `vidbyte/**/README.md`, module headers, and `REPO_MAP.md`; a file outside the planned list needs the orchestrator's approval, then edit it.
- **Because:** `vidbyte/agents/README.md` still listed first-batch categories after the PR (R-11); the pack now tests that no header says "eleven".
- **Check:** `git grep -n -i "<old count word>"` over `vidbyte` and `REPO_MAP.md` is empty.
- **Evidence:** PR #882 R-11 → `bde205cd`; `test_docs_no_module_header_or_readme_still_counts_eleven_connectors`.

Not proposed: R-4 (72-column comments in tests). The verifier showed `comment-format.md` covers `vidbyte/` code, and 73% of `tests/` comment lines are wider, so it is not a repo rule for tests yet. R-13 (README "how to add" step wording) is a one-off doc fix.

## 7. Things that looked wrong while reading

None blocks the PR; none was fixed here (no source changes).
- `vidbyte/lib/outputs/teams.py:61-70` — `_body_without_title` decides with `OutputText.first_line` (which skips a line made only of `#` marks) but drops through the first line that is non-blank by `line.strip()`. Probe: title `Title`, body `"###\n# Title\nrest"` → body block `'# Title\nrest'`, so the title shows twice. Reachable from model output with a stray `###` line; cosmetic. Spec D-9 literally says "first non-blank line", so this is a spec-level gap, not a conformance bug.
- `vidbyte/lib/outputs/adf.py:80` — ordered lists carry no `attrs.order`, so a list that starts at `3.` renders from 1 in Jira and Confluence. Cosmetic; D-10 does not ask for it.
- `vidbyte/lib/outputs/typefully.py:51` — each platform's post is the uncut body. Documented assumption A-12 (drafts accept long text); L-10 covers it.
- `vidbyte/lib/outputs/github_api.py:91-97` — the sticky marker matches any author's comment. Documented (EC-42, README "Planted markers", Q-8).
- `vidbyte/lib/constants/outputs.py:127` — every Telegram send now uses `sendRichMessage`. The spec grounds it in a saved Bot API page; I could not confirm it independently. If the method is not live, every Telegram reply fails. The PR body puts L-2 second, right after the Slack check.
- `docs/spec/agent-output-connectors/spec.md:5` says `revision: 8`, but its §17 has an r9 row (:1419) added by this batch. Bookkeeping only; this stage may not edit that file. The PR body calls it r8, as instructed.
