import logging
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings
from src.index.reader import filter_by_industry, get_docs_by_gcs_names, search_by_text
from src.index.vector_store import get_vector_count, semantic_search
from src.storage.gcs_client import GCSClient

logger = logging.getLogger(__name__)
gcs_client = GCSClient()


@dataclass
class RetrievedDoc:
    gcs_name: str
    doc_name: str
    industry: str
    market_scope: str
    topics: list[str]
    forecasts: list[str]
    local_path: Path
    score: float


def load_docs_by_gcs_names(gcs_names: list[str]) -> list[RetrievedDoc]:
    """Load a specific set of docs by GCS name (used for follow-up queries)."""
    rows = get_docs_by_gcs_names(gcs_names)
    docs = []
    for r in rows:
        try:
            local_path = gcs_client.download_pdf(r.gcs_name)
            docs.append(RetrievedDoc(
                gcs_name=r.gcs_name,
                doc_name=r.doc_name,
                industry=r.industry,
                market_scope=r.market_scope,
                topics=r.topics,
                forecasts=r.forecasts,
                local_path=local_path,
                score=1.0,
            ))
        except Exception as e:
            logger.warning(f"Could not load {r.gcs_name}: {e}")
    return docs


def _matches_industry_filter(industry: str, filters: list[str]) -> bool:
    industry_lower = industry.lower()
    return any(f.lower() in industry_lower for f in filters)


def retrieve_relevant_docs(
    question: str,
    industry_filter: list[str] | str | None = None,
    max_docs: int | None = None,
) -> list[RetrievedDoc]:
    if max_docs is None:
        max_docs = settings.max_query_docs

    # Normalise to list or None
    if isinstance(industry_filter, str):
        industry_filter = [industry_filter] if industry_filter.lower() not in ("all", "any", "") else None
    elif isinstance(industry_filter, list):
        industry_filter = [f for f in industry_filter if f.lower() not in ("all", "any", "")] or None

    # Use semantic vector search if embeddings exist, else fall back to FTS5
    if get_vector_count() > 0:
        raw_results = semantic_search(
            query=question,
            n_results=max_docs * 2,
            industry_filter=industry_filter[0] if industry_filter and len(industry_filter) == 1 else None,
        )
        # Apply industry post-filter if needed
        if industry_filter:
            filtered = [r for r in raw_results if _matches_industry_filter(r["industry"], industry_filter)]
            if not filtered:
                filtered = raw_results  # relax filter if it wiped everything
            raw_results = filtered

        results = raw_results[:max_docs]
        doc_data = [
            {
                "gcs_name": r["gcs_name"],
                "doc_name": r["doc_name"],
                "industry": r["industry"],
                "market_scope": r["market_scope"],
                "topics": r["topics"],
                "forecasts": r["forecasts"],
                "score": 1.0 - r["distance"],  # convert distance to similarity score
            }
            for r in results
        ]
    else:
        # FTS5 fallback (before embeddings are generated)
        logger.info("No embeddings yet, falling back to FTS5 search")
        fts_results = search_by_text(question, limit=max_docs * 3)
        if industry_filter:
            fts_results = [r for r in fts_results if _matches_industry_filter(r.industry, industry_filter)]
            if not fts_results:
                fts_results = filter_by_industry(industry_filter[0], limit=max_docs * 2)
        doc_data = [
            {
                "gcs_name": r.gcs_name,
                "doc_name": r.doc_name,
                "industry": r.industry,
                "market_scope": r.market_scope,
                "topics": r.topics,
                "forecasts": r.forecasts,
                "score": r.score,
            }
            for r in fts_results[:max_docs]
        ]

    if not doc_data:
        return []

    docs = []
    for r in doc_data:
        try:
            local_path = gcs_client.download_pdf(r["gcs_name"])
            docs.append(RetrievedDoc(
                gcs_name=r["gcs_name"],
                doc_name=r["doc_name"],
                industry=r["industry"],
                market_scope=r["market_scope"],
                topics=r["topics"],
                forecasts=r["forecasts"],
                local_path=local_path,
                score=r["score"],
            ))
        except Exception as e:
            logger.warning(f"Could not download {r['gcs_name']}: {e}")

    return docs
