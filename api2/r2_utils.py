import os
import logging
from io import BytesIO
from botocore.exceptions import ClientError

# Importar configuración R2 desde r2_client
from .r2_client import r2_client, R2_BUCKET_NAME

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
    """Determina el content type basado en la extensión"""
    if not key:
        return 'application/octet-stream'
    
    if '.' in key:
        extension = key.split('.')[-1].lower()
    else:
        return 'application/octet-stream'
    
    content_types = {
        # Audio
        'mp3': 'audio/mpeg',
        'wav': 'audio/wav',
        'ogg': 'audio/ogg',
        'webm': 'audio/webm',
        'flac': 'audio/flac',
        'm4a': 'audio/mp4',
        'aac': 'audio/aac',
        'opus': 'audio/opus',
        
        # Imágenes
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'svg': 'image/svg+xml',
        
        # Video
        'mp4': 'video/mp4',
        'webm': 'video/webm',
        
        # Documentos
        'pdf': 'application/pdf',
        'txt': 'text/plain',
    }
    
    return content_types.get(extension, 'application/octet-stream')


def upload_file_to_r2(file_obj, key, content_type=None):
    """
    Sube un archivo a R2 Cloudflare Storage - VERSIÓN SIMPLE Y FUNCIONAL
    
    Args:
        file_obj: Objeto archivo (UploadedFile, BytesIO, o ruta string)
        key: Clave única en R2 (ej: 'songs/audio/uuid.mp3')
        content_type: Tipo MIME (opcional, se deduce si no se proporciona)
    
    Returns:
        bool: True si se subió correctamente, False si hubo error
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
                content_type = get_content_type_from_key(key)
        
        # Asegurar content_type válido
        if not content_type:
            content_type = 'application/octet-stream'

        # Configuración para R2
        extra_args = {'ContentType': content_type}

        # 1. Si file_obj es una ruta de archivo (string)
        if isinstance(file_obj, str):
            logger.info(f"Subiendo desde ruta: {file_obj} -> {key}")
            with open(file_obj, 'rb') as f:
                r2_client.upload_fileobj(
                    Fileobj=f,
                    Bucket=R2_BUCKET_NAME,
                    Key=key,
                    ExtraArgs=extra_args
                )
        
        # 2. Si file_obj es un objeto UploadedFile de Django
        elif hasattr(file_obj, 'read'):
            # Asegurarse de que estamos al inicio del archivo
            if hasattr(file_obj, 'seek'):
                try:
                    file_obj.seek(0)
                except (AttributeError, ValueError) as e:
                    logger.warning(f"No se pudo seek en el archivo: {e}")
                    
                    # Si falla seek, manejar diferentes tipos de UploadedFile
                    if hasattr(file_obj, 'file'):
                        # InMemoryUploadedFile
                        file_content = file_obj.file.read()
                        file_obj = BytesIO(file_content)
                        file_obj.seek(0)
                    elif hasattr(file_obj, 'temporary_file_path'):
                        # TemporaryUploadedFile
                        logger.info(f"Subiendo desde archivo temporal: {key}")
                        with open(file_obj.temporary_file_path(), 'rb') as f:
                            r2_client.upload_fileobj(
                                Fileobj=f,
                                Bucket=R2_BUCKET_NAME,
                                Key=key,
                                ExtraArgs=extra_args
                            )
                        logger.info(f"Archivo subido desde temp path: {key}")
                        return True
                    else:
                        logger.error("No se puede procesar el archivo")
                        return False
            
            # Subir el archivo
            logger.info(f"Subiendo archivo: {key}")
            r2_client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=R2_BUCKET_NAME,
                Key=key,
                ExtraArgs=extra_args
            )
        
        # 3. Si file_obj es BytesIO o similar
        elif isinstance(file_obj, BytesIO):
            file_obj.seek(0)
            r2_client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=R2_BUCKET_NAME,
                Key=key,
                ExtraArgs=extra_args
            )
        
        else:
            logger.error(f"Tipo de archivo no soportado: {type(file_obj)}")
            return False

        logger.info(f"Archivo subido exitosamente a R2: {key}")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] subiendo '{key}': {error_msg}")
        return False
        
    except Exception as e:
        logger.error(f"Error inesperado subiendo archivo '{key}' a R2: {str(e)}", exc_info=True)
        return False


def generate_presigned_url(key, expiration=3600):
    """
    Genera una URL temporal para acceder a un archivo privado en R2
    
    Args:
        key: Clave del archivo en R2
        expiration: Tiempo en segundos que la URL será válida (default: 1 hora)
    
    Returns:
        str: URL firmada o None si hay error
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
        logger.info(f"URL presigned generada para: {key} (expira en {expiration}s)")
        return url
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] generando URL para '{key}': {error_msg}")
        return None
        
    except Exception as e:
        logger.error(f"Error generando URL presigned para '{key}': {str(e)}")
        return None


