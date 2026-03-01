# api2/utils/r2_direct.py - VERSIÓN COMPATIBLE CON WINDOWS
"""
R2 Direct Upload - Versión Windows compatible
Con nuevo formato de keys: songs/audio/{uuid}.mp3
"""

import os
import uuid
import time
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


class R2DirectUpload:
    """
    Versión Windows compatible - SIN EMOJIS
    Formato de keys: songs/audio/{uuid}.mp3
    """

    def __init__(self):
        """Inicialización para R2 - Windows compatible"""
        try:
            self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME

            self.s3_client = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(
                    signature_version="s3v4",
                    s3={'addressing_style': 'virtual'}
                ),
            )
            
            logger.info(f"[OK] R2DirectUpload inicializado. Bucket: {self.bucket_name}")
            
        except Exception as e:
            logger.error(f"[ERROR] Error inicializando R2DirectUpload: {e}")
            raise

    def generate_presigned_put(
        self,
        user_id: int,
        file_name: str,
        file_size: int,
        file_type: str = "application/octet-stream",
        expires_in: int = 3600,
        custom_metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Genera URL PUT con formato songs/audio/{uuid}.mp3
        CORREGIDO: Solo incluye metadata con valor para evitar error SignatureDoesNotMatch
        """
        try:
            logger.info(f"[PROCESANDO] Generando URL PUT para user {user_id}, archivo: {file_name}")

            # Generar UUID completo
            file_uuid = str(uuid.uuid4())
            
            # Obtener extensión del archivo original
            extension = os.path.splitext(file_name)[1]
            if not extension:
                # Mapeo de content-type a extensión
                ext_map = {
                    'audio/mpeg': '.mp3',
                    'audio/mp3': '.mp3',
                    'audio/wav': '.wav',
                    'audio/flac': '.flac',
                    'audio/m4a': '.m4a',
                    'audio/aac': '.aac',
                    'audio/ogg': '.ogg',
                    'audio/x-m4a': '.m4a',
                    'audio/x-wav': '.wav'
                }
                extension = ext_map.get(file_type, '.mp3')
            
            # NUEVO FORMATO: songs/audio/{uuid}{extension}
            key = f"songs/audio/{file_uuid}{extension}"

            # 🔥 SOLUCIÓN: Solo incluir metadata que TIENE VALOR
            metadata = {}
            
            # Metadata obligatoria (siempre con valor)
            metadata['x-amz-meta-user_id'] = str(user_id)
            metadata['x-amz-meta-file_uuid'] = file_uuid
            metadata['x-amz-meta-upload_timestamp'] = datetime.utcnow().isoformat()
            
            # Metadata del usuario (solo si tiene valor)
            if custom_metadata:
                # Campos principales
                for field in ['artist', 'title', 'genre', 'album', 'year', 'track_number', 'lyrics', 'composer']:
                    if field in custom_metadata and custom_metadata[field] is not None:
                        value = str(custom_metadata[field]).strip()
                        if value:
                            metadata[f'x-amz-meta-{field}'] = value
                
                # Nombre original (prioridad)
                if 'original_name' in custom_metadata and custom_metadata['original_name']:
                    safe_name = self._safe_filename(custom_metadata['original_name'])
                    metadata['x-amz-meta-original_filename'] = safe_name
            
            # Si no hay original_name, usar file_name sanitizado
            if 'x-amz-meta-original_filename' not in metadata:
                metadata['x-amz-meta-original_filename'] = self._safe_filename(file_name)

            # Parámetros para la URL firmada
            params = {
                'Bucket': self.bucket_name,
                'Key': key,
            }
            
            # Solo añadir Metadata si hay alguna (si está vacío, no incluir el campo)
            if metadata:
                params['Metadata'] = metadata

            # Generar URL pre-firmada
            presigned_url = self.s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params=params,
                ExpiresIn=expires_in,
                HttpMethod='PUT'
            )

            if not presigned_url or '?' not in presigned_url:
                raise ValueError("URL pre-firmada inválida")

            # Respuesta con nuevo formato
            result = {
                "upload_url": presigned_url,
                "method": "PUT",
                "file_key": key,
                "file_name": file_name,
                "file_uuid": file_uuid,
                "file_size": file_size,
                "suggested_content_type": file_type,
                "expires_at": int(time.time() + expires_in),
                "expires_in": expires_in,
                "user_id": user_id,
                "key_structure": {
                    "format": "songs/audio/{uuid}{extension}",
                    "uuid": file_uuid,
                    "extension": extension,
                    "full_key": key
                }
            }

            # Incluir metadata original si existe (para referencia)
            if custom_metadata:
                result["metadata"] = custom_metadata

            logger.info(f"[OK] URL PUT generada: {key}")
            return result

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"[ERROR] Error S3 ({error_code}) generando URL: {e}")
            raise
        except Exception as e:
            logger.error(f"[ERROR] Error inesperado: {e}", exc_info=True)
            raise

    def verify_upload_complete(
        self,
        key: str,
        expected_size: Optional[int] = None,
        expected_user_id: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verifica que un archivo existe en R2 y es válido
        """
        try:
            # Verificar existencia
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )

            actual_size = response.get('ContentLength', 0)
            metadata = response.get('Metadata', {})

            # Validaciones
            validation = {
                "size_match": True,
                "owner_match": True,
                "key_pattern_valid": True,
                "issues": []
            }

            # Validar tamaño
            if expected_size and actual_size != expected_size:
                validation["size_match"] = False
                validation["issues"].append(
                    f"Tamaño: esperado {expected_size:,}B, actual {actual_size:,}B"
                )

            # Validar ownership por metadata
            if expected_user_id:
                meta_user_id = metadata.get('x-amz-meta-user_id')
                
                if meta_user_id is None:
                    validation["owner_match"] = False
                    validation["issues"].append("No hay user_id en metadata")
                elif str(meta_user_id) != str(expected_user_id):
                    validation["owner_match"] = False
                    validation["issues"].append(
                        f"Ownership: esperado {expected_user_id}, metadata tiene {meta_user_id}"
                    )

            # Validar patrón de key
            key_validation = self._validate_key_pattern(key)
            if not key_validation["is_valid"]:
                validation["key_pattern_valid"] = False
                validation["issues"].append(f"Key inválida: {key_validation.get('error')}")

            # Construir respuesta
            info = {
                "exists": True,
                "size": actual_size,
                "content_type": response.get('ContentType', ''),
                "etag": response.get('ETag', '').strip('"'),
                "last_modified": response.get('LastModified'),
                "metadata": metadata,
                "validation": validation,
                "key_analysis": key_validation
            }

            is_valid = all([
                info["exists"],
                validation["size_match"],
                validation["owner_match"],
                validation["key_pattern_valid"]
            ])

            logger.info(f"[VERIFICACION] Key: {key} | Valido: {is_valid}")
            
            return is_valid, info

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"[WARNING] Archivo no encontrado: {key}")
                return False, {
                    "exists": False,
                    "error": "File not found in R2",
                    "validation": {
                        "size_match": False,
                        "owner_match": False,
                        "key_pattern_valid": False,
                        "issues": ["Archivo no existe en R2"]
                    }
                }
            else:
                logger.error(f"[ERROR] Error verificando archivo {key}: {e}")
                return False, {
                    "exists": False,
                    "error": f"S3 Error: {e}",
                    "validation": {
                        "size_match": False,
                        "owner_match": False,
                        "key_pattern_valid": False,
                        "issues": [f"Error de conexión: {e}"]
                    }
                }
        except Exception as e:
            logger.error(f"[ERROR] Error inesperado verificando {key}: {e}")
            return False, {
                "exists": False,
                "error": str(e),
                "validation": {
                    "size_match": False,
                    "owner_match": False,
                    "key_pattern_valid": False,
                    "issues": [f"Error interno: {e}"]
                }
            }

    # ==========================================================
    # MÉTODOS AUXILIARES
    # ==========================================================

    def _extract_user_id_from_key(self, key: str) -> Optional[int]:
        """
        Extrae user_id de metadata (ya no de la key)
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            metadata = response.get('Metadata', {})
            user_id = metadata.get('x-amz-meta-user_id')
            
            if user_id:
                return int(user_id)
            return None
            
        except (ClientError, ValueError, TypeError):
            return None

    def _validate_key_pattern(self, key: str) -> Dict[str, Any]:
        """
        Valida patrón de key: songs/audio/{uuid}.mp3
        """
        # Patrón para UUIDv4: 8-4-4-4-12 caracteres hexadecimales
        uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
        pattern = rf'^songs/audio/({uuid_pattern})(\.[a-z0-9]+)$'
        
        match = re.match(pattern, key, re.IGNORECASE)
        
        if not match:
            return {
                "is_valid": False,
                "error": "Patrón de key inválido",
                "expected_pattern": "songs/audio/{uuid}.mp3",
                "received": key
            }
        
        try:
            return {
                "is_valid": True,
                "components": {
                    "uuid": match.group(1),
                    "extension": match.group(2)
                }
            }
        except (ValueError, TypeError) as e:
            return {
                "is_valid": False,
                "error": f"Componente inválido en key: {e}"
            }

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Sanitiza nombre de archivo"""
        import unicodedata
        
        # Normalizar unicode
        filename = unicodedata.normalize('NFKD', filename)
        filename = filename.encode('ASCII', 'ignore').decode('ASCII')
        
        # Solo nombre base
        filename = os.path.basename(filename)
        
        # Reemplazar caracteres no seguros
        filename = re.sub(r'[^\w\s\-\.]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        filename = re.sub(r'_+', '_', filename)
        
        # Limitar longitud
        if len(filename) > 180:
            name, ext = os.path.splitext(filename)
            filename = name[:180 - len(ext)] + ext
        
        return filename.strip('_.')

    def add_metadata_to_file(self, key: str, metadata: Dict[str, str], user_id: Optional[int] = None) -> bool:
        """Añade metadata a un archivo existente"""
        try:
            # Validar ownership si se proporciona user_id
            if user_id:
                meta_user_id = self._extract_user_id_from_key(key)
                if meta_user_id != user_id:
                    logger.warning(f"[WARNING] Intento de modificar archivo de otro usuario: {key}")
                    return False

            # Verificar que existe
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            except ClientError:
                return False

            # Preparar metadata
            safe_metadata = {}
            
            # Obtener metadata existente
            try:
                response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
                existing_metadata = response.get('Metadata', {})
                safe_metadata.update(existing_metadata)
            except:
                pass
            
            # Añadir nueva metadata (solo con valor)
            for k, v in metadata.items():
                if v is not None and str(v).strip():
                    safe_metadata[f'x-amz-meta-{k}'] = str(v)
            
            # Copiar con nueva metadata
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource={'Bucket': self.bucket_name, 'Key': key},
                Key=key,
                Metadata=safe_metadata,
                MetadataDirective='REPLACE'
            )
            
            logger.info(f"[INFO] Metadata añadida a {key}")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Error añadiendo metadata: {e}")
            return False

    def delete_file(self, key: str) -> Tuple[bool, str]:
        """Elimina archivo de R2"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            logger.info(f"[INFO] Archivo eliminado: {key}")
            return True, "File deleted"
        except ClientError as e:
            error_msg = f"S3 Error: {e.response['Error'].get('Message', str(e))}"
            logger.error(f"[ERROR] Error eliminando {key}: {error_msg}")
            return False, error_msg
        except Exception as e:
            logger.error(f"[ERROR] Error eliminando {key}: {e}")
            return False, str(e)

    def generate_download_url(
        self,
        key: str,
        filename: Optional[str] = None,
        expires_in: int = 300
    ) -> Optional[str]:
        """Genera URL de descarga firmada"""
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': key
            }
            
            if filename:
                params['ResponseContentDisposition'] = f'attachment; filename="{filename}"'

            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"[ERROR] Error generando URL de descarga: {e}")
            return None

    def extract_key_info(self, key: str) -> Dict[str, Any]:
        """Extrae información de una key"""
        validation = self._validate_key_pattern(key)
        
        if validation["is_valid"]:
            return {
                "key": key,
                "is_valid": True,
                "uuid": validation["components"]["uuid"],
                "extension": validation["components"]["extension"]
            }
        else:
            return {
                "key": key,
                "is_valid": False,
                "error": validation.get("error", "Key inválida")
            }


# ==========================================================
# CLASES DE COMPATIBILIDAD
# ==========================================================

class R2UploadValidator:
    """
    Clase de compatibilidad para código existente
    Mantiene la misma interfaz que antes
    """
    
    @staticmethod
    def validate_file_key(key: str, user_id: Optional[int] = None) -> Tuple[bool, str]:
        """Valida que una key sea segura"""
        if not key:
            return False, "Key vacía"
        
        if '..' in key or key.startswith('/'):
            return False, "Key con formato inválido"
        
        if len(key) > 500:
            return False, "Key demasiado larga"
        
        # Validar formato general (songs/audio/)
        if not key.startswith('songs/audio/'):
            return False, "Key debe empezar con songs/audio/"
        
        return True, "Key válida"
    
    @staticmethod
    def extract_user_id_from_key(key: str) -> Optional[int]:
        """Extrae user_id de una key (compatibilidad)"""
        # En el nuevo formato, el user_id está en metadata
        return None
    
    @staticmethod
    def sanitize_key(key: str) -> str:
        """Sanitiza una key"""
        key = re.sub(r'//+', '/', key)
        key = re.sub(r'\.\.+', '.', key)
        key = key.strip().lstrip('/')
        return key


# ==========================================================
# INSTANCIAS GLOBALES
# ==========================================================

r2_upload = R2DirectUpload()
r2_direct = r2_upload  # Compatibilidad total


def generate_presigned_put_url(user_id: int, file_name: str, file_size: int, **kwargs) -> Dict[str, Any]:
    """Helper para compatibilidad"""
    return r2_upload.generate_presigned_put(user_id, file_name, file_size, **kwargs)


def verify_r2_upload(key: str, **kwargs) -> Tuple[bool, Dict[str, Any]]:
    """Helper para compatibilidad"""
    return r2_upload.verify_upload_complete(key, **kwargs)