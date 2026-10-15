LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the SDK code follows AGENTS.md placement, layering, Style 1–5, A001/A002, and every lint ratchet with no new finding in any touched file; one Major remains: 133 new test comment lines break the field-guide 72-column lesson. Six Minor doc and header drifts remain as well.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- Placement and layering hold exactly. The only new enums are `OutputMethod` and `TypefullyPlatform`. They live in `vidbyte/lib/enums/outputs.py` and are exported from `vidbyte/lib/enums/__init__.py`. The only new dataclass is `OutputRead`, which lives in `vidbyte/lib/dataclasses/outputs.py`, is frozen and slotted, and validates in `__post_init__`. Every HTTP call goes through `OutputHttp` and then `HttpTransport` (S011 0, S012 0). The job-summary write goes only through `LocalFileSystemBackend.append_text` on a dedicated one-worker executor (S061 has no touched-file finding; S047 and S052 are clean). A006 stays at 34/34 with no touched-file finding.
- Style 1 holds by design. An AST scan of every touched `vidbyte/lib/` file finds no same-class chain deeper than one level. The only chain it reports is `HttpTransport.request -> _send_once -> _send_bounded` in `transport.py`, which predates this PR. Four static helper classes keep the chains flat: `OutputResponses`, `GitHubRequests`, `GitHubResponses`, and `OutputAdf`. This follows `class-bound-helpers.md`. The only lambdas are the callbacks for `itertools.dropwhile` and `groupby`, which the API requires, so they are allowed.
- Lint hygiene is clean. A script ran 28 lint rules with `--rule <ID> --all --format json` and checked each finding against the lines this diff added: every finding in a touched file sits on code that predates the PR. Every added source comment line is at most 72 columns. I001 is clean on all touched files. Semgrep reports 0 findings. The diff adds no `noqa` or `type: ignore` and edits no `lint/` file. `--check` confirms the contract is current.
- Headers and docs are complete. All seven new modules carry the full seven-field `"""FILE:` header. The "eleven" counts are now "sixteen" in `base.py`, `agents/output/__init__.py`, and `vidbyte/__init__.py`. `## Modules` keeps its name and lists the seven new files. Every changed Provider Reference row has an official link dated 2026-10-14. The README is 31,755 characters (limit 40,000). The first-batch spec changed only in §9.2(b) and §17.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Major] [field guide: comment-format.md] tests/features/agent_output_connectors/test_output_connectors_webhook_options.py:48 — 133 comment lines the diff adds to 10 test files are wider than 72 columns, up to 114
  Evidence: `test_output_connectors_webhook_options.py:48` (114 cols) `    # Standard Webhooks: base64 HMAC-SHA256 of "{id}.{timestamp}." plus the raw body, keyed by the decoded sec…`; `test_output_connectors_update_in_place.py:89` (98) `    # AC-27 / INV-1 / D-15: GET page 1, GET page 2, then one PATCH of the marked comment; no POST.`; `test_output_connectors_rendering.py:42` (114); section rules such as `# --- Sticky comment ----…` (77). The command `git diff -U0 336d6c78...d5611f25 -- <test file> | grep '^+' | sed 's/^+//' | awk 'length($0) > 72' | grep -cE '^\s*#'` gives these counts: new_destinations 30, update_in_place 27, rendering 19, webhook_options 19, comments 17, followup_contract 12, followup_acceptance 4, factories 3, conftest 1, contract 1. The total is 133. The same check on every touched `vidbyte/` file prints only lines that predate the PR.
  Failure: The `comment-format.md` check says `awk 'length($0) > 72' <file> | grep -E '^\s*#'` "prints nothing for the files you touched". The entry also says a single-line comment over 72 columns "becomes a wrapped block too". The owner rejected 100–120-column comment lines in PR #690 ("stop writing comments like this"), so a reviewer will raise the same comment here. One caveat: the entry says "SDK code", and the first-batch test files already hold 49 such lines, so the verifier may judge test files out of its scope and downgrade this to Minor.
  Smallest fix: Rewrap only the added lines to at most 72 columns, keeping each block directly above its line. Trim each `# --- X ---…` rule to 72 columns. Comments only, so no test behavior changes. Re-run the awk check on the 10 files.
  Spec IDs: §12.4 "Comment blocks are at most 72 columns"

