"""FILE: tests/test_codex_durable_sessions.py

PURPOSE:
    Feature tests for Codex durable sessions: CodexSessionTranslator's
    provider-state round trip and portability rejections,
    CodexHarnessAgent.export_state/restore, SessionRestoreRegistry dispatch,
    and a full checkpoint-and-resume cycle through a real Session and store.
    Locks the behavior docs/design/codex-durable-sessions.md specifies: a
    checkpoint carries the native thread id, resume rebuilds a Codex agent
    rather than a BaseAgent, and an unresumable checkpoint fails loudly.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/session.py,
    vidbyte/agents/codex/agent.py (export_state/restore),
    vidbyte/lib/registries/session_restore.py, RunState.provider_state in
    vidbyte/lib/dataclasses/sessions.py, and the dispatch in
    vidbyte/sessions/session.py, against a real InMemorySessionStore.

ARCHITECTURE NOTE:
    Every test runs offline. Only CodexTransport is faked; Session, the store,
    and the serializer are all real, because the defects here — the wrong
    agent type on resume, a field written but never read back, a restored
    agent that starts a fresh thread — only appear end to end.

FUNCTION INVENTORY:
    No production functions. _codex_settings() builds provider settings with
    every field set away from its default, _build_agent() wires an agent to a
    recording transport, and _run_result() builds one completed turn.

COMMON MODIFICATION PATTERNS:
    Add a provider setting, then extend _codex_settings() so the round-trip
    test would fail if the new field were dropped from either direction.

WHAT NOT TO DO IN THIS FILE:
    Do not assert that files are restored (they are not), and do not compare
    provider state dicts key-by-key where comparing rebuilt settings proves
    more.

KNOWN EDGE CASES:
    A payload written without provider_state must still deserialize and take
    the BaseAgent path; an ephemeral thread must refuse to resume.

RELATED DOCS: docs/design/codex-durable-sessions.md
TESTS: python -m pytest tests/test_codex_durable_sessions.py
"""

from __future__ import annotations

import asyncio
import json
import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.session import CodexSessionTranslator
from vidbyte.context.manager import ContextManager
from vidbyte.lib.constants.codex import (
    CODEX_PROVIDER_NAME,
    CODEX_PROVIDER_STATE_KIND,
    CODEX_RUNTIME_TYPE,
    CODEX_STATE_SETTINGS_KEY,
    CODEX_STATE_THREAD_ID_KEY,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexContextPlacement,
    CodexHarnessAgentSettings,
    CodexRunInput,
    CodexRunResult,
    CodexSessionExportRequest,
    CodexSubagentSettings,
    CodexThreadSettings,
    CodexTransportRunRequest,
    CodexTurnSettings,
    CodexUsage,
)
from vidbyte.lib.dataclasses.sessions import SESSION_SCHEMA_VERSION, RunState
from vidbyte.lib.enums.codex import (
    CodexApprovalMode,
    CodexContextAnchor,
    CodexPersonality,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexSandbox,
    CodexThreadSource,
    CodexThreadStartSource,
)
from vidbyte.lib.registries.session_restore import SessionRestoreRegistry
from vidbyte.sessions.errors import SessionError
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.session import Session

FINAL_RESPONSE = "codex reply"
THREAD_ID = "th_live"


def _run_result(thread_id: str = THREAD_ID) -> CodexRunResult:
    # Builds one completed native snapshot.
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
    """Stands in for CodexTransport, recording the thread id each turn used."""

    def __init__(self) -> None:
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records the request so a resumed agent's thread reuse is observable.
        self.requests.append(request)
        return _run_result()


