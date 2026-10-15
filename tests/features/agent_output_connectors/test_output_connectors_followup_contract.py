"""FILE: tests/features/agent_output_connectors/test_output_connectors_followup_contract.py

PURPOSE: Prove the follow-ups' structural contract: the two new enums and their members, where each new class lives and which export lists carry it, the moved response readers, and the documentation the spec requires (dated provider rows, the Email-in and Webhook receivers sections, the vendor notes, the first spec's corrected catalog and revision row, and no stale "eleven connectors" count).
ROLE IN CODEBASE: Static checks over vidbyte/lib/enums, vidbyte/lib/outputs, vidbyte/lib/dataclasses/outputs.py, the root and agent-side exports, vidbyte/lib/outputs/README.md, REPO_MAP.md, the folder READMEs, and docs/spec/agent-output-connectors/spec.md, against docs/spec/output-connector-followups/spec.md §8.5, §9.4, and §12.3 rows 1, 2, 4, 6, 8, 15, 19 to 26, 29, and 31 to 33.
ARCHITECTURE NOTE: Feature modules are imported inside each test (importlib), so a missing module is a failing test, not a collection error. Documents are read as UTF-8 text from the repository root.
FUNCTION INVENTORY: test_new_enums_* (FR-29, D-2, D-19); test_new_classes_live_* (§12.3 placement); test_output_responses_* (D-2); test_docs_* (AC-35, NFR-8); _section, _rows_naming, _module_docstring.
COMMON MODIFICATION PATTERNS: Add a required README phrase to the matching table; keep each phrase one the spec names, not wording chosen here.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert README prose beyond the names, links, and dates §12.3 row 29 requires. 2. Do not read any other file under docs/.
KNOWN EDGE CASES: A provider row is found by its credential variable, as the first-batch docs test does, so one row may serve several checks. The "eleven" check looks only for a count of connectors or destinations, so an unrelated use of the word stays allowed.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§6.2 AC-26, AC-35; §8.5; §12.3 rows 29 and 33; §15 verified sources)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_followup_contract.py
"""

from __future__ import annotations

import ast
import importlib
import json
import re
from pathlib import Path

import pytest