R-V2 [Minor] [AGENTS.md Style 5] vidbyte/lib/outputs/confluence.py:68 — the Basic auth header is now written twice, byte for byte
  Evidence: `jira.py:77` and `confluence.py:68` are the same line: `headers = {"authorization": "Basic " + base64.b64encode(f"{self._email}:{self._api_token}".encode()).decode()}`. `git grep b64encode vidbyte` shows that no helper in `vidbyte/lib/` builds this header.
  Failure: AGENTS.md Style 5 says "whenever a canonical helper in vidbyte/lib/ would save writing the same logic a second time, build it that way". This PR writes the logic a second time. The expected review comment is "make the Atlassian Basic header one helper".
  Smallest fix: Add one static method to an existing class, for example `OutputHttp.basic_authorization(username: str, secret: str) -> str` in `delivery.py`, and call it from both connectors. This adds no class, so the §8.4 budget is unchanged.
  Spec IDs: n/a (house rule; W-16 reuse)

R-V3 [Minor] [folder README] vidbyte/agents/README.md:252 — the agents README's "Output Connectors" section still describes only the first batch's destinations
  Evidence: lines 252–253 read `Send each finished reply to Slack, email, an issue tracker, Notion, or any HTTPS webhook by passing connectors as outputs=:`. `REPO_MAP.md` and `vidbyte/lib/README.md` now name code hosts with comments and update-in-place, CI job summaries, social-post drafts, CRM tasks, and signed webhooks. This file is not in the diff.
  Failure: FR-5 says "Every repo doc … that lists the connector set … names the 16 connectors". AGENTS.md says to read a folder's README and keep it current. A developer opening `vidbyte/agents/` sees the old scope.
  Smallest fix: Change that one sentence to the same category list `vidbyte/lib/README.md:42` now uses.
  Spec IDs: FR-5, W-3

R-V4 [Minor] [agentic: A001 header accuracy] vidbyte/lib/outputs/delivery.py:9 — the TESTS fields of ten changed modules omit the new test files that cover their new behavior
  Evidence: The `delivery.py:9` TESTS field names `…http_failures.py and test_output_connectors_email.py`, but `read`, `patch`, and `OutputResponses` are tested in `test_output_connectors_update_in_place.py`. The `base.py:9` TESTS field names only `…configuration.py`, but the new `OutputArguments` checks are tested in `…rendering.py`, `…comments.py`, `…webhook_options.py`, and `…new_destinations.py`. The TESTS fields of `slack.py:9`, `discord.py:9`, `teams.py:9`, and `telegram.py:9` name only `…wire_contract.py`, but the new rendering is tested in `test_output_connectors_rendering.py`. The TESTS fields of `dataclasses/outputs.py:9`, `enums/outputs.py:9`, and `constants/outputs.py:9` name only `…contract.py`. They should also name `…followup_contract.py` and `…update_in_place.py`. The same diff did update the TESTS field for `github.py`, `jira.py`, `linear.py`, `notion.py`, and `webhook.py`. `github.py:9` still omits `…comments.py`, which tests `comment_on`.
  Failure: The A001 and file-header obligation is that a header is accurate against the finished code, including the headers of existing files the diff changed. The next agent that changes Slack's markdown block will follow TESTS to the wrong file.
  Smallest fix: Append the covering test file names to the TESTS fields of those ten headers. This is a docstring change only.
  Spec IDs: §12.4 A001 row; §12.3 rows 1, 3, 4, 6, 7, 9–12

