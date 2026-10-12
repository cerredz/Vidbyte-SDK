"""FILE: vidbyte/lib/outputs/delivery.py

PURPOSE: Defines OutputHttp and OutputSmtp, which send one connector request and map the outcome to a DeliveryReceipt.
ROLE IN CODEBASE: Called by every connector's send in this package; HTTP goes through vidbyte/lib/http/transport.py, email through stdlib smtplib.
ARCHITECTURE NOTE: The only place delivery outcomes become error codes, so the INV-11 code grammar and the retry policy live in one module.
COMMON MODIFICATION PATTERNS: A new HTTP connector builds an OutputRequest and calls OutputHttp.post; it never calls HttpTransport itself.
KNOWN EDGE CASES: A 2xx without a usable https link is FAILED invalid_response; a partial SMTP refusal is FAILED, since a retry would duplicate the mail.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_http_failures.py and test_output_connectors_email.py
"""

from __future__ import annotations

import json
import logging
import re
import smtplib
import ssl
from collections.abc import Mapping
from contextvars import ContextVar
from email.message import EmailMessage
from uuid import uuid4

from vidbyte.lib.constants.outputs import (
    OUTPUT_ERROR_HTTP_PREFIX,
    OUTPUT_ERROR_INVALID_RESPONSE,
    OUTPUT_ERROR_NETWORK,
    OUTPUT_ERROR_SMTP,
    OUTPUT_ERROR_SMTP_PREFIX,
    OUTPUT_ERROR_SMTP_REFUSED,
    OUTPUT_ERROR_TOKEN_PATTERN,
    OUTPUT_HTTP_SUCCESS_MAX,
    OUTPUT_HTTP_SUCCESS_MIN,
    OUTPUT_MAX_RESPONSE_BYTES,
    OUTPUT_RATE_LIMIT_RETRIES,
    OUTPUT_RETRY_STATUS_CODES,
    OUTPUT_TIMEOUT_SECONDS,
    SMTP_IMPLICIT_TLS_PORT,
)
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputRequest, SmtpSettings
from vidbyte.lib.enums.outputs import DeliveryStatus, OutputDestination
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

# True only inside OutputHttp.post, so the httpx log filter below hides
# that send's request line and leaves every other request's line alone.
_OUTPUT_POST_ACTIVE: ContextVar[bool] = ContextVar("vidbyte_output_post_active", default=False)


class OutputHttp:
    """Sends one connector's HTTPS JSON request and maps the response to a receipt."""

    @staticmethod
    async def post(destination: OutputDestination, request: OutputRequest) -> DeliveryReceipt:
        """POST the request once (plus 429 retries) and return its receipt."""
        # @intent output-post-retries-only-rate-limits
        # Only a 429 is retried: the destination did not process it, so
        # a retry cannot post a reply twice. Redirects are refused, so a
        # credential header never reaches a second host.
        # Mark the send so httpx's request log line, whose URL can be
        # the credential, is dropped for this send only.
        active = _OUTPUT_POST_ACTIVE.set(True)
        try:
            response = await HttpTransport().request(
                method="POST",
                url=request.url,
                headers=request.headers,
                json_body=request.json_body,
                timeout_seconds=OUTPUT_TIMEOUT_SECONDS,
                retry_count=OUTPUT_RATE_LIMIT_RETRIES,
                retry_status_codes=OUTPUT_RETRY_STATUS_CODES,
                max_response_bytes=OUTPUT_MAX_RESPONSE_BYTES,
                idempotency_key=uuid4().hex,
                follow_redirects=False,
            )
        except ProviderRequestError:
            # No answer arrived, or the answer was too big.
            return DeliveryReceipt(destination, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_NETWORK)
        finally:
            _OUTPUT_POST_ACTIVE.reset(active)
        # Any status outside 2xx is a failure the destination reported.
        if not OUTPUT_HTTP_SUCCESS_MIN <= response.status_code <= OUTPUT_HTTP_SUCCESS_MAX:
            return DeliveryReceipt(destination, DeliveryStatus.FAILED, error_code=OutputHttp._error_code(response))
        # Chat and webhook destinations return no link to report.
        if not request.link_path:
            return DeliveryReceipt(destination, DeliveryStatus.SENT)
        # A created issue or page must come back with its https link.
        link = OutputHttp._link(response, request)
        if link is None:
            return DeliveryReceipt(destination, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_INVALID_RESPONSE)
        return DeliveryReceipt(destination, DeliveryStatus.SENT, url=link)

    @staticmethod
    def _error_code(response: HttpResponse) -> str:
        # The status, plus the body when the whole body is one error
        # word (Slack's "no_service"); other text is never kept.
        code = f"{OUTPUT_ERROR_HTTP_PREFIX}{response.status_code}"
        token = response.body.strip()
        if re.fullmatch(OUTPUT_ERROR_TOKEN_PATTERN, token):
            return f"{code}:{token}"
        return code

    @staticmethod
    def _link(response: HttpResponse, request: OutputRequest) -> str | None:
        # @intent created-object-link-is-https
        # Linear can answer 200 with errors[] and no issue, so a 2xx
        # counts only with a link. The prefix is added before the https
        # check, because Jira returns a bare key such as PROJ-123.
        try:
            node: object = json.loads(response.body)
        except ValueError:
            return None
        for key in request.link_path:
            node = node.get(key) if isinstance(node, Mapping) else None
        if not (isinstance(node, str) and node.strip()):
            return None
        link = request.link_prefix + node
        return link if link.startswith("https://") else None

    @staticmethod
    def _keep_log_record(record: logging.LogRecord) -> bool:
        # @intent output-request-log-hides-the-url
        # httpx logs every request's full URL at INFO, and for Slack,
        # Discord, Teams, Google Chat, Telegram, and webhooks that URL
        # is the credential. Only lines from an output send are dropped,
        # so the caller's own httpx requests still log.
        return not (_OUTPUT_POST_ACTIVE.get() and record.getMessage().startswith("HTTP Request:"))


