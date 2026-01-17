from google.cloud import storage
from google.cloud.exceptions import NotFound
from PIL import Image
import io
import os

from config.settings.base import GCS_BUCKET_NAME


def download_image_from_gcs(blob_name: str) -> Image.Image:
    """
    GCS(Google Cloud Storage)에서 이미지를 다운로드하여 PIL Image 객체로 반환합니다.
    
    Args:
        blob_name (str): GCS 버킷 내 객체의 이름 (경로 포함)
        
    Returns:
        Image.Image: PIL Image 객체
        
    Raises:
        Exception: 인증 실패, 파일 없음 등의 오류 발생 시
    """
    try:
        # GCS 클라이언트 생성 (환경 변수 GOOGLE_APPLICATION_CREDENTIALS 사용)
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        # 이미지 데이터 다운로드
        image_data = blob.download_as_bytes()
        image = Image.open(io.BytesIO(image_data))
        
        return image
        
    except NotFound:
        raise Exception(f"File {blob_name} does not exist in bucket {GCS_BUCKET_NAME}")
    except Exception as e:
        raise Exception(f"Failed to download image from GCS: {str(e)}")


# 하위 호환성을 위한 별칭 (기존 코드에서 사용 중인 함수명)
download_image_from_s3 = download_image_from_gcs
