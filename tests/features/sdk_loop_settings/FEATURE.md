# Feature: Safe agent loop settings

## High-Level Feature Description

SDK callers configure iteration, tool-call, context, and timeout limits before running an agent. Invalid types or non-finite values must fail immediately so a budget never silently becomes unenforceable.

## Contract

Optional loop count limits are positive integers (never booleans); retry counts may also be zero where supported. Loop and tool-call timeouts are finite positive numbers, and retry backoff is finite with its documented minimum. Invalid input raises an SDK `ConfigurationError` naming the field. Valid settings preserve their exact values in the runtime configuration.

## Actors / Callers

Python SDK users, YAML configuration parsing, BaseAgent, and JevAgentSettings.

## Inputs and Preconditions

An `AgentLoopSettings` object with optional limit fields; no credentials or network are required.

## Observable Outcomes

A valid instance exposes a runtime config with the requested limits; invalid inputs raise `ConfigurationError` during construction, not during a model/tool call.

## State Transitions

The settings object must not be constructed with an invalid budget; valid input converts without coercion.

## Invariants

True is not an integer budget; fractional and string values are not integer budgets; NaN and infinities are not finite timeouts.

## External Dependencies

None: the tests run offline without model runners or provider credentials.

## Known Failure Modes

Python's `bool` is an `int`; positive floats compare greater than zero; strings raise a raw TypeError when compared with an integer; NaN bypasses ordered comparisons.

## Historical Regressions

The first bug-hunt pass found the above four failure mechanisms in the public constructor.

## Test Suite Map

`test_contract.py` covers every integer field, valid conversion, malformed types, loop and tool-call timeout boundaries, and nested tool retry settings. Run with `python -m pytest -q tests/features/sdk_loop_settings`.

## Omitted Testing Strategies

Network, browser, concurrency, and performance tests are unnecessary for this synchronous validation boundary. Existing `tests/test_agent_settings_validation.py` covers the YAML parser and nested settings independently.
