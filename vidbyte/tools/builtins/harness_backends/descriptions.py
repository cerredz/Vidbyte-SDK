"""FILE: vidbyte/tools/builtins/harness_backends/descriptions.py

PURPOSE: Holds the model-facing description text of the three backend tools (list_harness_backends, check_backend_ready, get_deepseek_balance) and of their one parameter, backend.
ROLE IN CODEBASE: Read by the tool classes in vidbyte/tools/builtins/harness_backends/tools.py when they declare their ToolSpec and ToolParameter values.
ARCHITECTURE NOTE: Plain string constants, each at least four general sentences with no concrete example values, so lint rule S025 can resolve and count them statically.
FUNCTION INVENTORY: No functions. One description per tool and one for the backend parameter.
COMMON MODIFICATION PATTERNS: When a tool's behaviour changes, update its description here in the same change, keeping at least four sentences.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a key value, a URL with credentials or a concrete example in a description. 2. Do not join adjacent string literals implicitly (S062); write each constant as one parenthesised expression with explicit spaces.
KNOWN EDGE CASES: The descriptions name environment variables, never their values.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.2 (Tools, rows 41-43); field guide model-facing-tool-contracts.md
TESTS: tests/features/native_backends/test_native_backends_tools.py
"""

from __future__ import annotations

LIST_HARNESS_BACKENDS_DESCRIPTION = (
    "Lists the Anthropic-compatible backend profiles this SDK can point a coding agent at, in a fixed order. "
    + "Each profile names its endpoint, the environment variable that must hold its key, the models it serves, the request features it ignores and the harnesses its terms allow. "
    + "The call reads no key and makes no network request, so it is safe to run at any time. "
    + "Use it to choose a backend and a model before checking readiness or starting a coding agent on that backend."
)
CHECK_BACKEND_READY_DESCRIPTION = (
    "Checks whether one backend profile can be used right now. "
    + "It always confirms that the backend's key variable is set, and for a backend with a free balance endpoint it also reads the account balance, which verifies the key without spending anything. "
    + "A backend without such an endpoint is reported as not remotely verified, which is not an error. "
    + "When the check fails, the result names the missing variable, the rejected key or the account problem, together with the next step to take."
)
GET_DEEPSEEK_BALANCE_DESCRIPTION = (
    "Reads the DeepSeek account balance with the key from the DeepSeek key variable. "
    + "The answer says whether the account can serve calls and lists the balance per currency, with amounts written as exact decimal text. "
    + "The call is a read-only request that spends nothing, and it gives up after a short fixed deadline. "
    + "Use it to confirm funds before starting long work on the DeepSeek backend, or to explain a billing failure."
)
BACKEND_PARAMETER_DESCRIPTION = (
    "The backend profile to check, written exactly as the profile name that list_harness_backends returns. "
    + "Only the lower-case names of the declared profiles are accepted, and any other text is refused before any network request. "
    + "The backend's key is read from its own environment variable, never from this argument. "
    + "Pass the name alone, without a model or endpoint."
)

__all__ = [
    "BACKEND_PARAMETER_DESCRIPTION",
    "CHECK_BACKEND_READY_DESCRIPTION",
    "GET_DEEPSEEK_BALANCE_DESCRIPTION",
    "LIST_HARNESS_BACKENDS_DESCRIPTION",
]
