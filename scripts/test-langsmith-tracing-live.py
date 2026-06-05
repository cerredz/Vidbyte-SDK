"""Live LangSmith smoke verification for the Vidbyte SDK tracer."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _add_repo_path() -> None:
    # Makes this worktree importable without requiring editable installation.
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))


def _safe_setting(name: str, default: str = "") -> str:
    # Returns non-secret diagnostic settings for smoke output.
    value = os.environ.get(name, default)
    return value if value else default


def main() -> None:
    # Creates and closes one strict LangSmith trace plus one child span.
    _add_repo_path()
    from vidbyte.providers.tracing.langsmith import LangSmithTracer

    project = _safe_setting("LANGSMITH_PROJECT", "default")
    endpoint = _safe_setting("LANGSMITH_ENDPOINT", "client-default")
    try:
        tracer = LangSmithTracer(project=project, endpoint=None if endpoint == "client-default" else endpoint, strict=True)
        root = tracer.start_trace("vidbyte.langsmith.smoke", smoke=True, project=project)
        span = tracer.start_span("llm.call", parent=root, provider="smoke", iteration=0)
        tracer.end_span(span, output="ok")
        tracer.end_trace(root, output="ok")
    except Exception as exc:
        print(f"FAIL: LangSmith smoke trace failed for project={project!r} endpoint={endpoint!r}: {exc}")
        sys.exit(1)
    print(f"PASS: LangSmith smoke trace created for project={project!r} endpoint={endpoint!r}")


if __name__ == "__main__":
    main()
