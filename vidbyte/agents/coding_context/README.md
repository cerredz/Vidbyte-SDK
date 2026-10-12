# Coding context window

This package builds what a `CodingAgent` shows the model between its system prompt and the user's message. Each piece is a *section*: a short block of text the agent reads once, when it is built, such as the repository's `AGENTS.md`. One loader class per section produces the text, and `CodingContextWindow` puts the sections in a fixed order through the SDK's own `ContextManager`, so they render in the `## Context Window Primitives` zone right after the system prompt.

The model sees, in order:

1. the system prompt, the agentic-loop note, and the tool list (the runtime's fixed header), then the loop budgets when any are set;
2. `coding:agents_md`: the root folder's `AGENTS.md`, from `AgentsMdLoader` in `agents_md.py`;
3. `coding:environment`: facts about the machine (OS, CPU, date, root folder, project files, git branch, which bash runs commands, and the tools that bash finds), from `EnvironmentLoader` in `environment.py`;
4. `coding:repo_map`: reserved for the map.md section;
5. `coding:setup_results`: reserved for the setup-command results section;
6. `coding:progress_notes`: the agent's own notes file, `.vidbyte/coding-agent/progress.md`, from `ProgressNotesLoader` in `progress_notes.py`;
7. the caller's own context-manager primitives, in the caller's order and placements;
8. the context body, then the user's message.

## The contract

- **Order** comes from one enum, `CodingContextSection` in `vidbyte/lib/enums/coding.py`. Declaration order is render order, and each member's value is the section's primitive id. A new kind of section appends its own member where the model should see it, as `PROGRESS_NOTES` did.
- **A section** is a `CodingContextSectionText(section, title, content, source=None)` record from `vidbyte/lib/dataclasses/coding.py`. It checks itself: the section must be a `CodingContextSection`, the title and content must be non-blank text, and the source, when given, must be non-blank text.
- **A loader** is a class with one classmethod, `load(settings: CodingAgentSettings) -> CodingContextSectionText | None`. It reads whatever it needs from the validated settings record, including its own on/off switch, and returns `None` when it has nothing to add. It does its work once, at construction. A loader bounds its own text; the record does not cap it.
- **The window**, `CodingContextWindow.build(sections, context_manager)`, ignores `None` entries and fails with `ConfigurationError` on anything that is not a section record, on a section kind given twice, or on a `context_manager` that is not a `ContextManager`. With no sections it returns the caller's manager, the same object, or `None`, so the request is exactly a plain `BaseAgent`'s. Otherwise it returns a new manager: the sections first, at `TOP_OF_CONTEXT`, then the caller's primitives with their own placements, plus the caller's plain items and metadata. It never changes the caller's manager. A caller primitive whose id equals a placed section's id is not copied; the section wins.

## Adding a section

A new section takes three things, and no file in this package other than the new loader changes:

1. **One loader class in its own file**, `vidbyte/agents/coding_context/<section>.py`, with `load(settings) -> CodingContextSectionText | None`, following `agents_md.py`: an A001 header, a narrated `load`, and one level of helpers.
2. **The reserved enum member**: the loader returns its record with `section=CodingContextSection.ENVIRONMENT`, `REPO_MAP`, or `SETUP_RESULTS`. The enum does not change.
3. **One line in `CodingAgent.__init__`** (`vidbyte/agents/coding.py`): import the loader from its module and add `<Loader>.load(settings)` to the `sections` tuple. The tuple's order does not matter; the enum decides.

If the section has its own switch, that switch is part of the feature, not of this package: a keyword on `CodingAgent`, a `bool` field on `CodingAgentSettings`, and one `isinstance(..., bool)` check in `CodingAgentSettings._check_context_switches`.

## Notes for agents

- The package `__init__.py` exports nothing, on purpose; import `window` and each loader from its own module, so a new loader never edits `__init__.py`.
- Do not add a section to the system prompt string, and do not write to `ContextManager`'s private registry; `scripts/check_context_write_paths.py` fails CI on private access.
- When a section is loaded and the caller passed a `context_manager`, the agent renders a new manager. Tools bound to the caller's manager object, such as `ContextWindowFactory` tools, keep writing to the caller's object, which that agent no longer shows.
- `fork()` keeps every section, because it copies the agent's manager. `BaseAgent.restore()` does not bring sections back.
- `EnvironmentLoader` never shows environment-variable values, the user name, or the host name. Its one bash probe writes to a temporary file, not a pipe, so a timeout on Windows cannot hang construction. The probe is cached per bash path and `PATH`, so git facts are read from `.git` rather than the probe, which keeps the cache independent of the root folder.
- `ProgressNotesLoader` is the one loader that writes: it creates `.vidbyte/coding-agent/progress.md` from a template and `.vidbyte/coding-agent/.gitignore` holding `*`, each only when missing, and never overwrites either. It never touches `.vidbyte/` itself, because other tools write there. Any `OSError` there, such as a read-only root, means no section rather than a failed construction, because the switch is on by default.
