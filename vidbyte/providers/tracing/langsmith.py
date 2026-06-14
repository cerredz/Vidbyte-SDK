from __future__ import annotations

import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing.base import SpanContext, TracerBase


@dataclass
class LangSmithSpanContext(SpanContext):
    """Carries LangSmith run identity for child span attachment."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_run_id: str | None = None
    trace_id: str | None = None


class LangSmithTracer(TracerBase):
    """Tracing adapter for LangSmith (https://smith.langchain.com).

    Credentials are read from constructor kwargs first, then from environment
    variables LANGSMITH_API_KEY and LANGSMITH_PROJECT.
    """

    def __init__(self, *, api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False) -> None:
        # Resolves LangSmith credentials/settings and creates the client adapter.
        try:
            from langsmith import Client
        except ImportError as exc:
            raise TracerConfigurationError(
                "langsmith is not installed. Install it with: pip install langsmith"
            ) from exc

        resolved_api_key = api_key or os.environ.get("LANGSMITH_API_KEY")
        if not resolved_api_key:
            raise TracerConfigurationError(
                "LangSmithTracer requires an api_key. "
                "Pass it as a constructor argument or set LANGSMITH_API_KEY."
            )

        self._project = project or os.environ.get("LANGSMITH_PROJECT", "default")
        self._endpoint = endpoint or os.environ.get("LANGSMITH_ENDPOINT")
        self._strict = strict
        self._include_runtime_info = include_runtime_info
        self._last_error: Exception | None = None
        self._client = self._build_client(Client, api_key=resolved_api_key)

    @property
    def last_error(self) -> Exception | None:
        # Returns the most recent sanitized LangSmith delivery error, if any.
        return self._last_error

    def _build_client(self, client_cls: type[Any], *, api_key: str) -> Any:
        # Constructs the LangSmith client with endpoint support when configured.
        kwargs: dict[str, Any] = {"api_key": api_key}
        kwargs["omit_traced_runtime_info"] = not self._include_runtime_info
        if self._endpoint:
            kwargs["api_url"] = self._endpoint
        try:
            return client_cls(**kwargs)
        except TypeError as exc:
            if self._endpoint:
                self._record_error(exc)
                if self._strict:
                    raise TracerConfigurationError(
                        "LangSmith client does not accept LANGSMITH_ENDPOINT/api_url."
                    ) from exc
                return client_cls(api_key=api_key)
            raise

    def _record_error(self, exc: Exception) -> None:
        # Stores a sanitized copy of an adapter error for later diagnostics.
        self._last_error = RuntimeError(_redact(str(exc)))

    def _call_langsmith(self, action: str, fn: Any, *args: Any, **kwargs: Any) -> None:
        # Runs a LangSmith client call and optionally fails in strict verification mode.
        try:
            fn(*args, **kwargs)
            self._last_error = None
        except Exception as exc:
            self._record_error(exc)
            if self._strict:
                raise TracerConfigurationError(f"LangSmith {action} failed: {self._last_error}") from exc

    def start_trace(self, name: str, **attributes: Any) -> LangSmithSpanContext:
        # Opens a root LangSmith chain run and returns its run context.
        run_id = str(uuid.uuid4())
        self._call_langsmith(
            "create_run",
            self._client.create_run,
            id=run_id,
            name=name,
            run_type="chain",
            inputs=attributes,
            project_name=self._project,
        )
        return LangSmithSpanContext(run_id=run_id, trace_id=run_id)

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Closes a root LangSmith chain run with either output or error metadata.
        if not isinstance(context, LangSmithSpanContext):
            return
        if error is not None:
            self._call_langsmith("update_run", self._client.update_run, context.run_id, error=str(error), end_time=_now())
        else:
            self._call_langsmith("update_run", self._client.update_run, context.run_id, outputs={"output": output}, end_time=_now())
        self._call_langsmith("flush", self._client.flush)

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> LangSmithSpanContext:
        # Opens a child LangSmith run under the parent trace when available.
        run_id = str(uuid.uuid4())
        parent_run_id = parent.run_id if isinstance(parent, LangSmithSpanContext) else None
        trace_id = parent.trace_id if isinstance(parent, LangSmithSpanContext) else None
        run_type = "llm" if name.startswith("llm.") else "tool"
        create_kwargs: dict[str, Any] = dict(
            id=run_id,
            name=name,
            run_type=run_type,
            inputs=attributes,
            parent_run_id=parent_run_id,
            project_name=self._project,
        )
        if trace_id is not None:
            create_kwargs["trace_id"] = trace_id
        self._call_langsmith("create_run", self._client.create_run, **create_kwargs)
        return LangSmithSpanContext(run_id=run_id, parent_run_id=parent_run_id, trace_id=trace_id)

    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        # Closes a child LangSmith run with output or error plus optional structured metadata.
        if not isinstance(context, LangSmithSpanContext):
            return
        extra = dict(metadata or {})
        if error is not None:
            self._call_langsmith("update_run", self._client.update_run, context.run_id, error=str(error), outputs=extra or None, end_time=_now())
        else:
            self._call_langsmith("update_run", self._client.update_run, context.run_id, outputs={"output": output, **extra}, end_time=_now())
        self._call_langsmith("flush", self._client.flush)


def _now() -> Any:
    # Returns the current UTC datetime object expected by the LangSmith client.
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _redact(value: str) -> str:
    # Redacts common LangSmith and xAI key shapes from diagnostic strings.
    redacted = re.sub(r"lsv2_[A-Za-z0-9_\\-]+", "lsv2_[REDACTED]", value)
    redacted = re.sub(r"xai-[A-Za-z0-9_\\-]+", "xai-[REDACTED]", redacted)
    return redacted


__all__ = ["LangSmithSpanContext", "LangSmithTracer"]
