"""FILE: tests/test_jev_skill_providers.py

PURPOSE: Verifies explicit skill source contracts, bounded FILE resolution, stable failures, and Jev preload integration.
ROLE IN CODEBASE: Covers the first implementation stage of docs/design/jev-skill-providers.md without live provider calls.
ARCHITECTURE NOTE: Tests use temporary files and replace only the TypeSafe/generative model boundaries.
"""

from __future__ import annotations

import asyncio
import ast
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.base import BaseAgent
from vidbyte import ClaudeSkillReference as RootClaudeSkillReference
from vidbyte import ClaudeSkillSession as RootClaudeSkillSession
from vidbyte import ClaudeSkillType as RootClaudeSkillType
from vidbyte import JevAgent, JevAlignmentSettings, JevRuntimeSettings
from vidbyte import SkillDocument as RootSkillDocument
from vidbyte import SkillSource as RootSkillSource
from vidbyte import SkillSourceKind as RootSkillSourceKind
from vidbyte.agents.jev.alignment.skills import JevSkillsPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings as InternalJevAgentSettings
from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.lib.config import DecisionModelConfig, TextModelConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevJson
from vidbyte.lib.dataclasses.skills import (
    ClaudeSkillReference,
    ClaudeSkillSession,
    SkillDocument,
    SkillSource,
)
from vidbyte.lib.enums.jev import JevQuestionType, JevSkillStatus
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.skills import ClaudeSkillType, SkillSourceKind
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderResponseError,
    UnsupportedProviderError,
)
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.jev.decision import DecisionModelHelper
import vidbyte.lib.jev.preflight.skills as skill_question_module
from vidbyte.lib.jev.preflight.skills import JevSkillRelevanceQuestion
from vidbyte.lib.runners.streaming_text import StreamingTextModelRunner
from vidbyte.lib.runners.text import TextModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse, TextModelResponse
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives.documents import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.providers.skills import SkillSourceError, SkillSourceResolver
from vidbyte.providers.skills.claude import ClaudeSkillSourceAdapter
from vidbyte.providers.skills.file import _MAX_SKILL_FILE_BYTES, FileSkillSourceAdapter
from vidbyte.providers.anthropic import AnthropicProvider
from vidbyte.tools.decorators import tool

_HELPER_PATH = "vidbyte.agents.jev.alignment.skills.DecisionModelHelper"


class _AlwaysYesDecisionHelper:
    """Returns a passing indexed answer for every request question."""

    requests: ClassVar[list[JevDecisionRequest]] = []
    score_noul = staticmethod(DecisionModelHelper.score_noul)

    def __init__(self, config: DecisionModelConfig) -> None:
        # Stores validated config only to match the production helper constructor.
        self.config = config

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Captures exact question indexes and supplies a deterministic passing decision.
        self.requests.append(request)
        answers = {
            question.name: JevAnswer(
                question_name=question.name,
                question_type=JevQuestionType.NOUL,
                choice="true",
                probabilities={"true": 0.9, "false": 0.1},
                noul=0.9,
            )
            for question in request.questions
        }
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="decision-test", answers=answers, raw={}, usage={"input_tokens": 3, "output_tokens": 1})


class _SelectiveDecisionHelper:
    """Answers true only for the fixed one-based candidate indexes configured by a test."""

    requests: ClassVar[list[JevDecisionRequest]] = []
    selected: ClassVar[frozenset[str]] = frozenset()
    score_noul = staticmethod(DecisionModelHelper.score_noul)

    def __init__(self, config: DecisionModelConfig) -> None:
        # Retains the policy object to match the production helper constructor.
        self.config = config

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Emits independent indexed answers so cap behavior can be tested after all candidates were considered.
        self.requests.append(request)
        answers = {}
        for question in request.questions:
            selected = question.name in self.selected
            answers[question.name] = JevAnswer(
                question_name=question.name,
                question_type=JevQuestionType.NOUL,
                choice="true" if selected else "false",
                probabilities={"true": 0.9 if selected else 0.1, "false": 0.1 if selected else 0.9},
                noul=0.9 if selected else 0.1,
            )
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="decision-test", answers=answers, raw={}, usage={"input_tokens": 3, "output_tokens": 1})


class _CapturingGenerativeRunner:
    """Captures the provider-visible system prompt for one JevAgent run."""

    def __init__(self) -> None:
        # Retains only prompts for assertions in the integration test.
        self.systems: list[str | None] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        # Returns a standard response after recording the exact per-run system option.
        self.systems.append(kwargs.get("system"))
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", text="done", raw={})


