"""FILE: vidbyte/harnesses/native/grok/commands.py

PURPOSE: Defines the fourteen public Grok command functions (GrokCommands: run_grok_command and the named wrappers run_grok_goal, run_grok_implement, run_grok_design, run_grok_execute_plan, run_grok_review, run_grok_code_review, run_grok_resume_claude, run_grok_resume_codex, run_grok_resume_cursor, run_grok_imagine, run_grok_imagine_video, run_grok_plan and run_grok_explore) and the flow of one run (GrokCommandRun): build the slash-command line, run `grok --single` once with the caller's key, a minted session id and streaming JSON output, and verify from the run's own record that the command really ran.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/grok/__init__.py and re-exported from vidbyte.harnesses.native. GrokCommandRun uses NativeLauncher, NativeErrorFactory and NativeCommandEvidence from hostkit, GrokHome and GrokStore (grok/store.py) for the private home and the new thread's summary.json, GrokStreamWire (grok/wire.py) to read the stream, and GrokHelperRun.export (grok/helpers.py) for the code-review transcript.
ARCHITECTURE NOTE: A command run is #1036's run_grok_thread with three changes: the prompt is the §9.2 slash line (or the task, with --agent, for plan and explore), the output is streaming JSON so every tool call is visible, and the SDK mints the thread id with --session-id (spec D-29), so a run that times out or floods its cap still names the paid thread. Every argument is checked in GrokCommandArguments before anything starts, the text under its public name (spec D-25, D-30, D-32). Evidence fails closed (spec INV-8): a tool call per GROK_EVIDENCE_TOOLS and GROK_EVIDENCE_FRAGMENTS, the agent_name of the new thread's own summary.json for an agent, or the run's own keyless export for /code-review (spec D-28). The output cap is NATIVE_PROCESS_MAX_OUTPUT_BYTES, because the stream carries every tool call (spec INV-16). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: GrokCommands holds the fourteen public functions and _call, the one guarded try they share. GrokCommandRun.execute is the narrated main function of one run; line builds the slash-command line; _argv builds the command line; _words turns one part of the line into its words.
COMMON MODIFICATION PATTERNS: A new wrapped command is one GrokCommand member, its evidence rows in GROK_EVIDENCE_TOOLS and GROK_EVIDENCE_FRAGMENTS, its text name in NATIVE_TEXT_ARGUMENTS, one NativeThreadOperation member and one wrapper here. A new slash option is a GrokCommandFlag member, a GrokCommandArguments field with its rule, and one part in line.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the key on argv, in the line or in a file; it travels only in XAI_API_KEY and GROK_CODE_XAI_API_KEY of the run child. 2. Do not accept a run without its evidence, and do not read the evidence from any other thread's record. 3. Do not take the thread id from the stream; the SDK minted it. 4. Do not let a named wrapper's text become a slash option; GrokCommandArguments refuses it before the run.
KNOWN EDGE CASES: A failure before Grok reported a tool call or the end carries the minted id and says the thread may not exist (spec INV-29, EC-81). With the default permission mode Grok refuses edits headless, so editing commands need permission_mode=ACCEPT_EDITS (spec EC-43). A same-named skill in the workspace or the user's home replaces the bundled one and the run fails closed with command_not_run (spec EC-78). /imagine-video needs Grok's video tools on (features.video_gen, spec EC-74).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_grok_commands.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.grok.helpers import GrokHelperRun
from vidbyte.harnesses.native.grok.store import GrokHome, GrokStore
from vidbyte.harnesses.native.grok.wire import GrokStreamWire
from vidbyte.harnesses.native.hostkit import (
    NativeCommandEvidence,
    NativeErrorFactory,
    NativeLauncher,
)
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    GrokCommandArguments,
    GrokThreadConfig,
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import (
    GrokAgent,
    GrokCommand,
    GrokCommandFlag,
    GrokFlag,
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class GrokCommands:
    """The public Grok command functions: run one bundled slash command or agent headless with the caller's key, and return only when the run shows it ran."""

    @staticmethod
    async def run_grok_command(command: GrokCommand, arguments: str = "", *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/<command> <arguments>` as one new Grok thread; arguments are the caller's own raw line, sent as they are."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_COMMAND, command=command, text=arguments, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_goal(objective: str, *, api_key: str, workspace: str | Path, budget_tokens: int | None = None, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/goal <objective>`, with `--budget <budget_tokens>` when given, in-turn with Grok's goal driver."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_GOAL, command=GrokCommand.GOAL, text=objective, budget_tokens=budget_tokens, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_implement(task: str, *, api_key: str, workspace: str | Path, effort: int | None = None, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/implement <task>`; pass config=GrokThreadConfig(permission_mode=GrokPermissionMode.ACCEPT_EDITS) to let it edit files."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_IMPLEMENT, command=GrokCommand.IMPLEMENT, text=task, effort=effort, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_design(description: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/design <description>`; pass config=GrokThreadConfig(permission_mode=GrokPermissionMode.ACCEPT_EDITS) to let it write the design doc."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_DESIGN, command=GrokCommand.DESIGN, text=description, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_execute_plan(design_doc: str | Path, *, api_key: str, workspace: str | Path, effort: int | None = None, concurrency: int | None = None, dry_run: bool = False, auto_pr: bool = False, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/execute-plan <design_doc>`; it needs permission_mode=ACCEPT_EDITS to edit, and auto_pr=True pushes branches and opens pull requests."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_EXECUTE_PLAN, command=GrokCommand.EXECUTE_PLAN, design_doc=design_doc, effort=effort, concurrency=concurrency, dry_run=dry_run, auto_pr=auto_pr, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_review(*, api_key: str, workspace: str | Path, local: bool = False, branch: str | None = None, pr: int | str | None = None, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/review` on the local changes, one branch or one pull request; pr posts a pending review on GitHub."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_REVIEW, command=GrokCommand.REVIEW, local=local, branch=branch, pr=pr, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_code_review(*, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/code-review` on the current branch; the run's own export transcript is its evidence."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_CODE_REVIEW, command=GrokCommand.CODE_REVIEW, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_resume_claude(session: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/resume-claude <session>` to carry a Claude Code session on in Grok."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_RESUME_CLAUDE, command=GrokCommand.RESUME_CLAUDE, text=session, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_resume_codex(session: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/resume-codex <session>` to carry a Codex session on in Grok."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_RESUME_CODEX, command=GrokCommand.RESUME_CODEX, text=session, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_resume_cursor(session: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/resume-cursor <session>` to carry a Cursor session on in Grok."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_RESUME_CURSOR, command=GrokCommand.RESUME_CURSOR, text=session, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_imagine(description: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/imagine <description>` to make or edit an image."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_IMAGINE, command=GrokCommand.IMAGINE, text=description, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_imagine_video(description: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run `/imagine-video <description>`; Grok's video tools must be on (features.video_gen)."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_IMAGINE_VIDEO, command=GrokCommand.IMAGINE_VIDEO, text=description, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_plan(task: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run task with Grok's plan agent, which plans without editing."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_PLAN, agent=GrokAgent.PLAN, text=task, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_grok_explore(question: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Answer question with Grok's explore agent, which reads the workspace without editing."""
        return await GrokCommands._call(NativeThreadOperation.RUN_GROK_EXPLORE, agent=GrokAgent.EXPLORE, text=question, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(
        operation: NativeThreadOperation,
        *,
        command: GrokCommand | None = None,
        agent: GrokAgent | None = None,
        text: str = "",
        design_doc: str | Path | None = None,
        budget_tokens: int | None = None,
        effort: int | None = None,
        concurrency: int | None = None,
        dry_run: bool = False,
        auto_pr: bool = False,
        local: bool = False,
        branch: str | None = None,
        pr: int | str | None = None,
        api_key: str,
        workspace: str | Path,
        model: str | None,
        skills: Sequence[str | Path],
        config: GrokThreadConfig | None,
    ) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.GROK, operation)
        request: NativeThreadRequest | None = None
        try:
            # Check the command, its options and its text under the
            # text's public name before anything starts (spec D-25,
            # D-30). /review and /code-review take no text, so their
            # empty one is the raw command's arguments.
            field = native_threads.NATIVE_TEXT_ARGUMENTS.get(operation, native_threads.NATIVE_TEXT_ARGUMENTS[NativeThreadOperation.RUN_GROK_COMMAND])
            arguments = GrokCommandArguments(command=command, agent=agent, text=text, design_doc=design_doc, budget_tokens=budget_tokens, effort=effort, concurrency=concurrency, dry_run=dry_run, auto_pr=auto_pr, local=local, branch=branch, pr=pr, named=operation is not NativeThreadOperation.RUN_GROK_COMMAND, text_field=field)
            if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM:
                RecordFieldValidator.require_command_line_units(arguments.text, field, max_units=native_threads.NATIVE_WINDOWS_COMMAND_TEXT_MAX_UNITS)

            # The run is a new thread whose prompt is the slash line;
            # then no skill folder of the caller's may be named like the
            # command it runs (spec D-32).
            request = NativeThreadRequest(harness=NativeHarness.GROK, verb=NativeThreadVerb.RUN, prompt=GrokCommandRun.line(arguments), api_key=api_key, workspace=workspace, model=model, skills=skills)
            arguments = dataclasses.replace(arguments, skill_names=tuple(Path(folder).name for folder in request.skills))
            settings = GrokThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, GrokThreadConfig)
            return await GrokCommandRun.execute(request, arguments, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class GrokCommandRun:
    """One Grok command run: launcher, private home, minted id, environment, argv, run, stream and evidence."""

    @staticmethod
    async def execute(request: NativeThreadRequest, arguments: GrokCommandArguments, config: GrokThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Find grok: the caller's command, then PATH, then the copy the
        # Grok installer puts under the user's home folder.
        launcher = NativeLauncher.resolve(config.grok_command, program=native_threads.GROK_PROGRAM, fallback=GrokHome.fallback(), errors=errors, request=request)

        # Prepare the private Grok home for this workspace with the
        # caller's skills, off the event loop; from here on the key is
        # scrubbed from anything grok prints.
        home = await asyncio.to_thread(GrokHome.prepare, request, errors)
        errors.register_secret(request.api_key)

        # Name the new thread before it exists, so even a run that
        # times out or floods its cap names the thread the caller paid
        # for (spec D-29).
        thread_id = str(uuid.uuid4())

        # @intent grok-goal-runs-with-workflows-off
        # The key and the private home travel in the environment; /goal
        # also gets GROK_WORKFLOWS=0, so it runs in-turn with the
        # update_goal driver instead of the background engine.
        environment = GrokHome.environment(home, request.api_key)
        if arguments.command is GrokCommand.GOAL:
            environment[NativeEnvironmentVariable.GROK_WORKFLOWS.value] = native_threads.GROK_WORKFLOWS_OFF

        # Run grok once, headless, in the workspace, with no standard
        # input; the stream carries every tool call, so its cap is the
        # process cap (spec INV-16).
        invocation = CliInvocation(
            argv=GrokCommandRun._argv(launcher, request, arguments, config, thread_id),
            env_overlay=environment,
            timeout_seconds=config.timeout_seconds,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
        )
        outcome = await CliRunner().run(invocation)

        # A program the OS would not start is reported with its path;
        # no thread exists then.
        if outcome.launch_failure is not None:
            program, *_arguments = launcher
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request)

        # Read the stream on the minted id: errors, the end event and
        # the answer text (spec §9.2 reading order).
        result = GrokStreamWire.read(outcome, request, errors, timeout_seconds=config.timeout_seconds, thread_id=thread_id)

        # @intent grok-command-evidence-fails-closed
        # Return only when the run's own record shows the command ran
        # (spec INV-8): an agent is named in the new thread's own
        # summary.json, /code-review's skill text is in the run's own
        # export, and every other command made its evidence tool call.
        command, agent = arguments.command, arguments.agent
        if agent is not None:
            found = await asyncio.to_thread(GrokStore.thread, home, request, errors, thread_id=thread_id)
            actual = None if found is None else found.agent_name
            NativeCommandEvidence.require_value(actual, expected=agent.value, member=native_threads.GROK_AGENT_NAME_FIELD, errors=errors, request=request, thread_id=thread_id)
        elif command is GrokCommand.CODE_REVIEW:
            document = await GrokHelperRun.export(home, request, config, errors, thread_id=thread_id)
            NativeCommandEvidence.require_text(document.text, fragment=native_threads.GROK_CODE_REVIEW_FRAGMENT, errors=errors, request=request, thread_id=thread_id)
        elif command is not None:
            calls = GrokStreamWire.tool_calls(outcome.stdout)
            NativeCommandEvidence.require(calls, tools=native_threads.GROK_EVIDENCE_TOOLS[command], fragment=native_threads.GROK_EVIDENCE_FRAGMENTS.get(command), errors=errors, request=request, thread_id=thread_id)
        return result

    @staticmethod
    def line(arguments: GrokCommandArguments) -> str:
        # An agent reads its task as the whole line.
        if arguments.command is None:
            return arguments.text

        # Otherwise /<command>, then each part that is set, in the §9.2
        # order: /implement takes its effort before the task and
        # /execute-plan after the plan; a raw run_grok_command line has
        # only its own text.
        leading = arguments.effort if arguments.command is GrokCommand.IMPLEMENT else None
        trailing = None if leading is not None else arguments.effort
        parts = (
            (GrokCommandFlag.EFFORT, leading),
            (None, arguments.design_doc),
            (None, arguments.text),
            (GrokCommandFlag.BUDGET, arguments.budget_tokens),
            (GrokCommandFlag.EFFORT, trailing),
            (GrokCommandFlag.CONCURRENCY, arguments.concurrency),
            (GrokCommandFlag.DRY_RUN, arguments.dry_run),
            (GrokCommandFlag.AUTO_PR, arguments.auto_pr),
            (GrokCommandFlag.LOCAL, arguments.local),
            (GrokCommandFlag.BRANCH, arguments.branch),
            (GrokCommandFlag.PR, arguments.pr),
        )
        words = [native_threads.GROK_SLASH_TEMPLATE.format(command=arguments.command.value)]
        for flag, value in parts:
            words.extend(GrokCommandRun._words(flag, value))
        return native_threads.NATIVE_COMMAND_PART_SEPARATOR.join(words)

    @staticmethod
    def _argv(launcher: tuple[str, ...], request: NativeThreadRequest, arguments: GrokCommandArguments, config: GrokThreadConfig, thread_id: str) -> tuple[str, ...]:
        # Every option is one --flag=value element, and the line
        # travels inside --single=, so it can never become a flag.
        options = [
            CliOption(GrokFlag.OUTPUT_FORMAT, native_threads.GROK_STREAMING_OUTPUT_FORMAT),
            CliOption(GrokFlag.SESSION_ID, thread_id),
            CliOption(GrokFlag.CWD, str(request.workspace)),
            CliOption(GrokFlag.PERMISSION_MODE, config.permission_mode.value),
        ]
        if request.model is not None:
            options.append(CliOption(GrokFlag.MODEL, request.model))
        if config.reasoning_effort is not None:
            options.append(CliOption(GrokFlag.REASONING_EFFORT, config.reasoning_effort.value))
        if arguments.agent is not None:
            options.append(CliOption(GrokFlag.AGENT, arguments.agent.value))
        options.append(CliOption(GrokFlag.SINGLE, request.prompt))
        return CliArgv.build(launcher, options=tuple(options), style=CliOptionStyle.JOINED)

    @staticmethod
    def _words(flag: GrokCommandFlag | None, value: object) -> tuple[str, ...]:
        # A part that is not set adds nothing, a switch adds its flag,
        # and a value adds its flag, when it has one, and the value.
        if value is None or value is False or value == "":
            return ()
        named = () if flag is None else (flag.value,)
        return named if value is True else (*named, str(value))


__all__ = ["GrokCommandRun", "GrokCommands"]
