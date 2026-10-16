"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_prompts.py

PURPOSE: Pins the text contract of the infinite_memory prompt family after the rewrite of docs/spec/infinite-memory-prompts/spec.md: the token floors of the seven behavior-shaping assets, the distinctive phrases that prove each principle is stated where its stage reads it, the exact placeholder set and brace-freedom of every formatted leaf, the trailing-newline split between fragments and whole texts, the digit rule, the size bounds on the 33 compact leaves, the no-repeated-sentence rule, the result card's labels, the quota line's standalone integers, the heading sets, and the folder-to-JSON parity of the 40 assets.
ROLE IN CODEBASE: Prompt-contract layer of tests/features/infinite_memory_agent/ (prompt spec AC-1, AC-3..AC-8, AC-10, AC-13; INV-6, INV-10..INV-17, INV-19; EC-1..EC-3, EC-5..EC-8, EC-11, EC-15, EC-16). Reads only vidbyte/prompts/prompts/infinite_memory/ through the catalog, plus vidbyte/lib/util/text.py and the family JSON.
ARCHITECTURE NOTE: Every count goes through Prompts().get, never through the file bytes, so a CRLF working tree measures exactly what the model receives. tiktoken is optional: the "tiktoken" measure is skipped with a message when it is not installed, and the SDK estimate is always checked. Phrases are matched after the D-9 normalization (lowercase, typographic quotes folded, `*`, `_`, backtick and comma removed, whitespace collapsed); sentences are the S025 SentenceCounter units, copied from lint/rules/s025_model_facing_description_depth.py because lint/ is not importable from tests.
FUNCTION INVENTORY: test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor (AC-1); test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline (INV-14, AC-7); test_pinned_phrase_is_present_in_its_leaf (INV-16, AC-4); test_verifier_system_prompt_states_the_three_verdict_literals_exactly (INV-6, AC-4, EC-8); test_formatted_leaf_renders_each_placeholder_once_and_leaves_no_brace (INV-11, AC-3, EC-1); test_raw_leaves_hold_no_brace_at_all (INV-11, INV-22, AC-3); test_fragments_end_without_a_newline_and_whole_texts_with_exactly_one (INV-12, AC-8, EC-2); test_digits_appear_only_as_ordered_list_markers (INV-13, AC-5, EC-3); test_compact_description_sum_stays_within_ten_percent_of_baseline (INV-15 a, AC-6, EC-7); test_every_compact_description_has_at_least_four_sentences (INV-15 b, AC-6); test_every_reply_leaf_stays_within_eighty_tokens (INV-15 c, AC-6); test_shape_leaf_never_grows_past_its_baseline (INV-15 d, AC-6); test_no_rule_sentence_repeats_inside_a_behavior_asset (INV-15 e, AC-7, EC-11); test_result_card_keeps_its_labels_in_order_and_never_carries_the_cut_marker (INV-17, AC-10, EC-5); test_quota_line_renders_each_count_as_a_standalone_integer (INV-17, AC-10, EC-6); test_every_base_heading_survives_in_order (INV-19, AC-13, EC-15, EC-16); test_family_folder_holds_exactly_the_leaf_assets_as_path_and_source_url (INV-10, AC-2).
COMMON MODIFICATION PATTERNS: When the spec adds or drops a pinned phrase, change PINNED_PHRASES and nothing else. When a baseline is re-measured at a new base commit, change BASELINES and SHAPE_BASELINES together with the spec's section 8.5 table. A new formatted leaf adds one row to PLACEHOLDERS; a new heading adds to HEADINGS.
WHAT NOT TO DO IN THIS FILE: 1. Do not read an asset with Path.read_text or read_bytes; go through prompt_text so line endings and the catalog's validation apply. 2. Do not pin a phrase on any leaf outside the ten INV-16 names; the other 30 compact leaves are review guidance (spec r2 R-5). 3. Do not add an upper ceiling or a per-leaf ratio bound; those are review thresholds, not tests (spec r2 R-4). 4. Do not import feature symbols at module level (see infinite_memory_fixtures.py).
KNOWN EDGE CASES: "A dash means none." repeats by design in the three briefings (spec outlines 4.3, 5.3, 6.2, 6.3), so the duplicate-sentence check ignores sentences under five words; a pasted rule is never that short. The §4 snippet shadows the names SEVEN, catalog and text inside the test body, so the module keeps its own tables under other names.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-prompts/spec.md sections 4, 6.1, 6.2, 8.1 (D-9), 8.5, 12.3.1 and 13; docs/spec/infinite-memory-prompts/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from string import Formatter

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import int_token, prompt_text

REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILY_DIR = REPO_ROOT / "vidbyte" / "prompts" / "prompts" / "infinite_memory"

TIKTOKEN_AVAILABLE = importlib.util.find_spec("tiktoken") is not None
# The two measures of spec D-8: the SDK estimate always runs; tiktoken
# cl100k_base is the binding one, skipped (not failed) when absent.
MEASURES = (
    pytest.param("estimate", id="estimate"),
    pytest.param("tiktoken", id="tiktoken", marks=pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken is not installed; the tiktoken bound is not checked")),
)
FLOORS = {"estimate": 1_000, "tiktoken": 1_100}

# Spec section 8.5 (1): the seven behavior-shaping assets, measured at
# base_commit 7efceb55 as (estimate, tiktoken).
BASELINES = {
    "root_system_prompt": (2_129, 1_829),
    "generator_system_prompt": (1_503, 1_277),
    "verifier_system_prompt": (1_246, 1_059),
    "task_prompt": (286, 241),
    "verifier_task_prompt": (294, 251),
    "resume_prompt": (273, 232),
    "launch_tool_description": (495, 416),
}

# Spec section 8.5 (1)-(3): the pinned phrases of the ten INV-16 leaves
# as (kept at base, new in the rewrite).
PINNED_PHRASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "root_system_prompt": (
        ("the run's scarcest resource", "more text into your context than its result card", "neither can see this conversation"),
        ("the default is not to remember", "check each deliverable against the cards", "a card is not memory", "never end your turn to ask", "trimming is not a reason to remember"),
    ),
    "generator_system_prompt": (
        ("is your whole brief", "write findings into your note as you go", "report only what you did and checked", "your parent reads only this"),
        ("the default is not to remember", "check each criterion before you reply", "state plainly what is not done", "trimming is not a reason to remember"),
    ),
    "verifier_system_prompt": (
        ("never pass what you did not check", "treat the answer as claims", "a criterion you could not verify counts as not met", "exactly one line, and nothing after it"),
        ("drop what is not worth keeping", "the workspace is the record", "say what you fixed", "trimming is not a reason to remember"),
    ),
    "task_prompt": (
        ("search the workspace for related entries and notes", "whether it is met and where the evidence is"),
        ("wrong or slower without it", "keep a note as you go", "nothing the parent does not need"),
    ),
    "verifier_task_prompt": (
        ("they are already written", "exactly one verdict line"),
        ("nothing below has been checked yet", "check them in place", "stage only what the generator missed"),
    ),
    "resume_prompt": (
        ("your earlier conversation is gone", "the same name runs a pair from scratch", "finish the original task"),
        ("compare the deliverables with the finished cards", "never save a card's status or progress", "no one will answer during the run"),
    ),
    "launch_tool_description": (
        ("outside your own context", "checked before anything starts", "give new or repeated work a new name", "quicker than writing a task card"),
        ("only the result card comes back", "never ask for a transcript"),
    ),
    "launch_generator_prompt_description": ((), ("ask for exactly what you will need",)),
    "remember_tool_description": ((), ("the default is not to remember",)),
    "remember_saved_prompt": ((), ("keep anything longer in a note",)),
}
VERDICT_LITERALS = ("VERDICT: passed", "VERDICT: fixed", "VERDICT: failed")

