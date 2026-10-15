"""FILE: tests/features/agent_output_connectors/test_output_connectors_rendering.py

PURPOSE: Prove the follow-ups' richer rendering for chat and issue destinations: Discord forum posts with a one-line thread name and tags, Slack Markdown blocks with mentions kept inert (and the escaped-text path above 12,000 characters), Telegram rich Markdown with no HTML tag or media block and an optional forum topic, the two-block full-width Teams card, and the Atlassian Document Format that Jira descriptions are built with.
ROLE IN CODEBASE: Contract tests of vidbyte/lib/outputs/discord.py, slack.py, telegram.py, teams.py, jira.py, and adf.py (OutputAdf.document) through the public connectors and vidbyte.lib.outputs.OutputAdf, against docs/spec/output-connector-followups/spec.md §9.2 table (a).
ARCHITECTURE NOTE: Connectors are driven directly with connector.send(reply, OutputContent(...)) over the scripted HttpTransport._send_once (fake_http); OutputAdf.document is called directly for the block rules and through JiraIssueOutput for the wire shape.
FUNCTION INVENTORY: test_discord_* (AC-2, AC-3, EC-5, INV-6); test_slack_* (AC-4, EC-6, INV-5, D-7); test_telegram_* (AC-5, AC-6, INV-18, EC-43, EC-44, D-8); test_teams_* (AC-7, EC-11, D-9); test_jira_description_* (AC-8, EC-12); test_adf_document_* (D-10, EC-13, EC-14, R-13).
COMMON MODIFICATION PATTERNS: Add a rendering case as one table row with its literal expected wire value; keep expected text written out, never computed with the constants module.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.lib.constants.outputs to build an expected value. 2. Do not assert ADF node boilerplate the spec leaves open (orderedList attrs, how code lines split into text nodes); compare through _outline.
KNOWN EDGE CASES: chat_text drops the title when the body's first line already is the title, so the Slack, Teams, and Telegram cases pick bodies that do or do not repeat it on purpose. The Telegram replacements are length-preserving, so an expected text has the same length as its input. ADF paragraph text is compared after rstrip, because EC-14 and INV-2 disagree on a line's trailing whitespace (reported to the orchestrator).
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§6.1 INV-5, INV-6, INV-18; §6.2 AC-2 to AC-8; §6.3 EC-5, EC-6, EC-11 to EC-14, EC-43, EC-44; §8.1 D-6 to D-10)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_rendering.py
"""

from __future__ import annotations

import importlib
import re

import pytest

