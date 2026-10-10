# llms.txt link note separators

## Summary

`LlmsTxtRegex.LINK_BULLET` only accepted `- [text](url): note`. Any other note
separator made the full-line match fail, and `LlmsTxtParser` raises
`SourceParseError` for an unmatched link bullet, so one `- [x](u) — note` line
rejected the whole document. The SDK's own `llms.txt` uses em-dash notes and could
not be parsed by the SDK. This change lets the note be introduced by `:`, `-`,
en-dash, or em-dash. Everything else, including fail-closed handling of malformed
links and of unseparated trailing text, is unchanged.

## Flow chart

```mermaid
flowchart TD
    A[line in a section] --> B{starts with '- ['?}
    B -- no --> Z[skip line]
    B -- yes --> C{LINK_BULLET full match?}
    C -- "[text](url)" alone --> D[link, note None]
    C -- "[text](url) then : - en-dash em-dash note" --> E[link, note stripped]
    C -- "no match: unclosed, other trailing text" --> F[SourceParseError]
    D --> G{url empty?}
    E --> G
    G -- yes --> F
    G -- no --> H[LlmsTxtLink]
```

## Usage example

```python
from vidbyte.sources import parse_llms_txt

raw = "# Docs\n## Guides\n- [Providers](providers.md) — Provider references.\n".encode()
link = parse_llms_txt(raw, url="https://ex.com/llms.txt").sections[0].links[0]
assert link.note == "Provider references."
```

## How it works

The optional note group in `LINK_BULLET` changes from `(?::\s*(?P<note>.*))?` to
`(?:[:\-–—]\s*(?P<note>.*))?`. The leading `\s*` before it already allows
the space in ` - ` / ` — `. The pattern stays anchored, so text after the link
without one of these separators still fails closed, as do `[x](` and `[x]()`.

## Files

- `vidbyte/sources/regex/regex.py`: the pattern and its helper comment.
- `tests/test_sources_llms_txt.py`: separator variants, no-note form, unseparated
  trailing text, and the repository `llms.txt` parsing.

## Risks

A note that legitimately starts with a hyphen after a colon is unaffected (the colon
is consumed first). Lines like `- [x](u)-suffix` now parse with note `suffix`
instead of failing; that is consistent with the llmstxt.org reference parser, which
does not fail on trailing text.

## Verification

`python -m pytest -q tests/test_sources_llms_txt.py`, `python lint/run.py`,
`python -m pytest -q -x`, and CI.
