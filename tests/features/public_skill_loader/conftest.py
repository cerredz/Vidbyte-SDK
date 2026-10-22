"""FILE: tests/features/public_skill_loader/conftest.py

PURPOSE: Offline fixtures for the public skill loader pack: an isolated working folder and environment, a URL-routed fake of the single-attempt HTTP send, a SKILL.md builder and writer, and a recorder of file opens, stats, and environment reads.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/public_skill_loader/. Mirrors the HttpTransport._send_once seam and the I/O recorder of tests/features/jev_skills_preload/conftest.py, whose fixtures pytest does not share with this folder.
ARCHITECTURE NOTE: Only modules that exist before the feature are imported here, so a missing root export fails each test at setup through its module's import guard instead of aborting collection of the suite. The HTTP fake is installed for every test, so an unexpected request raises AssertionError instead of reaching the network.
FUNCTION INVENTORY: FakeHttp.reply/answer/urls/count/send routes GET requests by exact URL and records each attempt's URL and headers; IoRecord.touched lists recorded paths under given roots; fixtures fake_http, skill_md, write_skill, record_io, and the autouse _isolated_environment.
COMMON MODIFICATION PATTERNS: Add a fixture here only when two or more modules in this pack need it; keep case tables in the module that uses them.
WHAT NOT TO DO IN THIS FILE: 1. Do not import SkillLoader, SkillResolution, ConfigurationError from the root, or SkillEntries; a missing feature must stay red per module. 2. Do not patch SkillLoader, SkillEntries, SkillMarkdown, entry validation, or the loader's memory; spec section 13 names them as real seams. 3. Do not open sockets or read real keys; every skill-source key variable is removed before each test.
KNOWN EDGE CASES: The fake mirrors HttpTransport._send_bounded: raw_bytes is set only when max_response_bytes is passed, and a body over that cap raises ProviderRequestError with its status. A route's last answer repeats for every later attempt, so a 429 or 503 route answers the transport's one retry too. Patching asyncio.sleep through the transport module patches it process-wide for the test.
RELATED DOCS: docs/spec/public-skill-loader/spec.md (section 13); tests/features/public_skill_loader/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import transport as transport_module
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

SKILL_SOURCE_ENV_VARS = ("GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


@dataclass(frozen=True)
class SentRequest:
    """One attempt the transport made, as the network would have seen it."""

    url: str
    headers: Mapping[str, str]


class FakeHttp:
    """Answers GET requests by exact URL and records every attempt the transport makes."""

    def __init__(self) -> None:
        self.routes: dict[str, list[object]] = {}
        self.sent: list[SentRequest] = []

    @staticmethod
    def reply(status: int, body: bytes | str = b"", headers: Mapping[str, str] | None = None) -> HttpResponse:
        # Header names are lowercase, as dict(httpx.Response.headers) gives them.
        raw = body.encode("utf-8") if isinstance(body, str) else body
        lowered = {name.lower(): value for name, value in (headers or {}).items()}
        return HttpResponse(status_code=status, body=raw.decode("utf-8", errors="replace"), headers=lowered, raw_bytes=raw)

    def answer(self, url: str, *answers: object) -> None:
        # Answers are used in order; the last one repeats for every later attempt.
        self.routes[url] = list(answers)

    def urls(self) -> list[str]:
        return [request.url for request in self.sent]

    def count(self, url: str) -> int:
        return sum(1 for request in self.sent if request.url == url)

    async def send(self, client: Any, *, url: str, headers: Mapping[str, str], max_response_bytes: int | None = None, **_: Any) -> HttpResponse:
        self.sent.append(SentRequest(url=url, headers={name.lower(): value for name, value in headers.items()}))
        answers = self.routes.get(url)
        if not answers:
            raise AssertionError(f"unexpected skill-source request: GET {url}")
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, BaseException):
            raise answer
        assert isinstance(answer, HttpResponse), f"route for {url} holds {answer!r}"
        return self._bounded(answer, max_response_bytes)

    @staticmethod
    def _bounded(response: HttpResponse, cap: int | None) -> HttpResponse:
        # HttpTransport sets raw_bytes only on the bounded path and refuses a body above the cap.
        if cap is None:
            return replace(response, raw_bytes=None)
        if len(response.raw_bytes or b"") > max(1, cap):
            raise ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=response.status_code)
        return response


@dataclass
class IoRecord:
    """Paths opened or stat-ed, and environment keys read, while a recording window was open."""

    opened: list[str] = field(default_factory=list)
    stat_paths: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)

    def touched(self, *roots: Path) -> list[str]:
        prefixes = tuple(str(root) for root in roots)
        return [path for path in self.opened + self.stat_paths if path.startswith(prefixes)]


def _path_text(value: object) -> str:
    return f"fd:{value}" if isinstance(value, int) else str(os.fspath(value))  # type: ignore[arg-type]


@contextmanager
def _recording_io() -> Iterator[IoRecord]:
    # Spies on every file open (worker threads included), os.stat, and os.environ reads, then restores them.
    record = IoRecord()
    real_open, real_os_open, real_stat, real_getitem = io.open, os.open, os.stat, os._Environ.__getitem__

    def spy_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        record.opened.append(_path_text(file))
        return real_open(file, mode, *args, **kwargs)

    def spy_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        record.opened.append(_path_text(path))
        return real_os_open(path, flags, *args, **kwargs)

    def spy_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        record.stat_paths.append(_path_text(path))
        return real_stat(path, *args, **kwargs)

    def spy_getitem(environ: Any, key: str) -> str:
        record.env_keys.append(key)
        return real_getitem(environ, key)

    with patch("builtins.open", spy_open), patch("io.open", spy_open), patch("os.open", spy_os_open), patch("os.stat", spy_stat), patch.object(os._Environ, "__getitem__", spy_getitem):
        yield record


def _skill_md(name: str, body: str, description: str = "Does one thing well.") -> bytes:
    # A valid SKILL.md: frontmatter with name and description, then the body after the closing line.
    return f"---\nname: {name}\ndescription: {description}\n---\n{body}".encode()


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeHttp:
    # Replaces the single-attempt send and the retry backoff sleep, so no socket opens and retries never wait.
    fake = FakeHttp()

    async def fake_send(transport: HttpTransport, client: Any, **kwargs: Any) -> HttpResponse:
        return await fake.send(client, **kwargs)

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
    monkeypatch.setattr(transport_module.asyncio, "sleep", no_sleep)
    return fake


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_http: FakeHttp) -> None:
    # Developer machines may hold real keys; relative skill paths must resolve inside this test's folder.
    for name in SKILL_SOURCE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def skill_md() -> Callable[..., bytes]:
    return _skill_md


@pytest.fixture
def write_skill() -> Callable[[Path, bytes], Path]:
    # Writes <folder>/SKILL.md as raw bytes (line endings kept) and returns the folder.
    def write(folder: Path, raw: bytes) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_bytes(raw)
        return folder

    return write


@pytest.fixture
def record_io() -> Callable[[], Any]:
    return _recording_io
