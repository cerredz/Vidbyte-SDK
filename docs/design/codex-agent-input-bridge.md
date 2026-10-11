# Design Doc: Codex Agent Input Bridge

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`CodexHarnessAgent.arun()` and `.run()` accept only `CodexRunInput`, while every other agent in the SDK accepts `str | AgentInput`. That mismatch means no existing composition surface — pipelines, workflows, multi-agent handoff, agent-as-tool — can call a Codex agent, because they all construct `str` or `AgentInput` and pass it along. This change adds one Vidbyte-abstraction translation, `AgentInput` to `CodexRunInput`, and widens the two entry points to accept the generic types, so a `CodexHarnessAgent` becomes callable through the SDK's shared agent input contract without changing anything about how native Codex input works.

---

## 2. Goals & Non-Goals

### Goals

- Accept `str`, `AgentInput`, and `CodexRunInput` at `CodexHarnessAgent.arun()` and `.run()`.
- Translate every `AgentInput` field — `prompt`, `metadata`, `context_items`, `context_manager` — onto its exact `CodexRunInput` counterpart with no loss.
- Keep the translation on the existing Vidbyte-abstraction translator (`CodexVidbyteTranslator`), not on the dataclass and not in a new module.
- Classify a failed input translation through the existing Codex failure vocabulary rather than leaking a raw `ConfigurationError`.
- Leave every existing `CodexRunInput` call path byte-for-byte unchanged.

### Non-Goals

- Media input. `AgentInput` has no media field, so native `CodexImageInput`, `CodexLocalImageInput`, `CodexSkillInput`, and `CodexMentionInput` stay reachable only through an explicit `CodexRunInput`. Designing a media bridge is roadmap task V01's separate half.
- `CodexContextPlacement` through the generic path. Placements are a Codex-specific anchor concept with no `AgentInput` counterpart; a caller who needs them constructs `CodexRunInput` directly.
- Registering `CodexHarnessAgent` in pipelines, workflows, or the YAML loader. This change makes the call contract compatible; wiring each composition surface is roadmap tasks V02 and V03.
- Declaring `BaseAgent` compatibility or inheriting from it. `docs/design/codex-harness-agent.md` §13 rejected that deliberately and this change does not revisit it.

---

## 3. Background & Context

`CodexHarnessAgent` (`vidbyte/agents/codex/agent.py`) landed in PR #409 and #411 as a facade over a Codex-owned agent loop. It deliberately does not subclass `BaseAgent`, because Codex owns its own model/tool iteration and inheriting would expose methods whose documented semantics the adapter cannot honor.

The consequence is that the class has no shared call contract with the rest of the SDK. `BaseAgent.run()` is declared as `def run(self, message: str | AgentInput, **options: Any) -> AgentMessage` (`vidbyte/agents/base.py:741`). `CodexHarnessAgent.arun()` is declared as `async def arun(self, request: CodexRunInput) -> AgentMessage` (`vidbyte/agents/codex/agent.py:64`). Any caller holding a `str` or an `AgentInput` gets a `ConfigurationError` from `CodexRunInput.__post_init__`, or more commonly never gets that far because the call site passes the wrong type entirely.

`skills/codex-harness-roadmap/references/checklist.md` tracks this as **V01** ("Bridge generic AgentInput") and **C05** ("Define shared agent contracts"), and lists both in delivery wave 5. Its translation map notes that main's `AgentInput` carries prompt, metadata, context items, and `ContextManager` only, and that media requires a separately defined bridge — which is why media is a non-goal here.

