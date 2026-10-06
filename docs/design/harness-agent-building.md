# Design Doc: Building Agents From a HarnessSpec

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-28
**Last Updated:** 2026-07-28
**Final path:** `docs/design/harness-agent-building.md`

---

## 1. Overview

`YamlLoader` can turn a *standalone agent document* into a live `BaseAgent` (`load_agent` → `build_agent`), but a *harness document* that declares its agents inline is a dead end: `HarnessSpec.agents` is a tuple of validated dicts written in a different dialect than `AgentSettings`, there is no way to look one up by name, and `build_agent` explicitly refuses a `HarnessSpec`. This change adds two small read-only methods to `YamlLoader` — `harness_agent_names(spec)` and `load_harness_agent(spec, name)` — that enumerate and translate harness-declared agents into ordinary `AgentSettings`. Because the result is a real `AgentSettings`, the existing `build_agent` accepts it unchanged. It also rewrites the `llms.txt` "YAML Configuration" section, which currently documents a different, non-exported loader class.

---

## 2. Goals & Non-Goals

### Goals

- Add `YamlLoader.harness_agent_names(spec) -> tuple[str, ...]` so a factory can loop over declared agents instead of taking a filesystem `Path` per agent.
- Add `YamlLoader.load_harness_agent(spec, name) -> AgentSettings` translating one resolved harness `agents[]` entry into validated `AgentSettings`.
- Let `build_agent(load_harness_agent(spec, name))` work **without modifying `build_agent`**.
- Keep `spec_id` byte-identical: no change to `vidbyte/harnesses/config.py` or to what is hashed.
- Fail closed with `ConfigurationError` naming the offending field, consistent with the rest of `vidbyte/config`.
- Correct the `llms.txt` YAML Configuration section to document `vidbyte/config/loader.py::YamlLoader` — including `build_agent` and the two new methods.

### Non-Goals

- **Changing the harness config schema.** `agents[]` validation in `vidbyte/harnesses/config.py` is untouched.
- **Translating the harness `tools: [{name, version}]` dialect** into `{ref, options}`. See §6.2 and §12.
- **Building non-`base` agent types.** `AgentSettings.from_mapping` already refuses them.
- **Removing the duplicate `YamlLoader`** in `vidbyte/lib/config/loader.py`. Still deferred (see §13).
- **New test files.** Per the invoked workflow; existing CI must stay green.
- **Any change to the `vidbyte` (backend) repo.** That follow-up is tracked separately.

---

## 3. Background & Context

This is the deferred half of PR #318. That design doc listed under Non-Goals:

> **Building from a `HarnessSpec`.** `HarnessSpec.agents` is `tuple[Mapping[str, Any], ...]` — untyped dicts in a different dialect (`model` not `model_name`, `params` not `loop`). Converging that is a separate PR; this one detects a `HarnessSpec` and raises a directive error.

The originating review comment is `Vidbyte#284` comment 3660837356:

