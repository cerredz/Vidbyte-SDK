from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.config import YamlLoader
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.config import AgentSettings, ToolDefinition
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry

BASE = {"name": "researcher", "system_prompt": "You are a helpful research agent."}


def build(**overrides: object) -> AgentSettings:
    # Builds one agent settings object from the minimal valid document plus the overrides under test.
    return AgentSettings.from_mapping({**BASE, **overrides})


class AgentNameValidationTests(unittest.TestCase):
    def test_accepts_a_tool_safe_name(self) -> None:
        self.assertEqual(build(name="research-agent_2").name, "research-agent_2")

    def test_rejects_a_name_over_the_character_ceiling(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(name="x" * 65)

        self.assertIn("64 characters or fewer", str(ctx.exception))
        self.assertEqual(ctx.exception.details["field"], "agent.name")

    def test_rejects_a_name_a_provider_would_refuse_as_a_tool_name(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(name="my agent!")

        self.assertIn("exposed as a tool", str(ctx.exception))


class SystemPromptValidationTests(unittest.TestCase):
    def test_rejects_a_prompt_over_the_character_ceiling(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(system_prompt="x" * 100_001)

        self.assertIn("context windows", str(ctx.exception))

    def test_rejects_control_characters_and_names_their_offset(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(system_prompt="hi\x00there")

        self.assertIn("U+0000", str(ctx.exception))
        self.assertEqual(ctx.exception.details["offset"], 2)

    def test_allows_ordinary_whitespace(self) -> None:
        self.assertIn("\n", build(system_prompt="line one\nline two\tend").system_prompt)


class ProviderModelValidationTests(unittest.TestCase):
    def test_normalizes_provider_case(self) -> None:
        self.assertEqual(build(provider="Anthropic").provider, "anthropic")

    def test_accepts_every_text_provider_default_model(self) -> None:
        # Audio-only providers are excluded: their defaults are correctly refused by the modality rule.
        for provider, model in ProviderModelRegistry.DEFAULT_PROVIDER_MODELS.items():
            if provider.value in {"elevenlabs", "playai"}:
                continue
            with self.subTest(provider=provider.value):
                self.assertEqual(build(provider=provider.value, model_name=model).model_name, model)

    def test_refuses_a_text_to_speech_provider_default_for_an_agent(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(provider="elevenlabs", model_name="eleven_multilingual_v2")

        self.assertEqual(ctx.exception.details["modality"], "audio")

    def test_rejects_an_uncatalogued_model(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(model_name="banana-9000")

        self.assertIn("no registered runner", str(ctx.exception))

    def test_rejects_a_model_belonging_to_another_provider(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(provider="anthropic", model_name="gpt-5.6-sol")

        self.assertIn("registered under provider 'openai'", str(ctx.exception))

    def test_rejects_a_non_text_model_for_a_conversational_agent(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(provider="openai", model_name="dall-e-3")

        self.assertIn("cannot drive a conversational agent", str(ctx.exception))
        self.assertEqual(ctx.exception.details["modality"], "image")

    def test_rejects_a_model_name_over_the_character_ceiling(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(model_name="x" * 129)


class TemperatureValidationTests(unittest.TestCase):
    def test_accepts_the_sdk_window(self) -> None:
        self.assertEqual(build(provider="openai", temperature=1.5).temperature, 1.5)

    def test_rejects_a_negative_temperature(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(temperature=-1)

        self.assertIn("between 0.0 and 2.0", str(ctx.exception))

    def test_rejects_a_temperature_above_the_sdk_window(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(temperature=5)

    def test_rejects_a_non_finite_temperature_reachable_from_yaml(self) -> None:
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ConfigurationError) as ctx:
                build(temperature=value)

            self.assertIn("finite number", str(ctx.exception))

    def test_applies_the_narrower_provider_ceiling(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(provider="anthropic", temperature=1.5)

        self.assertIn("'anthropic'", str(ctx.exception))
        self.assertEqual(ctx.exception.details["maximum"], 1.0)

    def test_rejects_a_boolean_temperature(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(temperature=True)


class MaxToolRoundsValidationTests(unittest.TestCase):
    def test_accepts_a_positive_integer(self) -> None:
        self.assertEqual(build(max_tool_rounds=8).max_tool_rounds, 8)

    def test_rejects_a_negative_value(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(max_tool_rounds=-3)

        self.assertIn("greater than zero", str(ctx.exception))

    def test_rejects_zero(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(max_tool_rounds=0)

    def test_rejects_a_boolean(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(max_tool_rounds=True)

        self.assertIn("must be an integer", str(ctx.exception))


class AlgorithmValidationTests(unittest.TestCase):
    def test_rejects_a_blank_placeholder(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(algorithm="")

    def test_rejects_an_unregistered_preset(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(algorithm="not-a-preset")

        self.assertIn("registered context-window preset", str(ctx.exception))


class LoopValidationTests(unittest.TestCase):
    def test_names_the_supported_keys_on_a_typo(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(loop={"max_iteration": 5})

        self.assertIn("unsupported field(s): max_iteration", str(ctx.exception))

    def test_builds_tool_settings_from_a_document_mapping(self) -> None:
        settings = build(loop={"tool_settings": {"max_calls": 5}})

        self.assertEqual(settings.loop.tool_settings.max_calls, 5)

    def test_builds_a_tool_error_policy_from_a_document_mapping(self) -> None:
        settings = build(loop={"tool_error_policy": {"max_retries_per_tool_call": 2}})

        self.assertEqual(settings.loop.tool_error_policy.max_retries_per_tool_call, 2)

    def test_reports_an_invalid_nested_loop_member_by_field(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(loop={"tool_settings": {"max_calls": -1}})

        self.assertEqual(ctx.exception.details["field"], "agent.loop.tool_settings")


class DefinitionValidationTests(unittest.TestCase):
    def test_reports_a_nested_error_at_its_document_position(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(tools=["ok_tool", {"ref": ""}])

        self.assertEqual(ctx.exception.details["field"], "agent.tools[1].ref")

    def test_rejects_a_reference_that_cannot_resolve(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(tools=[{"ref": "has space"}])

        self.assertIn("valid reference name", str(ctx.exception))

    def test_rejects_more_entries_than_the_ceiling(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(tools=[{"ref": f"tool_{index}"} for index in range(129)])

    def test_accepts_context_items_as_ref_options_entries(self) -> None:
        settings = build(context_items=[{"ref": "team_handbook", "options": {"pin": "v2"}}])

        self.assertEqual(settings.context_items[0].ref, "team_handbook")
        self.assertEqual(settings.context_items[0].options, {"pin": "v2"})


class SecretAndDepthValidationTests(unittest.TestCase):
    def test_rejects_a_credential_hidden_under_a_header_key(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(tools=[{"ref": "http", "options": {"headers": {"Authorization": "Bearer sk-x"}}}])

        self.assertIn("must not contain YAML-held secrets", str(ctx.exception))

    def test_rejects_an_acyclic_but_deeply_nested_document(self) -> None:
        deep: dict[str, object] = {"leaf": 1}
        for _ in range(60):
            deep = {"nested": deep}

        with self.assertRaises(ConfigurationError) as ctx:
            build(metadata=deep)

        self.assertIn("maximum nesting depth", str(ctx.exception))


class OutputSchemaValidationTests(unittest.TestCase):
    def test_accepts_a_json_schema_object(self) -> None:
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

        self.assertEqual(build(output_schema=schema).output_schema, schema)

    def test_rejects_a_mapping_that_is_not_a_schema(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(output_schema={"foo": 1})

        self.assertIn("JSON Schema object", str(ctx.exception))


class AgentMetadataValidationTests(unittest.TestCase):
    def test_builds_agent_metadata_from_a_document_mapping(self) -> None:
        settings = build(agent_metadata={"name": "researcher", "description": "Researches", "use_cases": "Deep dives"})

        self.assertIsInstance(settings.agent_metadata, AgentMetadata)
        self.assertEqual(settings.agent_metadata.description, "Researches")

    def test_rejects_a_tool_name_a_provider_would_refuse(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(agent_metadata={"name": "not a tool name"})

        self.assertIn("becomes the tool name", str(ctx.exception))

    def test_rejects_an_unsupported_key(self) -> None:
        with self.assertRaises(ConfigurationError):
            build(agent_metadata={"nmae": "typo"})


class TraceOptionValidationTests(unittest.TestCase):
    SCHEMA = {"name": "findings", "fields": {"summary": {"description": "What was found", "type": "string"}}}

    def test_builds_a_trace_option_from_a_document_mapping(self) -> None:
        settings = build(trace_option={"mode": "continual", "schema": self.SCHEMA})

        self.assertTrue(settings.trace_option.enabled)
        self.assertEqual(settings.trace_option.schema.name, "findings")

    def test_requires_a_schema(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(trace_option={"mode": "continual"})

        self.assertEqual(ctx.exception.details["field"], "agent.trace_option.schema")

    def test_requires_each_trace_field_to_describe_itself(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(trace_option={"mode": "continual", "schema": {"name": "f", "fields": {"x": {"type": "string"}}}})

        self.assertIn("non-blank 'description'", str(ctx.exception))


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_rejects_middleware_on_a_non_linear_runtime(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            build(runtime="mcts_search", middleware=[{"ref": "logger"}])

        self.assertEqual(ctx.exception.details["field"], "agent.middleware")
        self.assertEqual(ctx.exception.details["runtime"], "mcts_search")

    def test_rejects_continual_tracing_on_a_non_linear_runtime(self) -> None:
        schema = {"name": "findings", "fields": {"summary": {"description": "What was found"}}}

        with self.assertRaises(ConfigurationError) as ctx:
            build(runtime="actor_model", trace_option={"mode": "continual", "schema": schema})

        self.assertEqual(ctx.exception.details["field"], "agent.trace_option")

    def test_allows_the_same_document_on_the_linear_runtime(self) -> None:
        self.assertEqual(len(build(runtime="linear", middleware=[{"ref": "logger"}]).middleware), 1)


class AgentKwargsTests(unittest.TestCase):
    def test_carries_every_new_field_through_to_agent_kwargs(self) -> None:
        settings = build(max_tool_rounds=4, output_schema={"type": "object"}, agent_metadata={"name": "res"})
        kwargs = settings.to_agent_kwargs()

        for key in ("max_tool_rounds", "output_schema", "agent_metadata", "trace_option", "context_items"):
            self.assertIn(key, kwargs)
        self.assertEqual(kwargs["max_tool_rounds"], 4)

    def test_does_not_alias_the_caller_output_schema(self) -> None:
        schema = {"type": "object", "properties": {}}
        settings = build(output_schema=schema)
        settings.to_agent_kwargs()["output_schema"]["type"] = "mutated"

        self.assertEqual(settings.output_schema["type"], "object")


class SystemPromptFileContainmentTests(unittest.TestCase):
    def test_loads_a_prompt_from_a_neighbouring_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "prompt.md").write_text("You are a research agent.", encoding="utf-8")
            (root / "agent.yaml").write_text("name: researcher\nsystem_prompt: ./prompt.md\n", encoding="utf-8")

            settings = YamlLoader().load_agent(root / "agent.yaml")

            self.assertEqual(settings.system_prompt, "You are a research agent.")

    def test_rejects_a_reference_escaping_the_document_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "outside.md").write_text("escaped", encoding="utf-8")
            (root / "conf").mkdir()
            (root / "conf" / "agent.yaml").write_text("name: researcher\nsystem_prompt: ../outside.md\n", encoding="utf-8")

            with self.assertRaises(ConfigurationError) as ctx:
                YamlLoader().load_agent(root / "conf" / "agent.yaml")

            self.assertIn("stay inside the configuration file's directory", str(ctx.exception))


class ExpectedStructureTests(unittest.TestCase):
    def test_documents_every_allowed_field(self) -> None:
        structure = AgentSettings.expected_structure()

        self.assertEqual(set(structure), set(AgentSettings._ALLOWED_FIELDS))

    def test_documents_the_nested_definition_shape(self) -> None:
        self.assertEqual(ToolDefinition.expected_structure(), {"ref": "<tool-reference>", "options": {}})


if __name__ == "__main__":
    unittest.main()
