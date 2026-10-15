"""FILE: tests/features/sdk_provider_keys/test_provider_keys_sessions.py

PURPOSE: Proves that saved agents keep their mode and their matching but never their keys: export_state records model_mode and the matched provider names, every restore path rebuilds the same ProviderKeys from the list it is given, live forks take the live record, a restored fork child is matched against its root's names (so an unproven key never moves to the child's vendor), and checkpoints written before this change still restore.
ROLE IN CODEBASE: Session layer of tests/features/sdk_provider_keys/ (spec AC-19, AC-41; INV-14, INV-15; D-30; EC-31, EC-32, EC-52 to EC-54). Exercises vidbyte/agents/base.py (export_state, restore), vidbyte/sessions/session.py (resume, continue_, fork_from, fork) and vidbyte/sessions/failure/recovery/fork_recovery.py with a FileSessionStore in a temporary folder.
ARCHITECTURE NOTE: Runs use real TextModelRunner instances behind the inner-transport seam (RUNNER_TRANSPORT_TARGET), so "ran in DIRECT" means a real vendor-shaped request was sent. Stored files are read back as text to prove no key reached disk.
COMMON MODIFICATION PATTERNS: When a new restore path appears on Session, add it to the AC-19 table with the same three checks (mode, record, no key on disk).
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols (TextModelMode.DIRECT, ProviderKeys) at module level. 2. Do not compare records rebuilt from differently ordered lists with ==; use key_view.
KNOWN EDGE CASES: A restored fork child whose provider differs from the first stored primary is matched with require_primary_key off, so a list holding only the child's key is accepted (EC-54). A root restored with a list that lacks its own provider's key is refused (INV-24 stays on for it).
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 5, 6.1 (INV-14, INV-15), 8.1 (D-30) and 9.1.
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_sessions.py
"""

from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import GATEWAY_URL, RUNNER_TRANSPORT_TARGET, VIDBYTE_KEY, ScriptedGateway, header
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_OPENAI,
    K_UNPROVEN,
    K_XAI,
    ProviderRouter,
    chat_done,
    flat,
    key_view,
    provider_key_header,
)
from vidbyte import Agent, Failure, FailureCode, FailurePhase, ForkRecovery, Session
from vidbyte.agents import AgentForkSettings, BaseAgent
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.sessions import FileSessionStore

ROOT_KEYS = [K_UNPROVEN, K_OPENAI]


def stored_text(root: str) -> str:
    # Everything the file store wrote, as one string, so "no key on disk" is a substring check.
    return "".join(path.read_text(encoding="utf-8") for path in Path(root).rglob("*") if path.is_file())


def deepseek_root(mode: object, **options: object) -> BaseAgent:
    # The AC-18/AC-41 root: deepseek with an openai backup; K_u (unproven) binds to deepseek and K_o to openai.
    values: dict[str, object] = {"fallback": ["openai/gpt-5.5"], "api_keys": ROOT_KEYS, "vidbyte_api_key": VIDBYTE_KEY}
    values.update(options)
    return Agent(name="desk", system_prompt="Work.", provider="deepseek", model_name="deepseek-chat", model_mode=mode, **values)