The relevant constraint on placement comes from the project field guide entry *Class-Bound Helpers → "Separate shared abstraction translation from provider serialization"* (PR #408 comments r3937530519 and r3937536632): a harness adapter uses a constructor-time Vidbyte translator to resolve shared abstractions, a separate content translator for SDK arguments, and operation collaborators for lifecycle work. `AgentInput` is a shared Vidbyte abstraction, so its translation belongs on `CodexVidbyteTranslator`.

---

## 4. Requirements

### Functional Requirements

1. `CodexHarnessAgent.arun()` accepts `str | AgentInput | CodexRunInput` and returns `AgentMessage` unchanged in every case.
2. `CodexHarnessAgent.run()` accepts the same union and preserves its existing active-event-loop guard.
3. A `str` input produces a `CodexRunInput` holding exactly one `CodexTextInput` with that text, `recipient="user"`, and empty metadata, context items, and placements.
4. An `AgentInput` input produces a `CodexRunInput` whose single `CodexTextInput` carries `AgentInput.prompt`, whose `metadata` is a copy of `AgentInput.metadata`, whose `context_items` is `AgentInput.context_items`, and whose `context_manager` is the same object identity as `AgentInput.context_manager`.
5. A `CodexRunInput` input is passed through as the identical object, with no copy and no re-validation.
6. Context-manager identity is preserved through the bridge, because `CodexContextTranslator._sources` distinguishes one source from two by object identity (`translation.context_manager is request.context_manager`), not by equality.
7. An input that cannot be translated — an empty or whitespace-only prompt, a non-mapping `metadata`, a context item without `to_context_text` — raises `CodexAgentError` with `failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED` and `operation="translate_input"`, chaining the original exception as `__cause__`.
8. An unsupported input type (for example `None`, an `int`, or a list) raises the same classified `CodexAgentError` rather than `TypeError` or `AttributeError`.
9. The translation happens before any Codex process starts, so an invalid input performs zero native calls.
10. `CodexVidbyteTranslator.translate_input()` is a public, annotated method on the existing translator class and is covered by the module's `__all__` surface through that class.

### Non-Functional Requirements

- **Performance:** the bridge is one dataclass construction per turn, with no I/O and no copying of context registries. `AgentInput.context_items` is already an immutable tuple and is reused, not rebuilt.
- **Scalability:** N/A — this is a per-call type conversion with no shared state, no growth, and no persistence.
- **Security:** no new external input surface, no credential handling, no subprocess. Metadata is copied into a plain dict exactly as `CodexRunInput.__post_init__` already requires; nothing new is logged.
- **Observability:** a failed translation is classified through the existing `FailureCode` vocabulary with a specific `operation` value, so a failure in the bridge is distinguishable in diagnostics from a failure in `translate_agent` or `translate_context`.
- **Reliability:** the bridge cannot partially apply. It either returns a fully validated `CodexRunInput` or raises before the transport is touched.

---

## 5. High-Level Design

The change has two parts and touches two existing files. No new module, no new class, no new dataclass.

First, `CodexVidbyteTranslator` (`vidbyte/agents/codex/config.py`) gains a `translate_input()` method. That class already exists for exactly this job — its docstring reads "Translates Vidbyte abstractions before any Codex process starts" — and it already owns `translate_agent`, `output_schema`, `system_prompt`, and `additional_context`. Adding the input translation there keeps every Vidbyte-to-Codex mapping inspectable in one place, which is what the field guide's *separate shared abstraction translation from provider serialization* entry asks for. The method dispatches on the input's type: a `CodexRunInput` returns unchanged, a `str` becomes a single-text request, and an `AgentInput` maps field by field.

Second, `CodexHarnessAgent.arun()` and `.run()` widen their parameter type to `str | AgentInput | CodexRunInput` and call the translator once, at the top of `arun`, before the existing context translation. The agent already holds the translator instance as `self._vidbyte` from construction, so no new state is introduced. The translation is wrapped in the same `try`/`except` shape the method already uses for `translate_context`, producing a `CodexAgentError` with `operation="translate_input"`.

The placement decision worth recording is why this is *not* a classmethod on `CodexRunInput` alongside the existing `CodexRunInput.text()`. `AgentInput` lives in `vidbyte/lib/dataclasses/agents.py`, and that module already imports `CodexMessageData` from `vidbyte/lib/dataclasses/codex.py` under `TYPE_CHECKING` because `AgentMessage` carries a `codex` field. A runtime import in the other direction would put a real edge into a module pair that currently has only a type-only one, for no benefit. Keeping the conversion in the orchestration layer, which may freely import `vidbyte.lib`, avoids that entirely and matches where every other Vidbyte-abstraction translation for this adapter already lives.

```
caller (pipeline / workflow / handoff / direct)
   |
   |  str | AgentInput | CodexRunInput
   v
CodexHarnessAgent.arun()
   |
   |-- CodexVidbyteTranslator.translate_input()   <- NEW: Vidbyte -> Codex request
   |        (str -> CodexRunInput.text)
   |        (AgentInput -> CodexRunInput fields)
   |        (CodexRunInput -> passthrough)
   v
CodexContextTranslator.translate()                <- unchanged
   v
CodexTransport.run()                              <- unchanged
   v
CodexResultTranslator.translate() -> AgentMessage <- unchanged
```

---

## 6. Detailed Design

### 6.1 CodexVidbyteTranslator input translation

**File(s):** `vidbyte/agents/codex/config.py`
**Type:** Modified

#### What it does

Converts any supported Vidbyte agent input into the single typed request the rest of the Codex adapter consumes, before any provider process starts.

#### Interface / API

```python
class CodexVidbyteTranslator:
    """Translates Vidbyte abstractions before any Codex process starts."""

    @staticmethod
    def translate_input(value: CodexAgentInput) -> CodexRunInput: ...
```

One flat function, per PR #412 review comment [r3952586662](https://github.com/cerredz/Vidbyte-SDK/pull/412#discussion_r3952586662). The three branches are short enough that a private `_from_agent_input` helper only split the dispatch across two call sites. It is a `@staticmethod` because no branch reads instance state, matching `system_prompt` and `additional_context` on the same class.

`CodexAgentInput` is a module-level type alias declared in `vidbyte/lib/dataclasses/codex.py`, immediately after `CodexRunInput` because it references that class:

```python
CodexAgentInput = str | AgentInput | CodexRunInput
```

#### Logic / Algorithm

1. If `value` is a `CodexRunInput`, return it unchanged. Identity passthrough, not a copy — a caller that built native image, skill, or mention items keeps them.
2. If `value` is a `str`, return `CodexRunInput.text(value)`, reusing the existing convenience constructor so the recipient default lives in exactly one place.
3. If `value` is an `AgentInput`, construct `CodexRunInput` inline with a single `CodexTextInput(value.prompt)`, copying `metadata`, `context_items`, and `context_manager` across.
4. Otherwise raise `ConfigurationError` naming the received type, which the agent's caller converts into a classified `CodexAgentError`.

The dispatch is an ordered `isinstance` chain rather than a dict lookup because the branches are three, the types are unrelated classes, and `CodexRunInput` must be checked before any structural test.

#### Edge Cases & Error Handling

- **Empty or whitespace-only prompt.** `CodexTextInput.__post_init__` calls `_require_text`, which raises `ConfigurationError`. The bridge does not pre-check; it lets the existing validator own the rule so there is exactly one definition of "valid text input."
- **`None` or an unsupported type.** Explicit `ConfigurationError` naming the type, so the caller sees a configuration failure rather than an `AttributeError` from duck-typed field access.
- **`metadata` that is not a mapping.** `CodexRunInput.__post_init__` already rejects it; the bridge does not duplicate the check.
- **`context_items` containing an object without `to_context_text`.** Same — `CodexRunInput.__post_init__` owns it.
- **`context_manager` present.** Passed by identity so `CodexContextTranslator._sources` can correctly collapse an agent-level and request-level manager into one source when they are the same object.

### 6.1a CodexContextTranslator ContextManager translation

**File(s):** `vidbyte/agents/codex/context.py`, `vidbyte/lib/dataclasses/codex.py`
**Type:** Modified

#### What it does

Translates every `ContextManager` surface that a Codex turn can carry, with one function per translated surface. Added in response to PR #412 review comment [r3952591325](https://github.com/cerredz/Vidbyte-SDK/pull/412#discussion_r3952591325), which asked whether more of `ContextManager` could be translated and for the translations to be modular.

#### Audit of the ContextManager surface

| Surface | Status before this change |
| --- | --- |
| Registry primitives in the context zone (`render_primitives_zone()`) | Translated to `developer_context` |
| Conversation-placed primitives (`render_conversation_messages()`, both placements) | Translated to `before_input` / `after_input` |
| Unmanaged items (`items()`) | Translated to prefix text |
| Anchored primitives (`get_by_id`, `placement_for`, `registry_items`) | Translated to `insertions` |
| **`metadata`** | **Dropped** |
| `by_kind()`, `recite()`, `set_frozen()`, mutators | Not translations — queries, mutators, or already covered by the rendered result |
| `to_context()` | Adds no information for Codex beyond `items()` text, because Codex has no `BaseContext` slot for `file_paths`, `artifacts`, `responses`, `tool_calls`, `memory`, `budget`, or `permissions` — except its `metadata` merge, which is the gap above |

`ContextManager.metadata` was the one piece of manager state no Codex turn ever saw. On the generic agent path it reaches provider metadata through `ContextManager.to_context()`. Codex builds no `BaseContext`, so a caller who set `ContextManager(metadata=...)` silently lost it for the whole turn.

#### Interface / API

```python
class CodexContextTranslator:
    @classmethod
    def _render_conversation(
        cls, manager: ContextManager, placement: ContextWindowPlacement
    ) -> tuple[CodexTextInput, ...]: ...

    @classmethod
    def _render_unmanaged_items(cls, manager: ContextManager) -> tuple[CodexTextInput, ...]: ...

    @classmethod
    def _render_insertions(
        cls,
        manager: ContextManager,
        placements: tuple[CodexContextPlacement, ...],
        items: tuple[CodexInputItem, ...],
    ) -> tuple[CodexContextInsertion, ...]: ...

    @staticmethod
    def _render_metadata(manager: ContextManager) -> Mapping[str, Any]: ...

    @staticmethod
    def _merge_metadata(
        rendered: tuple[CodexRenderedContext, ...], request_metadata: Mapping[str, Any]
    ) -> dict[str, Any]: ...
```

`CodexRenderedContext` gains one field so a rendered source carries its own metadata alongside its text:

```python
metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. `_render_manager` reads each translated surface through its own function instead of inline expressions, so translating a further surface adds one function rather than another inline branch.
2. Placement-scoped surfaces (`developer_context`, conversation placements) read the *remaining* view from `_remaining_manager`, which excludes anchored primitives. Whole-manager surfaces (unmanaged items, metadata) read the caller's manager, because the remaining view is a fresh `ContextManager` that carries neither.
3. `_render_metadata` returns a plain `dict` copy, so a rendered snapshot never aliases the caller's mapping.
4. `_merge_metadata` merges sources in render order, then applies `CodexRunInput.metadata` last. `_sources` orders the agent-scoped manager before the request-scoped one, so a request-scoped manager overrides the agent-scoped one, and per-turn input metadata — the most specific signal — wins outright. This mirrors `to_context()` (manager over base) and `AgentRuntime` (input metadata last).

#### Edge Cases & Error Handling

- **Shared manager at both scopes.** `_sources` already collapses it to one source by object identity, so its metadata is contributed once, not merged with itself.
- **No manager.** `_render_manager` returns a default `CodexRenderedContext`, whose `metadata` defaults to an empty dict, so `_merge_metadata` is a no-op for that source.
- **Manager with empty metadata.** Turn metadata is unchanged, which keeps every existing `CodexRunInput` call path byte-for-byte identical.
- **Caller mutation.** `_render_metadata` copies, so mutating the resulting turn metadata cannot reach back into the caller's manager.
- **Evaluation order.** `_render_insertions` now runs after zone rendering rather than before it. Rendering raises nothing for valid primitives, so a missing-primitive or missing-anchor `ConfigurationError` still surfaces from the same turn, before transport.

### 6.2 CodexHarnessAgent entry points

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### What it does

Widens the public call contract and performs the input translation once, before context translation and before the transport is touched.

#### Interface / API

```python
class CodexHarnessAgent:
    async def arun(self, request: CodexAgentInput) -> AgentMessage: ...
    def run(self, request: CodexAgentInput) -> AgentMessage: ...
```

#### Logic / Algorithm

1. `arun` calls `self._vidbyte.translate_input(request)` inside a `try`, converting any exception into `CodexAgentError(failure_code=FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED, operation="translate_input")` with `from exc`.
2. The resulting `CodexRunInput` is passed to the existing `CodexContextTranslator.translate(...)` call exactly as the parameter was before.
3. Everything downstream — transport, thread id assignment, result translation, history append — is untouched.
4. `run` widens its annotation only. Its event-loop guard and its delegation to `asyncio.run(self.arun(...))` are unchanged, so the sync path inherits the bridge for free.

#### Edge Cases & Error Handling

- **Translation failure leaves no partial state.** The call happens before `self.thread_id`, `self.history`, `self.last_prompt`, and `self.last_reply` are read or written, so a rejected input cannot leave the agent half-updated.
- **Zero native calls on failure.** The transport is only reached after both translations succeed, satisfying functional requirement 9.
- **Cancellation.** `asyncio.CancelledError` raised inside the translator would be caught by a bare `except Exception`, but `CancelledError` inherits from `BaseException` in Python 3.8+, so it propagates correctly and cancellation semantics are preserved. This matches the existing `translate_context` guard in the same method.

---

## 7. Data Model Changes

N/A - no persisted records, no database, and no migration. One module-level type alias, `CodexAgentInput`, is added to `vidbyte/lib/dataclasses/codex.py`; it is a typing construct with no runtime instances and no serialized form.

---

## 8. API Changes

N/A - no HTTP endpoints in this package. The public Python surface change is two widened parameter annotations and one new translator method, all additive and backward compatible: every existing `CodexRunInput` call site continues to type-check and behave identically.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-agent-input-bridge.md` | This design document |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | Add the `CodexAgentInput` union alias next to `CodexInputItem`; add `CodexRenderedContext.metadata` |
| MODIFY | `vidbyte/agents/codex/config.py` | Add `CodexVidbyteTranslator.translate_input()` as one flat static method |
| MODIFY | `vidbyte/agents/codex/agent.py` | Widen `arun`/`run` annotations; translate input before context translation |
| MODIFY | `vidbyte/agents/codex/context.py` | One `_render_*` function per translated `ContextManager` surface; translate manager metadata onto the turn |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export `CodexAgentInput` |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export `CodexAgentInput` on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export `CodexAgentInput` for public-export integrity (S015) |
| CREATE | `tests/test_codex_agent_input_bridge.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-agent-input-bridge.py` | Phase 5 verification script |

Totals: 3 create, 7 modify, 0 delete.

---

## 10. Testing Plan

All tests run offline. `CodexVidbyteTranslator` performs no provider I/O, so the entire bridge is verifiable without `openai-codex` installed — which matters because the transport's `_load_sdk` raises `CODEX_SDK_UNAVAILABLE` when the optional extra is absent.

### Unit Tests

- `translate_input` -> `returns the identical CodexRunInput object when given one` — [Silent Failure] — an accidental `replace()` or reconstruction would drop native image/skill/mention items while still returning a valid-looking request; asserts `result is request`.
- `translate_input` -> `converts a plain string into one CodexTextInput with recipient user` — [Edge Case]
- `translate_input` -> `converts AgentInput prompt into exactly one text item` — [Edge Case]
- `translate_input` -> `copies AgentInput metadata into the request` — [Silent Failure] — a dropped metadata dict still produces a runnable turn but loses caller correlation data.
- `translate_input` -> `preserves AgentInput context_items in order` — [Silent Failure] — reordered or truncated context items produce a plausible but wrong prompt.
- `translate_input` -> `preserves context_manager object identity, not equality` — [Hidden Assumption] — `CodexContextTranslator._sources` collapses two sources into one via `is`; a copied manager would silently render every primitive twice.
- `translate_input` -> `raises ConfigurationError for an empty prompt string` — [Edge Case]
- `translate_input` -> `raises ConfigurationError for a whitespace-only prompt` — [Edge Case]
- `translate_input` -> `raises ConfigurationError for None` — [Hidden Assumption] — the implementation must not assume a non-null input.
- `translate_input` -> `raises ConfigurationError for an int` — [Hidden Assumption]
- `translate_input` -> `raises ConfigurationError for a list of CodexTextInput` — [Hidden Assumption] — a caller who passes items directly instead of a request must fail loudly, not silently produce an empty turn.
- `arun` -> `raises CodexAgentError with operation translate_input for an invalid input` — [Hidden Failure] — an unwrapped `ConfigurationError` would escape the adapter's failure vocabulary and bypass any caller routing on `FailureCode`.
- `arun` -> `chains the original exception as __cause__` — [Hidden Failure] — losing the cause makes an invalid-input failure indistinguishable from a translator bug.
- `arun` -> `makes zero transport calls when input translation fails` — [Hidden Failure] — asserts against a fake transport whose `run` records invocations; a translation performed after thread start would strand a native thread.
- `arun` -> `leaves history, last_prompt, last_reply, and thread_id unchanged after a failed translation` — [Silent Failure] — partial mutation would make the next turn resume from a corrupted facade state.
- `run` -> `accepts a plain string through the synchronous path` — [Edge Case]
- `run` -> `still raises CodexAgentError inside an active event loop` — [Hidden Assumption] — confirms the widened annotation did not disturb the existing `run_sync_guard`.
- `CodexContextTranslator.translate` -> `manager metadata reaches the translated turn` — [Silent Failure] — this was the dropped surface; a turn ran normally while losing every key the caller set on the manager.
- `CodexContextTranslator.translate` -> `absent manager metadata leaves turn metadata empty` — [Edge Case] — guards the requirement that existing `CodexRunInput` paths stay byte-for-byte unchanged.
- `CodexContextTranslator.translate` -> `per-turn input metadata overrides manager metadata` — [Hidden Assumption] — the merge order must match `AgentRuntime`, where input metadata is applied last.
- `CodexContextTranslator.translate` -> `request-scoped manager overrides the agent-scoped manager` — [Hidden Assumption] — depends on `_sources` render order; a reversed merge would let stale agent-level metadata win.
- `CodexContextTranslator.translate` -> `a shared manager contributes its metadata once` — [Silent Failure] — the identity-collapse path must not merge a manager with itself.
- `CodexContextTranslator.translate` -> `translating metadata does not mutate the caller manager` — [Silent Failure] — returning the caller's mapping by reference would let one turn's merge leak into the next.

### Integration Tests

The end-to-end flow to prove is: generic input at `arun` produces the same `AgentMessage` as the equivalent explicit `CodexRunInput`. `CodexTransport` is replaced with a fake returning a fixed `CodexRunResult`, because the real one spawns a Codex app-server process. `CodexVidbyteTranslator`, `CodexContextTranslator`, and `CodexResultTranslator` are all real — the point is to prove the seams line up, and mocking them would test nothing.

- `arun("prompt")` and `arun(CodexRunInput.text("prompt"))` produce byte-identical `AgentMessage` content, metadata, and `codex` payloads.
- `arun(AgentInput(prompt=..., context_manager=manager))` renders the manager's primitives exactly once when the same manager is also on the agent's settings — the identity-collapse path in `CodexContextTranslator._sources`. This is the silent failure unit tests cannot catch, because it only appears when both scopes hold the manager.
- `arun(AgentInput(prompt=..., context_items=(item,)))` places the item's rendered text in the prompt prefix, proving `context_items` survives both translations rather than only the first.
- `arun("p")` on an agent whose settings carry `ContextManager(metadata=...)` puts those keys on the reply metadata, proving manager metadata survives the context translator, the result translator, and the metadata merge in `CodexResultTranslator`.
- `arun(AgentInput(prompt=..., context_manager=manager))` does the same for a request-scoped manager, and a per-turn `AgentInput.metadata` key still wins over the manager's.

The hidden assumption the integration surfaces: the bridge assumes `CodexContextTranslator` treats a bridged request exactly like a hand-built one. Only running both through the real translator proves it.

### Manual / QA Test Cases

1. Given a `CodexHarnessAgent` with no `openai-codex` installed, when `arun("")` is called, then a `CodexAgentError` with `codex.vidbyte_translation_failed` is raised and no `codex.sdk_unavailable` error appears — proving translation precedes SDK loading. — [Edge Case]
2. Given a `CodexHarnessAgent`, when `run(AgentInput(prompt="hi", metadata={"trace": "x"}))` is called from synchronous code, then the returned `AgentMessage.metadata` contains `trace="x"` alongside the adapter's own `provider` key. — [Silent Failure]
3. Given an existing script that calls `arun(CodexRunInput(items=(CodexTextInput("a"), CodexImageInput("data:image/png;base64,..."))))`, when it runs after this change, then behavior is identical to before — the passthrough branch preserves multi-item native input. — [Hidden Assumption]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Only reached after translation; not required by any test in this change | None added — the bridge runs entirely before `_load_sdk` |
| Existing dev tooling | Pinned in `pyproject.toml` | `python scripts/run_ci.py`, `python lint/run.py` | Pre-existing environment drift only |

No dependency additions.

---

## 12. Rollout & Deployment

No feature flag. This is a purely additive, backward-compatible widening of two public annotations: every existing `CodexRunInput` caller keeps working unchanged, so there is no migration path to document and no breaking change to stage.

Deployment is a normal package release; there is no service, no ordering constraint, and no data to migrate. Rollback is a revert of this branch's commits, which restores the narrower annotation without leaving any persisted state behind.

One sequencing note for the reviewer: this is the first of five independent Codex-translation PRs, each branched from `origin/main` and each touching `vidbyte/agents/codex/agent.py`. They are reviewable independently but should be **merged in numbered order** (this one first) to keep the conflicts in `agent.py` trivial.

---

## 13. Open Questions

- [ ] Should `CodexHarnessAgent` eventually declare a shared agent `Protocol` (roadmap C05) so composition surfaces can type-check against it rather than against `BaseAgent`? This change makes the call contract compatible but does not declare a protocol.
- [ ] Should a future media bridge extend `AgentInput` with a media field, or stay a Codex-only path through explicit `CodexRunInput`? Recorded as a non-goal here; roadmap V01 leaves it open.

---

## 14. Alternatives Considered

### Alternative 1: A `from_agent_input()` classmethod on `CodexRunInput`

- What: Put the conversion on the dataclass in `vidbyte/lib/dataclasses/codex.py`, next to the existing `CodexRunInput.text()` convenience constructor.
- Why rejected: It requires `vidbyte/lib/dataclasses/codex.py` to import `AgentInput` from `vidbyte/lib/dataclasses/agents.py` at runtime, while `agents.py` already imports `CodexMessageData` from `codex.py` under `TYPE_CHECKING`. That turns a type-only relationship into a real bidirectional one for no benefit. It also puts a Vidbyte-abstraction translation somewhere other than the class the field guide designates for it.

### Alternative 2: A new `CodexInputTranslator` collaborator module

- What: Add `vidbyte/agents/codex/input.py` mirroring `context.py` and `result.py`.
- Why rejected: A new module, file header, class, and export for one pure three-branch conversion with a single call site. `CodexVidbyteTranslator` already exists for exactly this concern and is already held by the agent. This is the smaller version that still fully solves the problem.

### Alternative 3: Overload `arun` with a separate `arun_agent_input()` method

- What: Keep `arun(CodexRunInput)` strict and add a second entry point for generic input.
- Why rejected: Composition surfaces call `run`/`arun` by name. A second method name is invisible to them, so it would not actually make the agent callable from a pipeline — it fails the stated goal while adding public surface.

### Alternative 4: Accept `**options` like `BaseAgent.run()`

- What: Match `BaseAgent.run(self, message, **options)` exactly.
- Why rejected: `BaseAgent`'s `options` configure a Vidbyte-owned loop that Codex does not have. Accepting and silently ignoring them would be the dishonest kind of compatibility this adapter was built to avoid. Per-turn overrides are roadmap task T04 and need a typed request, not a kwargs bag.
