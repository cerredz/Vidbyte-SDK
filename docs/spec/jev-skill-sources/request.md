---
slug: jev-skill-sources
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-11 23:17
flags: none
---

# Request: JevAgent skill sources — declarative skill entries (inline, local, skills.sh, GitHub, Anthropic, OpenAI) resolved under the hood

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening question; the user pasted the current public docs page for JevAgent skill preloading inside the parentheses):

````text
question for the JevAgent inside of the vidbyte-sdk/ (

This page is part of the Vidbyte SDK documentation. It introduces “JevAgent Skill Preloading” and explains what this page covers. The text below includes the page information and examples. You can share it with a teammate or an assistant for help with this topic.

Optional capability · SDK mainJevAgent Skill PreloadingGive JevAgent a library of skills, and before each run Jev checks every skill against the request and loads only the ones that fit into your agent's instructions. Skill preloading is on the SDK's main branch and isn't in a tagged SDK release yet.Offer many skills, load only the ones that fitA skill is a written guide your agent can follow, such as a review checklist or a release-notes style guide. Loading every skill into every run spends your agent's attention on guidance that doesn't apply, so Jev picks the skills that fit each request.Before your agent starts, Jev asks one question about each of your candidate skills: would its guidance help with this request? Each skill that passes is added, in full, to your agent's instructions for this run only. The rest stay out.One request, every skill checkedOn SDK main · illustrativeRequestReview PR 182 for breaking API changes↓Jev · System 2 · once per skillWould this skill's guidance help with this request?Selected · at or above the thresholdFull text added to this run's instructionsSeveral skills can pass at once.Your agent startsIts own instructions plus every selected skill.Skipped · below the thresholdLeft out of this runYour agent never sees its text.Unavailable · no answerLeft out; the run continuesJev couldn't be reached, or the skill was too large to check.Illustrative flow, not recorded Jev output. Every skill is judged on its own, and each one at or above the threshold (0.5 by default) is loaded, so a request can load several skills, one, or none. Illustrative request: review PR 182 for breaking API changes. Before the main agent starts, Jev asks one yes-or-no question per configured skill: would this skill's guidance help with this request? Selected (probability at or above skills_threshold, 0.5 by default): the skill's full text is appended to this run's system prompt, and several skills can be selected. Skipped (below the threshold): left out of this run. Unavailable (no usable answer, for example a missing key, a provider error, or a skill too large to send): left out, and the run continues without it. Then the main agent starts with its own instructions plus the selected skills. No Jev output is shown.Each skill gets its own yes or noJev doesn't rank your skills or pick a single winner. It scores each skill on its own, and every skill that reaches the threshold is loaded, so one request can load several skills, one, or none.Pick a sample request to see four skills judged. Sharing a topic with the request isn't enough: a skill's guidance has to help with the work the request asks for. A request that asks for no work, such as a thank-you, loads no skills.Four skills, one request at a timeIllustrativeReview a PRRelease notesSchema changeSmall talkRequest“Add a nullable discount column to orders and write the migration.”Jev · System 2 decisionAsked once per skill: would its guidance help with this request?A skill loads at 50% or higher, the default threshold.code-review46%Reviewing a code change for bugs, missing tests, and risky edits.Skippedapi-compatibility21%Checking a change against a public API's contract.Skippedrelease-notes5%Turning merged changes into short, customer-facing release notes.Skippedsql-migrations95%Writing and verifying a reversible database schema migration.SelectedAdded to this run's instructionssql-migrationsSample probabilities are made up to show the rule; they are not real Jev output. Jev scores every skill again on every run.Set up skill preloadingThree steps: write each skill as a named document, add the skills to your JevAgent, then run it and check which skills were picked. Setting up skills never calls Jev; Jev needs a key only when a run starts.1Write each skill as a named documentGive each skill a unique name, a short description of the work it guides, and its full text. A source, such as the file it came from, is optional and only labels the skill.Named skillsPlain textLoad skills from filesPythonCopy1from pathlib import Path
2
3from vidbyte import SkillDocument
4
5# One Markdown file per skill, for example skills/code-review.md.
6SKILLS = {
7    "code-review": "Reviewing a code change for bugs, missing tests, and risky edits.",
8    "api-compatibility": "Checking a change against a public API's contract.",
9    "release-notes": "Turning merged changes into short, customer-facing release notes.",
10    "sql-migrations": "Writing and verifying a reversible database schema migration.",
11}
12
13skills = tuple(
14    SkillDocument(
15        name=name,
16        description=description,
17        text=Path(f"skills/{name}.md").read_text(encoding="utf-8"),
18        source=f"skills/{name}.md",
19    )
20    for name, description in SKILLS.items()
21)Plain text works too, but each piece gets a numbered name and the same generic description, so Jev judges it from its text alone and the results are harder to read.Pass plain textPythonCopy1from pathlib import Path
2
3# Each string becomes a skill named inline_skill_1, inline_skill_2, ...
4# with the same generic description, so Jev judges it from its text alone.
5skills = (
6    "When reviewing a change, read every edited function and its tests first.",
7    Path("skills/release-notes.md").read_text(encoding="utf-8"),
8)Describe the work, not the promiseJev judges each skill by the guidance it actually gives. A description such as “Reviewing a code change for bugs, missing tests, and risky edits” gives Jev something to compare. A skill that only claims to help with anything isn't picked unless its text gives concrete guidance for the request.2Add the skills to your JevAgentPass the skills in your agent settings. Jev runs through Vidbyte's managed option, so set your Vidbyte API key before a run. The threshold sets how sure Jev must be before a skill loads. The default is 0.5, and a skill exactly at the threshold loads.Turn on skill preloadingPythonCopy1from vidbyte import JevAgent, JevAgentSettings, JevAlignmentSettings, JevRuntimeSettings
2
3# Jev runs through Vidbyte's managed gateway, which reads your
4# Vidbyte API key (vb_live_...) from VIDBYTE_API_KEY.
5
6agent = JevAgent(
7    JevAgentSettings(
8        name="dev-assistant",
9        system_prompt="You help engineers review, ship, and document code changes.",
10        provider="openai",
11        model_name="gpt-4.1-mini",
12        alignment=JevAlignmentSettings(skills=skills),
13    ),
14    JevRuntimeSettings(
15        skills_threshold=0.5,  # the default; a skill loads at or above it
16    ),
17)3Run the agent and check which skills loadedAfter each run, the results list every skill in the order you gave them, with its status and Jev's probability. They never include the skill text.See which skills were pickedPythonCopy1reply = await agent.arun("Review PR 182 and check it doesn't break the public API.")
2
3for skill in agent.response.skills.results:
4    print(f"{skill.name:<18} {skill.status.value:<12} {skill.probability}")
5# code-review        selected     0.92   <- illustrative; Jev scores every run
6# api-compatibility  selected     0.88
7# release-notes      skipped      0.12
8# sql-migrations     skipped      0.07
9
10# Jev's token use for this run's skill check, for your own cost tracking.
11usage = agent.response.skills.usage
12if usage:
13    print(usage.input_tokens, usage.output_tokens)Read how Jev questions are writtenWhat your agent receivesSelected skills are added after your agent's own instructions, in the order you listed them, under one heading. Skipped and unavailable skills never appear.Your agent's instructions for this runCopyYou help engineers review, ship, and document code changes.

--- Caller-selected skill guidance for this request ---

<full text of skills/code-review.md>

---

<full text of skills/api-compatibility.md>The added text applies to this run only. The next request starts again from your original instructions, and Jev checks every skill again.Read each skill's resultEvery skill ends a run with one of three results, and only selected skills are loaded.What each skill result meansResultWhat happenedLoaded into the run?SelectedJev answered, and its probability was at or above your threshold.Yes, its full textSkippedJev answered, and its probability was below your threshold.NoUnavailableJev gave no usable answer: no key, a provider error, or a skill too large to send.NoA failed check doesn't stop the runSkills are optional guidance, so when Jev can't be reached, for example because no key is set, every skill is marked unavailable and your agent runs with its own instructions, without raising an error. Check the results after a run when your agent depends on a skill.Limits to plan aroundSkill preloading keeps your agent's instructions focused, but Jev still reads every skill on every run. Keep these limits in mind as your library grows.Every run checks again — Skills are picked per request, and nothing carries over to the next run.Jev reads every skill in full — Each check sends Jev the request plus each skill's name, description, source, and full text, so Jev's input grows with your whole library, not just the skills it picks. Skills are checked in parallel.Keep each skill under about 8,000 characters — A skill too large to send to Jev alongside the request is marked unavailable and never loaded; it is never cut short. The limit is lower when the request itself is long, or when the text uses many symbols or accented letters.Only your main agent gets skills — If a preflight question stops the run, or a specialist takes the request, no skills are checked and specialists never receive your skills. The results are then empty.Picked means relevant, not safe — Jev judges only whether a skill fits the request, not whether it is correct or safe, and a selected skill is added to your instructions as written. Only offer skills you trust. Nothing in a skill is run or fetched, and your agent keeps its own tools and permissions.Names must be unique — Each name identifies one result, so duplicates are rejected when you create the agent. Creating the agent never calls Jev.A design goal, not a measured resultThe aim is to cut wasted context-token use and leave more room for the task. This is a design goal, not a measured result. It does not guarantee fewer tokens, lower cost, or better answers on every task; results depend on your skills and your requests.Read how Jev usage is pricedLoading skills from other sources comes laterPulling skills from outside sources, such as GitHub URLs, Anthropic's Skills API, skills.sh, or other catalogs, is separate work and isn't available yet.For now, load each skill's text yourself, for example from a file in your repository as the setup example does, and pass it in as a named skill.Next stepsPreflight questionsThe up-front check that can stop a run before any skill is checked.Specialist routingHand requests to specialist agents; a specialist runs without your skills.Usage and pricingWhere Jev usage shows up and how to total a run's cost.JevAgentEvery Jev capability and its current status.

). I want to give users the ability to attach skills in the following way:

