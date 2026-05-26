"""Context Protocol Header

Description:
    Secret-redaction middleware that scans tool inputs and outputs for known
    secret patterns and replaces them with safe placeholder tokens.
Purpose:
    Prevents accidental disclosure of API keys, bearer tokens, private keys,
    and credential-like strings in agent conversation history and logs.
Architecture:
    - SECRET_PATTERNS defines regex-to-replacement mappings including callables.
    - SecretRedactionMiddleware.redact() is a static method for standalone use.
    - before_tool_call redacts tool call arguments.
    - after_tool_call redacts tool result outputs.
Relations:
    Extends vidbyte.middleware.base.AgentMiddleware.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.middleware.base import AgentMiddleware

SECRET_PATTERNS: list[tuple[str, str | Callable[[re.Match], str]]] = [
    (r"sk-[a-zA-Z0-9]{20,}", "[OPENAI_KEY]"),
    (r"sk-ant-[a-zA-Z0-9\-_]{20,}", "[ANTHROPIC_KEY]"),
    (r"AIza[0-9A-Za-z\-_]{35}", "[GOOGLE_KEY]"),
    (r"Bearer\s+[a-zA-Z0-9\-_\.]{20,}", "[BEARER_TOKEN]"),
    (r"github_pat_[a-zA-Z0-9_]{20,}", "[GITHUB_PAT]"),
    (
        r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----.*?-----END .*?-----",
        "[PRIVATE_KEY]",
    ),
    (
        r'(?:api_key|apikey|api-key|secret|password|token|auth)\s*[:=]\s*["\']?([a-zA-Z0-9\-_\.]{16,})["\']?',
        lambda m: f"{m.group(0).split(':')[0].split('=')[0]}=[REDACTED]",
    ),
]


class SecretRedactionMiddleware(AgentMiddleware):
    """Detects and redacts secrets in tool inputs and outputs."""

    @staticmethod
    def redact(text: str) -> str:
        """Apply all secret patterns to the given string, returning a sanitized copy."""
        for pattern, replacement in SECRET_PATTERNS:
            if callable(replacement):
                text = re.sub(pattern, replacement, text, flags=re.DOTALL)
            else:
                text = re.sub(pattern, replacement, text, flags=re.DOTALL)
        return text

    def _redact_tool_call(self, tool_call: ToolCall | None) -> None:
        """Redact secrets from a ToolCall's arguments in place."""
        if tool_call is None:
            return
        try:
            redacted_args: dict[str, Any] = {}
            for key, value in dict(tool_call.arguments).items():
                if isinstance(value, str):
                    redacted_args[key] = self.redact(value)
                else:
                    redacted_args[key] = value
            object.__setattr__(tool_call, "arguments", redacted_args)
        except Exception:
            pass

    def _redact_tool_result(self, tool_result: ToolResult | None) -> None:
        """Redact secrets from a ToolResult's output in place."""
        if tool_result is None:
            return
        try:
            object.__setattr__(tool_result, "output", self.redact(tool_result.output))
        except Exception:
            pass

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Redact secrets from tool call arguments."""
        self._redact_tool_call(ctx.tool_call)
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Redact secrets from tool call results."""
        self._redact_tool_result(ctx.tool_result)
        return MiddlewareDecision.continue_()


__all__ = ["SECRET_PATTERNS", "SecretRedactionMiddleware"]