from tests.features.agent_output_connectors.factories import (
    DISCORD_URL,
    JIRA_TOKEN,
    SLACK_URL,
    TEAMS_URL,
    TELEGRAM_TOKEN,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ConfigurationError

MARKER = "\n\n[truncated]"
NO_LANGUAGE = "(no language)"
CARD_TYPE = "application/vnd.microsoft.card.adaptive"


def _names(word: str, message: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


async def _send(output_api, fake_http, connector, host: str, success: tuple[int, str], title: str, body: str):
    # Answers the destination with success, sends one reply, and returns its receipt and the one recorded request.
    fake_http.answer(host, success)
    receipt = await connector.send(build_reply(body), output_api.OutputContent(title, body))
    [send] = fake_http.sends
    return receipt, send


def _adf(markdown: str):
    return importlib.import_module("vidbyte.lib.outputs").OutputAdf.document(markdown)


def _inline_text(node) -> str:
    return "".join(child["text"] for child in node["content"])


def _item_text(item) -> str:
    # A listItem holds exactly one paragraph (D-10, ADF node rules).
    assert item["type"] == "listItem", item
    [paragraph] = item["content"]
    assert paragraph["type"] == "paragraph", paragraph
    return _inline_text(paragraph).rstrip()


def _code_lines(block) -> list[str]:
    # How code lines split into text nodes is open, so compare the non-blank lines.
    return [line for line in "\n".join(node["text"] for node in block["content"]).splitlines() if line]


def _outline(doc) -> list[tuple[object, ...]]:
    # Flattens an ADF document into one row per block, so a test reads the block order without node boilerplate.
    rows: list[tuple[object, ...]] = []
    for block in doc["content"]:
        kind = block["type"]
        if kind == "paragraph":
            rows.append(("paragraph", _inline_text(block).rstrip()))
        elif kind == "heading":
            rows.append(("heading", block["attrs"]["level"], _inline_text(block)))
        elif kind in ("bulletList", "orderedList"):
            rows.append((kind, [_item_text(item) for item in block["content"]]))
        elif kind == "codeBlock":
            rows.append(("codeBlock", block.get("attrs", {}).get("language", NO_LANGUAGE), _code_lines(block)))
        else:
            rows.append((kind,))
    return rows


def _text_nodes(node) -> list[dict]:
    # Every text node anywhere in the document, depth first.
    if node.get("type") == "text":
        return [node]
    return [found for child in node.get("content", []) for found in _text_nodes(child)]


def _assert_valid_adf(doc) -> None:
    # ADF rejects empty text, and D-10 adds no inline marks.
    assert (doc["type"], doc["version"]) == ("doc", 1)
    for node in _text_nodes(doc):
        assert isinstance(node["text"], str) and node["text"] != "", node
        assert "marks" not in node, node


# --- Discord ---------------------------------------------------------------

FORUM_TITLE = "Checkout fails\n" + "y" * 285
FORUM_CHAT = FORUM_TITLE + "\n\nSteps: x"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "extra"),
    [
        pytest.param({"forum": True, "forum_tags": ["1203040506070809", "99"]}, {"thread_name": "Checkout fails " + "y" * 85, "applied_tags": ["1203040506070809", "99"]}, id="forum-with-tags"),
        pytest.param({"forum": True}, {"thread_name": "Checkout fails " + "y" * 85}, id="forum-without-tags"),
        pytest.param({"forum": False}, {}, id="not-a-forum-is-todays-body"),
    ],
)
async def test_discord_forum_post_adds_a_one_line_thread_name_and_its_tags(output_api, fake_http, options, extra) -> None:
    # AC-2 / EC-5 / INV-6 / D-6: a 300-character two-line title becomes a 100-character one-line thread name; mentions stay off.
    connector = output_api.DiscordOutput(webhook_url=DISCORD_URL, **options)

    receipt, send = await _send(output_api, fake_http, connector, "discord.com", (204, ""), FORUM_TITLE, "Steps: x")

    assert send["url"] == DISCORD_URL
    assert send["json_body"] == {"content": FORUM_CHAT, "allowed_mentions": {"parse": []}, **extra}
    assert receipt_rows([receipt]) == [("discord", "sent", None, None)]


@pytest.mark.parametrize(
    ("options", "parameter"),
    [
        pytest.param({"forum_tags": ["1203040506070809"]}, "forum_tags", id="tags-without-forum"),
        pytest.param({"forum": False, "forum_tags": ["1"]}, "forum_tags", id="tags-with-forum-false"),
        pytest.param({"forum": True, "forum_tags": ["12a"]}, "forum_tags", id="tag-not-all-digits"),
        pytest.param({"forum": True, "forum_tags": [""]}, "forum_tags", id="blank-tag"),
        pytest.param({"forum": True, "forum_tags": "1203040506070809"}, "forum_tags", id="tags-as-one-string"),
        pytest.param({"forum": True, "forum_tags": [1203040506070809]}, "forum_tags", id="tag-as-int"),
        pytest.param({"forum": "true"}, "forum", id="forum-as-text"),
        pytest.param({"forum": 1}, "forum", id="forum-as-int"),
        pytest.param({"forum": None}, "forum", id="forum-none"),
    ],
)
def test_discord_forum_arguments_are_checked_at_construction(output_api, options, parameter) -> None:
    # AC-3 / INV-11: a forum setting Discord would reject fails before any request, naming the parameter.
    with pytest.raises(ConfigurationError) as info:
        output_api.DiscordOutput(webhook_url=DISCORD_URL, **options)

    assert _names(parameter, str(info.value)), str(info.value)
    assert "S3CRET" not in str(info.value)


