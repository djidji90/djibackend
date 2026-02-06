# api2/utils/r2_direct.py - VERSIÓN COMPLETA CORREGIDA PARA WINDOWS

""" 
R2 Direct Upload Utility - VERSIÓN CORREGIDA
SOLUCIÓN DEFINITIVA PARA ERROR 403
Presigned PUT mínimo y robusto
Sin headers extraños, sin firma frágil
"""

import os
import uuid
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

# Configurar logger
logger = logging.getLogger(__name__)


class R2DirectUpload:
    """
    VERSIÓN CORREGIDA: Presigned PUT mínimo para R2
    Sigue el patrón correcto: URL con firma en query params, sin headers extra
    """

    def __init__(self):
        """Inicializa cliente S3 para R2 con configuración corregida"""
        try:
            self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            
            # Configuración robusta para R2
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(
                    signature_version="s3v4",
                    s3={
                        'addressing_style': 'virtual'
                    }
                ),
            )
            # ✅ SIN EMOJIS PARA WINDOWS
            logger.info(f"[OK] R2DirectUpload inicializado. Bucket: {self.bucket_name}")
            logger.info(f"     Endpoint: {settings.AWS_S3_ENDPOINT_URL}")
        except Exception as e:
            logger.error(f"[ERROR] Error inicializando R2DirectUpload: {e}")
            raise

    # ==========================================================
    # MÉTODO PRINCIPAL CORREGIDO - VERSIÓN SIMPLE Y ROBUSTA
    # ==========================================================

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
        GENERA URL PUT PRE-FIRMADA - VERSIÓN CORRECTA
        Parámetros MÍNIMOS en la firma:
        - Solo Bucket y Key
        - NO ContentType (el cliente lo envía si quiere)
        - NO Metadata (se añade después)
        - NO Content-Length (no debe firmarse)
        """
        try:
            # ✅ SIN EMOJIS
            logger.info(f"[PROCESANDO] Generando URL PUT para user {user_id}, archivo: {file_name}")
            
            # 1. SANITIZAR Y GENERAR KEY ÚNICA
            safe_name = self._safe_filename(file_name)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            
            # Estructura: uploads/user_123/20250205_143022_abc123ef_mi_audio.mp3
            key = f"uploads/user_{user_id}/{timestamp}_{unique_id}_{safe_name}"

            # 2. PARÁMETROS MÍNIMOS PARA LA FIRMA
            # ¡IMPORTANTE! Solo Bucket y Key, nada más
            params = {
                'Bucket': self.bucket_name,
                'Key': key,
                # ❌ NO INCLUIR ContentType aquí
                # ❌ NO INCLUIR Metadata aquí
                # ❌ NO INCLUIR ContentLength aquí
            }

            # 3. GENERAR URL PRE-FIRMADA (FIRMA EN QUERY PARAMS)
            logger.debug(f"Generando URL para key: {key}")
            presigned_url = self.s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params=params,
                ExpiresIn=expires_in,
                HttpMethod='PUT'
            )

            # 4. VALIDAR URL GENERADA
            if not presigned_url:
                raise ValueError("No se pudo generar URL pre-firmada")
                
            if '?' not in presigned_url or 'X-Amz-Signature=' not in presigned_url:
                logger.warning(f"URL generada parece no tener firma: {presigned_url[:100]}...")

            # 5. METADATA PARA GUARDAR EN BASE DE DATOS (NO SE ENVÍA AL CLIENTE)
            metadata_to_store = {
                'user_id': str(user_id),
                'original_name': safe_name,
                'expected_size': file_size,
                'expected_type': file_type,
                'upload_timestamp': datetime.utcnow().isoformat(),
                'custom_metadata': custom_metadata or {},
            }

            # 6. RESPUESTA MÍNIMA Y CORRECTA
            result = {
                "success": True,
                "upload_url": presigned_url,  # URL completa con firma en query
                "method": "PUT",               # Siempre PUT
                "file_key": key,               # Para verificación posterior
                "file_name": safe_name,
                "file_size": file_size,
                "file_type": file_type,
                "expires_at": int(time.time() + expires_in),
                "expires_in": expires_in,
                "user_id": user_id,
                "metadata": metadata_to_store,  # Solo para backend
                "instructions": {
                    "method": "PUT",
                    "body": "binary_file_data",
                    "content_type_suggested": file_type,
                    "important_notes": [
                        "1. Usa PUT (no POST) a la URL proporcionada",
                        "2. Envía el archivo binario como cuerpo de la petición",
                        "3. Content-Type es opcional (sugerido: usar el proporcionado)",
                        "4. NO añadas headers X-Amz-* (ya están en la URL)",
                        "5. Después del upload, confirma en el endpoint de confirmación"
                    ]
                }
            }

            # ✅ SIN EMOJIS
            logger.info(f"[OK] URL PUT generada exitosamente para key: {key}")
            logger.debug(f"URL: {presigned_url[:80]}...")
            return result

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            # ✅ SIN EMOJIS
            logger.error(f"[ERROR] Error de S3 generando URL PUT: {error_code} - {error_msg}")
            raise
        except Exception as e:
            logger.error(f"[ERROR] Error inesperado generando URL PUT: {e}", exc_info=True)
            raise

    # ==========================================================
    # MÉTODOS POST-UPLOAD (PARA METADATA E INTEGRIDAD)
    # ==========================================================

    def verify_upload_complete(
        self,
        key: str,
        expected_size: Optional[int] = None,
        expected_user_id: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verifica que un upload se completó correctamente.
        """
        try:
            # 1. VERIFICAR QUE EL ARCHIVO EXISTE
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )

            # 2. INFORMACIÓN DEL ARCHIVO REAL
            actual_size = response.get('ContentLength', 0)
            actual_content_type = response.get('ContentType', '')
            actual_metadata = response.get('Metadata', {})
            etag = response.get('ETag', '').strip('"')
            last_modified = response.get('LastModified')

            info = {
                "exists": True,
                "size": actual_size,
                "content_type": actual_content_type,
                "etag": etag,
                "last_modified": last_modified,
                "metadata": actual_metadata,
                "validation": {
                    "size_match": True,
                    "user_match": True,
                    "issues": []
                }
            }

            # 3. VALIDACIONES
            if expected_size and actual_size != expected_size:
                info["validation"]["size_match"] = False
                info["validation"]["issues"].append(
                    f"Tamaño incorrecto: esperado {expected_size}, actual {actual_size}"
                )

            if expected_user_id:
                actual_user_id = actual_metadata.get('user_id')
                if not actual_user_id:
                    info["validation"]["user_match"] = False
                    info["validation"]["issues"].append("No hay metadata user_id")
                elif str(actual_user_id) != str(expected_user_id):
                    info["validation"]["user_match"] = False
                    info["validation"]["issues"].append(
                        f"User ID mismatch: esperado {expected_user_id}, actual {actual_user_id}"
                    )

            # 4. CALCULAR INTEGRIDAD
            all_valid = (
                info["validation"]["size_match"] and
                info["validation"]["user_match"]
            )

            # ✅ SIN EMOJIS
            logger.info(f"[OK] Verificación completada para {key}. Válido: {all_valid}")
            return all_valid, info

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # ✅ SIN EMOJIS
                logger.warning(f"[WARNING] Archivo no encontrado: {key}")
                return False, {"exists": False, "error": "File not found"}
            else:
                logger.error(f"[ERROR] Error verificando archivo {key}: {e}")
                return False, {"exists": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[ERROR] Error inesperado verificando {key}: {e}")
            return False, {"exists": False, "error": str(e)}

    def add_metadata_to_file(
        self,
        key: str,
        metadata: Dict[str, str],
        user_id: Optional[int] = None
    ) -> bool:
        """
        Añade metadata a un archivo ya subido usando copy_object.
        """
        try:
            # 1. VALIDAR QUE EL ARCHIVO EXISTE
            exists, info = self.verify_upload_complete(key, expected_user_id=user_id)
            if not exists:
                logger.error(f"[ERROR] No se puede añadir metadata, archivo no existe: {key}")
                return False

            # 2. PREPARAR METADATA (todos los campos como strings)
            safe_metadata = {}
            for k, v in metadata.items():
                if v is not None:
                    safe_metadata[str(k)] = str(v)

            # 3. COPIAR OBJETO CONSIGO MISMO PARA AÑADIR/REEMPLAZAR METADATA
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': key
            }

            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource=copy_source,
                Key=key,
                Metadata=safe_metadata,
                MetadataDirective='REPLACE',
                ContentType=info.get('content_type', 'application/octet-stream'),
                CacheControl='max-age=31536000',
                ContentDisposition=f'attachment; filename="{info.get("metadata", {}).get("original_name", key.split("/")[-1])}"'
            )

            # ✅ SIN EMOJIS
            logger.info(f"[OK] Metadata añadida a {key}: {list(safe_metadata.keys())}")
            return True

        except ClientError as e:
            logger.error(f"[ERROR] Error S3 añadiendo metadata a {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Error inesperado añadiendo metadata a {key}: {e}")
            return False

    def delete_file(self, key: str) -> Tuple[bool, str]:
        """Elimina archivo de R2"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            # ✅ SIN EMOJIS
            logger.info(f"[OK] Archivo eliminado: {key}")
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
        """Genera URL temporal para descargar archivo"""
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
            logger.debug(f"[DEBUG] URL de descarga generada para {key}")
            return url
        except Exception as e:
            logger.error(f"[ERROR] Error generando URL de descarga: {e}")
            return None

    # ==========================================================
    # MÉTODOS AUXILIARES
    # ==========================================================

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Sanitiza nombre de archivo para uso seguro en S3"""
        import re
        import unicodedata
        
        # Normalizar unicode
        filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')
        
        # Tomar solo el nombre base (sin path)
        filename = os.path.basename(filename)
        
        # Reemplazar caracteres peligrosos
        filename = re.sub(r'[^\w\s.-]', '_', filename)
        
        # Reemplazar espacios
        filename = re.sub(r'\s+', '_', filename)
        
        # Limitar longitud
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200 - len(ext)] + ext
            
        return filename

    @staticmethod
    def _get_safe_extension(filename: str) -> str:
        """Extrae extensión segura del nombre de archivo"""
        import re
        _, ext = os.path.splitext(filename.lower())
        
        if not ext:
            return ""
        
        # Limpiar extensión
        ext = re.sub(r'[^a-z0-9]', '', ext)
        if not ext:
            return ""
        
        # Limitar longitud de extensión
        if len(ext) > 10:
            ext = ext[:10]
            
        return f".{ext}"

    @staticmethod
    def extract_key_info(key: str) -> Dict[str, Any]:
        """Extrae información de una R2 key"""
        import re
        
        info = {
            "key": key,
            "is_valid": False,
            "user_id": None,
            "timestamp": None,
            "filename": None
        }
        
        try:
            pattern = r'^uploads/user_(\d+)/(\d{8}_\d{6})_([a-f0-9]{8})_(.+)$'
            match = re.match(pattern, key)
            
            if match:
                info.update({
                    "is_valid": True,
                    "user_id": int(match.group(1)),
                    "timestamp": match.group(2),
                    "unique_id": match.group(3),
                    "filename": match.group(4)
                })
                
            return info
        except Exception:
            return info


