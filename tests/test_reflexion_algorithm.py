"""Context Protocol Header

Description:
    Tests for the Reflexion context-window algorithm config and helpers.
Purpose:
    Validates ReflexionAdmission enum, ReflexionConfig dataclass,
    ContextWindowAlgorithm integration, presets, and helper functions.
"""

from __future__ import annotations

import unittest

from vidbyte import ReflexionAdmission, ReflexionConfig
from vidbyte.context import ContextWindowAlgorithm, ContextWindowPresets
from vidbyte.context.algorithms.reflexion import (
    REFLECTION_AFTER_LAST_TRIAL_HEADER,
    REFLECTION_HEADER,
    LAST_TRIAL_HEADER,
    build_reflexion_context,
    format_last_attempt,
    format_reflections,
)


class ReflexionAdmissionTests(unittest.TestCase):
    def test_enum_values(self) -> None:
        self.assertEqual(ReflexionAdmission.NONE.value, "none")
        self.assertEqual(ReflexionAdmission.LAST_ATTEMPT.value, "last_attempt")
        self.assertEqual(ReflexionAdmission.REFLEXION.value, "reflexion")
        self.assertEqual(
            ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION.value,
            "last_attempt_and_reflexion",
        )

    def test_enum_is_str(self) -> None:
        self.assertIsInstance(ReflexionAdmission.NONE, str)
        self.assertEqual(ReflexionAdmission.REFLEXION, "reflexion")


class ReflexionConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        config = ReflexionConfig()
        self.assertEqual(config.admission, ReflexionAdmission.REFLEXION)
        self.assertEqual(config.max_reflection_chars, 1000)
        self.assertEqual(config.max_scratchpad_chars, 6000)
        self.assertEqual(config.metadata, {})

    def test_custom_admission(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.LAST_ATTEMPT)
        self.assertEqual(config.admission, ReflexionAdmission.LAST_ATTEMPT)

    def test_custom_token_limits(self) -> None:
        config = ReflexionConfig(max_reflection_chars=500, max_scratchpad_chars=3000)
        self.assertEqual(config.max_reflection_chars, 500)
        self.assertEqual(config.max_scratchpad_chars, 3000)

    def test_is_frozen(self) -> None:
        config = ReflexionConfig()
        with self.assertRaises(Exception):
            config.admission = ReflexionAdmission.NONE  # type: ignore[misc]


class ContextWindowAlgorithmReflexionTests(unittest.TestCase):
    def test_default_no_reflexion(self) -> None:
        algo = ContextWindowAlgorithm(name="test")
        self.assertIsNone(algo.reflexion)

    def test_with_reflexion(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.REFLEXION)
        algo = ContextWindowAlgorithm(name="test", reflexion=config)
        self.assertIsNotNone(algo.reflexion)
        self.assertEqual(algo.reflexion.admission, ReflexionAdmission.REFLEXION)


class FormatReflectionsTests(unittest.TestCase):
    def test_empty_returns_empty_string(self) -> None:
        result = format_reflections([])
        self.assertEqual(result, "")

    def test_non_empty_formats_with_header_and_bullets(self) -> None:
        reflections = ["Diagnose failure A", "Plan improvement B"]
        result = format_reflections(reflections)
        self.assertIn(REFLECTION_HEADER, result)
        self.assertIn("Diagnose failure A", result)
        self.assertIn("Plan improvement B", result)
        self.assertTrue(result.startswith(REFLECTION_HEADER))

    def test_custom_header(self) -> None:
        result = format_reflections(["test"], header="Custom:")
        self.assertTrue(result.startswith("Custom:"))

    def test_strips_whitespace(self) -> None:
        result = format_reflections(["  padded  "])
        self.assertIn("padded", result)
        self.assertNotIn("  padded  ", result)


