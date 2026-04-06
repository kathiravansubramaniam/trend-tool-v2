"""
ChromaDB vector store for chunk-level semantic search.

Each chunk gets its own embedding, built from:
  section_title + chunk_summary + retrieval_phrases + first 500 chars of chunk_text

This collection is separate from the document-level "trend_documents" collection.
"""

import json
import logging

import chromadb
from openai import OpenAI

from config.settings import settings
from src.index.chunk_reader import ChunkResult

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_COLLECTION = "trend_chunks"
CHROMA_PATH = "./data/chroma_db"

# Max chunks per document to store in the vector store
# (avoids overly long docs dominating results)
MAX_CHUNKS_PER_DOC = 120


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=CHUNK_COLLECTION,
        metadata={"hf:space": "cosine"},
    )


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts in a single API call (max 2048 inputs)."""
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def _chunk_to_embed_text(chunk: ChunkResult) -> str:
    """Build the text we embed for a chunk — rich signal, not just raw text."""
    parts: list[str] = []
    if chunk.section_title:
        parts.append(f"Section: {chunk.section_title}")
    if chunk.chunk_summary:
        parts.append(f"Summary: {chunk.chunk_summary}")
    if chunk.retrieval_phrases:
        parts.append(f"Key phrases: {', '.join(chunk.retrieval_phrases)}")
    if chunk.topics:
        parts.append(f"Topics: {', '.join(chunk.topics[:4])}")
    parts.append(chunk.chunk_text[:500])
    return "\n".join(parts)


def upsert_chunk_embeddings(chunks: list[ChunkResult]) -> None:
    """
    Upsert embeddings for a list of chunks.
    Processes in batches of 100 for the embedding API.
    """
    if not chunks:
        return

    chunks = chunks[:MAX_CHUNKS_PER_DOC]
    collection = _get_collection()
    EMBED_BATCH = 100

    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        texts = [_chunk_to_embed_text(c) for c in batch]

        try:
            embeddings = _embed_batch(texts)
        except Exception as e:
            logger.warning(f"Embedding batch {i // EMBED_BATCH} failed: {e}")
            continue

        collection.upsert(
            ids=[c.chunk_id for c in batch],
            embeddings=embeddings,
            metadatas=[
                {
                    "chunk_id":    c.chunk_id,
                    "gcs_name":    c.gcs_name,
                    "doc_name":    c.doc_name,
                    "chunk_order": c.chunk_order,
                    "section_title": c.section_title[:200] if c.section_title else "",
                    "evidence_strength": c.evidence_strength,
                }
                for c in batch
            ],
            documents=texts,
        )

    logger.debug(f"Upserted {len(chunks)} chunk embeddings for {chunks[0].gcs_name}")


def delete_chunk_embeddings(gcs_name: str) -> None:
    """Remove all chunk embeddings for a document."""
    collection = _get_collection()
    try:
        collection.delete(where={"gcs_name": gcs_name})
    except Exception as e:
        logger.warning(f"Could not delete chunk embeddings for {gcs_name}: {e}")


def semantic_search_chunks(
    query: str,
    n_results: int = 50,
    gcs_name_filter: str | None = None,
) -> list[dict]:
    """
    Search for the most semantically similar chunks to the query.
    Returns list of {chunk_id, gcs_name, doc_name, section_title, distance}.
    """
    collection = _get_collection()
    if collection.count() == 0:
        return []

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=query)
    query_embedding = resp.data[0].embedding

    where = {"gcs_name": gcs_name_filter} if gcs_name_filter else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["metadatas", "distances"],
        where=where,
    )

    output = []
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        output.append({
            "chunk_id":      meta["chunk_id"],
            "gcs_name":      meta["gcs_name"],
            "doc_name":      meta["doc_name"],
            "section_title": meta.get("section_title", ""),
            "distance":      dist,
        })
    return output


def get_chunk_vector_count() -> int:
    return _get_collection().count()
