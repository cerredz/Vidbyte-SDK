# Design Doc: Jev Skill Providers

**Status:** Draft
**Author:** Codex
**Created:** 2026-10-01
**Last Updated:** 2026-10-01

---

## 1. Overview

Extend Jev's opt-in skill preload from caller-provided text to explicit local, GitHub, skills.sh, and Claude Skills sources. Resolve sources at run time, preserve one indexed outcome per configured candidate, and let Jev select usable skills before the main model call. Text skills remain in the run context; Claude-native references are mounted only for Anthropic calls and use a bounded, usage-metered pause/resume loop.

---

## 2. Goals & Non-Goals

### Goals

- Accept explicit SkillSource values beside existing inline strings and resolved SkillDocument values.
- Resolve local SKILL.md, GitHub repository/file/tree references, skills.sh owner/repo/slug references, and Claude Skills API metadata without executing skill assets.
- Keep order and index stable; isolate each source failure as one UNAVAILABLE candidate and handle duplicate names discovered after resolution explicitly.
- Score available candidates with Jev, inject selected text in the existing context, and attach selected Claude-native references only to Anthropic requests.
- Add typed per-call claude_skills and claude_skill_session runner options while leaving configured defaults unchanged.
- Resume Claude pause_turn exchanges with exact assistant content and container ID, recording each raw exchange through the existing usage tracker once.
- Preserve ordinary local tools, request limits, cancellation, and existing behavior when callers configure no sources.
- Document source forms and one public usage example in a feature-specific guide.

### Non-Goals

- Guess that strings are file paths; strings continue to mean inline skill text.
- Install skills, clone arbitrary repositories, execute scripts, download or run companion assets, or introduce a generic plugin/registry system.
- Treat Claude list/retrieve metadata as skill text or make opaque native skills available to non-Anthropic providers.
- Add provider-internal retries, hidden aggregation of raw usage, or a second independent agent loop.
- Add native-skill support to streaming calls; such calls fail explicitly before sending a request.
- Integrate bulk-native worker delegation in this PR; that is a later integration change.

---

## 3. Background & Context

The prior jev-skills-preload feature accepts SkillDocument or string values in JevAlignmentSettings.skills. JevSkillsPreload asks fixed, indexed Jev questions, preserves one result per configured text document, and appends selected text to one run's context. SkillDocument currently requires text and does not fetch its optional source. This feature extends that existing boundary rather than changing generic agent context.

The JevPreload.run(message, BaseAgentContext) -> BaseAgentContext contract remains unchanged. The Jev response writer already stores the current JevSkillsOutcome; JevRuntime can read it after preload and create request-local runner options. TextModelRunner already makes a copied TextModelConfig for each call. AnthropicProvider.run_text sends one HTTP request and returns raw response usage, while AgentRuntime centrally records each raw response before local tool parsing.

Cached official Anthropic documentation says Skills use Messages container.skills and code_execution_20250825, support up to 20 references, and reuse container IDs. A long operation resumes by appending the exact assistant content and sending the next request with the container ID. Claude list/retrieve endpoints expose metadata; skill-version metadata does not return the original SKILL.md body. The cached skills.sh documentation describes the Vercel Skills CLI and GitHub-backed source forms, not a skill-content API. Existing PyYAML and bounded HttpTransport.request(max_response_bytes=...) are reused.

---

## 4. Requirements

### Functional Requirements

