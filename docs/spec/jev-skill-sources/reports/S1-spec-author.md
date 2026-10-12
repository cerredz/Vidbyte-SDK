# S1 Spec author report: jev-skill-sources

- **Stage:** S1 spec author, revision r1
- **Output:** `docs/spec/jev-skill-sources/spec.md`, 868 lines, 18 `## §` sections, committed as `80cea9d0` ("docs(spec): add jev-skill-sources spec r1")
- **Base:** `ba3e4ca5`; branch `feat/jev-skill-sources`
- **This report:** written after the commit and left uncommitted, as S0's report was; the orchestrator commits reports at stage boundaries.
- **Restrictions kept:**
  - no production code and no tests;
  - no network calls;
  - no edits outside the spec and this report;
  - under `docs/` I read only `request.md`, `context/code-map.md` and `reports/S0-scout.md`.

## What I read

### Pipeline inputs
- `request.md` (whole)
- `context/code-map.md` (whole)
- `reports/S0-scout.md`
- the skill references:
  - `spec-template.md`
  - `house-style.md`
  - `report-formats.md`
  - `vidbyte-gates.md` (via the scout)

### Rules
- AGENTS.md (whole)
- REPO_MAP.md:
  - the `vidbyte/agents/*` entries
  - the three-skills-locations warning
  - the JEV table
- `lint/README.md` (ratchet section)

### Preload wiring
- `vidbyte/agents/jev/alignment/skills.py` (whole)
- `agent.py` (construction of the preload; fresh-continuation factory)
- `runtime.py`: `_arun_metered`, `_preload_skills`
- `preload.py`
- `response.py`: `start`, `skills`
- `settings.py`: header, `JevAlignmentSettings`
- `vidbyte/agents/base.py:1265,1285`. `arun` calls `self._runtime().arun`, and `_runtime()` builds a new runtime each call.

### Records, enums, constants
- `vidbyte/lib/dataclasses/skills.py` (whole)
- `vidbyte/lib/dataclasses/jev.py`:
  - header
  - `JevSkillResult`, `JevSkillsOutcome`, `JevSkillBatch` (3722-3790)
  - `JevText`
- `vidbyte/lib/enums/skills.py` (whole)
- `vidbyte/lib/enums/__init__.py` (skills block)
- `vidbyte/lib/constants/jev.py`: `VIDBYTE_API_KEY_PREFIX`, the skills constants
- the `vidbyte/lib/constants/` listing

### Helpers
- `vidbyte/lib/http/transport.py`: `request`, `_send_once`, `_send_bounded`
- `vidbyte/lib/http/parser.py`: `bearer_headers`
- `vidbyte/lib/http/vidbyte_gateway.py`: the status-to-remedy pattern
- `vidbyte/lib/errors/base.py`: `ProviderRequestError`
- `vidbyte/lib/registries/models.py`:
  - `resolve_api_key`
  - `get_default_endpoint`
  - `find_vidbyte_api_key`
- `vidbyte/tools/builtins/operations/clients/_base.py` (symbols)
- `vidbyte/skills/catalog.py` (the frontmatter parser)
- `vidbyte/lib/dataclasses/coding.py`: the `root_dir` header lines

### Pattern sibling
- `vidbyte/agents/coding_context/`:
  - `__init__.py`
  - `root_file.py` (lines 1-110)
  - the README headings

### Exports
- The `SkillDocument` and `JevSkillStatus` lines in:
  - `vidbyte/__init__.py`
  - `vidbyte/agents/__init__.py`
  - `vidbyte/agents/jev/__init__.py`
  - `vidbyte/lib/__init__.py`
  - `vidbyte/lib/dataclasses/__init__.py`

### Tests
- `tests/test_jev_skill_preload.py`:
  - imports and fakes
  - settings tests (155-196)
  - edge-case tests (338-383)
  - greps for `_build_batch`, `preload.*`, and `JevSkillResult(`
- `tests/features/jev_skills_preload/FEATURE.md`

### Other
- `pyproject.toml` (versions)
- `lint/ruff.toml` (banned APIs)
- Bundled claude-api skill files: the Skills API tables, and the GA note in its drift table. This was a local cache, not a network call.

### Commands run (local only)

**`python lint/run.py --rule A001 --format json`.** The parsed result:
```
643 643 RATCHETED
[{'path': 'vidbyte/lib/enums/skills.py', 'line': 1, ..., 'extra': {'missing': 'ROLE IN CODEBASE:, ARCHITECTURE NOTE:, COMMON MODIFICATION PATTERNS:, KNOWN EDGE CASES:, RELATED DOCS:, TESTS:'}}]
```

