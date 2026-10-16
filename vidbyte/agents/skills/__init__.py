"""FILE: vidbyte/agents/skills/__init__.py

PURPOSE: Marks the agent-agnostic package that turns declarative skill entries (inline text, a local folder, a skills.sh install, a GitHub folder, an Anthropic or OpenAI skill) into SkillDocument records, with a reason and an explanation for every entry it cannot load.
ROLE IN CODEBASE: Imported through its modules: vidbyte.agents.skills.loader (SkillLoader) by JevSkillsPreload in vidbyte/agents/jev/alignment/skills.py, and one module per source resolver (vidbyte.agents.skills.github for GitHubSkillResolver) by the loader.
ARCHITECTURE NOTE: The package exports nothing here on purpose, so adding a source never edits this file; callers import each module directly. Its modules import only vidbyte.lib and their sibling modules, never vidbyte.agents.jev or the vidbyte.agents package root, which is still initializing while JEV imports the loader.
FUNCTION INVENTORY: No functions.
COMMON MODIFICATION PATTERNS: A new source is a new resolver module in this package plus one loader map entry; see README.md for every step.
WHAT NOT TO DO IN THIS FILE: 1. Do not add per-resolver imports or exports. 2. Do not add import-time side effects.
KNOWN EDGE CASES: None.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md
TESTS: tests/features/jev_skills_preload/
"""

from __future__ import annotations

__all__: list[str] = []
