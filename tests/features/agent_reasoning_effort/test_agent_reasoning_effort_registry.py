"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_registry.py

PURPOSE: Unit tests for ReasoningEffortRegistry and the tables it resolves: every spec
section 9.2 line returns exactly its "sent" values, every id without a row returns (),
every table row is a catalog text id with a non-empty, enum-ordered tuple, every sent
value has the section 9.2 wire form, the lookup normalizes prefix, alias, padding and
case, the section 8.5 registry texts come back character for character and in their
stated order, and attach deep-merges a private copy of the fragment without ever
touching the table.
ROLE IN CODEBASE: Covers spec INV-13, INV-20, AC-18, EC-27, FR-3 and the section 8.5
"registry" rows for vidbyte/lib/registries/reasoning_effort.py and
vidbyte/lib/configs/reasoning_effort.py. The carriers' refusals and the adapters'
bodies are proven in the refusals and wire modules; this one pins the lookup they
all share.
ARCHITECTURE NOTE: Pure in-process calls, no fakes. The oracle is the fixtures'
copy of the section 9.2 text, never the production table, so a production row that
drifts from the spec fails here. The structural test reads the production table only
to check its shape, so a later sourced row keeps the pack green.
FUNCTION INVENTORY: _scribble overwrites every value inside a payload in place;
_dict_ids lists the ids of every dict inside a payload; the test_* functions are one
behaviour each.
COMMON MODIFICATION PATTERNS: A new section 9.2 row is added to SENT or NO_ROW in the
fixtures, never here. A new refusal text is a new REFUSAL_CASES row.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert the table's size or freeze its key set.
2. Do not write REASONING_EFFORT_AS_OF as a literal; read it from the module.
3. Do not import a feature name outside the FEATURE_MISSING guard.
KNOWN EDGE CASES: gpt-5.6 is an alias of gpt-5.6-sol, so it is checked through
supported, not as a table key. The capability text lists the line's own values, never
the provider's union.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1 INV-13, INV-20,
6.2 AC-18, 8.5 and 9.2; tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_registry.py
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    NO_ROW,
    SENT,
    capability_reason,
    cell_id,
    deep_merge,
    fragment,
    mode_reason,
    no_row_reason,
    sent_cells,
)
from vidbyte.lib.constants.runners import MODEL_PROVIDER_RUNNER_TYPE_MAP
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.errors import ConfigurationError

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.configs import (
        REASONING_EFFORT_AS_OF,
        REASONING_EFFORT_FORMS,
        REASONING_EFFORT_SUPPORT,
    )
    from vidbyte.lib.enums import ModelProvider, ReasoningEffort
    from vidbyte.lib.registries import ReasoningEffortRegistry
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

LINES = [(provider, model) for provider, rows in SENT.items() for model in rows]
# Ids section 9.2 never lists, one per provider, plus providers with no wire form (EC-10).
UNLISTED = (
    ("openai", "gpt-effort-probe"),
    ("anthropic", "claude-effort-probe"),
    ("gemini", "gemini-effort-probe"),
    ("deepseek", "deepseek-effort-probe"),
    ("xai", "grok-effort-probe"),
    ("glm", "glm-effort-probe"),
    ("meta", "muse-spark-effort-probe"),
    ("mistral", "mistral-medium-latest"),
    ("minimax", "minimax-m2"),
)
# Section 8.5 "Which reason comes first": mode, then capability or no row, else None.
REFUSAL_CASES = (
    ("gemini", "gemini-3.5-flash", "xhigh", "DIRECT", "capability"),
    ("deepseek", "deepseek-v4-pro", "medium", "DIRECT", "capability"),
    ("openai", "o3", "high", "DIRECT", "no_row"),
    ("kimi", "kimi-k2.7-code", "low", "DIRECT", "no_row"),
    ("openai", "gpt-5.5", "high", "AUTO", "mode"),
    ("gemini", "gemini-3.5-flash", "xhigh", "AUTO", "mode"),
    ("openai", "o3", "high", "VIDBYTE_MANAGED", "mode"),
    ("openai", "gpt-5.5", "high", "DIRECT", "none"),
)
# Payloads that already hold keys inside the fragment's top-level keys (D-7, EC-6).
NESTED_CASES = (
    (
        "anthropic",
        "claude-sonnet-5",
        "high",
        {
            "model": "claude-sonnet-5",
            "output_config": {
                "format": {"type": "json_schema", "schema": {"type": "object"}}
            },
        },
    ),
    (
        "gemini",
        "gemini-3.5-flash",
        "low",
        {
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            }
        },
    ),
    (
        "gemini",
        "gemini-2.5-flash",
        "none",
        {
            "generationConfig": {
                "maxOutputTokens": 64,
                "thinkingConfig": {"includeThoughts": False},
            }
        },
    ),
    (
        "glm",
        "glm-5.3",
        "low",
        {"thinking": {"clear_thinking": False}, "reasoning_effort": "stale"},
    ),
    ("openai", "gpt-5.5", "xhigh", {"reasoning": {"summary": "auto"}}),
)


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _scribble(value: Any) -> None:
    # Overwrites every value inside value in place, so any object shared with the table shows the change.
    if isinstance(value, dict):
        for key in list(value):
            if isinstance(value[key], (dict, list)):
                _scribble(value[key])
            else:
                value[key] = "scribbled"
        value["scribbled"] = True
    elif isinstance(value, list):
        for item in value:
            _scribble(item)