**Zip probe, run under Python 3.11.0 with `-I`.** The output:
```
corrupt-middle (<class 'zlib.error'>, ...) Error -3 while decompressing data: invalid bit length repeat
truncated (<class 'zipfile.BadZipFile'>, ...) File is not a zip file
notzip (<class 'zipfile.BadZipFile'>, ...) File is not a zip file
lying BadZipFile Bad CRC-32 for file 'SKILL.md'
flag_bits 0
```

**httpx and path probe.** The output:
- `httpx.AsyncClient().headers` includes `user-agent: python-httpx/0.28.1`.
- `quote('release/v1', safe='')` gives `release%2Fv1`.
- `PureWindowsPath('.agents/skills')/'C:x'` gives `C:x`.

**Earlier in this stage, before a context compaction:**
- Slotted dataclass inheritance probes on 3.11.0 and 3.13.1:
  - a base `type = field(init=False)` with per-subclass defaults works;
  - passing `type=` raises `TypeError`;
  - the entries pickle;
  - `super().__post_init__()` raises `TypeError` in a slotted subclass.
- `dict(response.headers)` lowercases keys.
- `yaml.safe_load` parses folded `>` descriptions.

## Approaches weighed and why I chose mine

1. **How the preload gets resolved documents (D-8).** Three options:
   - (a) A per-run mutable `self.documents` on the preload.
   - (b) The loader owned by the preload. `_build_batches(message)` reads `loader.documents()`, and `SkillDocument` entries are remembered from construction.
   - (c) A `documents` parameter on `_build_batches`.

   (c) breaks the existing test, which calls `_build_batches("…")` with one argument before any run. (a) adds mutable per-run state to an object that lives across runs. I chose (b): it keeps the test contract with no new mutable state.

2. **Entry validation (D-3).** The natural design is a base `__post_init__` that each subclass extends with `super().__post_init__()`. That raises `TypeError` in slotted dataclass subclasses on both 3.11 and 3.13, which I verified. I chose a template hook instead: the base validates `name`, then calls `_validate_source()`. Shared text checks go through a static helper class (`SkillText`, after the `JevText` precedent), which keeps own-helper calls one level deep.

3. **Resolver shape against AGENTS.md principle 1 (D-22).** I considered three shapes:
   - Phase-style `resolve` mains for every source. These are flat, but long and heavy on bookkeeping.
   - Sequential per-entry loops. These are flat, but first-run latency grows linearly.
   - The base `resolve` as a concurrent fan-out into each subclass's narrated `_resolve_one`.

   I chose the fan-out and named it in the spec as the one sanctioned two-step. GitHub overrides `resolve`, because it must share the commit lookup and tree listing across entries. The §8.4 budget allows one private per-group helper class in the `github` module if the implementer needs it to stay flat. A reviewer may still flag the fan-out-plus-`_resolve_one` chain.

4. **The HTTP step (D-9).** Calling `HttpTransport` directly from each resolver family would duplicate the exception mapping:
   - no answer → `FETCH_FAILED`;
   - a 2xx answer over the size cap → `TOO_LARGE`.

   I chose one small `SkillFetch`. It returns the `HttpResponse` for every status, so that GitHub's 403 rate-limit check (which reads response headers) stays in the GitHub module.

5. **Cache-less design (§8.3).** I rejected it because five GitHub skills cost seven requests per run, which exhausts the 60/hour unauthenticated limit in nine runs.

6. **Vendor "latest" (D-19).** The runner-up was to always read the metadata first. That costs one extra call per vendor skill on every first run. I chose to try `latest` first and fall back on 400, 404 or 422, which works whichever way the open question resolves.

7. **Parser (D-12, D-13).**
   - I wrote a new `SkillMarkdown` parser rather than reusing `vidbyte/skills/catalog.py:_parse_frontmatter_fields`. That parser is line-based, rejects folded YAML continuation lines, requires the name to equal the folder, and returns no body.
   - I chose strict UTF-8 decoding over `errors="replace"`, because replacement characters would silently change an agent's instructions.

8. **Redirects (D-10).** Redirects are never followed, because httpx keeps `x-api-key` on cross-origin redirects. A GitHub 3xx maps to `NOT_FOUND` ("moved"), which is permanent for a renamed repository. A vendor 3xx maps to `FETCH_FAILED`.

