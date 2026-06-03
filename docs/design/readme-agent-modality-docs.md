# Design Doc: README Agent Modality Docs

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-02
**Last Updated:** 2026-06-02

---

## 1. Overview

Update the project README so the public agent examples match the current SDK behavior: developers should pass plain string prompts to agents, and execution modality should be detected automatically from configured model names such as `gpt-image-1`. `AgentInput` remains available for advanced per-call context and metadata, but the README should no longer teach it as the normal way to select image or video execution.

---

## 2. Goals & Non-Goals

### Goals

- Make the README's "Agents and Modalities" section describe model-name-based automatic modality detection.
- Remove explicit `ModelModality.IMAGE` from the primary image-agent example.
- Remove the primary "typed input with modality" example that implies `AgentInput` is required for image execution.
- Keep `AgentInput` documented only where it is actually useful today: advanced per-call context and metadata.
- Update the custom `BaseAgent` example so it does not pass `ModelModality.TEXT` for ordinary text use.
- Add a lightweight verification script that checks the README does not regress to the stale modality guidance.

### Non-Goals

- No runtime code changes.
- No changes to `BaseAgent`, `ModalityDetector`, runner routing, providers, or public exports.
- No semantic prompt-intent classifier that guesses image or video modality from prompt text.
- No removal or deprecation of `AgentInput`.
- No live provider calls, credential changes, packaging changes, or release automation.

---

## 3. Background & Context

The current README says, "Pick a modality explicitly when the request is not ordinary text; plain string prompts default to text." That is stale relative to the implementation. `BaseAgent.__init__()` defaults `modality` to `ModelModality.AUTO`, `generate_reply()` resolves call/input/default modality and then detects from `runner_config.model_name`, and tests already verify that a plain string sent to an agent configured with `model_name="gpt-image-1"` routes to the image runner.

Relevant audited files:

- `pyproject.toml` defines a Python 3.11 package named `vidbyte-sdk` and uses `README.md` as the package readme.
- `README.md` contains the stale examples under "Agents and Modalities" and "Multi-Agent Orchestration".
- `vidbyte/client.py` exposes `VidbyteSDK`, whose `agents` namespace is backed by `AgentClient`.
- `vidbyte/agents/client.py` exposes `AgentClient.base(**kwargs) -> BaseAgent`.
- `vidbyte/agents/base.py` owns public agent construction and execution, including `modality=ModelModality.AUTO`, `run()`, `arun()`, and model-name-based modality detection.
- `vidbyte/lib/agents/modality_detector.py` maps model names and patterns to text, image, video, audio, and embedding modalities.
- `tests/test_agent_modality_routing.py` already covers model-name auto-detection, plain-string text fallback, typed input overrides, and detector behavior.
- `scripts/` contains feature verification scripts named `test-<feature>.py`, which matches the design-doc workflow.

The working tree currently contains many modified and untracked `__pycache__` files unrelated to this change. Those must not be reverted as part of this work.

---

## 4. Requirements

### Functional Requirements

1. The README must state that agents infer execution modality from the configured model when possible.
2. The README must show image generation with `sdk.agents.base(..., model_name="gpt-image-1")` and a plain `run("...")` string call.
3. The primary image example must not import or pass `ModelModality`.
4. The README must not say plain string prompts default to text without qualifying that configured model names can route to non-text modalities.
5. The README must not present `AgentInput(..., modality=...)` as the normal way to run image or video agents.
6. The README must preserve `AgentInput` for advanced per-call context examples because current code supports `context_items` and `context_manager` through `AgentInput`.
7. The custom `BaseAgent` text example must omit explicit `modality=ModelModality.TEXT`.
8. The README must preserve the current warning that semantic labels such as roles belong in agent metadata when callers need them.
9. The verification script must fail if stale phrases or imports return to the primary README sections.
10. The verification script must pass without network access or provider credentials.

### Non-Functional Requirements

- Performance: N/A - documentation-only change.
- Scalability: N/A - documentation-only change.
- Security: No secrets or real API keys may be added to examples.
- Observability: N/A - no runtime behavior changes.
- Reliability: README language must avoid implying semantic prompt classification exists.
- Compatibility: Examples must use public imports already exported by `vidbyte.__all__`.
- Maintainability: The verification script should use straightforward README substring checks so future failures identify the stale guidance clearly.

---

## 5. High-Level Design

This is a documentation correction grounded in existing runtime behavior. The implementation will update only the README's agent guidance and add a script-level regression check required by the design-doc workflow. No SDK code, test fixtures, package metadata, or runtime contracts will change.

