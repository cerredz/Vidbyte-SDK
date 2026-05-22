from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import SkeletonOfThoughtPrompts
from vidbyte.strategies.base import BaseStrategy, BaseStrategyUtils
from vidbyte.strategies.types import StrategyResult


class SkeletonOfThoughtStrategy(BaseStrategy):
    name: ClassVar[str] = "skeleton_of_thought"
    prompts: ClassVar[dict[str, str]] = SkeletonOfThoughtPrompts().export()

    def __init__(self, *, max_points: int = 8, max_workers: int = 4, **runner_options: object) -> None:
        super().__init__(**runner_options)
        BaseStrategyUtils.require_positive(max_points, field_name="max_points")
        BaseStrategyUtils.require_positive(max_workers, field_name="max_workers")
        self.max_points = max_points
        self.max_workers = max_workers

    def run(self, prompt: str, *, runner: TextModelRunner | None = None, **options: object) -> StrategyResult:
        runner = self._resolve_runner(runner)
        skeleton_response = self._build_skeleton(prompt, runner=runner)
        points = self._parse_points(skeleton_response.text)
        completion_responses = self._expand_points(prompt, skeleton_response.text, points, runner=runner)
        assembled = self._assemble_output(points, completion_responses)
        calls = (skeleton_response, *completion_responses)
        return StrategyResult(output=assembled, strategy_name=self.name, calls=calls, metadata={"points": points, "max_workers": self.max_workers})

    def _build_skeleton(self, prompt: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Request a concise numbered skeleton before expanding into detail.
        instruction = self.prompts["skeleton_prompt"].format(max_points=self.max_points)
        return self._run_model(runner, f"{instruction}\n\n{prompt}")

    def _parse_points(self, skeleton_text: str) -> tuple[str, ...]:
        # Extract numbered lines up to max_points; fall back to the full text.
        points = BaseStrategyUtils.parse_numbered_lines(skeleton_text)[: self.max_points]
        return points if points else (skeleton_text.strip(),)

    def _expand_points(self, prompt: str, skeleton_text: str, points: tuple[str, ...], *, runner: TextModelRunner) -> tuple[TextModelResponse, ...]:
        # Expand skeleton points in parallel using the configured thread pool.
        expand_prompt = self.prompts["expand_prompt"]

        def complete_point(point: str) -> TextModelResponse:
            return self._run_model(runner, f"{expand_prompt}\n\nOriginal task:\n{prompt}\n\nSkeleton:\n{skeleton_text}\n\nPoint:\n{point}")

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(points))) as executor:
            return tuple(executor.map(complete_point, points))

    def _assemble_output(self, points: tuple[str, ...], responses: tuple[TextModelResponse, ...]) -> str:
        # Interleave skeleton points with their expanded text into one document.
        return "\n\n".join(f"{i}. {p}\n{r.text}" for i, (p, r) in enumerate(zip(points, responses), start=1))


__all__ = [
    "SkeletonOfThoughtStrategy",
]
