import boto3
from django.conf import settings

r2_client = boto3.client(
    's3',
    region_name='auto',  # Cloudflare R2 no requiere región específica
    endpoint_url=settings.R2_ENDPOINT_URL,
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY
)
