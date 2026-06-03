from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


class RunnerHandle:
    """Bundles a runner object, provider label, and invocation/extraction callables into one unit."""

    def __init__(self, *, runner: object, provider: str, invoke: Callable[..., Any], extract_text: Callable[[object], str], extract_metadata: Callable[[object], Mapping[str, Any]]) -> None:
        # Store the runner object, provider label, and the three callable strategies.
        self.runner = runner
        self.provider = provider
        self._invoke = invoke
        self._extract_text = extract_text
        self._extract_metadata = extract_metadata

    async def invoke(self, message: str, **options: Any) -> object:
        # Call the underlying runner with the stored duck-typed dispatch logic.
        return await self._invoke(self.runner, message, **options)

    def extract_text(self, result: object) -> str:
        # Extract the text content from any runner response shape.
        return self._extract_text(result)

    def extract_metadata(self, result: object) -> Mapping[str, Any]:
        # Extract the metadata mapping from any runner response shape.
        return self._extract_metadata(result)

    def with_runner(self, runner: object, provider: str) -> RunnerHandle:
        # Return a new handle with a different runner and provider, reusing all other logic.
        return RunnerHandle(
            runner=runner,
            provider=provider,
            invoke=self._invoke,
            extract_text=self._extract_text,
            extract_metadata=self._extract_metadata,
        )

    def wrap_text(self, interceptor: Callable[[str], None]) -> RunnerHandle:
        # Return a new handle that calls interceptor(text) as a side-effect during extract_text.
        original = self._extract_text

        def wrapped(result: object) -> str:
            text = original(result)
            interceptor(text)
            return text

        return RunnerHandle(
            runner=self.runner,
            provider=self.provider,
            invoke=self._invoke,
            extract_text=wrapped,
            extract_metadata=self._extract_metadata,
        )


__all__ = ["RunnerHandle"]
