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

## Usage

```python
import vidbyte.shared

assert hasattr(vidbyte.shared, "__all__")
```

## Key Modules

- `__init__.py`: currently defines an empty public export list.

## Related Layers

Use [`lib`](../lib/README.md) for current shared contracts and root `vidbyte`
imports for stable SDK entry points.
