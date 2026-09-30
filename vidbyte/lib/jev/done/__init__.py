"""FILE: vidbyte/lib/jev/done/__init__.py

PURPOSE: Exposes JevDoneRegistry and every fixed done question dataclass from the canonical done question folder.
ROLE IN CODEBASE: JevRuntimeSettings and JevRunState (vidbyte/agents/jev/done/) import JevDoneRegistry from here; tests import the question dataclasses to pin their contract.
ARCHITECTURE NOTE: This folder is the one home for fixed done questions and their registry; the check vocabulary lives in vidbyte/lib/enums/jev.py, records and structured-reply payloads in vidbyte/lib/dataclasses/jev.py, and the logic that asks and acts on the questions in vidbyte/agents/jev/done/.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before writing or changing any question (see README.md in this folder), then export each new check's question module here beside multi_part.
KNOWN EDGE CASES: Importing this package builds the question registry but never resolves credentials or constructs a decision runner.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from vidbyte.lib.jev.done.claims import ClaimsSupportedQuestion
from vidbyte.lib.jev.done.done import JevDoneRegistry
from vidbyte.lib.jev.done.multi_part import DONE_STATE, MultiPartDeliveredQuestion

__all__ = ["ClaimsSupportedQuestion", "DONE_STATE", "JevDoneRegistry", "MultiPartDeliveredQuestion"]
