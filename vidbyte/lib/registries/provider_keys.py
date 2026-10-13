"""FILE: vidbyte/lib/registries/provider_keys.py

PURPOSE: Matches a developer's list of API keys to the providers an agent or text config uses: a key whose prefix proves its provider goes to that provider, a Vidbyte key becomes the Vidbyte key, and any other key is bound only when exactly one configured provider can take it.
ROLE IN CODEBASE: The roots (TextModelConfig, BaseAgent and AggregateAgent, JevAgentSettings, BaseAgent.restore) call ProviderKeyMatcher.match once and hand the returned ProviderKeys record to every child unchanged; JevRunBriefSettings and AgentRoleSettings call normalize. ProviderModelRegistry.find_provider_api_key reads a provider's key from the record.
ARCHITECTURE NOTE: A static lookup class in the lib layer. At module level it imports only re, collections.abc, typing, vidbyte.lib.constants.jev, vidbyte.lib.enums, and vidbyte.lib.errors; ProviderKeys and ProviderModelRegistry are imported inside match, because vidbyte.lib.dataclasses.agents is reached through this package's own __init__ (spec D-21). It reads no environment and makes no request.
COMMON MODIFICATION PATTERNS: Add a KEY_FORMATS rule only for a prefix the vendor documents first-party, with its source in a comment here and in the registries README's "Provider Key Format Sources"; its literal prefixes become reserved automatically. A refuse-only prefix goes in RESERVED_PREFIXES and may rest on a secondary source.
KNOWN EDGE CASES: A key that starts with a KEY_FORMATS prefix but does not fully match the rule (an xai- key with a dot) is unproven and reserved to that provider, which takes no unproven key, so nothing takes it. Entries are named by their index in the developer's list, counting skipped None and blank entries, and no message ever quotes a key.
RELATED DOCS: docs/spec/byok-api-keys/spec.md (section 9.2 "Matching", tables F, A, and M; D-2, D-21, D-28, D-29, D-31) and vidbyte/lib/registries/README.md.
TESTS: tests/features/sdk_provider_keys/test_provider_keys_matching.py and tests/features/sdk_provider_keys/test_provider_keys_property.py.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, ClassVar

from vidbyte.lib.constants.jev import VIDBYTE_API_KEY_PREFIX, VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND, VIDBYTE_PROVIDER_KEY_PATTERN
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agents import ProviderKeys


class ProviderKeyMatcher:
    """Match a list of API keys to the providers a root is configured with."""

    # Table F: prefixes that prove a provider, in order; the first rule
    # that fully matches a stripped key names its provider. Each rule's
    # literal prefixes are also reserved to that provider.
    KEY_FORMATS: ClassVar[tuple[tuple[ModelProvider, tuple[str, ...], re.Pattern[str]], ...]] = (
        # Anthropic documents "sk-ant-api..." keys (first-party):
        # https://platform.claude.com/docs/en/manage-claude/authentication
        (ModelProvider.ANTHROPIC, ("sk-ant-",), re.compile(r"sk-ant-[A-Za-z0-9_-]+")),
        # OpenRouter: "Copy your key (starts with sk-or-...)":
        # https://openrouter.ai/docs/cookbook/coding-agents/codex-cli.md
        (ModelProvider.OPENROUTER, ("sk-or-",), re.compile(r"sk-or-[A-Za-z0-9_-]+")),
        # OpenAI's own GitHub organization names "an sk-proj key" in its
        # openai-platform-api-key skill:
        # https://github.com/openai/plugins
        # and its API reference shows "sk-admin-1234abcd":
        # https://developers.openai.com/api/reference/resources/organization/subresources/admin_api_keys/methods/create
        (ModelProvider.OPENAI, ("sk-proj-", "sk-admin-"), re.compile(r"sk-(?:proj|admin)-[A-Za-z0-9_-]+")),
        # xAI documents export XAI_API_KEY="xai-..." (first-party):
        # https://docs.x.ai/build/overview
        (ModelProvider.XAI, ("xai-",), re.compile(r"xai-[A-Za-z0-9_-]+")),
        # Google's example key is AIza plus 35 characters:
        # https://cloud.google.com/docs/authentication/api-keys
        # and Google's own GitHub organization names "AQ.Ab8..." keys:
        # https://github.com/google-gemini/cookbook/blob/main/tools/README.md
        (ModelProvider.GEMINI, ("AIza", "AQ."), re.compile(r"(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]+)")),
    )

    # Table A: these providers issue only keys that carry their table F
    # prefix, so they never take an unproven key.
    FORMAT_BOUND_PROVIDERS: ClassVar[frozenset[ModelProvider]] = frozenset(
        {ModelProvider.ANTHROPIC, ModelProvider.XAI, ModelProvider.GEMINI, ModelProvider.OPENROUTER}
    )

    # Table A: every OpenAI key starts with sk-, so openai takes an
    # unproven key only with that prefix. OpenAI's own key check:
    # https://github.com/openai/plugins (/^sk-[A-Za-z0-9_-]+$/)
    OPENAI_KEY_PREFIX: ClassVar[str] = "sk-"

    # Refuse-only: a prefix reserved to one provider beyond table F. It
    # never proves a key. Secondary source, the gitleaks openai rule:
    # https://raw.githubusercontent.com/gitleaks/gitleaks/master/config/gitleaks.toml
    RESERVED_PREFIXES: ClassVar[tuple[tuple[str, ModelProvider], ...]] = (("sk-svcacct-", ModelProvider.OPENAI),)

    @classmethod
    def provider_of(cls, key: str) -> ModelProvider | None:
        """Return the provider whose table F rule fully matches key, or None when no prefix proves one."""
        # @intent key-prefix-decides-provider
        # Only a vendor-documented prefix proves a provider, so a proven
        # key can go nowhere else; the first full match in table order
        # wins, which keeps sk-ant- and sk-or- away from the openai
        # rule.
        for provider, _prefixes, pattern in cls.KEY_FORMATS:
            if pattern.fullmatch(key):
                return provider
        return None

    @classmethod
    def accepts_unproven(cls, provider: ModelProvider | str, key: str) -> bool:
        """Return True when provider may take key although no prefix proves it (table A)."""
        member = ModelProvider(provider)
        # @intent reserved-prefixes-only-refuse
        # A prefix reserved to one provider keeps the key from every
        # other vendor, even when the key does not fully match that
        # provider's rule. Reserved prefixes never prove a key.
        reserved = [(prefix, owner) for owner, prefixes, _pattern in cls.KEY_FORMATS for prefix in prefixes]
        reserved.extend((prefix, owner) for prefix, owner in cls.RESERVED_PREFIXES)
        if any(key.startswith(prefix) and owner is not member for prefix, owner in reserved):
            return False
        # @intent no-shape-guesses
        # Only the documented families decide: a key's length or
        # character set never decides its provider.
        if member in cls.FORMAT_BOUND_PROVIDERS:
            return False
        if member is ModelProvider.OPENAI:
            return key.startswith(cls.OPENAI_KEY_PREFIX)
        return True

    @classmethod
    def normalize(cls, api_keys: Iterable[str | None] | None, *, field_name: str = "api_keys") -> tuple[str, ...]:
        """Return the list's usable entries, stripped and in order, after checking the list and each entry."""
        return tuple(key for _index, key in cls._entries(api_keys, field_name))

    @classmethod
    def match(
        cls,
        api_keys: Iterable[str | None] | ProviderKeys | None,
        *,
        primary: ModelProvider | str | tuple[ModelProvider | str, ...] | None,
        others: Iterable[ModelProvider | str] = (),
        vidbyte_api_key: str | None = None,
        field_name: str = "api_keys",
        require_primary_key: bool = True,
    ) -> ProviderKeys:
        """Match a developer's list of keys to the root's configured providers and return the matched record."""
        # @intent provider-keys-import-late
        # This package's __init__ reaches vidbyte.lib.dataclasses.agents
        # through vidbyte.agents.types, so ProviderKeys and the provider
        # variable names are imported here, at call time, which keeps
        # every load order free of an import cycle.
        from vidbyte.lib.dataclasses.agents import ProviderKeys
        from vidbyte.lib.registries.models import ProviderModelRegistry

        # A blank explicit Vidbyte key counts as none, as it always has.
        explicit = (vidbyte_api_key.strip() or None) if isinstance(vidbyte_api_key, str) else vidbyte_api_key

        # Step 1: a record matched earlier passes through after a check
        # of each key against its provider, and is never matched again.
        # @intent matched-keys-pass-through
        # Children receive the root's record; matching it again against
        # a child's providers could bind an unproven key to another
        # vendor.
        if isinstance(api_keys, ProviderKeys):
            proven_at = tuple(cls.provider_of(key) for key in api_keys.keys)
            accepted_at = tuple(cls.accepts_unproven(provider, key) for provider, key in zip(api_keys.providers, api_keys.keys, strict=True))
            cls._check_record(api_keys, proven_at, accepted_at, field_name)
            # An explicit Vidbyte key fills in a record that has none,
            # and must agree with one it has.
            if explicit is None or explicit == api_keys.vidbyte_api_key:
                return api_keys
            if api_keys.vidbyte_api_key is None:
                return ProviderKeys(api_keys.providers, api_keys.keys, explicit, api_keys.matched_primary, api_keys.matched_others)
            raise ConfigurationError(
                f"{field_name} holds a Vidbyte API key that differs from vidbyte_api_key; pass one Vidbyte key.",
                details={"field": field_name, "error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND},
            )

        # Steps 2 and 3: check the list's shape and each entry, keeping
        # every entry's index in the developer's list for the messages.
        entries = cls._entries(api_keys, field_name)

        # Step 4: sort the entries. A Vidbyte entry is the Vidbyte key,
        # a key whose prefix proves its provider goes to that provider,
        # and every other key waits for step 5; identical repeats count
        # once.
        vidbyte_key = cls._vidbyte_key(entries, explicit, field_name)
        proven = {key: cls.provider_of(key) for _index, key in entries}
        held = cls._bind_proven(entries, proven, field_name)
        unproven: dict[str, int] = {}
        for index, key in entries:
            if proven[key] is None and not key.startswith(VIDBYTE_API_KEY_PREFIX):
                unproven.setdefault(key, index)

        # Step 5: name the configured providers, the primaries first,
        # and find which of them can take each unproven key.
        primaries = cls._provider_names(primary if isinstance(primary, tuple) else (primary,))
        other_names = tuple(name for name in cls._provider_names(others) if name not in primaries)
        configured = primaries + other_names
        accepting = {key: tuple(name for name in configured if cls.accepts_unproven(name, key)) for key in unproven}
        cls._refuse_unaccepted(unproven, accepting, configured, field_name)
        # @intent lone-key-goes-to-its-primary
        # A lone unproven key that one keyless primary can take is that
        # primary's key: binding it anywhere else would leave the
        # primary without a key, which step 6 refuses anyway.
        if len(unproven) == 1:
            ((lone_key, lone_index),) = unproven.items()
            owners = [name for name in primaries if name not in held and name in accepting[lone_key]]
            if len(owners) == 1:
                held[owners[0]] = (lone_index, lone_key)
                unproven = {}
        # Every remaining unproven key is bound only where it has
        # exactly one possible owner left, taking the keys in index
        # order.
        env_vars = ProviderModelRegistry.API_KEY_ENV_VARS
        held = cls._bind_unproven(unproven, accepting, held, field_name, env_vars)

        # Step 6: a list that holds provider keys must hold one for
        # every primary, unless a restore turns this off (D-30).
        if require_primary_key and held:
            cls._require_primary_keys(primaries, held, field_name, env_vars)

        # Step 7: return the record, keys in order of first appearance.
        ordered = sorted(held.items(), key=lambda item: item[1][0])
        return ProviderKeys(
            providers=tuple(provider for provider, _bound in ordered),
            keys=tuple(key for _provider, (_index, key) in ordered),
            vidbyte_api_key=vidbyte_key,
            matched_primary=primaries,
            matched_others=other_names,
        )

    @staticmethod
    def _entries(api_keys: object, field_name: str) -> tuple[tuple[int, str], ...]:
        """Return each usable entry stripped, with its index in the developer's list."""
        # @intent name-lists-reject-bare-strings
        # A bare string would be read one character at a time and a
        # mapping would match its own keys, so both are refused, never
        # converted into a list.
        if api_keys is None:
            return ()
        if isinstance(api_keys, (str, bytes)):
            raise ConfigurationError(f"{field_name} must be a list of provider API keys, not a single string; wrap it in a list.", details={"field": field_name})
        if isinstance(api_keys, Mapping):
            raise ConfigurationError(
                f"{field_name} must be a list of provider API keys, not a mapping; list the keys in any order and the SDK matches each one to its provider.",
                details={"field": field_name},
            )
        if not isinstance(api_keys, Iterable):
            type_name = type(api_keys).__name__
            raise ConfigurationError(f"{field_name} must be a list of provider API keys, got {type_name}.", details={"field": field_name, "type": type_name})
        entries: list[tuple[int, str]] = []
        for index, entry in enumerate(api_keys):
            # None and blank entries are skipped, so a list built from
            # os.environ.get calls works.
            if entry is None or (isinstance(entry, str) and not entry.strip()):
                continue
            if not isinstance(entry, str):
                raise ConfigurationError(f"{field_name}[{index}] must be a string, got {type(entry).__name__}.", details={"field": field_name, "index": index})
            key = entry.strip()
            if re.fullmatch(VIDBYTE_PROVIDER_KEY_PATTERN, key) is None:
                raise ConfigurationError(
                    f"{field_name}[{index}] ({len(key)} characters) contains spaces, line breaks, or characters outside printable ASCII, so it cannot be an API key.",
                    details={"field": field_name, "index": index, "length": len(key)},
                )
            entries.append((index, key))
        return tuple(entries)

    @staticmethod
    def _check_record(record: ProviderKeys, proven_at: tuple[ModelProvider | None, ...], accepted_at: tuple[bool, ...], field_name: str) -> None:
        """Refuse a record whose key does not fit the provider it sits at (M-20)."""
        # @intent records-are-checked-not-rebound
        # A record built by hand is held to the same rules a matched one
        # meets: sendable characters, a proven key at its own provider,
        # an unproven key only where table A allows it, and never the
        # Vidbyte key as a provider key. It is checked, never re-bound.
        for index, (provider, key) in enumerate(zip(record.providers, record.keys, strict=True)):
            sendable = re.fullmatch(VIDBYTE_PROVIDER_KEY_PATTERN, key) is not None and not key.startswith(VIDBYTE_API_KEY_PREFIX)
            placed = proven_at[index] is provider if proven_at[index] is not None else accepted_at[index]
            if not (sendable and placed):
                raise ConfigurationError(
                    f"{field_name} is a ProviderKeys record whose key {index} does not fit {provider.value}; pass your keys as a list and the SDK matches each one to its provider.",
                    details={"field": field_name, "index": index, "provider": provider.value},
                )

    @staticmethod
    def _vidbyte_key(entries: tuple[tuple[int, str], ...], explicit: object, field_name: str) -> str | None:
        """Return the one Vidbyte key from the explicit value and the list's Vidbyte entries (M-5)."""
        # @intent vidbyte-entry-is-the-vidbyte-key
        # An entry with the Vidbyte prefix is the Vidbyte key and never
        # a provider key, so it only ever reaches the gateway; two
        # different Vidbyte keys have no right answer, so they raise.
        found, found_index = explicit, None
        for index, key in entries:
            if not key.startswith(VIDBYTE_API_KEY_PREFIX):
                continue
            if found is None:
                found, found_index = key, index
            elif key != found:
                other = "vidbyte_api_key" if found_index is None else f"{field_name}[{found_index}]"
                raise ConfigurationError(
                    f"{field_name}[{index}] is a Vidbyte API key that differs from {other}; pass one Vidbyte key.",
                    details={"field": field_name, "index": index, "error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND},
                )
        return found  # type: ignore[return-value]

    @staticmethod
    def _bind_proven(entries: tuple[tuple[int, str], ...], proven: Mapping[str, ModelProvider | None], field_name: str) -> dict[ModelProvider, tuple[int, str]]:
        """Bind each proven key to its provider, with the index where it first appears (M-7)."""
        # @intent one-key-per-provider
        # A provider gets one key: the same key twice is one key, and
        # two different keys for one provider have no right answer.
        held: dict[ModelProvider, tuple[int, str]] = {}
        for index, key in entries:
            provider = proven[key]
            if provider is None:
                continue
            if provider not in held:
                held[provider] = (index, key)
            elif held[provider][1] != key:
                first = held[provider][0]
                raise ConfigurationError(
                    f"{field_name}[{first}] and {field_name}[{index}] are both {provider.value} keys; pass one key per provider.",
                    details={"field": field_name, "indexes": (first, index), "provider": provider.value},
                )
        return held

    @staticmethod
    def _provider_names(names: Iterable[object]) -> tuple[ModelProvider, ...]:
        """Return provider names as members, stripped and casefolded, without None, unknown names, or repeats."""
        # @intent unknown-provider-names-take-no-key
        # A name the SDK does not know can take no key, so it is left
        # out here and the root's own provider check reports it. A bare
        # string would be read one letter at a time, so it is refused.
        if isinstance(names, (str, bytes)):
            raise ConfigurationError("Provider names must be given as a list or tuple, not a single string.")
        members: list[ModelProvider] = []
        for name in names:
            try:
                member = name if isinstance(name, ModelProvider) else ModelProvider(str(name).strip().casefold())
            except ValueError:
                continue
            if member not in members:
                members.append(member)
        return tuple(members)

    @staticmethod
    def _refuse_unaccepted(unproven: Mapping[str, int], accepting: Mapping[str, tuple[ModelProvider, ...]], configured: tuple[ModelProvider, ...], field_name: str) -> None:
        """Refuse the lowest-index unproven key that no configured provider can take (M-6)."""
        for key, index in unproven.items():
            if accepting[key]:
                continue
            names = [name.value for name in configured]
            raise ConfigurationError(
                f"{field_name}[{index}] ({len(key)} characters) has no prefix that proves its provider, and none of the providers configured here "
                f"({', '.join(names) or 'none'}) can take such a key. Add the model that uses it, or set that provider's own API key environment variable instead.",
                details={"field": field_name, "index": index, "length": len(key), "providers": names},
            )

    @staticmethod
    def _bind_unproven(
        unproven: Mapping[str, int],
        accepting: Mapping[str, tuple[ModelProvider, ...]],
        held: Mapping[ModelProvider, tuple[int, str]],
        field_name: str,
        env_vars: Mapping[ModelProvider, str],
    ) -> dict[ModelProvider, tuple[int, str]]:
        """Bind each unproven key to its one possible owner, lowest index first, or refuse (M-7, M-19)."""
        # @intent unproven-key-needs-one-owner
        # An unproven key is bound only where exactly one configured
        # provider can still take it. Anything else would be a guess
        # that could send the key to the wrong vendor, so the root
        # refuses.
        bound = dict(held)
        waiting = dict(unproven)
        while waiting:
            candidates = {key: [name for name in accepting[key] if name not in bound] for key in waiting}
            stuck = next((key for key in waiting if not candidates[key]), None)
            if stuck is not None:
                owner = accepting[stuck][0]
                first, second = sorted((bound[owner][0], waiting[stuck]))
                raise ConfigurationError(
                    f"{field_name}[{first}] and {field_name}[{second}] are both {owner.value} keys; pass one key per provider.",
                    details={"field": field_name, "indexes": (first, second), "provider": owner.value},
                )
            forced = next((key for key in waiting if len(candidates[key]) == 1), None)
            if forced is None:
                key, index = next(iter(waiting.items()))
                names = [name.value for name in candidates[key]]
                variables = [env_vars[name] for name in candidates[key]]
                raise ConfigurationError(
                    f"{field_name}[{index}] ({len(key)} characters) has no prefix that proves its provider, and it could belong to any of {', '.join(names)}. "
                    f"Set it as one of {', '.join(variables)} instead, so the SDK does not have to guess.",
                    details={"field": field_name, "index": index, "length": len(key), "providers": names},
                )
            bound[candidates[forced][0]] = (waiting.pop(forced), forced)
        return bound

    @staticmethod
    def _require_primary_keys(primaries: tuple[ModelProvider, ...], held: Mapping[ModelProvider, tuple[int, str]], field_name: str, env_vars: Mapping[ModelProvider, str]) -> None:
        """Refuse a list that holds provider keys but none for a primary provider (M-18)."""
        # @intent configured-model-needs-its-key
        # Keys for other providers but none for the model this root runs
        # is almost always the wrong key; going Vidbyte-paid instead
        # would silently bill a call the developer meant to relay.
        missing = next((name for name in primaries if name not in held), None)
        if missing is None:
            return
        names = [provider.value for provider, _bound in sorted(held.items(), key=lambda item: item[1][0])]
        raise ConfigurationError(
            f"{field_name} holds keys for {', '.join(names)} but none for {missing.value}, the provider of a configured model. "
            f"Add your {missing.value} key to {field_name}, or pass no provider keys to use {env_vars[missing]} or Vidbyte's own {missing.value} account.",
            details={"field": field_name, "provider": missing.value, "providers": names},
        )


__all__ = ["ProviderKeyMatcher"]
