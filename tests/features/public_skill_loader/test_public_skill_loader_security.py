"""FILE: tests/features/public_skill_loader/test_public_skill_loader_security.py

PURPOSE: Pin the public door's secret handling: a rejected argument, element, or credentialed entry never appears, whole or in part, in the ConfigurationError's message, repr, details, args, or chained cause; and a loader built from a list reads no key variable and touches no file at construction, then at load sends each entry's own credential, or the variable's value at load time, only to that credential's fixed host.
ROLE IN CODEBASE: Covers spec AC-6, AC-9, INV-3, INV-4, INV-9, NFR-4, T-1 and T-3 for SkillEntries.__post_init__ (vidbyte/lib/dataclasses/skills.py) and SkillLoader (vidbyte/agents/skills/loader.py) through the root export, with the existing GitHub and vendor resolvers behind it.
ARCHITECTURE NOTE: Every request is answered at HttpTransport._send_once by the conftest's URL-routed fake, which records each attempt's headers as the host would see them; construction runs inside the conftest's file and environment recorder. Secrets are obvious fakes that share one marker, so a truncated echo is caught too.
FUNCTION INVENTORY: test_rejection_never_echoes_the_rejected_value_or_a_credential; test_construction_reads_no_key_and_load_sends_each_credential_only_to_its_own_host.
COMMON MODIFICATION PATTERNS: A new rejected shape that can carry caller text adds a LEAK_CASES row; a new credentialed source adds an entry, its route, and its host to the credential test.
WHAT NOT TO DO IN THIS FILE: 1. Do not use a real token or key. 2. Do not check only the full secret; a validator that shows the first characters of a value leaks just as badly. 3. Do not set the variables only before construction; changing them afterwards is what proves they are read at load.
KNOWN EDGE CASES: GitHub sends "Authorization: Bearer <token>", Anthropic "x-api-key", and OpenAI "Authorization: Bearer <key>"; the fake lowercases header names. Entry credential fields are repr=False, so only a validator that reads field values or asdict() can leak them.
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 6.1 INV-3, INV-4, INV-9, 6.2 AC-6, AC-9, 9.2 row 3, 10 T-1 and T-3)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_security.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        AnthropicSkill,
        ConfigurationError,
        GitHubSkill,
        InlineSkill,
        LocalSkill,
        OpenAISkill,
        SkillLoader,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

MARKER = "PUBLICDOORLEAK"
SECRET_TOKEN = f"ghp_{MARKER}0000000000000000000000FAKE"
SECRET_KEY = f"sk-ant-api03-{MARKER}-FAKE-KEY"
KEY_VARIABLES = {"GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
SHA = "0123456789abcdef0123456789abcdef01234567"
HOSTS = {"github": "api.github.com", "anthropic": "api.anthropic.com", "openai": "api.openai.com"}


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def inline(name: str) -> Any:
    return InlineSkill(name=name, description=f"The {name} skill.", text=f"Text of {name}.\n")


# (case, argument builder, the details the error must carry instead of the value)
LEAK_CASES: list[tuple[str, Callable[[], object], dict[str, object]]] = [
    ("token pasted as the whole argument", lambda: SECRET_TOKEN, {"entries_type": "str"}),
    ("key bytes as the whole argument", lambda: SECRET_KEY.encode(), {"entries_type": "bytes"}),
    ("token pasted as an element", lambda: (inline("house-review"), SECRET_TOKEN), {"position": 1, "entry_type": "str"}),
    ("dict element holding a token and a key", lambda: [inline("house-review"), {"token": SECRET_TOKEN, "api_key": SECRET_KEY}], {"position": 1, "entry_type": "dict"}),
    (
        "credentialed entries repeating a name",
        lambda: (GitHubSkill(name="pdf", repo="acme/skills", token=SECRET_TOKEN), AnthropicSkill(name="pdf", skill_id="skill_x", api_key=SECRET_KEY)),
        {"names": ["pdf"]},
    ),
]


@pytest.mark.parametrize(("case", "build", "details"), LEAK_CASES, ids=[row[0] for row in LEAK_CASES])
def test_rejection_never_echoes_the_rejected_value_or_a_credential(case: str, build: Callable[[], object], details: dict[str, object]) -> None:
    # AC-6, INV-3, T-3: the error names types, positions, and names only; a token typed into the wrong place stays hidden.
    with pytest.raises(ConfigurationError) as raised:
        SkillLoader(build())
    error = raised.value
    assert error.details == details
    chained = [repr(cause) for cause in (error.__cause__, error.__context__) if cause is not None]
    for text in (str(error), repr(error), error.message, repr(error.details), *map(str, error.args), *chained):
        assert MARKER not in text, f"{case}: {text}"


@pytest.mark.asyncio
async def test_construction_reads_no_key_and_load_sends_each_credential_only_to_its_own_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_http: Any, record_io: Callable[[], Any], write_skill: Callable[..., Path], skill_md: Callable[..., bytes]) -> None:
    # AC-9, INV-4, INV-9, T-1: the variables change after construction, so a value read while building would be sent stale.
    for name, value in (("GITHUB_TOKEN", "ghp_ENV_AT_BUILD_FAKE"), ("ANTHROPIC_API_KEY", "sk-ant-ENV-AT-BUILD-FAKE"), ("OPENAI_API_KEY", "sk-proj-ENV-AT-BUILD-FAKE")):
        monkeypatch.setenv(name, value)
    routes = {
        "own-token": f"https://{HOSTS['github']}/repos/acme/team/contents/skills/own-token/SKILL.md?ref={SHA}",
        "env-token": f"https://{HOSTS['github']}/repos/acme/public/contents/skills/env-token/SKILL.md?ref={SHA}",
        "own-anthropic": f"https://{HOSTS['anthropic']}/v1/skills/skill_a/versions/1/content",
        "env-anthropic": f"https://{HOSTS['anthropic']}/v1/skills/skill_b/versions/1/content",
        "own-openai": f"https://{HOSTS['openai']}/v1/skills/skill_c/versions/1/content",
        "env-openai": f"https://{HOSTS['openai']}/v1/skills/skill_d/versions/1/content",
    }
    entries = [
        GitHubSkill(name="own-token", repo="acme/team", ref=SHA, path="skills/own-token", token="ghp_ENTRY_FAKE"),
        GitHubSkill(name="env-token", repo="acme/public", ref=SHA, path="skills/env-token"),
        AnthropicSkill(name="own-anthropic", skill_id="skill_a", version="1", api_key="sk-ant-ENTRY-FAKE"),
        AnthropicSkill(name="env-anthropic", skill_id="skill_b", version="1"),
        OpenAISkill(name="own-openai", skill_id="skill_c", version="1", api_key="sk-proj-ENTRY-FAKE"),
        OpenAISkill(name="env-openai", skill_id="skill_d", version="1"),
        LocalSkill(name="local-one", path=tmp_path / "skills" / "local-one"),
    ]

    with record_io() as construction:
        loader = SkillLoader(entries)
    assert KEY_VARIABLES.isdisjoint(construction.env_keys)
    assert construction.touched(tmp_path) == []
    assert fake_http.sent == []

    for name, value in (("GITHUB_TOKEN", "ghp_ENV_AT_LOAD_FAKE"), ("ANTHROPIC_API_KEY", "sk-ant-ENV-AT-LOAD-FAKE"), ("OPENAI_API_KEY", "sk-proj-ENV-AT-LOAD-FAKE")):
        monkeypatch.setenv(name, value)
    for name, url in routes.items():
        fake_http.answer(url, fake_http.reply(200, skill_md(name, f"Body of {name}.\n")))
    write_skill(tmp_path / "skills" / "local-one", skill_md("local-one", "Local body.\n"))
    resolutions = await loader.load()

    assert [resolution.document.text if resolution.document else resolution.reason for resolution in resolutions] == [f"Body of {entry.name}.\n" for entry in entries[:6]] + ["Local body.\n"]
    headers = {request.url: request.headers for request in fake_http.sent}
    assert sorted(headers) == sorted(routes.values()) and len(fake_http.sent) == len(routes)
    assert headers[routes["own-token"]]["authorization"] == "Bearer ghp_ENTRY_FAKE"
    assert headers[routes["env-token"]]["authorization"] == "Bearer ghp_ENV_AT_LOAD_FAKE"
    assert headers[routes["own-anthropic"]]["x-api-key"] == "sk-ant-ENTRY-FAKE"
    assert headers[routes["env-anthropic"]]["x-api-key"] == "sk-ant-ENV-AT-LOAD-FAKE"
    assert headers[routes["own-openai"]]["authorization"] == "Bearer sk-proj-ENTRY-FAKE"
    assert headers[routes["env-openai"]]["authorization"] == "Bearer sk-proj-ENV-AT-LOAD-FAKE"
    # Each credential travels only to its own host, and nothing read at construction is ever sent.
    owners = {"ghp_": HOSTS["github"], "sk-ant-": HOSTS["anthropic"], "sk-proj-": HOSTS["openai"]}
    for request in fake_http.sent:
        host = urlsplit(request.url).hostname
        for value in request.headers.values():
            assert "AT_BUILD" not in value and "AT-BUILD" not in value, (request.url, value)
            for prefix, owner in owners.items():
                assert prefix not in value or host == owner, (request.url, value)