def _codex_settings(ephemeral: bool = False) -> CodexAgentSettings:
    # Every field is set away from its default, so a dropped field fails the round trip.
    return CodexAgentSettings(
        client=CodexClientSettings(
            codex_bin="/usr/bin/codex",
            launch_args_override=("--flag",),
            config_overrides=("key=value",),
            cwd="/repo",
            env={"SECRET_TOKEN": "must-not-persist"},
            client_name="custom-client",
            client_title="Custom Client",
            client_version="9.9.9",
            experimental_api=False,
        ),
        thread=CodexThreadSettings(
            approval_mode=CodexApprovalMode.DENY_ALL,
            base_instructions="base",
            cwd="/repo",
            model="gpt-5-codex",
            model_provider="",
            personality=CodexPersonality.PRAGMATIC,
            sandbox=CodexSandbox.READ_ONLY,
            service_name="svc",
            service_tier="priority",
            session_start_source=CodexThreadStartSource.STARTUP,
            thread_source=CodexThreadSource.USER,
            ephemeral=ephemeral,
            config={"agents": {"enabled": True}},
        ),
        turn=CodexTurnSettings(
            approval_mode=CodexApprovalMode.AUTO_REVIEW,
            cwd="/repo",
            effort=CodexReasoningEffort.HIGH,
            model="gpt-5-codex",
            personality=CodexPersonality.PRAGMATIC,
            sandbox=CodexSandbox.READ_ONLY,
            service_tier="priority",
            summary=CodexReasoningSummary.DETAILED,
        ),
        subagents=CodexSubagentSettings(
            enabled=False,
            max_concurrent_threads=3,
            default_model="gpt-5-codex",
            default_reasoning_effort=CodexReasoningEffort.LOW,
            interrupt_message=False,
            roles={"reviewer": {"description": "reviews"}},
        ),
    )


def _agent_settings(ephemeral: bool = False) -> CodexHarnessAgentSettings:
    # Builds the Vidbyte-facing settings, including fork lineage metadata.
    return CodexHarnessAgentSettings(
        name="codex-agent",
        system_prompt="You are a Codex harness agent.",
        codex=_codex_settings(ephemeral),
        additional_context="extra context",
        description="a codex agent",
        capabilities=("code",),
        metadata={"forked_from_thread_id": "th_parent", "fork_depth": 2},
    )


def _build_agent(
    ephemeral: bool = False,
) -> tuple[CodexHarnessAgent, _RecordingTransport]:
    # Builds an agent whose transport is a recorder, so no Codex process is started.
    agent = CodexHarnessAgent(_agent_settings(ephemeral))
    transport = _RecordingTransport()
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport


class ProviderStateRoundTripTests(unittest.TestCase):
    """Covers the settings mapping in both directions."""

    def setUp(self) -> None:
        self.settings = _agent_settings()
        self.state = CodexSessionTranslator.to_provider_state(
            CodexSessionExportRequest(settings=self.settings, thread_id=THREAD_ID)
        )

    def test_round_trips_every_provider_settings_field(self) -> None:
        rebuilt = CodexSessionTranslator.to_settings(self.state)

        expected = _codex_settings()
        self.assertEqual(rebuilt.thread, expected.thread)
        self.assertEqual(rebuilt.turn, expected.turn)
        self.assertEqual(rebuilt.subagents, expected.subagents)

    def test_round_trips_enums_through_their_values(self) -> None:
        rebuilt = CodexSessionTranslator.to_settings(self.state)

        self.assertIs(rebuilt.turn.effort, CodexReasoningEffort.HIGH)
        self.assertIs(rebuilt.thread.sandbox, CodexSandbox.READ_ONLY)
        self.assertIs(rebuilt.turn.summary, CodexReasoningSummary.DETAILED)

    def test_omits_client_env_from_the_provider_state(self) -> None:
        serialized = json.dumps(self.state)

        self.assertNotIn("SECRET_TOKEN", serialized)
        self.assertNotIn("must-not-persist", serialized)
        self.assertEqual(
            CodexSessionTranslator.to_settings(self.state).client.env, {}
        )

    def test_carries_fork_lineage_from_the_agent_metadata(self) -> None:
        self.assertEqual(self.state["forked_from_thread_id"], "th_parent")
        self.assertEqual(self.state["fork_depth"], 2)

    def test_carries_the_thread_id_and_kind(self) -> None:
        self.assertEqual(self.state[CODEX_STATE_THREAD_ID_KEY], THREAD_ID)
        self.assertEqual(self.state["kind"], CODEX_PROVIDER_STATE_KIND)

    def test_provider_state_is_json_serializable(self) -> None:
        self.assertTrue(json.dumps(self.state))