class OutputSmtp:
    """Sends one email over verified TLS and maps the outcome to a receipt."""

    @staticmethod
    def send(settings: SmtpSettings, message: EmailMessage) -> DeliveryReceipt:
        """Blocking: run it with asyncio.to_thread. One session, never retried."""
        # @intent smtp-is-one-verified-tls-attempt
        # The session always runs over verified TLS and never falls back
        # to plain text. A failure is never retried, because the server
        # may already have accepted the mail for some recipients.
        try:
            # Connect, upgrade to TLS unless implicit, sign in, send.
            with OutputSmtp._client(settings) as client:
                if settings.port != SMTP_IMPLICIT_TLS_PORT:
                    client.starttls(context=ssl.create_default_context())
                client.login(settings.username, settings.password)
                refused = client.send_message(message)
        except smtplib.SMTPRecipientsRefused:
            return DeliveryReceipt(OutputDestination.EMAIL, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_SMTP_REFUSED)
        except smtplib.SMTPResponseException as exc:
            return DeliveryReceipt(OutputDestination.EMAIL, DeliveryStatus.FAILED, error_code=f"{OUTPUT_ERROR_SMTP_PREFIX}{exc.smtp_code}")
        except smtplib.SMTPException:
            return DeliveryReceipt(OutputDestination.EMAIL, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_SMTP)
        except OSError:
            # Unknown host, refused connection, timeout, bad cert.
            return DeliveryReceipt(OutputDestination.EMAIL, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_NETWORK)
        # Some recipients refused; the rest got it, so it still failed.
        if refused:
            return DeliveryReceipt(OutputDestination.EMAIL, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_SMTP_REFUSED)
        return DeliveryReceipt(OutputDestination.EMAIL, DeliveryStatus.SENT)

    @staticmethod
    def _client(settings: SmtpSettings) -> smtplib.SMTP:
        # Port 465 is TLS from the first byte; other ports use STARTTLS.
        if settings.port == SMTP_IMPLICIT_TLS_PORT:
            return smtplib.SMTP_SSL(settings.host, settings.port, timeout=OUTPUT_TIMEOUT_SECONDS, context=ssl.create_default_context())
        return smtplib.SMTP(settings.host, settings.port, timeout=OUTPUT_TIMEOUT_SECONDS)


# Registered once, at import; the logger is found by name, so this
# module never imports httpx.
logging.getLogger("httpx").addFilter(OutputHttp._keep_log_record)

__all__ = ["OutputHttp", "OutputSmtp"]
