# Skill sources

This package turns declarative skill entries into `SkillDocument` records an agent can use. A developer lists entries such as `GitHubSkill(name="pdf", repo="anthropics/skills")` in `JevAlignmentSettings.skills`; nothing is read while the agent is built, and on the agent's first run `SkillLoader` reads each entry from its source, parses its `SKILL.md`, and hands JevAgent's skill preload one result per entry: a document, or a reason with an explanation. The package is agent-agnostic: it imports only `vidbyte.lib` and its own modules, and JevAgent's preload (`vidbyte/agents/jev/alignment/skills.py`) is its consumer.

The six sources, one entry class and one resolver module each:

| Entry (`vidbyte/lib/dataclasses/skills.py`) | Resolver module | Reads | Label on the document |
|---|---|---|---|
| `InlineSkill` | `inline.py` | the description and text written in the settings | `inline` |
| `LocalSkill` | `local.py` | `<path>/SKILL.md` on this machine | `local:<folder name>` |
| `SkillsShSkill` | `skills_sh.py` | `<directory>/<name>/SKILL.md` installed by `npx skills add`, checked against `skills-lock.json` | `skills_sh:<source>/<name>[@<hash>]` |
| `GitHubSkill` | `github.py` | a folder's `SKILL.md` through the GitHub REST API, pinned to one commit | `github:<owner>/<repo>@<sha>/<folder>/SKILL.md` |
| `AnthropicSkill` | `anthropic.py` over `vendor.py` | a skill version from Anthropic's Skills API | `anthropic:<skill_id>@<version>` |
| `OpenAISkill` | `openai.py` over `vendor.py` | a skill version from OpenAI's Skills API | `openai:<skill_id>@<version>` |

The shared pieces are `resolver.py` (the `SkillResolver` base), `fetch.py` (`SkillFetch`, the one bounded GET), `markdown.py` (`SkillMarkdown`, the one `SKILL.md` parser), and `loader.py` (`SkillLoader`, the coordinator and its memory).

## The contract

- **No I/O at construction.** Entries validate their own fields when they are created and pin relative paths to the working folder; `SkillLoader(entries)` only stores them. Files, environment variables, and the network are read inside `load()`, on the first run.
- **One resolver per source type.** `SkillLoader` keeps a map from `SkillSourceType` to its resolver, groups the entries it has not remembered by `(entry.type, resolver.group_key(entry))`, and resolves every group at the same time. Only GitHub shares lookups: its group key is `(repo, ref, token)`, so entries from one repository, ref, and token share one commit lookup and at most one tree listing.
- **Fail open, with reasons.** An expected failure is data, never an exception: a `SkillResolution` with a `SkillUnavailableReason` (`not_installed`, `not_found`, `auth_failed`, `rate_limited`, `fetch_failed`, `invalid_skill`, `too_large`) and a detail that names the fix. A programming error, such as a `RuntimeError` from a resolver, propagates unchanged, and cancellation stays cancellation.
- **Memory.** Each loader remembers every document and every permanent failure for its own lifetime, and the first remembered value is never replaced. `rate_limited` and `fetch_failed` are transient (`SKILL_TRANSIENT_REASONS`) and are tried again on the next run. A remembered entry costs no request and no file read on later runs.
- **Bounds.** Every request goes through `HttpTransport.request` via `SkillFetch`: a 10-second timeout per network operation, one retry on retryable statuses, no redirects, a size cap per step, and a 25-second deadline per step. A `SKILL.md` is capped at 1 MiB and any other download at 32 MiB; the caps live in `vidbyte/lib/constants/skills.py`.

## Adding a source

1. **The enum member**: add it to `SkillSourceType` in `vidbyte/lib/enums/skills.py`.
2. **The entry class**: a frozen, slotted subclass of `SkillEntry` in `vidbyte/lib/dataclasses/skills.py` that redeclares `type` with `field(init=False)` and its member as the default, and checks its own fields in `_validate_source` (never `super().__post_init__()`; slotted subclasses cannot call it). Secret fields are `field(default=None, repr=False)`.
3. **The resolver module**: one file here with a `SkillResolver[<Entry>]` subclass whose `resolve(entries)` is a narrated main that calls only leaf helpers and other classes. Network requests go through `SkillFetch.get`; the file goes through `SkillMarkdown.parse`; statuses map through a dict keyed by `HTTPStatus` members with an explicit default. A source hosted by a model vendor's Skills API instead subclasses `VendorSkillResolver` (as `anthropic.py` does), sets `PROVIDER`, `SOURCE_TYPE`, and `_headers`, and adds its entry class to the constrained `VendorSkillT` in `vendor.py`, or mypy (lint S009) rejects the subclass.
4. **The loader map**: one line in `SkillLoader.__init__`.
5. **The exports**: the entry class beside the other entries in `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/__init__.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, and `vidbyte/__init__.py`.
6. **The contract**: commit the root export, then run `python scripts/generate-sdk-public-api.py` to regenerate `contracts/sdk-public-api.json`.

## Non-goals

This package does not install skills, run `npx` or any process, refresh a remembered skill while an agent lives, follow links or files that a `SKILL.md` mentions, extract archives to disk, or load anything a skill bundles besides its `SKILL.md`. Well-known URLs, GitLab, and Vidbyte-hosted skills are not sources here.

## Notes for agents

- Never run `npx`, a subprocess, or a shell from this package; a missing skills.sh install is reported as `not_installed` with the command for the developer to run.
- Never follow redirects. httpx drops `authorization` on a cross-origin redirect but keeps `x-api-key`, so a vendor redirect could hand a key to another host.
- Never put a token or key in a label, a detail, a URL, or a log line. Details are written by the SDK and never echo a response body or a YAML error, which can quote the file. A key or token that starts with `VIDBYTE_API_KEY_PREFIX` is refused before any request; never spell that prefix in code.
- Never import `vidbyte.agents.jev`, and never write `from vidbyte.agents import …` here: the `vidbyte.agents` package root is still initializing while JEV imports the loader.
- This is the fourth folder named for skills. The repository's `skills/` holds guidance for developers and agents, `vidbyte/skills/` loads the SDK's packaged skill catalog, and `vidbyte/prompts/skills/` holds skill documents shipped as prompt assets. This package is none of those: it loads skills the developer configures from outside the package.
- Entries are trusted configuration, and the GitHub, Anthropic, and OpenAI fallbacks read process credentials (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). An app that builds entries from untrusted input, such as one tenant's settings, must pass an explicit `token=` or `api_key=` on every entry or unset those variables; otherwise the operator's credentials read that tenant's skills.
- A host whose egress to GitHub or a vendor is blocked pays up to one deadline per step on every run, because transient failures are never remembered.
- The loader's memory is resolved configuration, not run state: it holds only what the frozen entries resolved to, never a message, answer, or usage, and it lives per agent. It does not conflict with the JEV rule that run state is run-local.
- A `SKILL.md` at the root of a GitHub repository is not supported; `GitHubSkill.path` must name a folder below the root, and `path="."` is rejected.
