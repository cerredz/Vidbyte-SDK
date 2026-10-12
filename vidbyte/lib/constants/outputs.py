"""FILE: vidbyte/lib/constants/outputs.py

PURPOSE: Defines the named limits, error codes, endpoints, and credential variables used to deliver agent replies.
ROLE IN CODEBASE: Read by the output records, the provider connectors in vidbyte/lib/outputs/, and the dispatcher in vidbyte/agents/output/.
ARCHITECTURE NOTE: This module contains immutable constants only; delivery behavior lives in the connectors and the dispatcher.
COMMON MODIFICATION PATTERNS: Add a named constant here before introducing another delivery limit, version, or endpoint literal.
KNOWN EDGE CASES: The delivery deadline must stay above three request timeouts plus the 429 backoff, or a rate-limited send is cut short.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_contract.py
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
    }
)

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
TELEGRAM_TEXT_MAX_CHARS = 4_096
GITHUB_BODY_MAX_CHARS = 65_536
JIRA_TEXT_MAX_CHARS = 32_767

# Mentions
GOOGLE_CHAT_MENTION_PREFIX = "<users/"
GOOGLE_CHAT_MENTION_REPLACEMENT = "＜users/"
NOTION_MENTION_PREFIX = "<mention-"
NOTION_MENTION_REPLACEMENT = "＜mention-"

# Endpoints and versions
TEAMS_ADAPTIVE_CARD_VERSION = "1.2"
TELEGRAM_API_URL = "https://api.telegram.org"
GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
GITHUB_REPO_PATTERN = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_ISSUE_CREATE_MUTATION = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { url } } }"
JIRA_SITE_PATTERN = r"[A-Za-z0-9-]+\.atlassian\.net"
JIRA_DEFAULT_ISSUE_TYPE = "Task"
JIRA_ADF_VERSION = 1
NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
NOTION_API_VERSION = "2026-03-11"

__all__ = [
    "DISCORD_CONTENT_MAX_CHARS",
    "GITHUB_API_URL",
    "GITHUB_API_VERSION",
    "GITHUB_BODY_MAX_CHARS",
    "GITHUB_REPO_PATTERN",
    "GOOGLE_CHAT_MENTION_PREFIX",
    "GOOGLE_CHAT_MENTION_REPLACEMENT",
    "GOOGLE_CHAT_TEXT_MAX_CHARS",
    "JIRA_ADF_VERSION",
    "JIRA_DEFAULT_ISSUE_TYPE",
    "JIRA_SITE_PATTERN",
    "JIRA_TEXT_MAX_CHARS",
    "LINEAR_GRAPHQL_URL",
    "LINEAR_ISSUE_CREATE_MUTATION",
    "NOTION_API_VERSION",
    "NOTION_MENTION_PREFIX",
    "NOTION_MENTION_REPLACEMENT",
    "NOTION_PAGES_URL",
    "OUTPUT_CREDENTIAL_ENV_VARS",
    "OUTPUT_DELIVERABLE_STOP_REASONS",
    "OUTPUT_DELIVERIES_METADATA_KEY",
    "OUTPUT_DELIVERY_DEADLINE_SECONDS",
    "OUTPUT_ERROR_HTTP_PREFIX",
    "OUTPUT_ERROR_INVALID_RESPONSE",
    "OUTPUT_ERROR_NETWORK",
    "OUTPUT_ERROR_SMTP",
    "OUTPUT_ERROR_SMTP_PREFIX",
    "OUTPUT_ERROR_SMTP_REFUSED",
    "OUTPUT_ERROR_TOKEN_MAX_CHARS",
    "OUTPUT_ERROR_TOKEN_PATTERN",
    "OUTPUT_ERROR_UNEXPECTED_PREFIX",
    "OUTPUT_HTTP_SUCCESS_MAX",
    "OUTPUT_HTTP_SUCCESS_MIN",
    "OUTPUT_MAX_RESPONSE_BYTES",
    "OUTPUT_RATE_LIMIT_RETRIES",
    "OUTPUT_RETRY_STATUS_CODES",
    "OUTPUT_TIMEOUT_SECONDS",
    "OUTPUT_TITLE_MAX_CHARS",
    "OUTPUT_TRUNCATION_MARKER",
    "SLACK_TEXT_MAX_CHARS",
    "SMTP_IMPLICIT_TLS_PORT",
    "SMTP_PORT_MAX",
    "SMTP_PORT_MIN",
    "SMTP_STARTTLS_PORT",
    "TEAMS_ADAPTIVE_CARD_VERSION",
    "TEAMS_TEXT_MAX_CHARS",
    "TELEGRAM_API_URL",
    "TELEGRAM_TEXT_MAX_CHARS",
]
