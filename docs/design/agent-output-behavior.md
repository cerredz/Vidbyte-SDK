# Design Doc: Agent Output Behavior

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-24
**Last Updated:** 2026-06-24

---

## 1. Overview

This feature extends the existing `agent.behavior` facade with a first-class output behavior category exposed as `agent.behavior.output`. The new category inspects structural and linguistic properties of a completed agent reply, such as emptiness, length, valid JSON, fenced code blocks, URLs, citations, refusals, hedging, prefix/suffix shape, and structured output fields sourced from `reply.metadata["structured"]`. It complements existing text graders without duplicating arbitrary substring or regex grading.

---

## 2. Goals & Non-Goals

### Goals

- Add `OutputBehavior` under `vidbyte/evals/behavior/output.py`.
- Expose the new category through `agent.behavior.output`.
- Extend `RunProbe` with a `structured: Any = None` field sourced from `reply.metadata.get("structured")`.
- Provide deterministic output-shape predicates over `RunProbe.output`.
- Provide structured-output predicates over `RunProbe.structured`.
- Update behavior package exports and SDK skill docs.
- Add focused unit, integration, and verification-script coverage for every new predicate.
- Preserve existing behavior categories: tool, tool arguments, stop, and handoff.

### Non-Goals

- No arbitrary substring grader replacement. `ContainsGrader` remains the correct API for "actual contains expected".
- No arbitrary regex grader replacement. `RegexMatchGrader` remains the correct API for caller-provided pattern checks.
- No LLM-as-judge output quality scoring. `LLMJudgeGrader` and `RubricGrader` remain separate.
- No new provider calls, hosted evals, persistence, registry schema, or database changes.
- No mutation of agent state, reply metadata, or structured output objects.
- No full Markdown parser dependency. Markdown checks use conservative stdlib regex heuristics.
- No deep JSON-schema validation inside `OutputBehavior`. `JSONSchemaGrader` and `OutputSchemaFormatter` keep that responsibility.

---

## 3. Background & Context

The repository already has an agent behavior system under `vidbyte/evals/behavior/`. `RunProbe` captures a completed run, `Behavior` composes category classes, `BaseAgent.behavior` exposes a lazy cached facade, and `PredicateGrader` lets `EvalRunner` pass a `RunProbe` into eval suites. Current categories cover tool presence/outcome, tool arguments, stop reasons, and handoffs.

The existing eval graders already cover exact text, substring, regex, JSON schema, LLM judge, and rubric scoring. The gap is response-shape behavior: users need concise predicates that ask what kind of output the agent produced, not whether it included one expected substring. Examples include "was the response empty", "did it produce valid JSON", "did it include a fenced code block", "did it refuse", "did it hedge", and "did native structured output produce a field with this value".

Structured output already exists in the SDK. `AgentResult.structured` is populated by the runtime when `output_schema` parsing succeeds, and `BaseAgent.generate_reply` writes non-None structured values to `reply.metadata["structured"]`. `RunProbe` currently captures `output` but not `structured`, so this feature adds that field as the source of truth for structured behavior checks.

Relevant current files:

- `vidbyte/evals/behavior/probe.py`: `RunProbe` snapshot, currently includes `output` but not `structured`.
- `vidbyte/evals/behavior/behavior.py`: facade exposing `.tool`, `.tool_args`, `.stop`, `.handoff`.
- `vidbyte/evals/behavior/__init__.py`: behavior package exports.
- `vidbyte/evals/graders/predicate.py`: `PredicateGrader` receives `RunProbe`.
- `vidbyte/evals/runner.py`: builds `RunProbe` for agent eval targets.
- `vidbyte/agents/base.py`: stores `reply.metadata["structured"]` when result structured output exists.
- `vidbyte/lib/dataclasses/strategies.py`: `AgentResult.structured`.
- `skills/vidbyte-sdk/agent-behavior.md` and `skills/usage/agent-behavior.md`: behavior docs to update.

