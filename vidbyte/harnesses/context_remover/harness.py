from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from vidbyte.harnesses.context_remover.types import (
    ConditionalHarnessState,
    ContextRemoverConfig,
    PurificationContract,
    PurificationResult,
)
from vidbyte.lib.errors import HarnessExecutionError
from vidbyte.shared import HarnessRole, LedgerEntry, ModelFunction


DEFAULT_PURIFIER_TEMPLATE = """You are purifying a noisy execution trace.

Immutable anchor:
{immutable_anchor}

Raw execution ledger:
{raw_execution_ledger}

Target extraction contract:
{target_extraction_contract}

Return only the concentrated summary. Keep it under {max_summary_chars} characters.
"""


class ContextRemoverHarness:
    """Outer harness that periodically compresses active execution context."""

    def __init__(
        self,
        *,
        original_intent: str,
        purifier_model_fn: ModelFunction,
        config: ContextRemoverConfig | None = None,
        contract: PurificationContract | None = None,
        prompt_registry: object | None = None,
    ) -> None:
        if not original_intent.strip():
            raise HarnessExecutionError("original_intent must not be empty")
        if not callable(purifier_model_fn):
            raise HarnessExecutionError("purifier_model_fn must be callable")
        self.original_intent = original_intent
        self.purifier_model_fn = purifier_model_fn
        self.config = config or ContextRemoverConfig()
        self.contract = contract or PurificationContract()
        self.prompt_registry = prompt_registry
        self._steps_since_purification = 0
        self._locked = False

    async def intercept_step(
        self,
        state: ConditionalHarnessState,
        step_fn: Callable[[ConditionalHarnessState], Awaitable[Any]],
    ) -> Any:
        if self._locked:
            raise HarnessExecutionError("context remover state is already executing a step")
        if self._steps_since_purification >= self.config.purify_every_n_steps:
            await self.purify(state)
            self._steps_since_purification = 0

        self._locked = True
        try:
            result = step_fn(state)
            output = await result if inspect.isawaitable(result) else result
            self._steps_since_purification += 1
            if output is not None:
                state.history.append(
                    LedgerEntry(role=HarnessRole.SYSTEM, kind="downstream_step_result", content=str(output))
                )
            return output
        finally:
            self._locked = False

    async def purify(self, state: ConditionalHarnessState) -> PurificationResult:
        if self._locked:
            raise HarnessExecutionError("cannot purify while a downstream step is active")

        self._locked = True
        try:
            before_entries = len(state.history)
            if before_entries == 0:
                result = PurificationResult(
                    summary=state.baseline_context,
                    before_entries=0,
                    after_entries=0,
                    metadata={"noop": True},
                )
                state.metadata["last_purification"] = result
                return result

            raw_ledger = self._format_ledger(state.history)
            if len(raw_ledger) > self.config.max_raw_ledger_chars:
                raw_ledger = raw_ledger[-self.config.max_raw_ledger_chars :]

            prompt = self._render_prompt(raw_ledger)
            purifier_result = self.purifier_model_fn(
                prompt,
                context=[
                    LedgerEntry(
                        role=HarnessRole.PURIFIER,
                        kind="purification_request",
                        content="isolated purification context",
                    )
                ],
                tools=(),
            )
            summary = str(await purifier_result if inspect.isawaitable(purifier_result) else purifier_result)
            if len(summary) > self.contract.max_summary_chars:
                summary = summary[: self.contract.max_summary_chars]

            retained = state.history[-self.config.retain_last_entries :] if self.config.retain_last_entries else []
            summary_entry = LedgerEntry(
                role=HarnessRole.PURIFIER,
                kind="purified_summary",
                content=summary,
                metadata={"source_entries": before_entries},
            )
            state.history = [summary_entry, *retained]
            state.baseline_context = summary
            state.token_offset = len(summary)

            result = PurificationResult(
                summary=summary,
                before_entries=before_entries,
                after_entries=len(state.history),
                metadata={"retained_entries": len(retained)},
            )
            state.metadata["last_purification"] = result
            return result
        except HarnessExecutionError:
            raise
        except Exception as error:
            raise HarnessExecutionError(f"context purification failed: {error}") from error
        finally:
            self._locked = False

    def _render_prompt(self, raw_ledger: str) -> str:
        variables = {
            "immutable_anchor": self.original_intent,
            "raw_execution_ledger": raw_ledger,
            "target_extraction_contract": self.contract.to_instruction_text(),
            "max_summary_chars": self.contract.max_summary_chars,
        }
        rendered = self._try_prompt_registry(variables)
        if rendered is not None:
            return rendered
        return DEFAULT_PURIFIER_TEMPLATE.format(**variables)

    def _try_prompt_registry(self, variables: dict[str, Any]) -> str | None:
        if self.prompt_registry is None or not hasattr(self.prompt_registry, "get"):
            return None
        try:
            rendered = self.prompt_registry.get(self.config.prompt_key, **variables)
        except Exception:
            return None
        return getattr(rendered, "text", str(rendered))

    def _format_ledger(self, entries: list[LedgerEntry]) -> str:
        return "\n".join(
            f"[{index}] role={entry.role.value} kind={entry.kind} content={entry.content}"
            for index, entry in enumerate(entries, start=1)
        )


__all__ = ["ContextRemoverHarness", "DEFAULT_PURIFIER_TEMPLATE"]
