"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/fmea_trace.py
PURPOSE: Defines the fmea-trace model-facing reasoning trace tool and its immutable strategy definition.
ROLE IN CODEBASE: ReasoningTraceCatalog registers this leaf tool; calls record one strategy-owned public checkpoint through ReasoningTraceTool.
ARCHITECTURE NOTE: This module declares strategy metadata and parameter shape only; _base.py owns typed normalization, context writes, and safe errors.
COMMON MODIFICATION PATTERNS: Change this strategy's prose or fields here, then run the reasoning contract checker and both canonical CI stages.
KNOWN EDGE CASES: Inputs are model-authored telemetry; this tool does not execute the strategy, verify truth, or expose private chain-of-thought.
RELATED DOCS: docs/design/reasoning-deep-observability-tools.md and vidbyte/tools/README.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Defines the fmea-trace strategy-specific reasoning trace tool.
Purpose:
    Exposes an explicit public schema for this reasoning strategy and records
    its model-authored checkpoint through the shared context manager boundary.
Architecture:
    - FmeaTraceTool: Strategy-owned description and parameter shape.
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


class FmeaTraceTool(ReasoningTraceTool):
    """Model-facing fmea-trace reasoning trace tool."""

    definition = ReasoningTraceDefinition(
        skill_name='fmea-trace',
        purpose='Identify component failure modes and assess effects.',
        description='Use the fmea reasoning trace when the current task benefits from identify component failure modes and assess effects. Its central move gives the public checkpoint a strategy-specific structure for examining the question. The parameters separate the observations, judgments, uncertainties, and actions that make the strategy inspectable. The tool writes one bounded context primitive so later iterations can recover the declared reasoning state. Use it at a meaningful checkpoint after the relevant inputs are available and before the next action is chosen. The record does not execute the strategy, verify model-authored claims, or replace authoritative task instructions. Treat the result as auditable telemetry that supports comparison across iterations without exposing private chain-of-thought.',
        parameters=(
        parameter(name='question', type='string', description="Question captures the focused question or decision target for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='process_step', type='string', description="Process step captures the process step dimension of the strategy for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='failure_modes', type='array', description="Failure modes captures the ways the system or process can fail for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='effects', type='array', description="Effects captures the consequences produced by each relevant failure mode for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='causes', type='array', description="Causes captures the contributing conditions that explain the observed outcome for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='severity', type='number', description="Severity captures the consequence magnitude assigned to a failure or risk for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='likelihood', type='number', description="Likelihood captures the estimated chance that a failure or event will occur for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='detectability', type='number', description="Detectability captures the likelihood that a failure will be found before causing harm for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='actions', type='string', description="Actions captures the actions dimension of the strategy for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='confidence', type='number', description="Confidence captures the calibrated confidence in the current working direction for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        parameter(name='next_action', type='string', description="Next action captures the next observable action that will advance or test the work for the fmea trace. It keeps the record anchored to the strategy's central move rather than a generic account of reasoning. It separates this dimension from the other observations and judgments needed for identify component failure modes and assess effects. Record the material content that would change how a careful reviewer interprets the current state. Keep the value explicit enough that a later iteration can compare it with new evidence and revise it. Treat this field as model-authored telemetry whose usefulness depends on honest, bounded reporting."),
        ),
    )


__all__ = ['FmeaTraceTool']
