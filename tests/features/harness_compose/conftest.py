"""FILE: tests/features/harness_compose/conftest.py

PURPOSE: Shared offline fixtures for the harness_compose pack: lazy imports of the spec §8.5 contract names, a sandbox with a redirected user home and temporary folder, the real git on PATH with the machine's git configuration shut out, git helpers and an independent tree oracle, stand-in scenarios of the base pack's fake_harness.py with a per-launch log reader, a step binder, a recording spy around CliRunner.run, prompt-file renderers, the ThreadComposeError check, and process liveness checks.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/harness_compose/. The stand-in runs as a real child process through the config records' <harness>_command fields (spec §13 "Real seams"); git, CliRunner, the nine thread functions and the filesystem are real and never mocked.
ARCHITECTURE NOTE: Every vidbyte import happens inside the compose_api fixture, compose first, so a missing module fails each test at setup instead of aborting collection. The spy wraps CliRunner.run and always awaits the real method, so it only records each child's invocation and the order in which children start and finish; that order is the deterministic evidence for one-writer and Grok-serialization rules. The tree oracle builds snapshot trees with the test's own git and a temporary index outside the repository, so expected diffs and tree ids never come from the code under test.
FUNCTION INVENTORY: compose_api returns the contract names; Sandbox builds folders, repositories, scenarios and stand-ins, reads the stand-in logs per launch and holds the git helpers (git, make_repo, commit, status, worktrees, index_bytes, refs, tree_of, tree_diff, files, leftovers); sandbox makes one per test with home, PATH, git configuration and temporary folder redirected; RunSpy and runs record every CliRunner child; StepBinder and steps bind steps against stand-in scenarios; check_compose_error asserts the ThreadComposeError packet and the INV-6 message order; fast_stop shrinks NATIVE_KILL_WAIT_SECONDS; wait_until polls with a deadline; process_alive and alive report liveness; render, prompt_fields and literal_chunks read the prompt files; verdict_json, plan_json, round_json and selection_json build model answers; the launch_* helpers read one launch's prompt, session, workspace and observations; pack hands the constants and helpers to the test modules.
COMMON MODIFICATION PATTERNS: Add a stand-in behaviour as a scenario field read with .get by fake_harness.py; add a fixture here only when two or more modules in this pack need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub compose, the nine functions, CliRunner, git or the filesystem; a missing feature must stay red. 2. Do not leave PATH, USERPROFILE, HOME or the temporary folder pointing at the developer's machine, and do not put a folder that holds a vendor program on PATH. 3. Do not let the developer's git configuration or vendor keys in: GIT_CONFIG_NOSYSTEM, an empty GIT_CONFIG_GLOBAL and GIT_CEILING_DIRECTORIES stay set, and the vendor credential variables stay removed. 4. Never use a real key; every key here is a generated placeholder.
KNOWN EDGE CASES: On win32 git is reached through its own installation folder appended to PATH (a copied git.exe cannot find its runtime); on POSIX through a symbolic link in the sandbox, so PATH stays closed. pip's distlib t64.exe is the launcher behind every `.exe` stand-in; tests that need one skip when pip lacks it. git prints paths with forward slashes on win32, so paths are compared after resolve and os.path.normcase. Stand-in logs of a still-running launch can end in a partial line, which the reader skips.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6, §8.5, §9.2, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import io
import json
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
import uuid
import zipfile
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PACK = Path(__file__).resolve().parent
REPO_ROOT = PACK.parents[2]
FAKE = REPO_ROOT / "tests" / "features" / "harness_threads" / "fake_harness.py"
PROMPTS = REPO_ROOT / "vidbyte" / "harnesses" / "native" / "compose" / "prompts"
GIT = shutil.which("git")
HARNESSES = ("grok", "opencode", "muse")
VERBS = ("run", "continue", "fork")
COMMAND_FIELDS = {"grok": "grok_command", "opencode": "opencode_command", "muse": "muse_command"}
CONFIG_NAMES = {"grok": "GrokThreadConfig", "opencode": "OpencodeThreadConfig", "muse": "MuseThreadConfig"}
EXEC_ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}
WORKSPACE_OPTIONS = {"grok": "--cwd", "opencode": "--dir", "muse-exec": "--workspace"}
VENDOR_NAMES = ("grok", "opencode", "muse", "wsl")
OPENCODE_MODEL = "deepseek/deepseek-v4-pro"
API_KEY = "vbk-compose-0123456789abcdef0123456789abcdef"
PROMPT = "Add a --verbose flag to cli.py."
TASK = "Make the CLI start faster."
CALL_TIMEOUT_SECONDS = 60.0
FAST_KILL_WAIT_SECONDS = 0.5
SLACK_SECONDS = 5.0
POLL_SECONDS = 0.05
WAIT_SECONDS = 120.0
FRAGMENT_CHARS = 12
GIT_LOCATION_VARIABLES = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY",
    "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
)
CREDENTIAL_VARIABLES = ("XAI_API_KEY", "GROK_CODE_XAI_API_KEY", "META_API_KEY", "DEEPSEEK_API_KEY", "ZAI_API_KEY", "ZHIPU_API_KEY", "OPENCODE_CONFIG_CONTENT")
GIT_GLOBAL_OPTIONS = ("--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.safecrlf=false")
GIT_IDENTITY = ("-c", "user.name=Compose Tests", "-c", "user.email=compose-tests@example.invalid", "-c", "commit.gpgsign=false")
WORKTREE_PREFIX = "vidbyte-compose-worktree-"
INDEX_PREFIX = "vidbyte-compose-index-"
REDACTED = "[redacted]"
PROMPT_SEPARATOR = "\n\n"
DIAGNOSTIC_FIELDS = ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests")
DEFAULT_FILES = {"README.md": "# Demo\n", "cli.py": "def main():\n    return 0\n"}
TREE_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_digest(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def key_digest(text: str) -> dict[str, Any]:
    return {"sha256": text_digest(text), "length": len(text)}


def private_home(home: Path, workspace: Path) -> Path:
    # Base INV-13 / D-24: <home>/.vidbyte/grok-homes/<first 16 hex of
    # sha256(normcase(resolved workspace))>.
    key = hashlib.sha256(os.path.normcase(str(Path(workspace).resolve())).encode("utf-8")).hexdigest()[:16]
    return home / ".vidbyte" / "grok-homes" / key


def path_spellings(path: Path | str) -> tuple[str, ...]:
    text = str(path)
    return tuple(dict.fromkeys((text, Path(text).as_posix())))


def normalized(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def same_path(left: Path | str, right: Path | str) -> bool:
    return normalized(left) == normalized(right)


def inside(path: Path | str, folder: Path | str) -> bool:
    # True when path is folder or lies below it, compared after resolve
    # and normcase.
    child, parent = Path(normalized(path)), Path(normalized(folder))
    return child == parent or parent in child.parents


def fresh_key(label: str) -> str:
    # A placeholder key in the base key pattern (^[!-z|~]+$), random so
    # its fragments cannot occur by chance: the label is cut to six
    # characters, so every 12-character fragment holds random hex.
    return f"vbk-{label[:6]}-{uuid.uuid4().hex}{uuid.uuid4().hex}"


def fragments(secret: str, size: int = FRAGMENT_CHARS) -> set[str]:
    return {secret[start : start + size] for start in range(len(secret) - size + 1)}


def leaks(text: str, secrets: Iterable[str]) -> list[str]:
    # Every fragment of any secret that occurs in text.
    return sorted(piece for secret in secrets for piece in fragments(secret) if piece in text)


def command_line_units(text: str) -> int:
    # How CreateProcess counts one argument: quoted as subprocess quotes
    # it, in UTF-16 code units (base RecordFieldValidator rule).
    return len(subprocess.list2cmdline([text]).encode("utf-16-le")) // 2


def launcher_bytes() -> bytes | None:
    # pip's console-script launcher: runs `<python from the shebang>
    # <this exe>`, where the exe ends with a zipped __main__.
    try:
        pip = importlib.import_module("pip")
    except ImportError:
        return None
    path = Path(pip.__file__).parent / "_vendor" / "distlib" / "t64.exe"
    return path.read_bytes() if path.is_file() else None


def prompt_text(stem: str) -> str:
    return (PROMPTS / f"{stem}.md").read_text(encoding="utf-8")


def render(stem: str, **values: Any) -> str:
    # One prompt file rendered the way spec INV-17 renders it, then
    # stripped, so containment checks ignore edge whitespace.
    return prompt_text(stem).format_map({name: str(value) for name, value in values.items()}).strip()


def prompt_fields(stem: str) -> list[tuple[str, str | None, str | None]]:
    # (field name, format spec, conversion) of every placeholder.
    return [(name, spec, conversion) for _literal, name, spec, conversion in string.Formatter().parse(prompt_text(stem)) if name is not None]


def literal_chunks(stem: str) -> list[str]:
    # The fixed text between placeholders, each stripped; a prompt
    # compose sends always holds every chunk of each file it used.
    return [literal.strip() for literal, _name, _spec, _conversion in string.Formatter().parse(prompt_text(stem)) if literal.strip()]


def longest_literal(template: str) -> tuple[str, ...]:
    # The longest fixed chunk of a text that may hold placeholders.
    try:
        chunks = [literal.strip() for literal, *_rest in string.Formatter().parse(template) if literal.strip()]
    except ValueError:
        chunks = [template.strip()]
    return (max(chunks, key=len),) if chunks else ()


def verdict_json(decision: str, summary: str = "The change does what was asked.", findings: Iterable[str] = ()) -> str:
    return json.dumps({"decision": decision, "summary": summary, "findings": list(findings)})


def role_record(name: str, identity: str) -> dict[str, str]:
    return {"name": name, "identity": identity, "personality": "careful", "expertise": "python startup", "knowledge": "import time", "skills": "profiling", "goal": "a faster start"}


def plan_json(roles: Iterable[tuple[str, str]], *, analysis: str = "The CLI imports too much at start.", strategy: str = "One role per bottleneck.", coverage: str = "Imports, plugins and parsing.") -> str:
    return json.dumps({"task_analysis": analysis, "roster_strategy": strategy, "coverage_summary": coverage, "roles": [role_record(name, identity) for name, identity in roles]})


def round_json(kept: Iterable[int], summary: str = "Kept the strongest proposals.") -> str:
    return json.dumps({"kept": list(kept), "summary": summary})


def selection_json(proposal: int, approach: str = "Lazy imports.", rationale: str = "Lowest risk.", guidance: str = "Change cli.py only.") -> str:
    return json.dumps({"proposal": proposal, "approach": approach, "rationale": rationale, "guidance": guidance})


def launch_prompt(launch: dict[str, Any]) -> str | None:
    # The prompt one launch received: Grok's --single, opencode's stdin,
    # the operand after `--` for Muse.
    start = launch["start"]
    if launch["role"] == "grok":
        return start.get("options", {}).get("--single")
    if launch["role"] == "opencode":
        return start.get("stdin_text")
    operands = start.get("operands") or []
    return operands[0] if len(operands) == 1 else None


def launch_session(launch: dict[str, Any]) -> str | None:
    return next((record["session"] for record in launch["records"] if record["kind"] == "session"), None)


def launch_answered(launch: dict[str, Any]) -> bool:
    return any(record["kind"] == "answer" for record in launch["records"])


def launch_observed(launch: dict[str, Any]) -> dict[str, str | None] | None:
    return next((record["files"] for record in launch["records"] if record["kind"] == "observed"), None)


def launch_workspace(launch: dict[str, Any]) -> str | None:
    return launch["start"].get("options", {}).get(WORKSPACE_OPTIONS.get(launch["role"], ""))


def find_in_order(message: str, parts: Iterable[tuple[str, tuple[str, ...]]], *, fold: bool = True, start: int = 0) -> int:
    # INV-6: each element must appear after the previous one; any
    # spelling in a tuple counts. Returns the end of the last match.
    haystack = message.lower() if fold else message
    position = start
    for label, spellings in parts:
        hits = [(haystack.find(text.lower() if fold else text, position), text) for text in spellings if text]
        hits = [(index, text) for index, text in hits if index >= 0]
        assert hits, f"INV-6: {label} ({spellings[:1]!r}) is missing from the message after position {position}: {message!r}"
        index, text = min(hits)
        position = index + len(text)
    return position


def process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    stat_path = Path("/proc") / str(pid) / "stat"
    if Path("/proc/self").exists():
        try:
            stat = stat_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Sandbox:
    """One test's folders, repositories, stand-in scenarios, stand-in logs and git helpers."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.workspace = root / "ws"
        self.skill_root = root / "skill-src"
        self.bin = root / "bin"
        self.gitbin = root / "gitbin"
        self.tmp = root / "tmp"
        self.oracle = root / "oracle"
        self.fake_root = root / "fake"
        self.log_dir = self.fake_root / "log"
        self.state_dir = self.fake_root / "state"
        self.release_file = self.fake_root / "release.flag"
        self.git_global = root / "gitconfig-global"
        for folder in (self.home, self.workspace, self.skill_root, self.bin, self.gitbin, self.tmp, self.oracle, self.log_dir, self.state_dir):
            folder.mkdir(parents=True)
        self.git_global.write_text("", encoding="utf-8")
        self.scenarios = 0
        self.oracle_indexes = 0
        self.labels: dict[str, str] = {}

    # ---- scenarios and stand-ins -------------------------------------------------

    def scenario(self, program: str, *, label: str | None = None, **fields: Any) -> Path:
        self.scenarios += 1
        path = self.fake_root / f"scenario-{self.scenarios:03d}.json"
        data = {"program": program, "log_dir": str(self.log_dir), "state_dir": str(self.state_dir), "release_file": str(self.release_file), **fields}
        if label is not None:
            data["label"] = label
            self.labels[str(path)] = label
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def command(self, program: str, *, label: str | None = None, **fields: Any) -> tuple[str, ...]:
        return (sys.executable, "-u", str(FAKE), str(self.scenario(program, label=label, **fields)))

    def stand_in(self, folder: Path, name: str, program: str, *, label: str | None = None, **fields: Any) -> Path:
        # An executable named like the vendor program that runs
        # fake_harness.py: an `.exe` on win32, a script on POSIX.
        scenario = self.scenario(program, label=label, **fields)
        body = f"import runpy, sys\nsys.argv = [{str(FAKE)!r}, {str(scenario)!r}, *sys.argv[1:]]\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n"
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            launcher = launcher_bytes()
            if launcher is None:
                pytest.skip("pip's console-script launcher (distlib t64.exe) is needed to build an .exe stand-in")
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("__main__.py", body)
            target = folder / (name if name.lower().endswith(".exe") else name + ".exe")
            target.write_bytes(launcher + f'#!"{sys.executable}"\r\n'.encode("utf-8") + archive.getvalue())
            return target
        target = folder / name
        target.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        target.chmod(0o755)
        return target

    def make_skill(self, name: str) -> Path:
        folder = self.skill_root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test skill {name}.\n---\nUse {name}.\n", encoding="utf-8")
        return folder

    def release(self) -> None:
        self.release_file.write_text("go", encoding="utf-8")

    # ---- stand-in logs -------------------------------------------------------------

    def launches(self, role: str | None = None, label: str | None = None) -> list[dict[str, Any]]:
        # One entry per stand-in process, in launch order: its role, its
        # start record (argv, cwd, options, stdin, label, turn, rule) and
        # every record it wrote.
        found: list[dict[str, Any]] = []
        for path in sorted(self.log_dir.glob("*.jsonl"), key=lambda item: int(item.name.split("-", 1)[0])):
            records: list[dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
            start = next((record for record in records if record.get("kind") == "start"), None)
            if start is None:
                continue
            file_role = path.name.split("-", 1)[1].rsplit("-", 1)[0]
            if role is not None and file_role != role:
                continue
            if label is not None and start.get("label") != label:
                continue
            found.append({"role": file_role, "label": start.get("label"), "start": start, "records": records, "pid": start.get("pid")})
        return found

    def only_launch(self, label: str) -> dict[str, Any]:
        found = self.launches(label=label)
        assert len(found) == 1, f"expected exactly one launch of {label}, got {[item['start'].get('argv') for item in found]}"
        return found[0]

    def started_labels(self) -> list[str | None]:
        return [item["label"] for item in self.launches()]

    # ---- git helpers ---------------------------------------------------------------

    def git_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = {name: value for name, value in os.environ.items() if name not in GIT_LOCATION_VARIABLES}
        environment.update(extra or {})
        return environment

    def git(self, *args: str, cwd: Path | str | None = None, check: bool = True, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
        # The test's own git, with compose's global options and never a
        # caller's location variables.
        finished = subprocess.run([str(GIT), *GIT_GLOBAL_OPTIONS, *args], cwd=str(cwd or self.workspace), env=self.git_env(extra_env), capture_output=True, stdin=subprocess.DEVNULL, check=False, timeout=120)
        if check and finished.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed with {finished.returncode}: {finished.stderr.decode('utf-8', 'replace')}")
        return finished

    def write(self, folder: Path, files: dict[str, str]) -> None:
        for relative, text in files.items():
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))

    def make_repo(self, folder: Path | None = None, files: dict[str, str] | None = None, *, commit: bool = True) -> Path:
        target = folder or self.workspace
        target.mkdir(parents=True, exist_ok=True)
        self.git("-c", "init.defaultBranch=main", "init", "-q", cwd=target)
        self.write(target, DEFAULT_FILES if files is None else files)
        if commit:
            self.commit(target)
        return target

    def commit(self, folder: Path | None = None, message: str = "commit") -> None:
        target = folder or self.workspace
        self.git("add", "-A", cwd=target)
        self.git(*GIT_IDENTITY, "commit", "-q", "--allow-empty", "-m", message, cwd=target)

    def status(self, folder: Path | None = None) -> set[str]:
        output = self.git("status", "--porcelain=v1", "-uall", cwd=folder).stdout.decode("utf-8")
        return {line for line in output.splitlines() if line}

    def worktrees(self, folder: Path | None = None) -> int:
        output = self.git("worktree", "list", "--porcelain", cwd=folder).stdout.decode("utf-8")
        return sum(1 for line in output.splitlines() if line.startswith("worktree "))

    def index_bytes(self, folder: Path | None = None) -> bytes | None:
        path = (folder or self.workspace) / ".git" / "index"
        return path.read_bytes() if path.is_file() else None

    def refs(self, folder: Path | None = None) -> tuple[str, ...]:
        # Every ref, HEAD's target and value, and the stash list.
        return (
            self.git("for-each-ref", "--format=%(refname) %(objectname)", cwd=folder).stdout.decode("utf-8"),
            self.git("symbolic-ref", "-q", "HEAD", cwd=folder, check=False).stdout.decode("utf-8"),
            self.git("rev-parse", "--verify", "--quiet", "HEAD", cwd=folder, check=False).stdout.decode("utf-8"),
            self.git("stash", "list", cwd=folder, check=False).stdout.decode("utf-8"),
        )

    def toplevel(self, folder: Path | None = None) -> str:
        return self.git("rev-parse", "--show-toplevel", cwd=folder).stdout.decode("utf-8").strip()

    def tree_of(self, folder: Path | None = None) -> str:
        # The oracle snapshot: the tree of the whole working tree, built
        # through a temporary index outside the repository (spec INV-7).
        top = self.toplevel(folder)
        self.oracle_indexes += 1
        environment = {"GIT_INDEX_FILE": str(self.oracle / f"index-{self.oracle_indexes}")}
        if self.git("rev-parse", "--verify", "--quiet", "HEAD", cwd=top, check=False).returncode == 0:
            self.git("read-tree", "HEAD", cwd=top, extra_env=environment)
        self.git("add", "-A", cwd=top, extra_env=environment)
        return self.git("write-tree", cwd=top, extra_env=environment).stdout.decode("utf-8").strip()

    def tree_diff(self, before: str, after: str, folder: Path | None = None) -> tuple[tuple[str, ...], str]:
        # The oracle diff between two trees, with compose's flags.
        top = self.toplevel(folder)
        names = self.git("diff", "--name-only", "-z", "--no-renames", before, after, cwd=top).stdout.decode("utf-8")
        text = self.git("diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", before, after, cwd=top).stdout.decode("utf-8", "replace")
        return tuple(name for name in names.split("\x00") if name), text

    def files(self, folder: Path | None = None) -> dict[str, str]:
        # Every working file outside .git, with its SHA-256.
        base = folder or self.workspace
        found: dict[str, str] = {}
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base).as_posix()
            if relative == ".git" or relative.startswith(".git/") or not path.is_file():
                continue
            found[relative] = sha256_bytes(path.read_bytes())
        return found

    def leftovers(self) -> list[str]:
        # What is left in the sandbox's temporary folder.
        return sorted(path.name for path in self.tmp.iterdir())

    def path_with_git(self) -> str:
        # PATH: the sandbox bin first, then a folder that holds git and
        # no vendor program.
        git_folder = Path(str(GIT)).parent
        if sys.platform == "win32":
            names = {path.name.lower() for path in git_folder.iterdir()}
            if any(name.split(".", 1)[0] in VENDOR_NAMES for name in names):
                pytest.skip(f"{git_folder} holds a vendor program, so it cannot go on the sandbox PATH")
            return os.pathsep.join((str(self.bin), str(git_folder)))
        link = self.gitbin / "git"
        if not link.exists():
            link.symlink_to(Path(str(GIT)).resolve())
        return os.pathsep.join((str(self.bin), str(self.gitbin)))


