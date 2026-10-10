"""FILE: lint/rules/c015_package_data_coverage.py

PURPOSE: Detect a non-Python file inside the vidbyte import package that the built wheel omits, a folder README the wheel ships, or a package-data pattern that ships nothing.
ROLE IN CODEBASE: Enforces C015 so the installed package and the source checkout hold the same non-Python files, which the 0.1.0 launch-gate defect (#266) showed is what `import vidbyte` depends on after installation.
ARCHITECTURE NOTE: Static emulation of setuptools build_py over tracked files: packages come from [tool.setuptools.packages.find] (namespace packages by default, as setuptools uses for pyproject `find`), each package-data pattern is globbed relative to its package folder the way glob(recursive=True) does, exclude-package-data uses fnmatch on the whole path, and "" or "*" keys apply to every package. Nothing is built or imported.
FUNCTION INVENTORY: PackagingConfig reads and validates pyproject.toml; PackageFinder discovers packages; DataGlob matches one pattern; ShippedFiles computes the wheel's data files; PackageDataAnalyzer coordinates; PackageDataCoverageRule reports and explains.
COMMON MODIFICATION PATTERNS: When setuptools changes how build_py globs package data, change DataGlob in the same edit and repeat the scratch wheel comparison recorded in the S3 pull request; when the project adopts MANIFEST.in or setuptools-scm, model it here before removing the fail-closed guard.
WHAT NOT TO DO: Do not import vidbyte or setuptools, build a wheel during lint, treat README.md files as runtime assets, or guess when the packaging configuration uses a feature this emulation does not model.
KNOWN EDGE CASES: Matching is case-sensitive, like the Linux builders. A `*` never matches a name that starts with a dot. A tracked MANIFEST.in, a setuptools-scm build requirement, an explicit package list, or a package-dir mapping fails closed (ERRORED) because each changes which files ship.
RELATED DOCS: docs/design/lint-sdk-jev-packaging-async.md; CONTRIBUTING.md (runtime assets); commit d575a3ff (#266 SDK launch gate); scripts/run_ci.py (_inspect_wheel).
TESTS: python lint/run.py --rule C015; fixture, mutation, and real-wheel comparison results are recorded in the S3 pull request body.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

PYPROJECT = "pyproject.toml"
MANIFEST = "MANIFEST.in"
PACKAGE_ROOT = "vidbyte/"
README = "README.md"
DATA_TABLE = "[tool.setuptools.package-data]"
EXCLUDE_TABLE = "[tool.setuptools.exclude-package-data]"
_ALL_PACKAGES = ("", "*")
_UNSHIPPED = "asset-not-shipped"
_README = "readme-shipped"
_DEAD = "pattern-ships-nothing"
_KINDS = (_UNSHIPPED, _README, _DEAD)
_SCM_REQUIREMENT = "setuptools-scm"


@dataclass(frozen=True, slots=True)
class DataPattern:
    """One package-data or exclude-package-data pattern with the pyproject line that declares it."""

    package: str
    pattern: str
    line: int

    def __post_init__(self) -> None:
        # The pattern is quoted in every message and must stay inside its package folder.
        if not self.pattern or self.line < 1:
            raise ValueError(f"DataPattern needs a pattern and a positive line, got {self.pattern!r} at {self.line}.")
        if self.pattern.startswith("/") or ".." in PurePosixPath(self.pattern).parts or "\\" in self.pattern:
            raise RuntimeError(f"C015 does not model the package-data pattern {self.pattern!r} for {self.package!r} at {PYPROJECT}:{self.line}: patterns must be relative, use forward slashes, and stay inside the package folder.")


@dataclass(frozen=True, slots=True)
class PackagingGap:
    """One mismatch between the import package's non-Python files and what the wheel ships."""

    kind: str
    rel: str
    line: int
    symbol: str
    facts: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        # The kind selects the repair, and the anchor must be a real file and line.
        if self.kind not in _KINDS:
            raise ValueError(f"PackagingGap.kind must be one of {_KINDS}, got {self.kind!r}.")
        if not self.rel or self.line < 1 or not self.symbol:
            raise ValueError(f"PackagingGap needs a path, a positive line, and a symbol, got {self.rel!r}/{self.line}/{self.symbol!r}.")


