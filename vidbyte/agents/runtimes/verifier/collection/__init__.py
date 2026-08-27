"""Context Protocol Header

Description:
    Public surface of the verifier collection sub-package.
Purpose:
    Re-exports VerifierCollection/VerifierCollectionParams (moved here
    verbatim from the former collection.py) alongside the first three
    concrete, built-in VerifierKind implementations, so every existing
    import of vidbyte.agents.runtimes.verifier.collection keeps resolving
    unchanged.
Architecture:
    - base: VerifierCollection, VerifierCollectionParams (tiered execution
      engine; not modified by this package split).
    - test_suite / database_query / lean_proof: one concrete Verifier
      subclass each, following the CallableVerifier(params, config) shape.
Relations:
    Re-exported by vidbyte.agents.runtimes.verifier.
Similar Files:
    - vidbyte/agents/runtimes/verifier/verifier.py: CallableVerifier, the
      generic Verifier subclass these concrete kinds follow the shape of.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.verifier.collection.base import VerifierCollection, VerifierCollectionParams
from vidbyte.agents.runtimes.verifier.collection.database_query import DatabaseQueryVerifier
from vidbyte.agents.runtimes.verifier.collection.lean_proof import LeanProofVerifier
from vidbyte.agents.runtimes.verifier.collection.test_suite import TestSuiteVerifier

__all__ = [
    "DatabaseQueryVerifier",
    "LeanProofVerifier",
    "TestSuiteVerifier",
    "VerifierCollection",
    "VerifierCollectionParams",
]
