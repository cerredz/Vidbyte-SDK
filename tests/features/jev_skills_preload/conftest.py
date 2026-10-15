"""FILE: tests/features/jev_skills_preload/conftest.py

PURPOSE: Shared offline fixtures for the skill-source tests in this pack: an isolated working folder and environment, a URL-routed fake of the single-attempt HTTP send, a Jev stand-in that answers by skill name, a main-model stand-in, SKILL.md writers, and an I/O recorder.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/jev_skills_preload/; builds on tests/agent_test_support.py (bind_test_runner), on the HttpTransport._send_once seam used by tests/features/coding_agent/conftest.py, and on the DecisionModelHelper patch point used by tests/test_jev_skill_preload.py.
ARCHITECTURE NOTE: Only modules that exist before the feature are imported here, so a missing vidbyte.agents.skills package or entry class fails each test at setup (through each module's import guard) instead of aborting collection of the whole suite. The HTTP fake is installed for every test in the pack, so an unexpected request raises AssertionError instead of reaching the network.
FUNCTION INVENTORY: FakeSkillHttp.answer/reply/oversized/connection_error/count/urls/send routes GET requests by exact URL and records each attempt with its headers, timeout, size cap, and redirect setting; NamedJev.arun answers each Jev skill question by the skill name in the request state; CapturingRunner.run records the system prompt the main model receives; IoRecord and record_io spy on file opens, os.stat, and environment reads; fixtures fake_http, jev, make_agent, bind_main_runner, skill_md, write_skill, record_io, spin_loop, and the autouse _isolated_skill_environment.
COMMON MODIFICATION PATTERNS: Add a fixture here only when two or more modules in this pack need it; keep source-specific builders (zip archives, GitHub trees, lock files) in the module that uses them.
WHAT NOT TO DO IN THIS FILE: 1. Do not import or stub vidbyte.agents.skills or the new entry classes; a missing feature must stay red. 2. Do not open sockets or read real keys; every skill-source key variable is removed before each test. 3. Do not patch SkillMarkdown, entry validation, SkillLoader memory, zipfile, or yaml; spec section 13 names them as real seams.
KNOWN EDGE CASES: The fake mirrors HttpTransport._send_bounded: it sets raw_bytes only when max_response_bytes is passed and raises ProviderRequestError(status_code=<status>) when a body exceeds that cap. Patching asyncio.sleep through the transport module patches it process-wide for the test, so spin_loop keeps the real sleep for yielding to the loop. A route's last answer repeats for every later attempt.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 9.2 and 13); tests/features/jev_skills_preload/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload
"""

from __future__ import annotations

import asyncio
import io
import os
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, JevAlignmentSettings, JevRuntimeSettings
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import transport as transport_module
from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse, TextModelResponse

SKILL_SOURCE_ENV_VARS = ("GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")
JEV_HELPER_PATH = "vidbyte.agents.jev.alignment.skills.DecisionModelHelper"
AGENT_BASE_PROMPT = "Agent base prompt."
_REAL_SLEEP = asyncio.sleep


@dataclass(frozen=True)
class SentRequest:
    """One attempt the transport made, as the network would have seen it."""

    url: str
    headers: Mapping[str, str]
    max_response_bytes: int | None
    timeout_seconds: float
    follow_redirects: bool


@dataclass(frozen=True)
class Oversized:
    """An answer whose body is `size` bytes long; only a cap below that size refuses it."""

    size: int
    status: int = 200


