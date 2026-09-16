# Design Doc — SourceContext / SourceTool (PR #431 replacement)

## 1. Overview

This feature gives an agent two explicit integration surfaces:

- `SourceContext(source).load()` loads one external resource into bounded
  `DocumentContextItem` objects.
- `SourceTool(source).build()` returns repository-scoped `BaseTool` objects.

GitHub is the first provider. When the GitHub CLI (`gh`) is available, the
provider plans an allowlisted command for each operation and sends it through
one central `CliRunner.run()` boundary. The caller supplies the GitHub token
once in validated configuration; the runner places it in `GH_TOKEN` in the
child process environment. The token is never a command argument, URL,
exception message, or log value. If `gh` is unavailable, the same provider
falls back to the existing typed HTTP transport.

The important boundary is deliberate: callers provide credentials and a
resource, while provider code owns command names, routes, scope, and output
parsing. This is a CLI-backed provider, not a free-form shell or URL proxy.

## 2. Goals / Non-Goals

Goals:

- Keep `SourceContext` and `SourceTool` as the only public entry points.
- Validate source configuration and GitHub client configuration with frozen,
  slotted dataclasses.
- Route GitHub reads through `gh` when present, with deterministic REST
  fallback for SDK, CI, and server environments without the CLI installed.
- Centralize subprocess safety in one reusable `CliRunner.run()` method:
  `shell=False`, bounded stdout/stderr, timeout, sanitized environment, and
  typed failure categories.
- Generate every GitHub command and HTTP URL from validated provider scope.
  Model-supplied paths and search strings cannot select a host, owner, repo,
  executable, or arbitrary command.
- Preserve the four explicit pull-request context sections: description,
  diff, reviews, and discussion.
- Keep tool output and context within caller-provided byte/token budgets and
  mark truncation explicitly.
- Make provider differences local so Slack and Google Drive can later have
  different context shapes and client capabilities.

Non-goals:

- No arbitrary CLI passthrough, arbitrary URL/route input, shell execution, or
  command templates supplied by callers.
- No provider registry or shared provider protocol. A closed factory switch is
  sufficient while GitHub is the only provider; provider clients need not
  expose the same context structure.
- No connection store, refresh-token flow, multi-resource batching, report
  aggregation, or permission-policy return value.
- No changes to `Agent`, `BaseAgent`, `vidbyte/sources/`, or the tool execution
  pipeline.

## 3. Background

PR #429 introduced a larger source-access abstraction without a concrete
provider. PR #431 is the smaller rework, but its GitHub client used direct
REST calls, a public provider protocol, module-level helpers, and a single
large tool module. Review feedback asks for reusable budget/helper code in
`vidbyte/lib`, strict input validation, class-bound helpers, a provider switch,
separate source subfolders, and one file per GitHub tool.

The existing `HttpTransport` already provides bounded async HTTP reads. The
new CLI helper follows the same boundary principles for a native executable.
The two transports share provider-level response normalization; transport
selection is an implementation detail of `GitHubClient`.

## 4. Requirements

1. `SourceContext(source: Mapping, *, max_tokens: int).load()` returns a list
   of four GitHub PR context items or raises a source access error.
2. `SourceTool(source: Mapping, *, max_output_bytes: int).build()` returns
   three repository-scoped tools in stable order.
3. Public source keys are `provider`, `api_key`, and `resource`; unknown keys,
   empty credentials, invalid GitHub token prefixes, invalid URLs, and invalid
   budgets fail at construction.
4. Every GitHub operation uses a provider-authored command plan or URL. The
   caller cannot provide an executable, command, host, route, owner, or repo.
5. CLI authentication uses `GH_TOKEN` only in the child environment. It is
   removed from inherited environment values and never included in argv or
   safe error details.
6. Native failures distinguish unavailable CLI from an attempted CLI request.
   Only unavailable CLI falls back to REST; auth, scope, rate-limit, malformed
   output, timeout, and command failures surface as source access failures.
7. HTTP and CLI responses map authentication, rate-limit, missing-resource,
   and transport failures to the existing source error hierarchy without
   returning an empty success result.
8. Repository tools reject absolute paths, path traversal, URLs, oversized
   paths/queries, and search qualifiers that widen repository scope before any
   transport request is made.
9. No credential or provider response body appears in exception messages,
   diagnostic fields, logs, or report strings.
10. The source verification script, source CI stage, package CI stage, full
    CI, and semgrep typed-mapping policy pass without baseline weakening.

## 5. High-Level Design

