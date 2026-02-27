"""
FastAPI backend for the Trend Analysis Bot.
Run with: python3 -m uvicorn api.main:app --reload --port 8000
"""
import hashlib
import sys
from collections import OrderedDict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.index.reader import get_index_stats, get_top_industries
from src.index.schema import init_db
from src.index.vector_store import get_vector_count
from src.query.answerer import answer_from_chunks, answer_question
from src.query.retriever import load_docs_by_gcs_names, retrieve_relevant_docs
from src.storage.gcs_client import GCSClient

_gcs = GCSClient()

# In-memory chunk cache: context_id -> list of (doc_name, chunk) tuples
# Keyed by a hash of the sorted gcs_names used in that query. Max 20 entries.
_chunk_cache: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
_CACHE_MAX = 20


def _make_context_id(gcs_names: list[str]) -> str:
    return hashlib.md5("|".join(sorted(gcs_names)).encode()).hexdigest()[:16]


def _cache_chunks(context_id: str, chunks: list[tuple[str, str]]) -> None:
    if context_id in _chunk_cache:
        _chunk_cache.move_to_end(context_id)
    _chunk_cache[context_id] = chunks
    while len(_chunk_cache) > _CACHE_MAX:
        _chunk_cache.popitem(last=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Trend Analysis Bot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow any localhost port during development
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    industry_filter: list[str] | str | None = None
    max_docs: int = 8
    pinned_gcs_names: list[str] | None = None
    context_id: str | None = None  # set on follow-up to skip re-chunking


class SourceDoc(BaseModel):
    gcs_name: str
    name: str
    industry: str
    topics: list[str]
    url: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceDoc]
    doc_count: int
    context_id: str | None = None  # returned so frontend can send it back on follow-up


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Follow-up fast path: reuse cached chunks, skip all PDF I/O
    if req.context_id and req.context_id in _chunk_cache:
        cached_chunks = _chunk_cache[req.context_id]
        result = answer_from_chunks(question=req.question, all_chunks=cached_chunks)
        # Rebuild sources from cached chunks' doc names
        seen: list[str] = []
        for doc_name, _ in cached_chunks:
            if doc_name not in seen:
                seen.append(doc_name)
        sources = [
            SourceDoc(gcs_name="", name=name, industry="", topics=[])
            for name in result.sources
        ]
        return QueryResponse(
            answer=result.answer,
            sources=sources,
            doc_count=len(seen),
            context_id=req.context_id,
        )

    # Normal path: retrieve or load docs, then chunk
    if req.pinned_gcs_names:
        docs = load_docs_by_gcs_names(req.pinned_gcs_names)
    else:
        docs = retrieve_relevant_docs(
            question=req.question,
            industry_filter=req.industry_filter,
            max_docs=req.max_docs,
        )

    result = answer_question(question=req.question, docs=docs)

    # Cache the chunks for follow-up queries
    gcs_names = [d.gcs_name for d in docs]
    context_id = _make_context_id(gcs_names) if gcs_names else None
    if context_id and result.all_chunks:
        _cache_chunks(context_id, result.all_chunks)

    # Build source metadata
    doc_map = {d.doc_name: d for d in docs}
    sources = []
    for name in result.sources:
        doc = doc_map.get(name)
        url = None
        if doc:
            try:
                url = _gcs.get_signed_url(doc.gcs_name)
            except Exception:
                pass
        sources.append(SourceDoc(
            gcs_name=doc.gcs_name if doc else "",
            name=name,
            industry=doc.industry if doc else "",
            topics=doc.topics[:4] if doc else [],
            url=url,
        ))

    return QueryResponse(
        answer=result.answer,
        sources=sources,
        doc_count=len(docs),
        context_id=context_id,
    )


@app.get("/api/industries")
def industries():
    items = get_top_industries(limit=40)
    return [{"name": name, "count": count} for name, count in items]


@app.get("/api/stats")
def stats():
    s = get_index_stats()
    return {
        "total": s["total"],
        "indexed": s["done"],
        "failed": s["failed"],
        "industries": s["industries"],
        "embeddings": get_vector_count(),
    }


@app.get("/health")
def health():
    return {"status": "ok"}
