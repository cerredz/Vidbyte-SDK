"""FILE: tests/test_compaction_windows.py

PURPOSE: Proves items 2 and 4 of spec infinite-memory-context-economy on the shared compaction pieces: ToolOutputSlidingWindowCompaction's new tools scope (only named tools are counted and compacted) and TrimWithProviderBoundariesCompaction's new low_watermark_tokens (a stateless, quantized cut that moves about once per max - low tokens of growth), with every default equal to main.
ROLE IN CODEBASE: Root-level test of vidbyte/middleware/compaction/windows.py, the engine options that reach it, and the MessageHistoryCompactionMiddleware builders (spec section 13: items 2 and 4 prior art is tests/test_deterministic_compaction_middleware.py).
ARCHITECTURE NOTE: The oracles are written here from the spec's own definitions, not from the implementation: _main_trim is main's _trim_groups_to_tokens copied as it was at base 0f2aeb48, _quantized_trim is INV-4.2 written out, and _window is main's per-tool window with an optional scope. Token costs come from an injected counter (len, so one character is one token) so every boundary in the tests is exact. Seeded random histories give the property checks; nothing depends on the clock.
FUNCTION INVENTORY: ScopedWindowTests (INV-2.1..INV-2.5, AC-2.3, FR-2.1, EC-2.4); QuantizedTrimTests (AC-4.1..AC-4.3, INV-4.1..INV-4.3, EC-4.5, FR-4.1); ImportPathTests (INV-R.3, D-3). msg / call / result build ContextMessages; _groups, _cost, _main_trim, _quantized_trim, _window are the oracles; _random_history and _history_of build inputs.
COMMON MODIFICATION PATTERNS: Add a property case by adding a seed range or a size distribution to _random_history; keep the oracles as the spec defines them.
WHAT NOT TO DO IN THIS FILE: 1. Do not replace an oracle with a call into vidbyte.middleware.compaction; that would compare the code with itself. 2. Do not loosen equality to a subset check; INV-4.1 and INV-4.2 are exact.
KNOWN EDGE CASES: main's token trim can keep an older small group after skipping a newer large one, so its output is not always a suffix; test_without_a_low_watermark_the_trim_equals_main proves at least one random case exercises that. A system group bigger than max_tokens makes the budget negative, which drops every non-system group (EC-4.5).
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-2.x, INV-4.x), 6.2 (AC-2.1..AC-2.3, AC-4.1..AC-4.3), 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_compaction_windows.py -q
"""

from __future__ import annotations

import copy
import dataclasses
import math
import random
import unittest
from collections.abc import Sequence
from typing import Any

from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine
from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware

STRIP = CompactionMode.STRIP_TOOL_RESULT_BODIES
DEFAULT_PLACEHOLDER = "[older tool result cleared by compaction]"
SEARCH_SCOPE = ("grep", "read_lines", "search_memory")


def msg(role: str, content: str, kind: str = "message", **metadata: object) -> ContextMessage:
    return ContextMessage(role=role, content=content, kind=kind, metadata=metadata)


def call(name: str, content: str) -> ContextMessage:
    return msg("assistant", content, "tool_call", tool_name=name)


def result(name: str | None, content: str) -> ContextMessage:
    return msg("tool", content, "tool_result", **({"tool_name": name} if name is not None else {}))


def _groups(messages: Sequence[ContextMessage]) -> list[tuple[ContextMessage, ...]]:
    # A tool call plus every result right after it is one group; any other message is its own group (main's rule).
    groups: list[tuple[ContextMessage, ...]] = []
    index = 0
    while index < len(messages):
        end = index + 1
        if messages[index].kind == "tool_call":
            while end < len(messages) and messages[end].kind == "tool_result":
                end += 1
        groups.append(tuple(messages[index:end]))
        index = end
    return groups


def _cost(group: Sequence[ContextMessage]) -> int:
    # The tests inject token_counter=len, so a group costs its characters.
    return sum(len(message.content) for message in group)


