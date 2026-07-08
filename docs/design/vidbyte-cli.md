# Design Doc: Minimal `vidbyte-sdk` CLI (skills subcommand)

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Add a unified `vidbyte-sdk` console command to the SDK, implemented as a small stdlib-argparse package at `vidbyte/cli/`, wired through a single `[project.scripts]` entry point in `pyproject.toml`. Its first and only subcommand group is `skills` (`vidbyte-sdk skills list|show|install`), a thin wrapper over the `Skills` registry designed in `docs/pre-design/paradigm-skills-and-registry.md`. The CLI is deliberately minimal (~100G혀150 lines, zero new dependencies) but structured with a subcommand-registration seam so future groups G현 e.g. commands that talk to the main Vidbyte backend G현 slot in without restructuring.

**Dependency note for the implementer:** this design depends on the skills registry design doc. Read `docs/pre-design/paradigm-skills-and-registry.md` (it is promoted to `docs/design/` once implemented) and look for these files in the repo: `vidbyte/skills/catalog.py` (`Skills`, `SkillRecord`), `vidbyte/lib/enums/skills.py` (`Skill` enum), and `vidbyte/paradigms/context_minimal_fanout/skills/` (assets + `skills.json`). If they do not exist yet, implement that doc first G현 this CLI has nothing to wrap without it.

---

## 2. Original User Prompts

Prompts 1G혀3 established the paradigm skills + registry feature and are recorded verbatim in `docs/pre-design/paradigm-skills-and-registry.md` -�2. Copied here again for self-containment:

**Prompt 1** (via `/talk`):

> - also, a few things to note with the "thin-harness paradigms" in our vidbyte-sdk/ repo. i wanted skill files inside of the folder of these paradigms (our first paradigm being the context window minimal paradigm), basically I want a skills/ folder inside of the actual paradigm folder, and subfolder for each "implementation" of that paradigm.
>   - I will give you an example of the skills that I want to add in our first paradigm folder.
>   - (these skill should have a goal, description, use cases, and step by step/instructions/agorithm sections to them (see the vidbyte prompts master prompt/action oriented templates to understand this))
>     - "decompose and then implement" -> tells model gather context, then decompose the original prompt/task into subtasks, save these subtasks somewhere, and then sequentially solve each of these subtasks
>     - "decompose, create design docs, and then implement" -> tells model gather context, then decompose the original prompt/task into subtasks, create design docs that 'solve' the subtasks, and then sequentially implement each of the design docs (basically answering the question in the early part of the context window)
>     - "decompose, create design docs, create subagents for each design doc, and then implement" -> tells model gather context, then decompose the original prompt/task into subtasks, create design docs that 'solve' the subtasks, create subagents in the current thread for each design doc (need to include exact terminal commands of all popular coding harness platforms (and how to lookup/find other platform commands)) on how to do this, and then return after all subagents are done
>     - "decompose, create subagents" -> decompose the original prompt into subtasks, then just pass the subtasks to each of the subagents
>     -
> ,   - by extension of this, I want to add functionality to our vidbyte-sdk/ repo where users can easily access and install these skills. what is the best way to do this (creating like a skills registry in the code and letting devs access through code, hooking up the actual skills in the repo to npm/pip install commands, publishing somewhere when we make a file, just keep skill files in the repo and let devs access them directly, etc), what is best way to like "publish these skills" (note, whatever is best way I still think adding a central registry is the best way to make this easy for devs, maybe hooking up our "thin harness paradigm" skills to the prompt registry of the repo?) what do you think about all of this
>  can you help me answer these questions

**Prompt 2** (via `/create-design`):

> great, so I want you to create a design doc of the following (inside of a singular design doc): 1) the skill files/folder to add to our first thin harness and 2) the skills register for a developer to view/see/use all of the thin harness skills in thier own code. Then, after you create the design doc I have a question about distribution. Is there a way for this pip package we can create like a pip install vidbyte-sdk-skills command, or like how would we do something like this, would have have to create an entire cli to add these commands?

**Prompt 3:** User renamed the session to "vidbyte-sdk-skills" and said: "continue"