# Spec section 8.5 and the .format calls in launch.py, memory.py,
# workspace.py and agent.py: the 12 formatted leaves and their exact
# placeholder sets.
PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    "task_prompt": ("goal", "criteria", "instructions", "entries", "paths", "finished", "quota"),
    "verifier_task_prompt": ("instructions", "goal", "criteria", "status", "summary", "staged", "files", "quota"),
    "resume_prompt": ("task", "finished", "interrupted"),
    "result_card": ("name", "key", "status", "verdict", "summary", "review", "entries", "dropped", "files"),
    "launch_rejected_prompt": ("problem",),
    "memory_rejected_prompt": ("problem",),
    "remember_saved_prompt": ("id",),
    "remember_staged_prompt": ("key",),
    "note_saved_prompt": ("path",),
    "entry_dropped_prompt": ("key", "remaining"),
    "quota_line": ("entries_left", "entries_max", "files_left", "files_max"),
    "map_header": ("files", "max_files", "tokens", "max_tokens", "entries"),
}
# INV-12: the 13 leaves inserted into a larger string end without a
# newline; every other leaf ends with exactly one.
FRAGMENTS = frozenset(PLACEHOLDERS) | {"replayed_label"}
REPLIES = ("remember_saved_prompt", "remember_staged_prompt", "note_saved_prompt", "entry_dropped_prompt", "memory_rejected_prompt", "launch_rejected_prompt", "replayed_label")
REPLY_BOUND = 80
# INV-15 (a): the sum of the per-leaf counts of the 23 descriptions at
# 110 % of its baseline (3,803 tiktoken, 4,455 estimate).
COMPACT_SUM_BOUND = {"estimate": 4_900, "tiktoken": 4_183}
MINIMUM_SENTENCES = 4
# INV-15 (d): the three shape leaves may not grow past their baseline,
# given as (estimate, tiktoken).
SHAPE_BASELINES = {"quota_line": (38, 38), "map_header": (54, 51), "result_card": (54, 56)}
RESULT_CARD_LABELS = ("### Pair {name} ({key})", "Status:", "Verdict:", "Generator summary:", "Verifier review:", "Entries saved to memory:", "Entries dropped, with reasons:", "Files written:")
CUT_MARKER = " … [cut]"

# Spec section 12.3.1: the heading set of every asset at base_commit,
# which must survive in order (new headings may sit between them).
TOOL_HEADINGS = ("## What it does", "## When to use it", "## How it behaves", "## Rules and refusals")
PARAMETER_HEADINGS = ("## Purpose", "## How to write it", "## Rules")
HEADINGS: dict[str, tuple[str, ...]] = {
    "root_system_prompt": ("# Your role: root", "# How the work flows", "# What to delegate and what to do yourself", "# How to write a task card", "# Running tasks in parallel", "# Reading result cards", "# Memory", "# Working within history trimming", "# When a call is refused", "# Your final answer"),
    "generator_system_prompt": ("# Your role: generator", "# How to work", "# Delegating further", "# Memory", "# Working within history trimming", "# When a call is refused", "# Your final answer"),
    "verifier_system_prompt": ("# Your role: verifier", "# How to check", "# How to fix", "# Reviewing staged entries", "# Working within history trimming", "# When a call is refused", "# Your final reply"),
    "task_prompt": ("# Goal", "# Done criteria", "# Your instructions", "# Memory entries to start from", "# Workspace files to start from", "# Your subagent pairs that already finished in this run", "# Your memory quota", "# What to do next"),
    "verifier_task_prompt": ("# Your instructions", "# Goal", "# Done criteria", "# What the generator reported", "# Memory entries the generator staged", "# Files the generator wrote", "# Your memory quota", "# What to do next"),
    "resume_prompt": ("# The original task", "# Subagent pairs that already finished", "# Subagent pairs that started but never finished", "# What to do next"),
    "launch_tool_description": TOOL_HEADINGS,
    **{leaf: TOOL_HEADINGS for leaf in ("remember_tool_description", "write_note_tool_description", "edit_file_tool_description", "drop_entry_tool_description")},
    **{leaf: PARAMETER_HEADINGS for leaf in ("launch_tasks_description", "launch_name_description", "launch_goal_description", "launch_done_criteria_description", "launch_generator_prompt_description", "launch_verifier_prompt_description", "launch_context_description", "launch_tools_description", "remember_text_description", "remember_tags_description", "remember_refs_description", "note_path_description", "write_note_file_description", "edit_file_old_text_description")},
    "remember_kind_description": ("## Purpose", "## How to choose", "## Rules"),
    "remember_supersedes_description": ("## Purpose", "## How it behaves", "## Rules"),
    "write_note_text_description": ("## Purpose", "## How it behaves", "## How to write it", "## Rules"),
    "edit_file_new_text_description": ("## Purpose", "## How it behaves", "## How to write it", "## Rules"),
    "drop_entry_id_description": ("## Purpose", "## How to find it", "## Rules"),
}

