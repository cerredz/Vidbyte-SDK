"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/after_action_review_trace.py
PURPOSE: Defines the after-action-review-trace model-facing reasoning trace tool and its immutable strategy definition.
ROLE IN CODEBASE: ReasoningTraceCatalog registers this leaf tool; calls record one strategy-owned public checkpoint through ReasoningTraceTool.
ARCHITECTURE NOTE: This module declares strategy metadata and parameter shape only; _base.py owns typed normalization, context writes, and safe errors.
COMMON MODIFICATION PATTERNS: Change this strategy's prose or fields here, then run the reasoning contract checker and both canonical CI stages.
KNOWN EDGE CASES: Inputs are model-authored telemetry; this tool does not execute the strategy, verify truth, or expose private chain-of-thought.
RELATED DOCS: docs/design/reasoning-deep-observability-tools.md and vidbyte/tools/README.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Defines the after-action-review-trace strategy-specific reasoning trace tool.
Purpose:
    Exposes an explicit public schema for this reasoning strategy and records
    its model-authored checkpoint through the shared context manager boundary.
Architecture:
    - AfterActionReviewTraceTool: Strategy-owned description and parameter shape.
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


class AfterActionReviewTraceTool(ReasoningTraceTool):
    """Model-facing after-action-review-trace reasoning trace tool."""

    definition = ReasoningTraceDefinition(
        skill_name='after-action-review-trace',
        purpose='Compare expectations with outcomes and derive improvements.',
        description='Use the after action review reasoning trace when the current task benefits from compare expectations with outcomes and derive improvements. Its central move gives the public checkpoint a strategy-specific structure for examining the question. The parameters separate the observations, judgments, uncertainties, and actions that make the strategy inspectable. The tool writes one bounded context primitive so later iterations can recover the declared reasoning state. Use it at a meaningful checkpoint after the relevant inputs are available and before the next action is chosen. The record does not execute the strategy, verify model-authored claims, or replace authoritative task instructions. Treat the result as auditable telemetry that supports comparison across iterations without exposing private chain-of-thought.',
        parameters=(
        parameter(name='question', type='string', description="Question captures the focused question or decision target for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='expected_outcome', type='string', description="Expected outcome captures the expected outcome dimension of the strategy for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='actual_outcome', type='string', description="Actual outcome captures the actual outcome dimension of the strategy for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='deviations', type='string', description="Deviations captures the deviations dimension of the strategy for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='causes', type='array', description="Causes captures the contributing conditions that explain the observed outcome for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='lessons', type='string', description="Lessons captures the lessons dimension of the strategy for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='changes', type='string', description="Changes captures the changes dimension of the strategy for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='confidence', type='number', description="Confidence captures the calibrated confidence in the current working direction for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='next_action', type='string', description="Next action captures the next observable action that will advance or test the work for the after action review trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for compare expectations with outcomes and derive improvements. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        ),
    )


__all__ = ['AfterActionReviewTraceTool']
