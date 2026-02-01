# test_real_r2.py
import os
import boto3
from botocore.client import Config
import uuid

def test_r2_connection():
    """Prueba REAL de conexión a R2"""
    
    # Leer variables de entorno
    account_id = os.getenv('R2_ACCOUNT_ID')
    access_key = os.getenv('R2_ACCESS_KEY')
    secret_key = os.getenv('R2_SECRET_KEY')
    bucket_name = os.getenv('R2_BUCKET_NAME', 'djidji-media')
    
    if not all([account_id, access_key, secret_key]):
        print("❌ Faltan variables de entorno R2")
        print("   Configura: R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY")
        return False
    
    try:
        # Crear cliente S3 compatible con R2
        s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4')
        )
        
        # Listar buckets (prueba de conexión)
        response = s3_client.list_buckets()
        buckets = [b['Name'] for b in response['Buckets']]
        
        print(f"✅ Conexión a R2 exitosa")
        print(f"   Account ID: {account_id}")
        print(f"   Buckets disponibles: {', '.join(buckets)}")
        
        # Verificar que nuestro bucket existe
        if bucket_name in buckets:
            print(f"   ✅ Bucket '{bucket_name}' encontrado")
            
            # Probar generación de URL firmada
            test_key = f"test-{uuid.uuid4().hex[:8]}.txt"
            
            url = s3_client.generate_presigned_post(
                Bucket=bucket_name,
                Key=test_key,
                ExpiresIn=3600
            )
            
            print(f"   ✅ URL firmada generada correctamente")
            print(f"   📋 URL: {url['url']}")
            print(f"   📋 Campos: {list(url['fields'].keys())}")
            
            return True
        else:
            print(f"   ❌ Bucket '{bucket_name}' no encontrado")
            return False
            
    except Exception as e:
        print(f"❌ Error de conexión a R2: {e}")
        return False

if __name__ == "__main__":
    print("🔗 Probando conexión REAL a R2 CloudFlare...")
    print("="*50)
    
    success = test_r2_connection()
    
    print("="*50)
    if success:
        print("🎉 ¡R2 configurado correctamente para uploads reales!")
    else:
        print("⚠  Configura las variables de entorno para pruebas reales")