"""FILE: tests/features/public_skill_loader/test_public_skill_loader_release.py

PURPOSE: Pin the release identity the public door ships under: each of the eight version literals (pyproject, vidbyte.__version__, the CLI fallback, the MCP server default, the MCP client's clientInfo, the README install line, llms.txt, and the bug template placeholder) equals pyproject.toml's version, observed through the code that uses it where one exists, and that version is never below 0.3.1, the first release that carries the loader.
ROLE IN CODEBASE: Covers spec AC-11, INV-16, FR-8, D-13 and EC-29 for pyproject.toml, vidbyte/__init__.py, vidbyte/cli/__init__.py, vidbyte/mcp_server/server/core.py, vidbyte/tools/mcp/client.py, README.md, llms.txt and .github/ISSUE_TEMPLATE/bug_report.yml. The ninth place, the contract's "version", is C016's: it must equal pyproject's version, which this file pins.
ARCHITECTURE NOTE: Values are read from this checkout's own files and modules, never from importlib.metadata, VersionResolver unpatched, or vidbyte --version, which read the shared editable install's stale metadata locally (spec section 13). The CLI fallback is reached by making the metadata lookup fail; the MCP client's version is captured from the initialize request it sends to a recording transport.
FUNCTION INVENTORY: test_every_version_bearing_place_reads_the_release_version.
COMMON MODIFICATION PATTERNS: A routine version bump changes nothing here, because every place is compared with pyproject.toml's version and FIRST_LOADER_RELEASE is only a floor; a new version-bearing place adds a reader and a PLACES row.
WHAT NOT TO DO IN THIS FILE: 1. Do not grep for the old literal instead; a merge from main can change what it finds (spec section 12.4). 2. Do not read the installed distribution's metadata.
KNOWN EDGE CASES: YAML reads the placeholder 0.3.1 as text, since it has two dots. The README has other install lines without a pinned version; only the pinned one is a version place.
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 6.1 INV-16, 8.1 D-13, 9.2 row 7, 12.3 rows 3 to 10, 13 Version)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_release.py
"""

from __future__ import annotations

import asyncio
import inspect
import re
import tomllib
from collections.abc import Callable, Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import yaml

import vidbyte
from vidbyte import cli as cli_module
from vidbyte.cli import VersionResolver
from vidbyte.mcp_server.server.core import McpStudioServer
from vidbyte.tools.mcp.client import McpClient

# EC-29, D-13: 0.3.1 is the first release that carries the public
# loader, so a later bump may raise the version but never go below it.
FIRST_LOADER_RELEASE = (0, 3, 1)
REPO_ROOT = Path(__file__).resolve().parents[3]


class RecordingTransport:
    """Stands in for an MCP transport and keeps every request the client sends."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, Mapping[str, Any] | None]] = []

    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.requests.append((method, params))
        return {}


def text_of(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def pyproject_version(monkeypatch: pytest.MonkeyPatch) -> str:
    return str(tomllib.loads(text_of("pyproject.toml"))["project"]["version"])


def package_version(monkeypatch: pytest.MonkeyPatch) -> str:
    return vidbyte.__version__


def cli_fallback_version(monkeypatch: pytest.MonkeyPatch) -> str:
    # A source checkout with no installed metadata makes the CLI fall back to its own literal.
    def not_installed(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(cli_module.metadata, "version", not_installed)
    return VersionResolver().resolve()


def mcp_server_default_version(monkeypatch: pytest.MonkeyPatch) -> str:
    return str(inspect.signature(McpStudioServer).parameters["version"].default)


def mcp_client_info_version(monkeypatch: pytest.MonkeyPatch) -> str:
    # The version the client announces in its initialize request.
    transport = RecordingTransport()
    asyncio.run(McpClient(transport).initialize())  # type: ignore[arg-type]
    ((method, params),) = transport.requests
    assert method == "initialize" and params is not None
    return str(params["clientInfo"]["version"])


def readme_pinned_install_version(monkeypatch: pytest.MonkeyPatch) -> str:
    return ",".join(re.findall(r"^pip install vidbyte-sdk==(\S+)$", text_of("README.md"), flags=re.MULTILINE))


def llms_version(monkeypatch: pytest.MonkeyPatch) -> str:
    return ",".join(re.findall(r"identifies the package as version `([^`]+)`", text_of("llms.txt")))


def bug_template_placeholder(monkeypatch: pytest.MonkeyPatch) -> str:
    fields = yaml.safe_load(text_of(".github/ISSUE_TEMPLATE/bug_report.yml"))["body"]
    (version_field,) = [item for item in fields if item.get("id") == "version"]
    return str(version_field["attributes"]["placeholder"])


PLACES: list[tuple[str, Callable[[pytest.MonkeyPatch], str]]] = [
    ("pyproject.toml project.version", pyproject_version),
    ("vidbyte.__version__", package_version),
    ("CLI VersionResolver fallback", cli_fallback_version),
    ("MCP server default version", mcp_server_default_version),
    ("MCP client clientInfo version", mcp_client_info_version),
    ("README pinned install line", readme_pinned_install_version),
    ("llms.txt version sentence", llms_version),
    ("bug report version placeholder", bug_template_placeholder),
]


@pytest.mark.parametrize(("place", "read"), PLACES, ids=[row[0] for row in PLACES])
def test_every_version_bearing_place_reads_the_release_version(monkeypatch: pytest.MonkeyPatch, place: str, read: Callable[[pytest.MonkeyPatch], str]) -> None:
    # AC-11, INV-16, EC-29: the CLI raises its floor to this release and C029 compares it with the vendored contract.
    assert read(monkeypatch) == pyproject_version(monkeypatch), place
    assert tuple(int(part) for part in pyproject_version(monkeypatch).split(".")[:3]) >= FIRST_LOADER_RELEASE, place