class PackagingConfig:
    """Reads the setuptools packaging configuration from pyproject.toml and the lines that declare it."""

    def __init__(self, text: str, tracked: tuple[str, ...]) -> None:
        # Parses the file once and refuses configurations whose shipped files this emulation cannot predict.
        self.lines = text.splitlines()
        try:
            self.data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise RuntimeError(f"C015 cannot parse {PYPROJECT}: {exc}. Fix the TOML so package data can be checked.") from exc
        self.setuptools = self.data.get("tool", {}).get("setuptools", {})
        self._require_supported(tracked)

    def _require_supported(self, tracked: tuple[str, ...]) -> None:
        # Each of these features ships files that the package-data patterns alone do not describe.
        requires = self.data.get("build-system", {}).get("requires", [])
        if MANIFEST in tracked:
            raise RuntimeError(f"C015 models shipped files from {PYPROJECT} patterns only, but {MANIFEST} is tracked and can add files to the wheel through include-package-data; extend the rule to read it.")
        if any(str(item).replace("_", "-").lower().startswith(_SCM_REQUIREMENT) for item in requires):
            raise RuntimeError("C015 found setuptools-scm in build-system.requires; it makes include-package-data ship every tracked file, so extend the rule before relying on it.")
        if ("packages" in self.setuptools and not isinstance(self.setuptools.get("packages"), dict)) or "package-dir" in self.setuptools:
            raise RuntimeError(f"C015 supports package discovery only through [tool.setuptools.packages.find] with no package-dir mapping; extend the rule for the configuration in {PYPROJECT}.")

    def find_options(self) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], bool]:
        # where, include, exclude, and namespaces of [tool.setuptools.packages.find], with setuptools' pyproject defaults.
        packages = self.setuptools.get("packages", {})
        find = packages.get("find") if isinstance(packages, dict) else None
        if not isinstance(find, dict):
            raise RuntimeError(f"C015 expects [tool.setuptools.packages.find] in {PYPROJECT} to discover packages; extend the rule if discovery changed.")
        return tuple(find.get("where", ["."])), tuple(find.get("include", ["*"])), tuple(find.get("exclude", [])), bool(find.get("namespaces", True))

    def patterns(self, table: str) -> tuple[DataPattern, ...]:
        # Every (package, pattern) pair of one table, located on the line that declares it.
        key = "package-data" if table == DATA_TABLE else "exclude-package-data"
        spec = self.setuptools.get(key, {})
        if not isinstance(spec, dict) or any(not isinstance(value, list) for value in spec.values()):
            raise RuntimeError(f"C015 expects {table} in {PYPROJECT} to map package names to lists of patterns.")
        return tuple(DataPattern(package=package, pattern=str(pattern), line=self._line(table, package, str(pattern))) for package, values in spec.items() for pattern in values)

    def table_line(self, table: str) -> int:
        # The 1-based line of a table header, or the first line when the table is absent.
        return next((index for index, text in enumerate(self.lines, 1) if text.strip() == table), 1)

    def _line(self, table: str, package: str, pattern: str) -> int:
        # The line quoting the pattern after its package key inside the table, falling back to the key and then the header.
        start = self.table_line(table)
        end = next((index for index, text in enumerate(self.lines, 1) if index > start and text.strip().startswith("[")), len(self.lines) + 1)
        key_line = next((index for index in range(start + 1, end) if self.lines[index - 1].strip().startswith((f'"{package}"', f"{package} ", f"{package}="))), start)
        return next((index for index in range(key_line, end) if f'"{pattern}"' in self.lines[index - 1] or f"'{pattern}'" in self.lines[index - 1]), key_line)