R-V5 [Minor] [folder README accuracy] vidbyte/lib/outputs/README.md:220 — "How To Add A Destination" step 3 tells authors to write "private static helpers", but the one multi-mode connector uses instance methods
  Evidence: README lines 220–222 say "when `send` has several modes, private static helpers that `send` calls". `github.py:79`, `86`, `93`, and `114` define the helpers as `async def _create_issue(self, …)`, `_comment(self, …)`, `_comment_on_keyed_issue(self, …)`, and `_sticky_comment(self, …)`. These are private async instance methods.
  Failure: Style 2 says comments and docs must never describe behavior that is gone. A connector author who follows step 3 will copy a shape the code does not use.
  Smallest fix: Say "private helpers (static, or async methods when they need the connector's settings)".
  Spec IDs: §12.3 row 29 (":98-102 … allow private static helpers")

R-V6 [Minor] [agentic: @intent accuracy] vidbyte/lib/outputs/teams.py:48 — the intent name `teams-text-is-plain` contradicts both its own rewritten comment and the new card
  Evidence: `# @intent teams-text-is-plain`, followed by `# TextBlocks carry no mention entities, so model-written text # cannot mention a person or the whole channel.` The old claim "renders the text as plain text" was removed, and the card now sends `"weight": TEAMS_TITLE_WEIGHT` plus TextBlock Markdown. The Telegram intent was renamed for the same kind of change (`telegram-rich-text-carries-no-html-or-media`).
  Failure: In `intent_based_commenting.md`, the intent name is the handle an agent greps for to find a rule. A name that states a rule the code no longer keeps misleads that search. The rule is also on spec row 12 ("`@intent` updated").
  Smallest fix: Rename the intent to `# @intent teams-text-cannot-mention`. A002 needs only that an `@intent` line be present, and nothing else references this name (`git grep teams-text-is-plain` finds only `teams.py:48`).
  Spec IDs: §12.3 row 12

R-V7 [Minor] [§12.5 docs: dated official links] vidbyte/lib/outputs/README.md:130 — the new Email-in table (14 rows) and Webhook receivers table (11 rows) have no retrieval date
  Evidence: `| Tool | Where to find the address | Docs |` (line 130) and `| Receiver | Recipe | Docs |` (line 201) have no Retrieved column and no date line. The only date note, line 102, says "Retrieved 2026-10-11; rows changed by the follow-ups retrieved 2026-10-14" and covers the Provider Reference table. All nine receiver links I fetched return 200, so the links themselves are fine.
  Failure: Spec row 29 says "Every changed or added row carries an official link and the date `2026-10-14`". These rows link to vendor pages that change, such as Pushcut's path (marked unverified) and Basecamp's Basecamp 2 guide. Without a date, nobody can tell when they were last checked.
  Smallest fix: Add one line under each table: "Links retrieved 2026-10-14."
  Spec IDs: FR-2, FR-17, §12.3 row 29

