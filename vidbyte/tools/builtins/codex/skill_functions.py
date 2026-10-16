"""FILE: vidbyte/tools/builtins/codex/skill_functions.py

PURPOSE: The five CodexHost tools over Codex goals and skills: get_codex_goal and list_codex_skills, which only read, and run_codex_goal, run_codex_skill and run_codex_openai_docs, which start paid Codex work on a new thread.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these last, after the thread-helper tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: The three run tools hold one cap slot while the host starts and confirms the run, release it in finally, and then own the handle, as start_codex_review does (codex-host INV-32 and INV-33). Their posture comes only from the developer's spawn_defaults, and the model sets only the run's own input (INV-27).
COMMON MODIFICATION PATTERNS: A new named skill wrapper is one more run tool here over its CodexHost function, with its texts in descriptions.py and its line in CodexHostTools.
KNOWN EDGE CASES: A thread without a goal is answered with NO_GOAL_TEXT rather than an error. A run whose command did not take is a codex.command_not_run error result, and the host already interrupted its turn.
RELATED DOCS: docs/spec/codex-host-thread-helpers/spec.md (section 9.2 tool table, rows 22 to 26)
TESTS: tests/features/codex_host/test_codex_host_helper_tools.py
"""

from __future__ import annotations

from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    GET_CODEX_GOAL_DESCRIPTION,
    LIST_CODEX_SKILLS_DESCRIPTION,
    QUESTION_DESCRIPTION,
    RUN_CODEX_GOAL_DESCRIPTION,
    RUN_CODEX_OPENAI_DOCS_DESCRIPTION,
    RUN_CODEX_SKILL_DESCRIPTION,
    RUN_GOAL_BUDGET_DESCRIPTION,
    RUN_GOAL_OBJECTIVE_DESCRIPTION,
    SKILL_NAME_DESCRIPTION,
    SKILL_PROMPT_DESCRIPTION,
    SKILLS_CWD_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

GOAL = CodexHostOperation.GET_CODEX_GOAL
RUN_GOAL = CodexHostOperation.RUN_CODEX_GOAL
SKILLS = CodexHostOperation.LIST_CODEX_SKILLS
RUN_SKILL = CodexHostOperation.RUN_CODEX_SKILL
DOCS = CodexHostOperation.RUN_CODEX_OPENAI_DOCS
ONE_TURN = 1
NO_GOAL_TEXT = "Thread {thread_id} has no goal."


class GetCodexGoalTool(_CodexHostTool):
    """Reads the goal stored on a Codex thread, without loading the thread."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=GOAL.value,
            description=GET_CODEX_GOAL_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the goal as JSON, or say there is none.
        return await self._run(GOAL.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # A thread without a goal is an answer, not a failure.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        goal = await self._host.get_codex_goal(thread_id)
        return NO_GOAL_TEXT.format(thread_id=thread_id) if goal is None else self._json(goal)


class RunCodexGoalTool(_CodexHostTool):
    """Starts a goal run on a new Codex thread, under the developer's posture."""

    def spec(self) -> ToolSpec:
        # The objective is required; the budget is optional.
        return ToolSpec(
            name=RUN_GOAL.value,
            description=RUN_CODEX_GOAL_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["objective"],
                "properties": {
                    "objective": {"type": "string", "description": RUN_GOAL_OBJECTIVE_DESCRIPTION},
                    "token_budget": {"type": "integer", "description": RUN_GOAL_BUDGET_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the run's handle as JSON.
        return await self._run(RUN_GOAL.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Hold one cap slot while the host starts the run and confirms
        # its goal, then own the handle (INV-27).
        objective = self._resolve_text(call, "objective", required=True)
        token_budget = self._resolve_count(call, "token_budget")
        await self._scope.reserve(self._host, ONE_TURN, RUN_GOAL)
        try:
            handle = await self._host.run_codex_goal(objective, token_budget, request=self._scope.spawn_defaults)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)


class ListCodexSkillsTool(_CodexHostTool):
    """Lists the skills Codex offers for one working folder."""

    def spec(self) -> ToolSpec:
        # The folder is optional.
        return ToolSpec(
            name=SKILLS.value,
            description=LIST_CODEX_SKILLS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"cwd": {"type": "string", "description": SKILLS_CWD_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the skills as a JSON array.
        return await self._run(SKILLS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # An omitted folder lists the app-server's own.
        cwd = self._resolve_text(call, "cwd")
        return self._json(await self._host.list_codex_skills(cwd))


class RunCodexSkillTool(_CodexHostTool):
    """Starts a new Codex thread whose first turn runs one skill on a prompt."""

    def spec(self) -> ToolSpec:
        # The skill and the prompt are both required.
        return ToolSpec(
            name=RUN_SKILL.value,
            description=RUN_CODEX_SKILL_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["skill", "prompt"],
                "properties": {
                    "skill": {"type": "string", "description": SKILL_NAME_DESCRIPTION},
                    "prompt": {"type": "string", "description": SKILL_PROMPT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the run's handle as JSON.
        return await self._run(RUN_SKILL.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Hold one cap slot while the host starts the run and confirms
        # its skill, then own the handle (INV-27).
        skill = self._resolve_text(call, "skill", required=True)
        prompt = self._resolve_text(call, "prompt", required=True)
        await self._scope.reserve(self._host, ONE_TURN, RUN_SKILL)
        try:
            handle = await self._host.run_codex_skill(skill, prompt, request=self._scope.spawn_defaults)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)


class RunCodexOpenaiDocsTool(_CodexHostTool):
    """Starts a new Codex thread that answers from the OpenAI documentation."""

    def spec(self) -> ToolSpec:
        # Only the question is the model's.
        return ToolSpec(
            name=DOCS.value,
            description=RUN_CODEX_OPENAI_DOCS_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["question"],
                "properties": {"question": {"type": "string", "description": QUESTION_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the run's handle as JSON.
        return await self._run(DOCS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Hold one cap slot while the host starts the run and confirms
        # its skill, then own the handle (INV-27).
        question = self._resolve_text(call, "question", required=True)
        await self._scope.reserve(self._host, ONE_TURN, DOCS)
        try:
            handle = await self._host.run_codex_openai_docs(question, request=self._scope.spawn_defaults)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)


__all__ = [
    "GetCodexGoalTool",
    "ListCodexSkillsTool",
    "RunCodexGoalTool",
    "RunCodexOpenaiDocsTool",
    "RunCodexSkillTool",
]
