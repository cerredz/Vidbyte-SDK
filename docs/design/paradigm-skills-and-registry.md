# Design Doc: Paradigm Skills + Skills Registry

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Add a set of distributable, harness-agnostic **skill files** to the first thin-harness paradigm (`context_minimal_fanout`), colocated inside the paradigm's Python package so they ship in the pip wheel, and add a **skills registry** (`vidbyte.skills`) — an enum-keyed, import-validated catalog mirroring the existing `vidbyte.prompts.Prompts` catalog — so any developer who has `pip install vidbyte-sdk` can list, read, and materialize these skills from their own code. The four initial skills are operating instructions for the context-window-minimal paradigm family: "decompose then implement", "decompose + design docs then implement", "decompose + design docs + subagent fanout", and "decompose + subagent fanout". A shared reference file holds the exact subagent-spawn terminal commands for popular coding harnesses so that command drift is confined to one file.

---

## 2. Original User Prompts

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

---

## 3. Structured Conversation Notes

### Key Decisions

1. **Skills live inside the paradigm Python package**, at `vidbyte/paradigms/context_minimal_fanout/skills/`, NOT in the repo's top-level `skills/` directory. Reasoning: the moment we want pip distribution plus a code registry, the files must be inside the `vidbyte` package tree so `[tool.setuptools.package-data]` includes them in the wheel and `importlib.resources` can load them. Precedent already exists on both fronts: `pyproject.toml` line 44 already ships `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/*.md` as package data, and `vidbyte/prompts/skills/prompt-bucket.md` is an existing distributable skill living inside the package.
2. **The four requested skills are paradigm *strategies*, not per-Python-implementation adapters.** Only one Python implementation exists (`multiple_prompts/`); three of the four skills have no `harness.py` behind them. The skill folders are therefore keyed by strategy name, one subfolder per skill, and do NOT mirror the implementation subpackages 1:1. (The user originally said "subfolder for each implementation"; in the /talk discussion this was refined: skills are adapters of the paradigm *concept* and can precede runnable implementations. The user accepted this framing by approving the plan with "great".)
3. **Registry is a sibling of — not merged into — the prompt registry.** The user floated "maybe hooking up our thin harness paradigm skills to the prompt registry"; the agreed direction is a separate `Skills` catalog that *copies the `Prompts` catalog pattern exactly* (JSON manifest + Markdown assets + enum keys + import-time sync validation) but is its own class, because prompts are text-by-enum while skills are file trees with install semantics. Different value type, different verbs.
4. **Exact harness spawn commands go in ONE shared reference file** (`references/harness-commands.md`), pointed to by both fanout skills, instead of being inlined into each SKILL.md. CLI flags for `claude`, `codex`, `opencode`, etc. drift constantly; keep the drift surface to a single file. The file must also include a "how to discover the command for other/unknown platforms" section (check `<tool> --help`, official docs).
5. **Skill document structure**: YAML frontmatter (`name`, `description` — required by Claude Code skill discovery) followed by Goal, Description, Algorithm (numbered step-by-step), and Rules sections. Goal and Description are intentionally longer overview sections, while use cases are omitted from the shipped skill files per review feedback.
6. **Top-level `skills/` directory stays untouched** in this change. It is contributor-facing (skills for working *on* this repo). The new paradigm skills are *distributable* (skills a downstream dev installs into their own harness). Both READMEs should name this distinction.
7. **Developer-facing "use in their own code" includes a materialize helper**: beyond `list`/`get`/`read`, the registry should be able to write a skill's file tree to a destination directory (e.g. `.claude/skills/decompose-fanout/`). This is the no-CLI install path.

### Rejected Alternatives

- **Top-level `skills/` as the home for the new skills** — rejected: not shippable in the wheel (setuptools `packages.find` only includes `vidbyte*`), and it would blur the contributor-vs-distributable distinction.
- **Merging skills into the `Prompts` catalog / `Prompt` enum** — rejected: skills are multi-file artifacts with install destinations; jamming them into a text-by-enum catalog muddies both. The prompts README already flags `prompt_bucket` and `agentic_engineering_skill` as "on-disk skill, not part of the import-validated catalog" — evidence the prompt catalog is the wrong container.
- **A separate npm package** — rejected: this is a Python SDK; a parallel npm artifact of markdown files is pure drift risk.
- **Skill folders mirroring Python implementation subpackages 1:1** — rejected: three of four skills have no Python implementation yet.
- **Building the CLI installer in this change** — deferred: the registry + materialize helper is the foundation; a `[project.scripts]` console command can wrap it later (see Open Questions / the distribution discussion).

