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
    # Rich metadata
    summary: str = ""
    industries_primary: list[str] = None  # type: ignore[assignment]
    subsectors: list[str] = None  # type: ignore[assignment]
    consumer_needs: list[str] = None  # type: ignore[assignment]
    behavioral_shifts: list[str] = None  # type: ignore[assignment]
    trend_drivers: list[str] = None  # type: ignore[assignment]
    technologies: list[str] = None  # type: ignore[assignment]
    themes: list[str] = None  # type: ignore[assignment]
    brands_companies: list[str] = None  # type: ignore[assignment]
    demographics: dict = None  # type: ignore[assignment]
    geographies: dict = None  # type: ignore[assignment]
    time_horizon: str = "short-term"
    publish_date: str | None = None
    likely_questions: list[str] = None  # type: ignore[assignment]
    retrieval_phrases: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.industries_primary is None:
            self.industries_primary = []
        if self.subsectors is None:
            self.subsectors = []
        if self.consumer_needs is None:
            self.consumer_needs = []
        if self.behavioral_shifts is None:
            self.behavioral_shifts = []
        if self.trend_drivers is None:
            self.trend_drivers = []
        if self.technologies is None:
            self.technologies = []
        if self.themes is None:
            self.themes = []
        if self.brands_companies is None:
            self.brands_companies = []
        if self.demographics is None:
            self.demographics = {}
        if self.geographies is None:
            self.geographies = {}
        if self.likely_questions is None:
            self.likely_questions = []
        if self.retrieval_phrases is None:
            self.retrieval_phrases = []


def _jl(val: str | None) -> list:
    return json.loads(val) if val else []


def _jd(val: str | None) -> dict:
    return json.loads(val) if val else {}


def _row_to_result(row: sqlite3.Row, score: float = 0.0) -> SearchResult:
    return SearchResult(
        id=row["id"],
        gcs_name=row["gcs_name"],
        doc_name=row["doc_name"] or row["gcs_name"],
        industry=row["industry"] or "Unknown",
        market_scope=row["market_scope"] or "unknown",
        topics=_jl(row["topics"]),
        forecasts=_jl(row["forecasts"]),
        score=score,
        summary=row["summary"] or "",
        industries_primary=_jl(row["industries_primary"]),
        subsectors=_jl(row["subsectors"]),
        consumer_needs=_jl(row["consumer_needs"]),
        behavioral_shifts=_jl(row["behavioral_shifts"]),
        trend_drivers=_jl(row["trend_drivers"]),
        technologies=_jl(row["technologies"]),
        themes=_jl(row["themes"]),
        brands_companies=_jl(row["brands_companies"]),
        demographics=_jd(row["demographics"]),
        geographies=_jd(row["geographies"]),
        time_horizon=row["time_horizon"] or "short-term",
        publish_date=row["publish_date"],
        likely_questions=_jl(row["likely_questions"]),
        retrieval_phrases=_jl(row["retrieval_phrases"]),
    )


def _sanitize_fts_query(query: str) -> str:
    # Remove FTS5 special characters to avoid syntax errors
    clean = re.sub(r'[^\w\s]', ' ', query)
    return ' '.join(clean.split())


_RICH_COLS = """
    d.id, d.gcs_name, d.doc_name, d.industry, d.market_scope,
    d.topics, d.forecasts, d.summary, d.industries_primary, d.subsectors,
    d.consumer_needs, d.behavioral_shifts, d.trend_drivers, d.technologies,
    d.themes, d.brands_companies, d.demographics, d.geographies,
    d.time_horizon, d.publish_date, d.likely_questions, d.retrieval_phrases
"""


def search_by_text(query: str, limit: int = 20) -> list[SearchResult]:
    safe_query = _sanitize_fts_query(query)
    if not safe_query.strip():
        return get_all_done(limit)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_RICH_COLS}, bm25(documents_fts) as score
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
            f"""
            SELECT {_RICH_COLS}
            FROM documents d
            WHERE d.industry LIKE ? AND d.parse_status = 'done'
            ORDER BY d.doc_name
            LIMIT ?
            """,
            (f"%{industry}%", limit),
        ).fetchall()
    return [_row_to_result(r) for r in rows]


def get_all_done(limit: int = 50) -> list[SearchResult]:
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {_RICH_COLS}
            FROM documents d
            WHERE d.parse_status = 'done'
            ORDER BY d.doc_name
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
            SELECT {_RICH_COLS}
            FROM documents d
            WHERE d.gcs_name IN ({placeholders}) AND d.parse_status = 'done'
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
