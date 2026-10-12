"""FILE: vidbyte/lib/outputs/base.py

PURPOSE: Defines BaseOutput, the provider base every connector subclasses, and OutputArguments, the checks for connector constructor arguments.
ROLE IN CODEBASE: Subclassed by the eleven connectors in this package; the agent-side OutputConnector Protocol is satisfied structurally, with no import.
ARCHITECTURE NOTE: Provider work only. The skip rule, the reply shaping, and the render call live in vidbyte/agents/output/, never here.
COMMON MODIFICATION PATTERNS: Add a static check to OutputArguments when a new connector argument needs one; keep every error naming the parameter.
KNOWN EDGE CASES: Errors never echo a credential or a URL, because a webhook URL is itself the secret.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_configuration.py
"""

from __future__ import annotations

import os
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from vidbyte.lib.constants.outputs import OUTPUT_CREDENTIAL_ENV_VARS
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.errors import ConfigurationError


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
        """Require an https:// URL with a host; the error never shows the URL, which can be the secret."""
        if value.startswith("https://") and urlsplit(value).hostname:
            return value
        raise ConfigurationError(f"{parameter} must be an https:// URL with a host.", details={"parameter": parameter})

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
    def identifier(value: object, *, parameter: str) -> str:
        """Require a UUID, dashed or 32 hex digits, and return it dashed."""
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            raise ConfigurationError(f"{parameter} must be a UUID, got {value!r}.", details={"parameter": parameter}) from None

    @staticmethod
    def optional_callable(value: Callable[[AgentMessage], OutputContent] | None, *, parameter: str) -> Callable[[AgentMessage], OutputContent] | None:
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
        if isinstance(value, str) and "@" in value and not any(char.isspace() or char == "," for char in value):
            return value
        raise ConfigurationError(f"{parameter} must be one email address, got {value!r}.", details={"parameter": parameter})


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