# lint/rules/s025_model_facing_description_depth.py:29 and :185-200,
# copied here because lint/ is not importable from tests.
ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.")
MINIMUM_WORDS_FOR_A_RULE = 5


def measure(name: str, text: str) -> int:
    """The token count of `text` by the named measure: the SDK's TokenEstimate.count or tiktoken cl100k_base."""
    if name == "tiktoken":
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    from vidbyte.lib.util import TokenEstimate

    return TokenEstimate.count(text)


def normalize(text: str) -> str:
    """Spec D-9: lowercase, typographic quotes folded to ASCII, `*`, `_`, backtick and comma removed, whitespace collapsed."""
    folded = text.lower()
    for typographic, ascii_form in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        folded = folded.replace(typographic, ascii_form)
    return re.sub(r"\s+", " ", re.sub(r"[*_`,]", "", folded)).strip()


def _is_terminal(text: str, index: int) -> bool:
    """S025: a `.`, `!` or `?` ends a sentence when followed by whitespace or the end and not closing an abbreviation."""
    if index + 1 < len(text) and not text[index + 1].isspace():
        return False
    return not any(text[: index + 1].lower().endswith(abbreviation) for abbreviation in ABBREVIATIONS)


def sentences(text: str) -> list[str]:
    """The S025 sentence units of `text`; a non-empty text with no terminal mark is one sentence, as SentenceCounter.count says."""
    stripped = text.strip()
    if not stripped:
        return []
    parts: list[str] = []
    start = 0
    for index, char in enumerate(stripped):
        if char in ".!?" and _is_terminal(stripped, index):
            parts.append(stripped[start : index + 1])
            start = index + 1
    return parts or [stripped]


def family() -> dict[str, str]:
    """Every leaf of the family by name, read through the catalog."""
    from vidbyte.prompts import Prompts

    return dict(Prompts().family("infinite_memory"))


def headings(text: str) -> list[str]:
    """The Markdown heading lines of an asset, in order."""
    return [line.rstrip() for line in text.splitlines() if re.match(r"#{1,6} ", line)]


# ------------------------ AC-1: the section 4 snippet


def test_section_4_snippet_prints_seven_lines_each_at_or_over_the_floor(capsys: pytest.CaptureFixture[str]) -> None:
    """AC-1, G-2: the spec's section 4 snippet, run as written, prints one line per asset with estimate >= 1,000 and tiktoken >= 1,100 (or "-" with a notice when tiktoken is absent)."""
    # ---- spec section 4, as printed ----
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.lib.util.text import TokenEstimate
    from vidbyte.prompts.catalog import Prompts

    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        encoding = None
        print("tiktoken is not installed; only the SDK estimate is shown")

    SEVEN = (
        "ROOT_SYSTEM_PROMPT",
        "GENERATOR_SYSTEM_PROMPT",
        "VERIFIER_SYSTEM_PROMPT",
        "TASK_PROMPT",
        "VERIFIER_TASK_PROMPT",
        "RESUME_PROMPT",
        "LAUNCH_TOOL_DESCRIPTION",
    )
    catalog = Prompts()
    for name in SEVEN:
        text = catalog.get(Prompt[f"INFINITE_MEMORY_{name}"])
        exact = len(encoding.encode(text)) if encoding else "-"
        print(f"{name.lower()}: estimate {TokenEstimate.count(text)}, tiktoken {exact}")
    # ---- end of the snippet ----
    lines = capsys.readouterr().out.splitlines()
    if not TIKTOKEN_AVAILABLE:
        assert lines[0] == "tiktoken is not installed; only the SDK estimate is shown"
        lines = lines[1:]
    assert len(lines) == 7, lines
    short = []
    for line, leaf in zip(lines, BASELINES, strict=True):
        match = re.fullmatch(rf"{leaf}: estimate (\d+), tiktoken (\d+|-)", line)
        assert match, f"unexpected output line: {line!r}"
        assert (match[2] == "-") is not TIKTOKEN_AVAILABLE, line
        if int(match[1]) < FLOORS["estimate"] or (match[2] != "-" and int(match[2]) < FLOORS["tiktoken"]):
            short.append(line)
    assert not short, f"under the floor (estimate >= {FLOORS['estimate']}, tiktoken >= {FLOORS['tiktoken']}): {short}"


