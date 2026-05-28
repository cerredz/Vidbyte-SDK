"""Context Protocol Header

Description:
    Defines the AgentActor class and prebuilt persona catalog for asynchronous actors.
Purpose:
    Encapsulates concurrent reactive loops, local memory channels, state dicts, and
    compiled prompt assembly pipelines for specialized LLM agents.
Architecture:
    - AgentActor: Base actor class running a background polling loop over its ActorInbox.
    - Prebuilt Personas: Planner, Coder, Reviewer, Generator, Critic, and Reasoner
      dynamically loaded from the SDK Prompts catalog.
Relations:
    Located under vidbyte/agents/runtimes/actor/actor.py. Consumed by BaseActorRuntime.
Similar Files:
    - vidbyte/agents/runtimes/actor/broker.py: The message brokers managing actors.
"""

from __future__ import annotations
import asyncio
from typing import Any, TYPE_CHECKING
from vidbyte.agents.runtimes.actor.inbox import ActorInbox
from vidbyte.agents.runtimes.actor.message import ActorMessage
from vidbyte.prompts.catalog import Prompts
from vidbyte.lib.enums.prompts import Prompt

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.broker import BaseActorRuntime

# Prebuilt actor roles mapped to their Prompt enum keys.
PREBUILT_ACTOR_PROMPTS = {
    "planner": Prompt.ACTOR_RUNTIME_PLANNER,
    "coder": Prompt.ACTOR_RUNTIME_CODER,
    "reviewer": Prompt.ACTOR_RUNTIME_REVIEWER,
    "generator": Prompt.ACTOR_RUNTIME_GENERATOR,
    "critic": Prompt.ACTOR_RUNTIME_CRITIC,
    "reasoner": Prompt.ACTOR_RUNTIME_REASONER,
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
