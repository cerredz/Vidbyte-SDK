from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.agents.contracts import MinToolCalls, MinToolCallsById
from vidbyte.agents.fallback import AgentFallback
from vidbyte.agents.settings import AgentFallbackSettings
from vidbyte.config import YamlLoader
from vidbyte.lib.dataclasses.agents import AgentMetadata, AgentRunnerConfig, FallbackModel
from vidbyte.lib.dataclasses.config import AgentSettings, ToolDefinition
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry

BASE = {"name": "researcher", "system_prompt": "You are a helpful research agent."}


class FallbackEnabledValidationTests(unittest.TestCase):
    def test_rejects_truthy_and_falsey_non_boolean_enabled_values(self) -> None:
        for value in ("false", "true", 0, 1, None):
            with self.subTest(value=value), self.assertRaisesRegex(ConfigurationError, "enabled"):
                AgentFallbackSettings(models=["gpt-5.4-mini"], enabled=value)

    def test_accepts_boolean_enabled_values(self) -> None:
        self.assertFalse(AgentFallbackSettings(models=["gpt-5.4-mini"], enabled=False).enabled)
        self.assertTrue(AgentFallbackSettings(models=["gpt-5.4-mini"], enabled=True).enabled)



class FallbackApiKeyInheritanceTests(unittest.TestCase):
    PRIMARY = FallbackModel(provider="openai", model="gpt-x", api_key="sk-openai", temperature=0.3)

    def resolve(self, *entries: str | FallbackModel, primary: FallbackModel | None = None) -> tuple[FallbackModel, ...]:
        # Resolves the declared entries against the primary and drops the primary itself from the result.
        return AgentFallbackSettings(models=entries).resolved_models(primary=primary or self.PRIMARY)[1:]

    def test_same_provider_entries_inherit_the_agent_key(self) -> None:
        bare, prefixed = self.resolve("gpt-y", "openai/gpt-y")
        self.assertEqual((bare.provider, bare.api_key), ("openai", "sk-openai"))
        self.assertEqual((prefixed.provider, prefixed.api_key), ("openai", "sk-openai"))

    def test_other_provider_prefix_does_not_receive_the_agent_key(self) -> None:
        (entry,) = self.resolve("anthropic/claude-z")
        self.assertEqual((entry.provider, entry.model, entry.api_key, entry.temperature), ("anthropic", "claude-z", None, 0.3))

    def test_enum_or_cased_primary_provider_still_counts_as_same_provider(self) -> None:
        for provider in (ModelProvider.OPENAI, "OpenAI"):
            with self.subTest(provider=provider):
                primary = FallbackModel(provider=provider, model="gpt-x", api_key="sk-openai")
                same, other = self.resolve("openai/gpt-y", "gemini/gemini-z", primary=primary)
                self.assertEqual(same.api_key, "sk-openai")
                self.assertIsNone(other.api_key)

    def test_enum_provider_is_stored_and_labelled_as_its_string_value(self) -> None:
        # A typed ModelProvider entry must not leak 'ModelProvider.ANTHROPIC' into identity() and run metadata.
        entry = FallbackModel(provider=ModelProvider.ANTHROPIC, model="m")
        self.assertEqual((type(entry.provider), entry.provider, entry.identity()), (str, "anthropic", "anthropic/m"))

    def test_explicit_fallback_model_keeps_its_own_key(self) -> None:
        explicit = FallbackModel(provider="anthropic", model="claude-z", api_key="sk-ant")
        self.assertEqual(self.resolve(explicit), (explicit,))

    def test_openrouter_auto_keeps_its_full_id(self) -> None:
        auto, slug = self.resolve("openrouter/auto", "openrouter/anthropic/claude-sonnet-5")
        self.assertEqual((auto.provider, auto.model), ("openrouter", "openrouter/auto"))
        self.assertEqual((slug.provider, slug.model), ("openrouter", "anthropic/claude-sonnet-5"))


