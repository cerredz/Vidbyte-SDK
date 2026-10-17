"""FILE: tests/features/codex_host/test_codex_host_turn_settings.py

PURPOSE: Proves the turn settings the hardening slice adds, as a real host sends them: a goal run refuses every turn-only field before any request and still starts with thread settings alone; the max and ultra efforts reach turn/start; model service tiers are listed, sent as serviceTierForTurn and checked against the listed tiers unless a custom provider is set; and network access and writable roots reach the turn's sandbox policy, while fork and review refuse them.
ROLE IN CODEBASE: Turn-settings layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-29 host half, AC-30 wire half, AC-31, AC-32, INV-34 to INV-37, EC-34, EC-35, EC-37, EC-38, D-15 to D-17, D-26). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: Every assertion reads the params the fake app-server received or the record the host returned. The fake's model list is replaced with one model that lists two tiers, so the tier check has exactly one list to read.
COMMON MODIFICATION PATTERNS: A new turn field adds one wire row to the sandbox or tier test and one refusal row to the goal test.
KNOWN EDGE CASES: openai-codex dumps a workspace-write policy with its defaults (excludeSlashTmp and excludeTmpdirEnvVar as false), so the policy check pins the three fields the spec names and requires every other key to be false. network_access and writable_roots need a non-default turn, which the goal rule refuses first, so their goal rows assert only that the run is refused before any request (S2 report, spec defects).
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md section 6.1 (INV-34 to INV-37) and section 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_turn_settings.py
"""

from __future__ import annotations

import asyncio
import os
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    GOAL_FIELD_MESSAGE,
    GOAL_RUN_OWNER,
    WAIT_SECONDS,
    HostTestCase,
    requires_sdk,
)
from vidbyte.lib.errors import ConfigurationError

EXTRA_ROOT = os.path.abspath(os.path.join(os.sep, "extra-root"))
TIERS = [{"id": "fast", "name": "Fast", "description": "Faster responses at a higher price."}, {"id": "flex", "name": "Flex", "description": "Slower and cheaper."}]


class TurnSettingsTestCase(HostTestCase):
    """HostTestCase plus the last turn/start's params."""

    def last_turn_start(self) -> dict[str, Any]:
        return self.server.matching("turn/start")[-1].params


