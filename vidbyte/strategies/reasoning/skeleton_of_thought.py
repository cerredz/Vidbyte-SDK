from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner, TextModelResponse
from vidbyte.strategies.base import BaseStrategy, parse_numbered_lines, require_positive
from vidbyte.strategies.types import StrategyResult


class SkeletonOfThoughtStrategy(BaseStrategy):
    name: ClassVar[str] = "skeleton_of_thought"

    def __init__(self, *, max_points: int = 8, max_workers: int = 4) -> None:
        require_positive(max_points, field_name="max_points")
        require_positive(max_workers, field_name="max_workers")
        self.max_points = max_points
        self.max_workers = max_workers

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        skeleton_response = runner.run(
            "\n".join(
                [
                    "Create a concise numbered skeleton for answering the task.",
                    f"Use no more than {self.max_points} points.",
                    "Do not fill in the details yet.",
                    "",
                    prompt,
                ]
            )
        )
        points = parse_numbered_lines(skeleton_response.text)[: self.max_points]
        if not points:
            points = (skeleton_response.text.strip(),)

        def complete_point(point: str) -> TextModelResponse:
            return runner.run(
                "\n".join(
                    [
                        "Complete this one skeleton point for the original task.",
                        "",
                        "Original task:",
                        prompt,
                        "",
                        "Point:",
                        point,
                    ]
                )
            )

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(points))) as executor:
            completion_responses = tuple(executor.map(complete_point, points))

        assembled = "\n\n".join(
            f"{index}. {point}\n{response.text}"
            for index, (point, response) in enumerate(zip(points, completion_responses), start=1)
        )
        calls = (skeleton_response, *completion_responses)
        return StrategyResult(
            output=assembled,
            strategy_name=self.name,
            calls=calls,
            metadata={"points": points, "max_workers": self.max_workers},
        )