---

## 4. Requirements

### Functional Requirements

1. `RunProbe` must gain `structured: Any = None`.
2. `RunProbe.from_agent(agent)` must copy `reply.metadata.get("structured")` into `probe.structured`.
3. `RunProbe.from_reply(reply, agent=None)` must copy `reply.metadata.get("structured")` into `probe.structured`.
4. `Behavior.__init__` must initialize `OutputBehavior(self)`.
5. `Behavior.output` must return the `OutputBehavior` instance.
6. `OutputBehavior.is_empty(strip=True)` must return whether output is empty, optionally after stripping whitespace.
7. `OutputBehavior.is_not_empty(strip=True)` must return the negation of `is_empty(strip=strip)`.
8. `OutputBehavior.length(at_least=None, at_most=None, strip=False)` must check output character length against optional inclusive bounds.
9. `OutputBehavior.line_count(at_least=None, at_most=None)` must count logical lines using `str.splitlines()`.
10. `OutputBehavior.word_count(at_least=None, at_most=None)` must count words using a deterministic word-token regex.
11. `OutputBehavior.is_valid_json()` must return `True` only when raw output parses via `json.loads`.
12. `OutputBehavior.contains_code_block(language=None)` must detect Markdown fenced code blocks and optionally match the fence language case-insensitively.
13. `OutputBehavior.code_block_count(language=None, at_least=None, at_most=None)` must count fenced code blocks and apply optional inclusive bounds.
14. `OutputBehavior.contains_url()` must detect `http://`, `https://`, or `www.` URLs.
15. `OutputBehavior.url_count(at_least=None, at_most=None)` must count detected URLs and apply optional inclusive bounds.
16. `OutputBehavior.contains_citation(style="any")` must support `any`, `markdown`, `bracket`, `footnote`, and `url` styles.
17. `OutputBehavior.citation_count(style="any", at_least=None, at_most=None)` must count citation-like references for the requested style and apply optional inclusive bounds.
18. `OutputBehavior.refused()` must detect common refusal phrases such as "I can't", "I cannot", "I'm unable to", "I am unable to", "I can't help with", and "I won't".
19. `OutputBehavior.contains_hedging()` must detect common hedging terms such as "maybe", "possibly", "probably", "I think", "it seems", "appears to", and "likely".
20. `OutputBehavior.starts_with(prefix, case_sensitive=True, strip=False)` must check output prefix with optional case folding and whitespace stripping.
21. `OutputBehavior.ends_with(suffix, case_sensitive=True, strip=False)` must check output suffix with optional case folding and whitespace stripping.
22. `OutputBehavior.structured_valid()` must return `True` when `probe.structured is not None`.
23. `OutputBehavior.structured_field_exists(path)` must support dot paths and integer list indexes such as `"items.0.title"`.
24. `OutputBehavior.structured_field_equals(path, value)` must compare a resolved structured field with `==`.
25. `OutputBehavior.structured_field_matches(path, predicate)` must call a user predicate on the resolved value and return its boolean result.
26. `OutputBehavior.structured_field_type(path, expected_type)` must return whether a resolved field is an instance of the supplied type.
27. `OutputBehavior.structured_contains_keys(keys)` must return whether a top-level structured mapping contains every requested key.
28. Missing structured fields must return `False`, not raise.
29. Predicate exceptions in `structured_field_matches` must propagate, matching existing behavior for `tool_called_with_matching`.
30. Existing `PredicateGrader` behavior must continue to work with the extended `RunProbe`.
31. Existing standard graders must remain unchanged.

### Non-Functional Requirements

