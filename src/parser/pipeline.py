import asyncio
import logging
from pathlib import Path

from config.settings import settings
from src.index.vector_store import upsert_embedding
from src.index.writer import mark_failed, mark_pending, upsert_document
from src.parser.metadata_extractor import extract_metadata
from src.parser.pdf_extractor import extract_text
from src.storage.gcs_client import GCSClient
from src.utils.token_counter import count_tokens

logger = logging.getLogger(__name__)
gcs_client = GCSClient()


async def parse_one(gcs_name: str, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        logger.info(f"Parsing: {gcs_name}")
        mark_pending(gcs_name)
        try:
            local_path: Path = await asyncio.to_thread(gcs_client.download_pdf, gcs_name)
            text = await asyncio.to_thread(extract_text, local_path)
            token_count = count_tokens(text, settings.parse_model)
            metadata = await asyncio.to_thread(extract_metadata, text, gcs_name)
            upsert_document(
                gcs_name=gcs_name,
                doc_name=metadata.doc_name,
                industry=metadata.industry,
                market_scope=metadata.market_scope,
                topics=metadata.topics,
                forecasts=metadata.forecasts,
                token_count=token_count,
            )
            await asyncio.to_thread(
                upsert_embedding,
                gcs_name,
                metadata.doc_name,
                metadata.industry,
                metadata.market_scope,
                metadata.topics,
                metadata.forecasts,
            )
            logger.info(f"Done: {gcs_name} -> {metadata.industry} / {metadata.doc_name}")
            return True
        except Exception as e:
            logger.error(f"Failed: {gcs_name}: {e}")
            mark_failed(gcs_name, str(e))
            return False


async def parse_all(gcs_names: list[str]) -> dict:
    semaphore = asyncio.Semaphore(settings.max_concurrent_parses)
    tasks = [parse_one(name, semaphore) for name in gcs_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if r is True)
    failed = len(results) - success
    return {"total": len(results), "success": success, "failed": failed}
