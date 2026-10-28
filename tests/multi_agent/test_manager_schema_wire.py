"""FILE: tests/multi_agent/test_manager_schema_wire.py

PURPOSE:
    Proves that the structured-output schema the MultiAgent manager sends is
    one that Anthropic and OpenAI strict mode accept. On main the plan phase
    sent an untyped payload and an open metadata map, so every Anthropic
    manager phase failed with HTTP 400 ("Schema type is missing for schema:
    {'default': None, 'title': 'Payload'}") and the team run never started.
ROLE IN CODEBASE:
    Regression tests for _TaskSpecOutput and _DecisionOutput in
    vidbyte/agents/multi/orchestrator.py, read off the real request bodies
    the Anthropic and OpenAI adapters build.
ARCHITECTURE NOTE:
    Only HttpTransport.request is scripted. The team, the manager forks, the
    runtime, the schema formatter and the provider adapters are production
    code, and the scripted replies walk the run through plan, delegate,
    worker, finish and the final answer.
COMMON MODIFICATION PATTERNS:
    When Anthropic changes its structured-output rules, update
    AnthropicSchemaRules from "JSON Schema limitations" in
    https://platform.claude.com/docs/en/build-with-claude/structured-outputs.
WHAT NOT TO DO:
    Do not reach the network or read keys from the environment.
KNOWN EDGE CASES:
    A prompt-only provider may still return an object payload; it validates
    as before. Anthropic's union and optional parameter limits are counted
    across the whole schema, not per object.
RELATED DOCS:
    docs/design/multiagent-manager-schema-types.md and
    vidbyte/agents/multi/README.md.
TESTS:
    python -m pytest tests/multi_agent/test_manager_schema_wire.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from vidbyte import Agent
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.multi.agent import MultiAgent
from vidbyte.agents.multi.orchestrator import _DecisionOutput
from vidbyte.agents.multi.transfer import AgentBinding, AgentTransfer
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.multi_agent import MultiAgentSettings
from vidbyte.lib.http import HttpResponse, HttpTransport

PLAN = {"plan_summary": "One task.", "tasks": [{"task_id": "t1", "goal": "Do the work.", "owner": "worker", "depends_on": [], "required": True, "acceptance_criteria": ["The work is done."], "payload": "notes for the worker", "max_attempts": None}], "verified_facts": [], "facts_to_find": [], "facts_to_derive": [], "educated_guesses": [], "next_action": "Delegate t1.", "rationale": "Single task."}
DELEGATE = {"action": "delegate", "task_id": "t1", "owner": "worker", "instruction": "Do the work.", "payload": "notes for the worker", "next_action": None, "final_answer": None, "loop_detected": False, "progress_made": True, "rationale": "Ready."}
FINISH = {"action": "finish", "task_id": None, "owner": None, "instruction": None, "payload": None, "next_action": None, "final_answer": "The work is done.", "loop_detected": False, "progress_made": True, "rationale": "Done."}


class AnthropicSchemaRules:
    """Checks a JSON schema against Anthropic's documented structured-output limitations."""

    TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
    FORMATS = frozenset({"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"})
    UNSUPPORTED = frozenset({"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength", "maxItems", "oneOf", "patternProperties", "if", "then", "else", "not"})
    MAX_UNION_PARAMETERS = 16
    MAX_OPTIONAL_PARAMETERS = 24

    def violations(self, schema: Mapping[str, Any]) -> list[str]:
        # Walks every node, then applies the request-wide parameter limits.
        defs = {**dict(schema.get("definitions") or {}), **dict(schema.get("$defs") or {})}
        found = [problem for path, node in self._nodes(schema, "#") for problem in self._node_violations(path, node, defs)]
        found.extend(self._recursion_violations(defs))
        found.extend(self._limit_violations(schema))
        return found

    def _nodes(self, node: Any, path: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
        # Yields each schema node with its JSON-pointer-like path.
        if not isinstance(node, Mapping):
            return
        yield path, node
        for key in ("$defs", "definitions", "properties"):
            for name, child in dict(node.get(key) or {}).items():
                yield from self._nodes(child, f"{path}/{key}/{name}")
        if isinstance(node.get("items"), Mapping):
            yield from self._nodes(node["items"], f"{path}/items")
        for key in ("anyOf", "allOf"):
            for index, child in enumerate(node.get(key) or ()):
                yield from self._nodes(child, f"{path}/{key}/{index}")

    def _node_violations(self, path: str, node: Mapping[str, Any], defs: Mapping[str, Any]) -> list[str]:
        # One node must be typed (or a union or a local ref), closed when it is an object, and use only supported keywords.
        if path.rsplit("/", 1)[-1] in ("$defs", "definitions") or path.endswith(("/$defs", "/definitions")):
            return []
        problems: list[str] = []
        declared = node.get("type")
        types = set(declared) if isinstance(declared, list) else {declared} if declared is not None else set()
        if not types and not any(key in node for key in ("anyOf", "allOf", "$ref")):
            problems.append(f"{path}: schema type is missing")
        if types - self.TYPES:
            problems.append(f"{path}: unsupported type {sorted(types - self.TYPES)}")
        if "object" in types and node.get("additionalProperties") is not False:
            problems.append(f"{path}: object must set additionalProperties to false, got {node.get('additionalProperties')!r}")
        ref = node.get("$ref")
        if isinstance(ref, str) and (not ref.startswith(("#/$defs/", "#/definitions/")) or ref.rsplit("/", 1)[-1] not in defs):
            problems.append(f"{path}: $ref {ref!r} is external or unresolved")
        if any(isinstance(part, Mapping) and "$ref" in part for part in node.get("allOf") or ()):
            problems.append(f"{path}: allOf with $ref is not supported")
        problems.extend(f"{path}: unsupported keyword {key}" for key in sorted(self.UNSUPPORTED & set(node)))
        if node.get("minItems") not in (None, 0, 1):
            problems.append(f"{path}: minItems {node['minItems']} is not 0 or 1")
        if "format" in node and node["format"] not in self.FORMATS:
            problems.append(f"{path}: unsupported string format {node['format']!r}")
        if any(isinstance(value, (dict, list)) for value in node.get("enum") or ()):
            problems.append(f"{path}: enum holds a complex value")
        return problems

    def _recursion_violations(self, defs: Mapping[str, Any]) -> list[str]:
        # Recursive schemas are unsupported, so no definition may reach itself through refs.
        edges = {name: {ref.rsplit("/", 1)[-1] for ref in self._refs(body)} for name, body in defs.items()}
        problems = []
        for start in edges:
            seen, frontier = set(), set(edges[start])
            while frontier:
                current = frontier.pop()
                if current == start:
                    problems.append(f"#/$defs/{start}: recursive schema")
                    break
                if current not in seen:
                    seen.add(current)
                    frontier |= edges.get(current, set())
        return problems

    def _refs(self, node: Any) -> Iterator[str]:
        # Yields every $ref string under a node.
        if isinstance(node, Mapping):
            if isinstance(node.get("$ref"), str):
                yield node["$ref"]
            for value in node.values():
                yield from self._refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from self._refs(value)

    def _limit_violations(self, schema: Mapping[str, Any]) -> list[str]:
        # Counts union-typed and optional parameters across the whole schema.
        unions = optional = 0
        for _, node in self._nodes(schema, "#"):
            required = set(node.get("required") or ())
            for name, child in dict(node.get("properties") or {}).items():
                unions += int("anyOf" in child or isinstance(child.get("type"), list))
                optional += int(name not in required)
        problems = []
        if unions > self.MAX_UNION_PARAMETERS:
            problems.append(f"{unions} union-typed parameters exceed {self.MAX_UNION_PARAMETERS}")
        if optional > self.MAX_OPTIONAL_PARAMETERS:
            problems.append(f"{optional} optional parameters exceed {self.MAX_OPTIONAL_PARAMETERS}")
        return problems


class OpenAIStrictSchemaRules(AnthropicSchemaRules):
    """OpenAI strict mode adds one rule to the shared ones: every property is required."""

    def _node_violations(self, path: str, node: Mapping[str, Any], defs: Mapping[str, Any]) -> list[str]:
        # Keeps the shared typed-and-closed checks and requires every listed property.
        problems = [problem for problem in super()._node_violations(path, node, defs) if "keyword" not in problem and "minItems" not in problem]
        properties = node.get("properties")
        if isinstance(properties, Mapping) and set(node.get("required") or ()) != set(properties):
            problems.append(f"{path}: strict mode requires every property in required")
        return problems


class ScriptedTeamTransport:
    """Answers each manager phase, the worker, and the final answer in the provider's own response shape."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.bodies: list[dict[str, Any]] = []

    async def request(self, *_: Any, json_body: Any = None, **__: Any) -> HttpResponse:
        # Records the body, picks the reply for the phase its schema names, and wraps it for the provider.
        body = json.loads(json.dumps(json_body))
        self.bodies.append(body)
        title = (self.schema(body) or {}).get("title")
        decisions = sum(1 for sent in self.bodies if (self.schema(sent) or {}).get("title") == "_DecisionOutput")
        if title == "_PlanOutput":
            text = json.dumps(PLAN)
        elif title == "_DecisionOutput":
            text = json.dumps(DELEGATE if decisions == 1 else FINISH)
        else:
            text = "Worker finished the work." if self.is_worker(body) else "The work is done."
        if self.provider == "anthropic":
            wire = {"id": "m", "type": "message", "role": "assistant", "model": body["model"], "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}}
        else:
            wire = {"id": "r", "output_text": text, "usage": {"input_tokens": 10, "output_tokens": 5}}
        return HttpResponse(status_code=200, body=json.dumps(wire), headers={"content-type": "application/json"})

    def schema(self, body: Mapping[str, Any]) -> Mapping[str, Any] | None:
        # Reads the structured-output schema from where this provider carries it.
        carrier = body.get("output_config") if self.provider == "anthropic" else body.get("text")
        return carrier.get("format", {}).get("schema") if isinstance(carrier, Mapping) else None

    def is_worker(self, body: Mapping[str, Any]) -> bool:
        # The worker is the only agent whose system prompt is "Work.".
        return "Work." in str(body.get("system") or body.get("instructions") or "")

    def schemas(self) -> dict[str, Mapping[str, Any]]:
        # Every distinct schema sent, keyed by its title.
        return {schema["title"]: schema for schema in (self.schema(body) for body in self.bodies) if schema is not None}


def _run_team(monkeypatch: pytest.MonkeyPatch, provider: str, model: str, key: str) -> tuple[ScriptedTeamTransport, Any]:
    # The billing run's build case, with only the provider and model varied.
    transport = ScriptedTeamTransport(provider)
    monkeypatch.setattr(HttpTransport, "request", transport.request)
    settings = dict(provider=provider, model_name=model, api_keys=[key], model_mode=TextModelMode.DIRECT)
    worker = Agent(name="worker", system_prompt="Work.", max_iterations=2, agent_metadata=AgentMetadata(name="worker", description="Does the work.", use_cases="work"), **settings)
    team = MultiAgent(name="team", system_prompt="Coordinate.", orchestrator=BaseAgent(name="manager", system_prompt="Manage.", max_iterations=2, **settings), agents=(AgentBinding(worker, transfer=AgentTransfer()),), settings=MultiAgentSettings(max_rounds=2))
    reply = asyncio.run(team.arun("Do the work."))
    return transport, reply


def test_anthropic_manager_schema_meets_anthropic_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] On main Anthropic rejected the plan schema, so the run raised after three free 400s.
    transport, reply = _run_team(monkeypatch, "anthropic", "claude-haiku-5-5", "sk-ant-api03-fake")
    schemas = transport.schemas()
    assert set(schemas) == {"_PlanOutput", "_DecisionOutput"}
    for title, schema in schemas.items():
        assert AnthropicSchemaRules().violations(schema) == [], title
    assert "The work is done." in str(reply.content)


def test_openai_manager_schema_meets_strict_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] The OpenAI adapter sends the same strict() schema, so it must pass strict mode's rules too.
    transport, reply = _run_team(monkeypatch, "openai", "gpt-5.4-mini", "sk-proj-fake")
    schemas = transport.schemas()
    assert set(schemas) == {"_PlanOutput", "_DecisionOutput"}
    for title, schema in schemas.items():
        assert OpenAIStrictSchemaRules().violations(schema) == [], title
    assert "The work is done." in str(reply.content)


def test_payload_text_reaches_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Silent Failure] The delegated text payload must arrive in the worker's request unchanged.
    transport, _ = _run_team(monkeypatch, "anthropic", "claude-haiku-5-5", "sk-ant-api03-fake")
    worker_bodies = [body for body in transport.bodies if transport.is_worker(body)]
    assert worker_bodies, "the worker was never called"
    assert '"payload":"notes for the worker"' in json.dumps(worker_bodies[0]["messages"]).replace("\\", "")


def test_rule_checker_rejects_the_old_shapes() -> None:
    # [Silent Failure] The checker must flag both nodes main sent, or the wire tests could pass vacuously.
    old = {"type": "object", "additionalProperties": False, "required": ["payload", "metadata"], "properties": {"payload": {"default": None, "title": "Payload"}, "metadata": {"type": "object", "additionalProperties": True, "title": "Metadata"}}}
    problems = AnthropicSchemaRules().violations(old)
    assert any("payload: schema type is missing" in problem for problem in problems)
    assert any("metadata: object must set additionalProperties to false" in problem for problem in problems)
    recursive = {"$defs": {"Node": {"type": "object", "additionalProperties": False, "properties": {"child": {"$ref": "#/$defs/Node"}}, "required": ["child"]}}, "$ref": "#/$defs/Node"}
    assert any("recursive" in problem for problem in AnthropicSchemaRules().violations(recursive))


@pytest.mark.parametrize("payload", [{"path": "a.py"}, ["a", "b"], 3, True, None, "text"])
def test_lenient_provider_payload_still_validates(payload: Any) -> None:
    # [Edge Case] A prompt-only provider may still return a non-text JSON payload; it is accepted exactly as before.
    decision = _DecisionOutput.model_validate({"action": "delegate", "task_id": "t1", "payload": payload})
    assert decision.payload == payload