1. SkillSourceKind is a closed enum with FILE, GITHUB, SKILLS_SH, and CLAUDE. A frozen SkillSource describes one explicit source with location/reference, optional name, revision/version, explicit API key hidden from repr, and optional Claude workspace ID.
2. JevAlignmentSettings.skills accepts str | SkillDocument | SkillSource. Inline strings remain exact text and are never path-guessed. Source resolution occurs during preload/run, never during settings or agent construction.
3. Source resolution is class-first and closed-dispatch. Each configured position yields exactly one result in the same position. Expected resolution, parsing, HTTP, ambiguity, and source-descriptor failures yield UNAVAILABLE for that index while sibling candidates continue. Cancellation propagates. Duplicate names discovered after resolution are identified after resolution; every member of a collision is unavailable, with no constructor-time guess based on optional names.
4. FILE accepts a SKILL.md path or a directory containing it. It bounds file reads, parses YAML frontmatter with existing PyYAML, requires valid name and description, and preserves the body exactly. It does not resolve or execute sibling assets.
5. GITHUB accepts supported GitHub repository, blob, raw, and tree URLs/references. It determines the default branch through the GitHub API, honors explicit revisions, rejects ambiguous slash refs, truncated trees, unresolved selectors, and duplicate matches. It uses bounded HTTP and sends an explicit credential only to approved GitHub hosts.
6. SKILLS_SH accepts an explicit owner/repo/skill-slug reference and resolves it through the same GitHub repository catalog. It does not call an invented skills.sh content endpoint or invoke an installer.
7. CLAUDE lists or retrieves Claude Skills metadata with an explicit Anthropic key and optional workspace ID. It returns a typed ClaudeSkillReference(skill_id, version, type) and metadata only. It never substitutes a description for missing body text.
8. SkillDocument.text may be None only when a valid Claude native reference is present. Text-backed documents keep the existing exact-text validation and source provenance behavior.
9. Jev receives metadata and body text only for text-backed candidates. The fixed relevance question states clearly that native candidates are judged from listed metadata only. Native candidates for non-Anthropic main providers are UNAVAILABLE before scoring. Jev selects candidates independently; selected text is injected as before, selected native references are collected in original order.
10. At most 20 selected native references are attached to one call. Overflow candidates are explicitly marked UNAVAILABLE in their indexed results; no candidate silently disappears or shifts position.
11. JevSkillsOutcome.claude_skills is a typed tuple, default empty. After preload, JevRuntime reads the just-written response outcome and adds claude_skills to the current run's copied options. It does not extend BaseAgentContext or add a generic preload-options callback.
12. TextModelRunner.arun and run accept typed per-call claude_skills and claude_skill_session, copying them into a TextModelConfig for that call. Existing runner config defaults and non-native calls are unchanged.
13. Anthropic adds selected references under container.skills, reuses a session container ID, and adds code_execution_20250825 once while retaining local tool schemas. A conflicting caller-supplied reserved container or incompatible code-execution payload fails with a typed configuration error rather than being overwritten. Native streaming fails before transport.
14. Anthropic validates that native-skill responses include content/container fields needed for safe continuation. Empty text is permitted only for a valid native pause_turn response. Each TextModelResponse carries optional typed ClaudeSkillSession(container_id, paused).
15. After usage recording and after_model_response middleware, but before local tool parsing, AgentRuntime handles a typed paused session. It appends exact assistant content blocks once, reuses the container, and resumes through the ordinary bounded runtime loop. It does not append the original user prompt a second time. Completed native responses preserve the container ID and continue through normal local-tool handling; server-side code execution blocks are never executed as local tools.
16. Existing limits, timeout, and cancellation govern every raw exchange. Usage and cache usage are recorded once per raw response by the existing tracker; no provider-side loop or summed replacement record is introduced.
17. Public exports expose the source enum, source descriptor, Claude reference/session, and updated skill outcome contracts through existing SDK namespaces. A feature-specific guide documents explicit source forms and one example.

### Non-Functional Requirements

- Bound local reads and remote response bodies; use existing transport timeout and no new retry knobs.
- Never leak API keys in reprs, response records, or surfaced provider errors. Never send credentials to arbitrary hosts.
- Preserve candidate ordering, complete text bodies, raw provider usage, caller tool schemas, cancellation, and non-native behavior.
- Keep class and method signatures on one line and add the required immediate one-to-two-line comment below every new/modified method signature.

---

## 5. High-Level Design

SkillSource is a caller-owned typed descriptor. JevAlignmentSettings preserves the candidate list and accepts descriptors without fetching them. During the existing preload phase, a closed SkillSourceResolver dispatches each descriptor to a narrow adapter. The FILE adapter is local; GitHub and skills.sh share GitHub catalog rules; Claude returns opaque references with metadata. Resolution produces one indexed internal candidate per configured item, including failures. Duplicate names discovered in resolved metadata are marked unavailable for every colliding index.

Jev scores only available candidates. It sees full body text for text-backed candidates, or the honest available metadata for Claude-native candidates. Selected text continues through the current BaseAgentContext system prompt. Selected native references are written to JevSkillsOutcome.claude_skills and copied into this run's named provider options by JevRuntime. Generic agent context and preload interfaces do not change.

