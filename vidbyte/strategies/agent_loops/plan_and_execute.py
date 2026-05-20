from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import PlanAndExecutePrompts
from vidbyte.strategies.base import BaseStrategy, parse_numbered_lines
from vidbyte.strategies.types import StrategyResult


class PlanAndExecuteStrategy(BaseStrategy):
    name: ClassVar[str] = "plan_and_execute"
    prompts: ClassVar[dict[str, str]] = PlanAndExecutePrompts().export()

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        plan_response = self._plan(prompt, runner=runner)
        steps = parse_numbered_lines(plan_response.text) or (plan_response.text.strip(),)
        step_calls, step_outputs = self._execute_plans(prompt, plan_response.text, steps, runner=runner)
        final_response = self._final_response(prompt, step_outputs, runner=runner)
        calls = tuple([plan_response, *step_calls, final_response])
        return StrategyResult(output=final_response.text, strategy_name=self.name, calls=calls, metadata={"plan": plan_response.text, "steps": steps})

    def _plan(self, prompt: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Request a numbered plan without revealing or solving the task yet.
        return runner.run(f"{self.prompts['plan_prompt']}\n\n{prompt}")

    def _execute_plans(self, prompt: str, plan_text: str, steps: tuple[str, ...], *, runner: TextModelRunner) -> tuple[list[TextModelResponse], list[str]]:
        # Run each plan step sequentially, grounded in the full plan context.
        calls: list[TextModelResponse] = []
        outputs: list[str] = []
        for index, step in enumerate(steps, start=1):
            response = runner.run(f"{self.prompts['execute_prompt']}\n\nOriginal task:\n{prompt}\n\nFull plan:\n{plan_text}\n\nStep {index}: {step}")
            calls.append(response)
            outputs.append(response.text)
        return calls, outputs

    def _final_response(self, prompt: str, step_outputs: list[str], *, runner: TextModelRunner) -> TextModelResponse:
        # Synthesize all step outputs into a single coherent final answer.
        return runner.run(f"{self.prompts['final_prompt']}\n\nOriginal task:\n{prompt}\n\nStep outputs:\n{chr(10).join(step_outputs)}\n\nFinal answer:")


__all__ = [
    "PlanAndExecuteStrategy",
]
