"""FILE: vidbyte/lib/dataclasses/outputs.py

PURPOSE: Defines the validated records that carry a reply's content, one delivery's outcome, one HTTP request, the result of one HTTP read, and one SMTP session.
ROLE IN CODEBASE: Built by the dispatcher in vidbyte/agents/output/ and the connectors in vidbyte/lib/outputs/; read by OutputDeliveryError.
ARCHITECTURE NOTE: Frozen, slotted records that check themselves in __post_init__; sending and shaping live in the layers that use them.
COMMON MODIFICATION PATTERNS: Add a field here with its check, then fill it in the connector or dispatcher that builds the record.
KNOWN EDGE CASES: Secret-bearing fields are repr=False and their errors never echo the value.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_contract.py
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from vidbyte.lib.constants.outputs import (
    OUTPUT_EMAIL_ADDRESS_PATTERN,
    OUTPUT_HTTPS_PREFIX,
    SMTP_PORT_MAX,
    SMTP_PORT_MIN,
)
from vidbyte.lib.enums.outputs import DeliveryStatus, OutputDestination
from vidbyte.lib.errors import ConfigurationError


def _require(condition: bool, field_name: str, message: str) -> None:
    # Raise the record's error, naming the offending field.
    if not condition:
        raise ConfigurationError(f"{field_name} {message}", details={"field": field_name})


def _is_text(value: object) -> bool:
    # Usable text is a string that is not only whitespace.
    return isinstance(value, str) and bool(value.strip())


def _is_address(value: object) -> bool:
    # One address: has an "@", and no whitespace, line break, or comma.
    return isinstance(value, str) and re.fullmatch(OUTPUT_EMAIL_ADDRESS_PATTERN, value) is not None


@dataclass(frozen=True, slots=True)
class OutputContent:
    """The title and body one connector delivers for one reply."""

    title: str
    body: str

    def __post_init__(self) -> None:
        _require(_is_text(self.title), "title", f"must be a non-blank string, got {self.title!r}.")
        _require(_is_text(self.body), "body", f"must be a non-blank string, got {self.body!r}.")


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """The final outcome of delivering one reply to one connector."""

    destination: OutputDestination
    status: DeliveryStatus
    url: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        _require(isinstance(self.destination, OutputDestination), "destination", f"must be an OutputDestination, got {self.destination!r}.")
        _require(isinstance(self.status, DeliveryStatus), "status", f"must be a DeliveryStatus, got {self.status!r}.")
        failed = self.status is DeliveryStatus.FAILED
        _require(_is_text(self.error_code) if failed else self.error_code is None, "error_code", f"must be set exactly when the status is failed, got {self.error_code!r}.")
        url_allowed = self.status is DeliveryStatus.SENT and isinstance(self.url, str) and self.url.startswith(OUTPUT_HTTPS_PREFIX)
        _require(self.url is None or url_allowed, "url", "must be None, or an https:// link on a sent receipt.")


@dataclass(frozen=True, slots=True)
class OutputRequest:
    """One HTTPS request to a destination, with a JSON body, exact bytes, or no body; the URL and headers can carry the credential."""

    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    json_body: Mapping[str, object] | None = field(repr=False)
    link_path: tuple[str, ...] = ()
    link_prefix: str = ""
    content: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _require(isinstance(self.url, str) and self.url.startswith(OUTPUT_HTTPS_PREFIX), "url", "must start with https://.")
        valid_headers = isinstance(self.headers, Mapping) and all(isinstance(key, str) and key == key.lower() and isinstance(value, str) for key, value in self.headers.items())
        _require(valid_headers, "headers", "must map lowercase string names to string values.")
        _require(self.json_body is None or isinstance(self.json_body, Mapping), "json_body", "must be a mapping or None.")
        _require(self.content is None or isinstance(self.content, bytes), "content", "must be bytes or None.")
        _require(self.json_body is None or self.content is None, "json_body", "and content cannot both be set.")
        valid_path = isinstance(self.link_path, tuple) and all(_is_text(part) for part in self.link_path)
        _require(valid_path, "link_path", f"must be a tuple of non-blank strings, got {self.link_path!r}.")
        _require(isinstance(self.link_prefix, str), "link_prefix", f"must be a string, got {self.link_prefix!r}.")


@dataclass(frozen=True, slots=True)
class OutputRead:
    """The result of one HTTP read: the parsed JSON, or the FAILED receipt that ends the send."""

    failure: DeliveryReceipt | None = None
    data: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        valid_failure = self.failure is None or (isinstance(self.failure, DeliveryReceipt) and self.failure.status is DeliveryStatus.FAILED)
        _require(valid_failure, "failure", f"must be None or a failed DeliveryReceipt, got {self.failure!r}.")
        _require(self.failure is None or self.data is None, "data", "must be None when failure is set.")


@dataclass(frozen=True, slots=True)
class SmtpSettings:
    """One SMTP session's server, login, sender, and recipients."""

    host: str
    port: int
    username: str
    password: str = field(repr=False)
    sender: str
    recipients: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(_is_text(self.host) and not any(char.isspace() for char in self.host), "host", f"must be a non-blank host with no whitespace, got {self.host!r}.")
        valid_port = isinstance(self.port, int) and not isinstance(self.port, bool) and SMTP_PORT_MIN <= self.port <= SMTP_PORT_MAX
        _require(valid_port, "port", f"must be an int from {SMTP_PORT_MIN} to {SMTP_PORT_MAX}, got {self.port!r}.")
        _require(_is_text(self.username), "username", f"must be a non-blank string, got {self.username!r}.")
        _require(_is_text(self.password), "password", "must be a non-blank string.")
        _require(_is_address(self.sender), "sender", f"must be one email address, got {self.sender!r}.")
        valid_recipients = isinstance(self.recipients, tuple) and bool(self.recipients) and all(_is_address(item) for item in self.recipients)
        _require(valid_recipients, "recipients", f"must be a non-empty tuple of email addresses, got {self.recipients!r}.")


__all__ = ["DeliveryReceipt", "OutputContent", "OutputRead", "OutputRequest", "SmtpSettings"]
