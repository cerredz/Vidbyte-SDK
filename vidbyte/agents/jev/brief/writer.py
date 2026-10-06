"""FILE: vidbyte/agents/jev/brief/writer.py

PURPOSE: Owns the run-brief event window, structured note verification, and the tool-free writer agent that proposes note deltas.
ROLE IN CODEBASE: JevRunBriefKeeper supplies the request, previous brief, iteration, and main-agent history; this module returns a verified complete brief or a precise rejection.
ARCHITECTURE NOTE: The writer returns only new notes. Code owns the clipped original goal, verifies every note against a fresh numbered event, appends verified notes, and retains only the newest bounded set.
COMMON MODIFICATION PATTERNS: Keep event numbering aligned with JevRunEventLog, keep quote checks against full original event text, and keep the retry on this same writer history.
KNOWN EDGE CASES: An empty delta is valid and advances the event pointer. An outage or output-schema failure returns None; a rejected first delta is shown to the writer for one retry.
TESTS: tests/test_jev_run_brief.py.
RELATED DOCS: skills/jev-agent/SKILL.md and vidbyte/agents/jev/README.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import (
    JEV_EVENT_ID_PREFIX,
    JEV_EVENT_LOG_FIRST_ID,
    JEV_RUN_BRIEF_CLIP_HEAD_SHARE,
    JEV_RUN_BRIEF_EVENT_MAX_CHARS,
    JEV_RUN_BRIEF_GOAL_MAX_CHARS,
    JEV_RUN_BRIEF_NOTES_MAX,
    JEV_RUN_BRIEF_WINDOW_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefAppendPayload,
    JevRunBriefNote,
    JevRunBriefVerification,
    JevRunBriefWindow,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.prompts.catalog import Prompts


class JevRunBriefWriter(BaseAgent):
    """A tool-free agent that proposes append-only notes and verifies them against the recorded run."""

    def __init__(self, settings: JevAgentSettings, brief: JevRunBriefSettings) -> None:
        # The separate writer may use a cheaper model; a provider override requires its own model and key.
        # @intent writer-provider-fallback
        # The writer follows the main provider/key unless configured independently, preserving a valid model/key pair.
        own_provider = brief.provider is not None
        super().__init__(
            name=f"{settings.name}-run-brief",
            system_prompt=Prompts().get(Prompt.JEV_RUN_BRIEF_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=brief.max_iterations, max_tokens=brief.max_tokens),
            api_key=brief.api_key if own_provider else (brief.api_key or settings.api_key),
            provider=brief.provider if own_provider else settings.provider,
            model_name=brief.model_name or settings.model_name,
            temperature=brief.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=JevRunBriefAppendPayload,
        )
        self._update_prompt = Prompts().get(Prompt.JEV_RUN_BRIEF_UPDATE_PROMPT)

    @staticmethod
    def window(
        request: str,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
        *,
        after_event: int,
    ) -> JevRunBriefWindow | None:
        """Build a bounded window of fresh events while retaining their full text for quote verification."""
        # @intent event-window-keeps-verification-source
        # Display clipping limits model input, while full shown event bodies remain available for exact quote checks.
        log = JevRunEventLog.from_run(request, responses, calls)
        fresh: list[tuple[int, str]] = []
        for line in log.lines:
            identifier, separator, text = line.partition(" ")
            if not separator or not identifier.startswith(JEV_EVENT_ID_PREFIX):
                continue
            digits = identifier.removeprefix(JEV_EVENT_ID_PREFIX)
            if not digits.isdigit():
                continue
            number = int(digits)
            # E1 is the original request and the goal is already stored directly from it.
            if number > after_event and number != JEV_EVENT_LOG_FIRST_ID:
                fresh.append((number, text))
        if not fresh:
            return None

        rendered_events = tuple(
            (number, full_text, f"{JEV_EVENT_ID_PREFIX}{number} {JevRunBriefWriter._clip(full_text, JEV_RUN_BRIEF_EVENT_MAX_CHARS)}")
            for number, full_text in fresh
        )
        all_events_size = sum(len(item[2]) for item in rendered_events) + max(len(rendered_events) - 1, 0)
        if all_events_size <= JEV_RUN_BRIEF_WINDOW_MAX_CHARS:
            shown = rendered_events
        else:
            shown_reversed: list[tuple[int, str, str]] = []
            rendered_size = 0
            for number, full_text, rendered in reversed(rendered_events):
                separator_size = 1 if shown_reversed else 0
                # Reserve room for the omitted-events marker while preserving the newest events first.
                reserve = len(JevRunBriefWriter._omitted_note(len(fresh))) + 1
                if rendered_size + separator_size + len(rendered) + reserve > JEV_RUN_BRIEF_WINDOW_MAX_CHARS:
                    break
                shown_reversed.append((number, full_text, rendered))
                rendered_size += separator_size + len(rendered)
            shown = tuple(reversed(shown_reversed))
        omitted = len(fresh) - len(shown)
        lines = ([JevRunBriefWriter._omitted_note(omitted)] if omitted else []) + [item[2] for item in shown]
        return JevRunBriefWindow(
            first_event=fresh[0][0],
            last_event=fresh[-1][0],
            text="\n".join(lines),
            omitted=omitted,
            full_events=tuple((number, text) for number, text, _ in shown),
        )

    async def write(
        self,
        request: str,
        previous: JevRunBrief | None,
        window: JevRunBriefWindow,
        *,
        iteration: int,
    ) -> JevRunBriefVerification | None:
        """Generate a note delta, verify it, and retry one rejected delta on the same writer history."""
        # @intent invalid-note-delta-retries-once
        # Keep one correction attempt with the original update context; outage and schema failures preserve prior state.
        self.history.clear()
        prompt = self.prompt(request, previous, window)
        try:
            reply = await self.arun(AgentInput(prompt=prompt))
        except VidbyteSdkError:
            return None
        delta = reply.structured if isinstance(reply.structured, JevRunBriefAppendPayload) else None
        if delta is None:
            return None

        verification = self.verify(delta, request, previous, window, iteration=iteration)
        if verification.brief is not None:
            return verification

        # Keep this writer's history so the retry can correct the rejected response in context.
        retry_prompt = f"{prompt}\n\n<verification_error>{verification.error}</verification_error>\nCorrect your previous note delta using only the fresh events shown above. Return only the append payload."
        try:
            retry = await self.arun(AgentInput(prompt=retry_prompt))
        except VidbyteSdkError:
            return None
        retry_delta = retry.structured if isinstance(retry.structured, JevRunBriefAppendPayload) else None
        if retry_delta is None:
            return None
        return self.verify(retry_delta, request, previous, window, iteration=iteration)

    def prompt(self, request: str, previous: JevRunBrief | None, window: JevRunBriefWindow) -> str:
        """Render the original request, stored aggregate, and bounded new events for one append update."""
        # @intent update-prompt-carries-fresh-window
        # Every retry can reconstruct the original request and evidence even when agent history retains only its reply.
        update = self._update_prompt.format(
            request=self._clip(request, JEV_RUN_BRIEF_GOAL_MAX_CHARS),
            previous_brief="none" if previous is None else previous.render(),
            first_event=f"{JEV_EVENT_ID_PREFIX}{window.first_event}",
            last_event=f"{JEV_EVENT_ID_PREFIX}{window.last_event}",
            events=window.text,
        )
        return update

    @staticmethod
    def verify(
        delta: JevRunBriefAppendPayload,
        request: str,
        previous: JevRunBrief | None,
        window: JevRunBriefWindow,
        *,
        iteration: int,
    ) -> JevRunBriefVerification:
        """Return a complete brief with verified new notes, or a precise error for the writer to correct."""
        # @intent notes-require-cited-source-text
        # Only fresh event passages can enter memory, keeping the aggregate grounded in the recorded run.
        event_text = {number: text for number, text in window.full_events}
        existing = tuple() if previous is None else previous.notes
        seen = {(note.event, JevRunBriefWriter._normalize(note.text)) for note in existing}
        appended: list[JevRunBriefNote] = []
        for index, candidate in enumerate(delta.notes, start=1):
            event_number = JevRunBriefWriter._event_number(candidate.event)
            source = None if event_number is None else event_text.get(event_number)
            if source is None:
                return JevRunBriefVerification(
                    brief=None,
                    error=f"Note {index} cites {candidate.event}, which is not a fresh full event shown in this update. Cite an event id from the new-events window.",
                )
            normalized = JevRunBriefWriter._normalize(candidate.text)
            if not normalized or normalized not in JevRunBriefWriter._normalize(source):
                return JevRunBriefVerification(
                    brief=None,
                    error=f"Note {index} text is not present in full event {candidate.event} after whitespace normalization. Copy a verbatim passage from that event.",
                )
            key = (candidate.event, normalized)
            if key in seen:
                return JevRunBriefVerification(
                    brief=None,
                    error=f"Note {index} duplicates an existing note from {candidate.event}. Omit duplicate notes.",
                )
            seen.add(key)
            appended.append(JevRunBriefNote(event=candidate.event, text=candidate.text))

        goal = previous.goal if previous is not None else JevRunBriefWriter._clip(request, JEV_RUN_BRIEF_GOAL_MAX_CHARS)
        notes = (existing + tuple(appended))[-JEV_RUN_BRIEF_NOTES_MAX:]
        try:
            brief = JevRunBrief(goal=goal, notes=notes, iteration=iteration, through_event=window.last_event)
        except ConfigurationError as exc:
            return JevRunBriefVerification(brief=None, error=f"The verified note delta could not be stored: {exc}")
        return JevRunBriefVerification(brief=brief)

    @staticmethod
    def _event_number(event: str) -> int | None:
        """Parse a numbered event id such as E14."""
        if not event.startswith(JEV_EVENT_ID_PREFIX):
            return None
        digits = event.removeprefix(JEV_EVENT_ID_PREFIX)
        return int(digits) if digits.isdigit() else None

    @staticmethod
    def _normalize(text: str) -> str:
        """Collapse whitespace so line wrapping alone does not invalidate an exact passage."""
        return " ".join(text.split())

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        """Keep a bounded head and tail when a request or event exceeds its input budget."""
        if len(text) <= limit:
            return text
        marker = " [...] "
        available = limit - len(marker)
        head = int(available * JEV_RUN_BRIEF_CLIP_HEAD_SHARE)
        tail = available - head
        return f"{text[:head]}{marker}{text[-tail:] if tail else ''}"

    @staticmethod
    def _omitted_note(count: int) -> str:
        return f"[{count} earlier new events were left out for length]"


__all__ = ["JevRunBriefWriter"]
