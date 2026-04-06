import logging
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings
from src.index.chunk_reader import ChunkResult, get_chunks_by_ids, search_chunks_fts
from src.index.chunk_schema import get_chunk_count
from src.index.chunk_vector_store import get_chunk_vector_count, semantic_search_chunks
from src.index.reader import SearchResult, filter_by_industry, get_docs_by_gcs_names, search_by_text
from src.index.vector_store import get_vector_count, semantic_search
from src.query.planner import plan_retrieval
from src.storage.gcs_client import GCSClient

logger = logging.getLogger(__name__)
gcs_client = GCSClient()

# Candidate pool sizes
_DOC_CANDIDATE_POOL   = 40
_CHUNK_CANDIDATE_POOL = 60   # more chunks since they're smaller units
_MAX_CHUNKS_PER_DOC   = 4    # cap per-document contribution to avoid one doc dominating


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
    planner_score: float = 0.0
    planner_explanation: str = ""


# ── Document-level retrieval (legacy path) ───────────────────────────────────

def load_docs_by_gcs_names(gcs_names: list[str]) -> list[RetrievedDoc]:
    rows = get_docs_by_gcs_names(gcs_names)
    docs = []
    for r in rows:
        try:
            local_path = gcs_client.download_pdf(r.gcs_name)
            docs.append(RetrievedDoc(
                gcs_name=r.gcs_name, doc_name=r.doc_name, industry=r.industry,
                market_scope=r.market_scope, topics=r.topics, forecasts=r.forecasts,
                local_path=local_path, score=1.0,
            ))
        except Exception as e:
            logger.warning(f"Could not load {r.gcs_name}: {e}")
    return docs


def _matches_industry_filter(industry: str, filters: list[str]) -> bool:
    industry_lower = industry.lower()
    return any(f.lower() in industry_lower for f in filters)


def _get_doc_candidates(
    question: str,
    industry_filter: list[str] | None,
    pool_size: int,
) -> list[SearchResult]:
    if get_vector_count() > 0:
        raw = semantic_search(query=question, n_results=pool_size)
        if industry_filter:
            filtered = [r for r in raw if _matches_industry_filter(r["industry"], industry_filter)]
            raw = filtered or raw
        gcs_names = [r["gcs_name"] for r in raw]
        candidates = get_docs_by_gcs_names(gcs_names)
        score_map = {r["gcs_name"]: 1.0 - r["distance"] for r in raw}
        for c in candidates:
            c.score = score_map.get(c.gcs_name, 0.5)
    else:
        candidates = search_by_text(question, limit=pool_size)
        if industry_filter:
            filtered = [c for c in candidates if _matches_industry_filter(c.industry, industry_filter)]
            candidates = filtered or (filter_by_industry(industry_filter[0], limit=pool_size) if industry_filter else candidates)
    return candidates


def retrieve_relevant_docs(
    question: str,
    industry_filter: list[str] | str | None = None,
    max_docs: int | None = None,
) -> list[RetrievedDoc]:
    """Document-level retrieval with LLM planner. Kept as fallback."""
    if max_docs is None:
        max_docs = settings.max_query_docs

    if isinstance(industry_filter, str):
        industry_filter = [industry_filter] if industry_filter.lower() not in ("all", "any", "") else None
    elif isinstance(industry_filter, list):
        industry_filter = [f for f in industry_filter if f.lower() not in ("all", "any", "")] or None

    candidates = _get_doc_candidates(question, industry_filter, _DOC_CANDIDATE_POOL)
    if not candidates:
        return []

    logger.info(f"Doc-level candidates: {len(candidates)} → running planner")
    plan = plan_retrieval(question, candidates, industry_filter)

    if plan.selected_gcs_names:
        candidate_map = {c.gcs_name: c for c in candidates}
        selected = [candidate_map[n] for n in plan.selected_gcs_names if n in candidate_map]
    else:
        selected = sorted(candidates, key=lambda r: r.score, reverse=True)

    docs: list[RetrievedDoc] = []
    for r in selected[:max_docs]:
        try:
            local_path = gcs_client.download_pdf(r.gcs_name)
            doc = RetrievedDoc(
                gcs_name=r.gcs_name, doc_name=r.doc_name, industry=r.industry,
                market_scope=r.market_scope, topics=r.topics, forecasts=r.forecasts,
                local_path=local_path, score=r.score,
                planner_score=plan.score_per_document.get(r.gcs_name, r.score),
                planner_explanation=plan.explanation_per_document.get(r.gcs_name, ""),
            )
            docs.append(doc)
        except Exception as e:
            logger.warning(f"Could not download {r.gcs_name}: {e}")

    logger.info(f"Retrieved {len(docs)} docs after planner selection")
    return docs


