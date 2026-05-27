# Design Doc: LLM-as-a-Judge Strategy Library (vidbyte.evals.llm_as_a_judge)

**Status:** Draft  
**Author:** Claude  
**Created:** 2026-05-27  
**Last Updated:** 2026-05-27  

---

## 1. Overview

This feature adds `vidbyte/evals/llm_as_a_judge/`, a library of 19 distinct LLM-as-a-judge grading strategies that developers can import and compose out of the box. Each strategy is a concrete `BaseGrader` subclass covering a different dimension of judgment: reasoning strategy (e.g. chain-of-thought before scoring), agent architecture (e.g. panel of judges, debate), rubric design (e.g. structured per-level anchors, constitutional principles), and evaluation mode (e.g. pairwise A-vs-B, atomic claim verification). All prompt text lives in `vidbyte/prompts/prompts/llm_as_a_judge/` as markdown files, registered through the existing enum → JSON manifest → catalog pipeline.

**Depends on:** PR #59 (`feat/sdk-evals`) must be merged or present as the base branch before this feature lands. All strategies extend the `BaseGrader` ABC introduced in that PR.

---

## 2. Goals & Non-Goals

### Goals
- Provide 19 production-ready LLM judge strategy classes under `vidbyte.evals.llm_as_a_judge`, each with meaningful default behaviour and explicit, typed override parameters.
- Store all prompt text in `vidbyte/prompts/prompts/llm_as_a_judge/` markdown files registered through the canonical Prompt enum and catalog pipeline.
- Eliminate copy-paste across strategy files with a shared `_utils.py` module.
- Export all strategies from `vidbyte.evals` and `vidbyte` top-level namespaces.
- Cover the three strategies the user explicitly requested: `MetaJudge`, `StructuredRubricJudge`, `MixtureOfPromptsJudge`.
- Include a verification script and full test coverage.