# --- Slack -----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "body", "expected"),
    [
        pytest.param(
            "Deploy <failed>\n& rolled back",
            "Steps: <!channel> and <@U123> see <https://ci.acme.dev|log>",
            {"text": "Deploy &lt;failed&gt; &amp; rolled back", "blocks": [{"type": "markdown", "text": "Deploy <failed>\n& rolled back\n\nSteps: ＜!channel> and ＜@U123> see <https://ci.acme.dev|log>"}]},
            id="mentions-inert-title-one-line-and-escaped",
        ),
        pytest.param("&" * 300, "Body", {"text": "&amp;" * 250, "blocks": [{"type": "markdown", "text": "&" * 300 + "\n\nBody"}]}, id="title-cut-to-250-before-escaping"),
    ],
)
async def test_slack_reply_up_to_12000_characters_is_a_markdown_block_with_an_escaped_one_line_title(output_api, fake_http, title, body, expected) -> None:
    # AC-4 / INV-5 / D-7: only "<!" and "<@" change inside the block; the fallback text is the title, escaped after the cut.
    connector = output_api.SlackOutput(webhook_url=SLACK_URL)

    receipt, send = await _send(output_api, fake_http, connector, "hooks.slack.com", (200, "ok"), title, body)

    assert send["json_body"] == expected
    assert send["headers"]["content-type"] == "application/json"
    assert receipt_rows([receipt]) == [("slack", "sent", None, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("length", "expected_text_of"),
    [
        pytest.param(12_000, lambda xs: {"text": "Load test", "blocks": [{"type": "markdown", "text": "Load test\n\n＜!here> " + xs}]}, id="12000-markdown-block"),
        pytest.param(12_001, lambda xs: {"text": "Load test\n\n&lt;!here&gt; " + xs}, id="12001-escaped-text"),
    ],
)
async def test_slack_switches_to_todays_escaped_text_above_12000_characters(output_api, fake_http, length, expected_text_of) -> None:
    # EC-6 / D-7 / INV-5: the block holds at most 12,000 characters; longer replies keep the escaped text, still inert.
    xs = "x" * (length - len("Load test\n\n<!here> "))
    connector = output_api.SlackOutput(webhook_url=SLACK_URL)

    _, send = await _send(output_api, fake_http, connector, "hooks.slack.com", (200, "ok"), "Load test", "<!here> " + xs)

    assert send["json_body"] == expected_text_of(xs)


# --- Telegram --------------------------------------------------------------

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendRichMessage"
TELEGRAM_OK = (200, '{"ok": true, "result": {"message_id": 7}}')
HOSTILE_BODY = 'Press <tg-button type="callback_data" data="x">Go</tg-button>, see ![](https://example.com/x.pdf), [docs](https://example.com/docs), and [Ann](tg://user?id=42).'
INERT_CHAT = 'Deploy report\n\nPress ＜tg-button type="callback_data" data="x">Go＜/tg-button>, see !［](https://example.com/x.pdf), [docs](https://example.com/docs), and [Ann](tg://user?id=42).'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "expected"),
    [
        pytest.param({"chat_id": -100123, "topic_id": 7}, {"chat_id": -100123, "message_thread_id": 7, "rich_message": {"markdown": INERT_CHAT}}, id="topic"),
        pytest.param({"chat_id": -100123}, {"chat_id": -100123, "rich_message": {"markdown": INERT_CHAT}}, id="no-topic"),
        pytest.param({"chat_id": "@acme_alerts", "topic_id": 7}, {"chat_id": "@acme_alerts", "message_thread_id": 7, "rich_message": {"markdown": INERT_CHAT}}, id="channel-username"),
    ],
)
async def test_telegram_sends_rich_markdown_with_no_html_tag_and_no_media_block(output_api, fake_http, options, expected) -> None:
    # AC-5 / EC-43 / EC-44 / INV-18 / D-8: a <tg-button> or ![](…) in reply text must not become a button or a posted file.
    connector = output_api.TelegramOutput(bot_token=TELEGRAM_TOKEN, **options)

    receipt, send = await _send(output_api, fake_http, connector, "api.telegram.org", TELEGRAM_OK, "Deploy report", HOSTILE_BODY)

    assert send["url"] == TELEGRAM_URL
    assert send["json_body"] == expected
    markdown = send["json_body"]["rich_message"]["markdown"]
    assert "<" not in markdown and "![" not in markdown
    assert receipt_rows([receipt]) == [("telegram", "sent", None, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("if a < b and x <= y", "if a ＜ b and x ＜= y", id="comparisons"),
        pytest.param("cat <<EOF", "cat ＜＜EOF", id="heredoc"),
        pytest.param("<https://example.com>", "＜https://example.com>", id="autolink"),
        pytest.param("![x][ref]", "!［x][ref]", id="reference-image"),
        pytest.param("![x](tg://emoji?id=5368324170671202286)", "!［x](tg://emoji?id=5368324170671202286)", id="custom-emoji"),
        pytest.param("!![x](https://e.com/a.png)", "!!［x](https://e.com/a.png)", id="double-bang"),
        pytest.param("! [x](https://e.com/a.png)", "! [x](https://e.com/a.png)", id="bang-space-untouched"),
        pytest.param("[Ann](tg://user?id=42) costs $5 and $10", "[Ann](tg://user?id=42) costs $5 and $10", id="mention-and-dollars-untouched"),
        # R-1 / INV-18: several blocks and tags in one reply, so a
        # replacement of only the first one fails.
        pytest.param(
            "<b>one</b> ![a](https://x/1.png) text ![b](https://x/2.png) and ![c][ref]",
            "＜b>one＜/b> !［a](https://x/1.png) text !［b](https://x/2.png) and !［c][ref]",
            id="every-media-block-and-tag",
        ),
    ],
)
async def test_telegram_neutralization_changes_only_tag_starts_and_media_brackets(output_api, fake_http, text, expected) -> None:
    # INV-18: every "<" and every "[" after "!" become fullwidth; nothing else changes and the length is kept.
    connector = output_api.TelegramOutput(chat_id=-100123, bot_token=TELEGRAM_TOKEN)

    _, send = await _send(output_api, fake_http, connector, "api.telegram.org", TELEGRAM_OK, "T", text)

    assert send["json_body"]["rich_message"]["markdown"] == "T\n\n" + expected


