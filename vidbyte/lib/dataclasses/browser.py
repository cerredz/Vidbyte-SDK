"""FILE: vidbyte/lib/dataclasses/browser.py

PURPOSE: Defines the records of the BrowserAgent: BrowserGoalCard, the run's goal, done criteria, plan, progress, and blockers; BrowserRecipeStep, one browser call a finished episode made; BrowserEpisodeResult, what one episode returned; BrowserRecheckResult, one fresh-context verdict; BrowserEvent, one progress event; BrowserAgentResponse, the record a developer reads after a run; and the three pydantic payloads the worker, the recheck, and the done-when agents answer with.
ROLE IN CODEBASE: Built and read by vidbyte/agents/browser/: BrowserGoal keeps the card and builds recheck results, BrowserEpisodeTool turns a worker's BrowserEpisodePayload into a BrowserEpisodeResult, BrowserGoalCheck reads the verdict and done-when payloads, BrowserAgentEvents builds events, and BrowserResponse is the one writer of BrowserAgentResponse. BrowserEvent is also a root export, because a developer's on_event sink receives it.
ARCHITECTURE NOTE: Validation only. Every check of a frozen record runs in __post_init__ and is one call to the SDK's canonical RecordFieldValidator or RecordFieldConverter (vidbyte/lib/dataclasses/validation.py), with bounds from vidbyte/lib/constants/browser.py; only the done_when minimum of one criterion and the progress total are checked here by hand, because the validators have no minimum-count or total-size option. The payloads carry no length limits: the agents layer cuts a model's answer to the record caps, so a long answer never fails an episode. BrowserAgentResponse is mutable and unvalidated, like JevAgentResponse, because only BrowserResponse writes it.
FUNCTION INVENTORY: Five frozen, slotted records with __post_init__ checks (BrowserGoalCard, BrowserRecipeStep, BrowserEpisodeResult, BrowserRecheckResult, BrowserEvent), the mutable BrowserAgentResponse, and three pydantic models (BrowserEpisodePayload, BrowserVerdictPayload, BrowserDoneWhenPayload).
COMMON MODIFICATION PATTERNS: A new card section adds one field to BrowserGoalCard, one validator call, one BrowserGoalSection member, and one placeholder in the goal_card leaf. A new episode-card field adds one field here and on BrowserEpisodePayload, with its cap in the constants module and its copy in BrowserEpisodeTool.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents, vidbyte.tools, or any other layer above vidbyte/lib at runtime; UsageRollup is imported only for type checking. 2. Do not add to_dict or from_dict methods or dict[str, Any] signatures. 3. Do not convert a list into a tuple here; the caller converts, and the record refuses anything else.
KNOWN EDGE CASES: The progress total counts the characters of its items without separators. A refusal of the progress total names the whole field, BrowserGoalCard.progress, while a refusal of one item names it with its index, so a caller can tell a full card from a bad line. An episode summary may be empty, because a worker may report only facts. True is refused wherever a whole number is expected.
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 8.5 and 9.1); vidbyte/agents/browser/README.md
TESTS: tests/features/browser_agent/test_browser_agent_goal.py, tests/features/browser_agent/test_browser_agent_episode.py, and tests/features/browser_agent/test_browser_agent_recheck.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from vidbyte.lib.constants.browser import (
    BROWSER_BLOCKERS_MAX_CHARS,
    BROWSER_EVENT_DETAIL_MAX_CHARS,
    BROWSER_FIRST_INDEX,
    BROWSER_ITEM_MAX_CHARS,
    BROWSER_MAX_CRITERIA,
    BROWSER_MAX_ITEMS,
    BROWSER_MIN_COUNT,
    BROWSER_PLAN_MAX_CHARS,
    BROWSER_PROGRESS_MAX_CHARS,
    BROWSER_SUMMARY_MAX_CHARS,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.browser import (
    BrowserEpisodeOutcome,
    BrowserEventKind,
    BrowserVerdict,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.pricing import UsageRollup


@dataclass(frozen=True, slots=True)
class BrowserGoalCard:
    """The run's goal card: the goal and done criteria, fixed for the run, and the plan, progress facts, and blockers the orchestrator keeps current."""

    goal: str
    done_when: tuple[str, ...]
    plan: str = ""
    progress: tuple[str, ...] = ()
    blockers: str = ""

    def __post_init__(self) -> None:
        # The goal is the run's message, kept verbatim, so it only has
        # to say something.
        RecordFieldValidator.require_text(self.goal, "BrowserGoalCard.goal")

        # A run is judged against its criteria, so there is at least
        # one, each a short line.
        RecordFieldValidator.require_text_items(self.done_when, "BrowserGoalCard.done_when", max_items=BROWSER_MAX_CRITERIA, max_chars=BROWSER_ITEM_MAX_CHARS, one_line=True)
        if not self.done_when:
            raise ConfigurationError("BrowserGoalCard.done_when must hold at least one criterion; got none.", details={"field": "BrowserGoalCard.done_when"})

        # The plan and blockers are free text under their caps, and
        # empty clears them.
        RecordFieldValidator.require_text(self.plan, "BrowserGoalCard.plan", max_chars=BROWSER_PLAN_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_text(self.blockers, "BrowserGoalCard.blockers", max_chars=BROWSER_BLOCKERS_MAX_CHARS, allow_blank=True)

        # @intent the-progress-section-has-a-total-cap
        # Each progress fact is one short line, and all of them together
        # fit the card's budget; the total refusal names the whole field
        # so the patch tool can say the card is full.
        RecordFieldValidator.require_text_items(self.progress, "BrowserGoalCard.progress", max_chars=BROWSER_ITEM_MAX_CHARS, one_line=True)
        total = sum(len(item) for item in self.progress)
        if total > BROWSER_PROGRESS_MAX_CHARS:
            raise ConfigurationError(f"BrowserGoalCard.progress may hold at most {BROWSER_PROGRESS_MAX_CHARS} characters in total; got {total}.", details={"field": "BrowserGoalCard.progress"})


@dataclass(frozen=True, slots=True)
class BrowserRecipeStep:
    """One browser call a finished episode executed successfully: the tool name and the JSON text of its arguments."""

    tool: str
    arguments: str

    def __post_init__(self) -> None:
        # Both are what really ran, copied from the worker's call
        # record.
        RecordFieldValidator.require_text(self.tool, "BrowserRecipeStep.tool", one_line=True)
        RecordFieldValidator.require_text(self.arguments, "BrowserRecipeStep.arguments")


@dataclass(frozen=True, slots=True)
class BrowserEpisodeResult:
    """What one run_episode call returned: the worker's card within its caps, the calls it made, and how it stopped."""

    index: int
    task: str
    done_when: str
    outcome: BrowserEpisodeOutcome
    summary: str
    facts: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    recipe: tuple[BrowserRecipeStep, ...] = ()
    actions: int | None = None
    tokens: int | None = None
    stop_reason: str = ""

    def __post_init__(self) -> None:
        # Episodes are numbered from 1 within a run, and the task and
        # its check are what the orchestrator asked for.
        RecordFieldValidator.require_int(self.index, "BrowserEpisodeResult.index", minimum=BROWSER_FIRST_INDEX)
        for name in ("task", "done_when"):
            RecordFieldValidator.require_text(getattr(self, name), f"BrowserEpisodeResult.{name}")
        RecordFieldValidator.require_enum(self.outcome, BrowserEpisodeOutcome, "BrowserEpisodeResult.outcome")

        # The card's text stays within its caps; the episode tool cuts
        # a worker's answer to them before building this record.
        RecordFieldValidator.require_text(self.summary, "BrowserEpisodeResult.summary", max_chars=BROWSER_SUMMARY_MAX_CHARS, allow_blank=True)
        for name in ("facts", "urls", "evidence"):
            RecordFieldValidator.require_text_items(getattr(self, name), f"BrowserEpisodeResult.{name}", max_items=BROWSER_MAX_ITEMS, max_chars=BROWSER_ITEM_MAX_CHARS)
        RecordFieldConverter.require_instance(self.recipe, "BrowserEpisodeResult.recipe", tuple)
        for index, step in enumerate(self.recipe):
            RecordFieldConverter.require_instance(step, f"BrowserEpisodeResult.recipe[{index}]", BrowserRecipeStep)

        # The counts are unknown (None) when the worker raised before
        # it replied, and never negative.
        for name in ("actions", "tokens"):
            if getattr(self, name) is not None:
                RecordFieldValidator.require_int(getattr(self, name), f"BrowserEpisodeResult.{name}", minimum=BROWSER_MIN_COUNT)
        RecordFieldValidator.require_text(self.stop_reason, "BrowserEpisodeResult.stop_reason", one_line=True, allow_blank=True)


@dataclass(frozen=True, slots=True)
class BrowserRecheckResult:
    """One recheck that produced a verdict: its number, the episodes finished so far, the verdict and gap, whether it judged a finish, and the stall count after it."""

    index: int
    episodes: int
    verdict: BrowserVerdict
    gap: str
    at_finish: bool
    stalls: int

    def __post_init__(self) -> None:
        # Rechecks are numbered from 1, and the counts are never
        # negative.
        RecordFieldValidator.require_int(self.index, "BrowserRecheckResult.index", minimum=BROWSER_FIRST_INDEX)
        for name in ("episodes", "stalls"):
            RecordFieldValidator.require_int(getattr(self, name), f"BrowserRecheckResult.{name}", minimum=BROWSER_MIN_COUNT)
        RecordFieldValidator.require_enum(self.verdict, BrowserVerdict, "BrowserRecheckResult.verdict")
        RecordFieldValidator.require_text(self.gap, "BrowserRecheckResult.gap", max_chars=BROWSER_ITEM_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_bool(self.at_finish, "BrowserRecheckResult.at_finish")


@dataclass(frozen=True, slots=True)
class BrowserEvent:
    """One progress event a run sends to on_event: its kind, its number in the run, the episode it belongs to (0 for none), and a one-line detail."""

    kind: BrowserEventKind
    sequence: int
    episode: int
    detail: str

    def __post_init__(self) -> None:
        # Events are numbered from 1, and a detail is one short line
        # that fits a log.
        RecordFieldValidator.require_enum(self.kind, BrowserEventKind, "BrowserEvent.kind")
        RecordFieldValidator.require_int(self.sequence, "BrowserEvent.sequence", minimum=BROWSER_FIRST_INDEX)
        RecordFieldValidator.require_int(self.episode, "BrowserEvent.episode", minimum=BROWSER_MIN_COUNT)
        RecordFieldValidator.require_text(self.detail, "BrowserEvent.detail", max_chars=BROWSER_EVENT_DETAIL_MAX_CHARS, allow_blank=True, one_line=True)


@dataclass(slots=True)
class BrowserAgentResponse:
    """Everything a BrowserAgent run produced, read as BrowserAgent.response.

    BrowserResponse is the only writer: it replaces this record at the
    start of each run. `goal` is the card as it stands after the latest
    patch, `episodes` and `rechecks` are in the order they happened,
    `rebuilds` counts the orchestrator's context rebuilds, and `usage`
    is the run's whole usage rollup, set when the run returns.
    """

    input: str = ""
    output: str = ""
    goal: BrowserGoalCard | None = None
    episodes: list[BrowserEpisodeResult] = field(default_factory=list)
    rechecks: list[BrowserRecheckResult] = field(default_factory=list)
    rebuilds: int = 0
    stop_reason: str | None = None
    usage: UsageRollup | None = None
    event_errors: list[str] = field(default_factory=list)


class BrowserEpisodePayload(BaseModel):
    """The episode card a browser worker returns: how the episode ended, a summary, and the facts, URLs, and evidence it found."""

    model_config = ConfigDict(extra="forbid")

    outcome: BrowserEpisodeOutcome
    summary: str
    facts: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class BrowserVerdictPayload(BaseModel):
    """A recheck's answer: continue, done, or stalled, and one sentence naming what is still missing."""

    model_config = ConfigDict(extra="forbid")

    verdict: BrowserVerdict
    gap: str


class BrowserDoneWhenPayload(BaseModel):
    """The done-when agent's answer: short, checkable criteria that say when the task is done."""

    model_config = ConfigDict(extra="forbid")

    criteria: list[str] = Field(min_length=1)


__all__ = [
    "BrowserAgentResponse",
    "BrowserDoneWhenPayload",
    "BrowserEpisodePayload",
    "BrowserEpisodeResult",
    "BrowserEvent",
    "BrowserGoalCard",
    "BrowserRecheckResult",
    "BrowserRecipeStep",
    "BrowserVerdictPayload",
]
