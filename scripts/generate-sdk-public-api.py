"""FILE: scripts/generate-sdk-public-api.py

PURPOSE: Writes contracts/sdk-public-api.json from vidbyte/__init__.py `__all__` and pyproject.toml, or checks that the committed copy is current.
ROLE IN CODEBASE: The only writer of the SDK public-API contract that the vidbyte-cli lint lane (C5) vendors at lint/contracts/sdk-public-api.json. Rule C016 (python lint/run.py --rule C016) runs the same derivation and fails when the committed file is stale.
ARCHITECTURE NOTE: One generator class over lint/core/public_api_contract.py, which reads the tracked sources with ast and tomllib. It never imports vidbyte and never contacts the network.
FUNCTION INVENTORY: PublicApiContractGenerator.run plus one-level helpers for checking, provenance, and writing; main.
COMMON MODIFICATION PATTERNS: Change derivation or schema in lint/core/public_api_contract.py, never here; this script only orchestrates. Commit the vidbyte/__init__.py or version change first, then run this script and commit the regenerated file in the same pull request.
WHAT NOT TO DO: 1. Do not hand-edit the contract. 2. Do not record a commit whose inputs differ from what was read. 3. Do not import vidbyte or contact the network.
KNOWN EDGE CASES: The file is left untouched when the derived data is unchanged, so source.commit keeps naming the commit whose inputs produced it; only formatting drift is rewritten. Writing refuses while any input file differs from HEAD. A missing or malformed committed file is rebuilt from source.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md; contracts/README.md; cerredz/Vidbyte scripts/generate-platform-contract.py (the platform-contract twin).
TESTS: python scripts/generate-sdk-public-api.py --check; C016 enforces freshness in the lint gate; scratch fixtures are recorded in the S4 pull request body.

Usage:
  python scripts/generate-sdk-public-api.py           # regenerate after committing a vidbyte/__init__.py or version change
  python scripts/generate-sdk-public-api.py --check   # exit 1 when the committed contract is stale; write nothing
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lint.core.discovery import SourceCatalog  # noqa: E402 - the repository root must be importable first
from lint.core.public_api_contract import (  # noqa: E402 - the repository root must be importable first
    CONTRACT_REL,
    GENERATOR_REL,
    REPOSITORY,
    ApiContractSource,
    CommittedPublicApi,
    DerivedPublicApi,
    ExportResolutionError,
    PublicApiCodec,
    PublicApiContract,
    PublicApiDeriver,
)


class PublicApiContractGenerator:
    """Derives the public-API contract from one checkout and either verifies or rewrites the committed copy."""

    def __init__(self, root: Path) -> None:
        # Binds the checkout, the committed contract path, and the canonical codec.
        self.root = root
        self.contract_path = root / CONTRACT_REL
        self.codec = PublicApiCodec()

    def run(self, check: bool) -> int:
        # Derive the contract data from source, without importing the package.
        try:
            derived = PublicApiDeriver(SourceCatalog(self.root)).derive()
        except ExportResolutionError as exc:
            return self._report_unresolvable(exc)
        committed = CommittedPublicApi.load(self.contract_path)

        # In --check mode, compare with the committed file and leave both git and the file alone.
        if check:
            return self._check(derived, committed)

        # Keep source.commit when nothing derived changed, so it still names the inputs behind the data.
        if committed.contract is not None and committed.contract.data == derived.data:
            return self._restore_canonical(committed.contract, committed.text)

        # Pin provenance: source.commit must describe every file the derivation read, so those files must match HEAD.
        dirty = self._dirty_inputs(derived.read_paths)
        if dirty:
            return self._report_dirty(dirty)
        contract = PublicApiContract(ApiContractSource(REPOSITORY, self._head_commit(), GENERATOR_REL), derived.data)

        # Write the canonical bytes with LF endings, exactly what C016 and the CLI's vendored copy compare against.
        self.contract_path.parent.mkdir(parents=True, exist_ok=True)
        self.contract_path.write_text(self.codec.render(contract), encoding="utf-8", newline="\n")
        print(f"wrote {CONTRACT_REL} at {contract.source.commit} ({self._summary(derived)})")
        return 0

    @staticmethod
    def _report_unresolvable(exc: ExportResolutionError) -> int:
        # Explains which declaration blocks a static contract; a partial contract would misinform the CLI.
        print(f"SDK public-API contract not generated: {exc.rel}:{exc.line}: {exc.message}")
        print("Declare `__all__` as module-level string lists (literals, `+`, `*name`, `+=`, `.extend`, `.append`) and a static [project].version; see C016's diagnostic.")
        return 1

    def _check(self, derived: DerivedPublicApi, committed: CommittedPublicApi) -> int:
        # A missing or schema-invalid file, any data drift, or non-canonical bytes all fail the check.
        if committed.contract is None:
            print(f"{CONTRACT_REL}:{committed.problem_line}: {committed.problem_field}: {committed.problem}")
            print(f"Run: python {GENERATOR_REL}")
            return 1
        old, new = committed.contract.data, derived.data
        drift = [f"exports added: {', '.join(sorted(set(new.exports) - set(old.exports)))}" if set(new.exports) - set(old.exports) else "", f"exports removed: {', '.join(sorted(set(old.exports) - set(new.exports)))}" if set(old.exports) - set(new.exports) else "", f"version {old.version!r} -> {new.version!r}" if old.version != new.version else "", f"distribution {old.distribution!r} -> {new.distribution!r}" if old.distribution != new.distribution else ""]
        drift = [line for line in drift if line]
        for line in drift:
            print(f"{CONTRACT_REL} is stale: {line}")
        canonical = committed.text == self.codec.render(committed.contract)
        if not canonical:
            print(f"{CONTRACT_REL} is not byte-identical to generator output; regenerate instead of editing it.")
        if drift or not canonical:
            print(f"Run: python {GENERATOR_REL} (after committing the source change).")
            return 1
        print(f"{CONTRACT_REL} is current at {committed.contract.source.commit} ({self._summary(derived)}).")
        return 0

    def _restore_canonical(self, contract: PublicApiContract, text: str) -> int:
        # Rewrites only formatting drift, keeping the recorded source.commit because the data did not change.
        canonical = self.codec.render(contract)
        if text == canonical:
            print(f"{CONTRACT_REL} is already current at {contract.source.commit}; nothing written.")
            return 0
        self.contract_path.write_text(canonical, encoding="utf-8", newline="\n")
        print(f"restored canonical formatting of {CONTRACT_REL}; data and source.commit unchanged.")
        return 0

    def _dirty_inputs(self, paths: tuple[str, ...]) -> list[str]:
        # Lists input files whose working-tree content differs from HEAD, including untracked ones.
        result = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=self.root, capture_output=True, text=True, check=True)
        return [line[3:] for line in result.stdout.splitlines() if line.strip()]

    @staticmethod
    def _report_dirty(dirty: list[str]) -> int:
        # Refuses to stamp a commit that does not contain the inputs that were read.
        print("SDK public-API contract not written: these input files have uncommitted changes:")
        for path in dirty:
            print(f"  {path}")
        print("Commit the source change first, then rerun, so source.commit names the commit whose inputs were read.")
        return 1

    def _head_commit(self) -> str:
        # Returns the full SHA of the checked-out commit.
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    @staticmethod
    def _summary(derived: DerivedPublicApi) -> str:
        # One-line description of the derived surface for the console.
        return f"{derived.data.distribution} {derived.data.version}, {len(derived.data.exports)} exports"


def main(argv: list[str] | None = None) -> int:
    # Parses the one flag and delegates to the generator for this checkout.
    parser = argparse.ArgumentParser(prog=f"python {GENERATOR_REL}", description=f"Write or check {CONTRACT_REL} from vidbyte/__init__.py and pyproject.toml, without importing vidbyte.")
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed contract is stale; write nothing")
    args = parser.parse_args(argv)
    return PublicApiContractGenerator(REPO_ROOT).run(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
