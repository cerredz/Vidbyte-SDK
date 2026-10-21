"""FILE: vidbyte/lib/util/secret_text.py

PURPOSE:
    Replaces every known secret value in a text with a marker, as exact
    text and longest secret first, so a secret that holds a shorter one is
    replaced whole and no fragment of it is left behind.

ROLE IN CODEBASE:
    The canonical exact-text secret scrub. Called by ComposeFailures.error
    in vidbyte/harnesses/native/compose/git.py for every text of a
    ThreadComposeError, and by PromptFitter.fit in
    vidbyte/harnesses/native/compose/texts.py for every spliced prompt
    value. Re-exported from vidbyte/lib/util/__init__.py. Uses only the
    standard library.

ARCHITECTURE NOTE:
    A static-method-only class with no SDK dependencies, like
    SubstringCounter in text.py. The caller names the secrets and the
    marker; nothing is matched by pattern, so a credential-shaped text
    that is not one of the secrets stays as it is.

FUNCTION INVENTORY:
    SecretText.replace_all(text, secrets, marker) -> str: text with every
    non-empty secret replaced by marker, longest first.

COMMON MODIFICATION PATTERNS:
    A caller that also needs pattern-based redaction runs HarnessRedactor
    on the text this returns, as ComposeFailures.error does.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import any SDK module.
    2. Do not replace shorter secrets first; a secret that holds a shorter
       one would then keep the rest of its text.
    3. Do not cap or cut the text here; a caller cuts after the scrub, so
       a cut never splits a secret in half.

KNOWN EDGE CASES:
    An empty secret is skipped, because replacing it would put the marker
    between every two characters. A secret given twice is replaced once.
    Secrets of one length go in sorted order, so the result never depends
    on the order they were given in.

RELATED DOCS:
    docs/spec/native-thread-compose/spec.md (D-28)

TESTS:
    tests/features/harness_compose/test_harness_compose_keys.py
"""

from __future__ import annotations

from collections.abc import Iterable


class SecretText:
    """Exact-text replacement of known secret values."""

    @staticmethod
    def replace_all(text: str, secrets: Iterable[str], marker: str) -> str:
        """Return text with every non-empty secret in secrets replaced by marker, the longest secret first."""
        # @intent secrets-are-replaced-longest-first-as-exact-text
        # A secret can hold a shorter one, so the longest goes first and
        # is replaced whole; matching is exact text, never a pattern.
        unique = sorted({secret for secret in secrets if secret})
        for secret in sorted(unique, key=len, reverse=True):
            text = text.replace(secret, marker)
        return text


__all__ = ["SecretText"]