TextModelRunner creates a per-call config copy. Anthropic mounts native refs in the API container, preserves standard tools, and returns typed session state alongside the untouched raw response and usage. The generic runtime records usage and middleware normally, then consumes pause_turn before its local tool parser. Each resume is another normal runner iteration, so existing token, iteration, timeout, speed, and cancellation logic remains authoritative.

~~~text
SkillSource settings -> closed source resolver -> ordered candidates -> Jev relevance
                                                       |                    |
                                                       |                    +-> text -> run context
                                                       |                    +-> Claude refs -> response.skills -> per-call options
                                                       |                                               |
                                                       +-----------------------------------------------v
                                  TextModelRunner -> Anthropic container + code execution
                                          ^                     |
                                          +--- typed session <--+ pause_turn
~~~

---

## 6. Detailed Design

### 6.1 Source Contracts and Settings

**File(s):** vidbyte/lib/enums/skills.py, vidbyte/lib/enums/__init__.py, vidbyte/lib/dataclasses/skills.py, vidbyte/lib/dataclasses/__init__.py, vidbyte/agents/jev/settings.py, vidbyte/lib/dataclasses/jev.py, vidbyte/__init__.py
**Type:** Modified

#### What it does

Defines the public explicit source kind/descriptor, native Claude reference/session records, and widened Jev skill input/outcome types.

#### Interface / API

~~~python
class SkillSourceKind(str, Enum): ...
@dataclass(frozen=True, slots=True)
class SkillSource:
    kind: SkillSourceKind
    location: str
    skill_name: str | None = None
    revision: str | None = None
    version: str | None = None
    api_key: str | None = field(default=None, repr=False)
    workspace_id: str | None = None
@dataclass(frozen=True, slots=True)
class ClaudeSkillReference:
    skill_id: str
    version: str
    type: str
@dataclass(frozen=True, slots=True)
class ClaudeSkillSession:
    container_id: str
    paused: bool
SkillDocument.text: str | None
JevAlignmentSettings.skills: tuple[str | SkillDocument | SkillSource, ...]
JevSkillsOutcome.claude_skills: tuple[ClaudeSkillReference, ...] = ()
~~~

#### Logic / Algorithm

1. Keep string normalization and existing resolved text validation unchanged.
2. Accept SkillSource values in settings and preserve their input positions. Do not resolve optional names or reject source duplicates at construction.
3. Keep source-specific semantic validation in the resolver so a bad descriptor becomes one indexed UNAVAILABLE result rather than aborting sibling work.
4. Require exactly one content mode: nonblank text without a native reference, or text=None with a valid Claude reference.
5. Keep API keys out of reprs and all Jev response fields. Export public types from vidbyte.lib.enums, vidbyte.lib.dataclasses, and root vidbyte.

#### Edge Cases & Error Handling

- Empty/whitespace inline text remains a configuration error as before.
- Invalid location, missing optional skill_name, or unsupported semantic descriptor is isolated by resolution at its source index.
- A text document with a native ref, or a bodyless document without a ref, is rejected as an invalid contract.
- Exact duplicate text names retain existing settings validation. Duplicates found only after source resolution make every source in that collision unavailable.

### 6.2 Source Adapters and Resolver

**File(s):** vidbyte/providers/skills/__init__.py, vidbyte/providers/skills/base.py, vidbyte/providers/skills/file.py, vidbyte/providers/skills/github.py, vidbyte/providers/skills/skills_sh.py, vidbyte/providers/skills/claude.py
**Type:** New files

#### What it does

Resolve explicit skill descriptors into text documents or Claude-native metadata using a small closed adapter family.

#### Interface / API

~~~python
class SkillSourceAdapter(ABC):
    @abstractmethod
    async def resolve(self, source: SkillSource) -> SkillDocument: ...
class SkillSourceResolver:
    async def resolve(self, sources: tuple[SkillSource, ...]) -> tuple[SkillDocument | SkillSourceFailure, ...]: ...
~~~

#### Logic / Algorithm