- Backward compatible: existing `RunProbe(...)` construction must continue to work because `structured` has a default.
- Read-only: no output or structured predicate may mutate output, structured data, agent state, or reply metadata.
- No new dependencies: use only Python stdlib plus existing SDK types.
- Deterministic: all predicates must be pure functions of `RunProbe.output` and `RunProbe.structured`.
- Efficient: all raw-output checks are O(n) in output length; structured path lookup is O(path segments).
- Style: methods follow the existing behavior classes: class-first design, one-line signatures, and an explanatory comment immediately below every method signature.
- Error tolerance: invalid JSON and missing structured fields return `False`; caller-supplied predicate errors propagate.

---

## 5. High-Level Design

The existing behavior architecture stays intact. `RunProbe` remains the immutable run snapshot. `Behavior` remains the facade cached on `BaseAgent`. The change adds one new category object, `OutputBehavior`, initialized alongside the existing category objects.

Data flow:

```text
BaseAgent.generate_reply()
  -> AgentMessage(content=result.output, metadata={..., "structured": result.structured?})
  -> agent.last_reply
  -> agent.behavior
  -> Behavior.probe
  -> RunProbe.from_agent(agent)
  -> RunProbe(output=reply.content, structured=reply.metadata.get("structured"))
  -> agent.behavior.output.*
```

For eval suites, no runner contract changes are needed beyond the `RunProbe` field extension. `EvalRunner` already builds a probe for agent targets and passes it to graders implementing `agrade_with_probe`. A `PredicateGrader` can directly inspect `p.output` and `p.structured`, or callers can instantiate/use `OutputBehavior` through the agent facade after a run.

Key decisions:

- Put output checks under `agent.behavior.output` rather than adding flat methods to `Behavior`. This keeps the behavior API grouped by category and matches existing conventions.
- Include only structural and linguistic output predicates, not arbitrary substring/regex checks. This avoids duplicating the grader catalog.
- Use `reply.metadata["structured"]` as the structured-output source of truth. The runtime already validates and stores it there when structured output succeeds.
- Use conservative stdlib parsing and regexes. This keeps the feature dependency-free and predictable.

---

## 6. Detailed Design

### 6.1 `RunProbe` Structured Field

**File(s):** `vidbyte/evals/behavior/probe.py`
**Type:** Modified

#### What it does

Adds structured output to the immutable run snapshot so output predicates and `PredicateGrader` lambdas can inspect parsed native structured output.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class RunProbe:
    structured: Any = None
```

#### Logic / Algorithm

1. Add `structured: Any = None` after `output: str = ""`.
2. In `_from_reply_and_agent`, build `md = dict(reply.metadata) if reply.metadata else {}` as today.
3. Pass `structured=md.get("structured")` into the `RunProbe` constructor.
4. In `_from_reply_only`, pass the same `structured=md.get("structured")`.
5. Keep no-reply default as `None`.

#### Edge Cases & Error Handling

- Missing `"structured"` metadata returns `None`.
- Structured value may be a `dict`, list, scalar, or Pydantic model instance.
- No validation occurs in `RunProbe`; it only snapshots existing observable state.

---

### 6.2 `OutputBehavior`

**File(s):** `vidbyte/evals/behavior/output.py`
**Type:** New file

#### What it does

Provides deterministic predicates over the final response text and optional structured output object.

#### Interface / API

```python
class OutputBehavior:
    def __init__(self, behavior: Behavior) -> None: ...
    def is_empty(self, strip: bool = True) -> bool: ...
    def is_not_empty(self, strip: bool = True) -> bool: ...
    def length(self, *, at_least: int | None = None, at_most: int | None = None, strip: bool = False) -> bool: ...
    def line_count(self, *, at_least: int | None = None, at_most: int | None = None) -> bool: ...
    def word_count(self, *, at_least: int | None = None, at_most: int | None = None) -> bool: ...
    def is_valid_json(self) -> bool: ...
    def contains_code_block(self, language: str | None = None) -> bool: ...
    def code_block_count(self, language: str | None = None, *, at_least: int | None = None, at_most: int | None = None) -> int | bool: ...
    def contains_url(self) -> bool: ...
    def url_count(self, *, at_least: int | None = None, at_most: int | None = None) -> int | bool: ...
    def contains_citation(self, style: str = "any") -> bool: ...
    def citation_count(self, style: str = "any", *, at_least: int | None = None, at_most: int | None = None) -> int | bool: ...
    def refused(self) -> bool: ...
    def contains_hedging(self) -> bool: ...
    def starts_with(self, prefix: str, *, case_sensitive: bool = True, strip: bool = False) -> bool: ...
    def ends_with(self, suffix: str, *, case_sensitive: bool = True, strip: bool = False) -> bool: ...
    def structured_valid(self) -> bool: ...
    def structured_field_exists(self, path: str) -> bool: ...
    def structured_field_equals(self, path: str, value: Any) -> bool: ...
    def structured_field_matches(self, path: str, predicate: Callable[[Any], bool]) -> bool: ...
    def structured_field_type(self, path: str, expected_type: type | tuple[type, ...]) -> bool: ...
    def structured_contains_keys(self, keys: Sequence[str]) -> bool: ...
