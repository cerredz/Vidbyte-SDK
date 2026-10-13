"""FILE: tests/features/sdk_provider_keys/test_provider_keys_agents.py

PURPOSE: Proves that agents match api_keys once, at the root, and that every call an agent makes carries only its own provider's matched key: list order changes nothing, a failed relay falls back with the backup's own key, a fallback or fork without a key goes Vidbyte-paid, every child carries the root's ProviderKeys and model_mode, an aggregate's spec-built models all need their keys, and image and audio models get their provider's matched key.
ROLE IN CODEBASE: Agent layer of tests/features/sdk_provider_keys/ (spec AC-7, AC-16 to AC-18, AC-23, AC-25, AC-26, AC-31, AC-33, AC-34, AC-37, AC-38; INV-3, INV-15, INV-23, INV-24, INV-25; EC-11, EC-29, EC-47, EC-48, EC-57). Exercises vidbyte/agents/base.py, fallback.py, fork.py, aggregation.py, handoff.py, vidbyte/trace/continual, vidbyte/agents/jev and vidbyte/lib/runners/utility.py with real TextModelRunner instances.
ARCHITECTURE NOTE: Agents build their own TextModelRunner, which looks HttpTransport up in vidbyte.lib.runners.text, so RUNNER_TRANSPORT_TARGET is replaced by a ScriptedGateway (ordered answers) or a ProviderRouter (answers by provider, for concurrent aggregate children). Nothing above the inner transport is faked.
COMMON MODIFICATION PATTERNS: When a new agent-building surface appears, add it to the children test with the same "carries the root's record and mode" assertion. Keep each run's answers in the dialect of the provider that receives them (provider_keys_fixtures.done_answer).
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols (TextModelMode.DIRECT, ProviderKeys) at module level. 2. Do not bind a fake runner where the test is about which key a real request carries; use the transport seam. 3. Do not compare ProviderKeys records from differently ordered lists with ==; compare key_view, because the spec keeps first-appearance order.
KNOWN EDGE CASES: A relayed provider 401 is a fallback error (DEFAULT_FALLBACK_ERRORS holds ProviderRequestError), so a ScriptedGateway whose first answer is a relayed 401 drives the chain to its backup. Aggregate proposers run concurrently, so their requests are checked per provider, never by position.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 5, 6.1, 6.2, 8.1 (D-13, D-27, D-29) and 9.2.
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_agents.py
"""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    RUNNER_TRANSPORT_TARGET,
    VIDBYTE_KEY,
    ScriptedGateway,
    header,
    relayed_provider_error,
)
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_OPENAI,
    K_SK_UNPROVEN,
    K_SK_UNPROVEN_2,
    K_UNPROVEN,
    K_UNPROVEN_2,
    K_XAI,
    ProviderRouter,
    RecordingEnviron,
    anthropic_done,
    chat_done,
    flat,
    key_view,
    provider_key_header,
    responses_done,
)
from vidbyte import Agent
from vidbyte.agents import AgentForkSettings, BaseAgent
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError

CREDENTIAL_ERROR_KIND = "vidbyte_managed_credentials"


def without_idempotency(request: dict[str, Any]) -> tuple[str, dict[str, str], Any]:
    # A request with its per-call Idempotency-Key removed, so two runs of the same agent can be compared.
    headers = {name.lower(): value for name, value in request["headers"].items() if name.lower() != "idempotency-key"}
    return request["url"], headers, request["json_body"]


def assert_no_key_text(case: unittest.TestCase, error: BaseException, *keys: str) -> str:
    # Every key-related refusal names indexes and providers, never key characters (D-17).
    message = str(error)
    rendered = message + repr(getattr(error, "details", {}))
    for key in keys:
        case.assertNotIn(key, rendered)
    return message


