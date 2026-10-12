"""FILE: vidbyte/lib/constants/skills.py

PURPOSE: Defines the fixed names, size caps, network bounds, header values, and validation patterns that the skill sources use to turn a configured skill entry into a SKILL.md document: the caps on a SKILL.md and on any download, the per-request timeout, retry, backoff, and whole-step deadline, which unavailable reasons are retried on the next run, the skills.sh install layout, the GitHub and vendor request details, and the zip checks.
ROLE IN CODEBASE: Read by the skill entry records (vidbyte/lib/dataclasses/skills.py) for name, path, and repository checks, and by the agent-agnostic skill loader package (vidbyte/agents/skills/) for every request, read, and parse. The feature tests read the caps and bounds from here.
ARCHITECTURE NOTE: Immutable constants only; the loader package owns the reading, fetching, and parsing behavior, and the records own validation. The Vidbyte API key prefix is not repeated here: it lives in vidbyte/lib/constants/jev.py as VIDBYTE_API_KEY_PREFIX, the only place it is spelled.
FUNCTION INVENTORY: No functions; constants and `__all__` only.
COMMON MODIFICATION PATTERNS: Change a cap or bound here, never at the call site, so the loader, its details, and the tests stay in step. Add a named constant here before introducing another skill-source policy literal. A new vendor header value joins the vendor block below.
WHAT NOT TO DO IN THIS FILE: Do not spell the Vidbyte key prefix (lint C020). Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: Caps count bytes, not characters, and are inclusive: a body of exactly the cap loads. The deadline bounds one whole fetch step including its retry, so it must stay above two timeouts plus the backoff. GITHUB_REPO_PATTERN alone accepts "owner/." and "owner/.."; the entry record also rejects those segments.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md
TESTS: tests/features/jev_skills_preload/test_skill_sources_fetch.py and the other skill-source modules in tests/features/jev_skills_preload/.
"""

from __future__ import annotations

import re

from vidbyte.lib.enums.skills import SkillUnavailableReason

# The file every skill folder holds; vendor archives match it without
# regard to case.
SKILL_MARKDOWN_FILE_NAME = "SKILL.md"

# 1 MiB per SKILL.md, about ten times the largest measured community
# SKILL.md, so one file cannot fill the agent's context.
SKILL_MARKDOWN_MAX_BYTES = 1_048_576

# 32 MiB per zip, tree listing, commit answer, or skill record: above
# Anthropic's 30 MB and OpenAI's 25 MB upload limits and GitHub's tree
# limit.
SKILL_DOWNLOAD_MAX_BYTES = 33_554_432

# Seconds per network operation, retries on retryable statuses, and the
# pause before the retry.
SKILL_FETCH_TIMEOUT_SECONDS = 10.0
SKILL_FETCH_RETRY_COUNT = 1
SKILL_FETCH_BACKOFF_SECONDS = 0.5

# Seconds for one whole fetch step, retry included, so a server that
# drips bytes cannot hold a run forever.
SKILL_FETCH_DEADLINE_SECONDS = 25.0

# Reasons that may clear by themselves; they are never remembered, so
# the next run tries again. Every other loader reason is remembered.
SKILL_TRANSIENT_REASONS = frozenset({SkillUnavailableReason.RATE_LIMITED, SkillUnavailableReason.FETCH_FAILED})

# Characters of a commit SHA or skills.sh hash shown in a label.
SKILL_LABEL_HASH_CHARS = 12

# A skill name used as a folder must be one path segment.
SKILL_NAME_FORBIDDEN_CHARACTERS = frozenset({"/", "\\", ":", "\x00"})
SKILL_PATH_SPECIAL_SEGMENTS = frozenset({".", ".."})

# Where npx skills installs project skills, and its lock file at the
# project root beside the .agents folder.
SKILLS_SH_DEFAULT_DIRECTORY = ".agents/skills"
SKILLS_SH_AGENTS_FOLDER = ".agents"
SKILLS_SH_SKILLS_FOLDER = "skills"
SKILLS_SH_LOCK_FILE_NAME = "skills-lock.json"
SKILLS_SH_LOCK_MIN_VERSION = 1

