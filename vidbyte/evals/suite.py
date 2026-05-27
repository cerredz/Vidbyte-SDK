"""Context Protocol Header

Description:
    Implements EvalSuite, the primary payload collection for evaluation cases.
Purpose:
    Provides structured loading of evaluation datasets from JSON or CSV configurations and supports
    dynamic tag-based subset filtering.
Architecture:
    - EvalSuite: Wraps list of EvalCase items and provides loading and query interfaces.
Functions:
    - from_json: Loads a structured JSON file mapping keys to suite cases.
    - from_csv: Parses legacy or flat CSV prompt/expected evaluation columns.
    - filter: Selects a subset of cases whose tags intersect with target criteria.
Relations:
    Related to vidbyte.evals.types (EvalCase) and consumed by vidbyte.evals.runner.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterator, Sequence
from vidbyte.evals.types import EvalCase


class EvalSuite:
    """A collection of evaluation cases used to run validation tests against agents or strategies."""

    def __init__(self, name: str, cases: Sequence[EvalCase]) -> None:
        # Initializes the EvalSuite with a descriptive name and a sequence of evaluation cases.
        self.name = name
        self.cases = tuple(cases)

    @classmethod
    def from_json(cls, path: str | Path) -> EvalSuite:
        # Asynchronously or synchronously loads an evaluation suite from a JSON file.
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        name = str(data.get("name", "Loaded JSON Suite"))
        cases_list = []
        for c in data.get("cases", []):
            case_tags = tuple(c.get("tags", []))
            cases_list.append(
                EvalCase(
                    prompt=c["prompt"],
                    expected=c.get("expected"),
                    tags=case_tags,
                    metadata=dict(c.get("metadata", {}))
                )
            )
        return cls(name=name, cases=cases_list)

    @classmethod
    def from_csv(cls, path: str | Path, *, prompt_col: str = "prompt", expected_col: str = "expected") -> EvalSuite:
        # Asynchronously or synchronously loads an evaluation suite from a flat CSV file.
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cases_list = []
            for row in reader:
                prompt = row.get(prompt_col, "")
                expected = row.get(expected_col)
                tags_str = row.get("tags", "")
                case_tags = tuple(t.strip() for t in tags_str.split(",") if t.strip()) if tags_str else ()
                cases_list.append(
                    EvalCase(
                        prompt=prompt,
                        expected=expected,
                        tags=case_tags
                    )
                )
        name = Path(path).stem
        return cls(name=name, cases=cases_list)

    def filter(self, tags: Sequence[str]) -> EvalSuite:
        # Filters and returns a new EvalSuite containing only cases matching any of the specified tags.
        target_tags = set(tags)
        filtered_cases = [c for c in self.cases if any(t in target_tags for t in c.tags)]
        return EvalSuite(name=f"{self.name}_filtered", cases=filtered_cases)

    def __len__(self) -> int:
        # Returns the number of evaluation cases contained in this suite.
        return len(self.cases)

    def __iter__(self) -> Iterator[EvalCase]:
        # Iterates over the evaluation cases inside the suite.
        return iter(self.cases)
