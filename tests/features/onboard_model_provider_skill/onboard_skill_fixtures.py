"""FILE: tests/features/onboard_model_provider_skill/onboard_skill_fixtures.py

PURPOSE: Shared reading tools and spec facts for the onboard-model-provider skill pack: the paths of the two skill files and REPO_MAP.md, the values spec r3 fixes (headings, constants, enumerations, the 33 wiring rows, the ten seed slugs, the output grammar), a Markdown reader that knows fenced code from prose, and an emulator for the skill's own `sed -n 's/.../.../p'` commands.
ROLE IN CODEBASE: Imported by every test module in tests/features/onboard_model_provider_skill/. It reads files only; the skill files themselves are the feature under test.
ARCHITECTURE NOTE: Every expected value here is spelled from docs/spec/provider-onboarding-skill/spec.md r3 (sections 8.5, 9.1, 9.2 and 12.3), never read from the skill files, so the tests and the skill cannot share one defect. MarkdownDoc classifies each line once (prose, fence delimiter, or code with its info string) so headings and tables inside code fences are never mistaken for structure. SedEmulator translates a POSIX basic regular expression to Python and prints what `sed -n 's/P/R/p'` would print, so a test can run the skill's own extraction command over the real repository files without a shell.
FUNCTION INVENTORY: read_markdown(path, spec_ref) parses a skill file or fails naming the spec row that creates it; MarkdownDoc.h2_headings / section / text / squashed / shell_commands / code_spans / fenced_blocks / commands / table_rows read one document; split_row(line) splits a GFM table row on unescaped pipes; sed_print_expressions(command) finds the `sed -n 's...p'` scripts in a command; SedEmulator.translate / print_lines run one; first_index(commands, pattern) locates a command.
COMMON MODIFICATION PATTERNS: When the spec changes a heading, a constant, an enumeration, a wiring row or a seed slug, change the matching constant here in the same change and cite the spec section. Keep the constants literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not read an expected value from the skill files or from code under test. 2. Do not create, stub or copy a skill file; a missing file must keep the pack red. 3. Do not run a shell, git, gh or the network; the emulator exists so no test needs them.
KNOWN EDGE CASES: Files are read in text mode, so CRLF working copies parse like the LF git blobs the skill reads. An unclosed fence runs to the end of the file, as in GitHub's renderer. The emulator supports the BRE subset the skill uses (groups, bracket expressions with POSIX classes, anchors, `*`, GNU `\\+ \\? \\|`) and sed's leftmost match, which equals POSIX leftmost-longest for the anchored `.*` patterns the skill writes.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md r3 sections 8.5, 9.1, 9.2, 12.3 and 13.
TESTS: python -m pytest tests/features/onboard_model_provider_skill -q
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "onboard-model-provider"
SKILL_FILE = SKILL_DIR / "SKILL.md"
PROCEDURE_FILE = SKILL_DIR / "references" / "provider-run.md"
REPO_MAP_FILE = REPO_ROOT / "REPO_MAP.md"
SKILL_REF = "spec 12.3 row 2 (SKILL.md)"
PROCEDURE_REF = "spec 12.3 row 1 (references/provider-run.md)"

# Fenced blocks whose lines are shell commands an agent runs verbatim (AC-5 scans `sh` and `bash`).
SHELL_INFOS = frozenset({"sh", "bash", "shell", "console", "zsh"})

# Spec 8.5 "H2 headings, exact text and order".
SKILL_HEADINGS = (
    "## What one invocation does",
    "## Prerequisites and preflight",
    "## Constants",
    "## Each pass",
    "## The provider subagent",
    "## Verifying a result",
    "## What each outcome leaves behind",
    "## Output",
    "## Rules",
    "## Seed vendors",
    "## Excluded vendors",
)
PROCEDURE_HEADINGS = (
    "## 1. Orient",
    "## 2. Research",
    "## 3. Qualify",
    "## 4. Red-first tests",
    "## 5. Wiring checklist",
    "## 6. Self-check",
    "## 7. Commit and mutation checks",
    "## 8. Gate",
    "## 9. Publish",
    "## 10. Result",
)

# Spec 8.5 "Constants SKILL.md states (names are the contract)".
CONSTANTS = (
    ("REPO", "cerredz/Vidbyte-SDK"),
    ("BRANCH_PREFIX", "feat/provider-"),
    ("MAX_OPEN_PROVIDER_PRS", "3"),
    ("MAX_CATALOGUED_MODELS", "5"),
    ("WORKTREE", "<checkout>-onboard-<slug>"),
    ("BRANCH", "feat/provider-<slug>"),
    ("PROCEDURE", "${CLAUDE_SKILL_DIR}/references/provider-run.md"),
)

# Spec 8.5 "Enumerations (exact spellings)".
STOP_REASONS = ("NO_CANDIDATE", "BACKPRESSURE", "PROOF_FAILED", "VINTAGE_DEFERRED", "PREREQ_MISSING", "NETWORK_BLOCKED", "PUBLISH_FAILED", "RESULT_UNVERIFIED")
PREREQ_NAMES = ("git-repo", "origin-remote", "github-push", "git-identity", "python-dev-extras", "agent-tool")
DISQUALIFICATION_REASONS = ("docs-unreachable", "not-openai-compatible", "no-fixed-endpoint", "no-tool-calling", "no-first-party-price", "price-shape-unsupported", "no-usable-model-id", "key-prefix-collision", "slug-collision")
PROOF_CHECKS = ("red-first", "self-check", "mutation-survived", "wire-test", "gate-source", "gate-package", "import-path")
SKIP_DISPOSITIONS = ("member", "open-pr", "closed-unmerged", "merged", "remote-branch", "local-branch")
UNVERIFIED_CHECKS = ("no-result", "pr-state", "pr-head", "pr-base", "pr-sha", "diff-paths", "diff-added-file", "jev-diff", "pr-body-gate", "worktree-not-clean")
PROVIDER_OUTCOMES = ("PR_OPENED", "DISQUALIFIED", "PROOF_FAILED", "PUBLISH_FAILED", "NETWORK_BLOCKED")

# Spec 9.2 "Output grammar (exact)", one entry per line form.
OUTPUT_GRAMMAR = (
    "onboard-model-provider: [<i>] <slug> PR_OPENED <pr-url>",
    "onboard-model-provider: [<i>] <slug> DISQUALIFIED <reason>",
    "onboard-model-provider: STOP NO_CANDIDATE <m> of <total> seed vendors checked, none qualifies; opened <k> this session",
    "onboard-model-provider: STOP BACKPRESSURE <n> open provider PRs (#<a> #<b> #<c>); opened <k> this session",
    "onboard-model-provider: STOP PROOF_FAILED <slug> <check>; kept <worktree>; opened <k> this session",
    "onboard-model-provider: STOP VINTAGE_DEFERRED PRICING_AS_OF <date> on main is not before today <date> (UTC); opened <k> this session",
    "onboard-model-provider: STOP PREREQ_MISSING <name>; opened 0 this session",
    'onboard-model-provider: remedy: <python 3.11+> -m pip install -e ".[dev]"',
    "onboard-model-provider: STOP NETWORK_BLOCKED <slug|-> <host> <evidence>; opened <k> this session",
    "onboard-model-provider: STOP PUBLISH_FAILED <slug> <push|pr> <reason>; kept <worktree>; opened <k> this session",
    "onboard-model-provider: STOP RESULT_UNVERIFIED <slug> <what>; kept <worktree>; opened <k> this session",
    "- <slug>: <member | open-pr #n | closed-unmerged #n | merged #n | remote-branch | local-branch | PR_OPENED <url> | DISQUALIFIED <reason> | PROOF_FAILED <check> | PUBLISH_FAILED <push|pr> | RESULT_UNVERIFIED | NETWORK_BLOCKED | not reached>",
)

# Spec 8.5 "Table header rows, verbatim".
SEED_HEADER = "| Slug | Rank | Enum | Display name | First-party hosts | Docs URL | Pricing URL | Reason |"
WIRING_HEADER = "| Ref | Path | Symbol | Add | Fails if skipped |"

# Spec 9.1 "Seed list r3", in rank order (slug, enum).
SEED_VENDORS = (
    ("cerebras", "CEREBRAS"),
    ("ai21", "AI21"),
    ("deepinfra", "DEEPINFRA"),
    ("cohere", "COHERE"),
    ("together", "TOGETHER"),
    ("groq", "GROQ"),
    ("sambanova", "SAMBANOVA"),
    ("upstage", "UPSTAGE"),
    ("fireworks", "FIREWORKS"),
    ("nebius", "NEBIUS"),
)
EXCLUDED_VENDOR_NAMES = ("Perplexity", "Writer", "Alibaba Qwen", "DashScope", "NVIDIA NIM")


@dataclass(frozen=True)
class WiringRow:
    """One required row of the spec 12.3 wiring checklist: its symbols are backticked code, heading texts, or none."""

    ref: str
    path: str
    kind: str
    symbols: tuple[str, ...]
    silent: bool


CODE = "code"
HEADING = "heading"
NONE = "none"

# Spec 12.3 "Wiring checklist", in order; `silent` marks the rows whose "Fails if skipped" cell says silent.
WIRING_ROWS = (
    WiringRow("A1", "vidbyte/lib/enums/model_provider.py", CODE, ("ModelProvider",), False),
    WiringRow("A2", "vidbyte/lib/enums/model_provider.py", CODE, ("_usage_class_map",), True),
    WiringRow("A3", "vidbyte/lib/constants/jev.py", CODE, ("PROVIDER_API_KEY_ENV_VARS",), False),
    WiringRow("A4", "vidbyte/lib/registries/models.py", CODE, ("DEFAULT_PROVIDER_MODELS",), False),
    WiringRow("A5", "vidbyte/lib/registries/models.py", CODE, ("DEFAULT_ENDPOINTS",), False),
    WiringRow("A6", "vidbyte/lib/constants/runners.py", CODE, ("MODEL_PROVIDER_RUNNER_TYPE_MAP",), False),
    WiringRow("A7", "vidbyte/lib/constants/runners.py", CODE, ("MODEL_RUNNER_TYPE_MAP",), False),
    WiringRow("A8", "vidbyte/lib/constants/runners.py", CODE, ("PROVIDER_DEFAULT_RUNNER_TYPE_MAP",), False),
    WiringRow("A9", "vidbyte/lib/enums/model_modality.py", CODE, ("_MODEL_NAME_MODALITY_MAP",), False),
    WiringRow("A10", "vidbyte/lib/enums/model_modality.py", CODE, ("ModelNameModality",), True),
    WiringRow("A11", "vidbyte/providers/compatible.py", CODE, ("OpenAICompatibleProvider",), False),
    WiringRow("A12", "vidbyte/providers/__init__.py", CODE, ("ModelProviders",), False),
    WiringRow("A13", "vidbyte/lib/configs/structured_output.py", CODE, ("PROVIDER_SUPPORT",), True),
    WiringRow("B1", "vidbyte/lib/registries/pricing.py", CODE, ("PROVIDER_PRICING",), False),
    WiringRow("B2", "vidbyte/lib/registries/pricing.py", CODE, ("PRICING_AS_OF",), False),
    WiringRow("B3", "lint/pricebook_vintage_lock.json", NONE, (), False),
    WiringRow("B4", "tests/features/sdk_model_catalog/test_catalog_pricing_contract.py", CODE, ("test_the_pricebook_vintage_names_this_refresh",), False),
    WiringRow("B5", "tests/features/sdk_model_catalog/test_catalog_pricing_contract.py", CODE, ("EXPECTED_RATES", "ADDED_MODELS"), True),
    WiringRow("B6", "vidbyte/lib/registries/README.md", HEADING, ("Cache Pricing Source Citations",), True),
    WiringRow("C1", "vidbyte/lib/registries/provider_keys.py", CODE, ("ProviderKeyMatcher.KEY_FORMATS",), False),
    WiringRow("C2", "vidbyte/lib/registries/provider_keys.py", CODE, ("ProviderKeyMatcher.FORMAT_BOUND_PROVIDERS",), False),
    WiringRow("C3", "vidbyte/lib/registries/provider_keys.py", CODE, ("ProviderKeyMatcher.RESERVED_PREFIXES",), False),
    WiringRow("C4", "vidbyte/lib/registries/README.md", HEADING, ("Provider Key Format Sources",), True),
    WiringRow("C5", "tests/features/sdk_provider_keys/test_provider_keys_contract.py", CODE, ("test_the_key_format_tables_follow_table_f_table_a_and_the_reserved_prefixes",), False),
    WiringRow("C6", "tests/features/sdk_provider_keys/test_provider_keys_matching.py", CODE, ("FORMAT_BOUND", "TableFAndATests", "UniqueAssignmentTests"), False),
    WiringRow("C7", "tests/features/sdk_provider_keys/provider_keys_fixtures.py", CODE, ("VENDOR_BASES", "__all__"), False),
    WiringRow("C8", "tests/features/sdk_provider_keys/test_provider_keys_property.py", CODE, ("POOL", "PROVIDERS", "PROVEN"), True),
    WiringRow("C9", "tests/features/sdk_provider_keys/test_provider_keys_modes.py", CODE, ("UnsendableKeyTests",), False),
    WiringRow("C10", "tests/features/sdk_provider_keys/test_provider_keys_modes.py", CODE, ("GatewayShapeTests",), True),
    WiringRow("C11", "tests/features/sdk_managed_text/managed_text_fixtures.py", CODE, ("UNMANAGED_TEXT_PROVIDERS",), True),
    WiringRow("C12", "tests/test_agent_pricing.py", CODE, ("test_usage_class_dispatches_compatible_providers",), False),
    WiringRow("D1", "vidbyte/providers/README.md", HEADING, ("Endpoint And Auth Matrix", "Official Provider Documentation"), True),
    WiringRow("D2", "README.md", CODE, ("Prefixes:", "Other keys:"), True),
)
WIRING_PATHS = frozenset(row.path for row in WIRING_ROWS)

# The reference swap regression wiring row C6 is modelled on (spec 12.3 C6, D-13, R-6).
SWAP_REFERENCE_TEST = "test_an_openai_access_token_beside_a_deepseek_key_is_refused_not_swapped"


@dataclass(frozen=True)
class MarkdownLine:
    """One source line: `kind` is prose, fence (a delimiter) or code; `info` is the fence's first info word."""

    number: int
    text: str
    kind: str
    info: str


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*$")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _classify(text: str) -> tuple[MarkdownLine, ...]:
    # Mark each line as prose, a fence delimiter, or code inside a fence, remembering the fence's info word.
    lines: list[MarkdownLine] = []
    fence: tuple[str, int, str] | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if fence is None:
            opening = _FENCE_OPEN.match(raw)
            if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
                words = opening.group(2).strip().split()
                fence = (opening.group(1)[0], len(opening.group(1)), words[0].lower() if words else "")
                lines.append(MarkdownLine(number, raw, "fence", fence[2]))
            else:
                lines.append(MarkdownLine(number, raw, "prose", ""))
            continue
        closing = _FENCE_CLOSE.match(raw)
        if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= fence[1]:
            lines.append(MarkdownLine(number, raw, "fence", fence[2]))
            fence = None
        else:
            lines.append(MarkdownLine(number, raw, "code", fence[2]))
    return tuple(lines)