def delete_file_from_r2(key):
    """
    Elimina un archivo de R2 Cloudflare Storage
    
    Args:
        key: Clave del archivo a eliminar
    
    Returns:
        bool: True si se eliminó correctamente, False si hubo error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return False

    if not validate_key(key):
        logger.error(f"Key inválida para eliminación: {key}")
        return False

    try:
        # Primero verificar si existe
        try:
            r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.info(f"Archivo no encontrado en R2 (ya eliminado?): {key}")
                return True
            else:
                raise
        
        # Eliminar el archivo
        r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        logger.info(f"Archivo eliminado de R2: {key}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] eliminando '{key}': {error_msg}")
        return False
        
    except Exception as e:
        logger.error(f"Error eliminando archivo '{key}' de R2: {str(e)}")
        return False


def check_file_exists(key):
    """
    Verifica si un archivo existe en R2
    
    Args:
        key: Clave del archivo a verificar
    
    Returns:
        bool: True si existe, False si no existe o hay error
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
        
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.debug(f"Archivo no encontrado en R2: {key}")
            return False
        else:
            logger.warning(f"Error verificando archivo '{key}': {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error inesperado verificando '{key}': {e}")
        return False


def get_file_size(key):
    """
    Obtiene el tamaño de un archivo en R2 (en bytes)
    
    Args:
        key: Clave del archivo
    
    Returns:
        int: Tamaño en bytes, o None si hay error
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
        
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.debug(f"Archivo no encontrado al obtener tamaño: {key}")
            return None
        else:
            logger.error(f"Error obteniendo tamaño de '{key}': {e}")
            return None
            
    except Exception as e:
        logger.error(f"Error obteniendo tamaño de '{key}': {str(e)}")
        return None


def get_file_info(key):
    """
    Obtiene información completa de un archivo en R2
    
    Args:
        key: Clave del archivo
    
    Returns:
        dict: Información del archivo o None si hay error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return None

    if not validate_key(key):
        return None

    try:
        response = r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        
        info = {
            'size': response['ContentLength'],
            'content_type': response.get('ContentType', get_content_type_from_key(key)),
            'last_modified': response.get('LastModified'),
            'etag': response.get('ETag'),
            'metadata': response.get('Metadata', {})
        }
        
        logger.debug(f"Información obtenida para '{key}': {info}")
        return info
        
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.debug(f"Archivo no encontrado al obtener info: {key}")
            return None
        else:
            logger.error(f"Error obteniendo info de '{key}': {e}")
            return None
            
    except Exception as e:
        logger.error(f"Error obteniendo info de '{key}': {str(e)}")
        return None


def list_files(prefix=None, max_keys=1000):
    """
    Lista archivos en el bucket R2
    
    Args:
        prefix: Prefijo para filtrar (ej: 'songs/audio/')
        max_keys: Máximo número de archivos a listar
    
    Returns:
        list: Lista de diccionarios con información de archivos
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
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag']
                })

        logger.info(f"Listados {len(files)} archivos con prefijo: {prefix or 'ninguno'}")
        return files

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] listando archivos: {error_msg}")
        return []
        
    except Exception as e:
        logger.error(f"Error listando archivos: {str(e)}")
        return []


def copy_file_in_r2(source_key, destination_key):
    """
    Copia un archivo dentro de R2
    
    Args:
        source_key: Clave del archivo origen
        destination_key: Clave del archivo destino
    
    Returns:
        bool: True si se copió correctamente, False si hubo error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return False

    if not validate_key(source_key) or not validate_key(destination_key):
        logger.error("Claves inválidas para copia")
        return False

    try:
        copy_source = {'Bucket': R2_BUCKET_NAME, 'Key': source_key}
        r2_client.copy_object(
            Bucket=R2_BUCKET_NAME,
            CopySource=copy_source,
            Key=destination_key
        )
        
        logger.info(f"Archivo copiado: {source_key} -> {destination_key}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] copiando {source_key} a {destination_key}: {error_msg}")
        return False
        
    except Exception as e:
        logger.error(f"Error copiando {source_key} a {destination_key}: {e}")
        return False