```text
SourceContext / SourceTool
          |
      SourceConfig  ---->  SourceProviderFactory (match provider)
                                     |
                              GitHubClient
                              /          \\
                 GitHub command plan    REST request builder
                          |                    |
                    CliRunner.run()       HttpTransport
                          \\                    /
                           response normalizer
```

`SourceContext` and `SourceTool` live in separate subpackages. The factory is
class-bound and uses an explicit `match`, so a future Slack or Drive client
can own a different API without implementing a false common protocol. GitHub
tools live below `vidbyte/tools/integrations/github/`, one tool class per
module.

## 6. Detailed Design

### 6.1 Validated configuration

`vidbyte/lib/dataclasses/integrations.py` owns `SourceConfig` and
`GitHubClientConfig`. Both are `@dataclass(frozen=True, slots=True)`.

`SourceConfig` validates provider, API key presence, control characters,
resource shape, repository scope, and pull-request number. `GitHubClientConfig`
validates GitHub token prefixes, timeout bounds, an `HttpTransport` instance,
and a `CliRunner` instance when one is supplied. The public adapters only
coerce mappings and budgets; they do not duplicate configuration rules.

### 6.2 Central CLI runner

`vidbyte/lib/cli.py` contains:

- `CliRequest`: immutable executable, argument tuple, secret token, timeout,
  and output ceiling.
- `CliResult`: immutable stdout, stderr, and return code.
- `CliRunner.run(request)`: the one async subprocess boundary.

The runner checks the configured executable with `shutil.which`, invokes with
`asyncio.create_subprocess_exec` and `shell=False`, passes only a copy of the
environment plus `GH_TOKEN`, reads both streams with a hard byte ceiling,
terminates timed-out or over-limit children, and returns only bounded text.
It raises safe typed errors for unavailable executables, timeouts, output
overflow, non-zero exit, and malformed JSON requested by the caller. It never
echoes argv, environment values, stdout, or stderr in an error message.

### 6.3 GitHub client and transport selection

`GitHubClient` receives one `GitHubClientConfig`. Its operation methods accept
the already validated `SourceConfig` and build an internal plan:

- pull request metadata: `gh pr view NUMBER --repo OWNER/REPO --json ...`;
- pull request diff: `gh pr diff NUMBER --repo OWNER/REPO`;
- repository contents: `gh api repos/OWNER/REPO/contents/PATH`;
- code search: `gh search code QUERY --repo OWNER/REPO --json ...`.

The plan is created from validated fields and fixed command constants. A
search query is a value argument, not a route fragment. The direct HTTP
fallback uses `SOURCES_GITHUB_API_ROOT` from `vidbyte/lib/constants` and the
same validated owner/repo/path components.

For the default client, `gh` is attempted first. A missing executable is the
only automatic fallback condition. Injected runners and transports make both
paths deterministic in tests. CLI JSON and REST JSON are normalized into the
same internal section/content shapes; no provider response is exposed in
failure text.

### 6.4 Provider factory

`vidbyte/integrations/providers.py` contains `SourceProviderFactory.create()`.
It uses a `match` on `SourceProvider.GITHUB` and constructs a GitHub client.
There is no `Protocol`: Slack and Drive may expose different context and tool
operations. `SourceContext` and `SourceTool` call the concrete capability they
need after the factory has selected the provider.

### 6.5 SourceContext

`vidbyte/integrations/source_context/` contains the public `SourceContext` and
its load pipeline. It requires a pull-request source, asks the selected
provider for four `LoadedSection` values, converts them into
`DocumentContextItem`s with provider/resource/revision provenance, then admits
them through `ContextAdmission`.

### 6.6 SourceTool and GitHub tools

`vidbyte/integrations/source_tool/` contains the public builder. It requires a
repository source and constructs, in order:

1. `GitHubListFilesTool` from `list_files.py`;
2. `GitHubReadFileTool` from `read_file.py`;
3. `GitHubSearchCodeTool` from `search_code.py`.

Common scope and output handling is class-bound in the GitHub tool base. Each
tool module owns exactly one public tool class. Tool specs expose only
model-fillable values (`path`, `ref`, or `query`); owner, repo, host, route,
and executable are not model parameters. Tool failures become failed
`ToolResult`s, while construction/configuration failures raise.

### 6.7 Reusable library helpers

`vidbyte/lib/integrations_budget.py` owns `ContextAdmission` and its
`AdmissionResult`; token estimation and token clipping are methods, not free
functions. `vidbyte/lib/text.py` owns the reusable UTF-8-safe clipping helper
as `TextClipper.clip()`. The source integration modules import these helpers
from `vidbyte.lib` rather than owning duplicate utility functions.

### 6.8 Errors and observability

