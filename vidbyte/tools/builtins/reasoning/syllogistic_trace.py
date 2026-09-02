"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/syllogistic_trace.py
PURPOSE: Defines the syllogistic-trace model-facing reasoning trace tool and its immutable strategy definition.
ROLE IN CODEBASE: ReasoningTraceCatalog registers this leaf tool; calls record one strategy-owned public checkpoint through ReasoningTraceTool.
ARCHITECTURE NOTE: This module declares strategy metadata and parameter shape only; _base.py owns typed normalization, context writes, and safe errors.
COMMON MODIFICATION PATTERNS: Change this strategy's prose or fields here, then run the reasoning contract checker and both canonical CI stages.
KNOWN EDGE CASES: Inputs are model-authored telemetry; this tool does not execute the strategy, verify truth, or expose private chain-of-thought.
RELATED DOCS: docs/design/reasoning-deep-observability-tools.md and vidbyte/tools/README.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Defines the syllogistic-trace strategy-specific reasoning trace tool.
Purpose:
    Exposes an explicit public schema for this reasoning strategy and records
    its model-authored checkpoint through the shared context manager boundary.
Architecture:
    - SyllogisticTraceTool: Strategy-owned description and parameter shape.
    - ReasoningTraceTool: Shared validation, rendering, and upsert behavior.
Relations:
    Re-exported by vidbyte.tools.builtins.reasoning and discovered by the
    fixed SDK ComponentRegistry through vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.reasoning._base import (
    ReasoningTraceDefinition,
    ReasoningTraceTool,
    parameter,
)


class SyllogisticTraceTool(ReasoningTraceTool):
    """Model-facing syllogistic-trace reasoning trace tool."""

    definition = ReasoningTraceDefinition(
        skill_name='syllogistic-trace',
        purpose='Test categorical syllogisms and their validity.',
        description='Use the syllogistic reasoning trace when the current task benefits from test categorical syllogisms and their validity. Its central move gives the public checkpoint a strategy-specific structure for examining the question. The parameters separate the observations, judgments, uncertainties, and actions that make the strategy inspectable. The tool writes one bounded context primitive so later iterations can recover the declared reasoning state. Use it at a meaningful checkpoint after the relevant inputs are available and before the next action is chosen. The record does not execute the strategy, verify model-authored claims, or replace authoritative task instructions. Treat the result as auditable telemetry that supports comparison across iterations without exposing private chain-of-thought.',
        parameters=(
        parameter(name='question', type='string', description="Question captures the focused question or decision target for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='claim', type='string', description="Claim captures the proposition whose support and limits are being examined for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='premises', type='array', description="Premises captures the stated reasons on which the conclusion depends for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='inference', type='string', description="Inference captures the step that connects the premises to the working conclusion for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='evidence', type='string', description="Evidence captures the observations, sources, calculations, or results supporting the trace for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='counterexample', type='string', description="Counterexample captures the case or condition that would challenge the proposed conclusion for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='conclusion', type='string', description="Conclusion captures the position that follows from the recorded reasoning for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='confidence', type='number', description="Confidence captures the calibrated confidence in the current working direction for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='next_action', type='string', description="Next action captures the next observable action that will advance or test the work for the syllogistic trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for test categorical syllogisms and their validity. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        ),
    )


__all__ = ['SyllogisticTraceTool']