@pytest.fixture
def compose_api() -> SimpleNamespace:
    # The spec §8.5 names, imported lazily; compose first, so its
    # absence is the failure every test reports.
    compose = importlib.import_module("vidbyte.harnesses.native.compose")
    native = importlib.import_module("vidbyte.harnesses.native")
    threads_records = importlib.import_module("vidbyte.lib.dataclasses.native_threads")
    threads_enums = importlib.import_module("vidbyte.lib.enums.native_threads")
    errors = importlib.import_module("vidbyte.lib.errors")
    return SimpleNamespace(
        compose=compose,
        native=native,
        records=importlib.import_module("vidbyte.lib.dataclasses.native_compose"),
        ensemble=importlib.import_module("vidbyte.lib.dataclasses.native_ensemble"),
        enums=importlib.import_module("vidbyte.lib.enums.native_compose"),
        enums_package=importlib.import_module("vidbyte.lib.enums"),
        constants=importlib.import_module("vidbyte.lib.constants.native_compose"),
        threads_constants=importlib.import_module("vidbyte.lib.constants.native_threads"),
        threads_enums=threads_enums,
        threads_records=threads_records,
        errors=errors,
        util=importlib.import_module("vidbyte.lib.util"),
        JsonText=importlib.import_module("vidbyte.lib.util.json_text").JsonText,
        RecordFieldValidator=importlib.import_module("vidbyte.lib.dataclasses.validation").RecordFieldValidator,
        CliRunner=importlib.import_module("vidbyte.lib.process").CliRunner,
        ThreadComposeError=errors.ThreadComposeError,
        ConfigurationError=errors.ConfigurationError,
        NativeThreadError=errors.NativeThreadError,
        AgentExecutionError=errors.AgentExecutionError,
        NativeThreadResult=threads_records.NativeThreadResult,
        NativeHarness=threads_enums.NativeHarness,
        NativeThreadVerb=threads_enums.NativeThreadVerb,
        NativeThreadProblem=threads_enums.NativeThreadProblem,
        GrokPermissionMode=threads_enums.GrokPermissionMode,
        GrokReasoningEffort=threads_enums.GrokReasoningEffort,
        functions={(harness, verb): getattr(native, f"{verb}_{harness}_thread") for harness in HARNESSES for verb in VERBS},
        configs={harness: getattr(threads_records, CONFIG_NAMES[harness]) for harness in HARNESSES},
    )


