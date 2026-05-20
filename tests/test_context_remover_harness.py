from __future__ import annotations

import unittest

from vidbyte.harnesses.context_remover import (
    ConditionalHarnessState,
    ContextRemoverConfig,
    ContextRemoverHarness,
)
from vidbyte.lib.errors import HarnessExecutionError
from vidbyte.shared import HarnessRole, LedgerEntry


class ContextRemoverHarnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_n_steps_then_purifies_before_next_step(self) -> None:
        purifier_prompts: list[str] = []

        async def purifier(prompt, *, context, tools):
            purifier_prompts.append(prompt)
            return "semantic summary"

        harness = ContextRemoverHarness(
            original_intent="keep the migration focused",
            purifier_model_fn=purifier,
            config=ContextRemoverConfig(purify_every_n_steps=3),
        )
        state = ConditionalHarnessState(original_intent="keep the migration focused")

        async def step(current_state):
            return f"step {len(current_state.history) + 1}"

        await harness.intercept_step(state, step)
        await harness.intercept_step(state, step)
        await harness.intercept_step(state, step)
        self.assertEqual(purifier_prompts, [])

        await harness.intercept_step(state, step)

        self.assertEqual(len(purifier_prompts), 1)
        self.assertEqual(state.history[0].kind, "purified_summary")
        self.assertEqual(state.baseline_context, "semantic summary")

    async def test_purifier_receives_anchor_raw_ledger_and_contract(self) -> None:
        captured_prompt = ""

        async def purifier(prompt, *, context, tools):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "summary"

        harness = ContextRemoverHarness(
            original_intent="original task",
            purifier_model_fn=purifier,
            config=ContextRemoverConfig(purify_every_n_steps=1),
        )
        state = ConditionalHarnessState(
            original_intent="original task",
            history=[LedgerEntry(role=HarnessRole.SYSTEM, kind="tool_result", content="value=42")],
        )

        result = await harness.purify(state)

        self.assertEqual(result.summary, "summary")
        self.assertIn("original task", captured_prompt)
        self.assertIn("value=42", captured_prompt)
        self.assertIn("Include core semantic facts", captured_prompt)

    async def test_retains_configured_tail_entries(self) -> None:
        async def purifier(prompt, *, context, tools):
            return "summary"

        harness = ContextRemoverHarness(
            original_intent="intent",
            purifier_model_fn=purifier,
            config=ContextRemoverConfig(retain_last_entries=1),
        )
        tail = LedgerEntry(role=HarnessRole.SYSTEM, kind="tail", content="keep")
        state = ConditionalHarnessState(
            original_intent="intent",
            history=[
                LedgerEntry(role=HarnessRole.SYSTEM, kind="old", content="drop"),
                tail,
            ],
        )

        await harness.purify(state)

        self.assertEqual([entry.kind for entry in state.history], ["purified_summary", "tail"])

    async def test_purifier_trace_is_not_appended_to_primary_history(self) -> None:
        async def purifier(prompt, *, context, tools):
            return "summary"

        harness = ContextRemoverHarness(original_intent="intent", purifier_model_fn=purifier)
        state = ConditionalHarnessState(
            original_intent="intent",
            history=[LedgerEntry(role=HarnessRole.SYSTEM, kind="raw", content="raw")],
        )

        await harness.purify(state)

        self.assertFalse(any(entry.kind == "purification_request" for entry in state.history))

    async def test_rejects_concurrent_intercept_step_calls(self) -> None:
        async def purifier(prompt, *, context, tools):
            return "summary"

        harness = ContextRemoverHarness(original_intent="intent", purifier_model_fn=purifier)
        state = ConditionalHarnessState(original_intent="intent")

        async def nested_step(current_state):
            with self.assertRaises(HarnessExecutionError):
                await harness.intercept_step(current_state, lambda state: "nested")
            return "outer"

        result = await harness.intercept_step(state, nested_step)

        self.assertEqual(result, "outer")


if __name__ == "__main__":
    unittest.main()