def _dict_ids(value: Any) -> set[int]:
    # The identities of every dict inside value.
    if isinstance(value, dict):
        return {id(value)} | {
            inner for item in value.values() for inner in _dict_ids(item)
        }
    return set()


@pytest.mark.parametrize(
    ("provider", "model"), LINES, ids=[cell_id(*line) for line in LINES]
)
def test_supported_returns_each_section_9_2_line_in_enum_order(
    provider: str, model: str
) -> None:
    # INV-20, AC-4: the supported values of a line are exactly its
    # "sent" cells; a provider member and its string name agree.
    expected = tuple(ReasoningEffort(value) for value in SENT[provider][model])

    assert ReasoningEffortRegistry.supported(provider, model) == expected
    assert ReasoningEffortRegistry.supported(ModelProvider(provider), model) == expected


@pytest.mark.parametrize(
    ("provider", "model"),
    (*NO_ROW, *UNLISTED),
    ids=[cell_id(*line) for line in (*NO_ROW, *UNLISTED)],
)
def test_an_id_with_no_row_supports_nothing(provider: str, model: str) -> None:
    # INV-20, EC-10, EC-23, EC-24: a "refused (all)" line, a prefix-map
    # id, an unlisted id and a provider with no form all return ().
    assert ReasoningEffortRegistry.supported(provider, model) == ()


def test_every_table_row_is_a_catalog_text_id_with_an_enum_ordered_tuple() -> None:
    # INV-20, NG-14, section 8.5: a row is never empty (so () always
    # means no row), never out of order, and never for an id outside
    # the provider catalog's text ids. Size and key set are not pinned.
    order = {member: index for index, member in enumerate(ReasoningEffort)}
    problems = []
    for provider, rows in REASONING_EFFORT_SUPPORT.items():
        for model, values in rows.items():
            where = f"{provider.value}:{model}"
            if model != model.strip().lower():
                problems.append(f"{where} is not a lower-case, stripped id")
            if not values or not all(
                isinstance(value, ReasoningEffort) for value in values
            ):
                problems.append(f"{where} maps to {values!r}")
            elif list(values) != sorted(set(values), key=order.__getitem__):
                problems.append(
                    f"{where} is not in enum order without repeats: {values!r}"
                )
            if (
                MODEL_PROVIDER_RUNNER_TYPE_MAP.get(f"{provider.value}/{model}")
                != "text"
            ):
                problems.append(f"{where} is not a provider-catalog text id")
            if values and any(
                value not in REASONING_EFFORT_FORMS.get(provider, {})
                for value in values
            ):
                problems.append(
                    f"{where} supports a value its provider has no wire form for"
                )
    assert problems == []


@pytest.mark.parametrize(
    ("provider", "value"),
    sorted({(provider, value) for provider, _, value in sent_cells()}),
    ids=[
        cell_id(*pair)
        for pair in sorted({(provider, value) for provider, _, value in sent_cells()})
    ],
)
def test_each_sent_value_has_the_section_9_2_wire_form(
    provider: str, value: str
) -> None:
    # AC-3, NFR-4: the form row is the vendor's documented spelling,
    # including Gemini's upper-case levels and GLM's enabled switch.
    assert REASONING_EFFORT_FORMS[ModelProvider(provider)][
        ReasoningEffort(value)
    ] == fragment(provider, value)


@pytest.mark.parametrize(
    ("provider", "given", "normalized"),
    [
        ("openai", "openai/gpt-5.6", "gpt-5.6-sol"),
        ("openai", "gpt-5.6", "gpt-5.6-sol"),
        ("openai", " GPT-5.5 ", "gpt-5.5"),
        ("anthropic", "anthropic/claude-sonnet-5", "claude-sonnet-5"),
        ("gemini", "Gemini-3.5-Flash", "gemini-3.5-flash"),
    ],
)
def test_supported_normalizes_the_prefix_the_alias_padding_and_case(
    provider: str, given: str, normalized: str
) -> None:
    # AC-18, section 9.2 "How to read it": lookup uses the lower-cased
    # id after the prefix strip and MODEL_ALIASES.
    expected = tuple(ReasoningEffort(value) for value in SENT[provider][normalized])

    assert ReasoningEffortRegistry.supported(provider, given) == expected