class PortabilityRejectionTests(unittest.TestCase):
    """Covers the checkpoints CodexSessionTranslator refuses to resume."""

    def test_raises_for_an_empty_thread_id(self) -> None:
        state = CodexSessionTranslator.to_provider_state(
            CodexSessionExportRequest(settings=_agent_settings(), thread_id="")
        )

        with self.assertRaises(SessionError):
            CodexSessionTranslator.require_resumable(state)

    def test_raises_for_an_ephemeral_thread(self) -> None:
        state = CodexSessionTranslator.to_provider_state(
            CodexSessionExportRequest(
                settings=_agent_settings(ephemeral=True), thread_id=THREAD_ID
            )
        )

        with self.assertRaises(SessionError):
            CodexSessionTranslator.require_resumable(state)

    def test_raises_a_session_error_for_an_unknown_enum_value(self) -> None:
        state = CodexSessionTranslator.to_provider_state(
            CodexSessionExportRequest(settings=_agent_settings(), thread_id=THREAD_ID)
        )
        state[CODEX_STATE_SETTINGS_KEY]["thread"]["sandbox"] = "not-a-sandbox"

        with self.assertRaises(SessionError):
            CodexSessionTranslator.to_settings(state)

    def test_raises_when_the_settings_mapping_is_absent(self) -> None:
        with self.assertRaises(SessionError):
            CodexSessionTranslator.to_settings({CODEX_STATE_SETTINGS_KEY: "nope"})


class ExportStateTests(unittest.IsolatedAsyncioTestCase):
    """Covers what a Codex checkpoint records."""

    async def test_records_the_codex_provider_and_runtime_type(self) -> None:
        agent, _ = _build_agent()

        state = agent.export_state()

        self.assertEqual(state.provider, CODEX_PROVIDER_NAME)
        self.assertEqual(state.runtime_type, CODEX_RUNTIME_TYPE)
        self.assertEqual(state.schema_version, SESSION_SCHEMA_VERSION)

    async def test_contains_no_live_objects(self) -> None:
        agent, _ = _build_agent()

        payload = SessionSerializer()._run_state_to_dict(agent.export_state())

        self.assertTrue(json.dumps(payload))

    async def test_serializes_history(self) -> None:
        agent, _ = _build_agent()
        await agent.arun(CodexRunInput.text("one"))
        await agent.arun(CodexRunInput.text("two"))

        state = agent.export_state()

        self.assertEqual(len(state.history), 2)


class RestoreTests(unittest.IsolatedAsyncioTestCase):
    """Covers rebuilding an agent from a checkpoint."""

    async def test_rebuilds_the_same_thread_id_and_settings(self) -> None:
        agent, _ = _build_agent()
        await agent.arun(CodexRunInput.text("go"))

        restored = CodexHarnessAgent.restore(agent.export_state())

        self.assertEqual(restored.thread_id, THREAD_ID)
        self.assertEqual(restored.settings.codex.turn, agent.settings.codex.turn)
        self.assertEqual(restored.settings.additional_context, "extra context")

    async def test_tolerates_the_keyword_arguments_session_passes(self) -> None:
        agent, _ = _build_agent()
        await agent.arun(CodexRunInput.text("go"))

        restored = CodexHarnessAgent.restore(
            agent.export_state(),
            tools=(),
            middleware=(),
            tracer=None,
            output_schema=None,
        )

        self.assertEqual(restored.thread_id, THREAD_ID)

    def test_restores_context_placements_with_a_resupplied_manager(self) -> None:
        manager = ContextManager()
        placements = (
            CodexContextPlacement(
                primitive_id="doc:x", anchor=CodexContextAnchor.BEFORE_IMAGES
            ),
        )
        agent = CodexHarnessAgent(
            CodexHarnessAgentSettings(
                name="codex-agent",
                system_prompt="prompt",
                context_manager=manager,
                context_placements=placements,
                thread_id=THREAD_ID,
            )
        )

        restored = CodexHarnessAgent.restore(
            agent.export_state(), context_manager=ContextManager()
        )

        self.assertEqual(restored.settings.context_placements, placements)

    def test_drops_placements_when_no_manager_is_resupplied(self) -> None:
        manager = ContextManager()
        agent = CodexHarnessAgent(
            CodexHarnessAgentSettings(
                name="codex-agent",
                system_prompt="prompt",
                context_manager=manager,
                context_placements=(
                    CodexContextPlacement(
                        primitive_id="doc:x", anchor=CodexContextAnchor.BEFORE_IMAGES
                    ),
                ),
                thread_id=THREAD_ID,
            )
        )

        restored = CodexHarnessAgent.restore(agent.export_state())

        self.assertEqual(restored.settings.context_placements, ())

    async def test_refuses_an_ephemeral_checkpoint(self) -> None:
        agent, _ = _build_agent(ephemeral=True)
        await agent.arun(CodexRunInput.text("go"))

        with self.assertRaises(SessionError):
            CodexHarnessAgent.restore(agent.export_state())

    async def test_rehydrates_history(self) -> None:
        agent, _ = _build_agent()
        await agent.arun(CodexRunInput.text("one"))
        await agent.arun(CodexRunInput.text("two"))

        restored = CodexHarnessAgent.restore(agent.export_state())

        self.assertEqual(len(restored.history), 2)
        self.assertEqual(restored.history[0].content, FINAL_RESPONSE)