class MarkdownDoc:
    """A Markdown document, or one section of it, read with fenced code kept apart from prose."""

    def __init__(self, lines: tuple[MarkdownLine, ...], label: str) -> None:
        self.lines = lines
        self.label = label

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    def squashed(self) -> str:
        # Collapse every run of whitespace, so a rule that wraps across lines still reads as one phrase.
        return " ".join(self.text.split())

    def h2_headings(self) -> list[str]:
        return [line.text.rstrip() for line in self.lines if line.kind == "prose" and re.match(r"^## (?!#)", line.text)]

    def section(self, heading: str) -> MarkdownDoc:
        # The body under one exact H2 heading, up to the next H1 or H2 outside a fence.
        starts = [index for index, line in enumerate(self.lines) if line.kind == "prose" and line.text.rstrip() == heading]
        assert len(starts) == 1, f"{self.label}: expected exactly one '{heading}' heading outside code fences, found {len(starts)}"
        end = next((index for index in range(starts[0] + 1, len(self.lines)) if self.lines[index].kind == "prose" and re.match(r"^#{1,2} (?!#)", self.lines[index].text)), len(self.lines))
        return MarkdownDoc(self.lines[starts[0] + 1 : end], f"{self.label} {heading}")

    def shell_commands(self) -> list[str]:
        # Logical command lines from sh/bash fences: backslash continuations joined, blank and comment-only lines dropped.
        commands: list[str] = []
        pending = ""
        for line in self.lines:
            if line.kind != "code" or line.info not in SHELL_INFOS:
                if pending:
                    commands.append(pending)
                    pending = ""
                continue
            body = (pending + " " + line.text.strip()).strip() if pending else line.text.strip()
            pending = ""
            body = body.removeprefix("$ ")
            if body.endswith("\\"):
                pending = body[:-1].rstrip()
            elif body and not body.startswith("#"):
                commands.append(body)
        if pending:
            commands.append(pending)
        return commands

    def code_spans(self) -> list[str]:
        return [match.group(2).strip() for line in self.lines if line.kind == "prose" for match in _CODE_SPAN.finditer(line.text)]

    def fenced_blocks(self) -> list[list[str]]:
        # The body lines of each fenced block, in order, delimiters excluded.
        blocks: list[list[str]] = []
        inside = False
        for line in self.lines:
            if line.kind == "fence":
                inside = not inside
                if inside:
                    blocks.append([])
            elif line.kind == "code" and blocks:
                blocks[-1].append(line.text)
        return blocks

    def commands(self) -> list[str]:
        # Everything an agent could run verbatim, in document order: each prose line's code spans, and each fenced
        # shell block's logical lines at the place the block sits.
        commands: list[str] = []
        index = 0
        while index < len(self.lines):
            line = self.lines[index]
            if line.kind == "code" and line.info in SHELL_INFOS:
                end = index
                while end < len(self.lines) and self.lines[end].kind == "code" and self.lines[end].info in SHELL_INFOS:
                    end += 1
                commands += MarkdownDoc(self.lines[index:end], self.label).shell_commands()
                index = end
                continue
            if line.kind == "prose":
                commands += [match.group(2).strip() for match in _CODE_SPAN.finditer(line.text)]
            index += 1
        return commands

    def table_rows(self, header: str) -> list[str]:
        # The raw rows under one exact header line (prose only), stopping at the first line that is not a table row.
        starts = [index for index, line in enumerate(self.lines) if line.kind == "prose" and line.text.rstrip() == header]
        assert len(starts) == 1, f"{self.label}: expected exactly one table header line {header!r}, found {len(starts)}"
        start = starts[0]
        assert start + 1 < len(self.lines) and re.match(r"^\|\s*:?-{3,}", self.lines[start + 1].text), f"{self.label}: the line after {header!r} must be the table delimiter row"
        rows: list[str] = []
        for line in self.lines[start + 2 :]:
            if line.kind != "prose" or not line.text.startswith("|"):
                break
            rows.append(line.text.rstrip())
        return rows