def _main_trim(messages: Sequence[ContextMessage], max_tokens: int, max_messages: int | None = None) -> tuple[ContextMessage, ...]:
    # main's TrimWithProviderBoundariesCompaction.compact at 0f2aeb48, copied: count trim, then newest-first greedy token fit.
    groups = _groups(messages)
    if max_messages is not None:
        first_kept = max(0, len(messages) - max_messages)
        kept, offset = [], 0
        for group in groups:
            if offset + len(group) > first_kept:
                kept.append(group)
            offset += len(group)
        groups = kept
    keep = {index for index, group in enumerate(groups) if group[0].role == "system"}
    remaining = max_tokens - sum(_cost(groups[index]) for index in keep)
    for index in range(len(groups) - 1, -1, -1):
        if remaining >= 0 and index not in keep and _cost(groups[index]) <= remaining:
            keep.add(index)
            remaining -= _cost(groups[index])
    return tuple(message for index, group in enumerate(groups) if index in keep for message in group)


def _quantized_trim(messages: Sequence[ContextMessage], max_tokens: int, low: int) -> tuple[ContextMessage, ...]:
    # INV-4.2 written out: B = M - system tokens, N = non-system tokens, S = M - L; drop the shortest
    # prefix of non-system groups reaching ceil((N - B) / S) * S, or every one when none reaches it.
    groups = _groups(messages)
    system = [index for index, group in enumerate(groups) if group[0].role == "system"]
    others = [index for index, group in enumerate(groups) if group[0].role != "system"]
    budget = max_tokens - sum(_cost(groups[index]) for index in system)
    total = sum(_cost(groups[index]) for index in others)
    step = max_tokens - low
    dropped: set[int] = set()
    if total > budget:
        target = math.ceil((total - budget) / step) * step
        running = 0
        for index in others:
            dropped.add(index)
            running += _cost(groups[index])
            if running >= target:
                break
    return tuple(message for index, group in enumerate(groups) if index not in dropped for message in group)


def _window(messages: Sequence[ContextMessage], keep: int, placeholder: str, scope: Sequence[str] = ()) -> tuple[ContextMessage, ...]:
    # main's per-tool STRIP window, newest first; with a scope only those names are counted and compacted (INV-2.2).
    seen: dict[str, int] = {}
    output = list(messages)
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.kind != "tool_result":
            continue
        name = message.metadata.get("tool_name")
        if scope and name not in scope:
            continue
        key = str(name) if name is not None else "_unknown"
        count = seen.get(key, 0)
        seen[key] = count + 1
        if count >= keep:
            output[index] = dataclasses.replace(message, content=placeholder, metadata={**dict(message.metadata), "compaction": STRIP.value, "original_chars": len(message.content)})
    return tuple(output)


