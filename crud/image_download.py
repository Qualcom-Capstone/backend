import boto3
from botocore.exceptions import NoCredentialsError
from PIL import Image
import io

from backend.settings.base import (AWS_S3_REGION_NAME, AWS_ACCESS_KEY_ID,
                                   AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME)


def download_image_from_s3(file_key: str) -> Image.Image:
    s3 = boto3.client(
        's3',
        region_name=AWS_S3_REGION_NAME,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )

    try:
        response = s3.get_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=file_key)
        image_data = response['Body'].read()
        image = Image.open(io.BytesIO(image_data))
        return image

    except NoCredentialsError:
        raise Exception("AWS credentials not set properly")
    except s3.exceptions.NoSuchKey:
        raise Exception(f"File {file_key} does not exist in the bucket")
