"""
ChromaDB vector store for semantic search across documents.
Stores one embedding per document using OpenAI text-embedding-3-small.
Embeddings are generated from the document's metadata text
(doc_name + industry + topics + forecasts), which concisely represents
what each document is about.
"""
import json
import logging
from pathlib import Path

import chromadb
from openai import OpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
COLLECTION_NAME = "trend_documents"
CHROMA_PATH = "./data/chroma_db"


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hf:space": "cosine"},
    )


def _embed(text: str) -> list[float]:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def _doc_to_embed_text(
    doc_name: str,
    industry: str,
    market_scope: str,
    topics: list[str],
    forecasts: list[str],
) -> str:
    """Build a rich text representation of the document for embedding."""
    parts = [
        f"Title: {doc_name}",
        f"Industry: {industry}",
        f"Scope: {market_scope}",
        f"Topics: {', '.join(topics)}",
        f"Forecasts: {' | '.join(forecasts[:5])}",
    ]
    return "\n".join(parts)


def upsert_embedding(
    gcs_name: str,
    doc_name: str,
    industry: str,
    market_scope: str,
    topics: list[str],
    forecasts: list[str],
) -> None:
    embed_text = _doc_to_embed_text(doc_name, industry, market_scope, topics, forecasts)
    embedding = _embed(embed_text)

    collection = _get_collection()
    collection.upsert(
        ids=[gcs_name],
        embeddings=[embedding],
        metadatas=[{
            "gcs_name": gcs_name,
            "doc_name": doc_name,
            "industry": industry,
            "market_scope": market_scope,
            "topics": json.dumps(topics),
            "forecasts": json.dumps(forecasts[:5]),
        }],
        documents=[embed_text],
    )
    logger.debug(f"Stored embedding for: {gcs_name}")


def semantic_search(
    query: str,
    n_results: int = 10,
    industry_filter: str | None = None,
) -> list[dict]:
    """
    Embed the query and return the most semantically similar documents.
    Returns list of dicts with gcs_name, doc_name, industry, topics, forecasts, distance.
    """
    collection = _get_collection()

    if collection.count() == 0:
        logger.warning("Vector store is empty — no embeddings yet")
        return []

    query_embedding = _embed(query)

    where = None
    if industry_filter and industry_filter.lower() not in ("all", "any", ""):
        # ChromaDB doesn't support LIKE, so we skip the filter here and
        # post-filter below — the semantic search will surface relevant docs anyway
        pass

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["metadatas", "distances"],
    )

    docs = []
    for metadata, distance in zip(
        results["metadatas"][0], results["distances"][0]
    ):
        if industry_filter and industry_filter.lower() not in ("all", "any", ""):
            if industry_filter.lower() not in metadata.get("industry", "").lower():
                continue
        docs.append({
            "gcs_name": metadata["gcs_name"],
            "doc_name": metadata["doc_name"],
            "industry": metadata["industry"],
            "market_scope": metadata["market_scope"],
            "topics": json.loads(metadata.get("topics", "[]")),
            "forecasts": json.loads(metadata.get("forecasts", "[]")),
            "distance": distance,
        })

    return docs


def get_vector_count() -> int:
    return _get_collection().count()