# ==========================================================
# ✅ CLASE R2UploadValidator PARA COMPATIBILIDAD
# ==========================================================

class R2UploadValidator:
    """Utilidades para validación de uploads."""
    
    @staticmethod
    def validate_file_key(key: str, user_id: Optional[int] = None) -> Tuple[bool, str]:
        """
        Valida que una R2 key sea segura y pertenezca al usuario.
        """
        if not key:
            return False, "Key vacía"
        
        # Validar formato básico
        if '..' in key or key.startswith('/') or '//' in key:
            return False, "Key con formato inválido"
        
        # Validar longitud
        if len(key) > 500:
            return False, "Key demasiado larga"
        
        # Validar caracteres peligrosos
        import re
        dangerous_patterns = [r'\.\.', r'/', r'\\', r'%00', r'<', r'>']
        for pattern in dangerous_patterns:
            if re.search(pattern, key):
                return False, f"Key contiene caracteres peligrosos: {pattern}"
        
        # Validar ownership si se proporciona user_id
        if user_id is not None:
            expected_prefix = f"uploads/user_{user_id}/"
            if not key.startswith(expected_prefix):
                return False, f"Key no pertenece al usuario {user_id}"
        
        return True, "Key válida"
    
    @staticmethod
    def extract_user_id_from_key(key: str) -> Optional[int]:
        """Extrae el user_id de una R2 key"""
        import re
        match = re.search(r'uploads/user_(\d+)/', key)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                return None
        return None
    
    @staticmethod
    def sanitize_key(key: str) -> str:
        """Sanitiza una R2 key para uso seguro"""
        import re
        # Remover doble slashes
        key = re.sub(r'//+', '/', key)
        # Remover puntos peligrosos
        key = re.sub(r'\.\.+', '.', key)
        # Remover espacios
        key = key.strip()
        # Asegurar que no empiece con /
        key = key.lstrip('/')
        
        return key


# ==========================================================
# 🔌 INSTANCIA GLOBAL Y FUNCIONES HELPER
# ==========================================================

# Instancia global para usar en toda la app
r2_upload = R2DirectUpload()

# ✅ ALIAS PARA COMPATIBILIDAD
r2_direct = r2_upload  # Para código existente que usa r2_direct


def generate_presigned_put_url(
    user_id: int,
    file_name: str,
    file_size: int,
    **kwargs
) -> Dict[str, Any]:
    """
    Función helper para compatibilidad con código existente.
    """
    return r2_upload.generate_presigned_put(
        user_id=user_id,
        file_name=file_name,
        file_size=file_size,
        **kwargs
    )


def verify_r2_upload(
    key: str,
    **kwargs
) -> Tuple[bool, Dict[str, Any]]:
    """
    Función helper para verificar uploads.
    """
    return r2_upload.verify_upload_complete(key, **kwargs)