1. Dispatch with an explicit match on source.kind to FILE, GITHUB, SKILLS_SH, or CLAUDE; no provider plugin registry.
2. For FILE, resolve a file path or directory's SKILL.md, stat and read under a fixed byte ceiling, parse only YAML frontmatter with installed PyYAML, and preserve the remaining body exactly.
3. For GITHUB, normalize approved GitHub URLs/shorthands; query repository metadata to get the true default branch; use an explicit revision when provided; use bounded tree lookup and raw/blob retrieval; reject malformed, ambiguous, or truncated results.
4. For SKILLS_SH, parse only owner/repo/slug forms and choose the matching SKILL.md from the same GitHub catalog resolver. No CLI, installation, or invented endpoint.
5. For CLAUDE, call official list/retrieve/version metadata endpoints using a typed API request, follow pagination within explicit bounds, and return a ClaudeSkillReference plus display metadata with text=None.
6. Use HttpTransport timeouts and maximum response sizes. Send API keys only to the fixed GitHub or Anthropic host set appropriate to the selected adapter. Do not include secrets in errors.
7. Convert expected per-source transport, parse, not-found, ambiguity, unsupported-kind, and descriptor failures into one indexed unavailable value. Propagate asyncio.CancelledError.
8. After resolution, group by resolved name and mark all colliding indices unavailable. Do not silently take the first result or shift later candidates.

#### Edge Cases & Error Handling

- Missing file, file over byte cap, invalid frontmatter/YAML, absent required metadata, or blank body returns one unavailable result.
- GitHub default-branch lookup failure, missing tree path, ambiguous SKILL.md, incomplete/truncated tree, or slash-ref ambiguity returns one unavailable result.
- HTTP non-success, malformed JSON, pagination loops, Claude metadata missing required IDs, or API-key rejection returns one unavailable result with secret-safe diagnostics.
- Cancelled resolution propagates and is not converted into unavailable.

### 6.3 Jev Preload Integration

**File(s):** vidbyte/agents/jev/alignment/skills.py, vidbyte/lib/jev/preflight/skills.py, vidbyte/agents/jev/settings.py
**Type:** Modified

#### What it does

Resolve source inputs at the existing preload phase, ask Jev only about available candidates, and preserve indexed outcomes for all inputs.

#### Interface / API

~~~python
async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext: ...
~~~

#### Logic / Algorithm

1. Pass the configured generative provider kind into the internal preload object at construction; do not fetch then.
2. On run, create one ordered slot per setting. Existing strings/documents are immediately available; source descriptors resolve into the corresponding slot.
3. Mark Claude native slots unavailable before Jev scoring when the main provider is not Anthropic.
4. Detect resolved name collisions; mark each colliding source slot unavailable.
5. Build indexed relevance questions only for available slots, with indices tied to original configuration order. Native prompt wording explicitly says only listed metadata is available; it does not imply Jev read the hidden skill body.
6. Score independently. Add selected text documents to context using existing injection behavior. Add selected Claude references to the typed response outcome, preserving configuration order and up to 20 entries; mark selected native overflow unavailable in its indexed result.
7. Write exactly one result for every configured candidate. Keep text bodies and credentials out of the outcome.

#### Edge Cases & Error Handling

- No sources preserves existing preload behavior and no new source HTTP call.
- Mixed resolved, unavailable, and cancelled candidates preserve positions; expected source errors do not suppress valid siblings.
- A missing Jev answer or decision call failure follows existing per-candidate unavailable behavior and does not shift indices.
- Native metadata is not scored as if hidden text were present; a generic provider never receives native references.

### 6.4 Runner and Anthropic Request Contracts

**File(s):** vidbyte/lib/dataclasses/model_configs.py, vidbyte/lib/runners/types.py, vidbyte/lib/runners/text.py, vidbyte/lib/runners/__init__.py, vidbyte/providers/anthropic.py
**Type:** Modified

#### What it does

Carry selected native refs and returned container session through one typed model call without changing persistent runner configuration.

#### Interface / API

~~~python
async def arun(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None, claude_skills: Iterable[ClaudeSkillReference] = (), claude_skill_session: ClaudeSkillSession | None = None) -> TextModelResponse: ...
def run(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None, tools: Iterable[Mapping[str, Any]] = (), tool_choice: str | Mapping[str, Any] | None = None, messages: Iterable[Mapping[str, Any]] = (), response_format: Mapping[str, Any] | None = None, claude_skills: Iterable[ClaudeSkillReference] = (), claude_skill_session: ClaudeSkillSession | None = None) -> TextModelResponse: ...
~~~

#### Logic / Algorithm

