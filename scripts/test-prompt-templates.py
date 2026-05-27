# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Verification script for prompt templates implementation.
# Purpose: Validates that all prompt templates are successfully registered, loaded, formatted, and exposed by the SDK.
# Architecture & Functions:
#   - test_templates_registered_in_enum(): Validates enum keys exist in the Prompt enum.
#   - test_templates_load_without_configuration_errors(): Asserts the catalog loads without JSON or parsing issues.
#   - test_no_duplicate_template_ids(): Confirms there are no duplicate prompt IDs in the registry.
#   - test_prompt_templates_bundle_export(): Confirms that PromptTemplatesPrompts works correctly.
#   - test_templates_formatted_output_structure(): Validates format placeholder strings in templates.
#   - test_template_direct_imports(): Confirms templates are directly importable from the top-level package.
# Codebase Relation:
#   - Serves as the final validation boundary (Phase 5) before opening a pull request.
# Similar Files:
#   - tests/test_prompt_registry.py (associated unit tests)
# ==============================================================================

from __future__ import annotations

import sys
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import (
    Prompts,
    PromptTemplatesPrompts,
    templates_intent_based,
    templates_persona,
    templates_specification,
)


def test_templates_registered_in_enum() -> bool:
    # [Edge Case] Verifies that the new prompt family keys are in the Prompt enum.
    try:
        assert hasattr(Prompt, "TEMPLATES_INTENT_BASED")
        assert hasattr(Prompt, "TEMPLATES_PERSONA")
        assert hasattr(Prompt, "TEMPLATES_SPECIFICATION")
        assert Prompt.TEMPLATES_INTENT_BASED.value == "templates.intent_based"
        assert Prompt.TEMPLATES_PERSONA.value == "templates.persona"
        assert Prompt.TEMPLATES_SPECIFICATION.value == "templates.specification"
        return True
    except AssertionError:
        return False


def test_templates_load_without_configuration_errors() -> bool:
    # [Hidden Failure] Asserts that Prompts resolves the sub-directory templates successfully.
    try:
        prompts = Prompts()
        assert Prompt.TEMPLATES_INTENT_BASED in prompts.keys()
        assert Prompt.TEMPLATES_PERSONA in prompts.keys()
        assert Prompt.TEMPLATES_SPECIFICATION in prompts.keys()
        return True
    except Exception:
        return False


def test_no_duplicate_template_ids() -> bool:
    # [Silent Failure] Validates that the keys mapped in templates.json do not duplicate.
    try:
        prompts = Prompts()
        all_keys = list(prompts.keys())
        assert len(all_keys) == len(set(all_keys))
        return True
    except AssertionError:
        return False


def test_prompt_templates_bundle_export() -> bool:
    # [Edge Case] Verifies that calling PromptTemplatesPrompts().export() returns correct keys.
    try:
        bundle = PromptTemplatesPrompts()
        exported = bundle.export()
        assert "intent_based" in exported
        assert "persona" in exported
        assert "specification" in exported
        assert isinstance(exported["intent_based"], str)
        return True
    except AssertionError:
        return False


def test_templates_formatted_output_structure() -> bool:
    # [Hidden Assumption] Verifies that the loaded templates contain expected placeholders.
    try:
        prompts = Prompts()
        intent = prompts.get(Prompt.TEMPLATES_INTENT_BASED)
        persona = prompts.get(Prompt.TEMPLATES_PERSONA)
        specification = prompts.get(Prompt.TEMPLATES_SPECIFICATION)

        assert "{task}" in intent
        assert "{role}" in persona
        assert "{task}" in specification
        return True
    except AssertionError:
        return False


def test_template_direct_imports() -> bool:
    # [Silent Failure] Asserts that variables are available as direct imports.
    try:
        assert isinstance(templates_intent_based, str)
        assert isinstance(templates_persona, str)
        assert isinstance(templates_specification, str)
        assert "specializing in **Intent-Based Prompting**" in templates_intent_based
        return True
    except AssertionError:
        return False


def main() -> None:
    # Runs the testing suite, prints PASS/FAIL labels, and exits 0 on success.
    tests = {
        "[Edge Case] test_templates_registered_in_enum": test_templates_registered_in_enum,
        "[Hidden Failure] test_templates_load_without_configuration_errors": test_templates_load_without_configuration_errors,
        "[Silent Failure] test_no_duplicate_template_ids": test_no_duplicate_template_ids,
        "[Edge Case] test_prompt_templates_bundle_export": test_prompt_templates_bundle_export,
        "[Hidden Assumption] test_templates_formatted_output_structure": test_templates_formatted_output_structure,
        "[Silent Failure] test_template_direct_imports": test_template_direct_imports,
    }

    failed = 0
    passed = 0

    print("=================== Running Prompt Templates Verification Script ===================")
    for name, test_fn in tests.items():
        if test_fn():
            print(f"PASS: {name}")
            passed += 1
        else:
            print(f"FAIL: {name}")
            failed += 1

    print("--------------------------------------------------------------------------------")
    print(f"Summary: {passed}/{len(tests)} tests passed.")

    if failed > 0:
        print("Verification FAILED.")
        sys.exit(1)
    else:
        print("Verification PASSED successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
