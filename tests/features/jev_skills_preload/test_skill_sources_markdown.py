"""FILE: tests/features/jev_skills_preload/test_skill_sources_markdown.py

PURPOSE: Pin the shared SKILL.md parser: a valid file yields the exact bytes after the closing frontmatter line as text, the YAML description, and the entry's name and label; every malformed file yields INVALID_SKILL with an SDK-written detail that never quotes YAML errors or skill text, and never raises.
ROLE IN CODEBASE: Covers spec INV-11, INV-18, FR-12, D-12 to D-14, D-29 and EC-25 to EC-35, EC-109, EC-110 for vidbyte/agents/skills/markdown.py (SkillMarkdown.parse), which every file-backed source uses.
ARCHITECTURE NOTE: SkillMarkdown.parse is a real seam (spec section 13), so these tests call it directly with raw bytes and patch nothing; yaml and the strict UTF-8 decoder run for real.
FUNCTION INVENTORY: test_valid_file_keeps_the_exact_body_after_the_closing_line; test_malformed_file_is_invalid_with_an_sdk_written_detail; test_yaml_error_text_and_skill_text_never_reach_the_detail.
COMMON MODIFICATION PATTERNS: A new parsing rule adds one row to the valid or the malformed table; keep each row's raw bytes literal so line endings are visible.
WHAT NOT TO DO IN THIS FILE: 1. Do not normalize line endings in the fixtures; CRLF bodies must come back byte for byte. 2. Do not assert full detail sentences; assert only the keyword the spec's "user sees" column names.
KNOWN EDGE CASES: PyYAML 6.0.2 raises ValueError for impossible dates and RecursionError for about 500 nested brackets, outside yaml.YAMLError; both must still end as INVALID_SKILL. Only one leading byte-order mark is removed, so a second one makes the first line something other than ---.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 6.3 SKILL.md parsing, 8.1 D-12 and D-29, 9.2 parser mapping)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_markdown.py
"""

from __future__ import annotations

import pytest
import yaml

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills.markdown import SkillMarkdown

    from vidbyte import SkillUnavailableReason
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

BOM = b"\xef\xbb\xbf"
LABEL = "local:pdf"
BODY_MARKER = "BODY-MARKER-7f3a"
SECRET_LINE = "SECRET-LINE-MARKER"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


# YAML keeps a folded value's final line break only if the frontmatter text it receives ends with one; the spec
# does not say whether the line break before the closing line is part of that text, so either value is accepted.
FOLDED = ("Plans SQL migrations and reviews them.", "Plans SQL migrations and reviews them.\n")

# (case, raw bytes, expected description or the accepted descriptions, expected text)
VALID_FILES = [
    ("bom", BOM + b"---\nname: pdf\ndescription: Reads PDFs.\n---\nBody line\n", "Reads PDFs.", "Body line\n"),
    ("crlf body kept", b"---\r\nname: pdf\r\ndescription: Reads PDFs.\r\n---\r\n  Indented\r\nnext\r\n", "Reads PDFs.", "  Indented\r\nnext\r\n"),
    ("trailing spaces after delimiters", b"---   \nname: pdf\ndescription: Reads PDFs.\n---  \nBody", "Reads PDFs.", "Body"),
    ("folded description", b"---\nname: pdf\ndescription: >\n  Plans SQL migrations\n  and reviews them.\n---\nBody\n", FOLDED, "Body\n"),
    ("frontmatter name differs from the entry", b"---\nname: some-other-name\ndescription: Reads PDFs.\n---\nBody\n", "Reads PDFs.", "Body\n"),
    ("rule inside the body", b"---\nname: pdf\ndescription: Reads PDFs.\n---\nIntro\n---\nAfter the rule\n", "Reads PDFs.", "Intro\n---\nAfter the rule\n"),
    ("quoted value holding dashes", b'---\nname: pdf\ndescription: "a --- b"\n---\nBody\n', "a --- b", "Body\n"),
    ("leading blank lines and tabs kept", b"---\nname: pdf\ndescription: Reads PDFs.\n---\n\n\n\tStep one\n```\ncode\n```", "Reads PDFs.", "\n\n\tStep one\n```\ncode\n```"),
    ("bom with crlf", BOM + b"---\r\nname: pdf\r\ndescription: Reads PDFs.\r\n---\r\nBody\r\n", "Reads PDFs.", "Body\r\n"),
]


@pytest.mark.parametrize(("case", "raw", "description", "text"), VALID_FILES, ids=[row[0] for row in VALID_FILES])
def test_valid_file_keeps_the_exact_body_after_the_closing_line(case: str, raw: bytes, description: str | tuple[str, ...], text: str) -> None:
    # INV-11, EC-26, EC-27, EC-31, EC-35: trimming or re-joining lines would change indentation-sensitive guidance.
    resolution = SkillMarkdown.parse(raw, name="pdf-entry", source=LABEL)
    assert resolution.reason is None and resolution.detail is None, resolution
    document = resolution.document
    assert document.text == text
    assert document.description in (description if isinstance(description, tuple) else (description,))
    assert (document.name, document.source) == ("pdf-entry", LABEL)


