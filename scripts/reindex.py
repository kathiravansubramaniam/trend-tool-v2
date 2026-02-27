"""
Re-parse specific documents or all failed ones.
Usage:
  python scripts/reindex.py --failed-only
  python scripts/reindex.py --all
  python scripts/reindex.py --name "path/to/file.pdf"
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index.schema import get_connection
from src.parser.pipeline import parse_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    args = sys.argv[1:]

    if "--failed-only" in args:
        with get_connection() as conn:
            names = [
                row[0]
                for row in conn.execute(
                    "SELECT gcs_name FROM documents WHERE parse_status='failed'"
                ).fetchall()
            ]
        logger.info(f"Re-parsing {len(names)} failed documents")

    elif "--all" in args:
        with get_connection() as conn:
            names = [
                row[0]
                for row in conn.execute("SELECT gcs_name FROM documents").fetchall()
            ]
        logger.info(f"Re-parsing all {len(names)} documents")

    elif "--name" in args:
        idx = args.index("--name")
        names = [args[idx + 1]]
        logger.info(f"Re-parsing: {names[0]}")

    else:
        print(__doc__)
        sys.exit(1)

    if not names:
        logger.info("No documents to re-parse.")
        return

    results = await parse_all(names)
    logger.info(f"Done: {results['success']} succeeded, {results['failed']} failed")


if __name__ == "__main__":
    asyncio.run(main())
