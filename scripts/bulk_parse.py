"""
One-time script to parse all PDFs in the GCS bucket.
Skips documents that already have parse_status='done'.
Run with: python scripts/bulk_parse.py [--force]
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index.reader import get_index_stats
from src.index.schema import init_db
from src.parser.pipeline import parse_all
from src.storage.gcs_client import GCSClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    force = "--force" in sys.argv

    logger.info("Initializing database...")
    init_db()

    logger.info("Listing PDFs in GCS bucket...")
    gcs_client = GCSClient()
    all_objects = gcs_client.list_pdfs()
    logger.info(f"Found {len(all_objects)} PDFs in bucket")

    if not all_objects:
        logger.warning("No PDFs found in bucket. Check your GCS_BUCKET_NAME setting.")
        return

    from src.index.schema import get_connection

    if force:
        to_parse = [obj.name for obj in all_objects]
        logger.info(f"--force flag set: re-parsing all {len(to_parse)} documents")
    else:
        with get_connection() as conn:
            done_names = {
                row[0]
                for row in conn.execute(
                    "SELECT gcs_name FROM documents WHERE parse_status='done'"
                ).fetchall()
            }
        to_parse = [obj.name for obj in all_objects if obj.name not in done_names]
        skipped = len(all_objects) - len(to_parse)
        logger.info(f"Skipping {skipped} already-parsed documents")
        logger.info(f"Parsing {len(to_parse)} new/pending documents")

    if not to_parse:
        logger.info("Nothing to parse. All documents are up to date.")
        stats = get_index_stats()
        logger.info(f"Index stats: {stats}")
        return

    results = await parse_all(to_parse)
    logger.info(
        f"\nParsing complete: {results['success']} succeeded, {results['failed']} failed "
        f"out of {results['total']} total"
    )
    stats = get_index_stats()
    logger.info(
        f"Index now has {stats['done']} indexed documents across {stats['industries']} industries"
    )


if __name__ == "__main__":
    asyncio.run(main())