def read_markdown(path: Path, spec_ref: str) -> MarkdownDoc:
    # A missing file keeps the pack red with a message naming the spec row that creates it.
    assert path.is_file(), f"{path.relative_to(REPO_ROOT).as_posix()} does not exist; {spec_ref} creates it"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"{path.relative_to(REPO_ROOT).as_posix()} is empty; {spec_ref} defines its content"
    return MarkdownDoc(_classify(text), path.relative_to(REPO_ROOT).as_posix())


def split_row(line: str) -> list[str]:
    # Split a GFM table row on unescaped pipes; `\|` stays inside its cell, as GitHub renders it.
    cells = _UNESCAPED_PIPE.split(line.strip())
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def first_index(commands: list[str], pattern: str) -> int:
    # The index of the first command matching a regex, or -1, so an ordering check can name what is missing.
    return next((index for index, command in enumerate(commands) if re.search(pattern, command)), -1)


@dataclass(frozen=True)
class SedPrint:
    """One `s<d>pattern<d>replacement<d>flags` script with the p flag, as `sed -n` runs it."""

    pattern: str
    replacement: str
    delimiter: str


_SED_SCRIPT = re.compile(r"\bsed\s+-n\s+(?:-e\s+)?'([^']*)'")


def sed_print_expressions(command: str) -> list[SedPrint]:
    # Find each single-quoted `sed -n 's...p'` script and split it on its unescaped delimiter.
    found: list[SedPrint] = []
    for script in _SED_SCRIPT.findall(command):
        if len(script) < 2 or script[0] != "s":
            continue
        delimiter, parts, buffer, index = script[1], [], "", 2
        while index < len(script):
            if script[index] == "\\" and index + 1 < len(script):
                buffer += script[index : index + 2]
                index += 2
                continue
            if script[index] == delimiter:
                parts.append(buffer)
                buffer = ""
            else:
                buffer += script[index]
            index += 1
        parts.append(buffer)
        if len(parts) == 3 and "p" in parts[2]:
            found.append(SedPrint(parts[0], parts[1], delimiter))
    return found


