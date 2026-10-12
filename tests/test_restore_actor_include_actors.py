"""FILE: tests/test_restore_actor_include_actors.py

PURPOSE:
    Regression tests proving export_state()/restore() keep an ActorRuntime's
    include_actors instead of widening a restored agent to every default actor.
ROLE IN CODEBASE:
    Covers BaseAgent._export_runtime_config and BaseAgent._restore_runtime for
    the actor topologies, plus the older-checkpoint fallback.
ARCHITECTURE NOTE:
    Builds agents offline and never runs them, so no provider network call is made.
COMMON MODIFICATION PATTERNS:
    Add a case here when another ActorRuntime setting joins the checkpoint.
KNOWN EDGE CASES:
    An actor class missing from the actor registry cannot be named in a
    checkpoint, so it is left out of the exported list.
RELATED DOCS:
    vidbyte/lib/registries/actors.py (the role-name registry used for the round trip)
TESTS:
    python -m pytest -q tests/test_restore_actor_include_actors.py
"""

from __future__ import annotations

import unittest

from vidbyte import Agent
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.runtimes.actor.actor import CriticActor, PlannerActor, PrebuiltActor
from vidbyte.agents.runtimes.configs import ActorRuntime
from vidbyte.lib.enums import AgentRuntimeType


class _UnregisteredActor(PrebuiltActor):
    role_name = "unregistered_test_actor"


def _actor_agent(include_actors: object) -> Agent:
    runtime = ActorRuntime(topology=AgentRuntimeType.ACTOR_MODEL_BROADCAST, include_actors=include_actors)
    return Agent(name="root", system_prompt="You coordinate.", provider="openai", model_name="gpt-4.1", runtime=runtime)


class RestoreActorIncludeActorsTests(unittest.TestCase):
    def test_include_actors_survives_export_and_restore(self) -> None:  # [Silent Failure]
        for include in ([], [CriticActor], [PlannerActor, CriticActor]):
            with self.subTest(include=[actor.role_name for actor in include]):
                restored = BaseAgent.restore(_actor_agent(include).export_state())

                self.assertIsInstance(restored.runtime_config_obj, ActorRuntime)
                self.assertEqual(restored.runtime_config_obj.include_actors, include)

    def test_default_actor_set_stays_default(self) -> None:  # [Hidden Assumption]
        state = _actor_agent(None).export_state()

        self.assertNotIn("include_actors", state.runtime_config)
        self.assertIsNone(BaseAgent.restore(state).runtime_config_obj.include_actors)

    def test_unregistered_actor_is_left_out_of_the_checkpoint(self) -> None:  # [Hidden Assumption]
        state = _actor_agent([CriticActor, _UnregisteredActor]).export_state()

        self.assertEqual(state.runtime_config["include_actors"], ["critic"])
        self.assertEqual(BaseAgent.restore(state).runtime_config_obj.include_actors, [CriticActor])


if __name__ == "__main__":
    unittest.main()
