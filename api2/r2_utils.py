# api2/r2_utils.py - Versión CORREGIDA y mejorada
import os
import mimetypes
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from .r2_client import r2_client, R2_BUCKET_NAME
import logging

logger = logging.getLogger(__name__)

def validate_key(key):
    """Valida que la key no esté vacía"""
    if not key or not isinstance(key, str) or key.strip() == "":
        logger.warning("Key vacía o inválida proporcionada")
        return False
    return True

def upload_file_to_r2(file_obj, key, content_type=None):
    """
    Sube un archivo a R2 Cloudflare Storage.
    Acepta:
        - file_obj: ruta al archivo (str) o archivo abierto (file-like)
        - key: ruta destino en R2
        - content_type: opcional, MIME type
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return False

    if not validate_key(key):
        logger.error(f"Key inválida: {key}")
        return False

    try:
        # Determinar content_type si no se proporciona
        if not content_type:
            if hasattr(file_obj, 'content_type') and file_obj.content_type:
                content_type = file_obj.content_type
            else:
                if isinstance(file_obj, str):
                    content_type, _ = mimetypes.guess_type(file_obj)
                if not content_type:
                    content_type = 'application/octet-stream'

        extra_args = {'ACL': 'private', 'ContentType': content_type}

        # Si file_obj es una ruta de archivo
        if isinstance(file_obj, str):
            with open(file_obj, 'rb') as f:
                r2_client.upload_fileobj(Fileobj=f, Bucket=R2_BUCKET_NAME, Key=key, ExtraArgs=extra_args)

        # Si file_obj es un objeto tipo file
        elif hasattr(file_obj, 'read'):
            if hasattr(file_obj, 'seek'):
                try:
                    file_obj.seek(0)
                except ValueError:
                    # Archivo ya cerrado, intentar reabrir si tiene temporary_file_path
                    if hasattr(file_obj, 'temporary_file_path'):
                        with open(file_obj.temporary_file_path(), 'rb') as f:
                            r2_client.upload_fileobj(Fileobj=f, Bucket=R2_BUCKET_NAME, Key=key, ExtraArgs=extra_args)
                        return True
                    else:
                        logger.error(f"El archivo proporcionado está cerrado: {key}")
                        return False

            r2_client.upload_fileobj(Fileobj=file_obj, Bucket=R2_BUCKET_NAME, Key=key, ExtraArgs=extra_args)

        else:
            logger.error(f"Tipo de archivo no soportado: {type(file_obj)}")
            return False

        logger.info(f"Archivo subido exitosamente a R2: {key}")
        return True

    except Exception as e:
        logger.error(f"Error subiendo archivo '{key}' a R2: {str(e)}")
        return False

def generate_presigned_url(key, expiration=3600):
    """
    Genera una URL temporal para acceder a un archivo privado en R2
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return None

    if not validate_key(key):
        logger.error(f"Key inválida para URL presigned: {key}")
        return None

    try:
        url = r2_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET_NAME, 'Key': key},
            ExpiresIn=expiration
        )
        logger.info(f"URL presigned generada para: {key}")
        return url
    except Exception as e:
        logger.error(f"Error generando URL presigned para '{key}': {str(e)}")
        return None

def delete_file_from_r2(key):
    """
    Elimina un archivo de R2 Cloudflare Storage
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return False

    if not validate_key(key):
        logger.error(f"Key inválida para eliminación: {key}")
        return False

    try:
        r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        logger.info(f"Archivo eliminado de R2: {key}")
        return True
    except Exception as e:
        logger.error(f"Error eliminando archivo '{key}' de R2: {str(e)}")
        return False

def check_file_exists(key):
    """
    Verifica si un archivo existe en R2
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return False

    if not validate_key(key):
        return False

    try:
        r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        logger.debug(f"Archivo existe en R2: {key}")
        return True
    except Exception as e:
        logger.debug(f"Archivo no existe en R2: {key} - {str(e)}")
        return False

def get_file_size(key):
    """
    Obtiene el tamaño de un archivo en R2 (en bytes)
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return None

    if not validate_key(key):
        return None

    try:
        response = r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        size = response['ContentLength']
        logger.debug(f"Tamaño del archivo '{key}': {size} bytes")
        return size
    except Exception as e:
        logger.error(f"Error obteniendo tamaño de '{key}': {str(e)}")
        return None

def get_file_info(key):
    """
    Obtiene información completa de un archivo en R2
    """
    if not r2_client or not validate_key(key):
        return None

    try:
        response = r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return {
            'size': response['ContentLength'],
            'content_type': response.get('ContentType', 'unknown'),
            'last_modified': response.get('LastModified'),
            'etag': response.get('ETag')
        }
    except Exception as e:
        logger.error(f"Error obteniendo info de '{key}': {str(e)}")
        return None

def list_files(prefix=None, max_keys=1000):
    """
    Lista archivos en el bucket R2 (útil para debugging)
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return []

    try:
        params = {'Bucket': R2_BUCKET_NAME, 'MaxKeys': max_keys}
        if prefix:
            params['Prefix'] = prefix

        response = r2_client.list_objects_v2(**params)
        files = []

        if 'Contents' in response:
            for obj in response['Contents']:
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified']
                })

        logger.info(f"Listados {len(files)} archivos con prefijo: {prefix}")
        return files

    except Exception as e:
        logger.error(f"Error listando archivos: {str(e)}")
        return []
