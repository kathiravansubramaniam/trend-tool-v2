import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from google.cloud import storage
from google.oauth2 import service_account

from config.settings import settings


@dataclass
class GCSObject:
    name: str
    md5_hash: str
    updated_at: datetime
    size: int


class GCSClient:
    def __init__(self):
        if settings.gcs_credentials_json:
            import json
            info = json.loads(settings.gcs_credentials_json)
            credentials = service_account.Credentials.from_service_account_info(info)
            self._client = storage.Client(
                project=settings.gcs_project_id,
                credentials=credentials,
            )
        elif settings.credentials_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(settings.credentials_path)
            )
            self._client = storage.Client(
                project=settings.gcs_project_id,
                credentials=credentials,
            )
        else:
            # Fall back to application default credentials (useful in Cloud Run)
            self._client = storage.Client(project=settings.gcs_project_id)

        self._bucket = self._client.bucket(settings.gcs_bucket_name)
        settings.pdf_cache_path.mkdir(parents=True, exist_ok=True)

    def list_pdfs(self) -> list[GCSObject]:
        blobs = self._client.list_blobs(settings.gcs_bucket_name)
        return [
            GCSObject(
                name=blob.name,
                md5_hash=blob.md5_hash or "",
                updated_at=blob.updated,
                size=blob.size or 0,
            )
            for blob in blobs
            if blob.name.lower().endswith(".pdf")
        ]

    def download_pdf(self, gcs_name: str) -> Path:
        safe_name = gcs_name.replace("/", "__")
        local_path = settings.pdf_cache_path / safe_name

        blob = self._bucket.blob(gcs_name)
        blob.reload()

        # Skip download if cached file matches remote MD5
        if local_path.exists():
            import base64
            import hashlib

            with open(local_path, "rb") as f:
                local_md5 = base64.b64encode(hashlib.md5(f.read()).digest()).decode()
            if local_md5 == (blob.md5_hash or ""):
                return local_path

        blob.download_to_filename(str(local_path))
        return local_path

    def get_signed_url(self, gcs_name: str, expiry_minutes: int = 60) -> str:
        blob = self._bucket.blob(gcs_name)
        return blob.generate_signed_url(
            expiration=timedelta(minutes=expiry_minutes),
            method="GET",
            version="v4",
        )

    def upload_pdf(self, local_path: Path, gcs_name: str) -> str:
        blob = self._bucket.blob(gcs_name)
        blob.upload_from_filename(
            str(local_path),
            content_type="application/pdf",
            timeout=300,  # 5 minutes for large files
        )
        return f"gs://{settings.gcs_bucket_name}/{gcs_name}"
