# api2/utils/r2_direct.py - VERSIÓN COMPATIBLE CON WINDOWS

"""
R2 Direct Upload - Versión Windows compatible
Sin emojis, con compatibilidad total
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
            
            # ✅ SIN EMOJIS PARA WINDOWS
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
        PUT mínimo y robusto - Windows compatible
        """
        try:
            logger.info(f"[PROCESANDO] Generando URL PUT para user {user_id}, archivo: {file_name}")

            # Generar key con estructura de ownership
            safe_name = self._safe_filename(file_name)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            
            key = f"uploads/user_{user_id}/{timestamp}_{unique_id}_{safe_name}"

            # Parámetros mínimos (robustos)
            params = {
                'Bucket': self.bucket_name,
                'Key': key,
                # ❌ NO 'ContentType': file_type (evita 403 por mismatch)
            }

            # Generar URL pre-firmada
            presigned_url = self.s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params=params,
                ExpiresIn=expires_in,
                HttpMethod='PUT'
            )

            # Validación básica
            if not presigned_url or '?' not in presigned_url:
                raise ValueError("URL pre-firmada inválida")

            # Respuesta coherente
            result = {
                "upload_url": presigned_url,
                "method": "PUT",
                "file_key": key,
                "file_name": safe_name,
                "file_size": file_size,
                "suggested_content_type": file_type,  # ✅ Solo sugerencia
                "expires_at": int(time.time() + expires_in),
                "expires_in": expires_in,
                "user_id": user_id,
                "key_structure": {
                    "format": "uploads/user_{id}/timestamp_uuid_filename",
                    "ownership_proof": "path_based"
                }
            }

            logger.info(f"[OK] URL PUT generada exitosamente para key: {key}")
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
        Verificación robusta - Windows compatible
        """
        try:
            # Verificar existencia física
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )

            # Extraer información básica
            actual_size = response.get('ContentLength', 0)

            # Validación coherente
            validation = {
                "size_match": True,
                "owner_match": True,
                "key_pattern_valid": True,
                "issues": []
            }

            # Validar tamaño si se espera
            if expected_size and actual_size != expected_size:
                validation["size_match"] = False
                validation["issues"].append(
                    f"Tamaño: esperado {expected_size:,}B, actual {actual_size:,}B"
                )

            # Validar ownership por estructura de key
            if expected_user_id:
                extracted_user_id = self._extract_user_id_from_key(key)
                
                if extracted_user_id is None:
                    validation["owner_match"] = False
                    validation["issues"].append("Key no tiene formato de ownership válido")
                elif extracted_user_id != expected_user_id:
                    validation["owner_match"] = False
                    validation["issues"].append(
                        f"Ownership: esperado user_{expected_user_id}, key es user_{extracted_user_id}"
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
                "metadata": response.get('Metadata', {}),
                "validation": validation,
                "key_analysis": key_validation
            }

            # Determinar validez
            is_valid = all([
                info["exists"],
                validation["size_match"],
                validation["owner_match"],
                validation["key_pattern_valid"]
            ])

            logger.info(f"[VERIFICACION] Key: {key} | Valido: {is_valid} | Issues: {len(validation['issues'])}")
            
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
        """Extrae user_id de la estructura de key"""
        try:
            pattern = r'^uploads/user_(\d+)/'
            match = re.match(pattern, key)
            
            if match:
                return int(match.group(1))
            return None
        except (ValueError, TypeError):
            return None

    def _validate_key_pattern(self, key: str) -> Dict[str, Any]:
        """Valida patrón de key"""
        pattern = r'^uploads/user_(\d+)/(\d{8}_\d{6})_([a-f0-9]{8})_([\w\s\-\.]+)$'
        match = re.match(pattern, key)
        
        if not match:
            return {
                "is_valid": False,
                "error": "Patrón de key inválido",
                "expected_pattern": "uploads/user_{id}/YYYYMMDD_HHMMSS_{uuid8}_{filename}"
            }
        
        try:
            return {
                "is_valid": True,
                "components": {
                    "user_id": int(match.group(1)),
                    "timestamp": match.group(2),
                    "uuid": match.group(3),
                    "filename": match.group(4)
                }
            }
        except (ValueError, TypeError):
            return {
                "is_valid": False,
                "error": "Componente inválido en key"
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

    # Métodos existentes (simplificados)
    def add_metadata_to_file(self, key: str, metadata: Dict[str, str], user_id: Optional[int] = None) -> bool:
        """Añade metadata opcional"""
        try:
            # Validar ownership
            if user_id:
                extracted_id = self._extract_user_id_from_key(key)
                if extracted_id != user_id:
                    return False

            # Verificar que existe
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            except ClientError:
                return False

            # Preparar metadata
            safe_metadata = {str(k): str(v) for k, v in metadata.items() if v is not None}
            
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
        """Genera URL de descarga"""
        try:
            params = {'Bucket': self.bucket_name, 'Key': key}
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
                "user_id": validation["components"]["user_id"],
                "timestamp": validation["components"]["timestamp"],
                "filename": validation["components"]["filename"]
            }
        else:
            return {
                "key": key,
                "is_valid": False,
                "user_id": self._extract_user_id_from_key(key),
                "error": validation.get("error", "Key inválida")
            }


# ==========================================================
# ✅ CLASES DE COMPATIBILIDAD (para imports existentes)
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
        
        # Validar ownership si se proporciona user_id
        if user_id is not None:
            pattern = r'^uploads/user_(\d+)/'
            match = re.match(pattern, key)
            if not match:
                return False, f"Key no pertenece al usuario {user_id}"
            
            try:
                key_user_id = int(match.group(1))
                if key_user_id != user_id:
                    return False, f"Key pertenece a otro usuario"
            except (ValueError, TypeError):
                return False, "User ID inválido en key"
        
        return True, "Key válida"
    
    @staticmethod
    def extract_user_id_from_key(key: str) -> Optional[int]:
        """Extrae user_id de una key"""
        pattern = r'uploads/user_(\d+)/'
        match = re.search(pattern, key)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                return None
        return None
    
    @staticmethod
    def sanitize_key(key: str) -> str:
        """Sanitiza una key"""
        import re
        key = re.sub(r'//+', '/', key)
        key = re.sub(r'\.\.+', '.', key)
        key = key.strip().lstrip('/')
        return key


# ==========================================================
# INSTANCIAS GLOBALES
# ==========================================================

r2_upload = R2DirectUpload()
r2_direct = r2_upload  # ✅ Compatibilidad total


def generate_presigned_put_url(user_id: int, file_name: str, file_size: int, **kwargs) -> Dict[str, Any]:
    """Helper para compatibilidad"""
    return r2_upload.generate_presigned_put(user_id, file_name, file_size, **kwargs)


def verify_r2_upload(key: str, **kwargs) -> Tuple[bool, Dict[str, Any]]:
    """Helper para compatibilidad"""
    return r2_upload.verify_upload_complete(key, **kwargs)