def _file(frontmatter: str, body: str = f"Use the {BODY_MARKER} steps.\n") -> bytes:
    return f"---\n{frontmatter}\n---\n{body}".encode()


# (case, raw bytes, keywords of which the detail must contain at least one, case-insensitively)
MALFORMED_FILES = [
    ("empty file", b"", ("---",)),
    ("no opening line", f"name: pdf\ndescription: Reads PDFs.\n---\n{BODY_MARKER}\n".encode(), ("---",)),
    ("blank line before the opening line", b"\n" + _file("name: pdf\ndescription: Reads PDFs."), ("---",)),
    ("two byte-order marks", BOM + BOM + _file("name: pdf\ndescription: Reads PDFs."), ("---",)),
    ("opening line never closed", f"---\nname: pdf\ndescription: Reads PDFs.\n{BODY_MARKER}\n".encode(), ("clos",)),
    ("frontmatter is not YAML", _file("name: [unclosed\ndescription: Reads PDFs."), ("yaml",)),
    ("frontmatter is a list", _file("- name\n- description"), ("yaml", "mapping")),
    ("frontmatter is a scalar", _file("just some words"), ("yaml", "mapping")),
    ("frontmatter is empty", f"---\n---\n{BODY_MARKER}\n".encode(), ("yaml", "mapping", "name")),
    ("name missing", _file("description: Reads PDFs."), ("name",)),
    ("name blank", _file('name: "   "\ndescription: Reads PDFs.'), ("name",)),
    ("name not text", _file("name: 42\ndescription: Reads PDFs."), ("name",)),
    ("description missing", _file("name: pdf"), ("description",)),
    ("description blank", _file('name: pdf\ndescription: ""'), ("description",)),
    ("description not text", _file("name: pdf\ndescription: 42"), ("description",)),
    ("description is a list", _file("name: pdf\ndescription: [a, b]"), ("description",)),
    ("frontmatter only", b"---\nname: pdf\ndescription: Reads PDFs.\n---\n", ("body",)),
    ("frontmatter only without a final newline", b"---\nname: pdf\ndescription: Reads PDFs.\n---", ("body",)),
    ("whitespace-only body", _file("name: pdf\ndescription: Reads PDFs.", " \n\t\r\n  "), ("body",)),
    ("invalid utf-8 in the body", _file("name: pdf\ndescription: Reads PDFs.")[:-1] + b" \xff\xfe\n", ("utf-8", "utf8")),
    ("invalid utf-8 in the frontmatter", b"---\nname: pdf\xc3\x28\ndescription: Reads PDFs.\n---\nBody\n", ("utf-8", "utf8")),
    ("python object tag", _file("name: pdf\ndescription: !!python/object/apply:os.system ['echo pwned']"), ("yaml",)),
    ("impossible month", _file("name: pdf\ndescription: 2024-13-45"), ("yaml",)),
    ("impossible day in the name", _file("name: 2024-02-30\ndescription: Reads PDFs."), ("yaml",)),
    ("impossible hour", _file("name: pdf\ndescription: !!timestamp 2024-01-01T25:00:00"), ("yaml",)),
    ("500 levels of nesting", _file("name: pdf\ndescription: " + "[" * 500 + "]" * 500), ("yaml",)),
]


@pytest.mark.parametrize(("case", "raw", "keywords"), MALFORMED_FILES, ids=[row[0] for row in MALFORMED_FILES])
def test_malformed_file_is_invalid_with_an_sdk_written_detail(case: str, raw: bytes, keywords: tuple[str, ...]) -> None:
    # EC-25 to EC-34, EC-109, EC-110, D-29: each row must end as data; an escaping ValueError or RecursionError would crash every run.
    resolution = SkillMarkdown.parse(raw, name="pdf", source=LABEL)
    assert resolution.document is None
    assert resolution.reason is SkillUnavailableReason.INVALID_SKILL
    assert resolution.detail and resolution.detail.strip()
    assert any(keyword in resolution.detail.lower() for keyword in keywords), resolution.detail
    # INV-18: a detail never carries the skill's own text.
    assert BODY_MARKER not in resolution.detail


def test_yaml_error_text_and_skill_text_never_reach_the_detail() -> None:
    # EC-29, INV-18: PyYAML error messages quote the offending line, which can hold anything the file holds.
    frontmatter = f"name: [{SECRET_LINE}\ndescription: {SECRET_LINE} again"
    # Non-vacuity: the real YAML error for this frontmatter does quote the marker, so copying it would fail below.
    with pytest.raises(yaml.YAMLError) as yaml_error:
        yaml.safe_load(frontmatter)
    assert SECRET_LINE in str(yaml_error.value)
    resolution = SkillMarkdown.parse(f"---\n{frontmatter}\n---\n{BODY_MARKER}\n".encode(), name="pdf", source=LABEL)
    assert resolution.reason is SkillUnavailableReason.INVALID_SKILL
    assert SECRET_LINE not in resolution.detail
    assert BODY_MARKER not in resolution.detail