The README will describe automatic modality detection as model-configuration-based routing: if an agent is configured with an image model, a plain string prompt routes to the image runner; if the modality remains unresolved, the existing implementation falls back to text. This wording keeps the developer experience simple without promising semantic prompt classification.

```text
README example
  |
  v
sdk.agents.base(provider="openai", model_name="gpt-image-1")
  |
  v
agent.run("A clean product mockup on a white desk")
  |
  v
Existing BaseAgent / ModalityDetector implementation routes by model name
```

---

## 6. Detailed Design

### 6.1 README Agent Modality Guidance

**File(s):** `README.md`
**Type:** Modified

#### What it does

Updates the public usage prose and examples so the documented agent path is plain strings plus automatic model-name modality routing.

#### Interface / API

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()

image_agent = sdk.agents.base(
    name="asset-generator",
    system_prompt="Create useful product assets.",
    provider="openai",
    model_name="gpt-image-1",
)

reply = image_agent.run("A clean product mockup on a white desk")
print(reply.content)
```

#### Logic / Algorithm

1. Replace the stale first paragraph under "Agents and Modalities" with wording that says agents infer modality from configured model names when possible.
2. State explicitly that callers normally pass plain strings to `run()` and `arun()`.
3. Mention the conservative fallback: unresolved modality stays text, and prompt text is not semantically classified.
4. Remove `ModelModality` import and `modality=ModelModality.IMAGE` from the image example.
5. Delete the primary typed-input modality override example.
6. Update the custom `BaseAgent` text example to import only `BaseAgent` and omit `modality=ModelModality.TEXT`.
7. Keep the later per-call context section using `AgentInput`, but frame it as advanced context/metadata rather than modality selection.

#### Edge Cases & Error Handling

- If future model names are unknown, README language must still be true because the code falls back to text.
- If a developer needs an explicit override, it remains supported but should not be taught as the default path in the README.
- The examples must not imply live provider calls can run without configured credentials.

---

### 6.2 README Verification Script

**File(s):** `scripts/test-readme-agent-modality-docs.py`
**Type:** New file

#### What it does

Adds a deterministic local verification script that checks the README contains the new public guidance and no longer contains the stale primary modality examples.

#### Interface / API

```python
class ReadmeAgentModalityDocsVerifier:
    def run(self) -> int:
        # Runs all README checks, prints PASS/FAIL lines, and returns a process exit code.
```

#### Logic / Algorithm

1. Read `README.md` as UTF-8 text.
2. Run named checks for required new snippets.
3. Run named checks for removed stale snippets.
4. Print `PASS` or `FAIL` for every check.
5. Print `X/Y tests passed`.
6. Exit with status `0` only if every check passes.

#### Edge Cases & Error Handling

- Missing `README.md` should produce a failed check and non-zero exit.
- Empty README should produce failed required-snippet checks and non-zero exit.
- Stale phrases in the primary guidance should produce failed checks even if the new example is also present.

---

### 6.3 Design Doc

**File(s):** `docs/design/readme-agent-modality-docs.md`
**Type:** New file

#### What it does

Records the approved scope, requirements, test plan, rollout, and rollback procedure for the README update.

#### Interface / API

```markdown
# Design Doc: README Agent Modality Docs
```

#### Logic / Algorithm

1. Use the repository's design-doc template sections in order.
2. Define the documentation-only implementation scope.
3. List every file that will be created or modified.
4. Provide verification checks that satisfy the required testing categories.

#### Edge Cases & Error Handling

- If implementation differs from this document after approval, the deviation must be called out in the handoff.

---

## 7. Data Model Changes

N/A - documentation-only change with no schema, dataclass, persistence, migration, or serialized data impact.

---

## 8. API Changes

N/A - no public API, endpoint, method signature, enum, export, provider, runner, or CLI behavior changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/readme-agent-modality-docs.md` | Design-doc workflow source of truth for the README update |
| MODIFY | `README.md` | Align public agent modality examples with existing automatic model-name detection behavior |
| CREATE | `scripts/test-readme-agent-modality-docs.py` | Required verification script for README regression checks |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] `ReadmeAgentModalityDocsVerifier` -> `empty README content fails required-snippet checks`: verifies an empty readme cannot pass because the new guidance is absent.
- [Hidden Failure] `ReadmeAgentModalityDocsVerifier` -> `missing README path exits non-zero`: verifies the script does not silently pass when the documentation file cannot be read.
- [Silent Failure] `ReadmeAgentModalityDocsVerifier` -> `stale primary phrase is rejected`: verifies the old phrase "Pick a modality explicitly when the request is not ordinary text; plain string prompts default to text." cannot remain while appearing correct.
- [Hidden Assumption] `ReadmeAgentModalityDocsVerifier` -> `README must not require AgentInput for image execution`: verifies the primary modality section does not assume developers wrap image prompts in `AgentInput`.
- [Silent Failure] `ReadmeAgentModalityDocsVerifier` -> `image example omits explicit ModelModality import`: verifies the example does not accidentally keep `from vidbyte import ModelModality, VidbyteSDK`.
- [Silent Failure] `ReadmeAgentModalityDocsVerifier` -> `image example omits modality keyword`: verifies the example does not include `modality=ModelModality.IMAGE`.
- [Hidden Assumption] `ReadmeAgentModalityDocsVerifier` -> `automatic wording is model-name based`: verifies the README includes wording that automatic modality detection comes from configured model names, not prompt semantics.
- [Edge Case] `ReadmeAgentModalityDocsVerifier` -> `AgentInput remains documented for context`: verifies the advanced per-call context section still includes `AgentInput`, so the docs do not overcorrect by removing a supported advanced API.