1. Store request-local values in a dataclasses.replace copy for the current run. Do not mutate the runner's saved defaults.
2. On Anthropic calls with native refs, attach container.skills entries with exact type, skill_id, and version, plus the typed session ID when available.
3. Add the required code_execution_20250825 tool once. Preserve normal caller tools in their existing order. Reject incompatible reserved caller payloads rather than overwriting container or tools data from extra_body.
4. For a paused-session resume, send the already appended assistant content and do not append the previous prompt again. For an ordinary call, preserve normal prompt append semantics.
5. Parse and validate container.id, content, and stop_reason; return raw response and raw usage unmodified plus a ClaudeSkillSession whose paused value matches pause_turn.
6. Permit empty extracted text only for a well-formed native paused response. Raise typed provider response/configuration errors for malformed responses or conflicting payloads.
7. If native skills are configured for streaming, raise before transport.

#### Edge Cases & Error Handling

- Empty native reference tuple produces the current payload aside from explicitly supplied ordinary per-call values.
- Repeated code execution schemas are deduplicated only when equivalent; conflicting reserved schema or extra-body container/tools is a typed config error.
- Missing/blank container ID or invalid content on a native response is a provider response error; no empty successful response is fabricated.
- Cancellation and transport exceptions propagate through the existing provider contract.

### 6.5 Runtime Pause Continuation

**File(s):** vidbyte/agents/jev/runtime.py, vidbyte/agents/runtime.py
**Type:** Modified

#### What it does

Pass only the current Jev run's selected native refs to the runner and continue valid Claude pause turns inside the existing bounded loop.

#### Interface / API

~~~python
def _continue_claude_skill_execution(self, response: TextModelResponse, state: AgentRuntimeState, messages: list[Mapping[str, Any]], options: dict[str, Any]) -> bool: ...
~~~

#### Logic / Algorithm

1. After the Jev preload response writer records JevSkillsOutcome, read response.state.skills.claude_skills and add it to the run's copied options only when nonempty.
2. Generic runtime records raw usage and invokes after-model middleware exactly as today.
3. Before ToolsFormatter.parse_tool_calls, inspect typed session state only when native refs are present.
4. For paused=True, append the exact raw assistant content list once to runtime messages, set the next request's session/container, and continue through the main bounded loop.
5. For paused=False, retain the returned container for later local-tool turns, then allow existing parser/runtime to process only local tool calls. Server tool blocks remain provider-side content.
6. Respect max iterations, token limits, timeout, middleware stop, and cancellation for each exchange. UsageTracker records each raw response exactly once; no rollup is synthesized.

#### Edge Cases & Error Handling

- A response without a typed Claude session follows the current path without native-specific behavior.
- Middleware stop after a paused response exits before another request.
- Paused content is appended once; resume does not duplicate the user prompt or flatten non-text blocks.
- The runtime does not dispatch server_tool_use/code execution blocks to local tools, while preserving ordinary local tool schemas and calls.

### 6.6 Public Usage Guide

**File(s):** docs/jev-skill-providers.md
**Type:** New file

#### What it does

Documents explicit source descriptor forms, limits, and a copyable public setup example without changing the generic README.

#### Interface / API

No callable API; examples use the exported SDK contracts.

#### Logic / Algorithm

1. Explain that plain strings remain inline text.
2. Show local file, GitHub, skills.sh, and Claude source descriptors with explicit kinds.
3. State that Claude Skills require Anthropic and use metadata-only Jev selection; source credentials are passed explicitly and never logged.
4. Explain run-time resolution, per-source unavailable outcomes, native cap, and no execution of repository scripts/assets.

#### Edge Cases & Error Handling

- A missing/unreachable source is an indexed unavailable result, not a guessed inline/path conversion.
- Native Claude sources configured for another provider are unavailable.

---

## 7. Data Model Changes

### 7.1 SkillSourceKind

**Change type:** Modified enum module; no database migration.

~~~python
class SkillSourceKind(str, Enum):
    FILE = "file"
    GITHUB = "github"
    SKILLS_SH = "skills_sh"
    CLAUDE = "claude"
~~~

### 7.2 SkillSource, ClaudeSkillReference, ClaudeSkillSession

**Change type:** New frozen value contracts in vidbyte.lib.dataclasses.skills.

