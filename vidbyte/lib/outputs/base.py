"""FILE: vidbyte/lib/outputs/base.py

PURPOSE: Defines BaseOutput, the provider base every connector subclasses, and OutputArguments, the checks for connector constructor arguments.
ROLE IN CODEBASE: Subclassed by the sixteen connectors in this package; the agent-side OutputConnector Protocol is satisfied structurally, with no import.
ARCHITECTURE NOTE: Provider work only. The skip rule, the reply shaping, and the render call live in vidbyte/agents/output/, never here.
COMMON MODIFICATION PATTERNS: Add a static check to OutputArguments when a new connector argument needs one; keep every error naming the parameter.
KNOWN EDGE CASES: Errors never echo a credential or a URL, because a webhook URL is itself the secret.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_configuration.py
"""

from __future__ import annotations

import base64
import os
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import TypeVar
from urllib.parse import urlsplit

from vidbyte.lib.constants.outputs import (
    OUTPUT_CREDENTIAL_ENV_VARS,
    OUTPUT_EMAIL_ADDRESS_PATTERN,
    OUTPUT_HEADER_NAME_PATTERN,
    OUTPUT_HTTPS_PREFIX,
    WEBHOOK_KEY_MAX_BYTES,
    WEBHOOK_KEY_MIN_BYTES,
    WEBHOOK_KEY_PREFIX,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.errors import ConfigurationError

CallableT = TypeVar("CallableT", bound=Callable[..., object])
EnumT = TypeVar("EnumT", bound=Enum)


class OutputArguments:
    """Static checks for connector arguments; each error names the parameter."""

    @staticmethod
    def credential(destination: OutputDestination, explicit: str | None, *, parameter: str) -> str:
        """Resolve a credential: the explicit argument, then the environment variable, each only when not blank."""
        env_var = OUTPUT_CREDENTIAL_ENV_VARS[destination]
        for candidate in (explicit, os.environ.get(env_var)):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        raise ConfigurationError(f"Missing credential for {destination.value} output. Pass {parameter} or set {env_var}.", details={"parameter": parameter, "env_var": env_var})

    @staticmethod
    def https_url(value: str, *, parameter: str) -> str:
        """Require an https:// URL with a host and a well-formed port; the error never shows the URL, which can be the secret."""
        message = f"{parameter} must be an https:// URL with a host and a valid port."
        try:
            parts = urlsplit(value)
            # Reading the port parses it, so a malformed or out-of-range
            # port fails here rather than at the first delivery.
            host, _port = parts.hostname, parts.port
        except ValueError:
            raise ConfigurationError(message, details={"parameter": parameter}) from None
        if value.startswith(OUTPUT_HTTPS_PREFIX) and host:
            return value
        raise ConfigurationError(message, details={"parameter": parameter})

    @staticmethod
    def text(value: object, *, parameter: str) -> str:
        """Require a non-blank string and return it stripped."""
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise ConfigurationError(f"{parameter} must be a non-blank string, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def texts(value: object, *, parameter: str) -> tuple[str, ...]:
        """Require a sequence of non-blank strings; a bare string is refused, since it would be read character by character."""
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return tuple(OutputArguments.text(item, parameter=parameter) for item in value)
        raise ConfigurationError(f"{parameter} must be a list or tuple of strings, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def non_empty(values: tuple[str, ...], *, parameter: str) -> tuple[str, ...]:
        """Require at least one item, so an empty list names the parameter rather than a record field."""
        if values:
            return values
        raise ConfigurationError(f"{parameter} must list at least one value.", details={"parameter": parameter})

    @staticmethod
    def identifier(value: object, *, parameter: str) -> str:
        """Require a UUID, dashed or 32 hex digits, and return it dashed."""
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            raise ConfigurationError(f"{parameter} must be a UUID, got {value!r}.", details={"parameter": parameter}) from None

    @staticmethod
    def optional_callable(value: CallableT | None, *, parameter: str) -> CallableT | None:
        """Require None or a callable."""
        if value is None or callable(value):
            return value
        raise ConfigurationError(f"{parameter} must be callable or None, got {type(value).__name__}.", details={"parameter": parameter})

    @staticmethod
    def matching(value: object, pattern: str, *, parameter: str) -> str:
        """Require a string that fully matches pattern, as given, with no stripping."""
        if isinstance(value, str) and re.fullmatch(pattern, value):
            return value
        raise ConfigurationError(f"{parameter} must match {pattern}, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def address(value: object, *, parameter: str) -> str:
        """Require one email address: an "@" and no whitespace, line break, or comma."""
        if isinstance(value, str) and re.fullmatch(OUTPUT_EMAIL_ADDRESS_PATTERN, value):
            return value
        raise ConfigurationError(f"{parameter} must be one email address, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def flag(value: object, *, parameter: str) -> bool:
        """Require a real bool, so a truthy string such as "no" is refused."""
        if isinstance(value, bool):
            return value
        raise ConfigurationError(f"{parameter} must be True or False, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def number(value: object, *, parameter: str) -> int:
        """Require a positive int that is not a bool."""
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        raise ConfigurationError(f"{parameter} must be a positive int, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def reference(value: object, pattern: str, *, parameter: str) -> str:
        """Require a positive int, returned as text, or a string that fully matches pattern, as given."""
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return str(value)
        if isinstance(value, str) and re.fullmatch(pattern, value):
            return value
        raise ConfigurationError(f"{parameter} must be a positive int or a string matching {pattern}, got {value!r}.", details={"parameter": parameter})

    @staticmethod
    def members(values: object, kind: type[EnumT], *, parameter: str) -> tuple[EnumT, ...]:
        """Require a list of one or more kind members or their values; duplicates are dropped in order."""
        allowed = ", ".join(str(member.value) for member in kind)
        message = f"{parameter} must list one or more of {allowed}, got {values!r}."
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            try:
                members = tuple(dict.fromkeys(kind(value) for value in values))
            except ValueError:
                raise ConfigurationError(message, details={"parameter": parameter}) from None
            if members:
                return members
        raise ConfigurationError(message, details={"parameter": parameter})

    @staticmethod
    def headers(value: object, *, parameter: str) -> Mapping[str, str]:
        """Require a mapping of HTTP header names to values; return it with lowercase names."""
        # @intent header-errors-never-echo-a-value
        # A header value is often a credential, and a bad name can be a
        # whole pasted line ("Authorization: Bearer ..."), so an error
        # names a valid header name or a bad name's position, never a
        # value and never the bad name itself.
        if isinstance(value, Mapping):
            lowered: dict[str, str] = {}
            for position, (name, text) in enumerate(value.items(), start=1):
                if not (isinstance(name, str) and re.fullmatch(OUTPUT_HEADER_NAME_PATTERN, name)):
                    raise ConfigurationError(f"{parameter} entry {position} does not have a valid HTTP header name.", details={"parameter": parameter, "position": position})
                header = name.lower()
                if not isinstance(text, str) or any(mark in text for mark in "\r\n\x00"):
                    raise ConfigurationError(f"{parameter} value for {header} must be a string with no line break or NUL.", details={"parameter": parameter, "header": header})
                if header in lowered:
                    raise ConfigurationError(f"{parameter} names {header} more than once; header names ignore case.", details={"parameter": parameter, "header": header})
                lowered[header] = text
            return lowered
        raise ConfigurationError(f"{parameter} must be a mapping of header names to values, got {type(value).__name__}.", details={"parameter": parameter})

    @staticmethod
    def signing_key(value: object, *, parameter: str) -> bytes:
        """Require a Standard Webhooks secret, an optional whsec_ prefix and then strict base64, and return the decoded key."""
        # @intent signing-secret-is-never-echoed
        # The secret signs every request, so an error names only the
        # parameter and the rule, never the value or any part of it.
        message = f"{parameter} must be a {WEBHOOK_KEY_PREFIX} secret: base64 of {WEBHOOK_KEY_MIN_BYTES} to {WEBHOOK_KEY_MAX_BYTES} bytes."
        if isinstance(value, str):
            try:
                key = base64.b64decode(value.strip().removeprefix(WEBHOOK_KEY_PREFIX), validate=True)
            except ValueError:
                raise ConfigurationError(message, details={"parameter": parameter}) from None
            if WEBHOOK_KEY_MIN_BYTES <= len(key) <= WEBHOOK_KEY_MAX_BYTES:
                return key
        raise ConfigurationError(message, details={"parameter": parameter})

    @staticmethod
    def exclusive(values: Mapping[str, object], *, required: bool = False) -> None:
        """Allow at most one of the named arguments to be set, and, when required, exactly one; None and an empty list count as not set."""
        chosen = [name for name, value in values.items() if value is not None and not (isinstance(value, Sequence) and not value)]
        names = " and ".join(values)
        if len(chosen) > 1:
            raise ConfigurationError(f"Pass at most one of {names}, not both.", details={"parameters": list(values)})
        if required and not chosen:
            raise ConfigurationError(f"Pass one of {names}.", details={"parameters": list(values)})


class BaseOutput(ABC):
    """Provider base: keeps the optional render hook and hides the credential from repr."""

    destination: OutputDestination

    def __init__(self, *, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        self._render = OutputArguments.optional_callable(render, parameter="render")

    @property
    def render(self) -> Callable[[AgentMessage], OutputContent] | None:
        """The caller's content builder that replaces the default shaping, if any."""
        return self._render

    @abstractmethod
    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Deliver one reply's content to this destination and report the outcome."""
        # @intent one-send-one-receipt
        # A send makes one delivery and returns its receipt; failures
        # the destination reports become FAILED receipts, not raises.

    def __repr__(self) -> str:
        return f"{type(self).__name__}(credential='***')"


__all__ = ["BaseOutput", "OutputArguments"]