```

#### Logic / Algorithm

1. Store a parent `Behavior` reference.
2. Add private properties `_output` and `_structured` that read `self._behavior.probe`.
3. Add a private `_within(value, at_least, at_most)` helper for inclusive count bounds.
4. Add a private `_resolve_path(path)` helper returning `(exists, value)`.
5. `is_empty`: optionally strip output and compare to `""`.
6. `is_not_empty`: negate `is_empty`.
7. `length`: optionally strip output, compute `len`, pass through `_within`.
8. `line_count`: compute `len(output.splitlines())`, with empty string counting as `0`.
9. `word_count`: use `re.findall(r"\b\w+\b", output)` and apply bounds.
10. `is_valid_json`: call `json.loads(output)` and catch `json.JSONDecodeError` / `ValueError`.
11. `contains_code_block` and `code_block_count`: find fenced blocks with a regex matching triple backticks or tildes. If `language` is supplied, compare the first language token case-insensitively.
12. `contains_url` and `url_count`: use a conservative URL regex for `http://`, `https://`, and `www.`.
13. `contains_citation` and `citation_count`: dispatch to citation matchers by style.
14. `refused`: casefold output and look for refusal phrases.
15. `contains_hedging`: casefold output and look for hedging phrases with word boundaries where appropriate.
16. `starts_with` and `ends_with`: optionally strip and casefold before calling native string methods.
17. `structured_valid`: return `self._structured is not None`.
18. Structured field methods resolve the path and return `False` for missing fields.
19. `structured_field_matches`: call predicate only when the path exists; let predicate exceptions propagate.
20. `structured_contains_keys`: require `structured` to be a mapping or mapping-like Pydantic object converted through `model_dump()`.

#### Edge Cases & Error Handling

- Empty output has length `0`, line count `0`, word count `0`, no JSON, no code block, no URL, no citation.
- Whitespace-only output is empty when `strip=True`, not empty when `strip=False`.
- Invalid JSON returns `False`, not an exception.
- Unclosed code fences do not count as code blocks.
- Unknown citation style raises `ValueError` because that is caller misuse.
- Missing structured data returns `False` for every structured field predicate except `structured_valid`, which returns `False`.
- Empty structured path returns `False` to avoid treating the entire object as a field.
- List indexes must be integer path segments; out-of-range or non-integer indexes return missing.

---

### 6.3 `Behavior` Facade

**File(s):** `vidbyte/evals/behavior/behavior.py`
**Type:** Modified

#### What it does

Composes the new output behavior category with the existing categories.

#### Interface / API

```python
class Behavior:
    @property
    def output(self) -> OutputBehavior: ...
```

#### Logic / Algorithm

1. Import `OutputBehavior`.
2. In `__init__`, set `self._output = OutputBehavior(self)`.
3. Add an `output` property returning `self._output`.
4. Update the module header to list the output category.

