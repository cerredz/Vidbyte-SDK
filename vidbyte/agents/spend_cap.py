"""FILE: vidbyte/agents/spend_cap.py

PURPOSE: Defines AgentSpendCap, the policy behind AgentLoopSettings.max_spend_usd: whether a run must stop because its measured spend reached the cap or can no longer be measured, and whether an agent must be refused at construction because the cap could not be enforced or measured on its configured models.
ROLE IN CODEBASE: Called by AgentRuntime._spend_cap_stop (vidbyte/agents/runtime.py) at the four loop check points, and by BaseAgent.__init__ (vidbyte/agents/base.py) for the construction refusal. It reads the agent-owned UsageRollup and the default pricebook; it never records usage.
ARCHITECTURE NOTE: Measured spend is the SDK-rated USD cost in the agent's own usage tracker: main model calls, billed failed attempts, context-window side calls, priced operations, Jev decision calls, algorithm side calls, and each child agent's rollup once that child's reply finishes. The runtime checks the cap at the top of every iteration, on the plain-text finish branch, before every tool call (internal tools included), and before the compute checkpoint of a continuing tool iteration. stop_output reports a reached cap before a blind meter, because the measured spend alone proves the cap was reached. The construction refusals stop an agent before any spend; a model that only appears at run time falls to the blind stop instead.
FUNCTION INVENTORY: AgentSpendCap.stop_output (the reached or unmeasured stop text, or None); AgentSpendCap.model_refusal (why a capped agent's runner type or configured models cannot be enforced or measured, or None); _blind_causes words what left spend unmeasured; _chain_runners builds one Runner per configured model, primary first; _unpriced_pairs lists the configured models the pricebook cannot price.
COMMON MODIFICATION PATTERNS: A new loop check point calls AgentRuntime._spend_cap_stop, never this class directly, so every stop carries the same stop reason and metadata. A new blind cause is one more entry in _blind_causes, after the existing ones, so the stop text keeps its order.
WHAT NOT TO DO IN THIS FILE: 1. Do not write to a UsageTracker or change a rollup; the cap only reads the ledger. 2. Do not treat cost_usd is None as unmeasured by itself; an empty ledger has no cost and is measured. 3. Do not describe the cap as a maximum bill; it is a threshold checked between steps. 4. Do not quote prompts, keys, or amounts in a stop text; it names models, operations, and counts only.
KNOWN EDGE CASES: An empty ledger is measured, so a capped run that has spent nothing never stops. When cost_measured is False, cost_usd is a lower bound, not the spend. A child agent's spend counts only after the child's reply finishes and merges. OpenRouter models need no pricebook entry, because OpenRouter reports each call's cost. An agent with neither a provider nor a model is not refused here, because it cannot run at all.
RELATED DOCS: vidbyte/agents/README.md (section Spend Cap); docs/spec/loop-spend-cap/spec.md
TESTS: tests/features/loop_spend_cap
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.agents.pricing.records import UsageRecordingIntegrity, UsageRollup
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.runners import Runner

if TYPE_CHECKING:
    from vidbyte.agents.fallback import AgentFallback
    from vidbyte.lib.dataclasses.agents import AgentRunnerConfig


class AgentSpendCap:
    """Stop and refusal decisions for AgentLoopSettings.max_spend_usd, read from the usage ledger and the pricebook."""

    @staticmethod
    def stop_output(max_spend_usd: float, rollup: UsageRollup) -> str | None:
        """Return the stop text when a run capped at max_spend_usd must stop on this rollup, else None."""
        # @intent spend-cap-fails-closed-on-a-blind-meter
        # A run whose spend cannot be fully measured could pass its cap
        # unseen, so it stops as if the cap were reached, and the text
        # names the cause. A reached cap is reported first, because the
        # measured spend alone proves it, whatever the meter missed.
        if rollup.cost_usd is not None and rollup.cost_usd >= max_spend_usd:
            return "Agent runtime stopped after reaching max_spend_usd."
        if rollup.cost_measured:
            return None
        causes = "; ".join(AgentSpendCap._blind_causes(rollup))
        return f"Agent runtime stopped because max_spend_usd is set and this run's spend could not be fully measured: {causes}."

    @staticmethod
    def model_refusal(
        max_spend_usd: float | None,
        runner_config: AgentRunnerConfig,
        fallback: AgentFallback | None,
    ) -> str | None:
        """Return why an agent capped at max_spend_usd cannot enforce or measure the cap on its configured models, else None."""
        # @intent spend-cap-is-refused-where-it-cannot-be-measured
        # A non-text runner runs outside the loop and records no usage,
        # and an unpriced model is found only after a paid call, so
        # either would leave the cap unenforced; refusing before the
        # first call costs nothing. OpenRouter reports its own cost.
        if max_spend_usd is None or not (runner_config.provider or runner_config.model_name):
            return None
        runners = AgentSpendCap._chain_runners(runner_config, fallback)
        runner_type = runners[0].resolve_runner_type()
        if runner_type != RUNNER_TYPE_TEXT:
            return f"its {runner_type} runner runs outside the agent loop, which is the only place the spend cap is enforced."
        unpriced = AgentSpendCap._unpriced_pairs(runners)
        if unpriced:
            return f"the pricebook has no price for {', '.join(unpriced)}, so its spend could not be measured."
        return None

    @staticmethod
    def _blind_causes(rollup: UsageRollup) -> list[str]:
        # Names every cause that left spend unmeasured, in a fixed
        # order, using names and counts only.
        causes: list[str] = []
        unpriced_calls = sorted({f"{record.provider}:{record.model}" for record in rollup.calls if record.cost_usd is None})
        if unpriced_calls:
            causes.append(f"no price for {', '.join(unpriced_calls)}")
        unpriced_operations = sorted({f"{record.provider}:{record.operation}" for record in rollup.operations if record.cost_usd is None})
        if unpriced_operations:
            causes.append(f"no price for operation {', '.join(unpriced_operations)}")
        if rollup.unaccounted_call_count:
            causes.append(f"{rollup.unaccounted_call_count} model calls reported no usage")
        if rollup.recording_integrity is UsageRecordingIntegrity.CORRUPTED:
            causes.append("usage recording failed")
        return causes

    @staticmethod
    def _chain_runners(runner_config: AgentRunnerConfig, fallback: AgentFallback | None) -> list[Runner]:
        # One Runner per configured model, primary first, so each model
        # is read with the runner's own provider normalization.
        if fallback is None:
            return [Runner.from_model(provider=runner_config.provider, model_name=runner_config.model_name)]
        return [Runner.from_model(provider=entry.provider, model_name=entry.model) for entry in fallback.models]

    @staticmethod
    def _unpriced_pairs(runners: Sequence[Runner]) -> list[str]:
        # Lists each distinct provider:model the pricebook cannot price,
        # in chain order, showing a missing part as "?".
        registry = ModelPricingRegistry.default()
        pairs: list[str] = []
        for runner in runners:
            if runner.provider == ModelProvider.OPENROUTER.value:
                continue
            priced = bool(runner.provider and runner.model_name) and registry.resolve(ModelProvider(runner.provider), runner.model_name) is not None
            pair = f"{runner.provider or '?'}:{runner.model_name or '?'}"
            if not priced and pair not in pairs:
                pairs.append(pair)
        return pairs


__all__ = ["AgentSpendCap"]
