# Release 0.3.1: harness thread functions from `vidbyte`

`vidbyte-sdk` 0.3.0, the latest release on PyPI, predates the harness thread functions in `vidbyte.harnesses.native` (#1036). vidbyte-cli is building `vidbyte-cli resolve`, a scheduled GitHub Actions job that resolves merge conflicts on a user's pull requests by running opencode, Grok Build or Muse Code threads through those functions. Two CLI lint rules block it today. C028 lets the CLI import only names listed in its vendored copy of `contracts/sdk-public-api.json`, which is `vidbyte.__all__`, and `vidbyte` did not re-export the thread functions. C029 requires every `vidbyte-sdk` pin to admit the contract's `version`, so the contract needs a released version that contains those names. This release does both. It exports from `vidbyte` every name in `vidbyte.harnesses.native.__all__`: the nine `run_`, `continue_` and `fork_` functions for Grok, opencode and Muse, `NativeThreadResult`, `NativeThreadError`, `GrokThreadConfig`, `OpencodeThreadConfig`, `MuseThreadConfig`, `GrokPermissionMode`, `GrokReasoningEffort` and `MuseReasoningEffort`. It then publishes everything on `main` since `v0.3.0`: 87 commits, of which 6 are features and 81 are fixes.

The nine functions load on first use, through a lazy-export mapping and a module `__getattr__` in `vidbyte/__init__.py`. A plain `import vidbyte` therefore still never imports `vidbyte.harnesses.native`, which keeps harness thread spec INV-23. The records, enums and error import from `vidbyte.lib` as usual. Every root name is the same object as the one in `vidbyte.harnesses.native`. `tests/features/root_native_thread_exports/` pins this, and it reads the native `__all__`, so a later harness pull request that adds a name there must also add it to the root and the contract.

What 0.3.1 adds, from `git log v0.3.0..HEAD`:

- **Harness thread functions (#1036), the headline.** `run_`, `continue_` and `fork_` for Grok Build, opencode and Muse Code. Each drives the vendor's installed CLI headless once, with the caller's API key, and returns `NativeThreadResult(harness, thread_id, text, text_truncated)` or raises one `NativeThreadError` with a closed failure code. This release exports them from `vidbyte`, which adds 17 root exports.
- **Codex host (#1055).** `CodexHost`, with agent tools, thread helpers and skill functions, in `vidbyte.harnesses.native.codex`. It needs the `codex` extra and is not a root export.
- **InfiniteMemoryAgent (#1084).** A delegating agent with a guarded file-workspace memory. This adds `InfiniteMemoryAgent`, `InfiniteMemoryAgentSettings`, `InfiniteWorkspaceSettings` and `InfiniteMemoryPreset`.
- **Working Principles preset (#1095).** An opt-in system-prompt preset that reaches every agent a run starts. This adds `SystemPromptPreset`.
- **Provider keys (#1027).** Agents take `vidbyte_api_key` and a list of `api_keys`, and text calls can relay your provider key through the Vidbyte gateway. **This is a breaking change:** `BaseAgent(api_key=...)`, `Agent(api_key=...)` and `BaseAgent.restore(api_key=...)` now raise `TypeError`. Pass `api_keys=[...]` instead.
- **Jev read-only intent (#1005).** Assessment-only runs are limited to SAFE and READ tools.
- **Fixes.** 81 fixes. Most are in compaction (21), algorithms (12), runtime (9), codex (7), multi-agent (6) and context (5).

The version is 0.3.1 because the owner chose it. Two facts would also support 0.4.0. The 0.3.0 note took a minor version for added root exports, and #1027 removes the `api_key=` keyword. A consumer pinned to `>=0.3.0,<0.4` receives both changes with this release. vidbyte-cli does not pass `api_key=` to an SDK agent.

Every literal that names the version moves together, as in the 0.2.0, 0.2.1 and 0.3.0 releases: `pyproject.toml`, `vidbyte/__init__.py`, the CLI fallback, the MCP server default, the MCP `clientInfo`, `README.md`, `llms.txt`, the bug template, and the regenerated `contracts/sdk-public-api.json`. The contract now lists 661 exports, against 639 at `v0.3.0`: 22 added and none removed. There are no dependency changes, and the `codex` extra keeps `openai-codex>=0.162.1,<0.163.0`.

To release after merge:

1. Push the tag `v0.3.1` on the merge commit.
2. Dispatch `publish.yml` on that tag. The workflow validates the tag, reruns CI, and waits for approval on the `pypi` environment before it uploads.
3. vidbyte-cli then vendors the new contract and raises its floor to `vidbyte-sdk[codex]>=0.3.1,<0.4`.
