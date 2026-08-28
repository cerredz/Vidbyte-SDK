"""Context Protocol Header

Description:
    Defines the AgentActor, PrebuiltActor hierarchy, and 15 prebuilt actor classes.
Purpose:
    Enables concurrent multi-agent executions by resolving and encapsulating
    actor loops, local memory queues, and specialized LLM prompt channels.
Architecture:
    - AgentActor: Base concurrent reactive queue listener.
    - PrebuiltActor: Specialized subclass loading system prompts from catalog.
    - 15 specialized personas subclassing PrebuiltActor.
Relations:
    Located in vidbyte/agents/runtimes/actor/actor.py. Consumed by BaseActorRuntime.
Similar Files:
    - vidbyte/agents/runtimes/configs.py: Configuration classes.
    - vidbyte/lib/registries/actors.py: Prebuilt actor class registry.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from vidbyte.agents.runtimes.actor.inbox import ActorInbox
from vidbyte.agents.runtimes.actor.message import ActorMessage
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.broker import BaseActorRuntime

# Prebuilt actor roles mapped to their Prompt enum keys.
PREBUILT_ACTOR_PROMPTS = {
    "planner": Prompt.ACTOR_RUNTIME_PLANNER,
    "reviewer": Prompt.ACTOR_RUNTIME_REVIEWER,
    "generator": Prompt.ACTOR_RUNTIME_GENERATOR,
    "critic": Prompt.ACTOR_RUNTIME_CRITIC,
    "reasoner": Prompt.ACTOR_RUNTIME_REASONER,
    "summarization": Prompt.ACTOR_RUNTIME_SUMMARIZATION,
    "decomposer": Prompt.ACTOR_RUNTIME_DECOMPOSER,
    "explorer": Prompt.ACTOR_RUNTIME_EXPLORER,
    "tradeoff": Prompt.ACTOR_RUNTIME_TRADEOFF,
    "hypothesis_generator": Prompt.ACTOR_RUNTIME_HYPOTHESIS_GENERATOR,
    "refiner": Prompt.ACTOR_RUNTIME_REFINER,
    "safety": Prompt.ACTOR_RUNTIME_SAFETY,
    "final_answer": Prompt.ACTOR_RUNTIME_FINAL_ANSWER,
}


class AgentActor:
    """Represents an isolated agent actor executing in a concurrent background loop."""

    def __init__(
        self,
        actor_id: str,
        system_prompt: str,
        broker: BaseActorRuntime,
        model_name: str | None = None,
    ) -> None:
        self.actor_id = actor_id
        self.system_prompt = system_prompt
        self.broker = broker
        self.model_name = model_name
        self.inbox = ActorInbox()
        self.state: dict[str, Any] = {}
        self.history: list[ActorMessage] = []

    async def start(self) -> None:
        """Starts the infinite reactive loop, dequeuing and processing inbox messages."""
        try:
            while True:
                msg = await self.inbox.get()
                self.history.append(msg)
                response = await self.on_receive(msg)
                if response:
                    # Send response back to the sender
                    await self.broker.send(
                        sender=self.actor_id,
                        recipient=msg.sender,
                        content=response,
                        parent_task_id=msg.parent_task_id,
                    )
        except asyncio.CancelledError:
            pass  # Task was cleanly stopped

    async def on_receive(self, message: ActorMessage) -> str | None:
        """Invoked when a new message is received. Formulates a prompt and invokes completion."""
        # Check for task completion signals or exit signals to prevent infinite execution.
        if "terminate_task" in message.state or message.content.strip().lower() == "exit":
            return None

        prompt = self.compile_prompt(message)
        # Execute the LLM completion using the broker's configured runner.
        return await self.broker.invoke_actor_completion(self, prompt)

    def compile_prompt(self, message: ActorMessage) -> str:
        """Assembles a local context prompt containing history, role, and the new message."""
        lines = [
            "You are operating inside an asynchronous actor model runtime.",
            f"Your Actor ID is: {self.actor_id}",
            f"Your Role System Instructions: {self.system_prompt}",
            "",
            "<conversation_history>"
        ]
        # Format the historical interactions for context containment.
        for msg in self.history[:-1]:
            lines.append(f"[{msg.sender} -> {msg.recipient}]: {msg.content}")
        lines.append("</conversation_history>")
        lines.append("")
        lines.append(f"New incoming message from [{message.sender}]:")
        lines.append(message.content)
        return "\n".join(lines)


class PrebuiltActorFactory:
    """Factory providing standardized, catalog-loaded prompts for actor personas."""

    @staticmethod
    def load_persona(role: str) -> str:
        """Loads a prebuilt actor persona system prompt from the Prompts catalog."""
        normalized_role = role.strip().lower()
        if normalized_role not in PREBUILT_ACTOR_PROMPTS:
            raise ValueError(f"Unknown prebuilt actor role: {role}. Supported roles: {list(PREBUILT_ACTOR_PROMPTS.keys())}")
        
        prompts_catalog = Prompts()
        return prompts_catalog.get(PREBUILT_ACTOR_PROMPTS[normalized_role])


class PrebuiltActor(AgentActor):
    """Base class for all prebuilt actors resolving their prompts automatically."""
    role_name: str
    system_prompt_key: Prompt

    def __init__(
        self,
        broker: BaseActorRuntime,
        model_name: str | None = None,
    ) -> None:
        # Load persona system prompt and call parent constructor
        prompt = PrebuiltActorFactory.load_persona(self.role_name)
        super().__init__(
            actor_id=self.role_name,
            system_prompt=prompt,
            broker=broker,
            model_name=model_name,
        )


class PlannerActor(PrebuiltActor):
    """Specialized Planner actor."""
    role_name = "planner"
    system_prompt_key = Prompt.ACTOR_RUNTIME_PLANNER


class ReviewerActor(PrebuiltActor):
    """Specialized Reviewer actor."""
    role_name = "reviewer"
    system_prompt_key = Prompt.ACTOR_RUNTIME_REVIEWER


class GeneratorActor(PrebuiltActor):
    """Specialized Generator actor."""
    role_name = "generator"
    system_prompt_key = Prompt.ACTOR_RUNTIME_GENERATOR


class CriticActor(PrebuiltActor):
    """Specialized Critic actor."""
    role_name = "critic"
    system_prompt_key = Prompt.ACTOR_RUNTIME_CRITIC


class ReasonerActor(PrebuiltActor):
    """Specialized Reasoner actor."""
    role_name = "reasoner"
    system_prompt_key = Prompt.ACTOR_RUNTIME_REASONER


class SummarizationActor(PrebuiltActor):
    """Specialized Summarization actor."""
    role_name = "summarization"
    system_prompt_key = Prompt.ACTOR_RUNTIME_SUMMARIZATION


class DecomposerActor(PrebuiltActor):
    """Specialized Decomposer actor."""
    role_name = "decomposer"
    system_prompt_key = Prompt.ACTOR_RUNTIME_DECOMPOSER


class ExplorerActor(PrebuiltActor):
    """Specialized Explorer actor."""
    role_name = "explorer"
    system_prompt_key = Prompt.ACTOR_RUNTIME_EXPLORER


class TradeoffActor(PrebuiltActor):
    """Specialized Tradeoff actor."""
    role_name = "tradeoff"
    system_prompt_key = Prompt.ACTOR_RUNTIME_TRADEOFF


class HypothesisGeneratorActor(PrebuiltActor):
    """Specialized Hypothesis Generator actor."""
    role_name = "hypothesis_generator"
    system_prompt_key = Prompt.ACTOR_RUNTIME_HYPOTHESIS_GENERATOR


class RefinerActor(PrebuiltActor):
    """Specialized Refiner actor."""
    role_name = "refiner"
    system_prompt_key = Prompt.ACTOR_RUNTIME_REFINER


class SafetyActor(PrebuiltActor):
    """Specialized Safety actor."""
    role_name = "safety"
    system_prompt_key = Prompt.ACTOR_RUNTIME_SAFETY


class FinalAnswerActor(PrebuiltActor):
    """Specialized Final Answer actor."""
    role_name = "final_answer"
    system_prompt_key = Prompt.ACTOR_RUNTIME_FINAL_ANSWER


# Auto-register all prebuilt actor classes in the actors registry
from vidbyte.lib.registries.actors import actor_registry

for actor_cls in [
    PlannerActor,
    ReviewerActor,
    GeneratorActor,
    CriticActor,
    ReasonerActor,
    SummarizationActor,
    DecomposerActor,
    ExplorerActor,
    TradeoffActor,
    HypothesisGeneratorActor,
    RefinerActor,
    SafetyActor,
    FinalAnswerActor,
]:
    actor_registry.register(actor_cls.role_name, actor_cls)