@requires_sdk
class CodexGoalRunFieldTests(TurnSettingsTestCase):
    """AC-29, INV-34 and D-15: run_codex_goal refuses a turn-only field before any request."""

    async def test_each_turn_only_field_is_refused_before_any_request_and_thread_settings_still_start(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReasoningEffort, CodexSandbox

        host = await self.open_host()
        sent = len(self.server.requests)
        named = (
            ("turn", CodexSpawnRequest(turn=CodexTurnSettings(effort=CodexReasoningEffort.HIGH))),
            ("output_schema", CodexSpawnRequest(output_schema={"type": "object"})),
            ("disabled_plugin_ids", CodexSpawnRequest(disabled_plugin_ids=("plugin-a",))),
            ("turn_service_tier", CodexSpawnRequest(turn_service_tier="fast")),
        )
        for name, request in named:
            with self.subTest(field=name):
                with self.assertRaises(ConfigurationError) as caught:
                    await asyncio.wait_for(host.run_codex_goal("Ship the fix.", request=request), WAIT_SECONDS)
                self.assertEqual(str(caught.exception), GOAL_FIELD_MESSAGE.format(owner=GOAL_RUN_OWNER, name=name))
        workspace = CodexTurnSettings(sandbox=CodexSandbox.WORKSPACE_WRITE)
        for name, request in (("network_access", CodexSpawnRequest(turn=workspace, network_access=True)), ("writable_roots", CodexSpawnRequest(turn=workspace, writable_roots=(EXTRA_ROOT,)))):
            with self.subTest(field=name):
                with self.assertRaises(ConfigurationError):
                    await asyncio.wait_for(host.run_codex_goal("Ship the fix.", request=request), WAIT_SECONDS)
        self.assertEqual(len(self.server.requests), sent)
        await asyncio.wait_for(host.run_codex_goal("Ship the fix.", request=CodexSpawnRequest(thread=CodexThreadSettings(model="gpt-5.5"))), WAIT_SECONDS)
        self.assertEqual(self.server.matching("thread/start")[-1].params.get("model"), "gpt-5.5")


@requires_sdk
class CodexEffortWireTests(TurnSettingsTestCase):
    """AC-30 and INV-35: the two new efforts are sent as their strings."""

    async def test_max_and_ultra_reach_turn_start(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        host = await self.open_host()
        for effort, wire in ((CodexReasoningEffort.MAX, "max"), (CodexReasoningEffort.ULTRA, "ultra")):
            with self.subTest(effort=wire):
                await self.spawn(host, turn=CodexTurnSettings(effort=effort))
                self.assertEqual(self.last_turn_start().get("effort"), wire)


@requires_sdk
class CodexServiceTierTests(TurnSettingsTestCase):
    """AC-31, INV-36, EC-34, EC-35 and D-16: tiers are listed, sent and checked."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        model = dict(self.fakes._model("gpt-5.5", "gpt-5.5", default=True))
        model.update({"serviceTiers": TIERS, "defaultServiceTier": "flex"})
        self.server.model_pages = [[model]]

    async def test_listed_tiers_are_mirrored_on_the_model_record(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexServiceTier

        host = await self.open_host()
        models = await asyncio.wait_for(host.list_codex_models(), WAIT_SECONDS)
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].service_tiers, tuple(CodexServiceTier(tier_id=tier["id"], name=tier["name"], description=tier["description"]) for tier in TIERS))
        self.assertEqual(models[0].default_service_tier, "flex")

    async def test_a_listed_tier_or_default_is_sent_and_an_unlisted_one_is_refused_before_the_thread_starts(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings

        host = await self.open_host()
        for tier in ("fast", "default"):
            with self.subTest(tier=tier):
                await self.spawn(host, turn_service_tier=tier)
                self.assertEqual(self.last_turn_start().get("serviceTierForTurn"), tier)
        await self.spawn(host)
        self.assertNotIn("serviceTierForTurn", self.last_turn_start())
        for label, fields in (
            ("turn_service_tier", {"turn_service_tier": "warp"}),
            ("turn.service_tier", {"turn": CodexTurnSettings(service_tier="warp")}),
            ("thread.service_tier", {"thread": CodexThreadSettings(service_tier="warp")}),
        ):
            with self.subTest(unlisted=label):
                starts = self.count("thread/start")
                error = await self.assert_codex_error(self.spawn(host, **fields), "codex.model_unknown")
                self.assertIn("Codex lists no service tier warp", error.message)
                self.assertIn("fast", error.message)
                self.assertIn("flex", error.message)
                self.assertEqual(self.count("thread/start"), starts)

    async def test_a_custom_provider_skips_the_tier_check(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings

        host = await self.open_host()
        await self.spawn(host, thread=CodexThreadSettings(model="llama-local", model_provider="ollama"), turn_service_tier="warp")
        self.assertEqual(self.last_turn_start().get("serviceTierForTurn"), "warp")

    async def test_a_named_model_that_lists_no_tiers_is_not_checked(self) -> None:
        # EC-35: only tiers a model lists can rule a tier out, so a tierless named model leaves the choice to Codex.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings

        self.server.model_pages = [[*self.server.model_pages[0], self.fakes._model("gpt-5.4", "gpt-5.4")]]
        host = await self.open_host()
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.4"), turn_service_tier="warp")
        self.assertEqual(self.last_turn_start().get("serviceTierForTurn"), "warp")


@requires_sdk
class CodexSandboxAccessTests(TurnSettingsTestCase):
    """AC-32, INV-37, EC-37, EC-38 and D-17: network access and writable roots inside the turn's sandbox policy."""

    async def test_network_access_and_writable_roots_reach_the_sandbox_policy(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexSandbox

        host = await self.open_host()
        await self.spawn(host, turn=CodexTurnSettings(sandbox=CodexSandbox.WORKSPACE_WRITE), network_access=True, writable_roots=(EXTRA_ROOT,))
        policy = self.last_turn_start()["sandboxPolicy"]
        named = ("type", "networkAccess", "writableRoots")
        self.assertEqual({key: policy.get(key) for key in named}, {"type": "workspaceWrite", "networkAccess": True, "writableRoots": [EXTRA_ROOT]})
        self.assertEqual({key: value for key, value in policy.items() if key not in named and value is not False}, {})
        await self.spawn(host, turn=CodexTurnSettings(sandbox=CodexSandbox.READ_ONLY), network_access=True)
        self.assertEqual(self.last_turn_start()["sandboxPolicy"], {"type": "readOnly", "networkAccess": True})

    async def test_fork_and_review_refuse_the_two_fields_before_any_request(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReviewTargetKind, CodexSandbox

        host = await self.open_host()
        stored = self.server.seed_thread()
        workspace = CodexTurnSettings(sandbox=CodexSandbox.WORKSPACE_WRITE)
        target = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
        sent = len(self.server.requests)
        for label, request in (("network_access", CodexSpawnRequest(turn=workspace, network_access=True)), ("writable_roots", CodexSpawnRequest(turn=workspace, writable_roots=(EXTRA_ROOT,)))):
            for operation, call in (("fork", lambda: host.fork_codex_thread(stored.thread_id, overrides=request)), ("review", lambda: host.start_codex_review(stored.thread_id, target, request=request))):
                with self.subTest(field=label, operation=operation):
                    with self.assertRaises(ConfigurationError):
                        await asyncio.wait_for(call(), WAIT_SECONDS)
        self.assertEqual(len(self.server.requests), sent)


if __name__ == "__main__":
    unittest.main()
