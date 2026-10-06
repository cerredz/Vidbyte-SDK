"""FILE: tests/test_codex_agent_input_bridge.py

PURPOSE:
    Feature tests for the Codex agent input bridge: CodexVidbyteTranslator's
    translate_input() conversion of str/AgentInput/CodexRunInput, and
    CodexHarnessAgent's widened arun()/run() entry points, plus
    CodexContextTranslator's translation of ContextManager.metadata onto the
    turn. Locks the behavior docs/design/codex-agent-input-bridge.md specifies:
    lossless field mapping, identity passthrough for native requests,
    context-manager identity preservation, manager metadata reaching the turn
    under per-turn overrides, classified translation failures, and zero
    transport calls plus zero facade mutation when an input is rejected.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/config.py (CodexVidbyteTranslator),
    vidbyte/agents/codex/agent.py (CodexHarnessAgent),
    vidbyte/agents/codex/context.py (CodexContextTranslator), and the
    CodexAgentInput alias in vidbyte/lib/dataclasses/codex.py. These are the
    first committed tests for the Codex adapter package.

ARCHITECTURE NOTE:
    Every test runs offline. The bridge executes entirely before
    CodexTransport._load_sdk, so the optional openai-codex extra is never
    imported. Integration tests replace only the transport with
    _RecordingTransport and keep every translator real, because the point is
    to prove the seams line up rather than to restate the unit assertions.

FUNCTION INVENTORY:
    No production functions. _build_agent() constructs a CodexHarnessAgent
    with a recording fake transport; _run_result() builds one completed
    CodexRunResult snapshot. See the ARCHITECTURE NOTE for the class layout.

COMMON MODIFICATION PATTERNS:
    Add a branch to translate_input(), then add its conversion test to
    TranslateInputTests and its failure test to
    CodexHarnessAgentInputBoundaryTests. Translate a further ContextManager
    surface and add its test to ContextManagerMetadataTranslationTests, or to a
    sibling class named for that surface.

WHAT NOT TO DO IN THIS FILE:
    Do not import openai_codex, do not construct a real CodexTransport, and
    do not assert on equality where the design requires object identity.

KNOWN EDGE CASES:
    An empty prompt is rejected by CodexTextInput, not by the bridge, so the
    raised type is ConfigurationError at the translator boundary and
    CodexAgentError once it crosses the agent.

RELATED DOCS: docs/design/codex-agent-input-bridge.md
TESTS: python -m pytest tests/test_codex_agent_input_bridge.py
"""

from __future__ import annotations

