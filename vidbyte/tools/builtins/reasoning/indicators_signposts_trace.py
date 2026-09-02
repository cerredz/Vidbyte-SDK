"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/indicators_signposts_trace.py
PURPOSE: Defines the indicators-signposts-trace model-facing reasoning trace tool and its immutable strategy definition.
ROLE IN CODEBASE: ReasoningTraceCatalog registers this leaf tool; calls record one strategy-owned public checkpoint through ReasoningTraceTool.
ARCHITECTURE NOTE: This module declares strategy metadata and parameter shape only; _base.py owns typed normalization, context writes, and safe errors.
COMMON MODIFICATION PATTERNS: Change this strategy's prose or fields here, then run the reasoning contract checker and both canonical CI stages.
KNOWN EDGE CASES: Inputs are model-authored telemetry; this tool does not execute the strategy, verify truth, or expose private chain-of-thought.
RELATED DOCS: docs/design/reasoning-deep-observability-tools.md and vidbyte/tools/README.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Defines the indicators-signposts-trace strategy-specific reasoning trace tool.
Purpose:
    Exposes an explicit public schema for this reasoning strategy and records
    its model-authored checkpoint through the shared context manager boundary.
Architecture:
    - IndicatorsSignpostsTraceTool: Strategy-owned description and parameter shape.
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


class IndicatorsSignpostsTraceTool(ReasoningTraceTool):
    """Model-facing indicators-signposts-trace reasoning trace tool."""

    definition = ReasoningTraceDefinition(
        skill_name='indicators-signposts-trace',
        purpose='Define signals that confirm, weaken, or redirect an assessment.',
        description='Use the indicators signposts reasoning trace when the current task benefits from define signals that confirm, weaken, or redirect an assessment. Its central move gives the public checkpoint a strategy-specific structure for examining the question. The parameters separate the observations, judgments, uncertainties, and actions that make the strategy inspectable. The tool writes one bounded context primitive so later iterations can recover the declared reasoning state. Use it at a meaningful checkpoint after the relevant inputs are available and before the next action is chosen. The record does not execute the strategy, verify model-authored claims, or replace authoritative task instructions. Treat the result as auditable telemetry that supports comparison across iterations without exposing private chain-of-thought.',
        parameters=(
        parameter(name='question', type='string', description="Question captures the focused question or decision target for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='drivers', type='array', description="Drivers captures the forces that can move the situation toward different futures for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='assumptions', type='array', description="Assumptions captures the premises currently accepted without complete verification for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='evidence', type='string', description="Evidence captures the observations, sources, calculations, or results supporting the trace for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='scenarios', type='array', description="Scenarios captures the coherent future states used to test strategic resilience for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='indicators', type='array', description="Indicators captures the observable signals that distinguish developing conditions for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='implications', type='array', description="Implications captures the consequences that follow if the assessed condition holds for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='confidence', type='number', description="Confidence captures the calibrated confidence in the current working direction for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='next_action', type='string', description="Next action captures the next observable action that will advance or test the work for the indicators signposts trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for define signals that confirm, weaken, or redirect an assessment. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        ),
    )


__all__ = ['IndicatorsSignpostsTraceTool']