# ------------------------ floors, phrases, verdict literals


@pytest.mark.parametrize("leaf", BASELINES)
@pytest.mark.parametrize("which", MEASURES)
def test_behavior_asset_clears_the_floor_and_never_shrinks_below_baseline(leaf: str, which: str) -> None:
    """INV-14, AC-7, FR-2: each of the seven measures at least the floor by this measure, and by tiktoken never fewer tokens than at base_commit."""
    count = measure(which, prompt_text(leaf))
    assert count >= FLOORS[which], f"{leaf} is {count} {which} tokens, under the floor of {FLOORS[which]}"
    if which == "tiktoken":
        baseline = BASELINES[leaf][1]
        assert count >= baseline, f"{leaf} shrank to {count} tiktoken tokens from its baseline of {baseline}"


@pytest.mark.parametrize(
    ("leaf", "phrase"),
    [pytest.param(leaf, phrase, id=f"{leaf}-{phrase}") for leaf, (kept, new) in PINNED_PHRASES.items() for phrase in (*kept, *new)],
)
def test_pinned_phrase_is_present_in_its_leaf(leaf: str, phrase: str) -> None:
    """INV-16, AC-4, FR-11: the leaf carries this section 8.5 phrase after D-9 normalization; a phrase moved to another leaf does not count."""
    assert normalize(phrase) in normalize(prompt_text(leaf)), f"{leaf} does not state {phrase!r}"


def test_verifier_system_prompt_states_the_three_verdict_literals_exactly() -> None:
    """INV-6, AC-4, EC-8: the verifier reads the three verdict lines spelled exactly as the parser expects; a reworded or missing one yields unchecked verdicts and lost entries."""
    text = prompt_text("verifier_system_prompt")
    missing = [literal for literal in VERDICT_LITERALS if literal not in text]
    assert not missing, f"verifier_system_prompt lacks the exact literal(s) {missing}"


# ------------------------ placeholders, braces, newlines, digits


@pytest.mark.parametrize("leaf", PLACEHOLDERS)
def test_formatted_leaf_renders_each_placeholder_once_and_leaves_no_brace(leaf: str) -> None:
    """INV-11, AC-3, EC-1: str.format with one dummy per documented placeholder raises nothing, places each dummy exactly once, and leaves no brace; a renamed, doubled or dropped placeholder, or a literal brace in prose, fails here before it fails every launch."""
    expected = PLACEHOLDERS[leaf]
    text = prompt_text(leaf)
    try:
        found = [name for _, name, _, _ in Formatter().parse(text) if name is not None]
    except ValueError as exc:
        pytest.fail(f"{leaf} is not a valid format template: {exc}")
    assert sorted(found) == sorted(expected), f"{leaf} placeholders {found} are not exactly {list(expected)}"
    dummies = {name: f"<{name.upper()}>" for name in expected}
    rendered = text.format(**dummies)
    for name, dummy in dummies.items():
        assert rendered.count(dummy) == 1, f"{leaf} renders {{{name}}} {rendered.count(dummy)} times"
    assert "{" not in rendered and "}" not in rendered, f"{leaf} leaves a brace after formatting: {rendered!r}"


