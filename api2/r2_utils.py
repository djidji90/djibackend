import os
import logging
import hashlib
import time
from io import BytesIO
from functools import lru_cache
from botocore.exceptions import ClientError

# Importar configuración R2 desde r2_client
from .r2_client import r2_client, R2_BUCKET_NAME

logger = logging.getLogger(__name__)

# =============================================================================
# ⚙️ CONFIGURACIÓN DE CACHE
# =============================================================================

# Importar cache de Django (si está disponible, si no usar cache simple)
try:
    from django.core.cache import cache
    from django.conf import settings
    CACHE_AVAILABLE = True
    # Configuración específica para URLs presigned
    PRESIGNED_URL_CACHE_TIMEOUT = getattr(settings, 'PRESIGNED_URL_CACHE_TIMEOUT', 1800)  # 30 minutos
    FILE_EXISTS_CACHE_TIMEOUT = getattr(settings, 'FILE_EXISTS_CACHE_TIMEOUT', 300)  # 5 minutos
    CACHE_PREFIX = getattr(settings, 'R2_CACHE_PREFIX', 'r2')
except ImportError:
    CACHE_AVAILABLE = False
    # Fallback a cache en memoria simple
    _simple_cache = {}
    
    class SimpleCache:
        def get(self, key, default=None):
            return _simple_cache.get(key, default)
        
        def set(self, key, value, timeout=None):
            _simple_cache[key] = value
        
        def delete(self, key):
            _simple_cache.pop(key, None)
    
    cache = SimpleCache()
    PRESIGNED_URL_CACHE_TIMEOUT = 1800
    FILE_EXISTS_CACHE_TIMEOUT = 300
    CACHE_PREFIX = 'r2'

# =============================================================================
# ✅ FUNCIONES AUXILIARES CON CACHE
# =============================================================================

def validate_key(key):
    """Valida que la key no esté vacía"""
    if not key or not isinstance(key, str) or key.strip() == "":
        logger.warning("Key vacía o inválida proporcionada")
        return False
    return True

@lru_cache(maxsize=128)
def get_content_type_from_key(key):
    """
    Determina el content type basado en la extensión
    Usa cache LRU para mejorar performance
    """
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


def _get_cache_key(prefix, key, *args):
    """Genera una clave de cache consistente"""
    parts = [prefix, key] + [str(arg) for arg in args]
    cache_string = ":".join(parts)
    return f"{CACHE_PREFIX}:{hashlib.md5(cache_string.encode()).hexdigest()}"

# =============================================================================
# ✅ GENERAR URLS PRESIGNED CON CACHE (FUNCIÓN CRÍTICA)
# =============================================================================

