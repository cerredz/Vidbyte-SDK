LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — lint, placement, layering, comment format and the contract are clean, but one validation rule is copied across lib/dataclasses and lib/outputs (and has started to drift), and a few headers, @intent anchors and error messages need small corrections.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Lint is clean for every new file. `python lint/run.py` ends `SDK-LINT: PASS`, and seven rules improved (A002 703→644, A007 255→253, S001 59→56, S009 350→349, S010 5→0, S025 263→261, S051 259→258). Every remaining touched-file hit is pre-existing: fork.py:1 A001, base.py A005/A006, older errors/base.py A003, jev/settings.py C008, vidbyte/__init__.py S015, and multi/README.md:26 S020.
- Placement and layering follow AGENTS.md.
  - The enums are in lib/enums/outputs.py and exported. The dataclasses are in lib/dataclasses/outputs.py and the constants in lib/constants/outputs.py.
  - The Jev capability is a validated `JevAgentSettings.outputs` field.
  - `vidbyte/agents/output/` imports only stdlib, lib and its own modules, and nothing in lib imports agents.
  - Every new file is under 150 lines. base.py grows by +29/−4, inside the 35-line budget.
- `OutputDispatcher.deliver` is a model narrated main function. It runs `gather(return_exceptions=True)`, re-raises non-Exception BaseExceptions so cancellation propagates, uses `zip(strict=True)`, and raises `OutputDeliveryError ... from first_exception`. `_deliver_outputs` re-raises from its `except BaseException`. Do not "simplify" either.
- C016 ordering is right: the export commit comes first, then contract commit 7fedbbc5, and `--check` passes. Every new comment block fits in 72 columns. `_generate_reply` keeps exactly main's S008 shape (C901 10 / PLR0912 9 / PLR0915 50).

FINDINGS (ranked, most severe first, max 15)

R-V1 [Major] [strict-config-dataclasses / DRY validation] vidbyte/lib/dataclasses/outputs.py:37 — The email-address, non-blank-text and https rules each exist as separate copies in two modules and have already drifted
  Evidence:
    vidbyte/lib/dataclasses/outputs.py:37  `return isinstance(value, str) and "@" in value and not any(char.isspace() or char == "," for char in value)`
    vidbyte/lib/outputs/base.py:86         `if isinstance(value, str) and "@" in value and not any(char.isspace() or char == "," for char in value):`
    vidbyte/lib/dataclasses/outputs.py:32 `_is_text`  vs  vidbyte/lib/outputs/base.py:49 `if isinstance(value, str) and value.strip():`
    The https rule is written three ways:
    - dataclasses/outputs.py:21 `_HTTPS = "https://"` (used at :66 and :81, prefix only).
    - outputs/base.py:43 `if value.startswith("https://") and urlsplit(value).hostname:` (prefix plus host).
    - outputs/delivery.py:107 `return link if link.startswith("https://") else None` (prefix only).
    The same value is checked twice by the two copies. email.py:51-52 runs `OutputArguments.address(...)` and passes the result to `SmtpSettings(...)` (email.py:46), which runs `_is_address` again at dataclasses/outputs.py:107-108.
  Failure: The field guide's strict-config-dataclasses lesson says "Any primitive value validated inline in more than one call site belongs in its own frozen dataclass", and bounds or literals belong in constants (AGENTS.md §4, A007). Here one rule has two hand-maintained copies. They already disagree on what makes a valid https URL: `OutputArguments.https_url` requires a host, while `OutputRequest.url` and `_link` accept any `https://` prefix. A human reviewer would write: "This predicate is copy-pasted from dataclasses/outputs.py. Define it once and call it from both, or the email rule will drift the way the https rule already has."
  Smallest fix:
    - Keep one predicate per rule in the lowest module. Make the `_is_address`/`_is_text` helpers in lib/dataclasses/outputs.py public, and have `OutputArguments.address`/`text` call them; lib/outputs may import lib/dataclasses.
    - Move `"https://"` to one constant in lib/constants/outputs.py and use it at all three sites.
    - No behavior change. Not scope-adding.
  Spec IDs: n/a

R-V2 [Minor] [agentic @intent placement] vidbyte/lib/outputs/jira.py:60 — The Jira host rule's @intent sits above the credential encoding, not above the check that enforces it, and the delivery skip rule has no @intent
  Evidence:
    jira.py:52 `self._site = OutputArguments.matching(site, JIRA_SITE_PATTERN, parameter="site")` has no comment.
    jira.py:60-63
      `# @intent jira-site-is-a-bare-atlassian-host` / `# The site is checked as a bare *.atlassian.net host, so the` / `# Basic credentials can never be sent to another server.` / `basic = base64.b64encode(...)`
    vidbyte/agents/output/connector.py:47-50
      `def is_deliverable(...)` has only the docstring "True when the reply has text and its run finished with an accepted answer." and no @intent explaining why stopped or failed runs are skipped.
  Failure: Agentic-engineering practice and the comment-format field guide say an `@intent` sits directly above the function or operation that enforces the rule, so that a search for the intent lands on the enforcing line. Here the Jira intent says "is checked", but the check is eight lines up, in `__init__`. The skip rule decides which replies leave the process, yet it carries no recorded why. A reviewer would write: "Move this @intent to line 52, and give is_deliverable an @intent saying partial or failed answers are never posted."
  Smallest fix:
    - Move the jira @intent block above jira.py:52; optionally leave a one-line pointer above `basic`.
    - Add a two-line `# @intent deliver-only-accepted-answers` block above the return in `is_deliverable`.
    - (github.py:48 is defensible: `send` is where the URL is built from constructor state. Leave it.)
  Spec IDs: INV-9, D-19, D-22

