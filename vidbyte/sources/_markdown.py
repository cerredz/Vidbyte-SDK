"""Context Protocol Header

Description:
    Tiny stdlib-only markdown helpers shared by the document and llms.txt loaders.
Purpose:
    Extracts the first H1 title, parses a markdown link bullet, and slugifies a name for
    stable IDs, without pulling in a markdown parsing dependency.
Architecture:
    - first_h1_title: First "# Title" in a document, or None.
    - parse_link_bullet: "- [text](url): note" -> (text, url, note) or None.
    - slugify: Lowercase hyphenated slug used to build deterministic IDs.
Relations:
    Consumed by vidbyte.sources.document and vidbyte.sources.llms_txt.parser.
"""

from __future__ import annotations

import re

# Conservative, anchored patterns (ReDoS-safe): a link target is any run of non-")" chars,
# allowed to be empty so the llms.txt parser can reject empty targets explicitly.
_LINK_RE = re.compile(r"^\s*-\s*\[(?P<text>[^\]]+)\]\((?P<url>[^)]*)\)\s*(?::\s*(?P<note>.*))?$")
_H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def first_h1_title(text: str) -> str | None:
    # Returns the first markdown H1 ("# Title") found in the text, or None when absent.
    match = _H1_RE.search(text)
    return match.group("title").strip() if match else None


def parse_link_bullet(line: str) -> tuple[str, str, str | None] | None:
    # Parses "- [text](url): note" into (text, url, note); returns None if not a link bullet.
    match = _LINK_RE.match(line)
    if match is None:
        return None
    note = match.group("note")
    return (match.group("text").strip(), match.group("url").strip(), note.strip() if note else None)


def slugify(name: str, *, max_len: int = 48) -> str:
    # Lowercases, replaces non-alphanumeric runs with hyphens, trims, and never returns empty.
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or "item"
