"""FILE: vidbyte/lib/constants/coding.py

PURPOSE: Defines the fixed AGENTS.md file name and byte cap that CodingAgent uses when it loads a repository's AGENTS.md into the model's context, and the probe script, limits, and project marker files of its environment section.
ROLE IN CODEBASE: Read by AgentsMdLoader (vidbyte/agents/coding_context/agents_md.py), EnvironmentLoader (vidbyte/agents/coding_context/environment.py), and the coding-agent feature tests.
ARCHITECTURE NOTE: Immutable constants only; the loaders own the reading, decoding, probing, and truncation behavior. The probe script prints finished lines, so the loader only caps and appends them.
COMMON MODIFICATION PATTERNS: Change a cap or a limit here, never at the call, so the loaders, their notes, and the tests stay in step. A new tool to report is one more name in the probe script's for list.
KNOWN EDGE CASES: The AGENTS.md cap counts bytes, not characters; the loader moves the cut back to a whole UTF-8 character, so the shown text can be up to three bytes shorter. The probe script uses only bash 3.2 syntax, because macOS ships bash 3.2.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-environment-context.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py and tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

# The preferred file name; any case variant is accepted when this exact
# name is absent from the root folder.
CODING_AGENTS_MD_FILE_NAME = "AGENTS.md"

# 32 KiB, Codex's default project-doc cap, so a huge file cannot fill
# the model's context.
CODING_AGENTS_MD_MAX_BYTES = 32_768

# One limit over the whole environment probe; tool versions are quick,
# so only a hanging tool reaches it.
CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS = 15.0

# The probe prints about 20 short lines; more than this is never shown.
CODING_ENVIRONMENT_PROBE_MAX_BYTES = 8_192

# Files in the root folder that tell the model which package manager or
# build tool the project uses.
CODING_ENVIRONMENT_PROJECT_MARKERS = (
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "Cargo.toml",
    "go.mod",
    "Makefile",
)

# Run as `bash -c` in the root folder. It prints the bash version and
# the system, then each tool found on bash's own PATH with the first
# line of its version output. It never prints environment values or the
# host name (uname gets no -n).
CODING_ENVIRONMENT_PROBE_SCRIPT = r"""
printf -- '- Bash: %s (%s)\n' "$BASH_VERSION" "$(uname -srm 2>/dev/null)"
echo '- Tools on the bash PATH (first line of each version output):'
for t in git python python3 pip uv poetry node npm pnpm yarn bun go cargo java dotnet docker make gh; do
  p=$(command -v "$t") || continue
  case $t in
    go) v=$("$t" version 2>&1) ;;
    java) v=$("$t" -version 2>&1) ;;
    *) v=$("$t" --version 2>&1) ;;
  esac
  printf -- '  - %s: %s (%s)\n' "$t" "${v%%$'\n'*}" "$p"
done
"""

__all__ = [
    "CODING_AGENTS_MD_FILE_NAME",
    "CODING_AGENTS_MD_MAX_BYTES",
    "CODING_ENVIRONMENT_PROBE_MAX_BYTES",
    "CODING_ENVIRONMENT_PROBE_SCRIPT",
    "CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS",
    "CODING_ENVIRONMENT_PROJECT_MARKERS",
]
