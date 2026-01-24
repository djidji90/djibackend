# api2/utils/r2_direct.py
import boto3
from botocore.client import Config
from django.conf import settings
from datetime import datetime, timedelta
import uuid
import os
import json
import base64
import hashlib
import hmac


class R2DirectUpload:
    """Maneja uploads directos a Cloudflare R2 con confirmación manual"""
    
    def __init__(self):
        """Inicializar cliente S3 compatible con R2"""
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'virtual'}  # Compatible con R2
            )
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    
    def generate_presigned_post(self, user_id, file_name, file_size, file_type='', custom_key=None):
        """
        Genera URL y campos para upload directo S3/R2 con políticas firmadas
        
        Args:
            user_id: ID del usuario
            file_name: Nombre original del archivo
            file_size: Tamaño en bytes
            file_type: Tipo MIME (opcional)
            custom_key: Key personalizada (opcional)
        
        Returns:
            Dict con URL, campos firmados y metadata
        """
        # Generar key única para el archivo
        if custom_key:
            key = custom_key
        else:
            key = self._generate_unique_key(user_id, file_name)
        
        # Configurar expiración (1 hora por defecto)
        expiration = datetime.utcnow() + timedelta(
            seconds=getattr(settings, 'R2_URL_EXPIRY', 3600)
        )
        
        # Crear condiciones de la política
        conditions = [
            ["content-length-range", 1, file_size],  # Validar tamaño
            {"bucket": self.bucket_name},
            {"key": key},
            {"x-amz-meta-uploader-id": str(user_id)},
            {"x-amz-meta-original-name": self._safe_filename(file_name)},
            {"x-amz-meta-upload-timestamp": datetime.utcnow().isoformat()},
        ]
        
        # Agregar content-type si se especifica
        if file_type:
            conditions.append(["starts-with", "$Content-Type", file_type])
        
        # Crear política
        policy = {
            "expiration": expiration.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "conditions": conditions
        }
        
        # Convertir política a base64
        policy_json = json.dumps(policy, separators=(',', ':'))
        policy_base64 = base64.b64encode(policy_json.encode()).decode()
        
        # Firmar la política
        signature = self._sign_policy(policy_base64)
        
        # Crear credential string
        credential = self._get_credential_string()
        
        return {
            "url": f"{settings.AWS_S3_ENDPOINT_URL}/{self.bucket_name}",
            "fields": {
                "key": key,
                "bucket": self.bucket_name,
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Credential": credential,
                "X-Amz-Date": datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
                "Policy": policy_base64,
                "X-Amz-Signature": signature,
                "x-amz-meta-uploader-id": str(user_id),
                "x-amz-meta-original-name": self._safe_filename(file_name),
                "x-amz-meta-upload-timestamp": datetime.utcnow().isoformat(),
            },
            "key": key,
            "expires_at": expiration,
            "file_name": file_name,
            "file_size": file_size,
            "file_type": file_type
        }
    
    def verify_file_uploaded(self, key):
        """
        Verifica si un archivo fue subido exitosamente a R2
        
        Args:
            key: S3 key del archivo
        
        Returns:
            Tuple (bool, dict): True si existe, con metadata del archivo
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            metadata = {
                'exists': True,
                'size': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'metadata': response.get('Metadata', {}),
                'etag': response.get('ETag', '')
            }
            
            return True, metadata
        except self.s3_client.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                return False, {'exists': False, 'error': 'File not found'}
            else:
                return False, {'exists': False, 'error': str(e)}
        except Exception as e:
            return False, {'exists': False, 'error': str(e)}
    
    def generate_download_url(self, key, expires_in=300):
        """
        Genera URL temporal para descargar/validar archivo
        
        Args:
            key: S3 key del archivo
            expires_in: Segundos hasta expiración
        
        Returns:
            URL firmada temporal
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': key
                },
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            # Log error but return None
            import logging
            logging.error(f"Error generating download URL for {key}: {str(e)}")
            return None
    
    def delete_file(self, key):
        """
        Elimina un archivo de R2
        
        Args:
            key: S3 key del archivo
        
        Returns:
            bool: True si se eliminó exitosamente
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
        except Exception as e:
            import logging
            logging.error(f"Error deleting file {key}: {str(e)}")
            return False
    
    def list_user_files(self, user_id, prefix='uploads/direct/'):
        """
        Lista archivos de un usuario específico
        
        Args:
            user_id: ID del usuario
            prefix: Prefijo para filtrar
        
        Returns:
            Lista de archivos del usuario
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{prefix}{user_id}/"
            )
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag']
                })
            
            return files
        except Exception as e:
            import logging
            logging.error(f"Error listing files for user {user_id}: {str(e)}")
            return []
    
    # ==================== MÉTODOS PRIVADOS ====================
    
    def _generate_unique_key(self, user_id, file_name):
        """Genera una key única para el archivo"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        ext = self._get_extension(file_name)
        
        # Estructura: uploads/direct/{user_id}/{timestamp}_{unique_id}{ext}
        return f"uploads/direct/{user_id}/{timestamp}_{unique_id}{ext}"
    
    def _get_extension(self, file_name):
        """Obtener extensión del archivo"""
        _, ext = os.path.splitext(file_name)
        return ext.lower() if ext else '.bin'
    
    def _safe_filename(self, filename):
        """Limpia el nombre de archivo para metadata S3"""
        # S3 metadata keys no pueden tener caracteres especiales
        import re
        safe_name = re.sub(r'[^\w\.\-]', '_', filename)
        return safe_name[:250]  # Limitar longitud
    
    def _get_credential_string(self):
        """Generar string de credencial AWS v4"""
        now = datetime.utcnow()
        date_stamp = now.strftime("%Y%m%d")
        return f"{settings.AWS_ACCESS_KEY_ID}/{date_stamp}/auto/s3/aws4_request"
    
    def _sign_policy(self, policy_base64):
        """Firmar política usando AWS Signature V4"""
        now = datetime.utcnow()
        date_stamp = now.strftime("%Y%m%d")
        
        # Derivar clave de firma
        def sign(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        
        # AWS4-HMAC-SHA256 signature calculation
        k_date = sign(("AWS4" + settings.AWS_SECRET_ACCESS_KEY).encode(), date_stamp)
        k_region = sign(k_date, "auto")  # R2 usa "auto" como región
        k_service = sign(k_region, "s3")
        k_signing = sign(k_service, "aws4_request")
        
        # Firmar la política
        signature = hmac.new(
            k_signing,
            policy_base64.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _validate_file_integrity(self, key, expected_size=None, expected_type=None):
        """
        Validar integridad del archivo subido
        
        Args:
            key: S3 key del archivo
            expected_size: Tamaño esperado en bytes
            expected_type: Content-Type esperado
        
        Returns:
            Dict con resultados de validación
        """
        exists, metadata = self.verify_file_uploaded(key)
        
        if not exists:
            return {
                'valid': False,
                'error': 'File does not exist',
                'metadata': metadata
            }
        
        issues = []
        
        # Validar tamaño si se especifica
        if expected_size and metadata.get('size') != expected_size:
            issues.append(f"Size mismatch: expected {expected_size}, got {metadata.get('size')}")
        
        # Validar tipo si se especifica
        if expected_type and metadata.get('content_type') != expected_type:
            issues.append(f"Content type mismatch: expected {expected_type}, got {metadata.get('content_type')}")
        
        # Validar metadata mínima
        required_meta = ['uploader-id']
        for meta_key in required_meta:
            if f'x-amz-meta-{meta_key}' not in metadata.get('metadata', {}):
                issues.append(f"Missing required metadata: {meta_key}")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'metadata': metadata,
            'size': metadata.get('size'),
            'content_type': metadata.get('content_type')
        }


# Instancia global para uso fácil
r2_direct = R2DirectUpload()


# Utilidades adicionales
class UploadValidator:
    """Utilidades para validar uploads"""
    
    @staticmethod
    def validate_audio_file(download_url):
        """
        Valida que un archivo sea un audio válido
        
        Nota: En producción, implementar con mutagen o similar
        """
        # Esta es una implementación básica
        # En producción, deberías descargar y validar el archivo
        
        # Por ahora, solo verificamos la extensión en el URL
        audio_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}
        
        # Extraer extensión del URL
        import urllib.parse
        parsed = urllib.parse.urlparse(download_url)
        path = parsed.path
        _, ext = os.path.splitext(path)
        
        is_audio = ext.lower() in audio_extensions
        
        return {
            'is_audio': is_audio,
            'extension': ext.lower() if ext else None,
            'message': 'Audio validation requires full implementation'
        }
    
    @staticmethod
    def calculate_checksum(file_path):
        """Calcula checksum SHA256 de un archivo"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()