"""
Chunk-level indexing pipeline.

For each document:
1. Extract section-aware chunks from the cached PDF
2. Generate LLM metadata for each chunk (batched)
3. Write chunks to SQLite
4. Upsert chunk embeddings to ChromaDB
"""

import asyncio
import logging
from pathlib import Path

from config.settings import settings
from src.index.chunk_reader import get_chunks_for_doc
from src.index.chunk_schema import get_chunk_count, init_chunks_db
from src.index.chunk_vector_store import upsert_chunk_embeddings
from src.index.chunk_writer import upsert_chunks
from src.index.reader import get_all_done
from src.parser.chunk_extractor import chunk_pdf
from src.parser.chunk_metadata_extractor import extract_chunk_metadata
from src.storage.gcs_client import GCSClient

logger = logging.getLogger(__name__)
gcs_client = GCSClient()


async def chunk_one(gcs_name: str, semaphore: asyncio.Semaphore) -> bool:
    """
    Chunk a single document: extract → generate metadata → write to DB → embed.
    Returns True on success, False on failure.
    """
    async with semaphore:
        logger.info(f"Chunking: {gcs_name}")
        try:
            # 1. Download PDF (uses local cache if available)
            local_path: Path = await asyncio.to_thread(gcs_client.download_pdf, gcs_name)

            # 2. Section-aware chunking
            segments = await asyncio.to_thread(chunk_pdf, local_path)
            if not segments:
                logger.warning(f"No chunks extracted from {gcs_name} — skipping")
                return False

            # 3. LLM metadata extraction (batched)
            chunk_inputs = [(seg.section_title, seg.text) for seg in segments]
            metadata = await asyncio.to_thread(extract_chunk_metadata, chunk_inputs)

            # 4. Write to SQLite (gcs_name is enough; doc_name comes from JOIN)
            await asyncio.to_thread(upsert_chunks, gcs_name, gcs_name, segments, metadata)

            # 5. Build ChunkResult objects for embedding (fetch from DB to get doc_name)
            chunk_results = await asyncio.to_thread(get_chunks_for_doc, gcs_name)

            # 6. Embed chunks
            await asyncio.to_thread(upsert_chunk_embeddings, chunk_results)

            logger.info(f"Done chunking: {gcs_name} → {len(segments)} chunks")
            return True

        except Exception as e:
            logger.error(f"Chunk failed: {gcs_name}: {e}")
            return False


async def chunk_all(
    gcs_names: list[str],
    concurrency: int | None = None,
) -> dict:
    """
    Chunk multiple documents concurrently.
    Returns {total, success, failed}.
    """
    if concurrency is None:
        concurrency = settings.max_concurrent_parses

    # Ensure chunk tables exist
    init_chunks_db()

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [chunk_one(name, semaphore) for name in gcs_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if r is True)
    failed = len(results) - success
    return {"total": len(results), "success": success, "failed": failed}


def get_unchunked_gcs_names() -> list[str]:
    """Return gcs_names of done documents that haven't been chunked yet."""
    from src.index.chunk_reader import get_chunked_gcs_names
    done_docs = {r.gcs_name for r in get_all_done(limit=10000)}
    already_chunked = get_chunked_gcs_names()
    return sorted(done_docs - already_chunked)