from skills.sh (think can be synced with npx commands), from github repos, from other popular skill providers  (think that antrhopic has an api key for this). Can you   explain the technical implementation for this?
````

**Prompt 2** (after the assistant's first design answer, which proposed loader classes the user would call themselves):

````text
few things: 1) can you make the skills for the JevAgent simply an array of skills, with each skill there should be a type and text option, of course if we choose github or skills.sh then there should be no text and simple a name options and other parameters for that type of skill. I dont want them to have to put in skill loadres and skill dataclasses, just the information in an array of dataclasses. Then under the hood we handle the actual SkillLoader class that retrieves/formats the settings of each skill. Also, for each different skill source explain the in-depth implementation ofthings that we have to do to actually implement it, and also, can you include some other skill providers that would be a good idea to add to this request?
````

**Prompt 3** (the `/spec-pipeline` invocation, after the assistant's second design answer):

````text
great, you can implement the 3 skill sources we talked about AND the localskill, and OpenAISkill. Make sure that for each type of skill we are handing the edge cases/failure modes of each skill in the way that they could go wrong in the spec and all throughout the implementation. Try to decompose the files for the skills into subclasses for each of  the different skill types. (want the actual  core skills code logic to go  inside of vidbyte-sdk/vidbyte/agents/skills). and then attach it/load it onto the JevAgent
````

## B. Handoff block and decision ledger (verbatim, if present)

No `## HANDOFF` block was produced. The last Re-entry card from the design conversation, verbatim:

````text
**Re-entry · jev-skill-sources**
Decided:
- `JevAlignmentSettings.skills` is a flat tuple of per-source entry dataclasses, each with a name and a read-only `type`. Plain strings still mean inline. `SkillDocument` becomes internal.
- An internal `SkillLoader` fetches entries inside the preload on the first run. One resolver per type gets all entries of that type. Successes and permanent failures are remembered on the agent; transient ones are retried.
- Results gain `reason` and `detail`. A skill that fails to load is `UNAVAILABLE` and the run continues. `TOO_LARGE` comes from the existing batching.
- skills.sh reads the npx-installed folder and checks `skills-lock.json`, with no network. GitHub resolves to a commit SHA, lists the tree once per repo and ref, then fetches each raw file.
- Anthropic downloads the version zip and reads only `SKILL.md`, in memory. `text` is always the body of `SKILL.md` only.

Open: check with real keys whether the Anthropic content endpoint accepts `latest` under the beta header, and what format OpenAI's content endpoint returns.

Needs you:
1. **Entry shape.** One class per source with a read-only `.type`, or a single `Skill(type=...)` class? Default: one class per source.
2. **Extra providers.** Which to include? Default: `LocalSkill`, `WellKnownSkill` and `OpenAISkill`; `VidbyteSkill` becomes a separate project.
3. **Skills too large for Jev to check (13 of 29 popular ones).** Leave them `UNAVAILABLE` with the reason `TOO_LARGE`, or have Jev judge them on name and description only, which would be a separate pull request changing the core? Default: leave them `UNAVAILABLE`.
````

The user's Prompt 3 answered these: (1) "decompose the files for the skills into subclasses for each of the different skill types" → one class per source, as subclasses; (2) "the 3 skill sources we talked about AND the localskill, and OpenAISkill" → skills.sh, GitHub, Anthropic, plus LocalSkill and OpenAISkill; **WellKnownSkill was not chosen**; (3) not answered → its default applies: oversized skills stay `UNAVAILABLE` with reason `TOO_LARGE`; no change to how Jev judges skills.

The user-facing usage sketch the assistant showed (the user replied "great" to it):

```python
alignment=JevAlignmentSettings(skills=(
    InlineSkill(name="house-review", description="Our PR review checklist.", text="Read every edited function and its tests first..."),
    SkillsShSkill(name="react-best-practices", source="vercel-labs/agent-skills"),
    GitHubSkill(name="webapp-testing", repo="anthropics/skills", ref="v1.2.0"),
    AnthropicSkill(name="release-notes", skill_id="skill_01AbCd..."),
))
```

Field table the assistant proposed (the user accepted it; LocalSkill and OpenAISkill rows were proposed as additions and Prompt 3 accepted them):

| Class (`type`) | Required | Optional | Where the text comes from |
|---|---|---|---|
| `InlineSkill` (`inline`) | name, description, text | none | the field itself; plain strings still work as a shortcut |
| `LocalSkill` (`local`) | name, path | none | `<path>/SKILL.md` on disk |
| `SkillsShSkill` (`skills_sh`) | name, source (`owner/repo`) | directory (default `.agents/skills`) | the copy `npx skills` installed |
| `GitHubSkill` (`github`) | name, repo | ref, path, token | GitHub REST API at a resolved commit |
| `AnthropicSkill` (`anthropic`) | name, skill_id | version (default `latest`), api_key | Anthropic Skills API zip |
| `OpenAISkill` (`openai`) | name, skill_id | version, api_key | OpenAI Skills API |

## C. Structured conversation notes

### Key decisions
- **Declarative entries, no user-facing loaders.** `JevAlignmentSettings.skills` takes a flat tuple of small frozen dataclasses, one class per source. Users never construct a loader or a `SkillDocument`. — The user said: "I dont want them to have to put in skill loadres and skill dataclasses, just the information in an array of dataclasses. Then under the hood we handle the actual SkillLoader class".
- **One class per source, as subclasses of a common base, each with a read-only `type` enum field.** — The user chose subclasses (Prompt 3). Reason given in the conversation: with one class per source, `GitHubSkill` simply has no `text` field, so wrong combinations are rejected while typing, and adding a source is a new class instead of editing a shared validation matrix. The `type` field keeps saved settings and dashboards able to see `"type": "github"`.
- **Sources in scope:** `InlineSkill` (today's behavior: name, description, text), `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill`. Plain strings keep working as an inline shortcut (today they become `inline_skill_<n>`).
- **Core skills logic lives in a new package `vidbyte/agents/skills/`** (user directive, Prompt 3). It does not exist at base `ba3e4ca5`. The user also asked for the files to be decomposed "into subclasses for each of the different skill types" — i.e. one resolver subclass (and file) per source under that package, plus the internal `SkillLoader` coordinator. The repo's placement rules still apply to the *records*: dataclasses in `vidbyte/lib/dataclasses/<domain>.py`, enums in `vidbyte/lib/enums/<domain>.py` (see Constraints).
- **Attach to JevAgent through the existing preload.** `JevSkillsPreload` (`vidbyte/agents/jev/alignment/skills.py`) calls the loader before it builds batches; the rest of the preload (concurrent Jev decisions, per-skill scoring, appending selected text) stays as it is.
- **Resolution happens inside the run, lazily, on the first run, and is remembered on the agent.** Not at agent construction (no network I/O in `__init__`; blocking I/O there would stall async apps and breaks the documented "creating the agent never calls Jev"). The loader lives as long as the `JevAgent`, so its cache does too. Long-running processes do not see upstream skill updates until restart — deliberate (stable system prompt).
- **What the cache remembers:** successes and permanent failures (not found, auth failed, invalid skill) are remembered for the agent's lifetime; transient failures (timeouts, connection errors, HTTP 429, 5xx, GitHub rate limit) are not remembered, so the next run retries. Reason: remembering a transient 503 hides the skill until restart; retrying a permanent 404 adds a network round trip to every run.
- **Fail-open at run time.** A skill that cannot be resolved becomes an `UNAVAILABLE` result and the run continues, consistent with the existing preload ("A failed check doesn't stop the run").
- **Every result explains itself.** `JevSkillResult` gains `reason` (a new enum, proposed `JevSkillUnavailableReason` with values `NOT_INSTALLED`, `NOT_FOUND`, `AUTH_FAILED`, `RATE_LIMITED`, `FETCH_FAILED`, `INVALID_SKILL`, `TOO_LARGE`, `DECISION_FAILED`) and `detail` (a human message telling the user how to fix it, e.g. "run `npx skills add vercel-labs/agent-skills --skill react-best-practices`"). `description` becomes `str | None` and is `None` only when the skill never loaded. Reason: once loading is under the hood, users can no longer see loader exceptions, so the failure needs a place to surface.
- **Every entry carries a user-chosen `name` known at construction**, so the existing duplicate-name check in `JevAlignmentSettings._normalized_skills` still runs when the agent is created, and results stay readable even when a fetch fails.
- **Loader interface groups by type.** The loader groups entries by `type` and hands each resolver *all* entries of its type at once (`resolve(specs) -> tuple[SkillResolution, ...]`), asking every source concurrently. Reason: GitHub shares one commit lookup and one tree listing per (repo, ref). Cache key = the entry dataclass itself (frozen slotted dataclasses are hashable).
- **`text` is always the body of `SKILL.md` only.** Frontmatter `name`/`description` go into the record's fields (they are already sent to Jev as separate fields; keeping frontmatter in `text` sends them twice and pushes more skills over the size limit). Supporting files (`references/`, `scripts/`) are never loaded. Skills whose body says "read references/x.md" degrade — documented limitation, not a bug.
- **Shared SKILL.md parser:** read as `utf-8-sig` (strip a Windows byte-order mark before looking for the opening `---`); frontmatter between `---` lines parsed with `yaml.safe_load` (PyYAML is already a dependency); `name` and `description` required non-blank; body after the closing `---`, untrimmed. Missing/malformed frontmatter → `INVALID_SKILL`.
- **Oversized skills stay `UNAVAILABLE`, now with reason `TOO_LARGE`.** The existing batching already marks a skill that fits in no batch; that case gets the `TOO_LARGE` reason. No change to how Jev judges skills (judging on name+description only was offered and NOT chosen).
- **`SkillDocument` becomes the internal resolved record** and leaves the public exports. Allowed because skill preloading is on SDK main (#698) but not in PyPI 0.2.1, so the public API can still change.
- **Secrets:** token/api_key fields use `field(repr=False)` like `JevAgentSettings.api_key`; keys are used only to fetch and never appear in `source`, results, or logs.

#### Per-source mechanics agreed in the conversation
- **InlineSkill(name, description, text):** identity resolution; `source="inline"`; no I/O.
- **LocalSkill(name, path):** reads `<path>/SKILL.md` from disk (any skill folder in the user's own repo, e.g. `skills/` or `.claude/skills/`); parses frontmatter; no lock-file check; no network. Relative paths resolve against the process working directory; a not-found result's `detail` includes the absolute path checked.
- **SkillsShSkill(name, source, directory=".agents/skills"):** no network; never runs `npx`; never calls the skills.sh REST API.
  - Developer workflow it relies on: `npx skills add vercel-labs/agent-skills --skill react-best-practices` writes `.agents/skills/react-best-practices/` (the canonical copy; agent folders such as `.claude/skills` are symlinks to it) and adds an entry to `skills-lock.json` at the project root. For production: commit `.agents/skills/` or run `npx skills experimental_install` (restores every skill in `skills-lock.json` into `.agents/skills/`, like `npm ci`). Sync: `npx skills update`.
  - Resolver: read `<directory>/<name>/SKILL.md`; if `skills-lock.json` exists (project root = the folder containing `.agents`), require `skills[name].source == spec.source`, else `INVALID_SKILL` naming both sources (catches a same-named skill installed from a fork). Missing folder → `NOT_INSTALLED` with `detail` containing the exact `npx skills add <source> --skill <name>` command and the absolute path checked. `source` label like `skills.sh:vercel-labs/agent-skills/react-best-practices@<computedHash first 12>`.
  - Symlinks (npx `link` mode) are followed by `Path`. A process running from a different working directory than the project (systemd, Docker WORKDIR, test runner) gets `NOT_INSTALLED` with the absolute path in `detail`.
  - Any GitHub-hosted skills.sh skill can also be loaded directly as `GitHubSkill(repo=..., name=...)` when shipping the folder is not possible.
- **GitHubSkill(name, repo, ref=None, path=None, token=None):** the resolver groups entries by `(repo, ref)`:
  1. If `ref` is not already a 40-character hex SHA: `GET https://api.github.com/repos/{owner}/{repo}/commits/{ref or HEAD}` with `Accept: application/vnd.github.sha` → commit SHA (put in `source`, so a moved `main` is visible).
  2. If `path` is not set: `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1` once per group; keep paths ending in `/<name>/SKILL.md`; the shallowest match wins (npx's shadowing rule); two matches at the same depth → `INVALID_SKILL` listing both and asking for `path`; a response with `truncated: true` → `INVALID_SKILL` asking for `path`.
  3. `GET /repos/{owner}/{repo}/contents/{path}/SKILL.md?ref={sha}` with `Accept: application/vnd.github.raw`, capped with `max_response_bytes`.
  - 404 → `NOT_FOUND` with detail "not found, or private: set GITHUB_TOKEN" (GitHub returns 404 for private repos without a token). 403 with header `x-ratelimit-remaining: 0` → `RATE_LIMITED` (transient). Token: entry `token` field, falling back to env `GITHUB_TOKEN`. Unauthenticated limit is 60 calls/hour/IP; grouping makes 5 skills from one repo cost 7 calls instead of 15. `source` like `github:anthropics/skills@<sha12>/skills/pdf/SKILL.md`.
- **AnthropicSkill(name, skill_id, version="latest", api_key=None):**
  1. `GET https://api.anthropic.com/v1/skills/{skill_id}/versions/{version}/content` with headers `x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-beta: skills-2025-10-02` → a zip archive.
  2. If the content endpoint does not accept `latest`, first `GET /v1/skills/{skill_id}` and use `latest_version_id`. (Unverified: with the beta header, versions are addressed by an epoch timestamp such as `1759178010641129`.)
  3. Open the zip in memory (stdlib `zipfile`); find `SKILL.md` at the archive root or inside the single top-level folder (Anthropic upload rule); check the member's declared size before reading (zip-bomb guard; uploads can be up to 30 MB uncompressed); never extract to disk.
  - 401/403 → `AUTH_FAILED` (permanent); 404 → `NOT_FOUND`; 429/5xx → transient. Key: `api_key` field, falling back to env `ANTHROPIC_API_KEY` — a separate key from Jev's `VIDBYTE_API_KEY`. `source` like `anthropic:{skill_id}@{version}`. Custom skills are workspace-scoped (visible to the whole Anthropic workspace).
  - Anthropic's prebuilt `pdf`/`docx`/`pptx`/`xlsx` skills drive Python scripts inside Anthropic's code-execution container; their text alone tells a non-Claude agent to run scripts it doesn't have. The same files are in the public `anthropics/skills` GitHub repo.
- **OpenAISkill(name, skill_id, version, api_key=None):** mirrors Anthropic and reuses the same zip reading: `GET https://api.openai.com/v1/skills/{skill_id}/versions/{version}/content` (listed in OpenAI's API reference as "Retrieve Skill Version Content"; the reference sidebar also lists a "Retrieve skill content" endpoint for the default version). Auth `Authorization: Bearer` with `OPENAI_API_KEY` fallback. OpenAI bundle rules: exactly one `SKILL.md`/`skill.md` (matched case-insensitively), under one top-level folder; max 500 files and 25 MB uncompressed. `skill_reference.version` accepts an integer or `"latest"`. Response format of the content endpoint (zip vs JSON) is **unverified**. OpenAI also has first-party skills such as `openai-spreadsheets` (shell-tool oriented).

### Rejected alternatives
- **Loader classes the user calls themselves** (`SkillDirectoryLoader().load(...)`, `GitHubSkillLoader().load(...)`, the assistant's first proposal) — the user rejected this in Prompt 2.
- **One `Skill(type=..., ...)` class with every field** — it can only reject wrong combinations (e.g. `text` on a GitHub skill) at run time; the user chose subclasses.
- **Fetching when the agent is created** — blocking network I/O in `__init__` stalls async apps and breaks "creating the agent never makes calls".
- **Running `npx` from the SDK** — adds a Node 22 runtime dependency, network access, and telemetry (on by default) to a Python library; also violates the "no CLI behaviour in the SDK" rule.
- **The skills.sh REST API** (`GET https://skills.sh/api/v1/skills/{source}/{skill}` returns files + a SHA-256 hash) — it authenticates with a Vercel OIDC token that only apps deployed on Vercel (or linked with the Vercel CLI) can get.
- **Remote fetch inside `SkillsShSkill`** — the same entry would load different text depending on whether an installed copy exists on that machine.
- **One GitHub API call per entry** — burns the 60-calls-per-hour unauthenticated limit.
- **GitHub tarball endpoint** — one call regardless of skill count, but downloads the whole repo (runner-up only if many skills are loaded without a token).
- **Native provider attachment** (Anthropic `container.skills`, OpenAI shell-tool `skill_reference`) — works only when the main model is that vendor's model with code execution, and bypasses Jev's selection.
- **Judging oversized skills on name+description only** — a separate change to the core preload; offered as Q3 and not chosen.
- **WellKnownSkill** (`/.well-known/agent-skills/index.json` discovery draft), **VidbyteSkill** (dashboard-managed skills; needs backend work), **PackageSkill** (skills inside installed Python packages), **GitLab / generic git URL** — discussed as candidates; not requested in Prompt 3. Do not build.
- **`vidbyte-jev-skills`** (YAML decision templates) is a different concept from guidance-text skills and is not a source for this feature.

### Constraints and assumptions
- **No CLI commands in the SDK.** The owner removed `vidbyte-sdk coding run` right after it merged; never add or offer SDK CLI commands (the existing `skills` command group stays as is).
- **No scope additions.** Build only what the conversation agreed (plus what a repo rule or gate forces). Risks with no agreed control become stated limitations or optional questions defaulting to "not built".
- **Existing preload invariants stay true** (from the `JevSkillsPreload` file header): do not execute, fetch, or interpret commands from a skill body; do not interpolate caller names, descriptions, sources, or text into Jev instructions; one missing answer or failed batch must not erase another candidate's valid answer; do not catch cancellation or arbitrary programming errors as provider failures; skill text is never stored in `JevAgent.response`.
- **Jev request bounds** (`vidbyte/lib/constants/jev.py`): at most 60,000 bytes per request and 30,000 bytes for state plus the largest question; with Jev's long question text the practical limit is roughly 8,000–8,800 characters per skill.
- **Measured community skill sizes** (2026-10-11): in `anthropics/skills`, 11 of 20 `SKILL.md` files are over 8,000 bytes (e.g. `pptx` 20,796; `skill-creator` 33,168; `claude-api` 105,146; `frontend-design` 9,390; `pdf` 8,072); in `vercel-labs/agent-skills`, 4 of 9 (e.g. `deploy-to-vercel` 11,786; `vercel-optimize` 17,311). Both repos use the `skills/<name>/SKILL.md` layout. Many imported skills will therefore end up `TOO_LARGE`.
- **Skill preloading is unreleased:** on SDK main via #698, not in PyPI 0.2.1; public API changes are free now and breaking later. A docs PR (#677, in the separate `vidbyte` website repo) documents `SkillDocument`; it is outside this repository.
- **Assumption:** a `JevAgent` instance is used one run at a time (JevRuntime restores its per-run fields in a `finally` block). If concurrent runs on one instance are supported, two simultaneous first runs would fetch twice.
- **Assumption:** the first run pays the resolution latency; a hanging upstream adds up to timeout × attempts to that run, then the run continues without the skill.
- Development host is Windows (Git Bash).

### Clarifications and answers
- Q: one class per source with a read-only `.type`, or a single `Skill(type=...)` class? — A: "Try to decompose the files for the skills into subclasses for each of the different skill types."
- Q: which extra providers? — A: "implement the 3 skill sources we talked about AND the localskill, and OpenAISkill" (the three = skills.sh, GitHub, Anthropic).
- Q: oversized skills? — no answer; default applies: leave them `UNAVAILABLE` with reason `TOO_LARGE`.
- Q: where does the code go? — A: "want the actual core skills code logic to go inside of vidbyte-sdk/vidbyte/agents/skills".
- Earlier question "Anthropic: explicit IDs or list the workspace?" — moot: each `AnthropicSkill` entry carries its own `skill_id`; no workspace listing.

### Terminology
- **skill entry / spec** — the user-facing dataclass that says where a skill comes from (`GitHubSkill`, `LocalSkill`, …).
- **resolve / load** — turn an entry into the internal `SkillDocument` (name, description, text, source).
- **SkillLoader** — the internal coordinator the user named: groups entries by type, calls each source's resolver, remembers results.
- **resolver** — one subclass per source that knows how to fetch and read that source.
- **SKILL.md** — the Agent Skills format: YAML frontmatter (`name`, `description`) followed by a Markdown body.
- **skills.sh** — Vercel's open agent-skills directory; `npx skills` is its CLI (source: github.com/vercel-labs/skills).
- **Jev** — Vidbyte's decision model; **JevAgent** — the agent that uses Jev to pick skills before its main loop.
- **transient vs permanent failure** — transient: may succeed on retry (timeout, connection error, 429, 5xx, rate limit); permanent: will not (404, 401/403, malformed skill, lock-file mismatch).

### Implementation hints
- Existing code the change builds on (paths at base `ba3e4ca5`):
  - `vidbyte/lib/dataclasses/skills.py` — `SkillDocument(name, description, text, source=None)`, frozen, validates non-blank strings, never trims text.
  - `vidbyte/agents/jev/alignment/skills.py` — `JevSkillsPreload.run()` builds per-skill `UNAVAILABLE` results, `_build_batches` (a skill too large to send alone joins no batch), concurrent `DecisionModelHelper(...).arun`, `_score_skill`, `_append_selected` (appends `JEV_SKILLS_PROMPT_SECTION` + selected texts joined by `\n\n---\n\n`).
  - `vidbyte/agents/jev/settings.py` — `JevAlignmentSettings(skills: tuple[SkillDocument | str, ...])` with `_normalized_skills()` (strings → `inline_skill_<n>`, duplicate names → `ConfigurationError`).
  - `vidbyte/lib/dataclasses/jev.py` — `JevSkillResult(name, description, source, status, probability=None)` (around line 3728; validates non-blank description), `JevSkillsOutcome`, `JevSkillBatch`.
  - `vidbyte/lib/enums/jev.py` — `JevSkillStatus` (`SELECTED`, `SKIPPED`, `UNAVAILABLE`).
  - `vidbyte/lib/constants/jev.py` — `JEV_SKILL_INDEX_BASE`, `JEV_SKILLS_MAX_REQUEST_JSON_BYTES`, `JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES`, `JEV_SKILLS_PROMPT_SECTION`.
  - `vidbyte/lib/http/transport.py` — `HttpTransport.request(...)` (async; `timeout_seconds`, `retry_count`, backoff, `max_response_bytes`, `follow_redirects`; `HttpResponse.raw_bytes`) and `SyncHttpTransport` (`request`, `request_bytes`). AGENTS.md principle 5 names `HttpTransport` as the canonical request helper.
  - `vidbyte/lib/enums/skills.py` and `vidbyte/skills/catalog.py` — the packaged Vidbyte skill catalog (a different concept: distributable skill assets read via `importlib.resources`); avoid name confusion with the new package.
  - `vidbyte/lib/config/loader.py` — `YamlLoader` with a duplicate-key-safe YAML loader (private).
  - Tests: `tests/test_jev_skill_preload.py`; verification script `scripts/test-jev-skills-preload.py`; feature pack `tests/features/jev_skills_preload/FEATURE.md`; agent skill doc `skills/jev-agent/SKILL.md`.
  - Public API: `vidbyte/__init__.py` exports; `contracts/sdk-public-api.json` (regenerate with `scripts/generate-sdk-public-api.py`).
  - `REPO_MAP.md` — File Index and JEV File Locations; a new package needs an entry.
- `npx skills` facts (read from github.com/vercel-labs/skills source): canonical project dir `<project>/.agents/skills/<name>/` (`getCanonicalSkillsDir` in `src/installer.ts`); global `~/.agents/skills`; `skills-lock.json` at the project root (`src/local-lock.ts`): `{ "version": 1, "skills": { "<name>": { "source", "sourceUrl"?, "ref"?, "sourceType", "skillPath"?, "version"?, "via"?, "computedHash", ... } } }`, sorted, timestamp-free; the CLI treats a lock with `version < 1`, missing `skills`, or unparsable content (e.g. merge-conflict markers) as empty. `npx skills experimental_install` = `runInstallFromLock` (restores into `.agents/skills/`). Frontmatter requires `name` (lowercase, hyphens) and `description`.
- Anthropic SKILL.md constraints: `name` ≤ 64 chars, lowercase letters/numbers/hyphens, no "anthropic"/"claude"; `description` ≤ 1024 chars, no XML tags.
- Sources consulted in the conversation: skills.sh API docs (https://skills.sh/docs/api), skills.sh CLI docs (https://skills.sh/docs/cli), github.com/vercel-labs/skills, Anthropic List Skills (https://platform.claude.com/docs/en/api/beta/skills/list), Anthropic Download Skill Version Content (https://platform.claude.com/docs/en/api/beta/skills/versions/download), OpenAI Skills guide (https://developers.openai.com/api/docs/guides/tools-skills), OpenAI skill version content reference (https://developers.openai.com/api/reference/cli/resources/skills/subresources/versions/subresources/content).

### Open questions
- Does Anthropic's content endpoint accept `latest` under the `skills-2025-10-02` beta header, or must the resolver first read `latest_version_id`? (Needs a real key; design must handle both.)
- What does OpenAI's version-content endpoint return (zip bytes or JSON), and does it accept `"latest"`? What is the path of OpenAI's default-version "Retrieve skill content" endpoint? (Unverified.)
- Exact base-class name and module layout inside `vidbyte/agents/skills/`, reconciled with the placement rules (records in `lib/dataclasses`, enums in `lib/enums`, constants in `lib/constants`).
- Where relative `LocalSkill.path` / `SkillsShSkill.directory` resolve (process working directory was the conversation's default).
- Timeout and retry constants for resolution, and the size caps (raw `SKILL.md` cap, zip archive cap, zip member cap).
- Whether `OpenAISkill.version` defaults to `"latest"` (the table left its default unstated).

## D. Weighted words

- "can you make the skills for the JevAgent simply an array of skills, with each skill there should be a type and text option" — Prompt 2
- "of course if we choose github or skills.sh then there should be no text and simple a name options and other parameters for that type of skill" — Prompt 2
- "I dont want them to have to put in skill loadres and skill dataclasses, just the information in an array of dataclasses." — Prompt 2
- "Then under the hood we handle the actual SkillLoader class that retrieves/formats the settings of each skill." — Prompt 2
- "Make sure that for each type of skill we are handing the edge cases/failure modes of each skill in the way that they could go wrong in the spec and all throughout the implementation." — Prompt 3
- "Try to decompose the files for the skills into subclasses for each of  the different skill types." — Prompt 3
- "(want the actual  core skills code logic to go  inside of vidbyte-sdk/vidbyte/agents/skills)" — Prompt 3
- "and then attach it/load it onto the JevAgent" — Prompt 3

Existing invariants stated in the docs page the user pasted (Prompt 1), which the change must keep true:
- "Setting up skills never calls Jev; Jev needs a key only when a run starts." / "Creating the agent never calls Jev."
- "A skill too large to send to Jev alongside the request is marked unavailable and never loaded; it is never cut short."
- "Nothing in a skill is run or fetched, and your agent keeps its own tools and permissions."
- "Names must be unique — Each name identifies one result, so duplicates are rejected when you create the agent."
- "After each run, the results list every skill in the order you gave them … They never include the skill text."
- "Skills are optional guidance, so when Jev can't be reached … every skill is marked unavailable and your agent runs with its own instructions, without raising an error."
- "Only your main agent gets skills — If a preflight question stops the run, or a specialist takes the request, no skills are checked and specialists never receive your skills."