> note, all of our agents should be defined in this agents file (not in seperate documents), then we should have 1 agent factory files that takes in the response of the YamlLoader and builds all of the agents through the YamlLoader … basically the YamlLoader when it takes in a .yaml file like this should return a list of AgentSettings, and then with those AgentSettings we should be able to actually build each one inside of the file … Maybe some helper functions in the YamlLoader class will also help (get_agent_name() given result of loading function, then we can loop over in factory class in vidbyte/ repo

**Current state, verified on `main` @ `812413a`:**

- `vidbyte/config/loader.py::YamlLoader` — `load`, `load_agent`, `load_harness`, `build_agent`, `view_agent`.
- `HarnessSpec.agents: tuple[Mapping[str, Any], ...]` (`vidbyte/lib/dataclasses/harnesses.py:79`) — validated dicts.
- `_buildable_settings` (`loader.py:169`) raises on a `HarnessSpec` with a directive pointing at `load_agent`.
- `HarnessConfigLoader._validate_agent` (`config.py:203`) requires a unique `name`, optionally validates `provider`, `model`, `system_prompt`, `params`, `tools`, and **copies every other key through unvalidated** — so `loop:` already survives into the spec.

**The dialect gap** (this is the whole problem, and it is smaller than it looks):

| Resolved harness `agents[]` entry | `AgentSettings` |
|---|---|
| `model` | `model_name` |
| `system_prompt: {content, sha256}` | `system_prompt: str` |
| `role` (canonical example) | not an allowed field |
| `params` (harness hyperparameters) | not an allowed field |
| everything else (`name`, `provider`, `temperature`, `loop`, `tools`, `middleware`, …) | identical |

`AgentSettings._ALLOWED_FIELDS` is a strict allowlist enforced by `_only()`, so an untranslated entry fails on the first harness-only key.

`$file` resolution matters here: `_resolve_file_reference` (`config.py:310`) replaces `{$file: prompts/x.md}` with `{"content": "...", "sha256": "..."}` **before** `_build_spec`. So the prompt text is already on the spec — no second disk read, and the digest that feeds `spec_id` is unaffected by anything this PR does.

### Field guide constraints applied

- *"Two classes named `YamlLoader` exist; the exported one is `vidbyte/config/loader.py`"* — verified again at runtime (`vidbyte.YamlLoader.__module__ == 'vidbyte.config.loader'`). All changes target that file.
- *"A `ref` resolves through a registry, never through the caller"* — this PR adds no caller-supplied component parameters; `build_agent` keeps owning ref resolution.
- *"Run the source stage with `PYTHONPATH=<worktree>`"* — recorded in §11.

---

## 4. Requirements

### Functional Requirements

1. `harness_agent_names(spec)` returns declared agent names in document order.
2. `harness_agent_names` raises `ConfigurationError` if given anything other than a `HarnessSpec`.
3. `load_harness_agent(spec, name)` returns validated `AgentSettings` for the named agent.
4. `load_harness_agent` raises `ConfigurationError` naming the unknown agent and listing available names when `name` is not declared.
5. Translation maps `model` → `model_name`.
6. Translation maps `system_prompt: {content, sha256}` → the `content` string; a plain string passes through unchanged.
7. Translation drops exactly the harness-only orchestration keys (`role`, `params`); every other key reaches `AgentSettings.from_mapping`.
8. Any remaining unsupported key fails closed via the existing `_only()` check, with `details["field"]` naming it.
9. `build_agent(load_harness_agent(spec, name))` constructs a `BaseAgent` with no change to `build_agent`.
10. `build_agent`'s existing `HarnessSpec` rejection message is updated to point at `load_harness_agent` instead of only `load_agent`.
11. `spec_id` for any existing harness document is byte-identical to `main`.
12. `llms.txt` documents the exported loader, its five existing methods, and the two new ones.

### Non-Functional Requirements

- **Performance:** pure in-memory dict translation; no disk or network access. `$file` was already resolved at `load_harness` time.
- **Security:** no document text reaches an import; no new file reads, so the `_contained` containment rule is not in play.
- **Observability:** every failure is a `ConfigurationError` carrying `details["field"]`, matching the package convention.
- **Reliability:** `HarnessSpec` is frozen; translation copies rather than mutates.
- **Compatibility:** purely additive. No existing signature, return type, or hashed value changes.

---

## 5. High-Level Design

Three additions, all in files that already own the relevant concern, and no new modules.

The core decision is **translate, don't converge**. Making `HarnessConfigLoader` emit `AgentSettings` directly would mean changing what `_build_spec` stores on `spec.agents`, which changes the canonical JSON, which changes every `spec_id` — a breaking change to durable identity for a convenience win. Instead the spec stays exactly as it is, and translation happens on read, in the loader that already owns document→settings translation. `vidbyte/harnesses/config.py` is not touched at all.

The second decision is **do not widen `build_agent`**. Once `load_harness_agent` returns a genuine `AgentSettings`, the existing guard accepts it — the guard only ever rejected a raw `HarnessSpec`. So the "relax `build_agent`" item from the original analysis turns out to need zero logic, only a better error message pointing at the new method.

```
config.yaml (harness envelope)
        |
        v
YamlLoader.load_harness()  ──> HarnessSpec  (spec_id unchanged, $file already resolved)
                                    |
              harness_agent_names(spec) ──> ("discovery", "source_extractor")
                                    |
              load_harness_agent(spec, name)
                    |
                    +-- _harness_agent_entry()    find by name, or raise
                    +-- _agent_settings_payload()  dialect translation
                    +-- AgentSettings.from_mapping()  all validation, unchanged
                                    |
                                    v
                              AgentSettings
                                    |
                     build_agent(settings)   <-- unchanged
                                    v
                               BaseAgent
```

---

## 6. Detailed Design

### 6.1 `YamlLoader` — two public methods plus three private helpers

**File:** `vidbyte/config/loader.py`
**Type:** Modified

#### What it does

Exposes harness-declared agents as ordinary `AgentSettings`, so a harness document with an inline `agents:` block becomes a valid source of buildable agents.

#### Interface / API

```python
def harness_agent_names(self, spec: HarnessSpec) -> tuple[str, ...]: ...
def load_harness_agent(self, spec: HarnessSpec, name: str) -> AgentSettings: ...

def _harness_spec(self, spec: object) -> HarnessSpec: ...
def _harness_agent_entry(self, spec: HarnessSpec, name: str) -> Mapping[str, Any]: ...
def _agent_settings_payload(self, entry: Mapping[str, Any], name: str) -> dict[str, Any]: ...
```

Module-level constants:

```python
# Harness-only orchestration keys that describe an agent's place in the harness,
# not how to construct it. Anything else unknown still fails AgentSettings._only().
_HARNESS_ONLY_AGENT_KEYS = frozenset({"role", "params"})
_HARNESS_AGENT_FIELD_ALIASES = {"model": "model_name"}
```

#### Logic / Algorithm

`harness_agent_names`:
1. `self._harness_spec(spec)` — type guard.
2. Return `tuple(str(entry["name"]) for entry in spec.agents)`.

`load_harness_agent`:
1. `self._harness_spec(spec)` — type guard.
2. `entry = self._harness_agent_entry(spec, name)` — lookup or raise.
3. `payload = self._agent_settings_payload(entry, name)` — translate.
4. `return AgentSettings.from_mapping(payload, f"harness.agents[{name}]")`, re-raising `ConfigurationError` with `details.setdefault("harness_type", spec.harness_type)`.

`_agent_settings_payload`:
1. Start from an empty dict; iterate `entry`.
2. Skip keys in `_HARNESS_ONLY_AGENT_KEYS`.
3. Rename via `_HARNESS_AGENT_FIELD_ALIASES`.
4. For `system_prompt`: if it is a `Mapping` containing `"content"`, take `str(value["content"])`; otherwise pass through untouched.
5. Return the dict.

#### Edge Cases & Error Handling

- **Not a `HarnessSpec`** → `ConfigurationError`, `field="harness.spec"`, `actual_type`.
- **Unknown agent name** → `ConfigurationError`, `field="harness.agents.name"`, `details["available"]` listing declared names.
- **Both `model` and `model_name` present** → the alias would collide. `model_name` is applied last and wins; documented in the method comment. (Cannot occur from `HarnessConfigLoader`, which never emits `model_name`, but the spec is constructible directly.)
- **`system_prompt` mapping without `content`** → passed through as a mapping; `AgentSettings._validated_system_prompt` rejects it with its own field-named error.
- **Harness-dialect `tools: [{name, version}]`** → reaches `AgentSettings` and is rejected there naming `harness.agents[x].tools`. Deliberate; see §12.
- **Empty `agents: []`** → `harness_agent_names` returns `()`; `load_harness_agent` raises with `available: []`.

### 6.2 `_buildable_settings` — redirect message only

**File:** `vidbyte/config/loader.py`
**Type:** Modified (one string)

The `HarnessSpec` branch currently says *"load the agent document with load_agent() instead"*, which is now wrong advice for a harness that declares agents inline. Updated to name `load_harness_agent(spec, name)`. The `details` payload already lists the declared agent names, so it becomes directly actionable. No control flow changes.

### 6.3 `llms.txt` — YAML Configuration section

**File:** `llms.txt`
**Type:** Modified

The section (lines ~122–152) documents `vidbyte.lib.config.loader`, `AgentDescriptor`/`HarnessDescriptor`/`EnvironmentDescriptor`, a `load_environment(path)` method, a `type:` root discriminator, and tells applications to resolve refs themselves. Verified against `main`, all of that is wrong for the exported class:

| `llms.txt` claims | Reality on `main` |
|---|---|
| `vidbyte.lib.config.loader` | `vidbyte.YamlLoader.__module__ == "vidbyte.config.loader"` |
| `load_environment(path)` | `hasattr(YamlLoader, "load_environment") is False` |
| families keyed by `type:` at root | harness detected by envelope (`schema_version`/`harness`); agents need no `kind` |
| returns `AgentDescriptor` | returns `AgentSettings` |
| `AgentSettings` is "legacy" | `AgentSettings` is what the exported loader returns |
| application resolves refs | `ComponentRegistry` resolves them inside `build_agent` |

Rewritten to describe: the two document families and how they are told apart; `load` / `load_agent` / `load_harness` / `build_agent` / `view_agent`; ref resolution through `ComponentRegistry` (and that application-defined components are attached after building, not declarable); and the new harness-agent path with a runnable example.

---

## 7. Data Model Changes

N/A — no persisted schema changes. `HarnessSpec` is unmodified, and `spec_id` inputs are untouched by design (§5).

---

## 8. API Changes

N/A — no HTTP surface. The Python API additions are covered in §6.1.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/harness-agent-building.md` | This design doc |
| MODIFY | `vidbyte/config/loader.py` | Add `harness_agent_names`, `load_harness_agent`, three private helpers, two module constants; update one error string |
| MODIFY | `llms.txt` | Rewrite the YAML Configuration section onto the exported loader; document `build_agent` and the new methods |

Three files. No new modules, no deletions, no changes under `vidbyte/harnesses/`.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| — | — | No new dependencies | None |

Uses only what `vidbyte/config/loader.py` already imports (`HarnessSpec`, `AgentSettings`, `ConfigurationError`).

---

## 11. Rollout & Deployment

- **Feature flags:** none. Purely additive methods.
- **Breaking change:** no. No existing signature, return type, or hashed value changes. The only altered behavior is the text of one error message.
- **Deployment order:** SDK merges first; the `vidbyte` backend picks it up when its pin moves. Nothing in the backend breaks before then.
- **Rollback:** revert the commit; nothing persists state.
- **CI gate (recorded per workflow):**
  ```bash
  python -m pip install -e ".[dev]"
  PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source   # diagnostic
  python scripts/run_ci.py --stage package                    # diagnostic, no PYTHONPATH
  python scripts/run_ci.py                                    # full gate
  ```
  Per the field guide: the source stage needs `PYTHONPATH=$(pwd)` from a worktree or it silently tests the canonical checkout; the package stage must *not* have it, or pip skips the install. New `.py` files must be `git add`-ed before semgrep is trusted — this PR adds none, but the doc is new.
- **`spec_id` regression check:** load an existing harness document on `main` and on the branch, assert the `spec_id` strings match.

---

## 12. Open Questions

- [ ] **Harness-dialect `tools`.** The canonical example in `docs/design/harness-execution-contract.md` shows `tools: [{name, version}]`, while `AgentSettings` expects ref strings or `{ref, options}`. I propose failing closed with a field-named error rather than adding a second translation, since the shape is documented as deliberately open and no consumer needs it today. Confirm, or should the bridge translate `{name}` → `{ref}`?
- [ ] **`params` handling.** Dropped, because harness hyperparameters are not agent construction settings and remain readable off `spec.agents`. Alternative would be folding them into `AgentSettings.metadata` — rejected as lossy and surprising. Confirm.
- [ ] **Method naming.** `harness_agent_names` / `load_harness_agent` reads consistently with `load_harness`. The review comment said "`get_agent_name()`"; I avoided a `get_` prefix since nothing else in the class uses one. Confirm.

---

## 13. Alternatives Considered

### Alternative 1: Make `HarnessConfigLoader` emit `AgentSettings` on the spec
- **What:** Change `_build_spec` so `spec.agents` is `tuple[AgentSettings, ...]`.
- **Why rejected:** `spec.agents` feeds the canonical JSON that produces `spec_id`. Changing its shape re-fingerprints every existing harness variant — a breaking change to durable identity, and it violates the standing "spec_id must stay byte-identical" constraint. It also forces `vidbyte/harnesses` to depend on `vidbyte/lib/dataclasses/config`, coupling the harness contract to the agent settings dialect.

### Alternative 2: Widen `build_agent` to accept `(spec, name)`
- **What:** Overload `build_agent` so it takes a `HarnessSpec` plus a name.
- **Why rejected:** Overloads the one method whose contract is deliberately narrow ("exactly the settings `load_agent()` returned"), and hides the translation step. Keeping translation in a separate named method means the intermediate `AgentSettings` is inspectable, and `build_agent` stays untouched — strictly less new logic.

### Alternative 3: Put the translation on `AgentSettings.from_harness_entry()`
- **What:** A classmethod on the settings dataclass.
- **Why rejected:** Would make `vidbyte/lib/dataclasses/config.py` aware of the harness dialect, inverting the layering — the loader is the component that already owns document→settings translation (`_parse_agent_settings` does exactly this for the agent-document dialect).

### Alternative 4: Add a `HarnessSpec.agent_settings` property
- **What:** Compute settings lazily on the frozen dataclass.
- **Why rejected:** `HarnessSpec` lives in `vidbyte/lib/dataclasses` and is a pure data contract; importing `AgentSettings` there creates the same inverted dependency as Alternative 3, and a property cannot raise a well-formed `ConfigurationError` with a `field` path as naturally as a loader method.

---

END OF DESIGN DOC
