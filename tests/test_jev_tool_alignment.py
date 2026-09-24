"""FILE: tests/test_jev_tool_alignment.py

PURPOSE: Verifies JevAgent tool alignment without network access: detection, needs, coverage, the scout's cited-only proposals, fact checks, Jev's candidate checks, the effect policy, attaching for one run only, the output footer, and every fail-open path.
ROLE IN CODEBASE: Covers docs/design/jev-tool-alignment.md; scripts/test-jev-tool-alignment.py and scripts/test-jev-agent-scaffold.py run it.
ARCHITECTURE NOTE: A scripted Jev replaces DecisionModelRunner, scripted generative runners replace the main model and the scout, a fake catalog replaces the provider layer, and a fake MCP handle replaces attach_mcp_server; the production agent, runtime, scout tools, and decision rules stay under test.
COMMON MODIFICATION PATTERNS: Add a case whenever a threshold, a rejection reason, a status branch, or a scout rule changes.
KNOWN EDGE CASES: The main agent uses PermissionPolicy.allow_all() where a test calls an attached EXECUTE tool, since the default policy denies writes by design.
RELATED DOCS: docs/design/jev-tool-alignment.md, skills/asking-jev-questions/SKILL.md, and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_tool_alignment.py and python scripts/test-jev-tool-alignment.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevToolAlignmentSettings, JevToolAlignmentStatus
from vidbyte.agents.jev.alignment.draft import JevToolScoutPass, JevToolScoutPhase
from vidbyte.agents.jev.alignment.questions import TOOL_QUESTIONS, JevToolQuestion
from vidbyte.agents.jev.alignment.result import JevToolEffect, JevToolNeed, JevToolRejection
from vidbyte.agents.jev.alignment.tool import JevToolScoutAction
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.tool_catalogs import (
    CatalogTool,
    ToolCatalogCredentials,
    ToolCatalogEntry,
    ToolInstall,
    ToolSecretRequirement,
)
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind, ToolSecretLocation
from vidbyte.lib.errors import ConfigurationError, McpConnectionError, ProviderRequestError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.providers.tool_catalogs import ToolCatalogProvider
from vidbyte.tools.mcp.types import McpServerConfig, McpServerHandle
from vidbyte.tools.types import ToolResult

PROMPT = "You are the engineering assistant for Acme. You help engineers track bugs and plan work."
REQUEST = "Open a Linear issue titled 'Login fails on Safari' for the web team."
RUNNER_PATH = "vidbyte.agents.jev.alignment.agent.DecisionModelRunner"
ATTACH_PATH = "vidbyte.agents.jev.alignment.agent.attach_mcp_server"
LINEAR_KEY = "mcp_registry:app.linear/linear"
CREATE_ISSUE = CatalogTool(
    name="create_issue",
    description="Create a new issue in a Linear team with a title and an optional description.",
    input_schema={"type": "object", "properties": {"title": {"type": "string", "description": "Issue title."}, "team": {"type": "string"}}, "required": ["title"]},
)
LIST_ISSUES = CatalogTool(name="list_issues", description="List issues in a Linear team.", input_schema={"type": "object", "properties": {"team": {"type": "string"}}})


def _linear_entry(*, installs: Sequence[ToolInstall] | None = None, tools: Sequence[CatalogTool] = (CREATE_ISSUE, LIST_ISSUES)) -> ToolCatalogEntry:
    # The entry the fake catalog returns: a verified remote Linear server.
    return ToolCatalogEntry(
        catalog=ToolCatalogName.MCP_REGISTRY,
        entry_id="app.linear/linear",
        name="Linear",
        description="MCP server for Linear project management and issue tracking.",
        installs=tuple(installs) if installs is not None else (ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url="https://mcp.linear.app/mcp"),),
        tools=tuple(tools),
        version="1.0.0",
        verified=True,
    )


class FakeCatalog(ToolCatalogProvider):
    """A catalog whose search returns fixed entries and whose describe returns them unchanged."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.MCP_REGISTRY

    def __init__(self, *entries: ToolCatalogEntry, fail: bool = False) -> None:
        super().__init__()
        self._fixed = entries
        self.fail = fail
        self.queries: list[str] = []
        self.executed: list[tuple[str, Mapping[str, object], str | None]] = []

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        self.queries.append(query)
        if self.fail:
            raise ProviderRequestError("The mcp_registry catalog returned HTTP 503.", provider="mcp_registry", status_code=503)
        return self._fixed[:limit]

    async def execute(self, entry: ToolCatalogEntry, tool: CatalogTool, arguments: Mapping[str, object], *, user_id: str | None) -> tuple[str, bool]:
        self.executed.append((tool.name, dict(arguments), user_id))
        return "done", False