#### Edge Cases & Error Handling

- Existing cached `Behavior` semantics remain unchanged.
- `OutputBehavior` reads the same cached probe as all other categories.

---

### 6.4 Behavior Package Exports

**File(s):** `vidbyte/evals/behavior/__init__.py`
**Type:** Modified

#### What it does

Exports `OutputBehavior` from the behavior package.

#### Interface / API

```python
from vidbyte.evals.behavior.output import OutputBehavior
```

#### Logic / Algorithm

1. Import `OutputBehavior`.
2. Add `"OutputBehavior"` to `__all__`.
3. Update the context protocol header to include the output category.

#### Edge Cases & Error Handling

- No change to root `vidbyte.evals` exports unless implementation review decides category classes should be root exported as a separate public-surface decision. Current root exports expose `Behavior` and `RunProbe`, not each category class.

---

### 6.5 SDK Developer Skill Docs

**File(s):** `skills/vidbyte-sdk/agent-behavior.md`
**Type:** Modified

#### What it does

Documents `agent.behavior.output`, its function catalog, and invariants for adding/changing output predicates.

#### Interface / API

N/A - Markdown documentation only.

#### Logic / Algorithm

1. Update the architecture list to include `vidbyte/evals/behavior/output.py`.
2. Add examples for output behavior.
3. Add a function catalog table for `agent.behavior.output`.
4. Add an invariant that arbitrary substring/regex grading belongs in graders, while output behavior owns structural/linguistic response properties.
5. Update verification commands if needed.

#### Edge Cases & Error Handling

N/A - Documentation only.

---

### 6.6 User-Facing Usage Docs

**File(s):** `skills/usage/agent-behavior.md`
**Type:** Modified

#### What it does

Adds usage examples for direct output behavior checks and `PredicateGrader` access to `RunProbe.output` / `RunProbe.structured`.

#### Interface / API

N/A - Markdown documentation only.

#### Logic / Algorithm

1. Update the quick start to mention five sub-properties instead of four.
2. Add an `Output` section with common examples.
3. Add a structured-output subsection.
4. Fix any examples that imply `RunProbe` has behavior methods directly; predicate lambdas should inspect fields or use helper code, not call nonexistent `p.tool_succeeded`.

#### Edge Cases & Error Handling

N/A - Documentation only.

---

### 6.7 Unit and Integration Tests

**File(s):** `tests/test_agent_behavior.py`
**Type:** Modified

#### What it does

Extends the existing behavior test suite with `OutputBehavior` tests.

#### Interface / API

N/A - Tests only.

#### Logic / Algorithm

1. Import `OutputBehavior` where test helper code manually builds `Behavior` objects from probes.
2. Update `behavior_from_probe` to initialize `_output`.
3. Add tests for `RunProbe.structured`.
4. Add tests for every output predicate.
5. Add an integration test that runs `MockAgent` with structured metadata and checks `agent.behavior.output`.
6. Add an eval-runner test that uses `PredicateGrader(lambda p: p.structured is not None and p.output)`.

#### Edge Cases & Error Handling

- Tests must include empty output, whitespace output, missing structured data, nested structured paths, list indexes, invalid JSON, unclosed code fences, and predicate exceptions.

---

### 6.8 Verification Script

**File(s):** `scripts/test-agent-output-behavior.py`
**Type:** New file

#### What it does

Runs every Section 10 test case through a direct script with clear `PASS` / `FAIL` output and a final summary.

#### Interface / API

```powershell
python scripts/test-agent-output-behavior.py
```

#### Logic / Algorithm

1. Import the implemented behavior classes and test helpers.
2. Define one callable per Section 10 test case.
3. Execute each callable, printing `PASS <name>` or `FAIL <name>: <error>`.
4. Print `X/Y tests passed`.
5. Exit with status `1` if any test fails.

#### Edge Cases & Error Handling

- The script must fail fast only per test case, not for the whole suite.
- It must exit non-zero on any failure.

