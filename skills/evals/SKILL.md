# Vidbyte Evals Subsystem

Use this reference when working with the evaluation subsystem in the Vidbyte SDK.

## Current Layout

```text
vidbyte/
|-- evals/
|   |-- base.py                     # BaseGrader abstract class
|   |-- types.py                    # EvalCase, GraderResult
|   |-- llm_as_a_judge/
|   |   |-- __init__.py             # Re-exports all 19 judge classes
|   |   |-- _utils.py               # invoke_runner, extract_text, parse_json_block
|   |   |-- atomic_claims.py
|   |   |-- binary.py
|   |   |-- branch_solve_merge.py
|   |   |-- chain_of_aspects.py
|   |   |-- chain_of_thought.py
|   |   |-- constitutional.py
|   |   |-- criteria_decomposition.py
|   |   |-- few_shot.py
|   |   |-- llm_rubric.py
|   |   |-- meta_judge.py
|   |   |-- mixture_of_prompts.py
|   |   |-- multi_agent_debate.py
|   |   |-- multi_agent_rubrics.py
|   |   |-- pairwise.py
|   |   |-- panel.py
|   |   |-- peer_review.py
|   |   |-- self_eval.py
|   |   |-- self_reference.py
|   |   `-- structured_rubric.py
|-- lib/
|   |-- dataclasses/
|   |   `-- llm_judge.py            # 19 frozen config dataclasses
|   |-- eval/
|   |   |-- __init__.py
|   |   `-- template_registry.py   # TemplatesRegistry
|   `-- config/
|       `-- templates.py            # JUDGE_TEMPLATES dict (SDK defaults)
vidbyte/prompts/prompts/llm_as_a_judge/
|   |-- *.md                        # 26 prompt template files
tests/
|   `-- test_llm_as_a_judge.py
scripts/
|   `-- test-llm-as-a-judge.py
```

## Rules

- All 19 judge classes live under `vidbyte/evals/llm_as_a_judge/` and inherit from `vidbyte.evals.base.BaseGrader`.
- Every judge accepts a single typed config dataclass as its constructor argument. Config dataclasses are defined in `vidbyte/lib/dataclasses/llm_judge.py` and use `@dataclass(frozen=True, slots=True)`.
- All validation (runner duck-typing, non-empty strings, threshold ranges, cross-field constraints) belongs in the config dataclass `__post_init__`, not in the judge class.
- Template resolution priority in every judge: user-supplied override → `Prompts().get(Prompt.XXX)` → `TemplatesRegistry.get(slot)`.
- Default templates are centrally stored in `vidbyte/lib/config/templates.py` as `JUDGE_TEMPLATES`, keyed as `"<judge_name>.<slot>"`.
- `TemplatesRegistry` is instance-isolated: each judge creates its own `_registry = TemplatesRegistry()` at module level; mutations to one instance do not affect others.
- Prompt `.md` files in `vidbyte/prompts/prompts/llm_as_a_judge/` must have 6–7 sentence introductory sections before the template body.
- The `LLMRubricJudge` holds `_cached_rubric: str | None = None` as mutable instance state in `__init__`, not in the frozen config dataclass.
- Follow `skills/evals/adding-llm-judge.md` when adding a new judge strategy.
- Follow `skills/evals/using-llm-judge.md` when writing user-facing examples.
- Follow `skills/evals/eval-pipeline.md` when setting up an evaluation pipeline with multiple graders.
