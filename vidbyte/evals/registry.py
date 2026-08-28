"""Context Protocol Header

Description:
    Implements EvalRegistry and ComparisonReport for persisting and comparing results.
Purpose:
    Exposes a zero-configuration SQLite backend to save evaluation suites, query histories,
    and generate pass-rate or score delta reports across distinct model revisions.
Architecture:
    - ComparisonReport: Typed data container outlining deltas, improvements, and regressions.
    - EvalRegistry: Handles SQLite table initialization, insertions, queries, and metric comparison logic.
Functions:
    - record: Inserts a complete suite run and nested case outputs inside a transaction.
    - latest: Reconstructs the latest run results matching a suite and model.
    - history: Fetches a history list of historical suite runs.
    - compare: Generates a comparison report detailing performance improvements and regressions.
Relations:
    Related to vidbyte.evals.types (consumes and reconstructs these data objects).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from vidbyte.evals.types import EvalCase, EvalResult, EvalSuiteResult, GraderResult


class EvalExpectedSerializer:
    """Serializer for preserving structured expected values in SQLite TEXT fields."""

    prefix = "__vidbyte_json__:"

    def dumps(self, expected: Any | None) -> str | None:
        # Serializes expected values while preserving plain string compatibility.
        if expected is None or isinstance(expected, str):
            return expected
        try:
            return self.prefix + json.dumps(expected, sort_keys=True, separators=(",", ":"))
        except TypeError as exc:
            raise TypeError(f"Eval expected value is not JSON serializable: {exc}") from exc

    def loads(self, raw: str | None) -> Any | None:
        # Restores structured expected values when a registry sentinel is present.
        if raw is None or not raw.startswith(self.prefix):
            return raw
        payload = raw[len(self.prefix):]
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return raw


@dataclass(frozen=True)
class ComparisonReport:
    """Carries the comparative statistics and detailed prompt changes between two evaluated models."""

    suite_name: str
    model_a: str
    model_b: str
    pass_rate_a: float
    pass_rate_b: float
    pass_rate_delta: float
    mean_score_a: float
    mean_score_b: float
    mean_score_delta: float
    improved_cases: tuple[str, ...]
    regressed_cases: tuple[str, ...]


class EvalRegistry:
    """Manages the SQLite database where all evaluation results are persisted, queried, and compared."""

    def __init__(self, db_path: str | Path = ".vidbyte_evals.db") -> None:
        # Connects to the local SQLite database and initializes results tables if they do not exist.
        self.db_path = str(db_path)
        self._expected_serializer = EvalExpectedSerializer()
        self._init_db()

    def _init_db(self) -> None:
        # Performs the default table creations inside a single SQLite transaction.
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS eval_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        suite_name TEXT NOT NULL,
                        model TEXT NOT NULL,
                        pass_rate REAL NOT NULL,
                        mean_score REAL NOT NULL,
                        p95_latency_ms REAL NOT NULL,
                        measured_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS eval_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER NOT NULL,
                        prompt TEXT NOT NULL,
                        expected TEXT,
                        actual TEXT NOT NULL,
                        score REAL NOT NULL,
                        passed INTEGER NOT NULL,
                        reason TEXT,
                        latency_ms REAL NOT NULL,
                        error TEXT,
                        FOREIGN KEY(run_id) REFERENCES eval_runs(id) ON DELETE CASCADE
                    )
                """)
        finally:
            conn.close()

    def record(self, result: EvalSuiteResult) -> None:
        # Records the full suite execution details and all case-by-case outputs in SQLite.
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO eval_runs (suite_name, model, pass_rate, mean_score, p95_latency_ms, measured_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        result.suite_name,
                        result.model,
                        result.pass_rate,
                        result.mean_score,
                        result.p95_latency_ms,
                        result.measured_at.isoformat()
                    )
                )
                run_id = cursor.lastrowid
                
                for r in result.results:
                    cursor.execute(
                        "INSERT INTO eval_results (run_id, prompt, expected, actual, score, passed, reason, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            run_id,
                            r.case.prompt,
                            self._expected_serializer.dumps(r.case.expected),
                            r.actual,
                            r.grader_result.score,
                            1 if r.grader_result.passed else 0,
                            r.grader_result.reason,
                            r.latency_ms,
                            r.error
                        )
                    )
        finally:
            conn.close()

    def latest(self, suite: str, model: str) -> EvalSuiteResult | None:
        # Retrieves the most recent recorded evaluation run for a specified suite name and model.
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM eval_runs WHERE suite_name = ? AND model = ? ORDER BY id DESC LIMIT 1",
                (suite, model)
            )
            run_row = cursor.fetchone()
            if not run_row:
                return None

            cursor.execute("SELECT * FROM eval_results WHERE run_id = ?", (run_row["id"],))
            results = []
            for row in cursor.fetchall():
                case = EvalCase(prompt=row["prompt"], expected=self._expected_serializer.loads(row["expected"]))
                grader_result = GraderResult(
                    score=row["score"],
                    passed=bool(row["passed"]),
                    reason=row["reason"] or ""
                )
                results.append(
                    EvalResult(
                        case=case,
                        actual=row["actual"],
                        grader_result=grader_result,
                        latency_ms=row["latency_ms"],
                        error=row["error"]
                    )
                )
            
            measured_at = datetime.fromisoformat(run_row["measured_at"])
            return EvalSuiteResult(
                suite_name=run_row["suite_name"],
                model=run_row["model"],
                results=tuple(results),
                measured_at=measured_at
            )
        finally:
            conn.close()

    def history(self, suite: str, model: str, limit: int = 10) -> list[EvalSuiteResult]:
        # Returns the last N recorded suite results matching the target query parameters.
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM eval_runs WHERE suite_name = ? AND model = ? ORDER BY id DESC LIMIT ?",
                (suite, model, limit)
            )
            runs = []
            for run_row in cursor.fetchall():
                cursor.execute("SELECT * FROM eval_results WHERE run_id = ?", (run_row["id"],))
                results = []
                for row in cursor.fetchall():
                    case = EvalCase(prompt=row["prompt"], expected=self._expected_serializer.loads(row["expected"]))
                    grader_result = GraderResult(
                        score=row["score"],
                        passed=bool(row["passed"]),
                        reason=row["reason"] or ""
                    )
                    results.append(
                        EvalResult(
                            case=case,
                            actual=row["actual"],
                            grader_result=grader_result,
                            latency_ms=row["latency_ms"],
                            error=row["error"]
                        )
                    )
                measured_at = datetime.fromisoformat(run_row["measured_at"])
                runs.append(
                    EvalSuiteResult(
                        suite_name=run_row["suite_name"],
                        model=run_row["model"],
                        results=tuple(results),
                        measured_at=measured_at
                    )
                )
            return runs
        finally:
            conn.close()

    def compare(self, suite: str, model_a: str, model_b: str) -> ComparisonReport:
        # Generates a metrics comparison and logs case delta improvements and regressions.
        run_a = self.latest(suite, model_a)
        run_b = self.latest(suite, model_b)

        if not run_a:
            raise ValueError(f"No run history found for Model A ({model_a}) on suite '{suite}'.")
        if not run_b:
            raise ValueError(f"No run history found for Model B ({model_b}) on suite '{suite}'.")

        map_a = {r.case.prompt: r for r in run_a.results}
        map_b = {r.case.prompt: r for r in run_b.results}

        improved = []
        regressed = []

        for prompt, res_b in map_b.items():
            if prompt in map_a:
                res_a = map_a[prompt]
                if res_b.grader_result.passed and not res_a.grader_result.passed:
                    improved.append(prompt)
                elif not res_b.grader_result.passed and res_a.grader_result.passed:
                    regressed.append(prompt)

        return ComparisonReport(
            suite_name=suite,
            model_a=model_a,
            model_b=model_b,
            pass_rate_a=run_a.pass_rate,
            pass_rate_b=run_b.pass_rate,
            pass_rate_delta=run_b.pass_rate - run_a.pass_rate,
            mean_score_a=run_a.mean_score,
            mean_score_b=run_b.mean_score,
            mean_score_delta=run_b.mean_score - run_a.mean_score,
            improved_cases=tuple(improved),
            regressed_cases=tuple(regressed)
        )
