"""FILE: scripts/run_ci.py

PURPOSE:
    Provides the one cross-platform command that developers, coding agents, pull
    requests, and releases use to prove the Vidbyte SDK source and distributions
    are production-ready. It owns verification only; it never publishes.
ROLE IN CODEBASE:
    .github/workflows/ci.yml invokes this module after installing the dev extra.
    CONTRIBUTING.md and global design-doc skills direct local agents here. The
    package stage calls Python build, Twine, venv, pip, and installed SDK APIs.
ARCHITECTURE NOTE:
    Source and package gates are independently addressable so the Python matrix
    can fan out before one job builds the exact releasable artifacts.
FUNCTION INVENTORY:
    CiPipeline.run() -> None: orchestrates the selected verification stage.
    parse_args() -> PipelineConfig: validates the command-line contract.
    main() -> int: renders diagnostic failures and returns the process status.
COMMON MODIFICATION PATTERNS:
    Add a source invariant to run_source; add an installed-artifact invariant to
    run_package; keep CI YAML as a thin caller of this module.
WHAT NOT TO DO IN THIS FILE:
    1. Do not publish packages; .github/workflows/publish.yml owns publication.
    2. Do not skip the full tests or silently narrow pytest discovery.
    3. Do not mutate source files or delete caller-owned distribution contents.
KNOWN EDGE CASES:
    Persistent --dist-dir targets must contain no prior wheel/sdist artifacts.
    Windows and POSIX virtual environments use different interpreter locations.
RELATED DOCS:
    docs/design/green-ci-pipeline-and-design-skill-enforcement.md
    docs/design/context-write-path-integrity.md
    CONTRIBUTING.md
TESTS:
    Exercised end-to-end by .github/workflows/ci.yml on Python 3.11 and 3.12.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "vidbyte"
REQUIRED_PROMPT_ASSET = "vidbyte/prompts/prompts/error_correction_auditor.md"


class CiFailure(RuntimeError):
    """Actionable failure at one local CI boundary."""


@dataclass(frozen=True)
class PipelineConfig:
    """Validated command-line settings for one CI invocation."""

    stage: str
    dist_dir: Path | None


class CiPipeline:
    """Runs source and package gates with the current Python interpreter."""

    def __init__(self, config: PipelineConfig) -> None:
        """Retain the validated stage and optional artifact destination."""
        self._config = config

    def run(self) -> None:
        """Run the selected gate or the complete source-to-package pipeline."""
        if self._config.stage in {"all", "source"}:
            self.run_source()
        if self._config.stage in {"all", "package"}:
            self.run_package()

    def run_source(self) -> None:
        """Verify repository hygiene, import syntax, write-path integrity, and tests."""
        self._assert_no_tracked_bytecode()
        self._run_command([sys.executable, "-m", "compileall", "-q", str(PACKAGE_ROOT)])
        self._run_command(
            [sys.executable, str(REPOSITORY_ROOT / "scripts" / "check_context_write_paths.py")],
        )
        self._run_command([sys.executable, str(REPOSITORY_ROOT / "lint" / "run.py")])
        self._run_command([sys.executable, "-m", "pytest"])

    def run_package(self) -> None:
        """Build, inspect, install, and smoke-test the distribution artifacts."""
        if self._config.dist_dir is None:
            with tempfile.TemporaryDirectory(prefix="vidbyte-sdk-dist-") as directory:
                self._verify_package(Path(directory))
            return
        dist_dir = self._config.dist_dir.resolve()
        self._assert_distribution_target_is_empty(dist_dir)
        self._verify_package(dist_dir)

    def _verify_package(self, dist_dir: Path) -> None:
        dist_dir.mkdir(parents=True, exist_ok=True)
        self._run_command(
            [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        )
        wheel, source_dist = self._distribution_pair(dist_dir)
        self._run_command(
            [sys.executable, "-m", "twine", "check", str(wheel), str(source_dist)],
        )
        self._inspect_wheel(wheel)
        self._verify_clean_install(wheel)

    def _assert_no_tracked_bytecode(self) -> None:
        result = self._run_command(
            ["git", "ls-files", "-z"],
            capture_output=True,
        )
        tracked = tuple(item for item in result.stdout.split("\0") if item)
        generated = sorted(
            path
            for path in tracked
            if "__pycache__" in Path(path).parts
            or Path(path).suffix.lower() in {".pyc", ".pyo"}
        )
        if generated:
            rendered = "\n  - ".join(generated)
            raise CiFailure(
                "Tracked Python bytecode makes the repository platform-specific. "
                f"Remove these files from Git:\n  - {rendered}"
            )

    @staticmethod
    def _assert_distribution_target_is_empty(dist_dir: Path) -> None:
        if not dist_dir.exists():
            return
        artifacts = sorted(
            (*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")),
        )
        if artifacts:
            rendered = ", ".join(str(path) for path in artifacts)
            raise CiFailure(
                f"Distribution target {dist_dir} already contains artifacts: {rendered}. "
                "Use an empty directory so only this commit's outputs are verified."
            )

    @staticmethod
    def _distribution_pair(dist_dir: Path) -> tuple[Path, Path]:
        wheels = sorted(dist_dir.glob("*.whl"))
        source_dists = sorted(dist_dir.glob("*.tar.gz"))
        if len(wheels) != 1 or len(source_dists) != 1:
            raise CiFailure(
                "Package build must produce exactly one wheel and one source "
                f"distribution; found wheels={wheels}, source_dists={source_dists}."
            )
        return wheels[0], source_dists[0]

    @staticmethod
    def _inspect_wheel(wheel: Path) -> None:
        with ZipFile(wheel) as archive:
            names = set(archive.namelist())
        if REQUIRED_PROMPT_ASSET not in names:
            raise CiFailure(
                f"Wheel {wheel.name} is missing required asset {REQUIRED_PROMPT_ASSET}."
            )
        generated = sorted(
            name
            for name in names
            if "__pycache__" in Path(name).parts
            or Path(name).suffix.lower() in {".pyc", ".pyo"}
        )
        if generated:
            raise CiFailure(
                f"Wheel {wheel.name} contains generated Python artifacts: {generated}."
            )

    def _verify_clean_install(self, wheel: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="vidbyte-sdk-install-") as directory:
            environment = Path(directory) / "venv"
            smoke_root = Path(directory) / "smoke"
            venv.EnvBuilder(with_pip=True).create(environment)
            smoke_root.mkdir()
            python = self._venv_python(environment)
            self._run_command(
                [str(python), "-m", "pip", "install", "--no-cache-dir", str(wheel)],
            )
            self._run_command([str(python), "-m", "pip", "check"])
            self._run_command(
                [str(python), "-c", self._smoke_program()],
                cwd=smoke_root,
                clean_python_path=True,
            )

    @staticmethod
    def _venv_python(environment: Path) -> Path:
        if os.name == "nt":
            return environment / "Scripts" / "python.exe"
        return environment / "bin" / "python"

    @staticmethod
    def _smoke_program() -> str:
        return (
            "from importlib.metadata import entry_points, version; "
            "import vidbyte; "
            "from vidbyte import Prompts, VidbyteSDK; "
            "distribution_version = version('vidbyte-sdk'); "
            "assert vidbyte.__version__ == distribution_version; "
            "assert Prompts().keys(); "
            "VidbyteSDK(); "
            "scripts = {item.name: item for item in entry_points(group='console_scripts')}; "
            "required = {'vidbyte-sdk', 'vidbyte-mcp-server'}; "
            "assert required <= scripts.keys(); "
            "[scripts[name].load() for name in sorted(required)]; "
            "print(f'Installed vidbyte-sdk {distribution_version} passed smoke checks.')"
        )

    @staticmethod
    def _run_command(command: list[str], *, cwd: Path = REPOSITORY_ROOT, capture_output: bool = False, clean_python_path: bool = False) -> subprocess.CompletedProcess[str]:
        """Run one gate command with deterministic Python artifact settings."""
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if clean_python_path:
            environment.pop("PYTHONPATH", None)
        print(f"> {' '.join(command)}", flush=True)
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                check=True,
                capture_output=capture_output,
                text=True,
            )
        except FileNotFoundError as exc:
            raise CiFailure(
                f"Required command {command[0]!r} is unavailable while running "
                f"{' '.join(command)} from {cwd}."
            ) from exc
        except subprocess.CalledProcessError as exc:
            output = "\n".join(
                part.strip()
                for part in (exc.stdout or "", exc.stderr or "")
                if part.strip()
            )
            detail = f"\n{output}" if output else ""
            raise CiFailure(
                f"Command failed with exit code {exc.returncode}: "
                f"{' '.join(command)} (cwd={cwd}).{detail}"
            ) from exc


def parse_args(argv: list[str] | None = None) -> PipelineConfig:
    """Parse and normalize the stable local CI command-line interface."""
    parser = argparse.ArgumentParser(
        description="Run the Vidbyte SDK production CI gates locally.",
    )
    parser.add_argument(
        "--stage",
        choices=("all", "source", "package"),
        default="all",
        help="Gate to run; defaults to the complete pipeline.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help="Persistent package output directory; must contain no prior artifacts.",
    )
    args = parser.parse_args(argv)
    return PipelineConfig(stage=args.stage, dist_dir=args.dist_dir)


def main(argv: list[str] | None = None) -> int:
    """Run CI and render one concise actionable failure to stderr."""
    try:
        CiPipeline(parse_args(argv)).run()
    except CiFailure as exc:
        print(f"CI failed: {exc}", file=sys.stderr)
        return 1
    print("CI passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