@pytest.mark.parametrize("topic_id", [True, 0, -1, "7", 7.5], ids=["bool", "zero", "negative", "text", "float"])
def test_telegram_topic_id_must_be_a_positive_int(output_api, topic_id) -> None:
    # AC-6 / FR-9: Telegram reads message_thread_id as a positive integer.
    with pytest.raises(ConfigurationError) as info:
        output_api.TelegramOutput(chat_id=-100123, topic_id=topic_id, bot_token=TELEGRAM_TOKEN)

    assert _names("topic_id", str(info.value)), str(info.value)


# --- Teams -----------------------------------------------------------------


def _title_block(text: str) -> dict:
    return {"type": "TextBlock", "text": text, "weight": "Bolder", "size": "Medium", "wrap": True}


def _body_block(text: str) -> dict:
    return {"type": "TextBlock", "text": text, "wrap": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "body", "blocks"),
    [
        pytest.param("Checkout fails", "# Checkout fails\n\nSteps: x", [_title_block("Checkout fails"), _body_block("Steps: x")], id="a-body-repeats-the-title"),
        pytest.param("Load test", "Results\n\nAll green", [_title_block("Load test"), _body_block("Results\n\nAll green")], id="b-body-does-not-repeat-the-title"),
        pytest.param("Checkout fails", "Checkout fails", [_title_block("Checkout fails")], id="c-body-is-only-the-title"),
        pytest.param("Checkout fails", "## Checkout fails\n\n", [_title_block("Checkout fails")], id="c-title-line-then-blank-lines"),
        pytest.param("Checkout fails", "\n\n## Checkout fails\n\n\nSteps: x\n\nMore", [_title_block("Checkout fails"), _body_block("Steps: x\n\nMore")], id="d-leading-blank-lines-dropped"),
        pytest.param("Checkout\nfails", "Steps: x", [_title_block("Checkout fails"), _body_block("Steps: x")], id="e-title-on-one-line"),
    ],
)
async def test_teams_card_has_a_bold_title_block_and_the_body_without_a_repeated_title(output_api, fake_http, title, body, blocks) -> None:
    # AC-7 / EC-11 / D-9: the title shows once, in bold, on a full-width card; a blank remainder leaves no empty block.
    connector = output_api.TeamsOutput(webhook_url=TEAMS_URL)

    receipt, send = await _send(output_api, fake_http, connector, "powerplatform.com", (202, ""), title, body)

    card = {"type": "AdaptiveCard", "version": "1.2", "body": blocks, "msteams": {"width": "Full"}}
    assert send["json_body"] == {"type": "message", "attachments": [{"contentType": CARD_TYPE, "contentUrl": None, "content": card}]}
    assert receipt_rows([receipt]) == [("teams", "sent", None, None)]


# --- Jira and OutputAdf ----------------------------------------------------

JIRA_SUCCESS = (201, '{"id": "10001", "key": "PROJ-1", "self": "https://acme.atlassian.net/rest/api/3/issue/10001"}')


def _jira(output_api):
    return output_api.JiraIssueOutput(site="acme.atlassian.net", project="PROJ", email="bot@acme.com", api_token=JIRA_TOKEN)


