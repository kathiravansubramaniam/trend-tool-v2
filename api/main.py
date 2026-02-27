"""
FastAPI backend for the Trend Analysis Bot.
Run with: python3 -m uvicorn api.main:app --reload --port 8000
"""
import asyncio
import hashlib
import json
import logging
import sys
from collections import OrderedDict
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

import fastapi
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
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


@app.post("/api/query-stream")
async def query_stream(req: QueryRequest):
    async def generate():
        from src.index.reader import get_docs_by_gcs_names, search_by_text
        from src.index.vector_store import get_vector_count, semantic_search
        from src.query.answerer import answer_from_chunks, answer_question
        from src.query.retriever import RetrievedDoc

        loop = asyncio.get_event_loop()

        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        try:
            # Fast path: cached context
            if req.context_id and req.context_id in _chunk_cache:
                cached_chunks = _chunk_cache[req.context_id]
                yield sse({"type": "answering"})
                result = await loop.run_in_executor(
                    None, lambda: answer_from_chunks(question=req.question, all_chunks=cached_chunks)
                )
                sources = [{"gcs_name": "", "name": n, "industry": "", "topics": []} for n in result.sources]
                yield sse({"type": "answer", "answer": result.answer, "sources": sources, "context_id": req.context_id})
                return

            # Step 1: search
            yield sse({"type": "searching"})

            if req.pinned_gcs_names:
                rows = get_docs_by_gcs_names(req.pinned_gcs_names)
                doc_data = [{"gcs_name": r.gcs_name, "doc_name": r.doc_name, "industry": r.industry,
                             "market_scope": r.market_scope, "topics": r.topics, "forecasts": r.forecasts, "score": 1.0}
                            for r in rows]
            else:
                industry_filter = req.industry_filter
                if isinstance(industry_filter, str):
                    industry_filter = [industry_filter] if industry_filter.lower() not in ("all", "any", "") else None
                elif isinstance(industry_filter, list):
                    industry_filter = [f for f in industry_filter if f.lower() not in ("all", "any", "")] or None

                if get_vector_count() > 0:
                    raw = await loop.run_in_executor(
                        None, lambda: semantic_search(query=req.question, n_results=req.max_docs * 2)
                    )
                    if industry_filter:
                        filtered = [r for r in raw if any(f.lower() in r["industry"].lower() for f in industry_filter)]
                        raw = filtered or raw
                    doc_data = [{"gcs_name": r["gcs_name"], "doc_name": r["doc_name"], "industry": r["industry"],
                                 "market_scope": r["market_scope"], "topics": r["topics"], "forecasts": r["forecasts"],
                                 "score": 1.0 - r["distance"]} for r in raw[:req.max_docs]]
                else:
                    fts = await loop.run_in_executor(None, lambda: search_by_text(req.question, limit=req.max_docs * 3))
                    if industry_filter:
                        fts = [r for r in fts if any(f.lower() in r.industry.lower() for f in industry_filter)] or fts
                    doc_data = [{"gcs_name": r.gcs_name, "doc_name": r.doc_name, "industry": r.industry,
                                 "market_scope": r.market_scope, "topics": r.topics, "forecasts": r.forecasts,
                                 "score": r.score} for r in fts[:req.max_docs]]

            total = len(doc_data)
            yield sse({"type": "found", "total": total})

            # Step 2: load each doc
            docs: list[RetrievedDoc] = []
            for i, r in enumerate(doc_data):
                yield sse({"type": "loading", "index": i, "total": total,
                           "doc": {"name": r["doc_name"], "industry": r["industry"]}})
                try:
                    local_path = await loop.run_in_executor(
                        None, lambda gn=r["gcs_name"]: _gcs.download_pdf(gn)
                    )
                    docs.append(RetrievedDoc(
                        gcs_name=r["gcs_name"], doc_name=r["doc_name"], industry=r["industry"],
                        market_scope=r["market_scope"], topics=r["topics"], forecasts=r["forecasts"],
                        local_path=local_path, score=r["score"],
                    ))
                except Exception as e:
                    logger.warning(f"Could not load {r['gcs_name']}: {e}")

            # Step 3: answer
            yield sse({"type": "answering"})
            result = await loop.run_in_executor(
                None, lambda: answer_question(question=req.question, docs=docs)
            )

            gcs_names = [d.gcs_name for d in docs]
            context_id = _make_context_id(gcs_names) if gcs_names else None
            if context_id and result.all_chunks:
                _cache_chunks(context_id, result.all_chunks)

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
                sources.append({"gcs_name": doc.gcs_name if doc else "", "name": name,
                                 "industry": doc.industry if doc else "",
                                 "topics": doc.topics[:4] if doc else [], "url": url})

            yield sse({"type": "answer", "answer": result.answer, "sources": sources, "context_id": context_id})

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/admin/upload-db")
async def upload_db(file: bytes = fastapi.Body(..., media_type="application/octet-stream")):
    """Upload a SQLite database file to replace the current one."""
    import shutil
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup = db_path.with_suffix(".db.bak")
    if db_path.exists():
        shutil.copy2(db_path, backup)
    db_path.write_bytes(file)
    return {"status": "ok", "bytes": len(file)}


# Parse state
_parse_status: dict = {"running": False, "done": 0, "failed": 0, "total": 0, "error": None}


@app.post("/api/admin/parse")
async def trigger_parse(background_tasks: BackgroundTasks):
    if _parse_status["running"]:
        return {"status": "already_running", **_parse_status}

    async def run_parse():
        import asyncio
        from src.parser.pipeline import parse_all
        from src.storage.gcs_client import GCSClient as _GCS
        from src.index.schema import get_connection

        _parse_status["running"] = True
        _parse_status["error"] = None
        try:
            gcs = _GCS()
            all_objects = gcs.list_pdfs()
            with get_connection() as conn:
                done_names = {
                    row[0] for row in conn.execute(
                        "SELECT gcs_name FROM documents WHERE parse_status='done'"
                    ).fetchall()
                }
            to_parse = [obj.name for obj in all_objects if obj.name not in done_names]
            _parse_status["total"] = len(to_parse)
            results = await parse_all(to_parse)
            _parse_status["done"] = results["success"]
            _parse_status["failed"] = results["failed"]
        except Exception as e:
            _parse_status["error"] = str(e)
        finally:
            _parse_status["running"] = False

    background_tasks.add_task(run_parse)
    return {"status": "started", "message": "Parsing started in background. Poll /api/parse-status to track progress."}


@app.get("/api/parse-status")
def parse_status():
    return _parse_status
