"""Context Protocol Header

Description:
    Defines the engineering handoff preset.
Purpose:
    Gives coding agents a detailed, reusable section spec for continuing software work.
Architecture:
    - EngineeringHandoff: Handoff subclass with engineering-focused default sections.
Relations:
    Re-exported by vidbyte.context.handoff and consumed by HandoffAgent.
Similar Files:
    - vidbyte/context/handoff/research.py: Research-oriented handoff preset.
"""

from __future__ import annotations

from vidbyte.context.handoff.base import Handoff


class EngineeringHandoff(Handoff):
    """Prebuilt handoff for continuing software-engineering work."""

    DEFAULT_TITLE = "Engineering Handoff"

    def default_sections(self) -> dict[str, str]:
        """Return engineering-focused sections for a coding continuation handoff."""
        return {
            "Objective": (
                "Explain the original engineering goal in concrete terms, including the user request, product outcome, or bug being addressed. "
                "State what would count as completion so the next engineer understands the target state instead of only the work performed. "
                "Include any explicit constraints, scope boundaries, or non-goals that shaped the implementation. "
                "If the goal changed during the run, describe the current goal and why it changed."
            ),
            "Changes Made": (
                "List the files, modules, APIs, or tests that were changed, with enough specificity for a cold reader to find them quickly. "
                "Describe the behavioral change introduced in each area rather than only naming the file. "
                "Capture the reasoning behind important design choices so the next engineer can preserve the intended structure. "
                "Separate completed implementation from partial edits or generated artifacts that still need review."
            ),
            "Verification Status": (
                "Report every verification command, test, type check, lint check, script, or manual inspection that actually ran. "
                "State the result of each verification action and include failures or skipped checks plainly. "
                "Distinguish observed evidence from assumptions, especially when a change was not exercised end to end. "
                "If no verification was performed, say that directly and explain what should be run next."
            ),
            "Open Threads": (
                "Identify unfinished work, unresolved decisions, ambiguous requirements, and follow-up questions that remain after the run. "
                "Describe why each thread is still open so the next engineer can decide whether it is blocking or optional. "
                "Include abandoned approaches or alternatives when they explain why the current direction exists. "
                "Avoid hiding uncertainty; a clearly named open thread is more useful than an implied gap."
            ),
            "Risks & Gotchas": (
                "Surface fragile code paths, compatibility concerns, merge-conflict risks, dependency assumptions, and areas with high blast radius. "
                "Explain the specific condition that could make each risk appear instead of using generic warnings. "
                "Call out interactions with existing architecture, public imports, schemas, package layout, or tests that could surprise the next worker. "
                "When a risk is only inferred, label it as an inference and explain the evidence behind it."
            ),
            "Next Steps": (
                "Provide ordered, concrete actions that a follow-up engineer can execute immediately. "
                "Start with the highest-value or blocking action, then continue with validation, cleanup, and optional improvements. "
                "Name commands, files, review threads, or expected outputs whenever that makes an action unambiguous. "
                "Avoid broad advice; each step should describe a specific operation and the reason it matters."
            ),
        }


__all__ = [
    "EngineeringHandoff",
]