### Integration Tests

- [Silent Failure] Run `python scripts/test-readme-agent-modality-docs.py` from the repository root and verify every README regression check prints `PASS`.
- [Hidden Assumption] Run `python -m unittest tests.test_agent_modality_routing.AgentModalityRoutingTests.test_model_name_auto_detection_routes_to_image` to confirm the README's automatic image example is backed by existing runtime behavior.
- [Hidden Assumption] Run `python -m unittest tests.test_agent_modality_routing.AgentModalityRoutingTests.test_plain_string_defaults_to_text_runner` to confirm README wording about conservative unresolved fallback remains accurate.
- [Hidden Failure] Run `python -m compileall vidbyte` to confirm no accidental runtime syntax changes were introduced.

### Manual / QA Test Cases

1. [Silent Failure] Given the updated README, when a developer reads "Agents and Modalities", then the first image example should use `VidbyteSDK`, `model_name="gpt-image-1"`, and a plain string prompt.
2. [Hidden Assumption] Given the updated README, when a developer looks for prompt-intent routing, then they should not find language promising semantic classification from prompt text.
3. [Edge Case] Given the updated README, when a developer needs per-call context, then they can still find the `AgentInput(..., context_items=...)` example.
4. [Hidden Failure] Given the updated README, when package rendering uses `pyproject.toml`'s `readme = "README.md"`, then the README should remain valid Markdown with fenced Python snippets.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` from `pyproject.toml` | Run verification script and existing tests | Low; already required by the package |
| Standard library `unittest` | Python bundled | Existing routing test verification | Low; existing test suite already uses it |
| External provider APIs | N/A | Not used | None; no network calls should occur |

---

## 12. Rollout & Deployment

- Feature flags: N/A - documentation-only change.
- Breaking change: No. Runtime behavior and public APIs are unchanged.
- Migration path: Developers following the README can remove explicit `ModelModality` arguments for model-name-detectable agents.
- Deployment order: Merge README and verification script together.
- Rollback procedure: Revert the README and script commits. No data or runtime rollback is required.

---

## 13. Open Questions

- [ ] Should the README mention that `generate_reply(..., modality="image")` remains available as an advanced explicit override, or should it avoid modality overrides entirely in the short public README?
- [ ] Should future docs add ergonomic keyword alternatives for `AgentInput` context, such as `agent.arun("...", context_items=(...))`, or is that out of scope until runtime API changes are approved?

---

## 14. Alternatives Considered

### Alternative 1: Only update README without a verification script

- What: Modify `README.md` and rely on human review.
- Why rejected: The design-doc workflow requires a script that runs the Section 10 test cases. A small README verifier also prevents this exact stale guidance from returning.

### Alternative 2: Change runtime API so strings carry per-call metadata and context

- What: Add `metadata=`, `context_items=`, and `context_manager=` keyword arguments to `arun()` and `run()` so `AgentInput` can disappear from user-facing docs entirely.
- Why rejected: The user asked to update the README based on behavior that already exists. Runtime API expansion should be a separate design because it changes `BaseAgent` contracts and tests.

### Alternative 3: Add semantic prompt-intent modality detection

- What: Classify prompts like "make an image" and route to image models automatically even when the configured model is text or unknown.
- Why rejected: That would require model selection, provider capability handling, credential expectations, and clearer cost semantics. The current reliable behavior is model-name-based routing, and the README should not overpromise beyond that.