class AgentRelayTests(unittest.TestCase):
    """What each call of a running agent carries (AC-7, AC-16, AC-17, AC-26, AC-31, AC-33, AC-38)."""

    def _run_xai_with_anthropic_backup(self, api_keys: list[str], *steps: Any) -> tuple[Any, Any, ScriptedGateway]:
        # Builds the section 4 agent with a scripted gateway and runs it once.
        gateway = ScriptedGateway(*steps)
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            agent = Agent(name="researcher", system_prompt="Answer in one word.", provider="xai", model_name="grok-4.5", vidbyte_api_key=VIDBYTE_KEY, api_keys=api_keys, fallback=["anthropic/claude-sonnet-5"])
            reply = agent.run("Say hi.")
        return agent, reply, gateway

    def test_list_order_changes_neither_the_match_nor_any_request(self) -> None:
        # AC-7, INV-9, NFR-2: [K_x, K_a] and [K_a, K_x] give the same matching and byte-identical requests.
        views, runs = [], []
        for api_keys in ([K_XAI, K_ANTHROPIC], [K_ANTHROPIC, K_XAI]):
            with self.subTest(order=[key[:4] for key in api_keys]):
                agent, reply, gateway = self._run_xai_with_anthropic_backup(api_keys, relayed_provider_error(ModelProvider.XAI, 401), anthropic_done("Hi"))
                self.assertEqual(reply.content, "Hi")
                views.append(key_view(agent.runner_config.api_keys))
                runs.append([without_idempotency(request) for request in gateway.requests])
                xai_call, anthropic_call = gateway.requests
                self.assertEqual(provider_key_header(xai_call), K_XAI)
                self.assertEqual(provider_key_header(anthropic_call), K_ANTHROPIC)
                self.assertNotIn(K_ANTHROPIC, flat(xai_call))
                self.assertNotIn(K_XAI, flat(anthropic_call))
        self.assertEqual(views[0], views[1])
        self.assertEqual(views[0][0], {"xai": K_XAI, "anthropic": K_ANTHROPIC})
        self.assertEqual(views[0][1], VIDBYTE_KEY)
        self.assertEqual(runs[0], runs[1])

    def test_a_relayed_401_falls_back_and_each_call_carries_only_its_own_providers_key(self) -> None:
        # AC-16, INV-1, INV-3: two gateway POSTs, the first with only the xAI key, the second with only the Anthropic key.
        _, reply, gateway = self._run_xai_with_anthropic_backup([K_XAI, K_ANTHROPIC], relayed_provider_error(ModelProvider.XAI, 401), anthropic_done("Claude says hi"))
        self.assertEqual(reply.content, "Claude says hi")
        self.assertEqual(len(gateway.requests), 2)
        self.assertEqual([request["url"] for request in gateway.requests], [GATEWAY_URL, GATEWAY_URL])
        self.assertEqual([request["json_body"]["provider"] for request in gateway.requests], ["xai", "anthropic"])
        for request, own, other in ((gateway.requests[0], K_XAI, K_ANTHROPIC), (gateway.requests[1], K_ANTHROPIC, K_XAI)):
            self.assertEqual(header(request, "authorization"), f"Bearer {VIDBYTE_KEY}")
            self.assertEqual(provider_key_header(request), own)
            self.assertNotIn(other, flat(request))

    def test_a_backup_without_a_matched_key_goes_vidbyte_paid_once_the_primary_holds_its_key(self) -> None:
        # AC-17, EC-11, EC-29, INV-15: construction succeeds; the anthropic call carries no provider-key header.
        _, reply, gateway = self._run_xai_with_anthropic_backup([K_XAI], relayed_provider_error(ModelProvider.XAI, 401), anthropic_done("Claude says hi"))
        self.assertEqual(reply.content, "Claude says hi")
        xai_call, anthropic_call = gateway.requests
        self.assertEqual(provider_key_header(xai_call), K_XAI)
        self.assertEqual(anthropic_call["json_body"]["provider"], "anthropic")
        self.assertIsNone(provider_key_header(anthropic_call))
        self.assertEqual({name.lower() for name in anthropic_call["headers"]}, {"authorization", "content-type", "idempotency-key"})
        self.assertNotIn(K_XAI, flat(anthropic_call))

    def test_an_unproven_key_reaches_only_the_backup_it_was_bound_to_in_either_order(self) -> None:
        # AC-31, INV-3, INV-25, D-2: anthropic takes no unproven key, so K_u's one possible owner is the deepseek backup.
        for api_keys in ([K_ANTHROPIC, K_UNPROVEN], [K_UNPROVEN, K_ANTHROPIC]):
            with self.subTest(first=api_keys[0][:6]):
                gateway = ScriptedGateway(relayed_provider_error(ModelProvider.ANTHROPIC, 401), chat_done("DeepSeek says hi"))
                with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
                    agent = Agent(name="writer", system_prompt="Answer.", provider="anthropic", model_name="claude-sonnet-5", vidbyte_api_key=VIDBYTE_KEY, api_keys=api_keys, fallback=["deepseek/deepseek-chat"])
                    reply = agent.run("Say hi.")
                self.assertEqual(reply.content, "DeepSeek says hi")
                anthropic_call, deepseek_call = gateway.requests
                self.assertEqual((anthropic_call["json_body"]["provider"], deepseek_call["json_body"]["provider"]), ("anthropic", "deepseek"))
                self.assertEqual(provider_key_header(anthropic_call), K_ANTHROPIC)
                self.assertEqual(provider_key_header(deepseek_call), K_UNPROVEN)
                self.assertNotIn(K_UNPROVEN, flat(anthropic_call))

    def test_a_lone_unproven_key_binds_to_the_agents_own_provider_and_its_openai_backup_goes_vidbyte_paid(self) -> None:
        # AC-38 (first case), D-29, NFR-12: the commonest migration, api_key=k -> api_keys=[k], stays mechanical.
        gateway = ScriptedGateway(relayed_provider_error(ModelProvider.DEEPSEEK, 401), responses_done("OpenAI says hi"))
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            agent = Agent(name="coder", system_prompt="Answer.", provider="deepseek", model_name="deepseek-chat", api_keys=[K_SK_UNPROVEN], fallback=["openai/gpt-5.5"], vidbyte_api_key=VIDBYTE_KEY)
            reply = agent.run("Say hi.")
        self.assertEqual(key_view(agent.runner_config.api_keys)[0], {"deepseek": K_SK_UNPROVEN})
        self.assertEqual(reply.content, "OpenAI says hi")
        deepseek_call, openai_call = gateway.requests
        self.assertEqual(provider_key_header(deepseek_call), K_SK_UNPROVEN)
        self.assertEqual(openai_call["json_body"]["provider"], "openai")
        self.assertIsNone(provider_key_header(openai_call))
        self.assertNotIn(K_SK_UNPROVEN, flat(openai_call))

    def test_two_unproven_sk_keys_for_a_deepseek_agent_with_an_openai_backup_are_refused_as_ambiguous(self) -> None:
        # AC-38 (second case), M-19, INV-25: both keys could belong to deepseek or openai, so the root refuses instead of guessing.
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigurationError) as caught:
            Agent(name="coder", system_prompt="Answer.", provider="deepseek", model_name="deepseek-chat", api_keys=[K_SK_UNPROVEN, K_SK_UNPROVEN_2], fallback=["openai/gpt-5.5"], vidbyte_api_key=VIDBYTE_KEY)
        message = assert_no_key_text(self, caught.exception, K_SK_UNPROVEN, K_SK_UNPROVEN_2, VIDBYTE_KEY)
        for fact in ("api_keys[0]", str(len(K_SK_UNPROVEN)), "deepseek", "openai", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
            self.assertIn(fact, message)

    def test_an_agent_without_any_vidbyte_key_builds_and_its_first_run_raises_the_missing_key_error_before_any_request(self) -> None:
        # AC-26, INV-7, INV-23, D-18: construction stays environment-free; the runner refuses when the run builds it.
        gateway = ScriptedGateway(responses_done("never"))
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            agent = Agent(name="greeter", system_prompt="Answer.", provider="openai", model_name="gpt-5.5", api_keys=[K_OPENAI])
            with self.assertRaises(AgentExecutionError) as caught:
                agent.run("Say hi.")
        cause = caught.exception.__cause__
        self.assertIsInstance(cause, ConfigurationError)
        assert isinstance(cause, ConfigurationError)
        self.assertEqual(cause.details.get("error_kind"), CREDENTIAL_ERROR_KIND)
        for fact in ("VIDBYTE_API_KEY", "vidbyte_api_key", "TextModelMode.DIRECT"):
            self.assertIn(fact, str(cause))
        self.assertEqual(gateway.requests, [])

    def test_a_list_without_the_agents_own_providers_key_is_refused_while_an_empty_or_vidbyte_only_list_goes_vidbyte_paid(self) -> None:
        # AC-33, INV-24, M-18: a wrong key can never silently turn an intended relay into a cost-plus-fee call.
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError) as caught:
                Agent(name="greeter", system_prompt="Answer.", provider="openai", model_name="gpt-5.5", api_keys=[K_XAI], vidbyte_api_key=VIDBYTE_KEY)
            message = assert_no_key_text(self, caught.exception, K_XAI, VIDBYTE_KEY)
            self.assertIn("openai", message)
            self.assertIn("xai", message)
            self.assertIn("OPENAI_API_KEY", message)
            with self.assertRaises(ConfigurationError) as config_caught:
                from vidbyte.lib.config import TextModelConfig

                TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_XAI])
            config_message = assert_no_key_text(self, config_caught.exception, K_XAI)
            self.assertIn("openai", config_message)
            self.assertIn("xai", config_message)

        for api_keys in ([], [VIDBYTE_KEY]):
            with self.subTest(api_keys=len(api_keys)):
                gateway = ScriptedGateway(responses_done("Hi"))
                with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
                    agent = Agent(name="greeter", system_prompt="Answer.", provider="openai", model_name="gpt-5.5", api_keys=api_keys, vidbyte_api_key=VIDBYTE_KEY)
                    reply = agent.run("Say hi.")
                self.assertEqual(reply.content, "Hi")
                [sent] = gateway.requests
                self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertIsNone(provider_key_header(sent))

    def test_building_an_agent_reads_no_api_key_variable(self) -> None:
        # INV-23: matching reads no environment; keys from the environment are read only when a runner is built.
        environment = RecordingEnviron({"OPENAI_API_KEY": K_OPENAI, "ANTHROPIC_API_KEY": K_ANTHROPIC, "VIDBYTE_API_KEY": VIDBYTE_KEY})
        with patch.object(os, "environ", environment):
            Agent(name="greeter", system_prompt="Answer.", provider="xai", model_name="grok-4.5", api_keys=[K_XAI], vidbyte_api_key=VIDBYTE_KEY, fallback=["anthropic/claude-sonnet-5", "openai/gpt-5.5"])
        self.assertEqual([name for name in environment.reads if name.endswith("_API_KEY")], [])

    def test_model_mode_must_be_the_enum(self) -> None:
        # AC-25, EC-44, D-9, M-16: a string or None is refused at construction; the enum member works.
        from vidbyte.lib.config import TextModelMode

        for bad in ("direct", None):
            with self.subTest(model_mode=bad), self.assertRaises(ConfigurationError) as caught:
                Agent(name="greeter", system_prompt="Answer.", provider="openai", model_name="gpt-5.5", model_mode=bad)  # type: ignore[arg-type]
            self.assertIn("model_mode must be a TextModelMode value", str(caught.exception))
        agent = Agent(name="greeter", system_prompt="Answer.", provider="openai", model_name="gpt-5.5", model_mode=TextModelMode.DIRECT)
        self.assertIs(agent.runner_config.model_mode, TextModelMode.DIRECT)
        self.assertIs(Agent(name="greeter", system_prompt="Answer.", provider="openai", model_name="gpt-5.5").runner_config.model_mode, TextModelMode.AUTO)