VERIFIED CLAIMS:
- "Pack 660 passed" (S3, orchestrator): held. My run printed `660 passed in 5.09s`.
- "SDK-LINT: PASS; S009 350" (S3): held. S009 is RATCHETED 350/350, and its only touched-file finding is `transport.py:233 [attr-defined]`, which predates this PR.
- "NFR-6: A002, S061, S001, S017, S025, C011, and C012 show no new finding in a touched file" (S3, §12.4 last box): held. A002 has 9 touched-file findings, all in `errors/base.py` and `transport.py`. Two of them are on the extended `request` and `_send_once` signature lines, but the same symbols existed on base. The 4 S001 findings are base F401s in `vidbyte/__init__.py`. S017, S025, C011, C012, and S061 have 0 touched-file findings. I extended the same check to 21 more rules (among them A001, A006, A007, S008, S024, S060, S062, S015, S054, and S051): every touched-file finding predates the PR.
- "Contract current" (S3, row 28): held: `contracts/sdk-public-api.json is current at eadefa3f… (vidbyte-sdk 0.2.1, 630 exports).`
- "Semgrep 0 findings" (S3): held: `Ran 1 rule on 921 files: 0 findings.`
- "7 new files, each with the A001 header" (§8.4, §12.4): held. `git diff --diff-filter=A` lists exactly the seven files, and A001's only touched-file findings are `vidbyte/__init__.py` and `transport.py`, which predate this PR. Per spec §11, `transport.py` is meant to stay without a header.
- "post/patch → _write → OutputResponses keeps Style 1" (D-2, R-9): held, per the AST scan.
- "I001: two touched import blocks wrapped, untouched blocks left alone" (S3): held. `ruff --select I001` passes on all touched files.
- "Comments ≤72 columns" (S3, §12.4): held for `vidbyte/`; every line awk prints there predates the PR. Not held for tests (R-V1).
- "TELEGRAM_TEXT_MAX_CHARS removed as dead" (S3 deviation): held. `grep -rn TELEGRAM_TEXT_MAX_CHARS vidbyte tests` finds nothing.
- "Row 33 changed only §9.2(b) and §17 of the first spec" (briefing): held.
- "llms.txt and artifacts/file_index.md do not name the output connectors" (§12.5): held; grep finds nothing.
- "No suppressions, no baseline raised" (§12.4): held. No added `noqa`, `type: ignore`, or `nosemgrep` in code, and `git diff --stat -- lint/ .semgrep/ pyproject.toml` is empty.
- "Commits end with Co-Authored-By and cite IDs": trailers held on all 52 commits. IDs held only partly: the fix-up commits `b0c5624e` ([W-1; FR-1]) and `1be7319e` ([W-19; FR-29]) change `delivery.py` (W-20) and `slack.py` (W-5). I did not file this, because the history cannot be rewritten (no force-push).
- "No cache or generated files in the diff": held. The grep for `__pycache__`, `.pyc`, and `.venv` prints nothing.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors </dev/null` → `660 passed in 5.09s`
- `PYTHONIOENCODING=utf-8 timeout 900 python lint/run.py </dev/null` → `SDK-LINT: PASS`, exit 0. IMPROVED: A002 703→579, C011 2→1, C012 24→23, S001 59→56, S010 5→0, S017 79→78, S025 263→261, S061 6→5. Every other rule is RATCHETED at its baseline or CLEAN.
- `python scratchpad/conv_touched_findings.py <wt> A001 A002 A006 A007 S001 S017 S025 C011 C012 S061 S008 S024 S060 S062 S015 S054 C006 C001 C008 S016 S051`, then `… S009 S012 S011 S056 C016 A009 S020` → every touched-file finding is on a line that predates the PR (listed under VERIFIED CLAIMS).
- `python scratchpad/conv_call_depth.py <touched vidbyte/lib files>` → `HttpTransport.request -> _send_once -> _send_bounded` (predates the PR); 2 lambdas, both API callbacks; no function over 40 lines.
- `awk 'length($0) > 72' <f> | grep -nE '^\s*#'` over the touched `vidbyte/*.py` files → only lines that predate the PR (`errors/base.py`, `transport.py`)
- `git diff -U0 … -- tests/*.py | … awk 'length($0) > 72' | grep -cE '^\s*#'` → total 133 (R-V1)
- `python -m ruff check <touched + new vidbyte files> --config lint/ruff.toml --select I001 --no-cache` → `All checks passed!`
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at eadefa3f6f17… (vidbyte-sdk 0.2.1, 630 exports).`
- `env -u PYTHONPATH PATH="$(cygpath -u <scratch>/semgrep-venv/Scripts):$PATH" semgrep scan --metrics=off --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → `Ran 1 rule on 921 files: 0 findings.`, exit 0
- `git diff --name-only 336d6c78...d5611f25 | grep -E "__pycache__|\.pyc$|\.venv"` → empty (exit 1)
- A per-commit loop over `git log -1 --format=%B` for the last non-blank line → every commit ends `Co-Authored-By: Claude …`
- `curl -s -o /dev/null -L --max-time 20 -w "%{http_code}"` on the ntfy, Gotify, Home Assistant, Inngest, incident.io, Jira Automation, Mattermost, Rocket.Chat, and Pushcut doc links → all `200`
- `wc -c` → `vidbyte/lib/outputs/README.md` 31,755; `vidbyte/agents/output/README.md` 5,439
