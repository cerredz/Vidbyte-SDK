"""FILE: vidbyte/harnesses/native/compose/texts.py

PURPOSE: Builds every prompt compose sends: ComposeTexts loads the 22 prompt files and renders a template into segments that keep each spliced value apart from the fixed text around it, and PromptFitter checks before any I/O that the longest form of a prompt fits its receiving step, then at send time removes NULs and bound keys from the spliced values and cuts them to a fair share when the whole prompt is too long.
ROLE IN CODEBASE: Used by JsonAnswers (answers.py) and by every composite (chain.py, verify.py, handoff.py, stages.py, ensemble.py, selection.py) for each prompt they send.
ARCHITECTURE NOTE: The prompt files live in the prompts folder next to this module and are read as package resources in UTF-8, off the event loop, once per process; each is checked with RecordFieldValidator.require_template against its COMPOSE_PROMPT_FIELDS entry and kept stripped (spec D-9, D-10, INV-20). render splits a template with string.Formatter, the parser str.format_map uses, so the joined segments are exactly what format_map would give while a value is never read as a template (INV-17). A segment is a PromptSegment record of text and spliced: fixed text is the caller's prompt, templates, schema texts, counted numbers and the prompt files; spliced text is model output or workspace content. Prompt fit follows spec INV-18 and D-19: check counts each spliced value as its longest truncation note, so at send time the share search always has a fitting floor; fit measures characters, and for Grok and Muse on win32 also command-line units.
FUNCTION INVENTORY: ComposeTexts.load reads and checks one prompt file; render fills a template into segments; spliced and fixed make one value a spliced or a fixed segment; join puts prompts one after another; opening builds an ensemble role's first turn, its system text then its turn, or fork_turn around both for an unanchored fork. PromptFitter.check refuses a prompt whose longest form does not fit; fit is the narrated main function of the send-time scrub and cut; _caps, _fits, _scrub, _sizes and _render are its leaves.
COMMON MODIFICATION PATTERNS: A new prompt file needs its ComposePrompt member and COMPOSE_PROMPT_FIELDS entry, and nothing here. A new spliced value is passed to render through spliced, so the scrub and the cut reach it.
WHAT NOT TO DO IN THIS FILE: 1. Do not hold prompt prose here; every sentence to a model comes from a prompt file (INV-20). 2. Do not scrub with HarnessRedactor; it rewrites credential-like lines inside diffs, so keys are replaced as exact text (D-28). 3. Do not cut a fixed segment; the caller's prompt, templates and schemas are sent whole or refused up front. 4. Do not read a prompt file at import time.
KNOWN EDGE CASES: A larger share never makes the prompt shorter, so the bisection finds the largest share that fits. A value no longer than its own note stays whole, and a long value at share 0 becomes its note alone, which check reserved room for, so no spliced value is sent blank in place of its content. The omitted count is the value's length after NUL removal and key replacement minus the kept prefix. A backslash run at a value's edge that meets a quote in the fixed text is counted only in the whole-prompt check, which is exact.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/test_harness_compose_prompts.py, tests/features/harness_compose/test_harness_compose_chain.py, tests/features/harness_compose/test_harness_compose_ensemble.py, tests/features/harness_compose/test_harness_compose_keys.py
"""

from __future__ import annotations

import asyncio
import importlib.resources
import string
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import ClassVar

from vidbyte.lib.constants import native_compose, native_threads
from vidbyte.lib.dataclasses.native_compose import PromptSegment, ThreadStep
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.native_compose import ComposeField, ComposePrompt
from vidbyte.lib.enums.native_threads import NativeHarness
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.secret_text import SecretText


