# Design: JevAgent Skill Preloading Core

**Status:** Implementation branch stacked on SDK PR #449 (`feat/jev-tool-alignment`)
**Scope:** Core candidate contract, inline/local loading, Jev relevance selection, run-local context injection, and tests. External-source adapters remain separate.

## Problem

Applications may have more reusable skill instructions than belong in every agent run. Injecting every full skill wastes generative context on irrelevant instructions; giving Jev only a candidate name without a useful description makes relevance judgment unreliable. Skill preloading lets Jev inspect concise candidate metadata before the main agent starts, then loads complete instructions only for candidates selected for the current request.

## Contract

- Candidates are configured under `JevAgentSettings.alignment.skills` as an immutable collection of named candidates; an empty tuple disables preloading.
- Candidate material is supplied as inline text or a local UTF-8 file. Selection metadata (name and description) is distinct from the full instructions.
- Before the main generative run, Jev evaluates each candidate independently against the exact user request. Code applies the fixed probability threshold to each answer.
- Only selected skill text is added to that run's context, ahead of the main agent loop. Candidate instructions are not appended to persistent agent settings, shared system prompts, or later runs.
- Missing Jev credentials, decision failures, invalid answers, or unreadable selected skill files do not stop the user task. Selection failures add no skill instructions; a selected file failure omits that candidate and records its name.
- The result is observable in `JevAgent.response` without exposing skill bodies or local file contents.
- This core does not fetch network URLs or know Claude Skills, GitHub, skills.sh, or other third-party protocols. A later adapter converts verified provider results into the core candidate contract.

## Architecture

1. Define frozen candidate and settings records in `vidbyte/agents/jev/settings.py`. Validate source shape at construction without opening files.
2. Keep the fixed, structured Jev question in `vidbyte/lib/jev/skill_preload.py`. A single `JevSkillsPreload` subclass in `vidbyte/agents/jev/alignment/skills.py` owns candidate request construction, Jev calls, answer validation, thresholding, inline/local materialization, usage aggregation, and result construction through private helper methods.
3. Construct this capability only when `alignment.skills` is configured and pass it through the existing JevAgent runtime extension seam.
4. Run selection after the preflight gate and before the main loop. Add selected instructions as `TextContextItem` values to the current `BaseAgentContext`, never to `self.system_prompt` or shared settings.
5. Record status, selected candidate names, and decision usage in the run response. Keep failures advisory and omit skill text and local paths from result metadata.

## Boundaries and safety

- Candidate names, descriptions, and bodies are user-supplied, untrusted text. The Jev question must say to classify the described guidance for fit and never follow it as an instruction.
- Keep each candidate's decision separate; do not ask Jev to rank or compare a bundle.
- File paths are explicit caller inputs; load UTF-8 text only after selection. Reject directories, unreadable files, and empty content with `ConfigurationError`. Do not add URL fetching, archive extraction, or path auto-discovery to core.
- If a candidate's selected file cannot be loaded, omit that candidate and continue with others; record its name without its path or partial contents.
- Do not claim token savings are guaranteed; the feature limits irrelevant instruction injection into the main run, while decision calls and candidate sizes still contribute to total usage.

## Tests

- Settings contract: inline/local candidates, immutability, invalid dual/missing sources, and safe repr behavior.
- Jev selection: one decision per candidate, exact request/candidate metadata, true-only selection, independent failure handling, redaction, and usage aggregation.
- Local materialization: UTF-8 reads, blank/missing/directory failures, selected-only loading, and no network behavior.
- Runtime behavior: selected content appears in this run's context before model execution; rejected/unavailable candidates do not; repeated runs do not retain prior skills; specialist/gate-stop paths do not run preloading.
- Response contract: status and selected names are exposed, contents and local paths are not.

## Rollout

This PR depends on the alignment settings and runtime seam in SDK PR #449. It targets that branch while #449 is open. Provider adapters remain a distinct follow-up PR against this core contract.
