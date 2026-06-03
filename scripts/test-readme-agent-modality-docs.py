from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


class ReadmeAgentModalityDocsVerifier:
    def __init__(self, readme_path: Path) -> None:
        # Stores the README path used by all documentation checks.
        self.readme_path = readme_path

    def verify(self) -> list[CheckResult]:
        # Loads README.md and runs every content check against it.
        try:
            text = self.readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            return [CheckResult("missing README path exits non-zero", False, str(exc))]
        return self.verify_text(text)

    def verify_text(self, text: str) -> list[CheckResult]:
        # Runs all README content checks against supplied text.
        agents_section = self._section_between(text, "## Agents and Modalities", "## Multi-Agent Orchestration")
        context_section = self._section_between(text, "## Context Management", "## Swappable Agent Runtimes")
        results = [
            self._contains(text, "Agents infer execution modality from the configured model name", "automatic wording is model-name based"),
            self._contains(text, 'model_name="gpt-image-1"', "image example uses model-name detection"),
            self._contains(text, 'reply = image_agent.run("A clean product mockup on a white desk")', "image example uses plain string run call"),
            self._omits(text, "Pick a modality explicitly when the request is not ordinary text; plain string prompts default to text.", "stale primary phrase is rejected"),
            self._omits(agents_section, "AgentInput(", "README must not require AgentInput for image execution"),
            self._omits(agents_section, "from vidbyte import ModelModality, VidbyteSDK", "image example omits explicit ModelModality import"),
            self._omits(agents_section, "modality=ModelModality.IMAGE", "image example omits modality keyword"),
            self._contains(context_section, "AgentInput(", "AgentInput remains documented for context"),
        ]
        return results

    def _section_between(self, text: str, start: str, end: str) -> str:
        # Returns the markdown section between two headings, or an empty string when missing.
        start_index = text.find(start)
        if start_index == -1:
            return ""
        end_index = text.find(end, start_index + len(start))
        if end_index == -1:
            return text[start_index:]
        return text[start_index:end_index]

    def _contains(self, text: str, needle: str, name: str) -> CheckResult:
        # Produces a passing result when the expected text is present.
        if self._normalize_whitespace(needle) in self._normalize_whitespace(text):
            return CheckResult(name, True)
        return CheckResult(name, False, f"missing expected text: {needle}")

    def _omits(self, text: str, needle: str, name: str) -> CheckResult:
        # Produces a passing result when stale text is absent.
        if self._normalize_whitespace(needle) not in self._normalize_whitespace(text):
            return CheckResult(name, True)
        return CheckResult(name, False, f"found stale text: {needle}")

    def _normalize_whitespace(self, text: str) -> str:
        # Collapses wrapped markdown text so prose checks are not line-break brittle.
        return " ".join(text.split())


class VerificationScript:
    def __init__(self, repo_root: Path) -> None:
        # Builds the script runner around the repository root.
        self.repo_root = repo_root
        self.verifier = ReadmeAgentModalityDocsVerifier(repo_root / "README.md")

    def run(self) -> int:
        # Runs real README checks plus synthetic edge-case checks and prints a summary.
        results = []
        results.extend(self.verifier.verify())
        results.append(self._empty_readme_content_fails_required_snippet_checks())
        results.append(self._missing_readme_path_exits_non_zero())
        passed_count = sum(1 for result in results if result.passed)
        for result in results:
            label = "PASS" if result.passed else "FAIL"
            suffix = f" - {result.detail}" if result.detail else ""
            print(f"{label}: {result.name}{suffix}")
        print(f"{passed_count}/{len(results)} tests passed")
        return 0 if passed_count == len(results) else 1

    def _empty_readme_content_fails_required_snippet_checks(self) -> CheckResult:
        # Verifies empty README content cannot pass the required documentation checks.
        results = self.verifier.verify_text("")
        if any(not result.passed for result in results):
            return CheckResult("empty README content fails required-snippet checks", True)
        return CheckResult("empty README content fails required-snippet checks", False, "empty content unexpectedly passed")

    def _missing_readme_path_exits_non_zero(self) -> CheckResult:
        # Verifies a missing README path is reported as a failed verification.
        missing_verifier = ReadmeAgentModalityDocsVerifier(self.repo_root / "README.missing.md")
        results = missing_verifier.verify()
        if any(not result.passed for result in results):
            return CheckResult("missing README path exits non-zero", True)
        return CheckResult("missing README path exits non-zero", False, "missing file unexpectedly passed")


if __name__ == "__main__":
    sys.exit(VerificationScript(Path(__file__).resolve().parents[1]).run())