~~~python
@dataclass(frozen=True, slots=True)
class SkillSource:
    kind: SkillSourceKind
    location: str
    skill_name: str | None = None
    revision: str | None = None
    version: str | None = None
    api_key: str | None = field(default=None, repr=False)
    workspace_id: str | None = None
~~~

No migration. API keys are excluded from repr and outcomes.

### 7.3 SkillDocument and JevSkillsOutcome

**Change type:** Modified.

SkillDocument.text becomes nullable only with a typed native Claude reference. JevSkillsOutcome adds claude_skills: tuple[ClaudeSkillReference, ...] = (). TextModelConfig and TextModelResponse add typed native request/session fields needed for one HTTP exchange at a time.

---

## 8. API Changes

### 8.1 Jev Skill Input

**Change type:** Modified public Python configuration surface; no HTTP endpoint.

**Request:**

~~~python
JevAlignmentSettings(skills=("inline text", SkillDocument(...), SkillSource(kind=SkillSourceKind.GITHUB, location="https://github.com/acme/skills", skill_name="review")))
~~~

**Response:** The existing JevSkillsOutcome includes one ordered result per configured candidate and zero or more selected native references.

**Error cases:** Invalid Python value types remain configuration errors. A well-typed source that cannot be resolved becomes one indexed UNAVAILABLE result; cancellation propagates.

### 8.2 TextModelRunner per-call options

**Change type:** Modified TextModelRunner.run and arun Python API.

**Request:** Optional typed claude_skills and claude_skill_session keyword parameters.

**Response:** Existing TextModelResponse, extended with optional typed session for native Claude calls.

**Error cases:** Unsupported provider, streaming native request, conflicting reserved payload, malformed native response, or transport error surfaces through existing typed configuration/provider errors.

---

## 9. File Change Manifest

Complete list of every file expected to be created, modified, or deleted. Totals: 10 create, 16 modify, 0 delete.

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | docs/design/jev-skill-providers.md | Architecture and implementation source of truth. |
| CREATE | docs/jev-skill-providers.md | Feature-specific public source guide and example. |
| CREATE | vidbyte/providers/skills/__init__.py | Closed resolver exports and dispatch. |
| CREATE | vidbyte/providers/skills/base.py | Narrow adapter protocol and safe source failure contract. |
| CREATE | vidbyte/providers/skills/file.py | Bounded local SKILL.md resolver. |
| CREATE | vidbyte/providers/skills/github.py | GitHub catalog, default branch, bounded tree/blob resolution. |
| CREATE | vidbyte/providers/skills/skills_sh.py | Explicit skills.sh slug-to-GitHub adapter. |
| CREATE | vidbyte/providers/skills/claude.py | Claude Skills metadata API adapter. |
| CREATE | tests/test_jev_skill_providers.py | Adapter, pipeline, provider, runtime, and failure coverage. |
| CREATE | scripts/test-jev-skill-providers.py | Executable design-plan test harness. |
| MODIFY | vidbyte/lib/enums/skills.py | Define closed source-kind enum. |
| MODIFY | vidbyte/lib/enums/__init__.py | Export source-kind enum. |
| MODIFY | vidbyte/lib/dataclasses/skills.py | Add source/native typed contracts and nullable native body rule. |
| MODIFY | vidbyte/lib/dataclasses/jev.py | Carry ordered native selections in the run outcome. |
| MODIFY | vidbyte/lib/dataclasses/__init__.py | Export source and native contracts. |
| MODIFY | vidbyte/__init__.py | Export public SDK source and native contracts. |
| MODIFY | vidbyte/agents/jev/settings.py | Accept explicit source descriptors without constructor fetching. |
| MODIFY | vidbyte/lib/jev/preflight/skills.py | State honest metadata-only criteria for native candidates. |
| MODIFY | vidbyte/agents/jev/alignment/skills.py | Resolve, score, preserve indexes, and select source candidates. |
| MODIFY | vidbyte/lib/dataclasses/model_configs.py | Add per-call Claude refs/session fields to copied provider config. |
| MODIFY | vidbyte/lib/runners/types.py | Carry typed native session in text response. |
| MODIFY | vidbyte/lib/runners/text.py | Forward typed per-call options through config copy. |
| MODIFY | vidbyte/lib/runners/__init__.py | Export typed response/session contracts as needed. |
| MODIFY | vidbyte/providers/anthropic.py | Mount refs, preserve tools, parse session, reject unsupported stream. |
| MODIFY | vidbyte/agents/jev/runtime.py | Add selected refs to named per-run options after preload. |
| MODIFY | vidbyte/agents/runtime.py | Meter and resume native pauses inside the bounded loop. |
| DELETE | N/A | No deletion is required. |

