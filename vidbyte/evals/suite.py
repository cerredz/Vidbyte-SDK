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
from typing import Any, Iterator, Mapping, Sequence
from vidbyte.evals.types import EvalCase
from vidbyte.evals.templates import default_template_registry


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
            # @intent tag-string-is-tag-text
            # tuple("billing") would split the tag into characters; a string is read like a CSV tags cell.
            # @intent null-optional-arg-means-default
            # JSON null for tags or metadata (what asdict() writes for unset fields) means "not given".
            raw_tags = c.get("tags")
            if raw_tags is None:
                case_tags: tuple[str, ...] = ()
            elif isinstance(raw_tags, str):
                case_tags = cls._split_tag_text(raw_tags)
            else:
                case_tags = tuple(raw_tags)
            raw_metadata = c.get("metadata")
            metadata = {} if raw_metadata is None else dict(raw_metadata)
            templates = cls._load_templates(c)
            cases_list.append(
                EvalCase(
                    prompt=c["prompt"],
                    expected=c.get("expected"),
                    tags=case_tags,
                    templates=templates,
                    metadata=metadata
                )
            )
        return cls(name=name, cases=cases_list)

    @classmethod
    def from_csv(cls, path: str | Path, *, prompt_col: str = "prompt", expected_col: str = "expected") -> EvalSuite:
        # Asynchronously or synchronously loads an evaluation suite from a flat CSV file.
        # @intent csv-bom-is-not-part-of-the-header
        # Excel's "CSV UTF-8" starts with a byte-order mark; read as part of the first header it hides the prompt column and every prompt becomes "".
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cases_list = []
            for row in reader:
                prompt = row.get(prompt_col, "")
                expected = row.get(expected_col)
                tags_str = row.get("tags", "")
                case_tags = cls._split_tag_text(tags_str) if tags_str else ()
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
        # @intent bare-string-tag-is-one-tag
        # set("billing") would match single letters and select nothing; a bare string is one tag.
        target_tags = {tags} if isinstance(tags, str) else set(tags)
        filtered_cases = [c for c in self.cases if any(t in target_tags for t in c.tags)]
        return EvalSuite(name=f"{self.name}_filtered", cases=filtered_cases)

    @staticmethod
    def _split_tag_text(text: str) -> tuple[str, ...]:
        # Reads comma-separated tag text such as "billing, refunds" into stripped, non-empty tags.
        return tuple(t.strip() for t in text.split(",") if t.strip())

    @classmethod
    def _load_templates(cls, case_data: Mapping[str, Any]) -> tuple[Any, ...]:
        # Resolves JSON template or templates fields into concrete template instances.
        # @intent null-optional-arg-means-default
        # A null template or templates value is treated exactly like the key being omitted.
        has_template = case_data.get("template") is not None
        has_templates = case_data.get("templates") is not None
        if has_template and has_templates:
            raise ValueError("Eval case cannot define both 'template' and 'templates'.")
        if has_template:
            return (default_template_registry.create(case_data["template"]),)
        if not has_templates:
            return ()
        templates_data = case_data["templates"]
        if not isinstance(templates_data, list):
            raise ValueError("Eval case 'templates' must be a list.")
        return tuple(default_template_registry.create(template) for template in templates_data)

    def __len__(self) -> int:
        # Returns the number of evaluation cases contained in this suite.
        return len(self.cases)

    def __iter__(self) -> Iterator[EvalCase]:
        # Iterates over the evaluation cases inside the suite.
        return iter(self.cases)
