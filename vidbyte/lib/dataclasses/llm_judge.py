"""Context Protocol Header

Description:
    Typed config dataclasses for all 19 LLM-as-a-judge strategy grader classes.
Purpose:
    Moves constructor validation out of __init__ bodies and into __post_init__,
    providing eager, descriptive errors at config construction time.
Architecture:
    - One frozen dataclass per judge class, mirroring its constructor parameters.
    - Shared helpers: _validate_runner, _validate_threshold, _validate_non_empty_str.
    - All dataclasses use frozen=True, slots=True, consistent with lib/dataclasses convention.
Relations:
    Consumed by each class in vidbyte/evals/llm_as_a_judge/.
    References vidbyte.evals.base.BaseGrader via TYPE_CHECKING only (no circular import).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from vidbyte.evals.base import BaseGrader


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------

def _validate_runner(runner: object, field: str) -> None:
    # Raises TypeError if runner lacks arun, generate_reply, or run interface.
    if not (hasattr(runner, "arun") or hasattr(runner, "generate_reply") or hasattr(runner, "run")):
        raise TypeError(
            f"'{field}' must expose arun(), generate_reply(), or run() — "
            f"got {type(runner).__name__} which has none of these."
        )


def _validate_non_empty_str(value: str, field: str) -> None:
    # Raises ValueError if value is not a non-empty, non-whitespace string.
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field}' must be a non-empty string, got: {value!r}")


def _validate_threshold(value: float, field: str) -> None:
    # Raises ValueError if threshold is not in the (0.0, 1.0] range.
    if not isinstance(value, (int, float)) or not (0.0 < float(value) <= 1.0):
        raise ValueError(f"'{field}' must be a float in (0.0, 1.0], got: {value!r}")


# ---------------------------------------------------------------------------
# Config dataclasses — one per judge
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ChainOfThoughtJudgeConfig:
    """Config for ChainOfThoughtJudge."""

    judge_runner: object
    cot_length: Literal["short", "medium", "long"] = "medium"
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface and cot_length literal.
        _validate_runner(self.judge_runner, "judge_runner")
        if self.cot_length not in ("short", "medium", "long"):
            raise ValueError(
                f"'cot_length' must be 'short', 'medium', or 'long', got: {self.cot_length!r}"
            )


@dataclass(frozen=True, slots=True)
class BinaryJudgeConfig:
    """Config for BinaryJudge."""

    judge_runner: object
    criterion: str
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface and non-empty criterion.
        _validate_runner(self.judge_runner, "judge_runner")
        _validate_non_empty_str(self.criterion, "criterion")


@dataclass(frozen=True, slots=True)
class FewShotJudgeConfig:
    """Config for FewShotJudge."""

    judge_runner: object
    examples: tuple
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface, non-empty examples, and required keys per example.
        _validate_runner(self.judge_runner, "judge_runner")
        if not self.examples:
            raise ValueError("'examples' must be a non-empty sequence of example dicts.")
        required_keys = {"prompt", "actual", "expected", "score", "reason"}
        for i, ex in enumerate(self.examples):
            if not isinstance(ex, dict):
                raise ValueError(f"'examples[{i}]' must be a dict, got {type(ex).__name__}.")
            missing = required_keys - ex.keys()
            if missing:
                raise ValueError(
                    f"'examples[{i}]' is missing required keys: {sorted(missing)}. "
                    "Each example must have 'prompt', 'actual', 'expected', 'score', and 'reason'."
                )
            try:
                score = float(ex["score"])
            except (TypeError, ValueError):
                raise ValueError(
                    f"'examples[{i}][\"score\"]' must be castable to float, got: {ex['score']!r}"
                )
            if not (0.0 <= score <= 1.0):
                raise ValueError(
                    f"'examples[{i}][\"score\"]' must be in [0.0, 1.0], got: {score}"
                )


@dataclass(frozen=True, slots=True)
class PairwiseJudgeConfig:
    """Config for PairwiseJudge."""

    judge_runner: object
    swap_check: bool = True
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface and that swap_check is boolean.
        _validate_runner(self.judge_runner, "judge_runner")
        if not isinstance(self.swap_check, bool):
            raise ValueError(f"'swap_check' must be a bool, got: {type(self.swap_check).__name__}")


@dataclass(frozen=True, slots=True)
class SelfReferenceJudgeConfig:
    """Config for SelfReferenceJudge."""

    judge_runner: object
    num_self_generations: int = 1
    system_prompt: str | None = None
    generation_prompt_template: str | None = None
    eval_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface and that num_self_generations is >= 1.
        _validate_runner(self.judge_runner, "judge_runner")
        if not isinstance(self.num_self_generations, int) or self.num_self_generations < 1:
            raise ValueError(
                f"'num_self_generations' must be an integer >= 1, got: {self.num_self_generations!r}"
            )


@dataclass(frozen=True, slots=True)
class SelfEvalJudgeConfig:
    """Config for SelfEvalJudge."""

    judge_runner: object
    framing: Literal["third_person", "anonymous"] = "third_person"
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface and framing literal.
        _validate_runner(self.judge_runner, "judge_runner")
        if self.framing not in ("third_person", "anonymous"):
            raise ValueError(
                f"'framing' must be 'third_person' or 'anonymous', got: {self.framing!r}"
            )


@dataclass(frozen=True, slots=True)
class CriteriaDecompositionJudgeConfig:
    """Config for CriteriaDecompositionJudge."""

    judge_runner: object
    criterion: str
    num_sub_criteria: int = 4
    system_prompt: str | None = None
    decomposition_prompt_template: str | None = None
    eval_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty criterion, and num_sub_criteria >= 2.
        _validate_runner(self.judge_runner, "judge_runner")
        _validate_non_empty_str(self.criterion, "criterion")
        if not isinstance(self.num_sub_criteria, int) or self.num_sub_criteria < 2:
            raise ValueError(
                f"'num_sub_criteria' must be an integer >= 2, got: {self.num_sub_criteria!r}"
            )


@dataclass(frozen=True, slots=True)
class ChainOfAspectsJudgeConfig:
    """Config for ChainOfAspectsJudge."""

    judge_runner: object
    aspects: tuple
    words_per_aspect: int = 30
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty aspects list of non-empty strings, and words_per_aspect >= 1.
        _validate_runner(self.judge_runner, "judge_runner")
        if not self.aspects:
            raise ValueError("'aspects' must be a non-empty sequence of strings.")
        for i, asp in enumerate(self.aspects):
            if not isinstance(asp, str) or not asp.strip():
                raise ValueError(
                    f"'aspects[{i}]' must be a non-empty string, got: {asp!r}"
                )
        if not isinstance(self.words_per_aspect, int) or self.words_per_aspect < 1:
            raise ValueError(
                f"'words_per_aspect' must be an integer >= 1, got: {self.words_per_aspect!r}"
            )


@dataclass(frozen=True, slots=True)
class BranchSolveMergeJudgeConfig:
    """Config for BranchSolveMergeJudge."""

    judge_runner: object
    branches: dict
    branch_weights: dict | None = None
    merge_strategy: Literal["weighted_mean", "llm"] = "weighted_mean"
    system_prompt: str | None = None
    branch_prompt_template: str | None = None
    merge_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty branches, weight consistency, and merge_strategy.
        _validate_runner(self.judge_runner, "judge_runner")
        if not self.branches:
            raise ValueError("'branches' must be a non-empty dict.")
        for k, v in self.branches.items():
            if not isinstance(v, str) or not v.strip():
                raise ValueError(
                    f"'branches[\"{k}\"]' must be a non-empty string rubric, got: {v!r}"
                )
        if self.branch_weights is not None:
            if set(self.branch_weights.keys()) != set(self.branches.keys()):
                raise ValueError(
                    "'branch_weights' keys must exactly match 'branches' keys. "
                    f"Got weights for {sorted(self.branch_weights.keys())} "
                    f"but branches are {sorted(self.branches.keys())}."
                )
            for k, w in self.branch_weights.items():
                if not isinstance(w, (int, float)) or float(w) <= 0:
                    raise ValueError(
                        f"'branch_weights[\"{k}\"]' must be a positive number, got: {w!r}"
                    )
        if self.merge_strategy not in ("weighted_mean", "llm"):
            raise ValueError(
                f"'merge_strategy' must be 'weighted_mean' or 'llm', got: {self.merge_strategy!r}"
            )


@dataclass(frozen=True, slots=True)
class LLMRubricJudgeConfig:
    """Config for LLMRubricJudge."""

    judge_runner: object
    task_description: str
    rubric_scale: int = 5
    system_prompt: str | None = None
    rubric_generation_prompt_template: str | None = None
    eval_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty task_description, and rubric_scale >= 2.
        _validate_runner(self.judge_runner, "judge_runner")
        _validate_non_empty_str(self.task_description, "task_description")
        if not isinstance(self.rubric_scale, int) or self.rubric_scale < 2:
            raise ValueError(
                f"'rubric_scale' must be an integer >= 2, got: {self.rubric_scale!r}"
            )


@dataclass(frozen=True, slots=True)
class StructuredRubricJudgeConfig:
    """Config for StructuredRubricJudge."""

    judge_runner: object
    dimensions: dict
    weights: dict | None = None
    threshold: float = 0.7
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty dimensions with level dicts, weight consistency, threshold.
        _validate_runner(self.judge_runner, "judge_runner")
        if not self.dimensions:
            raise ValueError("'dimensions' must be a non-empty dict.")
        for dim_name, levels in self.dimensions.items():
            if not isinstance(levels, dict) or not levels:
                raise ValueError(
                    f"'dimensions[\"{dim_name}\"]' must be a non-empty dict of {{int: str}} levels."
                )
            for lvl, desc in levels.items():
                if not isinstance(lvl, int):
                    raise ValueError(
                        f"'dimensions[\"{dim_name}\"]' level keys must be integers, got: {lvl!r}"
                    )
                if not isinstance(desc, str) or not desc.strip():
                    raise ValueError(
                        f"'dimensions[\"{dim_name}\"][{lvl}]' must be a non-empty string description."
                    )
        if self.weights is not None:
            if set(self.weights.keys()) != set(self.dimensions.keys()):
                raise ValueError(
                    "'weights' keys must exactly match 'dimensions' keys. "
                    f"Got weights for {sorted(self.weights.keys())} "
                    f"but dimensions are {sorted(self.dimensions.keys())}."
                )
            for k, w in self.weights.items():
                if not isinstance(w, (int, float)) or float(w) <= 0:
                    raise ValueError(
                        f"'weights[\"{k}\"]' must be a positive number, got: {w!r}"
                    )
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class AtomicClaimsJudgeConfig:
    """Config for AtomicClaimsJudge."""

    judge_runner: object
    threshold: float = 0.8
    system_prompt: str | None = None
    decomposition_prompt_template: str | None = None
    verification_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner interface and threshold in (0, 1].
        _validate_runner(self.judge_runner, "judge_runner")
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class ConstitutionalJudgeConfig:
    """Config for ConstitutionalJudge."""

    judge_runner: object
    principles: tuple
    threshold: float = 1.0
    system_prompt: str | None = None
    check_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty principles list of non-empty strings, threshold in (0, 1].
        _validate_runner(self.judge_runner, "judge_runner")
        if not self.principles:
            raise ValueError("'principles' must be a non-empty sequence of strings.")
        for i, p in enumerate(self.principles):
            if not isinstance(p, str) or not p.strip():
                raise ValueError(
                    f"'principles[{i}]' must be a non-empty string, got: {p!r}"
                )
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class PanelJudgeConfig:
    """Config for PanelJudge."""

    judge_runners: tuple
    aggregation: Literal["mean", "median", "majority_vote"] = "mean"
    threshold: float = 0.7
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates >= 2 runners all with run interface, valid aggregation, threshold in (0, 1].
        if len(self.judge_runners) < 2:
            raise ValueError(
                f"'judge_runners' must contain at least 2 runners, got {len(self.judge_runners)}."
            )
        for i, r in enumerate(self.judge_runners):
            _validate_runner(r, f"judge_runners[{i}]")
        if self.aggregation not in ("mean", "median", "majority_vote"):
            raise ValueError(
                f"'aggregation' must be 'mean', 'median', or 'majority_vote', got: {self.aggregation!r}"
            )
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class MultiAgentRubricJudgeConfig:
    """Config for MultiAgentRubricJudge."""

    agents: tuple
    weights: tuple | None = None
    merge_strategy: Literal["weighted_mean", "llm"] = "weighted_mean"
    merge_runner: object | None = None
    threshold: float = 0.7
    system_prompt: str | None = None
    agent_prompt_template: str | None = None
    merge_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates >= 2 (runner, rubric) agent tuples, weight consistency, merge_strategy, threshold.
        if len(self.agents) < 2:
            raise ValueError(
                f"'agents' must contain at least 2 (runner, rubric) tuples, got {len(self.agents)}."
            )
        for i, agent in enumerate(self.agents):
            if not (isinstance(agent, (list, tuple)) and len(agent) == 2):
                raise ValueError(
                    f"'agents[{i}]' must be a (runner, rubric_str) tuple, got: {agent!r}"
                )
            _validate_runner(agent[0], f"agents[{i}][0]")
            if not isinstance(agent[1], str) or not agent[1].strip():
                raise ValueError(
                    f"'agents[{i}][1]' (rubric) must be a non-empty string, got: {agent[1]!r}"
                )
        if self.weights is not None:
            if len(self.weights) != len(self.agents):
                raise ValueError(
                    f"'weights' length ({len(self.weights)}) must match 'agents' length ({len(self.agents)})."
                )
            for i, w in enumerate(self.weights):
                if not isinstance(w, (int, float)) or float(w) <= 0:
                    raise ValueError(
                        f"'weights[{i}]' must be a positive number, got: {w!r}"
                    )
        if self.merge_strategy not in ("weighted_mean", "llm"):
            raise ValueError(
                f"'merge_strategy' must be 'weighted_mean' or 'llm', got: {self.merge_strategy!r}"
            )
        if self.merge_strategy == "llm" and self.merge_runner is None:
            raise ValueError(
                "'merge_runner' must be provided when merge_strategy is 'llm'."
            )
        if self.merge_runner is not None:
            _validate_runner(self.merge_runner, "merge_runner")
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class MultiAgentDebateJudgeConfig:
    """Config for MultiAgentDebateJudge."""

    judge_runners: tuple
    debate_rounds: int = 1
    require_dissent: bool = True
    threshold: float = 0.7
    system_prompt: str | None = None
    initial_prompt_template: str | None = None
    debate_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates >= 2 runners, debate_rounds >= 1, require_dissent is bool, threshold in (0, 1].
        if len(self.judge_runners) < 2:
            raise ValueError(
                f"'judge_runners' must contain at least 2 runners, got {len(self.judge_runners)}."
            )
        for i, r in enumerate(self.judge_runners):
            _validate_runner(r, f"judge_runners[{i}]")
        if not isinstance(self.debate_rounds, int) or self.debate_rounds < 1:
            raise ValueError(
                f"'debate_rounds' must be an integer >= 1, got: {self.debate_rounds!r}"
            )
        if not isinstance(self.require_dissent, bool):
            raise ValueError(
                f"'require_dissent' must be a bool, got: {type(self.require_dissent).__name__}"
            )
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class MetaJudgeConfig:
    """Config for MetaJudge."""

    primary_judge: "BaseGrader"
    meta_runner: object
    filter_on_fail: bool = True
    system_prompt: str | None = None
    meta_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates primary_judge is a BaseGrader and meta_runner has run interface.
        from vidbyte.evals.base import BaseGrader
        if not isinstance(self.primary_judge, BaseGrader):
            raise TypeError(
                f"'primary_judge' must be a BaseGrader instance, got: {type(self.primary_judge).__name__}"
            )
        _validate_runner(self.meta_runner, "meta_runner")
        if not isinstance(self.filter_on_fail, bool):
            raise ValueError(
                f"'filter_on_fail' must be a bool, got: {type(self.filter_on_fail).__name__}"
            )


@dataclass(frozen=True, slots=True)
class PeerReviewJudgeConfig:
    """Config for PeerReviewJudge."""

    judge_runners: tuple
    confidence_threshold: float = 0.5
    threshold: float = 0.7
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates >= 2 runners, confidence_threshold in [0, 1] and threshold in (0, 1].
        if len(self.judge_runners) < 2:
            raise ValueError(
                f"'judge_runners' must contain at least 2 runners, got {len(self.judge_runners)}."
            )
        for i, r in enumerate(self.judge_runners):
            _validate_runner(r, f"judge_runners[{i}]")
        if not isinstance(self.confidence_threshold, float) or not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError(
                f"'confidence_threshold' must be a float in [0.0, 1.0], got: {self.confidence_threshold!r}"
            )
        _validate_threshold(self.threshold, "threshold")


@dataclass(frozen=True, slots=True)
class MixtureOfPromptsJudgeConfig:
    """Config for MixtureOfPromptsJudge."""

    judge_runner: object
    prompt_library: dict
    router_runner: object | None = None
    router_fn: Callable[[str], str] | None = None
    fallback_key: str | None = None
    system_prompt: str | None = None
    router_prompt_template: str | None = None

    def __post_init__(self) -> None:
        # Validates runner, non-empty prompt_library, fallback_key in library, mutual exclusivity of routing options.
        _validate_runner(self.judge_runner, "judge_runner")
        if not self.prompt_library:
            raise ValueError("'prompt_library' must be a non-empty dict of {task_type: template_str}.")
        for k, v in self.prompt_library.items():
            if not isinstance(v, str) or not v.strip():
                raise ValueError(
                    f"'prompt_library[\"{k}\"]' must be a non-empty string template, got: {v!r}"
                )
        if self.fallback_key is not None and self.fallback_key not in self.prompt_library:
            raise ValueError(
                f"'fallback_key' ({self.fallback_key!r}) must be a key in 'prompt_library'. "
                f"Available keys: {sorted(self.prompt_library.keys())}"
            )
        if self.router_runner is not None and self.router_fn is not None:
            raise ValueError(
                "Provide at most one of 'router_runner' or 'router_fn', not both."
            )
        if self.router_runner is not None:
            _validate_runner(self.router_runner, "router_runner")


__all__ = [
    "AtomicClaimsJudgeConfig",
    "BinaryJudgeConfig",
    "BranchSolveMergeJudgeConfig",
    "ChainOfAspectsJudgeConfig",
    "ChainOfThoughtJudgeConfig",
    "ConstitutionalJudgeConfig",
    "CriteriaDecompositionJudgeConfig",
    "FewShotJudgeConfig",
    "LLMRubricJudgeConfig",
    "MetaJudgeConfig",
    "MixtureOfPromptsJudgeConfig",
    "MultiAgentDebateJudgeConfig",
    "MultiAgentRubricJudgeConfig",
    "PairwiseJudgeConfig",
    "PanelJudgeConfig",
    "PeerReviewJudgeConfig",
    "SelfEvalJudgeConfig",
    "SelfReferenceJudgeConfig",
    "StructuredRubricJudgeConfig",
]