---

## 7. Data Model Changes

### 7.1 `RunProbe`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class RunProbe:
    output: str = ""
    structured: Any = None
```

**Migration strategy:** Additive dataclass field with a default. Existing construction sites keep working. Rollback removes the field and output structured predicates.

---

## 8. API Changes

### 8.1 Python SDK: `agent.behavior.output`

**Change type:** New

**Request:**

```python
agent.behavior.output.is_valid_json()
agent.behavior.output.contains_code_block(language="python")
agent.behavior.output.structured_field_equals("answer", "yes")
```

**Response:**

```python
bool
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Most predicates return `False` for malformed or missing output state. |
| N/A | `contains_citation(style=...)` raises `ValueError` for unknown style. |
| N/A | `structured_field_matches(...)` propagates predicate exceptions. |

### 8.2 Python SDK: `RunProbe.structured`

**Change type:** Modified

**Request:**

```python
probe.structured
```

**Response:**

```python
Any | None
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing structured metadata returns `None`. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-output-behavior.md` | Design doc for this feature |
| CREATE | `vidbyte/evals/behavior/output.py` | New output behavior category |
| CREATE | `scripts/test-agent-output-behavior.py` | Required verification script for this feature |
| MODIFY | `vidbyte/evals/behavior/probe.py` | Add `structured` to `RunProbe` |
| MODIFY | `vidbyte/evals/behavior/behavior.py` | Initialize and expose `OutputBehavior` |
| MODIFY | `vidbyte/evals/behavior/__init__.py` | Export `OutputBehavior` |
| MODIFY | `tests/test_agent_behavior.py` | Add output behavior unit and integration coverage |
| MODIFY | `skills/vidbyte-sdk/agent-behavior.md` | Document architecture and function catalog |
| MODIFY | `skills/usage/agent-behavior.md` | Document user-facing examples |

---

## 10. Testing Plan

### Unit Tests

`RunProbe`:

- [Hidden Assumption] `from_agent` copies `metadata["structured"]` into `probe.structured`.
- [Hidden Assumption] `from_reply` copies `metadata["structured"]` into `probe.structured` without an agent.
- [Edge Case] Missing structured metadata leaves `probe.structured is None`.

`OutputBehavior` emptiness and counts:

- [Edge Case] `is_empty()` returns `True` for `""`.
- [Edge Case] `is_empty(strip=True)` returns `True` for whitespace-only output.
- [Silent Failure] `is_empty(strip=False)` returns `False` for whitespace-only output.
- [Silent Failure] `is_not_empty(strip=True)` is the exact negation of `is_empty(strip=True)`.
- [Edge Case] `length(at_least=0, at_most=0)` returns `True` for empty output.
- [Silent Failure] `length(at_least=2, at_most=4)` is inclusive at both bounds.
- [Edge Case] `line_count(at_least=0, at_most=0)` returns `True` for empty output.
- [Silent Failure] `line_count(at_least=2, at_most=2)` counts `splitlines()` logical lines, not newline characters.
- [Silent Failure] `word_count(at_least=3, at_most=3)` counts word tokens rather than raw whitespace splits.

`OutputBehavior` JSON and Markdown/code:

- [Edge Case] `is_valid_json()` returns `False` for empty output.
- [Hidden Failure] `is_valid_json()` returns `False` for malformed JSON without raising.
- [Silent Failure] `is_valid_json()` returns `True` for valid JSON arrays and objects.
- [Edge Case] `contains_code_block()` returns `False` for no fenced block.
- [Hidden Failure] `contains_code_block()` returns `False` for an unclosed fence.
- [Silent Failure] `contains_code_block(language="python")` matches fence language case-insensitively.
- [Silent Failure] `code_block_count(language="python")` counts only matching language fences.
- [Edge Case] `code_block_count(at_least=0, at_most=0)` returns `True` when no blocks exist.

