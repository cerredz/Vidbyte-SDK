"""FILE: vidbyte/lib/constants/coding.py

PURPOSE: Defines the fixed file names and byte caps that CodingAgent uses when it loads a repository's AGENTS.md and MAP.md into the model's context, the probe script, limits, marker-file tables, and dependency caps of its environment section, the line and byte caps on the output tail it shows for a failed setup command, and the paths, cap, template, and model-facing text of the agent's own progress notes file. It also defines the named bounds of CodingAgent's verification command: the default and the smallest allowed number of verification attempts.
ROLE IN CODEBASE: Read by AgentsMdLoader (vidbyte/agents/coding_context/agents_md.py), EnvironmentLoader (vidbyte/agents/coding_context/environment.py), EnvironmentProbe (vidbyte/agents/coding_context/environment_probe.py), ProjectDependencies (vidbyte/agents/coding_context/project_dependencies.py), MapMdLoader (vidbyte/agents/coding_context/map_md.py), SetupCommandsLoader (vidbyte/agents/coding_context/setup_commands.py), ProgressNotesLoader (vidbyte/agents/coding_context/progress_notes.py), and the coding-agent feature tests. The verification bounds are read by vidbyte/lib/dataclasses/coding.py (CodingAgentSettings and CodingVerification checks) and by vidbyte/agents/coding.py (the max_verify_attempts default).
ARCHITECTURE NOTE: Immutable constants only; the loaders own the reading, decoding, probing, and truncation behavior, with RootFileLoader (vidbyte/agents/coding_context/root_file.py) doing it for AGENTS.md and MAP.md. The verification itself lives in vidbyte/middleware/builtins/verify_command.py. The probe script prints raw tab-separated records, not text for the model; EnvironmentProbe parses them and EnvironmentContextItem (vidbyte/context/primitives/documents.py) formats them. Marker tables are tuples of pairs, so their order is the listing order.
COMMON MODIFICATION PATTERNS: Change the cap here, never at the read call, so the loader, its truncation line, and the tests stay in step. Add a named constant here before introducing another CodingAgent policy literal. A new tool to report is one more name in the probe script's tool loop, and a new system package manager one more name in its package-manager loop. A new language or lockfile is one more pair in its marker table.
KNOWN EDGE CASES: The AGENTS.md, MAP.md, and notes caps count bytes, not characters; the loader moves the cut back to a whole UTF-8 character, so the shown text can be up to three bytes shorter. The setup-output byte cap can cut the first shown line, or a character in it. The verify-attempts default is a count of command runs, not of retries: 3 means the third failed run ends the run. The probe script uses only bash 3.2 syntax, because macOS ships bash 3.2.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-environment-context.md; docs/design/coding-agent-map-md.md; docs/design/coding-agent-setup-commands.md; docs/design/coding-agent-progress-notes.md; docs/design/coding-agent-verify-command.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py, tests/features/coding_agent/test_coding_agent_environment.py, tests/features/coding_agent/test_coding_agent_map_md.py, tests/features/coding_agent/test_coding_agent_setup_commands.py, tests/features/coding_agent/test_coding_agent_progress_notes.py, and tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

# The preferred file name; any case variant is accepted when this exact
# name is absent from the root folder.
CODING_AGENTS_MD_FILE_NAME = "AGENTS.md"

# 32 KiB, Codex's default project-doc cap, so a huge file cannot fill
# the model's context.
CODING_AGENTS_MD_MAX_BYTES = 32_768

# The preferred repository-map file name; any case variant, such as
# map.md, is accepted when this exact name is absent.
CODING_MAP_MD_FILE_NAME = "MAP.md"

# 32 KiB, the same cap as AGENTS.md; a map is meant to be short.
CODING_MAP_MD_MAX_BYTES = 32_768

# A failed setup command shows at most this many of its last output
# lines, taken from at most this many of its last output bytes, so one
# huge line cannot fill the model's context either. Errors are at the
# end, so the tail is the useful part.
CODING_SETUP_OUTPUT_TAIL_LINES = 30
CODING_SETUP_OUTPUT_TAIL_BYTES = 8_192

# One limit over the whole environment probe; tool versions are quick,
# so only a hanging tool reaches it.
CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS = 15.0

# The probe prints about 30 short lines; more than this is never read.
CODING_ENVIRONMENT_PROBE_MAX_BYTES = 8_192

# Files in the root folder that name the project's language, as (file
# name, language) pairs in the order the languages are listed.
CODING_ENVIRONMENT_LANGUAGE_MARKERS = (
    ("pyproject.toml", "Python"),
    ("setup.py", "Python"),
    ("requirements.txt", "Python"),
    ("package.json", "JavaScript"),
    ("tsconfig.json", "TypeScript"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pom.xml", "Java"),
    ("build.gradle", "Java or Kotlin"),
    ("build.gradle.kts", "Kotlin"),
    ("Gemfile", "Ruby"),
    ("composer.json", "PHP"),
    ("CMakeLists.txt", "C or C++"),
    ("Package.swift", "Swift"),
    ("pubspec.yaml", "Dart"),
    ("mix.exs", "Elixir"),
)

# Lockfiles in the root folder that name the package manager the
# project uses, as (file name, package manager) pairs.
CODING_ENVIRONMENT_PACKAGE_MANAGER_MARKERS = (
    ("uv.lock", "uv"),
    ("poetry.lock", "Poetry"),
    ("Pipfile.lock", "Pipenv"),
    ("pdm.lock", "PDM"),
    ("package-lock.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "Yarn"),
    ("bun.lock", "Bun"),
    ("bun.lockb", "Bun"),
    ("Cargo.lock", "Cargo"),
    ("go.sum", "Go modules"),
    ("Gemfile.lock", "Bundler"),
    ("composer.lock", "Composer"),
)

# Build and task files in the root folder that tell the model how the
# project is built, tested, or run.
CODING_ENVIRONMENT_BUILD_FILES = (
    "Makefile",
    "justfile",
    "Taskfile.yml",
    "tox.ini",
    "noxfile.py",
    "Dockerfile",
    "compose.yaml",
    "docker-compose.yml",
)

# Folders in the root folder that hold installed dependencies; one being
# present tells the model the install step has already run.
CODING_ENVIRONMENT_DEPENDENCY_FOLDERS = (".venv", "venv", "node_modules", "vendor")

# A manifest larger than this is not read for dependency names.
CODING_ENVIRONMENT_MANIFEST_MAX_BYTES = 262_144

# At most this many declared dependency names are shown.
CODING_ENVIRONMENT_MAX_DEPENDENCIES = 60

# Run as `bash -c` in the root folder. It prints raw tab-separated
# records, one per line, and EnvironmentContextItem formats them:
#   bash, then the bash version and `uname -srm`;
#   package-manager, then a system package manager found on the PATH;
#   tool, then the name, the first version line, and the path.
# Package managers come before tools, so a hanging tool cannot hide
# them. It never prints environment values or the host name (uname
# gets no -n).
CODING_ENVIRONMENT_PROBE_SCRIPT = r"""
printf 'bash\t%s\t%s\n' "$BASH_VERSION" "$(uname -srm 2>/dev/null)"
for m in brew port apt-get dnf yum zypper pacman apk winget choco scoop; do
  command -v "$m" >/dev/null 2>&1 && printf 'package-manager\t%s\n' "$m"