from tests.features.agent_output_connectors.factories import (
    GITHUB_CREATED,
    GITHUB_ISSUE_URL,
    GITHUB_TOKEN,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
NEW_CONNECTOR_MODULES = {
    "GitLabIssueOutput": "vidbyte.lib.outputs.gitlab",
    "GitHubJobSummaryOutput": "vidbyte.lib.outputs.github_job_summary",
    "ConfluencePageOutput": "vidbyte.lib.outputs.confluence",
    "TypefullyDraftOutput": "vidbyte.lib.outputs.typefully",
    "HubSpotTaskOutput": "vidbyte.lib.outputs.hubspot",
}


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} is missing"
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    # The body of one "## <heading>" section, up to the next second-level heading.
    match = re.search(rf"^## {re.escape(heading)}\b.*?(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, f"README has no '## {heading}' section"
    return match.group(0)


def _rows_naming(text: str, name: str) -> list[str]:
    return [line for line in text.splitlines() if line.lstrip().startswith("|") and name in line]


def _module_docstring(path: Path) -> str:
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""


# --- Enums and placement ---------------------------------------------------


def test_new_enums_have_the_documented_members_and_live_in_lib_enums(output_api) -> None:
    # §8.5 / §12.3 rows 1-2 / D-19: two str enums in vidbyte/lib/enums/outputs.py, both in the package export list.
    enums = importlib.import_module("vidbyte.lib.enums")
    vidbyte = importlib.import_module("vidbyte")

    assert [member.value for member in enums.OutputMethod] == ["GET", "POST", "PATCH"]
    assert [member.value for member in enums.TypefullyPlatform] == ["x", "linkedin", "threads", "bluesky", "mastodon"]
    assert {"OutputMethod", "TypefullyPlatform"} <= set(enums.__all__)
    assert {kind.__module__ for kind in (enums.OutputMethod, enums.TypefullyPlatform)} == {"vidbyte.lib.enums.outputs"}
    assert issubclass(enums.OutputMethod, str) and issubclass(enums.TypefullyPlatform, str)
    assert output_api.TypefullyPlatform is enums.TypefullyPlatform is vidbyte.TypefullyPlatform


def test_new_classes_live_in_their_modules_and_only_the_documented_ones_are_re_exported() -> None:
    # §12.3 rows 4, 6, 8, 15, 19-24: one home per class; helpers stay out of the vidbyte.lib.outputs export list except OutputAdf.
    lib_outputs = importlib.import_module("vidbyte.lib.outputs")
    delivery = importlib.import_module("vidbyte.lib.outputs.delivery")
    github_api = importlib.import_module("vidbyte.lib.outputs.github_api")
    records = importlib.import_module("vidbyte.lib.dataclasses.outputs")

    assert {name: getattr(lib_outputs, name).__module__ for name in NEW_CONNECTOR_MODULES} == NEW_CONNECTOR_MODULES
    assert "OutputAdf" in lib_outputs.__all__ and lib_outputs.OutputAdf.__module__ == "vidbyte.lib.outputs.adf"
    assert "OutputResponses" in delivery.__all__ and delivery.OutputResponses.__module__ == "vidbyte.lib.outputs.delivery"
    assert {"GitHubRequests", "GitHubResponses"} <= set(github_api.__all__)
    assert {"OutputResponses", "GitHubRequests", "GitHubResponses"}.isdisjoint(lib_outputs.__all__)
    assert "OutputRead" in records.__all__ and records.OutputRead.__module__ == "vidbyte.lib.dataclasses.outputs"


def test_output_responses_read_errors_and_links_as_the_first_batch_did() -> None:
    # D-2: error_code and link moved unchanged from OutputHttp, so their results are the first batch's.
    delivery = importlib.import_module("vidbyte.lib.outputs.delivery")
    records = importlib.import_module("vidbyte.lib.dataclasses.outputs")
    transport = importlib.import_module("vidbyte.lib.http.transport")
    request = records.OutputRequest("https://api.github.com/repos/acme/shop/issues", {"authorization": f"Bearer {GITHUB_TOKEN}"}, {"title": "x"}, link_path=("html_url",))

    assert delivery.OutputResponses.error_code(transport.HttpResponse(status_code=404, body="channel_not_found", headers={})) == "http_404:channel_not_found"
    assert delivery.OutputResponses.error_code(transport.HttpResponse(status_code=500, body="<html>", headers={})) == "http_500"
    assert delivery.OutputResponses.link(transport.HttpResponse(status_code=201, body=GITHUB_CREATED, headers={}), request) == GITHUB_ISSUE_URL
    assert delivery.OutputResponses.link(transport.HttpResponse(status_code=201, body=json.dumps({"html_url": "http://x"}), headers={}), request) is None


# --- Documentation ---------------------------------------------------------

CHANGED_ROWS = {
    "SLACK_WEBHOOK_URL": ("12,000", "markdown"),
    "DISCORD_WEBHOOK_URL": ("thread_id", "forum_tags", "wait=true"),
    "TEAMS_WEBHOOK_URL": (),
    "GOOGLE_CHAT_WEBHOOK_URL": ("markupSyntax",),
    "TELEGRAM_BOT_TOKEN": ("sendRichMessage", "32,768", "topic_id", "@"),
    "GITHUB_TOKEN": ("comment_on", "key"),
    "LINEAR_API_KEY": ("comment_on", "labels"),
    "JIRA_API_TOKEN": ("comment_on", "labels", "365"),
    "NOTION_API_KEY": ("append_to",),
    "VIDBYTE_OUTPUT_WEBHOOK_URL": ("headers", "payload", "secret"),
    "GITLAB_TOKEN": ("GitLabIssueOutput",),
    "GITHUB_STEP_SUMMARY": ("GitHubJobSummaryOutput",),
    "CONFLUENCE_API_TOKEN": ("ConfluencePageOutput",),
    "TYPEFULLY_API_KEY": ("TypefullyDraftOutput",),
    "HUBSPOT_ACCESS_TOKEN": ("HubSpotTaskOutput", "Legacy"),
}


@pytest.mark.parametrize(("env_var", "phrases"), list(CHANGED_ROWS.items()), ids=list(CHANGED_ROWS))
def test_docs_changed_and_new_provider_rows_carry_their_facts_a_link_and_the_new_date(env_var, phrases) -> None:
    # AC-35 / §12.3 row 29 / NFR-8: every changed or added row has an official link and 2026-10-14.
    rows = _rows_naming(_read("vidbyte/lib/outputs/README.md"), env_var)

    complete = [row for row in rows if "https://" in row and "2026-10-14" in row and all(phrase in row for phrase in phrases)]
    assert complete, f"no {env_var} row with https://, 2026-10-14, and {phrases}: {rows}"


def test_docs_webhook_row_no_longer_says_the_request_is_unsigned() -> None:
    # AC-35 / §12.3 row 29: secret= signs the request, so "unsigned" would now be false.
    rows = _rows_naming(_read("vidbyte/lib/outputs/README.md"), "VIDBYTE_OUTPUT_WEBHOOK_URL")

    assert rows and [row for row in rows if "unsigned" in row.lower()] == []


def test_docs_teams_note_names_the_legacy_trigger_and_the_group_chat_template() -> None:
    # AC-35 / §B 0 Teams note: Microsoft labels the "Anyone" trigger Legacy; group chats use a named template.
    text = _read("vidbyte/lib/outputs/README.md")

    assert "Legacy" in text and "Send webhook alerts to a chat" in text


EMAIL_IN_NAMES = ("Linear", "Trello", "Asana", "ClickUp", "monday.com", "Todoist", "PagerDuty", "Zendesk", "Freshdesk", "Help Scout", "Slack", "Teams", "Evernote", "Basecamp", "Auto-Submitted", "Precedence")
WEBHOOK_RECEIVER_NAMES = ("Apps Script", "http_302", "n8n", "Make", "Zapier", "webhook-id", "webhook-timestamp", "ntfy", "Gotify", "Home Assistant", "Pushcut", "Apprise", "Inngest", "incident.io", "Mattermost", "Rocket.Chat", "Jira Automation")


@pytest.mark.parametrize(
    ("heading", "names", "min_links"),
    [pytest.param("Email-in", EMAIL_IN_NAMES, 14, id="email-in"), pytest.param("Webhook receivers", WEBHOOK_RECEIVER_NAMES, 10, id="webhook-receivers")],
)
def test_docs_new_readme_sections_cover_every_named_tool_with_official_links(heading, names, min_links) -> None:
    # AC-35 / §12.3 row 29 / §15: each section names every tool the spec lists, each with its official page.
    section = _section(_read("vidbyte/lib/outputs/README.md"), heading)

    assert [name for name in names if name not in section] == []
    assert section.count("https://") >= min_links


FIRST_SPEC_CATALOG_NAMES = ("Typefully", "Buffer", "Apprise", "Telnyx", "Plivo", "Telesign", "Zendesk", "Shopify", "Greenhouse", "Bandwidth", "Bitbucket", "Relay.app", "OneNote", "LINE Notify")


def test_docs_first_spec_catalog_carries_the_corrections_and_a_revision_row() -> None:
    # AC-35 / §12.3 row 33: the first spec's §9.2(b) is corrected, and §17 records r9 for this follow-up.
    text = _read("docs/spec/agent-output-connectors/spec.md")
    start = text.index("**Platform catalog (b)")
    catalog = text[start : text.index("### 9.3", start)]

    assert [name for name in FIRST_SPEC_CATALOG_NAMES if name not in catalog] == []
    assert [line for line in text.splitlines() if line.startswith("| r9 |") and "output-connector-followups" in line]


ELEVEN_COUNT = re.compile(r"\beleven\b[^.\n]{0,40}\b(connectors|destinations)\b", flags=re.IGNORECASE)
COUNTED_DOCS = ("REPO_MAP.md", "vidbyte/lib/README.md", "vidbyte/lib/outputs/README.md", "vidbyte/agents/output/README.md")


def test_docs_no_module_header_or_readme_still_counts_eleven_connectors() -> None:
    # AC-35 / §12.3 rows 25, 26, 31, 32: there are sixteen now, so an "eleven connectors" count is stale.
    headers = [REPO_ROOT / "vidbyte" / "__init__.py", *sorted((REPO_ROOT / "vidbyte" / "agents" / "output").glob("*.py")), *sorted((REPO_ROOT / "vidbyte" / "lib" / "outputs").glob("*.py"))]

    stale = [path.relative_to(REPO_ROOT).as_posix() for path in headers if ELEVEN_COUNT.search(_module_docstring(path))]
    stale += [relative for relative in COUNTED_DOCS if ELEVEN_COUNT.search(_read(relative))]
    assert stale == []
