"""Prebuilt eval templates and registry helpers."""

from __future__ import annotations

from vidbyte.evals.templates.base import EvalTemplate
from vidbyte.evals.templates.builtins import (
    ClassificationTemplate,
    ConciseGroundedAnswerTemplate,
    MultipleChoiceTemplate,
    NumericAnswerTemplate,
    SafeCustomerSupportTemplate,
    ShortAnswerFactTemplate,
    StructuredJsonTemplate,
    classification,
    concise_grounded_answer,
    multiple_choice,
    numeric_answer,
    register_builtin_templates,
    safe_customer_support,
    short_answer_fact,
    structured_json,
)
from vidbyte.evals.templates.registry import EvalTemplateRegistry

default_template_registry = EvalTemplateRegistry()
register_builtin_templates(default_template_registry)

__all__ = [
    "ClassificationTemplate",
    "ConciseGroundedAnswerTemplate",
    "EvalTemplate",
    "EvalTemplateRegistry",
    "MultipleChoiceTemplate",
    "NumericAnswerTemplate",
    "SafeCustomerSupportTemplate",
    "ShortAnswerFactTemplate",
    "StructuredJsonTemplate",
    "classification",
    "concise_grounded_answer",
    "default_template_registry",
    "multiple_choice",
    "numeric_answer",
    "safe_customer_support",
    "short_answer_fact",
    "structured_json",
]

