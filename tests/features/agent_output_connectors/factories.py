"""FILE: tests/features/agent_output_connectors/factories.py

PURPOSE: Domain-shaped test data and offline fakes for the agent-output-connectors pack: placeholder credentials, the eleven-destination table, a scripted HTTP destination, a scripted SMTP server, scripted model turns, a caller-written connector, and reply and receipt helpers.
ROLE IN CODEBASE: Imported by conftest.py (which turns these into fixtures) and by the pack's test modules as tests.features.agent_output_connectors.factories; builds on vidbyte.lib.http.transport.HttpResponse and the AgentMessage record.
ARCHITECTURE NOTE: Nothing here imports a feature module at module level; ScriptedConnector imports the receipt record lazily, so a missing feature fails each test instead of aborting collection. The HTTP fake JSON-encodes each body exactly as the real _send_once does, so a body that cannot reach the wire fails here too.
FUNCTION INVENTORY: ConnectorCase.build / build_without_credential construct one destination; CONNECTOR_CASES maps each OutputDestination value to its case; HttpScript.answer / respond / sends_to script and record HTTP attempts; HttpxRequests.handle records and answers requests that reach an httpx.MockTransport; SmtpScript.fail / hold / check / answer_quit script SMTP failures, a stalled step, and the QUIT reply, with ScriptedSmtp and ScriptedSmtpSsl mirroring smtplib's constructors, __exit__, and quit; AnswerRunner replays isDone turns (optionally repeating the last one); ScriptedConnector is a structural OutputConnector whose send can return any value; build_reply builds a finished AgentMessage; receipt_rows flattens receipts.
COMMON MODIFICATION PATTERNS: Add a destination by adding one ConnectorCase row and its key to HTTP_DESTINATION_KEYS; keep wire expectations in the test module that asserts them, not here.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub or re-implement OutputDispatcher, OutputShaping, OutputText, OutputArguments, a connector, or a record. 2. Do not open sockets or read real credentials. 3. Do not import this module as a bare `factories`; always use the dotted path so there is one module object.
KNOWN EDGE CASES: Every placeholder credential contains SECRET_MARKER, so one substring scan finds any leaked fragment. Response queues do not repeat unless asked, so an unexpected retry fails loudly. The SMTP fakes mirror the real constructor signatures, so passing context= to plain SMTP fails as it would in production; like smtplib, the fake __exit__ raises SMTPResponseException when QUIT is not answered 221, while quit() returns the reply. A held SMTP step gives up after HOLD_SAFETY_SECONDS, so a run that waits for the worker thread fails slowly instead of hanging. Telegram's wire secret is the token inside the URL path; Jira's is the Basic header built from email and token.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§9.2, §9.3, §13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import smtplib
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from types import ModuleType
from typing import Any

import httpx

from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http.transport import HttpResponse

# Every placeholder credential carries this marker, so one substring scan finds any leaked fragment.
SECRET_MARKER = "S3CRET"

SLACK_URL = "https://hooks.slack.com/services/T000/B000/S3CRETslack"
DISCORD_URL = "https://discord.com/api/webhooks/000/S3CRETdiscord"
TEAMS_URL = "https://default000.environment.api.powerplatform.com/powerautomate/automations/direct/workflows/000/triggers/manual/paths/invoke?api-version=1&sig=S3CRETteams"
GOOGLE_CHAT_URL = "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=S3CRETkey&token=S3CRETtoken"
TELEGRAM_TOKEN = "123456:S3CRETtelegram"
GITHUB_TOKEN = "ghp_S3CRETgithub"
LINEAR_KEY = "lin_api_S3CRETlinear"
JIRA_TOKEN = "S3CRETjira"
NOTION_KEY = "ntn_S3CRETnotion"
WEBHOOK_URL = "https://hook.eu1.make.com/S3CRETwebhook"
SMTP_PASSWORD = "S3CRETsmtp"

LINEAR_TEAM_ID = "9cfb482a-81e3-4154-b5b9-2c805e70a02d"
NOTION_PARENT_PAGE_ID = "1f2e3d4c-5b6a-4789-8abc-def012345678"
TELEGRAM_CHAT_ID = -1001234567890
GITHUB_ISSUE_URL = "https://github.com/acme/shop/issues/412"
GITHUB_CREATED = json.dumps({"number": 412, "html_url": GITHUB_ISSUE_URL})
LINEAR_ISSUE_URL = "https://linear.app/acme/issue/ENG-7/checkout-total-ignores-coupons"
JIRA_BASIC = "Basic " + base64.b64encode(f"bot@acme.com:{JIRA_TOKEN}".encode()).decode()
NOTION_PAGE_URL = "https://www.notion.so/Checkout-total-ignores-coupons-1f2e3d4c"

# The §9.3 variables, literally: these names are part of the user-facing contract.
OUTPUT_ENV_VARS = (
    "SLACK_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
    "TEAMS_WEBHOOK_URL",
    "GOOGLE_CHAT_WEBHOOK_URL",
    "TELEGRAM_BOT_TOKEN",
    "SMTP_PASSWORD",
    "GITHUB_TOKEN",
    "LINEAR_API_KEY",
    "JIRA_API_TOKEN",
    "NOTION_API_KEY",
    "VIDBYTE_OUTPUT_WEBHOOK_URL",
)


@dataclass(frozen=True)
class ConnectorCase:
    """One destination: how to build it, where its credential lives, and its documented success response."""

    key: str
    class_name: str
    parameter: str
    env_var: str
    credential: str
    options: Mapping[str, object]
    host: str
    success: tuple[int, str]
    # The credential as it must appear on the wire: in the URL, or as a header value.
    wire_secret: str

    def build(self, api: ModuleType, **overrides: object) -> Any:
        # Builds the connector with its credential passed explicitly.
        return getattr(api, self.class_name)(**{**self.options, self.parameter: self.credential, **overrides})

    def build_without_credential(self, api: ModuleType) -> Any:
        # Builds the connector from addressing arguments only, so the credential must come from the environment.
        return getattr(api, self.class_name)(**self.options)


CONNECTOR_CASES: dict[str, ConnectorCase] = {
    "slack": ConnectorCase("slack", "SlackOutput", "webhook_url", "SLACK_WEBHOOK_URL", SLACK_URL, {}, "hooks.slack.com", (200, "ok"), SLACK_URL),
    "discord": ConnectorCase("discord", "DiscordOutput", "webhook_url", "DISCORD_WEBHOOK_URL", DISCORD_URL, {}, "discord.com", (204, ""), DISCORD_URL),
    "teams": ConnectorCase("teams", "TeamsOutput", "webhook_url", "TEAMS_WEBHOOK_URL", TEAMS_URL, {}, "powerplatform.com", (202, ""), TEAMS_URL),
    "google_chat": ConnectorCase("google_chat", "GoogleChatOutput", "webhook_url", "GOOGLE_CHAT_WEBHOOK_URL", GOOGLE_CHAT_URL, {}, "chat.googleapis.com", (200, json.dumps({"name": "spaces/AAAA/messages/BBBB"})), GOOGLE_CHAT_URL),
    "telegram": ConnectorCase("telegram", "TelegramOutput", "bot_token", "TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN, {"chat_id": TELEGRAM_CHAT_ID}, "api.telegram.org", (200, json.dumps({"ok": True, "result": {"message_id": 7}})), f"/bot{TELEGRAM_TOKEN}/"),
    "github_issue": ConnectorCase("github_issue", "GitHubIssueOutput", "token", "GITHUB_TOKEN", GITHUB_TOKEN, {"repo": "acme/shop", "labels": ("bug",)}, "api.github.com", (201, GITHUB_CREATED), f"Bearer {GITHUB_TOKEN}"),
    "linear_issue": ConnectorCase("linear_issue", "LinearIssueOutput", "api_key", "LINEAR_API_KEY", LINEAR_KEY, {"team_id": LINEAR_TEAM_ID}, "api.linear.app", (200, json.dumps({"data": {"issueCreate": {"success": True, "issue": {"url": LINEAR_ISSUE_URL}}}})), LINEAR_KEY),
    "jira_issue": ConnectorCase("jira_issue", "JiraIssueOutput", "api_token", "JIRA_API_TOKEN", JIRA_TOKEN, {"site": "acme.atlassian.net", "project": "PROJ", "email": "bot@acme.com"}, "acme.atlassian.net", (201, json.dumps({"id": "10001", "key": "PROJ-1", "self": "https://acme.atlassian.net/rest/api/3/issue/10001"})), JIRA_BASIC),
    "notion_page": ConnectorCase("notion_page", "NotionPageOutput", "api_key", "NOTION_API_KEY", NOTION_KEY, {"parent_page_id": NOTION_PARENT_PAGE_ID}, "api.notion.com", (200, json.dumps({"object": "page", "url": NOTION_PAGE_URL})), f"Bearer {NOTION_KEY}"),
    "webhook": ConnectorCase("webhook", "WebhookOutput", "url", "VIDBYTE_OUTPUT_WEBHOOK_URL", WEBHOOK_URL, {}, "hook.eu1.make.com", (200, "Accepted"), WEBHOOK_URL),
    "email": ConnectorCase("email", "EmailOutput", "password", "SMTP_PASSWORD", SMTP_PASSWORD, {"to": "ops@acme.com", "host": "smtp.gmail.com", "username": "bot@acme.com"}, "smtp.gmail.com", (250, "OK"), SMTP_PASSWORD),
}
HTTP_DESTINATION_KEYS = ("slack", "discord", "teams", "google_chat", "telegram", "github_issue", "linear_issue", "jira_issue", "notion_page", "webhook")
ALL_DESTINATION_KEYS = (*HTTP_DESTINATION_KEYS, "email")


class HttpScript:
    """Scripted destinations: answers each attempt from a per-URL queue and records what went on the wire."""

    # A response that never arrives; only a deadline can end the wait.
    HANG = "__hang__"

    def __init__(self) -> None:
        self.sends: list[dict[str, Any]] = []
        self._routes: list[tuple[str, list[object], bool]] = []

    def answer(self, url_fragment: str, *responses: object, repeat: bool = False) -> None:
        # Queues responses for requests whose URL contains url_fragment: (status, body), an exception to raise, or HANG.
        self._routes.append((url_fragment, list(responses), repeat))

    def sends_to(self, url_fragment: str) -> list[dict[str, Any]]:
        # Returns the recorded attempts whose URL contains url_fragment, in send order.
        return [send for send in self.sends if url_fragment in send["url"]]

    async def respond(self, kwargs: Mapping[str, Any]) -> HttpResponse:
        # Encodes the body as the real send would, records the attempt, then plays the next scripted response.
        json_body = kwargs.get("json_body")
        wire_body = None if json_body is None else json.loads(json.dumps(json_body))
        self.sends.append({**kwargs, "headers": dict(kwargs["headers"]), "json_body": wire_body})
        # The first route for this URL that still has a response answers; an exhausted route never repeats.
        route = next((route for route in self._routes if route[0] in kwargs["url"] and route[1]), None)
        if route is None:
            raise AssertionError(f"no scripted response left for request #{len(self.sends)}")
        item = route[1][0] if route[2] else route[1].pop(0)
        if item == self.HANG:
            await asyncio.Event().wait()
        if isinstance(item, BaseException):
            raise item
        status, body = item
        return HttpResponse(status_code=status, body=body, headers={})


class HttpxRequests(list):
    """Requests that reached an in-memory httpx.MockTransport, plus the response scripted for each host."""

    def __init__(self) -> None:
        super().__init__()
        self.routes: dict[str, httpx.Response] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        # Records the request, then answers with its host's scripted response, or 599 for a host no test expected.
        self.append(request)
        return self.routes.get(request.url.host, httpx.Response(599, text="unexpected host"))


@dataclass
class SmtpSession:
    """What one scripted SMTP connection saw, in order."""

    implicit_tls: bool
    host: str
    port: int
    timeout: object
    context: object
    thread_id: int
    steps: list[str] = field(default_factory=list)
    starttls_context: object = None
    login: tuple[str, str] | None = None
    message: EmailMessage | None = None


class SmtpScript:
    """A scripted SMTP server: records each connection, fails or stalls at the step a test names, and answers QUIT as told."""

    # How long a held step waits for its gate; a backstop so a broken implementation fails the test instead of hanging it.
    HOLD_SAFETY_SECONDS = 10.0

    def __init__(self) -> None:
        self.sessions: list[SmtpSession] = []
        self.refused: dict[str, tuple[int, bytes]] = {}
        # The reply to QUIT: a (code, text) pair, or an exception such as SMTPServerDisconnected for a dropped connection.
        self.quit_reply: tuple[int, bytes] | BaseException = (221, b"2.0.0 closing connection")
        # Set once a held step stops waiting, whether the test opened the gate or the backstop ran out.
        self.released = threading.Event()
        self._fail_on: str | None = None
        self._failure: BaseException | None = None
        self._hold_on: str | None = None
        self._gate = threading.Event()

    def fail(self, step: str, error: BaseException) -> None:
        # Makes the named step ("connect", "starttls", "login", "send_message") raise error.
        self._fail_on, self._failure = step, error

    def hold(self, step: str) -> threading.Event:
        # Makes the named step block its worker thread until the test sets the returned gate: a server that stalls mid-session.
        self._hold_on = step
        return self._gate

    def check(self, step: str) -> None:
        # Stalls at a held step, then raises the scripted failure when this step is the one a test chose.
        if self._hold_on == step:
            self._gate.wait(self.HOLD_SAFETY_SECONDS)
            self.released.set()
        if self._fail_on == step and self._failure is not None:
            raise self._failure

    def answer_quit(self) -> tuple[int, bytes]:
        # Plays the scripted QUIT reply: returns it, or raises it when it is an exception.
        if isinstance(self.quit_reply, BaseException):
            raise self.quit_reply
        return self.quit_reply


UNSET_TIMEOUT = object()


class ScriptedSmtp:
    """Stands in for smtplib.SMTP with the same constructor signature; the fixture binds `script` on a subclass."""

    script: SmtpScript
    implicit_tls = False

    def __init__(self, host: str = "", port: int = 0, local_hostname: str | None = None, timeout: object = UNSET_TIMEOUT, source_address: object = None) -> None:
        self._open(host, port, timeout, None)

    def _open(self, host: str, port: int, timeout: object, context: object) -> None:
        # Records the connection and the thread it runs on, then fails if the test scripted a connect failure.
        self.session = SmtpSession(self.implicit_tls, host, port, timeout, context, threading.get_ident())
        self.script.sessions.append(self.session)
        self.script.check("connect")

    def __enter__(self) -> ScriptedSmtp:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        # Mirrors smtplib.SMTP.__exit__: send QUIT, raise SMTPResponseException on any reply but 221, ignore a dropped connection, always close.
        try:
            code, text = self._quit()
            if code != 221:
                raise smtplib.SMTPResponseException(code, text)
        except smtplib.SMTPServerDisconnected:
            pass
        finally:
            self.session.steps.append("close")
        return False

    def ehlo(self, name: str = "") -> tuple[int, bytes]:
        return 250, b"smtp.example ready"

    def ehlo_or_helo_if_needed(self) -> None:
        return None

    def has_extn(self, name: str) -> bool:
        return True

    def starttls(self, keyfile: object = None, certfile: object = None, context: object = None) -> tuple[int, bytes]:
        self.session.steps.append("starttls")
        self.session.starttls_context = context
        self.script.check("starttls")
        return 220, b"ready to start TLS"

    def login(self, user: str, password: str, *, initial_response_ok: bool = True) -> tuple[int, bytes]:
        self.session.steps.append("login")
        self.session.login = (user, password)
        self.script.check("login")
        return 235, b"accepted"

    def send_message(self, msg: EmailMessage, from_addr: str | None = None, to_addrs: object = None, mail_options: Sequence[str] = (), rcpt_options: Sequence[str] = ()) -> dict[str, tuple[int, bytes]]:
        self.session.steps.append("send_message")
        self.session.message = msg
        self.script.check("send_message")
        return dict(self.script.refused)

    def quit(self) -> tuple[int, bytes]:
        # Mirrors smtplib.SMTP.quit: send QUIT, return the reply whatever its code, then close; a dropped connection raises.
        try:
            return self._quit()
        finally:
            self.session.steps.append("close")

    def _quit(self) -> tuple[int, bytes]:
        self.session.steps.append("quit")
        return self.script.answer_quit()

    def close(self) -> None:
        self.session.steps.append("close")


class ScriptedSmtpSsl(ScriptedSmtp):
    """Stands in for smtplib.SMTP_SSL: timeout and context are keyword-only, as in the real class."""

    implicit_tls = True

    def __init__(self, host: str = "", port: int = 0, local_hostname: str | None = None, *, timeout: object = UNSET_TIMEOUT, source_address: object = None, context: object = None) -> None:
        self._open(host, port, timeout, context)


class ScriptedResponse:
    """A Responses-shape model turn with priced usage, as JevAgent's usage ledger requires."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = ""
        self.raw = raw
        self.provider = ModelProvider.OPENAI
        self.model = "gpt-5.4-mini"
        self.usage = {"input_tokens": 100, "output_tokens": 20}


