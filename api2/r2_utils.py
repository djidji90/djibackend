# api2/r2_utils.py - VERSIÓN COMPLETA CORREGIDA
import os
import mimetypes
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from .r2_client import r2_client, R2_BUCKET_NAME
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# =============================================================================
# ✅ FUNCIONES AUXILIARES
# =============================================================================

def validate_key(key):
    """Valida que la key no esté vacía"""
    if not key or not isinstance(key, str) or key.strip() == "":
        logger.warning("Key vacía o inválida proporcionada")
        return False
    return True

def get_content_type_from_key(key):
    """
    Determina el content type basado en la extensión del archivo.
    """
    if not key:
        return 'application/octet-stream'
    
    # Extraer extensión
    if '.' in key:
        extension = key.split('.')[-1].lower()
    else:
        return 'application/octet-stream'
    
    # Mapeo de extensiones a MIME types
    content_types = {
        'mp3': 'audio/mpeg',
        'wav': 'audio/wav',
        'ogg': 'audio/ogg',
        'webm': 'audio/webm',
        'flac': 'audio/flac',
        'm4a': 'audio/mp4',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'mp4': 'video/mp4',
        'pdf': 'application/pdf'
    }
    
    return content_types.get(extension, 'application/octet-stream')

# =============================================================================
# ✅ FUNCIONES PRINCIPALES
# =============================================================================

def upload_file_to_r2(file_obj, key, content_type=None):
    """Sube un archivo a R2 Cloudflare Storage."""
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
                    content_type = get_content_type_from_key(key)

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
    """Genera una URL temporal para acceder a un archivo privado en R2"""
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
    """Elimina un archivo de R2 Cloudflare Storage"""
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
    """Verifica si un archivo existe en R2"""
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
    """Obtiene el tamaño de un archivo en R2 (en bytes)"""
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
    """Obtiene información completa de un archivo en R2"""
    if not r2_client or not validate_key(key):
        return None

    try:
        response = r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return {
            'size': response['ContentLength'],
            'content_type': response.get('ContentType', get_content_type_from_key(key)),
            'last_modified': response.get('LastModified'),
            'etag': response.get('ETag')
        }
    except Exception as e:
        logger.error(f"Error obteniendo info de '{key}': {str(e)}")
        return None

def list_files(prefix=None, max_keys=1000):
    """Lista archivos en el bucket R2 (útil para debugging)"""
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

# =============================================================================
# ✅ STREAM FILE FROM R2 - VERSIÓN CORREGIDA
# =============================================================================

def stream_file_from_r2(key, start=None, end=None, range_header=None):
    """
    Stream eficiente desde R2 con soporte para Range requests.
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible para streaming")
        return None

    if not validate_key(key):
        logger.error(f"Key inválida para streaming: {key}")
        return None

    try:
        params = {'Bucket': R2_BUCKET_NAME, 'Key': key}

        # Construir Range header
        if range_header:
            params['Range'] = range_header
            logger.debug(f"Usando range_header proporcionado: {range_header}")
            
        elif start is not None or end is not None:
            # Construir range a partir de start/end
            if start is not None and end is not None:
                range_val = f"bytes={start}-{end}"
            elif start is not None:
                range_val = f"bytes={start}-"
            elif end is not None:
                range_val = f"bytes=-{end}"
            else:
                range_val = None
                
            if range_val:
                params['Range'] = range_val
                logger.debug(f"Range construido: {range_val}")

        logger.info(f"R2 Request - Key: {key}, Params: {params}")

        # Obtener objeto de R2
        response = r2_client.get_object(**params)
        
        # Extraer metadatos importantes
        result = {
            'Body': response['Body'],
            'ContentLength': response.get('ContentLength'),
            'ContentType': response.get('ContentType', get_content_type_from_key(key)),
            'ETag': response.get('ETag')
        }
        
        # Extraer ContentRange si existe
        if 'ContentRange' in response.get('ResponseMetadata', {}).get('HTTPHeaders', {}):
            result['ContentRange'] = response['ResponseMetadata']['HTTPHeaders']['ContentRange']
        
        logger.info(
            f"R2 Response - Key: {key} | "
            f"Size: {result['ContentLength']} | "
            f"Type: {result['ContentType']} | "
            f"Range: {params.get('Range', 'full')}"
        )
        
        return result

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        
        if error_code == 'NoSuchKey':
            logger.error(f"❌ Archivo no encontrado en R2: {key}")
        elif error_code == 'InvalidRange':
            logger.error(f"❌ Range inválido para {key}: {params.get('Range')}")
        elif error_code == 'AccessDenied':
            logger.error(f"❌ Acceso denegado a {key}")
        else:
            logger.error(f"❌ Error R2 [{error_code}]: {error_msg} para {key}")
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error inesperado streaming {key}: {str(e)}", exc_info=True)
        return None