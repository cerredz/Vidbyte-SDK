"""FILE: vidbyte/tools/builtins/codex/skill_functions.py

PURPOSE: The eight CodexHost tools over Codex goals, skills and plans: get_codex_goal and list_codex_skills, which only read, run_codex_goal, run_codex_skill, run_codex_openai_docs and run_codex_plan, which start paid Codex work on a new thread, and pause_codex_goal and resume_codex_goal, which stop or restart a stored goal's paid Codex work.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists the first five after the thread-helper tools, and the plan, pause and resume tools among the sixteen first-class tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: The four run tools and the resume tool hold one cap slot while the host starts and confirms the run, release it in finally, and then own the handle, as start_codex_review does (codex-host INV-32 and INV-33). Their posture comes only from the developer's spawn_defaults, and the model sets only the run's own input (INV-27, first-class INV-43). The resume tool clears from those defaults every field a goal resume refuses, read from the host's own CODEX_HOST_REJECTED_FIELDS and CODEX_HOST_GOAL_REJECTED_FIELDS, so a posture built for spawn still works for resume.
COMMON MODIFICATION PATTERNS: A new named skill wrapper is one more run tool here over its CodexHost function, with its texts in descriptions.py and its line in CodexHostTools.
KNOWN EDGE CASES: A thread without a goal is answered with NO_GOAL_TEXT by get_codex_goal, while pause and resume refuse it with the host's codex.session_not_found error result. A run whose command did not take is a codex.command_not_run error result, and the host already interrupted its turn. A collaboration mode in spawn_defaults makes the plan tool's run refused, because the plan's mode comes from Codex's plan preset (first-class EC-53).
RELATED DOCS: docs/spec/codex-host-thread-helpers/spec.md (section 9.2 tool table, rows 22 to 26); docs/spec/codex-host-first-class/spec.md (section 9.2 tool table, rows 29, 35 and 36)
TESTS: tests/features/codex_host/test_codex_host_helper_tools.py, tests/features/codex_host/test_codex_host_feature_tools.py
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.lib.constants.codex import CODEX_HOST_MIN_TOKEN_LIMIT
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_GOAL_REJECTED_FIELDS,
    CODEX_HOST_REJECTED_FIELDS,
)
from vidbyte.lib.dataclasses.codex import CodexThreadSettings
from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    GET_CODEX_GOAL_DESCRIPTION,
    LIST_CODEX_SKILLS_DESCRIPTION,
    PAUSE_CODEX_GOAL_DESCRIPTION,
    PLAN_PROMPT_DESCRIPTION,
    QUESTION_DESCRIPTION,
    RESUME_CODEX_GOAL_DESCRIPTION,
    RUN_CODEX_GOAL_DESCRIPTION,
    RUN_CODEX_OPENAI_DOCS_DESCRIPTION,
    RUN_CODEX_PLAN_DESCRIPTION,
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
PLAN = CodexHostOperation.RUN_CODEX_PLAN
PAUSE = CodexHostOperation.PAUSE_CODEX_GOAL
RESUME = CodexHostOperation.RESUME_CODEX_GOAL
THREAD_FIELD_PREFIX = "thread."
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
                    "token_budget": {"type": "integer", "minimum": CODEX_HOST_MIN_TOKEN_LIMIT, "description": RUN_GOAL_BUDGET_DESCRIPTION},
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


class RunCodexPlanTool(_CodexHostTool):
    """Starts a new Codex thread whose first turn runs in Codex's plan mode, under the developer's posture."""

    def spec(self) -> ToolSpec:
        # Only the task is the model's.
        return ToolSpec(
            name=PLAN.value,
            description=RUN_CODEX_PLAN_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["prompt"],
                "properties": {"prompt": {"type": "string", "description": PLAN_PROMPT_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the run's handle as JSON.
        return await self._run(PLAN.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Hold one cap slot while the host starts the plan-mode turn,
        # then own the handle; the request is the developer's posture
        # unchanged (first-class INV-43).
        prompt = self._resolve_text(call, "prompt", required=True)
        await self._scope.reserve(self._host, ONE_TURN, PLAN)
        try:
            handle = await self._host.run_codex_plan(prompt, request=self._scope.spawn_defaults)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)


class PauseCodexGoalTool(_CodexHostTool):
    """Pauses the goal stored on a Codex thread, so Codex starts no further goal turns."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=PAUSE.value,
            description=PAUSE_CODEX_GOAL_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the paused goal as JSON.
        return await self._run(PAUSE.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Pause the thread's goal.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        return self._json(await self._host.pause_codex_goal(thread_id))


class ResumeCodexGoalTool(_CodexHostTool):
    """Resumes the stopped goal stored on a Codex thread, under the developer's posture."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=RESUME.value,
            description=RESUME_CODEX_GOAL_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the resumed run's handle as JSON.
        return await self._run(RESUME.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Hold one cap slot while the host resumes the goal, then own
        # the handle; the request is the developer's posture without
        # the fields a goal resume refuses (first-class INV-31, INV-43).
        thread_id = self._resolve_text(call, "thread_id", required=True)
        request = self._resume_defaults(self._scope.spawn_defaults)
        await self._scope.reserve(self._host, ONE_TURN, RESUME)
        try:
            handle = await self._host.resume_codex_goal(thread_id, request=request)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)

    @staticmethod
    def _resume_defaults(defaults: CodexSpawnRequest) -> CodexSpawnRequest:
        # @intent resume-drops-the-fields-it-refuses
        # Every field a resume refuses as a continue does, and every
        # field a goal run refuses, goes back to a fresh request's
        # value, so the host's own tables decide what is cleared.
        fresh, fresh_thread = CodexSpawnRequest(), CodexThreadSettings()
        paths = (*CODEX_HOST_REJECTED_FIELDS[RESUME], *CODEX_HOST_GOAL_REJECTED_FIELDS)
        thread_names = [path.removeprefix(THREAD_FIELD_PREFIX) for path in paths if path.startswith(THREAD_FIELD_PREFIX)]
        thread = replace(defaults.thread, **{name: getattr(fresh_thread, name) for name in thread_names})
        return replace(defaults, thread=thread, **{path: getattr(fresh, path) for path in paths if not path.startswith(THREAD_FIELD_PREFIX)})


__all__ = [
    "GetCodexGoalTool",
    "ListCodexSkillsTool",
    "PauseCodexGoalTool",
    "ResumeCodexGoalTool",
    "RunCodexGoalTool",
    "RunCodexOpenaiDocsTool",
    "RunCodexPlanTool",
    "RunCodexSkillTool",
]
