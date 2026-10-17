"""Context Protocol Header

Description:
    Tests for the Independent Critic context-window configuration.
Purpose:
    Validates that a custom review_prompt which str.format cannot render is
    refused at construction under every failure policy, and that a template
    with escaped braces renders them literally.
Relations:
    Exercises vidbyte/context/algorithms/independent_critic.py with no runner or network.
Similar Files:
    - tests/test_reflexion_algorithm.py: the same template checks for Reflexion.
"""

from __future__ import annotations

import unittest

from vidbyte import CriticFailurePolicy, IndependentCriticAlgorithm
from vidbyte.lib.errors import ConfigurationError

_JSON_EXAMPLE_PROMPT = 'Review {review_payload}. Reply as JSON like {"verdict": "pass"}.'
_ESCAPED_JSON_EXAMPLE_PROMPT = 'Review {review_payload}. Reply as JSON like {{"verdict": "pass"}}.'


class IndependentCriticReviewPromptTests(unittest.TestCase):
    def test_review_prompt_with_an_unknown_placeholder_is_refused_at_construction(self) -> None:
        # [Silent Failure] An example JSON object is an unknown {name} to str.format; under RETURN_CANDIDATE it used to skip every review.
        for policy in (CriticFailurePolicy.RAISE, CriticFailurePolicy.RETURN_CANDIDATE):
            with self.subTest(policy=policy):
                with self.assertRaises(ConfigurationError) as ctx:
                    IndependentCriticAlgorithm(review_prompt=_JSON_EXAMPLE_PROMPT, failure_policy=policy)
                self.assertIn('"verdict"', str(ctx.exception))
                self.assertIn("{{", str(ctx.exception))

    def test_review_prompt_with_escaped_braces_renders_them_literally(self) -> None:
        # [Edge Case] Escaped braces construct and reach the reviewer as a literal JSON example beside the payload.
        algorithm = IndependentCriticAlgorithm(review_prompt=_ESCAPED_JSON_EXAMPLE_PROMPT)
        rendered = algorithm.render_review_prompt("the task", "the candidate", ())
        self.assertTrue(rendered.endswith('Reply as JSON like {"verdict": "pass"}.'))
        self.assertIn('"candidate": "the candidate"', rendered)


if __name__ == "__main__":
    unittest.main()
