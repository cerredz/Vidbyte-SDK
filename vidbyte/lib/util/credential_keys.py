"""FILE: vidbyte/lib/util/credential_keys.py

PURPOSE:
    Decides whether a mapping key names a credential, by exact normalized name
    or credential suffix, without misclassifying ordinary words such as
    author, token_estimate, or auth_flow.

ROLE IN CODEBASE:
    Shared by vidbyte/harnesses/serialization.py (HarnessSecretPolicy, which
    subclasses it for config rejection and capture scrubbing) and by
    vidbyte/sessions/serialization.py (checkpoint trace artifacts). It lives
    here because sessions sit below harnesses and may not import them.

ARCHITECTURE NOTE:
    A static-policy class with no SDK dependencies: keys are lower-cased,
    non-alphanumeric runs collapse to "_", and the result must equal a known
    credential name or end in a credential suffix.

FUNCTION INVENTORY:
    CredentialKeyPolicy.is_secret_key(key) -> bool: True for credential names
    such as api_key, access_token, client_secret, github_token.

COMMON MODIFICATION PATTERNS:
    Add a credential name to _SECRET_KEYS or a suffix to _SECRET_SUFFIXES;
    both harness capture and session trace artifacts pick it up.

WHAT NOT TO DO IN THIS FILE:
    1. Do not switch to substring matching; it deletes field names such as
       token_estimate and author.
    2. Do not import any SDK feature package.

KNOWN EDGE CASES:
    Keys are classified by name only; a secret stored under an innocent key
    is not detected here.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/trace-artifact-precise-secret-keys.md

TESTS:
    tests/test_durable_sessions.py (trace artifact checkpoint and bundle tests)
    and tests/test_harness_redaction.py cover this policy through its callers.
"""

from __future__ import annotations

import re


class CredentialKeyPolicy:
    """Exact-name and suffix classifier for credential-like mapping keys."""

    _SECRET_KEYS = frozenset({
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "token",
        "secret",
        "client_secret",
        "private_key",
        "secret_key",
        "access_key",
        "access_key_id",
        "session_token",
        "bearer_token",
        "password",
        "credential",
        "credentials",
        "authorization",
        "auth",
    })
    _SECRET_SUFFIXES = ("_api_key", "_private_key", "_secret_key", "_access_key", "_access_key_id", "_token", "_secret", "_password")

    @classmethod
    def is_secret_key(cls, key: str) -> bool:
        # Matches exact normalized credential names without misclassifying words such as author.
        normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
        return normalized in cls._SECRET_KEYS or normalized.endswith(cls._SECRET_SUFFIXES)


__all__ = ["CredentialKeyPolicy"]