class SkillQuestionContractTests(unittest.TestCase):
    """Checks question length, metadata boundaries, and standalone rubric literals."""

    def test_text_and_native_questions_exceed_two_thousand_tokens(self) -> None:
        # [Silent Failure] both body-aware and metadata-only questions carry complete recognition rubrics.
        if importlib.util.find_spec("tiktoken") is None:
            self.skipTest("tiktoken is not installed")
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        for metadata_only in (False, True):
            with self.subTest(metadata_only=metadata_only):
                question = JevSkillRelevanceQuestion(7, metadata_only=metadata_only).to_question()
                parts = [question.instructions]
                parts.extend(json.dumps(JevJson.thaw(option.description), ensure_ascii=False) for option in question.options)
                self.assertGreaterEqual(len(encoding.encode("\n".join(parts))), 2_000)
                self.assertIn("skills.skill_7", question.instructions)
                self.assertNotIn("CALLER_PRIVATE", question.instructions)

    def test_metadata_definitions_and_rules_are_standalone_literals(self) -> None:
        # [Hidden Assumption] every rubric entry remains one literal rather than split adjacent strings.
        self.assertEqual(len(skill_question_module._NATIVE_DEFINITIONS), 11)
        self.assertEqual(len(skill_question_module._NATIVE_RULES), 10)
        module_path = Path(skill_question_module.__file__)
        syntax = ast.parse(module_path.read_text(encoding="utf-8"))
        assignments = {
            target.id: node.value
            for node in ast.walk(syntax)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name) and target.id in {"_NATIVE_DEFINITIONS", "_NATIVE_RULES"}
        }
        for name in ("_NATIVE_DEFINITIONS", "_NATIVE_RULES"):
            value = assignments[name]
            self.assertIsInstance(value, ast.Tuple)
            self.assertTrue(all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in value.elts))


class SkillSourceContractTests(unittest.TestCase):
    """Checks the closed source model, compatible options, and stable public exports."""

    def test_source_fields_kind_options_and_secret_repr(self) -> None:
        # [Edge Case] optional fields are accepted only for kinds that define them and keys never appear in repr.
        source = SkillSource(kind=SkillSourceKind.CLAUDE, location="skill_123", version="latest", api_key="private-key", workspace_id="ws_123")
        self.assertNotIn("private-key", repr(source))
        credential_url = SkillSource(kind=SkillSourceKind.GITHUB, location="https://user:key-marker@github.com/org/repo?token=query-marker")
        self.assertNotIn("key-marker", repr(credential_url))
        self.assertNotIn("query-marker", repr(credential_url))
        self.assertEqual(source.version, "latest")
        with self.assertRaises(ConfigurationError):
            SkillSource(kind=SkillSourceKind.FILE, location="./skills", revision="main")
        with self.assertRaises(ConfigurationError):
            SkillSource(kind="file", location="./skills")  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            SkillSource(kind=SkillSourceKind.GITHUB, location=" ")

    def test_native_contract_requires_closed_enum_and_exactly_one_content_mode(self) -> None:
        # [Hidden Assumption] a native reference has metadata identity but no fake text body.
        reference = ClaudeSkillReference(skill_id="skill_123", version="latest", type=ClaudeSkillType.CUSTOM)
        document = SkillDocument(name="native", description="Opaque skill", text=None, source="claude", claude_reference=reference)
        self.assertIsNone(document.text)
        self.assertIs(RootClaudeSkillReference, ClaudeSkillReference)
        self.assertIs(RootClaudeSkillSession, ClaudeSkillSession)
        self.assertIs(RootClaudeSkillType, ClaudeSkillType)
        self.assertIs(RootSkillDocument, SkillDocument)
        self.assertIs(RootSkillSource, SkillSource)
        self.assertIs(RootSkillSourceKind, SkillSourceKind)
        with self.assertRaises(ConfigurationError):
            SkillDocument(name="bad", description="No body", text=None)

    def test_settings_preserve_source_duplicates_until_resolution(self) -> None:
        # [Silent Failure] constructor does not guess whether two optional source names resolve to duplicate content.
        first = SkillSource(kind=SkillSourceKind.FILE, location="./one", skill_name="maybe-same")
        second = SkillSource(kind=SkillSourceKind.FILE, location="./two", skill_name="maybe-same")
        settings = JevAlignmentSettings(skills=(first, second))
        self.assertEqual(settings.skills, (first, second))


class FileSkillSourceTests(unittest.IsolatedAsyncioTestCase):
    """Verifies local path forms, full text preservation, and safe bounded failures."""

    async def test_file_and_directory_paths_preserve_complete_crlf_document(self) -> None:
        # [Silent Failure] parsing metadata must not strip frontmatter or normalize CRLF in returned text.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "review"
            directory.mkdir()
            path = directory / "SKILL.md"
            content = b"---\r\nname: review\r\ndescription: Review changes\r\n---\r\nKeep exact.\r\n"
            path.write_bytes(content)
            adapter = FileSkillSourceAdapter()
            from_directory = await adapter.resolve(SkillSource(kind=SkillSourceKind.FILE, location=str(directory)))
            from_file = await adapter.resolve(SkillSource(kind=SkillSourceKind.FILE, location=str(path), skill_name="review"))

        self.assertEqual(from_directory.text, content.decode("utf-8"))
        self.assertEqual(from_file.text, content.decode("utf-8"))
        self.assertEqual(from_file.source, str(path.resolve()))
        self.assertEqual(from_file.name, "review")

    async def test_missing_malformed_and_wrong_named_files_fail_with_safe_messages(self) -> None:
        # [Hidden Failure] expected local lookup errors are typed and never echo caller paths.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            malformed = root / "SKILL.md"
            malformed.write_text("---\nnot: [valid\n---\nbody\n", encoding="utf-8")
            named = root / "not-a-skill.md"
            named.write_text("---\nname: x\ndescription: y\n---\nbody\n", encoding="utf-8")
            adapter = FileSkillSourceAdapter()
            for location in (str(root / "missing"), str(malformed), str(named)):
                with self.subTest(location=location), self.assertRaises(SkillSourceError) as caught:
                    await adapter.resolve(SkillSource(kind=SkillSourceKind.FILE, location=location))
                self.assertNotIn(temporary, str(caught.exception))

    async def test_file_size_limit_reads_only_bounded_content(self) -> None:
        # [Edge Case] a file exactly over the cap is rejected without parsing or loading the rest.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SKILL.md"
            path.write_bytes(b"x" * (_MAX_SKILL_FILE_BYTES + 1))
            with self.assertRaisesRegex(SkillSourceError, "size limit"):
                await FileSkillSourceAdapter().resolve(SkillSource(kind=SkillSourceKind.FILE, location=str(path)))

    async def test_closed_dispatch_does_not_guess_remote_sources(self) -> None:
        # [Hidden Assumption] URL-like values are acted on only when paired with an explicit supported kind.
        source = SkillSource(kind=SkillSourceKind.GITHUB, location="https://github.com/acme/skills")
        with self.assertRaisesRegex(SkillSourceError, "could not be resolved"):
            await SkillSourceResolver().resolve(source)


class SkillPreloadIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Checks ordered per-source outcomes and the production JevAgent preload path."""

    def setUp(self) -> None:
        # Keeps scripted decision requests isolated across test cases.
        _AlwaysYesDecisionHelper.requests.clear()

    async def test_failed_source_keeps_index_and_later_inline_skill_is_selected(self) -> None:
        # [Hidden Failure] one missing file is unavailable while the next candidate keeps its original question key.
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            settings = JevAlignmentSettings(skills=(SkillSource(kind=SkillSourceKind.FILE, location=str(missing)), "inline exact text"))
            preload = JevSkillsPreload(skills=settings.skills, decision=DecisionModelConfig(api_key="test"), threshold=0.5, response=JevResponse())
            with patch(_HELPER_PATH, new=_AlwaysYesDecisionHelper):
                context = await preload.run("Use the inline guidance", BaseAgentContext(system_prompt="Base."))

        results = preload.response.state.skills.results
        self.assertEqual(tuple(result.status for result in results), (JevSkillStatus.UNAVAILABLE, JevSkillStatus.SELECTED))
        self.assertEqual(results[0].detail, "Skill source could not be resolved.")
        self.assertEqual(_AlwaysYesDecisionHelper.requests[0].questions[0].name, "skills.skill_2")
        self.assertIn("inline exact text", context.system_prompt)
        self.assertNotIn(temporary, repr(results))

    async def test_resolved_duplicate_names_mark_all_source_slots_unavailable(self) -> None:
        # [Silent Failure] duplicate names discovered only after local resolution cannot select the first silently.
        with tempfile.TemporaryDirectory() as temporary:
            sources = []
            for name in ("first", "second"):
                directory = Path(temporary) / name
                directory.mkdir()
                (directory / "SKILL.md").write_text("---\nname: same\ndescription: duplicate\n---\nbody\n", encoding="utf-8")
                sources.append(SkillSource(kind=SkillSourceKind.FILE, location=str(directory)))
            settings = JevAlignmentSettings(skills=tuple(sources))
            preload = JevSkillsPreload(skills=settings.skills, decision=DecisionModelConfig(api_key="test"), threshold=0.5, response=JevResponse())
            with patch(_HELPER_PATH, new=_AlwaysYesDecisionHelper):
                context = await preload.run("Do work", BaseAgentContext(system_prompt="Base."))

        self.assertEqual(tuple(result.status for result in preload.response.state.skills.results), (JevSkillStatus.UNAVAILABLE,) * 2)
        self.assertEqual(tuple(result.detail for result in preload.response.state.skills.results), ("Resolved skill name is ambiguous.",) * 2)
        self.assertEqual(_AlwaysYesDecisionHelper.requests, [])
        self.assertEqual(context.system_prompt, "Base.")

    async def test_cancellation_from_source_resolver_propagates(self) -> None:
        # [Hidden Failure] cancellation is not translated into an ordinary unavailable source result.
        class CancelledResolver:
            async def resolve(self, source: SkillSource) -> SkillDocument:
                # Simulates task cancellation at the provider boundary.
                raise asyncio.CancelledError

        source = SkillSource(kind=SkillSourceKind.FILE, location="./valid")
        preload = JevSkillsPreload(skills=(source,), decision=DecisionModelConfig(api_key="test"), threshold=0.5, response=JevResponse(), source_resolver=CancelledResolver())  # type: ignore[arg-type]
        with self.assertRaises(asyncio.CancelledError):
            await preload.run("Do work", BaseAgentContext(system_prompt="Base."))

    async def test_jev_agent_resolves_local_skill_and_injects_full_document(self) -> None:
        # [Hidden Assumption] an explicit FILE source flows through settings, runtime preload, decision, and main runner.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SKILL.md"
            content = "---\nname: release-notes\ndescription: Write release notes\n---\nPreserve full file content.\n"
            path.write_bytes(content.encode("utf-8"))
            settings = InternalJevAgentSettings(
                name="source-test",
                system_prompt="Base prompt.",
                provider=ModelProvider.OPENAI,
                model_name="gpt-4.1-mini",
                alignment=JevAlignmentSettings(skills=(SkillSource(kind=SkillSourceKind.FILE, location=str(path)),)),
            )
            agent = JevAgent(settings, JevRuntimeSettings(preflight=()))
            runner = _CapturingGenerativeRunner()
            bind_test_runner(agent, runner)
            with patch(_HELPER_PATH, new=_AlwaysYesDecisionHelper):
                await agent.arun("Write release notes")

        self.assertIn(content, runner.systems[0])
        self.assertEqual(agent.response.skills.results[0].status, JevSkillStatus.SELECTED)
        self.assertEqual(agent.response.skills.results[0].source, str(path.resolve()))

    async def test_claude_skill_uses_agent_key_and_metadata_only_relevance_state(self) -> None:
        # [Hidden Assumption] an Anthropic agent key is the Claude source fallback and Jev never receives an invented body.
        transport = _QueueResponseTransport((
            {"data": [{"id": "skill_meta", "display_name": "Data cleanup", "latest_version_id": "version_1", "source": {"type": "custom"}}], "next_page": None},
            {"id": "version_1", "skill_id": "skill_meta", "name": "data-cleanup", "description": "Guidance for cleaning tabular data and handling missing values."},
        ))
        source = SkillSource(kind=SkillSourceKind.CLAUDE, location="skill_meta")
        settings = InternalJevAgentSettings(
            name="native-source",
            system_prompt="Base prompt.",
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-sonnet-4-6",
            api_key="agent-anthropic-key",
            alignment=JevAlignmentSettings(skills=(source,)),
        )
        agent = JevAgent(settings, JevRuntimeSettings(preflight=()))
        agent.skill_preload.source_resolver._claude_adapter._transport = transport
        _AlwaysYesDecisionHelper.requests.clear()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), patch(_HELPER_PATH, new=_AlwaysYesDecisionHelper):
            context = await agent.skill_preload.run("Clean the report data", BaseAgentContext(system_prompt="Base prompt."))

        self.assertTrue(all(request["headers"]["x-api-key"] == "agent-anthropic-key" for request in transport.requests))
        self.assertEqual(agent.response.skills.claude_skills, (ClaudeSkillReference("skill_meta", "version_1", ClaudeSkillType.CUSTOM),))
        self.assertEqual(agent.response.skills.results[0].status, JevSkillStatus.SELECTED)
        self.assertEqual(context.system_prompt, "Base prompt.")
        decision_request = _AlwaysYesDecisionHelper.requests[0]
        candidate = decision_request.state["skills"]["skills.skill_1"]
        self.assertEqual(candidate["kind"], "claude_native_metadata")
        self.assertNotIn("text", candidate)
        self.assertIn("full body is unavailable", decision_request.questions[0].instructions)

    async def test_non_anthropic_agent_does_not_resolve_or_score_claude_candidates(self) -> None:
        # [Hidden Failure] an OpenAI key is never forwarded to Anthropic, and unsupported native candidates skip Jev scoring.
        source = SkillSource(kind=SkillSourceKind.CLAUDE, location="skill_not_fetched")
        settings = InternalJevAgentSettings(
            name="other-provider",
            system_prompt="Base prompt.",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4.1-mini",
            api_key="openai-secret",
            alignment=JevAlignmentSettings(skills=(source,)),
        )
        agent = JevAgent(settings, JevRuntimeSettings(preflight=()))
        transport = _QueueResponseTransport(())
        agent.skill_preload.source_resolver._claude_adapter._transport = transport
        _AlwaysYesDecisionHelper.requests.clear()

        with patch(_HELPER_PATH, new=_AlwaysYesDecisionHelper):
            await agent.skill_preload.run("Do other work", BaseAgentContext(system_prompt="Base prompt."))

        self.assertEqual(transport.requests, [])
        self.assertEqual(_AlwaysYesDecisionHelper.requests, [])
        result = agent.response.skills.results[0]
        self.assertEqual(result.status, JevSkillStatus.UNAVAILABLE)
        self.assertEqual(result.detail, "Native Claude skills require an Anthropic model.")
        self.assertIsNone(agent.skill_preload.source_resolver._claude_adapter._default_api_key)

    async def test_native_cap_counts_only_selected_skills_and_keeps_later_positive(self) -> None:
        # [Edge Case] every candidate is classified before the API's 20-selected-reference cap is applied.
        documents = tuple(
            SkillDocument(
                name=f"native-{index}",
                description=f"Concrete guidance for candidate {index}.",
                text=None,
                source=f"claude:skill_{index}@version_{index}",
                claude_reference=ClaudeSkillReference(f"skill_{index}", f"version_{index}", ClaudeSkillType.CUSTOM),
            )
            for index in range(1, 22)
        )
        response = JevResponse()
        preload = JevSkillsPreload(
            skills=documents,
            decision=DecisionModelConfig(api_key="test-key"),
            threshold=0.5,
            response=response,
            provider=ModelProvider.ANTHROPIC,
        )
        _SelectiveDecisionHelper.requests.clear()
        _SelectiveDecisionHelper.selected = frozenset({"skills.skill_21"})

        with patch(_HELPER_PATH, new=_SelectiveDecisionHelper):
            await preload.run("Do the requested work", BaseAgentContext(system_prompt="Base."))

        requested = [question.name for call in _SelectiveDecisionHelper.requests for question in call.questions]
        self.assertEqual(requested, [f"skills.skill_{index}" for index in range(1, 22)])
        first_native_question = _SelectiveDecisionHelper.requests[0].questions[0]
        self.assertIn("full body is unavailable", first_native_question.instructions)
        self.assertEqual(len(response.state.skills.claude_skills), 1)
        self.assertEqual(response.state.skills.claude_skills[0].skill_id, "skill_21")
        self.assertEqual(response.state.skills.results[0].status, JevSkillStatus.SKIPPED)
        self.assertEqual(response.state.skills.results[20].status, JevSkillStatus.SELECTED)

        _SelectiveDecisionHelper.selected = frozenset(f"skills.skill_{index}" for index in range(1, 22))
        with patch(_HELPER_PATH, new=_SelectiveDecisionHelper):
            await preload.run("Do the requested work", BaseAgentContext(system_prompt="Base."))
        self.assertEqual(len(response.state.skills.claude_skills), 20)
        self.assertEqual(response.state.skills.results[19].status, JevSkillStatus.SELECTED)
        self.assertEqual(response.state.skills.results[20].status, JevSkillStatus.UNAVAILABLE)
        self.assertEqual(response.state.skills.results[20].detail, "Anthropic supports at most 20 skills per request.")


class ClaudeNativeRunnerTests(unittest.IsolatedAsyncioTestCase):
    """Checks typed Claude call options, payload composition, and one-exchange pause parsing."""

    async def test_native_payload_preserves_local_tools_usage_and_pause_response(self) -> None:
        # [Silent Failure] a native response remains one raw exchange with exact assistant blocks and usage.
        blocks = [{"type": "server_tool_use", "id": "toolu_1", "name": "code_execution", "input": {"code": "print(1)"}}]
        transport = _ResponseTransport({"content": blocks, "container": {"id": "container_1"}, "stop_reason": "pause_turn", "usage": {"input_tokens": 9, "output_tokens": 2, "cache_read_input_tokens": 4}})
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        reference = ClaudeSkillReference(skill_id="skill_1", version="skver_1", type=ClaudeSkillType.CUSTOM)
        local_tool = {"name": "lookup", "description": "Search local data", "input_schema": {"type": "object", "properties": {}}}

        response = await runner.arun("Create a report", tools=(local_tool,), claude_skills=(reference,))

        body = transport.requests[0]["json_body"]
        self.assertEqual(body["container"]["skills"], [{"type": "custom", "skill_id": "skill_1", "version": "skver_1"}])
        self.assertEqual(body["messages"], [{"role": "user", "content": "Create a report"}])
        self.assertIn(local_tool, body["tools"])
        self.assertEqual(sum(tool.get("type") == "code_execution_20250825" for tool in body["tools"]), 1)
        self.assertEqual(response.text, "")
        self.assertEqual(response.raw["content"], blocks)
        self.assertEqual(response.usage["cache_read_input_tokens"], 4)
        expected_resume = (*body["messages"], {"role": "assistant", "content": blocks})
        self.assertEqual(response.claude_skill_session, ClaudeSkillSession("container_1", True, expected_resume))

    async def test_paused_session_reuses_container_and_does_not_repeat_user_prompt(self) -> None:
        # [Hidden Assumption] the typed pause flag means the exact assistant block is already in call history.
        assistant_blocks = [{"type": "server_tool_use", "id": "toolu_2", "name": "code_execution", "input": {"code": "print(2)"}}]
        transport = _ResponseTransport({"content": [{"type": "text", "text": "Finished."}], "container": {"id": "container_2"}, "stop_reason": "end_turn", "usage": {"input_tokens": 8, "output_tokens": 3, "cache_creation_input_tokens": 2}})
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        reference = ClaudeSkillReference(skill_id="skill_2", version="skver_2", type=ClaudeSkillType.ANTHROPIC)
        messages = ({"role": "user", "content": "Original request"}, {"role": "assistant", "content": assistant_blocks})

        response = await runner.arun(
            "Original request",
            messages=messages,
            claude_skills=(reference,),
            claude_skill_session=ClaudeSkillSession("container_2", True, messages),
        )

        body = transport.requests[0]["json_body"]
        self.assertEqual(body["container"]["id"], "container_2")
        self.assertEqual(body["messages"], list(messages))
        self.assertEqual(response.text, "Finished.")
        self.assertEqual(response.claude_skill_session, ClaudeSkillSession("container_2", False))
        self.assertEqual(response.usage["cache_creation_input_tokens"], 2)

    async def test_agent_replays_exact_multiple_pauses_and_records_each_exchange_once(self) -> None:
        # [Silent Failure] the runtime resumes exact provider messages, including conversation placements, and meters each HTTP response once.
        first_blocks = [{"type": "server_tool_use", "id": "srv_1", "name": "code_execution", "input": {"code": "print(1)"}}]
        second_blocks = [{"type": "server_tool_use", "id": "srv_2", "name": "code_execution", "input": {"code": "print(2)"}}]
        responses = (
            {"content": first_blocks, "container": {"id": "run_container"}, "stop_reason": "pause_turn", "usage": {"input_tokens": 11, "output_tokens": 2, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 4}},
            {"content": second_blocks, "container": {"id": "run_container"}, "stop_reason": "pause_turn", "usage": {"input_tokens": 12, "output_tokens": 3, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 6}},
            {"content": [{"type": "text", "text": "Finished."}], "container": {"id": "run_container"}, "stop_reason": "end_turn", "usage": {"input_tokens": 13, "output_tokens": 4, "cache_read_input_tokens": 7, "cache_creation_input_tokens": 8}},
        )
        transport = _QueueResponseTransport(responses)
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        context_manager = ContextManager()
        context_manager.upsert(TextContextItem(title="top marker", content="TOP MESSAGE", primitive_id="top"), placement=ContextWindowPlacement.TOP_OF_CONVERSATION)
        context_manager.upsert(TextContextItem(title="end marker", content="END MESSAGE", primitive_id="end"), placement=ContextWindowPlacement.END_OF_CONVERSATION)
        top_messages = context_manager.render_conversation_messages(ContextWindowPlacement.TOP_OF_CONVERSATION)
        end_messages = context_manager.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)
        original_prompt = "Continue the report"
        # [Hidden Failure] an identical historical request must not replace this new turn.
        history = ({"role": "user", "content": original_prompt},)
        reference = ClaudeSkillReference("skill_runtime", "skver_runtime", ClaudeSkillType.CUSTOM)
        agent = BaseAgent(
            name="native-runtime",
            system_prompt="System instructions",
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-sonnet-4-6",
            api_key="test-key",
            context_manager=context_manager,
            agent_loop_settings=AgentLoopSettings(max_iterations=4),
        )

        result = await agent._run_direct(
            original_prompt,
            BaseAgentContext(system_prompt="System instructions"),
            runner=runner,
            messages=history,
            claude_skills=(reference,),
            claude_skill_session=None,
        )

        first_request = (*top_messages, *history, *end_messages, {"role": "user", "content": original_prompt})
        first_resume = (*first_request, {"role": "assistant", "content": first_blocks})
        second_resume = (*first_resume, {"role": "assistant", "content": second_blocks})
        sent = [request["json_body"]["messages"] for request in transport.requests]
        self.assertEqual(sent, [list(first_request), list(first_resume), list(second_resume)])
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual([request["json_body"]["container"].get("id") for request in transport.requests], [None, "run_container", "run_container"])
        for messages in sent:
            self.assertEqual(sum(item == {"role": "user", "content": original_prompt} for item in messages), 2)
        self.assertEqual(result.output, "Finished.")
        usage = agent.get_usage()
        self.assertEqual(len(usage.calls), 3)
        self.assertEqual(
            [(call.usage.cache_read_input_tokens, call.usage.cache_creation_input_tokens) for call in usage.calls],
            [(3, 4), (5, 6), (7, 8)],
        )

    async def test_native_pause_obeys_existing_iteration_limit(self) -> None:
        # [Edge Case] a pause continuation consumes one normal bounded runtime iteration.
        transport = _QueueResponseTransport(({"content": [{"type": "server_tool_use", "id": "srv_bound", "name": "code_execution", "input": {"code": "pass"}}], "container": {"id": "bound_container"}, "stop_reason": "pause_turn", "usage": {"input_tokens": 1, "output_tokens": 1}},))
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        agent = BaseAgent(name="bounded-native", system_prompt="System", provider=ModelProvider.ANTHROPIC, model_name="claude-sonnet-4-6", api_key="test-key", agent_loop_settings=AgentLoopSettings(max_iterations=1))

        await agent._run_direct("Task", BaseAgentContext(system_prompt="System"), runner=runner, claude_skills=(ClaudeSkillReference("skill_bound", "v1", ClaudeSkillType.CUSTOM),), claude_skill_session=None)

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(len(agent.get_usage().calls), 1)

    async def test_local_tool_exchange_then_pause_replays_fresh_exchange_history(self) -> None:
        # [Hidden Failure] a completed native response can execute a local tool before the next exchange pauses.
        @tool
        def lookup(topic: str) -> str:
            """Look up one topic."""
            executions.append(topic)
            return f"found:{topic}"

        executions: list[str] = []
        pause_blocks = [{"type": "server_tool_use", "id": "srv_after_local", "name": "code_execution", "input": {"code": "print('ok')"}}]
        transport = _QueueResponseTransport((
            {"content": [{"type": "tool_use", "id": "local_call", "name": "lookup", "input": {"topic": "sdk"}}], "container": {"id": "local_container"}, "stop_reason": "tool_use", "usage": {"input_tokens": 5, "output_tokens": 2}},
            {"content": pause_blocks, "container": {"id": "local_container"}, "stop_reason": "pause_turn", "usage": {"input_tokens": 6, "output_tokens": 3}},
            {"content": [{"type": "text", "text": "All done."}], "container": {"id": "local_container"}, "stop_reason": "end_turn", "usage": {"input_tokens": 7, "output_tokens": 4}},
        ))
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        agent = BaseAgent(name="local-tool-native", system_prompt="System", provider=ModelProvider.ANTHROPIC, model_name="claude-sonnet-4-6", api_key="test-key", tools=(lookup,), agent_loop_settings=AgentLoopSettings(max_iterations=4))

        result = await agent._run_direct(
            "Use lookup then continue",
            BaseAgentContext(system_prompt="System"),
            runner=runner,
            claude_skills=(ClaudeSkillReference("skill_local", "v1", ClaudeSkillType.CUSTOM),),
            claude_skill_session=None,
        )

        messages_by_call = [request["json_body"]["messages"] for request in transport.requests]
        prompt = {"role": "user", "content": "Use lookup then continue"}
        self.assertEqual(executions, ["sdk"])
        self.assertEqual(len(messages_by_call), 3)
        self.assertEqual([sum(item == prompt for item in messages) for messages in messages_by_call], [1, 2, 2])
        self.assertTrue(any(item.get("role") == "assistant" and any(block.get("type") == "tool_use" for block in item.get("content", ())) for item in messages_by_call[1]))
        self.assertEqual(messages_by_call[2], [*messages_by_call[1], {"role": "assistant", "content": pause_blocks}])
        self.assertEqual(result.output, "All done.")
        self.assertEqual(len(agent.get_usage().calls), 3)

    async def test_conflicts_and_non_anthropic_native_requests_fail_before_transport(self) -> None:
        # [Hidden Failure] callers cannot shadow reserved native fields or send opaque refs to another provider.
        reference = ClaudeSkillReference(skill_id="skill_3", version="skver_3", type=ClaudeSkillType.CUSTOM)
        transport = _ResponseTransport({})
        anthropic = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key", extra_body={"container": {"id": "other"}}), transport=transport)
        with self.assertRaises(ConfigurationError):
            await anthropic.arun("Task", claude_skills=(reference,))
        with self.assertRaises(UnsupportedProviderError):
            await TextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", api_key="test-key"), transport=transport).arun("Task", claude_skills=(reference,))
        self.assertEqual(transport.requests, [])

    async def test_explicit_empty_native_options_clear_static_provider_defaults(self) -> None:
        # [Edge Case] direct provider callers can clear configured native fields without mutating the saved config.
        reference = ClaudeSkillReference("skill_clear", "version_clear", ClaudeSkillType.CUSTOM)
        paused_history = ({"role": "user", "content": "Prior"}, {"role": "assistant", "content": [{"type": "server_tool_use", "id": "srv", "name": "code_execution", "input": {}}]})
        config = TextModelConfig(
            provider=ModelProvider.ANTHROPIC,
            model="claude-sonnet-4-6",
            api_key="test-key",
            claude_skills=(reference,),
            claude_skill_session=ClaudeSkillSession("saved_container", True, paused_history),
        )
        transport = _ResponseTransport({"content": [{"type": "text", "text": "Plain."}], "usage": {"input_tokens": 1, "output_tokens": 1}})

        response = await AnthropicProvider(text_config=config).run_text(
            prompt="Plain request",
            system=None,
            metadata=None,
            transport=transport,
            claude_skills=(),
            claude_skill_session=None,
        )

        body = transport.requests[0]["json_body"]
        self.assertNotIn("container", body)
        self.assertNotIn("tools", body)
        self.assertEqual(body["messages"], [{"role": "user", "content": "Plain request"}])
        self.assertIsNone(response.claude_skill_session)
        self.assertEqual(config.claude_skills, (reference,))
        self.assertEqual(config.claude_skill_session.container_id, "saved_container")

    async def test_runner_omission_inherits_native_defaults_and_explicit_none_clears_them(self) -> None:
        # [Hidden Assumption] omitted call fields inherit config, while explicit empty values clear request-local state.
        reference = ClaudeSkillReference("skill_default", "version_default", ClaudeSkillType.CUSTOM)
        session = ClaudeSkillSession(
            "default_container",
            True,
            ({"role": "user", "content": "Saved"}, {"role": "assistant", "content": [{"type": "server_tool_use", "id": "srv_default", "name": "code_execution", "input": {}}]}),
        )
        config = TextModelConfig(
            provider=ModelProvider.ANTHROPIC,
            model="claude-sonnet-4-6",
            api_key="test-key",
            claude_skills=(reference,),
            claude_skill_session=session,
        )
        transport = _QueueResponseTransport((
            {"content": [{"type": "text", "text": "Resumed."}], "container": {"id": "default_container"}, "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}},
            {"content": [{"type": "text", "text": "Plain."}], "usage": {"input_tokens": 1, "output_tokens": 1}},
        ))
        runner = TextModelRunner(config, transport=transport)

        await runner.arun("ignored while paused")
        await runner.arun("Plain call", claude_skills=(), claude_skill_session=None)

        first_body = transport.requests[0]["json_body"]
        second_body = transport.requests[1]["json_body"]
        self.assertEqual(first_body["container"]["id"], "default_container")
        self.assertEqual(first_body["container"]["skills"], [{"type": "custom", "skill_id": "skill_default", "version": "version_default"}])
        self.assertEqual(first_body["messages"], list(session.resume_messages))
        self.assertNotIn("container", second_body)
        self.assertNotIn("tools", second_body)
        self.assertEqual(second_body["messages"], [{"role": "user", "content": "Plain call"}])
        self.assertEqual(config.claude_skills, (reference,))
        self.assertEqual(config.claude_skill_session, session)


class ClaudeSkillSourceTests(unittest.IsolatedAsyncioTestCase):
    """Verifies bounded Claude metadata lookup, explicit auth, and concrete version pinning."""

    async def test_latest_metadata_is_pinned_to_returned_concrete_version(self) -> None:
        # [Silent Failure] Jev's metadata and the eventual Anthropic container use the same immutable version ID.
        list_first = {"data": [{"id": "other", "display_name": "Other", "latest_version_id": "latest_other", "source": {"type": "custom"}}], "next_page": "page token"}
        list_second = {"data": [{"id": "skill_6", "display_name": "Data Cleaning", "latest_version_id": "skver_concrete_6", "source": {"type": "custom"}}], "next_page": None}
        version = {"id": "skver_concrete_6", "skill_id": "skill_6", "name": "data-cleaning", "description": "Clean tabular data"}
        transport = _QueueResponseTransport((list_first, list_second, version))
        source = SkillSource(kind=SkillSourceKind.CLAUDE, location="skill_6", skill_name="data-cleaning", version="latest", api_key="anthropic-secret", workspace_id="workspace_6")

        document = await SkillSourceResolver(transport=transport).resolve(source)

        self.assertIsNone(document.text)
        self.assertEqual(document.name, "data-cleaning")
        self.assertEqual(document.description, "Clean tabular data")
        self.assertEqual(document.source, "claude:skill_6@skver_concrete_6")
        self.assertEqual(document.claude_reference, ClaudeSkillReference("skill_6", "skver_concrete_6", ClaudeSkillType.CUSTOM))
        self.assertIn("/versions/skver_concrete_6", transport.requests[-1]["url"])
        self.assertNotIn("latest", transport.requests[-1]["url"])
        for request in transport.requests:
            self.assertEqual(request["headers"]["x-api-key"], "anthropic-secret")
            self.assertEqual(request["headers"]["anthropic-workspace-id"], "workspace_6")
            self.assertTrue(request["url"].startswith("https://api.anthropic.com/v1/"))
        self.assertNotIn("anthropic-secret", repr(document))

    async def test_provider_error_is_redacted_and_cancellation_propagates(self) -> None:
        # [Hidden Failure] an auth rejection remains a safe candidate failure and cancellation is never swallowed.
        error_transport = _QueueResponseTransport(({"error": {"message": "bad token: anthropic-secret"}},), status_code=401)
        source = SkillSource(kind=SkillSourceKind.CLAUDE, location="skill_7", api_key="anthropic-secret")
        with self.assertRaises(SkillSourceError) as caught:
            await ClaudeSkillSourceAdapter(error_transport).resolve(source)
        self.assertNotIn("anthropic-secret", str(caught.exception))

        class CancelledTransport:
            async def request(self, **request: Any) -> HttpResponse:
                # Models cancellation from the outbound HTTP boundary.
                raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await ClaudeSkillSourceAdapter(CancelledTransport()).resolve(source)  # type: ignore[arg-type]

    async def test_native_response_requires_content_and_container_fields(self) -> None:
        # [Edge Case] missing native continuation state is a typed provider response error.
        transport = _ResponseTransport({"content": [{"type": "text", "text": "Done"}], "stop_reason": "end_turn"})
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        with self.assertRaises(ProviderResponseError):
            await runner.arun("Task", claude_skills=(ClaudeSkillReference("skill_4", "skver_4", ClaudeSkillType.CUSTOM),))

    async def test_native_streaming_is_rejected_without_transport(self) -> None:
        # [Hidden Assumption] streaming cannot silently drop typed native skill options.
        transport = _ResponseTransport({})
        runner = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-4-6", api_key="test-key"), transport=transport)
        with self.assertRaises(UnsupportedProviderError):
            tuple(runner.stream("Task", claude_skills=(ClaudeSkillReference("skill_5", "skver_5", ClaudeSkillType.CUSTOM),)))
        self.assertEqual(transport.requests, [])


class _ResponseTransport:
    """Returns one canned provider response and captures outgoing payloads."""

    def __init__(self, response: dict[str, Any]) -> None:
        # Retains the deterministic response and request bodies for contract assertions.
        self.response = response
        self.requests: list[dict[str, Any]] = []

    async def request(self, **request: Any) -> HttpResponse:
        # Returns exactly one JSON response per requested model exchange.
        self.requests.append(request)
        return HttpResponse(status_code=200, body=json.dumps(self.response), headers={"content-type": "application/json"})


class _QueueResponseTransport:
    """Returns provider records in order and captures bounded request metadata."""

    def __init__(self, responses: tuple[dict[str, Any], ...], *, status_code: int = 200) -> None:
        # Stores response sequence and fixed HTTP status for one adapter resolution.
        self.responses = list(responses)
        self.status_code = status_code
        self.requests: list[dict[str, Any]] = []

    async def request(self, **request: Any) -> HttpResponse:
        # Consumes one record per adapter HTTP exchange.
        self.requests.append(request)
        response = self.responses.pop(0)
        return HttpResponse(status_code=self.status_code, body=json.dumps(response), headers={"content-type": "application/json"})


__all__ = ["ClaudeNativeRunnerTests", "ClaudeSkillSourceTests", "FileSkillSourceTests", "SkillPreloadIntegrationTests", "SkillSourceContractTests"]