class ComposeTexts:
    """The 22 prompt files, each read once and checked, and templates rendered into fixed and spliced segments."""

    _texts: ClassVar[dict[ComposePrompt, str]] = {}

    @staticmethod
    async def load(prompt: ComposePrompt) -> str:
        """The stripped text of one prompt file, read off the event loop on first use and checked against its fields."""
        text = ComposeTexts._texts.get(prompt)
        if text is None:
            resource = importlib.resources.files(str(__package__)).joinpath(native_compose.COMPOSE_PROMPTS_FOLDER).joinpath(prompt.value + native_compose.COMPOSE_PROMPT_SUFFIX)
            raw = await asyncio.to_thread(resource.read_text, encoding=native_compose.COMPOSE_PROMPT_ENCODING)
            fields = native_compose.COMPOSE_PROMPT_FIELDS[prompt]
            text = RecordFieldValidator.require_template(raw, prompt.value, fields=fields, required=fields).strip()
            ComposeTexts._texts[prompt] = text
        return text

    @staticmethod
    def render(template: str, values: Mapping[ComposeField, str | tuple[PromptSegment, ...]]) -> tuple[PromptSegment, ...]:
        """template with every placeholder filled: a str value is fixed text, and a segment tuple (a spliced value or another rendered prompt) goes in as it is."""
        segments: list[PromptSegment] = []
        for literal, name, _spec, _conversion in string.Formatter().parse(template):
            if literal:
                segments.append(PromptSegment(text=literal, spliced=False))
            if name is None:
                continue
            value = values[ComposeField(name)]
            segments.extend((PromptSegment(text=value, spliced=False),) if isinstance(value, str) else value)
        return tuple(segments)

    @staticmethod
    def spliced(value: str) -> tuple[PromptSegment, ...]:
        """value as one spliced segment: model output or workspace content, which fit scrubs and may cut."""
        return (PromptSegment(text=value, spliced=True),)

    @staticmethod
    def fixed(value: str) -> tuple[PromptSegment, ...]:
        """value as one fixed segment: the caller's prompt or a system text, sent whole and never scrubbed or cut."""
        return (PromptSegment(text=value, spliced=False),)

    @staticmethod
    def join(parts: Sequence[Sequence[PromptSegment]]) -> tuple[PromptSegment, ...]:
        """parts one after another, with the prompt separator between each two."""
        segments: list[PromptSegment] = []
        for index, part in enumerate(parts):
            if index:
                segments.append(PromptSegment(text=native_compose.COMPOSE_PROMPT_SEPARATOR, spliced=False))
            segments.extend(part)
        return tuple(segments)

    @staticmethod
    async def opening(system: Sequence[PromptSegment], turn: Sequence[PromptSegment], *, fork: bool) -> tuple[PromptSegment, ...]:
        """An ensemble role's first turn: its system text, then its turn; for an unanchored fork, which opens on the planner's thread, fork_turn holding both (spec INV-23, D-3)."""
        if not fork:
            return ComposeTexts.join((system, turn))
        wrapper = await ComposeTexts.load(ComposePrompt.FORK_TURN)
        return ComposeTexts.render(wrapper, {ComposeField.INSTRUCTIONS: tuple(system), ComposeField.TURN: tuple(turn)})


