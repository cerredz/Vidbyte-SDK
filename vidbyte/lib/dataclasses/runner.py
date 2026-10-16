from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.lib.enums.text_model import TextModelMode

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agents import ProviderKeys


class RunnerHandle:
    """Bundles a runner object, provider label, and invocation/extraction callables into one unit."""

    def __init__(self, *, runner: object, provider: str, invoke: Callable[..., Any], extract_text: Callable[[object], str], extract_metadata: Callable[[object], Mapping[str, Any]], api_keys: ProviderKeys | None = None, model_mode: TextModelMode = TextModelMode.AUTO) -> None:
        # Store the runner object, provider label, and the three callable strategies.
        self.runner = runner
        self.provider = provider
        self._invoke = invoke
        self._extract_text = extract_text
        self._extract_metadata = extract_metadata
        # @intent handle-carries-the-agents-keys-and-mode
        # A stage that builds its own runner passes these on, so the child model authenticates and routes like its agent.
        self.api_keys = api_keys
        self.model_mode = model_mode

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
            api_keys=self.api_keys,
            model_mode=self.model_mode,
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
            api_keys=self.api_keys,
            model_mode=self.model_mode,
        )


__all__ = ["RunnerHandle"]
