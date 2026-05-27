"""Context Protocol Header

Description:
    Unit tests for all 19 LLM-as-a-judge strategy graders.
Purpose:
    Validates construction, grading logic, edge cases, hidden failure modes,
    and silent failures for every strategy in vidbyte/evals/llm_as_a_judge/.
Architecture:
    - AsyncMockRunner: Async mock returning pre-configured strings.
    - LlmAsAJudgeTests: IsolatedAsyncioTestCase covering all 19 strategies.
Relations:
    Validates code in vidbyte/evals/llm_as_a_judge/ and runs under
    scripts/test-llm-as-a-judge.py.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from vidbyte.evals.llm_as_a_judge import (
    AtomicClaimsJudge,
    BinaryJudge,
    BranchSolveMergeJudge,
    ChainOfAspectsJudge,
    ChainOfThoughtJudge,
    ConstitutionalJudge,
    CriteriaDecompositionJudge,
    FewShotJudge,
    LLMRubricJudge,
    MetaJudge,
    MixtureOfPromptsJudge,
    MultiAgentDebateJudge,
    MultiAgentRubricJudge,
    PairwiseJudge,
    PanelJudge,
    PeerReviewJudge,
    SelfEvalJudge,
    SelfReferenceJudge,
    StructuredRubricJudge,
)
from vidbyte.evals.types import EvalCase, GraderResult


def _make_case(prompt: str = "What is 2+2?", expected: str | None = "4", metadata: dict | None = None) -> EvalCase:
    return EvalCase(prompt=prompt, expected=expected, tags=[], grader=None, metadata=metadata or {})


class AsyncMockRunner:
    """Async mock runner returning pre-set response strings."""

    def __init__(self, *responses: str) -> None:
        # Cycles through responses in order; repeats last response indefinitely.
        self._responses = list(responses)
        self._idx = 0
        self.calls: list[str] = []

    async def arun(self, prompt: str, **kwargs: Any) -> str:
        # Records the prompt and returns the next configured response.
        self.calls.append(prompt)
        if self._idx < len(self._responses):
            response = self._responses[self._idx]
            self._idx += 1
        else:
            response = self._responses[-1]
        return response


def _json_resp(score: float = 0.9, passed: bool = True, reason: str = "ok") -> str:
    return json.dumps({"score": score, "passed": passed, "reason": reason})


class LlmAsAJudgeTests(unittest.IsolatedAsyncioTestCase):
    """Comprehensive tests for all 19 LLM-as-a-judge strategy graders."""

    # --- ChainOfThoughtJudge ---

    async def test_cot_judge_score_line_parse(self) -> None:
        """Parses trailing Score: line correctly from CoT response."""
        runner = AsyncMockRunner("The response is excellent.\n\nScore: 0.85")
        judge = ChainOfThoughtJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.85)
        self.assertTrue(result.passed)

    async def test_cot_judge_json_fallback(self) -> None:
        """Falls back to JSON block parse when no Score line present."""
        runner = AsyncMockRunner(_json_resp(0.6, False))
        judge = ChainOfThoughtJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.6)
        self.assertFalse(result.passed)

    async def test_cot_judge_unparseable_returns_zero(self) -> None:
        """Returns score=0.0 and passed=False when response cannot be parsed."""
        runner = AsyncMockRunner("garbage")
        judge = ChainOfThoughtJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "Four")
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.passed)

    async def test_cot_judge_score_clamped_to_range(self) -> None:
        """Clamps scores outside [0, 1] to [0, 1]."""
        runner = AsyncMockRunner("Score: 2.5")
        judge = ChainOfThoughtJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "Four")
        self.assertEqual(result.score, 1.0)

    # --- BinaryJudge ---

    async def test_binary_judge_yes_keyword(self) -> None:
        """Detects 'yes' keyword in response to return passed=True."""
        runner = AsyncMockRunner("yes, the criterion is met")
        judge = BinaryJudge(judge_runner=runner, criterion="Is the answer correct?")
        result = await judge.agrade(_make_case(), "Four")
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)

    async def test_binary_judge_no_keyword(self) -> None:
        """Detects 'no' keyword to return passed=False."""
        runner = AsyncMockRunner("no, it is incorrect")
        judge = BinaryJudge(judge_runner=runner, criterion="Is the answer correct?")
        result = await judge.agrade(_make_case(), "Five")
        self.assertFalse(result.passed)
        self.assertEqual(result.score, 0.0)

    async def test_binary_judge_json_fallback(self) -> None:
        """Falls back to JSON {"passed": bool} when no keyword in first 100 chars."""
        runner = AsyncMockRunner(json.dumps({"passed": True, "reason": "correct"}))
        judge = BinaryJudge(judge_runner=runner, criterion="Is the answer correct?")
        result = await judge.agrade(_make_case(), "Four")
        self.assertTrue(result.passed)

    def test_binary_judge_empty_criterion_raises(self) -> None:
        """Raises ValueError when criterion is empty."""
        with self.assertRaises(ValueError):
            BinaryJudge(judge_runner=AsyncMockRunner("yes"), criterion="")

    def test_binary_judge_whitespace_criterion_raises(self) -> None:
        """Raises ValueError when criterion is only whitespace."""
        with self.assertRaises(ValueError):
            BinaryJudge(judge_runner=AsyncMockRunner("yes"), criterion="   ")

    # --- FewShotJudge ---

    async def test_few_shot_judge_grading(self) -> None:
        """Grades correctly using few-shot examples."""
        runner = AsyncMockRunner(_json_resp(0.8))
        examples = [{"prompt": "p", "actual": "a", "expected": "e", "score": 1.0, "reason": "perfect"}]
        judge = FewShotJudge(judge_runner=runner, examples=examples)
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.8)

    def test_few_shot_judge_empty_examples_raises(self) -> None:
        """Raises ValueError when examples list is empty."""
        with self.assertRaises(ValueError):
            FewShotJudge(judge_runner=AsyncMockRunner("x"), examples=[])

    def test_few_shot_judge_missing_key_raises(self) -> None:
        """Raises ValueError when an example is missing required keys."""
        with self.assertRaises(ValueError):
            FewShotJudge(judge_runner=AsyncMockRunner("x"), examples=[{"prompt": "p"}])

    # --- PairwiseJudge ---

    async def test_pairwise_judge_a_wins_both_orderings(self) -> None:
        """Returns score=1.0 when actual wins both orderings."""
        runner = AsyncMockRunner(
            json.dumps({"winner": "A", "reason": "A is better"}),
            json.dumps({"winner": "B", "reason": "B is better"}),
        )
        judge = PairwiseJudge(judge_runner=runner, swap_check=True)
        case = _make_case(metadata={"response_b": "Five"})
        result = await judge.agrade(case, "Four")
        self.assertEqual(result.score, 1.0)
        self.assertTrue(result.passed)

    async def test_pairwise_judge_disagreement_is_tie(self) -> None:
        """Returns score=0.5 when swap check disagrees."""
        runner = AsyncMockRunner(
            json.dumps({"winner": "A", "reason": "A wins"}),
            json.dumps({"winner": "A", "reason": "A wins again"}),
        )
        judge = PairwiseJudge(judge_runner=runner, swap_check=True)
        case = _make_case(metadata={"response_b": "Five"})
        result = await judge.agrade(case, "Four")
        self.assertEqual(result.score, 0.5)

    async def test_pairwise_judge_missing_response_b_raises(self) -> None:
        """Raises ValueError when response_b not in case.metadata."""
        judge = PairwiseJudge(judge_runner=AsyncMockRunner("x"), swap_check=False)
        with self.assertRaises(ValueError):
            await judge.agrade(_make_case(), "Four")

    async def test_pairwise_judge_no_swap(self) -> None:
        """Returns result without swap check when swap_check=False."""
        runner = AsyncMockRunner(json.dumps({"winner": "A", "reason": "A wins"}))
        judge = PairwiseJudge(judge_runner=runner, swap_check=False)
        case = _make_case(metadata={"response_b": "Five"})
        result = await judge.agrade(case, "Four")
        self.assertEqual(result.score, 1.0)

    # --- SelfReferenceJudge ---

    async def test_self_reference_judge_happy_path(self) -> None:
        """Generates reference and evaluates correctly."""
        runner = AsyncMockRunner("My reference answer.", _json_resp(0.9))
        judge = SelfReferenceJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.9)

    async def test_self_reference_judge_multiple_generations(self) -> None:
        """Uses first generation as reference when num_self_generations=2."""
        runner = AsyncMockRunner("First ref.", "Second ref.", _json_resp(0.7))
        judge = SelfReferenceJudge(judge_runner=runner, num_self_generations=2)
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.7)

    # --- CriteriaDecompositionJudge ---

    async def test_criteria_decomp_happy_path(self) -> None:
        """Decomposes criterion and evaluates response correctly."""
        runner = AsyncMockRunner(
            "1. Is it accurate?\n2. Is it clear?",
            _json_resp(0.85),
        )
        judge = CriteriaDecompositionJudge(judge_runner=runner, criterion="Quality")
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.85)

    # --- ChainOfAspectsJudge ---

    async def test_chain_of_aspects_happy_path(self) -> None:
        """Scores each aspect and computes mean when overall absent."""
        runner = AsyncMockRunner(json.dumps({
            "scores": {"accuracy": 0.9, "clarity": 0.8},
            "reasons": {"accuracy": "correct", "clarity": "clear"},
        }))
        judge = ChainOfAspectsJudge(judge_runner=runner, aspects=["accuracy", "clarity"])
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.85)

    async def test_chain_of_aspects_overall_provided(self) -> None:
        """Uses explicit overall score when present in JSON."""
        runner = AsyncMockRunner(json.dumps({
            "scores": {"accuracy": 0.9},
            "reasons": {"accuracy": "fine"},
            "overall": 0.75,
        }))
        judge = ChainOfAspectsJudge(judge_runner=runner, aspects=["accuracy"])
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.75)

    def test_chain_of_aspects_empty_list_raises(self) -> None:
        """Raises ValueError when aspects is empty."""
        with self.assertRaises(ValueError):
            ChainOfAspectsJudge(judge_runner=AsyncMockRunner("x"), aspects=[])

    # --- BranchSolveMergeJudge ---

    async def test_bsm_weighted_mean_merge(self) -> None:
        """Correctly computes weighted mean over two equal branches."""
        runner = AsyncMockRunner(
            json.dumps({"score": 0.8, "reason": "good"}),
            json.dumps({"score": 0.6, "reason": "ok"}),
        )
        judge = BranchSolveMergeJudge(
            judge_runner=runner,
            branches={"factual": "Is it accurate?", "clarity": "Is it clear?"},
        )
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.7)

    async def test_bsm_llm_merge(self) -> None:
        """Uses LLM merge call when merge_strategy='llm'."""
        runner = AsyncMockRunner(
            json.dumps({"score": 0.8, "reason": "branch1"}),
            json.dumps({"score": 0.6, "reason": "branch2"}),
            json.dumps({"score": 0.75, "reason": "merged"}),
        )
        judge = BranchSolveMergeJudge(
            judge_runner=runner,
            branches={"a": "rubric_a", "b": "rubric_b"},
            merge_strategy="llm",
        )
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.75)

    # --- LLMRubricJudge ---

    async def test_llm_rubric_generates_rubric_once(self) -> None:
        """Generates rubric on first call and uses cache on second."""
        runner = AsyncMockRunner(
            "Level 1: Poor. Level 2: OK. Level 3: Good.",
            _json_resp(0.8),
            _json_resp(0.9),
        )
        judge = LLMRubricJudge(judge_runner=runner, task_description="Answer questions")
        result1 = await judge.agrade(_make_case(), "Four")
        result2 = await judge.agrade(_make_case(), "Four")
        self.assertEqual(len(runner.calls), 3)
        self.assertAlmostEqual(result1.score, 0.8)
        self.assertAlmostEqual(result2.score, 0.9)

    # --- StructuredRubricJudge ---

    async def test_structured_rubric_normalises_scores(self) -> None:
        """Normalises integer level scores to 0-1 range."""
        runner = AsyncMockRunner(json.dumps({
            "scores": {"accuracy": 4, "clarity": 2},
            "reasons": {"accuracy": "good", "clarity": "ok"},
        }))
        judge = StructuredRubricJudge(
            judge_runner=runner,
            dimensions={"accuracy": {1: "bad", 2: "ok", 3: "good", 4: "great", 5: "perfect"}, "clarity": {1: "unclear", 2: "ok", 3: "clear"}},
        )
        result = await judge.agrade(_make_case(), "Four")
        expected = (4 / 5 + 2 / 3) / 2
        self.assertAlmostEqual(result.score, expected, places=5)

    # --- AtomicClaimsJudge ---

    async def test_atomic_claims_all_verified(self) -> None:
        """Returns score=1.0 when all claims verified."""
        runner = AsyncMockRunner(
            json.dumps({"claims": ["The sky is blue.", "Water is wet."]}),
            json.dumps({"verified": True, "reason": "correct"}),
            json.dumps({"verified": True, "reason": "correct"}),
        )
        judge = AtomicClaimsJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "The sky is blue. Water is wet.")
        self.assertEqual(result.score, 1.0)
        self.assertTrue(result.passed)

    async def test_atomic_claims_half_verified(self) -> None:
        """Returns score=0.5 when half claims verified."""
        runner = AsyncMockRunner(
            json.dumps({"claims": ["True claim.", "False claim."]}),
            json.dumps({"verified": True, "reason": "ok"}),
            json.dumps({"verified": False, "reason": "wrong"}),
        )
        judge = AtomicClaimsJudge(judge_runner=runner, threshold=0.8)
        result = await judge.agrade(_make_case(), "True claim. False claim.")
        self.assertAlmostEqual(result.score, 0.5)
        self.assertFalse(result.passed)

    async def test_atomic_claims_empty_response_scores_one(self) -> None:
        """Returns score=1.0 when no claims found in response."""
        runner = AsyncMockRunner(json.dumps({"claims": []}))
        judge = AtomicClaimsJudge(judge_runner=runner)
        result = await judge.agrade(_make_case(), "")
        self.assertEqual(result.score, 1.0)
        self.assertTrue(result.passed)

    # --- ConstitutionalJudge ---

    async def test_constitutional_all_satisfied(self) -> None:
        """Returns score=1.0 when no principles violated."""
        runner = AsyncMockRunner(
            json.dumps({"violated": False, "reason": "fine"}),
            json.dumps({"violated": False, "reason": "fine"}),
        )
        judge = ConstitutionalJudge(judge_runner=runner, principles=["Be helpful.", "Be safe."])
        result = await judge.agrade(_make_case(), "Four")
        self.assertEqual(result.score, 1.0)

    async def test_constitutional_one_violation(self) -> None:
        """Returns score=0.5 when one of two principles violated."""
        runner = AsyncMockRunner(
            json.dumps({"violated": True, "reason": "harmful"}),
            json.dumps({"violated": False, "reason": "fine"}),
        )
        judge = ConstitutionalJudge(judge_runner=runner, principles=["Principle A", "Principle B"], threshold=1.0)
        result = await judge.agrade(_make_case(), "Some response")
        self.assertAlmostEqual(result.score, 0.5)
        self.assertFalse(result.passed)

    def test_constitutional_empty_principles_raises(self) -> None:
        """Raises ValueError when principles is empty."""
        with self.assertRaises(ValueError):
            ConstitutionalJudge(judge_runner=AsyncMockRunner("x"), principles=[])

    # --- PanelJudge ---

    async def test_panel_mean_aggregation(self) -> None:
        """Correctly computes mean of panel scores."""
        runners = [AsyncMockRunner(_json_resp(0.8)), AsyncMockRunner(_json_resp(0.6))]
        judge = PanelJudge(judge_runners=runners, aggregation="mean")
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.7)

    async def test_panel_majority_vote(self) -> None:
        """Majority vote passes when >50% pass."""
        runners = [
            AsyncMockRunner(_json_resp(0.9, True)),
            AsyncMockRunner(_json_resp(0.3, False)),
            AsyncMockRunner(_json_resp(0.8, True)),
        ]
        judge = PanelJudge(judge_runners=runners, aggregation="majority_vote", threshold=0.7)
        result = await judge.agrade(_make_case(), "Four")
        self.assertTrue(result.passed)

    def test_panel_requires_two_runners(self) -> None:
        """Raises ValueError when fewer than 2 runners provided."""
        with self.assertRaises(ValueError):
            PanelJudge(judge_runners=[AsyncMockRunner("x")])

    # --- MultiAgentRubricJudge ---

    async def test_multi_agent_rubric_weighted_mean(self) -> None:
        """Computes correct weighted mean across two agents."""
        agents = [
            (AsyncMockRunner(json.dumps({"score": 0.9, "reason": "ok"})), "rubric1"),
            (AsyncMockRunner(json.dumps({"score": 0.7, "reason": "ok"})), "rubric2"),
        ]
        judge = MultiAgentRubricJudge(agents=agents, weights=[2.0, 1.0])
        result = await judge.agrade(_make_case(), "Four")
        expected = (0.9 * 2 + 0.7 * 1) / 3
        self.assertAlmostEqual(result.score, expected, places=5)

    def test_multi_agent_rubric_requires_two_agents(self) -> None:
        """Raises ValueError when fewer than 2 agents provided."""
        with self.assertRaises(ValueError):
            MultiAgentRubricJudge(agents=[(AsyncMockRunner("x"), "r1")])

    def test_multi_agent_rubric_llm_merge_without_runner_raises(self) -> None:
        """Raises ValueError when merge_strategy='llm' without merge_runner."""
        with self.assertRaises(ValueError):
            MultiAgentRubricJudge(
                agents=[(AsyncMockRunner("x"), "r1"), (AsyncMockRunner("x"), "r2")],
                merge_strategy="llm",
            )

    # --- MultiAgentDebateJudge ---

    async def test_debate_majority_pass(self) -> None:
        """Returns passed=True when majority of judges pass."""
        runners = [
            AsyncMockRunner(
                json.dumps({"score": 0.9, "passed": True, "reason": "ok"}),
                json.dumps({"score": 0.9, "passed": True, "reason": "maintained"}),
            ),
            AsyncMockRunner(
                json.dumps({"score": 0.3, "passed": False, "reason": "bad"}),
                json.dumps({"score": 0.8, "passed": True, "reason": "revised"}),
            ),
        ]
        judge = MultiAgentDebateJudge(judge_runners=runners, debate_rounds=1, threshold=0.7)
        result = await judge.agrade(_make_case(), "Four")
        self.assertTrue(result.passed)

    def test_debate_requires_two_runners(self) -> None:
        """Raises ValueError when fewer than 2 runners provided."""
        with self.assertRaises(ValueError):
            MultiAgentDebateJudge(judge_runners=[AsyncMockRunner("x")])

    def test_debate_requires_positive_rounds(self) -> None:
        """Raises ValueError when debate_rounds < 1."""
        with self.assertRaises(ValueError):
            MultiAgentDebateJudge(
                judge_runners=[AsyncMockRunner("x"), AsyncMockRunner("y")],
                debate_rounds=0,
            )

    # --- MetaJudge ---

    async def test_meta_judge_quality_ok_passes_through(self) -> None:
        """Returns primary result unchanged when meta judge approves."""
        from vidbyte.evals.llm_as_a_judge.binary import BinaryJudge as _B

        primary_runner = AsyncMockRunner(_json_resp(0.8))
        meta_runner = AsyncMockRunner(json.dumps({"quality_ok": True, "quality_reason": "coherent"}))
        primary = BinaryJudge(judge_runner=primary_runner, criterion="Is it correct?")
        judge = MetaJudge(primary_judge=primary, meta_runner=meta_runner)
        result = await judge.agrade(_make_case(), "Four")
        self.assertTrue(result.passed)

    async def test_meta_judge_filter_on_fail(self) -> None:
        """Returns score=0.0 when meta flags primary and filter_on_fail=True."""
        primary_runner = AsyncMockRunner(_json_resp(0.9, True))
        meta_runner = AsyncMockRunner(json.dumps({"quality_ok": False, "quality_reason": "incoherent"}))
        primary = ChainOfThoughtJudge(judge_runner=primary_runner)
        judge = MetaJudge(primary_judge=primary, meta_runner=meta_runner, filter_on_fail=True)
        result = await judge.agrade(_make_case(), "Four")
        self.assertEqual(result.score, 0.0)
        self.assertFalse(result.passed)

    async def test_meta_judge_no_filter_preserves_score(self) -> None:
        """Preserves primary score but flags reason when filter_on_fail=False."""
        primary_runner = AsyncMockRunner(_json_resp(0.9, True))
        meta_runner = AsyncMockRunner(json.dumps({"quality_ok": False, "quality_reason": "incoherent"}))
        primary = ChainOfThoughtJudge(judge_runner=primary_runner)
        judge = MetaJudge(primary_judge=primary, meta_runner=meta_runner, filter_on_fail=False)
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.9)
        self.assertIn("[Meta-judge flagged]", result.reason)

    # --- PeerReviewJudge ---

    async def test_peer_review_confidence_weighted(self) -> None:
        """Correctly computes confidence-weighted average."""
        runners = [
            AsyncMockRunner(json.dumps({"score": 0.9, "passed": True, "confidence": 0.8, "reason": "sure"})),
            AsyncMockRunner(json.dumps({"score": 0.5, "passed": False, "confidence": 0.2, "reason": "uncertain"})),
        ]
        judge = PeerReviewJudge(judge_runners=runners, confidence_threshold=0.0, threshold=0.7)
        result = await judge.agrade(_make_case(), "Four")
        expected = (0.9 * 0.8 + 0.5 * 0.2) / (0.8 + 0.2)
        self.assertAlmostEqual(result.score, expected, places=5)

    async def test_peer_review_all_filtered_falls_back(self) -> None:
        """Falls back to all reviews when none meet confidence threshold."""
        runners = [
            AsyncMockRunner(json.dumps({"score": 0.8, "passed": True, "confidence": 0.3, "reason": "ok"})),
            AsyncMockRunner(json.dumps({"score": 0.6, "passed": False, "confidence": 0.2, "reason": "ok"})),
        ]
        judge = PeerReviewJudge(judge_runners=runners, confidence_threshold=0.9, threshold=0.7)
        result = await judge.agrade(_make_case(), "Four")
        self.assertGreater(result.score, 0.0)

    def test_peer_review_requires_two_runners(self) -> None:
        """Raises ValueError when fewer than 2 runners provided."""
        with self.assertRaises(ValueError):
            PeerReviewJudge(judge_runners=[AsyncMockRunner("x")])

    # --- MixtureOfPromptsJudge ---

    async def test_mop_router_fn_selects_key(self) -> None:
        """Uses router_fn to select correct prompt template."""
        runner = AsyncMockRunner(_json_resp(0.9))
        judge = MixtureOfPromptsJudge(
            judge_runner=runner,
            prompt_library={"qa": "QA template: {prompt}\n{actual}\n{expected}", "creative": "Creative: {prompt}\n{actual}\n{expected}"},
            router_fn=lambda p: "qa",
        )
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.9)

    async def test_mop_fallback_key_used_when_no_router(self) -> None:
        """Uses fallback_key when no router_fn or router_runner provided."""
        runner = AsyncMockRunner(_json_resp(0.7))
        judge = MixtureOfPromptsJudge(
            judge_runner=runner,
            prompt_library={"qa": "QA: {prompt}\n{actual}\n{expected}"},
            fallback_key="qa",
        )
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.7)

    def test_mop_empty_library_raises(self) -> None:
        """Raises ValueError when prompt_library is empty."""
        with self.assertRaises(ValueError):
            MixtureOfPromptsJudge(judge_runner=AsyncMockRunner("x"), prompt_library={})

    async def test_mop_missing_key_no_fallback_raises(self) -> None:
        """Raises KeyError when selected key missing and no fallback_key."""
        runner = AsyncMockRunner(_json_resp(0.5))
        judge = MixtureOfPromptsJudge(
            judge_runner=runner,
            prompt_library={"qa": "{prompt}\n{actual}\n{expected}"},
            router_fn=lambda p: "nonexistent",
        )
        with self.assertRaises(KeyError):
            await judge.agrade(_make_case(), "Four")

    # --- SelfEvalJudge ---

    async def test_self_eval_third_person_framing(self) -> None:
        """Uses third-person framing header and grades correctly."""
        runner = AsyncMockRunner(_json_resp(0.85))
        judge = SelfEvalJudge(judge_runner=runner, framing="third_person")
        result = await judge.agrade(_make_case(), "Four")
        self.assertAlmostEqual(result.score, 0.85)
        self.assertIn("another assistant", runner.calls[0])

    async def test_self_eval_anonymous_framing(self) -> None:
        """Uses anonymous framing header in prompt."""
        runner = AsyncMockRunner(_json_resp(0.7, False))
        judge = SelfEvalJudge(judge_runner=runner, framing="anonymous")
        result = await judge.agrade(_make_case(), "Four")
        self.assertIn("an AI assistant", runner.calls[0])

    # --- Prompt catalog integration ---

    def test_all_19_classes_importable(self) -> None:
        """All 19 strategy classes are importable from the package."""
        classes = [
            AtomicClaimsJudge, BinaryJudge, BranchSolveMergeJudge,
            ChainOfAspectsJudge, ChainOfThoughtJudge, ConstitutionalJudge,
            CriteriaDecompositionJudge, FewShotJudge, LLMRubricJudge,
            MetaJudge, MixtureOfPromptsJudge, MultiAgentDebateJudge,
            MultiAgentRubricJudge, PairwiseJudge, PanelJudge,
            PeerReviewJudge, SelfEvalJudge, SelfReferenceJudge,
            StructuredRubricJudge,
        ]
        self.assertEqual(len(classes), 19)
        for cls in classes:
            self.assertTrue(callable(cls))

    def test_all_classes_have_name_attr(self) -> None:
        """All strategy classes define a ClassVar 'name' attribute."""
        classes_and_names = [
            (AtomicClaimsJudge, "atomic_claims"),
            (BinaryJudge, "binary"),
            (BranchSolveMergeJudge, "branch_solve_merge"),
            (ChainOfAspectsJudge, "chain_of_aspects"),
            (ChainOfThoughtJudge, "chain_of_thought"),
            (ConstitutionalJudge, "constitutional"),
            (CriteriaDecompositionJudge, "criteria_decomposition"),
            (FewShotJudge, "few_shot"),
            (LLMRubricJudge, "llm_rubric"),
            (MetaJudge, "meta_judge"),
            (MixtureOfPromptsJudge, "mixture_of_prompts"),
            (MultiAgentDebateJudge, "multi_agent_debate"),
            (MultiAgentRubricJudge, "multi_agent_rubric"),
            (PairwiseJudge, "pairwise"),
            (PanelJudge, "panel"),
            (PeerReviewJudge, "peer_review"),
            (SelfEvalJudge, "self_eval"),
            (SelfReferenceJudge, "self_reference"),
            (StructuredRubricJudge, "structured_rubric"),
        ]
        for cls, expected_name in classes_and_names:
            self.assertEqual(cls.name, expected_name)

    def test_prompt_catalog_loads_llm_as_a_judge_family(self) -> None:
        """Prompt catalog successfully loads the llm_as_a_judge family."""
        from vidbyte.prompts.catalog import Prompts
        prompts = Prompts()
        family = prompts.family("llm_as_a_judge")
        self.assertIn("chain_of_thought_user", family)
        self.assertIn("binary_user", family)
        self.assertIn("self_eval_user", family)
        self.assertEqual(len(family), 26)

    def test_enum_members_exist(self) -> None:
        """All 26 LLM_AS_A_JUDGE enum members are present in Prompt."""
        from vidbyte.lib.enums.prompts import Prompt
        expected_values = [
            "llm_as_a_judge.chain_of_thought_user",
            "llm_as_a_judge.binary_user",
            "llm_as_a_judge.few_shot_user",
            "llm_as_a_judge.pairwise_user",
            "llm_as_a_judge.self_reference_generation",
            "llm_as_a_judge.self_reference_eval",
            "llm_as_a_judge.criteria_decomposition_decompose",
            "llm_as_a_judge.criteria_decomposition_eval",
            "llm_as_a_judge.chain_of_aspects_user",
            "llm_as_a_judge.branch_solve_merge_branch",
            "llm_as_a_judge.branch_solve_merge_merge",
            "llm_as_a_judge.llm_rubric_generate",
            "llm_as_a_judge.llm_rubric_eval",
            "llm_as_a_judge.structured_rubric_user",
            "llm_as_a_judge.atomic_claims_decompose",
            "llm_as_a_judge.atomic_claims_verify",
            "llm_as_a_judge.constitutional_check",
            "llm_as_a_judge.panel_user",
            "llm_as_a_judge.multi_agent_rubric_agent",
            "llm_as_a_judge.multi_agent_rubric_merge",
            "llm_as_a_judge.multi_agent_debate_initial",
            "llm_as_a_judge.multi_agent_debate_round",
            "llm_as_a_judge.meta_judge_user",
            "llm_as_a_judge.peer_review_user",
            "llm_as_a_judge.mixture_of_prompts_router",
            "llm_as_a_judge.self_eval_user",
        ]
        prompt_values = {p.value for p in Prompt}
        for v in expected_values:
            self.assertIn(v, prompt_values, f"Missing Prompt enum value: {v}")


if __name__ == "__main__":
    unittest.main()