---

## 10. Testing Plan

All cases run without live provider credentials. Adapter HTTP uses stub transports; file cases use temporary directories. The mandated script invokes every case and prints one PASS/FAIL per test plus an X/Y tests passed summary. Each listed test is individually labeled by category.

### Unit Tests

- [Edge Case] Source contract accepts each closed kind, keeps secret repr-safe, and rejects invalid content-mode combinations.
- [Hidden Failure] A semantically invalid configured source becomes exactly one indexed unavailable result; another source still resolves.
- [Silent Failure] Configured strings preserve exact leading/trailing text and are not interpreted as file paths.
- [Hidden Assumption] Optional skill_name is absent and the adapter must select only a unique metadata/path match.
- [Edge Case] FILE resolves both a SKILL.md path and a directory, including minimal frontmatter/body.
- [Hidden Failure] FILE reports over-limit, unreadable, and malformed YAML inputs as unavailable without reading sibling assets.
- [Silent Failure] FILE preserves body whitespace and code fences after removing only the frontmatter envelope.
- [Hidden Assumption] Missing, non-string, or blank YAML metadata is not silently replaced with defaults.
- [Edge Case] GitHub URL forms cover repository root, explicit tree path, blob path, and raw path.
- [Hidden Failure] GitHub transport failure, default-branch lookup failure, and truncated tree remain local to one candidate.
- [Silent Failure] A slash-containing branch/path is not misparsed as a different skill; ambiguity requires explicit revision.
- [Hidden Assumption] Default branch is read from repository metadata rather than assumed to be main.
- [Edge Case] skills.sh accepts owner/repo/slug and resolves a unique match.
- [Hidden Failure] A catalog failure never triggers a guessed skills.sh API or installer.
- [Silent Failure] Slug/frontmatter mismatch or duplicate match cannot silently select another skill.
- [Hidden Assumption] URL-looking inline strings remain literal text unless wrapped in SkillSource.
- [Edge Case] Claude metadata supports custom and Anthropic refs with explicit versions.
- [Hidden Failure] Claude pagination, malformed metadata, and credential rejection return one unavailable item without exposing keys.
- [Silent Failure] Claude description is never placed into SkillDocument.text or injected as instructions.
- [Hidden Assumption] Workspace ID omission is accepted for a scoped credential; an explicit mismatch becomes unavailable.
- [Edge Case] Two sources resolving to one name mark every colliding slot unavailable without reordering.
- [Hidden Failure] One resolver exception cannot cancel sibling assembly; CancelledError still propagates.
- [Silent Failure] Outcome length/order equal configured inputs after failed, duplicate, and unsupported candidates.
- [Hidden Assumption] A native skill on a non-Anthropic provider is unavailable before Jev scoring.
- [Edge Case] Exactly 20 native refs mount; 21 selected refs retain explicit unavailable overflow.
- [Hidden Failure] Missing Jev answer or decision failure cannot shift an answer onto another candidate.
- [Silent Failure] Generated question indices remain tied to original candidate positions.
- [Hidden Assumption] Jev question text admits metadata-only evaluation for opaque native candidates.
- [Edge Case] Empty refs leave persistent runner config unchanged; repeated calls carry independent refs/session.
- [Hidden Failure] Conflicting extra_body container/tools and incompatible code execution schema fail before HTTP.
- [Silent Failure] Ordinary local tools remain present and equivalent code execution schema appears once.
- [Hidden Assumption] Streaming with native refs fails before transport instead of omitting them.
- [Edge Case] Valid paused response with empty text but structured content is accepted; final session is unpaused.
- [Hidden Failure] Missing container ID/content is a typed provider response failure.
- [Silent Failure] Full assistant content blocks and raw usage survive response/session handling exactly.
- [Hidden Assumption] Non-native calls preserve their current payload and response behavior.
- [Edge Case] Pause on the last allowed iteration and middleware stop after pause are bounded.
- [Hidden Failure] Cancellation/timeout during resume propagates.
- [Silent Failure] Pause content is appended once and original user prompt is not duplicated.
- [Hidden Assumption] Server-side code execution blocks are never dispatched as local tools while local tool calls still work.
- [Edge Case] Two exchanges preserve per-call usage, including cached input fields when present.
- [Hidden Failure] Continuation failure does not bypass usage recording for an already received response.
- [Silent Failure] Every HTTP response is recorded once without flattening priced rollups.
- [Hidden Assumption] Existing max-iteration, token, and timeout bounds apply to resumes through the normal loop.