**Prompt 4** (this design's driving prompt):

> I think that the cleanest way we can do it is this:   2. One line in pyproject G현 a real command. Add vidbyte-skills =
>   "vidbyte.skills.__main__:main" (or better, a unified vidbyte =
>   "vidbyte.cli:main" with skills as a subcommand, since you'll
>   likely want more subcommands later). The "CLI" is ~100 lines of
>   stdlib argparse with subparsers wrapping Skills().keys() and
>   Skills().materialize(). No click/typer dependency needed.. I think that just creating a very small CLI would be good for our sdk, and Besides we might end up hooking up our SDK to our main vidbyte backend so I think that a CLI isn't actually too bad and we can start it off with. I think that right now it's fine to just build a very minimalistic CLI for this one command. Can you kind of just create a design doc to sketch this out? (we dont actually have the code yet, go off of the original design doc, say something like "here was the design doc for the skill registry code, look for these files in the repo, then here is the design doc you have to create". Also, either place the cli at vidbyte-sdk/cli or vidbyte-sdk/vidbyte/cli, whichever one is a software engineering best practice

---

## 3. Structured Conversation Notes

### Key Decisions

1. **unified `vidbyte-sdk` command, not `vidbyte-skills`.** The user chose the unified entry point (`vidbyte-sdk = "vidbyte.cli:main"`) with `skills` as the first subcommand group, explicitly because the SDK may later hook up to the main Vidbyte backend and more subcommands are expected. One brand command that grows beats a constellation of `vidbyte-*` binaries.
2. **CLI lives at `vidbyte/cli/` (inside the package), not repo-top-level `cli/`.** This is the software-engineering-best-practice answer the user asked for, for three hard reasons: (a) `[project.scripts]` entry points must reference an *importable module path* G현 `vidbyte.cli:main` only resolves if the code is inside the `vidbyte` package; (b) `pyproject.toml` packaging uses `[tool.setuptools.packages.find] include = ["vidbyte*"]`, so a top-level `cli/` directory would silently not ship in the wheel; (c) even if force-included, installing a top-level package literally named `cli` into site-packages would squat a generic name and collide with other distributions G현 a known packaging anti-pattern. Precedent in-repo: the existing console script `vidbyte-mcp-server = "vidbyte.mcp_server.__main__:main"` already follows the inside-the-package pattern.
3. **stdlib argparse only.** No click/typer/rich. The SDK's dependency surface is deliberately tiny (`pydantic`, `httpx`); a ~100-line CLI does not justify a framework. User approved this explicitly.
4. **Minimal command surface for v1**: `vidbyte-sdk skills list`, `vidbyte-sdk skills show <key>`, `vidbyte-sdk skills install <key> --dest <dir>`. The user said "very minimalistic CLI for this one command" G현 the load-bearing command is `install`; `list` is required for discoverability; `show` is cheap and lets users read a skill before installing. Nothing else.
5. **Subcommand-registration seam for growth.** Each subcommand group is its own module (`vidbyte/cli/skills.py`) exposing a `register(subparsers)` function; `vidbyte/cli/__init__.py`'s `main()` builds the root parser and calls each group's `register`. Adding a future `backend`/`auth`/`prompts` group = one new module + one register call. No plugin machinery, no dynamic discovery G현 an explicit list is fine at this scale.
6. **The CLI is a thin adapter over the registry G현 zero business logic.** All listing/reading/materializing behavior lives in `Skills` (per the registry design doc). The CLI translates argv G樣 catalog calls G樣 stdout/exit codes. If the CLI needs a capability the catalog lacks, the capability goes in the catalog.
7. **This doc supersedes the registry doc's stretch requirement 11** (`vidbyte/skills/__main__.py` with its own argparse). Instead, add `vidbyte/cli/__main__.py` (two lines) so `python -m vidbyte.cli` works for users who somehow lack PATH shims. Do not build a parallel argparse in `vidbyte.skills`.

### Rejected Alternatives

- **`vidbyte-skills` as a separate console script** G현 rejected by the user in favor of the unified command (Prompt 4 quotes both options and picks unified).
- **Repo-top-level `cli/` directory** G현 rejected; see Key Decision 2 (not importable as `vidbyte.cli`, not shipped by `packages.find`, generic-name squatting).
- **click / typer** G현 rejected; unnecessary dependency for this surface.
- **A separate `vidbyte-sdk-skills` PyPI package** G현 rejected earlier in the conversation: nothing to escape (SDK deps are only pydantic + httpx), and a second package means version-sync drift. `pip install <name>` only installs files; the command comes from the entry point either way.
- **`python -m vidbyte.skills` as the primary interface** (option 1 from the conversation) G현 superseded by the real entry point; keeping both argparse surfaces would duplicate code.
- **Harness-aware install (`--harness claude --scope user` auto-resolving paths like `~/.claude/skills/`)** G현 deferred to keep v1 minimal; `--dest` is explicit and universal. Recorded as future work (see Open Questions), since the harness path table already exists conceptually in the prompts README / PR #154 work.

### Constraints & Assumptions

- **Assumes the skills registry exists** per `docs/pre-design/paradigm-skills-and-registry.md`: `Skills` with `keys()`, `descriptions()`, `get()`, `text()`, `files()`, `materialize(key, dest_dir)`; `Skill` str-Enum; `ConfigurationError` on invalid assets. If the implemented API drifted from that doc, wrap what actually exists G현 do not re-implement.
- Python >= 3.11, stdlib only for the CLI; no new `[project.dependencies]`.
- House style applies: Context Protocol Header comment at the top of each new module (copy the format from `vidbyte/prompts/__init__.py` or `vidbyte/mcp_server/__main__.py`), folder README following the repo's Role-In-The-SDK/Usage/Key-Modules format.
- Windows is the primary dev environment: use `pathlib`, never assume POSIX paths; output must not rely on ANSI color.
- The existing `vidbyte-mcp-server` script must keep working unchanged.

### Clarifications & Answers

- Q (user): `vidbyte-sdk/cli` or `vidbyte-sdk/vidbyte/cli` G현 which is best practice? A: `vidbyte-sdk/vidbyte/cli` (inside the package), for the three reasons in Key Decision 2. This doc treats that as settled.
- Q (user, from Prompt 2): do we need "an entire CLI"? A: no framework needed G현 one entry-point line in pyproject plus an argparse `main()`. This doc is that answer made concrete.
- Assumption made without asking: `show` prints the SKILL.md body to stdout; `list` prints one `key G현 description` line per skill. If the user wants different output shapes, it's a trivial change at implementation review time.

### Terminology / Glossary

- **Entry point / console script**: the `[project.scripts]` table in `pyproject.toml`; pip generates a PATH executable per entry that imports and calls the referenced function.
- **Subcommand group**: first positional token after `vidbyte` (e.g. `skills`), owning its own argparse subparser and actions.
- **Materialize / install**: `Skills.materialize(key, dest_dir)` G현 write the skill folder (SKILL.md + any shared references) under `dest_dir`. The CLI verb is `install`; the catalog verb is `materialize`.
- **Registry / catalog**: `vidbyte.skills.Skills`, the enum-keyed loader from the companion design doc.

### Implementation Hints for the Downstream Model

- **Read first**: `docs/pre-design/paradigm-skills-and-registry.md` (or its promoted copy in `docs/design/`), then the actual implemented files: `vidbyte/skills/catalog.py`, `vidbyte/lib/enums/skills.py`, `tests/test_skills_interface.py`. The CLI must call what exists, not what this doc guesses.
- **Entry-point precedent**: `pyproject.toml` `[project.scripts]` already has `vidbyte-mcp-server = "vidbyte.mcp_server.__main__:main"`. Add `vidbyte-sdk = "vidbyte.cli:main"` beside it. Look at `vidbyte/mcp_server/__main__.py` for the house style of a `main()` module.
- **Suggested file layout** (3 files + README):
  - `vidbyte/cli/__init__.py` G현 `main(argv: list[str] | None = None) -> int`: builds root parser (`prog="vidbyte-sdk"`, `--version` from package metadata via `importlib.metadata.version("vidbyte-sdk")`), attaches subparsers, calls each group's `register`, dispatches to the selected handler, returns exit code.
  - `vidbyte/cli/skills.py` G현 `register(subparsers)` adding `skills` with actions `list`, `show <key>`, `install <key> --dest <dir> [--force]`; handlers instantiate `Skills()` lazily (inside handlers, not at import) so `vidbyte-sdk --help` stays fast and never trips catalog validation.
  - `vidbyte/cli/__main__.py` G현 `raise SystemExit(main())` so `python -m vidbyte.cli` works.
  - `vidbyte/cli/README.md` G현 folder README in house format.
- **`main()` must accept an argv parameter** and return an int rather than calling `sys.exit` internally (except in `__main__.py`) G현 this is what makes the CLI unit-testable without subprocesses.
- **Key parsing UX**: accept both the enum value (`context_minimal_fanout.decompose_fanout`) and the bare kebab/snake skill name (`decompose-fanout` / `decompose_fanout`) when unambiguous; on unknown key, print the valid keys (from `Skills().keys()`) to stderr and exit 2. Do not make users type Python enum member names.
- **Error handling**: catch `ConfigurationError` (from `vidbyte.lib.errors`) and OS errors at the dispatch boundary; print `error: <message>` to stderr; exit 1. Argparse usage errors keep argparse's default exit 2. Never print a traceback for expected failures.
- **`install` behavior**: default `--dest` to the current directory's `.claude/skills/` only if you can do it without harness-specific logic G현 otherwise make `--dest` required and let the help text show an example (`vidbyte-sdk skills install decompose-fanout --dest .claude/skills`). Refuse to overwrite an existing non-empty target unless `--force` is passed. Print the final written path on success.
- **Tests** (`tests/test_cli_interface.py`): call `main([...])` directly with tmp_path destinations; assert exit codes, stdout contents for `list`/`show`, files-on-disk for `install`, unknown-key behavior, and `--force` overwrite semantics. Mirror the style of existing tests (plain pytest, no subprocess).
- **Docs to touch**: root `README.md` (a short "CLI" section with the three commands), `vidbyte/skills/README.md` (point at the CLI as the non-Python install path), `llms.txt` if it indexes developer surfaces.
- **Do NOT touch**: `vidbyte/mcp_server/`, the paradigm packages, the prompts catalog, or the `Skills` catalog itself (unless a missing capability forces a catalog addition G현 in which case add it there, with tests, not in the CLI).

### Open Questions

1. **Harness-aware install** (`--harness claude|codex|opencode|antigravity --scope user|project` resolving destination paths automatically) G현 future work; the path table exists in the prompts README / PR #154 context. v1 ships `--dest` only.
2. Should `vidbyte mcp-server` become an alias for the existing `vidbyte-mcp-server` script later? Out of scope; keep both scripts independent for now.
3. `--json` output flag on `list`/`show` for scripting G현 cheap, but omitted from v1 requirements; add only if the implementer finds it trivial.
4. Command name collision check: `vidbyte` as a console script is assumed free on the user's PATH (it is the brand name). No known conflict; if PyPI/PATH conflicts surface, fall back to `vidbyte-cli` G현 user decision at that point.

---

## 4. Goals & Non-Goals

### Goals

- A `vidbyte-sdk` console command installed with `pip install vidbyte-sdk`, via one `[project.scripts]` line.
- `vidbyte-sdk skills list` G현 enumerate all registry skills with descriptions.
- `vidbyte-sdk skills show <key>` G현 print a skill's SKILL.md to stdout.
- `vidbyte-sdk skills install <key> --dest <dir>` G현 materialize a skill folder to disk via `Skills.materialize`.
- `python -m vidbyte.cli` parity; `vidbyte-sdk --version`; testable `main(argv) -> int`.
- A growth seam (per-group `register(subparsers)` modules) for future backend-connected subcommands.
- Tests + README/docs updates.

### Non-Goals

- No click/typer/rich or any new dependency.
- No harness-aware path resolution (`--harness`/`--scope`) in v1.
- No backend/API commands, no auth, no networking of any kind.
- No changes to the `Skills` catalog contract, the paradigm assets, prompts, or the MCP server.
- No `vidbyte/skills/__main__.py` (explicitly superseded G현 see Key Decision 7).
- No shell completions, no color output, no interactive prompts.

---

## 5. Background & Context

- **Why now:** the companion design (`paradigm-skills-and-registry.md`) gives Python developers programmatic access to distributable paradigm skills, but the primary install audience is a developer at a terminal who wants a skill dropped into `.claude/skills/` without writing a script. The conversation established that pip alone cannot provide a command G현 `[project.scripts]` entry points can, with ~100 lines of argparse.
- **Why a unified command:** the user anticipates hooking the SDK to the main Vidbyte backend; starting with `vidbyte <group> <action>` now means future capabilities extend an existing surface instead of introducing one.
- **Current state:** the repo has one console script (`vidbyte-mcp-server`) proving the entry-point path works end-to-end. There is no `vidbyte/cli/` package and (as of this doc) the skills registry itself is not yet implemented G현 implementation order is registry first, CLI second.

---

## 6. Requirements

1. `pyproject.toml` gains `vidbyte-sdk = "vidbyte.cli:main"` under `[project.scripts]`; the existing `vidbyte-mcp-server` entry is unchanged.
2. `vidbyte/cli/` is an importable package containing `__init__.py` (with `main`), `skills.py`, `__main__.py`, and `README.md`; it ships in the wheel via the existing `packages.find` include (`vidbyte*`) with no extra package-data config.
3. `main(argv: list[str] | None = None) -> int` parses argv (defaulting to `sys.argv[1:]`), dispatches, and returns an exit code; it never calls `sys.exit` itself.
4. `vidbyte-sdk --version` prints the installed `vidbyte-sdk` version (via `importlib.metadata`) and exits 0.
5. `vidbyte-sdk skills list` prints one line per registry skill G현 key plus description G현 sourced from `Skills`; exits 0.
6. `vidbyte-sdk skills show <key>` prints the skill's SKILL.md text to stdout; exits 0.
7. `vidbyte-sdk skills install <key> --dest <dir>` calls `Skills.materialize`, creating `<dir>` if needed, and prints the written skill path; exits 0. With an existing non-empty target it exits 1 with an error unless `--force` is given.
8. `<key>` accepts the full enum value and unambiguous short forms (kebab or snake skill name); an unknown key prints the valid keys to stderr and exits 2.
9. Expected failures (`ConfigurationError`, filesystem errors, unknown keys) produce a one-line stderr message and a nonzero exit G현 never a traceback.
10. `Skills` is instantiated only inside command handlers, so `vidbyte-sdk --help` and `vidbyte-sdk skills --help` succeed even if catalog assets are broken.
11. `python -m vidbyte.cli <args>` behaves identically to `vidbyte <args>`.
12. `tests/test_cli_interface.py` covers requirements 3G혀11 by invoking `main()` in-process (no subprocesses), using `tmp_path` for installs and `capsys` for output.
13. Root `README.md` documents the three commands; `vidbyte/cli/README.md` follows the house folder-README format.

---

## 7. Non-Functional Requirements

- **Performance:** `vidbyte-sdk --help` must not import or validate the skills catalog (lazy handler-level instantiation); target sub-200ms help output on a warm interpreter.
- **Scalability:** adding a subcommand group must require only a new module with `register(subparsers)` plus one call in `main()` G현 no refactor.
- **Security:** `install` writes only under the user-supplied `--dest` (path-traversal safety is owned by `Skills.materialize` per the registry doc; the CLI must not bypass it). No network access. No secrets handling.
- **Observability:** N/A G현 stdout/stderr and exit codes are the whole interface; keep stderr messages one-line and prefixed `error:`.
- **Reliability:** deterministic exit codes (0 success, 1 expected failure, 2 usage/unknown-key); identical behavior on Windows and POSIX (pathlib everywhere, no ANSI codes).
- **Compatibility:** stdlib only; Python >= 3.11; no change to existing scripts or public SDK imports.

---

## 8. High-Level Design

The CLI is a three-module adapter in front of the skills registry. `vidbyte/cli/__init__.py` owns the root argparse parser: program name, `--version`, and a subparsers object it passes to each subcommand group's `register()` function. `vidbyte/cli/skills.py` is the first and only group: `register()` declares the `skills` subparser with `list`/`show`/`install` actions and binds each to a handler function; handlers construct `Skills()` on demand, call the corresponding catalog method (`keys()` + `descriptions()`, `text()`, `materialize()`), print results, and return exit codes. `vidbyte/cli/__main__.py` bridges `python -m vidbyte.cli`. The single pyproject entry point (`vidbyte-sdk = "vidbyte.cli:main"`) makes pip generate the PATH executable at install time.

Key design decisions: all skill knowledge stays in the catalog (the CLI never touches `importlib.resources`, manifests, or file trees directly); handlers are lazy so a broken asset tree cannot break `--help`; `main()` takes argv and returns int so the whole surface is unit-testable in-process; and the explicit `register()` seam G현 rather than plugin discovery G현 keeps growth cheap while the command count is small.

```
 pip install vidbyte-sdk
        |  [project.scripts] vidbyte-sdk = "vidbyte.cli:main"
        v
 $ vidbyte-sdk skills install decompose-fanout --dest .claude/skills
        |
        v
 vidbyte/cli/__init__.py   main(argv) -> int
        |   root parser + --version
        v
 vidbyte/cli/skills.py     register(subparsers); handlers: list/show/install
        |
        v
 vidbyte/skills/catalog.py Skills.keys()/descriptions()/text()/materialize()
        |                  (from paradigm-skills-and-registry.md)
        v
 vidbyte/paradigms/context_minimal_fanout/skills/G푸  packaged assets
        |
        v
 .claude/skills/decompose-fanout/SKILL.md (+ references/) written to disk
```

Future growth (out of scope, shaping the seam only): a `backend`-style group registering alongside `skills` in `main()`, and an optional later alias for the MCP server. Neither influences v1 code beyond the `register()` convention.

---
