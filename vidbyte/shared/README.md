# Shared

`vidbyte.shared` is a reserved namespace in the Vidbyte SDK. It currently
exports no stable public symbols.

## Role In The SDK

The package exists so future cross-cutting shared code can have an obvious home
without changing the top-level package layout. Today, developers should prefer
root imports from `vidbyte` or the explicit contract layer under `vidbyte.lib`.

## Design Philosophy

An empty namespace is better than an accidental public API. Keeping this package
reserved prevents temporary implementation helpers from becoming compatibility
promises before their boundaries are clear.

## Vidbyte Website

This namespace supports the SDK architecture used to power agents on the
[Vidbyte website](https://vidbyte.pro) by reserving a place for future
cross-cutting shared code. It intentionally does not expose website-specific
internals today.

## Usage

```python
import vidbyte.shared

assert hasattr(vidbyte.shared, "__all__")
```

## Feature Coverage

- Reserved package location for future shared code.
- Empty `__all__` to avoid accidental public exports.
- Clear signal that stable shared contracts currently live in `vidbyte.lib` or root `vidbyte` exports.
- A safe place to document future shared abstractions if they become public.

## Key Modules

- `__init__.py`: currently defines an empty public export list.

## Related Layers

Use [`lib`](../lib/README.md) for current shared contracts and root `vidbyte`
imports for stable SDK entry points.
