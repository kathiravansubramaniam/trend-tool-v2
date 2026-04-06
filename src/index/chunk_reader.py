import json
import re
import sqlite3
from dataclasses import dataclass, field

from src.index.chunk_schema import get_connection


@dataclass
class ChunkResult:
    chunk_id: str
    gcs_name: str
    doc_name: str
    chunk_order: int
    section_title: str
    chunk_text: str
    chunk_summary: str
    topics: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    behavioral_shifts: list[str] = field(default_factory=list)
    trend_drivers: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    brands_companies: list[str] = field(default_factory=list)
    consumer_needs: list[str] = field(default_factory=list)
    retrieval_phrases: list[str] = field(default_factory=list)
    evidence_type: str = "claim"
    evidence_strength: str = "moderate"
    score: float = 0.0


def _jl(v: str | None) -> list:
    return json.loads(v) if v else []


def _row_to_chunk(row: sqlite3.Row, score: float = 0.0) -> ChunkResult:
    return ChunkResult(
        chunk_id=row["chunk_id"],
        gcs_name=row["gcs_name"],
        doc_name=row["doc_name"] if "doc_name" in row.keys() else row["gcs_name"],
        chunk_order=row["chunk_order"],
        section_title=row["section_title"] or "",
        chunk_text=row["chunk_text"] or "",
        chunk_summary=row["chunk_summary"] or "",
        topics=_jl(row["topics"]),
        themes=_jl(row["themes"]),
        behavioral_shifts=_jl(row["behavioral_shifts"]),
        trend_drivers=_jl(row["trend_drivers"]),
        technologies=_jl(row["technologies"]),
        brands_companies=_jl(row["brands_companies"]),
        consumer_needs=_jl(row["consumer_needs"]),
        retrieval_phrases=_jl(row["retrieval_phrases"]),
        evidence_type=row["evidence_type"] or "claim",
        evidence_strength=row["evidence_strength"] or "moderate",
        score=score,
    )


_CHUNK_COLS = """
    c.chunk_id, c.gcs_name, c.chunk_order, c.section_title,
    c.chunk_text, c.chunk_summary, c.topics, c.themes,
    c.behavioral_shifts, c.trend_drivers, c.technologies,
    c.brands_companies, c.consumer_needs, c.retrieval_phrases,
    c.evidence_type, c.evidence_strength,
    d.doc_name
"""


def _sanitize(query: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", query).split())


def search_chunks_fts(query: str, limit: int = 50) -> list[ChunkResult]:
    """FTS5 search over chunk content and metadata fields."""
    safe = _sanitize(query)
    if not safe:
        return []

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_CHUNK_COLS}, bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.id
            JOIN documents d ON c.gcs_name = d.gcs_name
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (safe, limit),
        ).fetchall()
    return [_row_to_chunk(r, r["score"]) for r in rows]


def get_chunks_by_ids(chunk_ids: list[str]) -> list[ChunkResult]:
    """Fetch specific chunks by chunk_id (used after vector search)."""
    if not chunk_ids:
        return []
    placeholders = ",".join("?" * len(chunk_ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_CHUNK_COLS}
            FROM chunks c
            JOIN documents d ON c.gcs_name = d.gcs_name
            WHERE c.chunk_id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()
    # Preserve the order of chunk_ids
    by_id = {r["chunk_id"]: _row_to_chunk(r) for r in rows}
    return [by_id[cid] for cid in chunk_ids if cid in by_id]


def get_chunks_for_doc(gcs_name: str) -> list[ChunkResult]:
    """Return all chunks for a document, ordered by chunk_order."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_CHUNK_COLS}
            FROM chunks c
            JOIN documents d ON c.gcs_name = d.gcs_name
            WHERE c.gcs_name = ?
            ORDER BY c.chunk_order
            """,
            (gcs_name,),
        ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def get_chunked_gcs_names() -> set[str]:
    """Return the set of gcs_names that have at least one chunk stored."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT gcs_name FROM chunks").fetchall()
    return {r["gcs_name"] for r in rows}
