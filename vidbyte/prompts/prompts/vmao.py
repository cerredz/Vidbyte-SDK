from __future__ import annotations

from typing import Any


class VMAOPrompts:
    """Prompt templates used by verified multi-agent orchestration."""

    _TEMPLATES = {
        "planner": (
            "You are the planner for verified multi-agent orchestration.\n"
            "Break the task into a minimal JSON array of DAG nodes. Each node must include id, question, depends_on, "
            "and optional preferred_capability. Keep questions independently answerable and avoid cycles.\n\n"
            "Task:\n{prompt}\n\nContext:\n{context}"
        ),
        "planner_repair": (
            "Repair the planner output into valid JSON only. Return a JSON array or an object with a nodes array. "
            "Each node needs id, question, depends_on, and optional preferred_capability.\n\n"
            "Invalid planner output:\n{raw}"
        ),
        "synthesizer": (
            "Synthesize a final answer for the original task using the collected node outputs. "
            "Resolve contradictions explicitly and do not invent missing evidence.\n\nTask:\n{prompt}\n\nEvidence:\n{evidence}"
        ),
        "verifier": (
            "Verify the answer against the task and the available evidence. Return strict JSON with approved, score, gaps, "
            "and rationale. Score must be between 0 and 1.\n\nTask:\n{prompt}\n\nAnswer:\n{output}\n\nContext:\n{context}"
        ),
        "gap_planner": (
            "Create follow-up DAG nodes only for the missing gaps. Preserve the original task and current answer as context. "
            "Return JSON nodes only.\n\nOriginal task:\n{prompt}\n\nCurrent answer:\n{output}\n\nGaps:\n{gaps}"
        ),
    }

    def __init__(self, key: str) -> None:
        if key not in self._TEMPLATES:
            raise ValueError(f"Unknown VMAO prompt key: {key}")
        self.key = key
        self.name = f"vmao.{key}"

    def export(self, **values: Any) -> str:
        return self._TEMPLATES[self.key].format(**{key: values.get(key, "") for key in ("prompt", "context", "raw", "evidence", "output", "gaps")})
