"""FILE: tests/features/jev_skills_preload/test_skill_sources_jev_wiring.py

PURPOSE: Pin how the Jev skill preload uses the loader: an InlineSkill's text is appended byte for byte, every result explains an unavailable skill with a reason and detail (too large for Jev, a failed batch, an unusable reply, a missing answer), too_large from batching is recomputed every run, a run where nothing loads asks Jev nothing, entries and caller documents batch in settings order, and the explicit system baseline still holds.
ROLE IN CODEBASE: Covers spec AC-3, AC-14, INV-16, INV-17, INV-22 to INV-27, FR-6, FR-13, FR-14, D-8 and EC-11, EC-12, EC-21, EC-104 to EC-108 for vidbyte/agents/jev/alignment/skills.py (JevSkillsPreload) and vidbyte/agents/skills/inline.py.
ARCHITECTURE NOTE: Exact-text checks run at the preload level, where the returned context's system prompt is the whole truth; agent-level checks use an explicit system baseline, which the runtime passes through unchanged. Jev is the conftest's NamedJev, which answers by skill name, so batch boundaries never decide which skill an answer belongs to.
FUNCTION INVENTORY: test_inline_text_is_appended_byte_for_byte; test_every_unavailable_result_explains_why; test_too_large_for_jev_is_recomputed_every_run; test_a_run_where_nothing_loads_asks_jev_nothing; test_batches_read_only_loaded_documents_in_settings_order; test_explicit_system_stays_the_baseline_with_entries_and_strings.
COMMON MODIFICATION PATTERNS: A new preload-set reason adds a skill to the AC-14 run with its own scripted Jev behavior.
WHAT NOT TO DO IN THIS FILE: 1. Do not change Jev limits or question wording to make a case fit; the text sizes below were calibrated against the current limits. 2. Do not assert skill text inside agent.response; INV-24 keeps it out.
KNOWN EDGE CASES: An 8,000-character text fills a batch on its own and a 35,000-character text fits none; a 4,000-character text fits beside a short message but not beside a 10,000-character one, which is why too_large must be recomputed per run.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 6.1 results and must-not-regress, 9.2 Jev preload details); tests/test_jev_skill_preload.py
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_jev_wiring.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vidbyte.agents.jev.alignment.skills import JevSkillsPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_SKILLS_MAX_REQUEST_JSON_BYTES,
    JEV_SKILLS_PROMPT_SECTION,
)
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.skills import SkillDocument

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        AnthropicSkill,
        GitHubSkill,
        InlineSkill,
        JevSkillStatus,
        LocalSkill,
        SkillsShSkill,
        SkillUnavailableReason,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

EXACT_TEXT = "  Two leading spaces.\n\tA tab.\n```python\nprint('kept')\n```\n\n"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _preload(skills: tuple[Any, ...]) -> JevSkillsPreload:
    # The same construction JevAgent uses, through the preload's unchanged keyword signature (INV-26).
    return JevSkillsPreload(skills=skills, decision=DecisionModelConfig(api_key="test-key"), threshold=0.5, response=JevResponse())


def _inline(name: str, size: int) -> Any:
    return InlineSkill(name=name, description=f"The {name} skill.", text=(name + " ") * (size // (len(name) + 1)) + "x" * (size % (len(name) + 1)))


@pytest.mark.asyncio
async def test_inline_text_is_appended_byte_for_byte(jev: Callable[..., Any]) -> None:
    # AC-3, EC-11, FR-6, INV-24: trimming or re-indenting the text would change indentation-sensitive guidance.
    jev({"house-review": 0.9})
    preload = _preload((InlineSkill(name="house-review", description="Our PR review checklist.", text=EXACT_TEXT),))
    context = await preload.run("Review PR 182.", BaseAgentContext(system_prompt="Base."))
    assert context.system_prompt == "Base." + JEV_SKILLS_PROMPT_SECTION + EXACT_TEXT
    (result,) = preload.response.state.skills.results
    assert (result.name, result.description, result.source, result.status, result.reason, result.detail) == ("house-review", "Our PR review checklist.", "inline", JevSkillStatus.SELECTED, None, None)
    assert EXACT_TEXT not in repr(preload.response.state)


@pytest.mark.asyncio
async def test_every_unavailable_result_explains_why(jev: Callable[..., Any]) -> None:
    # AC-14, INV-17, INV-22, INV-23, EC-104 to EC-106: each reason is distinct, and the failed-batch detail points at VIDBYTE_API_KEY.
    runner = jev({"fits": 0.9, "unanswered": 0.9, "uncounted": 0.9, "outage": 0.9}, fail={"outage"}, missing={"unanswered"}, unreported_usage={"uncounted"})
    entries = (_inline("fits", 8000), _inline("huge", 35000), _inline("outage", 8000), _inline("unanswered", 8000), _inline("uncounted", 8000))
    preload = _preload(entries)
    context = await preload.run("Review the change.", BaseAgentContext(system_prompt="Base."))
    fits, huge, outage, unanswered, uncounted = preload.response.state.skills.results
    assert (fits.status, fits.reason, fits.detail) == (JevSkillStatus.SELECTED, None, None)
    assert [(result.status, result.reason) for result in (huge, outage, unanswered, uncounted)] == [
        (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.TOO_LARGE),
        (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.DECISION_FAILED),
        (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.DECISION_FAILED),
        (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.DECISION_FAILED),
    ]
    # Loaded skills keep their description and label even when unavailable (INV-17).
    assert all((result.description, result.source) == (f"The {result.name} skill.", "inline") for result in (huge, outage, unanswered, uncounted))
    assert all(result.detail and result.detail.strip() for result in (huge, outage, unanswered, uncounted))
    assert len({outage.detail, unanswered.detail, uncounted.detail}) == 3
    assert "ProviderRequestError" in outage.detail and "VIDBYTE_API_KEY" in outage.detail
    assert "jev" in huge.detail.lower()
    assert "JEV_SKILLS_MAX_REQUEST_JSON_BYTES" in huge.detail or str(JEV_SKILLS_MAX_REQUEST_JSON_BYTES) in huge.detail.replace(",", "").replace("_", ""), huge.detail
    # The too-large skill never reached Jev, and usage counts only the batches whose replies carried token counts.
    assert "huge" not in runner.asked
    assert preload.response.state.skills.usage.input_tokens == 20
    assert context.system_prompt == "Base." + JEV_SKILLS_PROMPT_SECTION + entries[0].text


@pytest.mark.asyncio
async def test_too_large_for_jev_is_recomputed_every_run(jev: Callable[..., Any]) -> None:
    # EC-12, EC-21, INV-22: the limit depends on the request, so a skill too large beside one message is fine beside the next.
    jev({"medium": 0.9})
    preload = _preload((_inline("medium", 4000),))
    statuses = []
    for message in ("Short request.", "x" * 10_000, "Short again."):
        await preload.run(message, BaseAgentContext(system_prompt="Base."))
        (result,) = preload.response.state.skills.results
        statuses.append((result.status, result.reason))
    assert statuses == [(JevSkillStatus.SELECTED, None), (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.TOO_LARGE), (JevSkillStatus.SELECTED, None)]


@pytest.mark.asyncio
async def test_a_run_where_nothing_loads_asks_jev_nothing(tmp_path: Path, fake_http: Any, jev: Callable[..., Any]) -> None:
    # EC-107, INV-16, INV-17, INV-25: one result per entry in settings order, each with its load reason, and the context object untouched.
    fake_http.answer("https://api.github.com/repos/acme/gone/commits/HEAD", fake_http.reply(404, "missing"))
    runner = jev()
    preload = _preload((LocalSkill(name="local-gone", path=tmp_path / "absent"), SkillsShSkill(name="sh-gone", source="acme/skills"), AnthropicSkill(name="no-key", skill_id="skill_x"), GitHubSkill(name="gh-gone", repo="acme/gone")))
    original = BaseAgentContext(system_prompt="Base.")
    context = await preload.run("Do the work.", original)
    assert context is original
    assert runner.requests == []
    results = preload.response.state.skills.results
    assert [result.name for result in results] == ["local-gone", "sh-gone", "no-key", "gh-gone"]
    assert [result.reason for result in results] == [SkillUnavailableReason.NOT_FOUND, SkillUnavailableReason.NOT_INSTALLED, SkillUnavailableReason.AUTH_FAILED, SkillUnavailableReason.NOT_FOUND]
    assert all((result.status, result.description, result.source, result.probability) == (JevSkillStatus.UNAVAILABLE, None, None, None) for result in results)
    assert all(result.detail.strip() for result in results)
    assert preload.response.state.skills.usage.input_tokens == 0


@pytest.mark.asyncio
async def test_batches_read_only_loaded_documents_in_settings_order(jev: Callable[..., Any]) -> None:
    # D-8, INV-26: before any run only caller documents can be batched; after a run every loaded entry joins in settings order.
    first = SkillDocument(name="first", description="First.", text="First body.", source="caller://1")
    third = SkillDocument(name="third", description="Third.", text="Third body.")
    preload = _preload((first, InlineSkill(name="second", description="Second.", text="Second body."), third))
    assert [index for batch in preload._build_batches("Do the work.") for index in batch.indices] == [1, 3]
    jev(default=0.9)
    context = await preload.run("Do the work.", BaseAgentContext(system_prompt="Base."))
    assert [index for batch in preload._build_batches("Do the work.") for index in batch.indices] == [1, 2, 3]
    assert context.system_prompt == "Base." + JEV_SKILLS_PROMPT_SECTION + "\n\n---\n\n".join(("First body.", "Second body.", "Third body."))
    assert [result.source for result in preload.response.state.skills.results] == ["caller://1", "inline", None]


@pytest.mark.asyncio
async def test_explicit_system_stays_the_baseline_with_entries_and_strings(make_agent: Callable[..., Any], jev: Callable[..., Any]) -> None:
    # INV-27, EC-108, INV-20: entries, caller documents, and plain strings share one ordered result list and one appended section.
    jev({"house-review": 0.9, "inline_skill_2": 0.9, "doc": 0.1})
    agent, runner = make_agent([InlineSkill(name="house-review", description="Checklist.", text=EXACT_TEXT), "Plain string guidance.", SkillDocument(name="doc", description="Doc.", text="Doc body.")])
    await agent.arun("Review it.", system="Caller baseline.")
    assert runner.systems == ["Caller baseline." + JEV_SKILLS_PROMPT_SECTION + EXACT_TEXT + "\n\n---\n\n" + "Plain string guidance."]
    assert [(result.name, result.status, result.source) for result in agent.response.skills.results] == [("house-review", JevSkillStatus.SELECTED, "inline"), ("inline_skill_2", JevSkillStatus.SELECTED, "inline"), ("doc", JevSkillStatus.SKIPPED, None)]
    assert agent.system_prompt == "Agent base prompt."
