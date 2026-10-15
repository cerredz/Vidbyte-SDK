"""FILE: tests/features/sdk_provider_keys/test_provider_keys_property.py

PURPOSE: Proves the algebraic promises of ProviderKeyMatcher.match over many generated lists: the outcome never depends on list order or on the environment (INV-9), and every outcome is either a well-formed ProviderKeys or a ConfigurationError that names no key (INV-10); a returned record passes back through match unchanged (D-13).
ROLE IN CODEBASE: Property layer of tests/features/sdk_provider_keys/ (spec INV-9, INV-10, INV-25, NFR-2). Exercises vidbyte/lib/registries/provider_keys.py only.
ARCHITECTURE NOTE: hypothesis is not a dependency (spec section 13), so cases come from a seeded random.Random and every permutation of each generated list is tried exhaustively. The generator mixes proven keys, unproven keys with and without sk-, a Vidbyte key, None, blanks, padded copies and repeats, over random primaries and configured backups, so both outcomes occur often; a guard fails the test if either outcome becomes rare, which would make the property vacuous.
COMMON MODIFICATION PATTERNS: When table F gains a row, add a proven fake for it to POOL. Raise CASES only if the run stays well under a second.
WHAT NOT TO DO IN THIS FILE: 1. Do not import ProviderKeyMatcher at module level. 2. Do not seed from the clock; a failure must reproduce. 3. Do not compare records from permuted lists with ==; the spec keeps first-appearance order, so compare key_view.
KNOWN EDGE CASES: Lists are capped at five entries so all 120 orders of each can be tried. An error may name a different index for a different order; only the outcome kind and the record's meaning must agree.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 6.1 (INV-9, INV-10) and 9.2 ("Matching").
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_property.py
"""

from __future__ import annotations

import itertools
import os
import random
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import VIDBYTE_KEY
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_GEMINI_AQ,
    K_META,
    K_OPENAI,
    K_OPENAI_2,
    K_OPENROUTER,
    K_SK_UNPROVEN,
    K_SK_UNPROVEN_2,
    K_UNPROVEN,
    K_UNPROVEN_2,
    K_XAI,
    key_view,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError

SEED = 20261012
CASES = 160
MAX_ENTRIES = 5
# Every kind of entry the matcher must handle; None and blanks are skipped, padded copies strip to their key.
POOL: tuple[str | None, ...] = (
    K_ANTHROPIC, K_XAI, K_OPENAI, K_OPENAI_2, K_OPENROUTER, K_GEMINI_AQ, K_META,
    K_UNPROVEN, K_UNPROVEN_2, K_SK_UNPROVEN, K_SK_UNPROVEN_2, VIDBYTE_KEY,
    None, "", "   ", f"  {K_XAI}\n", f"\t{K_UNPROVEN} ",
)
KEYS = tuple(entry.strip() for entry in POOL if entry is not None and entry.strip())
PROVIDERS = (
    ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.XAI, ModelProvider.GEMINI,
    ModelProvider.DEEPSEEK, ModelProvider.KIMI, ModelProvider.MISTRAL, ModelProvider.OPENROUTER, ModelProvider.META,
)
# The provider each proven fake belongs to, spelled from spec section 9.2 table F (never read from KEY_FORMATS).
PROVEN: dict[str, ModelProvider] = {
    K_ANTHROPIC: ModelProvider.ANTHROPIC, K_XAI: ModelProvider.XAI, K_OPENAI: ModelProvider.OPENAI,
    K_OPENAI_2: ModelProvider.OPENAI, K_OPENROUTER: ModelProvider.OPENROUTER, K_GEMINI_AQ: ModelProvider.GEMINI,
    K_META: ModelProvider.META,
}
# Junk provider variables: matching must never read them (INV-9, INV-23).
NOISY_ENVIRONMENT = {"OPENAI_API_KEY": K_SK_UNPROVEN_2, "DEEPSEEK_API_KEY": K_UNPROVEN_2, "VIDBYTE_API_KEY": VIDBYTE_KEY, "XAI_API_KEY": K_XAI}


def generated_cases() -> list[tuple[list[str | None], tuple[ModelProvider, ...], tuple[ModelProvider, ...]]]:
    # Seeded cases: up to five entries; half the time the primary is a provider one of the entries proves (so success is common),
    # otherwise one or two random primaries (sometimes none) and up to two random backups.
    rng = random.Random(SEED)
    cases = []
    for _ in range(CASES):
        entries = [rng.choice(POOL) for _ in range(rng.randint(0, MAX_ENTRIES))]
        owned = [PROVEN[entry.strip()] for entry in entries if entry is not None and entry.strip() in PROVEN]
        if owned and rng.random() < 0.5:
            primaries: tuple[ModelProvider, ...] = (owned[0],)
            others = tuple(rng.sample((ModelProvider.DEEPSEEK, ModelProvider.KIMI, ModelProvider.MISTRAL, ModelProvider.OPENAI), rng.randint(0, 2)))
        else:
            primaries = tuple(rng.sample(PROVIDERS, rng.choice((0, 1, 1, 1, 2))))
            others = tuple(rng.sample(PROVIDERS, rng.randint(0, 2)))
        cases.append((entries, primaries, others))
    return cases