class PackageFinder:
    """Discovers packages the way setuptools' find_namespace_packages (or find_packages) walks a tracked tree."""

    @staticmethod
    def packages(tracked: tuple[str, ...], options: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], bool]) -> dict[str, str]:
        # Dotted package name -> package folder, for every tracked folder setuptools would treat as an included package.
        where, include, exclude, namespaces = options
        found: dict[str, str] = {}
        for base in where:
            prefix = "" if base in {".", ""} else f"{base.strip('/')}/"
            folders = {str(PurePosixPath(rel).parent) for rel in tracked if rel.startswith(prefix)}
            for folder in sorted(item for item in folders if item not in {".", ""}):
                parts = PurePosixPath(folder[len(prefix):]).parts
                walked = all("." not in part for part in parts)
                regular = all(f"{prefix}{'/'.join(parts[:depth])}/__init__.py" in tracked for depth in range(1, len(parts) + 1))
                name = ".".join(parts)
                if parts and walked and (namespaces or regular) and any(fnmatchcase(name, item) for item in include) and not any(fnmatchcase(name, item) for item in exclude):
                    found[name] = folder
        return found


class DataGlob:
    """Matches one package-data pattern against a path relative to its package folder, as glob(recursive=True) does."""

    @classmethod
    def matches(cls, pattern: str, relative: str) -> bool:
        # Segment by segment: `*` stays inside one folder name, `**` spans folders, and hidden names need a dot pattern.
        return cls._match(PurePosixPath(pattern).parts, PurePosixPath(relative).parts)

    @classmethod
    def _match(cls, pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
        # Recursive segment matcher; a bare `**` matches zero or more non-hidden folders.
        if not pattern:
            return not path
        head, rest = pattern[0], pattern[1:]
        if head == "**":
            return any(cls._match(rest, path[skip:]) for skip in range(len(path) + 1) if not any(part.startswith(".") for part in path[:skip]))
        if not path or (path[0].startswith(".") and not head.startswith(".")):
            return False
        return fnmatchcase(path[0], head) and cls._match(rest, path[1:])


class ShippedFiles:
    """Computes which tracked files build_py would copy into the wheel as package data, package by package."""

    def __init__(self, tracked: tuple[str, ...], packages: dict[str, str], includes: tuple[DataPattern, ...], excludes: tuple[DataPattern, ...]) -> None:
        # For each package, glob its own and the all-package patterns over its folder, then drop that package's whole-path exclusions.
        self.matches: dict[DataPattern, set[str]] = {pattern: set() for pattern in includes}
        self.excluded: dict[str, DataPattern] = {}
        self._shipped: dict[str, DataPattern] = {}
        for package, folder in packages.items():
            inside = [rel for rel in tracked if rel.startswith(f"{folder}/")]
            removals = [item for item in excludes if item.package in _ALL_PACKAGES or item.package == package]
            for pattern in (item for item in includes if item.package in _ALL_PACKAGES or item.package == package):
                hits = {rel for rel in inside if DataGlob.matches(pattern.pattern, rel[len(folder) + 1:])}
                self.matches[pattern].update(hits)
                for rel in sorted(hits):
                    removal = next((item for item in removals if fnmatchcase(rel, f"{folder}/{item.pattern}")), None)
                    if removal is None:
                        self._shipped.setdefault(rel, pattern)
                    else:
                        self.excluded.setdefault(rel, removal)

    def shipped(self) -> dict[str, DataPattern]:
        # Each shipped file with the first pattern that ships it; a file one package excludes can still ship through another.
        return dict(self._shipped)


class PackageDataAnalyzer:
    """Compares the import package's tracked non-Python files with the files the wheel would ship."""

    def analyze(self, config: PackagingConfig, tracked: tuple[str, ...]) -> list[PackagingGap]:
        # Discover packages and compute the shipped set exactly as setuptools would from these patterns.
        packages = PackageFinder.packages(tracked, config.find_options())
        includes = config.patterns(DATA_TABLE)
        excludes = config.patterns(EXCLUDE_TABLE)
        files = ShippedFiles(tracked, packages, includes, excludes)
        shipped = files.shipped()

        # Every non-Python file inside the import package is either a README or must ship.
        gaps: list[PackagingGap] = []
        for rel in (item for item in tracked if item.startswith(PACKAGE_ROOT) and not item.endswith(".py")):
            if PurePosixPath(rel).name == README:
                if rel in shipped:
                    pattern = shipped[rel]
                    others = [item for item in files.matches[pattern] if item != rel and PurePosixPath(item).name != README]
                    gaps.append(PackagingGap(_README, PYPROJECT, pattern.line, rel, (("readme", rel), ("package", pattern.package), ("pattern", pattern.pattern), ("others", str(len(others))))))
            elif rel not in shipped:
                gaps.append(self._unshipped(rel, packages, includes, files, config))

        # Every pattern ships at least one file, or it names a package that does not exist.
        for pattern, rels in files.matches.items():
            if not rels:
                reason = "names no discovered package" if pattern.package not in packages and pattern.package not in _ALL_PACKAGES else "matches no tracked file"
                gaps.append(PackagingGap(_DEAD, PYPROJECT, pattern.line, f"{pattern.package or '*'}: {pattern.pattern}", (("package", pattern.package), ("pattern", pattern.pattern), ("reason", reason))))
        return gaps

    @staticmethod
    def _unshipped(rel: str, packages: dict[str, str], includes: tuple[DataPattern, ...], files: ShippedFiles, config: PackagingConfig) -> PackagingGap:
        # Names the deepest package that holds the file and what its key, if any, currently ships.
        owners = sorted((name for name, folder in packages.items() if rel.startswith(f"{folder}/")), key=lambda name: name.count("."))
        owner = owners[-1] if owners else ""
        keyed = [name for name in reversed(owners) if any(item.package == name for item in includes)]
        key = keyed[0] if keyed else ""
        patterns = ", ".join(f"`{item.pattern}`" for item in includes if item.package == key)
        exclusion = files.excluded.get(rel)
        anchor = next((item.line for item in includes if item.package == key), config.table_line(DATA_TABLE))
        facts = (("owner", owner), ("key", key), ("patterns", patterns), ("excluded_by", "" if exclusion is None else exclusion.pattern), ("table_line", str(anchor)), ("folder", str(PurePosixPath(rel).parent)), ("suffix", PurePosixPath(rel).suffix or PurePosixPath(rel).name))
        return PackagingGap(_UNSHIPPED, rel, 1, rel, facts)


class PackageDataCoverageRule(Rule):
    """Requires the wheel to ship every non-README non-Python file in the vidbyte package, and nothing else."""

    id = "C015"
    name = "package-data-coverage"
    severity = "blocking"
    summary = "Every tracked non-Python file inside the vidbyte import package, other than a folder README.md, is shipped by a [tool.setuptools.package-data] pattern in pyproject.toml (as setuptools would glob it), no README.md is shipped, and every package-data pattern ships at least one tracked file. A file the wheel omits loads from a source checkout but is missing after `pip install`."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Read the packaging configuration, then report each mismatch at the file or pattern that needs the edit.
        tracked = catalog.tracked_paths()
        if PYPROJECT not in tracked:
            raise RuntimeError(f"C015 requires the tracked {PYPROJECT}; restore it so package data can be checked.")
        path = catalog.root / PYPROJECT
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"C015 could not read {path}: {exc}.") from exc
        config = PackagingConfig(text, tracked)
        gaps = PackageDataAnalyzer().analyze(config, tracked)
        lines = text.splitlines()
        return [self._finding(gap, lines) for gap in sorted(gaps, key=lambda item: (item.rel, item.line, item.symbol))]

    def explain(self, finding: Finding) -> Diagnostic:
        # Each kind has its own consequence; all share the build-and-install verification.
        kind = finding.extra["kind"]
        if kind == _UNSHIPPED:
            return self._explain_unshipped(finding)
        if kind == _README:
            return self._explain_readme(finding)
        return self._explain_dead(finding)

    @staticmethod
    def _finding(gap: PackagingGap, lines: list[str]) -> Finding:
        # Stores every quoted fact, so explain() never re-reads source.
        source_line = lines[gap.line - 1] if gap.rel == PYPROJECT and 0 < gap.line <= len(lines) else ""
        return Finding(rule_id=PackageDataCoverageRule.id, rel_path=gap.rel, line=gap.line, source_line=source_line, symbol=gap.symbol, extra={"kind": gap.kind, **dict(gap.facts)})

    def _explain_unshipped(self, finding: Finding) -> Diagnostic:
        # An unshipped asset works in the checkout and is missing after installation.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.rel_path} is a tracked non-Python file inside the vidbyte import package, but no [tool.setuptools.package-data] pattern in {PYPROJECT} ships it, so the built wheel omits it. {self._owner_sentence(extra)}",
            why_blocked="CONTRIBUTING.md requires it: \"When adding non-Python runtime assets, confirm that the built wheel contains them and that the installed package can load them outside the source checkout.\" The 0.1.0 launch gate (commit d575a3ff, #266) found exactly this defect: \"error_correction.json references error_correction_auditor.md, and the Markdown file is absent from the wheel\", so `import vidbyte` failed after installation while every source-checkout test passed. scripts/run_ci.py inspects the built wheel for that one asset only (REQUIRED_PROMPT_ASSET), so every other file inside the package ships only if a pattern matches it.",
            how_to_fix="\n".join((
                f"1. If the installed package needs the file (code, a prompt family, or a skill loads it, or the package documents it as shipped), add the smallest pattern that matches it to [tool.setuptools.package-data] in {PYPROJECT} (line {extra['table_line']}): {self._pattern_hint(extra)}. Do not use a catch-all such as `**/*.md`, which would also ship README files.",
                f"2. If the file is not a runtime asset (a document for people or for another repository surface), move it out of the vidbyte/ import package, for example to the repository-level skills/ or docs/ folder, and update the links that point at {finding.rel_path}.",
                "3. Build the wheel with `python -m build --wheel` and confirm it lists the file (`python -m zipfile -l dist/<wheel>.whl`), then install it into a fresh virtual environment and load the file outside the checkout, as CONTRIBUTING.md asks.",
                "4. Run `python scripts/run_ci.py --stage package` before treating the change as complete.",
            )),
            correct_examples=(
                f"{PYPROJECT} `\"vidbyte.prompts.prompts\" = [\"*.json\", \"*.md\", \"*/*.json\", \"*/*.md\"]` - #266 added root `*.md` so error_correction_auditor.md ships, keeping the patterns scoped to the prompt families.",
                f"{PYPROJECT} `\"vidbyte.paradigms.context_minimal_fanout\"` - `prompts/*.md`, `skills/*/*.md`, and `skills/skills.json` each name one asset folder.",
                "scripts/run_ci.py CiPipeline._inspect_wheel - checks the built wheel, not the source tree, for a required asset.",
            ),
            will_not_work=(
                "Adding a recursive catch-all such as `\"vidbyte\" = [\"**/*\"]`: it ships every README and stray file, the launch gate chose \"the smallest correct package-data rule rather than broadly include every Markdown file\", and C015 then reports each shipped README.",
                "Relying on include-package-data alone: without a MANIFEST.in or setuptools-scm it adds nothing the patterns do not already ship, and adding either makes C015 fail closed until it models it.",
                "Raising C015's baseline in lint/baseline.json: each finding is a file that the source checkout has and the installed package does not.",
            ),
            verify=f"{self.verify_command()} && python scripts/run_ci.py --stage package",
        )

    def _explain_readme(self, finding: Finding) -> Diagnostic:
        # A shipped README means a pattern is broader than the runtime assets it was written for.
        extra = finding.extra
        only = extra["others"] == "0"
        scope = "It matches no other non-README file, so the pattern now exists only to ship this README." if only else f"It also ships {extra['others']} runtime file(s), so the pattern is broader than those assets."
        return Diagnostic(
            what_happened=f"{finding.location()}: the package-data pattern `{extra['pattern']}` under `\"{extra['package']}\"` ships {extra['readme']} into the wheel. {scope}",
            why_blocked="The launch gate that set the packaging policy (commit d575a3ff, #266) states \"Source files that are not runtime assets, including general component README files, remain outside the wheel unless separately justified\", and chose \"the smallest correct package-data rule rather than broadly include every Markdown file\". A README in the wheel is a folder guide for contributors that no installed code reads; its presence means the pattern is broader than the assets it was written for, or those assets moved and the pattern was left behind.",
            how_to_fix="\n".join((
                f"1. {'Delete' if only else 'Narrow'} the pattern `{extra['pattern']}` under `\"{extra['package']}\"` in {PYPROJECT}{'' if only else ' so it names the asset folder or file type it is meant for and no longer matches README.md'}.",
                f"2. If the README genuinely must ship (installed code reads it), say so in a comment above the pattern and match it by its full name instead of a broad `*.md`; otherwise, if narrowing is impractical, add `\"{extra['package']}\" = [\"README.md\"]` under [tool.setuptools.exclude-package-data].",
                "3. Build the wheel with `python -m build --wheel` and confirm the README is gone and every runtime asset is still listed.",
            )),
            correct_examples=(
                f"{PYPROJECT} `\"vidbyte.prompts.prompts\"` - its patterns match prompt JSON and Markdown in the package and its families, and no README.md is tracked there.",
                f"{PYPROJECT} `\"vidbyte.paradigms.context_minimal_fanout\"` - `prompts/*.md` and `skills/*/*.md` ship the paradigm's assets without its folder README.",
            ),
            will_not_work=(
                "Renaming the README so the pattern no longer matches it: the pattern still ships nothing it was written for, and the folder loses its guide.",
                "Raising C015's baseline in lint/baseline.json: each finding is a contributor document inside the installed package and a pattern that no longer describes its assets.",
            ),
            verify=f"{self.verify_command()} && python scripts/run_ci.py --stage package",
        )

    def _explain_dead(self, finding: Finding) -> Diagnostic:
        # A pattern that ships nothing hides a moved or deleted asset.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()}: the package-data pattern `{extra['pattern']}` under `\"{extra['package'] or '*'}\"` {extra['reason']}, so it ships nothing.",
            why_blocked="A dead pattern means the assets it was written for moved, were renamed, or were deleted without the packaging table following them; the moved files may now be unshipped, and a later file that happens to match the stale pattern ships without anyone deciding it should. The launch gate (commit d575a3ff, #266) made the installed wheel the acceptance surface and chose the smallest correct pattern per asset, which a pattern matching nothing no longer is.",
            how_to_fix="\n".join((
                f"1. Find where the assets `{extra['pattern']}` was meant for live now (`git log --follow` on the old path) and point the pattern at them, or delete the pattern if they are gone.",
                f"2. If the key `\"{extra['package']}\"` names a package that no longer exists, move its patterns under the package that now holds the files.",
                "3. Build the wheel with `python -m build --wheel` and confirm the intended assets are listed.",
            )),
            correct_examples=(
                f"{PYPROJECT} `\"vidbyte.paradigms.context_minimal_fanout\"` - `prompts/*.md` names the folder that holds the paradigm's four prompt files, and each skills pattern names one skills file or folder.",
                f"{PYPROJECT} `\"vidbyte.prompts.prompts\"` - every pattern there matches tracked prompt files.",
            ),
            will_not_work=(
                "Keeping the pattern \"in case\" assets return: it silently ships whatever file next matches it.",
                "Raising C015's baseline in lint/baseline.json: each finding is a packaging rule that describes no file.",
            ),
            verify=f"{self.verify_command()} && python scripts/run_ci.py --stage package",
        )

    @staticmethod
    def _owner_sentence(extra: dict[str, str]) -> str:
        # Explains which package holds the file and why its patterns miss it.
        if extra["excluded_by"]:
            return f"The exclude-package-data pattern `{extra['excluded_by']}` removes it."
        if not extra["owner"]:
            return "Its folder is not inside any package that [tool.setuptools.packages.find] discovers."
        if not extra["key"]:
            return f"Its package `{extra['owner']}` has no package-data key, and no enclosing package's patterns reach it."
        return f"Its enclosing package `{extra['key']}` ships {extra['patterns']}, and none of those patterns matches it."

    @staticmethod
    def _pattern_hint(extra: dict[str, str]) -> str:
        # A concrete key and folder-scoped pattern for the file.
        package = extra["owner"] or "<package>"
        return f"for example `\"{package}\" = [\"*{extra['suffix']}\"]` when every {extra['suffix']} file in {extra['folder']} is an asset"


RULE = PackageDataCoverageRule()
