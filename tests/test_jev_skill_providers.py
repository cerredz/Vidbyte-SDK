"""FILE: tests/test_jev_skill_providers.py

PURPOSE: Verifies explicit skill source contracts, bounded FILE resolution, stable failures, and Jev preload integration.
ROLE IN CODEBASE: Covers the first implementation stage of docs/design/jev-skill-providers.md without live provider calls.
ARCHITECTURE NOTE: Tests use temporary files and replace only the TypeSafe/generative model boundaries.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
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
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.dataclasses.skills import (
    ClaudeSkillReference,
    ClaudeSkillSession,
    SkillDocument,
    SkillSource,
)
from vidbyte.lib.enums.jev import JevQuestionType, JevSkillStatus
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.skills import ClaudeSkillType, SkillSourceKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse, TextModelResponse
from vidbyte.providers.skills import SkillSourceError, SkillSourceResolver
from vidbyte.providers.skills.file import _MAX_SKILL_FILE_BYTES, FileSkillSourceAdapter

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


class _CapturingGenerativeRunner:
    """Captures the provider-visible system prompt for one JevAgent run."""

    def __init__(self) -> None:
        # Retains only prompts for assertions in the integration test.
        self.systems: list[str | None] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        # Returns a standard response after recording the exact per-run system option.
        self.systems.append(kwargs.get("system"))
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", text="done", raw={})


class SkillSourceContractTests(unittest.TestCase):
    """Checks the closed source model, compatible options, and stable public exports."""

    def test_source_fields_kind_options_and_secret_repr(self) -> None:
        # [Edge Case] optional fields are accepted only for kinds that define them and keys never appear in repr.
        source = SkillSource(kind=SkillSourceKind.CLAUDE, location="skill_123", version="latest", api_key="private-key", workspace_id="ws_123")
        self.assertNotIn("private-key", repr(source))
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


__all__ = ["FileSkillSourceTests", "SkillPreloadIntegrationTests", "SkillSourceContractTests"]