class SessionRestoreTests(unittest.IsolatedAsyncioTestCase):
    """AC-19: every restore path keeps DIRECT, takes keys only from its arguments, and rebuilds the same record."""

    async def test_every_restore_path_keeps_direct_and_rebuilds_the_roots_record_without_storing_a_key(self) -> None:
        # AC-19, INV-14, INV-15, NG-5: resume, continue_ and fork_from re-match the list; fork and fork recovery take the live record.
        from vidbyte.lib.config import TextModelMode

        failure = Failure(code=FailureCode.RUNTIME_MAX_ITERATIONS, source="test", phase=FailurePhase.LOOP)
        router = ProviderRouter({ModelProvider.DEEPSEEK: chat_done("answer")})
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=router):
            store = FileSessionStore(root)
            agent = deepseek_root(TextModelMode.DIRECT)
            session = Session(agent, store=store)
            await session.arun("Say hi.")
            record = agent.runner_config.api_keys
            head = session.head
            assert head is not None
            rematched = {
                "resume": Session.resume(store, session.id, api_keys=ROOT_KEYS, vidbyte_api_key=VIDBYTE_KEY).agent,
                "continue_": Session.continue_(store, session.id, api_keys=list(reversed(ROOT_KEYS)), vidbyte_api_key=VIDBYTE_KEY).agent,
                "fork_from": Session.fork_from(store, head, api_keys=ROOT_KEYS, vidbyte_api_key=VIDBYTE_KEY).agent,
            }
            live = {
                "fork": session.fork().agent,
                "fork recovery": ForkRecovery().recover(failure, session=session).value.agent,
                "tagged fork recovery": ForkRecovery(tags=["repair"]).recover(failure, session=session).value.agent,
            }
            keyless = Session.resume(store, session.id).agent
            runtime_config = store.get(head).run_state.runtime_config
            saved = stored_text(root)

        # The run itself went straight to DeepSeek with K_u.
        [sent] = router.requests
        self.assertTrue(sent["url"].startswith("https://api.deepseek.com/"))
        self.assertEqual(header(sent, "authorization"), f"Bearer {K_UNPROVEN}")
        for name, restored in rematched.items():
            with self.subTest(path=name):
                self.assertIs(restored.runner_config.model_mode, TextModelMode.DIRECT)
                self.assertEqual(key_view(restored.runner_config.api_keys), key_view(record))
        for name, restored in live.items():
            with self.subTest(path=name):
                self.assertIs(restored.runner_config.model_mode, TextModelMode.DIRECT)
                self.assertEqual(restored.runner_config.api_keys, record)
        # EC-32: without keys passed in, a restored agent holds none; checkpoints never stored them.
        self.assertEqual(tuple(keyless.runner_config.api_keys.keys), ())
        self.assertIsNone(keyless.runner_config.api_keys.vidbyte_api_key)
        self.assertIs(keyless.runner_config.model_mode, TextModelMode.DIRECT)
        self.assertEqual(runtime_config["model_mode"], "direct")
        self.assertEqual(runtime_config["key_providers"], {"primary": ["deepseek"], "others": ["openai"]})
        for secret in (K_UNPROVEN, K_OPENAI, VIDBYTE_KEY):
            self.assertNotIn(secret, saved)


class ForkChildRestoreTests(unittest.TestCase):
    """AC-41, D-30, EC-52, EC-54: a restored fork child is matched against its root's provider names."""

    def test_a_restored_openai_child_rebuilds_its_roots_record_and_accepts_only_its_own_key(self) -> None:
        # AC-41 (first and third cases): matching the root's list against the child's own providers could refuse it (M-6).
        from vidbyte.lib.config import TextModelMode

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            store = FileSessionStore(root)
            parent = deepseek_root(TextModelMode.AUTO)
            child = parent.fork(AgentForkSettings(provider="openai", model_name="gpt-5.5"))
            session = Session(child, store=store)
            session.checkpoint()
            same = Session.resume(store, session.id, api_keys=ROOT_KEYS, vidbyte_api_key=VIDBYTE_KEY).agent
            own_key_only = Session.resume(store, session.id, api_keys=[K_OPENAI], vidbyte_api_key=VIDBYTE_KEY).agent
            runtime_config = store.head(session.id).run_state.runtime_config
            saved = stored_text(root)
        self.assertEqual(key_view(same.runner_config.api_keys), key_view(parent.runner_config.api_keys))
        own = own_key_only.runner_config.api_keys
        self.assertEqual(own.key_for("openai"), K_OPENAI)
        self.assertIsNone(own.key_for("deepseek"))
        self.assertEqual(runtime_config["key_providers"], {"primary": ["deepseek"], "others": ["openai"]})
        for secret in (K_UNPROVEN, K_OPENAI, VIDBYTE_KEY):
            self.assertNotIn(secret, saved)

    def test_a_restored_kimi_child_keeps_the_unproven_key_on_deepseek_and_goes_vidbyte_paid(self) -> None:
        # AC-41 (second case), INV-3: re-matching against the child's own provider would send K_u to Moonshot.
        from vidbyte.lib.config import TextModelMode

        gateway = ScriptedGateway(chat_done("Kimi says hi"))
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=gateway):
            store = FileSessionStore(root)
            parent = Agent(name="desk", system_prompt="Work.", provider="deepseek", model_name="deepseek-chat", api_keys=[K_UNPROVEN], vidbyte_api_key=VIDBYTE_KEY, model_mode=TextModelMode.AUTO)
            child = parent.fork(AgentForkSettings(provider="kimi", model_name="kimi-k2.7-code"))
            session = Session(child, store=store)
            session.checkpoint()
            restored = Session.resume(store, session.id, api_keys=[K_UNPROVEN], vidbyte_api_key=VIDBYTE_KEY).agent
            reply = restored.run("Say hi.")
            saved = stored_text(root)
        self.assertEqual(reply.content, "Kimi says hi")
        record = restored.runner_config.api_keys
        self.assertEqual(record.key_for("deepseek"), K_UNPROVEN)
        self.assertIsNone(record.key_for("kimi"))
        [sent] = gateway.requests
        self.assertEqual((sent["url"], sent["json_body"]["provider"]), (GATEWAY_URL, "kimi"))
        self.assertIsNone(provider_key_header(sent))
        self.assertNotIn(K_UNPROVEN, flat(sent))
        for secret in (K_UNPROVEN, VIDBYTE_KEY):
            self.assertNotIn(secret, saved)