# =============================================================================
# ✅ STREAM FILE FROM R2 - VERSIÓN OPTIMIZADA
# =============================================================================

def stream_file_from_r2(key, start=None, end=None, range_header=None):
    """
    Stream eficiente desde R2 con soporte para Range requests
    
    Args:
        key: Clave del archivo
        start: Byte inicial (opcional)
        end: Byte final (opcional)
        range_header: Header Range completo (ej: 'bytes=0-1000')
    
    Returns:
        dict: Información del stream o None si hay error
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

        logger.debug(f"R2 Request - Key: {key}, Range: {params.get('Range', 'full')}")

        # Obtener objeto de R2
        response = r2_client.get_object(**params)
        
        # Extraer metadatos importantes
        result = {
            'Body': response['Body'],
            'ContentLength': response.get('ContentLength'),
            'ContentType': response.get('ContentType', get_content_type_from_key(key)),
            'ETag': response.get('ETag'),
            'LastModified': response.get('LastModified'),
            'Metadata': response.get('Metadata', {})
        }
        
        # Extraer ContentRange si existe
        if 'ContentRange' in response.get('ResponseMetadata', {}).get('HTTPHeaders', {}):
            result['ContentRange'] = response['ResponseMetadata']['HTTPHeaders']['ContentRange']
        
        logger.info(
            f"R2 Response - Key: {key} | "
            f"Size: {result['ContentLength']} | "
            f"Type: {result['ContentType']}"
        )
        
        return result

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        
        if error_code == 'NoSuchKey':
            logger.error(f"Archivo no encontrado en R2: {key}")
        elif error_code == 'InvalidRange':
            logger.error(f"Range inválido para {key}: {params.get('Range')}")
        elif error_code == 'AccessDenied':
            logger.error(f"Acceso denegado a {key}")
        else:
            logger.error(f"Error R2 [{error_code}] streaming {key}: {error_msg}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error inesperado streaming {key}: {str(e)}", exc_info=True)
        return None


# =============================================================================
# ✅ FUNCIONES DE DIAGNÓSTICO
# =============================================================================

def test_r2_connection():
    """
    Prueba la conexión a R2
    
    Returns:
        dict: Resultado de la prueba de conexión
    """
    if not r2_client:
        return {'success': False, 'error': 'Cliente R2 no inicializado'}
    
    try:
        # Probar conexión listando buckets
        response = r2_client.list_buckets()
        buckets = [b['Name'] for b in response.get('Buckets', [])]
        
        # Verificar nuestro bucket
        bucket_exists = R2_BUCKET_NAME in buckets
        
        return {
            'success': True,
            'buckets': buckets,
            'target_bucket': R2_BUCKET_NAME,
            'bucket_exists': bucket_exists,
            'bucket_count': len(buckets)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'target_bucket': R2_BUCKET_NAME
        }


def get_r2_stats():
    """
    Obtiene estadísticas del bucket R2
    
    Returns:
        dict: Estadísticas del bucket
    """
    if not r2_client:
        return {'error': 'Cliente R2 no disponible'}
    
    try:
        # Listar todos los objetos para obtener estadísticas
        total_size = 0
        total_files = 0
        file_types = {}
        
        paginator = r2_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=R2_BUCKET_NAME):
            if 'Contents' in page:
                for obj in page['Contents']:
                    total_size += obj['Size']
                    total_files += 1
                    
                    # Contar por tipo de archivo
                    key = obj['Key']
                    if '.' in key:
                        ext = key.split('.')[-1].lower()
                        file_types[ext] = file_types.get(ext, 0) + 1
        
        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'file_types': file_types,
            'bucket': R2_BUCKET_NAME
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'bucket': R2_BUCKET_NAME
        }