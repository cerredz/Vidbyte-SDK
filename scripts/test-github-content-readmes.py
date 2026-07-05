from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

PUBLIC_LAYER_READMES = [
    "vidbyte/agents/README.md",
    "vidbyte/context/README.md",
    "vidbyte/evals/README.md",
    "vidbyte/harnesses/README.md",
    "vidbyte/lib/README.md",
    "vidbyte/mcp_server/README.md",
    "vidbyte/middleware/README.md",
    "vidbyte/pipelines/README.md",
    "vidbyte/prompts/README.md",
    "vidbyte/providers/README.md",
    "vidbyte/tools/README.md",
    "vidbyte/trace/README.md",
]

RESERVED_LAYER_READMES = ["vidbyte/shared/README.md"]

ROOT_KEYWORDS = [
    "Vidbyte SDK",
    "agent",
    "context",
    "eval",
    "MCP",
    "middleware",
    "pipeline",
    "prompt",
    "provider",
    "tool",
    "trace",
]


class ReadmeCheck:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.total += 1
        if condition:
            self.passed += 1
            print(f"PASS {name}")
            return
        suffix = f" - {detail}" if detail else ""
        print(f"FAIL {name}{suffix}")

    def finish(self) -> int:
        print(f"{self.passed}/{self.total} tests passed")
        return 0 if self.passed == self.total else 1


def read(path: str) -> str:
    file_path = REPO_ROOT / path
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def main() -> int:
    checks = ReadmeCheck()
    required_files = ["README.md", *PUBLIC_LAYER_READMES, *RESERVED_LAYER_READMES]

    for path in required_files:
        file_path = REPO_ROOT / path
        checks.check(f"{path} exists", file_path.exists(), path)
        checks.check(f"{path} is non-empty", bool(read(path).strip()), path)

    root = read("README.md")
    for keyword in ROOT_KEYWORDS:
        checks.check(f"root README mentions {keyword}", keyword in root, keyword)
    for path in [*PUBLIC_LAYER_READMES, *RESERVED_LAYER_READMES]:
        checks.check(f"root README links {path}", path in root.replace("\\", "/"), path)

    for path in PUBLIC_LAYER_READMES:
        content = read(path)
        checks.check(f"{path} mentions Vidbyte SDK", "Vidbyte SDK" in content, path)
        checks.check(f"{path} has Role In The SDK", "## Role In The SDK" in content, path)
        checks.check(f"{path} has Design Philosophy", "## Design Philosophy" in content, path)
        checks.check(f"{path} has Usage", "## Usage" in content, path)
        checks.check(f"{path} has python fence", "```python" in content, path)

    shared = read("vidbyte/shared/README.md")
    checks.check("shared README is reserved", "reserved namespace" in shared.lower(), "vidbyte/shared/README.md")
    checks.check("shared README states no stable public symbols", "no stable public symbols" in shared.lower(), "vidbyte/shared/README.md")

    return checks.finish()


if __name__ == "__main__":
    sys.exit(main())
