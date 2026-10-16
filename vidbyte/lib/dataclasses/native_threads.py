"""FILE: vidbyte/lib/dataclasses/native_threads.py

PURPOSE: Defines the validated records of the harness thread functions, thread helpers and command functions: NativeThreadRequest, the checked arguments of one run, continue, fork or command call; NativeHelperRequest, the checked arguments of one keyless thread helper call; GrokThreadConfig, OpencodeThreadConfig and MuseThreadConfig, the per-harness settings a caller may pass; NativeThreadResult, what a run or a read returns; NativeThreadSummary, one listed thread; NativeCommandOutput, the printed output of a command that makes no thread; NativeToolCall, one tool call of a run's record; GrokCommandArguments, the checked slash command or agent and options of one Grok command call; and GrokThreadFile, one Grok summary.json as the store holds it.
ROLE IN CODEBASE: NativeThreadRequest is built by the public run and command functions under vidbyte/harnesses/native/ (threads.py and commands.py of grok, opencode and muse) and NativeHelperRequest by the helpers (helpers.py of each); both are read by every step of their flows. The three config records, NativeThreadResult, NativeThreadSummary and NativeCommandOutput are re-exported from vidbyte.harnesses.native; callers build the configs, the functions return the others. NativeToolCall, GrokCommandArguments and GrokThreadFile are internal to the harness readers and flows.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid. Field checks go through RecordFieldValidator and RecordFieldConverter (vidbyte/lib/dataclasses/validation.py), every int and bool through require_int and require_bool (lint C002); the rules that relate a field to another value (thread_id against the verb, a skill folder's SKILL.md, unique skill folder names, which helper takes which argument, which Grok command takes which option) raise ConfigurationError inline. A refused field raises ConfigurationError whose details["field"] is the public argument name (api_key, skills[2], objective, limit); the functions turn it into a NativeThreadError naming that argument, and the readers turn a refused NativeThreadSummary field into protocol_mismatch naming the vendor member. The workspace and each skill path are checked as given, absolute and existing, and then stored resolved, so a relative path never passes because of the current folder. Which helper takes which argument is read from the operation tables of vidbyte/lib/constants/native_threads.py.
FUNCTION INVENTORY: NativeThreadRequest.__post_init__ is the narrated main function; _checked_workspace checks and resolves the workspace; _checked_model checks the model for the harness; _checked_thread_id ties the thread id to the verb; _checked_skills checks, resolves and names each skill folder; _checked_command checks the opencode command or Muse skill id. NativeHelperRequest.__post_init__ is narrated and calls _checked_thread_id, _checked_since, _checked_limit, _checked_query, _checked_scope and _checked_dry_run. GrokCommandArguments.__post_init__ is narrated and calls _checked_target, _checked_text, _checked_design_doc, _checked_counts, _checked_plan_flags, _checked_review_target, _checked_wrapper_text and _checked_skill_names. GrokThreadConfig, OpencodeThreadConfig, MuseThreadConfig, NativeThreadResult, NativeThreadSummary, NativeCommandOutput, NativeToolCall and GrokThreadFile have only __post_init__.
COMMON MODIFICATION PATTERNS: A new config field adds one field and one validator call to its record, and its bound or pattern to vidbyte/lib/constants/native_threads.py. A config record never gets a model field: the model is an argument of every call. A new helper joins the operation tables in constants; a new Grok command option adds one field and one rule to GrokCommandArguments.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys from environment variables. 2. Do not put a key value in an error message or its details; name the parameter instead. 3. Do not drop repr=False from a key field. 4. Do not import from vidbyte.harnesses; vidbyte/lib is the bottom layer. 5. Do not guard an int or bool field with an inline bool check; call require_int or require_bool.
KNOWN EDGE CASES: The prompt cap is NATIVE_PROMPT_MAX_CHARS for opencode, which reads the prompt from stdin, and NATIVE_ARGV_PROMPT_MAX_CHARS for Grok and Muse, which take it on argv; on Windows the Grok and Muse prompt must also fit NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS once quoted and counted in UTF-16 units, the way CreateProcess counts it; that ceiling leaves room for the rest of the command line, and a launch that still passes the limit is reported as launch_failed. An opencode request with a command may have an empty prompt, because the command then runs with no arguments and nothing goes on stdin. A skill item that is not a path is refused naming skills[<i>], while a skill list that is a str or holds too many items is refused naming skills. Two skill folders with the same folder name are refused, because each harness finds a skill by its folder name. since is refused as an int (hours or seconds would be a guess) and above NATIVE_SINCE_MAX (now - since would overflow). A NativeThreadSummary may not name itself as its parent. A design doc path is kept as given (not resolved), because it travels in the slash line the caller expects.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_records.py, tests/features/harness_threads/test_harness_threads_arguments.py, tests/features/harness_threads/test_harness_threads_helper_surface.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from vidbyte.lib.constants.native_threads import (
    GROK_BLANK_TEXT_COMMANDS,
    GROK_BRANCH_MAX_CHARS,
    GROK_BRANCH_PATTERN,
    GROK_COMMAND_MIN_VALUE,
    GROK_DESIGN_DOC_SPACE_RULE,
    GROK_EXECUTE_PLAN_MAX_CONCURRENCY,
    GROK_FLAG_JOIN,
    GROK_GOAL_MAX_BUDGET_TOKENS,
    GROK_GOAL_RESERVED_RULE,
    GROK_GOAL_RESERVED_WORDS,
    GROK_MAX_EFFORTS,
    GROK_PR_MAX_CHARS,
    GROK_PR_MAX_NUMBER,
    GROK_PR_PATTERN,
    GROK_REVIEW_MAX_TARGETS,
    GROK_TEXT_FLAG_RULE,
    GROK_TEXT_OPTION_FLAGS,
    MUSE_DEFAULT_PATH,
    MUSE_DISTRO_MAX_CHARS,
    MUSE_DISTRO_PATTERN,
    MUSE_PATH_MAX_CHARS,
    MUSE_PATH_PATTERN,
    NATIVE_API_KEY_MAX_CHARS,
    NATIVE_API_KEY_PATTERN,
    NATIVE_ARGV_PROMPT_MAX_CHARS,
    NATIVE_COMMAND_ARGUMENTS,
    NATIVE_COMMAND_MAX_CHARS,
    NATIVE_COMMAND_PATTERN,
    NATIVE_COMMAND_TEXT_MAX_CHARS,
    NATIVE_COMMAND_TEXT_PATTERN,
    NATIVE_HELPER_OPERATIONS,
    NATIVE_LIMIT_OPERATIONS,
    NATIVE_LIST_MAX_LIMIT,
    NATIVE_LIST_MIN_LIMIT,
    NATIVE_MODEL_MAX_CHARS,
    NATIVE_MODEL_PATTERN,
    NATIVE_NAME_MAX_CHARS,
    NATIVE_NAME_PATTERN,
    NATIVE_PROMPT_MAX_CHARS,
    NATIVE_PROMPT_PATTERN,
    NATIVE_QUERY_MAX_CHARS,
    NATIVE_QUERY_OPERATIONS,
    NATIVE_QUERY_PATTERN,
    NATIVE_SINCE_MAX,
    NATIVE_SINCE_MIN,
    NATIVE_SINCE_OPTIONAL_OPERATIONS,
    NATIVE_SINCE_REQUIRED_OPERATIONS,
    NATIVE_SKILL_FILE_NAME,
    NATIVE_SKILL_NAME_MAX_CHARS,
    NATIVE_SKILL_NAME_PATTERN,
    NATIVE_THREAD_DEFAULT_SECONDS,
    NATIVE_THREAD_ID_MAX_CHARS,
    NATIVE_THREAD_ID_OPERATIONS,
    NATIVE_THREAD_ID_PATTERN,
    NATIVE_THREAD_MAX_SECONDS,
    NATIVE_THREAD_MAX_SKILLS,
    NATIVE_TITLE_MAX_CHARS,
    NATIVE_TITLE_PATTERN,
    NATIVE_TOOL_NAME_MAX_CHARS,
    NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS,
    NATIVE_WINDOWS_PLATFORM,
    OPENCODE_MODEL_PATTERN,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import (
    GrokAgent,
    GrokCommand,
    GrokPermissionMode,
    GrokReasoningEffort,
    GrokThreadScope,
    MuseReasoningEffort,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class NativeThreadRequest:
    """The checked arguments of one thread function call; the key never shows in repr.

    workspace is typed Path | str and skills Sequence[str | Path]
    because the record must see the raw values: a relative path
    must be refused before it is resolved, and a bare string is a
    sequence of characters, not a list of skills. After
    __post_init__ workspace is always the resolved Path and skills
    a tuple of resolved Paths.
    """

    harness: NativeHarness
    verb: NativeThreadVerb
    prompt: str
    api_key: str = field(repr=False)
    workspace: Path | str
    model: str | None = None
    skills: Sequence[str | Path] = ()
    thread_id: str | None = None
    command: str | None = None

    def __post_init__(self) -> None:
        # Pin the harness and the verb first, because the prompt cap,
        # the model rule and the thread id rule depend on them.
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))
        object.__setattr__(self, "verb", RecordFieldConverter.to_enum(self.verb, NativeThreadVerb, "verb"))

        # Grok and Muse take the prompt on argv, so they get the
        # smaller cap; opencode reads it from stdin, and an opencode
        # command may run with no arguments, so its prompt may be "".
        prompt_cap = NATIVE_PROMPT_MAX_CHARS if self.harness is NativeHarness.OPENCODE else NATIVE_ARGV_PROMPT_MAX_CHARS
        empty_allowed = self.harness is NativeHarness.OPENCODE and self.command is not None
        prompt_pattern = NATIVE_COMMAND_TEXT_PATTERN if empty_allowed else NATIVE_PROMPT_PATTERN
        RecordFieldValidator.require_text(self.prompt, "prompt", max_chars=prompt_cap, pattern=prompt_pattern, allow_blank=empty_allowed)

        # @intent argv-prompt-fits-the-windows-command-line
        # On Windows a prompt of quotes or emoji within the cap can
        # double once quoted and counted in UTF-16 units, pass the
        # CreateProcess limit and fail as if the CLI were missing, so
        # the quoted argv prompt must fit its own unit ceiling. The
        # ceiling sits above the character cap, so every prose prompt
        # the cap allows still runs (spec §9.1, EC-3).
        if self.harness is not NativeHarness.OPENCODE and sys.platform == NATIVE_WINDOWS_PLATFORM:
            RecordFieldValidator.require_command_line_units(self.prompt, "prompt", max_units=NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS)

        # The key is checked under its public name, which the validator
        # never quotes, and the pattern keeps it printable ASCII.
        RecordFieldValidator.require_text(self.api_key, "api_key", max_chars=NATIVE_API_KEY_MAX_CHARS, pattern=NATIVE_API_KEY_PATTERN)

        # Check the paths as given, then store them resolved.
        object.__setattr__(self, "workspace", self._checked_workspace())
        self._checked_model()
        object.__setattr__(self, "skills", self._checked_skills())

        # A run starts a new thread; continue and fork need the one to
        # use.
        self._checked_thread_id()

        # An opencode command or a Muse skill id runs on a new thread
        # only, under the name the caller passed it as.
        self._checked_command()

    def _checked_workspace(self) -> Path:
        # The workspace must be an absolute existing folder as given.
        workspace = RecordFieldConverter.to_path(self.workspace, "workspace")
        RecordFieldValidator.require_directory(workspace, "workspace")
        return workspace.resolve()

    def _checked_model(self) -> None:
        # opencode needs "<provider>/<model>"; Grok and Muse take an
        # optional bare model id.
        if self.harness is NativeHarness.OPENCODE:
            RecordFieldValidator.require_text(self.model, "model", max_chars=NATIVE_MODEL_MAX_CHARS, pattern=OPENCODE_MODEL_PATTERN)
        else:
            RecordFieldValidator.require_optional_text(self.model, "model", max_chars=NATIVE_MODEL_MAX_CHARS, pattern=NATIVE_MODEL_PATTERN)

    def _checked_thread_id(self) -> None:
        # thread_id is None exactly when the verb is run.
        if self.verb is NativeThreadVerb.RUN and self.thread_id is not None:
            raise ConfigurationError(f"thread_id must be None when the verb is {self.verb.value}.", details={"field": "thread_id"})
        if self.verb is not NativeThreadVerb.RUN:
            RecordFieldValidator.require_text(self.thread_id, "thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)

    def _checked_skills(self) -> tuple[Path, ...]:
        # Each skill is an absolute existing folder as given, holding a
        # SKILL.md file, with a unique lowercase-hyphenated folder name.
        items = RecordFieldConverter.to_tuple(self.skills, "skills", item_type=object, max_items=NATIVE_THREAD_MAX_SKILLS)
        folders: list[Path] = []
        for index, item in enumerate(items):
            name = f"skills[{index}]"
            given = RecordFieldConverter.to_path(item, name)
            RecordFieldValidator.require_directory(given, name)
            folder = given.resolve()
            if not (folder / NATIVE_SKILL_FILE_NAME).is_file():
                raise ConfigurationError(f"{name} must be a folder holding a {NATIVE_SKILL_FILE_NAME} file.", details={"field": name})
            RecordFieldValidator.require_text(folder.name, name, max_chars=NATIVE_SKILL_NAME_MAX_CHARS, pattern=NATIVE_SKILL_NAME_PATTERN)
            if any(earlier.name == folder.name for earlier in folders):
                raise ConfigurationError(f"{name} has the same folder name as an earlier skill; skill folder names must be unique.", details={"field": name})
            folders.append(folder)
        return tuple(folders)

    def _checked_command(self) -> None:
        # @intent native-command-names-never-become-flags
        # A Grok command travels inside the prompt line, so a Grok
        # request names none. An opencode command or a Muse skill id
        # must match NATIVE_COMMAND_PATTERN, whose first character is
        # alphanumeric, so it can never be read as a flag (spec INV-9).
        if self.command is None:
            return
        if self.harness is NativeHarness.GROK:
            raise ConfigurationError("command must be None for Grok, whose commands travel in the prompt line.", details={"field": "command"})
        name = NATIVE_COMMAND_ARGUMENTS[self.harness]
        if self.verb is not NativeThreadVerb.RUN:
            raise ConfigurationError(f"{name} may be set only when the verb is {NativeThreadVerb.RUN.value}.", details={"field": name})
        RecordFieldValidator.require_text(self.command, name, max_chars=NATIVE_COMMAND_MAX_CHARS, pattern=NATIVE_COMMAND_PATTERN)


@dataclass(frozen=True, slots=True)
class NativeHelperRequest:
    """The checked arguments of one thread helper call: the helper, the workspace (given as Path | str, stored resolved), and the thread id, window, limit, query, Grok scope or dry-run flag that helper takes."""

    harness: NativeHarness
    operation: NativeThreadOperation
    workspace: Path | str
    thread_id: str | None = None
    since: timedelta | None = None
    limit: int | None = None
    query: str | None = None
    scope: GrokThreadScope | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        # Pin the harness and the helper first: which arguments a call
        # takes is read from the tables keyed by the helper.
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))
        object.__setattr__(self, "operation", RecordFieldConverter.to_enum(self.operation, NativeThreadOperation, "operation"))
        if self.operation not in NATIVE_HELPER_OPERATIONS[self.harness]:
            raise ConfigurationError(f"operation must be a thread helper of {self.harness.value}; got {self.operation.value}.", details={"field": "operation"})

        # The workspace follows the rule of the thread functions: an
        # absolute existing folder as given, then stored resolved.
        workspace = RecordFieldConverter.to_path(self.workspace, "workspace")
        RecordFieldValidator.require_directory(workspace, "workspace")
        object.__setattr__(self, "workspace", workspace.resolve())

        # Each remaining argument is required by the helpers that take
        # it and must be absent from the others.
        self._checked_thread_id()
        self._checked_since()
        self._checked_limit()
        self._checked_query()
        self._checked_scope()
        self._checked_dry_run()

    def _checked_thread_id(self) -> None:
        # The one-thread helpers need an id that can never be a path, a
        # flag or SQL (spec INV-9).
        if self.operation in NATIVE_THREAD_ID_OPERATIONS:
            RecordFieldValidator.require_text(self.thread_id, "thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)
        elif self.thread_id is not None:
            raise ConfigurationError(f"thread_id must be None for {self.operation.value}.", details={"field": "thread_id"})

    def _checked_since(self) -> None:
        # @intent helper-since-is-a-bounded-timedelta
        # A window is a timedelta above 0 and at most NATIVE_SINCE_MAX:
        # an int would leave hours or seconds to a guess, 0 would list
        # nothing, and a larger value would overflow now - since.
        if self.operation not in NATIVE_SINCE_REQUIRED_OPERATIONS | NATIVE_SINCE_OPTIONAL_OPERATIONS:
            if self.since is not None:
                raise ConfigurationError(f"since must be None for {self.operation.value}.", details={"field": "since"})
            return
        if self.since is None and self.operation in NATIVE_SINCE_OPTIONAL_OPERATIONS:
            return
        if not isinstance(self.since, timedelta) or not NATIVE_SINCE_MIN < self.since <= NATIVE_SINCE_MAX:
            raise ConfigurationError(f"since must be a datetime.timedelta greater than 0 and at most {NATIVE_SINCE_MAX}; got a value of type {type(self.since).__name__} that is not one.", details={"field": "since"})

    def _checked_limit(self) -> None:
        # Lists and searches return at most NATIVE_LIST_MAX_LIMIT
        # threads; require_int refuses True standing in for 1.
        if self.operation in NATIVE_LIMIT_OPERATIONS:
            RecordFieldValidator.require_int(self.limit, "limit", minimum=NATIVE_LIST_MIN_LIMIT, maximum=NATIVE_LIST_MAX_LIMIT)
        elif self.limit is not None:
            raise ConfigurationError(f"limit must be None for {self.operation.value}.", details={"field": "limit"})

    def _checked_query(self) -> None:
        # A search query is non-blank text without NUL; it is matched in
        # the SDK and never reaches argv.
        if self.operation in NATIVE_QUERY_OPERATIONS:
            RecordFieldValidator.require_text(self.query, "query", max_chars=NATIVE_QUERY_MAX_CHARS, pattern=NATIVE_QUERY_PATTERN)
        elif self.query is not None:
            raise ConfigurationError(f"query must be None for {self.operation.value}.", details={"field": "query"})

    def _checked_scope(self) -> None:
        if self.harness is NativeHarness.GROK:
            object.__setattr__(self, "scope", RecordFieldConverter.to_enum(self.scope, GrokThreadScope, "scope"))
        elif self.scope is not None:
            raise ConfigurationError(f"scope must be None for {self.operation.value}.", details={"field": "scope"})

    def _checked_dry_run(self) -> None:
        RecordFieldValidator.require_bool(self.dry_run, "dry_run")
        if self.dry_run and self.operation is not NativeThreadOperation.INIT_MUSE_WORKSPACE:
            raise ConfigurationError(f"dry_run must be False for {self.operation.value}.", details={"field": "dry_run"})


@dataclass(frozen=True, slots=True)
class GrokCommandArguments:
    """The checked slash command or agent of one Grok command call, its text and line options; text_field names the text in refusals, named marks a named wrapper, skill_names are the request's skill folder names."""

    command: GrokCommand | None = None
    agent: GrokAgent | None = None
    text: str = ""
    design_doc: Path | str | None = None
    budget_tokens: int | None = None
    effort: int | None = None
    concurrency: int | None = None
    dry_run: bool = False
    auto_pr: bool = False
    local: bool = False
    branch: str | None = None
    pr: int | str | None = None
    named: bool = False
    text_field: str = "arguments"
    skill_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Exactly one slash command or agent runs; then the design doc
        # and the text it may stand in for.
        self._checked_target()
        RecordFieldValidator.require_text(self.text_field, "GrokCommandArguments.text_field", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldValidator.require_bool(self.named, "GrokCommandArguments.named")
        object.__setattr__(self, "design_doc", self._checked_design_doc())
        self._checked_text()

        # Each option belongs to one command and stays in its range.
        self._checked_counts()
        self._checked_plan_flags()
        self._checked_review_target()

        # Text a named wrapper got cannot turn into the command's own
        # option, and no skill folder of the caller's may replace the
        # bundled command.
        self._checked_wrapper_text()
        self._checked_skill_names()

    def _checked_target(self) -> None:
        if self.command is not None:
            object.__setattr__(self, "command", RecordFieldConverter.to_enum(self.command, GrokCommand, "command"))
        if self.agent is not None:
            object.__setattr__(self, "agent", RecordFieldConverter.to_enum(self.agent, GrokAgent, "agent"))
        if (self.command is None) == (self.agent is None):
            raise ConfigurationError("command must name one Grok command, or agent one Grok agent, but not both.", details={"field": "command"})

    def _checked_text(self) -> None:
        # The text may be empty only for /review and /code-review, which
        # take none, and when a design doc is the argument; an agent
        # always needs its task.
        blank = self.command in GROK_BLANK_TEXT_COMMANDS or self.design_doc is not None
        RecordFieldValidator.require_text(self.text, self.text_field, max_chars=NATIVE_COMMAND_TEXT_MAX_CHARS, pattern=NATIVE_COMMAND_TEXT_PATTERN, allow_blank=blank)

    def _checked_design_doc(self) -> Path | None:
        # @intent grok-design-doc-is-one-token
        # /execute-plan splits its arguments at whitespace, so the doc
        # is an absolute existing file whose path holds none; otherwise
        # "x --auto-pr.md" would push branches without the opt-in.
        if self.design_doc is None:
            return None
        if self.command is not GrokCommand.EXECUTE_PLAN:
            raise ConfigurationError("design_doc is taken only by /execute-plan.", details={"field": "design_doc"})
        path = RecordFieldConverter.to_path(self.design_doc, "design_doc")
        if not path.is_absolute() or not path.is_file():
            raise ConfigurationError("design_doc must be an absolute path to an existing file; got a path that is not one.", details={"field": "design_doc"})
        if any(character.isspace() for character in str(path)):
            raise ConfigurationError(GROK_DESIGN_DOC_SPACE_RULE, details={"field": "design_doc"})
        return path

    def _checked_counts(self) -> None:
        # budget_tokens belongs to /goal, effort to /implement and
        # /execute-plan, concurrency to /execute-plan; each is an int
        # in its command's range, never a bool.
        if self.budget_tokens is not None:
            if self.command is not GrokCommand.GOAL:
                raise ConfigurationError("budget_tokens is taken only by /goal.", details={"field": "budget_tokens"})
            RecordFieldValidator.require_int(self.budget_tokens, "budget_tokens", minimum=GROK_COMMAND_MIN_VALUE, maximum=GROK_GOAL_MAX_BUDGET_TOKENS)
        if self.effort is not None:
            if self.command not in GROK_MAX_EFFORTS:
                raise ConfigurationError("effort is taken only by /implement and /execute-plan.", details={"field": "effort"})
            RecordFieldValidator.require_int(self.effort, "effort", minimum=GROK_COMMAND_MIN_VALUE, maximum=GROK_MAX_EFFORTS[self.command])
        if self.concurrency is not None:
            if self.command is not GrokCommand.EXECUTE_PLAN:
                raise ConfigurationError("concurrency is taken only by /execute-plan.", details={"field": "concurrency"})
            RecordFieldValidator.require_int(self.concurrency, "concurrency", minimum=GROK_COMMAND_MIN_VALUE, maximum=GROK_EXECUTE_PLAN_MAX_CONCURRENCY)

    def _checked_plan_flags(self) -> None:
        # dry_run and auto_pr are /execute-plan switches; auto_pr pushes
        # branches and opens pull requests, so it is never implied.
        RecordFieldValidator.require_bool(self.dry_run, "dry_run")
        RecordFieldValidator.require_bool(self.auto_pr, "auto_pr")
        if (self.dry_run or self.auto_pr) and self.command is not GrokCommand.EXECUTE_PLAN:
            raise ConfigurationError("dry_run and auto_pr are taken only by /execute-plan.", details={"field": "dry_run" if self.dry_run else "auto_pr"})

    def _checked_review_target(self) -> None:
        # /review reviews the local changes, one branch or one pull
        # request: at most one of them, each in its own form.
        RecordFieldValidator.require_bool(self.local, "local")
        if self.branch is not None:
            RecordFieldValidator.require_text(self.branch, "branch", max_chars=GROK_BRANCH_MAX_CHARS, pattern=GROK_BRANCH_PATTERN)
        if isinstance(self.pr, str):
            RecordFieldValidator.require_text(self.pr, "pr", max_chars=GROK_PR_MAX_CHARS, pattern=GROK_PR_PATTERN)
        elif self.pr is not None:
            RecordFieldValidator.require_int(self.pr, "pr", minimum=GROK_COMMAND_MIN_VALUE, maximum=GROK_PR_MAX_NUMBER)
        chosen = [name for name, given in (("local", self.local), ("branch", self.branch is not None), ("pr", self.pr is not None)) if given]
        if chosen and self.command is not GrokCommand.REVIEW:
            raise ConfigurationError(f"{chosen[0]} is taken only by /review.", details={"field": chosen[0]})
        if len(chosen) > GROK_REVIEW_MAX_TARGETS:
            raise ConfigurationError(f"pass at most one of local, branch and pr; got {', '.join(chosen)}.", details={"field": chosen[-1]})

    def _checked_wrapper_text(self) -> None:
        # @intent grok-wrapper-text-cannot-become-an-option
        # Grok reads the slash line word by word, so a named wrapper's
        # text may not hold the command's own flag, alone or joined to
        # a value, and an objective may not be a /goal subcommand. Raw
        # run_grok_command arguments are the caller's own line.
        if not self.named or self.command is None:
            return
        words = self.text.split()
        for flag in GROK_TEXT_OPTION_FLAGS.get(self.command, ()):
            if any(word == flag.value or word.startswith(flag.value + GROK_FLAG_JOIN) for word in words):
                raise ConfigurationError(GROK_TEXT_FLAG_RULE.format(field=self.text_field, flag=flag.value), details={"field": self.text_field})
        word = self.text.strip().casefold()
        if self.command is GrokCommand.GOAL and word in GROK_GOAL_RESERVED_WORDS:
            raise ConfigurationError(GROK_GOAL_RESERVED_RULE.format(field=self.text_field, word=word), details={"field": self.text_field})

    def _checked_skill_names(self) -> None:
        # A skills folder named like the command would replace Grok's
        # bundled skill, and the paid run would then not run it.
        names = RecordFieldConverter.to_tuple(self.skill_names, "skills", item_type=str)
        object.__setattr__(self, "skill_names", names)
        if self.command is not None and self.command.value in names:
            raise ConfigurationError(f"skills may not hold a folder named {self.command.value}, which would replace Grok's bundled /{self.command.value}.", details={"field": "skills"})


@dataclass(frozen=True, slots=True)
class GrokThreadConfig:
    """Settings of the Grok thread functions: reasoning effort, permission mode, time limit and an explicit grok launcher."""

    reasoning_effort: GrokReasoningEffort | None = None
    permission_mode: GrokPermissionMode = GrokPermissionMode.DEFAULT
    timeout_seconds: float = NATIVE_THREAD_DEFAULT_SECONDS
    grok_command: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.reasoning_effort is not None:
            object.__setattr__(self, "reasoning_effort", RecordFieldConverter.to_enum(self.reasoning_effort, GrokReasoningEffort, "GrokThreadConfig.reasoning_effort"))
        object.__setattr__(self, "permission_mode", RecordFieldConverter.to_enum(self.permission_mode, GrokPermissionMode, "GrokThreadConfig.permission_mode"))
        RecordFieldValidator.require_number(self.timeout_seconds, "GrokThreadConfig.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        if self.grok_command is not None:
            RecordFieldValidator.require_argv(self.grok_command, "GrokThreadConfig.grok_command")


@dataclass(frozen=True, slots=True)
class OpencodeThreadConfig:
    """Settings of the opencode thread functions: agent, model variant, time limit and an explicit opencode launcher."""

    agent: str | None = None
    variant: str | None = None
    timeout_seconds: float = NATIVE_THREAD_DEFAULT_SECONDS
    opencode_command: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_optional_text(self.agent, "OpencodeThreadConfig.agent", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldValidator.require_optional_text(self.variant, "OpencodeThreadConfig.variant", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldValidator.require_number(self.timeout_seconds, "OpencodeThreadConfig.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        if self.opencode_command is not None:
            RecordFieldValidator.require_argv(self.opencode_command, "OpencodeThreadConfig.opencode_command")


@dataclass(frozen=True, slots=True)
class MuseThreadConfig:
    """Settings of the Muse thread functions: reasoning effort, time limit, an explicit muse launcher, or the WSL distro and the muse path inside it."""

    reasoning_effort: MuseReasoningEffort | None = None
    timeout_seconds: float = NATIVE_THREAD_DEFAULT_SECONDS
    muse_command: tuple[str, ...] | None = None
    wsl_distro: str | None = None
    muse_path: str = MUSE_DEFAULT_PATH

    def __post_init__(self) -> None:
        if self.reasoning_effort is not None:
            object.__setattr__(self, "reasoning_effort", RecordFieldConverter.to_enum(self.reasoning_effort, MuseReasoningEffort, "MuseThreadConfig.reasoning_effort"))
        RecordFieldValidator.require_number(self.timeout_seconds, "MuseThreadConfig.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        if self.muse_command is not None:
            RecordFieldValidator.require_argv(self.muse_command, "MuseThreadConfig.muse_command")
        RecordFieldValidator.require_optional_text(self.wsl_distro, "MuseThreadConfig.wsl_distro", max_chars=MUSE_DISTRO_MAX_CHARS, pattern=MUSE_DISTRO_PATTERN)
        RecordFieldValidator.require_text(self.muse_path, "MuseThreadConfig.muse_path", max_chars=MUSE_PATH_MAX_CHARS, pattern=MUSE_PATH_PATTERN)


@dataclass(frozen=True, slots=True)
class NativeThreadResult:
    """What a successful thread function call returns: the harness, the thread id to continue or fork, the final answer text, and whether that text was cut at the cap."""

    harness: NativeHarness
    thread_id: str
    text: str
    text_truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "NativeThreadResult.harness"))
        RecordFieldValidator.require_text(self.thread_id, "NativeThreadResult.thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)
        RecordFieldConverter.require_instance(self.text, "NativeThreadResult.text", str)
        RecordFieldValidator.require_bool(self.text_truncated, "NativeThreadResult.text_truncated")


@dataclass(frozen=True, slots=True)
class NativeThreadSummary:
    """One thread as the helpers list it: the harness, the thread id, the title, when it was created and last updated (in UTC), the thread it came from, and the model."""

    harness: NativeHarness
    thread_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    parent_thread_id: str | None
    model: str | None

    def __post_init__(self) -> None:
        # Each field is refused under its own name, which the readers
        # turn into protocol_mismatch naming the vendor member (spec
        # INV-6); the times are stored in UTC so they sort across
        # offsets.
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))
        RecordFieldValidator.require_text(self.thread_id, "thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)
        RecordFieldValidator.require_optional_text(self.title, "title", max_chars=NATIVE_TITLE_MAX_CHARS, pattern=NATIVE_TITLE_PATTERN)
        object.__setattr__(self, "created_at", RecordFieldConverter.to_utc_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", RecordFieldConverter.to_utc_datetime(self.updated_at, "updated_at"))
        RecordFieldValidator.require_optional_text(self.parent_thread_id, "parent_thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)
        if self.parent_thread_id == self.thread_id:
            raise ConfigurationError("parent_thread_id must name another thread than thread_id.", details={"field": "parent_thread_id"})
        RecordFieldValidator.require_optional_text(self.model, "model", max_chars=NATIVE_MODEL_MAX_CHARS, pattern=NATIVE_MODEL_PATTERN)


@dataclass(frozen=True, slots=True)
class NativeCommandOutput:
    """What a command that makes no thread printed: the harness and its standard output."""

    harness: NativeHarness
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))
        RecordFieldConverter.require_instance(self.text, "text", str)


@dataclass(frozen=True, slots=True)
class NativeToolCall:
    """One tool call in a run's own record: the tool name and its arguments as text."""

    name: str
    arguments: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.name, "NativeToolCall.name", max_chars=NATIVE_TOOL_NAME_MAX_CHARS)
        RecordFieldConverter.require_instance(self.arguments, "NativeToolCall.arguments", str)


@dataclass(frozen=True, slots=True)
class GrokThreadFile:
    """One Grok session's summary.json as the store holds it: its summary, the title and two summaries a search reads, the agent that ran it, and the file's path."""

    summary: NativeThreadSummary
    search_text: tuple[str | None, ...]
    agent_name: str | None
    path: Path

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.summary, "GrokThreadFile.summary", NativeThreadSummary)
        object.__setattr__(self, "search_text", RecordFieldConverter.to_tuple(self.search_text, "search_text", item_type=(str, type(None))))
        RecordFieldConverter.require_instance(self.agent_name, "agent_name", str, optional=True)
        RecordFieldConverter.require_instance(self.path, "GrokThreadFile.path", Path)


__all__ = [
    "GrokCommandArguments",
    "GrokThreadConfig",
    "GrokThreadFile",
    "MuseThreadConfig",
    "NativeCommandOutput",
    "NativeHelperRequest",
    "NativeThreadRequest",
    "NativeThreadResult",
    "NativeThreadSummary",
    "NativeToolCall",
    "OpencodeThreadConfig",
]
