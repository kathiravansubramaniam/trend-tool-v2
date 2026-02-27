import json
import re
import sqlite3
from dataclasses import dataclass

from src.index.schema import get_connection


@dataclass
class SearchResult:
    id: int
    gcs_name: str
    doc_name: str
    industry: str
    market_scope: str
    topics: list[str]
    forecasts: list[str]
    score: float = 0.0


def _row_to_result(row: sqlite3.Row, score: float = 0.0) -> SearchResult:
    return SearchResult(
        id=row["id"],
        gcs_name=row["gcs_name"],
        doc_name=row["doc_name"] or row["gcs_name"],
        industry=row["industry"] or "Unknown",
        market_scope=row["market_scope"] or "unknown",
        topics=json.loads(row["topics"] or "[]"),
        forecasts=json.loads(row["forecasts"] or "[]"),
        score=score,
    )


def _sanitize_fts_query(query: str) -> str:
    # Remove FTS5 special characters to avoid syntax errors
    clean = re.sub(r'[^\w\s]', ' ', query)
    return ' '.join(clean.split())


def search_by_text(query: str, limit: int = 20) -> list[SearchResult]:
    safe_query = _sanitize_fts_query(query)
    if not safe_query.strip():
        return get_all_done(limit)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.gcs_name, d.doc_name, d.industry, d.market_scope,
                   d.topics, d.forecasts, bm25(documents_fts) as score
            FROM documents_fts
            JOIN documents d ON documents_fts.rowid = d.id
            WHERE documents_fts MATCH ?
              AND d.parse_status = 'done'
            ORDER BY score
            LIMIT ?
            """,
            (safe_query, limit),
        ).fetchall()
    return [_row_to_result(r, r["score"]) for r in rows]


def filter_by_industry(industry: str, limit: int = 50) -> list[SearchResult]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, gcs_name, doc_name, industry, market_scope, topics, forecasts
            FROM documents
            WHERE industry LIKE ? AND parse_status = 'done'
            ORDER BY doc_name
            LIMIT ?
            """,
            (f"%{industry}%", limit),
        ).fetchall()
    return [_row_to_result(r) for r in rows]


def get_all_done(limit: int = 50) -> list[SearchResult]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, gcs_name, doc_name, industry, market_scope, topics, forecasts
            FROM documents
            WHERE parse_status = 'done'
            ORDER BY doc_name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_result(r) for r in rows]


def get_top_industries(limit: int = 50) -> list[tuple[str, int]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT industry, COUNT(*) as cnt
            FROM documents
            WHERE parse_status = 'done' AND industry IS NOT NULL
            GROUP BY industry
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(r["industry"], r["cnt"]) for r in rows]


def get_index_stats() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        done = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE parse_status='done'"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE parse_status='pending'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE parse_status='failed'"
        ).fetchone()[0]
        industries = conn.execute(
            "SELECT COUNT(DISTINCT industry) FROM documents WHERE parse_status='done'"
        ).fetchone()[0]
    return {
        "total": total,
        "done": done,
        "pending": pending,
        "failed": failed,
        "industries": industries,
    }


def get_docs_by_gcs_names(gcs_names: list[str]) -> list[SearchResult]:
    placeholders = ",".join("?" * len(gcs_names))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, gcs_name, doc_name, industry, market_scope, topics, forecasts
            FROM documents
            WHERE gcs_name IN ({placeholders}) AND parse_status = 'done'
            """,
            gcs_names,
        ).fetchall()
    return [_row_to_result(r) for r in rows]


def get_unparsed_gcs_names() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT gcs_name FROM documents WHERE parse_status != 'done'"
        ).fetchall()
    return [r["gcs_name"] for r in rows]