R-V3 [Minor] [file-header accuracy] vidbyte/lib/outputs/delivery.py:5 — A file header claims a single owner of error codes that the dispatcher contradicts, and two headers omit the new test file
  Evidence:
    delivery.py:5 `ARCHITECTURE NOTE: The only place delivery outcomes become error codes, so the INV-11 code grammar and the retry policy live in one module.`
    But the dispatcher also produces error codes:
    - dispatcher.py:94 `return DeliveryReceipt(connector.destination, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_NETWORK)`.
    - dispatcher.py:7 says ordinary exceptions fail "as unexpected:<Type>".
    The header also cites INV-11, a spec ID that lives only under docs/, which AGENTS.md tells agents to treat as opaque.
    vidbyte/agents/jev/settings.py:9 and vidbyte/agents/jev/agent.py:9 list TESTS without tests/features/agent_output_connectors/test_output_connectors_agent_wiring.py, even though both files gained `outputs` in this diff.
  Failure: Agentic-engineering says file headers must be accurate, and A001 requires the headers to be present and current. A reader who trusts delivery.py:5 will look for the timeout and unexpected codes in the wrong module. A reviewer would write: "This header is wrong: dispatcher.py also makes codes. Drop the 'only place' claim and the INV-11 reference."
  Smallest fix:
    - Reword delivery.py:5 to say "Maps HTTP and SMTP outcomes to error codes; the dispatcher adds network-on-deadline and unexpected:<Type>", and remove "INV-11".
    - Append the wiring test path to the TESTS line in both jev headers.
  Spec IDs: INV-11

R-V4 [Minor] [AGENTS.md §4 clear errors] vidbyte/lib/outputs/telegram.py:36 — Some validation errors misstate the rule or leave out a non-secret bad value
  Evidence:
    telegram.py:36 `self._chat_id = chat_id if isinstance(chat_id, int) and not isinstance(chat_id, bool) else OutputArguments.text(chat_id, parameter="chat_id")`
    probe → `ConfigurationError chat_id must be a non-blank string, got True.` / `ConfigurationError chat_id must be a non-blank string, got 1.5.`
    vidbyte/lib/dataclasses/outputs.py:67 `_require(self.url is None or url_allowed, "url", "must be None, or an https:// link on a sent receipt.")`
    probe → `ConfigurationError url must be None, or an https:// link on a sent receipt.`
  Failure: AGENTS.md §4 says a validated record "raises a clear error that names the field and the bad value", and the spec's error-message rule adds that the bad value is shown for non-secret fields only.
    - The Telegram error tells a caller who passed a number that only strings are valid, but an int chat id is accepted.
    - The receipt URL is a public issue or page link, not a secret, yet the receipt error omits it.
    A reviewer would write: "This says 'string' but ints are allowed. Say 'an int or a non-blank string'."
  Smallest fix:
    - In telegram.py, raise `ConfigurationError(f"chat_id must be an int or a non-blank string, got {chat_id!r}.")` for non-int, non-str input.
    - Append `got {self.url!r}` to dataclasses/outputs.py:67.
  Spec IDs: n/a

R-V5 [Minor] [constants / A007 spirit] vidbyte/lib/outputs/jira.py:73 — The Jira REST path and API version are inlined, while every other connector names its endpoint in constants
  Evidence:
    jira.py:73 `request = OutputRequest(f"https://{self._site}/rest/api/3/issue", ...)`
    Compare github.py:53, which uses `GITHUB_API_URL` and `GITHUB_API_VERSION`, and the Linear and Notion connectors, which use `LINEAR_GRAPHQL_URL` and `NOTION_PAGES_URL` from lib/constants/outputs.py. lib/constants/outputs.py has no Jira path constant.
  Failure: AGENTS.md placement and the strict-config-dataclasses field guide put fixed provider values in `lib/constants/<domain>.py`. A Jira API version bump becomes a search through f-strings instead of a one-line constant change. A reviewer would write: "Name this like the others: JIRA_ISSUE_PATH = '/rest/api/3/issue'."
  Smallest fix: Add `JIRA_ISSUE_PATH = "/rest/api/3/issue"` (and, if wanted, `JIRA_BROWSE_PATH = "/browse/"`) to lib/constants/outputs.py and use them at jira.py:73.
  Spec IDs: n/a

