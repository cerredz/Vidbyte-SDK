# Contributor Skills

The top-level `skills/` directory contains contributor-facing instructions for
agents working on this repository. These files are not packaged in the
`vidbyte-sdk` wheel.

Distributable skills for downstream developers live inside the `vidbyte` package
tree instead. For example, context-minimal fanout skills ship from
`vidbyte/paradigms/context_minimal_fanout/skills/` and are exposed through the
`vidbyte.skills` registry.