class DirectCatalog(FakeCatalog):
    """A fake managed platform that runs tools through its execute endpoint, like Arcade."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.ARCADE
    executes_directly: ClassVar[bool] = True


class FakeMcpClient:
    """Records tool calls made through a bridged MCP tool."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        self.calls.append((name, dict(arguments)))
        return ToolResult.success(name, "Created LIN-42.")


class FakeMcpTransport:
    """Tracks whether the session was closed."""

    def __init__(self) -> None:
        self.closed = False

    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        return {}

    async def close(self) -> None:
        self.closed = True


class FakeAttach:
    """Stands in for attach_mcp_server: returns a handle listing the given definitions, or raises."""

    def __init__(self, definitions: Sequence[McpToolDefinition] = (), *, fail: bool = False) -> None:
        self.definitions = tuple(definitions)
        self.fail = fail
        self.configs: list[McpServerConfig] = []
        self.handles: list[McpServerHandle] = []
        self.client = FakeMcpClient()

    async def __call__(self, config: McpServerConfig) -> McpServerHandle:
        self.configs.append(config)
        if self.fail:
            raise McpConnectionError("Failed to start MCP server transport.")
        handle = McpServerHandle(config=config, client=self.client, transport=FakeMcpTransport(), bridged_tools=(), definitions=self.definitions)  # type: ignore[arg-type]
        self.handles.append(handle)
        return handle


def _definition(tool: CatalogTool, **annotations: bool) -> McpToolDefinition:
    return McpToolDefinition(name=tool.name, description=tool.description, input_schema=tool.input_schema, annotations=annotations)


