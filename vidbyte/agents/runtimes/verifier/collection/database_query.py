"""Context Protocol Header

Description:
    Defines DatabaseQueryVerifier.
Purpose:
    Runs one parameterized read query through a caller-supplied connection
    and gates on its result rows. The first concrete
    VerifierKind.QUERY_EXECUTION implementation this SDK ships.
Architecture note:
    - DatabaseQueryVerifier: Verifier subclass taking (params, config); opens
      a connection via config.connection_factory, executes config.query with
      config.query_params bound (never string-interpolated), and evaluates
      every configured gate independently against the returned rows.
Relations:
    Consumes vidbyte.lib.dataclasses.verifier.DatabaseQueryVerifierConfig,
    DBAPIConnection, DBAPICursor, UNSET. Consumed by
    vidbyte.agents.runtimes.verifier.collection.VerifierCollection.
Similar Files:
    - vidbyte/lib/providers/sqlite.py: the nearest existing "DB-API cursor,
      parameter-bound execute()" pattern in this repo — session storage, not
      verification, but the same parameter-binding discipline applies here.
Role in codebase:
    Provides the built-in DB-API query verifier implementation.
Common modification patterns:
    Add gates through DatabaseQueryVerifierConfig without interpolating SQL.
Known edge cases:
    Cursor rows may be sqlite3.Row objects or ordinary sequences.
Related docs:
    docs/design/verifier-runtime-builtin-verifiers.md
Tests:
    Covered by database query verifier tests.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from vidbyte.agents.runtimes.verifier.verifier import Verifier
from vidbyte.lib.dataclasses.verifier import UNSET, DatabaseQueryVerifierConfig, VerifierKind, VerifierParams, VerifierTarget, VerifierVerdict
from vidbyte.lib.errors import ConfigurationError


class DatabaseQueryVerifier(Verifier):
    """Runs one read query and gates on row-count and/or value assertions against the result."""

    def __init__(self, params: VerifierParams, config: DatabaseQueryVerifierConfig) -> None:
        # Validates the verifier is declared as QUERY_EXECUTION before storing its query-specific config.
        super().__init__(params)
        self._validate_kind()
        self._config = config

    def _validate_kind(self) -> None:
        # A misdeclared kind would report inaccurately to VerifierCollectionParams and downstream feedback.
        if self.params.kind is not VerifierKind.QUERY_EXECUTION:
            raise ConfigurationError(f"DatabaseQueryVerifier requires kind=VerifierKind.QUERY_EXECUTION, got {self.params.kind!r}.")

    async def check(self, target: VerifierTarget) -> VerifierVerdict:
        """Executes the configured query and evaluates every configured gate against its result rows."""
        del target
        started = time.monotonic()
        rows = await asyncio.to_thread(self._execute)
        failures = self._evaluate_gates(rows)
        return self._to_verdict(rows, failures, duration_seconds=time.monotonic() - started)

    def _execute(self) -> tuple[Any, ...]:
        # Opens a connection via the injected factory and always closes it, even when execute() raises.
        conn = self._config.connection_factory()
        try:
            cursor = conn.cursor()
            cursor.execute(self._config.query, self._config.query_params)
            return tuple(cursor.fetchall())
        finally:
            conn.close()

    def _evaluate_gates(self, rows: tuple[Any, ...]) -> list[str]:
        # Runs every configured gate independently and collects a message for each one that failed.
        failures: list[str] = []
        self._check_row_count(rows, failures)
        self._check_expected_value(rows, failures)
        self._check_row_matcher(rows, failures)
        return failures

    def _check_row_count(self, rows: tuple[Any, ...], failures: list[str]) -> None:
        # Applies expected/min/max row-count gates, each independent of the others.
        count = len(rows)
        if self._config.expected_row_count is not None and count != self._config.expected_row_count:
            failures.append(f"expected exactly {self._config.expected_row_count} rows, got {count}")
        if self._config.min_row_count is not None and count < self._config.min_row_count:
            failures.append(f"expected at least {self._config.min_row_count} rows, got {count}")
        if self._config.max_row_count is not None and count > self._config.max_row_count:
            failures.append(f"expected at most {self._config.max_row_count} rows, got {count}")

    def _check_expected_value(self, rows: tuple[Any, ...], failures: list[str]) -> None:
        # Compares the configured column of the first row against expected_value, when configured.
        if self._config.expected_value is UNSET:
            return
        if not rows:
            failures.append("expected_value configured but the query returned no rows")
            return
        actual = self._read_column(rows[0], self._config.expected_column)
        if actual != self._config.expected_value:
            failures.append(f"expected column {self._config.expected_column!r} to equal {self._config.expected_value!r}, got {actual!r}")

    @staticmethod
    def _read_column(row: Any, column: str | int) -> Any:
        # __getitem__ already does the right thing for a str or int key across dict, sqlite3.Row, and tuple rows;
        # getattr would raise on sqlite3.Row, which supports mapping-style access but not attribute access.
        return row[column]

    def _check_row_matcher(self, rows: tuple[Any, ...], failures: list[str]) -> None:
        # Runs the caller-supplied predicate, when configured, over every returned row.
        if self._config.row_matcher is not None and not self._config.row_matcher(rows):
            failures.append("row_matcher predicate returned False")

    def _to_verdict(self, rows: tuple[Any, ...], failures: list[str], *, duration_seconds: float) -> VerifierVerdict:
        # Passes only when every configured gate held; diagnostics list every gate that failed.
        diagnostics = "; ".join(failures) if failures else f"{len(rows)} rows matched every configured gate"
        return VerifierVerdict(
            verifier_name=self.params.name,
            tier=self.params.tier,
            blocking=self.params.blocking,
            passed=not failures,
            score=None,
            diagnostics=diagnostics,
            duration_seconds=duration_seconds,
        )


__all__ = ["DatabaseQueryVerifier"]
