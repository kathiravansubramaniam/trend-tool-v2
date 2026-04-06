import logging
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings
from src.index.reader import SearchResult, filter_by_industry, get_docs_by_gcs_names, search_by_text
from src.index.vector_store import get_vector_count, semantic_search
from src.query.planner import plan_retrieval
from src.storage.gcs_client import GCSClient

logger = logging.getLogger(__name__)
gcs_client = GCSClient()

# How many candidates to pull before sending to the planner
_CANDIDATE_POOL = 40


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
    # Planner-provided context (optional, may be empty)
    planner_score: float = 0.0
    planner_explanation: str = ""


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


def _search_result_to_retrieved_doc(r: SearchResult, local_path: Path) -> RetrievedDoc:
    return RetrievedDoc(
        gcs_name=r.gcs_name,
        doc_name=r.doc_name,
        industry=r.industry,
        market_scope=r.market_scope,
        topics=r.topics,
        forecasts=r.forecasts,
        local_path=local_path,
        score=r.score,
    )


def _get_candidates(
    question: str,
    industry_filter: list[str] | None,
    pool_size: int,
) -> list[SearchResult]:
    """
    Pull a broad candidate set from ChromaDB (semantic) or FTS5 (fallback).
    Returns SearchResult objects with full rich metadata.
    """
    if get_vector_count() > 0:
        raw_results = semantic_search(
            query=question,
            n_results=pool_size,
            industry_filter=industry_filter[0] if industry_filter and len(industry_filter) == 1 else None,
        )
        if industry_filter and len(industry_filter) > 1:
            filtered = [r for r in raw_results if _matches_industry_filter(r["industry"], industry_filter)]
            if not filtered:
                filtered = raw_results
            raw_results = filtered

        # Re-fetch full metadata from SQLite (vector store only returns basic fields)
        gcs_names = [r["gcs_name"] for r in raw_results]
        candidates = get_docs_by_gcs_names(gcs_names)

        # Attach vector distances as scores
        score_map = {r["gcs_name"]: 1.0 - r["distance"] for r in raw_results}
        for c in candidates:
            c.score = score_map.get(c.gcs_name, 0.5)
    else:
        logger.info("No embeddings yet — falling back to FTS5 search")
        candidates = search_by_text(question, limit=pool_size)
        if industry_filter:
            filtered = [c for c in candidates if _matches_industry_filter(c.industry, industry_filter)]
            if not filtered:
                filtered = filter_by_industry(industry_filter[0], limit=pool_size)
            candidates = filtered

    return candidates


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

    # Step 1: Get broad candidate pool with full rich metadata
    candidates = _get_candidates(question, industry_filter, _CANDIDATE_POOL)
    if not candidates:
        return []

    logger.info(f"Candidate pool: {len(candidates)} docs — running retrieval planner")

    # Step 2: Run LLM retrieval planner to semantically rank candidates
    plan = plan_retrieval(question, candidates, industry_filter)

    # Step 3: Build ordered list using planner selection
    if plan.selected_gcs_names:
        candidate_map = {c.gcs_name: c for c in candidates}
        selected_results = [
            candidate_map[name]
            for name in plan.selected_gcs_names
            if name in candidate_map
        ]
    else:
        # Fallback: use raw candidates ordered by score
        selected_results = sorted(candidates, key=lambda r: r.score, reverse=True)[:max_docs]

    selected_results = selected_results[:max_docs]

    # Step 4: Download PDFs for selected docs only
    docs: list[RetrievedDoc] = []
    for r in selected_results:
        try:
            local_path = gcs_client.download_pdf(r.gcs_name)
            doc = _search_result_to_retrieved_doc(r, local_path)
            doc.planner_score = plan.score_per_document.get(r.gcs_name, r.score)
            doc.planner_explanation = plan.explanation_per_document.get(r.gcs_name, "")
            docs.append(doc)
        except Exception as e:
            logger.warning(f"Could not download {r.gcs_name}: {e}")

    logger.info(f"Retrieved {len(docs)} docs after planner selection")
    return docs
