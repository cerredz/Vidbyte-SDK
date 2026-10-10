"""FILE: scripts/review_agents/registry.py

PURPOSE: Finds the review agents and holds every agent prompt to one shape.
ROLE IN CODEBASE: run.py loads the registry in the plan, prompt, finalize, report, and check steps. An agent is any `NN-name.md` file in `.github/prompts/review-agents/`; the two digits set the order agents run in, and an optional frontmatter block sets the agent's scope, which defaults to one run per review, and whether it adds a guard. Adding an agent therefore means adding one file.
ARCHITECTURE NOTE: The frontmatter reader is a tiny `key: value` parser, so no YAML dependency enters a workflow whose plan job runs on the runner's bare Python.
COMMON MODIFICATION PATTERNS: A new frontmatter field joins _FIELDS, gets its validation in _fields(), and its AgentSpec field in review_data.py; a new required prompt section joins REQUIRED_SECTIONS.
KNOWN EDGE CASES: Windows line endings are normalized before parsing; a misnamed Markdown file in the agents folder is an error, not a skip, so a typo cannot silently drop an agent.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py checks the committed prompts and every rejection.
"""

from __future__ import annotations

import re
from pathlib import Path

from review_agents.review_data import AgentSpec, Scope

REQUIRED_SECTIONS = ("Goal", "Objective", "Instructions", "Constraints", "Output")
MINIMUM_STEPS = 4
MINIMUM_SECTION_WORDS = 40

_FILE_NAME = re.compile(r"^(?P<order>[0-9]{2})-(?P<name>[a-z][a-z0-9-]*)\.md$")
_FRONTMATTER = re.compile(r"\A---\n(?P<fields>.*?)\n---\n", re.DOTALL)
_SECTION = re.compile(r"^## (?P<title>.+)$", re.MULTILINE)
_STEP = re.compile(r"^[0-9]+\. ", re.MULTILINE)
_FIELDS = {"scope", "guard"}


class PromptContractError(ValueError):
    """A prompt file is missing something every review prompt must have."""


class PromptContract:
    """Checks one prompt: a title, the required sections, and real numbered instructions."""

    def check(self, label: str, body: str) -> None:
        # Exactly one title, so the agent knows which role it is playing.
        titles = [line for line in body.splitlines() if line.startswith("# ")]
        if len(titles) != 1:
            raise PromptContractError(f"{label}: expected one '# ' title, found {len(titles)}")
        # Every required section exists and says something substantial.
        sections = self._sections(body)
        for required in REQUIRED_SECTIONS:
            text = sections.get(required)
            if text is None:
                raise PromptContractError(f"{label}: missing the '## {required}' section")
            if len(text.split()) < MINIMUM_SECTION_WORDS:
                raise PromptContractError(f"{label}: '## {required}' has fewer than {MINIMUM_SECTION_WORDS} words")
        # The instructions are a real procedure, and the first thing it does is read the rules.
        steps = _STEP.split(sections["Instructions"])[1:]
        if len(steps) < MINIMUM_STEPS:
            raise PromptContractError(f"{label}: '## Instructions' needs at least {MINIMUM_STEPS} numbered steps")
        if "AGENTS.md" not in steps[0]:
            raise PromptContractError(f"{label}: the first instruction must tell the agent to read AGENTS.md")

    def _sections(self, body: str) -> dict[str, str]:
        # Splits on level-two headings; the text before the first heading is the preamble.
        parts = _SECTION.split(body)
        return {parts[index].strip(): parts[index + 1] for index in range(1, len(parts) - 1, 2)}


class AgentRegistry:
    """Loads every agent prompt in one directory, in run order."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._contract = PromptContract()

    def load(self) -> tuple[AgentSpec, ...]:
        # Every Markdown file here is an agent, so a misnamed file is an error, not a skip.
        paths = sorted(self._directory.glob("*.md"))
        if not paths:
            raise PromptContractError(f"No review agents found in {self._directory}")
        agents = tuple(self._agent(path) for path in paths)
        # Two agents with one number would make the run order ambiguous.
        orders = [agent.order for agent in agents]
        names = [agent.name for agent in agents]
        if len(set(orders)) != len(orders) or len(set(names)) != len(names):
            raise PromptContractError(f"Agent numbers and names must be unique: {names}")
        return agents

    def _agent(self, path: Path) -> AgentSpec:
        # Name and order come from the file name; scope and guard from the frontmatter.
        match = _FILE_NAME.match(path.name)
        if match is None:
            raise PromptContractError(f"{path.name}: agent files are named NN-name.md")
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        frontmatter = _FRONTMATTER.match(text)
        fields = self._fields(path.name, frontmatter.group("fields") if frontmatter else "")
        body = text[frontmatter.end() :] if frontmatter else text
        self._contract.check(path.name, body)
        return AgentSpec(name=match.group("name"), order=int(match.group("order")), scope=Scope(fields.get("scope", Scope.REVIEW.value)), guard=fields.get("guard", "false") == "true", prompt_path=path.as_posix(), body=body.strip() + "\n")

    def _fields(self, label: str, block: str) -> dict[str, str]:
        # A tiny `key: value` reader, so no YAML dependency enters the workflow.
        fields: dict[str, str] = {}
        for line in filter(None, (raw.strip() for raw in block.splitlines())):
            key, separator, value = line.partition(":")
            if not separator or key.strip() not in _FIELDS:
                raise PromptContractError(f"{label}: unknown frontmatter line {line!r}")
            fields[key.strip()] = value.strip()
        if fields.get("scope", Scope.REVIEW.value) not in {scope.value for scope in Scope}:
            raise PromptContractError(f"{label}: scope must be one of comment, review")
        if fields.get("guard", "false") not in {"true", "false"}:
            raise PromptContractError(f"{label}: guard must be true or false")
        return fields