### Constraints & Assumptions

- Python >= 3.11, setuptools build backend, deps limited to `pydantic>=2,<3` and `httpx>=0.27`. **The registry must not add any new dependency** — stdlib `json` + `importlib.resources` only, exactly like `catalog.py`.
- The paradigm governance rules in `skills/paradigm/SKILL.md` apply: *"Never treat a skill as the canonical implementation of a paradigm. Skills are adapters and operating instructions for external harnesses."* The four skills are adapters of the context-minimal paradigm concept; they must not claim to be the SDK implementation.
- House style: Context Protocol Header comments at the top of new `__init__.py`/module files (see `vidbyte/prompts/__init__.py` and `vidbyte/lib/enums/prompts.py` for the exact format), frozen slotted dataclasses for records, `ConfigurationError` from `vidbyte.lib.errors` for validation failures, `ClassVar` lazy-load caching.
- Naming: snake_case for enum values / manifest keys (paradigm conventions), kebab-case for skill folder names (Claude Code skill convention). Both spellings of the same skill must map deterministically (e.g. `decompose_then_implement` ↔ `decompose-then-implement/`).
- Current checked-out branch is `feat/context-minimal-fanout-trace`; implementation should branch appropriately (the implement skill handles git).

### Clarifications & Answers

- Q (user): best distribution — code registry, npm/pip hookup, publish somewhere, or raw repo files? A (agreed): layered — repo files are the source of truth; ship them in the existing pip package via package-data; expose via a code registry mirroring `Prompts`; CLI installer later; skip npm entirely. Releasing the SDK *is* the publish step.
- Q (user): hook skills to the prompt registry? A: sibling registry with identical mechanics, not a merge (see Key Decision 3).
- Q (user, pending): can we do `pip install vidbyte-sdk-skills` as a command, or do we need a whole CLI? A (answered in conversation, out of scope for this doc's implementation): `pip install` only installs files; commands come from `[project.scripts]` entry points, which need only a single argparse function, not a framework — `vidbyte-mcp-server` in `pyproject.toml` is the existing precedent. A separate PyPI package is unnecessary. Also `python -m vidbyte.skills` works with just a `__main__.py`. This doc includes the optional `__main__.py` as a stretch requirement but the console-script wiring is a follow-up.

### Terminology / Glossary

- **Paradigm / thin harness**: a named high-level agentic execution strategy packaged under `vidbyte/paradigms/` (see `vidbyte/paradigms/README.md`). First family: `context_minimal_fanout`.
- **Implementation**: a runnable Python subpackage of a paradigm, e.g. `context_minimal_fanout/multiple_prompts/` (harness.py + prompts + types).
- **Skill (distributable)**: a Markdown operating-instruction folder (SKILL.md + optional supporting files) a developer installs into an external coding harness (Claude Code, Codex, opencode, Cursor, Antigravity) to make that harness execute the paradigm strategy.
- **Contributor skill**: a SKILL.md under the repo top-level `skills/` used by agents working on this repo itself. NOT shipped.
- **Registry / catalog**: the enum-keyed loader class exposing packaged assets to Python code (`Prompts` today; `Skills` in this design).
- **Materialize**: write a skill's packaged file tree to a caller-chosen directory on disk.
- **Fanout**: running decomposed subtasks in parallel subagents with fresh context windows.

### Implementation Hints for the Downstream Model

- **Copy `vidbyte/prompts/catalog.py` as the template for `vidbyte/skills/catalog.py`.** It shows the exact patterns to reuse: `resources.files(...)` traversal, JSON manifest validation with `ConfigurationError`, `_validate_enum_sync` (every enum member must resolve to an asset, every asset to an enum member), `ClassVar` caching, frozen slotted dataclass record.
- **Copy `vidbyte/lib/enums/prompts.py`'s header style and str-Enum pattern** for the new `vidbyte/lib/enums/skills.py`.
- **Copy `tests/test_prompts_interface.py`'s test approach** for `tests/test_skills_interface.py`.
- **`pyproject.toml` package-data gotcha**: keys must be importable packages. The `skills/` folder under the paradigm package will have no `__init__.py`, so add globs under the parent package key, e.g. `"vidbyte.paradigms.context_minimal_fanout" = ["skills/*/*.md", "skills/references/*.md", "skills/skills.json"]`. Do not rely on `**` recursive globs (setuptools support is version-sensitive); enumerate the levels.
- **The existing `skills/context-minimal-fanout/SKILL.md` (top-level, contributor) overlaps ~80% with the new `decompose-fanout` skill.** Do not delete it in this change; its Markdown-split-plan structure (Owned Paths / Read-Only Paths / non-overlap rules) is excellent source material — reuse that structure inside the two fanout skills' Algorithm sections.
- **The `multiple_prompts` implementation's assets** (`split_prompt.md`, `implementation_prompt.md`) show the paradigm's canonical vocabulary (split plan, ownership, non-overlap). Keep skill wording consistent with them and with `context_minimal_fanout/README.md`.
- **Harness spawn commands for `references/harness-commands.md`** — verify each against current docs at implementation time; known shapes as of this writing: Claude Code headless `claude -p "<prompt>"` (add `--permission-mode`/`--allowedTools` as needed; inside a Claude Code session, subagents are spawned via the built-in Task/Agent tool, not the CLI); Codex CLI `codex exec "<prompt>"`; opencode `opencode run "<prompt>"`; Cursor `cursor-agent -p "<prompt>"`; Gemini CLI `gemini -p "<prompt>"`. Include a closing subsection: "for any other platform, run `<tool> --help` and look for a non-interactive/print/exec mode; check the platform's docs for 'headless' or 'scripting'." Also state that fanout = launching N of these as parallel background processes from the current session, and the parent must wait for all to exit before merging.
- **Frontmatter is load-bearing**: Claude Code (and most harnesses) discover skills by `name` + `description` in YAML frontmatter. Every SKILL.md must have both; `name` matches the folder name.
- **README updates to make**: `vidbyte/paradigms/README.md` (mention the skills dir + registry), `vidbyte/paradigms/context_minimal_fanout/README.md` (list the four skills), new `vidbyte/skills/README.md` (catalog docs in the style of `vidbyte/prompts/README.md`, including a quick-reference table with GitHub links so the personal `/vidbyte-prompts` skill can resolve them), and a one-line note in the top-level `skills/` docs distinguishing contributor vs distributable skills. Follow the repo's folder-README house format (Role In The SDK / Design Philosophy / Usage / Key Modules / Related Layers).
- **Dynamic exports**: `vidbyte/prompts/__init__.py` generates direct imports from the catalog at import time. Mirror this only if cheap; direct text imports are less useful for multi-file skills — exporting `Skill`, `SkillRecord`, `Skills` is sufficient.
- Do NOT touch `vidbyte/paradigms/base.py`, `client.py`, or the `multiple_prompts` harness code. This change is assets + registry only.

### Open Questions

1. Should `Skills` also be reachable as `VidbyteSDK().skills` (like `sdk.paradigms`), or direct-import only (like `Prompts`)? Default if undecided: direct import only, matching `Prompts`; adding an SDK property later is non-breaking.
2. Should the two on-disk skills under `vidbyte/prompts/skills/` (`prompt-bucket.md`, `agentic-engineering.md`) be folded into the new registry now? Default: no — note it in `vidbyte/skills/README.md` as a planned consolidation.
3. Console-script wiring (`vidbyte skills install ...`) — explicitly a follow-up change; see the distribution Q&A above. The optional `python -m vidbyte.skills` entry in this design keeps the door open.
4. Eventual fate of the top-level contributor skill `skills/context-minimal-fanout/SKILL.md` (supersede vs keep) — user decision, deferred.

---

## 4. Goals & Non-Goals

### Goals

- Ship four distributable skill folders under `vidbyte/paradigms/context_minimal_fanout/skills/`, each with frontmatter + Goal / Description / Algorithm / Rules sections.
- Ship one shared `references/harness-commands.md` with exact subagent-spawn commands per major coding harness plus discovery guidance for unknown platforms.
- Add a `skills.json` manifest and a `Skills` catalog (`vidbyte/skills/`) with a `Skill` enum (`vidbyte/lib/enums/skills.py`), giving developers `list`/`get`/`descriptions`/`files`/`materialize` access from Python.
- Package everything into the wheel via package-data so `pip install vidbyte-sdk` delivers the skills.
- Import-time validation: manifest ↔ filesystem ↔ enum sync, non-empty frontmatter, referenced files exist.
- Tests mirroring `tests/test_prompts_interface.py`, plus README/documentation updates.

### Non-Goals

- No CLI / console-script installer in this change (follow-up; see Open Question 3).
- No npm package, no hosted registry, no MCP-server exposure of skills.
- No changes to paradigm harness Python code (`base.py`, `client.py`, `multiple_prompts/`).
- No new Python implementations for the three strategies that lack one.
- No moving/deleting top-level contributor `skills/` content.
- No consolidation of `vidbyte/prompts/skills/*.md` into the new registry (documented as future work only).

---

## 5. Background & Context

- **Why now:** the paradigms namespace just landed its first concrete family (`context_minimal_fanout`, PR #206 lineage) and the user wants the paradigm usable from *any* coding harness immediately — via skills — not only through the Python harness. Skills also seed the broader plan of making Vidbyte skills installable by downstream devs.
- **Problem solved:** today the decompose/design-doc/fanout strategies exist only as scattered contributor guidance (`skills/context-minimal-fanout/SKILL.md`) and one Python harness. A downstream developer has no supported way to discover or install these strategies into their own Claude Code / Codex / opencode setup, and no programmatic index of what skills the SDK ships.
- **Current state being extended:** `vidbyte.prompts` already solved the identical problem for prompt text (enum-keyed catalog, JSON manifests, package-data, import-time validation, README quick-reference table consumed by the personal `/vidbyte-prompts` skill). This design deliberately clones that proven machinery for skills.
- **Dependencies:** none new; builds on setuptools package-data and `importlib.resources` exactly as `catalog.py` does.

---

## 6. Requirements

1. `vidbyte/paradigms/context_minimal_fanout/skills/` exists and contains exactly four skill folders — `decompose-then-implement/`, `decompose-design-then-implement/`, `decompose-design-fanout/`, `decompose-fanout/` — each holding a `SKILL.md`, plus `references/harness-commands.md` and a `skills.json` manifest.
2. Every `SKILL.md` has YAML frontmatter with non-empty `name` (matching its folder name) and `description`, followed by sections: Goal, Description, Algorithm (numbered steps), Rules.
3. Skill content matches the user's specified behavior:
   a. **decompose-then-implement**: gather repo context → decompose the original task into subtasks → persist the subtask list to a Markdown file → solve each subtask sequentially, checking off progress.
   b. **decompose-design-then-implement**: gather context → decompose into subtasks → write a short design doc per subtask that *solves* it up front (answering the hard questions early in the context window) → implement each design doc sequentially.
   c. **decompose-design-fanout**: gather context → decompose → write per-subtask design docs → spawn one subagent per design doc using the exact commands in `references/harness-commands.md` → wait for all subagents → merge/report.
   d. **decompose-fanout**: decompose the original prompt into non-overlapping subtasks → spawn one subagent per subtask (same command reference) → wait → merge/report. Must carry the non-overlap ownership rules (owned paths vs read-only paths) from the existing contributor skill.
4. Both fanout skills reference `references/harness-commands.md` rather than inlining platform commands; that file covers at minimum Claude Code, Codex CLI, opencode, Cursor, and Gemini CLI, plus a "discovering commands for other platforms" section, plus parallel-launch/wait semantics.
5. `vidbyte/lib/enums/skills.py` exposes a dictionary of paradigm keys to skill enums, beginning with `ContextMinimalFanoutSkill` for `context_minimal_fanout`.
6. A `Skills` catalog class and frozen `SkillRecord` dataclass exist in `vidbyte/skills/catalog.py`, loading from the manifest via `importlib.resources`, exposing at minimum: `get(key) -> SkillRecord`, `text(key) -> str` (SKILL.md body), `keys()`, `descriptions()`, `paradigm(family_key)`, `files(key) -> Mapping[str, str]` (relative path → content, including shared references), and `materialize(key, dest_dir) -> Path` (writes the skill folder + needed references to `dest_dir`).
7. Import-time validation raises `ConfigurationError` for: invalid/missing manifest fields, manifest entries without folders (and vice versa), enum members without manifest entries (and vice versa), missing/empty SKILL.md or frontmatter, and dangling file references.
8. `pyproject.toml` package-data includes all new `.md` and `.json` assets; a wheel build contains them (verifiable via `python -m build` or `pip install -e .` + `importlib.resources` round-trip in tests).
9. `tests/test_skills_interface.py` covers: catalog load, enum sync, every accessor, materialize round-trip into a tmp dir (including that references land alongside fanout skills), and frontmatter presence for every shipped skill.
10. Documentation updated: `vidbyte/skills/README.md` (new, with quick-reference table + GitHub links), `vidbyte/paradigms/README.md`, `vidbyte/paradigms/context_minimal_fanout/README.md`, and the contributor-vs-distributable note near the top-level `skills/` docs.
11. (Stretch) `vidbyte/skills/__main__.py` supporting `python -m vidbyte.skills list` and `python -m vidbyte.skills install <key> --dest <dir>` using only argparse + the catalog, as the pre-CLI escape hatch.

---

## 7. Non-Functional Requirements

- **Performance:** catalog load is lazy + cached (ClassVar), same as `Prompts`; no measurable import-time regression (assets are a handful of small Markdown files).
- **Scalability:** manifest/loader design must accommodate future paradigms adding their own `skills/` dirs without changing the catalog API (manifest discovery should iterate paradigm packages, or a single top-level manifest lists per-paradigm entries — implementer's choice, but document it).
- **Security:** `materialize` must refuse to write outside `dest_dir` (no path traversal from manifest-supplied relative paths); no network access anywhere.
- **Observability:** N/A — validation errors via `ConfigurationError` with precise file names, matching existing catalog error style.
- **Reliability:** import-time validation guarantees a broken asset tree fails loudly at first use, never silently ships a partial skill; cross-platform paths (Windows dev environment is primary — use `pathlib`/`importlib.resources`, never string path concatenation).
- **No new dependencies.**

---

## 8. High-Level Design

Two cooperating pieces: **assets** and **catalog**.

**Assets.** The paradigm package gains a `skills/` asset directory (not a Python package) holding one kebab-case folder per strategy skill, a shared `references/` folder, and a `skills.json` manifest describing every skill (snake_case key, name, description, entry file, extra file references). The four SKILL.md files are authored per the content spec in Requirements 2–4, reusing the split-plan/ownership vocabulary already established by the contributor skill and the `multiple_prompts` prompt assets. `pyproject.toml` package-data globs pull the whole tree into the wheel, exactly as it already does for `multiple_prompts/*.md`.

**Catalog.** A new `vidbyte/skills/` package clones the `Prompts` catalog architecture: `Skill` enum in `vidbyte/lib/enums/skills.py` as the typed key space; `SkillRecord` frozen dataclass carrying key, paradigm, name, description, entry text, and file map; `Skills` class loading the manifest through `importlib.resources`, validating enum↔manifest↔filesystem sync at first load, and exposing read accessors plus `materialize(key, dest_dir)` which writes the skill folder (and any shared references it declares) to the destination — this is the programmatic "install" a developer calls to drop a skill into `.claude/skills/` or any other harness path. An optional `__main__.py` wraps `list`/`install` for `python -m vidbyte.skills`, deferring a real console script to a follow-up.

```
 pip install vidbyte-sdk
        |
        v  (wheel contains packaged assets)
 vidbyte/paradigms/context_minimal_fanout/skills/
 ├── skills.json  ─────────────┐ manifest
 ├── decompose-then-implement/SKILL.md
 ├── decompose-design-then-implement/SKILL.md
 ├── decompose-design-fanout/SKILL.md ──┐
 ├── decompose-fanout/SKILL.md ─────────┤ both point at
 └── references/harness-commands.md  <──┘ shared commands
        |
        v  importlib.resources
 vidbyte/skills/catalog.py  (Skills, SkillRecord)
 vidbyte/lib/enums/skills.py (paradigm-keyed skill enums)
        |
        +--> dev code: Skills().text(ContextMinimalFanoutSkill.DECOMPOSE_FANOUT)
        +--> dev code: Skills().materialize(key, ".claude/skills/")
        +--> (stretch) python -m vidbyte.skills install <key> --dest <dir>
```

Key decisions and why: colocating assets inside the paradigm package makes pip the publish channel with zero extra release steps; a sibling catalog (rather than extending `Prompts`) keeps text-by-enum and file-tree-with-install semantics separate while reusing a proven, already-tested loading pattern; one shared commands reference confines harness-CLI drift to a single file; and `materialize` gives developers a complete no-CLI install path, making the future console script a thin convenience wrapper rather than load-bearing infrastructure.

---
