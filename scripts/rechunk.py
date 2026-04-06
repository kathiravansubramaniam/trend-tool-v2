#!/usr/bin/env python3
"""
Re-chunk all (or specific) documents.

Usage:
    python3 scripts/rechunk.py              # chunk all unchunked docs
    python3 scripts/rechunk.py --all        # re-chunk all docs (overwrite existing)
    python3 scripts/rechunk.py --name foo.pdf
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

import argparse

from src.index.chunk_schema import init_chunks_db
from src.index.reader import get_all_done
from src.parser.chunk_pipeline import chunk_all, get_unchunked_gcs_names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",  action="store_true", help="Re-chunk all done documents")
    parser.add_argument("--name", type=str,            help="Re-chunk a specific document by gcs_name")
    args = parser.parse_args()

    init_chunks_db()

    if args.name:
        gcs_names = [args.name]
    elif args.all:
        gcs_names = [r.gcs_name for r in get_all_done(limit=10000)]
    else:
        gcs_names = get_unchunked_gcs_names()

    if not gcs_names:
        print("Nothing to chunk.")
        return

    print(f"Chunking {len(gcs_names)} documents...")
    results = asyncio.run(chunk_all(gcs_names))
    print(f"Done: {results['success']} succeeded, {results['failed']} failed")


if __name__ == "__main__":
    main()
