# Adding a New LLM-as-a-Judge Strategy

Follow these steps in order when adding a new judge strategy to the Vidbyte SDK.

## 1. Define the Config Dataclass

Add a new `@dataclass(frozen=True, slots=True)` to `vidbyte/lib/dataclasses/llm_judge.py`:

```python
@dataclass(frozen=True, slots=True)
class MyNewJudgeConfig:
    judge_runner: object
    # ... other fields with defaults last
    threshold: float = 0.7
    system_prompt: str | None = None
    prompt_template: str | None = None

    def __post_init__(self) -> None:
        _validate_runner(self.judge_runner, "judge_runner")
        _validate_threshold(self.threshold, "threshold")
        # add any other field validation here
```

Validation helpers already available in `llm_judge.py`:
- `_validate_runner(runner, field)` — checks for `arun`, `generate_reply`, or `run`
- `_validate_non_empty_str(value, field)` — checks non-empty string
- `_validate_threshold(value, field)` — checks float in (0, 1]

Export the new class in `__all__` at the bottom of `llm_judge.py`.

## 2. Add Default Template(s) to JUDGE_TEMPLATES

Add entries to `vidbyte/lib/config/templates.py` using the key format `"<judge_name>.<slot>"`:

```python
"my_new_judge.user": (
    "You are an objective judge...\n\n"
    "...\n\n"
    "Task Prompt:\n{prompt}\n\n"
    "Model Response:\n{actual}\n\n"
    "Expected Output:\n{expected}"
),
```

Keys must match the slot strings used in `_resolve_template()` calls in the judge class.

## 3. Add Prompt Enum Members

Add corresponding entries to `vidbyte/lib/enums/prompts.py`:

```python
LLM_AS_A_JUDGE_MY_NEW_JUDGE_USER = "llm_as_a_judge.my_new_judge_user"
```

## 4. Add Prompt `.md` Files

Create `vidbyte/prompts/prompts/llm_as_a_judge/my_new_judge_user.md` with:
- A 6–7 sentence introduction explaining what this prompt does, when to use it, and how to interpret the output.
- The full template body matching `JUDGE_TEMPLATES` exactly.

Update the prompt manifest JSON in `vidbyte/prompts/` to register the new prompt.

## 5. Implement the Judge Class

Create `vidbyte/evals/llm_as_a_judge/my_new_judge.py`:

```python
from vidbyte.lib.dataclasses.llm_judge import MyNewJudgeConfig
from vidbyte.lib.eval.template_registry import TemplatesRegistry
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_registry = TemplatesRegistry()

class MyNewJudge(BaseGrader):
    name: ClassVar[str] = "my_new_judge"

    def __init__(self, config: MyNewJudgeConfig) -> None:
        # Unpacks config fields into instance attributes.
        self.judge_runner = config.judge_runner
        self.threshold = config.threshold
        self.system_prompt = config.system_prompt
        self.prompt_template = config.prompt_template

    def _resolve_template(self, slot: str, override: str | None, prompt_key: Prompt) -> str:
        # Returns override, SDK catalog prompt, or registry default in priority order.
        if override:
            return override
        try:
            return Prompts().get(prompt_key)
        except Exception:
            return _registry.get(slot)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Implementation here.
        ...
```

## 6. Export from Package `__init__`

Add the new class to `vidbyte/evals/llm_as_a_judge/__init__.py`.

## 7. Write Tests

Add test cases to `tests/test_llm_as_a_judge.py` covering:
- Happy path grading
- Template override works
- Config validation raises `ValueError` on bad inputs
- Edge cases specific to the strategy

## 8. Update Verification Script

The `scripts/test-llm-as-a-judge.py` script auto-loads from `test_llm_as_a_judge.py` — no changes needed unless the script has separate test counts.
