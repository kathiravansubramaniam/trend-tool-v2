"""
Unzips a local zip file and uploads all PDFs to the configured GCS bucket.

Usage:
  python3 scripts/upload_from_zip.py /path/to/your/file.zip

Optional: upload to a subfolder in the bucket:
  python3 scripts/upload_from_zip.py /path/to/file.zip --prefix reports/
"""
import sys
import zipfile
import tempfile
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print(__doc__)
        sys.exit(1)

    zip_path = Path(args[0]).expanduser().resolve()
    prefix = ""
    if "--prefix" in args:
        idx = args.index("--prefix")
        prefix = args[idx + 1].strip("/") + "/"

    if not zip_path.exists():
        logger.error(f"Zip file not found: {zip_path}")
        sys.exit(1)

    if not zipfile.is_zipfile(zip_path):
        logger.error(f"Not a valid zip file: {zip_path}")
        sys.exit(1)

    from src.storage.gcs_client import GCSClient
    from config.settings import settings

    gcs_client = GCSClient()
    logger.info(f"Target bucket: gs://{settings.gcs_bucket_name}/{prefix or ''}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        logger.info(f"Unzipping {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # Find all PDFs recursively, skip macOS metadata files
        pdfs = [
            p for p in tmp.rglob("*.pdf")
            if not any(part.startswith("__MACOSX") or part.startswith("._")
                       for part in p.parts)
        ]

        if not pdfs:
            logger.error("No PDF files found inside the zip.")
            sys.exit(1)

        logger.info(f"Found {len(pdfs)} PDF(s) to upload")

        uploaded = 0
        failed = 0
        for pdf_path in sorted(pdfs):
            gcs_name = prefix + pdf_path.name
            try:
                uri = gcs_client.upload_pdf(pdf_path, gcs_name)
                logger.info(f"  Uploaded: {gcs_name}")
                uploaded += 1
            except Exception as e:
                logger.error(f"  Failed: {pdf_path.name}: {e}")
                failed += 1

        logger.info(
            f"\nDone: {uploaded} uploaded, {failed} failed"
        )
        if uploaded > 0:
            logger.info(
                f"\nNext step: run `make parse` to index all documents."
            )


if __name__ == "__main__":
    main()