class AgentRootRefusalTests(unittest.TestCase):
    """Lists an agent root refuses before any request (AC-9, AC-32, AC-37, EC-46, EC-48)."""

    def test_a_key_no_configured_provider_can_take_is_refused_naming_its_index_length_and_the_providers(self) -> None:
        # AC-9 (first case), EC-46, M-6: anthropic takes only sk-ant- keys, and nothing else is configured.
        entry = "not-a-key-123"
        gateway = ScriptedGateway(anthropic_done("never"))
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            with self.assertRaises(ConfigurationError) as caught:
                Agent(name="writer", system_prompt="Answer.", provider="anthropic", model_name="claude-sonnet-5", api_keys=[K_ANTHROPIC, entry])
        message = assert_no_key_text(self, caught.exception, entry, K_ANTHROPIC)
        for fact in ("api_keys[1]", "13", "anthropic", "environment variable"):
            self.assertIn(fact, message)
        self.assertEqual(gateway.requests, [])

    def test_an_entry_with_a_space_or_line_break_is_refused_before_anything_else(self) -> None:
        # AC-9 (second case), EC-10, T-5, M-6b: a header-injection attempt never reaches a header.
        for entry in ("xai-abc\r\nX-Other: y", "sk-ant-abc def", "d-mocké"):
            with self.subTest(entry=repr(entry)), patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigurationError) as caught:
                Agent(name="writer", system_prompt="Answer.", provider="xai", model_name="grok-4.5", api_keys=[K_XAI, entry])
            message = assert_no_key_text(self, caught.exception, entry, K_XAI)
            self.assertIn("api_keys[1]", message)
            self.assertIn(str(len(entry)), message)

    def test_two_unproven_keys_two_providers_could_take_are_refused_and_a_lone_one_binds_to_the_primary(self) -> None:
        # AC-32, EC-35, M-19, D-29: the SDK never guesses between deepseek and kimi; the developer moves one key to its variable.
        cases = (
            ("deepseek", "deepseek-chat", ["kimi/kimi-k2.7-code"], [K_UNPROVEN, K_UNPROVEN_2], "api_keys[0]", K_UNPROVEN),
            ("anthropic", "claude-sonnet-5", ["deepseek/deepseek-chat", "kimi/kimi-k2.7-code"], [K_ANTHROPIC, K_UNPROVEN], "api_keys[1]", K_UNPROVEN),
        )
        for provider, model, fallback, api_keys, index, entry in cases:
            with self.subTest(provider=provider), patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigurationError) as caught:
                Agent(name="coder", system_prompt="Answer.", provider=provider, model_name=model, api_keys=api_keys, fallback=fallback)
            message = assert_no_key_text(self, caught.exception, *api_keys)
            for fact in (index, str(len(entry)), "deepseek", "kimi", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"):
                self.assertIn(fact, message)
        with patch.dict(os.environ, {}, clear=True):
            agent = Agent(name="coder", system_prompt="Answer.", provider="deepseek", model_name="deepseek-chat", api_keys=[K_UNPROVEN], fallback=["kimi/kimi-k2.7-code"])
        self.assertEqual(key_view(agent.runner_config.api_keys)[0], {"deepseek": K_UNPROVEN})

    def test_an_agent_without_a_primary_binds_proven_keys_and_refuses_an_unproven_one(self) -> None:
        # EC-48: with no provider and no model, an unproven key has no configured provider (M-6), and INV-24 does not apply.
        with patch.dict(os.environ, {}, clear=True):
            agent = BaseAgent(name="custom", system_prompt="Answer.", api_keys=[K_XAI, VIDBYTE_KEY])
            self.assertEqual(agent.runner_config.api_keys.key_for("xai"), K_XAI)
            self.assertEqual(agent.runner_config.api_keys.vidbyte_api_key, VIDBYTE_KEY)
            with self.assertRaises(ConfigurationError) as caught:
                BaseAgent(name="custom", system_prompt="Answer.", api_keys=[K_UNPROVEN])
        message = assert_no_key_text(self, caught.exception, K_UNPROVEN)
        self.assertIn("api_keys[0]", message)

    def test_an_aggregate_needs_every_spec_built_models_key_unless_its_list_holds_none(self) -> None:
        # AC-37, INV-24, D-27, EC-33, EC-57: proposers and the aggregator are all primaries; a prebuilt aggregator adds none.
        from vidbyte import AggregateAgent

        proposers = [("openai", "gpt-5.5"), ("deepseek", "deepseek-chat")]
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError) as caught:
                AggregateAgent(name="panel", system_prompt="Answer.", proposers=proposers, aggregator=("anthropic", "claude-sonnet-5"), api_keys=[K_ANTHROPIC])
            message = assert_no_key_text(self, caught.exception, K_ANTHROPIC)
            self.assertIn("openai", message)
            self.assertIn("anthropic", message)
            self.assertEqual(caught.exception.details.get("provider"), "openai")

            # Review R-3: with no aggregator given, the default one is the agent's own provider and model, so it is a primary too.
            with self.assertRaises(ConfigurationError) as default_caught:
                AggregateAgent(name="panel", system_prompt="Answer.", proposers=[("openai", "gpt-5.5")], provider="anthropic", model_name="claude-sonnet-5", api_keys=[K_OPENAI])
            assert_no_key_text(self, default_caught.exception, K_OPENAI)
            self.assertEqual(default_caught.exception.details.get("provider"), "anthropic")

            judge = Agent(name="judge", system_prompt="Judge.", provider="anthropic", model_name="claude-sonnet-5")
            prebuilt = AggregateAgent(name="panel", system_prompt="Answer.", proposers=proposers, aggregator=judge, api_keys=[K_OPENAI, K_UNPROVEN])
        record = prebuilt.runner_config.api_keys
        self.assertEqual(key_view(record)[0], {"openai": K_OPENAI, "deepseek": K_UNPROVEN})
        self.assertEqual(key_view(record)[2], ("openai", "deepseek"))
        for _, child in prebuilt._engine._proposers:
            own = str(getattr(child.runner_config.provider, "value", child.runner_config.provider))
            self.assertEqual(child.runner_config.api_keys.key_for(own), {"openai": K_OPENAI, "deepseek": K_UNPROVEN}[own])

    def test_an_aggregate_with_no_provider_keys_sends_every_child_call_vidbyte_paid(self) -> None:
        # AC-37 (second case), EC-33: an empty list skips INV-24, and in AUTO every proposer and the aggregator go Vidbyte-paid.
        from vidbyte import AggregateAgent

        router = ProviderRouter({ModelProvider.OPENAI: responses_done("proposal"), ModelProvider.DEEPSEEK: chat_done("proposal"), ModelProvider.ANTHROPIC: anthropic_done("final")})
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=router):
            agent = AggregateAgent(name="panel", system_prompt="Answer.", proposers=[("openai", "gpt-5.5"), ("deepseek", "deepseek-chat")], aggregator=("anthropic", "claude-sonnet-5"), api_keys=[])
            agent.run("Which is larger, 2 or 3?")
        self.assertEqual({request["json_body"]["provider"] for request in router.requests}, {"openai", "deepseek", "anthropic"})
        for request in router.requests:
            self.assertEqual(request["url"], GATEWAY_URL)
            self.assertIsNone(provider_key_header(request))


