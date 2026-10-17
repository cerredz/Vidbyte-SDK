"""FILE: tests/features/browser_agent/test_browser_agent_settings.py

PURPOSE: Pins the construction surface of BrowserAgent: BrowserServerSettings and BrowserAgentSettings refuse every invalid input the spec lists, name the field that is wrong, never read os.environ for a server key, never show a key in a repr or an error, and default every cap to its named constant.
ROLE IN CODEBASE: Settings layer of tests/features/browser_agent/ (spec AC-2, AC-3 settings half, AC-4, AC-21 settings half; INV-1, INV-2, INV-3, INV-4, INV-25; EC-1..EC-5, EC-20; FR-1..FR-3, FR-21; section 9.2 and 9.3). Exercises vidbyte/agents/browser/settings.py and BrowserAgent.__init__'s type check.
ARCHITECTURE NOTE: Every feature symbol is imported inside the test that needs it, so before the feature exists each test fails on its own ImportError and the rest of the pack still collects. Nothing here starts a server or makes a model call; a settings-level refusal must happen before either could.
FUNCTION INVENTORY: test_a_required_server_key_is_refused_unless_it_is_in_env_even_when_os_environ_has_it (AC-2, INV-2, EC-5); test_a_blank_required_key_is_refused_without_quoting_any_value (EC-4, INV-3); test_each_invalid_server_setting_is_refused_naming_its_field (EC-1, EC-2, EC-3, AC-4, section 9.2); test_each_invalid_agent_setting_is_refused_naming_its_field (AC-4, AC-21, INV-4, INV-25, EC-20, section 9.2); test_keys_never_appear_in_a_settings_repr_or_a_settings_error (AC-3, INV-3, T-1, T-3); test_a_non_settings_object_is_refused_naming_its_type (INV-1, FR-1); test_defaults_are_the_named_constants (section 9.3, field guide strict-config-dataclasses); test_a_preset_is_stored_as_its_registered_definition_and_env_is_read_only (D-5, section 8.5).
COMMON MODIFICATION PATTERNS: When the spec adds a bound, add one row to INVALID_AGENT_SETTINGS or INVALID_SERVER_SETTINGS with the field name and the bad value the error must name. Take bounds from vidbyte.lib.constants.browser, never from a literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see browser_agent_fixtures.py). 2. Do not pin a cap with a literal; compare to the BROWSER_* constant. 3. Do not put a real key in any row; FIRECRAWL_KEY and MODEL_KEY are fakes.
KNOWN EDGE CASES: A ConfigurationError may carry the field in `details` instead of the message, so error_text joins both. Which of the three role fields a cross-role duplicate is reported on is not fixed by the spec, so that row accepts any of them.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1, 6.2, 6.3, 9.2 and 9.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_settings.py -q
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from typing import Any

import pytest

from tests.features.browser_agent.browser_agent_fixtures import (
    FETCH_COMMAND,
    FIRECRAWL_KEY,
    MODEL_KEY,
    NAME,
    build_settings,
    error_text,
    fetch_server,
    int_token,
)
from vidbyte import tool
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.mcp import FirecrawlMCP, McpPresetDefinition, PlaywrightMCP


@tool(name="run_episode")
def shadow_run_episode(task: str) -> str:
    """A developer tool that takes a reserved name."""
    return task


@tool(name="patch_goal")
def shadow_patch_goal(text: str) -> str:
    """A developer tool that takes the other reserved name."""
    return text


async def async_sink(event: object) -> None:
    """An async sink, which the spec refuses because its coroutine would never be awaited."""


# ---------------------------------------------------------------- server keys (INV-2)


@pytest.mark.parametrize("preset", (pytest.param("definition", id="definition"), pytest.param("name", id="registered-name")))
def test_a_required_server_key_is_refused_unless_it_is_in_env_even_when_os_environ_has_it(monkeypatch: pytest.MonkeyPatch, preset: str) -> None:
    """AC-2, INV-2, EC-5: Firecrawl without FIRECRAWL_API_KEY in env is refused naming the variable, the preset, and BrowserServerSettings.env, whether or not os.environ holds the key."""
    from vidbyte.agents.browser import BrowserServerSettings

    given = FirecrawlMCP if preset == "definition" else "firecrawl"
    outcomes: list[str] = []
    for environ_value in ("fc-from-os-environ-0000", None):
        if environ_value is None:
            monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        else:
            monkeypatch.setenv("FIRECRAWL_API_KEY", environ_value)
        with pytest.raises(ConfigurationError) as refused:
            BrowserServerSettings(given)
        text = error_text(refused.value)
        for named in ("FIRECRAWL_API_KEY", "firecrawl", "BrowserServerSettings.env"):
            assert named in text, f"the refusal does not name {named!r}: {text}"
        assert "fc-from-os-environ-0000" not in text
        outcomes.append(type(refused.value).__name__)
    assert outcomes == ["ConfigurationError", "ConfigurationError"], "setting os.environ changed the outcome"
    # Positive control: the same preset with the key in env is accepted.
    accepted = BrowserServerSettings(given, env={"FIRECRAWL_API_KEY": FIRECRAWL_KEY})
    assert accepted.env["FIRECRAWL_API_KEY"] == FIRECRAWL_KEY


def test_a_blank_required_key_is_refused_without_quoting_any_value() -> None:
    """EC-4, INV-3: a present-but-blank key is refused naming the variable; a second, real key in the same env never appears in the message."""
    from vidbyte.agents.browser import BrowserServerSettings

    for blank in ("", "   "):
        with pytest.raises(ConfigurationError) as refused:
            BrowserServerSettings(FirecrawlMCP, env={"FIRECRAWL_API_KEY": blank, "FIRECRAWL_RETRY_TOKEN": FIRECRAWL_KEY})
        text = error_text(refused.value)
        assert "FIRECRAWL_API_KEY" in text, text
        assert FIRECRAWL_KEY not in text


# ---------------------------------------------------------------- server validation (section 9.2)


def _unregistered_definition() -> McpPresetDefinition:
    return McpPresetDefinition(name="vc-scout-browser", category="Search & Web Research", description="A browser nobody registered.", command=("vc-scout-browser",), required_env=())


def _tampered_playwright() -> McpPresetDefinition:
    return dataclasses.replace(PlaywrightMCP, command=("python", "-m", "some_other_server"))


INVALID_SERVER_SETTINGS = (
    pytest.param(lambda: {"preset": "not-a-preset"}, ("BrowserServerSettings.preset", "not-a-preset"), id="EC-1-unknown-preset-name"),
    pytest.param(lambda: {"preset": _unregistered_definition()}, ("McpPresetRegistry.register", "command"), id="EC-2-unregistered-definition"),
    pytest.param(lambda: {"preset": _tampered_playwright()}, ("McpPresetRegistry.register", "command"), id="EC-2-definition-differs-from-registered"),
    pytest.param(lambda: {"preset": PlaywrightMCP, "command": ("fake-browser",)}, ("preset", "command"), id="EC-3-both-preset-and-command"),
    pytest.param(lambda: {}, ("preset", "command"), id="EC-3-neither-preset-nor-command"),
    pytest.param(lambda: {"command": ()}, ("command",), id="empty-command"),
    pytest.param(lambda: {"preset": PlaywrightMCP, "timeout": "BROWSER_MAX_SERVER_TIMEOUT_SECONDS+1"}, ("timeout",), id="timeout-over-max"),
    pytest.param(lambda: {"command": FETCH_COMMAND, "env": {"FETCH_REGION": "   "}}, ("FETCH_REGION",), id="blank-env-value"),
)


@pytest.mark.parametrize(("fields", "named"), INVALID_SERVER_SETTINGS)
def test_each_invalid_server_setting_is_refused_naming_its_field(fields: Callable[[], dict[str, Any]], named: tuple[str, ...]) -> None:
    """EC-1, EC-2, EC-3, AC-4, section 9.2: each invalid BrowserServerSettings is refused with ConfigurationError naming the field."""
    from vidbyte.agents.browser import BrowserServerSettings
    from vidbyte.lib.constants.browser import BROWSER_MAX_SERVER_TIMEOUT_SECONDS

    values = fields()
    if values.get("timeout") == "BROWSER_MAX_SERVER_TIMEOUT_SECONDS+1":
        values["timeout"] = BROWSER_MAX_SERVER_TIMEOUT_SECONDS + 1
    with pytest.raises(ConfigurationError) as refused:
        BrowserServerSettings(**values)
    text = error_text(refused.value)
    for token in named:
        assert token in text, f"the refusal does not name {token!r}: {text}"


# ---------------------------------------------------------------- agent validation (section 9.2)


def _too_many_criteria() -> tuple[str, ...]:
    from vidbyte.lib.constants.browser import BROWSER_MAX_CRITERIA

    return tuple(f"Criterion number {chr(65 + index % 26)}{index}" for index in range(BROWSER_MAX_CRITERIA + 1))


def _overlong_criterion() -> tuple[str, ...]:
    from vidbyte.lib.constants.browser import BROWSER_ITEM_MAX_CHARS

    return ("x" * (BROWSER_ITEM_MAX_CHARS + 1),)


def _same_preset_in_two_roles() -> dict[str, Any]:
    from vidbyte.agents.browser import BrowserServerSettings

    return {"fetch_servers": (BrowserServerSettings(PlaywrightMCP),)}


def _same_command_twice() -> dict[str, Any]:
    from vidbyte.agents.browser import BrowserServerSettings

    return {"fetch_servers": (fetch_server(), BrowserServerSettings(command=FETCH_COMMAND))}


ROLE_FIELDS = r"action_servers|search_servers|fetch_servers"

INVALID_AGENT_SETTINGS = (
    pytest.param(lambda: {"action_servers": ()}, ("action_servers",), id="AC-4-no-action-server"),
    pytest.param(_same_preset_in_two_roles, (re.compile(ROLE_FIELDS), "playwright"), id="AC-4-same-preset-in-action-and-fetch"),
    pytest.param(_same_command_twice, (re.compile(ROLE_FIELDS), FETCH_COMMAND[0]), id="INV-4-same-command-twice"),
    pytest.param(lambda: {"action_servers": ("playwright",)}, ("action_servers",), id="role-item-not-server-settings"),
    pytest.param(lambda: {"name": "   "}, ("name",), id="blank-name"),
    pytest.param(lambda: {"system_prompt": ""}, ("system_prompt",), id="blank-system-prompt"),
    pytest.param(lambda: {"model_name": "not-a-real-model-7731"}, ("not-a-real-model-7731",), id="C012-unknown-model"),
    pytest.param(lambda: {"episode_model_name": "not-a-real-model-7732"}, ("not-a-real-model-7732",), id="C012-unknown-episode-model"),
    pytest.param(lambda: {"recheck_model_name": "not-a-real-model-7733"}, ("not-a-real-model-7733",), id="C012-unknown-recheck-model"),
    pytest.param(lambda: {"model_mode": "direct"}, ("model_mode", "direct"), id="model-mode-not-enum"),
    pytest.param(lambda: {"done_when": ("",)}, ("done_when",), id="blank-criterion"),
    pytest.param(lambda: {"done_when": ("Twenty programs are listed\nwith deadlines",)}, ("done_when",), id="multi-line-criterion"),
    pytest.param(lambda: {"done_when": _too_many_criteria()}, ("done_when",), id="too-many-criteria"),
    pytest.param(lambda: {"done_when": _overlong_criterion()}, ("done_when",), id="overlong-criterion"),
    pytest.param(lambda: {"tools": (shadow_run_episode,)}, ("tools", "run_episode"), id="AC-21-reserved-run-episode"),
    pytest.param(lambda: {"tools": (shadow_patch_goal,)}, ("tools", "patch_goal"), id="INV-25-reserved-patch-goal"),
    pytest.param(lambda: {"on_event": async_sink}, ("on_event",), id="EC-20-async-sink"),
    pytest.param(lambda: {"on_event": "print"}, ("on_event",), id="sink-not-callable"),
    pytest.param(lambda: {"max_actions": 0}, ("max_actions", 0), id="max-actions-0"),
    pytest.param(lambda: {"max_screenshots": 0}, ("max_screenshots", 0), id="max-screenshots-0"),
    pytest.param(lambda: {"keep_observations": 0}, ("keep_observations", 0), id="keep-observations-0"),
    pytest.param(lambda: {"recheck_every": 0}, ("recheck_every", 0), id="recheck-every-0"),
    pytest.param(lambda: {"max_stalls": 0}, ("max_stalls", 0), id="max-stalls-0"),
    pytest.param(lambda: {"permission_policy": "allow_all"}, ("permission_policy",), id="policy-not-a-policy"),
    pytest.param(lambda: {"loop": {"max_iterations": 3}}, ("loop",), id="loop-not-loop-settings"),
)


@pytest.mark.parametrize(("fields", "named"), INVALID_AGENT_SETTINGS)
def test_each_invalid_agent_setting_is_refused_naming_its_field(fields: Callable[[], dict[str, Any]], named: tuple[Any, ...]) -> None:
    """AC-4, AC-21, INV-4, INV-25, EC-20, section 9.2: each invalid BrowserAgentSettings is refused at construction with ConfigurationError naming the field and value."""
    with pytest.raises(ConfigurationError) as refused:
        build_settings(**fields())
    text = error_text(refused.value)
    for token in named:
        if isinstance(token, re.Pattern):
            pattern = token
        elif isinstance(token, int):
            pattern = int_token(token)
        else:
            pattern = re.compile(re.escape(str(token)))
        assert pattern.search(text), f"the refusal does not name {getattr(token, 'pattern', token)!r}: {text}"


# ---------------------------------------------------------------- key secrecy in settings (INV-3)


def test_keys_never_appear_in_a_settings_repr_or_a_settings_error() -> None:
    """AC-3, INV-3, T-1, T-3: with a server key in env and a model key in api_keys, neither appears in repr(settings), repr of a server, or the message of any invalid-settings error."""
    from vidbyte.agents.browser import BrowserServerSettings
    from vidbyte.lib.constants.browser import BROWSER_MAX_SERVER_TIMEOUT_SECONDS

    settings = build_settings(api_keys=[MODEL_KEY], vidbyte_api_key=None)
    for text in (repr(settings), str(settings), repr(settings.search_servers[0]), repr(settings.search_servers)):
        assert FIRECRAWL_KEY not in text and MODEL_KEY not in text, text
    # Positive control: the keys are held, so their absence above is not because they were dropped.
    assert settings.search_servers[0].env["FIRECRAWL_API_KEY"] == FIRECRAWL_KEY
    failing: list[Callable[[], object]] = [
        lambda: build_settings(api_keys=[MODEL_KEY], max_actions=0),
        lambda: build_settings(api_keys=[MODEL_KEY], done_when=("",)),
        lambda: BrowserServerSettings(FirecrawlMCP, env={"FIRECRAWL_API_KEY": FIRECRAWL_KEY}, timeout=BROWSER_MAX_SERVER_TIMEOUT_SECONDS + 1),
        lambda: BrowserServerSettings(FirecrawlMCP, command=("fake-browser",), env={"FIRECRAWL_API_KEY": FIRECRAWL_KEY}),
        lambda: BrowserServerSettings(FirecrawlMCP, env={"FIRECRAWL_API_KEY": FIRECRAWL_KEY, "FIRECRAWL_REGION": " "}),
    ]
    for build in failing:
        with pytest.raises(ConfigurationError) as refused:
            build()
        text = error_text(refused.value) + repr(refused.value)
        assert FIRECRAWL_KEY not in text and MODEL_KEY not in text, f"a settings error quoted a key: {text}"


# ---------------------------------------------------------------- the construction surface (INV-1)


def test_a_non_settings_object_is_refused_naming_its_type() -> None:
    """INV-1, FR-1: BrowserAgent accepts only BrowserAgentSettings; a dict is refused with ConfigurationError naming what it got."""
    from vidbyte.agents.browser import BrowserAgent

    for wrong in ({"name": NAME, "action_servers": ()}, "vc-scout"):
        with pytest.raises(ConfigurationError) as refused:
            BrowserAgent(wrong)  # type: ignore[arg-type]
        text = error_text(refused.value)
        assert type(wrong).__name__ in text, f"the refusal does not name the type it got: {text}"
        assert re.search("settings", text, re.IGNORECASE), text


def test_defaults_are_the_named_constants() -> None:
    """Section 9.3: every optional field defaults to its BROWSER_* constant (bounds come from constants, not literals)."""
    from vidbyte.agents.browser import BrowserServerSettings
    from vidbyte.lib.constants import browser as limits
    from vidbyte.lib.dataclasses.security import PermissionPolicy

    settings = build_settings(search_servers=(), fetch_servers=(), done_when=())
    assert (settings.search_servers, settings.fetch_servers, settings.done_when, settings.tools) == ((), (), (), ())
    assert settings.max_actions == limits.BROWSER_DEFAULT_MAX_ACTIONS
    assert settings.max_screenshots == limits.BROWSER_DEFAULT_MAX_SCREENSHOTS
    assert settings.keep_observations == limits.BROWSER_DEFAULT_KEEP_OBSERVATIONS
    assert settings.recheck_every == limits.BROWSER_DEFAULT_RECHECK_EVERY
    assert settings.max_stalls == limits.BROWSER_DEFAULT_MAX_STALLS
    assert settings.loop.max_iterations == limits.BROWSER_DEFAULT_MAX_ITERATIONS
    assert settings.loop.tool_settings is not None
    assert settings.loop.tool_settings.result_max_chars == limits.BROWSER_TOOL_RESULT_MAX_CHARS
    assert settings.permission_policy == PermissionPolicy.allow_all()
    assert settings.on_event is None and settings.episode_model_name is None and settings.recheck_model_name is None
    assert BrowserServerSettings(PlaywrightMCP).timeout == limits.BROWSER_DEFAULT_SERVER_TIMEOUT_SECONDS
    # Each settings object gets its own loop and policy, so one agent's settings never alias another's.
    other = build_settings()
    assert other.loop is not settings.loop


def test_a_preset_is_stored_as_its_registered_definition_and_env_is_read_only() -> None:
    """D-5, section 8.5: a preset given by name is stored as the registered McpPresetDefinition, and env cannot be changed after validation."""
    from vidbyte.agents.browser import BrowserServerSettings
    from vidbyte.tools.mcp import McpPresetRegistry

    by_name = BrowserServerSettings("playwright")
    by_definition = BrowserServerSettings(PlaywrightMCP)
    assert by_name.preset == McpPresetRegistry.get("playwright") == by_definition.preset
    assert isinstance(by_name.preset, McpPresetDefinition)
    server = BrowserServerSettings(FirecrawlMCP, env={"FIRECRAWL_API_KEY": FIRECRAWL_KEY})
    with pytest.raises(TypeError):
        server.env["FIRECRAWL_API_KEY"] = "fc-swapped-after-validation"  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        server.timeout = 1.0  # type: ignore[misc]
