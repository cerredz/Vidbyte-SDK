from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing.base import SpanContext, TracerBase


@dataclass
class LangfuseSpanContext(SpanContext):
    """Carries the Langfuse trace or generation/span handle."""

    handle: Any = field(default=None)


class LangfuseTracer(TracerBase):
    """Tracing adapter for Langfuse (https://langfuse.com).

    Credentials are read from constructor kwargs first, then from environment
    variables LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST.
    """

    def __init__(
        self,
        *,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
    ) -> None:
        try:
            import langfuse  # noqa: F401 — validate install
            from langfuse import Langfuse
        except ImportError as exc:
            raise TracerConfigurationError(
                "langfuse is not installed. Install it with: pip install langfuse"
            ) from exc

        resolved_public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
        resolved_secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")
        resolved_host = host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

        if not resolved_public_key or not resolved_secret_key:
            raise TracerConfigurationError(
                "LangfuseTracer requires public_key and secret_key. "
                "Pass them as constructor arguments or set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY."
            )

        self._client = Langfuse(
            public_key=resolved_public_key,
            secret_key=resolved_secret_key,
            host=resolved_host,
        )

    def start_trace(self, name: str, **attributes: Any) -> LangfuseSpanContext:
        try:
            trace = self._client.trace(name=name, metadata=attributes or None)
            return LangfuseSpanContext(handle=trace)
        except Exception:
            return LangfuseSpanContext()

    def end_trace(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        if not isinstance(context, LangfuseSpanContext) or context.handle is None:
            return
        try:
            if error is not None:
                context.handle.update(status_message=str(error), level="ERROR")
            elif output is not None:
                context.handle.update(output=output)
            self._client.flush()
        except Exception:
            pass

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        **attributes: Any,
    ) -> LangfuseSpanContext:
        parent_handle = (
            parent.handle
            if isinstance(parent, LangfuseSpanContext) and parent.handle is not None
            else None
        )
        try:
            if parent_handle is not None:
                if name.startswith("llm."):
                    handle = parent_handle.generation(name=name, metadata=attributes or None)
                else:
                    handle = parent_handle.span(name=name, metadata=attributes or None)
            else:
                trace = self._client.trace(name=name, metadata=attributes or None)
                handle = trace
            return LangfuseSpanContext(handle=handle)
        except Exception:
            return LangfuseSpanContext()

    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        # Closes a Langfuse span with output/error plus optional structured metadata.
        if not isinstance(context, LangfuseSpanContext) or context.handle is None:
            return
        try:
            if metadata:
                context.handle.update(metadata=dict(metadata))
            if error is not None:
                context.handle.update(status_message=str(error), level="ERROR")
            if hasattr(context.handle, "end"):
                context.handle.end(output=output)
        except Exception:
            pass


__all__ = ["LangfuseSpanContext", "LangfuseTracer"]
