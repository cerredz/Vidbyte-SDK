"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_wiring_checklist.py

PURPOSE: Prove the wiring checklist in references/provider-run.md is the spec r3 section 12.3 table and still matches the tree: the header and the 33 refs in order, the section 8.5 cell grammar, every path and symbol present in the file it names, the silent rows marked, the swap regression in row C6, and the checklist paths that SKILL.md's own sed command prints for result check (2).
ROLE IN CODEBASE: Integration layer of tests/features/onboard_model_provider_skill/ (spec AC-4, AC-5 last clause, AC-7 C6 and collision clauses; INV-14, INV-21 path + symbol; NFR-7; D-12, D-13, D-21, D-28; EC-43; reviews R-4, R-8; section 12.3 "Wiring checklist").
ARCHITECTURE NOTE: These tests read the real repository files the checklist names, so a rename of DEFAULT_ENDPOINTS or a README heading on main fails here, in every provider PR, instead of misleading the next provider run (spec section 13, version split). The sed check runs the skill's own command through SedEmulator, so a padded or reformatted row that the command would skip fails here rather than in a live result check.
FUNCTION INVENTORY: test_wiring_table_has_the_spec_header_and_the_33_refs_in_order (W1); test_each_wiring_row_follows_the_cell_grammar_and_names_the_spec_path_and_symbols (W2); test_every_wiring_path_and_symbol_exists_in_the_tree (W3); test_exactly_the_silent_rows_say_silent (W4); test_row_c6_requires_the_swap_case_and_qualify_runs_the_cross_vendor_collision_check (W5); test_verifying_command_prints_exactly_the_checklist_paths (W6); test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays (W7).
COMMON MODIFICATION PATTERNS: When a provider PR legitimately renames a symbol a row names, the provider PR must update the row in provider-run.md; this test is what tells it to. When the spec adds a row, add it to WIRING_ROWS in onboard_skill_fixtures.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not check line numbers; D-21 forbids them and they drift on every merge. 2. Do not assert anything about the provider list; every provider PR grows it. 3. Do not run a shell to execute the sed command.
KNOWN EDGE CASES: Table cells are split on unescaped pipes, so the escaped pipes in the C4 Add cell stay inside it. A dotted symbol A.B passes when both A and B appear with identifier boundaries. Heading texts are matched verbatim anywhere in the file, as the grammar says. Row B3's symbol is the exempt dash. W7 measures the C9 template's comment lines with the longest seed slug in place of <s>, the width a provider PR pastes.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md r3 sections 6.2 (AC-4), 8.5 (cell grammar), 12.3.
TESTS: python -m pytest tests/features/onboard_model_provider_skill/test_onboard_skill_wiring_checklist.py -q
"""

from __future__ import annotations

import re
import textwrap

from tests.features.onboard_model_provider_skill.onboard_skill_fixtures import (
    CODE,
    HEADING,
    NONE,
    PROCEDURE_FILE,
    PROCEDURE_REF,
    REPO_ROOT,
    SEED_VENDORS,
    SKILL_FILE,
    SKILL_REF,
    SWAP_REFERENCE_TEST,
    WIRING_HEADER,
    WIRING_PATHS,
    WIRING_ROWS,
    SedEmulator,
    read_markdown,
    sed_print_expressions,
    split_row,
)

EXEMPT_SYMBOL = "—"
_PATH_CELL = re.compile(r"`([^`]+)`")
_CODE_CELL = re.compile(r"`[^`]+`(?:, `[^`]+`)*")
_HEADING_CELL = re.compile(r"[^`;|]+(?:; [^`;|]+)*")

# Row C9's test template in section 5 (final wording, S5 repair 1): each statement the DIRECT key proof rests on.
C9_TEST_DEF = "def test_a_<s>_key_from_a_mixed_list_reaches_<s>_unchanged_in_direct(self) -> None:"
C9_MODEL_TEST = "test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct"
C9_STATEMENTS = (
    C9_TEST_DEF,
    "from vidbyte.lib.config import TextModelMode",
    "vendor = ScriptedGateway(provider_answer(ModelProvider.<E>))",
    "with patch.dict(os.environ, {}, clear=True):",
    'TextModelRunner(TextModelConfig(provider="<s>", model="<default id>", api_keys=[K_ANTHROPIC, K_<E>], mode=TextModelMode.DIRECT), transport=vendor).run("Hi")',
    "[sent] = vendor.requests",
    'self.assertTrue(str(sent["url"]).startswith("<base URL>/"), sent["url"])',
    'self.assertEqual(header(sent, "authorization"), f"Bearer {K_<E>}")',
    "self.assertNotIn(K_ANTHROPIC, flat(sent))",
    'self.assertEqual(sent["json_body"]["model"], "<default id>")',
)
COMMENT_RULE = "- Comments go above the line they explain, as `#` lines wrapped at 72 columns. Every price block and every key rule carries its source URL in that comment."
C9_NAMES = ("ScriptedGateway", "provider_answer", "header", "flat", "K_ANTHROPIC", "TextModelRunner", "TextModelConfig", "ModelProvider", "patch", "os", "UnsendableKeyTests")


def _wiring_rows() -> list[list[str]]:
    section = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 5. Wiring checklist")
    return [split_row(line) for line in section.table_rows(WIRING_HEADER)]


def _symbol_cell(cell: str) -> tuple[str, tuple[str, ...]]:
    # Read one Symbol cell with the spec 8.5 grammar: the exempt dash, backticked symbols, or heading texts.
    if cell in (EXEMPT_SYMBOL, f"`{EXEMPT_SYMBOL}`"):
        return NONE, ()
    if _CODE_CELL.fullmatch(cell):
        return CODE, tuple(re.findall(r"`([^`]+)`", cell))
    if _HEADING_CELL.fullmatch(cell):
        return HEADING, tuple(part.strip() for part in cell.split("; "))
    return "invalid", ()


def _code_symbol_present(symbol: str, text: str) -> bool:
    # A dotted symbol A.B means both A and B appear in the file (spec 8.5 cell grammar).
    return all(re.search(rf"(?<![\w]){re.escape(part)}(?![\w])", text) for part in symbol.split(".") if part)


def test_wiring_table_has_the_spec_header_and_the_33_refs_in_order() -> None:
    # W1 · AC-4: the header is exact and the refs are A1..A13, B1..B6, C1..C12, D1..D2, so no row was dropped or reordered.
    rows = _wiring_rows()

    assert len(WIRING_ROWS) == 33
    assert [row[0] for row in rows] == [row.ref for row in WIRING_ROWS]


def test_each_wiring_row_follows_the_cell_grammar_and_names_the_spec_path_and_symbols() -> None:
    # W2 · AC-4 / NFR-7 / D-21: five cells; the Path cell is one backticked path, the spec's; the Symbol cell parses with
    # the 8.5 grammar into the spec's kind and holds at least the spec's symbols.
    rows = _wiring_rows()
    assert len(rows) == len(WIRING_ROWS)

    problems = []
    for row, expected in zip(rows, WIRING_ROWS):
        if len(row) != 5:
            problems.append(f"{expected.ref}: {len(row)} cells")
            continue
        path = _PATH_CELL.fullmatch(row[1])
        kind, symbols = _symbol_cell(row[2])
        if not path or path.group(1) != expected.path:
            problems.append(f"{expected.ref}: Path cell {row[1]!r} is not `{expected.path}`")
        if kind != expected.kind or not set(expected.symbols) <= set(symbols):
            problems.append(f"{expected.ref}: Symbol cell {row[2]!r} must be {expected.kind} naming {expected.symbols}")
        if not row[3].strip() or not row[4].strip():
            problems.append(f"{expected.ref}: the Add and Fails if skipped cells must be filled")
    assert problems == []


def test_every_wiring_path_and_symbol_exists_in_the_tree() -> None:
    # W3 · AC-4 / INV-21: every path exists and every symbol or heading the row names appears in that file at HEAD;
    # rows whose symbol is the dash are exempt from the symbol check only.
    rows = _wiring_rows()
    assert len(rows) == len(WIRING_ROWS)

    missing = []
    for row in rows:
        path = _PATH_CELL.fullmatch(row[1])
        target = REPO_ROOT / path.group(1) if path else None
        if target is None or not target.is_file():
            missing.append(f"{row[0]}: path {row[1]}")
            continue
        text = target.read_text(encoding="utf-8")
        kind, symbols = _symbol_cell(row[2])
        absent = [symbol for symbol in symbols if not (_code_symbol_present(symbol, text) if kind == CODE else symbol in text)]
        missing += [f"{row[0]}: {symbol!r} not in {path.group(1)}" for symbol in absent]
        if kind == "invalid":
            missing.append(f"{row[0]}: Symbol cell {row[2]!r} does not parse")
    assert missing == []


def test_exactly_the_silent_rows_say_silent() -> None:
    # W4 · section 12.3: "silent means no check fails if the row is skipped"; an unmarked silent row is a row a provider
    # run can skip without any test noticing, so the procedure must warn about exactly these.
    rows = _wiring_rows()
    assert len(rows) == len(WIRING_ROWS)

    marked = [row[0] for row in rows if len(row) == 5 and re.search(r"\bsilent\b", row[4], flags=re.IGNORECASE)]
    assert marked == [row.ref for row in WIRING_ROWS if row.silent]


def test_row_c6_requires_the_swap_case_and_qualify_runs_the_cross_vendor_collision_check() -> None:
    # W5 · AC-7 / D-13 / R-6 / EC-33: every provider adds a swap case modelled on the DeepSeek regression in both
    # orders, and Qualify checks a new prefix against gitleaks and GitHub secret scanning for existing vendors.
    rows = {row[0]: row for row in _wiring_rows()}
    assert "C6" in rows and len(rows["C6"]) == 5
    add = rows["C6"][3]

    assert SWAP_REFERENCE_TEST in add
    assert re.search(r"\bswap", add, flags=re.IGNORECASE) and re.search(r"\border", add, flags=re.IGNORECASE)
    assert re.search(rf"def {SWAP_REFERENCE_TEST}\(", (REPO_ROOT / "tests/features/sdk_provider_keys/test_provider_keys_matching.py").read_text(encoding="utf-8"))
    qualify = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 3. Qualify").squashed()
    assert re.search(r"gitleaks", qualify, flags=re.IGNORECASE) and re.search(r"secret[- ]scanning", qualify, flags=re.IGNORECASE)
    assert "key-prefix-collision" in qualify


def test_c9_template_proves_the_vendor_key_leaves_as_its_bearer_token_and_the_other_key_stays() -> None:
    # W7 · C9 row "new proof" / D-12 / EC-43 / review R-8: the one test that proves a key reaches the vendor's endpoint in
    # its auth header sends a mixed key list in DIRECT mode and asserts the Bearer header, the absent other key, the URL
    # and the model; it must compile, and every name it uses must exist in the file it is added to.
    section = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 5. Wiring checklist")
    blocks = [body for info, body in section.fenced_blocks_with_info() if info == "python" and any(C9_TEST_DEF in line for line in body)]
    assert len(blocks) == 1, "## 5. Wiring checklist holds the C9 test template as one python fence"
    lines = [line.strip() for line in blocks[0]]

    assert [statement for statement in C9_STATEMENTS if not any(line.startswith(statement) for line in lines)] == []
    assert not [line for line in lines if re.search(r"x-api-key|TextModelMode\.AUTO", line)], "the template asserts the Bearer header in DIRECT mode only"
    source = "\n".join(blocks[0]).replace("<E>", "VENDOR").replace("<s>", "vendor")
    compile(textwrap.dedent(source), "c9_template.py", "exec")
    target = (REPO_ROOT / "tests/features/sdk_provider_keys/test_provider_keys_modes.py").read_text(encoding="utf-8")
    assert [name for name in C9_NAMES if not re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", target)] == [], "every name the template uses is importable in the C9 file"
    assert f"def {C9_MODEL_TEST}(" in target and f"`{C9_MODEL_TEST}`" in section.text, "the template is modelled on the existing Meta test"
    rows = {row[0]: row for row in _wiring_rows()}
    assert "C9" in rows and "`authorization` is `Bearer <fake>`" in rows["C9"][3] and "the other key is absent" in rows["C9"][3]

    # Review R-4 (S5 repair 1): every provider PR pastes this template, so its comments obey the procedure's own
    # 72-column rule even with the longest seed slug in place of <s>.
    longest = max((slug for slug, _enum in SEED_VENDORS), key=len)
    comments = [line for line in blocks[0] if line.lstrip().startswith("#")]
    assert comments and [line for line in comments if len(line.replace("<s>", longest)) > 72] == [], f"comments wrap at 72 columns with <s> = {longest}"
    assert any(COMMENT_RULE in line for line in section.prose_lines()), "the procedure states the 72-column comment rule"


def test_verifying_command_prints_exactly_the_checklist_paths() -> None:
    # W6 · AC-5 / D-28 / FR-11 check (2): the command SKILL.md runs over the procedure prints one path per wiring row,
    # in order, so a padded or reformatted row cannot drop a path from the allowed diff set.
    verifying = read_markdown(SKILL_FILE, SKILL_REF).section("## Verifying a result")
    commands = [command for command in verifying.commands() if re.search(r"\bsed\s+-n\b", command) and re.search(r"references/provider-run\.md|\$\{?PROCEDURE\}?", command)]
    assert commands, "## Verifying a result must print the checklist paths with a `sed -n` command over references/provider-run.md"
    procedure = PROCEDURE_FILE.read_text(encoding="utf-8")

    for command in commands:
        expressions = sed_print_expressions(command)
        assert len(expressions) == 1, f"expected one `sed -n 's...p'` script in {command!r}"
        printed = SedEmulator().print_lines(expressions[0], procedure)
        assert printed == [row.path for row in WIRING_ROWS], f"{command!r} must print one path per wiring row, in order"
        assert set(printed) == WIRING_PATHS