def test_raw_leaves_hold_no_brace_at_all() -> None:
    """INV-11, INV-22, AC-3: the 28 leaves the code never formats contain no brace, so none can be mistaken for a placeholder or weaken a template regex."""
    offenders = [leaf for leaf, text in family().items() if leaf not in PLACEHOLDERS and ("{" in text or "}" in text)]
    assert not offenders, f"raw leaves holding a brace: {offenders}"


def test_fragments_end_without_a_newline_and_whole_texts_with_exactly_one() -> None:
    """INV-12, AC-8, EC-2: the 13 fragments the code joins into larger strings end without a newline; the 27 whole texts end with exactly one."""
    offenders = []
    for leaf, text in family().items():
        if leaf in FRAGMENTS:
            if text.endswith("\n"):
                offenders.append(f"{leaf} (fragment) ends with a newline")
        elif not text.endswith("\n") or text.endswith("\n\n"):
            offenders.append(f"{leaf} (whole text) does not end with exactly one newline")
    assert not offenders, offenders


def test_digits_appear_only_as_ordered_list_markers() -> None:
    """INV-13, AC-5, EC-3, NG-10: after removing ordered-list markers at line start, no leaf holds a digit, so no asset can quote a limit the settings may change."""
    offenders = {leaf: re.findall(r"\S*\d\S*", re.sub(r"(?m)^\d+\. ", "", text)) for leaf, text in family().items()}
    offenders = {leaf: hits for leaf, hits in offenders.items() if hits}
    assert not offenders, f"digits outside list markers: {offenders}"


# ------------------------ INV-15: the tested size bounds


def compact_descriptions(leaves: dict[str, str]) -> dict[str, str]:
    """The 23 compact descriptions: every `*_description` leaf except the launch tool's own."""
    return {leaf: text for leaf, text in leaves.items() if leaf.endswith("_description") and leaf != "launch_tool_description"}


@pytest.mark.parametrize("which", MEASURES)
def test_compact_description_sum_stays_within_ten_percent_of_baseline(which: str) -> None:
    """INV-15 (a), AC-6, EC-7, NFR-1: the per-leaf counts of the 23 compact descriptions, which ride in every tool schema, sum to at most 110 % of their baseline."""
    compact = compact_descriptions(family())
    assert len(compact) == 23, sorted(compact)
    counts = {leaf: measure(which, text) for leaf, text in compact.items()}
    total = sum(counts.values())
    assert total <= COMPACT_SUM_BOUND[which], f"the 23 descriptions sum to {total} {which} tokens, over {COMPACT_SUM_BOUND[which]}: {counts}"


def test_every_compact_description_has_at_least_four_sentences() -> None:
    """INV-15 (b), AC-6, FR-6: each of the 23 descriptions reads as at least four S025 sentences, the field guide's depth for model-facing contracts."""
    short = {leaf: len(sentences(text)) for leaf, text in compact_descriptions(family()).items() if len(sentences(text)) < MINIMUM_SENTENCES}
    assert not short, f"descriptions under {MINIMUM_SENTENCES} sentences: {short}"


@pytest.mark.parametrize("which", MEASURES)
def test_every_reply_leaf_stays_within_eighty_tokens(which: str) -> None:
    """INV-15 (c), AC-6, FR-7, NFR-2: each of the seven replies, which repeat in every tool result, measures at most 80 tokens."""
    over = {leaf: measure(which, prompt_text(leaf)) for leaf in REPLIES if measure(which, prompt_text(leaf)) > REPLY_BOUND}
    assert not over, f"replies over {REPLY_BOUND} {which} tokens: {over}"


@pytest.mark.parametrize("leaf", SHAPE_BASELINES)
@pytest.mark.parametrize("which", MEASURES)
def test_shape_leaf_never_grows_past_its_baseline(leaf: str, which: str) -> None:
    """INV-15 (d), AC-6, FR-8: the quota line, the map header and the card template measure no more than at base_commit."""
    bound = SHAPE_BASELINES[leaf][0 if which == "estimate" else 1]
    count = measure(which, prompt_text(leaf))
    assert count <= bound, f"{leaf} grew to {count} {which} tokens from its baseline of {bound}"