class AnswerRunner:
    """Offline model stand-in: each run finishes at once with the next scripted final answer via isDone."""

    def __init__(self, *answers: str, repeat_last: bool = False) -> None:
        # repeat_last keeps answering with the final answer, for runs that re-prompt the model (an output-schema repair).
        self._answers = list(answers)
        self._repeat_last = repeat_last
        self.calls = 0

    def run(self, prompt: str, **kwargs: Any) -> ScriptedResponse:
        self.calls += 1
        answer = self._answers[0] if self._repeat_last and len(self._answers) == 1 else self._answers.pop(0)
        call = {"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": answer}), "call_id": f"done_{self.calls}"}
        return ScriptedResponse({"output": [call]})


class ScriptedConnector:
    """A caller-written connector: satisfies OutputConnector structurally (no BaseOutput) and records each send."""

    # Default for `result`: send reports a SENT receipt for its own destination.
    SENT = object()

    def __init__(self, destination: Any, *, render: Callable[[AgentMessage], object] | None = None, error: BaseException | None = None, wait_for: asyncio.Event | None = None, signal: asyncio.Event | None = None, finished: list[str] | None = None, result: object = SENT) -> None:
        # result replaces the SENT receipt with any value, such as None from a send that forgot to return its receipt.
        self.destination = destination
        self._render = render
        self._error = error
        self._wait_for = wait_for
        self._signal = signal
        self._finished = finished
        self._result = result
        self.contents: list[object] = []

    @property
    def render(self) -> Callable[[AgentMessage], object] | None:
        return self._render

    async def send(self, reply: AgentMessage, content: object) -> object:
        # Waits for its gate, fails if told to, signals its partner, records that it finished, then reports SENT.
        self.contents.append(content)
        if self._wait_for is not None:
            await self._wait_for.wait()
        if self._error is not None:
            raise self._error
        if self._signal is not None:
            self._signal.set()
        if self._finished is not None:
            self._finished.append(self.destination.value)
        if self._result is not self.SENT:
            return self._result
        records = importlib.import_module("vidbyte.lib.dataclasses.outputs")
        enums = importlib.import_module("vidbyte.lib.enums.outputs")
        return records.DeliveryReceipt(destination=self.destination, status=enums.DeliveryStatus.SENT)


def build_reply(content: str, *, sender: str = "checkout-scout", stop_reason: str | None = "final_response", structured: object = None) -> AgentMessage:
    # A finished reply as BaseAgent builds it; stop_reason=None leaves the key out, as JevAgent's clarification stop does.
    metadata: dict[str, Any] = {} if stop_reason is None else {"stop_reason": stop_reason}
    return AgentMessage(sender=sender, recipient="orchestrator", content=content, metadata=metadata, structured=structured)


def receipt_rows(receipts: Sequence[Any]) -> list[tuple[object, ...]]:
    # Flattens receipts into (destination, status, url, error_code) rows that read well in a failed assertion.
    return [(receipt.destination.value, receipt.status.value, receipt.url, receipt.error_code) for receipt in receipts]
