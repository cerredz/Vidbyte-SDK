# Context Window Templates

Use this guide when adding template support to a new context-window algorithm,
or when running template validation during AI-assisted algorithm development.

Related skill files:

- Vidbyte SDK structure: `skills/vidbyte-sdk/SKILL.md`
- Adding context window algorithms: `skills/vidbyte-sdk/adding-context-window-algorithms.md`

Related design doc:

- `docs/design/context-window-templates.md`

---

## 1. Mental Model

Context-window algorithms produce a **deterministic structural pattern** in the
sequence of events that drive an agent run. A *template* is the expected version
of that pattern, expressed as an ordered list of named slot strings:

```python
["system_prompt", "reflexion_trial", "reflexion_reflection", "reflexion_trial"]
```

A *recorder* is the actual version — a lightweight event log that accumulates
slot names as they are emitted by the running algorithm. Validation is positional
string matching: each expected slot at index `i` must equal the actual slot at
index `i`.

This system has three key properties:

1. **Deterministic** — slots are emitted in code, not inferred. There is no
   parsing, heuristics, or model output involved.
2. **Zero overhead in production** — `AgentRuntime` defaults to `NullRecorder`,
   which is a no-op. No list allocations, no overhead.
3. **Machine-readable acceptance criterion** — an AI agent can write the template
   first, implement the algorithm, run the test harness, read the violations, and
   iterate on the implementation until `template.passes(recorder)` is `True`.

---

## 2. Slot Name Conventions

Use snake_case for all slot names. Follow these prefixing rules:

| Category | Prefix | Examples |
|----------|--------|---------|
| Base runtime | none | `system_prompt`, `tool_call`, `agent_iteration`, `middleware` |
| Algorithm-specific | `<algorithm_name>_` | `reflexion_trial`, `reflexion_reflection` |

**Reserved base runtime slots** (Phase 2 — not yet emitted):

- `system_prompt` — currently emitted by algorithm implementations at run start.
  When base runtime emission is added, algorithms should not emit this themselves.
- `tool_call` — one per executed tool call inside `_arun_once`.
- `agent_iteration` — one per model call inside `_arun_once`.
- `middleware` — one per middleware gate evaluation (before_run, before_model_call).

**Algorithm-specific slots** must be unique and descriptive. Examples:

```
reflexion_trial          # one trial through the main agentic loop
reflexion_reflection     # one reflection-stage model call
inner_loop_iteration     # one pass through the inner agent loop
outer_loop_summary       # one summary injected by the outer loop
outer_loop_critique      # one critique injected by the outer loop
reasoning_injection      # one injected reasoning token block
```

Do not create slots that duplicate base runtime slots. Do not create slots that
are too granular (e.g. per-token events). Slots should represent structural
decisions made by the algorithm, not internal bookkeeping.

---

## 3. Recorder Usage

### Creating and passing a recorder

```python
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.templates import ContextWindowRecorder
from vidbyte.context.window import ContextWindow
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy

recorder = ContextWindowRecorder()

runtime = AgentRuntime(
    agent_name="my-agent",
    system_prompt="Work carefully.",
    tools=Tools(),
    permission_policy=PermissionPolicy(),
    algorithm=ContextWindow.preset.reflexion,
    recorder=recorder,    # pass recorder here
)

# ... run the agent ...

print(recorder.slots())
# ('system_prompt', 'reflexion_trial', 'reflexion_reflection', 'reflexion_trial')
```

### Inspecting events

```python
for event in recorder.events():
    print(event.slot_type, event.iteration, event.metadata)
```

### Resetting between test cases

```python
recorder.reset()
# recorder.slots() is now ()
```

### Production code — no change needed

In production, `recorder` is not passed to `AgentRuntime`. The default
`NullRecorder` is used automatically with zero overhead.

---

## 4. Template Construction

Templates are built by constructing a list of expected slot names and wrapping
it in a `ContextWindowTemplate` (or a subclass).

### Inline construction

```python
from vidbyte.lib.templates import ContextWindowTemplate

template = ContextWindowTemplate([
    "system_prompt",
    "reflexion_trial",
    "reflexion_reflection",
    "reflexion_trial",
])
```

### Parameterized construction using list arithmetic

When slot sequences depend on runtime parameters (trial count, failure count,
iteration count), build the list programmatically:

```python
def build_inner_outer_loop_template(outer_iterations: int) -> ContextWindowTemplate:
    slots = ["system_prompt"]
    for _ in range(outer_iterations):
        slots.extend(["outer_loop_summary", "outer_loop_critique"])
    return ContextWindowTemplate(slots)
```

For the reasoning injection algorithm (every N iterations):

```python
def build_reasoning_injection_template(cycles: int, n: int) -> ContextWindowTemplate:
    cycle = ["agent_iteration"] * n + ["reasoning_injection"]
    slots = ["system_prompt"] + cycle * cycles
    return ContextWindowTemplate(slots)
```

### Subclass pattern (preferred for reuse)

Wrap the construction logic in a subclass so templates are importable and
named:

```python
from vidbyte.lib.templates.base import ContextWindowTemplate

class InnerOuterLoopTemplate(ContextWindowTemplate):
    def __init__(self, *, outer_iterations: int) -> None:
        super().__init__(self._build_slots(outer_iterations=outer_iterations))

    @staticmethod
    def _build_slots(*, outer_iterations: int) -> list[str]:
        slots = ["system_prompt"]
        for _ in range(outer_iterations):
            slots.extend(["outer_loop_summary", "outer_loop_critique"])
        return slots
```

Place the subclass in `vidbyte/lib/templates/<algorithm_name>.py` and export
it from `vidbyte/lib/templates/__init__.py`.

---

## 5. Validation

```python
from vidbyte.lib.templates import ReflexionContextWindowTemplate

template = ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)

violations = template.validate(recorder)
if violations:
    for v in violations:
        print(v.message)  # "position 2: expected 'reflexion_reflection', got None"
else:
    print("Template passed.")

# Boolean shorthand
assert template.passes(recorder)
```

`TemplateViolation` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `position` | `int` | 0-based index in the slot sequence |
| `expected` | `str` | The expected slot name (or `"<end>"` for extra slots) |
| `actual` | `str | None` | The actual slot name; `None` if trace ended early |
| `message` | `str` | Human-readable description of the mismatch |

---

## 6. Instrumentation Pattern

Algorithm runtime adapters emit slots via `self.runtime.recorder.append(...)`.
The recorder is always available because `AgentRuntime` defaults to
`NullRecorder` — emit calls never need to check whether a recorder is present.

### Where to emit

Emit a slot **at the exact code point where the structural element is
introduced**, not before or after. Correct placement is what makes the template
meaningful.

| Structural element | Emit point |
|--------------------|------------|
| Run start (system prompt configured) | First statement in `arun`, before the loop |
| Algorithm trial begins | First statement in `_run_trial`, before `_arun_once` |
| Algorithm reflection begins | First statement in `_reflect_after_failure`, before `_invoke_with_middleware` |
| Algorithm stage begins (e.g. outer loop summary) | First statement in the method that produces the summary injection |

### Example — new algorithm

```python
class InnerOuterLoopRuntimeAlgorithm:
    async def arun(self, message: str, ...) -> StrategyResult:
        self.runtime.recorder.append("system_prompt")
        for outer_index in range(self.algorithm.max_outer_loops):
            inner_result = await self._run_inner_loop(message, outer_index=outer_index, ...)
            await self._summarize_and_critique(inner_result, outer_index=outer_index, ...)
        return ...

    async def _run_inner_loop(self, message: str, *, outer_index: int, ...) -> StrategyResult:
        # No slot emitted here; _run_inner_loop is structural bookkeeping, not a new element.
        return await self.runtime._arun_once(message, ...)

    async def _summarize_and_critique(self, result: StrategyResult, *, outer_index: int, ...) -> None:
        self.runtime.recorder.append("outer_loop_summary", iteration=outer_index)
        # ... generate summary and inject into context ...
        self.runtime.recorder.append("outer_loop_critique", iteration=outer_index)
        # ... generate critique and inject into context ...
```

### emit signature

```python
self.runtime.recorder.append(
    "slot_type_name",     # required: the slot name string
    iteration=0,          # required: the trial/iteration index
    **metadata,           # optional: any extra context for debugging
)
```

---

## 7. Test Structure

Each algorithm with template support needs a dedicated test section in
`tests/test_context_window_templates.py` (or its own test file for complex
algorithms). The required test scenarios are:

### 7.1 Template construction tests

- Minimum configuration (lowest possible trial/iteration count)
- Default configuration (verify default parameter wiring)
- Maximum or multi-cycle configuration
- Verify `expected_slots` exactly matches the manually constructed expected list

### 7.2 Recorder instrumentation tests

- Correct number of algorithm-specific slots are emitted
- Slots appear at the correct positions relative to each other
- Slot `iteration` field matches the trial or outer-loop index
- Early exit (algorithm succeeds on first attempt) does not pollute trace with
  unexecuted stages

### 7.3 Template validation integration test

- Full end-to-end run with `FakeRunner` responses
- `template.passes(recorder)` is `True`
- `template.validate(recorder)` returns an empty list

### 7.4 NullRecorder safety test

- Running the algorithm with the default `NullRecorder` produces no exception
- All `StrategyResult.metadata` assertions from pre-existing tests still hold

### Test helper pattern

Use `FakeRunner` with an explicit list of canned responses. Remember that
**both trial model calls and algorithm stage calls (reflection, scoring, etc.)
consume responses from the same runner**. For a 2-trial Reflexion run:

```python
runner = FakeRunner([
    _max_iterations_response(),   # trial 0 model call
    _reflection_response(),       # reflection model call after trial 0
    _is_done_response(),          # trial 1 model call
])
```

Always count the total model calls your algorithm will make and provide exactly
that many responses.

---

## 8. Reflexion — Full Walkthrough

### Template