@pytest.mark.parametrize(
    ("provider", "model"), [("acme", "gpt-5.5"), ("openai", ""), ("openai", "   ")]
)
def test_supported_refuses_an_unknown_provider_or_a_blank_model(
    provider: str, model: str
) -> None:
    # Section 8.5: an unknown provider or a blank model is a
    # ConfigurationError, never a silent ().
    with pytest.raises(ConfigurationError):
        ReasoningEffortRegistry.supported(provider, model)


@pytest.mark.parametrize(
    ("provider", "model", "value", "mode_name", "kind"),
    REFUSAL_CASES,
    ids=[cell_id(*case) for case in REFUSAL_CASES],
)
def test_refusal_gives_the_section_8_5_reason_mode_first(
    provider: str, model: str, value: str, mode_name: str, kind: str
) -> None:
    # Section 8.5, INV-5, INV-11, INV-20: the mode reason wins in every
    # gateway mode; otherwise the capability text for a line with a row,
    # the no-row text (naming the table date) for any other id, or None.
    expected = {
        "capability": capability_reason(
            provider, model, value, SENT.get(provider, {}).get(model, ())
        ),
        "no_row": no_row_reason(provider, model, value, REASONING_EFFORT_AS_OF),
        "mode": mode_reason(mode_name),
        "none": None,
    }[kind]

    reason = ReasoningEffortRegistry.refusal(
        provider=provider,
        model=model,
        effort=ReasoningEffort(value),
        mode=TextModelMode[mode_name],
    )

    assert reason == expected
    assert (
        ReasoningEffortRegistry.refusal(
            provider=ModelProvider(provider),
            model=model,
            effort=ReasoningEffort(value),
            mode=TextModelMode[mode_name],
        )
        == expected
    )


@pytest.mark.parametrize(
    ("provider", "given", "normalized"),
    [
        ("openai", " GPT-5.5 ", "gpt-5.5"),
        ("openai", "openai/gpt-5.6", "gpt-5.6-sol"),
        ("anthropic", "anthropic/claude-sonnet-5", "claude-sonnet-5"),
    ],
)
def test_refusal_names_the_model_as_given_but_stripped(
    provider: str, given: str, normalized: str
) -> None:
    # AC-18: support is the normalized id's, but the text quotes the
    # caller's own id (stripped), so they can find it in their code.
    reason = ReasoningEffortRegistry.refusal(
        provider=provider,
        model=given,
        effort=ReasoningEffort.MINIMAL,
        mode=TextModelMode.DIRECT,
    )

    assert reason == capability_reason(
        provider, given, "minimal", SENT[provider][normalized]
    )
    assert f"{provider}:{given.strip()} " in reason


def test_attach_deep_merges_into_keys_the_payload_already_holds() -> None:
    # INV-2, D-7, EC-6: nested keys the adapter set survive; any other
    # value the fragment names is replaced by the fragment's.
    for provider, model, value, payload in NESTED_CASES:
        merged = copy.deepcopy(payload)

        ReasoningEffortRegistry.attach(
            merged, provider=provider, model=model, effort=ReasoningEffort(value)
        )

        assert merged == deep_merge(payload, fragment(provider, value)), cell_id(
            provider, model, value
        )


def test_attach_gives_each_payload_a_private_copy_and_never_touches_the_table() -> None:
    # INV-13, EC-27: concurrent agents share the registry, so no payload
    # may hold an object of the table or of another payload.
    table_before = copy.deepcopy(REASONING_EFFORT_FORMS)
    for provider, model, value in sent_cells():
        first, second = {"model": model}, {"model": model}

        ReasoningEffortRegistry.attach(
            first, provider=provider, model=model, effort=ReasoningEffort(value)
        )
        ReasoningEffortRegistry.attach(
            second, provider=provider, model=model, effort=ReasoningEffort(value)
        )

        assert first == second == {"model": model, **fragment(provider, value)}, (
            cell_id(provider, model, value)
        )
        assert _dict_ids(first) & _dict_ids(second) == set()
        _scribble(first)
    assert REASONING_EFFORT_FORMS == table_before


def test_attach_does_nothing_without_an_effort_and_refuses_an_unsupported_cell() -> (
    None
):
    # Section 8.5: None is a no-op; an unsupported cell raises the very
    # text refusal gives, so an adapter can never send it.
    payload = {"model": "gpt-5.5", "input": [{"role": "user", "content": "Hi."}]}
    before = copy.deepcopy(payload)
    ReasoningEffortRegistry.attach(
        payload, provider="openai", model="gpt-5.5", effort=None
    )
    assert payload == before

    for provider, model, value in (
        ("gemini", "gemini-3.5-flash", "xhigh"),
        ("openai", "o3", "low"),
    ):
        target: dict[str, Any] = {"model": model}
        with pytest.raises(ConfigurationError) as refused:
            ReasoningEffortRegistry.attach(
                target, provider=provider, model=model, effort=ReasoningEffort(value)
            )
        assert str(refused.value) == ReasoningEffortRegistry.refusal(
            provider=provider,
            model=model,
            effort=ReasoningEffort(value),
            mode=TextModelMode.DIRECT,
        )