# ── Chunk-level retrieval (primary path when chunks are indexed) ─────────────

def _dedupe_and_cap(chunks: list[ChunkResult]) -> list[ChunkResult]:
    """
    Remove duplicate chunk_ids and cap per-document contributions.
    Preserves score ordering.
    """
    seen_ids: set[str] = set()
    per_doc: dict[str, int] = {}
    result: list[ChunkResult] = []

    for c in chunks:
        if c.chunk_id in seen_ids:
            continue
        doc_count = per_doc.get(c.gcs_name, 0)
        if doc_count >= _MAX_CHUNKS_PER_DOC:
            continue
        seen_ids.add(c.chunk_id)
        per_doc[c.gcs_name] = doc_count + 1
        result.append(c)

    return result


def retrieve_relevant_chunks(
    question: str,
    industry_filter: list[str] | str | None = None,
    max_chunks: int = 15,
    pinned_gcs_names: list[str] | None = None,
) -> list[ChunkResult]:
    """
    Chunk-level retrieval.

    1. Semantic vector search over chunk embeddings → top 60 candidates
    2. Per-document cap (_MAX_CHUNKS_PER_DOC) to avoid dominance
    3. FTS5 fallback if no chunk vectors exist
    4. Returns up to max_chunks chunks with their text ready for the answerer

    When pinned_gcs_names is set, only return chunks from those documents.
    """
    # Normalise industry filter
    if isinstance(industry_filter, str):
        industry_filter = [industry_filter] if industry_filter.lower() not in ("all", "any", "") else None
    elif isinstance(industry_filter, list):
        industry_filter = [f for f in industry_filter if f.lower() not in ("all", "any", "")] or None

    raw_chunks: list[ChunkResult] = []

    if pinned_gcs_names:
        # When pinned: fetch all chunks for those docs from DB, scored flat
        from src.index.chunk_reader import get_chunks_for_doc
        for gcs_name in pinned_gcs_names:
            chunks = get_chunks_for_doc(gcs_name)
            for c in chunks:
                c.score = 1.0
            raw_chunks.extend(chunks)
        # Score by keyword overlap against question
        q_words = set(question.lower().split())
        for c in raw_chunks:
            text_words = set((c.section_title + " " + c.chunk_summary + " " + " ".join(c.retrieval_phrases)).lower().split())
            c.score = len(q_words & text_words) / max(len(q_words), 1)
        raw_chunks.sort(key=lambda c: c.score, reverse=True)

    elif get_chunk_vector_count() > 0:
        # Semantic chunk search
        vector_results = semantic_search_chunks(question, n_results=_CHUNK_CANDIDATE_POOL)
        chunk_ids = [r["chunk_id"] for r in vector_results]
        chunks_by_id = {c.chunk_id: c for c in get_chunks_by_ids(chunk_ids)}

        for r in vector_results:
            c = chunks_by_id.get(r["chunk_id"])
            if not c:
                continue
            # Apply industry filter
            if industry_filter:
                # We don't store industry per-chunk, so skip industry filter at chunk level
                # (document-level industry filter is applied at document retrieval)
                pass
            c.score = 1.0 - r["distance"]
            raw_chunks.append(c)

    elif get_chunk_count() > 0:
        # FTS5 fallback
        logger.info("No chunk vectors yet — falling back to FTS5 chunk search")
        raw_chunks = search_chunks_fts(question, limit=_CHUNK_CANDIDATE_POOL)

    if not raw_chunks:
        return []

    # De-dupe and cap per-document contribution
    selected = _dedupe_and_cap(raw_chunks)[:max_chunks]

    logger.info(f"Chunk retrieval: {len(raw_chunks)} candidates → {len(selected)} selected "
                f"across {len({c.gcs_name for c in selected})} docs")
    return selected


def has_chunks() -> bool:
    """True if the chunk index has been populated."""
    return get_chunk_count() > 0
