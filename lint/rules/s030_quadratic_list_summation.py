"""FILE: lint/rules/s030_quadratic_list_summation.py

PURPOSE: Defines S030 for repeated list concatenation during summation.
ROLE IN CODEBASE: Prevents response aggregation from becoming quadratic.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not normalize away a performance failure with a suppression.
KNOWN EDGE CASES: Ruff owns the exact list-sum expression classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S030.
"""

from lint.core.ruff import RuffBackedRule


class QuadraticListSummationRule(RuffBackedRule):
    """Requires list aggregation to avoid repeated quadratic concatenation."""

    id = "S030"
    name = "quadratic-list-summation"
    summary = (
        "List aggregation does not repeatedly copy accumulated lists through sum. "
        "Each concatenation can copy all values collected so far. "
        "That turns a normal batch into quadratic work as the response grows. "
        "Use an extend-based or iterator-based aggregation strategy instead."
    )
    codes = frozenset({"RUF017"})
    impact = (
        "A provider or evaluation batch that grows modestly can consume disproportionate CPU and memory. "
        "The slow path may appear only under production-sized inputs, after retries or fan-out amplify it. "
        "Latency then threatens caller deadlines even though each individual item is simple. "
        "Linear aggregation keeps resource use aligned with the number of values."
    )
    repair = (
        "Use itertools.chain.from_iterable, a comprehension, or a list that is extended once per input according to the surrounding API. "
        "Preserve ordering and the behavior for empty inputs. "
        "Do not replace sum with another repeatedly concatenating helper. "
        "Run the focused rule and a representative large-batch benchmark or test after the edit."
    )


RULE = QuadraticListSummationRule()