class PromptFitter:
    """Makes every prompt fit its receiving step: an up-front check of its longest form, and at send time a scrub and a fair cut of its spliced values."""

    @staticmethod
    async def check(frame: Sequence[PromptSegment], step: ThreadStep, *, argument: str, receiver: str) -> None:
        """Refuse, naming argument, a prompt for step whose longest form, with each spliced value as its longest truncation note, is too long."""
        note = await ComposeTexts.load(ComposePrompt.TRUNCATION_NOTE)
        longest = note.format_map({ComposeField.OMITTED: sys.maxsize})
        prompt = "".join(longest if segment.spliced else segment.text for segment in frame)
        chars_cap, units_cap = PromptFitter._caps(step)
        needed, units, cap = len(prompt), native_compose.COMPOSE_CHARACTER_UNITS, chars_cap
        if needed <= chars_cap and units_cap is not None:
            needed, units, cap = RecordFieldValidator.command_line_units(prompt), native_compose.COMPOSE_COMMAND_LINE_UNITS, units_cap
        if needed > cap:
            raise ConfigurationError(native_compose.COMPOSE_PROMPT_TOO_LONG.format(argument=argument, receiver=receiver, needed=needed, units=units, cap=cap), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})

    @staticmethod
    async def fit(frame: Sequence[PromptSegment], step: ThreadStep, keys: Iterable[str]) -> str:
        """The prompt step receives: spliced values without NULs or bound keys, each cut to the largest fair share when the whole prompt is too long."""
        # @intent spliced-values-never-carry-a-key-or-break-a-step
        # A model can print a key and a writer can save one, so every key
        # bound in the composite leaves spliced text before it reaches
        # another vendor's argv; and a step refuses a prompt past its
        # cap, so a long answer is cut instead of failing the step.
        note = await ComposeTexts.load(ComposePrompt.TRUNCATION_NOTE)
        caps = PromptFitter._caps(step)

        # Take NULs and every bound key out of what a model or the
        # workspace wrote; the caller's own texts stay as given.
        bound = tuple(keys)
        segments = [PromptSegment(text=PromptFitter._scrub(segment.text, bound), spliced=True) if segment.spliced else segment for segment in frame]
        prompt = "".join(segment.text for segment in segments)
        if PromptFitter._fits(prompt, caps):
            return prompt

        # Measure each spliced value prefix by prefix, in characters, or
        # in command-line units when the step takes its prompt on a
        # Windows command line, and measure the note that ends a cut.
        windows = caps[1] is not None
        sizes = [PromptFitter._sizes(segment.text, windows) if segment.spliced else None for segment in segments]
        note_size = PromptFitter._sizes(note.format_map({ComposeField.OMITTED: ""}), windows)[-1]
        separator_size = PromptFitter._sizes(native_compose.COMPOSE_PROMPT_SEPARATOR, windows)[-1]

        # Find by bisection the largest share each spliced value may
        # take. At share 0 every long value is its note alone, which the
        # up-front check made room for, so that floor always fits.
        best = PromptFitter._render(segments, sizes, 0, note, note_size, separator_size)
        low, high = 0, max((size[-1] for size in sizes if size is not None), default=0)
        while low < high:
            share = (low + high + 1) >> 1
            candidate = PromptFitter._render(segments, sizes, share, note, note_size, separator_size)
            if PromptFitter._fits(candidate, caps):
                low, best = share, candidate
            else:
                high = share - 1
        return best

    @staticmethod
    def _caps(step: ThreadStep) -> tuple[int, int | None]:
        # opencode reads its prompt from stdin; Grok and Muse take it on
        # argv, which on win32 also has a command-line unit ceiling.
        if step.harness is NativeHarness.OPENCODE:
            return native_threads.NATIVE_PROMPT_MAX_CHARS, None
        if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM:
            return native_threads.NATIVE_ARGV_PROMPT_MAX_CHARS, native_threads.NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS
        return native_threads.NATIVE_ARGV_PROMPT_MAX_CHARS, None

    @staticmethod
    def _fits(prompt: str, caps: tuple[int, int | None]) -> bool:
        # What the step's own request record accepts: non-blank, no NUL,
        # within the character cap and, when there is one, the units.
        chars_cap, units_cap = caps
        if not RecordFieldValidator.accepts_text(prompt, max_chars=chars_cap, pattern=native_threads.NATIVE_PROMPT_PATTERN):
            return False
        return units_cap is None or RecordFieldValidator.command_line_units(prompt) <= units_cap

    @staticmethod
    def _scrub(text: str, bound: Sequence[str]) -> str:
        # NULs go first, so a key split by one is whole again; then each
        # key, longest first, becomes COMPOSE_REDACTED_KEY.
        return SecretText.replace_all(text.replace(native_compose.COMPOSE_NUL, ""), bound, native_compose.COMPOSE_REDACTED_KEY)

    @staticmethod
    def _sizes(text: str, windows: bool) -> Sequence[int]:
        # The size of every prefix of text, from the empty one to the
        # whole: its characters, or the UTF-16 units it takes inside a
        # quoted Windows argument when a space follows it. A quote is
        # sent as a backslash and a quote and doubles the backslashes
        # before it, and a character past U+FFFF is a surrogate pair.
        if not windows:
            return range(len(text) + 1)
        escaped_quote = len(native_compose.COMPOSE_BACKSLASH + native_compose.COMPOSE_QUOTE)
        sizes = [0]
        backslashes = 0
        for character in text:
            if character == native_compose.COMPOSE_BACKSLASH:
                cost, backslashes = 1, backslashes + 1
            elif character == native_compose.COMPOSE_QUOTE:
                cost, backslashes = escaped_quote + backslashes, 0
            else:
                cost, backslashes = 1 + (ord(character) > native_compose.COMPOSE_BMP_MAX_CODE_POINT), 0
            sizes.append(sizes[-1] + cost)
        return sizes

    @staticmethod
    def _render(segments: Sequence[PromptSegment], sizes: Sequence[Sequence[int] | None], share: int, note: str, note_size: int, separator_size: int) -> str:
        # The prompt with each spliced value that is longer than share
        # and than its own note cut to its longest prefix that, with the
        # separator and its note, fits share, or to the note alone.
        parts: list[str] = []
        for segment, size in zip(segments, sizes, strict=True):
            text = segment.text
            length = len(text)
            if size is None or size[-1] <= share or size[-1] <= note_size + len(str(length)):
                parts.append(text)
                continue
            low, high = 0, length - 1
            while low < high:
                middle = (low + high + 1) >> 1
                if size[middle] + separator_size + note_size + len(str(length - middle)) <= share:
                    low = middle
                else:
                    high = middle - 1
            cut = note.format_map({ComposeField.OMITTED: length - low})
            parts.append(text[:low] + native_compose.COMPOSE_PROMPT_SEPARATOR + cut if low else cut)
        return "".join(parts)


__all__ = ["ComposeTexts", "PromptFitter"]