class SessionRestoreRegistryTests(unittest.TestCase):
    """Covers the registry that keeps the dispatch inside the layer graph."""

    def test_resolves_the_registered_codex_kind(self) -> None:
        self.assertIsNotNone(SessionRestoreRegistry.resolve(CODEX_PROVIDER_STATE_KIND))

    def test_returns_none_for_an_unknown_kind(self) -> None:
        self.assertIsNone(SessionRestoreRegistry.resolve("not-a-provider"))

    def test_lists_the_registered_kinds(self) -> None:
        self.assertIn(CODEX_PROVIDER_STATE_KIND, SessionRestoreRegistry.kinds())


class RunStateProviderStateTests(unittest.TestCase):
    """Covers the new RunState field's default and serialization."""

    def test_defaults_provider_state_to_an_empty_mapping(self) -> None:
        state = RunState(
            schema_version=SESSION_SCHEMA_VERSION,
            agent_name="a",
            system_prompt="p",
            description="",
            capabilities=(),
            provider=None,
            model_name=None,
            temperature=None,
            runtime_type="linear",
            runtime_config={},
            algorithm="default",
            metadata={},
            agent_metadata={},
            tool_names=(),
            history=(),
        )

        self.assertEqual(state.provider_state, {})

    def test_a_payload_without_provider_state_still_deserializes(self) -> None:
        serializer = SessionSerializer()
        payload = serializer._run_state_to_dict(
            RunState(
                schema_version=SESSION_SCHEMA_VERSION,
                agent_name="a",
                system_prompt="p",
                description="",
                capabilities=(),
                provider=None,
                model_name=None,
                temperature=None,
                runtime_type="linear",
                runtime_config={},
                algorithm="default",
                metadata={},
                agent_metadata={},
                tool_names=(),
                history=(),
            )
        )
        payload.pop("provider_state")

        rebuilt = serializer._run_state_from_dict(payload)

        self.assertEqual(rebuilt.provider_state, {})


class SessionIntegrationTests(unittest.TestCase):
    """Covers a full checkpoint-and-resume cycle through a real Session."""

    def setUp(self) -> None:
        self.agent, self.transport = _build_agent()
        self.session = Session(self.agent)

    def test_session_accepts_a_codex_agent(self) -> None:
        self.assertIsNotNone(self.session)

    def test_resume_rebuilds_a_codex_agent_not_a_base_agent(self) -> None:
        asyncio.run(self.agent.arun(CodexRunInput.text("go")))
        self.session.checkpoint()

        resumed = Session.resume(self.session._store, self.session._session_id)

        self.assertIsInstance(resumed._agent, CodexHarnessAgent)
        self.assertEqual(resumed._agent.thread_id, THREAD_ID)

    def test_a_resumed_agent_reuses_the_native_thread(self) -> None:
        asyncio.run(self.agent.arun(CodexRunInput.text("go")))
        self.session.checkpoint()
        resumed = Session.resume(self.session._store, self.session._session_id)
        transport = _RecordingTransport()
        resumed._agent._transport = transport  # type: ignore[assignment]

        asyncio.run(resumed._agent.arun(CodexRunInput.text("again")))

        self.assertEqual(transport.requests[0].thread_id, THREAD_ID)

    def test_a_checkpoint_round_trips_through_the_serializer(self) -> None:
        asyncio.run(self.agent.arun(CodexRunInput.text("go")))
        checkpoint_id = self.session.checkpoint()
        stored = self.session._store.get(checkpoint_id)
        serializer = SessionSerializer()

        rebuilt = serializer.checkpoint_from_dict(
            serializer.checkpoint_to_dict(stored)
        )

        self.assertEqual(
            rebuilt.run_state.provider_state[CODEX_STATE_THREAD_ID_KEY], THREAD_ID
        )

    def test_two_turns_carry_both_history_entries_into_the_restored_agent(self) -> None:
        asyncio.run(self.agent.arun(CodexRunInput.text("one")))
        asyncio.run(self.agent.arun(CodexRunInput.text("two")))
        self.session.checkpoint()

        resumed = Session.resume(self.session._store, self.session._session_id)

        self.assertEqual(len(resumed._agent.history), 2)


if __name__ == "__main__":
    unittest.main()
