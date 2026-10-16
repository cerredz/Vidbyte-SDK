# S6 PR author report: agent-output-connectors

- **Stage:** S6, the last stage. The PR body is `docs/spec/agent-output-connectors/pr-body.md`.
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/882. It is still a draft, its base is `main`, and the `[WIP]` prefix is gone from the title.
- **Commits from this stage:**
  - `b58a022a` `docs(spec): finalize agent-output-connectors for PR`: spec frontmatter, the §17 row, and the first `pr-body.md`.
  - A follow-up docs commit that records the CI run IDs in `pr-body.md` and adds this report.
- **No source or test file changed.** `git diff b18ac7d1..HEAD --stat` lists only files under `docs/spec/agent-output-connectors/`.

## 1. What the code does

I wrote this from the diff before I opened the spec. The working copy is at `scratchpad/s6/code-understanding.md`.

**Construction**
- `BaseAgent.__init__` takes `outputs: Sequence[OutputConnector] = ()` and stores `OutputDispatcher.connectors(outputs)` as a tuple (`vidbyte/agents/base.py:235`). `BaseAgent.restore` takes `outputs=` too.
- `JevAgentSettings.outputs` is checked the same way in `__post_init__`, and `JevAgent` passes it on.
- `CodingAgent` gets `outputs` through `**kwargs`.
- `connectors()` (`vidbyte/agents/output/dispatcher.py:34`) rejects each of these with a `ConfigurationError` whose message contains `outputs`:
  - a `str`, `bytes`, or mapping;
  - anything that is not iterable;
  - a class instead of an instance;
  - an item that does not satisfy the `OutputConnector` protocol;
  - an item whose `destination` is not an `OutputDestination`;
  - the same instance listed twice.
- Each connector checks its own arguments with `OutputArguments` when it is built.
- Credentials are resolved in this order: the explicit argument, then the environment variable (stripped; a blank value counts as missing), then a `ConfigurationError` that names both the parameter and the variable.
- `BaseOutput.__repr__` masks the credential.

**Run path**
- `_generate_reply` builds the reply. The reply's metadata is the same dict object that delivery writes into later.
- It appends the reply to history and sets `last_reply`. Then it calls `_record_last_trace` (three lines moved out of `_generate_reply`), runs the auto-handoff, calls `_notify_session(reply)`, and calls `_assert_schema_satisfied`.
- Next comes `if self.outputs: await self._deliver_outputs(reply, metadata)` (`base.py:936-937`), and after that the queued-prompt drain.
- `_deliver_outputs` (`base.py:948`) wraps `OutputDispatcher.deliver` in `try` / `except BaseException`. On any exception it clears `_queued_prompts`, calls `_notify_session_exception`, and re-raises.

**`OutputDispatcher.deliver`** (`dispatcher.py:54`)
- If `OutputShaping.is_deliverable(reply)` is false, every receipt is SKIPPED and is written to `metadata["deliveries"]`. A reply is not deliverable when its content is blank, or when its `stop_reason` is set and is neither `final_response` nor `is_done`.
- Otherwise it runs `asyncio.gather(_deliver_one(...) for each connector, return_exceptions=True)`.
- Any non-`Exception` `BaseException` (cancellation) is re-raised.
- `_receipt` turns each result into a receipt, kept in configured order. An exception becomes FAILED `unexpected:<Type>`.
- It writes the receipts to `metadata["deliveries"]`. If any receipt is FAILED, it raises `OutputDeliveryError(reply=, receipts=)` from the first exception.

**`_deliver_one`** (`dispatcher.py:84`)
1. Build the content with `connector.render(reply)`, or with `OutputShaping.content(reply)` when there is no `render`.
2. Raise `ConfigurationError` unless the content is an `OutputContent`.
3. Await `asyncio.wait_for(connector.send(...), 35 s)`. A `TimeoutError` becomes FAILED `network`.
4. Raise `ConfigurationError` unless `send` returned a `DeliveryReceipt`.

**`OutputShaping.content`**
- **Body:** the structured `body` field, else `reply.content`.
- **Title:** the structured `title` field. When there is no structured output, the title is the first line of the body with any leading `#` removed. If neither gives a title, the agent name is used.

**`OutputHttp.post`** (`vidbyte/lib/outputs/delivery.py`)
- It makes one `HttpTransport().request` POST, with these options:
  - 10 s timeout;
  - 2 retries, on 429 only;
  - a 1 MB response cap;
  - a local idempotency key;
  - `follow_redirects=False`.
- Results map to receipts like this:
  - `ProviderRequestError` gives FAILED `network`;
  - a status outside 2xx gives `http_<code>`, plus `:<token>` when the whole body is one lowercase word;
  - when the request sets a `link_path`, the response must yield an `https://` link after `link_prefix` is added, or the result is FAILED `invalid_response`.
