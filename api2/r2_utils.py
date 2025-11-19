# api2/r2_utils.py
from .r2_client import r2_client, R2_BUCKET_NAME

def upload_file_to_r2(file_obj, key):
    """
    Sube un archivo a R2 Cloudflare Storage
    """
    try:
        r2_client.upload_fileobj(
            Fileobj=file_obj,
            Bucket=R2_BUCKET_NAME,
            Key=key,
            ExtraArgs={'ACL': 'private'}  # archivos privados, solo accesibles con URL temporal
        )
        return True
    except Exception as e:
        print(f"Error uploading to R2: {e}")
        return False

def generate_presigned_url(key, expiration=3600):
    """
    Genera una URL temporal para acceder a un archivo privado en R2
    """
    try:
        return r2_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET_NAME, 'Key': key},
            ExpiresIn=expiration
        )
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None

def delete_file_from_r2(key):
    """
    Elimina un archivo de R2 Cloudflare Storage
    """
    try:
        r2_client.delete_object(
            Bucket=R2_BUCKET_NAME,
            Key=key
        )
        return True
    except Exception as e:
        print(f"Error deleting from R2: {e}")
        return False

def check_file_exists(key):
    """
    Verifica si un archivo existe en R2
    """
    try:
        r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except:
        return False