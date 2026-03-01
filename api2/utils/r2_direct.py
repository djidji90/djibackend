# api2/utils/r2_direct.py - VERSIÓN COMPATIBLE CON WINDOWS
"""
R2 Direct Upload - Versión Windows compatible
Formato de keys: songs/audio/{12chars}_audio.mp3
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
    Formato de keys: songs/audio/{12chars}_audio.mp3
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
        Genera URL PUT con formato songs/audio/{12chars}_audio.mp3
        """
        try:
            logger.info(f"[PROCESANDO] Generando URL PUT para user {user_id}, archivo: {file_name}")

            # 🔥 NUEVO FORMATO: 12 caracteres hexadecimales
            file_uuid = uuid.uuid4().hex[:12]  # Ejemplo: "11f6b4ca6de9"
            
            # Obtener extensión (siempre .mp3 para audio, como en el ejemplo)
            # Pero mantenemos la lógica por si acaso
            extension = os.path.splitext(file_name)[1]
            if not extension:
                ext_map = {
                    'audio/mpeg': '.mp3',
                    'audio/mp3': '.mp3',
                    'audio/wav': '.wav',
                    'audio/flac': '.flac',
                    'audio/m4a': '.m4a',
                    'audio/aac': '.aac',
                    'audio/ogg': '.ogg',
                }
                extension = ext_map.get(file_type, '.mp3')
            
            # 🔥 NUEVO FORMATO: songs/audio/{12chars}_audio{extension}
            key = f"songs/audio/{file_uuid}_audio{extension}"

            # Parámetros mínimos (sin metadata para evitar errores de firma)
            params = {
                'Bucket': self.bucket_name,
                'Key': key,
            }

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
                    "format": "songs/audio/{12chars}_audio{extension}",
                    "uuid": file_uuid,
                    "extension": extension,
                    "full_key": key
                }
            }

            # Incluir metadata original si existe (para referencia en BD)
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

            # Validar ownership (en el nuevo formato no hay user_id en la ruta)
            # El user_id se valida por la sesión en la BD, no por la key
            if expected_user_id:
                # Opcional: buscar user_id en metadata si existe
                meta_user_id = metadata.get('user_id') or metadata.get('x-amz-meta-user_id')
                if meta_user_id and str(meta_user_id) != str(expected_user_id):
                    validation["owner_match"] = False
                    validation["issues"].append(
                        f"Ownership: metadata indica user {meta_user_id}, esperado {expected_user_id}"
                    )
                # Si no hay metadata, confiamos en la sesión (ya validada antes)

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
                # Nota: owner_match puede ser True incluso sin validación de key
                # porque confiamos en la sesión
                validation["owner_match"] if expected_user_id else True,
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
        Extrae user_id de la key (para compatibilidad)
        En el nuevo formato, el user_id NO está en la ruta
        """
        # Intentar extraer de metadata si es posible
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            metadata = response.get('Metadata', {})
            user_id = metadata.get('user_id') or metadata.get('x-amz-meta-user_id')
            if user_id:
                return int(user_id)
        except:
            pass
        
        return None

    def _validate_key_pattern(self, key: str) -> Dict[str, Any]:
        """
        Valida patrón de key: songs/audio/{12chars}_audio.{ext}
        """
        # Patrón: songs/audio/12caracteres_audio.extension
        pattern = r'^songs/audio/([a-f0-9]{12})_audio(\.[a-z0-9]+)$'
        match = re.match(pattern, key, re.IGNORECASE)
        
        if not match:
            return {
                "is_valid": False,
                "error": "Patrón de key inválido",
                "expected_pattern": "songs/audio/{12hex}_audio.{ext}",
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
        """Sanitiza nombre de archivo (para referencia, no para la key)"""
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
                if meta_user_id and meta_user_id != user_id:
                    logger.warning(f"[WARNING] Intento de modificar archivo de otro usuario: {key}")
                    return False

            # Verificar que existe
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            except ClientError:
                return False

            # Preparar metadata (sin prefijo x-amz-meta-, boto3 lo añade)
            safe_metadata = {}
            for k, v in metadata.items():
                if v is not None and str(v).strip():
                    safe_metadata[k] = str(v)
            
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
        # En el nuevo formato, el user_id está en metadata o sesión
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