# GitHub REST API host, the environment variable that holds the token,
# and the accept headers that ask for a bare commit SHA, a JSON tree, and
# a raw file. The variable constant is not called GITHUB_TOKEN_ENV_VAR:
# lint S054 (ruff S105) reads any name containing _TOKEN_ that is given
# a string as a hard-coded password.
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_CREDENTIAL_ENV_VAR = "GITHUB_TOKEN"
GITHUB_ACCEPT_SHA = "application/vnd.github.sha"
GITHUB_ACCEPT_JSON = "application/vnd.github+json"
GITHUB_ACCEPT_RAW = "application/vnd.github.raw"
GITHUB_DEFAULT_REF = "HEAD"

# owner/repo: letters, digits, and hyphens for the owner; the repository
# may also hold dots and underscores. A full lowercase commit SHA skips
# the commit lookup.
GITHUB_REPO_PATTERN = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")
GITHUB_COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")

# A 403 with this header at this value, or with a retry-after header,
# is GitHub's rate limit rather than a permission refusal.
GITHUB_RATE_LIMIT_REMAINING_HEADER = "x-ratelimit-remaining"
GITHUB_RATE_LIMIT_EXHAUSTED = "0"
HTTP_RETRY_AFTER_HEADER = "retry-after"

# Anthropic Skills API version and beta headers.
ANTHROPIC_SKILLS_API_VERSION = "2023-06-01"
ANTHROPIC_SKILLS_BETA = "skills-2025-10-02"

# The version that asks a vendor for a skill's newest version, and the
# skill-record fields that name that version when the content route
# refuses it.
SKILL_VENDOR_LATEST_VERSION = "latest"
SKILL_VENDOR_LATEST_VERSION_FIELDS = ("latest_version", "latest_version_id")

# A zip body starts with this local-file signature; flag bit 0x1 marks
# an encrypted member; SKILL.md may sit at the root or one folder deep,
# and the archive must hold exactly one there.
SKILL_ARCHIVE_MAGIC = b"PK\x03\x04"
SKILL_ARCHIVE_ENCRYPTED_FLAG = 0x1
SKILL_ARCHIVE_MAX_DEPTH = 1
SKILL_ARCHIVE_MARKDOWN_COUNT = 1

__all__ = [
    "ANTHROPIC_SKILLS_API_VERSION",
    "ANTHROPIC_SKILLS_BETA",
    "GITHUB_ACCEPT_JSON",
    "GITHUB_ACCEPT_RAW",
    "GITHUB_ACCEPT_SHA",
    "GITHUB_API_BASE_URL",
    "GITHUB_COMMIT_SHA_PATTERN",
    "GITHUB_CREDENTIAL_ENV_VAR",
    "GITHUB_DEFAULT_REF",
    "GITHUB_RATE_LIMIT_EXHAUSTED",
    "GITHUB_RATE_LIMIT_REMAINING_HEADER",
    "GITHUB_REPO_PATTERN",
    "HTTP_RETRY_AFTER_HEADER",
    "SKILLS_SH_AGENTS_FOLDER",
    "SKILLS_SH_DEFAULT_DIRECTORY",
    "SKILLS_SH_LOCK_FILE_NAME",
    "SKILLS_SH_LOCK_MIN_VERSION",
    "SKILLS_SH_SKILLS_FOLDER",
    "SKILL_ARCHIVE_ENCRYPTED_FLAG",
    "SKILL_ARCHIVE_MAGIC",
    "SKILL_ARCHIVE_MARKDOWN_COUNT",
    "SKILL_ARCHIVE_MAX_DEPTH",
    "SKILL_DOWNLOAD_MAX_BYTES",
    "SKILL_FETCH_BACKOFF_SECONDS",
    "SKILL_FETCH_DEADLINE_SECONDS",
    "SKILL_FETCH_RETRY_COUNT",
    "SKILL_FETCH_TIMEOUT_SECONDS",
    "SKILL_LABEL_HASH_CHARS",
    "SKILL_MARKDOWN_FILE_NAME",
    "SKILL_MARKDOWN_MAX_BYTES",
    "SKILL_NAME_FORBIDDEN_CHARACTERS",
    "SKILL_PATH_SPECIAL_SEGMENTS",
    "SKILL_TRANSIENT_REASONS",
    "SKILL_VENDOR_LATEST_VERSION",
    "SKILL_VENDOR_LATEST_VERSION_FIELDS",
]
