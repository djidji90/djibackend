# test_fix.py
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

# Fuerza addressing_style='path' temporalmente
import boto3
from botocore.client import Config
from django.conf import settings

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    config=Config(
        signature_version="s3v4",
        s3={'addressing_style': 'path'}  # Forzar 'path'
    ),
)

# Generar URL
url = s3_client.generate_presigned_url(
    ClientMethod='put_object',
    Params={
        'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
        'Key': 'test/test.mp3'
    },
    ExpiresIn=3600,
    HttpMethod='PUT'
)

print(f"URL con 'path' addressing: {url}")