## Where I disagreed with the request or the scout (with evidence)

**Superseded or corrected claims in request.md**
- **"`SkillDocument` becomes internal" (request.md:163).** Superseded by the orchestrator decision.
  - The test asserts the root export (`tests/test_jev_skill_preload.py:25,164`).
  - The test asserts string normalization to `SkillDocument` with `source == "inline"` (:171-174).
  - The spec keeps both (D-4, INV-20, INV-21).
- **"JevRuntime restores its per-run fields in a `finally` block" (request.md:208).** False: `runtime.py` has no `finally`. It does not matter, because the loader lives on the preload.
  - The preload is built once in `JevAgent.__init__` (`agent.py:80-89`).
  - The runtime is rebuilt every run (`base.py:1265` → `_runtime()` at :1285).
  - This also resolves the scout's "Unverified: `_runtime()` once per run": it runs **every** run.
- **YAML loader citation (request.md:239).** It cites `vidbyte/lib/config/loader.py`, which imports upward (`vidbyte.agents.settings.loop`, code-map N7). The spec uses `yaml.safe_load` directly.

**Names I changed from the request**
- **Reason enum name (request.md:157 proposed `JevSkillUnavailableReason`).** I chose `SkillUnavailableReason` in the skills enum domain (D-7): the agent-agnostic loader produces six of the eight values. The flip condition is recorded.
- **Label prefix `skills.sh:` (request.md:171).** I chose `skills_sh:`, the enum value, for one consistent label scheme (D-21).
- **`latest_version_id` (request.md:181).** My recollection of the beta object is `latest_version`, and neither is verified. The spec reads `latest_version` through a single constant (A-2, D-19).

**Anthropic Skills API status**
- The bundled Claude API skill (local cache) says the Skills API is GA, and that requests still sending `skills-2025-10-02` get the old beta shapes.
- Its endpoint tables do not list `/versions/{version}/content`.
- I kept the beta header, because the conversation read the beta download reference, and recorded this as A-1 with a flip condition.

**Field naming collision (scout N4)**
- I kept `SkillsShSkill.source`, as the user approved in the sketch (D-16). It is also the `skills-lock.json` key and the `npx skills add <source>` argument.
- I recorded Q-3 (rename to `repo`?), defaulting to no.

**Package location vs AGENTS.md:76 (scout N1)**
- The user's directive wins (D-2), reconciled as follows:
  - Resolving a source asks Jev nothing and touches no Jev state.
  - The Jev capability itself (selection) stays in the JEV package.

**Scout items confirmed**
- Batching (N10): the field guide's "one request per candidate" is out of date; the code batches.
- Semgrep is not in `run_ci.py`.
- FEATURE.md's "deferred" sentence is stale; §12.3 row 29 assigns that update to S2.

**Judgment calls that a reviewer may call scope**
None of these adds a field or a knob. Each defines the value domain or failure mapping of an agreed field.
- `GitHubSkill.path="."` names the repository root. It is the only way to load a single-skill repository.
- Construction-time rejection of a `LocalSkill.path` or `GitHubSkill.path` that ends in `SKILL.md`.
- Vendor 400/422 maps to `NOT_FOUND`.
- GitHub 3xx maps to `NOT_FOUND`.
- Local `OSError` maps to the transient `FETCH_FAILED`.

## Assumptions I am least sure of

1. **A-1, A-3, A-4: the vendor content routes.**
   - Whether they exist as written.
   - Whether they return zip bytes.
   - Whether they answer directly rather than through a redirect.

   If any is wrong, every Anthropic or OpenAI skill fails with an explained reason; the fix is local to one resolver.
2. **A-2:** which statuses refuse `latest`, and the metadata field name.
3. **A-6:** GitHub's 422 for an unknown ref, and whether it accepts `%2F`-encoded refs.
4. **mypy (S009) and the generic resolvers.** S009 must accept `SkillResolver(Generic[SkillEntryT])` with a `VendorSkillResolver` over a constrained TypeVar. Not run. If mypy objects, the implementer needs equivalent typing, without renaming the §8.5 classes.
5. **The `RuntimeError` on an encrypted zip member.** That the stdlib raises it is known CPython behavior, but I did not run it. D-20's flag check guards it either way.
6. **The A001 count.** The header upgrade should lower A001 by exactly one (to 642). This assumes the new and modified files all carry complete headers; otherwise the count rises and REGRESSES.