done
for t in git python python3 pip uv poetry node npm pnpm yarn bun deno go cargo rustc java dotnet ruby php docker make gh; do
  p=$(command -v "$t") || continue
  case $t in
    go) v=$("$t" version 2>&1) ;;
    java) v=$("$t" -version 2>&1) ;;
    *) v=$("$t" --version 2>&1) ;;
  esac
  printf 'tool\t%s\t%s\t%s\n' "$t" "${v%%$'\n'*}" "$p"
done
"""

# The agent's own notes folder and file under the root folder. They are
# local working files, not a repository convention. The folder is its
# own subfolder of .vidbyte, which other Vidbyte tools also write to.
CODING_PROGRESS_NOTES_DIR = ".vidbyte/coding-agent"
CODING_PROGRESS_NOTES_FILE_NAME = "progress.md"

# Written as .vidbyte/coding-agent/.gitignore, so only the notes folder
# ignores itself, the way pytest's .pytest_cache does. Neither the
# user's .gitignore nor other tools' files under .vidbyte are touched.
CODING_PROGRESS_NOTES_GITIGNORE = "*\n"

# 32 KiB, the same cap as AGENTS.md; notes are meant to stay short.
CODING_PROGRESS_NOTES_MAX_BYTES = 32_768

# The text of a new notes file: a heading and three empty headings.
CODING_PROGRESS_NOTES_TEMPLATE = "# Progress notes\n\n## Done\n\n## Next\n\n## Decisions\n"

# Shown to the model above the notes.
CODING_PROGRESS_NOTES_INSTRUCTION = "This is your own notes file for this repository. It is kept between runs and is never committed. Read it before you start.\nAfter each meaningful step, update .vidbyte/coding-agent/progress.md with write_text or replace_text: what is done, what is next, and any decisions.\nKeep it short."

# Shown after notes cut at the cap.
CODING_PROGRESS_NOTES_TRUNCATION_NOTE = "[The notes were cut at 32 KiB. Read the rest of .vidbyte/coding-agent/progress.md with read_lines, then shorten it.]"

CODING_DEFAULT_MAX_VERIFY_ATTEMPTS = 3
CODING_MIN_VERIFY_ATTEMPTS = 1

__all__ = [
    "CODING_AGENTS_MD_FILE_NAME",
    "CODING_AGENTS_MD_MAX_BYTES",
    "CODING_DEFAULT_MAX_VERIFY_ATTEMPTS",
    "CODING_ENVIRONMENT_BUILD_FILES",
    "CODING_ENVIRONMENT_DEPENDENCY_FOLDERS",
    "CODING_ENVIRONMENT_LANGUAGE_MARKERS",
    "CODING_ENVIRONMENT_MANIFEST_MAX_BYTES",
    "CODING_ENVIRONMENT_MAX_DEPENDENCIES",
    "CODING_ENVIRONMENT_PACKAGE_MANAGER_MARKERS",
    "CODING_ENVIRONMENT_PROBE_MAX_BYTES",
    "CODING_ENVIRONMENT_PROBE_SCRIPT",
    "CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS",
    "CODING_MAP_MD_FILE_NAME",
    "CODING_MAP_MD_MAX_BYTES",
    "CODING_MIN_VERIFY_ATTEMPTS",
    "CODING_PROGRESS_NOTES_DIR",
    "CODING_PROGRESS_NOTES_FILE_NAME",
    "CODING_PROGRESS_NOTES_GITIGNORE",
    "CODING_PROGRESS_NOTES_INSTRUCTION",
    "CODING_PROGRESS_NOTES_MAX_BYTES",
    "CODING_PROGRESS_NOTES_TEMPLATE",
    "CODING_PROGRESS_NOTES_TRUNCATION_NOTE",
    "CODING_SETUP_OUTPUT_TAIL_BYTES",
    "CODING_SETUP_OUTPUT_TAIL_LINES",
]