def generate_presigned_url(key, expiration=3600, use_cache=True):
    """
    Genera una URL temporal CACHEADA para acceder a un archivo privado en R2
    
    Args:
        key: Clave del archivo en R2
        expiration: Tiempo en segundos que la URL será válida (default: 1 hora)
        use_cache: Usar cache (True por defecto) - IMPORTANTE para production
    
    Returns:
        str: URL firmada o None si hay error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return None

    if not validate_key(key):
        logger.error(f"Key inválida para URL presigned: {key}")
        return None

    # ========== IMPLEMENTACIÓN DE CACHE ==========
    if use_cache:
        cache_key = _get_cache_key("presigned_url", key, expiration)
        
        # Intentar obtener del cache
        cached_url = cache.get(cache_key)
        if cached_url is not None:  # Explicit check for None (cache could return None)
            logger.debug(f"URL presigned obtenida de CACHE: {key[:50]}...")
            return cached_url
    # ========== FIN CACHE ==========

    try:
        # Generar nueva URL (esto hace una llamada a R2)
        url = r2_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET_NAME, 'Key': key},
            ExpiresIn=expiration
        )
        
        if url:
            logger.info(f"URL presigned generada NUEVA para: {key[:50]}... (expira en {expiration}s)")
            
            # ========== GUARDAR EN CACHE ==========
            if use_cache:
                # Cachear por menos tiempo que la expiración (para evitar URLs caducadas)
                # Ej: URL expira en 3600s, cacheamos por 3000s (50 minutos)
                cache_timeout = min(expiration - 600, PRESIGNED_URL_CACHE_TIMEOUT)
                if cache_timeout > 0:
                    cache.set(cache_key, url, timeout=cache_timeout)
                    logger.debug(f"URL guardada en CACHE por {cache_timeout}s: {key[:50]}...")
            # ========== FIN CACHE ==========
        else:
            logger.warning(f"URL presigned vacía generada para: {key}")
            
        return url

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] generando URL para '{key[:50]}...': {error_msg}")
        return None

    except Exception as e:
        logger.error(f"Error generando URL presigned para '{key[:50]}...': {str(e)}")
        return None


def generate_presigned_urls_batch(keys, expiration=3600):
    """
    Genera múltiples URLs presigned optimizadas con cache
    Útil para endpoints que devuelven muchas canciones (como /songs/random/)
    
    Args:
        keys: Lista de keys de archivos
        expiration: Tiempo de expiración en segundos
    
    Returns:
        dict: {key: url} con todas las URLs (puede incluir None para errores)
    """
    if not keys:
        return {}
    
    result = {}
    keys_to_generate = []
    
    # 1. Obtener del cache primero
    for key in keys:
        if not validate_key(key):
            result[key] = None
            continue
            
        cache_key = _get_cache_key("presigned_url", key, expiration)
        cached_url = cache.get(cache_key)
        
        if cached_url is not None:
            result[key] = cached_url
            logger.debug(f"URL batch desde cache: {key[:30]}...")
        else:
            keys_to_generate.append(key)
            result[key] = None  # Placeholder
    
    # 2. Generar URLs faltantes
    if keys_to_generate:
        logger.info(f"Generando {len(keys_to_generate)} URLs presigned nuevas en batch")
        
        for key in keys_to_generate:
            try:
                url = r2_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': R2_BUCKET_NAME, 'Key': key},
                    ExpiresIn=expiration
                )
                
                result[key] = url
                
                # Guardar en cache si se generó correctamente
                if url:
                    cache_key = _get_cache_key("presigned_url", key, expiration)
                    cache_timeout = min(expiration - 600, PRESIGNED_URL_CACHE_TIMEOUT)
                    if cache_timeout > 0:
                        cache.set(cache_key, url, timeout=cache_timeout)
                        
            except Exception as e:
                logger.warning(f"Error generando URL para {key[:30]}... en batch: {e}")
                result[key] = None
    
    return result


def invalidate_presigned_url_cache(key, expiration=None):
    """
    Invalida el cache de una URL presigned
    Útil cuando se elimina o actualiza un archivo
    
    Args:
        key: Clave del archivo
        expiration: Expiración específica (None para todas)
    
    Returns:
        bool: True si se invalidó, False si hubo error
    """
    try:
        if expiration:
            # Invalidar solo para una expiración específica
            cache_key = _get_cache_key("presigned_url", key, expiration)
            cache.delete(cache_key)
            logger.debug(f"Cache invalidado para URL (exp={expiration}): {key[:50]}...")
        else:
            # Invalidar para todas las expiraciones comunes
            common_expirations = [300, 600, 1800, 3600, 7200]
            for exp in common_expirations:
                cache_key = _get_cache_key("presigned_url", key, exp)
                cache.delete(cache_key)
            logger.debug(f"Cache invalidado para todas las URLs: {key[:50]}...")
        
        # También invalidar cache de existencia
        exists_cache_key = _get_cache_key("file_exists", key)
        cache.delete(exists_cache_key)
        
        return True
        
    except Exception as e:
        logger.error(f"Error invalidando cache para {key[:50]}...: {e}")
        return False

# =============================================================================
# ✅ SUBIR ARCHIVOS A R2 (FUNCIÓN EXISTENTE OPTIMIZADA)
# =============================================================================

def upload_file_to_r2(file_obj, key, content_type=None, invalidate_cache=True):
    """
    Sube un archivo a R2 Cloudflare Storage - VERSIÓN OPTIMIZADA
    
    Args:
        file_obj: Objeto archivo (UploadedFile, BytesIO, o ruta string)
        key: Clave única en R2 (ej: 'songs/audio/uuid.mp3')
        content_type: Tipo MIME (opcional, se deduce si no se proporciona)
        invalidate_cache: Invalidar cache de URLs después de subir
    
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
                        
                        # Invalidar cache después de subir
                        if invalidate_cache:
                            invalidate_presigned_url_cache(key)
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
        
        # Invalidar cache después de subir
        if invalidate_cache:
            invalidate_presigned_url_cache(key)
        
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] subiendo '{key}': {error_msg}")
        return False

    except Exception as e:
        logger.error(f"Error inesperado subiendo archivo '{key}' a R2: {str(e)}", exc_info=True)
        return False