class FakeSkillHttp:
    """Answers GET requests by exact URL and records every attempt the transport makes."""

    HANG = object()

    def __init__(self) -> None:
        self.routes: dict[str, list[object]] = {}
        self.sent: list[SentRequest] = []
        self.sleeps: list[float] = []

    @staticmethod
    def reply(status: int, body: bytes | str = b"", headers: Mapping[str, str] | None = None) -> HttpResponse:
        # Header names are lowercase, as dict(httpx.Response.headers) gives them.
        raw = body.encode("utf-8") if isinstance(body, str) else body
        lowered = {name.lower(): value for name, value in (headers or {}).items()}
        return HttpResponse(status_code=status, body=raw.decode("utf-8", errors="replace"), headers=lowered, raw_bytes=raw)

    @staticmethod
    def oversized(size: int, status: int = 200) -> Oversized:
        # A body too large to build in memory; only a request whose cap is below `size` gets the transport's refusal.
        return Oversized(size=size, status=status)

    @staticmethod
    def connection_error() -> ProviderRequestError:
        # The transport's own shape for a timeout or refused connection: no status code.
        return ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt="ConnectError: [Errno 11001] getaddrinfo failed")

    def answer(self, url: str, *answers: object) -> None:
        # Answers are used in order; the last one repeats for every later attempt.
        self.routes[url] = list(answers)

    def urls(self) -> list[str]:
        return [request.url for request in self.sent]

    def count(self, url: str) -> int:
        return sum(1 for request in self.sent if request.url == url)

    async def send(self, client: Any, *, url: str, headers: Mapping[str, str], timeout_seconds: float, max_response_bytes: int | None = None, **_: Any) -> HttpResponse:
        self.sent.append(SentRequest(url=url, headers={name.lower(): value for name, value in headers.items()}, max_response_bytes=max_response_bytes, timeout_seconds=timeout_seconds, follow_redirects=bool(client.follow_redirects)))
        answers = self.routes.get(url)
        if not answers:
            raise AssertionError(f"unexpected skill-source request: GET {url}")
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if callable(answer):
            answer = await answer()
        if answer is self.HANG:
            # A server that accepted the connection and never finishes the body.
            await asyncio.Event().wait()
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, Oversized):
            return self._refuse_oversized(answer, max_response_bytes)
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

    @staticmethod
    def _refuse_oversized(answer: Oversized, cap: int | None) -> HttpResponse:
        if cap is None or answer.size <= cap:
            raise AssertionError(f"a {answer.size}-byte body was not refused: the request passed max_response_bytes={cap}")
        raise ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=answer.status)


def _jev_answer(question_name: str, probability: float) -> JevAnswer:
    # A normalized noul answer with matching choice and probability fields.
    return JevAnswer(
        question_name=question_name,
        question_type=JevQuestionType.NOUL,
        choice="true" if probability >= 0.5 else "false",
        probabilities={"true": probability, "false": 1.0 - probability},
        noul=probability,
    )


class NamedJev:
    """Answers each Jev skill question by the skill name that the request state carries for it."""

    def __init__(self, probabilities: Mapping[str, float], *, fail: Iterable[str] = (), missing: Iterable[str] = (), unreported_usage: Iterable[str] = (), default: float | None = None) -> None:
        self.probabilities = dict(probabilities)
        self.fail = frozenset(fail)
        self.missing = frozenset(missing)
        self.unreported_usage = frozenset(unreported_usage)
        self.default = default
        self.requests: list[JevDecisionRequest] = []

    @staticmethod
    def names(request: JevDecisionRequest) -> dict[str, str]:
        # Question name -> the skill name in that question's decision-state record.
        return {question.name: request.state["skills"][question.name]["name"] for question in request.questions}

    @property
    def asked(self) -> list[str]:
        return [name for request in self.requests for name in self.names(request).values()]

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        names = self.names(request)
        if self.fail & set(names.values()):
            raise ProviderRequestError("scripted Jev failure", provider="typesafe")
        answers: dict[str, JevAnswer] = {}
        for question_name, skill_name in names.items():
            if skill_name in self.missing:
                continue
            probability = self.probabilities.get(skill_name, self.default)
            if probability is None:
                raise AssertionError(f"Jev was asked about {skill_name!r}, which this test expected never to reach Jev")
            answers[question_name] = _jev_answer(question_name, probability)
        usage = None if self.unreported_usage & set(names.values()) else {"input_tokens": 10, "output_tokens": 1}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage=usage)


def _helper_class(runner: NamedJev) -> type:
    # Replaces DecisionModelHelper construction while keeping the canonical noul scorer.
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> NamedJev:
            return runner

    return ScriptedHelper


class CapturingRunner:
    """Main-model stand-in that records the system prompt each generative call receives."""

    def __init__(self) -> None:
        self.systems: list[str | None] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        self.systems.append(kwargs.get("system"))
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text="completed", raw={}, usage={"input_tokens": 100, "output_tokens": 20})


@dataclass
class IoRecord:
    """Paths opened or stat-ed, and environment keys read, while a recording window was open."""

    opened: list[tuple[str, str]] = field(default_factory=list)
    stat_paths: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)

    def touched(self, *roots: Path) -> list[str]:
        prefixes = tuple(str(root) for root in roots)
        paths = [path for path, _ in self.opened] + self.stat_paths
        return [path for path in paths if path.startswith(prefixes)]

    def writes(self) -> list[str]:
        return [path for path, mode in self.opened if any(flag in mode for flag in "wax+")]


def _path_text(value: object) -> str:
    return f"fd:{value}" if isinstance(value, int) else str(os.fspath(value))  # type: ignore[arg-type]