@pytest.mark.parametrize("leaf", BASELINES)
def test_no_rule_sentence_repeats_inside_a_behavior_asset(leaf: str) -> None:
    """INV-15 (e), AC-7, EC-11, NFR-4: no sentence of five or more words appears twice in one of the seven after D-9 normalization, so the floor cannot be met by pasting a rule again."""
    units = [normalize(unit) for unit in sentences(prompt_text(leaf))]
    rules = [unit for unit in units if len(unit.split()) >= MINIMUM_WORDS_FOR_A_RULE]
    repeated = sorted({unit for unit in rules if rules.count(unit) > 1})
    assert not repeated, f"{leaf} repeats: {repeated}"


# ------------------------ INV-17: the shape leaves' literal text


def test_result_card_keeps_its_labels_in_order_and_never_carries_the_cut_marker() -> None:
    """INV-17, AC-10, EC-5: the card template keeps its heading line and six labels in order and holds no truncation marker, so a parent reads the same cues and NFR-7 counts only the code's four cuts."""
    text = prompt_text("result_card")
    positions = [text.find(label) for label in RESULT_CARD_LABELS]
    missing = [label for label, position in zip(RESULT_CARD_LABELS, positions, strict=True) if position < 0]
    assert not missing, f"result_card lost the label(s) {missing}"
    assert positions == sorted(positions), f"result_card labels are out of order: {list(zip(RESULT_CARD_LABELS, positions, strict=True))}"
    assert CUT_MARKER not in text, "result_card carries the truncation marker itself"


def test_quota_line_renders_each_count_as_a_standalone_integer() -> None:
    """INV-17, AC-10, EC-6: every one of the four quota counts renders with no letter, digit or hyphen touching it, so a reader (and the workspace test's int_token) finds the integer."""
    values = {name: number for name, number in zip(PLACEHOLDERS["quota_line"], (11, 22, 33, 44), strict=True)}
    rendered = prompt_text("quota_line").format(**values)
    stuck = [name for name, number in values.items() if not int_token(number).search(rendered)]
    assert not stuck, f"quota_line does not render {stuck} as standalone integers: {rendered!r}"


# ------------------------ INV-19, INV-10: headings and the folder


@pytest.mark.parametrize("leaf", HEADINGS)
def test_every_base_heading_survives_in_order(leaf: str) -> None:
    """INV-19, AC-13, EC-15, EC-16, D-5: every heading the asset had at base_commit is still there in the same order; headings may be added between them, never dropped, renamed or reordered."""
    found = headings(prompt_text(leaf))
    remaining = list(found)
    for heading in HEADINGS[leaf]:
        assert heading in remaining, f"{leaf} lost or moved heading {heading!r}; headings now: {found}"
        remaining = remaining[remaining.index(heading) + 1 :]


def test_family_folder_holds_exactly_the_leaf_assets_as_path_and_source_url() -> None:
    """INV-10, AC-2, NG-2, D-D: the family JSON lists each leaf as {path, source_url} with no inline text, and the folder's .md files are exactly those paths: no stray asset ships, none is missing."""
    data = json.loads((FAMILY_DIR / "infinite_memory.json").read_text(encoding="utf-8"))
    leaves = data["prompts"]
    assert len(leaves) == 40, sorted(leaves)
    not_files = {leaf: value for leaf, value in leaves.items() if not isinstance(value, dict) or set(value) != {"path", "source_url"}}
    assert not not_files, f"leaves that are not {{path, source_url}} records: {not_files}"
    assert {leaf: value["path"] for leaf, value in leaves.items()} == {leaf: f"{leaf}.md" for leaf in leaves}
    on_disk = sorted(path.name for path in FAMILY_DIR.glob("*.md"))
    assert on_disk == sorted(value["path"] for value in leaves.values()), f"folder and JSON differ: {set(on_disk) ^ {value['path'] for value in leaves.values()}}"
    assert set(leaves) == set(family()), "the catalog does not serve exactly the JSON's leaves"