- A module `ContextVar` is set around the request. A filter on the `httpx` logger, registered at import (`delivery.py:180`), drops `HTTP Request:` lines only while that flag is set.

**`OutputSmtp.send`**
- It opens `SMTP_SSL` on port 465, or `SMTP` plus `starttls` with a verified default context on any other port. Then it logs in and calls `send_message`.
- `quit()` runs under `suppress`, so the reply to QUIT never changes the receipt.
- Errors map like this:
  - every recipient refused: `smtp_recipients_refused`;
  - `SMTPResponseException`: `smtp_<code>`;
  - any other `SMTPException`: `smtp_error`;
  - `OSError`: `network`;
  - a partial refusal is FAILED too.
- `EmailOutput.send` runs it on the module's own `_SMTP_EXECUTOR` (`email.py:30`).

**The 11 connectors**

| Connector | What it sends |
|---|---|
| `SlackOutput` | Escapes `&`, `<`, and `>`. |
| `DiscordOutput` | Sets `allowed_mentions.parse = []`. |
| `TeamsOutput` | One Adaptive Card `TextBlock`. |
| `GoogleChatOutput` | Neutralizes `<users/`. |
| `TelegramOutput` | No `parse_mode`. |
| `EmailOutput` | One-line `Subject`, `text/plain` body. |
| `GitHubIssueOutput` | Fixed repo and labels. The link is `html_url`. |
| `LinearIssueOutput` | GraphQL. The link is `data.issueCreate.issue.url`. |
| `JiraIssueOutput` | Basic auth, an ADF paragraph for each non-blank line. The link is `/browse/{key}`. |
| `NotionPageOutput` | The `markdown` body, with `<mention-` neutralized. The link is `url`. |
| `WebhookOutput` | JSON `{agent, title, body, structured}`. |

**Other changes**
- Forks pass `outputs=()` (`fork.py:84`).
- There are 17 new root exports. `OutputDispatcher` is exported only from `vidbyte.agents.output`.
- The public API contract was regenerated.

## 2. Deviations found (code against spec §4, §5, §8, §12)

I found no deviation beyond the ones already recorded in spec §17. I checked these points:
- **§4:** the snippet runs as written (section 3).
- **§5:** the flow matches the code step for step, so I left it unchanged. The PR body's flow chart also draws two things that §5 covers only in prose: the connector-construction step and the `unexpected:<Type>` path.
- **§8.5:** the signatures match the code, except the recorded `optional_callable` typing.
- **§9.2:** the wire bodies, headers, caps, and constants match the code.
- **§12:** the budget holds: 23 new files and 26 classes.

The PR body's "Deviations" section lists the seven recorded items: S3-1, `optional_callable`, canonical UUID, `title or reply.sender`, lowercase header keys, `errors/__init__` I001 left as is, and the inline `chat_id` raise in `TelegramOutput`.

## 3. Snippet output (AC-1)

- **AC-1 test:** `PYTHONPATH=$(pwd) python -m pytest -q "tests/features/agent_output_connectors/test_output_connectors_acceptance.py::test_spec_snippet_delivers_one_validated_reply_to_slack_and_a_github_issue_and_prints_both_receipts" -s` gave `1 passed in 0.13s`. The test captures stdout itself, so `-s` showed nothing.
- **Re-review probe:** `scratchpad/rereview/p_ac1_snippet.py` executes the §4 block exactly as it appears in `spec.md`. Only the model runner and `HttpTransport._send_once` are scripted, so it made no network call. Its output:

```text
output: 'slack sent None\ngithub_issue sent https://github.com/acme/shop/issues/412\n'
expected: 'slack sent None\ngithub_issue sent https://github.com/acme/shop/issues/412\n'
byte-equal: True
sent hooks.slack.com {'text': 'Coupon total wrong\n\nTotals ignore coupons.'}
sent api.github.com {'title': 'Coupon total wrong', 'body': 'Totals ignore coupons.', 'labels': ['bug']}
```

## 4. Verification I ran

The code is identical from `ad4ed50a` through `b58a022a`.