# =============================================================================
# ✅ ELIMINAR ARCHIVOS CON CACHE INVALIDATION
# =============================================================================

def delete_file_from_r2(key, invalidate_cache=True):
    """
    Elimina un archivo de R2 Cloudflare Storage
    
    Args:
        key: Clave del archivo a eliminar
        invalidate_cache: Invalidar cache de URLs después de eliminar
    
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
                
                # Aún así invalidar cache por si acaso
                if invalidate_cache:
                    invalidate_presigned_url_cache(key)
                return True
            else:
                raise

        # Eliminar el archivo
        r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        logger.info(f"Archivo eliminado de R2: {key}")
        
        # Invalidar cache después de eliminar
        if invalidate_cache:
            invalidate_presigned_url_cache(key)
        
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"Error R2 [{error_code}] eliminando '{key}': {error_msg}")
        return False

    except Exception as e:
        logger.error(f"Error eliminando archivo '{key}' de R2: {str(e)}")
        return False

# =============================================================================
# ✅ VERIFICAR EXISTENCIA DE ARCHIVOS CON CACHE
# =============================================================================

def check_file_exists(key, use_cache=True):
    """
    Verifica si un archivo existe en R2 CON CACHE
    
    Args:
        key: Clave del archivo a verificar
        use_cache: Usar cache (True por defecto)
    
    Returns:
        bool: True si existe, False si no existe o hay error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return False

    if not validate_key(key):
        return False

    # ========== IMPLEMENTACIÓN DE CACHE ==========
    if use_cache:
        cache_key = _get_cache_key("file_exists", key)
        cached_result = cache.get(cache_key)
        
        if cached_result is not None:
            logger.debug(f"Existencia obtenida de CACHE: {key[:50]}... = {cached_result}")
            return cached_result
    # ========== FIN CACHE ==========

    try:
        r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        exists = True
        logger.debug(f"Archivo existe en R2 (verificado): {key[:50]}...")
        
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            exists = False
            logger.debug(f"Archivo no encontrado en R2: {key[:50]}...")
        else:
            logger.warning(f"Error verificando archivo '{key[:50]}...': {e}")
            exists = False
    
    except Exception as e:
        logger.error(f"Error inesperado verificando '{key[:50]}...': {e}")
        exists = False

    # ========== GUARDAR EN CACHE ==========
    if use_cache:
        cache.set(cache_key, exists, timeout=FILE_EXISTS_CACHE_TIMEOUT)
    # ========== FIN CACHE ==========
    
    return exists

# =============================================================================
# ✅ OBTENER INFORMACIÓN DE ARCHIVOS CON CACHE
# =============================================================================

