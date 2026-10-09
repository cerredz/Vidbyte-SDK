# Judge Verdict Parsing

## Summary

`LLMJudgeGrader` and `RubricGrader` turn a judge model's reply into a `GraderResult`. Two parsing bugs make that result wrong:

1. **Fail-open verdict.** `LLMJudgeGrader` computed `passed = bool(parsed.get("passed", False))`. Judges sometimes return the verdict as a string, and `bool("false")` is `True`, so `{"score": 0.1, "passed": "false"}` was recorded as a pass.
2. **Greedy extraction.** Both graders located the JSON with `re.search(r"\{.*\}", text, re.DOTALL)`, which spans from the first `{` to the last `}` in the whole reply. A valid verdict followed by prose that contains braces failed `json.loads` ("Extra data") and a correct verdict became a fail with score 0.

The fix decodes only the first JSON object in the reply and accepts only a real `true` (or the string `"true"`) as a pass. Public APIs do not change.

## Flow chart

```mermaid
flowchart TD
    A[Judge reply text] --> B{Contains a '{'?}
    B -- no --> F1[GraderResult: Failed to find JSON block]
    B -- yes --> C[raw_decode the object starting at the first '{']
    C -- decode error --> F2[GraderResult: Failed to parse ...]
    C -- ok, trailing text ignored --> D{Which grader?}
    D -- LLMJudgeGrader --> E{passed is JSON true or string 'true'?}
    E -- yes --> P[passed=True]
    E -- no: false, 'false', missing, number, other --> N[passed=False]
    D -- RubricGrader --> R[weighted score >= threshold]
```

## Usage example

```python
from vidbyte.evals import EvalCase, LLMJudgeGrader

class StubJudge:
    def run(self, prompt: str, **kwargs: object) -> str:
        return '{"score": 0.1, "passed": "false", "reason": "wrong"}\nNote: format {ok}.'

result = await LLMJudgeGrader(judge_runner=StubJudge()).agrade(EvalCase(prompt="2+2?", expected="4"), "5")
assert result.passed is False   # was True before the fix
assert result.score == 0.1      # the verdict is still read despite the trailing braces
```

## How it works

- **Extraction (both graders).** `_parse_response` finds the first `{` and calls `json.JSONDecoder().raw_decode(text, start)`, which decodes exactly one JSON value and ignores whatever follows. Fenced `json` blocks keep working because the object still starts at the first `{`. No `{` keeps the existing "Failed to find JSON block" result; an undecodable object keeps the existing "Failed to parse" result.
- **Verdict (LLM judge).** A small private helper `_coerce_passed` returns the value itself for a JSON boolean, `value.strip().lower() == "true"` for a string, and `False` for anything else. A missing field still defaults to `False`.

## Files changed

- `vidbyte/evals/graders/llm_judge.py` — first-object extraction and strict verdict coercion.
- `vidbyte/evals/graders/rubric.py` — first-object extraction.
- `tests/test_evals.py` — regression tests.

## Risks and open questions

- A reply whose prose *before* the verdict contains a `{` still fails to parse, as it did before. This fails closed (not passed) and is left out of scope to keep the change minimal.
- Judges that returned the string `"true"` keep passing; judges returning `"yes"`, `1`, or similar now count as not passed, which is the intended fail-closed behavior.

## Verification

- New tests in `tests/test_evals.py`: string `"false"` is not passed, string `"true"` is passed, a verdict followed by brace-containing prose parses correctly for both graders, and fenced `json` replies still parse.
- `python lint/run.py` and `python scripts/run_ci.py` pass locally; required GitHub checks pass on the PR.