class FallbackRunnerTimeoutTests(unittest.TestCase):
    def test_fallback_runner_inherits_the_agent_timeout(self) -> None:
        # A backup model must get the agent's per-request timeout, not the 60-second library default.
        config = AgentRunnerConfig(provider="deepseek", model_name="deepseek-v4-pro", api_key="k", timeout_seconds=300.0)
        backup = FallbackModel(provider="anthropic", model="claude-sonnet-4-6", api_key="sk-ant")
        chain = AgentFallback.from_spec([backup], runner_config=config, agent_name="researcher")
        self.assertEqual(chain.build_runner(1)._config.timeout_seconds, 300.0)


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

    def test_accepts_an_openrouter_vendor_slug_but_not_a_cross_provider_bare_name(self) -> None:
        settings = build(provider="openrouter", model_name="anthropic/claude-sonnet-5")
        self.assertEqual((settings.provider, settings.model_name), ("openrouter", "anthropic/claude-sonnet-5"))
        self.assertEqual(build(provider="openrouter", model_name="openrouter/auto").model_name, "openrouter/auto")
        with self.assertRaises(ConfigurationError):
            build(provider="openrouter", model_name="meta-llama/llama-4-maverick")
        with self.assertRaises(ConfigurationError) as ctx:
            build(provider="deepseek", model_name="anthropic/claude-sonnet-5")
        self.assertIn("registered under provider 'anthropic'", str(ctx.exception))

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

    def test_builds_the_output_contract_a_document_names_by_type(self) -> None:
        settings = build(loop={"output_contracts": [{"type": "MinToolCalls", "minimum": 1}, {"type": "MinToolCallsById", "tool_name": "search", "minimum": 2}]})

        first, second = settings.loop.output_contracts
        self.assertIsInstance(first, MinToolCalls)
        self.assertEqual(first.minimum, 1)
        self.assertIsInstance(second, MinToolCallsById)
        self.assertEqual((second.tool_name, second.minimum), ("search", 2))

    def test_rejects_an_output_contract_without_a_concrete_type(self) -> None:
        for entry in ({"minimum": 1}, {"type": "OutputContract", "minimum": 1}, {"type": "SchemaConformance"}, {"type": "Nope"}):
            with self.subTest(entry=entry), self.assertRaises(ConfigurationError) as ctx:
                build(loop={"output_contracts": [entry]})

            self.assertEqual(ctx.exception.details["field"], "agent.loop.output_contracts[0].type")
            self.assertIn("MinToolCalls", str(ctx.exception))


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

    def test_rejects_camelcase_and_hyphenated_credential_keys_loaded_from_yaml(self) -> None:
        # @intent yaml-secret-guard-normalizes-key-spelling
        rejected = ("apiKey", "accessToken", "x-api-key", "clientSecret", "cookie", "bearer", "passwd", "aws_credentials")
        with tempfile.TemporaryDirectory() as folder:
            for key in rejected:
                path = self._write_agent(Path(folder), key)
                with self.subTest(key=key), self.assertRaises(ConfigurationError) as ctx:
                    YamlLoader().load_agent(path)
                self.assertIn("must not contain YAML-held secrets", str(ctx.exception))
                self.assertEqual(ctx.exception.details["field"], f"agent.metadata.{key}")

    def test_keeps_ordinary_keys_that_resemble_credentials_loadable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for key in ("author", "max_tokens", "tokenizer"):
                with self.subTest(key=key):
                    settings = YamlLoader().load_agent(self._write_agent(Path(folder), key))
                    self.assertEqual(settings.metadata, {key: "value123"})

    def _write_agent(self, folder: Path, key: str) -> Path:
        # Writes a minimal agent document whose metadata holds one key under test.
        path = folder / "agent.yaml"
        path.write_text(
            f"type: base\nname: researcher\nsystem_prompt: You research.\nprovider: deepseek\nmodel_name: deepseek-chat\nmetadata:\n  {key}: value123\n",
            encoding="utf-8",
        )
        return path

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

    def test_loads_credential_like_field_names_from_a_yaml_output_schema(self) -> None:
        # @intent output-schema-field-names-are-not-secrets
        with tempfile.TemporaryDirectory() as folder:
            for name in ("token", "auth", "refresh_token", "password_policy"):
                with self.subTest(name=name):
                    path = self._write_agent(Path(folder), f"output_schema:\n  type: object\n  properties:\n    {name}:\n      type: string\n  required: [{name}]\n")
                    settings = YamlLoader().load_agent(path)
                    self.assertEqual(settings.output_schema["properties"], {name: {"type": "string"}})

    def test_still_rejects_interpolation_inside_a_yaml_output_schema(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = self._write_agent(Path(folder), "output_schema:\n  type: object\n  properties:\n    token:\n      type: string\n      default: ${API_TOKEN}\n")
            with self.assertRaises(ConfigurationError) as ctx:
                YamlLoader().load_agent(path)

        self.assertIn("environment interpolation", str(ctx.exception))

    def test_still_rejects_credential_keys_in_yaml_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = self._write_agent(Path(folder), "metadata:\n  apiKey: value123\n")
            with self.assertRaises(ConfigurationError) as ctx:
                YamlLoader().load_agent(path)

        self.assertIn("must not contain YAML-held secrets", str(ctx.exception))
        self.assertEqual(ctx.exception.details["field"], "agent.metadata.apiKey")

    def _write_agent(self, folder: Path, extra: str) -> Path:
        # Writes a minimal agent document followed by the YAML block under test.
        path = folder / "agent.yaml"
        path.write_text(f"type: base\nname: tokenizer\nsystem_prompt: Analyze.\nprovider: deepseek\nmodel_name: deepseek-chat\n{extra}", encoding="utf-8")
        return path


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
        self.assertEqual(kwargs["agent_loop_settings"].max_iterations, 4)
        self.assertIsNone(kwargs["max_tool_rounds"])

    def test_builds_an_agent_from_a_document_with_max_tool_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.yaml"
            path.write_text("type: base\nname: support\nsystem_prompt: Help.\nprovider: deepseek\nmodel_name: deepseek-v4-flash\nmax_tool_rounds: 3\n", encoding="utf-8")
            loader = YamlLoader()
            settings = loader.load_agent(path)
            first, second = loader.build_agent(settings), loader.build_agent(settings)

        for agent in (first, second):
            self.assertEqual(agent.agent_loop_settings.max_iterations, 3)
            self.assertEqual(agent.max_tool_rounds, 3)

    def test_rejects_max_tool_rounds_that_conflicts_with_the_loop(self) -> None:
        self.assertEqual(build(max_tool_rounds=5, loop={"max_iterations": 5}).loop.max_iterations, 5)
        with self.assertRaises(ConfigurationError) as ctx:
            build(max_tool_rounds=5, loop={"max_iterations": 7})

        self.assertEqual(ctx.exception.details["field"], "agent.max_tool_rounds")

    def test_max_tool_rounds_rejects_a_floor_it_makes_unreachable(self) -> None:
        # @intent yaml-max-tool-rounds-validates-floors
        floor = [{"type": "MinIterations", "minimum": 5}]
        with self.assertRaises(ConfigurationError) as nested:
            build(loop={"max_iterations": 3, "output_contracts": floor})
        with self.assertRaises(ConfigurationError) as top_level:
            build(max_tool_rounds=3, loop={"output_contracts": floor})

        self.assertEqual(nested.exception.details["field"], "agent.loop")
        self.assertEqual(top_level.exception.details["field"], "agent.max_tool_rounds")
        self.assertIn("MinIterations(minimum=5) conflicts with AgentLoopSettings.max_iterations=3", str(top_level.exception))
        reachable = build(max_tool_rounds=2, loop={"output_contracts": [{"type": "MinToolCalls", "minimum": 1}], "tool_settings": {"max_calls": 2}})
        self.assertEqual(reachable.loop.max_iterations, 2)
        self.assertEqual(build(max_tool_rounds=5, loop={"output_contracts": floor}).loop.max_iterations, 5)

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

    def test_inline_prompts_ending_in_a_filename_stay_inline_text(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            documents = {
                "sentence.yaml": ("name: writer\nsystem_prompt: You are a writer. Save your notes to notes.md\n", "You are a writer. Save your notes to notes.md"),
                "block.yaml": ("name: writer\nsystem_prompt: |\n  You are a writer.\n  Always attach summary.txt\n", "You are a writer.\nAlways attach summary.txt"),
            }
            for name, (text, expected) in documents.items():
                (root / name).write_text(text, encoding="utf-8")

                self.assertEqual(YamlLoader().load_agent(root / name).system_prompt, expected)

    def test_unreadable_prompt_file_raises_configuration_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "agent.yaml").write_text("name: researcher\nsystem_prompt: ./missing.md\n", encoding="utf-8")

            with self.assertRaises(ConfigurationError) as ctx:
                YamlLoader().load_agent(root / "agent.yaml")

            self.assertIsInstance(ctx.exception.__cause__, OSError)
            self.assertEqual(ctx.exception.details["field"], "agent.system_prompt")


class ExpectedStructureTests(unittest.TestCase):
    def test_documents_every_allowed_field(self) -> None:
        structure = AgentSettings.expected_structure()

        self.assertEqual(set(structure), set(AgentSettings._ALLOWED_FIELDS))

    def test_documents_the_nested_definition_shape(self) -> None:
        self.assertEqual(ToolDefinition.expected_structure(), {"ref": "<tool-reference>", "options": {}})


if __name__ == "__main__":
    unittest.main()