class SedEmulator:
    """Runs one `sed -n 's/P/R/p'` script over text with Python's re, after translating P from POSIX BRE."""

    _TOKEN = re.compile(r"\\.|\[\^?\]?(?:\[:[a-z]+:\]|[^\]])*\]|.", re.DOTALL)
    _ESCAPED: ClassVar[dict[str, str]] = {"(": "(", ")": ")", "{": "{", "}": "}", "+": "+", "?": "?", "|": "|", "n": "\n", "t": "\t", "<": r"\b", ">": r"\b"}
    _CLASSES: ClassVar[dict[str, str]] = {"[:digit:]": "0-9", "[:alpha:]": "A-Za-z", "[:alnum:]": "A-Za-z0-9", "[:upper:]": "A-Z", "[:lower:]": "a-z", "[:space:]": r"\s", "[:blank:]": r" \t", "[:xdigit:]": "0-9A-Fa-f"}

    def translate(self, expression: SedPrint) -> re.Pattern[str]:
        # Map each BRE token to Python: \( \) become groups, bare ( ) + ? { } | become literals, brackets keep their sets.
        parts: list[str] = []
        for token in self._TOKEN.findall(expression.pattern):
            if token.startswith("\\") and len(token) == 2:
                escaped = token[1]
                parts.append(token if escaped.isdigit() else self._ESCAPED.get(escaped, re.escape(escaped)))
            elif token.startswith("[") and len(token) > 1:
                parts.append(self._bracket(token))
            else:
                parts.append("\\" + token if token in "(){}+?|" else token)
        return re.compile("".join(parts))

    def _bracket(self, token: str) -> str:
        # POSIX bracket contents are literal except ranges and classes; Python needs \ [ ] escaped inside a set.
        body = token[1:-1]
        negate = body.startswith("^")
        body = body[1:] if negate else body
        pieces = [self._CLASSES.get(part) or "".join("\\" + char if char in "\\[]^" else char for char in part) for part in re.split(r"(\[:[a-z]+:\])", body)]
        return "[" + ("^" if negate else "") + "".join(pieces) + "]"

    def print_lines(self, expression: SedPrint, text: str) -> list[str]:
        # Like `sed -n 's/P/R/p'`: for each line where P matches, print the line with the first match replaced.
        compiled = self.translate(expression)
        printed: list[str] = []
        for line in text.splitlines():
            match = compiled.search(line)
            if match:
                printed.append(line[: match.start()] + self._expand(expression.replacement, match) + line[match.end() :])
        return printed

    def _expand(self, replacement: str, match: re.Match[str]) -> str:
        # sed replacement syntax: \1..\9 are groups, & is the whole match, \x is a literal x.
        out: list[str] = []
        index = 0
        while index < len(replacement):
            char = replacement[index]
            if char == "\\" and index + 1 < len(replacement):
                following = replacement[index + 1]
                out.append((match.group(int(following)) or "") if following.isdigit() else ("\n" if following == "n" else following))
                index += 2
                continue
            out.append(match.group(0) if char == "&" else char)
            index += 1
        return "".join(out)
