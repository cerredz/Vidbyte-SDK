"""Context Protocol Header

Description:
    Implements the public Market Auction algorithm configuration.
Purpose:
    Defines the frozen, type-safe settings for a specialist bidding protocol
    where N agent roles bid for a task and the highest-confidence winner executes.
Architecture:
    - MarketAuctionAlgorithm: Immutable public configuration class.
Relations:
    Used by ContextWindowPresets and AgentRuntimeContextAlgorithms to configure
    the runtime adapter.
Similar Files:
    - vidbyte/context/algorithms/multi_provider_agentic_grader.py: Similar pattern
      of multi-agent dispatch with a selection stage.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import ConfigurationError

_MAX_AGENTS_LIMIT = 20
_MAX_BID_CHARS_LIMIT = 1_000_000
_MAX_EXECUTOR_CHARS_LIMIT = 1_000_000

_DEFAULT_AUCTIONEER_SYSTEM_PROMPT = (
    "You are a task routing expert. Given a task, identify {num_agents} specialist roles "
    "best suited to handle it. Respond with a JSON array of role name strings only — "
    "no prose, no markdown fences. Example: [\"Data Analyst\", \"Code Reviewer\", \"Domain Expert\"]"
)

_DEFAULT_BIDDER_SYSTEM_PROMPT = (
    "You are a {role}. Evaluate whether you can handle the given task. "
    "Respond with a JSON object with exactly three keys: "
    '"can_handle" (boolean), "confidence" (integer 0-10), "approach" (one sentence describing your plan). '
    "No prose, no markdown fences."
)

_DEFAULT_EXECUTOR_SYSTEM_PROMPT = (
    "You are a {role}. Your approach: {approach}. "
    "Execute the task thoroughly and precisely using your expertise."
)


@dataclass(frozen=True, slots=True)
class MarketAuctionAlgorithm:
    """Public immutable config for the Market Auction runtime algorithm."""

    num_agents: int = 3
    max_bid_chars: int = 600
    max_executor_chars: int = 8000
    roles: tuple[str, ...] | None = None
    auctioneer_system_prompt: str | None = None
    bidder_system_prompt: str | None = None
    executor_system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates all configuration fields at construction time.
        _validate_num_agents(self.num_agents)
        _validate_positive_chars(self.max_bid_chars, "max_bid_chars", limit=_MAX_BID_CHARS_LIMIT)
        _validate_positive_chars(self.max_executor_chars, "max_executor_chars", limit=_MAX_EXECUTOR_CHARS_LIMIT)
        _validate_roles(self.roles, self.num_agents)
        _validate_prompt_override(self.auctioneer_system_prompt, "auctioneer_system_prompt")
        _validate_prompt_override(self.bidder_system_prompt, "bidder_system_prompt")
        _validate_prompt_override(self.executor_system_prompt, "executor_system_prompt")
        _validate_metadata_keys(self.metadata)

    def auctioneer_system_prompt_text(self) -> str:
        """Return the system prompt for role generation."""
        template = self.auctioneer_system_prompt or _DEFAULT_AUCTIONEER_SYSTEM_PROMPT
        return template.format(num_agents=self.num_agents)

    def bidder_system_prompt_text(self, role: str) -> str:
        """Return the system prompt for a bidder agent of the given role."""
        template = self.bidder_system_prompt or _DEFAULT_BIDDER_SYSTEM_PROMPT
        return template.format(role=role)

    def executor_system_prompt_text(self, role: str, approach: str) -> str:
        """Return the system prompt for the winning role's execution stage."""
        template = self.executor_system_prompt or _DEFAULT_EXECUTOR_SYSTEM_PROMPT
        return template.format(role=role, approach=approach)

    def parse_bid(self, bid_text: str) -> dict[str, Any]:
        """Extract JSON bid from bidder output; return safe default on failure."""
        cleaned = _strip_markdown_fences(bid_text.strip())
        try:
            bid = json.loads(cleaned)
            if isinstance(bid, dict):
                return bid
        except (json.JSONDecodeError, ValueError):
            pass
        return {"can_handle": False, "confidence": 0, "approach": ""}

    def parse_roles(self, roles_text: str) -> list[str]:
        """Extract JSON role list from auctioneer output; return empty list on failure."""
        cleaned = _strip_markdown_fences(roles_text.strip())
        try:
            roles = json.loads(cleaned)
            if isinstance(roles, list):
                return [str(r) for r in roles if str(r).strip()][: self.num_agents]
        except (json.JSONDecodeError, ValueError):
            pass
        return []

    def select_winner(self, bids: list[dict[str, Any]], roles: list[str]) -> tuple[str, dict[str, Any]]:
        """Select the highest-confidence bidder that can handle the task."""
        candidates = [
            (role, bid) for role, bid in zip(roles, bids) if bid.get("can_handle", False)
        ]
        if not candidates:
            fallback_role = roles[0] if roles else "General Expert"
            fallback_bid = bids[0] if bids else {"can_handle": True, "confidence": 0, "approach": "Best effort."}
            return fallback_role, {**fallback_bid, "_fallback": True}
        return max(candidates, key=lambda x: int(x[1].get("confidence", 0)))

    def truncate_approach(self, approach: str) -> str:
        """Trim bid approach text to max_bid_chars."""
        if len(approach) <= self.max_bid_chars:
            return approach
        return approach[: self.max_bid_chars].rstrip() + "...[truncated]"


def _strip_markdown_fences(text: str) -> str:
    # Removes leading/trailing ```json or ``` fences from model output.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _validate_num_agents(num_agents: int) -> None:
    # Raises ConfigurationError if num_agents is less than one.
    if num_agents < 1:
        raise ConfigurationError("num_agents must be at least 1.")
    if num_agents > _MAX_AGENTS_LIMIT:
        raise ConfigurationError(f"num_agents ({num_agents}) exceeds the safeguard limit of {_MAX_AGENTS_LIMIT}.")


def _validate_positive_chars(value: int, field_name: str, limit: int | None = None) -> None:
    # Raises ConfigurationError if value is not positive or exceeds optional limit.
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")
    if limit is not None and value > limit:
        raise ConfigurationError(f"{field_name} ({value}) exceeds the safeguard limit of {limit}.")


def _validate_roles(roles: tuple[str, ...] | None, num_agents: int) -> None:
    # Raises ConfigurationError if roles are provided but do not match num_agents or contain empty strings.
    if roles is None:
        return
    if len(roles) != num_agents:
        raise ConfigurationError(
            f"roles tuple length ({len(roles)}) must match num_agents ({num_agents}) when provided."
        )
    for i, role in enumerate(roles):
        if not role.strip():
            raise ConfigurationError(f"roles[{i}] must be a non-empty string.")


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Raises ConfigurationError if an optional prompt override is provided but empty.
    if value is not None and not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if any metadata key is not a string.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


__all__ = [
    "MarketAuctionAlgorithm",
]
