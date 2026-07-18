# Multi-agent test pack

This folder verifies the ledger-driven `MultiAgent` protocol after its class-based
runtime decomposition.

| File | Responsibility |
| --- | --- |
| `test_behavior.py` | End-to-end dispatch ordering, ledger containment, context rendering, and terminal results. |
| `test_structure.py` | Review constraints for class ownership, module size, shared types, and lifecycle shape. |

The fakes are provider-free `BaseAgent` subclasses and orchestration-protocol
implementations. They exercise public/runtime boundaries without network access.