| Gate | Where | Final lines |
|---|---|---|
| feature pack | `b18ac7d1` | `340 passed in 2.54s` |
| `python scripts/run_ci.py` with PYTHONPATH unset | `b18ac7d1` | `SDK-LINT: PASS` · `3743 passed, 13 skipped in 29.58s` · `No broken requirements found.` · `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` (exit 0) |
| `generate-sdk-public-api.py --check` | `b18ac7d1` | `contracts/sdk-public-api.json is current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).` |
| Semgrep 1.170.1 (session venv) | `b18ac7d1` | `1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.` (exit 0) |
| `pyproject.toml` diff against `origin/main` | `b18ac7d1` | empty |
| remote `ci.yml`, run 38215147873 | `b58a022a` | success. Source 3.11 `3738 passed, 18 skipped` · `CI passed.`; Source 3.12 the same; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` |
| remote `static-policy.yml`, run 38215150030 | `b58a022a` | success. `1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.` |

In `run_ci`, lint reported seven rules IMPROVED and none REGRESSED: A002 703→638, A007 255→254, C012 24→23, S001 59→56, S010 5→0, S025 263→261, S051 259→258.

**The follow-up docs commit.** It is dispatched again after it is pushed. Its run IDs are in the S6 STATUS block, as in the S5 precedent.

**Mergeability with current main.** `main` is now 7 commits ahead. It added #885 and #889 after the briefing was written; #885 changes `vidbyte/agents/coding.py` (`load_environment`) and #889 changes `runtime.py`. The checks:
- `gh pr view` reports `mergeable: MERGEABLE`, `mergeStateStatus: BEHIND`.
- `git merge-tree --write-tree HEAD origin/main` is clean.
- Two files overlap with main, `vidbyte/agents/README.md` and `vidbyte/lib/enums/__init__.py`. Both merge automatically.
- I merged into a throwaway detached worktree (`scratchpad/s6/merge-check`, never pushed). There, the feature pack plus the coding-agent pack gave `610 passed, 12 skipped`, and `python lint/run.py` gave `SDK-LINT: PASS`.
- I did not catch up on the branch, because that is not this stage's job. A catch-up merge is optional.

## 5. Final `gh pr view` and `gh pr checks`

```text
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/882 --json title,isDraft,baseRefName,url
{"baseRefName":"main","isDraft":true,"title":"feat(outputs): agents deliver each finished reply to Slack, email, issue trackers, Notion, and webhooks","url":"https://github.com/cerredz/Vidbyte-SDK/pull/882"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/882
no checks reported on the 'feat/agent-output-connectors' branch
```

`gh pr checks` is empty because CI on this repo runs only when dispatched. The checks are the dispatched runs in section 4.

The remote PR body matches `tail -n +2 pr-body.md`, apart from the trailing newline that `jq` adds.

## 6. Candidate field-guide lessons (not written to the field guide)

Each lesson is in the field-guide shape: trigger · preferred action · project-specific reason · quick check · link.

1. **A secret in a URL sent through `HttpTransport`** (R-1).
   - **Trigger:** a webhook URL or a path token passes through `HttpTransport`.
   - **Preferred action:** set a module `ContextVar` around the request, and add a filter on the `httpx` logger that drops `HTTP Request:` lines while the flag is set. Do not raise the `httpx` log level, and do not `import httpx` outside `lib/http`.
   - **Why here:** httpx logs the full URL at INFO. `vidbyte/` had no `addFilter` anywhere, and six destinations keep the credential in the URL.
   - **Quick check:** run each connector with `caplog.set_level(logging.INFO, logger="httpx")` and assert the secret is absent.
   - **Link:** PR #882, `228c0fdc`.
2. **Blocking I/O that sync `run()` must bound** (R-3).
   - **Trigger:** blocking I/O that sync `agent.run()` must finish within a deadline.
   - **Preferred action:** use a dedicated module-level `ThreadPoolExecutor` with `loop.run_in_executor`, not `asyncio.to_thread`.
   - **Why here:** on Python 3.11, `asyncio.run` joins the default executor with no timeout, so `wait_for` alone does not bound `run()`.
   - **Quick check:** a fake that blocks on a `threading.Event`, where `run()` must raise before the event is set.
   - **Link:** PR #882, `e6ae0fa2`.
3. **The same validation rule in two modules** (R-4).
   - **Trigger:** one rule (a regex or a predicate) appears in a `lib/dataclasses` record and in a `lib/<feature>` argument checker.
   - **Preferred action:** put the pattern in `lib/constants/<domain>.py`, and have both sites call `re.fullmatch` on it, each with its own message.
   - **Why here:** C008 catches only numeric and bool drift, and `lib/dataclasses` cannot import `lib/<feature>` because that would be a cycle.
   - **Quick check:** `git grep` the regex literal and expect one hit.
   - **Link:** PR #882, `f73ae753`.
4. **`@intent` placement** (R-6).
   - **Trigger:** an `@intent` block.
   - **Preferred action:** put it directly above the line that enforces the rule, not above nearby code. Every business rule, including a skip rule, gets one.
   - **Why here:** reviewers and A002 read the block as documentation of the line below it.
   - **Quick check:** the line after the block enforces the rule the block names.
   - **Link:** PR #882, `0cb2dbc8`.
5. **Module header claims** (R-7).
   - **Trigger:** a module header says "the only place" something happens, or cites a spec ID.
   - **Preferred action:** state the split of responsibility truthfully, do not cite `docs/` IDs (agents treat `docs/` as opaque), and add any new test path to the TESTS line of every header you touch.
   - **Why here:** AGENTS.md makes `docs/` opaque, and headers are the agent's map.
   - **Quick check:** grep the header for `INV-`, `AC-`, and `R-` IDs, and check its TESTS line against the files touched.
   - **Link:** PR #882, `540b8501`.
6. **Endpoint paths as literals** (R-9).
   - **Trigger:** an endpoint path or a URL prefix written inline in an f-string.
   - **Preferred action:** name it in `lib/constants/<domain>.py`, next to the other endpoints.
   - **Why here:** every other connector names its endpoint there, and A007 tracks operational constants.
   - **Quick check:** no `"/rest/` or `"/browse/` literal outside `constants/`.
   - **Link:** PR #882, `e41c535f`.
7. **A new folder README** (R-10).
   - **Trigger:** a new folder README.
   - **Preferred action:** include a `## Non-Goals` section that repeats the settled exclusions.
   - **Why here:** sibling READMEs carry one, and agents read the README before they change the folder.
   - **Quick check:** `grep -n "^## Non-Goals" <folder>/README.md`.
   - **Link:** PR #882, `ad96036f`.
8. **Lint headroom on `BaseAgent._generate_reply`** (S3-1, and S3-2 for names).
   - **Trigger:** a change needs to grow `BaseAgent._generate_reply`.
   - **Preferred action:** put the new step in a private helper called under a guard, and move unrelated lines out if needed. Never raise the S008 baseline.
   - **Why here:** the function sits exactly at C901 10 and 50 statements, and S008 is ratcheted. Separately, S054 and S105 flag constants whose name contains `_TOKEN_`, so prefer `_PREFIX` names.
   - **Quick check:** `python lint/run.py --rule S008` shows no REGRESSED line.
   - **Link:** PR #882, `4346dfb5`.

These come from `conformance` and `engineering` and are one-off bugs, so I did not draft lessons for them: R-2, R-8, R-12, and R-15. R-C2 (E302) is not a lesson because the repo's ruff config selects only `TID251`.

## 7. Things that looked wrong while reading

All three are Minor. None of them blocks review, and I fixed none of them.

**`EmailOutput(to=[])` names the wrong field**
- **Where:** `vidbyte/lib/outputs/email.py:50`, with `vidbyte/lib/dataclasses/outputs.py:112-113`.
- **What happens:** the call raises `ConfigurationError("recipients must be a non-empty tuple of email addresses, got ().")` with `details={"field": "recipients"}`. The parameter is `to`.
- **Why it matters:** INV-21 and AC-20 expect the error to name the parameter. AC-20 lists `to="not-an-address"`, which does name `to`, but not an empty list.
- **Fix:** add an empty-sequence check in `OutputArguments.texts`, or one at the `EmailOutput` call site.

**`deliver` does not check what it is given**
- **Where:** `vidbyte/agents/output/dispatcher.py:54`, with `vidbyte/lib/errors/base.py:215`.
- **What happens:** `OutputDispatcher.deliver` is documented as the way to resend failed outputs, but it does not validate its `outputs` argument. The repair hint in `OutputDeliveryError` says `OutputDispatcher.deliver(failed, err.reply, {})`, while `err.failed` holds receipts, not connectors. Passing `err.failed` gives `OutputDeliveryError: 1 of 1 outputs failed: slack (unexpected:AttributeError)`, which I reproduced.
- **Note:** the README recipe is correct; it zips `agent.outputs` with `err.receipts`.
- **Fix:** reword the hint ("the failed connectors, selected by zipping agent.outputs with err.receipts"), or call `connectors()` inside `deliver`.

**The email-address rule accepts `"@"`**
- **Where:** `vidbyte/lib/constants/outputs.py:67`.
- **What happens:** `OUTPUT_EMAIL_ADDRESS_PATTERN = r"[^\s,]*@[^\s,]*"` matches `"@"` and `"bot@"`.
- **Why it is not a bug:** this is exactly the spec's rule ("an @ and no whitespace, line break, or comma"), so I am only noting it.

**No vacuous tests found.**
- The 44 distinct test functions named in §6.2 all exist on the branch.
- The S4 engineering mutations show the pack catches real regressions: 9 of 14 caught, and the R-14 gap is closed by `45ba29cc`.
