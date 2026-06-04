"""Context Protocol Header

Description:
    Defines the research handoff preset.
Purpose:
    Gives investigation agents a detailed, reusable section spec for continuing research.
Architecture:
    - ResearchHandoff: Handoff subclass with research-focused default sections.
Relations:
    Re-exported by vidbyte.context.handoff and consumed by HandoffAgent.
Similar Files:
    - vidbyte/context/handoff/engineering.py: Engineering-oriented handoff preset.
"""

from __future__ import annotations

from vidbyte.context.handoff.base import Handoff


class ResearchHandoff(Handoff):
    """Prebuilt handoff for continuing a research or investigation task."""

    DEFAULT_TITLE = "Research Handoff"

    def default_sections(self) -> dict[str, str]:
        """Return research-focused sections for an investigation continuation handoff."""
        return {
            "Question": (
                "State the research question, decision, claim, or uncertainty the run was trying to resolve. "
                "Include any framing assumptions, definitions, or scope limits that affect how the answer should be interpreted. "
                "Clarify whether the task asked for factual verification, source mapping, comparison, synthesis, or recommendation. "
                "If the question evolved, explain the latest version and what caused the change."
            ),
            "Findings": (
                "Summarize the substantive findings reached so far, grouping related conclusions together for fast scanning. "
                "Explain the evidence strength behind each important finding rather than listing disconnected facts. "
                "Separate confirmed findings from tentative interpretations, especially when the source material was incomplete or indirect. "
                "Preserve nuance where sources conflict or where the answer depends on time, jurisdiction, or context."
            ),
            "Sources": (
                "Name the sources, documents, datasets, pages, or tool outputs that support each key finding. "
                "Describe what each source contributed so the next researcher knows why it matters. "
                "Flag primary sources, official documentation, and direct evidence separately from commentary or secondary summaries. "
                "If citations, links, or exact source identifiers were not captured, say what is missing and how to reconstruct it."
            ),
            "Confidence & Gaps": (
                "Assess confidence in the findings with explicit reasons based on source quality, consistency, recency, and directness. "
                "List information gaps, unverified assumptions, ambiguous data points, and contradictions that remain. "
                "Explain whether each gap is likely to change the answer or only improve precision. "
                "Avoid overstating certainty; mark anything inferred from weak or partial evidence."
            ),
            "Recommended Next Queries": (
                "Provide specific follow-up searches, source checks, interviews, datasets, or documents that should be examined next. "
                "Order the queries by expected value, starting with those most likely to resolve gaps or contradictions. "
                "Include useful search terms, domains, source types, or verification methods when the next step depends on them. "
                "Explain what each query is expected to prove, disprove, or clarify."
            ),
        }


__all__ = [
    "ResearchHandoff",
]
