"""
R2 Direct Upload Utility - Production Ready Version

Maneja uploads directos a Cloudflare R2 usando URLs firmadas generadas por boto3.
Este módulo NO implementa firma manual - usa las utilidades probadas de AWS SDK.
"""

import os
import uuid
import logging
from datetime import datetime
import boto3
from botocore.client import Config
from django.conf import settings

logger = logging.getLogger(__name__)


class R2DirectUpload:
    """
    Maneja uploads directos a Cloudflare R2 con confirmación manual.
    
    Características:
    - Genera URLs firmadas con expiración usando boto3
    - Verifica uploads manualmente (HEAD requests)
    - Proporciona URLs temporales para descarga/validación
    - Gestiona eliminación y listado de archivos
    
    Nota: R2 no tiene webhooks nativos, por lo que usamos verificación manual.
    """

    def __init__(self):
        """Inicializa cliente S3 compatible con Cloudflare R2."""
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        # Configuración optimizada para R2
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": "virtual",  # Compatible con R2
                    "payload_signing_enabled": False,  # Mejor performance
                },
            ),
        )
        logger.info(f"R2DirectUpload inicializado para bucket: {self.bucket_name}")

    # ==========================================================
    # GENERACIÓN DE URLS PARA UPLOAD
    # ==========================================================

    def generate_presigned_post(
        self,
        *,
        user_id: int,
        file_name: str,
        file_size: int,
        file_type: str = "",
        expires_in: int = 3600,
    ) -> dict:
        """
        Genera URL firmada para upload directo a R2.
        
        Args:
            user_id: ID del usuario autenticado
            file_name: Nombre original del archivo
            file_size: Tamaño en bytes (validado previamente)
            file_type: Tipo MIME (ej: 'audio/mpeg')
            expires_in: Segundos hasta que expira la URL (default: 1 hora)
        
        Returns:
            Dict con:
            - url: URL para POST
            - fields: Campos para incluir en FormData
            - key: R2 key donde se guardará el archivo
            - expires_at: Timestamp UNIX de expiración
        """
        # Validaciones básicas
        if file_size <= 0:
            raise ValueError("file_size debe ser mayor a 0")
        if file_size > settings.R2_MAX_FILE_SIZE:
            raise ValueError(f"file_size excede el límite de {settings.R2_MAX_FILE_SIZE} bytes")
        
        # Generar key única y segura
        key = self._generate_secure_key(user_id, file_name)
        logger.debug(f"Generando URL para key: {key}, tamaño: {file_size}, usuario: {user_id}")
        
        # Configurar condiciones de la política
        conditions = [
            ["content-length-range", 1, file_size],  # Validación estricta de tamaño
            {"bucket": self.bucket_name},
            {"key": key},
            {"x-amz-meta-uploader-id": str(user_id)},
            {"x-amz-meta-original-name": self._safe_filename(file_name)},
        ]
        
        # Incluir content-type si se especifica
        if file_type:
            conditions.append(["starts-with", "$Content-Type", file_type])
        
        # Generar URL firmada usando boto3 (no firmamos manualmente)
        try:
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=key,
                Fields={
                    "x-amz-meta-uploader-id": str(user_id),
                    "x-amz-meta-original-name": self._safe_filename(file_name),
                    "x-amz-meta-upload-timestamp": datetime.utcnow().isoformat(),
                },
                Conditions=conditions,
                ExpiresIn=expires_in,
            )
            
            expires_at = datetime.utcnow().timestamp() + expires_in
            
            return {
                "success": True,
                "url": response["url"],
                "fields": response["fields"],
                "key": key,
                "expires_at": expires_at,
                "expires_in": expires_in,
                "file_name": file_name,
                "file_size": file_size,
                "file_type": file_type,
                "bucket": self.bucket_name,
                "user_id": user_id,
            }
            
        except Exception as e:
            logger.error(f"Error generando URL firmada: {str(e)}", exc_info=True)
            raise

    # ==========================================================
    # VERIFICACIÓN Y VALIDACIÓN
    # ==========================================================

    def verify_file_uploaded(self, key: str) -> tuple[bool, dict]:
        """
        Verifica que un archivo exista en R2 y devuelve sus metadatos.
        
        Args:
            key: R2 key del archivo
        
        Returns:
            Tuple (existe: bool, metadata: dict)
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            
            metadata = {
                "exists": True,
                "size": response.get("ContentLength", 0),
                "content_type": response.get("ContentType", ""),
                "last_modified": response.get("LastModified"),
                "etag": response.get("ETag", ""),
                "metadata": response.get("Metadata", {}),
                "storage_class": response.get("StorageClass", "STANDARD"),
            }
            
            logger.debug(f"Archivo verificado en R2: {key}, tamaño: {metadata['size']}")
            return True, metadata
            
        except self.s3_client.exceptions.ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            if error_code == "404":
                logger.debug(f"Archivo no encontrado en R2: {key}")
                return False, {"exists": False, "error": "File not found", "code": "404"}
            elif error_code == "403":
                logger.warning(f"Permiso denegado para archivo: {key}")
                return False, {"exists": False, "error": "Access denied", "code": "403"}
            else:
                logger.error(f"Error de cliente S3 para {key}: {error_code}", exc_info=True)
                return False, {"exists": False, "error": str(e), "code": error_code}
                
        except Exception as e:
            logger.error(f"Error verificando archivo {key}: {str(e)}", exc_info=True)
            return False, {"exists": False, "error": str(e), "code": "Unknown"}

    def validate_upload_integrity(
        self, 
        key: str, 
        expected_size: int = None, 
        expected_uploader_id: int = None
    ) -> dict:
        """
        Valida integridad de un archivo subido.
        
        Args:
            key: R2 key del archivo
            expected_size: Tamaño esperado en bytes (opcional)
            expected_uploader_id: ID del usuario esperado (opcional)
        
        Returns:
            Dict con resultados de validación
        """
        exists, metadata = self.verify_file_uploaded(key)
        
        if not exists:
            return {
                "valid": False,
                "exists": False,
                "error": "File does not exist in R2",
                "key": key,
            }
        
        issues = []
        
        # Validar tamaño si se especifica
        if expected_size and metadata.get("size") != expected_size:
            issues.append(
                f"Size mismatch: expected {expected_size}, got {metadata.get('size')}"
            )
        
        # Validar metadata del uploader
        if expected_uploader_id:
            actual_uploader_id = metadata.get("metadata", {}).get("uploader-id")
            if actual_uploader_id != str(expected_uploader_id):
                issues.append(
                    f"Uploader mismatch: expected {expected_uploader_id}, got {actual_uploader_id}"
                )
        
        # Validar que tenga metadata básica
        required_metadata = ["uploader-id", "original-name"]
        for meta_key in required_metadata:
            if meta_key not in metadata.get("metadata", {}):
                issues.append(f"Missing required metadata: {meta_key}")
        
        return {
            "valid": len(issues) == 0,
            "exists": True,
            "issues": issues,
            "metadata": metadata,
            "key": key,
            "size": metadata.get("size"),
            "content_type": metadata.get("content_type"),
            "uploader_id": metadata.get("metadata", {}).get("uploader-id"),
        }

    # ==========================================================
    # DESCARGA Y ACCESO TEMPORAL
    # ==========================================================

    def generate_download_url(self, key: str, expires_in: int = 300) -> str | None:
        """
        Genera URL temporal para descargar/validar archivo.
        
        Args:
            key: R2 key del archivo
            expires_in: Segundos hasta expiración (default: 5 minutos)
        
        Returns:
            URL firmada temporal o None en caso de error
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                },
                ExpiresIn=expires_in,
            )
            logger.debug(f"URL de descarga generada para {key}, expira en {expires_in}s")
            return url
            
        except Exception as e:
            logger.error(f"Error generando URL de descarga para {key}: {str(e)}")
            return None

    def generate_upload_status_url(self, key: str) -> str | None:
        """
        Genera URL para verificar estado de upload (HEAD request).
        
        Args:
            key: R2 key del archivo
        
        Returns:
            URL para HEAD request o None en caso de error
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "head_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                },
                ExpiresIn=60,  # Corta expiración para checks rápidos
            )
            return url
            
        except Exception as e:
            logger.error(f"Error generando URL de status para {key}: {str(e)}")
            return None

    # ==========================================================
    # GESTIÓN DE ARCHIVOS
    # ==========================================================

    def delete_file(self, key: str) -> bool:
        """
        Elimina un archivo de R2.
        
        Args:
            key: R2 key del archivo
        
        Returns:
            True si se eliminó exitosamente, False en caso contrario
        """
        try:
            response = self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            
            deleted = response.get("DeleteMarker", False) or response.get("VersionId")
            if deleted:
                logger.info(f"Archivo eliminado de R2: {key}")
            else:
                logger.warning(f"Archivo no se pudo eliminar de R2: {key}")
                
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"Error eliminando archivo {key}: {str(e)}")
            return False

    def list_user_files(
        self, 
        user_id: int, 
        prefix: str = "uploads/direct/",
        max_keys: int = 1000
    ) -> list:
        """
        Lista archivos de un usuario específico en R2.
        
        Args:
            user_id: ID del usuario
            prefix: Prefijo para filtrar (default: 'uploads/direct/')
            max_keys: Máximo número de resultados
        
        Returns:
            Lista de dicts con información de archivos
        """
        try:
            files = []
            continuation_token = None
            
            # Manejar paginación para muchos archivos
            while True:
                list_kwargs = {
                    "Bucket": self.bucket_name,
                    "Prefix": f"{prefix}{user_id}/",
                    "MaxKeys": min(max_keys, 1000),  # AWS limita a 1000 por request
                }
                
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token
                
                response = self.s3_client.list_objects_v2(**list_kwargs)
                
                for obj in response.get("Contents", []):
                    files.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                        "etag": obj.get("ETag", ""),
                        "storage_class": obj.get("StorageClass", "STANDARD"),
                    })
                
                # Verificar si hay más resultados
                if response.get("IsTruncated"):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break
            
            logger.debug(f"Listados {len(files)} archivos para usuario {user_id}")
            return files
            
        except Exception as e:
            logger.error(f"Error listando archivos para usuario {user_id}: {str(e)}")
            return []

    def get_user_storage_usage(self, user_id: int) -> dict:
        """
        Calcula uso de almacenamiento de un usuario.
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Dict con estadísticas de uso
        """
        files = self.list_user_files(user_id)
        
        total_size = sum(f["size"] for f in files)
        file_count = len(files)
        
        return {
            "user_id": user_id,
            "file_count": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_size_gb": round(total_size / (1024 * 1024 * 1024), 3),
            "files": files[:10],  # Primeros 10 archivos
        }

    # ==========================================================
    # MÉTODOS PRIVADOS - SEGURIDAD Y KEY GENERATION
    # ==========================================================

    def _generate_secure_key(self, user_id: int, file_name: str) -> str:
        """
        Genera una key única y segura para R2.
        
        Estructura: uploads/direct/{user_id}/{timestamp}_{uuid}{ext}
        
        Args:
            user_id: ID del usuario
            file_name: Nombre original del archivo
        
        Returns:
            Key segura para R2
        """
        # Timestamp en formato seguro para S3
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # UUID único (8 caracteres es suficiente para este caso)
        unique_id = uuid.uuid4().hex[:8]
        
        # Extensión segura
        ext = self._get_safe_extension(file_name)
        
        # Construir key
        key = f"uploads/direct/{user_id}/{timestamp}_{unique_id}{ext}"
        
        logger.debug(f"Key generada: {key} para usuario {user_id}, archivo {file_name}")
        return key

    @staticmethod
    def _get_safe_extension(file_name: str) -> str:
        """
        Extrae y sanitiza extensión de archivo.
        
        Args:
            file_name: Nombre del archivo
        
        Returns:
            Extensión sanitizada (ej: '.mp3')
        """
        # Extraer extensión
        _, ext = os.path.splitext(file_name)
        
        # Si no hay extensión, usar .bin como default seguro
        if not ext:
            return ".bin"
        
        # Normalizar a minúsculas y limitar longitud
        ext = ext.lower()
        
        # Validar que sea una extensión razonable
        # (protección contra nombres de archivo maliciosos)
        if len(ext) > 20:  # Extensiones razonables son cortas
            return ".bin"
        
        # Remover caracteres peligrosos
        import re
        safe_ext = re.sub(r'[^a-z0-9._-]', '', ext)
        
        return safe_ext if safe_ext.startswith('.') else f".{safe_ext}"

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """
        Sanitiza nombre de archivo para metadata S3.
        
        Args:
            filename: Nombre original del archivo
        
        Returns:
            Nombre sanitizado y seguro
        """
        import re
        
        # Remover path traversal attempts
        safe_name = os.path.basename(filename)
        
        # Remover caracteres peligrosos para S3 metadata
        safe_name = re.sub(r'[^\w.\-]', '_', safe_name)
        
        # Limitar longitud (S3 metadata tiene límites)
        return safe_name[:250]


# ==========================================================
# INSTANCIA GLOBAL - SINGLETON PATTERN
# ==========================================================

r2_direct = R2DirectUpload()


# ==========================================================
# UTILIDADES ADICIONALES
# ==========================================================

class R2UploadValidator:
    """Utilidades para validación de uploads."""
    
    @staticmethod
    def validate_file_key(key: str, user_id: int = None) -> tuple[bool, str]:
        """
        Valida que una R2 key sea segura y pertenezca al usuario.
        
        Args:
            key: R2 key a validar
            user_id: ID del usuario (opcional, para validación de ownership)
        
        Returns:
            Tuple (es_válida: bool, mensaje: str)
        """
        if not key:
            return False, "Key vacía"
        
        # Validar formato básico
        if not key.startswith("uploads/direct/"):
            return False, "Key no sigue el patrón esperado"
        
        # Validar que no tenga path traversal
        if ".." in key or "//" in key:
            return False, "Key contiene patrones peligrosos"
        
        # Validar ownership si se proporciona user_id
        if user_id is not None:
            expected_prefix = f"uploads/direct/{user_id}/"
            if not key.startswith(expected_prefix):
                return False, "Key no pertenece al usuario"
        
        return True, "Key válida"
    
    @staticmethod
    def extract_user_id_from_key(key: str) -> int | None:
        """
        Extrae user_id de una R2 key.
        
        Args:
            key: R2 key
        
        Returns:
            user_id o None si no se puede extraer
        """
        try:
            # Patrón: uploads/direct/{user_id}/...
            parts = key.split("/")
            if len(parts) >= 3 and parts[0] == "uploads" and parts[1] == "direct":
                return int(parts[2])
        except (ValueError, IndexError):
            pass
        return None


# ==========================================================
# EXCEPCIONES ESPECÍFICAS
# ==========================================================

class R2UploadError(Exception):
    """Excepción base para errores de R2."""
    pass

class R2ConfigError(R2UploadError):
    """Error de configuración de R2."""
    pass

class R2ValidationError(R2UploadError):
    """Error de validación de archivo."""
    pass

class R2PermissionError(R2UploadError):
    """Error de permisos en R2."""
    pass