@pytest.mark.asyncio
async def test_jira_description_is_built_with_adf_blocks_in_order(output_api, fake_http) -> None:
    # AC-8 / FR-11 / D-10: a heading, two bullets, one numbered item, a fenced block, and a plain line keep their kinds.
    body = "## Steps\n- a\n- b\n1. one\n```python\nprint(1)\n```\nPlain line"

    receipt, send = await _send(output_api, fake_http, _jira(output_api), "acme.atlassian.net", JIRA_SUCCESS, "Checkout fails", body)

    description = send["json_body"]["fields"]["description"]
    _assert_valid_adf(description)
    assert _outline(description) == [("heading", 2, "Steps"), ("bulletList", ["a", "b"]), ("orderedList", ["one"]), ("codeBlock", "python", ["print(1)"]), ("paragraph", "Plain line")]
    assert receipt_rows([receipt]) == [("jira_issue", "sent", "https://acme.atlassian.net/browse/PROJ-1", None)]


@pytest.mark.asyncio
async def test_jira_description_cut_inside_an_open_fence_ends_its_code_block_with_the_marker(output_api, fake_http) -> None:
    # EC-12 / D-10: truncation runs first, so an unclosed fence runs to the end and holds the [truncated] line.
    body = "Intro\n```\n" + "x" * 40_000

    _, send = await _send(output_api, fake_http, _jira(output_api), "acme.atlassian.net", JIRA_SUCCESS, "Load test", body)

    description = send["json_body"]["fields"]["description"]
    _assert_valid_adf(description)
    xs = "x" * (32_767 - len("Intro\n```\n") - len(MARKER))
    assert _outline(description) == [("paragraph", "Intro"), ("codeBlock", NO_LANGUAGE, [xs, "[truncated]"])]


ADF_CASES = [
    pytest.param("Plain line\nSecond line", [("paragraph", "Plain line"), ("paragraph", "Second line")], id="plain-lines-one-paragraph-each"),
    pytest.param("# H1\n###### H6", [("heading", 1, "H1"), ("heading", 6, "H6")], id="heading-levels-1-and-6"),
    pytest.param("####### x\n#x\n-x", [("paragraph", "####### x"), ("paragraph", "#x"), ("paragraph", "-x")], id="EC-13-not-headings-or-items"),
    pytest.param("1. a\n\n2. b", [("orderedList", ["a", "b"])], id="loose-ordered-list-is-one-list"),
    pytest.param("- a\n\n- b", [("bulletList", ["a", "b"])], id="loose-bullet-list-is-one-list"),
    pytest.param("* a\n+ b\n  - c", [("bulletList", ["a", "b", "c"])], id="mixed-markers-and-indent-one-flat-list"),
    pytest.param("1) one\n2. two", [("orderedList", ["one", "two"])], id="paren-and-dot-numbers"),
    pytest.param("- a\n1. b", [("bulletList", ["a"]), ("orderedList", ["b"])], id="kind-change-starts-a-new-list"),
    pytest.param("- a\n\n1. b", [("bulletList", ["a"]), ("orderedList", ["b"])], id="blank-then-other-kind-ends-the-list"),
    pytest.param("- a\n\nplain\n- b", [("bulletList", ["a"]), ("paragraph", "plain"), ("bulletList", ["b"])], id="paragraph-between-lists"),
    pytest.param("* * *\n---\n- - -", [("paragraph", "* * *"), ("paragraph", "---"), ("paragraph", "- - -")], id="R-13-thematic-breaks-are-paragraphs"),
    pytest.param("- \nnext", [("paragraph", "-"), ("paragraph", "next")], id="EC-14-lone-marker-is-a-paragraph"),
    pytest.param("```\n```\nafter", [("paragraph", "after")], id="EC-14-empty-fence-emits-nothing"),
    pytest.param("```\nx = 1\n```", [("codeBlock", NO_LANGUAGE, ["x = 1"])], id="fence-without-language"),
    pytest.param("```js  \n- not a list\n# not a heading\n```", [("codeBlock", "js", ["- not a list", "# not a heading"])], id="code-lines-are-not-parsed"),
    pytest.param("```\ncode\nmore", [("codeBlock", NO_LANGUAGE, ["code", "more"])], id="unclosed-fence-runs-to-the-end"),
]


@pytest.mark.parametrize(("markdown", "outline"), ADF_CASES)
def test_adf_document_follows_the_block_rules_and_never_emits_empty_text(markdown, outline) -> None:
    # D-10 / EC-12 to EC-14 / R-13: flat lists, ATX headings 1-6, fences, and paragraphs; anything else stays a paragraph.
    doc = _adf(markdown)

    _assert_valid_adf(doc)
    assert _outline(doc) == outline
