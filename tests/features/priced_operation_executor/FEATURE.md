# Feature: Priced operation executor delegation

## High-Level Feature Description
Priced operation tools let applications supply real provider I/O without
subclassing SDK search and fetch tools. The SDK remains the owner of tool
schemas and operation-usage metadata while the application remains the owner
of credentials, HTTP clients, and provider response mapping.

## Contract
Every priced operation tool may receive one asynchronous executor. The executor
receives the validated `ToolCall` and returns a `ToolResult`. The SDK preserves
safe executor metadata, normalizes the result tool name, and overwrites any
caller-supplied `operation_usage` value with the tool's authoritative operation,
provider, mode, and units.

Executor failures become safe error results without including the exception
message, and they still carry operation metadata so attempted provider calls can
be priced. Tools constructed without an executor retain their deterministic
contract-result behavior.

## Actors / Callers
SDK applications attach provider adapters to built-in operation tools. The agent
runtime executes those tools and sends their metadata to `UsageTracker`.

## Inputs and Preconditions
The executor is an async callable accepting `ToolCall` and returning
`ToolResult`. Tool-call validation still occurs in the standard `ToolExecutor`
before delegation.

## Observable Outcomes
The provider result reaches the model, safe metadata survives, authoritative
operation usage is present, and callback exceptions return a redacted error.

## State Transitions
Priced tools are stateless. Each invocation delegates independently and cannot
retain provider response state between calls.

## Invariants
- Applications cannot spoof operation pricing identity through result metadata.
- Callback exception messages never enter the model-visible result.
- Failed provider attempts remain visible to operation usage tracking.
- Omitting an executor preserves backward-compatible placeholder behavior.

## External Dependencies
None. Tests use in-memory async executors and do not call providers.

## Known Failure Modes
An executor can raise, return an error result, supply a different tool name, or
attempt to spoof usage metadata. Each case must remain deterministic and safe.

## Historical Regressions
PR `cerredz/Vidbyte#284` found that the built-in operation tools exposed pricing
contracts but no application execution seam, forcing a local subclass.

## Test Suite Map
- `test_contract.py` protects delegation, metadata authority, error handling,
  fetch-unit accounting, and backward compatibility.

## Omitted Testing Strategies
- Network integration is omitted because provider I/O belongs to applications.
- Browser and accessibility testing are omitted because this is an SDK runtime contract.
- Load testing is omitted because the feature performs one constant-size metadata merge.
