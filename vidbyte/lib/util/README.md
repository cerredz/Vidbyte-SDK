# Shared utility classes

Domain-independent helpers used by SDK features. Feature behavior remains in its
owning package; these utilities have no dependency on agents or provider clients.

## File Index

- `__init__.py`: Shared utility exports.
- `concurrency.py`: AsyncCapacityLimiter owns bounded asynchronous admission.
- `math.py`: MathHelper provides shared statistics and interval arithmetic.

Create `limiter = AsyncCapacityLimiter(1)` and use `async with limiter` around
operations that must run alone. Keep that instance for their shared lifetime.
Cancelled waiters do not consume permits; admitted operations release them on exit.