```python
from vidbyte.lib.templates import ReflexionContextWindowTemplate

# 3 trials, 2 failures (default)
template = ReflexionContextWindowTemplate(max_trials=3)
print(template.expected_slots)
# ('system_prompt', 'reflexion_trial', 'reflexion_reflection',
#  'reflexion_trial', 'reflexion_reflection', 'reflexion_trial')
```

### Instrumentation points

| Method | File | Slot emitted |
|--------|------|-------------|
| `ReflexionRuntimeAlgorithm.arun` | `vidbyte/agents/algorithms/reflexion.py` | `"system_prompt"` |
| `ReflexionRuntimeAlgorithm._run_trial` | `vidbyte/agents/algorithms/reflexion.py` | `"reflexion_trial"` |
| `ReflexionRuntimeAlgorithm._reflect_after_failure` | `vidbyte/agents/algorithms/reflexion.py` | `"reflexion_reflection"` |

### Full test example

```python
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.templates import ContextWindowRecorder
from vidbyte.context.algorithms import ReflexionAlgorithm
from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
from vidbyte.lib.templates import ReflexionContextWindowTemplate
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.strategies.types import BaseAgentContext

recorder = ContextWindowRecorder()
algorithm = ContextWindowAlgorithm(
    name="reflexion",
    reflexion=ReflexionAlgorithm(max_trials=2),
)
runtime = AgentRuntime(
    agent_name="test-agent",
    system_prompt="Work.",
    tools=Tools(),
    permission_policy=PermissionPolicy(),
    config=AgentRuntimeConfig(max_iterations=1),
    algorithm=algorithm,
    recorder=recorder,
)
context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)

# Runner: trial 0 fails, reflection runs, trial 1 succeeds
runner = FakeRunner([
    FakeResponse("Could not finish.", {}),       # trial 0
    FakeResponse("Should try differently.", {}), # reflection
    FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]}),  # trial 1
])

await runtime.arun(
    "task",
    runner=runner,
    context=context,
    provider="openai",
    invoke_runner=invoke_runner,
    runner_output_text=output_text,
    runner_output_metadata=output_metadata,
)

template = ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)
assert template.passes(recorder), template.validate(recorder)
```

---

## 9. AI-Assisted Algorithm Development Loop

This is the primary use case for templates. When an AI agent is asked to
implement a new context-window algorithm, the workflow is:

1. **Receive prompt** — describe the algorithm's structural behavior.
2. **Derive the template** — write the expected slot list as a
   `ContextWindowTemplate` subclass in `vidbyte/lib/templates/<name>.py`.
   This is the acceptance criterion. Do not modify it once written.
3. **Write the implementation** — implement the algorithm following the guide
   in `adding-context-window-algorithms.md`. Add emit calls at all structural
   points per Section 6 above.
4. **Run the test harness** — execute
   `python scripts/test-context-window-templates.py` and observe the
   `template.validate(recorder)` output.
5. **Read violations** — each `TemplateViolation` names the position, expected
   slot, and actual slot. The implementation must be changed to match the
   template; the template must not be changed to match the implementation.
6. **Edit and rerun** — modify the implementation (emit points, ordering, loop
   structure) until all violations are resolved.
7. **Full test gate** — after the template passes, run
   `python -m unittest discover -s tests` and confirm 0 failures.

The template is the invariant. The implementation is the variable.

---

## 10. Adding Templates to a New Algorithm — Checklist

- [ ] Add `recorder.append("<algo>_<stage>", iteration=...)` at each structural
      emit point in `vidbyte/agents/algorithms/<name>.py`.
- [ ] Create `vidbyte/lib/templates/<name>.py` with the template subclass.
- [ ] Export the new template from `vidbyte/lib/templates/__init__.py`.
- [ ] Add template construction tests and instrumentation tests to
      `tests/test_context_window_templates.py`.
- [ ] Add a section to this skill file documenting the new algorithm's slot
      names, instrumentation points, and expected slot sequence.
- [ ] Verify `python -m compileall vidbyte` passes.
- [ ] Verify `python -m unittest discover -s tests` passes with 0 failures.

---

## 11. File Reference

| File | Role |
|------|------|
| `vidbyte/context/templates/recorder.py` | RecorderBase, ContextWindowRecorder, NullRecorder, SlotEvent |
| `vidbyte/context/templates/__init__.py` | Module exports |
| `vidbyte/lib/templates/base.py` | ContextWindowTemplate, TemplateViolation |
| `vidbyte/lib/templates/reflexion.py` | ReflexionContextWindowTemplate |
| `vidbyte/lib/templates/__init__.py` | Module exports |
| `vidbyte/agents/runtime.py` | recorder param added; defaults to NullRecorder |
| `vidbyte/agents/algorithms/reflexion.py` | system_prompt, reflexion_trial, reflexion_reflection emits |
| `tests/test_context_window_templates.py` | All template and instrumentation tests |
| `scripts/test-context-window-templates.py` | Executable verification script |
| `docs/design/context-window-templates.md` | Full design doc |