### Non-Goals
- Token-probability / logit-weighted scoring (requires raw model internals not exposed by the runner interface).
- Fine-tuned or reward model as judge (infrastructure concern; users point `judge_runner` at their own endpoint).
- Generator + Critic / REFINER loop (the generator is the user's agent, outside grader scope).
- Closed-loop agentic judge (pipeline pattern, not a grader primitive).
- Listwise ranking across N responses as a grader (EvalRunner operates on one `actual` at a time).
- Multimodal (image) input — text-only runners only.

---

## 3. Background & Context

PR #59 introduces `vidbyte.evals` with two LLM-based graders: `LLMJudgeGrader` (pointwise, single call, JSON output) and `RubricGrader` (multi-dimensional weighted average). Both accept a `judge_runner` and an optional `prompt_template` override. The research literature and open-source eval frameworks show at least 19 meaningfully distinct judging strategies that vary across six dimensions: comparison mode, output format, reasoning strategy, rubric design, agent architecture, and model type. This feature makes all implementable strategies available as first-class SDK primitives without adding external dependencies.

---

## 4. Requirements

### Functional Requirements
1. Every strategy must inherit `BaseGrader` and implement `async agrade(case: EvalCase, actual: str) -> GraderResult`.
2. Every strategy must accept `judge_runner` as its first keyword argument (the runner callable).
3. Every strategy must accept `prompt_template: str | None = None` to fully override the SDK default prompt.
4. Every strategy must accept `system_prompt: str | None = None` to override only the system message where applicable.
5. Strategy-specific parameters must use `Literal` types for fixed-choice options (e.g. `cot_length`, `aggregation`, `framing`).
6. `PairwiseJudge` reads `response_b` from `case.metadata["response_b"]`; raises `ValueError` if missing.
7. Multi-runner strategies (`PanelJudge`, `MultiAgentRubricJudge`, `MultiAgentDebateJudge`, `PeerReviewJudge`) must invoke all runners concurrently via `asyncio.gather`.
8. Multi-call strategies (`CriteriaDecompositionJudge`, `AtomicClaimsJudge`, `LLMRubricJudge`, `SelfReferenceJudge`, `BranchSolveMergeJudge`) must make sub-calls within `agrade` via the shared `_invoke_runner` utility.
9. All prompt text must be registered through the `Prompt` enum and loaded via `Prompts().get(Prompt.KEY)`, falling back to an inline default string if the catalog lookup fails.
10. `vidbyte/evals/llm_as_a_judge/__init__.py` must export all 19 strategy classes.
11. `vidbyte/evals/__init__.py` must re-export all 19 strategy classes.
12. `vidbyte/__init__.py` must re-export all 19 strategy classes.

### Non-Functional Requirements
- No new third-party dependencies; all strategies use only the Python standard library and the existing runner interface.
- Multi-runner parallel strategies must not block on sequential API calls; `asyncio.gather` is mandatory.
- Each strategy must be importable independently: `from vidbyte.evals.llm_as_a_judge import ChainOfThoughtJudge`.
- Shared logic (runner invocation, JSON parsing, response extraction) must live exclusively in `_utils.py`.

---

## 5. High-Level Design

The library lives under `vidbyte/evals/llm_as_a_judge/` as a Python package. Each of the 19 strategy files contains exactly one class that extends `BaseGrader`. A shared `_utils.py` provides `invoke_runner(runner, prompt, temperature) -> str` and `parse_json_block(text) -> dict` so no runner-dispatch or JSON-extraction logic is duplicated.

All prompt text is stored in `vidbyte/prompts/prompts/llm_as_a_judge/` as markdown files (one per distinct prompt), referenced by a single JSON manifest `llm_as_a_judge.json`. Enum members are added to `vidbyte/lib/enums/prompts.py` and a new `LlmAsAJudgePrompts` bundle class is added to `vidbyte/prompts/strategies/strategy_prompts.py`.

```
[Developer]
    |
    v
from vidbyte.evals.llm_as_a_judge import ChainOfThoughtJudge
    |
    v
ChainOfThoughtJudge(judge_runner=runner, cot_length="medium")
    |
    v
EvalRunner.arun(suite) -> calls grader.agrade(case, actual)
    |
    v
_utils.invoke_runner(judge_runner, rendered_prompt) -> raw_text
    |
    v
_utils.parse_json_block(raw_text) -> {"score": 0.9, "passed": True, "reason": "..."}
    |
    v
GraderResult(score=0.9, passed=True, reason="...")
```

Multi-runner strategies (Panel, Debate, PeerReview, MultiAgentRubric):
```
agrade()
  ├── asyncio.gather(runner_1.arun(...), runner_2.arun(...), runner_3.arun(...))
  └── aggregate(results) -> GraderResult
```

Multi-call single-runner strategies (CriteriaDecomposition, AtomicClaims, LLMRubric, SelfReference):
```
agrade()
  ├── call_1: sub-task (decompose / generate / extract)
  └── call_2: evaluation using sub-task output -> GraderResult
```

---

## 6. Detailed Design

### 6.1 `vidbyte/evals/llm_as_a_judge/_utils.py`

**File:** `vidbyte/evals/llm_as_a_judge/_utils.py`  
**Type:** New file

#### What it does
Shared utilities to eliminate code duplication across all 19 strategy files: runner dispatch (supports `arun`, `generate_reply`, `run` sync/async), response text extraction, and JSON block parsing.

#### Interface / API
```python
async def invoke_runner(runner: object, prompt: str, temperature: float = 0.0) -> str: ...
def parse_json_block(text: str) -> dict: ...
def extract_text(res: object) -> str: ...
```

#### Logic / Algorithm
1. `invoke_runner`: checks for `arun`, `generate_reply`, `async run`, `sync run` in that order; raises `TypeError` if none found. Calls `extract_text` on result.
2. `extract_text`: handles `str`, `.text`, `.content`, `dict["text"]`, falls back to `str(res)`.
3. `parse_json_block`: uses `re.search(r"\{.*\}", text, re.DOTALL)` to extract first JSON object; raises `ValueError` if not found or parse fails.

---

### 6.2 `ChainOfThoughtJudge`

**File:** `vidbyte/evals/llm_as_a_judge/chain_of_thought.py`  
**Type:** New file

#### What it does
Instructs the judge to write a step-by-step reasoning chain before emitting a final numeric score, producing better-calibrated scores that are constrained by the judge's own reasoning (G-Eval style).

#### Interface / API
```python
class ChainOfThoughtJudge(BaseGrader):
    name: ClassVar[str] = "chain_of_thought"

    def __init__(
        self,
        *,
        judge_runner: object,
        cot_length: Literal["short", "medium", "long"] = "medium",
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Resolve prompt template (user override → catalog → inline default).
2. Inject `cot_length` as a word-budget instruction: short=`"~2 sentences"`, medium=`"3–5 sentences"`, long=`"as many steps as needed"`.
3. Format prompt with `{prompt}`, `{actual}`, `{expected}`, `{cot_budget}`.
4. Invoke runner; parse response for trailing `Score: X.XX` line (regex: `Score:\s*([\d.]+)`); fall back to JSON block parse.
5. Return `GraderResult`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_CHAIN_OF_THOUGHT_USER`

---

### 6.3 `BinaryJudge`

**File:** `vidbyte/evals/llm_as_a_judge/binary.py`  
**Type:** New file

#### What it does
Asks the judge a single yes/no question defined by `criterion`. Output is `score=1.0/0.0`, `passed=True/False`. Suitable for safety checks, hallucination flags, format compliance.

#### Interface / API
```python
class BinaryJudge(BaseGrader):
    name: ClassVar[str] = "binary"

    def __init__(
        self,
        *,
        judge_runner: object,
        criterion: str,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Format prompt with `{criterion}`, `{prompt}`, `{actual}`, `{expected}`.
2. Parse response: look for `yes`/`no`/`pass`/`fail` case-insensitively in first 50 chars; fall back to JSON `{"passed": bool}`.
3. Return `score=1.0` if pass, `score=0.0` if fail.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_BINARY_USER`

---

### 6.4 `FewShotJudge`

**File:** `vidbyte/evals/llm_as_a_judge/few_shot.py`  
**Type:** New file

#### What it does
Prepends calibrated worked examples to the evaluation prompt, anchoring the judge's scale so scores are consistent across runs and aligned to developer intent.

#### Interface / API
```python
class FewShotJudge(BaseGrader):
    name: ClassVar[str] = "few_shot"

    def __init__(
        self,
        *,
        judge_runner: object,
        examples: list[dict],  # keys: prompt, actual, expected, score, reason
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Serialize `examples` into a formatted block: each example shows prompt, response, expected, then score+reason.
2. Prepend serialized block to the main evaluation prompt.
3. Format with `{examples_block}`, `{prompt}`, `{actual}`, `{expected}`.
4. Parse JSON: `{"score": float, "passed": bool, "reason": str}`.
5. Validate that `examples` is non-empty list of dicts with required keys; raise `ValueError` otherwise.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_FEW_SHOT_USER`

---

### 6.5 `PairwiseJudge`

**File:** `vidbyte/evals/llm_as_a_judge/pairwise.py`  
**Type:** New file

#### What it does
Compares two responses (A and B) to the same prompt. With `swap_check=True`, runs both orderings and only declares a winner if both agree; otherwise records a tie. Debiases LLM position preference.

#### Interface / API
```python
class PairwiseJudge(BaseGrader):
    name: ClassVar[str] = "pairwise"

    def __init__(
        self,
        *,
        judge_runner: object,
        swap_check: bool = True,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Read `response_b = case.metadata.get("response_b")`; raise `ValueError` if absent.
2. Format prompt (A=`actual`, B=`response_b`) → call judge → parse `{"winner": "A"|"B"|"Tie", "reason": str}`.
3. If `swap_check`: re-run with A/B swapped → parse second verdict.
4. Consensus: both say A → winner=A; both say B → winner=B; disagreement → Tie.
5. Return `score=1.0` if `actual` wins, `0.5` if tie, `0.0` if `response_b` wins.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_PAIRWISE_USER`

---

### 6.6 `SelfReferenceJudge`

**File:** `vidbyte/evals/llm_as_a_judge/self_reference.py`  
**Type:** New file

#### What it does
Before evaluating, the judge generates its own answer to the prompt (optionally multiple times with majority vote as consensus). Uses that self-generated answer as a soft reference instead of `case.expected`.

#### Interface / API
```python
class SelfReferenceJudge(BaseGrader):
    name: ClassVar[str] = "self_reference"

    def __init__(
        self,
        *,
        judge_runner: object,
        num_self_generations: int = 1,
        system_prompt: str | None = None,
        generation_prompt_template: str | None = None,
        eval_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Run `num_self_generations` generation calls concurrently, each asking judge to answer `case.prompt`.
2. If `num_self_generations > 1`: use first generation as soft reference (true majority-vote consensus requires semantic comparison, out of scope).
3. Run evaluation call: compare `actual` against self-generated reference.
4. Parse JSON → return `GraderResult`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_SELF_REFERENCE_GENERATION`
- `Prompt.LLM_AS_A_JUDGE_SELF_REFERENCE_EVAL`

---

### 6.7 `CriteriaDecompositionJudge`

**File:** `vidbyte/evals/llm_as_a_judge/criteria_decomposition.py`  
**Type:** New file

#### What it does
Two-call strategy. First call expands a high-level criterion (e.g. "helpfulness") into a numbered checklist of specific sub-questions. Second call evaluates the response against that checklist.

#### Interface / API
```python
class CriteriaDecompositionJudge(BaseGrader):
    name: ClassVar[str] = "criteria_decomposition"

    def __init__(
        self,
        *,
        judge_runner: object,
        criterion: str,
        num_sub_criteria: int = 4,
        system_prompt: str | None = None,
        decomposition_prompt_template: str | None = None,
        eval_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Call 1: format decomposition prompt with `{criterion}`, `{num_sub_criteria}` → receive numbered checklist as raw text.
2. Call 2: format eval prompt with `{checklist}`, `{prompt}`, `{actual}`, `{expected}` → parse JSON score.
3. Return `GraderResult`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_DECOMPOSE`
- `Prompt.LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_EVAL`

---

### 6.8 `ChainOfAspectsJudge`

**File:** `vidbyte/evals/llm_as_a_judge/chain_of_aspects.py`  
**Type:** New file

#### What it does
Evaluates a fixed ordered list of aspects sequentially, writing a short prose evaluation for each before producing a final score. Distinct from `RubricGrader` — produces full written rationale per aspect, not just a number.

#### Interface / API
```python
class ChainOfAspectsJudge(BaseGrader):
    name: ClassVar[str] = "chain_of_aspects"

    def __init__(
        self,
        *,
        judge_runner: object,
        aspects: list[str],
        words_per_aspect: int = 30,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `aspects` is non-empty; raise `ValueError` otherwise.
2. Serialize aspects into instructional lines: `"1. Evaluate {aspect}. Write ~{words_per_aspect} words. 2. Evaluate ..."`.
3. Format prompt with `{aspects_instructions}`, `{prompt}`, `{actual}`, `{expected}`.
4. Parse JSON: `{"scores": {aspect: float}, "reasons": {aspect: str}, "overall": float}`.
5. Compute `overall` as mean of aspect scores if not returned by model.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_CHAIN_OF_ASPECTS_USER`

---

### 6.9 `BranchSolveMergeJudge`

**File:** `vidbyte/evals/llm_as_a_judge/branch_solve_merge.py`  
**Type:** New file

#### What it does
Splits evaluation into independent branch sub-tasks (each a separate LLM call in parallel), then merges results via weighted mean or a final LLM merge call.

#### Interface / API
```python
class BranchSolveMergeJudge(BaseGrader):
    name: ClassVar[str] = "branch_solve_merge"

    def __init__(
        self,
        *,
        judge_runner: object,
        branches: dict[str, str],  # {branch_name: rubric_description}
        branch_weights: dict[str, float] | None = None,
        merge_strategy: Literal["weighted_mean", "llm"] = "weighted_mean",
        system_prompt: str | None = None,
        branch_prompt_template: str | None = None,
        merge_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Launch `len(branches)` concurrent calls, each formatted with its `{branch_name}`, `{rubric}`, `{prompt}`, `{actual}`, `{expected}`.
2. Parse each branch response: `{"score": float, "reason": str}`.
3. If `merge_strategy == "weighted_mean"`: compute weighted average using `branch_weights` (equal weights if `None`).
4. If `merge_strategy == "llm"`: format merge prompt with all branch scores and reasons → single merge call → parse `{"score": float, "reason": str}`.
5. `passed = score >= 0.7`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_BRANCH`
- `Prompt.LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_MERGE`

---

### 6.10 `LLMRubricJudge`

**File:** `vidbyte/evals/llm_as_a_judge/llm_rubric.py`  
**Type:** New file

#### What it does
Two-call strategy: first call generates a rubric from a task description; second call evaluates using the generated rubric. Scales rubric creation to new task types without manual writing.

#### Interface / API
```python
class LLMRubricJudge(BaseGrader):
    name: ClassVar[str] = "llm_rubric"

    def __init__(
        self,
        *,
        judge_runner: object,
        task_description: str,
        rubric_scale: int = 5,
        system_prompt: str | None = None,
        rubric_generation_prompt_template: str | None = None,
        eval_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Call 1: format rubric generation prompt with `{task_description}`, `{rubric_scale}` → receive rubric as plain text.
2. Cache rubric on `self._cached_rubric` after first call (rubric is stable per instance, not per case).
3. Call 2: format eval prompt with `{rubric}`, `{prompt}`, `{actual}`, `{expected}` → parse JSON.
4. Return `GraderResult`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_LLM_RUBRIC_GENERATE`
- `Prompt.LLM_AS_A_JUDGE_LLM_RUBRIC_EVAL`

---

### 6.11 `StructuredRubricJudge`

**File:** `vidbyte/evals/llm_as_a_judge/structured_rubric.py`  
**Type:** New file

#### What it does
Multi-dimensional evaluation where each dimension has explicit per-level anchor descriptions (e.g. 1="multiple factual errors", 3="mostly accurate", 5="fully accurate and precise"). Distinct from `RubricGrader` which only takes a weight, not level descriptions.

#### Interface / API
```python
class StructuredRubricJudge(BaseGrader):
    name: ClassVar[str] = "structured_rubric"

    def __init__(
        self,
        *,
        judge_runner: object,
        dimensions: dict[str, dict[int, str]],  # {dim: {level: description}}
        weights: dict[str, float] | None = None,
        threshold: float = 0.7,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Serialize `dimensions` into a rubric block: for each dimension, list each level with its description.
2. Format prompt with `{rubric_block}`, `{prompt}`, `{actual}`, `{expected}`.
3. Parse JSON: `{"scores": {dim: int}, "reasons": {dim: str}}`.
4. Normalise scores to 0.0–1.0 by dividing by max level key in each dimension.
5. Compute weighted average using `weights` (equal if `None`). `passed = final >= threshold`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_STRUCTURED_RUBRIC_USER`

---

### 6.12 `AtomicClaimsJudge`

**File:** `vidbyte/evals/llm_as_a_judge/atomic_claims.py`  
**Type:** New file

#### What it does
Two-call factuality evaluator. First call decomposes the response into a list of atomic factual claims. Second call verifies each claim independently (parallel). Score = fraction of claims verified as true.

#### Interface / API
```python
class AtomicClaimsJudge(BaseGrader):
    name: ClassVar[str] = "atomic_claims"

    def __init__(
        self,
        *,
        judge_runner: object,
        threshold: float = 0.8,
        system_prompt: str | None = None,
        decomposition_prompt_template: str | None = None,
        verification_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Call 1: extract claims from `actual` → parse JSON: `{"claims": ["claim 1", "claim 2", ...]}`.
2. If claims list is empty: return `GraderResult(score=1.0, passed=True, reason="No factual claims found.")`.
3. Launch concurrent verification calls (one per claim) → parse each: `{"verified": bool, "reason": str}`.
4. `score = verified_count / total_claims`. `passed = score >= threshold`.
5. Include per-claim verdicts in reason summary.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_ATOMIC_CLAIMS_DECOMPOSE`
- `Prompt.LLM_AS_A_JUDGE_ATOMIC_CLAIMS_VERIFY`

---

### 6.13 `ConstitutionalJudge`

**File:** `vidbyte/evals/llm_as_a_judge/constitutional.py`  
**Type:** New file

#### What it does
Checks the response against a fixed list of named principles (each a short declarative statement). Runs one binary check per principle in parallel. Final score = fraction of principles satisfied.

#### Interface / API
```python
class ConstitutionalJudge(BaseGrader):
    name: ClassVar[str] = "constitutional"

    def __init__(
        self,
        *,
        judge_runner: object,
        principles: list[str],
        threshold: float = 1.0,
        system_prompt: str | None = None,
        check_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `principles` is non-empty; raise `ValueError` otherwise.
2. Launch concurrent checks (one per principle), each formatted with `{principle}`, `{prompt}`, `{actual}`.
3. Parse each: `{"violated": bool, "reason": str}`.
4. `score = satisfied / total_principles`. `passed = score >= threshold`.
5. Report which principles were violated in reason.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_CONSTITUTIONAL_CHECK`

---

### 6.14 `PanelJudge`

**File:** `vidbyte/evals/llm_as_a_judge/panel.py`  
**Type:** New file

#### What it does
Sends the same evaluation prompt to multiple different judge runners concurrently and aggregates their scores via mean, median, or majority vote. Reduces individual model bias.

#### Interface / API
```python
class PanelJudge(BaseGrader):
    name: ClassVar[str] = "panel"

    def __init__(
        self,
        *,
        judge_runners: list,
        aggregation: Literal["mean", "median", "majority_vote"] = "mean",
        threshold: float = 0.7,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `judge_runners` has at least 2 entries; raise `ValueError` otherwise.
2. Format prompt once; send to all runners concurrently via `asyncio.gather`.
3. Parse each JSON: `{"score": float, "passed": bool, "reason": str}`.
4. Aggregate: `mean` → average scores; `median` → sorted midpoint; `majority_vote` → majority of `passed` booleans.
5. Combine reasons with runner index labels.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_PANEL_USER`

---

### 6.15 `MultiAgentRubricJudge`

**File:** `vidbyte/evals/llm_as_a_judge/multi_agent_rubrics.py`  
**Type:** New file

#### What it does
Different judge agents specialise in different evaluation dimensions. Each agent receives a specialised rubric. All agents run in parallel; results are aggregated via weighted sum or an LLM merge call.

#### Interface / API
```python
class MultiAgentRubricJudge(BaseGrader):
    name: ClassVar[str] = "multi_agent_rubric"

    def __init__(
        self,
        *,
        agents: list[tuple[object, str]],  # [(runner, rubric_description), ...]
        weights: list[float] | None = None,
        merge_strategy: Literal["weighted_mean", "llm"] = "weighted_mean",
        merge_runner: object | None = None,
        threshold: float = 0.7,
        system_prompt: str | None = None,
        agent_prompt_template: str | None = None,
        merge_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `agents` ≥ 2; raise `ValueError` otherwise.
2. Format agent-specific prompt for each (runner, rubric) pair → run all concurrently.
3. Parse each: `{"score": float, "reason": str}`.
4. Aggregate using `merge_strategy` (same logic as `BranchSolveMergeJudge`).
5. If `merge_strategy == "llm"`, `merge_runner` must not be `None`; raise `ValueError` otherwise.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_RUBRIC_AGENT`
- `Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_RUBRIC_MERGE`

---

### 6.16 `MultiAgentDebateJudge`

**File:** `vidbyte/evals/llm_as_a_judge/multi_agent_debate.py`  
**Type:** New file

#### What it does
Implements ChatEval-style debate. Judges first independently produce verdicts. Then in debate rounds each judge sees others' verdicts and may revise. Final verdict by majority vote. Surfaces reasoning errors that individual judges would make silently.

#### Interface / API
```python
class MultiAgentDebateJudge(BaseGrader):
    name: ClassVar[str] = "multi_agent_debate"

    def __init__(
        self,
        *,
        judge_runners: list,
        debate_rounds: int = 1,
        require_dissent: bool = True,
        threshold: float = 0.7,
        system_prompt: str | None = None,
        initial_prompt_template: str | None = None,
        debate_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `judge_runners` ≥ 2; `debate_rounds` ≥ 1; raise `ValueError` otherwise.
2. Round 0: all judges evaluate independently (concurrent). Parse `{"score": float, "passed": bool, "reason": str}`.
3. For each debate round: share all previous verdicts with all judges; each produces revised verdict (concurrent).
4. Final: majority vote on `passed`; mean of final scores. If tie (even number of judges), use mean score ≥ threshold.
5. `require_dissent=True` includes instruction that judges may maintain disagreement.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_INITIAL`
- `Prompt.LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_ROUND`

---

### 6.17 `MetaJudge`

**File:** `vidbyte/evals/llm_as_a_judge/meta_judge.py`  
**Type:** New file

#### What it does
Runs a primary judge first, then passes its verdict to a meta-judge that checks coherence, consistency of rationale with score, and coverage of evaluation criteria. If the meta-judge flags the verdict as poor quality, the result is either filtered (zeroed) or the primary score is preserved with a warning flag in `reason`.

#### Interface / API
```python
class MetaJudge(BaseGrader):
    name: ClassVar[str] = "meta_judge"

    def __init__(
        self,
        *,
        primary_judge: BaseGrader,
        meta_runner: object,
        filter_on_fail: bool = True,
        system_prompt: str | None = None,
        meta_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Call `primary_judge.agrade(case, actual)` → `primary_result: GraderResult`.
2. Format meta prompt with `{prompt}`, `{actual}`, `{expected}`, `{primary_score}`, `{primary_reason}`.
3. Parse meta response: `{"quality_ok": bool, "quality_reason": str}`.
4. If `quality_ok`: return `primary_result`.
5. If not `quality_ok` and `filter_on_fail`: return `GraderResult(score=0.0, passed=False, reason=f"Meta-judge flagged: {quality_reason}")`.
6. If not `quality_ok` and not `filter_on_fail`: return `primary_result` with `reason` prepended with `"[Meta-judge flagged] "`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_META_JUDGE_USER`

---

### 6.18 `PeerReviewJudge`

**File:** `vidbyte/evals/llm_as_a_judge/peer_review.py`  
**Type:** New file

#### What it does
Multiple judge agents each produce a verdict AND a confidence score (0.0–1.0). Final vote is weighted by confidence. Judges with confidence below `confidence_threshold` are excluded from the final aggregate.

#### Interface / API
```python
class PeerReviewJudge(BaseGrader):
    name: ClassVar[str] = "peer_review"

    def __init__(
        self,
        *,
        judge_runners: list,
        confidence_threshold: float = 0.5,
        threshold: float = 0.7,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `judge_runners` ≥ 2; raise `ValueError` otherwise.
2. Send identical prompt to all runners concurrently. Parse each: `{"score": float, "passed": bool, "confidence": float, "reason": str}`.
3. Filter to verdicts with `confidence >= confidence_threshold`. If all filtered out, fall back to all verdicts.
4. Compute confidence-weighted average score: `sum(score * confidence) / sum(confidence)`.
5. `passed = weighted_score >= threshold`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_PEER_REVIEW_USER`

---

### 6.19 `MixtureOfPromptsJudge`

**File:** `vidbyte/evals/llm_as_a_judge/mixture_of_prompts.py`  
**Type:** New file

#### What it does
Dynamically routes each evaluation to the most appropriate prompt template from a named library, based on input characteristics. The router can be an LLM call or a user-provided `Callable[[str], str]` for deterministic (e.g. keyword-based) routing without an extra API call.

#### Interface / API
```python
class MixtureOfPromptsJudge(BaseGrader):
    name: ClassVar[str] = "mixture_of_prompts"

    def __init__(
        self,
        *,
        judge_runner: object,
        prompt_library: dict[str, str],  # {task_type: prompt_template_str}
        router_runner: object | None = None,
        router_fn: Callable[[str], str] | None = None,
        fallback_key: str | None = None,
        system_prompt: str | None = None,
        router_prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Validate `prompt_library` is non-empty; exactly one of `router_runner` or `router_fn` is set (or neither for fallback-only mode); raise `ValueError` on violations.
2. Route: if `router_fn` provided, call synchronously → get key. Elif `router_runner` provided, format router prompt with `{task_types}`, `{prompt}` → invoke runner → extract first word/JSON key. Else use `fallback_key`.
3. Look up selected key in `prompt_library`; if not found, use `fallback_key` if set; else raise `KeyError`.
4. Format selected template with `{prompt}`, `{actual}`, `{expected}` → invoke judge → parse JSON.
5. Return `GraderResult`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_MIXTURE_OF_PROMPTS_ROUTER`

---

### 6.20 `SelfEvalJudge`

**File:** `vidbyte/evals/llm_as_a_judge/self_eval.py`  
**Type:** New file

#### What it does
Uses the same model as both generator and judge, but frames the evaluation in third-person to reduce self-preference bias. Cheapest possible setup — one runner, one API key.

#### Interface / API
```python
class SelfEvalJudge(BaseGrader):
    name: ClassVar[str] = "self_eval"

    def __init__(
        self,
        *,
        judge_runner: object,
        framing: Literal["third_person", "anonymous"] = "third_person",
        system_prompt: str | None = None,
        prompt_template: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm
1. Select framing: `"third_person"` → prompt refers to the response as "another assistant's response"; `"anonymous"` → prompt says "an AI assistant's response" with no identity cues.
2. Format prompt with `{framing_header}`, `{prompt}`, `{actual}`, `{expected}`.
3. Parse JSON → return `GraderResult`.

#### Prompt keys
- `Prompt.LLM_AS_A_JUDGE_SELF_EVAL_USER`

---

### 6.21 Prompt Assets

**Directory:** `vidbyte/prompts/prompts/llm_as_a_judge/`  
**Type:** New directory

#### JSON Manifest (`llm_as_a_judge.json`)
```json
{
  "name": "LLM-as-a-Judge Strategies",
  "description": "Prompt templates for the 19 LLM-as-a-judge evaluation strategies.",
  "key": "llm_as_a_judge",
  "prompts": {
    "chain_of_thought_user":        { "path": "chain_of_thought_user.md" },
    "binary_user":                  { "path": "binary_user.md" },
    "few_shot_user":                { "path": "few_shot_user.md" },
    "pairwise_user":                { "path": "pairwise_user.md" },
    "self_reference_generation":    { "path": "self_reference_generation.md" },
    "self_reference_eval":          { "path": "self_reference_eval.md" },
    "criteria_decomposition_decompose": { "path": "criteria_decomposition_decompose.md" },
    "criteria_decomposition_eval":  { "path": "criteria_decomposition_eval.md" },
    "chain_of_aspects_user":        { "path": "chain_of_aspects_user.md" },
    "branch_solve_merge_branch":    { "path": "branch_solve_merge_branch.md" },
    "branch_solve_merge_merge":     { "path": "branch_solve_merge_merge.md" },
    "llm_rubric_generate":          { "path": "llm_rubric_generate.md" },
    "llm_rubric_eval":              { "path": "llm_rubric_eval.md" },
    "structured_rubric_user":       { "path": "structured_rubric_user.md" },
    "atomic_claims_decompose":      { "path": "atomic_claims_decompose.md" },
    "atomic_claims_verify":         { "path": "atomic_claims_verify.md" },
    "constitutional_check":         { "path": "constitutional_check.md" },
    "panel_user":                   { "path": "panel_user.md" },
    "multi_agent_rubric_agent":     { "path": "multi_agent_rubric_agent.md" },
    "multi_agent_rubric_merge":     { "path": "multi_agent_rubric_merge.md" },
    "multi_agent_debate_initial":   { "path": "multi_agent_debate_initial.md" },
    "multi_agent_debate_round":     { "path": "multi_agent_debate_round.md" },
    "meta_judge_user":              { "path": "meta_judge_user.md" },
    "peer_review_user":             { "path": "peer_review_user.md" },
    "mixture_of_prompts_router":    { "path": "mixture_of_prompts_router.md" },
    "self_eval_user":               { "path": "self_eval_user.md" }
  }
}
```

---

### 6.22 Enum Additions

**File:** `vidbyte/lib/enums/prompts.py`  
**Type:** Modified

Add 26 new members under the `# LLM-as-a-Judge strategies` comment block:
```python
LLM_AS_A_JUDGE_CHAIN_OF_THOUGHT_USER = "llm_as_a_judge.chain_of_thought_user"
LLM_AS_A_JUDGE_BINARY_USER = "llm_as_a_judge.binary_user"
LLM_AS_A_JUDGE_FEW_SHOT_USER = "llm_as_a_judge.few_shot_user"
LLM_AS_A_JUDGE_PAIRWISE_USER = "llm_as_a_judge.pairwise_user"
LLM_AS_A_JUDGE_SELF_REFERENCE_GENERATION = "llm_as_a_judge.self_reference_generation"
LLM_AS_A_JUDGE_SELF_REFERENCE_EVAL = "llm_as_a_judge.self_reference_eval"
LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_DECOMPOSE = "llm_as_a_judge.criteria_decomposition_decompose"
LLM_AS_A_JUDGE_CRITERIA_DECOMPOSITION_EVAL = "llm_as_a_judge.criteria_decomposition_eval"
LLM_AS_A_JUDGE_CHAIN_OF_ASPECTS_USER = "llm_as_a_judge.chain_of_aspects_user"
LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_BRANCH = "llm_as_a_judge.branch_solve_merge_branch"
LLM_AS_A_JUDGE_BRANCH_SOLVE_MERGE_MERGE = "llm_as_a_judge.branch_solve_merge_merge"
LLM_AS_A_JUDGE_LLM_RUBRIC_GENERATE = "llm_as_a_judge.llm_rubric_generate"
LLM_AS_A_JUDGE_LLM_RUBRIC_EVAL = "llm_as_a_judge.llm_rubric_eval"
LLM_AS_A_JUDGE_STRUCTURED_RUBRIC_USER = "llm_as_a_judge.structured_rubric_user"
LLM_AS_A_JUDGE_ATOMIC_CLAIMS_DECOMPOSE = "llm_as_a_judge.atomic_claims_decompose"
LLM_AS_A_JUDGE_ATOMIC_CLAIMS_VERIFY = "llm_as_a_judge.atomic_claims_verify"
LLM_AS_A_JUDGE_CONSTITUTIONAL_CHECK = "llm_as_a_judge.constitutional_check"
LLM_AS_A_JUDGE_PANEL_USER = "llm_as_a_judge.panel_user"
LLM_AS_A_JUDGE_MULTI_AGENT_RUBRIC_AGENT = "llm_as_a_judge.multi_agent_rubric_agent"
LLM_AS_A_JUDGE_MULTI_AGENT_RUBRIC_MERGE = "llm_as_a_judge.multi_agent_rubric_merge"
LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_INITIAL = "llm_as_a_judge.multi_agent_debate_initial"
LLM_AS_A_JUDGE_MULTI_AGENT_DEBATE_ROUND = "llm_as_a_judge.multi_agent_debate_round"
LLM_AS_A_JUDGE_META_JUDGE_USER = "llm_as_a_judge.meta_judge_user"
LLM_AS_A_JUDGE_PEER_REVIEW_USER = "llm_as_a_judge.peer_review_user"
LLM_AS_A_JUDGE_MIXTURE_OF_PROMPTS_ROUTER = "llm_as_a_judge.mixture_of_prompts_router"
LLM_AS_A_JUDGE_SELF_EVAL_USER = "llm_as_a_judge.self_eval_user"
```

---

### 6.23 Prompt Bundle Class

**File:** `vidbyte/prompts/strategies/strategy_prompts.py`  
**Type:** Modified

Add:
```python
class LlmAsAJudgePrompts(_PromptBundle):
    key = "llm_as_a_judge"
```

---

### 6.24 Package Exports

**Files:** `vidbyte/evals/llm_as_a_judge/__init__.py`, `vidbyte/evals/__init__.py`, `vidbyte/__init__.py`  
**Type:** New / Modified

All 19 strategy classes must be importable from all three namespaces.

---

## 7. Data Model Changes

N/A — No new database schema changes. `EvalCase.metadata` is already `dict[str, Any]`; `PairwiseJudge` reads `response_b` from there without schema change.

---

## 8. API Changes

N/A — This is a pure library addition. No HTTP endpoints are introduced. The public Python import API is described in Section 6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/evals/llm_as_a_judge/__init__.py` | Package exports for all 19 strategies |
| CREATE | `vidbyte/evals/llm_as_a_judge/_utils.py` | Shared runner invocation and JSON parsing |
| CREATE | `vidbyte/evals/llm_as_a_judge/chain_of_thought.py` | CoT before score strategy |
| CREATE | `vidbyte/evals/llm_as_a_judge/binary.py` | Pass/fail criterion check |
| CREATE | `vidbyte/evals/llm_as_a_judge/few_shot.py` | Calibrated example prompting |
| CREATE | `vidbyte/evals/llm_as_a_judge/pairwise.py` | A vs B comparison with swap debiasing |
| CREATE | `vidbyte/evals/llm_as_a_judge/self_reference.py` | Judge self-generates answer as reference |
| CREATE | `vidbyte/evals/llm_as_a_judge/criteria_decomposition.py` | 2-call: expand criterion → evaluate |
| CREATE | `vidbyte/evals/llm_as_a_judge/chain_of_aspects.py` | Sequential prose evaluation per aspect |
| CREATE | `vidbyte/evals/llm_as_a_judge/branch_solve_merge.py` | Parallel branches → merge |
| CREATE | `vidbyte/evals/llm_as_a_judge/llm_rubric.py` | 2-call: generate rubric → evaluate |
| CREATE | `vidbyte/evals/llm_as_a_judge/structured_rubric.py` | Per-level anchor descriptions per dimension |
| CREATE | `vidbyte/evals/llm_as_a_judge/atomic_claims.py` | Factuality via claim decomposition + verify |
| CREATE | `vidbyte/evals/llm_as_a_judge/constitutional.py` | Principle-by-principle binary checks |
| CREATE | `vidbyte/evals/llm_as_a_judge/panel.py` | Ensemble of same-rubric judges |
| CREATE | `vidbyte/evals/llm_as_a_judge/multi_agent_rubrics.py` | Parallel agents with specialised rubrics |
| CREATE | `vidbyte/evals/llm_as_a_judge/multi_agent_debate.py` | ChatEval-style debate rounds |
| CREATE | `vidbyte/evals/llm_as_a_judge/meta_judge.py` | Judge-of-judges QA layer |
| CREATE | `vidbyte/evals/llm_as_a_judge/peer_review.py` | Confidence-weighted voting |
| CREATE | `vidbyte/evals/llm_as_a_judge/mixture_of_prompts.py` | MoPs: route to specialised prompt templates |
| CREATE | `vidbyte/evals/llm_as_a_judge/self_eval.py` | Same-runner third-person framing |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/llm_as_a_judge.json` | Prompt family manifest |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/chain_of_thought_user.md` | CoT judge prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/binary_user.md` | Binary pass/fail prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/few_shot_user.md` | Few-shot calibration prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/pairwise_user.md` | Pairwise comparison prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/self_reference_generation.md` | Self-answer generation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/self_reference_eval.md` | Self-reference evaluation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/criteria_decomposition_decompose.md` | Criterion expansion prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/criteria_decomposition_eval.md` | Checklist evaluation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/chain_of_aspects_user.md` | Sequential aspect evaluation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/branch_solve_merge_branch.md` | Branch evaluation sub-prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/branch_solve_merge_merge.md` | Merge synthesis prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/llm_rubric_generate.md` | Rubric generation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/llm_rubric_eval.md` | Rubric-guided evaluation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/structured_rubric_user.md` | Anchored multi-dim rubric prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/atomic_claims_decompose.md` | Claim extraction prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/atomic_claims_verify.md` | Single claim verification prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/constitutional_check.md` | Single principle check prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/panel_user.md` | Panel evaluation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_rubric_agent.md` | Agent-specific rubric eval prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_rubric_merge.md` | Multi-agent merge prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_debate_initial.md` | Initial debate verdict prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/multi_agent_debate_round.md` | Debate revision round prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/meta_judge_user.md` | Meta-judge QA evaluation prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/peer_review_user.md` | Confidence-scored review prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/mixture_of_prompts_router.md` | Task-type routing prompt |
| CREATE | `vidbyte/prompts/prompts/llm_as_a_judge/self_eval_user.md` | Third-person self-evaluation prompt |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add 26 new Prompt enum members |
| MODIFY | `vidbyte/prompts/strategies/strategy_prompts.py` | Add `LlmAsAJudgePrompts` bundle |
| MODIFY | `vidbyte/evals/__init__.py` | Re-export all 19 strategy classes |
| MODIFY | `vidbyte/__init__.py` | Re-export all 19 strategy classes |
| CREATE | `tests/test_llm_as_a_judge.py` | Test suite for all 19 strategies |
| CREATE | `scripts/test-llm-as-a-judge.py` | Verification script |

**Total:** 48 files created, 4 files modified = **52 file changes**

---

## 10. Testing Plan

### Unit Tests (`tests/test_llm_as_a_judge.py`)

**MockRunner** returns configurable JSON responses. **MockAgent** supports `arun`. All tests use `unittest.IsolatedAsyncioTestCase`.

**`_utils.py`**
- `test_invoke_runner_arun` — runner with `arun` method is dispatched correctly — [Happy Path]
- `test_invoke_runner_run_sync` — runner with sync `run` is wrapped correctly — [Happy Path]
- `test_invoke_runner_no_method` — runner with no known method raises `TypeError` — [Hidden Assumption]
- `test_parse_json_block_valid` — valid JSON extracted from surrounding text — [Happy Path]
- `test_parse_json_block_no_json` — raises `ValueError` when no JSON found — [Edge Case]
- `test_parse_json_block_nested` — first `{...}` block extracted from nested output — [Hidden Failure]

**`ChainOfThoughtJudge`**
- `test_cot_short_length` — short cot_length injects correct budget instruction — [Silent Failure]
- `test_cot_score_parsed_from_trailing_line` — "Score: 0.8" on last line parsed correctly — [Happy Path]
- `test_cot_falls_back_to_json` — falls back to JSON parse when no Score line — [Hidden Failure]
- `test_cot_prompt_override` — user-provided `prompt_template` replaces SDK default — [Happy Path]

**`BinaryJudge`**
- `test_binary_yes_response` — "yes" → score=1.0, passed=True — [Happy Path]
- `test_binary_no_response` — "no" → score=0.0, passed=False — [Happy Path]
- `test_binary_json_fallback` — `{"passed": true}` parsed when no yes/no keyword — [Hidden Failure]
- `test_binary_empty_criterion` — empty criterion string raises `ValueError` — [Edge Case]

**`FewShotJudge`**
- `test_few_shot_examples_serialised` — examples block present in rendered prompt — [Silent Failure]
- `test_few_shot_empty_examples` — empty list raises `ValueError` — [Edge Case]
- `test_few_shot_missing_keys` — dict missing required key raises `ValueError` — [Hidden Assumption]

**`PairwiseJudge`**
- `test_pairwise_winner_a_both_orderings` — A wins both → score=1.0 — [Happy Path]
- `test_pairwise_disagreement_is_tie` — A wins one, B wins other → score=0.5 — [Silent Failure]
- `test_pairwise_no_response_b` — missing `response_b` in metadata raises `ValueError` — [Hidden Assumption]
- `test_pairwise_swap_check_false` — single call only, no swap — [Happy Path]
- `test_pairwise_tie_explicit` — judge outputs "Tie" → score=0.5 — [Edge Case]

**`SelfReferenceJudge`**
- `test_self_reference_generates_before_eval` — generation call happens before eval call — [Hidden Assumption]
- `test_self_reference_multiple_generations` — `num_self_generations=3` runs 3 concurrent calls — [Edge Case]

**`CriteriaDecompositionJudge`**
- `test_criteria_decomposition_two_calls` — two separate runner invocations — [Hidden Assumption]
- `test_criteria_checklist_injected_in_eval` — decomposition output present in eval prompt — [Silent Failure]

**`ChainOfAspectsJudge`**
- `test_chain_of_aspects_empty_list` — empty aspects raises `ValueError` — [Edge Case]
- `test_chain_of_aspects_mean_fallback` — overall score computed as mean if model omits it — [Hidden Failure]
- `test_chain_of_aspects_words_per_aspect` — word budget instruction in prompt — [Silent Failure]

**`BranchSolveMergeJudge`**
- `test_branch_solve_merge_parallel_calls` — N branches = N concurrent calls — [Hidden Failure]
- `test_branch_solve_merge_weighted_mean` — correct weighted average computed — [Silent Failure]
- `test_branch_solve_merge_llm_merge` — merge runner invoked when strategy is "llm" — [Happy Path]
- `test_branch_solve_merge_equal_weights` — equal weights when branch_weights is None — [Hidden Assumption]

**`LLMRubricJudge`**
- `test_llm_rubric_rubric_cached` — rubric generation called once across multiple cases — [Silent Failure]
- `test_llm_rubric_two_calls` — two runner invocations in single `agrade` — [Hidden Assumption]

**`StructuredRubricJudge`**
- `test_structured_rubric_normalises_scores` — integer score /max_level → float — [Silent Failure]
- `test_structured_rubric_anchor_descriptions_in_prompt` — level descriptions in rendered prompt — [Silent Failure]
- `test_structured_rubric_equal_weights_default` — equal weights when not provided — [Hidden Assumption]

**`AtomicClaimsJudge`**
- `test_atomic_claims_empty_claims` — empty claims list → score=1.0, passed=True — [Edge Case]
- `test_atomic_claims_partial_truth` — 3/5 verified → score=0.6 — [Silent Failure]
- `test_atomic_claims_parallel_verification` — N claims = N concurrent verify calls — [Hidden Failure]
- `test_atomic_claims_threshold` — threshold=0.8, score=0.6 → passed=False — [Edge Case]

**`ConstitutionalJudge`**
- `test_constitutional_all_satisfied` — all pass → score=1.0 — [Happy Path]
- `test_constitutional_one_violation` — 3/4 pass → score=0.75 — [Silent Failure]
- `test_constitutional_empty_principles` — empty list raises `ValueError` — [Edge Case]
- `test_constitutional_parallel_checks` — N principles = N concurrent calls — [Hidden Failure]
- `test_constitutional_threshold_one` — default threshold=1.0 requires all satisfied — [Hidden Assumption]

**`PanelJudge`**
- `test_panel_mean_aggregation` — scores averaged correctly — [Silent Failure]
- `test_panel_majority_vote` — 2/3 passed → overall passed — [Happy Path]
- `test_panel_single_runner` — list of 1 raises `ValueError` — [Edge Case]
- `test_panel_concurrent_calls` — all runners called concurrently — [Hidden Failure]

**`MultiAgentRubricJudge`**
- `test_multi_agent_rubric_weighted_mean` — correct weighted average — [Silent Failure]
- `test_multi_agent_rubric_llm_merge_requires_merge_runner` — merge_strategy="llm" without merge_runner raises `ValueError` — [Hidden Assumption]
- `test_multi_agent_rubric_minimum_agents` — 1 agent raises `ValueError` — [Edge Case]

**`MultiAgentDebateJudge`**
- `test_debate_round_0_independent` — agents produce verdicts without seeing others — [Hidden Assumption]
- `test_debate_all_verdicts_shared` — debate round prompt includes all prior verdicts — [Silent Failure]
- `test_debate_tie_on_even_split` — 1 pass, 1 fail → use mean score ≥ threshold — [Edge Case]
- `test_debate_minimum_runners` — 1 runner raises `ValueError` — [Edge Case]

**`MetaJudge`**
- `test_meta_judge_passes_through_good_verdict` — quality_ok=True → primary_result returned unchanged — [Happy Path]
- `test_meta_judge_filter_on_fail` — quality_ok=False, filter_on_fail=True → score=0.0 — [Happy Path]
- `test_meta_judge_no_filter` — quality_ok=False, filter_on_fail=False → primary score preserved, reason prepended — [Hidden Failure]
- `test_meta_judge_receives_primary_verdict` — meta prompt includes primary score and reason — [Silent Failure]

**`PeerReviewJudge`**
- `test_peer_review_confidence_weighted` — confidence-weighted average correct — [Silent Failure]
- `test_peer_review_filter_low_confidence` — confidence < threshold excluded from vote — [Hidden Failure]
- `test_peer_review_all_filtered_fallback` — falls back to all verdicts when all filtered — [Edge Case]
- `test_peer_review_minimum_runners` — 1 runner raises `ValueError` — [Edge Case]

**`MixtureOfPromptsJudge`**
- `test_mops_router_fn_called` — `router_fn` used when provided — [Happy Path]
- `test_mops_llm_router_called` — `router_runner` invoked when `router_fn` absent — [Happy Path]
- `test_mops_unknown_key_raises` — routed key not in library raises `KeyError` — [Hidden Failure]
- `test_mops_fallback_key` — unknown key falls back to fallback_key — [Edge Case]
- `test_mops_empty_library` — empty `prompt_library` raises `ValueError` — [Edge Case]

**`SelfEvalJudge`**
- `test_self_eval_third_person_framing` — "another assistant" in rendered prompt — [Silent Failure]
- `test_self_eval_anonymous_framing` — "an AI assistant" in rendered prompt — [Silent Failure]

### Integration Tests
- Full `EvalRunner` round-trip with `ChainOfThoughtJudge` as `default_grader` — verifies `GraderResult` flows correctly through `EvalRunner` → `EvalRegistry`.
- `MetaJudge` wrapping `ChainOfThoughtJudge` — verifies two-stage judging pipeline.
- `PanelJudge` with 3 different mock runners — verifies concurrent invocation and aggregation.
- `EvalRunner` with `PairwiseJudge` — verifies `case.metadata["response_b"]` is accessible inside runner flow.

### Manual / QA Test Cases
1. `python scripts/test-llm-as-a-judge.py` exits 0 with all tests passed.
2. `from vidbyte.evals.llm_as_a_judge import ChainOfThoughtJudge` succeeds at the Python REPL.
3. `from vidbyte import ChainOfThoughtJudge` succeeds at the Python REPL.
4. `Prompts().get(Prompt.LLM_AS_A_JUDGE_CHAIN_OF_THOUGHT_USER)` returns a non-empty string.
5. All 26 new Prompt enum members accessible without `AttributeError`.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` | stdlib | Concurrent runner calls | None — already used throughout codebase |
| `re` | stdlib | JSON block extraction, Score line parsing | None |
| `json` | stdlib | Response parsing | None |
| `statistics` | stdlib | Median aggregation in PanelJudge | None |

No new external packages required.

---

## 12. Rollout & Deployment

- Backward-compatible addition. No existing grader or API surface is modified.
- **Base branch:** This PR must be rebased on top of `feat/sdk-evals` (PR #59). Do not merge against `main` until PR #59 lands first.
- No feature flags required.
- Rollback: removing the `vidbyte/evals/llm_as_a_judge/` package and the 26 enum members restores the prior state completely.

---

## 13. Open Questions

- [ ] Should `LLMRubricJudge` generate a fresh rubric per case (ignoring cache) when `task_description` is templated with the case prompt? Current design caches per instance assuming a fixed task type.
- [ ] `MultiAgentDebateJudge` debate rounds are sequential (each round depends on previous). Should the number of rounds be capped (e.g. max 3) to prevent cost blow-up?
- [ ] Should `ConstitutionalJudge` default `threshold=1.0` (all principles must pass) or `threshold=0.8` (allows one failure in 5)? Default of 1.0 is strictest but may be too aggressive.
- [ ] Should `PairwiseJudge` also expose a `score_mode: Literal["binary","continuous"]` where continuous mode returns a weighted preference score from the judge rather than 1.0/0.5/0.0?

---

## 14. Alternatives Considered

### Alternative 1: Add strategies as parameters to `LLMJudgeGrader`
- What: `LLMJudgeGrader(strategy="cot", aggregation="panel", ...)` instead of separate classes.
- Why rejected: Creates a god-class with a combinatorial explosion of parameters. Separate files are independently importable, independently testable, and composable (e.g. wrap any grader in `MetaJudge`).

### Alternative 2: Keep strategies in `vidbyte/evals/graders/` alongside existing graders
- What: Put all 19 files next to `llm_judge.py` and `rubric.py`.
- Why rejected: The existing graders cover deterministic and basic LLM-graded evaluation. The new strategies are a distinct, richer tier. A named sub-package `llm_as_a_judge/` makes the distinction clear and is a natural home for future additions.

### Alternative 3: Inline all prompts into `evals.json`
- What: Store all 26 prompt strings directly in the JSON file.
- Why rejected: Many prompts (chain-of-aspects, debate round, etc.) are multi-paragraph with formatting requirements. Inline JSON strings are unreadable and untestable. Markdown files match the existing `multi_provider_agentic_grader/` pattern.

### Alternative 4: Use a shared base class for multi-runner strategies
- What: `MultiRunnerJudge(BaseGrader)` with abstract `aggregate()` that `PanelJudge`, `PeerReviewJudge`, `MultiAgentDebateJudge` extend.
- Why rejected: The three strategies differ enough in their call pattern (panel is stateless parallel, debate has sequential rounds, peer review adds confidence) that a shared base saves minimal code while adding indirection. `_utils.py` already handles the shared runner invocation logic.