`OutputBehavior` URLs and citations:

- [Edge Case] `contains_url()` returns `False` for output without URLs.
- [Silent Failure] `contains_url()` detects `https://`, `http://`, and `www.` forms.
- [Silent Failure] `url_count(at_least=2, at_most=2)` counts two URLs, not one line.
- [Edge Case] `contains_citation(style="any")` returns `False` when no citation-like marker exists.
- [Silent Failure] `contains_citation(style="markdown")` detects `[text](https://example.com)`.
- [Silent Failure] `contains_citation(style="bracket")` detects bracket citations like `[1]`.
- [Silent Failure] `contains_citation(style="footnote")` detects footnotes like `[^1]`.
- [Silent Failure] `contains_citation(style="url")` delegates to URL detection.
- [Hidden Failure] Unknown citation style raises `ValueError`.

`OutputBehavior` refusal, hedging, prefix, and suffix:

- [Silent Failure] `refused()` detects "I can't", "I cannot", and "I'm unable to" case-insensitively.
- [Edge Case] `refused()` returns `False` for ordinary text containing "can" but not a refusal phrase.
- [Silent Failure] `contains_hedging()` detects "maybe", "possibly", "I think", and "likely" case-insensitively.
- [Edge Case] `contains_hedging()` returns `False` for decisive output.
- [Silent Failure] `starts_with(prefix, case_sensitive=False)` casefolds both sides.
- [Silent Failure] `ends_with(suffix, strip=True)` ignores trailing whitespace.
- [Edge Case] Empty prefix and suffix follow Python string behavior and return `True`.

`OutputBehavior` structured fields:

- [Edge Case] `structured_valid()` returns `False` when structured is `None`.
- [Edge Case] `structured_valid()` returns `True` for an empty dict because it is not `None`.
- [Silent Failure] `structured_field_exists("answer")` returns `True` when the key exists with a falsey value.
- [Hidden Failure] `structured_field_exists("missing")` returns `False` without raising.
- [Silent Failure] `structured_field_exists("items.0.title")` resolves nested list indexes.
- [Hidden Failure] `structured_field_exists("items.x.title")` returns `False` for a non-integer list index.
- [Hidden Failure] `structured_field_exists("items.99.title")` returns `False` for an out-of-range list index.
- [Silent Failure] `structured_field_equals("count", 0)` compares with `==`, preserving falsey values.
- [Hidden Assumption] `structured_field_matches("score", lambda v: v > 0.8)` calls the predicate only when the field exists.
- [Hidden Failure] `structured_field_matches("score", bad_predicate)` propagates predicate exceptions.
- [Silent Failure] `structured_field_type("items", list)` returns `True` only for the actual resolved type.
- [Silent Failure] `structured_contains_keys(["a", "b"])` requires every requested top-level key.
- [Hidden Assumption] Pydantic structured objects are supported through `model_dump()` if available.

`Behavior` facade:

- [Edge Case] `agent.behavior.output` returns an `OutputBehavior`.
- [Silent Failure] repeated `agent.behavior.output` access returns the same category object for the cached facade.
- [Hidden Assumption] `OutputBehavior` reads the same cached `RunProbe` as other categories.

### Integration Tests

- [Hidden Assumption] A `MockAgent` reply with `metadata={"structured": {"answer": "yes"}}` supports `agent.behavior.output.structured_field_equals("answer", "yes")` after `await agent.arun(...)`.
- [Silent Failure] A `MockAgent` reply with a fenced Python block supports `agent.behavior.output.contains_code_block("python")`.
- [Hidden Failure] `EvalRunner` plus `PredicateGrader(lambda p: p.structured is not None)` passes when the forked agent reply metadata contains structured output.
- [Hidden Failure] `EvalRunner` plus a standard `ContainsGrader` still uses the existing `agrade` path and ignores output behavior.
- [Silent Failure] Cache invalidation after a second run updates `agent.behavior.output` to read the second run's output.

