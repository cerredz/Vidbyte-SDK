"""FILE: vidbyte/lib/constants/outputs.py

PURPOSE: Defines the named limits, error codes, endpoints, and credential variables used to deliver agent replies.
ROLE IN CODEBASE: Read by the output records, the provider connectors in vidbyte/lib/outputs/, and the dispatcher in vidbyte/agents/output/.
ARCHITECTURE NOTE: This module contains immutable constants only; delivery behavior lives in the connectors and the dispatcher.
COMMON MODIFICATION PATTERNS: Add a named constant here before introducing another delivery limit, version, or endpoint literal.
KNOWN EDGE CASES: The delivery deadline must stay above three request timeouts plus the 429 backoff, or a rate-limited send is cut short. A send that makes several requests (GitHub key=) can still be cut by the deadline, during its reads or during its one write.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_contract.py; the follow-up caps, URLs, and patterns are pinned through written-out wire values in test_output_connectors_rendering.py, test_output_connectors_comments.py, test_output_connectors_new_destinations.py, test_output_connectors_update_in_place.py, and test_output_connectors_webhook_options.py
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from vidbyte.lib.dataclasses.agents import AgentStopReason
from vidbyte.lib.enums.outputs import OutputDestination

# Operation
OUTPUT_TIMEOUT_SECONDS = 10.0
OUTPUT_RATE_LIMIT_RETRIES = 2
OUTPUT_RETRY_STATUS_CODES = (429,)
OUTPUT_MAX_RESPONSE_BYTES = 1_000_000
# Reads use their own ceiling: a page of 100 GitHub comments of up
# to 65,536 characters each does not fit in the write ceiling.
OUTPUT_MAX_READ_BYTES = 16_000_000
OUTPUT_DELIVERY_DEADLINE_SECONDS = 35.0
OUTPUT_HTTP_SUCCESS_MIN = 200
OUTPUT_HTTP_SUCCESS_MAX = 299
OUTPUT_DELIVERIES_METADATA_KEY = "deliveries"
OUTPUT_TRUNCATION_MARKER = "\n\n[truncated]"
OUTPUT_TITLE_MAX_CHARS = 250
OUTPUT_DELIVERABLE_STOP_REASONS: frozenset[str] = frozenset(
    {AgentStopReason.FINAL_RESPONSE.value, AgentStopReason.IS_DONE.value}
)

# Error codes
OUTPUT_ERROR_NETWORK = "network"
OUTPUT_ERROR_INVALID_RESPONSE = "invalid_response"
OUTPUT_ERROR_SMTP = "smtp_error"
OUTPUT_ERROR_SMTP_REFUSED = "smtp_recipients_refused"
OUTPUT_ERROR_FILE = "file_error"
OUTPUT_ERROR_HTTP_PREFIX = "http_"
OUTPUT_ERROR_SMTP_PREFIX = "smtp_"
OUTPUT_ERROR_UNEXPECTED_PREFIX = "unexpected:"
# A response-body error token, such as Slack's "no_service", is one
# lowercase word of at most OUTPUT_ERROR_TOKEN_MAX_CHARS characters.
OUTPUT_ERROR_TOKEN_MAX_CHARS = 64
OUTPUT_ERROR_TOKEN_PATTERN = rf"[a-z][a-z0-9_]{{0,{OUTPUT_ERROR_TOKEN_MAX_CHARS - 1}}}"

# Credentials
OUTPUT_CREDENTIAL_ENV_VARS: Mapping[OutputDestination, str] = MappingProxyType(
    {
        OutputDestination.SLACK: "SLACK_WEBHOOK_URL",
        OutputDestination.DISCORD: "DISCORD_WEBHOOK_URL",
        OutputDestination.TEAMS: "TEAMS_WEBHOOK_URL",
        OutputDestination.GOOGLE_CHAT: "GOOGLE_CHAT_WEBHOOK_URL",
        OutputDestination.TELEGRAM: "TELEGRAM_BOT_TOKEN",
        OutputDestination.EMAIL: "SMTP_PASSWORD",
        OutputDestination.GITHUB_ISSUE: "GITHUB_TOKEN",
        OutputDestination.LINEAR_ISSUE: "LINEAR_API_KEY",
        OutputDestination.JIRA_ISSUE: "JIRA_API_TOKEN",
        OutputDestination.NOTION_PAGE: "NOTION_API_KEY",
        OutputDestination.WEBHOOK: "VIDBYTE_OUTPUT_WEBHOOK_URL",
        OutputDestination.GITLAB_ISSUE: "GITLAB_TOKEN",
        OutputDestination.GITHUB_JOB_SUMMARY: "GITHUB_STEP_SUMMARY",
        OutputDestination.CONFLUENCE_PAGE: "CONFLUENCE_API_TOKEN",
        OutputDestination.TYPEFULLY_DRAFT: "TYPEFULLY_API_KEY",
        OutputDestination.HUBSPOT_TASK: "HUBSPOT_ACCESS_TOKEN",
    }
)

# Validation
# One email address: an "@", and no whitespace, line break, or comma.
OUTPUT_EMAIL_ADDRESS_PATTERN = r"[^\s,]*@[^\s,]*"
OUTPUT_HTTPS_PREFIX = "https://"
# One HTTP header name: an RFC 9110 token.
OUTPUT_HEADER_NAME_PATTERN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
OUTPUT_JSON_CONTENT_TYPE = "application/json"
OUTPUT_FILE_ENCODING = "utf-8"

# SMTP
SMTP_STARTTLS_PORT = 587
SMTP_IMPLICIT_TLS_PORT = 465
SMTP_PORT_MIN = 1
SMTP_PORT_MAX = 65_535

# Body caps
SLACK_TEXT_MAX_CHARS = 40_000
DISCORD_CONTENT_MAX_CHARS = 2_000
TEAMS_TEXT_MAX_CHARS = 7_000
GOOGLE_CHAT_TEXT_MAX_CHARS = 8_000
GITHUB_BODY_MAX_CHARS = 65_536
JIRA_TEXT_MAX_CHARS = 32_767
SLACK_MARKDOWN_MAX_CHARS = 12_000
DISCORD_THREAD_NAME_MAX_CHARS = 100
TELEGRAM_RICH_TEXT_MAX_CHARS = 32_768
GITLAB_DESCRIPTION_MAX_CHARS = 1_048_576
GITLAB_NOTE_MAX_CHARS = 1_000_000
GITHUB_JOB_SUMMARY_MAX_CHARS = 262_144
CONFLUENCE_BODY_MAX_CHARS = 500_000
HUBSPOT_TASK_BODY_MAX_CHARS = 65_536

# Mentions
GOOGLE_CHAT_MENTION_PREFIX = "<users/"
GOOGLE_CHAT_MENTION_REPLACEMENT = "＜users/"
NOTION_MENTION_PREFIX = "<mention-"
NOTION_MENTION_REPLACEMENT = "＜mention-"
SLACK_BROADCAST_PREFIX = "<!"
SLACK_BROADCAST_REPLACEMENT = "＜!"
SLACK_USER_MENTION_PREFIX = "<@"
SLACK_USER_MENTION_REPLACEMENT = "＜@"
# Telegram rich text: no HTML tag and no media block may open.
TELEGRAM_TAG_PREFIX = "<"
TELEGRAM_TAG_REPLACEMENT = "＜"
TELEGRAM_MEDIA_PREFIX = "!["
TELEGRAM_MEDIA_REPLACEMENT = "!［"

# Endpoints and versions
TEAMS_ADAPTIVE_CARD_VERSION = "1.2"
TEAMS_CARD_WIDTH = "Full"
TEAMS_TITLE_WEIGHT = "Bolder"
TEAMS_TITLE_SIZE = "Medium"
DISCORD_SNOWFLAKE_PATTERN = r"[0-9]+"
TELEGRAM_API_URL = "https://api.telegram.org"
TELEGRAM_RICH_METHOD = "sendRichMessage"
GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
GITHUB_REPO_PATTERN = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_ISSUE_CREATE_MUTATION = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { url } } }"
LINEAR_COMMENT_CREATE_MUTATION = "mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success comment { url } } }"
# A team-key identifier such as ENG-123, or a dashed UUID.
LINEAR_ISSUE_REF_PATTERN = r"[A-Za-z][A-Za-z0-9]*-[0-9]+|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
JIRA_SITE_PATTERN = r"[A-Za-z0-9-]+\.atlassian\.net"
JIRA_DEFAULT_ISSUE_TYPE = "Task"
JIRA_ISSUE_PATH = "/rest/api/3/issue"
JIRA_BROWSE_PATH = "/browse/"
JIRA_ADF_VERSION = 1
JIRA_ISSUE_KEY_PATTERN = r"[A-Z][A-Z0-9_]+-[0-9]+"
# Jira labels cannot contain spaces.
JIRA_LABEL_PATTERN = r"\S+"
JIRA_COMMENT_PATH = "/comment"
JIRA_FOCUSED_COMMENT_QUERY = "?focusedCommentId="
NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
NOTION_API_VERSION = "2026-03-11"
NOTION_MARKDOWN_PATH = "/markdown"
NOTION_INSERT_COMMAND = "insert_content"
GITLAB_DEFAULT_HOST = "gitlab.com"
# Host labels plus an optional port with no leading zero; no scheme,
# path, or userinfo.
GITLAB_HOST_PATTERN = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*(?::[1-9][0-9]{0,4})?"
# namespace/.../name, where no segment starts with "." or "-".
GITLAB_PROJECT_PATH_PATTERN = r"[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+"
GITLAB_API_PATH = "/api/v4"
GITLAB_AUTH_HEADER = "private-token"
CONFLUENCE_PAGES_PATH = "/wiki/api/v2/pages"
CONFLUENCE_WEB_PREFIX = "/wiki"
CONFLUENCE_ID_PATTERN = r"[0-9]+"
CONFLUENCE_REPRESENTATION = "atlas_doc_format"
CONFLUENCE_PAGE_STATUS = "current"
TYPEFULLY_SOCIAL_SETS_URL = "https://api.typefully.com/v2/social-sets"
TYPEFULLY_DRAFTS_PATH = "/drafts"
TYPEFULLY_ID_PATTERN = r"[A-Za-z0-9_-]+"
HUBSPOT_TASKS_URL = "https://api.hubapi.com/crm/v3/objects/tasks"

# Job summary
GITHUB_JOB_SUMMARY_SEPARATOR = "\n\n"
# One writer thread, so two appends never interleave in the file.
GITHUB_JOB_SUMMARY_WRITERS = 1

# Rich text (Atlassian Document Format), applied with re.fullmatch
# to each line after rstrip(). A break line is checked before the
# bullet pattern, so "* * *" is never a list item.
ADF_HEADING_PATTERN = r"(#{1,6})[ \t]+(\S.*)"
ADF_BULLET_PATTERN = r"[ \t]*[-*+][ \t]+(\S.*)"
ADF_ORDERED_PATTERN = r"[ \t]*[0-9]{1,9}[.)][ \t]+(\S.*)"
ADF_BREAK_PATTERN = r"[ \t]*[-*_][-*_ \t]*"
ADF_FENCE = "```"

# Webhook signing (Standard Webhooks)
WEBHOOK_KEY_PREFIX = "whsec_"
WEBHOOK_KEY_MIN_BYTES = 24
WEBHOOK_KEY_MAX_BYTES = 64
WEBHOOK_ID_PREFIX = "msg_"
WEBHOOK_SIGNATURE_VERSION = "v1"
WEBHOOK_ID_HEADER = "webhook-id"
WEBHOOK_TIMESTAMP_HEADER = "webhook-timestamp"
WEBHOOK_SIGNATURE_HEADER = "webhook-signature"

# GitHub update in place
GITHUB_PAGE_SIZE = 100
GITHUB_FIRST_PAGE = 1
GITHUB_MAX_PAGES = 10
# "vidbyte:" plus a key is at most 50 characters, the label limit.
GITHUB_KEY_PATTERN = r"[A-Za-z0-9._-]{1,42}"
GITHUB_KEY_LABEL_PREFIX = "vidbyte:"
GITHUB_MARKER_PREFIX = "<!-- vidbyte:"
GITHUB_MARKER_REPLACEMENT = "<!-- vidbyte-quoted:"
GITHUB_MARKER_SUFFIX = " -->"

__all__ = [
    "ADF_BREAK_PATTERN",
    "ADF_BULLET_PATTERN",
    "ADF_FENCE",
    "ADF_HEADING_PATTERN",
    "ADF_ORDERED_PATTERN",
    "CONFLUENCE_BODY_MAX_CHARS",
    "CONFLUENCE_ID_PATTERN",
    "CONFLUENCE_PAGES_PATH",
    "CONFLUENCE_PAGE_STATUS",
    "CONFLUENCE_REPRESENTATION",
    "CONFLUENCE_WEB_PREFIX",
    "DISCORD_CONTENT_MAX_CHARS",
    "DISCORD_SNOWFLAKE_PATTERN",
    "DISCORD_THREAD_NAME_MAX_CHARS",
    "GITHUB_API_URL",
    "GITHUB_API_VERSION",
    "GITHUB_BODY_MAX_CHARS",
    "GITHUB_FIRST_PAGE",
    "GITHUB_JOB_SUMMARY_MAX_CHARS",
    "GITHUB_JOB_SUMMARY_SEPARATOR",
    "GITHUB_JOB_SUMMARY_WRITERS",
    "GITHUB_KEY_LABEL_PREFIX",
    "GITHUB_KEY_PATTERN",
    "GITHUB_MARKER_PREFIX",
    "GITHUB_MARKER_REPLACEMENT",
    "GITHUB_MARKER_SUFFIX",
    "GITHUB_MAX_PAGES",
    "GITHUB_PAGE_SIZE",
    "GITHUB_REPO_PATTERN",
    "GITLAB_API_PATH",
    "GITLAB_AUTH_HEADER",
    "GITLAB_DEFAULT_HOST",
    "GITLAB_DESCRIPTION_MAX_CHARS",
    "GITLAB_HOST_PATTERN",
    "GITLAB_NOTE_MAX_CHARS",
    "GITLAB_PROJECT_PATH_PATTERN",
    "GOOGLE_CHAT_MENTION_PREFIX",
    "GOOGLE_CHAT_MENTION_REPLACEMENT",
    "GOOGLE_CHAT_TEXT_MAX_CHARS",
    "HUBSPOT_TASKS_URL",
    "HUBSPOT_TASK_BODY_MAX_CHARS",
    "JIRA_ADF_VERSION",
    "JIRA_BROWSE_PATH",
    "JIRA_COMMENT_PATH",
    "JIRA_DEFAULT_ISSUE_TYPE",
    "JIRA_FOCUSED_COMMENT_QUERY",
    "JIRA_ISSUE_KEY_PATTERN",
    "JIRA_ISSUE_PATH",
    "JIRA_LABEL_PATTERN",
    "JIRA_SITE_PATTERN",
    "JIRA_TEXT_MAX_CHARS",
    "LINEAR_COMMENT_CREATE_MUTATION",
    "LINEAR_GRAPHQL_URL",
    "LINEAR_ISSUE_CREATE_MUTATION",
    "LINEAR_ISSUE_REF_PATTERN",
    "NOTION_API_VERSION",
    "NOTION_INSERT_COMMAND",
    "NOTION_MARKDOWN_PATH",
    "NOTION_MENTION_PREFIX",
    "NOTION_MENTION_REPLACEMENT",
    "NOTION_PAGES_URL",
    "OUTPUT_CREDENTIAL_ENV_VARS",
    "OUTPUT_DELIVERABLE_STOP_REASONS",
    "OUTPUT_DELIVERIES_METADATA_KEY",
    "OUTPUT_DELIVERY_DEADLINE_SECONDS",
    "OUTPUT_EMAIL_ADDRESS_PATTERN",
    "OUTPUT_ERROR_FILE",
    "OUTPUT_ERROR_HTTP_PREFIX",
    "OUTPUT_ERROR_INVALID_RESPONSE",
    "OUTPUT_ERROR_NETWORK",
    "OUTPUT_ERROR_SMTP",
    "OUTPUT_ERROR_SMTP_PREFIX",
    "OUTPUT_ERROR_SMTP_REFUSED",
    "OUTPUT_ERROR_TOKEN_MAX_CHARS",
    "OUTPUT_ERROR_TOKEN_PATTERN",
    "OUTPUT_ERROR_UNEXPECTED_PREFIX",
    "OUTPUT_FILE_ENCODING",
    "OUTPUT_HEADER_NAME_PATTERN",
    "OUTPUT_HTTPS_PREFIX",
    "OUTPUT_HTTP_SUCCESS_MAX",
    "OUTPUT_HTTP_SUCCESS_MIN",
    "OUTPUT_JSON_CONTENT_TYPE",
    "OUTPUT_MAX_READ_BYTES",
    "OUTPUT_MAX_RESPONSE_BYTES",
    "OUTPUT_RATE_LIMIT_RETRIES",
    "OUTPUT_RETRY_STATUS_CODES",
    "OUTPUT_TIMEOUT_SECONDS",
    "OUTPUT_TITLE_MAX_CHARS",
    "OUTPUT_TRUNCATION_MARKER",
    "SLACK_BROADCAST_PREFIX",
    "SLACK_BROADCAST_REPLACEMENT",
    "SLACK_MARKDOWN_MAX_CHARS",
    "SLACK_TEXT_MAX_CHARS",
    "SLACK_USER_MENTION_PREFIX",
    "SLACK_USER_MENTION_REPLACEMENT",
    "SMTP_IMPLICIT_TLS_PORT",
    "SMTP_PORT_MAX",
    "SMTP_PORT_MIN",
    "SMTP_STARTTLS_PORT",
    "TEAMS_ADAPTIVE_CARD_VERSION",
    "TEAMS_CARD_WIDTH",
    "TEAMS_TEXT_MAX_CHARS",
    "TEAMS_TITLE_SIZE",
    "TEAMS_TITLE_WEIGHT",
    "TELEGRAM_API_URL",
    "TELEGRAM_MEDIA_PREFIX",
    "TELEGRAM_MEDIA_REPLACEMENT",
    "TELEGRAM_RICH_METHOD",
    "TELEGRAM_RICH_TEXT_MAX_CHARS",
    "TELEGRAM_TAG_PREFIX",
    "TELEGRAM_TAG_REPLACEMENT",
    "TYPEFULLY_DRAFTS_PATH",
    "TYPEFULLY_ID_PATTERN",
    "TYPEFULLY_SOCIAL_SETS_URL",
    "WEBHOOK_ID_HEADER",
    "WEBHOOK_ID_PREFIX",
    "WEBHOOK_KEY_MAX_BYTES",
    "WEBHOOK_KEY_MIN_BYTES",
    "WEBHOOK_KEY_PREFIX",
    "WEBHOOK_SIGNATURE_HEADER",
    "WEBHOOK_SIGNATURE_VERSION",
    "WEBHOOK_TIMESTAMP_HEADER",
]