def outcome(entries: list[str | None], primaries: tuple[ModelProvider, ...], others: tuple[ModelProvider, ...]) -> tuple[str, Any]:
    # ("ok", record) or ("refused", error); any other exception escapes and fails the test (INV-10: exactly two outcomes).
    from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

    primary: Any = primaries[0] if len(primaries) == 1 else (primaries or None)
    try:
        return "ok", ProviderKeyMatcher.match(entries, primary=primary, others=others)
    except ConfigurationError as error:
        return "refused", error


class MatchingPropertyTests(unittest.TestCase):
    """INV-9 and INV-10 over every order of every generated list."""

    def test_matching_ignores_list_order_and_the_environment_and_has_exactly_two_outcomes(self) -> None:
        # INV-9, INV-10, NFR-2: the same keys and providers always give the same answer.
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        counts = {"ok": 0, "refused": 0}
        for entries, primaries, others in generated_cases():
            with patch.dict(os.environ, {}, clear=True):
                kind, value = outcome(entries, primaries, others)
            counts[kind] += 1
            reference = key_view(value) if kind == "ok" else None
            context = f"entries={len(entries)} primaries={[p.value for p in primaries]} others={[p.value for p in others]} first-kind={kind}"
            for environment in ({}, NOISY_ENVIRONMENT):
                with patch.dict(os.environ, environment, clear=True):
                    for order in itertools.permutations(entries):
                        other_kind, other_value = outcome(list(order), primaries, others)
                        self.assertEqual(other_kind, kind, context)
                        if kind == "ok":
                            self.assertEqual(key_view(other_value), reference, context)
            if kind == "ok":
                self._assert_well_formed(ProviderKeyMatcher, value, entries, primaries)
            else:
                self._assert_names_no_key(value)
        # Guard against a vacuous property: both outcomes must be common in the generated set.
        self.assertGreater(counts["ok"], CASES // 8, counts)
        self.assertGreater(counts["refused"], CASES // 8, counts)

    def _assert_well_formed(self, matcher: Any, record: Any, entries: list[str | None], primaries: tuple[ModelProvider, ...]) -> None:
        # INV-10: one key per provider, one Vidbyte key, nothing silently dropped, every key where the rules allow it.
        providers = [ModelProvider(getattr(provider, "value", provider)) for provider in record.providers]
        self.assertEqual(len(providers), len(set(providers)))
        self.assertEqual(len(record.keys), len(providers))
        stripped = {entry.strip() for entry in entries if entry is not None and entry.strip()}
        vidbyte_entries = {entry for entry in stripped if entry == VIDBYTE_KEY}
        self.assertEqual(record.vidbyte_api_key, VIDBYTE_KEY if vidbyte_entries else None)
        self.assertEqual(set(record.keys), stripped - vidbyte_entries, "a non-blank entry was dropped or invented")
        for provider, key in zip(providers, record.keys):
            proven = matcher.provider_of(key)
            if proven is not None:
                self.assertIs(proven, provider, "a proven key sits at its table F provider")
            else:
                self.assertTrue(matcher.accepts_unproven(provider, key), "an unproven key sits only where table A allows it")
        self.assertEqual(tuple(ModelProvider(getattr(p, "value", p)) for p in record.matched_primary), tuple(dict.fromkeys(primaries)))
        # D-13: a returned record passes back through unchanged.
        self.assertEqual(matcher.match(record, primary=None), record)

    def _assert_names_no_key(self, error: ConfigurationError) -> None:
        # D-17: a refusal names indexes and providers, never key characters.
        rendered = str(error) + repr(dict(error.details))
        for key in KEYS:
            self.assertNotIn(key, rendered)

    def test_a_bare_string_is_never_iterated_into_characters(self) -> None:
        # INV-10, EC-1: every string the generator uses, passed bare, is refused rather than split.
        from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher

        for key in KEYS:
            with self.subTest(key=key[:6]), self.assertRaises(ConfigurationError):
                ProviderKeyMatcher.match(key, primary=ModelProvider.DEEPSEEK)


if __name__ == "__main__":
    unittest.main()
