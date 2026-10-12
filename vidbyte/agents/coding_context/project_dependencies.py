"""FILE: vidbyte/agents/coding_context/project_dependencies.py

PURPOSE: Defines ProjectDependencies, which reads the dependency names a project declares in the manifests directly in its root folder (pyproject.toml, requirements.txt, package.json, and Cargo.toml), so the model knows the frameworks and test tools in play.
ROLE IN CODEBASE: Called once per CodingAgent by EnvironmentLoader (vidbyte/agents/coding_context/environment.py); reads its caps from vidbyte/lib/constants/coding.py, and its names reach the model through EnvironmentContextItem.dependencies (vidbyte/context/primitives/documents.py).
ARCHITECTURE NOTE: Plain deterministic parsing with the standard library (tomllib, json, re); nothing is installed, resolved, or run. Every manifest is optional, so a missing, oversized, undecodable, or malformed one gives no names rather than an error: the names only inform the model and never gate the agent.
FUNCTION INVENTORY: ProjectDependencies.read is the narrated main function; _text reads one manifest up to the size cap; _toml and _json parse text into a table; _python_names, _requirement_names, _node_names, and _rust_names pull the names out of one manifest each.
COMMON MODIFICATION PATTERNS: A new manifest adds its file name to the reads in read, one _<language>_names helper, and its names to the list in read.
WHAT NOT TO DO IN THIS FILE: 1. Do not run a package manager or import the project; reading the files is enough. 2. Do not raise for a bad manifest. 3. Do not search parent or child folders; only the root folder's own manifests count.
KNOWN EDGE CASES: Names are kept in first-mention order and repeated names once, so a runtime dependency listed again as a development one appears once. Versions (bare or in parentheses), extras, markers, and requirements.txt comments are dropped. A requirements.txt line that is a URL, an option, or an include gives no name. Only the first CODING_ENVIRONMENT_MAX_DEPENDENCIES names are kept.
RELATED DOCS: docs/design/coding-agent-environment-context.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from vidbyte.lib.constants.coding import (
    CODING_ENVIRONMENT_MANIFEST_MAX_BYTES,
    CODING_ENVIRONMENT_MAX_DEPENDENCIES,
)

# A requirement's name at the start of a PEP 508 string, followed by
# extras, a version (bare or in parentheses, as Poetry 2 writes it), a
# marker, a URL, a requirements.txt comment after whitespace, or nothing.
# A URL, a path, or a VCS line such as git+https:// still gives no name.
_REQUIREMENT_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?=[\[(<>=!~;@]|(?<=\s)#|$)")


class ProjectDependencies:
    """Reads the dependency names the root folder's manifests declare."""

    @classmethod
    def read(cls, root: Path) -> tuple[str, ...]:
        """Return the names root's manifests declare, each once, at most CODING_ENVIRONMENT_MAX_DEPENDENCIES of them."""
        # Read each manifest the root folder has. A missing, oversized,
        # or malformed one reads as empty, so it adds no names.
        pyproject = cls._toml(cls._text(root / "pyproject.toml"))
        requirements = cls._text(root / "requirements.txt")
        package_json = cls._json(cls._text(root / "package.json"))
        cargo = cls._toml(cls._text(root / "Cargo.toml"))

        # Collect runtime and development names alike, since the test
        # and build tools are what the model most often needs to know.
        names = [*cls._python_names(pyproject), *cls._requirement_names(requirements), *cls._node_names(package_json), *cls._rust_names(cargo)]

        # @intent blank-manifest-key-gives-no-name
        # A table key such as "" or " " is malformed, not a name, and
        # EnvironmentContextItem rejects a blank one.
        names = [name.strip() for name in names if isinstance(name, str) and name.strip()]

        # Keep each name once, in the order it first appeared, and cap
        # the list so a huge manifest cannot fill the context.
        return tuple(dict.fromkeys(names))[:CODING_ENVIRONMENT_MAX_DEPENDENCIES]

    @staticmethod
    def _text(path: Path) -> str:
        """Return path's text, or "" when it is not a regular file, cannot be read, or is over the size cap."""
        try:
            if not path.is_file():
                return ""
            with path.open("rb") as handle:
                total_bytes = os.fstat(handle.fileno()).st_size
                raw = handle.read(CODING_ENVIRONMENT_MANIFEST_MAX_BYTES)
        except OSError:
            return ""
        # "utf-8-sig" drops the byte-order mark Windows PowerShell writes,
        # which npm and pip accept but tomllib, json, and the name match do not.
        return "" if total_bytes > CODING_ENVIRONMENT_MANIFEST_MAX_BYTES else raw.decode("utf-8-sig", errors="replace")

    @staticmethod
    def _toml(text: str) -> dict[str, Any]:
        """Return text parsed as TOML, or an empty table when it is not valid TOML."""
        # @intent deeply-nested-manifest-gives-no-name
        # The parser raises RecursionError on input nested thousands deep; that is malformed too.
        try:
            return tomllib.loads(text)
        except (tomllib.TOMLDecodeError, RecursionError):
            return {}

    @staticmethod
    def _json(text: str) -> dict[str, Any]:
        """Return text parsed as a JSON object, or an empty table when it is not one."""
        # @intent deeply-nested-manifest-gives-no-name
        # The parser raises RecursionError on input nested thousands deep; that is malformed too.
        try:
            data = json.loads(text) if text else {}
        except (json.JSONDecodeError, RecursionError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _python_names(pyproject: dict[str, Any]) -> list[str]:
        """Return the names in pyproject's PEP 621 dependencies, optional dependencies, and dependency groups, and its Poetry tables."""
        # A table of the wrong shape, such as a number where a table of
        # groups belongs, means a malformed manifest; it gives no names.
        # A list or table of the wrong shape inside one is skipped.
        try:
            project = pyproject.get("project", {})
            poetry = pyproject.get("tool", {}).get("poetry", {})
            lists = [project.get("dependencies", []), *project.get("optional-dependencies", {}).values(), *pyproject.get("dependency-groups", {}).values()]
            tables = [poetry.get("dependencies", {}), poetry.get("dev-dependencies", {}), *(group.get("dependencies", {}) for group in poetry.get("group", {}).values())]
        except AttributeError:
            return []
        requirements = (entry for entries in lists if isinstance(entries, list) for entry in entries if isinstance(entry, str))
        matches = (_REQUIREMENT_NAME.match(requirement) for requirement in requirements)
        poetry_names = (name for table in tables if isinstance(table, dict) for name in table if name != "python")
        return [*(match.group(1) for match in matches if match), *poetry_names]

    @staticmethod
    def _requirement_names(text: str) -> list[str]:
        """Return the names on requirements.txt lines, skipping comments, options, includes, and URLs."""
        lines = (line for line in text.splitlines() if not line.lstrip().startswith(("#", "-")))
        matches = (_REQUIREMENT_NAME.match(line) for line in lines)
        return [match.group(1) for match in matches if match]

    @staticmethod
    def _node_names(package_json: dict[str, Any]) -> list[str]:
        """Return the names in package.json's dependencies and devDependencies."""
        tables = (package_json.get("dependencies", {}), package_json.get("devDependencies", {}))
        return [name for table in tables if isinstance(table, dict) for name in table]

    @staticmethod
    def _rust_names(cargo: dict[str, Any]) -> list[str]:
        """Return the names in Cargo.toml's dependencies and dev-dependencies."""
        tables = (cargo.get("dependencies", {}), cargo.get("dev-dependencies", {}))
        return [name for table in tables if isinstance(table, dict) for name in table]


__all__ = ["ProjectDependencies"]
