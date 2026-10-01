# Design: JevAgent Skill Preloading Core

**Status:** Implementation branch stacked on open SDK PR #449 (`feat/jev-tool-alignment`)  
**Scope:** Core candidate contract, inline/local loading, Jev relevance selection, run-local context injection, and tests. External-source adapters are explicitly excluded and belong in a separate PR.

## Problem

Applications may have more reusable skill instructions than belong in every agent run. Injecting every full skill wastes generative context on irrelevant instructions; giving Jev only a candidate name without a useful description makes relevance judgment unreliable. Skill preloading should let Jev inspect concise candidate metadata before the main agent starts, then load complete instructions only for candidates selected for the current request.

## Contract

- Candidates are configured under `JevAgentSettings.alignment.skills` as a non-empty immutable collection of named skill candidates.
- Core candidate material may be supplied as inline text or a local UTF-8 file. Candidate selection metadata (name and description) is distinct from the full instructions.
- Before the main generative run, Jev evaluates each candidate independently against the exact user request. The selection question follows `skills/asking-jev-questions/SKILL.md`; Jev recognizes a supplied definition and code applies a named probability threshold.
- Only selected skill text is added to that run's context, ahead of the main agent loop. Candidate instructions are not appended to persistent agent settings, shared system prompts, or later runs.
- Missing Jev credentials, decision failures, invalid answers, or unreadable selected skill files do not stop the user task. Preloading fails closed for context injection: no candidate instructions are added when the selection pass cannot be trusted. The ordinary agent run proceeds.
- The result is observable in `JevAgent.response` without exposing skill bodies or local file contents.
- This core PR does not fetch network URLs or know Claude Skills, GitHub, skills.sh, or other third-party protocols. A later adapter PR converts verified provider results into the core candidate contract.

## Architecture

1. Add frozen candidate/settings records to `vidbyte/agents/jev/settings.py`; normalize and validate sources at construction without opening files.
2. Add `JevSkillsPreload` as a `JevAgentAlignment` subclass in a sibling alignment module. It builds per-candidate Jev requests and returns loaded selected text plus a typed status record. It delegates source-independent materialization to a small loader in a separate core module; remote retrieval is not part of that loader.
3. Construct this capability only when `alignment.skills` is configured and pass it through the existing JevAgent runtime extension seam.
4. Run selection after the existing preflight gate and before the main loop. Add selected instructions as `TextContextItem` values to the current `BaseAgentContext`, never to `self.system_prompt` or shared settings.
5. Record status, selected candidate names, and decision usage in the run response. Keep failures advisory and avoid putting skill text into result metadata.

## Boundaries and safety

- Candidate names/descriptions and skill bodies are user-supplied, untrusted text. The Jev instructions must explicitly say to classify the described instructions for fit and never follow them as instructions.
- Keep each candidate's decision separate; do not ask Jev to rank or compare a bundle.
- File paths are explicit caller inputs; source loading reads UTF-8 text only. Reject directories, unreadable files, empty content, and paths that are not regular files with `ConfigurationError` at load time. Do not add URL fetching, archive extraction, or path auto-discovery to core.
- If a candidate's selected file cannot be loaded, omit that candidate and continue with the others; record the failed candidate name without including its path or partial contents.
- Do not claim token savings are guaranteed; the feature limits irrelevant instruction injection into the main run, while decision calls and candidate sizes still contribute to total usage.

## Tests

- Settings contract: inline/local candidate validation, immutability, invalid dual/missing sources, and safe repr behavior.
- Loader unit tests: UTF-8 reads, blank/missing/directory failures, and no network behavior.
- Jev selection tests: one decision per candidate, exact request/candidate metadata, true-only selection, independent failure handling, and no skill body in Jev state.
- Runtime acceptance tests: selected content appears in this run's context before model execution; rejected/unavailable candidates do not; repeated runs do not retain prior skills; specialist/gate-stop paths do not run preloading.
- Response contract tests: status and selected names are exposed, contents and local paths are not.
- Third-party adapters and live provider calls are omitted from this PR because they are separate, independently verifiable integrations.

## Rollout

This PR depends on the alignment settings and runtime seam in SDK PR #449. It must target that branch while #449 is open, then be retargeted to `main` after #449 merges. Do not describe the core API as part of a released package until the code merges and ships. Provider adapters remain a distinct follow-up PR against this core contract.