@contextmanager
def _recording_io() -> Iterator[IoRecord]:
    # Spies on every file open (including worker threads), os.stat, and os.environ reads, then restores them.
    record = IoRecord()
    real_open, real_os_open, real_stat, real_getitem = io.open, os.open, os.stat, os._Environ.__getitem__

    def spy_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        record.opened.append((_path_text(file), mode))
        return real_open(file, mode, *args, **kwargs)

    def spy_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND)
        record.opened.append((_path_text(path), "w" if writing else "r"))
        return real_os_open(path, flags, *args, **kwargs)

    def spy_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        record.stat_paths.append(_path_text(path))
        return real_stat(path, *args, **kwargs)

    def spy_getitem(environ: Any, key: str) -> str:
        record.env_keys.append(key)
        return real_getitem(environ, key)

    with patch("builtins.open", spy_open), patch("io.open", spy_open), patch("os.open", spy_os_open), patch("os.stat", spy_stat), patch.object(os._Environ, "__getitem__", spy_getitem):
        yield record


def _skill_md(name: str = "a-skill", description: str = "Does one thing well.", body: str = "Follow these steps.\n", *, newline: str = "\n", bom: bool = False) -> bytes:
    # A valid SKILL.md: frontmatter with name and description, then the body after the closing line.
    head = newline.join(("---", f"name: {name}", f"description: {description}", "---", ""))
    return (b"\xef\xbb\xbf" if bom else b"") + (head + body).encode("utf-8")


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeSkillHttp:
    # Replaces the single-attempt send and the retry backoff sleep, so no socket opens and retries never wait.
    fake = FakeSkillHttp()

    async def fake_send(transport: HttpTransport, client: Any, **kwargs: Any) -> HttpResponse:
        return await fake.send(client, **kwargs)

    async def no_sleep(delay: float) -> None:
        fake.sleeps.append(delay)

    monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
    monkeypatch.setattr(transport_module.asyncio, "sleep", no_sleep)
    return fake


@pytest.fixture(autouse=True)
def _isolated_skill_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_http: FakeSkillHttp) -> None:
    # Developer machines may hold real keys; relative skill paths must resolve inside this test's folder.
    for name in SKILL_SOURCE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def jev(monkeypatch: pytest.MonkeyPatch) -> Callable[..., NamedJev]:
    def install(probabilities: Mapping[str, float] | None = None, **options: Any) -> NamedJev:
        runner = NamedJev(probabilities or {}, **options)
        monkeypatch.setattr(JEV_HELPER_PATH, _helper_class(runner))
        return runner

    return install


@pytest.fixture
def bind_main_runner() -> Callable[[JevAgent], CapturingRunner]:
    def bind(agent: JevAgent) -> CapturingRunner:
        runner = CapturingRunner()
        bind_test_runner(agent, runner)
        return runner

    return bind


@pytest.fixture
def make_agent(bind_main_runner: Callable[[JevAgent], CapturingRunner]) -> Callable[[Sequence[object]], tuple[JevAgent, CapturingRunner]]:
    # A JevAgent with no preflight gate, so every run reaches the skill preload, and an offline main model.
    def build(skills: Sequence[object]) -> tuple[JevAgent, CapturingRunner]:
        settings = JevAgentSettings(
            name="skill-sources-test",
            system_prompt=AGENT_BASE_PROMPT,
            provider=ModelProvider.OPENAI,
            model_name="gpt-4.1-mini",
            alignment=JevAlignmentSettings(skills=tuple(skills)),  # type: ignore[arg-type]
        )
        agent = JevAgent(settings, JevRuntimeSettings(preflight=()))
        return agent, bind_main_runner(agent)

    return build


@pytest.fixture
def skill_md() -> Callable[..., bytes]:
    return _skill_md


@pytest.fixture
def write_skill() -> Callable[..., Path]:
    # Writes <folder>/SKILL.md as raw bytes (line endings kept) and returns the folder.
    def write(folder: Path, raw: bytes | None = None, **markdown: Any) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_bytes(raw if raw is not None else _skill_md(**markdown))
        return folder

    return write


@pytest.fixture
def record_io() -> Callable[[], Any]:
    return _recording_io


@pytest.fixture
def spin_loop() -> Callable[..., Any]:
    # Yields to the event loop with the real sleep, which fake_http's backoff patch does not replace here.
    async def spin(times: int = 50) -> None:
        for _ in range(times):
            await _REAL_SLEEP(0)

    return spin
