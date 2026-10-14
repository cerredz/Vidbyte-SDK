"""FILE: vidbyte/tools/builtins/prebuilt/seeded_random.py

PURPOSE: Defines SeededRandomToolFunctions, the six prebuilt tools that draw reproducible randomness from a seed: integers in a range, a shuffled list, a sample without replacement, weighted picks with replacement, dice rolls from tabletop notation, and version-4 UUIDs.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the SEEDED_RANDOM category is chosen. Builds on PrebuiltToolSupport in _support.py for paired lists, weights, and the argument error.
ARCHITECTURE NOTE: Every tool builds its own random.Random(seed) for the call and makes exactly the generator calls its Appendix A.6 row documents, in that order, so a caller can replay a result with the standard library alone. The global generator is never touched, so no tool changes or depends on the interpreter's random state.
FUNCTION INVENTORY: seeded_random_integers, seeded_shuffle_list, seeded_sample_list, seeded_weighted_choice, roll_dice_notation, and generate_seeded_uuid4 are the tools; _parse_dice_notation reads and bounds the dice count, sides, and modifier; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new seeded tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.6, and its entry in tool_functions, and documents the exact generator calls it makes. Changing the order or kind of generator calls changes every result for every seed, so it needs a spec change first.
WHAT NOT TO DO IN THIS FILE: 1. Do not call the module-level random functions or reseed the global generator; build a random.Random(seed) per call. 2. Do not use the secrets module or uuid.uuid4, because results must repeat for the same seed. 3. Do not describe these results as secure; anyone who knows the seed can predict them.
KNOWN EDGE CASES: Python guarantees the same sequence only for random() itself, so randint, sample, shuffle, and choices may give different results on another Python minor version (EC-24). A unique draw from a range of up to two quadrillion integers samples the range lazily, without building it. Dice notation counts only ASCII digits, so other Unicode digits make the text invalid.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.6, section 9.2 items 2 and 13, EC-24); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_statistics.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import random
import re
import uuid
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_DICE,
    PREBUILT_MAX_DICE_MODIFIER,
    PREBUILT_MAX_DIE_SIDES,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_RANDOM_MAGNITUDE,
    PREBUILT_MAX_RANDOM_PICKS,
    PREBUILT_MAX_SEED,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_DICE_NOTATION = re.compile(r"^\s*([0-9]*)\s*[dD]\s*([0-9]+)\s*(?:([+-])\s*([0-9]+))?\s*$")
_DEFAULT_DICE_COUNT = 1
_MIN_DIE_SIDES = 2
_UUID_BITS = 128

_SEED_DESCRIPTION = "The seed that fixes the random sequence, as a whole number from zero to the largest signed 64-bit integer. The same seed and arguments give the same result every time on the same Python minor version. Results may differ between Python versions, because Python only guarantees its basic generator sequence. A seed is not a secret, so the result gives no security."
_ITEMS_DESCRIPTION = "The text items to work with, given as a JSON array of strings. Duplicate items stay separate entries. The list may hold at most ten thousand items, each at most ten thousand characters. Items are returned exactly as given, without trimming or case changes."


class SeededRandomToolFunctions:
    """The seeded_random category: reproducible draws, shuffles, samples, weighted picks, dice, and UUIDs from a seed."""

    @staticmethod
    def seeded_random_integers(
        seed: Annotated[int, Field(description=_SEED_DESCRIPTION, ge=0, le=PREBUILT_MAX_SEED)],
        count: Annotated[int, Field(description="How many numbers to draw. The value must be between 1 and 1,000. With unique set, the range from minimum to maximum must hold at least this many whole numbers. A larger count than that fails with an error naming count.", ge=1, le=PREBUILT_MAX_RANDOM_PICKS)],
        minimum: Annotated[int, Field(description="The smallest number that may be drawn, included in the range. Its magnitude must be at most one quadrillion. It must not be greater than maximum. Negative values are allowed.", ge=-PREBUILT_MAX_RANDOM_MAGNITUDE, le=PREBUILT_MAX_RANDOM_MAGNITUDE)],
        maximum: Annotated[int, Field(description="The largest number that may be drawn, included in the range. Its magnitude must be at most one quadrillion. A maximum below minimum fails with an error naming maximum. Negative values are allowed.", ge=-PREBUILT_MAX_RANDOM_MAGNITUDE, le=PREBUILT_MAX_RANDOM_MAGNITUDE)],
        unique: Annotated[bool, Field(description="Whether every drawn number must be different. When true, the numbers are drawn without replacement from the range. When false, each number is drawn independently and repeats are possible. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Draw a reproducible list of random whole numbers between a minimum and a maximum, both included, from a seed. Use it when a task needs random integers that can be regenerated exactly, such as test data or a draw that anyone can replay. Without unique each number is drawn independently, and with unique the numbers are distinct and drawn without replacement. Results repeat for the same arguments on the same Python minor version but may differ between versions, and they are not suitable for security. A minimum above the maximum fails naming maximum, and a unique draw from a range with fewer than count numbers fails naming count."""
        # Check the range before drawing anything.
        if minimum > maximum:
            raise PrebuiltToolSupport.argument_error("maximum", "it is below minimum", "a maximum at least as large as minimum")
        rng = random.Random(seed)

        # Draw distinct numbers from the range without building it, or
        # draw each number independently.
        if unique:
            if maximum - minimum + 1 < count:
                problem = f"the range from minimum to maximum holds {maximum - minimum + 1} whole numbers, fewer than count"
                raise PrebuiltToolSupport.argument_error("count", problem, "a count no larger than the size of the range")
            return {"values": rng.sample(range(minimum, maximum + 1), count)}
        return {"values": [rng.randint(minimum, maximum) for _ in range(count)]}

    @staticmethod
    def seeded_shuffle_list(
        items: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description=_ITEMS_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)],
        seed: Annotated[int, Field(description=_SEED_DESCRIPTION, ge=0, le=PREBUILT_MAX_SEED)],
    ) -> PrebuiltToolOutput:
        """Shuffle a list of text items into a reproducible random order from a seed. Use it to randomize an order in a way that anyone can replay exactly with the same seed. Every item appears exactly once in the result, duplicates included, and an empty list gives an empty list. Results repeat on the same Python minor version but may differ between versions, they are not suitable for security, and the tool has no failure case beyond the list caps."""
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        return {"items": shuffled}

    @staticmethod
    def seeded_sample_list(
        items: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description=_ITEMS_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)],
        size: Annotated[int, Field(description="How many items to pick. The value must be between 0 and 10,000. A size of zero gives empty lists. A size larger than the number of items fails with an error naming size.", ge=0, le=PREBUILT_MAX_LIST_ITEMS)],
        seed: Annotated[int, Field(description=_SEED_DESCRIPTION, ge=0, le=PREBUILT_MAX_SEED)],
    ) -> PrebuiltToolOutput:
        """Pick a reproducible random sample of items from a list without replacement, from a seed, with the 0-based positions the items came from. Use it to choose a subset fairly in a way that anyone can replay with the same seed. The sample is in the order drawn, each position is picked at most once, and duplicate items count as separate positions. A size larger than the list fails with an error naming size, and results may differ between Python versions."""
        if size > len(items):
            raise PrebuiltToolSupport.argument_error("size", f"the list holds only {len(items)} items", "a size no larger than the number of items")
        indices = random.Random(seed).sample(range(len(items)), size)
        return {"items": [items[index] for index in indices], "indices": indices}

    @staticmethod
    def seeded_weighted_choice(
        items: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description="The items to pick from, given as a JSON array of strings. Each item pairs with the weight at the same index. The list must hold at least one item and at most ten thousand, each at most ten thousand characters. Items are returned exactly as given.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        weights: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The weight of each item, given as a JSON array of finite numbers in the same order as items. An item's chance on each pick is its weight divided by the total. Weights must be zero or more, and at least one must be above zero. A list of a different length or any other weights fails with an error naming weights.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        seed: Annotated[int, Field(description=_SEED_DESCRIPTION, ge=0, le=PREBUILT_MAX_SEED)],
        picks: Annotated[int, Field(description="How many picks to make, each independent of the others. The value must be between 1 and 1,000. The same item can appear in several picks. The default is one pick.", ge=1, le=PREBUILT_MAX_RANDOM_PICKS)] = 1,
    ) -> PrebuiltToolOutput:
        """Pick items at random with replacement, where each item's chance is proportional to its weight, reproducibly from a seed. Use it for weighted draws in simulations or assignments that must be replayable. The same item may be picked many times, and the picks come from the choices method of a Python generator given these weights. Results repeat on the same Python minor version but may differ between versions, and they are not suitable for security. A weights list of a different length, a negative weight, a zero total, or a total beyond the floating-point range fails with an error naming weights."""
        # Check that every item has a weight and that the weights can
        # form a distribution.
        PrebuiltToolSupport.paired_values(items, weights, "weights")
        PrebuiltToolSupport.weight_total(weights, "weights")

        # Draw the picks; choices refuses a running total of weights
        # that overflows to infinity.
        try:
            picked = random.Random(seed).choices(items, weights=weights, k=picks)
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("weights", "the total of the weights exceeds the floating-point range", "weights whose total is a finite number") from exc
        return {"picks": picked}

    @staticmethod
    def roll_dice_notation(
        notation: Annotated[str, Field(description="The dice to roll in standard notation: an optional count, the letter d in either case, the number of sides, and an optional plus or minus modifier. The count defaults to one die when left out. Spaces may appear around each part. Text that does not follow this form, or numbers outside the allowed ranges, fail with an error naming notation.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        seed: Annotated[int, Field(description=_SEED_DESCRIPTION, ge=0, le=PREBUILT_MAX_SEED)],
    ) -> PrebuiltToolOutput:
        """Roll dice written in standard tabletop notation, reproducibly from a seed, and return each roll, the modifier, and the total. Use it for games or simulations that need dice results anyone can replay with the same seed. The notation is an optional dice count, the letter d, the number of sides, and an optional plus or minus modifier, with spaces allowed between the parts. The count must be 1 to 1,000, the sides 2 to 1,000, and the modifier at most one million in size, and any other text fails with an error naming notation."""
        dice, sides, modifier = SeededRandomToolFunctions._parse_dice_notation(notation)
        rng = random.Random(seed)
        rolls = [rng.randint(1, sides) for _ in range(dice)]
        return {"rolls": rolls, "modifier": modifier, "total": sum(rolls) + modifier}

    @staticmethod
    def generate_seeded_uuid4(
        seed: Annotated[int, Field(description=_SEED_DESCRIPTION, ge=0, le=PREBUILT_MAX_SEED)],
        count: Annotated[int, Field(description="How many UUIDs to generate. The value must be between 1 and 1,000. Each UUID continues the same seeded sequence. The default is one UUID.", ge=1, le=PREBUILT_MAX_RANDOM_PICKS)] = 1,
    ) -> PrebuiltToolOutput:
        """Generate reproducible version-4 UUIDs from a seed, as lowercase hyphenated text. Use it for stable test fixtures or deterministic identifiers that must be regenerated exactly. Each UUID takes its random bits from a generator seeded with the given seed, so anyone who knows the seed can predict every UUID. These are not secret identifiers and must never serve as passwords, keys, or session identifiers, and results may differ between Python versions."""
        rng = random.Random(seed)
        return {"uuids": [str(uuid.UUID(int=rng.getrandbits(_UUID_BITS), version=4)) for _ in range(count)]}

    @staticmethod
    def _parse_dice_notation(notation: str) -> tuple[int, int, int]:
        """Read the dice count, sides, and signed modifier from dice notation, refusing any out of range."""
        expected = f"dice notation with 1 to {PREBUILT_MAX_DICE} dice of {_MIN_DIE_SIDES} to {PREBUILT_MAX_DIE_SIDES} sides and a modifier of at most {PREBUILT_MAX_DICE_MODIFIER} in size"
        parts = _DICE_NOTATION.match(notation)
        if parts is None:
            raise PrebuiltToolSupport.argument_error("notation", "the text is not dice notation", expected)
        dice = int(parts[1]) if parts[1] else _DEFAULT_DICE_COUNT
        sides = int(parts[2])
        modifier = int(parts[4]) if parts[4] else 0
        if not _DEFAULT_DICE_COUNT <= dice <= PREBUILT_MAX_DICE:
            raise PrebuiltToolSupport.argument_error("notation", "the number of dice is out of range", expected)
        if not _MIN_DIE_SIDES <= sides <= PREBUILT_MAX_DIE_SIDES:
            raise PrebuiltToolSupport.argument_error("notation", "the number of sides is out of range", expected)
        if modifier > PREBUILT_MAX_DICE_MODIFIER:
            raise PrebuiltToolSupport.argument_error("notation", "the modifier is out of range", expected)
        return dice, sides, -modifier if parts[3] == "-" else modifier

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.seeded_random_integers,
            cls.seeded_shuffle_list,
            cls.seeded_sample_list,
            cls.seeded_weighted_choice,
            cls.roll_dice_notation,
            cls.generate_seeded_uuid4,
        )


__all__ = ["SeededRandomToolFunctions"]