Existing `SourceError`/`SourceFetchError` remain the source failure base. The
GitHub client maps classified failures to `SourceFetchError` with safe
provider/resource/state details. Tool results include provider, resource,
operation, transport, and truncation metadata, but never credentials or raw
error payloads. No new diagnostic error class is needed for this bounded
provider surface.

## 7. Data Model Changes

No persisted state or migration. New in-memory values are the strict client
config, CLI request/result, loaded sections, budget result, and source-tool
objects. Secrets exist only in the caller mapping, validated config, and the
short-lived child-process environment.

## 8. API Changes

```python
from vidbyte import Agent, SourceContext, SourceTool

items = await SourceContext(
    {
        "provider": "github",
        "api_key": "ghp_example",
        "resource": "https://github.com/acme/api/pull/41",
    }
).load()
tools = SourceTool(
    {
        "provider": "github",
        "api_key": "ghp_example",
        "resource": "https://github.com/acme/api",
    }
).build()
agent = Agent(name="reviewer", system_prompt="...", context_items=items, tools=tools)
```

`SourceContext` and `SourceTool` are exported from `vidbyte` and
`vidbyte.integrations`. `GitHubClient`, `CliRunner`, and the internal data
classes are implementation seams, not the end-user source API.

## 9. File Change Manifest

Modify the files introduced by PR #431:

- move source budget logic into `vidbyte/lib/integrations_budget.py`;
- update `vidbyte/lib/constants/integrations.py` and
  `vidbyte/lib/dataclasses/integrations.py` with CLI/API/token/timeout rules;
- replace the provider protocol with the class-bound factory;
- split `source_context` and `source_tool` into subpackages;
- move GitHub tools into `vidbyte/tools/integrations/github/`, one class per
  file;
- refactor `vidbyte/integrations/github.py` around `CliRunner` plus REST
  fallback;
- update integration READMEs, exports, tests, and verification script.

Add the reusable library modules `vidbyte/lib/cli.py` and `vidbyte/lib/text.py`
because the review explicitly requests a central reusable CLI/helper boundary.
No unrelated package or application files are changed.

## 10. Testing Plan

Extend `tests/test_source_context_tools.py` and
`scripts/test-source-context-tools.py` with injected fakes for:

- CLI happy path for PR metadata, diff, contents, listing, and search;
- command plans that preserve the bound repository and never contain a token;
- missing CLI fallback to REST;
- CLI timeout, non-zero exit, malformed JSON, and output-limit failures;
- strict token prefix, timeout, transport, and runner validation;
- existing empty-section, zero-budget, UTF-8 clipping, authentication,
  pagination, path escape, search-scope, and unknown-key cases;
- import/build assertions for split source packages and one-tool-per-file
  layout;
- attaching both output lists to a real `Agent` without a network request.

All tests use fake transports/runners. No test depends on a local GitHub login,
network, or installed `gh` executable.

## 11. Dependencies

No new runtime dependency. The CLI runner uses the Python standard library;
HTTP continues to use the existing `HttpTransport`. Existing dev dependencies
run the tests, source gates, package gates, and semgrep policy.

## 12. Rollout

1. Land this updated design with the implementation in the replacement branch.
2. Run the source-specific verification script and all SDK CI stages.
3. Open the replacement PR against `main` with this document as the body.
4. Close PR #431 after the replacement PR exists and point reviewers to the
   replacement.
5. Add Slack and Google Drive as separate provider clients when their concrete
   context/tool shapes are specified; do not generalize the GitHub protocol
   prematurely.

## 13. Open Questions

1. Should future providers expose a shared capability protocol? Decide only
   after a second provider demonstrates which operations are actually common.
2. Should a future CLI provider support a user-selected executable? Current
   answer: no; executable and command allowlists are part of the provider
   trust boundary.
3. Should token budgeting adopt a model tokenizer? Current answer: retain the
   documented character-ratio approximation until model-specific counting is
   selected.

## 14. Alternatives Considered

1. **Accept an arbitrary URL and command and pass them to one subprocess.**
   Rejected: it creates a shell/SSRF/scope boundary controlled by caller input.
   The central runner owns process safety, while the provider owns an
   allowlisted command plan.
2. **Keep direct REST as the only GitHub transport.** Rejected: it ignores the
   intended CLI-native authentication and local GitHub workflow. REST remains
   a safe availability fallback.
3. **Keep one provider protocol for all context shapes.** Rejected: Slack and
   Drive are expected to have different operations and normalization needs.
   The factory switch is explicit until real common behavior exists.
4. **Keep helpers and all tools in the integration modules.** Rejected per
   review: shared budget/text/CLI behavior belongs in `vidbyte/lib`, and each
   tool should be independently discoverable and testable.
