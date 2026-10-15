## Spec ready: Public skill loader: resolve every #904 skill source without JevAgent (SDK 0.3.1)
`C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader/docs/spec/public-skill-loader/spec.md` · r3 · grounded at `c9d31a7f` · review: two rounds (SOUND WITH FIXES both times), 11 findings applied

**In one breath:** The code that turns a skill entry into skill text exists, but it is private, so only JevAgent can use it and vidbyte-cli cannot. This PR makes the existing loader public instead of writing a second one: `SkillLoader`, `SkillResolution` and `ConfigurationError` become root exports. A small new record checks the loader's input before anything is read. The one change you didn't pick: the version goes to **0.3.1, not 0.2.2**, because SDK main released 0.3.0 to PyPI half an hour after this run started.

**How a developer will use it:**
```python
import asyncio

from vidbyte import ConfigurationError, InlineSkill, LocalSkill, SkillLoader

entries = (
    InlineSkill(name="house-review", description="Our review checklist.", text="Read the tests first.\n"),
    LocalSkill(name="pdf", path="no-such-folder/pdf"),
)
loader = SkillLoader(entries)  # a tuple or a list; reads no file, key, or URL
resolutions = asyncio.run(loader.load())  # inside a running loop: await loader.load()
for entry, resolution in zip(entries, resolutions, strict=True):
    if resolution.document is not None:
        print(entry.name, "loaded", len(resolution.document.text.encode("utf-8")), "bytes")
    else:
        print(entry.name, resolution.reason.value, resolution.transient)

try:
    SkillLoader((entries[0], entries[0]))
except ConfigurationError as error:
    print("rejected:", error.details["names"])
```

### Open questions, decided by default
1. **Q-8**: Which version? SDK main released 0.3.0 at 15:34 (tag `v0.3.0`, now the latest on PyPI), so 0.2.2 on main would lower main's version. CLI main also already pins `>=0.3.0,<0.4`. *Going with:* **0.3.1** on a branch rebased onto current main. Interrupt to override, for example with "0.2.2 on a new release/0.2.x branch".
2. **Q-1**: Root-export `ConfigurationError`, so the CLI can catch a bad skill entry by name? Every entry constructor raises it, and the CLI may import only root names. *Going with:* yes, built.

### Optional additions the review suggested, not built
- **Q-2**: a synchronous `load_sync()`. Risk it would close: a caller with no event loop. *Going with:* not built; `asyncio.run(loader.load())` does the job.
- **Q-3**: a caller byte limit on the loader. Risk it would close: the CLI's 20,000-byte budget. *Going with:* not built; the CLI measures `document.text` itself and reports its own structured failure.
- **Q-4**: a parser for `github:owner/repo/path`, `skills.sh:<id>` and local paths. *Going with:* not built; the CLI builds entry objects itself.
- **Q-5**: a release note at `docs/design/release-0-3-1.md` (each of the last three bumps added one). *Going with:* not built; no gate requires it.
- **Q-6**: a loader-level credential parameter. *Going with:* not built; `token=` and `api_key=` already exist on each entry.
- **Q-7**: rewording "next run" and "create a new agent" for callers that load once. *Going with:* not built.
- **Q-9**: having JevAgent's settings reuse the new record for its duplicate-name rule. *Going with:* not built; it would change JevAgent's error message. A test keeps the two copies of the rule in step instead.

### What will be built, step by step
1. **The loader checks its input before reading anything.** A new frozen record, `SkillEntries`, rejects text, non-collections, non-entries and repeated names with `ConfigurationError`. A list is turned into a tuple first (`vidbyte/lib/dataclasses/skills.py`, `vidbyte/agents/skills/loader.py`).
2. **Three new root exports:** `SkillLoader`, `SkillResolution` and `ConfigurationError` are added to `vidbyte/__init__.py` and `__all__`.
3. **JevAgent is untouched.** All 296 existing loader constructions still pass, and both entry points reject a repeated name with the same details.
4. **0.3.1 everywhere.** The version changes in eight hand-edited literals (pyproject, `__version__`, CLI fallback, MCP server default, MCP clientInfo, README, llms.txt, bug template).
5. **Docs say the door is public.** The skills README, the package header, the loader header and REPO_MAP no longer call JevAgent the only consumer, or say the constructor only stores its input.
6. **Regenerated contract.** `contracts/sdk-public-api.json` is regenerated in its own commit after the source commit, with the three names and 0.3.1, and `--check` passes.

### What we're deliberately NOT doing
- No `skills` field on `Agent`/`BaseAgent`, because it is out of scope.
- No PyPI publish, tag or merge. That is your call after review.
- No vidbyte-cli change. The CLI is only the consumer.
- No Jev relevance selection on the public path. The public loader resolves what it is given.
- No change to any cap, timeout, retry, reason or detail string. There is one loader and one set of rules.
- No 0.2.x maintenance branch.

### What could go wrong, and what the design does about it
- **A skill can't be loaded** (missing folder, bad key, rate limit, network error, too large): the result for that entry carries a `SkillUnavailableReason` and a detail. The other entries still load and nothing is raised. Guarded by the loader's existing result model (G-2).
- **A skill is bigger than the CLI's 20,000-byte budget:** the SDK caps a SKILL.md at 1 MiB (whole file) and reports `too_large` beyond that, never truncating. The CLI measures the returned text against its own budget (D-7).
- **Bad input** (a string, two skills with the same name): `SkillLoader(...)` raises `ConfigurationError` with fixed `details` keys before any I/O. Secrets and the rejected value are never echoed (INV-2/INV-3).
- **GitHub rate limit:** an unpinned `GitHubSkill` with no path costs 3 requests on each fresh loader, about 20 commands an hour anonymously. Pinning a full SHA and a path costs 1 request, and a token raises the limit. This is documented for the CLI (EC-27).

### Assumptions I made (interrupt to correct)
- **A-1**: The CLI can `await` the loader or use `asyncio.run(...)` from command setup.
- **A-2**: The CLI uses each skill name once per run, the same rule as JevAgent.
- **A-3**: The CLI budgets against `document.text` (the body after the frontmatter).
- **A-9**: Nothing else releases 0.3.1 before this PR merges.

---
**Next:** building now. S2 to S6 run unattended: tests, then implementation, adversarial review, repair until green, and the PR. Interrupt with a correction at any point and I will revise the spec before the next stage.
