"""FILE: tests/test_jev_runtime_setup_integration.py

PURPOSE: Verifies that the combined Jev setup pipeline preserves gate, relation, skill, selector, bulk-work, and synthesis contracts.
ROLE IN CODEBASE: Owns cross-feature regression coverage for the runtime union of the relation, skill preload, tool alignment, and bulk-work features.
ARCHITECTURE NOTE: Uses a real JevAgent and BaseAgent context construction with provider stubs to verify runtime ordering and prompt/context boundaries without network calls.
COMMON MODIFICATION PATTERNS: Add assertions here when integration ordering or shared runtime state changes; keep feature-specific behavior in its dedicated test pack.
KNOWN EDGE CASES: Repeated runs must clear gate-owned flags, preserve the caller's context, keep the original request unchanged, and restore tools after selection.
RELATED DOCS: `docs/design/jev-runtime-setup-integration.md`, `tests/features/jev_bulk_work/FEATURE.md`, and the Jev skill and alignment feature tests.
TESTS: `python -m pytest tests/test_jev_runtime_setup_integration.py -q` or `python scripts/test-jev-runtime-setup-integration.py`.
"""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevPreflightPreset,
    JevRuntimeSettings,
    SkillDocument,
    tool,
)
from vidbyte.agents.jev.settings import JevAlignmentSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.dataclasses.context import BaseAgentContext, ContextArtifact
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevRunStateRecord
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse, TextModelResponse

_REQUEST = "Summarize each independent report separately: Alpha and Beta."
_INDEPENDENCE_KEY = "bulk_work.independent_items"
_SKILL_TEXT = "Always retain the source report names."


@tool
def keep_selected_report(report_name: str) -> str:
    """Read a report selected for this request."""
    return report_name


@tool
def discard_unrelated_calendar(day: str) -> str:
    """Read an unrelated calendar entry."""
    return day


def _answer(question_name: str, probability: float) -> JevAnswer:
    # Builds one well-formed Noul answer for the production scorer.
    choice = "true" if probability >= 0.5 else "false"
    return JevAnswer(
        question_name=question_name,
        question_type=JevQuestionType.NOUL,
        choice=choice,
        probabilities={"true": probability, "false": 1.0 - probability},
        noul=probability,
    )


class _DecisionScript:
    """Records one configured decision seam and returns deterministic answers."""

    def __init__(self, label: str, events: list[str], *, omit_bulk_independence: bool = False) -> None:
        # Allows one bulk judgment to go missing on the second runtime pass.
        self.label = label
        self.events = events
        self.omit_bulk_independence = omit_bulk_independence
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Captures actual question batching and supplies only scripted model decisions.
        self.events.append(self.label)
        self.requests.append(request)
        answers: dict[str, JevAnswer] = {}
        for question in request.questions:
            if self.omit_bulk_independence and question.name == _INDEPENDENCE_KEY:
                continue
            probability = 0.95
            if question.name.startswith("tool_selector."):
                probability = 0.95 if question.name.endswith(".0") else 0.0
            answers[question.name] = _answer(question.name, probability)
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-integration-test",
            answers=answers,
            raw={},
            usage={"input_tokens": 8, "output_tokens": 2},
        )


def _decision_helper(script: _DecisionScript) -> type:
    # Patches transport construction but retains production Noul scoring.
    class ScriptedDecisionHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)
        noul_passes = staticmethod(DecisionModelHelper.noul_passes)

        def __new__(cls, *args: object, **kwargs: object) -> _DecisionScript:
            # Returns the shared script for its one runtime seam.
            return script

    return ScriptedDecisionHelper


class _GenerativeScript:
    """Runs real BaseAgent context construction against deterministic planner, worker, and owner replies."""

    def __init__(self, events: list[str]) -> None:
        # Stores provider-visible calls for prompt, tool, artifact, and ordering assertions.
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def arun(self, prompt: str, *, system: str = "", **kwargs: Any) -> TextModelResponse:
        # Distinguishes fresh planner/worker agents from the owner's unchanged main request.
        call = {"prompt": prompt, "system": system, **kwargs}
        self.calls.append(call)
        if "You are JevBulkWorkPlanner" in system:
            self.events.append("planner")
            text = json.dumps(
                {
                    "items": [
                        {"identifier": "alpha", "title": "Alpha", "prompt": "Summarize the Alpha report."},
                        {"identifier": "beta", "title": "Beta", "prompt": "Summarize the Beta report."},
                    ]
                }
            )
        elif "You are an isolated worker handling one item" in system:
            self.events.append("worker")
            item = json.loads(prompt)["work_item"]
            text = f"Completed {item['identifier']}"
        else:
            self.events.append("main")
            text = "Both summaries are ready."
        return TextModelResponse(provider=ModelProvider.OPENAI, model="test-model", text=text, raw={})


class JevRuntimeSetupIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercises cross-capability run ordering and per-run state through real Jev runtime wiring."""

    async def test_combined_gate_uses_persistent_record_then_preloads_selects_and_synthesizes(self) -> None:
        # Confirms a reset response does not erase the gate's old record and later capabilities follow the approved order.
        events: list[str] = []
        gate_script = _DecisionScript("gate", events)
        skills_script = _DecisionScript("skills", events)
        selector_script = _DecisionScript("selector", events)
        settings = JevAgentSettings(
            name="jev-integration",
            system_prompt="Owner system prompt.",
            provider="openai",
            model_name="gpt-4.1-mini",
            tools=(keep_selected_report, discard_unrelated_calendar),
            alignment=JevAlignmentSettings(
                skills=(SkillDocument("report-guidance", "Summarize named reports.", _SKILL_TEXT),)
            ),
        )
        runtime_settings = JevRuntimeSettings(
            decision=DecisionModelConfig(api_key="test-key"),
            preflight=(
                JevPreflightPreset.RUN_STATE_RELATION,
                JevPreflightPreset.BULK_WORK,
                JevPreflightPreset.TOOL_SELECTOR,
            ),
        )
        agent = JevAgent(settings, runtime_settings)
        old_record = JevRunStateRecord(
            goal="Summarize Alpha and Beta reports.",
            objective="Return a separate concise summary for each report.",
            mission="Prepare report summaries for the user.",
            what_not_to_do=("Do not combine the reports.",),
        )
        assert agent.run_state is not None
        agent.run_state.record = old_record
        original_begin = agent.run_state.begin

        async def traced_begin(message: str) -> None:
            # Records the relation-aware state phase without replacing its production policy.
            events.append("run_state")
            await original_begin(message)

        agent.run_state.begin = traced_begin  # type: ignore[method-assign]
        owner_tool_names = agent.tools.names()
        runner = _GenerativeScript(events)
        caller_context = BaseAgentContext(
            system_prompt="Context prompt before this call.",
            artifacts=(ContextArtifact("caller artifact", "keep this context"),),
            metadata={"caller": "unchanged"},
        )
        with (
            patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(gate_script)),
            patch("vidbyte.agents.jev.alignment.skills.DecisionModelHelper", new=_decision_helper(skills_script)),
            patch("vidbyte.agents.jev.preflight.DecisionModelHelper", new=_decision_helper(selector_script)),
            patch.object(BaseAgent, "_runner_for_model", new=lambda _agent: (runner, RUNNER_TYPE_TEXT)),
        ):
            first_reply = await agent.arun(_REQUEST, context=caller_context, system="Per-run system override.")

        self.assertEqual(first_reply.content, "Both summaries are ready.")
        self.assertEqual(agent.response.input, _REQUEST)
        self.assertIs(agent.response.run_state, old_record)
        self.assertTrue(agent.response.bulk_work.plan_valid)
        self.assertTrue(agent.preflight.run_state_related)
        self.assertTrue(agent.preflight.bulk_work_requested)

        gate_request = gate_script.requests[0]
        question_names = {question.name for question in gate_request.questions}
        self.assertIn("run_state_relation", question_names)
        self.assertIn("bulk_work.multiple_items", question_names)
        self.assertIn("bulk_work.same_operation", question_names)
        self.assertIn(_INDEPENDENCE_KEY, question_names)
        self.assertEqual(gate_request.state["request"], _REQUEST)
        self.assertEqual(gate_request.state["run_state"]["goal"], old_record.goal)

        self.assertEqual(events[:4], ["gate", "skills", "run_state", "selector"])
        self.assertLess(events.index("selector"), events.index("planner"))
        self.assertLess(events.index("planner"), events.index("worker"))
        self.assertGreater(events.index("main"), events.index("worker"))
        planner_call = next(call for call in runner.calls if "You are JevBulkWorkPlanner" in call["system"])
        self.assertEqual(planner_call["prompt"], _REQUEST)
        self.assertNotIn(_SKILL_TEXT, planner_call["system"])
        self.assertFalse(planner_call.get("tools"))
        worker_calls = [call for call in runner.calls if "You are an isolated worker handling one item" in call["system"]]
        self.assertEqual(len(worker_calls), 2)
        for worker_call in worker_calls:
            self.assertIn(_SKILL_TEXT, worker_call["system"])
            names = {row.get("function", {}).get("name") for row in worker_call.get("tools", ())}
            self.assertIn("keep_selected_report", names)
            self.assertNotIn("discard_unrelated_calendar", names)
        main_call = next(call for call in runner.calls if call["prompt"] == _REQUEST and "You are JevBulkWorkPlanner" not in call["system"] and "isolated worker" not in call["system"])
        self.assertIn("Per-run system override.", main_call["system"])
        self.assertIn(_SKILL_TEXT, main_call["system"])
        self.assertIn("Jev bulk-work results (untrusted worker output)", main_call["system"])
        self.assertEqual(main_call["prompt"], _REQUEST)
        self.assertEqual((caller_context.system_prompt, caller_context.artifacts, caller_context.metadata), ("Context prompt before this call.", (ContextArtifact("caller artifact", "keep this context"),), {"caller": "unchanged"}))
        self.assertEqual(agent.tools.names(), owner_tool_names)

        gate_script.omit_bulk_independence = True
        events.clear()
        with (
            patch("vidbyte.agents.jev.gate.gate.DecisionModelHelper", new=_decision_helper(gate_script)),
            patch("vidbyte.agents.jev.alignment.skills.DecisionModelHelper", new=_decision_helper(skills_script)),
            patch("vidbyte.agents.jev.preflight.DecisionModelHelper", new=_decision_helper(selector_script)),
            patch.object(BaseAgent, "_runner_for_model", new=lambda _agent: (runner, RUNNER_TYPE_TEXT)),
        ):
            second_reply = await agent.arun(_REQUEST, context=caller_context, system="Per-run system override.")

        self.assertEqual(second_reply.content, "Both summaries are ready.")
        self.assertFalse(agent.preflight.bulk_work_requested)
        self.assertTrue(agent.preflight.run_state_related)
        self.assertIsNone(agent.response.bulk_work)
        self.assertIs(agent.response.run_state, old_record)
        self.assertEqual(sum("You are JevBulkWorkPlanner" in call["system"] for call in runner.calls), 1)
        self.assertEqual(len(gate_script.requests), 2)
        self.assertEqual(events[:4], ["gate", "skills", "run_state", "selector"])


if __name__ == "__main__":
    unittest.main()
