# api2/r2_utils.py
import boto3
from botocore.client import Config
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Inicializar cliente S3/R2
s3_client = boto3.client(
    "s3",
    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    config=Config(signature_version="s3v4"),
)

def upload_file_to_r2(file_obj, key, content_type=None):
    """Sube un archivo a R2 directamente"""
    try:
        s3_client.upload_fileobj(
            file_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            key,
            ExtraArgs={'ContentType': content_type or 'application/octet-stream'}
        )
        return True
    except Exception as e:
        logger.error(f"Error subiendo archivo a R2: {e}")
        return False

def delete_file_from_r2(key):
    """Elimina un archivo de R2"""
    try:
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key
        )
        return True
    except Exception as e:
        logger.error(f"Error eliminando archivo de R2: {e}")
        return False

def check_file_exists(key):
    """Verifica si un archivo existe en R2"""
    try:
        s3_client.head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key
        )
        return True
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise

def generate_presigned_url(key, expiration=3600):
    """Genera una URL temporal para un archivo en R2"""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': key
            },
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        logger.error(f"Error generando URL presigned: {e}")
        return None
# Añade esto al final de tu archivo api2/r2_utils.py

def check_r2_connection():
    """Verifica conexión a R2 para health check"""
    try:
        # Intenta una operación simple
        # Generar una URL de prueba
        test_url = generate_presigned_url("health_check_test.txt", expiration=60)
        
        if test_url:
            return {
                "status": "OK",
                "message": "R2 connection successful - URLs can be generated"
            }
        else:
            return {
                "status": "ERROR", 
                "message": "Failed to generate presigned URL"
            }
            
    except Exception as e:
        logger.error(f"R2 health check failed: {e}")
        return {
            "status": "ERROR",
            "message": f"R2 connection failed: {str(e)}"
        }