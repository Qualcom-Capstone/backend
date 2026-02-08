"""Google Cloud Storage Client"""

import logging
import os
from typing import Optional

from google.cloud import storage

logger = logging.getLogger(__name__)


class GCSClient:
    """GCS 클라이언트 래퍼"""

    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def client(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def get_bucket(self, bucket_name: Optional[str] = None) -> storage.Bucket:
        """버킷 가져오기"""
        bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME is not set")
        return self.client.bucket(bucket_name)

    def download_as_bytes(self, gcs_uri: str) -> bytes:
        """GCS URI에서 파일 다운로드"""
        # gs://bucket-name/path/to/file.jpg
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_path = parts[1] if len(parts) > 1 else ""

        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        logger.debug(f"Downloading from GCS: {gcs_uri}")
        return blob.download_as_bytes()

    def upload_from_bytes(
        self,
        data: bytes,
        blob_path: str,
        bucket_name: Optional[str] = None,
        content_type: str = "image/jpeg",
    ) -> str:
        """바이트 데이터를 GCS에 업로드"""
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(data, content_type=content_type)

        gcs_uri = f"gs://{bucket.name}/{blob_path}"
        logger.debug(f"Uploaded to GCS: {gcs_uri}")
        return gcs_uri

    def get_signed_url(
        self, blob_path: str, bucket_name: Optional[str] = None, expiration: int = 3600
    ) -> str:
        """Signed URL 생성"""
        from datetime import timedelta

        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_path)

        url = blob.generate_signed_url(
            expiration=timedelta(seconds=expiration), method="GET"
        )
        return url


# 편의 함수
_gcs_client = None


def get_gcs_client() -> GCSClient:
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = GCSClient()
    return _gcs_client


def download_image(gcs_uri: str) -> bytes:
    """GCS에서 이미지 다운로드"""
    return get_gcs_client().download_as_bytes(gcs_uri)


def upload_image(data: bytes, blob_path: str) -> str:
    """이미지를 GCS에 업로드"""
    return get_gcs_client().upload_from_bytes(data, blob_path)