class ExportedStateTests(unittest.TestCase):
    """INV-14, D-30, EC-31, EC-53: what export_state records and how restore reads it."""

    def test_export_records_the_mode_and_the_matched_names_and_no_key(self) -> None:
        # INV-14, INV-4: names only, so a checkpoint can never leak a key.
        from vidbyte.lib.config import TextModelMode

        with patch.dict(os.environ, {}, clear=True):
            state = deepseek_root(TextModelMode.DIRECT).export_state()
        self.assertEqual(state.runtime_config["model_mode"], "direct")
        self.assertEqual(state.runtime_config["key_providers"], {"primary": ["deepseek"], "others": ["openai"]})
        for secret in (K_UNPROVEN, K_OPENAI, VIDBYTE_KEY):
            self.assertNotIn(secret, flat(state))

    def test_a_restored_root_still_needs_its_own_providers_key(self) -> None:
        # D-30: require_primary_key stays on when the restored agent's provider is the first stored primary.
        from vidbyte.lib.config import TextModelMode

        with patch.dict(os.environ, {}, clear=True):
            state = deepseek_root(TextModelMode.AUTO).export_state()
            with self.assertRaises(ConfigurationError) as caught:
                BaseAgent.restore(state, api_keys=[K_OPENAI], vidbyte_api_key=VIDBYTE_KEY)
            restored = BaseAgent.restore(state, api_keys=ROOT_KEYS, vidbyte_api_key=VIDBYTE_KEY)
        message = str(caught.exception)
        self.assertIn("deepseek", message)
        self.assertNotIn(K_OPENAI, message + repr(caught.exception.details))
        self.assertEqual(key_view(restored.runner_config.api_keys)[0], {"deepseek": K_UNPROVEN, "openai": K_OPENAI})

    def test_a_checkpoint_written_before_this_change_restores_auto_and_is_matched_as_a_root(self) -> None:
        # EC-31, EC-53: no model_mode means AUTO; no key_providers means the agent's own provider and stored fallbacks, with INV-24 on.
        from vidbyte.lib.config import TextModelMode

        with patch.dict(os.environ, {}, clear=True):
            exported = deepseek_root(TextModelMode.DIRECT).export_state()
            legacy = replace(exported, runtime_config={name: value for name, value in exported.runtime_config.items() if name not in ("model_mode", "key_providers")})
            restored = BaseAgent.restore(legacy, api_keys=ROOT_KEYS, vidbyte_api_key=VIDBYTE_KEY)
            with self.assertRaises(ConfigurationError) as caught:
                BaseAgent.restore(legacy, api_keys=[K_XAI])
        self.assertIs(restored.runner_config.model_mode, TextModelMode.AUTO)
        self.assertEqual(key_view(restored.runner_config.api_keys)[0], {"deepseek": K_UNPROVEN, "openai": K_OPENAI})
        self.assertIn("deepseek", str(caught.exception))
        self.assertIn("xai", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
