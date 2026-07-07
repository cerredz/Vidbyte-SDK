# Actor Runtime Internals

## Folder Intent

This folder implements the actor-model runtime: actor messages, inboxes, reactive actor loops, and brokers for point-to-point or broadcast topologies.

## Non-Goals

Do not add general BaseAgent behavior here; actor runtime code should stay focused on actor lifecycle, routing, and termination.

## File Index

- `__init__.py`: Initializer for the Actor subpackage, exporting brokers and actors. Exposes the redesigned Point-to-Point and Broadcast Actor Runtimes, Prebuilt Actor Personas, and ActorMessage schema as public interfaces. Key symbols: ActorMessage, ActorInbox, AgentActor, PrebuiltActorFactory, BaseActorRuntime, PointToPointActorRuntime.
- `actor.py`: Defines the AgentActor, PrebuiltActor hierarchy, and 15 prebuilt actor classes. Enables concurrent multi-agent executions by resolving and encapsulating actor loops, local memory queues, and specialized LLM prompt channels. Key symbols: AgentActor, PrebuiltActorFactory, PrebuiltActor, PlannerActor, ReviewerActor, GeneratorActor.
- `broker.py`: Implements Point-to-Point and Broadcast multi-agent brokers. Orchestrates actor loops, concurrent task lifecycles, structured message passing, and fail-fast termination gates in multi-agent executions. Key symbols: BaseActorRuntime, PointToPointActorRuntime, BroadcastActorRuntime.
- `inbox.py`: Implements a thread-safe asynchronous message queue for individual agent actors. Provides decoupled communication in concurrent agent actor systems, serving as the primary polling/waiting state for active worker tasks. Key symbols: ActorInbox.
- `message.py`: Defines the structured ActorMessage class for message passing between concurrent actors. Enables reliable context, state, and conversation propagation across concurrent actors in both Point-to-Point and Broadcast topologies. Key symbols: ActorMessage.

## Subfolder Routing

- No source subfolders.

## Logs

- 2026-07-07: Broker cleanup and termination behavior are load-bearing because leaked actor tasks can outlive a run.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
