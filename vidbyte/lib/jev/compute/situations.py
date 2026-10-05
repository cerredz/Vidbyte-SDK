"""FILE: vidbyte/lib/jev/compute/situations.py

PURPOSE: Defines JevComputeSituations, the fixed recognition policy of every compute situation: which sign questions it asks, the mean P(yes) they must reach, the veto any single sign can apply, and the gate sign the rest depend on.
ROLE IN CODEBASE: JevComputeRegistry reads each situation's question keys from here, and the recognizer in vidbyte/agents/jev/compute/ scores Jev's answers against each definition.
ARCHITECTURE NOTE: Mirrors JevPresets for preflight: policy values live in vidbyte/lib/constants/jev.py and each situation's definition is fixed at import, so a run never chooses its own thresholds. Situations are listed in JevComputeSituation's priority order.
COMMON MODIFICATION PATTERNS: Add a situation by adding its JevComputeSituation member, its sign questions in a new module here, and its definition below with named threshold and veto constants.
KNOWN EDGE CASES: The gate must pass on its own at the threshold, so a strong mean cannot carry a situation whose core sign is uncertain; the veto stops one clear no from being averaged away.
RELATED DOCS: docs/design/jev-compute-situations.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_EACH_OF_SEVERAL_THRESHOLD,
    JEV_COMPUTE_EACH_OF_SEVERAL_VETO,
    JEV_COMPUTE_REPEATING_THRESHOLD,
    JEV_COMPUTE_REPEATING_VETO,
    JEV_COMPUTE_SELF_CONTAINED_STEP_THRESHOLD,
    JEV_COMPUTE_SELF_CONTAINED_STEP_VETO,
)
from vidbyte.lib.dataclasses.jev import JevComputeSituationDefinition
from vidbyte.lib.enums.jev import JevComputeQuestionKey, JevComputeSituation


class JevComputeSituations:
    """The fixed recognition policy of every mid-run compute situation, in priority order."""

    _definitions: Mapping[JevComputeSituation, JevComputeSituationDefinition] = MappingProxyType(
        {
            JevComputeSituation.REPEATING: JevComputeSituationDefinition(
                situation=JevComputeSituation.REPEATING,
                question_keys=(
                    JevComputeQuestionKey.REPEATING_SAME_APPROACH,
                    JevComputeQuestionKey.REPEATING_SAME_RESULT,
                    JevComputeQuestionKey.REPEATING_NO_NEW_CAUSE,
                    JevComputeQuestionKey.REPEATING_BLOCKS_REQUEST,
                ),
                threshold=JEV_COMPUTE_REPEATING_THRESHOLD,
                # A new idea from the agent, or a problem off the requested path, is a clear reason not to interrupt.
                veto=JEV_COMPUTE_REPEATING_VETO,
                gate=JevComputeQuestionKey.REPEATING_SAME_APPROACH,
            ),
            JevComputeSituation.EACH_OF_SEVERAL: JevComputeSituationDefinition(
                situation=JevComputeSituation.EACH_OF_SEVERAL,
                question_keys=(
                    JevComputeQuestionKey.EACH_OF_SEVERAL_SAME_WORK,
                    JevComputeQuestionKey.EACH_OF_SEVERAL_INDEPENDENT,
                    JevComputeQuestionKey.EACH_OF_SEVERAL_SUBSTANTIAL,
                    JevComputeQuestionKey.EACH_OF_SEVERAL_REQUESTED,
                ),
                threshold=JEV_COMPUTE_EACH_OF_SEVERAL_THRESHOLD,
                # Items that depend on each other cannot be split, however clearly the plan names them.
                veto=JEV_COMPUTE_EACH_OF_SEVERAL_VETO,
                gate=JevComputeQuestionKey.EACH_OF_SEVERAL_SAME_WORK,
            ),
            JevComputeSituation.SELF_CONTAINED_STEP: JevComputeSituationDefinition(
                situation=JevComputeSituation.SELF_CONTAINED_STEP,
                question_keys=(
                    JevComputeQuestionKey.SELF_CONTAINED_STEP_SUBSTANTIAL,
                    JevComputeQuestionKey.SELF_CONTAINED_STEP_STATES_ALL,
                    JevComputeQuestionKey.SELF_CONTAINED_STEP_HANDS_BACK,
                    JevComputeQuestionKey.SELF_CONTAINED_STEP_REQUESTED,
                ),
                threshold=JEV_COMPUTE_SELF_CONTAINED_STEP_THRESHOLD,
                # A step that leans on the run cannot go to a helper with no memory of it.
                veto=JEV_COMPUTE_SELF_CONTAINED_STEP_VETO,
                gate=JevComputeQuestionKey.SELF_CONTAINED_STEP_SUBSTANTIAL,
            ),
        }
    )

    @classmethod
    def definition(cls, situation: JevComputeSituation) -> JevComputeSituationDefinition:
        """Return the recognition policy of one situation."""
        return cls._definitions[situation]

    @classmethod
    def all(cls) -> tuple[JevComputeSituation, ...]:
        """Return every situation, in priority order."""
        return tuple(JevComputeSituation)


__all__ = ["JevComputeSituations"]