def get_file_size(key, use_cache=True):
    """
    Obtiene el tamaño de un archivo en R2 (en bytes) CON CACHE
    
    Args:
        key: Clave del archivo
        use_cache: Usar cache (True por defecto)
    
    Returns:
        int: Tamaño en bytes, o None si hay error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return None

    if not validate_key(key):
        return None

    # ========== IMPLEMENTACIÓN DE CACHE ==========
    if use_cache:
        cache_key = _get_cache_key("file_size", key)
        cached_size = cache.get(cache_key)
        
        if cached_size is not None:
            logger.debug(f"Tamaño obtenido de CACHE: {key[:50]}... = {cached_size} bytes")
            return cached_size
    # ========== FIN CACHE ==========

    try:
        response = r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
        size = response['ContentLength']
        logger.debug(f"Tamaño del archivo '{key[:50]}...': {size} bytes")
        
        # ========== GUARDAR EN CACHE ==========
        if use_cache:
            cache.set(cache_key, size, timeout=FILE_EXISTS_CACHE_TIMEOUT)
        # ========== FIN CACHE ==========
        
        return size

    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.debug(f"Archivo no encontrado al obtener tamaño: {key[:50]}...")
        else:
            logger.error(f"Error obteniendo tamaño de '{key[:50]}...': {e}")
        return None

    except Exception as e:
        logger.error(f"Error obteniendo tamaño de '{key[:50]}...': {str(e)}")
        return None

def get_file_info(key, use_cache=True):
    """
    Obtiene información completa de un archivo en R2 CON CACHE
    
    Args:
        key: Clave del archivo
        use_cache: Usar cache (True por defecto)
    
    Returns:
        dict: Información del archivo o None si hay error
    """
    if not r2_client:
        logger.error("Cliente R2 no disponible")
        return None

    if not validate_key(key):
        return None

    # ========== IMPLEMENTACIÓN DE CACHE ==========
    if use_cache:
        cache_key = _get_cache_key("file_info", key)
        cached_info = cache.get(cache_key)
        
        if cached_info is not None:
            logger.debug(f"Información obtenida de CACHE: {key[:50]}...")
            return cached_info
    # ========== FIN CACHE ==========

    try:
        response = r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=key)

        info = {
            'size': response['ContentLength'],
            'content_type': response.get('ContentType', get_content_type_from_key(key)),
            'last_modified': response.get('LastModified'),
            'etag': response.get('ETag'),
            'metadata': response.get('Metadata', {})
        }

        logger.debug(f"Información obtenida para '{key[:50]}...': {info}")
        
        # ========== GUARDAR EN CACHE ==========
        if use_cache:
            cache.set(cache_key, info, timeout=FILE_EXISTS_CACHE_TIMEOUT)
        # ========== FIN CACHE ==========
        
        return info

    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.debug(f"Archivo no encontrado al obtener info: {key[:50]}...")
        else:
            logger.error(f"Error obteniendo info de '{key[:50]}...': {e}")
        return None

    except Exception as e:
        logger.error(f"Error obteniendo info de '{key[:50]}...': {str(e)}")
        return None

# =============================================================================
# ✅ LISTAR ARCHIVOS (FUNCIÓN EXISTENTE)
# =============================================================================

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

# =============================================================================
# ✅ COPIAR ARCHIVOS CON CACHE INVALIDATION
# =============================================================================

def copy_file_in_r2(source_key, destination_key, invalidate_cache=True):
    """
    Copia un archivo dentro de R2
    
    Args:
        source_key: Clave del archivo origen
        destination_key: Clave del archivo destino
        invalidate_cache: Invalidar cache del archivo destino
    
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
        
        # Invalidar cache del archivo destino
        if invalidate_cache:
            invalidate_presigned_url_cache(destination_key)
        
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
# ✅ STREAM FILE FROM R2 - VERSIÓN OPTIMIZADA (EXISTENTE)
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
            f"R2 Response - Key: {key[:50]}... | "
            f"Size: {result['ContentLength']} | "
            f"Type: {result['ContentType']}"
        )

        return result

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']

        if error_code == 'NoSuchKey':
            logger.error(f"Archivo no encontrado en R2: {key[:50]}...")
        elif error_code == 'InvalidRange':
            logger.error(f"Range inválido para {key[:50]}...: {params.get('Range')}")
        elif error_code == 'AccessDenied':
            logger.error(f"Acceso denegado a {key[:50]}...")
        else:
            logger.error(f"Error R2 [{error_code}] streaming {key[:50]}...: {error_msg}")

        return None

    except Exception as e:
        logger.error(f"Error inesperado streaming {key[:50]}...: {str(e)}", exc_info=True)
        return None

# =============================================================================
# ✅ FUNCIONES DE DIAGNÓSTICO Y MONITOREO
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


def get_cache_stats():
    """
    Obtiene estadísticas del cache (si está disponible)
    
    Returns:
        dict: Estadísticas del cache
    """
    if not CACHE_AVAILABLE:
        return {'cache_available': False, 'message': 'Cache de Django no disponible'}
    
    try:
        # Esta es una implementación básica, puedes expandirla según tu backend de cache
        stats = {
            'cache_available': True,
            'cache_prefix': CACHE_PREFIX,
            'presigned_url_timeout': PRESIGNED_URL_CACHE_TIMEOUT,
            'file_exists_timeout': FILE_EXISTS_CACHE_TIMEOUT,
            'backend': getattr(settings, 'CACHES', {}).get('default', {}).get('BACKEND', 'unknown')
        }
        
        # Intentar obtener algunas métricas básicas
        test_key = f"{CACHE_PREFIX}:test_stats"
        cache.set(test_key, 'test_value', timeout=10)
        stats['cache_working'] = cache.get(test_key) == 'test_value'
        cache.delete(test_key)
        
        return stats
        
    except Exception as e:
        return {
            'cache_available': CACHE_AVAILABLE,
            'error': str(e)
        }


