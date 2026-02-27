"""
GCP Cloud Run Function (gen2) entry point.
Triggered by GCS Pub/Sub OBJECT_FINALIZE events.

Deploy with:
  gcloud functions deploy trend-parser \
    --gen2 \
    --runtime python312 \
    --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
    --trigger-event-filters="bucket=YOUR_BUCKET_NAME" \
    --entry-point=on_gcs_upload \
    --source=. \
    --region=us-central1
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def on_gcs_upload(cloud_event) -> None:
    try:
        import functions_framework  # noqa - only available in Cloud Run env
    except ImportError:
        raise RuntimeError("functions_framework not installed. This runs only in Cloud Run.")

    data = cloud_event.data
    gcs_name: str = data.get("name", "")

    if not gcs_name.lower().endswith(".pdf"):
        logger.info(f"Skipping non-PDF file: {gcs_name}")
        return

    logger.info(f"Processing new upload: {gcs_name}")

    from src.index.schema import init_db
    from src.parser.pipeline import parse_one

    init_db()
    semaphore = asyncio.Semaphore(1)
    asyncio.run(parse_one(gcs_name, semaphore))
    logger.info(f"Successfully processed: {gcs_name}")