import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.context import CodexContextTranslator
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.codex import (
    CodexContextTranslationRequest,
    CodexHarnessAgentSettings,
    CodexImageInput,
    CodexPrompt,
    CodexRunInput,
    CodexRunResult,
    CodexTextInput,
    CodexTransportRunRequest,
    CodexUsage,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

FINAL_RESPONSE = "codex reply"


def _run_result(thread_id: str = "th_1") -> CodexRunResult:
    # Builds one completed native snapshot with no usage, matching an interrupted-free turn.
    return CodexRunResult(
        thread_id=thread_id,
        turn_id="tu_1",
        status="completed",
        final_response=FINAL_RESPONSE,
        duration_ms=12,
        usage=CodexUsage(),
        items=(),
    )


class _RecordingTransport:
    """Stands in for CodexTransport, recording every request it is handed."""

    def __init__(self) -> None:
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records the translated request and returns a fixed completed result.
        self.requests.append(request)
        return _run_result()


def _build_agent(**overrides: object) -> tuple[CodexHarnessAgent, _RecordingTransport]:
    # Builds an agent whose transport is a recorder, so no Codex process is started.
    settings = CodexHarnessAgentSettings(
        name="codex-agent",
        system_prompt="You are a Codex harness agent.",
        **overrides,  # type: ignore[arg-type]
    )
    agent = CodexHarnessAgent(settings)
    transport = _RecordingTransport()
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport


class TranslateInputTests(unittest.TestCase):
    """Covers every branch of CodexVidbyteTranslator.translate_input()."""

    def setUp(self) -> None:
        self.translator = CodexVidbyteTranslator()

    def test_returns_the_identical_codex_run_input_object(self) -> None:
        request = CodexRunInput(
            items=(CodexTextInput("a"), CodexImageInput("data:image/png;base64,AA")),
        )

        self.assertIs(self.translator.translate_input(request), request)

    def test_converts_a_plain_string_into_one_text_item_for_the_user(self) -> None:
        request = self.translator.translate_input("hello")

        self.assertEqual(request.items, (CodexTextInput("hello"),))
        self.assertEqual(request.recipient, "user")
        self.assertEqual(request.metadata, {})
        self.assertEqual(request.context_items, ())
        self.assertEqual(request.context_placements, ())

    def test_converts_agent_input_prompt_into_exactly_one_text_item(self) -> None:
        request = self.translator.translate_input(AgentInput(prompt="do the thing"))

        self.assertEqual(request.items, (CodexTextInput("do the thing"),))

    def test_copies_agent_input_metadata_into_the_request(self) -> None:
        request = self.translator.translate_input(
            AgentInput(prompt="p", metadata={"trace_id": "abc"})
        )

        self.assertEqual(request.metadata, {"trace_id": "abc"})

    def test_preserves_agent_input_context_items_in_order(self) -> None:
        first = TextContextItem(title="First", content="one")
        second = TextContextItem(title="Second", content="two")

        request = self.translator.translate_input(
            AgentInput(prompt="p", context_items=(first, second))
        )

        self.assertEqual(request.context_items, (first, second))

    def test_preserves_context_manager_object_identity(self) -> None:
        manager = ContextManager()

        request = self.translator.translate_input(
            AgentInput(prompt="p", context_manager=manager)
        )

        self.assertIs(request.context_manager, manager)

    def test_rejects_an_empty_prompt_string(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.translator.translate_input("")

    def test_rejects_a_whitespace_only_prompt(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.translator.translate_input(AgentInput(prompt="   "))

    def test_rejects_none(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.translator.translate_input(None)  # type: ignore[arg-type]

    def test_rejects_an_integer(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.translator.translate_input(7)  # type: ignore[arg-type]

    def test_rejects_a_bare_list_of_input_items(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.translator.translate_input([CodexTextInput("a")])  # type: ignore[arg-type]


class CodexHarnessAgentInputBoundaryTests(unittest.IsolatedAsyncioTestCase):
    """Covers how arun()/run() classify and contain a failed input translation."""

    async def test_arun_raises_codex_agent_error_for_an_invalid_input(self) -> None:
        agent, _ = _build_agent()

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(None)  # type: ignore[arg-type]

        self.assertEqual(
            caught.exception.failure_code,
            FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
        )
        self.assertEqual(caught.exception.operation, "translate_input")

    async def test_arun_classifies_an_unsupported_input_type(self) -> None:
        agent, transport = _build_agent()

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(7)  # type: ignore[arg-type]

        self.assertEqual(caught.exception.operation, "translate_input")
        self.assertEqual(transport.requests, [])

    async def test_arun_chains_the_original_exception_as_cause(self) -> None:
        agent, _ = _build_agent()

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun("")

        self.assertIsInstance(caught.exception.__cause__, ConfigurationError)

    async def test_arun_makes_zero_transport_calls_when_translation_fails(self) -> None:
        agent, transport = _build_agent()

        with self.assertRaises(CodexAgentError):
            await agent.arun("")

        self.assertEqual(transport.requests, [])

    async def test_arun_leaves_facade_state_unchanged_after_a_failed_input(self) -> None:
        agent, _ = _build_agent()

        with self.assertRaises(CodexAgentError):
            await agent.arun("   ")

        self.assertEqual(agent.history, [])
        self.assertEqual(agent.last_prompt, "")
        self.assertIsNone(agent.last_reply)
        self.assertEqual(agent.thread_id, "")

    async def test_run_still_guards_against_an_active_event_loop(self) -> None:
        agent, _ = _build_agent()

        with self.assertRaises(CodexAgentError) as caught:
            agent.run("hello")

        self.assertEqual(caught.exception.operation, "run_sync_guard")


class CodexHarnessAgentInputIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Covers the bridged request travelling through the real translators."""

    async def test_string_input_matches_an_explicit_codex_run_input(self) -> None:
        bridged_agent, bridged_transport = _build_agent()
        native_agent, native_transport = _build_agent()

        bridged = await bridged_agent.arun("same prompt")
        native = await native_agent.arun(CodexRunInput.text("same prompt"))

        self.assertEqual(bridged.content, native.content)
        self.assertEqual(dict(bridged.metadata), dict(native.metadata))
        self.assertEqual(bridged.codex, native.codex)
        self.assertEqual(
            bridged_transport.requests[0].prompt.items,
            native_transport.requests[0].prompt.items,
        )

    async def test_shared_context_manager_renders_its_primitive_once(self) -> None:
        manager = ContextManager()
        manager.upsert(
            TextContextItem(
                title="Shared", content="shared body", primitive_id="doc:shared"
            )
        )
        agent, transport = _build_agent(context_manager=manager)

        await agent.arun(AgentInput(prompt="p", context_manager=manager))

        rendered = "\n".join(
            item.text
            for item in transport.requests[0].prompt.items
            if isinstance(item, CodexTextInput)
        )
        developer = transport.requests[0].system_prompt
        self.assertEqual((rendered + developer).count("shared body"), 1)

    async def test_agent_input_context_items_reach_the_prompt_prefix(self) -> None:
        agent, transport = _build_agent()
        item = TextContextItem(title="Doc", content="request scoped body")

        await agent.arun(AgentInput(prompt="p", context_items=(item,)))

        texts = [
            entry.text
            for entry in transport.requests[0].prompt.items
            if isinstance(entry, CodexTextInput)
        ]
        self.assertTrue(any("request scoped body" in text for text in texts))
        self.assertEqual(texts[-1], "p")


class CodexHarnessAgentSynchronousRunTests(unittest.TestCase):
    """Covers run() from ordinary synchronous code, with no event loop present."""

    def test_run_accepts_a_plain_string_through_the_synchronous_path(self) -> None:
        agent, transport = _build_agent()

        reply = agent.run("hello from sync")

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertEqual(len(transport.requests), 1)


class ContextManagerMetadataTranslationTests(unittest.TestCase):
    """Covers CodexContextTranslator's translation of ContextManager.metadata."""

    @staticmethod
    def _translate(
        *,
        agent_manager: ContextManager | None = None,
        request: CodexRunInput | None = None,
    ) -> CodexPrompt:
        # Runs the real context translator with no agent and no transport involved.
        return CodexContextTranslator.translate(
            CodexContextTranslationRequest(
                input=request if request is not None else CodexRunInput.text("p"),
                static_context="",
                context_manager=agent_manager,
                context_placements=(),
            )
        )

    def test_manager_metadata_reaches_the_translated_turn(self) -> None:
        manager = ContextManager(metadata={"tenant": "acme"})

        prompt = self._translate(agent_manager=manager)

        self.assertEqual(dict(prompt.metadata), {"tenant": "acme"})

    def test_absent_manager_metadata_leaves_the_turn_metadata_empty(self) -> None:
        prompt = self._translate(agent_manager=ContextManager())

        self.assertEqual(dict(prompt.metadata), {})

    def test_per_turn_input_metadata_overrides_manager_metadata(self) -> None:
        manager = ContextManager(metadata={"tenant": "acme", "run": "manager"})
        request = CodexRunInput(
            items=(CodexTextInput("p"),), metadata={"run": "per-turn"}
        )

        prompt = self._translate(agent_manager=manager, request=request)

        self.assertEqual(
            dict(prompt.metadata), {"tenant": "acme", "run": "per-turn"}
        )

    def test_request_scoped_manager_overrides_the_agent_scoped_manager(self) -> None:
        agent_manager = ContextManager(metadata={"scope": "agent", "tenant": "acme"})
        request_manager = ContextManager(metadata={"scope": "request"})
        request = CodexRunInput(
            items=(CodexTextInput("p"),), context_manager=request_manager
        )

        prompt = self._translate(agent_manager=agent_manager, request=request)

        self.assertEqual(
            dict(prompt.metadata), {"tenant": "acme", "scope": "request"}
        )

    def test_a_shared_manager_contributes_its_metadata_once(self) -> None:
        manager = ContextManager(metadata={"tenant": "acme"})
        request = CodexRunInput(items=(CodexTextInput("p"),), context_manager=manager)

        prompt = self._translate(agent_manager=manager, request=request)

        self.assertEqual(dict(prompt.metadata), {"tenant": "acme"})

    def test_translating_metadata_does_not_mutate_the_caller_manager(self) -> None:
        manager = ContextManager(metadata={"tenant": "acme"})

        prompt = self._translate(agent_manager=manager)
        dict(prompt.metadata)["tenant"] = "mutated"

        self.assertEqual(dict(manager.metadata), {"tenant": "acme"})


class ContextManagerMetadataAgentTests(unittest.IsolatedAsyncioTestCase):
    """Covers manager metadata surviving a full bridged turn through the agent."""

    async def test_agent_manager_metadata_reaches_the_reply_metadata(self) -> None:
        manager = ContextManager(metadata={"tenant": "acme"})
        agent, _ = _build_agent(context_manager=manager)

        reply = await agent.arun("p")

        self.assertEqual(reply.metadata["tenant"], "acme")

    async def test_agent_input_manager_metadata_reaches_the_reply_metadata(
        self,
    ) -> None:
        agent, _ = _build_agent()
        manager = ContextManager(metadata={"tenant": "acme"})

        reply = await agent.arun(AgentInput(prompt="p", context_manager=manager))

        self.assertEqual(reply.metadata["tenant"], "acme")

    async def test_agent_input_metadata_still_overrides_manager_metadata(self) -> None:
        agent, _ = _build_agent()
        manager = ContextManager(metadata={"run": "manager"})

        reply = await agent.arun(
            AgentInput(
                prompt="p", metadata={"run": "per-turn"}, context_manager=manager
            )
        )

        self.assertEqual(reply.metadata["run"], "per-turn")


if __name__ == "__main__":
    unittest.main()