class AgentChildrenTests(unittest.TestCase):
    """Every agent-built child carries the root's ProviderKeys and mode (AC-18, AC-34, INV-15, EC-47)."""

    def _deepseek_parent(self, mode: Any) -> BaseAgent:
        # The AC-18 parent: K_u (unproven) binds to deepseek, K_o (sk-proj-) to openai.
        return Agent(name="parent", system_prompt="Work.", provider="deepseek", model_name="deepseek-chat", fallback=["openai/gpt-5.5"], api_keys=[K_UNPROVEN, K_OPENAI], vidbyte_api_key=VIDBYTE_KEY, model_mode=mode)

    def test_forks_handoff_and_continual_trace_agents_carry_the_parents_record_and_direct_mode(self) -> None:
        # AC-18, INV-15, D-13: a child never re-matches the list; the openai fork's call carries only K_o.
        from vidbyte import EngineeringHandoff, HandoffAgent
        from vidbyte.lib.config import TextModelMode
        from vidbyte.trace.continual import ActionTrace, ContinualTraceAgent

        with patch.dict(os.environ, {}, clear=True):
            parent = self._deepseek_parent(TextModelMode.DIRECT)
            record = parent.runner_config.api_keys
            self.assertEqual(key_view(record)[0], {"deepseek": K_UNPROVEN, "openai": K_OPENAI})
            fork = parent.fork(AgentForkSettings(provider="openai", model_name="gpt-5.5"))
            children = {
                "fork": fork,
                "handoff": HandoffAgent.from_source_agent(parent, EngineeringHandoff()),
                "continual-trace": ContinualTraceAgent.from_source_agent(parent, ActionTrace),
            }
        for name, child in children.items():
            with self.subTest(child=name):
                self.assertEqual(child.runner_config.api_keys, record)
                self.assertIs(child.runner_config.model_mode, TextModelMode.DIRECT)

        router = ProviderRouter({ModelProvider.OPENAI: responses_done("forked")})
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=router):
            self.assertEqual(fork.run("Say hi.").content, "forked")
        [sent] = router.requests
        self.assertTrue(sent["url"].startswith("https://api.openai.com/"))
        self.assertEqual(header(sent, "authorization"), f"Bearer {K_OPENAI}")
        for secret in (K_UNPROVEN, VIDBYTE_KEY):
            self.assertNotIn(secret, flat(sent))

    def test_a_jev_agent_its_clone_and_its_brief_writer_carry_the_settings_record_and_mode(self) -> None:
        # AC-18 (Jev), EC-34, D-27: JevAgentSettings is the root; a writer without its own list carries the main record.
        from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRuntimeSettings
        from vidbyte.agents.jev.compute.clone import JevCloneAgent
        from vidbyte.agents.jev.settings import JevRunBriefSettings
        from vidbyte.lib.config import DecisionModelConfig, TextModelMode
        from vidbyte.lib.enums import DecisionModelMode

        with patch.dict(os.environ, {}, clear=True):
            settings = JevAgentSettings(name="researcher", system_prompt="Research.", provider="deepseek", model_name="deepseek-chat", api_keys=[K_UNPROVEN, K_OPENAI], vidbyte_api_key=VIDBYTE_KEY, model_mode=TextModelMode.DIRECT)
            runtime = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=JevComputeSettings(brief=JevRunBriefSettings(every_iterations=3)))
            agent = JevAgent(settings, runtime)
            clone = JevCloneAgent(settings, 1)
            assert agent.compute is not None
            writer = agent.compute.keeper.writer
            own_brief = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=JevComputeSettings(brief=JevRunBriefSettings(provider="anthropic", model_name="claude-haiku-4-5-20251001", api_keys=[K_ANTHROPIC])))
            own_writer_agent = JevAgent(settings, own_brief)
            assert own_writer_agent.compute is not None
            own_writer = own_writer_agent.compute.keeper.writer
        self.assertEqual(key_view(settings.api_keys)[0], {"deepseek": K_UNPROVEN, "openai": K_OPENAI})
        for name, child in (("agent", agent), ("clone", clone), ("writer", writer)):
            with self.subTest(child=name):
                self.assertEqual(child.runner_config.api_keys, settings.api_keys)
                self.assertIs(child.runner_config.model_mode, TextModelMode.DIRECT)
        # A writer with its own list is its own root: it matches K_a against its own provider and keeps the main Vidbyte key.
        self.assertEqual(key_view(own_writer.runner_config.api_keys)[0], {"anthropic": K_ANTHROPIC})
        self.assertEqual(own_writer.runner_config.api_keys.vidbyte_api_key, VIDBYTE_KEY)
        self.assertIs(own_writer.runner_config.model_mode, TextModelMode.DIRECT)

    def test_an_aggregates_children_carry_its_record_and_each_direct_call_carries_its_own_key(self) -> None:
        # AC-18 (aggregate), INV-3, D-27: the aggregate's own record, its proposers' and its aggregator's are one record.
        from vidbyte import AggregateAgent
        from vidbyte.lib.config import TextModelMode

        router = ProviderRouter({ModelProvider.OPENAI: responses_done("proposal"), ModelProvider.DEEPSEEK: chat_done("final")})
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=router):
            agent = AggregateAgent(name="panel", system_prompt="Answer.", proposers=[("deepseek", "deepseek-chat"), ("openai", "gpt-5.5")], aggregator=("deepseek", "deepseek-chat"), api_keys=[K_UNPROVEN, K_OPENAI], vidbyte_api_key=VIDBYTE_KEY, model_mode=TextModelMode.DIRECT)
            record = agent.runner_config.api_keys
            children = [child for _, child in agent._engine._proposers] + [agent._engine._aggregator]
            agent.run("Which is larger, 2 or 3?")
        self.assertEqual(key_view(record)[0], {"deepseek": K_UNPROVEN, "openai": K_OPENAI})
        for child in children:
            self.assertEqual(child.runner_config.api_keys, record)
            self.assertIs(child.runner_config.model_mode, TextModelMode.DIRECT)
        self.assertTrue(router.for_provider(ModelProvider.OPENAI))
        self.assertTrue(router.for_provider(ModelProvider.DEEPSEEK))
        for provider, own, other in ((ModelProvider.OPENAI, K_OPENAI, K_UNPROVEN), (ModelProvider.DEEPSEEK, K_UNPROVEN, K_OPENAI)):
            for request in router.for_provider(provider):
                self.assertNotEqual(request["url"], GATEWAY_URL)
                self.assertEqual(header(request, "authorization"), f"Bearer {own}")
                self.assertNotIn(other, flat(request))
                self.assertNotIn(VIDBYTE_KEY, flat(request))

    def test_a_fork_to_a_provider_without_a_key_goes_vidbyte_paid_and_never_receives_the_unproven_key(self) -> None:
        # AC-34, EC-47, INV-15: the fork is a child, so it never raises INV-24, and K_u stays bound to deepseek.
        from vidbyte.agents.fork import AgentForker
        from vidbyte.lib.config import TextModelMode

        gateway = ScriptedGateway(chat_done("Kimi says hi"))
        with patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            parent = self._deepseek_parent(TextModelMode.AUTO)
            fork = AgentForker.fork(parent, AgentForkSettings(provider="kimi", model_name="kimi-k2.7-code"))
            reply = fork.run("Say hi.")
        self.assertEqual(reply.content, "Kimi says hi")
        self.assertEqual(fork.runner_config.api_keys, parent.runner_config.api_keys)
        [sent] = gateway.requests
        self.assertEqual((sent["url"], sent["json_body"]["provider"]), (GATEWAY_URL, "kimi"))
        self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
        self.assertIsNone(provider_key_header(sent))
        self.assertNotIn(K_UNPROVEN, flat(sent))
        self.assertNotIn(K_OPENAI, flat(sent))


