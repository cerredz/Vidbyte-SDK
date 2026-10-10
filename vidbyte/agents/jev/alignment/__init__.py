"""FILE: vidbyte/agents/jev/alignment/__init__.py

PURPOSE: Groups JevAgent's request-time alignment capabilities; today it holds the skill preload in skills.py.
ROLE IN CODEBASE: JevAgent imports JevSkillsPreload from vidbyte.agents.jev.alignment.skills directly, so importing this package loads nothing.
ARCHITECTURE NOTE: Each capability keeps its own module; the package exports nothing so a capability's dependencies load only when JevAgent uses it.
COMMON MODIFICATION PATTERNS: Add a capability as its own module and import it from JevAgent.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no credentials.
RELATED DOCS: docs/design/jev-skills-preload.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_skill_preload.py.
"""

__all__: list[str] = []