@pytest.fixture
def sandbox(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    # Spec §13: the user home and the temporary folder in the sandbox,
    # the real git on PATH, and the machine's git configuration,
    # repository-location variables and vendor credentials shut out.
    if GIT is None:
        pytest.skip("the real git must be on PATH when the tests start (spec §13)")
    box = Sandbox(tmp_path_factory.mktemp("case").resolve())
    monkeypatch.setenv("USERPROFILE", str(box.home))
    monkeypatch.setenv("HOME", str(box.home))
    for name in GIT_LOCATION_VARIABLES + CREDENTIAL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(box.git_global))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(box.root))
    monkeypatch.setenv("PATH", box.path_with_git())
    for name in ("TMP", "TEMP", "TMPDIR"):
        monkeypatch.setenv(name, str(box.tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(box.tmp))
    return box


class RunSpy:
    """Records every child CliRunner.run starts, and the order in which children start and finish."""

    def __init__(self, box: Sandbox) -> None:
        self.box = box
        self.invocations: list[Any] = []
        self.events: list[tuple[str, int]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch, runner_class: Any) -> None:
        original = runner_class.run
        spy = self

        async def run(runner: Any, invocation: Any) -> Any:
            # Observation only: the real run always happens.
            index = len(spy.invocations)
            spy.invocations.append(invocation)
            spy.events.append(("enter", index))
            try:
                return await original(runner, invocation)
            finally:
                spy.events.append(("exit", index))

        monkeypatch.setattr(runner_class, "run", run)

    @staticmethod
    def is_git(invocation: Any) -> bool:
        return os.path.basename(invocation.argv[0]).lower() in ("git", "git.exe")

    def git_calls(self) -> list[tuple[int, Any]]:
        return [(index, item) for index, item in enumerate(self.invocations) if self.is_git(item)]

    def vendor_calls(self) -> list[tuple[int, Any]]:
        return [(index, item) for index, item in enumerate(self.invocations) if not self.is_git(item)]

    def label(self, invocation: Any) -> str | None:
        argv = invocation.argv
        if len(argv) > 3 and argv[2] == str(FAKE):
            return self.box.labels.get(argv[3])
        return None

    def calls_of(self, label: str) -> list[int]:
        return [index for index, item in self.vendor_calls() if self.label(item) == label]

    @staticmethod
    def subcommand(invocation: Any) -> list[str]:
        return list(invocation.argv[1 + len(GIT_GLOBAL_OPTIONS) :])

    def position(self, kind: str, index: int) -> int:
        return self.events.index((kind, index))

    def interval(self, index: int) -> tuple[int, int]:
        return self.position("enter", index), self.position("exit", index)

    def overlap(self, first: int, second: int) -> bool:
        (start_a, end_a), (start_b, end_b) = self.interval(first), self.interval(second)
        return start_a < end_b and start_b < end_a


@pytest.fixture
def runs(compose_api: SimpleNamespace, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch) -> RunSpy:
    spy = RunSpy(sandbox)
    spy.install(monkeypatch, compose_api.CliRunner)
    return spy


class StepBinder:
    """Binds steps whose configs point at their own stand-in scenario."""

    def __init__(self, api: SimpleNamespace, box: Sandbox) -> None:
        self.api = api
        self.box = box

    def config(self, harness: str, *, fake: dict[str, Any] | None = None, label: str | None = None, **fields: Any) -> Any:
        values = {COMMAND_FIELDS[harness]: self.box.command(harness, label=label, **(fake or {})), "timeout_seconds": CALL_TIMEOUT_SECONDS, **fields}
        return self.api.configs[harness](**values)

    def bind(self, harness: str, verb: str = "run", thread_id: str | None = None, *, fake: dict[str, Any] | None = None, label: str | None = None, key: str = API_KEY, workspace: Path | str | None = None, model: str | None = None, skills: Iterable[Path | str] = (), plan: bool = False, edits: bool = False, config: Any = None, **fields: Any) -> Any:
        # bind_thread for a run or an unanchored fork, bind_continue
        # when a thread id is given.
        if config is None:
            if harness == "grok" and plan:
                fields.setdefault("permission_mode", self.api.GrokPermissionMode.PLAN)
            if harness == "grok" and edits:
                fields.setdefault("permission_mode", self.api.GrokPermissionMode.ACCEPT_EDITS)
            config = self.config(harness, fake=fake, label=label or f"{harness}-{verb}", **fields)
        if model is None and harness == "opencode":
            model = OPENCODE_MODEL
        arguments = {"api_key": key, "workspace": workspace if workspace is not None else self.box.workspace, "model": model, "skills": tuple(skills), "config": config}
        function = self.api.functions[(harness, verb)]
        if thread_id is None:
            return self.api.compose.bind_thread(function, **arguments)
        return self.api.compose.bind_continue(function, thread_id, **arguments)


@pytest.fixture
def steps(compose_api: SimpleNamespace, sandbox: Sandbox) -> StepBinder:
    return StepBinder(compose_api, sandbox)


@pytest.fixture
def check_compose_error(compose_api: SimpleNamespace) -> Callable[..., None]:
    def check(error: BaseException, *, problem: str, workspace: Path | str, observations: Iterable[tuple[str, tuple[str, ...]]] = (), git_text: str | None = None, add_texts: bool = False) -> None:
        # The ThreadComposeError packet (spec §8.5, §12.3 row 9) and the
        # INV-6 message order: problem and workspace, the observation,
        # git's text, the likely cause, the next step.
        api = compose_api
        assert isinstance(error, api.ThreadComposeError), f"expected ThreadComposeError, got {type(error).__name__}: {error}"
        assert isinstance(error, api.AgentExecutionError)
        kind = api.enums.ThreadComposeProblem(problem)
        assert error.problem is kind, f"expected {kind}, got {error.problem}: {error}"
        assert same_path(error.workspace, workspace), f"{error.workspace!r} is not {workspace!r}"
        cause = api.constants.THREAD_COMPOSE_ADD_LIKELY_CAUSE if add_texts else api.constants.THREAD_COMPOSE_LIKELY_CAUSES[kind]
        step = api.constants.THREAD_COMPOSE_ADD_NEXT_STEP if add_texts else api.constants.THREAD_COMPOSE_NEXT_STEPS[kind]
        assert error.likely_cause == cause and error.next_step == step, "likely_cause and next_step must be the texts written for this problem"
        assert error.likely_cause.strip() and error.next_step.strip()
        assert error.error_kind == kind.value
        assert tuple(error.DIAGNOSTIC_FIELDS) == DIAGNOSTIC_FIELDS
        assert set(error.details) == set(DIAGNOSTIC_FIELDS)
        assert error.related_docs == ("vidbyte/harnesses/README.md",)
        assert error.relevant_tests == ("tests/features/harness_compose",)
        assert {"problem", "workspace", "git_message"} <= set(error.safe_runtime_details)
        if git_text is not None:
            assert error.git_message is not None and git_text.lower() in error.git_message.lower(), f"git text {git_text!r} missing from {error.git_message!r}"
        message = str(error)
        head = max(
            find_in_order(message, [("problem", (kind.value, *longest_literal(api.constants.THREAD_COMPOSE_SUMMARIES[kind])))]),
            find_in_order(message, [("workspace", path_spellings(Path(workspace).resolve()) + path_spellings(workspace))]),
        )
        rest: list[tuple[str, tuple[str, ...]]] = list(observations)
        if git_text is not None:
            rest.append(("git text", (git_text,)))
        rest.extend([("likely cause", (error.likely_cause,)), ("next step", (error.next_step,))])
        find_in_order(message, rest, start=head)
        assert len(SENTENCE_END.findall(message)) >= 3, f"INV-6: the message is several complete sentences: {message!r}"

    return check


@pytest.fixture
def fast_stop(compose_api: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Base timing knob, read through vidbyte.lib.constants.native_threads
    # at call time.
    monkeypatch.setattr(compose_api.threads_constants, "NATIVE_KILL_WAIT_SECONDS", FAST_KILL_WAIT_SECONDS)
    return SimpleNamespace(kill_wait=FAST_KILL_WAIT_SECONDS, slack=SLACK_SECONDS)


@pytest.fixture
def wait_until() -> Callable[[Callable[[], bool], float], Awaitable[bool]]:
    async def poll(predicate: Callable[[], bool], timeout: float) -> bool:
        # Bounded polling; never a fixed sleep.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return True
            await asyncio.sleep(POLL_SECONDS)
        return predicate()

    return poll


@pytest.fixture
def alive() -> Callable[[int], bool]:
    return process_alive


@pytest.fixture
def pack() -> SimpleNamespace:
    # Pack constants and pure helpers; test modules cannot import
    # conftest by name (no __init__.py in pack folders).
    return SimpleNamespace(
        API_KEY=API_KEY, PROMPT=PROMPT, TASK=TASK, HARNESSES=HARNESSES, VERBS=VERBS, OPENCODE_MODEL=OPENCODE_MODEL, REPO_ROOT=REPO_ROOT,
        FAKE=FAKE, PROMPTS=PROMPTS, GIT=GIT, COMMAND_FIELDS=COMMAND_FIELDS, EXEC_ROLES=EXEC_ROLES, CALL_TIMEOUT_SECONDS=CALL_TIMEOUT_SECONDS,
        SLACK_SECONDS=SLACK_SECONDS, WAIT_SECONDS=WAIT_SECONDS, WORKTREE_PREFIX=WORKTREE_PREFIX, INDEX_PREFIX=INDEX_PREFIX, REDACTED=REDACTED,
        PROMPT_SEPARATOR=PROMPT_SEPARATOR, GIT_GLOBAL_OPTIONS=GIT_GLOBAL_OPTIONS, GIT_LOCATION_VARIABLES=GIT_LOCATION_VARIABLES,
        DIAGNOSTIC_FIELDS=DIAGNOSTIC_FIELDS, DEFAULT_FILES=DEFAULT_FILES, TREE_ID=TREE_ID, GIT_IDENTITY=GIT_IDENTITY,
        sha256_bytes=sha256_bytes, text_digest=text_digest, key_digest=key_digest, private_home=private_home, path_spellings=path_spellings,
        same_path=same_path, inside=inside, fresh_key=fresh_key, fragments=fragments, leaks=leaks, command_line_units=command_line_units,
        launcher_bytes=launcher_bytes, prompt_text=prompt_text, render=render, prompt_fields=prompt_fields, literal_chunks=literal_chunks, longest_literal=longest_literal,
        verdict_json=verdict_json, plan_json=plan_json, round_json=round_json, selection_json=selection_json, role_record=role_record,
        launch_prompt=launch_prompt, launch_session=launch_session, launch_answered=launch_answered, launch_observed=launch_observed,
        launch_workspace=launch_workspace, find_in_order=find_in_order,
    )