class NonTextModelKeyTests(unittest.TestCase):
    """Image, video, audio and embedding configs keep api_key and get their provider's matched key (AC-23, D-12, INV-19)."""

    def test_image_and_audio_runners_get_their_providers_matched_key_or_none(self) -> None:
        # AC-23, EC-41: ProviderKeys.key_for(provider) goes to the non-text config; with no matched key the variable resolves as today.
        from vidbyte.lib.agents.modality_detector import ModalityDetector

        with patch.dict(os.environ, {"OPENAI_API_KEY": K_OPENAI}, clear=True):
            image_agent = Agent(name="artist", system_prompt="Draw.", provider="openai", model_name="gpt-image-1", api_keys=[K_OPENAI])
            image_runner, image_type = image_agent._runner_for_model()
            audio_agent = Agent(name="voice", system_prompt="Speak.", provider="elevenlabs", model_name="eleven_multilingual_v2", api_keys=[K_UNPROVEN])
            audio_runner, audio_type = audio_agent._runner_for_model()
            keyless_runner, _ = Agent(name="artist", system_prompt="Draw.", provider="openai", model_name="gpt-image-1")._runner_for_model()
            factory_runner = ModalityDetector.create_runner("image", provider="openai", model="gpt-image-1", api_keys=[K_OPENAI])
        self.assertEqual((image_type, audio_type), ("image", "audio"))
        self.assertEqual(image_runner._config.api_key, K_OPENAI)
        self.assertEqual(audio_runner._config.api_key, K_UNPROVEN)
        self.assertIsNone(keyless_runner._config.api_key)
        self.assertEqual(factory_runner._config.api_key, K_OPENAI)

    def test_a_non_text_runner_takes_its_own_providers_key_when_another_providers_key_comes_first(self) -> None:
        # AC-23, INV-3, NFR-10 (review R-5): with single-key lists, "first key" and key_for(provider) look the same; here the xAI key comes first.
        from vidbyte.lib.agents.modality_detector import ModalityDetector

        with patch.dict(os.environ, {}, clear=True):
            image_runner, image_type = Agent(name="artist", system_prompt="Draw.", provider="openai", model_name="gpt-image-1", api_keys=[K_XAI, K_OPENAI])._runner_for_model()
            factory_runner = ModalityDetector.create_runner("image", provider="openai", model="gpt-image-1", api_keys=[K_XAI, K_OPENAI])
        self.assertEqual(image_type, "image")
        self.assertEqual(image_runner._config.api_key, K_OPENAI)
        self.assertEqual(factory_runner._config.api_key, K_OPENAI)


if __name__ == "__main__":
    unittest.main()