### Integration Tests

- FILE source through JevAgent resolves, receives an indexed decision, and injects only selected exact body text into the current run.
- Claude metadata selection produces typed refs for Anthropic and none for non-Anthropic.
- Anthropic stub captures container refs, code execution plus local schemas, and container ID on pause/resume; assistant blocks survive exactly.
- Runtime stub confirms two raw responses create two usage records and pause resumes through existing iteration bounds.
- Mixed source failure verifies original settings order and one unavailable outcome per failed/ambiguous source.

### Manual / QA Test Cases

1. Given a local directory containing frontmatter SKILL.md, when configured as FILE, then Jev reports one result and injects selected exact body text.
2. Given a skills.sh source slug, when resolved, then it maps to the matching GitHub catalog and makes no installer or skills.sh content API call.
3. Given an Anthropic-native selection and pause_turn response, when resumed, then the next request reuses the container and exact prior assistant content without duplicating the prompt.
4. Given an unavailable source beside an available inline skill, when preload runs, then the inline candidate can still be selected.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| PyYAML | Existing project dependency | Parse SKILL.md frontmatter | Malformed YAML becomes unavailable. |
| GitHub REST API | api.github.com repository, tree, blob endpoints | Resolve explicit GitHub and skills.sh catalog sources | Rate limiting, private repository auth, truncated trees. |
| Anthropic Skills API | api.anthropic.com/v1/skills and version endpoints | Discover metadata and native IDs/versions | API key/workspace scope; metadata is not body text. |
| Anthropic Messages API | /v1/messages | Mount native skills and code execution; container continuation | Provider/model capability and response shape. |
| Existing HttpTransport | Existing timeout/response-size controls | Bounded remote calls | Propagate cancellation and typed errors. |

No new package dependency is planned.

---

## 12. Rollout & Deployment

- Opt-in only: applications without SkillSource or native runner kwargs keep current behavior.
- No database or persisted config migration. New enum/dataclass fields are additive except SkillDocument.text becomes conditionally nullable for typed native references.
- Release with the SDK after source, lint, focused script, and full SDK CI gates pass.
- Implement in parent-reviewed stages: first public contracts, the FILE adapter, closed dispatch, and one real Jev preload integration; pause for review before adding remote adapters or native runtime continuation.
- Rollback is a code revert; callers can continue with inline strings and resolved SkillDocument values.
- Native support requires Anthropic and code execution capability; unsupported providers get explicit unavailable outcomes.

---

## 13. Open Questions

- [ ] Confirm supported GitHub shorthand grammar during implementation against cached Vercel source-format documentation; reject other forms.

---

## 14. Alternatives Considered

### Alternative 1: Interpret strings as local paths when they look like paths

- What: Probe strings for path/URL syntax before treating them as inline text.
- Why rejected: It makes existing strings ambiguous, can trigger surprise file/network access, and breaks the established inline text contract.

### Alternative 2: Use a generic plugin registry

- What: Allow arbitrary adapter registration/callbacks.
- Why rejected: Four explicit source types are sufficient; a registry widens the execution and trust surface without a current use case.

### Alternative 3: Download Claude Skill bundle content and inject it as text

- What: Convert native Claude metadata into generic model prompt text.
- Why rejected: Stable list/retrieve APIs expose metadata and references, not the bundle body. A description would misrepresent what Jev and other providers can use.

### Alternative 4: Resume pause turns inside AnthropicProvider

- What: Hide retries and repeated HTTP responses inside one provider call.
- Why rejected: It would hide raw exchanges from usage/speed accounting and runtime iteration, timeout, and cancellation controls.

### Alternative 5: Add source outcomes/options to generic BaseAgentContext

- What: Extend generic context with provider-specific preload metadata or a callback.
- Why rejected: Jev's current response outcome is already the typed run-local carrier; generic context would spread this capability to unrelated agents.