class ScriptedJev:
    """Answers every question from a table of name prefixes: floats for nouls, option names for choices."""

    def __init__(self, table: Mapping[str, float | str] | None = None, *, fail: bool = False) -> None:
        self.table = dict(table or {})
        self.fail = fail
        self.requests: list[JevDecisionRequest] = []

    def __call__(self, config: object = None) -> ScriptedJev:
        return self

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        if self.fail:
            raise ProviderRequestError("TypeSafe is unavailable.", provider="typesafe")
        answers = {question.name: self._answer(question.name, question.question_type, [option.name for option in question.options]) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 10, "output_tokens": 2})

    def asked(self) -> list[str]:
        return [question.name for request in self.requests for question in request.questions]

    def _lookup(self, name: str, default: float | str) -> float | str:
        matches = [prefix for prefix in self.table if name.startswith(prefix)]
        return self.table[max(matches, key=len)] if matches else default

    def _answer(self, name: str, kind: JevQuestionType, options: list[str]) -> JevAnswer:
        if kind is JevQuestionType.CHOICE:
            chosen = str(self._lookup(name, "reads"))
            rest = (1.0 - 0.9) / (len(options) - 1)
            probabilities = {option: (0.9 if option == chosen else rest) for option in options}
            return JevAnswer(question_name=name, question_type=kind, choice=chosen, probabilities=probabilities, confidence=0.9)
        probability = float(self._lookup(name, 0.9))
        choice = "true" if probability >= 0.5 else "false"
        return JevAnswer(question_name=name, question_type=kind, choice=choice, probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


class ScriptedRunner:
    """Minimal generative runner that returns scripted responses and records invocation kwargs."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RawResponse:
    """OpenAI-shaped raw response wrapper for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = ""
        self.raw = raw


def _text(text: str) -> TextModelResponse:
    return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


def _call(name: str, arguments: Mapping[str, Any], call_id: str) -> RawResponse:
    return RawResponse({"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


def _done(call_id: str) -> RawResponse:
    return _call("isDone", {"final_answer": "done"}, call_id)


NEED = {"needs": [{"action": "create", "object": "issue", "system": "Linear"}]}


def _scout(*search_pass: RawResponse) -> ScriptedRunner:
    # The needs pass, then the given search-pass calls, then isDone.
    return ScriptedRunner(_call("write_tool_needs", NEED, "n1"), _done("n2"), *search_pass, _done("s9"))


def _linear_search_pass(tool_names: Sequence[str] = ("create_issue",)) -> tuple[RawResponse, ...]:
    return (
        _call("search_tool_catalogs", {"need_id": "need_1", "query": "linear"}, "s1"),
        _call("describe_catalog_entry", {"entry_key": LINEAR_KEY}, "s2"),
        _call("propose_tool_candidates", {"need_id": "need_1", "entry_key": LINEAR_KEY, "tool_names": list(tool_names)}, "s3"),
    )


def _settings(**tool_overrides: Any) -> JevAgentSettings:
    tool_align = JevToolAlignmentSettings(**tool_overrides)
    return JevAgentSettings(name="assistant", system_prompt=PROMPT, provider="openai", model_name="gpt-4.1-mini", tool_align=tool_align, permission_policy=PermissionPolicy.allow_all())


def _agent(main: ScriptedRunner, scout: ScriptedRunner, catalog: ToolCatalogProvider | None = None, **tool_overrides: Any) -> JevAgent:
    agent = bind_test_runner(JevAgent(_settings(**tool_overrides)), main)
    assert agent.alignment is not None and agent.alignment.tool_scout is not None
    bind_test_runner(agent.alignment.tool_scout, scout)
    fake = catalog or FakeCatalog(_linear_entry())
    agent.alignment._tool_catalogs = {fake.name: fake}
    return agent


# Jev answers that approve create_issue for the Linear request.
APPROVE: Mapping[str, float | str] = {
    "alignment.tools.cover.": 0.1,
    "alignment.tools.need.asks_change": 0.95,
    "alignment.tools.candidate.effect": "writes",
}


class ToolQuestionTests(unittest.TestCase):
    """Pins the shape the asking-jev-questions skill requires for every tool question."""

    def test_questions_are_unique_and_end_with_one_question(self) -> None:
        # [Silent Failure] answers are keyed by name, and each question must carry one recognition step.
        names = [question.name() for question in TOOL_QUESTIONS]
        self.assertEqual(len(names), len(set(names)))
        for question in TOOL_QUESTIONS:
            jev = question.to_jev_question(field_name="tool_1")
            text = str(jev.instructions)
            self.assertTrue(text.rstrip().endswith("?"), question.key)
            self.assertNotIn("{field}", text)
            if jev.question_type is JevQuestionType.NOUL:
                self.assertTrue(all(option.description for option in jev.options))

    def test_effect_is_a_choice_with_a_way_out(self) -> None:
        # [Edge Case] strategy 22: the effect options include `unclear` for descriptions that say nothing.
        effect = next(question for question in TOOL_QUESTIONS if question.key == "candidate.effect")
        jev = effect.to_jev_question()
        self.assertIs(jev.question_type, JevQuestionType.CHOICE)
        self.assertEqual(set(jev.option_names()), {item.value for item in JevToolEffect})

    def test_description_questions_never_read_the_request(self) -> None:
        # [Hidden Assumption] cached description answers must not depend on any user's message.
        for question in TOOL_QUESTIONS:
            if question.key in ("candidate.describes_only", "candidate.effect"):
                self.assertNotIn("`request`", question.to_jev_question().instructions)
        self.assertIsInstance(TOOL_QUESTIONS[0], JevToolQuestion)


class ToolAlignmentSettingsTests(unittest.TestCase):
    """Pins settings validation that must fail before any run."""

    def test_keyed_catalogs_need_credentials_and_managed_ones_need_a_user(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "catalog_credentials"):
            JevToolAlignmentSettings(catalogs=("glama",))
        with self.assertRaisesRegex(ConfigurationError, "user_id"):
            JevToolAlignmentSettings(catalogs=("composio",), catalog_credentials={"composio": ToolCatalogCredentials(api_key="k")})
        settings = JevToolAlignmentSettings(catalogs=("composio",), catalog_credentials={"composio": ToolCatalogCredentials(api_key="k")}, user_id="u1")
        self.assertEqual(settings.catalogs, (ToolCatalogName.COMPOSIO,))
        with self.assertRaisesRegex(ConfigurationError, "environment"):
            JevToolAlignmentSettings(catalogs=("pipedream",), catalog_credentials={"pipedream": ToolCatalogCredentials(client_id="c", client_secret="s", project_id="p", environment="staging")}, user_id="u1")

    def test_install_kinds_and_bounds(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "openapi"):
            JevToolAlignmentSettings(install_kinds=frozenset({"openapi"}))
        with self.assertRaises(ConfigurationError):
            JevToolAlignmentSettings(max_attached_tools=0)
        with self.assertRaises(ConfigurationError):
            JevToolAlignmentSettings(time_budget_seconds=0)
        with self.assertRaises(ConfigurationError):
            JevAgentSettings(name="a", system_prompt="p", provider="openai", model_name="m", tool_align="yes")  # type: ignore[arg-type]

    def test_secrets_and_credentials_stay_out_of_repr(self) -> None:
        # [Security] a logged settings object must never print a key.
        settings = JevToolAlignmentSettings(secrets={"LINEAR_API_KEY": "sk-live-123"}, catalogs=("glama",), catalog_credentials={"glama": ToolCatalogCredentials(api_key="glama-secret")})
        self.assertNotIn("sk-live-123", repr(settings))
        self.assertNotIn("glama-secret", repr(settings))


class ToolAlignmentRunTests(unittest.IsolatedAsyncioTestCase):
    """Pins the full pass through a real JevAgent run."""

    async def test_tool_align_off_makes_no_jev_call(self) -> None:
        # [Edge Case] without tool_align the agent behaves exactly like the scaffold.
        jev = ScriptedJev()
        agent = bind_test_runner(JevAgent(JevAgentSettings(name="a", system_prompt=PROMPT, provider="openai", model_name="gpt-4.1-mini")), ScriptedRunner(_text("ok")))
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun(REQUEST)
        self.assertEqual(jev.requests, [])
        self.assertNotIn("jev_tool_alignment", reply.metadata)

    async def test_request_without_outside_action_stops_after_one_call(self) -> None:
        # [Edge Case] the cheap path: one Jev request, no scout, no catalog search.
        jev = ScriptedJev({"alignment.tools.detect.outside_action": 0.1})
        scout = ScriptedRunner()
        catalog = FakeCatalog(_linear_entry())
        agent = _agent(ScriptedRunner(_text("OAuth is ...")), scout, catalog)
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Explain how OAuth works.")
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.status, JevToolAlignmentStatus.NOT_NEEDED)
        self.assertEqual(len(jev.requests), 1)
        self.assertEqual(scout.calls, [])
        self.assertEqual(catalog.queries, [])
        self.assertEqual(reply.content, "OAuth is ...")

    async def test_out_of_scope_request_never_gains_tools(self) -> None:
        # [Hidden Failure] an off-topic request must not widen what the agent can do.
        jev = ScriptedJev({"alignment.fit.task_in_scope": 0.1})
        scout = ScriptedRunner()
        agent = _agent(ScriptedRunner(_text("I only help with engineering work.")), scout)
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun("Book me a flight to Paris.")
        self.assertIs(reply.metadata["jev_tool_alignment"].status, JevToolAlignmentStatus.OUT_OF_SCOPE)
        self.assertEqual(scout.calls, [])

    async def test_need_covered_by_an_existing_tool_skips_the_search(self) -> None:
        # [Edge Case] an existing tool that performs the need means no catalog is searched.
        jev = ScriptedJev({"alignment.tools.cover.": 0.9})
        scout = ScriptedRunner(_call("write_tool_needs", NEED, "n1"), _done("n2"))
        catalog = FakeCatalog(_linear_entry())
        agent = _agent(ScriptedRunner(_text("done")), scout, catalog)
        agent.add_tool(_existing_tool())
        with patch(RUNNER_PATH, jev):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.status, JevToolAlignmentStatus.COVERED)
        self.assertEqual(result.needs[0].covered_by, ("linear_create_issue",))
        self.assertEqual(catalog.queries, [])

    async def test_approved_tool_is_attached_used_announced_and_released(self) -> None:
        # [Silent Failure] the main model calls the attached tool, users see it in the output, and nothing persists.
        jev = ScriptedJev(APPROVE)
        attach = FakeAttach([_definition(CREATE_ISSUE), _definition(LIST_ISSUES)])
        main = ScriptedRunner(_call("Linear__create_issue", {"title": "Login fails on Safari"}, "m1"), _call("isDone", {"final_answer": "Opened LIN-42."}, "m2"))
        agent = _agent(main, _scout(*_linear_search_pass()))
        with patch(RUNNER_PATH, jev), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.status, JevToolAlignmentStatus.ATTACHED)
        attached = result.attached[0]
        self.assertEqual((attached.name, attached.original_name, attached.entry_id, attached.location), ("Linear__create_issue", "create_issue", "app.linear/linear", "https://mcp.linear.app/mcp"))
        self.assertIs(attached.effect, JevToolEffect.WRITES)
        self.assertEqual(attach.client.calls, [("create_issue", {"title": "Login fails on Safari"})])
        self.assertIn("Tools added for this request:", reply.content)
        self.assertIn("Linear__create_issue", reply.content)
        self.assertTrue(attach.handles[0].transport.closed)
        self.assertEqual(attach.configs[0].tool_allowlist, ())
        self.assertNotIn("Linear__create_issue", [tool.name for tool in agent.tools])
        self.assertGreater(result.usage.input_tokens, 0)

    async def test_injected_description_is_rejected_and_its_session_closed(self) -> None:
        # [Security] a description that instructs the AI never attaches, however well it matches.
        jev = ScriptedJev({**APPROVE, "alignment.tools.candidate.describes_only": 0.3})
        attach = FakeAttach([_definition(CREATE_ISSUE)])
        agent = _agent(ScriptedRunner(_text("I cannot open issues.")), _scout(*_linear_search_pass()))
        with patch(RUNNER_PATH, jev), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.status, JevToolAlignmentStatus.NO_MATCH)
        self.assertIs(result.rejected[0].rejection, JevToolRejection.INSTRUCTIONS_IN_DESCRIPTION)
        self.assertTrue(attach.handles[0].transport.closed)
        self.assertNotIn("Tools added", reply.content)

    async def test_write_tool_needs_a_request_that_asks_for_a_change(self) -> None:
        # [Hidden Failure] a read-only request cannot attach a tool that writes.
        jev = ScriptedJev({**APPROVE, "alignment.tools.need.asks_change": 0.1})
        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()))
        with patch(RUNNER_PATH, jev), patch(ATTACH_PATH, FakeAttach([_definition(CREATE_ISSUE)])):
            reply = await agent.arun(REQUEST)
        self.assertIs(reply.metadata["jev_tool_alignment"].rejected[0].rejection, JevToolRejection.EFFECT_NOT_ALLOWED)

    async def test_declared_destructive_hint_needs_the_owners_permission(self) -> None:
        # [Security] a server's destructive hint overrides Jev's "reads", and high-impact tools need allow_high_impact.
        jev = ScriptedJev({**APPROVE, "alignment.tools.candidate.effect": "reads"})
        attach = FakeAttach([_definition(CREATE_ISSUE, destructiveHint=True)])
        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()))
        with patch(RUNNER_PATH, jev), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.rejected[0].effect, JevToolEffect.SENDS_OR_DELETES)
        self.assertIs(result.rejected[0].rejection, JevToolRejection.EFFECT_NOT_ALLOWED)
        self.assertTrue(any("allow_high_impact" in action for action in result.owner_actions))

    async def test_missing_secret_becomes_an_owner_action_without_connecting(self) -> None:
        # [Hidden Failure] nothing connects without its required secret, and the owner is told which one to set.
        secret = ToolSecretRequirement(name="LINEAR_API_KEY", location=ToolSecretLocation.HEADER, target="Authorization", template="Bearer {value}")
        entry = _linear_entry(installs=(ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url="https://mcp.linear.app/mcp", secrets=(secret,)),))
        attach = FakeAttach([_definition(CREATE_ISSUE)])
        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()), FakeCatalog(entry))
        with patch(RUNNER_PATH, ScriptedJev(APPROVE)), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.rejected[0].rejection, JevToolRejection.MISSING_CREDENTIAL)
        self.assertIn("LINEAR_API_KEY", result.owner_actions[0])
        self.assertEqual(attach.configs, [])

    async def test_configured_secret_is_sent_only_where_declared(self) -> None:
        # [Security] a header secret goes into the header the install names, rendered by its template.
        secret = ToolSecretRequirement(name="LINEAR_API_KEY", location=ToolSecretLocation.HEADER, target="Authorization", template="Bearer {value}")
        entry = _linear_entry(installs=(ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url="https://mcp.linear.app/mcp", secrets=(secret,)),))
        attach = FakeAttach([_definition(CREATE_ISSUE)])
        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()), FakeCatalog(entry), secrets={"LINEAR_API_KEY": "sk-1"})
        with patch(RUNNER_PATH, ScriptedJev(APPROVE)), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        self.assertEqual(dict(attach.configs[0].headers or {}), {"Authorization": "Bearer sk-1"})
        self.assertNotIn("sk-1", json.dumps([record.location for record in reply.metadata["jev_tool_alignment"].attached]))

    async def test_local_install_kinds_are_opt_in(self) -> None:
        # [Security] a container is never started unless the owner allowed container installs.
        entry = _linear_entry(installs=(ToolInstall(kind=ToolInstallKind.CONTAINER, command=("docker", "run", "-i", "--rm", "mcp/linear@sha256:abc")),))
        attach = FakeAttach([_definition(CREATE_ISSUE)])
        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()), FakeCatalog(entry))
        with patch(RUNNER_PATH, ScriptedJev(APPROVE)), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.rejected[0].rejection, JevToolRejection.INSTALL_NOT_ALLOWED)
        self.assertIn("container", result.owner_actions[0])
        self.assertEqual(attach.configs, [])

    async def test_connection_failure_is_reported_and_the_run_continues(self) -> None:
        # [Hidden Failure] a server that refuses the connection is a rejection, not a failed run.
        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()))
        with patch(RUNNER_PATH, ScriptedJev(APPROVE)), patch(ATTACH_PATH, FakeAttach(fail=True)):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.rejected[0].rejection, JevToolRejection.CONNECT_FAILED)
        self.assertEqual(result.rejected[0].detail, "McpConnectionError")
        self.assertEqual(reply.content, "ok")

    async def test_jev_outage_fails_open_with_original_tools(self) -> None:
        # [Silent Failure] no Jev means no tools are added, and the main run still happens.
        scout = ScriptedRunner()
        agent = _agent(ScriptedRunner(_text("ok")), scout)
        with patch(RUNNER_PATH, ScriptedJev(fail=True)):
            reply = await agent.arun(REQUEST)
        self.assertIs(reply.metadata["jev_tool_alignment"].status, JevToolAlignmentStatus.UNAVAILABLE)
        self.assertEqual(reply.content, "ok")
        self.assertEqual(scout.calls, [])

    async def test_time_budget_fails_open_and_closes_opened_sessions(self) -> None:
        # [Silent Failure] a slow pass is abandoned, and every session it opened is closed.
        attach = FakeAttach([_definition(CREATE_ISSUE)])

        class SlowJev(ScriptedJev):
            async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
                if any(question.name.startswith("alignment.tools.candidate") for question in request.questions):
                    await asyncio.sleep(5)
                return await super().arun(request)

        agent = _agent(ScriptedRunner(_text("ok")), _scout(*_linear_search_pass()), time_budget_seconds=0.5)
        with patch(RUNNER_PATH, SlowJev(APPROVE)), patch(ATTACH_PATH, attach):
            reply = await agent.arun(REQUEST)
        self.assertIs(reply.metadata["jev_tool_alignment"].status, JevToolAlignmentStatus.UNAVAILABLE)
        self.assertTrue(attach.handles[0].transport.closed)

    async def test_catalog_failure_is_recorded_per_catalog(self) -> None:
        # [Hidden Failure] a failing catalog's error is reported, and the pass ends without a match.
        agent = _agent(ScriptedRunner(_text("ok")), _scout(_call("search_tool_catalogs", {"need_id": "need_1", "query": "linear"}, "s1")), FakeCatalog(fail=True))
        with patch(RUNNER_PATH, ScriptedJev(APPROVE)):
            reply = await agent.arun(REQUEST)
        result = reply.metadata["jev_tool_alignment"]
        self.assertIs(result.status, JevToolAlignmentStatus.NO_MATCH)
        self.assertIn("503", result.provider_errors["mcp_registry"])

    async def test_description_answers_are_cached_across_runs(self) -> None:
        # [Edge Case] describes_only and effect depend only on the description, so a second run does not ask them again.
        jev = ScriptedJev(APPROVE)
        agent = _agent(ScriptedRunner(_text("one"), _text("two")), ScriptedRunner(*_scout(*_linear_search_pass()).responses, *_scout(*_linear_search_pass()).responses))
        with patch(RUNNER_PATH, jev), patch(ATTACH_PATH, FakeAttach([_definition(CREATE_ISSUE)])):
            await agent.arun(REQUEST)
            await agent.arun(REQUEST)
        self.assertEqual(sum(1 for name in jev.asked() if name.startswith("alignment.tools.candidate.describes_only")), 1)

    async def test_prompt_alignment_gate_answer_is_reused(self) -> None:
        # [Edge Case] with self_align on, the scope gate is asked once, by prompt alignment.
        jev = ScriptedJev({"alignment.tools.detect.outside_action": 0.1})
        settings = JevAgentSettings(name="a", system_prompt=PROMPT, provider="openai", model_name="gpt-4.1-mini", self_align=True, tool_align=JevToolAlignmentSettings())
        agent = bind_test_runner(JevAgent(settings), ScriptedRunner(_text("ok")))
        with patch(RUNNER_PATH, jev):
            await agent.arun("Explain our bug triage process.")
        self.assertEqual(jev.asked().count("alignment.fit.task_in_scope"), 1)

    async def test_direct_execute_platform_tool_runs_on_the_platform(self) -> None:
        # [Silent Failure] a platform like Arcade runs the judged tool for the configured end user.
        tool = CatalogTool(name="Linear.CreateIssue", description=CREATE_ISSUE.description, input_schema=CREATE_ISSUE.input_schema, read_only=False)
        entry = ToolCatalogEntry(catalog=ToolCatalogName.ARCADE, entry_id="Linear", name="Linear", description="Arcade Linear toolkit.", installs=(ToolInstall(kind=ToolInstallKind.MANAGED, reference="Linear"),), tools=(tool,), verified=True)
        catalog = DirectCatalog(entry)
        search_pass = (
            _call("search_tool_catalogs", {"need_id": "need_1", "query": "linear"}, "s1"),
            _call("describe_catalog_entry", {"entry_key": "arcade:Linear"}, "s2"),
            _call("propose_tool_candidates", {"need_id": "need_1", "entry_key": "arcade:Linear", "tool_names": ["Linear.CreateIssue"]}, "s3"),
        )
        main = ScriptedRunner(_call("Linear__Linear_CreateIssue", {"title": "Login fails"}, "m1"), _call("isDone", {"final_answer": "done"}, "m2"))
        agent = _agent(main, _scout(*search_pass), catalog)
        with patch(RUNNER_PATH, ScriptedJev(APPROVE)):
            reply = await agent.arun(REQUEST)
        self.assertIs(reply.metadata["jev_tool_alignment"].status, JevToolAlignmentStatus.ATTACHED)
        self.assertEqual(catalog.executed, [("Linear.CreateIssue", {"title": "Login fails"}, None)])


