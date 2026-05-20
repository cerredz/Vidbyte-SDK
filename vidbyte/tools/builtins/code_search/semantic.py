"""Context Protocol Header

Description:
    Implements bounded semantic-style search over an in-memory code chunk index.
Purpose:
    Supports natural-language lookup through an injectable embedding provider
    while retaining a dependency-free token-overlap fallback.
Architecture:
    - EmbeddingProvider: Protocol for optional vector embeddings.
    - SemanticSearchTool: Builds/ranks code chunks and returns top matches.
Relations:
    Related to vidbyte.tools.builtins.code_search.base and grep.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from vidbyte.tools.builtins.code_search.base import BaseCodeSearchTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class EmbeddingProvider(Protocol):
    """Protocol for optional embedding providers."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector for each input text."""


@dataclass(frozen=True, slots=True)
class _CodeChunk:
    """Internal representation of an indexed code chunk."""

    path: str
    start_line: int
    end_line: int
    text: str
    vector: tuple[float, ...] = ()


class SemanticSearchTool(BaseCodeSearchTool):
    """Rank code chunks by embedding similarity or token overlap."""

    def __init__(
        self,
        root_dir: str,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        chunk_lines: int = 80,
        overlap_lines: int = 10,
    ) -> None:
        """Configure indexing and optional embeddings."""
        super().__init__(root_dir)
        self.embedding_provider = embedding_provider
        self.chunk_lines = max(10, chunk_lines)
        self.overlap_lines = max(0, min(overlap_lines, self.chunk_lines - 1))
        self._chunks: tuple[_CodeChunk, ...] = ()

    def spec(self) -> ToolSpec:
        """Return the model-facing semantic search declaration."""
        return ToolSpec(
            name="semantic_search",
            description="Search indexed code chunks by natural-language query.",
            permission=ToolPermission.READ,
            parameters=(
                ToolParameter("query", "string", "Natural-language search query."),
                ToolParameter("subdir", "string", "Subdirectory to index/search.", required=False),
                ToolParameter("max_results", "integer", "Maximum chunks to return.", required=False),
                ToolParameter("max_chars_per_result", "integer", "Maximum text per chunk.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Rank indexed chunks and return bounded top results."""
        query = str(call.arguments["query"])
        subdir = str(call.arguments.get("subdir", "."))
        max_results = max(1, min(int(call.arguments.get("max_results", 5)), 25))
        max_chars = max(200, min(int(call.arguments.get("max_chars_per_result", 1200)), 5000))
        try:
            self.rebuild_index(subdir=subdir)
        except ValueError as exc:
            return ToolResult.error(self.name, str(exc), metadata={"error": "unsafe_path"})
        if not self._chunks:
            return ToolResult.success(self.name, "No indexable code chunks found.", metadata={"count": 0})

        ranked = self._rank(query)
        blocks: list[str] = []
        for score, chunk in ranked[:max_results]:
            text = chunk.text[:max_chars]
            if len(chunk.text) > max_chars:
                text += "\n...[truncated]"
            blocks.append(
                f"{chunk.path}:{chunk.start_line}-{chunk.end_line} score={score:.3f}\n```text\n{text}\n```"
            )
        return ToolResult.success(
            self.name,
            "\n\n".join(blocks),
            metadata={"count": len(blocks), "indexed_chunks": len(self._chunks)},
        )

    def rebuild_index(self, *, subdir: str = ".") -> None:
        """Rebuild the in-memory chunk index for a safe subdirectory."""
        chunks: list[_CodeChunk] = []
        for path in self.iter_files(subdir):
            lines = self.read_text_lines(path)
            step = max(1, self.chunk_lines - self.overlap_lines)
            for start in range(0, len(lines), step):
                end = min(len(lines), start + self.chunk_lines)
                text = "\n".join(lines[start:end]).strip()
                if not text:
                    continue
                chunks.append(
                    _CodeChunk(
                        path=self.relative_path(path),
                        start_line=start + 1,
                        end_line=end,
                        text=text,
                    )
                )
                if end >= len(lines):
                    break
        if self.embedding_provider and chunks:
            vectors = self.embedding_provider.embed([chunk.text for chunk in chunks])
            chunks = [
                _CodeChunk(
                    path=chunk.path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    text=chunk.text,
                    vector=tuple(float(value) for value in vector),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        self._chunks = tuple(chunks)

    def _rank(self, query: str) -> list[tuple[float, _CodeChunk]]:
        """Rank chunks using embeddings when present, otherwise token overlap."""
        if self.embedding_provider:
            query_vector = tuple(float(value) for value in self.embedding_provider.embed([query])[0])
            return sorted(
                ((self._cosine(query_vector, chunk.vector), chunk) for chunk in self._chunks),
                key=lambda item: item[0],
                reverse=True,
            )
        query_tokens = self._tokens(query)
        return sorted(
            ((self._token_score(query_tokens, self._tokens(chunk.text)), chunk) for chunk in self._chunks),
            key=lambda item: item[0],
            reverse=True,
        )

    def _tokens(self, text: str) -> set[str]:
        """Extract normalized word tokens for fallback ranking."""
        return set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", text.lower()))

    def _token_score(self, query_tokens: set[str], chunk_tokens: set[str]) -> float:
        """Return a stable overlap score between query and chunk tokens."""
        if not query_tokens or not chunk_tokens:
            return 0.0
        return len(query_tokens & chunk_tokens) / len(query_tokens)

    def _cosine(self, left: Sequence[float], right: Sequence[float]) -> float:
        """Compute cosine similarity for two embedding vectors."""
        if len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
