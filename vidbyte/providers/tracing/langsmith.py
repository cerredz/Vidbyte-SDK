from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing.base import SpanContext, TracerBase


@dataclass
class LangSmithSpanContext(SpanContext):
    """Carries LangSmith run identity for child span attachment."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_run_id: str | None = None


class LangSmithTracer(TracerBase):
    """Tracing adapter for LangSmith (https://smith.langchain.com).

    Credentials are read from constructor kwargs first, then from environment
    variables LANGSMITH_API_KEY and LANGSMITH_PROJECT.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        project: str | None = None,
    ) -> None:
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
        self._client = Client(api_key=resolved_api_key)

    def start_trace(self, name: str, **attributes: Any) -> LangSmithSpanContext:
        run_id = str(uuid.uuid4())
        try:
            self._client.create_run(
                id=run_id,
                name=name,
                run_type="chain",
                inputs=attributes,
                project_name=self._project,
            )
        except Exception:
            pass
        return LangSmithSpanContext(run_id=run_id)

    def end_trace(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        if not isinstance(context, LangSmithSpanContext):
            return
        try:
            if error is not None:
                self._client.update_run(
                    context.run_id,
                    error=str(error),
                    end_time=_now(),
                )
            else:
                self._client.update_run(
                    context.run_id,
                    outputs={"output": output},
                    end_time=_now(),
                )
        except Exception:
            pass

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        **attributes: Any,
    ) -> LangSmithSpanContext:
        run_id = str(uuid.uuid4())
        parent_run_id = parent.run_id if isinstance(parent, LangSmithSpanContext) else None
        run_type = "llm" if name.startswith("llm.") else "tool"
        try:
            self._client.create_run(
                id=run_id,
                name=name,
                run_type=run_type,
                inputs=attributes,
                parent_run_id=parent_run_id,
                project_name=self._project,
            )
        except Exception:
            pass
        return LangSmithSpanContext(run_id=run_id, parent_run_id=parent_run_id)

    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        if not isinstance(context, LangSmithSpanContext):
            return
        try:
            if error is not None:
                self._client.update_run(
                    context.run_id,
                    error=str(error),
                    end_time=_now(),
                )
            else:
                self._client.update_run(
                    context.run_id,
                    outputs={"output": output},
                    end_time=_now(),
                )
        except Exception:
            pass


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


__all__ = ["LangSmithSpanContext", "LangSmithTracer"]