def clear_r2_cache(key=None):
    """
    Limpia el cache de R2 (útil para desarrollo/debug)
    
    Args:
        key: Clave específica a limpiar (None para limpiar todo)
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        cleared = 0
        
        if key:
            # Limpiar cache específico para una key
            invalidate_presigned_url_cache(key)
            cleared += 1
        else:
            # Limpiar todo el cache relacionado con R2
            # Esto depende del backend de cache
            if hasattr(cache, 'delete_pattern'):
                # Redis u otros backends que soportan patterns
                cache.delete_pattern(f"{CACHE_PREFIX}:*")
                cleared = "all"
            else:
                # Para backends simples, no podemos limpiar selectivamente
                if hasattr(cache, 'clear'):
                    cache.clear()
                    cleared = "all"
                else:
                    return {
                        'success': False,
                        'message': 'Backend de cache no soporta limpieza masiva'
                    }
        
        return {
            'success': True,
            'cleared': cleared,
            'message': f'Cache limpiado: {cleared} entradas'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# =============================================================================
# ✅ FUNCIÓN DE MONITOREO DE PERFORMANCE
# =============================================================================

def monitor_r2_performance():
    """
    Monitorea el performance de las operaciones R2
    Útil para identificar cuellos de botella
    
    Returns:
        dict: Métricas de performance
    """
    import time
    
    test_key = f"test_perf_{int(time.time())}.txt"
    test_content = b"Test content for performance monitoring"
    
    metrics = {
        'generate_presigned_url': {},
        'upload_file': {},
        'check_file_exists': {},
        'get_file_size': {},
        'delete_file': {}
    }
    
    # Test 1: generate_presigned_url (con y sin cache)
    try:
        # Primera llamada (sin cache)
        start = time.time()
        url1 = generate_presigned_url(test_key, use_cache=False)
        time1 = time.time() - start
        
        # Segunda llamada (con cache debería ser más rápido)
        start = time.time()
        url2 = generate_presigned_url(test_key, use_cache=True)
        time2 = time.time() - start
        
        metrics['generate_presigned_url'] = {
            'first_call_ms': round(time1 * 1000, 2),
            'second_call_ms': round(time2 * 1000, 2),
            'improvement_percent': round(((time1 - time2) / time1) * 100, 1) if time1 > 0 else 0,
            'url_generated': url1 is not None
        }
    except Exception as e:
        metrics['generate_presigned_url']['error'] = str(e)
    
    # Test 2: Operaciones básicas con un archivo temporal
    try:
        # Subir archivo de prueba
        start = time.time()
        upload_success = upload_file_to_r2(
            BytesIO(test_content),
            test_key,
            content_type='text/plain',
            invalidate_cache=False
        )
        metrics['upload_file']['time_ms'] = round((time.time() - start) * 1000, 2)
        metrics['upload_file']['success'] = upload_success
        
        if upload_success:
            # Verificar existencia
            start = time.time()
            exists = check_file_exists(test_key)
            metrics['check_file_exists']['time_ms'] = round((time.time() - start) * 1000, 2)
            metrics['check_file_exists']['success'] = exists
            
            # Obtener tamaño
            start = time.time()
            size = get_file_size(test_key)
            metrics['get_file_size']['time_ms'] = round((time.time() - start) * 1000, 2)
            metrics['get_file_size']['success'] = size == len(test_content)
            
            # Eliminar archivo de prueba
            start = time.time()
            delete_success = delete_file_from_r2(test_key, invalidate_cache=False)
            metrics['delete_file']['time_ms'] = round((time.time() - start) * 1000, 2)
            metrics['delete_file']['success'] = delete_success
    
    except Exception as e:
        metrics['error'] = str(e)
        # Asegurarse de limpiar el archivo de prueba si hubo error
        try:
            delete_file_from_r2(test_key, invalidate_cache=False)
        except:
            pass
    
    return metrics