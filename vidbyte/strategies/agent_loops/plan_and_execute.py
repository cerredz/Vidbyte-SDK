from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy, parse_numbered_lines
from vidbyte.strategies.types import StrategyResult


class PlanAndExecuteStrategy(BaseStrategy):
    name: ClassVar[str] = "plan_and_execute"

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        plan_response = runner.run(
            "\n".join(
                [
                    "Create a concise numbered plan for solving the task.",
                    "Do not execute the plan yet.",
                    "",
                    prompt,
                ]
            )
        )
        steps = parse_numbered_lines(plan_response.text)
        if not steps:
            steps = (plan_response.text.strip(),)

        calls = [plan_response]
        step_outputs: list[str] = []
        for index, step in enumerate(steps, start=1):
            response = runner.run(
                "\n".join(
                    [
                        "Execute this plan step for the original task.",
                        "",
                        "Original task:",
                        prompt,
                        "",
                        "Full plan:",
                        plan_response.text,
                        "",
                        f"Step {index}: {step}",
                    ]
                )
            )
            calls.append(response)
            step_outputs.append(response.text)

        final_response = runner.run(
            "\n".join(
                [
                    "Synthesize the executed steps into a final answer.",
                    "",
                    "Original task:",
                    prompt,
                    "",
                    "Step outputs:",
                    "\n\n".join(step_outputs),
                    "",
                    "Final answer:",
                ]
            )
        )
        calls.append(final_response)
        return StrategyResult(
            output=final_response.text,
            strategy_name=self.name,
            calls=tuple(calls),
            metadata={"plan": plan_response.text, "steps": steps},
        )