def _random_history(rng: random.Random, *, groups: int, max_size: int, system_sizes: Sequence[int] = ()) -> tuple[ContextMessage, ...]:
    # Leading system groups, then plain turns and tool groups with one to three results (parallel calls); every text is unique.
    messages: list[ContextMessage] = [msg("system", f"S{index}:" + "s" * max(0, size - 3)) for index, size in enumerate(system_sizes)]
    for number in range(groups):
        shape = rng.choice(("user", "assistant", "tool", "tool", "parallel"))
        size = rng.randint(1, max_size)
        label = f"{number:05d}"
        if shape in ("user", "assistant"):
            messages.append(msg(shape, label + "x" * max(0, size - len(label))))
            continue
        messages.append(call("read_lines", label + "c" * max(0, size // 3 - len(label))))
        for part in range(1 if shape == "tool" else rng.randint(2, 3)):
            messages.append(result("read_lines", f"{label}.{part}" + "r" * rng.randint(0, size)))
    return tuple(messages)


def _history_of(sizes: Sequence[int], start: int = 0) -> tuple[ContextMessage, ...]:
    # One plain turn per size, alternating roles, each text unique and exactly `size` characters (sizes are at least 7).
    return tuple(msg("user" if (start + offset) % 2 == 0 else "assistant", f"{start + offset:06d}:" + "x" * (size - 7)) for offset, size in enumerate(sizes))


def _sizes_summing_to(rng: random.Random, total: int, largest: int) -> list[int]:
    # Random group sizes in 7..largest that add up to exactly `total`.
    sizes: list[int] = []
    left = total
    while left > 0:
        size = min(left, rng.randint(7, largest))
        if 0 < left - size < 7:
            # Never leave a remainder too short to label; take it all when it is small, else leave exactly 7.
            size = left - 7 if left - 7 >= 7 else left
        sizes.append(size)
        left -= size
    return sizes


def _trim(**options: Any) -> Any:
    from vidbyte.middleware.compaction.windows import TrimWithProviderBoundariesCompaction

    return TrimWithProviderBoundariesCompaction(token_counter=len, **options)


def _context(provider_messages: Sequence[dict[str, Any]]) -> MiddlewareContext:
    return MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="agent", message="go", provider_messages=tuple(provider_messages))


async def _view(middleware: Any, provider_messages: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    decision = await middleware.before_model_call(_context(provider_messages))
    return tuple(decision.transform.provider_messages) if decision.transform is not None and decision.transform.provider_messages is not None else tuple(provider_messages)


def _lookup(name: str, key: str, output: str) -> list[dict[str, Any]]:
    # One OpenAI-chat call turn and its named result.
    tool_call = {"id": f"call_{key}", "type": "function", "function": {"name": name, "arguments": f'{{"key": "{key}"}}'}}
    return [{"role": "assistant", "content": None, "tool_calls": [tool_call]}, {"role": "tool", "tool_call_id": f"call_{key}", "name": name, "content": output}]


class ImportPathTests(unittest.TestCase):
    def test_both_strategies_live_in_windows_and_keep_their_public_import_path(self) -> None:
        # INV-R.3, D-3: the classes moved to the windows module and the package still exports the same objects.
        from vidbyte.middleware.compaction import ToolOutputSlidingWindowCompaction, TrimWithProviderBoundariesCompaction
        from vidbyte.middleware.compaction import windows

        self.assertIs(windows.ToolOutputSlidingWindowCompaction, ToolOutputSlidingWindowCompaction)
        self.assertIs(windows.TrimWithProviderBoundariesCompaction, TrimWithProviderBoundariesCompaction)
        self.assertEqual(set(windows.__all__), {"ToolOutputSlidingWindowCompaction", "TrimWithProviderBoundariesCompaction"})


class ScopedWindowTests(unittest.IsolatedAsyncioTestCase):
    def _mixed_history(self) -> tuple[ContextMessage, ...]:
        # Five greps, four read_lines, two search_memory, and one result of every unscoped tool, interleaved, plus a nameless result.
        history: list[ContextMessage] = [msg("user", "Compare the prices.")]
        unscoped = ("launch_subagent", "bash", "remember", "write_note", "edit_file", "drop_entry", "recall")
        for number in range(5):
            history += [call("grep", f"grep call {number}"), result("grep", f"GREP-OUTPUT-{number} " + "g" * 300)]
            if number < 4:
                history += [call("read_lines", f"read call {number}"), result("read_lines", f"READ-OUTPUT-{number} " + "r" * 300)]
            if number < 2:
                history += [call("search_memory", f"search call {number}"), result("search_memory", f"SEARCH-OUTPUT-{number}")]
        for name in unscoped:
            for number in range(5):
                history += [call(name, f"{name} call {number}"), result(name, f"{name.upper()}-OUTPUT-{number} " + "u" * 300)]
        history += [result(None, "NAMELESS-OUTPUT " + "n" * 300), msg("assistant", "Thinking about it.")]
        return tuple(history)

    async def test_without_a_scope_every_tools_older_outputs_are_compacted_as_on_main(self) -> None:
        # INV-2.1: tools=() (default or given) counts and compacts every tool, nameless results included, exactly as main does.
        from vidbyte.middleware.compaction.windows import ToolOutputSlidingWindowCompaction

        history = self._mixed_history()
        expected = _window(history, 3, "P")
        for strategy in (ToolOutputSlidingWindowCompaction(keep_recent=3, mode=STRIP, placeholder="P"), ToolOutputSlidingWindowCompaction(keep_recent=3, mode=STRIP, placeholder="P", tools=())):
            with self.subTest(tools=getattr(strategy, "tools", None)):
                self.assertEqual(await strategy.compact(history), expected)

    async def test_a_scope_compacts_only_the_named_tools_and_keeps_the_newest_per_tool(self) -> None:
        # INV-2.2, INV-2.3, INV-2.4, EC-2.4, AC-2.1 (strategy level): only grep's two oldest and read_lines' oldest are stripped.
        from vidbyte.middleware.compaction.windows import ToolOutputSlidingWindowCompaction

        history = self._mixed_history()
        after = await ToolOutputSlidingWindowCompaction(keep_recent=3, mode=STRIP, placeholder="MASKED", tools=SEARCH_SCOPE).compact(history)

        self.assertEqual(after, _window(history, 3, "MASKED", SEARCH_SCOPE))
        changed = [(before.content.split(" ")[0], now) for before, now in zip(history, after, strict=True) if before != now]
        self.assertEqual([label for label, _ in changed], ["GREP-OUTPUT-0", "READ-OUTPUT-0", "GREP-OUTPUT-1"])
        for label, now in changed:
            self.assertEqual(now.content, "MASKED")
            self.assertEqual(now.metadata["compaction"], STRIP.value)
            self.assertEqual(now.metadata["original_chars"], len(next(m for m in history if m.content.startswith(label + " ")).content))
        for before, now in zip(history, after, strict=True):
            if before.kind == "tool_call" or before.metadata.get("tool_name") not in SEARCH_SCOPE:
                self.assertEqual(now, before, "masking changed an unscoped result or a tool call")

    async def test_masking_is_a_pure_function_of_its_input(self) -> None:
        # INV-2.5, INV-0.1: the same history gives the same view twice, and the input history is not changed.
        from vidbyte.middleware.compaction.windows import ToolOutputSlidingWindowCompaction

        history = self._mixed_history()
        before = copy.deepcopy(history)
        strategy = ToolOutputSlidingWindowCompaction(keep_recent=3, mode=STRIP, placeholder="MASKED", tools=SEARCH_SCOPE)
        first = await strategy.compact(history)
        second = await ToolOutputSlidingWindowCompaction(keep_recent=3, mode=STRIP, placeholder="MASKED", tools=SEARCH_SCOPE).compact(history)
        self.assertEqual(first, second)
        self.assertEqual(await strategy.compact(history), first)
        self.assertEqual(history, before)

    async def test_a_blank_scope_name_is_refused_at_construction(self) -> None:
        # Section 8.5: a blank tool name in the scope is a ValueError, from the strategy and from the builder.
        from vidbyte.middleware.compaction.windows import ToolOutputSlidingWindowCompaction

        for tools in (("grep", ""), ("  ",), ("read_lines", "\t")):
            with self.subTest(tools=tools):
                with self.assertRaises(ValueError):
                    ToolOutputSlidingWindowCompaction(keep_recent=3, mode=STRIP, tools=tools)
                with self.assertRaises(ValueError):
                    MessageHistoryCompactionMiddleware.tool_output_sliding_window(3, STRIP, tools=tools)

    async def test_the_builder_forwards_the_placeholder_and_the_scope(self) -> None:
        # FR-2.1: the builder's keyword-only placeholder and tools reach the strategy through the engine.
        provider = [{"role": "user", "content": "go"}]
        for number in range(2):
            provider += _lookup("grep", f"g{number}", f"GREP-{number} " + "g" * 50)
            provider += _lookup("bash", f"b{number}", f"BASH-{number} " + "b" * 50)
        middleware = MessageHistoryCompactionMiddleware.tool_output_sliding_window(1, STRIP, placeholder="PLACEHOLDER-TEXT", tools=("grep",))
        view = await _view(middleware, provider)
        contents = [message["content"] for message in view if message["role"] == "tool"]
        self.assertEqual(contents, ["PLACEHOLDER-TEXT", provider[4]["content"], provider[6]["content"], provider[8]["content"]])
        self.assertEqual([m for m in view if m["role"] != "tool"], [m for m in provider if m["role"] != "tool"])

    async def test_the_builder_with_no_new_arguments_equals_main(self) -> None:
        # AC-2.3: tool_output_sliding_window() compacts every tool with main's defaults (keep 2, truncate at 600), and the
        # explicit defaults of the two new keywords change nothing.
        provider = [{"role": "user", "content": "go"}]
        for number in range(3):
            provider += _lookup("lookup" if number % 2 else "fetch", f"k{number}", f"OUT-{number}-" + "x" * 900)
        provider += _lookup("fetch", "k3", "NEWEST")
        plain = await _view(MessageHistoryCompactionMiddleware.tool_output_sliding_window(), provider)
        explicit = await _view(MessageHistoryCompactionMiddleware.tool_output_sliding_window(placeholder=DEFAULT_PLACEHOLDER, tools=()), provider)
        self.assertEqual(plain, explicit)
        results = [m["content"] for m in plain if m["role"] == "tool"]
        # Per tool, newest first: fetch keeps k3 and k2, so k0 (900 + 6 chars) is truncated to 600; lookup keeps k1.
        self.assertEqual(results[0], provider[2]["content"][:600] + f" [... truncated {len(provider[2]['content']) - 600} characters ...]")
        self.assertEqual(results[1:], [provider[4]["content"], provider[6]["content"], "NEWEST"])

    async def test_the_engine_forwards_tools_and_placeholder_options(self) -> None:
        # FR-2.1: compact_messages with the tools and placeholder options scopes the window.
        history = self._mixed_history()
        after, _ = await ContextCompactionEngine().compact_messages(history, mode=CompactionMode.TOOL_OUTPUT_SLIDING_WINDOW, options={"keep_recent": 3, "window_mode": STRIP.value, "placeholder": "ENGINE-MASK", "tools": SEARCH_SCOPE})
        self.assertEqual(after, _window(history, 3, "ENGINE-MASK", SEARCH_SCOPE))


class QuantizedTrimTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_91k_history_keeps_one_suffix_between_65_5k_and_66k(self) -> None:
        # AC-4.1: M = 90,000, L = 65,000, no system groups, N = 91,000 in groups of at most 500: the cut drops the shortest
        # prefix reaching 25,000 tokens, so the kept suffix holds at most 66,000 and more than 65,500.
        sizes = _sizes_summing_to(random.Random(41), 91_000, 500)
        history = _history_of(sizes)
        kept = await _trim(max_tokens=90_000, low_watermark_tokens=65_000).compact(history)
        self.assertEqual(kept, history[len(history) - len(kept):], "the kept history is not one contiguous suffix")
        self.assertTrue(65_500 < sum(len(m.content) for m in kept) <= 66_000, sum(len(m.content) for m in kept))
        self.assertEqual(kept, _quantized_trim(history, 90_000, 65_000))

    async def test_appending_up_to_24k_more_keeps_the_same_first_message(self) -> None:
        # AC-4.2, INV-4.4: appended groups of at most 500 tokens, 24,000 in total, keep ceil((N - B) / S) at 1, so the cut stays put.
        rng = random.Random(42)
        history = _history_of(_sizes_summing_to(rng, 91_000, 500))
        trim = _trim(max_tokens=90_000, low_watermark_tokens=65_000)
        first = (await trim.compact(history))[0]
        grown = history
        for chunk in _sizes_summing_to(rng, 24_000, 500):
            grown = grown + _history_of([chunk], start=len(grown))
            self.assertEqual((await _trim(max_tokens=90_000, low_watermark_tokens=65_000).compact(grown))[0], first)
        self.assertEqual(sum(len(m.content) for m in grown), 115_000)

    async def test_the_quantized_cut_matches_inv_4_2_on_random_histories(self) -> None:
        # INV-4.2, INV-4.3, EC-4.5: on seeded random histories (tool groups, parallel results, system groups, budgets that go
        # negative), the trim equals the spec's formula, keeps whole groups, and keeps one contiguous non-system suffix <= B.
        for seed in range(300):
            rng = random.Random(seed)
            system_sizes = [rng.randint(1, 400) for _ in range(rng.choice((0, 0, 1, 2)))]
            history = _random_history(rng, groups=rng.randint(0, 40), max_size=rng.randint(5, 300), system_sizes=system_sizes)
            max_tokens = rng.randint(0, 4_000)
            low = rng.randint(0, max(0, max_tokens - 1))
            if max_tokens == 0:
                continue
            with self.subTest(seed=seed, max_tokens=max_tokens, low=low):
                kept = await _trim(max_tokens=max_tokens, low_watermark_tokens=low).compact(history)
                self.assertEqual(kept, _quantized_trim(history, max_tokens, low))
                self.assertEqual([m for m in kept if m.role == "system"], [m for m in history if m.role == "system"], "a system group was dropped")
                non_system = [m for m in kept if m.role != "system"]
                tail = [m for m in history if m.role != "system"]
                self.assertEqual(non_system, tail[len(tail) - len(non_system):])
                budget = max_tokens - sum(len(m.content) for m in history if m.role == "system")
                self.assertTrue(not non_system or sum(len(m.content) for m in non_system) <= budget, (budget, len(non_system)))

    async def test_without_a_low_watermark_the_trim_equals_main(self) -> None:
        # AC-4.3, INV-4.1, D-6: None, L == M, and L > M give main's output for every input, including main's non-contiguous keep.
        non_contiguous = 0
        for seed in range(200):
            rng = random.Random(1_000 + seed)
            history = _random_history(rng, groups=rng.randint(0, 30), max_size=rng.randint(5, 400), system_sizes=[rng.randint(1, 200)] if rng.random() < 0.3 else [])
            max_tokens = rng.randint(0, 3_000)
            max_messages = rng.choice((None, None, rng.randint(0, 40)))
            expected = _main_trim(history, max_tokens, max_messages)
            kept_tail = [m for m in expected if m.role != "system"]
            all_tail = [m for m in history if m.role != "system"]
            non_contiguous += kept_tail != all_tail[len(all_tail) - len(kept_tail):]
            for low in (None, max_tokens, max_tokens + 1 + seed):
                with self.subTest(seed=seed, low=low, max_messages=max_messages):
                    kept = await _trim(max_tokens=max_tokens, max_messages=max_messages, low_watermark_tokens=low).compact(history)
                    self.assertEqual(kept, expected)
        self.assertGreater(non_contiguous, 0, "no random case exercised main's non-contiguous keep, so the fallback was not really tested")

    async def test_a_bad_low_watermark_is_refused_by_the_strategy_and_the_builder(self) -> None:
        # Section 8.5, row 4 and row 7: a negative value, a bool, a float, or text is a ValueError at construction.
        for bad in (-1, True, 2.5, "65000"):
            with self.subTest(low_watermark_tokens=bad):
                with self.assertRaises(ValueError):
                    _trim(max_tokens=90_000, low_watermark_tokens=bad)
                with self.assertRaises(ValueError):
                    MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=90_000, low_watermark_tokens=bad)
        _trim(max_tokens=90_000, low_watermark_tokens=0)

    async def test_the_engine_and_the_builder_forward_the_low_watermark(self) -> None:
        # FR-4.1: the option reaches the strategy through compact_messages and through the middleware builder.
        sizes = _sizes_summing_to(random.Random(7), 1_000, 50)
        history = _history_of(sizes)
        expected = _quantized_trim(history, 800, 500)
        self.assertNotEqual(expected, _main_trim(history, 800), "precondition: the cut differs from main's")
        after, _ = await ContextCompactionEngine().compact_messages(history, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_tokens": 800, "low_watermark_tokens": 500, "token_counter": len})
        self.assertEqual(after, expected)
        provider = [{"role": message.role, "content": message.content} for message in history]
        middleware = MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=800, token_counter=len, low_watermark_tokens=500)
        view = await _view(middleware, provider)
        self.assertEqual([m["content"] for m in view], [m.content for m in expected])


if __name__ == "__main__":
    unittest.main()