class ScoutRuleTests(unittest.IsolatedAsyncioTestCase):
    """Pins the scout's phase and citation rules, which live in JevAgentAlignment."""

    def _alignment_and_pass(self) -> tuple[Any, JevToolScoutPass]:
        agent = _agent(ScriptedRunner(), ScriptedRunner())
        scout_pass = JevToolScoutPass(request=REQUEST, phase=JevToolScoutPhase.SEARCH)
        scout_pass.needs = [JevToolNeed(need_id="need_1", action="create", object="issue", system="Linear", sentence="create issue in Linear")]
        return agent.alignment, scout_pass

    async def test_actions_outside_the_phase_are_refused(self) -> None:
        alignment, scout_pass = self._alignment_and_pass()
        scout_pass.phase = JevToolScoutPhase.NEEDS
        result = await alignment._handle_scout_action(scout_pass, JevToolScoutAction.SEARCH, {"need_id": "need_1", "query": "linear"})
        self.assertIn("not available in the needs pass", result.output)

    async def test_proposals_must_cite_described_entries_and_listed_tools(self) -> None:
        # [Security] the scout cannot invent an entry, skip describe, or name a tool the entry does not list.
        alignment, scout_pass = self._alignment_and_pass()
        propose = JevToolScoutAction.PROPOSE
        unseen = await alignment._handle_scout_action(scout_pass, propose, {"need_id": "need_1", "entry_key": LINEAR_KEY, "tool_names": ["create_issue"]})
        self.assertIn("describe_catalog_entry this entry_key", unseen.output)
        await alignment._handle_scout_action(scout_pass, JevToolScoutAction.SEARCH, {"need_id": "need_1", "query": "linear"})
        await alignment._handle_scout_action(scout_pass, JevToolScoutAction.DESCRIBE, {"entry_key": LINEAR_KEY})
        invented = await alignment._handle_scout_action(scout_pass, propose, {"need_id": "need_1", "entry_key": LINEAR_KEY, "tool_names": ["delete_everything"]})
        self.assertIn("not listed", invented.output)
        wrong_need = await alignment._handle_scout_action(scout_pass, propose, {"need_id": "need_9", "entry_key": LINEAR_KEY, "tool_names": ["create_issue"]})
        self.assertIn("uncovered needs", wrong_need.output)
        accepted = await alignment._handle_scout_action(scout_pass, propose, {"need_id": "need_1", "entry_key": LINEAR_KEY, "tool_names": ["create_issue"]})
        self.assertIn("Proposed 1 tool", accepted.output)
        self.assertEqual(len(scout_pass.proposals), 1)

    async def test_needs_are_bounded_and_their_sentence_is_built_in_code(self) -> None:
        alignment, scout_pass = self._alignment_and_pass()
        scout_pass.phase = JevToolScoutPhase.NEEDS
        too_many = await alignment._handle_scout_action(scout_pass, JevToolScoutAction.WRITE_NEEDS, {"needs": [{"action": "a", "object": "b"}] * 4})
        self.assertIn("Refused", too_many.output)
        await alignment._handle_scout_action(scout_pass, JevToolScoutAction.WRITE_NEEDS, {"needs": [{"action": "search", "object": "web pages"}]})
        self.assertEqual(scout_pass.needs[0].sentence, "search web pages")
        self.assertIsNone(scout_pass.needs[0].system)


def _existing_tool() -> Any:
    # An existing agent tool whose description performs the Linear need.
    from vidbyte.tools import tool

    @tool(name="linear_create_issue", description="Create an issue in Linear.")
    def linear_create_issue(title: str) -> str:
        """Create an issue in Linear."""
        return "ok"

    return linear_create_issue


if __name__ == "__main__":
    unittest.main()
