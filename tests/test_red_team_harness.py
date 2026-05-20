from __future__ import annotations

import json
import unittest

from vidbyte.harnesses.red_team import (
    HarnessPipeline,
    RedTeamChallengeHarness,
    RedTeamHarnessConfig,
    StoppingConditionEvaluator,
)
from vidbyte.lib.errors import ExploitSuccessError


class RedTeamHarnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_alternates_blue_then_red_each_round(self) -> None:
        calls: list[str] = []

        async def blue_model(prompt, *, context, tools):
            calls.append("blue")
            return json.dumps({"artifact": "safe artifact"})

        async def red_model(prompt, *, context, tools):
            calls.append("red")
            return json.dumps({"findings": []})

        harness = RedTeamChallengeHarness(
            blue_pipeline=HarnessPipeline(name="blue", model_fn=blue_model),
            red_pipeline=HarnessPipeline(name="red", model_fn=red_model),
            config=RedTeamHarnessConfig(max_rounds=1, consecutive_clean_attacks_for_win=1),
        )

        result = await harness.arun("build a validator")

        self.assertEqual(calls, ["blue", "red"])
        self.assertEqual(result.outcome, "defensive_win")

    async def test_context_views_filter_private_pipeline_output(self) -> None:
        red_context_roles: list[str] = []
        blue_prompts: list[str] = []

        async def blue_model(prompt, *, context, tools):
            blue_prompts.append(prompt)
            return json.dumps({"artifact": "patched sql injection", "patched_findings": ["sql"]})

        async def red_model(prompt, *, context, tools):
            red_context_roles.extend(f"{entry.role.value}:{entry.kind}" for entry in context)
            if len(red_context_roles) <= 2:
                return json.dumps(
                    {
                        "findings": [
                            {
                                "payload": "' OR 1=1",
                                "severity": 0.4,
                                "category": "sql",
                                "description": "sql injection",
                            }
                        ]
                    }
                )
            return json.dumps({"findings": []})

        harness = RedTeamChallengeHarness(
            blue_pipeline=HarnessPipeline(name="blue", model_fn=blue_model),
            red_pipeline=HarnessPipeline(name="red", model_fn=red_model),
            config=RedTeamHarnessConfig(max_rounds=2, consecutive_clean_attacks_for_win=2),
        )

        await harness.arun("build a validator")

        self.assertTrue(any("sql injection" in prompt for prompt in blue_prompts))
        self.assertIn("blue:target_artifact", red_context_roles)
        self.assertNotIn("blue:pipeline_output", red_context_roles)

    async def test_fatal_violation_raises_exploit_success_error_with_payload(self) -> None:
        async def blue_model(prompt, *, context, tools):
            return json.dumps({"artifact": "unsafe artifact"})

        async def red_model(prompt, *, context, tools):
            return json.dumps(
                {
                    "findings": [
                        {
                            "payload": "CRASH_PAYLOAD",
                            "severity": 1.0,
                            "category": "stability",
                            "description": "crashes runtime",
                            "fatal": True,
                        }
                    ]
                }
            )

        harness = RedTeamChallengeHarness(
            blue_pipeline=HarnessPipeline(name="blue", model_fn=blue_model),
            red_pipeline=HarnessPipeline(name="red", model_fn=red_model),
        )

        with self.assertRaises(ExploitSuccessError) as raised:
            await harness.arun("build a validator")

        self.assertEqual(raised.exception.payload, "CRASH_PAYLOAD")

    async def test_exhaustion_returns_highest_scoring_artifact(self) -> None:
        round_index = 0

        async def blue_model(prompt, *, context, tools):
            nonlocal round_index
            round_index += 1
            if round_index == 1:
                return json.dumps({"artifact": "first artifact"})
            return json.dumps({"artifact": "second artifact patches xss", "patched_findings": ["xss"]})

        async def red_model(prompt, *, context, tools):
            if round_index == 1:
                return json.dumps(
                    {
                        "findings": [
                            {
                                "payload": "<script>",
                                "severity": 0.5,
                                "category": "xss",
                                "description": "xss",
                            }
                        ]
                    }
                )
            return json.dumps({"findings": []})

        harness = RedTeamChallengeHarness(
            blue_pipeline=HarnessPipeline(name="blue", model_fn=blue_model),
            red_pipeline=HarnessPipeline(name="red", model_fn=red_model),
            evaluator=StoppingConditionEvaluator(),
            config=RedTeamHarnessConfig(
                max_rounds=2,
                consecutive_clean_attacks_for_win=3,
                fatal_severity_threshold=1.0,
            ),
        )

        result = await harness.arun("build a validator")

        self.assertEqual(result.outcome, "exhausted")
        self.assertIn("second artifact", result.artifact.content)
        self.assertGreater(result.score.equilibrium, 0.0)


if __name__ == "__main__":
    unittest.main()