class FormatLastAttemptTests(unittest.TestCase):
    def test_formats_question_and_scratchpad(self) -> None:
        result = format_last_attempt("What is X?", "Thought: maybe Y")
        self.assertIn(LAST_TRIAL_HEADER, result)
        self.assertIn("What is X?", result)
        self.assertIn("Thought: maybe Y", result)
        self.assertIn("(END PREVIOUS TRIAL)", result)

    def test_truncates_long_scratchpad(self) -> None:
        long_pad = "Observation: " + ("x" * 5000)
        result = format_last_attempt("Q", long_pad, max_chars=100)
        self.assertLess(len(result), len(long_pad) + 200)
        self.assertIn("[truncated]", result)

    def test_respects_custom_max_chars(self) -> None:
        long_pad = "Observation: " + ("y" * 3000)
        result = format_last_attempt("Q", long_pad, max_chars=500)
        self.assertIn("[truncated]", result)

    def test_short_scratchpad_not_truncated(self) -> None:
        short = "Thought: hello"
        result = format_last_attempt("Q", short)
        self.assertNotIn("[truncated]", result)


class BuildReflexionContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.question = "Test question"
        self.scratchpad = "Thought: test\nObservation: result"
        self.reflections = ["Fix approach A", "Try method B"]

    def test_none_strategy_returns_empty(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.NONE)
        result = build_reflexion_context(config, self.question, self.scratchpad, self.reflections)
        self.assertEqual(result, "")

    def test_last_attempt_strategy(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.LAST_ATTEMPT)
        result = build_reflexion_context(config, self.question, self.scratchpad, self.reflections)
        self.assertIn(LAST_TRIAL_HEADER, result)
        self.assertIn(self.question, result)
        self.assertNotIn(REFLECTION_HEADER, result)

    def test_reflexion_strategy(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.REFLEXION)
        result = build_reflexion_context(config, self.question, self.scratchpad, self.reflections)
        self.assertIn(REFLECTION_HEADER, result)
        self.assertIn("Fix approach A", result)
        self.assertNotIn(LAST_TRIAL_HEADER, result)

    def test_last_attempt_and_reflexion_strategy(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION)
        result = build_reflexion_context(config, self.question, self.scratchpad, self.reflections)
        self.assertIn(LAST_TRIAL_HEADER, result)
        self.assertIn(REFLECTION_AFTER_LAST_TRIAL_HEADER, result)
        self.assertIn("Fix approach A", result)

    def test_empty_reflections_in_combined(self) -> None:
        config = ReflexionConfig(admission=ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION)
        result = build_reflexion_context(config, self.question, self.scratchpad, [])
        self.assertIn(LAST_TRIAL_HEADER, result)
        self.assertNotIn("Reflections:", result)


class PresetTests(unittest.TestCase):
    def test_reflexion_preset(self) -> None:
        presets = ContextWindowPresets()
        algo = presets.reflexion
        self.assertEqual(algo.name, "reflexion")
        self.assertIsNotNone(algo.reflexion)
        self.assertEqual(algo.reflexion.admission, ReflexionAdmission.REFLEXION)

    def test_reflexion_last_attempt_preset(self) -> None:
        presets = ContextWindowPresets()
        algo = presets.reflexion_last_attempt
        self.assertEqual(algo.name, "reflexion_last_attempt")
        self.assertIsNotNone(algo.reflexion)
        self.assertEqual(algo.reflexion.admission, ReflexionAdmission.LAST_ATTEMPT)

    def test_reflexion_last_attempt_and_reflexion_preset(self) -> None:
        presets = ContextWindowPresets()
        algo = presets.reflexion_last_attempt_and_reflexion
        self.assertEqual(algo.name, "reflexion_last_attempt_and_reflexion")
        self.assertIsNotNone(algo.reflexion)
        self.assertEqual(
            algo.reflexion.admission,
            ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION,
        )


class PublicExportsTests(unittest.TestCase):
    def test_import_from_vidbyte(self) -> None:
        from vidbyte import ReflexionAdmission, ReflexionConfig
        self.assertIsNotNone(ReflexionAdmission)
        self.assertIsNotNone(ReflexionConfig)

    def test_import_from_vidbyte_context(self) -> None:
        from vidbyte.context import ReflexionAdmission, ReflexionConfig
        self.assertIsNotNone(ReflexionAdmission)
        self.assertIsNotNone(ReflexionConfig)

    def test_import_from_vidbyte_context_algorithms(self) -> None:
        from vidbyte.context.algorithms import (
            ReflexionAdmission,
            ReflexionConfig,
        )
        self.assertIsNotNone(ReflexionAdmission)
        self.assertIsNotNone(ReflexionConfig)


if __name__ == "__main__":
    unittest.main()