### Manual / QA Test Cases

1. [Edge Case] Given an agent that returns an empty string, when `agent.behavior.output.is_empty()` is called, then it returns `True`.
2. [Silent Failure] Given an agent that returns a Markdown Python fence, when `agent.behavior.output.contains_code_block("python")` is called, then it returns `True`.
3. [Hidden Failure] Given an agent that returns malformed JSON, when `agent.behavior.output.is_valid_json()` is called, then it returns `False` rather than raising.
4. [Hidden Assumption] Given an agent configured with `output_schema` whose parsed result is stored in `reply.metadata["structured"]`, when `agent.behavior.output.structured_valid()` is called, then it returns `True`.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `json` stdlib | Python 3.11+ | Validate raw JSON output | None |
| Python `re` stdlib | Python 3.11+ | Deterministic structural text detection | Regexes must stay conservative |
| `collections.abc.Mapping`, `Sequence`, `Callable` | Python 3.11+ | Structured path and type contracts | None |
| Existing `RunProbe` / `Behavior` | Local SDK | Behavior integration point | Must preserve current API |
| Existing `AgentResult.structured` / `reply.metadata["structured"]` | Local SDK | Structured source of truth | Missing metadata means structured predicates return false |

No external services are added.

---

## 12. Rollout & Deployment

- Feature flags: none.
- Breaking change: no. All additions are optional and backward compatible.
- Deployment order: single SDK package PR.
- Migration path: existing behavior calls continue unchanged.
- Rollback procedure: revert the feature PR. The only data model change is an additive in-memory dataclass field.
- Verification before PR: `python -m compileall vidbyte`, `python -m unittest tests.test_agent_behavior`, and `python scripts/test-agent-output-behavior.py`.

---

## 13. Open Questions

- [ ] Should count methods return `int` when no bounds are passed and `bool` when bounds are passed, as designed here, or should they always return `int` and require separate `*_within` predicates?
- [ ] Should `OutputBehavior` include `contains_table`, `contains_list`, and `contains_heading` in this first PR, or defer those Markdown-shape predicates until there is a concrete eval use case?
- [ ] Should `OutputBehavior` expose a classmethod such as `from_probe(probe)` for direct `PredicateGrader` use, or should direct probe lambdas remain the intended suite-level pattern?

---

## 14. Alternatives Considered

### Alternative 1: Add More Graders Instead

- What: Create `OutputShapeGrader`, `RefusalGrader`, `CodeBlockGrader`, and `StructuredFieldGrader` under `vidbyte/evals/graders/`.
- Why rejected: The user asked for first-class agent behavior functions. Graders are useful at suite level, but they do not give the direct post-run ergonomics of `agent.behavior.output.*`.

### Alternative 2: Put Output Methods Directly On `Behavior`

- What: Add `agent.behavior.output_is_empty()` and similar flat methods.
- Why rejected: Existing design uses category objects to keep the facade organized. A flat API would mix tool, stop, handoff, and output methods into one large surface.

### Alternative 3: Duplicate Contains And Regex Graders

- What: Add `output_contains(substring)` and `output_matches(pattern)`.
- Why rejected: That duplicates `ContainsGrader` and `RegexMatchGrader`. This feature should own structural and linguistic properties, not arbitrary caller-defined content matching.

### Alternative 4: Parse Raw JSON For Structured Field Predicates

- What: If `probe.structured` is `None`, parse `probe.output` and use that for structured fields.
- Why rejected: `structured` should mean provider/runtime-validated structured output. Raw JSON validity is available through `is_valid_json()`, and schema validation belongs to existing structured-output machinery.

### Alternative 5: Add A Markdown Parser Dependency

- What: Depend on a Markdown parser to identify code blocks, headings, lists, tables, and citations.
- Why rejected: The SDK currently keeps behavior predicates dependency-free. Conservative regex detection is enough for this feature and avoids expanding package requirements.