R-V6 [Minor] [folder README] vidbyte/agents/output/README.md:1 — The new agents/output README has no Non-Goals section
  Evidence:
    `grep "^## " vidbyte/agents/output/README.md` → `## Modules`, `## When Delivery Runs`, `## Forks And Sub-Agents`, `## Failure Behavior`.
    Sibling READMEs have one: vidbyte/agents/multi/README.md:15 `## Non-Goals`, vidbyte/agents/codex/README.md:1095 `## Non-Goals`, and this PR's own vidbyte/lib/outputs/README.md:17 `## Non-goals`.
  Failure: Agentic-engineering folder-README practice requires intent, Non-Goals, a file index and logs. The agent-side folder is where a reader decides whether delivery may be extended to OAuth, MCP, sub-agents or forks. Those are settled no-gos, and they are written only in the lib README. A reviewer would write: "Add Non-Goals here, as multi/ and lib/outputs/ have."
  Smallest fix: Add a short `## Non-Goals` section restating the settled exclusions: no OAuth or MCP, no delivery from forks or sub-agents, no retries beyond the lib policy, and the out-of-scope Q-1..Q-10. Use one bullet per item and no new behavior.
  Spec IDs: n/a

VERIFIED CLAIMS:
- "Lint passes with no new findings": HELD. `SDK-LINT: PASS`, exit 0, and the per-rule `--all` WHERE lines show no hit in a new file. S020's single hit is pre-existing at vidbyte/agents/multi/README.md:26.
- "_generate_reply's S008 shape is unchanged": HELD. C901 10, PLR0912 9, PLR0915 50 on both the branch (line 826) and main (line 821).
- "base.py stays within its line budget": HELD. numstat shows 29 added and 4 removed.
- "No new I001 or mypy errors": HELD. The I001 hits are only the pre-existing errors/__init__.py:22 and base.py:24/426/454. mypy reports 349 errors, none in a new module.
- "Contract regenerated after the export change": HELD. `--check` → current at 839e8e33, 623 exports. The root gains 17 names; `vidbyte.agents.output` exports 18.
- "Comments wrapped at 72 columns": HELD. The scan of added comment lines printed nothing.
- "lib never imports agents / no misplaced dataclass or enum": HELD.
- "Only new `except BaseException` re-raises": HELD, at base.py `_deliver_outputs`.
- "No suppressions added": HELD. No `noqa`, `type: ignore`, `pragma: no cover`, TODO or FIXME in added lines.
- "Feature tests pass": HELD. The pack gives 313 passed and the pinned suites give 94 passed.
- "delivery.py is the only module that creates error codes" (file header): DID NOT HOLD. See R-V3.
- "Validation rules defined once": DID NOT HOLD. See R-V1.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python lint/run.py` → `S020 RATCHETED: 1 known finding(s).` / `SDK-LINT: PASS` / `exit=0`
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) python lint/run.py --rule S020 --all` → `vidbyte/agents/multi/README.md:26 File Index entry multi_agent.py is out of parity` (pre-existing)
- `python lint/run.py --rule <A001|A002|A003|A006|A007|S008|S051|C016> --all`, filtered by WHERE for touched files → only the pre-existing hits listed above. `--rule S062 --all` fails with a Windows console UnicodeEncodeError; the full run shows S062 889/889 RATCHETED.
- `python -m mypy --config-file lint/mypy.ini vidbyte` → 349 errors, 0 in vidbyte/agents/output, vidbyte/lib/outputs, or lib/{enums,constants,dataclasses}/outputs.py
- `ruff check --select C901,PLR0912,PLR0915` on base.py (branch and main) → `_generate_reply` 10 / 9 / 50 on both
- `git diff --numstat origin/main...9463c348 -- vidbyte/agents/base.py` → `29	4	vidbyte/agents/base.py`
- `ruff check --select I001` filtered to touched files → errors/__init__.py:22 and base.py:24/426/454 only (pre-existing); total 222
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 839e8e33... (vidbyte-sdk 0.2.1, 623 exports)`
- `python -m pytest tests/features/agent_output_connectors -q` → `313 passed in 1.56s`
- `python -m pytest <jev_agent, coding_agent contract, readme size, fork isolation, restore_output_schema> -q` → `94 passed in 0.69s`
- 72-column scan of added `#` comment lines → no output
- `git diff origin/main...9463c348 | grep -nE "^\+.*(TODO|FIXME|noqa|type: ignore|pragma: no cover)"` → no output
- Python probe of the TelegramOutput(chat_id=True / 1.5) and DeliveryReceipt(url=...) errors → the three ConfigurationError lines quoted in R-V4
- `grep -n` / `sed -n` anchors on jira.py, github.py, connector.py, dispatcher.py, delivery.py, base.py, dataclasses/outputs.py, email.py, telegram.py and the jev headers → quoted under each finding
